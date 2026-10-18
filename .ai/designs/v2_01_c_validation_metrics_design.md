# V2-01-C design record: generalized validation metrics and scientific status engine

Status: APPROVED for implementation.

This record exists because the approved design was delivered in conversation on
2026-09-14 and was never written to the repository. It is persisted here before any
implementation so that the builder and the independent auditor read the same
authoritative definitions, including the exact meaning of LD-1, LD-2 and LD-3.

Section 1 is the approved design, verbatim (SHA-256 of that text: cf1df2d9b1e0e4b1f0d87f73be256bdc3092fad27e4bcdcf4fb5462b5efcbb00).
Section 2 records the decisions approved in the execution authorization of
2026-09-15. Section 3 records how the two were reconciled where the authorization is
more specific than the design. Where they differ, Section 2 and Section 3 govern.

---

## Section 1 - Approved design (verbatim)

Reconnaissance complete. Here is the V2-01-C design, built against what the repository actually contains.

## REPOSITORY REALITY CHECK

**Verified state.** Branch `v2-validation-framework`, HEAD `16e6ce9`, clean, pushed. Validation package 2,730 lines; 51 validation tests (23 core, 18 serialization, 10 adapter); suite **1,372**. `SCHEMA_VERSION = "1.1"`, supported set `{"1.1"}`. Protected paths as specified; `aggregation.py` holds containers only — no metrics exist yet.

**Discrepancies with the requested design — each changes C:**

| ID | Finding | Consequence for C |
|---|---|---|
| **G-6** | `ValidationRecord` has **one** `status` and **one** `declared_tolerance` per record, yet a record holds pressure *and* composition. Uncertainty and tolerance statuses are mutually exclusive values of that one field. | §4/§5 are unrepresentable. "Outside U but within tolerance" cannot be stored; neither can different outcomes for P and x. |
| **C-1 site** | `models.py`: `any(value.uncertainty is not None for value in self.case.reference_values)` | Confirmed. And **matching by quantity would not fix it** — see G-5. |
| **G-5** | No phase identity anywhere. `MOLE_FRACTION` serves both x and y. Every dew case carries a *specified* vapor `MOLE_FRACTION` with `U=(0.025, 0.025)` and a *reference* liquid `MOLE_FRACTION` with `U=None`. `PredictionValue` has only `quantity` and `value` — no phase, no component identity. | A quantity-keyed uncertainty lookup would borrow vapor uncertainty onto the liquid comparison — precisely the C-1 error. Phase meaning (§6) cannot be verified today, only assumed. |
| **G-7** | `DeclaredTolerance` is scalar-only with no absolute/relative kind, no phase, and free-text `scope`. | "0.01" on a mole fraction is ambiguous between absolute and 1%; applicability cannot be checked. |
| **LD-1** | Legacy per-point residual is `e/U` — **C-2 compliant**, never an inferred k — and the docs state "within 1U means ≤U, not one standard deviation." But legacy also counts `|e|/U ≤ 2` against an already-95%-expanded `U`, published in `docs/EXPERIMENTAL_VALIDATION.md` ("11/11 within 2U"). No UI, plot or report consumes it. | Transparently labelled, not a numerical error — but a 2× band on an expanded uncertainty must not become an uncertainty-agreement statistic. |
| **LD-2** | Legacy composition MAE flattens components: 11 cases → **22** observations, perfectly correlated for binaries. Per-case value differs by ≤2.1e-17. | Two different statistics with different *n*; both must be labelled. |
| **LD-3** | Legacy `failure_count` merges `not_found` and `inconclusive`. B already preserves them at `solver_metadata["legacy_solver_outcome"]`. | C splits them. |

**Confirmed correct.** The B adapter places uncertainty right: bubble reference y carries `U`, dew reference x carries `None`, dew specified y carries `U`. That is better than my own B-spec wording ("the opposite composition with vapor_expanded_uncertainties"), which was ambiguous.

