"""Focused Module 20 tests for the mixture critical-point solver."""

from dataclasses import FrozenInstanceError, replace
from math import exp, log

import numpy as np
import pytest

import pvt_phase_simulator.eos.critical_point as critical_point_module
from pvt_phase_simulator.eos.critical_point import (
    CriticalPointScanSettings,
    CriticalPointSolverSettings,
    CriticalPointStatus,
    CriticalResidualEvaluation,
    JacobianStepFailure,
    ResidualScaling,
    calculate_critical_residual_jacobian,
    log_coordinates,
    physical_coordinates,
    scan_mixture_criticality,
    solve_critical_residual_system,
    solve_mixture_critical_point,
)
from pvt_phase_simulator.eos.criticality import (
    CriticalityStatus,
    calculate_stable_root_mixture_criticality,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    FluidMixture,
    MixtureComponent,
)

TARGET_T = 300.0
TARGET_P = 8_000_000.0
TARGET_Q = np.asarray(log_coordinates(TARGET_T, TARGET_P))


def _binary(
    methane_fraction: float = 0.5,
    *,
    permuted: bool = False,
) -> FluidMixture:
    items = (
        (
            MixtureComponent(PROPANE, 1.0 - methane_fraction),
            MixtureComponent(METHANE, methane_fraction),
        )
        if permuted
        else (
            MixtureComponent(METHANE, methane_fraction),
            MixtureComponent(PROPANE, 1.0 - methane_fraction),
        )
    )
    return FluidMixture(items)


def _synthetic_evaluator(
    field: object,
    *,
    calls: list[tuple[tuple[float, float], tuple[float, ...] | None]] | None = None,
) -> critical_point_module.ResidualEvaluator:
    function = field

    def evaluate(
        q: tuple[float, float], previous: tuple[float, ...] | None
    ) -> CriticalResidualEvaluation:
        if calls is not None:
            calls.append((q, previous))
        raw_values = function(np.asarray(q) - TARGET_Q)  # type: ignore[operator]
        raw = (float(raw_values[0]), float(raw_values[1]))
        direction = np.asarray((2.0**-0.5, -(2.0**-0.5)))
        if previous is not None and float(np.dot(direction, previous)) < 0.0:
            direction = -direction
        temperature, pressure = physical_coordinates(q)
        return CriticalResidualEvaluation(
            q,
            temperature,
            pressure,
            raw,
            tuple(float(value) for value in direction),
        )

    return evaluate


def _linear_field(offset: np.ndarray) -> np.ndarray:
    u, v = offset
    return np.asarray((u + 2.0 * v, 3.0 * u - v))


def _nonlinear_field(offset: np.ndarray) -> np.ndarray:
    u, v = offset
    return np.asarray((u + 2.0 * v + 0.3 * u * u, 3.0 * u - v + 0.2 * v * v))


def _seed(offset: tuple[float, float]) -> tuple[float, float]:
    return TARGET_T * exp(offset[0]), TARGET_P * exp(offset[1])


class TestCoordinatesScalingAndSettings:
    def test_variable_order_is_log_temperature_then_log_pressure(self) -> None:
        q = log_coordinates(321.0, 8_500_000.0)
        assert q == pytest.approx((log(321.0), log(8_500_000.0)))
        assert physical_coordinates(q) == pytest.approx((321.0, 8_500_000.0))

    def test_transforms_reject_nonpositive_or_nonfinite_inputs(self) -> None:
        with pytest.raises(ValueError):
            log_coordinates(0.0, 1.0)
        with pytest.raises(ValueError):
            physical_coordinates((float("nan"), 0.0))

    def test_residual_scaling_is_explicit_and_componentwise(self) -> None:
        scaling = ResidualScaling(2.0, 5.0)
        assert scaling.scaled((6.0, -20.0)) == (3.0, -4.0)

    def test_initial_residual_scales_have_documented_unit_floors(self) -> None:
        result = solve_critical_residual_system(
            _synthetic_evaluator(_linear_field), *_seed((0.05, -0.04))
        )
        assert result.residual_scaling == ResidualScaling(1.0, 1.0)

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            ("minimum_temperature_k", 0.0),
            ("lambda_tolerance", float("nan")),
            ("jacobian_log_step", 0.0),
            ("minimum_jacobian_log_step", 0.0),
            ("jacobian_absolute_tolerance", 0.0),
            ("jacobian_relative_tolerance", 0.0),
            ("maximum_iterations", 0),
            ("maximum_jacobian_step_reductions", -1),
            ("line_search_reduction_factor", 1.0),
            ("minimum_line_search_factor", 0.0),
        ],
    )
    def test_settings_reject_invalid_controls(self, name: str, value: object) -> None:
        with pytest.raises(ValueError):
            CriticalPointSolverSettings(**{name: value})  # type: ignore[arg-type]


