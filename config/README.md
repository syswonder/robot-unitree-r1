# R1 部署配置

- `vitals_thresholds.yaml`：电池、IMU 和关节健康阈值；板载温度 warning 为 85 °C，error 为 95 °C。
- `camera_calibration.json`：本地 Map 使用的近似双目参数，544×448、
  `fx=fy=213.5`、`cx=272`、`cy=224`、baseline 0.060 m；外参仍为占位值。

Map 配置中的近似值与标准相机原语的实测标定分别管理。相机原语通过
`calibration_file` 读取 ROS camera_info YAML，通过 `extrinsics_file`
读取 TransformStamped YAML；两个相机提供方分别配置，文件不存在或
数值无效时初始化失败。

真实参数需要取得官方 `cam_param.txt`，并核对当前图像源、旋转、裁剪、
像素坐标及深度配准状态。交接文档记录的下载入口为 `.161:9080`，
本轮机器人尚未开机，尚未取得新的实测参数。

标准几何字段和独立检查命令见
[传感器几何配置](../common/r1_sensor_geometry/README.md)。
整机运动参数保存在 `robonix_manifest.yaml` 的 `r1_chassis`
和双臂原语配置中。当前目录尚未提供 Nav2 和 RTAB-Map 配置。
