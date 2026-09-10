# Independent audit: v2_01_a_validation_core

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
- Name: v2_01_a_validation_core
- Declared risk: MEDIUM
- Objective: Create the type system, provenance model and serialization contract that every future
OpenPhase validation dataset will use, so that adding a new publication later means
writing a manifest and a small loader rather than building another bespoke validation
pipeline. This package writes NO science, computes NO error metrics, and adds NO data.
Its value is that it makes certain scientific mistakes structurally difficult.

THE CENTRAL REQUIREMENT
A comparison against EXPERIMENT and a comparison against ANOTHER MODEL must never be
combinable into one statistic. Enforce this with types, not conventions:

- DataClass is EXPERIMENTAL_VALIDATION or NUMERICAL_CROSS_CHECK.
- It is declared once on the dataset and propagated immutably into every case and
  record. There must be NO public API through which a caller supplies or overrides a
  record's DataClass independently of its parent dataset.
- Aggregation entry points accept only a homogeneous collection and raise
  MixedDataClassError otherwise.
- Summary containers are DISTINCT TYPES with distinct vocabulary:
  ExperimentalAccuracySummary (speaks of accuracy) and CrossCheckAgreementSummary
  (speaks of agreement). There must be no type into which both kinds of record can be
  placed.

CLARIFICATION 1 - DATASET AND DATA-CLASS IDENTITY
Introduce a small immutable DatasetIdentity value object carrying exactly dataset_id,
dataset_version and data_class. A ValidationCase and a ValidationRecord each hold that
identity, so they know their own provenance without any caller re-supplying it. Cases
are created through, or reference, their parent dataset identity, and construction
validates that a case's identity agrees with the dataset that contains it;
disagreement is an error, never a silent fix.

Serialized records explicitly retain the immutable dataset identity, including
data_class, and decoding restores it from the payload rather than from any caller
argument. Provide adversarial tests proving that a record decoded from serialized form
cannot be reclassified from EXPERIMENTAL_VALIDATION to NUMERICAL_CROSS_CHECK or the
reverse, through constructors, decoding, copying, dataclasses.replace, or mutation.

CLARIFICATION 2 - HASH VERIFICATION RESPONSIBILITY
This package does not load real datasets, so it must NOT claim that constructing a
ReferenceDataset proves normalized_sha256 matches external content: no content bytes
or path are supplied here. The responsibility of this package is limited to
representing source hashes, validating their syntax and shape (64 hexadecimal
characters for SHA-256, normalized consistently), preserving them faithfully through
serialization, and providing one deterministic helper that verifies SUPPLIED bytes or
content against an expected hash.

Actual verification of normalized dataset content happens later, in V2-01-B or
V2-01-E, where a loader holds the real content. Test the helper with synthetic
in-memory bytes only. Do not read anything under data/ or docs/validation/.

CLARIFICATION 3 - SCHEMA AND ENUM EVOLUTION
Do not claim new quantities or capabilities can be added "without schema change"
unqualified. Define this behaviour explicitly and simply:
- schema_version identifies the serialization contract.
- Adding an enum member may be backward compatible for writers and readers that
  support it.
- A reader encountering an unknown or unsupported required enum value, or an
  unsupported schema_version, MUST fail explicitly with a clear error
  (SchemaVersionError or an unsupported-value error).
- Never silently coerce, default, or drop an unknown quantity or capability.
Do NOT build a migration framework in this package.

DATA MODEL
Canonical SI throughout; original units and conversions recorded as provenance.
- ReferenceDataset: identity (DatasetIdentity), schema_version, SourceManifest,
  CapabilityUnderTest, and its cases.
- ValidationCase: case_id, dataset identity, system_id, ordered component_ids,
  specified_conditions (what is given) and reference_values (what is compared), plus a
  reference back to the source point (row or dataset number).
  Separating specified conditions from reference values is what makes the schema
  source-agnostic: a bubble point specifies temperature and liquid composition and
  references pressure and vapour composition; a pure saturation point specifies
  temperature and references pressure; a flash specifies temperature, pressure and
  feed and references vapour fraction and phase compositions. One schema, no
  per-publication special cases.
