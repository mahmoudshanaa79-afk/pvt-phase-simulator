"""Peng–Robinson equation-of-state calculations."""

from dataclasses import dataclass
from enum import StrEnum
from math import exp, fsum, log1p, sqrt, ulp
from sys import float_info
from typing import Final

import numpy as np

from pvt_phase_simulator._validation import (
    require_finite as _require_finite,
)
from pvt_phase_simulator._validation import (
    require_non_negative as _require_non_negative,
)
from pvt_phase_simulator._validation import (
    require_positive as _require_positive,
)
from pvt_phase_simulator.physical_constants import UNIVERSAL_GAS_CONSTANT

# Conventional rounded Peng–Robinson constants are retained for compatibility
# with the project's existing textbook-style numerical references. Exact PR
# critical constraints instead give Omega_a = 0.4572355289213822 and
# Omega_b = 0.07779607390388846; therefore the rounded constants do not produce
# an exact triple root at a component's nominal Tc and Pc.
PENG_ROBINSON_OMEGA_A: Final = 0.45724
PENG_ROBINSON_OMEGA_B: Final = 0.07780

# Floating-point polynomial evaluation and derivative cancellation allowances.
# Both are multipliers on local float64 error scales, not absolute tolerances.
CUBIC_BACKWARD_ERROR_FACTOR: Final = 64.0
ROOT_DEDUPLICATION_ULP_FACTOR: Final = 128.0
MECHANICAL_DERIVATIVE_ERROR_FACTOR: Final = 64.0

# User-supplied roots may be rounded more coarsely than NumPy solver output.
# Residual and distance checks are both required; the distance check prevents
# small residuals near repeated roots from accepting unrelated values.
SUPPLIED_ROOT_RESIDUAL_RELATIVE_TOLERANCE: Final = 1e-10
SUPPLIED_ROOT_DISTANCE_RELATIVE_TOLERANCE: Final = 1e-9

# Below this offset, forming Z - 1 loses progressively more significant digits.
# The transformed cubic is algebraically identical and resolves that offset
# directly. At the switch, the subtraction error is at most about 2e-12
# relative in float64, so the two branches meet to far better than EOS accuracy.
LOW_PRESSURE_ROOT_OFFSET_THRESHOLD: Final = 1e-4


@dataclass(frozen=True, slots=True)
class PengRobinsonParameters:
    """Immutable pure-component Peng–Robinson parameters.

    ``a`` is in Pa·m⁶/mol², ``b`` is in m³/mol, and all other fields are
    dimensionless. The factory rejects non-finite or out-of-domain inputs.
    """

    reduced_temperature: float
    kappa: float
    alpha: float
    a: float
    b: float
    A: float
    B: float


@dataclass(frozen=True, slots=True)
class PengRobinsonCubicCoefficients:
    """Immutable dimensionless coefficients of the PR cubic in Z."""

    z3: float
    z2: float
    z1: float
    z0: float


@dataclass(frozen=True, slots=True)
class FugacityRootResult:
    """Immutable pure-fluid fugacity data at one validated root.

    ``compressibility_factor``, ``ln(phi)``, and ``phi`` are dimensionless;
    ``fugacity_pa`` is in Pa. This record alone does not imply stability.
    """

    compressibility_factor: float
    log_fugacity_coefficient: float
    fugacity_coefficient: float
    fugacity_pa: float


@dataclass(frozen=True, slots=True)
class StableRootResult:
    """Immutable pure-fluid lowest-fugacity result and evaluated candidates.

    This pure-fluid result must not be interpreted as multicomponent global
    phase stability.
    """

    stable: FugacityRootResult
    candidates: tuple[FugacityRootResult, ...]
    is_near_phase_equilibrium: bool


class MechanicalStabilityClassification(StrEnum):
    """Local fixed-temperature mechanical classification for one Z root."""

    STABLE = "stable"
    UNSTABLE = "unstable"
    MARGINAL = "marginal"


