# Independent audit: v2_01_b_module17_adapter

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
- Name: v2_01_b_module17_adapter
- Declared risk: MEDIUM
- Objective: Map the existing protected Module 17 independent experimental validation evidence onto
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

## Scientific invariants claimed to hold
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

## Repository state
- Branch: `v2-validation-framework`
- HEAD: `8a1205afe1b93e08aedc02e54d95caa900bff822`
- Base for this change: `8a1205afe1b93e08aedc02e54d95caa900bff822`

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
Changed files: ['docs/VALIDATION_FRAMEWORK.md', 'src/pvt_phase_simulator_validation/__init__.py', 'src/pvt_phase_simulator_validation/models.py', 'src/pvt_phase_simulator_validation/module17_adapter.py', 'src/pvt_phase_simulator_validation/provenance.py', 'src/pvt_phase_simulator_validation/serialization.py', 'tests/test_validation_core.py', 'tests/test_validation_module17_adapter.py', 'tests/test_validation_serialization.py']

## Builder's own report — treat as an unverified claim
```
Implemented the Module 17 adapter and vector-uncertainty schema v1.1.

Key results:

- Emits 40 bubble + 40 dew records.
- Preserves coverage exactly: bubble 31/9; dew 22/4/14.
- Keeps retrospective root data isolated in diagnostics.
- Preserves provenance and leaves coverage factor unset.
- Protected artifact hashes remain unchanged.
- Focused validation tests: 65 passed.
- Ruff, mypy, compileall passed.
- Repository-wide format check only flags a pre-existing `.ai` audit file outside the allowed scope; all changed files pass formatting.
- Full pytest was not run, per the work order’s build-time testing policy.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "Focused pytest: 65 passed, 1 non-test pytest-cache permission warning. Ruff check passed. Ruff format check passed for all changed/in-scope files; repository-wide format check flags only the pre-existing out-of-scope .ai/claude_audits/20260909-172636-v2_01_a_validation_core-audit.md. Mypy passed for 58 source files. Compileall passed. Protected artifact SHA-256 hashes verified unchanged. Full pytest intentionally not run per build-time testing policy.",
  "files_changed": ["docs/VALIDATION_FRAMEWORK.md", "src/pvt_phase_simulator_validation/__init__.py", "src/pvt_phase_simulator_validation/models.py", "src/pvt_phase_simulator_validation/provenance.py", "src/pvt_phase_simulator_validation/serialization.py", "src/pvt_phase_simulator_validation/module17_adapter.py", "tests/test_validation_core.py", "tests/test_validation_serialization.py", "tests/test_validation_module17_adapter.py"],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>
```

## Diff stat
```
 .ai/workflow_state.json                            | 89 ++++++++++++++++++----
 docs/VALIDATION_FRAMEWORK.md                       | 55 +++++++++++++
 src/pvt_phase_simulator_validation/__init__.py     | 12 +++
 src/pvt_phase_simulator_validation/models.py       | 18 ++++-
 src/pvt_phase_simulator_validation/provenance.py   | 27 +++++--
 .../serialization.py                               |  4 +-
 tests/test_validation_core.py                      | 81 ++++++++++++++++++++
 tests/test_validation_serialization.py             | 40 +++++++++-
 8 files changed, 300 insertions(+), 26 deletions(-)

```

