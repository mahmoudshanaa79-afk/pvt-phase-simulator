"""Known-value checks for unit conversion (mutation testing, 2026-11).

Round-trip properties cannot catch a conversion that is wrong in both
directions, or a shortcut that skips conversion between different units. These
fix the conversions to known values.
"""

from __future__ import annotations

import dataclasses

import pytest

from pvt_phase_simulator_ui.units import (
    PressureUnit,
    TemperatureUnit,
    UnitPreferences,
    convert_pressure,
    convert_temperature,
    pressure_from_pa,
    pressure_to_pa,
    temperature_from_k,
    temperature_to_k,
)


@pytest.mark.parametrize(
    ("value_k", "unit", "expected"),
    (
        (300.0, TemperatureUnit.KELVIN, 300.0),
        (200.0, TemperatureUnit.CELSIUS, -73.15),
        (600.0, TemperatureUnit.CELSIUS, 326.85),
        (100.0, TemperatureUnit.FAHRENHEIT, -279.67),
        (300.0, TemperatureUnit.FAHRENHEIT, 80.33),
    ),
)
def test_temperature_from_kelvin(
    value_k: float, unit: TemperatureUnit, expected: float
) -> None:
    assert temperature_from_k(value_k, unit) == pytest.approx(expected, abs=1e-9)
    assert temperature_to_k(expected, unit) == pytest.approx(value_k, abs=1e-9)


@pytest.mark.parametrize(
    ("value", "unit", "pascal"),
    (
        (1.0, PressureUnit.PA, 1.0),
        (1.0, PressureUnit.MPA, 1.0e6),
        (1.0, PressureUnit.BAR, 1.0e5),
        (1.0, PressureUnit.PSI, 6_894.757_293_168),
    ),
)
def test_pressure_to_pascal(value: float, unit: PressureUnit, pascal: float) -> None:
    assert pressure_to_pa(value, unit) == pytest.approx(pascal, rel=1e-15)
    assert pressure_from_pa(pascal, unit) == pytest.approx(value, rel=1e-15)


def test_conversion_between_different_units_is_not_skipped() -> None:
    assert convert_pressure(1.0, "MPa", "bar") == pytest.approx(10.0)
    assert convert_pressure(14.5, "psi", "Pa") == pytest.approx(
        14.5 * 6_894.757_293_168
    )
    assert convert_temperature(0.0, "°C", "°F") == pytest.approx(32.0)
    assert convert_temperature(212.0, "°F", "K") == pytest.approx(373.15)
    assert convert_pressure(7.0, "bar", "bar") == 7.0
    assert convert_temperature(7.0, "K", "K") == 7.0


def test_unknown_units_name_the_supported_ones() -> None:
    with pytest.raises(
        ValueError, match=r"Unsupported pressure unit 'atm'; use Pa, MPa, bar, psi\."
    ):
        pressure_to_pa(1.0, "atm")
    with pytest.raises(
        ValueError, match=r"Unsupported temperature unit 'R'; use K, °C, °F\."
    ):
        temperature_to_k(1.0, "R")
    assert pressure_to_pa(2.0, "bar") == 2.0e5


def test_unit_preferences_are_immutable_and_slotted() -> None:
    preferences = UnitPreferences()
    with pytest.raises(dataclasses.FrozenInstanceError):
        preferences.pressure = PressureUnit.PA  # type: ignore[misc]
    assert not hasattr(preferences, "__dict__")
