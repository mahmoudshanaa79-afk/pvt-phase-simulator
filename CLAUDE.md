# Working on OpenPhase

OpenPhase (repo `pvt-phase-simulator`) is a Peng–Robinson phase-behaviour simulator
with a public Streamlit app. The owner works with Claude directly. There is no
separate builder agent.

## Start here

Read these before proposing work. They say where the project stands and what is
waiting on a decision.

- `docs/PROJECT_STATUS.md`: what exists, the evidence behind it, open decisions
  and next steps.
- `docs/ENGINE_CHANGE_PROPOSALS.md`: proposed engine changes P1–P5, with exact
  code. None of them is applied.
- `docs/DEW_INVESTIGATION.md`: why the CH4+C3 dew error is mostly not model
  error.

## Rules

- **The scientific engine is frozen.** That covers `src/pvt_phase_simulator/`,
  `data/`, `docs/validation/`, `docs/EXPERIMENTAL_VALIDATION.md` and
  `tests/golden_master/`. Do not edit them without the owner's explicit decision
  for that specific change. Investigate read-only and write up a proposal
  instead.
- Never make a test pass by loosening a tolerance, editing expected numbers,
  regenerating a baseline or weakening a gate.
- Never hide a solver failure, non-convergence or inconclusive result. Report
  the engine's own reason.
- Any number shown to users or students (Learn mode, teaching labs) must be
  recomputed from the engine by a test.
- Do not raise or change licensing or ownership. The owner has parked that
  question.

## Workflow

- Branch, then open a PR to `master`, wait for CI to pass, and merge with a
  normal merge commit. Never squash and never force-push.
- Ask the owner before a release or a tag.
- When reporting, separate the tests you ran yourself from results you only
  saw in CI.

## Commands

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest -q --ignore=tests/test_app_browser.py
uv run streamlit run streamlit_app.py
```

The full suite takes about 20 minutes. The real-browser test
(`tests/test_app_browser.py`) needs Chromium, from `uv run playwright install
chromium` or a local Chrome.

## Deployment

The public app runs on Streamlit Community Cloud from `master`. It does not
reliably redeploy on push. It picks up `master` when it wakes from sleep;
otherwise the owner reboots it from share.streamlit.io.
