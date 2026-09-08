# Independent audit: 04_engineering_report

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
- Name: 04_engineering_report
- Declared risk: MEDIUM
- Objective: Provide a useful downloadable engineering/scientific case report built ENTIRELY from results OpenPhase has already computed. The report renders results; it never recomputes them and never starts a calculation.

CONTENT, where available: case identification; date and version where appropriate; fluid composition; temperature and pressure with their units; the model (Peng-Robinson EOS); the verified component scope; the kij assumption; the calculation inputs; phase and stability result; flash result; liquid and vapour fractions; phase compositions; Z factors; bubble and dew outputs if calculated; sweep summaries if calculated; the critical point if calculated; convergence and status information; model assumptions; limitations; and the validation/provenance references the repository already supports.

TRUTHFULNESS. The report must never fabricate a missing result. Every field that is unavailable or that failed appears explicitly as unavailable or failed - never blank, never zero, never interpolated. Only a genuinely converged result may be presented as a result.

FORMAT. Choose the lightest robust format the existing infrastructure already supports - HTML or Markdown assembled from the existing adapters is sufficient, and a printable HTML report is preferred. Do NOT add a reporting framework or any heavy new dependency for visual polish. Add PDF only if it is reliable with dependencies already present and does not become a reporting detour; if in doubt, do not add PDF. Keep the existing CSV and JSON exports working unchanged.

SCOPE. No new thermodynamics. The scientific engine is frozen and must not change, and no thermodynamic relation may be implemented or restated in the application layer.

TESTS. Cover: a report generated from a real computed case; unavailable and failed fields being labelled as such rather than blank; units being stated explicitly; the report never triggering a calculation; and the existing exports still working. Avoid brittle hard-coded one-ULP float strings.

BUILD-TIME TESTING POLICY. Run only focused tests for the files and behaviour you changed, plus Ruff and mypy if useful. Do NOT run the whole pytest suite for reassurance - the orchestrator runs the authoritative full-suite verification after you finish, and duplicating it wastes a great deal of wall-clock time.

## Scientific invariants claimed to hold
  - The scientific engine is frozen: no file under src/pvt_phase_simulator/, data/, docs/validation/ or tests/golden_master/ may change.
  - No thermodynamic relation may be implemented, restated or approximated in the application layer.
  - Unavailable quantities are reported as unavailable and never fabricated or interpolated.
  - Structured failures remain failures; only CriticalPointStatus.CONVERGED is a certified critical point.

## Repository state
- Branch: `app-v1.2-engineering`
- HEAD: `9a34001c12d6718bfa9745405b51daf922da901b`
- Base for this change: `9a34001c12d6718bfa9745405b51daf922da901b`

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
Changed files: ['docs/STREAMLIT_APPLICATION.md', 'src/pvt_phase_simulator_ui/reports.py', 'src/pvt_phase_simulator_ui/views.py', 'tests/test_app_reports.py', 'tests/test_app_streamlit.py']

## Builder's own report — treat as an unverified claim
```
Implemented a printable, dependency-free HTML engineering report generated only from stored, non-stale result exports.

- Covers inputs, units, model scope, flash/stability, compositions, Z factors, envelope, critical point, sweep summary, limitations, and provenance.
- Explicitly labels unavailable, not-applicable, and failed values.
- Preserves existing CSV/JSON behavior.
- Protected artifact hashes remain unchanged.
- Full pytest suite was intentionally not run per the build-time testing policy.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "10 report tests passed; 6 focused Streamlit tests passed; 4 export-adapter tests and 1 sweep-export test passed; 5 final Streamlit/release tests passed including startup health smoke. Ruff check and format check passed; mypy passed for 47 source files; compileall passed.",
  "files_changed": ["src/pvt_phase_simulator_ui/reports.py", "src/pvt_phase_simulator_ui/views.py", "tests/test_app_reports.py", "tests/test_app_streamlit.py", "docs/STREAMLIT_APPLICATION.md"],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>
```

## Diff stat
```
 .ai/work_packages/01_model_and_limitations.json |   2 +-
 .ai/work_packages/02_field_units.json           |   2 +-
 .ai/work_packages/03_case_save_load.json        |   4 +-
 .ai/work_packages/04_engineering_report.json    |   2 +-
 .ai/work_packages/05_v1_2_release_qa.json       |   2 +-
 .ai/workflow_state.json                         | 424 +++++++++++++++++++++++-
 docs/STREAMLIT_APPLICATION.md                   |  25 +-
 src/pvt_phase_simulator_ui/views.py             |  23 ++
 tests/test_app_streamlit.py                     |  26 +-
 9 files changed, 480 insertions(+), 30 deletions(-)

```

