"""Analytical Peng–Robinson derivatives on one fixed physical root.

Derivatives are valid locally on a fixed physical root and do not include root
switching or branch-selection discontinuities. This module supplies derivative
infrastructure only; existing equilibrium solvers do not call it.
"""

from dataclasses import dataclass
from math import fsum, isfinite, log1p, sqrt, ulp
from sys import float_info
from typing import Final

from pvt_phase_simulator._validation import (
    require_finite as _require_finite,
)
from pvt_phase_simulator._validation import (
    require_positive as _require_positive,
)
from pvt_phase_simulator.eos.mixing_rules import (
    BinaryInteractionMapping,
    PengRobinsonMixtureParameters,
    calculate_component_pair_attraction_parameter,
    calculate_mixture_a_alpha,
    calculate_mixture_A_parameter,
    calculate_mixture_b,
    calculate_mixture_B_parameter,
    canonicalize_binary_interactions,
    canonicalize_supplied_binary_interaction_pairs,
    resolve_binary_interaction_metadata,
    validate_component_parameter_provenance,
)
from pvt_phase_simulator.eos.mixture_fugacity import (
    calculate_component_attraction_sum,
    calculate_mixture_fugacity_coefficients,
)
from pvt_phase_simulator.eos.peng_robinson import (
    calculate_A_parameter,
    calculate_a_parameter,
    calculate_alpha,
    calculate_B_parameter,
    calculate_b_parameter,
    calculate_compressibility_root_offset,
    calculate_kappa,
    calculate_reduced_temperature,
    validate_compressibility_root,
)
from pvt_phase_simulator.fluid_models import Component

FIXED_ROOT_DERIVATIVE_ERROR_FACTOR: Final = 64.0
DERIVATIVE_RECONSTRUCTION_ERROR_FACTOR: Final = 32.0


@dataclass(frozen=True, slots=True)
class PureComponentTemperatureDerivatives:
    """Pure PR temperature derivatives at fixed component properties.

    ``alpha_temperature_derivative_per_k`` has units K⁻¹ and
    ``a_alpha_temperature_derivative`` has units Pa·m⁶·mol⁻²·K⁻¹. The
    dimensional PR ``a`` and ``b`` parameters are temperature independent.
    """

    component_name: str
    temperature_k: float
    reduced_temperature: float
    kappa: float
    alpha: float
    alpha_temperature_derivative_per_k: float
    a: float
    a_alpha: float
    a_alpha_temperature_derivative: float
    b: float


@dataclass(frozen=True, slots=True)
class PureDimensionlessParameterDerivatives:
    """Pure PR ``A`` and ``B`` derivatives at fixed component properties.

    Pressure derivatives hold temperature fixed and have units Pa⁻¹.
    Temperature derivatives hold pressure fixed and have units K⁻¹.
    Log-pressure derivatives are dimensionless and obey
    ``d/dln(P)=P*d/dP``.
    """

    component_name: str
    temperature_k: float
    pressure_pa: float
    A: float
    B: float
    A_pressure_derivative_per_pa: float
    B_pressure_derivative_per_pa: float
    A_log_pressure_derivative: float
    B_log_pressure_derivative: float
    A_temperature_derivative_per_k: float
    B_temperature_derivative_per_k: float


