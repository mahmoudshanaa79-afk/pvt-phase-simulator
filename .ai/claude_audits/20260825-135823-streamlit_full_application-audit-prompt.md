# Independent audit: streamlit_full_application

This is a TARGETED RE-AUDIT. Confirm only whether each listed finding is genuinely closed, and whether the fix caused any regression. Do NOT repeat a whole-project audit.

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
- Name: streamlit_full_application
- Declared risk: MEDIUM
- Objective: Build the first optional post-v1.0 application extension: a polished, testable Streamlit frontend for the completed Hydrocarbon Phase-Behavior & PVT Simulator. Create app/streamlit_app.py as the entrypoint and keep supporting modules under app/ only when they improve maintainability (prefer a compact adapters/state/UI structure over a large page framework). Use a light, responsive scientific-engineering design with white/off-white surfaces, dark navy text, restrained teal/blue accents, thin borders, modest rounding, generous spacing, and no flashy gradients, neon, decorative gauges, or unnecessary animation. The header must identify PVT PHASE SIMULATOR and Peng-Robinson EOS - Hydrocarbon Phase Behavior. Provide Overview, Phase Envelope, Critical Point, Validation, and Diagnostics navigation using standard Streamlit constructs.

Provide a persistent Fluid Input panel for the verified v1 components Methane, Ethane, and Propane. Accept composition in mol %, show an exact live total with valid/invalid semantics, reject negative, above-100, zero-total, nonfinite, and materially non-100% input, and do not silently renormalize clearly invalid input. Accept positive finite temperature in K and pressure in MPa, convert mol % to fractions and MPa to internal Pa exactly, and call scientific APIs only after validation and an explicit RUN FLASH action. Preserve results across cosmetic reruns while clearly invalidating or marking results stale after scientific inputs change.

The Overview must answer the entered fluid/conditions, phase, vapor and liquid fractions, pressure, vapor and liquid compressibility factors, and location relative to the phase envelope. Never fabricate unavailable single-phase quantities. Use the existing public flash/result APIs unchanged, show source-provided liquid/vapor compositions only when available, and place advanced statuses, iterations, residuals, K values, phase compositions, and fugacity details in a technical-details expander only when public result fields provide them.

Use src/pvt_phase_simulator/plotting.py Figure-returning APIs rather than rebuilding plotting logic. The Phase Envelope view must retain bubble/dew identity, status-aware unavailable points, certified converged critical overlays, and the distinction between turning points and critical points. The Critical Point view must use existing Module 19/20 results and show Tc, Pc, lambda_min, C, critical direction, convergence, conditioning, and criticality maps only when available; lambda_min=0 alone must never be certified as a critical point. The Validation view must consume existing Module 17 artifacts/adapters and Module 21 parity, error, composition, status, and retrospective figures; retrospective nearest-root diagnostics must remain separately labelled 'not production prediction', and relative error remains 100*(P_pred-P_exp)/P_exp. The Diagnostics view must expose stable public status, termination, iteration, residual, Jacobian, continuation, and root information with explanatory labels, without reaching into private implementation objects.

