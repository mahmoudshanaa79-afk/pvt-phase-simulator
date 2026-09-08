# Independent audit: 03_case_save_load

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
- Name: 03_case_save_load
- Declared risk: MEDIUM
- Objective: Let a user save a complete, reproducible OpenPhase case to a file and load it back later, restoring the same valid application inputs. Reproducibility is the entire point of this package.

SAVED CONTENT. The case must capture all input state needed to reproduce the run, as applicable: selected components; mole fractions; temperature; pressure; the presentation unit selections (pressure Pa/MPa/bar/psi and temperature K/degC/degF); sweep settings; any other relevant calculation inputs; and an explicit schema/version identifier.

FORMAT. Deterministic JSON: the same case must serialise to the same bytes, with stable key ordering. The schema version is explicit and written into the file.

LOADING. Validate the entire file BEFORE any scientific call is made. No calculation may run against unvalidated input. Malformed JSON, an invalid schema, an unknown or future schema version, and an invalid composition must each produce a clear, specific, user-facing error message - never a raw traceback. Never silently invent a missing value, and never silently normalise or repair an invalid composition: a composition that does not total 100 mol % must fail exactly the way typing it by hand fails. Unknown or future schema versions are refused, not guessed at.

SAFETY. Use only safe deserialisation - plain JSON parsing. Do not use pickle, eval, or any mechanism that can execute content from the file.

SCOPE. Restoring inputs only. The scientific engine is frozen and must not change, and no thermodynamic relation may be implemented or restated in the application layer.

TESTS. Cover: round-trip save/load; malformed JSON; invalid schema; unsupported/future version; invalid composition; unit selections surviving the round trip; sweep inputs surviving where applicable; and that loading does not execute any science before validation. Avoid brittle hard-coded one-ULP float strings.

BUILD-TIME TESTING POLICY. Run only focused tests for the files and behaviour you changed, plus Ruff and mypy if useful. Do NOT run the whole pytest suite for reassurance - the orchestrator runs the authoritative full-suite verification after you finish, and duplicating it wastes a great deal of wall-clock time.

## Scientific invariants claimed to hold
  - The scientific engine is frozen: no file under src/pvt_phase_simulator/, data/, docs/validation/ or tests/golden_master/ may change.
  - No thermodynamic relation may be implemented, restated or approximated in the application layer.
  - Unavailable quantities are reported as unavailable and never fabricated or interpolated.
  - Structured failures remain failures; only CriticalPointStatus.CONVERGED is a certified critical point.

## Repository state
- Branch: `app-v1.2-engineering`
- HEAD: `ccebd61e51351fa9072682ad696765deb015b839`
- Base for this change: `ccebd61e51351fa9072682ad696765deb015b839`

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
Changed files: ['docs/STREAMLIT_APPLICATION.md', 'src/pvt_phase_simulator_ui/__init__.py', 'src/pvt_phase_simulator_ui/app.py', 'src/pvt_phase_simulator_ui/case_files.py', 'src/pvt_phase_simulator_ui/state.py', 'src/pvt_phase_simulator_ui/views.py', 'tests/test_app_case_files.py', 'tests/test_app_streamlit.py']

## Builder's own report — treat as an unverified claim
```
Implemented deterministic, versioned OpenPhase case save/load.

- Saves all scientific inputs, presentation units, and both sweep configurations.
- Strictly validates JSON/schema/version/composition before mutating state.
- Loading never runs scientific calculations or restores cached results.
- Added focused persistence and Streamlit regression coverage.
- Protected artifacts retain their required hashes.
- No Streamlit server is currently running.

Focused tests: 136 passed. Ruff, formatting, mypy, and compileall all passed. The full suite was intentionally left to the orchestrator per build-time policy.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "Focused pytest: 136 passed (tests/test_app_case_files.py, tests/test_app_streamlit.py, tests/test_app_sweeps.py, tests/test_app_adapters.py, tests/test_app_release.py); Ruff check passed; Ruff format check passed; mypy src app passed; compileall src app passed.",
  "files_changed": ["docs/STREAMLIT_APPLICATION.md", "src/pvt_phase_simulator_ui/__init__.py", "src/pvt_phase_simulator_ui/app.py", "src/pvt_phase_simulator_ui/case_files.py", "src/pvt_phase_simulator_ui/state.py", "src/pvt_phase_simulator_ui/views.py", "tests/test_app_case_files.py", "tests/test_app_streamlit.py"],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>
```