## Full diff
```diff
diff --git a/.ai/workflow_state.json b/.ai/workflow_state.json
index d79d214..a33de51 100644
--- a/.ai/workflow_state.json
+++ b/.ai/workflow_state.json
@@ -1,14 +1,14 @@
 {
   "project": "pvt-phase-simulator",
   "phase": "post-v1.0-extensions",
-  "workflow_status": "APPROVED",
+  "workflow_status": "CLAUDE_RUNNING",
   "last_scientific_commit": "d2a0a74",
   "last_independent_audit_commit": "a0dcaf3c6a3ea96437ba8bca9305bb92815c024d",
   "work_packages_since_audit": 0,
-  "current_work_package": "v2_01_a_validation_core",
+  "current_work_package": "v2_01_b_module17_adapter",
   "current_risk": "MEDIUM",
-  "audit_required": false,
-  "audit_reason": null,
+  "audit_required": true,
+  "audit_reason": "package audit_policy=IMMEDIATE",
   "blocking_findings": [],
   "safe_defer_findings": [
     {
@@ -56,7 +56,7 @@
   ],
   "planned_scope": "Original 21-module Hydrocarbon Phase-Behavior & PVT Simulator",
   "planned_scope_complete": true,
-  "codex_correction_cycles": 0,
+  "codex_correction_cycles": 1,
   "claude_reaudit_cycles": 0,
   "provisional_review_cycles": 0,
   "claude_cost_usd_this_package": 0.0,
@@ -64,29 +64,29 @@
   "last_error": null,
   "workflow_id": "c3d365745ae6",
   "builder": "codex",
-  "reviewer": "claude",
-  "last_completed_stage": "committed",
+  "reviewer": "codex",
+  "last_completed_stage": "verified",
   "verification_status": "passed",
-  "base_commit": "610057c878a231565f2beff10e5fd13825458e46",
-  "resulting_commit": "a0dcaf3c6a3ea96437ba8bca9305bb92815c024d",
-  "builder_report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260909-164240-v2_01_a_validation_core-codex-report.md",
+  "base_commit": "8a1205afe1b93e08aedc02e54d95caa900bff822",
+  "resulting_commit": null,
+  "builder_report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260910-105648-v2_01_b_module17_adapter-codex-report.md",
   "builder_evidence": {
     "builder": "codex",
-    "package": "v2_01_a_validation_core",
+    "package": "v2_01_b_module17_adapter",
     "workflow_id": "c3d365745ae6",
-    "report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260909-164240-v2_01_a_validation_core-codex-report.md",
-    "report_sha256": "c3932b6facd4e7036cb03c813d47bce4b17b7df129d187059aea18a254659c4b",
+    "report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260910-105648-v2_01_b_module17_adapter-codex-report.md",
+    "report_sha256": "02fdd135751b01071e150910e2c1897078ce2459fbed88eef5fe1fde49890d5a",
     "revision": 1,
     "kind": "build"
   },
-  "tree_fingerprint": "c300734d969a1fe756c603b731876f65cbf01310a0c6e717cfa5192ecddb4080",
+  "tree_fingerprint": "3c18789be29477c9f1539c735cf04ee990c1209752e1b8f0c700f5074038d8df",
   "revisions": [
     {
-      "package": "v2_01_a_validation_core",
+      "package": "v2_01_b_module17_adapter",
       "revision": 1,
       "author": "codex",
       "kind": "build",
-      "at": 1788963506.7869718
+      "at": 1789028377.199698
     }
   ],
   "role_transitions": [
@@ -159,6 +159,13 @@
       "to_builder": "claude",
       "reason": "preferred builder claude is available",
       "at": 1788862175.1038766
+    },
+    {
+      "package": "v2_01_b_module17_adapter",
+      "from_builder": "codex",
+      "to_builder": "claude",
+      "reason": "preferred builder claude is available",
+      "at": 1789028920.3494034
     }
   ],
   "history": [
@@ -981,6 +988,56 @@
       "from": "CLAUDE_RUNNING",
       "to": "APPROVED",
       "reason": "independent audit approved"
+    },
+    {
+      "from": "APPROVED",
+      "to": "PLANNING",
+      "reason": "planning v2_01_b_module17_adapter"
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
+      "to": "CORRECTION_REQUIRED",
+      "reason": "local verification failed"
+    },
+    {
+      "from": "CORRECTION_REQUIRED",
+      "to": "CODEX_CORRECTION",
+      "reason": "correction cycle 1"
+    },
+    {
+      "from": "CODEX_CORRECTION",
+      "to": "HUMAN_ACTION_REQUIRED",
+      "reason": "role policy: Claude is a read-only reviewer and may not build or correct; preserve the work and wait for Codex"
+    },
+    {
+      "from": "HUMAN_ACTION_REQUIRED",
+      "to": "PLANNING",
+      "reason": "external resume shim: v2_01_b_module17_adapter build is complete and its work is intact; resuming into verification, independent audit and commit"
+    },
+    {
+      "from": "PLANNING",
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
index 4664189..ed93652 100644
--- a/docs/VALIDATION_FRAMEWORK.md
+++ b/docs/VALIDATION_FRAMEWORK.md
@@ -42,6 +42,11 @@ the helper accepts supplied bytes or UTF-8 text, returns `None` on a match, and
 
 Missing source uncertainty is represented only as `None`. A source-reported zero is a
 valid explicit `Uncertainty(value=0.0, ...)`; the framework never imputes it.
+`Uncertainty.value` has the same scalar or vector shape as its `ReferenceValue`.
+Vector uncertainty is an immutable tuple with one finite, non-negative value per
+reference-vector entry. For component-indexed mole fractions, that ordering is the
+case's ordered `component_ids`. Construction rejects scalar/vector mismatches and
+unequal vector lengths.
 
 ## Predictions and statuses
 
@@ -64,6 +69,12 @@ round-trip float representation. Decoders validate all required fields, reject u
 fields, restore identity from the payload, and check the record identity against its
 embedded case. Encoding, decoding, and encoding again is byte-identical.
 
+Schema version `1.1` extends `Uncertainty.value` from a scalar number to either a
+scalar number or an array of numbers. An array decodes to an immutable tuple and is
+encoded as an array again, so uncertainty shape is deterministic. This is the only
+`1.1` contract change. Version `1.0` is not accepted by the `1.1` reader: the package
+deliberately has no migration framework, and unsupported versions fail explicitly.
+
 Adding an enum member can be backward compatible only for writers and readers that
 both support it. A reader that encounters an unsupported schema version or a required
 enum value it does not know fails explicitly with `SchemaVersionError` or
@@ -75,6 +86,50 @@ contains no migration framework.
 commit, interpreter, platform, dataset identity/hash, command, and record content live
 outside that volatile block so run diffs remain meaningful.
 
+## Module 17 evidence adapter
+
+`load_module17_validation_evidence` is a read-only adapter over the existing May et
+al. source manifest, normalized experimental CSV, production-validation CSV, and
+summary JSON. It performs no equation-of-state calculation and has no dependency on
+the scientific engine. It verifies the normalized source hash, joins the experimental
+and legacy evidence by `source_point_id`, and rejects any exact disagreement in the
+duplicated reference fields.
+
+The adapter emits two `EXPERIMENTAL_VALIDATION` datasets, one each for `BUBBLE_POINT`
+and `DEW_POINT`. Each contains all 40 source points across both systems. A case ID is
+the source point ID plus its capability; the source reference retains the ThermoML
+pressure/vapor dataset and row coordinates. Temperature and the direction's specified
+composition are specified conditions. Experimental pressure and the opposite
+composition are references. Published pressure uncertainty remains scalar. Published
+vapor-composition uncertainty follows the vapor composition: it is attached to the
+bubble reference composition and to the dew specified composition. No uncertainty is
+invented for the liquid composition.
+
+Production-selected pressure and composition are prediction values only when the
+legacy solver outcome is `converged`. The exact legacy outcome is separately retained
+under the structured solver-metadata key `legacy_solver_outcome`, so `converged`,
+`not_found`, and `inconclusive` are queryable without parsing prose. The latter two
+use the generalized `FAILURE`/`SOLVER_FAILURE` shape; converged records use
+`REPORTED_NO_TOLERANCE`. The adapter assigns no accuracy status and stores none of the
+legacy error or uncertainty-normalized residual columns.
+
+All retrospective dew branch-scan, experimental-state, and
+`nearest_experimental_root` fields live only inside a diagnostic object marked
+`RETROSPECTIVE_DIAGNOSTIC`. The protected summary interpretation is retained with that
+object: the experimental-pressure scan identifies an already-existing nearest root
+but never replaces the production prediction. No retrospective field participates in
+constructing prediction values.
+
+The single framework `SourceManifest` is populated from the protected Module 17
+manifest rather than creating competing provenance. It retains citation, DOI, the
+ThermoML page URL, raw JSON URL, access date, raw and normalized hashes, measurement
+methods, compound mapping, uncertainty definitions, confidence, pressure conversion,
+selected ThermoML dataset metadata, anomalies, extraction coordinates, and the raw
+snapshot/redistribution policy. Selected-dataset metadata and source-only distinctions
+that lack dedicated V2-01-A fields are preserved as canonical JSON in the existing
+textual extraction provenance. `coverage_factor` remains `None`; a stated 95 percent
+confidence level does not imply a source-reported coverage factor.
+
 ## Deferred to V2-01-C
 
 **C-1 — the uncertainty-status guard is too permissive.** `ValidationRecord`
diff --git a/src/pvt_phase_simulator_validation/__init__.py b/src/pvt_phase_simulator_validation/__init__.py
index b87da1b..c298049 100644
--- a/src/pvt_phase_simulator_validation/__init__.py
+++ b/src/pvt_phase_simulator_validation/__init__.py
@@ -43,6 +43,13 @@ from .models import (
     ValidationRun,
     require_supported_schema_version,
 )
+from .module17_adapter import (
+    LEGACY_SOLVER_OUTCOME_KEY,
+    RETROSPECTIVE_DIAGNOSTIC_KIND,
+    Module17Adaptation,
+    adapt_module17_evidence,
+    load_module17_validation_evidence,
+)
 from .provenance import (
     CompoundIdentity,
     OriginalUnit,
@@ -61,6 +68,8 @@ from .serialization import (
 
 __all__ = [
     "MOLE_FRACTION_SUM_ABSOLUTE_TOLERANCE",
+    "LEGACY_SOLVER_OUTCOME_KEY",
+    "RETROSPECTIVE_DIAGNOSTIC_KIND",
     "SCHEMA_VERSION",
     "SUPPORTED_SCHEMA_VERSIONS",
     "CapabilityUnderTest",
@@ -77,6 +86,7 @@ __all__ = [
     "JsonScalar",
     "JsonValue",
     "MixedDataClassError",
+    "Module17Adaptation",
     "OriginalUnit",
     "PredictionOutcome",
     "PredictionValue",
@@ -97,6 +107,7 @@ __all__ = [
     "ValidationRecord",
     "ValidationRun",
     "ValidationStatus",
+    "adapt_module17_evidence",
     "decode_reference_dataset",
     "decode_validation_record",
     "decode_validation_run",
@@ -104,6 +115,7 @@ __all__ = [
     "encode_validation_record",
     "encode_validation_run",
     "homogeneous_data_class",
+    "load_module17_validation_evidence",
     "normalize_sha256",
     "require_supported_schema_version",
     "summarize_cross_check_agreement",
diff --git a/src/pvt_phase_simulator_validation/models.py b/src/pvt_phase_simulator_validation/models.py
index e57b5c5..8da8eb7 100644
--- a/src/pvt_phase_simulator_validation/models.py
+++ b/src/pvt_phase_simulator_validation/models.py
@@ -23,7 +23,7 @@ from .hashing import normalize_sha256
 from .json_values import FrozenJsonObject, JsonValue, freeze_json
 from .provenance import SourceManifest, Uncertainty
 
-SCHEMA_VERSION = "1.0"
+SCHEMA_VERSION = "1.1"
 SUPPORTED_SCHEMA_VERSIONS = frozenset({SCHEMA_VERSION})
 MOLE_FRACTION_SUM_ABSOLUTE_TOLERANCE = 1.0e-12
 
@@ -89,6 +89,22 @@ class ReferenceValue:
             self.uncertainty, Uncertainty
         ):
             raise TypeError("uncertainty must be Uncertainty or None")
+        if self.uncertainty is not None:
+            value_is_vector = isinstance(self.value, tuple)
+            uncertainty_is_vector = isinstance(self.uncertainty.value, tuple)
+            if value_is_vector != uncertainty_is_vector:
+                raise ValueError(
+                    "reference value and uncertainty must have the same scalar/vector "
+                    "shape"
+                )
+            if (
+                isinstance(self.value, tuple)
+                and isinstance(self.uncertainty.value, tuple)
+                and len(self.value) != len(self.uncertainty.value)
+            ):
+                raise ValueError(
+                    "uncertainty vector length must match the reference-value vector"
+                )
 
 
 @dataclass(frozen=True, slots=True)
diff --git a/src/pvt_phase_simulator_validation/provenance.py b/src/pvt_phase_simulator_validation/provenance.py
index 10feccf..f5a8a3f 100644
--- a/src/pvt_phase_simulator_validation/provenance.py
+++ b/src/pvt_phase_simulator_validation/provenance.py
@@ -68,17 +68,34 @@ class UnitConversion:
 class Uncertainty:
     """A source-reported uncertainty in the quantity's canonical SI unit."""
 
-    value: float
+    value: float | tuple[float, ...]
     kind: UncertaintyKind
     coverage_factor: float | None
     confidence_level_percent: float | None
     source: str
 
     def __post_init__(self) -> None:
-        require_finite(self.value, "uncertainty value")
-        if self.value < 0.0:
-            raise ValueError("uncertainty value must be non-negative")
-        object.__setattr__(self, "value", float(self.value))
+        if isinstance(self.value, bool):
+            raise TypeError("uncertainty value must be a scalar or vector of numbers")
+        if isinstance(self.value, (int, float)):
+            require_finite(self.value, "uncertainty value")
+            if self.value < 0.0:
+                raise ValueError("uncertainty value must be non-negative")
+            object.__setattr__(self, "value", float(self.value))
+        else:
+            if not isinstance(self.value, tuple):
+                raise TypeError("uncertainty value vectors must be immutable tuples")
+            if not self.value:
+                raise ValueError("uncertainty value vectors must not be empty")
+            for item in self.value:
+                if isinstance(item, bool) or not isinstance(item, (int, float)):
+                    raise TypeError(
+                        "uncertainty value vectors must contain only numbers"
+                    )
+                require_finite(item, "uncertainty value")
+                if item < 0.0:
+                    raise ValueError("uncertainty value must be non-negative")
+            object.__setattr__(self, "value", tuple(float(item) for item in self.value))
         require_enum(self.kind, UncertaintyKind, "uncertainty kind")
         if self.coverage_factor is not None:
             require_finite(self.coverage_factor, "coverage_factor")
diff --git a/src/pvt_phase_simulator_validation/serialization.py b/src/pvt_phase_simulator_validation/serialization.py
index 669b92f..40b2b43 100644
--- a/src/pvt_phase_simulator_validation/serialization.py
+++ b/src/pvt_phase_simulator_validation/serialization.py
@@ -133,7 +133,7 @@ def _identity_from(payload: object) -> DatasetIdentity:
 
 def _uncertainty_payload(value: Uncertainty) -> dict[str, object]:
     return {
-        "value": value.value,
+        "value": _value_payload(value.value),
         "kind": value.kind.value,
         "coverage_factor": value.coverage_factor,
         "confidence_level_percent": value.confidence_level_percent,
@@ -152,7 +152,7 @@ def _uncertainty_from(payload: object) -> Uncertainty:
     )
     _require_keys(item, fields, "uncertainty")
     return Uncertainty(
-        value=_number(item["value"], "uncertainty.value"),
+        value=_value_from(item["value"], "uncertainty.value"),
         kind=_enum(item["kind"], UncertaintyKind, "uncertainty.kind"),
         coverage_factor=_optional_number(
             item["coverage_factor"], "uncertainty.coverage_factor"
diff --git a/tests/test_validation_core.py b/tests/test_validation_core.py
index 8d882c7..74dc946 100644
--- a/tests/test_validation_core.py
+++ b/tests/test_validation_core.py
@@ -361,6 +361,87 @@ def test_uncertainty_absence_is_none_and_reported_zero_is_representable() -> Non
     assert reported_zero.uncertainty.value == 0.0
 
 
+def _uncertainty(value: float | tuple[float, ...]) -> Uncertainty:
+    return Uncertainty(
+        value=value,
+        kind=UncertaintyKind.EXPANDED,
+        coverage_factor=None,
+        confidence_level_percent=95.0,
+        source="Synthetic source-reported expanded uncertainty.",
+    )
+
+
+@pytest.mark.parametrize(
+    ("reference_value", "uncertainty_value"),
+    [
+        (1.0, (0.1,)),
+        ((0.25, 0.75), 0.1),
+    ],
+)
+def test_reference_value_rejects_scalar_vector_uncertainty_shape_mismatches(
+    reference_value: float | tuple[float, ...],
+    uncertainty_value: float | tuple[float, ...],
+) -> None:
+    with pytest.raises(ValueError, match="same scalar/vector shape"):
+        ReferenceValue(
+            ValidationQuantity.MOLE_FRACTION,
+            reference_value,
+            _uncertainty(uncertainty_value),
+        )
+
+
+def test_reference_value_rejects_wrong_uncertainty_vector_length() -> None:
+    with pytest.raises(ValueError, match="uncertainty vector length"):
+        ReferenceValue(
+            ValidationQuantity.MOLE_FRACTION,
+            (0.25, 0.75),
+            _uncertainty((0.01, 0.01, 0.01)),
+        )
+
+
+@pytest.mark.parametrize(
+    "value",
+    [
+        float("nan"),
+        float("inf"),
+        float("-inf"),
+        (0.1, float("nan")),
+        (0.1, float("inf")),
+    ],
+)
+def test_uncertainty_rejects_non_finite_scalar_and_vector_values(
+    value: float | tuple[float, ...],
+) -> None:
+    with pytest.raises(ValueError, match="finite"):
+        _uncertainty(value)
+
+
+@pytest.mark.parametrize("value", [-0.1, (0.1, -0.01)])
+def test_uncertainty_rejects_negative_scalar_and_vector_values(
+    value: float | tuple[float, ...],
+) -> None:
+    with pytest.raises(ValueError, match="non-negative"):
+        _uncertainty(value)
+
+
+@pytest.mark.parametrize("value", [True, (0.1, True), [0.1, 0.2]])
+def test_uncertainty_rejects_non_numeric_or_mutable_values(value: object) -> None:
+    with pytest.raises(TypeError, match="uncertainty value"):
+        _uncertainty(value)  # type: ignore[arg-type]
+
+
+def test_vector_uncertainty_retains_explicit_zero_and_component_order() -> None:
+    value = ReferenceValue(
+        ValidationQuantity.MOLE_FRACTION,
+        (0.25, 0.75),
+        _uncertainty((0.0, 0.02)),
+    )
+    case = replace(_case(), reference_values=(value,))
+    assert case.component_ids == ("methane", "ethane")
+    assert value.uncertainty is not None
+    assert value.uncertainty.value == (0.0, 0.02)
+
+
 @pytest.mark.parametrize(
     "composition",
     [(0.2, 0.2), (-0.1, 1.1), (0.1, 0.2, 0.7)],
diff --git a/tests/test_validation_serialization.py b/tests/test_validation_serialization.py
index 7f85656..1d078ad 100644
--- a/tests/test_validation_serialization.py
+++ b/tests/test_validation_serialization.py
@@ -20,6 +20,8 @@ from pvt_phase_simulator_validation import (
     RunMetadata,
     SchemaVersionError,
     SerializationError,
+    Uncertainty,
+    UncertaintyKind,
     UnsupportedValueError,
     ValidationPrediction,
     ValidationQuantity,
@@ -109,6 +111,40 @@ def test_float_serialization_uses_python_round_trip_representation() -> None:
     assert decoded.prediction.values[0].value == value
 
 
+def test_uncertainty_scalar_and_vector_shapes_survive_round_trip() -> None:
+    dataset = _dataset()
+    vector_uncertainty = Uncertainty(
+        value=(0.025, 0.01),
+        kind=UncertaintyKind.EXPANDED,
+        coverage_factor=None,
+        confidence_level_percent=95.0,
+        source="Synthetic per-component expanded uncertainty.",
+    )
+    composition = dataset.cases[0].reference_values[1]
+    case = replace(
+        dataset.cases[0],
+        reference_values=(
+            dataset.cases[0].reference_values[0],
+            replace(composition, uncertainty=vector_uncertainty),
+        ),
+    )
+    encoded = encode_reference_dataset(replace(dataset, cases=(case,)))
+    document = _document(encoded)
+    decoded = decode_reference_dataset(encoded)
+    decoded_pressure = decoded.cases[0].reference_values[0].uncertainty
+    decoded_composition = decoded.cases[0].reference_values[1].uncertainty
+
+    assert decoded_pressure is not None
+    assert isinstance(decoded_pressure.value, float)
+    assert decoded_composition is not None
+    assert decoded_composition.value == (0.025, 0.01)
+    assert isinstance(decoded_composition.value, tuple)
+    assert document["reference_dataset"]["cases"][0]["reference_values"][1][
+        "uncertainty"
+    ]["value"] == [0.025, 0.01]
+    assert encode_reference_dataset(decoded) == encoded
+
+
 def test_record_identity_is_retained_and_decoder_takes_no_identity_argument() -> None:
     encoded = encode_validation_record(_record())
     decoded = decode_validation_record(encoded)
@@ -233,8 +269,8 @@ def test_unknown_fields_are_not_silently_dropped() -> None:
 def test_duplicate_json_keys_are_rejected_instead_of_overwritten() -> None:
     encoded = encode_validation_record(_record()).decode()
     tampered = encoded.replace(
-        '"schema_version":"1.0"',
-        '"schema_version":"1.0","schema_version":"99.0"',
+        f'"schema_version":"{SCHEMA_VERSION}"',
+        f'"schema_version":"{SCHEMA_VERSION}","schema_version":"99.0"',
         1,
     )
     with pytest.raises(SerializationError, match="duplicate JSON object key"):

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