@dataclass(frozen=True, slots=True)
class MechanicalStabilityResult:
    """Immutable local mechanical derivative diagnostic at dimensionless Z.

    ``derivative`` and its float64 cancellation tolerance are dimensionless
    sign indicators, not a dimensional pressure derivative.
    """

    compressibility_factor: float
    derivative: float
    derivative_tolerance: float
    classification: MechanicalStabilityClassification


def calculate_kappa(acentric_factor: float) -> float:
    """Calculate the Peng–Robinson kappa parameter."""

    _require_finite(acentric_factor, "acentric_factor")
    try:
        kappa = 0.37464 + 1.54226 * acentric_factor - 0.26992 * acentric_factor**2
    except OverflowError as error:
        raise ValueError("kappa calculation must remain finite.") from error
    _require_finite(kappa, "kappa")
    return kappa


def calculate_reduced_temperature(
    temperature_k: float,
    critical_temperature_k: float,
) -> float:
    """Calculate reduced temperature."""

    _require_positive(temperature_k, "temperature_k")
    _require_positive(critical_temperature_k, "critical_temperature_k")

    reduced_temperature = temperature_k / critical_temperature_k
    _require_finite(reduced_temperature, "reduced_temperature")
    return reduced_temperature


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

    try:
        alpha = (1.0 + kappa * (1.0 - sqrt(reduced_temperature))) ** 2
    except OverflowError as error:
        raise ValueError("alpha calculation must remain finite.") from error
    _require_finite(alpha, "alpha")
    return alpha


def calculate_a_parameter(
    critical_temperature_k: float,
    critical_pressure_pa: float,
) -> float:
    """Calculate the Peng–Robinson a parameter in Pa m^6 / mol^2."""

    _require_positive(critical_temperature_k, "critical_temperature_k")
    _require_positive(critical_pressure_pa, "critical_pressure_pa")

    try:
        a_parameter = (
            PENG_ROBINSON_OMEGA_A
            * UNIVERSAL_GAS_CONSTANT**2
            * critical_temperature_k**2
            / critical_pressure_pa
        )
    except OverflowError as error:
        raise ValueError("a_parameter calculation must remain finite.") from error
    _require_positive(a_parameter, "a_parameter")
    return a_parameter


def calculate_b_parameter(
    critical_temperature_k: float,
    critical_pressure_pa: float,
) -> float:
    """Calculate the Peng–Robinson b parameter in m^3 / mol."""

    _require_positive(critical_temperature_k, "critical_temperature_k")
    _require_positive(critical_pressure_pa, "critical_pressure_pa")

    b_parameter = (
        PENG_ROBINSON_OMEGA_B
        * UNIVERSAL_GAS_CONSTANT
        * critical_temperature_k
        / critical_pressure_pa
    )
    _require_positive(b_parameter, "b_parameter")
    return b_parameter


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

    try:
        dimensionless_a = (
            a_parameter
            * alpha
            * pressure_pa
            / (UNIVERSAL_GAS_CONSTANT**2 * temperature_k**2)
        )
    except (OverflowError, ZeroDivisionError) as error:
        raise ValueError("A calculation must remain finite.") from error
    _require_non_negative(dimensionless_a, "A")
    return dimensionless_a


def calculate_B_parameter(
    pressure_pa: float,
    temperature_k: float,
    b_parameter: float,
) -> float:
    """Calculate the dimensionless Peng–Robinson B parameter."""

    _require_non_negative(pressure_pa, "pressure_pa")
    _require_positive(temperature_k, "temperature_k")
    _require_positive(b_parameter, "b_parameter")

    dimensionless_b = (
        b_parameter * pressure_pa / (UNIVERSAL_GAS_CONSTANT * temperature_k)
    )
    _require_non_negative(dimensionless_b, "B")
    return dimensionless_b


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

    try:
        coefficients = PengRobinsonCubicCoefficients(
            z3=1.0,
            z2=B - 1.0,
            z1=A - 3.0 * B**2 - 2.0 * B,
            z0=-(A * B - B**2 - B**3),
        )
    except OverflowError as error:
        raise ValueError("Cubic coefficients must remain finite.") from error

    for name, value in (
        ("z3", coefficients.z3),
        ("z2", coefficients.z2),
        ("z1", coefficients.z1),
        ("z0", coefficients.z0),
    ):
        _require_finite(value, name)
    return coefficients


