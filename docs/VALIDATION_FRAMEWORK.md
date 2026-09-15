# Validation framework: schema 1.2 and scientific comparisons

Software correctness and model accuracy are separate. Deterministic unit,
invariant, regression and golden-master checks may gate CI. Prediction error
against experiment does not gate CI merely because Peng–Robinson disagrees with a
measurement. There is no global pass badge, accuracy boolean, default tolerance or
invented acceptance threshold. The scientific engine and protected Module 17
artifacts remain unchanged.

## Identity, source values and schema evolution

`DatasetIdentity` retains dataset ID, version and `DataClass` on every case and
record. Experimental data and numerical cross-check data cannot share an aggregate.
`ReferenceDataset` checks case and manifest identity. Provenance retains citation,
source hashes, archive and extraction information, uncertainty definitions and unit
conversions. `verify_sha256` checks supplied bytes; merely constructing a manifest
checks digest syntax, not external content.

`SCHEMA_VERSION = "1.2"`; the supported set contains only `"1.2"`. New writes emit
1.2. A 1.1 envelope raises `SchemaVersionError` before constructing records: phase
identity, component identity and per-quantity assessment semantics would have to be
guessed. There is no migration helper. Module 17 records are regenerated in memory
from the protected evidence, where those identities are known.

`ReferenceValue` and `PredictionValue` are finite canonical-SI values. `ValuePhase`
is LIQUID, VAPOR or OVERALL, and is required for MOLE_FRACTION,
COMPRESSIBILITY_FACTOR and DENSITY. It must be absent for PRESSURE, TEMPERATURE and
VAPOR_FRACTION. Every vector supplies unique `component_ids`, one per entry,
matching exactly the owning case's component set. Scalars forbid component IDs.
The reference uncertainty vector follows its owning reference value's component
order. Predictions are reordered by component identity, never compared by assumed
array position. Quantity, phase, component and basis mismatches raise alignment
errors. Density means mass density in kg/m^3; molar density is unrepresentable.
If a basis field is introduced later, it must join the comparison key.

Mole fractions retain their structural [0, 1] and normalization checks. The named
`MOLE_FRACTION_SUM_ABSOLUTE_TOLERANCE` is solely an input-shape invariant, not a
scientific accuracy tolerance. Negative and non-finite uncertainty are rejected.
Explicit source-stated zero is retained. A missing vector component is `None`,
never imputed or omitted from assessment.

`ValidationStatus` is lifecycle-only: REPORTED_NO_TOLERANCE means prediction
recorded, with scientific assessments on quantity comparisons; SOLVER_FAILURE
requires a FAILURE prediction and vice versa; EXCLUDED requires an exclusion reason,
and an exclusion reason requires EXCLUDED. The record has no declared-tolerance
field and no agreement status. A VALUE prediction contains finite values and no
failure reason. A FAILURE contains no values and retains its reason and diagnostics.
Diagnostics and solver metadata remain deeply immutable JSON.

## Comparison and solver outcomes

`compare_record(record, capability, ...)` derives `CaseComparison` without changing
the record. Capability is supplied explicitly from the owning dataset; it is never
inferred from text. Comparisons use `ComparisonKey(quantity, phase)` and reject
duplicate reference or prediction keys within a record. The union of reference and
prediction keys produces COMPARED, REFERENCE_UNAVAILABLE, NOT_PREDICTED,
PREDICTION_UNAVAILABLE or EXCLUDED. Errors and assessments exist only for COMPARED;
non-comparisons carry explicit `NotAssessed` reasons.

`SolverOutcome` is separate from agreement. Module 17 reads only the structured
`solver_metadata["legacy_solver_outcome"]`: converged, not_found or inconclusive.
A VALUE is CONVERGED; a FAILURE without structured classification is OTHER_FAILURE.
Failure prose is never parsed. CONVERGED holds if and only if the prediction is
VALUE. NOT_FOUND means the configured numerical search found no acceptable
solution; it does **not** prove that no physical solution exists. INCONCLUSIVE stays
distinct and queryable.

