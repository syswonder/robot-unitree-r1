# R1 sensor geometry

The RGB and depth primitives share this library to read intrinsics and a static mount extrinsic. The library parses the standard files with PyYAML and checks numbers and rotation matrices with NumPy. The primitives publish the resulting CameraInfo and TransformStamped messages.

## Intrinsics file

`calibration_file` is a ROS camera_info YAML with these fields:

| Field | Format |
| --- | --- |
| `image_width`, `image_height` | Positive integers, the resolution that was calibrated |
| `distortion_model` | `plumb_bob`, `rational_polynomial` or `equidistant` |
| `distortion_coefficients` | `rows=1`, `cols`, and a numeric `data` list. plumb_bob allows 4 or 5 values, rational_polynomial 8, equidistant 4 |
| `camera_matrix` | `rows=3`, `cols=3`, nine row-major numbers |
| `rectification_matrix` | 3x3 rotation matrix, orthogonal with determinant 1 |
| `projection_matrix` | `rows=3`, `cols=4`, twelve row-major numbers |

K/P focal lengths must be positive. Every value must be finite. The last row follows the standard pinhole model. The file must match the rotation, crop and resolution the primitive actually outputs. The intrinsics interface does not resize a calibration or invent missing parameters. Depth uses its own calibration for the depth image grid.

When no intrinsics file is set, the returned CameraInfo is uncalibrated and K/R/P are zero. `tests/data/ros_camera_info.yaml` is an upstream ROS format sample. Its source and license are stored with the file. A deployment uses a measured file from this robot.

## Static extrinsics file

`extrinsics_file` uses the standard TransformStamped YAML fields:

| Field | Meaning |
| --- | --- |
| `header.frame_id` | Parent frame of the camera mount |
| `child_frame_id` | Optical frame the primitive actually outputs. It must equal the configured `frame_id` |
| `transform.translation.x/y/z` | Child origin in the parent frame, in metres |
| `transform.rotation.x/y/z/w` | Normalized quaternion of the child relative to the parent |

The transform expresses a point in the child frame into the parent frame. The static message has a zero stamp. Each gRPC subscriber receives the current configuration immediately. After the file changes, re-initialize or restart the primitive. Without a measured extrinsic the interface reports `FAILED_PRECONDITION`.

When the head camera is mounted on a head link, that real link is the parent. Motion from the head joints to `base_link` needs the URDF, joint feedback and TF. The current robot URDF does not yet include a measured camera frame.

## Configuration check

Relative `calibration_file` and `extrinsics_file` paths are resolved from the deployment root. On the R1, use the built primitive environment:

```bash
primitives/r1_depth/.venv/bin/python scripts/validate_camera_geometry.py --frame-id r1_depth_camera_optical_frame --width 544 --height 448 --calibration-file config/depth_camera_info.yaml --extrinsics-file config/depth_extrinsics.yaml
```

The command reads measured files the operator has supplied. Omitting both file arguments prints `calibrated=false` and `extrinsics_available=false`. A missing file, a bad format, a frame mismatch or a size mismatch fails the command immediately.

This library does not capture images, publish dynamic TF, or command the robot.

## Local checks

Ten checks passed on Python 3.10.22: the upstream ROS calibration format, CameraInfo serialization, the uncalibrated state, a size conflict, non-finite values, matrix shape, the rotation matrix, the extrinsic frame and the quaternion. The reference source and license are in `tests/data/`.

New capabilities were checked against the real onboard Atlas/gRPC registry. `r1_camera` and `r1_depth` both declare `intrinsics` and `extrinsics`. Without an extrinsic file they return `FAILED_PRECONDITION`.

## Onboard stream check

On 2026-10-28 the native R1 build and a live stream check completed. RGB was about 15 FPS and depth about 10.75 FPS. Each side produced seven frame stamps shared with CameraInfo. No measured intrinsics or extrinsics were supplied, and both CameraInfo messages reported uncalibrated.

From the deployment root:

```bash
primitives/r1_camera/.venv/bin/python scripts/check_camera_geometry_contracts.py --expect-unconfigured
primitives/r1_camera/.venv/bin/python scripts/check_camera_geometry_live.py --output .tools/camera-geometry/result.json
```

The stream check subscribes to both images and intrinsics. It checks the standard encoding, size, data length, frame_id, stamps and same-frame pairing, and it saves the image rate and the depth value distribution. The result file must not already exist. Each acceptance run uses a new name. The depth distribution does not verify ranging accuracy. RGB-D registration, time alignment of the two images, and a check against a known distance still have to be done.
