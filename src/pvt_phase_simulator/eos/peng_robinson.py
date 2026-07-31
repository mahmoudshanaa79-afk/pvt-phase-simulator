"""Peng–Robinson equation-of-state calculations."""

from dataclasses import dataclass
from math import exp, isclose, log, sqrt

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


@dataclass(frozen=True, slots=True)
class FugacityRootResult:
    """Fugacity properties evaluated at one compressibility root."""

    compressibility_factor: float
    log_fugacity_coefficient: float
    fugacity_coefficient: float
    fugacity_pa: float


@dataclass(frozen=True, slots=True)
class StableRootResult:
    """Stable fugacity candidate and all evaluated candidates."""

    stable: FugacityRootResult
    candidates: tuple[FugacityRootResult, ...]
    is_near_phase_equilibrium: bool


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
    """Calculate the Peng–Robinson a parameter in Pa m^6 / mol^2."""

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
    """Calculate the Peng–Robinson b parameter in m^3 / mol."""

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


def _dimensionless_pressure_derivative(
    compressibility_factor: float,
    A: float,
    B: float,
) -> float:
    """Calculate a quantity with the sign of (dP/dV) at fixed temperature."""

    _require_positive(compressibility_factor, "compressibility_factor")
    _require_non_negative(A, "A")
    _require_non_negative(B, "B")
    _require_positive(
        compressibility_factor - B,
        "compressibility_factor - B",
    )

    attraction_denominator = (
        compressibility_factor**2 + 2.0 * B * compressibility_factor - B**2
    )
    _require_positive(
        attraction_denominator,
        "pressure derivative denominator",
    )

    return (
        -1.0 / (compressibility_factor - B) ** 2
        + 2.0 * A * (compressibility_factor + B) / attraction_denominator**2
    )


def filter_mechanically_stable_compressibility_roots(
    roots: tuple[float, ...],
    A: float,
    B: float,
) -> tuple[float, ...]:
    """Return roots satisfying the strict mechanical-stability condition."""

    if not roots:
        raise ValueError("roots must not be empty.")

    stable_roots = tuple(
        root for root in roots if _dimensionless_pressure_derivative(root, A, B) < 0.0
    )
    if not stable_roots:
        raise ValueError("No mechanically stable compressibility roots remain.")

    return stable_roots


def calculate_log_fugacity_coefficient(
    compressibility_factor: float,
    A: float,
    B: float,
) -> float:
    """Calculate the pure-component Peng–Robinson ln(phi)."""

    _require_positive(compressibility_factor, "compressibility_factor")
    _require_non_negative(A, "A")
    _require_non_negative(B, "B")

    z_minus_b = compressibility_factor - B
    _require_positive(z_minus_b, "Z - B logarithm argument")

    if A == 0.0 and B == 0.0:
        return 0.0
    if B == 0.0:
        raise ValueError("B must be greater than zero when A is positive.")

    sqrt_two = sqrt(2.0)
    numerator = compressibility_factor + (1.0 + sqrt_two) * B
    denominator = compressibility_factor + (1.0 - sqrt_two) * B
    _require_positive(numerator, "fugacity logarithm numerator")
    _require_positive(denominator, "fugacity logarithm denominator")
    logarithm_argument = numerator / denominator
    _require_positive(logarithm_argument, "fugacity logarithm argument")

    return (
        compressibility_factor
        - 1.0
        - log(z_minus_b)
        - A / (2.0 * sqrt_two * B) * log(logarithm_argument)
    )


def calculate_fugacity_coefficient(
    compressibility_factor: float,
    A: float,
    B: float,
) -> float:
    """Calculate the pure-component fugacity coefficient."""

    log_fugacity_coefficient = calculate_log_fugacity_coefficient(
        compressibility_factor,
        A,
        B,
    )

    return exp(log_fugacity_coefficient)


