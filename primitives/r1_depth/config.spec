specVersion: 1
description: Metric depth stream and display-snapshot settings for the R1.
properties:
  device:
    type: string
    default: /dev/video-dep
    description: V4L2 device written by the official depth client. The process needs the video group.
  width:
    type: integer
    default: 544
    description: Actual depth-device width in pixels. Must be a positive integer.
  height:
    type: integer
    default: 448
    description: Actual depth-device height in pixels. Must be a positive integer.
  fps:
    type: number
    default: 10.0
    description: Device poll rate in Hz when no data is available. Must be a finite positive number. Valid frames are read at the device rate.
  stale_after_s:
    type: number
    default: 2.0
    description: Seconds a cached sample stays valid. Must be a finite positive number.
  min_depth_mm:
    type: number
    default: 200.0
    description: Nearest display distance of the grayscale snapshot, in millimetres. Must be a non-negative finite number. It does not clip the standard depth stream.
  max_depth_mm:
    type: number
    default: 10000.0
    description: Farthest display distance of the grayscale snapshot, in millimetres. Must be greater than min_depth_mm. It does not clip the standard depth stream.
  frame_id:
    type: string
    default: r1_depth_camera_optical_frame
    description: Depth camera optical frame. Must be non-empty. The real mount and RGB-D registration need a device calibration.
  byte_order:
    type: string
    default: big
    description: Byte order of the raw uint16 depth, big or little. The current R1 client uses big. Raw values are millimetres. The standard output is little-endian 32FC1 metres, and 0 and 65535 become NaN.
  calibration_file:
    type: string
    default: ""
    description: ROS camera_info YAML for the current depth image geometry. Its size must equal width and height. A relative path is from the deployment directory, for example config/depth_camera_info.yaml. Empty means CameraInfo K/R/P are zero and the camera is uncalibrated.
  extrinsics_file:
    type: string
    default: ""
    description: Measured mount TransformStamped YAML. child_frame_id must equal the current depth optical frame_id. Translation is in metres and rotation is a normalized x,y,z,w quaternion. A relative path is from the deployment directory. Empty makes extrinsics return FAILED_PRECONDITION.
