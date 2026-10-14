# LGMT — Logic-Grounded Metamorphic Testing for LLM Logical Reasoning

[![CI](https://github.com/MaxwelsDonc/lgmt-tool/actions/workflows/ci.yml/badge.svg)](https://github.com/MaxwelsDonc/lgmt-tool/actions/workflows/ci.yml)
[![Python ≥3.10](https://img.shields.io/badge/python-≥3.10-blue.svg)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Check whether an LLM reasons *consistently*: rewrite its logical problems
into provably equivalent variants, ask both, and flag every self-contradiction.**

LGMT is the tool companion of *"LGMT: Logic-Grounded Metamorphic Testing for
Evaluating the Reasoning Reliability of LLMs"* (Knowledge-Based Systems, in
press). It packages that study's methodology into an extensible testing
pipeline:

- **20 first-order-logic metamorphic relations** — equivalence-law rewriting
  of FOL syntax trees (De Morgan, contraposition, quantifier dualities,
  premise restructuring, symbol renaming), with auto-discovery for custom MRs;
- **Z3-guarded correctness**: every built-in MR's equivalence preservation
  is verified by SMT-based tests (`tests/z3check.py`);
- **CLI + Zero-Dependency Web Studio** targeting any OpenAI-compatible
  endpoint — commercial APIs or local vLLM/Ollama — plus an offline mock
  mode that runs without an API key;
- **Self-contained HTML defect reports**: your model ranked against six
  reference SOTA LLMs, per-MR drill-down metrics, side-by-side FOL/NL diffs,
  and collapsible CoT reasoning traces;
- **Bundled 3,091-group evaluation benchmark** with documented provenance.

![An LGMT report: your model ranked against six reference LLMs, with per-group violation evidence](docs/report-screenshot.png)

## Three Workflows at a Glance

Depending on your goal, choose one of the three workflows below (available
both in the CLI and as the three tabs of `lgmt web`):

| Workflow | What you need | Command |
|---|---|---|
| **1. Quick Offline Tour**<br>*(Experience LGMT in 30s)* | **Nothing** — no API key, no network. Uses a deterministic mock model on bundled data. | `lgmt demo` *(40 groups)*<br>`lgmt demo --full` *(3,091 groups)* |
| **2. Benchmark a Model**<br>*(Rank an LLM against 6 SOTA models)* | **An API key** (or local vLLM/Ollama URL). Uses the bundled `demo` (40) or `benchmark` (3,091) set. | `lgmt run --mgs benchmark --model gpt-4o --output results.jsonl`<br>`lgmt report --results results.jsonl --output report.html` |
| **3. Test Custom Cases**<br>*(Audit your own domain rules)* | **An API key + a `.jsonl` file** of premise–conclusion pairs (pure English or NL+FOL; no labels needed). | `lgmt build-mgs --input examples/custom_cases.example.jsonl --output my_mgs.jsonl --model gpt-4o`<br>`lgmt run --mgs my_mgs.jsonl --model gpt-4o --output my_res.jsonl`<br>`lgmt report --results my_res.jsonl --output my_report.html` |

## Try it (Installation & Workflow 1)

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
python -m venv .venv && source .venv/bin/activate   # use python3 on macOS/Linux if python is missing; Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e .

lgmt demo            # 40 groups, offline mock model → demo_output/report.html
lgmt demo --full     # same tour on the full 3,091-group benchmark (overwrites demo_output/)
```

Open `demo_output/report.html` in any browser — the leaderboard, metric
cards, and side-by-side FOL/NL violation evidence open completely offline.
(On Windows consoles, `set PYTHONIOENCODING=utf-8` keeps logic symbols
printing cleanly.)

**Prefer a Web UI over the CLI?** Launch the built-in **LGMT Web Studio**
(zero extra dependencies — works immediately after `pip install -e .` or via
Docker):

```bash
lgmt web --port 7860
# or via Docker: docker run --rm -p 7860:7860 lgmt lgmt-web
```

Then open http://localhost:7860 to access the three guided workflow tabs
(**1. Quick Demo**, **2. Benchmark Your Model**, **3. Test Custom Cases**)
with live interactive report rendering.

## Workflow 2: Evaluate a real model on the benchmark

Works with any OpenAI-compatible endpoint (OpenAI, DeepSeek, Claude proxy,
or local vLLM / Ollama):

```bash
export LGMT_API_KEY=sk-...        # and LGMT_BASE_URL if not the default below
export LGMT_BASE_URL=https://api.deepseek.com
lgmt run --mgs benchmark --model deepseek-flash --output results.jsonl
lgmt report --results results.jsonl --output report.html       # your model joins the leaderboard
```

- **Dataset shorthands:** `--mgs benchmark` resolves to
  `data/metamorphic_group/processed_mgs_core/processed_mgs_3091.jsonl`
  (3,091 groups); `--mgs demo` resolves to the 40-group fast subset
  (explicit file paths also work).
- **Config precedence:** `--api-key` / other CLI flags > `LGMT_API_KEY` /
  `LGMT_BASE_URL` / `LGMT_MODEL` env vars > `config.yaml` > defaults. When
  the key is missing everywhere, the CLI prompts for it interactively on a
  terminal (hidden input; held in memory only).
- **Cost transparency:** The full 3,091-group benchmark issues one judgment
  per source and per follow-up case — **6,182 API calls** per model (~10⁷
  tokens; use `--mgs demo` for an 80-call fast check first).

## Workflow 3: Test your own domain cases

One test case = a few premise lines + one conclusion — **no FOL knowledge
and no ground-truth labels needed**. Paste plain English or Chinese sentences,
FOL formulas, or JSONL into the Web Studio's single smart input (or pass a
`.jsonl` file on the CLI); the backend sniffs the format, the LLM
synthesizes the logic, and NLTK's parser validates every formula:

```bash
lgmt build-mgs --input examples/custom_cases.example.jsonl \
               --output my_mgs.jsonl --model <your-model>
lgmt run --mgs my_mgs.jsonl --model <your-model> --output my_results.jsonl
lgmt report --results my_results.jsonl --output my_report.html
```

Records that already include `premises_logic` / `conclusion_logic` are
used as-is (`--mock` and `--no-realize` run fully offline for those).

To audit back-translation fidelity on generated MGs with an independent
judge model:

```bash
lgmt audit --mgs my_mgs.jsonl --output audit.jsonl --model <judge-model>
```

## Extending LGMT with a custom MR

Inspect all currently registered MRs at any time with:

```bash
lgmt list-mrs
```

To add a new MR, subclass `MetamorphicRelation` and implement four methods:

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

Every custom MR is **verified for logical equivalence with Z3 before it
can run** (five standard FOL samples; the check is skipped only via
`--no-verify`). Three ways to register:

- **Web Studio drawer:** in Workflow 3 click `➕ Register Custom MR`, edit
  the pre-filled template (the paper's Listing 1), and press
  `Verify with Z3 & Register` — a green bar confirms
  `Z3 Equivalence Verified (5/5)` and the MR joins the category row.
  *(Executes Python locally — only paste code you trust.)*
- **CLI file loading:** save the class in a `.py` file and pass it to any
  MR-consuming command:
  ```bash
  lgmt list-mrs --mr-file examples/custom_mr_example.py
  lgmt build-mgs --input my_cases.jsonl --output my_mgs.jsonl \
                 --mr-file my_mr.py --mr MR-X1 --no-realize
  ```
  ([examples/custom_mr_example.py](examples/custom_mr_example.py) is the
  runnable Listing 1 reference.)
- **Package drop-in:** save the class in any module under `lgmt/mrs/` — it
  is discovered and registered automatically on the next import.

The 20 built-in MRs use this exact API, and their equivalence preservation
is guarded by `tests/test_mr_equivalence.py` (Z3-backed).

## Tests

```bash
pip install -e ".[dev]"
pytest
```

MR equivalence (Z3-backed), label canonicalization, mock self-consistency,
NL→FOL synthesis, custom MR auto-discovery, CLI end-to-end, parse-failure
handling, and report/web rendering. CI runs the same suite on
Windows/macOS/Linux × Python 3.10–3.13.

## Repository layout

```
lgmt/      the Python package (core / mrs / prompts / models / utils / webapp)
data/      source test cases and the 3,091-group benchmark (see data/README.md)
docs/      assets (report screenshot, TikZ architecture figure)
examples/  custom case templates and multi-model evaluation driver
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
