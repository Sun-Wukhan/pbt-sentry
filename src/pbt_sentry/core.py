"""Core engine for pbt-sentry.

Runs a user-supplied property-test command once per seed, captures failures,
normalises each failing output into a stable signature, and groups failures
with the same signature into a single finding.

Standard library only.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass, field

__all__ = [
    "Finding",
    "HuntResult",
    "RunOutcome",
    "normalise_output",
    "failure_signature",
    "build_command",
    "run_hunt",
]

# How many trailing lines of output feed the signature / are kept as excerpt.
SIGNATURE_LINES = 15
EXCERPT_LINES = 30

TIMEOUT_SIGNATURE = "timeout"

_HEX_ADDRESS = re.compile(r"0x[0-9a-fA-F]+")
_ISO_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)
_DATE_ONLY = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_TIME_ONLY = re.compile(r"\b\d{2}:\d{2}:\d{2}(?:\.\d+)?\b")
_DURATION = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:ms|s|sec|secs|second|seconds|min|mins|minute|minutes)\b"
)
_TEMP_PATH = re.compile(r"(?:/tmp/|/var/folders/|\\Temp\\)[^\s:'\"]*")
_TMP_GENERIC = re.compile(r"\btmp[0-9a-zA-Z_]{6,}\b")


def normalise_output(text: str, seed: int | None = None) -> str:
    """Strip run-specific noise so identical bugs hash identically.

    Removes: the seed value itself, hex memory addresses, ISO timestamps
    and dates/times, durations, and absolute temp paths. File paths and
    line numbers are deliberately KEPT — they identify the bug.
    """
    out = text
    # Noise patterns first: they contain digits that could collide with
    # the seed value (e.g. seed 0 inside 0xdeadbeef, or inside a date).
    out = _HEX_ADDRESS.sub("<ADDR>", out)
    out = _ISO_TIMESTAMP.sub("<TIMESTAMP>", out)
    out = _DATE_ONLY.sub("<DATE>", out)
    out = _TIME_ONLY.sub("<TIME>", out)
    out = _DURATION.sub("<DURATION>", out)
    out = _TEMP_PATH.sub("<TMP>", out)
    out = _TMP_GENERIC.sub("<TMP>", out)
    if seed is not None:
        # Strip the seed as a standalone token — but never when it is
        # part of a file:line reference or a path, which identify the bug.
        out = re.sub(
            rf"(?<![0-9:/.]){re.escape(str(seed))}(?![0-9])", "<SEED>", out
        )
    return out


def _tail(text: str, lines: int) -> str:
    parts = text.rstrip().splitlines()
    return "\n".join(parts[-lines:])


def failure_signature(output: str, seed: int | None = None) -> str:
    """sha256 of the normalised last SIGNATURE_LINES lines of output."""
    normalised = normalise_output(_tail(output, SIGNATURE_LINES), seed=seed)
    return hashlib.sha256(normalised.encode("utf-8", "replace")).hexdigest()


def build_command(template: str, seed: int) -> str:
    """Substitute {seed} if present; the seed is always also in the env."""
    if "{seed}" in template:
        return template.replace("{seed}", str(seed))
    return template


@dataclass
class RunOutcome:
    seed: int
    command: str
    exit_code: int | None  # None when the run timed out
    output: str
    timed_out: bool = False

    @property
    def failed(self) -> bool:
        return self.timed_out or (self.exit_code not in (0, None))


@dataclass
class Finding:
    signature: str
    example_seed: int
    seeds: list[int] = field(default_factory=list)
    exit_code: int | None = None
    output_excerpt: str = ""
    repro_command: str = ""

    @property
    def runs_failed(self) -> int:
        return len(self.seeds)

    def to_dict(self) -> dict:
        return {
            "signature": self.signature,
            "example_seed": self.example_seed,
            "seeds": list(self.seeds),
            "runs_failed": self.runs_failed,
            "exit_code": self.exit_code,
            "repro_command": self.repro_command,
            "output_excerpt": self.output_excerpt,
        }


@dataclass
class HuntResult:
    command_template: str
    runs: int
    seed_start: int
    timeout: float
    passed: int = 0
    failed_runs: int = 0
    findings: list[Finding] = field(default_factory=list)

    @property
    def unique_findings(self) -> int:
        return len(self.findings)

    def to_dict(self) -> dict:
        return {
            "command": self.command_template,
            "runs": self.runs,
            "seed_start": self.seed_start,
            "timeout_seconds": self.timeout,
            "passed": self.passed,
            "failed_runs": self.failed_runs,
            "unique_findings": self.unique_findings,
            "findings": [f.to_dict() for f in self.findings],
        }


def _run_once(template: str, seed: int, timeout: float) -> RunOutcome:
    command = build_command(template, seed)
    env = dict(os.environ)
    env["PBT_SEED"] = str(seed)
    env["HYPOTHESIS_SEED"] = str(seed)
    try:
        proc = subprocess.run(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            timeout=timeout,
            env=env,
        )
        return RunOutcome(
            seed=seed,
            command=command,
            exit_code=proc.returncode,
            output=proc.stdout or "",
        )
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", "replace")
        return RunOutcome(
            seed=seed,
            command=command,
            exit_code=None,
            output=partial,
            timed_out=True,
        )


def run_hunt(
    command_template: str,
    runs: int = 50,
    seed_start: int = 0,
    timeout: float = 120.0,
) -> HuntResult:
    """Execute the command across seeds seed_start..seed_start+runs-1."""
    result = HuntResult(
        command_template=command_template,
        runs=runs,
        seed_start=seed_start,
        timeout=timeout,
    )
    by_signature: dict[str, Finding] = {}

    for offset in range(runs):
        seed = seed_start + offset
        outcome = _run_once(command_template, seed, timeout)
        if not outcome.failed:
            result.passed += 1
            continue
        result.failed_runs += 1
        if outcome.timed_out:
            signature = TIMEOUT_SIGNATURE
        else:
            signature = failure_signature(outcome.output, seed=seed)
        finding = by_signature.get(signature)
        if finding is None:
            if "{seed}" in command_template:
                repro = outcome.command
            else:
                # The seed reached this run through the environment, so a
                # bare command would not reproduce it. Make the repro
                # command self-contained with the env assignments inline.
                repro = f"PBT_SEED={seed} HYPOTHESIS_SEED={seed} {outcome.command}"
            finding = Finding(
                signature=signature,
                example_seed=seed,
                exit_code=outcome.exit_code,
                output_excerpt=_tail(outcome.output, EXCERPT_LINES),
                repro_command=repro,
            )
            by_signature[signature] = finding
            result.findings.append(finding)
        finding.seeds.append(seed)

    return result
