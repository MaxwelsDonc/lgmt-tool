"""Gradio web demo for LGMT.

Three tabs:
    1. Try Demo     — one-click offline demo (mock model + bundled MGs)
    2. Test Your Model — bring your own OpenAI-compatible endpoint and key
    3. Browse Report   — details of the most recent run

Run locally:
    pip install -r requirements-web.txt
    python -m lgmt.webapp            # serves on http://0.0.0.0:7860

gradio is imported lazily so that importing this module (e.g. during
package discovery or testing) never requires the web extras.
"""
import html
import json
import os
import re
import tempfile
from typing import Any, Dict, List, Optional

from lgmt.core.builder import build_metamorphic_groups, make_realize_fn
from lgmt.core.runner import PROMPTING_PRESETS, run_inference
from lgmt.models import MockLLMClient
from lgmt.models.openai_compat import OpenAICompatClient
from lgmt.mrs import ALL_MRS
from lgmt.utils.io import (
    load_inference_records,
    load_metamorphic_groups,
    write_jsonl,
)
from lgmt.utils.labels import canonical_label
from lgmt.utils.metrics import compute_metrics, format_metrics_table
from lgmt.utils.report import generate_run_report

DEMO_MGS_PATH = os.path.join(os.path.dirname(__file__), "demo", "demo_mgs.jsonl")

EXAMPLE_JSONL = """\
{"premises_logic": ["all x.(Man(x) -> Mortal(x))", "Man(socrates)"],
 "conclusion_logic": "Mortal(socrates)",
 "premises_text": ["All men are mortal.", "Socrates is a man."],
 "conclusion_text": "Socrates is mortal.",
 "metadata": {"label": "True"}}
{"premises_logic": ["all x.(Manager(x) -> Office(x))", "Office(alice)"],
 "conclusion_logic": "Manager(alice)",
 "premises_text": ["All managers have a private office.", "Alice has a private office."],
 "conclusion_text": "Alice is a manager.",
 "metadata": {"label": "Unknown"}}
"""

#: In-memory state of the most recent run (never persisted).
LAST_RUN: Dict[str, Any] = {}


# --------------------------------------------------------------------- #
# shared pipeline helpers
# --------------------------------------------------------------------- #
def _new_run_dir() -> str:
    return tempfile.mkdtemp(prefix="lgmt_web_")


def _metrics_rows(metrics: Dict[str, Any]) -> List[List[Any]]:
    header = ["scope", "total", "MVR", "acc_src", "acc_cons", "HDR", "FUR"]
    rows = [header]
    rows.append(
        [
            "ALL",
            metrics["total"],
            f"{metrics['mvr'] * 100:.2f}%",
            f"{metrics['acc_static'] * 100:.2f}%",
            f"{metrics['acc_cons'] * 100:.2f}%",
            f"{metrics['hdr'] * 100:.2f}%",
            f"{metrics['fur'] * 100:.2f}%",
        ]
    )
    for row in metrics.get("per_category", []):
        rows.append(
            [
                f"category {row['key']}",
                row["total"],
                f"{row['mvr'] * 100:.2f}%",
                "",
                "",
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
        'style="width:100%;height:780px;border:1px solid #ddd;border-radius:6px;"></iframe>'
    )


# --------------------------------------------------------------------- #
# Tab 1: offline demo
# --------------------------------------------------------------------- #
def run_offline_demo(persona: str, prompting: str):
    """Run the bundled demo with a mock model; returns gr-update values."""
    out_dir = _new_run_dir()
    results_path = os.path.join(out_dir, "results.jsonl")
    report_path = os.path.join(out_dir, "report.html")

    mgs = load_metamorphic_groups(DEMO_MGS_PATH)
    run_inference(
        mgs,
        MockLLMClient(persona=persona),
        f"mock-{persona}",
        prompting=prompting,
        result_save_path=results_path,
        max_workers=8,
        quiet=True,
    )
    records = load_inference_records(results_path)
    metrics = compute_metrics(records)
    generate_run_report(
        records, metrics, report_path, mgs=mgs, title="LGMT Web Demo Report"
    )
    LAST_RUN.update(
        records=records, metrics=metrics, report=report_path, kind=f"offline demo ({persona})"
    )
    return (
        _metrics_rows(metrics),
        _violation_rows(records),
        _report_iframe(report_path),
        f"Run finished: {len(records)} groups | model=mock-{persona} | prompting={prompting}\n\n"
        + format_metrics_table(metrics),
    )


# --------------------------------------------------------------------- #
# Tab 2: test your own model
# --------------------------------------------------------------------- #
def _parse_source_cases(text: str):
    """Parse user-pasted JSONL into TestCase-like dicts."""
    from lgmt.core.structure import TestCase

    cases = []
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"line {lineno}: invalid JSON ({e})") from e
        premises_logic = obj.get("premises_logic")
        conclusion_logic = obj.get("conclusion_logic")
        if not premises_logic or not conclusion_logic:
            raise ValueError(
                f"line {lineno}: each record needs 'premises_logic' and 'conclusion_logic'"
            )
        cases.append(
            TestCase(
                premises_logic=list(premises_logic),
                conclusion_logic=conclusion_logic,
                premises_text=list(
                    obj.get("premises_text") or [p for p in premises_logic]
                ),
                conclusion_text=obj.get("conclusion_text") or conclusion_logic,
                metadata={"label": canonical_label((obj.get("metadata") or {}).get("label"))},
            )
        )
    if not cases:
        raise ValueError("no test cases found — paste one JSON object per line")
    return cases


