# Independent Audit: 03_case_save_load

## Method

I did not trust the diff or the builder's report. I read `case_files.py`, `adapters.py`, `sweeps.py`, `units.py`, `state.py`, and `app.py` directly in full (note: `case_files.py` and `tests/test_app_case_files.py` are new untracked files and were **absent from the diff supplied** — I read them from disk directly rather than relying on the diff). I then independently reproduced the numeric behavior that the closed B-1 finding depended on, rather than accepting the builder's claim that it was fixed.

## What the package actually does

`case_files.py` defines a versioned JSON case format (`openphase.case` / `1.0.0`) capturing composition, T/P in SI plus presentation units, and both sweep axes. `serialize_case` produces `json.dumps(..., sort_keys=True, separators=(",",":"), ensure_ascii=False)` — deterministic byte output confirmed by direct reading (stable key order, fixed component order via `COMPONENT_NAMES`). `load_case` parses with plain `json.loads`, an `object_pairs_hook` that rejects duplicate keys, and `parse_constant` that rejects `NaN`/`Infinity`/`-Infinity` tokens — no `eval`/`pickle` anywhere. Validation (`_validated_case`) runs entirely on the parsed dict *before* any session-state mutation; `apply_case_to_state` is only called after `load_case` returns successfully, so a failed load provably cannot touch application state (verified against `test_invalid_sweep_is_rejected_before_state_is_changed`, which snapshots state before/after and asserts equality).

Composition and sweep validation are **reused**, not restated: `_case_inputs` calls the same `validate_scientific_inputs` used for manual entry, and sweep bounds go through the same `validate_sweep_request` used by the Engineering Sweeps page. No thermodynamic relation appears anywhere in `case_files.py`. Nothing in `case_files.py` imports or calls `calculate_two_phase_flash` or any other production science entry point.

## Independent verification performed

1. **Frozen engine / protected artifacts**: `git diff --stat HEAD -- src/pvt_phase_simulator/ data/component_properties.csv docs/validation/ tests/golden_master/` returned empty — confirmed untouched, not merely taken on faith. `src/pvt_phase_simulator_ui/exports.py` also untouched, confirming the CSV/JSON export path is genuinely undisturbed.
2. **The closed B-1 finding (OverflowError → raw traceback)**: I did not accept "fixed" on the builder's word. I directly tested `float(10**400)` in the project's own venv and confirmed it raises `OverflowError`, which `_number()` now catches. I then went one step further than the builder's own regression test and fed `load_case` a **raw JSON float literal** `1e400` (which the C-accelerated JSON parser resolves straight to `float('inf')`, bypassing the `int`→`float` overflow path entirely) — this is a different code path than an oversized integer literal, and it is also caught cleanly, via the `isfinite()` check, producing `Case file schema is invalid: inputs.pressure_pa must be a finite number.` No raw traceback in either case. Both representations of "too large" are covered, not just the one the builder's test exercises.
3. **Unit conversions**: re-derived independently — psi factor (6894.757293168 Pa) matches the exact NIST/avoirdupois definition, Celsius/Fahrenheit conversions are the exact standard affine formulas. No approximation, no thermodynamics.
4. **Streamlit execution-order safety**: `apply_case_to_state` writes directly into widget-bound session-state keys (`temperature_value`, `sweep_kind`, etc.). This is only safe in Streamlit if it happens before those widgets are instantiated in the same script run. Traced the call order in `app.py`: `_case_controls()` (which may call `apply_case_to_state`) runs before the sidebar's `number_input`/`segmented_control` widgets are created in the same `_input_form()` call — correct by construction, not accidental.
5. **Duplicate-key and version-refusal semantics**: confirmed `object_pairs_hook` fires recursively at every nesting depth (not just root), and that an unknown/future `schema_version` is rejected *before* structural validation of the rest of the document runs — correct, since a future schema is not obligated to share this version's shape.

## Non-blocking observations (informational only)

- **D**: `test_loading_invalid_file_cannot_execute_science` in `tests/test_app_case_files.py` is somewhat tautological — it monkeypatches `_cached_flash` and feeds *malformed* JSON, which never reaches the flash call regardless of the patch (the JSON decode error fires first), so the test can't distinguish "science is properly gated" from "science was never called on this path anyway." The actual claim (a *successful* load never triggers a calculation) is adequately covered elsewhere, by `test_applying_loaded_case_restores_widget_inputs_without_results` (asserts `results` dict and `submitted_inputs` are untouched after a valid load). Net coverage is fine; the individual test's name overstates what it proves.
- **D**: `_integer()`'s `except OverflowError` clause is unreachable — Python's `int(x)` for an already-`int` `x` never raises `OverflowError` (only `float()` does). Harmless dead code, not a defect.
- **D**: `load_case()` has no byte-size guard of its own; the only cap is the UI's `st.file_uploader(..., max_upload_size=1)` (1 MB). Not a stated requirement and not exploitable via the current UI-only call site, but worth knowing if `load_case` is ever exposed to an untrusted caller directly in the future.

None of these are scientific, safety, determinism, or scope defects, and none block release.

## Verdict

Save/load correctly captures all required input state, serializes deterministically, validates the complete file before any state mutation and before any scientific call, safely refuses malformed/invalid/future-version files with specific messages (verified independently, not just via the builder's own test), never normalizes an invalid composition, and does not touch the frozen engine or restate any thermodynamics. The previously blocking B-1 defect is genuinely fixed and I independently confirmed the fix covers both the integer-literal and float-literal overflow representations.

<ORCHESTRATOR_RESULT>
{
  "verdict": "APPROVED",
  "findings": [],
  "safe_defer": [
    {"id": "D-1", "severity": "D", "blocks": false, "summary": "test_loading_invalid_file_cannot_execute_science feeds malformed JSON to a monkeypatched _cached_flash, which never reaches the flash call regardless of the patch; the test can't actually distinguish gated-science from never-called-anyway. Coverage of the real claim (successful load never runs science) is adequately provided elsewhere by test_applying_loaded_case_restores_widget_inputs_without_results."},
    {"id": "D-2", "severity": "D", "blocks": false, "summary": "case_files.py's _integer() has an unreachable except OverflowError clause; Python's int(x) on an already-int x never raises OverflowError. Dead code, no functional effect."},
    {"id": "D-3", "severity": "D", "blocks": false, "summary": "load_case() has no intrinsic byte-size guard; the only size cap is the UI's file_uploader max_upload_size=1MB. Not exploitable via the current UI-only call site but worth noting if load_case is ever called directly by an untrusted caller."}
  ]
}
</ORCHESTRATOR_RESULT>