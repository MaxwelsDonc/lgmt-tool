"""HTML report generation for MG transformations and inference results.

The evaluation report has three layers:
    1. Leaderboard summary (this run vs. reference SOTA models, ranked only
       when the run matches a known evaluation caliber).
    2. Metric detail (big metric cards + a collapsible full metrics table).
    3. Per-MG audit cards with vanilla-JS filtering.

Everything is inlined (CSS/JS) so the report opens offline by double-click.
"""
import html
import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from lgmt.core.structure import MetamorphicGroups, TestCase

REFERENCE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "reference_metrics.json")
REFERENCE_PROMPTING = "zero_cot"

_PRIMARY = "#3a6ea5"

_CSS = """
    * { box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin: 0; background: #f2f4f8; color: #2b3440; }
    .container { max-width: 1200px; margin: 0 auto; padding: 28px 20px 60px; }
    h1 { font-size: 26px; margin: 0 0 4px; color: #1f2937; }
    h2 { font-size: 18px; margin: 34px 0 12px; color: #1f2937; }
    .subtitle { color: #6b7280; font-size: 14px; margin-bottom: 18px; }
    .card { background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(16,24,40,.08), 0 1px 2px rgba(16,24,40,.04); padding: 20px; margin-bottom: 20px; }

    /* ---------- leaderboard ---------- */
    .lb-table { width: 100%; border-collapse: collapse; font-size: 14px; }
    .lb-table th { text-align: left; font-size: 12px; text-transform: uppercase; letter-spacing: .4px; color: #6b7280; padding: 8px 10px; border-bottom: 2px solid #e5e7eb; }
    .lb-table td { padding: 9px 10px; border-bottom: 1px solid #f0f1f3; }
    .lb-table tr.this-run td { background: #eaf1f9; font-weight: 600; }
    .lb-table tr.medal-1 td:first-child { color: #b8860b; font-weight: 700; }
    .lb-table tr.medal-2 td:first-child { color: #70757a; font-weight: 700; }
    .lb-table tr.medal-3 td:first-child { color: #a05a2c; font-weight: 700; }
    .lb-bar { display: inline-block; height: 10px; border-radius: 5px; background: linear-gradient(90deg, #3a6ea5, #6f9fd0); vertical-align: middle; margin-right: 8px; }
    .lb-mvr { white-space: nowrap; font-variant-numeric: tabular-nums; }
    .this-tag { display: inline-block; margin-left: 8px; padding: 1px 8px; border-radius: 9px; background: #3a6ea5; color: #fff; font-size: 11px; font-weight: 700; }
    .ref-tag { display: inline-block; margin-left: 8px; padding: 1px 6px; border-radius: 4px; background: #eef1f5; color: #6b7280; font-size: 10px; }
    .lb-note { color: #6b7280; font-size: 12.5px; margin-top: 10px; }
    .lb-hint { background: #fff8e6; border: 1px solid #f3e3b3; color: #7a6414; border-radius: 10px; padding: 12px 14px; font-size: 13.5px; }

    /* ---------- metric cards ---------- */
    .metric-cards { display: flex; flex-wrap: wrap; gap: 14px; }
    .metric-card { flex: 1 1 160px; border-radius: 12px; padding: 16px 18px; color: #fff; box-shadow: 0 1px 3px rgba(16,24,40,.12); }
    .metric-card .mc-value { font-size: 30px; font-weight: 750; line-height: 1.1; font-variant-numeric: tabular-nums; }
    .metric-card .mc-label { font-size: 12.5px; opacity: .92; margin-top: 4px; text-transform: uppercase; letter-spacing: .5px; }
    .mc-red { background: linear-gradient(135deg, #c0392b, #e07b6a); }
    .mc-amber { background: linear-gradient(135deg, #b9770e, #e2a13d); }
    .mc-blue { background: linear-gradient(135deg, #3a6ea5, #6f9fd0); }
    .mc-grey { background: linear-gradient(135deg, #4b5563, #7b8794); }
    .meta-line { color: #6b7280; font-size: 13px; margin: 6px 0 0; }
    .meta-line code { background: #eef1f5; padding: 1px 6px; border-radius: 5px; font-size: 12px; }

    details.full-metrics summary { cursor: pointer; color: #3a6ea5; font-weight: 600; font-size: 14px; margin-bottom: 8px; }
    .metrics-table { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 13px; }
    .metrics-table th, .metrics-table td { border: 1px solid #e5e7eb; padding: 6px 10px; text-align: right; font-variant-numeric: tabular-nums; }
    .metrics-table th { background: #f7f8fa; color: #4b5563; }
    .metrics-table td:first-child, .metrics-table th:first-child { text-align: left; }
    .metrics-table caption { caption-side: top; text-align: left; color: #6b7280; font-size: 12px; padding-bottom: 4px; }

    /* ---------- filter bar + MG cards ---------- */
    .filter-bar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 14px; }
    .filter-bar label { font-size: 13px; color: #4b5563; display: inline-flex; align-items: center; gap: 4px; }
    .filter-bar input[type="text"] { flex: 1 1 200px; padding: 7px 10px; border: 1px solid #d7dbe0; border-radius: 8px; font-size: 13px; }
    .filter-bar select { padding: 7px 8px; border: 1px solid #d7dbe0; border-radius: 8px; font-size: 13px; background: #fff; }
    .filter-count { font-size: 12.5px; color: #6b7280; margin-left: auto; }

    details.mg-card { background: #fff; border-radius: 10px; box-shadow: 0 1px 2px rgba(16,24,40,.07); margin-bottom: 10px; }
    details.mg-card summary { cursor: pointer; padding: 12px 16px; display: flex; flex-wrap: wrap; align-items: center; gap: 8px; list-style: none; }
    details.mg-card summary::-webkit-details-marker { display: none; }
    .mg-title { font-weight: 600; font-size: 14px; }
    .mg-sub { color: #6b7280; font-size: 12.5px; }
    .card-body { padding: 0 16px 16px; }

    .badge { display: inline-block; padding: 2px 10px; font-size: 11.5px; font-weight: 700; border-radius: 10px; color: #fff; }
    .badge-consistent { background: #1f9d55; }
    .badge-violation { background: #d64541; }
    .badge-correct { background: #1287a8; }
    .badge-wrong { background: #e2a13d; color: #4d3a05; }

    /* ---------- comparison table ---------- */
    .comparison-table { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 13px; }
    .comparison-table th { background: #f7f8fa; color: #4b5563; padding: 8px 10px; text-align: left; border-bottom: 2px solid #e5e7eb; font-size: 12px; text-transform: uppercase; letter-spacing: .4px; }
    .comparison-table td { padding: 8px 10px; border-bottom: 1px solid #f0f1f3; vertical-align: top; word-wrap: break-word; }
    .col-logic { width: 30%; background: #fbfcfe; }
    .col-text { width: 20%; }
    .changed-source { background: #fff8e6 !important; }
    .changed-followup { background: #eaf7ee !important; }
    .conclusion-row { font-weight: 700; border-top: 2px solid #9aa3ad; background: #f2f4f6; }
    .conclusion-changed { background: #ffefc2; }
    .tag { display: inline-block; padding: 1px 6px; font-size: 10.5px; border-radius: 4px; background: #6b7280; color: #fff; margin-right: 4px; }
    .split-item { margin-bottom: 6px; padding: 6px; background: #eaf7ee; border-left: 3px solid #1f9d55; border-radius: 0 4px 4px 0; }
    pre { white-space: pre-wrap; margin: 0; font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace; font-size: 12.5px; color: #a3336b; }
    .text-content { font-family: Georgia, serif; color: #495057; font-style: italic; }
    .section-header { font-weight: 700; color: #6b7280; margin-bottom: 4px; display: block; font-size: 11px; text-transform: uppercase; letter-spacing: .5px; }

    footer { margin-top: 40px; text-align: center; color: #9aa3ad; font-size: 12.5px; }
    footer a { color: #3a6ea5; text-decoration: none; }
"""

