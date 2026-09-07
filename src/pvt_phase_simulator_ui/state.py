"""Per-session result identity and submitted-input state."""

from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass
from math import isfinite
from typing import Any, Final, cast

from pvt_phase_simulator_ui.adapters import ScientificInputs
from pvt_phase_simulator_ui.units import (
    DEFAULT_UNITS,
    PressureUnit,
    TemperatureUnit,
    pressure_from_pa,
    pressure_to_pa,
    temperature_from_k,
    temperature_to_k,
)

RESULT_KEYS: Final = ("flash", "envelope", "critical", "critical_scan", "sweep")


@dataclass(frozen=True)
class InputExample:
    """A documented input-only case for the verified component scope."""

    label: str
    methane_pct: float
    ethane_pct: float
    propane_pct: float
    temperature_k: float
    pressure_pa: float

    @property
    def pressure_mpa(self) -> float:
        return pressure_from_pa(self.pressure_pa, PressureUnit.MPA)


INPUT_EXAMPLES: Final = (
    InputExample(
        label="Default two-phase-oriented case",
        methane_pct=50.0,
        ethane_pct=0.0,
        propane_pct=50.0,
        temperature_k=300.0,
        pressure_pa=5.0e6,
    ),
    InputExample(
        label="Known single-phase case at 300 K and 20 MPa",
        methane_pct=50.0,
        ethane_pct=0.0,
        propane_pct=50.0,
        temperature_k=300.0,
        pressure_pa=20.0e6,
    ),
    InputExample(
        label="Audited critical-solver seed",
        methane_pct=50.0,
        ethane_pct=0.0,
        propane_pct=50.0,
        temperature_k=321.5829183194,
        pressure_pa=8_534_443.23606381,
    ),
)

_DEFAULT_INPUTS: Final = INPUT_EXAMPLES[0]
_DEFAULT_PRESSURE_SWEEP_PA: Final = (1.0e6, 20.0e6)
_DEFAULT_TEMPERATURE_SWEEP_K: Final = (240.0, 340.0)
_DEFAULT_SWEEP_POINTS: Final = 21


def initialize_session(state: MutableMapping[str, Any]) -> None:
    state.setdefault("results", {})
    state.setdefault("result_signatures", {})
    state.setdefault("submitted_inputs", None)
    state.setdefault("current_inputs", None)
    state.setdefault("input_example", None)
    state.setdefault("rendered_input_example", None)
    state.setdefault("methane_pct", _DEFAULT_INPUTS.methane_pct)
    state.setdefault("ethane_pct", _DEFAULT_INPUTS.ethane_pct)
    state.setdefault("propane_pct", _DEFAULT_INPUTS.propane_pct)
    state.setdefault("temperature_k", _DEFAULT_INPUTS.temperature_k)
    state.setdefault("pressure_mpa", _DEFAULT_INPUTS.pressure_mpa)
    state.setdefault("pressure_pa", _DEFAULT_INPUTS.pressure_pa)
    state.setdefault("temperature_unit", DEFAULT_UNITS.temperature.value)
    state.setdefault("pressure_unit", DEFAULT_UNITS.pressure.value)
    state.setdefault("rendered_temperature_unit", DEFAULT_UNITS.temperature.value)
    state.setdefault("rendered_pressure_unit", DEFAULT_UNITS.pressure.value)
    state.setdefault("temperature_value", _DEFAULT_INPUTS.temperature_k)
    state.setdefault("pressure_value", _DEFAULT_INPUTS.pressure_mpa)
    state.setdefault("rendered_temperature_value", state["temperature_value"])
    state.setdefault("rendered_pressure_value", state["pressure_value"])
    state.setdefault("sweep_kind", "pressure")
    state.setdefault("sweep_pressure_start_pa", _DEFAULT_PRESSURE_SWEEP_PA[0])
    state.setdefault("sweep_pressure_end_pa", _DEFAULT_PRESSURE_SWEEP_PA[1])
    state.setdefault("sweep_points_pressure", _DEFAULT_SWEEP_POINTS)
    state.setdefault("sweep_temperature_start_k", _DEFAULT_TEMPERATURE_SWEEP_K[0])
    state.setdefault("sweep_temperature_end_k", _DEFAULT_TEMPERATURE_SWEEP_K[1])
    state.setdefault("sweep_points_temperature", _DEFAULT_SWEEP_POINTS)
    state.setdefault(
        "sweep_start_value",
        pressure_from_pa(
            _DEFAULT_PRESSURE_SWEEP_PA[0], PressureUnit(str(state["pressure_unit"]))
        ),
    )
    state.setdefault(
        "sweep_end_value",
        pressure_from_pa(
            _DEFAULT_PRESSURE_SWEEP_PA[1], PressureUnit(str(state["pressure_unit"]))
        ),
    )
    state.setdefault("sweep_points_value", _DEFAULT_SWEEP_POINTS)
    state.setdefault("rendered_sweep_kind", state["sweep_kind"])
    state.setdefault("rendered_sweep_temperature_unit", state["temperature_unit"])
    state.setdefault("rendered_sweep_pressure_unit", state["pressure_unit"])
    state.setdefault("rendered_sweep_start_value", state["sweep_start_value"])
    state.setdefault("rendered_sweep_end_value", state["sweep_end_value"])
    state.setdefault("rendered_sweep_points_value", state["sweep_points_value"])


