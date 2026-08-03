"""Component fugacity coefficients for a fixed Peng-Robinson mixture root."""

from dataclasses import dataclass
from math import exp, fsum, log1p, sqrt, ulp
from sys import float_info
from typing import Final

from pvt_phase_simulator._validation import (
    require_finite as _require_finite,
)
from pvt_phase_simulator._validation import (
    require_positive as _require_positive,
)
from pvt_phase_simulator.eos import mixing_rules as _mixing_rules
from pvt_phase_simulator.eos.mixing_rules import (
    BinaryInteractionMapping,
    BinaryInteractionPolicy,
    CanonicalBinaryInteractionPairs,
    PengRobinsonMixtureParameters,
    PureComponentMixtureParameters,
    calculate_mixture_a_alpha,
    calculate_mixture_A_parameter,
    calculate_mixture_b,
    calculate_mixture_B_parameter,
    canonicalize_binary_interactions,
    canonicalize_supplied_binary_interaction_pairs,
    resolve_binary_interaction_metadata,
)
from pvt_phase_simulator.eos.peng_robinson import (
    MechanicalStabilityResult,
    calculate_compressibility_root_offset,
    classify_mechanical_stability,
    validate_compressibility_root,
)

# Deterministic reconstruction normally returns bit-identical values. A small
# ULP allowance accommodates harmless changes in float64 evaluation order
# without introducing a unit-dependent absolute floor.
FLOAT64_RECONSTRUCTION_ERROR_FACTOR: Final = 32.0


@dataclass(frozen=True, slots=True)
class MixtureFugacityCoefficientResult:
    """Dimensionless ``ln(phi_i)`` and ``phi_i`` at one dimensionless Z root."""

    component_name: str
    mole_fraction: float
    log_fugacity_coefficient: float
    fugacity_coefficient: float


@dataclass(frozen=True, slots=True)
class MixtureRootFugacityResult:
    """Diagnostic fugacity results for one genuine mixture cubic root.

    Mechanical stability is local at fixed temperature. This result does not
    determine global mixture phase stability. Binary-interaction policy and
    defaulted-pair assumptions are exposed rather than hidden.
    """

    compressibility_factor: float
    mechanical_stability: MechanicalStabilityResult
    component_results: tuple[MixtureFugacityCoefficientResult, ...]
    binary_interaction_policy: BinaryInteractionPolicy = (
        BinaryInteractionPolicy.DEFAULT_ZERO
    )
    defaulted_binary_interaction_pairs: CanonicalBinaryInteractionPairs = ()


def _require_consistent(actual: float, expected: float, name: str) -> None:
    _require_finite(actual, name)
    _require_finite(expected, f"expected {name}")
    if expected == 0.0:
        consistent = actual == 0.0
    else:
        allowed_error = FLOAT64_RECONSTRUCTION_ERROR_FACTOR * max(
            ulp(expected),
            float_info.epsilon * abs(expected),
        )
        consistent = abs(actual - expected) <= allowed_error
    if not consistent:
        raise ValueError(f"{name} is inconsistent with the component parameters.")


def calculate_component_pair_attraction_parameter(
    component_i: PureComponentMixtureParameters,
    component_j: PureComponentMixtureParameters,
    binary_interactions: BinaryInteractionMapping | None = None,
) -> float:
    """Return ``a_ij`` in Pa·m^6/mol^2 using the mixing-rules implementation."""

    return _mixing_rules.calculate_component_pair_attraction_parameter(
        component_i,
        component_j,
        binary_interactions,
    )


def _require_component_membership(
    component_i: PureComponentMixtureParameters,
    component_parameters: tuple[PureComponentMixtureParameters, ...],
) -> None:
    matches = tuple(
        parameter
        for parameter in component_parameters
        if parameter.component_name == component_i.component_name
    )
    if len(matches) != 1 or matches[0] != component_i:
        raise ValueError(
            "component_i must exactly match one entry in component_parameters."
        )


def _calculate_component_attraction_sum_validated(
    component_i: PureComponentMixtureParameters,
    component_parameters: tuple[PureComponentMixtureParameters, ...],
    binary_interactions: BinaryInteractionMapping | None,
) -> float:
    try:
        attraction_sum = fsum(
            component_j.mole_fraction
            * _mixing_rules.calculate_component_pair_attraction_parameter(
                component_i,
                component_j,
                binary_interactions,
            )
            for component_j in component_parameters
        )
    except (OverflowError, ValueError) as error:
        raise ValueError("component attraction sum must be finite.") from error
    _require_finite(attraction_sum, "component attraction sum")
    return attraction_sum


def calculate_component_attraction_sum(
    component_i: PureComponentMixtureParameters,
    component_parameters: tuple[PureComponentMixtureParameters, ...],
    binary_interactions: BinaryInteractionMapping | None = None,
) -> float:
    """Calculate ``sum_j(x_j*a_ij)`` in Pa·m^6/mol^2 for component i."""

    calculate_mixture_a_alpha(component_parameters, binary_interactions)
    _require_component_membership(component_i, component_parameters)
    return _calculate_component_attraction_sum_validated(
        component_i,
        component_parameters,
        binary_interactions,
    )


