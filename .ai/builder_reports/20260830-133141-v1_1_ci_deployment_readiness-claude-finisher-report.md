# Package completion report — v1_1_ci_deployment_readiness

- **Builder of record:** **Claude** (Codex unavailable — usage quota)
- **Independent review:** **NOT PERFORMED.** See "Audit debt".
- **Risk:** LOW. Three files, no source or scientific change.

## What was implemented

| File | Change |
|---|---|
| `.github/workflows/quality.yml` | new — 13-step Ubuntu / Python 3.12 workflow installing from the locked graph and running every authoritative gate |
| `README.md` | prerequisites, portable health-smoke command, and a "Continuous verification and deployment status" section |
| `docs/STREAMLIT_APPLICATION.md` | prerequisites, portable smoke invocation with the Windows equivalent and `--timeout` guidance, and a deployment-status section |

## Workflow design

Triggers on push, pull request and manual dispatch, with `contents: read`
permissions only and concurrency cancellation. Installs uv, pins Python 3.12,
then runs: `uv lock --check`, Ruff, Ruff formatting, mypy over `src` and `app`,
`compileall`, application import smoke, the full test suite, the localhost
Streamlit health smoke, and a working-tree-unchanged assertion.

Deliberately absent: any secret, any badge, any deployment, publication or
release automation, and any paid infrastructure.

## Review of my own diff

Reviewing my own work surfaced one real defect, which I fixed before committing:

- **Undocumented flags in the install step.** I first wrote
  `uv sync --locked --all-extras --dev`. `--dev` does not appear in
  `uv sync --help` (only `--no-dev`, `--group`, `--all-groups`) and
  `--all-extras` is a no-op because this project defines no
  `[project.optional-dependencies]` — it uses PEP 735 `[dependency-groups]`.
  I confirmed by dry-run that `uv sync --locked` alone resolves the same 83
  packages including pytest, Ruff and mypy, and that `--no-dev` removes them,
  proving the dev group is included by default. Simplified to `uv sync --locked`.

Other checks:

- **Portability.** Verified before targeting Ubuntu: no `.venv/Scripts` path, no
  drive letter, no `.exe`, no `os.system` in shipped code; tests use
  `sys.executable`. The only backslashes are `\n` escapes.
- **Documented commands are verified, not assumed.** `uv run python
  tools/streamlit_smoke.py` was executed: health check passed on ephemeral port
  57002, exit 0, and no listening Streamlit port remained afterwards.
- **No unearned status claims.** No CI badge was added. The documentation
  describes what the workflow *does*, never that it has passed — it has never
  run, because that requires a push to GitHub.
- **Smoke headroom.** `tests/test_app_release.py` allows the smoke 20 s. That
  file is outside this package's `allowed_files`, so I did not touch it; instead
  the workflow's explicit smoke step uses `--timeout 60` and a 5-minute step
  ceiling for cold runners. Recorded as a follow-up rather than an out-of-scope edit.

## Verification (machine-generated, regenerated against the final file)

`.ai/verification/*-v1_1_ci_deployment_readiness-claude-finisher.json`

Changed files: exactly `.github/workflows/quality.yml`, `README.md`,
`docs/STREAMLIT_APPLICATION.md`. All eight gates PASS; scope PASS; protected
artifacts 4/4 unchanged; `git diff --check` clean.

## Known unverifiable claim

**The workflow has never executed.** GitHub Actions cannot run locally, so
`astral-sh/setup-uv@v5`, `actions/checkout@v4` and the runner behaviour are
unverified until the branch is pushed. The YAML parses and every command in it
was executed successfully on this machine, but the first CI run is the real test.

## Audit debt

Built and verified by the same agent. `commit_policy` is `AFTER_AUDIT` and
`audit_policy` is `IMMEDIATE`; neither was satisfied. Recorded in
`deferred_independent_audits`. **Codex must perform the independent review.**
