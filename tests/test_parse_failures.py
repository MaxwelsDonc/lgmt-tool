"""P0: groups whose responses fail JSON parsing must not pollute metrics."""
import json

from lgmt.core.runner import run_inference
from lgmt.models.base import LLMClient
from lgmt.utils.metrics import compute_metrics
from lgmt.utils.report import generate_run_report


class UnparseableClient(LLMClient):
    """Always returns text that fails JSON repair/schema validation."""

    def __init__(self):
        self.calls = 0

    def generate(self, prompt_data, model=None, **kwargs):
        self.calls += 1
        return "this is not json at all {{{"


def _run_with(client, mgs, tmp_path):
    results = str(tmp_path / "results.jsonl")
    run_inference(
        mgs,
        client,
        "broken",
        prompting="zero_direct",
        result_save_path=results,
        max_workers=2,
        quiet=True,
    )
    records = []
    with open(results, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def test_failed_groups_excluded_from_metrics(demo_mgs_sample, tmp_path):
    records = _run_with(UnparseableClient(), demo_mgs_sample[:6], tmp_path)
    assert len(records) == 6
    # failed groups are recorded (visible) but flagged invalid
    assert all(r.get("error") for r in records)
    assert all(r.get("is_valid") is False for r in records)

    metrics = compute_metrics(records)
    assert metrics["failed"] == 6
    assert metrics["total"] == 0
    assert metrics["mvr"] == 0.0 and metrics["acc_static"] == 0.0


def test_mixed_run_counts_only_valid_groups(demo_mgs_sample, tmp_path):
    from lgmt.models import MockLLMClient

    results = str(tmp_path / "mixed.jsonl")
    mgs = demo_mgs_sample[:4]
    # first group fails, the rest succeed
    run_inference(
        mgs[:1],
        UnparseableClient(),
        "broken",
        prompting="zero_direct",
        result_save_path=results,
        max_workers=1,
        quiet=True,
    )
    run_inference(
        mgs[1:],
        MockLLMClient(persona="consistent"),
        "mock-consistent",
        prompting="zero_direct",
        result_save_path=results,
        max_workers=1,
        quiet=True,
    )
    records = [json.loads(l) for l in open(results, encoding="utf-8") if l.strip()]
    metrics = compute_metrics(records)
    assert metrics["failed"] == 1
    assert metrics["total"] == 3
    assert metrics["mvr"] == 0.0

    # the HTML report surfaces the failure count
    out = tmp_path / "report.html"
    generate_run_report(records, metrics, str(out), model="mixed")
    html = out.read_text(encoding="utf-8")
    assert "1 failed (excluded)" in html
    assert "badge-error" in html
