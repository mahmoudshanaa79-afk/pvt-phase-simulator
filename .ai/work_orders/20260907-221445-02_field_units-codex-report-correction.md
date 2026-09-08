# Correction order: 02_field_units

## Repository state
- Branch: `app-v1.2-engineering`
- HEAD: `cd908da958d3a616a22c58735ae3f1b4d2c6bb94`
- Working tree: DIRTY — .ai/claude_audits/20260906-115645-01_model_and_limitations-audit-prompt.md, .ai/claude_audits/20260906-115645-01_model_and_limitations-audit.md, .ai/claude_audits/20260906-115645-01_model_and_limitations-audit.transcript.json, .ai/claude_audits/20260906-150728-02_field_units-audit-prompt.md, .ai/claude_audits/20260906-150728-02_field_units-audit.md, .ai/claude_audits/20260906-150728-02_field_units-audit.transcript.json, .ai/claude_audits/20260907-220100-02_field_units-audit-prompt.md, .ai/claude_audits/20260907-220100-02_field_units-audit.md, .ai/claude_audits/20260907-220100-02_field_units-audit.transcript.json, .ai/claude_builds/20260906-123830-02_field_units-claude-report.md

## Objective
The implementation for this package is present in the working tree and every
deterministic gate passes against it (Ruff, Ruff format, mypy, compileall, and
the full suite at 1256 passed). An independent audit then accepted the package
except for ONE blocking finding. Your entire task is to close that finding.
Do not restructure, rewrite, or redo anything else, and do not revisit the
already-accepted B-1 critical-point hover fix.

FINDING C-1 (blocking)
`result_is_stale` in `src/pvt_phase_simulator_ui/state.py` decides staleness by
comparing `ScientificInputs.signature` — a tuple of
`(mole_fractions, temperature_k, pressure_pa)` — with exact `!=` equality.
Meanwhile `current_inputs` is recomputed on every Streamlit rerun by re-parsing
whatever value currently sits in the input field, and that field's value has
been round-tripped through the selected display unit.

An IEEE-754 double does not survive a K -> °F -> K (or Pa -> psi -> Pa) round
trip bit-exactly. The auditor measured this against the real
`validate_scientific_inputs`: across 20,000 realistic
`(temperature_k, pressure_mpa)` pairs, about 50% of temperature signatures
differed by 1 ULP after a K -> °F -> K round trip, for example
373.7993794602593 becoming 373.79937946025933.

The user-visible consequence is a functional regression: simply switching the
temperature or pressure display unit, changing nothing physical, marks an
already-computed result as "Stale result — submitted scientific inputs changed"
for roughly half of ordinary inputs, and disables the CSV/JSON downloads until
the user pointlessly recalculates. It applies to every cached result type that
keys off the same signature comparison: flash, envelope, critical,
critical_scan and sweep.

This also directly contradicts documentation this same package introduced, in
`docs/STREAMLIT_APPLICATION.md`: "Changing a unit converts the editable value
and preserves the physical state; it does not run a calculation or make a
current scientific result stale."

WHAT TO DO
Fix the cause, and prefer the structural fix over a numeric band-aid:

- Preferred: stop the round trip from being able to change the canonical value
  at all. Keep the submitted SI state authoritative, and treat the display unit
  as presentation only, so that a unit-only change cannot alter the signature
  that staleness is judged against.
- Only if that is genuinely impractical within this package's scope: compare
  the signature with a principled relative tolerance instead of exact equality.
  If you take this route, justify the tolerance explicitly. It must be tight
  enough that a real user edit — including a deliberately small one — is still
  correctly detected as stale. Silently widening staleness detection into
  something that misses genuine input changes would be a worse defect than the
  one you are fixing.

Either way, a genuine change to composition, temperature or pressure MUST still
be detected as stale. Do not weaken that.

CONSTRAINTS
- The scientific engine stays frozen. Nothing under `src/pvt_phase_simulator/`,
  `data/`, `docs/validation/` or `tests/golden_master/` may change.
- No thermodynamic relation may be implemented or restated in the application
  layer.
- Keep the change narrowly scoped to this finding.
- If the fix changes documented behaviour, make
  `docs/STREAMLIT_APPLICATION.md` accurate. Documentation is corrected to match
  the application, never the reverse.

TESTS
- Add regression coverage that would actually have caught this. The existing
  test `test_presentation_unit_change_does_not_stale_a_calculated_result` in
  `tests/test_app_streamlit.py` passed only because its fixed 300 K / 5 MPa
  case happens to round-trip exactly through every supported unit.
- Cover values that are known NOT to round-trip exactly, across several units,
  rather than one lucky canonical case. Parametrising over a handful of
  representative values, or over many values, is fine.
- Also assert the converse: a genuine physical input change is still correctly
  reported as stale.
- Do not hard-code brittle one-ULP formatted float strings as expected values.

TESTING POLICY FOR THIS RUN
Run focused tests only — the specific test files and cases relevant to what you
changed, plus Ruff and mypy if useful. Do NOT run the entire pytest suite for
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
