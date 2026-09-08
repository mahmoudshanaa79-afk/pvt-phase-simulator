# Independent audit: 05_v1_2_release_qa

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
- Name: 05_v1_2_release_qa
- Declared risk: LOW
- Objective: Final application-level verification of the complete v1.2 product. This package adds NO capability; its job is to test the actual product and close the gaps it finds. No feature creep.

USER JOURNEY to exercise end to end: home/first use; fluid setup; examples; single-state analysis; flash; bubble and dew; phase envelope; engineering sweeps; field units; save and load; exports; the engineering report; the science/methodology pages; and limitations/validation.

VERIFY: a new user can run a meaningful example; input errors are reported in normal language; no raw traceback is ever exposed to an ordinary user; units are obvious and consistent; non-SI presentation never alters internal science; stale-result protection works and a changed input can never display an obsolete result as current; invalid compositions are rejected; failed or non-converged science is never hidden; plots are readable; sweep failure gaps remain explicit rather than interpolated; exports preserve precision and state their units; save/load is reproducible; the report is truthful; limitations are accessible; and the stated model scope is truthful.

TRUTHFULNESS OF CLAIMS: no claim of commercial PVT capability; no unsupported component implied; the kij = 0 assumption visible; and the verified components remain methane, ethane and propane unless evidence in the repository says otherwise. Where documentation and the application disagree, correct the documentation to match the application - never the reverse.

READINESS: deployment smoke readiness, clean-environment startup, and the Streamlit application launching correctly.

Fix P0/P1 release defects. Record non-blocking P2/P3 findings rather than fixing them. The scientific engine is frozen and must not change.

BUILD-TIME TESTING POLICY. Run only focused tests for the files and behaviour you changed, plus Ruff and mypy if useful. Do NOT run the whole pytest suite for reassurance - the orchestrator runs the authoritative full-suite verification after you finish, and duplicating it wastes a great deal of wall-clock time.

## Scientific invariants claimed to hold
  - The scientific engine is frozen: no file under src/pvt_phase_simulator/, data/, docs/validation/ or tests/golden_master/ may change.
  - No thermodynamic relation may be implemented, restated or approximated in the application layer.
  - Unavailable quantities are reported as unavailable and never fabricated or interpolated.
  - Structured failures remain failures; only CriticalPointStatus.CONVERGED is a certified critical point.

## Repository state
- Branch: `app-v1.2-engineering`
- HEAD: `b95f80c2889f95b4164959f187a111dad67b3394`
- Base for this change: `b95f80c2889f95b4164959f187a111dad67b3394`

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
Changed files: ['README.md', 'docs/STREAMLIT_APPLICATION.md', 'src/pvt_phase_simulator_ui/adapters.py', 'src/pvt_phase_simulator_ui/app.py', 'src/pvt_phase_simulator_ui/state.py', 'src/pvt_phase_simulator_ui/units.py', 'src/pvt_phase_simulator_ui/views.py', 'tests/test_app_adapters.py', 'tests/test_app_streamlit.py', 'tests/test_app_sweeps.py']

## Builder's own report — treat as an unverified claim
```
Release QA is complete. P1 fixes prevent raw exception exposure, clear obsolete results before retries, persist plain-language failure notices, and safely reject numeric conversion overflow. Documentation now matches the six-page app and envelope behavior.

The full end-to-end AppTest journey succeeded. Protected artifact hashes remain unchanged.

Non-blocking P2 recorded: Streamlit logs an Arrow auto-coercion warning for mixed numeric/“—” sweep-table columns, but renders the table successfully without a user-facing exception.

Per the build-time policy, I ran the focused application suite—not the entire repository pytest suite.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "Focused application pytest suite: 166 passed, with one environment-only PytestCacheWarning. Ruff check passed; Ruff format check reported 240 files formatted; mypy passed for 47 source files; compileall passed. Streamlit startup/health smoke and clean-shell compatibility passed within the focused suite. A real AppTest journey also completed flash, bubble/dew envelope, engineering sweep, validation, diagnostics, field-unit switching, and certified critical-point solving without UI exceptions.",
  "files_changed": ["README.md", "docs/STREAMLIT_APPLICATION.md", "src/pvt_phase_simulator_ui/adapters.py", "src/pvt_phase_simulator_ui/app.py", "src/pvt_phase_simulator_ui/state.py", "src/pvt_phase_simulator_ui/units.py", "src/pvt_phase_simulator_ui/views.py", "tests/test_app_adapters.py", "tests/test_app_streamlit.py", "tests/test_app_sweeps.py"],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>
```

