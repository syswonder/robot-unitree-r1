import json
import math
import threading
import time
from contextlib import contextmanager

import grpc
from google.protobuf.empty_pb2 import Empty
from google.protobuf.json_format import MessageToDict
from PIL import Image
from robonix_api import ATLAS

import chassis_pb2
import geometry_msgs_pb2
import robonix_contracts_pb2_grpc as services
import r1_state_pb2

from .dataset import archive_rgb
from .models import Action


class Robot:
    def __init__(self, settings, consumer_id):
        self.settings = settings
        self.consumer_id = consumer_id
        self.lock = threading.Lock()
        self.active_call = None
        self.last_execution = {"stop_requested": False, "stop_confirmed": False}

    @contextmanager
    def connect(self, provider_id, contract):
        with ATLAS.connect_capability(consumer_id=self.consumer_id, provider_id=provider_id,
                                      contract_id=contract, transport="grpc") as connection:
            with grpc.insecure_channel(connection.endpoint.removeprefix("http://")) as channel:
                yield channel

    def state(self):
        with self.connect(self.settings.state_provider_id, "robonix/primitive/r1/get_state") as channel:
            response = services.RobonixPrimitiveR1GetStateStub(channel).GetState(r1_state_pb2.GetState_Request(), timeout=2)
            return json.loads(response.json)

    def first(self, provider_id, contract, stub_class, method):
        with self.connect(provider_id, contract) as channel:
            stream = getattr(stub_class(channel), method)(Empty(), timeout=self.settings.capture_timeout_s)
            try:
                return next(stream)
            finally:
                stream.cancel()

    def capture(self, instruction, scene_id):
        rgb = self.first(self.settings.camera_provider_id, "robonix/primitive/camera/rgb",
                         services.RobonixPrimitiveCameraRgbStub, "Rgb")
        received = time.monotonic_ns()
        source_stamp = rgb.header.stamp.sec * 1_000_000_000 + rgb.header.stamp.nanosec
        if rgb.encoding != "rgb8" or rgb.step < rgb.width * 3 or len(rgb.data) != rgb.step * rgb.height:
            raise ValueError("RGB encoding or size is invalid")
        if not 0 <= time.time_ns() - source_stamp <= 2_000_000_000:
            raise RuntimeError("OBSERVATION_STALE: the camera stamp is invalid or older than two seconds")
        image = Image.frombytes("RGB", (rgb.width, rgb.height), rgb.data, "raw", "RGB", rgb.step)
        info = self.first(self.settings.camera_provider_id, "robonix/primitive/camera/intrinsics",
                          services.RobonixPrimitiveCameraIntrinsicsStub, "Intrinsics")
        depth = None
        if self.settings.capture_depth:
            message = self.first(self.settings.depth_provider_id, "robonix/primitive/camera/depth",
                                 services.RobonixPrimitiveCameraDepthStub, "Depth")
            depth = (message.data, {"encoding": message.encoding, "width": message.width, "height": message.height,
                                    "step": message.step, "is_bigendian": message.is_bigendian,
                                    "header": MessageToDict(message.header, preserving_proto_field_name=True),
                                    "registered_to_rgb": False})
        return archive_rgb(self.settings.data_dir + "/samples", image, scene_id, instruction, self.state(),
                           MessageToDict(info, preserving_proto_field_name=True), source_stamp, received, depth)

    @staticmethod
    def validate_state(state):
        if state["stale"] or state["age_s"]["lowstate"] is None or state["age_s"]["lowstate"] > 0.5:
            raise RuntimeError("FEEDBACK_STALE: robot feedback has timed out")
        if state["fsm"]["fsm_id_code"] != 0 or state["fsm"]["fsm_id"] != 811:
            raise RuntimeError("MODE_NOT_READY: motion requires official FSM 811")
        if len(state["motors"]) < 10 or any(not math.isfinite(state["motors"][index]["q"]) for index in (0, 3, 6, 9)):
            raise RuntimeError("FEEDBACK_STALE: leg joint feedback is invalid")

    def stop(self):
        with self.lock:
            call = self.active_call
        if call is not None:
            call.cancel()
        with self.connect(self.settings.chassis_provider_id, "robonix/primitive/chassis/move") as channel:
            result = services.RobonixPrimitiveChassisMoveStub(channel).ExecuteMoveCommand(
                chassis_pb2.ExecuteMoveCommand_Request(command=chassis_pb2.MoveCommand()), timeout=2)
        value = json.loads(result.status.data)
        if value["status"] != "stopped":
            raise RuntimeError("STOP_UNCONFIRMED: the zero-velocity interface did not confirm the stop")
        return value

    def execute(self, action, cancelled):
        self.last_execution = {"stop_requested": False, "stop_confirmed": False, "physical_motion_confirmed": None}
        self.validate_state(self.state())
        if action == Action.FORWARD:
            linear, angular, duration = self.settings.forward_speed, 0, self.settings.forward_duration_s
        elif action in (Action.TURN_LEFT, Action.TURN_RIGHT) and self.settings.turning_verified:
            linear, angular, duration = 0, self.settings.turn_speed * (1 if action == Action.TURN_LEFT else -1), self.settings.turn_duration_s
        else:
            raise ValueError("the motion action is not accepted yet, or it is invalid")
        result = {"sent_commands": [], "feedback": [], "stop_requested": False, "stop_confirmed": False,
                  "physical_motion_confirmed": None, "native_return_codes": None}
        self.last_execution = result
        observer_done = threading.Event()
        monitor_error = []
        latest = {"received": time.monotonic(), "state": self.state()}
        result["feedback"].append(latest["state"])

        def observe():
            try:
                while not observer_done.wait(0.2):
                    state = self.state()
                    self.validate_state(state)
                    latest.update(received=time.monotonic(), state=state)
                    result["feedback"].append(state)
            except (RuntimeError, ValueError, grpc.RpcError) as error:
                monitor_error.append(error)

        observer = threading.Thread(target=observe, name="jev-feedback", daemon=True)
        observer.start()
        started = time.monotonic()

        def commands():
            period = 1 / self.settings.control_rate_hz
            next_tick = started
            while time.monotonic() - started < duration:
                if cancelled.is_set():
                    return
                if monitor_error:
                    raise monitor_error[0]
                if time.monotonic() - latest["received"] > 0.6:
                    raise RuntimeError("FEEDBACK_STALE: motion monitoring exceeded its valid period")
                self.validate_state(latest["state"])
                message = geometry_msgs_pb2.Twist()
                message.linear.x, message.angular.z = linear, angular
                result["sent_commands"].append({"elapsed_s": time.monotonic() - started, "linear_x": linear, "angular_z": angular})
                yield message
                next_tick += period
                if next_tick < time.monotonic():
                    next_tick = time.monotonic() + period
                cancelled.wait(max(0, next_tick - time.monotonic()))
            if not cancelled.is_set():
                yield geometry_msgs_pb2.Twist()

        try:
            with self.connect(self.settings.chassis_provider_id, "robonix/primitive/chassis/twist_in") as channel:
                if cancelled.is_set():
                    raise RuntimeError("the task was cancelled")
                call = services.RobonixPrimitiveChassisTwistInStub(channel).TwistIn.future(commands(), timeout=duration + 3)
                with self.lock:
                    self.active_call = call
                call.result()
                if monitor_error:
                    raise monitor_error[0]
                result["stream_status"] = "OK"
                if not cancelled.is_set():
                    result["joint_motion_rad"] = max(
                        max(state["motors"][index]["q"] for state in result["feedback"]) -
                        min(state["motors"][index]["q"] for state in result["feedback"])
                        for index in (0, 3, 6, 9))
                    if result["joint_motion_rad"] < 0.1:
                        raise RuntimeError("EXECUTION_FAILED: no leg motion response was confirmed")
                    result["motion_observed"] = True
        finally:
            with self.lock:
                self.active_call = None
            observer_done.set()
            observer.join(timeout=3)
            result["stop_requested"] = True
            result["stop_response"] = self.stop()
            result["stop_confirmed"] = True
            result["elapsed_s"] = time.monotonic() - started
        return result
