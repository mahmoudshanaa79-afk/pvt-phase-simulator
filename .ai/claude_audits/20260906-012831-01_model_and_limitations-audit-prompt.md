# Independent audit: 01_model_and_limitations

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
- Name: 01_model_and_limitations
- Declared risk: LOW
- Objective: Add a user-facing panel stating exactly what this application models and what it does not. Show the Peng-Robinson EOS, the three verified components (methane, ethane, propane), the kij = 0 assumption, the validation scope, the calculations supported, the known limitations, an explicit statement that this is not a commercial PVT package, and the provenance already recorded in the repository. Documentation and presentation only; read existing values rather than restating them.

## Scientific invariants claimed to hold
  - The scientific engine is frozen: no file under src/pvt_phase_simulator/, data/, docs/validation/ or tests/golden_master/ may change.
  - No thermodynamic relation may be implemented, restated or approximated in the application layer.
  - Unavailable quantities are reported as unavailable and never fabricated or interpolated.
  - Structured failures remain failures; only CriticalPointStatus.CONVERGED is a certified critical point.

## Repository state
- Branch: `app-v1.2-engineering`
- HEAD: `46b1d8e75c60d76b5e7d920ef30f6c1f14da051d`
- Base for this change: `46b1d8e75c60d76b5e7d920ef30f6c1f14da051d`

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
Changed files: ['docs/STREAMLIT_APPLICATION.md', 'src/pvt_phase_simulator_ui/adapters.py', 'src/pvt_phase_simulator_ui/model_scope.py', 'src/pvt_phase_simulator_ui/views.py', 'tests/test_app_streamlit.py']

## Builder's own report — treat as an unverified claim
```
Implemented the Overview “Model and limitations” panel with repository-backed components, validation scope, and provenance. Added semantic UI tests and documentation. Scientific and protected artifacts remain unchanged.

All required tests and quality gates pass. Pytest emitted one non-failing cache-permission warning.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "pytest: 1238 passed, 1 warning; ruff check: passed; ruff format --check: 192 files formatted; mypy: no issues in 44 source files; compileall: passed",
  "files_changed": ["src/pvt_phase_simulator_ui/model_scope.py", "src/pvt_phase_simulator_ui/adapters.py", "src/pvt_phase_simulator_ui/views.py", "tests/test_app_streamlit.py", "docs/STREAMLIT_APPLICATION.md"],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>
```

## Diff stat
```
 .ai/workflow_state.json                | 65 +++++++++++++++++++++++++---
 docs/STREAMLIT_APPLICATION.md          | 15 +++++++
 src/pvt_phase_simulator_ui/adapters.py |  2 +-
 src/pvt_phase_simulator_ui/views.py    | 78 ++++++++++++++++++++++++++++++++++
 tests/test_app_streamlit.py            | 42 ++++++++++++++++++
 5 files changed, 195 insertions(+), 7 deletions(-)

```