## C-1: uncertainty belongs to the exact reference value

The previous record-level `any(reference.uncertainty)` guard and the statuses it
protected have been removed. The comparison receives the exact `ReferenceValue`
and uses only that object's uncertainty. No lookup by quantity across a case, no
specified-condition uncertainty, and no different-phase uncertainty can substitute.
For Module 17 dew, the specified vapor composition carries U=(0.025, 0.025), but the
reference liquid composition has no uncertainty. The liquid comparison therefore
reports NO_REFERENCE_UNCERTAINTY. Its pressure uncertainty is also inapplicable.

Only EXPERIMENTAL_VALIDATION permits uncertainty assessment. Every numerical
cross-check comparison carries `NotAssessed(NOT_EXPERIMENTAL)`.

## C-2: published and derived uncertainty are distinct

`AppliedUncertainty` retains kind_used (STANDARD or EXPANDED), derivation (PUBLISHED
or EXPANDED_FROM_STANDARD), the actual denominator, source-stated coverage factor,
source-stated confidence level and serialized scope REFERENCE_ONLY. Published U is
used directly; a coverage factor never multiplies it again. Published u is used as
u. Deriving U=k*u requires STANDARD source uncertainty, an explicit published k,
and caller opt-in `derive_expanded=True`. The derivation remains labelled and is
never pooled with published U. Unknown k remains None; 95% confidence does not imply
k=2. There is no U-to-u derivation.

Exactly one residual field is populated: `expanded_normalized_residual = error/U`
or `standard_normalized_residual = error/u`. The scalar criterion is the computed
`abs(normalized_residual) <= 1`. Vector comparisons use
ALL_COMPONENTS_WITHIN_REFERENCE_UNCERTAINTY: every component must have usable
uncertainty, and `max(abs(normalized_i)) <= 1`. Every residual remains accessible.
Missing any component yields MISSING_COMPONENT_UNCERTAINTY for the whole vector;
zero scalar or component denominator yields ZERO_UNCERTAINTY_DENOMINATOR. No partial
maximum, epsilon, infinity or NaN is used. This is component-wise agreement, never
joint coverage or a joint confidence region.

Module 17's manifest states that complementary methane has the same absolute vapor
composition uncertainty as the published heavy component. The adapter preserves
that provenance. Generalized covariance machinery is deferred.

## Reference-only limitation

Uncertainty assessment compares the prediction only with the reference value's own
published uncertainty. It excludes propagation from input temperature, input
pressure, composition inputs, EOS parameters, covariance, model uncertainty and
sensitivity derivatives. A full budget could only widen the band: OUTSIDE does not
prove disagreement beyond combined uncertainty, and WITHIN does not establish model
adequacy. Scope REFERENCE_ONLY is serialized with the applied uncertainty on every
assessed comparison. No uncertainty-propagation engine is built.

## Declared tolerances coexist with uncertainty

A `DeclaredTolerance` requires quantity, tolerance_kind, finite non-negative value,
unit, justification, source_citation and scope. ABSOLUTE uses the canonical quantity
unit. RELATIVE uses unit `"1"` and a fractional value (0.05 means 5%); it is forbidden
where the quantity disallows relative error. In particular, mol/m^3 is not an
absolute mass-density tolerance unit.

Only an explicit `ToleranceBinding(DatasetIdentity, ComparisonKey, DeclaredTolerance)`
can apply a bound. Scope prose never determines applicability. No binding yields
NO_DECLARED_TOLERANCE. Every vector component must satisfy the bound. Relative bounds
require strictly positive references, with explicit ZERO_REFERENCE_DENOMINATOR or
NEGATIVE_REFERENCE_DENOMINATOR otherwise. There are zero real tolerances in the
package; tests contain synthetic cited fixtures only.

