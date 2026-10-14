"""LGMT command-line interface.

Subcommands:
    demo        offline end-to-end demo with a mock model (no keys, no network)
    build-mgs   source test cases -> metamorphic groups (MR transform + optional NL realize)
    run         inference over MGs + metamorphic oracle consistency check
    report      metrics (MVR / acc / HDR / FUR) + interactive HTML report
    audit       back-translation fidelity audit
    list-mrs    list all registered FOL-grounded metamorphic relations
    web         launch the interactive Web Studio (zero extra dependencies)
"""
import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

from loguru import logger

from lgmt.config import resolve_settings
from lgmt.core.runner import PROMPTING_PRESETS
from lgmt.mrs import ALL_MRS, MR_CLASS_REGISTRY, get_mr

PROMPTING_CHOICES = sorted(PROMPTING_PRESETS.keys())

_KEY_PROMPT = (
    "No API key configured. Enter your API key (input hidden), or set "
    "LGMT_API_KEY to skip this prompt: "
)

_EPILOG = """\
Three Common Workflows:
  1. Quick Offline Tour (no API key, no network):
       lgmt demo
       lgmt demo --full

  2. Benchmark a Model (on the bundled 3,091-group or 40-group set):
       export LGMT_API_KEY=sk-...
       lgmt run --mgs benchmark --model gpt-4o --output results.jsonl
       lgmt report --results results.jsonl --output report.html

  3. Test Custom Domain Cases (pure natural language, unstructured text, pure FOL, or NL+FOL):
       lgmt build-mgs --input examples/custom_cases.example.jsonl --output my_mgs.jsonl --model gpt-4o
       lgmt run --mgs my_mgs.jsonl --model gpt-4o --output my_results.jsonl
       lgmt report --results my_results.jsonl --output my_report.html

  Interactive Web Studio:
       lgmt web --port 7860
"""


def _configure_logging(verbose: bool = False) -> None:
    """Keep terminal output clean by default; full INFO logs still go to files."""
    logger.remove()
    level = "INFO" if verbose else "WARNING"
    logger.add(
        sys.stderr,
        level=level,
        format="<level>{level}</level>: {message}",
    )


def _prompt_for_api_key() -> Optional[str]:
    """Interactively ask for an API key on a TTY (input hidden).

    Returns the key, or None when not on a TTY or when the user entered
    nothing. The key is only ever held in memory.
    """
    try:
        if not sys.stdin.isatty():
            return None
        import getpass

        return getpass.getpass(_KEY_PROMPT) or None
    except (OSError, EOFError, KeyboardInterrupt):
        return None


def _resolve_client(args, settings, require_real=False):
    """Return (client, model_name) from --mock or real settings."""
    from lgmt.models import MockLLMClient, OpenAICompatClient

    mock_persona = getattr(args, "mock", None)
    if mock_persona:
        model_name = f"mock-{mock_persona}"
        return MockLLMClient(persona=mock_persona), model_name
    if require_real and not settings.api_key:
        typed = _prompt_for_api_key()
        if typed:
            settings.api_key = typed  # in memory only, never persisted
    if require_real and not settings.api_key:
        raise SystemExit(
            "Error: no API key configured. Use --mock for offline mode, pass "
            "--api-key, or set LGMT_API_KEY / 'model.api_key' in the config file."
        )
    client = OpenAICompatClient(
        api_key=settings.api_key,
        base_url=settings.base_url,
        models_map=settings.models_map,
    )
    return client, settings.model


def _find_full_eval_set() -> Optional[str]:
    """Locate the 3,091-group evaluation set (repo checkout or cwd)."""
    rel = Path("data") / "metamorphic_group" / "processed_mgs_core" / "processed_mgs_3091.jsonl"
    candidates = [
        Path.cwd() / rel,
        Path(__file__).resolve().parent.parent / rel,
    ]
    for path in candidates:
        if path.exists():
            return str(path.resolve())
    return None


def _resolve_mgs_path(spec: Optional[str]) -> Optional[str]:
    """Resolve dataset aliases ('demo', 'benchmark', 'full') or return path as-is."""
    if not spec:
        return None
    low = spec.strip().lower()
    if low == "demo":
        return str(Path(__file__).resolve().parent / "demo" / "demo_mgs.jsonl")
    if low in ("benchmark", "full", "3091"):
        found = _find_full_eval_set()
        if found:
            return found
    return spec


