# Unitree R1 EDU

Robonix deployment repository. Catalog name: `robonix.robot.unitree.r1`.

The deployment includes the body description, state, health, RGB, depth, IMU and audio, plus walking and dual-arm control through Unitree's official sport controller. Speech and the visual action decider start with the full manifest. Primitives and services live in this repository and are referenced by relative path.

Maintainer: Zhenyu Zhang \<768726812@qq.com\>

Prepare the Robonix source tree, wheels, toolchains, and speech models before the first build. The layout and checksums are in [INSTALL.md](INSTALL.md). Licenses for vendored files are in [NOTICE](NOTICE).

## Start

Two entries are available. They do not start the same processes.

`rbnx boot` starts only the providers and services named in the manifest: Atlas, Soma, Vitals, Pilot, the hardware primitives, speech, and the visual action decider. It does not start the Unitree depth receiver, the map service, or the web client. `rbnx` must already be on `PATH`, and the packages must already be built.

```bash
source scripts/env.sh
rbnx boot -f robonix_manifest.yaml --no-update-check
```

`scripts/env.sh` exports `ROBONIX_DEPLOY_DIR`. Thresholds, the wake-word model, and record directories in the manifest expand from that directory. For chat, export `VLM_BASE_URL`, `VLM_API_KEY`, and `VLM_MODEL` before this command, or accept the defaults documented in [INSTALL.md](INSTALL.md). The key is not stored in the manifest.

`scripts/02_start.sh` is the onboard helper. It also starts the depth receiver, the map service on port 50107, and the web client on `http://127.0.0.1:7860/`. It expects the workspace in [INSTALL.md](INSTALL.md), Stereo patch PC1 with `video_hub` off, and an OpenAI-compatible service at `VLM_BASE_URL` when chat is required. Store a key with `bash scripts/vlm_key.sh set deepseek`.

```bash
bash scripts/01_build.sh
bash scripts/02_start.sh
bash scripts/03_stop.sh
```

The read-only sensor deployment omits the chassis, arms, audio, and dialogue. It does not start the web client:

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
