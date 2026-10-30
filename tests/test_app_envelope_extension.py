"""The display-only envelope extension through the engine's turning points."""

from __future__ import annotations

import plotly.graph_objects as go  # type: ignore[import-untyped]
import pytest

from pvt_phase_simulator_ui.adapters import validate_scientific_inputs
from pvt_phase_simulator_ui.envelope_extension import (
    BUBBLE_TRACE_NAME,
    DEW_TRACE_NAME,
    NEAR_CRITICAL,
    PRESSURE_TURNING_TRACE_NAME,
    ExtendedEnvelope,
    add_extended_branches,
    describe_branch,
    trace_extended_envelope,
)
from pvt_phase_simulator_ui.state import INPUT_EXAMPLES
from pvt_phase_simulator_ui.units import (
    PressureUnit,
    TemperatureUnit,
    UnitPreferences,
    pressure_from_pa,
    temperature_from_k,
)
from pvt_phase_simulator_ui.views import _presentation_figure

#: The audited, certified critical point of the default 50/0/50 mixture, recorded as
#: the shipped "Audited critical-solver seed" example.
CERTIFIED_TEMPERATURE_K = INPUT_EXAMPLES[2].temperature_k
CERTIFIED_PRESSURE_PA = INPUT_EXAMPLES[2].pressure_pa


def _mixture(composition: tuple[float, float, float], temperature_k: float):
    return validate_scientific_inputs(composition, temperature_k, 5.0e6).mixture()


@pytest.fixture(scope="module")
def default_extension() -> ExtendedEnvelope:
    return trace_extended_envelope(_mixture((50.0, 0.0, 50.0), 300.0), 300.0)


def test_default_case_reaches_the_near_critical_region_on_both_branches(
    default_extension: ExtendedEnvelope,
) -> None:
    assert default_extension.bubble.reached_critical_region
    assert default_extension.dew.reached_critical_region
    assert default_extension.both_reached_critical_region
    for branch in (default_extension.bubble, default_extension.dew):
        end = branch.points[-1]
        # Ending near the certified critical point is evidence, not a definition of
        # it; the bounds are generous on purpose and independent of the extension.
        assert abs(end.temperature_k - CERTIFIED_TEMPERATURE_K) < 3.0
        assert abs(end.pressure_pa - CERTIFIED_PRESSURE_PA) < 0.2e6


def test_the_extension_passes_the_cricondenbar_that_the_standard_trace_cannot(
    default_extension: ExtendedEnvelope,
) -> None:
    bubble = default_extension.bubble.points
    peak = max(point.pressure_pa for point in bubble)
    # The standard natural-temperature trace stops at 307 K / 8.79 MPa. The extension
    # continues past the pressure maximum and turns back toward lower pressure.
    assert peak > 8.7e6
    assert bubble[-1].pressure_pa < peak
    assert any(point.pressure_turning_point for point in bubble)
    assert any(
        point.temperature_turning_point for point in default_extension.dew.points
    )


def test_a_branch_that_stops_early_is_reported_and_never_called_closed() -> None:
    # 70/30 methane/propane: the bubble branch ends in the engine's trivial-state
    # guard near 9.9 MPa, a cause unrelated to cubic root counts. (Ethane/propane
    # 30/70 used to stop early here; root-count-tolerant continuity, P1, closes it.)
    extension = trace_extended_envelope(_mixture((70.0, 0.0, 30.0), 270.0), 270.0)

    assert not extension.both_reached_critical_region
    stopped = [
        branch
        for branch in (extension.bubble, extension.dew)
        if branch.termination_reason != NEAR_CRITICAL
    ]
    assert stopped
    for branch in stopped:
        status, detail = describe_branch(branch)
        assert not branch.reached_critical_region
        assert branch.termination_reason.replace("_", " ") in status.lower()
        assert "near-critical guard" not in status
        assert detail


def test_a_rejected_start_is_recorded_without_raising() -> None:
    extension = trace_extended_envelope(_mixture((50.0, 0.0, 50.0), 300.0), 20.0)

    assert extension.bubble.points == ()
    assert extension.bubble.attempts[0].termination_reason == "start_rejected"
    status, detail = describe_branch(extension.bubble)
    assert status.startswith("Not extended")
    assert "20" in detail or "-10" in detail
    assert not extension.both_reached_critical_region


def test_the_number_of_engine_attempts_is_bounded(
    default_extension: ExtendedEnvelope,
) -> None:
    assert len(default_extension.bubble.attempts) == 1
    assert 1 <= len(default_extension.dew.attempts) <= 3
    for branch in (default_extension.bubble, default_extension.dew):
        assert len(branch.points) <= 60


def test_the_extension_is_deterministic(default_extension: ExtendedEnvelope) -> None:
    again = trace_extended_envelope(_mixture((50.0, 0.0, 50.0), 300.0), 300.0)

    assert again == default_extension


def test_overlay_is_added_in_si_and_converted_with_every_other_trace(
    default_extension: ExtendedEnvelope,
) -> None:
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=(300.0,), y=(5.0e6,), name="standard branch"))
    add_extended_branches(figure, default_extension)

    names = [trace.name for trace in figure.data]
    assert BUBBLE_TRACE_NAME in names
    assert DEW_TRACE_NAME in names
    assert PRESSURE_TURNING_TRACE_NAME in names
    bubble_trace = next(
        trace for trace in figure.data if trace.name == BUBBLE_TRACE_NAME
    )
    first = default_extension.bubble.points[0]
    assert bubble_trace.x[0] == first.temperature_k
    assert bubble_trace.y[0] == first.pressure_pa

    units = UnitPreferences(TemperatureUnit.FAHRENHEIT, PressureUnit.PSI)
    converted = _presentation_figure(
        figure, units, x_quantity="temperature", y_quantity="pressure"
    )
    bubble_trace = next(
        trace for trace in converted.data if trace.name == BUBBLE_TRACE_NAME
    )
    assert bubble_trace.x[0] == pytest.approx(
        temperature_from_k(first.temperature_k, units.temperature)
    )
    assert bubble_trace.y[0] == pytest.approx(
        pressure_from_pa(first.pressure_pa, units.pressure)
    )
    assert "°F" in bubble_trace.hovertemplate
    assert "psi" in bubble_trace.hovertemplate


def test_turning_points_are_labelled_as_not_critical_points(
    default_extension: ExtendedEnvelope,
) -> None:
    figure = add_extended_branches(go.Figure(), default_extension)

    marker = next(
        trace for trace in figure.data if trace.name == PRESSURE_TURNING_TRACE_NAME
    )
    assert "not a critical point" in marker.hovertemplate


def test_a_branch_without_points_adds_no_trace() -> None:
    extension = trace_extended_envelope(_mixture((50.0, 0.0, 50.0), 300.0), 20.0)

    figure = add_extended_branches(go.Figure(), extension)

    assert BUBBLE_TRACE_NAME not in [trace.name for trace in figure.data]


def test_the_legend_moves_below_the_axes_when_the_overlay_is_shown(
    default_extension: ExtendedEnvelope,
) -> None:
    figure = add_extended_branches(go.Figure(), default_extension)

    assert figure.layout.legend.y < 0
    assert figure.layout.legend.yanchor == "top"
