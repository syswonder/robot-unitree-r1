# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import threading
import time
import math
import os

import grpc
from google.protobuf.empty_pb2 import Empty
from robonix_api import ATLAS, Err, Ok, Primitive
from robonix_api.atlas_types import LifecycleState, Transport

r1_health = Primitive(id=os.environ.get("RBNX_INSTANCE_NAME", "r1_health"), namespace="robonix/primitive/health")

import health_pb2  # noqa: E402
import robonix_contracts_pb2_grpc  # noqa: E402

from unitree_sdk2py.a2.audio.audio_client import AudioClient  # noqa: E402
from unitree_sdk2py.core.channel import (  # noqa: E402
    ChannelFactoryInitialize,
    ChannelSubscriber,
)
from unitree_sdk2py.idl.unitree_hg.msg.dds_ import BmsState_, LowState_  # noqa: E402
from cyclonedds.internal import InvalidSample


# Official R1JointIndex order (left leg, right leg, waist, left arm,
# right arm, head) and the corresponding lowstate.motor_state indices.
JOINT_NAMES = (
    "body/body/left_leg/left_hip_pitch",
    "body/body/left_leg/left_hip_roll",
    "body/body/left_leg/left_hip_yaw",
    "body/body/left_leg/left_knee",
    "body/body/left_leg/left_ankle_pitch",
    "body/body/left_leg/left_ankle_roll",
    "body/body/right_leg/right_hip_pitch",
    "body/body/right_leg/right_hip_roll",
    "body/body/right_leg/right_hip_yaw",
    "body/body/right_leg/right_knee",
    "body/body/right_leg/right_ankle_pitch",
    "body/body/right_leg/right_ankle_roll",
    "body/body/waist/waist_roll",
    "body/body/waist/waist_yaw",
    "body/body/waist/left_arm/left_shoulder_pitch",
    "body/body/waist/left_arm/left_shoulder_roll",
    "body/body/waist/left_arm/left_shoulder_yaw",
    "body/body/waist/left_arm/left_elbow",
    "body/body/waist/left_arm/left_wrist_roll",
    "body/body/waist/right_arm/right_shoulder_pitch",
    "body/body/waist/right_arm/right_shoulder_roll",
    "body/body/waist/right_arm/right_shoulder_yaw",
    "body/body/waist/right_arm/right_elbow",
    "body/body/waist/right_arm/right_wrist_roll",
    "body/body/waist/head/head_pitch",
    "body/body/waist/head/head_yaw",
)
JOINT_IDL_INDEX = (
    0, 1, 2, 3, 4, 5,
    6, 7, 8, 9, 10, 11,
    12, 13,
    15, 16, 17, 18, 19,
    22, 23, 24, 25, 26,
    29, 30,
)
JOINTS = tuple(zip(JOINT_NAMES, JOINT_IDL_INDEX, strict=True))

_settings = {
    "network_interface": "eth10",
    "interval_s": 0.5,
    "stale_after_s": 2.0,
}
_lock = threading.Lock()
_stop = threading.Event()
_subs: list[ChannelSubscriber] = []
_latest: dict[str, object] = {
    "low": None,
    "low_ts": None,
    "bms": None,
    "bms_ts": None,
    "bms_good_ts": None,
    "bms_valid": False,
}
_peripheral_online = {"front_camera": False, "depth_camera": False, "audio": False}
_peripheral_ts = 0.0
_peripheral_thread = None
_low_thread = None
_voice_client = None


def _ints(values) -> list[int]:
    return [int(v) for v in values]


def _on_low(msg: LowState_) -> None:
    """Copy the lowstate fields this provider needs into plain Python values."""
    motors = [
        {
            "mode": int(m.mode),
            "temperature": _ints(m.temperature),
            "vol": float(m.vol),
            "motorstate": int(m.motorstate),
        }
        for m in msg.motor_state
    ]
    low = {
        "imu_temperature": int(msg.imu_state.temperature),
        "motors": motors,
    }
    with _lock:
        _latest["low"] = low
        _latest["low_ts"] = time.monotonic()


