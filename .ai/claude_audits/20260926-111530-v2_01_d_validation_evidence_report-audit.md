# Independent audit: v2_01_d_validation_evidence_report

**Verdict: CONDITIONAL.** The scientific core holds. D computes no science of its own, membership is proven per metric, and the diagnostics are kept apart. Two defects need fixing before approval: (1) the comparisons CSV gives a false reason for a missing standard residual, and (2) the JSON exports accuracy values pooled across systems.

**Method.** I read `report/*.py`, `module17.json`, the test file, the D section of `docs/VALIDATION_FRAMEWORK.md`, and the relevant parts of the design record and C (`comparisons.py`). I generated the full evidence for the real Module 17 data in memory and scanned all four outputs.

I made no changes to the repository. One scan wrote a scratch copy of the HTML body into `%TEMP%`, outside the repo; I deleted it afterwards. Git status shows that only the D paths, `docs/VALIDATION_FRAMEWORK.md` and `.ai/` files differ from HEAD. All A/B/C modules, the engine, data and golden files match HEAD.

## What held up under attack

- **Membership (S1).** `membership.py` does three things:
  - It re-runs C's `aggregate_group` on each group and requires frozen-dataclass equality with the source aggregate.
  - It picks the contributors for each metric from C's own state: every `COMPARED` observation for absolute metrics, and only observations with a defined `relative_error` for metrics whose unit is `%`.
  - It re-runs `aggregate_group` on just those contributors and requires the metric's state, value and `sample_count` to match.

  All 12 proven aggregates pass on real Module 17 data: 8 per-component and 4 per-case-vector (MEAN_ABS_COMPONENT). Their contributor counts are 11/22, 20/40, 15/30 and 7/14.
- **S2 synthetic test.** I re-derived the expected values by hand: MAE = (2 + 4 + 3)/3 = 3.0 with N = 3, and AARD = 100 × (0.02 + 0.02)/2 = 2.0 with N = 2. The test:
  - checks both memberships;
  - confirms `ZERO_REFERENCE_DENOMINATOR` sits on case-Z's own relative error and in its CSV state/reason columns;
  - confirms a tampered AARD membership that includes case-Z raises, and so does removing a case from the group.
- **Coverage and failures.** Coverage figures come from C's `CoverageBlock`. NOT_FOUND, INCONCLUSIVE and OTHER_FAILURE stay separate. The frozen NOT_FOUND sentence is present. Failures come immediately after Solver Coverage. The ledger has 80 rows, derived from the evidence rather than hard-coded.
- **283.38 K case.** It stays in both ch4_c3 primary groups. Sensitivity uses C's `analyze_sensitivity`, and the test asserts the primary result equals the source aggregate. The callout renders the manifest anomaly text verbatim plus the archive record, "not performed (article inaccessible)" and UNRESOLVED.
- **Uncertainty wording (S3).** The exact reference-only sentence is present. Coverage factor reads "not stated by the source"; confidence reads "95 % (as recorded)". The declaration refuses any non-null coverage factor. No "k=2" and no "joint" wording appears outside the Plotly library. Historical 2U counts appear only in the legacy box.
- **Diagnostics isolation.** A test plants a sentinel in `prediction.diagnostics`. It appears only in the diagnostics section and the JSON `diagnostics` block, and it arrives escaped.
- **Security.**
  - Plotly figure fragments neutralise a hostile `</SCRIPT >` in `customdata` and `name`; I confirmed this myself.
  - The inlined Plotly library has `</script` rewritten.
  - The only live links are the DOI and archive links. They are `https`-validated and carry `rel="noopener noreferrer"`.
  - No `<link>`, `<img>` or `script src` is emitted.
- **JSON.**
  - The top-level keys match design §9 exactly.
  - Output uses `allow_nan=False` and passes a strict re-parse.
  - `content_sha256` does not change when the volatile block changes, and the CSVs and HTML with the volatile block masked are identical.
- **Privacy.** No absolute paths, usernames or OneDrive paths appear in the outputs. The tree is correctly reported DIRTY, and DIRTY and UNKNOWN get separate banners.
- **Model configuration.** Ωa, Ωb, the kij policy, and Tc/Pc/ω/κ for each component are checked against the engine.

## Findings

**C-1 (moderate, blocking): invented reason for the missing standard residual.**
- In `exports.py:536-545`, every assessed row gets `standard_normalized_residual_state = NOT_CALCULATED` and reason `COVERAGE_FACTOR_NOT_STATED`.
- In C, the standard residual is only filled in when the uncertainty used is STANDARD (`comparisons.py:176-188`). With a published expanded U it is structurally absent, whatever k is.
- All 115 assessed Module 17 rows carry this reason. It suggests a U→u conversion would happen if k were known, which contradicts C-2 ("There is no U → u derivation"). It is also a scientific reason that D made up rather than took from C. The reason would stay wrong even with a stated k.
- The docs repeat it ("unavailable standard normalized residual is never an unexplained blank").
- Related gap: when STANDARD uncertainty is used, the empty `expanded_normalized_residual` cell has no state/reason column of its own.