- ReferenceValue: quantity, value (scalar or component-indexed vector), optional
  Uncertainty.
- ValidationPrediction: case_id, outcome (VALUE or FAILURE), values (empty on
  failure), failure_reason, diagnostics preserved verbatim, solver metadata.
- ValidationRecord: case + prediction + status + dataset identity. Error metrics are
  attached later by V2-01-C and are NOT computed here.
- ValidationRun: records plus reproducibility metadata.

CapabilityUnderTest: PURE_SATURATION_PRESSURE, BUBBLE_POINT, DEW_POINT, FLASH,
CRITICAL_POINT, COMPRESSIBILITY.

ValidationQuantity: PRESSURE, TEMPERATURE, MOLE_FRACTION, VAPOR_FRACTION,
COMPRESSIBILITY_FACTOR, DENSITY. Each quantity carries its canonical SI unit and a
relative_error_meaningful boolean with a short rationale. MOLE_FRACTION and
VAPOR_FRACTION are False because they approach 0 and 1, so percentage error is
meaningless there. V2-01-C will consume this flag; encoding it here makes the rule
structural rather than a convention.

PROVENANCE
SourceManifest generalizes the existing may_2015 manifest, which is already the right
shape: source_id, citation_text, doi, archive_name, archive_url, access_date,
raw_sha256, normalized_sha256, raw_snapshot_retained, raw_snapshot_policy,
measurement_methods, uncertainty_definition, coverage_factor,
confidence_level_percent, original_units, unit_conversions, compound identity mapping
(name, formula, InChIKey, CAS), extraction_method and data_class. A dataset cannot be
constructed without citation and hash fields present.

Uncertainty: value in SI, kind (STANDARD or EXPANDED), coverage_factor,
confidence_level_percent, source. Absent uncertainty is None - never zero, never
imputed.

STATUS VOCABULARY
AGREES_WITHIN_UNCERTAINTY, OUTSIDE_UNCERTAINTY, AGREES_WITHIN_DECLARED_TOLERANCE,
OUTSIDE_DECLARED_TOLERANCE, REPORTED_NO_TOLERANCE, SOLVER_FAILURE,
REFERENCE_UNAVAILABLE, EXCLUDED.

REPORTED_NO_TOLERANCE is the honest default: a quantitative error is recorded and no
badge is asserted. Define the vocabulary and its consistency rules here; V2-01-C
computes and assigns statuses.

DeclaredTolerance is a record type carrying quantity, value, unit, justification,
source_citation and scope. It cannot be constructed without a justification and a
citation. SHIP ZERO INSTANCES of it in this package. Invent no thresholds anywhere.

REPRODUCIBILITY
ValidationRun pins run_id, UTC timestamp, framework schema_version, OpenPhase package
version, git commit SHA, Python version, platform, dataset ids with versions and
content hashes, and the reproduction command. Records are ordered deterministically by
case_id. Two runs on the same commit and dataset must produce byte-identical output
apart from run_id and timestamp, which stay confined to one clearly delimited metadata
block so diffs remain meaningful.

INVARIANTS TO ENFORCE AND TEST
1. A record's data_class always equals its dataset's; it cannot be set independently.
2. Building a summary from records of more than one data_class raises
   MixedDataClassError.
3. ExperimentalAccuracySummary rejects NUMERICAL_CROSS_CHECK records, and vice versa.
4. A prediction with outcome FAILURE carries no values and forces SOLVER_FAILURE
   status.
5. A record with status EXCLUDED must carry a non-empty exclusion_reason.
6. A DeclaredTolerance without justification and source_citation cannot be constructed.
7. Absent uncertainty is None; zero is representable only if the source states it.
8. Mole-fraction vectors are ordered by the dataset's component_ids and sum to 1
   within a stated tolerance, or the case is rejected at construction.
