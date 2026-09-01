# Independent audit: streamlit_engineering_ui_refinement

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
- Name: streamlit_engineering_ui_refinement
- Declared risk: MEDIUM
- Objective: Refine the existing, independently audited Streamlit frontend into a polished engineering-grade scientific application without changing any thermodynamic calculation, scientific result, public scientific API, or validation artifact. This is an application architecture, launch reliability, interaction design, accessibility, information hierarchy, and deployment-readiness package; it must improve the existing application rather than rebuild it.

Fix the clean-shell launch failure in which `uv run streamlit run app/streamlit_app.py` raises `ModuleNotFoundError: No module named 'app'`. Do not use `sys.path` mutation or require a manual `PYTHONPATH`. Inspect the uv-build packaging configuration and migrate the application layer to a clearly named installed package such as `src/pvt_phase_simulator_ui`, separate from the protected `src/pvt_phase_simulator` scientific package. A thin root `streamlit_app.py` may be used when it provides the cleanest stable Streamlit entrypoint. Configure packaging only as needed, preserve reproducible `uv` operation, document one normal launch command that works from a clean shell, and add a subprocess/startup regression test that reproduces Streamlit's real import context and would have caught the current failure. Do not introduce absolute machine paths, Windows-only runtime behavior, filesystem writes, or deployment in this package.

Use installed Streamlit 1.60 public APIs and native components wherever possible. Replace the horizontal radio-button navigation with `st.navigation` and `st.Page` using a clear active state for Overview, Phase Envelope, Critical Point, Validation, and Diagnostics; keep global fluid inputs in the sidebar. Organize page modules and shared session state cleanly within the installed UI package. Use `st.form` or an equally explicit submit boundary for Methane/Ethane/Propane mol %, temperature K, and pressure MPa so editing individual number fields does not trigger heavy application work. Retain precise number entry rather than sliders, exact composition validation, exact mol-percent-to-fraction and MPa-to-Pa conversion, explicit scientific actions, deterministic stale-result behavior, and prominent full-width RUN FLASH semantics. Invalid input must explain why submission is unavailable.

Adopt a restrained light engineering visual system primarily through `.streamlit/config.toml`: white/off-white surfaces, dark navy readable typography, restrained teal/blue accent, thin visible borders, modest radii, accessible status colors, coherent chart colors, and a focused sidebar. Correct hidden, clipped, disabled-looking, white-on-light, gray-on-gray, hover-dependent, and selected-navigation contrast failures. Prefer native theme and layout APIs over internal `data-testid` selectors; retain only narrowly scoped custom CSS where native Streamlit cannot express a required engineering visualization. Remove deprecated `use_container_width` usage in favor of current width semantics. Use sentence casing and restrained Material Symbols where they improve comprehension. Do not add gradients, glassmorphism, neon, fake gauges, or decorative animation.

Create a concise header hierarchy without repeated wording: `PVT PHASE SIMULATOR`, `Hydrocarbon Phase Behavior`, and `Peng-Robinson EOS - 3 verified components - kij = 0`. On Overview, make the entered composition, temperature, pressure, and model immediately legible; make phase and convergence the strongest result; show vapor/liquid fractions, available Z factors, source-provided phase compositions, and a restrained engineering phase-split bar without fabricating unavailable quantities. Show operating-point location relative to an existing calculated phase envelope and overlay the operating point when supported by the existing Module 21 plotting API; if no envelope exists, provide a clear action/status instead of fabricating one. Avoid ragged metric-card layouts.

Redesign Technical Details and Diagnostics as engineering output rather than raw/debug output. Always show applicable solver status, converged/not-converged state, termination or failure reason, and iteration count. Present K values, equilibrium and material-balance residuals, fugacity coefficients, phase/root information, continuation evidence, Jacobian/conditioning evidence, and units through labelled status rows and tables using scientific notation where appropriate. Raw public-object or JSON inspection may remain only behind a secondary advanced toggle and must never become the primary presentation. Preserve every structured failure and never convert failure information into plausible success.

Make the Phase Envelope plot the primary content and preserve bubble/dew identity, converged/unavailable status semantics, operating-point display, certified critical overlays, and the distinction between continuation turning points and critical points. Present completed, bounded-stop, and failure states as statuses rather than numeric metrics. Expose only existing safely bounded trace settings; do not change continuation science. On Critical Point, show `CERTIFIED CRITICAL POINT` with Tc and Pc only for an existing production result certified by `CriticalPointStatus.CONVERGED`, followed by existing lambda_min, C, scaled residual, iterations, conditioning, and critical direction evidence. Otherwise show `NOT CERTIFIED` with the production reason and no certified Tc/Pc; lambda_min=0 and spinodal status alone remain insufficient.

Lead Validation with a concise, honest summary of the existing experimental dataset, state count, kij=0, unfitted-model status, and only error metrics supported by the protected records. Do not replace measured performance with a generic green validated badge. Continue using Module 21 parity, error, composition, status, and retrospective plotting functions. Keep retrospective nearest-root diagnostics in a strongly separated section whose `NOT PRODUCTION PREDICTIONS` label remains visually associated with its chart, and preserve signed relative pressure error `100*(P_pred-P_exp)/P_exp`.

Bound expensive UI-triggered work. Heavy flash, envelope, critical-point, criticality-map, validation-figure, and diagnostic work must remain behind explicit actions, submitted state, guarded dynamic sections, or appropriately bounded caching without changing numerical results or sharing mutable per-user state. Render stable UI before slow work and provide honest progress/status feedback. Do not execute hidden expensive content merely because it sits inside a tab or collapsed expander. Preserve per-session result identity across navigation and cosmetic reruns.

Add semantic tests covering installed UI-package and styles imports, clean-shell launch without PYTHONPATH, Streamlit startup/AppTest behavior, explicit form-submit boundaries, input validation, exact unit conversions, production flash invocation, phase/fraction/composition/Z identity, structured failure presentation, critical certification rejection, Module 21 plotting reuse, retrospective labelling, protected scientific integrity, and absence of duplicated thermodynamic implementations. Avoid screenshot-pixel tests as the primary evidence. Update only the Streamlit application documentation and truthful README launch instructions. Prepare for a later public Streamlit deployment but do not deploy.

The scientific engine is frozen. Do not modify `src/pvt_phase_simulator`, `data`, `docs/validation`, golden-master/reference artifacts, or any pre-existing scientific test. Do not implement or duplicate Peng-Robinson, mixing rules, fugacity, Rachford-Rice, TPD, saturation, bubble/dew, phase-envelope continuation, Gibbs-curvature, or critical-point equations in the UI. Existing production APIs remain the only scientific source of truth and Module 21 Figure-returning APIs remain reused. Do not add components, kij editing, C7+/pseudocomponents, density, Bo, GOR, CCE, CVD, depletion, separators, pressure/temperature sweeps, field units, desktop packaging, case management, new datasets, or public deployment.

