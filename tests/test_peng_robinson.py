"""Tests for Peng–Robinson calculations."""

from math import exp

import pytest

from pvt_phase_simulator.eos.peng_robinson import (
    PENG_ROBINSON_OMEGA_A,
    PENG_ROBINSON_OMEGA_B,
    FugacityRootResult,
    MechanicalStabilityClassification,
    PengRobinsonCubicCoefficients,
    StableRootResult,
    _deduplicate_sorted_roots,
    _exponentiate_fugacity_coefficient,
    _is_numerically_real_root,
    _root_uncertainty_tolerance,
    calculate_A_parameter,
    calculate_a_parameter,
    calculate_alpha,
    calculate_B_parameter,
    calculate_b_parameter,
    calculate_compressibility_roots,
    calculate_cubic_coefficients,
    calculate_cubic_discriminant,
    calculate_cubic_residual,
    calculate_fugacity_coefficient,
    calculate_fugacity_pa,
    calculate_kappa,
    calculate_log_fugacity_coefficient,
    calculate_peng_robinson_parameters,
    calculate_reduced_temperature,
    calculate_stable_compressibility_result,
    classify_mechanical_stability,
    evaluate_fugacity_roots,
    filter_mechanically_stable_compressibility_roots,
    filter_physical_compressibility_roots,
    select_stable_root,
    solve_compressibility_roots,
)
from pvt_phase_simulator.fluid_models import METHANE

TEMPERATURE_K = 300.0
PRESSURE_PA = 10_000_000.0
CRITICAL_TEMPERATURE_K = METHANE.critical_temperature_k
CRITICAL_PRESSURE_PA = METHANE.critical_pressure_pa
ACENTRIC_FACTOR = METHANE.acentric_factor


def test_calculate_kappa_for_methane() -> None:
    """Methane kappa should match an independent Decimal reference."""

    assert calculate_kappa(ACENTRIC_FACTOR) == pytest.approx(
        0.39157219968,
        abs=1e-14,
    )


def test_calculate_reduced_temperature_for_methane() -> None:
    """Reduced temperature should match an independent Decimal reference."""

    assert calculate_reduced_temperature(
        TEMPERATURE_K,
        CRITICAL_TEMPERATURE_K,
    ) == pytest.approx(1.5743073047858942, abs=1e-14)


def test_calculate_alpha_for_methane() -> None:
    """Alpha should match an independent Decimal reference."""

    assert calculate_alpha(
        TEMPERATURE_K,
        CRITICAL_TEMPERATURE_K,
        ACENTRIC_FACTOR,
    ) == pytest.approx(0.8104699865610172, abs=1e-14)


def test_calculate_a_parameter_for_methane() -> None:
    """The a parameter should match an independent SI Decimal reference."""

    assert calculate_a_parameter(
        CRITICAL_TEMPERATURE_K,
        CRITICAL_PRESSURE_PA,
    ) == pytest.approx(0.2495708044210156, abs=1e-14)


def test_calculate_b_parameter_for_methane() -> None:
    """The b parameter should match an independent SI Decimal reference."""

    assert calculate_b_parameter(
        CRITICAL_TEMPERATURE_K,
        CRITICAL_PRESSURE_PA,
    ) == pytest.approx(2.680175485495062e-05, abs=1e-16)


def test_calculate_A_parameter_for_methane() -> None:
    """Dimensionless A should match an independent Decimal reference."""

    a_parameter = calculate_a_parameter(
        CRITICAL_TEMPERATURE_K,
        CRITICAL_PRESSURE_PA,
    )
    alpha = calculate_alpha(
        TEMPERATURE_K,
        CRITICAL_TEMPERATURE_K,
        ACENTRIC_FACTOR,
    )
    assert calculate_A_parameter(
        PRESSURE_PA,
        TEMPERATURE_K,
        a_parameter,
        alpha,
    ) == pytest.approx(0.3251021457172964, abs=1e-14)


def test_calculate_B_parameter_for_methane() -> None:
    """Dimensionless B should match an independent Decimal reference."""

    b_parameter = calculate_b_parameter(
        CRITICAL_TEMPERATURE_K,
        CRITICAL_PRESSURE_PA,
    )
    assert calculate_B_parameter(
        PRESSURE_PA,
        TEMPERATURE_K,
        b_parameter,
    ) == pytest.approx(0.10745033918942425, abs=1e-14)


def test_reduced_temperature_is_one_at_critical_temperature() -> None:
    """Reduced temperature should be exactly one when T equals Tc."""

    assert calculate_reduced_temperature(190.56, 190.56) == 1.0


def test_alpha_is_one_at_critical_temperature() -> None:
    """Alpha should be one when T equals Tc for any finite acentric factor."""

    assert calculate_alpha(190.56, 190.56, ACENTRIC_FACTOR) == 1.0


def test_calculate_all_parameters_for_methane() -> None:
    """The orchestration function should return every independently derived value."""

    result = calculate_peng_robinson_parameters(
        TEMPERATURE_K,
        PRESSURE_PA,
        CRITICAL_TEMPERATURE_K,
        CRITICAL_PRESSURE_PA,
        ACENTRIC_FACTOR,
    )

    assert result.reduced_temperature == pytest.approx(
        calculate_reduced_temperature(TEMPERATURE_K, CRITICAL_TEMPERATURE_K)
    )
    assert result.kappa == pytest.approx(calculate_kappa(ACENTRIC_FACTOR))
    assert result.alpha == pytest.approx(
        calculate_alpha(
            TEMPERATURE_K,
            CRITICAL_TEMPERATURE_K,
            ACENTRIC_FACTOR,
        )
    )
    assert result.a == pytest.approx(
        calculate_a_parameter(CRITICAL_TEMPERATURE_K, CRITICAL_PRESSURE_PA)
    )
    assert result.b == pytest.approx(
        calculate_b_parameter(CRITICAL_TEMPERATURE_K, CRITICAL_PRESSURE_PA)
    )
    assert result.A == pytest.approx(
        calculate_A_parameter(PRESSURE_PA, TEMPERATURE_K, result.a, result.alpha)
    )
    assert result.B == pytest.approx(
        calculate_B_parameter(PRESSURE_PA, TEMPERATURE_K, result.b)
    )