class TestCriticalResidualJacobian:
    def test_richardson_jacobian_matches_analytic_log_coordinate_matrix(self) -> None:
        evaluator = _synthetic_evaluator(_linear_field)
        q = log_coordinates(TARGET_T, TARGET_P)
        base = evaluator(q, None)
        result = calculate_critical_residual_jacobian(
            evaluator,
            base,
            ResidualScaling(1.0, 1.0),
            CriticalPointSolverSettings(),
        )
        assert result.applicable
        assert np.asarray(result.raw_jacobian) == pytest.approx(
            np.asarray(((1.0, 2.0), (3.0, -1.0))), abs=5e-12
        )

    def test_log_chain_factors_are_present_for_physical_T_P_field(self) -> None:
        def physical_field(offset: np.ndarray) -> np.ndarray:
            temperature = TARGET_T * exp(float(offset[0]))
            pressure = TARGET_P * exp(float(offset[1]))
            return np.asarray(
                (
                    temperature / TARGET_T + 2.0 * pressure / TARGET_P - 3.0,
                    3.0 * temperature / TARGET_T - pressure / TARGET_P - 2.0,
                )
            )

        evaluator = _synthetic_evaluator(physical_field)
        base = evaluator(tuple(TARGET_Q), None)  # type: ignore[arg-type]
        result = calculate_critical_residual_jacobian(
            evaluator,
            base,
            ResidualScaling(1.0, 1.0),
            CriticalPointSolverSettings(),
        )
        assert np.asarray(result.raw_jacobian) == pytest.approx(
            np.asarray(((1.0, 2.0), (3.0, -1.0))), abs=1e-11
        )

    def test_production_richardson_agrees_with_independent_five_point_stencil(
        self,
    ) -> None:
        evaluator = _synthetic_evaluator(_nonlinear_field)
        q = tuple(TARGET_Q + np.asarray((0.03, -0.02)))
        base = evaluator(q, None)  # type: ignore[arg-type]
        production = calculate_critical_residual_jacobian(
            evaluator,
            base,
            ResidualScaling(1.0, 1.0),
            CriticalPointSolverSettings(jacobian_log_step=2e-3),
        )
        step = 5e-4
        independent = np.empty((2, 2))
        for column in range(2):
            samples = []
            for multiple in (-2.0, -1.0, 1.0, 2.0):
                trial = np.asarray(q)
                trial[column] += multiple * step
                samples.append(
                    np.asarray(
                        evaluator(tuple(trial), base.critical_direction).raw_residuals
                    )
                )  # type: ignore[arg-type]
            independent[:, column] = (
                samples[0] - 8.0 * samples[1] + 8.0 * samples[2] - samples[3]
            ) / (12.0 * step)
        assert np.asarray(production.raw_jacobian) == pytest.approx(
            independent, abs=2e-11
        )

    def test_nonapplicable_stencil_reduces_step_deterministically(self) -> None:
        center = tuple(TARGET_Q)

        def evaluator(
            q: tuple[float, float], previous: tuple[float, ...] | None
        ) -> CriticalResidualEvaluation:
            if max(abs(q[index] - center[index]) for index in range(2)) > 3e-4:
                raise ValueError("synthetic local applicability boundary")
            return _synthetic_evaluator(_linear_field)(q, previous)

        base = evaluator(center, None)  # type: ignore[arg-type]
        result = calculate_critical_residual_jacobian(
            evaluator,
            base,
            ResidualScaling(1.0, 1.0),
            CriticalPointSolverSettings(jacobian_log_step=1e-3),
        )
        assert result.applicable
        assert result.step_reductions == 2
        assert result.base_step == pytest.approx(2.5e-4)

    def test_aliasing_prone_stencil_is_reduced_until_error_gate_passes(self) -> None:
        frequency = 1_000.0

        def oscillatory_field(offset: np.ndarray) -> np.ndarray:
            return np.asarray((np.sin(frequency * offset[0]), offset[1]))

        evaluator = _synthetic_evaluator(oscillatory_field)
        base = evaluator(tuple(TARGET_Q), None)  # type: ignore[arg-type]
        result = calculate_critical_residual_jacobian(
            evaluator,
            base,
            ResidualScaling(1.0, 1.0),
            CriticalPointSolverSettings(),
        )
        assert result.applicable
        assert result.step_reductions == 4
        assert result.base_step == pytest.approx(6.25e-5)
        assert result.estimated_errors is not None
        assert result.error_thresholds is not None
        assert np.all(
            np.asarray(result.estimated_errors) <= np.asarray(result.error_thresholds)
        )
        assert all(
            attempt.outcome is JacobianStepFailure.NUMERICAL_NONCONVERGENCE
            for attempt in result.attempts
        )
        assert np.asarray(result.raw_jacobian) == pytest.approx(
            np.asarray(((frequency, 0.0), (0.0, 1.0))), rel=4e-8, abs=1e-8
        )

    def test_numerically_unresolved_stencil_is_structured_failure(self) -> None:
        initial_step = 1.0e-3

        def unresolved_field(offset: np.ndarray) -> np.ndarray:
            u = float(offset[0])
            first = (
                0.0
                if u == 0.0
                else u * np.sin(np.pi * (np.log2(abs(u) / initial_step) + 0.25))
            )
            return np.asarray((first, offset[1]))

        evaluator = _synthetic_evaluator(unresolved_field)
        base = evaluator(tuple(TARGET_Q), None)  # type: ignore[arg-type]
        result = calculate_critical_residual_jacobian(
            evaluator,
            base,
            ResidualScaling(1.0, 1.0),
            CriticalPointSolverSettings(jacobian_log_step=initial_step),
        )
        assert not result.applicable
        assert result.raw_jacobian is None
        assert result.failure_reason is not None
        assert "numerical-convergence" in result.failure_reason
        assert len(result.attempts) == 9
        assert all(
            attempt.outcome is JacobianStepFailure.NUMERICAL_NONCONVERGENCE
            for attempt in result.attempts
        )


