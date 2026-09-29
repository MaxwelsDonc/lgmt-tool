import csv
import os


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_CSV = os.path.join(CURRENT_DIR, "rq4_mitigation_main_table.csv")
OUTPUT_TEX = os.path.join(CURRENT_DIR, "rq4_table.tex")


def _latex_escape(text: str) -> str:
    return (
        text.replace("\\", r"\textbackslash{}")
        .replace("&", r"\&")
        .replace("%", r"\%")
        .replace("_", r"\_")
        .replace("#", r"\#")
        .replace("$", r"\$")
    )


def _load_rows(path: str) -> list[dict[str, str]]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return [row for row in reader if isinstance(row, dict)]


def _to_latex_table(rows: list[dict[str, str]]) -> str:
    columns = [
        "Model",
        "Prompt",
        "Acc_static",
        "Acc_cons",
        "HDR",
        "MVR",
        "FUR",
    ]

    caption = (
        "Impact of prompting strategies on model performance. "
        "Acc\_static, Acc\_cons, and HDR are comparative evaluation metrics; "
        "MVR measures the defect detection capability of LGMT; "
        "FUR captures the limitation of consistency-based testing."
    )

    header = " & ".join(_latex_escape(col) for col in columns) + r" \\"
    lines = [
        r"\begin{table*}[pos=htbp]",
        r"\centering",
        rf"\caption{{{caption}}}\label{{tab:rq4}}",
        r"\begin{tabular}{llccc|c|c}",
        r"\toprule",
        header,
        r"\midrule",
    ]

    prev_model = ""
    for row in rows:
        current_model = str(row.get("Model", ""))
        if prev_model and current_model != prev_model:
            lines.append(r"\midrule")

        row_values = [
            _latex_escape(current_model),
            _latex_escape(str(row.get("Prompt", ""))),
            _latex_escape(str(row.get("acc_static_percent", ""))),
            _latex_escape(str(row.get("acc_cons_percent", ""))),
            _latex_escape(str(row.get("hdr_percent", ""))),
            _latex_escape(str(row.get("mvr_percent", ""))),
            _latex_escape(str(row.get("fur_percent", ""))),
        ]
        lines.append(" & ".join(row_values) + r" \\")
        prev_model = current_model

    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table*}",
    ]
    return "\n".join(lines)


def rq4_table() -> str:
    rows = _load_rows(INPUT_CSV)
    latex = _to_latex_table(rows)

    with open(OUTPUT_TEX, "w", encoding="utf-8") as f:
        f.write(latex)

    print(latex)
    print(f"\n✅ LaTeX table successfully saved to: {OUTPUT_TEX}")
    return latex


if __name__ == "__main__":
    rq4_table()