def calculate_cubic_residual(
    compressibility_factor: float,
    coefficients: PengRobinsonCubicCoefficients,
) -> float:
    """Evaluate the Peng–Robinson cubic polynomial at a supplied Z value."""

    _require_finite(compressibility_factor, "compressibility_factor")
    for name, value in (
        ("z3", coefficients.z3),
        ("z2", coefficients.z2),
        ("z1", coefficients.z1),
        ("z0", coefficients.z0),
    ):
        _require_finite(value, name)

    try:
        residual = (
            (coefficients.z3 * compressibility_factor + coefficients.z2)
            * compressibility_factor
            + coefficients.z1
        ) * compressibility_factor + coefficients.z0
    except OverflowError as error:
        raise ValueError("Cubic residual must remain finite.") from error
    _require_finite(residual, "cubic residual")
    return residual


def calculate_cubic_discriminant(
    coefficients: PengRobinsonCubicCoefficients,
) -> float:
    """Return the cubic discriminant as a root-conditioning diagnostic."""

    for name, value in (
        ("z3", coefficients.z3),
        ("z2", coefficients.z2),
        ("z1", coefficients.z1),
        ("z0", coefficients.z0),
    ):
        _require_finite(value, name)
    a, b, c, d = (
        coefficients.z3,
        coefficients.z2,
        coefficients.z1,
        coefficients.z0,
    )
    try:
        discriminant = (
            18.0 * a * b * c * d
            - 4.0 * b**3 * d
            + b**2 * c**2
            - 4.0 * a * c**3
            - 27.0 * a**2 * d**2
        )
    except OverflowError as error:
        raise ValueError("cubic discriminant must remain finite.") from error
    _require_finite(discriminant, "cubic discriminant")
    return discriminant


def _cubic_evaluation_scale(
    compressibility_factor: float,
    coefficients: PengRobinsonCubicCoefficients,
) -> float:
    """Return the absolute-term scale for Horner-polynomial error analysis."""

    z = compressibility_factor
    try:
        scale = (
            abs(coefficients.z3 * z**3)
            + abs(coefficients.z2 * z**2)
            + abs(coefficients.z1 * z)
            + abs(coefficients.z0)
        )
    except OverflowError as error:
        raise ValueError("cubic evaluation scale must remain finite.") from error
    _require_finite(scale, "cubic evaluation scale")
    return scale


def _cubic_residual_tolerance(
    compressibility_factor: float,
    coefficients: PengRobinsonCubicCoefficients,
) -> float:
    """Return a float64 backward-error bound for cubic evaluation."""

    scale = _cubic_evaluation_scale(compressibility_factor, coefficients)
    tolerance = CUBIC_BACKWARD_ERROR_FACTOR * max(
        ulp(scale),
        float_info.epsilon * scale,
    )
    _require_positive(tolerance, "cubic residual tolerance")
    return tolerance


def _root_uncertainty_tolerance(
    root: float,
    coefficients: PengRobinsonCubicCoefficients,
) -> float:
    """Estimate resolvable root distance from local cubic conditioning."""

    residual_bound = _cubic_residual_tolerance(root, coefficients)
    first_derivative = abs(
        3.0 * coefficients.z3 * root**2 + 2.0 * coefficients.z2 * root + coefficients.z1
    )
    second_derivative = abs(6.0 * coefficients.z3 * root + 2.0 * coefficients.z2)
    candidate_distances: list[float] = []
    if first_derivative > 0.0:
        candidate_distances.append(residual_bound / first_derivative)
    if second_derivative > 0.0:
        candidate_distances.append(sqrt(2.0 * residual_bound / second_derivative))
    if coefficients.z3 != 0.0:
        candidate_distances.append(
            (residual_bound / abs(coefficients.z3)) ** (1.0 / 3.0)
        )
    if not candidate_distances:
        raise ValueError("cubic root conditioning could not be evaluated.")

    uncertainty = max(
        ROOT_DEDUPLICATION_ULP_FACTOR * ulp(root),
        min(candidate_distances),
    )
    _require_positive(uncertainty, "root uncertainty tolerance")
    return uncertainty


