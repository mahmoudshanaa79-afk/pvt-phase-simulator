"""Input-only OpenPhase case persistence and validation tests."""

from __future__ import annotations

import copy
import json
from collections.abc import MutableMapping
from typing import Any

import pytest

from pvt_phase_simulator_ui import app as ui_app
from pvt_phase_simulator_ui.case_files import (
    CASE_SCHEMA,
    CASE_SCHEMA_VERSION,
    CaseFileError,
    apply_case_to_state,
    case_from_state,
    load_case,
    serialize_case,
)
from pvt_phase_simulator_ui.state import (
    initialize_session,
    synchronize_sweep_inputs,
    synchronize_unit_inputs,
)
from pvt_phase_simulator_ui.units import (
    PressureUnit,
    TemperatureUnit,
    pressure_from_pa,
    temperature_from_k,
)


def _configured_state() -> dict[str, Any]:
    state: dict[str, Any] = {}
    initialize_session(state)
    state.update(
        {
            "methane_pct": 70.0,
            "ethane_pct": 20.0,
            "propane_pct": 10.0,
            "temperature_k": 315.123456789,
            "pressure_pa": 8_765_432.1,
            "temperature_unit": "\N{DEGREE SIGN}F",
            "pressure_unit": "psi",
            "sweep_kind": "temperature",
            "sweep_pressure_start_pa": 2_345_678.9,
            "sweep_pressure_end_pa": 19_876_543.2,
            "sweep_points_pressure": 17,
            "sweep_temperature_start_k": 255.25,
            "sweep_temperature_end_k": 377.75,
            "sweep_points_temperature": 29,
        }
    )
    return state


def _document() -> dict[str, Any]:
    return json.loads(serialize_case(case_from_state(_configured_state())))


def _json_bytes(document: object) -> bytes:
    return json.dumps(document, ensure_ascii=False).encode()


def test_case_round_trip_is_deterministic_and_captures_all_inputs() -> None:
    case = case_from_state(_configured_state())
    first = serialize_case(case)
    restored = load_case(first)
    second = serialize_case(restored)

    assert first == second
    assert first.endswith(b"\n")
    document = json.loads(first)
    assert document["schema"] == CASE_SCHEMA
    assert document["schema_version"] == CASE_SCHEMA_VERSION
    assert [item["name"] for item in document["inputs"]["components"]] == [
        "Methane",
        "Ethane",
        "Propane",
    ]
    assert restored.inputs.composition_mol_percent == (70.0, 20.0, 10.0)
    assert restored.inputs.temperature_k == 315.123456789
    assert restored.inputs.pressure_pa == 8_765_432.1


def test_units_and_both_sweep_definitions_survive_round_trip() -> None:
    restored = load_case(serialize_case(case_from_state(_configured_state())))

    assert restored.temperature_unit.value == "\N{DEGREE SIGN}F"
    assert restored.pressure_unit.value == "psi"
    assert restored.active_sweep == "temperature"
    assert restored.pressure_sweep.start == 2_345_678.9
    assert restored.pressure_sweep.end == 19_876_543.2
    assert restored.pressure_sweep.points == 17
    assert restored.temperature_sweep.start == 255.25
    assert restored.temperature_sweep.end == 377.75
    assert restored.temperature_sweep.points == 29


def test_sweep_widget_edits_and_unit_changes_are_captured_losslessly() -> None:
    state: dict[str, Any] = {}
    initialize_session(state)
    state.update(
        {
            "sweep_start_value": 2.5,
            "sweep_end_value": 18.5,
            "sweep_points_value": 13,
        }
    )
    synchronize_sweep_inputs(state)
    assert state["sweep_pressure_start_pa"] == 2.5e6
    assert state["sweep_pressure_end_pa"] == 18.5e6
    assert state["sweep_points_pressure"] == 13

    state["sweep_kind"] = "temperature"
    synchronize_sweep_inputs(state)
    state.update(
        {
            "sweep_start_value": 260.5,
            "sweep_end_value": 375.5,
            "sweep_points_value": 31,
        }
    )
    synchronize_sweep_inputs(state)
    state["temperature_unit"] = TemperatureUnit.CELSIUS.value
    state["pressure_unit"] = PressureUnit.BAR.value
    synchronize_unit_inputs(state)

    assert state["sweep_temperature_start_k"] == 260.5
    assert state["sweep_temperature_end_k"] == 375.5
    assert state["sweep_points_temperature"] == 31
    assert state["sweep_start_value"] == temperature_from_k(
        260.5, TemperatureUnit.CELSIUS
    )
    assert state["sweep_end_value"] == temperature_from_k(
        375.5, TemperatureUnit.CELSIUS
    )

    restored = load_case(serialize_case(case_from_state(state)))
    assert (
        restored.pressure_sweep.start,
        restored.pressure_sweep.end,
        restored.pressure_sweep.points,
    ) == (2.5e6, 18.5e6, 13)
    assert (
        restored.temperature_sweep.start,
        restored.temperature_sweep.end,
        restored.temperature_sweep.points,
    ) == (260.5, 375.5, 31)


