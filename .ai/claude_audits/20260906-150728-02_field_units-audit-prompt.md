# Independent audit: 02_field_units

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
- Name: 02_field_units
- Declared risk: MEDIUM
- Objective: Let users work in practical field units while the engine stays internally SI. Support pressure in Pa, MPa, bar and psi, and temperature in K, degrees Celsius and degrees Fahrenheit. Every conversion happens at the application boundary, once, on the way in and on the way out. Exports state their units explicitly.

## Scientific invariants claimed to hold
  - The scientific engine is frozen: no file under src/pvt_phase_simulator/, data/, docs/validation/ or tests/golden_master/ may change.
  - No thermodynamic relation may be implemented, restated or approximated in the application layer.
  - Unavailable quantities are reported as unavailable and never fabricated or interpolated.
  - Structured failures remain failures; only CriticalPointStatus.CONVERGED is a certified critical point.

## Repository state
- Branch: `app-v1.2-engineering`
- HEAD: `cd908da958d3a616a22c58735ae3f1b4d2c6bb94`
- Base for this change: `cd908da958d3a616a22c58735ae3f1b4d2c6bb94`

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
Changed files: ['docs/STREAMLIT_APPLICATION.md', 'src/pvt_phase_simulator_ui/adapters.py', 'src/pvt_phase_simulator_ui/app.py', 'src/pvt_phase_simulator_ui/context.py', 'src/pvt_phase_simulator_ui/exports.py', 'src/pvt_phase_simulator_ui/model_scope.py', 'src/pvt_phase_simulator_ui/state.py', 'src/pvt_phase_simulator_ui/sweeps.py', 'src/pvt_phase_simulator_ui/units.py', 'src/pvt_phase_simulator_ui/views.py', 'tests/test_app_adapters.py', 'tests/test_app_streamlit.py', 'tests/test_app_sweeps.py']

## Builder's own report — treat as an unverified claim
```
Field-units package is complete. I preserved the existing implementation and centralized the final legacy pressure conversion in `units.py`. Protected artifacts remain unchanged; no Streamlit server was started.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "pytest: 1255 passed in 648.64s (TEMP/TMP redirected to a workspace-local directory and pytest cache disabled due sandbox ACLs); ruff check: all checks passed; ruff format --check: 203 files already formatted; mypy: success, no issues in 45 source files; compileall: exit 0",
  "files_changed": [
    "docs/STREAMLIT_APPLICATION.md",
    "src/pvt_phase_simulator_ui/adapters.py",
    "src/pvt_phase_simulator_ui/app.py",
    "src/pvt_phase_simulator_ui/context.py",
    "src/pvt_phase_simulator_ui/exports.py",
    "src/pvt_phase_simulator_ui/model_scope.py",
    "src/pvt_phase_simulator_ui/state.py",
    "src/pvt_phase_simulator_ui/sweeps.py",
    "src/pvt_phase_simulator_ui/units.py",
    "src/pvt_phase_simulator_ui/views.py",
    "tests/test_app_adapters.py",
    "tests/test_app_streamlit.py",
    "tests/test_app_sweeps.py"
  ],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>
```

