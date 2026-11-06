specVersion: 1
description: R1 官方 SetVelocity 的部署速度与时间配置；速度超过部署限制时拒绝输入。
properties:
  network_interface:
    type: string
    default: eth10
    description: 机器人 DDS 网络接口，必须已经存在并可用，例如 eth10。
  linear_speed_m_s:
    type: number
    default: 0.3
    description: forward_m 为正时使用的前进速度幅度，单位 m/s，必须不超过 max_linear_speed_m_s。
  backward_speed_m_s:
    type: number
    default: 0.4
    description: forward_m 为负时使用的后退速度幅度，单位 m/s，必须不超过 max_linear_speed_m_s。
  angular_speed_rad_s:
    type: number
    default: 0.3
    description: rotate_deg 使用的正角速度，单位 rad/s，必须不超过 max_angular_speed_rad_s。
  max_linear_speed_m_s:
    type: number
    default: 0.4
    description: 部署允许的最大平移速度模长，单位 m/s，必须为有限正数。
  max_angular_speed_rad_s:
    type: number
    default: 0.5
    description: 部署允许的最大旋转速度绝对值，单位 rad/s，必须为有限正数。
  default_duration_s:
    type: number
    default: 5.0
    description: velocity 模式 duration_sec 为零时的持续时间，单位秒，必须不超过 max_duration_s。
  max_duration_s:
    type: number
    default: 10.0
    description: 单次 move 指令持续时间上限，单位秒，必须为有限正数。
  command_timeout_s:
    type: number
    default: 0.3
    description: Twist 和停止请求的官方指令有效时间，单位秒，范围 (0, 1]；速度流至少每个有效期更新一次。
