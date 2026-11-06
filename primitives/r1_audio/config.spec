specVersion: 1
description: R1 头部麦克风组播和 voice 播放服务配置；PCM 固定为 16 kHz、单声道、s16le。
properties:
  network_interface:
    type: string
    default: eth10
    description: 已配置 IPv4 的机器人网络接口，名称为 1 至 15 字节。影响 DDS 和组播加入；示例 eth10。
  multicast_group:
    type: string
    default: 239.168.123.161
    description: 真实头部麦克风的 IPv4 组播地址，必须属于组播范围；示例 239.168.123.161。
  port:
    type: integer
    default: 5555
    description: 麦克风 UDP 端口，范围 1 至 65535；示例 5555。
  sample_rate_hz:
    type: integer
    default: 16000
    description: PCM 采样率，单位 Hz，当前只接受 16000；不会进行重采样。
  chunk_bytes:
    type: integer
    default: 32000
    description: 每个麦克风 AudioChunk 的字节数，必须为正偶数；32000 对应 1 秒，3200 对应 0.1 秒。
  stale_after_s:
    type: number
    default: 3.0
    description: 麦克风连续没有 UDP 数据的超时秒数，必须为有限正数；超时结束本次流并返回 UNAVAILABLE，示例 3.0。
