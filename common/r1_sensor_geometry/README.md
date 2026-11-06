# R1 传感器几何配置

RGB 与深度原语共同使用本库读取内参和静态安装外参。库通过 PyYAML
解析标准文件，通过 NumPy 检查数值和旋转矩阵；由原语使用生成的
CameraInfo、TransformStamped 消息对外提供数据。

## 内参文件

`calibration_file` 为 ROS camera_info YAML，需要以下字段：

| 字段 | 格式和要求 |
| --- | --- |
| `image_width`、`image_height` | 实际标定分辨率，正整数 |
| `distortion_model` | `plumb_bob`、`rational_polynomial` 或 `equidistant` |
| `distortion_coefficients` | `rows=1`、`cols` 及数值列表 `data`；plumb_bob 支持 4/5 个、rational_polynomial 为 8 个、equidistant 为 4 个 |
| `camera_matrix` | `rows=3`、`cols=3`、九个行优先数值 |
| `rectification_matrix` | 3×3 旋转矩阵，正交且行列式为 1 |
| `projection_matrix` | `rows=3`、`cols=4`、十二个行优先数值 |

K/P 焦距必须为正，所有数值必须有限，最后一行遵循标准针孔模型。
文件必须对应原语实际输出的旋转、裁剪和分辨率。内参接口不自动改变
标定尺寸或推导缺少的参数。深度使用对应深度成像网格的独立标定。

未设置内参文件时返回未标定 CameraInfo，K/R/P 为零。
`tests/data/ros_camera_info.yaml` 是上游 ROS 格式参考数据，来源及许可证
随文件保存；部署时使用本机设备的实测文件。

## 静态外参文件

`extrinsics_file` 使用标准 TransformStamped YAML 字段：

| 字段 | 含义 |
| --- | --- |
| `header.frame_id` | 相机安装关系的 parent frame |
| `child_frame_id` | 原语实际输出的光学 frame，必须与 `frame_id` 配置相同 |
| `transform.translation.x/y/z` | child 原点在 parent 中的位置，单位米 |
| `transform.rotation.x/y/z/w` | child 相对 parent 的归一化四元数 |

该变换将 child 坐标中的点表示到 parent 坐标，静态消息时间戳为零。
每个 gRPC 订阅者立即取得当前配置；文件变更后需要重新初始化或重启原语。
未提供实测外参时，接口报告 `FAILED_PRECONDITION`。

头部相机安装到头部 link 时，应以真实安装部件作为 parent；头部关节
到 `base_link` 的运动关系需要 URDF、关节反馈及 TF。当前整机 URDF
尚未增加实测相机 frame。

## 配置检查

`calibration_file` 与 `extrinsics_file` 的相对路径均以部署根目录为基准。
在 R1 部署根目录使用已经构建的原语环境运行：

```bash
primitives/r1_depth/.venv/bin/python scripts/validate_camera_geometry.py --frame-id r1_depth_camera_optical_frame --width 544 --height 448 --calibration-file config/depth_camera_info.yaml --extrinsics-file config/depth_extrinsics.yaml
```

此命令读取操作者已提供的实测文件。省略两个文件参数时输出
`calibrated=false` 和 `extrinsics_available=false`。指定的文件不存在、
格式错误、frame 不符或尺寸不符时，命令立即失败。

本库不采集图像，不发布动态 TF，不控制机器人。

## 本机检查记录

Python 3.10.22 环境下已通过十项检查，覆盖上游 ROS 标定格式、
CameraInfo 序列化、未标定状态、尺寸冲突、非有限数值、矩阵结构、
旋转矩阵、外参 frame 和四元数。参考数据来源及许可证见 `tests/data/`。

新增能力通过真实本机 Atlas/gRPC 注册检查。`r1_camera` 和 `r1_depth`
均声明 `intrinsics`、`extrinsics`；缺少外参文件时返回
`FAILED_PRECONDITION`。

## 板端数据流检查

2026-10-28 已完成 R1 原生构建和真实数据流检查：RGB 约 15 FPS，
深度约 10.75 FPS，各取得七组与 CameraInfo 相同的帧时间戳。
当前未提供实测内外参，两路 CameraInfo 均明确表示未标定。

在部署根目录运行：

```bash
primitives/r1_camera/.venv/bin/python scripts/check_camera_geometry_contracts.py --expect-unconfigured
primitives/r1_camera/.venv/bin/python scripts/check_camera_geometry_live.py --output .tools/camera-geometry/result.json
```

数据流检查同时订阅两路图像和内参，检查标准编码、尺寸、数据长度、
frame_id、时间戳与同帧关系，并保存图像频率及深度数值分布。
结果文件必须尚不存在，每次验收使用新的文件名。
深度数值分布检查不验证测距精度；RGB-D 配准、两路图像的时间同步和
已知距离参照物检查仍需完成。
