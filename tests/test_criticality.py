"""Focused Module 19 tests for local mixture-criticality derivatives."""

from dataclasses import FrozenInstanceError
from math import fsum, isfinite, log

import numpy as np
import pytest

from pvt_phase_simulator.eos.criticality import (
    CriticalityStatus,
    MixtureCriticalityResult,
    analyze_tangent_hessian,
    calculate_direct_simplex_hessian,
    calculate_fixed_root_mixture_criticality,
    calculate_stable_root_mixture_criticality,
    construct_orthonormal_tangent_basis,
    criticality_residual_pair,
    maximum_symmetric_simplex_step,
    richardson_directional_derivative,
    transform_direct_hessian_to_orthonormal_basis,
)
from pvt_phase_simulator.eos.derivatives import (
    calculate_fixed_root_mixture_fugacity_derivatives,
)
from pvt_phase_simulator.eos.mixing_rules import (
    calculate_peng_robinson_mixture_parameters,
)
from pvt_phase_simulator.eos.mixture_fugacity import (
    calculate_mixture_fugacity_coefficients,
)
from pvt_phase_simulator.eos.peng_robinson import calculate_compressibility_roots
from pvt_phase_simulator.eos.phase_stability import (
    calculate_tangent_plane_distance,
    evaluate_feed_phase_reference,
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
    components: tuple[Component, ...], fractions: tuple[float, ...]
) -> FluidMixture:
    return FluidMixture(
        tuple(
            MixtureComponent(component, fraction)
            for component, fraction in zip(components, fractions, strict=True)
        )
    )


def _stable_result(
    components: tuple[Component, ...] = (METHANE, ETHANE, PROPANE),
    fractions: tuple[float, ...] = (0.5, 0.3, 0.2),
    temperature_k: float = 280.0,
    pressure_pa: float = 3_000_000.0,
    **options: object,
) -> MixtureCriticalityResult:
    mixture = _mixture(components, fractions)
    if options:
        return calculate_stable_root_mixture_criticality(
            mixture,
            temperature_k,
            pressure_pa,
            cubic_step=float(options.get("cubic_step", 1.0e-3)),
        )
    return calculate_stable_root_mixture_criticality(
        mixture, temperature_k, pressure_pa
    )


def _continued_log_phi(
    components: tuple[Component, ...],
    composition: tuple[float, ...],
    temperature_k: float,
    pressure_pa: float,
    reference_root: float,
) -> tuple[float, tuple[float, ...]]:
    parameters = calculate_peng_robinson_mixture_parameters(
        _mixture(components, composition), temperature_k, pressure_pa
    )
    root = min(
        calculate_compressibility_roots(parameters.A_mix, parameters.B_mix),
        key=lambda value: abs(value - reference_root),
    )
    log_phi = tuple(
        item.log_fugacity_coefficient
        for item in calculate_mixture_fugacity_coefficients(parameters, root)
    )
    return root, log_phi


def _direct_hessian_at(
    components: tuple[Component, ...],
    composition: tuple[float, ...],
    temperature_k: float,
    pressure_pa: float,
    reference_root: float,
    reference_component_index: int | None = None,
) -> tuple[float, np.ndarray]:
    parameters = calculate_peng_robinson_mixture_parameters(
        _mixture(components, composition), temperature_k, pressure_pa
    )
    root = min(
        calculate_compressibility_roots(parameters.A_mix, parameters.B_mix),
        key=lambda value: abs(value - reference_root),
    )
    derivatives = calculate_fixed_root_mixture_fugacity_derivatives(
        parameters, root, reference_component_index=reference_component_index
    )
    assert derivatives.log_fugacity_composition_derivatives is not None
    hessian = calculate_direct_simplex_hessian(
        composition,
        derivatives.log_fugacity_composition_derivatives,
        reference_component_index=reference_component_index,
    )
    return root, np.asarray(hessian)