@dataclass(frozen=True, slots=True)
class MixtureParameterDerivatives:
    """Analytical mixture derivatives at fixed ``kij`` and component order.

    Composition columns use ``n-1`` simplex coordinates. For each independent
    component ``k``, ``u_k=x_k`` and
    ``x_reference=1-sum(u_k)``. Thus each stored composition derivative is the
    tangent derivative ``partial/partial x_k - partial/partial x_reference``.
    """

    component_names: tuple[str, ...]
    reference_component_index: int
    independent_component_indices: tuple[int, ...]
    pure_temperature_derivatives: tuple[PureComponentTemperatureDerivatives, ...]
    pair_attraction_parameters: tuple[tuple[float, ...], ...]
    pair_attraction_temperature_derivatives: tuple[tuple[float, ...], ...]
    component_attraction_sums: tuple[float, ...]
    component_attraction_sum_temperature_derivatives: tuple[float, ...]
    a_alpha_mix_temperature_derivative: float
    b_mix_temperature_derivative: float
    A_mix_pressure_derivative_per_pa: float
    B_mix_pressure_derivative_per_pa: float
    A_mix_log_pressure_derivative: float
    B_mix_log_pressure_derivative: float
    A_mix_temperature_derivative_per_k: float
    B_mix_temperature_derivative_per_k: float
    a_alpha_mix_composition_derivatives: tuple[float, ...]
    b_mix_composition_derivatives: tuple[float, ...]
    A_mix_composition_derivatives: tuple[float, ...]
    B_mix_composition_derivatives: tuple[float, ...]
    component_attraction_sum_composition_derivatives: tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class FixedRootCompressibilityDerivative:
    """One implicit derivative of ``Z`` along an already selected PR root.

    ``parameter_partial`` is the partial derivative of the cubic residual with
    respect to the named variable while holding ``Z`` fixed. ``derivative`` is
    dimensionless per ``derivative_units`` when applicable. A near-multiple
    root returns ``applicable=False`` rather than a misleading finite value.
    """

    derivative_variable: str
    derivative_units: str
    applicable: bool
    derivative: float | None
    cubic_partial_z: float
    parameter_partial: float
    singularity_tolerance: float
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class FixedRootMixtureFugacityDerivatives:
    """Fixed-root derivatives of ordered mixture ``ln(phi_i)`` values.

    Pressure derivatives are per Pa, log-pressure derivatives are
    dimensionless, temperature derivatives are per K, and composition columns
    use the explicit simplex coordinates in ``parameter_derivatives``.
    """

    component_names: tuple[str, ...]
    compressibility_factor: float
    log_fugacity_coefficients: tuple[float, ...]
    parameter_derivatives: MixtureParameterDerivatives
    pressure_root_derivative: FixedRootCompressibilityDerivative
    temperature_root_derivative: FixedRootCompressibilityDerivative
    composition_root_derivatives: tuple[FixedRootCompressibilityDerivative, ...]
    applicable: bool
    failure_reason: str | None
    log_fugacity_pressure_derivatives_per_pa: tuple[float, ...] | None
    log_fugacity_log_pressure_derivatives: tuple[float, ...] | None
    log_fugacity_temperature_derivatives_per_k: tuple[float, ...] | None
    log_fugacity_composition_derivatives: tuple[tuple[float, ...], ...] | None


def _require_consistent(actual: float, expected: float, name: str) -> None:
    _require_finite(actual, name)
    _require_finite(expected, f"expected {name}")
    if expected == 0.0:
        consistent = actual == 0.0
    else:
        tolerance = DERIVATIVE_RECONSTRUCTION_ERROR_FACTOR * max(
            ulp(expected), float_info.epsilon * abs(expected)
        )
        consistent = abs(actual - expected) <= tolerance
    if not consistent:
        raise ValueError(f"{name} is inconsistent with the mixture parameters.")


def calculate_pure_component_temperature_derivatives(
    component: Component,
    temperature_k: float,
) -> PureComponentTemperatureDerivatives:
    """Return analytical pure PR derivatives with respect to temperature.

    Critical properties and acentric factor are fixed. With
    ``m=1+kappa*(1-sqrt(T/Tc))`` and ``alpha=m²``, the derivative is
    ``dalpha/dT=-kappa*m/(Tc*sqrt(T/Tc))``. No finite difference is used.
    """

    _require_positive(temperature_k, "temperature_k")
    reduced_temperature = calculate_reduced_temperature(
        temperature_k, component.critical_temperature_k
    )
    kappa = calculate_kappa(component.acentric_factor)
    root_reduced_temperature = sqrt(reduced_temperature)
    alpha_base = 1.0 + kappa * (1.0 - root_reduced_temperature)
    alpha = calculate_alpha(
        temperature_k,
        component.critical_temperature_k,
        component.acentric_factor,
    )
    alpha_derivative = -(
        kappa
        * alpha_base
        / (component.critical_temperature_k * root_reduced_temperature)
    )
    a = calculate_a_parameter(
        component.critical_temperature_k, component.critical_pressure_pa
    )
    b = calculate_b_parameter(
        component.critical_temperature_k, component.critical_pressure_pa
    )
    a_alpha = a * alpha
    a_alpha_derivative = a * alpha_derivative
    for name, value in (
        ("alpha temperature derivative", alpha_derivative),
        ("a_alpha", a_alpha),
        ("a_alpha temperature derivative", a_alpha_derivative),
    ):
        _require_finite(value, name)
    return PureComponentTemperatureDerivatives(
        component_name=component.name,
        temperature_k=temperature_k,
        reduced_temperature=reduced_temperature,
        kappa=kappa,
        alpha=alpha,
        alpha_temperature_derivative_per_k=alpha_derivative,
        a=a,
        a_alpha=a_alpha,
        a_alpha_temperature_derivative=a_alpha_derivative,
        b=b,
    )


