import json
import math
import threading
import time
from collections import deque

from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_
from unitree_sdk2py.r1.loco.r1_loco_client import LocoClient


def finite(value, name):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} 必须是有限数值")
    return value


def settings(config):
    values = {}
    for name, default in (("linear_speed_m_s", 0.3), ("backward_speed_m_s", 0.4),
                          ("angular_speed_rad_s", 0.3),
                          ("max_linear_speed_m_s", 0.4), ("max_angular_speed_rad_s", 0.5),
                          ("default_duration_s", 5.0), ("max_duration_s", 10.0),
                          ("command_timeout_s", 0.3)):
        values[name] = finite(config.get(name, default), name)
        if values[name] <= 0:
            raise ValueError(f"{name} 必须为正数")
    if values["linear_speed_m_s"] > values["max_linear_speed_m_s"]:
        raise ValueError("linear_speed_m_s 超过部署速度限制")
    if values["backward_speed_m_s"] > values["max_linear_speed_m_s"]:
        raise ValueError("backward_speed_m_s 超过部署速度限制")
    if values["angular_speed_rad_s"] > values["max_angular_speed_rad_s"]:
        raise ValueError("angular_speed_rad_s 超过部署角速度限制")
    if values["default_duration_s"] > values["max_duration_s"]:
        raise ValueError("default_duration_s 超过 max_duration_s")
    if values["command_timeout_s"] > 1.0:
        raise ValueError("command_timeout_s 必须不超过官方默认有效时间 1 秒")
    return values


def validate_velocity(velocity, config):
    vx, vy, omega = [finite(value, "velocity") for value in velocity]
    if math.hypot(vx, vy) > config["max_linear_speed_m_s"]:
        raise ValueError("平移速度超过 max_linear_speed_m_s")
    if abs(omega) > config["max_angular_speed_rad_s"]:
        raise ValueError("旋转速度超过 max_angular_speed_rad_s")
    return vx, vy, omega


def plan_command(command, config):
    names = ("forward_m", "rotate_deg", "duration_sec", "linear_x", "linear_y",
             "linear_z", "angular_x", "angular_y", "angular_z")
    values = {name: finite(getattr(command, name), name) for name in names}
    if values["duration_sec"] < 0:
        raise ValueError("duration_sec 必须大于或等于零")
    if values["forward_m"]:
        speed = config["linear_speed_m_s"] if values["forward_m"] > 0 else config["backward_speed_m_s"]
        velocity = (math.copysign(speed, values["forward_m"]), 0, 0)
        duration = abs(values["forward_m"]) / speed
        mode = "forward_m"
    elif values["rotate_deg"]:
        velocity = (0, 0, math.copysign(config["angular_speed_rad_s"], values["rotate_deg"]))
        duration = abs(math.radians(values["rotate_deg"])) / config["angular_speed_rad_s"]
        mode = "rotate_deg"
    else:
        if any(values[name] for name in ("linear_z", "angular_x", "angular_y")):
            raise ValueError("R1 行走仅支持 linear_x、linear_y 和 angular_z")
        velocity = (values["linear_x"], values["linear_y"], values["angular_z"])
        duration = values["duration_sec"] or config["default_duration_s"]
        mode = "velocity"
    if duration > config["max_duration_s"]:
        raise ValueError("指令持续时间超过 max_duration_s")
    return validate_velocity(velocity, config), duration, mode


