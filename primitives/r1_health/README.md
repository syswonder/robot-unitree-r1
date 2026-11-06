# r1_health

Read-only Unitree R1 health provider. It subscribes to `rt/lowstate` and
`rt/lf/bmsstate` and exposes:

- `robonix/primitive/health/state`
- `robonix/primitive/health/stream`

Soma consumes the stream, maps the readings onto the `soma.yaml` component
tree, and Vitals displays the battery, IMU, joints and body health. Joint
names and lowstate indices follow the official R1 `R1JointIndex` and
`joint_idx_in_idl` mapping from `unitree_sdk2`'s
`example/r1/low_level/r1_ankle_swing_example.cpp`.

The provider never sends a motion or low-level command.

Battery communication handling: the R1 low-level firmware continues to
publish `rt/lf/bmsstate` at ~10 Hz when the BMS data link is lost, but fills
the payload with zeros. The provider treats "all pack voltages are zero" as a
communication fault, keeps the last valid BMS sample for a 2 s grace period,
and then reports `body/body/battery/online=0` plus
`body/body/battery/error=1`. This avoids showing a false 0% SOC while the
battery telemetry is timing out.

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
## 配置与生命周期

实例名称由 `RBNX_INSTANCE_NAME` 指定，默认 `r1_health`。
公开配置说明见 [config.spec](config.spec)。shutdown 关闭全部 DDS
订阅并等待外设状态查询线程结束；重复 shutdown 不重复使用已关闭资源。
重新初始化清空采样缓存，再接收真实设备数据。

`LowState` 由独立线程约每秒读取 100 次最新样本；BMS 独立接收。
DDS writer 生命周期通知不作为状态样本。关闭时等待接收线程结束。
健康数据的新鲜度和电池有效性检查继续使用 `stale_after_s`。

## Client 外设状态

健康数据包含 `body/body/front_camera`、`body/body/depth_camera` 和
`body/body/audio` 的 `online`、`communication_ok`、`error`。
RGB 状态检查提供方是否 ACTIVE；深度状态同时通过标准 gRPC 接口
读取实际 `32FC1` 帧并检查时间戳、尺寸和数据长度。
音频状态要求麦克风、扬声器能力已注册且提供方 ACTIVE，并通过
官方 `GetVolume()` 确认 voice 服务可以响应。查询不会播放声音；
音频状态不代表麦克风当前正在产生 PCM 数据。

外设查询每轮结束后等待两秒，深度与 voice 请求各有一秒超时。
超过八秒未更新的查询结果按不可用处理。Soma/Vitals 根据这些
数据更新 Client 中的组件状态，音频组件类型为 `audio_io`。
