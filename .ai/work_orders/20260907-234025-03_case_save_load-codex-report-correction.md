# Correction order: 03_case_save_load

## Repository state
- Branch: `app-v1.2-engineering`
- HEAD: `ccebd61e51351fa9072682ad696765deb015b839`
- Working tree: DIRTY — .ai/claude_audits/20260906-115645-01_model_and_limitations-audit-prompt.md, .ai/claude_audits/20260906-115645-01_model_and_limitations-audit.md, .ai/claude_audits/20260906-115645-01_model_and_limitations-audit.transcript.json, .ai/claude_audits/20260906-150728-02_field_units-audit-prompt.md, .ai/claude_audits/20260906-150728-02_field_units-audit.md, .ai/claude_audits/20260906-150728-02_field_units-audit.transcript.json, .ai/claude_audits/20260907-220100-02_field_units-audit-prompt.md, .ai/claude_audits/20260907-220100-02_field_units-audit.md, .ai/claude_audits/20260907-220100-02_field_units-audit.transcript.json, .ai/claude_audits/20260907-224421-02_field_units-audit-prompt.md

## Objective
The implementation for this package is present in the working tree and every
deterministic gate passes against it (Ruff, Ruff format, mypy, compileall and
the full suite). An independent audit accepted the package except for ONE
blocking finding. Your entire task is to close that finding. Do not
restructure or redo anything else.

FINDING B-1 (blocking)
`_number()` in `src/pvt_phase_simulator_ui/case_files.py` accepts any JSON
int/float and calls `float(value)` unconditionally. JSON integers have
unbounded precision in Python's parser, so a case file containing an integer
literal too large for a C double - for example `"temperature_k": 1` followed by
400 zeros - makes `float(value)` raise `OverflowError`.

`OverflowError` does not derive from `ValueError`, so nothing in the chain
catches it: `_case_inputs` -> `_validated_case` -> `load_case` ->
`app._load_case_inputs` -> `app._case_controls`'s `except CaseFileError`. The
running Streamlit app crashes and shows the user a raw traceback.

The auditor reproduced this twice: directly, where `load_case()` raises a bare
`OverflowError: int too large to convert to float` instead of `CaseFileError`;
and end to end through `streamlit.testing.v1.AppTest`, where uploading the
crafted file and clicking "Load case" populates `app.exception` with a full
stack trace rendered to the user.

Every field routed through `_number` is affected: `temperature_k`,
`pressure_pa`, each component's `mole_percent`, and all four sweep bounds
(`start_pa`, `end_pa`, `start_k`, `end_k`).

This directly violates this package's explicit requirement that malformed or
invalid load input must produce a clear, specific, user-facing error message
and never a raw traceback.

WHAT TO DO
- Harden the JSON-to-domain numeric conversion boundary so that any value it
  cannot faithfully convert becomes a `CaseFileError` (via `_schema_error`)
  with a clear, specific, user-facing message. Catch `OverflowError` and
  `TypeError` alongside the existing `ValueError`. Apply the fix at the
  boundary so it covers `_number`, `_integer`, and every field routed through
  them, rather than patching one call site.
- While you are at this boundary, also reject non-finite values. Python's
  `json` module accepts the bare literals `NaN`, `Infinity` and `-Infinity` by
  default, so a case file can currently carry a NaN or infinite temperature,
  pressure, mole percent or sweep bound straight through `float()` without
  error. A non-finite value is not a valid physical input and must be refused
  with the same clear error, never passed toward the scientific engine.
- Keep the change narrowly scoped to this finding. Do not alter the schema
  version, the file format, or any behaviour the audit already accepted.

CONSTRAINTS
- The scientific engine stays frozen. Nothing under `src/pvt_phase_simulator/`,
  `data/`, `docs/validation/` or `tests/golden_master/` may change.
- No thermodynamic relation may be implemented or restated in the application
  layer.
- Do not weaken or delete any existing test.

TESTS
- Add regression coverage for an out-of-range JSON integer literal in EACH
  class of numeric field: temperature, pressure, a component mole percent, and
  a sweep bound. Assert a `CaseFileError` with a useful message, not a crash.
- Add coverage for `NaN`, `Infinity` and `-Infinity` literals being refused.
- Add at least one end-to-end assertion, in the style the auditor used, that
  the running app surfaces a clean error rather than populating
  `app.exception` with a traceback.
- Avoid brittle hard-coded one-ULP formatted float strings.

TESTING POLICY FOR THIS RUN
Run focused tests only - the case-file tests and the specific app test you
touch, plus Ruff and mypy if useful. Do NOT run the entire pytest suite for
reassurance. The orchestrator runs the authoritative full-suite verification
after you finish, and duplicating it costs a great deal of wall-clock time.

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
