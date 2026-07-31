"""Peng–Robinson equation-of-state calculations."""

from dataclasses import dataclass
from math import isclose, sqrt

import numpy as np

from pvt_phase_simulator.physical_constants import UNIVERSAL_GAS_CONSTANT


@dataclass(frozen=True, slots=True)
class PengRobinsonParameters:
    """Pure-component Peng–Robinson parameters."""

    reduced_temperature: float
    kappa: float
    alpha: float
    a: float
    b: float
    A: float
    B: float


@dataclass(frozen=True, slots=True)
class PengRobinsonCubicCoefficients:
    """Coefficients of the Peng–Robinson cubic in Z."""

    z3: float
    z2: float
    z1: float
    z0: float


def _require_positive(value: float, name: str) -> None:
    """Require a value greater than zero."""

    if not value > 0.0:
        raise ValueError(f"{name} must be greater than zero.")


def _require_non_negative(value: float, name: str) -> None:
    """Require a value greater than or equal to zero."""

    if not value >= 0.0:
        raise ValueError(f"{name} must be greater than or equal to zero.")


def calculate_kappa(acentric_factor: float) -> float:
    """Calculate the Peng–Robinson kappa parameter."""

    return 0.37464 + 1.54226 * acentric_factor - 0.26992 * acentric_factor**2


def calculate_reduced_temperature(
    temperature_k: float,
    critical_temperature_k: float,
) -> float:
    """Calculate reduced temperature."""

    _require_positive(temperature_k, "temperature_k")
    _require_positive(critical_temperature_k, "critical_temperature_k")

    return temperature_k / critical_temperature_k


def calculate_alpha(
    temperature_k: float,
    critical_temperature_k: float,
    acentric_factor: float,
) -> float:
    """Calculate the Peng–Robinson alpha correction."""

    reduced_temperature = calculate_reduced_temperature(
        temperature_k,
        critical_temperature_k,
    )
    kappa = calculate_kappa(acentric_factor)

    return (1.0 + kappa * (1.0 - sqrt(reduced_temperature))) ** 2


def calculate_a_parameter(
    critical_temperature_k: float,
    critical_pressure_pa: float,
) -> float:
    """Calculate the dimensional Peng–Robinson a parameter."""

    _require_positive(critical_temperature_k, "critical_temperature_k")
    _require_positive(critical_pressure_pa, "critical_pressure_pa")

    return (
        0.45724
        * UNIVERSAL_GAS_CONSTANT**2
        * critical_temperature_k**2
        / critical_pressure_pa
    )


def calculate_b_parameter(
    critical_temperature_k: float,
    critical_pressure_pa: float,
) -> float:
    """Calculate the dimensional Peng–Robinson b parameter."""

    _require_positive(critical_temperature_k, "critical_temperature_k")
    _require_positive(critical_pressure_pa, "critical_pressure_pa")

    return (
        0.07780 * UNIVERSAL_GAS_CONSTANT * critical_temperature_k / critical_pressure_pa
    )


def calculate_A_parameter(
    pressure_pa: float,
    temperature_k: float,
    a_parameter: float,
    alpha: float,
) -> float:
    """Calculate the dimensionless Peng–Robinson A parameter."""

    _require_non_negative(pressure_pa, "pressure_pa")
    _require_positive(temperature_k, "temperature_k")
    _require_positive(a_parameter, "a_parameter")
    _require_positive(alpha, "alpha")

    return (
        a_parameter
        * alpha
        * pressure_pa
        / (UNIVERSAL_GAS_CONSTANT**2 * temperature_k**2)
    )


def calculate_B_parameter(
    pressure_pa: float,
    temperature_k: float,
    b_parameter: float,
) -> float:
    """Calculate the dimensionless Peng–Robinson B parameter."""

    _require_non_negative(pressure_pa, "pressure_pa")
    _require_positive(temperature_k, "temperature_k")
    _require_positive(b_parameter, "b_parameter")

    return b_parameter * pressure_pa / (UNIVERSAL_GAS_CONSTANT * temperature_k)