_JS = """
function lgmtFilter(){
  var mode = document.querySelector('input[name="lgmt-filter"]:checked').value;
  var cat = document.getElementById('lgmt-cat').value;
  var q = document.getElementById('lgmt-search').value.toLowerCase();
  var cards = document.querySelectorAll('details.mg-card');
  var shown = 0, viol = 0;
  cards.forEach(function(c){
    var ok = true;
    if (mode === 'violations' && c.dataset.consistent !== 'false') ok = false;
    if (mode === 'consistent' && c.dataset.consistent !== 'true') ok = false;
    if (cat !== 'all' && c.dataset.category !== cat) ok = false;
    if (q && (c.dataset.search || '').indexOf(q) < 0) ok = false;
    c.style.display = ok ? '' : 'none';
    if (ok) { shown++; if (c.dataset.consistent === 'false') viol++; }
  });
  var el = document.getElementById('lgmt-count');
  if (el) el.textContent = shown + ' shown · ' + viol + ' violations';
}
"""


# --------------------------------------------------------------------- #
# reference leaderboard
# --------------------------------------------------------------------- #
def load_reference() -> Optional[Dict[str, Any]]:
    path = os.path.abspath(REFERENCE_PATH)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def detect_caliber(mg_ids, reference: Dict[str, Any]) -> str:
    """Classify a run against the known evaluation calibers.

    A run counts as the full evaluation set when its mg_ids are a subset of
    the reference set with only a few failures missing (real runs can drop
    a handful of groups on API errors).
    """
    ids = set(str(x) for x in mg_ids)
    if ids == set(reference.get("demo_40_mg_ids", [])):
        return "demo_40"
    full = set(reference.get("full_3091_mg_ids", []))
    if full and ids.issubset(full):
        missing = len(full) - len(ids)
        if missing <= max(5, int(0.01 * len(full))):
            return "full_3091"
    return "custom"