def _on_bms(msg: BmsState_) -> None:
    bms = {
        "soc": int(msg.soc),
        "soh": int(msg.soh),
        "current": int(msg.current),
        "bmsvoltage": _ints(msg.bmsvoltage),
        "temperature": _ints(msg.temperature),
        "cycle": int(msg.cycle),
    }
    # The low-level firmware keeps publishing BmsState at ~10 Hz when the
    # battery data link is lost, but fills every field with zero.  A real
    # empty pack still has a positive pack voltage, so use voltage presence
    # as the validity test; SOC 0 with a valid pack must remain a real
    # low-battery reading.
    valid = any(v > 0 for v in bms["bmsvoltage"])
    now = time.monotonic()
    with _lock:
        _latest["bms_ts"] = now
        _latest["bms_valid"] = valid
        if valid:
            _latest["bms"] = bms
            _latest["bms_good_ts"] = now


def _watch_low(subscriber):
    while not _stop.is_set():
        message = subscriber.Read(timeout=0.1)
        if message is not None and not isinstance(message, InvalidSample):
            _on_low(message)
        _stop.wait(0.01)


def _reading(
    name: str,
    *,
    temp_c: float = -1.0,
    voltage: float = -1.0,
    current_a: float = -1.0,
    battery_percent: float = -1.0,
) -> "health_pb2.SensorReading":
    return health_pb2.SensorReading(
        name=name,
        temp_c=temp_c,
        voltage=voltage,
        current_a=current_a,
        battery_percent=battery_percent,
    )


def _control(name: str, value: float) -> "health_pb2.SensorReading":
    return _reading(name, current_a=value)


def _provider_active(provider_id, contracts):
    providers = ATLAS.query_primitives(id=provider_id)
    return any(provider.state == LifecycleState.ACTIVE
               and set(contracts) <= {cap.contract_id for cap in provider.capabilities}
               for provider in providers)


def _depth_available():
    contract = "robonix/primitive/camera/depth"
    if not _provider_active("r1_depth", [contract]):
        return False
    try:
        with ATLAS.connect_capability(consumer_id=r1_health.id, provider_id="r1_depth",
                                      contract_id=contract, transport=Transport.GRPC) as connection:
            endpoint = connection.endpoint.removeprefix("http://")
            with grpc.insecure_channel(endpoint) as channel:
                stream = robonix_contracts_pb2_grpc.RobonixPrimitiveCameraDepthStub(channel).Depth(
                    Empty(), timeout=1.0)
                try:
                    frame = next(stream, None)
                finally:
                    stream.cancel()
        if frame is None:
            return False
        stamp_ns = frame.header.stamp.sec * 1_000_000_000 + frame.header.stamp.nanosec
        return (frame.encoding == "32FC1" and frame.width > 0 and frame.height > 0
                and len(frame.data) == frame.step * frame.height
                and 0 <= (time.time_ns() - stamp_ns) / 1e9 <= _settings["stale_after_s"])
    except grpc.RpcError:
        return False


def _audio_available():
    contracts = ["robonix/primitive/audio/mic", "robonix/primitive/audio/speaker"]
    if not _provider_active("r1_audio", contracts):
        return False
    code, _ = _voice_client.GetVolume()
    return code == 0


def _watch_peripherals() -> None:
    """Query peripheral status separately. The depth check reads a real image. The audio check only queries volume."""
    global _peripheral_ts
    while not _stop.is_set():
        online = {
            "front_camera": _provider_active("r1_camera", ["robonix/primitive/camera/snapshot"]),
            "depth_camera": _depth_available(),
            "audio": _audio_available(),
        }
        with _lock:
            _peripheral_online.update(online)
            _peripheral_ts = time.monotonic()
        _stop.wait(2.0)


