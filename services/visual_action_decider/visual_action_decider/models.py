import base64
import hashlib
import json
import math
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Action(str, Enum):
    TURN_LEFT = "TURN_LEFT"
    FORWARD = "FORWARD"
    TURN_RIGHT = "TURN_RIGHT"
    STOP = "STOP"


class Pipeline(str, Enum):
    DIRECT_IMAGE = "direct_image"
    VISUAL_TEXT = "visual_text"


REGIONS = ("full", "left", "center", "right")
CANDIDATES = {
    Action.TURN_LEFT: "Turn left once to face a target visible on the left.",
    Action.FORWARD: "Move forward once toward the visible target ahead.",
    Action.TURN_RIGHT: "Turn right once to face a target visible on the right.",
    Action.STOP: "Remain stopped: the current step is complete, stopping is requested, or evidence is insufficient.",
}


def fingerprint(value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode()).hexdigest()


class ImageRecord(Model):
    region: Literal["full", "left", "center", "right"]
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    crop_xyxy: tuple[int, int, int, int]


class Sample(Model):
    schema_version: Literal[1] = 1
    sample_id: UUID
    source_kind: Literal["r1_live", "imported_image"] = "r1_live"
    scene_id: str = Field(min_length=1, max_length=120)
    instruction: str = Field(min_length=1, max_length=2000)
    captured_unix_ns: int = Field(gt=0)
    source_stamp_ns: int = Field(ge=0)
    received_monotonic_ns: int = Field(gt=0)
    original_size: tuple[int, int]
    images: list[ImageRecord] = Field(min_length=4, max_length=4)
    robot_state: dict
    camera_info: dict
    depth: dict | None = None
    history: list[dict] = Field(default_factory=list)

    @model_validator(mode="after")
    def regions(self):
        if tuple(image.region for image in self.images) != REGIONS:
            raise ValueError("图片必须依次包含 full、left、center、right")
        return self


class Label(Model):
    schema_version: Literal[1] = 1
    sample_id: UUID
    allowed_actions: list[Action] = Field(min_length=1, max_length=4)
    requires_stop: bool
    annotation_reason: str = Field(min_length=1)
    annotator: str = Field(min_length=1)
    annotation_version: str = Field(min_length=1)
    ambiguous: bool = False

    @model_validator(mode="after")
    def actions(self):
        if len(set(self.allowed_actions)) != len(self.allowed_actions):
            raise ValueError("允许动作不能重复")
        if self.requires_stop and self.allowed_actions != [Action.STOP]:
            raise ValueError("要求停止的标签只能允许 STOP")
        return self


class Asset(Model):
    type: Literal["image"] = "image"
    format: Literal["jpg"] = "jpg"
    data_base64: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def digest(self):
        data = base64.b64decode(self.data_base64, validate=True)
        if hashlib.sha256(data).hexdigest() != self.sha256:
            raise ValueError("图像校验失败")
        return self


class EncodeRequest(Model):
    schema_version: Literal[1] = 1
    request_id: UUID
    images: dict[str, Asset]

    @model_validator(mode="after")
    def regions(self):
        if tuple(self.images) != REGIONS:
            raise ValueError("图片区域及顺序不完整")
        return self


class Description(Model):
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    caption: str
    tags: list[str]


class EncodeResponse(Model):
    schema_version: Literal[1] = 1
    request_id: UUID
    images: dict[str, Description]
    revisions: dict[str, str]
    config_hash: str
    timings_ms: dict[str, float]
    gpu: dict


class Decision(Model):
    schema_version: Literal[1] = 1
    decision_id: UUID
    request_id: UUID
    sample_id: UUID
    pipeline: Pipeline
    selected_action: Action
    probabilities: dict[Action, float]
    model: str
    model_revision: str
    candidate_set_hash: str
    pipeline_config_hash: str
    timings_ms: dict[str, float]
    usage: dict
    gpu: dict

    @model_validator(mode="after")
    def distribution(self):
        values = self.probabilities
        if not values or any(not math.isfinite(v) or v < 0 or v > 1 for v in values.values()):
            raise ValueError("候选概率无效")
        if abs(sum(values.values()) - 1) > 0.001:
            raise ValueError("候选概率总和无效")
        if self.selected_action not in values or values[self.selected_action] < max(values.values()):
            raise ValueError("选中动作与概率不一致")
        return self


class Settings(Model):
    decider_url: str = "http://127.0.0.1:18080"
    encoder_url: str = "http://127.0.0.1:18081"
    model_revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    data_dir: str = Field(min_length=1)
    camera_provider_id: str = "r1_camera"
    depth_provider_id: str = "r1_depth"
    state_provider_id: str = "r1_state"
    chassis_provider_id: str = "r1_chassis"
    capture_depth: bool = True
    pipeline_timeout_s: float = Field(default=5, gt=0, le=120)
    capture_timeout_s: float = Field(default=3, gt=0, le=30)
    decision_age_limit_s: float = Field(default=8, gt=0, le=30)
    control_rate_hz: float = Field(default=20, ge=10, le=50)
    motion_enabled: bool = False
    turning_verified: bool = False
    forward_speed: float = Field(default=0.3, gt=0, le=0.4)
    forward_duration_s: float = Field(default=5, gt=0, le=5)
    turn_speed: float = Field(default=0.2, gt=0, le=0.5)
    turn_duration_s: float = Field(default=2, gt=0, le=5)

    def live_actions(self):
        if not self.motion_enabled:
            raise RuntimeError("当前部署仅启用 evaluate；运动配置尚未启用")
        return list(Action) if self.turning_verified else [Action.FORWARD, Action.STOP]
