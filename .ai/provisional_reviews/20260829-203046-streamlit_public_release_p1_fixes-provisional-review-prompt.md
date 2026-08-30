# Provisional Codex review: streamlit_public_release_p1_fixes

## Your role and limits

You are a SECOND, FRESH Codex process performing a
`PROVISIONAL_CODEX_REVIEW`. Assume the implementation may contain defects.

- Work read-only. Do not edit, stage, commit, or regenerate artifacts.
- This is NOT an independent audit and does not replace Claude review.
- Check the actual diff, local verification, acceptance criteria, failure
  semantics, tests, and scientific separation adversarially.
- Report blocking defects precisely; do not fix them.

## Review scope
Review the complete work-package implementation.

## Objective and acceptance criteria
Fix only the two P1 findings from the latest independent Claude audit of the public Streamlit application. This is application-layer work only; do not rebuild or broadly redesign the UI, add unrelated features, modify documentation, or change any scientific implementation, decision, result, tolerance, dataset, baseline, or validation artifact.

P1 FINDING 1 - VALID SINGLE-PHASE PRESENTATION. A scientifically valid and conclusive single-phase result is currently rendered with red error styling. The reproducing case is Methane/Propane = 50/50 mol %, T = 300 K, P = 20 MPa: phase stability is conclusive, no two-phase flash is required, and the production result supplies a valid selected single-phase Z. Fix presentation only. Render valid single-phase outcomes with neutral, success, or information styling; explicitly say no two-phase split was required; preserve and display the selected single-phase Z from the result. Genuine structured solver failures must continue to use failure/error styling. Do not change or reinterpret scientific classification or convergence logic. Add semantic regression tests proving the valid single-phase case does not take the error path and genuine failures still do.

P1 FINDING 2 - CURRENT-CASE CSV AND JSON EXPORT. Add explicit native Streamlit `Download CSV` and `Download JSON` controls for the current calculated case, using stable keys and truthful MIME types. Build export serialization in the application package from existing adapters/public production result objects; do not duplicate any thermodynamic equation. Preserve source numerical precision in serialization even though normal UI displays may remain rounded. Do not calculate, infer, backfill, or fabricate unavailable outputs; represent unavailability explicitly and consistently. JSON must be structured, deterministic apart from an optional clearly identified export timestamp, and reproducible. CSV must be UTF-8 and useful in Excel, using a tidy section/path/value representation or another documented flat structure that faithfully represents nested arrays and branch points without precision loss.

Where applicable and actually present in the current case, exports must include: case inputs (temperature in K, pressure in Pa and/or clearly labelled MPa, component names, overall mole fractions, model, kij assumption); flash result (phase classification, solver/convergence status, vapor and liquid fractions, liquid Z, vapor Z, selected single-phase Z, liquid and vapor compositions, K-values, equilibrium residuals, material-balance residuals); phase-envelope result (bubble branch points, dew branch points, and branch termination/status information); critical-point result (certification status, Tc, Pc, and criticality residual information); metadata (Peng-Robinson EOS, SI units, kij = 0, verified Methane/Ethane/Propane scope, schema/version information, and export timestamp only if useful). Export only results already calculated and held for that current case/session; do not trigger hidden scientific calculations during export. Distinguish not-calculated, not-applicable, and unavailable when the existing state permits that distinction.

Add regression tests for CSV existence and representative exact values; JSON existence, valid structure, and full float precision; safe unavailable handling; and absence of fabricated flash, envelope, or critical results. Tests should exercise pure serialization helpers where practical and Streamlit rendering semantics where needed. Retain explicit scientific action gating, stale-result semantics, existing navigation, theme, diagnostics, plots, precision policy, and all stabilization work. Follow installed Streamlit 1.60 public APIs; use `st.download_button` with `width` rather than deprecated `use_container_width`, and prefer native status elements over custom styling.

The scientific engine is frozen. Do not modify `src/pvt_phase_simulator`, `data`, `docs/validation`, `tests/golden_master`, any pre-existing scientific test, experimental validation data, critical-point science, flash science, phase-envelope science, or any existing scientific algorithm. Existing engine/adapters/results are the only source of scientific truth.