## Diff stat
```
 .ai/work_packages/01_model_and_limitations.json |   2 +-
 .ai/work_packages/02_field_units.json           |   2 +-
 .ai/work_packages/03_case_save_load.json        |   4 +-
 .ai/work_packages/04_engineering_report.json    |   4 +-
 .ai/work_packages/05_v1_2_release_qa.json       |   2 +-
 .ai/workflow_state.json                         | 438 +++++++++++++++++++++++-
 README.md                                       |   6 +-
 docs/STREAMLIT_APPLICATION.md                   |  14 +-
 src/pvt_phase_simulator_ui/adapters.py          |   8 +-
 src/pvt_phase_simulator_ui/app.py               |  57 ++-
 src/pvt_phase_simulator_ui/state.py             |  70 +++-
 src/pvt_phase_simulator_ui/units.py             |  24 +-
 src/pvt_phase_simulator_ui/views.py             |  94 ++++-
 tests/test_app_adapters.py                      |  43 +++
 tests/test_app_streamlit.py                     | 101 ++++++
 tests/test_app_sweeps.py                        |  22 ++
 16 files changed, 822 insertions(+), 69 deletions(-)

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
index 0af62c4..3d506db 100644
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
@@ -64,6 +64,6 @@
   "dependencies": [
     "03_case_save_load"
   ],
-  "status": "PENDING",
+  "status": "COMMITTED",
   "notes": "The report renders results; it never recomputes them and never starts a calculation. Do not add a reporting framework - HTML or Markdown assembled from the existing adapters is sufficient. A failed or unavailable field appears as such, not as a blank."
 }
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
index a6e5b0a..49d11fa 100644
--- a/.ai/workflow_state.json
+++ b/.ai/workflow_state.json
@@ -3,19 +3,19 @@
   "phase": "post-v1.0-extensions",
   "workflow_status": "CLAUDE_RUNNING",
   "last_scientific_commit": "d2a0a74",
-  "last_independent_audit_commit": "c29ae4961543e74a271e8e2e54de22852892cf00",
+  "last_independent_audit_commit": "b95f80c2889f95b4164959f187a111dad67b3394",
   "work_packages_since_audit": 0,
-  "current_work_package": "01_model_and_limitations",
+  "current_work_package": "05_v1_2_release_qa",
   "current_risk": "LOW",
-  "audit_required": false,
-  "audit_reason": null,
+  "audit_required": true,
+  "audit_reason": "package audit_policy=IMMEDIATE",
   "blocking_findings": [],
   "safe_defer_findings": [
     {
-      "id": "D-1",
+      "id": "D-4",
       "severity": "D",
       "blocks": false,
-      "summary": "adapters.py's COMPONENT_NAMES was changed from a hardcoded literal to a value derived from COMPONENTS; harmless and value-preserving (confirmed by test run) but technically broader than the 'documentation/presentation only, new panel' framing of the work package."
+      "summary": "reports.py's _termination_failed() classifies envelope branch failure via substring matching (\"failed\"/\"failure\"/\"lost\") against EnvelopeTerminationReason string values instead of an explicit allowlist; currently correct for all known enum members and only affects a supplementary failure banner (termination status/message are always shown verbatim regardless), so no truthfulness impact today, but fragile if the frozen enum ever gains new members."
     }
   ],
   "deferred_independent_audits": [
@@ -61,31 +61,102 @@
   "workflow_id": "c3d365745ae6",
   "builder": "codex",
   "reviewer": "claude",
-  "last_completed_stage": "audited",
+  "last_completed_stage": "verified",
   "verification_status": "passed",
-  "base_commit": "46b1d8e75c60d76b5e7d920ef30f6c1f14da051d",
+  "base_commit": "b95f80c2889f95b4164959f187a111dad67b3394",
   "resulting_commit": null,
-  "builder_report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260906-004904-01_model_and_limitations-codex-report.md",
+  "builder_report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260908-133040-05_v1_2_release_qa-codex-report.md",
   "builder_evidence": {
     "builder": "codex",
-    "package": "01_model_and_limitations",
+    "package": "05_v1_2_release_qa",
     "workflow_id": "c3d365745ae6",
-    "report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260906-004904-01_model_and_limitations-codex-report.md",
-    "report_sha256": "aba55903df96e2d4cb704675c21b9a85475bea40f07260b49672cb6766daff05",
+    "report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260908-133040-05_v1_2_release_qa-codex-report.md",
+    "report_sha256": "ff28f99db820b91d24d2a41a7ef0f53ba918597719bf4d861a9e4e3439679c90",
     "revision": 1,
     "kind": "build"
   },
-  "tree_fingerprint": "26f7c0227453f1f2851c35ee7897ac909e05b24fb1876f0b9e11f4226cc01a00",
+  "tree_fingerprint": "2d904d41672955f76341b976503524b2815ab3a5dd269a9c8b7d9edfc0fae8d6",
   "revisions": [
     {
-      "package": "01_model_and_limitations",
+      "package": "05_v1_2_release_qa",
       "revision": 1,
       "author": "codex",
       "kind": "build",
-      "at": 1788646855.9640622
+      "at": 1788865133.0810683
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
@@ -536,6 +607,341 @@
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
+    },
+    {
+      "from": "CLAUDE_RUNNING",
+      "to": "APPROVED",
+      "reason": "independent audit approved"
+    },
+    {
+      "from": "APPROVED",
+      "to": "PLANNING",
+      "reason": "planning 05_v1_2_release_qa"
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
diff --git a/README.md b/README.md
index 0c298b2..cc94041 100644
--- a/README.md
+++ b/README.md
@@ -66,9 +66,9 @@ The first experimental comparison and its limitations are documented in
 ## Streamlit application
 
 An optional Streamlit frontend now provides Overview, Phase Envelope, Critical
-Point, Validation, and Diagnostics views for the verified methane, ethane, and
-propane scope. It calls the existing scientific APIs and Module 21 Plotly
-figures without changing the v1.0 engine.
+Point, Engineering Sweeps, Validation, and Diagnostics views for the verified
+methane, ethane, and propane scope. It calls the existing scientific APIs and
+Module 21 Plotly figures without changing the v1.0 engine.
 
 ```powershell
 uv run streamlit run streamlit_app.py
