"""Input validation, kij and view helpers of the app adapters, pinned exactly.

Mutation testing of ``adapters.py`` (November 2026) left these behaviours
unchecked: a kij that is only negative, the exact refusal messages and range
texts per unit, the keyword-only options, immutable views, and which critical
fields are shown for a result that is not certified.
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace
from typing import Any

import pytest

from pvt_phase_simulator.eos.critical_point import CriticalPointStatus
from pvt_phase_simulator_ui.adapters import (
    COMPONENT_NAMES,
    CriticalView,
    FlashView,
    InputValidationError,
    ScientificInputs,
    adapt_critical_result,
    binary_interaction_assumption,
    run_validated_flash,
    validate_scientific_inputs,
)

FEED = (40.0, 30.0, 30.0)


def _refused(message: str, *args: Any, **kwargs: Any) -> None:
    with pytest.raises(InputValidationError) as refused:
        validate_scientific_inputs(*args, **kwargs)
    assert str(refused.value) == message


def test_a_kij_that_is_only_negative_is_used_and_stated() -> None:
    inputs = validate_scientific_inputs(FEED, 300.0, 5.0, kij=(0.0, 0.0, -0.003))
    assert inputs.uses_kij
    # Every pair present in the mixture is given, the unset ones as 0.
    assert inputs.binary_interactions() == {
        ("Methane", "Ethane"): 0.0,
        ("Ethane", "Methane"): 0.0,
        ("Methane", "Propane"): 0.0,
        ("Propane", "Methane"): 0.0,
        ("Ethane", "Propane"): -0.003,
        ("Propane", "Ethane"): -0.003,
    }
    assert inputs.binary_interaction_assumption == (
        "user-supplied kij: C1–C2 = +0, C1–C3 = +0, C2–C3 = -0.003"
    )
    assert (
        binary_interaction_assumption((0.4, 0.3, 0.3), (-0.01, 0.0, 0.0))
        == "user-supplied kij: C1–C2 = -0.01, C1–C3 = +0, C2–C3 = +0"
    )


def test_each_kij_goes_to_its_own_component_pair() -> None:
    inputs = validate_scientific_inputs(FEED, 300.0, 5.0, kij=(0.01, 0.02, 0.03))
    names = COMPONENT_NAMES
    assert inputs.binary_interactions() == {
        (names[0], names[1]): 0.01,
        (names[1], names[0]): 0.01,
        (names[0], names[2]): 0.02,
        (names[2], names[0]): 0.02,
        (names[1], names[2]): 0.03,
        (names[2], names[1]): 0.03,
    }
    assert names == ("Methane", "Ethane", "Propane")


def test_the_refusal_messages() -> None:
    _refused(
        "Composition total must be greater than zero. Enter a positive mol % for "
        "at least one component.",
        (0.0, 0.0, 0.0),
        300.0,
        5.0,
    )
    _refused("Temperature must be above absolute zero.", FEED, -5.0, 5.0)
    _refused("Temperature must be above absolute zero.", FEED, 0.0, 5.0)
    _refused("Pressure must be positive.", FEED, 300.0, -1.0)
    _refused("Pressure must be positive.", FEED, 300.0, 0.0)
    _refused(
        "Exactly three kij values are required.",
        FEED,
        300.0,
        5.0,
        kij=(0.0, 0.0, 0.0, 0.0),
    )
    _refused("Exactly three kij values are required.", FEED, 300.0, 5.0, kij=(0.0,))


@pytest.mark.parametrize(
    ("unit", "value", "text"),
    (
        ("K", 10.0, "50 K and 1000 K"),
        ("°C", -250.0, "50 K and 1000 K (-223.15 °C to 726.85 °C)"),
        ("°F", -450.0, "50 K and 1000 K (-369.67 °F to 1340.33 °F)"),
    ),
)
def test_the_temperature_range_text_per_unit(
    unit: str, value: float, text: str
) -> None:
    _refused(
        f"Temperature must be between {text}, the application's supported input range.",
        FEED,
        value,
        5.0,
        temperature_unit=unit,
        supported_range=True,
    )


@pytest.mark.parametrize(
    ("unit", "value", "text"),
    (
        ("Pa", 2.0e9, "1 Pa and 1e+09 Pa"),
        ("MPa", 2.0e3, "1 Pa and 1e+09 Pa (1e-06 MPa to 1000 MPa)"),
        ("bar", 2.0e4, "1 Pa and 1e+09 Pa (1e-05 bar to 10000 bar)"),
    ),
)
def test_the_pressure_range_text_per_unit(unit: str, value: float, text: str) -> None:
    _refused(
        f"Pressure must be between {text}, the application's supported input range.",
        FEED,
        300.0,
        value,
        pressure_unit=unit,
        supported_range=True,
    )


def test_units_and_options_are_keyword_only() -> None:
    with pytest.raises(TypeError):
        validate_scientific_inputs(FEED, 300.0, 5.0, "K")  # type: ignore[misc]
    with pytest.raises(TypeError):
        run_validated_flash(FEED, 300.0, 5.0, "K")  # type: ignore[misc]


def test_inputs_and_views_are_immutable_and_slotted() -> None:
    inputs = validate_scientific_inputs(FEED, 300.0, 5.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        inputs.temperature_k = 1.0  # type: ignore[misc]
    for cls in (ScientificInputs, FlashView, CriticalView):
        params = cls.__dataclass_params__  # type: ignore[attr-defined]
        assert params.frozen, cls
        assert "__slots__" in cls.__dict__, cls
    assert not hasattr(inputs, "__dict__")


def _critical(status: CriticalPointStatus) -> Any:
    return SimpleNamespace(
        status=status,
        temperature_k=321.5,
        pressure_pa=8.5e6,
        lambda_min=1e-12,
        cubic_coefficient=0.25,
        scaled_residual_norm=1e-13,
        critical_direction=(0.6, 0.0, -0.8),
        iterations=4,
        termination_reason="reason",
        jacobian_condition_history=(10.0,),
    )


def test_only_a_converged_critical_point_shows_its_values() -> None:
    certified = adapt_critical_result(_critical(CriticalPointStatus.CONVERGED))
    assert certified.certified
    assert (
        certified.temperature_k,
        certified.pressure_pa,
        certified.lambda_min,
        certified.cubic_coefficient,
        certified.scaled_residual_norm,
        certified.critical_direction,
    ) == (321.5, 8.5e6, 1e-12, 0.25, 1e-13, (0.6, 0.0, -0.8))
    for status in CriticalPointStatus:
        if status is CriticalPointStatus.CONVERGED:
            continue
        view = adapt_critical_result(_critical(status))
        assert not view.certified, status
        assert (
            view.temperature_k,
            view.pressure_pa,
            view.lambda_min,
            view.cubic_coefficient,
            view.scaled_residual_norm,
            view.critical_direction,
        ) == (None,) * 6, status
        assert (view.iterations, view.termination_reason) == (4, "reason")
        assert view.jacobian_condition_history == (10.0,)


def test_an_unknown_unit_falls_back_to_the_base_unit_range() -> None:
    from pvt_phase_simulator_ui.adapters import _pressure_bounds, _temperature_bounds

    assert _temperature_bounds("furlong") == "50 K and 1000 K"
    assert _pressure_bounds("furlong") == "1 Pa and 1e+09 Pa"


def test_exactly_three_composition_values_are_accepted() -> None:
    message = "Exactly Methane, Ethane, and Propane are required."
    _refused(message, (40.0, 30.0, 30.0, 0.0), 300.0, 5.0)
    _refused(message, (50.0, 50.0), 300.0, 5.0)