The scientific engine and its evidence are protected: do not modify src/pvt_phase_simulator/** (including plotting.py), data/**, docs/validation/**, tests/golden_master/**, or any pre-existing scientific test enumerated in protected_files. Only the application surface enumerated in allowed_files may change. Any actual change to a configured high-risk scientific path automatically escalates effective risk to HIGH and requires an immediate independent audit; a protected-path change also fails local scope verification.

Do not implement Peng-Robinson, fugacity, Rachford-Rice, TPD, saturation, envelope, criticality, or continuation equations in app code. Do not change scientific APIs or tune calculations to reference values. Structured failures such as LINE_SEARCH_FAILED, JACOBIAN_FAILED, NOT_FOUND, BRANCH_LOST, and non-applicable results must remain failures/information rather than plausible success. Preserve the approved 50/50 methane/propane zero-kij critical regression exactly through production result objects: 321.5829183194 K and 8,534,443.23606381 Pa, displayed as 8.53444323606381 MPa.

Add semantic application tests in new tests/test_app*.py files without browser or screenshot dependence. Cover imports, input validation, unit conversion, prevention of invalid scientific calls, correct valid flash invocation, scientifically unchanged result adaptation, phase/fraction/composition/Z identity, structured failures, critical certification, Module 21 figure use, retrospective separation, pressure-error sign, turning-point labelling, absence of thermodynamic equations in app code, protected-file integrity, and deterministic adapter/session behavior. Create docs/STREAMLIT_APPLICATION.md with purpose, architecture, launch command, supported inputs/pages, API separation, state and failure handling, limitations, and relationship to the v1.0 scientific engine; add only a truthful README launch/capability update. Do not claim or implement reservoir depletion, CCE/CVD, separator trains, pseudocomponents/C7+, EOS tuning, kij fitting, new components, new experimental datasets, arbitrary reservoir-fluid validation, or commercial-PVT readiness.

## Scientific invariants claimed to hold
  - Modules 1-21 and every file under src/pvt_phase_simulator remain unchanged; the application calls existing public scientific APIs and Module 21 Plotly APIs.
  - No Peng-Robinson, fugacity, Rachford-Rice, TPD, saturation, phase-envelope, pseudo-arclength, Gibbs-curvature, or critical-point equations are duplicated in app code.
  - Internal pressure remains SI Pa; UI conversion is exactly MPa * 1e6 on input and Pa / 1e6 on display.
  - Composition input is mol %, converted exactly to mole fractions only after finite, nonnegative, positive-total, production-compatible 100% validation; clearly invalid input is not silently normalized.
  - Invalid UI input cannot invoke a production scientific API, and expensive calculations occur only on explicit user action.
  - Production result objects remain the scientific source of truth; adapters do not alter phase, vapor/liquid fractions, x/y compositions, Z factors, statuses, residuals, or iteration data.
  - Unavailable phase quantities are displayed as unavailable and are never fabricated for single-phase or failed states.
  - Bubble and dew identities are preserved; failed/unavailable envelope points are not rendered as converged states; pressure or temperature turning points are never labelled critical points.
  - Only CriticalPointStatus.CONVERGED results may be presented as certified critical points; lambda_min=0 alone and spinodal states are not critical certification.
  - The approved zero-kij 50/50 methane/propane result remains 321.5829183194 K and 8,534,443.23606381 Pa, displayed as 8.53444323606381 MPa, when supplied by the production result.
  - Module 17 production predictions remain separate from retrospective nearest-root diagnostics, which retain explicit 'not production prediction' semantics.
  - Module 17 relative pressure error remains 100*(P_pred-P_exp)/P_exp and reported validation remains kij=0 with no fitted binary interaction parameters.
  - Expected scientific failures remain structured failures/information and are never converted into plausible success or valid-looking critical metrics.
  - Session state preserves deliberate calculation results across cosmetic reruns while stale results are invalidated or clearly identified after scientific inputs change.
  - The existing 1137 scientific tests are retained and continue to pass; no historical test, tolerance, baseline, or expected scientific value is deleted or weakened.
  - Golden, property, and Module 17 protected artifacts remain byte-identical and are never regenerated.
  - Supported verified frontend property scope remains methane, ethane, and propane; no arbitrary reservoir-fluid or commercial-PVT claim is introduced.
  - No reservoir depletion, CCE/CVD, separator, pseudocomponent/C7+, EOS tuning, kij fitting, component expansion, or experimental-data extension is implemented.

## Repository state
- Branch: `master`
- HEAD: `341bc3d27479eca60d323e2f209d4f8865721ffa`
- Base for this change: `341bc3d27479eca60d323e2f209d4f8865721ffa`

## Findings this correction was meant to close
  - **VERIFY** (B):         PASS  .venv/Scripts/python.exe -m pytest -q
        PASS  .venv/Scripts/python.exe -m ruff check .
        PASS  .venv/Scripts/python.exe -m ruff format --check .
        PASS  .venv/Scripts/python.exe -m mypy src app
        PASS  .venv/Scripts/python.exe -m compileall -q src app
        PASS  git diff --check
        FAIL  scope: files outside allowed_files: ['.streamlit/']

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
        PASS  git diff --check
```
Changed files: ['README.md', 'app/__init__.py', 'app/adapters.py', 'app/state.py', 'app/streamlit_app.py', 'app/styles.py', 'docs/STREAMLIT_APPLICATION.md', 'tests/test_app_adapters.py']

## Builder's own report — treat as an unverified claim
```
Removed the optional untracked `.streamlit/config.toml`, eliminating the erroneous `.streamlit/` scope token. Scope and protected-artifact checks now pass.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "pytest: 1155 passed, 1 non-failing cache ACL warning (rerun with TEMP/TMP redirected after the direct invocation hit a system temp-directory ACL error); ruff check: passed; ruff format --check: 122 files already formatted; mypy src app: passed; compileall src app: passed; git diff --check: passed with line-ending warnings; orchestrator scope check: scope ok; all protected artifact hashes unchanged",
  "files_changed": ["README.md", "app/__init__.py", "app/adapters.py", "app/state.py", "app/streamlit_app.py", "app/styles.py", "docs/STREAMLIT_APPLICATION.md", "tests/test_app_adapters.py"],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>
```

## Diff stat
```
 .ai/workflow_state.json |  77 +++++--
 README.md               |  18 +-
 app/streamlit_app.py    | 566 +++++++++++++++++++++++++++++++++++++++++++++++-
 3 files changed, 643 insertions(+), 18 deletions(-)

```

## Full diff
```diff
diff --git a/.ai/workflow_state.json b/.ai/workflow_state.json
index f9664d6..cf9ed09 100644
--- a/.ai/workflow_state.json
+++ b/.ai/workflow_state.json
@@ -1,12 +1,12 @@
 {
   "project": "pvt-phase-simulator",
   "phase": "release-ready",
-  "workflow_status": "IDLE",
+  "workflow_status": "CLAUDE_RUNNING",
   "last_scientific_commit": "cb82425",
   "last_independent_audit_commit": "89fdcbe464b6dec814a1f315959cb9160ecfc57d",
   "work_packages_since_audit": 0,
-  "current_work_package": "final_release_doc_cleanup",
-  "current_risk": "LOW",
+  "current_work_package": "streamlit_full_application",
+  "current_risk": "MEDIUM",
   "audit_required": false,
   "audit_reason": null,
   "blocking_findings": [],
@@ -28,8 +28,8 @@
   ],
   "planned_scope": "Original 21-module Hydrocarbon Phase-Behavior & PVT Simulator",
   "planned_scope_complete": true,
-  "codex_correction_cycles": 0,
-  "claude_reaudit_cycles": 0,
+  "codex_correction_cycles": 1,
+  "claude_reaudit_cycles": 1,
   "claude_cost_usd_this_package": 0.0,
   "claude_cost_unknown_runs": 0,
   "last_error": null,
@@ -118,14 +118,61 @@
       "from": "APPROVED",
       "to": "IDLE",
       "reason": "manually stopped"
+    },
+    {
+      "from": "IDLE",
+      "to": "PLANNING",
+      "reason": "planning streamlit_full_application"
+    },
+    {
+      "from": "PLANNING",
+      "to": "CODEX_RUNNING",
+      "reason": "invoking Codex builder"
+    },
+    {
+      "from": "CODEX_RUNNING",
+      "to": "PLANNING",
+      "reason": "planning streamlit_full_application"
+    },
+    {
+      "from": "PLANNING",
+      "to": "CODEX_RUNNING",
+      "reason": "invoking Codex builder"
+    },
+    {
+      "from": "CODEX_RUNNING",
+      "to": "CODEX_REVIEW",
+      "reason": "Codex returned COMPLETE"
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
+      "to": "LOCAL_VERIFY",
+      "reason": "running local gates"
+    },
+    {
+      "from": "LOCAL_VERIFY",
+      "to": "REAUDIT_PENDING",
+      "reason": "targeted re-audit 1"
+    },
+    {
+      "from": "REAUDIT_PENDING",
+      "to": "CLAUDE_RUNNING",
+      "reason": "invoking Claude auditor"
     }
-  ],
-  "release_state": {
-    "original_modules_1_to_21": "COMPLETE",
-    "final_whole_project_audit": "APPROVED",
-    "final_documentation_findings": "CLOSED (FINAL-D-1, FINAL-D-2 at cb82425)",
-    "blocking_findings": "NONE",
-    "project_release_state": "READY",
-    "optional_extensions": "NOT STARTED - awaiting explicit human scope decision"
-  }
-}
\ No newline at end of file
+  ]
+}
diff --git a/README.md b/README.md
index 662b549..96c94bc 100644
--- a/README.md
+++ b/README.md
@@ -63,6 +63,21 @@ The equations and their implementation mapping are documented in
 The first experimental comparison and its limitations are documented in
 [`docs/EXPERIMENTAL_VALIDATION.md`](docs/EXPERIMENTAL_VALIDATION.md).
 
+## Streamlit application
+
+An optional Streamlit frontend now provides Overview, Phase Envelope, Critical
+Point, Validation, and Diagnostics views for the verified methane, ethane, and
+propane scope. It calls the existing scientific APIs and Module 21 Plotly
+figures without changing the v1.0 engine.
+
+```powershell
+.venv\Scripts\python.exe -m streamlit run app/streamlit_app.py
+```
+
+Input validation, explicit calculation actions, stale-result handling, failure
+semantics, supported views, and limitations are documented in
+[`docs/STREAMLIT_APPLICATION.md`](docs/STREAMLIT_APPLICATION.md).
+
 ## Package structure
 
 ```text
@@ -92,7 +107,7 @@ docs/                            # Scientific documentation
 data/
 â””â”€â”€ component_properties.csv     # Human-review/source-tree property mirror
 notebooks/                       # Exploration scaffold
-app/                             # Reserved Streamlit entry point; no UI yet
+app/                             # Optional Streamlit application surface
 ```
 
 The package includes a `py.typed` marker and exposes inline type information.
@@ -232,7 +247,6 @@ The project does **not** yet implement:
 - experimental authentication and uncertainty quantification beyond the
   verified bibliographic traceability of component-property values
 - engineering unit conversion functions
-- a Streamlit user interface
 
 Near a mixture critical point, the bounded stability trials can collapse to the
 trivial solution and falsely classify a state as stable. In the independently
diff --git a/app/streamlit_app.py b/app/streamlit_app.py
index df55762..3083e46 100644
--- a/app/streamlit_app.py
+++ b/app/streamlit_app.py
@@ -1 +1,565 @@
-"""Reserved Streamlit entry-point module; no user interface is implemented."""
+"""Polished Streamlit frontend for the verified PVT scientific engine."""
+
+from __future__ import annotations
+
+from collections.abc import MutableMapping
+from dataclasses import asdict
+from pathlib import Path
+from typing import Any, Literal, cast
+
+import pandas as pd  # type: ignore[import-untyped]
+import streamlit as st
+
+from app.adapters import (
+    COMPONENT_NAMES,
+    PA_PER_MPA,
+    InputValidationError,
+    ScientificInputs,
+    adapt_critical_result,
+    adapt_flash_result,
+    composition_total,
+    load_module17_records,
+    location_relative_to_envelope,
+    run_validated_flash,
+    status_text,
+    validate_scientific_inputs,
+)
+from app.state import get_result, initialize_session, result_is_stale, store_result
+from app.styles import apply_styles
+from pvt_phase_simulator.eos.critical_point import (
+    CriticalPointScanResult,
+    CriticalPointScanSettings,
+    MixtureCriticalPointResult,
+    scan_mixture_criticality,
+    solve_mixture_critical_point,
+)
+from pvt_phase_simulator.eos.flash import TwoPhaseFlashResult
+from pvt_phase_simulator.eos.phase_envelope import (
+    EnvelopeContinuationSettings,
+    PhaseEnvelopeResult,
+    calculate_phase_envelope,
+)
+from pvt_phase_simulator.plotting import (
+    CompositionDisplay,
+    PressureUnit,
+    plot_critical_solver_conditioning,
+    plot_critical_solver_convergence,
+    plot_critical_solver_path,
+    plot_criticality_map,
+    plot_phase_compositions,
+    plot_phase_envelope,
+    plot_validation_composition_parity,
+    plot_validation_pressure_error,
+    plot_validation_pressure_parity,
+    plot_validation_retrospective_diagnostics,
+    plot_validation_status,
+)
+
+ROOT = Path(__file__).resolve().parents[1]
+PAGES = ("Overview", "Phase Envelope", "Critical Point", "Validation", "Diagnostics")
+
+
+def _state() -> MutableMapping[str, Any]:
+    return cast(MutableMapping[str, Any], st.session_state)
+
+
+def _value(item: object) -> str:
+    return str(item.value if hasattr(item, "value") else item)
+
+
+def _optional(value: float | None, digits: int = 6) -> str:
+    return "Unavailable" if value is None else f"{value:.{digits}g}"
+
+
+def _inputs() -> ScientificInputs | None:
+    st.sidebar.markdown("## Fluid Input")
+    st.sidebar.caption("Verified v1.0 components. Enter composition in mol %.")
+    values = (
+        st.sidebar.number_input("Methane (mol %)", value=50.0, format="%.10g"),
+        st.sidebar.number_input("Ethane (mol %)", value=0.0, format="%.10g"),
+        st.sidebar.number_input("Propane (mol %)", value=50.0, format="%.10g"),
+    )
+    total = composition_total(values)
+    if abs(total - 100.0) <= 1.0e-8 and all(0.0 <= value <= 100.0 for value in values):
+        st.sidebar.success(f"Total: {total:.12g} mol %")
+    else:
+        st.sidebar.error(f"Total: {total:.12g} mol %. Required: 100 mol %.")
+    temperature = st.sidebar.number_input(
+        "Temperature (K)", value=300.0, format="%.10g"
+    )
+    pressure = st.sidebar.number_input("Pressure (MPa)", value=5.0, format="%.10g")
+    try:
+        inputs = validate_scientific_inputs(values, temperature, pressure)
+    except InputValidationError as error:
+        inputs = None
+        st.sidebar.error(str(error))
+    if st.sidebar.button(
+        "RUN FLASH", type="primary", use_container_width=True, disabled=inputs is None
+    ):
+        try:
+            run_inputs, result = run_validated_flash(values, temperature, pressure)
+            store_result(_state(), "flash", result, run_inputs)
+            st.sidebar.success("Structured flash result received.")
+        except (ValueError, ArithmeticError) as error:
+            st.sidebar.error(f"Flash calculation failure: {error}")
+    st.sidebar.caption(
+        "Pressure is converted exactly from MPa to internal Pa. "
+        "Calculations require an explicit action."
+    )
+    return inputs
+
+
+def _navigation() -> str:
+    st.markdown(
+        """
+        <div class="pvt-header">
+          <div class="pvt-kicker">PVT PHASE SIMULATOR</div>
+          <div class="pvt-title">Hydrocarbon phase behavior</div>
+          <p class="pvt-subtitle">Peng-Robinson EOS - Hydrocarbon Phase Behavior</p>
+        </div>
+        """,
+        unsafe_allow_html=True,
+    )
+    return st.radio(
+        "Application view",
+        PAGES,
+        horizontal=True,
+        label_visibility="collapsed",
+        key="navigation",
+    )
+
+
+def _stale(name: str, inputs: ScientificInputs | None) -> None:
+    if result_is_stale(_state(), name, inputs):
+        st.markdown(
+            '<div class="pvt-status pvt-stale"><strong>Stale result.</strong> '
+            "Scientific inputs changed. Run this calculation again before use.</div>",
+            unsafe_allow_html=True,
+        )
+
+
+def _overview(inputs: ScientificInputs | None) -> None:
+    st.header("Overview")
+    raw = get_result(_state(), "flash")
+    if raw is None:
+        st.info("Enter valid conditions and select RUN FLASH to calculate a state.")
+        return
+    result = cast(TwoPhaseFlashResult, raw)
+    view = adapt_flash_result(result)
+    _stale("flash", inputs)
+    st.markdown(
+        f'<div class="pvt-status"><strong>{status_text(view.phase_state)}</strong> | '
+        f"{status_text(view.convergence_status)}</div>",
+        unsafe_allow_html=True,
+    )
+    metrics = st.columns(4)
+    metrics[0].metric("Temperature", f"{view.temperature_k:.8g} K")
+    metrics[1].metric("Pressure", f"{view.pressure_pa / PA_PER_MPA:.15g} MPa")
+    metrics[2].metric("Vapor fraction", _optional(view.vapor_fraction))
+    metrics[3].metric("Liquid fraction", _optional(view.liquid_fraction))
+    z_metrics = st.columns(2)
+    z_metrics[0].metric("Liquid Z", _optional(view.liquid_z))
+    z_metrics[1].metric("Vapor Z", _optional(view.vapor_z))
+    envelope = cast(PhaseEnvelopeResult | None, get_result(_state(), "envelope"))
+    if result_is_stale(_state(), "envelope", inputs):
+        envelope = None
+    st.write(
+        "**Location relative to phase envelope:** "
+        + location_relative_to_envelope(envelope, view.temperature_k, view.pressure_pa)
+    )
+    rows: dict[str, tuple[float, ...]] = {
+        "Feed (mol %)": tuple(
+            100.0 * item.mole_fraction for item in result.feed_mixture.components
+        )
+    }
+    if view.liquid_composition is not None:
+        rows["Liquid (mol %)"] = tuple(
+            100.0 * value for value in view.liquid_composition
+        )
+    if view.vapor_composition is not None:
+        rows["Vapor (mol %)"] = tuple(100.0 * value for value in view.vapor_composition)
+    st.subheader("Composition")
+    st.dataframe(pd.DataFrame(rows, index=COMPONENT_NAMES).T, use_container_width=True)
+    if view.single_phase_z is not None:
+        st.caption(
+            f"Single-phase selected root Z: {view.single_phase_z:.10g}. "
+            "It is not labelled as liquid Z or vapor Z."
+        )
+    with st.expander("Technical details"):
+        st.write("Iterations", view.iteration_count)
+        st.write("Failure or termination", view.failure_reason or "None")
+        if view.final_k_values is not None:
+            st.write("Final K values", view.final_k_values)
+        if view.equilibrium_residuals:
+            st.write("Equilibrium residuals", view.equilibrium_residuals)
+        if view.material_balance_residuals:
+            st.write("Material-balance residuals", view.material_balance_residuals)
+        for label, phase in (
+            ("Liquid", result.liquid_phase),
+            ("Vapor", result.vapor_phase),
+        ):
+            if phase is not None:
+                st.write(
+                    f"{label} log fugacity coefficients",
+                    phase.component_log_fugacity_coefficients,
+                )
+
+
+def _calculate_envelope(inputs: ScientificInputs) -> PhaseEnvelopeResult:
+    settings = EnvelopeContinuationSettings(
+        target_temperature_k=inputs.temperature_k + 50.0,
+        initial_temperature_step_k=5.0,
+        maximum_points=15,
+    )
+    return calculate_phase_envelope(
+        inputs.mixture(),
+        settings,
+        settings,
+        inputs.temperature_k,
+        inputs.temperature_k,
+    )
+
+
+def _envelope(inputs: ScientificInputs | None) -> None:
+    st.header("Phase Envelope")
+    st.write(
+        "Bubble and dew identities are retained. Unavailable points remain "
+        "visibly non-converged."
+    )
+    if st.button("RUN PHASE ENVELOPE", disabled=inputs is None):
+        assert inputs is not None
+        with st.spinner("Tracing independent bubble and dew branches..."):
+            try:
+                store_result(_state(), "envelope", _calculate_envelope(inputs), inputs)
+            except (ValueError, ArithmeticError) as error:
+                st.error(f"Phase-envelope calculation could not start: {error}")
+    raw = get_result(_state(), "envelope")
+    if raw is None:
+        st.info("No envelope result is available. This calculation is optional.")
+        return
+    result = cast(PhaseEnvelopeResult, raw)
+    _stale("envelope", inputs)
+    critical = cast(MixtureCriticalPointResult | None, get_result(_state(), "critical"))
+    if result_is_stale(_state(), "critical", inputs):
+        critical = None
+    st.plotly_chart(
+        plot_phase_envelope(
+            result,
+            pressure_unit=PressureUnit.MPA,
+            critical_point=critical,
+            metadata={"model": "Peng-Robinson EOS; kij=0"},
+        ),
+        use_container_width=True,
+    )
+    columns = st.columns(2)
+    columns[0].metric(
+        "Bubble termination", status_text(result.bubble_branch.termination_reason)
+    )
+    columns[1].metric(
+        "Dew termination", status_text(result.dew_branch.termination_reason)
+    )
+    st.caption(
+        "Pressure or temperature turning points are continuation geometry. "
+        "They are not certified critical points."
+    )
+    component = st.selectbox("Composition component", COMPONENT_NAMES)
+    branch = cast(
+        Literal["bubble", "dew"],
+        st.radio("Composition branch", ("bubble", "dew"), horizontal=True),
+    )
+    try:
+        st.plotly_chart(
+            plot_phase_compositions(
+                result,
+                branch=branch,
+                component_index=COMPONENT_NAMES.index(component),
+                display=CompositionDisplay.MOL_PERCENT,
+                pressure_unit=PressureUnit.MPA,
+            ),
+            use_container_width=True,
+        )
+    except ValueError as error:
+        st.info(f"Phase-composition figure unavailable: {error}")
+
+
+def _calculate_critical(inputs: ScientificInputs) -> MixtureCriticalPointResult:
+    return solve_mixture_critical_point(
+        inputs.mixture(),
+        inputs.temperature_k,
+        inputs.pressure_pa,
+        initialization_source="streamlit_user_conditions",
+    )
+
+
+def _calculate_scan(inputs: ScientificInputs) -> CriticalPointScanResult:
+    return scan_mixture_criticality(
+        inputs.mixture(),
+        CriticalPointScanSettings(
+            0.8 * inputs.temperature_k,
+            1.2 * inputs.temperature_k,
+            0.5 * inputs.pressure_pa,
+            1.5 * inputs.pressure_pa,
+            temperature_points=7,
+            pressure_points=7,
+        ),
+    )
+
+
+def _critical(inputs: ScientificInputs | None) -> None:
+    st.header("Critical Point")
+    st.write(
+        "Certification requires a converged Module 20 result and both critical "
+        "conditions. lambda_min=0 alone is a spinodal condition."
+    )
+    controls = st.columns(2)
+    if controls[0].button("RUN CRITICAL SOLVER", disabled=inputs is None):
+        assert inputs is not None
+        with st.spinner("Solving fixed-composition critical conditions..."):
+            try:
+                store_result(_state(), "critical", _calculate_critical(inputs), inputs)
+            except (ValueError, ArithmeticError) as error:
+                st.error(f"Critical solver could not start: {error}")
+    if controls[1].button("RUN CRITICALITY MAP", disabled=inputs is None):
+        assert inputs is not None
+        with st.spinner("Evaluating the bounded diagnostic map..."):
+            try:
+                store_result(_state(), "critical_scan", _calculate_scan(inputs), inputs)
+            except (ValueError, ArithmeticError) as error:
+                st.error(f"Criticality map could not be evaluated: {error}")
+    raw = get_result(_state(), "critical")
+    if raw is None:
+        st.info("No critical-point solve has been requested.")
+    else:
+        result = cast(MixtureCriticalPointResult, raw)
+        view = adapt_critical_result(result)
+        _stale("critical", inputs)
+        st.markdown(
+            f'<div class="pvt-status"><strong>{status_text(view.status)}</strong> | '
+            + ("Certified critical point" if view.certified else "Not certified")
+            + "</div>",
+            unsafe_allow_html=True,
+        )
+        if view.certified:
+            assert view.temperature_k is not None
+            assert view.pressure_pa is not None
+            metrics = st.columns(4)
+            metrics[0].metric("Tc", f"{view.temperature_k:.13g} K")
+            metrics[1].metric("Pc", f"{view.pressure_pa / PA_PER_MPA:.15g} MPa")
+            metrics[2].metric("lambda_min", _optional(view.lambda_min, 8))
+            metrics[3].metric("C", _optional(view.cubic_coefficient, 8))
+            st.write("Critical direction", view.critical_direction)
+        st.write("Termination", view.termination_reason)
+        st.write("Iterations", view.iterations)
+        if result.history:
+            st.plotly_chart(
+                plot_critical_solver_convergence(result), use_container_width=True
+            )
+            st.plotly_chart(plot_critical_solver_path(result), use_container_width=True)
+        if result.jacobian_condition_history:
+            st.plotly_chart(
+                plot_critical_solver_conditioning(result), use_container_width=True
+            )
+    scan_raw = get_result(_state(), "critical_scan")
+    if scan_raw is not None:
+        _stale("critical_scan", inputs)
+        overlay = cast(MixtureCriticalPointResult | None, raw)
+        if result_is_stale(_state(), "critical", inputs):
+            overlay = None
+        st.plotly_chart(
+            plot_criticality_map(
+                cast(CriticalPointScanResult, scan_raw),
+                pressure_unit=PressureUnit.MPA,
+                critical_point=overlay,
+                metadata={"model": "Peng-Robinson EOS; kij=0"},
+            ),
+            use_container_width=True,
+        )
+
+
+@st.cache_data(show_spinner=False)
+def _records() -> tuple[Any, ...]:
+    return load_module17_records(ROOT)
+
+
+def _validation() -> None:
+    st.header("Validation")
+    st.write(
+        "Module 17 methane/ethane and methane/propane comparisons use kij=0 "
+        "with no fitted binary interaction parameters."
+    )
+    records = _records()
+    direction = cast(
+        Literal["bubble", "dew"],
+        st.radio("Prediction direction", ("bubble", "dew"), horizontal=True),
+    )
+    for figure in (
+        plot_validation_pressure_parity(
+            records, direction=direction, pressure_unit=PressureUnit.MPA
+        ),
+        plot_validation_pressure_error(records, direction=direction),
+        plot_validation_status(records, direction=direction),
+    ):
+        st.plotly_chart(figure, use_container_width=True)
+    try:
+        st.plotly_chart(
+            plot_validation_composition_parity(
+                records,
+                direction=direction,
+                component_index=0,
+                display=CompositionDisplay.MOL_PERCENT,
+            ),
+            use_container_width=True,
+        )
+    except (ValueError, IndexError) as error:
+        st.info(f"Composition parity unavailable: {error}")
+    st.subheader("Retrospective nearest-root diagnostics")
+    st.warning(
+        "Not production prediction. This validation-only view is separate from "
+        "Module 17 production predictions."
+    )
+    try:
+        st.plotly_chart(
+            plot_validation_retrospective_diagnostics(
+                records, pressure_unit=PressureUnit.MPA
+            ),
+            use_container_width=True,
+        )
+    except ValueError as error:
+        st.info(f"Retrospective diagnostics unavailable: {error}")
+    st.caption("Relative pressure error is 100*(P_pred-P_exp)/P_exp.")
+
+
+def _diagnostics(inputs: ScientificInputs | None) -> None:
+    st.header("Diagnostics")
+    st.write(
+        "Public solver evidence is shown without converting structured "
+        "failures into success."
+    )
+    flash_raw = get_result(_state(), "flash")
+    if flash_raw is not None:
+        result = cast(TwoPhaseFlashResult, flash_raw)
+        _stale("flash", inputs)
+        st.subheader("Flash and stability")
+        st.json(
+            {
+                "phase_state": _value(result.phase_state),
+                "convergence": _value(result.convergence_status),
+                "termination_or_failure": result.failure_reason,
+                "iterations": len(result.iteration_history),
+                "stability_status": _value(result.phase_stability.status),
+            }
+        )
+        if result.diagnostics:
+            st.dataframe(
+                pd.DataFrame(
+                    {
+                        "code": item.code,
+                        "severity": _value(item.severity),
+                        "category": _value(item.category),
+                        "message": item.message,
+                        "value": item.value,
+                    }
+                    for item in result.diagnostics
+                ),
+                use_container_width=True,
+            )
+        if result.iteration_history:
+            latest = result.iteration_history[-1]
+            st.write(
+                "Latest iteration evidence",
+                {
+                    "iteration": latest.iteration,
+                    "maximum_log_k_residual": latest.maximum_log_k_residual,
+                    "maximum_fugacity_equilibrium_residual": (
+                        latest.maximum_fugacity_equilibrium_residual
+                    ),
+                    "maximum_material_balance_residual": (
+                        latest.phase_compositions.maximum_material_balance_residual
+                    ),
+                    "Rachford-Rice status": _value(latest.rachford_rice.status),
+                    "Rachford-Rice iterations": latest.rachford_rice.iterations,
+                },
+            )
+        for phase_name, phase in (
+            ("liquid", result.liquid_phase),
+            ("vapor", result.vapor_phase),
+        ):
+            if phase is not None:
+                st.write(
+                    f"{phase_name.title()} public root selection",
+                    asdict(phase.root_selection),
+                )
+    envelope_raw = get_result(_state(), "envelope")
+    if envelope_raw is not None:
+        envelope_result = cast(PhaseEnvelopeResult, envelope_raw)
+        st.subheader("Envelope continuation")
+        st.dataframe(
+            pd.DataFrame(
+                {
+                    "branch": branch.branch_kind.value,
+                    "accepted_points": len(branch.points),
+                    "rejected_attempts": len(branch.rejected_attempts),
+                    "termination": branch.termination_reason.value,
+                    "message": branch.termination_message,
+                }
+                for branch in (
+                    envelope_result.bubble_branch,
+                    envelope_result.dew_branch,
+                )
+            ),
+            use_container_width=True,
+        )
+        st.caption("Turning indicators are continuation geometry, not critical points.")
+    critical_raw = get_result(_state(), "critical")
+    if critical_raw is not None:
+        critical_result = cast(MixtureCriticalPointResult, critical_raw)
+        st.subheader("Critical solver")
+        st.json(
+            {
+                "status": critical_result.status.value,
+                "termination": critical_result.termination_reason,
+                "iterations": critical_result.iterations,
+                "accepted_steps": critical_result.accepted_steps,
+                "rejected_steps": critical_result.rejected_steps,
+                "function_evaluations": critical_result.function_evaluations,
+                "jacobian_condition_history": (
+                    critical_result.jacobian_condition_history
+                ),
+                "certified": adapt_critical_result(critical_result).certified,
+            }
+        )
+        if critical_result.criticality_result is not None:
+            st.write(
+                "Final public criticality result",
+                asdict(critical_result.criticality_result),
+            )
+    if flash_raw is None and envelope_raw is None and critical_raw is None:
+        st.info("Run a calculation to populate public diagnostics.")
+
+
+def main() -> None:
+    """Render the application through public scientific APIs only."""
+
+    st.set_page_config(
+        page_title="PVT Phase Simulator",
+        layout="wide",
+        initial_sidebar_state="expanded",
+    )
+    apply_styles()
+    initialize_session(_state())
+    inputs = _inputs()
+    page = _navigation()
+    if page == "Overview":
+        _overview(inputs)
+    elif page == "Phase Envelope":
+        _envelope(inputs)
+    elif page == "Critical Point":
+        _critical(inputs)
+    elif page == "Validation":
+        _validation()
+    else:
+        _diagnostics(inputs)
+
+
+if __name__ == "__main__":
+    main()

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
