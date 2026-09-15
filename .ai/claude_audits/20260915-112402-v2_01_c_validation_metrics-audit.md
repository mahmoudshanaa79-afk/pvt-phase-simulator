Note: the plan-mode file/exit tools (Write, ExitPlanMode) aren't actually available in this session — only read-only tools plus Agent/Artifact were provisioned, consistent with this being a read-only audit task rather than an implementation task. Since the entire task is read-only analysis (no edits were made or needed), I'm delivering the required audit output directly below.

---

# Independent audit: v2_01_c_validation_metrics

## Method

I did not trust the builder's report, the design document's own formula listings, or the docstrings in the diff. I investigated the actual code via three independent read-only passes (delegated to sub-agents, each instructed to re-derive rather than accept documented claims) covering the three highest-risk clusters, plus my own direct follow-up read on one gap:

1. **Uncertainty/comparison identity** (`comparisons.py`, `models.py`, `metrics.py`, `provenance.py`, `enums.py`, `exceptions.py`): C-1/C-2 uncertainty sourcing, residual/criterion logic, Q4 vector all-or-nothing rule, zero-denominator guards, component alignment by identity, phase identity in `ComparisonKey`, DENSITY mass-basis, duplicate-key rejection, exception-swallowing sweep — all 10 sub-checks.
2. **Metrics/aggregation/coverage** (`metrics.py`, `aggregates.py`, `aggregation.py`): exact `fsum` formulas and operator order, relative-metric denominator rules, `METRIC_POLICY` contents, empty-aggregate handling, NaN/Inf leakage, `CoverageBlock` reconciliation enforcement, PER_COMPONENT vs PER_CASE_VECTOR non-pooling, uncertainty-agreement stratification, experimental/cross-check separation, `format_metric` — all 10 sub-checks.
3. **Module 17 equivalence, legacy statistics, sensitivity, serialization** (`module17_adapter.py`, `module17_legacy.py`, `sensitivity.py`, `serialization.py`, `scientific_serialization.py`, all three test files, the protected summary JSON): schema 1.1 rejection ordering, non-tautological JSON-sourced equivalence tests, exact reproduction of every cited legacy number, LD-1/LD-2/LD-3 isolation, sensitivity subset identity and shift-sign correctness, serialization determinism, protected-file read-only access — all 10 sub-checks.
4. **My own follow-up**: independently grepped `module17_adapter.py:326-350` to verify the actual `Uncertainty(...)` construction at the Module 17 boundary, since this was flagged as unaudited by pass 1. Confirmed `coverage_factor=None` at both construction sites (pressure and vapor composition — no inferred `k`), `kind=UncertaintyKind.EXPANDED` used directly (never re-derived from a standard uncertainty), and the vapor uncertainty vector set as `(vapor_component, vapor_component)` — correctly encoding the manifest's stated provenance that methane's uncertainty equals the published heavy-component value.

## Findings

**No severity A or B (blocking) findings.** All 23 named adversarial attack vectors were checked and none succeeded:

- **C-1** (`comparisons.py:_uncertainty`) sources the uncertainty exclusively from the `ReferenceValue` selected for the exact `ComparisonKey(quantity, phase)` under comparison. `case.specified_conditions` is never read anywhere in `comparisons.py` (grep-confirmed zero references). The dew liquid-composition case (no reference uncertainty, while the specified vapor composition carries U=(0.025,0.025)) correctly yields `NotAssessed(NO_REFERENCE_UNCERTAINTY)` and never borrows the vapor value.
- **C-2**: multiplication by `coverage_factor` only triggers when `kind is UncertaintyKind.STANDARD`; an already-EXPANDED source is structurally excluded from that branch and passes through unmultiplied. `derive_expanded` defaults to `False` and must be explicitly requested by the caller. `AppliedUncertainty.__post_init__` hard-enforces that `EXPANDED_FROM_STANDARD` requires `kind_used is EXPANDED` and a non-`None` `coverage_factor`. No `k=2` default exists anywhere in the package.
- **Q4**: the `MISSING_COMPONENT_UNCERTAINTY` check (`any(v is None ...)`) unconditionally short-circuits before any `max()`/reduction runs, so a partial-subset maximum over only available components is not reachable.
- Zero-denominator guards precede the only division in each path and are re-checked after coverage-factor multiplication; no `try/except` wraps a division that could mask a `ZeroDivisionError` into a plausible number.
- Component alignment rebuilds vectors via an identity-keyed dict (no positional/index arithmetic); set mismatch, duplicate, and length mismatch all raise `ComponentAlignmentError`. `ComparisonKey` uses default dataclass `(quantity, phase)` equality/hash, so liquid/vapor and different components genuinely land in different dict slots.
- `CoverageBlock.__post_init__` actively raises on every stated reconciliation invariant (not merely documented). `GroupingKey` includes the full `ComparisonKey`, so different quantities/phases are structurally incapable of pooling into one aggregate.
- All PART 5 formulas (MAE, bias, RMSE, AARD%, bias%, RMS relative%, max abs relative%) matched byte-for-byte against the code, including `math.fsum` (not `sum()`) and the literal `100.0 * fsum(...) / n` operator ordering.
- Module 17 equivalence tests read `docs/validation/module17_vle_validation_summary.json` live via `json.loads(...read_text())` at test time and assert full-dict `==` against framework-computed aggregates — confirmed genuinely non-tautological. All cited representative numbers (CH4+C2H6 bubble AARD 0.454690272936386, composition MAE 0.0037091200128458565/22 obs, pressure within-1U 10/11; CH4+C3H8 dew AARD 36.668237970426496, within-1U 1/7) and all four coverage splits are asserted, not merely present.
- **LD-1** exists only in `module17_legacy.py`; `aggregation.py` hard-rejects any non-`CaseComparison` input via `raise TypeError`, verified live by a test that confirms the `TypeError` actually fires when a `LegacyDescriptiveStatistics` is passed in.
- **LD-2** exposes PER_COMPONENT (22 obs) and PER_CASE_VECTOR/MEAN_ABS_COMPONENT (11 obs) as two separately labeled statistics with the sample-count relationship directly asserted.
- **LD-3**'s failure_count derives from `CoverageBlock`'s structured fields, themselves from `solver_outcome()` reading only `solver_metadata["legacy_solver_outcome"]` — verified live by a test injecting misleading failure-reason prose that classification ignores.
- **Sensitivity** subset selection uses hardcoded case IDs only; the sole `temperature_k ==` comparison in production code is unrelated (cross-source row matching). I independently re-derived the shift arithmetic by hand: `0.9807666332366116 − 1.0338049113443992 = −0.053038278107787606`, exactly matching the JSON's shift field — confirming correct `alternate − primary` sign, not the reverse.
- **Protected artifacts**: `git status`/`git diff --stat` show no changes to any of the four protected files; on-disk SHA-256 matches the hashes hardcoded in tests; both `module17_adapter.py` and `module17_legacy.py` use read-only file access (no `write_text`/`write_bytes`/`.write(` in either file).