## Scientific invariants
- Every file under src/pvt_phase_simulator remains byte-unchanged; presentation and export code may only consume existing public results through the application layer.
- No scientific classification, convergence decision, equation, algorithm, tolerance, or production result object changes.
- A conclusive production single-phase result remains single-phase and retains its exact selected Z; only its visual status changes from erroneous failure styling to valid-result styling.
- A genuine production failure remains visibly and structurally a failure; presentation code never converts failure information into success.
- Exports preserve source float precision and never use rounded display strings as numeric source data.
- Exports never trigger a flash, envelope, critical-point, validation, or other scientific calculation and never invent unavailable phase fractions, Z factors, compositions, residuals, branch points, or certified critical values.
- Only already-calculated current-case results are exported, with explicit not-calculated, not-applicable, or unavailable values where supported by current state.
- Peng-Robinson EOS, SI units, kij = 0, and verified Methane/Ethane/Propane scope remain truthful metadata; no fitted interaction parameter is claimed.
- Golden master, component property provenance, Module 17 validation artifacts, critical-point results, flash results, and phase-envelope results remain unchanged.
- All pre-existing scientific tests remain present and unchanged; new tests are application tests only.

## Local deterministic verification
Passed: **True**
```
        PASS  .venv/Scripts/python.exe -m pytest -q
        PASS  .venv/Scripts/python.exe -m ruff check .
        PASS  .venv/Scripts/python.exe -m ruff format --check .
        PASS  .venv/Scripts/python.exe -m mypy src app
        PASS  .venv/Scripts/python.exe -m compileall -q src app
        PASS  uv lock --check
        PASS  uv run python -c import pvt_phase_simulator_ui; import pvt_phase_simulator_ui.app; import pvt_phase_simulator_ui.views
        PASS  git diff --check
```
Changed files: ['src/pvt_phase_simulator_ui/adapters.py', 'src/pvt_phase_simulator_ui/exports.py', 'src/pvt_phase_simulator_ui/views.py', 'tests/test_app_adapters.py', 'tests/test_app_streamlit.py']

## Previous blocking findings
(none)

