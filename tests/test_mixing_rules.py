"""Tests for fluid mixtures and classical Peng-Robinson mixing rules."""

from dataclasses import FrozenInstanceError
from math import isfinite
from typing import Any, cast

import pytest

from pvt_phase_simulator.eos import mixing_rules as mixing_rules_module
from pvt_phase_simulator.eos.mixing_rules import (
    BinaryInteractionMapping,
    BinaryInteractionPolicy,
    PureComponentMixtureParameters,
    calculate_component_pair_attraction_parameter,
    calculate_mixture_a_alpha,
    calculate_mixture_A_parameter,
    calculate_mixture_b,
    calculate_mixture_B_parameter,
    calculate_mixture_compressibility_roots,
    calculate_peng_robinson_mixture_parameters,
    calculate_pure_component_mixture_parameters,
    canonical_binary_interactions_to_mapping,
    canonicalize_binary_interactions,
    get_binary_interaction_coefficient,
)
from pvt_phase_simulator.eos.peng_robinson import (
    calculate_compressibility_roots,
    calculate_cubic_coefficients,
    calculate_peng_robinson_parameters,
    filter_mechanically_stable_compressibility_roots,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    Component,
    FluidMixture,
    MixtureComponent,
)

TEMPERATURE_K = 300.0
PRESSURE_PA = 10_000_000.0

# Independently calculated with Decimal at 50-digit precision using the published
# Peng-Robinson equations and the reference data in fluid_models.py.
METHANE_ALPHA = 0.8104699865610172
METHANE_A_ALPHA = 0.20226964650512277
METHANE_B = 2.680175485495062e-05
ETHANE_ALPHA = 1.0092034269136129
ETHANE_A_ALPHA = 0.6103718985846066
ETHANE_B = 4.0537947522064814e-05
CROSS_A_ALPHA = 0.3513683368822083
REFERENCE_A_ALPHA_MIX = 0.30162029915065224
REFERENCE_B_MIX = 3.092261265508488e-05
REFERENCE_A_MIX = 0.4847855728233867
REFERENCE_B_DIMENSIONLESS = 0.12397118160336873
REFERENCE_ROOT = 0.6894757512823003


def _methane_ethane_mixture() -> FluidMixture:
    return FluidMixture(
        components=(
            MixtureComponent(METHANE, 0.70),
            MixtureComponent(ETHANE, 0.30),
        )
    )


def _reference_component_parameters() -> tuple[PureComponentMixtureParameters, ...]:
    return (
        PureComponentMixtureParameters(
            component=METHANE,
            mole_fraction=0.70,
            temperature_k=TEMPERATURE_K,
            reduced_temperature=TEMPERATURE_K / 190.56,
            kappa=0.39157219968,
            alpha=METHANE_ALPHA,
            a=METHANE_A_ALPHA / METHANE_ALPHA,
            a_alpha=METHANE_A_ALPHA,
            b=METHANE_B,
        ),
        PureComponentMixtureParameters(
            component=ETHANE,
            mole_fraction=0.30,
            temperature_k=TEMPERATURE_K,
            reduced_temperature=TEMPERATURE_K / 305.32,
            kappa=0.52467825408,
            alpha=ETHANE_ALPHA,
            a=ETHANE_A_ALPHA / ETHANE_ALPHA,
            a_alpha=ETHANE_A_ALPHA,
            b=ETHANE_B,
        ),
    )


def test_reference_component_properties() -> None:
    assert METHANE.model_dump(exclude={"provenance"}) == {
        "name": "Methane",
        "critical_temperature_k": 190.56,
        "critical_pressure_pa": 4_599_200.0,
        "acentric_factor": 0.011,
    }
    assert ETHANE.model_dump(exclude={"provenance"}) == {
        "name": "Ethane",
        "critical_temperature_k": 305.32,
        "critical_pressure_pa": 4_872_000.0,
        "acentric_factor": 0.099,
    }
    assert PROPANE.model_dump(exclude={"provenance"}) == {
        "name": "Propane",
        "critical_temperature_k": 369.83,
        "critical_pressure_pa": 4_248_000.0,
        "acentric_factor": 0.152,
    }


def test_valid_single_component_mixture() -> None:
    mixture = FluidMixture((MixtureComponent(METHANE, 1.0),))
    assert mixture.components[0].component is METHANE


