from concurrent.futures import ThreadPoolExecutor
import math
import threading
import time


PERIOD = 0.01


def smooth_step(progress):
    value = min(1.0, max(0.0, progress))
    return (value ** 3 * (10.0 + value * (-15.0 + 6.0 * value)),
            30.0 * value ** 2 * (1.0 - value) ** 2)


def trajectory_duration(starts, targets, speeds, acceleration, jerk):
    return max(PERIOD, *(max(1.875 * abs(target - start) / speed,
                             math.sqrt((10.0 / math.sqrt(3.0)) * abs(target - start) / acceleration),
                             (60.0 * abs(target - start) / jerk) ** (1.0 / 3.0))
                          for start, target, speed in zip(starts, targets, speeds)))


def apply_trajectory(command, indices, starts, targets, elapsed, duration):
    ratio, derivative = smooth_step(elapsed / duration)
    for index, start, target in zip(indices, starts, targets):
        command.motor_cmd[index].q = start + (target - start) * ratio
        command.motor_cmd[index].dq = (target - start) * derivative / duration


def wait_tick(deadline):
    deadline += PERIOD
    now = time.monotonic()
    if deadline < now:
        deadline += (math.floor((now - deadline) / PERIOD) + 1) * PERIOD
    time.sleep(max(0.0, deadline - time.monotonic()))
    return deadline


class ArmMotion:
    def __init__(self, controller, publisher, command, active):
        self.controller = controller
        self.publisher = publisher
        self.command = command
        self.active = active
        self.positions = [motor.q for motor in command.motor_cmd]
        self.plan = None
        self.plan_lock = threading.Lock()
        self.finished = threading.Event()

    def __enter__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="r1_arm_publish")
        self.began = time.monotonic()
        self.future = self.executor.submit(self._run)
        return self

    def __exit__(self, *_errors):
        self.finished.set()
        try:
            self.future.result()
        finally:
            self.executor.shutdown(wait=True)

    def wait_until(self, deadline):
        while time.monotonic() < deadline:
            if self.future.done():
                self.future.result()
                raise RuntimeError("the arm publisher task ended early")
            if self.controller.stop.is_set() or not self.active():
                raise RuntimeError("the arm command was cancelled")
            self.controller.snapshot(moving=True)
            self.finished.wait(min(PERIOD, max(0.0, deadline - time.monotonic())))

    def target(self, indices, targets, speeds):
        starts = [self.positions[index] for index in indices]
        duration = trajectory_duration(starts, targets, speeds,
            self.controller.max_acceleration, self.controller.max_jerk)
        began = time.monotonic()
        with self.plan_lock:
            self.plan = (indices, starts, targets, began, duration)
        return began, duration

    def _publish(self):
        self.command.crc = self.controller.crc.Crc(self.command)
        if not self.publisher.Write(self.command):
            raise RuntimeError("arm_sdk DDS publish failed")

    def _run(self):
        deadline = self.began
        try:
            while not self.finished.is_set():
                if self.controller.stop.is_set() or not self.active():
                    raise RuntimeError("the arm command was cancelled")
                self.controller.snapshot(moving=True)
                now = time.monotonic()
                with self.plan_lock:
                    plan = self.plan
                if plan is not None:
                    indices, starts, targets, began, duration = plan
                    apply_trajectory(self.command, indices, starts, targets, now - began, duration)
                ratio, _ = smooth_step(now - self.began)
                self.command.mode_pr = round(100 * ratio)
                self._publish()
                deadline = wait_tick(deadline)
        finally:
            for motor in self.command.motor_cmd:
                motor.dq = 0.0
            weight = self.command.mode_pr
            began = time.monotonic()
            deadline = began
            while weight and time.monotonic() - began < 1.0:
                ratio, _ = smooth_step(time.monotonic() - began)
                self.command.mode_pr = round(weight * (1.0 - ratio))
                self._publish()
                deadline = wait_tick(deadline)
            self.controller._release_confirmed(self.publisher, self.command)
