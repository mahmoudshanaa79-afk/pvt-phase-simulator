"""Tests for the bounded engineering sweep layer.

The sweep layer must call the existing audited flash API and must never invent,
smooth, or hide a value the production result did not supply.
"""

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pvt_phase_simulator_ui.exports import (
    SWEEP_CSV_COLUMNS,
    build_sweep_export_document,
    export_json_bytes,
    export_sweep_csv_bytes,
)
from pvt_phase_simulator_ui.sweeps import (
    DEFAULT_SWEEP_POINTS,
    MAX_SWEEP_POINTS,
    MIN_SWEEP_POINTS,
    SweepValidationError,
    run_pressure_sweep,
    run_sweep,
    run_temperature_sweep,
    sweep_axis_values,
    validate_sweep_request,
)
from pvt_phase_simulator_ui.units import PressureUnit, TemperatureUnit, UnitPreferences

ROOT = Path(__file__).resolve().parents[1]
COMPOSITION = (50.0, 0.0, 50.0)


# --------------------------------------------------------------------- stubs


def _phase(z: float) -> SimpleNamespace:
    return SimpleNamespace(
        composition=(0.5, 0.0, 0.5), selected_compressibility_factor=z
    )


def _stub_result(
    *,
    phase_state: str,
    convergence: str,
    stability: str,
    vapor_fraction: float | None = None,
    liquid_fraction: float | None = None,
    liquid_z: float | None = None,
    vapor_z: float | None = None,
    single_phase_root: float | None = None,
    failure_reason: str | None = None,
) -> Any:
    """A minimal public-result stand-in for the fields the adapters read."""

    return SimpleNamespace(
        phase_state=phase_state,
        convergence_status=convergence,
        temperature_k=300.0,
        pressure_pa=5.0e6,
        vapor_fraction=vapor_fraction,
        liquid_fraction=liquid_fraction,
        liquid_phase=None if liquid_z is None else _phase(liquid_z),
        vapor_phase=None if vapor_z is None else _phase(vapor_z),
        single_phase_root=single_phase_root,
        final_k_values=None,
        equilibrium_residuals=(),
        material_balance_residuals=(),
        iteration_history=(),
        failure_reason=failure_reason,
        phase_stability=SimpleNamespace(status=stability),
    )


def _single_phase_api(*_: object) -> Any:
    return _stub_result(
        phase_state="single_phase",
        convergence="not_attempted",
        stability="stable",
        single_phase_root=0.5828298153218295,
    )


def _two_phase_api(*_: object) -> Any:
    return _stub_result(
        phase_state="two_phase",
        convergence="converged",
        stability="unstable",
        vapor_fraction=0.19956455877388646,
        liquid_fraction=0.8004354412261135,
        liquid_z=0.2934273404241833,
        vapor_z=0.5986875870131091,
    )


def _structured_failure_api(*_: object) -> Any:
    return _stub_result(
        phase_state="two_phase",
        convergence="line_search_failed",
        stability="unstable",
        failure_reason="Line search failed.",
    )


def _raising_api(*_: object) -> Any:
    raise RuntimeError("solver exploded")


# ----------------------------------------------------------------- axis math


def test_sweep_axis_is_evenly_spaced_with_exact_endpoints() -> None:
    values = sweep_axis_values(1.0, 20.0, 5)
    assert values == (1.0, 5.75, 10.5, 15.25, 20.0)
    assert values[0] == 1.0
    assert values[-1] == 20.0


def test_sweep_axis_endpoint_is_exact_for_awkward_steps() -> None:
    values = sweep_axis_values(1.0, 10.0, 7)
    assert values[0] == 1.0
    assert values[-1] == 10.0
    assert len(values) == 7


def test_descending_sweep_is_permitted_and_ordered() -> None:
    values = sweep_axis_values(20.0, 1.0, 4)
    assert values[0] == 20.0
    assert values[-1] == 1.0
    assert list(values) == sorted(values, reverse=True)


# ------------------------------------------------------------ determinism


