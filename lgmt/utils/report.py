"""HTML report generation for MG transformations and inference results.

The side-by-side comparison table reuses the layout of the original
``metamorphic_relations/check_mr.py`` report.
"""
import html
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from lgmt.core.structure import MetamorphicGroups, TestCase

_CSS = """
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
    .container { max-width: 95%; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    h1 { color: #333; border-bottom: 2px solid #eee; padding-bottom: 10px; }
    h2 { color: #555; margin-top: 30px; background: #e9ecef; padding: 10px; border-radius: 5px; }

    .comparison-table { width: 100%; border-collapse: collapse; margin-top: 10px; table-layout: fixed; }
    .comparison-table th { background-color: #343a40; color: white; padding: 12px; text-align: left; border-bottom: 2px solid #dee2e6; }
    .comparison-table td { padding: 10px; border-bottom: 1px solid #dee2e6; vertical-align: top; word-wrap: break-word; font-size: 14px; }

    .col-logic { width: 30%; background-color: #f8f9fa; }
    .col-text { width: 20%; }

    .premise-row:hover { background-color: #f1f3f5; }

    .changed-source { background-color: #fff3cd !important; }
    .changed-followup { background-color: #d4edda !important; }

    .conclusion-row { font-weight: bold; border-top: 2px solid #6c757d; background-color: #e2e6ea; }
    .conclusion-changed { background-color: #ffeeba; }

    .tag { display: inline-block; padding: 2px 6px; font-size: 11px; border-radius: 4px; background-color: #6c757d; color: white; margin-right: 5px; margin-bottom: 5px; }
    .split-item { margin-bottom: 8px; padding: 8px; background-color: #e8f5e9; border-left: 4px solid #4caf50; border-radius: 0 4px 4px 0; }

    pre { white-space: pre-wrap; margin: 0; font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace; font-size: 13px; color: #d63384; }
    .text-content { font-family: Georgia, serif; color: #495057; font-style: italic; }

    .section-header { font-weight: bold; color: #495057; margin-bottom: 5px; display: block; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }

    .metrics-table { border-collapse: collapse; margin: 15px 0; }
    .metrics-table th, .metrics-table td { border: 1px solid #dee2e6; padding: 6px 12px; text-align: right; }
    .metrics-table th { background-color: #343a40; color: white; }
    .metrics-table td:first-child, .metrics-table th:first-child { text-align: left; }

    .badge { display: inline-block; padding: 3px 10px; font-size: 12px; font-weight: bold; border-radius: 10px; color: white; margin-right: 6px; }
    .badge-consistent { background-color: #28a745; }
    .badge-violation { background-color: #dc3545; }
    .badge-correct { background-color: #17a2b8; }
    .badge-wrong { background-color: #ffc107; color: #333; }
"""


def _render_comparison_table(source: TestCase, followup: TestCase) -> str:
    """Render the 4-column source/follow-up comparison table."""
    rows = ""

    changes_map: Dict[int, list] = {}
    consumed_f_indices = set()
    tagged_f_indices = set()

    for f_idx, f_text in enumerate(followup.premises_text):
        match = re.search(r"\[Changed_(\d+)\]", f_text)
        if match:
            s_idx = int(match.group(1))
            changes_map.setdefault(s_idx, [])
            changes_map[s_idx].append(
                (followup.premises_logic[f_idx], f_text, f_idx)
            )
            tagged_f_indices.add(f_idx)

    f_ptr = 0

    for s_idx, s_logic in enumerate(source.premises_logic):
        s_text_val = (
            source.premises_text[s_idx] if s_idx < len(source.premises_text) else ""
        )
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
                    f'<div class="split-item"><span class="tag">P{part_idx+1}</span>'
                    f"<pre>{html.escape(part_logic)}</pre></div>"
                )
                f_text_html += (
                    f'<div class="split-item text-content">'
                    f"{html.escape(part_text)}</div>"
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
                    f'<span class="tag">P{f_ptr+1}</span>'
                    f"<pre>{html.escape(f_logic_val)}</pre>"
                )
                f_text_html = (
                    f'<div class="text-content">{html.escape(f_text_val)}</div>'
                )
                consumed_f_indices.add(f_ptr)
                f_ptr += 1
            else:
                f_logic_html = "<i>(Missing)</i>"

        rows += f"""
        <tr class="premise-row">
            <td class="{s_style_class}"><span class="tag">P{s_idx+1}</span>{s_logic_html}</td>
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
                f'<span class="tag">P{f_ptr+1}</span>'
                f"<pre>{html.escape(f_logic_val)}</pre>"
            )
            f_text_html = (
                f'<div class="text-content">{html.escape(f_text_val)}</div>'
            )
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
</body>
</html>"""


