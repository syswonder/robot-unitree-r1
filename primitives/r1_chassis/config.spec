specVersion: 1
description: Deployment speed and time settings for official R1 SetVelocity. Input above a deployment limit is rejected.
properties:
  network_interface:
    type: string
    default: eth10
    description: Robot DDS network interface. It must already exist and be usable, for example eth10.
  linear_speed_m_s:
    type: number
    default: 0.3
    description: Forward speed magnitude in m/s used when forward_m is positive. Must not exceed max_linear_speed_m_s.
  backward_speed_m_s:
    type: number
    default: 0.4
    description: Backward speed magnitude in m/s used when forward_m is negative. Must not exceed max_linear_speed_m_s.
  angular_speed_rad_s:
    type: number
    default: 0.3
    description: Positive yaw rate in rad/s used by rotate_deg. Must not exceed max_angular_speed_rad_s.
  max_linear_speed_m_s:
    type: number
    default: 0.4
    description: Maximum planar speed magnitude allowed by this deployment, in m/s. Must be a finite positive number.
  max_angular_speed_rad_s:
    type: number
    default: 0.5
    description: Maximum absolute yaw rate allowed by this deployment, in rad/s. Must be a finite positive number.
  default_duration_s:
    type: number
    default: 5.0
    description: Duration in seconds used when velocity-mode duration_sec is zero. Must not exceed max_duration_s.
  max_duration_s:
    type: number
    default: 10.0
    description: Maximum duration of one move command, in seconds. Must be a finite positive number.
  command_timeout_s:
    type: number
    default: 0.3
    description: Official command lifetime in seconds for Twist and stop requests, in (0, 1]. A velocity stream must update at least once per lifetime.