def test_deterministic_pressure_sweep_repeats_exactly() -> None:
    first = run_pressure_sweep(
        COMPOSITION,
        temperature_k=300.0,
        start_pressure_mpa=2.0,
        end_pressure_mpa=20.0,
        points=5,
        flash_api=_two_phase_api,
    )
    second = run_pressure_sweep(
        COMPOSITION,
        temperature_k=300.0,
        start_pressure_mpa=2.0,
        end_pressure_mpa=20.0,
        points=5,
        flash_api=_two_phase_api,
    )
    assert first.points == second.points
    assert first.abscissae() == (2.0, 6.5, 11.0, 15.5, 20.0)
    assert all(point.temperature_k == 300.0 for point in first.points)


def test_deterministic_temperature_sweep_repeats_exactly() -> None:
    first = run_temperature_sweep(
        COMPOSITION,
        pressure_mpa=5.0,
        start_temperature_k=260.0,
        end_temperature_k=300.0,
        points=5,
        flash_api=_two_phase_api,
    )
    second = run_temperature_sweep(
        COMPOSITION,
        pressure_mpa=5.0,
        start_temperature_k=260.0,
        end_temperature_k=300.0,
        points=5,
        flash_api=_two_phase_api,
    )
    assert first.points == second.points
    assert first.abscissae() == (260.0, 270.0, 280.0, 290.0, 300.0)
    assert all(point.pressure_mpa == 5.0 for point in first.points)


def test_sweep_calls_the_flash_api_exactly_once_per_point() -> None:
    calls: list[tuple[float, float]] = []

    def spy(mixture: object, temperature_k: float, pressure_pa: float) -> Any:
        calls.append((temperature_k, pressure_pa))
        return _two_phase_api()

    run_pressure_sweep(
        COMPOSITION,
        temperature_k=300.0,
        start_pressure_mpa=1.0,
        end_pressure_mpa=5.0,
        points=5,
        flash_api=spy,
    )
    assert len(calls) == 5
    assert [temperature for temperature, _ in calls] == [300.0] * 5
    assert [pressure for _, pressure in calls] == [1e6, 2e6, 3e6, 4e6, 5e6]


def test_field_unit_sweep_calls_engine_with_k_and_pa() -> None:
    calls: list[tuple[float, float]] = []

    def spy(_: object, temperature_k: float, pressure_pa: float) -> Any:
        calls.append((temperature_k, pressure_pa))
        return _two_phase_api()

    request = validate_sweep_request(
        "pressure",
        COMPOSITION,
        fixed_value=80.33,
        start=14.503773773,
        end=43.511321319,
        points=3,
        temperature_unit=TemperatureUnit.FAHRENHEIT,
        pressure_unit=PressureUnit.PSI,
    )
    result = run_sweep(request, flash_api=spy)

    assert [temperature for temperature, _ in calls] == pytest.approx([300.0] * 3)
    assert [pressure for _, pressure in calls] == pytest.approx(
        [100_000.0, 200_000.0, 300_000.0], rel=2e-11
    )
    assert result.abscissae() == request.axis_values()


def test_negative_celsius_sweep_bounds_are_valid_above_absolute_zero() -> None:
    request = validate_sweep_request(
        "temperature",
        COMPOSITION,
        fixed_value=50.0,
        start=-30.0,
        end=30.0,
        points=3,
        temperature_unit=TemperatureUnit.CELSIUS,
        pressure_unit=PressureUnit.BAR,
    )

    result = run_sweep(request, flash_api=_two_phase_api)
    assert [point.temperature_k for point in result.points] == pytest.approx(
        [243.15, 273.15, 303.15]
    )
    assert all(point.pressure_pa == 5_000_000.0 for point in result.points)


# ------------------------------------------------------------- point kinds


def test_single_phase_points_report_only_a_single_phase_root() -> None:
    result = run_pressure_sweep(
        COMPOSITION,
        temperature_k=300.0,
        start_pressure_mpa=18.0,
        end_pressure_mpa=20.0,
        points=3,
        flash_api=_single_phase_api,
    )
    assert result.calculated_count == 3
    for point in result.points:
        assert point.status == "calculated"
        assert point.phase_state == "single_phase"
        assert point.single_phase_z == 0.5828298153218295
        assert point.vapor_fraction is None
        assert point.liquid_fraction is None
        assert point.liquid_z is None
        assert point.vapor_z is None


