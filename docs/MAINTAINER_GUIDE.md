# Maintainer guide

For a future maintainer or a new Claude session. It says how to work on
OpenPhase day to day and how to release it. The rules in `CLAUDE.md` come
first; this guide explains how to follow them.

## How the project is run

- GitHub is the only shared state. The owner works from more than one account
  (a desktop session and a web session), and none can see another's chat. So
  every result belongs in a commit, a PR or a document. Nothing lives only in a
  chat.
- The **Session log** at the end of `docs/PROJECT_STATUS.md` is the hand-over
  between sessions. Read only its latest two or three entries when you start.
  Add one short dated entry, at the top, in every PR.
- Use one branch and one PR per task. Merge only after CI is green, with a
  normal merge commit; never squash or force-push. If `master` moved, merge
  `master` into the branch. When the Session log conflicts, keep both entries,
  newest first.

## Setup

You need Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

```bash
uv run streamlit run streamlit_app.py
```

Daily commands, the same gates CI runs:

```bash
uv lock --check
```

```bash
uv run ruff check . && uv run ruff format --check .
```

```bash
uv run mypy
```

```bash
uv run pytest -q tests/test_<area>.py
```

```bash
uv run pytest -q -n auto
```

The full suite takes about 4–5 minutes on 4 cores; CI takes longer. Run only
the related tests for a small change. Run the full suite when you touch shared
app code or anything that calls the engine.

## What CI runs

`.github/workflows/quality.yml`, on every push and PR:

1. `uv sync --locked` and `uv lock --check`.
2. Ruff, Ruff format and mypy (`src` and `app`).
3. `compileall` and an import smoke of the app.
4. The real-browser test `tests/test_app_browser.py` (Chromium), with
   screenshots uploaded as evidence.
5. The full suite with pytest-xdist (`-n auto --dist loadfile`), with the
   browser test excluded because step 4 already ran it.
6. `tools/streamlit_smoke.py`: Streamlit starts and answers its health
   endpoint.
7. A run with only the deployed dependencies (`uv sync --no-dev --locked`),
   then `tools/streamlit_smoke.py` and `tools/deploy_check.py` in it.
8. A check that verification left the working tree unchanged.

CI never deploys and needs no secrets.

## Adding a test

- Put it in `tests/test_<area>.py`. Prefer a new file over editing a long one,
  especially files an open PR also changes.
- **Numbers shown to users or students** (the app, Learn mode, labs, README,
  release notes, `docs/STATE_OF_OPENPHASE.md`) must be recomputed from the
  engine or from a committed record by a test. Examples:
  `tests/test_validation_claims.py`, `tests/test_teaching_lab_05.py` and
  `tests/test_release_notes.py`. Commit every CSV or JSON file a test reads in
  the same push.
- **App tests** use Streamlit's AppTest. The helpers in `tests/_robustness.py`
  set inputs, press buttons and check that no generic failure message or
  logged error appeared.
- **Real-browser tests** use Playwright's waiting `expect(...)`, never a fixed
  sleep followed by a read.
- Tests run in parallel, so never write into the repository from a test. Use
  `tmp_path`.
- **For a bug fix**, first show the new test failing on the old code, then
  passing on the fixed code, and say so in the PR.
- Never loosen a tolerance, edit an expected number, regenerate a baseline or
  mark a test xfail to get green. If a test blocks you, it is probably right.

## The frozen engine and engine proposals

These paths are frozen:
- `src/pvt_phase_simulator/`
- `data/`
- `docs/validation/`
- `docs/EXPERIMENTAL_VALIDATION.md`
- `tests/golden_master/`

Change them only with the owner's explicit approval of that specific change.

If you find an engine problem:

1. Write a reproducer script in `tools/` that shows it with the engine's own
   status and reason.
