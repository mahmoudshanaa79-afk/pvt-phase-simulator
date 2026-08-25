"""Semantic tests for the Streamlit application boundary."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from app.adapters import (
    InputValidationError,
    adapt_critical_result,
    adapt_flash_result,
    load_module17_records,
    relative_pressure_error_percent,
    run_validated_flash,
    validate_scientific_inputs,
)
from app.state import get_result, initialize_session, result_is_stale, store_result
from pvt_phase_simulator.eos.critical_point import (
    CriticalPointStatus,
    solve_mixture_critical_point,
)
from pvt_phase_simulator.eos.flash import calculate_two_phase_flash
from pvt_phase_simulator.fluid_models import FluidMixture
from pvt_phase_simulator.plotting import (
    PressureUnit,
    plot_validation_pressure_error,
    plot_validation_pressure_parity,
    plot_validation_retrospective_diagnostics,
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


def test_module21_validation_figures_keep_sign_and_retrospective_separation() -> None:
    records = load_module17_records(ROOT)
    parity = plot_validation_pressure_parity(
        records, direction="bubble", pressure_unit=PressureUnit.MPA
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


def test_app_code_contains_labels_but_no_thermodynamic_implementation() -> None:
    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "app").glob("*.py")
    )
    assert (
        "Turning indicators are continuation geometry, not critical points" in sources
    )
    assert "Not production prediction" in sources
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
