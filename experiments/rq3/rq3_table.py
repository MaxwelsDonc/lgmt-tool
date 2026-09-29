import csv
import os
from typing import Any


FEWSHOT = False
COT = True

MODEL_COLUMNS: list[str] = [
    "GPT-5.2",
    "Claude 4.5 Sonnet",
    "Llama 3.3",
    "DeepSeek Chat",
    "o4-mini",
    "DeepSeek Reasoner",
]

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

# Handle current CSV naming inconsistency gracefully.
MODEL_COLUMN_ALIASES: dict[str, list[str]] = {
    "GPT-5.2": ["GPT-5.2"],
    "Claude 4.5 Sonnet": ["Claude 4.5 Sonnet"],
    "Llama 3.3": ["Llama 3.3"],
    "DeepSeek Chat": ["DeepSeek Chat"],
    "o4-mini": ["o4-mini"],
    "DeepSeek Reasoner": ["DeepSeek Reasoner", "Deepseek Reasoner"],
}

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))


def _latex_escape(text: str) -> str:
    return (
        text.replace("\\", r"\textbackslash{}")
        .replace("&", r"\&")
        .replace("%", r"\%")
        .replace("_", r"\_")
        .replace("#", r"\#")
        .replace("$", r"\$")
    )


def _parse_mvr_to_percent(value: Any) -> str:
    try:
        ratio = float(value)
    except (TypeError, ValueError):
        ratio = 0.0
    return f"{ratio * 100:.2f}%"


def _load_csv_rows(path: str) -> list[dict[str, str]]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return [row for row in reader if isinstance(row, dict)]


def _pick_model_value(row: dict[str, str], model: str) -> str:
    aliases = MODEL_COLUMN_ALIASES.get(model, [model])
    for alias in aliases:
        if alias in row:
            return row.get(alias, "")
    return ""


def _build_table_rows(
    rows_by_category: dict[str, dict[str, str]],
    row_order: list[str],
) -> list[dict[str, str]]:
    output_rows: list[dict[str, str]] = []
    for category in row_order:
        source = rows_by_category.get(category, {})
        row: dict[str, str] = {
            "Category": category,
            "Avg. MVR": _parse_mvr_to_percent(source.get("Average", 0)),
        }
        for model in MODEL_COLUMNS:
            row[model] = _parse_mvr_to_percent(_pick_model_value(source, model))
        output_rows.append(row)
    return output_rows


def _to_latex_table(
    rows: list[dict[str, str]],
    caption: str,
    label: str,
) -> str:
    columns = ["Category", "Avg. MVR"] + MODEL_COLUMNS
    header = " & ".join(_latex_escape(column) for column in columns) + r" \\"
    lines = [
        r"\begin{table*}[pos=htbp]",
        r"\centering",
        rf"\caption{{{caption}}}\label{{{label}}}",
        r"\begin{tabular}{lccccccc}",
        r"\toprule",
        header,
        r"\midrule",
    ]

    for row in rows:
        row_values = [_latex_escape(str(row.get(column, ""))) for column in columns]
        lines.append(" & ".join(row_values) + r" \\")

    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table*}",
    ]
    return "\n".join(lines)


def rq3_table(few_shot: bool = FEWSHOT, cot: bool = COT) -> tuple[str, str]:
    shot_type = "few" if few_shot else "zero"
    prompt_type = "cot" if cot else "direct"

    category_csv_path = os.path.join(CURRENT_DIR, f"rq3_sensitivity_{shot_type}_{prompt_type}_category.csv")
    rule_csv_path = os.path.join(CURRENT_DIR, f"rq3_sensitivity_{shot_type}_{prompt_type}_rule.csv")

    category_rows_raw = _load_csv_rows(category_csv_path)
    rule_rows_raw = _load_csv_rows(rule_csv_path)

    category_rows_by_name = {str(row.get("Category", "")): row for row in category_rows_raw}
    rule_rows_by_name = {str(row.get("Category", "")): row for row in rule_rows_raw}

    table1_rows = _build_table_rows(category_rows_by_name, CATEGORY_ORDER)
    table2_rows = _build_table_rows(rule_rows_by_name, RULE_ORDER)

    table1_caption = (
        "Sensitivity of LGMT across MR categories. Each cell reports the Metamorphic "
        "Violation Rate (MVR). The Avg. MVR column is computed by aggregating "
        "violations across all models."
    )
    table2_caption = (
        "Sensitivity of LGMT across MRs. Each cell reports the Metamorphic "
        "Violation Rate (MVR). The Avg. MVR column is computed by aggregating "
        "violations across all models."
    )

    table1_tex = _to_latex_table(table1_rows, caption=table1_caption, label="tab:rq3")
    table2_tex = _to_latex_table(table2_rows, caption=table2_caption, label="tab:rq3_appendix")

    output_main_path = os.path.join(CURRENT_DIR, "rq3_table.tex")
    output_appendix_path = os.path.join(CURRENT_DIR, "rq3_table_appendix.tex")

    with open(output_main_path, "w", encoding="utf-8") as f:
        f.write(table1_tex)

    with open(output_appendix_path, "w", encoding="utf-8") as f:
        f.write(table2_tex)

    print(table1_tex)
    print("\n")
    print(table2_tex)
    print(f"\n✅ Main table saved to: {output_main_path}")
    print(f"✅ Appendix table saved to: {output_appendix_path}")
    return table1_tex, table2_tex


if __name__ == "__main__":
    rq3_table(few_shot=FEWSHOT, cot=COT)
