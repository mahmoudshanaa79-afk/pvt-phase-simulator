# V2-01-D design record: professor-facing validation evidence report

Status: APPROVED for implementation.

This record exists because the approved design was delivered as a document on
2026-09-24 and was never written to the repository. It is persisted here before any
implementation so that the builder and the independent auditor read the same
authoritative text.

The design was delivered as two files with the same content:

| File | SHA-256 |
|---|---|
| `OpenPhase_V2-01-D_Design.docx` | `4f0e4726ababe5cc7940c7c62fd36a1334d9969810799ec5639315c4d7cccb6b` |
| `OpenPhase_V2-01-D_Design.pdf` | `0ccedb41aca94e9baecd3631071ec34eb86b94e609047491989dcae9351094a7` |

Section 1 is a faithful Markdown transcription of that design. Its text is
character-identical to the DOCX once whitespace is normalised, and its bold, italic
and monospace formatting matches the DOCX character for character. Its word sequence
matches the PDF except for list markers (automatic numbers and bullet glyphs), which
Markdown expresses as list syntax. Only the presentation was adapted:

- The document title is a level-3 heading and the design's numbered headings are
  level-4, nested under this record's Section 1.
- Monospace (Consolas) text is inline code. The two monospace blocks in section 6 are
  fenced code blocks with their spacing kept exactly.
- The PDF's running page footer is omitted.

SHA-256 of Section 1, from its first line (`### V2-01-D design: …`) to the end of this
file, as UTF-8 with LF line endings:
50d3308c459362de8ddf0025aa8a2d52c89df3935649a3073412789dd2eb3c3e.

This record contains the design only. It does not record the execution authorization.

---

## Section 1 - Approved design (faithful transcription)

### V2-01-D design: professor-facing validation evidence report

*Reproduced verbatim from Claude Code's repository-grounded design response of 24 September 2026 (OpenPhase repository, branch v2-validation-framework at f8e7fdc). Design only: nothing was implemented, committed or pushed.*

#### 1. Repository reality and C evidence check

**State.** Branch `v2-validation-framework` at `f8e7fdc`: clean, 0 ahead and 0 behind origin. `master` and `origin/master` are at `610057c` (tags `v1.0.0`, `v1.1.0`, `v1.2.0`). **D has not started**: no report module exists and `.ai/work_packages/` holds only A, B and C. The schema is `1.2`.

**C is verified and approved, and the evidence binds to the final revision:**

- **Single revision.** The revision ledger holds one entry, Codex revision 1, with no correction.

- **Verification.** `.ai/verification/20260915-112359-…` passed all five gates, **1432 passed**. Its changed-file set is **identical to commit** `0ed2942` (18 of 18 files).

- **Audit.** `20260915-112402-…-audit.md` is APPROVED with no A/B findings. The prompt's embedded diff was truncated, and the Method section shows the auditor re-derived claims from on-disk code in three read-only passes.

- **Workflow state.** `resulting_commit 0ed2942`, `verification_status passed`, `last_completed_stage committed`.

- **HEAD code.** HEAD differs from `0ed2942` only in `.ai/` evidence (zero other files), so the 1432 result describes HEAD's code.

- **CI.** HEAD is green. Two earlier runs on this branch (`582bb1a`, `d69eaef`) failed the Ruff format step on committed audit Markdown; `8a1205a` fixed that. It was not a C defect, and the brief doesn't mention it.

**One limitation.** Verification records store neither a content hash nor a commit SHA. The binding of verified content to `0ed2942` therefore rests on the identical file set plus one uninterrupted engine run. The recorded `tree_fingerprint` can't be recomputed after the fact, because it included untracked files present at that moment. This is adequate here and belongs in the orchestrator backlog, not in D.

#### 2. 283.38 K provenance finding

