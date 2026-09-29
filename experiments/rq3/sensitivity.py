import csv
import json
import os
import re
from typing import Any, Optional, Tuple


FEWSHOT = False
COT = True

MODEL_NAME_MAP: dict[str, str] = {
    "chatgpt": "GPT-5.2",
    "chatgpt_reasoner": "o4-mini",
    "claude": "Claude 4.5 Sonnet",
    "deepseek": "DeepSeek Chat",
    "deepseek_reasoner": "Deepseek Reasoner",
    "llama": "Llama 3.3",
}

MODEL_ORDER: list[str] = [
    "GPT-5.2",
    "Claude 4.5 Sonnet",
    "Llama 3.3",
    "DeepSeek Chat",
    "o4-mini",
    "Deepseek Reasoner",
]

MR_CATEGORY_MAP: dict[str, str] = {
    "MR-E1.1": "MR-E",
    "MR-E1.2": "MR-E",
    "MR-E1.3": "MR-E",
    "MR-E1.4": "MR-E",
    "MR-E1.5": "MR-E",
    "MR-E1.6": "MR-E",
    "MR-E2.1": "MR-E",
    "MR-E2.2": "MR-E",
    "MR-E2.3": "MR-E",
    "MR-E2.4": "MR-E",
    "MR-S1": "MR-S",
    "MR-S2": "MR-S",
    "MR-P1": "MR-P",
    "MR-P2": "MR-P",
    "MR-P3": "MR-P",
    "MR-P4": "MR-P",
    "MR-P5": "MR-P",
    "MR-C1": "MR-C",
    "MR-C2": "MR-C",
    "MR-C3": "MR-C",
}