**Other facts.** `DENSITY` is pinned to `kg/m^3`, so it is mass-basis only and molar density is unrepresentable. `TEMPERATURE.relative_error_meaningful=True` is a *permission*, not a primary-metric choice. The published vapor uncertainty is heavy-component only; the methane value is derived by binary closure and recorded only in prose. The adapter labels measured-state fugacity residuals `RETROSPECTIVE_DIAGNOSTIC` and attaches them to dew records only, although they are capability-independent (P3 — the non-production property still holds). Legacy metrics are strictly per (system, direction); **no pooled statistic exists**. Correcting my own earlier shorthand: "~1.03% bubble AARD" is CH₄+C₃H₈ only, never an overall figure.

**Reproducibility — the key enabling fact.** Recomputing from stored predictions with the documented formulas reproduces **every** legacy production aggregate **bit-exactly** across all four system×direction groups: pressure MAE, AARD, bias, RMS, max; composition MAE and max; pressure within-1U/2U counts; bubble composition within-U counts. Worst difference: **0.0**.

## V2-01-C PURPOSE

Turn validation records into per-quantity comparisons and transparent aggregates, with model accuracy and software correctness kept permanently separate. Close C-1 and C-2 structurally, account for every failure, make every statistic's observation unit explicit, and reproduce Module 17 exactly — surfacing, rather than inheriting, any legacy semantics that the frozen policy rejects.

## SCIENTIFIC METRIC POLICY

Metrics describe; they never gate CI and never produce a "scientifically passed" badge. Each quantity has a declared, data-encoded metric policy distinguishing **primary**, **enabled**, and **disabled** metrics, so any change of policy is visible in review. Every aggregate carries its observation unit, grouping key, sample count, and adjacent coverage block. Relative metrics require both `relative_error_meaningful=True` **and** a strictly positive finite reference; for these quantities a non-positive reference is invalid physics and raises explicitly — no epsilon threshold is invented.

## PER-QUANTITY METRICS

| Quantity | Per observation | Enabled aggregates | Primary | Disabled |
|---|---|---|---|---|
| PRESSURE | e, \|e\|, r = e/ref, \|r\|, z | MAE, bias, RMSE (Pa); AARD, bias, RMS-rel, max\|r\| (%) | AARD %, bias %, MAE | — |
| TEMPERATURE | e, \|e\| (K) | MAE, bias, RMSE, max (K) | MAE K, bias K | relative/AARD — permitted by flag, not enabled by policy |
| MOLE_FRACTION | e_i, \|e_i\| per component | MAE, bias, RMSE, max (absolute) | MAE, max\|e\| | all relative and percent |
| VAPOR_FRACTION | e, \|e\| | MAE, bias, RMSE, max | MAE, max | relative; a predicted/reference phase-state mismatch is a classification disagreement, never a small numeric β error |
| COMPRESSIBILITY_FACTOR | e, \|e\|, r, \|r\| | MAE, bias, RMSE, AARD, bias %, max | AARD %, MAE | — (phase required: liquid Z ≠ vapor Z) |
| DENSITY (mass) | e, \|e\|, r | MAE, AARD, bias %, max | AARD %, MAE | molar density — unrepresentable, so it cannot be mis-compared |

## UNCERTAINTY MODEL

Each assessment carries an `AppliedUncertainty` recording `kind_used` (STANDARD | EXPANDED), `derivation` (PUBLISHED | EXPANDED_FROM_STANDARD), the denominator actually used (scalar or component-aligned), `coverage_factor` and `confidence_level_percent` exactly as published, and `scope = REFERENCE_ONLY`.

Residuals are **distinct fields, never one field**: `expanded_normalized_residual = e/U` and `standard_normalized_residual = e/u`. Exactly one is populated, determined by `kind_used`.

Agreement counts group only by the full key `(kind_used, derivation, coverage_factor, confidence_level_percent)`. Groups are never pooled, so u-based and U-based counts cannot merge into one ambiguous number.

## C-1 RESOLUTION

1. The uncertainty for a comparison comes from **the exact `ReferenceValue` object being compared**. Never a lookup by quantity; never from `specified_conditions`. This alone closes the dew borrowing path.
2. Vector uncertainty aligns by component identity to the case's `component_ids`, validated before use.
3. Record-level uncertainty and tolerance statuses are retired (G-6), so the `any()` guard is deleted together with the only statuses it guarded. Assessment then exists only at the quantity level, where the quantity is known.

## C-2 RESOLUTION

