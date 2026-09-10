# Work order: v2_01_b_module17_adapter

## Repository state
- Branch: `v2-validation-framework`
- HEAD: `5230e870628685f91be0249c9674e17832ebcae6`
- Working tree: DIRTY — .ai/work_packages/v2_01_b_module17_adapter.json, .ai/workflow_state.json

## Objective
Map the existing protected Module 17 independent experimental validation evidence onto
the generalized V2-01-A validation framework and prove scientific equivalence. This is
an ADAPTER. It is not a new scientific calculation, not a new validation dataset, not a
metrics rewrite, and not a solver modification.

PART 1 - AUTHORIZED SCHEMA EXTENSION G-1 (VECTOR UNCERTAINTY)
Real Module 17 data publishes per-component expanded uncertainties for compositions,
for example [0.025, 0.025], on all 40 rows, but Uncertainty.value is currently a scalar
float. Make the smallest justified extension: Uncertainty.value may be a float or a
tuple[float, ...].

Rules to enforce at construction:
- A scalar ReferenceValue: if uncertainty is present it must be scalar.
- A vector ReferenceValue: uncertainty may be a vector; its length must exactly equal
  the reference-value vector length, and its ordering must correspond exactly to
  component_ids.
- Reject scalar/vector shape mismatches, wrong vector length, non-finite values, and
  negative values.
- Zero is allowed only because a source may explicitly report zero uncertainty. Never
  invent zero when uncertainty is absent; absent uncertainty remains None.
- Uncertainty shape must survive deterministic serialization and decoding unchanged.
Add adversarial tests for each rejection rule and for shape preservation across a
round trip.

If the serialized schema contract or its version needs a small update under the
existing schema-versioning policy, make that update explicitly and document it in
docs/VALIDATION_FRAMEWORK.md. Do NOT build a migration framework. Do not broaden
V2-01-A in any other way.

PART 2 - STRUCTURED LEGACY SOLVER OUTCOME
Module 17 distinguishes three solver outcomes: converged, not_found, and inconclusive.
Do NOT preserve that distinction only inside free-text failure_reason. Preserve the
original outcome in a structured, queryable representation using the smallest existing
suitable structure, which is the already-supported structured solver metadata on
ValidationPrediction.

Required: converged remains identifiable as converged, not_found as not_found, and
inconclusive as inconclusive, without parsing human-readable prose. V2-01-C must later
be able to compute solver coverage and inconclusive counts directly from structure.
The generalized ValidationStatus may still classify both non-success outcomes as
SOLVER_FAILURE; do NOT redesign the global status model to accommodate this.

PART 3 - THE ADAPTER
Source-of-truth hierarchy, all read-only:
- data/experimental/may_2015_source_manifest.json is provenance truth.
- data/experimental/may_2015_ch4_c2_ch4_c3_vle.csv is experimental reference truth.
- docs/validation/module17_vle_validation.csv and its summary JSON are production
  prediction and diagnostic truth.

Read this existing evidence. Do NOT recompute thermodynamics merely to build the
adapter, do NOT create a second Module 17 solver, and do NOT import or reimplement
Peng-Robinson science. The adapter must not import from pvt_phase_simulator.eos.

Because capability is dataset-level in the framework while system_id is per-case, emit
TWO ReferenceDatasets from the one source manifest: a BUBBLE_POINT dataset and a
DEW_POINT dataset, each containing all 40 source points and spanning both ch4_c2 and
ch4_c3. Both carry data_class EXPERIMENTAL_VALIDATION, inherited from the manifest;
no caller may reclassify them.

Mapping, per direction:
- source_point_id plus capability produces a deterministic, stable case_id.
- system_id, ordered component_ids, temperature_k, and the specified composition
  (liquid for bubble, vapor for dew) become the case identity and specified
  conditions.
- experimental_pressure_pa with pressure_expanded_uncertainty_pa, and the opposite
  composition with vapor_expanded_uncertainties, become reference values with their
  published uncertainties.
- predicted pressure and predicted composition become the production prediction.
- solver iterations, inner iteration count, selected parent/incipient roots, root
  ordering consistency, maximum fugacity equilibrium residual and diagnostic codes
  become structured solver metadata.
- All dew_*_diagnostic_* and nearest_experimental_root_* fields become diagnostics
  ONLY. See Part 4.

Do NOT store the legacy error columns (absolute, relative, percent, and
uncertainty-normalized residuals). Those are V2-01-C output. Use them in tests as an
independent consistency check on the mapping, never as stored fields. Assign no
accuracy statuses: every record is REPORTED_NO_TOLERANCE.

PART 4 - RETROSPECTIVE DIAGNOSTICS, HARD SCIENTIFIC RULE
The retrospective dew nearest-root diagnostics use the EXPERIMENTAL pressure to inspect
or select among already-existing PR roots. They must NEVER become production
predictions. Anything derived that way remains a RETROSPECTIVE DIAGNOSTIC.

Keep retrospective quantities structurally separate from prediction values: there must
be no code path from any nearest_experimental_root field into prediction values. Add an
adversarial test specifically covering the cases where the retrospective nearest root
DIFFERS from the production-selected root, because that is exactly where a careless
adapter would silently substitute the better-looking number. The summary's
interpretation statement, that the retrospective scan never replaces the production
prediction, must survive into the adapted output. If any retrospective result can reach
a production prediction field, that is a P1 defect.