| **Layer** | **Evidence** |
|----|----|
| Case IDs | `may2015_ch4_c3_023::bubble_point`, `::dew_point` |
| Normalized row | T = 283.38 K; P = 7630 kPa → 7 630 000 Pa; x = (0.4586, 0.5414); y = (0.7955, 0.2045); U(P) = 54 kPa; U(y<sub>C3H8</sub>) = 0.0046; 95 %; ThermoML pressure dataset 3 row 1, vapor dataset 4 row 1 |
| Primary archive | NIST ThermoML record streamed live today. Raw SHA-256 `77630E90…659662` **equals** the manifest's `raw_json_sha256` |
| Dataset 3 | "Vapor or sublimation pressure, kPa"; liquid-phase property; closed-cell static method. Variable 1 is "Temperature, K" = 283.38 (5 digits); variable 2 is liquid x(CH₄) = 0.4586; P = 7630 (3 digits); combined expanded U = 54 |
| Dataset 4 | Gas-phase mole fraction of propane (component 3); chromatography; same (T, x); y = 0.2045, U = 0.0046 |
| Extractor | Re-running `tools/extract_may_2015_thermoml.py` on the live record reproduces the normalized CSV **byte-for-byte** (SHA-256 `04ED00B6…07BD`, equal to the manifest) |
| Mapping guard | The extractor validates exact ThermoML variable descriptors and pairs points by (T, x), never by array index |
| Article | ThermoML's *own* citation title reads "…from (203 to 273) K…". The article's tables are inaccessible from here (the publisher returns HTTP 403) |

**Finding:** the value is **faithfully sourced from the archive and correctly mapped**, and it appears independently in both paired datasets. Whether the **published article's tables contain this state is UNRESOLVED**. The 273.48 K point (`c3_022`) also exceeds the title range, by 0.48 K. No correction or exclusion is justified.

**D disclosure:**

- A "Source anomalies" callout appears in the Scope section and again at the head of the CH₄+C₃H₈ results. It renders the manifest's `source_anomalies` text verbatim, plus the archive-verification record, stating "article table check: not performed (article inaccessible)".

- The case stays in every primary result.

- The sensitivity section shows C's alternate subset.

**Missing evidence:** the article's CH₄+C₃H₈ data table or its supporting information. If that table is obtained and disagrees with the archive, the fix belongs in a separate, scoped provenance-correction package, never inside D.

**Additional primary-source finding.** ThermoML records the uncertainties as evaluated by the **"Data file compiler"**, by "Propagation of evaluated standard uncertainties", at a 95 % level of confidence. The manifest does not capture the evaluator or the method. So the "published U" is the archive compiler's combined expanded uncertainty, not demonstrably the authors' own figure. No number and no C-2 semantics change (the value is still expanded, used directly, with k unknown), but the report's wording must say so.

#### 3. Verified facts, discrepancies, missing evidence

**Verified.** The brief's project-state table holds. So do its Module 17 facts: 40 states in 17 + 23, the stated ranges, the coverage splits and the AARDs. C reproduces the protected summary bit-exactly.

**Corrections to the brief:**

1.  **D-2.** The brief says to render the case as UNAVAILABLE. I recommend failing report generation explicitly instead (§10).

2.  **"Reuse existing plots"** isn't possible for C-sourced figures (§5).

3.  **"No parameters fitted"** exists only in prose (`docs/EXPERIMENTAL_VALIDATION.md` l. 64–66) and in code. It appears in **no structured evidence artifact**.

4.  `docs/EXPERIMENTAL_VALIDATION.md` l. 196 says "Module 18 has not started", which is stale. D sources no state claims from that document.

**Missing evidence. Every conclusion that depends on these items is provisional:**

- **M-1.** The article table (see §2). Article-level consistency of the 283.38 K point is provisional.

- **M-2.** The model configuration of the *stored* predictions is not recorded in the artifacts. kij = 0 appears only as 4 × `BinaryInteractionPolicy.DEFAULT_ZERO` in the frozen validator, which references no other policy member. The EOS constants live in the engine, and "no tuning" is prose only.

- **M-3. Dataset role.** Git history shows:

  - the data entered at `80e8146` (2026-08-23), together with its validator, extractor and predictions;

  - that commit touched **no** production solver file;

  - the saturation solver was last changed at `248787a`, two days earlier;

  - later EOS commits touched only `pseudo_arclength.py`, `criticality.py` and `critical_point.py`.

  Whether the source was consulted *before* it was committed can't be established from the repository, so the solver-development role and holdout status remain **NOT ESTABLISHED**.

- **M-4.** The prediction artifact doesn't embed the revision that generated it. It was introduced at `80e8146` and never regenerated. `test_one_point_production_validation…` reproduces one stored dew prediction today, which is only a partial link between today's engine and the stored predictions.

- **M-5.** The manifest lacks the uncertainty evaluator and method (§2).

- **M-6.** Verification records carry no content hash (§1).

#### 4. Recommended scope and explicit non-goals

**One package, V2-01-D:**