- Published `U` → used directly: `e/U`, band `|e| ≤ U`. **Never `k·U`.**
- Published `u` without k → `e/u` only; no expanded assessment is produced.
- Published `u` with explicit k → a derived `U = k·u` only by explicit caller opt-in, marked `EXPANDED_FROM_STANDARD`, never pooled with published `U`.
- No `U → u` derivation in C; no dataset needs it, and it would require inference.
- Unknown k stays `None`; 95% confidence never implies k = 2.
- **Module 17:** EXPANDED, PUBLISHED, k = None, 95%. The legacy 2U count is handled under Q3 and is never an uncertainty assessment.

## REFERENCE-ONLY UNCERTAINTY LIMITATION

Every uncertainty assessment compares a prediction against the **reference value's own published uncertainty only**. It excludes: uncertainty in specified conditions (including u(y) on dew inputs, and T, for which no uncertainty is published); property-parameter uncertainty (Tc, Pc, ω); model sensitivities; and covariances, including the closure correlation between binary mole fractions.

A full budget could only *widen* the band. So `OUTSIDE` here does **not** prove disagreement beyond combined uncertainty, and `WITHIN` does not establish model adequacy. This wording belongs in the framework document, and `scope = REFERENCE_ONLY` is serialized on every assessment so it cannot be stripped in transit. No propagation engine is built.

## SOLVER OUTCOME MODEL

`SolverOutcome`: `CONVERGED`, `NOT_FOUND`, `INCONCLUSIVE`, `OTHER_FAILURE`. It is read from structured metadata only — for Module 17, `solver_metadata["legacy_solver_outcome"]` — through a dataset-owned reader, never from `failure_reason` prose. A generic `FAILURE` without a structured outcome becomes `OTHER_FAILURE` and is **not** guessed to be `NOT_FOUND`.

Invariant: `CONVERGED ⇔ PredictionOutcome.VALUE`.

Documented semantics: **`NOT_FOUND` means the configured numerical search found no acceptable solution — not that no physical solution exists.** `INCONCLUSIVE` means the solver could not decide, and stays distinct. The solver outcome lives on `CaseComparison`, separately from any agreement assessment.

## AGREEMENT/STATUS MODEL

Each `QuantityComparison` has:

- `comparison_state`: `COMPARED` | `REFERENCE_UNAVAILABLE` | `NOT_PREDICTED` (converged without producing this quantity) | `PREDICTION_UNAVAILABLE` (solver did not converge) | `EXCLUDED` (reason required)
- `errors` — only when `COMPARED`
- `uncertainty_assessment`: `WITHIN` | `OUTSIDE`, plus `AppliedUncertainty` — or `NotAssessed(NO_REFERENCE_UNCERTAINTY | NOT_EXPERIMENTAL | NOT_COMPARED)`
- `tolerance_assessment`: `WITHIN` | `OUTSIDE`, plus the full bound tolerance — or `NotAssessed(NO_DECLARED_TOLERANCE)`

There is **no combined or primary field and no precedence rule**. Record-level `ValidationStatus` narrows to lifecycle only: `REPORTED_NO_TOLERANCE` (read as "prediction recorded"), `SOLVER_FAILURE`, `EXCLUDED`.

## UNCERTAINTY VS TOLERANCE COEXISTENCE

The two assessments are independent optional slots, computed whenever their inputs exist, serialized together, and counted in separate aggregate columns. "OUTSIDE U, WITHIN cited tolerance" is a single storable record. Any later presentation (V2-01-D) must declare its own documented primary view without altering the record.

## QUANTITY/UNIT/BASIS ALIGNMENT

Comparisons match on `ComparisonKey(quantity, phase)`. Before any error is computed:

- quantity identical;
- units — values are already canonical SI, and a tolerance's unit must equal the quantity's canonical unit (or be "1" for relative);
- phase identical and **required** for `MOLE_FRACTION`, `COMPRESSIBILITY_FACTOR`, `DENSITY`; `None` for P, T, β;
- exactly one reference and one prediction per key — duplicates raise.

Basis: `DENSITY` is mass-basis by unit, so a mass/molar mismatch is structurally impossible today; if molar density is ever added, basis joins the key. Every mismatch raises `ComparisonAlignmentError`; nothing converts silently between different bases.

