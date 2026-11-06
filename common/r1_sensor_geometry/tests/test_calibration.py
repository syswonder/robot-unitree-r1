from pathlib import Path
import time
import xml.etree.ElementTree as ET

import numpy as np
import pytest
import yaml

import sensor_msgs_pb2

from r1_sensor_geometry import CameraCalibration, CameraMount, camera_info, load_geometry

DATA = Path(__file__).parent / "data/ros_camera_info.yaml"
DEPLOYMENT = Path(__file__).resolve().parents[3]


def test_ros_reference_and_protobuf_roundtrip():
    calibration = CameraCalibration.from_file(DATA)
    stamp = time.time_ns()
    message = camera_info(calibration, 640, 480, "reference_optical_frame", stamp)
    decoded = sensor_msgs_pb2.CameraInfo.FromString(message.SerializeToString())
    assert decoded.k[0] == 1168.68
    assert decoded.distortion_model == "plumb_bob"
    assert decoded.width == 640 and decoded.height == 480
    assert decoded.header.stamp.sec * 1_000_000_000 + decoded.header.stamp.nanosec == stamp
    np.testing.assert_array_equal(decoded.r, calibration.r)
    with pytest.raises(ValueError, match="标定尺寸"):
        camera_info(calibration, 480, 640, "reference_optical_frame", stamp)


def test_uncalibrated_info_and_new_timestamp():
    first = camera_info(None, 544, 448, "r1_depth_camera_optical_frame", time.time_ns())
    second = camera_info(None, 544, 448, "r1_depth_camera_optical_frame", time.time_ns())
    assert not any(first.k) and not any(first.r) and not any(first.p)
    assert first.header.frame_id == "r1_depth_camera_optical_frame"
    assert second.header.stamp != first.header.stamp


@pytest.mark.parametrize("field,change", [
    ("image_width", 640.5),
    ("distortion_model", "unsupported"),
    ("camera_matrix", {"rows": 3, "cols": 3, "data": [float("nan")] * 9}),
    ("camera_matrix", {"rows": 3, "cols": 3, "data": [0] * 9}),
    ("projection_matrix", {"rows": 4, "cols": 3, "data": [0] * 12}),
    ("rectification_matrix", {"rows": 3, "cols": 3, "data": [-1, 0, 0, 0, 1, 0, 0, 0, 1]}),
])
def test_reject_invalid_calibration(tmp_path, field, change):
    document = yaml.safe_load(DATA.read_text())
    document[field] = change
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml.safe_dump(document))
    with pytest.raises(ValueError):
        CameraCalibration.from_file(path)


def urdf_transform_document():
    root = ET.parse(DEPLOYMENT / "urdf/R1.urdf").getroot()
    joint = root.find("joint[@name='base_link_to_pelvis']")
    origin = joint.find("origin")
    xyz = [float(value) for value in origin.attrib["xyz"].split()]
    assert [float(value) for value in origin.attrib["rpy"].split()] == [0, 0, 0]
    return {"header": {"frame_id": joint.find("parent").attrib["link"]},
            "child_frame_id": joint.find("child").attrib["link"],
            "transform": {"translation": dict(zip(("x", "y", "z"), xyz)),
                          "rotation": {"x": 0, "y": 0, "z": 0, "w": 1}}}


def test_existing_urdf_fixed_transform(tmp_path):
    document = urdf_transform_document()
    path = tmp_path / "urdf-transform.yaml"
    path.write_text(yaml.safe_dump(document))
    mount = CameraMount.from_file(path, document["child_frame_id"])
    message = mount.message()
    assert message.header.frame_id == document["header"]["frame_id"]
    assert message.child_frame_id == document["child_frame_id"]
    assert message.header.stamp.sec == 0 and message.header.stamp.nanosec == 0
    assert message.transform.rotation.w == 1
    with pytest.raises(ValueError, match="child_frame_id"):
        CameraMount.from_file(path, "another_optical_frame")
    document["transform"]["rotation"]["w"] = 2
    path.write_text(yaml.safe_dump(document))
    with pytest.raises(ValueError, match="四元数"):
        CameraMount.from_file(path, document["child_frame_id"])


def test_empty_configuration_and_missing_file(tmp_path):
    assert load_geometry({}, tmp_path, "r1_depth_camera_optical_frame") == (None, None)
    with pytest.raises(FileNotFoundError):
        load_geometry({"calibration_file": "missing.yaml"}, tmp_path, "r1_depth_camera_optical_frame")
