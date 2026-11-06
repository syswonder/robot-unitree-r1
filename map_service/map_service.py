#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""R1 local depth map + RGB-D odometry service.

This is the robot-local HTTP service the Robonix client's Perception page
expects on 127.0.0.1:50107. It:

* reads the Unitree stereo depth stream from /dev/video-dep (544x448, Y16 BE);
* reads the left RGB H.264 stream from UDP 5002 (GStreamer);
* estimates frame-to-frame camera motion with ORB features + solvePnPRansac;
* accumulates a 2D occupancy grid in a gravity-aligned floor frame;
* serves /api/state, /api/pose, /api/health and /api/calibration.

Calibration is approximate until Unitree's cam_param.txt is available. The
service never commands motion; mapping requires an operator to move the robot.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np


DEFAULT_CALIB = {
    "camera": {
        "width": 544,
        "height": 448,
        "fx": 213.5,
        "fy": 213.5,
        "cx": 272.0,
        "cy": 224.0,
        "distortion": [0.0, 0.0, 0.0, 0.0, 0.0],
        "baseline_m": 0.060,
        "source": "FOV approximation; replace with Unitree cam_param.txt",
    },
    "extrinsics": {
        "parent": "base_link",
        "child": "r1_front_camera",
        "translation_xyz": [0.0, 0.0, 0.0],
        "rotation_quat_xyzw": [0.0, 0.0, 0.0, 1.0],
        "floor_height_m": 1.2,
        "floor_mode": "auto",
        "floor_min_m": 0.5,
        "floor_max_m": 2.0,
        "status": "placeholder; map is currently expressed in the initial camera frame",
    },
}

DEFAULTS = {
    "device": "/dev/video-dep",
    "rgb_port": 5002,
    "width": 544,
    "height": 448,
    "fps": 10.0,
    "map_width": 400,
    "map_height": 400,
    "map_resolution": 0.05,
    "min_depth_mm": 500.0,
    "max_depth_mm": 6000.0,
}


def log(message):
    print("[r1_map] " + message, flush=True)