def _record_needs_llm_synthesis(r: dict) -> bool:
    """Return True if a record requires an LLM for unstructured extraction or NL->FOL."""
    from lgmt.core.builder import looks_like_fol

    if r.get("premises_logic") and r.get("conclusion_logic"):
        return False
    pt = [str(p).strip() for p in (r.get("premises_text") or []) if str(p).strip()]
    ct = str(r.get("conclusion_text") or "").strip()
    if pt and ct and all(looks_like_fol(p) for p in pt) and looks_like_fol(ct):
        return False
    return True



def _load_mr_files(paths) -> None:
    """Load custom MRs from .py files (Z3-verified) before building/listing."""
    from lgmt.mrs import load_mr_from_source

    for path in paths or []:
        with open(path, "r", encoding="utf-8") as f:
            results = load_mr_from_source(f.read(), verify_z3=True)
        for r in results:
            print(
                f"Loaded custom MR {r['index']}: {r['name']} "
                f"(Z3-verified {r['verified_count']}/{r['tested']} test formulas)"
            )


# --------------------------------------------------------------------- #
# subcommands
# --------------------------------------------------------------------- #
def cmd_build_mgs(args) -> int:
    from lgmt.core.builder import (
        build_metamorphic_groups,
        make_nl2fol_translator,
        make_realize_fn,
        make_unstructured_extractor,
        synthesize_missing_logic,
    )
    from lgmt.core.structure import TestCase
    from lgmt.utils.io import (
        load_json_records,
        save_metamorphic_groups,
    )

    records = load_json_records(args.input)
    if not records:
        print(f"Error: no source test cases loaded from {args.input}")
        return 1

    needs_llm = any(_record_needs_llm_synthesis(r) for r in records)
    synthesis_client = None
    translator = None
    extractor = None

    if needs_llm:
        if args.mock:
            print(
                "Error: NL→FOL synthesis requires a real model (the mock cannot "
                "translate). Provide premises_logic/conclusion_logic fields, or "
                "drop --mock and configure a model."
            )
            return 2
        settings = resolve_settings(
            args.config, {"model": args.model, "api_key": args.api_key}
        )
        try:
            synthesis_client, synthesis_model = _resolve_client(
                args, settings, require_real=True
            )
        except SystemExit:
            print(
                "Error: NL→FOL synthesis requires a model: set LGMT_API_KEY or "
                "pass --model; or provide premises_logic/conclusion_logic fields."
            )
            return 2
        translator = make_nl2fol_translator(synthesis_client, synthesis_model)
        extractor = make_unstructured_extractor(synthesis_client, synthesis_model)

    n_before = len(records)
    records = synthesize_missing_logic(
        records, translator=translator, extractor=extractor
    )
    if needs_llm:
        print(
            f"NL→FOL synthesis: {len(records)}/{n_before} cases translated/kept "
            f"(model '{synthesis_model}')."
        )
    if not records:
        print("Error: no usable source cases remain after NL→FOL synthesis.")
        return 1

    try:
        source_cases = [
            TestCase(
                premises_logic=r.get("premises_logic"),
                conclusion_logic=r.get("conclusion_logic"),
                premises_text=r.get("premises_text"),
                conclusion_text=r.get("conclusion_text"),
                metadata=r.get("metadata") or {},
            )
            for r in records
        ]
    except TypeError as e:
        print(f"Error: malformed source case: {e}")
        return 1
    if not source_cases:
        print(f"Error: no source test cases loaded from {args.input}")
        return 1

    if args.mr_file:
        _load_mr_files(args.mr_file)

    if args.mr:
        mr_list = [get_mr(name) for name in args.mr]
    else:
        mr_list = ALL_MRS

    realize_fn = None
    if not args.no_realize:
        if synthesis_client is not None:
            realize_client, realize_model = synthesis_client, synthesis_model
        else:
            settings = resolve_settings(
                args.config, {"model": args.model, "api_key": args.api_key}
            )
            realize_client, realize_model = _resolve_client(
                args, settings, require_real=True
            )
        realize_fn = make_realize_fn(realize_client, realize_model)
        print(f"Realization (Logic-to-NL) enabled with model '{realize_model}'.")
    else:
        print("Realization disabled: follow-ups keep tagged FOL-skeleton text.")

    mgs = build_metamorphic_groups(
        source_cases,
        mr_list=mr_list,
        max_per_case=args.max_per_case,
        seed=args.seed,
        realize_fn=realize_fn,
        max_workers=args.workers,
    )
    if not mgs:
        print("Error: no metamorphic groups were built.")
        return 1
    save_metamorphic_groups(args.output, mgs)
    print(f"Built {len(mgs)} metamorphic groups -> {args.output}")
    return 0


