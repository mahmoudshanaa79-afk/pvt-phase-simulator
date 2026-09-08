"""Engineering page presentations over immutable public scientific results."""

from __future__ import annotations

import logging
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Final, Literal, cast

import pandas as pd  # type: ignore[import-untyped]
import plotly.graph_objects as go  # type: ignore[import-untyped]
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
from pvt_phase_simulator.plotting import (
    PressureUnit as PlotPressureUnit,
)
from pvt_phase_simulator_ui.adapters import (
    COMPONENT_NAMES,
    ScientificInputs,
    adapt_critical_result,
    adapt_flash_result,
    flash_presentation_kind,
    load_module17_records,
    location_relative_to_envelope,
    status_text,
    validation_pressure_error_summary,
)
from pvt_phase_simulator_ui.context import session, unit_preferences
from pvt_phase_simulator_ui.exports import (
    build_export_document,
    build_sweep_export_document,
    export_csv_bytes,
    export_json_bytes,
    export_sweep_csv_bytes,
)
from pvt_phase_simulator_ui.model_scope import ModelScope, load_model_scope
from pvt_phase_simulator_ui.reports import export_engineering_report_html
from pvt_phase_simulator_ui.state import (
    begin_result_attempt,
    get_result,
    get_result_action_failure,
    result_is_stale,
    store_result,
    store_result_action_failure,
    synchronize_sweep_inputs,
)
from pvt_phase_simulator_ui.styles import phase_split_bar
from pvt_phase_simulator_ui.sweeps import (
    DEFAULT_SWEEP_POINTS,
    MAX_SWEEP_POINTS,
    MIN_SWEEP_POINTS,
    SweepKind,
    SweepResult,
    SweepValidationError,
    run_sweep,
    validate_sweep_request,
)
from pvt_phase_simulator_ui.units import (
    DEFAULT_UNITS,
    UnitPreferences,
    pressure_from_pa,
    temperature_from_k,
)

ROOT = Path(__file__).resolve().parents[2]
LOGGER = logging.getLogger(__name__)

ENVELOPE_ACTION_FAILURE: Final = (
    "The phase-envelope calculation stopped unexpectedly and did not return a "
    "result. Any earlier envelope result was removed so it cannot be mistaken "
    "for the current calculation. Review the inputs and try again."
)
CRITICAL_ACTION_FAILURE: Final = (
    "The critical-point calculation stopped unexpectedly and did not return a "
    "result. Any earlier critical-point result was removed so it cannot be "
    "mistaken for the current calculation. Review the seed and try again."
)
CRITICAL_SCAN_ACTION_FAILURE: Final = (
    "The criticality map stopped unexpectedly and did not return a result. Any "
    "earlier map was removed so it cannot be mistaken for the current calculation. "
    "Review the inputs and try again."
)
SWEEP_ACTION_FAILURE: Final = (
    "The engineering sweep stopped unexpectedly and did not return a complete "
    "result. Any earlier sweep was removed so it cannot be mistaken for the "
    "current calculation. Review the bounds and try again."
)

_CRITICAL_TEMPERATURE_TEXT: Final = re.compile(
    r"(?P<label>(?:^|<br>)T=)"
    r"(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?) K"
)
_CRITICAL_PRESSURE_TEXT: Final = re.compile(
    r"(?P<label>(?:^|<br>)P=)"
    r"(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?) Pa"
)


def _display_temperature(value_k: float, units: UnitPreferences) -> float:
    return temperature_from_k(value_k, units.temperature)


def _display_pressure(value_pa: float, units: UnitPreferences) -> float:
    return pressure_from_pa(value_pa, units.pressure)


def _format_plot_hover_value(value: float) -> str:
    return f"{value:.12g}"


def _convert_critical_hover_text(text: str, units: UnitPreferences) -> str:
    def replace_temperature(match: re.Match[str]) -> str:
        value = _display_temperature(float(match.group("value")), units)
        return (
            f"{match.group('label')}{_format_plot_hover_value(value)} "
            f"{units.temperature.value}"
        )

    def replace_pressure(match: re.Match[str]) -> str:
        value = _display_pressure(float(match.group("value")), units)
        return (
            f"{match.group('label')}{_format_plot_hover_value(value)} "
            f"{units.pressure.value}"
        )

    text = _CRITICAL_TEMPERATURE_TEXT.sub(replace_temperature, text)
    return _CRITICAL_PRESSURE_TEXT.sub(replace_pressure, text)


