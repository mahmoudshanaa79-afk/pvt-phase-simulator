"""Peng–Robinson equation-of-state calculations."""

from dataclasses import dataclass
from math import sqrt

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
