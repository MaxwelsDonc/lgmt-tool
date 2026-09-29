import csv
import json
import os
import re
from typing import Any, Optional, Tuple


MODEL_SPECS: list[tuple[str, str]] = [
    ("chatgpt", "GPT-5.2"),
    ("claude", "Claude 4.5 Sonnet"),
    ("llama", "Llama 3.3"),
    ("deepseek", "DeepSeek Chat"),
    ("chatgpt_reasoner", "o4-mini"),
    ("deepseek_reasoner", "DeepSeek Reasoner"),
]

PROMPTING_STRATEGIES: list[tuple[str, str, str]] = [
    ("zero", "direct", "Zero-shot"),
    ("zero", "cot", "Zero-shot CoT"),
    ("few", "direct", "Few-shot"),
    ("few", "cot", "Few-shot CoT"),
]

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
INFER_RESULTS_DIR = os.path.join(PROJECT_ROOT, "infer_results")
FILE_PATTERN = re.compile(
    r"^sampled_mgs_label_(?P<model>.+)_(?P<shot>zero|few)_(?P<prompt>cot|direct)\.jsonl$"
)


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _format_percentage(value: float) -> str:
    if value < 0 and value > -1e-7:
        value = 0.0
    return f"{value * 100:.2f}%"


def _parse_filename(filename: str) -> Optional[Tuple[str, str, str]]:
    match = FILE_PATTERN.match(filename)
    if not match:
        return None
    return match.group("model"), match.group("shot"), match.group("prompt")


def _iter_all_result_files(root_dir: str) -> list[str]:
    matched: list[str] = []
    for model_dir in sorted(os.listdir(root_dir)):
        model_dir_path = os.path.join(root_dir, model_dir)
        if not os.path.isdir(model_dir_path):
            continue
        for filename in sorted(os.listdir(model_dir_path)):
            file_path = os.path.join(model_dir_path, filename)
            if not os.path.isfile(file_path):
                continue
            if _parse_filename(filename) is None:
                continue
            matched.append(file_path)
    return sorted(matched)


def _read_jsonl_records(file_path: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _compute_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    total_count = len(records)
    source_correct_count = 0
    acc_cons_count = 0
    violation_count = 0
    fur_count = 0

    for record in records:
        source_response = record.get("source_response")
        followup_response = record.get("followup_response")

        source_correct = (
            source_response.get("is_correct") if isinstance(source_response, dict) else None
        )
        followup_correct = (
            followup_response.get("is_correct") if isinstance(followup_response, dict) else None
        )
        is_consistent = record.get("is_consistent")

        if source_correct is True:
            source_correct_count += 1

        if source_correct is True and followup_correct is True:
            acc_cons_count += 1

        if is_consistent is False:
            violation_count += 1

        if source_correct is False and followup_correct is False and is_consistent is True:
            fur_count += 1

    acc_static = _safe_div(float(source_correct_count), float(total_count))
    acc_cons = _safe_div(float(acc_cons_count), float(total_count))
    hdr = acc_static - acc_cons
    mvr = _safe_div(float(violation_count), float(total_count))
    fur = _safe_div(float(fur_count), float(total_count))

    return {
        "total_count": total_count,
        "source_correct_count": source_correct_count,
        "acc_cons_count": acc_cons_count,
        "violation_count": violation_count,
        "fur_count": fur_count,
        "acc_static": acc_static,
        "acc_cons": acc_cons,
        "hdr": hdr,
        "mvr": mvr,
        "fur": fur,
    }


def _write_csv(path: str, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def rq4_mitigation() -> dict[str, Any]:
    file_index: dict[tuple[str, str, str], str] = {}
    for file_path in _iter_all_result_files(INFER_RESULTS_DIR):
        parsed = _parse_filename(os.path.basename(file_path))
        if parsed is None:
            continue
        raw_model, shot_type, prompt_type = parsed
        file_index[(raw_model, shot_type, prompt_type)] = file_path

    rows: list[dict[str, Any]] = []
    source_counts: dict[str, dict[str, int]] = {}

    for raw_model, display_model in MODEL_SPECS:
        for shot_type, prompt_type, prompt_display in PROMPTING_STRATEGIES:
            file_path = file_index.get((raw_model, shot_type, prompt_type))
            records = _read_jsonl_records(file_path) if file_path is not None else []
            metrics = _compute_metrics(records)

            row = {
                "Model": display_model,
                "Prompt": prompt_display,
                "Shot_Type": shot_type,
                "Prompt_Type": prompt_type,
                "total_count": metrics["total_count"],
                "acc_static": round(float(metrics["acc_static"]), 6),
                "acc_static_percent": _format_percentage(float(metrics["acc_static"])),
                "acc_cons": round(float(metrics["acc_cons"]), 6),
                "acc_cons_percent": _format_percentage(float(metrics["acc_cons"])),
                "hdr": round(float(metrics["hdr"]), 6),
                "hdr_percent": _format_percentage(float(metrics["hdr"])),
                "mvr": round(float(metrics["mvr"]), 6),
                "mvr_percent": _format_percentage(float(metrics["mvr"])),
                "fur": round(float(metrics["fur"]), 6),
                "fur_percent": _format_percentage(float(metrics["fur"])),
            }
            rows.append(row)

            source_counts[f"{display_model}::{prompt_display}"] = {
                "total_count": int(metrics["total_count"]),
                "source_correct_count": int(metrics["source_correct_count"]),
                "acc_cons_count": int(metrics["acc_cons_count"]),
                "violation_count": int(metrics["violation_count"]),
                "fur_count": int(metrics["fur_count"]),
            }

    output_prefix = "rq4_mitigation"
    json_path = os.path.join(CURRENT_DIR, f"{output_prefix}.json")
    csv_path = os.path.join(CURRENT_DIR, f"{output_prefix}_main_table.csv")

    csv_columns = [
        "Model",
        "Prompt",
        "Shot_Type",
        "Prompt_Type",
        "total_count",
        "acc_static",
        "acc_static_percent",
        "acc_cons",
        "acc_cons_percent",
        "hdr",
        "hdr_percent",
        "mvr",
        "mvr_percent",
        "fur",
        "fur_percent",
    ]
    _write_csv(csv_path, rows, csv_columns)

    output_json: dict[str, Any] = {
        "metadata": {
            "model_order": [display for _, display in MODEL_SPECS],
            "prompting_strategy_order": [display for _, _, display in PROMPTING_STRATEGIES],
            "prompt_mapping": [
                {"shot": shot, "prompt": prompt, "display": display}
                for shot, prompt, display in PROMPTING_STRATEGIES
            ],
            "model_mapping": [
                {"raw_model": raw, "display_model": display} for raw, display in MODEL_SPECS
            ],
            "metric_definitions": {
                "acc_static": "# source_correct / # total_MGs",
                "acc_cons": "# (source_correct and followup_correct) / # total_MGs",
                "hdr": "acc_static - acc_cons",
                "mvr": "# (is_consistent == false) / # total_MGs",
                "fur": "# (source_correct == false and followup_correct == false and is_consistent == true) / # total_MGs",
            },
            "zero_division_policy": "all metrics are set to 0.0 when total_count == 0",
        },
        "main_table": rows,
        "source_counts": source_counts,
        "output_files": {
            "json": json_path,
            "csv": csv_path,
        },
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output_json, f, ensure_ascii=False, indent=4)

    print("✅ RQ4 mitigation results saved:")
    print(f"- {json_path}")
    print(f"- {csv_path}")
    return output_json


if __name__ == "__main__":
    rq4_mitigation()
