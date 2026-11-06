# R1 相机标准接口

| 能力 | 传输 | 数据 |
|---|---|---|
| `robonix/primitive/camera/rgb` | gRPC 流 | `sensor_msgs/Image`，`rgb8` 原始像素，step 为宽度乘 3 |
| `robonix/primitive/camera/intrinsics` | gRPC 流 | `sensor_msgs/CameraInfo`，供晚连接客户端读取最新标定 |
| `robonix/primitive/camera/extrinsics` | gRPC 流 | 静态安装 `geometry_msgs/TransformStamped`，每个晚订阅者可读取配置值 |
| `robonix/primitive/camera/snapshot` | MCP | JPEG 快照，供网页和模型按需读取 |

主部署使用宇树官方 H.264 RTP 的 5001 img 图像，GStreamer 接收并旋转，
PyAV 负责 MJPEG 分帧，Pillow 解码原始 RGB 像素。也支持官方
`videohub` API 1001 的 `GetImageSample`。输入与流式输出共用最新图像，
每个订阅者只发送新帧。消息时间戳为 R1 接收帧的时间。

在 App 关闭 `video_hub` 并开启 `Stereo patch PC1` 后接收双目图像。
官方端口 5001 为 img、5002 为左目、5003 为右目；同一 UDP 端口由一个
接收进程管理。当前本地地图服务使用 5002，不应再为它启动第二个接收器。

配置见 `config.spec`。默认光学 frame 为 `r1_front_camera_optical_frame`，
轴向为右、下、前。到本体的安装变换仍需测量并加入整机 URDF。
输出图像的旋转和分辨率必须与标定文件一致。

`calibration_file` 接受标准 ROS camera_info YAML，包括
`image_width`、`image_height`、`distortion_model`、`distortion_coefficients`、
`camera_matrix`、`rectification_matrix`、`projection_matrix`。
相对路径以部署目录为基准。未设置时 D/K/R/P 为零，表示未标定；
不会使用本地地图的 FOV 近似内参。真实设备参数从官方 9080 页面下载，
需确认参数格式、图像旋转和像素几何后生成对应 YAML。

标定加载由共享 `r1_sensor_geometry` 库完成，校验图像尺寸、矩阵形状、
有限数值、焦距、畸变系数和旋转矩阵。内参流按当前有效图像更新时间戳；
缓存过期时返回 `UNAVAILABLE`，标定与输出尺寸不符时返回
`FAILED_PRECONDITION`。

`extrinsics_file` 接受标准 TransformStamped YAML，字段包括
`header.frame_id`、`child_frame_id`、`transform.translation.{x,y,z}`、
`transform.rotation.{x,y,z,w}`。child 必须等于 `frame_id`，平移单位米，
四元数必须归一化。静态变换时间戳为零，表示与图像采集时间无关的安装关系。
没有实测配置时外参接口返回 `FAILED_PRECONDITION`。配置格式和本机检查入口见
[传感器几何配置](/home/xiongyingjie/Projects/go2-w-r1-robonix/robot-unitree-r1/common/r1_sensor_geometry/README.md)。

当前 RGB 与深度使用独立光学 frame，尚未完成配准、同步和完整 TF。
本接口为 gRPC 数据面；当前 Robonix Scene 的 ROS 2 数据面仍需单独接入。

从部署目录执行 `rbnx build -p primitives/r1_camera`，由整机脚本启动。
依赖 GStreamer、PyAV 16.0.1、Pillow 11.3.0、Unitree SDK、Robonix API 和共享几何库。
无输入、过期数据和解码错误直接报告；关闭时停止图像进程和读取线程。

官方依据：[R1 视频流服务接口](https://support.unitree.com/home/zh/R1_developer/video_service)。