def _resolve_binary_interactions(
    parameters: PengRobinsonMixtureParameters,
    binary_interactions: BinaryInteractionMapping | None,
) -> dict[tuple[str, str], float]:
    component_names = {
        parameter.component_name for parameter in parameters.component_parameters
    }
    stored_interactions = resolve_binary_interaction_metadata(
        parameters.binary_interactions,
        parameters.binary_interaction_policy,
        parameters.supplied_binary_interaction_pairs,
        parameters.defaulted_binary_interaction_pairs,
        component_names,
    )
    if binary_interactions is not None:
        supplied_canonical = canonicalize_binary_interactions(
            binary_interactions,
            component_names,
        )
        supplied_pairs = canonicalize_supplied_binary_interaction_pairs(
            binary_interactions,
            component_names,
        )
        if (
            supplied_canonical != parameters.binary_interactions
            or supplied_pairs != parameters.supplied_binary_interaction_pairs
        ):
            raise ValueError(
                "binary_interactions do not match the interactions stored with "
                "the mixture parameters."
            )
    return stored_interactions


def _validate_mixture_parameters(
    parameters: PengRobinsonMixtureParameters,
    binary_interactions: BinaryInteractionMapping | None,
) -> dict[tuple[str, str], float]:
    _mixing_rules.validate_component_parameter_provenance(
        parameters.component_parameters,
        parameters.temperature_k,
    )
    stored_interactions = _resolve_binary_interactions(
        parameters,
        binary_interactions,
    )
    expected_a_alpha_mix = calculate_mixture_a_alpha(
        parameters.component_parameters,
        stored_interactions,
    )
    expected_b_mix = calculate_mixture_b(parameters.component_parameters)
    expected_A_mix = calculate_mixture_A_parameter(
        expected_a_alpha_mix,
        parameters.pressure_pa,
        parameters.temperature_k,
    )
    expected_B_mix = calculate_mixture_B_parameter(
        expected_b_mix,
        parameters.pressure_pa,
        parameters.temperature_k,
    )
    _require_consistent(
        parameters.a_alpha_mix,
        expected_a_alpha_mix,
        "a_alpha_mix",
    )
    _require_consistent(parameters.b_mix, expected_b_mix, "b_mix")
    _require_consistent(parameters.A_mix, expected_A_mix, "A_mix")
    _require_consistent(parameters.B_mix, expected_B_mix, "B_mix")

    if parameters.pressure_pa == 0.0 and (
        parameters.A_mix != 0.0 or parameters.B_mix != 0.0
    ):
        raise ValueError("A_mix and B_mix must equal zero at zero pressure.")
    return stored_interactions


def _validate_compressibility_factor(
    compressibility_factor: float,
    parameters: PengRobinsonMixtureParameters,
) -> None:
    if compressibility_factor <= parameters.B_mix:
        raise ValueError("compressibility_factor must be greater than B_mix.")
    validate_compressibility_root(
        compressibility_factor,
        parameters.A_mix,
        parameters.B_mix,
    )


def _calculate_logarithm_ratio(
    root_offset: float,
    B_mix: float,
) -> float:
    sqrt_two = sqrt(2.0)
    numerator_offset = root_offset + (1.0 + sqrt_two) * B_mix
    denominator_offset = root_offset + (1.0 - sqrt_two) * B_mix
    _require_finite(numerator_offset, "mixture fugacity numerator offset")
    _require_finite(denominator_offset, "mixture fugacity denominator offset")
    _require_positive(
        1.0 + numerator_offset,
        "mixture fugacity logarithm numerator",
    )
    _require_positive(
        1.0 + denominator_offset,
        "mixture fugacity logarithm denominator",
    )
    logarithm_ratio = log1p(numerator_offset) - log1p(denominator_offset)
    _require_finite(logarithm_ratio, "mixture fugacity logarithm")
    return logarithm_ratio


def _calculate_log_component_fugacity_coefficient_validated(
    component_i: PureComponentMixtureParameters,
    parameters: PengRobinsonMixtureParameters,
    compressibility_factor: float,
    binary_interactions: BinaryInteractionMapping | None,
) -> float:
    if parameters.pressure_pa == 0.0:
        return 0.0

    _require_positive(parameters.B_mix, "B_mix")
    _require_positive(parameters.a_alpha_mix, "a_alpha_mix")
    _require_positive(parameters.b_mix, "b_mix")
    root_offset = calculate_compressibility_root_offset(
        compressibility_factor,
        parameters.A_mix,
        parameters.B_mix,
    )
    z_minus_b_offset = root_offset - parameters.B_mix
    _require_positive(
        1.0 + z_minus_b_offset,
        "Z - B_mix logarithm argument",
    )
    logarithm_ratio = _calculate_logarithm_ratio(
        root_offset,
        parameters.B_mix,
    )
    attraction_sum = _calculate_component_attraction_sum_validated(
        component_i,
        parameters.component_parameters,
        binary_interactions,
    )
    b_ratio = component_i.b / parameters.b_mix
    attraction_bracket = 2.0 * attraction_sum / parameters.a_alpha_mix - b_ratio
    attraction_factor = parameters.A_mix / (2.0 * sqrt(2.0) * parameters.B_mix)
    log_fugacity_coefficient = (
        b_ratio * root_offset
        - log1p(z_minus_b_offset)
        - attraction_factor * attraction_bracket * logarithm_ratio
    )
    _require_finite(
        log_fugacity_coefficient,
        "component log fugacity coefficient",
    )
    return log_fugacity_coefficient