2. Add a proposal to `docs/ENGINE_CHANGE_PROPOSALS.md` with the next free
   P-number. Give its status ("proposed, awaiting owner decision"), the
   question, the evidence (the reproducer's output), the exact suggested
   change, and what it would do to the validation record and the golden
   master.
3. Do not implement it.

Once the owner approves, prove the effect:
- **A change that must not alter results** (like P9): show every result is
  byte-identical with `tools/engine_fingerprint.py` (801 cases, compare mode)
  and the full suite.
- **A change that alters results:** regenerate the record with
  `tools/run_module17_validation.py` and explain every changed value.

## Releasing a version

The web sessions' network proxy blocks pushing tags and `gh release`, so
**steps 6 and 7 must be done from the desktop**.

1. Branch `release-vX.Y.Z` from fresh `master`.
2. Set `version = "X.Y.Z"` in `pyproject.toml`, then run `uv lock`.
3. Write `docs/release_notes/v<X.Y.Z>.md`, listing only merged work, with
   honest known limits. Add a test, like `tests/test_release_notes.py`, that
   recomputes every number the notes quote.
4. Add a `CHANGELOG.md` section and update the version wording in
   `docs/STREAMLIT_APPLICATION.md`.
5. Open the PR as a draft titled "Release vX.Y.Z (awaiting owner approval)".
   Merge it only after the owner approves and CI is green.
6. Once **master CI on the merge commit** is green, tag that commit:
   ```bash
   git tag -a vX.Y.Z <merge-commit> -m "OpenPhase vX.Y.Z"
   ```
   ```bash
   git push origin vX.Y.Z
   ```
7. Publish the release from the notes:
   ```bash
   gh release create vX.Y.Z --verify-tag --title "OpenPhase vX.Y: ..." --notes-file docs/release_notes/v<X.Y.Z>.md
   ```
8. Check the public app (next section) and record the release in the Session
   log.

## The public app (Streamlit Community Cloud)

- The app runs from `master`, with `streamlit_app.py` as the entry point and
  `uv.lock` as the dependency source. No secrets are stored.
- It picks up `master` when it wakes from sleep. Otherwise the owner reboots it
  at <https://share.streamlit.io>.
- The steps and what to check afterwards are in `docs/STREAMLIT_APPLICATION.md`
  under "Rebooting the public app and what to check afterwards".

## Finishing the butanes

PR 47 ("Butanes: DRAFT, do not merge until Table 5 values arrive") holds
everything except the six published constants. Its description lists the
owner's remaining steps:

1. Enter the Yang & Richter (2025) Table 5 values in the values file that
   branch adds (data/butanes_table5_values.json).
2. Run `uv run python tools/admit_butanes.py --report admission.json`.
3. Run the full suite.
4. Update `docs/EXPERIMENTAL_VALIDATION.md`.

The plan is `docs/BUTANES_ADMISSION_PLAN.md`.

## Troubleshooting

- **"Access is denied" or a locked file in `.venv` on Windows/OneDrive.**
  OneDrive held a file open during the sync. Run `uv sync` again, or pause
  OneDrive syncing for the project folder.
- **Playwright cannot find a browser.** CI installs Chromium with
  `uv run playwright install --with-deps chromium`. Locally, either do the same
  or point the tests at an installed Chrome with
  `OPENPHASE_BROWSER_EXECUTABLE=/path/to/chrome`;
  `tests/test_app_browser.py` also looks for `google-chrome` and `chromium` on
  the PATH.
- **AppTest passes but the real page is wrong.** AppTest reads the content of
  collapsed expanders as if it were visible, and lists expanders that have an
  icon under `status`, not `expander`. A table inside a collapsed section
  passed AppTest while users could not see it. Check anything that must be
  visible with the real-browser test.
- **`CacheReplayClosureError`.** A function decorated with `st.cache_resource`
  or `st.cache_data` drew into an element created outside it. On a cache hit,
  Streamlit replays the drawing, and the outside element no longer exists.
  This broke the repeated sweep once. Keep cached functions free of Streamlit
  elements: compute inside the cache and draw outside it.
- **The first phase envelope is slow.** This is engine time: about one to
  three minutes from click to plot. A repeat of the same case is answered from
  the cache. P10 in `docs/ENGINE_CHANGE_PROPOSALS.md` describes faster options
  that change results; they wait for the owner.
- **Regenerated records differ in the last digits on another machine.**
  Floating-point results can change in the last bit between machines. Compare
  two runs on the same machine before you conclude anything changed.
