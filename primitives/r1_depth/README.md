# R1 depth interfaces

`robonix/primitive/camera/depth` streams a standard `sensor_msgs/Image` over gRPC, little-endian `32FC1`, in metres. Raw values 0 and 65535 are invalid measurements and become NaN. Step is the width times 4. The stamp is the time the R1 host read the device frame. A subscriber receives only new frames. The default optical frame is `r1_depth_camera_optical_frame`. The stream keeps every valid metric depth. It is not clipped to the grayscale snapshot display range.

Images come from the official depth device. The current R1 client is read as big-endian uint16 millimetres. Another client version can select `byte_order` `little` or `big`. RGB-D registration, time sync and the camera mount TF are not done. The full settings are in `config.spec`.

`camera/intrinsics` publishes `sensor_msgs/CameraInfo` for the current depth image grid. The optical frame and stamp follow the valid depth frame. `calibration_file` is a separate ROS camera_info YAML whose size must equal the depth output. Without it, K/R/P are zero, which means uncalibrated. A real calibration still needs RGB-D registration.

`camera/extrinsics` publishes a static `TransformStamped`. The `extrinsics_file` child must equal the depth `frame_id`. Without a measured extrinsic the call returns `FAILED_PRECONDITION`. Both interfaces share the strict checks in `r1_sensor_geometry`. Fields and the local check are in [sensor geometry](../../common/r1_sensor_geometry/README.md).

The read-only snapshot provider reads the latest 544x448 Y16 frame from `/dev/video-dep` (the v4l2loopback device fed by Unitree's `depth_client`) and exposes `robonix/primitive/camera/depth_snapshot` as an MCP tool. The file is read as big-endian uint16 millimetres (the stereo module's network byte order). Decoding it as native little-endian gives implausible 1-90 mm values. The returned image is an 8-bit grayscale PNG. Near objects are bright. Pixels outside the configured display range are black.

Missing or stale data makes the standard stream return `UNAVAILABLE`. Pillow encodes the snapshot. After shutdown, the reader thread stops and closes the device descriptor it owns.

## Enable the depth stream

Official Unitree R1 video service steps:

1. In the Unitree app, open **Settings -> Service Status**.
2. Turn off `video_hub` (it conflicts with the stereo service).
3. Enable `Stereo patch PC1` (it is not auto-start by default).
4. On the NX, run `sudo unitree_depth_start`; or run the client directly:
   `/unitree/module/system_patch_pc4/depth_client/client 192.168.123.161 5000 /dev/video-dep`
5. Verify: `v4l2-ctl -d /dev/video-dep --get-fmt-video` or
   `ffplay -f v4l2 -framerate 10 -video_size 544x448 -i /dev/video-dep`.

Configuration:

```yaml
config:
  device: /dev/video-dep
  width: 544
  height: 448
  fps: 10.0
  stale_after_s: 2.0
  min_depth_mm: 200.0
  max_depth_mm: 10000.0
```

Build (R1, offline wheels):

```bash
export RBNX_OFFLINE_WHEELS="$HOME/r1-robonix-bootstrap/wheels"
rbnx build -p primitives/r1_depth --no-update-check
```
