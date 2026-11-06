# Unitree R1 EDU

Robonix deployment repository. Catalog name: `robonix.robot.unitree.r1`.

The deployment includes the body description, state, health, RGB, depth, IMU and audio, plus walking and dual-arm control through Unitree's official sport controller. Speech and the visual action decider start with the full manifest. Primitives and services live in this repository and are referenced by relative path.

Maintainer: Zhenyu Zhang \<768726812@qq.com\>

## Start

On the R1, with the Robonix runtime already installed:

```bash
source scripts/env.sh
rbnx boot -f robonix_manifest.yaml --no-update-check
```

`scripts/env.sh` exports `ROBONIX_DEPLOY_DIR`. Thresholds, the wake-word model and record directories in the manifest expand from that directory. Model credentials come from `VLM_BASE_URL`, `VLM_API_KEY` and `VLM_MODEL`. They are not stored in the repository.

Onboard helpers:

```bash
bash scripts/01_build.sh
bash scripts/02_start.sh
bash scripts/03_stop.sh
```

The read-only sensor deployment omits the chassis, arms, audio and dialogue:

```bash
bash scripts/start_sensors.sh
bash scripts/stop_sensors.sh
```

`robonix_manifest.r1-native.yaml` is a symlink to the root manifest, so existing boot commands that use that filename keep working.

## Other manifests

These files are local launch profiles. The package catalog indexes only `robonix_manifest.yaml`.

| File | Use |
| --- | --- |
| `robonix_manifest.r1-native-sensors.yaml` | State, health, RGB, depth and IMU |
| `robonix_manifest.r1-native-state.yaml` | Atlas, Soma and read-only state |
| `robonix_manifest.state-only.yaml` | State-path check on a workstation |
| `robonix_manifest.pc-readonly.yaml` | Read-only state, health and camera on a workstation NIC |

## Layout

```text
robot-unitree-r1/
├── robonix_manifest.yaml          # catalog-indexed deployment
├── soma.yaml                      # body, components and exports
├── urdf/                          # official URDF and meshes, BSD-3-Clause
├── config/                        # Vitals thresholds and approximate camera parameters
├── primitives/                    # chassis, arms, sensors and audio
├── services/                      # speech and visual action decider
├── map_service/                   # onboard occupancy grid
└── scripts/
```

`audio_client_bridge` is included in this tree. It corresponds to the published package `robonix.primitive.audio.client_bridge`. The URDF comes from `unitreerobotics/unitree_ros` `robots/r1_description`; see `urdf/LICENSE.unitree`. Mesh paths and filenames stay as upstream published them. The only addition is a zero-offset `base_link`.

Forward and backward walking, and both wrist joints, have on-robot records. Turning, end-effector accuracy and grasping still need acceptance.