## Full diff
```diff
diff --git a/.ai/work_packages/01_model_and_limitations.json b/.ai/work_packages/01_model_and_limitations.json
index 391a62e..e19d93d 100644
--- a/.ai/work_packages/01_model_and_limitations.json
+++ b/.ai/work_packages/01_model_and_limitations.json
@@ -62,6 +62,6 @@
   "audit_policy": "IMMEDIATE",
   "commit_policy": "AFTER_AUDIT",
   "dependencies": [],
-  "status": "PENDING",
+  "status": "COMMITTED",
   "notes": "Every claim on the panel must be traceable to something already in the repository. Do not invent a limitation, a scope boundary or a citation that is not already recorded."
 }
diff --git a/.ai/work_packages/02_field_units.json b/.ai/work_packages/02_field_units.json
index 83a7939..17c6d57 100644
--- a/.ai/work_packages/02_field_units.json
+++ b/.ai/work_packages/02_field_units.json
@@ -64,6 +64,6 @@
   "dependencies": [
     "01_model_and_limitations"
   ],
-  "status": "PENDING",
+  "status": "COMMITTED",
   "notes": "The engine keeps receiving SI and keeps returning SI. Conversion factors are exact where they are exact; a round-trip through a unit must not silently lose precision. No thermodynamics is duplicated."
 }
diff --git a/.ai/work_packages/03_case_save_load.json b/.ai/work_packages/03_case_save_load.json
index 6b410ca..73e53f1 100644
--- a/.ai/work_packages/03_case_save_load.json
+++ b/.ai/work_packages/03_case_save_load.json
@@ -1,6 +1,6 @@
 {
   "name": "03_case_save_load",
-  "objective": "Let a user save a complete, reproducible case and load it again later: composition, temperature and pressure, unit selections, sweep settings where applicable, the relevant calculation inputs, and a schema version identifier. Serialize deterministic JSON. Loading validates before any scientific call is made.",
+  "objective": "Let a user save a complete, reproducible OpenPhase case to a file and load it back later, restoring the same valid application inputs. Reproducibility is the entire point of this package.\n\nSAVED CONTENT. The case must capture all input state needed to reproduce the run, as applicable: selected components; mole fractions; temperature; pressure; the presentation unit selections (pressure Pa/MPa/bar/psi and temperature K/degC/degF); sweep settings; any other relevant calculation inputs; and an explicit schema/version identifier.\n\nFORMAT. Deterministic JSON: the same case must serialise to the same bytes, with stable key ordering. The schema version is explicit and written into the file.\n\nLOADING. Validate the entire file BEFORE any scientific call is made. No calculation may run against unvalidated input. Malformed JSON, an invalid schema, an unknown or future schema version, and an invalid composition must each produce a clear, specific, user-facing error message - never a raw traceback. Never silently invent a missing value, and never silently normalise or repair an invalid composition: a composition that does not total 100 mol % must fail exactly the way typing it by hand fails. Unknown or future schema versions are refused, not guessed at.\n\nSAFETY. Use only safe deserialisation - plain JSON parsing. Do not use pickle, eval, or any mechanism that can execute content from the file.\n\nSCOPE. Restoring inputs only. The scientific engine is frozen and must not change, and no thermodynamic relation may be implemented or restated in the application layer.\n\nTESTS. Cover: round-trip save/load; malformed JSON; invalid schema; unsupported/future version; invalid composition; unit selections surviving the round trip; sweep inputs surviving where applicable; and that loading does not execute any science before validation. Avoid brittle hard-coded one-ULP float strings.\n\nBUILD-TIME TESTING POLICY. Run only focused tests for the files and behaviour you changed, plus Ruff and mypy if useful. Do NOT run the whole pytest suite for reassurance - the orchestrator runs the authoritative full-suite verification after you finish, and duplicating it wastes a great deal of wall-clock time.",
   "risk": "MEDIUM",
   "allowed_files": [
     "src/pvt_phase_simulator_ui/**",
@@ -64,6 +64,6 @@
   "dependencies": [
     "02_field_units"
   ],
-  "status": "PENDING",
+  "status": "COMMITTED",
   "notes": "A loaded case that is invalid is rejected, never quietly repaired: a composition that does not total 100 mol % must fail the same way typing it by hand fails. Unknown or future schema versions are refused rather than guessed at."
 }
diff --git a/.ai/work_packages/04_engineering_report.json b/.ai/work_packages/04_engineering_report.json
index 0af62c4..e4fa6ff 100644
--- a/.ai/work_packages/04_engineering_report.json
+++ b/.ai/work_packages/04_engineering_report.json
@@ -1,6 +1,6 @@
 {
   "name": "04_engineering_report",
-  "objective": "Produce a downloadable case report from results that have already been computed. Include the case inputs, the model and its scope, the flash result and phase state, compositions and Z factors, sweep summaries and the critical point where those exist, the model limitations, the provenance, and an explicit statement of every field that is unavailable or failed. Reuse the existing export infrastructure; keep CSV and JSON export working unchanged.",
+  "objective": "Provide a useful downloadable engineering/scientific case report built ENTIRELY from results OpenPhase has already computed. The report renders results; it never recomputes them and never starts a calculation.\n\nCONTENT, where available: case identification; date and version where appropriate; fluid composition; temperature and pressure with their units; the model (Peng-Robinson EOS); the verified component scope; the kij assumption; the calculation inputs; phase and stability result; flash result; liquid and vapour fractions; phase compositions; Z factors; bubble and dew outputs if calculated; sweep summaries if calculated; the critical point if calculated; convergence and status information; model assumptions; limitations; and the validation/provenance references the repository already supports.\n\nTRUTHFULNESS. The report must never fabricate a missing result. Every field that is unavailable or that failed appears explicitly as unavailable or failed - never blank, never zero, never interpolated. Only a genuinely converged result may be presented as a result.\n\nFORMAT. Choose the lightest robust format the existing infrastructure already supports - HTML or Markdown assembled from the existing adapters is sufficient, and a printable HTML report is preferred. Do NOT add a reporting framework or any heavy new dependency for visual polish. Add PDF only if it is reliable with dependencies already present and does not become a reporting detour; if in doubt, do not add PDF. Keep the existing CSV and JSON exports working unchanged.\n\nSCOPE. No new thermodynamics. The scientific engine is frozen and must not change, and no thermodynamic relation may be implemented or restated in the application layer.\n\nTESTS. Cover: a report generated from a real computed case; unavailable and failed fields being labelled as such rather than blank; units being stated explicitly; the report never triggering a calculation; and the existing exports still working. Avoid brittle hard-coded one-ULP float strings.\n\nBUILD-TIME TESTING POLICY. Run only focused tests for the files and behaviour you changed, plus Ruff and mypy if useful. Do NOT run the whole pytest suite for reassurance - the orchestrator runs the authoritative full-suite verification after you finish, and duplicating it wastes a great deal of wall-clock time.",
   "risk": "MEDIUM",
   "allowed_files": [
     "src/pvt_phase_simulator_ui/**",
diff --git a/.ai/work_packages/05_v1_2_release_qa.json b/.ai/work_packages/05_v1_2_release_qa.json
index 176aa10..0cd371d 100644
--- a/.ai/work_packages/05_v1_2_release_qa.json
+++ b/.ai/work_packages/05_v1_2_release_qa.json
@@ -1,6 +1,6 @@
 {
   "name": "05_v1_2_release_qa",
-  "objective": "Final application-level verification of the complete v1.2 product. Exercise first use, every navigation page, flash, sweeps, field units, save and load, exports, the report, stale-result protection, invalid-input protection, deployment smoke readiness, and the truthfulness of the documentation against what the application actually does. No new features.",
+  "objective": "Final application-level verification of the complete v1.2 product. This package adds NO capability; its job is to test the actual product and close the gaps it finds. No feature creep.\n\nUSER JOURNEY to exercise end to end: home/first use; fluid setup; examples; single-state analysis; flash; bubble and dew; phase envelope; engineering sweeps; field units; save and load; exports; the engineering report; the science/methodology pages; and limitations/validation.\n\nVERIFY: a new user can run a meaningful example; input errors are reported in normal language; no raw traceback is ever exposed to an ordinary user; units are obvious and consistent; non-SI presentation never alters internal science; stale-result protection works and a changed input can never display an obsolete result as current; invalid compositions are rejected; failed or non-converged science is never hidden; plots are readable; sweep failure gaps remain explicit rather than interpolated; exports preserve precision and state their units; save/load is reproducible; the report is truthful; limitations are accessible; and the stated model scope is truthful.\n\nTRUTHFULNESS OF CLAIMS: no claim of commercial PVT capability; no unsupported component implied; the kij = 0 assumption visible; and the verified components remain methane, ethane and propane unless evidence in the repository says otherwise. Where documentation and the application disagree, correct the documentation to match the application - never the reverse.\n\nREADINESS: deployment smoke readiness, clean-environment startup, and the Streamlit application launching correctly.\n\nFix P0/P1 release defects. Record non-blocking P2/P3 findings rather than fixing them. The scientific engine is frozen and must not change.\n\nBUILD-TIME TESTING POLICY. Run only focused tests for the files and behaviour you changed, plus Ruff and mypy if useful. Do NOT run the whole pytest suite for reassurance - the orchestrator runs the authoritative full-suite verification after you finish, and duplicating it wastes a great deal of wall-clock time.",
   "risk": "LOW",
   "allowed_files": [
     "tests/test_app_*.py",
diff --git a/.ai/workflow_state.json b/.ai/workflow_state.json
index a6e5b0a..b1dda46 100644
--- a/.ai/workflow_state.json
+++ b/.ai/workflow_state.json
@@ -3,19 +3,31 @@
   "phase": "post-v1.0-extensions",
   "workflow_status": "CLAUDE_RUNNING",
   "last_scientific_commit": "d2a0a74",
-  "last_independent_audit_commit": "c29ae4961543e74a271e8e2e54de22852892cf00",
+  "last_independent_audit_commit": "9a34001c12d6718bfa9745405b51daf922da901b",
   "work_packages_since_audit": 0,
-  "current_work_package": "01_model_and_limitations",
-  "current_risk": "LOW",
-  "audit_required": false,
-  "audit_reason": null,
+  "current_work_package": "04_engineering_report",
+  "current_risk": "MEDIUM",
+  "audit_required": true,
+  "audit_reason": "package audit_policy=IMMEDIATE",
   "blocking_findings": [],
   "safe_defer_findings": [
     {
       "id": "D-1",
       "severity": "D",
       "blocks": false,
-      "summary": "adapters.py's COMPONENT_NAMES was changed from a hardcoded literal to a value derived from COMPONENTS; harmless and value-preserving (confirmed by test run) but technically broader than the 'documentation/presentation only, new panel' framing of the work package."
+      "summary": "test_loading_invalid_file_cannot_execute_science feeds malformed JSON to a monkeypatched _cached_flash, which never reaches the flash call regardless of the patch; the test can't actually distinguish gated-science from never-called-anyway. Coverage of the real claim (successful load never runs science) is adequately provided elsewhere by test_applying_loaded_case_restores_widget_inputs_without_results."
+    },
+    {
+      "id": "D-2",
+      "severity": "D",
+      "blocks": false,
+      "summary": "case_files.py's _integer() has an unreachable except OverflowError clause; Python's int(x) on an already-int x never raises OverflowError. Dead code, no functional effect."
+    },
+    {
+      "id": "D-3",
+      "severity": "D",
+      "blocks": false,
+      "summary": "load_case() has no intrinsic byte-size guard; the only size cap is the UI's file_uploader max_upload_size=1MB. Not exploitable via the current UI-only call site but worth noting if load_case is ever called directly by an untrusted caller."
     }
   ],
   "deferred_independent_audits": [
@@ -52,7 +64,7 @@
   ],
   "planned_scope": "Original 21-module Hydrocarbon Phase-Behavior & PVT Simulator",
   "planned_scope_complete": true,
-  "codex_correction_cycles": 0,
+  "codex_correction_cycles": 1,
   "claude_reaudit_cycles": 0,
   "provisional_review_cycles": 0,
   "claude_cost_usd_this_package": 0.0,
@@ -60,32 +72,103 @@
   "last_error": null,
   "workflow_id": "c3d365745ae6",
   "builder": "codex",
-  "reviewer": "claude",
-  "last_completed_stage": "audited",
+  "reviewer": "codex",
+  "last_completed_stage": "verified",
   "verification_status": "passed",
-  "base_commit": "46b1d8e75c60d76b5e7d920ef30f6c1f14da051d",
+  "base_commit": "9a34001c12d6718bfa9745405b51daf922da901b",
   "resulting_commit": null,
-  "builder_report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260906-004904-01_model_and_limitations-codex-report.md",
+  "builder_report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260908-000441-04_engineering_report-codex-report.md",
   "builder_evidence": {
     "builder": "codex",
-    "package": "01_model_and_limitations",
+    "package": "04_engineering_report",
     "workflow_id": "c3d365745ae6",
-    "report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260906-004904-01_model_and_limitations-codex-report.md",
-    "report_sha256": "aba55903df96e2d4cb704675c21b9a85475bea40f07260b49672cb6766daff05",
+    "report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260908-000441-04_engineering_report-codex-report.md",
+    "report_sha256": "20fd4ab736a29614a2b3c831b12f8f11620e5dd55f2c0f7189930f4de6a61b3a",
     "revision": 1,
     "kind": "build"
   },
-  "tree_fingerprint": "26f7c0227453f1f2851c35ee7897ac909e05b24fb1876f0b9e11f4226cc01a00",
+  "tree_fingerprint": "3e30a09ee45fdf2d377656e32122fdadcd64b93cd5bd97a3af8d2b7c84d2c980",
   "revisions": [
     {
-      "package": "01_model_and_limitations",
+      "package": "04_engineering_report",
       "revision": 1,
       "author": "codex",
       "kind": "build",
-      "at": 1788646855.9640622
+      "at": 1788816481.6177282
+    }
+  ],
+  "role_transitions": [
+    {
+      "package": "02_field_units",
+      "from_builder": "codex",
+      "to_builder": "claude",
+      "reason": "codex unavailable (quota_exhausted); claude takes over as builder",
+      "at": 1788687510.3261995
+    },
+    {
+      "package": "02_field_units",
+      "from_builder": "claude",
+      "to_builder": "codex",
+      "reason": "preferred builder codex is available",
+      "at": 1788693966.9367764
+    },
+    {
+      "package": "02_field_units",
+      "from_builder": "codex",
+      "to_builder": "claude",
+      "reason": "preferred builder claude is available",
+      "at": 1788696807.3323603
+    },
+    {
+      "package": "02_field_units",
+      "from_builder": "claude",
+      "to_builder": "codex",
+      "reason": "preferred builder codex is available",
+      "at": 1788717793.4116943
+    },
+    {
+      "package": "02_field_units",
+      "from_builder": "codex",
+      "to_builder": "claude",
+      "reason": "preferred builder claude is available",
+      "at": 1788728997.6445315
+    },
+    {
+      "package": "02_field_units",
+      "from_builder": "codex",
+      "to_builder": "claude",
+      "reason": "preferred builder claude is available",
+      "at": 1788808385.8840787
+    },
+    {
+      "package": "02_field_units",
+      "from_builder": "claude",
+      "to_builder": "codex",
+      "reason": "preferred builder codex is available",
+      "at": 1788808485.8928094
+    },
+    {
+      "package": "03_case_save_load",
+      "from_builder": "codex",
+      "to_builder": "claude",
+      "reason": "preferred builder claude is available",
+      "at": 1788813570.9417365
+    },
+    {
+      "package": "03_case_save_load",
+      "from_builder": "claude",
+      "to_builder": "codex",
+      "reason": "preferred builder codex is available",
+      "at": 1788813625.186788
+    },
+    {
+      "package": "04_engineering_report",
+      "from_builder": "codex",
+      "to_builder": "claude",
+      "reason": "preferred builder claude is available",
+      "at": 1788862175.1038766
     }
   ],
-  "role_transitions": [],
   "history": [
     {
       "from": "IDLE",
@@ -536,6 +619,311 @@
       "from": "AUDIT_PENDING",
       "to": "CLAUDE_RUNNING",
       "reason": "invoking claude auditor"
+    },
+    {
+      "from": "CLAUDE_RUNNING",
+      "to": "APPROVED",
+      "reason": "independent audit approved"
+    },
+    {
+      "from": "APPROVED",
+      "to": "PLANNING",
+      "reason": "planning 02_field_units"
+    },
+    {
+      "from": "PLANNING",
+      "to": "CODEX_RUNNING",
+      "reason": "invoking codex builder"
+    },
+    {
+      "from": "CODEX_RUNNING",
+      "to": "CODEX_RUNNING",
+      "reason": "invoking claude builder"
+    },
+    {
+      "from": "CODEX_RUNNING",
+      "to": "HUMAN_ACTION_REQUIRED",
+      "reason": "claude output contract unusable: no <ORCHESTRATOR_RESULT> block found in agent output. Raw report preserved at C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\claude_builds\\20260906-123830-02_field_units-claude-report.md."
+    },
+    {
+      "from": "HUMAN_ACTION_REQUIRED",
+      "to": "PLANNING",
+      "reason": "external recovery shim: resuming the unfinished builder stage for 02_field_units against a preserved, fully passing working tree"
+    },
+    {
+      "from": "PLANNING",
+      "to": "PLANNING",
+      "reason": "external recovery shim: resuming the unfinished builder stage for 02_field_units against a preserved, fully passing working tree"
+    },
+    {
+      "from": "PLANNING",
+      "to": "PLANNING",
+      "reason": "planning 02_field_units"
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
+    },
+    {
+      "from": "CLAUDE_RUNNING",
+      "to": "CORRECTION_REQUIRED",
+      "reason": "audit verdict CONDITIONAL"
+    },
+    {
+      "from": "CORRECTION_REQUIRED",
+      "to": "CODEX_CORRECTION",
+      "reason": "correction cycle 1"
+    },
+    {
+      "from": "CODEX_CORRECTION",
+      "to": "HUMAN_ACTION_REQUIRED",
+      "reason": "claude correction contract unusable: no <ORCHESTRATOR_RESULT> block found in agent output"
+    },
+    {
+      "from": "HUMAN_ACTION_REQUIRED",
+      "to": "PLANNING",
+      "reason": "external recovery: Codex implements audit finding B-1 for 02_field_units against the restored post-Codex tree"
+    },
+    {
+      "from": "PLANNING",
+      "to": "PLANNING",
+      "reason": "planning 02_field_units"
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
+      "reason": "correction cycle 2"
+    },
+    {
+      "from": "CODEX_CORRECTION",
+      "to": "HUMAN_ACTION_REQUIRED",
+      "reason": "v1.2 role policy: Claude is a read-only reviewer for the remainder of this release and may not build or correct"
+    },
+    {
+      "from": "HUMAN_ACTION_REQUIRED",
+      "to": "PLANNING",
+      "reason": "external resume shim: 02_field_units build is complete and its evidence is intact; resuming into verification, independent audit and commit"
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
+    },
+    {
+      "from": "CLAUDE_RUNNING",
+      "to": "CORRECTION_REQUIRED",
+      "reason": "audit verdict CONDITIONAL"
+    },
+    {
+      "from": "CORRECTION_REQUIRED",
+      "to": "CODEX_CORRECTION",
+      "reason": "correction cycle 3"
+    },
+    {
+      "from": "CODEX_CORRECTION",
+      "to": "HUMAN_ACTION_REQUIRED",
+      "reason": "v1.2 role policy: Claude is a read-only reviewer and may not build or correct; preserve the work and wait for Codex"
+    },
+    {
+      "from": "HUMAN_ACTION_REQUIRED",
+      "to": "PLANNING",
+      "reason": "external correction shim: Codex authors the audit correction for 02_field_units; Claude remains the independent reviewer"
+    },
+    {
+      "from": "PLANNING",
+      "to": "PLANNING",
+      "reason": "planning 02_field_units"
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
+    },
+    {
+      "from": "CLAUDE_RUNNING",
+      "to": "APPROVED",
+      "reason": "independent audit approved"
+    },
+    {
+      "from": "APPROVED",
+      "to": "PLANNING",
+      "reason": "planning 03_case_save_load"
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
+    },
+    {
+      "from": "CLAUDE_RUNNING",
+      "to": "CORRECTION_REQUIRED",
+      "reason": "audit verdict CONDITIONAL"
+    },
+    {
+      "from": "CORRECTION_REQUIRED",
+      "to": "CODEX_CORRECTION",
+      "reason": "correction cycle 1"
+    },
+    {
+      "from": "CODEX_CORRECTION",
+      "to": "HUMAN_ACTION_REQUIRED",
+      "reason": "v1.2 role policy: Claude is a read-only reviewer and may not build or correct; preserve the work and wait for Codex"
+    },
+    {
+      "from": "HUMAN_ACTION_REQUIRED",
+      "to": "PLANNING",
+      "reason": "external correction shim: Codex authors the audit correction for 03_case_save_load; Claude remains the independent reviewer"
+    },
+    {
+      "from": "PLANNING",
+      "to": "PLANNING",
+      "reason": "planning 03_case_save_load"
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
+    },
+    {
+      "from": "CLAUDE_RUNNING",
+      "to": "APPROVED",
+      "reason": "independent audit approved"
+    },
+    {
+      "from": "APPROVED",
+      "to": "PLANNING",
+      "reason": "planning 04_engineering_report"
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
+      "reason": "v1.2 role policy: Claude is a read-only reviewer and may not build or correct; preserve the work and wait for Codex"
+    },
+    {
+      "from": "HUMAN_ACTION_REQUIRED",
+      "to": "PLANNING",
+      "reason": "external resume shim: 04_engineering_report build is complete and its evidence is intact; resuming into verification, independent audit and commit"
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
diff --git a/docs/STREAMLIT_APPLICATION.md b/docs/STREAMLIT_APPLICATION.md
index 0627863..89ae7f0 100644
--- a/docs/STREAMLIT_APPLICATION.md
+++ b/docs/STREAMLIT_APPLICATION.md
@@ -49,6 +49,9 @@ package:
   implementation for pressure and temperature unit conversion.
 - `src/pvt_phase_simulator_ui/state.py` associates each result with a scientific
   input signature.
+- `src/pvt_phase_simulator_ui/reports.py` renders printable HTML solely from the
+  existing result-export documents and repository-backed model scope. It has no
+  scientific API entry point.
 - `src/pvt_phase_simulator_ui/sweeps.py` chooses swept abscissae and calls the
   existing verified flash API once per point. It implements no thermodynamics.
 - `.streamlit/config.toml` supplies the light engineering theme. Narrow custom
@@ -124,7 +127,8 @@ are 1 Pa/Pa, 1,000,000 Pa/MPa, 100,000 Pa/bar, and 6,894.757293168 Pa/psi;
 temperature uses the standard 273.15 and 459.67 offsets.
 
 - **Overview:** entered state, phase and convergence statuses, available phase
-  fractions and Z factors, source-provided compositions, and envelope location.
+  fractions and Z factors, source-provided compositions, envelope location, and
+  a downloadable printable engineering case report.
 - **Phase Envelope:** independent bubble and dew traces using Module 21,
   status-aware unavailable points, terminations, critical overlay, and phase
   compositions when available.
@@ -168,6 +172,25 @@ states the engine units (K and Pa) and selected presentation units. CSV headers
 use explicit temperature and pressure unit columns and retain canonical
 `temperature_k` and `pressure_pa` columns for unambiguous downstream use.
 
+The Overview also offers `openphase-engineering-report.html`, a self-contained
+printable report with no added reporting framework or runtime dependency. It is
+assembled only from the current non-stale export documents already held in the
+session; creating or downloading it never starts or repeats a calculation. The
+report identifies the submitted case and generation time, states the application
+and report-format versions, and includes the calculation inputs, model and kij
+assumption, verified scope, flash and stability outcome, phase fractions,
+source-provided compositions, Z factors, available bubble/dew points, a certified
+critical point when present, an engineering-sweep summary, statuses, limitations,
+and repository-backed validation provenance.
+
+Every missing report quantity is labelled **UNAVAILABLE** or **NOT APPLICABLE**.
+Failed flash quantities and uncertified critical values are labelled **FAILED**
+and are not displayed as usable results. Envelope tables render values only for
+points whose stored status is `converged`; structured branch terminations remain
+visible. A sweep report gives the recorded requested, calculated, and failed
+counts without filling failed point values. CSV and JSON exports are independent
+and retain their existing schemas and serialization.
+
 Structured statuses such as `LINE_SEARCH_FAILED`, `JACOBIAN_FAILED`,
 `NOT_FOUND`, and `BRANCH_LOST` remain failures or information. Only
 `CriticalPointStatus.CONVERGED` is a certified critical point. `lambda_min=0`
diff --git a/src/pvt_phase_simulator_ui/views.py b/src/pvt_phase_simulator_ui/views.py
index 2b178c9..7b8d254 100644
--- a/src/pvt_phase_simulator_ui/views.py
+++ b/src/pvt_phase_simulator_ui/views.py
@@ -61,6 +61,7 @@ from pvt_phase_simulator_ui.exports import (
     export_sweep_csv_bytes,
 )
 from pvt_phase_simulator_ui.model_scope import ModelScope, load_model_scope
+from pvt_phase_simulator_ui.reports import export_engineering_report_html
 from pvt_phase_simulator_ui.state import (
     get_result,
     result_is_stale,
@@ -534,6 +535,9 @@ def render_overview(inputs: ScientificInputs | None) -> None:
         )
         if result_is_stale(session(), "critical", inputs):
             critical_export = None
+        sweep_export = cast(SweepResult | None, get_result(session(), "sweep"))
+        if result_is_stale(session(), "sweep", inputs):
+            sweep_export = None
         document = build_export_document(
             inputs,
             flash_result=None if flash_stale else result,
@@ -541,8 +545,27 @@ def render_overview(inputs: ScientificInputs | None) -> None:
             critical_result=critical_export,
             units=units,
         )
+        sweep_document = (
+            None
+            if sweep_export is None
+            else build_sweep_export_document(sweep_export, units)
+        )
         st.subheader("Export current case")
         with st.container(horizontal=True):
+            st.download_button(
+                "Download report",
+                data=export_engineering_report_html(
+                    document,
+                    scope=_model_scope(),
+                    sweep_document=sweep_document,
+                ),
+                file_name="openphase-engineering-report.html",
+                mime="text/html;charset=utf-8",
+                key="download_engineering_report",
+                on_click="ignore",
+                width="content",
+                icon=":material/description:",
+            )
             st.download_button(
                 "Download CSV",
                 data=export_csv_bytes(document),
diff --git a/tests/test_app_streamlit.py b/tests/test_app_streamlit.py
index 158a712..59c737b 100644
--- a/tests/test_app_streamlit.py
+++ b/tests/test_app_streamlit.py
@@ -146,7 +146,7 @@ def test_presentation_unit_change_does_not_stale_a_calculated_result() -> None:
     metrics = {metric.label: metric.value for metric in app.metric}
     assert metrics["Temperature"] == "26.85 °C"
     assert metrics["Pressure"] == "50 bar"
-    assert len(app.get("download_button")) == 3
+    assert len(app.get("download_button")) == 4
 
 
 @pytest.mark.parametrize(
@@ -199,7 +199,7 @@ def test_non_exact_unit_round_trip_preserves_result_identity(
     assert app.session_state["results"]["flash"] is result
     assert app.session_state["current_inputs"].signature == submitted.signature
     assert not any("Stale result" in message.value for message in app.warning)
-    assert len(app.get("download_button")) == 3
+    assert len(app.get("download_button")) == 4
 
     app.number_input[3].set_value(displayed_temperature + 1.0e-9)
     app.run()
@@ -355,8 +355,14 @@ def test_valid_single_phase_uses_information_semantics_and_offers_exports() -> N
     )
     downloads = app.get("download_button")
     downloads_by_label = {button.label: button for button in downloads}
-    assert set(downloads_by_label) == {"Save case", "Download CSV", "Download JSON"}
+    assert set(downloads_by_label) == {
+        "Save case",
+        "Download report",
+        "Download CSV",
+        "Download JSON",
+    }
     assert downloads_by_label["Save case"].key == "save_openphase_case"
+    assert downloads_by_label["Download report"].key == "download_engineering_report"
     assert downloads_by_label["Download CSV"].key == "download_current_case_csv"
     assert downloads_by_label["Download JSON"].key == "download_current_case_json"
 
@@ -403,13 +409,23 @@ def test_download_widgets_receive_real_payloads_and_mime_metadata(
     _button(app, "RUN FLASH").click().run()
 
     assert not app.exception
-    assert set(captured) == {"Save case", "Download CSV", "Download JSON"}
+    assert set(captured) == {
+        "Save case",
+        "Download report",
+        "Download CSV",
+        "Download JSON",
+    }
     saved_case = captured["Save case"]
     assert saved_case["file_name"] == "openphase-case.json"
     assert saved_case["mime"] == "application/json"
     assert json.loads(saved_case["data"])["schema_version"] == "1.0.0"
     csv_download = captured["Download CSV"]
     json_download = captured["Download JSON"]
+    report_download = captured["Download report"]
+    assert report_download["file_name"] == "openphase-engineering-report.html"
+    assert report_download["mime"] == "text/html;charset=utf-8"
+    assert isinstance(report_download["data"], bytes)
+    assert b"<!doctype html>" in report_download["data"]
     assert csv_download["file_name"] == "pvt-current-case.csv"
     assert csv_download["mime"] == "text/csv;charset=utf-8"
     assert json_download["file_name"] == "pvt-current-case.json"
@@ -438,7 +454,7 @@ def test_changed_inputs_keep_result_visible_but_stale_and_disable_exports() -> N
     app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
     _button(app, "RUN FLASH").click().run()
     original = app.session_state["results"]["flash"]
-    assert len(app.get("download_button")) == 3
+    assert len(app.get("download_button")) == 4
 
     app.selectbox[0].select("Known single-phase case at 300 K and 20 MPa").run()
 

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