def _deduplicate_sorted_roots(
    roots: list[float],
    coefficients: PengRobinsonCubicCoefficients,
) -> tuple[float, ...]:
    """Merge only roots unresolved at the cubic's float64 conditioning scale."""

    if not roots:
        return ()

    clusters: list[list[float]] = [[roots[0]]]
    for root in roots[1:]:
        previous = clusters[-1][-1]
        separation_tolerance = _root_uncertainty_tolerance(
            previous, coefficients
        ) + _root_uncertainty_tolerance(root, coefficients)
        if root - previous <= separation_tolerance:
            clusters[-1].append(root)
        else:
            clusters.append([root])

    representatives: list[float] = []
    for cluster in clusters:
        centroid = fsum(cluster) / len(cluster)
        if abs(calculate_cubic_residual(centroid, coefficients)) <= (
            _cubic_residual_tolerance(centroid, coefficients)
        ):
            representatives.append(centroid)
        else:
            representatives.append(
                min(
                    cluster,
                    key=lambda root: abs(calculate_cubic_residual(root, coefficients)),
                )
            )
    return tuple(representatives)


def _is_numerically_real_root(
    real_part: float,
    imaginary_part: float,
    coefficients: PengRobinsonCubicCoefficients,
    imaginary_tolerance: float,
) -> bool:
    """Return whether a complex root has a defensible real projection."""

    residual = abs(calculate_cubic_residual(real_part, coefficients))
    residual_tolerance = _cubic_residual_tolerance(real_part, coefficients)
    imaginary_limit = max(
        imaginary_tolerance * max(1.0, abs(real_part)),
        _root_uncertainty_tolerance(real_part, coefficients),
    )
    return abs(imaginary_part) <= imaginary_limit and residual <= residual_tolerance


def solve_compressibility_roots(
    coefficients: PengRobinsonCubicCoefficients,
    imaginary_tolerance: float = 1e-10,
) -> tuple[float, ...]:
    """Return sorted real roots verified by scale-aware residual checks.

    ``imaginary_tolerance`` is relative to ``max(1, abs(real_part))``. Near a
    repeated root, the local coefficient-conditioning estimate may permit a
    larger projection only when the projected real root also satisfies the
    cubic backward-error bound.
    """

    _require_positive(imaginary_tolerance, "imaginary_tolerance")

    for name, value in (
        ("z3", coefficients.z3),
        ("z2", coefficients.z2),
        ("z1", coefficients.z1),
        ("z0", coefficients.z0),
    ):
        _require_finite(value, name)

    calculated_roots = np.roots(
        (
            coefficients.z3,
            coefficients.z2,
            coefficients.z1,
            coefficients.z0,
        )
    )
    real_roots: list[float] = []
    for root in calculated_roots:
        real_part = float(root.real)
        imaginary_part = float(root.imag)
        _require_finite(real_part, "compressibility root real part")
        _require_finite(imaginary_part, "compressibility root imaginary part")
        if _is_numerically_real_root(
            real_part,
            imaginary_part,
            coefficients,
            imaginary_tolerance,
        ):
            real_roots.append(real_part)
    real_roots.sort()

    return _deduplicate_sorted_roots(real_roots, coefficients)


def filter_physical_compressibility_roots(
    roots: tuple[float, ...],
    B: float,
    tolerance: float = 1e-10,
) -> tuple[float, ...]:
    """Return roots satisfying the Peng–Robinson condition Z > B."""

    _require_non_negative(B, "B")
    _require_positive(tolerance, "tolerance")

    for root in roots:
        _require_finite(root, "compressibility root")

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


