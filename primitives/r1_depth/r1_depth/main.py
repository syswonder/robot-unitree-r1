#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read-only Unitree R1 binocular depth snapshot provider.

The R1 EDU head stereo module outputs a 544x448 Y16 depth image. The
Unitree ``depth_client`` on the NX receives it from 192.168.123.161:5000 and
writes it into the v4l2loopback device ``/dev/video-dep`` (``/dev/video102``).
This provider reads that device, converts the latest frame to an 8-bit
grayscale PNG (near = bright), and exposes it as
``robonix/primitive/camera/depth_snapshot`` over MCP.

The stereo module sends depth in network byte order; the raw frame is decoded
as big-endian uint16 millimetres. Decoding it as native little-endian produces
implausible 1-90 mm values on the NX.

The depth stream must be enabled separately:

1. In the Unitree app: Settings -> Service Status, turn off ``video_hub`` and
   enable ``Stereo patch PC1`` (it is not auto-start by default).
2. On the NX: ``sudo unitree_depth_start`` (or run the depth client directly;
   the ``unitree`` user is in the ``video`` group).

Until those steps are done, the device opens but returns no frames; the MCP
tool reports that condition instead of fabricating depth.
"""

from __future__ import annotations

import io
import math
import os
from pathlib import Path
import threading
import time

import grpc
import numpy as np
from PIL import Image as PillowImage

from robonix_api import Err, Ok, Primitive
from r1_sensor_geometry import camera_info, load_geometry

r1_depth = Primitive(id=os.environ.get("RBNX_INSTANCE_NAME", "r1_depth"), namespace="robonix/primitive/camera")

import builtin_interfaces_mcp  # noqa: E402
import std_msgs_mcp  # noqa: E402
from sensor_msgs_mcp import Image  # noqa: E402
import sensor_msgs_pb2


_settings = {
    "device": "/dev/video-dep",
    "width": 544,
    "height": 448,
    "fps": 10.0,
    "stale_after_s": 2.0,
    "min_depth_mm": 200.0,
    "max_depth_mm": 10000.0,
    "frame_id": "r1_depth_camera_optical_frame",
    "byte_order": "big",
    "calibration_file": "",
    "extrinsics_file": "",
}
_lock = threading.Lock()
_changed = threading.Condition(_lock)
_stop = threading.Event()
_fd: int | None = None
_latest: dict[str, object] = {"frame": None, "ts": None, "stamp_ns": 0}
_last_error = ""
_worker = None
_calibration = None
_mount = None


def _header(stamp_ns) -> "std_msgs_mcp.Header":
    return std_msgs_mcp.Header(
        stamp=builtin_interfaces_mcp.Time(
            sec=stamp_ns // 1_000_000_000, nanosec=stamp_ns % 1_000_000_000
        ),
        frame_id=_settings["frame_id"],
    )


def _png_gray(gray: np.ndarray) -> bytes:
    output = io.BytesIO()
    PillowImage.fromarray(gray).save(output, format="PNG")
    return output.getvalue()


def _reader() -> None:
    """Keep the newest depth frame; tolerate a device that is not streaming."""
    global _fd, _last_error
    frame_size = int(_settings["width"]) * int(_settings["height"]) * 2
    period = 1.0 / float(_settings["fps"])
    while not _stop.is_set():
        fd = None
        try:
            fd = os.open(str(_settings["device"]), os.O_RDWR | os.O_NONBLOCK)
            with _lock:
                _fd = fd
            _last_error = ""
            print(f"[r1_depth] opened {_settings['device']}", flush=True)
            while not _stop.is_set():
                try:
                    data = os.read(fd, frame_size)
                except BlockingIOError:
                    _stop.wait(period)
                    continue
                except OSError as exc:
                    _last_error = f"depth read failed: {exc}"
                    print(f"[r1_depth] {_last_error}", flush=True)
                    break
                if len(data) != frame_size:
                    _stop.wait(period)
                    continue
                dtype = ">u2" if _settings["byte_order"] == "big" else "<u2"
                frame = np.frombuffer(data, dtype=dtype).reshape(
                    int(_settings["height"]), int(_settings["width"])
                ).copy()
                with _changed:
                    _latest["frame"] = frame
                    _latest["ts"] = time.monotonic()
                    _latest["stamp_ns"] = time.time_ns()
                    _changed.notify_all()
        except FileNotFoundError:
            _last_error = f"{_settings['device']} does not exist"
        except OSError as exc:
            _last_error = f"cannot open {_settings['device']}: {exc}"
        finally:
            if fd is not None:
                os.close(fd)
                with _lock:
                    _fd = None
        if _last_error:
            print(f"[r1_depth] {_last_error}; retrying", flush=True)
        _stop.wait(1.0)


def _current_frame():
    with _lock:
        frame = _latest["frame"]
        ts = _latest["ts"]
        error = _last_error
        stamp_ns = _latest["stamp_ns"]
    if frame is None or ts is None:
        raise RuntimeError(
            "no depth frame; enable Stereo patch PC1 in the Unitree app and "
            f"run unitree_depth_start ({error or 'no frame received'})"
        )
    age = time.monotonic() - float(ts)
    if age > float(_settings["stale_after_s"]):
        raise RuntimeError(f"depth frame is stale ({age:.1f}s old)")
    return frame, stamp_ns


def _depth_message(frame, stamp_ns):
    # Official depth values are millimetres. The standard float depth is metres, and invalid device values become NaN.
    meters = frame.astype("<f4") * np.float32(0.001)
    meters[(frame == 0) | (frame == 65535)] = np.nan
    message = sensor_msgs_pb2.Image(width=frame.shape[1], height=frame.shape[0],
                                    encoding="32FC1", is_bigendian=0,
                                    step=frame.shape[1] * 4, data=meters.tobytes())
    message.header.frame_id = _settings["frame_id"]
    message.header.stamp.sec = stamp_ns // 1_000_000_000
    message.header.stamp.nanosec = stamp_ns % 1_000_000_000
    return message


@r1_depth.grpc("robonix/primitive/camera/depth")
def depth(_request, context):
    previous = 0
    while context.is_active() and not _stop.is_set():
        with _changed:
            _changed.wait_for(lambda: _latest["stamp_ns"] != previous or _stop.is_set(), timeout=0.1)
        if not context.is_active() or _stop.is_set():
            return
        try:
            frame, stamp_ns = _current_frame()
        except RuntimeError as error:
            context.abort(grpc.StatusCode.UNAVAILABLE, str(error))
        if stamp_ns == previous:
            continue
        previous = stamp_ns
        yield _depth_message(frame, stamp_ns)


@r1_depth.mcp("robonix/primitive/camera/depth_snapshot")
def depth_snapshot(_msg: "std_msgs_mcp.Empty") -> "Image":
    """Capture one depth frame from the R1 binocular camera as a PNG image."""
    frame, stamp_ns = _current_frame()

    lo = float(_settings["min_depth_mm"])
    hi = float(_settings["max_depth_mm"])
    valid = (frame >= lo) & (frame <= hi)
    if not valid.any():
        raise RuntimeError("depth frame contains no pixels in the display range")
    normalized = np.zeros(frame.shape, dtype=np.uint8)
    # The display range applies only to the snapshot. The metric depth stream keeps every valid measurement.
    scaled = np.clip((frame[valid].astype(np.float32) - lo) / (hi - lo), 0.0, 1.0)
    normalized[valid] = (255.0 - scaled * 255.0).astype(np.uint8)
    png = _png_gray(normalized)
    return Image(
        header=_header(stamp_ns),
        height=int(frame.shape[0]),
        width=int(frame.shape[1]),
        encoding="png",
        is_bigendian=0,
        step=int(frame.shape[1]),
        data=png,
    )


@r1_depth.grpc("robonix/primitive/camera/intrinsics")
def intrinsics(_request, context):
    previous = 0
    while context.is_active() and not _stop.is_set():
        with _changed:
            _changed.wait_for(lambda: _latest["stamp_ns"] != previous or _stop.is_set(), timeout=0.1)
        if not context.is_active() or _stop.is_set():
            return
        try:
            frame, stamp_ns = _current_frame()
        except RuntimeError as error:
            context.abort(grpc.StatusCode.UNAVAILABLE, str(error))
        if stamp_ns == previous:
            continue
        try:
            message = camera_info(_calibration, int(frame.shape[1]), int(frame.shape[0]), _settings["frame_id"], stamp_ns)
        except ValueError as error:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(error))
        yield message
        previous = stamp_ns
        _stop.wait(1.0)


@r1_depth.grpc("robonix/primitive/camera/extrinsics")
def extrinsics(_request, context):
    previous = None
    while context.is_active() and not _stop.is_set():
        mount = _mount
        if mount is None:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, "no measured extrinsics_file is configured")
        if mount is not previous:
            yield mount.message()
            previous = mount
        _stop.wait(0.2)


@r1_depth.on_init
def init(cfg: dict):
    """Start the depth reader; it keeps retrying until the stream is enabled."""
    global _worker, _calibration, _mount
    device = str(cfg.get("device", "/dev/video-dep")).strip()
    try:
        width = int(cfg.get("width", 544))
        height = int(cfg.get("height", 448))
        fps = float(cfg.get("fps", 10.0))
        stale_after_s = float(cfg.get("stale_after_s", 2.0))
        min_depth_mm = float(cfg.get("min_depth_mm", 200.0))
        max_depth_mm = float(cfg.get("max_depth_mm", 10000.0))
    except (TypeError, ValueError):
        return Err(
            "width, height, fps, stale_after_s, min_depth_mm and max_depth_mm "
            "must be numbers"
        )
    if not device:
        return Err("device must be non-empty")
    if width <= 0 or height <= 0:
        return Err("width and height must be positive")
    if not all(math.isfinite(v) and v > 0 for v in (fps, stale_after_s)):
        return Err("fps and stale_after_s must be positive")
    if not math.isfinite(min_depth_mm) or not math.isfinite(max_depth_mm) or min_depth_mm < 0 or max_depth_mm <= min_depth_mm:
        return Err("min_depth_mm/max_depth_mm must define a positive range")
    frame_id = str(cfg.get("frame_id", "r1_depth_camera_optical_frame")).strip()
    byte_order = str(cfg.get("byte_order", "big"))
    if not frame_id or byte_order not in ("big", "little"):
        raise ValueError("frame_id must not be empty, and byte_order must be big or little")
    _calibration, _mount = load_geometry(cfg, Path(__file__).resolve().parents[3], frame_id, width, height)

    _settings.update(
        {
            "device": device,
            "width": width,
            "height": height,
            "fps": fps,
            "stale_after_s": stale_after_s,
            "min_depth_mm": min_depth_mm,
            "max_depth_mm": max_depth_mm,
            "frame_id": frame_id,
            "byte_order": byte_order,
            "calibration_file": str(cfg.get("calibration_file", "")),
            "extrinsics_file": str(cfg.get("extrinsics_file", "")),
        }
    )
    _stop.clear()
    with _lock:
        _latest.update(frame=None, ts=None, stamp_ns=0)
    _worker = threading.Thread(target=_reader, name="r1-depth-reader", daemon=True)
    _worker.start()

    # Wait briefly for the first frame so the first web-client snapshot after
    # a stack restart does not race the reader thread. Absence of a frame is
    # not fatal: the provider keeps retrying and reports the condition.
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        with _lock:
            if _latest["ts"] is not None:
                break
        time.sleep(0.05)
    print(
        f"[r1_depth] initialized device={device} {width}x{height} fps={fps}",
        flush=True,
    )
    return Ok()


@r1_depth.on_shutdown
def shutdown():
    """Stop the reader and close the V4L2 device; no robot state changes."""
    global _worker
    _stop.set()
    with _changed:
        _changed.notify_all()
    if _worker is not None:
        _worker.join(timeout=3)
        if _worker.is_alive():
            raise RuntimeError("the depth reader thread did not exit")
        _worker = None
    return Ok()


if __name__ == "__main__":
    r1_depth.run()