- A `pvt_phase_simulator_validation.report` subpackage that assembles a `ValidationEvidence` bundle from A, B and C. It renders **four artifacts**: a self-contained HTML report, versioned JSON, a comparisons CSV and a case-ledger CSV.

- A **structured, versioned Module 17 evidence declaration** that closes M-2 through M-5. Every fact in it carries its basis and evidence pointers.

- A CLI.

- A framework-document section.

**Non-goals:**

- No metrics or formulas, and no C changes. The C-owned API gap for membership is solved without touching C (§8).

- No engine, data, manifest, `plotting.py` or `EXPERIMENTAL_VALIDATION.md` changes.

- No new dependency and no PDF: kaleido is absent and would be a new dependency.

- **No Streamlit hook, deferred to V2-02.** The UI has been protected throughout V2, and V2 isn't deployed (the public app serves `master`). The existing page also hard-codes kij prose and plots legacy records, so integrating properly is dashboard work.

- **No cross-check rendering.** Numerical cross-check input is *refused*, which keeps the separation structural until a real cross-check package defines its own vocabulary.

- No dew investigation, no E, no CoolProp.

#### 5. Existing code to reuse

| **Symbol (actual)** | **D uses it for** |
|----|----|
| `adapt_module17_evidence` | datasets, records, `interpretation` |
| `compare_record(record, capability)` | every `CaseComparison` |
| `aggregate_experimental_accuracy(cases)` | per-group aggregates (`PER_COMPONENT` default) |
| same, `vector_observation_unit=PER_CASE_VECTOR, reduction=MEAN_ABS_COMPONENT` | LD-2 companion view |
| same, `pooled_across_systems=True` | capability-level **coverage only** (31/40, 22/40); pooled accuracy is not displayed |
| `aggregate_group` | membership proof (§8) |
| `align_values` | identity-aligned reference/prediction pairs for tables and parity plots |
| `analyze_sensitivity`, `module17_anomaly_subset` | sensitivity |
| `legacy_descriptive_statistics`, `module17_discrepancies` | legacy box, LD-1..3 |
| `METRIC_POLICY`, `format_metric` | policy statements, primary metrics, text form |
| `encode_scientific_artifact` | embed C objects in the JSON unchanged |
| `ValidationRun`, `RunMetadata`, `DatasetPin`, `SourceManifest` | run and provenance records |
| Engine: `PENG_ROBINSON_OMEGA_A/B`, `calculate_kappa`, `BinaryInteractionPolicy`, `load_component_database`/`get_component`, `plotting.PressureUnit`/`convert_pressure` | derived model constants; checking the declared κ(ω) and policy; Tc/Pc/ω plus citations; display-unit conversion only |

**Conventions mirrored, not imported,** from `pvt_phase_simulator_ui/reports.py`:

- `html.escape` at every insertion point;

- status classes `available`, `unavailable`, `failed`, `not-applicable`, `incomplete`;

- section-id pattern;

- a format-version constant.

The validation and UI packages currently have zero imports in either direction, and D keeps it that way.

**Not reused:** `plot_validation_*`**.** These functions consume `ValidationPlotRecord` rows built from the protected CSV. The records carry the *legacy* `*_pressure_relative_error` columns and retrospective fields in the same object, in a Module 17-specific bubble/dew shape. Using them would plot legacy values instead of C outputs, and they wouldn't generalize to V2-01-E.

**Figures use Plotly**, already a runtime dependency (6.9.0).

#### 6. Proposed architecture and public API

```text
src/pvt_phase_simulator_validation/report/
  __init__.py        public API; plotly imported lazily
  __main__.py        CLI
  evidence.py        assemble ValidationEvidence from A/B/C - no formulas
  declarations.py    load + schema-validate evidence declarations
  declarations/module17.json
  membership.py      group membership + proof by re-invoking C
  figures.py         Plotly figures from C and record values
  html.py            renderer: escaping, sections, CSS, plotly.js inlined once
  exports.py         canonical JSON, comparisons CSV, case-ledger CSV
```

```text
build_validation_evidence(repository_root, *, dataset="module17",
                          run_id=None, clock=None) -> ValidationEvidence
render_html(evidence) -> str
export_json(evidence) -> str
export_comparisons_csv(evidence) -> str
export_case_ledger_csv(evidence) -> str
write_validation_report(evidence, output_dir) -> ReportArtifacts   # paths + SHA-256
# python -m pvt_phase_simulator_validation.report --output build/validation_evidence
```

