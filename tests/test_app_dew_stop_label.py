"""Neutral wording for the standard trace's dew stop marker (proposal P5).

On the default case the standard dew branch stops at the cricondentherm, not at the
critical point, but the engine labels the marker "Dew Near-critical termination".
The application relabels it; the engine's own label is not touched.
"""

from __future__ import annotations

import inspect

from pvt_phase_simulator.eos.phase_envelope import (
    EnvelopeContinuationSettings,
    calculate_phase_envelope,
)
from pvt_phase_simulator.plotting import (
    PhaseBehaviorPoint,
    PhaseEnvelopePlotData,
    plot_phase_envelope,
)
from pvt_phase_simulator_ui import views
from pvt_phase_simulator_ui.adapters import validate_scientific_inputs
from pvt_phase_simulator_ui.views import (
    DEW_STOP_MARKER_NAME,
    ENGINE_DEW_STOP_MARKER_NAME,
    _neutral_dew_stop_label,
)

#: The cricondentherm of the default 50/50 methane/propane dew curve
#: (docs/DEW_INVESTIGATION.md): the standard trace stops near here, not at the
#: certified critical point (321.58 K, 8.534 MPa).
CRICONDENTHERM_K = 329.15


def _envelope(*, bubble: str, dew: str) -> PhaseEnvelopePlotData:
    return PhaseEnvelopePlotData(
        bubble_points=(
            PhaseBehaviorPoint(280.0, 4.0e6),
            PhaseBehaviorPoint(300.0, 6.0e6),
        ),
        dew_points=(
            PhaseBehaviorPoint(280.0, 2.0e6),
            PhaseBehaviorPoint(300.0, 5.0e6),
        ),
        component_names=("Methane", "Propane"),
        composition=(0.5, 0.5),
        bubble_termination=bubble,
        dew_termination=dew,
    )


def _names(figure: object) -> tuple[str, ...]:
    return tuple(str(trace.name) for trace in figure.data)  # type: ignore[attr-defined]


def test_the_engine_still_uses_the_label_the_app_replaces() -> None:
    figure = plot_phase_envelope(_envelope(bubble="near_critical", dew="near_critical"))

    assert ENGINE_DEW_STOP_MARKER_NAME in _names(figure)


def test_the_dew_stop_marker_says_what_happened() -> None:
    figure = plot_phase_envelope(_envelope(bubble="near_critical", dew="near_critical"))
    before = {trace.name: (tuple(trace.x), tuple(trace.y)) for trace in figure.data}

    result = _neutral_dew_stop_label(figure)

    assert result is figure
    names = _names(figure)
    assert DEW_STOP_MARKER_NAME in names
    assert ENGINE_DEW_STOP_MARKER_NAME not in names
    marker = next(trace for trace in figure.data if trace.name == DEW_STOP_MARKER_NAME)
    assert marker.hovertemplate.startswith(DEW_STOP_MARKER_NAME)
    assert ENGINE_DEW_STOP_MARKER_NAME not in marker.hovertemplate
    assert "critical point" not in DEW_STOP_MARKER_NAME.lower()
    # The marker's position and every other trace are unchanged.
    assert (tuple(marker.x), tuple(marker.y)) == before[ENGINE_DEW_STOP_MARKER_NAME]
    assert len(figure.data) == len(before)
    for trace in figure.data:
        if trace.name != DEW_STOP_MARKER_NAME:
            assert (tuple(trace.x), tuple(trace.y)) == before[trace.name]


def test_the_bubble_marker_and_other_dew_stops_are_left_alone() -> None:
    figure = plot_phase_envelope(_envelope(bubble="near_critical", dew="branch_lost"))
    before = _names(figure)

    _neutral_dew_stop_label(figure)

    assert _names(figure) == before
    assert "Bubble Near-critical termination" in before
    assert "Dew Branch-lost termination" in before


def test_the_relabelling_is_idempotent() -> None:
    figure = plot_phase_envelope(_envelope(bubble="near_critical", dew="near_critical"))

    first = _names(_neutral_dew_stop_label(figure))
    second = _names(_neutral_dew_stop_label(figure))

    assert first == second


def test_the_standard_default_dew_branch_stops_at_the_cricondentherm() -> None:
    """Real engine, the app's own settings: the marker is not at a critical point."""

    inputs = validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 5.0e6)
    start_temperature_k = inputs.temperature_k - 30.0
    settings = EnvelopeContinuationSettings(
        target_temperature_k=inputs.temperature_k + 30.0,
        initial_temperature_step_k=5.0,
        maximum_points=15,
    )
    result = calculate_phase_envelope(
        inputs.mixture(), settings, settings, start_temperature_k, start_temperature_k
    )
    assert result.dew_branch.termination_reason.value == "near_critical"

    figure = _neutral_dew_stop_label(plot_phase_envelope(result))

    marker = next(trace for trace in figure.data if trace.name == DEW_STOP_MARKER_NAME)
    assert abs(marker.x[0] - CRICONDENTHERM_K) < 3.0
    assert ENGINE_DEW_STOP_MARKER_NAME not in _names(figure)


def test_the_phase_envelope_view_relabels_the_figure_it_builds() -> None:
    source = inspect.getsource(views.render_phase_envelope)

    assert "_neutral_dew_stop_label(" in source
    assert source.index("_neutral_dew_stop_label(") < source.index(
        "_presentation_figure("
    )