def cmd_run(args) -> int:
    from lgmt.core.runner import run_inference
    from lgmt.utils.io import load_metamorphic_groups

    mgs_path = _resolve_mgs_path(args.mgs)
    mgs = load_metamorphic_groups(mgs_path)
    if not mgs:
        print(f"Error: no metamorphic groups loaded from {args.mgs}")
        return 1

    settings = resolve_settings(
        args.config,
        {
            "model": args.model,
            "api_key": args.api_key,
            "temperature": args.temperature,
            "max_workers": args.workers,
            "prompting": args.prompting,
        },
    )
    client, model_name = _resolve_client(args, settings, require_real=True)
    if os.path.exists(args.output) and os.path.getsize(args.output) > 0:
        if args.resume:
            print(f"Resuming: new results append to existing {args.output}")
        else:
            print(f"Note: overwriting existing {args.output} (use --resume to append)")
            os.remove(args.output)
    print(
        f"Running inference: {len(mgs)} groups | model='{model_name}' | "
        f"prompting='{settings.prompting}' | workers={settings.max_workers}"
    )
    path = run_inference(
        mgs,
        client,
        model_name,
        prompting=settings.prompting,
        result_save_path=args.output,
        max_workers=settings.max_workers,
        temperature=settings.temperature,
    )
    print(f"Results written to {path}")
    return 0


def cmd_report(args) -> int:
    from lgmt.utils.io import load_inference_records, load_metamorphic_groups
    from lgmt.utils.metrics import compute_metrics, format_metrics_table
    from lgmt.utils.report import generate_run_report

    runs = []
    for i, path in enumerate(args.results):
        records = load_inference_records(path)
        if not records:
            print(f"Error: no inference records loaded from {path}")
            return 1
        models = args.model or []
        name = (
            models[i]
            if i < len(models)
            else (
                records[0].get("model")
                if len(args.results) == 1 and records[0].get("model")
                else (Path(path).stem if len(args.results) == 1 else f"run {i + 1}")
            )
        )
        runs.append(
            {
                "path": path,
                "records": records,
                "metrics": compute_metrics(records),
                "model": name,
            }
        )

    current = runs[0]
    print(format_metrics_table(current["metrics"]))

    mgs_path = _resolve_mgs_path(args.mgs) if args.mgs else None
    mgs = load_metamorphic_groups(mgs_path) if mgs_path else None
    output = args.output or str(
        Path(current["path"]).resolve().parent / "report.html"
    )
    extras = [{"model": r["model"], "metrics": r["metrics"]} for r in runs[1:]]
    generate_run_report(
        current["records"],
        current["metrics"],
        output,
        mgs=mgs,
        model=current["model"],
        prompting=args.prompting,
        extra_runs=extras,
    )
    return 0


def cmd_audit(args) -> int:
    from lgmt.core.audit import audit_mgs, audit_summary
    from lgmt.utils.io import load_metamorphic_groups, write_jsonl

    mgs_path = _resolve_mgs_path(args.mgs)
    mgs = load_metamorphic_groups(mgs_path)
    if not mgs:
        print(f"Error: no metamorphic groups loaded from {args.mgs}")
        return 1

    settings = resolve_settings(
        args.config,
        {
            "model": args.model,
            "api_key": args.api_key,
            "max_workers": args.workers,
        },
    )
    client, model_name = _resolve_client(args, settings, require_real=True)
    print(f"Auditing back-translations with model '{model_name}'...")
    records = audit_mgs(mgs, client, model_name, max_workers=settings.max_workers)
    write_jsonl(args.output, records)
    summary = audit_summary(records)
    print(
        f"Fidelity: {summary['valid']}/{summary['total']} "
        f"({summary['fidelity'] * 100:.2f}%) -> {args.output}"
    )
    return 0