def validate_compressibility_root(
    compressibility_factor: float,
    A: float,
    B: float,
) -> None:
    """Validate a supplied Z as an admissible real PR cubic root.

    This low-level contract validates the cubic and ``Z > B`` domain but does
    not require mechanical or global thermodynamic stability.
    """

    _require_finite(compressibility_factor, "compressibility_factor")
    _require_non_negative(A, "A")
    _require_non_negative(B, "B")
    if compressibility_factor <= B:
        raise ValueError(
            "compressibility_factor must be greater than B for the logarithm argument."
        )

    coefficients = calculate_cubic_coefficients(A, B)
    residual = abs(calculate_cubic_residual(compressibility_factor, coefficients))
    residual_scale = max(
        1.0,
        _cubic_evaluation_scale(compressibility_factor, coefficients),
    )
    if residual > SUPPLIED_ROOT_RESIDUAL_RELATIVE_TOLERANCE * residual_scale:
        raise ValueError(
            "compressibility_factor does not satisfy the Peng-Robinson cubic "
            "within the documented residual tolerance."
        )

    admissible_roots = tuple(
        root for root in solve_compressibility_roots(coefficients) if root > B
    )
    is_near_root = any(
        abs(compressibility_factor - root)
        <= max(
            SUPPLIED_ROOT_DISTANCE_RELATIVE_TOLERANCE
            * max(1.0, abs(compressibility_factor), abs(root)),
            _root_uncertainty_tolerance(root, coefficients),
        )
        for root in admissible_roots
    )
    if not is_near_root:
        raise ValueError(
            "compressibility_factor is not within the documented distance "
            "tolerance of an admissible Peng-Robinson cubic root."
        )


def calculate_compressibility_root_offset(
    compressibility_factor: float,
    A: float,
    B: float,
) -> float:
    """Return ``Z - 1``, resolving small offsets with a transformed cubic.

    The supplied ``Z`` is validated first. For ``|Z - 1| < 1e-4``, Newton
    refinement is applied to the PR cubic written directly in ``w = Z - 1``::

        w^3 + (B + 2)w^2 + (1 + A - 3B^2)w
        + A - B - 2B^2 - AB + B^3 = 0

    This is a conditioning refinement of the already selected root, not a
    phase/root-selection operation. Exact zero pressure returns exact zero.
    """

    validate_compressibility_root(compressibility_factor, A, B)
    if A == 0.0 and B == 0.0:
        return 0.0

    direct_offset = compressibility_factor - 1.0
    if abs(direct_offset) >= LOW_PRESSURE_ROOT_OFFSET_THRESHOLD:
        return direct_offset

    quadratic_coefficient = B + 2.0
    linear_coefficient = 1.0 + A - 3.0 * B * B
    constant_coefficient = A - B - 2.0 * B * B - A * B + B**3
    root_offset = -constant_coefficient / linear_coefficient
    for _ in range(4):
        residual = (
            (root_offset + quadratic_coefficient) * root_offset + linear_coefficient
        ) * root_offset + constant_coefficient
        derivative = (
            3.0 * root_offset * root_offset
            + 2.0 * quadratic_coefficient * root_offset
            + linear_coefficient
        )
        _require_finite(residual, "transformed cubic residual")
        _require_finite(derivative, "transformed cubic derivative")
        if derivative == 0.0:
            raise ValueError("transformed cubic derivative must not equal zero.")
        root_offset -= residual / derivative
    _require_finite(root_offset, "compressibility root offset")
    return root_offset


