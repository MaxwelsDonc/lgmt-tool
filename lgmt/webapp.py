"""LGMT Interactive Web Studio (Zero-Dependency Native Server + Gradio Adapter).

Provides three strictly isolated workflow tabs:
    1. Quick Demo (Offline)   — zero API key/network; 40-group or 3,091-group tour
    2. Benchmark Your Model   — evaluate any OpenAI-compatible endpoint on bundled sets
    3. Test Custom Cases      — three clean input modes (Quick Form, Unstructured Text,
                                Batch JSONL / File Upload) supporting English, Chinese,
                                Bilingual, Pure FOL, and Dual NL+FOL inputs.

Run locally (zero extra dependencies beyond core lgmt):
    lgmt web                  # serves on http://0.0.0.0:7860
    lgmt-web                  # console script alias
    python -m lgmt.webapp     # module entrypoint
"""
import html
import json
import os
import tempfile
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from lgmt.core.builder import (
    FOLTranslator,
    UnstructuredExtractor,
    build_metamorphic_groups,
    looks_like_fol,
    make_nl2fol_translator,
    make_realize_fn,
    make_unstructured_extractor,
    synthesize_missing_logic,
)
from lgmt.core.runner import PROMPTING_PRESETS, run_inference
from lgmt.core.structure import TestCase
from lgmt.models import MockLLMClient
from lgmt.models.openai_compat import OpenAICompatClient
from lgmt.mrs import ALL_MRS
from lgmt.utils.io import load_inference_records, load_metamorphic_groups
from lgmt.utils.labels import canonical_label
from lgmt.utils.metrics import compute_metrics, format_metrics_table
from lgmt.utils.report import (
    _CSS as REPORT_CSS,
    _JS as REPORT_JS,
    REFERENCE_SNAPSHOT,
    generate_run_report,
    render_report_body,
)

DEMO_MGS_PATH = str(Path(__file__).resolve().parent / "demo" / "demo_mgs.jsonl")

EXAMPLE_NL_EN_JSONL = """\
{"premises_text": ["Every patient who takes the medication recovers within a week.", "Alice takes the medication."], "conclusion_text": "Alice recovers within a week.", "metadata": {"label": "True"}}
{"premises_text": ["All contracts signed under duress are voidable.", "The Smith contract was signed under duress."], "conclusion_text": "The Smith contract is voidable.", "metadata": {"label": "True"}}
"""

EXAMPLE_NL_ZH_JSONL = """\
{"premises_text": ["所有在胁迫下签署的合同都是可撤销的。", "Smith合同是在胁迫下签署的。"], "conclusion_text": "Smith合同是可撤销的。", "metadata": {"label": "True"}}
{"premises_text": ["所有按时服药的患者都会在一周内康复。", "李明按时服药了。"], "conclusion_text": "李明会在一周内康复。", "metadata": {"label": "True"}}
"""

EXAMPLE_PURE_FOL_JSONL = """\
{"premises_logic": ["all x.(Bird(x) -> Fly(x))", "Bird(tweety)"], "conclusion_logic": "Fly(tweety)", "metadata": {"label": "True"}}
{"premises_logic": ["all x.(Manager(x) -> Office(x))", "Office(alice)"], "conclusion_logic": "Manager(alice)", "metadata": {"label": "Unknown"}}
"""

EXAMPLE_FOL_JSONL = """\
{"premises_logic": ["all x.(Man(x) -> Mortal(x))", "Man(socrates)"], "conclusion_logic": "Mortal(socrates)", "premises_text": ["All men are mortal.", "Socrates is a man."], "conclusion_text": "Socrates is mortal.", "metadata": {"label": "True"}}
{"premises_logic": ["all x.(Manager(x) -> Office(x))", "Office(alice)"], "conclusion_logic": "Manager(alice)", "premises_text": ["All managers have a private office.", "Alice has a private office."], "conclusion_text": "Alice is a manager.", "metadata": {"label": "Unknown"}}
"""

LISTING1_CUSTOM_MR_TEMPLATE = """\
import copy
from nltk.sem.logic import LogicParser, NegatedExpression
from lgmt.core.structure import MetamorphicRelation, TestCase


class MRCxDoubleNegation(MetamorphicRelation):
    def __init__(self):
        self.index = "MR-CX"
        self.name = "Double Negation (Custom)"

    def check_applicability_logic(self, fol: str) -> bool:
        return bool(fol)

    def source_templates(self) -> list[str]:
        return []

    def check_applicability(self, tc: TestCase) -> bool:
        return bool(tc.conclusion_logic)

    def transform(self, tc: TestCase) -> TestCase:
        follow = copy.deepcopy(tc)
        ast = LogicParser().parse(tc.conclusion_logic)
        follow.conclusion_logic = str(NegatedExpression(NegatedExpression(ast)))
        follow.conclusion_text = f"[Changed_conclusion] It is not the case that not ({tc.conclusion_text})"
        return follow
"""

EXAMPLE_PLAINTEXT_EN = """Every patient who takes the prescribed antiviral medication recovers within a week. Alice is a patient who takes the prescribed antiviral medication. Does Alice recover within a week?

All contracts signed under duress are legally voidable. The Smith commercial lease is a contract signed under duress. Is the Smith commercial lease legally voidable?"""

EXAMPLE_PLAINTEXT_ZH = """\
根据医疗指南，所有按时服用该抗病毒药物的患者都会在一周内康复。张伟是一名患者并且按时服用了该抗病毒药物。请问：张伟会在一周内康复吗？

所有在胁迫下签署的商业合同都是可撤销的。甲乙双方的采购协议是在胁迫下签署的商业合同。因此，甲乙双方的采购协议是可撤销的。"""

EXAMPLE_NL_JSONL = EXAMPLE_NL_EN_JSONL
EXAMPLE_JSONL = EXAMPLE_FOL_JSONL

#: Per-tab isolated run states ("demo", "benchmark", "custom") + legacy LAST_RUN
RUNS_BY_TAB: Dict[str, Dict[str, Any]] = {}
LAST_RUN: Dict[str, Any] = {}

#: Benchmark run history per (dataset, prompting): aggregates only, capped.
_BENCH_HISTORY_MAX = 5
_BENCH_HISTORY: Dict[tuple, "deque"] = {}

#: Live run progress per tab key: {"completed", "total", "failed", "done"}.
PROGRESS: Dict[str, Dict[str, Any]] = {}
_PROGRESS_LOCK = threading.Lock()


def _begin_progress(tab_key: str, total: int, results_path: str) -> None:
    with _PROGRESS_LOCK:
        PROGRESS[tab_key] = {
            "completed": 0,
            "total": total,
            "failed": 0,
            "done": False,
            "results_path": results_path,
        }


def _progress_callback(tab_key: str):
    """Build a run_inference progress_callback updating PROGRESS[tab_key]."""

    def update(completed: int, total: int) -> None:
        with _PROGRESS_LOCK:
            entry = PROGRESS.get(tab_key)
            if entry is None:
                return
            entry["completed"] = completed
            entry["total"] = total

    return update


def _finish_progress(tab_key: str, failed: int) -> None:
    with _PROGRESS_LOCK:
        entry = PROGRESS.get(tab_key)
        if entry is not None:
            entry["failed"] = failed
            entry["done"] = True


def _read_progress(tab_key: str) -> Dict[str, Any]:
    """Snapshot of a tab's progress; failed count is read from the results
    file so failures show up live without extra plumbing."""
    with _PROGRESS_LOCK:
        entry = PROGRESS.get(tab_key)
        if entry is None:
            return {"completed": 0, "total": 0, "failed": 0, "done": False}
        snapshot = dict(entry)
    path = snapshot.pop("results_path", None)
    if path and os.path.exists(path):
        failed = 0
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if '"is_valid": false' in line or '"is_valid":False' in line:
                        failed += 1
        except OSError:
            failed = snapshot.get("failed", 0)
        snapshot["failed"] = failed
        if not snapshot["done"]:
            snapshot["completed"] = max(snapshot["completed"], failed)
    return snapshot