def _convert_axis_values(values: Any, converter: Any) -> tuple[object, ...]:
    if values is None:
        return ()
    return tuple(None if value is None else converter(float(value)) for value in values)


def _presentation_figure(
    figure: go.Figure,
    units: UnitPreferences,
    *,
    x_quantity: Literal["temperature", "pressure"] | None = None,
    y_quantity: Literal["temperature", "pressure"] | None = None,
) -> go.Figure:
    """Convert a source figure's SI axes once at the presentation boundary."""

    converters = {
        "temperature": lambda value: _display_temperature(value, units),
        "pressure": lambda value: _display_pressure(value, units),
    }
    labels = {
        "temperature": f"Temperature ({units.temperature.value})",
        "pressure": f"Pressure ({units.pressure.value})",
    }
    for trace in figure.data:
        if x_quantity is not None and getattr(trace, "x", None) is not None:
            trace.x = _convert_axis_values(trace.x, converters[x_quantity])
        if y_quantity is not None and getattr(trace, "y", None) is not None:
            trace.y = _convert_axis_values(trace.y, converters[y_quantity])
        text = getattr(trace, "text", None)
        if getattr(trace, "name", None) == "Certified critical point":
            if isinstance(text, str):
                trace.text = _convert_critical_hover_text(text, units)
            elif text is not None:
                trace.text = tuple(
                    _convert_critical_hover_text(value, units)
                    if isinstance(value, str)
                    else value
                    for value in text
                )
        template = getattr(trace, "hovertemplate", None)
        if isinstance(template, str):
            trace.hovertemplate = template.replace(
                " K", f" {units.temperature.value}"
            ).replace(" Pa", f" {units.pressure.value}")
    if x_quantity is not None:
        figure.update_xaxes(title_text=labels[x_quantity])
    if y_quantity is not None:
        figure.update_yaxes(title_text=labels[y_quantity])
    return figure


def _value(item: object) -> str:
    return str(item.value if hasattr(item, "value") else item)


def _optional(value: float | None, digits: int = 6) -> str:
    return "Unavailable" if value is None else f"{value:.{digits}g}"


def _full_precision(value: float | None) -> str:
    return "Unavailable" if value is None else repr(float(value))


def _action_requirement(inputs: ScientificInputs | None) -> None:
    if inputs is None:
        st.caption(":material/lock: Submit RUN FLASH to enable this action.")


def _action_inputs(inputs: ScientificInputs | None) -> ScientificInputs | None:
    if inputs is None or get_result(session(), "flash") is None:
        return None
    if result_is_stale(session(), "flash", inputs):
        return None
    return inputs


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


def _show_action_failure(name: str) -> bool:
    message = get_result_action_failure(session(), name)
    if message is None:
        return False
    st.error(message, icon=":material/error:")
    return True


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


@st.cache_data(show_spinner=False, max_entries=1)
def _model_scope() -> ModelScope:
    return load_model_scope(ROOT)


def _doi_link(doi: str | None) -> str:
    if doi is None:
        return "DOI unavailable"
    return f"[DOI {doi}](https://doi.org/{doi})"