## COMPONENT ALIGNMENT

With G-5, vector `PredictionValue`s declare `component_ids`. Alignment is **identity-based**: reordering happens only when the identity sets are equal and unique, and anything else raises `ComponentAlignmentError`. Position is never trusted.

The reference uncertainty vector is aligned through its own case's `component_ids`. Closure-derived component uncertainty is recorded as provenance (Q5). The test the requirement asks for: a prediction delivered as `(ethane, methane)` against a `(methane, ethane)` case either realigns correctly or raises — it never compares CH₄ against C₂H₆.

## AGGREGATION/WEIGHTING RULES

Observation units are declared, never implied:

- `PER_CASE_SCALAR` — one observation per case (P, T, β, Z, ρ).
- `PER_COMPONENT` — one per (case, component); the legacy composition MAE.
- `PER_CASE_VECTOR` — one per case via a *named* reduction: `MAX_ABS_COMPONENT` or `MEAN_ABS_COMPONENT`. Legacy within-U uses max-normalized component.

Rules: default grouping is `(dataset_id, system_id, ComparisonKey)`, matching legacy per (system, direction). A pooled-across-systems view exists only as a separately labelled aggregate and never replaces per-system results. **Different quantities are never pooled**, so a two-component composition case cannot outweigh a pressure case. Weight is equal per declared observation; no inverse-variance weighting.

## FAILURE/COVERAGE ACCOUNTING

Every aggregate carries a `CoverageBlock`: `total_cases`, `excluded_cases`, `eligible_cases`, `reference_available`, `converged`, `not_found`, `inconclusive`, `other_failure`, `compared_cases`, `metric_observation_count`, `uncertainty_assessable_count`.

Enforced reconciliation: `converged + not_found + inconclusive + other_failure = eligible_cases`; `compared ≤ min(converged, reference_available)`.

A formatting helper emits *"AARD = X% over 7 compared of 23 cases (14 inconclusive, 2 not_found)"*, and there is no API that returns the bare number without its coverage.

## MODULE 17 EQUIVALENCE TARGETS

**Exact equality — tolerance 0.0**, justified because reproduction was demonstrated bit-exact during this check.

| Group | Coverage | Values that must reproduce exactly |
|---|---|---|
| CH₄+C₂H₆ bubble | 11/17, 6 not_found | AARD 0.454690272936386 %, bias −0.2902490453707504 %, RMS 0.6957623241073989 %, max 1.4302143942514662 %, MAE 22191.23154053439 Pa; comp MAE 0.0037091200128458565 (n = 22), max 0.008813395774289176; P within 1U 10/11, 2U 11/11; comp within 1U 10/11 |
| CH₄+C₂H₆ dew | 15/17, 2 not_found | AARD 6.045523060713735 %, bias −4.646066590639891 %, RMS 9.84725988020644 %, max 25.85001850624154 %, MAE 355947.236133196 Pa; comp MAE 0.03902500301144884, max 0.18938747494145863; P within 1U 8/15, 2U 13/15; comp uncertainty unavailable |
| CH₄+C₃H₈ bubble | 20/23, 3 not_found | AARD 1.0338049113443992 %, RMS 1.2474942514800351 %, bias −1.0228574613168764 %; P within 1U 11/20, 2U 15/20; comp within 1U 20/20; remaining fields from the summary JSON |
| CH₄+C₃H₈ dew | 7/23, 14 inconclusive, 2 not_found | AARD 36.668237970426496 %, RMS 42.40217430079411 %, bias −35.858325688636896 %; P within 1U 1/7, 2U 1/7 |

Targets are formulas, inclusion, coverage and sample sizes. **No acceptance criterion asserts that bubble is good or dew is poor.**

Deferred with reason: retrospective nearest-root aggregates and measured-state fugacity-residual summaries — these are diagnostics, not accuracy, and must not enter accuracy outputs (Q6).

## LEGACY-DISCREPANCY POLICY

For each legacy statistic: (1) reproduce it using the legacy definition; (2) compute the new-policy statistic; (3) if they differ, emit a `LegacyDiscrepancy` record — metric, legacy value, new value, cause, scientific assessment — plus a test and a framework-document entry; (4) if the difference changes a conclusion published in `docs/EXPERIMENTAL_VALIDATION.md` or the UI, stop at HUMAN_ACTION_REQUIRED.