diff --git a/docs/STREAMLIT_APPLICATION.md b/docs/STREAMLIT_APPLICATION.md
index 89ae7f0..5ea038b 100644
--- a/docs/STREAMLIT_APPLICATION.md
+++ b/docs/STREAMLIT_APPLICATION.md
@@ -87,7 +87,9 @@ the physical state; it does not run a calculation or make a current scientific
 result stale. On submission, the panel shows the composition total and rejects
 nonfinite, negative, above-100, zero-total, and materially non-100% composition.
 It rejects pressure at or below zero and temperature at or below absolute zero
-in every supported unit. It does not silently normalize invalid composition.
+in every supported unit, and rejects finite field values whose conversion would
+fall outside the supported floating-point range. It does not silently normalize
+invalid composition.
 
 The native example selector can fill the form with the default
 two-phase-oriented case, the known 50/50 methane/propane single-phase case at
@@ -162,7 +164,12 @@ Results persist in Streamlit session state. Each stores the exact composition,
 temperature, and internal-pressure signature used to produce it. Changed or
 invalid current input marks the prior result stale until explicitly recalculated.
 Stale results remain visible with a warning, but downloads are unavailable until
-the changed inputs have a current calculated result.
+the changed inputs have a current calculated result. Starting an explicit retry
+removes the prior result for that calculation. If an unexpected exception stops
+the retry before a new result exists, the application keeps a plain-language
+failure notice instead of redisplaying the old result or exposing a raw traceback;
+technical details remain in server logs. Structured scientific failure results
+remain visible with their public status and termination evidence.
 
 Case files are distinct from result exports: they contain reproducible inputs
 only and do not serialize cached scientific result objects.
@@ -211,7 +218,8 @@ Retrospective nearest-root diagnostics are separate and explicitly labelled
 
 The frontend inherits all v1.0 applicability limits. Supported property scope
 is Methane, Ethane, and Propane with the documented default-zero interaction
-assumption. Bounded envelope continuation begins at the entered temperature and
+assumption. The bounded UI envelope trace cold-starts 30 K below the entered
+temperature and continues both branches through the operating temperature; it
 may legitimately return unavailable branches or structured termination.
 
 This extension adds no reservoir depletion, CCE/CVD, separator trains,
diff --git a/src/pvt_phase_simulator_ui/adapters.py b/src/pvt_phase_simulator_ui/adapters.py
index de4fac0..b418c2d 100644
--- a/src/pvt_phase_simulator_ui/adapters.py
+++ b/src/pvt_phase_simulator_ui/adapters.py
@@ -80,7 +80,13 @@ class ScientificInputs:
 def composition_total(values: Sequence[float]) -> float:
     """Return the floating-point sum displayed at the input boundary."""
 