## Full diff
```diff
diff --git a/.ai/workflow_state.json b/.ai/workflow_state.json
index 3c87327..0e4dbf3 100644
--- a/.ai/workflow_state.json
+++ b/.ai/workflow_state.json
@@ -1,14 +1,14 @@
 {
   "project": "pvt-phase-simulator",
   "phase": "post-v1.0-extensions",
-  "workflow_status": "IDLE",
+  "workflow_status": "CLAUDE_RUNNING",
   "last_scientific_commit": "d2a0a74",
   "last_independent_audit_commit": "c29ae4961543e74a271e8e2e54de22852892cf00",
   "work_packages_since_audit": 2,
-  "current_work_package": null,
-  "current_risk": null,
-  "audit_required": false,
-  "audit_reason": null,
+  "current_work_package": "01_model_and_limitations",
+  "current_risk": "LOW",
+  "audit_required": true,
+  "audit_reason": "package audit_policy=IMMEDIATE",
   "blocking_findings": [],
   "safe_defer_findings": [
     {
@@ -58,6 +58,34 @@
   "claude_cost_usd_this_package": 0.0,
   "claude_cost_unknown_runs": 0,
   "last_error": null,
+  "workflow_id": "c3d365745ae6",
+  "builder": "codex",
+  "reviewer": "claude",
+  "last_completed_stage": "verified",
+  "verification_status": "passed",
+  "base_commit": "46b1d8e75c60d76b5e7d920ef30f6c1f14da051d",
+  "resulting_commit": null,
+  "builder_report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260906-004904-01_model_and_limitations-codex-report.md",
+  "builder_evidence": {
+    "builder": "codex",
+    "package": "01_model_and_limitations",
+    "workflow_id": "c3d365745ae6",
+    "report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260906-004904-01_model_and_limitations-codex-report.md",
+    "report_sha256": "aba55903df96e2d4cb704675c21b9a85475bea40f07260b49672cb6766daff05",
+    "revision": 1,
+    "kind": "build"
+  },
+  "tree_fingerprint": "26f7c0227453f1f2851c35ee7897ac909e05b24fb1876f0b9e11f4226cc01a00",
+  "revisions": [
+    {
+      "package": "01_model_and_limitations",
+      "revision": 1,
+      "author": "codex",
+      "kind": "build",
+      "at": 1788646855.9640622
+    }
+  ],
+  "role_transitions": [],
   "history": [
     {
       "from": "IDLE",
@@ -468,6 +496,31 @@
       "from": "HUMAN_ACTION_REQUIRED",
       "to": "IDLE",
       "reason": "manually stopped"
+    },
+    {
+      "from": "IDLE",
+      "to": "PLANNING",
+      "reason": "planning 01_model_and_limitations"
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
-}
\ No newline at end of file
+}
diff --git a/docs/STREAMLIT_APPLICATION.md b/docs/STREAMLIT_APPLICATION.md
index 33c0844..cbeb30a 100644
--- a/docs/STREAMLIT_APPLICATION.md
+++ b/docs/STREAMLIT_APPLICATION.md
@@ -58,6 +58,21 @@ equation is implemented in the UI package.
 
 ## Inputs and views
 
+The default Overview includes an always-visible **Model and limitations** panel.
+It names the Peng–Robinson EOS and its default-zero binary-interaction policy,
+lists the property-verified components, distinguishes supported calculations
+from unsupported commercial-PVT workflows, and states the critical-point and
+unavailable-value safeguards. It explicitly says that the application is not a
+commercial PVT package or a substitute for engineering review.
+
+The panel does not maintain a second copy of repository facts. Component names,
+property verification states, and property citations come from the packaged
+component database; the validation state count, systems, and observed domain
+come from the protected Module 17 artifact; and the experimental citation comes
+from the checked source manifest. The recorded citations and exact artifact path
+are available in the panel's **Recorded provenance** expander. Opening the panel
+does not run a scientific calculation.
+
 The persistent Fluid inputs form supports the verified v1.0 Methane, Ethane,
 and Propane components. Composition is entered in mol %, temperature in K, and
 pressure in MPa. On submission, the panel shows the composition total and rejects
diff --git a/src/pvt_phase_simulator_ui/adapters.py b/src/pvt_phase_simulator_ui/adapters.py
index 9d11138..6c3c167 100644
--- a/src/pvt_phase_simulator_ui/adapters.py
+++ b/src/pvt_phase_simulator_ui/adapters.py
@@ -30,8 +30,8 @@ from pvt_phase_simulator.plotting import (
     load_validation_plot_records,
 )
 
-COMPONENT_NAMES: Final = ("Methane", "Ethane", "Propane")
 COMPONENTS: Final = (METHANE, ETHANE, PROPANE)
+COMPONENT_NAMES: Final = tuple(component.name for component in COMPONENTS)
 COMPOSITION_TOTAL_MOL_PERCENT: Final = 100.0
 COMPOSITION_TOLERANCE_MOL_PERCENT: Final = 1.0e-8
 PA_PER_MPA: Final = 1.0e6
diff --git a/src/pvt_phase_simulator_ui/views.py b/src/pvt_phase_simulator_ui/views.py
index e037370..37e937f 100644
--- a/src/pvt_phase_simulator_ui/views.py
+++ b/src/pvt_phase_simulator_ui/views.py
@@ -58,6 +58,7 @@ from pvt_phase_simulator_ui.exports import (
     export_json_bytes,
     export_sweep_csv_bytes,
 )
+from pvt_phase_simulator_ui.model_scope import ModelScope, load_model_scope
 from pvt_phase_simulator_ui.state import get_result, result_is_stale, store_result
 from pvt_phase_simulator_ui.styles import phase_split_bar
 from pvt_phase_simulator_ui.sweeps import (
@@ -265,8 +266,85 @@ def _flash_details(result: TwoPhaseFlashResult) -> None:
         st.dataframe(pd.DataFrame(phase_rows), hide_index=True, width="stretch")
 
 
+@st.cache_data(show_spinner=False, max_entries=1)
+def _model_scope() -> ModelScope:
+    return load_model_scope(ROOT)
+
+
+def _doi_link(doi: str | None) -> str:
+    if doi is None:
+        return "DOI unavailable"
+    return f"[DOI {doi}](https://doi.org/{doi})"
+
+
+def _render_model_scope_panel() -> None:
+    scope = _model_scope()
+    components = ", ".join(scope.verified_component_names)
+    systems = " and ".join(scope.validation_system_names)
+    temperature_min, temperature_max = scope.validation_temperature_range_k
+    pressure_min, pressure_max = scope.validation_pressure_range_mpa
+
+    with st.container(border=True):
+        st.subheader("Model and limitations", anchor="model-and-limitations")
+        st.markdown(
+            f"**Model.** {scope.eos_name} for {len(scope.verified_component_names)} "
+            f"property-verified components: **{components}**. The active "
+            "interaction policy is "
+            f"`{scope.interaction_policy.value}`: every omitted off-diagonal "
+            "binary interaction is **kij = 0**; no fitted interaction parameters "
+            "are used."
+        )
+        st.markdown(
+            "**Supported calculations.** Phase stability and isothermal flash; "
+            "bubble/dew phase-envelope tracing; mixture critical-point solving and "
+            "criticality scans; bounded pressure/temperature flash sweeps; and "
+            "repository-backed validation figures, diagnostics, and exports."
+        )
+        st.markdown(
+            f"**Validation scope.** The protected Module 17 artifact contains "
+            f"**{scope.validation_state_count} experimental VLE states** for "
+            f"**{systems}**, spanning {temperature_min:g}–{temperature_max:g} K and "
+            f"{pressure_min:g}–{pressure_max:g} MPa in the recorded states. This "
+            "does not establish accuracy for other components, mixtures, or "
+            "conditions."
+        )
+        st.markdown(
+            "**Known limitations.** Envelope continuation is bounded and may return "
+            "unavailable branches or structured terminations. Unavailable values "
+            "remain unavailable and are never fabricated or interpolated. Only "
+            "`CriticalPointStatus.CONVERGED` is a certified critical point. The "
+            "application provides no reservoir depletion, CCE/CVD, separator "
+            "trains, pseudocomponents or C7+, EOS tuning, kij fitting, new-component "
+            "support, or arbitrary reservoir-fluid validation."
+        )
+        st.warning(
+            "This is not a commercial PVT package and is not a substitute for "
+            "engineering review.",
+            icon=":material/warning:",
+        )
+        with st.expander("Recorded provenance", icon=":material/source:"):
+            for source in scope.property_sources:
+                st.markdown(
+                    f"**Component-property source — {source.name}.** "
+                    f"{source.citation} {_doi_link(source.doi)}"
+                )
+            st.markdown(
+                f"**Experimental-validation source — "
+                f"{scope.validation_source.name}.** "
+                f"{scope.validation_source.citation} "
+                f"{_doi_link(scope.validation_source.doi)}"
+            )
+            st.caption(
+                "Validation evidence is read from "
+                f"`{scope.validation_artifact.as_posix()}`; citations and component "
+                "verification status are read from repository-owned provenance "
+                "records."
+            )
+
+
 def render_overview(inputs: ScientificInputs | None) -> None:
     st.header("Overview")
+    _render_model_scope_panel()
     raw = get_result(session(), "flash")
     if raw is None:
         st.info(
diff --git a/tests/test_app_streamlit.py b/tests/test_app_streamlit.py
index 833b607..83941a0 100644
--- a/tests/test_app_streamlit.py
+++ b/tests/test_app_streamlit.py
@@ -20,6 +20,7 @@ from pvt_phase_simulator.eos.flash import FlashConvergenceStatus
 from pvt_phase_simulator_ui import app as ui_app
 from pvt_phase_simulator_ui import views
 from pvt_phase_simulator_ui.adapters import run_validated_flash
+from pvt_phase_simulator_ui.model_scope import load_model_scope
 
 ROOT = Path(__file__).resolve().parents[1]
 
@@ -69,6 +70,47 @@ def test_streamlit_apptest_starts_and_exposes_explicit_form_boundary() -> None:
     assert [button.label for button in app.button] == ["RUN FLASH"]
 
 
+def test_overview_exposes_repository_backed_model_and_limitations_panel() -> None:
+    scope = load_model_scope(ROOT)
+    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
+
+    assert not app.exception
+    assert "Model and limitations" in [item.value for item in app.subheader]
+    copy = "\n".join(item.value for item in app.markdown)
+    assert scope.eos_name in copy
+    assert ", ".join(scope.verified_component_names) in copy
+    assert scope.interaction_policy.value in copy
+    assert f"{scope.validation_state_count} experimental VLE states" in copy
+    assert all(system in copy for system in scope.validation_system_names)
+    assert "CriticalPointStatus.CONVERGED" in copy
+    assert "never fabricated or interpolated" in copy
+    assert all(source.citation in copy for source in scope.property_sources)
+    assert scope.validation_source.citation in copy
+    assert all(source.doi in copy for source in scope.property_sources if source.doi)
+    assert scope.validation_source.doi in copy
+    assert any("not a commercial PVT package" in item.value for item in app.warning)
+
+
+def test_model_scope_reads_recorded_component_and_validation_provenance() -> None:
+    scope = load_model_scope(ROOT)
+
+    assert scope.verified_component_names == ("Methane", "Ethane", "Propane")
+    assert scope.validation_state_count == 40
+    assert scope.validation_system_names == (
+        "Methane + Ethane",
+        "Methane + Propane",
+    )
+    assert scope.validation_temperature_range_k == (203.22, 283.38)
+    assert scope.validation_pressure_range_mpa == (0.891, 8.32)
+    assert {source.doi for source in scope.property_sources} == {
+        "10.1021/acs.jced.5c00110"
+    }
+    assert scope.validation_source.doi == "10.1021/acs.jced.5b00610"
+    assert scope.validation_artifact == Path(
+        "docs/validation/module17_vle_validation.csv"
+    )
+
+
 def test_example_selection_populates_inputs_without_populating_results() -> None:
     app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
 

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
