"""Versioned, deterministic persistence for validated OpenPhase input cases.

Case files contain application inputs only.  They never contain Python objects,
cached results, or executable content, and loading them does not call a
scientific API.
"""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from dataclasses import dataclass
from math import isfinite
from typing import Any, Final, cast

from pvt_phase_simulator_ui.adapters import (
    COMPONENT_NAMES,
    InputValidationError,
    ScientificInputs,
    validate_scientific_inputs,
)
from pvt_phase_simulator_ui.sweeps import (
    SweepKind,
    SweepValidationError,
    validate_sweep_request,
)
from pvt_phase_simulator_ui.units import (
    PressureUnit,
    TemperatureUnit,
    pressure_from_pa,
    temperature_from_k,
)

CASE_SCHEMA: Final = "openphase.case"
CASE_SCHEMA_VERSION: Final = "1.0.0"


class CaseFileError(ValueError):
    """A case file cannot be safely accepted as valid application input."""


class _DuplicateKeyError(ValueError):
    """JSON object keys must be unique for an unambiguous case document."""


class _NonFiniteJsonNumberError(ValueError):
    """JSON extensions such as NaN and Infinity are not valid case numbers."""


@dataclass(frozen=True, slots=True)
class SweepAxisSettings:
    """Canonical bounds and point count for one engineering sweep axis."""

    start: float
    end: float
    points: int


@dataclass(frozen=True, slots=True)
class OpenPhaseCase:
    """Fully validated application inputs restored by an OpenPhase case file."""

    inputs: ScientificInputs
    temperature_unit: TemperatureUnit
    pressure_unit: PressureUnit
    active_sweep: SweepKind
    pressure_sweep: SweepAxisSettings
    temperature_sweep: SweepAxisSettings


def _schema_error(message: str) -> CaseFileError:
    return CaseFileError(f"Case file schema is invalid: {message}")


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(key)
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> object:
    raise _NonFiniteJsonNumberError(value)


