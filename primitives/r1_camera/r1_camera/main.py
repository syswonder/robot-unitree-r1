#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read-only Unitree R1 RGB camera snapshot provider.

Exposes ``robonix/primitive/camera/snapshot`` as an MCP tool. Two sources are
supported:

* ``videohub`` — the original Unitree ``VideoClient`` (videohub API 1001).
  This is the default and requires the robot's ``video_hub`` service.
* ``stereo_udp`` — the R1 EDU stereo module's H.264 image stream on UDP
  (port 5001 by default). Use this when ``video_hub`` is disabled so that the
  stereo/depth service can run. GStreamer decodes the stream and the provider
  keeps the latest JPEG frame.

Neither path sends a motion command.
"""

from __future__ import annotations

import io
import math
import os
from pathlib import Path
import subprocess
import threading
import time

import av
import grpc
from PIL import Image as PillowImage
from robonix_api import Err, Ok, Primitive
from r1_sensor_geometry import camera_info, load_geometry

r1_camera = Primitive(id=os.environ.get("RBNX_INSTANCE_NAME", "r1_camera"), namespace="robonix/primitive/camera")

import builtin_interfaces_mcp  # noqa: E402
import std_msgs_mcp  # noqa: E402
from sensor_msgs_mcp import Image  # noqa: E402
import sensor_msgs_pb2

from unitree_sdk2py.core.channel import ChannelFactoryInitialize  # noqa: E402
from unitree_sdk2py.go2.video.video_client import VideoClient  # noqa: E402


_settings = {
    "source": "videohub",
    "network_interface": "eth10",
    "timeout_s": 3.0,
    "udp_port": 5001,
    "rotate": "clockwise",
    "stale_after_s": 2.0,
    "frame_id": "r1_front_camera_optical_frame",
    "calibration_file": "",
    "extrinsics_file": "",
}
_lock = threading.Lock()
_changed = threading.Condition(_lock)
_stop = threading.Event()
_client: VideoClient | None = None
_proc: subprocess.Popen | None = None
_latest_jpeg: bytes | None = None
_latest_ts: float | None = None
_latest_stamp_ns = 0
_last_error = ""
_calibration = None
_mount = None
_worker = None


def _header(stamp_ns) -> "std_msgs_mcp.Header":
    return std_msgs_mcp.Header(
        stamp=builtin_interfaces_mcp.Time(
            sec=stamp_ns // 1_000_000_000, nanosec=stamp_ns % 1_000_000_000
        ),
        frame_id=_settings["frame_id"],
    )


def _jpeg_size(jpeg: bytes) -> tuple[int, int]:
    with PillowImage.open(io.BytesIO(jpeg), formats=("JPEG",)) as image:
        return image.size


def _gst_pipeline(port: int, rotate: str) -> list[str]:
    pipeline = [
        "gst-launch-1.0",
        "-q",
        "udpsrc",
        f"port={port}",
        "caps=application/x-rtp,media=video,clock-rate=90000,"
        "encoding-name=H264,payload=96",
        "!",
        "rtph264depay",
        "!",
        "avdec_h264",
        "!",
        "videoconvert",
    ]
    if rotate in ("clockwise", "counterclockwise", "rotate-180"):
        pipeline.extend(["!", "videoflip", f"method={rotate}"])
    pipeline.extend(["!", "jpegenc", "quality=85", "!", "fdsink", "fd=1"])
    return pipeline


def _read_jpegs(stream) -> None:
    global _latest_jpeg, _latest_ts, _latest_stamp_ns
    # FFmpeg splits MJPEG frames and Pillow decodes the image.
    with av.open(stream, format="mjpeg", buffer_size=4096,
                 options={"probesize": "32", "analyzeduration": "0"}) as container:
        for packet in container.demux(video=0):
            if _stop.is_set():
                return
            if packet.size:
                with _changed:
                    _latest_jpeg = bytes(packet)
                    _latest_ts = time.monotonic()
                    _latest_stamp_ns = time.time_ns()
                    _changed.notify_all()


def _stereo_reader() -> None:
    """Keep the GStreamer stereo pipeline alive and cache the latest frame."""
    global _proc, _last_error
    if not _stop.is_set():
        proc = None
        try:
            proc = subprocess.Popen(
                _gst_pipeline(int(_settings["udp_port"]), str(_settings["rotate"])),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
            )
            with _lock:
                _proc = proc
            print(
                f"[r1_camera] stereo pipeline on udp:{_settings['udp_port']} "
                f"rotate={_settings['rotate']}",
                flush=True,
            )
            assert proc.stdout is not None
            _read_jpegs(proc.stdout)
        except (OSError, av.FFmpegError) as exc:
            if _stop.is_set():
                return
            _last_error = f"stereo pipeline failed: {exc}"
            raise
        finally:
            if proc is not None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
            with _lock:
                _proc = None


def _current_frame():
    if _settings["source"] == "videohub":
        with _lock:
            if _client is None:
                raise RuntimeError("r1_camera is not initialized")
            code, data = _client.GetImageSample()
        if code != 0:
            raise RuntimeError(f"videohub GetImageSample returned {code}")
        return bytes(data), time.monotonic(), time.time_ns()
    with _lock:
        sample = _latest_jpeg, _latest_ts, _latest_stamp_ns
        error = _last_error
    if sample[0] is None or sample[1] is None:
        raise RuntimeError(f"no RGB data yet; enable Stereo patch PC1; {error}")
    if time.monotonic() - sample[1] > _settings["stale_after_s"]:
        raise RuntimeError("RGB data has timed out")
    return sample


def _proto_header(message, stamp_ns):
    message.header.frame_id = _settings["frame_id"]
    message.header.stamp.sec = stamp_ns // 1_000_000_000
    message.header.stamp.nanosec = stamp_ns % 1_000_000_000


def _next_frame(previous, context):
    if _settings["source"] == "stereo_udp":
        with _changed:
            _changed.wait_for(lambda: _latest_stamp_ns != previous or _stop.is_set(), timeout=0.1)
    if not context.is_active() or _stop.is_set():
        return None
    try:
        sample = _current_frame()
    except RuntimeError as error:
        context.abort(grpc.StatusCode.UNAVAILABLE, str(error))
    return sample


@r1_camera.grpc("robonix/primitive/camera/rgb")
def rgb(_request, context):
    previous = 0
    while context.is_active() and not _stop.is_set():
        sample = _next_frame(previous, context)
        if sample is None:
            return
        jpeg, _, stamp_ns = sample
        if stamp_ns == previous:
            continue
        previous = stamp_ns
        yield _rgb_message(jpeg, stamp_ns)


def _rgb_message(jpeg, stamp_ns):
    with PillowImage.open(io.BytesIO(jpeg), formats=("JPEG",)) as image:
        pixels = image.convert("RGB")
        message = sensor_msgs_pb2.Image(width=pixels.width, height=pixels.height,
                                        encoding="rgb8", is_bigendian=0,
                                        step=pixels.width * 3, data=pixels.tobytes())
    _proto_header(message, stamp_ns)
    return message


def _camera_info(width, height, stamp_ns):
    return camera_info(_calibration, width, height, _settings["frame_id"], stamp_ns)


@r1_camera.grpc("robonix/primitive/camera/intrinsics")
def intrinsics(_request, context):
    previous = 0
    while context.is_active() and not _stop.is_set():
        sample = _next_frame(previous, context)
        if sample is None:
            return
        jpeg, _, stamp_ns = sample
        if stamp_ns == previous:
            _stop.wait(0.1)
            continue
        width, height = _jpeg_size(jpeg)
        try:
            message = _camera_info(width, height, stamp_ns)
        except ValueError as error:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(error))
        yield message
        previous = stamp_ns
        _stop.wait(1.0)


@r1_camera.grpc("robonix/primitive/camera/extrinsics")
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


@r1_camera.mcp("robonix/primitive/camera/snapshot")
def snapshot(_msg: "std_msgs_mcp.Empty") -> "Image":
    """Capture one RGB frame from the R1 front camera as a JPEG image."""
    jpeg, _, stamp_ns = _current_frame()
    width, height = _jpeg_size(jpeg)
    return Image(
        header=_header(stamp_ns),
        height=height,
        width=width,
        encoding="jpeg",
        is_bigendian=0,
        step=len(jpeg),
        data=jpeg,
    )


@r1_camera.on_init
def init(cfg: dict):
    """Initialize the configured RGB source."""
    global _client, _last_error, _calibration, _mount, _worker, _latest_jpeg, _latest_ts, _latest_stamp_ns
    source = str(cfg.get("source", "videohub")).strip().lower()
    try:
        timeout_s = float(cfg.get("timeout_s", 3.0))
        udp_port = int(cfg.get("udp_port", 5001))
        stale_after_s = float(cfg.get("stale_after_s", 2.0))
    except (TypeError, ValueError):
        return Err("timeout_s, udp_port and stale_after_s must be numbers")
    rotate = str(cfg.get("rotate", "clockwise")).strip().lower()
    interface = str(cfg.get("network_interface", "eth10")).strip()
    if source not in ("videohub", "stereo_udp"):
        return Err("source must be 'videohub' or 'stereo_udp'")
    if not all(math.isfinite(v) and v > 0 for v in (timeout_s, stale_after_s)) or not 1 <= udp_port <= 65535:
        return Err("timeout_s, udp_port and stale_after_s must be positive")
    if rotate not in ("none", "clockwise", "counterclockwise", "rotate-180"):
        return Err("rotate must be none, clockwise, counterclockwise or rotate-180")
    frame_id = str(cfg.get("frame_id", "r1_front_camera_optical_frame")).strip()
    if not frame_id:
        raise ValueError("frame_id must not be empty")
    calibration_file = str(cfg.get("calibration_file", "")).strip()
    extrinsics_file = str(cfg.get("extrinsics_file", "")).strip()
    _calibration, _mount = load_geometry(cfg, Path(__file__).resolve().parents[3], frame_id)

    _settings.update(
        {
            "source": source,
            "network_interface": interface,
            "timeout_s": timeout_s,
            "udp_port": udp_port,
            "rotate": rotate,
            "stale_after_s": stale_after_s,
            "frame_id": frame_id,
            "calibration_file": calibration_file,
            "extrinsics_file": extrinsics_file,
        }
    )
    _stop.clear()
    _last_error = ""
    with _lock:
        _latest_jpeg, _latest_ts, _latest_stamp_ns = None, None, 0

    if source == "stereo_udp":
        _worker = threading.Thread(target=_stereo_reader, name="r1-stereo-reader", daemon=True)
        _worker.start()
        print(
            f"[r1_camera] initialized source=stereo_udp udp_port={udp_port} "
            f"rotate={rotate}",
            flush=True,
        )
        return Ok()

    if not interface:
        return Err("network_interface must be non-empty")
    try:
        ChannelFactoryInitialize(0, interface)
        client = VideoClient()
        client.SetTimeout(timeout_s)
        client.Init()
    except Exception as exc:  # noqa: BLE001
        return Err(f"R1 videohub initialization failed: {exc}")

    with _lock:
        _client = client

    return Ok()


@r1_camera.on_shutdown
def shutdown():
    """Stop the stereo pipeline or drop the videohub client."""
    global _client, _proc, _worker
    _stop.set()
    with _lock:
        _client = None
        proc = _proc
        _proc = None
    if proc is not None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    with _changed:
        _changed.notify_all()
    if _worker is not None:
        _worker.join(timeout=3)
        if _worker.is_alive():
            raise RuntimeError("the RGB reader thread did not exit")
        _worker = None
    return Ok()


if __name__ == "__main__":
    r1_camera.run()
