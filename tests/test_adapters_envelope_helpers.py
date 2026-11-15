"""Envelope-location and error helpers of the app adapters, pinned exactly.

Mutation testing of ``adapters.py`` (November 2026) showed that the
operating-point helpers were only checked on one or two easy cases. These tests
pin the interpolation (order, endpoints, ignored points), every branch of the
location message, and the error helpers' edges.
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any

import pytest

from pvt_phase_simulator_ui.adapters import (
    location_relative_to_envelope,
    relative_pressure_error_percent,
    status_text,
    validation_pressure_error_summary,
)


def _point(temperature_k: float, pressure_pa: float, status: str = "converged") -> Any:
    return SimpleNamespace(
        temperature_k=temperature_k, pressure_pa=pressure_pa, status=status
    )


def _envelope(
    bubble: tuple[Any, ...] = (),
    dew: tuple[Any, ...] = (),
    bubble_message: str = "Bubble stopped.",
    dew_message: str = "Dew stopped.",
) -> Any:
    return SimpleNamespace(
        bubble_branch=SimpleNamespace(
            points=bubble, termination_message=bubble_message
        ),
        dew_branch=SimpleNamespace(points=dew, termination_message=dew_message),
    )


def _where(envelope: Any, temperature_k: float, pressure_pa: float) -> str:
    return location_relative_to_envelope(envelope, temperature_k, pressure_pa)


# Bubble 4 -> 6 MPa between 290 and 310 K (5 MPa at 300 K);
# dew 2 -> 3 MPa (2.5 MPa at 300 K). Points are given out of order.
BUBBLE = (_point(310.0, 6.0e6), _point(290.0, 4.0e6))
DEW = (_point(310.0, 3.0e6), _point(290.0, 2.0e6))


def test_without_an_envelope_the_location_is_unavailable() -> None:
    assert (
        location_relative_to_envelope(None, 300.0, 1e6)
        == "Unavailable until a phase envelope has been calculated."
    )


@pytest.mark.parametrize(
    ("pressure_pa", "expected"),
    (
        (2.4e6, "Below both interpolated saturation branches."),
        (2.5e6, "Inside the interpolated two-phase envelope."),
        (3.0e6, "Inside the interpolated two-phase envelope."),
        (5.0e6, "Inside the interpolated two-phase envelope."),
        (5.1e6, "Above both interpolated saturation branches."),
    ),
)
def test_both_branches_bound_the_two_phase_region_inclusively(
    pressure_pa: float, expected: str
) -> None:
    assert _where(_envelope(BUBBLE, DEW), 300.0, pressure_pa) == expected
    # The order of the branches does not matter: the region is between them.
    assert _where(_envelope(DEW, BUBBLE), 300.0, pressure_pa) == expected


@pytest.mark.parametrize(
    ("pressure_pa", "relation"),
    ((4.9e6, "Below"), (5.0e6, "On"), (5.1e6, "Above")),
)
def test_a_single_bubble_branch_is_compared_exactly(
    pressure_pa: float, relation: str
) -> None:
    message = _where(_envelope(BUBBLE, (), dew_message="No dew."), 300.0, pressure_pa)
    assert message == (
        f"{relation} the interpolated bubble branch. Dew branch unavailable: No dew."
    )


@pytest.mark.parametrize(
    ("pressure_pa", "relation"),
    ((2.4e6, "Below"), (2.5e6, "On"), (2.6e6, "Above")),
)
def test_a_single_dew_branch_is_compared_exactly(
    pressure_pa: float, relation: str
) -> None:
    message = _where(
        _envelope((), DEW, bubble_message="No bubble."), 300.0, pressure_pa
    )
    assert message == (
        f"{relation} the interpolated dew branch. Bubble branch unavailable: No bubble."
    )


def test_no_branch_at_the_temperature_names_both_engine_reasons() -> None:
    message = _where(_envelope(BUBBLE, DEW, "B reason.", "D reason."), 320.0, 3e6)
    assert message == (
        "No interpolated branch is available at this temperature. "
        "Bubble branch: B reason. Dew branch: D reason."
    )


@pytest.mark.parametrize("temperature_k", (290.0, 310.0))
def test_the_branch_end_temperatures_are_inside_the_interpolation(
    temperature_k: float,
) -> None:
    pressure = 4.0e6 if temperature_k == 290.0 else 6.0e6
    message = _where(_envelope(BUBBLE, ()), temperature_k, pressure)
    assert message.startswith("On the interpolated bubble branch.")


def test_the_interpolation_weight_is_linear_in_temperature() -> None:
    # 295 K is a quarter of the way: 4 + 0.25 * 2 = 4.5 MPa.
    assert _where(_envelope(BUBBLE, ()), 295.0, 4.5e6).startswith("On the")
    assert _where(_envelope(BUBBLE, ()), 295.0, 4.5e6 * (1 + 1e-12)).startswith(
        "Above the"
    )
    assert _where(_envelope(BUBBLE, ()), 295.0, 4.5e6 * (1 - 1e-12)).startswith(
        "Below the"
    )


def test_points_that_did_not_converge_are_ignored() -> None:
    bubble = (*BUBBLE, _point(300.0, 9.0e6, status="corrector_failed"))
    assert _where(_envelope(bubble, ()), 300.0, 5.0e6).startswith("On the")
    lonely = (_point(300.0, 9.0e6, status="rejected"),)
    assert _where(_envelope(lonely, ()), 300.0, 9.0e6).startswith(
        "No interpolated branch"
    )


def test_a_single_converged_point_answers_only_at_its_own_temperature() -> None:
    single = (_point(300.0, 5.0e6),)
    assert _where(_envelope(single, ()), 300.0, 5.0e6).startswith("On the")
    assert _where(_envelope(single, ()), 300.5, 5.0e6).startswith("No interpolated")


def test_the_relative_pressure_error_and_its_refusals() -> None:
    assert relative_pressure_error_percent(102.0, 100.0) == pytest.approx(2.0)
    assert relative_pressure_error_percent(98.0, 100.0) == pytest.approx(-2.0)
    for bad in (math.inf, -math.inf, math.nan):
        with pytest.raises(ValueError, match="pressures must be finite"):
            relative_pressure_error_percent(bad, 100.0)
        with pytest.raises(ValueError, match="pressures must be finite"):
            relative_pressure_error_percent(100.0, bad)
    for experimental in (0.0, -1.0):
        with pytest.raises(ValueError, match="experimental pressure must be positive"):
            relative_pressure_error_percent(1.0, experimental)


def test_the_validation_error_summary() -> None:
    records = [
        SimpleNamespace(bubble_pressure_relative_error=value)
        for value in (0.01, -0.03, None, 0.02)
    ]
    count, available, median, largest = validation_pressure_error_summary(
        records,  # type: ignore[arg-type]
        "bubble",
    )
    assert (count, available) == (4, 3)
    assert median == pytest.approx(2.0)
    assert largest == pytest.approx(3.0)
    empty = [SimpleNamespace(dew_pressure_relative_error=None)] * 2
    assert validation_pressure_error_summary(empty, "dew") == (2, 0, None, None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="direction must be 'bubble' or 'dew'"):
        validation_pressure_error_summary([], "flash")


def test_status_text_reads_enum_values_and_plain_strings() -> None:
    assert status_text(SimpleNamespace(value="two_phase")) == "Two phase"
    assert status_text("near_critical") == "Near critical"
    assert status_text(3) == "3"


def test_a_retrograde_branch_is_interpolated_in_temperature_order() -> None:
    # Pressure falls as temperature rises; given out of order.
    falling = (_point(310.0, 4.0e6), _point(290.0, 6.0e6))
    assert _where(_envelope(falling, ()), 295.0, 5.5e6).startswith("On the")
    assert _where(_envelope(falling, ()), 305.0, 4.5e6).startswith("On the")


def test_below_the_branch_range_there_is_no_interpolation() -> None:
    message = _where(_envelope(BUBBLE, DEW), 280.0, 3e6)
    assert message.startswith("No interpolated branch is available")


def test_a_wide_bracket_uses_the_offset_from_its_left_end() -> None:
    wide = (_point(100.0, 1.0e6), _point(300.0, 3.0e6))
    assert _where(_envelope(wide, ()), 250.0, 2.5e6).startswith("On the")


def test_points_at_the_same_temperature_never_divide_by_zero() -> None:
    # A distinct but equal float, as two separate engine results would give.
    repeated = (
        _point(290.0, 4.0e6),
        _point(float("290"), 4.2e6),
        _point(310.0, 6.0e6),
    )
    assert _where(_envelope(repeated, ()), 290.0, 4.2e6).startswith("On the")


def test_a_lone_point_matches_an_equal_temperature_value() -> None:
    single = (_point(300.0, 5.0e6),)
    assert _where(_envelope(single, ()), float("300"), 5.0e6).startswith("On the")


def test_the_relative_error_is_not_rounded() -> None:
    assert relative_pressure_error_percent(101.5, 100.0) == pytest.approx(1.5)
    assert relative_pressure_error_percent(98.5, 100.0) == pytest.approx(-1.5)


def test_a_small_positive_experimental_pressure_is_accepted() -> None:
    assert relative_pressure_error_percent(1.0, 0.5) == pytest.approx(100.0)