def _resolve_reference_index(component_count: int, requested: int | None) -> int:
    if requested is None:
        return component_count - 1
    if not isinstance(requested, int) or isinstance(requested, bool):
        raise ValueError("reference_component_index must be an integer.")
    if not 0 <= requested < component_count:
        raise ValueError("reference_component_index is outside component order.")
    return requested


def calculate_mixture_parameter_derivatives(
    parameters: PengRobinsonMixtureParameters,
    binary_interactions: BinaryInteractionMapping | None = None,
    *,
    reference_component_index: int | None = None,
) -> MixtureParameterDerivatives:
    """Return analytical PR mixture derivatives at fixed ``kij`` values.

    Pressure derivatives hold temperature and composition fixed. Temperature
    derivatives hold pressure and composition fixed. Composition derivatives
    are tangent to the mole-fraction simplex using the documented reference
    component; temperature, pressure, component properties, and ``kij`` are
    fixed for those columns.
    """

    validate_component_parameter_provenance(
        parameters.component_parameters, parameters.temperature_k
    )
    component_names = tuple(
        item.component_name for item in parameters.component_parameters
    )
    stored_interactions = resolve_binary_interaction_metadata(
        parameters.binary_interactions,
        parameters.binary_interaction_policy,
        parameters.supplied_binary_interaction_pairs,
        parameters.defaulted_binary_interaction_pairs,
        set(component_names),
    )
    if binary_interactions is not None:
        names = set(component_names)
        supplied_interactions = canonicalize_binary_interactions(
            binary_interactions, names
        )
        supplied_pairs = canonicalize_supplied_binary_interaction_pairs(
            binary_interactions, names
        )
        if (
            supplied_interactions != parameters.binary_interactions
            or supplied_pairs != parameters.supplied_binary_interaction_pairs
        ):
            raise ValueError(
                "binary_interactions do not match stored mixture provenance."
            )

    expected_a = calculate_mixture_a_alpha(
        parameters.component_parameters, stored_interactions
    )
    expected_b = calculate_mixture_b(parameters.component_parameters)
    expected_A = calculate_mixture_A_parameter(
        expected_a, parameters.pressure_pa, parameters.temperature_k
    )
    expected_B = calculate_mixture_B_parameter(
        expected_b, parameters.pressure_pa, parameters.temperature_k
    )
    _require_consistent(parameters.a_alpha_mix, expected_a, "a_alpha_mix")
    _require_consistent(parameters.b_mix, expected_b, "b_mix")
    _require_consistent(parameters.A_mix, expected_A, "A_mix")
    _require_consistent(parameters.B_mix, expected_B, "B_mix")
    _require_positive(parameters.pressure_pa, "pressure_pa")

    pure = tuple(
        calculate_pure_component_temperature_derivatives(
            item.component, parameters.temperature_k
        )
        for item in parameters.component_parameters
    )
    pair = tuple(
        tuple(
            calculate_component_pair_attraction_parameter(
                first, second, stored_interactions
            )
            for second in parameters.component_parameters
        )
        for first in parameters.component_parameters
    )
    pair_temperature = tuple(
        tuple(
            pair[i][j]
            * 0.5
            * (
                pure[i].a_alpha_temperature_derivative / pure[i].a_alpha
                + pure[j].a_alpha_temperature_derivative / pure[j].a_alpha
            )
            for j in range(len(pure))
        )
        for i in range(len(pure))
    )
    fractions = tuple(item.mole_fraction for item in parameters.component_parameters)
    attraction_sums = tuple(
        calculate_component_attraction_sum(
            item, parameters.component_parameters, stored_interactions
        )
        for item in parameters.component_parameters
    )
    attraction_sum_temperature = tuple(
        fsum(fractions[j] * pair_temperature[i][j] for j in range(len(pure)))
        for i in range(len(pure))
    )
    a_temperature = fsum(
        fractions[i] * fractions[j] * pair_temperature[i][j]
        for i in range(len(pure))
        for j in range(len(pure))
    )
    b_temperature = 0.0
    pressure = parameters.pressure_pa
    temperature = parameters.temperature_k
    A_pressure = parameters.A_mix / pressure
    B_pressure = parameters.B_mix / pressure
    A_temperature = parameters.A_mix * (
        a_temperature / parameters.a_alpha_mix - 2.0 / temperature
    )
    B_temperature = -parameters.B_mix / temperature

    reference = _resolve_reference_index(len(pure), reference_component_index)
    independent = tuple(i for i in range(len(pure)) if i != reference)
    a_composition = tuple(
        2.0 * (attraction_sums[i] - attraction_sums[reference]) for i in independent
    )
    b_composition = tuple(pure[i].b - pure[reference].b for i in independent)
    A_composition = tuple(
        parameters.A_mix * value / parameters.a_alpha_mix for value in a_composition
    )
    B_composition = tuple(
        parameters.B_mix * value / parameters.b_mix for value in b_composition
    )
    attraction_sum_composition = tuple(
        tuple(pair[i][k] - pair[i][reference] for k in independent)
        for i in range(len(pure))
    )
    values = (
        *attraction_sum_temperature,
        a_temperature,
        A_pressure,
        B_pressure,
        A_temperature,
        B_temperature,
        *a_composition,
        *b_composition,
        *A_composition,
        *B_composition,
        *(value for row in attraction_sum_composition for value in row),
    )
    if not all(isfinite(value) for value in values):
        raise ValueError("mixture parameter derivatives must remain finite.")
    return MixtureParameterDerivatives(
        component_names=component_names,
        reference_component_index=reference,
        independent_component_indices=independent,
        pure_temperature_derivatives=pure,
        pair_attraction_parameters=pair,
        pair_attraction_temperature_derivatives=pair_temperature,
        component_attraction_sums=attraction_sums,
        component_attraction_sum_temperature_derivatives=(attraction_sum_temperature),
        a_alpha_mix_temperature_derivative=a_temperature,
        b_mix_temperature_derivative=b_temperature,
        A_mix_pressure_derivative_per_pa=A_pressure,
        B_mix_pressure_derivative_per_pa=B_pressure,
        A_mix_log_pressure_derivative=parameters.A_mix,
        B_mix_log_pressure_derivative=parameters.B_mix,
        A_mix_temperature_derivative_per_k=A_temperature,
        B_mix_temperature_derivative_per_k=B_temperature,
        a_alpha_mix_composition_derivatives=a_composition,
        b_mix_composition_derivatives=b_composition,
        A_mix_composition_derivatives=A_composition,
        B_mix_composition_derivatives=B_composition,
        component_attraction_sum_composition_derivatives=(attraction_sum_composition),
    )


