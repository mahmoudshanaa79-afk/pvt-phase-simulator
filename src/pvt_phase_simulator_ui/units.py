"""Physical-unit conversions at the application boundary.

The scientific package accepts and returns SI values.  This module is the only
place where the UI translates pressure or temperature between a user's chosen
field unit and that SI contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from typing import Final


class PressureUnit(StrEnum):
    """Pressure units supported by the application boundary."""

    PA = "Pa"
    MPA = "MPa"
    BAR = "bar"
    PSI = "psi"


class TemperatureUnit(StrEnum):
    """Temperature units supported by the application boundary."""

    KELVIN = "K"
    CELSIUS = "°C"
    FAHRENHEIT = "°F"


PRESSURE_UNITS: Final = tuple(PressureUnit)
TEMPERATURE_UNITS: Final = tuple(TemperatureUnit)

# The SI definitions of bar and psi.  The psi factor follows from the exact
# definitions of the international avoirdupois pound and the inch.
PA_PER_PRESSURE_UNIT: Final[dict[PressureUnit, float]] = {
    PressureUnit.PA: 1.0,
    PressureUnit.MPA: 1.0e6,
    PressureUnit.BAR: 1.0e5,
    PressureUnit.PSI: 6_894.757_293_168,
}


def _finite_conversion(value: float, quantity: str) -> float:
    if not isfinite(value):
        raise ValueError(f"{quantity} is outside the supported numeric range.")
    return value


def _pressure_unit(unit: PressureUnit | str) -> PressureUnit:
    try:
        return unit if isinstance(unit, PressureUnit) else PressureUnit(unit)
    except ValueError as error:
        supported = ", ".join(item.value for item in PRESSURE_UNITS)
        raise ValueError(
            f"Unsupported pressure unit {unit!r}; use {supported}."
        ) from error


def _temperature_unit(unit: TemperatureUnit | str) -> TemperatureUnit:
    try:
        return unit if isinstance(unit, TemperatureUnit) else TemperatureUnit(unit)
    except ValueError as error:
        supported = ", ".join(item.value for item in TEMPERATURE_UNITS)
        raise ValueError(
            f"Unsupported temperature unit {unit!r}; use {supported}."
        ) from error


def pressure_to_pa(value: float, unit: PressureUnit | str) -> float:
    """Convert one pressure value from ``unit`` to the engine's Pa boundary."""

    numeric = float(value)
    if not isfinite(numeric):
        raise ValueError("Pressure must be finite.")
    converted = numeric * PA_PER_PRESSURE_UNIT[_pressure_unit(unit)]
    return _finite_conversion(converted, "Pressure")


def pressure_from_pa(value_pa: float, unit: PressureUnit | str) -> float:
    """Convert one engine pressure in Pa to a selected presentation unit."""

    numeric = float(value_pa)
    if not isfinite(numeric):
        raise ValueError("Pressure must be finite.")
    converted = numeric / PA_PER_PRESSURE_UNIT[_pressure_unit(unit)]
    return _finite_conversion(converted, "Pressure")


def temperature_to_k(value: float, unit: TemperatureUnit | str) -> float:
    """Convert one absolute temperature from ``unit`` to kelvin."""

    numeric = float(value)
    if not isfinite(numeric):
        raise ValueError("Temperature must be finite.")
    selected = _temperature_unit(unit)
    if selected is TemperatureUnit.KELVIN:
        return numeric
    if selected is TemperatureUnit.CELSIUS:
        converted = numeric + 273.15
    else:
        converted = (numeric + 459.67) * (5.0 / 9.0)
    return _finite_conversion(converted, "Temperature")


def temperature_from_k(value_k: float, unit: TemperatureUnit | str) -> float:
    """Convert one engine temperature in kelvin to a presentation unit."""

    numeric = float(value_k)
    if not isfinite(numeric):
        raise ValueError("Temperature must be finite.")
    selected = _temperature_unit(unit)
    if selected is TemperatureUnit.KELVIN:
        return numeric
    if selected is TemperatureUnit.CELSIUS:
        converted = numeric - 273.15
    else:
        converted = numeric * (9.0 / 5.0) - 459.67
    return _finite_conversion(converted, "Temperature")


def convert_pressure(
    value: float, from_unit: PressureUnit | str, to_unit: PressureUnit | str
) -> float:
    """Convert a pressure between two supported application units."""

    source = _pressure_unit(from_unit)
    target = _pressure_unit(to_unit)
    if source is target:
        return float(value)
    return pressure_from_pa(pressure_to_pa(value, source), target)


def convert_temperature(
    value: float, from_unit: TemperatureUnit | str, to_unit: TemperatureUnit | str
) -> float:
    """Convert a temperature between two supported application units."""

    source = _temperature_unit(from_unit)
    target = _temperature_unit(to_unit)
    if source is target:
        return float(value)
    return temperature_from_k(temperature_to_k(value, source), target)


@dataclass(frozen=True, slots=True)
class UnitPreferences:
    """Per-session units used only at UI and export presentation boundaries."""

    temperature: TemperatureUnit = TemperatureUnit.KELVIN
    pressure: PressureUnit = PressureUnit.MPA


DEFAULT_UNITS: Final = UnitPreferences()
