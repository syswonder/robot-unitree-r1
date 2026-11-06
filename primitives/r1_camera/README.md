# R1 camera interfaces

| Capability | Transport | Data |
| --- | --- | --- |
| `robonix/primitive/camera/rgb` | gRPC stream | `sensor_msgs/Image`, raw `rgb8` pixels, step is width times 3 |
| `robonix/primitive/camera/intrinsics` | gRPC stream | `sensor_msgs/CameraInfo`, so a late client can read the current calibration |
| `robonix/primitive/camera/extrinsics` | gRPC stream | Static mount `geometry_msgs/TransformStamped`. Each late subscriber can read the configured value |
| `robonix/primitive/camera/snapshot` | MCP | JPEG snapshot for the web client and models |

The main deployment uses the official Unitree H.264 RTP image on port 5001. GStreamer receives and rotates it, PyAV splits MJPEG, and Pillow decodes raw RGB. The official `videohub` API 1001 `GetImageSample` is also supported. The input and the streamed output share the latest image. Each subscriber receives only new frames. The stamp is the time the R1 received the frame.

Receive the stereo image after the app turns `video_hub` off and `Stereo patch PC1` on. Official ports are 5001 img, 5002 left and 5003 right. One process owns a UDP port. The local map service uses 5002, so do not start a second receiver for it.

Settings are in `config.spec`. The default optical frame is `r1_front_camera_optical_frame`, with axes right, down and forward. The mount transform into the body still has to be measured and added to the URDF. Output rotation and resolution must match the calibration file.

`calibration_file` is a standard ROS camera_info YAML: `image_width`, `image_height`, `distortion_model`, `distortion_coefficients`, `camera_matrix`, `rectification_matrix` and `projection_matrix`. Relative paths are from the deployment directory. When unset, D/K/R/P are zero, which means uncalibrated. The local map's FOV approximation is not used as intrinsics. Device parameters are downloaded from the official page on port 9080, then checked for format, image rotation and pixel geometry before writing the YAML.

The shared `r1_sensor_geometry` library loads the calibration and checks image size, matrix shape, finite values, focal length, distortion coefficients and the rotation matrix. The intrinsics stream stamps the current valid image. An expired cache returns `UNAVAILABLE`. A calibration that does not match the output size returns `FAILED_PRECONDITION`.

`extrinsics_file` is a standard TransformStamped YAML: `header.frame_id`, `child_frame_id`, `transform.translation.{x,y,z}` and `transform.rotation.{x,y,z,w}`. The child must equal `frame_id`. Translation is in metres. The quaternion must be normalized. The static transform has a zero stamp because the mount does not depend on capture time. Without a measured file the extrinsics interface returns `FAILED_PRECONDITION`. Format and the local check are in [sensor geometry](../../common/r1_sensor_geometry/README.md).

RGB and depth currently use separate optical frames. Registration, synchronization and a complete TF tree are not done. This interface is the gRPC data plane. The ROS 2 data plane used by Robonix Scene still needs its own wiring.

From the deployment directory, `rbnx build -p primitives/r1_camera`. The full-stack script starts it. Dependencies are GStreamer, PyAV 16.0.1, Pillow 11.3.0, the Unitree SDK, the Robonix API and the shared geometry library. Missing input, stale data and decode errors are reported directly. Shutdown stops the image process and the reader thread.

Official reference: [R1 video stream service](https://support.unitree.com/home/zh/R1_developer/video_service).
