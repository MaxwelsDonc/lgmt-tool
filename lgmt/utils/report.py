"""HTML report generation for MG transformations and inference results.

The evaluation report is an evidence chain organized as
"how bad -> where -> prove it", and every number drills down to atomic
cases:

    1. Leaderboard (sortable; reference models only on matching calibers).
    2. Metric detail (cards + collapsible tables; violation counts link
       into the per-group view with filters applied).
    3. Per-MG audit view (violations as full cards rendered lazily,
       consistent groups as one-line summaries expandable on demand,
       with side-by-side FOL/NL diffs and CoT reasoning traces).

Everything is inlined (CSS/JS) so the report opens offline by double-click.
"""
import html
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lgmt.core.structure import MetamorphicGroups, TestCase

REFERENCE_PATH = str(Path(__file__).resolve().parent.parent / "data" / "reference_metrics.json")
REFERENCE_PROMPTING = "zero_cot"


def _reference_snapshot() -> str:
    try:
        from lgmt import __version__
    except Exception:
        __version__ = "0.1.0"
    return f"2026-09, LGMT v{__version__}"


REFERENCE_SNAPSHOT = _reference_snapshot()

#: How many violation cards render upfront; more load on demand.
LAZY_BATCH = 30

_METRIC_TIPS = {
    "mvr": "Metamorphic Violation Rate: fraction of groups where source and follow-up verdicts disagree (lower is better).",
    "acc_static": "Static Accuracy: accuracy on original source cases alone (higher is better).",
    "acc_cons": "Consistent Accuracy: fraction of groups where BOTH source and follow-up verdicts are correct (higher is better).",
    "hdr": "Harmful Disagreement Rate: fraction of groups judged correctly on source but flipped to wrong on follow-up (lower is better).",
    "fur": "Flaw-persisting Unanimous Rate: fraction of groups where both verdicts are wrong yet consistent (lower is better).",
}

# --------------------------------------------------------------------- #
# model-name aliasing: the same model often appears under different names
# (CLI dir names, API names, paper names). Centralized normalization.
# --------------------------------------------------------------------- #
_MODEL_ALIASES = {
    "chatgpt": "GPT-5.2",
    "gpt 5.2": "GPT-5.2",
    "gpt5.2": "GPT-5.2",
    "gpt 5": "GPT-5.2",
    "chatgpt reasoner": "o4-mini",
    "o4 mini": "o4-mini",
    "o4mini": "o4-mini",
    "claude": "Claude 4.5 Sonnet",
    "claude 4.5 sonnet": "Claude 4.5 Sonnet",
    "claude sonnet": "Claude 4.5 Sonnet",
    "deepseek": "DeepSeek Chat",
    "deepseek chat": "DeepSeek Chat",
    "deepseek v3": "DeepSeek Chat",
    "deepseek reasoner": "DeepSeek Reasoner",
    "deepseek r1": "DeepSeek Reasoner",
    "llama": "Llama 3.3 70B",
    "llama 3.3": "Llama 3.3 70B",
    "llama3.3": "Llama 3.3 70B",
    "llama 3.3 70b": "Llama 3.3 70B",
}


def normalize_model_name(name: str) -> str:
    """Normalize casing/hyphens/underscores and resolve known aliases."""
    key = re.sub(r"[\-_]+", " ", str(name)).strip().lower()
    key = re.sub(r"\s+", " ", key)
    return _MODEL_ALIASES.get(key, key)