@pytest.mark.parametrize("temperature_k", [0.0, -1.0])
def test_reduced_temperature_rejects_non_positive_temperature(
    temperature_k: float,
) -> None:
    """Temperature must be greater than zero."""

    with pytest.raises(ValueError, match="temperature_k"):
        calculate_reduced_temperature(temperature_k, CRITICAL_TEMPERATURE_K)


@pytest.mark.parametrize("critical_temperature_k", [0.0, -1.0])
def test_reduced_temperature_rejects_non_positive_critical_temperature(
    critical_temperature_k: float,
) -> None:
    """Critical temperature must be greater than zero."""

    with pytest.raises(ValueError, match="critical_temperature_k"):
        calculate_reduced_temperature(TEMPERATURE_K, critical_temperature_k)


@pytest.mark.parametrize("critical_temperature_k", [0.0, -1.0])
def test_a_parameter_rejects_non_positive_critical_temperature(
    critical_temperature_k: float,
) -> None:
    """The a parameter requires a positive critical temperature."""

    with pytest.raises(ValueError, match="critical_temperature_k"):
        calculate_a_parameter(critical_temperature_k, CRITICAL_PRESSURE_PA)


@pytest.mark.parametrize("critical_pressure_pa", [0.0, -1.0])
def test_a_parameter_rejects_non_positive_critical_pressure(
    critical_pressure_pa: float,
) -> None:
    """The a parameter requires a positive critical pressure."""

    with pytest.raises(ValueError, match="critical_pressure_pa"):
        calculate_a_parameter(CRITICAL_TEMPERATURE_K, critical_pressure_pa)


@pytest.mark.parametrize("critical_pressure_pa", [0.0, -1.0])
def test_b_parameter_rejects_non_positive_critical_pressure(
    critical_pressure_pa: float,
) -> None:
    """The b parameter requires a positive critical pressure."""

    with pytest.raises(ValueError, match="critical_pressure_pa"):
        calculate_b_parameter(CRITICAL_TEMPERATURE_K, critical_pressure_pa)


@pytest.mark.parametrize(
    ("pressure_pa", "temperature_k", "a_parameter", "alpha"),
    [
        (-1.0, TEMPERATURE_K, 1.0, 1.0),
        (PRESSURE_PA, 0.0, 1.0, 1.0),
        (PRESSURE_PA, -1.0, 1.0, 1.0),
        (PRESSURE_PA, TEMPERATURE_K, 0.0, 1.0),
        (PRESSURE_PA, TEMPERATURE_K, -1.0, 1.0),
        (PRESSURE_PA, TEMPERATURE_K, 1.0, 0.0),
        (PRESSURE_PA, TEMPERATURE_K, 1.0, -1.0),
    ],
)
def test_A_parameter_rejects_invalid_inputs(
    pressure_pa: float,
    temperature_k: float,
    a_parameter: float,
    alpha: float,
) -> None:
    """The A parameter should reject inputs outside its valid domain."""

    with pytest.raises(ValueError):
        calculate_A_parameter(
            pressure_pa,
            temperature_k,
            a_parameter,
            alpha,
        )


@pytest.mark.parametrize(
    ("pressure_pa", "temperature_k", "b_parameter"),
    [
        (-1.0, TEMPERATURE_K, 1.0),
        (PRESSURE_PA, 0.0, 1.0),
        (PRESSURE_PA, -1.0, 1.0),
        (PRESSURE_PA, TEMPERATURE_K, 0.0),
        (PRESSURE_PA, TEMPERATURE_K, -1.0),
    ],
)
def test_B_parameter_rejects_invalid_inputs(
    pressure_pa: float,
    temperature_k: float,
    b_parameter: float,
) -> None:
    """The B parameter should reject inputs outside its valid domain."""

    with pytest.raises(ValueError):
        calculate_B_parameter(pressure_pa, temperature_k, b_parameter)


def test_dimensionless_parameters_allow_zero_pressure() -> None:
    """A and B should be zero when pressure is zero."""

    assert calculate_A_parameter(0.0, TEMPERATURE_K, 1.0, 1.0) == 0.0
    assert calculate_B_parameter(0.0, TEMPERATURE_K, 1.0) == 0.0


def test_calculate_cubic_coefficients_for_methane() -> None:
    """Methane coefficients should match independent Decimal references."""

    A = 0.32510214571729645
    B = 0.10745033918942425

    result = calculate_cubic_coefficients(A, B)

    assert result.z3 == 1.0
    assert result.z2 == pytest.approx(-0.8925496608105758, abs=1e-14)
    assert result.z1 == pytest.approx(0.07556474116268096, abs=1e-14)
    assert result.z0 == pytest.approx(-0.022146184444611684, abs=1e-14)


def test_solve_compressibility_roots_for_one_real_root() -> None:
    """The methane example should have one real mathematical root."""

    coefficients = calculate_cubic_coefficients(
        A=0.32510214571729645,
        B=0.10745033918942425,
    )

    assert solve_compressibility_roots(coefficients) == pytest.approx(
        (0.8337767914856751,),
        abs=1e-12,
    )