## Scientific invariants claimed to hold
  - Every file under src/pvt_phase_simulator remains unchanged; the separately installed UI package may import only existing public scientific and Module 21 plotting APIs.
  - No Peng-Robinson, mixing-rule, fugacity, Rachford-Rice, TPD, saturation, phase-envelope, pseudo-arclength, Gibbs-curvature, or critical-point equation is duplicated in the UI.
  - Internal pressure remains SI Pa; validated UI input converts MPa to Pa exactly once with MPa * 1e6, and display converts Pa to MPa without changing production results.
  - Methane, Ethane, and Propane mol-percent input is converted to mole fractions only after finite, nonnegative, positive-total, materially 100-percent validation; invalid input is never silently normalized and cannot invoke a scientific API.
  - The existing flash result remains the source of phase, convergence, vapor/liquid fractions, x/y compositions, Z factors, K values, residuals, iterations, roots, and failure information; presentation code does not reclassify or fill unavailable values.
  - Bubble and dew identities, structured unavailable points, and continuation terminations remain unchanged; operating-point presentation does not fabricate an envelope, and turning points are never labelled critical points.
  - Only a production MixtureCriticalPointResult with CriticalPointStatus.CONVERGED may display certified Tc/Pc; lambda_min=0 or a spinodal condition alone never certifies criticality.
  - Module 17 production predictions remain separate from retrospective nearest-root diagnostics labelled NOT PRODUCTION PREDICTIONS, relative pressure error remains 100*(P_pred-P_exp)/P_exp, and validation remains kij=0 with no fitted interaction parameters.
  - Session state remains per-user and preserves deliberate calculation results across navigation/cosmetic reruns while identifying results as stale after scientific inputs change.
  - Golden master, component-property, and Module 17 validation artifacts remain byte-identical and are never regenerated.
  - All 1137 pre-existing scientific tests remain present and unchanged; application tests add coverage without weakening any scientific test, tolerance, baseline, or expected value.
  - Verified frontend property scope remains Methane, Ethane, and Propane; no claim of arbitrary reservoir-fluid validation or commercial-PVT readiness is introduced.
  - No new thermodynamic feature, component, interaction-parameter editor, C7+ model, density/Bo/GOR output, CCE/CVD/depletion/separator workflow, sweep, field-unit system, desktop packaging, case management, dataset, or deployment is added.

## Repository state
- Branch: `master`
- HEAD: `b94f3ef69351caeeaa6abacae5ec30103e1a88ef`
- Base for this change: `b94f3ef69351caeeaa6abacae5ec30103e1a88ef`

## Findings this correction was meant to close
  - **B-1** (B): The mandated .streamlit/config.toml light-engineering theme was created in the original build, then deleted in correction cycle 1 to dodge a scope-checker false positive (the file was actually on the allowed list), and was never restored in the two subsequent correction cycles. The application now renders under Streamlit's unmodified stock theme, so none of the specified visual requirements (surface colors, teal/blue accent, contrast fixes for disabled/hover/selected-nav states) are actually implemented. docs/STREAMLIT_APPLICATION.md:33 still falsely states that '.streamlit/config.toml supplies the light engineering theme.'

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
        PASS  .venv/Scripts/python.exe -m mypy src
        PASS  .venv/Scripts/python.exe -m compileall -q src
        PASS  uv lock --check
        PASS  uv run python -c import pvt_phase_simulator_ui; import pvt_phase_simulator_ui.styles
        PASS  git diff --check
```
Changed files: ['.streamlit/config.toml', 'README.md', 'app/adapters.py', 'app/state.py', 'app/streamlit_app.py', 'app/styles.py', 'docs/STREAMLIT_APPLICATION.md', 'pyproject.toml', 'src/pvt_phase_simulator_ui/__init__.py', 'src/pvt_phase_simulator_ui/adapters.py', 'src/pvt_phase_simulator_ui/app.py', 'src/pvt_phase_simulator_ui/context.py', 'src/pvt_phase_simulator_ui/pages/__init__.py', 'src/pvt_phase_simulator_ui/pages/critical_point.py', 'src/pvt_phase_simulator_ui/pages/diagnostics.py', 'src/pvt_phase_simulator_ui/pages/overview.py', 'src/pvt_phase_simulator_ui/pages/phase_envelope.py', 'src/pvt_phase_simulator_ui/pages/validation.py', 'src/pvt_phase_simulator_ui/state.py', 'src/pvt_phase_simulator_ui/styles.py', 'src/pvt_phase_simulator_ui/views.py', 'streamlit_app.py', 'tests/test_app_adapters.py', 'tests/test_app_streamlit.py']

## Builder's own report — treat as an unverified claim
```
Targeted B-1 correction: restored the original native light engineering theme at .streamlit/config.toml. Documentation already truthfully references that file. No application or scientific code was changed for B-1. The untracked-directory scope bug was fixed and committed separately before this package verification.
```

## Diff stat
```
 .ai/workflow_state.json       | 142 ++++++++---
 README.md                     |   9 +-
 app/adapters.py               | 293 +---------------------
 app/state.py                  |  56 +----
 app/streamlit_app.py          | 566 +-----------------------------------------
 app/styles.py                 |  52 +---
 docs/STREAMLIT_APPLICATION.md |  31 ++-
 pyproject.toml                |   3 +
 tests/test_app_adapters.py    |  30 ++-
 9 files changed, 160 insertions(+), 1022 deletions(-)