def run_user_model(
    api_key: str,
    base_url: str,
    model: str,
    cases_jsonl: str,
    categories: List[str],
    prompting: str,
    realize: bool,
):
    """Build MGs from user cases and run them against a user-provided model."""
    empty = [["scope", "total", "MVR", "acc_src", "acc_cons", "HDR", "FUR"]]
    no_violations = [["mg_id", "mr", "ground truth", "source verdict", "follow-up verdict"]]

    if not api_key.strip():
        msg = (
            "Please provide an API key to run a real model (it is used in memory "
            "only and never stored or logged). For a key-free run use the "
            "'Try Demo' tab."
        )
        return empty, [no_violations[0] + [""]], "", msg
    if not model.strip():
        return empty, [no_violations[0] + [""]], "", "Please provide a model name."
    if not base_url.strip():
        base_url = "https://api.openai.com/v1"

    try:
        cases = _parse_source_cases(cases_jsonl)
    except ValueError as e:
        return empty, [no_violations[0] + [""]], "", f"Input error: {e}"

    selected = [
        mr for mr in ALL_MRS if mr.index.split("-")[1][0].upper() in set(categories)
    ]
    if not selected:
        return empty, [no_violations[0] + [""]], "", "Select at least one MR category."

    out_dir = _new_run_dir()
    results_path = os.path.join(out_dir, "results.jsonl")
    report_path = os.path.join(out_dir, "report.html")

    client = OpenAICompatClient(api_key=api_key.strip(), base_url=base_url.strip())
    realize_fn = make_realize_fn(client, model.strip()) if realize else None
    mgs = build_metamorphic_groups(
        cases, mr_list=selected, max_per_case=1, seed=42, realize_fn=realize_fn
    )
    if not mgs:
        return (
            empty,
            [no_violations[0] + [""]],
            "",
            "No metamorphic groups could be built from the given cases with the "
            "selected MR categories.",
        )
    run_inference(
        mgs,
        client,
        model.strip(),
        prompting=prompting,
        result_save_path=results_path,
        max_workers=8,
        quiet=True,
    )
    records = load_inference_records(results_path)
    metrics = compute_metrics(records)
    generate_run_report(records, metrics, report_path, mgs=mgs, title="LGMT Run Report")
    LAST_RUN.update(
        records=records, metrics=metrics, report=report_path, kind=f"model {model.strip()}"
    )
    return (
        _metrics_rows(metrics),
        _violation_rows(records),
        _report_iframe(report_path),
        f"Run finished: {len(records)} groups from {len(cases)} cases | model={model.strip()}\n\n"
        + format_metrics_table(metrics),
    )


# --------------------------------------------------------------------- #
# Tab 3: browse last report
# --------------------------------------------------------------------- #
def browse_last_report():
    if not LAST_RUN:
        empty = [["scope", "total", "MVR", "acc_src", "acc_cons", "HDR", "FUR"]]
        return empty, "", "No run yet — use 'Try Demo' or 'Test Your Model' first."
    return (
        _metrics_rows(LAST_RUN["metrics"]),
        _report_iframe(LAST_RUN["report"]),
        f"Last run: {LAST_RUN.get('kind', '')}\n\n"
        + format_metrics_table(LAST_RUN["metrics"]),
    )


def last_violations():
    if not LAST_RUN:
        return [["mg_id", "mr", "ground truth", "source verdict", "follow-up verdict"]]
    return _violation_rows(LAST_RUN["records"])