Uncertainty and tolerance assessments have independent slots and no precedence,
combined status or primary assessment. OUTSIDE uncertainty and WITHIN tolerance
coexist and serialize together without reclassification.

## Metric policy and formulas

`METRIC_POLICY` is immutable data with per-observation, primary, enabled and disabled
metrics for each quantity. Pressure enables MAE, bias, RMSE in Pa and AARD, bias,
RMS relative and max absolute relative in percent; primary metrics are AARD percent,
bias percent and MAE. Temperature enables MAE, bias, RMSE and max absolute error in K;
MAE and bias are primary. Relative temperature error is permitted by the quantity
flag but disabled by policy. Mole and vapor fractions use only absolute MAE, bias,
RMSE and max, with MAE and max primary. A vapor phase-state mismatch is a
classification disagreement, never a small numeric error (policy only).
Compressibility factor enables MAE, bias, RMSE, max, AARD and bias percent. Mass
density enables MAE, max, AARD and bias percent. Both use AARD percent and MAE as
primary metrics and require phase identity.

For errors e=predicted-reference and relatives r=e/reference, the implementation uses
exactly these operation orders with `math.fsum`:

- MAE = fsum(abs(e)) / n; bias = fsum(e) / n.
- RMSE = sqrt(fsum(e*e) / n); max absolute error = max(abs(e)).
- AARD percent = 100.0 * fsum(abs(r)) / n.
- Bias percent = 100.0 * fsum(r) / n.
- RMS relative percent = 100.0 * sqrt(fsum(r*r) / n).
- Max absolute relative percent = 100.0 * max(abs(r)).

Relative metrics require policy permission and a strictly positive finite reference.
`UndefinedMetric` represents invalid per-observation relative denominators explicitly;
absolute errors remain available. Aggregate `MetricResult` has DEFINED or UNDEFINED,
value or reason, sample_count and coverage. No usable observations yields
NO_USABLE_OBSERVATIONS with count zero and value None. If invalid relative references
are the only observations, their denominator reason is retained. With both usable
and invalid references, relative metrics count only usable observations; the original
case coverage and per-observation undefined reasons remain available. Non-finite
predictions are rejected; a producer must record a FAILURE and reason instead.
Arithmetic overflow also never enters serialized metrics as NaN or Infinity.

## Observation units, grouping and coverage

`aggregate_experimental_accuracy` returns `ExperimentalAccuracySummary`;
`aggregate_cross_check_agreement` returns `CrossCheckAgreementSummary`. They accept
`CaseComparison` inputs and reject the other data class or mixed input. The latter
uses numerical difference, model-to-model discrepancy and agreement vocabulary and
has no uncertainty-agreement fields. Reference EOS or CoolProp output is not
experimental truth. The original `summarize_*` helpers remain record containers.

Default grouping is dataset identity (including version), system, capability and
ComparisonKey. Quantities and phases never pool. Optional pooled-across-systems
aggregates are separately labelled and appended without replacing system results.
Each aggregate declares PER_CASE_SCALAR, PER_COMPONENT or PER_CASE_VECTOR, plus its
sample count and grouping. PER_CASE_VECTOR requires MAX_ABS_COMPONENT or
MEAN_ABS_COMPONENT; metrics then describe that named non-negative reduction. All
observations receive equal weight; no inverse-variance weighting is performed.
The default vector unit is PER_COMPONENT. Pressure observations and composition
components never share a statistic. `aggregate_group` accepts an explicit grouping
key even for empty input, allowing complete undefined metrics and zero coverage;
a summary with no inputs has no inferred groups.

Every aggregate and every `MetricResult` carries `CoverageBlock`: total_cases,
excluded_cases, eligible_cases, reference_available_cases, converged, not_found,
inconclusive, other_failure, compared_cases, metric_observation_count and
uncertainty_assessable_count. Eligibility is total minus exclusions, solver outcomes
sum to eligibility, and compared cases cannot exceed either convergence or reference
availability. Failures remain in denominators. `format_metric` prints the value with
case coverage and observation count. Uncertainty agreement counts are grouped by
(kind_used, derivation, coverage_factor, confidence_level_percent); these strata
never merge.

