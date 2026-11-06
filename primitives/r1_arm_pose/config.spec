specVersion: 1
description: Settings for one R1 wrist pose interface.
properties:
  side:
    type: string
    required: true
    description: left or right. Selects the arm this instance controls.
  joint_provider_id:
    type: string
    default: r1_arm
    description: Provider that serves standard joint feedback and commands.
  speed_rad_s:
    type: number
    default: 0.05
    description: Joint speed limit used by the standard pos_command, in rad/s.