_CSS = """
    * { box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin: 0; background: #f2f4f8; color: #2b3440; line-height: 1.45; }
    .container { max-width: 1220px; margin: 0 auto; padding: 28px 20px 60px; }
    h1 { font-size: 26px; margin: 0 0 4px; color: #17273f; letter-spacing: -0.3px; }
    h2 { font-size: 18px; margin: 34px 0 12px; color: #17273f; }
    .subtitle { color: #6b7280; font-size: 14px; margin-bottom: 18px; }
    .card { background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(16,24,40,.08), 0 1px 2px rgba(16,24,40,.04); padding: 20px 22px; margin-bottom: 20px; border: 1px solid #e8ecf2; }

    /* ---------- leaderboard ---------- */
    .lb-table { width: 100%; border-collapse: collapse; font-size: 14px; }
    .lb-table th { text-align: left; font-size: 12px; text-transform: uppercase; letter-spacing: .4px; color: #5a6577; padding: 9px 10px; border-bottom: 2px solid #e5e7eb; user-select: none; }
    .lb-table th.sortable { cursor: pointer; transition: color 0.15s ease; }
    .lb-table th.sortable:hover { color: #3a6ea5; }
    .lb-table th.sorted-asc::after { content: " ▲"; font-size: 10px; color: #3a6ea5; }
    .lb-table th.sorted-desc::after { content: " ▼"; font-size: 10px; color: #3a6ea5; }
    .lb-table td { padding: 9px 10px; border-bottom: 1px solid #f0f1f3; font-variant-numeric: tabular-nums; }
    .lb-table tr:hover td { background: #f8fafd; }
    .lb-table tr.this-run td { background: #eaf1f9; font-weight: 600; }
    .lb-table tr.medal-1 td:first-child { color: #b8860b; font-weight: 700; }
    .lb-table tr.medal-2 td:first-child { color: #70757a; font-weight: 700; }
    .lb-table tr.medal-3 td:first-child { color: #a05a2c; font-weight: 700; }
    .lb-bar { display: inline-block; height: 10px; border-radius: 5px; background: linear-gradient(90deg, #3a6ea5, #6f9fd0); vertical-align: middle; margin-right: 8px; }
    .lb-mvr { white-space: nowrap; font-variant-numeric: tabular-nums; }
    .this-tag { display: inline-block; margin-left: 8px; padding: 1px 8px; border-radius: 9px; background: #3a6ea5; color: #fff; font-size: 11px; font-weight: 700; }
    .ref-tag { display: inline-block; margin-left: 8px; padding: 1px 6px; border-radius: 4px; background: #eef1f5; color: #6b7280; font-size: 10px; }
    .lb-note { color: #6b7280; font-size: 12.5px; margin-top: 10px; }
    .lb-guardrail { color: #8a6d1d; font-size: 12.5px; margin-top: 4px; }
    .lb-hint { background: #fff8e6; border: 1px solid #f3e3b3; color: #7a6414; border-radius: 10px; padding: 12px 14px; font-size: 13.5px; }
    .all-failed-banner { background: #fef2f2; border: 1px solid #f87171; color: #b91c1c; border-radius: 10px; padding: 14px 16px; font-size: 14.5px; font-weight: 600; margin-bottom: 18px; }

    /* ---------- metric cards ---------- */
    .metric-cards { display: flex; flex-wrap: wrap; gap: 14px; }
    .metric-card { flex: 1 1 160px; border-radius: 12px; padding: 15px 18px; color: #fff; box-shadow: 0 1px 3px rgba(16,24,40,.12); }
    .metric-card .mc-value { font-size: 28px; font-weight: 750; line-height: 1.1; font-variant-numeric: tabular-nums; }
    .metric-card .mc-label { font-size: 12px; opacity: .95; margin-top: 5px; text-transform: uppercase; letter-spacing: .5px; font-weight: 600; }
    .metric-card .mc-sub { font-size: 11px; opacity: .82; margin-top: 3px; line-height: 1.25; }
    .mc-red { background: linear-gradient(135deg, #b83227, #dc6b5b); }
    .mc-amber { background: linear-gradient(135deg, #b9770e, #e2a13d); }
    .mc-green { background: linear-gradient(135deg, #1f7a4c, #3aa16d); }
    .mc-blue { background: linear-gradient(135deg, #335c8d, #5b8bc2); }
    .mc-grey { background: linear-gradient(135deg, #4b5563, #74808f); }
    .meta-line { color: #6b7280; font-size: 13px; margin: 10px 0 8px; }
    .meta-line code { background: #eef1f5; padding: 1px 6px; border-radius: 5px; font-size: 12px; color: #1f2937; }

    details.full-metrics summary { cursor: pointer; color: #3a6ea5; font-weight: 600; font-size: 14px; margin: 10px 0 8px; user-select: none; }
    .metrics-table { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 13px; }
    .metrics-table th, .metrics-table td { border: 1px solid #e5e7eb; padding: 6px 10px; text-align: right; font-variant-numeric: tabular-nums; }
    .metrics-table th { background: #f7f8fa; color: #4b5563; }
    .metrics-table td:first-child, .metrics-table th:first-child { text-align: left; }
    .metrics-table caption { caption-side: top; text-align: left; color: #6b7280; font-size: 12px; padding-bottom: 4px; }
    a.drill { color: #3a6ea5; font-weight: 600; text-decoration: none; }
    a.drill:hover { text-decoration: underline; }

    /* ---------- filter bar + MG cards ---------- */
    .filter-bar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 14px; background: #f8fafc; padding: 10px 12px; border-radius: 10px; border: 1px solid #e5e7eb; }
    .filter-bar label { font-size: 13px; color: #374151; display: inline-flex; align-items: center; gap: 5px; cursor: pointer; font-weight: 500; }
    .filter-bar input[type="text"] { flex: 1 1 220px; padding: 7px 10px; border: 1px solid #d1d5db; border-radius: 8px; font-size: 13px; background: #fff; }
    .filter-bar select { padding: 7px 10px; border: 1px solid #d1d5db; border-radius: 8px; font-size: 13px; background: #fff; }
    .filter-count { font-size: 12.5px; color: #4b5563; margin-left: auto; font-weight: 600; }

    details.mg-card { background: #fff; border-radius: 10px; box-shadow: 0 1px 2px rgba(16,24,40,.06); margin-bottom: 10px; border: 1px solid #e5e7eb; overflow: hidden; }
    details.mg-card summary { cursor: pointer; padding: 11px 16px; display: flex; flex-wrap: wrap; align-items: center; gap: 8px; list-style: none; background: #fcfcfd; }
    details.mg-card summary:hover { background: #f5f8fc; }
    details.mg-card summary::-webkit-details-marker { display: none; }
    .mg-title { font-weight: 600; font-size: 13.5px; color: #17273f; }
    .mg-sub { color: #6b7280; font-size: 12.5px; margin-left: auto; }
    .card-body { padding: 0 16px 16px; border-top: 1px solid #f0f2f5; }

    .mg-summary { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; background: #fff; border: 1px solid #edf0f4; border-radius: 8px; padding: 7px 12px; margin-bottom: 5px; cursor: pointer; font-size: 13px; transition: background 0.12s ease; }
    .mg-summary:hover { background: #f4f7fb; }
    .mg-summary .mg-sub-mr { color: #4b5563; font-size: 12.5px; }
    .mg-summary .mg-sub { margin-left: auto; }

    .load-more { display: block; margin: 14px auto 4px; padding: 8px 22px; border: 1px solid #cbd5e1; border-radius: 8px; background: #fff; color: #3a6ea5; font-weight: 600; font-size: 13.5px; cursor: pointer; }
    .load-more:hover { background: #f2f6fb; }

    .badge { display: inline-block; padding: 2px 10px; font-size: 11px; font-weight: 700; border-radius: 10px; color: #fff; letter-spacing: 0.2px; }
    .badge-consistent { background: #1f9d55; }
    .badge-violation { background: #d64541; }
    .badge-error { background: #6b7280; }
    .badge-correct { background: #167c9c; }
    .badge-wrong { background: #e2a13d; color: #4d3a05; }

    /* ---------- comparison table ---------- */
    .comparison-table { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 13px; margin-top: 10px; border: 1px solid #e5e7eb; }
    .comparison-table th { background: #f7f8fa; color: #4b5563; padding: 8px 10px; text-align: left; border-bottom: 2px solid #e5e7eb; font-size: 11.5px; text-transform: uppercase; letter-spacing: .4px; }
    .comparison-table td { padding: 8px 10px; border-bottom: 1px solid #f0f1f3; vertical-align: top; word-wrap: break-word; }
    .col-logic { width: 30%; background: #fbfcfe; }
    .col-text { width: 20%; }
    .changed-source { background: #fff8e6 !important; }
    .changed-followup { background: #eaf7ee !important; }
    .conclusion-row { font-weight: 700; border-top: 2px solid #9aa3ad; background: #f2f4f6; }
    .conclusion-changed { background: #ffefc2 !important; }
    .tag { display: inline-block; padding: 1px 6px; font-size: 10px; font-weight: 700; border-radius: 4px; background: #64748b; color: #fff; margin-right: 5px; vertical-align: middle; }
    .tag-rewritten { background: #1f8b4c; color: #fff; font-style: normal; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
    .split-item { margin-bottom: 6px; padding: 6px 8px; background: #eaf7ee; border-left: 3px solid #1f9d55; border-radius: 0 4px 4px 0; }
    pre { white-space: pre-wrap; margin: 0; font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace; font-size: 12px; color: #9d2958; display: inline; }
    .text-content { font-family: Georgia, "Times New Roman", serif; color: #374151; font-style: italic; }
    .section-header { font-weight: 700; color: #6b7280; margin: 8px 0 4px; display: block; font-size: 11px; text-transform: uppercase; letter-spacing: .5px; }

    /* ---------- reasoning drawer & error banner ---------- */
    details.reasoning-box { margin-top: 10px; border: 1px solid #e2e8f0; border-radius: 8px; background: #f8fafc; }
    details.reasoning-box summary { padding: 7px 12px; font-size: 12px; font-weight: 600; color: #335c8d; cursor: pointer; user-select: none; }
    .reasoning-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; padding: 8px 12px 12px; border-top: 1px solid #e2e8f0; font-size: 12.5px; }
    .reasoning-col { background: #fff; border: 1px solid #e5e7eb; border-radius: 6px; padding: 8px 10px; color: #374151; white-space: pre-wrap; max-height: 220px; overflow-y: auto; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
    .reasoning-col h4 { margin: 0 0 4px; font-size: 11px; text-transform: uppercase; color: #6b7280; letter-spacing: 0.4px; }
    .error-banner { margin-top: 10px; padding: 8px 12px; border-radius: 6px; background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; font-size: 12.5px; font-family: monospace; }

    footer { margin-top: 40px; text-align: center; color: #9aa3ad; font-size: 12.5px; }
    footer a { color: #3a6ea5; text-decoration: none; }
"""

