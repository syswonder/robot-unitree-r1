specVersion: 1
description: R1 度量深度标准数据流与显示快照配置。
properties:
  device:
    type: string
    default: /dev/video-dep
    description: 官方深度客户端写入的 V4L2 设备路径；需要 video 组权限。
  width:
    type: integer
    default: 544
    description: 深度设备实际宽度，单位像素，必须为正整数。
  height:
    type: integer
    default: 448
    description: 深度设备实际高度，单位像素，必须为正整数。
  fps:
    type: number
    default: 10.0
    description: 无数据时的设备轮询频率，单位 Hz，必须为有限正数；有效数据按设备实际输出读取。
  stale_after_s:
    type: number
    default: 2.0
    description: 缓存样本有效时间，单位秒，必须为有限正数。
  min_depth_mm:
    type: number
    default: 200.0
    description: 灰度快照的最近显示距离，单位毫米，必须为非负有限数值；不限制标准深度流。
  max_depth_mm:
    type: number
    default: 10000.0
    description: 灰度快照的最远显示距离，单位毫米，必须大于 min_depth_mm；不限制标准深度流。
  frame_id:
    type: string
    default: r1_depth_camera_optical_frame
    description: 深度相机光学 frame，必须非空；实际安装变换及 RGB-D 配准需要设备标定。
  byte_order:
    type: string
    default: big
    description: 原始 uint16 深度字节序，可选 big 或 little；当前 R1 客户端实际使用 big。原始数值单位毫米，标准输出为小端 32FC1 米，0 和 65535 转换为 NaN。
  calibration_file:
    type: string
    default: ""
    description: 对应当前深度成像几何的 ROS camera_info YAML；尺寸必须等于 width/height。相对路径以部署目录为基准，例如 config/depth_camera_info.yaml。留空时 CameraInfo 的 K/R/P 为零，表示未标定。
  extrinsics_file:
    type: string
    default: ""
    description: 实测安装外参的 TransformStamped YAML；child_frame_id 必须等于当前深度光学 frame_id，translation 单位米，rotation 为归一化 x/y/z/w。相对路径以部署目录为基准；留空时 extrinsics 返回 FAILED_PRECONDITION。
