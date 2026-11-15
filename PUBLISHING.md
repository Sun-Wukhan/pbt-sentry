# Publishing pbt-sentry to PyPI

Status (14 Nov 2026): the distribution name `pbt-sentry` is **available**
on PyPI (checked: 404). Version 0.1.1 in `pyproject.toml` has never been
published, so it can go up as-is. The 0.1.1 sdist and wheel build cleanly
and pass `twine check`.

Publishing uses **Trusted Publishing** (OIDC) — no API token is stored
anywhere. One-time setup is the only step that needs the project owner:

## One-time setup (owner, ~2 minutes)

1. Sign in to [pypi.org](https://pypi.org) (create the account and enable 2FA
   if you have not already).
2. Go to **Publishing → Add a pending publisher** ("Your projects" →
   Publishing, or https://pypi.org/manage/account/publishing/).
3. Enter exactly:
   - **PyPI project name:** `pbt-sentry`
   - **Owner:** `Sun-Wukhan`
   - **Repository:** `pbt-sentry`
   - **Workflow name:** `publish.yml`
   - **Environment name:** `pypi`
4. Save. Nothing else is needed — no secrets go into GitHub.

## Every release after that

Create a GitHub Release from the version tag (or run the
**Publish to PyPI** workflow manually from the Actions tab).
`.github/workflows/publish.yml` builds the sdist/wheel and publishes them
via OIDC. Bump `version` in `pyproject.toml` and `__version__` first —
PyPI never accepts the same version twice.

## Local build (already verified for 0.1.1)

```bash
pip install build twine
python -m build
twine check dist/*
```