_JS = r"""
// ---------- leaderboard sorting ----------
var LB = {key: null, dir: 1};
// Accuracy metrics are higher-is-better (default descending on first click);
// error/violation rates are lower-is-better (default ascending on first click).
var DESC_BY_DEFAULT = {acc_static: true, acc_cons: true};

function lbSort(key){
  if (LB.key === key) {
    LB.dir *= -1;
  } else {
    LB.key = key;
    LB.dir = DESC_BY_DEFAULT[key] ? -1 : 1;
  }
  var tbody = document.querySelector('#lb-table tbody');
  if (!tbody) return;
  var rows = Array.prototype.slice.call(tbody.rows);
  rows.sort(function(a, b){
    if (key === 'model') {
      return LB.dir * a.dataset.model.localeCompare(b.dataset.model);
    }
    return LB.dir * (parseFloat(a.dataset[key]) - parseFloat(b.dataset[key]));
  });
  rows.forEach(function(r, i){
    tbody.appendChild(r);
    r.cells[0].textContent = i + 1;
    r.classList.remove('medal-1', 'medal-2', 'medal-3');
    if (i === 0) r.classList.add('medal-1');
    else if (i === 1) r.classList.add('medal-2');
    else if (i === 2) r.classList.add('medal-3');
  });
  document.querySelectorAll('#lb-table th.sortable').forEach(function(th){
    th.classList.remove('sorted-asc', 'sorted-desc');
    if (th.dataset.sort === LB.key) {
      th.classList.add(LB.dir === 1 ? 'sorted-asc' : 'sorted-desc');
    }
  });
}

// ---------- per-group view: data-driven, lazy rendering ----------
var DATA = [];
try { DATA = JSON.parse(document.getElementById('lgmt-data').textContent); } catch (e) { DATA = []; }
var LAZY_BATCH = 30;
var violRendered = 0;
var mgHost = null, sentinel = null;

function elemFrom(html){
  var t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}
function esc(s){
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function escapeAttr(s){ return String(s).replace(/"/g, '&quot;'); }

function cleanChangedTag(text){
  var raw = String(text == null ? '' : text);
  if (/^\[Changed_(\d+|conclusion)\]\s*/i.test(raw)) {
    var stripped = raw.replace(/^\[Changed_(\d+|conclusion)\]\s*/i, '');
    return '<span class="tag tag-rewritten">REWRITTEN</span>' + esc(stripped);
  }
  return esc(raw);
}

// four-column source/follow-up comparison, mirroring the server-side renderer
function buildCompareTable(src, fol){
  if (!src.pl || !src.pl.length) {  // text-only fallback (legacy records without FOL)
    var t = '<span class="section-header">Source</span>';
    (src.pt || []).forEach(function(p){ t += '<div class="text-content">' + cleanChangedTag(p) + '</div>'; });
    t += '<div class="text-content"><b>Conclusion:</b> ' + cleanChangedTag(src.ct) + '</div>';
    t += '<span class="section-header">Follow-up</span>';
    (fol.pt || []).forEach(function(p){ t += '<div class="text-content">' + cleanChangedTag(p) + '</div>'; });
    t += '<div class="text-content"><b>Conclusion:</b> ' + cleanChangedTag(fol.ct) + '</div>';
    return t;
  }
  var changes = {}, tagged = {}, consumed = {}, f_idx;
  (fol.pt || []).forEach(function(text, fi){
    var m = String(text).match(/\[Changed_(\d+)\]/i);
    if (m) {
      var si = parseInt(m[1], 10);
      (changes[si] = changes[si] || []).push(fi);
      tagged[fi] = true;
    }
  });
  var rows = '', f_ptr = 0;
  src.pl.forEach(function(s_logic, s_idx){
    var s_text = (src.pt && src.pt[s_idx]) || '', scls = '', fcls = '', fl = '', ft = '';
    if (changes[s_idx] !== undefined) {
      scls = 'changed-source'; fcls = 'changed-followup';
      changes[s_idx].forEach(function(fi){
        fl += '<div class="split-item"><span class="tag">P' + (fi + 1) + '</span><pre>' + esc(fol.pl[fi]) + '</pre></div>';
        ft += '<div class="split-item text-content">' + cleanChangedTag(fol.pt[fi]) + '</div>';
        consumed[fi] = true;
      });
    } else {
      while (f_ptr < fol.pl.length && (tagged[f_ptr] || consumed[f_ptr])) f_ptr++;
      if (f_ptr < fol.pl.length) {
        var changedLogic = (fol.pl[f_ptr] !== s_logic);
        var changedText = ((fol.pt && fol.pt[f_ptr]) || '') !== s_text;
        if (changedLogic || changedText) { scls = 'changed-source'; fcls = 'changed-followup'; }
        fl = '<span class="tag">P' + (f_ptr + 1) + '</span><pre>' + esc(fol.pl[f_ptr]) + '</pre>';
        ft = '<div class="text-content">' + cleanChangedTag((fol.pt && fol.pt[f_ptr]) || '') + '</div>';
        consumed[f_ptr] = true; f_ptr++;
      } else { fl = '<i>(Missing)</i>'; }
    }
    rows += '<tr><td class="' + scls + '"><span class="tag">P' + (s_idx + 1) + '</span><pre>' + esc(s_logic) + '</pre></td>'
      + '<td class="' + scls + '"><div class="text-content">' + cleanChangedTag(s_text) + '</div></td>'
      + '<td class="' + fcls + '">' + fl + '</td><td class="' + fcls + '">' + ft + '</td></tr>';
  });
  while (f_ptr < fol.pl.length) {
    if (!consumed[f_ptr]) {
      rows += '<tr><td><i>(Added premise)</i></td><td></td>'
        + '<td class="changed-followup"><span class="tag">P' + (f_ptr + 1) + '</span><pre>' + esc(fol.pl[f_ptr]) + '</pre></td>'
        + '<td class="changed-followup"><div class="text-content">' + cleanChangedTag((fol.pt && fol.pt[f_ptr]) || '') + '</div></td></tr>';
    }
    f_ptr++;
  }
  var concCls = 'conclusion-row' + ((src.cl !== fol.cl || src.ct !== fol.ct) ? ' conclusion-changed' : '');
  rows += '<tr class="' + concCls + '"><td><span class="tag">Conc</span><pre>' + esc(src.cl) + '</pre></td>'
    + '<td><div class="text-content">' + cleanChangedTag(src.ct) + '</div></td>'
    + '<td><span class="tag">Conc</span><pre>' + esc(fol.cl) + '</pre></td>'
    + '<td><div class="text-content">' + cleanChangedTag(fol.ct) + '</div></td></tr>';
  return '<table class="comparison-table"><thead><tr>'
    + '<th class="col-logic">Source Logic (FOL)</th><th class="col-text">Source Text (NL)</th>'
    + '<th class="col-logic">Follow-up Logic (FOL)</th><th class="col-text">Follow-up Text (NL)</th>'
    + '</tr></thead><tbody>' + rows + '</tbody></table>';
}

function buildReasoningHtml(rec){
  var extras = '';
  if (rec.err_msg) {
    extras += '<div class="error-banner">Inference error: ' + esc(rec.err_msg) + '</div>';
  }
  if (rec.src_reason || rec.fol_reason) {
    extras += '<details class="reasoning-box"><summary>View Model CoT Reasoning Trace (Source vs. Follow-up)</summary>'
      + '<div class="reasoning-grid">'
      + '<div class="reasoning-col"><h4>Source Reasoning (' + esc(rec.src_label) + ')</h4>' + esc(rec.src_reason || '(none)') + '</div>'
      + '<div class="reasoning-col"><h4>Follow-up Reasoning (' + esc(rec.fol_label) + ')</h4>' + esc(rec.fol_reason || '(none)') + '</div>'
      + '</div></details>';
  }
  return extras;
}

function cardHtml(rec){
  var badge = rec.error
    ? '<span class="badge badge-error">ERROR</span>'
    : (rec.consistent
        ? '<span class="badge badge-consistent">CONSISTENT</span>'
        : '<span class="badge badge-violation">VIOLATION</span>');
  var srcB = '<span class="badge ' + (rec.src_ok ? 'badge-correct' : 'badge-wrong') + '">source: '
    + esc(rec.src_label) + ' (' + (rec.src_ok ? 'correct' : 'wrong') + ')</span>';
  var folB = '<span class="badge ' + (rec.fol_ok ? 'badge-correct' : 'badge-wrong') + '">follow-up: '
    + esc(rec.fol_label) + ' (' + (rec.fol_ok ? 'correct' : 'wrong') + ')</span>';
  var openAttr = rec.consistent ? '' : ' open';
  return '<details class="mg-card"' + openAttr + '><summary><span class="mg-title">#'
    + (rec.i + 1) + ' ' + esc(rec.mg_id) + ' · ' + esc(rec.mr) + ' ' + esc(rec.mr_name) + '</span>'
    + badge + srcB + folB + '<span class="mg-sub">ground truth: ' + esc(rec.gt) + '</span></summary>'
    + '<div class="card-body">' + buildCompareTable(rec.src, rec.fol) + buildReasoningHtml(rec) + '</div></details>';
}

function summaryHtml(rec){
  return '<div class="mg-summary" data-mr="' + esc(rec.mr) + '" data-cat="' + esc(rec.cat) + '" ' +
    'data-cons="true" data-idx="' + rec.i + '" data-search="' + escapeAttr(rec.search) + '" ' +
    'onclick="toggleSummary(this)">' +
    '<span class="mg-title">' + esc(rec.mg_id) + '</span>' +
    '<span class="mg-sub-mr">' + esc(rec.mr) + ' ' + esc(rec.mr_name) + '</span>' +
    '<span class="badge badge-consistent">CONSISTENT</span>' +
    '<span class="mg-sub">ground truth: ' + esc(rec.gt) + ' · click to expand</span></div>';
}

function toggleSummary(el){
  var next = el.nextElementSibling;
  if (next && next.classList.contains('mg-card')) { next.remove(); return; }
  var rec = DATA[parseInt(el.dataset.idx, 10)];
  el.parentNode.insertBefore(elemFrom(cardHtml(rec)), el.nextSibling);
}

function currentFilter(){
  var mode = document.querySelector('input[name="lgmt-filter"]:checked').value;
  var cat = document.getElementById('lgmt-cat').value;
  var q = document.getElementById('lgmt-search').value.toLowerCase();
  return {mode: mode, cat: cat, q: q};
}
function recMatches(rec, f){
  if (f.mode === 'violations' && rec.consistent) return false;
  if (f.mode === 'consistent' && !rec.consistent) return false;
  if (f.cat !== 'all' && rec.cat !== f.cat) return false;
  if (f.q && rec.search.indexOf(f.q) < 0) return false;
  return true;
}

function renderMore(){
  var f = currentFilter();
  var viol = [];
  DATA.forEach(function(rec){ if (recMatches(rec, f) && !rec.consistent) viol.push(rec); });
  var slice = viol.slice(violRendered, violRendered + LAZY_BATCH);
  slice.forEach(function(rec){ mgHost.appendChild(elemFrom(cardHtml(rec))); });
  violRendered += slice.length;
  updateSentinel(viol.length);
  updateCount();
}
function updateSentinel(totalViol){
  if (!sentinel) return;
  var remaining = totalViol - violRendered;
  if (remaining <= 0) { sentinel.style.display = 'none'; }
  else {
    sentinel.style.display = '';
    sentinel.textContent = 'Load more violations (' + remaining + ' remaining)';
  }
}
function updateCount(){
  var f = currentFilter();
  var shown = 0, viol = 0;
  var failed = 0;
  DATA.forEach(function(rec){
    if (recMatches(rec, f)) { shown++; if (rec.error) failed++; else if (!rec.consistent) viol++; }
  });
  var el = document.getElementById('lgmt-count');
  var txt = shown + ' shown · ' + viol + ' violations';
  if (failed > 0) txt += ' · ' + failed + ' failed';
  if (el) el.textContent = txt;
}

function lgmtFilter(){
  if (!mgHost) return;
  var f = currentFilter();
  mgHost.innerHTML = '';
  violRendered = 0;
  // consistent groups: compact summary rows (cheap, render all matches)
  DATA.forEach(function(rec){
    if (rec.consistent && recMatches(rec, f)) mgHost.appendChild(elemFrom(summaryHtml(rec)));
  });
  // violations: full cards, lazily in batches
  renderMore();
}

// drill-down from metrics tables: apply filter + scroll to per-group view
function drillFilter(kind, value){
  document.querySelector('input[name="lgmt-filter"][value="violations"]').checked = true;
  if (kind === 'cat') {
    document.getElementById('lgmt-search').value = '';
    document.getElementById('lgmt-cat').value = value;
  } else if (kind === 'mr') {
    document.getElementById('lgmt-cat').value = 'all';
    document.getElementById('lgmt-search').value = value;
  } else if (kind === 'all') {
    document.getElementById('lgmt-cat').value = 'all';
    document.getElementById('lgmt-search').value = '';
  }
  lgmtFilter();
  document.getElementById('per-group').scrollIntoView({behavior: 'smooth'});
}

function initLgmtReport(){
  try { DATA = JSON.parse(document.getElementById('lgmt-data').textContent); } catch (e) { DATA = []; }
  mgHost = document.getElementById('mg-list');
  sentinel = document.getElementById('lgmt-more');
  if (mgHost) lgmtFilter();
  LB = {key: null, dir: 1};
  lbSort('mvr');  // establish default sort indicator
}

window.addEventListener('DOMContentLoaded', initLgmtReport);
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
    """Reference models are only ranked on the same data + prompting.

    The current run's model name is normalized; if it matches a reference
    model (e.g. "claude" == "Claude 4.5 Sonnet") the rows merge and the
    reference row becomes the highlighted "this run" row.
    """
    rows: List[Dict[str, Any]] = []
    if reference and caliber in ("demo_40", "full_3091"):
        for name, m in reference.get("models", {}).items():
            rows.append(_lb_row(name, m[caliber], is_reference=True))

    def _merge(run_name, m):
        norm = normalize_model_name(run_name)
        for r in rows:
            if normalize_model_name(r["model"]) == norm:
                r.update(
                    {
                        "mvr": m["mvr"],
                        "acc_static": m["acc_static"],
                        "acc_cons": m["acc_cons"],
                        "hdr": m["hdr"],
                        "fur": m["fur"],
                        "is_current": True,
                    }
                )
                return
        rows.append(_lb_row(run_name, m, is_current=True))

    _merge(current_name, current_metrics)
    for run in extra_runs:
        _merge(run["model"], run["metrics"])
    rows.sort(key=lambda r: (r["mvr"], normalize_model_name(r["model"])))
    return rows


def _leaderboard_html(rows, caliber, prompting, reference) -> Tuple[str, str]:
    if not rows:
        return "", ""
    max_mvr = max(r["mvr"] for r in rows) or 1.0

    def _head(label, key, sortable=True):
        cls = "sortable" if sortable else ""
        tip = _METRIC_TIPS.get(key, "")
        title_attr = f' title="{html.escape(tip, quote=True)}"' if tip else ""
        return f'<th class="{cls}" data-sort="{key}"{title_attr} onclick="lbSort(\'{key}\')">{label}</th>'

    head = (
        "<tr><th>Rank</th>"
        + _head("Model", "model")
        + _head("MVR ↓", "mvr")
        + _head("Acc_static ↑", "acc_static")
        + _head("Acc_cons ↑", "acc_cons")
        + _head("HDR ↓", "hdr")
        + _head("FUR ↓", "fur")
        + "</tr>"
    )
    body = ""
    for rank, r in enumerate(rows, 1):
        medal = f"medal-{rank} " if rank <= 3 else ""
        current = "this-run" if r["is_current"] else ""
        width = max(2, int(r["mvr"] / max_mvr * 120))
        tags = ""
        if r["is_current"]:
            tags += '<span class="this-tag">▶ this run</span>'
        if r["is_reference"]:
            tags += '<span class="ref-tag">reference</span>'
        body += (
            f'<tr class="{medal}{current}" data-model="{html.escape(r["model"], quote=True)}" '
            f'data-mvr="{r["mvr"]}" data-acc_static="{r["acc_static"]}" '
            f'data-acc_cons="{r["acc_cons"]}" data-hdr="{r["hdr"]}" data-fur="{r["fur"]}">'
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
        f'<table class="lb-table" id="lb-table"><thead>{head}</thead>'
        f"<tbody>{body}</tbody></table>"
    )
    if caliber in ("demo_40", "full_3091"):
        subset = "demo-40 subset" if caliber == "demo_40" else "full 3,091-group evaluation set"
        note = f"ranked on {subset} · zero-shot CoT · reference: 6 SOTA models"
        if reference and prompting != reference.get("prompting", REFERENCE_PROMPTING):
            note += (
                f" — note: reference used {reference.get('prompting', REFERENCE_PROMPTING)}, "
                f"this run used {prompting}"
            )
    else:
        note = (
            f"ranked on your data set · {len(rows)} model run(s) · mutual comparison"
            if len(rows) >= 2
            else ""
        )
    return table, note


def _clean_changed_tag_py(text: str) -> str:
    raw = str(text or "")
    m = re.match(r"^\[Changed_(?:\d+|conclusion)\]\s*(.*)$", raw, flags=re.IGNORECASE | re.DOTALL)
    if m:
        return f'<span class="tag tag-rewritten">REWRITTEN</span>{html.escape(m.group(1))}'
    return html.escape(raw)


# --------------------------------------------------------------------- #
# comparison table (server-side helper)
# --------------------------------------------------------------------- #
def _render_comparison_table(source: TestCase, followup: TestCase) -> str:
    rows = ""

    changes_map: Dict[int, list] = {}
    consumed_f_indices = set()
    tagged_f_indices = set()

    for f_idx, f_text in enumerate(followup.premises_text):
        match = re.search(r"\[Changed_(\d+)\]", f_text, flags=re.IGNORECASE)
        if match:
            s_idx = int(match.group(1))
            changes_map.setdefault(s_idx, [])
            changes_map[s_idx].append((followup.premises_logic[f_idx], f_text, f_idx))
            tagged_f_indices.add(f_idx)

    f_ptr = 0

    for s_idx, s_logic in enumerate(source.premises_logic):
        s_text_val = source.premises_text[s_idx] if s_idx < len(source.premises_text) else ""
        s_logic_html = f"<pre>{html.escape(s_logic)}</pre>"
        s_text_html = f'<div class="text-content">{_clean_changed_tag_py(s_text_val)}</div>'

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
                    f'<div class="split-item text-content">{_clean_changed_tag_py(part_text)}</div>'
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
                f_text_html = f'<div class="text-content">{_clean_changed_tag_py(f_text_val)}</div>'
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
            f_text_html = f'<div class="text-content">{_clean_changed_tag_py(f_text_val)}</div>'
            rows += f"""
            <tr class="premise-row">
                <td><i>(Added premise)</i></td>
                <td></td>
                <td class="changed-followup">{f_logic_html}</td>
                <td class="changed-followup">{f_text_html}</td>
            </tr>"""
        f_ptr += 1

    s_conc_logic = html.escape(source.conclusion_logic)
    s_conc_text = _clean_changed_tag_py(source.conclusion_text)
    f_conc_logic = html.escape(followup.conclusion_logic)
    f_conc_text = _clean_changed_tag_py(followup.conclusion_text)

    conc_row_class = "conclusion-row"
    if source.conclusion_logic != followup.conclusion_logic or source.conclusion_text != followup.conclusion_text:
        conc_row_class += " conclusion-changed"

    rows += f"""
        <tr class="{conc_row_class}">
            <td><span class="tag">Conc</span><pre>{s_conc_logic}</pre></td>
            <td><div class="text-content">{s_conc_text}</div></td>
            <td><span class="tag">Conc</span><pre>{f_conc_logic}</pre></td>
            <td><div class="text-content">{f_conc_text}</div></td>
        </tr>"""

    return f"""
    <table class="comparison-table">
        <thead>
            <tr>
                <th class="col-logic">Source Logic (FOL)</th>
                <th class="col-text">Source Text (NL)</th>
                <th class="col-logic">Follow-up Logic (FOL)</th>
                <th class="col-text">Follow-up Text (NL)</th>
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
        LGMT · <a href="https://github.com/MaxwelsDonc/lgmt-tool">GitHub</a> ·
        Companion study: Knowledge-Based Systems (2026), in press ·
        Reference metrics: {html.escape(REFERENCE_SNAPSHOT)} ·
        generated {datetime.now().strftime("%Y-%m-%d %H:%M")}
    </footer>
    <script>{_JS}</script>