## Diff stat
```
 .ai/work_packages/01_model_and_limitations.json |   2 +-
 .ai/workflow_state.json                         | 105 ++++++--
 docs/STREAMLIT_APPLICATION.md                   |  51 ++--
 src/pvt_phase_simulator_ui/adapters.py          |  56 +++--
 src/pvt_phase_simulator_ui/app.py               |  61 +++--
 src/pvt_phase_simulator_ui/context.py           |  19 ++
 src/pvt_phase_simulator_ui/exports.py           | 129 ++++++++--
 src/pvt_phase_simulator_ui/model_scope.py       |  20 +-
 src/pvt_phase_simulator_ui/state.py             |  57 ++++-
 src/pvt_phase_simulator_ui/sweeps.py            | 122 ++++++----
 src/pvt_phase_simulator_ui/views.py             | 304 ++++++++++++++++++------
 tests/test_app_adapters.py                      | 107 ++++++++-
 tests/test_app_streamlit.py                     |  44 ++++
 tests/test_app_sweeps.py                        |  84 ++++++-
 14 files changed, 936 insertions(+), 225 deletions(-)

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
diff --git a/.ai/workflow_state.json b/.ai/workflow_state.json
index a6e5b0a..c48083e 100644
--- a/.ai/workflow_state.json
+++ b/.ai/workflow_state.json
@@ -3,12 +3,12 @@
   "phase": "post-v1.0-extensions",
   "workflow_status": "CLAUDE_RUNNING",
   "last_scientific_commit": "d2a0a74",
-  "last_independent_audit_commit": "c29ae4961543e74a271e8e2e54de22852892cf00",
+  "last_independent_audit_commit": "cd908da958d3a616a22c58735ae3f1b4d2c6bb94",
   "work_packages_since_audit": 0,
-  "current_work_package": "01_model_and_limitations",
-  "current_risk": "LOW",
-  "audit_required": false,
-  "audit_reason": null,
+  "current_work_package": "02_field_units",
+  "current_risk": "MEDIUM",
+  "audit_required": true,
+  "audit_reason": "package audit_policy=IMMEDIATE",
   "blocking_findings": [],
   "safe_defer_findings": [
     {
@@ -61,31 +61,46 @@
   "workflow_id": "c3d365745ae6",
   "builder": "codex",
   "reviewer": "claude",
-  "last_completed_stage": "audited",
+  "last_completed_stage": "verified",
   "verification_status": "passed",
-  "base_commit": "46b1d8e75c60d76b5e7d920ef30f6c1f14da051d",
+  "base_commit": "cd908da958d3a616a22c58735ae3f1b4d2c6bb94",
   "resulting_commit": null,
-  "builder_report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260906-004904-01_model_and_limitations-codex-report.md",
+  "builder_report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260906-142606-02_field_units-codex-report.md",
   "builder_evidence": {
     "builder": "codex",
-    "package": "01_model_and_limitations",
+    "package": "02_field_units",
     "workflow_id": "c3d365745ae6",
-    "report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260906-004904-01_model_and_limitations-codex-report.md",
-    "report_sha256": "aba55903df96e2d4cb704675c21b9a85475bea40f07260b49672cb6766daff05",
+    "report_path": "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260906-142606-02_field_units-codex-report.md",
+    "report_sha256": "5523eda13424551da600c5f6ed143d9a468e7bfbf9939bbf97526728a1848452",
     "revision": 1,
     "kind": "build"
   },
-  "tree_fingerprint": "26f7c0227453f1f2851c35ee7897ac909e05b24fb1876f0b9e11f4226cc01a00",
+  "tree_fingerprint": "52e5ac8365e0083fcd47cad10967b34e7d65e3e7c67eb26005b6ca5839e37638",
   "revisions": [
     {
-      "package": "01_model_and_limitations",
+      "package": "02_field_units",
       "revision": 1,
       "author": "codex",
       "kind": "build",
-      "at": 1788646855.9640622
+      "at": 1788695756.3398404
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
     }
   ],
-  "role_transitions": [],
   "history": [
     {
       "from": "IDLE",
@@ -536,6 +551,66 @@
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
     }
   ]
 }
diff --git a/docs/STREAMLIT_APPLICATION.md b/docs/STREAMLIT_APPLICATION.md
index cbeb30a..73647c2 100644
--- a/docs/STREAMLIT_APPLICATION.md
+++ b/docs/STREAMLIT_APPLICATION.md
@@ -42,8 +42,9 @@ package:
 - `src/pvt_phase_simulator_ui/app.py` owns navigation and submitted inputs.
 - `src/pvt_phase_simulator_ui/pages/` contains the six page scripts.
 - `src/pvt_phase_simulator_ui/adapters.py` validates inputs, converts boundary
-  units, and selects public
-  result fields without changing them.
+  units to K and Pa, and selects public result fields without changing them.
+- `src/pvt_phase_simulator_ui/units.py` is the single application-boundary
+  implementation for pressure and temperature unit conversion.
 - `src/pvt_phase_simulator_ui/state.py` associates each result with a scientific
   input signature.
 - `src/pvt_phase_simulator_ui/sweeps.py` chooses swept abscissae and calls the
@@ -74,22 +75,32 @@ are available in the panel's **Recorded provenance** expander. Opening the panel
 does not run a scientific calculation.
 
 The persistent Fluid inputs form supports the verified v1.0 Methane, Ethane,
-and Propane components. Composition is entered in mol %, temperature in K, and
-pressure in MPa. On submission, the panel shows the composition total and rejects
-nonfinite, negative, above-100, zero-total, and materially non-100% values. It
-does not silently normalize invalid composition.
+and Propane components. Composition is entered in mol %. Temperature can be
+entered and displayed in K, °C, or °F; pressure can be entered and displayed in
+Pa, MPa, bar, or psi. Changing a unit converts the editable value and preserves
+the physical state; it does not run a calculation or make a current scientific
+result stale. On submission, the panel shows the composition total and rejects
+nonfinite, negative, above-100, zero-total, and materially non-100% composition.
+It rejects pressure at or below zero and temperature at or below absolute zero
+in every supported unit. It does not silently normalize invalid composition.
 
 The native example selector can fill the form with the default
 two-phase-oriented case, the known 50/50 methane/propane single-phase case at
 300 K and 20 MPa, or the audited 50/50 methane/propane critical-solver seed near
-321.5829183194 K and 8.53444323606381 MPa. Selection changes input values only;
-it never submits the form or starts a scientific calculation. Every populated
-value remains editable and passes through the same validation and conversion
-boundary when the user explicitly submits it.
-
-Valid composition is divided by 100 exactly for mole fractions. Valid pressure
-is multiplied by `1e6` exactly before it reaches an SI-pressure API, and public
-Pa results are divided by `1e6` for MPa display.
+321.5829183194 K and 8.53444323606381 MPa. Examples are stored as documented SI
+states and shown in the currently selected field units. Selection changes input
+values only; it never submits the form or starts a scientific calculation. Every
+populated value remains editable and passes through the same validation and
+conversion boundary when the user explicitly submits it.
+
+Valid composition is divided by 100 exactly for mole fractions. The selected
+temperature and pressure units are converted once to K and Pa at submission.
+Only the canonical K/Pa state is passed to the scientific APIs and stored in a
+result signature. Public K/Pa result values are converted once at presentation
+to the selected units. Unit-only changes therefore redraw existing results
+without recomputing or changing their scientific identity. The pressure factors
+are 1 Pa/Pa, 1,000,000 Pa/MPa, 100,000 Pa/bar, and 6,894.757293168 Pa/psi;
+temperature uses the standard 273.15 and 459.67 offsets.
 
 - **Overview:** entered state, phase and convergence statuses, available phase
   fractions and Z factors, source-provided compositions, and envelope location.
@@ -100,15 +111,16 @@ Pa results are divided by `1e6` for MPa display.
   maps, including Tc, Pc, lambda_min, C, direction, convergence, and conditioning.
 - **Engineering Sweeps:** bounded pressure or temperature sweeps at the other
   submitted variable, with vapor-fraction and Z-factor curves, a phase-state
-  table, a progress indicator, and CSV/JSON export. Each point is one call into
+  table, a progress indicator, and CSV/JSON export in the selected units. Each point is one call into
   the existing verified flash and stability API; nothing is re-derived. A point
   that fails is reported as **FAILED** and breaks the plotted line rather than
   being interpolated across: the abscissa is kept and its value left empty, so
   the curve shows a real gap. A quantity a point never supplied, such as a vapor
   fraction at a single-phase state, breaks the line the same way. Failed
   abscissae are additionally marked on both charts. Displayed values are rounded
-  for reading; exports carry full precision. The default is 21 points, bounded
-  to 60.
+  for reading; exports carry full precision. Each exported state includes both
+  selected-unit values with explicit unit fields and canonical `temperature_k`
+  and `pressure_pa` values. The default is 21 points, bounded to 60.
 - **Validation:** Module 17 artifacts rendered through Module 21 parity, error,
   composition, status, and retrospective figures.
 - **Diagnostics:** public status, termination, iteration, residual, stability,
@@ -127,6 +139,11 @@ invalid current input marks the prior result stale until explicitly recalculated
 Stale results remain visible with a warning, but downloads are unavailable until
 the changed inputs have a current calculated result.
 
+Current-case and sweep JSON exports use schema version 1.1.0. Their metadata
+states the engine units (K and Pa) and selected presentation units. CSV headers
+use explicit temperature and pressure unit columns and retain canonical
+`temperature_k` and `pressure_pa` columns for unambiguous downstream use.
+
 Structured statuses such as `LINE_SEARCH_FAILED`, `JACOBIAN_FAILED`,
 `NOT_FOUND`, and `BRANCH_LOST` remain failures or information. Only
 `CriticalPointStatus.CONVERGED` is a certified critical point. `lambda_min=0`
diff --git a/src/pvt_phase_simulator_ui/adapters.py b/src/pvt_phase_simulator_ui/adapters.py
index 6c3c167..de4fac0 100644
--- a/src/pvt_phase_simulator_ui/adapters.py
+++ b/src/pvt_phase_simulator_ui/adapters.py
@@ -29,12 +29,18 @@ from pvt_phase_simulator.plotting import (
     ValidationPlotRecord,
     load_validation_plot_records,
 )
+from pvt_phase_simulator_ui.units import (
+    PressureUnit,
+    TemperatureUnit,
+    pressure_from_pa,
+    pressure_to_pa,
+    temperature_to_k,
+)
 
 COMPONENTS: Final = (METHANE, ETHANE, PROPANE)
 COMPONENT_NAMES: Final = tuple(component.name for component in COMPONENTS)
 COMPOSITION_TOTAL_MOL_PERCENT: Final = 100.0
 COMPOSITION_TOLERANCE_MOL_PERCENT: Final = 1.0e-8
-PA_PER_MPA: Final = 1.0e6
 
 
 class InputValidationError(ValueError):
@@ -48,9 +54,14 @@ class ScientificInputs:
     composition_mol_percent: tuple[float, float, float]
     mole_fractions: tuple[float, float, float]
     temperature_k: float
-    pressure_mpa: float
     pressure_pa: float
 
+    @property
+    def pressure_mpa(self) -> float:
+        """Compatibility presentation of the canonical pressure in MPa."""
+
+        return pressure_from_pa(self.pressure_pa, PressureUnit.MPA)
+
     @property
     def signature(self) -> tuple[tuple[float, float, float], float, float]:
         return self.mole_fractions, self.temperature_k, self.pressure_pa
@@ -74,10 +85,13 @@ def composition_total(values: Sequence[float]) -> float:
 
 def validate_scientific_inputs(
     composition_mol_percent: Sequence[float],
-    temperature_k: float,
-    pressure_mpa: float,
+    temperature: float,
+    pressure: float,
+    *,
+    temperature_unit: TemperatureUnit | str = TemperatureUnit.KELVIN,
+    pressure_unit: PressureUnit | str = PressureUnit.MPA,
 ) -> ScientificInputs:
-    """Validate first, then perform the two exact boundary conversions once."""
+    """Validate and convert user-facing values to the engine's K/Pa contract."""
 
     if len(composition_mol_percent) != len(COMPONENTS):
         raise InputValidationError("Exactly Methane, Ethane, and Propane are required.")
@@ -95,19 +109,21 @@ def validate_scientific_inputs(
         raise InputValidationError(
             "Composition must total 100 mol %. Values are not automatically normalized."
         )
-    temperature = float(temperature_k)
-    pressure = float(pressure_mpa)
-    if not isfinite(temperature) or temperature <= 0.0:
-        raise InputValidationError("Temperature must be positive and finite.")
-    if not isfinite(pressure) or pressure <= 0.0:
-        raise InputValidationError("Pressure must be positive and finite.")
+    try:
+        temperature_k = temperature_to_k(temperature, temperature_unit)
+        pressure_pa = pressure_to_pa(pressure, pressure_unit)
+    except ValueError as error:
+        raise InputValidationError(str(error)) from error
+    if temperature_k <= 0.0:
+        raise InputValidationError("Temperature must be above absolute zero.")
+    if pressure_pa <= 0.0:
+        raise InputValidationError("Pressure must be positive.")
     fractions = tuple(value / 100.0 for value in values)
     return ScientificInputs(
         (values[0], values[1], values[2]),
         (fractions[0], fractions[1], fractions[2]),
-        temperature,
-        pressure,
-        pressure * PA_PER_MPA,
+        temperature_k,
+        pressure_pa,
     )
 
 
@@ -116,13 +132,19 @@ FlashCallable = Callable[[FluidMixture, float, float], TwoPhaseFlashResult]
 
 def run_validated_flash(
     composition_mol_percent: Sequence[float],
-    temperature_k: float,
-    pressure_mpa: float,
+    temperature: float,
+    pressure: float,
     *,
+    temperature_unit: TemperatureUnit | str = TemperatureUnit.KELVIN,
+    pressure_unit: PressureUnit | str = PressureUnit.MPA,
     flash_api: FlashCallable = calculate_two_phase_flash,
 ) -> tuple[ScientificInputs, TwoPhaseFlashResult]:
     inputs = validate_scientific_inputs(
-        composition_mol_percent, temperature_k, pressure_mpa
+        composition_mol_percent,
+        temperature,
+        pressure,
+        temperature_unit=temperature_unit,
+        pressure_unit=pressure_unit,
     )
     result = flash_api(inputs.mixture(), inputs.temperature_k, inputs.pressure_pa)
     return inputs, result
diff --git a/src/pvt_phase_simulator_ui/app.py b/src/pvt_phase_simulator_ui/app.py
index a2a32be..12e41fd 100644
--- a/src/pvt_phase_simulator_ui/app.py
+++ b/src/pvt_phase_simulator_ui/app.py
@@ -6,11 +6,11 @@ from pathlib import Path
 
 import streamlit as st
 
+from pvt_phase_simulator.eos.flash import calculate_two_phase_flash
 from pvt_phase_simulator_ui.adapters import (
     InputValidationError,
     ScientificInputs,
     composition_total,
-    run_validated_flash,
     validate_scientific_inputs,
 )
 from pvt_phase_simulator_ui.context import session
@@ -19,7 +19,9 @@ from pvt_phase_simulator_ui.state import (
     apply_selected_input_example,
     initialize_session,
     store_result,
+    synchronize_unit_inputs,
 )
+from pvt_phase_simulator_ui.units import PRESSURE_UNITS, TEMPERATURE_UNITS
 
 PAGES_DIRECTORY = Path(__file__).with_name("pages")
 
@@ -28,17 +30,32 @@ PAGES_DIRECTORY = Path(__file__).with_name("pages")
 def _cached_flash(inputs: ScientificInputs) -> object:
     """Cache an unchanged submitted case without changing its calculations."""
 
-    _, result = run_validated_flash(
-        inputs.composition_mol_percent,
+    return calculate_two_phase_flash(
+        inputs.mixture(),
         inputs.temperature_k,
-        inputs.pressure_mpa,
+        inputs.pressure_pa,
     )
-    return result
 
 
 def _input_form() -> tuple[ScientificInputs | None, bool]:
     with st.sidebar:
         st.subheader("Fluid inputs")
+        st.caption("Display and entry units")
+        st.segmented_control(
+            "Temperature unit",
+            options=[unit.value for unit in TEMPERATURE_UNITS],
+            key="temperature_unit",
+            on_change=synchronize_unit_inputs,
+            args=(session(),),
+        )
+        st.segmented_control(
+            "Pressure unit",
+            options=[unit.value for unit in PRESSURE_UNITS],
+            key="pressure_unit",
+            on_change=synchronize_unit_inputs,
+            args=(session(),),
+        )
+        synchronize_unit_inputs(session())
         st.selectbox(
             "Example case",
             options=[example.label for example in INPUT_EXAMPLES],
@@ -59,7 +76,12 @@ def _input_form() -> tuple[ScientificInputs | None, bool]:
             None,
         )
         st.caption("Examples fill the inputs only; they do not run a calculation.")
-        st.caption("Verified components · precise mol %, K, and MPa entry")
+        temperature_unit = str(session()["temperature_unit"])
+        pressure_unit = str(session()["pressure_unit"])
+        st.caption(
+            "Verified components · precise mol % entry · "
+            f"{temperature_unit} and {pressure_unit} field units"
+        )
         with st.form("scientific_inputs", border=True):
             methane = st.number_input(
                 "Methane (mol %)", format="%.15g", key="methane_pct"
@@ -69,10 +91,14 @@ def _input_form() -> tuple[ScientificInputs | None, bool]:
                 "Propane (mol %)", format="%.15g", key="propane_pct"
             )
             temperature = st.number_input(
-                "Temperature (K)", format="%.15g", key="temperature_k"
+                f"Temperature ({temperature_unit})",
+                format="%.17g",
+                key="temperature_value",
             )
             pressure = st.number_input(
-                "Pressure (MPa)", format="%.15g", key="pressure_mpa"
+                f"Pressure ({pressure_unit})",
+                format="%.17g",
+                key="pressure_value",
             )
             if selected_example is None:
                 values = (methane, ethane, propane)
@@ -82,10 +108,16 @@ def _input_form() -> tuple[ScientificInputs | None, bool]:
                     selected_example.ethane_pct,
                     selected_example.propane_pct,
                 )
-                temperature = selected_example.temperature_k
-                pressure = selected_example.pressure_mpa
+                temperature = float(session()["temperature_value"])
+                pressure = float(session()["pressure_value"])
             try:
-                validated = validate_scientific_inputs(values, temperature, pressure)
+                validated = validate_scientific_inputs(
+                    values,
+                    temperature,
+                    pressure,
+                    temperature_unit=temperature_unit,
+                    pressure_unit=pressure_unit,
+                )
                 validation_error = None
             except InputValidationError as error:
                 validated = None
@@ -104,14 +136,15 @@ def _input_form() -> tuple[ScientificInputs | None, bool]:
                 width="stretch",
                 icon=":material/play_arrow:",
             )
-        st.caption(
-            "A submit converts mol % to fractions and MPa to internal Pa exactly once."
-        )
+        st.caption("A submit converts field values to internal K and Pa exactly once.")
     session()["rendered_input_example"] = session().get("input_example")
     session()["current_inputs"] = validated
     if submitted:
         session()["submitted_inputs"] = validated
         session()["input_error"] = validation_error
+        if validated is not None:
+            session()["temperature_k"] = validated.temperature_k
+            session()["pressure_mpa"] = validated.pressure_mpa
     return validated, bool(submitted and validated is not None)
 
 
diff --git a/src/pvt_phase_simulator_ui/context.py b/src/pvt_phase_simulator_ui/context.py
index 09a7a0b..eb16765 100644
--- a/src/pvt_phase_simulator_ui/context.py
+++ b/src/pvt_phase_simulator_ui/context.py
@@ -8,6 +8,12 @@ from typing import Any, cast
 import streamlit as st
 
 from pvt_phase_simulator_ui.adapters import ScientificInputs
+from pvt_phase_simulator_ui.units import (
+    DEFAULT_UNITS,
+    PressureUnit,
+    TemperatureUnit,
+    UnitPreferences,
+)
 
 
 def session() -> MutableMapping[str, Any]:
@@ -17,3 +23,16 @@ def session() -> MutableMapping[str, Any]:
 def current_inputs() -> ScientificInputs | None:
     value = st.session_state.get("current_inputs")
     return cast(ScientificInputs | None, value)
+
+
+def unit_preferences() -> UnitPreferences:
+    """Return the current presentation units without changing scientific state."""
+
+    return UnitPreferences(
+        temperature=TemperatureUnit(
+            str(st.session_state.get("temperature_unit", DEFAULT_UNITS.temperature))
+        ),
+        pressure=PressureUnit(
+            str(st.session_state.get("pressure_unit", DEFAULT_UNITS.pressure))
+        ),
+    )
diff --git a/src/pvt_phase_simulator_ui/exports.py b/src/pvt_phase_simulator_ui/exports.py
index 895c392..537a78d 100644
--- a/src/pvt_phase_simulator_ui/exports.py
+++ b/src/pvt_phase_simulator_ui/exports.py
@@ -22,9 +22,15 @@ from pvt_phase_simulator_ui.adapters import (
     adapt_flash_result,
 )
 from pvt_phase_simulator_ui.sweeps import SweepPoint, SweepResult
+from pvt_phase_simulator_ui.units import (
+    DEFAULT_UNITS,
+    UnitPreferences,
+    pressure_from_pa,
+    temperature_from_k,
+)
 
 EXPORT_SCHEMA_NAME = "pvt-phase-simulator-current-case"
-EXPORT_SCHEMA_VERSION = "1.0.0"
+EXPORT_SCHEMA_VERSION = "1.1.0"
 
 
 def _enum_value(value: object) -> str:
@@ -115,12 +121,26 @@ def _flash_export(result: TwoPhaseFlashResult) -> dict[str, object]:
     }
 
 
-def _envelope_point_export(point: PhaseEnvelopePoint) -> dict[str, object]:
+def _display_state(
+    temperature_k: float, pressure_pa: float, units: UnitPreferences
+) -> dict[str, object]:
+    return {
+        "temperature": temperature_from_k(temperature_k, units.temperature),
+        "temperature_unit": units.temperature.value,
+        "pressure": pressure_from_pa(pressure_pa, units.pressure),
+        "pressure_unit": units.pressure.value,
+        "temperature_k": temperature_k,
+        "pressure_pa": pressure_pa,
+    }
+
+
+def _envelope_point_export(
+    point: PhaseEnvelopePoint, units: UnitPreferences
+) -> dict[str, object]:
     saturation = point.saturation_result
     return {
         "status": _enum_value(point.status),
-        "temperature_k": point.temperature_k,
-        "pressure_pa": point.pressure_pa,
+        **_display_state(point.temperature_k, point.pressure_pa, units),
         "parent_composition": saturation.parent_composition,
         "incipient_composition": saturation.incipient_composition,
         "k_values": saturation.k_values,
@@ -134,7 +154,7 @@ def _envelope_point_export(point: PhaseEnvelopePoint) -> dict[str, object]:
 
 
 def _envelope_branch_export(
-    branch: PhaseEnvelopeBranchResult,
+    branch: PhaseEnvelopeBranchResult, units: UnitPreferences
 ) -> dict[str, object]:
     return {
         "branch_kind": _enum_value(branch.branch_kind),
@@ -142,21 +162,35 @@ def _envelope_branch_export(
         "termination_message": branch.termination_message,
         "accepted_point_count": len(branch.points),
         "rejected_attempt_count": len(branch.rejected_attempts),
-        "points": [_envelope_point_export(point) for point in branch.points],
+        "points": [_envelope_point_export(point, units) for point in branch.points],
     }
 
 
-def _envelope_export(result: PhaseEnvelopeResult) -> dict[str, object]:
+def _envelope_export(
+    result: PhaseEnvelopeResult, units: UnitPreferences
+) -> dict[str, object]:
     return {
         "calculation_status": "calculated",
-        "bubble_branch": _envelope_branch_export(result.bubble_branch),
-        "dew_branch": _envelope_branch_export(result.dew_branch),
+        "bubble_branch": _envelope_branch_export(result.bubble_branch, units),
+        "dew_branch": _envelope_branch_export(result.dew_branch, units),
     }
 
 
-def _critical_export(result: MixtureCriticalPointResult) -> dict[str, object]:
+def _critical_export(
+    result: MixtureCriticalPointResult, units: UnitPreferences
+) -> dict[str, object]:
     view = adapt_critical_result(result)
     reason = "No certified critical value is available from this production result."
+    display_temperature = (
+        None
+        if view.temperature_k is None
+        else temperature_from_k(view.temperature_k, units.temperature)
+    )
+    display_pressure = (
+        None
+        if view.pressure_pa is None
+        else pressure_from_pa(view.pressure_pa, units.pressure)
+    )
     return {
         "calculation_status": "calculated",
         "solver_status": _enum_value(view.status),
@@ -169,6 +203,14 @@ def _critical_export(result: MixtureCriticalPointResult) -> dict[str, object]:
         "pressure_pa": _optional_result_value(
             view.pressure_pa, not_applicable=False, reason=reason
         ),
+        "temperature": _optional_result_value(
+            display_temperature, not_applicable=False, reason=reason
+        ),
+        "temperature_unit": units.temperature.value,
+        "pressure": _optional_result_value(
+            display_pressure, not_applicable=False, reason=reason
+        ),
+        "pressure_unit": units.pressure.value,
         "lambda_min": _optional_result_value(
             result.lambda_min, not_applicable=False, reason=reason
         ),
@@ -190,6 +232,7 @@ def build_export_document(
     flash_result: TwoPhaseFlashResult | None = None,
     envelope_result: PhaseEnvelopeResult | None = None,
     critical_result: MixtureCriticalPointResult | None = None,
+    units: UnitPreferences = DEFAULT_UNITS,
 ) -> dict[str, object]:
     """Build an export solely from submitted inputs and already-held results."""
 
@@ -214,6 +257,11 @@ def build_export_document(
         "metadata": {
             "eos": "Peng-Robinson",
             "unit_system": "SI",
+            "engine_units": {"temperature": "K", "pressure": "Pa"},
+            "presentation_units": {
+                "temperature": units.temperature.value,
+                "pressure": units.pressure.value,
+            },
             "binary_interaction_assumption": "kij = 0",
             "verified_component_scope": list(COMPONENT_NAMES),
             "export_timestamp": {
@@ -222,8 +270,7 @@ def build_export_document(
             },
         },
         "case": {
-            "temperature_k": inputs.temperature_k,
-            "pressure_pa": inputs.pressure_pa,
+            **_display_state(inputs.temperature_k, inputs.pressure_pa, units),
             "pressure_mpa": inputs.pressure_mpa,
             "model": "Peng-Robinson",
             "binary_interaction_assumption": "kij = 0",
@@ -238,12 +285,12 @@ def build_export_document(
             "phase_envelope": (
                 {"calculation_status": "not_calculated"}
                 if envelope_result is None
-                else _envelope_export(envelope_result)
+                else _envelope_export(envelope_result, units)
             ),
             "critical_point": (
                 {"calculation_status": "not_calculated"}
                 if critical_result is None
-                else _critical_export(critical_result)
+                else _critical_export(critical_result, units)
             ),
         },
     }
@@ -304,7 +351,7 @@ def export_csv_bytes(document: Mapping[str, object]) -> bytes:
 
 
 SWEEP_EXPORT_SCHEMA_NAME = "pvt-phase-simulator-engineering-sweep"
-SWEEP_EXPORT_SCHEMA_VERSION = "1.0.0"
+SWEEP_EXPORT_SCHEMA_VERSION = "1.1.0"
 
 #: Ordered CSV columns for the tabular sweep export. Engineers read a sweep as a
 #: table of states, so this export is one row per point rather than the
@@ -312,6 +359,10 @@ SWEEP_EXPORT_SCHEMA_VERSION = "1.0.0"
 SWEEP_CSV_COLUMNS: Final = (
     "index",
     "status",
+    "temperature",
+    "temperature_unit",
+    "pressure",
+    "pressure_unit",
     "temperature_k",
     "pressure_mpa",
     "pressure_pa",
@@ -329,7 +380,7 @@ SWEEP_CSV_COLUMNS: Final = (
 )
 
 
-def _sweep_point_export(point: SweepPoint) -> dict[str, object]:
+def _sweep_point_export(point: SweepPoint, units: UnitPreferences) -> dict[str, object]:
     """Export one point without inventing a value the result did not supply."""
 
     failed = point.status == "failed"
@@ -348,9 +399,8 @@ def _sweep_point_export(point: SweepPoint) -> dict[str, object]:
     return {
         "index": point.index,
         "status": point.status,
-        "temperature_k": point.temperature_k,
+        **_display_state(point.temperature_k, point.pressure_pa, units),
         "pressure_mpa": point.pressure_mpa,
-        "pressure_pa": point.pressure_pa,
         "phase_state": _optional_result_value(
             point.phase_state, not_applicable=failed, reason=failed_reason
         ),
@@ -377,10 +427,15 @@ def _sweep_point_export(point: SweepPoint) -> dict[str, object]:
     }
 
 
-def build_sweep_export_document(result: SweepResult) -> dict[str, object]:
+def build_sweep_export_document(
+    result: SweepResult, units: UnitPreferences | None = None
+) -> dict[str, object]:
     """Build a sweep export from an already-computed sweep, calculating nothing."""
 
     request = result.request
+    selected_units = units or UnitPreferences(
+        temperature=request.temperature_unit, pressure=request.pressure_unit
+    )
     components = [
         {"name": name, "composition_mol_percent": mol_percent}
         for name, mol_percent in zip(
@@ -395,6 +450,11 @@ def build_sweep_export_document(result: SweepResult) -> dict[str, object]:
         "metadata": {
             "eos": "Peng-Robinson",
             "unit_system": "SI",
+            "engine_units": {"temperature": "K", "pressure": "Pa"},
+            "presentation_units": {
+                "temperature": selected_units.temperature.value,
+                "pressure": selected_units.pressure.value,
+            },
             "binary_interaction_assumption": "kij = 0",
             "verified_component_scope": list(COMPONENT_NAMES),
             "export_timestamp": {
@@ -404,10 +464,17 @@ def build_sweep_export_document(result: SweepResult) -> dict[str, object]:
         },
         "request": {
             "kind": request.kind,
-            "fixed_temperature_k": request.fixed_temperature_k,
-            "fixed_pressure_mpa": request.fixed_pressure_mpa,
+            "fixed_temperature": request.fixed_temperature,
+            "fixed_temperature_unit": request.temperature_unit.value,
+            "fixed_pressure": request.fixed_pressure,
+            "fixed_pressure_unit": request.pressure_unit.value,
             "start": request.start,
             "end": request.end,
+            "sweep_unit": (
+                request.pressure_unit.value
+                if request.kind == "pressure"
+                else request.temperature_unit.value
+            ),
             "points": request.points,
             "components": components,
         },
@@ -416,17 +483,31 @@ def build_sweep_export_document(result: SweepResult) -> dict[str, object]:
             "calculated_points": result.calculated_count,
             "failed_points": result.failed_count,
         },
-        "points": [_sweep_point_export(point) for point in result.points],
+        "points": [
+            _sweep_point_export(point, selected_units) for point in result.points
+        ],
     }
 
 
-def export_sweep_csv_bytes(result: SweepResult) -> bytes:
+def export_sweep_csv_bytes(
+    result: SweepResult, units: UnitPreferences | None = None
+) -> bytes:
     """Serialize one full-precision row per swept point, failures included."""
 
     output = StringIO(newline="")
     writer = csv.writer(output, lineterminator="\n")
     writer.writerow(SWEEP_CSV_COLUMNS)
+    selected_units = units or UnitPreferences(
+        temperature=result.request.temperature_unit,
+        pressure=result.request.pressure_unit,
+    )
     for point in result.points:
-        row = [getattr(point, column) for column in SWEEP_CSV_COLUMNS]
+        exported = _sweep_point_export(point, selected_units)
+        row = []
+        for column in SWEEP_CSV_COLUMNS:
+            value = exported.get(column)
+            if isinstance(value, Mapping) and "value" in value:
+                value = value["value"]
+            row.append(value)
         writer.writerow([_csv_value(value) for value in row])
     return output.getvalue().encode("utf-8-sig")
diff --git a/src/pvt_phase_simulator_ui/model_scope.py b/src/pvt_phase_simulator_ui/model_scope.py
index 3f445bc..c9a412f 100644
--- a/src/pvt_phase_simulator_ui/model_scope.py
+++ b/src/pvt_phase_simulator_ui/model_scope.py
@@ -19,9 +19,9 @@ from pvt_phase_simulator.experimental_validation import (
 )
 from pvt_phase_simulator_ui.adapters import (
     COMPONENTS,
-    PA_PER_MPA,
     load_module17_records,
 )
+from pvt_phase_simulator_ui.units import PressureUnit, pressure_from_pa
 
 EOS_DISPLAY_NAME: Final = "Peng–Robinson EOS"
 VALIDATION_ARTIFACT: Final = Path("docs/validation/module17_vle_validation.csv")
@@ -48,11 +48,21 @@ class ModelScope:
     validation_state_count: int
     validation_system_names: tuple[str, ...]
     validation_temperature_range_k: tuple[float, float]
-    validation_pressure_range_mpa: tuple[float, float]
+    validation_pressure_range_pa: tuple[float, float]
     property_sources: tuple[RecordedSource, ...]
     validation_source: RecordedSource
     validation_artifact: Path
 
+    @property
+    def validation_pressure_range_mpa(self) -> tuple[float, float]:
+        """Compatibility presentation of the recorded canonical Pa range."""
+
+        lower, upper = self.validation_pressure_range_pa
+        return (
+            pressure_from_pa(lower, PressureUnit.MPA),
+            pressure_from_pa(upper, PressureUnit.MPA),
+        )
+
 
 def _property_records(component: Component) -> tuple[ComponentPropertyProvenance, ...]:
     provenance = component.provenance
@@ -111,9 +121,7 @@ def load_model_scope(repository_root: Path) -> ModelScope:
         repository_root / EXPERIMENTAL_MANIFEST,
     )
     temperatures = tuple(record.temperature_k for record in records)
-    pressures_mpa = tuple(
-        record.experimental_pressure_pa / PA_PER_MPA for record in records
-    )
+    pressures_pa = tuple(record.experimental_pressure_pa for record in records)
     systems = tuple(dict.fromkeys(record.system_id for record in records))
     source = dataset.source
     return ModelScope(
@@ -125,7 +133,7 @@ def load_model_scope(repository_root: Path) -> ModelScope:
             _validation_system_name(item) for item in systems
         ),
         validation_temperature_range_k=(min(temperatures), max(temperatures)),
-        validation_pressure_range_mpa=(min(pressures_mpa), max(pressures_mpa)),
+        validation_pressure_range_pa=(min(pressures_pa), max(pressures_pa)),
         property_sources=_property_sources(),
         validation_source=RecordedSource(
             source.archive_name,
diff --git a/src/pvt_phase_simulator_ui/state.py b/src/pvt_phase_simulator_ui/state.py
index 3877058..249849d 100644
--- a/src/pvt_phase_simulator_ui/state.py
+++ b/src/pvt_phase_simulator_ui/state.py
@@ -7,6 +7,15 @@ from dataclasses import dataclass
 from typing import Any, Final, cast
 
 from pvt_phase_simulator_ui.adapters import ScientificInputs
+from pvt_phase_simulator_ui.units import (
+    DEFAULT_UNITS,
+    PressureUnit,
+    TemperatureUnit,
+    convert_pressure,
+    convert_temperature,
+    pressure_from_pa,
+    temperature_from_k,
+)
 
 RESULT_KEYS: Final = ("flash", "envelope", "critical", "critical_scan", "sweep")
 
@@ -20,7 +29,11 @@ class InputExample:
     ethane_pct: float
     propane_pct: float
     temperature_k: float
-    pressure_mpa: float
+    pressure_pa: float
+
+    @property
+    def pressure_mpa(self) -> float:
+        return pressure_from_pa(self.pressure_pa, PressureUnit.MPA)
 
 
 INPUT_EXAMPLES: Final = (
@@ -30,7 +43,7 @@ INPUT_EXAMPLES: Final = (
         ethane_pct=0.0,
         propane_pct=50.0,
         temperature_k=300.0,
-        pressure_mpa=5.0,
+        pressure_pa=5.0e6,
     ),
     InputExample(
         label="Known single-phase case at 300 K and 20 MPa",
@@ -38,7 +51,7 @@ INPUT_EXAMPLES: Final = (
         ethane_pct=0.0,
         propane_pct=50.0,
         temperature_k=300.0,
-        pressure_mpa=20.0,
+        pressure_pa=20.0e6,
     ),
     InputExample(
         label="Audited critical-solver seed",
@@ -46,7 +59,7 @@ INPUT_EXAMPLES: Final = (
         ethane_pct=0.0,
         propane_pct=50.0,
         temperature_k=321.5829183194,
-        pressure_mpa=8.53444323606381,
+        pressure_pa=8_534_443.23606381,
     ),
 )
 
@@ -65,6 +78,32 @@ def initialize_session(state: MutableMapping[str, Any]) -> None:
     state.setdefault("propane_pct", _DEFAULT_INPUTS.propane_pct)
     state.setdefault("temperature_k", _DEFAULT_INPUTS.temperature_k)
     state.setdefault("pressure_mpa", _DEFAULT_INPUTS.pressure_mpa)
+    state.setdefault("temperature_unit", DEFAULT_UNITS.temperature.value)
+    state.setdefault("pressure_unit", DEFAULT_UNITS.pressure.value)
+    state.setdefault("rendered_temperature_unit", DEFAULT_UNITS.temperature.value)
+    state.setdefault("rendered_pressure_unit", DEFAULT_UNITS.pressure.value)
+    state.setdefault("temperature_value", _DEFAULT_INPUTS.temperature_k)
+    state.setdefault("pressure_value", _DEFAULT_INPUTS.pressure_mpa)
+
+
+def synchronize_unit_inputs(state: MutableMapping[str, Any]) -> None:
+    """Preserve the physical input state when a presentation unit changes."""
+
+    initialize_session(state)
+    old_temperature = TemperatureUnit(str(state["rendered_temperature_unit"]))
+    new_temperature = TemperatureUnit(str(state["temperature_unit"]))
+    old_pressure = PressureUnit(str(state["rendered_pressure_unit"]))
+    new_pressure = PressureUnit(str(state["pressure_unit"]))
+    if old_temperature is not new_temperature:
+        state["temperature_value"] = convert_temperature(
+            float(state["temperature_value"]), old_temperature, new_temperature
+        )
+        state["rendered_temperature_unit"] = new_temperature.value
+    if old_pressure is not new_pressure:
+        state["pressure_value"] = convert_pressure(
+            float(state["pressure_value"]), old_pressure, new_pressure
+        )
+        state["rendered_pressure_unit"] = new_pressure.value
 
 
 def apply_selected_input_example(state: MutableMapping[str, Any]) -> None:
@@ -79,6 +118,16 @@ def apply_selected_input_example(state: MutableMapping[str, Any]) -> None:
     state["propane_pct"] = example.propane_pct
     state["temperature_k"] = example.temperature_k
     state["pressure_mpa"] = example.pressure_mpa
+    temperature_unit = TemperatureUnit(
+        str(state.get("temperature_unit", DEFAULT_UNITS.temperature.value))
+    )
+    pressure_unit = PressureUnit(
+        str(state.get("pressure_unit", DEFAULT_UNITS.pressure.value))
+    )
+    state["temperature_value"] = temperature_from_k(
+        example.temperature_k, temperature_unit
+    )
+    state["pressure_value"] = pressure_from_pa(example.pressure_pa, pressure_unit)
 
 
 def store_result(
diff --git a/src/pvt_phase_simulator_ui/sweeps.py b/src/pvt_phase_simulator_ui/sweeps.py
index 2e7f123..97e3b89 100644
--- a/src/pvt_phase_simulator_ui/sweeps.py
+++ b/src/pvt_phase_simulator_ui/sweeps.py
@@ -14,17 +14,20 @@ from dataclasses import dataclass
 from math import isfinite
 from typing import Final, Literal
 
-from pvt_phase_simulator.eos.flash import TwoPhaseFlashResult
+from pvt_phase_simulator.eos.flash import TwoPhaseFlashResult, calculate_two_phase_flash
 from pvt_phase_simulator_ui.adapters import (
-    PA_PER_MPA,
     FlashCallable,
     InputValidationError,
     ScientificInputs,
     adapt_flash_result,
     flash_presentation_kind,
-    run_validated_flash,
     validate_scientific_inputs,
 )
+from pvt_phase_simulator_ui.units import (
+    PressureUnit,
+    TemperatureUnit,
+    pressure_from_pa,
+)
 
 #: Sweeps are an engineering overview, not a continuation study. The bounds keep
 #: a hosted session responsive and make the cost of a run predictable.
@@ -63,27 +66,30 @@ class SweepRequest:
 
     kind: SweepKind
     composition_mol_percent: tuple[float, float, float]
-    fixed_temperature_k: float | None
-    fixed_pressure_mpa: float | None
+    fixed_temperature: float | None
+    fixed_pressure: float | None
     start: float
     end: float
     points: int
+    temperature_unit: TemperatureUnit = TemperatureUnit.KELVIN
+    pressure_unit: PressureUnit = PressureUnit.MPA
 
     @property
     def axis_label(self) -> str:
-        return "Pressure (MPa)" if self.kind == "pressure" else "Temperature (K)"
+        unit = self.pressure_unit if self.kind == "pressure" else self.temperature_unit
+        return f"{self.kind.capitalize()} ({unit.value})"
 
     def axis_values(self) -> tuple[float, ...]:
         return sweep_axis_values(self.start, self.end, self.points)
 
     def state_at(self, value: float) -> tuple[float, float]:
-        """Return the (temperature K, pressure MPa) state for one swept value."""
+        """Return a state in the request's explicitly recorded field units."""
 
         if self.kind == "pressure":
-            assert self.fixed_temperature_k is not None
-            return self.fixed_temperature_k, value
-        assert self.fixed_pressure_mpa is not None
-        return value, self.fixed_pressure_mpa
+            assert self.fixed_temperature is not None
+            return self.fixed_temperature, value
+        assert self.fixed_pressure is not None
+        return value, self.fixed_pressure
 
 
 @dataclass(frozen=True, slots=True)
@@ -92,7 +98,6 @@ class SweepPoint:
 
     index: int
     temperature_k: float
-    pressure_mpa: float
     pressure_pa: float
     status: PointStatus
     phase_state: str | None
@@ -107,6 +112,12 @@ class SweepPoint:
     failure_reason: str | None
     error: str | None
 
+    @property
+    def pressure_mpa(self) -> float:
+        """Compatibility presentation of the canonical pressure in MPa."""
+
+        return pressure_from_pa(self.pressure_pa, PressureUnit.MPA)
+
 
 @dataclass(frozen=True, slots=True)
 class SweepResult:
@@ -124,14 +135,14 @@ class SweepResult:
         return sum(1 for point in self.points if point.status == "failed")
 
     def abscissae(self) -> tuple[float, ...]:
-        """The swept coordinate for every point, in request order."""
+        """The requested swept coordinates in their explicitly recorded unit."""
 
-        if self.request.kind == "pressure":
-            return tuple(point.pressure_mpa for point in self.points)
-        return tuple(point.temperature_k for point in self.points)
+        return self.request.axis_values()
 
 
-def _validate_axis(start: float, end: float, points: int) -> tuple[float, float, int]:
+def _validate_axis(
+    start: float, end: float, points: int, *, require_positive: bool
+) -> tuple[float, float, int]:
     if isinstance(points, bool) or not isinstance(points, int):
         raise SweepValidationError("Number of points must be an integer.")
     if points < MIN_SWEEP_POINTS or points > MAX_SWEEP_POINTS:
@@ -143,7 +154,7 @@ def _validate_axis(start: float, end: float, points: int) -> tuple[float, float,
     last = float(end)
     if not isfinite(first) or not isfinite(last):
         raise SweepValidationError("Sweep bounds must be finite.")
-    if first <= 0.0 or last <= 0.0:
+    if require_positive and (first <= 0.0 or last <= 0.0):
         raise SweepValidationError("Sweep bounds must be positive.")
     if first == last:
         raise SweepValidationError("Sweep start and end must differ.")
@@ -158,6 +169,8 @@ def validate_sweep_request(
     start: float,
     end: float,
     points: int,
+    temperature_unit: TemperatureUnit | str = TemperatureUnit.KELVIN,
+    pressure_unit: PressureUnit | str = PressureUnit.MPA,
 ) -> SweepRequest:
     """Validate a sweep before any production call is attempted.
 
@@ -167,33 +180,52 @@ def validate_sweep_request(
 
     if kind not in ("pressure", "temperature"):
         raise SweepValidationError("Sweep kind must be 'pressure' or 'temperature'.")
-    first, last, count = _validate_axis(start, end, points)
+    first, last, count = _validate_axis(
+        start, end, points, require_positive=kind == "pressure"
+    )
 
     fixed = float(fixed_value)
-    if not isfinite(fixed) or fixed <= 0.0:
+    if not isfinite(fixed):
         raise SweepValidationError(
-            "Fixed temperature must be positive and finite."
+            "Fixed temperature must be finite."
             if kind == "pressure"
-            else "Fixed pressure must be positive and finite."
+            else "Fixed pressure must be finite."
         )
 
-    temperature = fixed if kind == "pressure" else first
-    pressure = first if kind == "pressure" else fixed
     try:
-        validated = validate_scientific_inputs(
-            composition_mol_percent, temperature, pressure
+        selected_temperature_unit = TemperatureUnit(temperature_unit)
+        selected_pressure_unit = PressureUnit(pressure_unit)
+    except ValueError as error:
+        raise SweepValidationError(str(error)) from error
+    states = (
+        (fixed, first) if kind == "pressure" else (first, fixed),
+        (fixed, last) if kind == "pressure" else (last, fixed),
+    )
+    try:
+        validated_states = tuple(
+            validate_scientific_inputs(
+                composition_mol_percent,
+                temperature,
+                pressure,
+                temperature_unit=selected_temperature_unit,
+                pressure_unit=selected_pressure_unit,
+            )
+            for temperature, pressure in states
         )
     except InputValidationError as error:
         raise SweepValidationError(str(error)) from error
+    validated = validated_states[0]
 
     return SweepRequest(
         kind=kind,
         composition_mol_percent=validated.composition_mol_percent,
-        fixed_temperature_k=fixed if kind == "pressure" else None,
-        fixed_pressure_mpa=None if kind == "pressure" else fixed,
+        fixed_temperature=fixed if kind == "pressure" else None,
+        fixed_pressure=None if kind == "pressure" else fixed,
         start=first,
         end=last,
         points=count,
+        temperature_unit=selected_temperature_unit,
+        pressure_unit=selected_pressure_unit,
     )
 
 
@@ -203,17 +235,15 @@ def _enum_value(value: object) -> str:
 
 def _failed_point(
     index: int,
-    temperature_k: float,
-    pressure_mpa: float,
+    inputs: ScientificInputs,
     error: str,
 ) -> SweepPoint:
     """A point the production API could not evaluate stays explicitly failed."""
 
     return SweepPoint(
         index=index,
-        temperature_k=temperature_k,
-        pressure_mpa=pressure_mpa,
-        pressure_pa=pressure_mpa * PA_PER_MPA,
+        temperature_k=inputs.temperature_k,
+        pressure_pa=inputs.pressure_pa,
         status="failed",
         phase_state=None,
         convergence_status=None,
@@ -241,7 +271,6 @@ def _adapt_point(
     return SweepPoint(
         index=index,
         temperature_k=inputs.temperature_k,
-        pressure_mpa=inputs.pressure_mpa,
         pressure_pa=inputs.pressure_pa,
         status=status,
         phase_state=_enum_value(view.phase_state),
@@ -271,25 +300,22 @@ def run_sweep(
     points: list[SweepPoint] = []
 
     for index, value in enumerate(axis):
-        temperature_k, pressure_mpa = request.state_at(value)
+        temperature, pressure = request.state_at(value)
+        inputs = validate_scientific_inputs(
+            request.composition_mol_percent,
+            temperature,
+            pressure,
+            temperature_unit=request.temperature_unit,
+            pressure_unit=request.pressure_unit,
+        )
         try:
-            if flash_api is None:
-                inputs, result = run_validated_flash(
-                    request.composition_mol_percent, temperature_k, pressure_mpa
-                )
-            else:
-                inputs, result = run_validated_flash(
-                    request.composition_mol_percent,
-                    temperature_k,
-                    pressure_mpa,
-                    flash_api=flash_api,
-                )
+            api = calculate_two_phase_flash if flash_api is None else flash_api
+            result = api(inputs.mixture(), inputs.temperature_k, inputs.pressure_pa)
         except Exception as error:  # noqa: BLE001 - a failed point stays failed
             points.append(
                 _failed_point(
                     index,
-                    temperature_k,
-                    pressure_mpa,
+                    inputs,
                     f"{type(error).__name__}: {error}",
                 )
             )
diff --git a/src/pvt_phase_simulator_ui/views.py b/src/pvt_phase_simulator_ui/views.py
index 37e937f..824553b 100644
--- a/src/pvt_phase_simulator_ui/views.py
+++ b/src/pvt_phase_simulator_ui/views.py
@@ -25,7 +25,6 @@ from pvt_phase_simulator.eos.phase_envelope import (
 )
 from pvt_phase_simulator.plotting import (
     CompositionDisplay,
-    PressureUnit,
     plot_critical_solver_conditioning,
     plot_critical_solver_convergence,
     plot_critical_solver_path,
@@ -38,9 +37,11 @@ from pvt_phase_simulator.plotting import (
     plot_validation_retrospective_diagnostics,
     plot_validation_status,
 )
+from pvt_phase_simulator.plotting import (
+    PressureUnit as PlotPressureUnit,
+)
 from pvt_phase_simulator_ui.adapters import (
     COMPONENT_NAMES,
-    PA_PER_MPA,
     ScientificInputs,
     adapt_critical_result,
     adapt_flash_result,
@@ -50,7 +51,7 @@ from pvt_phase_simulator_ui.adapters import (
     status_text,
     validation_pressure_error_summary,
 )
-from pvt_phase_simulator_ui.context import session
+from pvt_phase_simulator_ui.context import session, unit_preferences
 from pvt_phase_simulator_ui.exports import (
     build_export_document,
     build_sweep_export_document,
@@ -71,10 +72,64 @@ from pvt_phase_simulator_ui.sweeps import (
     run_sweep,
     validate_sweep_request,
 )
+from pvt_phase_simulator_ui.units import (
+    DEFAULT_UNITS,
+    UnitPreferences,
+    pressure_from_pa,
+    temperature_from_k,
+)
 
 ROOT = Path(__file__).resolve().parents[2]
 
 
+def _display_temperature(value_k: float, units: UnitPreferences) -> float:
+    return temperature_from_k(value_k, units.temperature)
+
+
+def _display_pressure(value_pa: float, units: UnitPreferences) -> float:
+    return pressure_from_pa(value_pa, units.pressure)
+
+
+def _convert_axis_values(values: Any, converter: Any) -> tuple[object, ...]:
+    if values is None:
+        return ()
+    return tuple(None if value is None else converter(float(value)) for value in values)
+
+
+def _presentation_figure(
+    figure: go.Figure,
+    units: UnitPreferences,
+    *,
+    x_quantity: Literal["temperature", "pressure"] | None = None,
+    y_quantity: Literal["temperature", "pressure"] | None = None,
+) -> go.Figure:
+    """Convert a source figure's SI axes once at the presentation boundary."""
+
+    converters = {
+        "temperature": lambda value: _display_temperature(value, units),
+        "pressure": lambda value: _display_pressure(value, units),
+    }
+    labels = {
+        "temperature": f"Temperature ({units.temperature.value})",
+        "pressure": f"Pressure ({units.pressure.value})",
+    }
+    for trace in figure.data:
+        if x_quantity is not None and getattr(trace, "x", None) is not None:
+            trace.x = _convert_axis_values(trace.x, converters[x_quantity])
+        if y_quantity is not None and getattr(trace, "y", None) is not None:
+            trace.y = _convert_axis_values(trace.y, converters[y_quantity])
+        template = getattr(trace, "hovertemplate", None)
+        if isinstance(template, str):
+            trace.hovertemplate = template.replace(
+                " K", f" {units.temperature.value}"
+            ).replace(" Pa", f" {units.pressure.value}")
+    if x_quantity is not None:
+        figure.update_xaxes(title_text=labels[x_quantity])
+    if y_quantity is not None:
+        figure.update_yaxes(title_text=labels[y_quantity])
+    return figure
+
+
 def _value(item: object) -> str:
     return str(item.value if hasattr(item, "value") else item)
 
@@ -279,10 +334,16 @@ def _doi_link(doi: str | None) -> str:
 
 def _render_model_scope_panel() -> None:
     scope = _model_scope()
+    units = unit_preferences()
     components = ", ".join(scope.verified_component_names)
     systems = " and ".join(scope.validation_system_names)
-    temperature_min, temperature_max = scope.validation_temperature_range_k
-    pressure_min, pressure_max = scope.validation_pressure_range_mpa
+    temperature_min, temperature_max = (
+        _display_temperature(value, units)
+        for value in scope.validation_temperature_range_k
+    )
+    pressure_min, pressure_max = (
+        _display_pressure(value, units) for value in scope.validation_pressure_range_pa
+    )
 
     with st.container(border=True):
         st.subheader("Model and limitations", anchor="model-and-limitations")
@@ -303,8 +364,9 @@ def _render_model_scope_panel() -> None:
         st.markdown(
             f"**Validation scope.** The protected Module 17 artifact contains "
             f"**{scope.validation_state_count} experimental VLE states** for "
-            f"**{systems}**, spanning {temperature_min:g}–{temperature_max:g} K and "
-            f"{pressure_min:g}–{pressure_max:g} MPa in the recorded states. This "
+            f"**{systems}**, spanning {temperature_min:g}–{temperature_max:g} "
+            f"{units.temperature.value} and {pressure_min:g}–{pressure_max:g} "
+            f"{units.pressure.value} in the recorded states. This "
             "does not establish accuracy for other components, mixtures, or "
             "conditions."
         )
@@ -344,6 +406,7 @@ def _render_model_scope_panel() -> None:
 
 def render_overview(inputs: ScientificInputs | None) -> None:
     st.header("Overview")
+    units = unit_preferences()
     _render_model_scope_panel()
     raw = get_result(session(), "flash")
     if raw is None:
@@ -376,8 +439,15 @@ def render_overview(inputs: ScientificInputs | None) -> None:
                 icon=":material/error:",
             )
     state_columns = st.columns(4, vertical_alignment="center")
-    state_columns[0].metric("Temperature", f"{view.temperature_k:.6g} K")
-    state_columns[1].metric("Pressure", f"{view.pressure_pa / PA_PER_MPA:.6g} MPa")
+    state_columns[0].metric(
+        "Temperature",
+        f"{_display_temperature(view.temperature_k, units):.6g} "
+        f"{units.temperature.value}",
+    )
+    state_columns[1].metric(
+        "Pressure",
+        f"{_display_pressure(view.pressure_pa, units):.6g} {units.pressure.value}",
+    )
     state_columns[2].metric("Model", "Peng-Robinson")
     state_columns[3].metric("Interactions", "kij = 0")
     phase_columns = st.columns(4, vertical_alignment="center")
@@ -420,6 +490,7 @@ def render_overview(inputs: ScientificInputs | None) -> None:
             flash_result=None if flash_stale else result,
             envelope_result=envelope_export,
             critical_result=critical_export,
+            units=units,
         )
         st.subheader("Export current case")
         with st.container(horizontal=True):
@@ -470,6 +541,7 @@ def _calculate_envelope(inputs: ScientificInputs) -> PhaseEnvelopeResult:
 
 def render_phase_envelope(inputs: ScientificInputs | None) -> None:
     st.header("Phase envelope")
+    units = unit_preferences()
     st.caption(
         "Independent bounded bubble and dew continuation · "
         "turning points are not critical points"
@@ -511,11 +583,16 @@ def render_phase_envelope(inputs: ScientificInputs | None) -> None:
         critical = None
     _wide_chart(
         _annotate_missing_envelope_branches(
-            plot_phase_envelope(
-                result,
-                pressure_unit=PressureUnit.MPA,
-                critical_point=critical,
-                metadata={"model": "Peng-Robinson EOS; kij=0"},
+            _presentation_figure(
+                plot_phase_envelope(
+                    result,
+                    pressure_unit=PlotPressureUnit.PA,
+                    critical_point=critical,
+                    metadata={"model": "Peng-Robinson EOS; kij=0"},
+                ),
+                units,
+                x_quantity="temperature",
+                y_quantity="pressure",
             ),
             result,
         ),
@@ -558,12 +635,16 @@ def render_phase_envelope(inputs: ScientificInputs | None) -> None:
     if st.button("SHOW PHASE COMPOSITIONS", icon=":material/show_chart:"):
         try:
             _wide_chart(
-                plot_phase_compositions(
-                    result,
-                    branch=branch,
-                    component_index=COMPONENT_NAMES.index(component),
-                    display=CompositionDisplay.MOL_PERCENT,
-                    pressure_unit=PressureUnit.MPA,
+                _presentation_figure(
+                    plot_phase_compositions(
+                        result,
+                        branch=branch,
+                        component_index=COMPONENT_NAMES.index(component),
+                        display=CompositionDisplay.MOL_PERCENT,
+                        pressure_unit=PlotPressureUnit.PA,
+                    ),
+           
… [truncated, 28681 more characters]
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
