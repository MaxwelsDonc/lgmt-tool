# LGMT Reproduction & Verification Checklist

A step-by-step playbook for verifying that the tool works as documented and
that every advertised capability actually behaves as expected. Run this
**before every push** (or at least before any release / submission-relevant
snapshot). Every step lists the command, the expected result, and how to
judge PASS/FAIL.

Prerequisites: Python ≥ 3.10, Git. No API key needed (everything below runs
offline except the explicitly marked optional step).

---

## 0. Fresh start

```bash
git clone https://github.com/MaxwelsDonc/lgmt-tool.git lgmt-verify && cd lgmt-verify
python -m venv .venv && source .venv/bin/activate   # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e .
```

- **PASS:** `lgmt --help` prints usage with the five subcommands
  (`build-mgs`, `demo`, `run`, `report`, `audit`) plus `list-mrs` and `web`.

## 1. README walkthrough (literal)

Follow README "Try it → Option 2" and "Evaluate a real model" (offline
variants) exactly as written.

- `lgmt demo`
  - **PASS:** finishes in < 30 s; prints an MVR table (ALL row **60.00%** on
    the mock-flawed persona); writes `demo_output/report.html`.
- `lgmt demo --full`
  - **PASS:** loads **3,091** groups; overwrites `demo_output/` (this is
    documented behavior).
- Open `demo_output/report.html`
  - **PASS:** leaderboard shows 6 reference models + your run highlighted;
    sortable column headers; metric cards; per-group section with filters.

## 2. Capability test points

### 2.1 All commands respond

```bash
for c in demo build-mgs run report audit list-mrs web; do lgmt $c --help >/dev/null || echo "FAIL: $c"; done
```

- **PASS:** no FAIL lines.

### 2.2 MR registry integrity (red line — never broken)

```bash
python tools/mr_smoke_compare.py
```

- **PASS:** all 20 MRs report `OK` and final line is `ALL MATCH`.
- **FAIL = stop.** The MR transformation layer is the scientific core; any
  drift must be investigated before anything else.

### 2.3 Built-in MR count and lookup

```bash
lgmt list-mrs
```

- **PASS:** 20 rows; first `MR-S1`, last `MR-E2.4`.

### 2.4 Web Studio (zero-dependency) and Gradio fallback

```bash
lgmt web --port 7860 &        # open http://localhost:7860 → three workflow tabs
lgmt web --gradio --port 7860 # requires: pip install -r requirements-web.txt
```

- **PASS (native):** HTTP 200 without gradio installed; three tabs usable.
- **PASS (gradio):** launches the Gradio UI when gradio is present.

### 2.5 NL→FOL synthesis (custom cases, LLM-only)

```bash
echo '{"premises_text": ["All birds can fly.", "Tweety is a bird."], "conclusion_text": "Tweety can fly."}' > /tmp/nl.jsonl
lgmt build-mgs --input /tmp/nl.jsonl --output /tmp/nl_mgs.jsonl --mock consistent
```

- **PASS:** exits non-zero with *"the mock cannot translate"* (LLM-only by
  design; offline mock must refuse).
- With a real model configured (`LGMT_API_KEY` or interactive prompt):
  `lgmt build-mgs --input /tmp/nl.jsonl --output /tmp/nl_mgs.jsonl --model <model>`
  must synthesize FOL and build MGs; fully-annotated inputs must **not**
  trigger translation (folio source file builds unchanged, see 2.2).

### 2.6 Interactive API key entry

- TTY, no key configured: run any real-model command → password-style
  prompt `Enter your API key (input hidden)…`; typed text is not echoed.
- Non-TTY (pipe/CI): same command → clean error, **no prompt**.

### 2.7 Multi-model leaderboard

```bash
LGMT_MOCK=flawed BENCH=lgmt/demo/demo_mgs.jsonl bash examples/run_multiple_models.sh m1 m2
```

- **PASS:** `runs/results_*.jsonl` × 2 and `runs/report.html` with both
  models ranked (mutual comparison on user data).

### 2.8 Custom MR auto-registration

Create `lgmt/mrs/premise/mrx9.py` with a concrete subclass (see README
"Extending"), then:

```bash
python -c "from lgmt.mrs import ALL_MRS, get_mr; print(len(ALL_MRS), get_mr('MR-X9').name)"
lgmt build-mgs --input /tmp/nl.jsonl --output /tmp/x9.jsonl --mr MR-X9 --no-realize
```

- **PASS:** 21 MRs registered (20 built-ins + yours); build succeeds.
- Delete the file → back to 20.

### 2.9 Parse-failure isolation (metric hygiene)

Simulate a client that always fails parsing (or inspect `tests/test_parse_failures.py`):

- **PASS:** failed groups are excluded from every denominator and counted as
  `failed` in the report meta line (visible, never silent).

### 2.10 Test suite & cross-platform CI

```bash
pip install -e ".[dev]" && pytest
```

- **PASS:** **125 passed, 5 skipped** (the 5 skips are rare-MR applicability
  scans, expected). If the count changes, find out which tests were added or
  lost and why.
- GitHub → Actions: every job green on the latest push
  (pytest 12-combo matrix, `readme-smoke` ×3 OS, `docker-build`).

## 3. Submission-grade gates

| Gate | Command / check | Expected |
|---|---|---|
| MR red line | `tools/mr_smoke_compare.py` | ALL MATCH |
| Suite | `pytest` | 125 passed, 5 skipped |
| README literal | section 1 above | all PASS |
| No placeholders | `grep -rn "TODO\|FIXME\|<org>" --include="*.py" --include="*.md" .` | no hits |
| English only | `grep -rP '[\x{4e00}-\x{9fff}]' README.md DEPLOY.md lgmt/ --include="*.md" --include="*.py"` | no hits |
| Brand | `grep -rn "Logic-Guided" .` | no hits (paper name is Logic-**Grounded**) |
| CI | GitHub Actions latest run | all jobs success |

## 4. Behavior-change disclosure

If your change alters **prompts**, **metric definitions**, **default
semantics**, or any user-visible output, mark it in the commit message with
`behavioral change:` so reviewers of the diff know to pay attention.

---

*Last updated: 2026-10-15. When capabilities change, update the expected
values in this file in the same commit.*
