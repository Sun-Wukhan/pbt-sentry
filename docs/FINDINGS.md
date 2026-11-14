# Findings: what this method caught in the wild

pbt-sentry packages the workflow behind a series of property-based bug
hunts run by Navid Khan against production open-source projects in
October and November 2026, following the property-based testing
approach of Maaz et al. (arXiv:2510.09907). Every finding below came
from a stated property, was confirmed against the real package, and
was filed upstream as an issue with a fix.

Totals: **8 confirmed findings across Argo CD and Prometheus. Three
fixes merged upstream, two in review, one bug fixed upstream
following our report.** Statuses verified 2026-11-13.

## Argo CD (Go, pgregory/rapid)

| # | Property tested | Bug found | Upstream |
|---|---|---|---|
| 1 | A matcher over user-supplied patterns must never panic | `glob.MatchStringInList` panics on a `"/"` pattern (`slice bounds out of range [1:0]`) | [Issue #30571](https://github.com/argoproj/argo-cd/issues/30571) · [PR #30572](https://github.com/argoproj/argo-cd/pull/30572) **merged** |
| 2 | Error messages must stay well-formed | List generator formats a nil error with `%w`, producing `%!w(<nil>)` corruption and losing the offending key | [Issue #30850](https://github.com/argoproj/argo-cd/issues/30850) · [PR #30855](https://github.com/argoproj/argo-cd/pull/30855) **merged** |
| 3 | Normalisation must be a fixed point: `Normalize(Normalize(x)) == Normalize(x)` | `NormalizeGitURL` is not idempotent: `ssh://git@github.com:22/org/repo.git` normalises twice into two different strings | [Issue #30579](https://github.com/argoproj/argo-cd/issues/30579) · [PR #30598](https://github.com/argoproj/argo-cd/pull/30598) in review |
| 4 | A deny pattern that positively matches must veto | AppProject destination deny (`!name` / `!server`) is ignored when the entry's other identifier matches, permitting destinations that should be denied | [Issue #30588](https://github.com/argoproj/argo-cd/issues/30588) · [PR #30884](https://github.com/argoproj/argo-cd/pull/30884) **merged** |
| 5 | Validation patterns must be anchored | `isValidAction` patterns are unanchored, so strings like `xupdate/y` validate as legitimate project-policy actions | [Issue #30852](https://github.com/argoproj/argo-cd/issues/30852) · [PR #30854](https://github.com/argoproj/argo-cd/pull/30854) in review |

## Prometheus (Go, pgregory/rapid)

| # | Property tested | Bug found | Upstream |
|---|---|---|---|
| 1 | A duration literal must round-trip exactly | Duration expressions lose 1 ms through float64 seconds and truncating conversion: `1s1ms` evaluates as `1s`. Independently confirmed by another reporter: about 0.66% of whole-millisecond values from 1 ms to 1 h are affected (23,602 of 3.6M sampled) | [Issue #20298](https://github.com/prometheus/prometheus/issues/20298) · evaluation fix [PR #20303](https://github.com/prometheus/prometheus/pull/20303) in review · companion printer fix [PR #20392](https://github.com/prometheus/prometheus/pull/20392) **merged** |
| 2 | Escaped values must round-trip | The OpenMetrics parser never unescapes exemplar label values | [Issue #20297](https://github.com/prometheus/prometheus/issues/20297) · fix [PR #20302](https://github.com/prometheus/prometheus/pull/20302) · bug fixed upstream by [PR #20299](https://github.com/prometheus/prometheus/pull/20299) **merged** |

A third Prometheus finding (relabel `labelmap` could create invalid
label names) was confirmed locally but deliberately not filed: an
existing upstream PR already implemented that fix, and filing a
duplicate would have been noise.

## Why this matters for the tool

None of these bugs came from a test case anyone would write by hand.
They came from invariants (never panic, normalisation is a fixed
point, a deny must veto, literals round-trip) checked across
thousands of generated inputs, with the failures grouped so each
unique bug surfaced once. That loop is exactly what pbt-sentry
automates: seed sweep, signature dedup, repro-ready report.