def test_solve_compressibility_roots_for_three_real_roots() -> None:
    """A verified subcritical cubic should return its three real roots."""

    coefficients = calculate_cubic_coefficients(A=0.05, B=0.005)

    # Independently refined with scipy.optimize.brentq; residuals are below 5e-16.
    expected = (
        0.006765344821898573,
        0.03486502042993024,
        0.9533696347481707,
    )

    assert solve_compressibility_roots(coefficients) == pytest.approx(
        expected,
        abs=1e-12,
    )


@pytest.mark.parametrize(
    ("A", "B"),
    [
        (0.32510214571729645, 0.10745033918942425),
        (0.05, 0.005),
    ],
)
def test_compressibility_roots_satisfy_the_cubic(A: float, B: float) -> None:
    """Every returned real root should have a small polynomial residual."""

    coefficients = calculate_cubic_coefficients(A, B)
    roots = solve_compressibility_roots(coefficients)

    for root in roots:
        residual = (
            (coefficients.z3 * root + coefficients.z2) * root + coefficients.z1
        ) * root + coefficients.z0
        assert abs(residual) <= 1e-12


def test_solve_compressibility_roots_removes_repeated_roots() -> None:
    """Repeated roots should appear only once in the result."""

    coefficients = PengRobinsonCubicCoefficients(
        z3=1.0,
        z2=-2.0,
        z1=1.0,
        z0=0.0,
    )

    assert solve_compressibility_roots(coefficients) == pytest.approx((0.0, 1.0))


def test_solve_compressibility_roots_sorts_and_preserves_negative_roots() -> None:
    """Mathematical roots should be sorted without removing negative values."""

    coefficients = PengRobinsonCubicCoefficients(
        z3=1.0,
        z2=-2.0,
        z1=-1.0,
        z0=2.0,
    )

    assert solve_compressibility_roots(coefficients) == pytest.approx((-1.0, 1.0, 2.0))


def test_solve_compressibility_roots_filters_imaginary_roots() -> None:
    """Only roots within the imaginary tolerance should be retained."""

    coefficients = PengRobinsonCubicCoefficients(
        z3=1.0,
        z2=0.0,
        z1=1.0,
        z0=0.0,
    )

    assert solve_compressibility_roots(coefficients) == pytest.approx((0.0,))


@pytest.mark.parametrize("imaginary_tolerance", [0.0, -1.0])
def test_solve_compressibility_roots_rejects_invalid_tolerance(
    imaginary_tolerance: float,
) -> None:
    """Imaginary tolerance must be greater than zero."""

    coefficients = calculate_cubic_coefficients(A=0.0, B=0.0)

    with pytest.raises(ValueError, match="imaginary_tolerance"):
        solve_compressibility_roots(coefficients, imaginary_tolerance)


def test_filter_physical_compressibility_roots_uses_Z_greater_than_B() -> None:
    """Only roots greater than B by more than the tolerance should remain."""

    roots = (-1.0, 0.1, 0.2, 0.3)

    assert filter_physical_compressibility_roots(
        roots,
        B=0.15,
    ) == pytest.approx((0.2, 0.3))


def test_filter_physical_compressibility_roots_honors_tolerance() -> None:
    """A root too close to B should not be considered physically usable."""

    roots = (0.1 + 5e-11, 0.2)

    assert filter_physical_compressibility_roots(
        roots,
        B=0.1,
        tolerance=1e-10,
    ) == pytest.approx((0.2,))


def test_filter_physical_compressibility_roots_rejects_negative_B() -> None:
    """B must be non-negative."""

    with pytest.raises(ValueError, match="B"):
        filter_physical_compressibility_roots((1.0,), B=-0.1)


@pytest.mark.parametrize("tolerance", [0.0, -1.0])
def test_filter_physical_compressibility_roots_rejects_invalid_tolerance(
    tolerance: float,
) -> None:
    """Physical-root tolerance must be greater than zero."""

    with pytest.raises(ValueError, match="tolerance"):
        filter_physical_compressibility_roots((1.0,), B=0.1, tolerance=tolerance)


def test_filter_physical_compressibility_roots_rejects_empty_result() -> None:
    """Filtering should fail when no roots satisfy Z > B."""

    with pytest.raises(ValueError, match="No physical"):
        filter_physical_compressibility_roots((0.1, 0.2), B=0.2)


def test_filter_mechanically_stable_roots_removes_middle_root() -> None:
    """The positive-slope middle root should be removed."""

    roots = (
        0.006765344821898573,
        0.03486502042993024,
        0.9533696347481707,
    )

    assert filter_mechanically_stable_compressibility_roots(
        roots,
        A=0.05,
        B=0.005,
    ) == pytest.approx(
        (roots[0], roots[2]),
        abs=1e-14,
    )


def test_filter_mechanically_stable_roots_rejects_unstable_only_result() -> None:
    """Filtering should fail when only the unstable middle root is supplied."""

    with pytest.raises(ValueError, match="mechanically stable"):
        filter_mechanically_stable_compressibility_roots(
            (0.03486502042993024,),
            A=0.05,
            B=0.005,
        )


@pytest.mark.parametrize(
    ("A", "B", "parameter_name"),
    [
        (-0.1, 0.1, "A"),
        (0.1, -0.1, "B"),
    ],
)
def test_calculate_cubic_coefficients_rejects_invalid_inputs(
    A: float,
    B: float,
    parameter_name: str,
) -> None:
    """Cubic coefficients require non-negative A and B."""

    with pytest.raises(ValueError, match=parameter_name):
        calculate_cubic_coefficients(A, B)