def calculate_fixed_root_compressibility_derivative(
    compressibility_factor: float,
    A_mix: float,
    B_mix: float,
    A_mix_derivative: float,
    B_mix_derivative: float,
    *,
    derivative_variable: str,
    derivative_units: str,
) -> FixedRootCompressibilityDerivative:
    """Implicitly differentiate the PR cubic along one fixed physical root.

    This differentiates ``F(Z,A,B)=0`` as
    ``dZ/dq=-(F_A*dA/dq+F_B*dB/dq)/F_Z``. It does not differentiate root
    finding, sorting, admissibility, mechanical classification, or selection.
    """

    if not derivative_variable:
        raise ValueError("derivative_variable must not be empty.")
    if not derivative_units:
        raise ValueError("derivative_units must not be empty.")
    for name, value in (
        ("A_mix_derivative", A_mix_derivative),
        ("B_mix_derivative", B_mix_derivative),
    ):
        _require_finite(value, name)
    validate_compressibility_root(compressibility_factor, A_mix, B_mix)
    z = compressibility_factor
    partial_z_terms = (
        3.0 * z**2,
        2.0 * (B_mix - 1.0) * z,
        A_mix - 3.0 * B_mix**2 - 2.0 * B_mix,
    )
    partial_z = fsum(partial_z_terms)
    partial_A = z - B_mix
    partial_B = z**2 + (-6.0 * B_mix - 2.0) * z - A_mix + 2.0 * B_mix + 3.0 * B_mix**2
    parameter_partial = partial_A * A_mix_derivative + partial_B * B_mix_derivative
    scale = fsum(abs(value) for value in partial_z_terms)
    tolerance = FIXED_ROOT_DERIVATIVE_ERROR_FACTOR * max(
        ulp(scale), float_info.epsilon * scale, float_info.min
    )
    for name, value in (
        ("cubic partial Z", partial_z),
        ("cubic parameter partial", parameter_partial),
        ("fixed-root singularity tolerance", tolerance),
    ):
        _require_finite(value, name)
    if abs(partial_z) <= tolerance:
        return FixedRootCompressibilityDerivative(
            derivative_variable=derivative_variable,
            derivative_units=derivative_units,
            applicable=False,
            derivative=None,
            cubic_partial_z=partial_z,
            parameter_partial=parameter_partial,
            singularity_tolerance=tolerance,
            failure_reason=(
                "The selected root is locally multiple or too ill-conditioned "
                "for a reliable fixed-root derivative."
            ),
        )
    derivative = -parameter_partial / partial_z
    if not isfinite(derivative):
        return FixedRootCompressibilityDerivative(
            derivative_variable=derivative_variable,
            derivative_units=derivative_units,
            applicable=False,
            derivative=None,
            cubic_partial_z=partial_z,
            parameter_partial=parameter_partial,
            singularity_tolerance=tolerance,
            failure_reason="The fixed-root derivative is non-finite.",
        )
    return FixedRootCompressibilityDerivative(
        derivative_variable=derivative_variable,
        derivative_units=derivative_units,
        applicable=True,
        derivative=derivative,
        cubic_partial_z=partial_z,
        parameter_partial=parameter_partial,
        singularity_tolerance=tolerance,
        failure_reason=None,
    )


