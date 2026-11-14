"""Command-line interface for pbt-sentry.

Exit codes:
  0  every run passed, or findings exist but --no-fail-on-finding was given
  1  unique findings exist and --fail-on-finding is in effect (the default)
  2  runner misuse / errors (unparseable command, invalid arguments, ...)
"""

from __future__ import annotations

import argparse
import shlex
import sys

from . import __version__
from .core import run_hunt
from .report import render_json, render_markdown

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_MISUSE = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pbt-sentry",
        description=(
            "Run a property-test command across many seeds, deduplicate "
            "failures by normalised signature, and write a minimised bug report."
        ),
    )
    parser.add_argument("--version", action="version", version=f"pbt-sentry {__version__}")
    parser.add_argument(
        "--command",
        required=True,
        help=(
            "Command to run once per seed. May contain a {seed} placeholder; "
            "the seed is always exported as PBT_SEED and HYPOTHESIS_SEED."
        ),
    )
    parser.add_argument("--runs", type=int, default=50, help="Number of seeds to run (default: 50).")
    parser.add_argument(
        "--seed-start",
        type=int,
        default=0,
        help="First seed; seeds are seed_start..seed_start+runs-1 (default: 0).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Per-run timeout in seconds (default: 120).",
    )
    parser.add_argument("--report", default="pbt-report.md", help="Markdown report path (default: pbt-report.md).")
    parser.add_argument("--json", default="pbt-report.json", help="JSON report path (default: pbt-report.json).")
    parser.add_argument(
        "--fail-on-finding",
        dest="fail_on_finding",
        action="store_true",
        default=True,
        help="Exit 1 if any unique finding is produced (default).",
    )
    parser.add_argument(
        "--no-fail-on-finding",
        dest="fail_on_finding",
        action="store_false",
        help="Always exit 0 unless the runner itself errors.",
    )
    return parser


def _validate(parser: argparse.ArgumentParser, args: argparse.Namespace) -> str | None:
    if not args.command or not args.command.strip():
        return "--command must not be empty"
    if args.runs < 1:
        return "--runs must be at least 1"
    if args.timeout <= 0:
        return "--timeout must be greater than 0"
    # The command is executed via the shell, but it must at least tokenise.
    try:
        tokens = shlex.split(args.command)
    except ValueError as exc:
        return f"unparseable command: {exc}"
    if not tokens:
        return "--command must not be empty"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse exits 2 on bad usage itself; preserve that as misuse.
        return int(exc.code or 0) if exc.code != 0 else EXIT_OK

    problem = _validate(parser, args)
    if problem is not None:
        print(f"pbt-sentry: error: {problem}", file=sys.stderr)
        return EXIT_MISUSE

    result = run_hunt(
        args.command,
        runs=args.runs,
        seed_start=args.seed_start,
        timeout=args.timeout,
    )

    try:
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write(render_markdown(result))
        with open(args.json, "w", encoding="utf-8") as fh:
            fh.write(render_json(result))
    except OSError as exc:
        print(f"pbt-sentry: error: could not write report: {exc}", file=sys.stderr)
        return EXIT_MISUSE

    print(
        f"pbt-sentry: {result.runs} runs | {result.passed} passed | "
        f"{result.failed_runs} failed runs | {result.unique_findings} unique finding(s)"
    )
    for finding in result.findings:
        print(
            f"  finding {finding.signature[:12]}: example seed {finding.example_seed}, "
            f"{finding.runs_failed} failing run(s) — repro: {finding.repro_command}"
        )
    print(f"pbt-sentry: reports written to {args.report} and {args.json}")

    if result.findings and args.fail_on_finding:
        return EXIT_FINDINGS
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
