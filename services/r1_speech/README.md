# R1 Speech 服务

复用 Robonix `services/speech` 的生命周期、ASR、TTS、唤醒和语音播放
接口，通过其 custom backend 加载本包的 Sherpa-ONNX 实现。

中文 ASR 使用 `sherpa-onnx-streaming-zipformer-ctc-zh-int8-2025-06-30`，
按实际 PCM 连续识别，向 Liaison 输出增量文本。模型不提供校准后的
置信度，`confidence` 为 0，表示未知。TTS 使用 `vits-melo-tts-zh_en`，
支持中文和词典中的英文，输出重采样为 16 kHz 单声道 s16le。

官方模型压缩包位于 `bootstrap/speech-models`，来源和 SHA256 记录在
本包 `models.sources.json`。构建解压至本包 `rbnx-build/models`，运行时
直接读取模型。依赖完整采用核心 Speech 的 `pyproject.toml`。
`R1_SPEECH_THREADS` 默认为 4，接受正整数，控制 ASR/TTS 的 CPU 线程。

在 R1 使用 `rbnx build -p services/r1_speech --no-update-check` 构建。
完整清单将该服务注册为 `speech`；Client 输入和输出可分别选择
“PC”（`audio_client_bridge`）或“R1”（`r1_audio`）。当前默认使用
PC 麦克风和 R1 扬声器。PC 音频服务及 SSH 转发由
`scripts/pc_audio.sh start` 在 PC 桌面会话启动。
R1 麦克风的语音唤醒模式通过宇树 App 或遥控器开启；Robonix 免提
通过 Client 开启。
