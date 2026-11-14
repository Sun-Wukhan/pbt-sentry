"""End-to-end and unit tests for pbt-sentry. Stdlib fakes only."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pbt_sentry.cli import main
from pbt_sentry.core import failure_signature, normalise_output, run_hunt

PY = sys.executable


def py_cmd(code: str) -> str:
    return f'"{PY}" -c "{code}"'


# 1. A command that always passes -> 0 findings, exit 0.
def test_always_passing_command(tmp_path):
    report = tmp_path / "r.md"
    data = tmp_path / "r.json"
    code = main(
        [
            "--command", py_cmd("pass"),
            "--runs", "5",
            "--report", str(report),
            "--json", str(data),
        ]
    )
    assert code == 0
    payload = json.loads(data.read_text())
    assert payload["runs"] == 5
    assert payload["passed"] == 5
    assert payload["failed_runs"] == 0
    assert payload["unique_findings"] == 0
    assert payload["findings"] == []
    assert "Unique findings | 0" in report.read_text()


# 2. Fails only on specific seeds, same error modulo the seed -> 1 finding.
def test_seed_specific_failures_dedup_to_one_finding():
    code = (
        "import os,sys; s=int(os.environ['PBT_SEED']); "
        "sys.exit('boom at 0xdeadbeef seed=%d' % s) if s % 3 == 0 else None"
    )
    result = run_hunt(py_cmd(code), runs=9, seed_start=0, timeout=30)
    assert result.passed == 6
    assert result.failed_runs == 3
    assert result.unique_findings == 1
    finding = result.findings[0]
    assert finding.example_seed == 0
    assert finding.seeds == [0, 3, 6]
    assert finding.runs_failed == 3
    # Reproduction is exact: the repro command fails the same way.
    import subprocess

    proc = subprocess.run(finding.repro_command, shell=True, capture_output=True, text=True)
    assert proc.returncode != 0
    assert "boom" in (proc.stdout + proc.stderr)


# 2b. The {seed} placeholder drives the failing seed identically.
def test_seed_placeholder_substitution():
    template = f'"{PY}" -c "import sys; sys.exit(1 if {{seed}} == 4 else 0)"'
    result = run_hunt(template, runs=6, seed_start=2, timeout=30)
    assert result.failed_runs == 1
    assert result.findings[0].example_seed == 4
    assert "{seed}" not in result.findings[0].repro_command
    assert "== 4" in result.findings[0].repro_command


# 3. Two different errors on different seeds -> 2 findings.
def test_two_distinct_errors_give_two_findings():
    code = (
        "import os,sys; s=int(os.environ['PBT_SEED']); "
        "sys.exit('alpha failure in parser.py:10') if s % 2 == 0 else "
        "sys.exit('beta failure in encoder.py:99')"
    )
    result = run_hunt(py_cmd(code), runs=6, seed_start=0, timeout=30)
    assert result.failed_runs == 6
    assert result.unique_findings == 2
    sigs = {f.signature for f in result.findings}
    assert len(sigs) == 2
    total = sum(f.runs_failed for f in result.findings)
    assert total == 6


# 4. Sleeping command with a tiny timeout -> one timeout finding.
def test_timeout_finding():
    result = run_hunt(py_cmd("import time; time.sleep(30)"), runs=3, seed_start=0, timeout=0.5)
    assert result.passed == 0
    assert result.failed_runs == 3
    assert result.unique_findings == 1
    assert result.findings[0].signature == "timeout"
    assert result.findings[0].seeds == [0, 1, 2]


# Exit-code contract: findings -> 1 by default, 0 with --no-fail-on-finding.
def test_exit_codes(tmp_path):
    failing = py_cmd("import sys; sys.exit('nope')")
    common = ["--runs", "2", "--report", str(tmp_path / "r.md"), "--json", str(tmp_path / "r.json")]
    assert main(["--command", failing, *common]) == 1
    assert main(["--command", failing, "--no-fail-on-finding", *common]) == 0


# Misuse -> exit 2.
def test_unparseable_command_is_misuse(tmp_path):
    code = main(
        [
            "--command", '"unterminated',
            "--report", str(tmp_path / "r.md"),
            "--json", str(tmp_path / "r.json"),
        ]
    )
    assert code == 2


# 5. Signature normalisation unit tests.
def test_normalisation_strips_addresses_timestamps_and_seed():
    raw = (
        "Failure at 0x7f8a1b2c on 2026-11-13T01:02:03.123Z seed=42 "
        "took 1.25s in /tmp/tmpab12cd/run.py:77"
    )
    out = normalise_output(raw, seed=42)
    assert "0x7f8a1b2c" not in out
    assert "2026-11-13" not in out
    assert "01:02:03" not in out
    assert "42" not in out
    assert "1.25s" not in out
    assert "/tmp/tmpab12cd" not in out


def test_normalisation_preserves_file_and_line():
    raw = "AssertionError in parser.py:56 while reading input"
    out = normalise_output(raw, seed=7)
    assert "parser.py:56" in out


def test_same_bug_different_noise_same_signature():
    a = "Error seed=1 at 0x1111 on 2026-01-01T00:00:00Z\nparser.py:56: boom"
    b = "Error seed=9 at 0x2222 on 2026-12-31T23:59:59Z\nparser.py:56: boom"
    assert failure_signature(a, seed=1) == failure_signature(b, seed=9)


def test_different_bug_different_signature():
    a = "parser.py:56: boom"
    b = "encoder.py:99: bang"
    assert failure_signature(a) != failure_signature(b)