**C-2 (moderate, blocking): pooled-across-systems accuracy is exported.**
- The design (§5, line 162) limits pooled aggregates to "capability-level coverage only".
- `exports.py:295-297` serialises the whole pooled aggregate under `coverage.pooled_by_capability`: pooled MAE, BIAS and RMSE (and pooled AARD for pressure), plus uncertainty-agreement counts.
- None of these pooled aggregates has a membership proof. Only the 12 per-system aggregates are proven.
- Only grouping key and `CoverageBlock` should be exported, or the pooled metrics must be proven and kept out of the coverage key.

**D-1 (minor): Plotly is loaded as soon as the package is imported.**
- `html.py` and `figures.py` import `pvt_phase_simulator.plotting` at module level, and that module imports Plotly straight away. `report/__init__.py` imports `html`.
- Result: importing `pvt_phase_simulator_validation.report` loads Plotly. I confirmed that the core validation package alone does not.
- The docstring in `__init__.py` ("Plotly is imported only when figures or HTML are actually rendered") is false, and the design's lazy-import requirement is not met.

**D-2 (minor): HTML section order differs from the spec.**
- The objective lists Provenance and Model Configuration right after Dataset Role.
- The report renders them after Limitations.
- The required placement of Failures right after Solver Coverage is honoured.

**D-3 (minor): some required links and counts are not implemented as specified.**
- The Accuracy "Membership" column prints `#membership-…` as escaped plain text, not a link.
- The F7 caption counts converged cases by listing cases in D rather than taking C's `CoverageBlock` integers. The counts are correct.
- The F5 and F6 axes do not say which phase is being compared (vapor for bubble, liquid for dew).

**D-4 (minor): the protected-files test misses some frozen paths and misses committed changes.**
- `test_protected_paths_remain_unchanged` does not cover the frozen A/B/C modules or their tests.
- It only compares the working tree against HEAD, so it cannot catch a frozen-path change that has been committed.
- The frozen files are currently unchanged.

**D-5 (info, a contradiction in the requirements, not a code defect).** The frozen sentence "…whether it was held out from solver development" contains the words "held out", while the rule forbids "held-out". The code emits the frozen sentence verbatim and never emits "held-out" or "blind".

<ORCHESTRATOR_RESULT>
{
  "verdict": "CONDITIONAL",
  "findings": [
    {"id": "C-1", "severity": "C", "blocks": true, "summary": "comparisons.csv labels every assessed row's absent standard_normalized_residual with D-invented reason COVERAGE_FACTOR_NOT_STATED; C populates it only when kind_used is STANDARD, so the reason is false and implies a U->u derivation that C-2 forbids (115 Module 17 rows). The docs repeat the claim, and the empty expanded-residual cell under STANDARD has no state/reason column."},
    {"id": "C-2", "severity": "C", "blocks": true, "summary": "JSON coverage.pooled_by_capability embeds full pooled_across_systems aggregates, including pooled MAE/BIAS/RMSE/AARD metrics and uncertainty-agreement counts, without membership proof, contrary to design section 5 'capability-level coverage only'."},
    {"id": "D-1", "severity": "D", "blocks": false, "summary": "Plotly is loaded as soon as the report package is imported (html.py/figures.py import pvt_phase_simulator.plotting at module level); the __init__ docstring and design lazy-import requirement are not met."},
    {"id": "D-2", "severity": "D", "blocks": false, "summary": "HTML renders Model Configuration and Provenance after Limitations instead of after Dataset Role as listed in the objective."},
    {"id": "D-3", "severity": "D", "blocks": false, "summary": "Accuracy membership column is plain text rather than a link; F7 caption counts converged cases in D instead of using C CoverageBlock; F5/F6 axes omit the compared composition phase."},
    {"id": "D-4", "severity": "D", "blocks": false, "summary": "Protected-path test omits frozen A/B/C modules and tests and only detects uncommitted changes."},
    {"id": "D-5", "severity": "D", "blocks": false, "summary": "Requirement contradiction: frozen sentence contains 'held out' while 'held-out' is forbidden; implementation emits the frozen sentence verbatim (informational)."}
  ],
  "safe_defer": ["D-1", "D-2", "D-3", "D-4", "D-5"]
}
</ORCHESTRATOR_RESULT>