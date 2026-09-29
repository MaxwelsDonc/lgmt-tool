"""Mock client self-consistency: the consistent persona never violates an
MR; the flawed persona violates exactly its configured flip categories."""
from lgmt.core.runner import run_inference
from lgmt.models import MockLLMClient
from lgmt.utils.io import load_inference_records
from lgmt.utils.metrics import compute_metrics


def _run_mock(mgs, persona, tmp_path):
    results = str(tmp_path / f"results_{persona}.jsonl")
    run_inference(
        mgs,
        MockLLMClient(persona=persona),
        f"mock-{persona}",
        prompting="zero_cot",
        result_save_path=results,
        max_workers=4,
        quiet=True,
    )
    return load_inference_records(results)


def test_consistent_persona_never_violates(demo_mgs_sample, tmp_path):
    records = _run_mock(demo_mgs_sample, "consistent", tmp_path)
    assert len(records) == len(demo_mgs_sample)
    metrics = compute_metrics(records)
    assert metrics["mvr"] == 0.0
    assert metrics["acc_static"] == 1.0
    assert metrics["acc_cons"] == 1.0
    assert metrics["hdr"] == 0.0
    assert all(r["is_consistent"] for r in records)


def test_flawed_persona_violates_only_flip_categories(demo_mgs_sample, tmp_path):
    records = _run_mock(demo_mgs_sample, "flawed", tmp_path)
    assert len(records) == len(demo_mgs_sample)
    metrics = compute_metrics(records)
    assert metrics["mvr"] > 0, "flawed persona must produce some violations"

    flip = set(MockLLMClient.DEFAULT_FLIP_CATEGORIES)
    for record in records:
        category = record.get("mr_index", "?").split("-")[1][0]
        if category in flip:
            assert record["is_consistent"] is False, (
                f"flawed persona must violate {record['mr_index']}"
            )
            assert record["source_response"]["is_correct"] is True
            assert record["followup_response"]["is_correct"] is False
        else:
            assert record["is_consistent"] is True, (
                f"flawed persona must stay consistent on {record['mr_index']}"
            )


def test_mock_rejects_unknown_persona():
    import pytest

    with pytest.raises(ValueError):
        MockLLMClient(persona="chaotic")
