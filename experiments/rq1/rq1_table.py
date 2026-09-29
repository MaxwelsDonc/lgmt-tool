import json
import os
import re
from typing import Any, Optional, Tuple


FEWSHOT = False
COT = True
AUDITED_VIOLATIONS = 100

MODEL_NAME_MAP: dict[str, str] = {
    "chatgpt": "GPT-5.2",
    "chatgpt_reasoner": "o4-mini",
    "claude": "Claude 4.5 Sonnet",
    "deepseek": "DeepSeek Chat",
    "deepseek_reasoner": "Deepseek Reasoner",
    "llama": "Llama 3.3",
}
DISPLAY_TO_RAW_MODEL: dict[str, str] = {v: k for k, v in MODEL_NAME_MAP.items()}

MODEL_ORDER: list[str] = [
    "gpt 5.2",
    "claude 4.5 sonnet",
    "llama3",
    "deepseek",
    "o4-mini",
    "deepseek reasoner",
]

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
INFER_RESULTS_DIR = os.path.join(PROJECT_ROOT, "infer_results")
FILE_PATTERN = re.compile(
    r"^sampled_mgs_label_(?P<model>.+)_(?P<shot>zero|few)_(?P<prompt>cot|direct)\.jsonl$"
)


def _latex_escape(text: str) -> str:
    return (
        text.replace("\\", r"\textbackslash{}")
        .replace("&", r"\&")
        .replace("%", r"\%")
        .replace("_", r"\_")
        .replace("#", r"\#")
        .replace("$", r"\$")
    )


def _parse_filename(filename: str) -> Optional[Tuple[str, str, str]]:
    match = FILE_PATTERN.match(filename)
    if not match:
        return None
    return match.group("model"), match.group("shot"), match.group("prompt")


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


def _compute_sample_size(file_path: str) -> int:
    records = _read_jsonl_records(file_path)
    count = 0
    for record in records:
        is_consistent = _extract_is_consistent(record)
        if is_consistent is None:
            continue
        count += 1
    return count


def _guess_infer_file_path(raw_model: str, shot_type: str, prompt_type: str) -> Optional[str]:
    model_dir = os.path.join(INFER_RESULTS_DIR, raw_model)
    if not os.path.isdir(model_dir):
        return None
    expected = f"sampled_mgs_label_{raw_model}_{shot_type}_{prompt_type}.jsonl"
    expected_path = os.path.join(model_dir, expected)
    if os.path.isfile(expected_path):
        return expected_path
    for filename in os.listdir(model_dir):
        parsed = _parse_filename(filename)
        if parsed is None:
            continue
        model, shot, prompt = parsed
        if model == raw_model and shot == shot_type and prompt == prompt_type:
            candidate = os.path.join(model_dir, filename)
            if os.path.isfile(candidate):
                return candidate
    return None


def _load_mvr_rows(shot_type: str, prompt_type: str) -> list[dict[str, Any]]:
    mvr_path = os.path.join(CURRENT_DIR, f"rq1_mvr_{shot_type}_{prompt_type}.json")
    with open(mvr_path, "r", encoding="utf-8") as f:
        rows = json.load(f)
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _to_latex_table(rows: list[dict[str, Any]]) -> str:
    caption = "Overall Effectiveness and Reliability of LGMT"
    columns = [
        "Model",
        "MVR",
        "# of Violations",
        "# of Audited Violations",
        "FP_drift",
        "FP_parse",
        "FRR",
    ]

    header = " & ".join(_latex_escape(column) for column in columns) + r" \\"
    lines = [
        r"\begin{table*}[pos=htbp]",
        r"\centering",
        rf"\caption{{{caption}}}\label{{tab:rq1}}",
        r"\begin{tabular}{lcccccc}",
        r"\toprule",
        header,
        r"\midrule",
    ]

    for row in rows:
        model = _latex_escape(str(row.get("Model", "")))
        mvr = _latex_escape(str(row.get("MVR", "")))
        violations = _latex_escape(str(row.get("# of Violations", "-")))
        audited_violations = _latex_escape(str(row.get("# of Audited Violations", "-")))
        fp_drift = _latex_escape(str(row.get("FP_drift", "-")))
        fp_parse = _latex_escape(str(row.get("FP_parse", "-")))
        frr = _latex_escape(str(row.get("FRR", "-")))
        lines.append(
            " & ".join(
                [model, mvr, violations, audited_violations, fp_drift, fp_parse, frr]
            )
            + r" \\"
        )

    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table*}",
    ]
    return "\n".join(lines)


def rq1_table(few_shot: bool = FEWSHOT, cot: bool = COT) -> str:
    shot_type = "few" if few_shot else "zero"
    prompt_type = "cot" if cot else "direct"

    mvr_rows = _load_mvr_rows(shot_type=shot_type, prompt_type=prompt_type)

    enriched_rows: list[dict[str, Any]] = []
    total_violations = 0
    for row in mvr_rows:
        model_display = str(row.get("Model", ""))
        if model_display == "ALL":
            continue
        normalized_model_display = "llama3" if model_display == "llama3.3" else model_display
        inconsistent_count = row.get("Inconsistent_Count", "-")
        if isinstance(inconsistent_count, int):
            total_violations += inconsistent_count

        enriched_rows.append(
            {
                "Model": normalized_model_display,
                "MVR": row.get("mvr", ""),
                "# of Violations": inconsistent_count,
                "# of Audited Violations": AUDITED_VIOLATIONS,
                "FP_drift": "-",
                "FP_parse": "-",
                "FRR": "-",
            }
        )

    order_index = {name: idx for idx, name in enumerate(MODEL_ORDER)}
    enriched_rows = sorted(
        enriched_rows,
        key=lambda r: order_index.get(str(r.get("Model", "")), 10_000),
    )

    latex = _to_latex_table(enriched_rows)

    output_path = os.path.join(CURRENT_DIR, "rq1_table.tex")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(latex)

    print(latex)
    print(f"\n✅ LaTeX table successfully saved to: {output_path}")
    return latex


if __name__ == "__main__":
    rq1_table(few_shot=FEWSHOT, cot=COT)
