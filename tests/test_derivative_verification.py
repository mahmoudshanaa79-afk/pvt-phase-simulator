"""Module 14 independent verification of Module 13 fixed-root derivatives."""

import ast
from collections.abc import Callable
from pathlib import Path

import pytest

from pvt_phase_simulator.eos.derivatives import (
    calculate_fixed_root_mixture_fugacity_derivatives,
    calculate_mixture_parameter_derivatives,
)
from tests.derivative_reference import (
    RootTrackingError,
    VerificationState,
    composition_richardson,
    independent_log_fugacity_algebra,
    log_pressure_richardson,
    ordinary_state,
    perturb_simplex,
    pressure_richardson,
    temperature_richardson,
)
from tests.derivative_verification import (
    EOS_STATES,
    VerificationEntry,
    VerificationReport,
    run_verification_matrix,
)

FAMILY_TOLERANCES: dict[str, tuple[float, float]] = {
    "pure_alpha_aalpha_temperature": (1e-13, 5e-11),
    "A_derivatives": (1e-11, 5e-10),
    "B_derivatives": (1e-11, 5e-10),
    "mixing_temperature": (1e-12, 5e-10),
    "mixing_composition": (1e-11, 5e-10),
    "Z_pressure": (2e-9, 5e-7),
    "Z_temperature": (3e-9, 5e-7),
    "Z_composition": (1e-7, 5e-7),
    "lnphi_pressure": (2e-9, 5e-7),
    "lnphi_temperature": (4e-9, 5e-7),
    "lnphi_composition": (2e-7, 5e-7),
    "cubic_identity": (3e-15, 0.0),
}


@pytest.fixture(scope="module")
def report() -> VerificationReport:
    return run_verification_matrix()


def _within_tolerance(entry: VerificationEntry) -> bool:
    absolute_tolerance, relative_tolerance = FAMILY_TOLERANCES[entry.family]
    scale = max(abs(entry.analytical), abs(entry.reference))
    return entry.absolute_error <= absolute_tolerance + relative_tolerance * scale


def _balanced_state() -> VerificationState:
    return next(state for state in EOS_STATES if state.case_id == "ternary_balanced")


def _assert_initial_second_order_or_roundoff(
    result: object, analytical: float, component_index: int = 0
) -> None:
    errors = tuple(
        abs(values[component_index] - analytical)
        for values in result.central_differences
    )
    roundoff_floor = 2e-12 * max(1.0, abs(analytical))
    assert errors[0] <= roundoff_floor or errors[1] <= 0.35 * errors[0]


class TestVerificationCoverageAndIndependence:
    def test_every_required_family_has_substantial_scalar_coverage(
        self, report: VerificationReport
    ) -> None:
        expected = set(FAMILY_TOLERANCES)
        observed = {entry.family for entry in report.entries}
        assert observed == expected
        assert len(report.explicit_case_ids) == 21
        assert len(report.entries) == 774
        assert all(report.summary(family).count > 0 for family in expected)

    def test_all_observed_errors_meet_predeclared_combined_tolerances(
        self, report: VerificationReport
    ) -> None:
        failures = [entry for entry in report.entries if not _within_tolerance(entry)]
        assert failures == []

    def test_reference_module_does_not_import_production_derivatives(self) -> None:
        path = Path(__file__).with_name("derivative_reference.py")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported_modules = {
            node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        }
        assert "pvt_phase_simulator.eos.derivatives" not in imported_modules

    def test_complex_step_is_confined_to_isolated_algebra(self) -> None:
        path = Path(__file__).with_name("derivative_reference.py")
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        complex_functions = {
            node.name: ast.get_source_segment(source, node) or ""
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name.startswith("complex_")
        }
        combined = "\n".join(complex_functions.values())
        assert "calculate_compressibility_roots" not in combined
        assert "calculate_mixture_fugacity_coefficients" not in combined
        assert "classify_mechanical_stability" not in combined

    def test_matrix_is_deterministic(self, report: VerificationReport) -> None:
        repeated = run_verification_matrix()
        assert repeated == report