def _render_model_scope_panel() -> None:
    scope = _model_scope()
    units = unit_preferences()
    components = ", ".join(scope.verified_component_names)
    systems = " and ".join(scope.validation_system_names)
    temperature_min, temperature_max = (
        _display_temperature(value, units)
        for value in scope.validation_temperature_range_k
    )
    pressure_min, pressure_max = (
        _display_pressure(value, units) for value in scope.validation_pressure_range_pa
    )

    with st.container(border=True):
        st.subheader("Model and limitations", anchor="model-and-limitations")
        st.markdown(
            f"**Model.** {scope.eos_name} for {len(scope.verified_component_names)} "
            f"property-verified components: **{components}**. The active "
            "interaction policy is "
            f"`{scope.interaction_policy.value}`: every omitted off-diagonal "
            "binary interaction is **kij = 0**; no fitted interaction parameters "
            "are used."
        )
        st.markdown(
            "**Supported calculations.** Phase stability and isothermal flash; "
            "bubble/dew phase-envelope tracing; mixture critical-point solving and "
            "criticality scans; bounded pressure/temperature flash sweeps; and "
            "repository-backed validation figures, diagnostics, and exports."
        )
        st.markdown(
            f"**Validation scope.** The protected Module 17 artifact contains "
            f"**{scope.validation_state_count} experimental VLE states** for "
            f"**{systems}**, spanning {temperature_min:g}–{temperature_max:g} "
            f"{units.temperature.value} and {pressure_min:g}–{pressure_max:g} "
            f"{units.pressure.value} in the recorded states. This "
            "does not establish accuracy for other components, mixtures, or "
            "conditions."
        )
        st.markdown(
            "**Known limitations.** Envelope continuation is bounded and may return "
            "unavailable branches or structured terminations. Unavailable values "
            "remain unavailable and are never fabricated or interpolated. Only "
            "`CriticalPointStatus.CONVERGED` is a certified critical point. The "
            "application provides no reservoir depletion, CCE/CVD, separator "
            "trains, pseudocomponents or C7+, EOS tuning, kij fitting, new-component "
            "support, or arbitrary reservoir-fluid validation."
        )
        st.warning(
            "This is not a commercial PVT package and is not a substitute for "
            "engineering review.",
            icon=":material/warning:",
        )
        with st.expander("Recorded provenance", icon=":material/source:"):
            for source in scope.property_sources:
                st.markdown(
                    f"**Component-property source — {source.name}.** "
                    f"{source.citation} {_doi_link(source.doi)}"
                )
            st.markdown(
                f"**Experimental-validation source — "
                f"{scope.validation_source.name}.** "
                f"{scope.validation_source.citation} "
                f"{_doi_link(scope.validation_source.doi)}"
            )
            st.caption(
                "Validation evidence is read from "
                f"`{scope.validation_artifact.as_posix()}`; citations and component "
                "verification status are read from repository-owned provenance "
                "records."
            )


