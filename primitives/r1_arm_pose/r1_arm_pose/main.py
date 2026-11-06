import json
import math
import os
import threading
from contextlib import contextmanager

import grpc
from google.protobuf.empty_pb2 import Empty
from robonix_api import ATLAS, Ok, Primitive
from scipy.spatial.transform import Rotation

from .kinematics import ArmKinematics

provider = Primitive(id=os.environ.get("RBNX_INSTANCE_NAME", "r1_left_arm"), namespace="robonix/primitive/arm")

import geometry_msgs_pb2
import sensor_msgs_pb2
import r1_arm_pose_pb2
import robonix_contracts_pb2_grpc as services
from r1_arm_pose_mcp import GetEndPose_Request, GetEndPose_Response, MovePose_Request, MovePose_Response

model = None
joint_provider = "r1_arm"
speed = 0.05
stopping = threading.Event()
channels = set()
channel_lock = threading.Lock()


@contextmanager
def connect(leaf):
    with ATLAS.connect_capability(consumer_id=provider.id, provider_id=joint_provider,
                                  contract_id=f"robonix/primitive/arm/{leaf}", transport="grpc") as connection:
        with grpc.insecure_channel(connection.endpoint.removeprefix("http://")) as channel:
            with channel_lock:
                if stopping.is_set():
                    raise RuntimeError("机械臂位姿接口已关闭")
                channels.add(channel)
            try:
                yield channel
            finally:
                with channel_lock:
                    channels.discard(channel)


def positions(message):
    if len(message.name) != len(message.position) or len(set(message.name)) != len(message.name):
        raise ValueError("关节反馈的名称与位置长度不一致或名称重复")
    return dict(zip(message.name, message.position))


def pose_message(matrix):
    message = geometry_msgs_pb2.Pose()
    message.position.x, message.position.y, message.position.z = matrix[:3, 3]
    (message.orientation.x, message.orientation.y,
     message.orientation.z, message.orientation.w) = Rotation.from_matrix(matrix[:3, :3]).as_quat()
    return message


def read_positions():
    with connect("joint_states") as channel:
        stream = services.RobonixPrimitiveArmJointStatesStub(channel).JointStates(Empty(), timeout=3)
        try:
            return positions(next(stream))
        finally:
            stream.cancel()


def read_pose():
    message = pose_message(model.forward(read_positions()))
    return dict(frame_id=model.frame_id, tip_link=model.tip_link,
                position_m=[message.position.x, message.position.y, message.position.z],
                quaternion_xyzw=[message.orientation.x, message.orientation.y,
                                 message.orientation.z, message.orientation.w])


def execute_pose(target, velocity, context=None):
    if not math.isfinite(velocity) or velocity <= 0:
        raise ValueError("speed_rad_s 必须是有限正数")
    values, position_error, orientation_error = model.solve(
        [target.position.x, target.position.y, target.position.z],
        [target.orientation.x, target.orientation.y, target.orientation.z, target.orientation.w],
        read_positions())
    if stopping.is_set() or (context is not None and not context.is_active()):
        raise RuntimeError("机械臂位姿指令已取消")
    command = sensor_msgs_pb2.JointState(name=model.names, position=values, velocity=[velocity] * 5)
    with connect("joint_command") as channel:
        call = services.RobonixPrimitiveArmJointCommandStub(channel).JointCommand.future(iter([command]))
        if context is not None and not context.add_callback(call.cancel):
            call.cancel()
        call.result()
    return dict(frame_id=model.frame_id, tip_link=model.tip_link, joint_names=model.names,
                target_rad=values, ik_position_error_m=position_error,
                ik_orientation_error_rad=orientation_error)


@provider.grpc("robonix/primitive/arm/end_pose")
def end_pose(_request, context):
    with connect("joint_states") as channel:
        stream = services.RobonixPrimitiveArmJointStatesStub(channel).JointStates(Empty())
        if not context.add_callback(stream.cancel):
            stream.cancel()
        try:
            for message in stream:
                if stopping.is_set() or not context.is_active():
                    return
                yield pose_message(model.forward(positions(message)))
        except grpc.RpcError as error:
            context.abort(error.code(), error.details())
        finally:
            stream.cancel()


@provider.grpc("robonix/primitive/arm/pos_command")
def pos_command(requests, context):
    errors = []

    def commands():
        current = None
        for target in requests:
            if stopping.is_set() or not context.is_active():
                raise RuntimeError("机械臂位姿指令已取消")
            if current is None:
                current = read_positions()
            try:
                values, _, _ = model.solve(
                    [target.position.x, target.position.y, target.position.z],
                    [target.orientation.x, target.orientation.y, target.orientation.z, target.orientation.w],
                    current)
            except ValueError as error:
                errors.append(error)
                raise
            current.update(zip(model.names, values))
            yield sensor_msgs_pb2.JointState(name=model.names, position=values, velocity=[speed] * 5)

    with connect("joint_command") as channel:
        call = services.RobonixPrimitiveArmJointCommandStub(channel).JointCommand.future(commands())
        if not context.add_callback(call.cancel):
            call.cancel()
        try:
            call.result()
        except grpc.RpcError as error:
            if errors:
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(errors[0]))
            context.abort(error.code(), error.details())
    return Empty()


@provider.mcp("robonix/primitive/arm/get_end_pose")
def get_end_pose(_request: GetEndPose_Request) -> GetEndPose_Response:
    """读取腕部相对于 waist_yaw_link 的位姿，position 单位米，四元数顺序 x,y,z,w。"""
    return GetEndPose_Response(json=json.dumps(read_pose(), ensure_ascii=False))


@provider.grpc("robonix/primitive/arm/get_end_pose")
def get_end_pose_grpc(_request):
    return r1_arm_pose_pb2.GetEndPose_Response(json=json.dumps(read_pose(), ensure_ascii=False))


def move_request(request, context=None):
    target = geometry_msgs_pb2.Pose()
    target.position.x, target.position.y, target.position.z = request.x, request.y, request.z
    target.orientation.x, target.orientation.y = request.qx, request.qy
    target.orientation.z, target.orientation.w = request.qz, request.qw
    return execute_pose(target, request.speed_rad_s, context)


@provider.mcp("robonix/primitive/arm/move_pose")
def move_pose(request: MovePose_Request) -> MovePose_Response:
    """移动当前 provider 对应腕部至 waist_yaw_link 中的绝对位姿，需要 FSM 811（走跑运控）。"""
    return MovePose_Response(json=json.dumps(move_request(request), ensure_ascii=False))


@provider.grpc("robonix/primitive/arm/move_pose")
def move_pose_grpc(request, context):
    try:
        result = move_request(request, context)
    except ValueError as error:
        context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
    except grpc.RpcError as error:
        context.abort(error.code(), error.details())
    return r1_arm_pose_pb2.MovePose_Response(json=json.dumps(result, ensure_ascii=False))


@provider.on_init
def init(config):
    global model, joint_provider, speed
    model = ArmKinematics(str(config["side"]))
    joint_provider = str(config.get("joint_provider_id", "r1_arm"))
    speed = float(config.get("speed_rad_s", 0.05))
    if not joint_provider or not math.isfinite(speed) or speed <= 0:
        raise ValueError("joint_provider_id 必须非空，speed_rad_s 必须是有限正数")
    stopping.clear()
    return Ok()


@provider.on_shutdown
def shutdown():
    stopping.set()
    with channel_lock:
        active = list(channels)
    for channel in active:
        channel.close()
    return Ok()


if __name__ == "__main__":
    provider.run()