# --------------------------------------------------------------------- #
# shared pipeline helpers
# --------------------------------------------------------------------- #
def _new_run_dir() -> str:
    return tempfile.mkdtemp(prefix="lgmt_web_")


def _find_full_eval_set() -> Optional[str]:
    rel = Path("data") / "metamorphic_group" / "processed_mgs_core" / "processed_mgs_3091.jsonl"
    candidates = [
        Path.cwd() / rel,
        Path(__file__).resolve().parent.parent / rel,
    ]
    for path in candidates:
        if path.exists():
            return str(path.resolve())
    return None


def _resolve_dataset_path(dataset_key: str) -> str:
    if dataset_key in ("full_3091", "benchmark", "full"):
        full_path = _find_full_eval_set()
        if not full_path:
            raise ValueError(
                "Full 3,091-group benchmark file not found in data/metamorphic_group/processed_mgs_core/."
            )
        return full_path
    return DEMO_MGS_PATH


def _parse_source_cases(
    text: str,
    translator: Optional[FOLTranslator] = None,
    extractor: Optional[UnstructuredExtractor] = None,
) -> List[TestCase]:
    """Parse user custom inputs of any supported form into ``TestCase`` objects.

    The backend sniffs the format automatically (JSONL vs plain text vs FOL
    blocks) — no ``input_mode`` needed.
    """
    from lgmt.core.builder import parse_and_normalize_cases

    return parse_and_normalize_cases(text, translator=translator, extractor=extractor)


# --------------------------------------------------------------------- #
# core execution workflows (with per-tab state isolation)
# --------------------------------------------------------------------- #
def execute_demo_workflow(
    persona: str = "flawed",
    prompting: str = "zero_cot",
    dataset: str = "demo_40",
) -> Dict[str, Any]:
    """Run Workflow 1: Offline Demo with MockLLMClient."""
    if prompting not in PROMPTING_PRESETS:
        prompting = "zero_cot"
    mgs_path = _resolve_dataset_path(dataset)
    mgs = load_metamorphic_groups(mgs_path)

    out_dir = _new_run_dir()
    results_path = os.path.join(out_dir, "results.jsonl")
    report_path = os.path.join(out_dir, "report.html")

    model_name = f"mock-{persona}"
    _begin_progress("demo", len(mgs), results_path)
    try:
        run_inference(
            mgs,
            MockLLMClient(persona=persona),
            model_name,
            prompting=prompting,
            result_save_path=results_path,
            max_workers=8,
            quiet=True,
            progress_callback=_progress_callback("demo"),
        )
    finally:
        _finish_progress("demo", 0)
    records = load_inference_records(results_path)
    _finish_progress("demo", compute_metrics(records).get("failed", 0))
    metrics = compute_metrics(records)
    generate_run_report(
        records,
        metrics,
        report_path,
        mgs=mgs,
        title="LGMT Offline Demo Report",
        model=model_name,
        prompting=prompting,
    )
    body_html = render_report_body(
        records, metrics, mgs=mgs, model=model_name, prompting=prompting
    )
    summary = (
        f"Offline Demo completed: {len(records)} groups ({dataset}) · "
        f"model={model_name} · prompting={prompting} · "
        f"MVR={metrics['mvr'] * 100:.2f}% ({metrics['violation_count']} violations)"
    )
    state = {
        "records": records,
        "metrics": metrics,
        "report": report_path,
        "body_html": body_html,
        "summary": summary,
        "kind": f"offline demo ({persona})",
    }
    RUNS_BY_TAB["demo"] = state
    LAST_RUN.update(state)
    return state


def execute_benchmark_workflow(
    api_key: str,
    base_url: str,
    model: str,
    dataset: str = "demo_40",
    prompting: str = "zero_cot",
    workers: int = 16,
) -> Dict[str, Any]:
    """Run Workflow 2: Benchmark an OpenAI-compatible model on bundled MGs."""
    if not api_key or not api_key.strip():
        raise ValueError(
            "Please provide an API key to evaluate a real model (kept in memory only). "
            "For a key-free run, use Tab 1: Quick Demo (Offline)."
        )
    if not model or not model.strip():
        raise ValueError("Please provide a model name (e.g. gpt-4o, claude-sonnet, deepseek-chat).")
    base_url = (base_url or "").strip() or "https://api.openai.com/v1"
    if prompting not in PROMPTING_PRESETS:
        prompting = "zero_cot"

    mgs_path = _resolve_dataset_path(dataset)
    mgs = load_metamorphic_groups(mgs_path)

    out_dir = _new_run_dir()
    results_path = os.path.join(out_dir, "results.jsonl")
    report_path = os.path.join(out_dir, "report.html")

    client = OpenAICompatClient(api_key=api_key.strip(), base_url=base_url)
    model_name = model.strip()
    _begin_progress("benchmark", len(mgs), results_path)
    try:
        run_inference(
            mgs,
            client,
            model_name,
            prompting=prompting,
            result_save_path=results_path,
            max_workers=max(1, min(64, int(workers or 32))),
            quiet=True,
            progress_callback=_progress_callback("benchmark"),
        )
    finally:
        _finish_progress("benchmark", 0)
    records = load_inference_records(results_path)
    _bench_failed = compute_metrics(records).get("failed", 0)
    _finish_progress("benchmark", _bench_failed)
    metrics = compute_metrics(records)

    # Keep a small in-memory history per (dataset, prompting) so repeated
    # benchmark runs of different models rank against each other. Only
    # aggregate metrics + model names are retained (never raw records),
    # and history is capped to avoid unbounded growth.
    bench_key = (dataset, prompting)
    history = _BENCH_HISTORY.setdefault(
        bench_key, deque(maxlen=_BENCH_HISTORY_MAX)
    )
    prev = RUNS_BY_TAB.get("benchmark")
    if prev and prev.get("_bench_key") == bench_key:
        history.append({"model": prev["model_name"], "metrics": prev["metrics"]})
    history.append({"model": model_name, "metrics": metrics})
    extra_runs = [{"model": h["model"], "metrics": h["metrics"]} for h in history]

    generate_run_report(
        records,
        metrics,
        report_path,
        mgs=mgs,
        title=f"LGMT Benchmark Report — {model_name}",
        model=model_name,
        prompting=prompting,
        extra_runs=extra_runs,
    )
    body_html = render_report_body(
        records,
        metrics,
        mgs=mgs,
        model=model_name,
        prompting=prompting,
        extra_runs=extra_runs,
    )
    summary = (
        f"Benchmark run completed: {len(records)} groups ({dataset}) · "
        f"model={model_name} · prompting={prompting} · "
        f"MVR={metrics['mvr'] * 100:.2f}% ({metrics['violation_count']} violations)"
    )
    state = {
        "records": records,
        "metrics": metrics,
        "report": report_path,
        "body_html": body_html,
        "summary": summary,
        "kind": f"benchmark ({model_name})",
        "model_name": model_name,
        "_bench_key": bench_key,
    }
    RUNS_BY_TAB["benchmark"] = state
    LAST_RUN.update(state)
    return state