class ChassisController:
    def __init__(self, config):
        self.config = settings(config)
        self.motion_lock = threading.Lock()
        self.io_lock = threading.Lock()
        self.cancel = threading.Event()
        self.closed = False
        self.feedback_condition = threading.Condition()
        self.joint_samples = deque(maxlen=10000)
        ChannelFactoryInitialize(0, str(config.get("network_interface", "eth10")))
        self.client = LocoClient()
        self.client.Init()
        self.client.SetTimeout(2.0)
        self.fsm()
        self.state_subscriber = ChannelSubscriber("rt/lowstate", LowState_)
        self.state_subscriber.Init()
        self.feedback_stopping = threading.Event()
        self.feedback_thread = threading.Thread(target=self._monitor_state, daemon=True)
        self.feedback_thread.start()

    def _monitor_state(self):
        while not self.feedback_stopping.is_set():
            message = self.state_subscriber.Read(timeout=0.2)
            if message is not None:
                self._observe_state(message)
            self.feedback_stopping.wait(0.05)

    def _observe_state(self, message):
        with self.feedback_condition:
            self.joint_samples.append((time.monotonic(),
                tuple(message.motor_state[index].q for index in range(12))))
            self.feedback_condition.notify_all()

    def feedback(self, began=None):
        with self.feedback_condition:
            if not self.feedback_condition.wait_for(lambda: bool(self.joint_samples), timeout=2):
                raise RuntimeError("未收到腿部关节反馈")
            if time.monotonic() - self.joint_samples[-1][0] > 0.5:
                raise RuntimeError("腿部关节反馈已经超时")
            samples = ([self.joint_samples[-1][1]] if began is None else
                       [values for received, values in self.joint_samples if received >= began])
        if not samples or not all(math.isfinite(value) for values in samples for value in values):
            raise RuntimeError("腿部关节反馈无效")
        return samples

    def fsm(self):
        code, data = self.client._Call(7001, "{}")
        if code != 0:
            raise RuntimeError(f"R1 GetFsmId 查询失败：{code}")
        return int(json.loads(data)["data"])

    def _set_velocity(self, velocity, duration):
        code = self.client.SetVelocity(*velocity, duration=duration)
        # 本机 ai_sport 1.0.2.154 在实际执行速度和停止指令时返回 127。
        if code not in (0, 127):
            raise RuntimeError(f"R1 SetVelocity 调用失败：{code}")
        return code

    def send(self, velocity, duration, active):
        with self.io_lock:
            if self.closed or self.cancel.is_set() or not active():
                raise RuntimeError("行走指令已取消或原语已经关闭")
            if any(velocity):
                self.feedback()
                mode = self.fsm()
                if mode != 811:
                    raise RuntimeError(f"当前 FSM {mode}，行走需要通过官方遥控器或 App 进入走跑运控 811")
            return self._set_velocity(velocity, duration)

    def stop(self):
        with self.io_lock:
            self.cancel.set()
            return self._set_velocity((0, 0, 0), self.config["command_timeout_s"])

    def move(self, command, active):
        velocity, duration, mode = plan_command(command, self.config)
        if self.closed:
            raise RuntimeError("行走原语已经关闭")
        if not any(velocity):
            code = self.stop()
            return {"status": "stopped", "mode": mode, "velocity": list(velocity),
                    "duration_sec": 0.0, "native_return_codes": [code]}
        if not self.motion_lock.acquire(blocking=False):
            raise RuntimeError("行走原语正在处理其他运动输入")
        began = time.monotonic()
        codes = set()
        try:
            self.cancel.clear()
            codes.add(self.send(velocity, duration, active))
            while True:
                if self.cancel.is_set() or not active():
                    raise RuntimeError("行走指令已取消")
                self.feedback()
                if self.fsm() != 811:
                    raise RuntimeError("行走期间官方 FSM 已离开 811")
                remaining = duration - (time.monotonic() - began)
                if remaining <= 0:
                    break
                self.cancel.wait(min(remaining, 0.1))
            samples = self.feedback(began)
            joint_motion = max(max(values[index] for values in samples)
                               - min(values[index] for values in samples)
                               for index in (0, 3, 6, 9))
            if joint_motion < 0.1:
                raise RuntimeError(f"未确认腿部运动：髋部和膝部最大角度变化 {joint_motion:.4f} rad；"
                                   f"SetVelocity 返回码 {sorted(codes)}")
            result = {"status": "done", "mode": mode, "velocity": list(velocity),
                      "duration_sec": duration, "elapsed_sec": time.monotonic() - began,
                      "open_loop": True, "motion_observed": True,
                      "joint_motion_rad": joint_motion}
        finally:
            try:
                codes.add(self.stop())
            finally:
                self.motion_lock.release()
        result["native_return_codes"] = sorted(codes)
        return result

    def twist(self, requests, active):
        if not self.motion_lock.acquire(blocking=False):
            raise RuntimeError("行走原语正在处理其他运动输入")
        try:
            self.cancel.clear()
            for request in requests:
                if any(finite(value, "Twist") for value in
                       (request.linear.z, request.angular.x, request.angular.y)):
                    raise ValueError("R1 行走仅支持 linear.x、linear.y 和 angular.z")
                velocity = validate_velocity((request.linear.x, request.linear.y, request.angular.z), self.config)
                # 每条速度输入只在官方控制器中短时生效，输入中断后自动归零。
                self.send(velocity, self.config["command_timeout_s"], active)
        finally:
            try:
                self.stop()
            finally:
                self.motion_lock.release()

    def close(self):
        try:
            with self.io_lock:
                self.closed = True
                self.cancel.set()
                self._set_velocity((0, 0, 0), self.config["command_timeout_s"])
        finally:
            self.feedback_stopping.set()
            self.feedback_thread.join()
            self.state_subscriber.Close()