**Errors:**

- `EvidenceInconsistencyError`: a membership-proof failure, a count or identity mismatch, or missing required evidence.

- `UnsupportedDataClassError`: `NUMERICAL_CROSS_CHECK` input.

**Structural diagnostic isolation.** `evidence.production` is built only from `prediction.values` and C outputs. `evidence.diagnostics` is a *different type*, built only from `prediction.diagnostics` and the adapter's `interpretation`. Figure and table builders accept only the production type.

#### 7. Report sections → evidence

| **§** | **Content** | **Source** | **Basis** |
|----|----|----|----|
| A Summary | per-capability coverage; per-group primary metrics with N compared of M total; dataset-role line; anomaly flag. **No score.** | C pooled/group aggregates, `METRIC_POLICY.primary`, declaration, manifest | derived |
| B Scope | groups; T, P and composition ranges over all M cases | C `GroupingKey`s; record values | derived |
| C Dataset role | five roles with status, basis and evidence | declaration | declared/verified |
| D Provenance | citation, DOI, URLs, access date, hashes, methods, InChIKeys, conversions, redistribution policy, archive verification | `SourceManifest`, `DatasetPin`, declaration | derived + declared |
| E Model configuration | Ωa/Ωb; κ(ω); mixing rule; policy; Tc/Pc/ω with citations | engine constants; declaration; component DB | derived / declared-verified |
| F Conditions | specified and reference quantities with phase and component identity; uncertainty availability | records | derived |
| G Solver coverage | total, excluded, eligible, converged, not_found, inconclusive, other_failure | `CoverageBlock` | derived |
| H Comparison coverage | reference available *of total*, compared, observations, uncertainty-assessable | `CoverageBlock`, comparison states | derived |
| I Accuracy | enabled metrics only | `MetricResult` | derived |
| J Uncertainty | agreement groups; per-comparison assessments | `UncertaintyAgreementCount`, `UncertaintyAssessment`/`NotAssessed` | derived |
| K Plots | reference/prediction values and C errors | records via `align_values`; `ObservationErrors` | derived |
| L Worst cases | ranked within a `GroupingKey` | `ObservationErrors` | derived |
| M Failures | every non-converged case with its reason verbatim | `solver_outcome`, `failure_reason` | derived |
| N Unavailable | reference-unavailable vs **uncertainty-unavailable**, kept distinct | comparison state, `NotAssessed` reason | derived |
| O Sensitivity | primary, alternate, shift | `SensitivityAnalysis` | derived |
| P Diagnostics | boxed: **RETROSPECTIVE DIAGNOSTICS — NOT PRODUCTION PREDICTIONS** | `prediction.diagnostics`, `interpretation` | derived |
| Q Limitations | reference-only scope; solver and model limits | `UncertaintyScope`, policy statements, reviewed fixed text | fixed text |
| R Software verification | what checks exist, with file pointers. **No test counts**: the report runs no tests, and CI holds the status for that revision | repository paths | pointers |
| S Reproducibility | run and revision metadata (§11) | `ValidationRun` + report metadata | derived |
| T Inventory | files, purposes, format versions, JSON/CSV SHA-256 | writer | derived |
| Legacy box | within-2U counts; LD-1..3 records verbatim | `LegacyDescriptiveStatistics`, `LegacyDiscrepancy` | derived |

#### 8. Coverage, traceability, dataset role, uncertainty

**Coverage, following C's actual counting:**

- `total_cases` includes excluded cases.

- `eligible = total − excluded`.

- `converged + not_found + inconclusive + other_failure = eligible`. Every eligible case has a solver outcome in schema 1.2, so **attempted ≡ eligible**. D shows no separate "attempted" figure and invents no "not attempted" state.

- `reference_available_cases` is counted *before* the exclusion check, so it is labelled "of total", never "of eligible".

- `compared ≤ min(converged, reference_available)`; `uncertainty_assessable ≤ compared`.

- Solver outcome, reference availability, comparison state and uncertainty assessability appear in **separate tables** and never add up.

- D displays C's integers only. "Reference available: 40 of 40" is shown as such, never computed by subtraction.

- NOT_FOUND carries the frozen wording.

