"""Hostile and edge inputs never crash the app: inputs, units, kij, sweeps, cases.

Each scenario must end in a readable message or a result, never in a raw
exception, a generic safe-boundary message or a logged application error (see
``tests/_robustness.py``). The heavier RUN-action scenarios are in
``tests/test_app_robustness_actions.py``.
"""

from __future__ import annotations

import json
import logging
import math

import pytest

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
from pvt_phase_simulator_ui.sweeps import (
    MAX_SWEEP_POINTS,
    SweepValidationError,
    validate_sweep_request,
)
from pvt_phase_simulator_ui.units import (
    PRESSURE_UNITS,
    TEMPERATURE_UNITS,
    pressure_from_pa,
    temperature_from_k,
)
from tests._robustness import (
    PAGE_FILES,
    app_errors,
    assert_clean,
    button,
    go,
    has_result,
    new_app,
    run_flash,
    set_inputs,
    submission_error,
)

__all__ = ["app_errors"]  # the fixture is used by name

Errors = list[logging.LogRecord]

# --- compositions -----------------------------------------------------------

INVALID_COMPOSITIONS = {
    "total below 100": ((40.0, 0.0, 50.0), "must total 100 mol %"),
    "total above 100": ((60.0, 0.0, 50.0), "must total 100 mol %"),
    "all zero": ((0.0, 0.0, 0.0), "greater than zero"),
    "negative": ((-1.0, 51.0, 50.0), "cannot be negative"),
    "above 100": ((101.0, -1.0, 0.0), "cannot be negative"),
}


@pytest.mark.parametrize("name", INVALID_COMPOSITIONS)
def test_an_invalid_composition_is_refused_with_its_reason(
    name: str, app_errors: Errors
) -> None:
    composition, reason = INVALID_COMPOSITIONS[name]
    app = new_app()
    set_inputs(app, composition=composition)
    run_flash(app)
    assert_clean(app, app_errors, name)
    assert not has_result(app, "flash")
    assert reason in submission_error(app)


def test_a_not_a_number_entry_is_refused_at_the_input_boundary() -> None:
    # A browser number field cannot hold NaN; the boundary refuses it anyway.
    with pytest.raises(InputValidationError, match="finite"):
        validate_scientific_inputs((math.nan, 50.0, 50.0), 300.0, 5.0)
    with pytest.raises(InputValidationError, match="finite"):
        validate_scientific_inputs((50.0, 0.0, 50.0), math.nan, 5.0)
    with pytest.raises(InputValidationError, match="finite"):
        validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, math.nan)


VALID_COMPOSITIONS = {
    "pure methane": ((100.0, 0.0, 0.0), 150.0),
    "pure ethane": ((0.0, 100.0, 0.0), 250.0),
    "pure propane": ((0.0, 0.0, 100.0), 300.0),
    "methane trace": ((1e-6, 0.0, 100.0 - 1e-6), 300.0),
    "two traces": ((100.0 - 2e-6, 1e-6, 1e-6), 150.0),
}


@pytest.mark.parametrize("name", VALID_COMPOSITIONS)
def test_pure_components_and_traces_flash_and_render_every_page(
    name: str, app_errors: Errors
) -> None:
    composition, temperature = VALID_COMPOSITIONS[name]
    app = new_app()
    set_inputs(app, composition=composition, temperature=temperature)
    run_flash(app)
    assert_clean(app, app_errors, name)
    assert has_result(app, "flash")
    for page in PAGE_FILES:
        go(app, page)
        assert_clean(app, app_errors, f"{name}: {page}")


# --- temperature and pressure in every unit ---------------------------------


def _temperature_cases() -> list[tuple[str, str, float, bool]]:
    cases = []
    for unit in TEMPERATURE_UNITS:
        low = temperature_from_k(MINIMUM_TEMPERATURE_K, unit)
        high = temperature_from_k(MAXIMUM_TEMPERATURE_K, unit)
        span = high - low
        cases += [
            (unit.value, "at the minimum", low, True),
            (unit.value, "at the maximum", high, True),
            (unit.value, "below the minimum", low - 0.01 * span, False),
            (unit.value, "above the maximum", high + 0.01 * span, False),
            (unit.value, "huge", 1.0e300, False),
            (unit.value, "below absolute zero", -1.0e6, False),
        ]
    return cases


@pytest.mark.parametrize(("unit", "label", "value", "accepted"), _temperature_cases())
def test_temperature_limits_in_every_unit(
    unit: str, label: str, value: float, accepted: bool, app_errors: Errors
) -> None:
    app = new_app()
    app.segmented_control(key="temperature_unit").set_value(unit).run()
    set_inputs(app, temperature=value)
    run_flash(app)
    assert_clean(app, app_errors, f"{unit} {label}")
    assert has_result(app, "flash") is accepted
    if not accepted:
        assert "Temperature" in submission_error(app)


