# Independent audit: v2_01_c_validation_metrics

This is a full audit of the work package described below.

## Your role and its limits

You are an INDEPENDENT ADVERSARIAL AUDITOR. You did not write this code and
you are not here to confirm it.

- Do NOT modify, stage, or commit anything. You are read-only.
- Do NOT regenerate any baseline or golden artifact.
- Do NOT start new features or fix what you find — report it.
- Re-derive equations independently where it matters; do not accept a
  formula because a comment or document agrees with the code.
- Do not trust a test merely because it passes. Ask what it would fail on.
- Prefer different numerical machinery from production when building a
  reference.
- Distinguish a genuine defect from a cosmetic preference. Do not inflate.

## Work package under audit
- Name: v2_01_c_validation_metrics
- Declared risk: MEDIUM
- Objective: V2-01-C - GENERALIZED VALIDATION METRICS AND SCIENTIFIC STATUS ENGINE

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

## Scientific invariants claimed to hold
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

## Repository state
- Branch: `v2-validation-framework`
- HEAD: `f1f0f20c2b28ca93b1f1972e6732a90eca821de1`
- Base for this change: `f1f0f20c2b28ca93b1f1972e6732a90eca821de1`

## Protected artifact hashes (recomputed locally)
  - `tests/golden_master/baseline.csv`: unchanged
  - `data/component_properties.csv`: unchanged
  - `docs/validation/module17_vle_validation.csv`: unchanged
  - `docs/validation/module17_vle_validation_summary.json`: unchanged

## Local verification the orchestrator already ran
Passed: **True**
```
        PASS  .venv/Scripts/python.exe -m pytest -q
        PASS  .venv/Scripts/python.exe -m ruff check .
        PASS  .venv/Scripts/python.exe -m ruff format --check .
        PASS  .venv/Scripts/python.exe -m mypy src app
        PASS  .venv/Scripts/python.exe -m compileall -q src app
```
Changed files: ['docs/VALIDATION_FRAMEWORK.md', 'src/pvt_phase_simulator_validation/__init__.py', 'src/pvt_phase_simulator_validation/aggregates.py', 'src/pvt_phase_simulator_validation/aggregation.py', 'src/pvt_phase_simulator_validation/comparisons.py', 'src/pvt_phase_simulator_validation/enums.py', 'src/pvt_phase_simulator_validation/exceptions.py', 'src/pvt_phase_simulator_validation/metrics.py', 'src/pvt_phase_simulator_validation/models.py', 'src/pvt_phase_simulator_validation/module17_adapter.py', 'src/pvt_phase_simulator_validation/module17_legacy.py', 'src/pvt_phase_simulator_validation/provenance.py', 'src/pvt_phase_simulator_validation/scientific_serialization.py', 'src/pvt_phase_simulator_validation/sensitivity.py', 'src/pvt_phase_simulator_validation/serialization.py', 'tests/test_validation_core.py', 'tests/test_validation_metrics.py', 'tests/test_validation_serialization.py']

## Builder's own report — treat as an unverified claim
```
Implemented schema 1.2, comparisons, metrics, coverage, legacy statistics, sensitivity, serialization, and documentation. All 125 focused tests and four quality gates pass. Module 17 targets match exactly; protected hashes are unchanged. Full pytest remains for the orchestrator.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "Focused pytest: test_validation_core.py, test_validation_serialization.py, test_validation_module17_adapter.py, test_validation_metrics.py with -p no:cacheprovider: 125 passed. Ruff check . passed. Ruff format --check . passed (162 files). Mypy src app passed (64 source files). Compileall -q src app passed. Full pytest suite not run, per build-time policy.",
  "files_changed": [
    "docs/VALIDATION_FRAMEWORK.md",
    "src/pvt_phase_simulator_validation/__init__.py",
    "src/pvt_phase_simulator_validation/aggregates.py",
    "src/pvt_phase_simulator_validation/aggregation.py",
    "src/pvt_phase_simulator_validation/comparisons.py",
    "src/pvt_phase_simulator_validation/enums.py",
    "src/pvt_phase_simulator_validation/exceptions.py",
    "src/pvt_phase_simulator_validation/metrics.py",
    "src/pvt_phase_simulator_validation/models.py",
    "src/pvt_phase_simulator_validation/module17_adapter.py",
    "src/pvt_phase_simulator_validation/module17_legacy.py",
    "src/pvt_phase_simulator_validation/provenance.py",
    "src/pvt_phase_simulator_validation/scientific_serialization.py",
    "src/pvt_phase_simulator_validation/serialization.py",
    "src/pvt_phase_simulator_validation/sensitivity.py",
    "tests/test_validation_core.py",
    "tests/test_validation_metrics.py",
    "tests/test_validation_serialization.py"
  ],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>
```

## Diff stat
```
 .ai/workflow_state.json                            |  72 +++-
 docs/VALIDATION_FRAMEWORK.md                       | 427 +++++++++++++--------
 src/pvt_phase_simulator_validation/__init__.py     | 113 ++++++
 src/pvt_phase_simulator_validation/aggregation.py  | 130 ++++++-
 src/pvt_phase_simulator_validation/enums.py        |  16 +-
 src/pvt_phase_simulator_validation/exceptions.py   |   8 +
 src/pvt_phase_simulator_validation/models.py       | 120 ++++--
 .../module17_adapter.py                            |  15 +
 src/pvt_phase_simulator_validation/provenance.py   |  10 +-
 .../serialization.py                               |  66 +++-
 tests/test_validation_core.py                      |  43 ++-
 tests/test_validation_serialization.py             |  18 +-
 12 files changed, 769 insertions(+), 269 deletions(-)

```