def _lb_row(model, m, is_current=False, is_reference=False) -> Dict[str, Any]:
    return {
        "model": model,
        "mvr": m["mvr"],
        "acc_static": m["acc_static"],
        "acc_cons": m["acc_cons"],
        "hdr": m["hdr"],
        "fur": m["fur"],
        "is_current": is_current,
        "is_reference": is_reference,
    }


def build_leaderboard_rows(
    current_name: str,
    current_metrics: Dict[str, Any],
    extra_runs: List[Dict[str, Any]],
    caliber: str,
    reference: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Reference models are only ranked on the same data + prompting."""
    rows = [_lb_row(current_name, current_metrics, is_current=True)]
    for run in extra_runs:
        rows.append(_lb_row(run["model"], run["metrics"]))
    if reference and caliber in ("demo_40", "full_3091"):
        for name, m in reference.get("models", {}).items():
            rows.append(_lb_row(name, m[caliber], is_reference=True))
    rows.sort(key=lambda r: (r["mvr"], r["model"]))
    return rows


def _leaderboard_html(rows, caliber, prompting, reference) -> Tuple[str, str]:
    """Return (html, note). Empty rows handling happens upstream."""
    if not rows:
        return "", ""
    max_mvr = max(r["mvr"] for r in rows) or 1.0
    body = ""
    for rank, r in enumerate(rows, 1):
        medal = f" medal-{rank}" if rank <= 3 else ""
        current = " this-run" if r["is_current"] else ""
        width = max(2, int(r["mvr"] / max_mvr * 120))
        tags = ""
        if r["is_current"]:
            tags += '<span class="this-tag">▶ this run</span>'
        if r["is_reference"]:
            tags += '<span class="ref-tag">reference</span>'
        body += (
            f'<tr class="{medal.strip()}{current}">'
            f"<td>{rank}</td>"
            f'<td>{html.escape(r["model"])}{tags}</td>'
            f'<td class="lb-mvr"><span class="lb-bar" style="width:{width}px"></span>'
            f'{r["mvr"] * 100:.2f}%</td>'
            f"<td>{r['acc_static'] * 100:.2f}%</td>"
            f"<td>{r['acc_cons'] * 100:.2f}%</td>"
            f"<td>{r['hdr'] * 100:.2f}%</td>"
            f"<td>{r['fur'] * 100:.2f}%</td>"
            f"</tr>"
        )
    table = (
        '<table class="lb-table"><thead><tr>'
        "<th>Rank</th><th>Model</th><th>MVR ↓</th><th>Acc_static</th>"
        "<th>Acc_cons</th><th>HDR</th><th>FUR</th>"
        f"</tr></thead><tbody>{body}</tbody></table>"
    )
    if caliber in ("demo_40", "full_3091"):
        subset = "demo-40 subset" if caliber == "demo_40" else "full 3,091-group evaluation set"
        note = (
            f"ranked on {subset} · zero-shot CoT · reference: 6 SOTA models"
        )
        if reference and prompting != reference.get("prompting", REFERENCE_PROMPTING):
            note += (
                f" — note: reference used {reference.get('prompting', REFERENCE_PROMPTING)}, "
                f"this run used {prompting}"
            )
    else:
        note = (
            f"ranked on your data set · {len(rows)} model run(s) · mutual comparison"
        )
    return table, note


# --------------------------------------------------------------------- #
# comparison table (kept from the original check_mr layout)
# --------------------------------------------------------------------- #
def _render_comparison_table(source: TestCase, followup: TestCase) -> str:
    rows = ""

    changes_map: Dict[int, list] = {}
    consumed_f_indices = set()
    tagged_f_indices = set()

    for f_idx, f_text in enumerate(followup.premises_text):
        match = re.search(r"\[Changed_(\d+)\]", f_text)
        if match:
            s_idx = int(match.group(1))
            changes_map.setdefault(s_idx, [])
            changes_map[s_idx].append((followup.premises_logic[f_idx], f_text, f_idx))
            tagged_f_indices.add(f_idx)

    f_ptr = 0

    for s_idx, s_logic in enumerate(source.premises_logic):
        s_text_val = source.premises_text[s_idx] if s_idx < len(source.premises_text) else ""
        s_logic_html = f"<pre>{html.escape(s_logic)}</pre>"
        s_text_html = f'<div class="text-content">{html.escape(s_text_val)}</div>'

        f_logic_html = ""
        f_text_html = ""
        s_style_class = ""
        f_style_class = ""

        if s_idx in changes_map:
            s_style_class = "changed-source"
            f_style_class = "changed-followup"
            for part_logic, part_text, part_idx in changes_map[s_idx]:
                f_logic_html += (
                    f'<div class="split-item"><span class="tag">P{part_idx + 1}</span>'
                    f"<pre>{html.escape(part_logic)}</pre></div>"
                )
                f_text_html += (
                    f'<div class="split-item text-content">{html.escape(part_text)}</div>'
                )
                consumed_f_indices.add(part_idx)
        else:
            while f_ptr < len(followup.premises_logic) and (
                f_ptr in tagged_f_indices or f_ptr in consumed_f_indices
            ):
                f_ptr += 1
            if f_ptr < len(followup.premises_logic):
                f_logic_val = followup.premises_logic[f_ptr]
                f_text_val = (
                    followup.premises_text[f_ptr]
                    if f_ptr < len(followup.premises_text)
                    else ""
                )
                f_logic_html = (
                    f'<span class="tag">P{f_ptr + 1}</span>'
                    f"<pre>{html.escape(f_logic_val)}</pre>"
                )
                f_text_html = f'<div class="text-content">{html.escape(f_text_val)}</div>'
                consumed_f_indices.add(f_ptr)
                f_ptr += 1
            else:
                f_logic_html = "<i>(Missing)</i>"

        rows += f"""
        <tr class="premise-row">
            <td class="{s_style_class}"><span class="tag">P{s_idx + 1}</span>{s_logic_html}</td>
            <td class="{s_style_class}">{s_text_html}</td>
            <td class="{f_style_class}">{f_logic_html}</td>
            <td class="{f_style_class}">{f_text_html}</td>
        </tr>"""

    while f_ptr < len(followup.premises_logic):
        if f_ptr not in consumed_f_indices:
            f_logic_val = followup.premises_logic[f_ptr]
            f_text_val = (
                followup.premises_text[f_ptr]
                if f_ptr < len(followup.premises_text)
                else ""
            )
            f_logic_html = (
                f'<span class="tag">P{f_ptr + 1}</span>'
                f"<pre>{html.escape(f_logic_val)}</pre>"
            )
            f_text_html = f'<div class="text-content">{html.escape(f_text_val)}</div>'
            rows += f"""
            <tr class="premise-row">
                <td><i>(None)</i></td>
                <td></td>
                <td class="changed-followup">{f_logic_html}</td>
                <td class="changed-followup">{f_text_html}</td>
            </tr>"""
        f_ptr += 1

    s_conc_logic = html.escape(source.conclusion_logic)
    s_conc_text = html.escape(source.conclusion_text)
    f_conc_logic = html.escape(followup.conclusion_logic)
    f_conc_text = html.escape(followup.conclusion_text)

    conc_row_class = "conclusion-row"
    if s_conc_logic != f_conc_logic:
        conc_row_class += " conclusion-changed"

    rows += f"""
        <tr class="{conc_row_class}">
            <td><span class="tag">Conc</span><pre>{s_conc_logic}</pre></td>
            <td><div class="text-content">{s_conc_text}</div></td>
            <td><pre>{f_conc_logic}</pre></td>
            <td><div class="text-content">{f_conc_text}</div></td>
        </tr>"""

    return f"""
    <table class="comparison-table">
        <thead>
            <tr>
                <th class="col-logic">Source Logic</th>
                <th class="col-text">Source Text</th>
                <th class="col-logic">Follow-up Logic</th>
                <th class="col-text">Follow-up Text</th>
            </tr>
        </thead>
        <tbody>{rows}
        </tbody>
    </table>"""


def _html_page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)}</title>
    <style>{_CSS}</style>
</head>
<body>
    <div class="container">
        <h1>{html.escape(title)}</h1>
{body}
    </div>
    <footer>
        LGMT · <a href="#">GitHub (TODO)</a> · <a href="#">Paper (TODO)</a> ·
        generated {datetime.now().strftime("%Y-%m-%d %H:%M")}
    </footer>
    <script>{_JS}</script>
</body>
</html>"""


def generate_transformation_report(
    results: List[Tuple[TestCase, TestCase, str]],
    output_file: str = "mr_report.html",
) -> str:
    """Report raw MR transformations: list of (source, followup, mr_name)."""
    body = ""
    for idx, (source, followup, mr_name) in enumerate(results):
        body += f'<div class="card"><h2 style="margin-top:0">Example #{idx + 1} ({html.escape(mr_name)})</h2>\n'
        body += _render_comparison_table(source, followup)
        body += "</div>"
    page = _html_page("Metamorphic Relation Check Report", body)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"HTML report generated: {os.path.abspath(output_file)}")
    return output_file