def test_cubic_allows_B_equal_to_one() -> None:
    """Cubic construction should not impose a nonstandard B < 1 restriction."""

    assert calculate_compressibility_roots(A=1.0, B=1.0) == pytest.approx(
        (1.8608058531117034,),
        abs=1e-12,
    )


def test_calculate_compressibility_roots_for_methane() -> None:
    """The convenience function should return the methane physical root."""

    assert calculate_compressibility_roots(
        A=0.32510214571729645,
        B=0.10745033918942425,
    ) == pytest.approx((0.8337767914856751,), abs=1e-12)


def test_calculate_compressibility_roots_at_ideal_limit() -> None:
    """At A = B = 0, only Z = 1 should pass the physical filter."""

    assert calculate_compressibility_roots(A=0.0, B=0.0) == pytest.approx((1.0,))


def test_ideal_pressure_fugacity_behavior() -> None:
    """The ideal-pressure limit should have phi = 1 and zero fugacity."""

    assert calculate_log_fugacity_coefficient(1.0, A=0.0, B=0.0) == 0.0
    assert calculate_fugacity_coefficient(1.0, A=0.0, B=0.0) == 1.0
    assert calculate_fugacity_pa(0.0, 1.0) == 0.0


def test_calculate_log_fugacity_coefficient_for_methane() -> None:
    """Methane ln(phi) should match an independent high-precision result."""

    result = calculate_log_fugacity_coefficient(
        compressibility_factor=0.8337767914856751,
        A=0.32510214571729645,
        B=0.10745033918942425,
    )

    assert result == pytest.approx(
        -0.19491872844246484,
        abs=1e-14,
    )


def test_calculate_fugacity_coefficient_for_methane() -> None:
    """Methane phi should match an independent high-precision result."""

    result = calculate_fugacity_coefficient(
        compressibility_factor=0.8337767914856751,
        A=0.32510214571729645,
        B=0.10745033918942425,
    )

    assert result == pytest.approx(
        0.8229015338277848,
        abs=1e-14,
    )


def test_calculate_fugacity_for_methane() -> None:
    """Methane fugacity should equal its independent phi times pressure."""

    result = calculate_fugacity_pa(
        pressure_pa=10_000_000.0,
        fugacity_coefficient=0.8229015338277848,
    )

    assert result == pytest.approx(
        8_229_015.338277848,
        abs=1e-6,
    )


def test_evaluate_three_fugacity_roots() -> None:
    """Every verified root should receive its independent fugacity values."""

    roots = (
        0.006765344821898573,
        0.03486502042993024,
        0.9533696347481707,
    )
    results = evaluate_fugacity_roots(
        roots,
        A=0.05,
        B=0.005,
        pressure_pa=1_000_000.0,
    )
    expected_log_fugacities = (
        0.4337350279307379,
        1.2782924293354634,
        -0.04579230613237837,
    )
    expected_coefficients = (
        1.5430099594023506,
        3.59050344963639,
        0.9552403391497088,
    )

    assert tuple(result.compressibility_factor for result in results) == pytest.approx(
        roots,
        abs=1e-14,
    )
    assert tuple(
        result.log_fugacity_coefficient for result in results
    ) == pytest.approx(expected_log_fugacities, abs=1e-13)
    assert tuple(result.fugacity_coefficient for result in results) == pytest.approx(
        expected_coefficients,
        abs=1e-13,
    )
    assert tuple(result.fugacity_pa for result in results) == pytest.approx(
        tuple(value * 1_000_000.0 for value in expected_coefficients),
        abs=1e-7,
    )


def test_evaluate_fugacity_roots_orders_candidates_by_Z() -> None:
    """Unordered root input should produce increasing-Z results."""

    roots = (
        0.9533696347481707,
        0.006765344821898573,
        0.03486502042993024,
    )

    results = evaluate_fugacity_roots(
        roots,
        A=0.05,
        B=0.005,
        pressure_pa=1_000_000.0,
    )

    assert tuple(result.compressibility_factor for result in results) == tuple(
        sorted(roots)
    )


def test_select_stable_root_with_one_candidate() -> None:
    """One candidate should be stable without a near-equilibrium flag."""

    candidate = FugacityRootResult(
        compressibility_factor=0.8,
        log_fugacity_coefficient=-0.2,
        fugacity_coefficient=exp(-0.2),
        fugacity_pa=8_000_000.0,
    )

    assert select_stable_root((candidate,)) == StableRootResult(
        stable=candidate,
        candidates=(candidate,),
        is_near_phase_equilibrium=False,
    )


def test_select_stable_root_uses_lowest_log_fugacity() -> None:
    """The lowest ln(phi) should determine stability."""

    candidates = (
        FugacityRootResult(0.1, -0.1, exp(-0.1), 900_000.0),
        FugacityRootResult(0.9, -0.5, exp(-0.5), 600_000.0),
    )

    result = select_stable_root(candidates)

    assert result.stable is candidates[1]
    assert result.candidates == candidates
    assert result.is_near_phase_equilibrium is False


def test_select_stable_root_excludes_unstable_middle_candidate() -> None:
    """An interior cubic root must not participate in stability selection."""

    smaller_Z = FugacityRootResult(0.1, -0.2, exp(-0.2), 800_000.0)
    unstable_middle = FugacityRootResult(0.5, -1.0, exp(-1.0), 300_000.0)
    larger_Z = FugacityRootResult(0.9, -0.3, exp(-0.3), 700_000.0)

    result = select_stable_root((unstable_middle, larger_Z, smaller_Z))

    assert result.stable is larger_Z
    assert result.candidates == (unstable_middle, larger_Z, smaller_Z)
    assert result.is_near_phase_equilibrium is False


