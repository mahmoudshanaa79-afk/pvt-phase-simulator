"""Edge cases of case files found by mutation testing (2026-11).

Each test pins a behaviour that a surviving mutant showed was not yet checked:
the exact refusal messages, booleans that are not numbers, the supported input
range on load, kij restored from a version 1.1.0 file, canonical bytes, and
the restored sweep widgets.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest

from pvt_phase_simulator_ui.case_files import (
    CASE_SCHEMA,
    CASE_SCHEMA_VERSION_WITH_KIJ,
    CaseFileError,
    OpenPhaseCase,
    SweepAxisSettings,
    apply_case_to_state,
    case_from_state,
    load_case,
    serialize_case,
)
from pvt_phase_simulator_ui.state import initialize_session


def _state(**overrides: Any) -> dict[str, Any]:
    state: dict[str, Any] = {}
    initialize_session(state)
    state.update(overrides)
    return state


def _document(**overrides: Any) -> dict[str, Any]:
    return json.loads(serialize_case(case_from_state(_state(**overrides))))


def _load(document: object) -> OpenPhaseCase:
    return load_case(json.dumps(document, ensure_ascii=False).encode())


def _refused(document: object, message: str) -> None:
    with pytest.raises(CaseFileError) as refused:
        _load(document)
    assert str(refused.value) == message


def test_case_records_are_immutable_and_slotted() -> None:
    case = case_from_state(_state())
    with pytest.raises(dataclasses.FrozenInstanceError):
        case.active_sweep = "temperature"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        case.pressure_sweep.points = 3  # type: ignore[misc]
    for value in (case, case.pressure_sweep):
        assert not hasattr(value, "__dict__")
    assert isinstance(case.pressure_sweep, SweepAxisSettings)


def test_a_root_that_is_not_an_object_is_refused() -> None:
    _refused("abc", "Case file schema is invalid: root must be an object.")
    _refused([1, 2], "Case file schema is invalid: root must be an object.")


def test_missing_fields_are_named_without_unknown_ones() -> None:
    document = _document()
    del document["inputs"]["pressure_pa"]
    document["inputs"]["colour"] = "blue"
    _refused(document, "Case file schema is invalid: inputs is missing pressure_pa.")


def test_booleans_are_not_numbers_or_integers() -> None:
    document = _document()
    document["inputs"]["temperature_k"] = True
    _refused(
        document, "Case file schema is invalid: inputs.temperature_k must be a number."
    )
    document = _document()
    document["engineering_sweeps"]["pressure"]["points"] = True
    with pytest.raises(CaseFileError, match="must be an integer"):
        _load(document)


@pytest.mark.parametrize(
    ("field", "unit"), (("pressure", "furlong"), ("temperature", "R"))
)
def test_an_unknown_presentation_unit_is_a_case_file_error(
    field: str, unit: str
) -> None:
    document = _document()
    document["presentation_units"][field] = unit
    with pytest.raises(
        CaseFileError, match=f"presentation_units.{field} must be one of"
    ):
        _load(document)


def test_the_supported_range_is_enforced_on_load() -> None:
    document = _document()
    document["inputs"]["temperature_k"] = 10.0
    with pytest.raises(CaseFileError, match="between 50 K and 1000 K"):
        _load(document)


@pytest.mark.parametrize("schema", (CASE_SCHEMA + "x", CASE_SCHEMA[:-1], "a", "z"))
def test_any_other_schema_name_is_refused(schema: str) -> None:
    document = _document()
    document["schema"] = schema
    _refused(document, f"Case file schema is invalid: schema must be {CASE_SCHEMA!r}.")


def test_kij_survives_a_version_1_1_round_trip() -> None:
    state = _state(methane_pct=40.0, ethane_pct=30.0, propane_pct=30.0)
    state.update({"kij_c1_c2": 0.01, "kij_c1_c3": 0.002, "kij_c2_c3": -0.003})
    saved = serialize_case(case_from_state(state))
    assert json.loads(saved)["schema_version"] == CASE_SCHEMA_VERSION_WITH_KIJ
    restored = load_case(saved)
    assert restored.inputs.kij == (0.01, 0.002, -0.003)


def test_a_state_without_kij_keys_gives_zero_kij() -> None:
    state = _state()
    for key in ("kij_c1_c2", "kij_c1_c3", "kij_c2_c3"):
        state.pop(key, None)
    assert case_from_state(state).inputs.kij == (0.0, 0.0, 0.0)


def test_saved_bytes_are_canonical_utf8_with_sorted_keys() -> None:
    saved = serialize_case(case_from_state(_state(temperature_unit="°F")))
    assert "°F".encode() in saved
    assert b"\\u00b0" not in saved
    document = json.loads(saved)

    def sorted_everywhere(value: object) -> bool:
        if isinstance(value, dict):
            return list(value) == sorted(value) and all(
                sorted_everywhere(item) for item in value.values()
            )
        if isinstance(value, list):
            return all(sorted_everywhere(item) for item in value)
        return True

    assert sorted_everywhere(document)
    assert (
        saved
        == json.dumps(
            document, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        + b"\n"
    )


def test_text_input_and_invalid_utf8() -> None:
    saved = serialize_case(case_from_state(_state()))
    assert load_case(saved.decode()) == load_case(saved)
    with pytest.raises(CaseFileError, match="not valid UTF-8 JSON"):
        load_case(b"\xff\xfe\x00{")


def test_duplicate_keys_and_non_finite_numbers_are_named() -> None:
    saved = serialize_case(case_from_state(_state())).decode()
    duplicated = saved.replace(
        '{"engineering_sweeps"', '{"schema":"x","engineering_sweeps"', 1
    )
    with pytest.raises(CaseFileError, match="duplicate object key 'schema'"):
        load_case(duplicated)
    non_finite = saved.replace('"temperature_k":300.0', '"temperature_k":NaN', 1)
    assert non_finite != saved
    with pytest.raises(CaseFileError, match="NaN is not finite"):
        load_case(non_finite)


@pytest.mark.parametrize("active", ("pressure", "temperature"))
def test_the_active_sweep_widgets_are_restored_in_its_units(active: str) -> None:
    state = _state(sweep_kind=active, pressure_unit="bar", temperature_unit="°C")
    case = load_case(serialize_case(case_from_state(state)))
    target = _state()
    apply_case_to_state(case, target)
    assert target["sweep_kind"] == active
    if active == "pressure":
        assert target["sweep_start_value"] == pytest.approx(
            case.pressure_sweep.start / 1e5
        )
        assert target["sweep_points_value"] == case.pressure_sweep.points
    else:
        assert target["sweep_start_value"] == pytest.approx(
            case.temperature_sweep.start - 273.15
        )
        assert target["sweep_points_value"] == case.temperature_sweep.points
