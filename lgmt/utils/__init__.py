"""I/O helpers, evaluation metrics, label canonicalization, and HTML reports."""
from lgmt.utils.io import (
    load_inference_records,
    load_metamorphic_groups,
    load_test_cases,
    save_metamorphic_groups,
    save_test_cases,
    write_jsonl,
)
from lgmt.utils.metrics import compute_metrics

__all__ = [
    "load_test_cases",
    "save_test_cases",
    "load_metamorphic_groups",
    "save_metamorphic_groups",
    "load_inference_records",
    "write_jsonl",
    "compute_metrics",
]