def test_near_equilibrium_compares_only_outer_branches() -> None:
    """A middle-root fugacity must not cause a false equilibrium flag."""

    smaller_Z = FugacityRootResult(0.1, -0.5, exp(-0.5), 600_000.0)
    unstable_middle = FugacityRootResult(
        0.5,
        -0.500000001,
        exp(-0.500000001),
        600_000.0,
    )
    larger_Z = FugacityRootResult(0.9, -0.1, exp(-0.1), 900_000.0)

    result = select_stable_root((smaller_Z, unstable_middle, larger_Z))

    assert result.stable is smaller_Z
    assert result.is_near_phase_equilibrium is False


def test_select_stable_root_detects_near_equal_fugacity() -> None:
    """Near-equal lowest ln(phi) values should set the equilibrium flag."""

    smaller_Z = FugacityRootResult(0.1, -0.5, exp(-0.5), 600_000.0)
    slightly_lower_log_phi = FugacityRootResult(
        0.9,
        -0.500000005,
        exp(-0.500000005),
        600_000.0,
    )

    result = select_stable_root(
        (slightly_lower_log_phi, smaller_Z),
        equilibrium_tolerance=1e-8,
    )

    assert result.is_near_phase_equilibrium is True
    assert result.stable is smaller_Z


def test_select_stable_root_breaks_exact_tie_with_smaller_Z() -> None:
    """Exact fugacity ties should deterministically choose the smaller Z."""

    larger_Z = FugacityRootResult(0.9, -0.5, exp(-0.5), 600_000.0)
    smaller_Z = FugacityRootResult(0.1, -0.5, exp(-0.5), 600_000.0)

    result = select_stable_root((larger_Z, smaller_Z))

    assert result.is_near_phase_equilibrium is True
    assert result.stable is smaller_Z


def test_select_stable_root_for_three_root_case() -> None:
    """Selection should follow independently calculated ln(phi) values."""

    roots = (
        0.006765344821898573,
        0.03486502042993024,
        0.9533696347481707,
    )
    candidates = evaluate_fugacity_roots(
        roots,
        A=0.05,
        B=0.005,
        pressure_pa=1_000_000.0,
    )

    result = select_stable_root(candidates)

    assert result.stable.compressibility_factor == pytest.approx(
        0.9533696347481707,
        abs=1e-14,
    )
    assert result.stable.log_fugacity_coefficient == pytest.approx(
        -0.04579230613237837,
        abs=1e-13,
    )
    assert result.is_near_phase_equilibrium is False


@pytest.mark.parametrize("compressibility_factor", [0.0, -1.0])
def test_log_fugacity_rejects_non_positive_Z(
    compressibility_factor: float,
) -> None:
    """Compressibility factor must be greater than zero."""

    with pytest.raises(ValueError, match="compressibility_factor"):
        calculate_log_fugacity_coefficient(
            compressibility_factor,
            A=0.1,
            B=0.01,
        )


@pytest.mark.parametrize("compressibility_factor", [0.05, 0.1])
def test_log_fugacity_rejects_non_positive_Z_minus_B(
    compressibility_factor: float,
) -> None:
    """Z - B must be a positive logarithm argument."""

    with pytest.raises(ValueError, match="logarithm argument"):
        calculate_log_fugacity_coefficient(
            compressibility_factor,
            A=0.1,
            B=0.1,
        )


def test_log_fugacity_rejects_negative_A() -> None:
    """A must be non-negative."""

    with pytest.raises(ValueError, match="A"):
        calculate_log_fugacity_coefficient(1.0, A=-0.1, B=0.1)


def test_log_fugacity_rejects_negative_B() -> None:
    """B must be non-negative."""

    with pytest.raises(ValueError, match="B"):
        calculate_log_fugacity_coefficient(1.0, A=0.1, B=-0.1)


def test_log_fugacity_rejects_zero_B_with_positive_A() -> None:
    """Positive A with B = 0 is inconsistent with the direct expression."""

    with pytest.raises(ValueError, match="B"):
        calculate_log_fugacity_coefficient(1.0, A=0.1, B=0.0)


def test_calculate_fugacity_rejects_negative_pressure() -> None:
    """Pressure must be non-negative."""

    with pytest.raises(ValueError, match="pressure_pa"):
        calculate_fugacity_pa(-1.0, 1.0)


@pytest.mark.parametrize("fugacity_coefficient", [0.0, -1.0])
def test_calculate_fugacity_rejects_non_positive_coefficient(
    fugacity_coefficient: float,
) -> None:
    """Fugacity coefficient must be greater than zero."""

    with pytest.raises(ValueError, match="fugacity_coefficient"):
        calculate_fugacity_pa(1_000_000.0, fugacity_coefficient)


def test_evaluate_fugacity_roots_rejects_empty_roots() -> None:
    """At least one physical root is required."""

    with pytest.raises(ValueError, match="roots"):
        evaluate_fugacity_roots((), A=0.1, B=0.01, pressure_pa=1_000_000.0)


def test_evaluate_fugacity_roots_rejects_non_physical_root() -> None:
    """Every supplied root must satisfy Z > B."""

    with pytest.raises(ValueError, match="logarithm argument"):
        evaluate_fugacity_roots((0.01,), A=0.1, B=0.01, pressure_pa=1_000_000.0)


def test_select_stable_root_rejects_empty_candidates() -> None:
    """At least one fugacity candidate is required."""

    with pytest.raises(ValueError, match="candidates"):
        select_stable_root(())


