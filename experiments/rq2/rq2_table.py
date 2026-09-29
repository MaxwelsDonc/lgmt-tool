import json
import os
from typing import Any


FEWSHOT = False
COT = True

MODEL_ORDER: list[str] = [
    "GPT-5.2",
    "Claude 4.5 Sonnet",
    "Llama 3.3",
    "DeepSeek Chat",
    "o4-mini",
    "DeepSeek Reasoner",
]

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


def _load_rq2_rows(shot_type: str, prompt_type: str) -> list[dict[str, Any]]:
    path = os.path.join(CURRENT_DIR, f"rq2_comparation_{shot_type}_{prompt_type}.json")
    with open(path, "r", encoding="utf-8") as f:
        rows = json.load(f)
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _to_latex_table(rows: list[dict[str, Any]]) -> str:
    caption = "Comparison of Reference-Based Testing and LGMT"
    columns = ["Model", "Acc_static", "Acc_cons", "HDR"]

    header = " & ".join(_latex_escape(column) for column in columns) + r" \\"
    lines = [
        r"\begin{table*}[pos=htbp]",
        r"\centering",
        rf"\caption{{{caption}}}\label{{tab:rq2}}",
        r"\begin{tabular}{lccc}",
        r"\toprule",
        header,
        r"\midrule",
    ]

    for row in rows:
        model = _latex_escape(str(row.get("Model", "")))
        acc_static = _latex_escape(str(row.get("Acc_static", "")))
        acc_cons = _latex_escape(str(row.get("Acc_cons", "")))
        hdr = _latex_escape(str(row.get("HDR", "")))
        lines.append(" & ".join([model, acc_static, acc_cons, hdr]) + r" \\")

    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table*}",
    ]
    return "\n".join(lines)


def rq2_table(few_shot: bool = FEWSHOT, cot: bool = COT) -> str:
    shot_type = "few" if few_shot else "zero"
    prompt_type = "cot" if cot else "direct"

    raw_rows = _load_rq2_rows(shot_type=shot_type, prompt_type=prompt_type)

    enriched_rows: list[dict[str, Any]] = []
    for row in raw_rows:
        model_display = str(row.get("Model", ""))
        if model_display == "ALL":
            continue
        
        enriched_rows.append(
            {
                "Model": model_display,
                "Acc_static": row.get("acc_static", ""),
                "Acc_cons": row.get("acc_cons", ""),
                "HDR": row.get("HDR", ""),
            }
        )

    order_index = {name: idx for idx, name in enumerate(MODEL_ORDER)}
    enriched_rows = sorted(
        enriched_rows,
        key=lambda r: order_index.get(str(r.get("Model", "")), 10_000),
    )

    latex = _to_latex_table(enriched_rows)
    output_path = os.path.join(CURRENT_DIR, "rq2_table.tex")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(latex)

    print(latex)
    print(f"\n✅ LaTeX table successfully saved to: {output_path}")
    return latex


if __name__ == "__main__":
    rq2_table(few_shot=FEWSHOT, cot=COT)