def _dimensionless_pressure_derivative_terms(
    compressibility_factor: float,
    A: float,
    B: float,
) -> tuple[float, float]:
    """Return repulsive and attractive terms of the reduced P-V derivative."""

    _require_positive(compressibility_factor, "compressibility_factor")
    _require_non_negative(A, "A")
    _require_non_negative(B, "B")
    _require_positive(
        compressibility_factor - B,
        "compressibility_factor - B",
    )

    try:
        attraction_denominator = (
            compressibility_factor**2 + 2.0 * B * compressibility_factor - B**2
        )
    except (OverflowError, ZeroDivisionError) as error:
        raise ValueError("Pressure derivative must remain finite.") from error
    _require_positive(
        attraction_denominator,
        "pressure derivative denominator",
    )

    try:
        repulsive_term = -1.0 / (compressibility_factor - B) ** 2
        attractive_term = (
            2.0 * A * (compressibility_factor + B) / attraction_denominator**2
        )
    except (OverflowError, ZeroDivisionError) as error:
        raise ValueError("Pressure derivative must remain finite.") from error
    _require_finite(repulsive_term, "pressure derivative repulsive term")
    _require_finite(attractive_term, "pressure derivative attractive term")
    return repulsive_term, attractive_term


def _dimensionless_pressure_derivative(
    compressibility_factor: float,
    A: float,
    B: float,
) -> float:
    """Calculate a quantity with the sign of (dP/dV) at fixed temperature."""

    repulsive_term, attractive_term = _dimensionless_pressure_derivative_terms(
        compressibility_factor,
        A,
        B,
    )
    derivative = repulsive_term + attractive_term
    _require_finite(derivative, "pressure derivative")
    return derivative


def classify_mechanical_stability(
    compressibility_factor: float,
    A: float,
    B: float,
) -> MechanicalStabilityResult:
    """Classify local mechanical stability without resolving global stability.

    The tolerance is 64 times the local float64 rounding scale of the two
    derivative terms. Values within the cancellation band are marginal rather
    than being assigned a confident sign.
    """

    repulsive_term, attractive_term = _dimensionless_pressure_derivative_terms(
        compressibility_factor,
        A,
        B,
    )
    derivative = repulsive_term + attractive_term
    derivative_scale = abs(repulsive_term) + abs(attractive_term)
    derivative_tolerance = MECHANICAL_DERIVATIVE_ERROR_FACTOR * max(
        ulp(derivative_scale),
        float_info.epsilon * derivative_scale,
    )
    _require_finite(derivative, "pressure derivative")
    _require_positive(derivative_tolerance, "pressure derivative tolerance")

    if derivative < -derivative_tolerance:
        classification = MechanicalStabilityClassification.STABLE
    elif derivative > derivative_tolerance:
        classification = MechanicalStabilityClassification.UNSTABLE
    else:
        classification = MechanicalStabilityClassification.MARGINAL
    return MechanicalStabilityResult(
        compressibility_factor=compressibility_factor,
        derivative=derivative,
        derivative_tolerance=derivative_tolerance,
        classification=classification,
    )


def filter_mechanically_stable_compressibility_roots(
    roots: tuple[float, ...],
    A: float,
    B: float,
) -> tuple[float, ...]:
    """Return confidently stable roots; marginal roots are not retained."""

    if not roots:
        raise ValueError("roots must not be empty.")

    stable_roots = tuple(
        root
        for root in roots
        if classify_mechanical_stability(root, A, B).classification
        is MechanicalStabilityClassification.STABLE
    )
    if not stable_roots:
        raise ValueError("No mechanically stable compressibility roots remain.")

    return stable_roots