def _log_fugacity_derivative(
    *,
    z: float,
    A: float,
    B: float,
    a_mix: float,
    b_mix: float,
    attraction_sum: float,
    component_b: float,
    d_z: float,
    d_A: float,
    d_B: float,
    d_a_mix: float,
    d_b_mix: float,
    d_attraction_sum: float,
) -> float:
    root_offset = calculate_compressibility_root_offset(z, A, B)
    sqrt_two = sqrt(2.0)
    c_plus = 1.0 + sqrt_two
    c_minus = 1.0 - sqrt_two
    z_minus_b = 1.0 + root_offset - B
    numerator = 1.0 + root_offset + c_plus * B
    denominator = 1.0 + root_offset + c_minus * B
    for name, value in (
        ("Z-B", z_minus_b),
        ("fugacity logarithm numerator", numerator),
        ("fugacity logarithm denominator", denominator),
    ):
        _require_positive(value, name)
    logarithm_ratio = log1p(root_offset + c_plus * B) - log1p(root_offset + c_minus * B)
    b_ratio = component_b / b_mix
    d_b_ratio = -b_ratio * d_b_mix / b_mix
    attraction_bracket = 2.0 * attraction_sum / a_mix - b_ratio
    d_attraction_bracket = (
        2.0 * (d_attraction_sum / a_mix - attraction_sum * d_a_mix / a_mix**2)
        - d_b_ratio
    )
    attraction_factor = A / (2.0 * sqrt_two * B)
    d_attraction_factor = (d_A * B - A * d_B) / (2.0 * sqrt_two * B**2)
    d_logarithm_ratio = (d_z + c_plus * d_B) / numerator - (
        d_z + c_minus * d_B
    ) / denominator
    derivative = (
        d_b_ratio * root_offset
        + b_ratio * d_z
        - (d_z - d_B) / z_minus_b
        - d_attraction_factor * attraction_bracket * logarithm_ratio
        - attraction_factor * d_attraction_bracket * logarithm_ratio
        - attraction_factor * attraction_bracket * d_logarithm_ratio
    )
    _require_finite(derivative, "log fugacity coefficient derivative")
    return derivative


