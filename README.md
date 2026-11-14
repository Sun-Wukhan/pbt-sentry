# pbt-sentry

**Property-based testing bug hunt in a box.**

Run a property-test command across many seeds, capture every failure,
deduplicate them by normalised failure signature, and get one minimised
bug report per *unique* bug — not one per failing run.

## The method

This packages the workflow behind a series of real property-based bug
hunts (Go `rapid` against Argo CD, Hypothesis-style properties against
Prometheus):

1. **Write properties, not examples.** A property states an invariant
   ("decode(encode(x)) == x", "a parsed duration re-renders to itself")
   and a framework generates thousands of inputs for it.
2. **Run properties at scale, per seed.** One process per seed, seeds
   numbered deterministically (`seed_start .. seed_start+runs-1`), so
   any failure can be replayed exactly.
3. **Group identical failures.** Raw output is noisy — seeds, memory
   addresses, timestamps, durations and temp paths change every run.
   pbt-sentry strips that noise, hashes the normalised tail of the
   output (sha256), and groups failures by hash. Fifty failing runs of
   the same bug become **one** finding.
4. **Report unique bugs only**, each with its example seed, every seed
   that hit it, and an exact reproduction command.

## Field results

This method has a track record. Run against Argo CD and Prometheus in
late 2026, it produced eight confirmed findings: three fixes merged
upstream, two more in review, and one bug fixed upstream following
our report. The catches include a panic in glob matching, a
security-relevant AppProject destination deny bypass, and a
Prometheus duration bug that silently drops a millisecond
(`1s1ms` evaluating as `1s`).

The full list, with the property that caught each bug and its
upstream status: [docs/FINDINGS.md](docs/FINDINGS.md).

## Quick start — CLI

```bash
pip install pbt-sentry        # or: pip install .
pbt-sentry --command "python -m pytest tests/test_properties.py -q --hypothesis-seed={seed}" --runs 100
```

The command may contain a `{seed}` placeholder. Whether or not it does,
the seed is always exported to each run as `PBT_SEED` and
`HYPOTHESIS_SEED`, so commands that read the seed from the environment
work unchanged.

Exit codes: `0` = all runs passed · `1` = at least one unique finding
(suppress with `--no-fail-on-finding`) · `2` = runner misuse (e.g. an
unparseable command).

### CLI options

| Option | Default | Meaning |
|---|---|---|
| `--command` | *(required)* | Command run once per seed; may contain `{seed}` |
| `--runs` | `50` | Number of seeds to run |
| `--seed-start` | `0` | First seed |
| `--timeout` | `120` | Per-run timeout in seconds; a timeout is a failure with signature `timeout` |
| `--report` | `pbt-report.md` | Markdown report path |
| `--json` | `pbt-report.json` | JSON report path |
| `--fail-on-finding` / `--no-fail-on-finding` | fail | Exit 1 when unique findings exist |

## Quick start — GitHub Action

```yaml
- uses: Sun-Wukhan/pbt-sentry@v0.1.0
  id: pbt
  with:
    command: "python -m pytest tests/test_properties.py -q --hypothesis-seed={seed}"
    runs: "100"

- name: Open an issue when unique bugs were found
  if: steps.pbt.outputs.unique-findings != '0'
  env:
    GH_TOKEN: ${{ github.token }}
  run: gh issue create --title "pbt-sentry findings" --body-file pbt-report.md
```

A complete scheduled example is in
[examples/workflows/pbt-hunt.yml](examples/workflows/pbt-hunt.yml).

### Action inputs

| Input | Required | Default | Meaning |
|---|---|---|---|
| `command` | yes | — | Property-test command, same semantics as the CLI |
| `runs` | no | `50` | Number of seeds |
| `seed-start` | no | `0` | First seed |
| `timeout` | no | `120` | Per-run timeout, seconds |
| `fail-on-finding` | no | `true` | Fail the job on unique findings |
| `report-name` | no | `pbt-report` | Base name for the `.md` / `.json` reports |
| `python-version` | no | `3.12` | Python used to run pbt-sentry itself |

