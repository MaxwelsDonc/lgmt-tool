"""LGMT command-line interface.

Subcommands:
    build-mgs   source test cases -> metamorphic groups (MR transform + optional NL realize)
    run         inference over MGs + metamorphic oracle consistency check
    report      metrics (MVR / acc / HDR / FUR) + HTML report
    audit       back-translation fidelity audit (FOL2NL_validate)
    demo        offline end-to-end demo with a mock model (no keys, no network)
"""
import argparse
import os
import sys
from typing import List, Optional

from lgmt.config import resolve_settings
from lgmt.core.runner import PROMPTING_PRESETS
from lgmt.mrs import ALL_MRS, get_mr

PROMPTING_CHOICES = sorted(PROMPTING_PRESETS.keys())


def _resolve_client(args, settings, require_real=False):
    """Return (client, model_name) from --mock or real settings."""
    from lgmt.models import MockLLMClient, OpenAICompatClient

    mock_persona = getattr(args, "mock", None)
    if mock_persona:
        model_name = f"mock-{mock_persona}"
        return MockLLMClient(persona=mock_persona), model_name
    if require_real and not settings.api_key:
        raise SystemExit(
            "Error: no API key configured. Use --mock for offline mode, or set "
            "LGMT_API_KEY / 'model.api_key' in the config file."
        )
    client = OpenAICompatClient(
        api_key=settings.api_key,
        base_url=settings.base_url,
        models_map=settings.models_map,
    )
    return client, settings.model


# --------------------------------------------------------------------- #
# subcommands
# --------------------------------------------------------------------- #
def cmd_build_mgs(args) -> int:
    from lgmt.core.builder import build_metamorphic_groups, make_realize_fn
    from lgmt.utils.io import load_test_cases, save_metamorphic_groups

    source_cases = load_test_cases(args.input)
    if not source_cases:
        print(f"Error: no source test cases loaded from {args.input}")
        return 1

    if args.mr:
        mr_list = [get_mr(name) for name in args.mr]
    else:
        mr_list = ALL_MRS

    realize_fn = None
    if not args.no_realize:
        settings = resolve_settings(args.config, {"model": args.model})
        client, model_name = _resolve_client(args, settings, require_real=True)
        realize_fn = make_realize_fn(client, model_name)
        print(f"Realization (Logic-to-NL) enabled with model '{model_name}'.")
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

    mgs = load_metamorphic_groups(args.mgs)
    if not mgs:
        print(f"Error: no metamorphic groups loaded from {args.mgs}")
        return 1

    settings = resolve_settings(
        args.config,
        {
            "model": args.model,
            "temperature": args.temperature,
            "max_workers": args.workers,
            "prompting": args.prompting,
        },
    )
    client, model_name = _resolve_client(args, settings)
    print(
        f"Running inference: model='{model_name}', prompting='{settings.prompting}', "
        f"workers={settings.max_workers}"
    )
    path = run_inference(
        mgs,
        client,
        model_name,
        prompting=settings.prompting,
        result_save_path=args.output,
        max_workers=settings.max_workers,
    )
    print(f"Results written to {path}")
    return 0


def cmd_report(args) -> int:
    from lgmt.utils.io import load_inference_records, load_metamorphic_groups
    from lgmt.utils.metrics import compute_metrics, format_metrics_table
    from lgmt.utils.report import generate_run_report

    records = load_inference_records(args.results)
    if not records:
        print(f"Error: no inference records loaded from {args.results}")
        return 1

    metrics = compute_metrics(records)
    print(format_metrics_table(metrics))

    mgs = load_metamorphic_groups(args.mgs) if args.mgs else None
    output = args.output or os.path.join(
        os.path.dirname(os.path.abspath(args.results)), "report.html"
    )
    generate_run_report(records, metrics, output, mgs=mgs)
    return 0


