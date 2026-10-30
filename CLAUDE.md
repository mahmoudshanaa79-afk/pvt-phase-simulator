# Working on OpenPhase

OpenPhase (repo `pvt-phase-simulator`) is a Peng–Robinson phase-behaviour simulator
with a public Streamlit app. The owner works from **two Claude accounts**, a
desktop session and a web session. Neither can see the other's chat or memory,
so **GitHub is the only shared state.**

## Do these automatically, without being asked

The owner may forget to ask for any of this. Do it anyway.

1. **Catching up (first message of a session).** Run `git fetch` and update
   from `origin/master`. Read only the latest two or three entries of the
   "Session log" at the end of `docs/PROJECT_STATUS.md`. Do **not** re-read the
   whole project or review it from scratch. Open other docs only when the task
   needs them. If the owner gives no task, propose the log's latest "Next" item.
2. **Work.** Use one branch per task, named for the task. Never commit to
   `master` directly.
3. **Finishing each task.** Do this before reporting the task done, not only at
   the end of the session, because the owner may simply close the window:
   - commit and push the branch;
   - open or update its PR;
   - in the same PR, add one short dated entry to the top of the "Session log"
     with the account (desktop or web), what was done, the open PRs and what
     comes next.
4. **Merging.** Merge only after CI passes. Use a normal merge commit; never
   squash or force-push. If `master` moved, merge `master` into the branch.

## Saving tokens (defaults)

- Run only the tests related to the change. Leave the full suite (about 20
  minutes) to CI unless the owner asks for it, or the change touches shared
  app or engine code.
- Find code with targeted searches and read only the parts you need, not whole
  files or directories.
- Skip browser and visual checks unless the change is visual.
- Keep replies short: what changed, the evidence, what needs the owner.
- When a session has grown long, or the task changes, suggest starting a new
  session. The session log carries the context across.
- For a small task (wording, docs, a one-line fix), mention once that a cheaper
  model is enough.
- Avoid working on the same files as another active session. Check open PRs
  first (`gh pr list`).

## Rules

- **The scientific engine is frozen.** That covers `src/pvt_phase_simulator/`,
  `data/`, `docs/validation/`, `docs/EXPERIMENTAL_VALIDATION.md` and
  `tests/golden_master/`. Do not edit them without the owner's explicit
  approval of that specific change. Investigate read-only and write up a
  proposal instead (see `docs/ENGINE_CHANGE_PROPOSALS.md`).
- Never make a test pass by loosening a tolerance, editing expected numbers,
  regenerating a baseline or weakening a gate.
- Never hide a solver failure, non-convergence or inconclusive result. Report
  the engine's own reason.
- Any number shown to users or students (Learn mode, teaching labs) must be
  recomputed from the engine by a test.
- Ask the owner before a release or a tag.
- Do not raise or change licensing or ownership. The owner has parked that
  question.
- When reporting, separate the tests you ran yourself from results you only
  saw in CI.

## Reference

- Status, open decisions and the session log: `docs/PROJECT_STATUS.md`.
- Engine proposals P1–P5: `docs/ENGINE_CHANGE_PROPOSALS.md`.
- Dew findings: `docs/DEW_INVESTIGATION.md`.
- Commands:

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest -q tests/<relevant_test_file>.py
uv run streamlit run streamlit_app.py
```

- The real-browser test (`tests/test_app_browser.py`) needs Chromium or a local
  Chrome. Only the desktop session can show the app in a browser.
- The public app runs on Streamlit Community Cloud from `master`. It picks up
  `master` when it wakes from sleep; otherwise the owner reboots it from
  share.streamlit.io.