def generate_transformation_report(
    results: List[Tuple[TestCase, TestCase, str]],
    output_file: str = "mr_report.html",
) -> str:
    """Report raw MR transformations: list of (source, followup, mr_name)."""
    body = ""
    for idx, (source, followup, mr_name) in enumerate(results):
        body += f"<h2>Example #{idx + 1} ({html.escape(mr_name)})</h2>\n"
        body += _render_comparison_table(source, followup)
    page = _html_page("Metamorphic Relation Check Report", body)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"HTML report generated: {os.path.abspath(output_file)}")
    return output_file


def _badge(text: str, css: str) -> str:
    return f'<span class="badge {css}">{html.escape(text)}</span>'


def _metrics_table_html(metrics: Dict[str, Any]) -> str:
    header = (
        "<tr><th>Scope</th><th>Total</th><th>MVR</th><th>Acc (source)</th>"
        "<th>Acc (consistent)</th><th>HDR</th><th>FUR</th></tr>"
    )
    rows = ""
    overall = (
        "<tr><td>ALL</td>"
        f"<td>{metrics['total']}</td>"
        f"<td>{metrics['mvr'] * 100:.2f}%</td>"
        f"<td>{metrics['acc_static'] * 100:.2f}%</td>"
        f"<td>{metrics['acc_cons'] * 100:.2f}%</td>"
        f"<td>{metrics['hdr'] * 100:.2f}%</td>"
        f"<td>{metrics['fur'] * 100:.2f}%</td></tr>"
    )
    for row in metrics.get("per_category", []):
        rows += (
            f"<tr><td>Category {html.escape(row['key'])}</td>"
            f"<td>{row['total']}</td>"
            f"<td>{row['mvr'] * 100:.2f}%</td>"
            f"<td>-</td><td>-</td>"
            f"<td>{row['hdr'] * 100:.2f}%</td>"
            f"<td>{row['fur'] * 100:.2f}%</td></tr>"
        )
    for row in metrics.get("per_mr", []):
        rows += (
            f"<tr><td>{html.escape(row['key'])}</td>"
            f"<td>{row['total']}</td>"
            f"<td>{row['mvr'] * 100:.2f}%</td>"
            f"<td>-</td><td>-</td>"
            f"<td>{row['hdr'] * 100:.2f}%</td>"
            f"<td>{row['fur'] * 100:.2f}%</td></tr>"
        )
    return f'<table class="metrics-table">{header}{overall}{rows}</table>'


def generate_run_report(
    records: List[Dict[str, Any]],
    metrics: Dict[str, Any],
    output_file: str,
    mgs: Optional[List[MetamorphicGroups]] = None,
    title: str = "LGMT Metamorphic Evaluation Report",
) -> str:
    """Full evaluation report: metrics summary + per-MG verdict details."""
    mg_by_id = {mg.metadata.get("mg_id"): mg for mg in (mgs or [])}

    body = "<h2>Metrics Summary</h2>\n"
    body += _metrics_table_html(metrics)

    body += "<h2>Per-Group Results</h2>\n"
    for idx, record in enumerate(records):
        mg_id = str(record.get("mg_id", f"#{idx + 1}"))
        consistent = record.get("is_consistent")
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

        heading = (
            f"#{idx + 1} | {html.escape(mg_id)} | "
            f"{html.escape(str(record.get('mr_index', '')))} "
            f"{html.escape(str(record.get('mr_name', '')))}"
        )
        body += f"<h2>{heading}</h2>\n"
        body += (
            f"<p>{consistency_badge}{src_badge}{fol_badge}"
            f'<span class="badge" style="background-color:#6c757d">'
            f"ground truth: {gt}</span></p>\n"
        )

        mg = mg_by_id.get(mg_id)
        if mg is not None:
            body += _render_comparison_table(mg.source_case, mg.followup_case)
        else:
            for side, key in (("Source", "source_input"), ("Follow-up", "followup_input")):
                inp = record.get(key, {}) or {}
                body += f'<p><span class="section-header">{side}</span></p>'
                for p in inp.get("premises_text", []):
                    body += f'<div class="text-content">{html.escape(str(p))}</div>'
                body += (
                    f'<div class="text-content"><b>Conclusion:</b> '
                    f"{html.escape(str(inp.get('conclusion_text', '')))}</div>"
                )
        body += "\n"

    page = _html_page(title, body)
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"HTML report generated: {os.path.abspath(output_file)}")
    return output_file
