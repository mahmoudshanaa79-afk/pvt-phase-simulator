# Work order: v2_01_c_validation_metrics

## Repository state
- Branch: `v2-validation-framework`
- HEAD: `f1f0f20c2b28ca93b1f1972e6732a90eca821de1`
- Working tree: DIRTY — .ai/work_packages/v2_01_c_validation_metrics.json, .ai/workflow_state.json

## Objective
V2-01-C - GENERALIZED VALIDATION METRICS AND SCIENTIFIC STATUS ENGINE

AUTHORITATIVE DESIGN - READ FIRST
The approved design is stored at .ai/designs/v2_01_c_validation_metrics_design.md.
Read all three sections before writing any code. Section 1 is the approved design
verbatim; Section 2 records the approved decisions; Section 3 records how the design
and the execution authorization were reconciled. Where they differ, Sections 2 and 3
govern. This objective restates the binding requirements. If anything here appears to
contradict that record, report the contradiction in your result instead of resolving
it silently. Also read docs/VALIDATION_FRAMEWORK.md (including C-1 and C-2),
src/pvt_phase_simulator_validation/** and module17_adapter.py as they exist now.

FROZEN PRINCIPLE
Software correctness (deterministic unit, invariant, regression and golden-master
checks) may gate CI. Model accuracy (prediction against experimental or reference
data) never gates CI merely because Peng-Robinson disagrees with experiment; a
scientifically poor prediction is not a software defect. There is no global pass
badge, no accuracy boolean, and no default or invented tolerance anywhere.

==================================================
PART 1 - SCHEMA 1.2 (G-5, G-6, G-7)
==================================================
SCHEMA_VERSION becomes "1.2" and SUPPORTED_SCHEMA_VERSIONS becomes {"1.2"}. New writes
emit 1.2 only.

Schema 1.1 payloads: decoding raises SchemaVersionError whose message states that 1.1
records cannot be converted because phase identity, component identity and
per-quantity assessment semantics would have to be guessed. Provide NO migration
helper. Decoding must not mutate its input or partially construct objects. The Module
17 adapter regenerates valid 1.2 records from the protected legacy evidence, where the
scientific identity is known. Protected artifacts are never modified.

G-6 - LIFECYCLE-ONLY RECORD STATUS
ValidationStatus keeps only: REPORTED_NO_TOLERANCE (meaning "prediction recorded;
scientific assessments live on quantity comparisons"), SOLVER_FAILURE, EXCLUDED.
Remove AGREES_WITHIN_UNCERTAINTY, OUTSIDE_UNCERTAINTY,
AGREES_WITHIN_DECLARED_TOLERANCE, OUTSIDE_DECLARED_TOLERANCE and REFERENCE_UNAVAILABLE
from the record level, remove ValidationRecord.declared_tolerance, and delete the
record-level uncertainty guard in models.py that uses
any(value.uncertainty is not None for value in self.case.reference_values) - this is
the C-1 defect site - together with the statuses it guarded. Keep the existing
FAILURE <-> SOLVER_FAILURE and EXCLUDED <-> exclusion_reason invariants.

G-5 - PHASE AND COMPONENT IDENTITY
Add a ValuePhase enum with LIQUID, VAPOR and OVERALL. ReferenceValue and
PredictionValue gain `phase`. Phase is REQUIRED for MOLE_FRACTION,
COMPRESSIBILITY_FACTOR and DENSITY, and must be None for PRESSURE, TEMPERATURE and
VAPOR_FRACTION; violations raise at construction.
Vector ReferenceValue and PredictionValue gain `component_ids`: required for vectors,
forbidden for scalars, unique, same length as the vector, and exactly the same set as
the owning case's component_ids. A vector uncertainty is ordered by the component_ids
of the ReferenceValue that owns it.
The Module 17 adapter populates identity as follows. BUBBLE_POINT: specified
composition LIQUID, reference composition VAPOR, predicted incipient composition
VAPOR. DEW_POINT: specified composition VAPOR, reference composition LIQUID, predicted
incipient composition LIQUID. Pressure and temperature: phase None. All B scientific
equivalence guarantees must continue to hold.

G-7 - DECLARED TOLERANCE SEMANTICS
DeclaredTolerance gains tolerance_kind (ToleranceKind: ABSOLUTE or RELATIVE).
ABSOLUTE: unit must equal quantity.canonical_si_unit. RELATIVE: unit must be "1" and
the value is a fraction (0.05 means five percent); RELATIVE is refused at construction
when quantity.relative_error_meaningful is False. The existing finite, non-negative
value rule and the mandatory justification, source_citation and scope stay. A
tolerance applies ONLY through an explicit ToleranceBinding(dataset identity,
ComparisonKey, DeclaredTolerance). Never infer applicability from scope text; there is
no global or default tolerance. Ship zero real tolerances; synthetic fixtures only.

==================================================
PART 2 - COMPARISON IDENTITY AND SCIENTIFIC ALIGNMENT
==================================================
ComparisonKey(quantity, phase). Before any error is computed, require: identical
quantity; identical phase; canonical units implied by the quantity (tolerance units are
checked as in G-7); exactly one reference value and at most one prediction value per
key within a record - duplicates raise.
Basis: DENSITY is mass-basis by its kg/m^3 unit and a molar basis is unrepresentable.
Any attempt to declare a molar basis for DENSITY, such as a tolerance with unit
mol/m^3, raises. If a basis field is ever added it becomes part of ComparisonKey.
Component alignment is by IDENTITY. A vector whose component_ids are a permutation of
the reference's is reordered by identity; a different set, a duplicate, or a length
mismatch raises ComponentAlignmentError. Array position is never trusted. All
mismatches raise an explicit alignment error; nothing converts silently between
phases, components or bases. Examples that must never compare: liquid x against vapor
y; CH4 against C2H6; mass density against molar density.

==================================================
PART 3 - SOLVER OUTCOME
==================================================
SolverOutcome: CONVERGED, NOT_FOUND, INCONCLUSIVE, OTHER_FAILURE. Read it from
structured metadata only; for Module 17 the structured key is
solver_metadata["legacy_solver_outcome"] with values converged, not_found and
inconclusive. Never parse failure_reason prose. A FAILURE prediction with no
structured outcome is OTHER_FAILURE, never guessed as NOT_FOUND. Invariant: CONVERGED
if and only if PredictionOutcome.VALUE. Document on the enum that NOT_FOUND means the
configured numerical search did not find an acceptable solution and does NOT prove
that no physical solution exists. INCONCLUSIVE stays distinct and queryable. The
solver outcome lives on the case comparison, separate from every agreement assessment.

==================================================
PART 4 - QUANTITY AND CASE COMPARISONS
==================================================
Form one QuantityComparison per ComparisonKey over the union of the record's reference
keys and prediction keys, with comparison_state:
- COMPARED: reference and finite prediction both present.
- REFERENCE_UNAVAILABLE: a predicted key with no reference value.
- NOT_PREDICTED: the solver converged but produced no value for a referenced key.
- PREDICTION_UNAVAILABLE: the solver did not converge.
- EXCLUDED: reason required.
Errors and assessments exist only for COMPARED.

UNCERTAINTY ASSESSMENT (C-1, C-2, Q4)
- Only for EXPERIMENTAL_VALIDATION. For NUMERICAL_CROSS_CHECK it is structurally
  NotAssessed(NOT_EXPERIMENTAL).
- C-1: the uncertainty used is EXACTLY the uncertainty object on the ReferenceValue
  being compared. Never from specified_conditions, another quantity, another phase or
  another component. Never a lookup by quantity across the case. A dew case carries a
  specified vapor MOLE_FRACTION with U=(0.025, 0.025) and a reference liquid
  MOLE_FRACTION with U=None; the liquid comparison must be
  NotAssessed(NO_REFERENCE_UNCERTAINTY) and must never borrow the vapor uncertainty.
- AppliedUncertainty records kind_used (STANDARD or EXPANDED), derivation (PUBLISHED or
  EXPANDED_FROM_STANDARD), the denominator actually used (component-aligned for
  vectors), coverage_factor exactly as published (possibly None),
  confidence_level_percent exactly as published, and scope = REFERENCE_ONLY. The scope
  field is serialized on every assessment.
- Residuals are distinct fields: expanded_normalized_residual = error / U when
  kind_used is EXPANDED; standard_normalized_residual = error / u when kind_used is
  STANDARD. Exactly one is populated. For vectors they are per component and remain
  accessible.
- Scalar criterion: abs(normalized_residual) <= 1, computed from the normalized
  residual itself (this matches the approved definition and the legacy computation).
- Vector criterion (Q4): align by identity; EVERY required component must have usable
  uncertainty; the criterion is max(abs(normalized_i)) <= 1 over EVERY component. If
  any component uncertainty is missing or unusable the whole vector assessment is
  NotAssessed(MISSING_COMPONENT_UNCERTAINTY); never take the maximum over only the
  available components. Label the criterion ALL_COMPONENTS_WITHIN_REFERENCE_UNCERTAINTY.
  It is component-wise; never describe it as joint coverage or a joint confidence
  region.
- A zero uncertainty denominator (scalar, or any vector component) gives
  NotAssessed(ZERO_UNCERTAINTY_DENOMINATOR); never 0, infinity or NaN.
- C-2: a published expanded U is used directly and is never multiplied by any factor
  in modern assessment. A published standard u is used as u. A derived U = k * u may
  exist only when the source kind is STANDARD, coverage_factor is explicitly present,
  and the caller explicitly requests derivation; the result is marked
  EXPANDED_FROM_STANDARD and is never pooled with published U. Unknown k stays None; a
  95 percent confidence level never implies k = 2. There is no U -> u derivation.
- Module 17 vapor composition uncertainties are usable for the vector criterion: the
  source manifest states the complementary methane fraction has the same absolute
  uncertainty as the published heavy-component value. Preserve that as provenance; do
  not build covariance machinery (Q5 deferred).

TOLERANCE ASSESSMENT (independent of uncertainty)
- NotAssessed(NO_DECLARED_TOLERANCE) unless an explicit ToleranceBinding matches the
  record's dataset identity and the ComparisonKey.
- ABSOLUTE: abs(error) <= tolerance. RELATIVE: abs(error / reference) <= tolerance,
  requiring a strictly positive reference, otherwise
  NotAssessed(ZERO_REFERENCE_DENOMINATOR) or NotAssessed(NEGATIVE_REFERENCE_DENOMINATOR).
- Vectors: every component must satisfy the bound, by the same all-components rule.
- The assessment carries the full bound DeclaredTolerance.

COEXISTENCE
No combined status, no primary field, no precedence rule. A comparison that is OUTSIDE
reference uncertainty and WITHIN a cited declared tolerance must be constructible,
serializable and round-trip unchanged.

CaseComparison carries the record identity, the SolverOutcome and the quantity
comparisons. It is derived from a record without mutating it.

==================================================
PART 5 - METRIC POLICY, INVALID AND EMPTY INPUTS
==================================================
Encode METRIC_POLICY as data (one entry per quantity: primary, enabled and disabled
metrics), not as scattered conditionals:
- PRESSURE: per observation error, abs error, relative, abs relative, normalized
  residual. Enabled: MAE, bias, RMSE (Pa); AARD, bias, RMS relative, max abs relative
  (percent). Primary: AARD percent, bias percent, MAE.
- TEMPERATURE: error and abs error in K. Enabled: MAE, bias, RMSE, max (K). Primary:
  MAE and bias in K. Relative and AARD are permitted by the quantity flag but NOT
  enabled by policy.
- MOLE_FRACTION: per-component error and abs error. Enabled: MAE, bias, RMSE, max
  (absolute). Primary: MAE and max abs error. All relative and percent metrics
  disabled.
- VAPOR_FRACTION: error, abs error; MAE, bias, RMSE, max. Relative disabled. A
  predicted versus reference phase-state mismatch is a classification disagreement,
  never a small numeric error (policy statement only; no dataset exercises it).
- COMPRESSIBILITY_FACTOR: error, abs error, relative, abs relative; MAE, bias, RMSE,
  AARD, bias percent, max. Primary: AARD percent and MAE. Phase required.
- DENSITY (mass basis): error, abs error, relative; MAE, AARD, bias percent, max.
  Primary: AARD percent and MAE. Phase required.
Relative metrics exist only for relative-permitted quantities AND a strictly positive
finite reference. A zero reference makes the relative metric UNDEFINED with reason
ZERO_REFERENCE_DENOMINATOR; a negative reference makes it UNDEFINED with reason
NEGATIVE_REFERENCE_DENOMINATOR. No epsilon. Absolute metrics for that comparison are
still computed.
Non-finite predictions never enter metrics: PredictionValue already rejects non-finite
values, and a producer with a non-finite result records a FAILURE with its reason.
Negative and non-finite uncertainty remain rejected (existing rule); zero uncertainty is
allowed only as source-stated and is handled as above.

Formulas - required exactly, because Module 17 equivalence is bit-exact:
  error = predicted - reference
  relative = error / reference
  MAE = fsum(abs(e) for e in errors) / n
  AARD percent = 100.0 * fsum(abs(r) for r in relatives) / n
  bias percent = 100.0 * fsum(relatives) / n
  RMS relative percent = 100.0 * sqrt(fsum(r * r for r in relatives) / n)
  max abs relative percent = 100.0 * max(abs(r) for r in relatives)
  absolute bias = fsum(errors) / n; RMSE = sqrt(fsum(e * e for e in errors) / n);
  max abs error = max(abs(e) for e in errors)
  PER_COMPONENT composition MAE = fsum(abs(e_ij) over every compared case and every
  component) / (number of component observations)
Use math.fsum and exactly these operation orders.

==================================================
PART 6 - AGGREGATION AND WEIGHTING
==================================================
ObservationUnit: PER_CASE_SCALAR (one observation per case), PER_COMPONENT (one per
case and component), PER_CASE_VECTOR (one per case through a named reduction:
MAX_ABS_COMPONENT or MEAN_ABS_COMPONENT). Every aggregate declares its observation
unit, reduction when applicable, grouping key and sample_count.
Default grouping: (dataset_id, system_id, capability, ComparisonKey). A
pooled-across-systems view is a separately labelled aggregate and never replaces the
per-system aggregates. Different quantities are never pooled; different phases are
never pooled. Equal weight per declared observation; no inverse-variance or hidden
weighting. PER_COMPONENT and PER_CASE_VECTOR are different statistics with different
sample counts, so a two-component composition case can never silently outweigh a
scalar pressure case.
Uncertainty-agreement counts are grouped by (kind_used, derivation, coverage_factor,
confidence_level_percent) and never pooled across groups.
An aggregate with zero usable observations reports an explicit UNDEFINED metric state
with sample_count = 0 and reason NO_USABLE_OBSERVATIONS - never 0 - and its coverage
still reports the real case counts. NaN and Infinity never appear in serialized
scientific output; undefined states are explicit.

==================================================
PART 7 - COVERAGE
==================================================
Every aggregate carries a CoverageBlock: total_cases, excluded_cases, eligible_cases,
reference_available_cases, converged, not_found, inconclusive, other_failure,
compared_cases, metric_observation_count, uncertainty_assessable_count.
Enforced reconciliation: eligible_cases = total_cases - excluded_cases;
converged + not_found + inconclusive + other_failure = eligible_cases;
compared_cases <= min(converged, reference_available_cases).
No aggregate API returns a metric value without its CoverageBlock and sample count.
Provide a formatting helper producing text such as "AARD = X% over 7 compared of 23
cases (2 not_found, 14 inconclusive, 0 other failures, 0 excluded)".

==================================================
PART 8 - SUMMARIES AND DATA-CLASS SEPARATION
==================================================
aggregate_experimental_accuracy(...) returns ExperimentalAccuracySummary, whose
vocabulary is experimental error, accuracy and uncertainty agreement; it rejects
non-experimental input. aggregate_cross_check_agreement(...) returns
CrossCheckAgreementSummary, whose vocabulary is numerical difference, model-to-model
discrepancy and agreement; it has NO uncertainty-agreement fields and rejects
experimental input. Mixed input raises MixedDataClassError. Reference-EOS or CoolProp
output is never experimental truth.

==================================================
PART 9 - MODULE 17 EQUIVALENCE
==================================================
Compute the generalized aggregates from the B-adapted 1.2 records and compare them
with the protected docs/validation/module17_vle_validation_summary.json READ AT TEST
TIME. Tests must not merely hardcode expected numbers, and must never compare the
framework against its own output. Legacy (system, direction) corresponds to
(system_id, capability).
Reproduce with exact equality (==) every field of
production_selected_bubble_metrics and production_selected_dew_metrics for both
systems: source_count; success_count; failure_count (via LD-3); pressure MAE, AARD,
RMS relative, max abs relative and bias; PER_COMPONENT composition MAE and max abs
component error; pressure_uncertainty_available_count and
pressure_within_one_uncertainty_count (these are modern expanded-uncertainty assessment
counts, same semantics); composition uncertainty available and within-one counts for
bubble (for dew, legacy None corresponds to zero assessable comparisons with reason
NO_REFERENCE_UNCERTAINTY); and the within-two counts ONLY through the legacy
descriptive path of Part 10.
Legacy coverage: CH4+C2H6 bubble 11 of 17 converged, 6 not_found; CH4+C2H6 dew 15 of
17, 2 not_found; CH4+C3H8 bubble 20 of 23, 3 not_found; CH4+C3H8 dew 7 of 23, 2
not_found, 14 inconclusive. Representative verified values: CH4+C2H6 bubble AARD
0.454690272936386, composition MAE 0.0037091200128458565 over 22 component
observations, pressure within 1U 10 of 11; CH4+C3H8 dew AARD 36.668237970426496,
pressure within 1U 1 of 7. The legacy values were confirmed reproducible bit-exactly
from the stored predictions using the Part 5 formulas.
Do NOT encode qualitative conclusions such as "bubble is good" or "dew is poor".
If a generalized value disagrees with legacy: investigate. If legacy is demonstrably
wrong, do not reproduce the mistake; record a LegacyDiscrepancy. If a discrepancy would
change a documented scientific conclusion in docs/EXPERIMENTAL_VALIDATION.md or the
application, STOP and report it rather than resolving it.

==================================================
PART 10 - LEGACY DESCRIPTIVE STATISTICS AND LD-1 / LD-2 / LD-3
==================================================
Implement exactly the approved definitions from Section 1 of the design record.
- LD-1: legacy per-point residual is error/U and is C-2 compliant, but legacy also
  counts abs(error)/U <= 2 against an already 95 percent expanded U. A 2x band on an
  expanded uncertainty must not become an uncertainty-agreement statistic. Implement a
  LegacyDescriptiveStatistics type in an isolated Module 17 legacy module. The
  within-two counts are computed ONLY there, clearly labelled as legacy descriptive
  statistics. That type can never be passed to modern aggregation, and modern
  uncertainty-agreement counts never include it.
- LD-2: legacy composition MAE flattens components, so 11 cases give 22 observations,
  perfectly correlated for binaries; the per-case value differs by at most about
  2.1e-17. Expose PER_COMPONENT (legacy-equivalent) and PER_CASE_VECTOR
  MEAN_ABS_COMPONENT as two distinct, labelled statistics with their own sample counts.
- LD-3: legacy failure_count merges not_found and inconclusive. Coverage splits them
  using the structured solver outcome; legacy failure_count equals not_found +
  inconclusive + other_failure.
Provide a LegacyDiscrepancy record with: identifier, metric, legacy definition, legacy
value, new definition, new value, cause, scientific assessment, and
changes_documented_conclusion. LD-1, LD-2 and LD-3 are recorded with
changes_documented_conclusion False; if implementation finds any case where it would
be True, stop and report. Document all three in docs/VALIDATION_FRAMEWORK.md.

==================================================
PART 11 - 283.38 K SENSITIVITY
==================================================
SubsetDefinition carries subset_id, the excluded case identities, scope system ch4_c3,
the reason quoted from the manifest's source_anomalies, and its source. The excluded
source point is may2015_ch4_c3_023; in the adapter's scheme its cases are
may2015_ch4_c3_023::bubble_point and may2015_ch4_c3_023::dew_point. The implementation
identifies the subset by case identity ONLY - never by raw float equality on
temperature. A test may verify, by reading legacy evidence, that this case-identity
subset equals the legacy temperature-defined subset.
SensitivityAnalysis carries the primary full-dataset aggregate, the alternate subset
aggregate, the subset definition, and shifts = alternate - primary. The primary result
is never replaced; records are never mutated or marked EXCLUDED; the excluded case
keeps its identity, reason and original result.
Reproduce exactly every field of source_anomaly_sensitivity_283_38_k in the legacy
summary, for bubble (20 compared -> 19) and dew (7 -> 6): included and excluded success
counts, AARD, RMS relative and bias, and each shift.

==================================================
PART 12 - REFERENCE-ONLY LIMITATION
==================================================
Write into docs/VALIDATION_FRAMEWORK.md, and reflect in the serialized scope field:
uncertainty assessments compare a prediction only against the reference value's own
published uncertainty. They exclude propagation from input temperature, input pressure,
composition inputs, EOS parameters, covariance, model uncertainty and sensitivity
derivatives. A full budget could only widen the band, so OUTSIDE does not prove
disagreement beyond combined uncertainty, and WITHIN does not establish model
adequacy. No uncertainty-propagation engine is built.

==================================================
PART 13 - SERIALIZATION
==================================================
Deterministic JSON encode and decode for every new type; encode then decode then encode
is byte-identical; floats use round-trip repr; undefined and not-assessed states are
explicit; unknown enum values are rejected; schema 1.1 is rejected as in Part 1.

==================================================
DEFERRED - DO NOT IMPLEMENT
==================================================
Q5 closure-derived covariance machinery. Q6 retrospective nearest-root and
measured-state fugacity diagnostic summaries (they stay diagnostics and never enter
accuracy outputs). Dashboard and report UI. The CH4+C3H8 dew-branch investigation.
CoolProp. CO2. New datasets. Real tolerance values. Any engine, kij or solver change.
Any Orchestrator v2 change.

==================================================
TESTS - ADVERSARIAL, FOCUSED DURING THE BUILD
==================================================
Prove each of these: quantity-specific uncertainty; no borrowing across quantities,
specified conditions, phases or components (including the dew vapor-to-liquid case);
standard versus expanded kept distinct; a published U is never re-expanded even when a
coverage factor is present; unknown k stays unknown; derived U requires explicit
opt-in and is marked; u-based and U-based counts never pool; vector uncertainty aligned
by identity; permuted component order realigns or raises; component set mismatch
raises; quantity, phase and basis mismatches raise; a missing vector-component
uncertainty makes the vector NOT ASSESSABLE rather than taking a partial maximum; zero
uncertainty gives ZERO_UNCERTAINTY_DENOMINATOR; zero and negative relative denominators
give explicit undefined metrics; relative metrics are impossible for fractions; empty
aggregates give NO_USABLE_OBSERVATIONS with sample_count 0 and never 0; no NaN or
Infinity is serialized; PER_COMPONENT and PER_CASE_VECTOR carry different sample counts
and composition never outweighs pressure; different quantities and phases never pool;
solver outcome is independent of assessment; not_found and inconclusive stay distinct;
OTHER_FAILURE is never promoted; no binding means NO_DECLARED_TOLERANCE; uncited,
wrong-kind, forbidden-relative and molar-density tolerances are rejected; OUTSIDE
uncertainty and WITHIN tolerance coexist and round-trip; experimental and cross-check
comparisons never share an aggregate; failures stay in coverage denominators and
coverage reconciles; schema 1.1 is rejected without mutating input; every Module 17
target reproduces exactly against the legacy summary; LD-1 within-two counts exist only
in the legacy descriptive type; LD-2 and LD-3 are surfaced; sensitivity never replaces
the primary result and its case-identity subset matches the legacy rule; serialization
is deterministic; protected artifacts are unchanged.

AUDIT FOCUS FOR THE INDEPENDENT REVIEWER
Attack adversarially: (1) uncertainty borrowing across quantities; (2) across phases;
(3) component misalignment; (4) a missing vector-component uncertainty silently
ignored; (5) a published U re-expanded; (6) k inferred; (7) standard and expanded
statistics pooled; (8) the legacy 2U band leaking into modern assessment; (9) zero,
negative or non-finite uncertainty handling; (10) zero relative-error denominators;
(11) empty aggregate handling; (12) failures disappearing from denominators; (13)
not_found and inconclusive merging; (14) hidden vector weighting; (15) quantity
pooling; (16) experimental and cross-check mixing; (17) tolerance and uncertainty
overwriting each other; (18) hidden or default tolerance; (19) ambiguous schema 1.1 to
1.2 conversion; (20) LD-1, LD-2 and LD-3 treatment against the design record; (21)
sensitivity replacing the primary result; (22) Module 17 numerical equivalence; (23)
protected-file changes. No unrelated architecture critique.

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
  - Model accuracy never gates CI; there is no accuracy boolean, pass badge, default tolerance or invented threshold.
  - C-1: an uncertainty assessment uses only the uncertainty of the exact ReferenceValue compared - never another quantity, phase, component or a specified condition.
  - C-2: a published expanded U is never multiplied by a coverage factor in modern assessment; unknown k stays unknown; 95 percent confidence never implies k = 2.
  - Q4: a vector uncertainty assessment requires usable uncertainty on every component and is never a maximum over a partial subset.
  - Liquid and vapor compositions never compare; components align by identity; mass and molar density never compare.
  - Solver outcome is separate from agreement; not_found and inconclusive are never merged; not_found never claims physical non-existence.
  - Uncertainty and declared-tolerance assessments coexist with no precedence or combined status.
  - Failures never leave coverage denominators; every aggregate declares its observation unit and sample count; quantities and phases never pool.
  - Undefined results are explicit states: zero denominators and empty aggregates never become 0, infinity or NaN.
  - The legacy within-2U statistic exists only as a labelled legacy descriptive statistic and never enters modern uncertainty agreement.
  - Module 17 aggregates reproduce the protected legacy summary exactly; a discrepancy that would change a documented conclusion stops the work.
  - The 283.38 K sensitivity subset is identified by case identity and never replaces the primary full-dataset result.
  - EXPERIMENTAL_VALIDATION and NUMERICAL_CROSS_CHECK never share an aggregate.
  - Schema 1.1 payloads are rejected explicitly and never silently reinterpreted.

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
