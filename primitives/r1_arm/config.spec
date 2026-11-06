specVersion: 1
description: R1 dual-arm joint control settings.
properties:
  network_interface:
    type: string
    default: eth10
    description: Robot DDS network interface. It must already exist and be up.
  max_acceleration_rad_s2:
    type: number
    default: 0.5
    description: Acceleration magnitude limit of the quintic joint trajectory, in rad/s^2. Must be a finite positive deployment parameter.
  max_jerk_rad_s3:
    type: number
    default: 2.0
    description: Jerk magnitude limit of the quintic joint trajectory, in rad/s^3. Must be a finite positive deployment parameter.
