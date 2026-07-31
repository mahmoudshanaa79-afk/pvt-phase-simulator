"""Tests for Peng–Robinson calculations."""

from math import exp

import pytest

from pvt_phase_simulator.eos.peng_robinson import (
    FugacityRootResult,
    PengRobinsonCubicCoefficients,
    StableRootResult,
    calculate_A_parameter,
    calculate_a_parameter,
    calculate_alpha,
    calculate_B_parameter,
    calculate_b_parameter,
    calculate_compressibility_roots,
    calculate_cubic_coefficients,
    calculate_fugacity_coefficient,
    calculate_fugacity_pa,
    calculate_kappa,
    calculate_log_fugacity_coefficient,
    calculate_peng_robinson_parameters,
    calculate_reduced_temperature,
    calculate_stable_compressibility_result,
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
