# Independent Audit — 03_case_save_load

## Scope and method

I read `case_files.py`, `adapters.py`, `sweeps.py`, `units.py`, `state.py`, `app.py`, and `views.py` in full, cross-checked them against the work-package objective and `tests/test_app_case_files.py`, ran the focused test files, and then wrote independent probe scripts (not reusing the builder's test helpers) to attack the implementation directly: duplicate keys, `NaN`/`Infinity` literals, non-object roots, dict-insertion-order sensitivity, borderline composition tolerance, and — critically — numeric-field edge cases the test suite never exercises.

## What holds up

- **Determinism**: `serialize_case` uses `sort_keys=True`, fixed `separators`, `ensure_ascii=False`, and a fixed component ordering derived from `adapters.COMPONENT_NAMES`. I independently verified byte-for-byte identical output from two `state` dicts built with keys inserted in randomly shuffled order — genuinely deterministic, not just deterministic-by-luck of dict insertion order.
- **Safety**: only `json.loads` is used, with `object_pairs_hook` (duplicate-key detection) and `parse_constant` (rejects `NaN`/`Infinity`/`-Infinity`) overridden. No `eval`, `pickle`, or dynamic import anywhere in `case_files.py`. Confirmed by import list: only `adapters`, `sweeps`, `units` — none of which import the EOS/flash engine.
- **No thermodynamics duplicated**: `case_files.py` calls the pre-existing `validate_scientific_inputs` and `validate_sweep_request` (both unchanged in this diff, already part of the frozen validation boundary) — it does not reimplement composition or sweep-bounds logic.
- **Validate-before-mutate**: `load_case` fully parses and validates before `apply_case_to_state` is ever called; `_load_case_inputs` in `app.py` only calls `apply_case_to_state` after `load_case` succeeds. I confirmed via a monkeypatched `_cached_flash` and a direct `state == before` diff check that no state mutation and no science call happens on a rejected file.
- **No normalization of invalid composition**: confirmed the exact "Composition must total 100 mol %..." message is preserved unmodified from the manual-entry path, and a 99.0/9-mol%-off composition is rejected outright.
- **Schema/version handling**: unknown top-level/nested fields, missing fields, wrong schema string, and any non-`"1.0.0"` version are all rejected with specific messages, not silently accepted or "upgraded."
- **Protected artifacts**: unchanged per diff; `case_files.py` touches none of them.
- **Scope**: all changed files fall within `allowed_files` for this package (`src/pvt_phase_simulator_ui/**`, `tests/test_app_*.py`, `docs/STREAMLIT_APPLICATION.md`). The `views.py`/`state.py` sweep-widget refactor is necessary plumbing to make sweep inputs persist across a load (previous sweep widgets were keyed by unit-string combinations, which can't survive a case load) — not unrelated scope creep.
- **UI wiring**: traced the Streamlit script-rerun order and confirmed `apply_case_to_state` runs (inside `_case_controls`) before the bound widgets (`methane_pct`, `temperature_value`, segmented controls, etc.) are instantiated later in the same run, so a loaded case correctly repopulates the visible form on the same rerun — verified this isn't just asserted in tests but is structurally sound.

## Confirmed defect

**A crafted/corrupted case file with an oversized JSON integer in any numeric leaf field crashes the running app with a raw, user-visible traceback — a direct violation of the package's explicit "never a raw traceback" requirement.**

`_number()` in `case_files.py:112-118` accepts any Python `int`/`float` and calls `float(value)` unconditionally. JSON integers have unbounded precision in Python's parser, so a file containing e.g. `"temperature_k": 1` followed by 400 zeros (or any JSON integer literal too large for a C double) causes `float(value)` to raise `OverflowError`, which is not `ValueError`-derived and is caught nowhere in the call chain (`_case_inputs` → `_validated_case` → `load_case` → `app._load_case_inputs` → `app._case_controls`'s `except CaseFileError`). This applies to every field routed through `_number`: `temperature_k`, `pressure_pa`, each component's `mole_percent`, and all four sweep bounds (`start_pa`/`end_pa`/`start_k`/`end_k`).

I reproduced this two ways:
1. Directly: `load_case()` on a crafted document raises a bare `OverflowError: int too large to convert to float` instead of `CaseFileError`.
2. End-to-end via `streamlit.testing.v1.AppTest`: uploading the same crafted file and clicking "Load case" in the running app produces `app.exception` populated with a full stack trace rendered to the user — confirmed the app has no outer handler that would turn this into the required clean message.

This is squarely inside the threat model the work package calls out ("Malformed JSON... must produce a clear, specific, user-facing error message - never a raw traceback") and is reachable by any user through the ordinary "Load case" file-upload control — no privilege or special access needed, just an adversarial or corrupted file, which is exactly the class of input this audit is asked to probe. The existing test suite (136 "passing" tests) never exercises this path — it tests malformed JSON syntax, wrong schema, wrong version, and invalid composition, but not out-of-range numeric literals — so the gap escaped both the builder's focused tests and the full-suite gate.

The fix is narrow and doesn't touch the scientific engine: widen the catch in `_number`/`_integer` (or wrap the JSON-to-domain conversion boundary in `_validated_case`) to also catch `OverflowError`/`TypeError` and raise `_schema_error(...)` instead.

## Other observations (non-blocking)

- `apply_case_to_state` deliberately does not clear `state["results"]`/`state["result_signatures"]` on load — instead it relies on the existing signature-mismatch staleness mechanism (`result_is_stale`) to mark any prior result stale once `current_inputs` changes. I traced this through `views.py` and it is consistent with the pre-existing stale-result protection; not a defect, just worth naming since a first read suggests results might leak across a case load. Confirmed via test `test_applying_loaded_case_restores_widget_inputs_without_results` and design reading — behaves correctly.
- `_validated_case` re-validates the full document at both `case_from_state` and `serialize_case` (and again inside `apply_case_to_state`) — redundant but harmless double/triple-validation, not a defect.
- Both sweep axes (active and inactive) are always validated on every save/load, not just the active one. This is a stricter reproducibility guarantee than the spec strictly requires but is self-consistent and did not produce any false rejection in testing.

<ORCHESTRATOR_RESULT>
{
  "verdict": "CONDITIONAL",
  "findings": [
    {"id": "B-1", "severity": "B", "blocks": true, "summary": "case_files.py's _number() calls float() on any JSON int/float without catching OverflowError; a case file containing an out-of-range JSON integer literal in any numeric field (temperature_k, pressure_pa, mole_percent, or any sweep bound) raises an uncaught OverflowError that propagates through load_case -> app._load_case_inputs and is not caught by app._case_controls's `except CaseFileError`, crashing the running Streamlit app with a raw traceback shown to the user -- reproduced directly and via AppTest end-to-end -- in direct violation of the package's explicit 'never a raw traceback' requirement for malformed/invalid load input."}
  ],
  "safe_defer": []
}
</ORCHESTRATOR_RESULT>