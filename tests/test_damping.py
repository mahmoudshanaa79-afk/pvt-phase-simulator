"""Tests for safeguarded fixed damping of successive-substitution log K."""

from math import inf, nan

import pytest

from pvt_phase_simulator.eos.flash import (
    FUGACITY_EQUILIBRIUM_TOLERANCE,
    LOG_K_UPDATE_TOLERANCE,
    FlashConvergenceStatus,
    FlashPhaseState,
    calculate_damped_log_k_values,
    calculate_two_phase_flash,
    phase_interaction_provenance_from_stability,
)
from pvt_phase_simulator.eos.phase_envelope import (
    EnvelopeContinuationSettings,
    EnvelopeTerminationReason,
    trace_bubble_branch,
)
from pvt_phase_simulator.eos.phase_stability import analyze_mixture_phase_stability
from pvt_phase_simulator.eos.saturation_pressure import (
    INNER_LOG_K_TOLERANCE,
    TRIVIAL_STATE_DIAGNOSTIC_CODE,
    InnerSaturationStatus,
    SaturationKind,
    SaturationStatus,
    calculate_saturation_pressure,
    evaluate_saturation_pressure,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    Component,
    FluidMixture,
    MixtureComponent,
)


def _mixture(
    components: tuple[Component, ...], composition: tuple[float, ...]
) -> FluidMixture:
    return FluidMixture(
        tuple(
            MixtureComponent(component, fraction)
            for component, fraction in zip(components, composition, strict=True)
        )
    )


def _methane_ethane() -> FluidMixture:
    return _mixture((METHANE, ETHANE), (0.5, 0.5))


def _methane_propane() -> FluidMixture:
    return _mixture((METHANE, PROPANE), (0.6, 0.4))


def test_log_k_damping_formula_and_exact_undamped_path() -> None:
    current = (2.0, -1.0)
    target = (-2.0, 3.0)
    assert calculate_damped_log_k_values(current, target, 0.25) == (1.0, 0.0)
    assert calculate_damped_log_k_values(current, target, 1.0) is target


@pytest.mark.parametrize("factor", [0.0, -0.1, 1.000001, nan, inf, -inf])
def test_invalid_damping_factors_are_rejected_by_public_apis(factor: float) -> None:
    with pytest.raises(ValueError, match="successive_substitution_damping_factor"):
        calculate_damped_log_k_values((0.0,), (1.0,), factor)
    with pytest.raises(ValueError, match="successive_substitution_damping_factor"):
        calculate_two_phase_flash(
            _methane_ethane(),
            170.0,
            100_000.0,
            successive_substitution_damping_factor=factor,
        )
    with pytest.raises(ValueError, match="successive_substitution_damping_factor"):
        calculate_saturation_pressure(
            _methane_ethane(),
            180.0,
            SaturationKind.BUBBLE_POINT,
            successive_substitution_damping_factor=factor,
        )
    with pytest.raises(ValueError, match="successive_substitution_damping_factor"):
        EnvelopeContinuationSettings(
            205.0,
            5.0,
            successive_substitution_damping_factor=factor,
        )


def test_flash_lambda_one_is_exactly_historical() -> None:
    historical = calculate_two_phase_flash(_methane_ethane(), 170.0, 100_000.0)
    explicit = calculate_two_phase_flash(
        _methane_ethane(),
        170.0,
        100_000.0,
        successive_substitution_damping_factor=1.0,
    )
    assert explicit == historical


def test_damped_flash_is_deterministic_and_preserves_physics() -> None:
    first = calculate_two_phase_flash(
        _methane_ethane(),
        170.0,
        100_000.0,
        successive_substitution_damping_factor=0.5,
    )
    second = calculate_two_phase_flash(
        _methane_ethane(),
        170.0,
        100_000.0,
        successive_substitution_damping_factor=0.5,
    )
    assert first == second
    assert first.phase_state is FlashPhaseState.TWO_PHASE
    assert first.convergence_status is FlashConvergenceStatus.CONVERGED
    assert first.vapor_fraction is not None and 0.0 < first.vapor_fraction < 1.0
    assert first.liquid_phase is not None and first.vapor_phase is not None
    assert sum(first.liquid_phase.composition) == pytest.approx(1.0, abs=1e-12)
    assert sum(first.vapor_phase.composition) == pytest.approx(1.0, abs=1e-12)
    assert max(abs(value) for value in first.material_balance_residuals) <= 1e-10
    assert (
        max(abs(value) for value in first.equilibrium_residuals if value is not None)
        <= FUGACITY_EQUILIBRIUM_TOLERANCE
    )


def test_damped_flash_preserves_component_order_equivariance() -> None:
    forward = calculate_two_phase_flash(
        _methane_propane(),
        180.0,
        500_000.0,
        successive_substitution_damping_factor=0.5,
    )
    reverse = calculate_two_phase_flash(
        _mixture((PROPANE, METHANE), (0.4, 0.6)),
        180.0,
        500_000.0,
        successive_substitution_damping_factor=0.5,
    )
    assert forward.convergence_status is reverse.convergence_status
    assert forward.vapor_fraction == pytest.approx(reverse.vapor_fraction, abs=1e-12)
    assert forward.liquid_phase is not None and reverse.liquid_phase is not None
    assert forward.vapor_phase is not None and reverse.vapor_phase is not None
    assert forward.liquid_phase.composition == pytest.approx(
        tuple(reversed(reverse.liquid_phase.composition)), abs=1e-12
    )
    assert forward.vapor_phase.composition == pytest.approx(
        tuple(reversed(reverse.vapor_phase.composition)), abs=1e-12
    )


