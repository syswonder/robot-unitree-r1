specVersion: 1
description: R1 相机标准数据流与快照配置。
properties:
  source:
    type: string
    default: videohub
    description: videohub 使用官方图像 RPC；stereo_udp 使用官方 H.264 RTP 推流。
  network_interface:
    type: string
    default: eth10
    description: videohub 的 DDS 接口，必须已存在；R1 本机为 eth10。
  timeout_s:
    type: number
    default: 3.0
    description: videohub RPC 超时秒数，必须为有限正数。
  udp_port:
    type: integer
    default: 5001
    description: 1–65535 的 RTP 端口；官方 5001 为 img，5002 为左目，5003 为右目。同一端口只能由一个接收进程使用。
  rotate:
    type: string
    default: clockwise
    description: 输出旋转，可选 none、clockwise、counterclockwise、rotate-180；标定必须对应处理后的图像。
  stale_after_s:
    type: number
    default: 2.0
    description: 缓存图像的有效时间，单位秒，必须为有限正数；超时返回数据不可用。
  frame_id:
    type: string
    default: r1_front_camera_optical_frame
    description: 输出图像光学 frame，x 向右、y 向下、z 向前；实际到本体的安装变换仍需标定并加入 URDF。
  calibration_file:
    type: string
    default: ""
    description: ROS camera_info YAML 文件；相对路径以部署目录为基准，例如 config/rgb_camera_info.yaml。必须包括真实 image_width、image_height、distortion_model 和 D/K/R/P；留空时 CameraInfo 的零矩阵明确表示未标定。
  extrinsics_file:
    type: string
    default: ""
    description: 实测安装外参的 TransformStamped YAML；相对路径以部署目录为基准。必须包含 header.frame_id、child_frame_id、transform.translation 和 transform.rotation；child 必须匹配输出 frame_id。留空时 extrinsics 返回 FAILED_PRECONDITION。
