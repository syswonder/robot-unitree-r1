# R1 local map service

Standalone robot-local HTTP service for the Robonix Web client's Perception
page. It listens on `127.0.0.1:50107` and serves the occupancy-grid contract
that the client expects from the robot's map service.

## Inputs

- Depth: `/dev/video-dep` (544x448 Y16 **big-endian** millimetres), fed by
  Unitree's `depth_client`;
- Left RGB: UDP 5002 (H.264), decoded by GStreamer;
- Calibration: `config/camera_calibration.json` (currently an FOV
  approximation; replace with `cam_param.txt` when available).

## Processing

- ORB features on the left RGB frame;
- 3D points from depth at those features;
- frame-to-frame `solvePnPRansac` for camera odometry;
- floor-plane RANSAC on the first frame to define a gravity-aligned map frame;
- 2D occupancy accumulation (20 m x 20 m at 0.05 m/cell by default).

The service is read-only and never commands motion. Mapping with useful
coverage requires an operator to move the robot slowly while it runs.

## Endpoints

- `GET /api/state` — occupancy PNG, origin, resolution, pose, stats (the Web
  client's map probe);
- `GET /api/pose` — current map-frame camera pose;
- `GET /api/calibration` — active intrinsics/extrinsics;
- `GET /api/health` — stream/map diagnostics.

## Run

```bash
./run.sh
# or explicitly use the system interpreter:
/usr/bin/python3 map_service.py --config ../config/camera_calibration.json
```

Logs go to stdout. Use `/usr/bin/python3` (system Python 3.8 with OpenCV 4.2
from ROS Noetic); `python3` on `PATH` may resolve to the offline CPython 3.10
toolchain, which does not have `cv2`. GStreamer plugins `avdec_h264` and
`jpegenc` are required.

## Calibration status

The intrinsics in `camera_calibration.json` are approximate. The official
stereo calibration download is at `http://192.168.123.161:9080`
(`cam_param.txt`), which is currently closed. Do not treat the map as a
survey-grade metric map until the real intrinsics and extrinsics are loaded.