class TestRichardsonAndRootTracking:
    def test_every_richardson_route_uses_four_predetermined_steps(self) -> None:
        state = _balanced_state()
        baseline = ordinary_state(state)
        results = (
            pressure_richardson(
                state, baseline, lambda value: (value.parameters.A_mix,)
            ),
            log_pressure_richardson(state, baseline, lambda value: (value.root,)),
            temperature_richardson(state, baseline, lambda value: (value.root,)),
            composition_richardson(
                state,
                baseline,
                0,
                2,
                lambda value: value.log_fugacity_coefficients,
            ),
        )
        for result in results:
            assert result.step_sizes == tuple(
                result.step_sizes[0] / 2**index for index in range(4)
            )
            assert len(result.central_differences) == 4
            assert len(result.richardson_estimates) == 3
            coarse, fine = result.central_differences[:2]
            expected = tuple(
                fine_value + (fine_value - coarse_value) / 3.0
                for coarse_value, fine_value in zip(coarse, fine, strict=True)
            )
            assert result.reference == expected

    def test_smooth_nonlinear_families_show_initial_second_order_convergence(
        self,
    ) -> None:
        state = _balanced_state()
        baseline = ordinary_state(state)
        parameter = calculate_mixture_parameter_derivatives(baseline.parameters)
        fugacity = calculate_fixed_root_mixture_fugacity_derivatives(
            baseline.parameters, baseline.root
        )
        assert fugacity.pressure_root_derivative.derivative is not None
        assert fugacity.temperature_root_derivative.derivative is not None
        assert fugacity.composition_root_derivatives[0].derivative is not None
        assert fugacity.log_fugacity_temperature_derivatives_per_k is not None
        assert fugacity.log_fugacity_composition_derivatives is not None
        checks: tuple[tuple[object, float, int], ...] = (
            (
                temperature_richardson(
                    state, baseline, lambda value: (value.parameters.A_mix,)
                ),
                parameter.A_mix_temperature_derivative_per_k,
                0,
            ),
            (
                pressure_richardson(state, baseline, lambda value: (value.root,)),
                fugacity.pressure_root_derivative.derivative,
                0,
            ),
            (
                temperature_richardson(state, baseline, lambda value: (value.root,)),
                fugacity.temperature_root_derivative.derivative,
                0,
            ),
            (
                composition_richardson(
                    state, baseline, 0, 2, lambda value: (value.root,)
                ),
                fugacity.composition_root_derivatives[0].derivative,
                0,
            ),
            (
                temperature_richardson(
                    state,
                    baseline,
                    lambda value: value.log_fugacity_coefficients,
                ),
                fugacity.log_fugacity_temperature_derivatives_per_k[0],
                0,
            ),
            (
                composition_richardson(
                    state,
                    baseline,
                    0,
                    2,
                    lambda value: value.log_fugacity_coefficients,
                ),
                fugacity.log_fugacity_composition_derivatives[0][0],
                0,
            ),
        )
        for result, analytical, index in checks:
            _assert_initial_second_order_or_roundoff(result, analytical, index)

    def test_root_tracker_rejects_root_count_change(self) -> None:
        state = next(
            item for item in EOS_STATES if item.case_id == "ch4_c3_three_root_vapor"
        )
        baseline = ordinary_state(state)
        with pytest.raises(RootTrackingError, match="root_count_changed"):
            ordinary_state(state, pressure_pa=8_000_000.0, baseline=baseline)

    def test_only_boundary_coordinate_is_excluded(
        self, report: VerificationReport
    ) -> None:
        assert report.exclusions == (
            ("ternary_zero_ethane:u[1|r=2]", "composition_boundary"),
        )


