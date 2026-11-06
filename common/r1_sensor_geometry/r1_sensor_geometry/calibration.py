from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml


def positive_integer(value, name):
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def vector(values, count, name):
    if not isinstance(values, list) or len(values) != count:
        raise ValueError(f"{name} must contain {count} numbers")
    if any(type(value) not in (int, float) for value in values):
        raise ValueError(f"{name} must contain only numbers")
    result = np.asarray(values, dtype=float)
    if not np.isfinite(result).all():
        raise ValueError(f"{name} contains a non-finite value")
    return result


def matrix(document, name, rows, cols):
    value = document[name]
    if (not isinstance(value, dict) or type(value.get("rows")) is not int or type(value.get("cols")) is not int
            or value["rows"] != rows or value["cols"] != cols):
        raise ValueError(f"{name} rows/cols must be {rows}/{cols}")
    return vector(value["data"], rows * cols, name).reshape(rows, cols)


def frame_name(value, name):
    if not isinstance(value, str) or not value or value != value.strip() or any(character.isspace() for character in value):
        raise ValueError(f"{name} must be a frame name without whitespace")
    return value


@dataclass(frozen=True)
class CameraCalibration:
    width: int
    height: int
    distortion_model: str
    d: tuple
    k: tuple
    r: tuple
    p: tuple

    @classmethod
    def from_file(cls, path):
        document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError("camera calibration must be a ROS camera_info YAML mapping")
        width = positive_integer(document["image_width"], "image_width")
        height = positive_integer(document["image_height"], "image_height")
        model = document["distortion_model"]
        counts = {"plumb_bob": (4, 5), "rational_polynomial": (8,), "equidistant": (4,)}
        if model not in counts:
            raise ValueError("unsupported distortion_model")
        coefficients = document["distortion_coefficients"]
        if not isinstance(coefficients, dict) or type(coefficients.get("cols")) is not int:
            raise ValueError("distortion_coefficients is missing its matrix size")
        count = coefficients["cols"]
        if count not in counts[model]:
            raise ValueError("the distortion coefficient count does not match distortion_model")
        d = matrix(document, "distortion_coefficients", 1, count).ravel()
        k = matrix(document, "camera_matrix", 3, 3)
        r = matrix(document, "rectification_matrix", 3, 3)
        p = matrix(document, "projection_matrix", 3, 4)
        if k[0, 0] <= 0 or k[1, 1] <= 0 or p[0, 0] <= 0 or p[1, 1] <= 0:
            raise ValueError("K/P focal lengths must be positive")
        if not np.allclose(k[2], [0, 0, 1], atol=1e-8, rtol=0) or not np.allclose(p[2], [0, 0, 1, 0], atol=1e-8, rtol=0):
            raise ValueError("the last row of K/P does not match the pinhole camera model")
        if not np.allclose(r.T @ r, np.eye(3), atol=1e-5, rtol=0) or not np.isclose(np.linalg.det(r), 1, atol=1e-5, rtol=0):
            raise ValueError("rectification_matrix must be a rotation matrix")
        return cls(width, height, model, tuple(d), tuple(k.ravel()), tuple(r.ravel()), tuple(p.ravel()))

    def check_size(self, width, height):
        if (width, height) != (self.width, self.height):
            raise ValueError("calibration size does not match the current output image; use a calibration for this rotation, crop and resolution")


@dataclass(frozen=True)
class CameraMount:
    parent_frame: str
    child_frame: str
    translation_xyz: tuple
    quaternion_xyzw: tuple

    @classmethod
    def from_file(cls, path, expected_child):
        document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError("camera extrinsics must be a TransformStamped YAML mapping")
        parent = frame_name(document["header"]["frame_id"], "header.frame_id")
        child = frame_name(document["child_frame_id"], "child_frame_id")
        if parent == child or child != expected_child:
            raise ValueError("extrinsic child_frame_id must equal the output optical frame and differ from the parent")
        transform = document["transform"]
        translation = vector([transform["translation"][axis] for axis in ("x", "y", "z")], 3, "translation")
        quaternion = vector([transform["rotation"][axis] for axis in ("x", "y", "z", "w")], 4, "rotation")
        if not np.isclose(np.linalg.norm(quaternion), 1, atol=1e-6, rtol=0):
            raise ValueError("the extrinsic quaternion must be normalized, in x,y,z,w order")
        return cls(parent, child, tuple(translation), tuple(quaternion))

    def message(self):
        import geometry_msgs_pb2

        value = geometry_msgs_pb2.TransformStamped()
        value.header.frame_id = self.parent_frame
        value.child_frame_id = self.child_frame
        value.transform.translation.x, value.transform.translation.y, value.transform.translation.z = self.translation_xyz
        (value.transform.rotation.x, value.transform.rotation.y,
         value.transform.rotation.z, value.transform.rotation.w) = self.quaternion_xyzw
        return value


def camera_info(calibration, width, height, frame_id, stamp_ns):
    import sensor_msgs_pb2

    positive_integer(width, "width")
    positive_integer(height, "height")
    frame_name(frame_id, "frame_id")
    if type(stamp_ns) is not int or stamp_ns < 0:
        raise ValueError("the image stamp must be a non-negative integer number of nanoseconds")
    message = sensor_msgs_pb2.CameraInfo(width=width, height=height)
    message.header.frame_id = frame_id
    message.header.stamp.sec = stamp_ns // 1_000_000_000
    message.header.stamp.nanosec = stamp_ns % 1_000_000_000
    if calibration is None:
        message.k.extend([0.0] * 9)
        message.r.extend([0.0] * 9)
        message.p.extend([0.0] * 12)
    else:
        calibration.check_size(width, height)
        message.distortion_model = calibration.distortion_model
        message.d.extend(calibration.d)
        message.k.extend(calibration.k)
        message.r.extend(calibration.r)
        message.p.extend(calibration.p)
    return message


def load_geometry(config, deployment_root, frame_id, width=None, height=None):
    frame_name(frame_id, "frame_id")
    if (width is None) != (height is None):
        raise ValueError("width and height must be provided together")
    if width is not None:
        positive_integer(width, "width")
        positive_integer(height, "height")

    def resolve(name):
        raw = config.get(name, "")
        if not isinstance(raw, str):
            raise ValueError(f"{name} must be a path string")
        if not raw:
            return None
        path = Path(raw)
        return path if path.is_absolute() else Path(deployment_root) / path

    calibration_path = resolve("calibration_file")
    extrinsics_path = resolve("extrinsics_file")
    calibration = CameraCalibration.from_file(calibration_path) if calibration_path is not None else None
    mount = CameraMount.from_file(extrinsics_path, frame_id) if extrinsics_path is not None else None
    if calibration is not None and width is not None and height is not None:
        calibration.check_size(width, height)
    return calibration, mount
