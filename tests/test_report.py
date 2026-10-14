"""Leaderboard/caliber behavior, FOL/CoT rendering, and Web Studio tests."""
import json
import os
import re

from lgmt.utils.metrics import compute_metrics
from lgmt.utils.report import generate_run_report, load_reference
from lgmt.webapp import _parse_source_cases, execute_custom_workflow, execute_demo_workflow

REFERENCE = os.path.join(
    os.path.dirname(__file__), "..", "lgmt", "data", "reference_metrics.json"
)


def _synth_records(mg_ids, violation_ratio=0.0, with_logic=False, with_cot=False):
    records = []
    for i, mg_id in enumerate(mg_ids):
        viol = (i % 100) < violation_ratio * 100
        src_in = {"premises_text": ["All birds can fly."], "conclusion_text": "Tweety flies."}
        fol_in = {"premises_text": ["[Changed_0] Anything that cannot fly is not a bird."], "conclusion_text": "Tweety flies."}
        if with_logic:
            src_in["premises_logic"] = ["all x.(Bird(x) -> Fly(x))"]
            src_in["conclusion_logic"] = "Fly(tweety)"
            fol_in["premises_logic"] = ["all x.(-Fly(x) -> -Bird(x))"]
            fol_in["conclusion_logic"] = "Fly(tweety)"
        records.append(
            {
                "mg_id": mg_id,
                "mr_name": "Contraposition",
                "mr_index": "MR-E1.1",
                "data_source": "test",
                "ground_truth": "True",
                "source_input": src_in,
                "followup_input": fol_in,
                "source_response": {
                    "reasoning": "Step 1: universal instantiation." if with_cot else "",
                    "response_label": "True",
                    "is_correct": True,
                },
                "followup_response": {
                    "reasoning": "Step 1: confused by double negation." if with_cot else "",
                    "response_label": "False" if viol else "True",
                    "is_correct": not viol,
                },
                "is_consistent": not viol,
            }
        )
    return records


def test_reference_file_exists_and_covers_six_models():
    ref = load_reference()
    assert ref is not None
    assert len(ref["models"]) == 6
    assert len(ref["demo_40_mg_ids"]) == 40
    assert len(ref["full_3091_mg_ids"]) == 3091
    for m in ref["models"].values():
        for caliber in ("full_3091", "demo_40"):
            for key in ("mvr", "acc_static", "acc_cons", "hdr", "fur"):
                assert key in m[caliber]


def test_demo_caliber_report_shows_leaderboard(tmp_path):
    ref = json.load(open(REFERENCE))
    records = _synth_records(ref["demo_40_mg_ids"], violation_ratio=0.6)
    out = tmp_path / "report.html"
    generate_run_report(
        records, compute_metrics(records), str(out), model="mock-60"
    )
    html = out.read_text(encoding="utf-8")
    assert 'class="lb-table"' in html
    assert "ranked on demo-40 subset" in html
    assert "reference: 6 SOTA models" in html
    assert "▶ this run" in html
    assert "GPT-5.2" in html and "Claude 4.5 Sonnet" in html
    # prompting unspecified -> honest mismatch note vs the zero-shot CoT reference
    assert "note: reference used zero_cot" in html


def test_custom_single_model_gets_hint_not_board(tmp_path):
    records = _synth_records([f"custom_{i}" for i in range(10)])
    out = tmp_path / "report.html"
    generate_run_report(records, compute_metrics(records), str(out), model="solo")
    html = out.read_text(encoding="utf-8")
    assert 'class="lb-table"' not in html
    assert "unlock the leaderboard" in html
    assert "GPT-5.2" not in html


def test_custom_multi_model_ranks_mutually(tmp_path):
    ids = [f"custom_{i}" for i in range(10)]
    rec_a = _synth_records(ids, violation_ratio=0.3)
    rec_b = _synth_records(ids, violation_ratio=0.6)
    out = tmp_path / "report.html"
    generate_run_report(
        rec_a,
        compute_metrics(rec_a),
        str(out),
        model="A",
        extra_runs=[{"model": "B", "metrics": compute_metrics(rec_b)}],
    )
    html = out.read_text(encoding="utf-8")
    assert 'class="lb-table"' in html
    assert "mutual comparison" in html
    assert "GPT-5.2" not in html  # reference stays out for unknown data
    lb = re.search(r'<table class="lb-table"[^>]*>.*?</table>', html, re.S).group(0)
    order = re.findall(r"<td>(?:\d+)</td><td>([A-Z])", lb.replace("\n", ""))
    assert order == ["A", "B"]


def test_full_caliber_detected_with_minor_missing(tmp_path):
    ref = json.load(open(REFERENCE))
    ids = ref["full_3091_mg_ids"][:3090]  # one dropped group
    records = _synth_records(ids)
    out = tmp_path / "report.html"
    generate_run_report(
        records,
        compute_metrics(records),
        str(out),
        model="nearly-full",
        prompting="zero_cot",
    )
    html = out.read_text(encoding="utf-8")
    assert "ranked on full 3,091-group evaluation set" in html


