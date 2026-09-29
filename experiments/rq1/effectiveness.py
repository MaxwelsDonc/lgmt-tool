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

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
INFER_RESULTS_DIR = os.path.join(PROJECT_ROOT, "infer_results")
FILE_PATTERN = re.compile(
    r"^sampled_mgs_label_(?P<model>.+)_(?P<shot>zero|few)_(?P<prompt>cot|direct)\.jsonl$"
)


def _format_percentage(value: float) -> str:
    if value < 0 and value > -1e-7:
        value = 0.0
    return f"{value * 100:.2f}%"


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


def _extract_is_consistent(record: dict[str, Any]) -> Optional[bool]:
    value = record.get("is_consistent")
    if value is True:
        return True
    if value is False:
        return False
    return None


def _compute_mvr_counts(records: list[dict[str, Any]]) -> tuple[int, int]:
    inconsistent = 0
    total = 0
    for record in records:
        is_consistent = _extract_is_consistent(record)
        if is_consistent is None:
            continue
        total += 1
        if not is_consistent:
            inconsistent += 1
    return inconsistent, total


def _map_model_name(raw_model: str) -> str:
    if raw_model == "ALL":
        return "ALL"
    return MODEL_NAME_MAP.get(raw_model, raw_model)


def rq1_effectiveness(few_shot: bool = FEWSHOT, cot: bool = COT) -> list[dict[str, Any]]:
    shot_type = "few" if few_shot else "zero"
    prompt_type = "cot" if cot else "direct"
    target_files = _iter_target_files(INFER_RESULTS_DIR, shot_type, prompt_type)

    rows: list[dict[str, Any]] = []
    total_inconsistent = 0
    total_records = 0

    for file_path in target_files:
        filename = os.path.basename(file_path)
        parsed = _parse_filename(filename)
        if parsed is None:
            continue
        model, _, _ = parsed
        records = _read_jsonl_records(file_path)
        inconsistent, total = _compute_mvr_counts(records)
        total_inconsistent += inconsistent
        total_records += total
        mvr = 0.0 if total == 0 else (inconsistent / total)
        rows.append(
            {
                "Model": _map_model_name(model),
                "Shot_Type": shot_type,
                "Prompt_Type": prompt_type,
                "mvr": _format_percentage(mvr),
                "Inconsistent_Count": inconsistent,
            }
        )

    rows = sorted(rows, key=lambda x: x["Model"])
    if total_records > 0:
        rows.append(
            {
                "Model": "ALL",
                "Shot_Type": shot_type,
                "Prompt_Type": prompt_type,
                "mvr": _format_percentage(total_inconsistent / total_records),
                "Inconsistent_Count": total_inconsistent,
            }
        )

    output_name = f"rq1_mvr_{shot_type}_{prompt_type}.json"
    output_path = os.path.join(CURRENT_DIR, output_name)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=4)
    print(f"✅ RQ1 MVR successfully saved to: {output_path}")
    return rows


if __name__ == "__main__":
    rq1_effectiveness(few_shot=FEWSHOT, cot=COT)
