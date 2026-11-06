import json
import math
from pathlib import Path
import threading
import time
import xml.etree.ElementTree as ET
from contextlib import contextmanager

from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelPublisher, ChannelSubscriber
from unitree_sdk2py.idl.default import unitree_hg_msg_dds__LowCmd_
from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowCmd_, LowState_
from unitree_sdk2py.r1.loco.r1_loco_client import LocoClient
from unitree_sdk2py.utils.crc import CRC
from .motion import ArmMotion


JOINTS = {
    "left_shoulder_pitch_joint": 15,
    "left_shoulder_roll_joint": 16,
    "left_shoulder_yaw_joint": 17,
    "left_elbow_joint": 18,
    "left_wrist_roll_joint": 19,
    "right_shoulder_pitch_joint": 22,
    "right_shoulder_roll_joint": 23,
    "right_shoulder_yaw_joint": 24,
    "right_elbow_joint": 25,
    "right_wrist_roll_joint": 26,
}
# R1 ArmSdk 同时接管这十三个关节；腰部和头部保持接管前的位置。
CONTROLLED = tuple(JOINTS.values()) + (13, 29, 30)
KP = (50, 50, 40, 40, 30, 50, 50, 40, 40, 30, 50, 15, 15)
KD = (2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 3, 1, 1)
ROOT = Path(__file__).resolve().parents[3]
FSM_MODES = {0: "零力矩", 1: "阻尼", 4: "锁定站立", 811: "走跑运控"}


def finite(value, name):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} 必须是有限数值")
    return value


def make_command(low):
    command = unitree_hg_msg_dds__LowCmd_()
    command.mode_machine = low["mode_machine"]
    for joint, kp, kd in zip(CONTROLLED, KP, KD):
        command.motor_cmd[joint].mode = 1
        command.motor_cmd[joint].q = low["q"][joint]
        command.motor_cmd[joint].dq = 0.0
        command.motor_cmd[joint].tau = 0.0
        command.motor_cmd[joint].kp = kp
        command.motor_cmd[joint].kd = kd
    return command


