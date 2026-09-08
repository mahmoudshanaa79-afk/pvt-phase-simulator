# Independent Audit: 04_engineering_report

## Scope reviewed

I read `src/pvt_phase_simulator_ui/reports.py` (new, 866 lines) in full, cross-checked it against `exports.py`, `model_scope.py`, `adapters.py`'s critical-point view, `views.py`'s new wiring, and the frozen engine's status enums (`FlashConvergenceStatus`, `CriticalPointStatus`, `EnvelopePointStatus`, `EnvelopeTerminationReason`). I ran the focused test suites and mypy on the changed files, and independently confirmed the DOI cited in a test against `data/component_properties.csv`. I diffed the working tree against protected paths to confirm no scientific-engine or data files changed.

## What I verified independently (not just re-read the builder's claims)

**No thermodynamics in the application layer.** `reports.py` contains only string formatting, HTML escaping, table assembly, and dict traversal (`_mapping`, `_sequence`, `_number`, `_available`, `_optional_record`, `_status`). No arithmetic that could be mistaken for a mixing rule, EOS relation, or phase-split computation. Confirmed by reading every function top to bottom.

**Truthfulness on the failure path is real, not cosmetic.** I traced the mechanism precisely: `exports.py`'s `_flash_export` populates `vapor_fraction`/`liquid_z`/etc. as `"available"` purely based on whether `view.vapor_fraction is not None` — it does **not** check `convergence_status`. That means a `FAILED` flash result whose dataclass still carries a stale numeric fraction *would* be exported as `"available"` at the exports layer. The truthfulness guarantee is enforced one layer up, in `reports.py`'s `_flash_is_usable()` + `_optional_record(..., failed_reason=...)`: when the flash is not usable, `_optional_record` returns `_failed(reason)` unconditionally, before ever looking at the "available" value. I confirmed this by reading the short-circuit (`if failed_reason is not None: return _failed(failed_reason)`) and by re-deriving why `test_failed_flash_fields_are_labelled_failed_and_source_values_are_hidden` — which asserts the raw `f"{result.vapor_fraction:.12g}"` string is absent from the rendered HTML even though the dataclass still holds that value — cannot pass by accident. This is a genuine, non-tautological test.

**Critical-point certification is correctly gated.** `adapt_critical_result` (pre-existing, unmodified) only exposes Tc/Pc/lambda_min etc. when `result.status is CriticalPointStatus.CONVERGED`; `reports.py` additionally requires `certified is True and solver_status == "converged"` before showing anything but FAILED. The test with a fabricated `line_search_failed` critical-point dict with populated numeric fields correctly gets hidden (`"12345.6789012" not in text"`) — I verified this arithmetic (`12345.67890123` formatted to 12 significant figures) matches what would appear if the guard were removed, so the test is discriminating, not vacuous.

**Envelope points**: only `status == "converged"` points render values; everything else renders FAILED with a reason. Cross-checking `exports.py`, the exported `points` list is built only from `branch.points` (accepted points), never `rejected_attempts`, so in practice this branch is a defensive backstop rather than reachable dead code — harmless either way.

**No calculation is triggered.** `test_report_generation_never_calls_a_scientific_calculation` monkeypatches the three real engine entry points (`calculate_two_phase_flash`, `calculate_phase_envelope`, `solve_mixture_critical_point`) to raise, and report generation still succeeds — a meaningful negative test, not a tautology, since `reports.py` genuinely has no import of those functions.

**CSV/JSON unaffected.** Confirmed by test and by reading `exports.py`: nothing in it was touched by this diff.

**Protected artifacts untouched.** `git diff --stat HEAD -- src/pvt_phase_simulator data docs/validation tests/golden_master` returns empty. Confirmed.

**DOI/provenance not fabricated.** The DOI `10.1021/acs.jced.5c00110` asserted in a test is genuinely present in `data/component_properties.csv`'s existing provenance records — not invented by the builder.

**UI wiring**: the report/CSV/JSON download buttons are only rendered inside `render_overview` after `raw = get_result(session(), "flash")` is confirmed non-`None` (function returns early otherwise), and inside `if inputs is not None and not flash_stale`. So the report can never appear before a flash has actually run, and disappears (along with CSV/JSON) once inputs go stale — consistent with the pre-existing stale-result protection pattern, extended rather than altered.

**Tests all pass independently**: `pytest tests/test_app_reports.py` (10 passed), `pytest tests/test_app_streamlit.py` (22 passed), `mypy` on both changed source files clean.

## Findings

One non-blocking observation, not a defect that causes fabrication:

`_termination_failed()` in `reports.py` classifies an envelope branch as having "ended with a structured failure" using a substring match (`"failed"`, `"failure"`, `"lost"`) against the termination-status string, rather than an explicit enumeration of `EnvelopeTerminationReason` members. Checking the frozen enum, `MINIMUM_STEP_REACHED` and `PRESSURE_OUT_OF_BOUNDS` are not matched by this heuristic (arguably correctly, since they represent bounded-continuation stopping conditions the docs already describe as expected, not solver failures) — but the classification is implicit rather than explicit against a closed set owned by another module. This affects only whether a supplementary "structured failure" banner is shown; the termination status and message are always rendered verbatim regardless, so no data is hidden or fabricated either way. Non-blocking.

No scientific error, no weakened/tautological test, no scope creep beyond the declared `allowed_files`, and no protected-artifact change were found.

<ORCHESTRATOR_RESULT>
{
  "verdict": "APPROVED",
  "findings": [],
  "safe_defer": [
    {"id": "D-4", "severity": "D", "blocks": false, "summary": "reports.py's _termination_failed() classifies envelope branch failure via substring matching (\"failed\"/\"failure\"/\"lost\") against EnvelopeTerminationReason string values instead of an explicit allowlist; currently correct for all known enum members and only affects a supplementary failure banner (termination status/message are always shown verbatim regardless), so no truthfulness impact today, but fragile if the frozen enum ever gains new members."}
  ]
}
</ORCHESTRATOR_RESULT>