class TestScientificIdentitiesAndLimits:
    def test_independent_cubic_total_derivative_identity(
        self, report: VerificationReport
    ) -> None:
        summary = report.summary("cubic_identity")
        assert summary.count == 36
        assert summary.maximum_absolute_error <= 3e-15

    def test_pressure_log_pressure_chain_rules(self) -> None:
        state = _balanced_state()
        baseline = ordinary_state(state)
        parameter = calculate_mixture_parameter_derivatives(baseline.parameters)
        fugacity = calculate_fixed_root_mixture_fugacity_derivatives(
            baseline.parameters, baseline.root
        )
        pressure = state.pressure_pa
        assert parameter.A_mix_log_pressure_derivative == pytest.approx(
            pressure * parameter.A_mix_pressure_derivative_per_pa, rel=2e-16
        )
        assert parameter.B_mix_log_pressure_derivative == pytest.approx(
            pressure * parameter.B_mix_pressure_derivative_per_pa, rel=2e-16
        )
        assert fugacity.pressure_root_derivative.derivative is not None
        assert fugacity.log_fugacity_pressure_derivatives_per_pa is not None
        assert fugacity.log_fugacity_log_pressure_derivatives is not None
        assert fugacity.log_fugacity_log_pressure_derivatives == pytest.approx(
            tuple(
                pressure * value
                for value in fugacity.log_fugacity_pressure_derivatives_per_pa
            ),
            rel=2e-16,
        )

    def test_zero_fraction_boundary_has_labeled_one_sided_check(self) -> None:
        state = next(
            item for item in EOS_STATES if item.case_id == "ternary_zero_ethane"
        )
        baseline = ordinary_state(state)
        parameter = calculate_mixture_parameter_derivatives(baseline.parameters)
        step = 1e-5

        def values(delta: float) -> tuple[float, ...]:
            perturbed = perturb_simplex(state.fractions, 1, 2, delta)
            ordinary = ordinary_state(state, fractions=perturbed, baseline=baseline)
            return (
                ordinary.parameters.a_alpha_mix,
                ordinary.parameters.b_mix,
                ordinary.parameters.A_mix,
                ordinary.parameters.B_mix,
                *ordinary.component_attraction_sums,
            )

        base_values = values(0.0)
        first = values(step)
        second = values(2.0 * step)
        one_sided = tuple(
            (-3.0 * base + 4.0 * at_h - at_2h) / (2.0 * step)
            for base, at_h, at_2h in zip(base_values, first, second, strict=True)
        )
        analytical = (
            parameter.a_alpha_mix_composition_derivatives[1],
            parameter.b_mix_composition_derivatives[1],
            parameter.A_mix_composition_derivatives[1],
            parameter.B_mix_composition_derivatives[1],
            *(
                row[1]
                for row in parameter.component_attraction_sum_composition_derivatives
            ),
        )
        assert analytical == pytest.approx(one_sided, rel=2e-8, abs=2e-9)

    def test_permutation_covariance_of_full_composition_jacobians(self) -> None:
        forward_state = _balanced_state()
        reverse_state = next(
            state for state in EOS_STATES if state.case_id == "ternary_reversed"
        )
        forward_base = ordinary_state(forward_state)
        reverse_base = ordinary_state(reverse_state)
        forward = calculate_fixed_root_mixture_fugacity_derivatives(
            forward_base.parameters, forward_base.root, reference_component_index=2
        )
        reverse = calculate_fixed_root_mixture_fugacity_derivatives(
            reverse_base.parameters, reverse_base.root, reference_component_index=0
        )
        assert forward.log_fugacity_composition_derivatives is not None
        assert reverse.log_fugacity_composition_derivatives is not None
        forward_columns = tuple(
            forward.component_names[index]
            for index in forward.parameter_derivatives.independent_component_indices
        )
        reverse_columns = tuple(
            reverse.component_names[index]
            for index in reverse.parameter_derivatives.independent_component_indices
        )
        reverse_named = {
            (row_name, column_name): reverse.log_fugacity_composition_derivatives[row][
                column
            ]
            for row, row_name in enumerate(reverse.component_names)
            for column, column_name in enumerate(reverse_columns)
        }
        for row, row_name in enumerate(forward.component_names):
            for column, column_name in enumerate(forward_columns):
                assert forward.log_fugacity_composition_derivatives[row][
                    column
                ] == pytest.approx(
                    reverse_named[(row_name, column_name)], rel=3e-13, abs=3e-13
                )