# --------------------------------------------------------------------- #
# Gradio app (lazy import)
# --------------------------------------------------------------------- #
def build_app():
    try:
        import gradio as gr
    except ImportError as e:  # pragma: no cover
        raise SystemExit(
            "gradio is required for the web demo: pip install -r requirements-web.txt"
        ) from e

    prompting_choices = sorted(PROMPTING_PRESETS.keys())
    category_choices = ["E", "S", "P", "C"]
    empty_metrics = [["scope", "total", "MVR", "acc_src", "acc_cons", "HDR", "FUR"]]
    empty_violations = [["mg_id", "mr", "ground truth", "source verdict", "follow-up verdict"]]

    with gr.Blocks(title="LGMT — Logic-Guided Metamorphic Testing") as app:
        gr.Markdown(
            "# LGMT — Logic-Guided Metamorphic Testing\n"
            "Evaluate LLM logical-reasoning reliability with first-order-logic "
            "metamorphic relations. The **Try Demo** tab runs fully offline with a "
            "mock model; **Test Your Model** uses your own API key (kept in memory "
            "only, never stored or logged)."
        )

        # ---------------- Tab 1: offline demo ---------------- #
        with gr.Tab("Try Demo"):
            with gr.Row():
                persona = gr.Dropdown(
                    choices=["flawed", "consistent"], value="flawed", label="Mock persona"
                )
                prompting1 = gr.Dropdown(
                    choices=prompting_choices, value="zero_direct", label="Prompting"
                )
            run_btn = gr.Button("Run offline demo (40 bundled groups)", variant="primary")
            status1 = gr.Textbox(label="Status / metrics", lines=8, interactive=False)
            with gr.Row():
                metrics1 = gr.Dataframe(value=empty_metrics, label="Metrics", interactive=False)
                violations1 = gr.Dataframe(
                    value=empty_violations, label="Violations", interactive=False
                )
            report1 = gr.HTML(label="HTML report")
            run_btn.click(
                run_offline_demo,
                inputs=[persona, prompting1],
                outputs=[metrics1, violations1, report1, status1],
            )

        # ---------------- Tab 2: user's model ---------------- #
        with gr.Tab("Test Your Model"):
            gr.Markdown(
                "Provide an OpenAI-compatible endpoint and your own key. "
                "Paste source cases as JSONL (one object per line, see the example). "
                "If the key field is empty, the run is refused with a hint."
            )
            with gr.Row():
                api_key = gr.Textbox(
                    label="API key", type="password", placeholder="sk-..."
                )
                base_url = gr.Textbox(
                    label="Base URL", value="https://api.openai.com/v1"
                )
                model = gr.Textbox(label="Model", placeholder="gpt-4o")
            with gr.Row():
                categories = gr.CheckboxGroup(
                    choices=category_choices, value=category_choices, label="MR categories"
                )
                prompting2 = gr.Dropdown(
                    choices=prompting_choices, value="zero_direct", label="Prompting"
                )
                realize = gr.Checkbox(
                    value=False,
                    label="LLM Logic→NL realize (extra calls; otherwise FOL skeleton)",
                )
            cases_box = gr.Textbox(
                label="Source cases (JSONL)",
                value=EXAMPLE_JSONL,
                lines=10,
                max_lines=20,
            )
            run_btn2 = gr.Button("Build MGs and run", variant="primary")
            status2 = gr.Textbox(label="Status / metrics", lines=8, interactive=False)
            with gr.Row():
                metrics2 = gr.Dataframe(value=empty_metrics, label="Metrics", interactive=False)
                violations2 = gr.Dataframe(
                    value=empty_violations, label="Violations", interactive=False
                )
            report2 = gr.HTML(label="HTML report")
            run_btn2.click(
                run_user_model,
                inputs=[api_key, base_url, model, cases_box, categories, prompting2, realize],
                outputs=[metrics2, violations2, report2, status2],
            )

        # ---------------- Tab 3: browse ---------------- #
        with gr.Tab("Browse Report"):
            refresh = gr.Button("Load last run")
            status3 = gr.Textbox(label="Last run", lines=8, interactive=False)
            with gr.Row():
                metrics3 = gr.Dataframe(value=empty_metrics, label="Metrics", interactive=False)
                violations3 = gr.Dataframe(
                    value=empty_violations, label="Violations", interactive=False
                )
            report3 = gr.HTML(label="HTML report")
            refresh.click(browse_last_report, outputs=[metrics3, report3, status3])
            refresh.click(last_violations, outputs=[violations3])

    return app


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="LGMT Gradio web demo")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    build_app().launch(server_name=args.host, server_port=args.port)


if __name__ == "__main__":
    main()