### Action outputs

| Output | Meaning |
|---|---|
| `unique-findings` | Number of unique failure signatures |
| `failed-runs` | Number of individual failing runs |

The Markdown report is uploaded as a build artifact and written to the
job step summary.

## Bundled example (Python + Hypothesis)

[examples/python-hypothesis/](examples/python-hypothesis/) contains a
run-length encoder with a planted edge-case bug (run lengths ≥ 10 are
truncated) and a Hypothesis round-trip property that catches it:

```bash
pip install pytest hypothesis
cd examples/python-hypothesis
pbt-sentry --runs 50 --command "python -m pytest test_rle.py -q -p no:cacheprovider --hypothesis-seed={seed}"
```

Expect many failing runs to collapse into a small number of unique
findings — that collapse is the entire point.

## Go / rapid example (docs only)

The same box works for Go property tests written with
[pgregory/rapid](https://github.com/flyingmutant/rapid). rapid reads its
seed from the `-rapid.seed` flag / `RAPID_SEED` environment; run each
seed as its own `go test` invocation:

```bash
pbt-sentry --runs 200 --timeout 300 \
  --command "go test ./pkg/... -run TestMyProperty -count=1 -rapid.seed={seed}"
```

or, relying on the environment instead of the placeholder:

```bash
pbt-sentry --runs 200 --command "go test ./pkg/... -run TestMyProperty -count=1"
# with RAPID_SEED bridged from PBT_SEED in a tiny wrapper script if needed
```

Dedup works the same way: a failing Go test's normalised output (file
and line kept, addresses/timestamps/seeds stripped) hashes to one
finding no matter how many seeds tripped it.

## Report format

**Markdown** (`pbt-report.md`): a summary table (runs, passed, failed
runs, unique findings) and one section per finding — signature, example
seed, all failing seeds, exit code, the exact reproduction command, and
the output excerpt (last 30 lines of the first example).

**JSON** (`pbt-report.json`): the same data, machine-readable:

```json
{
  "command": "...",
  "runs": 50,
  "passed": 31,
  "failed_runs": 19,
  "unique_findings": 1,
  "findings": [
    {
      "signature": "<sha256>",
      "example_seed": 3,
      "seeds": [3, 7, 11],
      "runs_failed": 3,
      "exit_code": 1,
      "repro_command": "...",
      "output_excerpt": "..."
    }
  ]
}
```

## Guarantees

- **Deterministic seed space.** Seeds are always
  `seed_start .. seed_start+runs-1`; re-running the same hunt covers the
  same space.
- **Exact reproduction.** A finding's repro command is the failing run's
  command with its seed substituted — or, for commands without a
  `{seed}` placeholder, with `PBT_SEED=` / `HYPOTHESIS_SEED=` assignments
  prefixed, so the command is self-contained. Run it and you get the same
  failure, provided the underlying test command is itself deterministic
  for a fixed seed (pin your framework's seed and disable example
  databases/caches that leak between runs, as the bundled example does).
- **Dedup by bug, not by run.** Normalisation strips the seed value, hex
  addresses, ISO timestamps, durations and temp paths — and deliberately
  *keeps* file paths and line numbers, because those identify the bug.

## Honest limits

- pbt-sentry finds failing seeds for properties **you** wrote. It does
  not write properties for you — yet.
- Dedup is only as good as the normalisation: two genuinely different
  bugs that produce identical normalised output tails will group
  together, and one bug whose output tail varies structurally may split
  into two findings. The seeds are always all listed, so nothing is
  hidden.
- One process per seed is simple and reproducible, not fast. For very
  large hunts, shard by `--seed-start` across jobs.
- A timeout is reported as a single `timeout` finding regardless of
  where the run hung.

## Licence

MIT