@pytest.mark.parametrize("equilibrium_tolerance", [0.0, -1.0])
def test_select_stable_root_rejects_invalid_tolerance(
    equilibrium_tolerance: float,
) -> None:
    """Equilibrium tolerance must be greater than zero."""

    candidate = FugacityRootResult(1.0, 0.0, 1.0, 0.0)

    with pytest.raises(ValueError, match="equilibrium_tolerance"):
        select_stable_root((candidate,), equilibrium_tolerance)


def test_calculate_stable_compressibility_result_orchestration() -> None:
    """Complete orchestration should match separately composed functions."""

    A = 0.05
    B = 0.005
    pressure_pa = 1_000_000.0
    roots = calculate_compressibility_roots(A, B)
    stable_roots = filter_mechanically_stable_compressibility_roots(roots, A, B)
    candidates = evaluate_fugacity_roots(stable_roots, A, B, pressure_pa)
    expected = select_stable_root(candidates)

    assert calculate_stable_compressibility_result(A, B, pressure_pa) == expected


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_pure_parameter_functions_reject_non_finite_inputs(value: float) -> None:
    """Pure-component parameter APIs must reject every non-finite input."""

    calls = (
        lambda: calculate_kappa(value),
        lambda: calculate_reduced_temperature(value, CRITICAL_TEMPERATURE_K),
        lambda: calculate_reduced_temperature(TEMPERATURE_K, value),
        lambda: calculate_alpha(value, CRITICAL_TEMPERATURE_K, ACENTRIC_FACTOR),
        lambda: calculate_alpha(TEMPERATURE_K, value, ACENTRIC_FACTOR),
        lambda: calculate_alpha(TEMPERATURE_K, CRITICAL_TEMPERATURE_K, value),
        lambda: calculate_a_parameter(value, CRITICAL_PRESSURE_PA),
        lambda: calculate_a_parameter(CRITICAL_TEMPERATURE_K, value),
        lambda: calculate_b_parameter(value, CRITICAL_PRESSURE_PA),
        lambda: calculate_b_parameter(CRITICAL_TEMPERATURE_K, value),
        lambda: calculate_A_parameter(value, TEMPERATURE_K, 1.0, 1.0),
        lambda: calculate_A_parameter(PRESSURE_PA, value, 1.0, 1.0),
        lambda: calculate_A_parameter(PRESSURE_PA, TEMPERATURE_K, value, 1.0),
        lambda: calculate_A_parameter(PRESSURE_PA, TEMPERATURE_K, 1.0, value),
        lambda: calculate_B_parameter(value, TEMPERATURE_K, 1.0),
        lambda: calculate_B_parameter(PRESSURE_PA, value, 1.0),
        lambda: calculate_B_parameter(PRESSURE_PA, TEMPERATURE_K, value),
    )
    for call in calls:
        with pytest.raises(ValueError):
            call()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_cubic_apis_reject_non_finite_inputs(value: float) -> None:
    """Cubic construction, evaluation, and solving require finite values."""

    with pytest.raises(ValueError):
        calculate_cubic_coefficients(value, 0.1)
    with pytest.raises(ValueError):
        calculate_cubic_coefficients(0.1, value)

    valid = calculate_cubic_coefficients(0.1, 0.01)
    with pytest.raises(ValueError):
        calculate_cubic_residual(value, valid)

    invalid = PengRobinsonCubicCoefficients(1.0, -1.0, value, 0.0)
    with pytest.raises(ValueError):
        solve_compressibility_roots(invalid)


def test_cubic_residual_matches_independent_polynomial_evaluation() -> None:
    """The shared residual helper evaluates the documented cubic."""

    coefficients = calculate_cubic_coefficients(0.05, 0.005)
    root = solve_compressibility_roots(coefficients)[-1]
    assert calculate_cubic_residual(root, coefficients) == pytest.approx(
        0.0,
        abs=1e-12,
    )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_root_filters_reject_non_finite_roots(value: float) -> None:
    """Invalid root values must not be silently filtered or retained."""

    with pytest.raises(ValueError, match="root"):
        filter_physical_compressibility_roots((value,), B=0.01)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_pure_fugacity_apis_reject_non_finite_inputs(value: float) -> None:
    """Pure fugacity paths reject non-finite thermodynamic inputs."""

    calls = (
        lambda: calculate_log_fugacity_coefficient(value, 0.1, 0.01),
        lambda: calculate_log_fugacity_coefficient(1.0, value, 0.01),
        lambda: calculate_log_fugacity_coefficient(1.0, 0.1, value),
        lambda: calculate_fugacity_pa(value, 1.0),
        lambda: calculate_fugacity_pa(1.0, value),
    )
    for call in calls:
        with pytest.raises(ValueError):
            call()


def test_fugacity_coefficient_converts_exponential_overflow_to_value_error() -> None:
    """An overflowing exponential must produce a controlled domain error."""

    with pytest.raises(ValueError, match="fugacity coefficient"):
        _exponentiate_fugacity_coefficient(1_000.0)


def test_fugacity_coefficient_rejects_exponential_underflow_to_zero() -> None:
    """A numerically underflowed fugacity coefficient is not strictly positive."""

    with pytest.raises(ValueError, match="fugacity coefficient"):
        _exponentiate_fugacity_coefficient(-1_000.0)


def test_fugacity_rejects_non_finite_product() -> None:
    """Finite inputs must not be allowed to produce infinite fugacity."""

    with pytest.raises(ValueError, match="fugacity_pa"):
        calculate_fugacity_pa(1e308, 1e308)


@pytest.mark.parametrize("field", range(4))
def test_stable_root_selection_rejects_non_finite_candidate_fields(field: int) -> None:
    """Externally constructed result records are validated before selection."""

    values = [1.0, 0.0, 1.0, 1.0]
    values[field] = float("nan")
    candidate = FugacityRootResult(*values)
    with pytest.raises(ValueError):
        select_stable_root((candidate,))


