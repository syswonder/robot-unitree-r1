import base64
import hashlib
import io
import json
import time
from pathlib import Path
from uuid import uuid4

from PIL import Image

from .models import Asset, ImageRecord, REGIONS, Sample


def save_json(path, value):
    path = Path(path)
    encoded = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        output.write(encoded)


def load_sample(path):
    path = Path(path)
    sample = Sample.model_validate_json(path.read_text())
    for record in sample.images:
        image_path = (path.parent / record.path).resolve()
        if not image_path.is_relative_to(path.parent.resolve()):
            raise ValueError("the image path escapes the sample directory")
        if hashlib.sha256(image_path.read_bytes()).hexdigest() != record.sha256:
            raise ValueError(f"image checksum failed: {record.region}")
        with Image.open(image_path) as image:
            if image.size != (record.width, record.height):
                raise ValueError("the image size does not match the record")
    return sample


def archive_rgb(root, image, scene_id, instruction, state, camera_info, source_stamp_ns,
                received_monotonic_ns, depth=None, source_kind="r1_live"):
    sample_id = uuid4()
    folder = Path(root) / str(sample_id)
    folder.mkdir(parents=True, exist_ok=False)
    image = image.convert("RGB")
    width, height = image.size
    if width < 3 or height < 1:
        raise ValueError("the image is too small")
    boxes = [(0, 0, width, height)] + [(i * width // 3, 0, (i + 1) * width // 3, height) for i in range(3)]
    records = []
    for region, box in zip(REGIONS, boxes):
        pixels = image.crop(box)
        pixels.thumbnail((768, 768), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        pixels.save(buffer, format="JPEG", quality=90)
        data = buffer.getvalue()
        filename = f"{region}.jpg"
        (folder / filename).write_bytes(data)
        records.append(ImageRecord(region=region, path=filename, sha256=hashlib.sha256(data).hexdigest(),
                                   width=pixels.width, height=pixels.height, crop_xyxy=box))
    depth_record = None
    if depth is not None:
        data, metadata = depth
        (folder / "depth.bin").write_bytes(data)
        depth_record = dict(metadata, path="depth.bin", sha256=hashlib.sha256(data).hexdigest())
    sample = Sample(sample_id=sample_id, source_kind=source_kind, scene_id=scene_id, instruction=instruction,
                    captured_unix_ns=time.time_ns(), source_stamp_ns=source_stamp_ns,
                    received_monotonic_ns=received_monotonic_ns, original_size=(width, height),
                    images=records, robot_state=state, camera_info=camera_info, depth=depth_record)
    save_json(folder / "sample.json", sample.model_dump(mode="json"))
    return folder / "sample.json"


def assets_for(path, sample):
    folder = Path(path).parent
    return {record.region: Asset(data_base64=base64.b64encode((folder / record.path).read_bytes()).decode(),
                                 sha256=record.sha256) for record in sample.images}
