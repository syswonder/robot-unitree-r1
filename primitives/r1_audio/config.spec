specVersion: 1
description: R1 head-microphone multicast and voice playback settings. PCM is fixed at 16 kHz, mono, s16le.
properties:
  network_interface:
    type: string
    default: eth10
    description: Robot network interface with IPv4 configured. The name is 1 to 15 bytes. It affects DDS and multicast join. Example eth10.
  multicast_group:
    type: string
    default: 239.168.123.161
    description: IPv4 multicast address of the real head microphone. It must be in the multicast range. Example 239.168.123.161.
  port:
    type: integer
    default: 5555
    description: Microphone UDP port, 1 to 65535. Example 5555.
  sample_rate_hz:
    type: integer
    default: 16000
    description: PCM sample rate in Hz. Only 16000 is accepted. Audio is not resampled.
  chunk_bytes:
    type: integer
    default: 32000
    description: Bytes in each microphone AudioChunk. Must be a positive even number. 32000 is 1 second and 3200 is 0.1 second.
  stale_after_s:
    type: number
    default: 3.0
    description: Seconds without UDP data before the microphone stream ends with UNAVAILABLE. Must be a finite positive number. Example 3.0.