Known cases: **LD-1** (2U band — framing only, numbers unchanged, needs Q3); **LD-2** (per-component vs per-case — both views exposed and labelled); **LD-3** (failure split — additive). None is demonstrably a numerical error, so no stop is triggered now.

## 283.38 K SENSITIVITY DESIGN

`SubsetDefinition(subset_id, excluded_case_ids=("may2015_ch4_c3_023",), scope_system="ch4_c3", reason=<manifest source_anomalies text>, source=manifest)`. The subset is defined by **case identity, not float equality**; C cross-checks that it matches the legacy `temperature_k != 283.38` rule exactly.

`SensitivityAnalysis(primary = full-dataset aggregate, alternate = subset aggregate, subset, shifts)`. Primary is always the full dataset. The alternate never replaces it, and records are **not** marked `EXCLUDED` — the excluded case keeps its identity, reason, and original result.

Exact targets: bubble 20 → 19 compared, AARD 1.0338049113443992 → 0.9807666332366116, shift −0.053038278107787606 pp; dew 7 → 6, AARD 36.668237970426496 → 38.86971885863611, shift +2.201480888209616 pp. Removing the point makes dew *worse* — recorded, not interpreted away.

## DECLARED TOLERANCE POLICY

Tolerances are applied **only** through an explicit `ToleranceBinding(dataset_id, ComparisonKey, DeclaredTolerance)`. There is no inference from `scope` text, no global value, and no default.

With G-7, `DeclaredTolerance` gains `tolerance_kind` (ABSOLUTE | RELATIVE); `RELATIVE` is refused when `relative_error_meaningful=False`. An absolute unit must equal the canonical unit; a relative tolerance is expressed as a fraction, never a percentage string. A scalar tolerance applies uniformly per component. Justification and citation remain mandatory. **Zero real instances ship**; tolerances exist only in synthetic tests.

## ARCHITECTURE

```
ValidationRecord ── solver_outcomes.py ──→ SolverOutcome
       │
  alignment.py      ComparisonKey · phase · identity-based component alignment
       │
  comparisons.py    QuantityComparison → CaseComparison
       │               (errors, uncertainty assessment, tolerance assessment)
  metrics.py        METRIC_POLICY (data) · per-observation errors · named reductions
       │
  aggregates.py     ObservationUnit · CoverageBlock · SubsetDefinition · SensitivityAnalysis
       │
  aggregation.py    ExperimentalAccuracySummary      (experimental error, uncertainty agreement)
                    CrossCheckAgreementSummary       (numerical difference, model discrepancy)
```

Plus: a `SolverOutcome` reader and `MODULE17_SENSITIVITY_283_38_K` in `module17_adapter.py`; G-5/G-6/G-7 as one schema bump **1.1 → 1.2**, with the adapter populating phase and component identity; serialization for all new types. Uncertainty assessment is structurally `NotAssessed(NOT_EXPERIMENTAL)` for cross-checks, and the two summary types expose different field names.

## PUBLIC API

```
compare_record(record, *, tolerance_bindings=()) -> CaseComparison
solver_outcome_of(record) -> SolverOutcome
aggregate_experimental_accuracy(comparisons, *, unit, group_by) -> ExperimentalAccuracySummary
aggregate_cross_check_agreement(comparisons, *, unit, group_by) -> CrossCheckAgreementSummary
run_sensitivity(comparisons, subset) -> SensitivityAnalysis
ComparisonKey, SolverOutcome, AssessmentOutcome, AppliedUncertainty, CoverageBlock,
ObservationUnit, SubsetDefinition, ToleranceBinding, LegacyDiscrepancy, METRIC_POLICY
encode_/decode_ for every new type
```

No API returns an accuracy boolean or a bare statistic without coverage.

## INVARIANTS

