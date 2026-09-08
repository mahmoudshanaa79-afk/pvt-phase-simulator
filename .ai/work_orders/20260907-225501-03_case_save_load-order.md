# Work order: 03_case_save_load

## Repository state
- Branch: `app-v1.2-engineering`
- HEAD: `ccebd61e51351fa9072682ad696765deb015b839`
- Working tree: DIRTY — .ai/claude_audits/20260906-115645-01_model_and_limitations-audit-prompt.md, .ai/claude_audits/20260906-115645-01_model_and_limitations-audit.md, .ai/claude_audits/20260906-115645-01_model_and_limitations-audit.transcript.json, .ai/claude_audits/20260906-150728-02_field_units-audit-prompt.md, .ai/claude_audits/20260906-150728-02_field_units-audit.md, .ai/claude_audits/20260906-150728-02_field_units-audit.transcript.json, .ai/claude_audits/20260907-220100-02_field_units-audit-prompt.md, .ai/claude_audits/20260907-220100-02_field_units-audit.md, .ai/claude_audits/20260907-220100-02_field_units-audit.transcript.json, .ai/claude_audits/20260907-224421-02_field_units-audit-prompt.md

## Objective
Let a user save a complete, reproducible OpenPhase case to a file and load it back later, restoring the same valid application inputs. Reproducibility is the entire point of this package.

SAVED CONTENT. The case must capture all input state needed to reproduce the run, as applicable: selected components; mole fractions; temperature; pressure; the presentation unit selections (pressure Pa/MPa/bar/psi and temperature K/degC/degF); sweep settings; any other relevant calculation inputs; and an explicit schema/version identifier.

FORMAT. Deterministic JSON: the same case must serialise to the same bytes, with stable key ordering. The schema version is explicit and written into the file.

LOADING. Validate the entire file BEFORE any scientific call is made. No calculation may run against unvalidated input. Malformed JSON, an invalid schema, an unknown or future schema version, and an invalid composition must each produce a clear, specific, user-facing error message - never a raw traceback. Never silently invent a missing value, and never silently normalise or repair an invalid composition: a composition that does not total 100 mol % must fail exactly the way typing it by hand fails. Unknown or future schema versions are refused, not guessed at.

SAFETY. Use only safe deserialisation - plain JSON parsing. Do not use pickle, eval, or any mechanism that can execute content from the file.

SCOPE. Restoring inputs only. The scientific engine is frozen and must not change, and no thermodynamic relation may be implemented or restated in the application layer.

TESTS. Cover: round-trip save/load; malformed JSON; invalid schema; unsupported/future version; invalid composition; unit selections surviving the round trip; sweep inputs surviving where applicable; and that loading does not execute any science before validation. Avoid brittle hard-coded one-ULP float strings.

BUILD-TIME TESTING POLICY. Run only focused tests for the files and behaviour you changed, plus Ruff and mypy if useful. Do NOT run the whole pytest suite for reassurance - the orchestrator runs the authoritative full-suite verification after you finish, and duplicating it wastes a great deal of wall-clock time.

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
