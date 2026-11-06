import argparse
import json
from pathlib import Path

from r1_sensor_geometry import load_geometry


def main():
    parser = argparse.ArgumentParser(description="Check an R1 RGB or depth calibration and extrinsic file without opening a device")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--frame-id", required=True)
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--calibration-file", default="")
    parser.add_argument("--extrinsics-file", default="")
    args = parser.parse_args()
    if (args.width is None) != (args.height is None):
        raise ValueError("width and height must be provided together")
    calibration, mount = load_geometry(vars(args), args.root, args.frame_id, args.width, args.height)
    print(json.dumps({"frame_id": args.frame_id, "calibrated": calibration is not None,
                      "calibrated_size": [calibration.width, calibration.height] if calibration is not None else None,
                      "extrinsics_available": mount is not None,
                      "parent_frame": mount.parent_frame if mount is not None else None,
                      "child_frame": mount.child_frame if mount is not None else None}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
