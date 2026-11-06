import argparse
import json
import time
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from .client import DecisionClient
from .dataset import load_sample, save_json
from .models import Action, Label, Pipeline, Settings
from .report import write_report


def settings(path):
    return Settings.model_validate_json(Path(path).read_text())


def compare(args):
    config = settings(args.settings)
    paths = sorted(Path(args.samples).glob("*/sample.json"))
    if not paths:
        raise ValueError("there is no real sample to read")
    samples = [(path, load_sample(path)) for path in paths]
    if any(sample.source_kind != "r1_live" for _, sample in samples):
        raise ValueError("R1 paired experiments accept only r1_live samples")
    if len({sample.sample_id for _, sample in samples}) != len(samples):
        raise ValueError("sample IDs are not unique")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    save_json(output / "config.json", config.model_dump(mode="json"))
    save_json(output / "inputs.json", [{"path": str(path.resolve()), "sample": sample.model_dump(mode="json")}
                                       for path, sample in samples])
    warmup_config = Settings.model_validate(dict(config.model_dump(), pipeline_timeout_s=args.warmup_timeout))
    warmup = []
    for pipeline in Pipeline:
        result = DecisionClient(warmup_config).evaluate(samples[0][0], pipeline, list(Action))
        warmup.append(result.model_dump(mode="json"))
    save_json(output / "warmup.json", {"pipeline_timeout_s": warmup_config.pipeline_timeout_s, "results": warmup})
    client = DecisionClient(config)
    with (output / "results.jsonl").open("x", encoding="utf-8", buffering=1) as stream:
        for index, (path, sample) in enumerate(samples):
            pipelines = list(Pipeline) if index % 2 == 0 else list(reversed(Pipeline))
            for repeat in range(3 if index < args.repeat_samples else 1):
                for pipeline in pipelines:
                    started = time.monotonic()
                    record = {"schema_version": 1, "sample_id": str(sample.sample_id), "scene_id": sample.scene_id,
                              "pipeline": pipeline.value, "repeat": repeat, "request_id": str(uuid4())}
                    try:
                        decision = client.evaluate(path, pipeline, list(Action), request_id=UUID(record["request_id"]))
                        record.update(status="ok", decision=decision.model_dump(mode="json"))
                    except (ValueError, KeyError, RuntimeError, TimeoutError, httpx.HTTPError) as error:
                        record.update(status="failed", error=str(error), error_type=type(error).__name__)
                    record["elapsed_ms"] = (time.monotonic() - started) * 1000
                    stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                    print(f"{sample.sample_id} {pipeline.value} {record['status']}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Jev MVP live image capture, paired decisions and evaluation")
    commands = parser.add_subparsers(dest="command", required=True)
    configure = commands.add_parser("configure")
    configure.add_argument("--manifest", required=True)
    configure.add_argument("--data-dir", required=True)
    configure.add_argument("--output", required=True)
    configure.add_argument("--pipeline-timeout-s", type=float, default=5)
    capture = commands.add_parser("capture")
    capture.add_argument("--settings", required=True)
    capture.add_argument("--instruction", required=True)
    capture.add_argument("--scene-id", required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--settings", required=True)
    evaluate.add_argument("--sample", required=True)
    evaluate.add_argument("--pipeline", choices=[item.value for item in Pipeline], required=True)
    batch = commands.add_parser("compare")
    batch.add_argument("--settings", required=True)
    batch.add_argument("--samples", required=True)
    batch.add_argument("--output", required=True)
    batch.add_argument("--repeat-samples", type=int, default=10)
    batch.add_argument("--warmup-timeout", type=float, default=120)
    label = commands.add_parser("label")
    label.add_argument("--sample", required=True)
    label.add_argument("--actions", nargs="+", choices=[action.value for action in Action], required=True)
    label.add_argument("--requires-stop", action="store_true")
    label.add_argument("--reason", required=True)
    label.add_argument("--annotator", required=True)
    label.add_argument("--output", required=True)
    report = commands.add_parser("report")
    report.add_argument("--results", required=True)
    report.add_argument("--labels")
    report.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "configure":
        manifest = json.loads(Path(args.manifest).read_text())
        config = Settings(model_revision=manifest["models"]["decider"]["revision"], data_dir=str(Path(args.data_dir).resolve()),
                          pipeline_timeout_s=args.pipeline_timeout_s)
        save_json(args.output, config.model_dump(mode="json"))
    elif args.command == "capture":
        from .robot import Robot
        robot = Robot(settings(args.settings), "jev-sampler")
        print(robot.capture(args.instruction, args.scene_id))
    elif args.command == "evaluate":
        value = DecisionClient(settings(args.settings)).evaluate(args.sample, Pipeline(args.pipeline), list(Action))
        print(value.model_dump_json(indent=2))
    elif args.command == "compare":
        if args.repeat_samples < 0:
            raise ValueError("repeat-samples cannot be negative")
        compare(args)
    elif args.command == "label":
        sample = load_sample(args.sample)
        value = Label(sample_id=sample.sample_id, allowed_actions=args.actions, requires_stop=args.requires_stop,
                      annotation_reason=args.reason, annotator=args.annotator, annotation_version="1")
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("a", encoding="utf-8") as stream:
            stream.write(value.model_dump_json() + "\n")
    elif args.command == "report":
        print(json.dumps(write_report(args.results, args.output, args.labels), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