## Module 17 equivalence and legacy distinctions

The read-only adapter retains all 40 source points for each capability. Bubble
specified composition is LIQUID and reference/predicted incipient composition is
VAPOR. Dew reverses those identities. Pressure and temperature have no phase.
Published vapor uncertainty follows the vapor value. Dataset/source identities,
source coordinates, confidence, hashes, diagnostics and production values retain
B's scientific semantics. Retrospective nearest-root and measured-state fugacity
values remain diagnostics and never enter metrics.

Tests read `docs/validation/module17_vle_validation_summary.json` at test time and
compare every targeted production metric with exact equality. Expected values are
not regenerated from the framework. Coverage is ch4_c2 bubble 11/17 with 6 not_found;
ch4_c2 dew 15/17 with 2 not_found; ch4_c3 bubble 20/23 with 3 not_found; ch4_c3 dew 7/23
with 2 not_found and 14 inconclusive. No qualitative model verdict is encoded.

`module17_legacy.py` records the approved distinctions as `LegacyDiscrepancy` values:

- LD-1: historical error/U residuals comply with C-2, but counting abs(error/U)<=2
  against already-expanded 95% U is solely a labelled legacy descriptive statistic.
  `LegacyDescriptiveStatistics` alone computes the within-two count. Modern
  aggregation rejects this type and never exposes it as uncertainty agreement.
- LD-2: historical composition MAE flattens components. Eleven binary cases give
  22 PER_COMPONENT observations, with correlated errors. PER_CASE_VECTOR
  MEAN_ABS_COMPONENT is also exposed with 11 observations; floating-point operation
  order can give a tiny difference. These are separately labelled statistics.
- LD-3: historical failure_count equals not_found + inconclusive + other_failure.
  Modern coverage retains the three structured categories rather than merging them.

Each discrepancy records identifier, metric, legacy definition/value, new
definition/value, cause, scientific assessment and changes_documented_conclusion.
LD-1, LD-2 and LD-3 have that flag False. If a new discrepancy changes a documented
scientific conclusion, implementation must stop for review instead of reproducing
an erroneous legacy value or silently changing the conclusion.

## Source-anomaly sensitivity

`module17_anomaly_subset` reads the exact source_anomalies reason from the protected
manifest. Its ch4_c3 subset excludes only identities
`may2015_ch4_c3_023::bubble_point` and `may2015_ch4_c3_023::dew_point`.
Implementation never compares temperatures to select the subset. A test reads the
legacy CSV to verify identity equivalence with the historical 283.38 K rule.
`SensitivityAnalysis` retains the full-dataset primary aggregate, the alternate
aggregate, the cited subset definition and alternate-minus-primary shifts. Records
are neither mutated nor marked EXCLUDED. The original case and result remain intact.
Every protected sensitivity field is tested exactly, including 20-to-19 bubble and
7-to-6 dew counts and the AARD, RMS-relative and bias shifts.

## Deterministic serialization and deferred work

Existing record, dataset and run serializers emit compact UTF-8 JSON with a trailing
newline and round-trip float representation. `encode_scientific_artifact` and
`decode_scientific_artifact` cover every registered new type, including enums,
comparisons, explicit undefined/not-assessed states, policies, aggregates, summaries,
legacy records and sensitivity. The registry is closed to the validation modules;
unknown types, enums, fields, duplicate JSON keys and non-finite values are rejected.
Encode/decode/encode is byte-identical. Run metadata remains separate from stable
reproduction inputs and retains deterministic dataset/record ordering.

Deferred: covariance machinery, retrospective diagnostic summaries, UI/dashboard,
CH4+C3 dew-branch investigation, CoolProp, CO2, new datasets, real tolerances,
uncertainty propagation and any engine, kij, solver or orchestration change.