```

## Full diff
```diff
diff --git a/.ai/workflow_state.json b/.ai/workflow_state.json
index bb50ea8..20d5cf2 100644
--- a/.ai/workflow_state.json
+++ b/.ai/workflow_state.json
@@ -1,45 +1,30 @@
 {
   "project": "pvt-phase-simulator",
   "phase": "post-v1.0-extensions",
-  "workflow_status": "IDLE",
+  "workflow_status": "CLAUDE_RUNNING",
   "last_scientific_commit": "da5594f",
   "last_independent_audit_commit": "da5594f",
   "work_packages_since_audit": 0,
-  "current_work_package": null,
-  "current_risk": null,
-  "audit_required": false,
-  "audit_reason": null,
-  "blocking_findings": [],
-  "safe_defer_findings": [
-    {
-      "id": "M20-D-1",
-      "category": "D",
-      "location": "src/pvt_phase_simulator/eos/critical_point.py",
-      "summary": "Root-continuity sub-checks are mutually redundant; diagnostic-quality only, no false convergence.",
-      "blocks_release": false
-    },
-    {
-      "id": "FINAL-D-1-residual",
-      "category": "D",
-      "location": "src/pvt_phase_simulator/eos/phase_stability.py",
-      "summary": "Near-critical trivial-solution collapse remains present in code; now explicitly documented in README. Behavioural fix is separate future work.",
-      "blocks_release": false
-    },
-    {
-      "id": "STREAMLIT-D-1",
-      "category": "D",
-      "location": "tests/test_app_adapters.py, app/streamlit_app.py",
-      "summary": "No test imports app.streamlit_app or app.styles, so the entrypoint has no import/type regression guard. Auditor also claimed the gates omit app/, but the package's required_tests do run 'mypy src app' and 'compileall src app' (both exit 0 in the recorded verification); only the import smoke test is genuinely missing.",
-      "blocks_release": false
+  "current_work_package": "streamlit_engineering_ui_refinement",
+  "current_risk": "MEDIUM",
+  "audit_required": true,
+  "audit_reason": "targeted re-audit after externally repaired VERIFY failure",
+  "blocking_findings": [
+    {
+      "id": "B-1",
+      "severity": "B",
+      "blocks": true,
+      "summary": "The mandated .streamlit/config.toml light-engineering theme was created in the original build, then deleted in correction cycle 1 to dodge a scope-checker false positive (the file was actually on the allowed list), and was never restored in the two subsequent correction cycles. The application now renders under Streamlit's unmodified stock theme, so none of the specified visual requirements (surface colors, teal/blue accent, contrast fixes for disabled/hover/selected-nav states) are actually implemented. docs/STREAMLIT_APPLICATION.md:33 still falsely states that '.streamlit/config.toml supplies the light engineering theme.'"
     }
   ],
+  "safe_defer_findings": [],
   "planned_scope": "Original 21-module Hydrocarbon Phase-Behavior & PVT Simulator",
   "planned_scope_complete": true,
-  "codex_correction_cycles": 0,
-  "claude_reaudit_cycles": 0,
-  "claude_cost_usd_this_package": 2.1170143999999995,
+  "codex_correction_cycles": 3,
+  "claude_reaudit_cycles": 2,
+  "claude_cost_usd_this_package": 0.9313499999999999,
   "claude_cost_unknown_runs": 0,
-  "last_error": null,
+  "last_error": "targeted recovery audit returned CONDITIONAL; no builder or correction invoked",
   "history": [
     {
       "from": "IDLE",
@@ -200,12 +185,91 @@
       "from": "CLAUDE_RUNNING",
       "to": "IDLE",
       "reason": "manually stopped"
+    },
+    {
+      "from": "IDLE",
+      "to": "PLANNING",
+      "reason": "planning streamlit_engineering_ui_refinement"
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
+      "to": "CODEX_CORRECTION",
+      "reason": "correction cycle 2"
+    },
+    {
+      "from": "CODEX_CORRECTION",
+      "to": "LOCAL_VERIFY",
+      "reason": "running local gates"
+    },
+    {
+      "from": "LOCAL_VERIFY",
+      "to": "CODEX_CORRECTION",
+      "reason": "correction cycle 3"
+    },
+    {
+      "from": "CODEX_CORRECTION",
+      "to": "LOCAL_VERIFY",
+      "reason": "running local gates"
+    },
+    {
+      "from": "LOCAL_VERIFY",
+      "to": "HUMAN_ACTION_REQUIRED",
+      "reason": "max_codex_correction_cycles (3) exhausted; all reports preserved."
+    },
+    {
+      "from": "HUMAN_ACTION_REQUIRED",
+      "to": "REAUDIT_PENDING",
+      "reason": "targeted recovery re-audit 1 after external VERIFY repair"
+    },
+    {
+      "from": "REAUDIT_PENDING",
+      "to": "CLAUDE_RUNNING",
+      "reason": "invoking Claude auditor"
+    },
+    {
+      "from": "CLAUDE_RUNNING",
+      "to": "HUMAN_ACTION_REQUIRED",
+      "reason": "targeted recovery audit returned CONDITIONAL; no builder or correction invoked"
+    },
+    {
+      "from": "HUMAN_ACTION_REQUIRED",
+      "to": "REAUDIT_PENDING",
+      "reason": "targeted re-audit 2 for B-1"
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
-    "optional_extensions": "streamlit_full_application COMMITTED at da5594f (audited APPROVED)",
-    "blocking_findings": "NONE"
-  }
-}
\ No newline at end of file
+  ]
+}
diff --git a/README.md b/README.md
index 96c94bc..a7f3859 100644
--- a/README.md
+++ b/README.md
@@ -71,9 +71,13 @@ propane scope. It calls the existing scientific APIs and Module 21 Plotly
 figures without changing the v1.0 engine.
 
 ```powershell
-.venv\Scripts\python.exe -m streamlit run app/streamlit_app.py
+uv run streamlit run streamlit_app.py
 ```
 
+The UI is installed as the separate `pvt_phase_simulator_ui` package. The
+compatibility command `uv run streamlit run app/streamlit_app.py` also works
+from a clean shell without `PYTHONPATH` configuration.
+
 Input validation, explicit calculation actions, stale-result handling, failure
 semantics, supported views, and limitations are documented in
 [`docs/STREAMLIT_APPLICATION.md`](docs/STREAMLIT_APPLICATION.md).
@@ -107,7 +111,8 @@ docs/                            # Scientific documentation
 data/
 └── component_properties.csv     # Human-review/source-tree property mirror
 notebooks/                       # Exploration scaffold
-app/                             # Optional Streamlit application surface
+src/pvt_phase_simulator_ui/      # Installed Streamlit application layer
+streamlit_app.py                 # Stable Streamlit entrypoint
 ```
 
 The package includes a `py.typed` marker and exposes inline type information.
diff --git a/app/adapters.py b/app/adapters.py
index 584c5c3..e6b95ed 100644
--- a/app/adapters.py
+++ b/app/adapters.py
@@ -1,292 +1,3 @@
-"""Pure validation and presentation adapters for the Streamlit application.
+"""Compatibility imports for the installed UI package."""
 
-This module deliberately contains no thermodynamic equations. Production result
-objects remain the sole source of scientific values and statuses.
-"""
-
-from __future__ import annotations
-
-from collections.abc import Callable, Sequence
-from dataclasses import dataclass
-from math import fsum, isfinite
-from pathlib import Path
-from typing import Final
-
-from pvt_phase_simulator.eos.critical_point import (
-    CriticalPointStatus,
-    MixtureCriticalPointResult,
-)
-from pvt_phase_simulator.eos.flash import TwoPhaseFlashResult, calculate_two_phase_flash
-from pvt_phase_simulator.eos.phase_envelope import (
-    PhaseEnvelopePoint,
-    PhaseEnvelopeResult,
-)
-from pvt_phase_simulator.fluid_models import (
-    ETHANE,
-    METHANE,
-    PROPANE,
-    FluidMixture,
-    MixtureComponent,
-)
-from pvt_phase_simulator.plotting import (
-    ValidationPlotRecord,
-    load_validation_plot_records,
-)
-
-COMPONENT_NAMES: Final = ("Methane", "Ethane", "Propane")
-COMPONENTS: Final = (METHANE, ETHANE, PROPANE)
-COMPOSITION_TOTAL_MOL_PERCENT: Final = 100.0
-COMPOSITION_TOLERANCE_MOL_PERCENT: Final = 1.0e-8
-PA_PER_MPA: Final = 1.0e6
-
-
-class InputValidationError(ValueError):
-    """One or more scientific UI inputs are invalid."""
-
-
-@dataclass(frozen=True, slots=True)
-class ScientificInputs:
-    """Validated, converted scientific input supplied to production APIs."""
-
-    composition_mol_percent: tuple[float, float, float]
-    mole_fractions: tuple[float, float, float]
-    temperature_k: float
-    pressure_mpa: float
-    pressure_pa: float
-
-    @property
-    def signature(self) -> tuple[tuple[float, float, float], float, float]:
-        """Return a deterministic state key for stale-result detection."""
-
-        return self.mole_fractions, self.temperature_k, self.pressure_pa
-
-    def mixture(self) -> FluidMixture:
-        """Build the verified three-component production mixture."""
-
-        return FluidMixture(
-            tuple(
-                MixtureComponent(component, fraction)
-                for component, fraction in zip(
-                    COMPONENTS, self.mole_fractions, strict=True
-                )
-            )
-        )
-
-
-def composition_total(values: Sequence[float]) -> float:
-    """Return the exact floating-point sum shown in the UI."""
-
-    return fsum(float(value) for value in values)
-
-
-def validate_scientific_inputs(
-    composition_mol_percent: Sequence[float],
-    temperature_k: float,
-    pressure_mpa: float,
-) -> ScientificInputs:
-    """Validate UI units and convert once to immutable production inputs."""
-
-    if len(composition_mol_percent) != len(COMPONENTS):
-        raise InputValidationError("Exactly Methane, Ethane, and Propane are required.")
-    values = tuple(float(value) for value in composition_mol_percent)
-    if not all(isfinite(value) for value in values):
-        raise InputValidationError("Composition values must be finite.")
-    if any(value < 0.0 for value in values):
-        raise InputValidationError("Composition values cannot be negative.")
-    if any(value > COMPOSITION_TOTAL_MOL_PERCENT for value in values):
-        raise InputValidationError("Each composition value must not exceed 100 mol %.")
-    total = composition_total(values)
-    if total <= 0.0:
-        raise InputValidationError("Composition total must be greater than zero.")
-    if abs(total - COMPOSITION_TOTAL_MOL_PERCENT) > COMPOSITION_TOLERANCE_MOL_PERCENT:
-        raise InputValidationError(
-            "Composition must total 100 mol %. Values are not automatically normalized."
-        )
-    temperature = float(temperature_k)
-    pressure = float(pressure_mpa)
-    if not isfinite(temperature) or temperature <= 0.0:
-        raise InputValidationError("Temperature must be positive and finite.")
-    if not isfinite(pressure) or pressure <= 0.0:
-        raise InputValidationError("Pressure must be positive and finite.")
-    mole_fractions = tuple(value / 100.0 for value in values)
-    return ScientificInputs(
-        (values[0], values[1], values[2]),
-        (mole_fractions[0], mole_fractions[1], mole_fractions[2]),
-        temperature,
-        pressure,
-        pressure * PA_PER_MPA,
-    )
-
-
-FlashCallable = Callable[[FluidMixture, float, float], TwoPhaseFlashResult]
-
-
-def run_validated_flash(
-    composition_mol_percent: Sequence[float],
-    temperature_k: float,
-    pressure_mpa: float,
-    *,
-    flash_api: FlashCallable = calculate_two_phase_flash,
-) -> tuple[ScientificInputs, TwoPhaseFlashResult]:
-    """Validate before invoking the unchanged production flash API."""
-
-    inputs = validate_scientific_inputs(
-        composition_mol_percent, temperature_k, pressure_mpa
-    )
-    result = flash_api(inputs.mixture(), inputs.temperature_k, inputs.pressure_pa)
-    return inputs, result
-
-
-@dataclass(frozen=True, slots=True)
-class FlashView:
-    """Lossless selection of public flash fields used by the Overview."""
-
-    phase_state: object
-    convergence_status: object
-    temperature_k: float
-    pressure_pa: float
-    vapor_fraction: float | None
-    liquid_fraction: float | None
-    liquid_composition: tuple[float, ...] | None
-    vapor_composition: tuple[float, ...] | None
-    liquid_z: float | None
-    vapor_z: float | None
-    single_phase_z: float | None
-    final_k_values: tuple[float, ...] | None
-    equilibrium_residuals: tuple[float | None, ...]
-    material_balance_residuals: tuple[float, ...]
-    iteration_count: int
-    failure_reason: str | None
-
-
-def adapt_flash_result(result: TwoPhaseFlashResult) -> FlashView:
-    """Expose public result fields without changing identity or filling gaps."""
-
-    liquid = result.liquid_phase
-    vapor = result.vapor_phase
-    return FlashView(
-        result.phase_state,
-        result.convergence_status,
-        result.temperature_k,
-        result.pressure_pa,
-        result.vapor_fraction,
-        result.liquid_fraction,
-        None if liquid is None else liquid.composition,
-        None if vapor is None else vapor.composition,
-        None if liquid is None else liquid.selected_compressibility_factor,
-        None if vapor is None else vapor.selected_compressibility_factor,
-        result.single_phase_root,
-        result.final_k_values,
-        result.equilibrium_residuals,
-        result.material_balance_residuals,
-        len(result.iteration_history),
-        result.failure_reason,
-    )
-
-
-@dataclass(frozen=True, slots=True)
-class CriticalView:
-    """Certification-safe selection of a public critical-point result."""
-
-    status: CriticalPointStatus
-    certified: bool
-    temperature_k: float | None
-    pressure_pa: float | None
-    lambda_min: float | None
-    cubic_coefficient: float | None
-    critical_direction: tuple[float, ...] | None
-    iterations: int
-    termination_reason: str
-    jacobian_condition_history: tuple[float, ...]
-
-
-def adapt_critical_result(result: MixtureCriticalPointResult) -> CriticalView:
-    """Certify only a production result whose status is exactly CONVERGED."""
-
-    certified = result.status is CriticalPointStatus.CONVERGED
-    return CriticalView(
-        result.status,
-        certified,
-        result.temperature_k if certified else None,
-        result.pressure_pa if certified else None,
-        result.lambda_min if certified else None,
-        result.cubic_coefficient if certified else None,
-        result.critical_direction if certified else None,
-        result.iterations,
-        result.termination_reason,
-        result.jacobian_condition_history,
-    )
-
-
-def _converged_pressures_at_temperature(
-    result: PhaseEnvelopeResult, temperature_k: float
-) -> tuple[float | None, float | None]:
-    def interpolate(points: Sequence[PhaseEnvelopePoint]) -> float | None:
-        accepted = sorted(
-            (
-                (float(point.temperature_k), float(point.pressure_pa))
-                for point in points
-                if str(point.status) == "converged"
-            ),
-            key=lambda pair: pair[0],
-        )
-        for left, right in zip(accepted, accepted[1:], strict=False):
-            if left[0] <= temperature_k <= right[0] and right[0] != left[0]:
-                weight = (temperature_k - left[0]) / (right[0] - left[0])
-                return left[1] + weight * (right[1] - left[1])
-        for point_temperature, point_pressure in accepted:
-            if point_temperature == temperature_k:
-                return point_pressure
-        return None
-
-    return (
-        interpolate(result.bubble_branch.points),
-        interpolate(result.dew_branch.points),
-    )
-
-
-def location_relative_to_envelope(
-    result: PhaseEnvelopeResult | None, temperature_k: float, pressure_pa: float
-) -> str:
-    """Describe a state against available converged branch interpolation only."""
-
-    if result is None:
-        return "Unavailable until a phase envelope has been calculated."
-    bubble, dew = _converged_pressures_at_temperature(result, temperature_k)
-    if bubble is None or dew is None:
-        return "Unavailable at this temperature from converged envelope points."
-    lower, upper = sorted((bubble, dew))
-    if lower <= pressure_pa <= upper:
-        return "Inside the interpolated two-phase envelope."
-    if pressure_pa < lower:
-        return "Below both interpolated saturation branches."
-    return "Above both interpolated saturation branches."
-
-
-def status_text(value: object) -> str:
-    """Format a public enum or scalar status without reclassifying it."""
-
-    raw = value.value if hasattr(value, "value") else str(value)
-    return str(raw).replace("_", " ").title()
-
-
-def load_module17_records(repository_root: Path) -> tuple[ValidationPlotRecord, ...]:
-    """Load the protected Module 17 artifact through the Module 21 adapter."""
-
-    return load_validation_plot_records(
-        repository_root / "docs" / "validation" / "module17_vle_validation.csv"
-    )
-
-
-def relative_pressure_error_percent(
-    predicted_pa: float, experimental_pa: float
-) -> float:
-    """Return the documented Module 17 signed relative pressure error."""
-
-    predicted = float(predicted_pa)
-    experimental = float(experimental_pa)
-    if not all(isfinite(value) for value in (predicted, experimental)):
-        raise ValueError("pressures must be finite")
-    if experimental <= 0.0:
-        raise ValueError("experimental pressure must be positive")
-    return 100.0 * (predicted - experimental) / experimental
+from pvt_phase_simulator_ui.adapters import *  # noqa: F403
diff --git a/app/state.py b/app/state.py
index 11414b6..77e1ccc 100644
--- a/app/state.py
+++ b/app/state.py
@@ -1,55 +1,3 @@
-"""Deterministic session-state helpers independent of Streamlit runtime."""
+"""Compatibility imports for the installed UI package."""
 
-from __future__ import annotations
-
-from collections.abc import MutableMapping
-from typing import Any, Final, cast
-
-from app.adapters import ScientificInputs
-
-RESULT_KEYS: Final = ("flash", "envelope", "critical", "critical_scan")
-
-
-def initialize_session(state: MutableMapping[str, Any]) -> None:
-    """Initialize application state without replacing existing results."""
-
-    state.setdefault("results", {})
-    state.setdefault("result_signatures", {})
-
-
-def store_result(
-    state: MutableMapping[str, Any],
-    name: str,
-    value: object,
-    inputs: ScientificInputs,
-) -> None:
-    """Store one deliberate calculation with its scientific input signature."""
-
-    initialize_session(state)
-    state["results"][name] = value
-    state["result_signatures"][name] = inputs.signature
-
-
-def get_result(state: MutableMapping[str, Any], name: str) -> object | None:
-    """Return a prior result across cosmetic reruns."""
-
-    initialize_session(state)
-    results = cast(dict[str, object], state["results"])
-    return results.get(name)
-
-
-def result_is_stale(
-    state: MutableMapping[str, Any], name: str, inputs: ScientificInputs | None
-) -> bool:
-    """Mark a stored result stale after scientific input changes or invalidates."""
-
-    initialize_session(state)
-    if name not in state["results"]:
-        return False
-    if inputs is None:
-        return True
-    signatures = cast(
-        dict[str, tuple[tuple[float, float, float], float, float]],
-        state["result_signatures"],
-    )
-    return signatures.get(name) != inputs.signature
+from pvt_phase_simulator_ui.state import *  # noqa: F403
diff --git a/app/streamlit_app.py b/app/streamlit_app.py
index 3083e46..8ca50d5 100644
--- a/app/streamlit_app.py
+++ b/app/streamlit_app.py
@@ -1,565 +1,5 @@
-"""Polished Streamlit frontend for the verified PVT scientific engine."""
+"""Compatibility entrypoint; the application is an installed UI package."""
 
-from __future__ import annotations
+from pvt_phase_simulator_ui.app import run_app
 
-from collections.abc import MutableMapping
-from dataclasses import asdict
-from pathlib import Path
-from typing import Any, Literal, cast
-
-import pandas as pd  # type: ignore[import-untyped]
-import streamlit as st
-
-from app.adapters import (
-    COMPONENT_NAMES,
-    PA_PER_MPA,
-    InputValidationError,
-    ScientificInputs,
-    adapt_critical_result,
-    adapt_flash_result,
-    composition_total,
-    load_module17_records,
-    location_relative_to_envelope,
-    run_validated_flash,
-    status_text,
-    validate_scientific_inputs,
-)
-from app.state import get_result, initialize_session, result_is_stale, store_result
-from app.styles import apply_styles
-from pvt_phase_simulator.eos.critical_point import (
-    CriticalPointScanResult,
-    CriticalPointScanSettings,
-    MixtureCriticalPointResult,
-    scan_mixture_criticality,
-    solve_mixture_critical_point,
-)
-from pvt_phase_simulator.eos.flash import TwoPhaseFlashResult
-from pvt_phase_simulator.eos.phase_envelope import (
-    EnvelopeContinuationSettings,
-    PhaseEnvelopeResult,
-    calculate_phase_envelope,
-)
-from pvt_phase_simulator.plotting import (
-    CompositionDisplay,
-    PressureUnit,
-    plot_critical_solver_conditioning,
-    plot_critical_solver_convergence,
-    plot_critical_solver_path,
-    plot_criticality_map,
-    plot_phase_compositions,
-    plot_phase_envelope,
-    plot_validation_composition_parity,
-    plot_validation_pressure_error,
-    plot_validation_pressure_parity,
-    plot_validation_retrospective_diagnostics,
-    plot_validation_status,
-)
-
-ROOT = Path(__file__).resolve().parents[1]
-PAGES = ("Overview", "Phase Envelope", "Critical Point", "Validation", "Diagnostics")
-
-
-def _state() -> MutableMapping[str, Any]:
-    return cast(MutableMapping[str, Any], st.session_state)
-
-
-def _value(item: object) -> str:
-    return str(item.value if hasattr(item, "value") else item)
-
-
-def _optional(value: float | None, digits: int = 6) -> str:
-    return "Unavailable" if value is None else f"{value:.{digits}g}"
-
-
-def _inputs() -> ScientificInputs | None:
-    st.sidebar.markdown("## Fluid Input")
-    st.sidebar.caption("Verified v1.0 components. Enter composition in mol %.")
-    values = (
-        st.sidebar.number_input("Methane (mol %)", value=50.0, format="%.10g"),
-        st.sidebar.number_input("Ethane (mol %)", value=0.0, format="%.10g"),
-        st.sidebar.number_input("Propane (mol %)", value=50.0, format="%.10g"),
-    )
-    total = composition_total(values)
-    if abs(total - 100.0) <= 1.0e-8 and all(0.0 <= value <= 100.0 for value in values):
-        st.sidebar.success(f"Total: {total:.12g} mol %")
-    else:
-        st.sidebar.error(f"Total: {total:.12g} mol %. Required: 100 mol %.")
-    temperature = st.sidebar.number_input(
-        "Temperature (K)", value=300.0, format="%.10g"
-    )
-    pressure = st.sidebar.number_input("Pressure (MPa)", value=5.0, format="%.10g")
-    try:
-        inputs = validate_scientific_inputs(values, temperature, pressure)
-    except InputValidationError as error:
-        inputs = None
-        st.sidebar.error(str(error))
-    if st.sidebar.button(
-        "RUN FLASH", type="primary", use_container_width=True, disabled=inputs is None
-    ):
-        try:
-            run_inputs, result = run_validated_flash(values, temperature, pressure)
-            store_result(_state(), "flash", result, run_inputs)
-            st.sidebar.success("Structured flash result received.")
-        except (ValueError, ArithmeticError) as error:
-            st.sidebar.error(f"Flash calculation failure: {error}")
-    st.sidebar.caption(
-        "Pressure is converted exactly from MPa to internal Pa. "
-        "Calculations require an explicit action."
-    )
-    return inputs
-
-
-def _navigation() -> str:
-    st.markdown(
-        """
-        <div class="pvt-header">
-          <div class="pvt-kicker">PVT PHASE SIMULATOR</div>
-          <div class="pvt-title">Hydrocarbon phase behavior</div>
-          <p class="pvt-subtitle">Peng-Robinson EOS - Hydrocarbon Phase Behavior</p>
-        </div>
-        """,
-        unsafe_allow_html=True,
-    )
-    return st.radio(
-        "Application view",
-        PAGES,
-        horizontal=True,
-        label_visibility="collapsed",
-        key="navigation",
-    )
-
-
-def _stale(name: str, inputs: ScientificInputs | None) -> None:
-    if result_is_stale(_state(), name, inputs):
-        st.markdown(
-            '<div class="pvt-status pvt-stale"><strong>Stale result.</strong> '
-            "Scientific inputs changed. Run this calculation again before use.</div>",
-            unsafe_allow_html=True,
-        )
-
-
-def _overview(inputs: ScientificInputs | None) -> None:
-    st.header("Overview")
-    raw = get_result(_state(), "flash")
-    if raw is None:
-        st.info("Enter valid conditions and select RUN FLASH to calculate a state.")
-        return
-    result = cast(TwoPhaseFlashResult, raw)
-    view = adapt_flash_result(result)
-    _stale("flash", inputs)
-    st.markdown(
-        f'<div class="pvt-status"><strong>{status_text(view.phase_state)}</strong> | '
-        f"{status_text(view.convergence_status)}</div>",
-        unsafe_allow_html=True,
-    )
-    metrics = st.columns(4)
-    metrics[0].metric("Temperature", f"{view.temperature_k:.8g} K")
-    metrics[1].metric("Pressure", f"{view.pressure_pa / PA_PER_MPA:.15g} MPa")
-    metrics[2].metric("Vapor fraction", _optional(view.vapor_fraction))
-    metrics[3].metric("Liquid fraction", _optional(view.liquid_fraction))
-    z_metrics = st.columns(2)
-    z_metrics[0].metric("Liquid Z", _optional(view.liquid_z))
-    z_metrics[1].metric("Vapor Z", _optional(view.vapor_z))
-    envelope = cast(PhaseEnvelopeResult | None, get_result(_state(), "envelope"))
-    if result_is_stale(_state(), "envelope", inputs):
-        envelope = None
-    st.write(
-        "**Location relative to phase envelope:** "
-        + location_relative_to_envelope(envelope, view.temperature_k, view.pressure_pa)
-    )
-    rows: dict[str, tuple[float, ...]] = {
-        "Feed (mol %)": tuple(
-            100.0 * item.mole_fraction for item in result.feed_mixture.components
-        )
-    }
-    if view.liquid_composition is not None:
-        rows["Liquid (mol %)"] = tuple(
-            100.0 * value for value in view.liquid_composition
-        )
-    if view.vapor_composition is not None:
-        rows["Vapor (mol %)"] = tuple(100.0 * value for value in view.vapor_composition)
-    st.subheader("Composition")
-    st.dataframe(pd.DataFrame(rows, index=COMPONENT_NAMES).T, use_container_width=True)
-    if view.single_phase_z is not None:
-        st.caption(
-            f"Single-phase selected root Z: {view.single_phase_z:.10g}. "
-            "It is not labelled as liquid Z or vapor Z."
-        )
-    with st.expander("Technical details"):
-        st.write("Iterations", view.iteration_count)
-        st.write("Failure or termination", view.failure_reason or "None")
-        if view.final_k_values is not None:
-            st.write("Final K values", view.final_k_values)
-        if view.equilibrium_residuals:
-            st.write("Equilibrium residuals", view.equilibrium_residuals)
-        if view.material_balance_residuals:
-            st.write("Material-balance residuals", view.material_balance_residuals)
-        for label, phase in (
-            ("Liquid", result.liquid_phase),
-            ("Vapor", result.vapor_phase),
-        ):
-            if phase is not None:
-                st.write(
-                    f"{label} log fugacity coefficients",
-                    phase.component_log_fugacity_coefficients,
-                )
-
-
-def _calculate_envelope(inputs: ScientificInputs) -> PhaseEnvelopeResult:
-    settings = EnvelopeContinuationSettings(
-        target_temperature_k=inputs.temperature_k + 50.0,
-        initial_temperature_step_k=5.0,
-        maximum_points=15,
-    )
-    return calculate_phase_envelope(
-        inputs.mixture(),
-        settings,
-        settings,
-        inputs.temperature_k,
-        inputs.temperature_k,
-    )
-
-
-def _envelope(inputs: ScientificInputs | None) -> None:
-    st.header("Phase Envelope")
-    st.write(
-        "Bubble and dew identities are retained. Unavailable points remain "
-        "visibly non-converged."
-    )
-    if st.button("RUN PHASE ENVELOPE", disabled=inputs is None):
-        assert inputs is not None
-        with st.spinner("Tracing independent bubble and dew branches..."):
-            try:
-                store_result(_state(), "envelope", _calculate_envelope(inputs), inputs)
-            except (ValueError, ArithmeticError) as error:
-                st.error(f"Phase-envelope calculation could not start: {error}")
-    raw = get_result(_state(), "envelope")
-    if raw is None:
-        st.info("No envelope result is available. This calculation is optional.")
-        return
-    result = cast(PhaseEnvelopeResult, raw)
-    _stale("envelope", inputs)
-    critical = cast(MixtureCriticalPointResult | None, get_result(_state(), "critical"))
-    if result_is_stale(_state(), "critical", inputs):
-        critical = None
-    st.plotly_chart(
-        plot_phase_envelope(
-            result,
-            pressure_unit=PressureUnit.MPA,
-            critical_point=critical,
-            metadata={"model": "Peng-Robinson EOS; kij=0"},
-        ),
-        use_container_width=True,
-    )
-    columns = st.columns(2)
-    columns[0].metric(
-        "Bubble termination", status_text(result.bubble_branch.termination_reason)
-    )
-    columns[1].metric(
-        "Dew termination", status_text(result.dew_branch.termination_reason)
-    )
-    st.caption(
-        "Pressure or temperature turning points are continuation geometry. "
-        "They are not certified critical points."
-    )
-    component = st.selectbox("Composition component", COMPONENT_NAMES)
-    branch = cast(
-        Literal["bubble", "dew"],
-        st.radio("Composition branch", ("bubble", "dew"), horizontal=True),
-    )
-    try:
-        st.plotly_chart(
-            plot_phase_compositions(
-                result,
-                branch=branch,
-                component_index=COMPONENT_NAMES.index(component),
-                display=CompositionDisplay.MOL_PERCENT,
-                pressure_unit=PressureUnit.MPA,
-            ),
-            use_container_width=True,
-        )
-    except ValueError as error:
-        st.info(f"Phase-composition figure unavailable: {error}")
-
-
-def _calculate_critical(inputs: ScientificInputs) -> MixtureCriticalPointResult:
-    return solve_mixture_critical_point(
-        inputs.mixture(),
-        inputs.temperature_k,
-        inputs.pressure_pa,
-        initialization_source="streamlit_user_conditions",
-    )
-
-
-def _calculate_scan(inputs: ScientificInputs) -> CriticalPointScanResult:
-    return scan_mixture_criticality(
-        inputs.mixture(),
-        CriticalPointScanSettings(
-            0.8 * inputs.temperature_k,
-            1.2 * inputs.temperature_k,
-            0.5 * inputs.pressure_pa,
-            1.5 * inputs.pressure_pa,
-            temperature_points=7,
-            pressure_points=7,
-        ),
-    )
-
-
-def _critical(inputs: ScientificInputs | None) -> None:
-    st.header("Critical Point")
-    st.write(
-        "Certification requires a converged Module 20 result and both critical "
-        "conditions. lambda_min=0 alone is a spinodal condition."
-    )
-    controls = st.columns(2)
-    if controls[0].button("RUN CRITICAL SOLVER", disabled=inputs is None):
-        assert inputs is not None
-        with st.spinner("Solving fixed-composition critical conditions..."):
-            try:
-                store_result(_state(), "critical", _calculate_critical(inputs), inputs)
-            except (ValueError, ArithmeticError) as error:
-                st.error(f"Critical solver could not start: {error}")
-    if controls[1].button("RUN CRITICALITY MAP", disabled=inputs is None):
-        assert inputs is not None
-        with st.spinner("Evaluating the bounded diagnostic map..."):
-            try:
-                store_result(_state(), "critical_scan", _calculate_scan(inputs), inputs)
-            except (ValueError, ArithmeticError) as error:
-                st.error(f"Criticality map could not be evaluated: {error}")
-    raw = get_result(_state(), "critical")
-    if raw is None:
-        st.info("No critical-point solve has been requested.")
-    else:
-        result = cast(MixtureCriticalPointResult, raw)
-        view = adapt_critical_result(result)
-        _stale("critical", inputs)
-        st.markdown(
-            f'<div class="pvt-status"><strong>{status_text(view.status)}</strong> | '
-            + ("Certified critical point" if view.certified else "Not certified")
-            + "</div>",
-            unsafe_allow_html=True,
-        )
-        if view.certified:
-            assert view.temperature_k is not None
-            assert view.pressure_pa is not None
-            metrics = st.columns(4)
-            metrics[0].metric("Tc", f"{view.temperature_k:.13g} K")
-            metrics[1].metric("Pc", f"{view.pressure_pa / PA_PER_MPA:.15g} MPa")
-            metrics[2].metric("lambda_min", _optional(view.lambda_min, 8))
-            metrics[3].metric("C", _optional(view.cubic_coefficient, 8))
-            st.write("Critical direction", view.critical_direction)
-        st.write("Termination", view.termination_reason)
-        st.write("Iterations", view.iterations)
-        if result.history:
-            st.plotly_chart(
-                plot_critical_solver_convergence(result), use_container_width=True
-            )
-            st.plotly_chart(plot_critical_solver_path(result), use_container_width=True)
-        if result.jacobian_condition_history:
-            st.plotly_chart(
-                plot_critical_solver_conditioning(result), use_container_width=True
-            )
-    scan_raw = get_result(_state(), "critical_scan")
-    if scan_raw is not None:
-        _stale("critical_scan", inputs)
-        overlay = cast(MixtureCriticalPointResult | None, raw)
-        if result_is_stale(_state(), "critical", inputs):
-            overlay = None
-        st.plotly_chart(
-            plot_criticality_map(
-                cast(CriticalPointScanResult, scan_raw),
-                pressure_unit=PressureUnit.MPA,
-                critical_point=overlay,
-                metadata={"model": "Peng-Robinson EOS; kij=0"},
-            ),
-            use_container_width=True,
-        )
-
-
-@st.cache_data(show_spinner=False)
-def _records() -> tuple[Any, ...]:
-    return load_module17_records(ROOT)
-
-
-def _validation() -> None:
-    st.header("Validation")
-    st.write(
-        "Module 17 methane/ethane and methane/propane comparisons use kij=0 "
-        "with no fitted binary interaction parameters."
-    )
-    records = _records()
-    direction = cast(
-        Literal["bubble", "dew"],
-        st.radio("Prediction direction", ("bubble", "dew"), horizontal=True),
-    )
-    for figure in (
-        plot_validation_pressure_parity(
-            records, direction=direction, pressure_unit=PressureUnit.MPA
-        ),
-        plot_validation_pressure_error(records, direction=direction),
-        plot_validation_status(records, direction=direction),
-    ):
-        st.plotly_chart(figure, use_container_width=True)
-    try:
-        st.plotly_chart(
-            plot_validation_composition_parity(
-                records,
-                direction=direction,
-                component_index=0,
-                display=CompositionDisplay.MOL_PERCENT,
-            ),
-            use_container_width=True,
-        )
-    except (ValueError, IndexError) as error:
-        st.info(f"Composition parity unavailable: {error}")
-    st.subheader("Retrospective nearest-root diagnostics")
-    st.warning(
-        "Not production prediction. This validation-only view is separate from "
-        "Module 17 production predictions."
-    )
-    try:
-        st.plotly_chart(
-            plot_validation_retrospective_diagnostics(
-                records, pressure_unit=PressureUnit.MPA
-            ),
-            use_container_width=True,
-        )
-    except ValueError as error:
-        st.info(f"Retrospective diagnostics unavailable: {error}")
-    st.caption("Relative pressure error is 100*(P_pred-P_exp)/P_exp.")
-
-
-def _diagnostics(inputs: ScientificInputs | None) -> None:
-    st.header("Diagnostics")
-    st.write(
-        "Public solver evidence is shown without converting structured "
-        "failures into success."
-    )
-    flash_raw = get_result(_state(), "flash")
-    if flash_raw is not None:
-        result = cast(TwoPhaseFlashResult, flash_raw)
-        _stale("flash", inputs)
-        st.subheader("Flash and stability")
-        st.json(
-            {
-                "phase_state": _value(result.phase_state),
-                "convergence": _value(result.convergence_status),
-                "termination_or_failure": result.failure_reason,
-                "iterations": len(result.iteration_history),
-                "stability_status": _value(result.phase_stability.status),
-            }
-        )
-        if result.diagnostics:
-            st.dataframe(
-                pd.DataFrame(
-                    {
-                        "code": item.code,
-                        "severity": _value(item.severity),
-                        "category": _value(item.category),
-                        "message": item.message,
-                        "value": item.value,
-                    }
-                    for item in result.diagnostics
-                ),
-                use_container_width=True,
-            )
-        if result.iteration_history:
-            latest = result.iteration_history[-1]
-            st.write(
-                "Latest iteration evidence",
-                {
-                    "iteration": latest.iteration,
-                    "maximum_log_k_residual": latest.maximum_log_k_residual,
-                    "maximum_fugacity_equilibrium_residual": (
-                        latest.maximum_fugacity_equilibrium_residual
-                    ),
-                    "maximum_material_balance_residual": (
-                        latest.phase_compositions.maximum_material_balance_residual
-                    ),
-                    "Rachford-Rice status": _value(latest.rachford_rice.status),
-                    "Rachford-Rice iterations": latest.rachford_rice.iterations,
-                },
-            )
-        for phase_name, phase in (
-            ("liquid", result.liquid_phase),
-            ("vapor", result.vapor_phase),
-        ):
-            if phase is not None:
-                st.write(
-                    f"{phase_name.title()} public root selection",
-                    asdict(phase.root_selection),
-                )
-    envelope_raw = get_result(_state(), "envelope")
-    if envelope_raw is not None:
-        envelope_result = cast(PhaseEnvelopeResult, envelope_raw)
-        st.subheader("Envelope continuation")
-        st.dataframe(
-            pd.DataFrame(
-                {
-                    "branch": branch.branch_kind.value,
-                    "accepted_points": len(branch.points),
-                    "rejected_attempts": len(branch.rejected_attempts),
-                    "termination": branch.termination_reason.value,
-                    "message": branch.termination_message,
-                }
-                for branch in (
-                    envelope_result.bubble_branch,
-                    envelope_result.dew_branch,
-                )
-            ),
-            use_container_width=True,
-        )
-        st.caption("Turning indicators are continuation geometry, not critical points.")
-    critical_raw = get_result(_state(), "critical")
-    if critical_raw is not None:
-        critical_result = cast(MixtureCriticalPointResult, critical_raw)
-        st.subheader("Critical solver")
-        st.json(
-            {
-                "status": critical_result.status.value,
-                "termination": critical_result.termination_reason,
-                "iterations": critical_result.iterations,
-                "accepted_steps": critical_result.accepted_steps,
-                "rejected_steps": critical_result.rejected_steps,
-                "function_evaluations": critical_result.function_evaluations,
-                "jacobian_condition_history": (
-                    critical_result.jacobian_condition_history
-                ),
-                "certified": adapt_critical_result(critical_result).certified,
-            }
-        )
-        if critical_result.criticality_result is not None:
-            st.write(
-                "Final public criticality result",
-                asdict(critical_result.criticality_result),
-            )
-    if flash_raw is None and envelope_raw is None and critical_raw is None:
-        st.info("Run a calculation to populate public diagnostics.")
-
-
-def main() -> None:
-    """Render the application through public scientific APIs only."""
-
-    st.set_page_config(
-        page_title="PVT Phase Simulator",
-        layout="wide",
-        initial_sidebar_state="expanded",
-    )
-    apply_styles()
-    initialize_session(_state())
-    inputs = _inputs()
-    page = _navigation()
-    if page == "Overview":
-        _overview(inputs)
-    elif page == "Phase Envelope":
-        _envelope(inputs)
-    elif page == "Critical Point":
-        _critical(inputs)
-    elif page == "Validation":
-        _validation()
-    else:
-        _diagnostics(inputs)
-
-
-if __name__ == "__main__":
-    main()
+run_app()
diff --git a/app/styles.py b/app/styles.py
index 76d4ff0..e09c6f3 100644
--- a/app/styles.py
+++ b/app/styles.py
@@ -1,51 +1,3 @@
-"""Light scientific-engineering visual system for native Streamlit widgets."""
+"""Compatibility imports for the installed UI package."""
 
-# ruff: noqa: E501
-
-from __future__ import annotations
-
-import streamlit as st
-
-CSS = """
-<style>
-:root {
-  --pvt-ink: #102a43;
-  --pvt-muted: #52677d;
-  --pvt-accent: #0f6b72;
-  --pvt-accent-dark: #09535a;
-  --pvt-border: #d8e1e8;
-  --pvt-surface: #ffffff;
-  --pvt-canvas: #f6f8fa;
-  --pvt-soft: #edf5f5;
-}
-.stApp { background: var(--pvt-canvas); color: var(--pvt-ink); }
-[data-testid="stHeader"] { background: rgba(246, 248, 250, 0.96); }
-[data-testid="stSidebar"] { background: var(--pvt-surface); border-right: 1px solid var(--pvt-border); }
-[data-testid="stMainBlockContainer"] { max-width: 1280px; padding-top: 1.5rem; padding-bottom: 4rem; }
-h1, h2, h3 { color: var(--pvt-ink); letter-spacing: -0.02em; }
-p, label, [data-testid="stCaptionContainer"] { color: var(--pvt-muted); }
-.pvt-header { border-bottom: 1px solid var(--pvt-border); padding: 0 0 1.2rem; margin-bottom: 1.25rem; }
-.pvt-kicker { color: var(--pvt-accent); font-size: .78rem; font-weight: 750; letter-spacing: .12em; text-transform: uppercase; }
-.pvt-title { color: var(--pvt-ink); font-size: clamp(1.7rem, 3vw, 2.7rem); font-weight: 760; margin: .25rem 0 .15rem; line-height: 1.08; }
-.pvt-subtitle { color: var(--pvt-muted); font-size: 1rem; margin: 0; }
-.pvt-status { border: 1px solid var(--pvt-border); border-left: 4px solid var(--pvt-accent); border-radius: 10px; background: var(--pvt-surface); padding: .8rem 1rem; margin: .5rem 0 1rem; }
-.pvt-stale { border-left-color: #a76316; background: #fff9ef; }
-div[data-testid="stMetric"] { background: var(--pvt-surface); border: 1px solid var(--pvt-border); border-radius: 10px; padding: .8rem 1rem; }
-div[data-testid="stMetricValue"] { color: var(--pvt-ink); font-variant-numeric: tabular-nums; }
-div[data-testid="stButton"] > button { border-radius: 9px; border: 1px solid var(--pvt-accent); font-weight: 700; }
-div[data-testid="stButton"] > button[kind="primary"] { background: var(--pvt-accent); color: #ffffff; }
-div[data-testid="stButton"] > button[kind="primary"]:hover { background: var(--pvt-accent-dark); border-color: var(--pvt-accent-dark); }
-div[data-testid="stNumberInput"] input { font-variant-numeric: tabular-nums; }
-div[data-testid="stExpander"] { background: var(--pvt-surface); border-color: var(--pvt-border); border-radius: 10px; }
-@media (max-width: 768px) {
-  [data-testid="stMainBlockContainer"] { padding-left: 1rem; padding-right: 1rem; }
-  .pvt-title { font-size: 1.8rem; }
-}
-</style>
-"""
-
-
-def apply_styles() -> None:
-    """Install scoped application CSS."""
-
-    st.markdown(CSS, unsafe_allow_html=True)
+from pvt_phase_simulator_ui.styles import *  # noqa: F403
diff --git a/docs/STREAMLIT_APPLICATION.md b/docs/STREAMLIT_APPLICATION.md
index fe648dd..d59035f 100644
--- a/docs/STREAMLIT_APPLICATION.md
+++ b/docs/STREAMLIT_APPLICATION.md
@@ -10,30 +10,39 @@ is not a commercial PVT package or a substitute for engineering review.
 Launch it from the repository root:
 
 ```powershell
-.venv\Scripts\python.exe -m streamlit run app/streamlit_app.py
+uv run streamlit run streamlit_app.py
 ```
 
+This reproducibly installs the project and requires no manual `PYTHONPATH`.
+`uv run streamlit run app/streamlit_app.py` remains a tested compatibility
+entrypoint.
+
 ## Architecture
 
-The application is deliberately compact:
+The application layer is installed separately from the frozen scientific
+package:
 
-- `app/streamlit_app.py` composes native Streamlit views.
-- `app/adapters.py` validates input, converts boundary units, and selects public
+- `streamlit_app.py` is the thin, stable root entrypoint.
+- `src/pvt_phase_simulator_ui/app.py` owns navigation and submitted inputs.
+- `src/pvt_phase_simulator_ui/pages/` contains the five page scripts.
+- `src/pvt_phase_simulator_ui/adapters.py` validates inputs, converts boundary
+  units, and selects public
   result fields without changing them.
-- `app/state.py` associates each calculation with a deterministic scientific
+- `src/pvt_phase_simulator_ui/state.py` associates each result with a scientific
   input signature.
-- `app/styles.py` applies the light scientific-engineering visual system.
+- `.streamlit/config.toml` supplies the light engineering theme. Narrow custom
+  styling is limited to the phase-split visualization.
 - `src/pvt_phase_simulator/plotting.py` remains the source of scientific Plotly
   figures.
 
 No EOS, fugacity, stability, flash, saturation, continuation, or criticality
-equation is implemented in `app/`.
+equation is implemented in the UI package.
 
 ## Inputs and views
 
-The persistent Fluid Input panel supports the verified v1.0 Methane, Ethane,
+The persistent Fluid inputs form supports the verified v1.0 Methane, Ethane,
 and Propane components. Composition is entered in mol %, temperature in K, and
-pressure in MPa. The panel shows the live composition total and rejects
+pressure in MPa. On submission, the panel shows the composition total and rejects
 nonfinite, negative, above-100, zero-total, and materially non-100% values. It
 does not silently normalize invalid composition.
 
@@ -57,8 +66,8 @@ Pa results are divided by `1e6` for MPa display.
 
 The UI calls existing flash, envelope, critical-point, and criticality APIs
 unchanged. Invalid input is rejected before a production call. Every expensive
-calculation requires an explicit button action; navigation and cosmetic reruns
-do not start calculations.
+calculation requires an explicit button action. Validation and advanced solver
+figures are guarded too; navigation and cosmetic reruns do not start them.
 
 Results persist in Streamlit session state. Each stores the exact composition,
 temperature, and internal-pressure signature used to produce it. Changed or
diff --git a/pyproject.toml b/pyproject.toml
index 8ea532c..6bdf85f 100644
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -23,6 +23,9 @@ pvt-phase-simulator = "pvt_phase_simulator:main"
 requires = ["uv_build>=0.11.33,<0.12.0"]
 build-backend = "uv_build"
 
+[tool.uv.build-backend]
+module-name = ["pvt_phase_simulator", "pvt_phase_simulator_ui"]
+
 [dependency-groups]
 dev = [
     "cosmic-ray>=8.4.6",
diff --git a/tests/test_app_adapters.py b/tests/test_app_adapters.py
index 77a259e..db78e56 100644
--- a/tests/test_app_adapters.py
+++ b/tests/test_app_adapters.py
@@ -9,16 +9,6 @@ from typing import cast
 
 import pytest
 
-from app.adapters import (
-    InputValidationError,
-    adapt_critical_result,
-    adapt_flash_result,
-    load_module17_records,
-    relative_pressure_error_percent,
-    run_validated_flash,
-    validate_scientific_inputs,
-)
-from app.state import get_result, initialize_session, result_is_stale, store_result
 from pvt_phase_simulator.eos.critical_point import (
     CriticalPointStatus,
     solve_mixture_critical_point,
@@ -31,6 +21,21 @@ from pvt_phase_simulator.plotting import (
     plot_validation_pressure_parity,
     plot_validation_retrospective_diagnostics,
 )
+from pvt_phase_simulator_ui.adapters import (
+    InputValidationError,
+    adapt_critical_result,
+    adapt_flash_result,
+    load_module17_records,
+    relative_pressure_error_percent,
+    run_validated_flash,
+    validate_scientific_inputs,
+)
+from pvt_phase_simulator_ui.state import (
+    get_result,
+    initialize_session,
+    result_is_stale,
+    store_result,
+)
 
 ROOT = Path(__file__).resolve().parents[1]
 
@@ -187,12 +192,13 @@ def test_module21_validation_figures_keep_sign_and_retrospective_separation() ->
 
 def test_app_code_contains_labels_but_no_thermodynamic_implementation() -> None:
     sources = "\n".join(
-        path.read_text(encoding="utf-8") for path in (ROOT / "app").glob("*.py")
+        path.read_text(encoding="utf-8")
+        for path in (ROOT / "src" / "pvt_phase_simulator_ui").rglob("*.py")
     )
     assert (
         "Turning indicators are continuation geometry, not critical points" in sources
     )
-    assert "Not production prediction" in sources
+    assert "NOT PRODUCTION PREDICTIONS" in sources
     assert "plot_validation_pressure_parity" in sources
     forbidden_definitions = (
         "def peng_robinson",

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
