"""Engineering page presentations over immutable public scientific results."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal, cast

import pandas as pd  # type: ignore[import-untyped]
import streamlit as st

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
from pvt_phase_simulator_ui.adapters import (
    COMPONENT_NAMES,
    PA_PER_MPA,
    ScientificInputs,
    adapt_critical_result,
    adapt_flash_result,
    flash_presentation_kind,
    load_module17_records,
    location_relative_to_envelope,
    status_text,
    validation_pressure_error_summary,
)
from pvt_phase_simulator_ui.context import session
from pvt_phase_simulator_ui.exports import (
    build_export_document,
    export_csv_bytes,
    export_json_bytes,
)
from pvt_phase_simulator_ui.state import get_result, result_is_stale, store_result
from pvt_phase_simulator_ui.styles import phase_split_bar

ROOT = Path(__file__).resolve().parents[2]


def _value(item: object) -> str:
    return str(item.value if hasattr(item, "value") else item)


def _optional(value: float | None, digits: int = 6) -> str:
    return "Unavailable" if value is None else f"{value:.{digits}g}"


def _full_precision(value: float | None) -> str:
    return "Unavailable" if value is None else repr(float(value))


def _action_requirement(inputs: ScientificInputs | None) -> None:
    if inputs is None:
        st.caption(":material/lock: Submit RUN FLASH to enable this action.")


def _wide_chart(figure: Any, *, key: str | None = None) -> None:
    st.plotly_chart(figure, width="stretch", height=500, key=key)


def _square_chart(figure: Any, *, key: str) -> None:
    with st.container(horizontal_alignment="center"):
        st.plotly_chart(figure, width=680, height=640, key=key)


def _annotate_missing_envelope_branches(
    figure: Any, result: PhaseEnvelopeResult
) -> Any:
    missing = tuple(
        branch
        for branch in (result.bubble_branch, result.dew_branch)
        if not branch.points
    )
    for index, branch in enumerate(missing):
        branch_name = status_text(branch.branch_kind)
        reason = status_text(branch.termination_reason)
        figure.add_annotation(
            x=0.01,
            y=0.99 - 0.1 * index,
            xref="paper",
            yref="paper",
            xanchor="left",
            yanchor="top",
            showarrow=False,
            align="left",
            text=(
                f"{branch_name} branch not plotted — {reason}: "
                f"{branch.termination_message}"
            ),
            borderpad=5,
            bgcolor="rgba(255,255,255,0.9)",
        )
    return figure


def _stale(name: str, inputs: ScientificInputs | None) -> bool:
    stale = result_is_stale(session(), name, inputs)
    if stale:
        st.warning(
            "Stale result — submitted scientific inputs changed. "
            "Run this calculation again before use.",
            icon=":material/history:",
        )
    return stale


def _status_rows(rows: list[tuple[str, object, str]]) -> None:
    st.dataframe(
        pd.DataFrame(rows, columns=("Field", "Value", "Units / meaning")),
        hide_index=True,
        width="stretch",
        column_config={
            "Field": st.column_config.TextColumn(width="medium"),
            "Value": st.column_config.TextColumn(width="medium"),
            "Units / meaning": st.column_config.TextColumn(width="large"),
        },
    )


def _composition_table(result: TwoPhaseFlashResult) -> None:
    rows: dict[str, tuple[float, ...]] = {
        "Feed": tuple(
            100.0 * item.mole_fraction for item in result.feed_mixture.components
        )
    }
    if result.liquid_phase is not None:
        rows["Liquid"] = tuple(
            100.0 * value for value in result.liquid_phase.composition
        )
    if result.vapor_phase is not None:
        rows["Vapor"] = tuple(100.0 * value for value in result.vapor_phase.composition)
    st.dataframe(
        pd.DataFrame(rows, index=COMPONENT_NAMES).T,
        width="stretch",
        column_config={
            name: st.column_config.NumberColumn(name, format="%.6g mol %")
            for name in COMPONENT_NAMES
        },
    )


def _flash_details(result: TwoPhaseFlashResult) -> None:
    view = adapt_flash_result(result)
    _status_rows(
        [
            ("Solver status", status_text(view.convergence_status), "Public status"),
            (
                "Converged",
                str(_value(view.convergence_status) == "converged"),
                "Boolean evidence",
            ),
            (
                "Termination / failure",
                view.failure_reason or "None reported",
                "Verbatim public reason",
            ),
            (
                "Iterations",
                str(view.iteration_count),
                "Successive-substitution iterations",
            ),
            (
                "Single-phase root",
                _full_precision(view.single_phase_z),
                "Z, dimensionless",
            ),
        ]
    )
    component_rows: list[dict[str, object]] = []
    for index, name in enumerate(COMPONENT_NAMES):
        component_rows.append(
            {
                "Component": name,
                "K value": _full_precision(
                    None if view.final_k_values is None else view.final_k_values[index]
                ),
                "Equilibrium residual": _full_precision(
                    view.equilibrium_residuals[index]
                    if index < len(view.equilibrium_residuals)
                    else None
                ),
                "Material-balance residual": _full_precision(
                    view.material_balance_residuals[index]
                    if index < len(view.material_balance_residuals)
                    else None
                ),
                "Liquid fugacity coefficient": _full_precision(
                    None
                    if result.liquid_phase is None
                    else result.liquid_phase.component_fugacity_coefficients[index]
                ),
                "Vapor fugacity coefficient": _full_precision(
                    None
                    if result.vapor_phase is None
                    else result.vapor_phase.component_fugacity_coefficients[index]
                ),
            }
        )
    st.dataframe(
        pd.DataFrame(component_rows),
        hide_index=True,
        width="stretch",
    )
    phase_rows = []
    for name, phase in (("Liquid", result.liquid_phase), ("Vapor", result.vapor_phase)):
        if phase is not None:
            phase_rows.append(
                {
                    "Phase": name,
                    "Selected Z": phase.selected_compressibility_factor,
                    "Mechanical class": _value(phase.mechanical_classification),
                    "Root policy": _value(phase.root_selection.trial_kind),
                    "Candidate roots": ", ".join(
                        repr(float(root.compressibility_factor))
                        for root in phase.root_selection.candidates
                    ),
                }
            )
    if phase_rows:
        st.dataframe(pd.DataFrame(phase_rows), hide_index=True, width="stretch")


def render_overview(inputs: ScientificInputs | None) -> None:
    st.header("Overview")
    raw = get_result(session(), "flash")
    if raw is None:
        st.info(
            "Submit valid fluid inputs with RUN FLASH to create a production result.",
            icon=":material/info:",
        )
        return
    result = cast(TwoPhaseFlashResult, raw)
    view = adapt_flash_result(result)
    flash_stale = _stale("flash", inputs)
    with st.container(border=True):
        st.subheader(status_text(view.phase_state))
        presentation = flash_presentation_kind(result)
        if presentation == "success":
            st.success(
                f"Solver status: {status_text(view.convergence_status)}",
                icon=":material/check_circle:",
            )
        elif presentation == "information":
            st.info(
                "Phase stability is conclusive. No two-phase split was required. "
                f"Selected single-phase Z = {_full_precision(view.single_phase_z)}.",
                icon=":material/info:",
            )
        else:
            st.error(
                f"Solver status: {status_text(view.convergence_status)} · "
                f"{view.failure_reason or 'No failure reason supplied'}",
                icon=":material/error:",
            )
    state_columns = st.columns(4, vertical_alignment="center")
    state_columns[0].metric("Temperature", f"{view.temperature_k:.6g} K")
    state_columns[1].metric("Pressure", f"{view.pressure_pa / PA_PER_MPA:.6g} MPa")
    state_columns[2].metric("Model", "Peng-Robinson")
    state_columns[3].metric("Interactions", "kij = 0")
    phase_columns = st.columns(4, vertical_alignment="center")
    phase_columns[0].metric("Vapor fraction", _optional(view.vapor_fraction))
    phase_columns[1].metric("Liquid fraction", _optional(view.liquid_fraction))
    phase_columns[2].metric("Vapor Z", _optional(view.vapor_z))
    phase_columns[3].metric("Liquid Z", _optional(view.liquid_z))
    if view.vapor_fraction is not None and view.liquid_fraction is not None:
        st.caption("Engineering phase split · liquid / vapor")
        phase_split_bar(view.vapor_fraction, view.liquid_fraction)
    if view.single_phase_z is not None:
        st.info(
            f"Single-phase selected root: Z = {view.single_phase_z:.6g}. "
            "It is not relabelled as a liquid or vapor root."
        )
    st.subheader("Source-provided phase compositions")
    _composition_table(result)
    envelope = cast(PhaseEnvelopeResult | None, get_result(session(), "envelope"))
    if result_is_stale(session(), "envelope", inputs):
        envelope = None
    st.subheader("Operating point")
    st.write(
        location_relative_to_envelope(envelope, view.temperature_k, view.pressure_pa)
    )
    if envelope is None:
        st.caption("Calculate a phase envelope to establish this relationship.")
    if inputs is not None:
        envelope_export = cast(
            PhaseEnvelopeResult | None, get_result(session(), "envelope")
        )
        if result_is_stale(session(), "envelope", inputs):
            envelope_export = None
        critical_export = cast(
            MixtureCriticalPointResult | None, get_result(session(), "critical")
        )
        if result_is_stale(session(), "critical", inputs):
            critical_export = None
        document = build_export_document(
            inputs,
            flash_result=None if flash_stale else result,
            envelope_result=envelope_export,
            critical_result=critical_export,
        )
        st.subheader("Export current case")
        with st.container(horizontal=True):
            st.download_button(
                "Download CSV",
                data=export_csv_bytes(document),
                file_name="pvt-current-case.csv",
                mime="text/csv;charset=utf-8",
                key="download_current_case_csv",
                on_click="ignore",
                width="content",
                icon=":material/download:",
            )
            st.download_button(
                "Download JSON",
                data=export_json_bytes(document),
                file_name="pvt-current-case.json",
                mime="application/json",
                key="download_current_case_json",
                on_click="ignore",
                width="content",
                icon=":material/download:",
            )
    details = st.expander("Technical details", icon=":material/table_view:")
    with details:
        _flash_details(result)
        if st.toggle("Show advanced public-object inspection", key="overview_raw"):
            st.json(asdict(result))


@st.cache_data(show_spinner=False, max_entries=8)
def _calculate_envelope(inputs: ScientificInputs) -> PhaseEnvelopeResult:
    start_temperature_k = inputs.temperature_k - 30.0
    settings = EnvelopeContinuationSettings(
        target_temperature_k=inputs.temperature_k + 30.0,
        initial_temperature_step_k=5.0,
        maximum_points=15,
    )
    return calculate_phase_envelope(
        inputs.mixture(), settings, settings, start_temperature_k, start_temperature_k
    )


def render_phase_envelope(inputs: ScientificInputs | None) -> None:
    st.header("Phase envelope")
    st.caption(
        "Independent bounded bubble and dew continuation · "
        "turning points are not critical points"
    )
    if st.button(
        "RUN PHASE ENVELOPE",
        type="primary",
        width="stretch",
        disabled=inputs is None,
        icon=":material/play_arrow:",
    ):
        assert inputs is not None
        with st.status("Tracing bubble and dew branches…", expanded=True) as status:
            status.write(
                "Cold-starting below the operating point, then continuing both "
                "branches through its temperature."
            )
            status.write("Typical first run: about 20–30 seconds.")
            status.caption("An unchanged submitted case reuses the bounded UI cache.")
            try:
                result = _calculate_envelope(inputs)
                store_result(session(), "envelope", result, inputs)
                status.update(label="Envelope trace complete", state="complete")
            except (ValueError, ArithmeticError) as error:
                status.update(label="Envelope trace failed", state="error")
                st.error(f"Phase-envelope calculation could not start: {error}")
    _action_requirement(inputs)
    raw = get_result(session(), "envelope")
    if raw is None:
        st.info("No calculated envelope is available.", icon=":material/info:")
        return
    result = cast(PhaseEnvelopeResult, raw)
    _stale("envelope", inputs)
    critical = cast(
        MixtureCriticalPointResult | None, get_result(session(), "critical")
    )
    if result_is_stale(session(), "critical", inputs):
        critical = None
    _wide_chart(
        _annotate_missing_envelope_branches(
            plot_phase_envelope(
                result,
                pressure_unit=PressureUnit.MPA,
                critical_point=critical,
                metadata={"model": "Peng-Robinson EOS; kij=0"},
            ),
            result,
        ),
        key="phase_envelope_chart",
    )
    _status_rows(
        [
            (
                "Bubble branch",
                status_text(result.bubble_branch.termination_reason),
                f"{len(result.bubble_branch.points)} accepted; "
                f"{len(result.bubble_branch.rejected_attempts)} rejected; "
                f"{result.bubble_branch.termination_message}",
            ),
            (
                "Dew branch",
                status_text(result.dew_branch.termination_reason),
                f"{len(result.dew_branch.points)} accepted; "
                f"{len(result.dew_branch.rejected_attempts)} rejected; "
                f"{result.dew_branch.termination_message}",
            ),
        ]
    )
    if inputs is not None:
        st.info(
            "Operating point: "
            + location_relative_to_envelope(
                result, inputs.temperature_k, inputs.pressure_pa
            )
        )
    st.caption(
        "Pressure or temperature turning indicators are continuation geometry, "
        "not certified critical points."
    )
    component = st.selectbox("Composition component", COMPONENT_NAMES)
    branch = cast(
        Literal["bubble", "dew"],
        st.segmented_control("Composition branch", ("bubble", "dew"), default="bubble"),
    )
    if st.button("SHOW PHASE COMPOSITIONS", icon=":material/show_chart:"):
        try:
            _wide_chart(
                plot_phase_compositions(
                    result,
                    branch=branch,
                    component_index=COMPONENT_NAMES.index(component),
                    display=CompositionDisplay.MOL_PERCENT,
                    pressure_unit=PressureUnit.MPA,
                ),
                key="phase_compositions_chart",
            )
        except ValueError as error:
            st.info(f"Phase-composition figure unavailable: {error}")


@st.cache_data(show_spinner=False, max_entries=8)
def _calculate_critical(inputs: ScientificInputs) -> MixtureCriticalPointResult:
    return solve_mixture_critical_point(
        inputs.mixture(),
        inputs.temperature_k,
        inputs.pressure_pa,
        initialization_source="streamlit_user_conditions",
    )


@st.cache_data(show_spinner=False, max_entries=8)
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


def render_critical_point(inputs: ScientificInputs | None) -> None:
    st.header("Critical point")
    st.caption(
        "Certification requires solver convergence on both criticality conditions. "
        "A zero minimum stability eigenvalue alone identifies a spinodal condition, "
        "not a critical point."
    )
    with st.container(horizontal=True):
        run_solver = st.button(
            "RUN CRITICAL SOLVER",
            type="primary",
            disabled=inputs is None,
            icon=":material/play_arrow:",
        )
        run_map = st.button(
            "RUN CRITICALITY MAP",
            disabled=inputs is None,
            icon=":material/grid_on:",
        )
    _action_requirement(inputs)
    if run_solver:
        assert inputs is not None
        with st.status("Solving production critical conditions…") as status:
            try:
                store_result(session(), "critical", _calculate_critical(inputs), inputs)
                status.update(label="Critical solver complete", state="complete")
            except (ValueError, ArithmeticError) as error:
                status.update(label="Critical solver failed", state="error")
                st.error(f"Critical solver could not start: {error}")
    if run_map:
        assert inputs is not None
        with st.status("Evaluating bounded diagnostic map…") as status:
            try:
                store_result(
                    session(), "critical_scan", _calculate_scan(inputs), inputs
                )
                status.update(label="Criticality map complete", state="complete")
            except (ValueError, ArithmeticError) as error:
                status.update(label="Criticality map failed", state="error")
                st.error(f"Criticality map could not be evaluated: {error}")
    raw = get_result(session(), "critical")
    if raw is None:
        st.info("No production critical-point solve has been requested.")
    else:
        result = cast(MixtureCriticalPointResult, raw)
        view = adapt_critical_result(result)
        _stale("critical", inputs)
        if view.certified:
            st.success("CERTIFIED CRITICAL POINT", icon=":material/verified:")
            certified = st.columns(2)
            certified[0].metric("Tc", f"{cast(float, view.temperature_k):.6g} K")
            certified[1].metric(
                "Pc", f"{cast(float, view.pressure_pa) / PA_PER_MPA:.6g} MPa"
            )
        else:
            st.error(
                f"NOT CERTIFIED — {view.termination_reason}",
                icon=":material/cancel:",
            )
        _status_rows(
            [
                ("Production status", status_text(view.status), "Public enum"),
                ("Termination", view.termination_reason, "Production reason"),
                ("Iterations", str(view.iterations), "Solver iterations"),
                (
                    "lambda_min",
                    _full_precision(result.lambda_min),
                    "Dimensionless critical residual",
                ),
                (
                    "C",
                    _full_precision(result.cubic_coefficient),
                    "Critical cubic coefficient",
                ),
                (
                    "Scaled residual",
                    _full_precision(result.scaled_residual_norm),
                    "Dimensionless",
                ),
                (
                    "Jacobian conditioning",
                    _full_precision(
                        result.jacobian_condition_history[-1]
                        if result.jacobian_condition_history
                        else None
                    ),
                    "Final recorded condition estimate",
                ),
                (
                    "Critical direction",
                    "Unavailable"
                    if result.critical_direction is None
                    else str(result.critical_direction),
                    "Composition tangent basis",
                ),
            ]
        )
        if st.toggle("Show critical solver figures", key="critical_figures"):
            if result.history:
                _wide_chart(
                    plot_critical_solver_convergence(result),
                    key="critical_convergence_chart",
                )
                _wide_chart(
                    plot_critical_solver_path(result), key="critical_path_chart"
                )
            if result.jacobian_condition_history:
                _wide_chart(
                    plot_critical_solver_conditioning(result),
                    key="critical_conditioning_chart",
                )
    scan_raw = get_result(session(), "critical_scan")
    if scan_raw is not None:
        _stale("critical_scan", inputs)
        overlay = cast(MixtureCriticalPointResult | None, raw)
        if result_is_stale(session(), "critical", inputs):
            overlay = None
        _wide_chart(
            plot_criticality_map(
                cast(CriticalPointScanResult, scan_raw),
                pressure_unit=PressureUnit.MPA,
                critical_point=overlay,
                metadata={"model": "Peng-Robinson EOS; kij=0"},
            ),
            key="criticality_map_chart",
        )


@st.cache_data(show_spinner=False, max_entries=2)
def _records() -> tuple[Any, ...]:
    return load_module17_records(ROOT)


def render_validation() -> None:
    st.header("Validation")
    st.info(
        "Existing experimental dataset: 40 methane/ethane and methane/propane "
        "VLE states. "
        "Production predictions use kij = 0 with no fitted interaction parameters. "
        "Figures report only fields present in the protected Module 17 records."
    )
    direction = cast(
        Literal["bubble", "dew"],
        st.segmented_control(
            "Prediction direction", ("bubble", "dew"), default="bubble"
        ),
    )
    if st.button(
        "GENERATE VALIDATION FIGURES",
        type="primary",
        icon=":material/analytics:",
    ):
        session()["validation_direction"] = direction
    requested = session().get("validation_direction")
    if requested is None:
        st.caption("Figures are generated only after the explicit action above.")
        return
    selected = cast(Literal["bubble", "dew"], requested)
    if selected != direction:
        st.warning(
            "Displayed figures are stale for the selected direction. Generate again."
        )
    records = _records()
    state_count, error_count, median_error, worst_error = (
        validation_pressure_error_summary(records, selected)
    )
    summary = st.columns(4)
    summary[0].metric("Module 17 states", str(state_count))
    summary[1].metric(f"{selected.capitalize()} error records", str(error_count))
    summary[2].metric("Median absolute pressure error", _optional(median_error) + "%")
    summary[3].metric("Worst absolute pressure error", _optional(worst_error) + "%")
    with st.status("Rendering Module 21 validation figures…") as status:
        figures = (
            plot_validation_pressure_parity(
                records, direction=selected, pressure_unit=PressureUnit.MPA
            ),
            plot_validation_pressure_error(records, direction=selected),
            plot_validation_status(records, direction=selected),
        )
        composition_error: str | None
        try:
            composition_figure = plot_validation_composition_parity(
                records,
                direction=selected,
                component_index=0,
                display=CompositionDisplay.MOL_PERCENT,
            )
        except (ValueError, IndexError) as error:
            composition_figure = None
            composition_error = str(error)
        else:
            composition_error = None
        status.update(label="Production validation figures ready", state="complete")
    _square_chart(figures[0], key="validation_pressure_parity")
    _wide_chart(figures[1], key="validation_pressure_error")
    _wide_chart(figures[2], key="validation_status")
    if composition_figure is not None:
        _square_chart(composition_figure, key="validation_composition_parity")
    elif composition_error is not None:
        st.info(f"Composition parity unavailable: {composition_error}")
    st.subheader("Retrospective nearest-root diagnostics")
    st.error(
        "NOT PRODUCTION PREDICTIONS — retrospective nearest-root diagnostics only.",
        icon=":material/warning:",
    )
    try:
        _wide_chart(
            plot_validation_retrospective_diagnostics(
                records, pressure_unit=PressureUnit.MPA
            ),
            key="validation_retrospective",
        )
    except ValueError as error:
        st.info(f"Retrospective diagnostics unavailable: {error}")
    st.caption("Signed relative pressure error = 100*(P_pred-P_exp)/P_exp.")


def render_diagnostics(inputs: ScientificInputs | None) -> None:
    st.header("Diagnostics")
    st.caption("Public engineering evidence; structured failures remain failures.")
    flash_raw = get_result(session(), "flash")
    envelope_raw = get_result(session(), "envelope")
    critical_raw = get_result(session(), "critical")
    if flash_raw is not None:
        result = cast(TwoPhaseFlashResult, flash_raw)
        _stale("flash", inputs)
        st.subheader("Flash and stability")
        _status_rows(
            [
                ("Phase", status_text(result.phase_state), "Public phase state"),
                (
                    "Solver status",
                    status_text(result.convergence_status),
                    "Public convergence status",
                ),
                (
                    "Termination / failure",
                    result.failure_reason or "None reported",
                    "Verbatim public reason",
                ),
                ("Iterations", str(len(result.iteration_history)), "Flash iterations"),
                (
                    "Stability",
                    status_text(result.phase_stability.status),
                    "Bounded stability result",
                ),
            ]
        )
        _flash_details(result)
        if result.diagnostics:
            st.dataframe(
                pd.DataFrame(
                    {
                        "Code": item.code,
                        "Severity": _value(item.severity),
                        "Category": _value(item.category),
                        "Message": item.message,
                        "Value": item.value,
                    }
                    for item in result.diagnostics
                ),
                hide_index=True,
                width="stretch",
            )
        if result.iteration_history:
            latest = result.iteration_history[-1]
            _status_rows(
                [
                    ("Latest iteration", str(latest.iteration), "Iteration index"),
                    (
                        "Maximum log-K residual",
                        _full_precision(latest.maximum_log_k_residual),
                        "Dimensionless",
                    ),
                    (
                        "Maximum equilibrium residual",
                        _full_precision(latest.maximum_fugacity_equilibrium_residual),
                        "Dimensionless",
                    ),
                    (
                        "Maximum material-balance residual",
                        _full_precision(
                            latest.phase_compositions.maximum_material_balance_residual
                        ),
                        "Mole fraction",
                    ),
                    (
                        "Rachford-Rice status",
                        status_text(latest.rachford_rice.status),
                        f"{latest.rachford_rice.iterations} iterations",
                    ),
                ]
            )
    if envelope_raw is not None:
        envelope = cast(PhaseEnvelopeResult, envelope_raw)
        _stale("envelope", inputs)
        st.subheader("Envelope continuation")
        _status_rows(
            [
                (
                    branch.branch_kind.value,
                    status_text(branch.termination_reason),
                    f"{len(branch.points)} accepted · "
                    f"{len(branch.rejected_attempts)} rejected · "
                    f"{branch.termination_message}",
                )
                for branch in (envelope.bubble_branch, envelope.dew_branch)
            ]
        )
        st.caption("Turning indicators are continuation geometry, not critical points.")
    if critical_raw is not None:
        critical = cast(MixtureCriticalPointResult, critical_raw)
        _stale("critical", inputs)
        st.subheader("Critical solver")
        _status_rows(
            [
                ("Status", status_text(critical.status), "Production status"),
                (
                    "Certified",
                    str(adapt_critical_result(critical).certified),
                    "Requires exact CONVERGED status",
                ),
                ("Termination", critical.termination_reason, "Production reason"),
                ("Iterations", str(critical.iterations), "Solver iterations"),
                (
                    "Accepted / rejected",
                    f"{critical.accepted_steps} / {critical.rejected_steps}",
                    "Line-search evidence",
                ),
                ("Function evaluations", str(critical.function_evaluations), "Count"),
            ]
        )
    if flash_raw is None and envelope_raw is None and critical_raw is None:
        st.info("Run a calculation to populate diagnostics.")
    if st.toggle("Show advanced raw public objects", key="diagnostics_raw"):
        if flash_raw is not None:
            st.json(asdict(cast(TwoPhaseFlashResult, flash_raw)))
        if envelope_raw is not None:
            st.json(asdict(cast(PhaseEnvelopeResult, envelope_raw)))
        if critical_raw is not None:
            st.json(asdict(cast(MixtureCriticalPointResult, critical_raw)))
