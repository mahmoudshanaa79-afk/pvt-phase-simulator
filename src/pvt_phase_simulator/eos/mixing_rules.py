"""Classical Peng-Robinson mixing rules for fixed-composition fluids."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from math import fsum, isclose, sqrt, ulp
from sys import float_info
from typing import Final

from pvt_phase_simulator._validation import (
    require_finite as _require_finite,
)
from pvt_phase_simulator._validation import (
    require_non_negative as _require_non_negative,
)
from pvt_phase_simulator._validation import (
    require_positive as _require_positive,
)
from pvt_phase_simulator.eos.peng_robinson import (
    calculate_a_parameter,
    calculate_alpha,
    calculate_b_parameter,
    calculate_compressibility_roots,
    calculate_kappa,
    calculate_reduced_temperature,
    filter_mechanically_stable_compressibility_roots,
)
from pvt_phase_simulator.fluid_models import (
    MOLE_FRACTION_TOLERANCE,
    Component,
    FluidMixture,
    MixtureComponent,
)
from pvt_phase_simulator.physical_constants import UNIVERSAL_GAS_CONSTANT

type BinaryInteractionKey = tuple[str, str]
type BinaryInteractionMapping = Mapping[BinaryInteractionKey, float]
type CanonicalBinaryInteraction = tuple[str, str, float]
type CanonicalBinaryInteractions = tuple[CanonicalBinaryInteraction, ...]
type CanonicalBinaryInteractionPair = tuple[str, str]
type CanonicalBinaryInteractionPairs = tuple[CanonicalBinaryInteractionPair, ...]

DERIVED_PARAMETER_ERROR_FACTOR: Final = 32.0


class BinaryInteractionPolicy(StrEnum):
    """Policy for omitted off-diagonal dimensionless ``k_ij`` values.

    ``DEFAULT_ZERO`` is an explicit approximation; it is not a universal
    physical statement. ``REQUIRE_ALL_PAIRS`` rejects incomplete pair data.
    """

    DEFAULT_ZERO = "default_zero"
    REQUIRE_ALL_PAIRS = "require_all_pairs"


@dataclass(frozen=True, slots=True)
class PureComponentMixtureParameters:
    """Pure-component quantities needed by the classical mixing rules.

    Temperature and pressure-derived quantities use SI units: reduced
    temperature, kappa, and alpha are dimensionless; ``a`` and ``a_alpha`` are
    in Pa·m^6/mol^2; and ``b`` is in m^3/mol.
    """

    component: Component
    mole_fraction: float
    temperature_k: float
    reduced_temperature: float
    kappa: float
    alpha: float
    a: float
    a_alpha: float
    b: float

    @property
    def component_name(self) -> str:
        """Return the name from the immutable component source of truth."""

        return self.component.name


@dataclass(frozen=True, slots=True)
class PengRobinsonMixtureParameters:
    """Aggregated Peng-Robinson parameters for a fixed-composition mixture.

    ``temperature_k`` is in K and ``pressure_pa`` is in Pa. ``a_alpha_mix`` is
    in Pa·m^6/mol^2, ``b_mix`` is in m^3/mol, and ``A_mix`` and ``B_mix`` are
    dimensionless. Interaction policy, supplied pairs, and defaulted pairs are
    immutable provenance used by downstream fugacity calculations.
    """

    temperature_k: float
    pressure_pa: float
    component_parameters: tuple[PureComponentMixtureParameters, ...]
    a_alpha_mix: float
    b_mix: float
    A_mix: float
    B_mix: float
    binary_interactions: CanonicalBinaryInteractions = ()
    binary_interaction_policy: BinaryInteractionPolicy = (
        BinaryInteractionPolicy.DEFAULT_ZERO
    )
    supplied_binary_interaction_pairs: CanonicalBinaryInteractionPairs = ()
    defaulted_binary_interaction_pairs: CanonicalBinaryInteractionPairs = ()


def _require_derived_parameter(
    actual: float,
    expected: float,
    name: str,
) -> None:
    """Require agreement within deterministic float64 reconstruction error."""

    _require_finite(actual, name)
    _require_finite(expected, f"expected {name}")
    if expected == 0.0:
        consistent = actual == 0.0
    else:
        tolerance = DERIVED_PARAMETER_ERROR_FACTOR * max(
            ulp(expected),
            float_info.epsilon * abs(expected),
        )
        consistent = abs(actual - expected) <= tolerance
    if not consistent:
        raise ValueError(f"{name} is inconsistent with component provenance.")


def _validate_single_component_parameter(
    parameter: PureComponentMixtureParameters,
    temperature_k: float | None = None,
) -> None:
    """Validate one parameter row against its immutable component and T."""

    if not isinstance(parameter.component, Component):
        raise ValueError("component provenance must be an immutable Component.")
    _require_non_negative(parameter.mole_fraction, "mole_fraction")
    if parameter.mole_fraction > 1.0:
        raise ValueError("mole_fraction must not exceed one.")
    _require_positive(parameter.temperature_k, "component temperature_k")
    if temperature_k is not None:
        _require_derived_parameter(
            parameter.temperature_k,
            temperature_k,
            "component temperature_k",
        )

    component = parameter.component
    expected_reduced_temperature = calculate_reduced_temperature(
        parameter.temperature_k,
        component.critical_temperature_k,
    )
    expected_kappa = calculate_kappa(component.acentric_factor)
    expected_alpha = calculate_alpha(
        parameter.temperature_k,
        component.critical_temperature_k,
        component.acentric_factor,
    )
    expected_a = calculate_a_parameter(
        component.critical_temperature_k,
        component.critical_pressure_pa,
    )
    expected_a_alpha = expected_a * expected_alpha
    _require_positive(expected_a_alpha, "expected a_alpha")
    expected_b = calculate_b_parameter(
        component.critical_temperature_k,
        component.critical_pressure_pa,
    )
    for name, actual, expected in (
        (
            "reduced_temperature",
            parameter.reduced_temperature,
            expected_reduced_temperature,
        ),
        ("kappa", parameter.kappa, expected_kappa),
        ("alpha", parameter.alpha, expected_alpha),
        ("a", parameter.a, expected_a),
        ("a_alpha", parameter.a_alpha, expected_a_alpha),
        ("b", parameter.b, expected_b),
    ):
        _require_derived_parameter(actual, expected, name)


def validate_component_parameter_provenance(
    component_parameters: tuple[PureComponentMixtureParameters, ...],
    temperature_k: float | None = None,
) -> None:
    """Re-derive every component parameter from immutable properties and T."""

    if not component_parameters:
        raise ValueError("component_parameters must not be empty.")
    if temperature_k is not None:
        _require_positive(temperature_k, "temperature_k")
    if any(
        not isinstance(parameter.component, Component)
        for parameter in component_parameters
    ):
        raise ValueError("component provenance must be an immutable Component.")

    names = [parameter.component_name.casefold() for parameter in component_parameters]
    if len(names) != len(set(names)):
        raise ValueError("component names must be unique case-insensitively.")

    reference_temperature = component_parameters[0].temperature_k
    for parameter in component_parameters:
        _validate_single_component_parameter(parameter, reference_temperature)
        if temperature_k is not None:
            _require_derived_parameter(
                parameter.temperature_k,
                temperature_k,
                "component temperature_k",
            )

    total = fsum(parameter.mole_fraction for parameter in component_parameters)
    if not isclose(total, 1.0, rel_tol=0.0, abs_tol=MOLE_FRACTION_TOLERANCE):
        raise ValueError("component mole fractions must sum to one within tolerance.")


def _validate_binary_interactions(
    binary_interactions: BinaryInteractionMapping | None,
    component_names: set[str] | None = None,
) -> None:
    if binary_interactions is None:
        return

    for key, coefficient in binary_interactions.items():
        if (
            not isinstance(key, tuple)
            or len(key) != 2
            or not all(isinstance(name, str) and name for name in key)
        ):
            raise ValueError(
                "binary interaction keys must be pairs of non-empty component names."
            )
        if component_names is not None and not set(key) <= component_names:
            casefold_names = {name.casefold(): name for name in component_names}
            mismatches = [
                name
                for name in key
                if name not in component_names and name.casefold() in casefold_names
            ]
            if mismatches:
                expected = ", ".join(
                    repr(casefold_names[name.casefold()]) for name in mismatches
                )
                raise ValueError(
                    "binary interaction component names are case-sensitive; "
                    f"use the canonical name(s) {expected}."
                )
            raise ValueError("binary interaction contains an unknown component name.")
        _require_finite(coefficient, f"binary interaction {key}")

        first_name, second_name = key
        if first_name == second_name:
            if coefficient != 0.0:
                raise ValueError("diagonal binary interactions must equal zero.")
            continue

        reverse_key = (second_name, first_name)
        if reverse_key not in binary_interactions:
            raise ValueError("binary interactions must include both symmetric entries.")
        if binary_interactions[reverse_key] != coefficient:
            raise ValueError("symmetric binary interactions must have equal values.")


def _canonical_component_pairs(
    component_names: set[str],
) -> CanonicalBinaryInteractionPairs:
    """Return every unique off-diagonal component pair in canonical order."""

    ordered_names = sorted(component_names)
    return tuple(
        (first_name, second_name)
        for index, first_name in enumerate(ordered_names)
        for second_name in ordered_names[index + 1 :]
    )


def canonicalize_supplied_binary_interaction_pairs(
    binary_interactions: BinaryInteractionMapping | None,
    component_names: set[str] | None = None,
) -> CanonicalBinaryInteractionPairs:
    """Return supplied off-diagonal pairs, retaining explicit zero values."""

    _validate_binary_interactions(binary_interactions, component_names)
    if binary_interactions is None:
        return ()
    canonical_pairs: set[CanonicalBinaryInteractionPair] = set()
    for first_name, second_name in binary_interactions:
        if first_name != second_name:
            canonical_pairs.add(
                (first_name, second_name)
                if first_name < second_name
                else (second_name, first_name)
            )
    return tuple(sorted(canonical_pairs))


def _resolve_binary_interaction_provenance(
    binary_interactions: BinaryInteractionMapping | None,
    component_names: set[str],
    policy: BinaryInteractionPolicy,
) -> tuple[CanonicalBinaryInteractionPairs, CanonicalBinaryInteractionPairs]:
    """Validate pair coverage and return supplied/defaulted pair provenance."""

    _validate_binary_interactions(binary_interactions, component_names)
    all_pairs = _canonical_component_pairs(component_names)
    supplied_pairs = canonicalize_supplied_binary_interaction_pairs(
        binary_interactions,
        component_names,
    )
    defaulted_pairs = tuple(pair for pair in all_pairs if pair not in supplied_pairs)
    if policy is BinaryInteractionPolicy.REQUIRE_ALL_PAIRS and defaulted_pairs:
        missing = ", ".join(f"{first}/{second}" for first, second in defaulted_pairs)
        raise ValueError(
            "binary interactions are required for every component pair; "
            f"missing: {missing}."
        )
    return supplied_pairs, defaulted_pairs


def canonicalize_binary_interactions(
    binary_interactions: BinaryInteractionMapping | None,
    component_names: set[str] | None = None,
) -> CanonicalBinaryInteractions:
    """Return sorted, immutable, nonzero k_ij entries with one entry per pair."""

    _validate_binary_interactions(binary_interactions, component_names)
    if binary_interactions is None:
        return ()

    canonical = [
        (first_name, second_name, coefficient)
        for (first_name, second_name), coefficient in binary_interactions.items()
        if first_name < second_name and coefficient != 0.0
    ]
    return tuple(sorted(canonical))


def canonical_binary_interactions_to_mapping(
    binary_interactions: CanonicalBinaryInteractions,
    component_names: set[str] | None = None,
) -> dict[BinaryInteractionKey, float]:
    """Validate canonical k_ij data and expand it to a symmetric mapping."""

    if not isinstance(binary_interactions, tuple):
        raise ValueError("canonical binary interactions must be an immutable tuple.")

    expanded: dict[BinaryInteractionKey, float] = {}
    for interaction in binary_interactions:
        if (
            not isinstance(interaction, tuple)
            or len(interaction) != 3
            or not isinstance(interaction[0], str)
            or not isinstance(interaction[1], str)
        ):
            raise ValueError("canonical binary interaction entries are invalid.")
        first_name, second_name, coefficient = interaction
        if not first_name or not second_name or first_name >= second_name:
            raise ValueError(
                "canonical interaction names must be non-empty and ordered."
            )
        if (
            component_names is not None
            and not {first_name, second_name} <= component_names
        ):
            raise ValueError("binary interaction contains an unknown component name.")
        _require_finite(coefficient, f"binary interaction {(first_name, second_name)}")
        if coefficient == 0.0:
            raise ValueError("canonical binary interactions must omit zero values.")
        if (first_name, second_name) in expanded:
            raise ValueError("canonical binary interaction pairs must be unique.")
        expanded[(first_name, second_name)] = coefficient
        expanded[(second_name, first_name)] = coefficient

    if (
        canonicalize_binary_interactions(expanded, component_names)
        != binary_interactions
    ):
        raise ValueError("canonical binary interactions must be sorted.")
    return expanded


def resolve_binary_interaction_metadata(
    binary_interactions: CanonicalBinaryInteractions,
    policy: BinaryInteractionPolicy,
    supplied_pairs: CanonicalBinaryInteractionPairs,
    defaulted_pairs: CanonicalBinaryInteractionPairs,
    component_names: set[str],
) -> dict[BinaryInteractionKey, float]:
    """Validate immutable interaction provenance and expand all mixture pairs."""

    if not isinstance(policy, BinaryInteractionPolicy):
        raise ValueError("binary_interaction_policy must be a BinaryInteractionPolicy.")
    all_pairs = _canonical_component_pairs(component_names)
    if (
        not isinstance(supplied_pairs, tuple)
        or tuple(sorted(supplied_pairs)) != supplied_pairs
    ):
        raise ValueError("supplied binary interaction pairs must be a sorted tuple.")
    if (
        not isinstance(defaulted_pairs, tuple)
        or tuple(sorted(defaulted_pairs)) != defaulted_pairs
    ):
        raise ValueError("defaulted binary interaction pairs must be a sorted tuple.")
    if len(set(supplied_pairs)) != len(supplied_pairs) or len(
        set(defaulted_pairs)
    ) != len(defaulted_pairs):
        raise ValueError("binary interaction provenance pairs must be unique.")
    if set(supplied_pairs) & set(defaulted_pairs):
        raise ValueError(
            "supplied and defaulted binary interaction pairs must not overlap."
        )
    if tuple(sorted((*supplied_pairs, *defaulted_pairs))) != all_pairs:
        raise ValueError(
            "binary interaction provenance must classify every component pair."
        )
    if policy is BinaryInteractionPolicy.REQUIRE_ALL_PAIRS and defaulted_pairs:
        raise ValueError("strict binary interaction policy cannot contain defaults.")

    expanded = canonical_binary_interactions_to_mapping(
        binary_interactions,
        component_names,
    )
    nonzero_pairs = {(first, second) for first, second, _ in binary_interactions}
    if not nonzero_pairs <= set(supplied_pairs):
        raise ValueError("nonzero binary interactions must be marked as supplied.")
    for first_name, second_name in all_pairs:
        coefficient = expanded.get((first_name, second_name), 0.0)
        expanded[(first_name, second_name)] = coefficient
        expanded[(second_name, first_name)] = coefficient
    return expanded


def get_binary_interaction_coefficient(
    first_component_name: str,
    second_component_name: str,
    binary_interactions: BinaryInteractionMapping | None = None,
) -> float:
    """Return k_ij; zero is the default approximation for an omitted pair."""

    if not first_component_name or not second_component_name:
        raise ValueError("component names must not be empty.")
    _validate_binary_interactions(binary_interactions)

    if first_component_name == second_component_name or binary_interactions is None:
        return 0.0
    expected_names = {first_component_name, second_component_name}
    expected_casefold_names = {name.casefold() for name in expected_names}
    if any(
        supplied_name not in expected_names
        and supplied_name.casefold() in expected_casefold_names
        for interaction_names in binary_interactions
        for supplied_name in interaction_names
    ):
        raise ValueError("binary interaction component names are case-sensitive.")
    return binary_interactions.get(
        (first_component_name, second_component_name),
        0.0,
    )


def calculate_pure_component_mixture_parameters(
    mixture_component: MixtureComponent,
    temperature_k: float,
) -> PureComponentMixtureParameters:
    """Calculate temperature-dependent parameters for one mixture component."""

    _require_positive(temperature_k, "temperature_k")
    component = mixture_component.component
    reduced_temperature = calculate_reduced_temperature(
        temperature_k,
        component.critical_temperature_k,
    )
    kappa = calculate_kappa(component.acentric_factor)
    alpha = calculate_alpha(
        temperature_k,
        component.critical_temperature_k,
        component.acentric_factor,
    )
    a_parameter = calculate_a_parameter(
        component.critical_temperature_k,
        component.critical_pressure_pa,
    )
    b_parameter = calculate_b_parameter(
        component.critical_temperature_k,
        component.critical_pressure_pa,
    )
    a_alpha = a_parameter * alpha
    _require_positive(a_alpha, "a_alpha")
    return PureComponentMixtureParameters(
        component=component,
        mole_fraction=mixture_component.mole_fraction,
        temperature_k=temperature_k,
        reduced_temperature=reduced_temperature,
        kappa=kappa,
        alpha=alpha,
        a=a_parameter,
        a_alpha=a_alpha,
        b=b_parameter,
    )


def calculate_component_pair_attraction_parameter(
    component_i: PureComponentMixtureParameters,
    component_j: PureComponentMixtureParameters,
    binary_interactions: BinaryInteractionMapping | None = None,
) -> float:
    """Calculate a_ij in Pa·m^6/mol^2 for one ordered component pair.

    The classical combining rule is
    ``a_ij = sqrt((a_alpha)_i * (a_alpha)_j) * (1 - k_ij)``.
    """

    _validate_single_component_parameter(component_i)
    _validate_single_component_parameter(component_j, component_i.temperature_k)
    interaction = get_binary_interaction_coefficient(
        component_i.component_name,
        component_j.component_name,
        binary_interactions,
    )
    pair_attraction = sqrt(component_i.a_alpha * component_j.a_alpha) * (
        1.0 - interaction
    )
    _require_finite(pair_attraction, "component pair attraction parameter")
    return pair_attraction


def calculate_mixture_a_alpha(
    component_parameters: tuple[PureComponentMixtureParameters, ...],
    binary_interactions: BinaryInteractionMapping | None = None,
) -> float:
    """Return mixture ``a_alpha`` in Pa·m^6/mol^2."""

    validate_component_parameter_provenance(component_parameters)
    names = {parameter.component_name for parameter in component_parameters}
    _validate_binary_interactions(binary_interactions, names)

    terms = []
    for first in component_parameters:
        for second in component_parameters:
            terms.append(
                first.mole_fraction
                * second.mole_fraction
                * calculate_component_pair_attraction_parameter(
                    first,
                    second,
                    binary_interactions,
                )
            )

    a_alpha_mix = fsum(terms)
    _require_positive(a_alpha_mix, "a_alpha_mix")
    return a_alpha_mix


def calculate_mixture_b(
    component_parameters: tuple[PureComponentMixtureParameters, ...],
) -> float:
    """Return mixture co-volume ``b_mix`` in m^3/mol."""

    validate_component_parameter_provenance(component_parameters)
    b_mix = fsum(
        parameter.mole_fraction * parameter.b for parameter in component_parameters
    )
    _require_positive(b_mix, "b_mix")
    return b_mix


def calculate_mixture_A_parameter(
    a_alpha_mix: float,
    pressure_pa: float,
    temperature_k: float,
) -> float:
    """Calculate the dimensionless mixture attraction parameter A."""

    _require_non_negative(pressure_pa, "pressure_pa")
    _require_positive(temperature_k, "temperature_k")
    _require_positive(a_alpha_mix, "a_alpha_mix")
    A_mix = a_alpha_mix * pressure_pa / (UNIVERSAL_GAS_CONSTANT**2 * temperature_k**2)
    _require_non_negative(A_mix, "A_mix")
    return A_mix


def calculate_mixture_B_parameter(
    b_mix: float,
    pressure_pa: float,
    temperature_k: float,
) -> float:
    """Calculate the dimensionless mixture co-volume parameter B."""

    _require_non_negative(pressure_pa, "pressure_pa")
    _require_positive(temperature_k, "temperature_k")
    _require_positive(b_mix, "b_mix")
    B_mix = b_mix * pressure_pa / (UNIVERSAL_GAS_CONSTANT * temperature_k)
    _require_non_negative(B_mix, "B_mix")
    return B_mix


def calculate_peng_robinson_mixture_parameters(
    mixture: FluidMixture,
    temperature_k: float,
    pressure_pa: float,
    binary_interactions: BinaryInteractionMapping | None = None,
    binary_interaction_policy: BinaryInteractionPolicy = (
        BinaryInteractionPolicy.DEFAULT_ZERO
    ),
) -> PengRobinsonMixtureParameters:
    """Calculate all classical Peng-Robinson mixture parameters.

    ``DEFAULT_ZERO`` records every omitted off-diagonal pair as an explicit
    modelling assumption. ``REQUIRE_ALL_PAIRS`` rejects any omitted pair;
    explicitly supplied zero coefficients count as supplied data.
    """

    _require_non_negative(pressure_pa, "pressure_pa")
    component_parameters = tuple(
        calculate_pure_component_mixture_parameters(item, temperature_k)
        for item in mixture.components
    )
    component_names = {parameter.component_name for parameter in component_parameters}
    if not isinstance(binary_interaction_policy, BinaryInteractionPolicy):
        raise ValueError("binary_interaction_policy must be a BinaryInteractionPolicy.")
    supplied_pairs, defaulted_pairs = _resolve_binary_interaction_provenance(
        binary_interactions,
        component_names,
        binary_interaction_policy,
    )
    canonical_binary_interactions = canonicalize_binary_interactions(
        binary_interactions,
        component_names,
    )
    a_alpha_mix = calculate_mixture_a_alpha(
        component_parameters,
        binary_interactions,
    )
    b_mix = calculate_mixture_b(component_parameters)
    A_mix = calculate_mixture_A_parameter(
        a_alpha_mix,
        pressure_pa,
        temperature_k,
    )
    B_mix = calculate_mixture_B_parameter(
        b_mix,
        pressure_pa,
        temperature_k,
    )

    return PengRobinsonMixtureParameters(
        temperature_k=temperature_k,
        pressure_pa=pressure_pa,
        component_parameters=component_parameters,
        a_alpha_mix=a_alpha_mix,
        b_mix=b_mix,
        A_mix=A_mix,
        B_mix=B_mix,
        binary_interactions=canonical_binary_interactions,
        binary_interaction_policy=binary_interaction_policy,
        supplied_binary_interaction_pairs=supplied_pairs,
        defaulted_binary_interaction_pairs=defaulted_pairs,
    )


def calculate_mixture_compressibility_roots(
    mixture: FluidMixture,
    temperature_k: float,
    pressure_pa: float,
    binary_interactions: BinaryInteractionMapping | None = None,
    binary_interaction_policy: BinaryInteractionPolicy = (
        BinaryInteractionPolicy.DEFAULT_ZERO
    ),
) -> tuple[float, ...]:
    """Return dimensionless locally mechanically eligible mixture roots.

    Final mixture phase stability requires component fugacities, which are outside
    this module's scope. Invalid inputs or absence of a confidently stable root
    raise ``ValueError``.
    """

    parameters = calculate_peng_robinson_mixture_parameters(
        mixture,
        temperature_k,
        pressure_pa,
        binary_interactions,
        binary_interaction_policy,
    )
    roots = calculate_compressibility_roots(parameters.A_mix, parameters.B_mix)
    return filter_mechanically_stable_compressibility_roots(
        roots,
        parameters.A_mix,
        parameters.B_mix,
    )
