import json
import os
from pathlib import Path

from robonix_api import Ok, Service

import visual_action_pb2
from visual_action_mcp import (
    Cancel_Request, Cancel_Response, Evaluate_Request, Evaluate_Response,
    RunStep_Request, RunStep_Response, Status_Request, Status_Response,
)

from .models import Settings
from .robot import Robot
from .runtime import Runtime

provider = Service(id=os.environ.get("RBNX_INSTANCE_NAME", "visual_action_decider"), namespace="robonix/service/visual_action")
runtime = None


def service():
    if runtime is None:
        raise RuntimeError("视觉动作服务尚未初始化")
    return runtime


def evaluation(request):
    decision = service().evaluate(request)
    return dict(decision_id=str(decision.decision_id), selected_action=decision.selected_action.value,
                action_ids=[action.value for action in decision.probabilities],
                probabilities=list(decision.probabilities.values()), total_ms=decision.timings_ms["service_total"],
                result_json=decision.model_dump_json())


def task_status(record, include_error=True):
    result = dict(run_id=record["run_id"], state=record["state"], stop_requested=record["stop_requested"],
                  stop_confirmed=record["stop_confirmed"], result_json=json.dumps(record, ensure_ascii=False, allow_nan=False))
    if include_error:
        result.update(error_code=record["error_code"], error_message=record["error_message"])
    return result


@provider.mcp("robonix/service/visual_action/evaluate")
def evaluate_mcp(request: Evaluate_Request) -> Evaluate_Response:
    return Evaluate_Response(**evaluation(request))


@provider.grpc("robonix/service/visual_action/evaluate")
def evaluate_grpc(request):
    return visual_action_pb2.Evaluate_Response(**evaluation(request))


@provider.mcp("robonix/service/visual_action/run_step")
def run_step_mcp(request: RunStep_Request) -> RunStep_Response:
    result = service().start(request)
    return RunStep_Response(run_id=result["run_id"], state=result["state"])


@provider.grpc("robonix/service/visual_action/run_step")
def run_step_grpc(request):
    result = service().start(request)
    return visual_action_pb2.RunStep_Response(run_id=result["run_id"], state=result["state"])


@provider.mcp("robonix/service/visual_action/status")
def status_mcp(request: Status_Request) -> Status_Response:
    return Status_Response(**task_status(service().status(request.run_id)))


@provider.grpc("robonix/service/visual_action/status")
def status_grpc(request):
    return visual_action_pb2.Status_Response(**task_status(service().status(request.run_id)))


@provider.mcp("robonix/service/visual_action/cancel")
def cancel_mcp(request: Cancel_Request) -> Cancel_Response:
    return Cancel_Response(**task_status(service().cancel(request.run_id), include_error=False))


@provider.grpc("robonix/service/visual_action/cancel")
def cancel_grpc(request):
    return visual_action_pb2.Cancel_Response(**task_status(service().cancel(request.run_id), include_error=False))


@provider.on_init
def init(config):
    global runtime
    settings = Settings.model_validate(config)
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    runtime = Runtime(settings, Robot(settings, provider.id))
    return Ok()


@provider.on_shutdown
def shutdown():
    if runtime is not None:
        runtime.close()
    return Ok()


@provider.on_deactivate
def deactivate():
    if runtime is not None and runtime.active_run is not None:
        runtime.cancel(runtime.active_run)
    return Ok()


if __name__ == "__main__":
    provider.run()
