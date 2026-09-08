# Correction order: 02_field_units

## Repository state
- Branch: `app-v1.2-engineering`
- HEAD: `cd908da958d3a616a22c58735ae3f1b4d2c6bb94`
- Working tree: DIRTY — .ai/claude_audits/20260906-115645-01_model_and_limitations-audit-prompt.md, .ai/claude_audits/20260906-115645-01_model_and_limitations-audit.md, .ai/claude_audits/20260906-115645-01_model_and_limitations-audit.transcript.json, .ai/claude_audits/20260906-150728-02_field_units-audit-prompt.md, .ai/claude_audits/20260906-150728-02_field_units-audit.md, .ai/claude_audits/20260906-150728-02_field_units-audit.transcript.json, .ai/claude_builds/20260906-123830-02_field_units-claude-report.md, .ai/claude_builds/20260906-123830-02_field_units-claude-report.transcript.json, .ai/claude_builds/20260906-151327-02_field_units-claude-report.md, .ai/claude_builds/20260906-151327-02_field_units-claude-report.transcript.json

## Objective
The implementation for this package is already present in the working tree and
is green: Ruff, Ruff formatting, mypy, compileall and the full suite (1255
passed) all succeed against it, the change is inside package scope, and the
protected scientific artifacts are untouched.

An independent audit accepted the package except for ONE blocking finding, and
your entire task is to close that finding. Do not restructure, rewrite or
re-do anything else.

FINDING B-1
`_presentation_figure` in `src/pvt_phase_simulator_ui/views.py` converts
`trace.x`, `trace.y` and `trace.hovertemplate` into the selected presentation
units, but never converts `trace.text`. The frozen plotting module bakes raw
K and Pa values into `trace.text` when it adds the certified critical point
(`_add_critical_point` / `_critical_hover`). The result is that whenever a
certified critical point is overlaid and the user has selected any non-SI unit,
the marker's hover tooltip still reports Kelvin and Pascals while every other
number on the chart is in the chosen units.

WHAT TO DO
- Convert the certified-critical-point values carried in `trace.text` to the
  currently selected presentation units, consistently with how x, y and the
  hovertemplate are already converted.
- Internal and scientific values stay SI. This is a presentation-boundary fix
  only. Do not touch any thermodynamic calculation, and do not modify anything
  under src/pvt_phase_simulator/.
- Keep the change narrowly scoped to what the finding describes.

TESTS
- Add focused regression coverage proving the tooltip is converted under
  non-SI presentation units.
- Do NOT hard-code a full formatted float string as the expected value. A
  previous attempt asserted `T=119.179252975` against an actual
  `119.179252974` and failed on the last digit. Build expected values with the
  application's own unit conversion and presentation formatter, or assert the
  converted quantity and its unit semantically, so the test cannot break on a
  one-ULP difference.

Finish by emitting the required <ORCHESTRATOR_RESULT> block. A reply without it
is treated as a failure and is never read as success.


## Allowed files
  - `src/pvt_phase_simulator_ui/**`
  - `tests/test_app_*.py`
  - `docs/STREAMLIT_APPLICATION.md`

## Files you must NOT modify
  - `src/pvt_phase_simulator`
  - `data`
  - `docs/validation`
  - `tests/golden_master`

## Protected artifacts — never regenerate
  - `tests/golden_master/baseline.csv` — SHA256 530C667AA70EF1EA182F4EDB98624A0A9B9908F149354276CDAC44A87EA7D2BE
  - `data/component_properties.csv` — SHA256 C6F6BA9AE9C2F4C7F257BBC09A75DF0D7065255868AA46BF3E8C81AC5A8B9B3A
  - `docs/validation/module17_vle_validation.csv` — SHA256 B14728D51AAC06AF38FC4F4E5F408942B253FEBE32D3E12EC26E9623CFA42482
  - `docs/validation/module17_vle_validation_summary.json` — SHA256 5B120B77BF05567FCC6A0EE0D0054C6D1DEBA35FE26A7C837352C92017D24870

## Scientific invariants that must continue to hold
  - The scientific engine is frozen: no file under src/pvt_phase_simulator/, data/, docs/validation/ or tests/golden_master/ may change.
  - No thermodynamic relation may be implemented, restated or approximated in the application layer.
  - Unavailable quantities are reported as unavailable and never fabricated or interpolated.
  - Structured failures remain failures; only CriticalPointStatus.CONVERGED is a certified critical point.

## Required tests
  - `.venv/Scripts/python.exe -m pytest -q`

## Required quality gates
  - `.venv/Scripts/python.exe -m ruff check .`
  - `.venv/Scripts/python.exe -m ruff format --check .`
  - `.venv/Scripts/python.exe -m mypy src app`
  - `.venv/Scripts/python.exe -m compileall -q src app`

## Rules
- Do NOT weaken a test to make it pass. Do not loosen a tolerance, edit an
  expected value to match output, delete a test, swallow an exception, or
  regenerate a baseline. Any of those is a blocking failure.
- Do NOT commit, stage, reset, or clean. The orchestrator owns git.
- Do NOT write your own audit — an independent auditor reviews your work.
- Keep the change within the objective; no unrelated cleanup.

## Required final output

End your reply with exactly one machine-readable block:

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "<what you ran and what it reported>",
  "files_changed": ["<path>", "..."],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>

`status` must be COMPLETE, BLOCKED or FAILED. The orchestrator re-runs every
check locally, so an inaccurate claim here will simply be caught.
