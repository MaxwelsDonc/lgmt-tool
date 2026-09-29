import csv
import math
import os
from typing import Any

import matplotlib.pyplot as plt
import numpy as np


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_CSV = os.path.join(CURRENT_DIR, "rq4_mitigation_main_table.csv")
OUTPUT_HDR = os.path.join(CURRENT_DIR, "rq4_hdr_heatmap.png")
OUTPUT_FUR = os.path.join(CURRENT_DIR, "rq4_fur_heatmap.png")

MODEL_ORDER = [
    "GPT-5.2",
    "Claude 4.5 Sonnet",
    "Llama 3.3",
    "DeepSeek Chat",
    "o4-mini",
    "DeepSeek Reasoner",
]

PROMPT_ORDER = [
    "Zero-shot",
    "Zero-shot CoT",
    "Few-shot",
    "Few-shot CoT",
]

# Font-size knobs (aligned with rq3_fig.py style):
# - TITLE_FONT_SIZE controls heatmap title font size.
# - AXIS_LABEL_FONT_SIZE controls x/y axis label font size.
# - TICK_LABEL_FONT_SIZE controls x/y tick font size.
# - VALUE_LABEL_FONT_SIZE controls each cell annotation font size.
# - COLORBAR_LABEL_FONT_SIZE controls colorbar label font size.
# - COLORBAR_TICK_FONT_SIZE controls colorbar tick font size.
TITLE_FONT_SIZE = 13
AXIS_LABEL_FONT_SIZE = 13
TICK_LABEL_FONT_SIZE = 13
VALUE_LABEL_FONT_SIZE = 13
COLORBAR_LABEL_FONT_SIZE = 13
COLORBAR_TICK_FONT_SIZE = 13


def _load_rows(path: str) -> list[dict[str, str]]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return [row for row in reader if isinstance(row, dict)]


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _build_matrix(rows: list[dict[str, str]], field_name: str) -> np.ndarray:
    value_map: dict[tuple[str, str], float] = {}
    for row in rows:
        model = str(row.get("Model", ""))
        prompt = str(row.get("Prompt", ""))
        value_map[(model, prompt)] = _to_float(row.get(field_name, 0.0))

    matrix = np.zeros((len(MODEL_ORDER), len(PROMPT_ORDER)))
    for i, model in enumerate(MODEL_ORDER):
        for j, prompt in enumerate(PROMPT_ORDER):
            matrix[i, j] = value_map.get((model, prompt), 0.0) * 100.0
    return matrix


def _draw_heatmap(matrix: np.ndarray, colorbar_label: str, output_path: str, vmax: float) -> None:
    fig, ax = plt.subplots(figsize=(7, 5.2))
    # im = ax.imshow(matrix, aspect="auto", vmin=0, vmax=vmax)
    im = ax.imshow(matrix, aspect="auto", vmin=0, vmax=vmax, cmap="viridis_r")

    ax.set_xticks(np.arange(len(PROMPT_ORDER)))
    ax.set_yticks(np.arange(len(MODEL_ORDER)))
    ax.set_xticklabels(PROMPT_ORDER, fontsize=TICK_LABEL_FONT_SIZE)
    ax.set_yticklabels(MODEL_ORDER, fontsize=TICK_LABEL_FONT_SIZE)
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")

    ax.set_xticks(np.arange(-0.5, len(PROMPT_ORDER), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(MODEL_ORDER), 1), minor=True)
    ax.grid(which="minor", color="white", linestyle="-", linewidth=1)
    ax.tick_params(which="minor", bottom=False, left=False)

    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label(colorbar_label, fontsize=COLORBAR_LABEL_FONT_SIZE)
    cbar.ax.tick_params(labelsize=COLORBAR_TICK_FONT_SIZE)

    threshold = matrix.max() * 0.55
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            value = matrix[i, j]
            text_color = "white" if value > threshold else "black"
            ax.text(
                j,
                i,
                f"{value:.2f}%",
                ha="center",
                va="center",
                color=text_color,
                fontsize=VALUE_LABEL_FONT_SIZE,
            )

    fig.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def rq4_fig() -> None:
    rows = _load_rows(INPUT_CSV)
    hdr_matrix = _build_matrix(rows, "hdr")
    fur_matrix = _build_matrix(rows, "fur")
    hdr_max = max(1.0, float(math.ceil(float(hdr_matrix.max()))))
    fur_max = max(1.0, float(math.ceil(float(fur_matrix.max()))))

    _draw_heatmap(hdr_matrix, "HDR (%)", OUTPUT_HDR, vmax=hdr_max)
    _draw_heatmap(fur_matrix, "FUR (%)", OUTPUT_FUR, vmax=fur_max)

    print(f"✅ HDR heatmap saved to: {OUTPUT_HDR}")
    print(f"✅ FUR heatmap saved to: {OUTPUT_FUR}")


if __name__ == "__main__":
    rq4_fig()
