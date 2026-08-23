"""Focused Module 18 pseudo-arclength continuation tests."""

from dataclasses import replace
from math import log

import numpy as np
import pytest

import pvt_phase_simulator.eos.pseudo_arclength as pseudo_module
from pvt_phase_simulator.eos.phase_envelope import (
    EnvelopeBranchKind,
    EnvelopeContinuationSettings,
    trace_bubble_branch,
)
from pvt_phase_simulator.eos.pseudo_arclength import (
    PseudoArclengthCorrectorStatus,
    PseudoArclengthSettings,
    PseudoArclengthTerminationReason,
    build_augmented_jacobian,
    calculate_pseudo_arclength_tangent,
    correct_pseudo_arclength_prediction,
    evaluate_saturation_continuation_system,
    predict_pseudo_arclength_state,
    pseudo_arclength_constraint,
    trace_pseudo_arclength_branch,
    trace_pseudo_arclength_curve,
    weighted_norm,
)
from pvt_phase_simulator.eos.saturation_pressure import (
    SaturationKind,
    SaturationStatus,
    calculate_saturation_pressure,
    saturation_phase_roles_are_consistent,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    FluidMixture,
    MixtureComponent,
)


def _binary() -> FluidMixture:
    return FluidMixture((MixtureComponent(METHANE, 0.5), MixtureComponent(ETHANE, 0.5)))


