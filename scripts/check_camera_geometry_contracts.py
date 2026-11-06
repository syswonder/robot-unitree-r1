import argparse
import json
from pathlib import Path
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="通过真实 Atlas/gRPC 检查相机几何能力，不采集图像或发送运动")
    parser.add_argument("--provider", action="append")
    parser.add_argument("--expect-unconfigured", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--proto-gen", type=Path, default=root / "primitives/r1_camera/rbnx-build/codegen/proto_gen")
    args = parser.parse_args()
    sys.path.insert(0, str(args.proto_gen))

    import grpc
    from google.protobuf.empty_pb2 import Empty
    from robonix_api import ATLAS
    import robonix_contracts_pb2_grpc as services

    records = []
    for provider_id in args.provider or ["r1_camera", "r1_depth"]:
        providers = ATLAS.query_primitives(id=provider_id)
        if len(providers) != 1:
            raise RuntimeError(f"提供方不存在或数量不正确：{provider_id}")
        contracts = {capability.contract_id for capability in providers[0].capabilities}
        required = {"robonix/primitive/camera/intrinsics", "robonix/primitive/camera/extrinsics"}
        if not required <= contracts:
            raise RuntimeError(f"几何能力未完整注册：{provider_id}")
        record = {"provider": provider_id, "state": providers[0].state.name, "contracts": sorted(contracts)}
        with ATLAS.connect_capability(consumer_id="r1-geometry-check", provider_id=provider_id,
                                      contract_id="robonix/primitive/camera/extrinsics", transport="grpc") as connection:
            with grpc.insecure_channel(connection.endpoint.removeprefix("http://")) as channel:
                stream = services.RobonixPrimitiveCameraExtrinsicsStub(channel).Extrinsics(Empty(), timeout=3)
                try:
                    message = next(stream)
                    record.update(extrinsics_available=True, parent_frame=message.header.frame_id,
                                  child_frame=message.child_frame_id)
                except grpc.RpcError as error:
                    if error.code() != grpc.StatusCode.FAILED_PRECONDITION:
                        raise
                    record.update(extrinsics_available=False, status=error.code().name, reason=error.details())
                finally:
                    stream.cancel()
        if args.expect_unconfigured and record["extrinsics_available"]:
            raise RuntimeError(f"预期未配置外参，但收到了值：{provider_id}")
        records.append(record)
    result = {"providers": records, "motion_requested": False, "images_requested": False}
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
