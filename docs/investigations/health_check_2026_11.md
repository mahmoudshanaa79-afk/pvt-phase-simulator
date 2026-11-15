# Health check, November 2026

Web session, 15 November 2026. The whole project was checked on fresh
`master` (`d0f2396`, after v1.7.0 and Lab 5) before the final web session's
changes. Each non-engine defect found got its own small PR with a test that
fails on the old code. The engine is frozen and was only read and called.

## Summary

| Check | Result | Evidence | Action |
|---|---|---|---|
| 2.1 Locked install | Pass | `uv sync --locked`: exit 0; `uv lock --check`: exit 0 | None |
| 2.1 Lint and format | Pass | `uv run ruff check .`: all checks passed; `uv run ruff format --check .`: 253 files already formatted | None |
| 2.1 Types | Pass | `uv run mypy`: no issues in 73 files; `uv run mypy src app` (CI): no issues in 78 files | None |
| 2.1 Full suite | Pass | `uv run pytest -q -n auto`: **1861 passed in 245 s** (4 cores) | None |
| 2.2 Coverage | 89.1 % (lines 91.9 %, branches 79.9 %) | `pytest -n auto --cov=src --cov-report=term-missing` (16.5 min with coverage) | Weakest user-facing modules listed below; property tests added (PR 57) |
| 2.3 Deployed environment | Pass | `uv sync --no-dev --locked` into a separate venv (no pytest present); `tools/streamlit_smoke.py`: health check passed; `tools/deploy_check.py`: every page renders and RUN FLASH gives a result | None |
| 2.4 Real-browser test | Pass | `tests/test_app_browser.py`: 2 passed (Chromium), in the full-suite run | None |
| 2.4 Browser walk, every page | Pass | New `tools/browser_walk.py`; results below | Committed so the desktop can rerun it |
| 2.5 Bad input and edge cases | Pass, with two weak messages | Probe of every case listed below | Fixed in PR 55 (case-file and all-zero messages say how to fix them) |
| 2.5 Diagnostic codes in plain language | Gap | The app explained 4 of the engine's 42 diagnostic codes | Fixed in PR 58 (glossary of all 42 on the Diagnostics page, guarded by a test that reads the codes from the engine) |
| 2.6 Numbers in the documents | Pass after adding tests | README, user guide, v1.6.0 and v1.7.0 notes, Labs 1–5, Learn mode, status page | New `tests/test_status_claims.py`, `tests/test_state_of_openphase.py` |
| 2.6 Stale wording | 3 stale lines | "Last updated 9 November", "Four labs", an untested test count in `PROJECT_STATUS.md` | Fixed in PR 56 |
| 2.6 Document references | Pass | `tests/test_docs_references.py` | `docs/README.md` now indexes every current document (PR 56) |
| 2.7 v1.7.0 release | Recorded | Tag `v1.7.0` → `923d492`; GitHub release published 15 Nov 2026 | Session log (PR 55) |

## 2.2 Coverage

Line plus branch coverage by package:

| Package | Coverage |
|---|---:|
| `pvt_phase_simulator_ui` (app) | 93.1 % |
| `pvt_phase_simulator_validation` (validation framework) | 87.4 % |
| `pvt_phase_simulator` (engine, frozen) | 88.4 % |

Weakest modules that matter to users:

| Module | Coverage | Note |
|---|---:|---|
| `pvt_phase_simulator_ui/units.py` | 86.8 % | Error branches for unknown units and non-finite values. Covered by the property tests in PR 57. |
| `pvt_phase_simulator_ui/validation_evidence.py` | 87.9 % | Fallback branches when an evidence file is missing. |
| `pvt_phase_simulator_ui/case_files.py` | 89.1 % | Schema-error branches. Round trip and corrupted-field properties added in PR 57. |
| `pvt_phase_simulator_validation/report/__main__.py` | 0 % | The report's command-line entry point is never run by a test. |
| `pvt_phase_simulator_validation/sensitivity.py` | 76.5 % | Error branches of the sensitivity check. |

Engine gaps (reported only, no engine code added):
- `experimental_validation.py`: 74.9 %, mostly the record-generation paths that only `tools/run_module17_validation.py` runs;
- `eos/criticality.py`: 79.8 %;
- `eos/critical_point.py`: 85.7 %;
- `plotting.py`: 84.4 %.