class TestSafeguardedNonlinearCore:
    def test_linear_system_converges_to_known_root(self) -> None:
        result = solve_critical_residual_system(
            _synthetic_evaluator(_linear_field), *_seed((0.08, -0.05))
        )
        assert result.status is CriticalPointStatus.CONVERGED
        assert result.temperature_k == pytest.approx(TARGET_T, rel=1e-12)
        assert result.pressure_pa == pytest.approx(TARGET_P, rel=1e-12)
        assert result.lambda_min == pytest.approx(0.0, abs=1e-12)
        assert result.cubic_coefficient == pytest.approx(0.0, abs=1e-12)

    def test_nonlinear_system_converges_to_known_root(self) -> None:
        result = solve_critical_residual_system(
            _synthetic_evaluator(_nonlinear_field), *_seed((0.1, -0.08))
        )
        assert result.status is CriticalPointStatus.CONVERGED
        assert result.temperature_k == pytest.approx(TARGET_T, rel=1e-8)
        assert result.pressure_pa == pytest.approx(TARGET_P, rel=1e-8)

    def test_singular_jacobian_is_structured_failure(self) -> None:
        evaluator = _synthetic_evaluator(
            lambda offset: np.asarray(
                (offset[0] + offset[1], 2.0 * offset[0] + 2.0 * offset[1])
            )
        )
        result = solve_critical_residual_system(evaluator, *_seed((0.1, 0.1)))
        assert result.status is CriticalPointStatus.ILL_CONDITIONED

    def test_line_search_backtracks_and_requires_merit_decrease(self) -> None:
        def field(offset: np.ndarray) -> np.ndarray:
            u, v = offset
            return np.asarray((u * u - 1.0, v))

        settings = CriticalPointSolverSettings(
            minimum_temperature_k=0.1,
            maximum_temperature_k=10_000.0,
            maximum_log_temperature_step=10.0,
            maximum_log_pressure_step=10.0,
        )
        result = solve_critical_residual_system(
            _synthetic_evaluator(field), *_seed((0.1, 0.2)), settings=settings
        )
        assert result.status is CriticalPointStatus.CONVERGED
        assert result.rejected_steps > 0
        norms = tuple(item.scaled_residual_norm for item in result.history)
        assert all(
            next_value < value
            for value, next_value in zip(norms, norms[1:], strict=False)
        )

    def test_out_of_bounds_initialization_is_structured(self) -> None:
        result = solve_critical_residual_system(
            _synthetic_evaluator(_linear_field), 50.0, TARGET_P
        )
        assert result.status is CriticalPointStatus.INITIALIZATION_FAILED

    def test_both_residuals_are_required_for_convergence(self) -> None:
        evaluator = _synthetic_evaluator(lambda offset: np.asarray((offset[0], 2.0)))
        result = solve_critical_residual_system(evaluator, TARGET_T, TARGET_P)
        assert result.status is not CriticalPointStatus.CONVERGED
        assert result.history[0].lambda_min == pytest.approx(0.0)
        assert result.history[0].cubic_coefficient == pytest.approx(2.0)

    def test_raw_cubic_tolerance_cannot_be_bypassed_by_large_scaling(self) -> None:
        cubic_floor = 2.0e-6

        def no_cubic_root(offset: np.ndarray) -> np.ndarray:
            u, v = offset
            return np.asarray((u, 60.0 * v * v + cubic_floor))

        result = solve_critical_residual_system(
            _synthetic_evaluator(no_cubic_root), *_seed((0.1, 1.0))
        )
        assert result.residual_scaling is not None
        assert result.residual_scaling.cubic_scale > 50.0
        assert result.status is not CriticalPointStatus.CONVERGED
        assert result.cubic_coefficient is not None
        assert result.cubic_coefficient > 1.0e-6

    def test_orientation_is_carried_to_jacobian_and_trial_evaluations(self) -> None:
        calls: list[tuple[tuple[float, float], tuple[float, ...] | None]] = []
        result = solve_critical_residual_system(
            _synthetic_evaluator(_linear_field, calls=calls), *_seed((0.03, 0.02))
        )
        assert result.status is CriticalPointStatus.CONVERGED
        assert calls[0][1] is None
        assert any(previous is not None for _, previous in calls[1:])

    def test_uncontrolled_eigenvector_sign_flip_is_rejected(self) -> None:
        ordinary = _synthetic_evaluator(_linear_field)

        def flipping(
            q: tuple[float, float], previous: tuple[float, ...] | None
        ) -> CriticalResidualEvaluation:
            result = ordinary(q, previous)
            if previous is None:
                return result
            return replace(
                result,
                critical_direction=tuple(-value for value in result.critical_direction),
            )

        result = solve_critical_residual_system(flipping, *_seed((0.03, 0.02)))
        assert result.status is CriticalPointStatus.JACOBIAN_FAILED

    def test_final_state_is_freshly_revalidated_twice(self) -> None:
        calls = 0
        ordinary = _synthetic_evaluator(_linear_field)

        def unstable_final(
            q: tuple[float, float], previous: tuple[float, ...] | None
        ) -> CriticalResidualEvaluation:
            nonlocal calls
            calls += 1
            result = ordinary(q, previous)
            if calls == 3:
                return replace(result, raw_residuals=(1e-3, 1e-3))
            return result

        result = solve_critical_residual_system(unstable_final, TARGET_T, TARGET_P)
        assert result.status is CriticalPointStatus.FINAL_VALIDATION_FAILED

    def test_repeated_synthetic_solve_is_exactly_deterministic(self) -> None:
        first = solve_critical_residual_system(
            _synthetic_evaluator(_nonlinear_field), *_seed((0.05, 0.04))
        )
        second = solve_critical_residual_system(
            _synthetic_evaluator(_nonlinear_field), *_seed((0.05, 0.04))
        )
        assert first == second

    def test_result_is_immutable(self) -> None:
        result = solve_critical_residual_system(
            _synthetic_evaluator(_linear_field), TARGET_T, TARGET_P
        )
        with pytest.raises(FrozenInstanceError):
            result.status = CriticalPointStatus.MAXIMUM_ITERATIONS  # type: ignore[misc]