CATEGORY_ORDER: list[str] = ["MR-E", "MR-S", "MR-P", "MR-C"]
RULE_ORDER: list[str] = [
    "MR-E1.1",
    "MR-E1.2",
    "MR-E1.3",
    "MR-E1.4",
    "MR-E1.5",
    "MR-E1.6",
    "MR-E2.1",
    "MR-E2.2",
    "MR-E2.3",
    "MR-E2.4",
    "MR-S1",
    "MR-S2",
    "MR-P1",
    "MR-P2",
    "MR-P3",
    "MR-P4",
    "MR-P5",
    "MR-C1",
    "MR-C2",
    "MR-C3",
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


def _parse_filename(filename: str) -> Optional[Tuple[str, str, str]]:
    match = FILE_PATTERN.match(filename)
    if not match:
        return None
    return match.group("model"), match.group("shot"), match.group("prompt")


def _iter_target_files(root_dir: str, shot_type: str, prompt_type: str) -> list[str]:
    matched: list[str] = []
    for model_dir in sorted(os.listdir(root_dir)):
        model_dir_path = os.path.join(root_dir, model_dir)
        if not os.path.isdir(model_dir_path):
            continue
        for filename in sorted(os.listdir(model_dir_path)):
            file_path = os.path.join(model_dir_path, filename)
            if not os.path.isfile(file_path):
                continue
            parsed = _parse_filename(filename)
            if parsed is None:
                continue
            _, shot, prompt = parsed
            if shot == shot_type and prompt == prompt_type:
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


def _to_bool(value: Any) -> Optional[bool]:
    if value is True:
        return True
    if value is False:
        return False
    return None


def _extract_mr_index(record: dict[str, Any]) -> Optional[str]:
    key_candidates = ["mr_index", "mrIndex", "mr_idx", "mr_id", "mrId"]
    for key in key_candidates:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    nested_candidates = ["mr", "mr_info", "metamorphic_relation", "metamorphicRelation"]
    for key in nested_candidates:
        nested = record.get(key)
        if isinstance(nested, dict):
            value = nested.get("mr_index") or nested.get("mrIndex")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _map_model_name(raw_model: str) -> str:
    return MODEL_NAME_MAP.get(raw_model, raw_model)


def _write_csv(path: str, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def rq3_sensitivity(few_shot: bool = FEWSHOT, cot: bool = COT) -> dict[str, Any]:
    shot_type = "few" if few_shot else "zero"
    prompt_type = "cot" if cot else "direct"
    target_files = _iter_target_files(INFER_RESULTS_DIR, shot_type, prompt_type)

    model_category_counts: dict[tuple[str, str], dict[str, int]] = {}
    model_rule_counts: dict[tuple[str, str], dict[str, int]] = {}
    model_totals: dict[str, dict[str, int]] = {}

    for file_path in target_files:
        filename = os.path.basename(file_path)
        parsed = _parse_filename(filename)
        if parsed is None:
            continue
        raw_model, _, _ = parsed
        model = _map_model_name(raw_model)

        for record in _read_jsonl_records(file_path):
            is_consistent = _to_bool(record.get("is_consistent"))
            if is_consistent is None:
                continue

            mr_index = _extract_mr_index(record)
            if mr_index is None:
                continue

            category = MR_CATEGORY_MAP.get(mr_index)
            if category is None:
                continue

            category_key = (model, category)
            category_bucket = model_category_counts.setdefault(
                category_key, {"total_count": 0, "violation_count": 0}
            )
            category_bucket["total_count"] += 1
            if not is_consistent:
                category_bucket["violation_count"] += 1

            rule_key = (model, mr_index)
            rule_bucket = model_rule_counts.setdefault(
                rule_key, {"total_count": 0, "violation_count": 0}
            )
            rule_bucket["total_count"] += 1
            if not is_consistent:
                rule_bucket["violation_count"] += 1

            total_bucket = model_totals.setdefault(model, {"total_count": 0, "violation_count": 0})
            total_bucket["total_count"] += 1
            if not is_consistent:
                total_bucket["violation_count"] += 1

    order_index = {name: idx for idx, name in enumerate(MODEL_ORDER)}
    models = sorted(
        set(model for (model, _) in model_category_counts.keys()),
        key=lambda m: order_index.get(m, 10_000),
    )

    category_rows: list[dict[str, Any]] = []
    for category in CATEGORY_ORDER:
        row: dict[str, Any] = {"Category": category, "Shot_Type": shot_type, "Prompt_Type": prompt_type}
        category_total_count = 0
        category_violation_count = 0
        for model in models:
            bucket = model_category_counts.get((model, category), {"total_count": 0, "violation_count": 0})
            mvr = _safe_div(float(bucket["violation_count"]), float(bucket["total_count"]))
            row[model] = round(mvr, 6)
            category_total_count += int(bucket["total_count"])
            category_violation_count += int(bucket["violation_count"])
        row["Average"] = round(
            _safe_div(float(category_violation_count), float(category_total_count)),
            6,
        )
        category_rows.append(row)

    average_row: dict[str, Any] = {"Category": "Average", "Shot_Type": shot_type, "Prompt_Type": prompt_type}
    all_total_count = 0
    all_violation_count = 0
    for model in models:
        bucket = model_totals.get(model, {"total_count": 0, "violation_count": 0})
        mvr = _safe_div(float(bucket["violation_count"]), float(bucket["total_count"]))
        average_row[model] = round(mvr, 6)
        all_total_count += int(bucket["total_count"])
        all_violation_count += int(bucket["violation_count"])
    average_row["Average"] = round(
        _safe_div(float(all_violation_count), float(all_total_count)),
        6,
    )
    category_rows.append(average_row)

    rule_rows: list[dict[str, Any]] = []
    for mr_index in RULE_ORDER:
        row = {"Category": mr_index, "Shot_Type": shot_type, "Prompt_Type": prompt_type}
        rule_total_count = 0
        rule_violation_count = 0
        for model in models:
            bucket = model_rule_counts.get((model, mr_index), {"total_count": 0, "violation_count": 0})
            mvr = _safe_div(float(bucket["violation_count"]), float(bucket["total_count"]))
            row[model] = round(mvr, 6)
            rule_total_count += int(bucket["total_count"])
            rule_violation_count += int(bucket["violation_count"])
        row["Average"] = round(
            _safe_div(float(rule_violation_count), float(rule_total_count)),
            6,
        )
        rule_rows.append(row)
    rule_rows.append(dict(average_row))

    output_prefix = f"rq3_sensitivity_{shot_type}_{prompt_type}"
    columns = ["Category", "Shot_Type", "Prompt_Type"] + models + ["Average"]

    category_csv_path = os.path.join(CURRENT_DIR, f"{output_prefix}_category.csv")
    rule_csv_path = os.path.join(CURRENT_DIR, f"{output_prefix}_rule.csv")
    json_path = os.path.join(CURRENT_DIR, f"{output_prefix}.json")

    _write_csv(category_csv_path, category_rows, columns)
    _write_csv(rule_csv_path, rule_rows, columns)

    output_json: dict[str, Any] = {
        "metadata": {
            "shot_type": shot_type,
            "prompt_type": prompt_type,
            "models": models,
            "category_order": CATEGORY_ORDER,
            "rule_order": RULE_ORDER,
            "mvr_definition": "violation_count / total_count, where violation means is_consistent == false",
            "zero_division_policy": "mvr=0.0 when total_count=0",
        },
        "tables": {
            "category_csv_rows": category_rows,
            "rule_csv_rows": rule_rows,
        },
        "source_counts": {
            "model_category_counts": {
                f"{model}::{category}": value
                for (model, category), value in sorted(model_category_counts.items())
            },
            "model_rule_counts": {
                f"{model}::{rule}": value for (model, rule), value in sorted(model_rule_counts.items())
            },
            "model_totals": model_totals,
        },
        "output_files": {
            "category_csv": category_csv_path,
            "rule_csv": rule_csv_path,
            "json": json_path,
        },
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output_json, f, ensure_ascii=False, indent=4)

    print("✅ RQ3 sensitivity results saved:")
    print(f"- {category_csv_path}")
    print(f"- {rule_csv_path}")
    print(f"- {json_path}")

    return output_json


if __name__ == "__main__":
    rq3_sensitivity(few_shot=FEWSHOT, cot=COT)