## 2.4 Browser walk

`uv run python tools/browser_walk.py --output walk-evidence` drives the app in
Chromium on localhost. On this branch **31 of 31 checks passed in 110 s**:

- app loads with Overview and the Start-here box;
- Learn mode on every page; all 5 lab links point to files in `docs/teaching/`;
- RUN FLASH twice;
- the volume-translation table is visible when switched on;
- Overview downloads: CSV (74 rows), JSON and the HTML report all parse;
- RUN PHASE ENVELOPE twice, and the envelope survives a page switch;
- RUN CRITICAL SOLVER and RUN CRITICALITY MAP, twice each;
- RUN SWEEP twice; the sweep CSV (22 rows) and JSON parse;
- GENERATE VALIDATION FIGURES twice;
- Diagnostics: the raw envelope download parses, and the code glossary is shown;
- every page keeps its results after a round trip;
- a kij entry is stated on Overview and removed again;
- save, reload the browser, load the case, rerun: the same flash numbers;
- a refused case file and an all-zero composition show how to fix them;
- no sideways scroll at 390 px on any of the 6 pages;
- no page errors and no blocking console errors.

The walk's first version waited for the label of a collapsed status widget,
which never becomes visible text. That was a mistake in the script, not an app
defect, and the script now waits for the result content and for Streamlit to
be idle.

## 2.5 Bad input and edge cases

| Input | Result |
|---|---|
| T = 49 K, T = 1001 K | Refused: "Temperature must be between 50 K and 1000 K, the application's supported input range." |
| P = 0.1 Pa, P = 1001 MPa | Refused: "Pressure must be between 1 Pa and 1e+09 Pa (1e-06 MPa to 1000 MPa), …" |
| Composition totalling 90 or 110 mol % | Refused: "Composition must total 100 mol %. Values are not automatically normalized." |
| Negative composition | Refused: "Composition values cannot be negative." |
| All zero | Refused. The message said only "Composition total must be greater than zero."; **now adds "Enter a positive mol % for at least one component."** (PR 55) |
| Single component (0/0/100) | Accepted; flashes as a pure fluid |
| kij = −5, kij = 10⁶ | Refused: "kij C1–C3 must be between -0.10 and 0.20." |
| Sweep of 0, 1 or 10 000 points | Refused: "Number of points must be between 2 and 60." |
| Sweep with start = end | Refused: "Sweep start and end must differ." |
| Reversed sweep (20 → 1 MPa) | Accepted; runs in the order given |
| Case file: not JSON, empty, binary | Refused: "Case file is not valid JSON." / "not valid UTF-8 JSON." |
| Case file: a list, missing keys, a field of the wrong type | Refused, naming the field (for example "inputs.temperature_k must be a number.") |
| Case file: version 0.9.0 or 9.0.0 | Refused: "Unsupported case schema version '0.9.0'; supported versions are 1.0.0, 1.1.0." |
| Every refused case file | **Now adds "Choose a .json file made with Save case in OpenPhase, or enter the inputs in the form instead."** (PR 55) |

None showed a traceback. Engine failures keep the engine's own status and
reason; `tests/test_app_robustness*.py` already checks this for every action.

## 2.6 Documentation truth

- **Already tested:** the README evidence table (`test_validation_claims.py`),
  Labs 1–5 (one test file each), Learn mode exercises, the v1.7.0 notes
  (`test_release_notes.py`) and the bubble AARD in the status page.
- **Newly tested:**
  - `tests/test_status_claims.py` covers the status page's current-state
    numbers: critical point, envelope survey 14 of 16, dew composition 22 of 23
    and 16 of 16, the bubble counts after P7, the CH4+C2 dew after P8, the
    fitted kij and the input range. It also covers the v1.6.0 notes' numbers
    that still describe the record, and the lab count in every guide.
  - `tests/test_state_of_openphase.py` covers the new faculty summary.
- The "before" side of a change in the status page's decision table (for
  example "11 → 17") describes the record before an approved engine change.
  It is history and cannot be recomputed from the current record; only the
  "after" side is checked.