def _fold_system(state: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x, y = state
    return np.array((x - y * y,)), np.array(((1.0, -2.0 * y),))


def _bubble_state(temperature_k: float = 200.0) -> tuple[float, ...]:
    result = calculate_saturation_pressure(
        _binary(),
        temperature_k,
        SaturationKind.BUBBLE_POINT,
        saturation_newton_enabled=True,
    )
    assert result.status is SaturationStatus.CONVERGED
    assert result.pressure_pa is not None
    return (
        result.incipient_composition[0],
        log(result.pressure_pa),
        log(temperature_k),
    )


@pytest.fixture(scope="module")
def pseudo_bubble() -> pseudo_module.PseudoArclengthBranchResult:
    return trace_pseudo_arclength_branch(
        _binary(),
        EnvelopeBranchKind.BUBBLE,
        PseudoArclengthSettings(
            initial_temperature_step_k=2.0,
            maximum_points=5,
        ),
        200.0,
    )


def test_settings_validate_dimensionless_step_and_weights() -> None:
    settings = PseudoArclengthSettings(
        initial_temperature_step_k=1.0,
        state_weights=(2.0, 3.0, 4.0),
    )
    assert settings.initial_arclength_step == 0.02
    with pytest.raises(ValueError, match="weights"):
        replace(settings, state_weights=(1.0, 0.0, 1.0))


def test_weighted_state_norm_honors_scaling() -> None:
    assert weighted_norm((1.0, 2.0), (4.0, 0.25)) == pytest.approx(5.0**0.5)


def test_tangent_is_in_null_space_and_normalized() -> None:
    jacobian = np.array(((1.0, -2.0),))
    tangent = np.asarray(calculate_pseudo_arclength_tangent(jacobian, (1.0, 1.0)))
    assert np.linalg.norm(jacobian @ tangent, ord=np.inf) < 1e-14
    assert weighted_norm(tangent, (1.0, 1.0)) == pytest.approx(1.0)


def test_tangent_default_sign_is_deterministic() -> None:
    first = calculate_pseudo_arclength_tangent(((1.0, -2.0),), (1.0, 1.0))
    second = calculate_pseudo_arclength_tangent(((1.0, -2.0),), (1.0, 1.0))
    assert first == second
    assert first[int(np.argmax(np.abs(first)))] > 0.0


def test_tangent_preserves_previous_orientation() -> None:
    previous = (-2.0 / 5.0**0.5, -1.0 / 5.0**0.5)
    tangent = calculate_pseudo_arclength_tangent(
        ((1.0, -2.0),), (1.0, 1.0), previous_tangent=previous
    )
    assert np.dot(tangent, previous) > 0.0


def test_tangent_respects_scaled_state_coordinates() -> None:
    tangent = calculate_pseudo_arclength_tangent(
        ((1.0, -10.0),), (100.0, 0.01), orientation_hint=(-10.0, -1.0)
    )
    assert abs(np.dot(np.array(((1.0, -10.0),))[0], tangent)) < 1e-13
    assert weighted_norm(tangent, (100.0, 0.01)) == pytest.approx(1.0)


def test_tangent_rejects_non_unique_null_space() -> None:
    with pytest.raises(ValueError, match="one-dimensional"):
        calculate_pseudo_arclength_tangent(((0.0, 0.0),), (1.0, 1.0))


def test_predictor_uses_oriented_normalized_tangent() -> None:
    assert predict_pseudo_arclength_state((1.0, 2.0), (0.6, 0.8), 0.5) == (
        1.3,
        2.4,
    )


def test_arclength_constraint_is_weighted_predictor_hyperplane() -> None:
    assert pseudo_arclength_constraint(
        (2.0, 3.0), (1.0, 1.0), (0.5, -0.25), (2.0, 4.0)
    ) == pytest.approx(-1.0)


def test_augmented_jacobian_is_square_with_exact_constraint_row() -> None:
    augmented = np.asarray(
        build_augmented_jacobian(((1.0, -2.0),), (0.5, 0.25), (4.0, 2.0))
    )
    assert augmented.shape == (2, 2)
    assert augmented[-1] == pytest.approx((2.0, 0.5))
    assert np.linalg.matrix_rank(augmented) == 2


def test_corrector_converges_on_generic_parabola() -> None:
    tangent = calculate_pseudo_arclength_tangent(
        _fold_system(np.array((1.0, -1.0)))[1],
        (1.0, 1.0),
        orientation_hint=(-1.0, 1.0),
    )
    predictor = predict_pseudo_arclength_state((1.0, -1.0), tangent, 0.2)
    result = correct_pseudo_arclength_prediction(
        _fold_system, predictor, tangent, (1.0, 1.0), tolerance=1e-12
    )
    assert result.status is PseudoArclengthCorrectorStatus.CONVERGED
    assert result.state is not None
    assert abs(result.state[0] - result.state[1] ** 2) < 1e-12


def test_generic_trace_crosses_fold_and_stays_on_manifold() -> None:
    result = trace_pseudo_arclength_curve(
        _fold_system,
        (1.0, -1.0),
        (0.81, -0.9),
        (1.0, 1.0),
        initial_step=0.12,
        maximum_step=0.12,
        maximum_points=18,
        tolerance=1e-12,
    )
    y_values = tuple(state[1] for state in result.states)
    x_tangents = tuple(tangent[0] for tangent in result.tangents)
    assert min(y_values) < 0.0 < max(y_values)
    assert any(
        left < 0.0 < right
        for left, right in zip(x_tangents, x_tangents[1:], strict=False)
    )
    assert max(abs(x - y * y) for x, y in result.states) < 1e-11


def test_generic_trace_orientation_never_flips_arbitrarily() -> None:
    result = trace_pseudo_arclength_curve(
        _fold_system,
        (1.0, -1.0),
        (0.81, -0.9),
        (1.0, 1.0),
        maximum_points=15,
    )
    assert all(
        np.dot(left, right) > 0.0
        for left, right in zip(result.tangents, result.tangents[1:], strict=False)
    )


def test_easy_generic_steps_grow_within_maximum() -> None:
    result = trace_pseudo_arclength_curve(
        _fold_system,
        (1.0, -1.0),
        (0.81, -0.9),
        (1.0, 1.0),
        initial_step=0.02,
        maximum_step=0.05,
        maximum_points=6,
        easy_iteration_limit=10,
    )
    assert result.step_size_increases > 0
    assert max(result.step_size_history) <= 0.05


def test_hard_generic_steps_reduce_after_acceptance() -> None:
    result = trace_pseudo_arclength_curve(
        _fold_system,
        (1.0, -1.0),
        (0.81, -0.9),
        (1.0, 1.0),
        initial_step=0.1,
        maximum_step=0.1,
        maximum_points=4,
        easy_iteration_limit=0,
    )
    assert result.step_size_reductions > 0
    assert result.step_size_history[-1] < result.step_size_history[0]


def test_failed_large_step_retries_at_smaller_step() -> None:
    result = trace_pseudo_arclength_curve(
        _fold_system,
        (1.0, -1.0),
        (0.81, -0.9),
        (1.0, 1.0),
        initial_step=0.5,
        minimum_step=0.05,
        maximum_step=0.5,
        maximum_points=3,
        validator=lambda state: bool(state[1] < -0.75),
    )
    assert result.accepted_steps == 1
    assert result.rejected_steps >= 1
    assert result.step_size_reductions >= 1


def test_minimum_step_failure_is_structured() -> None:
    result = trace_pseudo_arclength_curve(
        _fold_system,
        (1.0, -1.0),
        (0.81, -0.9),
        (1.0, 1.0),
        initial_step=0.1,
        minimum_step=0.04,
        maximum_step=0.1,
        maximum_points=3,
        validator=lambda state: False,
    )
    assert (
        result.termination_reason
        is PseudoArclengthTerminationReason.MINIMUM_ARCLENGTH_STEP_REACHED
    )
    assert result.accepted_steps == 0


def test_eos_state_uses_simplex_ln_pressure_and_ln_temperature() -> None:
    state = _bubble_state()
    evaluation = evaluate_saturation_continuation_system(
        _binary(), EnvelopeBranchKind.BUBBLE, state
    )
    assert len(state) == 3
    assert sum(evaluation.incipient_composition) == pytest.approx(1.0)
    assert all(0.0 < value < 1.0 for value in evaluation.incipient_composition)
    assert evaluation.pressure_pa == pytest.approx(np.exp(state[-2]))
    assert evaluation.temperature_k == pytest.approx(np.exp(state[-1]))


def test_eos_augmented_physical_jacobian_matches_central_difference() -> None:
    state = np.asarray(_bubble_state())
    analytical = np.asarray(
        evaluate_saturation_continuation_system(
            _binary(), EnvelopeBranchKind.BUBBLE, state
        ).jacobian
    )
    numerical = np.empty_like(analytical)
    for column in range(len(state)):
        step = 1e-6
        plus = state.copy()
        minus = state.copy()
        plus[column] += step
        minus[column] -= step
        plus_residual = np.asarray(
            evaluate_saturation_continuation_system(
                _binary(), EnvelopeBranchKind.BUBBLE, plus
            ).residuals
        )
        minus_residual = np.asarray(
            evaluate_saturation_continuation_system(
                _binary(), EnvelopeBranchKind.BUBBLE, minus
            ).residuals
        )
        numerical[:, column] = (plus_residual - minus_residual) / (2.0 * step)
    assert analytical == pytest.approx(numerical, rel=2e-6, abs=2e-7)
    incorrectly_unscaled_temperature = analytical[:, -1] / np.exp(state[-1])
    assert np.max(abs(incorrectly_unscaled_temperature - numerical[:, -1])) > 0.1


def test_eos_pseudo_trace_preserves_phase_role_and_nontriviality(
    pseudo_bubble: pseudo_module.PseudoArclengthBranchResult,
) -> None:
    assert len(pseudo_bubble.points) == 5
    for point in pseudo_bubble.points:
        assert point.parent_root < point.incipient_root
        assert (
            max(
                abs(feed - incipient)
                for feed, incipient in zip(
                    (0.5, 0.5), point.incipient_composition, strict=True
                )
            )
            > 1e-3
        )


def test_eos_pseudo_trace_matches_fixed_temperature_production_branch(
    pseudo_bubble: pseudo_module.PseudoArclengthBranchResult,
) -> None:
    for point in pseudo_bubble.points:
        reference = calculate_saturation_pressure(
            _binary(),
            point.temperature_k,
            SaturationKind.BUBBLE_POINT,
            saturation_newton_enabled=True,
        )
        assert reference.status is SaturationStatus.CONVERGED
        assert reference.pressure_pa is not None
        assert point.pressure_pa == pytest.approx(reference.pressure_pa, rel=2e-9)
        assert point.incipient_composition == pytest.approx(
            reference.incipient_composition, abs=2e-9
        )
        assert reference.parent_phase is not None
        assert reference.incipient_phase is not None
        assert point.parent_root == pytest.approx(
            reference.parent_phase.selected_compressibility_factor, abs=2e-9
        )
        assert point.incipient_root == pytest.approx(
            reference.incipient_phase.selected_compressibility_factor, abs=2e-9
        )
        assert saturation_phase_roles_are_consistent(
            SaturationKind.BUBBLE_POINT, point.parent_root, point.incipient_root
        )


def test_phase_role_loss_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pseudo_module, "saturation_phase_roles_are_consistent", lambda *args: False
    )
    result = trace_pseudo_arclength_branch(
        _binary(),
        EnvelopeBranchKind.BUBBLE,
        PseudoArclengthSettings(initial_temperature_step_k=2.0, maximum_points=3),
        200.0,
    )
    assert result.termination_reason is PseudoArclengthTerminationReason.PHASE_ROLE_LOST
    assert len(result.points) == 2


