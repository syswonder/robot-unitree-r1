# Unitree R1 EDU

Robonix 整机部署仓库，目录名 `robonix.robot.unitree.r1`。

部署包含本体描述、状态、健康、RGB、深度、IMU、音频，以及基于宇树官方运控的行走和双臂控制。语音和视觉动作决策随整机清单启动。原语和服务放在本仓库内，用相对路径引用。

维护者：张振宇 \<768726812@qq.com\>

## 启动

在 R1 上，先准备 Robonix 运行时，再：

```bash
source scripts/env.sh
rbnx boot -f robonix_manifest.yaml --no-update-check
```

`scripts/env.sh` 会导出 `ROBONIX_DEPLOY_DIR`。清单里的阈值、语音模型和记录目录都相对这个目录展开。模型密钥通过 `VLM_BASE_URL`、`VLM_API_KEY` 和 `VLM_MODEL` 传入，不写进仓库。

本机辅助入口：

```bash
bash scripts/01_build.sh
bash scripts/02_start.sh
bash scripts/03_stop.sh
```

只读传感器部署不包含底盘、机械臂、音频和对话：

```bash
bash scripts/start_sensors.sh
bash scripts/stop_sensors.sh
```

`robonix_manifest.r1-native.yaml` 是根清单的符号链接，已有启动命令可以继续使用这个文件名。

## 其他清单

这些文件只用于本地启动，不进入软件包目录：

| 文件 | 用途 |
| --- | --- |
| `robonix_manifest.r1-native-sensors.yaml` | 状态、健康、RGB、深度、IMU |
| `robonix_manifest.r1-native-state.yaml` | Atlas、Soma 和只读状态 |
| `robonix_manifest.state-only.yaml` | 工作站上的状态通路检查 |
| `robonix_manifest.pc-readonly.yaml` | 工作站网卡上的只读状态、健康和相机 |

## 布局

```text
robot-unitree-r1/
├── robonix_manifest.yaml          # 目录索引的整机清单
├── soma.yaml                      # 本体、部件和导出
├── urdf/                          # 官方 URDF 与网格，另有 BSD-3-Clause
├── config/                        # Vitals 阈值和相机近似参数
├── primitives/                    # 底盘、双臂、传感器、音频
├── services/                      # 语音、视觉动作决策
├── map_service/                   # 本机占用栅格
└── scripts/
```

`audio_client_bridge` 随仓库提供，对应已发布的 `robonix.primitive.audio.client_bridge`。URDF 来自 `unitreerobotics/unitree_ros` 的 `robots/r1_description`，许可证见 `urdf/LICENSE.unitree`。网格路径和文件名保持官方原样，只增加了零偏移的 `base_link`。

行走的前进和后退、双腕关节运动已有现场记录。转向、末端定位精度和抓取仍待验收。
