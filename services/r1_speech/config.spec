specVersion: 1
description: R1 Speech uses the core Speech settings and the onboard Sherpa-ONNX models.
properties:
  speech_backend:
    type: string
    default: custom
    enum: [custom]
    description: ASR/TTS backends implemented by this package.
  speech_asr_backend_class:
    type: string
    default: r1_speech.backends:SherpaASRBackend
    description: One-shot recognition backend. Input is 16 kHz PCM converted by core Speech.
  speech_asr_stream_backend_class:
    type: string
    default: r1_speech.backends:SherpaASRBackend
    description: Incremental Chinese recognition backend. Output goes to Liaison.
  speech_tts_backend_class:
    type: string
    default: r1_speech.backends:SherpaTTSBackend
    description: Chinese and lexicon-English synthesis backend. Output is 16 kHz PCM.
  default_speaker_provider_id:
    type: string
    default: r1_audio
    description: Default speaker provider for speech/speak.
  wake_word_model_dir:
    type: string
    description: Absolute path of the official KWS model inside this package's rbnx-build/models.
  wake_words:
    type: array
    items:
      type: string
    default: ["罗伯特"]  # i18n-ok: spoken wake word detected by the onboard KWS model
    description: Hands-free Robonix wake phrase, detected by the core Speech KWS model.