def test_two_phase_points_report_fractions_and_both_z_factors() -> None:
    result = run_pressure_sweep(
        COMPOSITION,
        temperature_k=300.0,
        start_pressure_mpa=4.0,
        end_pressure_mpa=6.0,
        points=3,
        flash_api=_two_phase_api,
    )
    assert result.calculated_count == 3
    for point in result.points:
        assert point.phase_state == "two_phase"
        assert point.convergence_status == "converged"
        assert point.vapor_fraction == 0.19956455877388646
        assert point.liquid_fraction == 0.8004354412261135
        assert point.liquid_z == 0.2934273404241833
        assert point.vapor_z == 0.5986875870131091
        assert point.single_phase_z is None


def test_raising_api_produces_explicitly_failed_points() -> None:
    result = run_pressure_sweep(
        COMPOSITION,
        temperature_k=300.0,
        start_pressure_mpa=1.0,
        end_pressure_mpa=3.0,
        points=3,
        flash_api=_raising_api,
    )
    assert result.failed_count == 3
    assert result.calculated_count == 0
    for point in result.points:
        assert point.status == "failed"
        assert point.error is not None
        assert "RuntimeError" in point.error
        assert point.vapor_fraction is None
        assert point.single_phase_z is None
        assert point.phase_state is None


def test_structured_solver_failure_is_reported_as_failed() -> None:
    result = run_pressure_sweep(
        COMPOSITION,
        temperature_k=300.0,
        start_pressure_mpa=1.0,
        end_pressure_mpa=2.0,
        points=2,
        flash_api=_structured_failure_api,
    )
    assert result.failed_count == 2
    for point in result.points:
        assert point.status == "failed"
        assert point.convergence_status == "line_search_failed"
        assert point.failure_reason == "Line search failed."
        assert point.error is None


def test_failed_points_are_not_interpolated_away() -> None:
    calls = {"n": 0}

    def alternating(*_: object) -> Any:
        calls["n"] += 1
        if calls["n"] % 2 == 0:
            raise RuntimeError("point failed")
        return _two_phase_api()

    result = run_pressure_sweep(
        COMPOSITION,
        temperature_k=300.0,
        start_pressure_mpa=1.0,
        end_pressure_mpa=4.0,
        points=4,
        flash_api=alternating,
    )
    assert result.calculated_count == 2
    assert result.failed_count == 2
    assert len(result.points) == 4
    failed = [point for point in result.points if point.status == "failed"]
    assert all(point.vapor_fraction is None for point in failed)


# ------------------------------------------------------------- validation


@pytest.mark.parametrize("points", (MIN_SWEEP_POINTS - 1, 0, -3, MAX_SWEEP_POINTS + 1))
def test_point_count_outside_bounds_is_rejected(points: int) -> None:
    with pytest.raises(SweepValidationError, match="between"):
        validate_sweep_request(
            "pressure",
            COMPOSITION,
            fixed_value=300.0,
            start=1.0,
            end=5.0,
            points=points,
        )


@pytest.mark.parametrize("points", (2.5, "5", True))
def test_non_integer_point_count_is_rejected(points: object) -> None:
    with pytest.raises(SweepValidationError, match="integer"):
        validate_sweep_request(
            "pressure",
            COMPOSITION,
            fixed_value=300.0,
            start=1.0,
            end=5.0,
            points=points,  # type: ignore[arg-type]
        )


def test_equal_bounds_are_rejected() -> None:
    with pytest.raises(SweepValidationError, match="differ"):
        validate_sweep_request(
            "pressure", COMPOSITION, fixed_value=300.0, start=5.0, end=5.0, points=5
        )


@pytest.mark.parametrize(("start", "end"), ((0.0, 5.0), (-1.0, 5.0), (1.0, -5.0)))
def test_non_positive_bounds_are_rejected(start: float, end: float) -> None:
    with pytest.raises(SweepValidationError, match="positive"):
        validate_sweep_request(
            "pressure", COMPOSITION, fixed_value=300.0, start=start, end=end, points=5
        )


