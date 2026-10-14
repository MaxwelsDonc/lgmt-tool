"""P0: groups whose API calls raise must land in results as failed records —
an all-failure run must still produce a results file and an honest report."""
import json

from lgmt.core.runner import run_inference
from lgmt.models.base import LLMClient
from lgmt.utils.io import load_inference_records
from lgmt.utils.metrics import compute_metrics
from lgmt.utils.report import generate_run_report


class RaisingClient(LLMClient):
    """Every generate() raises, like persistent 401s from a bad key."""

    def generate(self, prompt_data, model=None, **kwargs):
        raise ConnectionError("401 Unauthorized: invalid API key")


class FlakyClient(LLMClient):
    """Raises for a fixed prefix of generate() invocations, answers the rest.

    A fully-failed group consumes 4 invocations (source call + 3 retries,
    then the exception propagates before the follow-up call).
    """

    INVOCATIONS_PER_FAILED_GROUP = 4

    def __init__(self, fail_invocations):
        self.seen = 0
        self.fail_invocations = fail_invocations

    def generate(self, prompt_data, model=None, **kwargs):
        self.seen += 1
        if self.seen <= self.fail_invocations:
            raise ConnectionError("boom")
        return json.dumps({"label": "True"})


def test_all_failed_run_keeps_records_and_reports(demo_mgs_sample, tmp_path):
    results = str(tmp_path / "results.jsonl")
    run_inference(
        demo_mgs_sample,
        RaisingClient(),
        "broken-model",
        prompting="zero_cot",
        result_save_path=results,
        max_workers=4,
        quiet=True,
    )

    # the file exists even though every group failed
    records = load_inference_records(results)
    assert len(records) == len(demo_mgs_sample)
    assert all(r.get("is_valid") is False for r in records)
    assert all(r.get("error") for r in records)
    assert all(r["model"] == "broken-model" and r["prompting"] == "zero_cot" for r in records)

    metrics = compute_metrics(records)
    assert metrics["failed"] == len(demo_mgs_sample)
    assert metrics["total"] == 0
    assert metrics["mvr"] == 0.0 and metrics["acc_static"] == 0.0

    out = tmp_path / "report.html"
    generate_run_report(records, metrics, str(out), model="broken-model")
    html = out.read_text(encoding="utf-8")
    assert f"All {len(demo_mgs_sample)} groups failed" in html
    assert "check API key / endpoint / model name" in html
    assert f"{len(demo_mgs_sample)} failed (excluded)" in html


def test_mixed_failure_and_success(demo_mgs_sample, tmp_path):
    results = str(tmp_path / "results.jsonl")
    n_fail = 2
    run_inference(
        demo_mgs_sample,
        FlakyClient(fail_invocations=n_fail * FlakyClient.INVOCATIONS_PER_FAILED_GROUP),
        "flaky",
        prompting="zero_direct",
        result_save_path=results,
        max_workers=1,
        quiet=True,
    )
    records = load_inference_records(results)
    assert len(records) == len(demo_mgs_sample)
    metrics = compute_metrics(records)
    assert metrics["failed"] == n_fail
    assert metrics["total"] == len(demo_mgs_sample) - n_fail
    # no banner when some groups succeeded
    out = tmp_path / "report.html"
    generate_run_report(records, metrics, str(out), model="flaky")
    assert "groups failed — check API key" not in out.read_text(encoding="utf-8")