def calculate_log_fugacity_coefficient(
    compressibility_factor: float,
    A: float,
    B: float,
) -> float:
    """Return dimensionless pure-component ``ln(phi)`` at a genuine PR root.

    The root may be locally stable, unstable, or marginal. Invalid domains,
    inconsistent zero-pressure parameters, and non-finite results raise
    ``ValueError``.
    """

    _require_positive(compressibility_factor, "compressibility_factor")
    _require_non_negative(A, "A")
    _require_non_negative(B, "B")
    if B == 0.0 and A > 0.0:
        raise ValueError("B must be greater than zero when A is positive.")
    validate_compressibility_root(compressibility_factor, A, B)

    if A == 0.0 and B == 0.0:
        return 0.0

    root_offset = calculate_compressibility_root_offset(
        compressibility_factor,
        A,
        B,
    )
    sqrt_two = sqrt(2.0)
    z_minus_b_offset = root_offset - B
    _require_positive(1.0 + z_minus_b_offset, "Z - B logarithm argument")
    numerator_offset = root_offset + (1.0 + sqrt_two) * B
    denominator_offset = root_offset + (1.0 - sqrt_two) * B
    _require_positive(1.0 + numerator_offset, "fugacity logarithm numerator")
    _require_positive(1.0 + denominator_offset, "fugacity logarithm denominator")
    logarithm_ratio = log1p(numerator_offset) - log1p(denominator_offset)

    try:
        log_fugacity_coefficient = (
            root_offset
            - log1p(z_minus_b_offset)
            - A / (2.0 * sqrt_two * B) * logarithm_ratio
        )
    except OverflowError as error:
        raise ValueError("log fugacity coefficient must remain finite.") from error
    _require_finite(log_fugacity_coefficient, "log fugacity coefficient")
    return log_fugacity_coefficient


def _exponentiate_fugacity_coefficient(log_fugacity_coefficient: float) -> float:
    """Exponentiate a validated ln(phi) with overflow/underflow checks."""

    _require_finite(log_fugacity_coefficient, "log fugacity coefficient")
    try:
        fugacity_coefficient = exp(log_fugacity_coefficient)
    except OverflowError as error:
        raise ValueError("fugacity coefficient must remain finite.") from error
    _require_positive(fugacity_coefficient, "fugacity coefficient")
    return fugacity_coefficient


def calculate_fugacity_coefficient(
    compressibility_factor: float,
    A: float,
    B: float,
) -> float:
    """Calculate the pure-component fugacity coefficient at a genuine root."""

    log_fugacity_coefficient = calculate_log_fugacity_coefficient(
        compressibility_factor,
        A,
        B,
    )
    return _exponentiate_fugacity_coefficient(log_fugacity_coefficient)


def calculate_fugacity_pa(
    pressure_pa: float,
    fugacity_coefficient: float,
) -> float:
    """Calculate fugacity in pascals."""

    _require_non_negative(pressure_pa, "pressure_pa")
    _require_positive(fugacity_coefficient, "fugacity_coefficient")

    fugacity_pa = fugacity_coefficient * pressure_pa
    _require_non_negative(fugacity_pa, "fugacity_pa")
    return fugacity_pa


def evaluate_fugacity_roots(
    roots: tuple[float, ...],
    A: float,
    B: float,
    pressure_pa: float,
) -> tuple[FugacityRootResult, ...]:
    """Evaluate pure-fluid fugacity at every supplied genuine physical root.

    Results are ordered by dimensionless Z and fugacity is returned in Pa.
    No mechanical filtering or stable-root selection occurs here.
    """

    if not roots:
        raise ValueError("roots must not be empty.")

    results: list[FugacityRootResult] = []
    for root in sorted(roots):
        log_fugacity_coefficient = calculate_log_fugacity_coefficient(root, A, B)
        fugacity_coefficient = calculate_fugacity_coefficient(root, A, B)
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

    for candidate in candidates:
        _require_positive(
            candidate.compressibility_factor,
            "candidate compressibility_factor",
        )
        _require_finite(
            candidate.log_fugacity_coefficient,
            "candidate log_fugacity_coefficient",
        )
        _require_positive(
            candidate.fugacity_coefficient,
            "candidate fugacity_coefficient",
        )
        _require_non_negative(candidate.fugacity_pa, "candidate fugacity_pa")

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
    """Return the pure-fluid lowest-fugacity mechanically eligible candidate.

    This high-level pure-fluid operation is not a mixture phase-stability or
    flash calculation. ``pressure_pa`` is in Pa; invalid values raise
    ``ValueError`` through the delegated validation contracts.
    """

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