def _pressure_cases() -> list[tuple[str, str, float, bool]]:
    cases = []
    for unit in PRESSURE_UNITS:
        low = pressure_from_pa(MINIMUM_PRESSURE_PA, unit)
        high = pressure_from_pa(MAXIMUM_PRESSURE_PA, unit)
        cases += [
            (unit.value, "at the minimum", low, True),
            (unit.value, "at the maximum", high, True),
            (unit.value, "below the minimum", 0.5 * low, False),
            (unit.value, "above the maximum", 2.0 * high, False),
            (unit.value, "zero", 0.0, False),
            (unit.value, "negative", -1.0, False),
            (unit.value, "huge", 1.0e300, False),
        ]
    return cases


@pytest.mark.parametrize(("unit", "label", "value", "accepted"), _pressure_cases())
def test_pressure_limits_in_every_unit(
    unit: str, label: str, value: float, accepted: bool, app_errors: Errors
) -> None:
    app = new_app()
    app.segmented_control(key="pressure_unit").set_value(unit).run()
    set_inputs(app, pressure=value)
    run_flash(app)
    assert_clean(app, app_errors, f"{unit} {label}")
    assert has_result(app, "flash") is accepted
    if not accepted:
        assert "Pressure" in submission_error(app)


def test_the_range_message_names_the_limits_in_the_selected_unit() -> None:
    # Library callers that only build a mixture are not range-checked.
    validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 5.0e6)
    with pytest.raises(InputValidationError) as caught:
        validate_scientific_inputs(
            (50.0, 0.0, 50.0),
            -250.0,
            5.0,
            temperature_unit="°C",
            supported_range=True,
        )
    assert "50 K and 1000 K (-223.15 °C to 726.85 °C)" in str(caught.value)
    with pytest.raises(InputValidationError) as caught:
        validate_scientific_inputs(
            (50.0, 0.0, 50.0), 300.0, 2.0e4, pressure_unit="bar", supported_range=True
        )
    assert "1 Pa and 1e+09 Pa (1e-05 bar to 10000 bar)" in str(caught.value)


# --- kij ----------------------------------------------------------------------

KIJ_EDGES = [(pair, value) for pair in range(3) for value in (KIJ_MINIMUM, KIJ_MAXIMUM)]


@pytest.mark.parametrize(("pair", "value"), KIJ_EDGES)
def test_each_kij_pair_at_its_range_edges(
    pair: int, value: float, app_errors: Errors
) -> None:
    kij = [0.0, 0.0, 0.0]
    kij[pair] = value
    app = new_app()
    set_inputs(app, composition=(40.0, 30.0, 30.0), kij=(kij[0], kij[1], kij[2]))
    run_flash(app)
    assert_clean(app, app_errors, f"kij pair {pair} = {value}")
    assert has_result(app, "flash")
    assert app.session_state["submitted_inputs"].kij[pair] == value


@pytest.mark.parametrize("value", (KIJ_MINIMUM - 1e-3, KIJ_MAXIMUM + 1e-3, math.nan))
def test_a_kij_beyond_its_range_is_refused(value: float) -> None:
    with pytest.raises(InputValidationError, match="kij C1–C3 must be between"):
        validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 5.0, kij=(0.0, value, 0.0))


# --- sweeps -------------------------------------------------------------------


def _sweep_app(app_errors: Errors) -> object:
    app = new_app()
    run_flash(app)
    go(app, "engineering_sweeps.py")
    assert_clean(app, app_errors, "sweep page")
    return app


def _set_sweep(app: object, start: float, end: float, points: int) -> None:
    app.number_input(key="sweep_start_control").set_value(start)  # type: ignore[attr-defined]
    app.number_input(key="sweep_end_control").set_value(end)  # type: ignore[attr-defined]
    app.number_input(key="sweep_points_control").set_value(points)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("start", "end", "points"),
    ((20.0, 1.0, 5), (1.0, 20.0, 2), (5.0, 6.0, 2)),
    ids=("inverted", "two points", "narrow"),
)
def test_a_valid_but_unusual_sweep_runs(
    start: float, end: float, points: int, app_errors: Errors
) -> None:
    app = _sweep_app(app_errors)
    _set_sweep(app, start, end, points)
    button(app, "RUN SWEEP").click().run()  # type: ignore[arg-type]
    assert_clean(app, app_errors, "sweep")  # type: ignore[arg-type]
    sweep = app.session_state["results"]["sweep"]  # type: ignore[attr-defined]
    assert len(sweep.points) == points


