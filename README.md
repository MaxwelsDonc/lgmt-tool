# LGMT — Logic-Grounded Metamorphic Testing for LLM Logical Reasoning

[![CI](https://github.com/MaxwelsDonc/lgmt-tool/actions/workflows/ci.yml/badge.svg)](https://github.com/MaxwelsDonc/lgmt-tool/actions/workflows/ci.yml)
[![Python ≥3.10](https://img.shields.io/badge/python-≥3.10-blue.svg)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Check whether an LLM reasons *consistently*: rewrite its logical problems
into provably equivalent variants, ask both, and flag every self-contradiction.**

LGMT is the tool companion of *"LGMT: Logic-Grounded Metamorphic Testing for
Evaluating the Reasoning Reliability of LLMs"* (Knowledge-Based Systems, in
press). It packages that study's methodology as a reusable tool:

- **20 first-order-logic metamorphic relations** — equivalence-law rewriting
  of FOL syntax trees (De Morgan, contraposition, quantifier dualities,
  premise restructuring, symbol renaming), with a three-method plugin API
  for adding your own;
- **Z3-guarded correctness**: every built-in MR's equivalence preservation
  is verified by SMT-based tests;
- a **five-command CLI** (`demo` / `build-mgs` / `run` / `report` / `audit`)
  targeting any OpenAI-compatible endpoint — commercial APIs or local
  vLLM/Ollama — plus a local Gradio web demo;
- a **self-contained HTML report**: your model ranked against six reference
  LLMs, per-MR metrics, and side-by-side violation evidence;
- a bundled **3,091-group evaluation benchmark** with documented provenance.

![An LGMT report: your model ranked against six reference LLMs, with per-group violation evidence](docs/report-screenshot.png)

## Try it

**Option 1 — Docker (nothing to install beyond Docker):**

```bash
docker build -t lgmt .
docker run --rm -v $(pwd)/demo_output:/app/demo_output lgmt   # offline demo; report lands in ./demo_output
```

**Option 2 — local install** (requires **Python ≥ 3.10**; no API key needed
for the offline demo):

```bash
git clone https://github.com/MaxwelsDonc/lgmt-tool.git
cd lgmt-tool
python -m venv .venv && source .venv/bin/activate   # macOS/Linux 无 python 时用 python3；Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e .

lgmt demo            # 40 groups, offline mock model → demo_output/report.html
lgmt demo --full     # same tour on the full benchmark (overwrites demo_output/)
```

Open `demo_output/report.html` — the leaderboard above is what you get.
(On Windows consoles, `set PYTHONIOENCODING=utf-8` keeps logic symbols
printing cleanly.)

**Prefer a UI over the CLI?** After installing (Option 1 or 2), launch the
local web demo — three tabs: offline demo, test-your-own-model, report
browser: `pip install -r requirements-web.txt && python -m lgmt.webapp`,
then open http://localhost:7860.

## Evaluate a real model

Works with any OpenAI-compatible endpoint:

```bash
export LGMT_API_KEY=sk-...                                     # and LGMT_BASE_URL if not OpenAI
lgmt run --mgs data/metamorphic_group/processed_mgs_core/processed_mgs_3091.jsonl \
         --model your-model --output results.jsonl
lgmt report --results results.jsonl --output report.html       # your model joins the leaderboard
```

Config precedence: CLI flags > `LGMT_API_KEY` / `LGMT_BASE_URL` /
`LGMT_MODEL` env vars > `config.yaml` > defaults.

**Cost transparency.** The full benchmark issues one judgment per source
and per follow-up case — **6,182 API calls** per model (~10⁷ tokens;
multiply by your provider's price).

**Your own test cases.** Write premise–conclusion pairs as JSONL and run
`lgmt build-mgs --input my_cases.jsonl --output my_mgs.jsonl` first — no FOL
knowledge or ground-truth labels needed; `--no-realize` (FOL-skeleton
output) and `--mock` run fully offline.

## Tests

```bash
pip install -e ".[dev]"
pytest        # 78 passed, 5 skipped (rare-MR applicability skips)
```

MR equivalence (Z3-backed), label canonicalization, mock self-consistency,
CLI end-to-end, parse-failure handling, and report rendering. CI runs
the same suite on Windows/macOS/Linux × Python 3.10–3.13.

## Extending LGMT with a custom MR

```python
from lgmt.core.structure import MetamorphicRelation, TestCase

class MyMR(MetamorphicRelation):
    def __init__(self):
        self.index = "MR-X1"          # unique id, shown in reports
        self.name = "My Relation"     # human-readable name

    def check_applicability_logic(self, fol: str) -> bool:
        ...                            # can a single FOL formula use this MR?

    def source_templates(self) -> list[str]:
        return []                      # minimal applicable patterns ([] = universal)

    def check_applicability(self, tc: TestCase) -> bool:
        ...                            # can this test case use this MR?

    def transform(self, tc: TestCase) -> TestCase:
        ...                            # return the follow-up case (Γ, q) => (Γ', q')
```

Save the class in any module under `lgmt/mrs/` (e.g.
`lgmt/mrs/premise/mrx1.py`) — it is discovered and registered
automatically on the next import, no `__init__.py` edit needed. Then use
it like any built-in MR:

```bash
lgmt build-mgs --input my_cases.jsonl --output my_mgs.jsonl --mr MR-X1 --no-realize
```

The 20 built-in MRs use exactly this API, and their equivalence
preservation is guarded by `tests/test_mr_equivalence.py` (Z3-backed).

## Repository layout

```
lgmt/      the Python package (core / mrs / prompts / models / utils / webapp)
data/      source test cases and the 3,091-group benchmark (see data/README.md)
docs/      assets (report screenshot, TikZ architecture figure)
examples/  multi-model evaluation driver (run_multiple_models.sh)
tools/     MR regression checker — `python tools/mr_smoke_compare.py`
tests/     pytest suite
```

Full RQ1–RQ4 experiment scripts live in the companion paper's research
repository, not here.

## License & attribution

Code: [MIT](LICENSE). The bundled data derives from FOLIO, LogicNLI, and
ProverQA under their own terms — see
[data/README.md](data/README.md). If you use this tool, please cite the
companion paper.

## Citation

```bibtex
@article{zhou2026lgmt,
  author  = {Zhou, Zenghui and others},
  title   = {LGMT: Logic-Grounded Metamorphic Testing for Evaluating the
             Reasoning Reliability of {LLMs}},
  journal = {Knowledge-Based Systems},
  year    = {2026},
  note    = {in press},
}
```
