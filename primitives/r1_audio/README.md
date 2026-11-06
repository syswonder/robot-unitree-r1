# R1 audio primitive

The standard `robonix/primitive/audio/mic` output and `robonix/primitive/audio/speaker` input both use `audio/AudioChunk`. Both ends are 16 kHz, mono, `pcm_s16le`. The message itself does not carry the format. This package captures the head-microphone multicast and plays PCM through the Unitree `voice` service.

Before use, confirm `vui_service >= 2.2.0.0` and `vui module >= 2.0.0.3` against the [official audio and light service note](https://support.unitree.com/home/zh/R1_developer/VuiClient_Service). The device sends microphone multicast only after the app or remote selects voice-wake mode and enables the microphone. A successful `GetVolume` only means the playback service is reachable.

The microphone listens on `eth10` at `239.168.123.161:5555` by default. Each subscription joins the group and emits `chunk_bytes`. The default 32000 bytes is one second. The stamp is the host time when the chunk was formed. Sequence starts at zero. `stale_after_s` with no data returns `UNAVAILABLE`. Cancelling a subscription closes that socket. Shutdown closes every microphone socket.

The speaker submits raw PCM to `voice` with one stream ID and the current instance's app name. One instance accepts one playback stream. A vendor error is reported as `UNAVAILABLE`. After a normal stream ends, the package waits for the submitted PCM duration, computed from the byte count, then stops playback for this instance. Cancel or shutdown stops the wait immediately. Every chunk of one playback stream uses the same stream ID so the official buffer can continue. An odd number of PCM bytes returns `INVALID_ARGUMENT` before submit. The package does not change the system volume and does not provide ASR or TTS.

The instance name is `RBNX_INSTANCE_NAME`, default `r1_audio`. Public settings, types, units, ranges, defaults and examples are in [config.spec](config.spec). Dependencies are Linux IPv4 multicast, Unitree SDK2 Python, CycloneDDS 0.10.2 and the Robonix API, on the deployment's Python 3.10.

On the R1:

```bash
source ~/r1-robonix/env.sh
cd ~/r1-robonix/robot-unitree-r1
rbnx build -p primitives/r1_audio --no-update-check
rbnx start -p primitives/r1_audio --endpoint 127.0.0.1:50051 --set network_interface=eth10
```

When the full deployment is already running, start and stop this package through that entry. Registration alone does not prove that capture and audible playback were accepted. The microphone times out when the upstream service is not sending multicast.