# --------------------------------------------------------------------- #
# evaluation report
# --------------------------------------------------------------------- #
def _badge(text: str, css: str) -> str:
    return f'<span class="badge {css}">{html.escape(text)}</span>'


def _metrics_table_html(metrics: Dict[str, Any]) -> str:
    def _pct(x):
        return f"{x * 100:.2f}%"

    def _row(label, r):
        return (
            f"<tr><td>{html.escape(label)}</td><td>{r['total']}</td>"
            f"<td>{_pct(r['mvr'])}</td>"
            f"<td>{_pct(r['acc_static'])}</td>"
            f"<td>{_pct(r['acc_cons'])}</td>"
            f"<td>{_pct(r['hdr'])}</td>"
            f"<td>{_pct(r['fur'])}</td></tr>"
        )

    head = (
        "<tr><th>Scope</th><th>Total</th><th>MVR ↓</th><th>Acc_static</th>"
        "<th>Acc_cons</th><th>HDR</th><th>FUR</th></tr>"
    )
    overall = (
        "<tr><td><b>ALL</b></td>"
        f"<td>{metrics['total']}</td>"
        f"<td><b>{_pct(metrics['mvr'])}</b></td>"
        f"<td>{_pct(metrics['acc_static'])}</td>"
        f"<td>{_pct(metrics['acc_cons'])}</td>"
        f"<td>{_pct(metrics['hdr'])}</td>"
        f"<td>{_pct(metrics['fur'])}</td></tr>"
    )
    cat_rows = "".join(
        _row(f"Category {r['key']}", r) for r in metrics.get("per_category", [])
    )
    mr_rows = "".join(_row(r["key"], r) for r in metrics.get("per_mr", []))
    return (
        f'<table class="metrics-table">{head}{overall}</table>'
        f'<details class="full-metrics"><summary>Full metrics by category and by MR'
        f" (Acc columns: per-scope accuracy over the groups in that scope)</summary>"
        f'<table class="metrics-table">{head}{cat_rows}</table>'
        f'<table class="metrics-table">{head}{mr_rows}</table></details>'
    )


