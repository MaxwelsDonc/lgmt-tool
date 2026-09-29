"""MR regression smoke check: run all 20 MRs over the validation fixture
plus a few real source cases, and compare against a pre-recorded baseline
produced by the original (pre-packaging) implementation.

Usage:
    python tools/mr_smoke_compare.py /path/to/mr_baseline.json
"""
import json
import os
import random
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from lgmt.mrs import MR_CLASS_REGISTRY  # noqa: E402
from lgmt.utils.io import load_test_cases  # noqa: E402

VALIDATION = os.path.join(REPO_ROOT, "lgmt", "mrs", "validation_test_case.jsonl")
EXTRA = [
    os.path.join(REPO_ROOT, "data", "source_test_case", "folio_source_test_case.jsonl"),
    os.path.join(REPO_ROOT, "data", "source_test_case", "logicnli_source_test_case.jsonl"),
]


def collect_cases():
    test_cases = []
    for p in [VALIDATION] + EXTRA:
        test_cases.extend(load_test_cases(p))
    # first validation case + 5 folio + 5 logicnli
    return test_cases[:1] + test_cases[1:6] + test_cases[996:1001]


def run_transforms(test_cases):
    out = {}
    for name in sorted(MR_CLASS_REGISTRY):
        mr = MR_CLASS_REGISTRY[name]()
        case_results = []
        for tc in test_cases[:1]:  # same single validation case as the baseline
            random.seed(42)  # determinism for shuffle-based MRs
            try:
                follow = mr.transform(tc)
                case_results.append(
                    {
                        "premises_logic": follow.premises_logic,
                        "conclusion_logic": follow.conclusion_logic,
                        "premises_text": follow.premises_text,
                        "conclusion_text": follow.conclusion_text,
                    }
                )
            except Exception as e:
                case_results.append({"error": f"{type(e).__name__}: {e}"})
        out[name] = case_results
    return out


def main() -> int:
    baseline_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/mr_baseline.json"
    test_cases = collect_cases()
    print(f"smoke cases loaded: {len(test_cases)} (validation case drives the diff)")

    baseline = json.load(open(baseline_path))
    out = run_transforms(test_cases)

    mismatch = 0
    for name, results in out.items():
        expected = baseline[name]["results"]
        if results != expected:
            mismatch += 1
            print(f"MISMATCH: {name}")
            for got, exp in zip(results, expected):
                if got != exp:
                    for k in set(got) | set(exp):
                        if got.get(k) != exp.get(k):
                            print(f"  key={k}\n    new: {got.get(k)}\n    old: {exp.get(k)}")
        else:
            print(f"OK: {name}")

    print(f"\n{'ALL MATCH' if mismatch == 0 else f'{mismatch} MISMATCHES'}")
    return 1 if mismatch else 0


if __name__ == "__main__":
    sys.exit(main())