def render_overview(inputs: ScientificInputs | None) -> None:
    st.header("Overview")
    units = unit_preferences()
    _render_model_scope_panel()
    raw = get_result(session(), "flash")
    if raw is None:
        if not _show_action_failure("flash"):
            st.info(
                "Submit valid fluid inputs with RUN FLASH to create a production "
                "result.",
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
    state_columns[0].metric(
        "Temperature",
        f"{_display_temperature(view.temperature_k, units):.6g} "
        f"{units.temperature.value}",
    )
    state_columns[1].metric(
        "Pressure",
        f"{_display_pressure(view.pressure_pa, units):.6g} {units.pressure.value}",
    )
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
    if inputs is not None and not flash_stale:
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
        sweep_export = cast(SweepResult | None, get_result(session(), "sweep"))
        if result_is_stale(session(), "sweep", inputs):
            sweep_export = None
        document = build_export_document(
            inputs,
            flash_result=None if flash_stale else result,
            envelope_result=envelope_export,
            critical_result=critical_export,
            units=units,
        )
        sweep_document = (
            None
            if sweep_export is None
            else build_sweep_export_document(sweep_export, units)
        )
        st.subheader("Export current case")
        with st.container(horizontal=True):
            st.download_button(
                "Download report",
                data=export_engineering_report_html(
                    document,
                    scope=_model_scope(),
                    sweep_document=sweep_document,
                ),
                file_name="openphase-engineering-report.html",
                mime="text/html;charset=utf-8",
                key="download_engineering_report",
                on_click="ignore",
                width="content",
                icon=":material/description:",
            )
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
    elif flash_stale:
        st.caption(
            ":material/lock: Downloads are unavailable until RUN FLASH recalculates "
            "the changed inputs."
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
    units = unit_preferences()
    st.caption(
        "Independent bounded bubble and dew continuation · "
        "turning points are not critical points"
    )
    action_inputs = _action_inputs(inputs)
    if st.button(
        "RUN PHASE ENVELOPE",
        type="primary",
        width="stretch",
        disabled=action_inputs is None,
        icon=":material/play_arrow:",
    ):
        assert action_inputs is not None
        begin_result_attempt(session(), "envelope")
        with st.status("Tracing bubble and dew branches…", expanded=True) as status:
            status.write(
                "Cold-starting below the operating point, then continuing both "
                "branches through its temperature."
            )
            status.write("Typical first run: about 20–30 seconds.")
            status.caption("An unchanged submitted case reuses the bounded UI cache.")
            try:
                result = _calculate_envelope(action_inputs)
                store_result(session(), "envelope", result, action_inputs)
                status.update(label="Envelope trace complete", state="complete")
            except Exception:  # noqa: BLE001 - preserve a safe application boundary
                LOGGER.exception("Unexpected failure in the phase-envelope action")
                store_result_action_failure(
                    session(), "envelope", ENVELOPE_ACTION_FAILURE
                )
                status.update(label="Envelope trace failed", state="error")
    _action_requirement(action_inputs)
    raw = get_result(session(), "envelope")
    if raw is None:
        if not _show_action_failure("envelope"):
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
            _presentation_figure(
                plot_phase_envelope(
                    result,
                    pressure_unit=PlotPressureUnit.PA,
                    critical_point=critical,
                    metadata={"model": "Peng-Robinson EOS; kij=0"},
                ),
                units,
                x_quantity="temperature",
                y_quantity="pressure",
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
                _presentation_figure(
                    plot_phase_compositions(
                        result,
                        branch=branch,
                        component_index=COMPONENT_NAMES.index(component),
                        display=CompositionDisplay.MOL_PERCENT,
                        pressure_unit=PlotPressureUnit.PA,
                    ),
                    units,
                    x_quantity="temperature",
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
    units = unit_preferences()
    st.caption(
        "Certification requires solver convergence on both criticality conditions. "
        "A zero minimum stability eigenvalue alone identifies a spinodal condition, "
        "not a critical point."
    )
    action_inputs = _action_inputs(inputs)
    with st.container(horizontal=True):
        run_solver = st.button(
            "RUN CRITICAL SOLVER",
            type="primary",
            disabled=action_inputs is None,
            icon=":material/play_arrow:",
        )
        run_map = st.button(
            "RUN CRITICALITY MAP",
            disabled=action_inputs is None,
            icon=":material/grid_on:",
        )
    _action_requirement(action_inputs)
    if run_solver:
        assert action_inputs is not None
        begin_result_attempt(session(), "critical")
        with st.status("Solving production critical conditions…") as status:
            try:
                store_result(
                    session(),
                    "critical",
                    _calculate_critical(action_inputs),
                    action_inputs,
                )
                status.update(label="Critical solver complete", state="complete")
            except Exception:  # noqa: BLE001 - preserve a safe application boundary
                LOGGER.exception("Unexpected failure in the critical-point action")
                store_result_action_failure(
                    session(), "critical", CRITICAL_ACTION_FAILURE
                )
                status.update(label="Critical solver failed", state="error")
    if run_map:
        assert action_inputs is not None
        begin_result_attempt(session(), "critical_scan")
        with st.status("Evaluating bounded diagnostic map…") as status:
            try:
                store_result(
                    session(),
                    "critical_scan",
                    _calculate_scan(action_inputs),
                    action_inputs,
                )
                status.update(label="Criticality map complete", state="complete")
            except Exception:  # noqa: BLE001 - preserve a safe application boundary
                LOGGER.exception("Unexpected failure in the criticality-map action")
                store_result_action_failure(
                    session(), "critical_scan", CRITICAL_SCAN_ACTION_FAILURE
                )
                status.update(label="Criticality map failed", state="error")
    raw = get_result(session(), "critical")
    if raw is None:
        if not _show_action_failure("critical"):
            st.info("No production critical-point solve has been requested.")
    else:
        result = cast(MixtureCriticalPointResult, raw)
        view = adapt_critical_result(result)
        _stale("critical", inputs)
        if view.certified:
            st.success("CERTIFIED CRITICAL POINT", icon=":material/verified:")
            certified = st.columns(2)
            certified[0].metric(
                "Tc",
                f"{_display_temperature(cast(float, view.temperature_k), units):.6g} "
                f"{units.temperature.value}",
            )
            certified[1].metric(
                "Pc",
                f"{_display_pressure(cast(float, view.pressure_pa), units):.6g} "
                f"{units.pressure.value}",
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
                    _presentation_figure(
                        plot_critical_solver_path(
                            result, pressure_unit=PlotPressureUnit.PA
                        ),
                        units,
                        x_quantity="temperature",
                        y_quantity="pressure",
                    ),
                    key="critical_path_chart",
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
            _presentation_figure(
                plot_criticality_map(
                    cast(CriticalPointScanResult, scan_raw),
                    pressure_unit=PlotPressureUnit.PA,
                    critical_point=overlay,
                    metadata={"model": "Peng-Robinson EOS; kij=0"},
                ),
                units,
                x_quantity="temperature",
                y_quantity="pressure",
            ),
            key="criticality_map_chart",
        )
    else:
        _show_action_failure("critical_scan")


@st.cache_data(show_spinner=False, max_entries=2)
def _records() -> tuple[Any, ...]:
    return load_module17_records(ROOT)


def render_validation() -> None:
    st.header("Validation")
    units = unit_preferences()
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
            _presentation_figure(
                plot_validation_pressure_parity(
                    records,
                    direction=selected,
                    pressure_unit=PlotPressureUnit.PA,
                ),
                units,
                x_quantity="pressure",
                y_quantity="pressure",
            ),
            _presentation_figure(
                plot_validation_pressure_error(records, direction=selected),
                units,
                x_quantity="temperature",
            ),
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
            _presentation_figure(
                plot_validation_retrospective_diagnostics(
                    records, pressure_unit=PlotPressureUnit.PA
                ),
                units,
                x_quantity="pressure",
                y_quantity="pressure",
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


SWEEP_TABLE_COLUMNS: Final = (
    "Point",
    "Status",
    "Temperature (K)",
    "Pressure (MPa)",
    "Phase",
    "Convergence",
    "Stability",
    "Vapor fraction",
    "Liquid fraction",
    "Liquid Z",
    "Vapor Z",
    "Single-phase Z",
    "Iterations",
)


def _rounded(value: float | None, digits: int) -> float | str:
    """Round for reading. Exports keep full precision; this display does not."""

    return "—" if value is None else round(float(value), digits)


def _sweep_table(
    result: SweepResult, units: UnitPreferences = DEFAULT_UNITS
) -> pd.DataFrame:
    temperature_column = f"Temperature ({units.temperature.value})"
    pressure_column = f"Pressure ({units.pressure.value})"
    columns = list(SWEEP_TABLE_COLUMNS)
    columns[2] = temperature_column
    columns[3] = pressure_column
    rows = []
    for point in result.points:
        rows.append(
            {
                "Point": point.index + 1,
                "Status": "FAILED" if point.status == "failed" else "Calculated",
                temperature_column: _rounded(
                    _display_temperature(point.temperature_k, units), 4
                ),
                pressure_column: _rounded(
                    _display_pressure(point.pressure_pa, units), 5
                ),
                "Phase": point.phase_state or "—",
                "Convergence": point.convergence_status or "—",
                "Stability": point.stability_status or "—",
                "Vapor fraction": _rounded(point.vapor_fraction, 5),
                "Liquid fraction": _rounded(point.liquid_fraction, 5),
                "Liquid Z": _rounded(point.liquid_z, 5),
                "Vapor Z": _rounded(point.vapor_z, 5),
                "Single-phase Z": _rounded(point.single_phase_z, 5),
                "Iterations": (
                    "—" if point.iteration_count is None else point.iteration_count
                ),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _sweep_series(
    result: SweepResult,
    attribute: str,
    units: UnitPreferences = DEFAULT_UNITS,
) -> tuple[list[float], list[float | None]]:
    """Return every abscissa, with ``None`` wherever the quantity is absent.

    Dropping absent points would hand Plotly a contiguous array and it would
    draw a straight segment from the last good point to the next one, silently
    interpolating across a failed or unavailable calculation. Keeping the
    abscissa and emitting ``None`` is what makes ``connectgaps=False`` break the
    line exactly where the science stops.
    """

    x: list[float] = []
    y: list[float | None] = []
    for point in result.points:
        value = (
            _display_pressure(point.pressure_pa, units)
            if result.request.kind == "pressure"
            else _display_temperature(point.temperature_k, units)
        )
        x.append(value)
        if point.status == "failed":
            y.append(None)
            continue
        quantity = getattr(point, attribute)
        y.append(None if quantity is None else float(quantity))
    return x, y


def _sweep_failure_marks(
    result: SweepResult, units: UnitPreferences = DEFAULT_UNITS
) -> list[float]:
    return [
        (
            _display_pressure(point.pressure_pa, units)
            if result.request.kind == "pressure"
            else _display_temperature(point.temperature_k, units)
        )
        for point in result.points
        if point.status == "failed"
    ]


def _sweep_axis_title(result: SweepResult, units: UnitPreferences) -> str:
    unit = units.pressure if result.request.kind == "pressure" else units.temperature
    return f"{result.request.kind.capitalize()} ({unit.value})"


def _mark_failed_points(
    figure: go.Figure, result: SweepResult, units: UnitPreferences
) -> go.Figure:
    """Draw failed abscissae explicitly so a gap is never read as smooth."""

    failures = _sweep_failure_marks(result, units)
    for index, value in enumerate(failures):
        figure.add_vline(
            x=value,
            line_width=1,
            line_dash="dot",
            line_color="#B3261E",
            annotation_text="failed" if index == 0 else None,
            annotation_position="top",
        )
    return figure


def _vapor_fraction_figure(
    result: SweepResult, units: UnitPreferences = DEFAULT_UNITS
) -> go.Figure:
    x, y = _sweep_series(result, "vapor_fraction", units)
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=x,
            y=y,
            mode="lines+markers",
            name="Vapor fraction",
            connectgaps=False,
        )
    )
    figure.update_layout(
        title="Vapor fraction",
        xaxis_title=_sweep_axis_title(result, units),
        yaxis_title="Vapor fraction (-)",
    )
    return _mark_failed_points(figure, result, units)


def _z_factor_figure(
    result: SweepResult, units: UnitPreferences = DEFAULT_UNITS
) -> go.Figure:
    figure = go.Figure()
    for attribute, label in (
        ("liquid_z", "Liquid Z"),
        ("vapor_z", "Vapor Z"),
        ("single_phase_z", "Single-phase Z"),
    ):
        x, y = _sweep_series(result, attribute, units)
        if all(value is None for value in y):
            continue
        figure.add_trace(
            go.Scatter(x=x, y=y, mode="lines+markers", name=label, connectgaps=False)
        )
    figure.update_layout(
        title="Compressibility factors",
        xaxis_title=_sweep_axis_title(result, units),
        yaxis_title="Z (-)",
    )
    return _mark_failed_points(figure, result, units)


def _sweep_controls(
    inputs: ScientificInputs, units: UnitPreferences
) -> tuple[SweepKind, float, float, int]:
    """Collect sweep bounds; the fixed variable comes from the submitted case."""

    synchronize_sweep_inputs(session())
    kind = cast(
        SweepKind,
        st.segmented_control(
            "Swept variable",
            options=["pressure", "temperature"],
            format_func=lambda value: value.capitalize(),
            key="sweep_kind",
            on_change=synchronize_sweep_inputs,
            args=(session(),),
        )
        or "pressure",
    )
    if kind == "pressure":
        st.caption(
            f"Pressure is swept at the submitted temperature of "
            f"{_display_temperature(inputs.temperature_k, units):g} "
            f"{units.temperature.value}."
        )
        label_start = f"Start pressure ({units.pressure.value})"
        label_end = f"End pressure ({units.pressure.value})"
    else:
        st.caption(
            f"Temperature is swept at the submitted pressure of "
            f"{_display_pressure(inputs.pressure_pa, units):g} "
            f"{units.pressure.value}."
        )
        label_start = f"Start temperature ({units.temperature.value})"
        label_end = f"End temperature ({units.temperature.value})"

    with st.container(horizontal=True):
        start = st.number_input(
            label_start,
            step=1.0,
            key="sweep_start_value",
        )
        end = st.number_input(
            label_end,
            step=1.0,
            key="sweep_end_value",
        )
        points = st.number_input(
            "Points",
            min_value=MIN_SWEEP_POINTS,
            max_value=MAX_SWEEP_POINTS,
            step=1,
            key="sweep_points_value",
        )
    return kind, float(start), float(end), int(points)


def render_engineering_sweeps(inputs: ScientificInputs | None) -> None:
    """Bounded sweeps that call the existing verified flash API at every point."""

    st.header("Engineering sweeps")
    units = unit_preferences()
    st.caption(
        "Every point is one call into the existing verified flash and stability "
        "API. A point that fails stays reported as FAILED and is never "
        "interpolated away."
    )

    action_inputs = _action_inputs(inputs)
    if inputs is None:
        _action_requirement(inputs)
    elif action_inputs is None:
        st.caption(
            ":material/lock: Submit RUN FLASH for the current inputs to enable sweeps."
        )

    kind, start, end, points = (
        _sweep_controls(inputs, units)
        if inputs
        else (
            "pressure",
            1.0,
            20.0,
            DEFAULT_SWEEP_POINTS,
        )
    )

    run = st.button(
        "RUN SWEEP",
        type="primary",
        icon=":material/play_arrow:",
        disabled=action_inputs is None,
        key="run_sweep",
    )

    if run and action_inputs is not None:
        fixed = (
            _display_temperature(action_inputs.temperature_k, units)
            if kind == "pressure"
            else _display_pressure(action_inputs.pressure_pa, units)
        )
        try:
            request = validate_sweep_request(
                kind,
                action_inputs.composition_mol_percent,
                fixed_value=fixed,
                start=start,
                end=end,
                points=points,
                temperature_unit=units.temperature,
                pressure_unit=units.pressure,
            )
        except SweepValidationError as error:
            st.error(f"Submission unavailable: {error}")
        else:
            begin_result_attempt(session(), "sweep")
            progress = st.progress(0.0, text="Starting sweep…")

            def _advance(done: int, total: int) -> None:
                progress.progress(
                    done / total,
                    text=f"Evaluated {done} of {total} points…",
                )

            try:
                with st.spinner("Running the sweep…"):
                    result = run_sweep(request, progress=_advance)
            except Exception:  # noqa: BLE001 - preserve a safe application boundary
                LOGGER.exception("Unexpected failure in the engineering-sweep action")
                store_result_action_failure(session(), "sweep", SWEEP_ACTION_FAILURE)
            else:
                store_result(session(), "sweep", result, action_inputs)
            finally:
                progress.empty()

    sweep = cast(SweepResult | None, get_result(session(), "sweep"))
    if sweep is None:
        if not _show_action_failure("sweep"):
            st.info("No sweep has been calculated yet.")
        return
    if _stale("sweep", inputs):
        return

    failed = sweep.failed_count
    with st.container(horizontal=True):
        st.metric("Points requested", sweep.request.points)
        st.metric("Calculated", sweep.calculated_count)
        st.metric("Failed", failed)
    if failed:
        st.warning(
            f"{failed} of {sweep.request.points} points failed and are reported "
            "as FAILED. Each one breaks the plotted line instead of being "
            "interpolated across."
        )

    _wide_chart(_vapor_fraction_figure(sweep, units), key="sweep_vapor_fraction")
    _wide_chart(_z_factor_figure(sweep, units), key="sweep_z_factors")

    st.subheader("Phase-state results")
    st.dataframe(_sweep_table(sweep, units), width="stretch", hide_index=True)
    st.caption(
        "Displayed values are rounded for reading. Exports carry full precision."
    )

    document = build_sweep_export_document(sweep, units)
    st.subheader("Export sweep")
    with st.container(horizontal=True):
        st.download_button(
            "Download CSV",
            data=export_sweep_csv_bytes(sweep, units),
            file_name="pvt-engineering-sweep.csv",
            mime="text/csv;charset=utf-8",
            key="download_sweep_csv",
            on_click="ignore",
            width="content",
            icon=":material/download:",
        )
        st.download_button(
            "Download JSON",
            data=export_json_bytes(document),
            file_name="pvt-engineering-sweep.json",
            mime="application/json",
            key="download_sweep_json",
            on_click="ignore",
            width="content",
            icon=":material/download:",
        )