def test_non_finite_bounds_are_rejected() -> None:
    with pytest.raises(SweepValidationError, match="finite"):
        validate_sweep_request(
            "pressure",
            COMPOSITION,
            fixed_value=300.0,
            start=float("inf"),
            end=5.0,
            points=5,
        )


@pytest.mark.parametrize("fixed", (0.0, -300.0, float("nan")))
def test_non_positive_fixed_variable_is_rejected(fixed: float) -> None:
    with pytest.raises(SweepValidationError):
        validate_sweep_request(
            "pressure", COMPOSITION, fixed_value=fixed, start=1.0, end=5.0, points=5
        )


def test_composition_that_does_not_total_100_is_rejected() -> None:
    with pytest.raises(SweepValidationError, match="100 mol"):
        validate_sweep_request(
            "pressure",
            (50.0, 0.0, 40.0),
            fixed_value=300.0,
            start=1.0,
            end=5.0,
            points=5,
        )


def test_unknown_sweep_kind_is_rejected() -> None:
    with pytest.raises(SweepValidationError, match="kind"):
        validate_sweep_request(
            "enthalpy",  # type: ignore[arg-type]
            COMPOSITION,
            fixed_value=300.0,
            start=1.0,
            end=5.0,
            points=5,
        )


def test_validation_happens_before_any_production_call() -> None:
    calls: list[object] = []

    def spy(*args: object) -> Any:
        calls.append(args)
        return _two_phase_api()

    with pytest.raises(SweepValidationError):
        run_pressure_sweep(
            COMPOSITION,
            temperature_k=300.0,
            start_pressure_mpa=5.0,
            end_pressure_mpa=5.0,
            points=5,
            flash_api=spy,
        )
    assert calls == []


# ----------------------------------------------------------------- exports


def _mixed_sweep() -> Any:
    calls = {"n": 0}

    def mixed(*_: object) -> Any:
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("point failed")
        if calls["n"] == 3:
            return _single_phase_api()
        return _two_phase_api()

    return run_pressure_sweep(
        COMPOSITION,
        temperature_k=300.0,
        start_pressure_mpa=1.0,
        end_pressure_mpa=4.0,
        points=4,
        flash_api=mixed,
    )


def test_sweep_csv_has_a_header_and_one_row_per_point_including_failures() -> None:
    result = _mixed_sweep()
    text = export_sweep_csv_bytes(result).decode("utf-8-sig")
    rows = list(csv.reader(StringIO(text)))
    assert rows[0] == list(SWEEP_CSV_COLUMNS)
    assert len(rows) == 1 + len(result.points)
    statuses = [row[SWEEP_CSV_COLUMNS.index("status")] for row in rows[1:]]
    assert statuses.count("failed") == result.failed_count
    assert statuses.count("calculated") == result.calculated_count


def test_sweep_csv_is_excel_friendly_utf8_with_bom() -> None:
    payload = export_sweep_csv_bytes(_mixed_sweep())
    assert payload.startswith(b"\xef\xbb\xbf")


def test_sweep_csv_preserves_full_precision() -> None:
    result = _mixed_sweep()
    text = export_sweep_csv_bytes(result).decode("utf-8-sig")
    rows = list(csv.DictReader(StringIO(text)))
    calculated = [row for row in rows if row["status"] == "calculated"]
    two_phase = [row for row in calculated if row["phase_state"] == "two_phase"]
    assert two_phase
    assert float(two_phase[0]["vapor_fraction"]) == 0.19956455877388646
    assert float(two_phase[0]["liquid_z"]) == 0.2934273404241833


def test_sweep_csv_writes_null_rather_than_a_guessed_value() -> None:
    result = _mixed_sweep()
    rows = list(
        csv.DictReader(StringIO(export_sweep_csv_bytes(result).decode("utf-8-sig")))
    )
    failed = [row for row in rows if row["status"] == "failed"]
    assert failed
    assert failed[0]["vapor_fraction"] == "null"
    assert failed[0]["single_phase_z"] == "null"
    assert failed[0]["phase_state"] == "null"