def _metric_card(value: str, label: str, css: str) -> str:
    return (
        f'<div class="metric-card {css}">'
        f'<div class="mc-value">{value}</div>'
        f'<div class="mc-label">{html.escape(label)}</div></div>'
    )


def _mg_card(idx, record, mg, mg_by_id) -> str:
    mg_id = str(record.get("mg_id", f"#{idx + 1}"))
    consistent = record.get("is_consistent")
    is_consistent = "true" if consistent is True else "false"
    consistency_badge = (
        _badge("CONSISTENT", "badge-consistent")
        if consistent is True
        else _badge("VIOLATION", "badge-violation")
        if consistent is False
        else ""
    )
    gt = html.escape(str(record.get("ground_truth", "")))
    src = record.get("source_response", {}) or {}
    fol = record.get("followup_response", {}) or {}
    src_badge = _badge(
        f"source: {src.get('response_label', '?')} "
        f"({'correct' if src.get('is_correct') else 'wrong'})",
        "badge-correct" if src.get("is_correct") else "badge-wrong",
    )
    fol_badge = _badge(
        f"follow-up: {fol.get('response_label', '?')} "
        f"({'correct' if fol.get('is_correct') else 'wrong'})",
        "badge-correct" if fol.get("is_correct") else "badge-wrong",
    )
    mr_index = str(record.get("mr_index", ""))
    category = mr_index.split("-")[1][0] if "-" in mr_index else "?"
    heading = f"{html.escape(mg_id)} · {html.escape(mr_index)} {html.escape(str(record.get('mr_name', '')))}"
    search_blob = " ".join(
        [
            mg_id,
            mr_index,
            str(record.get("mr_name", "")),
            gt,
            " ".join(str(p) for p in (record.get("source_input", {}) or {}).get("premises_text", [])),
            " ".join(str(p) for p in (record.get("followup_input", {}) or {}).get("premises_text", [])),
        ]
    ).lower()

    details_open = "" if consistent is True else " open"
    parts = [
        f'<details class="mg-card" data-consistent="{is_consistent}" '
        f'data-category="{html.escape(category)}" data-search="{html.escape(search_blob, quote=True)}"{details_open}>',
        f'<summary><span class="mg-title">#{idx + 1} {heading}</span>'
        f"{consistency_badge}{src_badge}{fol_badge}"
        f'<span class="mg-sub">ground truth: {gt}</span></summary>',
        '<div class="card-body">',
    ]
    mg_obj = mg_by_id.get(mg_id)
    if mg_obj is not None:
        parts.append(_render_comparison_table(mg_obj.source_case, mg_obj.followup_case))
    else:
        for side, key in (("Source", "source_input"), ("Follow-up", "followup_input")):
            inp = record.get(key, {}) or {}
            parts.append(f'<span class="section-header">{side}</span>')
            for p in inp.get("premises_text", []):
                parts.append(f'<div class="text-content">{html.escape(str(p))}</div>')
            parts.append(
                '<div class="text-content"><b>Conclusion:</b> '
                f"{html.escape(str(inp.get('conclusion_text', '')))}</div>"
            )
    parts.append("</div></details>")
    return "\n".join(parts)