def test_trivial_state_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pseudo_module,
        "multicomponent_saturation_is_near_trivial",
        lambda *args: True,
    )
    result = trace_pseudo_arclength_branch(
        _binary(),
        EnvelopeBranchKind.BUBBLE,
        PseudoArclengthSettings(initial_temperature_step_k=2.0, maximum_points=3),
        200.0,
    )
    assert result.termination_reason is PseudoArclengthTerminationReason.TRIVIAL_STATE
    assert len(result.points) == 2


def test_near_critical_stop_uses_existing_envelope_thresholds() -> None:
    safeguards = EnvelopeContinuationSettings(
        target_temperature_k=202.0,
        initial_temperature_step_k=2.0,
        near_critical_composition_warning=1.0,
        near_critical_log_k_warning=10.0,
        near_critical_root_warning=1.0,
        near_critical_composition_stop=1.0,
        near_critical_log_k_stop=10.0,
        near_critical_root_stop=1.0,
    )
    result = trace_pseudo_arclength_branch(
        _binary(),
        EnvelopeBranchKind.BUBBLE,
        PseudoArclengthSettings(initial_temperature_step_k=2.0, maximum_points=3),
        200.0,
        physical_safeguards=safeguards,
    )
    assert result.termination_reason is PseudoArclengthTerminationReason.NEAR_CRITICAL
    assert len(result.points) == 2