## Actual Git diff, including untracked files
```diff
diff --git a/src/pvt_phase_simulator_ui/adapters.py b/src/pvt_phase_simulator_ui/adapters.py
index e24acc0..9d11138 100644
--- a/src/pvt_phase_simulator_ui/adapters.py
+++ b/src/pvt_phase_simulator_ui/adapters.py
@@ -7,7 +7,7 @@ from dataclasses import dataclass
 from math import fsum, isfinite
 from pathlib import Path
 from statistics import median
-from typing import Final
+from typing import Final, Literal
 
 from pvt_phase_simulator.eos.critical_point import (
     CriticalPointStatus,
@@ -173,6 +173,29 @@ def adapt_flash_result(result: TwoPhaseFlashResult) -> FlashView:
     )
 
 
+def flash_presentation_kind(
+    result: TwoPhaseFlashResult,
+) -> Literal["success", "information", "error"]:
+    """Map public result semantics to UI styling without reclassifying science."""
+
+    view = adapt_flash_result(result)
+    phase_state = getattr(view.phase_state, "value", view.phase_state)
+    convergence = getattr(view.convergence_status, "value", view.convergence_status)
+    stability = getattr(
+        result.phase_stability.status, "value", result.phase_stability.status
+    )
+    if convergence == "converged":
+        return "success"
+    if (
+        phase_state == "single_phase"
+        and convergence == "not_attempted"
+        and stability == "stable"
+        and view.single_phase_z is not None
+    ):
+        return "information"
+    return "error"
+
+
 @dataclass(frozen=True, slots=True)
 class CriticalView:
     status: CriticalPointStatus
diff --git a/src/pvt_phase_simulator_ui/views.py b/src/pvt_phase_simulator_ui/views.py
index d180d4c..a60a185 100644
--- a/src/pvt_phase_simulator_ui/views.py
+++ b/src/pvt_phase_simulator_ui/views.py
@@ -43,12 +43,18 @@ from pvt_phase_simulator_ui.adapters import (
     ScientificInputs,
     adapt_critical_result,
     adapt_flash_result,
+    flash_presentation_kind,
     load_module17_records,
     location_relative_to_envelope,
     status_text,
     validation_pressure_error_summary,
 )
 from pvt_phase_simulator_ui.context import session
+from pvt_phase_simulator_ui.exports import (
+    build_export_document,
+    export_csv_bytes,
+    export_json_bytes,
+)
 from pvt_phase_simulator_ui.state import get_result, result_is_stale, store_result
 from pvt_phase_simulator_ui.styles import phase_split_bar
 
@@ -249,14 +255,21 @@ def render_overview(inputs: ScientificInputs | None) -> None:
         return
     result = cast(TwoPhaseFlashResult, raw)
     view = adapt_flash_result(result)
-    _stale("flash", inputs)
+    flash_stale = _stale("flash", inputs)
     with st.container(border=True):
         st.subheader(status_text(view.phase_state))
-        if _value(view.convergence_status) == "converged":
+        presentation = flash_presentation_kind(result)
+        if presentation == "success":
             st.success(
                 f"Solver status: {status_text(view.convergence_status)}",
                 icon=":material/check_circle:",
             )
+        elif presentation == "information":
+            st.info(
+                "Phase stability is conclusive. No two-phase split was required. "
+                f"Selected single-phase Z = {_full_precision(view.single_phase_z)}.",
+                icon=":material/info:",
+            )
         else:
             st.error(
                 f"Solver status: {status_text(view.convergence_status)} · "
@@ -292,6 +305,45 @@ def render_overview(inputs: ScientificInputs | None) -> None:
     )
     if envelope is None:
         st.caption("Calculate a phase envelope to establish this relationship.")
+    if inputs is not None:
+        envelope_export = cast(
+            PhaseEnvelopeResult | None, get_result(session(), "envelope")
+        )
+        if result_is_stale(session(), "envelope", inputs):
+            envelope_export = None
+        critical_export = cast(
+            MixtureCriticalPointResult | None, get_result(session(), "critical")
+        )
+        if result_is_stale(session(), "critical", inputs):
+            critical_export = None
+        document = build_export_document(
+            inputs,
+            flash_result=None if flash_stale else result,
+            envelope_result=envelope_export,
+            critical_result=critical_export,
+        )
+        st.subheader("Export current case")
+        with st.container(horizontal=True):
+            st.download_button(
+                "Download CSV",
+                data=export_csv_bytes(document),
+                file_name="pvt-current-case.csv",
+                mime="text/csv;charset=utf-8",
+                key="download_current_case_csv",
+                on_click="ignore",
+                width="content",
+                icon=":material/download:",
+            )
+            st.download_button(
+                "Download JSON",
+                data=export_json_bytes(document),
+                file_name="pvt-current-case.json",
+                mime="application/json",
+                key="download_current_case_json",
+                on_click="ignore",
+                width="content",
+                icon=":material/download:",
+            )
     details = st.expander("Technical details", icon=":material/table_view:")
     with details:
         _flash_details(result)
diff --git a/tests/test_app_adapters.py b/tests/test_app_adapters.py
index 6a5f14e..5af8389 100644
--- a/tests/test_app_adapters.py
+++ b/tests/test_app_adapters.py
@@ -2,8 +2,11 @@
 
 from __future__ import annotations
 
+import csv
 import hashlib
+import json
 from dataclasses import replace
+from io import StringIO
 from pathlib import Path
 from types import SimpleNamespace
 from typing import cast
@@ -14,7 +17,10 @@ from pvt_phase_simulator.eos.critical_point import (
     CriticalPointStatus,
     solve_mixture_critical_point,
 )
-from pvt_phase_simulator.eos.flash import calculate_two_phase_flash
+from pvt_phase_simulator.eos.flash import (
+    FlashConvergenceStatus,
+    calculate_two_phase_flash,
+)
 from pvt_phase_simulator.fluid_models import FluidMixture
 from pvt_phase_simulator.plotting import (
     PressureUnit,
@@ -27,6 +33,7 @@ from pvt_phase_simulator_ui.adapters import (
     InputValidationError,
     adapt_critical_result,
     adapt_flash_result,
+    flash_presentation_kind,
     load_module17_records,
     location_relative_to_envelope,
     relative_pressure_error_percent,
@@ -34,6 +41,11 @@ from pvt_phase_simulator_ui.adapters import (
     validate_scientific_inputs,
     validation_pressure_error_summary,
 )
+from pvt_phase_simulator_ui.exports import (
+    build_export_document,
+    export_csv_bytes,
+    export_json_bytes,
+)
 from pvt_phase_simulator_ui.state import (
     get_result,
     initialize_session,
@@ -136,6 +148,121 @@ def test_structured_flash_failure_is_not_reclassified() -> None:
     assert view.convergence_status is failed.convergence_status
 
 
+def test_single_phase_presentation_is_informational_but_failure_is_error() -> None:
+    inputs, result = run_validated_flash((50.0, 0.0, 50.0), 300.0, 20.0)
+    assert inputs.pressure_pa == 20_000_000.0
+    assert flash_presentation_kind(result) == "information"
+    assert result.single_phase_root == 0.5828298153218298
+
+    failed = replace(
+        result,
+        convergence_status=FlashConvergenceStatus.FAILED,
+        failure_reason="STRUCTURED_TEST_FAILURE",
+    )
+    assert flash_presentation_kind(failed) == "error"
+
+
+def test_current_case_json_preserves_precision_and_unavailable_semantics() -> None:
+    inputs, result = run_validated_flash((50.0, 0.0, 50.0), 300.0, 20.0)
+    document = build_export_document(inputs, flash_result=result)
+    encoded = export_json_bytes(document)
+    decoded = json.loads(encoded)
+    flash = decoded["results"]["flash"]
+
+    assert encoded == export_json_bytes(document)
+    assert decoded["schema"]["version"] == "1.0.0"
+    assert decoded["case"]["pressure_pa"] == 20_000_000.0
+    assert flash["selected_single_phase_z"]["value"] == result.single_phase_root
+    assert flash["selected_single_phase_z"]["value"] == 0.5828298153218298
+    assert flash["vapor_fraction"]["status"] == "not_applicable"
+    assert flash["vapor_fraction"]["value"] is None
+    assert decoded["results"]["phase_envelope"] == {
+        "calculation_status": "not_calculated"
+    }
+    assert decoded["results"]["critical_point"] == {
+        "calculation_status": "not_calculated"
+    }
+
+
+def test_current_case_csv_is_utf8_tidy_and_uses_source_float_values() -> None:
+    inputs, result = run_validated_flash((50.0, 0.0, 50.0), 300.0, 20.0)
+    encoded = export_csv_bytes(build_export_document(inputs, flash_result=result))
+    assert encoded.startswith(b"\xef\xbb\xbf")
+    rows = list(csv.DictReader(StringIO(encoded.decode("utf-8-sig"))))
+    values = {(row["section"], row["path"]): row["value"] for row in rows}
+
+    assert values[("case", "pressure_pa")] == "20000000.0"
+    assert values[("case", "components[0].overall_mole_fraction")] == "0.5"
+    assert values[("results", "flash.selected_single_phase_z.value")] == repr(
+        result.single_phase_root
+    )
+    assert values[("results", "flash.vapor_fraction.status")] == "not_applicable"
+
+
+def test_export_without_calculated_results_does_not_fabricate_fields() -> None:
+    inputs = validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 20.0)
+    results = build_export_document(inputs)["results"]
+    assert results == {
+        "flash": {"calculation_status": "not_calculated"},
+        "phase_envelope": {"calculation_status": "not_calculated"},
+        "critical_point": {"calculation_status": "not_calculated"},
+    }
+
+
+def test_envelope_export_preserves_branch_points_and_termination_evidence() -> None:
+    inputs = validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 5.0)
+    saturation = SimpleNamespace(
+        parent_composition=(0.5, 0.0, 0.5),
+        incipient_composition=(0.2, 0.1, 0.7),
+        k_values=(0.4, 1.25, 1.4),
+        fugacity_equilibrium_residuals=(1.0e-13, None, -2.0e-13),
+        maximum_fugacity_equilibrium_residual=2.0e-13,
+        composition_sum_residual=4.440892098500626e-16,
+        pressure_residual=1.2345678901234567e-10,
+    )
+    point = SimpleNamespace(
+        status="converged",
+        temperature_k=300.1234567890123,
+        pressure_pa=8_669_987.654321097,
+        saturation_result=saturation,
+    )
+    envelope = SimpleNamespace(
+        bubble_branch=SimpleNamespace(
+            branch_kind="bubble",
+            termination_reason="target_reached",
+            termination_message="Bubble target reached.",
+            points=(point,),
+            rejected_attempts=(object(),),
+        ),
+        dew_branch=SimpleNamespace(
+            branch_kind="dew",
+            termination_reason="corrector_failed",
+            termination_message="Dew corrector stopped safely.",
+            points=(),
+            rejected_attempts=(),
+        ),
+    )
+    exported = build_export_document(  # type: ignore[arg-type]
+        inputs, envelope_result=envelope
+    )["results"]["phase_envelope"]
+
+    assert exported["bubble_branch"]["points"][0]["pressure_pa"] == (
+        8_669_987.654321097
+    )
+    assert exported["bubble_branch"]["points"][0]["pressure_residual"] == (
+        1.2345678901234567e-10
+    )
+    assert exported["bubble_branch"]["rejected_attempt_count"] == 1
+    assert exported["dew_branch"] == {
+        "branch_kind": "dew",
+        "termination_status": "corrector_failed",
+        "termination_message": "Dew corrector stopped safely.",
+        "accepted_point_count": 0,
+        "rejected_attempt_count": 0,
+        "points": [],
+    }
+
+
 def test_critical_certification_and_approved_regression() -> None:
     inputs = validate_scientific_inputs((50.0, 0.0, 50.0), 320.0, 8.5)
     result = solve_mixture_critical_point(
@@ -160,6 +287,27 @@ def test_critical_certification_and_approved_regression() -> None:
     assert rejected.temperature_k is None
     assert rejected.pressure_pa is None
     assert rejected.lambda_min is None
+    certified_export = build_export_document(inputs, critical_result=result)["results"][
+        "critical_point"
+    ]
+    assert certified_export["certified"] is True
+    assert certified_export["temperature_k"]["value"] == result.temperature_k
+    assert certified_export["pressure_pa"]["value"] == result.pressure_pa
+
+    uncertified_export = build_export_document(inputs, critical_result=uncertified)[
+        "results"
+    ]["critical_point"]
+    assert uncertified_export["certified"] is False
+    assert uncertified_export["temperature_k"]["status"] == "unavailable"
+    assert uncertified_export["temperature_k"]["value"] is None
+    assert uncertified_export["pressure_pa"]["value"] is None
+    assert uncertified_export["lambda_min"] == {
+        "status": "available",
+        "value": 0.0,
+    }
+    assert uncertified_export["scaled_residual_norm"]["value"] == (
+        uncertified.scaled_residual_norm
+    )
 
 
 def test_session_state_is_deterministic_and_marks_scientific_changes_stale() -> None:
diff --git a/tests/test_app_streamlit.py b/tests/test_app_streamlit.py
index a91fb35..5b9137a 100644
--- a/tests/test_app_streamlit.py
+++ b/tests/test_app_streamlit.py
@@ -79,6 +79,26 @@ def test_invalid_form_submission_never_creates_a_flash_result() -> None:
     assert any("Submission unavailable" in error.value for error in app.error)
 
 
+def test_valid_single_phase_uses_information_semantics_and_offers_exports() -> None:
+    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
+    app.number_input[4].set_value(20.0)
+    app.button[0].click().run()
+
+    assert not app.exception
+    assert not any("Solver status" in error.value for error in app.error)
+    assert any(
+        "No two-phase split was required" in info.value
+        and "0.5828298153218298" in info.value
+        for info in app.info
+    )
+    downloads = app.get("download_button")
+    assert [button.label for button in downloads] == ["Download CSV", "Download JSON"]
+    assert [button.key for button in downloads] == [
+        "download_current_case_csv",
+        "download_current_case_json",
+    ]
+
+
 def test_navigation_module21_reuse_and_no_deprecated_width_argument() -> None:
     app_source = (ROOT / "src" / "pvt_phase_simulator_ui" / "app.py").read_text(
         encoding="utf-8"

diff --git a/src/pvt_phase_simulator_ui/exports.py b/src/pvt_phase_simulator_ui/exports.py
new file mode 100644
--- /dev/null
+++ b/src/pvt_phase_simulator_ui/exports.py
+"""Deterministic, calculation-free exports for the submitted UI case."""
+
+from __future__ import annotations
+
+import csv
+import json
+from collections.abc import Iterator, Mapping, Sequence
+from io import StringIO
+from typing import Literal
+
+from pvt_phase_simulator.eos.critical_point import MixtureCriticalPointResult
+from pvt_phase_simulator.eos.flash import TwoPhaseFlashResult
+from pvt_phase_simulator.eos.phase_envelope import (
+    PhaseEnvelopeBranchResult,
+    PhaseEnvelopePoint,
+    PhaseEnvelopeResult,
+)
+from pvt_phase_simulator_ui.adapters import (
+    COMPONENT_NAMES,
+    ScientificInputs,
+    adapt_critical_result,
+    adapt_flash_result,
+)
+
+EXPORT_SCHEMA_NAME = "pvt-phase-simulator-current-case"
+EXPORT_SCHEMA_VERSION = "1.0.0"
+
+
+def _enum_value(value: object) -> str:
+    return str(value.value if hasattr(value, "value") else value)
+
+
+def _available(value: object) -> dict[str, object]:
+    return {"status": "available", "value": value}
+
+
+def _missing(
+    status: Literal["not_applicable", "unavailable"], reason: str
+) -> dict[str, object]:
+    return {"status": status, "value": None, "reason": reason}
+
+
+def _optional_result_value(
+    value: object | None, *, not_applicable: bool, reason: str
+) -> dict[str, object]:
+    if value is not None:
+        return _available(value)
+    if not_applicable:
+        return _missing("not_applicable", reason)
+    return _missing(
+        "unavailable", "The calculated production result did not supply it."
+    )
+
+
+def _flash_export(result: TwoPhaseFlashResult) -> dict[str, object]:
+    view = adapt_flash_result(result)
+    phase_state = _enum_value(view.phase_state)
+    single_phase = phase_state == "single_phase"
+    two_phase = phase_state == "two_phase"
+    split_reason = "No two-phase split was required for this single-phase result."
+    single_reason = "A selected single-phase Z is not applicable to a two-phase result."
+    split_required: object
+    if single_phase:
+        split_required = False
+    elif two_phase:
+        split_required = True
+    else:
+        split_required = _missing(
+            "unavailable",
+            "The phase classification does not establish whether a split is required.",
+        )
+    return {
+        "calculation_status": "calculated",
+        "phase_classification": phase_state,
+        "phase_stability_status": _enum_value(result.phase_stability.status),
+        "solver_status": _enum_value(view.convergence_status),
+        "termination_or_failure_reason": view.failure_reason,
+        "two_phase_split_required": split_required,
+        "iteration_count": view.iteration_count,
+        "vapor_fraction": _optional_result_value(
+            view.vapor_fraction, not_applicable=single_phase, reason=split_reason
+        ),
+        "liquid_fraction": _optional_result_value(
+            view.liquid_fraction, not_applicable=single_phase, reason=split_reason
+        ),
+        "liquid_z": _optional_result_value(
+            view.liquid_z, not_applicable=single_phase, reason=split_reason
+        ),
+        "vapor_z": _optional_result_value(
+            view.vapor_z, not_applicable=single_phase, reason=split_reason
+        ),
+        "selected_single_phase_z": _optional_result_value(
+            view.single_phase_z, not_applicable=two_phase, reason=single_reason
+        ),
+        "liquid_composition": _optional_result_value(
+            view.liquid_composition, not_applicable=single_phase, reason=split_reason
+        ),
+        "vapor_composition": _optional_result_value(
+            view.vapor_composition, not_applicable=single_phase, reason=split_reason
+        ),
+        "k_values": _optional_result_value(
+            view.final_k_values, not_applicable=single_phase, reason=split_reason
+        ),
+        "equilibrium_residuals": _optional_result_value(
+            view.equilibrium_residuals or None,
+            not_applicable=single_phase,
+            reason=split_reason,
+        ),
+        "material_balance_residuals": _optional_result_value(
+            view.material_balance_residuals or None,
+            not_applicable=single_phase,
+            reason=split_reason,
+        ),
+    }
+
+
+def _envelope_point_export(point: PhaseEnvelopePoint) -> dict[str, object]:
+    saturation = point.saturation_result
+    return {
+        "status": _enum_value(point.status),
+        "temperature_k": point.temperature_k,
+        "pressure_pa": point.pressure_pa,
+        "parent_composition": saturation.parent_composition,
+        "incipient_composition": saturation.incipient_composition,
+        "k_values": saturation.k_values,
+        "equilibrium_residuals": saturation.fugacity_equilibrium_residuals,
+        "maximum_equilibrium_residual": (
+            saturation.maximum_fugacity_equilibrium_residual
+        ),
+        "composition_sum_residual": saturation.composition_sum_residual,
+        "pressure_residual": saturation.pressure_residual,
+    }
+
+
+def _envelope_branch_export(
+    branch: PhaseEnvelopeBranchResult,
+) -> dict[str, object]:
+    return {
+        "branch_kind": _enum_value(branch.branch_kind),
+        "termination_status": _enum_value(branch.termination_reason),
+        "termination_message": branch.termination_message,
+        "accepted_point_count": len(branch.points),
+        "rejected_attempt_count": len(branch.rejected_attempts),
+        "points": [_envelope_point_export(point) for point in branch.points],
+    }
+
+
+def _envelope_export(result: PhaseEnvelopeResult) -> dict[str, object]:
+    return {
+        "calculation_status": "calculated",
+        "bubble_branch": _envelope_branch_export(result.bubble_branch),
+        "dew_branch": _envelope_branch_export(result.dew_branch),
+    }
+
+
+def _critical_export(result: MixtureCriticalPointResult) -> dict[str, object]:
+    view = adapt_critical_result(result)
+    reason = "No certified critical value is available from this production result."
+    return {
+        "calculation_status": "calculated",
+        "solver_status": _enum_value(view.status),
+        "certified": view.certified,
+        "termination_reason": view.termination_reason,
+        "iteration_count": view.iterations,
+        "temperature_k": _optional_result_value(
+            view.temperature_k, not_applicable=False, reason=reason
+        ),
+        "pressure_pa": _optional_result_value(
+            view.pressure_pa, not_applicable=False, reason=reason
+        ),
+        "lambda_min": _optional_result_value(
+            result.lambda_min, not_applicable=False, reason=reason
+        ),
+        "cubic_coefficient": _optional_result_value(
+            result.cubic_coefficient, not_applicable=False, reason=reason
+        ),
+        "scaled_residual_norm": _optional_result_value(
+            result.scaled_residual_norm, not_applicable=False, reason=reason
+        ),
+        "critical_direction": _optional_result_value(
+            result.critical_direction, not_applicable=False, reason=reason
+        ),
+    }
+
+
+def build_export_document(
+    inputs: ScientificInputs,
+    *,
+    flash_result: TwoPhaseFlashResult | None = None,
+    envelope_result: PhaseEnvelopeResult | None = None,
+    critical_result: MixtureCriticalPointResult | None = None,
+) -> dict[str, object]:
+    """Build an export solely from submitted inputs and already-held results."""
+
+    components = [
+        {
+            "name": name,
+            "overall_mole_fraction": mole_fraction,
+            "composition_mol_percent": mol_percent,
+        }
+        for name, mole_fraction, mol_percent in zip(
+            COMPONENT_NAMES,
+            inputs.mole_fractions,
+            inputs.composition_mol_percent,
+            strict=True,
+        )
+    ]
+    return {
+        "schema": {
+            "name": EXPORT_SCHEMA_NAME,
+            "version": EXPORT_SCHEMA_VERSION,
+        },
+        "metadata": {
+            "eos": "Peng-Robinson",
+            "unit_system": "SI",
+            "binary_interaction_assumption": "kij = 0",
+            "verified_component_scope": list(COMPONENT_NAMES),
+            "export_timestamp": {
+                "status": "omitted",
+                "reason": "Omitted to keep exports reproducible.",
+            },
+        },
+        "case": {
+            "temperature_k": inputs.temperature_k,
+            "pressure_pa": inputs.pressure_pa,
+            "pressure_mpa": inputs.pressure_mpa,
+            "model": "Peng-Robinson",
+            "binary_interaction_assumption": "kij = 0",
+            "components": components,
+        },
+        "results": {
+            "flash": (
+                {"calculation_status": "not_calculated"}
+                if flash_result is None
+                else _flash_export(flash_result)
+            ),
+            "phase_envelope": (
+                {"calculation_status": "not_calculated"}
+                if envelope_result is None
+                else _envelope_export(envelope_result)
+            ),
+            "critical_point": (
+                {"calculation_status": "not_calculated"}
+                if critical_result is None
+                else _critical_export(critical_result)
+            ),
+        },
+    }
+
+
+def export_json_bytes(document: Mapping[str, object]) -> bytes:
+    """Serialize deterministic, round-trippable JSON without float rounding."""
+
+    return (
+        json.dumps(
+            document,
+            ensure_ascii=False,
+            allow_nan=False,
+            indent=2,
+            sort_keys=True,
+        )
+        + "\n"
+    ).encode("utf-8")
+
+
+def _flatten(value: object, path: str = "") -> Iterator[tuple[str, str, object]]:
+    if isinstance(value, Mapping):
+        for key in sorted(value, key=str):
+            child = f"{path}.{key}" if path else str(key)
+            yield from _flatten(value[key], child)
+        return
+    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
+        if not value:
+            section, _, nested_path = path.partition(".")
+            yield section, nested_path, "[]"
+            return
+        for index, item in enumerate(value):
+            yield from _flatten(item, f"{path}[{index}]")
+        return
+    section, _, nested_path = path.partition(".")
+    yield section, nested_path, value
+
+
+def _csv_value(value: object) -> str:
+    if value is None:
+        return "null"
+    if isinstance(value, bool):
+        return "true" if value else "false"
+    if isinstance(value, float):
+        return repr(value)
+    return str(value)
+
+
+def export_csv_bytes(document: Mapping[str, object]) -> bytes:
+    """Serialize a deterministic path/value CSV with Excel-friendly UTF-8 BOM."""
+
+    output = StringIO(newline="")
+    writer = csv.writer(output, lineterminator="\n")
+    writer.writerow(("section", "path", "value"))
+    for section, path, value in _flatten(document):
+        writer.writerow((section, path, _csv_value(value)))
+    return output.getvalue().encode("utf-8-sig")
```

## Required final output

End with exactly one machine-readable block:

<ORCHESTRATOR_RESULT>
{
  "review_type": "PROVISIONAL_CODEX_REVIEW",
  "verdict": "APPROVED",
  "findings": [
    {"id": "PCR-1", "severity": "C", "blocks": true, "summary": "..."}
  ]
}
</ORCHESTRATOR_RESULT>

`verdict` must be exactly APPROVED or NOT_APPROVED. This review is not an
independent audit and must never be described as one.