def test_sweep_json_marks_unavailable_values_explicitly() -> None:
    result = _mixed_sweep()
    document = json.loads(export_json_bytes(build_sweep_export_document(result)))
    assert document["summary"] == {
        "requested_points": 4,
        "calculated_points": result.calculated_count,
        "failed_points": result.failed_count,
    }
    failed = [point for point in document["points"] if point["status"] == "failed"]
    assert failed
    assert failed[0]["vapor_fraction"]["status"] == "not_applicable"
    assert failed[0]["vapor_fraction"]["value"] is None
    assert failed[0]["vapor_fraction"]["reason"]

    single = [
        point
        for point in document["points"]
        if point["phase_state"]["value"] == "single_phase"
    ]
    assert single
    assert single[0]["single_phase_z"]["status"] == "available"
    assert single[0]["vapor_fraction"]["status"] == "not_applicable"


def test_sweep_json_preserves_full_precision() -> None:
    result = _mixed_sweep()
    document = json.loads(export_json_bytes(build_sweep_export_document(result)))
    two_phase = [
        point
        for point in document["points"]
        if point["phase_state"]["value"] == "two_phase"
    ]
    assert two_phase
    assert two_phase[0]["vapor_fraction"]["value"] == 0.19956455877388646
    assert two_phase[0]["vapor_z"]["value"] == 0.5986875870131091


def test_sweep_exports_name_selected_and_engine_units() -> None:
    result = _mixed_sweep()
    units = UnitPreferences(TemperatureUnit.FAHRENHEIT, PressureUnit.PSI)
    document = build_sweep_export_document(result, units)

    assert document["metadata"]["engine_units"] == {
        "temperature": "K",
        "pressure": "Pa",
    }
    assert document["metadata"]["presentation_units"] == {
        "temperature": "°F",
        "pressure": "psi",
    }
    first = document["points"][0]
    assert first["temperature_unit"] == "°F"
    assert first["pressure_unit"] == "psi"
    assert first["temperature_k"] == result.points[0].temperature_k
    assert first["pressure_pa"] == result.points[0].pressure_pa

    rows = list(
        csv.DictReader(
            StringIO(export_sweep_csv_bytes(result, units).decode("utf-8-sig"))
        )
    )
    assert rows[0]["temperature_unit"] == "°F"
    assert rows[0]["pressure_unit"] == "psi"
    assert float(rows[0]["temperature_k"]) == result.points[0].temperature_k
    assert float(rows[0]["pressure_pa"]) == result.points[0].pressure_pa


def test_sweep_json_omits_a_timestamp_to_stay_reproducible() -> None:
    document = build_sweep_export_document(_mixed_sweep())
    metadata = document["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["export_timestamp"]["status"] == "omitted"
    assert export_json_bytes(document) == export_json_bytes(
        build_sweep_export_document(_mixed_sweep())
    )


# ------------------------------------------------------- integration + firewall


def test_pressure_sweep_over_the_real_engine_spans_both_phase_regimes() -> None:
    result = run_pressure_sweep(
        COMPOSITION,
        temperature_k=300.0,
        start_pressure_mpa=2.0,
        end_pressure_mpa=20.0,
        points=5,
    )
    assert result.failed_count == 0
    states = {point.phase_state for point in result.points}
    assert "two_phase" in states
    assert "single_phase" in states
    for point in result.points:
        if point.phase_state == "single_phase":
            assert point.single_phase_z is not None
            assert point.vapor_fraction is None
        else:
            assert point.vapor_fraction is not None
            assert point.liquid_z is not None
            assert point.vapor_z is not None
            assert point.single_phase_z is None


def test_temperature_sweep_over_the_real_engine_is_reproducible() -> None:
    kwargs: dict[str, Any] = {
        "pressure_mpa": 5.0,
        "start_temperature_k": 270.0,
        "end_temperature_k": 300.0,
        "points": 4,
    }
    first = run_temperature_sweep(COMPOSITION, **kwargs)
    second = run_temperature_sweep(COMPOSITION, **kwargs)
    assert first.points == second.points
    assert first.abscissae() == (270.0, 280.0, 290.0, 300.0)


def test_sweep_module_implements_no_thermodynamics() -> None:
    source = (ROOT / "src" / "pvt_phase_simulator_ui" / "sweeps.py").read_text(
        encoding="utf-8"
    )
    forbidden_constants = ("0.45724", "0.07780", "0.37464", "1.54226", "0.26992")
    assert not any(constant in source for constant in forbidden_constants)
    forbidden_terms = (
        "def peng_robinson",
        "def fugacity",
        "def rachford_rice",
        "def tpd",
        "def stability",
        "def cubic",
        "np.roots",
        "discriminant",
    )
    assert not any(term in source.lower() for term in forbidden_terms)


def test_sweep_layer_calls_the_audited_flash_api_with_validated_si_inputs() -> None:
    source = (ROOT / "src" / "pvt_phase_simulator_ui" / "sweeps.py").read_text(
        encoding="utf-8"
    )
    assert "calculate_two_phase_flash" in source
    assert "validate_scientific_inputs" in source
    assert "inputs.temperature_k, inputs.pressure_pa" in source


def test_sweep_feature_adds_nothing_to_the_protected_science_package() -> None:
    engine = ROOT / "src" / "pvt_phase_simulator"
    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in engine.rglob("*.py")
    )
    assert "sweep" not in sources.lower()
    assert not list(engine.rglob("*sweep*"))