def test_pseudo_arclength_is_opt_in_and_legacy_result_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = EnvelopeContinuationSettings(210.0, 5.0, maximum_points=4)
    reference = trace_bubble_branch(_binary(), settings, 200.0)
    monkeypatch.setattr(
        pseudo_module,
        "trace_pseudo_arclength_branch",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("opt-in called")),
    )
    repeated = trace_bubble_branch(_binary(), settings, 200.0)
    assert repeated == reference


def test_pseudo_arclength_result_is_deterministic(
    pseudo_bubble: pseudo_module.PseudoArclengthBranchResult,
) -> None:
    repeated = trace_pseudo_arclength_branch(
        _binary(),
        EnvelopeBranchKind.BUBBLE,
        pseudo_bubble.settings,
        200.0,
    )
    assert repeated == pseudo_bubble


def test_pseudo_trace_records_work_and_adaptation(
    pseudo_bubble: pseudo_module.PseudoArclengthBranchResult,
) -> None:
    assert pseudo_bubble.accepted_arclength_steps == 3
    assert pseudo_bubble.rejected_steps == 0
    assert pseudo_bubble.corrector_iteration_history == (2, 2, 2)
    assert pseudo_bubble.equilibrium_evaluations > len(pseudo_bubble.points)
    assert pseudo_bubble.step_size_increases == 3
    assert pseudo_bubble.step_size_reductions == 0


def test_ch4_c3_bubble_crosses_regular_pressure_turning_point() -> None:
    mixture = FluidMixture(
        (MixtureComponent(METHANE, 0.5), MixtureComponent(PROPANE, 0.5))
    )
    result = trace_pseudo_arclength_branch(
        mixture,
        EnvelopeBranchKind.BUBBLE,
        PseudoArclengthSettings(
            initial_temperature_step_k=2.0,
            initial_arclength_step=0.04,
            maximum_arclength_step=0.08,
            maximum_points=18,
        ),
        210.0,
    )
    before, after = result.points[-2:]
    assert before.tangent is not None
    assert after.tangent is not None
    assert before.tangent[-2] > 0.0 > after.tangent[-2]
    assert before.tangent[-1] > 0.0 and after.tangent[-1] > 0.0
    assert after.pressure_turning_point
    assert result.pressure_turning_point_count == 1
    assert result.temperature_turning_point_count == 0
    assert max(point.maximum_fugacity_residual for point in result.points) < 1e-8
    assert all(point.parent_root < point.incipient_root for point in result.points)
    assert (
        min(abs(point.parent_root - point.incipient_root) for point in result.points)
        > 0.05
    )


def test_zero_fraction_uses_the_existing_active_simplex_reduction() -> None:
    reduced = FluidMixture(
        (MixtureComponent(METHANE, 0.5), MixtureComponent(PROPANE, 0.5))
    )
    zero_fraction = FluidMixture(
        (
            MixtureComponent(METHANE, 0.5),
            MixtureComponent(ETHANE, 0.0),
            MixtureComponent(PROPANE, 0.5),
        )
    )
    settings = PseudoArclengthSettings(initial_temperature_step_k=2.0, maximum_points=3)
    reference = trace_pseudo_arclength_branch(
        reduced, EnvelopeBranchKind.BUBBLE, settings, 210.0
    )
    result = trace_pseudo_arclength_branch(
        zero_fraction, EnvelopeBranchKind.BUBBLE, settings, 210.0
    )
    assert np.asarray(tuple(point.state for point in result.points)) == pytest.approx(
        np.asarray(tuple(point.state for point in reference.points))
    )


def test_pure_component_is_exempt_from_multicomponent_triviality() -> None:
    pure = FluidMixture((MixtureComponent(METHANE, 1.0),))
    result = trace_pseudo_arclength_branch(
        pure,
        EnvelopeBranchKind.BUBBLE,
        PseudoArclengthSettings(initial_temperature_step_k=2.0, maximum_points=3),
        150.0,
    )
    assert result.termination_reason is PseudoArclengthTerminationReason.MAXIMUM_POINTS
    assert len(result.points) == 3
    assert all(point.incipient_composition == (1.0,) for point in result.points)