**Five non-blocking (C/D) informational items, all safe to defer:**

1. **(C)** `serialization.py`'s plain record/dataset/run decode path does not use `parse_constant` to reject bare `NaN`/`Infinity` JSON tokens at parse time, unlike `scientific_serialization.py` which does. Not currently exploitable — every numeric field downstream independently rejects non-finite values at construction, empirically confirmed by hand-injecting NaN/Infinity into pressure, uncertainty, coverage_factor, confidence_level_percent, and diagnostics (all raised). But there's no dedicated regression test for this path, so a future field added without a finiteness guard could silently accept non-finite JSON. Recommend adding `parse_constant` there too, plus a test.
2. **(D)** `comparisons.py:_shape` raises an unhandled `ValueError` rather than a graceful `UndefinedMetric` if `predicted - reference` itself overflows to `inf` for astronomically large finite inputs (~1e308) — not reachable by any real PVT magnitude.
3. **(D)** `aggregates.py` reports only `relative_reasons[0]` instead of `NO_USABLE_OBSERVATIONS` when zero usable observations result from *mixed* relative-denominator failure reasons — a narrow information-loss edge case not currently exercised by any real dataset.
4. **(D)** Uncertainty-agreement stratification keys on `coverage_factor`/`confidence_level_percent` by exact float equality — safe failure direction (under-pooling), but a latent fragility.
5. **(D)** `DENSITY`'s `METRIC_POLICY` entry has cosmetically inconsistent `per_observation`/`enabled` tuples versus the structurally similar `COMPRESSIBILITY_FACTOR` entry; no downstream consumer is affected today.

## Verdict

**APPROVED.** No defect reaches blocking severity. The frozen principle (no accuracy gate, no default tolerance), C-1/C-2 uncertainty isolation, Q4 vector all-or-nothing semantics, LD-1/2/3 isolation, sensitivity non-replacement, and Module 17 bit-exact equivalence all hold under adversarial re-derivation.

<ORCHESTRATOR_RESULT>
{
  "verdict": "APPROVED",
  "findings": [],
  "safe_defer": [
    {"id": "D-1", "severity": "C", "blocks": false, "summary": "serialization.py's plain decode path lacks parse_constant NaN/Infinity rejection at parse time; currently caught by downstream finite-value validators but that path is untested directly."},
    {"id": "D-2", "severity": "D", "blocks": false, "summary": "comparisons.py:_shape raises an unhandled ValueError instead of a graceful UndefinedMetric when predicted-reference overflows to inf for astronomically large finite inputs; not reachable by real PVT magnitudes."},
    {"id": "D-3", "severity": "D", "blocks": false, "summary": "aggregates.py reports only the first per-observation reason (relative_reasons[0]) instead of NO_USABLE_OBSERVATIONS when zero usable observations result from mixed relative-denominator failure reasons."},
    {"id": "D-4", "severity": "D", "blocks": false, "summary": "Uncertainty-agreement stratification keys on coverage_factor/confidence_level_percent by exact float equality; safe failure direction (under-pooling) but a latent fragility."},
    {"id": "D-5", "severity": "D", "blocks": false, "summary": "DENSITY's METRIC_POLICY per_observation/enabled tuples are cosmetically inconsistent with the structurally similar COMPRESSIBILITY_FACTOR entry; no downstream consumer affected today."}
  ]
}
</ORCHESTRATOR_RESULT>