def cmd_demo(args) -> int:
    from lgmt.models import MockLLMClient
    from lgmt.core.runner import run_inference
    from lgmt.utils.io import load_inference_records, load_metamorphic_groups
    from lgmt.utils.metrics import compute_metrics, format_metrics_table
    from lgmt.utils.report import generate_run_report

    if args.mgs:
        mgs_path = _resolve_mgs_path(args.mgs)
    elif args.full:
        mgs_path = _find_full_eval_set()
        if mgs_path is None:
            print(
                "Error: full evaluation set not found. Expected "
                "data/metamorphic_group/processed_mgs_core/processed_mgs_3091.jsonl "
                "in the current directory or the repository root."
            )
            return 1
        print(f"[demo] full evaluation set: {mgs_path}")
    else:
        mgs_path = str(Path(__file__).resolve().parent / "demo" / "demo_mgs.jsonl")
    mgs = load_metamorphic_groups(mgs_path)
    if not mgs:
        print(f"Error: no demo metamorphic groups at {mgs_path}")
        return 1

    output_dir = args.output
    os.makedirs(output_dir, exist_ok=True)
    results_path = os.path.join(output_dir, "results.jsonl")
    report_path = os.path.join(output_dir, "report.html")
    if os.path.exists(results_path):
        os.remove(results_path)

    client = MockLLMClient(persona=args.persona)
    model_name = f"mock-{args.persona}"
    print(
        f"[demo] Offline mode: {len(mgs)} demo MGs | mock persona='{args.persona}' | "
        f"prompting='{args.prompting}' (no API key or network needed)"
    )
    run_inference(
        mgs,
        client,
        model_name,
        prompting=args.prompting,
        result_save_path=results_path,
        max_workers=min(8, args.workers),
        quiet=args.quiet,
    )

    records = load_inference_records(results_path)
    metrics = compute_metrics(records)
    print(format_metrics_table(metrics))
    generate_run_report(
        records,
        metrics,
        report_path,
        mgs=mgs,
        title="LGMT Demo Report (mock model)",
        prompting=args.prompting,
    )
    print(f"[demo] Done. Open {os.path.abspath(report_path)} in your browser.")
    return 0


def cmd_list_mrs(args) -> int:
    if getattr(args, "mr_file", None):
        _load_mr_files(args.mr_file)
    cat_names = {
        "E": "Formula Equivalence (De Morgan, Contraposition, Quantifiers, PNNF)",
        "S": "Symbol Renaming (Predicate / Constant Alpha-Renaming)",
        "P": "Premise Restructuring (Reorder, Duplicate, Irrelevant, Fuse, Split)",
        "C": "Conclusion Variation (Contradiction, Tautology, Double Negation)",
    }
    cls_by_index = {cls().index: name for name, cls in MR_CLASS_REGISTRY.items()}
    header = f"{'Index':<10} {'Class':<10} {'Category':<10} {'Metamorphic Relation Name'}"
    sep = "─" * 68
    print(sep)
    print(header)
    print(sep)
    for mr in sorted(ALL_MRS, key=lambda m: m.index):
        cat = mr.index.split("-")[1][0].upper() if "-" in mr.index else "?"
        cls_name = cls_by_index.get(mr.index, mr.__class__.__name__)
        print(f"{mr.index:<10} {cls_name:<10} {cat:<10} {mr.name}")
    print(sep)
    print(f"Total registered MRs: {len(ALL_MRS)}")
    for k, desc in cat_names.items():
        print(f"  • Category {k}: {desc}")
    return 0


def cmd_web(args) -> int:
    from lgmt.webapp import launch_server

    launch_server(host=args.host, port=args.port, use_gradio=args.gradio)
    return 0


