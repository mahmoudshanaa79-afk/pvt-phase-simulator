"""Deterministic property-based tests for the application layer.

The hypothesis profile in ``tests/conftest.py`` is derandomized, so every run
draws the same examples. Example counts are small: the engine-backed
properties (exports and reports) run a real flash for each example.
"""

from __future__ import annotations

import csv
import io
import json
import math
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pvt_phase_simulator.eos.flash import calculate_two_phase_flash
from pvt_phase_simulator_ui.adapters import (
    KIJ_MAXIMUM,
    KIJ_MINIMUM,
    MAXIMUM_PRESSURE_PA,
    MAXIMUM_TEMPERATURE_K,
    MINIMUM_PRESSURE_PA,
    MINIMUM_TEMPERATURE_K,
    InputValidationError,
    validate_scientific_inputs,
)
from pvt_phase_simulator_ui.case_files import (
    CaseFileError,
    case_from_state,
    load_case,
    serialize_case,
)
from pvt_phase_simulator_ui.exports import (
    build_export_document,
    export_csv_bytes,
    export_json_bytes,
)
from pvt_phase_simulator_ui.model_scope import ModelScope, load_model_scope
from pvt_phase_simulator_ui.reports import export_engineering_report_html
from pvt_phase_simulator_ui.state import initialize_session
from pvt_phase_simulator_ui.sweeps import (
    MAX_SWEEP_POINTS,
    MIN_SWEEP_POINTS,
    SweepValidationError,
    validate_sweep_request,
)
from pvt_phase_simulator_ui.units import (
    PRESSURE_UNITS,
    TEMPERATURE_UNITS,
    PressureUnit,
    TemperatureUnit,
    convert_pressure,
    convert_temperature,
    pressure_from_pa,
    pressure_to_pa,
    temperature_from_k,
    temperature_to_k,
)

ROOT = Path(__file__).resolve().parents[1]
FAST = 60
ENGINE = 8


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-9)


# -- units -------------------------------------------------------------------

finite = st.floats(min_value=-1e12, max_value=1e12, allow_nan=False)


@given(value=finite, unit=st.sampled_from(PRESSURE_UNITS))
@settings(max_examples=FAST)
def test_every_pressure_conversion_round_trips(
    value: float, unit: PressureUnit
) -> None:
    assert _close(pressure_from_pa(pressure_to_pa(value, unit), unit), value)
    for other in PRESSURE_UNITS:
        there = convert_pressure(value, unit, other)
        assert _close(convert_pressure(there, other, unit), value)


@given(value=finite, unit=st.sampled_from(TEMPERATURE_UNITS))
@settings(max_examples=FAST)
def test_every_temperature_conversion_round_trips(
    value: float, unit: TemperatureUnit
) -> None:
    assert math.isclose(
        temperature_from_k(temperature_to_k(value, unit), unit),
        value,
        rel_tol=1e-12,
        abs_tol=1e-6,
    )
    for other in TEMPERATURE_UNITS:
        there = convert_temperature(value, unit, other)
        assert math.isclose(
            convert_temperature(there, other, unit), value, rel_tol=1e-12, abs_tol=1e-6
        )