@pytest.mark.parametrize(
    "components",
    [
        (MixtureComponent(METHANE, 0.7), MixtureComponent(ETHANE, 0.3)),
        (
            MixtureComponent(METHANE, 0.7),
            MixtureComponent(ETHANE, 0.2),
            MixtureComponent(PROPANE, 0.1),
        ),
    ],
)
def test_valid_multicomponent_mixture(
    components: tuple[MixtureComponent, ...],
) -> None:
    assert FluidMixture(components).components == components


def test_empty_mixture_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        FluidMixture(())


def test_zero_total_mole_fraction_is_rejected() -> None:
    with pytest.raises(ValueError, match="total mole fraction"):
        FluidMixture(
            (
                MixtureComponent(METHANE, 0.0),
                MixtureComponent(ETHANE, 0.0),
            )
        )


def test_duplicate_component_is_rejected() -> None:
    with pytest.raises(ValueError, match="unique"):
        FluidMixture(
            (
                MixtureComponent(METHANE, 0.5),
                MixtureComponent(METHANE, 0.5),
            )
        )


def test_duplicate_component_names_differing_only_by_case_are_rejected() -> None:
    lowercase_methane = Component(
        name="methane",
        critical_temperature_k=METHANE.critical_temperature_k,
        critical_pressure_pa=METHANE.critical_pressure_pa,
        acentric_factor=METHANE.acentric_factor,
    )
    with pytest.raises(ValueError, match="unique"):
        FluidMixture(
            (
                MixtureComponent(METHANE, 0.5),
                MixtureComponent(lowercase_methane, 0.5),
            )
        )


@pytest.mark.parametrize("mole_fraction", [-0.01, 1.01])
def test_invalid_individual_mole_fraction_is_rejected(mole_fraction: float) -> None:
    with pytest.raises(ValueError, match="between zero and one"):
        MixtureComponent(METHANE, mole_fraction)