def test_default_point_count_is_an_engineering_overview_not_a_study() -> None:
    assert MIN_SWEEP_POINTS <= DEFAULT_SWEEP_POINTS <= MAX_SWEEP_POINTS
    assert 20 <= DEFAULT_SWEEP_POINTS <= 25


# --------------------------------------------------------------------- page


def _sweeps_page() -> Any:
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=60).run()
    page = ROOT / "src" / "pvt_phase_simulator_ui" / "pages" / "engineering_sweeps.py"
    return app.switch_page(page).run()


def test_sweeps_page_renders_without_running_a_calculation() -> None:
    app = _sweeps_page()
    assert not app.exception
    assert "Engineering sweeps" in [header.value for header in app.header]
    assert app.session_state["results"] == {}


def test_sweeps_page_requires_a_submitted_flash_before_running() -> None:
    app = _sweeps_page()
    run_buttons = [button for button in app.button if "RUN SWEEP" in button.label]
    assert run_buttons
    assert run_buttons[0].disabled
    assert any("Submit RUN FLASH" in caption.value for caption in app.caption)


def test_sweeps_page_states_that_failed_points_stay_failed() -> None:
    app = _sweeps_page()
    captions = " ".join(caption.value for caption in app.caption)
    assert "FAILED" in captions
    assert "interpolated" in captions


# ------------------------------------------------- chart gaps at failed points


def _series(result: Any, attribute: str) -> tuple[list[float], list[float | None]]:
    from pvt_phase_simulator_ui.views import _sweep_series

    return _sweep_series(result, attribute)


def _segments(y: list[float | None]) -> list[list[float]]:
    """Split a trace into the runs Plotly will actually draw as lines."""

    runs: list[list[float]] = []
    current: list[float] = []
    for value in y:
        if value is None:
            if current:
                runs.append(current)
                current = []
            continue
        current.append(value)
    if current:
        runs.append(current)
    return runs


def _sweep_with_failure_at(failing_index: int, points: int = 5) -> Any:
    calls = {"n": 0}

    def api(*_: object) -> Any:
        index = calls["n"]
        calls["n"] += 1
        if index == failing_index:
            raise RuntimeError("point failed")
        return _two_phase_api()

    return run_pressure_sweep(
        COMPOSITION,
        temperature_k=300.0,
        start_pressure_mpa=1.0,
        end_pressure_mpa=float(points),
        points=points,
        flash_api=api,
    )


def test_valid_contiguous_points_connect_as_one_segment() -> None:
    result = run_pressure_sweep(
        COMPOSITION,
        temperature_k=300.0,
        start_pressure_mpa=1.0,
        end_pressure_mpa=5.0,
        points=5,
        flash_api=_two_phase_api,
    )
    x, y = _series(result, "vapor_fraction")
    assert len(x) == len(y) == 5
    assert None not in y
    assert len(_segments(y)) == 1


def test_a_failed_point_breaks_the_trace() -> None:
    result = _sweep_with_failure_at(2)
    x, y = _series(result, "vapor_fraction")
    assert len(x) == len(y) == 5
    assert y[2] is None
    assert x[2] == result.points[2].pressure_mpa
    assert len(_segments(y)) == 2


