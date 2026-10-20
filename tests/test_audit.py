"""Fidelity-audit wiring: realization must record what `lgmt audit` checks."""
from lgmt.core.audit import audit_mgs, audit_summary
from lgmt.core.builder import build_metamorphic_groups, make_realize_fn
from lgmt.core.structure import TestCase
from lgmt.models.mock import MockLLMClient


def _source_case() -> TestCase:
    return TestCase(
        premises_logic=[
            "all x. (Patient(x) -> Recover(x))",
            "Patient(alice)",
        ],
        conclusion_logic="Recover(alice)",
        premises_text=[
            "Every patient who takes the medication recovers within a week.",
            "Alice takes the medication.",
        ],
        conclusion_text="Alice recovers within a week.",
        metadata={"label": "True"},
    )


def _build(client: MockLLMClient):
    return build_metamorphic_groups(
        [_source_case()],
        max_per_case=20,
        realize_fn=make_realize_fn(client, "mock-consistent"),
    )


def test_realization_records_audit_items():
    mgs = _build(MockLLMClient("consistent"))

    realized = [
        item
        for mg in mgs
        for item in (mg.followup_case.metadata.get("realized_items") or [])
    ]

    assert realized, "realization should record at least one re-generated statement"
    for item in realized:
        assert item["kind"].startswith(("premise_", "conclusion"))
        assert item["fol"] and item["nl"]


def test_realization_does_not_touch_source_metadata():
    case = _source_case()
    build_metamorphic_groups(
        [case],
        max_per_case=20,
        realize_fn=make_realize_fn(MockLLMClient("consistent"), "mock-consistent"),
    )

    assert "realized_items" not in case.metadata


def test_audit_checks_recorded_items():
    client = MockLLMClient("consistent")
    mgs = _build(client)

    records = audit_mgs(mgs, client, "mock-consistent", max_workers=2)
    summary = audit_summary(records)

    assert records, "audit should have items to check"
    assert summary["total"] == len(records)
    assert summary["valid"] == summary["total"]
    assert summary["fidelity"] == 1.0
    assert records[0]["judge_model"] == "mock-consistent"
    assert {"mg_id", "mr_index", "kind", "fol", "nl", "valid"} <= set(records[0])


def test_audit_skips_groups_without_realized_items():
    client = MockLLMClient("consistent")
    mgs = build_metamorphic_groups(
        [_source_case()],
        max_per_case=20,
        realize_fn=None,
    )

    summary = audit_summary(audit_mgs(mgs, client, "mock-consistent"))

    assert summary == {"total": 0, "valid": 0, "fidelity": None}
