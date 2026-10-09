#!/usr/bin/env python3
"""MR regression checker: detect unintended changes to MR transform logic.

Runs all 20 metamorphic relations over the bundled fixture cases (with a
fixed RNG seed for shuffle-based MRs) and either saves a baseline or
compares the current transforms against a previously saved baseline.

Usage:
    python tools/mr_smoke_compare.py --save-baseline        # record baseline
    python tools/mr_smoke_compare.py                        # compare (exit 1 on drift)
    python tools/mr_smoke_compare.py --baseline PATH        # custom baseline file
"""
import argparse
import json
import os
import random
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from lgmt.mrs import MR_CLASS_REGISTRY  # noqa: E402
from lgmt.utils.io import load_test_cases  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "validation_test_case.jsonl")
DEFAULT_BASELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mr_baseline.json")


def run_transforms():
    test_cases = load_test_cases(FIXTURE)
    out = {}
    for name in sorted(MR_CLASS_REGISTRY):
        mr = MR_CLASS_REGISTRY[name]()
        case_results = []
        for tc in test_cases:
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
        out[name] = {"index": mr.index, "name": mr.name, "results": case_results}
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--save-baseline",
        action="store_true",
        help="Record the current transform outputs as the baseline.",
    )
    parser.add_argument("--baseline", default=DEFAULT_BASELINE, help="Baseline file path.")
    args = parser.parse_args()

    current = run_transforms()

    if args.save_baseline:
        with open(args.baseline, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=1, sort_keys=True)
        print(f"baseline saved to {os.path.abspath(args.baseline)}")
        return 0

    if not os.path.exists(args.baseline):
        print(
            f"no baseline at {args.baseline} — run with --save-baseline first"
        )
        return 2

    with open(args.baseline, "r", encoding="utf-8") as f:
        baseline = json.load(f)

    mismatches = 0
    for name in sorted(current):
        if current[name] != baseline.get(name):
            mismatches += 1
            print(f"MISMATCH: {name}")
            for got, exp in zip(current[name]["results"], baseline[name]["results"]):
                if got != exp:
                    for k in set(got) | set(exp):
                        if got.get(k) != exp.get(k):
                            print(f"  key={k}\n    current:  {got.get(k)}\n    baseline: {exp.get(k)}")
        else:
            print(f"OK: {name}")

    print(f"\n{'ALL MATCH' if mismatches == 0 else f'{mismatches} MISMATCHES'}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
