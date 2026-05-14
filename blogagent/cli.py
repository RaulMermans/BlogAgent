"""CLI entry point for BlogAgent.

Usage:
    python -m blogagent.cli run "Why elephants are the heaviest land animals"
    python -m blogagent.cli run "..." --show-trace
    python -m blogagent.cli run "..." --json
    python -m blogagent.cli run "..." --output examples/live_smoke_output.json
    python -m blogagent.cli compare examples/mock_elephants_output.json \
        examples/live_elephants_output.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from blogagent.workflow.graph import run_pipeline, validate_final_state
from blogagent.workflow.state import BlogRunState  # noqa: F401 (used in type hint)

# ---------------------------------------------------------------------------
# Subcommand: run
# ---------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> int:
    topic: str = args.topic
    state: BlogRunState = run_pipeline(topic)

    if state.blocked:
        print(f"BLOCKED: {state.block_reason}")
        if args.show_trace:
            _print_trace(state)
        return 1

    errors = validate_final_state(state)
    pkg = state.final_article_package

    if args.json:
        if pkg:
            payload = _enrich_package(pkg.model_dump(), state)
        else:
            payload = {
                "blocked": state.blocked,
                "block_reason": state.block_reason,
                "errors": errors,
            }
        output_str = json.dumps(payload, indent=2)
        print(output_str)
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(output_str)
        return 0 if not errors else 1

    # Default human-readable summary
    if pkg:
        report = pkg.fact_check_report
        print(f"Title:            {pkg.title}")
        print(f"Meta description: {pkg.meta_description}")
        print(f"Slug:             {pkg.slug}")
        print(f"Sources:          {len(pkg.source_list)}")
        print(
            f"Claims:           {report.total_claims} total  "
            f"| {report.supported_count} supported  "
            f"| {report.partially_supported_count} partial  "
            f"| {report.unsupported_count} unsupported"
        )
        print(f"Revisions:        {state.revision_count}")
        print(f"Execution mode:   {state.execution_mode}")
        print(f"Blocked:          {state.blocked}")
        if errors:
            print(f"Validation:       FAILED — {'; '.join(errors)}")
        else:
            print("Validation:       OK")

    if args.show_trace:
        _print_trace(state)

    if args.output and pkg:
        payload = json.dumps(_enrich_package(pkg.model_dump(), state), indent=2)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(payload)
        print(f"Output written:   {args.output}")

    return 0 if not errors else 1


def _enrich_package(pkg_dict: dict, state: BlogRunState) -> dict:
    """Add state-level fields to an ArticlePackage dict for richer --output files."""
    pkg_dict["execution_mode"] = state.execution_mode
    pkg_dict["revision_count"] = state.revision_count
    pkg_dict["blocked"] = state.blocked
    pkg_dict["block_reason"] = state.block_reason
    pkg_dict["provider_events"] = list(state.provider_events)
    pkg_dict["warnings"] = list(state.warnings)
    return pkg_dict


def _print_trace(state: BlogRunState) -> None:
    print()
    print("--- Run Trace ---")
    print(f"Execution mode: {state.execution_mode}")
    if state.warnings:
        print("Warnings:")
        for w in state.warnings:
            print(f"  [WARN] {w}")
    else:
        print("Warnings:       none")
    if state.provider_events:
        print("Provider events:")
        for e in state.provider_events:
            print(f"  [INFO] {e}")
    if state.stage_timings:
        print("Stage timings (s):")
        for stage, t in state.stage_timings.items():
            print(f"  {stage}: {t:.3f}s")
    print("-----------------")


# ---------------------------------------------------------------------------
# Subcommand: compare
# ---------------------------------------------------------------------------


def cmd_compare(args: argparse.Namespace) -> int:
    from blogagent.evals.compare_outputs import compare_outputs, format_comparison_table

    paths = [Path(p) for p in args.files]
    metrics_list = compare_outputs(paths)

    # Print errors for missing/invalid files
    errors = [m for m in metrics_list if m.load_error]
    ok = [m for m in metrics_list if not m.load_error]

    print(format_comparison_table(metrics_list))

    if errors and not ok:
        return 2  # all files failed to load
    if errors:
        return 1  # some files failed
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m blogagent.cli",
        description="BlogAgent CLI — smoke-test and inspect the pipeline.",
    )
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Run the pipeline on a topic and print a summary.")
    run_p.add_argument("topic", help="The blog topic to research and write about.")
    run_p.add_argument(
        "--json",
        action="store_true",
        dest="json",
        help="Print the full ArticlePackage as JSON instead of the summary.",
    )
    run_p.add_argument(
        "--show-trace",
        action="store_true",
        dest="show_trace",
        help="Print warnings, provider events, and stage timings after the summary.",
    )
    run_p.add_argument(
        "--output",
        metavar="PATH",
        default=None,
        help="Write JSON output to this file path (creates parent dirs if needed).",
    )

    compare_p = sub.add_parser(
        "compare",
        help="Compare two or more saved run output JSON files and print a quality table.",
    )
    compare_p.add_argument(
        "files",
        nargs="+",
        metavar="FILE",
        help="Paths to ArticlePackage JSON files produced by --output.",
    )

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "run":
        sys.exit(cmd_run(args))

    if args.command == "compare":
        sys.exit(cmd_compare(args))


if __name__ == "__main__":
    main()