def test_an_unavailable_quantity_breaks_the_trace() -> None:
    """A single-phase point supplies no vapor fraction; that is a real gap."""

    calls = {"n": 0}

    def api(*_: object) -> Any:
        index = calls["n"]
        calls["n"] += 1
        return _single_phase_api() if index == 2 else _two_phase_api()

    result = run_pressure_sweep(
        COMPOSITION,
        temperature_k=300.0,
        start_pressure_mpa=1.0,
        end_pressure_mpa=5.0,
        points=5,
        flash_api=api,
    )
    x, y = _series(result, "vapor_fraction")
    assert result.failed_count == 0
    assert len(x) == 5
    assert y[2] is None
    assert len(_segments(y)) == 2


def test_valid_points_after_a_failure_resume_as_a_new_segment() -> None:
    result = _sweep_with_failure_at(1)
    _, y = _series(result, "vapor_fraction")
    segments = _segments(y)
    assert len(segments) == 2
    assert len(segments[0]) == 1
    assert len(segments[1]) == 3
    assert all(value == 0.19956455877388646 for value in segments[1])


def test_no_fabricated_value_is_ever_plotted() -> None:
    result = _sweep_with_failure_at(3)
    for attribute in ("vapor_fraction", "liquid_z", "vapor_z", "single_phase_z"):
        x, y = _series(result, attribute)
        assert len(x) == len(result.points)
        for value, point in zip(y, result.points, strict=True):
            if point.status == "failed":
                assert value is None
            else:
                source = getattr(point, attribute)
                assert value == (None if source is None else float(source))


def test_figures_break_lines_rather_than_connecting_across_gaps() -> None:
    from pvt_phase_simulator_ui.views import _vapor_fraction_figure, _z_factor_figure

    result = _sweep_with_failure_at(2)
    for figure in (_vapor_fraction_figure(result), _z_factor_figure(result)):
        assert figure.data
        for trace in figure.data:
            assert trace.connectgaps is False
            assert len(trace.x) == len(result.points)
            assert any(value is None for value in trace.y)


def test_z_factor_traces_keep_their_own_gaps_per_phase() -> None:
    from pvt_phase_simulator_ui.views import _z_factor_figure

    calls = {"n": 0}

    def api(*_: object) -> Any:
        index = calls["n"]
        calls["n"] += 1
        return _single_phase_api() if index in (0, 4) else _two_phase_api()

    result = run_pressure_sweep(
        COMPOSITION,
        temperature_k=300.0,
        start_pressure_mpa=1.0,
        end_pressure_mpa=5.0,
        points=5,
        flash_api=api,
    )
    figure = _z_factor_figure(result)
    traces = {trace.name: trace for trace in figure.data}
    assert set(traces) == {"Liquid Z", "Vapor Z", "Single-phase Z"}
    assert traces["Liquid Z"].y[0] is None
    assert traces["Liquid Z"].y[4] is None
    assert traces["Single-phase Z"].y[1] is None
    assert _segments(list(traces["Single-phase Z"].y)) == [
        [0.5828298153218295],
        [0.5828298153218295],
    ]


def test_failed_points_remain_in_the_results_table_with_their_status() -> None:
    from pvt_phase_simulator_ui.views import _sweep_table

    result = _sweep_with_failure_at(2)
    frame = _sweep_table(result)
    assert len(frame) == len(result.points)
    assert list(frame["Status"]).count("FAILED") == 1
    failed_row = frame[frame["Status"] == "FAILED"].iloc[0]
    assert failed_row["Point"] == 3
    assert failed_row["Vapor fraction"] == "—"
    assert failed_row["Phase"] == "—"


def test_failed_abscissae_are_still_marked_on_the_charts() -> None:
    from pvt_phase_simulator_ui.views import _vapor_fraction_figure

    result = _sweep_with_failure_at(2)
    figure = _vapor_fraction_figure(result)
    vlines = [
        shape
        for shape in figure.layout.shapes
        if getattr(shape, "line", None) is not None
    ]
    assert len(vlines) == result.failed_count
