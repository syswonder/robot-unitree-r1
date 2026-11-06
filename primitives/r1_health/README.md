# r1_health

Read-only Unitree R1 health provider. It subscribes to `rt/lowstate` and `rt/lf/bmsstate` and exposes:

- `robonix/primitive/health/state`
- `robonix/primitive/health/stream`

Soma consumes the stream, maps the readings onto the `soma.yaml` component tree, and Vitals displays the battery, IMU, joints and body health. Joint names and lowstate indices follow the official R1 `R1JointIndex` and `joint_idx_in_idl` mapping from `unitree_sdk2`'s `example/r1/low_level/r1_ankle_swing_example.cpp`.

The provider never sends a motion or low-level command.

Battery communication handling: the R1 low-level firmware continues to publish `rt/lf/bmsstate` at ~10 Hz when the BMS data link is lost, but fills the payload with zeros. The provider treats "all pack voltages are zero" as a communication fault, keeps the last valid BMS sample for a 2 s grace period, and then reports `body/body/battery/online=0` plus `body/body/battery/error=1`. This avoids showing a false 0% SOC while the battery telemetry is timing out.

Configuration:

```yaml
config:
  network_interface: eth10   # enp131s0 on the PC
  interval_s: 0.5
  stale_after_s: 2.0
```

Build (R1, offline wheels):

```bash
source ~/r1-robonix/env.sh
cd ~/r1-robonix/robot-unitree-r1
rbnx build -p primitives/r1_health --no-update-check
```

## Configuration and lifecycle

The instance name comes from `RBNX_INSTANCE_NAME`, default `r1_health`. Public settings are in [config.spec](config.spec). Shutdown closes every DDS subscription and waits for the peripheral status thread. A second shutdown does not reuse a closed resource. Re-initialization clears the sample cache and then accepts live device data.

`LowState` is read by its own thread at about 100 latest samples per second. BMS is received separately. A DDS writer lifecycle notice is not a state sample. Shutdown waits for the receiver threads. Freshness and battery validity still use `stale_after_s`.

## Client peripheral status

Health data includes `online`, `communication_ok` and `error` for `body/body/front_camera`, `body/body/depth_camera` and `body/body/audio`. RGB status checks that the provider is ACTIVE. Depth status also reads a real `32FC1` frame over the standard gRPC interface and checks the stamp, size and data length. Audio status requires the microphone and speaker capabilities to be registered, the provider to be ACTIVE, and official `GetVolume()` to show that the voice service answers. The query does not play sound. Audio status does not mean the microphone is currently producing PCM.

Each peripheral query waits two seconds after a round. Depth and voice requests time out after one second. A query result older than eight seconds is treated as unavailable. Soma and Vitals use these fields to update component status in the client. The audio component type is `audio_io`.