def calculate_log_component_fugacity_coefficient(
    component_i: PureComponentMixtureParameters,
    parameters: PengRobinsonMixtureParameters,
    compressibility_factor: float,
    binary_interactions: BinaryInteractionMapping | None = None,
) -> float:
    """Calculate dimensionless ``ln(phi_i)`` at a validated dimensionless Z."""

    stored_interactions = _validate_mixture_parameters(
        parameters,
        binary_interactions,
    )
    _validate_compressibility_factor(
        compressibility_factor,
        parameters,
    )
    _require_component_membership(component_i, parameters.component_parameters)
    return _calculate_log_component_fugacity_coefficient_validated(
        component_i,
        parameters,
        compressibility_factor,
        stored_interactions,
    )


def _exponentiate_fugacity_coefficient(
    log_fugacity_coefficient: float,
) -> float:
    _require_finite(log_fugacity_coefficient, "log_fugacity_coefficient")
    try:
        fugacity_coefficient = exp(log_fugacity_coefficient)
    except OverflowError as error:
        raise ValueError("fugacity coefficient must be finite.") from error
    _require_positive(fugacity_coefficient, "fugacity coefficient")
    return fugacity_coefficient


def calculate_component_fugacity_coefficient(
    component_i: PureComponentMixtureParameters,
    parameters: PengRobinsonMixtureParameters,
    compressibility_factor: float,
    binary_interactions: BinaryInteractionMapping | None = None,
) -> float:
    """Calculate dimensionless ``phi_i`` at a validated dimensionless Z."""

    log_fugacity_coefficient = calculate_log_component_fugacity_coefficient(
        component_i,
        parameters,
        compressibility_factor,
        binary_interactions,
    )
    return _exponentiate_fugacity_coefficient(log_fugacity_coefficient)


def calculate_mixture_fugacity_coefficients(
    parameters: PengRobinsonMixtureParameters,
    compressibility_factor: float,
    binary_interactions: BinaryInteractionMapping | None = None,
) -> tuple[MixtureFugacityCoefficientResult, ...]:
    """Low-level component fugacities at any genuine mixture cubic root.

    This backward-compatible function does not report or determine global
    phase stability. Results are immutable, dimensionless, and retain component
    ordering. Invalid roots, forged parameter provenance, mismatched
    interactions, invalid logarithm domains, or non-finite results raise
    ``ValueError``. Prefer :func:`calculate_mixture_root_fugacity_result` when
    root-level mechanical status is required.
    """

    stored_interactions = _validate_mixture_parameters(
        parameters,
        binary_interactions,
    )
    _validate_compressibility_factor(
        compressibility_factor,
        parameters,
    )

    results: list[MixtureFugacityCoefficientResult] = []
    for component_i in parameters.component_parameters:
        log_fugacity_coefficient = (
            _calculate_log_component_fugacity_coefficient_validated(
                component_i,
                parameters,
                compressibility_factor,
                stored_interactions,
            )
        )
        results.append(
            MixtureFugacityCoefficientResult(
                component_name=component_i.component_name,
                mole_fraction=component_i.mole_fraction,
                log_fugacity_coefficient=log_fugacity_coefficient,
                fugacity_coefficient=_exponentiate_fugacity_coefficient(
                    log_fugacity_coefficient
                ),
            )
        )

    return tuple(results)


def calculate_mixture_root_fugacity_result(
    parameters: PengRobinsonMixtureParameters,
    compressibility_factor: float,
    binary_interactions: BinaryInteractionMapping | None = None,
) -> MixtureRootFugacityResult:
    """Return component fugacities plus local mechanical status for one root.

    Genuine stable, unstable, and marginal roots may all be evaluated. The
    classification is not a global mixture phase-stability calculation.
    """

    component_results = calculate_mixture_fugacity_coefficients(
        parameters,
        compressibility_factor,
        binary_interactions,
    )
    return MixtureRootFugacityResult(
        compressibility_factor=compressibility_factor,
        mechanical_stability=classify_mechanical_stability(
            compressibility_factor,
            parameters.A_mix,
            parameters.B_mix,
        ),
        component_results=component_results,
        binary_interaction_policy=parameters.binary_interaction_policy,
        defaulted_binary_interaction_pairs=(
            parameters.defaulted_binary_interaction_pairs
        ),
    )
