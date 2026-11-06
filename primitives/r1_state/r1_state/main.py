#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read-only Unitree R1 state provider.

Reads the R1 high-level and low-level DDS streams:

  * ``rt/lowstate``     — IMU, mode_machine, 35 motor states
  * ``rt/lf/bmsstate``  — BMS SOC/SOH, pack voltages, temperatures
  * LocoClient 7001/7002 — FSM id and FSM mode (read-only calls)

It exposes one gRPC capability, ``robonix/primitive/r1/get_state``, whose
response is a JSON snapshot. It never calls SetFsmId, SetVelocity, LowCmd or
any other control API.

The provider can run on the PC (external compute, interface ``enp131s0``) or
natively on the R1 (interface ``eth10``); the deployment manifest supplies the
interface. It only subscribes and calls read-only getters.
"""

from __future__ import annotations

import json
import threading
import time
import os
import math

from robonix_api import Err, Ok, Primitive

r1_state = Primitive(id=os.environ.get("RBNX_INSTANCE_NAME", "r1_state"), namespace="robonix/primitive/r1")

# Codegen output (rbnx-build/codegen/proto_gen) is put on PYTHONPATH by
# scripts/start.sh and by robonix_api.
import r1_state_pb2  # noqa: E402

from unitree_sdk2py.core.channel import (  # noqa: E402
    ChannelFactoryInitialize,
    ChannelSubscriber,
)
from unitree_sdk2py.idl.unitree_hg.msg.dds_ import BmsState_, LowState_  # noqa: E402
from unitree_sdk2py.r1.loco.r1_loco_client import LocoClient  # noqa: E402
from cyclonedds.internal import InvalidSample

from std_msgs_mcp import Empty, String  # noqa: E402


_lock = threading.Lock()
_client_lock = threading.Lock()
_settings = {"network_interface": "enp131s0", "stale_after_s": 2.0}
_latest: dict[str, object] = {
    "low": None,
    "bms": None,
    "low_ts": None,
    "bms_ts": None,
}
_subs: list[ChannelSubscriber] = []
_client: LocoClient | None = None
_stop = threading.Event()
_low_thread = None


def _floats(values) -> list[float]:
    return [float(v) for v in values]


def _ints(values) -> list[int]:
    return [int(v) for v in values]


def _on_low(msg: LowState_) -> None:
    """Copy the DDS sample into plain Python values immediately.

    CycloneDDS may reuse the sample object after the callback returns, so we
    must not keep ``msg`` itself.
    """
    motors = [
        {
            "index": i,
            "mode": int(m.mode),
            "q": float(m.q),
            "dq": float(m.dq),
            "ddq": float(m.ddq),
            "tau_est": float(m.tau_est),
            "temperature": _ints(m.temperature),
            "vol": float(m.vol),
            "motorstate": int(m.motorstate),
        }
        for i, m in enumerate(msg.motor_state)
    ]
    low = {
        "mode_pr": int(msg.mode_pr),
        "mode_machine": int(msg.mode_machine),
        "tick": int(msg.tick),
        "imu": {
            "quaternion": _floats(msg.imu_state.quaternion),
            "gyroscope": _floats(msg.imu_state.gyroscope),
            "accelerometer": _floats(msg.imu_state.accelerometer),
            "rpy": _floats(msg.imu_state.rpy),
            "temperature": int(msg.imu_state.temperature),
        },
        "motor_count": len(motors),
        "motors": motors,
    }
    with _lock:
        _latest["low"] = low
        _latest["low_ts"] = time.monotonic()


def _on_bms(msg: BmsState_) -> None:
    cell_vol = _ints(msg.cell_vol)
    bms = {
        "soc": int(msg.soc),
        "soh": int(msg.soh),
        "current": int(msg.current),
        "bmsvoltage": _ints(msg.bmsvoltage),
        "temperature": _ints(msg.temperature),
        "cycle": int(msg.cycle),
        "cell_vol_min": min(cell_vol) if cell_vol else None,
        "cell_vol_max": max(cell_vol) if cell_vol else None,
    }
    with _lock:
        _latest["bms"] = bms
        _latest["bms_ts"] = time.monotonic()


def _watch_low(subscriber):
    while not _stop.is_set():
        message = subscriber.Read(timeout=0.1)
        if message is not None and not isinstance(message, InvalidSample):
            _on_low(message)
        _stop.wait(0.01)


def _json_data(data: object) -> object:
    if isinstance(data, bytes):
        data = data.decode("utf-8", "replace")
    if not isinstance(data, str):
        return None
    try:
        return json.loads(data).get("data")
    except Exception:
        return None


def _fsm_snapshot() -> dict[str, object]:
    """Read FSM id/mode with the SDK's read-only RPC calls."""
    global _client
    if _client is None:
        return {"fsm_id": None, "fsm_mode": None, "error": "LocoClient not initialized"}
    with _client_lock:
        result: dict[str, object] = {"fsm_id": None, "fsm_mode": None}
        try:
            code, data = _client._Call(7001, "{}")
            result["fsm_id_code"] = int(code)
            result["fsm_id"] = _json_data(data)
        except Exception as exc:  # noqa: BLE001
            result["fsm_id_error"] = str(exc)
        try:
            code, data = _client._Call(7002, "{}")
            result["fsm_mode_code"] = int(code)
            result["fsm_mode"] = _json_data(data)
        except Exception as exc:  # noqa: BLE001
            result["fsm_mode_error"] = str(exc)
        return result