def execute_custom_workflow(
    api_key: str,
    base_url: str,
    model: str,
    cases_jsonl: str,
    categories: List[str],
    prompting: str = "zero_cot",
    realize: bool = False,
    use_mock: bool = False,
    mock_persona: str = "flawed",
) -> Dict[str, Any]:
    """Run Workflow 3: sniff & normalize custom cases, build MGs, and test."""
    if not categories:
        raise ValueError("Select at least one MR category (E, S, P, C).")
    wanted = {c.upper() for c in categories}
    selected = [
        mr
        for mr in ALL_MRS
        if mr.index.upper() in wanted or mr.index.split("-")[1][0].upper() in wanted
    ]
    if not selected:
        raise ValueError("No MRs matched the selected categories.")

    if use_mock:
        client = MockLLMClient(persona=mock_persona)
        model_name = f"mock-{mock_persona}"
        translator = None
        extractor = None
    else:
        if not api_key or not api_key.strip():
            raise ValueError(
                "Please provide an API key (kept in memory only), or switch Execution Mode to "
                "'Offline Mock' (supported when FOL formulas are provided)."
            )
        if not model or not model.strip():
            raise ValueError("Please provide a model name (e.g. gpt-4o).")
        base_url = (base_url or "").strip() or "https://api.openai.com/v1"
        model_name = model.strip()
        client = OpenAICompatClient(api_key=api_key.strip(), base_url=base_url)
        translator = make_nl2fol_translator(client, model_name)
        extractor = make_unstructured_extractor(client, model_name)

    cases = _parse_source_cases(
        cases_jsonl, translator=translator, extractor=extractor
    )
    realize_fn = make_realize_fn(client, model_name) if (realize and not use_mock) else None

    mgs = build_metamorphic_groups(
        cases, mr_list=selected, max_per_case=1, seed=42, realize_fn=realize_fn
    )
    if not mgs:
        raise ValueError(
            "No metamorphic groups could be built from the given cases with the selected MR categories."
        )

    out_dir = _new_run_dir()
    results_path = os.path.join(out_dir, "results.jsonl")
    report_path = os.path.join(out_dir, "report.html")

    if prompting not in PROMPTING_PRESETS:
        prompting = "zero_cot"
    _begin_progress("custom", len(mgs), results_path)
    try:
        run_inference(
            mgs,
            client,
            model_name,
            prompting=prompting,
            result_save_path=results_path,
            max_workers=8,
            quiet=True,
            progress_callback=_progress_callback("custom"),
        )
    finally:
        _finish_progress("custom", 0)
    records = load_inference_records(results_path)
    metrics = compute_metrics(records)
    _finish_progress("custom", metrics.get("failed", 0))
    generate_run_report(
        records,
        metrics,
        report_path,
        mgs=mgs,
        title=f"LGMT Custom Evaluation Report — {model_name}",
        model=model_name,
        prompting=prompting,
    )
    body_html = render_report_body(
        records, metrics, mgs=mgs, model=model_name, prompting=prompting
    )
    summary = (
        f"Custom run completed: {len(records)} MGs built from {len(cases)} source case(s) · "
        f"model={model_name} · prompting={prompting} · "
        f"MVR={metrics['mvr'] * 100:.2f}% ({metrics['violation_count']} violations)"
    )
    state = {
        "records": records,
        "metrics": metrics,
        "report": report_path,
        "body_html": body_html,
        "summary": summary,
        "kind": f"custom ({model_name})",
    }
    RUNS_BY_TAB["custom"] = state
    LAST_RUN.update(state)
    return state


# --------------------------------------------------------------------- #
# Legacy/Gradio helper wrappers (backward-compatible signatures)
# --------------------------------------------------------------------- #
def _metrics_rows(metrics: Dict[str, Any]) -> List[List[Any]]:
    header = ["scope", "total", "MVR", "acc_src", "acc_cons", "HDR", "FUR"]
    rows = [
        header,
        [
            "ALL",
            metrics["total"],
            f"{metrics['mvr'] * 100:.2f}%",
            f"{metrics['acc_static'] * 100:.2f}%",
            f"{metrics['acc_cons'] * 100:.2f}%",
            f"{metrics['hdr'] * 100:.2f}%",
            f"{metrics['fur'] * 100:.2f}%",
        ],
    ]
    for row in metrics.get("per_category", []):
        rows.append(
            [
                f"category {row['key']}",
                row["total"],
                f"{row['mvr'] * 100:.2f}%",
                f"{row['acc_static'] * 100:.2f}%",
                f"{row['acc_cons'] * 100:.2f}%",
                f"{row['hdr'] * 100:.2f}%",
                f"{row['fur'] * 100:.2f}%",
            ]
        )
    return rows


def _violation_rows(records: List[Dict[str, Any]]) -> List[List[str]]:
    rows = [["mg_id", "mr", "ground truth", "source verdict", "follow-up verdict"]]
    for r in records:
        if r.get("is_consistent"):
            continue
        src = (r.get("source_response") or {}).get("response_label", "?")
        fol = (r.get("followup_response") or {}).get("response_label", "?")
        rows.append(
            [str(r.get("mg_id", "")), str(r.get("mr_index", "")), str(r.get("ground_truth", "")), src, fol]
        )
    if len(rows) == 1:
        rows.append(["(no violations)", "", "", "", ""])
    return rows


def _report_iframe(report_path: str) -> str:
    with open(report_path, "r", encoding="utf-8") as f:
        content = f.read()
    return (
        f'<iframe srcdoc="{html.escape(content, quote=True)}" '
        'style="width:100%;height:820px;border:1px solid #e2e8f0;border-radius:10px;"></iframe>'
    )


def run_offline_demo(persona: str = "flawed", prompting: str = "zero_cot"):
    state = execute_demo_workflow(persona=persona, prompting=prompting, dataset="demo_40")
    return (
        _metrics_rows(state["metrics"]),
        _violation_rows(state["records"]),
        _report_iframe(state["report"]),
        state["summary"] + "\n\n" + format_metrics_table(state["metrics"]),
    )


def run_user_model(
    api_key: str,
    base_url: str,
    model: str,
    cases_jsonl: str,
    categories: List[str],
    prompting: str,
    realize: bool,
):
    empty = [["scope", "total", "MVR", "acc_src", "acc_cons", "HDR", "FUR"]]
    no_violations = [["mg_id", "mr", "ground truth", "source verdict", "follow-up verdict"]]
    try:
        state = execute_custom_workflow(
            api_key=api_key,
            base_url=base_url,
            model=model,
            cases_jsonl=cases_jsonl,
            categories=categories,
            prompting=prompting,
            realize=realize,
            use_mock=False,
        )
    except ValueError as e:
        return empty, [no_violations[0] + [""]], "", f"Input error: {e}"
    return (
        _metrics_rows(state["metrics"]),
        _violation_rows(state["records"]),
        _report_iframe(state["report"]),
        state["summary"] + "\n\n" + format_metrics_table(state["metrics"]),
    )


