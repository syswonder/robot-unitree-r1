specVersion: 1
description: R1 内置 IMU 只读标准数据流配置。
properties:
  network_interface:
    type: string
    default: eth10
    description: DDS 网络接口，必须存在；例如 R1 本机 eth10。
  frame_id:
    type: string
    default: imu_in_pelvis_link
    description: URDF 中实际 IMU frame，不得为空；角速度为 rad/s，加速度为 m/s²。
  stale_after_s:
    type: number
    default: 2.0
    description: 无有效样本时返回 UNAVAILABLE 的等待时间，单位秒，必须为有限正数。