**Traceability without touching C.** Aggregates carry no member IDs, which is a real gap. D partitions cases by the `GroupingKey`'s own fields, then **re-invokes C's** `aggregate_group` **on that membership and requires the result to equal C's summary aggregate** by frozen-dataclass equality. It also requires the contributing (case, component) count to equal `metric_observation_count`, and any mismatch fails generation. The membership list is therefore proven by C's own code, not re-derived by D. Every aggregate row links to `aggregates[*].membership`, which lists the ordered case IDs and the contributing observations.

**Dataset role.** Five roles, each with a status (USED, NOT_USED or NOT_ESTABLISHED) and a basis:

- **DERIVED**: read from structured evidence at generation time.

- **DECLARED_VERIFIED**: a declaration that an automated test checks against the frozen engine.

- **DECLARED**: a declaration with evidence pointers, verified by the audit.

| **Role** | **Module 17** | **Basis** |
|----|----|----|
| parameter_fitting | **NOT_USED**: Tc/Pc/ω cite Yang & Richter (2025); policy `default_zero` leaves no interaction parameter to fit | derived + declared-verified |
| solver_development | **NOT_ESTABLISHED** (M-3 evidence attached) | declared |
| regression_testing | **USED**: `test_experimental_validation.py`, C equivalence tests, protected artifacts | declared |
| evaluation | **USED** | declared |
| held_out_from_development | **NOT_ESTABLISHED**. The words "blind" and "held-out" never appear | declared |

Rendered as: *"No model parameters were fitted to this dataset. Repository evidence does not establish whether it was held out from solver development."*

**Uncertainty:**

- C fields are rendered verbatim: EXPANDED, PUBLISHED.

- k is shown as "not stated by the source", never blank and never 2.

- Confidence is shown as "95 % (as recorded)".

- The source wording comes from the declaration: "combined expanded uncertainty evaluated by the ThermoML data-file compiler".

- The full reference-only limitation text is printed.

- Vector rows show `ALL_COMPONENTS_WITHIN_REFERENCE_UNCERTAINTY` with per-component residuals keyed by component ID, and never "joint coverage".

- Legacy 2U counts appear only inside the boxed legacy section.

#### 9. Tables, plots, JSON, CSV

**Tables (HTML).** Scope → solver coverage → **failures (immediately after coverage, never an appendix)** → comparison coverage → accuracy → uncertainty → worst cases → reference/uncertainty-unavailable → sensitivity → legacy box → diagnostics box → model configuration → provenance → reproducibility → inventory.

- **Accuracy.** Composition gets PER_COMPONENT *and* PER_CASE_VECTOR mean rows, labelled separately.

- **Worst cases.** Top 5 per `GroupingKey`, COMPARED comparisons only. The ranking key follows the first primary metric: pressure → C `absolute_relative_error`; mole fraction → C per-component `absolute_error`, one row per (case, component). The ranking metric is named in the caption, and ties break by case ID, then component ID.

- **Display.** Pressure is shown in MPa (an explicit display conversion) with 6 significant figures in HTML. JSON and CSV keep full round-trip precision in SI. An unavailable value is always a labelled status with its reason, never blank and never 0.

**Figures.** Plotly, deterministic div IDs, hover shows the case ID, and every caption states "N compared of M total":

- **F1.** Pressure parity per capability, one trace per system, with an identity line.

- **F2–F4.** Signed relative pressure error (%) against specified T (F2), reference P (F3) and specified CH₄ fraction, with its phase labelled (F4, the CH₄+C₃H₈ dew question).

- **F5.** Mole-fraction parity per capability, one subplot per component ID.

- **F6.** Signed mole-fraction error against T.

- **F7.** Solver outcome against specified T. This is the only place failures can appear graphically, since they have no prediction to plot.

That is 14 figures for Module 17. **Size:** the inlined `plotly.min.js` is **4.63 MB**. That makes the report self-contained, offline and deterministic; a CDN link was rejected because it adds a network dependency and version drift.

**JSON** (`openphase.validation_evidence` v1.0.0). Top-level keys: `format`, `volatile` (run_id, generated_at_utc), `report_metadata`, `dataset`, `dataset_role`, `source_provenance`, `model_configuration`, `scope`, `coverage`, `aggregates` (with membership), `uncertainty_assessments`, `cases`, `failures`, `sensitivity`, `legacy`, `diagnostics` (retrospective only), `reproducibility`, `content_sha256`.

- C objects are embedded through `encode_scientific_artifact`, never re-serialized by D.

- `sort_keys`, `allow_nan=False`, round-trip `repr` floats.

