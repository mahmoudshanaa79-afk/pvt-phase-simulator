"""Polished Streamlit frontend for the verified PVT scientific engine."""

from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal, cast

import pandas as pd  # type: ignore[import-untyped]
import streamlit as st

from app.adapters import (
    COMPONENT_NAMES,
    PA_PER_MPA,
    InputValidationError,
    ScientificInputs,
    adapt_critical_result,
    adapt_flash_result,
    composition_total,
    load_module17_records,
    location_relative_to_envelope,
    run_validated_flash,
    status_text,
    validate_scientific_inputs,
)
from app.state import get_result, initialize_session, result_is_stale, store_result
from app.styles import apply_styles
from pvt_phase_simulator.eos.critical_point import (
    CriticalPointScanResult,
    CriticalPointScanSettings,
    MixtureCriticalPointResult,
    scan_mixture_criticality,
    solve_mixture_critical_point,
)
from pvt_phase_simulator.eos.flash import TwoPhaseFlashResult
from pvt_phase_simulator.eos.phase_envelope import (
    EnvelopeContinuationSettings,
    PhaseEnvelopeResult,
    calculate_phase_envelope,
)
from pvt_phase_simulator.plotting import (
    CompositionDisplay,
    PressureUnit,
    plot_critical_solver_conditioning,
    plot_critical_solver_convergence,
    plot_critical_solver_path,
    plot_criticality_map,
    plot_phase_compositions,
    plot_phase_envelope,
    plot_validation_composition_parity,
    plot_validation_pressure_error,
    plot_validation_pressure_parity,
    plot_validation_retrospective_diagnostics,
    plot_validation_status,
)

ROOT = Path(__file__).resolve().parents[1]
PAGES = ("Overview", "Phase Envelope", "Critical Point", "Validation", "Diagnostics")


def _state() -> MutableMapping[str, Any]:
    return cast(MutableMapping[str, Any], st.session_state)


def _value(item: object) -> str:
    return str(item.value if hasattr(item, "value") else item)


def _optional(value: float | None, digits: int = 6) -> str:
    return "Unavailable" if value is None else f"{value:.{digits}g}"


def _inputs() -> ScientificInputs | None:
    st.sidebar.markdown("## Fluid Input")
    st.sidebar.caption("Verified v1.0 components. Enter composition in mol %.")
    values = (
        st.sidebar.number_input("Methane (mol %)", value=50.0, format="%.10g"),
        st.sidebar.number_input("Ethane (mol %)", value=0.0, format="%.10g"),
        st.sidebar.number_input("Propane (mol %)", value=50.0, format="%.10g"),
    )
    total = composition_total(values)
    if abs(total - 100.0) <= 1.0e-8 and all(0.0 <= value <= 100.0 for value in values):
        st.sidebar.success(f"Total: {total:.12g} mol %")
    else:
        st.sidebar.error(f"Total: {total:.12g} mol %. Required: 100 mol %.")
    temperature = st.sidebar.number_input(
        "Temperature (K)", value=300.0, format="%.10g"
    )
    pressure = st.sidebar.number_input("Pressure (MPa)", value=5.0, format="%.10g")
    try:
        inputs = validate_scientific_inputs(values, temperature, pressure)
    except InputValidationError as error:
        inputs = None
        st.sidebar.error(str(error))
    if st.sidebar.button(
        "RUN FLASH", type="primary", use_container_width=True, disabled=inputs is None
    ):
        try:
            run_inputs, result = run_validated_flash(values, temperature, pressure)
            store_result(_state(), "flash", result, run_inputs)
            st.sidebar.success("Structured flash result received.")
        except (ValueError, ArithmeticError) as error:
            st.sidebar.error(f"Flash calculation failure: {error}")
    st.sidebar.caption(
        "Pressure is converted exactly from MPa to internal Pa. "
        "Calculations require an explicit action."
    )
    return inputs