## Full diff
```diff
diff --git a/.ai/workflow_state.json b/.ai/workflow_state.json
index f4760c2..6a31258 100644
--- a/.ai/workflow_state.json
+++ b/.ai/workflow_state.json
@@ -1,14 +1,14 @@
 {
   "project": "pvt-phase-simulator",
   "phase": "post-v1.0-extensions",
-  "workflow_status": "APPROVED",
+  "workflow_status": "CLAUDE_RUNNING",
   "last_scientific_commit": "d2a0a74",
   "last_independent_audit_commit": "824dd6892f521c033af423f0d60286c4ccb3d64b",
   "work_packages_since_audit": 0,
-  "current_work_package": "v2_01_b_module17_adapter",
+  "current_work_package": "v2_01_c_validation_metrics",
   "current_risk": "MEDIUM",
-  "audit_required": false,
-  "audit_reason": null,
+  "audit_required": true,
+  "audit_reason": "package audit_policy=IMMEDIATE",
   "blocking_findings": [],
   "safe_defer_findings": [],
   "deferred_independent_audits": [
@@ -50,32 +50,32 @@
   "provisional_review_cycles": 0,
   "claude_cost_usd_this_package": 0.0,
   "claude_cost_unknown_runs": 0,
-  "last_error": null,
+  "last_error": "codex output contract unusable: no <ORCHESTRATOR_RESULT> block found in agent output. Raw report preserved at C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260915-000710-v2_01_c_validation_metrics-codex-report.md.",
   "workflow_id": "c3d365745ae6",
   "builder": "codex",
-  "reviewer": "codex",
-  "last_completed_stage": "committed",
+  "reviewer": "claude",
+  "last_completed_stage": "verified",
   "verification_status": "passed",
-  "base_commit": "8a1205afe1b93e08aedc02e54d95caa900bff822",
-  "resulting_commit": "824dd6892f521c033af423f0d60286c4ccb3d64b",
-  "builder_report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260910-105648-v2_01_b_module17_adapter-codex-report.md",
+  "base_commit": "f1f0f20c2b28ca93b1f1972e6732a90eca821de1",
+  "resulting_commit": null,
+  "builder_report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260915-001203-v2_01_c_validation_metrics-codex-report.md",
   "builder_evidence": {
     "builder": "codex",
-    "package": "v2_01_b_module17_adapter",
+    "package": "v2_01_c_validation_metrics",
     "workflow_id": "c3d365745ae6",
-    "report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260910-105648-v2_01_b_module17_adapter-codex-report.md",
-    "report_sha256": "02fdd135751b01071e150910e2c1897078ce2459fbed88eef5fe1fde49890d5a",
+    "report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260915-001203-v2_01_c_validation_metrics-codex-report.md",
+    "report_sha256": "b2f9f7aff4543bab74ecf78b25a2def714abc7dd8c31ff0cadec1784349deeec",
     "revision": 1,
     "kind": "build"
   },
-  "tree_fingerprint": "3c18789be29477c9f1539c735cf04ee990c1209752e1b8f0c700f5074038d8df",
+  "tree_fingerprint": "be1aebee47434186a567c6203ff51d85fd22ec9b80bdd5a4806c98b742d09ae3",
   "revisions": [
     {
-      "package": "v2_01_b_module17_adapter",
+      "package": "v2_01_c_validation_metrics",
       "revision": 1,
       "author": "codex",
       "kind": "build",
-      "at": 1789028377.199698
+      "at": 1789460208.016005
     }
   ],
   "role_transitions": [
@@ -1032,6 +1032,46 @@
       "from": "CLAUDE_RUNNING",
       "to": "APPROVED",
       "reason": "independent audit approved"
+    },
+    {
+      "from": "APPROVED",
+      "to": "PLANNING",
+      "reason": "planning v2_01_c_validation_metrics"
+    },
+    {
+      "from": "PLANNING",
+      "to": "CODEX_RUNNING",
+      "reason": "invoking codex builder"
+    },
+    {
+      "from": "CODEX_RUNNING",
+      "to": "HUMAN_ACTION_REQUIRED",
+      "reason": "codex output contract unusable: no <ORCHESTRATOR_RESULT> block found in agent output. Raw report preserved at C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260915-000710-v2_01_c_validation_metrics-codex-report.md."
+    },
+    {
+      "from": "HUMAN_ACTION_REQUIRED",
+      "to": "PLANNING",
+      "reason": "planning v2_01_c_validation_metrics"
+    },
+    {
+      "from": "PLANNING",
+      "to": "CODEX_RUNNING",
+      "reason": "invoking codex builder"
+    },
+    {
+      "from": "CODEX_RUNNING",
+      "to": "CODEX_REVIEW",
+      "reason": "codex returned COMPLETE"
+    },
+    {
+      "from": "CODEX_REVIEW",
+      "to": "LOCAL_VERIFY",
+      "reason": "running local gates"
+    },
+    {
+      "from": "LOCAL_VERIFY",
+      "to": "CLAUDE_RUNNING",
+      "reason": "invoking claude auditor"
     }
   ]
 }
diff --git a/docs/VALIDATION_FRAMEWORK.md b/docs/VALIDATION_FRAMEWORK.md
index ed93652..eaef95a 100644
--- a/docs/VALIDATION_FRAMEWORK.md
+++ b/docs/VALIDATION_FRAMEWORK.md
@@ -1,165 +1,262 @@
-# Validation framework core contract
-
-`pvt_phase_simulator_validation` is the data and serialization boundary for future
-OpenPhase validation work. It contains no thermodynamic calculation, error metric,
-dataset loader, accuracy threshold, or bundled reference data.
-
-## Data-class separation
-
-Every dataset has one immutable `DatasetIdentity`, containing exactly its ID, version,
-and `DataClass`. The identity is retained by every `ValidationCase` and derived by
-every `ValidationRecord` from its case. A record constructor has no independent
-data-class or identity parameter. Dataset construction rejects any case or source
-manifest whose identity disagrees.
-
-Experimental comparisons and numerical cross-checks use distinct summary types:
-`ExperimentalAccuracySummary` exposes `accuracy_records`, while
-`CrossCheckAgreementSummary` exposes `agreement_records`. Every aggregation entry
-point first requires a non-empty homogeneous collection and raises
-`MixedDataClassError` if the classes differ. Neither type computes a metric or returns
-an accuracy-pass boolean.
-
-## Canonical values and provenance
-
-Numeric values are canonical SI. `ValidationQuantity` declares the canonical unit and
-whether relative error is meaningful. Relative error is structurally marked
-meaningless for mole fraction and vapor fraction because both approach bounded
-endpoints where percentage error misleads.
-
-A `ValidationCase` separates specified conditions from reference values. Vector mole
-fractions use the case's ordered `component_ids`, must contain one entry per component,
-must lie in `[0, 1]`, and must sum to one within the explicitly declared structural
-normalization tolerance `MOLE_FRACTION_SUM_ABSOLUTE_TOLERANCE`. This is an input-shape
-invariant, not an accuracy threshold.
-
-`SourceManifest` requires citation text and both raw and normalized SHA-256 fields,
-along with archive, extraction, unit-conversion, measurement, uncertainty, compound,
-snapshot-policy, and data-class provenance. Digest construction checks only syntax and
-normalizes hexadecimal spelling to uppercase. It does **not** verify a file or make an
-external-content claim. A later loader holding actual bytes must call `verify_sha256`;
-the helper accepts supplied bytes or UTF-8 text, returns `None` on a match, and raises
-`HashMismatchError` on a mismatch.
-
-Missing source uncertainty is represented only as `None`. A source-reported zero is a
-valid explicit `Uncertainty(value=0.0, ...)`; the framework never imputes it.
-`Uncertainty.value` has the same scalar or vector shape as its `ReferenceValue`.
-Vector uncertainty is an immutable tuple with one finite, non-negative value per
-reference-vector entry. For component-indexed mole fractions, that ordering is the
-case's ordered `component_ids`. Construction rejects scalar/vector mismatches and
-unequal vector lengths.
-
-## Predictions and statuses
-
-A `ValidationPrediction` has either `VALUE` with one or more values and no failure
-reason, or `FAILURE` with no values and a non-empty failure reason. A failure can only
-form a record with `SOLVER_FAILURE`; successful values cannot use that status.
-Diagnostics are preserved as deeply immutable JSON values, and solver metadata is a
-canonical immutable JSON object.
-
-`EXCLUDED` requires a non-empty exclusion reason. Declared-tolerance statuses require
-a `DeclaredTolerance`, and that type requires canonical units, justification, source
-citation, and scope. The package creates and ships no tolerance instances. The honest
-default record status is `REPORTED_NO_TOLERANCE`.
-
-## Serialization and evolution
-
-`SCHEMA_VERSION` identifies the JSON contract. Encoders emit deterministic compact
-UTF-8 JSON with a trailing newline; Python's JSON encoder uses the language's
-round-trip float representation. Decoders validate all required fields, reject unknown
-fields, restore identity from the payload, and check the record identity against its
-embedded case. Encoding, decoding, and encoding again is byte-identical.
-
-Schema version `1.1` extends `Uncertainty.value` from a scalar number to either a
-scalar number or an array of numbers. An array decodes to an immutable tuple and is
-encoded as an array again, so uncertainty shape is deterministic. This is the only
-`1.1` contract change. Version `1.0` is not accepted by the `1.1` reader: the package
-deliberately has no migration framework, and unsupported versions fail explicitly.
-
-Adding an enum member can be backward compatible only for writers and readers that
-both support it. A reader that encounters an unsupported schema version or a required
-enum value it does not know fails explicitly with `SchemaVersionError` or
-`UnsupportedValueError`. No value is coerced, defaulted, or dropped, and this package
-contains no migration framework.
-
-`ValidationRun` deterministically orders dataset pins and records. Its serialized
-`run_metadata` block contains only `run_id` and UTC `timestamp_utc`; stable package,
-commit, interpreter, platform, dataset identity/hash, command, and record content live
-outside that volatile block so run diffs remain meaningful.
-
-## Module 17 evidence adapter
-
-`load_module17_validation_evidence` is a read-only adapter over the existing May et
-al. source manifest, normalized experimental CSV, production-validation CSV, and
-summary JSON. It performs no equation-of-state calculation and has no dependency on
-the scientific engine. It verifies the normalized source hash, joins the experimental
-and legacy evidence by `source_point_id`, and rejects any exact disagreement in the
-duplicated reference fields.
-
-The adapter emits two `EXPERIMENTAL_VALIDATION` datasets, one each for `BUBBLE_POINT`
-and `DEW_POINT`. Each contains all 40 source points across both systems. A case ID is
-the source point ID plus its capability; the source reference retains the ThermoML
-pressure/vapor dataset and row coordinates. Temperature and the direction's specified
-composition are specified conditions. Experimental pressure and the opposite
-composition are references. Published pressure uncertainty remains scalar. Published
-vapor-composition uncertainty follows the vapor composition: it is attached to the
-bubble reference composition and to the dew specified composition. No uncertainty is
-invented for the liquid composition.
-
-Production-selected pressure and composition are prediction values only when the
-legacy solver outcome is `converged`. The exact legacy outcome is separately retained
-under the structured solver-metadata key `legacy_solver_outcome`, so `converged`,
-`not_found`, and `inconclusive` are queryable without parsing prose. The latter two
-use the generalized `FAILURE`/`SOLVER_FAILURE` shape; converged records use
-`REPORTED_NO_TOLERANCE`. The adapter assigns no accuracy status and stores none of the
-legacy error or uncertainty-normalized residual columns.
-
-All retrospective dew branch-scan, experimental-state, and
-`nearest_experimental_root` fields live only inside a diagnostic object marked
-`RETROSPECTIVE_DIAGNOSTIC`. The protected summary interpretation is retained with that
-object: the experimental-pressure scan identifies an already-existing nearest root
-but never replaces the production prediction. No retrospective field participates in
-constructing prediction values.
-
-The single framework `SourceManifest` is populated from the protected Module 17
-manifest rather than creating competing provenance. It retains citation, DOI, the
-ThermoML page URL, raw JSON URL, access date, raw and normalized hashes, measurement
-methods, compound mapping, uncertainty definitions, confidence, pressure conversion,
-selected ThermoML dataset metadata, anomalies, extraction coordinates, and the raw
-snapshot/redistribution policy. Selected-dataset metadata and source-only distinctions
-that lack dedicated V2-01-A fields are preserved as canonical JSON in the existing
-textual extraction provenance. `coverage_factor` remains `None`; a stated 95 percent
-confidence level does not imply a source-reported coverage factor.
-
-## Deferred to V2-01-C
-
-**C-1 — the uncertainty-status guard is too permissive.** `ValidationRecord`
-currently accepts `AGREES_WITHIN_UNCERTAINTY` or `OUTSIDE_UNCERTAINTY` when *any*
-reference value in the case carries an uncertainty, rather than requiring the
-uncertainty to belong to the quantity actually being compared. A case whose pressure
-has a published uncertainty but whose composition does not could therefore carry an
-uncertainty-based status on the composition comparison, implying a rigour the source
-does not support.
-
-Nothing assigns these statuses yet, so no result is currently affected. The check must
-match on `value.quantity` against the quantity under comparison, and that is an
-explicit acceptance criterion for V2-01-C, which is the package that first computes
-comparisons and assigns statuses from them.
-
-Found by the independent audit of V2-01-A, which reached it by writing its own
-adversarial probe rather than reading the shipped tests.
-
-**C-2 — standard versus expanded uncertainty.** The metrics and status engine must
-distinguish standard uncertainty `u` from expanded uncertainty `U = k*u`.
-
-Where a source already publishes an expanded uncertainty, comparison uses that
-published `U` directly. It must never be expanded again: multiplying a published `U`
-by a coverage factor would silently double the tolerance and turn disagreement into
-apparent agreement. Where a source supplies a standard uncertainty and a coverage
-factor, expansion may be derived, but only when scientifically justified and
-explicitly represented in the record.
-
-Where `coverage_factor` is unknown, it stays unknown. A stated 95% confidence level is
-not a licence to assume `k = 2`; the May et al. 2015 manifest states the confidence
-level and never states `k`, which is exactly the case this rule exists to protect.
-
-This is V2-01-C scope. V2-01-B assigns no uncertainty-based accuracy statuses at all.
+﻿# Validation framework: schema 1.2 and scientific comparisons
+
+Software correctness and model accuracy are separate. Deterministic unit,
+invariant, regression and golden-master checks may gate CI. Prediction error
+against experiment does not gate CI merely because Peng–Robinson disagrees with a
+measurement. There is no global pass badge, accuracy boolean, default tolerance or
+invented acceptance threshold. The scientific engine and protected Module 17
+artifacts remain unchanged.
+
+## Identity, source values and schema evolution
+
+`DatasetIdentity` retains dataset ID, version and `DataClass` on every case and
+record. Experimental data and numerical cross-check data cannot share an aggregate.
+`ReferenceDataset` checks case and manifest identity. Provenance retains citation,
+source hashes, archive and extraction information, uncertainty definitions and unit
+conversions. `verify_sha256` checks supplied bytes; merely constructing a manifest
+checks digest syntax, not external content.
+
+`SCHEMA_VERSION = "1.2"`; the supported set contains only `"1.2"`. New writes emit
+1.2. A 1.1 envelope raises `SchemaVersionError` before constructing records: phase
+identity, component identity and per-quantity assessment semantics would have to be
+guessed. There is no migration helper. Module 17 records are regenerated in memory
+from the protected evidence, where those identities are known.
+
+`ReferenceValue` and `PredictionValue` are finite canonical-SI values. `ValuePhase`
+is LIQUID, VAPOR or OVERALL, and is required for MOLE_FRACTION,
+COMPRESSIBILITY_FACTOR and DENSITY. It must be absent for PRESSURE, TEMPERATURE and
+VAPOR_FRACTION. Every vector supplies unique `component_ids`, one per entry,
+matching exactly the owning case's component set. Scalars forbid component IDs.
+The reference uncertainty vector follows its owning reference value's component
+order. Predictions are reordered by component identity, never compared by assumed
+array position. Quantity, phase, component and basis mismatches raise alignment
+errors. Density means mass density in kg/m^3; molar density is unrepresentable.
+If a basis field is introduced later, it must join the comparison key.
+
+Mole fractions retain their structural [0, 1] and normalization checks. The named
+`MOLE_FRACTION_SUM_ABSOLUTE_TOLERANCE` is solely an input-shape invariant, not a
+scientific accuracy tolerance. Negative and non-finite uncertainty are rejected.
+Explicit source-stated zero is retained. A missing vector component is `None`,
+never imputed or omitted from assessment.
+
+`ValidationStatus` is lifecycle-only: REPORTED_NO_TOLERANCE means prediction
+recorded, with scientific assessments on quantity comparisons; SOLVER_FAILURE
+requires a FAILURE prediction and vice versa; EXCLUDED requires an exclusion reason,
+and an exclusion reason requires EXCLUDED. The record has no declared-tolerance
+field and no agreement status. A VALUE prediction contains finite values and no
+failure reason. A FAILURE contains no values and retains its reason and diagnostics.
+Diagnostics and solver metadata remain deeply immutable JSON.
+
+## Comparison and solver outcomes
+
+`compare_record(record, capability, ...)` derives `CaseComparison` without changing
+the record. Capability is supplied explicitly from the owning dataset; it is never
+inferred from text. Comparisons use `ComparisonKey(quantity, phase)` and reject
+duplicate reference or prediction keys within a record. The union of reference and
+prediction keys produces COMPARED, REFERENCE_UNAVAILABLE, NOT_PREDICTED,
+PREDICTION_UNAVAILABLE or EXCLUDED. Errors and assessments exist only for COMPARED;
+non-comparisons carry explicit `NotAssessed` reasons.
+
+`SolverOutcome` is separate from agreement. Module 17 reads only the structured
+`solver_metadata["legacy_solver_outcome"]`: converged, not_found or inconclusive.
+A VALUE is CONVERGED; a FAILURE without structured classification is OTHER_FAILURE.
+Failure prose is never parsed. CONVERGED holds if and only if the prediction is
+VALUE. NOT_FOUND means the configured numerical search found no acceptable
+solution; it does **not** prove that no physical solution exists. INCONCLUSIVE stays
+distinct and queryable.
+
+## C-1: uncertainty belongs to the exact reference value
+
+The previous record-level `any(reference.uncertainty)` guard and the statuses it
+protected have been removed. The comparison receives the exact `ReferenceValue`
+and uses only that object's uncertainty. No lookup by quantity across a case, no
+specified-condition uncertainty, and no different-phase uncertainty can substitute.
+For Module 17 dew, the specified vapor composition carries U=(0.025, 0.025), but the
+reference liquid composition has no uncertainty. The liquid comparison therefore
+reports NO_REFERENCE_UNCERTAINTY. Its pressure uncertainty is also inapplicable.
+
+Only EXPERIMENTAL_VALIDATION permits uncertainty assessment. Every numerical
+cross-check comparison carries `NotAssessed(NOT_EXPERIMENTAL)`.
+
+## C-2: published and derived uncertainty are distinct
+
+`AppliedUncertainty` retains kind_used (STANDARD or EXPANDED), derivation (PUBLISHED
+or EXPANDED_FROM_STANDARD), the actual denominator, source-stated coverage factor,
+source-stated confidence level and serialized scope REFERENCE_ONLY. Published U is
+used directly; a coverage factor never multiplies it again. Published u is used as
+u. Deriving U=k*u requires STANDARD source uncertainty, an explicit published k,
+and caller opt-in `derive_expanded=True`. The derivation remains labelled and is
+never pooled with published U. Unknown k remains None; 95% confidence does not imply
+k=2. There is no U-to-u derivation.
+
+Exactly one residual field is populated: `expanded_normalized_residual = error/U`
+or `standard_normalized_residual = error/u`. The scalar criterion is the computed
+`abs(normalized_residual) <= 1`. Vector comparisons use
+ALL_COMPONENTS_WITHIN_REFERENCE_UNCERTAINTY: every component must have usable
+uncertainty, and `max(abs(normalized_i)) <= 1`. Every residual remains accessible.
+Missing any component yields MISSING_COMPONENT_UNCERTAINTY for the whole vector;
+zero scalar or component denominator yields ZERO_UNCERTAINTY_DENOMINATOR. No partial
+maximum, epsilon, infinity or NaN is used. This is component-wise agreement, never
+joint coverage or a joint confidence region.
+
+Module 17's manifest states that complementary methane has the same absolute vapor
+composition uncertainty as the published heavy component. The adapter preserves
+that provenance. Generalized covariance machinery is deferred.
+
+## Reference-only limitation
+
+Uncertainty assessment compares the prediction only with the reference value's own
+published uncertainty. It excludes propagation from input temperature, input
+pressure, composition inputs, EOS parameters, covariance, model uncertainty and
+sensitivity derivatives. A full budget could only widen the band: OUTSIDE does not
+prove disagreement beyond combined uncertainty, and WITHIN does not establish model
+adequacy. Scope REFERENCE_ONLY is serialized with the applied uncertainty on every
+assessed comparison. No uncertainty-propagation engine is built.
+
+## Declared tolerances coexist with uncertainty
+
+A `DeclaredTolerance` requires quantity, tolerance_kind, finite non-negative value,
+unit, justification, source_citation and scope. ABSOLUTE uses the canonical quantity
+unit. RELATIVE uses unit `"1"` and a fractional value (0.05 means 5%); it is forbidden
+where the quantity disallows relative error. In particular, mol/m^3 is not an
+absolute mass-density tolerance unit.
+
+Only an explicit `ToleranceBinding(DatasetIdentity, ComparisonKey, DeclaredTolerance)`
+can apply a bound. Scope prose never determines applicability. No binding yields
+NO_DECLARED_TOLERANCE. Every vector component must satisfy the bound. Relative bounds
+require strictly positive references, with explicit ZERO_REFERENCE_DENOMINATOR or
+NEGATIVE_REFERENCE_DENOMINATOR otherwise. There are zero real tolerances in the
+package; tests contain synthetic cited fixtures only.
+
+Uncertainty and tolerance assessments have independent slots and no precedence,
+combined status or primary assessment. OUTSIDE uncertainty and WITHIN tolerance
+coexist and serialize together without reclassification.
+
+## Metric policy and formulas
+
+`METRIC_POLICY` is immutable data with per-observation, primary, enabled and disabled
+metrics for each quantity. Pressure enables MAE, bias, RMSE in Pa and AARD, bias,
+RMS relative and max absolute relative in percent; primary metrics are AARD percent,
+bias percent and MAE. Temperature enables MAE, bias, RMSE and max absolute error in K;
+MAE and bias are primary. Relative temperature error is permitted by the quantity
+flag but disabled by policy. Mole and vapor fractions use only absolute MAE, bias,
+RMSE and max, with MAE and max primary. A vapor phase-state mismatch is a
+classification disagreement, never a small numeric error (policy only).
+Compressibility factor enables MAE, bias, RMSE, max, AARD and bias percent. Mass
+density enables MAE, max, AARD and bias percent. Both use AARD percent and MAE as
+primary metrics and require phase identity.
+
+For errors e=predicted-reference and relatives r=e/reference, the implementation uses
+exactly these operation orders with `math.fsum`:
+
+- MAE = fsum(abs(e)) / n; bias = fsum(e) / n.
+- RMSE = sqrt(fsum(e*e) / n); max absolute error = max(abs(e)).
+- AARD percent = 100.0 * fsum(abs(r)) / n.
+- Bias percent = 100.0 * fsum(r) / n.
+- RMS relative percent = 100.0 * sqrt(fsum(r*r) / n).
+- Max absolute relative percent = 100.0 * max(abs(r)).
+
+Relative metrics require policy permission and a strictly positive finite reference.
+`UndefinedMetric` represents invalid per-observation relative denominators explicitly;
+absolute errors remain available. Aggregate `MetricResult` has DEFINED or UNDEFINED,
+value or reason, sample_count and coverage. No usable observations yields
+NO_USABLE_OBSERVATIONS with count zero and value None. If invalid relative references
+are the only observations, their denominator reason is retained. With both usable
+and invalid references, relative metrics count only usable observations; the original
+case coverage and per-observation undefined reasons remain available. Non-finite
+predictions are rejected; a producer must record a FAILURE and reason instead.
+Arithmetic overflow also never enters serialized metrics as NaN or Infinity.
+
+## Observation units, grouping and coverage
+
+`aggregate_experimental_accuracy` returns `ExperimentalAccuracySummary`;
+`aggregate_cross_check_agreement` returns `CrossCheckAgreementSummary`. They accept
+`CaseComparison` inputs and reject the other data class or mixed input. The latter
+uses numerical difference, model-to-model discrepancy and agreement vocabulary and
+has no uncertainty-agreement fields. Reference EOS or CoolProp output is not
+experimental truth. The original `summarize_*` helpers remain record containers.
+
+Default grouping is dataset identity (including version), system, capability and
+ComparisonKey. Quantities and phases never pool. Optional pooled-across-systems
+aggregates are separately labelled and appended without replacing system results.
+Each aggregate declares PER_CASE_SCALAR, PER_COMPONENT or PER_CASE_VECTOR, plus its
+sample count and grouping. PER_CASE_VECTOR requires MAX_ABS_COMPONENT or
+MEAN_ABS_COMPONENT; metrics then describe that named non-negative reduction. All
+observations receive equal weight; no inverse-variance weighting is performed.
+The default vector unit is PER_COMPONENT. Pressure observations and composition
+components never share a statistic. `aggregate_group` accepts an explicit grouping
+key even for empty input, allowing complete undefined metrics and zero coverage;
+a summary with no inputs has no inferred groups.
+
+Every aggregate and every `MetricResult` carries `CoverageBlock`: total_cases,
+excluded_cases, eligible_cases, reference_available_cases, converged, not_found,
+inconclusive, other_failure, compared_cases, metric_observation_count and
+uncertainty_assessable_count. Eligibility is total minus exclusions, solver outcomes
+sum to eligibility, and compared cases cannot exceed either convergence or reference
+availability. Failures remain in denominators. `format_metric` prints the value with
+case coverage and observation count. Uncertainty agreement counts are grouped by
+(kind_used, derivation, coverage_factor, confidence_level_percent); these strata
+never merge.
+
+## Module 17 equivalence and legacy distinctions
+
+The read-only adapter retains all 40 source points for each capability. Bubble
+specified composition is LIQUID and reference/predicted incipient composition is
+VAPOR. Dew reverses those identities. Pressure and temperature have no phase.
+Published vapor uncertainty follows the vapor value. Dataset/source identities,
+source coordinates, confidence, hashes, diagnostics and production values retain
+B's scientific semantics. Retrospective nearest-root and measured-state fugacity
+values remain diagnostics and never enter metrics.
+
+Tests read `docs/validation/module17_vle_validation_summary.json` at test time and
+compare every targeted production metric with exact equality. Expected values are
+not regenerated from the framework. Coverage is ch4_c2 bubble 11/17 with 6 not_found;
+ch4_c2 dew 15/17 with 2 not_found; ch4_c3 bubble 20/23 with 3 not_found; ch4_c3 dew 7/23
+with 2 not_found and 14 inconclusive. No qualitative model verdict is encoded.
+
+`module17_legacy.py` records the approved distinctions as `LegacyDiscrepancy` values:
+
+- LD-1: historical error/U residuals comply with C-2, but counting abs(error/U)<=2
+  against already-expanded 95% U is solely a labelled legacy descriptive statistic.
+  `LegacyDescriptiveStatistics` alone computes the within-two count. Modern
+  aggregation rejects this type and never exposes it as uncertainty agreement.
+- LD-2: historical composition MAE flattens components. Eleven binary cases give
+  22 PER_COMPONENT observations, with correlated errors. PER_CASE_VECTOR
+  MEAN_ABS_COMPONENT is also exposed with 11 observations; floating-point operation
+  order can give a tiny difference. These are separately labelled statistics.
+- LD-3: historical failure_count equals not_found + inconclusive + other_failure.
+  Modern coverage retains the three structured categories rather than merging them.
+
+Each discrepancy records identifier, metric, legacy definition/value, new
+definition/value, cause, scientific assessment and changes_documented_conclusion.
+LD-1, LD-2 and LD-3 have that flag False. If a new discrepancy changes a documented
+scientific conclusion, implementation must stop for review instead of reproducing
+an erroneous legacy value or silently changing the conclusion.
+
+## Source-anomaly sensitivity
+
+`module17_anomaly_subset` reads the exact source_anomalies reason from the protected
+manifest. Its ch4_c3 subset excludes only identities
+`may2015_ch4_c3_023::bubble_point` and `may2015_ch4_c3_023::dew_point`.
+Implementation never compares temperatures to select the subset. A test reads the
+legacy CSV to verify identity equivalence with the historical 283.38 K rule.
+`SensitivityAnalysis` retains the full-dataset primary aggregate, the alternate
+aggregate, the cited subset definition and alternate-minus-primary shifts. Records
+are neither mutated nor marked EXCLUDED. The original case and result remain intact.
+Every protected sensitivity field is tested exactly, including 20-to-19 bubble and
+7-to-6 dew counts and the AARD, RMS-relative and bias shifts.
+
+## Deterministic serialization and deferred work
+
+Existing record, dataset and run serializers emit compact UTF-8 JSON with a trailing
+newline and round-trip float representation. `encode_scientific_artifact` and
+`decode_scientific_artifact` cover every registered new type, including enums,
+comparisons, explicit undefined/not-assessed states, policies, aggregates, summaries,
+legacy records and sensitivity. The registry is closed to the validation modules;
+unknown types, enums, fields, duplicate JSON keys and non-finite values are rejected.
+Encode/decode/encode is byte-identical. Run metadata remains separate from stable
+reproduction inputs and retains deterministic dataset/record ordering.
+
+Deferred: covariance machinery, retrospective diagnostic summaries, UI/dashboard,
+CH4+C3 dew-branch investigation, CoolProp, CO2, new datasets, real tolerances,
+uncertainty propagation and any engine, kij, solver or orchestration change.
diff --git a/src/pvt_phase_simulator_validation/__init__.py b/src/pvt_phase_simulator_validation/__init__.py
index c298049..bf1862a 100644
--- a/src/pvt_phase_simulator_validation/__init__.py
+++ b/src/pvt_phase_simulator_validation/__init__.py
@@ -1,21 +1,61 @@
 """Versioned, immutable core types for OpenPhase validation datasets."""
 
+from .aggregates import (
+    CoverageBlock,
+    ExperimentalQuantityAggregate,
+    GroupingKey,
+    MetricResult,
+    ObservationUnit,
+    QuantityAggregate,
+    UncertaintyAgreementCount,
+    VectorReduction,
+    aggregate_group,
+    format_metric,
+)
 from .aggregation import (
     CrossCheckAgreementSummary,
     ExperimentalAccuracySummary,
+    aggregate_cross_check_agreement,
+    aggregate_experimental_accuracy,
     homogeneous_data_class,
     summarize_cross_check_agreement,
     summarize_experimental_accuracy,
 )
+from .comparisons import (
+    Agreement,
+    AppliedUncertainty,
+    CaseComparison,
+    ComparisonKey,
+    ComparisonState,
+    NotAssessed,
+    ObservationErrors,
+    QuantityComparison,
+    Reason,
+    SolverOutcome,
+    ToleranceAssessment,
+    ToleranceBinding,
+    UncertaintyAssessment,
+    UncertaintyCriterion,
+    UncertaintyDerivation,
+    UncertaintyScope,
+    UndefinedMetric,
+    align_values,
+    compare_record,
+    solver_outcome,
+)
 from .enums import (
     CapabilityUnderTest,
     DataClass,
     PredictionOutcome,
+    ToleranceKind,
     UncertaintyKind,
     ValidationQuantity,
     ValidationStatus,
+    ValuePhase,
 )
 from .exceptions import (
+    ComparisonAlignmentError,
+    ComponentAlignmentError,
     HashMismatchError,
     InvariantViolationError,
     MixedDataClassError,
@@ -26,6 +66,7 @@ from .exceptions import (
 )
 from .hashing import normalize_sha256, verify_sha256
 from .json_values import FrozenJsonObject, JsonScalar, JsonValue
+from .metrics import METRIC_POLICY, MetricName, MetricPolicy, MetricState
 from .models import (
     MOLE_FRACTION_SUM_ABSOLUTE_TOLERANCE,
     SCHEMA_VERSION,
@@ -50,6 +91,13 @@ from .module17_adapter import (
     adapt_module17_evidence,
     load_module17_validation_evidence,
 )
+from .module17_legacy import (
+    LegacyDescriptiveStatistics,
+    LegacyDiscrepancy,
+    legacy_descriptive_statistics,
+    module17_anomaly_subset,
+    module17_discrepancies,
+)
 from .provenance import (
     CompoundIdentity,
     OriginalUnit,
@@ -57,6 +105,16 @@ from .provenance import (
     Uncertainty,
     UnitConversion,
 )
+from .scientific_serialization import (
+    decode_scientific_artifact,
+    encode_scientific_artifact,
+)
+from .sensitivity import (
+    MetricShift,
+    SensitivityAnalysis,
+    SubsetDefinition,
+    analyze_sensitivity,
+)
 from .serialization import (
     decode_reference_dataset,
     decode_validation_record,
@@ -107,6 +165,8 @@ __all__ = [
     "ValidationRecord",
     "ValidationRun",
     "ValidationStatus",
+    "ValuePhase",
+    "ToleranceKind",
     "adapt_module17_evidence",
     "decode_reference_dataset",
     "decode_validation_record",
@@ -122,3 +182,56 @@ __all__ = [
     "summarize_experimental_accuracy",
     "verify_sha256",
 ]
+
+__all__ += [
+    "aggregate_experimental_accuracy",
+    "aggregate_cross_check_agreement",
+    "CoverageBlock",
+    "GroupingKey",
+    "MetricResult",
+    "MetricState",
+    "ObservationUnit",
+    "VectorReduction",
+    "QuantityAggregate",
+    "ExperimentalQuantityAggregate",
+    "UncertaintyAgreementCount",
+    "aggregate_group",
+    "format_metric",
+    "ComparisonKey",
+    "ToleranceBinding",
+    "NotAssessed",
+    "Reason",
+    "Agreement",
+    "AppliedUncertainty",
+    "UncertaintyDerivation",
+    "UncertaintyScope",
+    "UncertaintyCriterion",
+    "UncertaintyAssessment",
+    "ToleranceAssessment",
+    "ObservationErrors",
+    "QuantityComparison",
+    "CaseComparison",
+    "ComparisonState",
+    "SolverOutcome",
+    "align_values",
+    "compare_record",
+    "solver_outcome",
+    "ComparisonAlignmentError",
+    "ComponentAlignmentError",
+    "METRIC_POLICY",
+    "MetricPolicy",
+    "MetricName",
+    "SubsetDefinition",
+    "SensitivityAnalysis",
+    "MetricShift",
+    "analyze_sensitivity",
+    "LegacyDescriptiveStatistics",
+    "LegacyDiscrepancy",
+    "legacy_descriptive_statistics",
+    "module17_discrepancies",
+    "module17_anomaly_subset",
+    "encode_scientific_artifact",
+    "decode_scientific_artifact",
+]
+
+__all__ += ["UndefinedMetric"]
diff --git a/src/pvt_phase_simulator_validation/aggregation.py b/src/pvt_phase_simulator_validation/aggregation.py
index 1be436b..b2349ea 100644
--- a/src/pvt_phase_simulator_validation/aggregation.py
+++ b/src/pvt_phase_simulator_validation/aggregation.py
@@ -5,6 +5,15 @@ from __future__ import annotations
 from collections.abc import Iterable
 from dataclasses import dataclass
 
+from .aggregates import (
+    ExperimentalQuantityAggregate,
+    GroupingKey,
+    ObservationUnit,
+    QuantityAggregate,
+    VectorReduction,
+    aggregate_group,
+)
+from .comparisons import CaseComparison
 from .enums import DataClass
 from .exceptions import MixedDataClassError
 from .models import ValidationRecord
@@ -34,14 +43,28 @@ def homogeneous_data_class(records: Iterable[ValidationRecord]) -> DataClass:
 
 @dataclass(frozen=True, slots=True)
 class ExperimentalAccuracySummary:
-    """Experimental records available for later accuracy calculations."""
+    """Experimental error, accuracy and reference-uncertainty agreement."""
 
     accuracy_records: tuple[ValidationRecord, ...]
+    accuracy_aggregates: tuple[ExperimentalQuantityAggregate, ...] = ()
 
     def __post_init__(self) -> None:
+        aggregates = tuple(self.accuracy_aggregates)
+        if any(
+            not isinstance(a, ExperimentalQuantityAggregate)
+            or a.grouping_key.identity.data_class
+            is not DataClass.EXPERIMENTAL_VALIDATION
+            for a in aggregates
+        ):
+            raise MixedDataClassError("accuracy aggregates must be experimental")
+        object.__setattr__(self, "accuracy_aggregates", aggregates)
         records = tuple(self.accuracy_records)
         object.__setattr__(self, "accuracy_records", records)
-        data_class = homogeneous_data_class(records)
+        data_class = (
+            homogeneous_data_class(records)
+            if records
+            else DataClass.EXPERIMENTAL_VALIDATION
+        )
         if data_class is not DataClass.EXPERIMENTAL_VALIDATION:
             raise MixedDataClassError(
                 "ExperimentalAccuracySummary accepts only "
@@ -51,14 +74,29 @@ class ExperimentalAccuracySummary:
 
 @dataclass(frozen=True, slots=True)
 class CrossCheckAgreementSummary:
-    """Numerical cross-check records available for later agreement calculations."""
+    """Numerical differences and model-to-model discrepancy."""
 
     agreement_records: tuple[ValidationRecord, ...]
+    agreement_aggregates: tuple[QuantityAggregate, ...] = ()
 
     def __post_init__(self) -> None:
+        aggregates = tuple(self.agreement_aggregates)
+        if any(
+            type(a) is not QuantityAggregate
+            or a.grouping_key.identity.data_class is not DataClass.NUMERICAL_CROSS_CHECK
+            for a in aggregates
+        ):
+            raise MixedDataClassError(
+                "agreement aggregates must be numerical cross-checks"
+            )
+        object.__setattr__(self, "agreement_aggregates", aggregates)
         records = tuple(self.agreement_records)
         object.__setattr__(self, "agreement_records", records)
-        data_class = homogeneous_data_class(records)
+        data_class = (
+            homogeneous_data_class(records)
+            if records
+            else DataClass.NUMERICAL_CROSS_CHECK
+        )
         if data_class is not DataClass.NUMERICAL_CROSS_CHECK:
             raise MixedDataClassError(
                 "CrossCheckAgreementSummary accepts only NUMERICAL_CROSS_CHECK records"
@@ -83,3 +121,87 @@ def summarize_cross_check_agreement(
     materialized = tuple(records)
     homogeneous_data_class(materialized)
     return CrossCheckAgreementSummary(materialized)
+
+
+def _aggregate_comparisons(
+    cases: Iterable[CaseComparison],
+    expected: DataClass,
+    *,
+    pooled_across_systems: bool = False,
+    vector_observation_unit: ObservationUnit = ObservationUnit.PER_COMPONENT,
+    reduction: VectorReduction | None = None,
+) -> tuple[QuantityAggregate, ...]:
+    materialized = tuple(cases)
+    if any(not isinstance(c, CaseComparison) for c in materialized):
+        raise TypeError("modern aggregation accepts CaseComparison only")
+    if any(c.identity.data_class is not expected for c in materialized):
+        raise MixedDataClassError("aggregate input has an incompatible data class")
+    keys = {
+        GroupingKey(c.identity, c.system_id, c.capability, q.key)
+        for c in materialized
+        for q in c.quantity_comparisons
+    }
+    if pooled_across_systems:
+        keys |= {
+            GroupingKey(k.identity, None, k.capability, k.comparison_key, True)
+            for k in tuple(keys)
+        }
+    results = []
+    for key in sorted(keys, key=repr):
+        group = tuple(
+            c
+            for c in materialized
+            if c.identity == key.identity
+            and c.capability == key.capability
+            and (key.pooled_across_systems or c.system_id == key.system_id)
+        )
+        vector = any(
+            q.component_ids is not None
+            for c in group
+            for q in c.quantity_comparisons
+            if q.key == key.comparison_key
+        )
+        unit = vector_observation_unit if vector else ObservationUnit.PER_CASE_SCALAR
+        results.append(aggregate_group(group, key, unit, reduction if vector else None))
+    return tuple(results)
+
+
+def aggregate_experimental_accuracy(
+    cases: Iterable[CaseComparison],
+    *,
+    pooled_across_systems: bool = False,
+    vector_observation_unit: ObservationUnit = ObservationUnit.PER_COMPONENT,
+    reduction: VectorReduction | None = None,
+) -> ExperimentalAccuracySummary:
+    """Experimental error, accuracy and reference-uncertainty agreement."""
+    aggregates = _aggregate_comparisons(
+        cases,
+        DataClass.EXPERIMENTAL_VALIDATION,
+        pooled_across_systems=pooled_across_systems,
+        vector_observation_unit=vector_observation_unit,
+        reduction=reduction,
+    )
+    experimental = tuple(
+        a for a in aggregates if isinstance(a, ExperimentalQuantityAggregate)
+    )
+    return ExperimentalAccuracySummary((), experimental)
+
+
+def aggregate_cross_check_agreement(
+    cases: Iterable[CaseComparison],
+    *,
+    pooled_across_systems: bool = False,
+    vector_observation_unit: ObservationUnit = ObservationUnit.PER_COMPONENT,
+    reduction: VectorReduction | None = None,
+) -> CrossCheckAgreementSummary:
+    """Numerical difference and model-to-model discrepancy, never experimental truth."""
+    return CrossCheckAgreementSummary(
+        (),
+        _aggregate_comparisons(
+            cases,
+            DataClass.NUMERICAL_CROSS_CHECK,
+            pooled_across_systems=pooled_across_systems,
+            vector_observation_unit=vector_observation_unit,
+            reduction=reduction,
+        ),
+    )
diff --git a/src/pvt_phase_simulator_validation/enums.py b/src/pvt_phase_simulator_validation/enums.py
index 6c59020..f6c3d38 100644
--- a/src/pvt_phase_simulator_validation/enums.py
+++ b/src/pvt_phase_simulator_validation/enums.py
@@ -99,11 +99,17 @@ class PredictionOutcome(StrEnum):
 class ValidationStatus(StrEnum):
     """Allowed interpretation attached to a validation record."""
 
-    AGREES_WITHIN_UNCERTAINTY = "AGREES_WITHIN_UNCERTAINTY"
-    OUTSIDE_UNCERTAINTY = "OUTSIDE_UNCERTAINTY"
-    AGREES_WITHIN_DECLARED_TOLERANCE = "AGREES_WITHIN_DECLARED_TOLERANCE"
-    OUTSIDE_DECLARED_TOLERANCE = "OUTSIDE_DECLARED_TOLERANCE"
     REPORTED_NO_TOLERANCE = "REPORTED_NO_TOLERANCE"
     SOLVER_FAILURE = "SOLVER_FAILURE"
-    REFERENCE_UNAVAILABLE = "REFERENCE_UNAVAILABLE"
     EXCLUDED = "EXCLUDED"
+
+
+class ValuePhase(StrEnum):
+    LIQUID = "LIQUID"
+    VAPOR = "VAPOR"
+    OVERALL = "OVERALL"
+
+
+class ToleranceKind(StrEnum):
+    ABSOLUTE = "ABSOLUTE"
+    RELATIVE = "RELATIVE"
diff --git a/src/pvt_phase_simulator_validation/exceptions.py b/src/pvt_phase_simulator_validation/exceptions.py
index c58a4b1..ce042f8 100644
--- a/src/pvt_phase_simulator_validation/exceptions.py
+++ b/src/pvt_phase_simulator_validation/exceptions.py
@@ -29,3 +29,11 @@ class SerializationError(ValidationFrameworkError):
 
 class HashMismatchError(ValidationFrameworkError):
     """Raised when supplied content does not have the expected digest."""
+
+
+class ComparisonAlignmentError(InvariantViolationError):
+    """Quantities, phases or canonical bases do not align."""
+
+
+class ComponentAlignmentError(ComparisonAlignmentError):
+    """Component identities do not uniquely align."""
diff --git a/src/pvt_phase_simulator_validation/models.py b/src/pvt_phase_simulator_validation/models.py
index 8da8eb7..4a1c3e6 100644
--- a/src/pvt_phase_simulator_validation/models.py
+++ b/src/pvt_phase_simulator_validation/models.py
@@ -15,15 +15,23 @@ from .enums import (
     CapabilityUnderTest,
     DataClass,
     PredictionOutcome,
+    ToleranceKind,
     ValidationQuantity,
     ValidationStatus,
+    ValuePhase,
+)
+from .exceptions import (
+    ComparisonAlignmentError,
+    ComponentAlignmentError,
+    InvariantViolationError,
+    MixedDataClassError,
+    SchemaVersionError,
 )
-from .exceptions import InvariantViolationError, MixedDataClassError, SchemaVersionError
 from .hashing import normalize_sha256
 from .json_values import FrozenJsonObject, JsonValue, freeze_json
 from .provenance import SourceManifest, Uncertainty
 
-SCHEMA_VERSION = "1.1"
+SCHEMA_VERSION = "1.2"
 SUPPORTED_SCHEMA_VERSIONS = frozenset({SCHEMA_VERSION})
 MOLE_FRACTION_SUM_ABSOLUTE_TOLERANCE = 1.0e-12
 
@@ -31,6 +39,11 @@ MOLE_FRACTION_SUM_ABSOLUTE_TOLERANCE = 1.0e-12
 def require_supported_schema_version(schema_version: str) -> None:
     """Reject contracts this reader does not implement."""
 
+    if schema_version == "1.1":
+        raise SchemaVersionError(
+            "1.1 records cannot be converted because phase identity, component "
+            "identity and per-quantity assessment semantics would have to be guessed"
+        )
     if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
         raise SchemaVersionError(
             f"unsupported schema_version {schema_version!r}; "
@@ -72,6 +85,38 @@ def _normalize_value(value: Value, field_name: str) -> Value:
     return normalized_vector
 
 
+def validate_value_identity(
+    quantity: ValidationQuantity,
+    phase: ValuePhase | None,
+    value: Value,
+    component_ids: tuple[str, ...] | None,
+) -> None:
+    phased = quantity in {
+        ValidationQuantity.MOLE_FRACTION,
+        ValidationQuantity.COMPRESSIBILITY_FACTOR,
+        ValidationQuantity.DENSITY,
+    }
+    if phased:
+        if phase is None:
+            raise ComparisonAlignmentError(f"{quantity} requires phase")
+        require_enum(phase, ValuePhase, "phase")
+    elif phase is not None:
+        raise ComparisonAlignmentError(f"{quantity} forbids phase")
+    if isinstance(value, tuple):
+        if (
+            not isinstance(component_ids, tuple)
+            or len(component_ids) != len(value)
+            or len(set(component_ids)) != len(component_ids)
+        ):
+            raise ComponentAlignmentError(
+                f"{quantity} vector requires unique component_ids of matching length"
+            )
+        for component in component_ids:
+            require_non_empty(component, "component_id")
+    elif component_ids is not None:
+        raise ComponentAlignmentError("scalar forbids component_ids")
+
+
 @dataclass(frozen=True, slots=True)
 class ReferenceValue:
     """A canonical-SI source value, optionally with reported uncertainty."""
@@ -79,6 +124,8 @@ class ReferenceValue:
     quantity: ValidationQuantity
     value: Value
     uncertainty: Uncertainty | None = None
+    phase: ValuePhase | None = None
+    component_ids: tuple[str, ...] | None = None
 
     def __post_init__(self) -> None:
         require_enum(self.quantity, ValidationQuantity, "quantity")
@@ -106,6 +153,10 @@ class ReferenceValue:
                     "uncertainty vector length must match the reference-value vector"
                 )
 
+        validate_value_identity(
+            self.quantity, self.phase, self.value, self.component_ids
+        )
+
 
 @dataclass(frozen=True, slots=True)
 class PredictionValue:
@@ -113,6 +164,8 @@ class PredictionValue:
 
     quantity: ValidationQuantity
     value: Value
+    phase: ValuePhase | None = None
+    component_ids: tuple[str, ...] | None = None
 
     def __post_init__(self) -> None:
         require_enum(self.quantity, ValidationQuantity, "quantity")
@@ -120,10 +173,18 @@ class PredictionValue:
             self, "value", _normalize_value(self.value, "prediction value")
         )
 
+        validate_value_identity(
+            self.quantity, self.phase, self.value, self.component_ids
+        )
+
 
 def _validate_mole_fraction_vector(
     value: ReferenceValue | PredictionValue, component_ids: tuple[str, ...]
 ) -> None:
+    if isinstance(value.value, tuple) and set(value.component_ids or ()) != set(
+        component_ids
+    ):
+        raise ComponentAlignmentError("vector component_ids must match owning case")
     if value.quantity is not ValidationQuantity.MOLE_FRACTION:
         return
     if not isinstance(value.value, tuple):
@@ -281,6 +342,7 @@ class DeclaredTolerance:
     justification: str
     source_citation: str
     scope: str
+    tolerance_kind: ToleranceKind
 
     def __post_init__(self) -> None:
         require_enum(self.quantity, ValidationQuantity, "quantity")
@@ -289,27 +351,22 @@ class DeclaredTolerance:
             raise ValueError("tolerance value must be non-negative")
         object.__setattr__(self, "value", float(self.value))
         require_non_empty(self.unit, "unit")
-        if self.unit != self.quantity.canonical_si_unit:
-            raise ValueError("tolerance unit must be the quantity's canonical SI unit")
+        require_enum(self.tolerance_kind, ToleranceKind, "tolerance_kind")
+        if self.tolerance_kind is ToleranceKind.RELATIVE:
+            if not self.quantity.relative_error_meaningful:
+                raise ValueError("relative tolerance forbidden for this quantity")
+            expected_unit = "1"
+        else:
+            expected_unit = self.quantity.canonical_si_unit
+        if self.unit != expected_unit:
+            raise ComparisonAlignmentError(
+                "tolerance unit must match its kind and canonical SI basis"
+            )
         require_non_empty(self.justification, "justification")
         require_non_empty(self.source_citation, "source_citation")
         require_non_empty(self.scope, "scope")
 
 
-_UNCERTAINTY_STATUSES = frozenset(
-    {
-        ValidationStatus.AGREES_WITHIN_UNCERTAINTY,
-        ValidationStatus.OUTSIDE_UNCERTAINTY,
-    }
-)
-_TOLERANCE_STATUSES = frozenset(
-    {
-        ValidationStatus.AGREES_WITHIN_DECLARED_TOLERANCE,
-        ValidationStatus.OUTSIDE_DECLARED_TOLERANCE,
-    }
-)
-
-
 @dataclass(frozen=True, slots=True, init=False)
 class ValidationRecord:
     """A dataset-bound case/prediction pairing with no computed error metrics."""
@@ -318,7 +375,6 @@ class ValidationRecord:
     prediction: ValidationPrediction
     status: ValidationStatus = ValidationStatus.REPORTED_NO_TOLERANCE
     exclusion_reason: str | None = None
-    declared_tolerance: DeclaredTolerance | None = None
     identity: DatasetIdentity = field(init=False)
 
     @property
@@ -333,13 +389,11 @@ class ValidationRecord:
         prediction: ValidationPrediction,
         status: ValidationStatus = ValidationStatus.REPORTED_NO_TOLERANCE,
         exclusion_reason: str | None = None,
-        declared_tolerance: DeclaredTolerance | None = None,
     ) -> None:
         object.__setattr__(self, "case", case)
         object.__setattr__(self, "prediction", prediction)
         object.__setattr__(self, "status", status)
         object.__setattr__(self, "exclusion_reason", exclusion_reason)
-        object.__setattr__(self, "declared_tolerance", declared_tolerance)
         self.__post_init__()
 
     def __post_init__(self) -> None:
@@ -366,26 +420,10 @@ class ValidationRecord:
             raise InvariantViolationError(
                 "exclusion_reason is only valid with EXCLUDED status"
             )
-        if self.status in _TOLERANCE_STATUSES:
-            if self.declared_tolerance is None:
-                raise InvariantViolationError(
-                    "declared-tolerance status requires a DeclaredTolerance"
-                )
-        elif self.declared_tolerance is not None:
-            raise InvariantViolationError(
-                "DeclaredTolerance is only valid with a declared-tolerance status"
-            )
-        if self.status in _UNCERTAINTY_STATUSES:
-            if self.identity.data_class is not DataClass.EXPERIMENTAL_VALIDATION:
-                raise InvariantViolationError(
-                    "uncertainty status is only valid for experimental validation"
-                )
-            if not any(
-                value.uncertainty is not None for value in self.case.reference_values
-            ):
-                raise InvariantViolationError(
-                    "uncertainty status requires a source-reported uncertainty"
-                )
+        for values in (self.case.reference_values, self.prediction.values):
+            keys = tuple((value.quantity, value.phase) for value in values)
+            if len(keys) != len(set(keys)):
+                raise ComparisonAlignmentError("duplicate quantity/phase key in record")
         for value in self.prediction.values:
             _validate_mole_fraction_vector(value, self.case.component_ids)
 
diff --git a/src/pvt_phase_simulator_validation/module17_adapter.py b/src/pvt_phase_simulator_validation/module17_adapter.py
index 6b1c6ed..0513ab4 100644
--- a/src/pvt_phase_simulator_validation/module17_adapter.py
+++ b/src/pvt_phase_simulator_validation/module17_adapter.py
@@ -17,6 +17,7 @@ from .enums import (
     UncertaintyKind,
     ValidationQuantity,
     ValidationStatus,
+    ValuePhase,
 )
 from .hashing import verify_sha256
 from .json_values import FrozenJsonObject
@@ -418,21 +419,29 @@ def _case(
         specified_composition = ReferenceValue(
             quantity=ValidationQuantity.MOLE_FRACTION,
             value=liquid,
+            phase=ValuePhase.LIQUID,
+            component_ids=(source_row["component_1_id"], source_row["component_2_id"]),
         )
         opposite_composition = ReferenceValue(
             quantity=ValidationQuantity.MOLE_FRACTION,
             value=vapor,
+            phase=ValuePhase.VAPOR,
+            component_ids=(source_row["component_1_id"], source_row["component_2_id"]),
             uncertainty=vapor_uncertainty,
         )
     else:
         specified_composition = ReferenceValue(
             quantity=ValidationQuantity.MOLE_FRACTION,
             value=vapor,
+            phase=ValuePhase.VAPOR,
+            component_ids=(source_row["component_1_id"], source_row["component_2_id"]),
             uncertainty=vapor_uncertainty,
         )
         opposite_composition = ReferenceValue(
             quantity=ValidationQuantity.MOLE_FRACTION,
             value=liquid,
+            phase=ValuePhase.LIQUID,
+            component_ids=(source_row["component_1_id"], source_row["component_2_id"]),
         )
     return ValidationCase(
         case_id=_case_id(source_row["source_point_id"], capability),
@@ -505,6 +514,7 @@ def _prediction(
     case_id: str,
     capability: CapabilityUnderTest,
     retrospective_interpretation: str,
+    component_ids: tuple[str, ...],
 ) -> ValidationPrediction:
     direction = "bubble" if capability is CapabilityUnderTest.BUBBLE_POINT else "dew"
     legacy_outcome = legacy_row[f"{direction}_status"]
@@ -545,6 +555,10 @@ def _prediction(
                 PredictionValue(
                     ValidationQuantity.MOLE_FRACTION,
                     predicted_composition,
+                    phase=ValuePhase.VAPOR
+                    if direction == "bubble"
+                    else ValuePhase.LIQUID,
+                    component_ids=component_ids,
                 ),
             ),
             diagnostics=diagnostics,
@@ -654,6 +668,7 @@ def load_module17_validation_evidence(
                 case.case_id,
                 capability,
                 retrospective_interpretation,
+                case.component_ids,
             )
             status = (
                 ValidationStatus.REPORTED_NO_TOLERANCE
diff --git a/src/pvt_phase_simulator_validation/provenance.py b/src/pvt_phase_simulator_validation/provenance.py
index f5a8a3f..df67a00 100644
--- a/src/pvt_phase_simulator_validation/provenance.py
+++ b/src/pvt_phase_simulator_validation/provenance.py
@@ -68,7 +68,7 @@ class UnitConversion:
 class Uncertainty:
     """A source-reported uncertainty in the quantity's canonical SI unit."""
 
-    value: float | tuple[float, ...]
+    value: float | tuple[float | None, ...]
     kind: UncertaintyKind
     coverage_factor: float | None
     confidence_level_percent: float | None
@@ -88,6 +88,8 @@ class Uncertainty:
             if not self.value:
                 raise ValueError("uncertainty value vectors must not be empty")
             for item in self.value:
+                if item is None:
+                    continue
                 if isinstance(item, bool) or not isinstance(item, (int, float)):
                     raise TypeError(
                         "uncertainty value vectors must contain only numbers"
@@ -95,7 +97,11 @@ class Uncertainty:
                 require_finite(item, "uncertainty value")
                 if item < 0.0:
                     raise ValueError("uncertainty value must be non-negative")
-            object.__setattr__(self, "value", tuple(float(item) for item in self.value))
+            object.__setattr__(
+                self,
+                "value",
+                tuple(None if item is None else float(item) for item in self.value),
+            )
         require_enum(self.kind, UncertaintyKind, "uncertainty kind")
         if self.coverage_factor is not None:
             require_finite(self.coverage_factor, "coverage_factor")
diff --git a/src/pvt_phase_simulator_validation/serialization.py b/src/pvt_phase_simulator_validation/serialization.py
index 40b2b43..128980d 100644
--- a/src/pvt_phase_simulator_validation/serialization.py
+++ b/src/pvt_phase_simulator_validation/serialization.py
@@ -12,9 +12,11 @@ from .enums import (
     CapabilityUnderTest,
     DataClass,
     PredictionOutcome,
+    ToleranceKind,
     UncertaintyKind,
     ValidationQuantity,
     ValidationStatus,
+    ValuePhase,
 )
 from .exceptions import (
     InvariantViolationError,
@@ -133,7 +135,7 @@ def _identity_from(payload: object) -> DatasetIdentity:
 
 def _uncertainty_payload(value: Uncertainty) -> dict[str, object]:
     return {
-        "value": _value_payload(value.value),
+        "value": list(value.value) if isinstance(value.value, tuple) else value.value,
         "kind": value.kind.value,
         "coverage_factor": value.coverage_factor,
         "confidence_level_percent": value.confidence_level_percent,
@@ -152,7 +154,11 @@ def _uncertainty_from(payload: object) -> Uncertainty:
     )
     _require_keys(item, fields, "uncertainty")
     return Uncertainty(
-        value=_value_from(item["value"], "uncertainty.value"),
+        value=(
+            tuple(_optional_number(v, "uncertainty.value") for v in item["value"])
+            if isinstance(item["value"], list)
+            else _number(item["value"], "uncertainty.value")
+        ),
         kind=_enum(item["kind"], UncertaintyKind, "uncertainty.kind"),
 
… [truncated, 13086 more characters]
```

## Your task

Attempt to FALSIFY this implementation.

Investigate the repository directly with your read-only tools — do not rely on
the summaries above. Independently reproduce anything numerical that matters.
Look specifically for:

- scientific error: wrong equation, wrong units, wrong sign, wrong branch
- tests that cannot fail, or that were weakened to pass
- silent scope creep, or a protected artifact quietly changed
- failure paths that return a plausible answer instead of an error
- claims in documentation that the code does not support

## Required final output

Write the full human-readable audit first, then end with exactly one
machine-readable block:

<ORCHESTRATOR_RESULT>
{
  "verdict": "APPROVED",
  "findings": [
    {"id": "C-1", "severity": "C", "blocks": true, "summary": "..."}
  ],
  "safe_defer": []
}
</ORCHESTRATOR_RESULT>

`verdict` must be exactly one of APPROVED, CONDITIONAL, NOT_APPROVED.
`severity` must be A (critical), B (major), C (moderate) or D (minor).
`blocks` must be a boolean.

If you cannot complete the audit, return NOT_APPROVED with a finding that
explains why. A missing or malformed block is never read as approval.
