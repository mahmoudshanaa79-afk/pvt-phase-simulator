# Correction order: 03_case_save_load

## Repository state
- Branch: `app-v1.2-engineering`
- HEAD: `ccebd61e51351fa9072682ad696765deb015b839`
- Working tree: DIRTY — .ai/claude_audits/20260906-115645-01_model_and_limitations-audit-prompt.md, .ai/claude_audits/20260906-115645-01_model_and_limitations-audit.md, .ai/claude_audits/20260906-115645-01_model_and_limitations-audit.transcript.json, .ai/claude_audits/20260906-150728-02_field_units-audit-prompt.md, .ai/claude_audits/20260906-150728-02_field_units-audit.md, .ai/claude_audits/20260906-150728-02_field_units-audit.transcript.json, .ai/claude_audits/20260907-220100-02_field_units-audit-prompt.md, .ai/claude_audits/20260907-220100-02_field_units-audit.md, .ai/claude_audits/20260907-220100-02_field_units-audit.transcript.json, .ai/claude_audits/20260907-224421-02_field_units-audit-prompt.md

## Objective
Close the following review or verification findings. Change nothing else, and do not weaken any test or tolerance to make a finding disappear.

- **B-1** (severity B): case_files.py's _number() calls float() on any JSON int/float without catching OverflowError; a case file containing an out-of-range JSON integer literal in any numeric field (temperature_k, pressure_pa, mole_percent, or any sweep bound) raises an uncaught OverflowError that propagates through load_case -> app._load_case_inputs and is not caught by app._case_controls's `except CaseFileError`, crashing the running Streamlit app with a raw traceback shown to the user -- reproduced directly and via AppTest end-to-end -- in direct violation of the package's explicit 'never a raw traceback' requirement for malformed/invalid load input.

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
