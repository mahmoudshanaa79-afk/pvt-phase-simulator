"""Approved Plotly figure families built only from production evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, cast

from pvt_phase_simulator_validation.comparisons import (
    ComparisonState,
    UndefinedMetric,
    align_values,
)
from pvt_phase_simulator_validation.enums import CapabilityUnderTest, ValidationQuantity

from .evidence import ProductionCase, ProductionEvidence


@dataclass(frozen=True, slots=True)
class ReportFigure:
    figure_id: str
    family: str
    title: str
    caption: str
    figure: Any


_COLORS = ("#087f8c", "#c46d2d", "#5b5f97", "#7a8b43")


def _to_mpa(value: float) -> float:
    from pvt_phase_simulator.plotting import PressureUnit, convert_pressure

    return float(convert_pressure(value, PressureUnit.MPA))


def _case_map(production: ProductionEvidence) -> dict[str, ProductionCase]:
    return {case.case_id: case for case in production.cases}


def _comparison(case_comparison: Any, quantity: ValidationQuantity):  # type: ignore[no-untyped-def]
    return next(
        item
        for item in case_comparison.quantity_comparisons
        if item.key.quantity is quantity
    )


def _values(case: ProductionCase, quantity: ValidationQuantity):  # type: ignore[no-untyped-def]
    reference = next(
        item for item in case.reference_values if item.quantity is quantity
    )
    prediction = next(
        item for item in case.prediction_values if item.quantity is quantity
    )
    return align_values(reference, prediction)


def _temperature(case: ProductionCase) -> float:
    value = next(
        item.value
        for item in case.specified_conditions
        if item.quantity is ValidationQuantity.TEMPERATURE
    )
    assert isinstance(value, float)
    return value


def _methane_fraction(case: ProductionCase) -> tuple[float, str]:
    value = next(
        item
        for item in case.specified_conditions
        if item.quantity is ValidationQuantity.MOLE_FRACTION
    )
    assert isinstance(value.value, tuple) and value.phase is not None
    by_id = dict(zip(value.component_ids or (), value.value, strict=True))
    return by_id["methane"], value.phase.value


def _caption(
    production: ProductionEvidence,
    capability: CapabilityUnderTest,
    quantity: ValidationQuantity,
) -> str:
    aggregate = next(
        item
        for item in production.pooled_coverage
        if item.grouping_key.capability is capability
        and item.grouping_key.comparison_key.quantity is quantity
    )
    coverage = aggregate.coverage
    return f"{coverage.compared_cases} compared of {coverage.total_cases} total cases."


def _phase_label(
    production: ProductionEvidence,
    capability: CapabilityUnderTest,
    quantity: ValidationQuantity,
) -> str:
    phases = {
        item.key.phase.value.lower()
        for comparison in production.comparisons
        if comparison.capability is capability
        for item in comparison.quantity_comparisons
        if item.key.quantity is quantity and item.key.phase is not None
    }
    if len(phases) != 1:
        raise ValueError("figure quantity must have one unambiguous phase")
    return next(iter(phases))


def _layout(figure: Any, x_title: str, y_title: str) -> None:
    figure.update_layout(
        template="plotly_white",
        margin={"l": 64, "r": 24, "t": 42, "b": 64},
        height=430,
        font={"family": "Arial, sans-serif", "size": 13, "color": "#18242a"},
        legend={"orientation": "h", "y": 1.12, "x": 0},
        hovermode="closest",
    )
    figure.update_xaxes(title_text=x_title, gridcolor="#dce5e7")
    figure.update_yaxes(title_text=y_title, gridcolor="#dce5e7")


def _pressure_parity(
    production: ProductionEvidence, capability: CapabilityUnderTest
) -> ReportFigure:
    import plotly.graph_objects as go  # type: ignore[import-untyped]

    cases = _case_map(production)
    figure = go.Figure()
    all_values: list[float] = []
    for color, system_id in zip(
        _COLORS, sorted({case.system_id for case in production.cases}), strict=False
    ):
        refs: list[float] = []
        preds: list[float] = []
        ids: list[str] = []
        for comparison in production.comparisons:
            if (
                comparison.capability is not capability
                or comparison.system_id != system_id
            ):
                continue
            quantity = _comparison(comparison, ValidationQuantity.PRESSURE)
            if quantity.comparison_state is not ComparisonState.COMPARED:
                continue
            reference, prediction = _values(
                cases[comparison.case_id], ValidationQuantity.PRESSURE
            )
            assert isinstance(reference, float) and isinstance(prediction, float)
            refs.append(_to_mpa(reference))
            preds.append(_to_mpa(prediction))
            ids.append(comparison.case_id)
        all_values.extend((*refs, *preds))
        figure.add_trace(
            go.Scatter(
                x=refs,
                y=preds,
                mode="markers",
                name=system_id,
                marker={"color": color, "size": 8},
                customdata=ids,
                hovertemplate=(
                    "%{customdata}<br>reference=%{x:.6g} MPa"
                    "<br>prediction=%{y:.6g} MPa<extra></extra>"
                ),
            )
        )
    if all_values:
        lower, upper = min(all_values), max(all_values)
        figure.add_trace(
            go.Scatter(
                x=[lower, upper],
                y=[lower, upper],
                mode="lines",
                name="identity",
                line={"color": "#57666c", "dash": "dash"},
                hoverinfo="skip",
            )
        )
    _layout(figure, "Reference pressure (MPa)", "Predicted pressure (MPa)")
    label = capability.value.replace("_", " ").title()
    return ReportFigure(
        f"figure-f1-{capability.value.lower()}",
        "F1",
        f"Pressure parity — {label}",
        _caption(production, capability, ValidationQuantity.PRESSURE),
        figure,
    )


def _pressure_error(
    production: ProductionEvidence,
    capability: CapabilityUnderTest,
    family: str,
    x_kind: str,
) -> ReportFigure:
    import plotly.graph_objects as go

    cases = _case_map(production)
    figure = go.Figure()
    phase_label = ""
    plotted = 0
    for color, system_id in zip(
        _COLORS, sorted({case.system_id for case in production.cases}), strict=False
    ):
        xs: list[float] = []
        ys: list[float] = []
        ids: list[str] = []
        for case_comparison in production.comparisons:
            if (
                case_comparison.capability is not capability
                or case_comparison.system_id != system_id
            ):
                continue
            quantity = _comparison(case_comparison, ValidationQuantity.PRESSURE)
            if quantity.comparison_state is not ComparisonState.COMPARED:
                continue
            assert quantity.errors is not None
            relative = quantity.errors.relative_error
            if relative is None or isinstance(relative, (tuple, UndefinedMetric)):
                continue
            case = cases[case_comparison.case_id]
            if x_kind == "temperature":
                x = _temperature(case)
            elif x_kind == "pressure":
                reference, _ = _values(case, ValidationQuantity.PRESSURE)
                assert isinstance(reference, float)
                x = _to_mpa(reference)
            else:
                x, phase_label = _methane_fraction(case)
            xs.append(x)
            ys.append(relative)
            ids.append(case.case_id)
        figure.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="markers",
                name=system_id,
                marker={"color": color, "size": 8},
                customdata=ids,
                hovertemplate=(
                    "%{customdata}<br>x=%{x:.6g}"
                    "<br>signed error=%{y:.3%}<extra></extra>"
                ),
            )
        )
        plotted += len(ids)
    if x_kind == "temperature":
        x_title = "Specified temperature (K)"
    elif x_kind == "pressure":
        x_title = "Reference pressure (MPa)"
    else:
        x_title = f"Specified methane mole fraction ({phase_label.lower()} input)"
    _layout(figure, x_title, "Signed relative pressure error (%)")
    figure.update_yaxes(tickformat=".1%")
    label = capability.value.replace("_", " ").title()
    aggregate = next(
        item
        for item in production.pooled_coverage
        if item.grouping_key.capability is capability
        and item.grouping_key.comparison_key.quantity is ValidationQuantity.PRESSURE
    )
    coverage = aggregate.coverage
    return ReportFigure(
        f"figure-{family.lower()}-{capability.value.lower()}",
        family,
        f"Signed pressure error vs {x_kind} — {label}",
        (
            f"{plotted} defined-error points plotted; C coverage records "
            f"{coverage.compared_cases} compared of {coverage.total_cases} total cases."
        ),
        figure,
    )


def _composition_parity(
    production: ProductionEvidence, capability: CapabilityUnderTest
) -> ReportFigure:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots  # type: ignore[import-untyped]

    cases = _case_map(production)
    component_ids = sorted(
        {component for case in production.cases for component in case.component_ids}
    )
    figure = make_subplots(
        rows=1, cols=len(component_ids), subplot_titles=component_ids
    )
    for column, component_id in enumerate(component_ids, start=1):
        for color, system_id in zip(
            _COLORS, sorted({case.system_id for case in production.cases}), strict=False
        ):
            refs: list[float] = []
            preds: list[float] = []
            ids: list[str] = []
            for comparison in production.comparisons:
                if (
                    comparison.capability is not capability
                    or comparison.system_id != system_id
                ):
                    continue
                quantity = _comparison(comparison, ValidationQuantity.MOLE_FRACTION)
                if quantity.comparison_state is not ComparisonState.COMPARED:
                    continue
                case = cases[comparison.case_id]
                if component_id not in case.component_ids:
                    continue
                reference, prediction = _values(case, ValidationQuantity.MOLE_FRACTION)
                assert isinstance(reference, tuple) and isinstance(prediction, tuple)
                component_order = quantity.component_ids or ()
                reference_value = dict(zip(component_order, reference, strict=True))[
                    component_id
                ]
                prediction_value = dict(zip(component_order, prediction, strict=True))[
                    component_id
                ]
                refs.append(reference_value)
                preds.append(prediction_value)
                ids.append(case.case_id)
            if refs:
                figure.add_trace(
                    go.Scatter(
                        x=refs,
                        y=preds,
                        mode="markers",
                        name=system_id,
                        legendgroup=system_id,
                        showlegend=column == 1,
                        marker={"color": color, "size": 8},
                        customdata=ids,
                        hovertemplate="%{customdata}<br>reference=%{x:.6g}<br>prediction=%{y:.6g}<extra></extra>",
                    ),
                    row=1,
                    col=column,
                )
                lower, upper = min((*refs, *preds)), max((*refs, *preds))
                figure.add_trace(
                    go.Scatter(
                        x=[lower, upper],
                        y=[lower, upper],
                        mode="lines",
                        legendgroup="identity",
                        name="identity",
                        showlegend=column == 1,
                        line={"color": "#57666c", "dash": "dash"},
                        hoverinfo="skip",
                    ),
                    row=1,
                    col=column,
                )
    phase = _phase_label(production, capability, ValidationQuantity.MOLE_FRACTION)
    _layout(
        figure,
        f"Reference {phase} mole fraction (1)",
        f"Predicted {phase} mole fraction (1)",
    )
    label = capability.value.replace("_", " ").title()
    return ReportFigure(
        f"figure-f5-{capability.value.lower()}",
        "F5",
        f"Mole-fraction parity — {label}",
        _caption(production, capability, ValidationQuantity.MOLE_FRACTION),
        figure,
    )


def _composition_error(
    production: ProductionEvidence, capability: CapabilityUnderTest
) -> ReportFigure:
    import plotly.graph_objects as go

    cases = _case_map(production)
    figure = go.Figure()
    for color_index, system_id in enumerate(
        sorted({case.system_id for case in production.cases})
    ):
        for dash_index, component_id in enumerate(
            sorted(
                {
                    component
                    for case in production.cases
                    for component in case.component_ids
                }
            )
        ):
            xs: list[float] = []
            ys: list[float] = []
            ids: list[str] = []
            for comparison in production.comparisons:
                if (
                    comparison.capability is not capability
                    or comparison.system_id != system_id
                ):
                    continue
                quantity = _comparison(comparison, ValidationQuantity.MOLE_FRACTION)
                if (
                    quantity.comparison_state is not ComparisonState.COMPARED
                    or component_id not in (quantity.component_ids or ())
                ):
                    continue
                assert quantity.errors is not None and isinstance(
                    quantity.errors.error, tuple
                )
                index = (quantity.component_ids or ()).index(component_id)
                xs.append(_temperature(cases[comparison.case_id]))
                ys.append(quantity.errors.error[index])
                ids.append(comparison.case_id)
            if xs:
                figure.add_trace(
                    go.Scatter(
                        x=xs,
                        y=ys,
                        mode="markers",
                        name=f"{system_id} · {component_id}",
                        marker={
                            "color": _COLORS[color_index % len(_COLORS)],
                            "symbol": "circle" if dash_index == 0 else "diamond",
                            "size": 8,
                        },
                        customdata=ids,
                        hovertemplate=(
                            "%{customdata}<br>T=%{x:.6g} K"
                            "<br>signed error=%{y:.6g}<extra></extra>"
                        ),
                    )
                )
    phase = _phase_label(production, capability, ValidationQuantity.MOLE_FRACTION)
    _layout(
        figure,
        "Specified temperature (K)",
        f"Signed {phase} mole-fraction error (1)",
    )
    label = capability.value.replace("_", " ").title()
    return ReportFigure(
        f"figure-f6-{capability.value.lower()}",
        "F6",
        f"Signed mole-fraction error vs temperature — {label}",
        _caption(production, capability, ValidationQuantity.MOLE_FRACTION),
        figure,
    )


def _solver_outcome(
    production: ProductionEvidence, capability: CapabilityUnderTest
) -> ReportFigure:
    import plotly.graph_objects as go

    figure = go.Figure()
    for color, system_id in zip(
        _COLORS, sorted({case.system_id for case in production.cases}), strict=False
    ):
        selected = [
            case
            for case in production.cases
            if case.capability is capability and case.system_id == system_id
        ]
        figure.add_trace(
            go.Scatter(
                x=[_temperature(case) for case in selected],
                y=[case.solver_outcome.value for case in selected],
                mode="markers",
                name=system_id,
                marker={"color": color, "size": 9},
                customdata=[case.case_id for case in selected],
                hovertemplate=(
                    "%{customdata}<br>T=%{x:.6g} K<br>outcome=%{y}<extra></extra>"
                ),
            )
        )
    _layout(figure, "Specified temperature (K)", "Solver outcome")
    label = capability.value.replace("_", " ").title()
    aggregate = next(
        item
        for item in production.pooled_coverage
        if item.grouping_key.capability is capability
        and item.grouping_key.comparison_key.quantity is ValidationQuantity.PRESSURE
    )
    coverage = aggregate.coverage
    return ReportFigure(
        f"figure-f7-{capability.value.lower()}",
        "F7",
        f"Solver outcome vs temperature — {label}",
        (
            f"{coverage.converged} converged of {coverage.total_cases} total cases; "
            "all outcomes remain visible."
        ),
        figure,
    )


def build_figures(production: ProductionEvidence) -> tuple[ReportFigure, ...]:
    """Build the 14 approved Module 17 figures with deterministic identifiers."""

    figures: list[ReportFigure] = []
    capabilities = (CapabilityUnderTest.BUBBLE_POINT, CapabilityUnderTest.DEW_POINT)
    for capability in capabilities:
        figures.append(_pressure_parity(production, capability))
    for family, x_kind in (
        ("F2", "temperature"),
        ("F3", "pressure"),
        ("F4", "methane fraction"),
    ):
        for capability in capabilities:
            figures.append(_pressure_error(production, capability, family, x_kind))
    for capability in capabilities:
        figures.append(_composition_parity(production, capability))
    for capability in capabilities:
        figures.append(_composition_error(production, capability))
    for capability in capabilities:
        figures.append(_solver_outcome(production, capability))
    return tuple(figures)


def figure_html(figure: ReportFigure) -> str:
    """Serialize a figure without loading Plotly or any resource externally."""

    import plotly.io as pio  # type: ignore[import-untyped]

    fragment = cast(
        str,
        pio.to_html(
            figure.figure,
            include_plotlyjs=False,
            full_html=False,
            div_id=figure.figure_id,
            config={"displaylogo": False, "responsive": True},
        ),
    )
    return fragment


def plotly_javascript() -> str:
    """Return the installed Plotly runtime for one inline script element."""

    from plotly.offline import get_plotlyjs  # type: ignore[import-untyped]

    return re.sub(r"</script", r"<\\/script", get_plotlyjs(), flags=re.IGNORECASE)
