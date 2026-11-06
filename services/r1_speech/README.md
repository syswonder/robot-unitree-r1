# R1 speech service

Reuses the lifecycle, ASR, TTS, wake-word and playback interfaces from Robonix `services/speech`, and loads this package's Sherpa-ONNX backends through the custom backend hook.

Chinese ASR uses `sherpa-onnx-streaming-zipformer-ctc-zh-int8-2025-06-30`. It recognizes continuous PCM and sends incremental text to Liaison. The model does not provide a calibrated confidence, so `confidence` is 0, meaning unknown. TTS uses `vits-melo-tts-zh_en`. It speaks Chinese and the English words in its lexicon, resampled to 16 kHz mono s16le.

Official model archives live in `bootstrap/speech-models`. Sources and SHA256 values are in this package's `models.sources.json`. The build unpacks them into `rbnx-build/models`, and runtime reads those files directly. Dependencies follow the core Speech `pyproject.toml`. `R1_SPEECH_THREADS` defaults to 4, must be a positive integer, and sets the ASR/TTS CPU thread count.

Build on the R1 with `rbnx build -p services/r1_speech --no-update-check`. The full manifest registers this service as `speech`. The client can choose "PC" (`audio_client_bridge`) or "R1" (`r1_audio`) for input and output separately. The current default is the PC microphone and the R1 speaker. The PC audio service and SSH forward are started with `scripts/pc_audio.sh start` in a PC desktop session. R1 microphone voice-wake mode is enabled in the Unitree app or remote. Hands-free Robonix wake is enabled from the client.
