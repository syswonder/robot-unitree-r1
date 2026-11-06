import json
import asyncio
import threading
import os

import grpc
from robonix_api import Ok, Primitive

from .controller import ArmController, FSM_MODES, JOINTS

provider = Primitive(id=os.environ.get("RBNX_INSTANCE_NAME", "r1_arm"), namespace="robonix/primitive/arm")

import r1_arm_pb2
from r1_arm_mcp import (GetJointStates_Request, GetJointStates_Response,
                        MoveJoint_Request, MoveJoint_Response, MoveJoints_Request, MoveJoints_Response)
import sensor_msgs_pb2
from google.protobuf.empty_pb2 import Empty

controller = None
stopping = threading.Event()
stream_contexts = set()
stream_lock = threading.Lock()


def read_joints():
    if controller is None:
        raise RuntimeError("r1_arm is not initialized")
    low = controller.snapshot()
    mode = controller.fsm()
    return {"fsm_id": mode, "fsm_mode": FSM_MODES.get(mode, "unknown mode"),
            "motion_fsm_ids": [811],
            "position_rad": {name: low["q"][index] for name, index in JOINTS.items()},
            "limits_rad": controller.limits, "velocity_limits_rad_s": controller.velocity_limits}


@provider.mcp("robonix/primitive/arm/get_joint_states")
def get_joint_states(_request: GetJointStates_Request) -> GetJointStates_Response:
    """Read both arms' joint angles, limits and command limits."""
    return GetJointStates_Response(json=json.dumps(read_joints(), ensure_ascii=False))


@provider.grpc("robonix/primitive/arm/get_joint_states")
def get_joint_states_grpc(_request):
    return r1_arm_pb2.GetJointStates_Response(json=json.dumps(read_joints(), ensure_ascii=False))


def run_move(request, active=lambda: True):
    if controller is None:
        raise RuntimeError("r1_arm is not initialized")
    return controller.move(request.joint_name, request.target_rad,
                           request.speed_rad_s, active=active)


@provider.mcp("robonix/primitive/arm/move_joint")
async def move_joint(request: MoveJoint_Request) -> MoveJoint_Response:
    """Move one arm joint by URDF name. Requires FSM 811 (walk-run)."""
    cancelled = threading.Event()
    try:
        result = await asyncio.to_thread(run_move, request, lambda: not cancelled.is_set())
        return MoveJoint_Response(json=json.dumps(result, ensure_ascii=False))
    finally:
        cancelled.set()


@provider.grpc("robonix/primitive/arm/move_joint")
def move_joint_grpc(request, context):
    return r1_arm_pb2.MoveJoint_Response(
        json=json.dumps(run_move(request, context.is_active), ensure_ascii=False))


def run_move_joints(request, active=lambda: True):
    if controller is None:
        raise RuntimeError("r1_arm is not initialized")
    if len(request.speed_rad_s) != len(request.joint_names):
        raise ValueError("speed_rad_s must have the same length as joint_names")
    return controller.move_joints(request.joint_names, request.target_rad,
                                  request.speed_rad_s, active=active)


@provider.mcp("robonix/primitive/arm/move_joints")
async def move_joints(request: MoveJoints_Request) -> MoveJoints_Response:
    """Move several joints together in FSM 811. Three equal-length arrays are URDF names, target rad and speed limits in rad/s, and may include both arms."""
    cancelled = threading.Event()
    try:
        result = await asyncio.to_thread(run_move_joints, request, lambda: not cancelled.is_set())
        return MoveJoints_Response(json=json.dumps(result, ensure_ascii=False))
    finally:
        cancelled.set()


@provider.grpc("robonix/primitive/arm/move_joints")
def move_joints_grpc(request, context):
    try:
        result = run_move_joints(request, context.is_active)
    except ValueError as error:
        context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
    return r1_arm_pb2.MoveJoints_Response(json=json.dumps(result, ensure_ascii=False))


@provider.grpc("robonix/primitive/arm/joint_states")
def joint_states(_request, context):
    while context.is_active() and not stopping.is_set():
        if controller is None:
            raise RuntimeError("r1_arm is not initialized")
        try:
            low = controller.snapshot()
        except RuntimeError as error:
            context.abort(grpc.StatusCode.UNAVAILABLE, str(error))
        message = sensor_msgs_pb2.JointState(
            name=list(JOINTS),
            position=[low["q"][index] for index in JOINTS.values()],
            velocity=[low["dq"][index] for index in JOINTS.values()],
            effort=[low["effort"][index] for index in JOINTS.values()],
        )
        now = low["stamp_ns"]
        message.header.stamp.sec = now // 1_000_000_000
        message.header.stamp.nanosec = now % 1_000_000_000
        message.header.frame_id = "waist_yaw_link"
        yield message
        stopping.wait(0.05)


@provider.grpc("robonix/primitive/arm/joint_command")
def joint_command(requests, context):
    if controller is None:
        raise RuntimeError("r1_arm is not initialized")

    def commands():
        for request in requests:
            if request.effort:
                raise ValueError("joint_command does not accept effort")
            yield request.name, request.position, request.velocity

    with stream_lock:
        if stopping.is_set():
            context.abort(grpc.StatusCode.UNAVAILABLE, "the arm interface is shut down")
        stream_contexts.add(context)
    try:
        try:
            controller.move_commands(commands(), context.is_active)
        except ValueError as error:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
    finally:
        with stream_lock:
            stream_contexts.discard(context)
    return Empty()


@provider.on_init
def init(config):
    global controller
    controller = ArmController(config)
    stopping.clear()
    print("[r1_arm] subscribed to joint feedback; arm motion uses FSM 811", flush=True)
    return Ok()


@provider.on_shutdown
def shutdown():
    stopping.set()
    with stream_lock:
        for context in stream_contexts:
            context.cancel()
    if controller is not None:
        controller.close()
    return Ok()


if __name__ == "__main__":
    provider.run()
