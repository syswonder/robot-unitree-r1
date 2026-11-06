specVersion: 1
description: R1 双臂关节控制配置。
properties:
  network_interface:
    type: string
    default: eth10
    description: 机器人 DDS 网络接口，必须已经存在并处于可用状态。
  max_acceleration_rad_s2:
    type: number
    default: 0.5
    description: 五次关节轨迹的加速度幅度上限，单位 rad/s²，必须为有限正数；属于部署参数。
  max_jerk_rad_s3:
    type: number
    default: 2.0
    description: 五次关节轨迹的 jerk 幅度上限，单位 rad/s³，必须为有限正数；属于部署参数。