def generate_run_report(
    records: List[Dict[str, Any]],
    metrics: Dict[str, Any],
    output_file: str,
    mgs: Optional[List[MetamorphicGroups]] = None,
    title: str = "LGMT Metamorphic Evaluation Report",
    model: Optional[str] = None,
    prompting: Optional[str] = None,
    extra_runs: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Full evaluation report: leaderboard + metrics + per-MG audit cards.

    Args:
        records: current run's inference records (drives cards and metrics).
        metrics: precomputed metrics for ``records``.
        extra_runs: optional list of ``{"model", "records", "metrics"}`` for
            other models evaluated on the same MG set (mutual ranking).
        model / prompting: labels for the current run, shown on the board.
    """
    prompting = prompting or "unspecified"
    current_name = model or "this run"
    extra_runs = extra_runs or []
    mg_ids = [r.get("mg_id") for r in records]
    reference = load_reference()
    caliber = detect_caliber(mg_ids, reference) if reference else "custom"

    body = ""

    # ---------------- layer 1: leaderboard ---------------- #
    body += '<div class="card"><h2 style="margin-top:0">Leaderboard</h2>\n'
    if caliber in ("demo_40", "full_3091") or extra_runs:
        rows = build_leaderboard_rows(
            current_name, metrics, extra_runs, caliber, reference
        )
        table, note = _leaderboard_html(rows, caliber, prompting, reference)
        body += table
        body += f'<div class="lb-note">{html.escape(note)}</div>\n'
    else:
        body += (
            '<div class="lb-hint">Leaderboard is unavailable for this data set: '
            "no reference model has been evaluated on it. "
            "Run another model on the same data to unlock the leaderboard "
            "(e.g. <code>lgmt report --results a.jsonl --model A "
            "--results b.jsonl --model B</code>).</div>\n"
        )
    body += "</div>"

    # ---------------- layer 2: metric detail ---------------- #
    body += '<div class="card"><h2 style="margin-top:0">Metrics Summary</h2>\n'
    body += (
        '<div class="metric-cards">'
        + _metric_card(f"{metrics['mvr'] * 100:.2f}%", "MVR (violation rate)", "mc-red")
        + _metric_card(f"{metrics['hdr'] * 100:.2f}%", "HDR (harmful disagreement)", "mc-amber")
        + _metric_card(str(metrics["violation_count"]), "violations", "mc-blue")
        + _metric_card(str(metrics["total"]), "metamorphic groups", "mc-grey")
        + "</div>"
    )
    meta_bits = []
    if model:
        meta_bits.append(f'model <code>{html.escape(model)}</code>')
    meta_bits.append(f"prompting <code>{html.escape(prompting)}</code>")
    meta_bits.append(f"{len(records)} metamorphic groups")
    meta_bits.append(f"generated {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if caliber != "custom":
        meta_bits.append(f"caliber <code>{caliber}</code>")
    body += f'<p class="meta-line">{" · ".join(meta_bits)}</p>\n'
    body += _metrics_table_html(metrics)
    body += "</div>"

    # ---------------- layer 3: per-MG cards ---------------- #
    mg_by_id = {mg.metadata.get("mg_id"): mg for mg in (mgs or [])}
    categories = sorted(
        {
            (str(r.get("mr_index", "")).split("-")[1][0] if "-" in str(r.get("mr_index", "")) else "?")
            for r in records
        }
    )
    cat_options = "".join(
        f'<option value="{html.escape(c)}">Category {html.escape(c)}</option>'
        for c in categories
    )
    body += '<div class="card"><h2 style="margin-top:0">Per-Group Results</h2>\n'
    body += (
        '<div class="filter-bar">'
        '<label><input type="radio" name="lgmt-filter" value="all" checked onchange="lgmtFilter()"> All</label>'
        '<label><input type="radio" name="lgmt-filter" value="violations" onchange="lgmtFilter()"> Violations only</label>'
        '<label><input type="radio" name="lgmt-filter" value="consistent" onchange="lgmtFilter()"> Consistent only</label>'
        '<select id="lgmt-cat" onchange="lgmtFilter()">'
        '<option value="all">All categories</option>'
        f"{cat_options}</select>"
        '<input type="text" id="lgmt-search" placeholder="Search premises / mr / mg_id…" oninput="lgmtFilter()">'
        '<span class="filter-count" id="lgmt-count"></span>'
        "</div>\n"
    )
    body += "\n".join(_mg_card(i, r, None, mg_by_id) for i, r in enumerate(records))
    body += "</div>"

    page = _html_page(title, body)
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"HTML report generated: {os.path.abspath(output_file)}")
    return output_file