def calculate_fixed_root_mixture_fugacity_derivatives(
    parameters: PengRobinsonMixtureParameters,
    compressibility_factor: float,
    binary_interactions: BinaryInteractionMapping | None = None,
    *,
    reference_component_index: int | None = None,
) -> FixedRootMixtureFugacityDerivatives:
    """Return pressure, temperature, and simplex derivatives of ``ln(phi_i)``.

    The selected ``Z`` must be a genuine current cubic root. Pressure columns
    hold temperature/composition fixed; temperature columns hold
    pressure/composition fixed; composition columns hold pressure, temperature,
    component properties, and ``kij`` fixed. Derivatives are local to that root
    and exclude every root-selection operation and discontinuity.
    """

    base = calculate_mixture_fugacity_coefficients(
        parameters, compressibility_factor, binary_interactions
    )
    derivatives = calculate_mixture_parameter_derivatives(
        parameters,
        binary_interactions,
        reference_component_index=reference_component_index,
    )
    pressure_root = calculate_fixed_root_compressibility_derivative(
        compressibility_factor,
        parameters.A_mix,
        parameters.B_mix,
        derivatives.A_mix_pressure_derivative_per_pa,
        derivatives.B_mix_pressure_derivative_per_pa,
        derivative_variable="pressure_pa",
        derivative_units="Pa^-1",
    )
    temperature_root = calculate_fixed_root_compressibility_derivative(
        compressibility_factor,
        parameters.A_mix,
        parameters.B_mix,
        derivatives.A_mix_temperature_derivative_per_k,
        derivatives.B_mix_temperature_derivative_per_k,
        derivative_variable="temperature_k",
        derivative_units="K^-1",
    )
    composition_roots = tuple(
        calculate_fixed_root_compressibility_derivative(
            compressibility_factor,
            parameters.A_mix,
            parameters.B_mix,
            d_A,
            d_B,
            derivative_variable=(f"simplex_mole_fraction[{component_index}]"),
            derivative_units="mole-fraction^-1",
        )
        for component_index, d_A, d_B in zip(
            derivatives.independent_component_indices,
            derivatives.A_mix_composition_derivatives,
            derivatives.B_mix_composition_derivatives,
            strict=True,
        )
    )
    root_results = (pressure_root, temperature_root, *composition_roots)
    failure = next(
        (item.failure_reason for item in root_results if not item.applicable), None
    )
    component_names = derivatives.component_names
    log_phi = tuple(item.log_fugacity_coefficient for item in base)
    if failure is not None:
        return FixedRootMixtureFugacityDerivatives(
            component_names=component_names,
            compressibility_factor=compressibility_factor,
            log_fugacity_coefficients=log_phi,
            parameter_derivatives=derivatives,
            pressure_root_derivative=pressure_root,
            temperature_root_derivative=temperature_root,
            composition_root_derivatives=composition_roots,
            applicable=False,
            failure_reason=failure,
            log_fugacity_pressure_derivatives_per_pa=None,
            log_fugacity_log_pressure_derivatives=None,
            log_fugacity_temperature_derivatives_per_k=None,
            log_fugacity_composition_derivatives=None,
        )

    pressure_z = pressure_root.derivative
    temperature_z = temperature_root.derivative
    if pressure_z is None or temperature_z is None:
        raise RuntimeError("applicable root derivatives must contain values.")
    pressure_values: list[float] = []
    temperature_values: list[float] = []
    composition_rows: list[tuple[float, ...]] = []
    for i, component in enumerate(parameters.component_parameters):
        common = {
            "z": compressibility_factor,
            "A": parameters.A_mix,
            "B": parameters.B_mix,
            "a_mix": parameters.a_alpha_mix,
            "b_mix": parameters.b_mix,
            "attraction_sum": derivatives.component_attraction_sums[i],
            "component_b": component.b,
        }
        pressure_values.append(
            _log_fugacity_derivative(
                **common,
                d_z=pressure_z,
                d_A=derivatives.A_mix_pressure_derivative_per_pa,
                d_B=derivatives.B_mix_pressure_derivative_per_pa,
                d_a_mix=0.0,
                d_b_mix=0.0,
                d_attraction_sum=0.0,
            )
        )
        temperature_values.append(
            _log_fugacity_derivative(
                **common,
                d_z=temperature_z,
                d_A=derivatives.A_mix_temperature_derivative_per_k,
                d_B=derivatives.B_mix_temperature_derivative_per_k,
                d_a_mix=derivatives.a_alpha_mix_temperature_derivative,
                d_b_mix=0.0,
                d_attraction_sum=(
                    derivatives.component_attraction_sum_temperature_derivatives[i]
                ),
            )
        )
        row = tuple(
            _log_fugacity_derivative(
                **common,
                d_z=root.derivative if root.derivative is not None else 0.0,
                d_A=d_A,
                d_B=d_B,
                d_a_mix=d_a,
                d_b_mix=d_b,
                d_attraction_sum=(
                    derivatives.component_attraction_sum_composition_derivatives[i][j]
                ),
            )
            for j, (root, d_A, d_B, d_a, d_b) in enumerate(
                zip(
                    composition_roots,
                    derivatives.A_mix_composition_derivatives,
                    derivatives.B_mix_composition_derivatives,
                    derivatives.a_alpha_mix_composition_derivatives,
                    derivatives.b_mix_composition_derivatives,
                    strict=True,
                )
            )
        )
        composition_rows.append(row)
    pressure_tuple = tuple(pressure_values)
    return FixedRootMixtureFugacityDerivatives(
        component_names=component_names,
        compressibility_factor=compressibility_factor,
        log_fugacity_coefficients=log_phi,
        parameter_derivatives=derivatives,
        pressure_root_derivative=pressure_root,
        temperature_root_derivative=temperature_root,
        composition_root_derivatives=composition_roots,
        applicable=True,
        failure_reason=None,
        log_fugacity_pressure_derivatives_per_pa=pressure_tuple,
        log_fugacity_log_pressure_derivatives=tuple(
            parameters.pressure_pa * value for value in pressure_tuple
        ),
        log_fugacity_temperature_derivatives_per_k=tuple(temperature_values),
        log_fugacity_composition_derivatives=tuple(composition_rows),
    )


