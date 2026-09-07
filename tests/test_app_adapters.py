"""Semantic tests for the Streamlit application boundary."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import replace
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from pvt_phase_simulator.eos.critical_point import (
    CriticalPointStatus,
    solve_mixture_critical_point,
)
from pvt_phase_simulator.eos.flash import (
    FlashConvergenceStatus,
    calculate_two_phase_flash,
)
from pvt_phase_simulator.fluid_models import FluidMixture
from pvt_phase_simulator.plotting import (
    PhaseBehaviorPoint,
    PhaseEnvelopePlotData,
    plot_phase_envelope,
    plot_validation_pressure_error,
    plot_validation_pressure_parity,
    plot_validation_retrospective_diagnostics,
)
from pvt_phase_simulator.plotting import (
    PressureUnit as PlotPressureUnit,
)
from pvt_phase_simulator_ui import views
from pvt_phase_simulator_ui.adapters import (
    InputValidationError,
    adapt_critical_result,
    adapt_flash_result,
    flash_presentation_kind,
    load_module17_records,
    location_relative_to_envelope,
    relative_pressure_error_percent,
    run_validated_flash,
    validate_scientific_inputs,
    validation_pressure_error_summary,
)
from pvt_phase_simulator_ui.exports import (
    build_export_document,
    export_csv_bytes,
    export_json_bytes,
)
from pvt_phase_simulator_ui.state import (
    INPUT_EXAMPLES,
    apply_selected_input_example,
    get_result,
    initialize_session,
    result_is_stale,
    store_result,
)
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

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("composition", "temperature", "pressure"),
    (
        ((-1.0, 51.0, 50.0), 300.0, 5.0),
        ((101.0, 0.0, 0.0), 300.0, 5.0),
        ((0.0, 0.0, 0.0), 300.0, 5.0),
        ((50.0, 0.0, 49.0), 300.0, 5.0),
        ((float("nan"), 0.0, 100.0), 300.0, 5.0),
        ((50.0, 0.0, 50.0), float("inf"), 5.0),
        ((50.0, 0.0, 50.0), 300.0, 0.0),
    ),
)
def test_invalid_inputs_never_call_scientific_api(
    composition: tuple[float, float, float], temperature: float, pressure: float
) -> None:
    calls = 0

    def forbidden(_: FluidMixture, __: float, ___: float) -> object:
        nonlocal calls
        calls += 1
        return object()

    with pytest.raises(InputValidationError):
        run_validated_flash(
            composition,
            temperature,
            pressure,
            flash_api=forbidden,  # type: ignore[arg-type]
        )
    assert calls == 0


def test_valid_conversion_and_flash_invocation_are_exact() -> None:
    captured: tuple[FluidMixture, float, float] | None = None
    sentinel = object()

    def fake(mixture: FluidMixture, temperature: float, pressure: float) -> object:
        nonlocal captured
        captured = mixture, temperature, pressure
        return sentinel

    inputs, result = run_validated_flash(
        (50.0, 0.0, 50.0),
        321.5829183194,
        8.53444323606381,
        flash_api=fake,  # type: ignore[arg-type]
    )
    assert result is sentinel
    assert inputs.mole_fractions == (0.5, 0.0, 0.5)
    assert inputs.pressure_pa == 8_534_443.23606381
    assert captured is not None
    assert captured[1:] == (321.5829183194, 8_534_443.23606381)
    assert tuple(item.mole_fraction for item in captured[0].components) == (
        0.5,
        0.0,
        0.5,
    )


@pytest.mark.parametrize("unit", tuple(PressureUnit))
def test_pressure_units_round_trip_without_losing_the_si_value(
    unit: PressureUnit,
) -> None:
    pressure_pa = 8_534_443.23606381
    field_value = pressure_from_pa(pressure_pa, unit)

    assert pressure_to_pa(field_value, unit) == pressure_pa
    assert convert_pressure(field_value, unit, unit) == field_value


@pytest.mark.parametrize("unit", tuple(TemperatureUnit))
def test_temperature_units_round_trip_at_the_boundary(
    unit: TemperatureUnit,
) -> None:
    temperature_k = 321.5829183194
    field_value = temperature_from_k(temperature_k, unit)

    assert temperature_to_k(field_value, unit) == pytest.approx(
        temperature_k, abs=6e-14
    )
    assert convert_temperature(field_value, unit, unit) == field_value


def test_field_unit_flash_reaches_engine_in_k_and_pa_once() -> None:
    captured: tuple[float, float] | None = None

    def fake(_: FluidMixture, temperature_k: float, pressure_pa: float) -> object:
        nonlocal captured
        captured = temperature_k, pressure_pa
        return object()

    inputs, _ = run_validated_flash(
        (50.0, 0.0, 50.0),
        80.33,
        pressure_from_pa(5_000_000.0, PressureUnit.PSI),
        temperature_unit=TemperatureUnit.FAHRENHEIT,
        pressure_unit=PressureUnit.PSI,
        flash_api=fake,  # type: ignore[arg-type]
    )

    assert inputs.temperature_k == pytest.approx(300.0, abs=1e-13)
    assert inputs.pressure_pa == 5_000_000.0
    assert captured == (inputs.temperature_k, inputs.pressure_pa)


@pytest.mark.parametrize(
    ("value", "unit"),
    (
        (0.0, TemperatureUnit.KELVIN),
        (-273.15, TemperatureUnit.CELSIUS),
        (-459.67, TemperatureUnit.FAHRENHEIT),
    ),
)
def test_absolute_zero_is_rejected_in_every_temperature_unit(
    value: float, unit: TemperatureUnit
) -> None:
    with pytest.raises(InputValidationError, match="absolute zero"):
        validate_scientific_inputs(
            (50.0, 0.0, 50.0),
            value,
            1.0,
            temperature_unit=unit,
        )


def test_export_includes_selected_and_engine_units_explicitly() -> None:
    inputs = validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 5.0)
    units = UnitPreferences(TemperatureUnit.CELSIUS, PressureUnit.BAR)

    document = build_export_document(inputs, units=units)

    assert document["metadata"]["engine_units"] == {
        "temperature": "K",
        "pressure": "Pa",
    }
    assert document["metadata"]["presentation_units"] == {
        "temperature": "°C",
        "pressure": "bar",
    }
    assert document["case"]["temperature"] == pytest.approx(26.85)
    assert document["case"]["temperature_unit"] == "°C"
    assert document["case"]["pressure"] == 50.0
    assert document["case"]["pressure_unit"] == "bar"
    assert document["case"]["temperature_k"] == 300.0
    assert document["case"]["pressure_pa"] == 5_000_000.0


def test_flash_adapter_preserves_every_scientific_field() -> None:
    inputs = validate_scientific_inputs((50.0, 0.0, 50.0), 250.0, 3.0)
    result = calculate_two_phase_flash(
        inputs.mixture(), inputs.temperature_k, inputs.pressure_pa
    )
    view = adapt_flash_result(result)
    assert view.phase_state is result.phase_state
    assert view.convergence_status is result.convergence_status
    assert view.vapor_fraction is result.vapor_fraction
    assert view.liquid_fraction is result.liquid_fraction
    assert view.final_k_values is result.final_k_values
    assert view.equilibrium_residuals is result.equilibrium_residuals
    assert view.material_balance_residuals is result.material_balance_residuals
    if result.liquid_phase is not None:
        assert view.liquid_composition is result.liquid_phase.composition
        assert view.liquid_z is result.liquid_phase.selected_compressibility_factor
    if result.vapor_phase is not None:
        assert view.vapor_composition is result.vapor_phase.composition
        assert view.vapor_z is result.vapor_phase.selected_compressibility_factor


def test_structured_flash_failure_is_not_reclassified() -> None:
    inputs = validate_scientific_inputs((50.0, 0.0, 50.0), 250.0, 3.0)
    result = calculate_two_phase_flash(
        inputs.mixture(), inputs.temperature_k, inputs.pressure_pa
    )
    failed = replace(result, failure_reason="LINE_SEARCH_FAILED")
    view = adapt_flash_result(failed)
    assert view.failure_reason == "LINE_SEARCH_FAILED"
    assert view.phase_state is failed.phase_state
    assert view.convergence_status is failed.convergence_status


def test_single_phase_presentation_is_informational_but_failure_is_error() -> None:
    inputs, result = run_validated_flash((50.0, 0.0, 50.0), 300.0, 20.0)
    assert inputs.pressure_pa == 20_000_000.0
    assert flash_presentation_kind(result) == "information"
    assert result.single_phase_root == pytest.approx(0.5828298153218298, abs=2e-12)

    failed = replace(
        result,
        convergence_status=FlashConvergenceStatus.FAILED,
        failure_reason="STRUCTURED_TEST_FAILURE",
    )
    assert flash_presentation_kind(failed) == "error"


def test_current_case_json_preserves_precision_and_unavailable_semantics() -> None:
    inputs, result = run_validated_flash((50.0, 0.0, 50.0), 300.0, 20.0)
    document = build_export_document(inputs, flash_result=result)
    encoded = export_json_bytes(document)
    decoded = json.loads(encoded)
    flash = decoded["results"]["flash"]

    assert encoded == export_json_bytes(document)
    assert decoded["schema"]["version"] == "1.1.0"
    assert decoded["case"]["pressure_pa"] == 20_000_000.0
    assert flash["selected_single_phase_z"]["value"] == result.single_phase_root
    assert flash["selected_single_phase_z"]["value"] == pytest.approx(
        0.5828298153218298, abs=2e-12
    )
    assert flash["vapor_fraction"]["status"] == "not_applicable"
    assert flash["vapor_fraction"]["value"] is None
    assert decoded["results"]["phase_envelope"] == {
        "calculation_status": "not_calculated"
    }
    assert decoded["results"]["critical_point"] == {
        "calculation_status": "not_calculated"
    }


def test_current_case_csv_is_utf8_tidy_and_uses_source_float_values() -> None:
    inputs, result = run_validated_flash((50.0, 0.0, 50.0), 300.0, 20.0)
    encoded = export_csv_bytes(build_export_document(inputs, flash_result=result))
    assert encoded.startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(StringIO(encoded.decode("utf-8-sig"))))
    values = {(row["section"], row["path"]): row["value"] for row in rows}

    assert values[("case", "pressure_pa")] == "20000000.0"
    assert values[("case", "components[0].overall_mole_fraction")] == "0.5"
    assert values[("results", "flash.selected_single_phase_z.value")] == repr(
        result.single_phase_root
    )
    assert values[("results", "flash.vapor_fraction.status")] == "not_applicable"


def test_export_without_calculated_results_does_not_fabricate_fields() -> None:
    inputs = validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 20.0)
    results = build_export_document(inputs)["results"]
    assert results == {
        "flash": {"calculation_status": "not_calculated"},
        "phase_envelope": {"calculation_status": "not_calculated"},
        "critical_point": {"calculation_status": "not_calculated"},
    }


def test_envelope_export_preserves_branch_points_and_termination_evidence() -> None:
    inputs = validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 5.0)
    saturation = SimpleNamespace(
        parent_composition=(0.5, 0.0, 0.5),
        incipient_composition=(0.2, 0.1, 0.7),
        k_values=(0.4, 1.25, 1.4),
        fugacity_equilibrium_residuals=(1.0e-13, None, -2.0e-13),
        maximum_fugacity_equilibrium_residual=2.0e-13,
        composition_sum_residual=4.440892098500626e-16,
        pressure_residual=1.2345678901234567e-10,
    )
    point = SimpleNamespace(
        status="converged",
        temperature_k=300.1234567890123,
        pressure_pa=8_669_987.654321097,
        saturation_result=saturation,
    )
    envelope = SimpleNamespace(
        bubble_branch=SimpleNamespace(
            branch_kind="bubble",
            termination_reason="target_reached",
            termination_message="Bubble target reached.",
            points=(point,),
            rejected_attempts=(object(),),
        ),
        dew_branch=SimpleNamespace(
            branch_kind="dew",
            termination_reason="corrector_failed",
            termination_message="Dew corrector stopped safely.",
            points=(),
            rejected_attempts=(),
        ),
    )
    exported = build_export_document(  # type: ignore[arg-type]
        inputs, envelope_result=envelope
    )["results"]["phase_envelope"]

    assert exported["bubble_branch"]["points"][0]["pressure_pa"] == (
        8_669_987.654321097
    )
    assert exported["bubble_branch"]["points"][0]["pressure_residual"] == (
        1.2345678901234567e-10
    )
    assert exported["bubble_branch"]["rejected_attempt_count"] == 1
    assert exported["dew_branch"] == {
        "branch_kind": "dew",
        "termination_status": "corrector_failed",
        "termination_message": "Dew corrector stopped safely.",
        "accepted_point_count": 0,
        "rejected_attempt_count": 0,
        "points": [],
    }


def test_critical_certification_and_approved_regression() -> None:
    inputs = validate_scientific_inputs((50.0, 0.0, 50.0), 320.0, 8.5)
    result = solve_mixture_critical_point(
        inputs.mixture(), inputs.temperature_k, inputs.pressure_pa
    )
    view = adapt_critical_result(result)
    assert view.certified
    assert view.status is CriticalPointStatus.CONVERGED
    assert view.temperature_k == pytest.approx(321.5829183194, abs=1e-9)
    assert view.pressure_pa == pytest.approx(8_534_443.23606381, abs=1e-6)
    assert cast(float, view.pressure_pa) / 1.0e6 == pytest.approx(
        8.53444323606381, abs=1e-12
    )
    uncertified = replace(
        result,
        status=CriticalPointStatus.LINE_SEARCH_FAILED,
        lambda_min=0.0,
        termination_reason="LINE_SEARCH_FAILED",
    )
    rejected = adapt_critical_result(uncertified)
    assert not rejected.certified
    assert rejected.temperature_k is None
    assert rejected.pressure_pa is None
    assert rejected.lambda_min is None
    certified_export = build_export_document(inputs, critical_result=result)["results"][
        "critical_point"
    ]
    assert certified_export["certified"] is True
    assert certified_export["temperature_k"]["value"] == result.temperature_k
    assert certified_export["pressure_pa"]["value"] == result.pressure_pa

    uncertified_export = build_export_document(inputs, critical_result=uncertified)[
        "results"
    ]["critical_point"]
    assert uncertified_export["certified"] is False
    assert uncertified_export["temperature_k"]["status"] == "unavailable"
    assert uncertified_export["temperature_k"]["value"] is None
    assert uncertified_export["pressure_pa"]["value"] is None
    assert uncertified_export["lambda_min"] == {
        "status": "available",
        "value": 0.0,
    }
    assert uncertified_export["scaled_residual_norm"]["value"] == (
        uncertified.scaled_residual_norm
    )


def test_certified_critical_hover_uses_selected_presentation_units() -> None:
    inputs = validate_scientific_inputs((50.0, 0.0, 50.0), 320.0, 8.5)
    result = solve_mixture_critical_point(
        inputs.mixture(), inputs.temperature_k, inputs.pressure_pa
    )
    figure = plot_phase_envelope(
        PhaseEnvelopePlotData(
            bubble_points=(PhaseBehaviorPoint(300.0, 5_000_000.0),),
            dew_points=(),
        ),
        pressure_unit=PlotPressureUnit.PA,
        critical_point=result,
    )
    critical_trace = next(
        trace for trace in figure.data if trace.name == "Certified critical point"
    )
    source_hover = cast(str, critical_trace.text[0])
    source_temperature_k = float(source_hover.split("<br>T=", 1)[1].split(" K", 1)[0])
    source_pressure_pa = float(source_hover.split("<br>P=", 1)[1].split(" Pa", 1)[0])
    units = UnitPreferences(TemperatureUnit.FAHRENHEIT, PressureUnit.PSI)

    views._presentation_figure(
        figure,
        units,
        x_quantity="temperature",
        y_quantity="pressure",
    )

    hover = cast(str, critical_trace.text[0])
    expected_temperature = views._format_plot_hover_value(
        temperature_from_k(source_temperature_k, units.temperature)
    )
    expected_pressure = views._format_plot_hover_value(
        pressure_from_pa(source_pressure_pa, units.pressure)
    )
    assert f"<br>T={expected_temperature} {units.temperature.value}" in hover
    assert f"<br>P={expected_pressure} {units.pressure.value}" in hover
    assert " K" not in hover
    assert " Pa" not in hover


def test_session_state_is_deterministic_and_marks_scientific_changes_stale() -> None:
    state: dict[str, object] = {}
    first = validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 5.0)
    same = validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 5.0)
    changed = validate_scientific_inputs((49.0, 1.0, 50.0), 300.0, 5.0)
    marker = object()
    initialize_session(state)
    store_result(state, "flash", marker, first)
    initialize_session(state)
    assert get_result(state, "flash") is marker
    assert not result_is_stale(state, "flash", same)
    assert result_is_stale(state, "flash", changed)
    assert result_is_stale(state, "flash", None)


def test_selecting_input_example_only_assigns_input_state() -> None:
    prior_result = object()
    state: dict[str, object] = {
        "results": {"flash": prior_result},
        "submitted_inputs": "prior submission",
        "input_example": INPUT_EXAMPLES[2].label,
    }

    apply_selected_input_example(state)

    assert state["results"] == {"flash": prior_result}
    assert state["submitted_inputs"] == "prior submission"
    assert state["methane_pct"] == 50.0
    assert state["ethane_pct"] == 0.0
    assert state["propane_pct"] == 50.0
    assert state["temperature_k"] == 321.5829183194
    assert state["pressure_mpa"] == 8.53444323606381


def test_module21_validation_figures_keep_sign_and_retrospective_separation() -> None:
    records = load_module17_records(ROOT)
    parity = plot_validation_pressure_parity(
        records, direction="bubble", pressure_unit=PlotPressureUnit.MPA
    )
    error = plot_validation_pressure_error(records, direction="bubble")
    retrospective = plot_validation_retrospective_diagnostics(records)
    assert any("Production bubble prediction" == trace.name for trace in parity.data)
    assert any("Relative Pressure Error" in str(error.layout.title.text) for _ in (0,))
    assert any(
        "not production prediction" in str(trace.name).lower()
        for trace in retrospective.data
    )
    assert relative_pressure_error_percent(90.0, 100.0) == -10.0
    assert relative_pressure_error_percent(110.0, 100.0) == 10.0


def test_validation_summary_uses_only_recorded_absolute_pressure_errors() -> None:
    records = load_module17_records(ROOT)
    state_count, error_count, median_error, worst_error = (
        validation_pressure_error_summary(records, "bubble")
    )
    recorded = sorted(
        abs(cast(float, record.bubble_pressure_relative_error)) * 100.0
        for record in records
        if record.bubble_pressure_relative_error is not None
    )
    assert state_count == len(records)
    assert error_count == len(recorded)
    assert median_error == pytest.approx(
        (recorded[(len(recorded) - 1) // 2] + recorded[len(recorded) // 2]) / 2.0
    )
    assert worst_error == max(recorded)


def test_operating_point_reports_available_branch_and_missing_reason() -> None:
    def point(temperature_k: float, pressure_pa: float) -> SimpleNamespace:
        return SimpleNamespace(
            temperature_k=temperature_k,
            pressure_pa=pressure_pa,
            status="converged",
        )

    result = SimpleNamespace(
        bubble_branch=SimpleNamespace(
            points=(), termination_message="Bubble bracket was not found."
        ),
        dew_branch=SimpleNamespace(
            points=(point(290.0, 2.0e6), point(310.0, 3.0e6)),
            termination_message="Target temperature reached.",
        ),
    )
    message = location_relative_to_envelope(  # type: ignore[arg-type]
        result, 300.0, 5.0e6
    )
    assert message == (
        "Above the interpolated dew branch. Bubble branch unavailable: "
        "Bubble bracket was not found."
    )


def test_ui_envelope_trace_is_centered_on_operating_temperature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 5.0)
    captured: dict[str, object] = {}
    sentinel = object()

    def fake_calculate(*args: object) -> object:
        captured["args"] = args
        return sentinel

    views._calculate_envelope.clear()
    monkeypatch.setattr(views, "calculate_phase_envelope", fake_calculate)
    result = views._calculate_envelope(inputs)
    args = cast(tuple[object, ...], captured["args"])
    bubble_settings = args[1]
    dew_settings = args[2]
    assert result is sentinel
    assert args[3:] == (270.0, 270.0)
    assert bubble_settings.target_temperature_k == 330.0  # type: ignore[attr-defined]
    assert dew_settings.target_temperature_k == 330.0  # type: ignore[attr-defined]
    assert bubble_settings.initial_temperature_step_k == 5.0  # type: ignore[attr-defined]
    assert bubble_settings.maximum_points == 15  # type: ignore[attr-defined]


def test_empty_envelope_branch_is_annotated_with_engine_termination() -> None:
    annotations: list[dict[str, object]] = []
    figure = SimpleNamespace(add_annotation=lambda **kwargs: annotations.append(kwargs))
    result = SimpleNamespace(
        bubble_branch=SimpleNamespace(
            branch_kind="bubble",
            points=(),
            termination_reason="corrector_failed",
            termination_message="No trustworthy bracket was found.",
        ),
        dew_branch=SimpleNamespace(
            branch_kind="dew",
            points=(object(),),
            termination_reason="target_reached",
            termination_message="Target reached.",
        ),
    )
    returned = views._annotate_missing_envelope_branches(  # type: ignore[arg-type]
        figure, result
    )
    assert returned is figure
    assert len(annotations) == 1
    assert annotations[0]["text"] == (
        "Bubble branch not plotted — Corrector failed: "
        "No trustworthy bracket was found."
    )


def test_app_code_contains_labels_but_no_thermodynamic_implementation() -> None:
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "src" / "pvt_phase_simulator_ui").rglob("*.py")
    )
    assert (
        "Turning indicators are continuation geometry, not critical points" in sources
    )
    assert "NOT PRODUCTION PREDICTIONS" in sources
    assert "plot_validation_pressure_parity" in sources
    forbidden_definitions = (
        "def peng_robinson",
        "def fugacity",
        "def rachford_rice",
        "def tpd",
        "def saturation_pressure",
        "def criticality",
    )
    assert not any(
        definition in sources.lower() for definition in forbidden_definitions
    )


@pytest.mark.parametrize(
    ("relative_path", "expected"),
    (
        (
            "tests/golden_master/baseline.csv",
            "530C667AA70EF1EA182F4EDB98624A0A9B9908F149354276CDAC44A87EA7D2BE",
        ),
        (
            "data/component_properties.csv",
            "C6F6BA9AE9C2F4C7F257BBC09A75DF0D7065255868AA46BF3E8C81AC5A8B9B3A",
        ),
        (
            "docs/validation/module17_vle_validation.csv",
            "B14728D51AAC06AF38FC4F4E5F408942B253FEBE32D3E12EC26E9623CFA42482",
        ),
        (
            "docs/validation/module17_vle_validation_summary.json",
            "5B120B77BF05567FCC6A0EE0D0054C6D1DEBA35FE26A7C837352C92017D24870",
        ),
    ),
)
def test_protected_artifact_integrity(relative_path: str, expected: str) -> None:
    digest = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest().upper()
    assert digest == expected