def _battery_values(bms: dict[str, object]) -> tuple[float, float, float, float]:
    """Return (soc, voltage_v, current_a, temperature_c) from one BMS frame.

    The R1 BMS reports pack voltages in millivolts and current in milliamps.
    Zero entries are unused channels (the R1 has two packs); ignore them.
    """
    soc = float(bms["soc"])
    voltages = [v for v in bms["bmsvoltage"] if v > 0]
    temps = [t for t in bms["temperature"] if t > 0]
    voltage_v = max(voltages) / 1000.0 if voltages else -1.0
    current_a = float(bms["current"]) / 1000.0
    temp_c = float(max(temps)) if temps else -1.0
    return soc, voltage_v, current_a, temp_c


def _build_state() -> "health_pb2.HealthState":
    now = time.monotonic()
    stale_after = float(_settings["stale_after_s"])
    with _lock:
        low = _latest["low"]
        low_ts = _latest["low_ts"]
        bms = _latest["bms"]
        bms_good_ts = _latest["bms_good_ts"]
        bms_valid = bool(_latest["bms_valid"])
        peripherals = dict(_peripheral_online)
        peripheral_fresh = now - _peripheral_ts <= 8.0

    low_fresh = low is not None and low_ts is not None and now - low_ts <= stale_after
    # Keep the last valid sample for a short grace period so a burst of
    # zero-filled frames does not make Vitals flap between 90% and 0%.
    bms_fresh = (
        bms is not None
        and bms_good_ts is not None
        and now - bms_good_ts <= stale_after
    )
    bms_current = bms_fresh and bms_valid

    readings = [
        _reading("body"),
        _control("body/online", 1.0),
        _control("body/error", 0.0),
    ]

    if low_fresh:
        readings.extend(
            [
                _reading("body/body/imu", temp_c=float(low["imu_temperature"])),
                _control("body/body/imu/online", 1.0),
                _control("body/body/imu/error", 0.0),
            ]
        )
        motors = low["motors"]
        for name, index in JOINTS:
            if index >= len(motors):
                readings.append(_control(f"{name}/communication_ok", 0.0))
                continue
            motor = motors[index]
            enabled = motor["mode"] != 0
            if enabled:
                temps = motor["temperature"]
                readings.append(
                    _reading(
                        name,
                        temp_c=float(temps[0]) if temps else -1.0,
                        voltage=float(motor["vol"]),
                    )
                )
                if len(temps) > 1 and temps[1] > 0:
                    readings.append(
                        _reading(f"{name}/driver_temp", temp_c=float(temps[1]))
                    )
            else:
                readings.append(_reading(name))
            readings.extend(
                [
                    _control(f"{name}/enabled", 1.0 if enabled else 0.0),
                    _control(
                        f"{name}/communication_ok",
                        1.0 if enabled and motor["motorstate"] == 0 else 0.0,
                    ),
                    _control(f"{name}/error", float(motor["motorstate"])),
                ]
            )
    else:
        readings.append(_control("body/body/imu/online", 0.0))
        for name, _index in JOINTS:
            readings.append(_control(f"{name}/communication_ok", 0.0))

    for name, online in peripherals.items():
        available = online and peripheral_fresh
        readings.extend([
            _control(f"body/body/{name}/online", float(available)),
            _control(f"body/body/{name}/communication_ok", float(available)),
            _control(f"body/body/{name}/error", 0.0 if available else 1.0),
        ])

    if bms_fresh:
        soc, voltage_v, current_a, temp_c = _battery_values(bms)
        readings.extend(
            [
                _reading(
                    "body/body/battery",
                    temp_c=temp_c,
                    voltage=voltage_v,
                    current_a=current_a,
                    battery_percent=soc,
                ),
                _control("body/body/battery/online", 1.0),
                _control("body/body/battery/error", 0.0 if bms_current else 1.0),
                _control(
                    "body/body/battery/communication_ok",
                    1.0 if bms_current else 0.0,
                ),
            ]
        )
        state_voltage = voltage_v
        charging = current_a > 0.0
    else:
        readings.extend(
            [
                _control("body/body/battery/online", 0.0),
                _control("body/body/battery/error", 1.0),
                _control("body/body/battery/communication_ok", 0.0),
            ]
        )
        state_voltage = -1.0
        charging = False

    return health_pb2.HealthState(
        voltage=state_voltage,
        charging=charging,
        remaining_s=-1,
        readings=readings,
    )