9. All dataclasses are frozen; datasets, cases and records are immutable.
10. encode then decode then encode is byte-identical.
11. Serialized floats use round-trip repr, matching the golden-master convention.
12. Source hashes are syntactically validated and preserved through serialization; the
    content-verification helper accepts matching and rejects non-matching supplied
    bytes. Construction does NOT claim to have verified external content.
13. Unknown or unsupported enum values and schema versions are rejected explicitly.
14. No API returns a boolean meaning "accuracy passed".

BUILD-TIME TESTING POLICY
Run only focused tests for what you changed, plus Ruff and mypy if useful. Do NOT run
the whole pytest suite for reassurance; the orchestrator runs the authoritative
full-suite verification after you finish, and duplicating it wastes a great deal of
wall-clock time. All fixtures in this package are synthetic and in-memory: no test may
read data/ or docs/validation/, which keeps this package independent of V2-01-B and E.

## Scientific invariants claimed to hold
  - The scientific engine is frozen: no file under src/pvt_phase_simulator/, data/, docs/validation/ or tests/golden_master/ may change.
  - This package performs no thermodynamic calculation and imports nothing from pvt_phase_simulator.eos.
  - EXPERIMENTAL_VALIDATION and NUMERICAL_CROSS_CHECK records can never be combined into one statistic or summary.
  - A record's DataClass is inseparable from its dataset identity and survives serialization and decoding unchanged.
  - No accuracy threshold, default tolerance, or boolean meaning 'accuracy passed' may exist anywhere in this package.
  - Solver failures are preserved as failures and can never become ordinary successful records.
  - Provenance cannot be constructed incomplete: a dataset requires citation and hash fields.
  - Hash claims must not exceed what is actually verified: construction validates hash syntax only; content verification requires supplied bytes.
  - Unknown or unsupported enum values and schema versions are rejected explicitly and never silently coerced.

## Repository state
- Branch: `v2-validation-framework`
- HEAD: `610057c878a231565f2beff10e5fd13825458e46`
- Base for this change: `610057c878a231565f2beff10e5fd13825458e46`

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
Changed files: ['docs/VALIDATION_FRAMEWORK.md', 'src/pvt_phase_simulator_validation/__init__.py', 'src/pvt_phase_simulator_validation/_validation.py', 'src/pvt_phase_simulator_validation/aggregation.py', 'src/pvt_phase_simulator_validation/enums.py', 'src/pvt_phase_simulator_validation/exceptions.py', 'src/pvt_phase_simulator_validation/hashing.py', 'src/pvt_phase_simulator_validation/json_values.py', 'src/pvt_phase_simulator_validation/models.py', 'src/pvt_phase_simulator_validation/provenance.py', 'src/pvt_phase_simulator_validation/py.typed', 'src/pvt_phase_simulator_validation/serialization.py', 'tests/test_validation_core.py', 'tests/test_validation_serialization.py']

## Builder's own report — treat as an unverified claim
```
Implemented the validation core with immutable identities, provenance, strict data-class separation, deterministic serialization, schema rejection, hash verification, status invariants, documentation, and 40 synthetic tests.

No protected scientific files were modified. Full-suite pytest remains for the orchestrator per the build-time policy.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "Focused pytest: 40 passed, 1 non-failing pytest-cache permission warning. Ruff check: passed. Ruff format --check: 257 files formatted. mypy src app: success, 57 source files. compileall src app: passed.",
  "files_changed": [
    "docs/VALIDATION_FRAMEWORK.md",
    "src/pvt_phase_simulator_validation/__init__.py",
    "src/pvt_phase_simulator_validation/_validation.py",
    "src/pvt_phase_simulator_validation/aggregation.py",
    "src/pvt_phase_simulator_validation/enums.py",
    "src/pvt_phase_simulator_validation/exceptions.py",
    "src/pvt_phase_simulator_validation/hashing.py",
    "src/pvt_phase_simulator_validation/json_values.py",
    "src/pvt_phase_simulator_validation/models.py",
    "src/pvt_phase_simulator_validation/provenance.py",
    "src/pvt_phase_simulator_validation/py.typed",
    "src/pvt_phase_simulator_validation/serialization.py",
    "tests/test_validation_core.py",
    "tests/test_validation_serialization.py"
  ],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>
```