def _snapshot() -> dict[str, object]:
    now = time.monotonic()
    with _lock:
        low = _latest["low"]
        bms = _latest["bms"]
        low_ts = _latest["low_ts"]
        bms_ts = _latest["bms_ts"]
    stale_after = float(_settings["stale_after_s"])
    low_age = None if low_ts is None else now - float(low_ts)
    bms_age = None if bms_ts is None else now - float(bms_ts)
    stale = (
        low is None
        or bms is None
        or low_age is None
        or bms_age is None
        or low_age > stale_after
        or bms_age > stale_after
    )
    snapshot: dict[str, object] = {
        "schema": "r1_state.v1",
        "timestamp_ns": time.time_ns(),
        "network_interface": _settings["network_interface"],
        "stale": stale,
        "age_s": {"lowstate": low_age, "bmsstate": bms_age},
        "fsm": _fsm_snapshot(),
    }
    if isinstance(low, dict):
        snapshot["imu"] = low["imu"]
        snapshot["mode_pr"] = low["mode_pr"]
        snapshot["mode_machine"] = low["mode_machine"]
        snapshot["tick"] = low["tick"]
        snapshot["motor_count"] = low["motor_count"]
        snapshot["motors"] = low["motors"]
    else:
        snapshot["imu"] = None
        snapshot["motor_count"] = None
        snapshot["motors"] = None
    snapshot["battery"] = bms
    return snapshot


@r1_state.grpc("robonix/primitive/r1/get_state")
def get_state(_request) -> "r1_state_pb2.GetState_Response":
    """Return a read-only R1 FSM/IMU/BMS/motor snapshot as a JSON string."""
    return r1_state_pb2.GetState_Response(
        json=json.dumps(_snapshot(), separators=(",", ":"), ensure_ascii=False)
    )


@r1_state.mcp("robonix/primitive/r1/get_state")
def get_state_mcp(_msg: "Empty") -> "String":
    """Return the R1 FSM, IMU, BMS and motor state as a JSON string.

    This is the read-only MCP view of the same snapshot as the gRPC
    get_state capability. It never sends a motion or low-level command.
    """
    return String(
        data=json.dumps(_snapshot(), separators=(",", ":"), ensure_ascii=False)
    )


@r1_state.on_init
def init(cfg: dict):
    """Open the read-only DDS subscriptions and the LocoClient."""
    global _client, _subs, _settings, _low_thread
    interface = str(cfg.get("network_interface", "enp131s0")).strip()
    try:
        stale_after = float(cfg.get("stale_after_s", 2.0))
    except (TypeError, ValueError):
        return Err("stale_after_s must be a number")
    if not interface:
        return Err("network_interface must be non-empty")
    if not math.isfinite(stale_after) or stale_after <= 0:
        return Err("stale_after_s must be greater than zero")

    with _lock:
        for key in _latest:
            _latest[key] = None
    try:
        ChannelFactoryInitialize(0, interface)
        low_sub = ChannelSubscriber("rt/lowstate", LowState_)
        low_sub.Init()
        bms_sub = ChannelSubscriber("rt/lf/bmsstate", BmsState_)
        bms_sub.Init(_on_bms, 10)
        client = LocoClient()
        client.SetTimeout(5.0)
        client.Init()
        # The Python SDK registers 7001 (GET_FSM_ID) but not 7002
        # (GET_FSM_MODE); register the read-only getter explicitly.
        try:
            client._RegistApi(7002, 0)
        except Exception:  # noqa: BLE001
            pass
        _client = client
        _subs = [low_sub, bms_sub]
        _settings = {
            "network_interface": interface,
            "stale_after_s": stale_after,
        }
    except Exception as exc:  # noqa: BLE001
        return Err(f"R1 DDS initialization failed: {exc}")

    _stop.clear()
    _low_thread = threading.Thread(target=_watch_low, args=(low_sub,),
                                   name="r1-state-feedback", daemon=True)
    _low_thread.start()

    # Give the robot a short window to publish the first samples. The provider
    # still starts and reports stale=True if the robot is off.
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        with _lock:
            if _latest["low"] is not None and _latest["bms"] is not None:
                break
        time.sleep(0.05)
    print(
        f"[r1_state] initialized interface={interface} "
        f"stale_after_s={stale_after}",
        flush=True,
    )
    return Ok()


@r1_state.on_shutdown
def shutdown():
    """Close DDS subscribers; no control state is changed."""
    global _subs, _client, _low_thread
    _stop.set()
    if _low_thread is not None:
        _low_thread.join()
        _low_thread = None
    for sub in _subs:
        sub.Close()
    _subs = []
    _client = None
    return Ok()


if __name__ == "__main__":
    r1_state.run()