def calculate_peng_robinson_parameters(
    temperature_k: float,
    pressure_pa: float,
    critical_temperature_k: float,
    critical_pressure_pa: float,
    acentric_factor: float,
) -> PengRobinsonParameters:
    """Calculate all pure-component Peng–Robinson parameters."""

    reduced_temperature = calculate_reduced_temperature(
        temperature_k,
        critical_temperature_k,
    )
    kappa = calculate_kappa(acentric_factor)
    alpha = calculate_alpha(
        temperature_k,
        critical_temperature_k,
        acentric_factor,
    )
    a_parameter = calculate_a_parameter(
        critical_temperature_k,
        critical_pressure_pa,
    )
    b_parameter = calculate_b_parameter(
        critical_temperature_k,
        critical_pressure_pa,
    )
    dimensionless_a = calculate_A_parameter(
        pressure_pa,
        temperature_k,
        a_parameter,
        alpha,
    )
    dimensionless_b = calculate_B_parameter(
        pressure_pa,
        temperature_k,
        b_parameter,
    )

    return PengRobinsonParameters(
        reduced_temperature=reduced_temperature,
        kappa=kappa,
        alpha=alpha,
        a=a_parameter,
        b=b_parameter,
        A=dimensionless_a,
        B=dimensionless_b,
    )


def calculate_cubic_coefficients(
    A: float,
    B: float,
) -> PengRobinsonCubicCoefficients:
    """Calculate coefficients of the Peng–Robinson cubic in Z."""

    _require_non_negative(A, "A")
    _require_non_negative(B, "B")
    if B >= 1.0:
        raise ValueError("B must be less than 1.")

    return PengRobinsonCubicCoefficients(
        z3=1.0,
        z2=B - 1.0,
        z1=A - 3.0 * B**2 - 2.0 * B,
        z0=-(A * B - B**2 - B**3),
    )


def _deduplicate_sorted_roots(roots: list[float]) -> tuple[float, ...]:
    """Remove numerically duplicated roots without rounding."""

    unique_roots: list[float] = []
    for root in roots:
        if not unique_roots or not isclose(
            root,
            unique_roots[-1],
            rel_tol=1e-9,
            abs_tol=1e-12,
        ):
            unique_roots.append(root)

    return tuple(unique_roots)


def solve_compressibility_roots(
    coefficients: PengRobinsonCubicCoefficients,
    imaginary_tolerance: float = 1e-10,
) -> tuple[float, ...]:
    """Solve the cubic and return sorted, unique real roots."""

    _require_positive(imaginary_tolerance, "imaginary_tolerance")

    calculated_roots = np.roots(
        (
            coefficients.z3,
            coefficients.z2,
            coefficients.z1,
            coefficients.z0,
        )
    )
    real_roots = sorted(
        float(root.real)
        for root in calculated_roots
        if abs(float(root.imag)) <= imaginary_tolerance
    )

    return _deduplicate_sorted_roots(real_roots)


def filter_physical_compressibility_roots(
    roots: tuple[float, ...],
    B: float,
    tolerance: float = 1e-10,
) -> tuple[float, ...]:
    """Return roots satisfying the Peng–Robinson condition Z > B."""

    _require_non_negative(B, "B")
    _require_positive(tolerance, "tolerance")

    physical_roots = tuple(root for root in roots if root > B + tolerance)
    if not physical_roots:
        raise ValueError("No physical compressibility roots satisfy Z > B.")

    return physical_roots


def calculate_compressibility_roots(
    A: float,
    B: float,
) -> tuple[float, ...]:
    """Calculate physically usable Peng–Robinson compressibility roots."""

    coefficients = calculate_cubic_coefficients(A, B)
    all_real_roots = solve_compressibility_roots(coefficients)

    return filter_physical_compressibility_roots(all_real_roots, B)
