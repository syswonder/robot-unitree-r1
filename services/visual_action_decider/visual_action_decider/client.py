import time
from pathlib import Path
from uuid import uuid4

import httpx

from .dataset import assets_for, load_sample, save_json
from .models import CANDIDATES, Decision, EncodeRequest, EncodeResponse, Pipeline, fingerprint


def visual_state(encoded):
    regions = [encoded.images[name] for name in ("left", "center", "right")]
    common = set(regions[0].tags).intersection(*(set(region.tags) for region in regions[1:]))
    return {
        "scene": {"caption": encoded.images["full"].caption, "tags": encoded.images["full"].tags},
        "common_tags": sorted(common),
        "regions": {name: {"caption": encoded.images[name].caption,
                           "distinct_tags": sorted(set(encoded.images[name].tags) - common)}
                    for name in ("left", "center", "right")},
    }


def request_body(sample, actions, assets=None, descriptions=None):
    criteria = {action.value: CANDIDATES[action] for action in actions}
    if len(criteria) < 2:
        raise ValueError("a Choice request needs at least two candidates")
    state = {"instruction": sample.instruction, "robot_state": {
                 key: sample.robot_state[key] for key in ("fsm", "stale", "age_s") if key in sample.robot_state},
             "history": sample.history, "candidates": criteria,
             "view_convention": "left/center/right are image regions viewed from the robot; left turn is positive yaw."}
    body = {"state": state, "layout": "state_first", "independent": True,
            "questions": {"next_action": {"type": "choice", "instructions": "Which next action fits the task and observations?",
                                           "criteria": criteria}}}
    if assets is not None:
        state["views"] = {name: f"view-{name}" for name in assets}
        body["assets"] = {f"view-{name}": asset.model_dump(exclude={"sha256"}) for name, asset in assets.items()}
    if descriptions is not None:
        state["visual_evidence"] = descriptions
    return body


class DecisionClient:
    def __init__(self, settings):
        self.settings = settings

    def evaluate(self, sample_path, pipeline, actions, request_id=None, cancelled=None):
        request_id = request_id or uuid4()
        pipeline = Pipeline(pipeline)
        started = time.monotonic()
        deadline = started + self.settings.pipeline_timeout_s
        sample = load_sample(sample_path)
        assets = assets_for(sample_path, sample)
        folder = Path(self.settings.data_dir) / "decisions" / str(request_id)
        folder.mkdir(parents=True, exist_ok=False)
        save_json(folder / "input.json", {"sample_path": str(Path(sample_path).resolve()), "pipeline": pipeline.value,
                                         "actions": [action.value for action in actions], "request_id": str(request_id)})

        def remaining():
            if cancelled is not None and cancelled.is_set():
                raise RuntimeError("the request was cancelled")
            value = deadline - time.monotonic()
            if value <= 0:
                raise TimeoutError("PIPELINE_TIMEOUT")
            return value

        with httpx.Client(trust_env=False) as client:
            response = client.get(self.settings.decider_url + "/mvp/info", timeout=remaining())
            response.raise_for_status()
            info = response.json()
            if info["model_revision"] != self.settings.model_revision or info["device"] != "cuda":
                raise ValueError("the model revision or runtime device does not match the configuration")
            save_json(folder / "model-info.json", info)
            encoded = None
            visual_started = time.monotonic()
            if pipeline == Pipeline.VISUAL_TEXT:
                payload = EncodeRequest(request_id=request_id, images=assets)
                response = client.post(self.settings.decider_url + "/mvp/encode", json=payload.model_dump(mode="json"),
                                       headers={"X-Jev-Encoder-URL": self.settings.encoder_url}, timeout=remaining())
                response.raise_for_status()
                encoded = EncodeResponse.model_validate(response.json())
                if encoded.request_id != request_id or tuple(encoded.images) != tuple(assets):
                    raise ValueError("the visual response does not match the request")
                if any(encoded.images[name].sha256 != asset.sha256 for name, asset in assets.items()):
                    raise ValueError("the visual response image checksum does not match")
                save_json(folder / "visual.json", encoded.model_dump(mode="json"))
            visual_ms = (time.monotonic() - visual_started) * 1000
            body = request_body(sample, actions, assets if encoded is None else None,
                                visual_state(encoded) if encoded is not None else None)
            save_json(folder / "request.json", body)
            decider_started = time.monotonic()
            response = client.post(self.settings.decider_url + "/v1/systemone", json=body, timeout=remaining())
            response.raise_for_status()
            raw = response.json()
            gpu = {"decider": {
                "peak_allocated_bytes": int(response.headers["X-Jev-Peak-Allocated-Bytes"]),
                "allocated_bytes": int(response.headers["X-Jev-Allocated-Bytes"]),
                "reserved_bytes": int(response.headers["X-Jev-Reserved-Bytes"])},
                "encoder": encoded.gpu if encoded is not None else None}
            save_json(folder / "response.json", raw)
            remaining()
            answer = raw["answers"]["next_action"]
            probabilities = answer["probabilities"]
            if answer["type"] != "choice" or set(probabilities) != {action.value for action in actions}:
                raise ValueError("INVALID_MODEL_RESPONSE: the candidate set does not match")
            config = {"settings": self.settings.model_dump(), "model_info": {
                          key: info[key] for key in ("model_revision", "model_path", "device", "temperatures", "resource_policy")},
                      "visual_config": encoded.config_hash if encoded is not None else None,
                      "candidates": body["questions"]["next_action"]["criteria"]}
            result = Decision(decision_id=uuid4(), request_id=request_id, sample_id=sample.sample_id,
                              pipeline=pipeline, selected_action=answer["choice"], probabilities=probabilities,
                              model=raw["model"], model_revision=self.settings.model_revision,
                              candidate_set_hash=fingerprint(config["candidates"]), pipeline_config_hash=fingerprint(config),
                              timings_ms={"visual": visual_ms, "decider_http": (time.monotonic() - decider_started) * 1000,
                                          "total": (time.monotonic() - started) * 1000}, usage=raw["usage"], gpu=gpu)
            save_json(folder / "decision.json", result.model_dump(mode="json"))
            return result