def synchronize_sweep_inputs(state: MutableMapping[str, Any]) -> None:
    """Preserve both sweep definitions across kind and presentation changes."""

    initialize_session(state)
    old_kind = str(state["rendered_sweep_kind"])
    old_temperature_unit = TemperatureUnit(
        str(state["rendered_sweep_temperature_unit"])
    )
    old_pressure_unit = PressureUnit(str(state["rendered_sweep_pressure_unit"]))

    start = float(state["sweep_start_value"])
    end = float(state["sweep_end_value"])
    points = state["sweep_points_value"]
    if isfinite(start) and isfinite(end):
        if old_kind == "pressure":
            state["sweep_pressure_start_pa"] = pressure_to_pa(start, old_pressure_unit)
            state["sweep_pressure_end_pa"] = pressure_to_pa(end, old_pressure_unit)
        elif old_kind == "temperature":
            state["sweep_temperature_start_k"] = temperature_to_k(
                start, old_temperature_unit
            )
            state["sweep_temperature_end_k"] = temperature_to_k(
                end, old_temperature_unit
            )
    if isinstance(points, int) and not isinstance(points, bool):
        state[f"sweep_points_{old_kind}"] = points

    new_kind = str(state["sweep_kind"])
    new_temperature_unit = TemperatureUnit(str(state["temperature_unit"]))
    new_pressure_unit = PressureUnit(str(state["pressure_unit"]))
    presentation_changed = (
        old_kind != new_kind
        or old_temperature_unit is not new_temperature_unit
        or old_pressure_unit is not new_pressure_unit
    )
    if presentation_changed:
        if new_kind == "pressure":
            state["sweep_start_value"] = pressure_from_pa(
                float(state["sweep_pressure_start_pa"]), new_pressure_unit
            )
            state["sweep_end_value"] = pressure_from_pa(
                float(state["sweep_pressure_end_pa"]), new_pressure_unit
            )
        elif new_kind == "temperature":
            state["sweep_start_value"] = temperature_from_k(
                float(state["sweep_temperature_start_k"]), new_temperature_unit
            )
            state["sweep_end_value"] = temperature_from_k(
                float(state["sweep_temperature_end_k"]), new_temperature_unit
            )
        state["sweep_points_value"] = state[f"sweep_points_{new_kind}"]

    state["rendered_sweep_kind"] = new_kind
    state["rendered_sweep_temperature_unit"] = new_temperature_unit.value
    state["rendered_sweep_pressure_unit"] = new_pressure_unit.value
    state["rendered_sweep_start_value"] = state["sweep_start_value"]
    state["rendered_sweep_end_value"] = state["sweep_end_value"]
    state["rendered_sweep_points_value"] = state["sweep_points_value"]


