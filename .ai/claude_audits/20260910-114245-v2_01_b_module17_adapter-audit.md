# Independent Audit: v2_01_b_module17_adapter

## Method

I did not trust the diff or the builder's report. I read `module17_adapter.py`, `models.py`, `provenance.py`, `serialization.py`, and the new test file in full, then independently re-derived the numeric claims directly from the source data files using a separate Python script (not the framework's own code), and ran the focused tests, mypy, and ruff myself rather than accepting the reported results.

## What I verified independently

**Hash and data integrity.** Recomputed SHA-256 of `data/experimental/may_2015_ch4_c2_ch4_c3_vle.csv` — matches `normalized_csv_sha256` in the manifest exactly. The adapter's `verify_sha256` call is real, not decorative.

**Coverage counts.** Directly counted `bubble_status`/`dew_status` in the legacy CSV with pandas-free Python: bubble = 31 converged / 9 not_found; dew = 22 converged / 4 not_found / 14 inconclusive. Matches the claimed and required legacy coverage exactly, and matches what the test asserts.

**Unit conversions.** Checked all 40 rows: `pressure_kpa*1000 == pressure_pa` and the uncertainty conversion, both exact, no drift.

**Mole-fraction integrity.** Checked all 40 source rows (liquid/vapor) and all converged predicted compositions (bubble+dew) for (a) sum-to-1 within the framework's 1e-12 absolute tolerance and (b) bounds in [0,1]. Zero violations in both source and legacy evidence — the tight tolerance in `models.py` is not a latent landmine here.

**Vapor uncertainty duplication.** The adapter turns a single scalar `vapor_heavy_expanded_uncertainty` column into a symmetric 2-tuple `(v, v)` for both mole-fraction components. I confirmed this is not invented: the manifest's `uncertainty_availability.vapor_composition` field explicitly states "the complementary methane fraction has the same absolute uncertainty." This is a documented source claim, not a fabrication — consistent with the "never invent, only if explicitly reported" rule.

**Uncertainty attachment across bubble/dew.** The work order's prose ("opposite composition ... with vapor_expanded_uncertainties") is ambiguous for the dew direction, where the "opposite" is liquid (which has no published uncertainty at all). The code instead attaches the published vapor uncertainty to whichever role the vapor composition plays (reference for bubble, specified condition for dew), which is the only physically correct binding — attaching it to liquid would misattribute a real measurement's uncertainty to the wrong quantity. `docs/VALIDATION_FRAMEWORK.md` explicitly documents this exact behavior, so it is not a silent deviation. I do not treat this as a defect.

**Retrospective-diagnostic isolation (Part 4, the highest-risk item).** I found a case (`may2015_ch4_c2_012`) where the retrospective nearest-root pressure (6,646,841.69 Pa, class `UPPER`) genuinely differs from the production-selected root (5,437,473.76 Pa, class `LOWER`) — confirmed directly from the legacy CSV, not from the test's assumption. In fact 21 of 22 converged dew cases have a differing nearest root, so the adversarial test is not vacuous. Traced the adapter code path: `predicted_pressure`/`predicted_composition` are built exclusively from `{direction}_predicted_pressure_pa` / `..._composition` fields; `dew_nearest_experimental_root_*` fields are only ever read inside `_retrospective_diagnostic`, which is attached under `prediction.diagnostics`, never under `prediction.values` or `solver_metadata`. No code path exists from retrospective fields to prediction values. Confirmed clean.

**Structured solver outcome (Part 2).** `legacy_solver_outcome` is stored verbatim (`converged`/`not_found`/`inconclusive`) in `solver_metadata`, queryable without prose parsing, while `ValidationStatus` correctly still collapses both failure kinds to `SOLVER_FAILURE` as instructed.

**Schema extension (Part 1).** Reviewed `models.py`/`provenance.py` construction-time checks for scalar/vector shape mismatch, wrong length, non-finite, negative, and confirmed via independent test run that the round-trip (`encode_reference_dataset`→`decode_reference_dataset`→`encode_reference_dataset`) is idempotent for vector uncertainty. The 1.1 version bump correctly excludes 1.0 as a supported version; I grepped the repo and found no persisted schema-1.0 artifact that this would silently break.

**Scope containment.** Grepped the adapter for imports — no reference to `pvt_phase_simulator.eos` or any EOS module. Diffed the protected paths (`src/pvt_phase_simulator/`, `data/`, `docs/validation/`, `tests/golden_master/`) against the base commit — empty diff, confirming nothing scientific was touched.

**Independent tool runs (not trusting the orchestrator's report).**
- `pytest tests/test_validation_module17_adapter.py tests/test_validation_core.py tests/test_validation_serialization.py` → 65 passed.
- `mypy src/pvt_phase_simulator_validation/module17_adapter.py` → clean.
- `ruff check` / `ruff format --check` on the new files → clean.

**Provenance completeness.** Cross-checked every field the work order requires (citation, DOI, archive URL, access date, raw/normalized hashes, measurement methods, compound mapping, uncertainty definitions, confidence, unit conversion, redistribution policy) against the manifest JSON and the `SourceManifest` object constructed by the adapter — all present. `coverage_factor` is hardcoded to `None` in the adapter and the manifest genuinely never states `k`; no inference occurs.

**Failure preservation.** All 40 points appear in both capabilities (80 records total, confirmed by test and by my own count of solver-metadata outcomes). The 283.38 K anomaly point (`may2015_ch4_c3_023`) is present as an ordinary case in both datasets, converged in both directions, not excluded.

## Findings

None survived scrutiny. I looked specifically for wrong units, wrong sign/branch, inflated tolerances, tests that can't fail, silently reclassified data, and prediction/diagnostic leakage — all came back clean, and I have independent numerical evidence (not just re-reading assertions) for the highest-risk claims: coverage counts, hash integrity, uncertainty duplication justification, and the retrospective-root isolation.

<ORCHESTRATOR_RESULT>
{
  "verdict": "APPROVED",
  "findings": [],
  "safe_defer": []
}
</ORCHESTRATOR_RESULT>