@pytest.fixture(scope="module")
def pr_solutions() -> tuple[critical_point_module.MixtureCriticalPointResult, ...]:
    mixture = _binary()
    return tuple(
        solve_mixture_critical_point(mixture, temperature, pressure)
        for temperature, pressure in (
            (320.0, 8_500_000.0),
            (325.0, 9_000_000.0),
            (315.0, 8_000_000.0),
            (330.0, 10_000_000.0),
        )
    )


class TestPengRobinsonCriticalPoint:
    def test_multiple_seeds_recover_same_binary_critical_point(
        self,
        pr_solutions: tuple[critical_point_module.MixtureCriticalPointResult, ...],
    ) -> None:
        assert all(
            item.status is CriticalPointStatus.CONVERGED for item in pr_solutions
        )
        temperatures = tuple(item.temperature_k for item in pr_solutions)
        pressures = tuple(item.pressure_pa for item in pr_solutions)
        assert temperatures == pytest.approx((321.582918,) * 4, abs=1e-5)
        assert pressures == pytest.approx((8_534_443.24,) * 4, abs=0.2)

    def test_final_raw_residuals_and_direction_are_certified(
        self,
        pr_solutions: tuple[critical_point_module.MixtureCriticalPointResult, ...],
    ) -> None:
        result = pr_solutions[0]
        assert abs(result.lambda_min or 1.0) < 1e-7
        assert abs(result.cubic_coefficient or 1.0) < 1e-6
        assert result.scaled_residual_norm is not None
        assert result.scaled_residual_norm < 1e-6
        direction = np.asarray(result.critical_direction)
        assert np.sum(direction) == pytest.approx(0.0, abs=1e-14)
        assert np.linalg.norm(direction) == pytest.approx(1.0, abs=1e-14)

    def test_independent_final_evaluation_and_local_crossing(
        self,
        pr_solutions: tuple[critical_point_module.MixtureCriticalPointResult, ...],
    ) -> None:
        result = pr_solutions[0]
        assert result.temperature_k is not None and result.pressure_pa is not None
        independent = calculate_stable_root_mixture_criticality(
            _binary(), result.temperature_k, result.pressure_pa
        )
        assert independent.status is CriticalityStatus.APPLICABLE
        assert independent.lambda_min == result.lambda_min
        assert independent.cubic_directional_derivative == result.cubic_coefficient
        lower_t = calculate_stable_root_mixture_criticality(
            _binary(), result.temperature_k - 0.05, result.pressure_pa
        )
        upper_t = calculate_stable_root_mixture_criticality(
            _binary(), result.temperature_k + 0.05, result.pressure_pa
        )
        assert lower_t.lambda_min is not None and upper_t.lambda_min is not None
        assert lower_t.cubic_directional_derivative is not None
        assert upper_t.cubic_directional_derivative is not None
        assert lower_t.lambda_min * upper_t.lambda_min < 0.0
        assert (
            lower_t.cubic_directional_derivative * upper_t.cubic_directional_derivative
            < 0.0
        )

    def test_real_backtracking_is_recorded(
        self,
        pr_solutions: tuple[critical_point_module.MixtureCriticalPointResult, ...],
    ) -> None:
        assert pr_solutions[-1].rejected_steps >= 1
        assert any(
            item.line_search_factor < 1.0 for item in pr_solutions[-1].history[1:]
        )

    def test_spinodal_like_state_is_not_false_positive(self) -> None:
        settings = CriticalPointSolverSettings(
            maximum_iterations=1,
            maximum_log_temperature_step=1e-8,
            maximum_log_pressure_step=1e-8,
        )
        result = solve_mixture_critical_point(
            _binary(), 294.178237, 7.0e6, settings=settings
        )
        initial = result.history[0]
        assert abs(initial.lambda_min) < 1.0e-5
        assert abs(initial.cubic_coefficient) > 10.0
        assert result.status is not CriticalPointStatus.CONVERGED

    def test_maxwell_root_switch_rejects_every_symmetric_jacobian_stencil(
        self,
    ) -> None:
        settings = CriticalPointSolverSettings()
        evaluator = critical_point_module._mixture_evaluator(
            _binary(),
            None,
            critical_point_module.BinaryInteractionPolicy.DEFAULT_ZERO,
            None,
            settings,
        )
        base = evaluator(log_coordinates(200.0, 330_900.04669931164), None)
        assert base.root_identity is not None
        assert base.root_identity.root_count == 3
        assert base.root_identity.selected_index == 0
        result = calculate_critical_residual_jacobian(
            evaluator, base, ResidualScaling(1.0, 1.0), settings
        )
        assert not result.applicable
        assert len(result.attempts) == 9
        assert all(
            attempt.outcome is JacobianStepFailure.ROOT_CONTINUITY
            for attempt in result.attempts
        )

    def test_selected_critical_path_stays_on_single_pr_root_branch(
        self,
        pr_solutions: tuple[critical_point_module.MixtureCriticalPointResult, ...],
    ) -> None:
        settings = CriticalPointSolverSettings()
        evaluator = critical_point_module._mixture_evaluator(
            _binary(),
            None,
            critical_point_module.BinaryInteractionPolicy.DEFAULT_ZERO,
            None,
            settings,
        )
        for item in pr_solutions[0].history:
            evaluation = evaluator(
                log_coordinates(item.temperature_k, item.pressure_pa), None
            )
            assert evaluation.root_identity is not None
            assert evaluation.root_identity.root_count == 1
            assert evaluation.root_identity.selected_index == 0

    def test_in_bounds_poor_seed_fails_without_fabricating_a_candidate(self) -> None:
        result = solve_mixture_critical_point(_binary(), 250.0, 5_000_000.0)
        assert result.status is CriticalPointStatus.LINE_SEARCH_FAILED
        assert result.iterations == 0
        assert result.temperature_k == pytest.approx(250.0)
        assert result.pressure_pa == pytest.approx(5_000_000.0)
        assert result.rejected_steps > 0

    def test_component_permutation_preserves_critical_T_and_P(
        self,
        pr_solutions: tuple[critical_point_module.MixtureCriticalPointResult, ...],
    ) -> None:
        permuted = solve_mixture_critical_point(_binary(permuted=True), 320.0, 8.5e6)
        reference = pr_solutions[0]
        assert permuted.status is CriticalPointStatus.CONVERGED
        assert permuted.temperature_k == pytest.approx(
            reference.temperature_k, abs=1e-6
        )
        assert permuted.pressure_pa == pytest.approx(reference.pressure_pa, abs=0.1)

    @pytest.mark.parametrize("reference_index", [0, 1])
    def test_reference_component_does_not_change_critical_state(
        self,
        reference_index: int,
        pr_solutions: tuple[critical_point_module.MixtureCriticalPointResult, ...],
    ) -> None:
        result = solve_mixture_critical_point(
            _binary(),
            320.0,
            8.5e6,
            reference_active_component_index=reference_index,
        )
        assert result.status is CriticalPointStatus.CONVERGED
        assert result.temperature_k == pytest.approx(
            pr_solutions[0].temperature_k, abs=1e-6
        )
        assert result.pressure_pa == pytest.approx(pr_solutions[0].pressure_pa, abs=0.1)

    def test_inactive_component_is_not_iterated_and_maps_to_zero_direction(
        self,
    ) -> None:
        mixture = FluidMixture(
            (
                MixtureComponent(METHANE, 0.5),
                MixtureComponent(PROPANE, 0.5),
                MixtureComponent(ETHANE, 0.0),
            )
        )
        result = solve_mixture_critical_point(mixture, 320.0, 8.5e6)
        assert result.status is CriticalPointStatus.CONVERGED
        assert result.composition == (0.5, 0.5, 0.0)
        assert result.critical_direction is not None
        assert result.critical_direction[2] == 0.0

    def test_pure_active_mixture_is_outside_module_scope(self) -> None:
        mixture = FluidMixture(
            (MixtureComponent(METHANE, 1.0), MixtureComponent(PROPANE, 0.0))
        )
        result = solve_mixture_critical_point(mixture, 190.0, 4.6e6)
        assert result.status is CriticalPointStatus.INSUFFICIENT_ACTIVE_COMPONENTS

    def test_module19_nonapplicability_is_structured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ordinary = calculate_stable_root_mixture_criticality(_binary(), 320.0, 8.5e6)
        unavailable = replace(
            ordinary,
            status=CriticalityStatus.CRITICAL_MODE_DEGENERATE,
            reason="synthetic mode collision",
        )
        monkeypatch.setattr(
            critical_point_module,
            "calculate_stable_root_mixture_criticality",
            lambda *args, **kwargs: unavailable,
        )
        result = solve_mixture_critical_point(_binary(), 320.0, 8.5e6)
        assert result.status is CriticalPointStatus.CRITICALITY_NOT_APPLICABLE

    def test_coarse_scan_is_bounded_deterministic_and_does_not_solve(self) -> None:
        settings = CriticalPointScanSettings(315.0, 325.0, 8e6, 9e6, 3, 3)
        first = scan_mixture_criticality(_binary(), settings)
        second = scan_mixture_criticality(_binary(), settings)
        assert first == second
        assert len(first.entries) == 9
        assert first.composition == (0.5, 0.5)
        assert first.best_applicable_entry is not None