class TestConditioningAndAdversarialSensitivity:
    def test_near_singular_study_shows_worsening_conditioning(
        self, report: VerificationReport
    ) -> None:
        rows = report.near_singular
        assert len(rows) == 5
        assert all(
            later.absolute_cubic_partial_z < earlier.absolute_cubic_partial_z
            for earlier, later in zip(rows[:-1], rows[1:], strict=True)
        )
        assert all(
            later.derivative_magnitude > earlier.derivative_magnitude
            for earlier, later in zip(rows[:-1], rows[1:], strict=True)
        )
        assert rows[-1].absolute_error > rows[0].absolute_error

    @pytest.mark.parametrize(
        ("family", "mutation"),
        [
            ("A_derivatives", lambda value: -value),
            ("mixing_composition", lambda value: 0.5 * value),
            ("Z_pressure", lambda value: 0.0),
            ("lnphi_temperature", lambda value: -value),
            ("lnphi_composition", lambda value: 0.5 * value),
        ],
    )
    def test_common_formula_mutations_are_detected(
        self,
        report: VerificationReport,
        family: str,
        mutation: Callable[[float], float],
    ) -> None:
        source = max(
            (entry for entry in report.entries if entry.family == family),
            key=lambda entry: abs(entry.analytical),
        )
        mutated = VerificationEntry(
            family=source.family,
            case_id=source.case_id,
            route="adversarial_mutation",
            analytical=mutation(source.analytical),
            reference=source.reference,
            absolute_error=abs(mutation(source.analytical) - source.reference),
            relative_error=None,
        )
        assert not _within_tolerance(mutated)

    def test_missing_pressure_to_log_pressure_factor_is_detected(self) -> None:
        state = _balanced_state()
        baseline = ordinary_state(state)
        derivative = calculate_mixture_parameter_derivatives(baseline.parameters)
        assert derivative.A_mix_pressure_derivative_per_pa != pytest.approx(
            derivative.A_mix_log_pressure_derivative,
            rel=FAMILY_TOLERANCES["A_derivatives"][1],
            abs=FAMILY_TOLERANCES["A_derivatives"][0],
        )

    def test_omitting_implicit_z_pathway_is_detected(self) -> None:
        state = _balanced_state()
        baseline = ordinary_state(state)
        full = calculate_fixed_root_mixture_fugacity_derivatives(
            baseline.parameters, baseline.root
        )
        assert full.log_fugacity_pressure_derivatives_per_pa is not None
        step = 1e-3 * state.pressure_pa
        plus_parameters = ordinary_state(
            state, pressure_pa=state.pressure_pa + step, baseline=baseline
        ).parameters
        minus_parameters = ordinary_state(
            state, pressure_pa=state.pressure_pa - step, baseline=baseline
        ).parameters
        explicit_only = tuple(
            (high - low) / (2.0 * step)
            for high, low in zip(
                independent_log_fugacity_algebra(plus_parameters, baseline.root),
                independent_log_fugacity_algebra(minus_parameters, baseline.root),
                strict=True,
            )
        )
        assert any(
            actual != pytest.approx(partial, rel=5e-7, abs=2e-9)
            for actual, partial in zip(
                full.log_fugacity_pressure_derivatives_per_pa,
                explicit_only,
                strict=True,
            )
        )

    def test_omitting_explicit_composition_pathway_is_detected(self) -> None:
        state = _balanced_state()
        baseline = ordinary_state(state)
        full = calculate_fixed_root_mixture_fugacity_derivatives(
            baseline.parameters, baseline.root
        )
        assert full.log_fugacity_composition_derivatives is not None
        root_derivative = full.composition_root_derivatives[0].derivative
        assert root_derivative is not None
        z_step = 1e-6
        d_log_phi_d_z = tuple(
            (high - low) / (2.0 * z_step)
            for high, low in zip(
                independent_log_fugacity_algebra(
                    baseline.parameters, baseline.root + z_step
                ),
                independent_log_fugacity_algebra(
                    baseline.parameters, baseline.root - z_step
                ),
                strict=True,
            )
        )
        root_only = tuple(value * root_derivative for value in d_log_phi_d_z)
        full_column = tuple(row[0] for row in full.log_fugacity_composition_derivatives)
        assert any(
            actual != pytest.approx(partial, rel=5e-7, abs=2e-7)
            for actual, partial in zip(full_column, root_only, strict=True)
        )

    def test_component_order_and_jacobian_orientation_are_detectable(self) -> None:
        state = _balanced_state()
        baseline = ordinary_state(state)
        result = calculate_fixed_root_mixture_fugacity_derivatives(
            baseline.parameters, baseline.root
        )
        assert result.log_fugacity_composition_derivatives is not None
        matrix = result.log_fugacity_composition_derivatives
        assert len(matrix) == 3
        assert all(len(row) == 2 for row in matrix)
        transposed = tuple(zip(*matrix, strict=True))
        assert len(transposed) == 2
        assert transposed != matrix