class TestTangentSpaceMathematics:
    @pytest.mark.parametrize("component_count", [2, 3, 5])
    def test_basis_is_orthonormal_and_sums_to_zero(self, component_count: int) -> None:
        basis = np.asarray(construct_orthonormal_tangent_basis(component_count))
        assert basis.T @ basis == pytest.approx(np.eye(component_count - 1), abs=1e-14)
        assert np.sum(basis, axis=0) == pytest.approx(0.0, abs=1e-14)

    def test_basis_construction_is_deterministic_with_documented_sign(self) -> None:
        first = np.asarray(construct_orthonormal_tangent_basis(4))
        second = np.asarray(construct_orthonormal_tangent_basis(4))
        assert first == pytest.approx(second, abs=0.0)
        for column in first.T:
            largest = max(abs(value) for value in column)
            pivot = next(
                index
                for index, value in enumerate(column)
                if abs(value) >= largest - 1e-14
            )
            assert column[pivot] > 0.0

    def test_binary_basis_has_expected_physical_direction(self) -> None:
        basis = np.asarray(construct_orthonormal_tangent_basis(2))
        assert basis[:, 0] == pytest.approx((2**-0.5, -(2**-0.5)))

    def test_direct_ideal_hessian_matches_exact_formula(self) -> None:
        composition = (0.2, 0.3, 0.5)
        zeros = ((0.0, 0.0),) * 3
        result = calculate_direct_simplex_hessian(composition, zeros)
        expected = ((7.0, 2.0), (2.0, 16.0 / 3.0))
        assert np.asarray(result) == pytest.approx(np.asarray(expected), abs=1e-15)

    def test_orthonormal_transform_preserves_quadratic_form(self) -> None:
        direct = ((7.0, 2.0), (2.0, 16.0 / 3.0))
        basis = construct_orthonormal_tangent_basis(3)
        transformed = np.asarray(
            transform_direct_hessian_to_orthonormal_basis(direct, basis)
        )
        q = np.asarray(basis)
        direct_basis = np.asarray(((1.0, 0.0), (0.0, 1.0), (-1.0, -1.0)))
        mapping = np.linalg.solve(direct_basis.T @ direct_basis, direct_basis.T @ q)
        eta = np.asarray((0.31, -0.47))
        assert eta @ transformed @ eta == pytest.approx(
            (mapping @ eta) @ np.asarray(direct) @ (mapping @ eta), abs=1e-14
        )

    def test_ideal_hessian_is_symmetric_positive_definite_and_permutation_safe(
        self,
    ) -> None:
        composition = (0.2, 0.3, 0.5)
        basis = construct_orthonormal_tangent_basis(3)
        direct = calculate_direct_simplex_hessian(composition, ((0.0, 0.0),) * 3)
        transformed = transform_direct_hessian_to_orthonormal_basis(direct, basis)
        analysis = analyze_tangent_hessian(transformed, basis)
        permuted = (composition[2], composition[0], composition[1])
        permuted_direct = calculate_direct_simplex_hessian(permuted, ((0.0, 0.0),) * 3)
        permuted_analysis = analyze_tangent_hessian(
            transform_direct_hessian_to_orthonormal_basis(
                permuted_direct, construct_orthonormal_tangent_basis(3)
            ),
            construct_orthonormal_tangent_basis(3),
        )
        assert analysis.symmetry_defect < 1e-14
        assert min(analysis.eigenvalues) > 0.0
        assert permuted_analysis.eigenvalues == pytest.approx(analysis.eigenvalues)


