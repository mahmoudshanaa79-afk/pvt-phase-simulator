"""Tests for non-blocking Peng-Robinson diagnostics."""

from dataclasses import FrozenInstanceError

import pytest

from pvt_phase_simulator.eos.diagnostics import (
    DiagnosticCategory,
    DiagnosticSeverity,
    EOSDiagnostic,
    evaluate_mixture_eos_diagnostics,
)
from pvt_phase_simulator.eos.mixing_rules import (
    calculate_mixture_compressibility_roots,
    calculate_peng_robinson_mixture_parameters,
)
from pvt_phase_simulator.eos.mixture_fugacity import (
    calculate_mixture_fugacity_coefficients,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    FluidMixture,
    MixtureComponent,
)


def _binary_mixture() -> FluidMixture:
    return FluidMixture((MixtureComponent(METHANE, 0.7), MixtureComponent(ETHANE, 0.3)))


def test_defaulted_interactions_emit_typed_data_quality_diagnostic() -> None:
    parameters = calculate_peng_robinson_mixture_parameters(
        _binary_mixture(), 300.0, 10_000_000.0
    )
    diagnostic = evaluate_mixture_eos_diagnostics(parameters)[0]
    assert diagnostic.code == "DEFAULTED_BINARY_INTERACTIONS"
    assert diagnostic.severity is DiagnosticSeverity.WARNING
    assert diagnostic.category is DiagnosticCategory.DATA_QUALITY
    assert diagnostic.value == 1.0


def test_nominal_critical_coordinates_emit_conditioning_diagnostic() -> None:
    mixture = FluidMixture((MixtureComponent(METHANE, 1.0),))
    parameters = calculate_peng_robinson_mixture_parameters(
        mixture,
        METHANE.critical_temperature_k,
        METHANE.critical_pressure_pa,
    )
    diagnostics = evaluate_mixture_eos_diagnostics(parameters)
    assert any(
        item.code == "NEAR_NOMINAL_COMPONENT_CRITICAL_POINT"
        and item.category is DiagnosticCategory.NUMERICAL_CONDITIONING
        and item.value == 0.0
        for item in diagnostics
    )


def test_alpha_turning_region_emits_model_applicability_diagnostic() -> None:
    mixture = FluidMixture((MixtureComponent(METHANE, 1.0),))
    parameters = calculate_peng_robinson_mixture_parameters(mixture, 3_000.0, 1e6)
    diagnostics = evaluate_mixture_eos_diagnostics(parameters)
    assert any(
        item.code == "ALPHA_CORRELATION_TURNING_REGION"
        and item.category is DiagnosticCategory.MODEL_APPLICABILITY
        and item.value is not None
        and item.value < 0.0
        for item in diagnostics
    )


def test_diagnostic_records_are_immutable_and_machine_readable() -> None:
    diagnostic = EOSDiagnostic(
        code="EXAMPLE",
        severity=DiagnosticSeverity.INFO,
        category=DiagnosticCategory.DATA_QUALITY,
        message="Example diagnostic.",
        value=1.0,
    )
    with pytest.raises(FrozenInstanceError):
        diagnostic.value = 2.0  # type: ignore[misc]


def test_diagnostics_do_not_change_fugacity_results() -> None:
    parameters = calculate_peng_robinson_mixture_parameters(
        _binary_mixture(), 300.0, 10_000_000.0
    )
    root = calculate_mixture_compressibility_roots(
        _binary_mixture(), 300.0, 10_000_000.0
    )[0]
    before = calculate_mixture_fugacity_coefficients(parameters, root)
    assert evaluate_mixture_eos_diagnostics(parameters)
    after = calculate_mixture_fugacity_coefficients(parameters, root)
    assert after == before
