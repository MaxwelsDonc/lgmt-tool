"""Leaderboard/caliber behavior of the evaluation report."""
import json
import os
import re

from lgmt.utils.metrics import compute_metrics
from lgmt.utils.report import generate_run_report, load_reference

REFERENCE = os.path.join(
    os.path.dirname(__file__), "..", "lgmt", "data", "reference_metrics.json"
)


def _synth_records(mg_ids, violation_ratio=0.0):
    records = []
    for i, mg_id in enumerate(mg_ids):
        viol = (i % 100) < violation_ratio * 100
        records.append(
            {
                "mg_id": mg_id,
                "mr_name": "T",
                "mr_index": "MR-E1.1",
                "data_source": "test",
                "ground_truth": "True",
                "source_input": {"premises_text": ["all x.(P(x) -> Q(x))"], "conclusion_text": "Q(a)"},
                "followup_input": {"premises_text": ["-P(a) | Q(a)"], "conclusion_text": "Q(a)"},
                "source_response": {"reasoning": "", "response_label": "True", "is_correct": True},
                "followup_response": {
                    "reasoning": "",
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
    # A (30% MVR) must rank above B (60%): compare model-cell order inside
    # the leaderboard table only
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


# --------------------------------------------------------------------- #
# finalization batch: sorting, guardrail, aliases, snapshot, smart
# collapse, drill links, lazy per-group view, prompting inference
# --------------------------------------------------------------------- #
def test_leaderboard_sortable_and_guardrail(tmp_path):
    import json as _json

    ref = _json.load(open(REFERENCE))
    records = _synth_records(ref["demo_40_mg_ids"], violation_ratio=0.5)
    out = tmp_path / "report.html"
    generate_run_report(records, compute_metrics(records), str(out), model="m")
    html = out.read_text(encoding="utf-8")
    for key in ("mvr", "acc_static", "acc_cons", "hdr", "fur", "model"):
        assert f'onclick="lbSort(\'{key}\')"' in html
    assert "lbSort('mvr')" in html  # default sort
    assert "MVR ranks consistency only" in html  # guardrail note
    assert "sort by Acc_cons" in html


def test_model_alias_merges_with_reference_row(tmp_path):
    import json as _json

    ref = _json.load(open(REFERENCE))
    records = _synth_records(ref["demo_40_mg_ids"], violation_ratio=0.2)
    out = tmp_path / "report.html"
    # "claude" must merge into "Claude 4.5 Sonnet" — one row, tagged this run
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
    assert "snapshot 2026-09, LGMT v0.1" in out.read_text(encoding="utf-8")


def test_smart_collapse_threshold(tmp_path):
    small = _synth_records([f"id_{i}" for i in range(50)])
    big = _synth_records([f"id_{i}" for i in range(101)])
    o1 = tmp_path / "small.html"
    o2 = tmp_path / "big.html"
    generate_run_report(small, compute_metrics(small), str(o1))
    generate_run_report(big, compute_metrics(big), str(o2))
    assert '<details class="full-metrics" open>' in o1.read_text(encoding="utf-8")
    assert '<details class="full-metrics">' in o2.read_text(encoding="utf-8")


def test_drill_links_and_lazy_view(tmp_path):
    records = _synth_records([f"id_{i}" for i in range(5)], violation_ratio=0.4)
    out = tmp_path / "report.html"
    generate_run_report(records, compute_metrics(records), str(out), model="m")
    html = out.read_text(encoding="utf-8")
    assert "drillFilter('cat'" in html and "drillFilter('mr'" in html
    assert "function drillFilter" in html
    assert 'id="lgmt-data"' in html  # data-driven cards
    assert "function renderMore" in html  # lazy batches
    assert 'id="lgmt-more"' in html
    assert "mg-summary" in html  # consistent groups degrade to one-liners


def test_prompting_inferred_from_records(tmp_path):
    records = _synth_records(["x_1"])
    for r in records:
        r["model"] = "my-model"
        r["prompting"] = "few_cot"
    out = tmp_path / "report.html"
    generate_run_report(records, compute_metrics(records), str(out))
    html = out.read_text(encoding="utf-8")
    assert "my-model" in html  # model name from records, not "this run"
    # custom data -> no reference board; prompting shown in the meta line
    assert "prompting <code>few_cot</code>" in html
