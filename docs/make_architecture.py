"""Redraw README architecture figure — modern card style, high-DPI PNG."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle

BLUE   = "#2f5f8f"
CARD   = "#ffffff"
BORDER = "#c8d6e5"
TEXT   = "#1f2937"
MUTED  = "#64748b"
AMBER  = "#b45309"
AMBBG  = "#fdf3e3"
GREEN  = "#2f7d4f"
GREENBG= "#eef7f0"

fig, ax = plt.subplots(figsize=(12.4, 5.0), dpi=200)
ax.set_xlim(0, 124)
ax.set_ylim(0, 50)
ax.axis("off")
fig.patch.set_facecolor("#fbfcfe")
ax.set_facecolor("#fbfcfe")

def card(x, y, w, h, fc=CARD, ec=BORDER, lw=1.2, r=1.6):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                                fc=fc, ec=ec, lw=lw, zorder=2))

def text(x, y, s, size=9, color=TEXT, weight="normal", ha="center", va="center", mono=False, z=4):
    ax.text(x, y, s, ha=ha, va=va, fontsize=size, color=color, fontweight=weight,
            family="monospace" if mono else "DejaVu Sans", zorder=z)

# ---------- top: interface pills ----------
pills = [
    ("CLI", "lgmt build-mgs · run · report · audit · demo", 3, 46),
    ("Python API", "", 46, 16),
    ("Web Demo", "", 63.5, 14),
    ("Docker", "", 79.5, 12),
]
x = 3
for name, sub, _, w in pills:
    card(x, 43.5, w, 4.6, fc="#eef3f9", ec="#b9cbe0", r=2.2)
    if sub:
        text(x + w/2, 45.9, f"{name}:  {sub}", size=8.2, color=BLUE, weight="bold", mono=True)
    else:
        text(x + w/2, 45.9, name, size=8.6, color=BLUE, weight="bold")
    x += w + 1.5
text(121, 45.9, "interfaces", size=7.5, color=MUTED, ha="right")

# connector from interfaces to pipeline
ax.add_patch(FancyArrowPatch((62, 43.3), (62, 40.6), arrowstyle="-", color="#b9cbe0", lw=1.4))

# ---------- middle: pipeline cards ----------
stages = [
    ("Case Loader", ["NL+FOL dual schema", "FOLIO · LogicNLI · ProverQA", "custom JSONL"]),
    ("MR Engine", ["FOL AST rewriting", "20 built-in MRs", "E / S / P / C levels"]),
    ("NL Realizer", ["FOL-to-NL via LLM", "strict translator", "fidelity audit"]),
    ("Inference\nRunner", ["any OpenAI-compat.", "4 prompt strategies", "schema-validated parsing"]),
    ("Oracle &\nReporter", ["consistency check", "MVR · Acc_cons · HDR", "HTML defect report"]),
]
w, h, gap, y0, x0 = 21.5, 15.8, 2.6, 26, 3
cx = x0
for i, (title, lines) in enumerate(stages, 1):
    card(cx, y0, w, h)
    # number badge
    ax.add_patch(Circle((cx + 3.2, y0 + h - 3.0), 1.55, fc=BLUE, ec="none", zorder=4))
    text(cx + 3.2, y0 + h - 3.05, str(i), size=9.5, color="white", weight="bold")
    nlines = title.count("\n") + 1
    text(cx + w/2 + 1.0, y0 + h - 3.0 - (nlines-1)*1.2, title, size=9.5, weight="bold", color=TEXT)
    for j, ln in enumerate(lines):
        text(cx + w/2, y0 + h - 6.4 - (nlines-1)*2.4 - j*2.55, ln, size=8.0, color=MUTED)
    if i < 5:
        ax.add_patch(FancyArrowPatch((cx + w + 0.35, y0 + h/2), (cx + w + gap - 0.35, y0 + h/2),
                                     arrowstyle="-|>", mutation_scale=16, color=BLUE, lw=1.8, zorder=3))
    cx += w + gap

# input / output chips
card(3, 21.2, 21.5, 3.4, fc=GREENBG, ec="#9dc9ab", r=1.8)
text(13.75, 22.9, "source cases (JSONL)", size=8.2, color=GREEN, mono=True)
ax.add_patch(FancyArrowPatch((13.75, 24.8), (13.75, 25.8), arrowstyle="-|>", mutation_scale=12, color=GREEN, lw=1.4))
card(3 + 4*(w+gap), 21.2, 21.5, 3.4, fc=GREENBG, ec="#9dc9ab", r=1.8)
text(3 + 4*(w+gap) + w/2, 22.9, "defects + metrics", size=8.2, color=GREEN, mono=True)
ax.add_patch(FancyArrowPatch((3 + 4*(w+gap) + w/2, 25.8), (3 + 4*(w+gap) + w/2, 24.8),
                             arrowstyle="-|>", mutation_scale=12, color=GREEN, lw=1.4))

# ---------- bottom: extension chips ----------
text(3, 16.4, "Extension points", size=9.5, color=AMBER, weight="bold", ha="left")
ext = [
    "custom MRs (3-method plugin, Z3-checked)",
    "custom datasets (open JSONL schema)",
    "any OpenAI-compatible model (API / vLLM / Ollama)",
    "offline mock (no key, no network)",
]
ex = [3, 37.5, 68, 102]; ew = [33, 29, 32.5, 21]
for (label, x, w2) in zip(ext, ex, ew):
    card(x, 11.6, w2, 3.8, fc=AMBBG, ec="#e3c89a", r=1.9)
    text(x + w2/2, 13.5, label, size=6.6, color=AMBER)
for xx in (3 + (w+gap) + w/2, 3 + 3*(w+gap) + w/2):
    ax.add_patch(FancyArrowPatch((xx, 25.8), (xx, 15.8), arrowstyle="-", color="#e3c89a", lw=1.1, zorder=1))

fig.savefig("/tmp/arch_v2.png", bbox_inches="tight", facecolor=fig.get_facecolor())
print("saved")
