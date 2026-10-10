# LGMT — Logic-Grounded Metamorphic Testing for LLM Logical Reasoning

[![CI](https://github.com/MaxwelsDonc/lgmt-tool/actions/workflows/ci.yml/badge.svg)](https://github.com/MaxwelsDonc/lgmt-tool/actions/workflows/ci.yml)
[![Python ≥3.10](https://img.shields.io/badge/python-≥3.10-blue.svg)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**LGMT checks whether an LLM reasons *consistently*.** It rewrites logical
reasoning problems into provably equivalent variants (20 metamorphic
relations grounded in first-order logic), asks the model both versions, and
flags every case where the model contradicts itself — no ground-truth labels
needed. Works with any OpenAI-compatible endpoint (commercial APIs, local
vLLM/Ollama), on Windows, macOS, and Linux.

![An LGMT report: your model ranked against six reference LLMs, with per-group violation evidence](docs/report-screenshot.png)

## Quick Start (60 seconds, no API key)

```bash
git clone https://github.com/MaxwelsDonc/lgmt-tool.git
cd lgmt-tool
python -m venv .venv && source .venv/bin/activate  # Windows: see Platform Notes
pip install -r requirements.txt && pip install -e .
lgmt demo
```

This runs the full pipeline offline — 40 bundled metamorphic groups against
a mock model — and opens an HTML report (screenshot above): a **leaderboard**
ranking your run against six reference LLMs, **metric cards** (MVR / HDR /
violations), and **per-group evidence** showing each inconsistent verdict
side by side. `lgmt demo --full` runs the same tour on the full 3,091-group
benchmark. Docker users: `docker build -t lgmt . && docker run --rm lgmt`.

## Evaluate your own model

```bash
export LGMT_API_KEY=sk-...
export LGMT_BASE_URL=https://api.openai.com/v1   # any OpenAI-compatible endpoint

lgmt run --mgs data/metamorphic_group/processed_mgs_core/processed_mgs_200.jsonl \
         --model your-model --output results.jsonl
lgmt report --results results.jsonl --output report.html
```

Your model is inserted into the reference leaderboard automatically. To test
your own premise–conclusion cases instead, write them as JSONL and run
`lgmt build-mgs --input my_cases.jsonl --output my_mgs.jsonl` first (no FOL
knowledge or ground-truth labels needed). Config precedence: CLI flags >
`LGMT_API_KEY` / `LGMT_BASE_URL` / `LGMT_MODEL` env vars > `config.yaml` >
defaults.

**Cost transparency.** The full benchmark issues one judgment per source and
per follow-up case — **6,182 API calls** per model (on the order of 10⁷
tokens; multiply by your provider's price).

## CLI reference

| Command | Purpose |
|---|---|
| `lgmt demo [--full]` | Offline tour on 40 groups (or the full 3,091-group benchmark) |
| `lgmt build-mgs --input cases.jsonl --output mgs.jsonl` | Build metamorphic groups (MR transform + NL realization; `--no-realize` keeps FOL skeletons; `--mr MRE15` repeatable) |
| `lgmt run --mgs mgs.jsonl --output results.jsonl` | Inference + metamorphic consistency check (`--model`, `--prompting`, `--temperature`, `--mock consistent\|flawed`) |
| `lgmt report --results results.jsonl --output report.html` | Metrics + self-contained HTML report (`--results` accepts multiple files for a multi-model leaderboard) |
| `lgmt audit --mgs mgs.jsonl --output audit.jsonl` | Back-translation fidelity audit |

Every subcommand accepts `--help` and `--config`.

## Platform Notes

Identical code paths on Windows, macOS, and Linux (UTF-8 I/O, portable paths;
CI runs the test suite on all three). Only virtualenv activation differs:

- **Windows PowerShell:** `.\.venv\Scripts\Activate.ps1` (if blocked:
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`)
- **Windows cmd:** `.\.venv\Scripts\activate.bat`
- **macOS / Linux:** `source .venv/bin/activate`

On Windows consoles, `set PYTHONIOENCODING=utf-8` keeps logic symbols
printing cleanly. If anything else misbehaves, Docker is the universal
fallback.

## Data

Bundled with the repo (provenance and licensing in
[data/README.md](data/README.md)):

- `lgmt/demo/demo_mgs.jsonl` — 40 demo groups used by `lgmt demo`.
- `data/metamorphic_group/processed_mgs_core/processed_mgs_200.jsonl` — the
  3,091-group benchmark used in the paper's experiments.
- `data/source_test_case/` — 6,740 source cases (FOLIO / LogicNLI / ProverQA)
  for building your own groups.

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

Equivalence preservation of every built-in MR is guarded by
`tests/test_mr_equivalence.py` (Z3-backed) and `tools/mr_smoke_compare.py`.

## Troubleshooting

<details>
<summary><b>UnicodeEncodeError / garbled logic symbols on Windows</b></summary>

The CLI forces UTF-8 on stdout/stderr where the console allows it. If you
still see `UnicodeEncodeError`, set `PYTHONIOENCODING=utf-8` before running
(`$env:PYTHONIOENCODING="utf-8"` in PowerShell).
</details>

<details>
<summary><b>z3-solver fails to install (only needed for tests)</b></summary>

The test suite needs `z3-solver>=4.12`; older releases lack prebuilt Windows
wheels. Upgrade pip first (`pip install -U pip`); if compilation still
fails, use `conda install -c conda-forge z3-solver`. The tool itself runs
without z3.
</details>

<details>
<summary><b>NLTK data / LookupError</b></summary>

LGMT uses only NLTK's pure parser (`nltk.sem.logic.LogicParser`) and needs
**no downloaded data packages** (verified with an empty `NLTK_DATA`). If you
repurpose the code for other NLTK features, install their data with
`python -m nltk.downloader <package>`.
</details>

<details>
<summary><b>"Error: no API key configured"</b></summary>

Real-model commands need a key: export `LGMT_API_KEY` (and `LGMT_BASE_URL`
for non-OpenAI endpoints), or copy `config.example.yaml` to `config.yaml`
and fill in `model.api_key`. Use `--mock` for offline runs.
</details>

<details>
<summary><b>SSL / proxy errors behind corporate networks</b></summary>

Point `SSL_CERT_FILE` (and `REQUESTS_CA_BUNDLE`) at your CA bundle, or set
`HTTPS_PROXY`/`HTTP_PROXY` — the httpx-based client honors these standard
environment variables.
</details>

## Repository layout

```
lgmt/    the Python package (core / mrs / prompts / models / utils)
data/    source test cases and the 3,091-group benchmark
docs/    assets (report screenshot, TikZ architecture figure)
tools/   MR regression checker — `python tools/mr_smoke_compare.py`
tests/   pytest suite (MR equivalence, labels, mock, CLI, report)
```

(Full RQ1–RQ4 experiment scripts live in the companion paper's research
repository, not here.)

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