# --------------------------------------------------------------------- #
# Zero-Dependency Native Web Studio (HTML + CSS + Raw JS)
# --------------------------------------------------------------------- #
_STUDIO_CSS = """
    .studio-banner { background: linear-gradient(135deg, #17273f 0%, #243b5e 100%); color: #fff; padding: 22px 0 0; border-bottom: 1px solid #1e3250; }
    .studio-inner { max-width: 1220px; margin: 0 auto; padding: 0 20px; }
    .studio-top { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; padding-bottom: 16px; }
    .studio-brand h1 { color: #fff; font-size: 23px; margin: 0; font-weight: 750; letter-spacing: -0.3px; }
    .studio-brand p { color: #b9c8dc; font-size: 13.5px; margin: 4px 0 0; }
    .studio-badges { display: flex; gap: 8px; flex-wrap: wrap; }
    .studio-pill { background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.2); color: #eef4fb; font-size: 11.5px; padding: 4px 10px; border-radius: 999px; font-weight: 600; }

    /* workflow tabs */
    .wf-tabs { display: flex; gap: 6px; margin-top: 4px; overflow-x: auto; }
    .wf-tab { background: rgba(255,255,255,0.08); color: #c7d4e6; border: 1px solid rgba(255,255,255,0.12); border-bottom: none; padding: 11px 18px; border-radius: 10px 10px 0 0; font-size: 13.5px; font-weight: 600; cursor: pointer; transition: all 0.15s ease; display: flex; align-items: center; gap: 8px; }
    .wf-tab:hover { background: rgba(255,255,255,0.15); color: #fff; }
    .wf-tab.active { background: #f2f4f8; color: #17273f; border-color: #f2f4f8; }
    .wf-step { display: inline-flex; width: 20px; height: 20px; border-radius: 50%; background: rgba(255,255,255,0.18); color: #fff; font-size: 11.5px; align-items: center; justify-content: center; font-weight: 700; }
    .wf-tab.active .wf-step { background: #3a6ea5; color: #fff; }

    /* control panels */
    .wf-panel { display: none; background: #fff; border-radius: 12px; padding: 18px 22px; margin-bottom: 18px; border: 1px solid #dce3ec; box-shadow: 0 2px 5px rgba(16,24,40,0.05); }
    .wf-panel.active { display: block; }
    .wf-guide { background: #f4f8fc; border-left: 4px solid #3a6ea5; padding: 10px 14px; border-radius: 0 8px 8px 0; font-size: 13px; color: #2b3a4f; margin-bottom: 14px; }
    .wf-guide b { color: #17273f; }
    .wf-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(195px, 1fr)); gap: 12px; align-items: end; }
    .wf-field { display: flex; flex-direction: column; gap: 5px; }
    .wf-field label { font-size: 11.5px; font-weight: 650; color: #4b5563; text-transform: uppercase; letter-spacing: 0.3px; }
    .wf-field input[type="text"], .wf-field input[type="password"], .wf-field input[type="number"], .wf-field select, .wf-field textarea {
        padding: 8px 11px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 13.5px; font-family: inherit; background: #fff; color: #1f2937;
    }
    .wf-field textarea { font-family: "SFMono-Regular", Consolas, Menlo, monospace; font-size: 12.5px; line-height: 1.45; resize: vertical; }
    .wf-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-top: 14px; padding-top: 12px; border-top: 1px solid #eef1f5; }
    .btn-primary { background: #3a6ea5; color: #fff; border: none; padding: 9px 20px; border-radius: 8px; font-size: 13.5px; font-weight: 650; cursor: pointer; transition: background 0.15s ease; }
    .btn-primary:hover { background: #2d5988; }
    .btn-primary:disabled { background: #94a3b8; cursor: wait; }
    .btn-secondary { background: #f1f5f9; color: #334155; border: 1px solid #cbd5e1; padding: 5px 11px; border-radius: 7px; font-size: 12px; font-weight: 600; cursor: pointer; }
    .btn-secondary:hover { background: #e2e8f0; }
    .chk-row { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; padding: 6px 0; }
    .chk-row label { font-size: 13px; color: #374151; font-weight: 500; text-transform: none; display: inline-flex; align-items: center; gap: 5px; cursor: pointer; }

    /* Sub-tabs inside Tab 3 (Custom Case Input Modes) */
    .sub-tabs { display: inline-flex; background: #f1f5f9; padding: 4px; border-radius: 9px; border: 1px solid #e2e8f0; margin-bottom: 12px; gap: 4px; flex-wrap: wrap; }
    .sub-tab { border: none; background: transparent; color: #475569; padding: 7px 14px; border-radius: 6px; font-size: 12.5px; font-weight: 600; cursor: pointer; transition: all 0.12s ease; }
    .sub-tab:hover { color: #1e293b; }
    .sub-tab.active { background: #fff; color: #17273f; box-shadow: 0 1px 2px rgba(16,24,40,0.08); }
    .sub-pane { display: none; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px 16px; }
    .sub-pane.active { display: block; }
    .sub-hint { font-size: 12.5px; color: #475569; margin: 0 0 10px; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px; }

    /* Quick Form Queue */
    .form-split { display: grid; grid-template-columns: 1.4fr 1fr; gap: 12px; }
    @media (max-width: 760px) { .form-split { grid-template-columns: 1fr; } }
    .queue-box { margin-top: 10px; background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px 12px; }
    .queue-header { display: flex; justify-content: space-between; align-items: center; font-size: 12px; font-weight: 600; color: #475569; margin-bottom: 6px; }
    .queue-item { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 5px 8px; background: #f8fafc; border-radius: 6px; font-size: 12px; color: #1e293b; margin-bottom: 4px; border-left: 3px solid #3a6ea5; }
    .queue-item button { border: none; background: none; color: #b91c1c; cursor: pointer; font-size: 11.5px; font-weight: 600; }

    .mr-status { font-size: 12.5px; color: #475569; }
    .mr-status.ok { color: #15803d; font-weight: 650; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 6px 12px; }
    .mr-status.error { color: #b91c1c; font-weight: 600; background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 6px 12px; }

    /* run progress */
    .run-progress { display: none; margin-top: 12px; align-items: center; gap: 12px; }
    .run-progress.active { display: flex; }
    .rp-track { flex: 1; height: 10px; background: #e8edf3; border-radius: 6px; overflow: hidden; }
    .rp-fill { height: 100%; width: 0%; background: linear-gradient(90deg, #3a6ea5, #6f9fd0); border-radius: 6px; transition: width 0.4s ease; }
    .rp-text { font-size: 12.5px; color: #475569; white-space: nowrap; font-variant-numeric: tabular-nums; }
    .rp-text b { color: #17273f; }

    /* status bar & empty state */
    .status-bar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px; background: #eaf1f9; border: 1px solid #c5d9ed; color: #17273f; padding: 10px 16px; border-radius: 10px; margin-bottom: 18px; font-size: 13.5px; font-weight: 500; }
    .status-bar.error { background: #fef2f2; border-color: #fecaca; color: #991b1b; }
    .status-bar a.dl-btn { background: #fff; color: #2d5988; border: 1px solid #b6cde6; padding: 5px 12px; border-radius: 6px; font-size: 12px; font-weight: 600; text-decoration: none; }
    .status-bar a.dl-btn:hover { background: #f0f6fc; }
    .empty-state { background: #fff; border: 1px dashed #cbd5e1; border-radius: 12px; padding: 44px 24px; text-align: center; color: #64748b; }
    .empty-state h3 { margin: 0 0 6px; font-size: 16px; color: #1e293b; }
    .empty-state p { margin: 0 auto; max-width: 580px; font-size: 13.5px; line-height: 1.5; }
"""

