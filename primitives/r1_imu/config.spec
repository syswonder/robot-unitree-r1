specVersion: 1
description: Read-only standard stream settings for the built-in R1 IMU.
properties:
  network_interface:
    type: string
    default: eth10
    description: DDS network interface. It must exist. On the R1 this is eth10.
  frame_id:
    type: string
    default: imu_in_pelvis_link
    description: Real IMU frame in the URDF. Must be non-empty. Angular velocity is rad/s and acceleration is m/s^2.
  stale_after_s:
    type: number
    default: 2.0
    description: Seconds to wait before returning UNAVAILABLE when no valid sample arrives. Must be a finite positive number.
