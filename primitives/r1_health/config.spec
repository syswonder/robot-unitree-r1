specVersion: 1
description: Read-only health settings for the R1 battery, joints, IMU, depth camera and audio service.
properties:
  network_interface:
    type: string
    default: eth10
    description: Non-empty DDS interface that exists and is attached to the robot network. Example eth10. The interface and sport mode are not changed.
  interval_s:
    type: number
    default: 0.5
    description: Health stream period in seconds. Must be a finite positive number. Example 0.5 is 2 Hz.
  stale_after_s:
    type: number
    default: 2.0
    description: Freshness limit in seconds for joint feedback, the last valid BMS sample and the depth frame. Must be a finite positive number. Example 2.0. An all-zero BMS packet does not refresh the valid-sample time.