def _navigation() -> str:
    st.markdown(
        """
        <div class="pvt-header">
          <div class="pvt-kicker">PVT PHASE SIMULATOR</div>
          <div class="pvt-title">Hydrocarbon phase behavior</div>
          <p class="pvt-subtitle">Peng-Robinson EOS - Hydrocarbon Phase Behavior</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    return st.radio(
        "Application view",
        PAGES,
        horizontal=True,
        label_visibility="collapsed",
        key="navigation",
    )


def _stale(name: str, inputs: ScientificInputs | None) -> None:
    if result_is_stale(_state(), name, inputs):
        st.markdown(
            '<div class="pvt-status pvt-stale"><strong>Stale result.</strong> '
            "Scientific inputs changed. Run this calculation again before use.</div>",
            unsafe_allow_html=True,
        )


def _overview(inputs: ScientificInputs | None) -> None:
    st.header("Overview")
    raw = get_result(_state(), "flash")
    if raw is None:
        st.info("Enter valid conditions and select RUN FLASH to calculate a state.")
        return
    result = cast(TwoPhaseFlashResult, raw)
    view = adapt_flash_result(result)
    _stale("flash", inputs)
    st.markdown(
        f'<div class="pvt-status"><strong>{status_text(view.phase_state)}</strong> | '
        f"{status_text(view.convergence_status)}</div>",
        unsafe_allow_html=True,
    )
    metrics = st.columns(4)
    metrics[0].metric("Temperature", f"{view.temperature_k:.8g} K")
    metrics[1].metric("Pressure", f"{view.pressure_pa / PA_PER_MPA:.15g} MPa")
    metrics[2].metric("Vapor fraction", _optional(view.vapor_fraction))
    metrics[3].metric("Liquid fraction", _optional(view.liquid_fraction))
    z_metrics = st.columns(2)
    z_metrics[0].metric("Liquid Z", _optional(view.liquid_z))
    z_metrics[1].metric("Vapor Z", _optional(view.vapor_z))
    envelope = cast(PhaseEnvelopeResult | None, get_result(_state(), "envelope"))
    if result_is_stale(_state(), "envelope", inputs):
        envelope = None
    st.write(
        "**Location relative to phase envelope:** "
        + location_relative_to_envelope(envelope, view.temperature_k, view.pressure_pa)
    )
    rows: dict[str, tuple[float, ...]] = {
        "Feed (mol %)": tuple(
            100.0 * item.mole_fraction for item in result.feed_mixture.components
        )
    }
    if view.liquid_composition is not None:
        rows["Liquid (mol %)"] = tuple(
            100.0 * value for value in view.liquid_composition
        )
    if view.vapor_composition is not None:
        rows["Vapor (mol %)"] = tuple(100.0 * value for value in view.vapor_composition)
    st.subheader("Composition")
    st.dataframe(pd.DataFrame(rows, index=COMPONENT_NAMES).T, use_container_width=True)
    if view.single_phase_z is not None:
        st.caption(
            f"Single-phase selected root Z: {view.single_phase_z:.10g}. "
            "It is not labelled as liquid Z or vapor Z."
        )
    with st.expander("Technical details"):
        st.write("Iterations", view.iteration_count)
        st.write("Failure or termination", view.failure_reason or "None")
        if view.final_k_values is not None:
            st.write("Final K values", view.final_k_values)
        if view.equilibrium_residuals:
            st.write("Equilibrium residuals", view.equilibrium_residuals)
        if view.material_balance_residuals:
            st.write("Material-balance residuals", view.material_balance_residuals)
        for label, phase in (
            ("Liquid", result.liquid_phase),
            ("Vapor", result.vapor_phase),
        ):
            if phase is not None:
                st.write(
                    f"{label} log fugacity coefficients",
                    phase.component_log_fugacity_coefficients,
                )


def _calculate_envelope(inputs: ScientificInputs) -> PhaseEnvelopeResult:
    settings = EnvelopeContinuationSettings(
        target_temperature_k=inputs.temperature_k + 50.0,
        initial_temperature_step_k=5.0,
        maximum_points=15,
    )
    return calculate_phase_envelope(
        inputs.mixture(),
        settings,
        settings,
        inputs.temperature_k,
        inputs.temperature_k,
    )


def _envelope(inputs: ScientificInputs | None) -> None:
    st.header("Phase Envelope")
    st.write(
        "Bubble and dew identities are retained. Unavailable points remain "
        "visibly non-converged."
    )
    if st.button("RUN PHASE ENVELOPE", disabled=inputs is None):
        assert inputs is not None
        with st.spinner("Tracing independent bubble and dew branches..."):
            try:
                store_result(_state(), "envelope", _calculate_envelope(inputs), inputs)
            except (ValueError, ArithmeticError) as error:
                st.error(f"Phase-envelope calculation could not start: {error}")
    raw = get_result(_state(), "envelope")
    if raw is None:
        st.info("No envelope result is available. This calculation is optional.")
        return
    result = cast(PhaseEnvelopeResult, raw)
    _stale("envelope", inputs)
    critical = cast(MixtureCriticalPointResult | None, get_result(_state(), "critical"))
    if result_is_stale(_state(), "critical", inputs):
        critical = None
    st.plotly_chart(
        plot_phase_envelope(
            result,
            pressure_unit=PressureUnit.MPA,
            critical_point=critical,
            metadata={"model": "Peng-Robinson EOS; kij=0"},
        ),
        use_container_width=True,
    )
    columns = st.columns(2)
    columns[0].metric(
        "Bubble termination", status_text(result.bubble_branch.termination_reason)
    )
    columns[1].metric(
        "Dew termination", status_text(result.dew_branch.termination_reason)
    )
    st.caption(
        "Pressure or temperature turning points are continuation geometry. "
        "They are not certified critical points."
    )
    component = st.selectbox("Composition component", COMPONENT_NAMES)
    branch = cast(
        Literal["bubble", "dew"],
        st.radio("Composition branch", ("bubble", "dew"), horizontal=True),
    )
    try:
        st.plotly_chart(
            plot_phase_compositions(
                result,
                branch=branch,
                component_index=COMPONENT_NAMES.index(component),
                display=CompositionDisplay.MOL_PERCENT,
                pressure_unit=PressureUnit.MPA,
            ),
            use_container_width=True,
        )
    except ValueError as error:
        st.info(f"Phase-composition figure unavailable: {error}")


def _calculate_critical(inputs: ScientificInputs) -> MixtureCriticalPointResult:
    return solve_mixture_critical_point(
        inputs.mixture(),
        inputs.temperature_k,
        inputs.pressure_pa,
        initialization_source="streamlit_user_conditions",
    )


def _calculate_scan(inputs: ScientificInputs) -> CriticalPointScanResult:
    return scan_mixture_criticality(
        inputs.mixture(),
        CriticalPointScanSettings(
            0.8 * inputs.temperature_k,
            1.2 * inputs.temperature_k,
            0.5 * inputs.pressure_pa,
            1.5 * inputs.pressure_pa,
            temperature_points=7,
            pressure_points=7,
        ),
    )


def _critical(inputs: ScientificInputs | None) -> None:
    st.header("Critical Point")
    st.write(
        "Certification requires a converged Module 20 result and both critical "
        "conditions. lambda_min=0 alone is a spinodal condition."
    )
    controls = st.columns(2)
    if controls[0].button("RUN CRITICAL SOLVER", disabled=inputs is None):
        assert inputs is not None
        with st.spinner("Solving fixed-composition critical conditions..."):
            try:
                store_result(_state(), "critical", _calculate_critical(inputs), inputs)
            except (ValueError, ArithmeticError) as error:
                st.error(f"Critical solver could not start: {error}")
    if controls[1].button("RUN CRITICALITY MAP", disabled=inputs is None):
        assert inputs is not None
        with st.spinner("Evaluating the bounded diagnostic map..."):
            try:
                store_result(_state(), "critical_scan", _calculate_scan(inputs), inputs)
            except (ValueError, ArithmeticError) as error:
                st.error(f"Criticality map could not be evaluated: {error}")
    raw = get_result(_state(), "critical")
    if raw is None:
        st.info("No critical-point solve has been requested.")
    else:
        result = cast(MixtureCriticalPointResult, raw)
        view = adapt_critical_result(result)
        _stale("critical", inputs)
        st.markdown(
            f'<div class="pvt-status"><strong>{status_text(view.status)}</strong> | '
            + ("Certified critical point" if view.certified else "Not certified")
            + "</div>",
            unsafe_allow_html=True,
        )
        if view.certified:
            assert view.temperature_k is not None
            assert view.pressure_pa is not None
            metrics = st.columns(4)
            metrics[0].metric("Tc", f"{view.temperature_k:.13g} K")
            metrics[1].metric("Pc", f"{view.pressure_pa / PA_PER_MPA:.15g} MPa")
            metrics[2].metric("lambda_min", _optional(view.lambda_min, 8))
            metrics[3].metric("C", _optional(view.cubic_coefficient, 8))
            st.write("Critical direction", view.critical_direction)
        st.write("Termination", view.termination_reason)
        st.write("Iterations", view.iterations)
        if result.history:
            st.plotly_chart(
                plot_critical_solver_convergence(result), use_container_width=True
            )
            st.plotly_chart(plot_critical_solver_path(result), use_container_width=True)
        if result.jacobian_condition_history:
            st.plotly_chart(
                plot_critical_solver_conditioning(result), use_container_width=True
            )
    scan_raw = get_result(_state(), "critical_scan")
    if scan_raw is not None:
        _stale("critical_scan", inputs)
        overlay = cast(MixtureCriticalPointResult | None, raw)
        if result_is_stale(_state(), "critical", inputs):
            overlay = None
        st.plotly_chart(
            plot_criticality_map(
                cast(CriticalPointScanResult, scan_raw),
                pressure_unit=PressureUnit.MPA,
                critical_point=overlay,
                metadata={"model": "Peng-Robinson EOS; kij=0"},
            ),
            use_container_width=True,
        )


@st.cache_data(show_spinner=False)
def _records() -> tuple[Any, ...]:
    return load_module17_records(ROOT)


def _validation() -> None:
    st.header("Validation")
    st.write(
        "Module 17 methane/ethane and methane/propane comparisons use kij=0 "
        "with no fitted binary interaction parameters."
    )
    records = _records()
    direction = cast(
        Literal["bubble", "dew"],
        st.radio("Prediction direction", ("bubble", "dew"), horizontal=True),
    )
    for figure in (
        plot_validation_pressure_parity(
            records, direction=direction, pressure_unit=PressureUnit.MPA
        ),
        plot_validation_pressure_error(records, direction=direction),
        plot_validation_status(records, direction=direction),
    ):
        st.plotly_chart(figure, use_container_width=True)
    try:
        st.plotly_chart(
            plot_validation_composition_parity(
                records,
                direction=direction,
                component_index=0,
                display=CompositionDisplay.MOL_PERCENT,
            ),
            use_container_width=True,
        )
    except (ValueError, IndexError) as error:
        st.info(f"Composition parity unavailable: {error}")
    st.subheader("Retrospective nearest-root diagnostics")
    st.warning(
        "Not production prediction. This validation-only view is separate from "
        "Module 17 production predictions."
    )
    try:
        st.plotly_chart(
            plot_validation_retrospective_diagnostics(
                records, pressure_unit=PressureUnit.MPA
            ),
            use_container_width=True,
        )
    except ValueError as error:
        st.info(f"Retrospective diagnostics unavailable: {error}")
    st.caption("Relative pressure error is 100*(P_pred-P_exp)/P_exp.")


def _diagnostics(inputs: ScientificInputs | None) -> None:
    st.header("Diagnostics")
    st.write(
        "Public solver evidence is shown without converting structured "
        "failures into success."
    )
    flash_raw = get_result(_state(), "flash")
    if flash_raw is not None:
        result = cast(TwoPhaseFlashResult, flash_raw)
        _stale("flash", inputs)
        st.subheader("Flash and stability")
        st.json(
            {
                "phase_state": _value(result.phase_state),
                "convergence": _value(result.convergence_status),
                "termination_or_failure": result.failure_reason,
                "iterations": len(result.iteration_history),
                "stability_status": _value(result.phase_stability.status),
            }
        )
        if result.diagnostics:
            st.dataframe(
                pd.DataFrame(
                    {
                        "code": item.code,
                        "severity": _value(item.severity),
                        "category": _value(item.category),
                        "message": item.message,
                        "value": item.value,
                    }
                    for item in result.diagnostics
                ),
                use_container_width=True,
            )
        if result.iteration_history:
            latest = result.iteration_history[-1]
            st.write(
                "Latest iteration evidence",
                {
                    "iteration": latest.iteration,
                    "maximum_log_k_residual": latest.maximum_log_k_residual,
                    "maximum_fugacity_equilibrium_residual": (
                        latest.maximum_fugacity_equilibrium_residual
                    ),
                    "maximum_material_balance_residual": (
                        latest.phase_compositions.maximum_material_balance_residual
                    ),
                    "Rachford-Rice status": _value(latest.rachford_rice.status),
                    "Rachford-Rice iterations": latest.rachford_rice.iterations,
                },
            )
        for phase_name, phase in (
            ("liquid", result.liquid_phase),
            ("vapor", result.vapor_phase),
        ):
            if phase is not None:
                st.write(
                    f"{phase_name.title()} public root selection",
                    asdict(phase.root_selection),
                )
    envelope_raw = get_result(_state(), "envelope")
    if envelope_raw is not None:
        envelope_result = cast(PhaseEnvelopeResult, envelope_raw)
        st.subheader("Envelope continuation")
        st.dataframe(
            pd.DataFrame(
                {
                    "branch": branch.branch_kind.value,
                    "accepted_points": len(branch.points),
                    "rejected_attempts": len(branch.rejected_attempts),
                    "termination": branch.termination_reason.value,
                    "message": branch.termination_message,
                }
                for branch in (
                    envelope_result.bubble_branch,
                    envelope_result.dew_branch,
                )
            ),
            use_container_width=True,
        )
        st.caption("Turning indicators are continuation geometry, not critical points.")
    critical_raw = get_result(_state(), "critical")
    if critical_raw is not None:
        critical_result = cast(MixtureCriticalPointResult, critical_raw)
        st.subheader("Critical solver")
        st.json(
            {
                "status": critical_result.status.value,
                "termination": critical_result.termination_reason,
                "iterations": critical_result.iterations,
                "accepted_steps": critical_result.accepted_steps,
                "rejected_steps": critical_result.rejected_steps,
                "function_evaluations": critical_result.function_evaluations,
                "jacobian_condition_history": (
                    critical_result.jacobian_condition_history
                ),
                "certified": adapt_critical_result(critical_result).certified,
            }
        )
        if critical_result.criticality_result is not None:
            st.write(
                "Final public criticality result",
                asdict(critical_result.criticality_result),
            )
    if flash_raw is None and envelope_raw is None and critical_raw is None:
        st.info("Run a calculation to populate public diagnostics.")


def main() -> None:
    """Render the application through public scientific APIs only."""

    st.set_page_config(
        page_title="PVT Phase Simulator",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_styles()
    initialize_session(_state())
    inputs = _inputs()
    page = _navigation()
    if page == "Overview":
        _overview(inputs)
    elif page == "Phase Envelope":
        _envelope(inputs)
    elif page == "Critical Point":
        _critical(inputs)
    elif page == "Validation":
        _validation()
    else:
        _diagnostics(inputs)


if __name__ == "__main__":
    main()
