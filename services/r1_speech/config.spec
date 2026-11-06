specVersion: 1
description: R1 Speech 使用核心 Speech 配置和本机 Sherpa-ONNX 模型。
properties:
  speech_backend:
    type: string
    default: custom
    enum: [custom]
    description: 使用本包实现的 ASR/TTS 后端。
  speech_asr_backend_class:
    type: string
    default: r1_speech.backends:SherpaASRBackend
    description: 单次识别后端，输入为核心 Speech 转换后的 16 kHz PCM。
  speech_asr_stream_backend_class:
    type: string
    default: r1_speech.backends:SherpaASRBackend
    description: 中文增量识别后端，输出交给 Liaison。
  speech_tts_backend_class:
    type: string
    default: r1_speech.backends:SherpaTTSBackend
    description: 中文及词典英文合成后端，输出 16 kHz PCM。
  default_speaker_provider_id:
    type: string
    default: r1_audio
    description: speech/speak 的默认扬声器提供方。
  wake_word_model_dir:
    type: string
    description: 本包 rbnx-build/models 内的官方 KWS 模型绝对路径。
  wake_words:
    type: array
    items:
      type: string
    default: [罗伯特]
    description: Robonix 免提唤醒词，通过核心 Speech KWS 模型检测。
