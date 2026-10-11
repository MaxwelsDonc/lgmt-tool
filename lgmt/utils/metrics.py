"""Metamorphic evaluation metrics (MVR / acc / HDR / FUR).

Formulas follow the LGMT evaluation:

- MVR (Metamorphic Violation Rate): fraction of MGs whose source and
  follow-up verdicts disagree.
- acc_static: accuracy on source cases; acc_cons: accuracy on both cases.
- HDR (Harmful Disagreement Rate): among judged pairs, fraction where the
  source verdict is correct and the follow-up verdict is wrong.
- FUR (Flaw-persisting Unanimous Rate): fraction of MGs where both verdicts
  are wrong yet consistent (the consistency oracle cannot flag them).
"""
from typing import Any, Dict, List, Optional

from lgmt.utils.labels import canonical_label


def _flag(record: Dict[str, Any], side: str) -> Optional[bool]:
    response = record.get(f"{side}_response")
    if not isinstance(response, dict):
        return None
    flag = response.get("is_correct")
    return flag if flag is True or flag is False else None


def _is_consistent(record: Dict[str, Any]) -> Optional[bool]:
    value = record.get("is_consistent")
    return value if value is True or value is False else None


def _mr_category(mr_index: str) -> str:
    # "MR-E1.5" -> "E", "MR-P1" -> "P"
    parts = str(mr_index).split("-")
    if len(parts) >= 2 and parts[1]:
        return parts[1][0].upper()
    return "?"


def compute_metrics(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute overall metrics plus per-MR and per-category breakdowns.

    Records flagged with ``is_valid: False`` (e.g. responses whose parsing
    exhausted all retries) are excluded from every denominator and counted
    under ``failed``.
    """
    valid = [r for r in records if r.get("is_valid", True) and not r.get("error")]
    failed = len(records) - len(valid)
    records = valid
    total = len(records)
    source_correct = 0
    both_correct = 0
    pairs = 0
    violations = 0
    hdr_count = 0
    fur_count = 0

    per_mr: Dict[str, Dict[str, int]] = {}
    per_category: Dict[str, Dict[str, int]] = {}

    for record in records:
        s = _flag(record, "source")
        f = _flag(record, "followup")
        consistent = _is_consistent(record)

        mr_index = str(record.get("mr_index", ""))
        mr_bucket = per_mr.setdefault(
            mr_index,
            {
                "total": 0,
                "violations": 0,
                "pairs": 0,
                "hdr": 0,
                "fur": 0,
                "src_correct": 0,
                "both_correct": 0,
            },
        )
        cat = _mr_category(mr_index)
        cat_bucket = per_category.setdefault(
            cat,
            {
                "total": 0,
                "violations": 0,
                "pairs": 0,
                "hdr": 0,
                "fur": 0,
                "src_correct": 0,
                "both_correct": 0,
            },
        )
        mr_bucket["total"] += 1
        cat_bucket["total"] += 1
        if s is not None and s:
            source_correct += 1
            mr_bucket["src_correct"] += 1
            cat_bucket["src_correct"] += 1

        if s is None or f is None:
            continue

        pairs += 1
        mr_bucket["pairs"] += 1
        cat_bucket["pairs"] += 1
        if s and f:
            both_correct += 1
            mr_bucket["both_correct"] += 1
            cat_bucket["both_correct"] += 1
        if s and not f:
            hdr_count += 1
            mr_bucket["hdr"] += 1
            cat_bucket["hdr"] += 1
        if not s and not f and consistent is True:
            fur_count += 1
            mr_bucket["fur"] += 1
            cat_bucket["fur"] += 1
        if consistent is False:
            violations += 1
            mr_bucket["violations"] += 1
            cat_bucket["violations"] += 1

    def _div(a: float, b: float) -> float:
        return a / b if b else 0.0

    overall = {
        "total": total,
        "pairs": pairs,
        "mvr": _div(violations, total),
        "acc_static": _div(source_correct, total),
        "acc_cons": _div(both_correct, pairs),
        "hdr": _div(hdr_count, pairs),
        "fur": _div(fur_count, total),
        "violation_count": violations,
        "hdr_count": hdr_count,
        "fur_count": fur_count,
        "failed": failed,
    }

    def _finalize(bucket: Dict[str, Dict[str, int]]) -> List[Dict[str, Any]]:
        rows = []
        for key in sorted(bucket):
            b = bucket[key]
            rows.append(
                {
                    "key": key,
                    "total": b["total"],
                    "mvr": _div(b["violations"], b["total"]),
                    "acc_static": _div(b["src_correct"], b["total"]),
                    "acc_cons": _div(b["both_correct"], b["pairs"]),
                    "hdr": _div(b["hdr"], b["pairs"]),
                    "fur": _div(b["fur"], b["total"]),
                    "violation_count": b["violations"],
                }
            )
        return rows

    overall["per_mr"] = _finalize(per_mr)
    overall["per_category"] = _finalize(per_category)
    return overall


def format_metrics_table(metrics: Dict[str, Any]) -> str:
    """Render the overall + per-category metrics as a plain-text table."""
    lines = []
    lines.append(
        f"{'scope':<10} {'total':>6} {'MVR':>8} {'acc_src':>8} "
        f"{'acc_cons':>9} {'HDR':>8} {'FUR':>8}"
    )
    lines.append("-" * 62)
    lines.append(
        f"{'ALL':<10} {metrics['total']:>6} {metrics['mvr'] * 100:>7.2f}% "
        f"{metrics['acc_static'] * 100:>7.2f}% {metrics['acc_cons'] * 100:>8.2f}% "
        f"{metrics['hdr'] * 100:>7.2f}% {metrics['fur'] * 100:>7.2f}%"
    )
    for row in metrics.get("per_category", []):
        lines.append(
            f"{row['key']:<10} {row['total']:>6} {row['mvr'] * 100:>7.2f}% "
            f"{'':>8} {'':>9} {row['hdr'] * 100:>7.2f}% {row['fur'] * 100:>7.2f}%"
        )
    return "\n".join(lines)


__all__ = ["compute_metrics", "format_metrics_table", "canonical_label"]
