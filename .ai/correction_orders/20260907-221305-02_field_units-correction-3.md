# Correction order: 02_field_units

## Repository state
- Branch: `app-v1.2-engineering`
- HEAD: `cd908da958d3a616a22c58735ae3f1b4d2c6bb94`
- Working tree: DIRTY — .ai/claude_audits/20260906-115645-01_model_and_limitations-audit-prompt.md, .ai/claude_audits/20260906-115645-01_model_and_limitations-audit.md, .ai/claude_audits/20260906-115645-01_model_and_limitations-audit.transcript.json, .ai/claude_audits/20260906-150728-02_field_units-audit-prompt.md, .ai/claude_audits/20260906-150728-02_field_units-audit.md, .ai/claude_audits/20260906-150728-02_field_units-audit.transcript.json, .ai/claude_audits/20260907-220100-02_field_units-audit-prompt.md, .ai/claude_audits/20260907-220100-02_field_units-audit.md, .ai/claude_audits/20260907-220100-02_field_units-audit.transcript.json, .ai/claude_builds/20260906-123830-02_field_units-claude-report.md

## Objective
Close the following review or verification findings. Change nothing else, and do not weaken any test or tolerance to make a finding disappear.

- **C-1** (severity B): result_is_stale() compares ScientificInputs.signature with exact float equality, but current_inputs is recomputed each rerun by round-tripping the field value through the selected display unit (K<->degF, Pa<->psi/bar); this round trip is not bit-exact for ~50% of realistic temperature values (verified directly against validate_scientific_inputs, e.g. 373.7993794602593 K -> degF -> 373.79937946025933 K), so merely switching the temperature (or pressure) display unit with no physical change frequently marks an already-calculated, unchanged result as stale and disables its downloads. This directly contradicts this PR's own new documentation ('does not... make a current scientific result stale') and is not caught by the existing regression test because that test's fixed 300 K/5 MPa case happens to round-trip exactly through every supported unit.

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