def _object(value: object, path: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise _schema_error(f"{path} must be an object.")
    return cast(dict[str, object], value)


def _exact_keys(value: object, path: str, expected: set[str]) -> dict[str, object]:
    item = _object(value, path)
    actual = set(item)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing:
        raise _schema_error(f"{path} is missing {', '.join(missing)}.")
    if unknown:
        raise _schema_error(f"{path} contains unknown field {', '.join(unknown)}.")
    return item


def _string(value: object, path: str) -> str:
    if not isinstance(value, str):
        raise _schema_error(f"{path} must be a string.")
    return value


def _number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _schema_error(f"{path} must be a number.")
    try:
        numeric = float(value)
    except (OverflowError, TypeError, ValueError) as error:
        raise _schema_error(f"{path} must be a finite number.") from error
    if not isfinite(numeric):
        raise _schema_error(f"{path} must be a finite number.")
    return numeric


def _integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _schema_error(f"{path} must be an integer.")
    try:
        return int(value)
    except (OverflowError, TypeError, ValueError) as error:
        raise _schema_error(f"{path} must be an integer.") from error


def _unit_preferences(
    document: dict[str, object],
) -> tuple[TemperatureUnit, PressureUnit]:
    units = _exact_keys(
        document["presentation_units"],
        "presentation_units",
        {"pressure", "temperature"},
    )
    temperature_text = _string(units["temperature"], "presentation_units.temperature")
    pressure_text = _string(units["pressure"], "presentation_units.pressure")
    try:
        temperature_unit = TemperatureUnit(temperature_text)
    except ValueError as error:
        supported = ", ".join(unit.value for unit in TemperatureUnit)
        raise _schema_error(
            f"presentation_units.temperature must be one of {supported}."
        ) from error
    try:
        pressure_unit = PressureUnit(pressure_text)
    except ValueError as error:
        supported = ", ".join(unit.value for unit in PressureUnit)
        raise _schema_error(
            f"presentation_units.pressure must be one of {supported}."
        ) from error
    return temperature_unit, pressure_unit


def _case_inputs(document: dict[str, object]) -> ScientificInputs:
    inputs = _exact_keys(
        document["inputs"],
        "inputs",
        {"components", "pressure_pa", "temperature_k"},
    )
    raw_components = inputs["components"]
    if not isinstance(raw_components, list):
        raise _schema_error("inputs.components must be an array.")

    composition_by_name: dict[str, float] = {}
    for index, raw_component in enumerate(raw_components):
        path = f"inputs.components[{index}]"
        component = _exact_keys(raw_component, path, {"mole_percent", "name"})
        name = _string(component["name"], f"{path}.name")
        if name not in COMPONENT_NAMES:
            raise _schema_error(f"{path}.name is not a supported component.")
        if name in composition_by_name:
            raise _schema_error(f"inputs.components contains duplicate {name}.")
        composition_by_name[name] = _number(
            component["mole_percent"], f"{path}.mole_percent"
        )

    missing = [name for name in COMPONENT_NAMES if name not in composition_by_name]
    if missing:
        raise _schema_error(
            "inputs.components must contain exactly Methane, Ethane, and Propane."
        )
    if len(composition_by_name) != len(COMPONENT_NAMES):
        raise _schema_error(
            "inputs.components must contain exactly Methane, Ethane, and Propane."
        )

    composition = (
        composition_by_name[COMPONENT_NAMES[0]],
        composition_by_name[COMPONENT_NAMES[1]],
        composition_by_name[COMPONENT_NAMES[2]],
    )
    temperature_k = _number(inputs["temperature_k"], "inputs.temperature_k")
    pressure_pa = _number(inputs["pressure_pa"], "inputs.pressure_pa")
    try:
        return validate_scientific_inputs(
            composition,
            temperature_k,
            pressure_pa,
            temperature_unit=TemperatureUnit.KELVIN,
            pressure_unit=PressureUnit.PA,
        )
    except InputValidationError as error:
        # Preserve the manual-entry validation message, including the explicit
        # promise that invalid composition is not normalized.
        raise CaseFileError(str(error)) from error


def _axis_settings(sweeps: dict[str, object], kind: SweepKind) -> SweepAxisSettings:
    suffix = "pa" if kind == "pressure" else "k"
    path = f"engineering_sweeps.{kind}"
    start_key = f"start_{suffix}"
    end_key = f"end_{suffix}"
    value = _exact_keys(sweeps[kind], path, {start_key, end_key, "points"})
    return SweepAxisSettings(
        start=_number(value[start_key], f"{path}.{start_key}"),
        end=_number(value[end_key], f"{path}.{end_key}"),
        points=_integer(value["points"], f"{path}.points"),
    )


def _validated_case(document: dict[str, object]) -> OpenPhaseCase:
    if "schema" not in document:
        raise _schema_error("root is missing schema.")
    if "schema_version" not in document:
        raise _schema_error("root is missing schema_version.")
    schema = _string(document["schema"], "schema")
    if schema != CASE_SCHEMA:
        raise _schema_error(f"schema must be {CASE_SCHEMA!r}.")
    version = _string(document["schema_version"], "schema_version")
    if version != CASE_SCHEMA_VERSION:
        raise CaseFileError(
            f"Unsupported case schema version {version!r}; "
            f"supported version is {CASE_SCHEMA_VERSION!r}."
        )

    _exact_keys(
        document,
        "root",
        {
            "engineering_sweeps",
            "inputs",
            "presentation_units",
            "schema",
            "schema_version",
        },
    )

    temperature_unit, pressure_unit = _unit_preferences(document)
    inputs = _case_inputs(document)
    sweeps = _exact_keys(
        document["engineering_sweeps"],
        "engineering_sweeps",
        {"active", "pressure", "temperature"},
    )
    active = _string(sweeps["active"], "engineering_sweeps.active")
    if active not in ("pressure", "temperature"):
        raise _schema_error(
            "engineering_sweeps.active must be 'pressure' or 'temperature'."
        )
    active_sweep = cast(SweepKind, active)
    pressure_sweep = _axis_settings(sweeps, "pressure")
    temperature_sweep = _axis_settings(sweeps, "temperature")

    try:
        validate_sweep_request(
            "pressure",
            inputs.composition_mol_percent,
            fixed_value=inputs.temperature_k,
            start=pressure_sweep.start,
            end=pressure_sweep.end,
            points=pressure_sweep.points,
            temperature_unit=TemperatureUnit.KELVIN,
            pressure_unit=PressureUnit.PA,
        )
        validate_sweep_request(
            "temperature",
            inputs.composition_mol_percent,
            fixed_value=inputs.pressure_pa,
            start=temperature_sweep.start,
            end=temperature_sweep.end,
            points=temperature_sweep.points,
            temperature_unit=TemperatureUnit.KELVIN,
            pressure_unit=PressureUnit.PA,
        )
    except SweepValidationError as error:
        raise CaseFileError(f"Case sweep settings are invalid: {error}") from error

    return OpenPhaseCase(
        inputs=inputs,
        temperature_unit=temperature_unit,
        pressure_unit=pressure_unit,
        active_sweep=active_sweep,
        pressure_sweep=pressure_sweep,
        temperature_sweep=temperature_sweep,
    )


def case_from_state(state: MutableMapping[str, Any]) -> OpenPhaseCase:
    """Validate and capture the complete application input state."""

    document: dict[str, object] = {
        "schema": CASE_SCHEMA,
        "schema_version": CASE_SCHEMA_VERSION,
        "inputs": {
            "components": [
                {"name": name, "mole_percent": state[key]}
                for name, key in zip(
                    COMPONENT_NAMES,
                    ("methane_pct", "ethane_pct", "propane_pct"),
                    strict=True,
                )
            ],
            "temperature_k": state["temperature_k"],
            "pressure_pa": state["pressure_pa"],
        },
        "presentation_units": {
            "temperature": state["temperature_unit"],
            "pressure": state["pressure_unit"],
        },
        "engineering_sweeps": {
            "active": state["sweep_kind"],
            "pressure": {
                "start_pa": state["sweep_pressure_start_pa"],
                "end_pa": state["sweep_pressure_end_pa"],
                "points": state["sweep_points_pressure"],
            },
            "temperature": {
                "start_k": state["sweep_temperature_start_k"],
                "end_k": state["sweep_temperature_end_k"],
                "points": state["sweep_points_temperature"],
            },
        },
    }
    return _validated_case(document)


def _document(case: OpenPhaseCase) -> dict[str, object]:
    components = [
        {"name": name, "mole_percent": mole_percent}
        for name, mole_percent in zip(
            COMPONENT_NAMES, case.inputs.composition_mol_percent, strict=True
        )
    ]
    return {
        "engineering_sweeps": {
            "active": case.active_sweep,
            "pressure": {
                "end_pa": case.pressure_sweep.end,
                "points": case.pressure_sweep.points,
                "start_pa": case.pressure_sweep.start,
            },
            "temperature": {
                "end_k": case.temperature_sweep.end,
                "points": case.temperature_sweep.points,
                "start_k": case.temperature_sweep.start,
            },
        },
        "inputs": {
            "components": components,
            "pressure_pa": case.inputs.pressure_pa,
            "temperature_k": case.inputs.temperature_k,
        },
        "presentation_units": {
            "pressure": case.pressure_unit.value,
            "temperature": case.temperature_unit.value,
        },
        "schema": CASE_SCHEMA,
        "schema_version": CASE_SCHEMA_VERSION,
    }


def serialize_case(case: OpenPhaseCase) -> bytes:
    """Return canonical UTF-8 JSON; equal cases always produce equal bytes."""

    validated = _validated_case(_document(case))
    text = json.dumps(
        _document(validated),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"{text}\n".encode()


def load_case(data: bytes | str) -> OpenPhaseCase:
    """Parse and fully validate plain JSON without executing scientific work."""

    try:
        text = data.decode("utf-8-sig") if isinstance(data, bytes) else data
    except UnicodeDecodeError as error:
        raise CaseFileError("Case file is not valid UTF-8 JSON.") from error
    try:
        raw = cast(
            object,
            json.loads(
                text,
                object_pairs_hook=_object_pairs,
                parse_constant=_reject_nonfinite_constant,
            ),
        )
    except json.JSONDecodeError as error:
        raise CaseFileError("Case file is not valid JSON.") from error
    except _DuplicateKeyError as error:
        raise _schema_error(f"duplicate object key {error.args[0]!r}.") from error
    except _NonFiniteJsonNumberError as error:
        raise CaseFileError(
            f"Case file is not valid JSON: {error.args[0]} is not finite."
        ) from error
    return _validated_case(_object(raw, "root"))


def apply_case_to_state(case: OpenPhaseCase, state: MutableMapping[str, Any]) -> None:
    """Atomically replace input state after ``case`` has been fully validated."""

    case = _validated_case(_document(case))
    inputs = case.inputs
    state.update(
        {
            "methane_pct": inputs.composition_mol_percent[0],
            "ethane_pct": inputs.composition_mol_percent[1],
            "propane_pct": inputs.composition_mol_percent[2],
            "temperature_k": inputs.temperature_k,
            "pressure_pa": inputs.pressure_pa,
            "pressure_mpa": pressure_from_pa(inputs.pressure_pa, PressureUnit.MPA),
            "temperature_unit": case.temperature_unit.value,
            "pressure_unit": case.pressure_unit.value,
            "rendered_temperature_unit": case.temperature_unit.value,
            "rendered_pressure_unit": case.pressure_unit.value,
            "temperature_value": temperature_from_k(
                inputs.temperature_k, case.temperature_unit
            ),
            "pressure_value": pressure_from_pa(inputs.pressure_pa, case.pressure_unit),
            "sweep_kind": case.active_sweep,
            "sweep_pressure_start_pa": case.pressure_sweep.start,
            "sweep_pressure_end_pa": case.pressure_sweep.end,
            "sweep_points_pressure": case.pressure_sweep.points,
            "sweep_temperature_start_k": case.temperature_sweep.start,
            "sweep_temperature_end_k": case.temperature_sweep.end,
            "sweep_points_temperature": case.temperature_sweep.points,
            "current_inputs": inputs,
            "submitted_inputs": None,
            "input_error": None,
            "input_example": None,
            "rendered_input_example": None,
        }
    )
    state["rendered_temperature_value"] = state["temperature_value"]
    state["rendered_pressure_value"] = state["pressure_value"]

    if case.active_sweep == "pressure":
        start = pressure_from_pa(case.pressure_sweep.start, case.pressure_unit)
        end = pressure_from_pa(case.pressure_sweep.end, case.pressure_unit)
        points = case.pressure_sweep.points
    else:
        start = temperature_from_k(case.temperature_sweep.start, case.temperature_unit)
        end = temperature_from_k(case.temperature_sweep.end, case.temperature_unit)
        points = case.temperature_sweep.points
    state.update(
        {
            "sweep_start_value": start,
            "sweep_end_value": end,
            "sweep_points_value": points,
            "rendered_sweep_kind": case.active_sweep,
            "rendered_sweep_temperature_unit": case.temperature_unit.value,
            "rendered_sweep_pressure_unit": case.pressure_unit.value,
            "rendered_sweep_start_value": start,
            "rendered_sweep_end_value": end,
            "rendered_sweep_points_value": points,
        }
    )