- An undefined metric is C's `{state: UNDEFINED, value: null, reason}`.

- `content_sha256` is the SHA-256 of the canonical JSON without `volatile` or itself.

`comparisons.csv`**.** One row per QuantityComparison × component, covering **all states**, so failure rows appear with empty values and explicit state columns. Columns:

- dataset_id/version, data_class, system_id, capability, case_id, source_reference;

- quantity, phase, component_id, unit, comparison_state, solver_outcome;

- specified T, specified phase and mole fraction;

- reference and predicted values;

- signed, absolute and relative error, with relative-error state and reason;

- uncertainty kind, derivation, denominator, k, confidence, scope;

- expanded and standard normalized residuals, criterion, uncertainty agreement or not-assessed reason;

- tolerance agreement or reason, tolerance kind, value and citation.

An empty cell always has a state/reason column beside it.

`case_ledger.csv`**.** One row per case (80 rows): identity, source reference, specified conditions (vector with component IDs), solver outcome, prediction outcome, failure reason, excluded flag and reason, reference-available keys, compared keys, sensitivity-subset membership, and a has-retrospective-diagnostics flag.

#### 10. Deferred C findings

| **Finding** | **Classification** | **D treatment** |
|----|----|----|
| D-1: plain decode path lacks `parse_constant` | **Report-layer mitigation** | D never decodes through that path. It writes with `allow_nan=False` through C's encoder, and its tests re-parse every export with a strict constant-rejecting parser |
| D-2: overflow in `_shape` raises `ValueError` | **No impact** | Unreachable at physical magnitudes. If it ever fires, report generation fails explicitly; D wraps `compare_record` in no `try`. Rendering "UNAVAILABLE", as the brief suggests, would disguise a bug |
| D-3: first reason instead of `NO_USABLE_OBSERVATIONS` | **No impact** | Only pressure has relative metrics, and every Module 17 reference pressure is positive. D renders C's reason verbatim, and every per-comparison reason stays visible in the CSV |
| D-4: exact-float uncertainty strata | **No impact** | Module 17 has one stratum (EXPANDED, PUBLISHED, k None, 95.0). D renders C's strata and never merges them |
| D-5: DENSITY policy inconsistency | **No impact, confirmed** | DENSITY's `per_observation` lacks `absolute_relative` while AARD is enabled. No density evidence exists, and D renders policy only for quantities present in the evidence |

None of these blocks D, and C is not reopened.

#### 11. Reproducibility, determinism, visual acceptance

**Revisions kept distinct:**

- **Predictions:** the stored artifact was introduced at `80e8146`, and the generating revision is not embedded in it. This is declared.

- **Metrics and report:** `git rev-parse HEAD` plus the tree state (CLEAN, DIRTY or UNKNOWN). A dirty tree produces a prominent banner: "not reproducible from a commit".

**Recorded:** format and schema versions, package version, Python version, coarse platform (OS and architecture only), dataset pins (raw and normalized SHA-256), the reproduction command, run_id and timestamp (volatile). **Repository-relative paths only**: no usernames, hostnames or absolute paths.

**Determinism.** Groups, cases, components and rows are sorted explicitly, and the volatile block is isolated. With an injected clock and run_id, two runs produce the same `content_sha256`, identical CSVs, and identical HTML once the volatile block is masked.

**Visual acceptance** runs on the approved revision **before commit**. I'll generate the real Module 17 report and inspect it in the browser at about 1280 px and about 400 px wide, checking:

- tables scroll horizontally without breaking the page;

- scientific notation, units, legends, axes and captions;

- failure counts and unavailable labels;

- DOI and citation wrapping;

- the diagnostic warning and the primary-versus-alternate distinction.

The package therefore uses `commit_policy MANUAL`. Any visual defect goes back through a Codex correction, full verification, re-audit and re-inspection, so approval always applies to the final revision.

#### 12. Paths

**Allowed:** `src/pvt_phase_simulator_validation/report/**`, `tests/test_validation_report*.py`, `docs/VALIDATION_FRAMEWORK.md`.

**Protected** (everything else, and specifically):

- `src/pvt_phase_simulator/**`, `data/**`, `docs/validation/**`, `docs/EXPERIMENTAL_VALIDATION.md`

- `tests/golden_master/**`, `src/pvt_phase_simulator_ui/**`, `tools/**`

- **all existing A/B/C modules** under `src/pvt_phase_simulator_validation/`

