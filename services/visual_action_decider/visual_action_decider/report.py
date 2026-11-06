import csv
import json
from pathlib import Path

import numpy as np

from .dataset import save_json
from .models import Action, Label, Pipeline


def read_jsonl(path):
    with Path(path).open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def summarize(records, labels):
    result = {}
    for pipeline in Pipeline:
        rows = [row for row in records if row["pipeline"] == pipeline.value and row["repeat"] == 0]
        valid = [row for row in rows if row["status"] == "ok"]
        labelled = [row for row in rows if row["sample_id"] in labels and not labels[row["sample_id"]].ambiguous]
        stop = [row for row in labelled if labels[row["sample_id"]].requires_stop]
        correct = sum(row["status"] == "ok" and Action(row["decision"]["selected_action"]) in labels[row["sample_id"]].allowed_actions
                      for row in labelled)
        times = [row["elapsed_ms"] for row in valid]
        bins = [[] for _ in range(5)]
        brier = []
        for row in labelled:
            label = labels[row["sample_id"]]
            if row["status"] != "ok" or len(label.allowed_actions) != 1:
                continue
            decision = row["decision"]
            probabilities = decision["probabilities"]
            confidence = max(probabilities.values())
            hit = decision["selected_action"] == label.allowed_actions[0].value
            bins[min(int(confidence * 5), 4)].append((confidence, hit))
            brier.append(sum((probability - (action == label.allowed_actions[0].value)) ** 2
                             for action, probability in probabilities.items()))
        count = sum(len(items) for items in bins)
        ece = sum(len(items) / count * abs(np.mean([item[0] for item in items]) - np.mean([item[1] for item in items]))
                  for items in bins if items) if count else None
        repeats = {}
        for row in records:
            if row["pipeline"] == pipeline.value:
                repeats.setdefault(row["sample_id"], []).append(row)
        repeated = [values for values in repeats.values() if len(values) > 1]
        per_scene = {}
        for row in rows:
            scene = per_scene.setdefault(row["scene_id"], {"requests": 0, "valid": 0, "labelled": 0, "correct": 0})
            scene["requests"] += 1
            scene["valid"] += row["status"] == "ok"
            if row in labelled:
                scene["labelled"] += 1
                scene["correct"] += row["status"] == "ok" and Action(row["decision"]["selected_action"]) in labels[row["sample_id"]].allowed_actions
        result[pipeline.value] = {
            "requests": len(rows), "valid": len(valid), "failed": len(rows) - len(valid),
            "valid_rate": len(valid) / len(rows) if rows else None,
            "labelled": len(labelled), "accuracy": correct / len(labelled) if labelled else None,
            "requires_stop": len(stop),
            "stop_motion_rate": sum(row["status"] == "ok" and row["decision"]["selected_action"] != "STOP" for row in stop) / len(stop) if stop else None,
            "stop_failed_requests": sum(row["status"] != "ok" for row in stop),
            "latency_ms": {key: float(np.percentile(times, value)) if times else None for key, value in (("p50", 50), ("p95", 95), ("max", 100))},
            "brier": float(np.mean(brier)) if brier else None, "ece_5_equal_width_bins": float(ece) if ece is not None else None,
            "calibration_samples": count,
            "repeat_consistency": sum(all(row["status"] == "ok" for row in values) and
                                      len({row["decision"]["selected_action"] for row in values if row["status"] == "ok"}) == 1
                                      for values in repeated) / len(repeated) if repeated else None,
            "scene_count": len({row["scene_id"] for row in rows}),
            "per_scene": per_scene,
            "process_peak_allocated_bytes": {
                process: max(values) if (values := [row["decision"]["gpu"][process]["peak_allocated_bytes"] for row in valid
                    if row["decision"].get("gpu", {}).get(process) is not None]) else None
                for process in ("decider", "encoder")},
        }
    pairs = {}
    for row in records:
        if row["repeat"] == 0:
            pairs.setdefault(row["sample_id"], {})[row["pipeline"]] = row
    complete = [pair for pair in pairs.values() if len(pair) == 2]
    result["paired"] = {
        "samples": len(complete),
        "agreement": sum(all(row["status"] == "ok" for row in pair.values()) and
                         pair["direct_image"]["decision"]["selected_action"] == pair["visual_text"]["decision"]["selected_action"]
                         for pair in complete) / len(complete) if complete else None,
        "failed_pairs": sum(any(row["status"] != "ok" for row in pair.values()) for pair in complete),
    }
    return result


def write_report(results_path, output, labels_path=None):
    records = read_jsonl(results_path)
    labels = {}
    if labels_path:
        for raw in read_jsonl(labels_path):
            label = Label.model_validate(raw)
            key = str(label.sample_id)
            if key in labels:
                raise ValueError("the same sample has duplicate labels")
            labels[key] = label
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    summary = summarize(records, labels)
    save_json(output / "summary.json", summary)
    fields = ["sample_id", "scene_id", "pipeline", "repeat", "status", "elapsed_ms", "selected_action", "error"]
    with (output / "samples.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in records:
            writer.writerow({**{field: row.get(field, "") for field in fields},
                             "selected_action": row.get("decision", {}).get("selected_action", "")})
    with (output / "report.md").open("x", encoding="utf-8") as stream:
        stream.write("# Jev paired-experiment results\n\n")
        stream.write("Accuracy and probability-calibration metrics stay empty when labels are missing. Details are in samples.csv and summary.json.\n\n")
        stream.write("| Pipeline | Requests | Valid | Accuracy | P50 ms | P95 ms |\n| --- | --- | --- | --- | --- | --- |\n")
        for pipeline in Pipeline:
            row = summary[pipeline.value]
            stream.write(f"| {pipeline.value} | {row['requests']} | {row['valid']} | {row['accuracy']} | {row['latency_ms']['p50']} | {row['latency_ms']['p95']} |\n")
    return summary