def test_damping_preserves_structured_single_phase_flash() -> None:
    result = calculate_two_phase_flash(
        _mixture((METHANE, ETHANE), (0.7, 0.3)),
        300.0,
        10_000_000.0,
        successive_substitution_damping_factor=0.5,
    )
    assert result.phase_state is FlashPhaseState.SINGLE_PHASE
    assert result.convergence_status is FlashConvergenceStatus.NOT_ATTEMPTED
    assert not result.iteration_history


def test_tiny_damped_flash_step_does_not_cause_false_convergence() -> None:
    result = calculate_two_phase_flash(
        _methane_ethane(),
        170.0,
        100_000.0,
        maximum_iterations=1,
        successive_substitution_damping_factor=1e-12,
    )
    iteration = result.iteration_history[0]
    damped_step = max(
        abs(updated - current)
        for updated, current in zip(
            iteration.updated_log_k_values, iteration.log_k_values, strict=True
        )
    )
    assert damped_step < LOG_K_UPDATE_TOLERANCE
    assert iteration.maximum_log_k_residual > LOG_K_UPDATE_TOLERANCE
    assert result.convergence_status is not FlashConvergenceStatus.CONVERGED


@pytest.mark.parametrize(
    "kind", [SaturationKind.BUBBLE_POINT, SaturationKind.DEW_POINT]
)
def test_saturation_lambda_one_is_exactly_historical(kind: SaturationKind) -> None:
    historical = calculate_saturation_pressure(_methane_ethane(), 180.0, kind)
    explicit = calculate_saturation_pressure(
        _methane_ethane(),
        180.0,
        kind,
        successive_substitution_damping_factor=1.0,
    )
    assert explicit == historical


def test_damped_dew_preserves_physical_branch_and_order_invariance() -> None:
    forward = calculate_saturation_pressure(
        _methane_propane(),
        250.0,
        SaturationKind.DEW_POINT,
        successive_substitution_damping_factor=0.5,
    )
    repeated = calculate_saturation_pressure(
        _methane_propane(),
        250.0,
        SaturationKind.DEW_POINT,
        successive_substitution_damping_factor=0.5,
    )
    reverse = calculate_saturation_pressure(
        _mixture((PROPANE, METHANE), (0.4, 0.6)),
        250.0,
        SaturationKind.DEW_POINT,
        successive_substitution_damping_factor=0.5,
    )
    assert forward == repeated
    assert forward.status is SaturationStatus.CONVERGED
    assert forward.pressure_pa == pytest.approx(575_360.2360506197, rel=1e-11)
    assert reverse.pressure_pa == pytest.approx(forward.pressure_pa, rel=1e-11)
    assert forward.incipient_composition == pytest.approx(
        tuple(reversed(reverse.incipient_composition)), abs=1e-10
    )
    assert sum(forward.incipient_composition) == pytest.approx(1.0, abs=1e-12)
    assert forward.maximum_fugacity_equilibrium_residual is not None
    assert forward.maximum_fugacity_equilibrium_residual <= 1e-8


def test_damped_bubble_is_deterministic_and_preserves_objective() -> None:
    first = calculate_saturation_pressure(
        _methane_ethane(),
        180.0,
        SaturationKind.BUBBLE_POINT,
        successive_substitution_damping_factor=0.5,
    )
    second = calculate_saturation_pressure(
        _methane_ethane(),
        180.0,
        SaturationKind.BUBBLE_POINT,
        successive_substitution_damping_factor=0.5,
    )
    assert first == second
    assert first.status is SaturationStatus.CONVERGED
    assert first.pressure_residual is not None
    assert abs(first.pressure_residual) <= 1e-8
    assert sum(first.incipient_composition) == pytest.approx(1.0, abs=1e-12)


def test_damping_preserves_structured_saturation_not_found() -> None:
    result = calculate_saturation_pressure(
        _methane_ethane(),
        250.0,
        SaturationKind.BUBBLE_POINT,
        successive_substitution_damping_factor=0.5,
    )
    assert result.status is SaturationStatus.NOT_FOUND
    assert result.pressure_pa is None
    assert (
        result.failure_reason == "No trustworthy saturation-pressure bracket was found."
    )
    assert any(
        diagnostic.code == TRIVIAL_STATE_DIAGNOSTIC_CODE
        for diagnostic in result.diagnostics
    )


def test_damping_preserves_pure_component_saturation_exception() -> None:
    mixture = _mixture((METHANE,), (1.0,))
    historical = calculate_saturation_pressure(
        mixture, 150.0, SaturationKind.BUBBLE_POINT
    )
    damped = calculate_saturation_pressure(
        mixture,
        150.0,
        SaturationKind.BUBBLE_POINT,
        successive_substitution_damping_factor=0.5,
    )
    assert historical.status is SaturationStatus.CONVERGED
    assert damped.status is SaturationStatus.CONVERGED
    assert damped.pressure_pa == historical.pressure_pa
    assert damped.incipient_composition == (1.0,)


