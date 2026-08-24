"""Pure Plotly visualizations for structured phase-behavior results.

Module 21 converts existing immutable solver and validation results into
scientific figures.  Rendering never calls a thermodynamic solver, writes a
file, changes a global Plotly template, or mutates caller-owned data.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from pathlib import Path
from typing import Final, Literal, overload

import numpy as np
import pandas as pd  # type: ignore[import-untyped]
import plotly.graph_objects as go  # type: ignore[import-untyped]

from pvt_phase_simulator.eos.critical_point import (
    CriticalPointScanResult,
    CriticalPointStatus,
    MixtureCriticalPointResult,
)
from pvt_phase_simulator.eos.phase_envelope import (
    EnvelopeBranchKind,
    EnvelopeTerminationReason,
    PhaseEnvelopeResult,
)
from pvt_phase_simulator.eos.pseudo_arclength import PseudoArclengthBranchResult
from pvt_phase_simulator.experimental_validation import ExperimentalVLEValidationResult

BLUE: Final = "#176B87"
ORANGE: Final = "#C75B12"
GOLD: Final = "#9A7300"
CHARCOAL: Final = "#263238"
GREY: Final = "#6B7280"
LIGHT_GREY: Final = "#D1D5DB"


class PressureUnit(StrEnum):
    """Supported display units for pressure values stored internally in Pa."""

    PA = "Pa"
    KPA = "kPa"
    MPA = "MPa"
    BAR = "bar"


class CompositionDisplay(StrEnum):
    """Supported mole-fraction display conventions."""

    FRACTION = "fraction"
    MOL_PERCENT = "mol %"


PRESSURE_DIVISORS: Final[dict[PressureUnit, float]] = {
    PressureUnit.PA: 1.0,
    PressureUnit.KPA: 1.0e3,
    PressureUnit.MPA: 1.0e6,
    PressureUnit.BAR: 1.0e5,
}


def _pressure_unit(unit: PressureUnit | str) -> PressureUnit:
    try:
        return unit if isinstance(unit, PressureUnit) else PressureUnit(unit)
    except ValueError as error:
        raise ValueError("pressure unit must be Pa, kPa, MPa, or bar") from error


@overload
def convert_pressure(
    pressure_pa: float, unit: PressureUnit | str = PressureUnit.MPA
) -> float: ...


@overload
def convert_pressure(
    pressure_pa: Sequence[float], unit: PressureUnit | str = PressureUnit.MPA
) -> tuple[float, ...]: ...


@overload
def convert_pressure(
    pressure_pa: np.ndarray, unit: PressureUnit | str = PressureUnit.MPA
) -> np.ndarray: ...


def convert_pressure(
    pressure_pa: float | Sequence[float] | np.ndarray,
    unit: PressureUnit | str = PressureUnit.MPA,
) -> float | tuple[float, ...] | np.ndarray:
    """Convert finite SI pressure values for display without changing the input."""

    divisor = PRESSURE_DIVISORS[_pressure_unit(unit)]
    if isinstance(pressure_pa, np.ndarray):
        array_values = np.asarray(pressure_pa, dtype=float)
        if not np.all(np.isfinite(array_values)):
            raise ValueError("pressure values must be finite")
        return array_values / divisor
    if isinstance(pressure_pa, Sequence) and not isinstance(pressure_pa, str):
        sequence_values = tuple(float(value) for value in pressure_pa)
        if not all(isfinite(value) for value in sequence_values):
            raise ValueError("pressure values must be finite")
        return tuple(value / divisor for value in sequence_values)
    value = float(pressure_pa)
    if not isfinite(value):
        raise ValueError("pressure value must be finite")
    return value / divisor


def _composition_display(
    display: CompositionDisplay | str,
) -> CompositionDisplay:
    try:
        return (
            display
            if isinstance(display, CompositionDisplay)
            else CompositionDisplay(display)
        )
    except ValueError as error:
        raise ValueError("composition display must be fraction or mol %") from error


def _composition_values(
    values: Sequence[float], display: CompositionDisplay | str
) -> tuple[float, ...]:
    mode = _composition_display(display)
    materialized = tuple(float(value) for value in values)
    if not materialized or not all(isfinite(value) for value in materialized):
        raise ValueError("composition values must be nonempty and finite")
    if any(value < 0.0 or value > 1.0 for value in materialized):
        raise ValueError("composition values must be mole fractions in [0, 1]")
    factor = 100.0 if mode is CompositionDisplay.MOL_PERCENT else 1.0
    return tuple(value * factor for value in materialized)


def _composition_label(display: CompositionDisplay | str) -> str:
    return (
        "Composition (mol %)"
        if _composition_display(display) is CompositionDisplay.MOL_PERCENT
        else "Mole fraction"
    )


def _required_float(value: float | None, name: str) -> float:
    if value is None or not isfinite(value):
        raise ValueError(f"{name} must be available and finite")
    return value


def _component_value(
    composition: tuple[float, ...] | None, component_index: int
) -> float:
    if composition is None:
        raise ValueError("composition is unavailable")
    try:
        return composition[component_index]
    except IndexError as error:
        raise ValueError("component_index is outside the composition") from error


def _finite_pair(temperature_k: float, pressure_pa: float) -> None:
    if not all(
        isfinite(value) and value > 0.0 for value in (temperature_k, pressure_pa)
    ):
        raise ValueError("temperature and pressure must be positive finite values")


def _layout(fig: go.Figure, title: str, y_title: str) -> None:
    fig.update_layout(
        title=title,
        xaxis_title="Temperature (K)",
        yaxis_title=y_title,
        hovermode="closest",
        font={"size": 14, "color": CHARCOAL},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        margin={"l": 72, "r": 32, "t": 84, "b": 64},
    )


def _apply_metadata(fig: go.Figure, metadata: Mapping[str, str] | None) -> None:
    if metadata is not None:
        if any(
            not str(key).strip() or not str(value).strip()
            for key, value in metadata.items()
        ):
            raise ValueError("figure metadata keys and values must not be blank")
        fig.update_layout(meta=dict(metadata))


@dataclass(frozen=True, slots=True)
class PhaseBehaviorPoint:
    """Minimal immutable saturation point consumed by pure renderers."""

    temperature_k: float
    pressure_pa: float
    status: str = "converged"
    liquid_composition: tuple[float, ...] | None = None
    vapor_composition: tuple[float, ...] | None = None


@dataclass(frozen=True, slots=True)
class PhaseEnvelopePlotData:
    """Plot-ready bubble/dew series, separate from thermodynamic computation."""

    bubble_points: tuple[PhaseBehaviorPoint, ...]
    dew_points: tuple[PhaseBehaviorPoint, ...]
    component_names: tuple[str, ...] = ()
    composition: tuple[float, ...] = ()
    bubble_termination: str | None = None
    dew_termination: str | None = None


def phase_envelope_plot_data(result: PhaseEnvelopeResult) -> PhaseEnvelopePlotData:
    """Adapt an existing Module 9 result without recomputation."""

    def adapt_point(point: object, branch: EnvelopeBranchKind) -> PhaseBehaviorPoint:
        saturation = point.saturation_result  # type: ignore[attr-defined]
        if branch is EnvelopeBranchKind.BUBBLE:
            liquid = tuple(saturation.parent_composition)
            vapor = tuple(saturation.incipient_composition)
        else:
            liquid = tuple(saturation.incipient_composition)
            vapor = tuple(saturation.parent_composition)
        return PhaseBehaviorPoint(
            float(point.temperature_k),  # type: ignore[attr-defined]
            float(point.pressure_pa),  # type: ignore[attr-defined]
            str(point.status),  # type: ignore[attr-defined]
            liquid,
            vapor,
        )

    return PhaseEnvelopePlotData(
        tuple(
            adapt_point(point, EnvelopeBranchKind.BUBBLE)
            for point in result.bubble_branch.points
        ),
        tuple(
            adapt_point(point, EnvelopeBranchKind.DEW)
            for point in result.dew_branch.points
        ),
        tuple(item.component.name for item in result.feed_mixture.components),
        tuple(result.bubble_branch.feed_composition),
        result.bubble_branch.termination_reason.value,
        result.dew_branch.termination_reason.value,
    )


def _validated_phase_points(
    points: Sequence[PhaseBehaviorPoint], name: str
) -> tuple[PhaseBehaviorPoint, ...]:
    materialized = tuple(points)
    for point in materialized:
        _finite_pair(point.temperature_k, point.pressure_pa)
        if not point.status:
            raise ValueError(f"{name} point status must not be blank")
    return materialized


def _critical_hover(
    result: MixtureCriticalPointResult,
    unit: PressureUnit,
    model_label: str | None,
) -> str:
    pressure = convert_pressure(result.pressure_pa or 0.0, unit)
    composition = ", ".join(f"{value:.8g}" for value in result.composition)
    hover = (
        "Critical point"
        f"<br>T={result.temperature_k:.12g} K"
        f"<br>P={pressure:.12g} {unit.value}"
        f"<br>composition=({composition})"
        f"<br>lambda_min={result.lambda_min:.8g}"
        f"<br>C={result.cubic_coefficient:.8g}"
    )
    if model_label:
        hover += f"<br>model={model_label}"
    return hover


def _add_critical_point(
    fig: go.Figure,
    result: MixtureCriticalPointResult | None,
    unit: PressureUnit,
    model_label: str | None = None,
) -> None:
    if result is None or result.status is not CriticalPointStatus.CONVERGED:
        return
    if result.temperature_k is None or result.pressure_pa is None:
        raise ValueError("converged critical result must contain T and P")
    _finite_pair(result.temperature_k, result.pressure_pa)
    fig.add_trace(
        go.Scatter(
            x=(result.temperature_k,),
            y=(convert_pressure(result.pressure_pa, unit),),
            mode="markers",
            name="Certified critical point",
            marker={
                "symbol": "star",
                "size": 15,
                "color": GOLD,
                "line": {"color": CHARCOAL, "width": 1.5},
            },
            text=(_critical_hover(result, unit, model_label),),
            hovertemplate="%{text}<extra></extra>",
        )
    )


def _add_termination_marker(
    fig: go.Figure,
    points: tuple[PhaseBehaviorPoint, ...],
    branch: str,
    reason: str | None,
    unit: PressureUnit,
) -> None:
    supported = {
        EnvelopeTerminationReason.NEAR_CRITICAL.value: "Near-critical termination",
        EnvelopeTerminationReason.BRANCH_LOST.value: "Branch-lost termination",
    }
    if not points or reason not in supported:
        return
    last = points[-1]
    fig.add_trace(
        go.Scatter(
            x=(last.temperature_k,),
            y=(convert_pressure(last.pressure_pa, unit),),
            mode="markers",
            name=f"{branch} {supported[reason]}",
            marker={"symbol": "x-open", "size": 12, "color": CHARCOAL},
            hovertemplate=(
                f"{branch} {supported[reason]}"
                "<br>T=%{x:.8g} K<br>P=%{y:.8g} "
                f"{unit.value}<extra></extra>"
            ),
        )
    )


def plot_phase_envelope(
    data: PhaseEnvelopePlotData | PhaseEnvelopeResult,
    *,
    pressure_unit: PressureUnit | str = PressureUnit.MPA,
    critical_point: MixtureCriticalPointResult | None = None,
    show_termination_markers: bool = True,
    title: str | None = None,
    metadata: Mapping[str, str] | None = None,
) -> go.Figure:
    """Plot separate bubble/dew P-T branches from already computed data."""

    source = (
        phase_envelope_plot_data(data)
        if isinstance(data, PhaseEnvelopeResult)
        else data
    )
    bubble = _validated_phase_points(source.bubble_points, "bubble")
    dew = _validated_phase_points(source.dew_points, "dew")
    if not bubble and not dew:
        raise ValueError("phase envelope contains no plottable points")
    unit = _pressure_unit(pressure_unit)
    fig = go.Figure()
    for name, points, dash, symbol, color in (
        ("Bubble branch", bubble, "solid", "circle", BLUE),
        ("Dew branch", dew, "dash", "diamond", ORANGE),
    ):
        if not points:
            continue
        converged = tuple(point for point in points if point.status == "converged")
        unavailable = tuple(point for point in points if point.status != "converged")
        if converged:
            fig.add_trace(
                go.Scatter(
                    x=tuple(point.temperature_k for point in converged),
                    y=convert_pressure(
                        tuple(point.pressure_pa for point in converged), unit
                    ),
                    mode="lines+markers",
                    name=name,
                    line={"dash": dash, "width": 2.5, "color": color},
                    marker={"symbol": symbol, "size": 7, "color": color},
                    customdata=tuple((point.status,) for point in converged),
                    hovertemplate=(
                        f"{name}<br>T=%{{x:.8g}} K<br>P=%{{y:.8g}} {unit.value}"
                        "<br>status=%{customdata[0]}<extra></extra>"
                    ),
                )
            )
        if unavailable:
            fig.add_trace(
                go.Scatter(
                    x=tuple(point.temperature_k for point in unavailable),
                    y=convert_pressure(
                        tuple(point.pressure_pa for point in unavailable), unit
                    ),
                    mode="markers",
                    name=f"{name} unavailable/rejected",
                    marker={"symbol": "x-open", "size": 10, "color": GREY},
                    customdata=tuple((point.status,) for point in unavailable),
                    hovertemplate=(
                        f"{name}<br>T=%{{x:.8g}} K<br>P=%{{y:.8g}} {unit.value}"
                        "<br>status=%{customdata[0]}<extra>Not converged</extra>"
                    ),
                )
            )
    if show_termination_markers:
        _add_termination_marker(fig, bubble, "Bubble", source.bubble_termination, unit)
        _add_termination_marker(fig, dew, "Dew", source.dew_termination, unit)
    model_label = metadata.get("model") if metadata is not None else None
    _add_critical_point(fig, critical_point, unit, model_label)
    default_title = "Phase Envelope"
    if source.component_names and source.composition:
        names = "/".join(source.component_names)
        fractions = "/".join(f"{value:g}" for value in source.composition)
        default_title = f"Phase Envelope — {names} ({fractions})"
    _layout(fig, title or default_title, f"Pressure ({unit.value})")
    _apply_metadata(fig, metadata)
    return fig


def plot_phase_compositions(
    data: PhaseEnvelopePlotData | PhaseEnvelopeResult,
    *,
    branch: Literal["bubble", "dew"] = "bubble",
    component_index: int = 0,
    x_axis: Literal["temperature", "pressure"] = "temperature",
    pressure_unit: PressureUnit | str = PressureUnit.MPA,
    display: CompositionDisplay | str = CompositionDisplay.FRACTION,
    title: str | None = None,
) -> go.Figure:
    """Plot available liquid/vapor composition from accepted branch points."""

    source = (
        phase_envelope_plot_data(data)
        if isinstance(data, PhaseEnvelopeResult)
        else data
    )
    points = source.bubble_points if branch == "bubble" else source.dew_points
    points = _validated_phase_points(points, branch)
    if not points:
        raise ValueError("selected branch contains no points")
    if any(
        point.liquid_composition is None or point.vapor_composition is None
        for point in points
    ):
        raise ValueError("composition data are unavailable for one or more points")
    liquid_raw = tuple(
        _component_value(point.liquid_composition, component_index) for point in points
    )
    vapor_raw = tuple(
        _component_value(point.vapor_composition, component_index) for point in points
    )
    liquid = _composition_values(liquid_raw, display)
    vapor = _composition_values(vapor_raw, display)
    unit = _pressure_unit(pressure_unit)
    if x_axis == "temperature":
        x = tuple(point.temperature_k for point in points)
        x_title = "Temperature (K)"
    elif x_axis == "pressure":
        x = convert_pressure(tuple(point.pressure_pa for point in points), unit)
        x_title = f"Pressure ({unit.value})"
    else:
        raise ValueError("x_axis must be temperature or pressure")
    component = (
        source.component_names[component_index]
        if component_index < len(source.component_names)
        else f"Component {component_index + 1}"
    )
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x,
            y=liquid,
            mode="lines+markers",
            name="Liquid composition",
            line={"color": BLUE, "dash": "solid"},
            marker={"symbol": "circle"},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=vapor,
            mode="lines+markers",
            name="Vapor composition",
            line={"color": ORANGE, "dash": "dash"},
            marker={"symbol": "diamond"},
        )
    )
    fig.update_layout(
        title=title or f"{component} Phase Compositions — {branch.title()} Branch",
        xaxis_title=x_title,
        yaxis_title=f"{component} {_composition_label(display).lower()}",
        font={"size": 14, "color": CHARCOAL},
    )
    return fig


def plot_binary_xy(
    data: PhaseEnvelopePlotData | PhaseEnvelopeResult,
    *,
    branch: Literal["bubble", "dew"] = "bubble",
    component_index: int = 0,
    display: CompositionDisplay | str = CompositionDisplay.FRACTION,
    title: str | None = None,
) -> go.Figure:
    """Plot liquid x against vapor y only when binary compositions exist."""

    source = (
        phase_envelope_plot_data(data)
        if isinstance(data, PhaseEnvelopeResult)
        else data
    )
    if source.component_names and len(source.component_names) != 2:
        raise ValueError("x-y visualization is supported only for binary data")
    points = source.bubble_points if branch == "bubble" else source.dew_points
    if not points:
        raise ValueError("selected branch contains no points")
    if any(
        point.liquid_composition is None
        or point.vapor_composition is None
        or len(point.liquid_composition) != 2
        or len(point.vapor_composition) != 2
        for point in points
    ):
        raise ValueError("complete binary liquid/vapor compositions are required")
    liquid = _composition_values(
        tuple(
            _component_value(point.liquid_composition, component_index)
            for point in points
        ),
        display,
    )
    vapor = _composition_values(
        tuple(
            _component_value(point.vapor_composition, component_index)
            for point in points
        ),
        display,
    )
    maximum = (
        100.0
        if _composition_display(display) is CompositionDisplay.MOL_PERCENT
        else 1.0
    )
    component = (
        source.component_names[component_index]
        if source.component_names
        else "Component 1"
    )
    fig = go.Figure(
        (
            go.Scatter(
                x=liquid,
                y=vapor,
                mode="lines+markers",
                name="Liquid–vapor states",
                line={"color": BLUE},
                marker={"symbol": "circle"},
            ),
            go.Scatter(
                x=(0.0, maximum),
                y=(0.0, maximum),
                mode="lines",
                name="x = y",
                line={"color": CHARCOAL, "dash": "dot"},
            ),
        )
    )
    suffix = "mol %" if maximum == 100.0 else "mole fraction"
    fig.update_layout(
        title=title or f"Binary x-y Diagram — {component}",
        xaxis_title=f"Liquid {component} {suffix}",
        yaxis_title=f"Vapor {component} {suffix}",
        font={"size": 14, "color": CHARCOAL},
    )
    return fig


def plot_pseudo_arclength_trace(
    result: PseudoArclengthBranchResult,
    *,
    pressure_unit: PressureUnit | str = PressureUnit.MPA,
    title: str | None = None,
    metadata: Mapping[str, str] | None = None,
) -> go.Figure:
    """Plot an existing Module 18 P-T trace and explicit turning diagnostics."""

    if not result.points:
        raise ValueError("pseudo-arclength trace contains no points")
    unit = _pressure_unit(pressure_unit)
    for point in result.points:
        _finite_pair(point.temperature_k, point.pressure_pa)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=tuple(point.temperature_k for point in result.points),
            y=convert_pressure(
                tuple(point.pressure_pa for point in result.points), unit
            ),
            mode="lines+markers",
            name=f"{result.branch_kind.value.title()} pseudo-arclength trace",
            line={"color": BLUE, "width": 2.5},
            marker={"symbol": "circle", "size": 7},
            hovertemplate=(
                "Pseudo-arclength state<br>T=%{x:.8g} K<br>P=%{y:.8g} "
                f"{unit.value}<extra></extra>"
            ),
        )
    )
    for attribute, name, symbol, color in (
        (
            "pressure_turning_point",
            "Pressure turning point (not critical)",
            "triangle-up",
            ORANGE,
        ),
        (
            "temperature_turning_point",
            "Temperature turning point (not critical)",
            "triangle-left",
            GOLD,
        ),
    ):
        selected = tuple(point for point in result.points if getattr(point, attribute))
        if selected:
            fig.add_trace(
                go.Scatter(
                    x=tuple(point.temperature_k for point in selected),
                    y=convert_pressure(
                        tuple(point.pressure_pa for point in selected), unit
                    ),
                    mode="markers",
                    name=name,
                    marker={"symbol": symbol, "size": 13, "color": color},
                )
            )
    termination_names = {
        "near_critical": "Near-critical termination (not critical point)",
        "phase_role_lost": "Phase-role-lost termination",
        "trivial_state": "Trivial-state termination",
    }
    termination = result.termination_reason.value
    if termination in termination_names:
        last = result.points[-1]
        fig.add_trace(
            go.Scatter(
                x=(last.temperature_k,),
                y=(convert_pressure(last.pressure_pa, unit),),
                mode="markers",
                name=termination_names[termination],
                marker={"symbol": "x-open", "size": 12, "color": CHARCOAL},
            )
        )
    _layout(fig, title or "Pseudo-Arclength Phase Trace", f"Pressure ({unit.value})")
    _apply_metadata(fig, metadata)
    return fig


PseudoMetric = Literal["dlnp_ds", "dlnt_ds", "step_size", "corrector_iterations"]


def plot_pseudo_arclength_diagnostic(
    result: PseudoArclengthBranchResult,
    metric: PseudoMetric,
    *,
    title: str | None = None,
) -> go.Figure:
    """Plot one reusable Module 18 continuation diagnostic."""

    if not result.points:
        raise ValueError("pseudo-arclength trace contains no points")
    indices = tuple(range(len(result.points)))
    if metric in ("dlnp_ds", "dlnt_ds"):
        coordinate = -2 if metric == "dlnp_ds" else -1
        values = tuple(
            None if point.tangent is None else point.tangent[coordinate]
            for point in result.points
        )
        label = "dln(P)/ds" if metric == "dlnp_ds" else "dln(T)/ds"
    elif metric == "step_size":
        values = tuple(point.accepted_step for point in result.points)
        label = "Accepted arclength step"
    elif metric == "corrector_iterations":
        values = tuple(point.corrector_iterations for point in result.points)
        label = "Corrector iterations"
    else:
        raise ValueError("unsupported pseudo-arclength diagnostic metric")
    finite_values = tuple(value for value in values if value is not None)
    if not finite_values or not all(isfinite(float(value)) for value in finite_values):
        raise ValueError("selected diagnostic contains no finite values")
    fig = go.Figure(
        go.Scatter(
            x=indices,
            y=values,
            mode="lines+markers",
            name=label,
            line={"color": BLUE},
            marker={"symbol": "circle"},
        )
    )
    fig.update_layout(
        title=title or f"Pseudo-Arclength Diagnostic — {label}",
        xaxis_title="Continuation point index",
        yaxis_title=label,
        font={"size": 14, "color": CHARCOAL},
    )
    if metric in ("dlnp_ds", "dlnt_ds"):
        fig.add_hline(y=0.0, line_dash="dot", line_color=CHARCOAL)
    return fig


@dataclass(frozen=True, slots=True)
class ValidationPlotRecord:
    """Centralized plotting adapter for one Module 17 result row."""

    source_point_id: str
    system_id: str
    temperature_k: float
    experimental_pressure_pa: float
    experimental_liquid_composition: tuple[float, ...]
    experimental_vapor_composition: tuple[float, ...]
    bubble_status: str
    bubble_predicted_pressure_pa: float | None
    bubble_pressure_relative_error: float | None
    bubble_predicted_composition: tuple[float, ...]
    dew_status: str
    dew_predicted_pressure_pa: float | None
    dew_pressure_relative_error: float | None
    dew_predicted_composition: tuple[float, ...]
    dew_failure_classification: str
    dew_production_selected_root_class: str | None
    retrospective_nearest_root_pressure_pa: float | None
    retrospective_nearest_root_class: str | None


def validation_plot_records(
    results: Iterable[ExperimentalVLEValidationResult],
) -> tuple[ValidationPlotRecord, ...]:
    """Adapt immutable Module 17 results once for all validation figures."""

    materialized = tuple(results)
    records = tuple(
        ValidationPlotRecord(
            item.point.source_point_id,
            item.point.system_id,
            item.point.temperature_k,
            item.point.pressure_pa,
            tuple(item.point.liquid_mole_fractions),
            tuple(item.point.vapor_mole_fractions),
            item.bubble.status,
            item.bubble.predicted_pressure_pa,
            item.bubble.pressure_relative_error,
            tuple(item.bubble.predicted_composition),
            item.dew.status,
            item.dew.predicted_pressure_pa,
            item.dew.pressure_relative_error,
            tuple(item.dew.predicted_composition),
            item.dew_branch_diagnostic.failure_classification.value,
            (
                None
                if item.dew_branch_diagnostic.production_selected_root_class is None
                else item.dew_branch_diagnostic.production_selected_root_class.value
            ),
            item.dew_branch_diagnostic.nearest_pr_root_to_experiment_pressure_pa,
            (
                None
                if item.dew_branch_diagnostic.nearest_pr_root_class is None
                else item.dew_branch_diagnostic.nearest_pr_root_class.value
            ),
        )
        for item in materialized
    )
    _validate_validation_records(records)
    return records


def _json_tuple(cell: str) -> tuple[float, ...]:
    if not cell:
        return ()
    value = json.loads(cell)
    if not isinstance(value, list):
        raise ValueError("validation composition cell must contain a JSON list")
    return tuple(float(item) for item in value)


def _validation_records_from_rows(
    rows: Sequence[dict[str, object]],
) -> tuple[ValidationPlotRecord, ...]:
    required = {
        "source_point_id",
        "system_id",
        "temperature_k",
        "experimental_pressure_pa",
        "liquid_mole_fractions",
        "vapor_mole_fractions",
        "bubble_status",
        "bubble_predicted_pressure_pa",
        "bubble_pressure_relative_error",
        "bubble_predicted_vapor_composition",
        "dew_status",
        "dew_predicted_pressure_pa",
        "dew_pressure_relative_error",
        "dew_predicted_liquid_composition",
        "dew_failure_classification",
        "dew_production_selected_root_class",
        "dew_nearest_experimental_root_pressure_pa",
        "dew_nearest_experimental_root_class",
    }
    if not rows or not required.issubset(rows[0]):
        raise ValueError("Module 17 result artifact schema is incomplete")

    def text(row: dict[str, object], key: str) -> str:
        value = row[key]
        return "" if value is None else str(value)

    def optional_float(cell: object) -> float | None:
        if cell is None or cell == "":
            return None
        value = float(str(cell))
        return None if np.isnan(value) else value

    def required_float(row: dict[str, object], key: str) -> float:
        return float(str(row[key]))

    records = tuple(
        ValidationPlotRecord(
            text(row, "source_point_id"),
            text(row, "system_id"),
            required_float(row, "temperature_k"),
            required_float(row, "experimental_pressure_pa"),
            _json_tuple(text(row, "liquid_mole_fractions")),
            _json_tuple(text(row, "vapor_mole_fractions")),
            text(row, "bubble_status"),
            optional_float(row["bubble_predicted_pressure_pa"]),
            optional_float(row["bubble_pressure_relative_error"]),
            _json_tuple(text(row, "bubble_predicted_vapor_composition")),
            text(row, "dew_status"),
            optional_float(row["dew_predicted_pressure_pa"]),
            optional_float(row["dew_pressure_relative_error"]),
            _json_tuple(text(row, "dew_predicted_liquid_composition")),
            text(row, "dew_failure_classification"),
            text(row, "dew_production_selected_root_class") or None,
            optional_float(row["dew_nearest_experimental_root_pressure_pa"]),
            text(row, "dew_nearest_experimental_root_class") or None,
        )
        for row in rows
    )
    _validate_validation_records(records)
    return records


def load_validation_plot_records(path: Path) -> tuple[ValidationPlotRecord, ...]:
    """Load the canonical Module 17 result artifact through one strict adapter."""

    with path.open(newline="", encoding="utf-8") as stream:
        rows = tuple(dict(row) for row in csv.DictReader(stream))
    return _validation_records_from_rows(rows)


def validation_plot_records_from_dataframe(
    frame: pd.DataFrame,
) -> tuple[ValidationPlotRecord, ...]:
    """Adapt a result-schema DataFrame without modifying it."""

    rows = tuple(dict(row) for row in frame.to_dict(orient="records"))
    return _validation_records_from_rows(rows)


def _validate_validation_records(records: Sequence[ValidationPlotRecord]) -> None:
    if not records:
        raise ValueError("validation plotting requires at least one record")
    for record in records:
        _finite_pair(record.temperature_k, record.experimental_pressure_pa)
        for value in (
            record.bubble_predicted_pressure_pa,
            record.bubble_pressure_relative_error,
            record.dew_predicted_pressure_pa,
            record.dew_pressure_relative_error,
            record.retrospective_nearest_root_pressure_pa,
        ):
            if value is not None and not isfinite(value):
                raise ValueError("validation numeric fields must be finite")


ValidationDirection = Literal["bubble", "dew"]


def _direction_fields(
    record: ValidationPlotRecord, direction: ValidationDirection
) -> tuple[str, float | None, float | None, tuple[float, ...]]:
    if direction == "bubble":
        return (
            record.bubble_status,
            record.bubble_predicted_pressure_pa,
            record.bubble_pressure_relative_error,
            record.bubble_predicted_composition,
        )
    if direction == "dew":
        return (
            record.dew_status,
            record.dew_predicted_pressure_pa,
            record.dew_pressure_relative_error,
            record.dew_predicted_composition,
        )
    raise ValueError("direction must be bubble or dew")


def plot_validation_pressure_parity(
    records: Sequence[ValidationPlotRecord],
    *,
    direction: ValidationDirection,
    pressure_unit: PressureUnit | str = PressureUnit.MPA,
    title: str | None = None,
    metadata: Mapping[str, str] | None = None,
) -> go.Figure:
    """Plot production-selected predictions only against experiment."""

    materialized = tuple(records)
    _validate_validation_records(materialized)
    successful = tuple(
        (record, fields)
        for record in materialized
        if (fields := _direction_fields(record, direction))[0] == "converged"
        and fields[1] is not None
    )
    if not successful:
        raise ValueError("selected direction contains no successful predictions")
    unit = _pressure_unit(pressure_unit)
    experimental = tuple(item[0].experimental_pressure_pa for item in successful)
    predicted = tuple(
        _required_float(item[1][1], "predicted pressure") for item in successful
    )
    converted_x = convert_pressure(experimental, unit)
    converted_y = convert_pressure(predicted, unit)
    lower = min((*converted_x, *converted_y))
    upper = max((*converted_x, *converted_y))
    ids = tuple(item[0].source_point_id for item in successful)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=converted_x,
            y=converted_y,
            mode="markers",
            name=f"Production {direction} prediction",
            marker={"symbol": "circle", "size": 8, "color": BLUE},
            text=ids,
            hovertemplate=(
                "%{text}<br>Experimental=%{x:.8g}<br>Predicted=%{y:.8g}"
                "<extra>Production prediction</extra>"
            ),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=(lower, upper),
            y=(lower, upper),
            mode="lines",
            name="y = x reference",
            line={"color": CHARCOAL, "dash": "dot"},
            hoverinfo="skip",
        )
    )
    fig.update_layout(
        title=title or "Experimental vs PR Pressure",
        xaxis_title=f"Experimental pressure ({unit.value})",
        yaxis_title=f"Predicted pressure ({unit.value})",
        font={"size": 14, "color": CHARCOAL},
    )
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    _apply_metadata(fig, metadata)
    return fig


def plot_validation_pressure_error(
    records: Sequence[ValidationPlotRecord],
    *,
    direction: ValidationDirection,
    x_axis: Literal["temperature", "experimental_pressure"] = "temperature",
    pressure_unit: PressureUnit | str = PressureUnit.MPA,
    title: str | None = None,
) -> go.Figure:
    """Plot 100*(P_pred-P_exp)/P_exp using the Module 17 sign convention."""

    materialized = tuple(records)
    _validate_validation_records(materialized)
    successful = tuple(
        (record, fields)
        for record in materialized
        if (fields := _direction_fields(record, direction))[0] == "converged"
        and fields[2] is not None
    )
    if not successful:
        raise ValueError("selected direction contains no pressure errors")
    if x_axis == "temperature":
        x = tuple(item[0].temperature_k for item in successful)
        x_title = "Temperature (K)"
    elif x_axis == "experimental_pressure":
        unit = _pressure_unit(pressure_unit)
        x = convert_pressure(
            tuple(item[0].experimental_pressure_pa for item in successful), unit
        )
        x_title = f"Experimental pressure ({unit.value})"
    else:
        raise ValueError("x_axis must be temperature or experimental_pressure")
    y = tuple(
        100.0 * _required_float(item[1][2], "relative pressure error")
        for item in successful
    )
    fig = go.Figure(
        go.Scatter(
            x=x,
            y=y,
            mode="markers",
            name=f"{direction.title()} relative pressure error",
            marker={"symbol": "circle", "size": 8, "color": BLUE},
        )
    )
    fig.add_hline(y=0.0, line_dash="dot", line_color=CHARCOAL)
    fig.update_layout(
        title=title or "PR Relative Pressure Error",
        xaxis_title=x_title,
        yaxis_title="Relative pressure error, 100×(P_pred−P_exp)/P_exp (%)",
        font={"size": 14, "color": CHARCOAL},
    )
    return fig


def plot_validation_composition_parity(
    records: Sequence[ValidationPlotRecord],
    *,
    direction: ValidationDirection,
    component_index: int = 0,
    display: CompositionDisplay | str = CompositionDisplay.FRACTION,
    title: str | None = None,
) -> go.Figure:
    """Plot production-predicted incipient composition against experiment."""

    materialized = tuple(records)
    _validate_validation_records(materialized)
    rows: list[tuple[float, float]] = []
    for record in materialized:
        status, _, _, predicted = _direction_fields(record, direction)
        experimental = (
            record.experimental_vapor_composition
            if direction == "bubble"
            else record.experimental_liquid_composition
        )
        if status == "converged" and predicted:
            rows.append((experimental[component_index], predicted[component_index]))
    if not rows:
        raise ValueError("selected direction contains no composition predictions")
    x = _composition_values(tuple(row[0] for row in rows), display)
    y = _composition_values(tuple(row[1] for row in rows), display)
    maximum = (
        100.0
        if _composition_display(display) is CompositionDisplay.MOL_PERCENT
        else 1.0
    )
    fig = go.Figure(
        (
            go.Scatter(
                x=x,
                y=y,
                mode="markers",
                name="Production composition prediction",
                marker={"symbol": "circle", "size": 8, "color": BLUE},
            ),
            go.Scatter(
                x=(0.0, maximum),
                y=(0.0, maximum),
                mode="lines",
                name="y = x reference",
                line={"color": CHARCOAL, "dash": "dot"},
            ),
        )
    )
    label = "mol %" if maximum == 100.0 else "mole fraction"
    fig.update_layout(
        title=title or "Experimental vs PR Composition",
        xaxis_title=f"Experimental composition ({label})",
        yaxis_title=f"Predicted composition ({label})",
        font={"size": 14, "color": CHARCOAL},
    )
    return fig


def plot_validation_status(
    records: Sequence[ValidationPlotRecord],
    *,
    direction: ValidationDirection,
    title: str | None = None,
) -> go.Figure:
    """Count exact production statuses/failure classes without collapsing them."""

    materialized = tuple(records)
    _validate_validation_records(materialized)
    categories: dict[str, int] = {}
    for record in materialized:
        status = _direction_fields(record, direction)[0]
        if direction == "dew" and status != "converged":
            category = record.dew_failure_classification
        elif direction == "dew":
            category = (
                f"converged:{record.dew_production_selected_root_class or 'UNMATCHED'}"
            )
        else:
            category = status
        categories[category] = categories.get(category, 0) + 1
    labels = tuple(sorted(categories))
    fig = go.Figure(
        go.Bar(
            x=labels,
            y=tuple(categories[label] for label in labels),
            name="Case count",
            marker={"color": BLUE, "line": {"color": CHARCOAL, "width": 1}},
        )
    )
    fig.update_layout(
        title=title or f"Validation Status — {direction.title()}",
        xaxis_title="Production status / exact failure classification",
        yaxis_title="Case count",
        font={"size": 14, "color": CHARCOAL},
    )
    return fig


def plot_validation_retrospective_diagnostics(
    records: Sequence[ValidationPlotRecord],
    *,
    pressure_unit: PressureUnit | str = PressureUnit.MPA,
    title: str | None = None,
) -> go.Figure:
    """Plot validation-only nearest-root diagnostics separately from predictions."""

    materialized = tuple(records)
    _validate_validation_records(materialized)
    available = tuple(
        record
        for record in materialized
        if record.retrospective_nearest_root_pressure_pa is not None
    )
    if not available:
        raise ValueError("no retrospective diagnostic roots are available")
    unit = _pressure_unit(pressure_unit)
    fig = go.Figure(
        go.Scatter(
            x=convert_pressure(
                tuple(record.experimental_pressure_pa for record in available), unit
            ),
            y=convert_pressure(
                tuple(
                    _required_float(
                        record.retrospective_nearest_root_pressure_pa,
                        "retrospective nearest-root pressure",
                    )
                    for record in available
                ),
                unit,
            ),
            mode="markers",
            name="Retrospective nearest PR root (not production prediction)",
            marker={"symbol": "x-open", "size": 9, "color": ORANGE},
            text=tuple(record.retrospective_nearest_root_class for record in available),
        )
    )
    fig.update_layout(
        title=title or "Retrospective Dew-Root Diagnostic",
        xaxis_title=f"Experimental pressure ({unit.value})",
        yaxis_title=f"Retrospective nearest-root pressure ({unit.value})",
        font={"size": 14, "color": CHARCOAL},
    )
    return fig


@dataclass(frozen=True, slots=True)
class CriticalityGrid:
    """Rectangular precomputed residual grid for pure contour rendering."""

    temperatures_k: tuple[float, ...]
    pressures_pa: tuple[float, ...]
    lambda_min: tuple[tuple[float | None, ...], ...]
    cubic_coefficient: tuple[tuple[float | None, ...], ...]
    statuses: tuple[tuple[str, ...], ...]


def criticality_grid_from_scan(scan: CriticalPointScanResult) -> CriticalityGrid:
    """Reshape the deterministic temperature-major Module 20 diagnostic scan."""

    temperatures = tuple(sorted({entry.temperature_k for entry in scan.entries}))
    pressures = tuple(sorted({entry.pressure_pa for entry in scan.entries}))
    lookup = {(entry.temperature_k, entry.pressure_pa): entry for entry in scan.entries}
    if len(lookup) != len(temperatures) * len(pressures):
        raise ValueError("criticality scan is not a complete rectangular grid")
    lambda_rows: list[tuple[float | None, ...]] = []
    cubic_rows: list[tuple[float | None, ...]] = []
    status_rows: list[tuple[str, ...]] = []
    for pressure in pressures:
        row = tuple(lookup[(temperature, pressure)] for temperature in temperatures)
        lambda_rows.append(tuple(item.lambda_min for item in row))
        cubic_rows.append(tuple(item.cubic_coefficient for item in row))
        status_rows.append(tuple(item.status.value for item in row))
    return CriticalityGrid(
        temperatures,
        pressures,
        tuple(lambda_rows),
        tuple(cubic_rows),
        tuple(status_rows),
    )


def _validate_criticality_grid(grid: CriticalityGrid) -> None:
    if len(grid.temperatures_k) < 2 or len(grid.pressures_pa) < 2:
        raise ValueError("criticality grid requires at least two values per axis")
    if not all(isfinite(value) and value > 0.0 for value in grid.temperatures_k):
        raise ValueError("criticality temperatures must be positive finite")
    if not all(isfinite(value) and value > 0.0 for value in grid.pressures_pa):
        raise ValueError("criticality pressures must be positive finite")
    expected = (len(grid.pressures_pa), len(grid.temperatures_k))
    for name, matrix in (
        ("lambda", grid.lambda_min),
        ("cubic", grid.cubic_coefficient),
        ("status", grid.statuses),
    ):
        if len(matrix) != expected[0] or any(len(row) != expected[1] for row in matrix):
            raise ValueError(f"{name} grid shape does not match its axes")
    for matrix in (grid.lambda_min, grid.cubic_coefficient):
        for row in matrix:
            if any(value is not None and not isfinite(value) for value in row):
                raise ValueError("criticality residual grids must be finite or None")


def plot_criticality_map(
    grid: CriticalityGrid | CriticalPointScanResult,
    *,
    pressure_unit: PressureUnit | str = PressureUnit.MPA,
    critical_point: MixtureCriticalPointResult | None = None,
    title: str | None = None,
    metadata: Mapping[str, str] | None = None,
) -> go.Figure:
    """Plot precomputed lambda=0 and C=0 contours and their candidate intersection."""

    source = (
        criticality_grid_from_scan(grid)
        if isinstance(grid, CriticalPointScanResult)
        else grid
    )
    _validate_criticality_grid(source)
    unit = _pressure_unit(pressure_unit)
    pressures = convert_pressure(source.pressures_pa, unit)
    fig = go.Figure()
    for name, matrix, color, dash in (
        ("lambda_min = 0 (spinodal condition)", source.lambda_min, BLUE, "solid"),
        ("C = 0 (cubic condition)", source.cubic_coefficient, ORANGE, "dash"),
    ):
        fig.add_trace(
            go.Contour(
                x=source.temperatures_k,
                y=pressures,
                z=matrix,
                name=name,
                showscale=False,
                contours={
                    "start": 0.0,
                    "end": 0.0,
                    "size": 1.0,
                    "coloring": "lines",
                    "showlabels": True,
                },
                line={"color": color, "width": 3, "dash": dash},
                hovertemplate=(
                    f"{name}<br>T=%{{x:.8g}} K<br>P=%{{y:.8g}} {unit.value}"
                    "<br>residual=%{z:.8g}<extra></extra>"
                ),
            )
        )
    unavailable_x: list[float] = []
    unavailable_y: list[float] = []
    for pressure_index, status_row in enumerate(source.statuses):
        for temperature_index, status in enumerate(status_row):
            if status != "applicable":
                unavailable_x.append(source.temperatures_k[temperature_index])
                unavailable_y.append(float(pressures[pressure_index]))
    if unavailable_x:
        fig.add_trace(
            go.Scatter(
                x=tuple(unavailable_x),
                y=tuple(unavailable_y),
                mode="markers",
                name="Criticality unavailable",
                marker={"symbol": "x-open", "color": GREY, "size": 8},
            )
        )
    model_label = metadata.get("model") if metadata is not None else None
    _add_critical_point(fig, critical_point, unit, model_label)
    _layout(fig, title or "Criticality Residual Map", f"Pressure ({unit.value})")
    _apply_metadata(fig, metadata)
    return fig


def plot_critical_solver_convergence(
    result: MixtureCriticalPointResult,
    *,
    include_raw_residuals: bool = True,
    title: str | None = None,
    metadata: Mapping[str, str] | None = None,
) -> go.Figure:
    """Plot Module 20 convergence evidence with explicit absolute raw residuals."""

    if not result.history:
        raise ValueError("critical solver result contains no iteration history")
    iterations = tuple(item.iteration for item in result.history)
    scaled = tuple(item.scaled_residual_norm for item in result.history)
    if not all(isfinite(value) and value >= 0.0 for value in scaled):
        raise ValueError("scaled residual history must be finite and nonnegative")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=iterations,
            y=scaled,
            mode="lines+markers",
            name="Scaled residual norm",
            line={"color": BLUE},
            marker={"symbol": "circle"},
        )
    )
    if include_raw_residuals:
        fig.add_trace(
            go.Scatter(
                x=iterations,
                y=tuple(abs(item.lambda_min) for item in result.history),
                mode="lines+markers",
                name="|lambda_min|",
                line={"color": ORANGE, "dash": "dash"},
                marker={"symbol": "diamond"},
            )
        )
        fig.add_trace(
            go.Scatter(
                x=iterations,
                y=tuple(abs(item.cubic_coefficient) for item in result.history),
                mode="lines+markers",
                name="|C|",
                line={"color": GOLD, "dash": "dot"},
                marker={"symbol": "square"},
            )
        )
    fig.update_layout(
        title=title or "Critical Solver Convergence",
        xaxis_title="Accepted iteration",
        yaxis_title="Residual magnitude (absolute value where labeled)",
        yaxis_type="log",
        font={"size": 14, "color": CHARCOAL},
    )
    _apply_metadata(fig, metadata)
    return fig


def plot_critical_solver_conditioning(
    result: MixtureCriticalPointResult,
    *,
    title: str | None = None,
) -> go.Figure:
    """Plot recorded Jacobian condition numbers separately from residuals."""

    values = tuple(result.jacobian_condition_history)
    if not values or not all(isfinite(value) and value > 0.0 for value in values):
        raise ValueError("no positive finite Jacobian condition history is available")
    fig = go.Figure(
        go.Scatter(
            x=tuple(range(1, len(values) + 1)),
            y=values,
            mode="lines+markers",
            name="Jacobian condition number",
            line={"color": BLUE},
            marker={"symbol": "circle"},
        )
    )
    fig.update_layout(
        title=title or "Critical Solver Jacobian Conditioning",
        xaxis_title="Newton iteration",
        yaxis_title="Jacobian condition number",
        yaxis_type="log",
        font={"size": 14, "color": CHARCOAL},
    )
    return fig


def plot_critical_solver_path(
    result: MixtureCriticalPointResult,
    *,
    pressure_unit: PressureUnit | str = PressureUnit.MPA,
    title: str | None = None,
) -> go.Figure:
    """Plot accepted Newton iterates as a solver trajectory, never a phase boundary."""

    if not result.history:
        raise ValueError("critical solver result contains no iteration history")
    unit = _pressure_unit(pressure_unit)
    for item in result.history:
        _finite_pair(item.temperature_k, item.pressure_pa)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=tuple(item.temperature_k for item in result.history),
            y=convert_pressure(
                tuple(item.pressure_pa for item in result.history), unit
            ),
            mode="lines+markers",
            name="Accepted Newton trajectory (not phase boundary)",
            line={"color": BLUE, "dash": "dash"},
            marker={"symbol": "circle", "size": 8},
            text=tuple(f"iteration {item.iteration}" for item in result.history),
            hovertemplate=(
                "%{text}<br>T=%{x:.10g} K<br>P=%{y:.10g} "
                f"{unit.value}<extra>Nonlinear solver trajectory</extra>"
            ),
        )
    )
    if result.status is CriticalPointStatus.CONVERGED:
        _add_critical_point(fig, result, unit)
    _layout(
        fig,
        title or "Critical-Point Nonlinear Solver Trajectory",
        f"Pressure ({unit.value})",
    )
    fig.add_annotation(
        text="Numerical solver path — not a thermodynamic phase boundary",
        xref="paper",
        yref="paper",
        x=0.0,
        y=-0.2,
        showarrow=False,
        font={"color": GREY},
    )
    return fig
