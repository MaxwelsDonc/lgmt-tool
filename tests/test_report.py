"""Leaderboard/caliber behavior of the evaluation report."""
import json
import os

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
    # A (30% MVR) must rank above B (60%)
    pos_a = html.index(">A<span")
    pos_b = html.index(">B<span")
    assert pos_a < pos_b


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