class TestHessianAnalysisSafeguards:
    def test_small_antisymmetry_is_recorded_then_safely_symmetrized(self) -> None:
        basis = construct_orthonormal_tangent_basis(3)
        result = analyze_tangent_hessian(((2.0, 0.3 + 1e-10), (0.3, 4.0)), basis)
        assert result.status is CriticalityStatus.APPLICABLE
        assert result.symmetry_defect == pytest.approx(1e-10)
        assert result.symmetric_hessian is not None

    def test_large_antisymmetry_is_structurally_rejected(self) -> None:
        result = analyze_tangent_hessian(
            ((2.0, 0.4), (0.1, 4.0)), construct_orthonormal_tangent_basis(3)
        )
        assert result.status is CriticalityStatus.SYMMETRY_UNRELIABLE
        assert result.symmetric_hessian is None
        assert not result.eigenvalues

    def test_smallest_algebraic_eigenvalue_and_rayleigh_value_agree(self) -> None:
        basis = construct_orthonormal_tangent_basis(3)
        hessian = ((-0.5, 0.2), (0.2, 3.0))
        result = analyze_tangent_hessian(hessian, basis)
        assert result.lambda_min is not None
        assert result.tangent_mode is not None
        vector = np.asarray(result.tangent_mode)
        assert vector @ np.asarray(hessian) @ vector == pytest.approx(result.lambda_min)

    def test_ternary_degenerate_soft_mode_is_not_claimed_unique(self) -> None:
        result = analyze_tangent_hessian(
            ((1.0, 0.0), (0.0, 1.0 + 1e-10)),
            construct_orthonormal_tangent_basis(3),
        )
        assert result.status is CriticalityStatus.CRITICAL_MODE_DEGENERATE
        assert result.physical_direction is None

    def test_binary_mode_needs_no_gap_test(self) -> None:
        result = analyze_tangent_hessian(
            ((0.0,),), construct_orthonormal_tangent_basis(2)
        )
        assert result.status is CriticalityStatus.APPLICABLE
        assert result.eigenvalue_gap is None

    def test_orientation_uses_largest_component_then_previous_direction(self) -> None:
        basis = construct_orthonormal_tangent_basis(3)
        initial = analyze_tangent_hessian(((1.0, 0.2), (0.2, 3.0)), basis)
        assert initial.physical_direction is not None
        direction = np.asarray(initial.physical_direction)
        assert direction[int(np.argmax(np.abs(direction)))] > 0.0
        reversed_result = analyze_tangent_hessian(
            ((1.0, 0.2), (0.2, 3.0)),
            basis,
            previous_direction=tuple(-direction),
        )
        assert reversed_result.physical_direction == pytest.approx(-direction)


class TestCubicDirectionalDerivative:
    def test_synthetic_polynomial_recovers_exact_quadratic_and_cubic_terms(
        self,
    ) -> None:
        a, b, c = 1.25, -0.75, 2.0
        result = richardson_directional_derivative(
            lambda step: (a + b * step + 0.5 * c * step**2, 1.0),
            0.5,
            requested_step=0.05,
        )
        assert result.richardson_estimate == pytest.approx(b, abs=1e-12)
        analysis = analyze_tangent_hessian(
            ((a,),), construct_orthonormal_tangent_basis(2)
        )
        assert analysis.lambda_min == pytest.approx(a)

    def test_synthetic_critical_polynomial_has_zero_a_and_b(self) -> None:
        result = richardson_directional_derivative(
            lambda step: (0.5 * 3.0 * step**2, 1.0), 0.5
        )
        assert result.richardson_estimate == pytest.approx(0.0, abs=1e-15)
        assert analyze_tangent_hessian(
            ((0.0,),), construct_orthonormal_tangent_basis(2)
        ).lambda_min == pytest.approx(0.0)

    def test_richardson_formula_cancels_centered_second_order_error(self) -> None:
        result = richardson_directional_derivative(
            lambda step: (2.0 + 4.0 * step + 7.0 * step**3, 0.8 + step),
            0.25,
            requested_step=0.1,
        )
        assert result.coarse_estimate != pytest.approx(4.0)
        assert result.refined_estimate != pytest.approx(4.0)
        assert result.richardson_estimate == pytest.approx(4.0, abs=1e-12)
        assert result.estimated_error is not None and result.estimated_error > 0.0

    def test_boundary_step_is_reduced_without_clipping(self) -> None:
        composition = (1.0e-6, 0.4, 0.599999)
        direction = (-0.8, 0.3, 0.5)
        bound = maximum_symmetric_simplex_step(composition, direction)
        result = richardson_directional_derivative(
            lambda step: (3.0 + 2.0 * step, 1.0), bound, requested_step=1e-3
        )
        assert bound == pytest.approx(1.25e-6)
        assert result.base_step == pytest.approx(0.25 * bound)
        assert result.sampled_steps and max(result.sampled_steps) < bound

    def test_root_boundary_failure_reduces_step_before_accepting(self) -> None:
        attempted: list[float] = []

        def evaluator(step: float) -> tuple[float, float]:
            attempted.append(step)
            if abs(step) > 0.002:
                raise ValueError("synthetic root switch")
            return 1.0 + 3.0 * step, 0.7 + step

        result = richardson_directional_derivative(evaluator, 1.0, requested_step=0.01)
        assert result.applicable
        assert result.step_reductions == 3
        assert result.base_step == pytest.approx(0.00125)
        assert any(abs(step) > 0.002 for step in attempted)

    def test_persistent_root_failure_is_structured_non_applicability(self) -> None:
        def evaluator(step: float) -> tuple[float, float]:
            raise ValueError(f"root switch at {step}")

        result = richardson_directional_derivative(
            evaluator, 1.0, maximum_step_reductions=2
        )
        assert not result.applicable
        assert result.richardson_estimate is None
        assert result.failure_reason is not None

    def test_direction_reversal_changes_cubic_sign_not_quadratic_curvature(
        self,
    ) -> None:
        forward = richardson_directional_derivative(
            lambda step: (2.0 - 5.0 * step, 1.0), 0.5
        )
        reverse = richardson_directional_derivative(
            lambda step: (2.0 + 5.0 * step, 1.0), 0.5
        )
        assert forward.richardson_estimate == pytest.approx(-5.0)
        assert reverse.richardson_estimate == pytest.approx(5.0)
        assert 2.0 == pytest.approx(2.0)