def cmd_audit(args) -> int:
    from lgmt.core.audit import audit_mgs, audit_summary
    from lgmt.utils.io import load_metamorphic_groups, write_jsonl

    mgs = load_metamorphic_groups(args.mgs)
    if not mgs:
        print(f"Error: no metamorphic groups loaded from {args.mgs}")
        return 1

    settings = resolve_settings(
        args.config, {"model": args.model, "max_workers": args.workers}
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
        mgs_path = args.mgs
    else:
        mgs_path = os.path.join(os.path.dirname(__file__), "demo", "demo_mgs.jsonl")
    mgs = load_metamorphic_groups(mgs_path)
    if not mgs:
        print(f"Error: no demo metamorphic groups at {mgs_path}")
        return 1

    output_dir = args.output
    os.makedirs(output_dir, exist_ok=True)
    results_path = os.path.join(output_dir, "results.jsonl")
    report_path = os.path.join(output_dir, "report.html")

    client = MockLLMClient(persona=args.persona)
    model_name = f"mock-{args.persona}"
    print(
        f"[demo] Offline mode: {len(mgs)} demo MGs, mock persona='{args.persona}', "
        f"prompting='{args.prompting}'. No API calls will be made."
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
        records, metrics, report_path, mgs=mgs, title="LGMT Demo Report (mock model)"
    )
    print(f"[demo] Done. Artifacts in {os.path.abspath(output_dir)}/")
    return 0


# --------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lgmt",
        description=(
            "LGMT: Logic-Guided Metamorphic Testing for LLM logical reasoning. "
            "Build metamorphic groups, run entailment inference, and evaluate "
            "metamorphic consistency."
        ),
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to YAML config file (default: config.yaml if present).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # build-mgs
    p = sub.add_parser(
        "build-mgs",
        help="Source test cases -> metamorphic groups (MR transform + optional NL realize).",
    )
    p.add_argument("--input", required=True, help="Source test-case JSONL.")
    p.add_argument("--output", required=True, help="Output MG JSONL.")
    p.add_argument(
        "--mr",
        action="append",
        default=None,
        help="MR to apply (class name like MRE15 or index like MR-E1.5); "
        "repeatable. Default: all 20.",
    )
    p.add_argument("--max-per-case", type=int, default=1)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--no-realize",
        action="store_true",
        help="Skip LLM Logic-to-NL back-translation (FOL skeleton only).",
    )
    p.add_argument("--model", default=None, help="Model for realization.")
    p.add_argument("--mock", choices=["consistent", "flawed"], default=None,
                   help="Use a mock client (offline) for realization.")
    p.add_argument("--workers", type=int, default=1, help="Parallel build workers.")
    p.set_defaults(func=cmd_build_mgs)

    # run
    p = sub.add_parser(
        "run", help="Run entailment inference over MGs and judge metamorphic consistency."
    )
    p.add_argument("--mgs", required=True, help="Metamorphic group JSONL.")
    p.add_argument("--output", required=True, help="Per-MG result JSONL.")
    p.add_argument("--model", default=None, help="Model name or alias.")
    p.add_argument(
        "--prompting", choices=PROMPTING_CHOICES, default=None,
        help="Prompting preset (default from config).",
    )
    p.add_argument("--workers", type=int, default=None)
    p.add_argument("--temperature", type=float, default=None)
    p.add_argument("--mock", choices=["consistent", "flawed"], default=None,
                   help="Offline mock model; no API calls.")
    p.set_defaults(func=cmd_run)

    # report
    p = sub.add_parser(
        "report", help="Compute MVR/acc/HDR/FUR metrics and render an HTML report."
    )
    p.add_argument("--results", required=True, help="Inference result JSONL.")
    p.add_argument("--mgs", default=None, help="Optional MG JSONL for full logic comparison.")
    p.add_argument("--output", default=None, help="Output HTML path.")
    p.set_defaults(func=cmd_report)

    # audit
    p = sub.add_parser(
        "audit", help="Audit Logic-to-NL back-translation fidelity (FOL2NL_validate)."
    )
    p.add_argument("--mgs", required=True, help="Metamorphic group JSONL.")
    p.add_argument("--output", required=True, help="Audit record JSONL.")
    p.add_argument("--model", default=None)
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
    p.add_argument("--prompting", choices=PROMPTING_CHOICES, default="zero_direct")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--quiet", action="store_true", help="Hide the progress bar.")
    p.set_defaults(func=cmd_demo)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.config is None and os.path.exists("config.yaml"):
        args.config = "config.yaml"
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