</body>
</html>"""


# --------------------------------------------------------------------- #
# evaluation report
# --------------------------------------------------------------------- #
def _metrics_table_html(metrics: Dict[str, Any]) -> str:
    """Full metrics tables; violation counts drill into the per-group view."""

    def _pct(x):
        return f"{x * 100:.2f}%"

    def _vcell(row, kind, key):
        return (
            f'<a class="drill" href="#per-group" '
            f"onclick=\"drillFilter('{kind}','{html.escape(key, quote=True)}');return false;\">"
            f"{row['violation_count']}</a>"
        )

    def _row(label, r, kind, key):
        return (
            f"<tr><td>{html.escape(label)}</td><td>{r['total']}</td>"
            f"<td>{_pct(r['mvr'])}</td>"
            f"<td>{_vcell(r, kind, key)}</td>"
            f"<td>{_pct(r['acc_static'])}</td>"
            f"<td>{_pct(r['acc_cons'])}</td>"
            f"<td>{_pct(r['hdr'])}</td>"
            f"<td>{_pct(r['fur'])}</td></tr>"
        )

    head = (
        "<tr><th>Scope</th><th>Total</th>"
        f'<th title="{html.escape(_METRIC_TIPS["mvr"], quote=True)}">MVR ↓</th>'
        "<th>Violations</th>"
        f'<th title="{html.escape(_METRIC_TIPS["acc_static"], quote=True)}">Acc_static ↑</th>'
        f'<th title="{html.escape(_METRIC_TIPS["acc_cons"], quote=True)}">Acc_cons ↑</th>'
        f'<th title="{html.escape(_METRIC_TIPS["hdr"], quote=True)}">HDR ↓</th>'
        f'<th title="{html.escape(_METRIC_TIPS["fur"], quote=True)}">FUR ↓</th></tr>'
    )
    overall = (
        "<tr><td><b>ALL</b></td>"
        f"<td>{metrics['total']}</td>"
        f"<td><b>{_pct(metrics['mvr'])}</b></td>"
        f"<td>{_vcell(metrics, 'all', '')}</td>"
        f"<td>{_pct(metrics['acc_static'])}</td>"
        f"<td>{_pct(metrics['acc_cons'])}</td>"
        f"<td>{_pct(metrics['hdr'])}</td>"
        f"<td>{_pct(metrics['fur'])}</td></tr>"
    )
    cat_rows = "".join(
        _row(f"Category {r['key']}", r, "cat", r["key"])
        for r in metrics.get("per_category", [])
    )
    mr_rows = "".join(
        _row(r["key"], r, "mr", r["key"]) for r in metrics.get("per_mr", [])
    )
    open_attr = " open" if metrics.get("total", 0) <= 100 else ""
    return (
        f'<table class="metrics-table">{head}{overall}</table>'
        f'<details class="full-metrics"{open_attr}><summary>Full metrics by category and by MR'
        f" (click any violation count to filter the evidence cards below)</summary>"
        f'<table class="metrics-table">{head}{cat_rows}</table>'
        f'<table class="metrics-table">{head}{mr_rows}</table></details>'
    )


def _metric_card(value: str, label: str, css: str, sublabel: str = "") -> str:
    sub_html = f'<div class="mc-sub">{html.escape(sublabel)}</div>' if sublabel else ""
    return (
        f'<div class="metric-card {css}">'
        f'<div class="mc-value">{value}</div>'
        f'<div class="mc-label">{html.escape(label)}</div>'
        f"{sub_html}</div>"
    )


def _record_view(records, mg_by_id) -> str:
    """Serialize records compactly; the browser builds cards on demand.

    Uses either explicit ``mgs`` passed at report time OR the
    ``premises_logic`` / ``conclusion_logic`` fields stored directly inside
    ``source_input`` / ``followup_input`` in ``results.jsonl``.
    """
    views = []
    for idx, record in enumerate(records):
        mg_id = str(record.get("mg_id", f"#{idx + 1}"))
        mr_index = str(record.get("mr_index", ""))
        category = mr_index.split("-")[1][0] if "-" in mr_index else "?"
        mg_obj = mg_by_id.get(mg_id)
        if mg_obj is not None:
            src = {
                "pl": mg_obj.source_case.premises_logic,
                "pt": mg_obj.source_case.premises_text,
                "cl": mg_obj.source_case.conclusion_logic,
                "ct": mg_obj.source_case.conclusion_text,
            }
            fol = {
                "pl": mg_obj.followup_case.premises_logic,
                "pt": mg_obj.followup_case.premises_text,
                "cl": mg_obj.followup_case.conclusion_logic,
                "ct": mg_obj.followup_case.conclusion_text,
            }
        else:
            src_in = record.get("source_input", {}) or {}
            fol_in = record.get("followup_input", {}) or {}
            src_pl = src_in.get("premises_logic")
            fol_pl = fol_in.get("premises_logic")
            src = {
                "pl": list(src_pl) if src_pl else None,
                "pt": list(src_in.get("premises_text", [])),
                "cl": str(src_in.get("conclusion_logic", "")),
                "ct": str(src_in.get("conclusion_text", "")),
            }
            fol = {
                "pl": list(fol_pl) if fol_pl else None,
                "pt": list(fol_in.get("premises_text", [])),
                "cl": str(fol_in.get("conclusion_logic", "")),
                "ct": str(fol_in.get("conclusion_text", "")),
            }
        src_resp = record.get("source_response", {}) or {}
        fol_resp = record.get("followup_response", {}) or {}
        search_blob = " ".join(
            [
                mg_id,
                mr_index,
                str(record.get("mr_name", "")),
                str(record.get("ground_truth", "")),
                " ".join(str(p) for p in src["pt"]),
                " ".join(str(p) for p in fol["pt"]),
            ]
        ).lower()
        views.append(
            {
                "i": idx,
                "mg_id": mg_id,
                "mr": mr_index,
                "mr_name": str(record.get("mr_name", "")),
                "cat": category,
                "gt": str(record.get("ground_truth", "")),
                "consistent": record.get("is_consistent") is True,
                "error": bool(record.get("error")),
                "err_msg": str(record.get("error", "")) if record.get("error") else "",
                "src_label": str(src_resp.get("response_label", "?")),
                "src_ok": bool(src_resp.get("is_correct")),
                "src_reason": str(src_resp.get("reasoning", "")).strip(),
                "fol_label": str(fol_resp.get("response_label", "?")),
                "fol_ok": bool(fol_resp.get("is_correct")),
                "fol_reason": str(fol_resp.get("reasoning", "")).strip(),
                "search": search_blob,
                "src": src,
                "fol": fol,
            }
        )
    # "</" must not appear inside the inline script tag
    return json.dumps(views, ensure_ascii=False).replace("</", "<\\/")


def _field_from_records(records, field) -> Optional[str]:
    for r in records:
        v = r.get(field)
        if v:
            return str(v)
    return None



def _all_failed_banner(metrics: Dict[str, Any]) -> str:
    """Prominent banner when every group failed (nothing valid to score)."""
    failed = metrics.get("failed", 0)
    if failed and metrics.get("total", 0) == 0:
        return (
            '<div class="all-failed-banner">All '
            f"{failed} groups failed — check API key / endpoint / model name."
            "</div>\n"
        )
    return ""


def render_report_body(
    records: List[Dict[str, Any]],
    metrics: Dict[str, Any],
    mgs: Optional[List[MetamorphicGroups]] = None,
    model: Optional[str] = None,
    prompting: Optional[str] = None,
    extra_runs: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Render the inner HTML cards (Leaderboard + Metrics + Per-Group View)."""
    prompting = prompting or _field_from_records(records, "prompting") or "unspecified"
    current_name = model or _field_from_records(records, "model") or "this run"
    extra_runs = extra_runs or []
    mg_ids = [r.get("mg_id") for r in records]
    reference = load_reference()
    caliber = detect_caliber(mg_ids, reference) if reference else "custom"

    body = ""
    body += _all_failed_banner(metrics)

    # ---------------- layer 1: leaderboard ---------------- #
    body += '<div class="card"><h2 style="margin-top:0">Leaderboard</h2>\n'
    if caliber in ("demo_40", "full_3091") or extra_runs:
        rows = build_leaderboard_rows(
            current_name, metrics, extra_runs, caliber, reference
        )
        table, note = _leaderboard_html(rows, caliber, prompting, reference)
        body += table
        if note:
            body += f'<div class="lb-note">{html.escape(note)}</div>\n'
        if len(rows) >= 2:
            body += (
                '<div class="lb-guardrail">MVR ranks consistency only; a model must also be '
                "accurate — sort by Acc_cons for the combined view.</div>\n"
            )
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
        + _metric_card(
            f"{metrics['mvr'] * 100:.2f}%",
            "MVR (violation rate)",
            "mc-red",
            "Source & follow-up disagree (↓)",
        )
        + _metric_card(
            f"{metrics['acc_cons'] * 100:.2f}%",
            "Acc_cons (consistent acc)",
            "mc-green",
            f"Both correct (vs {metrics['acc_static'] * 100:.1f}% static ↑)",
        )
        + _metric_card(
            f"{metrics['hdr'] * 100:.2f}%",
            "HDR (harmful disagreement)",
            "mc-amber",
            "Source right → follow-up wrong (↓)",
        )
        + _metric_card(
            str(metrics["violation_count"]),
            "violations",
            "mc-blue",
            f"Out of {metrics['total']} valid groups",
        )
        + _metric_card(
            str(metrics["total"]),
            "metamorphic groups",
            "mc-grey",
            "Evaluated premise–conclusion pairs",
        )
        + "</div>"
    )
    meta_bits = [f'model <code>{html.escape(current_name)}</code>']
    meta_bits.append(f"prompting <code>{html.escape(prompting)}</code>")
    meta_bits.append(f"{len(records)} metamorphic groups")
    if metrics.get("failed"):
        meta_bits.append(
            f"<span style='color:#b3261e'>{metrics['failed']} failed (excluded)</span>"
        )
    meta_bits.append(f"generated {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if caliber != "custom":
        meta_bits.append(f"caliber <code>{caliber}</code>")
    body += f'<p class="meta-line">{" · ".join(meta_bits)}</p>\n'
    body += _metrics_table_html(metrics)
    body += "</div>"

    # ---------------- layer 3: per-MG audit view ---------------- #
    mg_by_id = {mg.metadata.get("mg_id"): mg for mg in (mgs or [])}
    categories = sorted(
        {
            (
                str(r.get("mr_index", "")).split("-")[1][0]
                if "-" in str(r.get("mr_index", ""))
                else "?"
            )
            for r in records
        }
    )
    cat_options = "".join(
        f'<option value="{html.escape(c)}">Category {html.escape(c)}</option>'
        for c in categories
    )
    body += '<div class="card" id="per-group"><h2 style="margin-top:0">Per-Group Results</h2>\n'
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
    body += f'<script type="application/json" id="lgmt-data">{_record_view(records, mg_by_id)}</script>\n'
    body += '<div id="mg-list"></div>\n'
    body += '<button class="load-more" id="lgmt-more" onclick="renderMore()">Load more</button>\n'
    body += "</div>"
    return body


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
    """Full evaluation report: leaderboard + metrics + per-MG audit view."""
    body = render_report_body(
        records,
        metrics,
        mgs=mgs,
        model=model,
        prompting=prompting,
        extra_runs=extra_runs,
    )
    page = _html_page(title, body)
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"HTML report generated: {os.path.abspath(output_file)}")
    return output_file