## Diff stat
```
 .ai/work_packages/01_model_and_limitations.json |   2 +-
 .ai/work_packages/02_field_units.json           |   2 +-
 .ai/work_packages/03_case_save_load.json        |   2 +-
 .ai/work_packages/04_engineering_report.json    |   2 +-
 .ai/work_packages/05_v1_2_release_qa.json       |   2 +-
 .ai/workflow_state.json                         | 293 ++++++++++++++++++++++--
 docs/STREAMLIT_APPLICATION.md                   |  24 ++
 src/pvt_phase_simulator_ui/__init__.py          |  18 ++
 src/pvt_phase_simulator_ui/app.py               |  69 ++++++
 src/pvt_phase_simulator_ui/state.py             |  90 ++++++++
 src/pvt_phase_simulator_ui/views.py             |  24 +-
 tests/test_app_streamlit.py                     |  54 +++--
 12 files changed, 527 insertions(+), 55 deletions(-)

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
index 6b410ca..4403681 100644
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
index a6e5b0a..a8eb84d 100644
--- a/.ai/workflow_state.json
+++ b/.ai/workflow_state.json
@@ -3,19 +3,25 @@
   "phase": "post-v1.0-extensions",
   "workflow_status": "CLAUDE_RUNNING",
   "last_scientific_commit": "d2a0a74",
-  "last_independent_audit_commit": "c29ae4961543e74a271e8e2e54de22852892cf00",
+  "last_independent_audit_commit": "ccebd61e51351fa9072682ad696765deb015b839",
   "work_packages_since_audit": 0,
-  "current_work_package": "01_model_and_limitations",
-  "current_risk": "LOW",
-  "audit_required": false,
-  "audit_reason": null,
+  "current_work_package": "03_case_save_load",
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
+      "summary": "_presentation_figure's hovertemplate unit-label substitution uses a literal string .replace(\" K\", ...).replace(\" Pa\", ...) rather than a structured template; currently safe because every call into the frozen plotting module forces pressure_unit=PlotPressureUnit.PA so hovertemplates always contain exactly one \" K\" and one \" Pa\" token, but fragile against a future wording change in that frozen module."
+    },
+    {
+      "id": "D-2",
+      "severity": "D",
+      "blocks": false,
+      "summary": "Sweep CSV/table pressure and temperature values are not rounded to a unit-appropriate precision (fine for Pa/K, excessive digits for bar/psi/\u00b0C); cosmetic only."
     }
   ],
   "deferred_independent_audits": [
@@ -61,31 +67,81 @@
   "workflow_id": "c3d365745ae6",
   "builder": "codex",
   "reviewer": "claude",
-  "last_completed_stage": "audited",
+  "last_completed_stage": "verified",
   "verification_status": "passed",
-  "base_commit": "46b1d8e75c60d76b5e7d920ef30f6c1f14da051d",
+  "base_commit": "ccebd61e51351fa9072682ad696765deb015b839",
   "resulting_commit": null,
-  "builder_report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260906-004904-01_model_and_limitations-codex-report.md",
+  "builder_report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260907-225501-03_case_save_load-codex-report.md",
   "builder_evidence": {
     "builder": "codex",
-    "package": "01_model_and_limitations",
+    "package": "03_case_save_load",
     "workflow_id": "c3d365745ae6",
-    "report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260906-004904-01_model_and_limitations-codex-report.md",
-    "report_sha256": "aba55903df96e2d4cb704675c21b9a85475bea40f07260b49672cb6766daff05",
+    "report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260907-225501-03_case_save_load-codex-report.md",
+    "report_sha256": "cbb474bacdcadbb3793ed2186a120c58b72eaad5a60e06031dd2d31614a480bc",
     "revision": 1,
     "kind": "build"
   },
-  "tree_fingerprint": "26f7c0227453f1f2851c35ee7897ac909e05b24fb1876f0b9e11f4226cc01a00",
+  "tree_fingerprint": "cacf74882e04803a4b982e61e7cf4f994a13f384a6c18a6fdf0f334b1bfb6cfe",
   "revisions": [
     {
-      "package": "01_model_and_limitations",
+      "package": "03_case_save_load",
       "revision": 1,
       "author": "codex",
       "kind": "build",
-      "at": 1788646855.9640622
+      "at": 1788812582.609157
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
     }
   ],
-  "role_transitions": [],
   "history": [
     {
       "from": "IDLE",
@@ -536,6 +592,211 @@
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
     }
   ]
 }
diff --git a/docs/STREAMLIT_APPLICATION.md b/docs/STREAMLIT_APPLICATION.md
index 73647c2..0627863 100644
--- a/docs/STREAMLIT_APPLICATION.md
+++ b/docs/STREAMLIT_APPLICATION.md
@@ -40,6 +40,8 @@ package:
 
 - `streamlit_app.py` is the thin, stable root entrypoint.
 - `src/pvt_phase_simulator_ui/app.py` owns navigation and submitted inputs.
+- `src/pvt_phase_simulator_ui/case_files.py` owns the versioned, deterministic
+  JSON case-file boundary and restores validated inputs only.
 - `src/pvt_phase_simulator_ui/pages/` contains the six page scripts.
 - `src/pvt_phase_simulator_ui/adapters.py` validates inputs, converts boundary
   units to K and Pa, and selects public result fields without changing them.
@@ -93,6 +95,25 @@ values only; it never submits the form or starts a scientific calculation. Every
 populated value remains editable and passes through the same validation and
 conversion boundary when the user explicitly submits it.
 
+The sidebar **Save or load case** panel persists a complete reproducible input
+case as `openphase-case.json`. A case records the explicit `openphase.case`
+schema identifier and schema version `1.0.0`; the named component mol
+percentages; canonical temperature in K and pressure in Pa; selected
+temperature and pressure presentation units; the active engineering sweep; and
+the canonical bounds and point counts for both pressure and temperature sweeps.
+JSON output is UTF-8 with sorted object keys and compact separators, so an
+unchanged case serializes to the same bytes.
+
+Loading uses only the standard JSON parser. The complete document is checked
+before session input state changes: object shape, required and unknown fields,
+duplicate keys, schema identifier, exact supported version, component names,
+units, scientific inputs, composition total, and both sweep definitions. A
+malformed document, invalid schema, unsupported or future version, or invalid
+composition produces a specific application error. Invalid composition is
+never normalized or repaired. A successful load restores inputs without
+running flash, envelope, critical-point, criticality, or sweep calculations;
+the user must still explicitly submit or run the desired calculation.
+
 Valid composition is divided by 100 exactly for mole fractions. The selected
 temperature and pressure units are converted once to K and Pa at submission.
 Only the canonical K/Pa state is passed to the scientific APIs and stored in a
@@ -139,6 +160,9 @@ invalid current input marks the prior result stale until explicitly recalculated
 Stale results remain visible with a warning, but downloads are unavailable until
 the changed inputs have a current calculated result.
 
+Case files are distinct from result exports: they contain reproducible inputs
+only and do not serialize cached scientific result objects.
+
 Current-case and sweep JSON exports use schema version 1.1.0. Their metadata
 states the engine units (K and Pa) and selected presentation units. CSV headers
 use explicit temperature and pressure unit columns and retain canonical
diff --git a/src/pvt_phase_simulator_ui/__init__.py b/src/pvt_phase_simulator_ui/__init__.py
index 4d56513..44170c8 100644
--- a/src/pvt_phase_simulator_ui/__init__.py
+++ b/src/pvt_phase_simulator_ui/__init__.py
@@ -5,9 +5,27 @@ from pvt_phase_simulator_ui.adapters import (
     ScientificInputs,
     validate_scientific_inputs,
 )
+from pvt_phase_simulator_ui.case_files import (
+    CASE_SCHEMA,
+    CASE_SCHEMA_VERSION,
+    CaseFileError,
+    OpenPhaseCase,
+    apply_case_to_state,
+    case_from_state,
+    load_case,
+    serialize_case,
+)
 
 __all__ = [
+    "CASE_SCHEMA",
+    "CASE_SCHEMA_VERSION",
+    "CaseFileError",
     "InputValidationError",
+    "OpenPhaseCase",
     "ScientificInputs",
+    "apply_case_to_state",
+    "case_from_state",
+    "load_case",
+    "serialize_case",
     "validate_scientific_inputs",
 ]
diff --git a/src/pvt_phase_simulator_ui/app.py b/src/pvt_phase_simulator_ui/app.py
index d77d566..050cd85 100644
--- a/src/pvt_phase_simulator_ui/app.py
+++ b/src/pvt_phase_simulator_ui/app.py
@@ -2,7 +2,9 @@
 
 from __future__ import annotations
 
+from collections.abc import MutableMapping
 from pathlib import Path
+from typing import Any
 
 import streamlit as st
 
@@ -13,6 +15,14 @@ from pvt_phase_simulator_ui.adapters import (
     composition_total,
     validate_scientific_inputs,
 )
+from pvt_phase_simulator_ui.case_files import (
+    CaseFileError,
+    OpenPhaseCase,
+    apply_case_to_state,
+    case_from_state,
+    load_case,
+    serialize_case,
+)
 from pvt_phase_simulator_ui.context import session
 from pvt_phase_simulator_ui.state import (
     INPUT_EXAMPLES,
@@ -42,8 +52,67 @@ def _cached_flash(inputs: ScientificInputs) -> object:
     )
 
 
+def _load_case_inputs(
+    data: bytes | str, state: MutableMapping[str, Any]
+) -> OpenPhaseCase:
+    """Validate a complete file before atomically restoring input state."""
+
+    case = load_case(data)
+    apply_case_to_state(case, state)
+    return case
+
+
+def _case_controls() -> None:
+    """Render input-only case persistence without submitting a calculation."""
+
+    with st.expander("Save or load case"):
+        st.caption(
+            "Cases are versioned JSON inputs only. Loading validates the entire "
+            "file and never runs a calculation."
+        )
+        uploaded = st.file_uploader(
+            "OpenPhase case file",
+            type="json",
+            max_upload_size=1,
+            key="openphase_case_file",
+        )
+        load_requested = st.button(
+            "Load case",
+            disabled=uploaded is None,
+            key="load_openphase_case",
+            icon=":material/upload_file:",
+        )
+        if load_requested and uploaded is not None:
+            try:
+                _load_case_inputs(uploaded.getvalue(), session())
+            except CaseFileError as error:
+                st.error(f"Case load unavailable: {error}")
+            else:
+                st.success("Case loaded. Inputs restored; no calculation was run.")
+
+        try:
+            payload = serialize_case(case_from_state(session()))
+        except CaseFileError as error:
+            st.caption(f"Save unavailable until all case inputs are valid: {error}")
+        else:
+            st.download_button(
+                "Save case",
+                data=payload,
+                file_name="openphase-case.json",
+                mime="application/json",
+                key="save_openphase_case",
+                on_click="ignore",
+                width="content",
+                icon=":material/download:",
+            )
+
+
 def _input_form() -> tuple[ScientificInputs | None, bool]:
     with st.sidebar:
+        # Capture any field edits from the prior browser event before building
+        # the downloadable case, and before any load can replace widget state.
+        synchronize_unit_inputs(session())
+        _case_controls()
         st.subheader("Fluid inputs")
         st.caption("Display and entry units")
         st.segmented_control(
diff --git a/src/pvt_phase_simulator_ui/state.py b/src/pvt_phase_simulator_ui/state.py
index 92b0c46..425eb15 100644
--- a/src/pvt_phase_simulator_ui/state.py
+++ b/src/pvt_phase_simulator_ui/state.py
@@ -65,6 +65,9 @@ INPUT_EXAMPLES: Final = (
 )
 
 _DEFAULT_INPUTS: Final = INPUT_EXAMPLES[0]
+_DEFAULT_PRESSURE_SWEEP_PA: Final = (1.0e6, 20.0e6)
+_DEFAULT_TEMPERATURE_SWEEP_K: Final = (240.0, 340.0)
+_DEFAULT_SWEEP_POINTS: Final = 21
 
 
 def initialize_session(state: MutableMapping[str, Any]) -> None:
@@ -88,6 +91,92 @@ def initialize_session(state: MutableMapping[str, Any]) -> None:
     state.setdefault("pressure_value", _DEFAULT_INPUTS.pressure_mpa)
     state.setdefault("rendered_temperature_value", state["temperature_value"])
     state.setdefault("rendered_pressure_value", state["pressure_value"])
+    state.setdefault("sweep_kind", "pressure")
+    state.setdefault("sweep_pressure_start_pa", _DEFAULT_PRESSURE_SWEEP_PA[0])
+    state.setdefault("sweep_pressure_end_pa", _DEFAULT_PRESSURE_SWEEP_PA[1])
+    state.setdefault("sweep_points_pressure", _DEFAULT_SWEEP_POINTS)
+    state.setdefault("sweep_temperature_start_k", _DEFAULT_TEMPERATURE_SWEEP_K[0])
+    state.setdefault("sweep_temperature_end_k", _DEFAULT_TEMPERATURE_SWEEP_K[1])
+    state.setdefault("sweep_points_temperature", _DEFAULT_SWEEP_POINTS)
+    state.setdefault(
+        "sweep_start_value",
+        pressure_from_pa(
+            _DEFAULT_PRESSURE_SWEEP_PA[0], PressureUnit(str(state["pressure_unit"]))
+        ),
+    )
+    state.setdefault(
+        "sweep_end_value",
+        pressure_from_pa(
+            _DEFAULT_PRESSURE_SWEEP_PA[1], PressureUnit(str(state["pressure_unit"]))
+        ),
+    )
+    state.setdefault("sweep_points_value", _DEFAULT_SWEEP_POINTS)
+    state.setdefault("rendered_sweep_kind", state["sweep_kind"])
+    state.setdefault("rendered_sweep_temperature_unit", state["temperature_unit"])
+    state.setdefault("rendered_sweep_pressure_unit", state["pressure_unit"])
+    state.setdefault("rendered_sweep_start_value", state["sweep_start_value"])
+    state.setdefault("rendered_sweep_end_value", state["sweep_end_value"])
+    state.setdefault("rendered_sweep_points_value", state["sweep_points_value"])
+
+
+def synchronize_sweep_inputs(state: MutableMapping[str, Any]) -> None:
+    """Preserve both sweep definitions across kind and presentation changes."""
+
+    initialize_session(state)
+    old_kind = str(state["rendered_sweep_kind"])
+    old_temperature_unit = TemperatureUnit(
+        str(state["rendered_sweep_temperature_unit"])
+    )
+    old_pressure_unit = PressureUnit(str(state["rendered_sweep_pressure_unit"]))
+
+    start = float(state["sweep_start_value"])
+    end = float(state["sweep_end_value"])
+    points = state["sweep_points_value"]
+    if isfinite(start) and isfinite(end):
+        if old_kind == "pressure":
+            state["sweep_pressure_start_pa"] = pressure_to_pa(start, old_pressure_unit)
+            state["sweep_pressure_end_pa"] = pressure_to_pa(end, old_pressure_unit)
+        elif old_kind == "temperature":
+            state["sweep_temperature_start_k"] = temperature_to_k(
+                start, old_temperature_unit
+            )
+            state["sweep_temperature_end_k"] = temperature_to_k(
+                end, old_temperature_unit
+            )
+    if isinstance(points, int) and not isinstance(points, bool):
+        state[f"sweep_points_{old_kind}"] = points
+
+    new_kind = str(state["sweep_kind"])
+    new_temperature_unit = TemperatureUnit(str(state["temperature_unit"]))
+    new_pressure_unit = PressureUnit(str(state["pressure_unit"]))
+    presentation_changed = (
+        old_kind != new_kind
+        or old_temperature_unit is not new_temperature_unit
+        or old_pressure_unit is not new_pressure_unit
+    )
+    if presentation_changed:
+        if new_kind == "pressure":
+            state["sweep_start_value"] = pressure_from_pa(
+                float(state["sweep_pressure_start_pa"]), new_pressure_unit
+            )
+            state["sweep_end_value"] = pressure_from_pa(
+                float(state["sweep_pressure_end_pa"]), new_pressure_unit
+            )
+        elif new_kind == "temperature":
+            state["sweep_start_value"] = temperature_from_k(
+                float(state["sweep_temperature_start_k"]), new_temperature_unit
+            )
+            state["sweep_end_value"] = temperature_from_k(
+                float(state["sweep_temperature_end_k"]), new_temperature_unit
+            )
+        state["sweep_points_value"] = state[f"sweep_points_{new_kind}"]
+
+    state["rendered_sweep_kind"] = new_kind
+    state["rendered_sweep_temperature_unit"] = new_temperature_unit.value
+    state["rendered_sweep_pressure_unit"] = new_pressure_unit.value
+    state["rendered_sweep_start_value"] = state["sweep_start_value"]
+    state["rendered_sweep_end_value"] = state["sweep_end_value"]
+    state["rendered_sweep_points_value"] = state["sweep_points_value"]
 
 
 def synchronize_unit_inputs(state: MutableMapping[str, Any]) -> None:
@@ -127,6 +216,7 @@ def synchronize_unit_inputs(state: MutableMapping[str, Any]) -> None:
     state["pressure_mpa"] = pressure_from_pa(
         float(state["pressure_pa"]), PressureUnit.MPA
     )
+    synchronize_sweep_inputs(state)
 
 
 def apply_selected_input_example(state: MutableMapping[str, Any]) -> None:
diff --git a/src/pvt_phase_simulator_ui/views.py b/src/pvt_phase_simulator_ui/views.py
index 6d3d5bc..2b178c9 100644
--- a/src/pvt_phase_simulator_ui/views.py
+++ b/src/pvt_phase_simulator_ui/views.py
@@ -61,7 +61,12 @@ from pvt_phase_simulator_ui.exports import (
     export_sweep_csv_bytes,
 )
 from pvt_phase_simulator_ui.model_scope import ModelScope, load_model_scope
-from pvt_phase_simulator_ui.state import get_result, result_is_stale, store_result
+from pvt_phase_simulator_ui.state import (
+    get_result,
+    result_is_stale,
+    store_result,
+    synchronize_sweep_inputs,
+)
 from pvt_phase_simulator_ui.styles import phase_split_bar
 from pvt_phase_simulator_ui.sweeps import (
     DEFAULT_SWEEP_POINTS,
@@ -1287,14 +1292,16 @@ def _sweep_controls(
 ) -> tuple[SweepKind, float, float, int]:
     """Collect sweep bounds; the fixed variable comes from the submitted case."""
 
+    synchronize_sweep_inputs(session())
     kind = cast(
         SweepKind,
         st.segmented_control(
             "Swept variable",
             options=["pressure", "temperature"],
-            default="pressure",
             format_func=lambda value: value.capitalize(),
             key="sweep_kind",
+            on_change=synchronize_sweep_inputs,
+            args=(session(),),
         )
         or "pressure",
     )
@@ -1304,8 +1311,6 @@ def _sweep_controls(
             f"{_display_temperature(inputs.temperature_k, units):g} "
             f"{units.temperature.value}."
         )
-        default_start = _display_pressure(1.0e6, units)
-        default_end = _display_pressure(20.0e6, units)
         label_start = f"Start pressure ({units.pressure.value})"
         label_end = f"End pressure ({units.pressure.value})"
     else:
@@ -1314,31 +1319,26 @@ def _sweep_controls(
             f"{_display_pressure(inputs.pressure_pa, units):g} "
             f"{units.pressure.value}."
         )
-        default_start = _display_temperature(240.0, units)
-        default_end = _display_temperature(340.0, units)
         label_start = f"Start temperature ({units.temperature.value})"
         label_end = f"End temperature ({units.temperature.value})"
 
     with st.container(horizontal=True):
         start = st.number_input(
             label_start,
-            value=default_start,
             step=1.0,
-            key=f"sweep_start_{kind}_{units.temperature}_{units.pressure}",
+            key="sweep_start_value",
         )
         end = st.number_input(
             label_end,
-            value=default_end,
             step=1.0,
-            key=f"sweep_end_{kind}_{units.temperature}_{units.pressure}",
+            key="sweep_end_value",
         )
         points = st.number_input(
             "Points",
             min_value=MIN_SWEEP_POINTS,
             max_value=MAX_SWEEP_POINTS,
-            value=DEFAULT_SWEEP_POINTS,
             step=1,
-            key=f"sweep_points_{kind}",
+            key="sweep_points_value",
         )
     return kind, float(start), float(end), int(points)
 
diff --git a/tests/test_app_streamlit.py b/tests/test_app_streamlit.py
index 7ed3767..ee3cecc 100644
--- a/tests/test_app_streamlit.py
+++ b/tests/test_app_streamlit.py
@@ -34,6 +34,10 @@ from pvt_phase_simulator_ui.units import (
 ROOT = Path(__file__).resolve().parents[1]
 
 
+def _button(app: AppTest, label: str) -> object:
+    return next(button for button in app.button if button.label == label)
+
+
 def test_ui_and_styles_are_installed_packages() -> None:
     package_path = Path(pvt_phase_simulator_ui.__file__).resolve()
     styles_path = Path(pvt_phase_simulator_ui.styles.__file__).resolve()
@@ -80,7 +84,9 @@ def test_streamlit_apptest_starts_and_exposes_explicit_form_boundary() -> None:
         "Temperature (K)",
         "Pressure (MPa)",
     ]
-    assert [button.label for button in app.button] == ["RUN FLASH"]
+    assert [button.label for button in app.button] == ["Load case", "RUN FLASH"]
+    assert app.button[0].disabled
+    assert [button.label for button in app.get("download_button")] == ["Save case"]
 
 
 def test_field_unit_selection_preserves_state_and_submits_si_to_engine() -> None:
@@ -94,7 +100,7 @@ def test_field_unit_selection_preserves_state_and_submits_si_to_engine() -> None
     assert fields["Temperature (°F)"] == pytest.approx(80.33)
     assert fields["Pressure (psi)"] == pytest.approx(725.1886886510841)
 
-    app.button[0].click().run()
+    _button(app, "RUN FLASH").click().run()
     submitted = app.session_state["submitted_inputs"]
     assert submitted.temperature_k == pytest.approx(300.0, abs=1e-13)
     assert submitted.pressure_pa == 5_000_000.0
@@ -108,7 +114,7 @@ def test_field_unit_selection_preserves_state_and_submits_si_to_engine() -> None
 
 def test_presentation_unit_change_does_not_stale_a_calculated_result() -> None:
     app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
-    app.button[0].click().run()
+    _button(app, "RUN FLASH").click().run()
     result = app.session_state["results"]["flash"]
 
     app.segmented_control[0].set_value("°C")
@@ -120,7 +126,7 @@ def test_presentation_unit_change_does_not_stale_a_calculated_result() -> None:
     metrics = {metric.label: metric.value for metric in app.metric}
     assert metrics["Temperature"] == "26.85 °C"
     assert metrics["Pressure"] == "50 bar"
-    assert len(app.get("download_button")) == 2
+    assert len(app.get("download_button")) == 3
 
 
 @pytest.mark.parametrize(
@@ -149,7 +155,7 @@ def test_non_exact_unit_round_trip_preserves_result_identity(
     app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
     app.number_input[3].set_value(temperature_k)
     app.number_input[4].set_value(pressure_mpa)
-    app.button[0].click().run()
+    _button(app, "RUN FLASH").click().run()
     result = app.session_state["results"]["flash"]
     submitted = app.session_state["submitted_inputs"]
 
@@ -173,13 +179,13 @@ def test_non_exact_unit_round_trip_preserves_result_identity(
     assert app.session_state["results"]["flash"] is result
     assert app.session_state["current_inputs"].signature == submitted.signature
     assert not any("Stale result" in message.value for message in app.warning)
-    assert len(app.get("download_button")) == 2
+    assert len(app.get("download_button")) == 3
 
     app.number_input[3].set_value(displayed_temperature + 1.0e-9)
     app.run()
 
     assert any("Stale result" in message.value for message in app.warning)
-    assert app.get("download_button") == []
+    assert [button.label for button in app.get("download_button")] == ["Save case"]
 
 
 def test_overview_exposes_repository_backed_model_and_limitations_panel() -> None:
@@ -246,7 +252,7 @@ def test_custom_edits_after_example_selection_validate_and_submit_normally() ->
     app.number_input[0].set_value(49.0)
     app.number_input[1].set_value(1.0)
     app.number_input[3].set_value(301.25)
-    app.button[0].click().run()
+    _button(app, "RUN FLASH").click().run()
 
     assert not app.exception
     submitted = app.session_state["submitted_inputs"]
@@ -277,14 +283,14 @@ def test_every_navigation_page_renders_without_hidden_calculation() -> None:
 def test_invalid_form_submission_never_creates_a_flash_result() -> None:
     app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
     app.number_input[0].set_value(40.0)
-    app.button[0].click().run()
+    _button(app, "RUN FLASH").click().run()
     assert "flash" not in app.session_state["results"]
     assert any("Submission unavailable" in error.value for error in app.error)
 
 
 def test_valid_two_phase_submission_preserves_science_and_success_semantics() -> None:
     app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
-    app.button[0].click().run()
+    _button(app, "RUN FLASH").click().run()
 
     assert not app.exception
     result = app.session_state["results"]["flash"]
@@ -312,7 +318,7 @@ def test_valid_two_phase_submission_preserves_science_and_success_semantics() ->
 def test_valid_single_phase_uses_information_semantics_and_offers_exports() -> None:
     app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
     app.number_input[4].set_value(20.0)
-    app.button[0].click().run()
+    _button(app, "RUN FLASH").click().run()
 
     assert not app.exception
     result = app.session_state["results"]["flash"]
@@ -328,11 +334,11 @@ def test_valid_single_phase_uses_information_semantics_and_offers_exports() -> N
         for info in app.info
     )
     downloads = app.get("download_button")
-    assert [button.label for button in downloads] == ["Download CSV", "Download JSON"]
-    assert [button.key for button in downloads] == [
-        "download_current_case_csv",
-        "download_current_case_json",
-    ]
+    downloads_by_label = {button.label: button for button in downloads}
+    assert set(downloads_by_label) == {"Save case", "Download CSV", "Download JSON"}
+    assert downloads_by_label["Save case"].key == "save_openphase_case"
+    assert downloads_by_label["Download CSV"].key == "download_current_case_csv"
+    assert downloads_by_label["Download JSON"].key == "download_current_case_json"
 
 
 def test_structured_flash_failure_is_presented_as_an_error(
@@ -347,7 +353,7 @@ def test_structured_flash_failure_is_presented_as_an_error(
     monkeypatch.setattr(ui_app, "_cached_flash", lambda _inputs: failure)
 
     app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
-    app.button[0].click().run()
+    _button(app, "RUN FLASH").click().run()
 
     assert not app.exception
     stored = app.session_state["results"]["flash"]
@@ -374,10 +380,14 @@ def test_download_widgets_receive_real_payloads_and_mime_metadata(
     monkeypatch.setattr(views.st, "download_button", capture_download)
     app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
     app.number_input[4].set_value(20.0)
-    app.button[0].click().run()
+    _button(app, "RUN FLASH").click().run()
 
     assert not app.exception
-    assert set(captured) == {"Download CSV", "Download JSON"}
+    assert set(captured) == {"Save case", "Download CSV", "Download JSON"}
+    saved_case = captured["Save case"]
+    assert saved_case["file_name"] == "openphase-case.json"
+    assert saved_case["mime"] == "application/json"
+    assert json.loads(saved_case["data"])["schema_version"] == "1.0.0"
     csv_download = captured["Download CSV"]
     json_download = captured["Download JSON"]
     assert csv_download["file_name"] == "pvt-current-case.csv"
@@ -406,9 +416,9 @@ def test_download_widgets_receive_real_payloads_and_mime_metadata(
 
 def test_changed_inputs_keep_result_visible_but_stale_and_disable_exports() -> None:
     app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
-    app.button[0].click().run()
+    _button(app, "RUN FLASH").click().run()
     original = app.session_state["results"]["flash"]
-    assert len(app.get("download_button")) == 2
+    assert len(app.get("download_button")) == 3
 
     app.selectbox[0].select("Known single-phase case at 300 K and 20 MPa").run()
 
@@ -417,7 +427,7 @@ def test_changed_inputs_keep_result_visible_but_stale_and_disable_exports() -> N
     assert app.session_state["submitted_inputs"].pressure_mpa == 5.0
     assert app.number_input[4].value == 20.0
     assert any("Stale result" in message.value for message in app.warning)
-    assert app.get("download_button") == []
+    assert [button.label for button in app.get("download_button")] == ["Save case"]
     assert any(
         "Downloads are unavailable until RUN FLASH recalculates" in caption.value
         for caption in app.caption

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