def test_repository_constants_at_nominal_methane_critical_state() -> None:
    """Rounded PR constants give one real root at the nominal methane Tc/Pc."""

    parameters = calculate_peng_robinson_parameters(
        CRITICAL_TEMPERATURE_K,
        CRITICAL_PRESSURE_PA,
        CRITICAL_TEMPERATURE_K,
        CRITICAL_PRESSURE_PA,
        ACENTRIC_FACTOR,
    )
    coefficients = calculate_cubic_coefficients(parameters.A, parameters.B)
    roots = solve_compressibility_roots(coefficients)

    assert parameters.A == PENG_ROBINSON_OMEGA_A == 0.45724
    assert PENG_ROBINSON_OMEGA_B == 0.07780
    assert parameters.B == pytest.approx(PENG_ROBINSON_OMEGA_B, abs=2e-17)
    assert coefficients == PengRobinsonCubicCoefficients(
        z3=1.0,
        z2=-0.9222,
        z1=0.28348147999999995,
        z0=-0.029049521048,
    )
    assert calculate_cubic_discriminant(coefficients) == pytest.approx(
        -1.9574436516123228e-10,
        abs=1e-20,
    )
    assert roots == pytest.approx((0.32137902517361217,), abs=1e-14)
    assert calculate_fugacity_coefficient(
        roots[0], parameters.A, parameters.B
    ) == pytest.approx(0.6426442137959292, abs=1e-14)
    diagnostic = classify_mechanical_stability(roots[0], parameters.A, parameters.B)
    assert diagnostic.derivative == pytest.approx(-0.01626804444617136, abs=1e-14)
    assert diagnostic.classification is MechanicalStabilityClassification.STABLE


@pytest.mark.parametrize(
    ("temperature_ratio", "expected_A", "expected_B", "expected_root", "expected_phi"),
    [
        (
            1.0 - 1e-4,
            0.457349370170706,
            0.07780778077807782,
            0.28395267336888547,
            0.6424853634675094,
        ),
        (
            1.0 + 1e-4,
            0.4571306656711461,
            0.07779222077792221,
            0.3359298370107594,
            0.6427900502577396,
        ),
    ],
)
def test_independent_methane_references_around_critical_temperature(
    temperature_ratio: float,
    expected_A: float,
    expected_B: float,
    expected_root: float,
    expected_phi: float,
) -> None:
    """Near-critical values match 50-digit Decimal equation evaluation."""

    parameters = calculate_peng_robinson_parameters(
        temperature_ratio * CRITICAL_TEMPERATURE_K,
        CRITICAL_PRESSURE_PA,
        CRITICAL_TEMPERATURE_K,
        CRITICAL_PRESSURE_PA,
        ACENTRIC_FACTOR,
    )
    coefficients = calculate_cubic_coefficients(parameters.A, parameters.B)
    roots = solve_compressibility_roots(coefficients)
    assert parameters.A == pytest.approx(expected_A, abs=2e-15)
    assert parameters.B == pytest.approx(expected_B, abs=2e-16)
    assert roots == pytest.approx((expected_root,), abs=2e-14)
    assert calculate_fugacity_coefficient(
        roots[0], parameters.A, parameters.B
    ) == pytest.approx(expected_phi, abs=2e-14)


def test_higher_precision_critical_constants_resolve_one_triple_root() -> None:
    """Constants derived from triple-root constraints recover Zc in float64."""

    exact_A = 0.4572355289213822
    exact_B = 0.07779607390388846
    exact_Z = 0.30740130869870386
    coefficients = calculate_cubic_coefficients(exact_A, exact_B)

    assert coefficients.z2 == pytest.approx(-3.0 * exact_Z, abs=2e-15)
    assert coefficients.z1 == pytest.approx(3.0 * exact_Z**2, abs=2e-15)
    assert coefficients.z0 == pytest.approx(-(exact_Z**3), abs=2e-15)
    assert abs(calculate_cubic_discriminant(coefficients)) <= 1e-16
    assert solve_compressibility_roots(coefficients) == pytest.approx(
        (exact_Z,),
        abs=2e-14,
    )
    diagnostic = classify_mechanical_stability(exact_Z, exact_A, exact_B)
    assert abs(diagnostic.derivative) <= diagnostic.derivative_tolerance
    assert diagnostic.classification is MechanicalStabilityClassification.MARGINAL


def test_near_spinodal_root_is_marginal_and_not_returned_as_stable() -> None:
    """A repeated spinodal root is retained diagnostically but not as stable."""

    A = 0.43714718366683
    B = 0.07334914941044646
    coefficients = calculate_cubic_coefficients(A, B)
    roots = solve_compressibility_roots(coefficients)
    assert roots == pytest.approx(
        (0.24585273921521483, 0.4349453721591239),
        abs=2e-13,
    )
    marginal = classify_mechanical_stability(roots[0], A, B)
    stable = classify_mechanical_stability(roots[1], A, B)
    assert marginal.derivative == pytest.approx(-2.913225216616411e-13, abs=1e-15)
    assert marginal.derivative_tolerance == pytest.approx(
        9.55111162511968e-13,
        rel=1e-13,
    )
    assert marginal.classification is MechanicalStabilityClassification.MARGINAL
    assert stable.classification is MechanicalStabilityClassification.STABLE
    assert filter_mechanically_stable_compressibility_roots(roots, A, B) == (roots[1],)