def synchronize_unit_inputs(state: MutableMapping[str, Any]) -> None:
    """Keep canonical SI input state authoritative across presentation changes."""

    initialize_session(state)
    old_temperature = TemperatureUnit(str(state["rendered_temperature_unit"]))
    new_temperature = TemperatureUnit(str(state["temperature_unit"]))
    old_pressure = PressureUnit(str(state["rendered_pressure_unit"]))
    new_pressure = PressureUnit(str(state["pressure_unit"]))

    # Capture genuine field edits in their previously rendered units before a
    # presentation-unit callback replaces the widget values.
    temperature_value = float(state["temperature_value"])
    if temperature_value != float(state["rendered_temperature_value"]) and isfinite(
        temperature_value
    ):
        state["temperature_k"] = temperature_to_k(temperature_value, old_temperature)
    pressure_value = float(state["pressure_value"])
    if pressure_value != float(state["rendered_pressure_value"]) and isfinite(
        pressure_value
    ):
        state["pressure_pa"] = pressure_to_pa(pressure_value, old_pressure)

    if old_temperature is not new_temperature:
        state["temperature_value"] = temperature_from_k(
            float(state["temperature_k"]), new_temperature
        )
        state["rendered_temperature_unit"] = new_temperature.value
    if old_pressure is not new_pressure:
        state["pressure_value"] = pressure_from_pa(
            float(state["pressure_pa"]), new_pressure
        )
        state["rendered_pressure_unit"] = new_pressure.value
    state["rendered_temperature_value"] = state["temperature_value"]
    state["rendered_pressure_value"] = state["pressure_value"]
    state["pressure_mpa"] = pressure_from_pa(
        float(state["pressure_pa"]), PressureUnit.MPA
    )
    synchronize_sweep_inputs(state)


def apply_selected_input_example(state: MutableMapping[str, Any]) -> None:
    """Copy a selected example into input state without submitting any work."""

    selected = state.get("input_example")
    example = next((item for item in INPUT_EXAMPLES if item.label == selected), None)
    if example is None:
        return
    state["methane_pct"] = example.methane_pct
    state["ethane_pct"] = example.ethane_pct
    state["propane_pct"] = example.propane_pct
    state["temperature_k"] = example.temperature_k
    state["pressure_mpa"] = example.pressure_mpa
    state["pressure_pa"] = example.pressure_pa
    temperature_unit = TemperatureUnit(
        str(state.get("temperature_unit", DEFAULT_UNITS.temperature.value))
    )
    pressure_unit = PressureUnit(
        str(state.get("pressure_unit", DEFAULT_UNITS.pressure.value))
    )
    temperature_value = temperature_from_k(example.temperature_k, temperature_unit)
    pressure_value = pressure_from_pa(example.pressure_pa, pressure_unit)
    state["temperature_value"] = temperature_value
    state["pressure_value"] = pressure_value
    state["rendered_temperature_value"] = temperature_value
    state["rendered_pressure_value"] = pressure_value


def store_result(
    state: MutableMapping[str, Any],
    name: str,
    value: object,
    inputs: ScientificInputs,
) -> None:
    initialize_session(state)
    state["results"][name] = value
    state["result_signatures"][name] = inputs.signature


def get_result(state: MutableMapping[str, Any], name: str) -> object | None:
    initialize_session(state)
    return cast(dict[str, object], state["results"]).get(name)


def result_is_stale(
    state: MutableMapping[str, Any], name: str, inputs: ScientificInputs | None
) -> bool:
    initialize_session(state)
    if name not in state["results"]:
        return False
    if inputs is None:
        return True
    signatures = cast(
        dict[str, tuple[tuple[float, float, float], float, float]],
        state["result_signatures"],
    )
    return signatures.get(name) != inputs.signature
