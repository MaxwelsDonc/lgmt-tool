# LGMT — Logic-Guided Metamorphic Testing for LLM Logical Reasoning

[![CI](https://github.com/MaxwelsDonc/lgmt-tool/actions/workflows/ci.yml/badge.svg)](https://github.com/MaxwelsDonc/lgmt-tool/actions/workflows/ci.yml)
[![Python ≥3.10](https://img.shields.io/badge/python-≥3.10-blue.svg)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## Overview

LGMT evaluates the logical-reasoning reliability of large language models
with metamorphic testing grounded in first-order logic. It applies 20
semantics-preserving FOL transformations (metamorphic relations) to
entailment test cases, probes the model under test on every source /
follow-up pair, and flags **metamorphic violations** — inconsistent
verdicts that expose fragile, non-invariant reasoning. The framework and
its 20 MRs are described in the companion KBS paper (see
[Citation](#citation)).

![LGMT architecture](docs/architecture.png)

## Installation

**Prerequisites:** Python ≥ 3.10 with pip. An API key is *not* required —
the offline demo and the whole test suite run without one; you only need a
key to evaluate real models.

```bash
git clone https://github.com/MaxwelsDonc/lgmt-tool.git
cd lgmt-tool
python -m venv .venv && source .venv/bin/activate   # Windows: see Platform Notes
pip install -r requirements.txt
pip install -e .
```

Docker is a zero-setup alternative (see [Docker](#docker) below).

## Quick Start

```bash
lgmt demo
```

This runs the full pipeline offline — a mock model with a deliberately
flawed persona over 40 bundled metamorphic groups — and writes
`demo_output/results.jsonl` plus an HTML report:

```
[demo] Offline mode: 40 demo MGs, mock persona='flawed', prompting='zero_direct'. No API calls will be made.
scope       total      MVR  acc_src  acc_cons      HDR      FUR
--------------------------------------------------------------
ALL            40   60.00%  100.00%    40.00%   60.00%    0.00%
C               8    0.00%                       0.00%    0.00%
E              16  100.00%                     100.00%    0.00%
P               8  100.00%                     100.00%    0.00%
S               8    0.00%                       0.00%    0.00%
HTML report generated: .../demo_output/report.html
```

Open `demo_output/report.html` in a browser: a leaderboard comparing your
run against six reference models, metric cards, and per-group evidence
cards with verdict badges.

## Usage

### CLI commands

| Command | Purpose |
|---|---|
| `lgmt demo` | Offline end-to-end run on the 40-group demo set (mock model, no key) |
| `lgmt demo --full` | Offline run on the full 3,091-group benchmark |
| `lgmt build-mgs` | Source test cases → metamorphic groups (MR transform + optional NL realize) |
| `lgmt run` | Entailment inference over MGs + metamorphic oracle consistency check |
| `lgmt report` | Metrics (MVR / acc / HDR / FUR) + self-contained HTML report |
| `lgmt audit` | Back-translation fidelity audit of realized natural language |

Key flags (every subcommand accepts `--help`):

| Flag | Command | Meaning |
|---|---|---|
| `--input` / `--output` | `build-mgs` | source-case JSONL in / MG JSONL out |
| `--no-realize` | `build-mgs` | keep the tagged FOL skeleton instead of LLM Logic→NL back-translation |
| `--mr MRE15` (repeatable) | `build-mgs` | restrict to specific MRs (class name or `MR-E1.5`) |
| `--mgs` / `--output` | `run`, `audit` | MG JSONL in / results JSONL out |
| `--model` | `run`, `report` | model name or alias (config / env / CLI) |
| `--prompting` | `run`, `report`, `demo` | `zero_direct` / `zero_cot` / `few_direct` / `few_cot` |
| `--temperature` | `run` | sampling temperature (ignored for reasoning models) |
| `--mock consistent\|flawed` | `run`, `build-mgs`, `audit` | offline mock model, no API calls |
| `--results` (repeatable) | `report` | one file per model → same-data multi-model leaderboard |
| `--full` | `demo` | use the 3,091-group benchmark instead of the demo set |
| `--config` | all | path to a YAML config file (default `config.yaml` if present) |

### Evaluate a real model

```bash
export LGMT_API_KEY=sk-...
export LGMT_BASE_URL=https://api.openai.com/v1   # any OpenAI-compatible endpoint

lgmt run --mgs mgs.jsonl --output results.jsonl --model gpt-4o --prompting zero_cot
lgmt report --results results.jsonl --mgs mgs.jsonl --output report.html
```

**Configuration precedence:** CLI flags > `LGMT_API_KEY` / `LGMT_BASE_URL`
/ `LGMT_MODEL` environment variables > `config.yaml` (copy
`config.example.yaml`) > built-in defaults.

**Cost transparency.** Evaluating the full 3,091-group benchmark issues
one entailment judgment per source case and per follow-up case — **6,182
API calls** per model/prompting combination. Depending on the preset and
output length this is on the order of 10⁷ input+output tokens; multiply by
your provider's per-token price for an exact figure. Reasoning models are
typically the most expensive per call.

### Docker

```bash
docker build -t lgmt .
docker run --rm lgmt                  # offline demo (mock model, no key needed)
docker run --rm -p 7860:7860 lgmt lgmt-web   # Gradio web demo on :7860
```

## Platform Notes

The code paths are identical on Windows, macOS, and Linux (all file I/O is
UTF-8, paths are handled portably). Only the virtualenv activation differs:

- **Windows (PowerShell):**
  `.\.venv\Scripts\Activate.ps1` — if execution policy blocks it, run
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` first.
- **Windows (cmd):** `.\.venv\Scripts\activate.bat`
- **macOS / Linux:** `source .venv/bin/activate`

On Windows consoles we recommend `set PYTHONIOENCODING=utf-8` (PowerShell:
`$env:PYTHONIOENCODING="utf-8"`) so logic symbols always print cleanly —
the CLI itself already forces UTF-8 output where possible. If anything
else behaves differently, Docker is the universal fallback.

## Output & Reports

`lgmt report` produces a **single self-contained HTML file** (inline
CSS/JS, opens offline by double-click) organized as an evidence chain:

1. **Leaderboard** — your run ranked against six reference models (only on
   matching evaluation calibers), sortable columns, MVR inline bars.
2. **Metrics** — MVR / HDR / violation-count cards plus per-category and
   per-MR tables; every violation count links into the per-group view.
3. **Per-group evidence** — verdict badges and side-by-side FOL/NL
   comparisons for every group, with violations-only filtering, category
   and keyword filters, and lazy rendering that keeps the 3,091-group
   report (~10 MB) snappy.

Artifacts written by the pipeline: `results.jsonl` (per-group verdicts
with model/prompting metadata), `report.html`, and a `logs/` directory.

## Data

Three tiers ship in this repository (see [data/README.md](data/README.md)
for provenance, schemas, and per-dataset licensing):

- `lgmt/demo/demo_mgs.jsonl` — 40 demo groups used by `lgmt demo`.
- `data/metamorphic_group/processed_mgs_core/processed_mgs_200.jsonl` —
  the 3,091-group evaluation benchmark (folio 2,673 / proverqa 325 /
  logicnli 93).
- `data/source_test_case/` — 6,740 source entailment cases from FOLIO,
  LogicNLI, and ProverQA for building your own groups.

## Extending LGMT with a custom MR

Implement three methods on the `MetamorphicRelation` base class:

```python
from lgmt.core.structure import MetamorphicRelation, TestCase

class MyMR(MetamorphicRelation):
    def __init__(self):
        self.index = "MR-X1"
        self.name = "My Relation"

    def check_applicability(self, test_case: TestCase) -> bool: ...
    def source_templates(self) -> list[str]: ...
    def transform(self, source_case: TestCase) -> TestCase: ...
```

Formula-level rewrites can subclass `MetamorphicTransform`
(`lgmt.mrs.equivalence.equivalence_utils`) with just a `LogicTransformer` +
`LogicChecker` visitor. Equivalence preservation of every MR is guarded by
`tests/test_mr_equivalence.py` (Z3-backed) and
`tools/mr_smoke_compare.py` (baseline diff).

## Troubleshooting

<details>
<summary><b>UnicodeEncodeError / garbled logic symbols on Windows</b></summary>

The CLI forces UTF-8 on stdout/stderr where the console allows it. If you
still see `UnicodeEncodeError`, set `PYTHONIOENCODING=utf-8` before running
(`$env:PYTHONIOENCODING="utf-8"` in PowerShell).
</details>

<details>
<summary><b>z3-solver fails to install</b></summary>

The test suite needs `z3-solver>=4.12` (pinned in requirements-dev.txt) —
older releases have no prebuilt Windows wheels and fall back to compiling
from source. Upgrade pip first (`pip install -U pip`); if compilation
still fails, use the conda route: `conda install -c conda-forge z3-solver`.
The tool itself runs without z3.
</details>

<details>
<summary><b>NLTK data / LookupError</b></summary>

LGMT only uses NLTK's pure-parser (`nltk.sem.logic.LogicParser`) and needs
**no downloaded data packages** (verified by running the demo with an
empty `NLTK_DATA`). If you repurpose the code for other NLTK features,
install their data with `python -m nltk.downloader <package>`.
</details>

<details>
<summary><b>"Error: no API key configured"</b></summary>

Real-model commands need a key: export `LGMT_API_KEY` (and
`LGMT_BASE_URL` for non-OpenAI endpoints), or copy `config.example.yaml`
to `config.yaml` and fill in `model.api_key`. Use `--mock` for offline
runs.
</details>

<details>
<summary><b>SSL / proxy errors behind corporate networks</b></summary>

Point `SSL_CERT_FILE` (and `REQUESTS_CA_BUNDLE`) at your CA bundle, or
configure `HTTPS_PROXY`/`HTTP_PROXY`. For the httpx-based client these
standard environment variables are honored.
</details>

## Repository layout

```
lgmt/               the Python package (core / mrs / prompts / models / utils)
data/               source test cases and the 3,091-group benchmark
docs/               assets (architecture figure)
tools/              MR regression checker — `python tools/mr_smoke_compare.py`
                    (full RQ1–RQ4 experiment scripts live in the companion
                    paper's research repository, not here)
tests/              pytest suite (MR equivalence, labels, mock, CLI, report)
```

## Citation

The framework and the 20 metamorphic relations are described in the
companion KBS paper:

> Zenghui Zhou et al. "LGMT: Logic-Grounded Metamorphic Testing for
> Evaluating the Reasoning Reliability of LLMs." *Knowledge-Based
> Systems*, 2026 (in press).

If you use this tool, please also cite the tool demonstration paper:

> Zenghui Zhou et al. "LGMT: A Tool for Testing the Logical Reasoning
> Reliability of LLMs via Logic-Grounded Metamorphic Relations." *ICSE
> 2027 — Tool Demonstration Track*, under review.

```bibtex
@article{zhou2026lgmt,
  title   = {LGMT: Logic-Grounded Metamorphic Testing for Evaluating the
             Reasoning Reliability of {LLMs}},
  author  = {Zhou, Zenghui and others},
  journal = {Knowledge-Based Systems},
  year    = {2026},
  note    = {in press},
}

@inproceedings{zhou2027lgmt-tool,
  title     = {LGMT: A Tool for Testing the Logical Reasoning Reliability
               of {LLMs} via Logic-Grounded Metamorphic Relations},
  author    = {Zhou, Zenghui and others},
  booktitle = {Proceedings of the 49th International Conference on
               Software Engineering (ICSE) -- Tool Demonstration Track},
  year      = {2027},
  note      = {under review},
}
```

## License

[MIT](LICENSE) — Copyright (c) 2026 Zenghui Zhou and contributors.

Note: the source datasets that the bundled evaluation data derives from
(FOLIO, LogicNLI, ProverQA) carry their own licenses — see
[data/README.md](data/README.md) for the full data-provenance statement.