@pytest.mark.parametrize("mole_fraction", [float("nan"), float("inf")])
def test_non_finite_mole_fraction_is_rejected(mole_fraction: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        MixtureComponent(METHANE, mole_fraction)


@pytest.mark.parametrize("methane_fraction", [0.69, 0.71])
def test_invalid_mixture_sum_is_rejected(methane_fraction: float) -> None:
    with pytest.raises(ValueError, match="sum to one"):
        FluidMixture(
            (
                MixtureComponent(METHANE, methane_fraction),
                MixtureComponent(ETHANE, 0.30),
            )
        )


def test_mixture_sum_within_tolerance_is_accepted() -> None:
    mixture = FluidMixture(
        (
            MixtureComponent(METHANE, 0.7),
            MixtureComponent(ETHANE, 0.30000000005),
        )
    )
    assert sum(item.mole_fraction for item in mixture.components) > 1.0


def test_pure_component_parameters_match_independent_reference() -> None:
    methane = calculate_pure_component_mixture_parameters(
        MixtureComponent(METHANE, 0.70), TEMPERATURE_K
    )
    ethane = calculate_pure_component_mixture_parameters(
        MixtureComponent(ETHANE, 0.30), TEMPERATURE_K
    )
    assert methane.alpha == pytest.approx(METHANE_ALPHA, rel=1e-13)
    assert methane.a_alpha == pytest.approx(METHANE_A_ALPHA, rel=1e-13)
    assert methane.b == pytest.approx(METHANE_B, rel=1e-13)
    assert ethane.alpha == pytest.approx(ETHANE_ALPHA, rel=1e-13)
    assert ethane.a_alpha == pytest.approx(ETHANE_A_ALPHA, rel=1e-13)
    assert ethane.b == pytest.approx(ETHANE_B, rel=1e-13)


def test_binary_interaction_defaults_and_symmetric_lookup() -> None:
    interactions = {("Methane", "Ethane"): 0.02, ("Ethane", "Methane"): 0.02}
    assert get_binary_interaction_coefficient("Methane", "Ethane") == 0.0
    assert get_binary_interaction_coefficient("Methane", "Methane", interactions) == 0.0
    assert get_binary_interaction_coefficient("Methane", "Ethane", interactions) == 0.02
    assert get_binary_interaction_coefficient("Ethane", "Methane", interactions) == 0.02


def test_authoritative_pair_attraction_matches_reference_and_self_limit() -> None:
    methane, ethane = _reference_component_parameters()
    assert calculate_component_pair_attraction_parameter(
        methane, methane
    ) == pytest.approx(methane.a_alpha)
    assert calculate_component_pair_attraction_parameter(
        methane, ethane
    ) == pytest.approx(CROSS_A_ALPHA, rel=1e-13)
    assert calculate_component_pair_attraction_parameter(
        methane, ethane
    ) == pytest.approx(
        calculate_component_pair_attraction_parameter(ethane, methane),
        rel=1e-15,
    )


def test_authoritative_pair_attraction_applies_nonzero_interaction() -> None:
    methane, ethane = _reference_component_parameters()
    interactions = {("Methane", "Ethane"): 0.05, ("Ethane", "Methane"): 0.05}
    assert calculate_component_pair_attraction_parameter(
        methane,
        ethane,
        interactions,
    ) == pytest.approx(CROSS_A_ALPHA * 0.95, rel=1e-13)


def test_mixture_aggregation_uses_authoritative_pair_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parameters = _reference_component_parameters()
    original = mixing_rules_module.calculate_component_pair_attraction_parameter
    calls: list[tuple[str, str]] = []

    def recording_pair_attraction(
        component_i: PureComponentMixtureParameters,
        component_j: PureComponentMixtureParameters,
        binary_interactions: BinaryInteractionMapping | None = None,
    ) -> float:
        calls.append((component_i.component_name, component_j.component_name))
        return original(component_i, component_j, binary_interactions)

    monkeypatch.setattr(
        mixing_rules_module,
        "calculate_component_pair_attraction_parameter",
        recording_pair_attraction,
    )
    assert calculate_mixture_a_alpha(parameters) == pytest.approx(
        REFERENCE_A_ALPHA_MIX,
        rel=1e-13,
    )
    assert calls == [
        ("Methane", "Methane"),
        ("Methane", "Ethane"),
        ("Ethane", "Methane"),
        ("Ethane", "Ethane"),
    ]


def test_mixture_parameters_store_immutable_canonical_interactions() -> None:
    interactions = {("Methane", "Ethane"): 0.02, ("Ethane", "Methane"): 0.02}
    result = calculate_peng_robinson_mixture_parameters(
        _methane_ethane_mixture(), TEMPERATURE_K, PRESSURE_PA, interactions
    )
    interactions[("Methane", "Ethane")] = 0.05
    interactions[("Ethane", "Methane")] = 0.05

    assert result.binary_interactions == (("Ethane", "Methane", 0.02),)


def test_default_binary_interactions_have_empty_canonical_representation() -> None:
    result = calculate_peng_robinson_mixture_parameters(
        _methane_ethane_mixture(), TEMPERATURE_K, PRESSURE_PA
    )
    assert result.binary_interactions == ()


def test_empty_and_zero_interactions_canonicalize_to_empty_tuple() -> None:
    zeros = {
        ("Methane", "Methane"): 0.0,
        ("Methane", "Ethane"): 0.0,
        ("Ethane", "Methane"): 0.0,
    }
    assert canonicalize_binary_interactions(None) == ()
    assert canonicalize_binary_interactions({}) == ()
    assert canonicalize_binary_interactions(zeros) == ()


def test_canonical_interactions_are_order_independent_and_sorted() -> None:
    forward = {
        ("Methane", "Propane"): 0.01,
        ("Propane", "Methane"): 0.01,
        ("Ethane", "Methane"): 0.02,
        ("Methane", "Ethane"): 0.02,
    }
    reversed_insertion = dict(reversed(tuple(forward.items())))
    expected = (
        ("Ethane", "Methane", 0.02),
        ("Methane", "Propane", 0.01),
    )
    assert canonicalize_binary_interactions(forward) == expected
    assert canonicalize_binary_interactions(reversed_insertion) == expected


def test_canonical_interactions_round_trip_to_validated_symmetric_mapping() -> None:
    original = {
        ("Methane", "Ethane"): 0.02,
        ("Ethane", "Methane"): 0.02,
    }
    canonical = canonicalize_binary_interactions(
        original,
        {"Methane", "Ethane"},
    )
    expanded = canonical_binary_interactions_to_mapping(
        canonical,
        {"Methane", "Ethane"},
    )
    assert canonicalize_binary_interactions(expanded) == canonical
    assert get_binary_interaction_coefficient(
        "Methane", "Ethane", expanded
    ) == pytest.approx(0.02)
    assert get_binary_interaction_coefficient(
        "Ethane", "Methane", expanded
    ) == pytest.approx(0.02)


@pytest.mark.parametrize(
    ("canonical", "message"),
    [
        ([], "immutable tuple"),
        ((("Methane", "Ethane"),), "entries"),
        ((("Methane", "Methane", 0.01),), "ordered"),
        ((("Ethane", "Methane", 0.0),), "omit zero"),
        ((("Ethane", "Methane", float("inf")),), "finite"),
        (
            (
                ("Ethane", "Methane", 0.02),
                ("Ethane", "Methane", 0.02),
            ),
            "unique",
        ),
        (
            (
                ("Methane", "Propane", 0.01),
                ("Ethane", "Methane", 0.02),
            ),
            "sorted",
        ),
    ],
)
def test_canonical_tuple_reconstruction_rejects_invalid_data(
    canonical: Any,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        canonical_binary_interactions_to_mapping(canonical)


def test_canonical_tuple_reconstruction_rejects_unknown_component() -> None:
    canonical = (("Methane", "Unknown", 0.01),)
    with pytest.raises(ValueError, match="unknown"):
        canonical_binary_interactions_to_mapping(
            canonical,
            {"Methane", "Ethane"},
        )


@pytest.mark.parametrize(
    ("interactions", "component_names", "message"),
    [
        ({("Methane", "Ethane"): 0.02}, None, "symmetric"),
        ({("Methane", "Methane"): 0.01}, None, "diagonal"),
        (
            {
                ("Methane", "Ethane"): float("inf"),
                ("Ethane", "Methane"): float("inf"),
            },
            None,
            "finite",
        ),
        (
            {("Methane", "Unknown"): 0.0, ("Unknown", "Methane"): 0.0},
            {"Methane", "Ethane"},
            "unknown",
        ),
    ],
)
def test_canonicalization_directly_rejects_invalid_interactions(
    interactions: BinaryInteractionMapping,
    component_names: set[str] | None,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        canonicalize_binary_interactions(interactions, component_names)


def test_canonicalization_directly_rejects_malformed_key() -> None:
    malformed = cast(BinaryInteractionMapping, cast(Any, {"Methane-Ethane": 0.0}))
    with pytest.raises(ValueError, match="keys"):
        canonicalize_binary_interactions(malformed)


@pytest.mark.parametrize(
    "interactions",
    [
        {("Methane", "Ethane"): 0.02},
        {("Methane", "Ethane"): 0.02, ("Ethane", "Methane"): 0.03},
        {("Methane", "Methane"): 0.01},
        {("Methane", "Ethane"): float("nan"), ("Ethane", "Methane"): float("nan")},
    ],
)
def test_invalid_binary_interactions_are_rejected(
    interactions: BinaryInteractionMapping,
) -> None:
    with pytest.raises(ValueError):
        get_binary_interaction_coefficient("Methane", "Ethane", interactions)


def test_invalid_binary_interaction_key_is_rejected() -> None:
    malformed = cast(BinaryInteractionMapping, cast(Any, {"Methane-Ethane": 0.0}))
    with pytest.raises(ValueError, match="keys"):
        get_binary_interaction_coefficient("Methane", "Ethane", malformed)


def test_nonzero_interaction_changes_attraction_but_not_covolume() -> None:
    parameters = _reference_component_parameters()
    zero_attraction = calculate_mixture_a_alpha(parameters)
    interactions = {("Methane", "Ethane"): 0.05, ("Ethane", "Methane"): 0.05}
    corrected_attraction = calculate_mixture_a_alpha(parameters, interactions)
    assert corrected_attraction < zero_attraction
    assert calculate_mixture_b(parameters) == pytest.approx(REFERENCE_B_MIX)


def test_independent_two_component_mixing_reference() -> None:
    parameters = _reference_component_parameters()
    assert calculate_mixture_a_alpha(parameters) == pytest.approx(
        REFERENCE_A_ALPHA_MIX, rel=1e-13
    )
    assert calculate_mixture_b(parameters) == pytest.approx(REFERENCE_B_MIX, rel=1e-13)
    assert calculate_mixture_A_parameter(
        REFERENCE_A_ALPHA_MIX, PRESSURE_PA, TEMPERATURE_K
    ) == pytest.approx(REFERENCE_A_MIX, rel=1e-13)
    assert calculate_mixture_B_parameter(
        REFERENCE_B_MIX, PRESSURE_PA, TEMPERATURE_K
    ) == pytest.approx(REFERENCE_B_DIMENSIONLESS, rel=1e-13)


def test_quadratic_mixing_rule_contains_both_cross_terms() -> None:
    explicit_double_sum = (
        0.70**2 * METHANE_A_ALPHA
        + 2.0 * 0.70 * 0.30 * CROSS_A_ALPHA
        + 0.30**2 * ETHANE_A_ALPHA
    )
    assert explicit_double_sum == pytest.approx(REFERENCE_A_ALPHA_MIX, rel=1e-13)
    assert calculate_mixture_a_alpha(
        _reference_component_parameters()
    ) == pytest.approx(explicit_double_sum, rel=1e-13)


def test_orchestration_matches_independent_reference() -> None:
    result = calculate_peng_robinson_mixture_parameters(
        _methane_ethane_mixture(), TEMPERATURE_K, PRESSURE_PA
    )
    assert result.a_alpha_mix == pytest.approx(REFERENCE_A_ALPHA_MIX, rel=1e-13)
    assert result.b_mix == pytest.approx(REFERENCE_B_MIX, rel=1e-13)
    assert result.A_mix == pytest.approx(REFERENCE_A_MIX, rel=1e-13)
    assert result.B_mix == pytest.approx(REFERENCE_B_DIMENSIONLESS, rel=1e-13)


def test_orchestration_matches_smaller_functions() -> None:
    mixture = _methane_ethane_mixture()
    component_parameters = tuple(
        calculate_pure_component_mixture_parameters(item, TEMPERATURE_K)
        for item in mixture.components
    )
    a_alpha_mix = calculate_mixture_a_alpha(component_parameters)
    b_mix = calculate_mixture_b(component_parameters)
    result = calculate_peng_robinson_mixture_parameters(
        mixture, TEMPERATURE_K, PRESSURE_PA
    )

    assert result.component_parameters == component_parameters
    assert result.a_alpha_mix == a_alpha_mix
    assert result.b_mix == b_mix
    assert result.A_mix == calculate_mixture_A_parameter(
        a_alpha_mix, PRESSURE_PA, TEMPERATURE_K
    )
    assert result.B_mix == calculate_mixture_B_parameter(
        b_mix, PRESSURE_PA, TEMPERATURE_K
    )


def test_reference_cubic_coefficients_and_root() -> None:
    coefficients = calculate_cubic_coefficients(
        REFERENCE_A_MIX, REFERENCE_B_DIMENSIONLESS
    )
    assert coefficients.z2 == pytest.approx(-0.8760288183966313, rel=1e-13)
    assert coefficients.z1 == pytest.approx(0.19073664801224296, rel=1e-13)
    assert coefficients.z0 == pytest.approx(-0.04282529144512353, rel=1e-13)

    roots = calculate_mixture_compressibility_roots(
        _methane_ethane_mixture(), TEMPERATURE_K, PRESSURE_PA
    )
    assert roots == pytest.approx((REFERENCE_ROOT,), rel=1e-12)
    for root in roots:
        residual = (
            coefficients.z3 * root**3
            + coefficients.z2 * root**2
            + coefficients.z1 * root
            + coefficients.z0
        )
        assert abs(residual) < 1e-12
        assert root > REFERENCE_B_DIMENSIONLESS


def test_zero_pressure_has_ideal_gas_root() -> None:
    result = calculate_peng_robinson_mixture_parameters(
        _methane_ethane_mixture(), TEMPERATURE_K, 0.0
    )
    assert result.A_mix == 0.0
    assert result.B_mix == 0.0
    assert calculate_mixture_compressibility_roots(
        _methane_ethane_mixture(), TEMPERATURE_K, 0.0
    ) == pytest.approx((1.0,))


def test_pure_methane_limit_matches_pure_component_api() -> None:
    mixture = FluidMixture((MixtureComponent(METHANE, 1.0),))
    mixed = calculate_peng_robinson_mixture_parameters(
        mixture, TEMPERATURE_K, PRESSURE_PA
    )
    pure = calculate_peng_robinson_parameters(
        TEMPERATURE_K,
        PRESSURE_PA,
        METHANE.critical_temperature_k,
        METHANE.critical_pressure_pa,
        METHANE.acentric_factor,
    )
    assert mixed.a_alpha_mix == pytest.approx(pure.a * pure.alpha)
    assert mixed.b_mix == pytest.approx(pure.b)
    assert mixed.A_mix == pytest.approx(pure.A)
    assert mixed.B_mix == pytest.approx(pure.B)
    pure_roots = calculate_compressibility_roots(pure.A, pure.B)
    mechanically_stable_pure_roots = filter_mechanically_stable_compressibility_roots(
        pure_roots, pure.A, pure.B
    )
    assert calculate_mixture_compressibility_roots(
        mixture, TEMPERATURE_K, PRESSURE_PA
    ) == pytest.approx(mechanically_stable_pure_roots)


@pytest.mark.parametrize(
    ("function", "arguments"),
    [
        (
            calculate_pure_component_mixture_parameters,
            (MixtureComponent(METHANE, 1.0), 0.0),
        ),
        (calculate_mixture_A_parameter, (1.0, -1.0, TEMPERATURE_K)),
        (calculate_mixture_A_parameter, (1.0, PRESSURE_PA, 0.0)),
        (calculate_mixture_B_parameter, (1.0, -1.0, TEMPERATURE_K)),
        (calculate_mixture_B_parameter, (1.0, PRESSURE_PA, float("inf"))),
    ],
)
def test_invalid_scalar_inputs_are_rejected(
    function: Any,
    arguments: tuple[Any, ...],
) -> None:
    with pytest.raises(ValueError):
        function(*arguments)


def test_empty_component_parameter_tuple_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        calculate_mixture_a_alpha(())
    with pytest.raises(ValueError, match="must not be empty"):
        calculate_mixture_b(())


def test_all_orchestration_results_are_finite() -> None:
    result = calculate_peng_robinson_mixture_parameters(
        _methane_ethane_mixture(), TEMPERATURE_K, PRESSURE_PA
    )
    values = (result.a_alpha_mix, result.b_mix, result.A_mix, result.B_mix)
    assert all(isfinite(value) for value in values)


def test_default_zero_policy_records_omitted_pairs() -> None:
    result = calculate_peng_robinson_mixture_parameters(
        _methane_ethane_mixture(), TEMPERATURE_K, PRESSURE_PA
    )
    assert result.binary_interaction_policy is BinaryInteractionPolicy.DEFAULT_ZERO
    assert result.supplied_binary_interaction_pairs == ()
    assert result.defaulted_binary_interaction_pairs == (("Ethane", "Methane"),)


def test_explicit_zero_counts_as_supplied_interaction_data() -> None:
    interactions = {("Methane", "Ethane"): 0.0, ("Ethane", "Methane"): 0.0}
    result = calculate_peng_robinson_mixture_parameters(
        _methane_ethane_mixture(),
        TEMPERATURE_K,
        PRESSURE_PA,
        interactions,
        BinaryInteractionPolicy.REQUIRE_ALL_PAIRS,
    )
    assert result.binary_interactions == ()
    assert result.supplied_binary_interaction_pairs == (("Ethane", "Methane"),)
    assert result.defaulted_binary_interaction_pairs == ()


def test_strict_incomplete_binary_mixture_is_rejected() -> None:
    with pytest.raises(ValueError, match="Ethane/Methane"):
        calculate_peng_robinson_mixture_parameters(
            _methane_ethane_mixture(),
            TEMPERATURE_K,
            PRESSURE_PA,
            binary_interaction_policy=BinaryInteractionPolicy.REQUIRE_ALL_PAIRS,
        )


def test_strict_complete_ternary_mixture_records_all_pairs_as_supplied() -> None:
    mixture = FluidMixture(
        (
            MixtureComponent(METHANE, 0.5),
            MixtureComponent(ETHANE, 0.3),
            MixtureComponent(PROPANE, 0.2),
        )
    )
    interactions = {
        ("Methane", "Ethane"): 0.0,
        ("Ethane", "Methane"): 0.0,
        ("Methane", "Propane"): 0.01,
        ("Propane", "Methane"): 0.01,
        ("Ethane", "Propane"): 0.02,
        ("Propane", "Ethane"): 0.02,
    }
    result = calculate_peng_robinson_mixture_parameters(
        mixture,
        TEMPERATURE_K,
        PRESSURE_PA,
        interactions,
        BinaryInteractionPolicy.REQUIRE_ALL_PAIRS,
    )
    assert len(result.supplied_binary_interaction_pairs) == 3
    assert result.defaulted_binary_interaction_pairs == ()


def test_strict_interaction_policy_lists_every_missing_ternary_pair() -> None:
    mixture = FluidMixture(
        (
            MixtureComponent(METHANE, 0.5),
            MixtureComponent(ETHANE, 0.3),
            MixtureComponent(PROPANE, 0.2),
        )
    )
    with pytest.raises(ValueError, match="Ethane/Propane.*Methane/Propane"):
        calculate_peng_robinson_mixture_parameters(
            mixture,
            TEMPERATURE_K,
            PRESSURE_PA,
            {("Methane", "Ethane"): 0.0, ("Ethane", "Methane"): 0.0},
            BinaryInteractionPolicy.REQUIRE_ALL_PAIRS,
        )


def test_strict_ternary_mixture_missing_one_pair_is_rejected() -> None:
    mixture = FluidMixture(
        (
            MixtureComponent(METHANE, 0.5),
            MixtureComponent(ETHANE, 0.3),
            MixtureComponent(PROPANE, 0.2),
        )
    )
    interactions = {
        ("Methane", "Ethane"): 0.01,
        ("Ethane", "Methane"): 0.01,
        ("Methane", "Propane"): 0.02,
        ("Propane", "Methane"): 0.02,
    }
    with pytest.raises(ValueError, match="Ethane/Propane"):
        calculate_peng_robinson_mixture_parameters(
            mixture,
            TEMPERATURE_K,
            PRESSURE_PA,
            interactions,
            BinaryInteractionPolicy.REQUIRE_ALL_PAIRS,
        )


def test_interaction_provenance_is_immutable_after_caller_mutation() -> None:
    interactions = {("Methane", "Ethane"): 0.02, ("Ethane", "Methane"): 0.02}
    result = calculate_peng_robinson_mixture_parameters(
        _methane_ethane_mixture(), TEMPERATURE_K, PRESSURE_PA, interactions
    )
    interactions[("Methane", "Ethane")] = 0.5
    interactions[("Ethane", "Methane")] = 0.5
    assert result.binary_interactions == (("Ethane", "Methane", 0.02),)
    assert result.supplied_binary_interaction_pairs == (("Ethane", "Methane"),)


def test_stored_interaction_policy_is_immutable() -> None:
    result = calculate_peng_robinson_mixture_parameters(
        _methane_ethane_mixture(), TEMPERATURE_K, PRESSURE_PA
    )
    with pytest.raises(FrozenInstanceError):
        result.binary_interaction_policy = (  # type: ignore[misc]
            BinaryInteractionPolicy.REQUIRE_ALL_PAIRS
        )


@pytest.mark.parametrize("wrong_name", ["methane", "METHANE", "MethanE"])
def test_interaction_names_require_exact_canonical_case(wrong_name: str) -> None:
    interactions = {
        (wrong_name, "Ethane"): 0.02,
        ("Ethane", wrong_name): 0.02,
    }
    with pytest.raises(ValueError, match="case-sensitive"):
        calculate_peng_robinson_mixture_parameters(
            _methane_ethane_mixture(),
            TEMPERATURE_K,
            PRESSURE_PA,
            interactions,
        )


def test_public_interaction_lookup_rejects_likely_case_mismatch() -> None:
    interactions = {("methane", "Ethane"): 0.02, ("Ethane", "methane"): 0.02}
    with pytest.raises(ValueError, match="case-sensitive"):
        get_binary_interaction_coefficient("Methane", "Ethane", interactions)
