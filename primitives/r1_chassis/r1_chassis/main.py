import json
import os

import grpc
from google.protobuf.empty_pb2 import Empty
from robonix_api import Ok, Primitive

import chassis_pb2
import std_msgs_pb2
from chassis_mcp import ExecuteMoveCommand_Request, ExecuteMoveCommand_Response
from std_msgs_mcp import String
from .controller import ChassisController

provider = Primitive(id=os.environ.get("RBNX_INSTANCE_NAME", "r1_chassis"),
                     namespace="robonix/primitive/chassis")
controller = None


@provider.mcp("robonix/primitive/chassis/move")
def move_mcp(request: ExecuteMoveCommand_Request) -> ExecuteMoveCommand_Response:
    """Run one official timed R1 move. Forward linear_x=0.3 and backward linear_x=-0.4 for duration_sec=5 have been checked. Requires FSM 811. Returns the measured joint change and the raw SDK code. Distance is an open-loop approximation."""
    if controller is None:
        raise RuntimeError("the walking primitive is not initialized")
    result = controller.move(request.command, lambda: True)
    return ExecuteMoveCommand_Response(status=String(data=json.dumps(result, ensure_ascii=False)))


@provider.grpc("robonix/primitive/chassis/move")
def move(request, context):
    if controller is None:
        context.abort(grpc.StatusCode.FAILED_PRECONDITION, "the walking primitive is not initialized")
    try:
        result = controller.move(request.command, context.is_active)
    except ValueError as error:
        context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
    except RuntimeError as error:
        context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(error))
    return chassis_pb2.ExecuteMoveCommand_Response(
        status=std_msgs_pb2.String(data=json.dumps(result, ensure_ascii=False)))


@provider.grpc("robonix/primitive/chassis/twist_in")
def twist_in(requests, context):
    if controller is None:
        context.abort(grpc.StatusCode.FAILED_PRECONDITION, "the walking primitive is not initialized")
    try:
        controller.twist(requests, context.is_active)
    except ValueError as error:
        context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
    except RuntimeError as error:
        context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(error))
    return Empty()


@provider.on_init
def init(config):
    global controller
    controller = ChassisController(config)
    return Ok()


@provider.on_shutdown
def shutdown():
    if controller is not None:
        controller.close()
    return Ok()


@provider.on_deactivate
def deactivate():
    if controller is not None:
        controller.stop()
    return Ok()


if __name__ == "__main__":
    provider.run()