class TestPREvaluation:
    @pytest.mark.parametrize(
        ("components", "fractions", "temperature_k", "pressure_pa"),
        [
            ((METHANE, ETHANE), (0.5, 0.5), 250.0, 3_000_000.0),
            ((METHANE, PROPANE), (0.5, 0.5), 280.0, 4_000_000.0),
            (
                (METHANE, ETHANE, PROPANE),
                (0.5, 0.3, 0.2),
                280.0,
                3_000_000.0,
            ),
        ],
    )
    def test_regular_states_are_finite_applicable_and_dimensionally_correct(
        self,
        components: tuple[Component, ...],
        fractions: tuple[float, ...],
        temperature_k: float,
        pressure_pa: float,
    ) -> None:
        result = _stable_result(components, fractions, temperature_k, pressure_pa)
        dimension = len(components) - 1
        assert result.status is CriticalityStatus.APPLICABLE
        assert result.fixed_root_applicable
        assert len(result.eigenvalues) == dimension
        assert np.asarray(result.raw_tangent_hessian).shape == (dimension, dimension)
        assert result.symmetry_defect is not None and result.symmetry_defect < 1e-12
        assert all(isfinite(value) for value in result.eigenvalues)
        assert result.cubic_directional_derivative is not None

    def test_result_is_immutable_and_residual_pair_is_explicit(self) -> None:
        result = _stable_result()
        assert criticality_residual_pair(result) == (
            result.lambda_min,
            result.cubic_directional_derivative,
        )
        with pytest.raises(FrozenInstanceError):
            result.lambda_min = 0.0  # type: ignore[misc]

    def test_critical_direction_is_normalized_tangent_and_rayleigh_consistent(
        self,
    ) -> None:
        result = _stable_result()
        assert result.active_critical_direction is not None
        assert result.critical_tangent_vector is not None
        direction = np.asarray(result.active_critical_direction)
        vector = np.asarray(result.critical_tangent_vector)
        hessian = np.asarray(result.symmetric_tangent_hessian)
        assert np.sum(direction) == pytest.approx(0.0, abs=1e-14)
        assert np.linalg.norm(direction) == pytest.approx(1.0, abs=1e-14)
        assert vector @ hessian @ vector == pytest.approx(result.lambda_min)

    def test_stable_wrapper_reuses_module5_parent_selection(self) -> None:
        mixture = _mixture((METHANE, ETHANE), (0.4, 0.6))
        reference = evaluate_feed_phase_reference(mixture, 240.0, 2_000_000.0)
        result = calculate_stable_root_mixture_criticality(mixture, 240.0, 2_000_000.0)
        assert result.root_selection_policy == "stable_parent_root"
        assert result.selected_compressibility_factor == pytest.approx(
            reference.selected_compressibility_factor
        )

    def test_invalid_explicit_root_returns_structured_failure(self) -> None:
        result = calculate_fixed_root_mixture_criticality(
            _mixture((METHANE, ETHANE), (0.5, 0.5)),
            250.0,
            3_000_000.0,
            0.123456789,
        )
        assert result.status is CriticalityStatus.DERIVATIVES_UNAVAILABLE
        assert not result.fixed_root_applicable

    def test_inactive_component_is_reduced_and_mapped_back(self) -> None:
        result = _stable_result(
            (METHANE, ETHANE, PROPANE), (0.6, 0.4, 0.0), 250.0, 3_000_000.0
        )
        assert result.status is CriticalityStatus.APPLICABLE
        assert result.active_component_indices == (0, 1)
        assert result.inactive_component_indices == (2,)
        assert result.critical_composition_direction is not None
        assert result.critical_composition_direction[2] == 0.0

    def test_pure_active_support_is_explicitly_not_applicable(self) -> None:
        result = _stable_result(
            (METHANE, ETHANE, PROPANE), (1.0, 0.0, 0.0), 200.0, 2_000_000.0
        )
        assert result.status is CriticalityStatus.NOT_APPLICABLE
        assert result.raw_direct_hessian == ()
        with pytest.raises(ValueError, match="Fewer than two"):
            criticality_residual_pair(result)

    def test_near_boundary_active_fraction_remains_finite_and_step_safe(self) -> None:
        result = _stable_result(
            (METHANE, ETHANE, PROPANE),
            (1.0e-6, 0.399999, 0.6),
            280.0,
            3_000_000.0,
        )
        assert result.status is CriticalityStatus.APPLICABLE
        assert (
            max(abs(value) for row in result.raw_direct_hessian for value in row) > 1e5
        )
        assert result.cubic_diagnostics is not None
        diagnostic = result.cubic_diagnostics
        assert diagnostic.base_step is not None
        assert diagnostic.base_step < diagnostic.maximum_symmetric_step
        assert all(isfinite(value) for value in diagnostic.sampled_curvatures)

    def test_repeated_evaluation_is_bitwise_deterministic(self) -> None:
        first = _stable_result()
        second = _stable_result()
        assert first == second