def test_applying_loaded_case_restores_widget_inputs_without_results() -> None:
    case = load_case(serialize_case(case_from_state(_configured_state())))
    target: dict[str, Any] = {}
    initialize_session(target)
    prior_result = object()
    target["results"] = {"flash": prior_result}

    apply_case_to_state(case, target)

    assert target["methane_pct"] == 70.0
    assert target["ethane_pct"] == 20.0
    assert target["propane_pct"] == 10.0
    assert target["temperature_unit"] == "\N{DEGREE SIGN}F"
    assert target["pressure_unit"] == "psi"
    assert target["temperature_value"] == temperature_from_k(
        case.inputs.temperature_k, TemperatureUnit.FAHRENHEIT
    )
    assert target["pressure_value"] == pressure_from_pa(
        case.inputs.pressure_pa, PressureUnit.PSI
    )
    assert target["sweep_kind"] == "temperature"
    assert target["sweep_start_value"] == temperature_from_k(
        case.temperature_sweep.start, TemperatureUnit.FAHRENHEIT
    )
    assert target["sweep_end_value"] == temperature_from_k(
        case.temperature_sweep.end, TemperatureUnit.FAHRENHEIT
    )
    assert target["sweep_points_value"] == 29
    assert target["submitted_inputs"] is None
    assert target["results"] == {"flash": prior_result}


def test_malformed_json_has_a_specific_user_facing_error() -> None:
    with pytest.raises(CaseFileError) as caught:
        load_case(b'{"schema":')
    assert str(caught.value) == "Case file is not valid JSON."


@pytest.mark.parametrize(
    ("mutation", "path"),
    [
        (
            lambda document, value: document["inputs"].update({"temperature_k": value}),
            "inputs.temperature_k",
        ),
        (
            lambda document, value: document["inputs"].update({"pressure_pa": value}),
            "inputs.pressure_pa",
        ),
        (
            lambda document, value: document["inputs"]["components"][0].update(
                {"mole_percent": value}
            ),
            "inputs.components[0].mole_percent",
        ),
        (
            lambda document, value: document["engineering_sweeps"]["pressure"].update(
                {"start_pa": value}
            ),
            "engineering_sweeps.pressure.start_pa",
        ),
    ],
)
def test_out_of_range_json_integers_have_specific_numeric_field_errors(
    mutation: Any, path: str
) -> None:
    document = _document()
    mutation(document, 10**400)

    with pytest.raises(CaseFileError) as caught:
        load_case(_json_bytes(document))
    assert str(caught.value) == (
        f"Case file schema is invalid: {path} must be a finite number."
    )


@pytest.mark.parametrize(
    ("literal", "value"),
    [
        ("NaN", float("nan")),
        ("Infinity", float("inf")),
        ("-Infinity", float("-inf")),
    ],
)
def test_non_finite_json_numeric_literals_are_refused(
    literal: str, value: float
) -> None:
    document = _document()
    document["inputs"]["temperature_k"] = value

    with pytest.raises(CaseFileError) as caught:
        load_case(_json_bytes(document))
    assert str(caught.value) == (
        f"Case file is not valid JSON: {literal} is not finite."
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda document: document.pop("inputs"),
        lambda document: document["inputs"].update({"invented": 1}),
        lambda document: document["presentation_units"].update(
            {"pressure": "atmospheres"}
        ),
    ],
)
def test_invalid_schema_has_a_specific_user_facing_error(
    mutation: Any,
) -> None:
    document = _document()
    mutation(document)

    with pytest.raises(CaseFileError, match="^Case file schema is invalid:"):
        load_case(_json_bytes(document))


@pytest.mark.parametrize("version", ["2.0.0", "999.0.0", "draft"])
def test_unknown_and_future_schema_versions_are_refused(version: str) -> None:
    document = _document()
    document["schema_version"] = version

    with pytest.raises(CaseFileError) as caught:
        load_case(_json_bytes(document))
    assert str(caught.value) == (
        f"Unsupported case schema version {version!r}; "
        f"supported version is {CASE_SCHEMA_VERSION!r}."
    )


def test_invalid_composition_uses_manual_entry_error_and_is_not_normalized() -> None:
    document = _document()
    document["inputs"]["components"][0]["mole_percent"] = 69.0

    with pytest.raises(CaseFileError) as caught:
        load_case(_json_bytes(document))
    assert str(caught.value) == (
        "Composition must total 100 mol %. Values are not automatically normalized."
    )


def test_invalid_sweep_is_rejected_before_state_is_changed() -> None:
    document = _document()
    document["engineering_sweeps"]["pressure"]["points"] = 1
    state = _configured_state()
    before = copy.deepcopy(state)

    with pytest.raises(CaseFileError, match="^Case sweep settings are invalid:"):
        ui_app._load_case_inputs(_json_bytes(document), state)
    assert state == before


def test_loading_invalid_file_cannot_execute_science(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    science_calls = 0

    def forbidden_science(_inputs: object) -> object:
        nonlocal science_calls
        science_calls += 1
        raise AssertionError("science must not run while loading")

    monkeypatch.setattr(ui_app, "_cached_flash", forbidden_science)
    state: MutableMapping[str, Any] = _configured_state()

    with pytest.raises(CaseFileError):
        ui_app._load_case_inputs(b"not-json", state)
    assert science_calls == 0


def test_duplicate_json_keys_are_rejected_as_an_ambiguous_schema() -> None:
    with pytest.raises(CaseFileError) as caught:
        load_case(
            b'{"schema":"openphase.case","schema":"openphase.case",'
            b'"schema_version":"1.0.0"}'
        )
    assert "duplicate object key 'schema'" in str(caught.value)