@pytest.mark.parametrize("bad", (math.nan, math.inf, -math.inf))
def test_non_finite_values_are_refused_with_a_message(bad: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        pressure_to_pa(bad, PressureUnit.MPA)
    with pytest.raises(ValueError, match="finite"):
        temperature_to_k(bad, TemperatureUnit.CELSIUS)


@given(
    unit=st.text(min_size=1, max_size=6).filter(
        lambda text: text not in {"Pa", "MPa", "bar", "psi", "K", "°C", "°F"}
    )
)
@settings(max_examples=FAST)
def test_an_unknown_unit_is_refused_and_the_message_lists_the_supported_ones(
    unit: str,
) -> None:
    with pytest.raises(ValueError, match="use Pa, MPa, bar, psi"):
        pressure_to_pa(1.0, unit)
    with pytest.raises(ValueError, match="use K"):
        temperature_to_k(1.0, unit)


# -- adapters: the supported input range ---------------------------------------

compositions = (
    st.tuples(
        st.integers(min_value=0, max_value=100),
        st.integers(min_value=0, max_value=100),
    )
    .filter(lambda pair: sum(pair) <= 100)
    .map(lambda pair: (float(pair[0]), float(pair[1]), float(100 - pair[0] - pair[1])))
)


@given(
    composition=compositions,
    temperature=st.floats(
        min_value=MINIMUM_TEMPERATURE_K, max_value=MAXIMUM_TEMPERATURE_K
    ),
    pressure=st.floats(min_value=MINIMUM_PRESSURE_PA, max_value=MAXIMUM_PRESSURE_PA),
)
@settings(max_examples=FAST)
def test_every_input_inside_the_supported_range_is_accepted_unchanged(
    composition: tuple[float, float, float], temperature: float, pressure: float
) -> None:
    inputs = validate_scientific_inputs(
        composition,
        temperature,
        pressure,
        pressure_unit=PressureUnit.PA,
        supported_range=True,
    )
    assert inputs.temperature_k == temperature
    assert inputs.pressure_pa == pressure
    assert math.isclose(sum(inputs.mole_fractions), 1.0, abs_tol=1e-12)


@given(
    temperature=st.one_of(
        st.floats(min_value=1e-3, max_value=MINIMUM_TEMPERATURE_K, exclude_max=True),
        st.floats(min_value=MAXIMUM_TEMPERATURE_K, max_value=1e7, exclude_min=True),
    )
)
@settings(max_examples=FAST)
def test_a_temperature_outside_the_range_is_refused_with_the_limits(
    temperature: float,
) -> None:
    with pytest.raises(InputValidationError, match="between 50 K and 1000 K"):
        validate_scientific_inputs((50, 0, 50), temperature, 5.0, supported_range=True)


@given(
    pressure=st.one_of(
        st.floats(min_value=1e-6, max_value=MINIMUM_PRESSURE_PA, exclude_max=True),
        st.floats(min_value=MAXIMUM_PRESSURE_PA, max_value=1e15, exclude_min=True),
    )
)
@settings(max_examples=FAST)
def test_a_pressure_outside_the_range_is_refused_with_the_limits(
    pressure: float,
) -> None:
    with pytest.raises(InputValidationError, match="between 1 Pa and 1e\\+09 Pa"):
        validate_scientific_inputs(
            (50, 0, 50),
            300.0,
            pressure,
            pressure_unit=PressureUnit.PA,
            supported_range=True,
        )


@given(
    composition=st.tuples(
        st.floats(min_value=0, max_value=100),
        st.floats(min_value=0, max_value=100),
        st.floats(min_value=0, max_value=100),
    ).filter(lambda values: abs(sum(values) - 100.0) > 1e-6 and sum(values) > 0)
)
@settings(max_examples=FAST)
def test_a_composition_that_does_not_total_100_is_refused(
    composition: tuple[float, float, float],
) -> None:
    with pytest.raises(InputValidationError, match="must total 100 mol %"):
        validate_scientific_inputs(composition, 300.0, 5.0)


@given(
    kij=st.one_of(
        st.floats(min_value=-1e6, max_value=KIJ_MINIMUM, exclude_max=True),
        st.floats(min_value=KIJ_MAXIMUM, max_value=1e6, exclude_min=True),
    ),
    pair=st.integers(min_value=0, max_value=2),
)
@settings(max_examples=FAST)
def test_a_kij_outside_its_range_is_refused_with_the_limits(
    kij: float, pair: int
) -> None:
    values = [0.0, 0.0, 0.0]
    values[pair] = kij
    with pytest.raises(InputValidationError, match="must be between -0.10 and 0.20"):
        validate_scientific_inputs((40, 30, 30), 300.0, 5.0, kij=tuple(values))


# -- case files --------------------------------------------------------


@st.composite
def _states(draw: st.DrawFn) -> dict[str, Any]:
    state: dict[str, Any] = {}
    initialize_session(state)
    methane, ethane, propane = draw(compositions)
    temperature = draw(
        st.floats(min_value=MINIMUM_TEMPERATURE_K, max_value=MAXIMUM_TEMPERATURE_K)
    )
    pressure = draw(
        st.floats(min_value=MINIMUM_PRESSURE_PA, max_value=MAXIMUM_PRESSURE_PA)
    )
    state.update(
        {
            "methane_pct": methane,
            "ethane_pct": ethane,
            "propane_pct": propane,
            "temperature_k": temperature,
            "pressure_pa": pressure,
            "temperature_unit": draw(st.sampled_from(TEMPERATURE_UNITS)).value,
            "pressure_unit": draw(st.sampled_from(PRESSURE_UNITS)).value,
            "sweep_kind": draw(st.sampled_from(("pressure", "temperature"))),
            "sweep_points_pressure": draw(
                st.integers(MIN_SWEEP_POINTS, MAX_SWEEP_POINTS)
            ),
            "sweep_points_temperature": draw(
                st.integers(MIN_SWEEP_POINTS, MAX_SWEEP_POINTS)
            ),
        }
    )
    return state


@given(state=_states())
@settings(max_examples=FAST)
def test_save_then_load_gives_the_same_case(state: dict[str, Any]) -> None:
    case = case_from_state(state)
    saved = serialize_case(case)
    restored = load_case(saved)
    assert restored == case
    assert serialize_case(restored) == saved


@given(data=st.binary(max_size=200))
@settings(max_examples=FAST)
def test_arbitrary_bytes_are_refused_cleanly(data: bytes) -> None:
    try:
        load_case(data)
    except CaseFileError as error:
        assert str(error).startswith(("Case file", "Unsupported case schema"))
    else:  # pragma: no cover - random bytes are never a valid case
        pytest.fail("random bytes loaded as a case")


@given(
    path=st.sampled_from(
        (
            "schema",
            "schema_version",
            "inputs",
            "presentation_units",
            "engineering_sweeps",
        )
    ),
    value=st.one_of(
        st.none(),
        st.integers(),
        st.text(max_size=5),
        st.lists(st.integers(), max_size=2),
    ),
)
@settings(max_examples=FAST)
def test_a_corrupted_field_is_refused_with_a_case_file_error(
    path: str, value: object
) -> None:
    state: dict[str, Any] = {}
    initialize_session(state)
    document = json.loads(serialize_case(case_from_state(state)))
    document[path] = value
    with pytest.raises(CaseFileError):
        load_case(json.dumps(document).encode())


# -- exports and reports (a real flash per example) --------------------

engine_states = st.tuples(
    compositions.filter(lambda c: c[0] > 0 and c[2] > 0),
    st.sampled_from((220.0, 260.0, 300.0, 340.0)),
    st.sampled_from((0.5, 2.0, 5.0, 10.0)),
)


@cache
def _scope() -> ModelScope:
    return load_model_scope(ROOT)


def _document(
    state: tuple[tuple[float, float, float], float, float],
) -> dict[str, object]:
    composition, temperature, pressure_mpa = state
    inputs = validate_scientific_inputs(composition, temperature, pressure_mpa)
    flash = calculate_two_phase_flash(
        inputs.mixture(), inputs.temperature_k, inputs.pressure_pa
    )
    return build_export_document(inputs, flash_result=flash)


@given(state=engine_states)
@settings(max_examples=ENGINE)
def test_every_export_parses_and_contains_its_inputs(
    state: tuple[tuple[float, float, float], float, float],
) -> None:
    document = _document(state)
    composition, temperature, pressure_mpa = state
    parsed = json.loads(export_json_bytes(document))
    assert parsed == json.loads(json.dumps(document))
    text = json.dumps(parsed)
    assert repr(float(temperature)) in text
    assert repr(pressure_mpa * 1e6) in text
    rows = list(csv.reader(io.StringIO(export_csv_bytes(document).decode("utf-8"))))
    assert len(rows) > 10
    flat = "\n".join(",".join(row) for row in rows)
    assert repr(float(temperature)) in flat
    for value in composition:
        assert repr(float(value)) in text


@given(state=engine_states)
@settings(max_examples=ENGINE)
def test_the_report_contains_its_inputs_and_the_engine_status(
    state: tuple[tuple[float, float, float], float, float],
) -> None:
    document = _document(state)
    html = export_engineering_report_html(
        document, scope=_scope(), generated_at=datetime(2026, 11, 15, tzinfo=UTC)
    ).decode("utf-8")
    assert html.lower().startswith("<!doctype html")
    results = document["results"]
    assert isinstance(results, dict)
    flash = results["flash"]
    assert isinstance(flash, dict)
    # The report shows statuses in words: "not_attempted" -> "Not attempted".
    for key in ("solver_status", "phase_classification"):
        assert str(flash[key]).replace("_", " ").capitalize() in html, key
    for name in ("Methane", "Ethane", "Propane"):
        assert name in html


# -- sweeps ------------------------------------------------------------


@given(
    start=st.floats(min_value=0.01, max_value=50.0),
    end=st.floats(min_value=0.01, max_value=50.0),
    points=st.integers(min_value=-5, max_value=100),
)
@settings(max_examples=FAST)
def test_sweep_requests_are_accepted_only_with_a_valid_range_and_count(
    start: float, end: float, points: int
) -> None:
    valid = MIN_SWEEP_POINTS <= points <= MAX_SWEEP_POINTS and start != end
    try:
        request = validate_sweep_request(
            "pressure",
            (50, 0, 50),
            fixed_value=300.0,
            start=start,
            end=end,
            points=points,
        )
    except SweepValidationError as error:
        assert not valid or str(error)
        assert str(error).endswith(".")
    else:
        assert valid
        assert request.points == points
        values = request.axis_values()
        assert len(values) == points
        assert values[0] == pytest.approx(start)
        assert values[-1] == pytest.approx(end)