1. An uncertainty assessment uses only the compared `ReferenceValue`'s own uncertainty.
2. `expanded_normalized_residual` and `standard_normalized_residual` are never both populated.
3. A published `U` is never multiplied by a coverage factor.
4. `coverage_factor` is never synthesized.
5. Agreement counts never pool across `(kind, derivation, k, confidence)`.
6. Component vectors align by identity or raise.
7. Quantity or phase mismatch raises; no silent basis conversion.
8. Relative metrics are impossible for `relative_error_meaningful=False` quantities.
9. `SolverOutcome` never derives from prose; `CONVERGED ⇔ VALUE`.
10. `NOT_FOUND` and `INCONCLUSIVE` are never merged.
11. Uncertainty and tolerance assessments coexist; no precedence field exists.
12. Coverage blocks reconcile; failures are never removed from denominators.
13. Every aggregate declares observation unit and sample count.
14. Different quantities are never pooled.
15. A sensitivity subset never replaces the primary result or mutates records.
16. A tolerance applies only through an explicit binding and requires kind, unit, justification, citation.
17. Experimental and cross-check comparisons never share an aggregate.
18. No accuracy boolean, default tolerance, or pass badge exists.
19. Serialization is deterministic and round-trip byte-identical.

## ACCEPTANCE CRITERIA

C-1 and C-2 are proven by adversarial tests (mandatory). All Module 17 targets reproduce exactly, including sensitivity. LD-1..3 are recorded as `LegacyDiscrepancy` entries and documented. Schema 1.2 is documented; a 1.1 payload is rejected explicitly with no migration. The adapter populates phase and component identity, and the B equivalence tests still pass. Full deterministic verification is green at ≥1,372 tests. The science firewall is intact and Module 17 artifacts are byte-identical. No real tolerance is shipped. The reference-only limitation is written into the framework document.

## TEST PLAN

Adversarial tests covering every item you listed:

- **C-1:** borrowing via the dew specified vapor `U` raises; pressure `U` never reaches composition; permuted component order realigns or raises.
- **C-2:** a published `U` is not re-expanded even when k is present; unknown k stays `None`; u-based and U-based counts stay in separate groups; derived `U` requires explicit opt-in and is marked.
- **Alignment:** quantity, phase and basis mismatches raise; relative error is refused for fractions; a non-positive reference raises.
- **Weighting:** composition never outweighs pressure; per-component and per-case views report different *n*.
- **Solver separation:** outcome is independent of assessment; `not_found` and `inconclusive` preserved; `OTHER_FAILURE` is never promoted.
- **Tolerances:** no tolerance means `NotAssessed`; uncited and wrong-kind tolerances are rejected; "outside U, within tolerance" coexists.
- **Separation:** mixing experimental and cross-check comparisons raises.
- **Coverage:** reconciliation holds on synthetic and Module 17 data.
- **Module 17:** exact reproduction of every target, compared against the **legacy evidence**; LD-1 and LD-2 surfaced; sensitivity doesn't replace the primary result, and the case-id subset matches the float rule.
- **Mechanics:** serialization determinism; protected artifacts hash-identical.

## ALLOWED PATHS

`src/pvt_phase_simulator_validation/**`, `tests/test_validation_*.py`, `docs/VALIDATION_FRAMEWORK.md`, `.ai` package and evidence files.

## PROTECTED PATHS

`src/pvt_phase_simulator/**`, `data/**`, `docs/validation/**`, `tests/golden_master/**`, `src/pvt_phase_simulator_ui/**`, `tools/orchestration/**`. Also left untouched: `docs/EXPERIMENTAL_VALIDATION.md` — any LD-1 wording change belongs to a later documentation package.

## CODEX BUILD SCOPE

Implement the schema 1.2 changes (G-5, G-6, G-7), alignment, comparisons, the metric policy, aggregates with coverage, sensitivity, the legacy-discrepancy records, the adapter's phase/identity population, and serialization — all inside the allowed paths.

Do not modify science. Do not add real tolerances, CoolProp, CO₂ or new datasets. Do not build the dashboard or report. Do not propagate uncertainty. Do not pool quantities. Do not fix the dew branch. Run focused tests only during the build.

## CLAUDE AUDIT SCOPE

Read-only, attacking in order:

1. Can uncertainty be borrowed — across quantities, phases, specified conditions or components?
2. Can a published `U` be re-expanded, or k inferred?
3. Can u-based and U-based counts pool?
4. Can a failure leave a denominator, or `not_found`/`inconclusive` merge?
5. Is there hidden weighting or quantity pooling?
6. Can any precedence or combined status emerge?
7. Do Module 17 targets reproduce exactly, and are LD-1..3 surfaced rather than hidden?
8. Does sensitivity overwrite the primary result?
9. Can experimental and cross-check data mix?
10. Is there any threshold, default tolerance, or pass badge?
11. Did anything protected change?

No unrelated architecture critique.

## RISKS

- **The schema 1.2 bump is the largest change since A.** Mitigated: no persisted validation data exists, and the B equivalence tests act as a regression net.
- **Over-generalizing** the metric policy for quantities with no dataset. Mitigated: policy is data, and only Module 17 quantities are exercised against real evidence.
- **Summation-order drift** breaking exact equivalence. Mitigated: `fsum` with the documented operation order.
- **Scope creep** into diagnostics or presentation. Mitigated: explicit deferrals.
- **The reference-only limitation being lost** downstream. Mitigated: `scope` is serialized on every assessment.

## SCIENTIFIC QUESTIONS REQUIRING HUMAN DECISION

**Q1 — G-6, recommended: approve.** Narrow record-level `ValidationStatus` to lifecycle only, and move all agreement and tolerance assessment to per-quantity comparisons. Without it, §4 and §5 cannot be met and C-1 cannot be closed structurally.

**Q2 — G-5, recommended: approve.** Add phase identity to `ReferenceValue` and `PredictionValue`, and component identity to vector predictions, in the same 1.2 bump. Without it, "liquid ≠ vapor" can only be assumed, never verified.

**Q3 — LD-1.** Legacy "within 2U" counts: **(a) recommended** — reproduce them only as labelled legacy descriptive counts, never as uncertainty agreement; or (b) drop them from new outputs entirely. Choosing (a) or (b) may later warrant a wording note in `docs/EXPERIMENTAL_VALIDATION.md`.

**Q4 — vector agreement rule.** Recommended: `MAXIMUM_NORMALIZED_COMPONENT`, which matches legacy and requires every component to agree.

**Q5 — closure-derived component uncertainty.** Recommended: keep it documented as provenance now, and structure it only when a ternary dataset appears.

**Q6 — diagnostic summaries** (retrospective nearest-root aggregates, measured-state fugacity residuals). Recommended: defer out of C, and give them their own separately typed diagnostic summary later.

**Q7 — G-7, recommended: approve.** Add `tolerance_kind` to `DeclaredTolerance` and apply tolerances only through explicit bindings.

## READY FOR ORCHESTRATOR

**YES** — the scientific design is resolved enough to prepare the work package, with one condition: **Q1, Q2 and Q7 change the approved V2-01-A contract** (as G-1 did), so I'd want them approved before the package is written. Q3–Q6 have recommended defaults you can accept as-is.

Nothing was implemented, no package was created, and no file was modified this turn.


---

## Section 2 - Approved decisions and execution refinements (2026-09-15)

**Q1 / G-6 - approved.** `ValidationRecord.status` becomes lifecycle-only. Scientific
agreement belongs to each quantity comparison. Pressure accuracy and composition
accuracy are never encoded into one record-level status.

**Q2 / G-5 - approved.** Explicit phase identity where required, and component
identity on vector prediction and reference structures. Liquid composition is not
vapor composition, and components align by identity, never merely by array index.

**Q3 / LD-1 - approved option (a).** Legacy within-2U counts remain reproducible only
as clearly labelled LEGACY DESCRIPTIVE STATISTICS. They are not modern
uncertainty-agreement statistics. Multiplying a published `U` by 2 is permitted only
inside that isolated legacy path, to reproduce the historical Module 17 statistic;
"never calculate `k x U`" governs all modern uncertainty assessment, and the legacy
statistic never enters modern uncertainty-agreement counts.

**Q4 - approved.** Vector uncertainty agreement is `max(abs(normalized_i)) <= 1`:
every required component must individually fall within its own applicable reference
uncertainty bound. Every required component must have usable uncertainty; a missing
component uncertainty is never silently omitted, and the maximum is never taken over
only the available components - the vector assessment is then NOT ASSESSABLE.
Component identity is aligned before residuals are calculated, and component-level
normalized residuals stay accessible. This is a component-wise all-bounds-satisfied
criterion, never a joint 95% coverage or joint confidence region.