def calculate_pure_dimensionless_parameter_derivatives(
    component: Component,
    temperature_k: float,
    pressure_pa: float,
) -> PureDimensionlessParameterDerivatives:
    """Return explicit pure ``A`` and ``B`` pressure/temperature derivatives.

    Pressure derivatives are per Pa at fixed temperature. Temperature
    derivatives are per K at fixed pressure. This exact-identity helper keeps
    the distinction between pressure and log-pressure derivatives explicit.
    """

    _require_positive(pressure_pa, "pressure_pa")
    pure = calculate_pure_component_temperature_derivatives(component, temperature_k)
    A = calculate_A_parameter(pressure_pa, temperature_k, pure.a, pure.alpha)
    B = calculate_B_parameter(pressure_pa, temperature_k, pure.b)
    return PureDimensionlessParameterDerivatives(
        component_name=component.name,
        temperature_k=temperature_k,
        pressure_pa=pressure_pa,
        A=A,
        B=B,
        A_pressure_derivative_per_pa=A / pressure_pa,
        B_pressure_derivative_per_pa=B / pressure_pa,
        A_log_pressure_derivative=A,
        B_log_pressure_derivative=B,
        A_temperature_derivative_per_k=A
        * (pure.a_alpha_temperature_derivative / pure.a_alpha - 2.0 / temperature_k),
        B_temperature_derivative_per_k=-B / temperature_k,
    )