## Diff stat
```
 .ai/workflow_state.json | 55 +++++++++++++++++++++++++++++++++++--------------
 1 file changed, 40 insertions(+), 15 deletions(-)

```

## Full diff
```diff
diff --git a/.ai/workflow_state.json b/.ai/workflow_state.json
index e89667c..b8a1d2c 100644
--- a/.ai/workflow_state.json
+++ b/.ai/workflow_state.json
@@ -1,14 +1,14 @@
 {
   "project": "pvt-phase-simulator",
   "phase": "post-v1.0-extensions",
-  "workflow_status": "APPROVED",
+  "workflow_status": "CLAUDE_RUNNING",
   "last_scientific_commit": "d2a0a74",
   "last_independent_audit_commit": "f7f6e79286dbced51f07ea19ab95d0c986bad9f4",
   "work_packages_since_audit": 0,
-  "current_work_package": "05_v1_2_release_qa",
-  "current_risk": "LOW",
-  "audit_required": false,
-  "audit_reason": null,
+  "current_work_package": "v2_01_a_validation_core",
+  "current_risk": "MEDIUM",
+  "audit_required": true,
+  "audit_reason": "package audit_policy=IMMEDIATE",
   "blocking_findings": [],
   "safe_defer_findings": [
     {
@@ -67,28 +67,28 @@
   "workflow_id": "c3d365745ae6",
   "builder": "codex",
   "reviewer": "claude",
-  "last_completed_stage": "committed",
+  "last_completed_stage": "verified",
   "verification_status": "passed",
-  "base_commit": "b95f80c2889f95b4164959f187a111dad67b3394",
-  "resulting_commit": "f7f6e79286dbced51f07ea19ab95d0c986bad9f4",
-  "builder_report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260908-133040-05_v1_2_release_qa-codex-report.md",
+  "base_commit": "610057c878a231565f2beff10e5fd13825458e46",
+  "resulting_commit": null,
+  "builder_report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260909-164240-v2_01_a_validation_core-codex-report.md",
   "builder_evidence": {
     "builder": "codex",
-    "package": "05_v1_2_release_qa",
+    "package": "v2_01_a_validation_core",
     "workflow_id": "c3d365745ae6",
-    "report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260908-133040-05_v1_2_release_qa-codex-report.md",
-    "report_sha256": "ff28f99db820b91d24d2a41a7ef0f53ba918597719bf4d861a9e4e3439679c90",
+    "report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260909-164240-v2_01_a_validation_core-codex-report.md",
+    "report_sha256": "c3932b6facd4e7036cb03c813d47bce4b17b7df129d187059aea18a254659c4b",
     "revision": 1,
     "kind": "build"
   },
-  "tree_fingerprint": "2d904d41672955f76341b976503524b2815ab3a5dd269a9c8b7d9edfc0fae8d6",
+  "tree_fingerprint": "c300734d969a1fe756c603b731876f65cbf01310a0c6e717cfa5192ecddb4080",
   "revisions": [
     {
-      "package": "05_v1_2_release_qa",
+      "package": "v2_01_a_validation_core",
       "revision": 1,
       "author": "codex",
       "kind": "build",
-      "at": 1788865133.0810683
+      "at": 1788963506.7869718
     }
   ],
   "role_transitions": [
@@ -953,6 +953,31 @@
       "from": "CLAUDE_RUNNING",
       "to": "APPROVED",
       "reason": "independent audit approved"
+    },
+    {
+      "from": "APPROVED",
+      "to": "PLANNING",
+      "reason": "planning v2_01_a_validation_core"
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