def test_tiny_damped_saturation_step_does_not_cause_false_convergence() -> None:
    mixture = _methane_ethane()
    stability = analyze_mixture_phase_stability(mixture, 180.0, 1_500_000.0)
    result = evaluate_saturation_pressure(
        mixture,
        180.0,
        1_500_000.0,
        SaturationKind.BUBBLE_POINT,
        phase_interaction_provenance_from_stability(stability),
        maximum_iterations=1,
        successive_substitution_damping_factor=1e-12,
    )
    iteration = result.history[0]
    damped_step = max(
        abs(updated - current)
        for updated, current in zip(
            iteration.updated_log_k_values, iteration.log_k_values, strict=True
        )
    )
    assert damped_step < INNER_LOG_K_TOLERANCE
    assert iteration.maximum_log_k_residual > INNER_LOG_K_TOLERANCE
    assert result.status is not InnerSaturationStatus.CONVERGED
    assert not result.converged


def test_envelope_lambda_one_is_exactly_historical() -> None:
    historical = trace_bubble_branch(
        _methane_ethane(),
        EnvelopeContinuationSettings(210.0, 5.0, maximum_points=6),
        200.0,
    )
    explicit = trace_bubble_branch(
        _methane_ethane(),
        EnvelopeContinuationSettings(
            210.0,
            5.0,
            maximum_points=6,
            successive_substitution_damping_factor=1.0,
        ),
        200.0,
    )
    assert explicit == historical


@pytest.mark.parametrize(
    ("settings", "start", "termination"),
    [
        (
            EnvelopeContinuationSettings(
                205.0,
                5.0,
                maximum_points=5,
                minimum_temperature_step_k=2.5,
                maximum_predictor_log_pressure_error=1e-6,
                successive_substitution_damping_factor=0.5,
            ),
            200.0,
            EnvelopeTerminationReason.BRANCH_LOST,
        ),
        (
            EnvelopeContinuationSettings(
                205.0,
                5.0,
                maximum_points=6,
                allow_global_fallback=False,
                local_log_pressure_half_span=1e-9,
                maximum_local_expansions=0,
                successive_substitution_damping_factor=0.5,
            ),
            200.0,
            EnvelopeTerminationReason.MINIMUM_STEP_REACHED,
        ),
    ],
)
def test_damped_envelope_preserves_structured_termination(
    settings: EnvelopeContinuationSettings,
    start: float,
    termination: EnvelopeTerminationReason,
) -> None:
    first = trace_bubble_branch(_methane_ethane(), settings, start)
    second = trace_bubble_branch(_methane_ethane(), settings, start)
    assert first == second
    assert first.termination_reason is termination


def test_damped_forward_and_reverse_envelopes_agree() -> None:
    mixture = _methane_ethane()
    forward = trace_bubble_branch(
        mixture,
        EnvelopeContinuationSettings(
            210.0,
            5.0,
            maximum_points=6,
            successive_substitution_damping_factor=0.5,
        ),
        200.0,
    )
    reverse = trace_bubble_branch(
        mixture,
        EnvelopeContinuationSettings(
            200.0,
            -5.0,
            maximum_points=6,
            successive_substitution_damping_factor=0.5,
        ),
        210.0,
    )
    forward_points = {round(point.temperature_k, 9): point for point in forward.points}
    reverse_points = {round(point.temperature_k, 9): point for point in reverse.points}
    shared = sorted(set(forward_points) & set(reverse_points))
    assert len(shared) >= 3
    for temperature in shared:
        ahead = forward_points[temperature]
        behind = reverse_points[temperature]
        assert ahead.pressure_pa == pytest.approx(behind.pressure_pa, rel=1e-11)
        assert ahead.log_k_values == pytest.approx(behind.log_k_values, abs=1e-9)


def test_damped_continuation_reaches_continuation_only_state() -> None:
    result = trace_bubble_branch(
        _methane_ethane(),
        EnvelopeContinuationSettings(
            250.0,
            5.0,
            maximum_points=6,
            successive_substitution_damping_factor=0.5,
        ),
        240.0,
    )
    assert result.termination_reason is EnvelopeTerminationReason.TARGET_REACHED
    assert result.points[-1].temperature_k == 250.0
    assert result.points[-1].pressure_pa == pytest.approx(
        6_174_169.157030562, rel=1e-11
    )


def test_damped_pure_trace_preserves_near_critical_termination() -> None:
    result = trace_bubble_branch(
        _mixture((METHANE,), (1.0,)),
        EnvelopeContinuationSettings(
            175.0,
            5.0,
            maximum_points=8,
            near_critical_root_stop=1.0,
            near_critical_root_warning=1.0,
            successive_substitution_damping_factor=0.5,
        ),
        150.0,
    )
    assert result.termination_reason is EnvelopeTerminationReason.NEAR_CRITICAL