# --------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lgmt",
        description=(
            "LGMT: Logic-Grounded Metamorphic Testing for LLM logical reasoning. "
            "Build metamorphic groups, run entailment inference, and evaluate "
            "metamorphic consistency."
        ),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to YAML config file (default: config.yaml if present).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed runtime logs on stderr.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # build-mgs
    p = sub.add_parser(
        "build-mgs",
        help="Source test cases -> metamorphic groups (MR transform + optional NL realize).",
    )
    p.add_argument("--input", required=True, help="Source test-case JSONL (pure NL, unstructured, pure FOL, or NL+FOL).")
    p.add_argument("--output", required=True, help="Output MG JSONL.")
    p.add_argument(
        "--mr-file",
        action="append",
        default=None,
        help="Path to a Python file defining custom MetamorphicRelation "
        "subclass(es); verified with Z3 on load. Repeatable.",
    )
    p.add_argument(
        "--mr",
        action="append",
        default=None,
        help="MR to apply (class name like MRE15 or index like MR-E1.5); "
        "repeatable. Default: all 20 (see `lgmt list-mrs`).",
    )
    p.add_argument("--max-per-case", type=int, default=1)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--no-realize",
        action="store_true",
        help="Skip LLM Logic-to-NL back-translation (FOL skeleton only).",
    )
    p.add_argument("--model", default=None, help="Model for NL→FOL / Logic→NL realization.")
    p.add_argument("--api-key", default=None, help="API key (overrides env/config).")
    p.add_argument("--mock", choices=["consistent", "flawed"], default=None,
                   help="Use a mock client (offline) for realization.")
    p.add_argument("--workers", type=int, default=1, help="Parallel build workers.")
    p.set_defaults(func=cmd_build_mgs)

    # run
    p = sub.add_parser(
        "run", help="Run entailment inference over MGs and judge metamorphic consistency."
    )
    p.add_argument(
        "--mgs",
        required=True,
        help="Metamorphic group JSONL path, or shorthand 'demo' (40 groups) / 'benchmark' (3,091 groups).",
    )
    p.add_argument("--output", required=True, help="Per-MG result JSONL.")
    p.add_argument("--model", default=None, help="Model name or alias.")
    p.add_argument("--api-key", default=None, help="API key (overrides env/config).")
    p.add_argument(
        "--prompting", choices=PROMPTING_CHOICES, default=None,
        help="Prompting preset (default from config: zero_cot).",
    )
    p.add_argument("--workers", type=int, default=None)
    p.add_argument("--temperature", type=float, default=None)
    p.add_argument("--mock", choices=["consistent", "flawed"], default=None,
                   help="Offline mock model; no API calls.")
    p.add_argument(
        "--resume",
        action="store_true",
        help="Append to an existing non-empty output file instead of "
        "overwriting it.",
    )
    p.set_defaults(func=cmd_run)

    # report
    p = sub.add_parser(
        "report", help="Compute MVR/acc/HDR/FUR metrics and render an interactive HTML report."
    )
    p.add_argument(
        "--results",
        action="append",
        required=True,
        help="Inference result JSONL; repeatable. The first file is the run "
        "shown in detail, the rest join the leaderboard.",
    )
    p.add_argument(
        "--model",
        action="append",
        default=None,
        help="Model name for each --results file (repeatable, same order).",
    )
    p.add_argument(
        "--prompting",
        choices=PROMPTING_CHOICES,
        default=None,
        help="Prompting preset of the run(s); used for leaderboard calibration.",
    )
    p.add_argument("--mgs", default=None, help="Optional MG JSONL (only needed for legacy results without FOL).")
    p.add_argument("--output", default=None, help="Output HTML path (default: <results_dir>/report.html).")
    p.set_defaults(func=cmd_report)

    # audit
    p = sub.add_parser(
        "audit", help="Audit Logic-to-NL back-translation fidelity."
    )
    p.add_argument("--mgs", required=True, help="Metamorphic group JSONL path or 'demo'/'benchmark'.")
    p.add_argument("--output", required=True, help="Audit record JSONL.")
    p.add_argument("--model", default=None)
    p.add_argument("--api-key", default=None, help="API key (overrides env/config).")
    p.add_argument("--workers", type=int, default=None)
    p.add_argument("--mock", choices=["consistent", "flawed"], default=None,
                   help="Offline mock client; all audits pass.")
    p.set_defaults(func=cmd_audit)

    # demo
    p = sub.add_parser(
        "demo",
        help="Offline end-to-end demo with a mock model (no API key, no network).",
    )
    p.add_argument("--output", default="demo_output", help="Output directory.")
    p.add_argument(
        "--persona", choices=["consistent", "flawed"], default="flawed",
        help="Mock model persona. 'flawed' intentionally violates some MRs.",
    )
    p.add_argument("--mgs", default=None, help="Override the bundled demo MG set.")
    p.add_argument(
        "--full",
        action="store_true",
        help="Run the full 3,091-group evaluation set from data/ instead of "
        "the 40-group demo set (still offline; uses the reference "
        "full_3091 leaderboard caliber).",
    )
    p.add_argument("--prompting", choices=PROMPTING_CHOICES, default="zero_cot")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--quiet", action="store_true", help="Hide the progress bar.")
    p.set_defaults(func=cmd_demo)

    # list-mrs
    p = sub.add_parser(
        "list-mrs",
        help="List all registered FOL-grounded metamorphic relations (built-in + custom).",
    )
    p.add_argument(
        "--mr-file",
        action="append",
        default=None,
        help="Path to a Python file defining custom MetamorphicRelation "
        "subclass(es); verified with Z3 on load. Repeatable.",
    )
    p.set_defaults(func=cmd_list_mrs)

    # web
    p = sub.add_parser(
        "web",
        help="Launch the interactive LGMT Web Studio (zero extra dependencies).",
    )
    p.add_argument("--port", type=int, default=7860, help="Port to serve on (default: 7860).")
    p.add_argument("--host", default="0.0.0.0", help="Host address (default: 0.0.0.0).")
    p.add_argument(
        "--gradio",
        action="store_true",
        help="Use the Gradio UI wrapper instead of the built-in native Web Studio.",
    )
    p.set_defaults(func=cmd_web)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    # Windows consoles default to a legacy code page (e.g. cp936/GBK);
    # force UTF-8 output so logic symbols and progress bars never crash.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(verbose=getattr(args, "verbose", False))
    if args.config is None and os.path.exists("config.yaml"):
        args.config = "config.yaml"
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