# Raw string for Studio JS so backslashes (\n, \r) are never corrupted by Python string escaping!
_STUDIO_JS = r"""
var PRESETS = {};
try { PRESETS = JSON.parse(document.getElementById('lgmt-presets').textContent); } catch (e) { PRESETS = {}; }

var activeTab = 1;

function emptyCardHtml(title, desc){
  return '<div class="empty-state"><h3>' + title + '</h3><p>' + desc + '</p></div>';
}

// Strictly isolated state for each of the 3 workflow tabs
var TAB_STATE = {
  1: {
    tabKey: 'demo',
    hasRun: false,
    isError: false,
    summary: 'Ready — click Run Offline Demo above to execute the offline pipeline.',
    html: emptyCardHtml(
      'No Offline Demo Run Yet',
      'Click <b>Run Offline Demo</b> above to run the built-in mock model on the 40-group subset (or full 3,091-group benchmark) and inspect the interactive leaderboard and violation cards.'
    )
  },
  2: {
    tabKey: 'benchmark',
    hasRun: false,
    isError: false,
    summary: 'Ready — configure your API key and model name above, then click Run Benchmark Evaluation.',
    html: emptyCardHtml(
      'No Model Benchmark Run Yet',
      'Enter an OpenAI-compatible API key and model name in Workflow 2 above and click <b>Run Benchmark Evaluation</b> to rank your model against 6 reference SOTA LLMs.'
    )
  },
  3: {
    tabKey: 'custom',
    hasRun: false,
    isError: false,
    summary: 'Ready — paste your test cases above and click Build MGs & Test Model.',
    html: emptyCardHtml(
      'No Custom Cases Evaluated Yet',
      'Paste your own cases (plain text, 中文, FOL, or JSONL) in Workflow 3 above and click <b>Build MGs &amp; Test Model</b>. Results appear strictly in this tab.'
    )
  }
};

function renderActiveTabState(){
  var st = TAB_STATE[activeTab];
  var bar = document.getElementById('status-bar');
  var txt = document.getElementById('status-text');
  var dlBtn = document.getElementById('dl-report-btn');
  var host = document.getElementById('report-host');

  bar.classList.toggle('error', !!st.isError);
  txt.textContent = st.summary;
  if (st.hasRun) {
    dlBtn.style.display = 'inline-block';
    dlBtn.href = '/api/download-report?tab=' + st.tabKey;
  } else {
    dlBtn.style.display = 'none';
  }
  host.innerHTML = st.html;
  if (st.hasRun) {
    initLgmtReport();
  }
}

function switchTab(idx){
  var prev = activeTab;
  activeTab = idx;
  if (prev !== idx && (idx === 2 || idx === 3) && (prev === 2 || prev === 3)) {
    syncModelConfig(prev);
  }
  [1, 2, 3].forEach(function(i){
    document.getElementById('tab-btn-' + i).classList.toggle('active', i === idx);
    document.getElementById('wf-panel-' + i).classList.toggle('active', i === idx);
  });
  renderActiveTabState();
}

// ---------------- Tab 3 Sub-Mode & Quick Form Queue ----------------
// ---------------- Tab 3: smart input, model sync, custom-MR drawer ----------------
var CUSTOM_MRS = [];

function fillExample(key){
  var map = {
    'plain_en': 'EX_PRESET_PLAIN_EN',
    'plain_zh': 'EX_PRESET_PLAIN_ZH',
    'jsonl': 'EX_PRESET_JSONL'
  };
  var preset = (PRESETS[map[key]] || '');
  if (preset) document.getElementById('c-cases').value = preset;
}

// Keep Tab 2 and Tab 3 model configuration in sync (both directions).
function syncModelConfig(source){
  var pairs = [
    ['b-key', 'c-key'], ['b-url', 'c-url'],
    ['b-model', 'c-model'], ['b-prompting', 'c-prompting']
  ];
  pairs.forEach(function(pr){
    var from = (source === 2) ? pr[0] : pr[1];
    var to = (source === 2) ? pr[1] : pr[0];
    var el = document.getElementById(to);
    if (el) el.value = document.getElementById(from).value;
  });
}

function toggleMrDrawer(){
  var d = document.getElementById('mr-drawer');
  d.style.display = (d.style.display === 'none') ? 'block' : 'none';
}

function registerCustomMr(){
  var status = document.getElementById('mr-status');
  var code = document.getElementById('mr-code').value || '';
  status.className = 'mr-status';
  status.textContent = 'Verifying with Z3…';
  fetch('/api/register-mr', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({code: code})
  })
  .then(function(r){ return r.json().then(function(d){ return {ok: r.ok, data: d}; }); })
  .then(function(res){
    if (!res.ok || res.data.error) {
      status.className = 'mr-status error';
      status.textContent = '✗ ' + (res.data.error || 'Registration failed.');
      return;
    }
    var info = res.data.registered[0];
    CUSTOM_MRS.push(info.index);
    var box = document.getElementById('custom-mr-checks');
    var lab = document.createElement('label');
    lab.innerHTML = '<input type="checkbox" class="c-cat c-custom" value="' +
      info.index + '" checked> ' + info.index + ' (Custom)';
    box.appendChild(lab);
    status.className = 'mr-status ok';
    status.textContent = '✓ Z3 Equivalence Verified (' + info.verified_count + '/' +
      info.tested + ' test formulas) · Registered ' + info.index + ': ' + info.name;
  })
  .catch(function(err){
    status.className = 'mr-status error';
    status.textContent = '✗ Request error: ' + err;
  });
}

function loadJsonlPreset(key){
  var el = document.getElementById('c-cases');
  if (el) el.value = PRESETS[key] || PRESETS.dual_fol;
}

function handleFileUpload(input){
  if (!input.files || !input.files[0]) return;
  var reader = new FileReader();
  reader.onload = function(e){
    document.getElementById('c-cases').value = e.target.result || '';
  };
  reader.readAsText(input.files[0], 'UTF-8');
}

// ---------------- Run Progress (1s polling of /api/progress) ----------------
var progressTimers = {};

function startProgress(tabIdx, tabKey){
  stopProgress(tabIdx);
  var host = document.getElementById('progress-' + tabIdx);
  if (!host) return;
  host.classList.add('active');
  updateProgressView(tabIdx, {completed: 0, total: 0, failed: 0, done: false});
  progressTimers[tabIdx] = setInterval(function(){
    fetch('/api/progress?tab=' + tabKey)
      .then(function(r){ return r.json(); })
      .then(function(d){ updateProgressView(tabIdx, d); })
      .catch(function(){ /* transient poll failure: keep trying */ });
  }, 1000);
}

function stopProgress(tabIdx){
  if (progressTimers[tabIdx]) {
    clearInterval(progressTimers[tabIdx]);
    delete progressTimers[tabIdx];
  }
  var host = document.getElementById('progress-' + tabIdx);
  if (host) host.classList.remove('active');
}

function updateProgressView(tabIdx, d){
  var fill = document.getElementById('rp-fill-' + tabIdx);
  var text = document.getElementById('rp-text-' + tabIdx);
  if (!fill || !text) return;
  var total = d.total || 0;
  var completed = d.completed || 0;
  var pct = total ? Math.round(completed / total * 100) : 0;
  fill.style.width = pct + '%';
  text.innerHTML = total
    ? '<b>' + completed + '</b>/' + total + ' (' + pct + '%)' +
      (d.failed ? ' · <span style="color:#b91c1c;">' + d.failed + ' failed</span>' : '')
    : 'Preparing run…';
}

// ---------------- API Dispatch (Strictly Scoped to Tab) ----------------
function postTabApi(tabIdx, url, payload, btnId){
  var btn = document.getElementById(btnId);
  var oldLabel = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Running…';
  TAB_STATE[tabIdx].isError = false;
  TAB_STATE[tabIdx].summary = 'Running pipeline… please wait.';
  if (activeTab === tabIdx) renderActiveTabState();
  startProgress(tabIdx, TAB_STATE[tabIdx].tabKey);

  fetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  })
  .then(function(r){ return r.json().then(function(d){ return {ok: r.ok, data: d}; }); })
  .then(function(res){
    stopProgress(tabIdx);
    btn.disabled = false;
    btn.textContent = oldLabel;
    if (!res.ok || res.data.error) {
      TAB_STATE[tabIdx].isError = true;
      TAB_STATE[tabIdx].summary = res.data.error || 'Run failed.';
      if (activeTab === tabIdx) renderActiveTabState();
      return;
    }
    TAB_STATE[tabIdx].isError = false;
    TAB_STATE[tabIdx].hasRun = true;
    TAB_STATE[tabIdx].summary = res.data.summary;
    TAB_STATE[tabIdx].html = res.data.body_html;
    if (activeTab === tabIdx) renderActiveTabState();
  })
  .catch(function(err){
    stopProgress(tabIdx);
    btn.disabled = false;
    btn.textContent = oldLabel;
    TAB_STATE[tabIdx].isError = true;
    TAB_STATE[tabIdx].summary = 'Request error: ' + err;
    if (activeTab === tabIdx) renderActiveTabState();
  });
}

function runDemo(){
  postTabApi(1, '/api/demo', {
    persona: document.getElementById('d-persona').value,
    dataset: document.getElementById('d-dataset').value,
    prompting: document.getElementById('d-prompting').value
  }, 'btn-run-demo');
}

function runBenchmark(){
  postTabApi(2, '/api/benchmark', {
    api_key: document.getElementById('b-key').value,
    base_url: document.getElementById('b-url').value,
    model: document.getElementById('b-model').value,
    dataset: document.getElementById('b-dataset').value,
    prompting: document.getElementById('b-prompting').value,
    workers: parseInt(document.getElementById('b-workers').value || '32', 10)
  }, 'btn-run-bench');
}

function runCustom(){
  var cats = [];
  document.querySelectorAll('.c-cat:checked').forEach(function(el){ cats.push(el.value); });
  var payloadText = (document.getElementById('c-cases').value || '').trim();
  if (!payloadText) {
    TAB_STATE[3].isError = true;
    TAB_STATE[3].summary = 'Please paste your test cases (plain text, 中文, FOL, or JSONL).';
    renderActiveTabState();
    return;
  }
  postTabApi(3, '/api/custom', {
    api_key: document.getElementById('c-key').value,
    base_url: document.getElementById('c-url').value,
    model: document.getElementById('c-model').value,
    prompting: document.getElementById('c-prompting').value,
    categories: cats,
    realize: true,
    use_mock: false,
    cases_jsonl: payloadText
  }, 'btn-run-custom');
}

window.addEventListener('DOMContentLoaded', function(){
  renderActiveTabState();
});
"""


