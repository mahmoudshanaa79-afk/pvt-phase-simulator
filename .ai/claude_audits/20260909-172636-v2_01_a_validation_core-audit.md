# Independent Audit: v2_01_a_validation_core

## Method

I read every source file in `src/pvt_phase_simulator_validation/` directly (not the builder's summary), read both test files line-by-line, and then wrote my own adversarial probe script (independent of the shipped tests) to attack the central DataClass-separation guarantee, the mole-fraction tolerance, the uncertainty-status invariant, and JSON injection paths (NaN/Infinity). I also independently re-ran the focused pytest suite myself rather than trusting the builder's report, confirmed via `git status`/`grep` that no file under the protected paths (`src/pvt_phase_simulator/`, `data/`, `docs/validation/`, `tests/golden_master/`) was touched, and confirmed via grep that the package imports nothing from `pvt_phase_simulator.eos`.

## What holds up

- **No scientific-engine coupling.** Grep for `pvt_phase_simulator.eos` and any import of the engine package returns nothing. Protected artifact paths show zero diff.
- **Central DataClass-separation requirement is real, not cosmetic.** `DataClass` lives only inside the frozen `DatasetIdentity`; `ValidationCase.data_class`/`ValidationRecord.data_class` are read-only properties derived from `identity`, never independently settable fields. `ValidationRecord` disables the generated `__init__` and hand-writes one that accepts no `identity`/`data_class` keyword at all, and marks `case`/`identity` as `init=False` fields, so `dataclasses.replace(record, identity=...)` and `replace(record, case=...)` both raise (`ValueError: ... init=False`) rather than silently reclassifying — I confirmed this myself independently, not just by trusting the shipped tests.
- **Decode-side reclassification is actually blocked, not just tested against a weak case.** `_record_from` decodes the top-level `identity` and the nested `case.identity` separately and raises `InvariantViolationError` if they disagree — I tampered with only the top-level `data_class` field in a JSON payload and it correctly rejected it. Tampering with *both* fields consistently is not (and cannot be) prevented by any framework — that's indistinguishable from constructing a fresh, self-consistent record of that class from scratch, which is legitimate.
- **Aggregation entry points genuinely reject mixed classes** (`homogeneous_data_class`, `summarize_experimental_accuracy/cross_check_agreement`), and the two summary types are structurally distinct dataclasses with non-overlapping field names (`accuracy_records` vs `agreement_records`) — verified `hasattr` checks in the tests are real, not tautological.
- **Hash-verification scope claim is accurate.** `SourceManifest`/`normalize_sha256` validate syntax only; `verify_sha256` is a separate, pure function operating on supplied bytes/text with no path or filesystem access — matches Clarification 2 exactly.
- **Schema/enum rejection is explicit.** I independently confirmed `UnsupportedValueError`/`SchemaVersionError` fire for unknown schema versions, unknown capability, unknown quantity, unknown outcome, unknown status — and that unknown top-level fields (`future_required_field`) are rejected rather than dropped, and duplicate JSON keys are rejected rather than silently overwritten (custom `object_pairs_hook`).
- **Float/JSON injection defenses work.** I hand-crafted payloads with literal `NaN`/`Infinity` (which Python's `json.loads` accepts by default as a non-standard extension) — both are rejected at construction time (`require_finite`), not merely at encode time.
- **Byte round-trip and repr-float claims verified independently**, including canonicalizing int-typed inputs (`coverage_factor=2` → `2.0`) before encoding.
- **`DeclaredTolerance` ships zero instances** in production code (only test fixtures construct it), requires justification+citation, and no boolean "accuracy passed" API exists anywhere (only `bool` I found is a private JSON-type-shape checker, unrelated to accuracy).
- Ruff/mypy/compileall claims are consistent with what I observed; I did not need to re-run the whole suite per the stated policy, and reproduced the 40-pass focused-test count myself.

## Genuine finding

**The `AGREES_WITHIN_UNCERTAINTY`/`OUTSIDE_UNCERTAINTY` guard checks the wrong scope.** In `models.py` (`ValidationRecord.__post_init__`):

```python
if not any(value.uncertainty is not None for value in self.case.reference_values):
    raise InvariantViolationError("uncertainty status requires a source-reported uncertainty")
```

This checks whether *any* reference value in the case carries an uncertainty, not whether the reference value for the *specific quantity actually being predicted/compared* does. I constructed a case with two reference values — `PRESSURE` (the one actually predicted, `uncertainty=None`) and an unrelated `MOLE_FRACTION` vector that happens to carry an `Uncertainty` — and built a `ValidationRecord` with `status=AGREES_WITHIN_UNCERTAINTY` for the pressure comparison. It constructed successfully, even though the pressure reference value the status is nominally about has no source-reported uncertainty at all. This is exactly the kind of scientific-mistake-by-construction this package's stated purpose ("makes certain scientific mistakes structurally difficult") is supposed to foreclose, and it's untested in the shipped suite (no test exercises a case with a *mismatched-quantity* uncertainty).

It is **not** a violation of the central DataClass-separation requirement (no cross-class leakage), doesn't corrupt serialization, and V2-01-C — which will actually compute and assign statuses from real comparisons — will necessarily have to look up the correct per-quantity reference value anyway, so the blast radius is contained. But as written, the guard gives false structural assurance and should be tightened (match on `value.quantity` against the predicted quantity) before any future package leans on it.

## Verdict reasoning

No critical or major defect found. The one real gap is a narrow, non-blocking structural weakness in a secondary guard rail, not in the central type-separation contract this package exists to enforce. Recommend fixing before V2-01-C is built, but it does not need to block this package's merge.

<ORCHESTRATOR_RESULT>
{
  "verdict": "APPROVED",
  "findings": [
    {"id": "C-1", "severity": "C", "blocks": false, "summary": "ValidationRecord's AGREES_WITHIN_UNCERTAINTY/OUTSIDE_UNCERTAINTY guard in models.py checks that ANY reference_value in the case has an uncertainty, not that the reference_value for the specific quantity being compared does — allowing an uncertainty-based status to be attached to a comparison whose own quantity has no source-reported uncertainty, as long as an unrelated reference_value in the same case happens to carry one."}
  ],
  "safe_defer": [
    {"id": "C-1", "note": "Tighten the uncertainty-status check in ValidationRecord.__post_init__ to match on value.quantity against the predicted quantity before V2-01-C begins assigning real statuses from computed comparisons."}
  ]
}
</ORCHESTRATOR_RESULT>