class ArmController:
    def __init__(self, config):
        self.lock = threading.Lock()
        self.motion_lock = threading.Lock()
        self.stop = threading.Event()
        self.low = None
        self.low_stamp = 0.0
        self.arm_weight = 0
        self.arm_stamp = 0.0
        self.max_acceleration = finite(config.get("max_acceleration_rad_s2", 0.5), "max_acceleration_rad_s2")
        self.max_jerk = finite(config.get("max_jerk_rad_s3", 2.0), "max_jerk_rad_s3")
        if self.max_acceleration <= 0 or self.max_jerk <= 0:
            raise ValueError("机械臂加速度和 jerk 上限必须为正数")
        tree = ET.parse(ROOT / "urdf/R1.urdf")
        self.limits = {}
        self.velocity_limits = {}
        for name in JOINTS:
            limit = tree.find(f"./joint[@name='{name}']/limit")
            if limit is None:
                raise ValueError(f"URDF 缺少关节限位：{name}")
            self.limits[name] = (float(limit.attrib["lower"]), float(limit.attrib["upper"]))
            self.velocity_limits[name] = float(limit.attrib["velocity"])
        ChannelFactoryInitialize(0, str(config.get("network_interface", "eth10")))
        self.subscribers = []
        self.low_subscriber = ChannelSubscriber("rt/lowstate", LowState_)
        self.low_subscriber.Init()
        self.subscribers.append(self.low_subscriber)
        arm_subscriber = ChannelSubscriber("rt/arm_sdk", LowCmd_)
        arm_subscriber.Init(self._on_arm, 10)
        self.subscribers.append(arm_subscriber)
        self.feedback_stopping = threading.Event()
        self.feedback_thread = threading.Thread(target=self._monitor_low, daemon=True)
        self.feedback_thread.start()
        self.client = LocoClient()
        self.client.Init()
        self.client.SetTimeout(2.0)
        self.crc = CRC()

    def _monitor_low(self):
        while not self.feedback_stopping.is_set():
            message = self.low_subscriber.Read(timeout=0.1)
            if message is not None:
                self._on_low(message)
            self.feedback_stopping.wait(0.01)

    def _on_low(self, message):
        low = {
            "mode_machine": int(message.mode_machine),
            "q": [float(m.q) for m in message.motor_state],
            "dq": [float(m.dq) for m in message.motor_state],
            "effort": [float(m.tau_est) for m in message.motor_state],
            "mode": [int(m.mode) for m in message.motor_state],
            "error": [int(m.motorstate) for m in message.motor_state],
            "rpy": [float(v) for v in message.imu_state.rpy],
            "stamp_ns": time.time_ns(),
        }
        with self.lock:
            self.low, self.low_stamp = low, time.monotonic()

    def _on_arm(self, message):
        with self.lock:
            self.arm_weight, self.arm_stamp = int(message.mode_pr), time.monotonic()

    def snapshot(self, moving=False):
        with self.lock:
            now = time.monotonic()
            if self.low is None or now - self.low_stamp > 0.3:
                raise RuntimeError("R1 关节反馈已超过 0.3 秒未更新")
            low = self.low
            if moving:
                if any(low["mode"][i] == 0 or low["error"][i] != 0 for i in CONTROLLED):
                    raise RuntimeError("R1 上肢关节未就绪或存在错误")
                if any(not math.isfinite(low["q"][i]) for i in CONTROLLED):
                    raise RuntimeError("R1 关节位置包含无效数值")
            return low

    def fsm(self):
        code, data = self.client._Call(7001, "{}")
        if code != 0:
            raise RuntimeError(f"GetFsmId 查询失败：{code}")
        return int(json.loads(data)["data"])

    def move(self, name, target, speed=0.05, active=lambda: True):
        result = self.move_joints([name], [target], [speed], active)
        return dict(joint_name=name, start_rad=result["start_rad"][0],
                    target_rad=result["target_rad"][0], measured_rad=result["measured_rad"][0],
                    error_rad=result["error_rad"][0], actual_change_rad=result["actual_change_rad"][0],
                    duration_s=result["duration_s"])

    def _validate_targets(self, names, targets, speeds):
        names = list(names)
        if not names or len(set(names)) != len(names) or len(targets) != len(names):
            raise ValueError("name 必须非空且不能重复，position 长度必须与 name 相同")
        if speeds and len(speeds) != len(names):
            raise ValueError("velocity 必须为空或与 name 长度相同")
        targets = [finite(value, "position") for value in targets]
        speeds = [finite(value, "velocity") for value in speeds] if speeds else [0.05] * len(names)
        for name, target, speed in zip(names, targets, speeds):
            if name not in JOINTS:
                raise ValueError(f"未知机械臂关节：{name}")
            if not 0 < speed <= self.velocity_limits[name]:
                raise ValueError(f"速度必须在 (0, {self.velocity_limits[name]}] rad/s，依据官方 URDF")
            if not self.limits[name][0] <= target <= self.limits[name][1]:
                raise ValueError(f"目标超过 URDF 限位：{name}")
        return names, targets, speeds

    @contextmanager
    def _motion(self, active):
        if not self.motion_lock.acquire(blocking=False):
            raise RuntimeError("机械臂正在执行其他指令")
        publisher = None
        try:
            mode = self.fsm()
            if mode != 811:
                raise RuntimeError(f"当前 FSM {mode}（{FSM_MODES.get(mode, '未知模式')}），"
                                   "机械臂运动需要通过官方遥控器或 App 进入走跑运控 811")
            low = self.snapshot(moving=True)
            with self.lock:
                if self.arm_weight > 0 and time.monotonic() - self.arm_stamp < 0.5:
                    raise RuntimeError("rt/arm_sdk 已被其他控制程序占用")
            command = make_command(low)
            publisher = ChannelPublisher("rt/arm_sdk", LowCmd_)
            publisher.Init()
            with ArmMotion(self, publisher, command, active) as motion:
                motion.wait_until(motion.began + 1.0)
                yield motion
        finally:
            if publisher is not None:
                publisher.Close()
            self.motion_lock.release()

    def _execute(self, motion, names, targets, speeds):
        indices = [JOINTS[name] for name in names]
        low = self.snapshot(moving=True)
        starts = [low["q"][index] for index in indices]
        began, duration = motion.target(indices, targets, speeds)
        motion.wait_until(began + duration)
        deadline = began + duration + 0.5
        while True:
            low = self.snapshot(moving=True)
            measured = [low["q"][index] for index in indices]
            errors = [value - target for value, target in zip(measured, targets)]
            if all(abs(error) <= 0.02 for error in errors):
                break
            if time.monotonic() >= deadline:
                feedback = [dict(joint_name=name, start_rad=start, target_rad=target,
                                 measured_rad=value, error_rad=error, actual_change_rad=value - start)
                    for name, start, target, value, error in zip(names, starts, targets, measured, errors)]
                raise RuntimeError("关节未到达目标：" + json.dumps(feedback, ensure_ascii=False))
            motion.wait_until(min(deadline, time.monotonic() + 0.01))
        for index, target in zip(indices, targets):
            motion.positions[index] = target
        result = {"joint_name": names, "start_rad": starts, "target_rad": targets,
                  "measured_rad": measured, "error_rad": errors,
                  "actual_change_rad": [value - start for value, start in zip(measured, starts)],
                  "duration_s": time.monotonic() - began}
        print("[r1_arm] 到位反馈 " + json.dumps(result, ensure_ascii=False), flush=True)
        return result

    def move_joints(self, names, targets, speeds=(), active=lambda: True):
        values = self._validate_targets(names, targets, speeds)
        with self._motion(active) as motion:
            return self._execute(motion, *values)

    def move_commands(self, requests, active):
        requests = iter(requests)
        first = next(requests, None)
        if first is None:
            return
        values = self._validate_targets(*first)
        with self._motion(active) as motion:
            while True:
                self._execute(motion, *values)
                request = next(requests, None)
                if request is None:
                    break
                values = self._validate_targets(*request)

    def _release_confirmed(self, publisher, command):
        command.mode_pr = 0
        command.crc = self.crc.Crc(command)
        began = time.monotonic()
        while time.monotonic() - began < 1.0:
            if not publisher.Write(command):
                raise RuntimeError("arm_sdk 最终释放消息发布失败")
            time.sleep(0.02)
            with self.lock:
                confirmed = self.arm_weight == 0 and self.arm_stamp >= began
            if confirmed and time.monotonic() - began >= 0.1:
                print("[r1_arm] 已确认 arm_sdk 控制权重为 0", flush=True)
                return
        raise RuntimeError("arm_sdk 零权重消息未获得 DDS 订阅确认")

    def close(self):
        self.stop.set()
        with self.motion_lock:
            self.feedback_stopping.set()
            self.feedback_thread.join()
            for subscriber in self.subscribers:
                subscriber.Close()
            self.subscribers.clear()
