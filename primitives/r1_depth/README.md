# R1 深度标准接口

`robonix/primitive/camera/depth` 以 gRPC 输出标准 `sensor_msgs/Image`，
编码为小端 `32FC1`，单位米；原始 0 和 65535 表示无效测量，输出 NaN。
step 为图像宽度乘 4。时间戳为 R1 主机读取设备帧的时间，同一订阅者
只接收新帧。默认光学 frame 为 `r1_depth_camera_optical_frame`。
该接口保留有效度量深度，不受灰度快照显示范围限制。

图像来自官方深度设备，默认按当前 R1 的大端 uint16 毫米格式读取；
不同深度客户端版本可通过 `byte_order` 显式选择 little 或 big。
RGB-D 配准、时间同步和相机安装 TF 尚未完成。完整配置见 `config.spec`。

`camera/intrinsics` 输出当前深度成像网格的 `sensor_msgs/CameraInfo`，
光学 frame 和时间戳对应有效深度帧。`calibration_file` 为独立的 ROS
camera_info YAML，尺寸必须等于深度输出尺寸。缺少配置时 K/R/P 为零，
表示未标定；读取真实标定后仍需完成 RGB-D 配准。

`camera/extrinsics` 输出静态 `TransformStamped`。`extrinsics_file` 的
child 必须等于深度 `frame_id`；缺少实测外参时返回
`FAILED_PRECONDITION`。两个接口与 RGB 共用 `r1_sensor_geometry` 的严格校验，
字段和检查入口见
[传感器几何配置](/home/xiongyingjie/Projects/go2-w-r1-robonix/robot-unitree-r1/common/r1_sensor_geometry/README.md)。

Read-only Unitree R1 binocular depth snapshot provider. It reads the latest
544x448 Y16 frame from `/dev/video-dep` (the v4l2loopback device fed by
Unitree's `depth_client`) and exposes `robonix/primitive/camera/depth_snapshot`
as an MCP tool. The file is read as big-endian uint16 millimetres (the stereo
module's network byte order); decoding it as native little-endian gives
implausible 1-90 mm values. The returned image is an 8-bit grayscale PNG;
near objects are bright, pixels outside the configured display range are black.

缺少或过期数据时，标准流返回 `UNAVAILABLE`。图像编码使用 Pillow；
提供方关闭后，读取线程停止并关闭自己持有的设备描述符。

## Enable the depth stream

Official Unitree R1 video service steps:

1. In the Unitree app, open **Settings -> Service Status**.
2. Turn off `video_hub` (it conflicts with the stereo service).
3. Enable `Stereo patch PC1` (it is not auto-start by default).
4. On the NX, run `sudo unitree_depth_start`; or run the client directly:
   `/unitree/module/system_patch_pc4/depth_client/client 192.168.123.161 5000 /dev/video-dep`
5. Verify: `v4l2-ctl -d /dev/video-dep --get-fmt-video` or
   `ffplay -f v4l2 -framerate 10 -video_size 544x448 -i /dev/video-dep`.

Configuration:

```yaml
config:
  device: /dev/video-dep
  width: 544
  height: 448
  fps: 10.0
  stale_after_s: 2.0
  min_depth_mm: 200.0
  max_depth_mm: 10000.0
```

Build (R1, offline wheels):

```bash
export RBNX_OFFLINE_WHEELS="$HOME/r1-robonix-bootstrap/wheels"
rbnx build -p primitives/r1_depth --no-update-check
```
