specVersion: 1
description: R1 单臂腕部位姿接口配置。
properties:
  side:
    type: string
    required: true
    description: left 或 right，确定当前实例控制的机械臂。
  joint_provider_id:
    type: string
    default: r1_arm
    description: 提供标准关节反馈与指令的 provider。
  speed_rad_s:
    type: number
    default: 0.05
    description: 标准 pos_command 使用的关节速度上限，单位 rad/s。