- `pyproject.toml`, `uv.lock`, `.github/**`

#### 13. Acceptance criteria and focused test plan

**Acceptance:**

1.  D contains no metric or error formula. An AST scan of `report/` finds no arithmetic on error or metric values.

2.  Groups are discovered from evidence (4 groups, 8 aggregates, found rather than asserted).

3.  The membership proof passes for every aggregate.

4.  HTML, JSON and both CSVs agree with C objects value for value, and CSV reference − prediction consistency is checked in tests only.

5.  All 80 cases appear in the ledger, every failure appears in the failure table, and no observation is lost.

6.  Diagnostics never leak: a sentinel planted in `prediction.diagnostics` appears only in the diagnostics sections.

7.  Cross-check input is refused.

8.  No NaN or Infinity appears, and no undefined metric renders as 0.

9.  Uncertainty wording is right: k is never 2, the reference-only text is present, and 2U appears only in the legacy box.

10. Sensitivity keeps the primary result and shows the alternate separately.

11. Dataset role renders with its statuses and bases, and "blind" and "held-out" never appear.

12. The declared κ(ω), Ωa/Ωb and policy are checked against the frozen engine.

13. Hostile metadata is neutralised: `<script>`, quotes and `javascript:` URLs are escaped or left unlinked, and only validated `https://doi.org/…` and https archive links are emitted, with `rel="noopener noreferrer"`.

14. No external resource loads.

15. Determinism holds.

16. Protected artifacts are unchanged.

17. Full verification is green at ≥ 1432 tests.

18. Visual QA passes (§11).

**Tests:**

- **Unit:** declarations schema, escaping, formatting, CSV and JSON writers.

- **Integration:** real Module 17 generation, with every table and figure input cross-checked against C objects.

- **Adversarial:** diagnostic leakage, mixed or cross-check data classes, non-finite values, empty and undefined metrics, OTHER_FAILURE, reference-unavailable versus uncertainty-unavailable, hostile and very long citations, a missing declaration field, and a membership-proof tamper that must fail.

- **Determinism:** masked-volatile comparison.

- **Manual:** visual QA.

#### 14. Build and audit scope

**Codex builds** exactly §6 and §9 within §12's paths, using focused tests only. It may not touch A/B/C modules, the engine, data, UI, tools or dependencies. Membership comes from re-invoking C, never from D logic.

**The Claude read-only audit attacks, in order:**

1.  any hidden formula or recomputation;

2.  diagnostic leakage;

3.  lost failures or observations and axis double-counting;

4.  uncertainty wording (k, 2U, reference-only, joint-coverage language);

5.  dataset-role overclaim;

6.  soundness of the membership proof;

7.  JSON/CSV/HTML/C disagreement;

8.  HTML injection and links;

9.  determinism;

10. the 283.38 K disclosure;

11. protected-file changes.

No unrelated architecture critique. After approval, I perform visual QA and then commit.

#### 15. Material unresolved decisions

None blocks the package. I'll apply these defaults unless you say otherwise:

1.  `commit_policy MANUAL`, so visual QA gates the commit.

2.  **Record the archive-verified uncertainty evaluator in D's declaration**, not in the protected manifest, and note the manifest gap for a later provenance package.

3.  **Solver-development role and holdout status stay NOT ESTABLISHED.** The only thing that could change this is your own knowledge. If you can state that you didn't consult May et al. while building the saturation solver (5–21 August), I can record it as *ATTESTED*, clearly distinct from verified. That is a scientific-meaning decision, and it is optional.

4.  **Optional human action:** through AUB library access, check the article's CH₄+C₃H₈ table for T = 283.38 K, P = 7.630 MPa, x₁ = 0.4586, y(C₃H₈) = 0.2045. D discloses the question either way.

#### 16. READY TO PREPARE IMPLEMENTATION PACKAGE: **YES**

- **C's approval binds to HEAD's code.**

- **Every report fact has a derivable source or a declared, evidence-pointed source.** Facts that existed only in prose are now structured.

- **The one C API gap has a zero-C-change solution:** membership is proven by re-invoking `aggregate_group`.

- **No deferred finding blocks honest reporting.**

- **No open decision changes scientific meaning** unless you choose the optional attestation.

Nothing was implemented, created, committed or pushed this turn. My only writes were scratch files outside the repository. I read the NIST ThermoML record into memory to verify the 283.38 K provenance and saved none of it.
