import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import sys
import time


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Check live RGB and depth data, the intrinsics stream, and frame stamps")
    parser.add_argument("--duration-s", type=float, default=6.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not math.isfinite(args.duration_s) or args.duration_s < 3:
        raise ValueError("duration-s must be a finite number of at least three seconds")
    if args.output.exists():
        raise FileExistsError(args.output)
    sys.path.insert(0, str(root / "primitives/r1_camera/rbnx-build/codegen/proto_gen"))

    import grpc
    import numpy as np
    from google.protobuf.empty_pb2 import Empty
    from robonix_api import ATLAS
    import robonix_contracts_pb2_grpc as services

    def collect(provider, kind):
        contract = f"robonix/primitive/camera/{kind}"
        constructors = {
            "rgb": (services.RobonixPrimitiveCameraRgbStub, "Rgb"),
            "depth": (services.RobonixPrimitiveCameraDepthStub, "Depth"),
            "intrinsics": (services.RobonixPrimitiveCameraIntrinsicsStub, "Intrinsics"),
        }
        stub_type, method = constructors[kind]
        records = {}
        with ATLAS.connect_capability(consumer_id="r1-live-geometry-check", provider_id=provider,
                                      contract_id=contract, transport="grpc") as connection:
            with grpc.insecure_channel(connection.endpoint.removeprefix("http://")) as channel:
                stream = getattr(stub_type(channel), method)(Empty(), timeout=args.duration_s + 5)
                began = time.monotonic()
                previous = 0
                try:
                    for message in stream:
                        stamp = message.header.stamp.sec * 1_000_000_000 + message.header.stamp.nanosec
                        age = (time.time_ns() - stamp) / 1_000_000_000
                        if stamp <= previous or not -0.1 <= age <= 2:
                            raise ValueError(f"{provider}/{kind} stamp is invalid or the data timed out: {stamp}, age={age}")
                        previous = stamp
                        record = {"width": message.width, "height": message.height,
                                  "frame_id": message.header.frame_id, "age_s": age}
                        if not record["frame_id"] or message.width <= 0 or message.height <= 0:
                            raise ValueError(f"{provider}/{kind} image size or frame is invalid")
                        if kind == "intrinsics":
                            if len(message.k) != 9 or len(message.r) != 9 or len(message.p) != 12:
                                raise ValueError(f"{provider} CameraInfo matrix length is invalid")
                            if not all(math.isfinite(value) for value in (*message.k, *message.r, *message.p, *message.d)):
                                raise ValueError(f"{provider} CameraInfo contains a non-finite value")
                            record["calibrated"] = message.k[0] > 0 and message.k[4] > 0
                        else:
                            size = 3 if kind == "rgb" else 4
                            encoding = "rgb8" if kind == "rgb" else "32FC1"
                            if message.encoding != encoding or message.is_bigendian != 0:
                                raise ValueError(f"{provider} encoding or byte order is invalid")
                            if message.step != message.width * size or len(message.data) != message.step * message.height:
                                raise ValueError(f"{provider} raw image length is invalid")
                            record["encoding"] = message.encoding
                            if kind == "depth":
                                values = np.frombuffer(message.data, dtype="<f4")
                                finite = values[np.isfinite(values)]
                                if np.isinf(values).any() or not len(finite) or (finite <= 0).any():
                                    raise ValueError("the depth image has no valid positive range, or it contains a non-finite value")
                                record.update(valid_fraction=len(finite) / len(values),
                                              min_m=float(finite.min()), max_m=float(finite.max()),
                                              percentiles_m=np.percentile(finite, [5, 50, 95]).tolist(),
                                              below_0_2_m_fraction=float(np.mean(finite < 0.2)),
                                              above_10_m_fraction=float(np.mean(finite > 10)))
                        records[stamp] = record
                        if time.monotonic() - began >= args.duration_s:
                            break
                finally:
                    stream.cancel()
        if len(records) < 2:
            raise RuntimeError(f"{provider}/{kind} does not have enough valid frames")
        return records

    providers = {"r1_camera": "rgb", "r1_depth": "depth"}
    with ThreadPoolExecutor(max_workers=4) as executor:
        jobs = {(provider, kind): executor.submit(collect, provider, kind)
                for provider, image_kind in providers.items() for kind in (image_kind, "intrinsics")}
        streams = {key: job.result() for key, job in jobs.items()}
    result = {"motion_requested": False, "providers": {}}
    for provider, image_kind in providers.items():
        images = streams[provider, image_kind]
        infos = streams[provider, "intrinsics"]
        matched = sorted(images.keys() & infos.keys())
        if len(matched) < 2:
            raise RuntimeError(f"{provider} has fewer than two stamps shared by the image and CameraInfo")
        for stamp in matched:
            if any(images[stamp][key] != infos[stamp][key] for key in ("width", "height", "frame_id")):
                raise ValueError(f"{provider} same-frame image and CameraInfo do not match")
        stamps = sorted(images)
        elapsed = (stamps[-1] - stamps[0]) / 1_000_000_000
        result["providers"][provider] = {
            "image_frames": len(images), "info_frames": len(infos), "matched_timestamps": len(matched),
            "image_fps": (len(images) - 1) / elapsed, "first_stamp_ns": stamps[0], "last_stamp_ns": stamps[-1],
            "last_image": images[stamps[-1]], "last_info": infos[max(infos)],
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