def load_calibration(path):
    calib = json.loads(json.dumps(DEFAULT_CALIB))
    if path:
        with open(path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        for section in ("camera", "extrinsics"):
            if isinstance(loaded.get(section), dict):
                calib[section].update(loaded[section])
    return calib


def camera_matrix(calib):
    cam = calib["camera"]
    return np.array(
        [
            [float(cam["fx"]), 0.0, float(cam["cx"])],
            [0.0, float(cam["fy"]), float(cam["cy"])],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def quat_to_matrix(quat):
    x, y, z, w = [float(v) for v in quat]
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if norm < 1e-9:
        return np.eye(3, dtype=np.float64)
    x, y, z, w = x / norm, y / norm, z / norm, w / norm
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def gst_pipeline(port):
    return [
        "gst-launch-1.0",
        "-q",
        "udpsrc",
        "port=%d" % int(port),
        "caps=application/x-rtp,media=video,clock-rate=90000,"
        "encoding-name=H264,payload=96",
        "!",
        "rtph264depay",
        "!",
        "avdec_h264",
        "!",
        "videoconvert",
        "!",
        "jpegenc",
        "quality=85",
        "!",
        "fdsink",
        "fd=1",
    ]


class JpegReader:
    """Decode the GStreamer JPEG stream into the latest numpy frame."""

    def __init__(self, port):
        self.port = int(port)
        self.lock = threading.Lock()
        self.frame = None
        self.stamp = None
        self.error = ""
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="rgb-reader", daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def latest(self):
        with self.lock:
            return self.frame, self.stamp, self.error

    def _run(self):
        while not self.stop_event.is_set():
            proc = None
            try:
                proc = subprocess.Popen(
                    gst_pipeline(self.port),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=0,
                )
                log("RGB pipeline on udp:%d" % self.port)
                buffer = bytearray()
                while not self.stop_event.is_set():
                    chunk = proc.stdout.read(4096)
                    if not chunk:
                        self.error = "GStreamer RGB pipeline closed"
                        break
                    buffer.extend(chunk)
                    if len(buffer) > 8 * 1024 * 1024:
                        buffer.clear()
                        self.error = "RGB JPEG buffer overflow"
                        continue
                    while True:
                        start = buffer.find(b"\xff\xd8")
                        if start < 0:
                            if len(buffer) > 1:
                                del buffer[:-1]
                            break
                        end = buffer.find(b"\xff\xd9", start + 2)
                        if end < 0:
                            if start:
                                del buffer[:start]
                            break
                        jpeg = bytes(buffer[start : end + 2])
                        del buffer[: end + 2]
                        frame = cv2.imdecode(
                            np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR
                        )
                        if frame is None:
                            continue
                        with self.lock:
                            self.frame = frame
                            self.stamp = time.monotonic()
                        self.error = ""
            except Exception as exc:
                self.error = "RGB pipeline failed: %s" % exc
                log(self.error)
            finally:
                if proc is not None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
            self.stop_event.wait(1.0)


class DepthReader:
    """Read big-endian Y16 depth frames from the v4l2loopback device."""

    def __init__(self, device, width, height):
        self.device = device
        self.width = int(width)
        self.height = int(height)
        self.frame_size = self.width * self.height * 2
        self.lock = threading.Lock()
        self.frame = None
        self.stamp = None
        self.error = ""
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="depth-reader", daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def latest(self):
        with self.lock:
            return self.frame, self.stamp, self.error

    def _run(self):
        period = 1.0 / 10.0
        while not self.stop_event.is_set():
            fd = None
            try:
                fd = os.open(self.device, os.O_RDWR | os.O_NONBLOCK)
                self.error = ""
                while not self.stop_event.is_set():
                    try:
                        data = os.read(fd, self.frame_size)
                    except BlockingIOError:
                        self.stop_event.wait(period)
                        continue
                    except OSError as exc:
                        self.error = "depth read failed: %s" % exc
                        break
                    if len(data) != self.frame_size:
                        self.stop_event.wait(period)
                        continue
                    frame = np.frombuffer(data, dtype=">u2").reshape(
                        self.height, self.width
                    ).copy()
                    with self.lock:
                        self.frame = frame
                        self.stamp = time.monotonic()
            except FileNotFoundError:
                self.error = "%s does not exist" % self.device
            except OSError as exc:
                self.error = "cannot open %s: %s" % (self.device, exc)
            finally:
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
            if self.error:
                log(self.error + "; retrying")
            self.stop_event.wait(1.0)


def fit_plane(points):
    """RANSAC + SVD floor plane. Returns (normal, d) with n . x + d = 0.

    A floor in the camera frame is approximately horizontal: its normal is
    mostly camera y (down), not camera x/z. If the visible depth frame has no
    floor support (textureless floors are common on the R1), return None so
    the caller can use the level-camera prior instead of fitting a wall.
    """
    if len(points) < 100:
        return None
    sample = points[:: max(1, len(points) // 6000)]
    # The floor is below the camera: keep points with positive camera y and a
    # sane forward distance. Do not fall back to all points here: a wall is
    # not a floor, and fitting one produces a skewed map frame.
    candidates = sample[
        (sample[:, 1] > 0.05)
        & (sample[:, 1] < 3.0)
        & (sample[:, 2] > 0.3)
        & (sample[:, 2] < 8.0)
    ]
    if len(candidates) < 100:
        return None
    best_inliers = None
    rng = np.random.default_rng(7)
    for _ in range(400):
        idx = rng.choice(len(candidates), 3, replace=False)
        p0, p1, p2 = candidates[idx]
        normal = np.cross(p1 - p0, p2 - p0)
        norm = np.linalg.norm(normal)
        if norm < 1e-9:
            continue
        normal = normal / norm
        # Reject walls/ceilings and steeply tilted surfaces.
        if abs(float(normal[1])) < 0.8 or abs(float(normal[2])) > 0.25:
            continue
        d = -float(np.dot(normal, p0))
        if d <= 0:
            normal = -normal
            d = -d
        distance = np.abs(candidates @ normal + d)
        inliers = distance < 0.04
        count = int(inliers.sum())
        if best_inliers is None or count > int(best_inliers.sum()):
            best_inliers = inliers
    if best_inliers is None or int(best_inliers.sum()) < 100:
        return None
    inlier_points = candidates[best_inliers]
    centroid = inlier_points.mean(axis=0)
    covariance = (inlier_points - centroid).T @ (inlier_points - centroid)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    normal = eigenvectors[:, int(np.argmin(eigenvalues))]
    normal = normal / np.linalg.norm(normal)
    if abs(float(normal[1])) < 0.8 or abs(float(normal[2])) > 0.25:
        return None
    d = -float(np.dot(normal, centroid))
    if d < 0:  # camera origin is above the floor -> positive side
        normal = -normal
        d = -d
    return normal, d


def rot_angle(rotation):
    value = (np.trace(rotation) - 1.0) / 2.0
    return math.acos(max(-1.0, min(1.0, value)))


class MapService:
    def __init__(self, args):
        self.args = args
        self.calib = load_calibration(args.config)
        self.K = camera_matrix(self.calib)
        self.fx = float(self.calib["camera"]["fx"])
        self.fy = float(self.calib["camera"]["fy"])
        self.cx = float(self.calib["camera"]["cx"])
        self.cy = float(self.calib["camera"]["cy"])
        self.width = int(self.calib["camera"].get("width", args.width))
        self.height = int(self.calib["camera"].get("height", args.height))
        self.min_depth_mm = float(args.min_depth_mm)
        self.max_depth_mm = float(args.max_depth_mm)

        extr = self.calib.get("extrinsics", {})
        self.apply_extrinsics = bool(extr.get("apply", True))
        self.R_base_camera = quat_to_matrix(
            extr.get("rotation_quat_xyzw", [0.0, 0.0, 0.0, 1.0])
        )
        self.t_base_camera = np.array(
            extr.get("translation_xyz", [0.0, 0.0, 0.0]), dtype=np.float64
        )
        self.floor_height_m = float(extr.get("floor_height_m", 1.2))
        self.floor_mode = str(extr.get("floor_mode", "auto")).strip().lower()
        self.floor_min_m = float(extr.get("floor_min_m", 0.5))
        self.floor_max_m = float(extr.get("floor_max_m", 2.0))

        self.lock = threading.Lock()
        self.depth = DepthReader(args.device, self.width, self.height)
        self.rgb = JpegReader(args.rgb_port)

        self.map_ready = False
        self.map_width = int(args.map_width)
        self.map_height = int(args.map_height)
        self.resolution = float(args.map_resolution)
        self.origin_x = -self.map_width * self.resolution / 2.0
        self.origin_y = -self.map_height * self.resolution / 2.0
        self.grid = np.zeros((self.map_height, self.map_width), dtype=np.uint8)
        self.occupied = np.zeros_like(self.grid, dtype=bool)
        self.free = np.zeros_like(self.grid, dtype=bool)

        self.plane_normal = None
        self.plane_d = None
        self.plane_origin = None
        self.plane_forward = None
        self.plane_left = None

        self.prev_gray = None
        self.prev_kp = None
        self.prev_desc = None
        self.prev_points = None
        self.T_initial_prev = np.eye(4, dtype=np.float64)
        self.T_initial_curr = np.eye(4, dtype=np.float64)
        self.pose = {"x": 0.0, "y": 0.0, "z": 0.0, "yaw": 0.0, "frame": "map"}
        self.processed_depth_stamp = None
        self.frames = 0
        self.last_error = ""
        self.orb = cv2.ORB_create(
            nfeatures=500,
            scaleFactor=1.2,
            nlevels=8,
            edgeThreshold=15,
            patchSize=15,
            fastThreshold=10,
        )
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="mapper", daemon=True)

    def start(self):
        self.depth.start()
        self.rgb.start()
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def _points_from_depth(self, depth, gray_points=None):
        if gray_points is None:
            ys, xs = np.mgrid[0 : self.height : 2, 0 : self.width : 2]
            z_mm = depth[ys, xs].astype(np.float32)
            mask = (z_mm >= self.min_depth_mm) & (z_mm <= self.max_depth_mm)
            ys = ys[mask].astype(np.float32)
            xs = xs[mask].astype(np.float32)
            z = z_mm[mask] / 1000.0
            if len(z) == 0:
                return np.zeros((0, 3), dtype=np.float32)
            x = (xs - self.cx) * z / self.fx
            y = (ys - self.cy) * z / self.fy
            return np.stack([x, y, z], axis=1)

        # Keypoint mode: keep the array aligned with keypoint indices and use
        # NaN for keypoints without a valid depth sample.
        xs = gray_points[:, 0].astype(np.float32)
        ys = gray_points[:, 1].astype(np.float32)
        z = np.zeros(len(xs), dtype=np.float32)
        for i, (x, y) in enumerate(zip(xs, ys)):
            xi, yi = int(round(x)), int(round(y))
            patch = depth[max(0, yi - 1) : yi + 2, max(0, xi - 1) : xi + 2]
            values = patch[
                (patch >= self.min_depth_mm) & (patch <= self.max_depth_mm)
            ]
            z[i] = float(np.median(values)) / 1000.0 if len(values) else 0.0
        points = np.full((len(xs), 3), np.nan, dtype=np.float32)
        valid = z > 0
        points[valid, 0] = (xs[valid] - self.cx) * z[valid] / self.fx
        points[valid, 1] = (ys[valid] - self.cy) * z[valid] / self.fy
        points[valid, 2] = z[valid]
        return points

    def _init_map_frame(self, points):
        plane = fit_plane(points)
        if plane is not None:
            _, plane_distance = plane
            # The head camera is roughly 1.2 m above the floor. A "floor"
            # 13 cm below the camera is usually a table/shelf or the robot's
            # own body; reject implausible plane distances.
            if not (self.floor_min_m <= plane_distance <= self.floor_max_m):
                log(
                    "floor plane rejected at %.2fm (expected %.2f-%.2fm)"
                    % (plane_distance, self.floor_min_m, self.floor_max_m)
                )
                plane = None
        if plane is None:
            if self.floor_mode == "plane":
                self.last_error = "floor plane not found"
                return False
            # The R1 floor is often white/textureless and produces no stereo
            # depth. A level-camera prior is safer than fitting a wall: the
            # robot is upright and the head camera is approximately forward
            # looking. floor_height_m is the camera height above the floor.
            normal = np.array([0.0, -1.0, 0.0], dtype=np.float64)
            d = self.floor_height_m
            origin = -d * normal
            forward = np.array([0.0, 0.0, 1.0], dtype=np.float64)
            left = np.cross(normal, forward)
            left = left / np.linalg.norm(left)
            log(
                "floor plane not found; using level prior height=%.2fm"
                % self.floor_height_m
            )
        else:
            normal, d = plane
            origin = -d * normal
            camera_z = np.array([0.0, 0.0, 1.0])
            forward = camera_z - np.dot(camera_z, normal) * normal
            if np.linalg.norm(forward) < 1e-6:
                forward = np.array([1.0, 0.0, 0.0]) - normal[0] * normal
            forward = forward / np.linalg.norm(forward)
            left = np.cross(normal, forward)
            left = left / np.linalg.norm(left)
        if self.apply_extrinsics:
            normal = self.R_base_camera @ normal
            origin = self.R_base_camera @ origin + self.t_base_camera
            forward = self.R_base_camera @ forward
            left = self.R_base_camera @ left
            d = -float(np.dot(normal, origin))
        self.plane_normal = normal
        self.plane_d = d
        self.plane_origin = origin
        self.plane_forward = forward
        self.plane_left = left
        self.map_ready = True
        log(
            "map frame ready: normal=%s origin=%s"
            % (np.round(normal, 3).tolist(), np.round(origin, 3).tolist())
        )
        return True

    def _to_map(self, points):
        if self.apply_extrinsics:
            points = points @ self.R_base_camera.T + self.t_base_camera
        relative = points - self.plane_origin
        return np.stack(
            [
                relative @ self.plane_forward,
                relative @ self.plane_left,
                relative @ self.plane_normal,
            ],
            axis=1,
        )

    def _add_points(self, points, transform):
        if not self.map_ready or len(points) == 0:
            return
        world = points @ transform[:3, :3].T + transform[:3, 3]
        self._update_grid(self._to_map(world))

    def _update_grid(self, points_map):
        if len(points_map) == 0:
            return
        # Height above the floor: ignore the floor itself and points that are
        # too high to matter for a 2D footprint. 2.5 m covers the R1 torso and
        # the shelves/curtains in front of the head camera.
        mask = (points_map[:, 2] > 0.05) & (points_map[:, 2] < 2.5)
        points = points_map[mask]
        if len(points) == 0:
            return
        cells_x = np.floor((points[:, 0] - self.origin_x) / self.resolution).astype(
            np.int32
        )
        cells_y = np.floor((points[:, 1] - self.origin_y) / self.resolution).astype(
            np.int32
        )
        valid = (
            (cells_x >= 0)
            & (cells_x < self.map_width)
            & (cells_y >= 0)
            & (cells_y < self.map_height)
        )
        if not valid.any():
            return
        with self.lock:
            self.occupied[cells_y[valid], cells_x[valid]] = True
        # Do not draw a free-space ray to every point: a sparse depth frame
        # turns that into a radial starburst instead of a usable occupancy
        # outline. Free-space rendering can be added back as a separate layer
        # once the depth stream is dense/stable.

    def _update_pose(self, gray, depth):
        # Retry map-frame initialization until a floor (or the level prior)
        # succeeds. Previously a bad first frame permanently disabled mapping.
        if not self.map_ready and not self._init_map_frame(
            self._points_from_depth(depth)
        ):
            self.last_error = "floor plane not found; waiting for a valid frame"
            return False

        # The head camera is fixed and can drift for minutes while the robot
        # is static; ORB matches between far-apart frames become unreliable.
        # Keep a shorter feature history and add every frame's depth points.
        keypoints, descriptors = self.orb.detectAndCompute(gray, None)
        if descriptors is None or len(keypoints) < 30:
            self.last_error = "not enough ORB features"
            return False
        pixels = np.array([kp.pt for kp in keypoints], dtype=np.float32)
        points = self._points_from_depth(depth, pixels)
        valid = ~np.isnan(points).any(axis=1)
        valid_points = points[valid]
        if len(valid_points) < 20:
            self.last_error = "not enough valid depth points"
            return False

        if self.prev_desc is None:
            self.prev_gray = gray
            self.prev_kp = keypoints
            self.prev_desc = descriptors
            self.prev_points = points
            self._add_points(valid_points, self.T_initial_prev)
            return True

        matches = self.matcher.knnMatch(self.prev_desc, descriptors, k=2)
        good = []
        for pair in matches:
            if len(pair) == 2 and pair[0].distance < 0.75 * pair[1].distance:
                good.append(pair[0])
        if len(good) < 20:
            self.last_error = "not enough feature matches"
            # Still add this frame's points; a static robot's map should not
            # stall just because ORB could not match a distant previous frame.
            self._add_points(valid_points, self.T_initial_prev)
            self.prev_gray, self.prev_kp, self.prev_desc, self.prev_points = (
                gray,
                keypoints,
                descriptors,
                points,
            )
            return True

        object_points = []
        image_points = []
        for match in good:
            prev_index = match.queryIdx
            if prev_index >= len(self.prev_points):
                continue
            prev_point = self.prev_points[prev_index]
            if not np.isfinite(prev_point).all():
                continue
            object_points.append(prev_point)
            image_points.append(keypoints[match.trainIdx].pt)
        if len(object_points) < 20:
            self.last_error = "not enough 3D-2D correspondences"
            self._add_points(valid_points, self.T_initial_prev)
            self.prev_gray, self.prev_kp, self.prev_desc, self.prev_points = (
                gray,
                keypoints,
                descriptors,
                points,
            )
            return True

        ok, rvec, tvec, inliers = cv2.solvePnPRansac(
            np.asarray(object_points, dtype=np.float64),
            np.asarray(image_points, dtype=np.float64),
            self.K,
            None,
            iterationsCount=150,
            reprojectionError=5.0,
            confidence=0.99,
            flags=cv2.SOLVEPNP_EPNP,
        )
        if not ok or inliers is None or len(inliers) < 15:
            self.last_error = "PnP failed; mapping with last pose"
            self._add_points(valid_points, self.T_initial_prev)
            self.prev_gray, self.prev_kp, self.prev_desc, self.prev_points = (
                gray,
                keypoints,
                descriptors,
                points,
            )
            return True

        rotation, _ = cv2.Rodrigues(rvec)
        T_prev_curr = np.eye(4, dtype=np.float64)
        T_prev_curr[:3, :3] = rotation
        T_prev_curr[:3, 3] = tvec.reshape(3)
        try:
            T_curr_prev = np.linalg.inv(T_prev_curr)
        except np.linalg.LinAlgError:
            self.last_error = "singular PnP transform"
            self._add_points(valid_points, self.T_initial_prev)
            return False
        candidate = self.T_initial_prev @ T_curr_prev
        translation = float(np.linalg.norm(candidate[:3, 3] - self.T_initial_prev[:3, 3]))
        angle = rot_angle(candidate[:3, :3] @ self.T_initial_prev[:3, :3].T)
        if translation > 1.0 or angle > math.radians(45.0):
            self.last_error = "pose jump rejected; mapping with last pose"
            self._add_points(valid_points, self.T_initial_prev)
            self.prev_gray, self.prev_kp, self.prev_desc, self.prev_points = (
                gray,
                keypoints,
                descriptors,
                points,
            )
            return True
        if translation < 0.01 and angle < math.radians(0.5):
            candidate = self.T_initial_prev.copy()
        self.T_initial_curr = candidate
        self.T_initial_prev = candidate
        self.pose = self._pose_from_transform(candidate)
        self._add_points(valid_points, candidate)

        self.prev_gray = gray
        self.prev_kp = keypoints
        self.prev_desc = descriptors
        self.prev_points = points
        return True

    def _pose_from_transform(self, transform):
        camera = transform[:3, 3]
        xyz = self._to_map(camera.reshape(1, 3))[0] if self.map_ready else camera
        forward = transform[:3, :3] @ np.array([0.0, 0.0, 1.0])
        if self.apply_extrinsics:
            forward = self.R_base_camera @ forward
        if self.map_ready:
            fx = float(np.dot(forward, self.plane_forward))
            fy = float(np.dot(forward, self.plane_left))
            yaw = math.atan2(fy, fx)
        else:
            yaw = 0.0
        return {
            "x": float(xyz[0]),
            "y": float(xyz[1]),
            "z": float(xyz[2]),
            "yaw": float(yaw),
            "frame": "map",
        }

    def _run(self):
        period = 1.0 / max(1.0, float(self.args.fps))
        while not self.stop_event.is_set():
            depth, depth_stamp, depth_error = self.depth.latest()
            rgb, rgb_stamp, rgb_error = self.rgb.latest()
            now = time.monotonic()
            if (
                depth is None
                or rgb is None
                or depth_stamp is None
                or rgb_stamp is None
                or depth_stamp == self.processed_depth_stamp
                or now - depth_stamp > 1.0
                or now - rgb_stamp > 1.0
            ):
                self.last_error = depth_error or rgb_error or "waiting for streams"
                self.stop_event.wait(period)
                continue
            self.processed_depth_stamp = depth_stamp
            gray = cv2.cvtColor(rgb, cv2.COLOR_BGR2GRAY)
            try:
                if self._update_pose(gray, depth):
                    self.frames += 1
            except Exception as exc:
                self.last_error = "mapper exception: %s" % exc
                log(self.last_error)
            self.stop_event.wait(period)

    def _render_png(self):
        x0, y0 = 0, 0
        x1, y1 = self.map_width, self.map_height
        if self.occupied.any():
            ys, xs = np.where(self.occupied)
            margin = 15
            x0 = max(0, int(xs.min()) - margin)
            x1 = min(self.map_width, int(xs.max()) + margin + 1)
            y0 = max(0, int(ys.min()) - margin)
            y1 = min(self.map_height, int(ys.max()) + margin + 1)
        image = np.zeros((y1 - y0, x1 - x0), dtype=np.uint8)
        image[self.free[y0:y1, x0:x1]] = 70
        image[self.occupied[y0:y1, x0:x1]] = 255
        occupied = self.occupied[y0:y1, x0:x1].astype(np.uint8)
        if occupied.any():
            occupied = cv2.dilate(occupied, np.ones((2, 2), np.uint8))
            image[occupied.astype(bool)] = 255
        ok, encoded = cv2.imencode(".png", image[::-1])
        if not ok:
            return None
        return (
            base64.b64encode(encoded.tobytes()).decode("ascii"),
            self.origin_x + x0 * self.resolution,
            self.origin_y + y0 * self.resolution,
            x1 - x0,
            y1 - y0,
        )

    def state(self):
        with self.lock:
            rendered = self._render_png() if self.map_ready else None
            png = rendered[0] if rendered else None
            return {
                "ok": bool(self.map_ready and png),
                "occupancy": {
                    "png_b64": png or "",
                    "width": rendered[3] if rendered else self.map_width,
                    "height": rendered[4] if rendered else self.map_height,
                    "resolution": self.resolution,
                    "origin_x": rendered[1] if rendered else self.origin_x,
                    "origin_y": rendered[2] if rendered else self.origin_y,
                },
                "pose": dict(self.pose),
                "calibration": {
                    "intrinsics": dict(self.calib["camera"]),
                    "extrinsics": dict(self.calib["extrinsics"]),
                },
                "stats": {
                    "frames": self.frames,
                    "occupied_cells": int(self.occupied.sum()),
                    "free_cells": int(self.free.sum()),
                    "error": self.last_error,
                },
            }


class Handler(BaseHTTPRequestHandler):
    service = None

    def _send(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.service is None:
            self._send({"ok": False, "error": "service not ready"}, 503)
            return
        if self.path.startswith("/api/state"):
            self._send(self.service.state())
        elif self.path.startswith("/api/pose"):
            self._send({"ok": True, "pose": self.service.pose})
        elif self.path.startswith("/api/calibration"):
            self._send(
                {
                    "ok": True,
                    "intrinsics": self.service.calib["camera"],
                    "extrinsics": self.service.calib["extrinsics"],
                }
            )
        elif self.path.startswith("/api/health"):
            self._send(
                {
                    "ok": True,
                    "map_ready": self.service.map_ready,
                    "frames": self.service.frames,
                    "error": self.service.last_error,
                }
            )
        else:
            self._send({"ok": False, "error": "not found"}, 404)

    def log_message(self, fmt, *args):
        return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="")
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=50107)
    parser.add_argument("--device", default=DEFAULTS["device"])
    parser.add_argument("--rgb-port", type=int, default=DEFAULTS["rgb_port"])
    parser.add_argument("--width", type=int, default=DEFAULTS["width"])
    parser.add_argument("--height", type=int, default=DEFAULTS["height"])
    parser.add_argument("--fps", type=float, default=DEFAULTS["fps"])
    parser.add_argument("--map-width", type=int, default=DEFAULTS["map_width"])
    parser.add_argument("--map-height", type=int, default=DEFAULTS["map_height"])
    parser.add_argument(
        "--map-resolution", type=float, default=DEFAULTS["map_resolution"]
    )
    parser.add_argument("--min-depth-mm", type=float, default=DEFAULTS["min_depth_mm"])
    parser.add_argument("--max-depth-mm", type=float, default=DEFAULTS["max_depth_mm"])
    args = parser.parse_args()

    service = MapService(args)
    Handler.service = service
    server = ThreadingHTTPServer((args.listen, args.port), Handler)
    log(
        "listening on http://%s:%d (map %dx%d @ %.2fm)"
        % (args.listen, args.port, args.map_width, args.map_height, args.map_resolution)
    )
    service.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        service.stop()
        server.server_close()


if __name__ == "__main__":
    main()