def test_the_maximum_point_count_runs(app_errors: Errors) -> None:
    app = _sweep_app(app_errors)
    _set_sweep(app, 1.0, 20.0, MAX_SWEEP_POINTS)
    button(app, "RUN SWEEP").click().run()  # type: ignore[arg-type]
    assert_clean(app, app_errors, "maximum sweep")  # type: ignore[arg-type]
    assert len(app.session_state["results"]["sweep"].points) == MAX_SWEEP_POINTS  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("start", "end", "reason"),
    (
        (5.0, 5.0, "must differ"),
        (-1.0, 20.0, "must be positive"),
        (1.0, 1.0e300, "Pressure must be between"),
    ),
    ids=("equal bounds", "negative", "beyond the range"),
)
def test_an_invalid_sweep_is_refused_with_its_reason(
    start: float, end: float, reason: str, app_errors: Errors
) -> None:
    app = _sweep_app(app_errors)
    _set_sweep(app, start, end, 5)
    button(app, "RUN SWEEP").click().run()  # type: ignore[arg-type]
    assert_clean(app, app_errors, "invalid sweep")  # type: ignore[arg-type]
    assert "sweep" not in app.session_state["results"]  # type: ignore[attr-defined]
    assert any(
        "Submission unavailable" in item.value and reason in item.value
        for item in app.error  # type: ignore[attr-defined]
    )


@pytest.mark.parametrize("points", (0, 1, MAX_SWEEP_POINTS + 1))
def test_a_point_count_outside_the_widget_range_is_refused(points: int) -> None:
    with pytest.raises(SweepValidationError, match="between 2 and 60"):
        validate_sweep_request(
            "pressure",
            (50.0, 0.0, 50.0),
            fixed_value=300.0,
            start=1.0,
            end=20.0,
            points=points,
        )


# --- case files ---------------------------------------------------------------


def _good_case() -> str:
    app = new_app()
    return serialize_case(case_from_state(app.session_state)).decode()


def _case_variants() -> dict[str, bytes]:
    good = _good_case()
    document = json.loads(good)
    old = dict(document)
    future = dict(document, schema_version="9.0.0")
    wrong = dict(document, schema="someone.else")
    no_inputs = {key: value for key, value in document.items() if key != "inputs"}
    hot = json.loads(good)
    hot["inputs"]["temperature_k"] = 5000.0
    return {
        "empty": b"",
        "truncated": good[: len(good) // 2].encode(),
        "binary": bytes(range(256)),
        "not an object": b"[1, 2, 3]",
        "deeply nested": b"[" * 50_000 + b"]" * 50_000,
        "oversized": b'{"padding": "' + b"x" * 1_200_000 + b'"}',
        "future schema": json.dumps(future).encode(),
        "wrong schema": json.dumps(wrong).encode(),
        "missing inputs": json.dumps(no_inputs).encode(),
        "outside the input range": json.dumps(hot).encode(),
        "old schema 1.0.0": json.dumps(old).encode(),
    }


VARIANTS = _case_variants()


@pytest.mark.parametrize("name", VARIANTS)
def test_every_case_file_loads_or_is_refused_cleanly(
    name: str, app_errors: Errors
) -> None:
    app = new_app()
    before = {key: app.session_state[key] for key in ("methane_pct", "temperature_k")}
    app.file_uploader[0].set_value((f"{name}.json", VARIANTS[name], "application/json"))
    app.run()
    button(app, "Load case").click().run()
    assert_clean(app, app_errors, name)
    if name == "old schema 1.0.0":
        assert any("Case loaded" in item.value for item in app.success)
        return
    assert any(item.value.startswith("Case load unavailable:") for item in app.error)
    after = {key: app.session_state[key] for key in ("methane_pct", "temperature_k")}
    assert after == before


def test_the_loader_refuses_deep_nesting_with_a_case_file_error() -> None:
    with pytest.raises(CaseFileError, match="nested too deeply"):
        load_case(b"[" * 100_000 + b"]" * 100_000)


# --- navigation -----------------------------------------------------------------


def test_every_page_renders_before_any_calculation(app_errors: Errors) -> None:
    app = new_app()
    for page in PAGE_FILES:
        go(app, page)
        assert_clean(app, app_errors, page)
    for page in reversed(PAGE_FILES):
        go(app, page)
        assert_clean(app, app_errors, page)


def test_unit_changes_after_a_result_render_every_page(app_errors: Errors) -> None:
    app = new_app()
    run_flash(app)
    for temperature, pressure in (("°F", "psi"), ("°C", "bar"), ("K", "Pa")):
        app.segmented_control(key="temperature_unit").set_value(temperature).run()
        app.segmented_control(key="pressure_unit").set_value(pressure).run()
        for page in PAGE_FILES:
            go(app, page)
            assert_clean(app, app_errors, f"{temperature}/{pressure}: {page}")


def test_an_invalid_edit_after_a_result_keeps_every_page_clean(
    app_errors: Errors,
) -> None:
    app = new_app()
    run_flash(app)
    set_inputs(app, composition=(0.0, 0.0, 0.0))
    run_flash(app)
    for page in PAGE_FILES:
        go(app, page)
        assert_clean(app, app_errors, page)