def test_only_marginal_critical_root_is_rejected_by_stable_filter() -> None:
    """The stable-only compatibility API must not relabel a marginal root."""

    A = 0.4572355289213822
    B = 0.07779607390388846
    roots = solve_compressibility_roots(calculate_cubic_coefficients(A, B))
    with pytest.raises(ValueError, match="mechanically stable"):
        filter_mechanically_stable_compressibility_roots(roots, A, B)


def test_genuinely_distinct_near_coalescing_roots_are_preserved() -> None:
    """Positive-discriminant roots remain separate just inside a spinodal."""

    A = 0.43714722474533796
    B = 0.07334915630303031
    coefficients = calculate_cubic_coefficients(A, B)
    assert calculate_cubic_discriminant(coefficients) == pytest.approx(
        3.995092104358555e-11,
        abs=1e-20,
    )
    assert solve_compressibility_roots(coefficients) == pytest.approx(
        (0.24576444657132412, 0.24594121939288996, 0.434945177732756),
        abs=2e-13,
    )


def test_root_deduplication_boundary_uses_conditioning_scale() -> None:
    """Synthetic candidates inside the uncertainty overlap merge; outside do not."""

    coefficients = PengRobinsonCubicCoefficients(1.0, -4.0, 5.0, -2.0)
    uncertainty = _root_uncertainty_tolerance(1.0, coefficients)
    inside = [1.0 - 0.25 * uncertainty, 1.0 + 0.25 * uncertainty, 2.0]
    outside = [1.0 - uncertainty, 1.0 + uncertainty, 2.0]
    assert _deduplicate_sorted_roots(inside, coefficients) == pytest.approx(
        (1.0, 2.0),
        abs=1e-15,
    )
    assert len(_deduplicate_sorted_roots(outside, coefficients)) == 3


def test_small_imaginary_classification_boundary_is_scale_aware() -> None:
    """Near-real conversion follows local root uncertainty and residual evidence."""

    coefficients = PengRobinsonCubicCoefficients(1.0, -4.0, 5.0, -2.0)
    uncertainty = _root_uncertainty_tolerance(1.0, coefficients)
    assert _is_numerically_real_root(
        1.0,
        0.99 * uncertainty,
        coefficients,
        imaginary_tolerance=1e-10,
    )
    assert not _is_numerically_real_root(
        1.0,
        1.01 * uncertainty,
        coefficients,
        imaginary_tolerance=1e-10,
    )
    assert not _is_numerically_real_root(
        1.1,
        1e-12,
        coefficients,
        imaginary_tolerance=1e-10,
    )


@pytest.mark.parametrize("coefficient_scale", [1e-12, 1e12])
def test_near_real_policy_is_invariant_to_polynomial_scaling(
    coefficient_scale: float,
) -> None:
    """Multiplying every coefficient does not change root classification."""

    base = PengRobinsonCubicCoefficients(1.0, -4.0, 5.0, -2.0)
    scaled = PengRobinsonCubicCoefficients(
        *(coefficient_scale * value for value in (1.0, -4.0, 5.0, -2.0))
    )
    base_uncertainty = _root_uncertainty_tolerance(1.0, base)
    assert _root_uncertainty_tolerance(1.0, scaled) == pytest.approx(
        base_uncertainty,
        rel=1e-12,
    )
    assert _is_numerically_real_root(
        1.0,
        0.5 * base_uncertainty,
        scaled,
        imaginary_tolerance=1e-10,
    )


def test_pure_fugacity_accepts_calculated_and_rounded_roots() -> None:
    """A genuine root and a harmless decimal rounding are both admissible."""

    A = 0.32510214571729645
    B = 0.10745033918942425
    root = calculate_compressibility_roots(A, B)[0]
    expected = -0.19491872844246484
    assert calculate_log_fugacity_coefficient(root, A, B) == pytest.approx(
        expected,
        abs=1e-14,
    )
    assert calculate_log_fugacity_coefficient(round(root, 10), A, B) == pytest.approx(
        expected,
        abs=2e-11,
    )


def test_pure_fugacity_rejects_arbitrary_non_root() -> None:
    """A finite value in the logarithm domain is not necessarily a cubic root."""

    with pytest.raises(ValueError, match="does not satisfy"):
        calculate_log_fugacity_coefficient(0.5, A=0.32510214571729645, B=0.1)


def test_pure_fugacity_ideal_limit_accepts_only_Z_one() -> None:
    """The exact ideal cubic retains Z=1 rather than arbitrary positive Z."""

    assert calculate_log_fugacity_coefficient(1.0, A=0.0, B=0.0) == 0.0
    assert calculate_fugacity_coefficient(1.0, A=0.0, B=0.0) == 1.0
    with pytest.raises(ValueError, match="does not satisfy"):
        calculate_log_fugacity_coefficient(2.0, A=0.0, B=0.0)


def test_pure_fugacity_accepts_every_genuine_three_root_candidate() -> None:
    """The low-level evaluator does not impose mechanical or global stability."""

    A = 0.05
    B = 0.005
    roots = calculate_compressibility_roots(A, B)
    assert len(roots) == 3
    assert all(calculate_fugacity_coefficient(root, A, B) > 0.0 for root in roots)


def test_pure_fugacity_rejects_non_root_near_repeated_ideal_root() -> None:
    """A small residual near excluded Z=0 cannot bypass root distance."""

    with pytest.raises(ValueError, match="distance tolerance"):
        calculate_log_fugacity_coefficient(1e-6, A=0.0, B=0.0)


def test_evaluate_fugacity_roots_rejects_user_supplied_non_root() -> None:
    """Multi-root orchestration applies the same supplied-root contract."""

    with pytest.raises(ValueError, match="does not satisfy"):
        evaluate_fugacity_roots((0.5,), A=0.05, B=0.005, pressure_pa=1e6)
