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
    "deepseek_reasoner": "DeepSeek Reasoner",
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


def _map_model_name(raw_model: str) -> str:
    if raw_model == "ALL":
        return "ALL"
    return MODEL_NAME_MAP.get(raw_model, raw_model)


def _extract_correct_flags(record: dict[str, Any]) -> tuple[Optional[bool], Optional[bool]]:
    source = record.get("source_response")
    followup = record.get("followup_response")
    source_flag = source.get("is_correct") if isinstance(source, dict) else None
    followup_flag = followup.get("is_correct") if isinstance(followup, dict) else None
    if source_flag is not True and source_flag is not False:
        source_flag = None
    if followup_flag is not True and followup_flag is not False:
        followup_flag = None
    return source_flag, followup_flag


def _compute_accuracy_counts(
    records: list[dict[str, Any]],
) -> tuple[int, int, int, int, int]:
    static_correct = 0
    static_total = 0
    cons_correct = 0
    pair_total = 0
    hdr_count = 0

    for record in records:
        source_correct, followup_correct = _extract_correct_flags(record)

        if source_correct is not None:
            static_total += 1
            if source_correct:
                static_correct += 1

        if source_correct is None or followup_correct is None:
            continue

        pair_total += 1
        if source_correct and followup_correct:
            cons_correct += 1
        if source_correct and (not followup_correct):
            hdr_count += 1

    return static_correct, static_total, cons_correct, pair_total, hdr_count


def rq2_comparation(few_shot: bool = FEWSHOT, cot: bool = COT) -> list[dict[str, Any]]:
    shot_type = "few" if few_shot else "zero"
    prompt_type = "cot" if cot else "direct"
    target_files = _iter_target_files(INFER_RESULTS_DIR, shot_type, prompt_type)

    rows: list[dict[str, Any]] = []

    total_static_correct = 0
    total_static = 0
    total_cons_correct = 0
    total_pairs = 0
    total_hdr = 0

    for file_path in target_files:
        filename = os.path.basename(file_path)
        parsed = _parse_filename(filename)
        if parsed is None:
            continue
        model, _, _ = parsed
        records = _read_jsonl_records(file_path)
        static_correct, static_total, cons_correct, pair_total, hdr_count = _compute_accuracy_counts(
            records
        )

        total_static_correct += static_correct
        total_static += static_total
        total_cons_correct += cons_correct
        total_pairs += pair_total
        total_hdr += hdr_count

        acc_static = 0.0 if static_total == 0 else (static_correct / static_total)
        acc_cons = 0.0 if pair_total == 0 else (cons_correct / pair_total)
        hdr = 0.0 if pair_total == 0 else (hdr_count / pair_total)

        rows.append(
            {
                "Model": _map_model_name(model),
                "Shot_Type": shot_type,
                "Prompt_Type": prompt_type,
                "acc_static": _format_percentage(acc_static),
                "acc_cons": _format_percentage(acc_cons),
                "HDR": _format_percentage(hdr),
                "Static_Correct": static_correct,
                "Static_Total": static_total,
                "Cons_Correct": cons_correct,
                "Pair_Total": pair_total,
                "HDR_Count": hdr_count,
            }
        )

    rows = sorted(rows, key=lambda x: x["Model"])
    if total_static > 0 or total_pairs > 0:
        acc_static_all = 0.0 if total_static == 0 else (total_static_correct / total_static)
        acc_cons_all = 0.0 if total_pairs == 0 else (total_cons_correct / total_pairs)
        hdr_all = 0.0 if total_pairs == 0 else (total_hdr / total_pairs)
        rows.append(
            {
                "Model": "ALL",
                "Shot_Type": shot_type,
                "Prompt_Type": prompt_type,
                "acc_static": _format_percentage(acc_static_all),
                "acc_cons": _format_percentage(acc_cons_all),
                "HDR": _format_percentage(hdr_all),
                "Static_Correct": total_static_correct,
                "Static_Total": total_static,
                "Cons_Correct": total_cons_correct,
                "Pair_Total": total_pairs,
                "HDR_Count": total_hdr,
            }
        )

    output_name = f"rq2_comparation_{shot_type}_{prompt_type}.json"
    output_path = os.path.join(CURRENT_DIR, output_name)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=4)

    print(f"✅ RQ2 comparation successfully saved to: {output_path}")
    return rows


if __name__ == "__main__":
    rq2_comparation(few_shot=FEWSHOT, cot=COT)