@r1_health.grpc("robonix/primitive/health/state")
def get_health_state(_request) -> "health_pb2.GetHealthState_Response":
    """Return one read-only R1 health frame."""
    return health_pb2.GetHealthState_Response(state=_build_state())


@r1_health.grpc("robonix/primitive/health/stream")
def stream_health_state(_request, context):
    """Yield R1 health frames until the consumer disconnects or shutdown."""
    while context.is_active() and not _stop.is_set():
        yield _build_state()
        _stop.wait(float(_settings["interval_s"]))


@r1_health.on_init
def init(cfg: dict):
    """Open read-only DDS subscriptions for lowstate and BMS."""
    global _subs, _peripheral_thread, _voice_client, _peripheral_ts, _low_thread
    interface = str(cfg.get("network_interface", "eth10")).strip()
    try:
        interval_s = float(cfg.get("interval_s", 0.5))
        stale_after_s = float(cfg.get("stale_after_s", 2.0))
    except (TypeError, ValueError):
        return Err("interval_s and stale_after_s must be numbers")
    if not interface:
        return Err("network_interface must be non-empty")
    if not math.isfinite(interval_s) or interval_s <= 0:
        return Err("interval_s must be greater than zero")
    if not math.isfinite(stale_after_s) or stale_after_s <= 0:
        return Err("stale_after_s must be greater than zero")

    with _lock:
        for key in _latest:
            _latest[key] = False if key == "bms_valid" else None
    try:
        ChannelFactoryInitialize(0, interface)
        low_sub = ChannelSubscriber("rt/lowstate", LowState_)
        low_sub.Init()
        bms_sub = ChannelSubscriber("rt/lf/bmsstate", BmsState_)
        bms_sub.Init(_on_bms, 10)
    except Exception as exc:  # noqa: BLE001
        return Err(f"R1 DDS initialization failed: {exc}")

    _subs = [low_sub, bms_sub]
    _voice_client = AudioClient()
    _voice_client.Init()
    _voice_client.SetTimeout(1.0)
    _settings.update(
        {
            "network_interface": interface,
            "interval_s": interval_s,
            "stale_after_s": stale_after_s,
        }
    )
    _stop.clear()
    _low_thread = threading.Thread(target=_watch_low, args=(low_sub,),
                                   name="r1-health-feedback", daemon=True)
    _low_thread.start()
    with _lock:
        _peripheral_online.update({name: False for name in _peripheral_online})
        _peripheral_ts = 0.0
    _peripheral_thread = threading.Thread(target=_watch_peripherals, name="r1-peripheral-watch", daemon=True)
    _peripheral_thread.start()

    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        with _lock:
            if _latest["low"] is not None and _latest["bms"] is not None:
                break
        time.sleep(0.05)
    print(
        f"[r1_health] initialized interface={interface} "
        f"interval_s={interval_s} stale_after_s={stale_after_s}",
        flush=True,
    )
    return Ok()


@r1_health.on_shutdown
def shutdown():
    """Stop the status thread and close the DDS subscriptions."""
    global _peripheral_thread, _voice_client, _low_thread
    _stop.set()
    if _low_thread is not None:
        _low_thread.join()
        _low_thread = None
    if _peripheral_thread is not None:
        _peripheral_thread.join()
        _peripheral_thread = None
    _voice_client = None
    for subscriber in _subs:
        subscriber.Close()
    _subs.clear()
    return Ok()


if __name__ == "__main__":
    r1_health.run()
