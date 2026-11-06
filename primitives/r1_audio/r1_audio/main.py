import ipaddress
import math
import os
import socket
import struct
import threading
import time
import uuid
import json

import fcntl
import grpc
from robonix_api import Ok, Primitive

r1_audio = Primitive(id=os.environ.get("RBNX_INSTANCE_NAME", "r1_audio"), namespace="robonix/primitive/audio")

import audio_pb2
from google.protobuf.empty_pb2 import Empty
from unitree_sdk2py.a2.audio.audio_client import AudioClient
from unitree_sdk2py.a2.audio.audio_api import ROBOT_API_ID_AUDIO_STOP_PLAY
from unitree_sdk2py.core.channel import ChannelFactoryInitialize

_settings = {}
_lock = threading.Lock()
_speaker_lock = threading.Lock()
_playing = threading.Event()
_stop = threading.Event()
_sockets = set()
_audio_client = None
_app_name = ""


def _integer(config, name, default):
    value = config.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} 必须为整数")
    return value


def _interface_ipv4(name):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        request = struct.pack("256s", name.encode())
        response = fcntl.ioctl(sock.fileno(), 0x8915, request)
        return socket.inet_ntoa(response[20:24])


def _open_multicast_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", _settings["port"]))
        membership = struct.pack("4s4s", socket.inet_aton(_settings["multicast_group"]),
                                 socket.inet_aton(_interface_ipv4(_settings["network_interface"])))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
        sock.settimeout(0.1)
        return sock
    except OSError:
        sock.close()
        raise


def _stop_playback(client):
    code, _ = client._Call(ROBOT_API_ID_AUDIO_STOP_PLAY, json.dumps({"app_name": _app_name}))
    if code != 0:
        raise RuntimeError(f"Unitree voice 停止播放失败：{code}")


@r1_audio.grpc("robonix/primitive/audio/mic")
def mic_stream(_request, context):
    if _stop.is_set() or _audio_client is None:
        context.abort(grpc.StatusCode.FAILED_PRECONDITION, "音频原语尚未初始化或已经关闭")
    sock = _open_multicast_socket()
    with _lock:
        if _stop.is_set():
            sock.close()
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, "音频原语已经关闭")
        _sockets.add(sock)
    sequence = 0
    last_packet = time.monotonic()
    pending = bytearray()
    try:
        while context.is_active() and not _stop.is_set():
            try:
                data = sock.recv(65536)
            except socket.timeout:
                if time.monotonic() - last_packet > _settings["stale_after_s"]:
                    context.abort(grpc.StatusCode.UNAVAILABLE, "R1 麦克风组播数据超时")
                continue
            except OSError as error:
                if _stop.is_set():
                    return
                context.abort(grpc.StatusCode.UNAVAILABLE, str(error))
            if not data:
                continue
            if len(data) % 2:
                context.abort(grpc.StatusCode.DATA_LOSS, "麦克风数据未包含完整的 s16le 采样")
            last_packet = time.monotonic()
            pending.extend(data)
            while (len(pending) >= _settings["chunk_bytes"]
                   and context.is_active() and not _stop.is_set()):
                payload = bytes(pending[:_settings["chunk_bytes"]])
                del pending[:_settings["chunk_bytes"]]
                yield audio_pb2.AudioChunk(timestamp_ns=time.time_ns(), data=payload,
                    sequence=sequence, duration_s=len(payload) / 32000.0)
                sequence += 1
    finally:
        with _lock:
            _sockets.discard(sock)
        sock.close()


@r1_audio.grpc("robonix/primitive/audio/speaker")
def speaker_stream(requests, context):
    client = _audio_client
    if client is None or _stop.is_set():
        context.abort(grpc.StatusCode.FAILED_PRECONDITION, "音频原语尚未初始化或已经关闭")
    if not _speaker_lock.acquire(blocking=False):
        context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, "扬声器正在播放其他数据流")
    stream_id = uuid.uuid4().hex
    playing = False
    playback_until = 0.0
    try:
        for chunk in requests:
            if _stop.is_set() or not context.is_active():
                break
            payload = bytes(chunk.data)
            if len(payload) % 2:
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, "播放数据必须包含完整的 s16le 采样")
            if not payload:
                continue
            playing = True
            _playing.set()
            code, _ = client.PlayStream(_app_name, stream_id, payload)
            if code != 0:
                context.abort(grpc.StatusCode.UNAVAILABLE, f"Unitree voice 播放失败：{code}")
            playback_until = max(playback_until, time.monotonic()) + len(payload) / 32000.0
        # 正常结束时等待已提交的 PCM 播放完成；取消和关闭及时结束等待。
        while context.is_active() and not _stop.is_set():
            remaining = playback_until - time.monotonic()
            if remaining <= 0:
                break
            _stop.wait(min(remaining, 0.05))
    finally:
        try:
            if playing:
                _stop_playback(client)
        finally:
            _playing.clear()
            _speaker_lock.release()
    return Empty()


@r1_audio.on_init
def init(config):
    global _audio_client, _app_name
    interface = str(config.get("network_interface", "eth10")).strip()
    group = str(config.get("multicast_group", "239.168.123.161"))
    port = _integer(config, "port", 5555)
    sample_rate = _integer(config, "sample_rate_hz", 16000)
    chunk_bytes = _integer(config, "chunk_bytes", 32000)
    stale = float(config.get("stale_after_s", 3.0))
    if not interface or len(interface.encode()) > 15:
        raise ValueError("network_interface 必须是非空且不超过 15 字节的 Linux 接口名称")
    address = ipaddress.IPv4Address(group)
    if not address.is_multicast or not 1 <= port <= 65535:
        raise ValueError("multicast_group 必须为 IPv4 组播地址，port 必须在 1 至 65535")
    if sample_rate != 16000:
        raise ValueError("官方 R1 音频流固定使用 16000 Hz、单声道 pcm_s16le")
    if chunk_bytes <= 0 or chunk_bytes % 2:
        raise ValueError("chunk_bytes 必须为正偶数")
    if not math.isfinite(stale) or stale <= 0:
        raise ValueError("stale_after_s 必须为有限正数")
    _interface_ipv4(interface)
    _settings.update(network_interface=interface, multicast_group=str(address), port=port,
                     sample_rate_hz=sample_rate, chunk_bytes=chunk_bytes, stale_after_s=stale)
    ChannelFactoryInitialize(0, interface)
    client = AudioClient()
    client.Init()
    client.SetTimeout(3.0)
    code, _ = client.GetVolume()
    if code != 0:
        raise RuntimeError(f"Unitree voice 服务查询失败：{code}")
    _app_name = f"robonix-{r1_audio.id}"
    _audio_client = client
    _stop.clear()
    return Ok()


@r1_audio.on_shutdown
def shutdown():
    global _audio_client
    _stop.set()
    with _lock:
        sockets = list(_sockets)
    for sock in sockets:
        sock.close()
    client = _audio_client
    if client is not None and _playing.is_set():
        _stop_playback(client)
    _audio_client = None
    return Ok()


if __name__ == "__main__":
    r1_audio.run()
