# R1 deployment config

- `vitals_thresholds.yaml`: battery, IMU and joint health thresholds. Onboard temperature warning is 85 C and error is 95 C.
- `camera_calibration.json`: approximate stereo parameters used by the local map, 544x448, `fx=fy=213.5`, `cx=272`, `cy=224`, baseline 0.060 m. Extrinsics are still placeholders.

The map approximation and the measured calibration used by the standard camera primitives are separate. Each camera primitive reads a ROS camera_info YAML from `calibration_file` and a TransformStamped YAML from `extrinsics_file`. The two providers are configured separately. Initialization fails when a file is missing or invalid.

Measured parameters require the official `cam_param.txt`, checked against the current image source, rotation, crop, pixel coordinates and depth registration. Those measured files are not in this directory yet.

Geometry fields and the standalone check commands are documented in [sensor geometry](../common/r1_sensor_geometry/README.md). Motion parameters for the full deployment are in `robonix_manifest.yaml` under `r1_chassis` and the arm primitives. This directory does not yet contain Nav2 or RTAB-Map parameters.
