# Configuration accepted under the `r1_state` primitive entry in
# robonix_manifest.yaml. The provider never sends a motion command.
specVersion: 1
description: Read-only R1 state provider configuration.

properties:
  network_interface:
    type: string
    default: enp131s0
    description: >-
      Host interface connected to the R1 robot network. This is the interface
      passed to Unitree ChannelFactoryInitialize; use enp131s0 on the current
      PC and eth10 on the R1 onboard computer.

  stale_after_s:
    type: number
    default: 2.0
    description: >-
      Age in seconds after which the cached IMU/BMS samples are marked stale.
      The snapshot is still returned, but `stale` is true and the sample ages
      are included.
