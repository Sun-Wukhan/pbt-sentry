"""Report rendering for pbt-sentry (Markdown + JSON)."""

from __future__ import annotations

import json

from .core import HuntResult


def render_markdown(result: HuntResult) -> str:
    lines: list[str] = []
    lines.append("# pbt-sentry report")
    lines.append("")
    lines.append(f"Command: `{result.command_template}`")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Runs | {result.runs} |")
    lines.append(f"| Seeds | {result.seed_start}..{result.seed_start + result.runs - 1} |")
    lines.append(f"| Passed | {result.passed} |")
    lines.append(f"| Failed runs | {result.failed_runs} |")
    lines.append(f"| Unique findings | {result.unique_findings} |")
    lines.append("")
    if not result.findings:
        lines.append("No unique failures found. Every seed passed.")
        lines.append("")
        return "\n".join(lines)

    lines.append("## Findings")
    lines.append("")
    for idx, finding in enumerate(result.findings, start=1):
        lines.append(f"### Finding {idx}: `{finding.signature[:12]}`")
        lines.append("")
        lines.append(f"- Signature: `{finding.signature}`")
        lines.append(f"- Example seed: `{finding.example_seed}`")
        lines.append(f"- All failing seeds: {', '.join(str(s) for s in finding.seeds)}")
        lines.append(f"- Failed runs with this signature: {finding.runs_failed}")
        exit_label = "timeout" if finding.exit_code is None else str(finding.exit_code)
        lines.append(f"- Exit code: {exit_label}")
        lines.append("")
        lines.append("Reproduce with:")
        lines.append("")
        lines.append("```bash")
        lines.append(finding.repro_command)
        lines.append("```")
        lines.append("")
        lines.append("Output excerpt (first failing example, last 30 lines):")
        lines.append("")
        lines.append("```text")
        lines.append(finding.output_excerpt)
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def render_json(result: HuntResult) -> str:
    return json.dumps(result.to_dict(), indent=2) + "\n"