**Q5 - deferred.** Closure-derived generalized covariance and uncertainty machinery.
Provenance only.

**Q6 - deferred.** Retrospective nearest-root and measured-state fugacity diagnostic
summaries stay out of generalized accuracy outputs. They remain diagnostics.

**Q7 / G-7 - approved.** `DeclaredTolerance` gains explicit tolerance semantics
(quantity, `tolerance_kind` ABSOLUTE or RELATIVE, value, unit and basis semantics,
scope, justification, source citation) and may be applied only through explicit
bindings. No inferred or default tolerance. Relative tolerance is forbidden where the
quantity policy disallows relative error. No real tolerance values ship.

**Schema 1.2.** New writes emit 1.2 only. A 1.1 payload is never silently
reinterpreted and its information is never silently discarded. A migration helper may
exist only if conversion is fully deterministic and scientifically unambiguous; any
conversion that would require guessing phase, component identity, tolerance meaning,
per-quantity status or solver meaning is rejected with an explicit error. No general
migration framework. The Module 17 adapter may regenerate valid 1.2 records from the
protected legacy evidence, where the scientific identity is known; protected legacy
artifacts are never mutated.

**Invalid and empty inputs.** Negative and non-finite uncertainty are rejected. Zero
uncertainty may exist only when explicitly present in source data, and normalizing by
it is undefined: the result is an explicit NOT ASSESSABLE state with reason
`ZERO_UNCERTAINTY_DENOMINATOR`, never 0, infinity or a silent NaN. Non-finite
references are rejected. A zero relative-error denominator makes the relative metric
undefined with reason `ZERO_REFERENCE_DENOMINATOR`, with no epsilon. Non-finite
predictions never enter metrics; they follow solver or comparison failure semantics
and keep their reason. An aggregate with zero usable observations reports an explicit
undefined metric state with `sample_count = 0` and reason `NO_USABLE_OBSERVATIONS`,
never a metric of 0, while coverage still reports the real case counts. NaN and
Infinity never leak into serialized scientific output.

**Verification revision rule.** Verification and audit apply to a specific code
revision. Final approval requires both an authoritative full verification and an
independent approval of the final code revision; any code correction requires full
re-verification and re-audit of the corrected revision.

---

## Section 3 - Reconciliation of the design with the execution authorization

1. **Relative-error denominator.** The design text says a non-positive reference for a
   relative-permitted quantity "raises explicitly". The authorization specifies an
   explicit undefined metric with a reason. Adopted: relative metrics are undefined
   with `ZERO_REFERENCE_DENOMINATOR` or `NEGATIVE_REFERENCE_DENOMINATOR`, while the
   absolute metrics for the same comparison are still computed. Both forms forbid
   silent numbers and invented epsilon thresholds; the authorized form is more specific
   and discards less information. This is a refinement, not a material conflict.
2. **283.38 K subset identity.** The implementation identifies the sensitivity subset
   by stable case identity only. The design's cross-check against the legacy
   `temperature_k != 283.38` rule exists only as a test that reads legacy evidence; it
   is verification of equivalence, not the implementation's selection mechanism.
3. **Schema 1.1.** No migration helper is provided. Converting a 1.1 record to 1.2
   would require guessing phase identity, component identity and per-quantity
   assessment semantics, so 1.1 payloads are rejected explicitly. No persisted 1.1
   validation output exists, so nothing is stranded.
4. **Module 17 vapor composition uncertainty.** The per-component vapor uncertainties
   are usable for the vector criterion. The source manifest states that the
   complementary methane fraction has the same absolute uncertainty as the published
   heavy-component value, so the vector is source-stated rather than inferred. That
   derivation is preserved as provenance (Q5); no covariance machinery is built.
5. **LD definitions.** LD-1, LD-2 and LD-3 are implemented exactly as defined in
   Section 1 and were confirmed consistent with the authorization's stated intent:
   LD-1 isolates the legacy 2U band from modern uncertainty assessment, LD-2 keeps the
   per-component and per-case composition statistics separately labelled with their
   own sample counts, and LD-3 splits the legacy failure count into structured
   `not_found` and `inconclusive`.