PART 5 - FAILURE PRESERVATION
All 40 source points appear in BOTH capabilities: 80 adapted records total. No case may
disappear because the solver failed, a point was not found, a result was inconclusive,
behaviour was near-critical, or model error was large.

Legacy coverage that must be reproduced exactly:
- Bubble: 31 of 40 converged, 9 not_found.
- Dew: 22 of 40 converged, 4 not_found, 14 inconclusive.
Tests must assert both numerator and denominator so a later change cannot quietly
improve the success rate by discarding difficult cases. Nothing is EXCLUDED; the
283.38 K anomaly case is preserved as an ordinary case, and its sensitivity study
belongs to V2-01-C.

PART 6 - PROVENANCE
Reuse the existing Module 17 provenance; do not invent a second competing record.
Preserve citation, DOI, ThermoML/source URL, access date, raw and normalized hashes,
measurement method, compound identity mapping, uncertainty definition, confidence
information, unit conversion and extraction information, and the redistribution policy.

coverage_factor remains None if the source does not explicitly state k. The manifest
states a 95 percent confidence level and never states k; inferring k = 2 from that
would fabricate a source claim. Never infer it.

If some provenance cannot be represented without scientific information loss, STOP and
report a genuine schema gap rather than discarding the information. Deferred gaps:
G-2 (hash placement) is deferred unless provenance cannot otherwise be preserved
correctly; G-3 (structured ThermoML selected-dataset metadata) must have its
information preserved faithfully now without forcing a large schema redesign; G-4
(SOLVER_FAILURE collapsing two outcomes) is addressed by Part 2 and must not trigger a
ValidationStatus redesign.

PART 7 - NUMERICAL EQUIVALENCE
Because the adapter reads rather than recomputes, values mapped directly from stored
Module 17 evidence must reproduce exactly after float round-trip parsing. Do NOT
introduce arbitrary tolerances merely to make tests pass; an inexact value is an
adapter defect, not a tolerance to widen. The only tolerance in play is the existing
mole-fraction sum tolerance. Scientific-equivalence tests compare against the LEGACY
EVIDENCE, never the adapter against its own output. Do not require cosmetic byte
identity of the new representation: column order, JSON layout, whitespace, and field
ordering are explicitly not part of equivalence.

BUILD-TIME TESTING POLICY
Run only focused tests for what you changed, plus Ruff and mypy if useful. Do NOT run
the whole pytest suite for reassurance; the orchestrator runs the authoritative
full-suite verification after you finish, and duplicating it wastes a great deal of
wall-clock time.

## Allowed files
  - `src/pvt_phase_simulator_validation/**`
  - `tests/test_validation_*.py`
  - `docs/VALIDATION_FRAMEWORK.md`

## Files you must NOT modify
  - `src/pvt_phase_simulator`
  - `data`
  - `docs/validation`
  - `tests/golden_master`
  - `src/pvt_phase_simulator_ui`
  - `tools/orchestration`

## Protected artifacts — never regenerate
  - `tests/golden_master/baseline.csv` — SHA256 530C667AA70EF1EA182F4EDB98624A0A9B9908F149354276CDAC44A87EA7D2BE
  - `data/component_properties.csv` — SHA256 C6F6BA9AE9C2F4C7F257BBC09A75DF0D7065255868AA46BF3E8C81AC5A8B9B3A
  - `docs/validation/module17_vle_validation.csv` — SHA256 B14728D51AAC06AF38FC4F4E5F408942B253FEBE32D3E12EC26E9623CFA42482
  - `docs/validation/module17_vle_validation_summary.json` — SHA256 5B120B77BF05567FCC6A0EE0D0054C6D1DEBA35FE26A7C837352C92017D24870

## Scientific invariants that must continue to hold
  - The scientific engine is frozen: no file under src/pvt_phase_simulator/, data/, docs/validation/ or tests/golden_master/ may change.
  - The adapter performs no thermodynamic calculation and imports nothing from pvt_phase_simulator.eos.
  - Retrospective nearest-root diagnostics can never reach a production prediction value; they remain structurally separate diagnostics.
  - All 40 Module 17 source states survive in both capabilities: 80 records, no case dropped for failure, non-convergence or large model error.
  - Legacy solver coverage is reproduced exactly: bubble 31/40 converged with 9 not_found; dew 22/40 converged with 4 not_found and 14 inconclusive.
  - The converged / not_found / inconclusive distinction is preserved structurally and queryably, not only in free-text prose.
  - The dataset remains EXPERIMENTAL_VALIDATION and cannot be reclassified.
  - coverage_factor stays None when the source does not state k; a 95 percent confidence level never implies k = 2.
  - No published provenance is silently discarded; a field that cannot be represented is reported as a schema gap.
  - Values mapped from stored legacy evidence reproduce exactly after float round-trip parsing; no tolerance is introduced to make tests pass.
  - No accuracy threshold, error metric, or boolean meaning 'accuracy passed' is added by this package.

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
