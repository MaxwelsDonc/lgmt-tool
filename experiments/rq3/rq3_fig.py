import json
import os

import matplotlib.pyplot as plt


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_JSON = os.path.join(CURRENT_DIR, "rq3_sensitivity_zero_cot.json")
OUTPUT_PNG = os.path.join(CURRENT_DIR, "rq3_average_mvr_across_categories.png")
CATEGORY_ORDER = ["MR-E", "MR-S", "MR-P", "MR-C"]

# Font-size knobs for paper figure tuning:
# - AXIS_LABEL_FONT_SIZE controls x/y axis label font size.
# - TICK_LABEL_FONT_SIZE controls x/y tick font size.
# - VALUE_LABEL_FONT_SIZE controls bar-top value text font size.
AXIS_LABEL_FONT_SIZE = 13
TICK_LABEL_FONT_SIZE = 13
VALUE_LABEL_FONT_SIZE = 13


def _load_category_average_mvr_percent(json_path: str) -> list[float]:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    rows = data.get("tables", {}).get("category_csv_rows", [])
    rows_by_category = {
        str(row.get("Category", "")): row for row in rows if isinstance(row, dict)
    }

    values: list[float] = []
    for category in CATEGORY_ORDER:
        row = rows_by_category.get(category, {})
        ratio = float(row.get("Average", 0.0))
        values.append(ratio * 100.0)
    return values


def main() -> None:
    mvr_values = _load_category_average_mvr_percent(INPUT_JSON)

    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(CATEGORY_ORDER, mvr_values, width=0.5)

    ax.set_xlabel("MR Category", fontsize=AXIS_LABEL_FONT_SIZE)
    ax.set_ylabel("MVR (%)", fontsize=AXIS_LABEL_FONT_SIZE)
    ax.set_ylim(0, 40)
    ax.tick_params(axis="both", labelsize=TICK_LABEL_FONT_SIZE)

    for bar, value in zip(bars, mvr_values):
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            value + 0.5,
            f"{value:.2f}%",
            ha="center",
            va="bottom",
            fontsize=VALUE_LABEL_FONT_SIZE,
        )

    fig.tight_layout()
    fig.savefig(OUTPUT_PNG, dpi=300, bbox_inches="tight")
    plt.close(fig)

    print(f"✅ Figure saved to: {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
