# Independent audit: streamlit_ui_stabilization

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
- Name: streamlit_ui_stabilization
- Declared risk: MEDIUM
- Objective: Post-audit UI stabilization of the Streamlit application, driven by a live-browser audit. Application layer only. The scientific engine is FROZEN: do not modify src/pvt_phase_simulator/**, scientific equations, validation datasets, critical-point algorithms, or flash/envelope/saturation logic. Two root causes below were already diagnosed against the live engine and are stated as FACT - do not re-litigate them, and do not change science to force any result.

=== PRIORITY 1: NAVIGATION (blocking) ===
st.navigation(..., position='top') renders a container measured at 924x0 px with overflow:hidden, so all five page tabs are clipped out of existence. The only visible affordance is a 57x28 px unlabeled 'more' overflow button. Reproduced at BOTH 1440x900 and 1920x1080, so it is not a responsive collapse. The application's own CSS is NOT the cause (styles.py is scoped only to the phase-split bar).
Required: replace top navigation with a clearly visible, professional layout that shows all five destinations. Prefer native Streamlit behaviour: either st.navigation with default sidebar position (recommended - the sidebar already exists and has room), or st.navigation with an explicit visible arrangement. Do NOT attempt to fix this with fragile CSS overrides against Streamlit internals. Per-page URLs must keep working (/phase_envelope, /critical_point, /validation, /diagnostics). Verify the chosen approach actually renders visible page labels rather than an overflow control.

=== PRIORITY 2: OPERATING POINT (root cause proven) ===
Symptom: with the default case (CH4 50 / C2 0 / C3 50 mol %, 300 K, 5 MPa) the Overview and Phase Envelope pages both report the operating point as unavailable even AFTER a successful envelope calculation.
PROVEN ROOT CAUSE (measured against the live engine, read-only):
  * views.py builds EnvelopeContinuationSettings(target_temperature_k = T + 50) and calls calculate_phase_envelope(..., start_bubble = T, start_dew = T). Both branches therefore COLD-START at exactly the operating temperature.
  * A cold bubble-point saturation search fails for this mixture at T >= about 280 K. Direct probe: bubble converged 5.45208 MPa at 240 K and 6.77618 MPa at 260 K, but returns NOT_FOUND at 280 K, 300 K and 310 K. Dew converges at all of those temperatures.
  * Consequently the bubble branch produced ZERO points, terminating corrector_failed with 'No trustworthy saturation-pressure bracket was found'. The dew branch produced 9 converged points spanning 300.0000-329.0730 K.
  * adapters._converged_pressures_at_temperature returns (None, 2348238.8178706504). location_relative_to_envelope then hits the all-or-nothing guard 'if bubble is None or dew is None' and returns the unavailable string, discarding the dew value it does have.
PROVEN FIX (application layer only, no science change):
  * Continuation marching THROUGH a temperature succeeds where a cold bracket at that temperature fails. Starting the trace BELOW the operating point resolves it. Measured: start 270 K, target 330 K, step 5 K, maximum_points 15 gives bubble 15 converged points over 270.0-307.1 K and dew 11 over 270.0-329.1 K; both bracket 300 K; interpolation yields bubble 8.66999 MPa and dew 2.36649 MPa; location becomes 'Inside the interpolated two-phase envelope', which AGREES with the independent flash result of Two Phase. Runtime 21.7 s.
  * Therefore: centre the traced range on the operating point (start below it, target above it) instead of starting at it. These settings live in the UI layer and are a UI decision, not science.
  * ALSO make the reporting per-branch instead of all-or-nothing: when only one branch converged, state the relationship to that branch, name the missing branch, and surface the engine's own termination_message. Never fabricate a missing branch and never imply a bound that was not computed.

=== PRIORITY 3: BUBBLE BRANCH (finding confirmed) ===
The audit observed only a dew branch in the rendered figure. Confirmed: the bubble branch genuinely contained zero points in that result - tracing did not produce it. This is NOT a plotting defect and NOT missing data that exists. It is the same root cause as Priority 2 and is resolved by the same trace-range change. Do not fabricate a bubble branch. If a branch is empty, the figure and the page must say so explicitly, citing the engine's termination reason.

=== PRIORITY 4: UX FIXES ===
  * Disabled actions: RUN PHASE ENVELOPE, RUN CRITICAL SOLVER, RUN CRITICALITY MAP and any other page action are disabled until RUN FLASH has been submitted, while the sidebar simultaneously reads 'Composition total: 100 mol % - ready'. Explain the requirement in the UI next to the disabled control, e.g. 'Submit RUN FLASH to enable'. Do not silently disable a primary action.
  * Replace raw internal identifiers in user-facing copy. The Critical Point page currently prints 'Certification requires CriticalPointStatus.CONVERGED; a spinodal or lambda_min = 0 is insufficient.' Use plain engineering language with no Python class or enum names. Keep the scientific meaning exactly: certification requires solver convergence on BOTH criticality conditions, and lambda_min = 0 alone is a spinodal condition, not a critical point.
  * Precision: normal UI surfaces currently show up to 10 significant figures (e.g. Vapor Z 0.7243397959, Tc 321.5829187 K), which overstates precision relative to solver tolerance. Round normal displays to about 5-6 significant figures. FULL precision must be preserved unchanged in technical details and in any export path. Do not round any value used in a calculation - display only.
  * Chart dimensions: figures are all rendered at roughly 1450x450 (about 3.2:1). Parity plots that draw a y = x reference line are visually distorted by that aspect ratio. Give parity/scatter figures a near-square aspect and keep wide aspect for P-T envelopes and error-versus-temperature plots.
  * Validation summary: the Validation page is about 3301 px tall - five stacked figures with no conclusion stated anywhere. Add a compact summary strip ABOVE the figures reporting only quantities that exist in the protected Module 17 records, for example number of states, and a median and worst absolute relative pressure error. State the worst case alongside the median. Do NOT add a bare 'validated' badge and do NOT make any accuracy claim beyond what the records support.
  * Caption contrast: captions currently compute to the same colour as body text (rgb(20,43,67)), so secondary text has no visual de-emphasis. Mute secondary/caption text via the native theme while keeping accessible contrast (target at least 4.5:1 against its background; body currently measures 13.66:1 so there is ample headroom).

=== PRIORITY 5: PERFORMANCE ===
Measured: the engine call for the current UI settings takes about 16 s; the browser end-to-end time from clicking RUN PHASE ENVELOPE to a rendered figure was about 51 s. The recommended bracketing range measures about 21.7 s in-engine. Do NOT weaken, truncate, or coarsen any calculation for speed. Permitted: cache results so an unchanged case is not recomputed, and replace the bare spinner with genuine progress/status feedback that tells the user what is running and roughly how long it takes. If runtime cannot be safely reduced at the UI layer, say so in the report and improve feedback instead.

=== PRESERVE EXACTLY (do not regress) ===
  * Diagnostics progressive disclosure: labelled tables by default plus the 'Show advanced raw public objects' toggle. Zero raw JSON dumps by default.
  * Certified critical-point gating: certification only when the production status is converged; uncertified solves must never render a certified Tc/Pc.
  * Technical details rendered as tables.
  * The phase-split bar.
  * The native theme in .streamlit/config.toml.
  * Explicit-action gating: nothing scientific computes on page load.
  * The 'turning points are not critical points' caption.
  * The retrospective 'NOT PRODUCTION PREDICTIONS' warning adjacent to its figure.
  * The 50/50 methane/propane regression must still read 321.5829183194 K and 8.53444323606381 MPa through production result objects at full precision.

## Scientific invariants claimed to hold
  - No file under src/pvt_phase_simulator/ changes. The engine is frozen.
  - No scientific equation, tolerance, dataset, or algorithm changes.
  - Golden master, property CSV, and Module 17 artifacts stay byte-identical.
  - Envelope trace-range settings are a UI decision; the continuation and saturation algorithms themselves are untouched.
  - A missing branch is reported as missing with the engine's own termination reason; no branch, point, or bound is ever fabricated.
  - Rounding is display-only; no rounded value is fed back into any calculation, technical-details table, or export.
  - Certification still requires the production converged status; lambda_min = 0 alone is never certified.
  - The 50/50 methane/propane regression still yields 321.5829183194 K and 8.53444323606381 MPa at full precision.
  - Validation copy claims nothing beyond what the protected Module 17 records contain.

## Repository state
- Branch: `master`
- HEAD: `a2d1513a5a00fbba5faf3263111ba6717573f22f`
- Base for this change: `a2d1513a5a00fbba5faf3263111ba6717573f22f`

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
Changed files: ['.streamlit/config.toml', 'src/pvt_phase_simulator_ui/adapters.py', 'src/pvt_phase_simulator_ui/app.py', 'src/pvt_phase_simulator_ui/views.py', 'tests/test_app_adapters.py', 'tests/test_app_streamlit.py']

## Builder's own report — treat as an unverified claim
```
Implemented the Streamlit UI stabilization entirely in the allowed application layer.

Key outcomes:

- Visible native sidebar navigation with all five destinations and working direct routes.
- Centered envelope tracing produces both branches for the default case and correctly reports the operating point inside the envelope.
- Missing branches report engine termination details in both page content and figure annotations.
- Added bounded caching and realistic progress feedback.
- Added disabled-action explanations, engineering-language critical-point copy, display-only rounding, validation summary metrics, square parity charts, and accessible muted captions.
- Frozen engine paths remain unchanged; all protected hashes match.
- Browser automation was unavailable, so rendering was verified with Streamlit AppTest and HTTP 200 checks for every route.

Verification:

- Pytest: 1,167 passed.
- Ruff check and format: passed.
- MyPy: passed.
- Compileall: passed.
- `git diff --check`: passed.
- Default envelope runtime: 22.26 s; bubble 15 points, dew 11 points.
- Critical regression test: passed at full precision.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "pytest: 1167 passed in 329.20s using a workspace-local temporary directory because the sandbox denied pytest's default Windows temp path; ruff check: passed; ruff format --check: 154 files formatted; mypy src app: passed; compileall src app: passed; git diff --check: passed; focused critical regression: passed; all protected artifact hashes matched",
  "files_changed": [".streamlit/config.toml", "src/pvt_phase_simulator_ui/adapters.py", "src/pvt_phase_simulator_ui/app.py", "src/pvt_phase_simulator_ui/views.py", "tests/test_app_adapters.py", "tests/test_app_streamlit.py"],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>
```

## Diff stat
```
 .ai/workflow_state.json                |  33 +++++-
 .streamlit/config.toml                 |   2 +
 src/pvt_phase_simulator_ui/adapters.py |  50 ++++++++-
 src/pvt_phase_simulator_ui/app.py      |  24 +++--
 src/pvt_phase_simulator_ui/views.py    | 186 ++++++++++++++++++++++-----------
 tests/test_app_adapters.py             | 101 ++++++++++++++++++
 tests/test_app_streamlit.py            |  23 ++++
 7 files changed, 346 insertions(+), 73 deletions(-)

```

## Full diff
```diff
diff --git a/.ai/workflow_state.json b/.ai/workflow_state.json
index 4a65d5b..bad41b0 100644
--- a/.ai/workflow_state.json
+++ b/.ai/workflow_state.json
@@ -1,14 +1,14 @@
 {
   "project": "pvt-phase-simulator",
   "phase": "post-v1.0-extensions",
-  "workflow_status": "IDLE",
+  "workflow_status": "CLAUDE_RUNNING",
   "last_scientific_commit": "c2b6de92e026953df0fecd0e4097c85da6375460",
   "last_independent_audit_commit": "b94f3ef69351caeeaa6abacae5ec30103e1a88ef",
   "work_packages_since_audit": 0,
-  "current_work_package": "streamlit_engineering_ui_refinement",
+  "current_work_package": "streamlit_ui_stabilization",
   "current_risk": "MEDIUM",
-  "audit_required": false,
-  "audit_reason": null,
+  "audit_required": true,
+  "audit_reason": "package audit_policy=IMMEDIATE",
   "blocking_findings": [],
   "safe_defer_findings": [
     {
@@ -285,6 +285,31 @@
       "from": "IDLE",
       "to": "IDLE",
       "reason": "manually stopped"
+    },
+    {
+      "from": "IDLE",
+      "to": "PLANNING",
+      "reason": "planning streamlit_ui_stabilization"
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
+      "to": "CLAUDE_RUNNING",
+      "reason": "invoking Claude auditor"
     }
   ]
 }
diff --git a/.streamlit/config.toml b/.streamlit/config.toml
index 720df98..e7d5035 100644
--- a/.streamlit/config.toml
+++ b/.streamlit/config.toml
@@ -4,6 +4,7 @@ primaryColor = "#0B6B75"
 backgroundColor = "#F7F9FB"
 secondaryBackgroundColor = "#FFFFFF"
 textColor = "#142B43"
+grayTextColor = "#526477"
 linkColor = "#075F8C"
 borderColor = "#B9C6D3"
 showWidgetBorder = true
@@ -21,6 +22,7 @@ codeFont = "monospace"
 backgroundColor = "#EEF3F6"
 secondaryBackgroundColor = "#FFFFFF"
 textColor = "#142B43"
+grayTextColor = "#526477"
 primaryColor = "#075F8C"
 borderColor = "#9FB0C0"
 showWidgetBorder = true
diff --git a/src/pvt_phase_simulator_ui/adapters.py b/src/pvt_phase_simulator_ui/adapters.py
index 901ee14..e24acc0 100644
--- a/src/pvt_phase_simulator_ui/adapters.py
+++ b/src/pvt_phase_simulator_ui/adapters.py
@@ -6,6 +6,7 @@ from collections.abc import Callable, Sequence
 from dataclasses import dataclass
 from math import fsum, isfinite
 from pathlib import Path
+from statistics import median
 from typing import Final
 
 from pvt_phase_simulator.eos.critical_point import (
@@ -239,8 +240,25 @@ def location_relative_to_envelope(
     if result is None:
         return "Unavailable until a phase envelope has been calculated."
     bubble, dew = _converged_pressures_at_temperature(result, temperature_k)
-    if bubble is None or dew is None:
-        return "Unavailable at this temperature from converged envelope points."
+    if bubble is None and dew is None:
+        return (
+            "No interpolated branch is available at this temperature. "
+            f"Bubble branch: {result.bubble_branch.termination_message} "
+            f"Dew branch: {result.dew_branch.termination_message}"
+        )
+    if bubble is None:
+        assert dew is not None
+        relationship = _relationship_to_branch(pressure_pa, dew, "dew")
+        return (
+            f"{relationship} Bubble branch unavailable: "
+            f"{result.bubble_branch.termination_message}"
+        )
+    if dew is None:
+        relationship = _relationship_to_branch(pressure_pa, bubble, "bubble")
+        return (
+            f"{relationship} Dew branch unavailable: "
+            f"{result.dew_branch.termination_message}"
+        )
     lower, upper = sorted((bubble, dew))
     if lower <= pressure_pa <= upper:
         return "Inside the interpolated two-phase envelope."
@@ -249,6 +267,34 @@ def location_relative_to_envelope(
     return "Above both interpolated saturation branches."
 
 
+def _relationship_to_branch(
+    pressure_pa: float, branch_pressure_pa: float, branch_name: str
+) -> str:
+    if pressure_pa < branch_pressure_pa:
+        return f"Below the interpolated {branch_name} branch."
+    if pressure_pa > branch_pressure_pa:
+        return f"Above the interpolated {branch_name} branch."
+    return f"On the interpolated {branch_name} branch."
+
+
+def validation_pressure_error_summary(
+    records: Sequence[ValidationPlotRecord], direction: str
+) -> tuple[int, int, float | None, float | None]:
+    """Summarize only pressure-error values present in Module 17 records."""
+
+    if direction not in {"bubble", "dew"}:
+        raise ValueError("direction must be 'bubble' or 'dew'")
+    values = tuple(
+        abs(float(value))
+        for record in records
+        if (value := getattr(record, f"{direction}_pressure_relative_error"))
+        is not None
+    )
+    if not values:
+        return len(records), 0, None, None
+    return len(records), len(values), median(values) * 100.0, max(values) * 100.0
+
+
 def status_text(value: object) -> str:
     raw = value.value if hasattr(value, "value") else str(value)
     return str(raw).replace("_", " ").capitalize()
diff --git a/src/pvt_phase_simulator_ui/app.py b/src/pvt_phase_simulator_ui/app.py
index 62dbfd6..0e07fb8 100644
--- a/src/pvt_phase_simulator_ui/app.py
+++ b/src/pvt_phase_simulator_ui/app.py
@@ -19,6 +19,18 @@ from pvt_phase_simulator_ui.state import initialize_session, store_result
 PAGES_DIRECTORY = Path(__file__).with_name("pages")
 
 
+@st.cache_data(show_spinner=False, max_entries=16)
+def _cached_flash(inputs: ScientificInputs) -> object:
+    """Cache an unchanged submitted case without changing its calculations."""
+
+    _, result = run_validated_flash(
+        inputs.composition_mol_percent,
+        inputs.temperature_k,
+        inputs.pressure_mpa,
+    )
+    return result
+
+
 def _input_form() -> tuple[ScientificInputs | None, bool]:
     with st.sidebar:
         st.subheader("Fluid inputs")
@@ -116,19 +128,17 @@ def run_app() -> None:
                 icon=":material/monitoring:",
             ),
         ],
-        position="top",
+        position="sidebar",
     )
     page.run()
     if run_flash:
         assert inputs is not None
         with st.sidebar.status("Running production flash…", expanded=True) as status:
+            status.write("Evaluating stability and phase split for the submitted case.")
+            status.caption("An unchanged submitted case reuses the bounded UI cache.")
             try:
-                run_inputs, result = run_validated_flash(
-                    inputs.composition_mol_percent,
-                    inputs.temperature_k,
-                    inputs.pressure_mpa,
-                )
-                store_result(session(), "flash", result, run_inputs)
+                result = _cached_flash(inputs)
+                store_result(session(), "flash", result, inputs)
                 status.update(label="Flash complete", state="complete", expanded=False)
             except (ValueError, ArithmeticError) as error:
                 session()["flash_startup_error"] = str(error)
diff --git a/src/pvt_phase_simulator_ui/views.py b/src/pvt_phase_simulator_ui/views.py
index 7c70208..d180d4c 100644
--- a/src/pvt_phase_simulator_ui/views.py
+++ b/src/pvt_phase_simulator_ui/views.py
@@ -46,6 +46,7 @@ from pvt_phase_simulator_ui.adapters import (
     load_module17_records,
     location_relative_to_envelope,
     status_text,
+    validation_pressure_error_summary,
 )
 from pvt_phase_simulator_ui.context import session
 from pvt_phase_simulator_ui.state import get_result, result_is_stale, store_result
@@ -62,8 +63,52 @@ def _optional(value: float | None, digits: int = 6) -> str:
     return "Unavailable" if value is None else f"{value:.{digits}g}"
 
 
-def _scientific(value: float | None) -> str:
-    return "Unavailable" if value is None else f"{value:.6e}"
+def _full_precision(value: float | None) -> str:
+    return "Unavailable" if value is None else repr(float(value))
+
+
+def _action_requirement(inputs: ScientificInputs | None) -> None:
+    if inputs is None:
+        st.caption(":material/lock: Submit RUN FLASH to enable this action.")
+
+
+def _wide_chart(figure: Any, *, key: str | None = None) -> None:
+    st.plotly_chart(figure, width="stretch", height=500, key=key)
+
+
+def _square_chart(figure: Any, *, key: str) -> None:
+    with st.container(horizontal_alignment="center"):
+        st.plotly_chart(figure, width=680, height=640, key=key)
+
+
+def _annotate_missing_envelope_branches(
+    figure: Any, result: PhaseEnvelopeResult
+) -> Any:
+    missing = tuple(
+        branch
+        for branch in (result.bubble_branch, result.dew_branch)
+        if not branch.points
+    )
+    for index, branch in enumerate(missing):
+        branch_name = status_text(branch.branch_kind)
+        reason = status_text(branch.termination_reason)
+        figure.add_annotation(
+            x=0.01,
+            y=0.99 - 0.1 * index,
+            xref="paper",
+            yref="paper",
+            xanchor="left",
+            yanchor="top",
+            showarrow=False,
+            align="left",
+            text=(
+                f"{branch_name} branch not plotted — {reason}: "
+                f"{branch.termination_message}"
+            ),
+            borderpad=5,
+            bgcolor="rgba(255,255,255,0.9)",
+        )
+    return figure
 
 
 def _stale(name: str, inputs: ScientificInputs | None) -> bool:
@@ -106,7 +151,7 @@ def _composition_table(result: TwoPhaseFlashResult) -> None:
         pd.DataFrame(rows, index=COMPONENT_NAMES).T,
         width="stretch",
         column_config={
-            name: st.column_config.NumberColumn(name, format="%.8g mol %")
+            name: st.column_config.NumberColumn(name, format="%.6g mol %")
             for name in COMPONENT_NAMES
         },
     )
@@ -134,7 +179,7 @@ def _flash_details(result: TwoPhaseFlashResult) -> None:
             ),
             (
                 "Single-phase root",
-                _optional(view.single_phase_z, 10),
+                _full_precision(view.single_phase_z),
                 "Z, dimensionless",
             ),
         ]
@@ -144,25 +189,25 @@ def _flash_details(result: TwoPhaseFlashResult) -> None:
         component_rows.append(
             {
                 "Component": name,
-                "K value": (
+                "K value": _full_precision(
                     None if view.final_k_values is None else view.final_k_values[index]
                 ),
-                "Equilibrium residual": (
+                "Equilibrium residual": _full_precision(
                     view.equilibrium_residuals[index]
                     if index < len(view.equilibrium_residuals)
                     else None
                 ),
-                "Material-balance residual": (
+                "Material-balance residual": _full_precision(
                     view.material_balance_residuals[index]
                     if index < len(view.material_balance_residuals)
                     else None
                 ),
-                "Liquid fugacity coefficient": (
+                "Liquid fugacity coefficient": _full_precision(
                     None
                     if result.liquid_phase is None
                     else result.liquid_phase.component_fugacity_coefficients[index]
                 ),
-                "Vapor fugacity coefficient": (
+                "Vapor fugacity coefficient": _full_precision(
                     None
                     if result.vapor_phase is None
                     else result.vapor_phase.component_fugacity_coefficients[index]
@@ -173,16 +218,6 @@ def _flash_details(result: TwoPhaseFlashResult) -> None:
         pd.DataFrame(component_rows),
         hide_index=True,
         width="stretch",
-        column_config={
-            column: st.column_config.NumberColumn(format="%.6e")
-            for column in (
-                "K value",
-                "Equilibrium residual",
-                "Material-balance residual",
-                "Liquid fugacity coefficient",
-                "Vapor fugacity coefficient",
-            )
-        },
     )
     phase_rows = []
     for name, phase in (("Liquid", result.liquid_phase), ("Vapor", result.vapor_phase)):
@@ -194,7 +229,7 @@ def _flash_details(result: TwoPhaseFlashResult) -> None:
                     "Mechanical class": _value(phase.mechanical_classification),
                     "Root policy": _value(phase.root_selection.trial_kind),
                     "Candidate roots": ", ".join(
-                        f"{root.compressibility_factor:.8g}"
+                        repr(float(root.compressibility_factor))
                         for root in phase.root_selection.candidates
                     ),
                 }
@@ -229,21 +264,21 @@ def render_overview(inputs: ScientificInputs | None) -> None:
                 icon=":material/error:",
             )
     state_columns = st.columns(4, vertical_alignment="center")
-    state_columns[0].metric("Temperature", f"{view.temperature_k:.8g} K")
-    state_columns[1].metric("Pressure", f"{view.pressure_pa / PA_PER_MPA:.10g} MPa")
+    state_columns[0].metric("Temperature", f"{view.temperature_k:.6g} K")
+    state_columns[1].metric("Pressure", f"{view.pressure_pa / PA_PER_MPA:.6g} MPa")
     state_columns[2].metric("Model", "Peng-Robinson")
     state_columns[3].metric("Interactions", "kij = 0")
     phase_columns = st.columns(4, vertical_alignment="center")
     phase_columns[0].metric("Vapor fraction", _optional(view.vapor_fraction))
     phase_columns[1].metric("Liquid fraction", _optional(view.liquid_fraction))
-    phase_columns[2].metric("Vapor Z", _optional(view.vapor_z, 10))
-    phase_columns[3].metric("Liquid Z", _optional(view.liquid_z, 10))
+    phase_columns[2].metric("Vapor Z", _optional(view.vapor_z))
+    phase_columns[3].metric("Liquid Z", _optional(view.liquid_z))
     if view.vapor_fraction is not None and view.liquid_fraction is not None:
         st.caption("Engineering phase split · liquid / vapor")
         phase_split_bar(view.vapor_fraction, view.liquid_fraction)
     if view.single_phase_z is not None:
         st.info(
-            f"Single-phase selected root: Z = {view.single_phase_z:.10g}. "
+            f"Single-phase selected root: Z = {view.single_phase_z:.6g}. "
             "It is not relabelled as a liquid or vapor root."
         )
     st.subheader("Source-provided phase compositions")
@@ -264,14 +299,16 @@ def render_overview(inputs: ScientificInputs | None) -> None:
             st.json(asdict(result))
 
 
+@st.cache_data(show_spinner=False, max_entries=8)
 def _calculate_envelope(inputs: ScientificInputs) -> PhaseEnvelopeResult:
+    start_temperature_k = inputs.temperature_k - 30.0
     settings = EnvelopeContinuationSettings(
-        target_temperature_k=inputs.temperature_k + 50.0,
+        target_temperature_k=inputs.temperature_k + 30.0,
         initial_temperature_step_k=5.0,
         maximum_points=15,
     )
     return calculate_phase_envelope(
-        inputs.mixture(), settings, settings, inputs.temperature_k, inputs.temperature_k
+        inputs.mixture(), settings, settings, start_temperature_k, start_temperature_k
     )
 
 
@@ -290,6 +327,12 @@ def render_phase_envelope(inputs: ScientificInputs | None) -> None:
     ):
         assert inputs is not None
         with st.status("Tracing bubble and dew branches…", expanded=True) as status:
+            status.write(
+                "Cold-starting below the operating point, then continuing both "
+                "branches through its temperature."
+            )
+            status.write("Typical first run: about 20–30 seconds.")
+            status.caption("An unchanged submitted case reuses the bounded UI cache.")
             try:
                 result = _calculate_envelope(inputs)
                 store_result(session(), "envelope", result, inputs)
@@ -297,6 +340,7 @@ def render_phase_envelope(inputs: ScientificInputs | None) -> None:
             except (ValueError, ArithmeticError) as error:
                 status.update(label="Envelope trace failed", state="error")
                 st.error(f"Phase-envelope calculation could not start: {error}")
+    _action_requirement(inputs)
     raw = get_result(session(), "envelope")
     if raw is None:
         st.info("No calculated envelope is available.", icon=":material/info:")
@@ -308,14 +352,17 @@ def render_phase_envelope(inputs: ScientificInputs | None) -> None:
     )
     if result_is_stale(session(), "critical", inputs):
         critical = None
-    st.plotly_chart(
-        plot_phase_envelope(
+    _wide_chart(
+        _annotate_missing_envelope_branches(
+            plot_phase_envelope(
+                result,
+                pressure_unit=PressureUnit.MPA,
+                critical_point=critical,
+                metadata={"model": "Peng-Robinson EOS; kij=0"},
+            ),
             result,
-            pressure_unit=PressureUnit.MPA,
-            critical_point=critical,
-            metadata={"model": "Peng-Robinson EOS; kij=0"},
         ),
-        width="stretch",
+        key="phase_envelope_chart",
     )
     _status_rows(
         [
@@ -323,13 +370,15 @@ def render_phase_envelope(inputs: ScientificInputs | None) -> None:
                 "Bubble branch",
                 status_text(result.bubble_branch.termination_reason),
                 f"{len(result.bubble_branch.points)} accepted; "
-                f"{len(result.bubble_branch.rejected_attempts)} rejected",
+                f"{len(result.bubble_branch.rejected_attempts)} rejected; "
+                f"{result.bubble_branch.termination_message}",
             ),
             (
                 "Dew branch",
                 status_text(result.dew_branch.termination_reason),
                 f"{len(result.dew_branch.points)} accepted; "
-                f"{len(result.dew_branch.rejected_attempts)} rejected",
+                f"{len(result.dew_branch.rejected_attempts)} rejected; "
+                f"{result.dew_branch.termination_message}",
             ),
         ]
     )
@@ -351,7 +400,7 @@ def render_phase_envelope(inputs: ScientificInputs | None) -> None:
     )
     if st.button("SHOW PHASE COMPOSITIONS", icon=":material/show_chart:"):
         try:
-            st.plotly_chart(
+            _wide_chart(
                 plot_phase_compositions(
                     result,
                     branch=branch,
@@ -359,12 +408,13 @@ def render_phase_envelope(inputs: ScientificInputs | None) -> None:
                     display=CompositionDisplay.MOL_PERCENT,
                     pressure_unit=PressureUnit.MPA,
                 ),
-                width="stretch",
+                key="phase_compositions_chart",
             )
         except ValueError as error:
             st.info(f"Phase-composition figure unavailable: {error}")
 
 
+@st.cache_data(show_spinner=False, max_entries=8)
 def _calculate_critical(inputs: ScientificInputs) -> MixtureCriticalPointResult:
     return solve_mixture_critical_point(
         inputs.mixture(),
@@ -374,6 +424,7 @@ def _calculate_critical(inputs: ScientificInputs) -> MixtureCriticalPointResult:
     )
 
 
+@st.cache_data(show_spinner=False, max_entries=8)
 def _calculate_scan(inputs: ScientificInputs) -> CriticalPointScanResult:
     return scan_mixture_criticality(
         inputs.mixture(),
@@ -391,8 +442,9 @@ def _calculate_scan(inputs: ScientificInputs) -> CriticalPointScanResult:
 def render_critical_point(inputs: ScientificInputs | None) -> None:
     st.header("Critical point")
     st.caption(
-        "Certification requires CriticalPointStatus.CONVERGED; a spinodal or "
-        "lambda_min = 0 is insufficient."
+        "Certification requires solver convergence on both criticality conditions. "
+        "A zero minimum stability eigenvalue alone identifies a spinodal condition, "
+        "not a critical point."
     )
     with st.container(horizontal=True):
         run_solver = st.button(
@@ -406,6 +458,7 @@ def render_critical_point(inputs: ScientificInputs | None) -> None:
             disabled=inputs is None,
             icon=":material/grid_on:",
         )
+    _action_requirement(inputs)
     if run_solver:
         assert inputs is not None
         with st.status("Solving production critical conditions…") as status:
@@ -436,9 +489,9 @@ def render_critical_point(inputs: ScientificInputs | None) -> None:
         if view.certified:
             st.success("CERTIFIED CRITICAL POINT", icon=":material/verified:")
             certified = st.columns(2)
-            certified[0].metric("Tc", f"{cast(float, view.temperature_k):.10g} K")
+            certified[0].metric("Tc", f"{cast(float, view.temperature_k):.6g} K")
             certified[1].metric(
-                "Pc", f"{cast(float, view.pressure_pa) / PA_PER_MPA:.10g} MPa"
+                "Pc", f"{cast(float, view.pressure_pa) / PA_PER_MPA:.6g} MPa"
             )
         else:
             st.error(
@@ -452,22 +505,22 @@ def render_critical_point(inputs: ScientificInputs | None) -> None:
                 ("Iterations", str(view.iterations), "Solver iterations"),
                 (
                     "lambda_min",
-                    _scientific(result.lambda_min),
+                    _full_precision(result.lambda_min),
                     "Dimensionless critical residual",
                 ),
                 (
                     "C",
-                    _scientific(result.cubic_coefficient),
+                    _full_precision(result.cubic_coefficient),
                     "Critical cubic coefficient",
                 ),
                 (
                     "Scaled residual",
-                    _scientific(result.scaled_residual_norm),
+                    _full_precision(result.scaled_residual_norm),
                     "Dimensionless",
                 ),
                 (
                     "Jacobian conditioning",
-                    _scientific(
+                    _full_precision(
                         result.jacobian_condition_history[-1]
                         if result.jacobian_condition_history
                         else None
@@ -485,13 +538,17 @@ def render_critical_point(inputs: ScientificInputs | None) -> None:
         )
         if st.toggle("Show critical solver figures", key="critical_figures"):
             if result.history:
-                st.plotly_chart(
-                    plot_critical_solver_convergence(result), width="stretch"
+                _wide_chart(
+                    plot_critical_solver_convergence(result),
+                    key="critical_convergence_chart",
+                )
+                _wide_chart(
+                    plot_critical_solver_path(result), key="critical_path_chart"
                 )
-                st.plotly_chart(plot_critical_solver_path(result), width="stretch")
             if result.jacobian_condition_history:
-                st.plotly_chart(
-                    plot_critical_solver_conditioning(result), width="stretch"
+                _wide_chart(
+                    plot_critical_solver_conditioning(result),
+                    key="critical_conditioning_chart",
                 )
     scan_raw = get_result(session(), "critical_scan")
     if scan_raw is not None:
@@ -499,14 +556,14 @@ def render_critical_point(inputs: ScientificInputs | None) -> None:
         overlay = cast(MixtureCriticalPointResult | None, raw)
         if result_is_stale(session(), "critical", inputs):
             overlay = None
-        st.plotly_chart(
+        _wide_chart(
             plot_criticality_map(
                 cast(CriticalPointScanResult, scan_raw),
                 pressure_unit=PressureUnit.MPA,
                 critical_point=overlay,
                 metadata={"model": "Peng-Robinson EOS; kij=0"},
             ),
-            width="stretch",
+            key="criticality_map_chart",
         )
 
 
@@ -545,6 +602,14 @@ def render_validation() -> None:
             "Displayed figures are stale for the selected direction. Generate again."
         )
     records = _records()
+    state_count, error_count, median_error, worst_error = (
+        validation_pressure_error_summary(records, selected)
+    )
+    summary = st.columns(4)
+    summary[0].metric("Module 17 states", str(state_count))
+    summary[1].metric(f"{selected.capitalize()} error records", str(error_count))
+    summary[2].metric("Median absolute pressure error", _optional(median_error) + "%")
+    summary[3].metric("Worst absolute pressure error", _optional(worst_error) + "%")
     with st.status("Rendering Module 21 validation figures…") as status:
         figures = (
             plot_validation_pressure_parity(
@@ -567,10 +632,11 @@ def render_validation() -> None:
         else:
             composition_error = None
         status.update(label="Production validation figures ready", state="complete")
-    for figure in figures:
-        st.plotly_chart(figure, width="stretch")
+    _square_chart(figures[0], key="validation_pressure_parity")
+    _wide_chart(figures[1], key="validation_pressure_error")
+    _wide_chart(figures[2], key="validation_status")
     if composition_figure is not None:
-        st.plotly_chart(composition_figure, width="stretch")
+        _square_chart(composition_figure, key="validation_composition_parity")
     elif composition_error is not None:
         st.info(f"Composition parity unavailable: {composition_error}")
     st.subheader("Retrospective nearest-root diagnostics")
@@ -579,11 +645,11 @@ def render_validation() -> None:
         icon=":material/warning:",
     )
     try:
-        st.plotly_chart(
+        _wide_chart(
             plot_validation_retrospective_diagnostics(
                 records, pressure_unit=PressureUnit.MPA
             ),
-            width="stretch",
+            key="validation_retrospective",
         )
     except ValueError as error:
         st.info(f"Retrospective diagnostics unavailable: {error}")
@@ -644,17 +710,17 @@ def render_diagnostics(inputs: ScientificInputs | None) -> None:
                     ("Latest iteration", str(latest.iteration), "Iteration index"),
                     (
                         "Maximum log-K residual",
-                        _scientific(latest.maximum_log_k_residual),
+                        _full_precision(latest.maximum_log_k_residual),
                         "Dimensionless",
                     ),
                     (
                         "Maximum equilibrium residual",
-                        _scientific(latest.maximum_fugacity_equilibrium_residual),
+                        _full_precision(latest.maximum_fugacity_equilibrium_residual),
                         "Dimensionless",
                     ),
                     (
                         "Maximum material-balance residual",
-                        _scientific(
+                        _full_precision(
                             latest.phase_compositions.maximum_material_balance_residual
                         ),
                         "Mole fraction",
diff --git a/tests/test_app_adapters.py b/tests/test_app_adapters.py
index db78e56..6a5f14e 100644
--- a/tests/test_app_adapters.py
+++ b/tests/test_app_adapters.py
@@ -5,6 +5,7 @@ from __future__ import annotations
 import hashlib
 from dataclasses import replace
 from pathlib import Path
+from types import SimpleNamespace
 from typing import cast
 
 import pytest
@@ -21,14 +22,17 @@ from pvt_phase_simulator.plotting import (
     plot_validation_pressure_parity,
     plot_validation_retrospective_diagnostics,
 )
+from pvt_phase_simulator_ui import views
 from pvt_phase_simulator_ui.adapters import (
     InputValidationError,
     adapt_critical_result,
     adapt_flash_result,
     load_module17_records,
+    location_relative_to_envelope,
     relative_pressure_error_percent,
     run_validated_flash,
     validate_scientific_inputs,
+    validation_pressure_error_summary,
 )
 from pvt_phase_simulator_ui.state import (
     get_result,
@@ -190,6 +194,103 @@ def test_module21_validation_figures_keep_sign_and_retrospective_separation() ->
     assert relative_pressure_error_percent(110.0, 100.0) == 10.0
 
 
+def test_validation_summary_uses_only_recorded_absolute_pressure_errors() -> None:
+    records = load_module17_records(ROOT)
+    state_count, error_count, median_error, worst_error = (
+        validation_pressure_error_summary(records, "bubble")
+    )
+    recorded = sorted(
+        abs(cast(float, record.bubble_pressure_relative_error)) * 100.0
+        for record in records
+        if record.bubble_pressure_relative_error is not None
+    )
+    assert state_count == len(records)
+    assert error_count == len(recorded)
+    assert median_error == pytest.approx(
+        (recorded[(len(recorded) - 1) // 2] + recorded[len(recorded) // 2]) / 2.0
+    )
+    assert worst_error == max(recorded)
+
+
+def test_operating_point_reports_available_branch_and_missing_reason() -> None:
+    def point(temperature_k: float, pressure_pa: float) -> SimpleNamespace:
+        return SimpleNamespace(
+            temperature_k=temperature_k,
+            pressure_pa=pressure_pa,
+            status="converged",
+        )
+
+    result = SimpleNamespace(
+        bubble_branch=SimpleNamespace(
+            points=(), termination_message="Bubble bracket was not found."
+        ),
+        dew_branch=SimpleNamespace(
+            points=(point(290.0, 2.0e6), point(310.0, 3.0e6)),
+            termination_message="Target temperature reached.",
+        ),
+    )
+    message = location_relative_to_envelope(  # type: ignore[arg-type]
+        result, 300.0, 5.0e6
+    )
+    assert message == (
+        "Above the interpolated dew branch. Bubble branch unavailable: "
+        "Bubble bracket was not found."
+    )
+
+
+def test_ui_envelope_trace_is_centered_on_operating_temperature(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    inputs = validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 5.0)
+    captured: dict[str, object] = {}
+    sentinel = object()
+
+    def fake_calculate(*args: object) -> object:
+        captured["args"] = args
+        return sentinel
+
+    views._calculate_envelope.clear()
+    monkeypatch.setattr(views, "calculate_phase_envelope", fake_calculate)
+    result = views._calculate_envelope(inputs)
+    args = cast(tuple[object, ...], captured["args"])
+    bubble_settings = args[1]
+    dew_settings = args[2]
+    assert result is sentinel
+    assert args[3:] == (270.0, 270.0)
+    assert bubble_settings.target_temperature_k == 330.0  # type: ignore[attr-defined]
+    assert dew_settings.target_temperature_k == 330.0  # type: ignore[attr-defined]
+    assert bubble_settings.initial_temperature_step_k == 5.0  # type: ignore[attr-defined]
+    assert bubble_settings.maximum_points == 15  # type: ignore[attr-defined]
+
+
+def test_empty_envelope_branch_is_annotated_with_engine_termination() -> None:
+    annotations: list[dict[str, object]] = []
+    figure = SimpleNamespace(add_annotation=lambda **kwargs: annotations.append(kwargs))
+    result = SimpleNamespace(
+        bubble_branch=SimpleNamespace(
+            branch_kind="bubble",
+            points=(),
+            termination_reason="corrector_failed",
+            termination_message="No trustworthy bracket was found.",
+        ),
+        dew_branch=SimpleNamespace(
+            branch_kind="dew",
+            points=(object(),),
+            termination_reason="target_reached",
+            termination_message="Target reached.",
+        ),
+    )
+    returned = views._annotate_missing_envelope_branches(  # type: ignore[arg-type]
+        figure, result
+    )
+    assert returned is figure
+    assert len(annotations) == 1
+    assert annotations[0]["text"] == (
+        "Bubble branch not plotted — Corrector failed: "
+        "No trustworthy bracket was found."
+    )
+
+
 def test_app_code_contains_labels_but_no_thermodynamic_implementation() -> None:
     sources = "\n".join(
         path.read_text(encoding="utf-8")
diff --git a/tests/test_app_streamlit.py b/tests/test_app_streamlit.py
index ffd35a4..a91fb35 100644
--- a/tests/test_app_streamlit.py
+++ b/tests/test_app_streamlit.py
@@ -91,6 +91,7 @@ def test_navigation_module21_reuse_and_no_deprecated_width_argument() -> None:
         for path in (ROOT / "src" / "pvt_phase_simulator_ui").rglob("*.py")
     )
     assert "st.navigation" in app_source
+    assert 'position="sidebar"' in app_source
     assert app_source.count("st.Page(") == 5
     assert "st.form(" in app_source
     assert "st.form_submit_button(" in app_source
@@ -101,6 +102,28 @@ def test_navigation_module21_reuse_and_no_deprecated_width_argument() -> None:
     assert "use_container_width" not in all_ui_source
 
 
+def test_disabled_scientific_actions_explain_flash_requirement() -> None:
+    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
+    phase_page = ROOT / "src" / "pvt_phase_simulator_ui" / "pages" / "phase_envelope.py"
+    app.switch_page(phase_page).run()
+    phase_action = next(
+        button for button in app.button if button.label == "RUN PHASE ENVELOPE"
+    )
+    assert phase_action.disabled
+    assert any("Submit RUN FLASH to enable" in caption.value for caption in app.caption)
+
+    critical_page = (
+        ROOT / "src" / "pvt_phase_simulator_ui" / "pages" / "critical_point.py"
+    )
+    app.switch_page(critical_page).run()
+    critical_actions = [
+        button for button in app.button if button.label.startswith("RUN CRITICAL")
+    ]
+    assert len(critical_actions) == 2
+    assert all(button.disabled for button in critical_actions)
+    assert any("Submit RUN FLASH to enable" in caption.value for caption in app.caption)
+
+
 def test_ui_contains_no_duplicated_thermodynamic_implementations() -> None:
     source = "\n".join(
         path.read_text(encoding="utf-8").lower()

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
