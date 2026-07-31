"""Tests for Peng–Robinson calculations."""

from math import sqrt

import pytest

from pvt_phase_simulator.eos.peng_robinson import (
    PengRobinsonCubicCoefficients,
    calculate_A_parameter,
    calculate_a_parameter,
    calculate_alpha,
    calculate_B_parameter,
    calculate_b_parameter,
    calculate_compressibility_roots,
    calculate_cubic_coefficients,
    calculate_kappa,
    calculate_peng_robinson_parameters,
    calculate_reduced_temperature,
    filter_physical_compressibility_roots,
    solve_compressibility_roots,
)
from pvt_phase_simulator.fluid_models import METHANE
from pvt_phase_simulator.physical_constants import UNIVERSAL_GAS_CONSTANT

TEMPERATURE_K = 300.0
PRESSURE_PA = 10_000_000.0
CRITICAL_TEMPERATURE_K = METHANE.critical_temperature_k
CRITICAL_PRESSURE_PA = METHANE.critical_pressure_pa
ACENTRIC_FACTOR = METHANE.acentric_factor


def test_calculate_kappa_for_methane() -> None:
    """Methane kappa should match the expected value."""

    expected = 0.37464 + 1.54226 * ACENTRIC_FACTOR - 0.26992 * ACENTRIC_FACTOR**2

    assert calculate_kappa(ACENTRIC_FACTOR) == pytest.approx(expected)


def test_calculate_reduced_temperature_for_methane() -> None:
    """Reduced temperature should equal temperature divided by critical temperature."""

    expected = TEMPERATURE_K / CRITICAL_TEMPERATURE_K

    assert calculate_reduced_temperature(
        TEMPERATURE_K,
        CRITICAL_TEMPERATURE_K,
    ) == pytest.approx(expected)


def test_calculate_alpha_for_methane() -> None:
    """Alpha should apply the methane temperature correction."""

    reduced_temperature = TEMPERATURE_K / CRITICAL_TEMPERATURE_K
    kappa = 0.37464 + 1.54226 * ACENTRIC_FACTOR - 0.26992 * ACENTRIC_FACTOR**2
    expected = (1.0 + kappa * (1.0 - sqrt(reduced_temperature))) ** 2

    assert calculate_alpha(
        TEMPERATURE_K,
        CRITICAL_TEMPERATURE_K,
        ACENTRIC_FACTOR,
    ) == pytest.approx(expected)


def test_calculate_a_parameter_for_methane() -> None:
    """The dimensional a parameter should match the Peng–Robinson equation."""

    expected = (
        0.45724
        * UNIVERSAL_GAS_CONSTANT**2
        * CRITICAL_TEMPERATURE_K**2
        / CRITICAL_PRESSURE_PA
    )

    assert calculate_a_parameter(
        CRITICAL_TEMPERATURE_K,
        CRITICAL_PRESSURE_PA,
    ) == pytest.approx(expected)


def test_calculate_b_parameter_for_methane() -> None:
    """The dimensional b parameter should match the Peng–Robinson equation."""

    expected = (
        0.07780 * UNIVERSAL_GAS_CONSTANT * CRITICAL_TEMPERATURE_K / CRITICAL_PRESSURE_PA
    )

    assert calculate_b_parameter(
        CRITICAL_TEMPERATURE_K,
        CRITICAL_PRESSURE_PA,
    ) == pytest.approx(expected)


def test_calculate_A_parameter_for_methane() -> None:
    """The dimensionless A parameter should match its defining equation."""

    a_parameter = calculate_a_parameter(
        CRITICAL_TEMPERATURE_K,
        CRITICAL_PRESSURE_PA,
    )
    alpha = calculate_alpha(
        TEMPERATURE_K,
        CRITICAL_TEMPERATURE_K,
        ACENTRIC_FACTOR,
    )
    expected = (
        a_parameter
        * alpha
        * PRESSURE_PA
        / (UNIVERSAL_GAS_CONSTANT**2 * TEMPERATURE_K**2)
    )

    assert calculate_A_parameter(
        PRESSURE_PA,
        TEMPERATURE_K,
        a_parameter,
        alpha,
    ) == pytest.approx(expected)


def test_calculate_B_parameter_for_methane() -> None:
    """The dimensionless B parameter should match its defining equation."""

    b_parameter = calculate_b_parameter(
        CRITICAL_TEMPERATURE_K,
        CRITICAL_PRESSURE_PA,
    )
    expected = b_parameter * PRESSURE_PA / (UNIVERSAL_GAS_CONSTANT * TEMPERATURE_K)

    assert calculate_B_parameter(
        PRESSURE_PA,
        TEMPERATURE_K,
        b_parameter,
    ) == pytest.approx(expected)


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
    """Methane cubic coefficients should match the standard equation."""

    A = 0.32510214571729645
    B = 0.10745033918942425

    result = calculate_cubic_coefficients(A, B)

    assert result == PengRobinsonCubicCoefficients(
        z3=1.0,
        z2=B - 1.0,
        z1=A - 3.0 * B**2 - 2.0 * B,
        z0=-(A * B - B**2 - B**3),
    )


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


@pytest.mark.parametrize(
    ("A", "B", "parameter_name"),
    [
        (-0.1, 0.1, "A"),
        (0.1, -0.1, "B"),
        (0.1, 1.0, "B"),
        (0.1, 1.1, "B"),
    ],
)
def test_calculate_cubic_coefficients_rejects_invalid_inputs(
    A: float,
    B: float,
    parameter_name: str,
) -> None:
    """Cubic coefficients require non-negative A and 0 <= B < 1."""

    with pytest.raises(ValueError, match=parameter_name):
        calculate_cubic_coefficients(A, B)


def test_calculate_compressibility_roots_for_methane() -> None:
    """The convenience function should return the methane physical root."""

    assert calculate_compressibility_roots(
        A=0.32510214571729645,
        B=0.10745033918942425,
    ) == pytest.approx((0.8337767914856751,), abs=1e-12)


def test_calculate_compressibility_roots_at_ideal_limit() -> None:
    """At A = B = 0, only Z = 1 should pass the physical filter."""

    assert calculate_compressibility_roots(A=0.0, B=0.0) == pytest.approx((1.0,))
