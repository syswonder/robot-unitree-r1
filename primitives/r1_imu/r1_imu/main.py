import math
import os
import threading
import time

import grpc
from robonix_api import Ok, Primitive

provider = Primitive(id=os.environ.get("RBNX_INSTANCE_NAME", "r1_imu"), namespace="robonix/primitive/imu")

import sensor_msgs_pb2
from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_

changed = threading.Condition()
stopping = threading.Event()
subscriber = None
latest = None
settings = {"frame_id": "imu_in_pelvis_link", "stale_after_s": 2.0}


def receive(message):
    global latest
    imu = message.imu_state
    sample = (time.monotonic(), time.time_ns(), tuple(float(v) for v in imu.quaternion),
              tuple(float(v) for v in imu.gyroscope), tuple(float(v) for v in imu.accelerometer))
    with changed:
        latest = sample
        changed.notify_all()


def to_message(sample):
    _, stamp_ns, quaternion, gyro, acceleration = sample
    if not all(math.isfinite(v) for values in (quaternion, gyro, acceleration) for v in values):
        raise ValueError("IMU 包含非有限数值")
    if sum(v * v for v in quaternion) == 0:
        raise ValueError("IMU 四元数无效")
    message = sensor_msgs_pb2.Imu()
    message.header.frame_id = settings["frame_id"]
    message.header.stamp.sec = stamp_ns // 1_000_000_000
    message.header.stamp.nanosec = stamp_ns % 1_000_000_000
    # Unitree 的 w,x,y,z 顺序转换为 ROS 的 x,y,z,w 字段。
    message.orientation.w, message.orientation.x, message.orientation.y, message.orientation.z = quaternion
    message.angular_velocity.x, message.angular_velocity.y, message.angular_velocity.z = gyro
    message.linear_acceleration.x, message.linear_acceleration.y, message.linear_acceleration.z = acceleration
    # 全零协方差表示设备未提供协方差，遵循 sensor_msgs/Imu 约定。
    message.orientation_covariance.extend([0.0] * 9)
    message.angular_velocity_covariance.extend([0.0] * 9)
    message.linear_acceleration_covariance.extend([0.0] * 9)
    return message


@provider.grpc("robonix/primitive/imu/imu")
def imu(_request, context):
    previous = None
    began = time.monotonic()
    while context.is_active() and not stopping.is_set():
        with changed:
            changed.wait_for(lambda: latest is not previous or stopping.is_set(), timeout=0.1)
            sample = latest
        if stopping.is_set():
            return
        now = time.monotonic()
        if sample is None:
            if now - began > settings["stale_after_s"]:
                context.abort(grpc.StatusCode.UNAVAILABLE, "尚未收到 R1 rt/lowstate IMU 数据")
            continue
        if now - sample[0] > settings["stale_after_s"]:
            context.abort(grpc.StatusCode.UNAVAILABLE, "R1 IMU 数据已超时")
        if sample is previous:
            continue
        previous = sample
        yield to_message(sample)


@provider.on_init
def init(config):
    global subscriber, latest
    interface = str(config.get("network_interface", "eth10")).strip()
    frame = str(config.get("frame_id", "imu_in_pelvis_link")).strip()
    stale = float(config.get("stale_after_s", 2.0))
    if not interface or not frame or not math.isfinite(stale) or stale <= 0:
        raise ValueError("网络接口和 frame_id 必须非空，stale_after_s 必须为有限正数")
    settings.update(frame_id=frame, stale_after_s=stale)
    with changed:
        latest = None
    stopping.clear()
    ChannelFactoryInitialize(0, interface)
    subscriber = ChannelSubscriber("rt/lowstate", LowState_)
    subscriber.Init(receive, 1)
    return Ok()


@provider.on_shutdown
def shutdown():
    global subscriber
    stopping.set()
    with changed:
        changed.notify_all()
    if subscriber is not None:
        subscriber.Close()
        subscriber = None
    return Ok()


if __name__ == "__main__":
    provider.run()