class TestIndependentVerification:
    @pytest.mark.parametrize(
        ("components", "composition", "temperature_k", "pressure_pa"),
        [
            ((METHANE, ETHANE), (0.4, 0.6), 250.0, 3_000_000.0),
            ((METHANE, PROPANE), (0.55, 0.45), 280.0, 4_000_000.0),
            (
                (METHANE, ETHANE, PROPANE),
                (0.5, 0.3, 0.2),
                280.0,
                3_000_000.0,
            ),
        ],
    )
    def test_hessian_matches_richardson_fd_of_reduced_chemical_potentials(
        self,
        components: tuple[Component, ...],
        composition: tuple[float, ...],
        temperature_k: float,
        pressure_pa: float,
    ) -> None:
        mixture = _mixture(components, composition)
        reference = evaluate_feed_phase_reference(mixture, temperature_k, pressure_pa)
        root = reference.selected_compressibility_factor
        assert root is not None
        _, analytical = _direct_hessian_at(
            components, composition, temperature_k, pressure_pa, root
        )
        dimension = len(composition) - 1

        def q_at(coordinates: np.ndarray) -> np.ndarray:
            trial = (
                *tuple(float(value) for value in coordinates),
                1.0 - fsum(coordinates),
            )
            _, log_phi = _continued_log_phi(
                components, trial, temperature_k, pressure_pa, root
            )
            return np.asarray(
                [
                    log(trial[index]) + log_phi[index] - log(trial[-1]) - log_phi[-1]
                    for index in range(dimension)
                ]
            )

        coordinates = np.asarray(composition[:-1])
        finite_difference = np.empty_like(analytical)
        h = 2.0e-4
        for column in range(dimension):
            unit = np.zeros(dimension)
            unit[column] = 1.0
            coarse = (q_at(coordinates + h * unit) - q_at(coordinates - h * unit)) / (
                2.0 * h
            )
            refined = (
                q_at(coordinates + 0.5 * h * unit) - q_at(coordinates - 0.5 * h * unit)
            ) / h
            finite_difference[:, column] = (4.0 * refined - coarse) / 3.0
        assert finite_difference == pytest.approx(analytical, rel=2e-8, abs=2e-9)

    def test_production_c_matches_independent_five_point_curvature_derivative(
        self,
    ) -> None:
        components = (METHANE, ETHANE, PROPANE)
        composition = (0.5, 0.3, 0.2)
        temperature_k, pressure_pa = 280.0, 3_000_000.0
        result = _stable_result(components, composition, temperature_k, pressure_pa)
        assert result.selected_compressibility_factor is not None
        assert result.active_critical_direction is not None
        direction = np.asarray(result.active_critical_direction)

        def curvature(step: float) -> float:
            trial = np.asarray(composition) + step * direction
            _, hessian = _direct_hessian_at(
                components,
                tuple(float(value) for value in trial),
                temperature_k,
                pressure_pa,
                result.selected_compressibility_factor,
            )
            direct_direction = direction[:-1]
            return float(direct_direction @ hessian @ direct_direction)

        h = 8.0e-4
        independent = (
            curvature(-2.0 * h)
            - 8.0 * curvature(-h)
            + 8.0 * curvature(h)
            - curvature(2.0 * h)
        ) / (12.0 * h)
        assert result.cubic_directional_derivative == pytest.approx(
            independent, rel=2e-8, abs=2e-8
        )

    def test_fixed_root_tpd_local_expansion_improves_with_smaller_step(self) -> None:
        components = (METHANE, ETHANE, PROPANE)
        composition = (0.5, 0.3, 0.2)
        temperature_k, pressure_pa = 280.0, 3_000_000.0
        result = _stable_result(components, composition, temperature_k, pressure_pa)
        root = result.selected_compressibility_factor
        direction = result.active_critical_direction
        assert root is not None and direction is not None
        _, feed_log_phi = _continued_log_phi(
            components, composition, temperature_k, pressure_pa, root
        )
        errors: list[float] = []
        for epsilon in (2.0e-3, 1.0e-3, 5.0e-4):
            trial = tuple(
                fraction + epsilon * component
                for fraction, component in zip(composition, direction, strict=True)
            )
            _, trial_log_phi = _continued_log_phi(
                components, trial, temperature_k, pressure_pa, root
            )
            tpd = calculate_tangent_plane_distance(
                composition, trial, feed_log_phi, trial_log_phi
            )
            approximation = (
                0.5 * float(result.lambda_min) * epsilon**2
                + float(result.cubic_directional_derivative) * epsilon**3 / 6.0
            )
            errors.append(abs(tpd - approximation))
        assert errors[2] < errors[1] < errors[0]
        assert errors[2] < 2e-13

    def test_component_permutation_preserves_physical_invariants(self) -> None:
        original = _stable_result()
        permuted = _stable_result((PROPANE, METHANE, ETHANE), (0.2, 0.5, 0.3))
        assert permuted.eigenvalues == pytest.approx(original.eigenvalues, rel=2e-13)
        assert permuted.lambda_min == pytest.approx(original.lambda_min, rel=2e-13)
        assert abs(float(permuted.cubic_directional_derivative)) == pytest.approx(
            abs(float(original.cubic_directional_derivative)), rel=2e-9
        )
        assert original.critical_composition_direction is not None
        assert permuted.critical_composition_direction is not None
        unpermuted = np.asarray(
            (
                permuted.critical_composition_direction[1],
                permuted.critical_composition_direction[2],
                permuted.critical_composition_direction[0],
            )
        )
        expected = np.asarray(original.critical_composition_direction)
        assert abs(float(np.dot(unpermuted, expected))) == pytest.approx(1.0, abs=1e-12)

    def test_reference_component_choice_preserves_orthonormal_invariants(self) -> None:
        mixture = _mixture((METHANE, ETHANE, PROPANE), (0.5, 0.3, 0.2))
        root = evaluate_feed_phase_reference(
            mixture, 280.0, 3_000_000.0
        ).selected_compressibility_factor
        assert root is not None
        first = calculate_fixed_root_mixture_criticality(
            mixture,
            280.0,
            3_000_000.0,
            root,
            reference_active_component_index=0,
        )
        last = calculate_fixed_root_mixture_criticality(
            mixture,
            280.0,
            3_000_000.0,
            root,
            reference_active_component_index=2,
        )
        assert first.eigenvalues == pytest.approx(last.eigenvalues, rel=2e-13)
        assert first.lambda_min == pytest.approx(last.lambda_min, rel=2e-13)
        assert first.cubic_directional_derivative == pytest.approx(
            last.cubic_directional_derivative, rel=2e-9
        )

    def test_cubic_convergence_sequence_is_reported_and_convergent(self) -> None:
        coarse = _stable_result(cubic_step=2e-3)
        fine = _stable_result(cubic_step=1e-3)
        assert coarse.cubic_diagnostics is not None
        assert fine.cubic_diagnostics is not None
        assert coarse.cubic_diagnostics.estimated_error is not None
        assert fine.cubic_diagnostics.estimated_error is not None
        assert (
            fine.cubic_diagnostics.estimated_error
            < coarse.cubic_diagnostics.estimated_error
        )
        assert fine.cubic_directional_derivative == pytest.approx(
            coarse.cubic_directional_derivative, rel=2e-8
        )
