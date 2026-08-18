"""Tests for safeguarded vector-secant log-K acceleration."""

from math import inf, nan

import pytest

import pvt_phase_simulator.eos.flash as flash_module
from pvt_phase_simulator.eos.flash import (
    FUGACITY_EQUILIBRIUM_TOLERANCE,
    LOG_K_UPDATE_TOLERANCE,
    FlashConvergenceStatus,
    FlashPhaseState,
    SafeguardedLogKAccelerationResult,
    SuccessiveSubstitutionAccelerationStatus,
    calculate_safeguarded_log_k_acceleration,
    calculate_two_phase_flash,
)
from pvt_phase_simulator.eos.phase_envelope import (
    EnvelopeContinuationSettings,
    EnvelopeTerminationReason,
    trace_bubble_branch,
)
from pvt_phase_simulator.eos.saturation_pressure import (
    TRIVIAL_STATE_DIAGNOSTIC_CODE,
    SaturationKind,
    SaturationStatus,
    calculate_saturation_pressure,
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


def _acceleration_counts(iterations: tuple[object, ...]) -> tuple[int, int]:
    records = [
        iteration.acceleration  # type: ignore[attr-defined]
        for iteration in iterations
        if iteration.acceleration is not None  # type: ignore[attr-defined]
    ]
    accepted = sum(
        item.status is SuccessiveSubstitutionAccelerationStatus.ACCEPTED
        for item in records
    )
    rejected = sum(item.status.value.startswith("rejected_") for item in records)
    return accepted, rejected


def test_vector_secant_formula_accepts_bounded_improving_proposal() -> None:
    result = calculate_safeguarded_log_k_acceleration(
        (1.0, 1.0),
        (1.5, 1.5),
        (0.0, 0.0),
        (1.0, 1.0),
        True,
    )
    assert result.status is SuccessiveSubstitutionAccelerationStatus.ACCEPTED
    assert result.extrapolation_factor == pytest.approx(1.0)
    assert result.target_log_k_values == pytest.approx((2.0, 2.0))
    assert result.predicted_residual_norm == pytest.approx(0.0)
    assert result.proposal_step_norm == pytest.approx(1.0)


def test_disabled_acceleration_returns_exact_historical_target() -> None:
    target = (0.5, -0.25)
    result = calculate_safeguarded_log_k_acceleration((0.0, 0.0), target, None, None)
    assert result.status is SuccessiveSubstitutionAccelerationStatus.DISABLED
    assert result.target_log_k_values is target


@pytest.mark.parametrize(
    ("current", "target", "previous", "previous_target", "status"),
    [
        (
            (1.0,),
            (3.0,),
            (0.0,),
            (1.0,),
            SuccessiveSubstitutionAccelerationStatus.REJECTED_RESIDUAL_WORSENING,
        ),
        (
            (1.0,),
            (1.9,),
            (0.0,),
            (1.0,),
            SuccessiveSubstitutionAccelerationStatus.REJECTED_STEP_LIMIT,
        ),
        (
            (1.0,),
            (1.5,),
            (nan,),
            (1.0,),
            SuccessiveSubstitutionAccelerationStatus.REJECTED_NONFINITE_HISTORY,
        ),
        (
            (1.0,),
            (1.5,),
            (0.0,),
            (0.5,),
            SuccessiveSubstitutionAccelerationStatus.REJECTED_DEGENERATE_SECANT,
        ),
    ],
)
def test_acceleration_rejection_falls_back_to_exact_ordinary_target(
    current: tuple[float, ...],
    target: tuple[float, ...],
    previous: tuple[float, ...],
    previous_target: tuple[float, ...],
    status: SuccessiveSubstitutionAccelerationStatus,
) -> None:
    result = calculate_safeguarded_log_k_acceleration(
        current, target, previous, previous_target, True
    )
    assert result.status is status
    assert result.target_log_k_values is target
    assert all(value not in (inf, -inf) for value in result.target_log_k_values)


@pytest.mark.parametrize("invalid", [0, 1, "yes", None])
def test_acceleration_enable_setting_requires_boolean(invalid: object) -> None:
    with pytest.raises(
        ValueError, match="successive_substitution_acceleration_enabled"
    ):
        calculate_two_phase_flash(
            _methane_ethane(),
            170.0,
            100_000.0,
            successive_substitution_acceleration_enabled=invalid,  # type: ignore[arg-type]
        )
    with pytest.raises(
        ValueError, match="successive_substitution_acceleration_enabled"
    ):
        calculate_saturation_pressure(
            _methane_ethane(),
            180.0,
            SaturationKind.BUBBLE_POINT,
            successive_substitution_acceleration_enabled=invalid,  # type: ignore[arg-type]
        )
    with pytest.raises(
        ValueError, match="successive_substitution_acceleration_enabled"
    ):
        EnvelopeContinuationSettings(
            205.0,
            5.0,
            successive_substitution_acceleration_enabled=invalid,  # type: ignore[arg-type]
        )


def test_flash_acceleration_disabled_is_exactly_historical() -> None:
    historical = calculate_two_phase_flash(_methane_ethane(), 170.0, 100_000.0)
    explicit = calculate_two_phase_flash(
        _methane_ethane(),
        170.0,
        100_000.0,
        successive_substitution_acceleration_enabled=False,
    )
    assert explicit == historical
    assert all(item.acceleration is None for item in explicit.iteration_history)


@pytest.mark.parametrize(
    "kind", [SaturationKind.BUBBLE_POINT, SaturationKind.DEW_POINT]
)
def test_saturation_acceleration_disabled_is_exactly_historical(
    kind: SaturationKind,
) -> None:
    historical = calculate_saturation_pressure(_methane_ethane(), 180.0, kind)
    explicit = calculate_saturation_pressure(
        _methane_ethane(),
        180.0,
        kind,
        successive_substitution_acceleration_enabled=False,
    )
    assert explicit == historical
    assert all(
        item.acceleration is None
        for evaluation in explicit.evaluation_history
        for item in evaluation.history
    )


def test_accelerated_flash_is_deterministic_physical_and_useful() -> None:
    mixture = _mixture((METHANE, PROPANE), (0.5, 0.5))
    historical = calculate_two_phase_flash(mixture, 150.0, 100_000.0)
    first = calculate_two_phase_flash(
        mixture,
        150.0,
        100_000.0,
        successive_substitution_acceleration_enabled=True,
    )
    second = calculate_two_phase_flash(
        mixture,
        150.0,
        100_000.0,
        successive_substitution_acceleration_enabled=True,
    )
    assert first == second
    assert first.convergence_status is FlashConvergenceStatus.CONVERGED
    assert len(first.iteration_history) < len(historical.iteration_history)
    accepted, rejected = _acceleration_counts(first.iteration_history)
    assert accepted >= 1
    assert rejected >= 1
    assert first.vapor_fraction is not None and 0.0 < first.vapor_fraction < 1.0
    assert first.liquid_phase is not None and first.vapor_phase is not None
    assert sum(first.liquid_phase.composition) == pytest.approx(1.0, abs=1e-12)
    assert sum(first.vapor_phase.composition) == pytest.approx(1.0, abs=1e-12)
    assert max(abs(value) for value in first.material_balance_residuals) <= 1e-10
    assert (
        max(abs(value) for value in first.equilibrium_residuals if value is not None)
        <= FUGACITY_EQUILIBRIUM_TOLERANCE
    )


@pytest.mark.parametrize("damping_factor", [1.0, 0.5])
def test_acceleration_interacts_explicitly_with_damping(
    damping_factor: float,
) -> None:
    result = calculate_two_phase_flash(
        _methane_ethane(),
        170.0,
        100_000.0,
        successive_substitution_damping_factor=damping_factor,
        successive_substitution_acceleration_enabled=True,
    )
    assert result.convergence_status is FlashConvergenceStatus.CONVERGED
    assert _acceleration_counts(result.iteration_history)[0] >= 1
    for iteration in result.iteration_history:
        if iteration.acceleration is None:
            continue
        target = iteration.acceleration.target_log_k_values
        expected = tuple(
            current + damping_factor * (candidate - current)
            for current, candidate in zip(iteration.log_k_values, target, strict=True)
        )
        assert iteration.updated_log_k_values == pytest.approx(expected, abs=1e-15)


def test_accelerated_flash_is_component_order_equivariant() -> None:
    forward = calculate_two_phase_flash(
        _methane_propane(),
        180.0,
        100_000.0,
        successive_substitution_acceleration_enabled=True,
    )
    reverse = calculate_two_phase_flash(
        _mixture((PROPANE, METHANE), (0.4, 0.6)),
        180.0,
        100_000.0,
        successive_substitution_acceleration_enabled=True,
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


def test_acceleration_preserves_structured_single_phase_flash() -> None:
    result = calculate_two_phase_flash(
        _methane_ethane(),
        300.0,
        10_000_000.0,
        successive_substitution_acceleration_enabled=True,
    )
    assert result.phase_state is FlashPhaseState.SINGLE_PHASE
    assert result.convergence_status is FlashConvergenceStatus.NOT_ATTEMPTED
    assert result.iteration_history == ()


def test_accelerated_step_cannot_establish_false_flash_convergence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def frozen_proposal(
        current: tuple[float, ...],
        target: tuple[float, ...],
        previous: tuple[float, ...] | None,
        previous_target: tuple[float, ...] | None,
        enabled: bool,
    ) -> SafeguardedLogKAccelerationResult:
        residual = max(abs(a - b) for a, b in zip(current, target, strict=True))
        return SafeguardedLogKAccelerationResult(
            target_log_k_values=current,
            status=SuccessiveSubstitutionAccelerationStatus.ACCEPTED,
            extrapolation_factor=0.0,
            current_residual_norm=residual,
            previous_residual_norm=None,
            predicted_residual_norm=0.0,
            proposal_step_norm=0.0,
            ordinary_step_norm=residual,
        )

    monkeypatch.setattr(
        flash_module, "calculate_safeguarded_log_k_acceleration", frozen_proposal
    )
    result = calculate_two_phase_flash(
        _methane_ethane(),
        170.0,
        100_000.0,
        successive_substitution_acceleration_enabled=True,
    )
    assert result.convergence_status is not FlashConvergenceStatus.CONVERGED
    assert result.iteration_history[0].maximum_log_k_residual > LOG_K_UPDATE_TOLERANCE
    assert result.iteration_history[0].updated_log_k_values == (
        result.iteration_history[0].log_k_values
    )


@pytest.mark.parametrize(
    "kind", [SaturationKind.BUBBLE_POINT, SaturationKind.DEW_POINT]
)
def test_acceleration_preserves_physical_saturation_branches(
    kind: SaturationKind,
) -> None:
    historical = calculate_saturation_pressure(_methane_ethane(), 180.0, kind)
    accelerated = calculate_saturation_pressure(
        _methane_ethane(),
        180.0,
        kind,
        successive_substitution_acceleration_enabled=True,
    )
    assert accelerated.status is SaturationStatus.CONVERGED
    assert accelerated.pressure_pa == pytest.approx(historical.pressure_pa, rel=1e-11)
    assert sum(accelerated.incipient_composition) == pytest.approx(1.0, abs=1e-12)
    assert accelerated.maximum_fugacity_equilibrium_residual is not None
    assert accelerated.maximum_fugacity_equilibrium_residual <= 1e-8
    iterations = tuple(
        item
        for evaluation in accelerated.evaluation_history
        for item in evaluation.history
    )
    assert _acceleration_counts(iterations)[0] >= 1


def test_accelerated_methane_propane_dew_preserves_true_branch() -> None:
    result = calculate_saturation_pressure(
        _methane_propane(),
        250.0,
        SaturationKind.DEW_POINT,
        successive_substitution_acceleration_enabled=True,
    )
    assert result.status is SaturationStatus.CONVERGED
    assert result.pressure_pa == pytest.approx(575_969.5124486194, rel=1e-11)
    assert any(
        diagnostic.code == TRIVIAL_STATE_DIAGNOSTIC_CODE
        for diagnostic in result.diagnostics
    )


def test_acceleration_preserves_trivial_rejection_and_pure_exception() -> None:
    trivial = calculate_saturation_pressure(
        _methane_ethane(),
        250.0,
        SaturationKind.BUBBLE_POINT,
        successive_substitution_acceleration_enabled=True,
    )
    assert trivial.status is SaturationStatus.NOT_FOUND
    assert trivial.pressure_pa is None
    assert any(
        diagnostic.code == TRIVIAL_STATE_DIAGNOSTIC_CODE
        for diagnostic in trivial.diagnostics
    )
    pure = calculate_saturation_pressure(
        _mixture((METHANE,), (1.0,)),
        150.0,
        SaturationKind.BUBBLE_POINT,
        successive_substitution_acceleration_enabled=True,
    )
    assert pure.status is SaturationStatus.CONVERGED
    assert pure.incipient_composition == (1.0,)


def test_accelerated_envelope_is_deterministic_and_preserves_branch_identity() -> None:
    settings = EnvelopeContinuationSettings(
        210.0,
        5.0,
        maximum_points=6,
        successive_substitution_acceleration_enabled=True,
    )
    first = trace_bubble_branch(_methane_ethane(), settings, 200.0)
    second = trace_bubble_branch(_methane_ethane(), settings, 200.0)
    assert first == second
    assert first.termination_reason is EnvelopeTerminationReason.TARGET_REACHED
    temperatures = tuple(point.temperature_k for point in first.points)
    assert temperatures[0] == 200.0
    assert temperatures[-1] == 210.0
    assert all(
        left < right
        for left, right in zip(temperatures, temperatures[1:], strict=False)
    )
    historical = trace_bubble_branch(
        _methane_ethane(),
        EnvelopeContinuationSettings(210.0, 5.0, maximum_points=6),
        200.0,
    )
    assert first.points[-1].pressure_pa == pytest.approx(
        historical.points[-1].pressure_pa, rel=1e-11
    )


def test_acceleration_reaches_real_continuation_only_state() -> None:
    result = trace_bubble_branch(
        _methane_ethane(),
        EnvelopeContinuationSettings(
            250.0,
            5.0,
            maximum_points=6,
            successive_substitution_acceleration_enabled=True,
        ),
        240.0,
    )
    assert result.termination_reason is EnvelopeTerminationReason.TARGET_REACHED
    assert result.points[-1].temperature_k == 250.0
    assert result.points[-1].pressure_pa == pytest.approx(
        6_172_720.661334422, rel=1e-11
    )


@pytest.mark.parametrize(
    ("settings", "termination"),
    [
        (
            EnvelopeContinuationSettings(
                205.0,
                5.0,
                maximum_points=5,
                minimum_temperature_step_k=2.5,
                maximum_predictor_log_pressure_error=1e-6,
                successive_substitution_acceleration_enabled=True,
            ),
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
                successive_substitution_acceleration_enabled=True,
            ),
            EnvelopeTerminationReason.MINIMUM_STEP_REACHED,
        ),
    ],
)
def test_acceleration_preserves_structured_envelope_failures(
    settings: EnvelopeContinuationSettings,
    termination: EnvelopeTerminationReason,
) -> None:
    result = trace_bubble_branch(_methane_ethane(), settings, 200.0)
    assert result.termination_reason is termination