-    return fsum(float(value) for value in values)
+    numeric = tuple(float(value) for value in values)
+    try:
+        return fsum(numeric)
+    except (OverflowError, ValueError):
+        # Display invalid extreme inputs without allowing fsum's strict overflow
+        # handling to escape the ordinary validation path.
+        return sum(numeric)
 
 
 def validate_scientific_inputs(
diff --git a/src/pvt_phase_simulator_ui/app.py b/src/pvt_phase_simulator_ui/app.py
index 050cd85..c066a24 100644
--- a/src/pvt_phase_simulator_ui/app.py
+++ b/src/pvt_phase_simulator_ui/app.py
@@ -2,6 +2,7 @@
 
 from __future__ import annotations
 
+import logging
 from collections.abc import MutableMapping
 from pathlib import Path
 from typing import Any
@@ -27,8 +28,10 @@ from pvt_phase_simulator_ui.context import session
 from pvt_phase_simulator_ui.state import (
     INPUT_EXAMPLES,
     apply_selected_input_example,
+    begin_result_attempt,
     initialize_session,
     store_result,
+    store_result_action_failure,
     synchronize_unit_inputs,
 )
 from pvt_phase_simulator_ui.units import (
@@ -39,6 +42,30 @@ from pvt_phase_simulator_ui.units import (
 )
 
 PAGES_DIRECTORY = Path(__file__).with_name("pages")
+LOGGER = logging.getLogger(__name__)
+
+FLASH_ACTION_FAILURE = (
+    "The flash calculation stopped unexpectedly and did not return a result. "
+    "Any earlier flash result was removed so it cannot be mistaken for the "
+    "current calculation. Review the inputs and try again."
+)
+PAGE_RENDER_FAILURE = (
+    "This view could not be displayed because the application encountered an "
+    "unexpected error. No failed calculation has been presented as a result. "
+    "Return to Overview or retry the action."
+)
+INPUT_PANEL_FAILURE = (
+    "The input panel could not be prepared because the application encountered "
+    "an unexpected error. No calculation was run. Refresh the page and try again."
+)
+CASE_LOAD_FAILURE = (
+    "Case load unavailable because the file could not be processed safely. "
+    "No inputs were changed and no calculation was run."
+)
+CASE_SAVE_FAILURE = (
+    "Case save unavailable because the current inputs could not be serialized "
+    "safely. Review the inputs and try again."
+)
 
 
 @st.cache_data(show_spinner=False, max_entries=16)
@@ -87,6 +114,9 @@ def _case_controls() -> None:
                 _load_case_inputs(uploaded.getvalue(), session())
             except CaseFileError as error:
                 st.error(f"Case load unavailable: {error}")
+            except Exception:  # noqa: BLE001 - uploaded data must not expose internals
+                LOGGER.exception("Unexpected failure while loading a case file")
+                st.error(CASE_LOAD_FAILURE)
             else:
                 st.success("Case loaded. Inputs restored; no calculation was run.")
 
@@ -94,6 +124,9 @@ def _case_controls() -> None:
             payload = serialize_case(case_from_state(session()))
         except CaseFileError as error:
             st.caption(f"Save unavailable until all case inputs are valid: {error}")
+        except Exception:  # noqa: BLE001 - session data must not expose internals
+            LOGGER.exception("Unexpected failure while serializing a case file")
+            st.caption(CASE_SAVE_FAILURE)
         else:
             st.download_button(
                 "Save case",
@@ -247,8 +280,15 @@ def run_app() -> None:
         layout="wide",
         initial_sidebar_state="expanded",
     )
-    initialize_session(session())
-    inputs, run_flash = _input_form()
+    try:
+        initialize_session(session())
+        inputs, run_flash = _input_form()
+    except Exception:  # noqa: BLE001 - never expose Streamlit's raw exception UI
+        LOGGER.exception("Unexpected error while preparing the scientific input panel")
+        st.error(INPUT_PANEL_FAILURE, icon=":material/error:")
+        return
+    if run_flash:
+        begin_result_attempt(session(), "flash")
     _header()
     page = st.navigation(
         [
@@ -286,7 +326,11 @@ def run_app() -> None:
         ],
         position="sidebar",
     )
-    page.run()
+    try:
+        page.run()
+    except Exception:  # noqa: BLE001 - never expose Streamlit's raw exception UI
+        LOGGER.exception("Unexpected error while rendering Streamlit page %s", page)
+        st.error(PAGE_RENDER_FAILURE, icon=":material/error:")
     if run_flash:
         assert inputs is not None
         with st.sidebar.status("Running production flash…", expanded=True) as status:
@@ -296,9 +340,10 @@ def run_app() -> None:
                 result = _cached_flash(inputs)
                 store_result(session(), "flash", result, inputs)
                 status.update(label="Flash complete", state="complete", expanded=False)
-            except (ValueError, ArithmeticError) as error:
-                session()["flash_startup_error"] = str(error)
+            except Exception:  # noqa: BLE001 - preserve a safe application boundary
+                LOGGER.exception("Unexpected failure in the production flash action")
+                store_result_action_failure(session(), "flash", FLASH_ACTION_FAILURE)
                 status.update(label="Flash failed", state="error", expanded=True)
-                st.error(f"Production flash failure: {error}")
+                st.error(FLASH_ACTION_FAILURE, icon=":material/error:")
             else:
                 st.rerun()
diff --git a/src/pvt_phase_simulator_ui/state.py b/src/pvt_phase_simulator_ui/state.py
index 425eb15..ae16323 100644
--- a/src/pvt_phase_simulator_ui/state.py
+++ b/src/pvt_phase_simulator_ui/state.py
@@ -73,6 +73,7 @@ _DEFAULT_SWEEP_POINTS: Final = 21
 def initialize_session(state: MutableMapping[str, Any]) -> None:
     state.setdefault("results", {})
     state.setdefault("result_signatures", {})
+    state.setdefault("result_action_failures", {})
     state.setdefault("submitted_inputs", None)
     state.setdefault("current_inputs", None)
     state.setdefault("input_example", None)
@@ -134,15 +135,27 @@ def synchronize_sweep_inputs(state: MutableMapping[str, Any]) -> None:
     points = state["sweep_points_value"]
     if isfinite(start) and isfinite(end):
         if old_kind == "pressure":
-            state["sweep_pressure_start_pa"] = pressure_to_pa(start, old_pressure_unit)
-            state["sweep_pressure_end_pa"] = pressure_to_pa(end, old_pressure_unit)
+            try:
+                canonical_start = pressure_to_pa(start, old_pressure_unit)
+                canonical_end = pressure_to_pa(end, old_pressure_unit)
+            except ValueError:
+                # Keep the last valid canonical bounds. The form validator reports
+                # the invalid displayed bounds in ordinary language on submission.
+                pass
+            else:
+                state["sweep_pressure_start_pa"] = canonical_start
+                state["sweep_pressure_end_pa"] = canonical_end
         elif old_kind == "temperature":
-            state["sweep_temperature_start_k"] = temperature_to_k(
-                start, old_temperature_unit
-            )
-            state["sweep_temperature_end_k"] = temperature_to_k(
-                end, old_temperature_unit
-            )
+            try:
+                canonical_start = temperature_to_k(start, old_temperature_unit)
+                canonical_end = temperature_to_k(end, old_temperature_unit)
+            except ValueError:
+                # Keep the last valid canonical bounds. The form validator reports
+                # the invalid displayed bounds in ordinary language on submission.
+                pass
+            else:
+                state["sweep_temperature_start_k"] = canonical_start
+                state["sweep_temperature_end_k"] = canonical_end
     if isinstance(points, int) and not isinstance(points, bool):
         state[f"sweep_points_{old_kind}"] = points
 
@@ -194,12 +207,22 @@ def synchronize_unit_inputs(state: MutableMapping[str, Any]) -> None:
     if temperature_value != float(state["rendered_temperature_value"]) and isfinite(
         temperature_value
     ):
-        state["temperature_k"] = temperature_to_k(temperature_value, old_temperature)
+        try:
+            canonical_temperature = temperature_to_k(temperature_value, old_temperature)
+        except ValueError:
+            pass
+        else:
+            state["temperature_k"] = canonical_temperature
     pressure_value = float(state["pressure_value"])
     if pressure_value != float(state["rendered_pressure_value"]) and isfinite(
         pressure_value
     ):
-        state["pressure_pa"] = pressure_to_pa(pressure_value, old_pressure)
+        try:
+            canonical_pressure = pressure_to_pa(pressure_value, old_pressure)
+        except ValueError:
+            pass
+        else:
+            state["pressure_pa"] = canonical_pressure
 
     if old_temperature is not new_temperature:
         state["temperature_value"] = temperature_from_k(
@@ -255,6 +278,33 @@ def store_result(
     initialize_session(state)
     state["results"][name] = value
     state["result_signatures"][name] = inputs.signature
+    state["result_action_failures"].pop(name, None)
+
+
+def begin_result_attempt(state: MutableMapping[str, Any], name: str) -> None:
+    """Remove prior evidence before explicitly retrying one calculation."""
+
+    initialize_session(state)
+    state["results"].pop(name, None)
+    state["result_signatures"].pop(name, None)
+    state["result_action_failures"].pop(name, None)
+
+
+def store_result_action_failure(
+    state: MutableMapping[str, Any], name: str, message: str
+) -> None:
+    """Persist a safe failed-attempt message without retaining an old result."""
+
+    begin_result_attempt(state, name)
+    state["result_action_failures"][name] = message
+
+
+def get_result_action_failure(state: MutableMapping[str, Any], name: str) -> str | None:
+    """Return the safe message for an action that produced no result."""
+
+    initialize_session(state)
+    failures = cast(dict[str, str], state["result_action_failures"])
+    return failures.get(name)
 
 
 def get_result(state: MutableMapping[str, Any], name: str) -> object | None:
diff --git a/src/pvt_phase_simulator_ui/units.py b/src/pvt_phase_simulator_ui/units.py
index 6379f86..781a1e0 100644
--- a/src/pvt_phase_simulator_ui/units.py
+++ b/src/pvt_phase_simulator_ui/units.py
@@ -43,6 +43,12 @@ PA_PER_PRESSURE_UNIT: Final[dict[PressureUnit, float]] = {
 }
 
 
+def _finite_conversion(value: float, quantity: str) -> float:
+    if not isfinite(value):
+        raise ValueError(f"{quantity} is outside the supported numeric range.")
+    return value
+
+
 def _pressure_unit(unit: PressureUnit | str) -> PressureUnit:
     try:
         return unit if isinstance(unit, PressureUnit) else PressureUnit(unit)
@@ -69,7 +75,8 @@ def pressure_to_pa(value: float, unit: PressureUnit | str) -> float:
     numeric = float(value)
     if not isfinite(numeric):
         raise ValueError("Pressure must be finite.")
-    return numeric * PA_PER_PRESSURE_UNIT[_pressure_unit(unit)]
+    converted = numeric * PA_PER_PRESSURE_UNIT[_pressure_unit(unit)]
+    return _finite_conversion(converted, "Pressure")
 
 
 def pressure_from_pa(value_pa: float, unit: PressureUnit | str) -> float:
@@ -78,7 +85,8 @@ def pressure_from_pa(value_pa: float, unit: PressureUnit | str) -> float:
     numeric = float(value_pa)
     if not isfinite(numeric):
         raise ValueError("Pressure must be finite.")
-    return numeric / PA_PER_PRESSURE_UNIT[_pressure_unit(unit)]
+    converted = numeric / PA_PER_PRESSURE_UNIT[_pressure_unit(unit)]
+    return _finite_conversion(converted, "Pressure")
 
 
 def temperature_to_k(value: float, unit: TemperatureUnit | str) -> float:
@@ -91,8 +99,10 @@ def temperature_to_k(value: float, unit: TemperatureUnit | str) -> float:
     if selected is TemperatureUnit.KELVIN:
         return numeric
     if selected is TemperatureUnit.CELSIUS:
-        return numeric + 273.15
-    return (numeric + 459.67) * (5.0 / 9.0)
+        converted = numeric + 273.15
+    else:
+        converted = (numeric + 459.67) * (5.0 / 9.0)
+    return _finite_conversion(converted, "Temperature")
 
 
 def temperature_from_k(value_k: float, unit: TemperatureUnit | str) -> float:
@@ -105,8 +115,10 @@ def temperature_from_k(value_k: float, unit: TemperatureUnit | str) -> float:
     if selected is TemperatureUnit.KELVIN:
         return numeric
     if selected is TemperatureUnit.CELSIUS:
-        return numeric - 273.15
-    return numeric * (9.0 / 5.0) - 459.67
+        converted = numeric - 273.15
+    else:
+        converted = numeric * (9.0 / 5.0) - 459.67
+    return _finite_conversion(converted, "Temperature")
 
 
 def convert_pressure(
diff --git a/src/pvt_phase_simulator_ui/views.py b/src/pvt_phase_simulator_ui/views.py
index 7b8d254..8cca655 100644
--- a/src/pvt_phase_simulator_ui/views.py
+++ b/src/pvt_phase_simulator_ui/views.py
@@ -2,6 +2,7 @@
 
 from __future__ import annotations
 
+import logging
 import re
 from dataclasses import asdict
 from pathlib import Path
@@ -63,9 +64,12 @@ from pvt_phase_simulator_ui.exports import (
 from pvt_phase_simulator_ui.model_scope import ModelScope, load_model_scope
 from pvt_phase_simulator_ui.reports import export_engineering_report_html
 from pvt_phase_simulator_ui.state import (
+    begin_result_attempt,
     get_result,
+    get_result_action_failure,
     result_is_stale,
     store_result,
+    store_result_action_failure,
     synchronize_sweep_inputs,
 )
 from pvt_phase_simulator_ui.styles import phase_split_bar
@@ -87,6 +91,28 @@ from pvt_phase_simulator_ui.units import (
 )
 
 ROOT = Path(__file__).resolve().parents[2]
+LOGGER = logging.getLogger(__name__)
+
+ENVELOPE_ACTION_FAILURE: Final = (
+    "The phase-envelope calculation stopped unexpectedly and did not return a "
+    "result. Any earlier envelope result was removed so it cannot be mistaken "
+    "for the current calculation. Review the inputs and try again."
+)
+CRITICAL_ACTION_FAILURE: Final = (
+    "The critical-point calculation stopped unexpectedly and did not return a "
+    "result. Any earlier critical-point result was removed so it cannot be "
+    "mistaken for the current calculation. Review the seed and try again."
+)
+CRITICAL_SCAN_ACTION_FAILURE: Final = (
+    "The criticality map stopped unexpectedly and did not return a result. Any "
+    "earlier map was removed so it cannot be mistaken for the current calculation. "
+    "Review the inputs and try again."
+)
+SWEEP_ACTION_FAILURE: Final = (
+    "The engineering sweep stopped unexpectedly and did not return a complete "
+    "result. Any earlier sweep was removed so it cannot be mistaken for the "
+    "current calculation. Review the bounds and try again."
+)
 
 _CRITICAL_TEMPERATURE_TEXT: Final = re.compile(
     r"(?P<label>(?:^|<br>)T=)"
@@ -255,6 +281,14 @@ def _stale(name: str, inputs: ScientificInputs | None) -> bool:
     return stale
 
 
+def _show_action_failure(name: str) -> bool:
+    message = get_result_action_failure(session(), name)
+    if message is None:
+        return False
+    st.error(message, icon=":material/error:")
+    return True
+
+
 def _status_rows(rows: list[tuple[str, object, str]]) -> None:
     st.dataframe(
         pd.DataFrame(rows, columns=("Field", "Value", "Units / meaning")),
@@ -460,10 +494,12 @@ def render_overview(inputs: ScientificInputs | None) -> None:
     _render_model_scope_panel()
     raw = get_result(session(), "flash")
     if raw is None:
-        st.info(
-            "Submit valid fluid inputs with RUN FLASH to create a production result.",
-            icon=":material/info:",
-        )
+        if not _show_action_failure("flash"):
+            st.info(
+                "Submit valid fluid inputs with RUN FLASH to create a production "
+                "result.",
+                icon=":material/info:",
+            )
         return
     result = cast(TwoPhaseFlashResult, raw)
     view = adapt_flash_result(result)
@@ -627,6 +663,7 @@ def render_phase_envelope(inputs: ScientificInputs | None) -> None:
         icon=":material/play_arrow:",
     ):
         assert action_inputs is not None
+        begin_result_attempt(session(), "envelope")
         with st.status("Tracing bubble and dew branches…", expanded=True) as status:
             status.write(
                 "Cold-starting below the operating point, then continuing both "
@@ -638,13 +675,17 @@ def render_phase_envelope(inputs: ScientificInputs | None) -> None:
                 result = _calculate_envelope(action_inputs)
                 store_result(session(), "envelope", result, action_inputs)
                 status.update(label="Envelope trace complete", state="complete")
-            except (ValueError, ArithmeticError) as error:
+            except Exception:  # noqa: BLE001 - preserve a safe application boundary
+                LOGGER.exception("Unexpected failure in the phase-envelope action")
+                store_result_action_failure(
+                    session(), "envelope", ENVELOPE_ACTION_FAILURE
+                )
                 status.update(label="Envelope trace failed", state="error")
-                st.error(f"Phase-envelope calculation could not start: {error}")
     _action_requirement(action_inputs)
     raw = get_result(session(), "envelope")
     if raw is None:
-        st.info("No calculated envelope is available.", icon=":material/info:")
+        if not _show_action_failure("envelope"):
+            st.info("No calculated envelope is available.", icon=":material/info:")
         return
     result = cast(PhaseEnvelopeResult, raw)
     _stale("envelope", inputs)
@@ -773,6 +814,7 @@ def render_critical_point(inputs: ScientificInputs | None) -> None:
     _action_requirement(action_inputs)
     if run_solver:
         assert action_inputs is not None
+        begin_result_attempt(session(), "critical")
         with st.status("Solving production critical conditions…") as status:
             try:
                 store_result(
@@ -782,11 +824,15 @@ def render_critical_point(inputs: ScientificInputs | None) -> None:
                     action_inputs,
                 )
                 status.update(label="Critical solver complete", state="complete")
-            except (ValueError, ArithmeticError) as error:
+            except Exception:  # noqa: BLE001 - preserve a safe application boundary
+                LOGGER.exception("Unexpected failure in the critical-point action")
+                store_result_action_failure(
+                    session(), "critical", CRITICAL_ACTION_FAILURE
+                )
                 status.update(label="Critical solver failed", state="error")
-                st.error(f"Critical solver could not start: {error}")
     if run_map:
         assert action_inputs is not None
+        begin_result_attempt(session(), "critical_scan")
         with st.status("Evaluating bounded diagnostic map…") as status:
             try:
                 store_result(
@@ -796,12 +842,16 @@ def render_critical_point(inputs: ScientificInputs | None) -> None:
                     action_inputs,
                 )
                 status.update(label="Criticality map complete", state="complete")
-            except (ValueError, ArithmeticError) as error:
+            except Exception:  # noqa: BLE001 - preserve a safe application boundary
+                LOGGER.exception("Unexpected failure in the criticality-map action")
+                store_result_action_failure(
+                    session(), "critical_scan", CRITICAL_SCAN_ACTION_FAILURE
+                )
                 status.update(label="Criticality map failed", state="error")
-                st.error(f"Criticality map could not be evaluated: {error}")
     raw = get_result(session(), "critical")
     if raw is None:
-        st.info("No production critical-point solve has been requested.")
+        if not _show_action_failure("critical"):
+            st.info("No production critical-point solve has been requested.")
     else:
         result = cast(MixtureCriticalPointResult, raw)
         view = adapt_critical_result(result)
@@ -904,6 +954,8 @@ def render_critical_point(inputs: ScientificInputs | None) -> None:
             ),
             key="criticality_map_chart",
         )
+    else:
+        _show_action_failure("critical_scan")
 
 
 @st.cache_data(show_spinner=False, max_entries=2)
@@ -1424,6 +1476,7 @@ def render_engineering_sweeps(inputs: ScientificInputs | None) -> None:
         except SweepValidationError as error:
             st.error(f"Submission unavailable: {error}")
         else:
+            begin_result_attempt(session(), "sweep")
             progress = st.progress(0.0, text="Starting sweep…")
 
             def _advance(done: int, total: int) -> None:
@@ -1432,14 +1485,21 @@ def render_engineering_sweeps(inputs: ScientificInputs | None) -> None:
                     text=f"Evaluated {done} of {total} points…",
                 )
 
-            with st.spinner("Running the sweep…"):
-                result = run_sweep(request, progress=_advance)
-            progress.empty()
-            store_result(session(), "sweep", result, action_inputs)
+            try:
+                with st.spinner("Running the sweep…"):
+                    result = run_sweep(request, progress=_advance)
+            except Exception:  # noqa: BLE001 - preserve a safe application boundary
+                LOGGER.exception("Unexpected failure in the engineering-sweep action")
+                store_result_action_failure(session(), "sweep", SWEEP_ACTION_FAILURE)
+            else:
+                store_result(session(), "sweep", result, action_inputs)
+            finally:
+                progress.empty()
 
     sweep = cast(SweepResult | None, get_result(session(), "sweep"))
     if sweep is None:
-        st.info("No sweep has been calculated yet.")
+        if not _show_action_failure("sweep"):
+            st.info("No sweep has been calculated yet.")
         return
     if _stale("sweep", inputs):
         return
diff --git a/tests/test_app_adapters.py b/tests/test_app_adapters.py
index c598b2d..688f989 100644
--- a/tests/test_app_adapters.py
+++ b/tests/test_app_adapters.py
@@ -7,6 +7,7 @@ import hashlib
 import json
 from dataclasses import replace
 from io import StringIO
+from math import isnan
 from pathlib import Path
 from types import SimpleNamespace
 from typing import cast
@@ -38,6 +39,7 @@ from pvt_phase_simulator_ui.adapters import (
     InputValidationError,
     adapt_critical_result,
     adapt_flash_result,
+    composition_total,
     flash_presentation_kind,
     load_module17_records,
     location_relative_to_envelope,
@@ -54,10 +56,13 @@ from pvt_phase_simulator_ui.exports import (
 from pvt_phase_simulator_ui.state import (
     INPUT_EXAMPLES,
     apply_selected_input_example,
+    begin_result_attempt,
     get_result,
+    get_result_action_failure,
     initialize_session,
     result_is_stale,
     store_result,
+    store_result_action_failure,
 )
 from pvt_phase_simulator_ui.units import (
     PressureUnit,
@@ -199,6 +204,23 @@ def test_absolute_zero_is_rejected_in_every_temperature_unit(
         )
 
 
+def test_finite_field_values_that_overflow_conversion_are_rejected_cleanly() -> None:
+    with pytest.raises(InputValidationError, match="supported numeric range"):
+        validate_scientific_inputs(
+            (50.0, 0.0, 50.0),
+            300.0,
+            1.0e308,
+            pressure_unit=PressureUnit.MPA,
+        )
+    with pytest.raises(ValueError, match="supported numeric range"):
+        temperature_from_k(1.0e308, TemperatureUnit.FAHRENHEIT)
+
+
+def test_extreme_invalid_composition_total_remains_reportable() -> None:
+    assert composition_total((1.0e308, 1.0e308, 1.0e308)) == float("inf")
+    assert isnan(composition_total((float("inf"), float("-inf"), 0.0)))
+
+
 def test_export_includes_selected_and_engine_units_explicitly() -> None:
     inputs = validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 5.0)
     units = UnitPreferences(TemperatureUnit.CELSIUS, PressureUnit.BAR)
@@ -474,6 +496,27 @@ def test_session_state_is_deterministic_and_marks_scientific_changes_stale() ->
     assert result_is_stale(state, "flash", None)
 
 
+def test_failed_retry_removes_prior_result_and_success_clears_failure() -> None:
+    state: dict[str, object] = {}
+    inputs = validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 5.0)
+    first_result = object()
+    replacement = object()
+
+    store_result(state, "flash", first_result, inputs)
+    begin_result_attempt(state, "flash")
+    assert get_result(state, "flash") is None
+    assert not result_is_stale(state, "flash", inputs)
+
+    message = "The calculation failed without a result."
+    store_result_action_failure(state, "flash", message)
+    assert get_result_action_failure(state, "flash") == message
+    assert get_result(state, "flash") is None
+
+    store_result(state, "flash", replacement, inputs)
+    assert get_result(state, "flash") is replacement
+    assert get_result_action_failure(state, "flash") is None
+
+
 def test_selecting_input_example_only_assigns_input_state() -> None:
     prior_result = object()
     state: dict[str, object] = {
diff --git a/tests/test_app_streamlit.py b/tests/test_app_streamlit.py
index 59c737b..5db9717 100644
--- a/tests/test_app_streamlit.py
+++ b/tests/test_app_streamlit.py
@@ -109,6 +109,38 @@ def test_case_upload_with_out_of_range_integer_surfaces_clean_error() -> None:
     )
 
 
+def test_unexpected_case_load_error_is_redacted(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    def raise_unexpected(_data: object, _state: object) -> object:
+        raise RuntimeError("PRIVATE_INTERNAL_CASE_DETAIL")
+
+    monkeypatch.setattr(ui_app, "_load_case_inputs", raise_unexpected)
+    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
+    app.file_uploader[0].set_value(("case.json", b"{}", "application/json")).run()
+    _button(app, "Load case").click().run()
+
+    assert not app.exception
+    assert any(ui_app.CASE_LOAD_FAILURE in error.value for error in app.error)
+    assert all("PRIVATE_INTERNAL_CASE_DETAIL" not in error.value for error in app.error)
+
+
+def test_unexpected_input_panel_error_is_redacted(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    def raise_unexpected() -> tuple[None, bool]:
+        raise RuntimeError("PRIVATE_INTERNAL_INPUT_DETAIL")
+
+    monkeypatch.setattr(ui_app, "_input_form", raise_unexpected)
+    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
+
+    assert not app.exception
+    assert any(ui_app.INPUT_PANEL_FAILURE in error.value for error in app.error)
+    assert all(
+        "PRIVATE_INTERNAL_INPUT_DETAIL" not in error.value for error in app.error
+    )
+
+
 def test_field_unit_selection_preserves_state_and_submits_si_to_engine() -> None:
     app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
 
@@ -308,6 +340,37 @@ def test_invalid_form_submission_never_creates_a_flash_result() -> None:
     assert any("Submission unavailable" in error.value for error in app.error)
 
 
+@pytest.mark.parametrize("field_index", (0, 4))
+def test_extreme_manual_inputs_report_validation_without_traceback(
+    field_index: int,
+) -> None:
+    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
+    app.number_input[field_index].set_value(1.0e308)
+    _button(app, "RUN FLASH").click().run()
+
+    assert not app.exception
+    assert "flash" not in app.session_state["results"]
+    assert any("Submission unavailable" in error.value for error in app.error)
+
+
+@pytest.mark.parametrize(
+    ("field_index", "expected"), ((0, "must not exceed"), (4, "numeric range"))
+)
+def test_extreme_manual_input_is_reported_without_a_raw_exception(
+    field_index: int, expected: str
+) -> None:
+    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
+    app.number_input[field_index].set_value(1.0e308)
+    _button(app, "RUN FLASH").click().run()
+
+    assert not app.exception
+    assert "flash" not in app.session_state["results"]
+    assert any(
+        "Submission unavailable" in error.value and expected in error.value
+        for error in app.error
+    )
+
+
 def test_valid_two_phase_submission_preserves_science_and_success_semantics() -> None:
     app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
     _button(app, "RUN FLASH").click().run()
@@ -394,6 +457,44 @@ def test_structured_flash_failure_is_presented_as_an_error(
     assert not any("No two-phase split was required" in item.value for item in app.info)
 
 
+def test_unexpected_flash_retry_has_no_traceback_or_obsolete_result(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
+    _button(app, "RUN FLASH").click().run()
+    prior_result = app.session_state["results"]["flash"]
+
+    def raise_unexpected(_inputs: object) -> object:
+        raise RuntimeError("PRIVATE_INTERNAL_FLASH_DETAIL")
+
+    monkeypatch.setattr(ui_app, "_cached_flash", raise_unexpected)
+    _button(app, "RUN FLASH").click().run()
+
+    assert not app.exception
+    assert prior_result is not None
+    assert "flash" not in app.session_state["results"]
+    failure = app.session_state["result_action_failures"]["flash"]
+    assert failure == ui_app.FLASH_ACTION_FAILURE
+    assert any(failure in item.value for item in app.error)
+    assert all("PRIVATE_INTERNAL_FLASH_DETAIL" not in item.value for item in app.error)
+
+
+def test_unexpected_page_error_is_replaced_with_plain_language(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    def raise_unexpected() -> None:
+        raise RuntimeError("PRIVATE_INTERNAL_PAGE_DETAIL")
+
+    monkeypatch.seta
… [truncated, 1840 more characters]
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