def _render_studio_page() -> str:
    presets_json = json.dumps(
        {
            "nl_en": EXAMPLE_NL_EN_JSONL,
            "nl_zh": EXAMPLE_NL_ZH_JSONL,
            "pure_fol": EXAMPLE_PURE_FOL_JSONL,
            "dual_fol": EXAMPLE_FOL_JSONL,
            "EX_PRESET_PLAIN_EN": EXAMPLE_PLAINTEXT_EN,
            "EX_PRESET_PLAIN_ZH": EXAMPLE_PLAINTEXT_ZH,
            "EX_PRESET_JSONL": EXAMPLE_FOL_JSONL,
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LGMT Web Studio — Logic-Grounded Metamorphic Testing</title>
    <style>{REPORT_CSS}\n{_STUDIO_CSS}</style>
</head>
<body>
    <header class="studio-banner">
        <div class="studio-inner">
            <div class="studio-top">
                <div class="studio-brand">
                    <h1>LGMT — Logic-Grounded Metamorphic Testing Studio</h1>
                    <p>Rewrite logical reasoning problems into provably equivalent FOL variants, query any LLM, and audit self-contradictions.</p>
                </div>
                <div class="studio-badges">
                    <span class="studio-pill">20 FOL Metamorphic Relations</span>
                    <span class="studio-pill">Z3-Verified AST Rewriting</span>
                    <span class="studio-pill">3,091-Group Benchmark</span>
                </div>
            </div>
            <nav class="wf-tabs">
                <button class="wf-tab active" onclick="switchTab(1)" id="tab-btn-1">
                    <span class="wf-step">1</span> Quick Demo (Offline)
                </button>
                <button class="wf-tab" onclick="switchTab(2)" id="tab-btn-2">
                    <span class="wf-step">2</span> Benchmark Your Model
                </button>
                <button class="wf-tab" onclick="switchTab(3)" id="tab-btn-3">
                    <span class="wf-step">3</span> Test Custom Cases
                </button>
            </nav>
        </div>
    </header>

    <div class="container" style="padding-top: 20px;">
        <!-- ==================== Workflow 1: Offline Demo ==================== -->
        <section class="wf-panel active" id="wf-panel-1">
            <div class="wf-guide">
                <b>Workflow 1 · Zero-Configuration Offline Tour:</b> No API key or network needed. Runs LGMT's built-in deterministic mock model (<i>flawed</i> intentionally contradicts itself on equivalence &amp; premise transformations; <i>consistent</i> is invariant) and ranks it against 6 reference SOTA LLMs.
            </div>
            <div class="wf-grid">
                <div class="wf-field">
                    <label>Mock Persona</label>
                    <select id="d-persona">
                        <option value="flawed" selected>flawed (simulates reasoning defects)</option>
                        <option value="consistent">consistent (0% violation baseline)</option>
                    </select>
                </div>
                <div class="wf-field">
                    <label>Bundled Dataset</label>
                    <select id="d-dataset">
                        <option value="demo_40" selected>Demo subset (40 FOLIO groups · instant)</option>
                        <option value="full_3091">Full benchmark (3,091 groups · ~2s)</option>
                    </select>
                </div>
                <div class="wf-field">
                    <label>Prompting Strategy</label>
                    <select id="d-prompting">
                        <option value="zero_direct" selected>zero_direct (Zero-shot Direct)</option>
                        <option value="zero_cot">zero_cot (Zero-shot CoT · matches reference)</option>
                        <option value="few_cot">few_cot (Few-shot CoT)</option>
                        <option value="few_direct">few_direct (Few-shot Direct)</option>
                    </select>
                </div>
            </div>
            <div class="wf-actions">
                <button class="btn-primary" id="btn-run-demo" onclick="runDemo()">Run Offline Demo</button>
                <span style="font-size:12.5px;color:#6b7280;">CLI equivalent: <code>lgmt demo</code> or <code>lgmt demo --full</code></span>
            </div>
            <div class="run-progress" id="progress-1">
                <div class="rp-track"><div class="rp-fill" id="rp-fill-1"></div></div>
                <span class="rp-text" id="rp-text-1"></span>
            </div>
        </section>

        <!-- ==================== Workflow 2: Benchmark Your Model ==================== -->
        <section class="wf-panel" id="wf-panel-2">
            <div class="wf-guide">
                <b>Workflow 2 · Evaluate an LLM on the Bundled Benchmark:</b> Point LGMT at any OpenAI-compatible endpoint (commercial API or local vLLM / Ollama server). Your API key is held in memory for this request only and never stored.
            </div>
            <div class="wf-grid">
                <div class="wf-field">
                    <label>API Key (in-memory only)</label>
                    <input type="password" id="b-key" placeholder="sk-...">
                </div>
                <div class="wf-field">
                    <label>Base URL</label>
                    <input type="text" id="b-url" value="https://api.deepseek.com">
                </div>
                <div class="wf-field">
                    <label>Model Name</label>
                    <input type="text" id="b-model" value="deepseek-flash">
                </div>
                <div class="wf-field">
                    <label>Benchmark Scope</label>
                    <select id="b-dataset">
                        <option value="demo_40" selected>Demo subset (40 groups · 80 API calls)</option>
                        <option value="full_3091">Full benchmark (3,091 groups · 6,182 API calls)</option>
                    </select>
                </div>
                <div class="wf-field">
                    <label>Prompting Strategy</label>
                    <select id="b-prompting">
                        <option value="zero_direct" selected>zero_direct</option>
                        <option value="zero_cot">zero_cot (matches reference leaderboard)</option>
                        <option value="few_cot">few_cot</option>
                        <option value="few_direct">few_direct</option>
                    </select>
                </div>
                <div class="wf-field">
                    <label>Workers</label>
                    <input type="number" id="b-workers" value="32" min="1" max="64">
                </div>
            </div>
            <div class="wf-actions">
                <button class="btn-primary" id="btn-run-bench" onclick="runBenchmark()">Run Benchmark Evaluation</button>
                <span style="font-size:12.5px;color:#6b7280;">CLI equivalent: <code>lgmt run --mgs benchmark --model &lt;name&gt; --output results.jsonl</code></span>
            </div>
            <div class="run-progress" id="progress-2">
                <div class="rp-track"><div class="rp-fill" id="rp-fill-2"></div></div>
                <span class="rp-text" id="rp-text-2"></span>
            </div>
        </section>

        <!-- ==================== Workflow 3: Test Custom Cases ==================== -->
        <section class="wf-panel" id="wf-panel-3">
            <div class="wf-guide">
                <b>Workflow 3 · Test Your Own Domain Cases:</b> One test case = a few premise lines + one conclusion — English, 中文, or FOL are all accepted. No formulas and no gold labels needed: the LLM synthesizes the logic automatically and LGMT rewrites it into provably equivalent variants.
            </div>

            <div class="wf-grid">
                <div class="wf-field" id="c-key-wrap">
                    <label>API Key (in-memory only)</label>
                    <input type="password" id="c-key" placeholder="sk-...">
                </div>
                <div class="wf-field" id="c-url-wrap">
                    <label>Base URL</label>
                    <input type="text" id="c-url" value="https://api.deepseek.com">
                </div>
                <div class="wf-field" id="c-model-wrap">
                    <label>Model Name</label>
                    <input type="text" id="c-model" value="deepseek-flash">
                </div>
                <div class="wf-field">
                    <label>Prompting Strategy</label>
                    <select id="c-prompting">
                        <option value="zero_direct" selected>zero_direct</option>
                        <option value="zero_cot">zero_cot</option>
                        <option value="few_cot">few_cot</option>
                        <option value="few_direct">few_direct</option>
                    </select>
                </div>
            </div>

            <div style="margin-top:14px;">
                <div class="sub-hint">
                    <span><b>Test Cases</b> — paste plain text, Chinese/English sentences, FOL formulas, or JSONL. <b>No ground-truth labels needed.</b></span>
                    <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
                        <select class="btn-secondary" style="padding:5px 8px;" onchange="if(this.value){{fillExample(this.value);this.value='';}}">
                            <option value="">Load Example ▾</option>
                            <option value="plain_en">1. Plain Text — Medical &amp; Legal (English)</option>
                            <option value="plain_zh">2. 中文业务规则段落 (Chinese)</option>
                            <option value="jsonl">3. Structured JSONL (NL + FOL)</option>
                        </select>
                        <label class="btn-secondary" style="cursor:pointer;margin:0;">
                            📂 Upload File <input type="file" accept=".txt,.jsonl,.json" style="display:none;" onchange="handleFileUpload(this)">
                        </label>
                    </div>
                </div>
                <div class="wf-field">
                    <textarea id="c-cases" rows="6">{html.escape(EXAMPLE_PLAINTEXT_EN)}</textarea>
                </div>
            </div>

            <div class="chk-row" style="margin-top:12px;">
                <span style="font-size:12px;font-weight:700;color:#4b5563;text-transform:uppercase;">MR Categories:</span>
                <label><input type="checkbox" class="c-cat" value="E" checked> E (Formula &times;10)</label>
                <label><input type="checkbox" class="c-cat" value="S" checked> S (Symbol &times;2)</label>
                <label><input type="checkbox" class="c-cat" value="P" checked> P (Premise &times;5)</label>
                <label><input type="checkbox" class="c-cat" value="C" checked> C (Conclusion &times;3)</label>
                <span id="custom-mr-checks"></span>
                <button type="button" class="btn-secondary" onclick="toggleMrDrawer()">➕ Register Custom MR</button>
            </div>

            <div id="mr-drawer" style="display:none;margin-top:10px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:14px 16px;">
                <div style="font-size:12px;color:#92400e;background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:8px 12px;margin-bottom:10px;">
                    ⚠️ Executes Python locally — only paste code you trust. Every registered MR is verified for logical equivalence with Z3 before use.
                </div>
                <div class="wf-field">
                    <label>Custom Metamorphic Relation (subclass of MetamorphicRelation)</label>
                    <textarea id="mr-code" rows="15" style="font-size:12px;">{html.escape(LISTING1_CUSTOM_MR_TEMPLATE)}</textarea>
                </div>
                <div class="wf-actions" style="border-top:none;padding-top:10px;">
                    <button type="button" class="btn-primary" onclick="registerCustomMr()">Verify with Z3 &amp; Register</button>
                    <span class="mr-status" id="mr-status" style="font-size:12.5px;color:#475569;"></span>
                </div>
            </div>

            <div class="wf-actions">
                <button class="btn-primary" id="btn-run-custom" onclick="runCustom()">Build MGs &amp; Test Model</button>
                <span style="font-size:12.5px;color:#6b7280;">CLI equivalent: <code>lgmt build-mgs --input my_cases.jsonl --output my_mgs.jsonl</code> → <code>lgmt run</code></span>
            </div>
            <div class="run-progress" id="progress-3">
                <div class="rp-track"><div class="rp-fill" id="rp-fill-3"></div></div>
                <span class="rp-text" id="rp-text-3"></span>
            </div>
        </section>

        <!-- Per-Tab Isolated Status Bar & Report Host -->
        <div class="status-bar" id="status-bar">
            <span id="status-text">Ready — click Run Offline Demo above to start.</span>
            <a class="dl-btn" id="dl-report-btn" href="/api/download-report?tab=demo" target="_blank" style="display:none;">Download Standalone HTML Report</a>
        </div>

        <div id="report-host"></div>
    </div>

    <footer>
        LGMT · <a href="https://github.com/MaxwelsDonc/lgmt-tool">GitHub</a> ·
        Companion study: Knowledge-Based Systems (2026), in press ·
        Reference metrics: {html.escape(REFERENCE_SNAPSHOT)}
    </footer>

    <script type="application/json" id="lgmt-presets">{presets_json}</script>
    <script>{REPORT_JS}</script>
    <script>{_STUDIO_JS}</script>
</body>
</html>"""


class _StudioHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return  # keep console clean

    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_html(self, html_str: str, status: int = 200, filename: Optional[str] = None) -> None:
        raw = html_str.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._send_html(_render_studio_page())
            return
        if parsed.path == "/api/progress":
            qs = parse_qs(parsed.query)
            tab_key = (qs.get("tab") or [""])[0]
            self._send_json(_read_progress(tab_key))
            return
        if parsed.path == "/api/download-report":
            qs = parse_qs(parsed.query)
            tab_key = (qs.get("tab") or [""])[0]
            target = RUNS_BY_TAB.get(tab_key) or LAST_RUN
            if not target or not os.path.exists(target.get("report", "")):
                self.send_error(404, "No report has been generated for this tab yet. Run the workflow first.")
                return
            with open(target["report"], "r", encoding="utf-8") as f:
                self._send_html(f.read(), filename=f"lgmt_{tab_key or 'run'}_report.html")
            return
        self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            data = json.loads(body)
        except Exception:
            self._send_json({"error": "Invalid JSON request body."}, status=400)
            return

        try:
            if parsed.path == "/api/demo":
                state = execute_demo_workflow(
                    persona=data.get("persona", "flawed"),
                    prompting=data.get("prompting", "zero_cot"),
                    dataset=data.get("dataset", "demo_40"),
                )
            elif parsed.path == "/api/benchmark":
                state = execute_benchmark_workflow(
                    api_key=data.get("api_key", ""),
                    base_url=data.get("base_url", ""),
                    model=data.get("model", ""),
                    dataset=data.get("dataset", "demo_40"),
                    prompting=data.get("prompting", "zero_cot"),
                    workers=int(data.get("workers", 16)),
                )
            elif parsed.path == "/api/register-mr":
                code = data.get("code", "")
                if not code.strip():
                    self._send_json({"error": "Provide Python code defining a MetamorphicRelation subclass."}, status=400)
                    return
                from lgmt.mrs import load_mr_from_source

                registered = load_mr_from_source(code, verify_z3=True)
                self._send_json({
                    "registered": registered,
                    "trust_notice": "Executes Python locally — only paste code you trust.",
                })
                return
            elif parsed.path == "/api/custom":
                state = execute_custom_workflow(
                    api_key=data.get("api_key", ""),
                    base_url=data.get("base_url", ""),
                    model=data.get("model", ""),
                    cases_jsonl=data.get("cases_jsonl", ""),
                    categories=data.get("categories") or ["E", "S", "P", "C"],
                    prompting=data.get("prompting", "zero_cot"),
                    realize=bool(data.get("realize", True)),
                    use_mock=bool(data.get("use_mock", False)),
                )
            else:
                self._send_json({"error": f"Unknown endpoint {parsed.path}"}, status=404)
                return
            self._send_json({"summary": state["summary"], "body_html": state["body_html"]})
        except Exception as e:
            self._send_json({"error": str(e)}, status=400)


# --------------------------------------------------------------------- #
# Gradio app adapter (for Hugging Face Gradio Spaces compatibility)
# --------------------------------------------------------------------- #
def build_app():
    """Build the Gradio Blocks app (used by `spaces/app.py` or `--gradio`)."""
    try:
        import gradio as gr
    except ImportError as e:  # pragma: no cover
        raise SystemExit(
            "gradio is required for `--gradio` mode: pip install -r requirements-web.txt "
            "(or omit `--gradio` to run the zero-dependency built-in Web Studio)."
        ) from e

    prompting_choices = sorted(PROMPTING_PRESETS.keys())
    category_choices = ["E", "S", "P", "C"]

    def _gr_demo(persona: str, dataset: str, prompting: str):
        state = execute_demo_workflow(persona=persona, prompting=prompting, dataset=dataset)
        return state["summary"], _report_iframe(state["report"])

    def _gr_bench(api_key: str, base_url: str, model: str, dataset: str, prompting: str):
        try:
            state = execute_benchmark_workflow(
                api_key=api_key,
                base_url=base_url,
                model=model,
                dataset=dataset,
                prompting=prompting,
            )
            return state["summary"], _report_iframe(state["report"])
        except Exception as e:
            return f"Error: {e}", ""

    def _gr_custom(
        api_key: str,
        base_url: str,
        model: str,
        cases_text: str,
        categories: List[str],
        prompting: str,
        realize: bool,
        use_mock: bool,
    ):
        try:
            state = execute_custom_workflow(
                api_key=api_key,
                base_url=base_url,
                model=model,
                cases_jsonl=cases_text,
                categories=categories,
                prompting=prompting,
                realize=realize,
                use_mock=use_mock,
            )
            return state["summary"], _report_iframe(state["report"])
        except Exception as e:
            return f"Error: {e}", ""

    with gr.Blocks(title="LGMT — Logic-Grounded Metamorphic Testing") as app:
        gr.Markdown(
            "# LGMT — Logic-Grounded Metamorphic Testing Studio\n"
            "Choose a workflow tab below: **1. Quick Demo (Offline)** (no API key needed), "
            "**2. Benchmark Your Model** (on bundled 40 or 3,091 groups), or "
            "**3. Test Custom Cases** (supports pure natural language in English/中文, unstructured text, pure FOL, or dual NL+FOL)."
        )

        with gr.Tab("1. Quick Demo (Offline)"):
            with gr.Row():
                persona = gr.Dropdown(
                    choices=["flawed", "consistent"], value="flawed", label="Mock persona"
                )
                dataset1 = gr.Dropdown(
                    choices=["demo_40", "full_3091"], value="demo_40", label="Bundled dataset"
                )
                prompting1 = gr.Dropdown(
                    choices=prompting_choices, value="zero_cot", label="Prompting"
                )
            run_btn1 = gr.Button("Run Offline Demo", variant="primary")
            status1 = gr.Textbox(
                label="Run Summary",
                value="Ready — click 'Run Offline Demo' above to start.",
                interactive=False,
            )
            report1 = gr.HTML(label="Interactive Report")
            run_btn1.click(
                _gr_demo,
                inputs=[persona, dataset1, prompting1],
                outputs=[status1, report1],
            )

        with gr.Tab("2. Benchmark Your Model"):
            with gr.Row():
                api_key2 = gr.Textbox(label="API key (in-memory only)", type="password", placeholder="sk-...")
                base_url2 = gr.Textbox(label="Base URL", value="https://api.openai.com/v1")
                model2 = gr.Textbox(label="Model", placeholder="gpt-4o")
            with gr.Row():
                dataset2 = gr.Dropdown(
                    choices=["demo_40", "full_3091"], value="demo_40", label="Benchmark scope"
                )
                prompting2 = gr.Dropdown(
                    choices=prompting_choices, value="zero_cot", label="Prompting"
                )
            run_btn2 = gr.Button("Run Benchmark Evaluation", variant="primary")
            status2 = gr.Textbox(label="Run Summary", interactive=False)
            report2 = gr.HTML(label="Interactive Report")
            run_btn2.click(
                _gr_bench,
                inputs=[api_key2, base_url2, model2, dataset2, prompting2],
                outputs=[status2, report2],
            )

        with gr.Tab("3. Test Custom Cases"):
            with gr.Row():
                api_key3 = gr.Textbox(label="API key", type="password", placeholder="sk-...")
                base_url3 = gr.Textbox(label="Base URL", value="https://api.openai.com/v1")
                model3 = gr.Textbox(label="Model", placeholder="gpt-4o")
            with gr.Row():
                categories3 = gr.CheckboxGroup(
                    choices=category_choices, value=category_choices, label="MR categories"
                )
                prompting3 = gr.Dropdown(
                    choices=prompting_choices, value="zero_cot", label="Prompting"
                )
                realize3 = gr.Checkbox(value=True, label="LLM Logic→NL Realize")
                use_mock3 = gr.Checkbox(value=False, label="Offline Mock Mode (requires FOL)")
            cases_box3 = gr.Textbox(
                label="Source cases",
                value=EXAMPLE_NL_EN_JSONL,
                lines=6,
                max_lines=16,
            )
            run_btn3 = gr.Button("Build MGs & Test Model", variant="primary")
            status3 = gr.Textbox(label="Run Summary", interactive=False)
            report3 = gr.HTML(label="Interactive Report")
            run_btn3.click(
                _gr_custom,
                inputs=[api_key3, base_url3, model3, cases_box3, categories3, prompting3, realize3, use_mock3],
                outputs=[status3, report3],
            )

    return app


def launch_server(host: str = "0.0.0.0", port: int = 7860, use_gradio: bool = False) -> None:
    """Launch either the built-in zero-dependency Web Studio or the Gradio wrapper."""
    if use_gradio:
        build_app().launch(server_name=host, server_port=port)
        return

    server = ThreadingHTTPServer((host, port), _StudioHandler)
    display_host = "localhost" if host in ("0.0.0.0", "127.0.0.1") else host
    print(f"LGMT Web Studio running at http://{display_host}:{port} (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down LGMT Web Studio.")
    finally:
        server.server_close()


def main(argv: Optional[List[str]] = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="LGMT Interactive Web Studio")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument(
        "--gradio",
        action="store_true",
        help="Use the Gradio UI wrapper instead of the built-in zero-dependency Web Studio.",
    )
    args = parser.parse_args(argv)
    launch_server(host=args.host, port=args.port, use_gradio=args.gradio)


if __name__ == "__main__":
    main()
