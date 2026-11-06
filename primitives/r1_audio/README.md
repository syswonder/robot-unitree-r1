# R1 音频原语

标准 `robonix/primitive/audio/mic` 输出 `audio/AudioChunk`，
`robonix/primitive/audio/speaker` 接收同类型的数据流。两端约定
16 kHz、单声道、`pcm_s16le`；消息本身不包含音频格式。
此包使用头部麦克风组播和 Unitree `voice` 服务播放 PCM。

使用前按[官方音频灯光服务说明](https://support.unitree.com/home/zh/R1_developer/VuiClient_Service)
确认 `vui_service >= 2.2.0.0`、`vui module >= 2.0.0.3`。
通过 App 或遥控器切换到语音唤醒模式并打开麦克风后，设备才会发送
麦克风组播音频。`GetVolume` 成功仅表示播放服务可以访问。

麦克风默认监听 `eth10` 上 `239.168.123.161:5555`。每个订阅独立
加入组播，按 `chunk_bytes` 输出数据；默认 32000 字节对应 1 秒。
时间戳为主机形成音频块的时间，sequence 从零递增。
连续 `stale_after_s` 没有数据时返回 `UNAVAILABLE`；取消订阅关闭
对应 socket，shutdown 关闭全部麦克风 socket。

扬声器使用唯一 stream ID 和当前实例的 app 名称，将原始 PCM
提交给 `voice`。单个实例只接受一个播放流；厂商返回错误时报告
`UNAVAILABLE`。正常输入流结束后，按 PCM 字节数计算并等待已经提交
的音频时长，再停止本实例播放；取消或 shutdown 时及时停止。
同一个播放流的全部数据块使用相同 stream ID，以使用官方缓存续播。
无效的奇数字节 PCM 在提交前返回 `INVALID_ARGUMENT`。
不会修改系统音量，也不提供 ASR 或 TTS。

实例名读取 `RBNX_INSTANCE_NAME`，默认 `r1_audio`。公开配置及
类型、单位、范围、默认值和示例见 [config.spec](config.spec)。
依赖 Linux IPv4 组播、Unitree SDK2 Python、CycloneDDS 0.10.2
和 Robonix API，使用部署已有的 Python 3.10 环境。

在 R1 上执行：

```bash
source ~/r1-robonix/env.sh
cd ~/r1-robonix/robot-unitree-r1
rbnx build -p primitives/r1_audio --no-update-check
rbnx start -p primitives/r1_audio --endpoint 127.0.0.1:50051 --set network_interface=eth10
```

已有整机部署运行时，通过整机启动入口管理此包。仅注册成功不能证明
有效收音和可听播放已完成验收；麦克风上游服务未提供组播数据时会超时。