def calculate_fugacity_pa(
    pressure_pa: float,
    fugacity_coefficient: float,
) -> float:
    """Calculate fugacity in pascals."""

    _require_non_negative(pressure_pa, "pressure_pa")
    _require_positive(fugacity_coefficient, "fugacity_coefficient")

    return fugacity_coefficient * pressure_pa


def evaluate_fugacity_roots(
    roots: tuple[float, ...],
    A: float,
    B: float,
    pressure_pa: float,
) -> tuple[FugacityRootResult, ...]:
    """Evaluate fugacity properties for every physical root."""

    if not roots:
        raise ValueError("roots must not be empty.")

    results: list[FugacityRootResult] = []
    for root in sorted(roots):
        log_fugacity_coefficient = calculate_log_fugacity_coefficient(root, A, B)
        fugacity_coefficient = exp(log_fugacity_coefficient)
        fugacity_pa = calculate_fugacity_pa(pressure_pa, fugacity_coefficient)
        results.append(
            FugacityRootResult(
                compressibility_factor=root,
                log_fugacity_coefficient=log_fugacity_coefficient,
                fugacity_coefficient=fugacity_coefficient,
                fugacity_pa=fugacity_pa,
            )
        )

    return tuple(results)


def _outer_stable_branch_candidates(
    candidates: tuple[FugacityRootResult, ...],
) -> tuple[FugacityRootResult, ...]:
    """Exclude mechanically unstable interior cubic-root candidates."""

    if len(candidates) <= 2:
        return candidates

    by_compressibility = sorted(
        candidates,
        key=lambda candidate: candidate.compressibility_factor,
    )
    return (by_compressibility[0], by_compressibility[-1])


def select_stable_root(
    candidates: tuple[FugacityRootResult, ...],
    equilibrium_tolerance: float = 1e-8,
) -> StableRootResult:
    """Select the lowest-ln(phi) outer mechanically stable branch."""

    if not candidates:
        raise ValueError("candidates must not be empty.")
    _require_positive(equilibrium_tolerance, "equilibrium_tolerance")

    if len(candidates) == 1:
        return StableRootResult(
            stable=candidates[0],
            candidates=candidates,
            is_near_phase_equilibrium=False,
        )

    stable_branch_candidates = _outer_stable_branch_candidates(candidates)
    by_fugacity = sorted(
        stable_branch_candidates,
        key=lambda candidate: (
            candidate.log_fugacity_coefficient,
            candidate.compressibility_factor,
        ),
    )
    lowest_log_fugacity = by_fugacity[0].log_fugacity_coefficient
    second_lowest_log_fugacity = by_fugacity[1].log_fugacity_coefficient
    is_near_phase_equilibrium = (
        second_lowest_log_fugacity - lowest_log_fugacity <= equilibrium_tolerance
    )

    stable = by_fugacity[0]
    if is_near_phase_equilibrium:
        near_equal_candidates = tuple(
            candidate
            for candidate in by_fugacity
            if candidate.log_fugacity_coefficient - lowest_log_fugacity
            <= equilibrium_tolerance
        )
        stable = min(
            near_equal_candidates,
            key=lambda candidate: candidate.compressibility_factor,
        )

    return StableRootResult(
        stable=stable,
        candidates=candidates,
        is_near_phase_equilibrium=is_near_phase_equilibrium,
    )


def calculate_stable_compressibility_result(
    A: float,
    B: float,
    pressure_pa: float,
    equilibrium_tolerance: float = 1e-8,
) -> StableRootResult:
    """Calculate roots, evaluate fugacity, and select the stable candidate."""

    roots = calculate_compressibility_roots(A, B)
    mechanically_stable_roots = filter_mechanically_stable_compressibility_roots(
        roots,
        A,
        B,
    )
    candidates = evaluate_fugacity_roots(
        mechanically_stable_roots,
        A,
        B,
        pressure_pa,
    )

    return select_stable_root(candidates, equilibrium_tolerance)
