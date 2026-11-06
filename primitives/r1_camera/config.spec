specVersion: 1
description: R1 camera stream and snapshot settings.
properties:
  source:
    type: string
    default: videohub
    description: videohub uses the official image RPC. stereo_udp uses the official H.264 RTP stream.
  network_interface:
    type: string
    default: eth10
    description: DDS interface for videohub. It must already exist. On the R1 this is eth10.
  timeout_s:
    type: number
    default: 3.0
    description: videohub RPC timeout in seconds. Must be a finite positive number.
  udp_port:
    type: integer
    default: 5001
    description: RTP port from 1 to 65535. Official ports are 5001 img, 5002 left and 5003 right. One receiver process owns a port.
  rotate:
    type: string
    default: clockwise
    description: Output rotation, one of none, clockwise, counterclockwise, rotate-180. The calibration must match the processed image.
  stale_after_s:
    type: number
    default: 2.0
    description: Seconds a cached image stays valid. Must be a finite positive number. Timeout returns unavailable.
  frame_id:
    type: string
    default: r1_front_camera_optical_frame
    description: Optical frame of the output image, x right, y down, z forward. The mount into the body still needs a calibration and a URDF update.
  calibration_file:
    type: string
    default: ""
    description: ROS camera_info YAML. A relative path is from the deployment directory, for example config/rgb_camera_info.yaml. It must include the real image_width, image_height, distortion_model and D/K/R/P. Empty means the CameraInfo zero matrices report uncalibrated.
  extrinsics_file:
    type: string
    default: ""
    description: Measured mount TransformStamped YAML. A relative path is from the deployment directory. It must include header.frame_id, child_frame_id, transform.translation and transform.rotation. The child must match the output frame_id. Empty makes extrinsics return FAILED_PRECONDITION.