def test_leaderboard_sortable_and_guardrail(tmp_path):
    ref = json.load(open(REFERENCE))
    records = _synth_records(ref["demo_40_mg_ids"], violation_ratio=0.5)
    out = tmp_path / "report.html"
    generate_run_report(records, compute_metrics(records), str(out), model="m")
    html = out.read_text(encoding="utf-8")
    for key in ("mvr", "acc_static", "acc_cons", "hdr", "fur", "model"):
        assert f'onclick="lbSort(\'{key}\')"' in html
    assert "lbSort('mvr')" in html  # default sort
    assert "DESC_BY_DEFAULT" in html  # accuracy columns sort descending first
    assert "MVR ranks consistency only" in html  # guardrail note
    assert "sort by Acc_cons" in html


def test_model_alias_merges_with_reference_row(tmp_path):
    ref = json.load(open(REFERENCE))
    records = _synth_records(ref["demo_40_mg_ids"], violation_ratio=0.2)
    out = tmp_path / "report.html"
    generate_run_report(records, compute_metrics(records), str(out), model="claude")
    html = out.read_text(encoding="utf-8")
    lb = re.search(r'<table class="lb-table"[^>]*>.*?</table>', html, re.S).group(0)
    rows = re.findall(r"<td>(?:\d+)</td><td>(.*?)<", lb.replace("\n", ""))
    assert len(rows) == 6
    assert "Claude 4.5 Sonnet" in rows
    assert "this-run" in lb
    assert "▶ this run" in lb


def test_snapshot_date_in_footer(tmp_path):
    records = _synth_records(["x_1"])
    out = tmp_path / "report.html"
    generate_run_report(records, compute_metrics(records), str(out))
    from lgmt import __version__

    assert f"2026-09, LGMT v{__version__}" in out.read_text(encoding="utf-8")


def test_smart_collapse_threshold(tmp_path):
    small = _synth_records([f"id_{i}" for i in range(50)])
    big = _synth_records([f"id_{i}" for i in range(101)])
    o1 = tmp_path / "small.html"
    o2 = tmp_path / "big.html"
    generate_run_report(small, compute_metrics(small), str(o1))
    generate_run_report(big, compute_metrics(big), str(o2))
    assert '<details class="full-metrics" open>' in o1.read_text(encoding="utf-8")
    assert '<details class="full-metrics">' in o2.read_text(encoding="utf-8")


def test_drill_links_and_lazy_view_with_logic_and_cot(tmp_path):
    records = _synth_records(
        [f"id_{i}" for i in range(5)],
        violation_ratio=0.4,
        with_logic=True,
        with_cot=True,
    )
    out = tmp_path / "report.html"
    generate_run_report(records, compute_metrics(records), str(out), model="m")
    html = out.read_text(encoding="utf-8")
    assert "drillFilter('cat'" in html and "drillFilter('mr'" in html
    assert "function drillFilter" in html
    assert 'id="lgmt-data"' in html
    assert "function renderMore" in html
    assert 'id="lgmt-more"' in html
    assert "mg-summary" in html
    # F1 & U2: embedded JSON includes FOL logic and CoT reasoning traces
    assert "all x.(Bird(x) -> Fly(x))" in html
    assert "Step 1: confused by double negation." in html
    assert "cleanChangedTag" in html
    assert "buildReasoningHtml" in html


def test_prompting_inferred_from_records(tmp_path):
    records = _synth_records(["x_1"])
    for r in records:
        r["model"] = "my-model"
        r["prompting"] = "few_cot"
    out = tmp_path / "report.html"
    generate_run_report(records, compute_metrics(records), str(out))
    html = out.read_text(encoding="utf-8")
    assert "my-model" in html
    assert "prompting <code>few_cot</code>" in html


def test_webapp_supports_pure_nl_and_offline_workflows():
    # Pure NL cases synthesized via a custom translator function
    nl_jsonl = (
        '{"premises_text": ["All birds can fly.", "Tweety is a bird."], '
        '"conclusion_text": "Tweety can fly.", "metadata": {"label": "True"}}'
    )
    fake_translator = lambda pt, ct: {
        "premises_logic": ["all x.(Bird(x) -> Fly(x))", "Bird(tweety)"],
        "conclusion_logic": "Fly(tweety)",
    }
    cases = _parse_source_cases(nl_jsonl, translator=fake_translator)
    assert len(cases) == 1
    assert cases[0].conclusion_logic == "Fly(tweety)"

    # Offline demo workflow produces body_html and summary
    demo_state = execute_demo_workflow(persona="flawed", prompting="zero_cot", dataset="demo_40")
    assert "MVR=" in demo_state["summary"]
    assert 'class="lb-table"' in demo_state["body_html"]

    # Offline custom workflow with dual NL+FOL
    fol_jsonl = (
        '{"premises_logic": ["all x.(Man(x) -> Mortal(x))", "Man(socrates)"], '
        '"conclusion_logic": "Mortal(socrates)", '
        '"premises_text": ["All men are mortal.", "Socrates is a man."], '
        '"conclusion_text": "Socrates is mortal.", "metadata": {"label": "True"}}'
    )
    custom_state = execute_custom_workflow(
        api_key="",
        base_url="",
        model="",
        cases_jsonl=fol_jsonl,
        categories=["E", "P", "C"],
        prompting="zero_cot",
        realize=False,
        use_mock=True,
    )
    assert "Custom run completed" in custom_state["summary"]
