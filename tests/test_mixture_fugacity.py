"""Tests for component fugacity coefficients in Peng-Robinson mixtures."""

from dataclasses import FrozenInstanceError, replace
from math import exp, fsum, isfinite, log, nextafter, sqrt

import pytest
from pydantic import ValidationError

from pvt_phase_simulator.eos import mixing_rules as mixing_rules_module
from pvt_phase_simulator.eos.mixing_rules import (
    BinaryInteractionMapping,
    BinaryInteractionPolicy,
    PengRobinsonMixtureParameters,
    PureComponentMixtureParameters,
    calculate_mixture_a_alpha,
    calculate_mixture_A_parameter,
    calculate_mixture_b,
    calculate_mixture_B_parameter,
    calculate_mixture_compressibility_roots,
    calculate_peng_robinson_mixture_parameters,
)
from pvt_phase_simulator.eos.mixture_fugacity import (
    MixtureRootFugacityResult,
    calculate_component_attraction_sum,
    calculate_component_fugacity_coefficient,
    calculate_component_pair_attraction_parameter,
    calculate_log_component_fugacity_coefficient,
    calculate_mixture_fugacity_coefficients,
    calculate_mixture_root_fugacity_result,
)
from pvt_phase_simulator.eos.peng_robinson import (
    LOW_PRESSURE_ROOT_OFFSET_THRESHOLD,
    MechanicalStabilityClassification,
    calculate_compressibility_roots,
    calculate_log_fugacity_coefficient,
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
REFERENCE_ROOT = 0.6894757512823003
REFERENCE_CROSS_ATTRACTION = 0.3513683368822083
REFERENCE_METHANE_ATTRACTION_SUM = 0.24699925361824843
REFERENCE_ETHANE_ATTRACTION_SUM = 0.4290694053929278
REFERENCE_METHANE_LOG_PHI = -0.16596256167249822
REFERENCE_METHANE_PHI = 0.8470779467773538
REFERENCE_ETHANE_LOG_PHI = -0.7659076856102491
REFERENCE_ETHANE_PHI = 0.4649117456959447
LOW_PRESSURE_PA = 1.0
LOW_PRESSURE_ROOT = 0.9999999639185609
LOW_PRESSURE_METHANE_LOG_PHI = -2.017535811566188e-08
LOW_PRESSURE_METHANE_PHI = 0.9999999798246421
LOW_PRESSURE_ETHANE_LOG_PHI = -7.319562804711643e-08
LOW_PRESSURE_ETHANE_PHI = 0.9999999268043746
CONSISTENCY_TEST_PRESSURE_PA = 1e-10

# Independent 60-digit Decimal evaluation of the published PR mixing and
# component-fugacity equations, using the project's decimal input properties.
LOW_PRESSURE_DECIMAL_LOG_PHI = {
    100.0: (-2.0175330140590654e-6, -7.319568444391803e-6),
    1.0: (-2.0175358115661878e-8, -7.319562804711643e-8),
    0.1: (-2.0175358369979786e-9, -7.319562753441864e-9),
    1e-3: (-2.0175358397954755e-11, -7.319562747802189e-11),
}


def _mixture() -> FluidMixture:
    return FluidMixture(
        (
            MixtureComponent(METHANE, 0.70),
            MixtureComponent(ETHANE, 0.30),
        )
    )


def _parameters(
    interactions: dict[tuple[str, str], float] | None = None,
) -> PengRobinsonMixtureParameters:
    return calculate_peng_robinson_mixture_parameters(
        _mixture(),
        TEMPERATURE_K,
        PRESSURE_PA,
        interactions,
    )


def test_component_pair_attraction_uses_self_and_cross_terms() -> None:
    parameters = _parameters().component_parameters
    methane, ethane = parameters
    assert calculate_component_pair_attraction_parameter(
        methane, methane
    ) == pytest.approx(methane.a_alpha)
    assert calculate_component_pair_attraction_parameter(
        ethane, ethane
    ) == pytest.approx(ethane.a_alpha)
    assert calculate_component_pair_attraction_parameter(
        methane, ethane
    ) == pytest.approx(REFERENCE_CROSS_ATTRACTION, rel=1e-13)


def test_component_pair_attraction_is_symmetric() -> None:
    methane, ethane = _parameters().component_parameters
    interactions = {("Methane", "Ethane"): 0.03, ("Ethane", "Methane"): 0.03}
    assert calculate_component_pair_attraction_parameter(
        methane, ethane, interactions
    ) == pytest.approx(
        calculate_component_pair_attraction_parameter(ethane, methane, interactions)
    )


def test_component_attraction_sums_match_independent_reference() -> None:
    parameters = _parameters().component_parameters
    methane, ethane = parameters
    assert calculate_component_attraction_sum(methane, parameters) == pytest.approx(
        REFERENCE_METHANE_ATTRACTION_SUM, rel=1e-13
    )
    assert calculate_component_attraction_sum(ethane, parameters) == pytest.approx(
        REFERENCE_ETHANE_ATTRACTION_SUM, rel=1e-13
    )


def test_fugacity_row_sum_uses_authoritative_pair_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parameters = _parameters().component_parameters
    methane = parameters[0]
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
    assert calculate_component_attraction_sum(methane, parameters) == pytest.approx(
        REFERENCE_METHANE_ATTRACTION_SUM,
        rel=1e-13,
    )
    assert calls[-2:] == [("Methane", "Methane"), ("Methane", "Ethane")]


def test_legacy_pair_attraction_api_delegates_to_authoritative_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    methane, ethane = _parameters().component_parameters

    def sentinel_pair_attraction(
        component_i: PureComponentMixtureParameters,
        component_j: PureComponentMixtureParameters,
        binary_interactions: BinaryInteractionMapping | None = None,
    ) -> float:
        del component_i, component_j, binary_interactions
        return 0.125

    monkeypatch.setattr(
        mixing_rules_module,
        "calculate_component_pair_attraction_parameter",
        sentinel_pair_attraction,
    )
    assert calculate_component_pair_attraction_parameter(methane, ethane) == 0.125


def test_mixture_fugacity_matches_independent_reference_case() -> None:
    parameters = _parameters()
    roots = calculate_mixture_compressibility_roots(
        _mixture(), TEMPERATURE_K, PRESSURE_PA
    )
    assert roots == pytest.approx((REFERENCE_ROOT,), rel=1e-12)

    results = calculate_mixture_fugacity_coefficients(parameters, roots[0])
    assert results[0].log_fugacity_coefficient == pytest.approx(
        REFERENCE_METHANE_LOG_PHI, rel=1e-12
    )
    assert results[0].fugacity_coefficient == pytest.approx(
        REFERENCE_METHANE_PHI, rel=1e-12
    )
    assert results[1].log_fugacity_coefficient == pytest.approx(
        REFERENCE_ETHANE_LOG_PHI, rel=1e-12
    )
    assert results[1].fugacity_coefficient == pytest.approx(
        REFERENCE_ETHANE_PHI, rel=1e-12
    )


def test_calculated_cubic_root_is_accepted() -> None:
    parameters = _parameters()
    root = calculate_mixture_compressibility_roots(
        _mixture(), TEMPERATURE_K, PRESSURE_PA
    )[0]
    assert calculate_mixture_fugacity_coefficients(parameters, root)


def test_arbitrary_non_root_is_rejected() -> None:
    with pytest.raises(ValueError, match="does not satisfy"):
        calculate_mixture_fugacity_coefficients(_parameters(), 5.0)


def test_slightly_rounded_cubic_root_is_accepted() -> None:
    rounded_root = round(REFERENCE_ROOT, 10)
    assert calculate_mixture_fugacity_coefficients(_parameters(), rounded_root)


def test_value_outside_cubic_residual_tolerance_is_rejected() -> None:
    outside_tolerance = REFERENCE_ROOT + 1e-8
    with pytest.raises(ValueError, match="residual tolerance"):
        calculate_mixture_fugacity_coefficients(_parameters(), outside_tolerance)


def test_all_genuine_three_root_candidates_are_accepted() -> None:
    parameters = calculate_peng_robinson_mixture_parameters(
        _mixture(), 190.0, 1_000_000.0
    )
    roots = calculate_compressibility_roots(parameters.A_mix, parameters.B_mix)
    assert len(roots) == 3

    for root in roots:
        assert calculate_mixture_fugacity_coefficients(parameters, root)


def test_all_results_are_finite_positive_and_ordered() -> None:
    parameters = _parameters()
    results = calculate_mixture_fugacity_coefficients(parameters, REFERENCE_ROOT)
    assert tuple(result.component_name for result in results) == (
        "Methane",
        "Ethane",
    )
    assert tuple(result.mole_fraction for result in results) == (0.70, 0.30)
    for result in results:
        assert isfinite(result.log_fugacity_coefficient)
        assert isfinite(result.fugacity_coefficient)
        assert result.fugacity_coefficient > 0.0
        assert result.fugacity_coefficient == pytest.approx(
            exp(result.log_fugacity_coefficient), rel=1e-14
        )


def test_single_component_functions_match_all_component_result() -> None:
    parameters = _parameters()
    methane = parameters.component_parameters[0]
    all_results = calculate_mixture_fugacity_coefficients(parameters, REFERENCE_ROOT)
    log_phi = calculate_log_component_fugacity_coefficient(
        methane, parameters, REFERENCE_ROOT
    )
    phi = calculate_component_fugacity_coefficient(methane, parameters, REFERENCE_ROOT)
    assert log_phi == all_results[0].log_fugacity_coefficient
    assert phi == all_results[0].fugacity_coefficient


def test_binary_interaction_changes_component_fugacity_coefficients() -> None:
    interactions = {("Methane", "Ethane"): 0.05, ("Ethane", "Methane"): 0.05}
    zero_parameters = _parameters()
    corrected_parameters = _parameters(interactions)
    zero_root = calculate_mixture_compressibility_roots(
        _mixture(), TEMPERATURE_K, PRESSURE_PA
    )[0]
    corrected_root = calculate_mixture_compressibility_roots(
        _mixture(), TEMPERATURE_K, PRESSURE_PA, interactions
    )[0]
    zero_results = calculate_mixture_fugacity_coefficients(zero_parameters, zero_root)
    corrected_results = calculate_mixture_fugacity_coefficients(
        corrected_parameters, corrected_root, interactions
    )
    assert corrected_results[0].fugacity_coefficient != pytest.approx(
        zero_results[0].fugacity_coefficient
    )
    assert corrected_results[1].fugacity_coefficient != pytest.approx(
        zero_results[1].fugacity_coefficient
    )


def test_asymmetric_binary_interaction_is_rejected() -> None:
    asymmetric = {("Methane", "Ethane"): 0.02}
    with pytest.raises(ValueError, match="symmetric"):
        calculate_mixture_fugacity_coefficients(
            _parameters(), REFERENCE_ROOT, asymmetric
        )


def test_interactions_must_match_parameters_used_for_mixing() -> None:
    interactions = {("Methane", "Ethane"): 0.02, ("Ethane", "Methane"): 0.02}
    with pytest.raises(ValueError, match="do not match"):
        calculate_mixture_fugacity_coefficients(
            _parameters(), REFERENCE_ROOT, interactions
        )


def test_three_component_interactions_cannot_be_replaced_at_equal_attraction() -> None:
    mixture = FluidMixture(
        (
            MixtureComponent(METHANE, 0.50),
            MixtureComponent(ETHANE, 0.30),
            MixtureComponent(PROPANE, 0.20),
        )
    )
    base = {
        ("Methane", "Ethane"): 0.02,
        ("Ethane", "Methane"): 0.02,
        ("Methane", "Propane"): 0.01,
        ("Propane", "Methane"): 0.01,
        ("Ethane", "Propane"): 0.03,
        ("Propane", "Ethane"): 0.03,
    }
    parameters = calculate_peng_robinson_mixture_parameters(
        mixture, TEMPERATURE_K, PRESSURE_PA, base
    )
    methane, ethane, propane = parameters.component_parameters
    methane_ethane_weight = (
        2.0
        * methane.mole_fraction
        * ethane.mole_fraction
        * sqrt(methane.a_alpha * ethane.a_alpha)
    )
    methane_propane_weight = (
        2.0
        * methane.mole_fraction
        * propane.mole_fraction
        * sqrt(methane.a_alpha * propane.a_alpha)
    )
    methane_ethane_delta = 0.01
    methane_propane_delta = (
        -methane_ethane_weight * methane_ethane_delta / methane_propane_weight
    )
    altered = {
        ("Methane", "Ethane"): 0.02 + methane_ethane_delta,
        ("Ethane", "Methane"): 0.02 + methane_ethane_delta,
        ("Methane", "Propane"): 0.01 + methane_propane_delta,
        ("Propane", "Methane"): 0.01 + methane_propane_delta,
        ("Ethane", "Propane"): 0.03,
        ("Propane", "Ethane"): 0.03,
    }
    altered_a_alpha_mix = calculate_mixture_a_alpha(
        parameters.component_parameters, altered
    )
    assert altered_a_alpha_mix == pytest.approx(parameters.a_alpha_mix, rel=1e-14)

    root = calculate_mixture_compressibility_roots(
        mixture, TEMPERATURE_K, PRESSURE_PA, base
    )[0]
    with pytest.raises(ValueError, match="do not match"):
        calculate_mixture_fugacity_coefficients(parameters, root, altered)


def test_three_component_fugacity_regression_is_unchanged() -> None:
    """The authoritative pair helper preserves the existing three-fluid result."""

    mixture = FluidMixture(
        (
            MixtureComponent(METHANE, 0.50),
            MixtureComponent(ETHANE, 0.30),
            MixtureComponent(PROPANE, 0.20),
        )
    )
    interactions = {
        ("Methane", "Ethane"): 0.02,
        ("Ethane", "Methane"): 0.02,
        ("Methane", "Propane"): 0.01,
        ("Propane", "Methane"): 0.01,
        ("Ethane", "Propane"): 0.03,
        ("Propane", "Ethane"): 0.03,
    }
    parameters = calculate_peng_robinson_mixture_parameters(
        mixture,
        TEMPERATURE_K,
        PRESSURE_PA,
        interactions,
    )
    root = calculate_mixture_compressibility_roots(
        mixture,
        TEMPERATURE_K,
        PRESSURE_PA,
        interactions,
    )[0]
    results = calculate_mixture_fugacity_coefficients(parameters, root)

    assert root == pytest.approx(0.457604183307468, abs=1e-14)
    assert tuple(
        result.log_fugacity_coefficient for result in results
    ) == pytest.approx(
        (0.017815239519452852, -0.9284362360321922, -1.6962978201699401),
        abs=1e-13,
    )
    assert tuple(result.fugacity_coefficient for result in results) == pytest.approx(
        (1.0179748774861577, 0.39517118191128936, 0.18336110479973672),
        abs=1e-13,
    )


def test_zero_pressure_is_ideal_gas_limit() -> None:
    parameters = calculate_peng_robinson_mixture_parameters(
        _mixture(), TEMPERATURE_K, 0.0
    )
    results = calculate_mixture_fugacity_coefficients(parameters, 1.0)
    assert tuple(result.log_fugacity_coefficient for result in results) == (0.0, 0.0)
    assert tuple(result.fugacity_coefficient for result in results) == (1.0, 1.0)


@pytest.mark.parametrize("field", ["A_mix", "B_mix"])
def test_zero_pressure_requires_exact_zero_dimensionless_parameters(
    field: str,
) -> None:
    parameters = calculate_peng_robinson_mixture_parameters(
        _mixture(), TEMPERATURE_K, 0.0
    )
    inconsistent = replace(parameters, **{field: nextafter(0.0, 1.0)})
    with pytest.raises(ValueError, match=field):
        calculate_mixture_fugacity_coefficients(inconsistent, 1.0)


def test_zero_pressure_near_repeated_root_is_rejected() -> None:
    """A small residual near the repeated Z=0 root is not enough for acceptance."""

    parameters = calculate_peng_robinson_mixture_parameters(
        _mixture(), TEMPERATURE_K, 0.0
    )
    with pytest.raises(ValueError, match="distance tolerance"):
        calculate_mixture_fugacity_coefficients(parameters, 1e-6)


def test_very_low_pressure_matches_independent_high_precision_reference() -> None:
    parameters = calculate_peng_robinson_mixture_parameters(
        _mixture(), TEMPERATURE_K, LOW_PRESSURE_PA
    )
    root = calculate_mixture_compressibility_roots(
        _mixture(), TEMPERATURE_K, LOW_PRESSURE_PA
    )[0]
    results = calculate_mixture_fugacity_coefficients(parameters, root)

    assert root == pytest.approx(LOW_PRESSURE_ROOT, abs=2e-15)
    assert results[0].log_fugacity_coefficient == pytest.approx(
        LOW_PRESSURE_METHANE_LOG_PHI, abs=2e-15
    )
    assert results[0].fugacity_coefficient == pytest.approx(
        LOW_PRESSURE_METHANE_PHI, abs=2e-15
    )
    assert results[1].log_fugacity_coefficient == pytest.approx(
        LOW_PRESSURE_ETHANE_LOG_PHI, abs=2e-15
    )
    assert results[1].fugacity_coefficient == pytest.approx(
        LOW_PRESSURE_ETHANE_PHI, abs=2e-15
    )
    assert all(
        isfinite(value)
        for result in results
        for value in (
            result.log_fugacity_coefficient,
            result.fugacity_coefficient,
        )
    )
    assert all(result.log_fugacity_coefficient != 0.0 for result in results)
    assert all(result.fugacity_coefficient != 1.0 for result in results)
    assert all(abs(result.fugacity_coefficient - 1.0) < 1e-6 for result in results)


def _direct_low_pressure_log_phi(
    component: PureComponentMixtureParameters,
    parameters: PengRobinsonMixtureParameters,
    root: float,
) -> float:
    """Reproduce the pre-Batch-4B subtraction/ratio formulation."""

    attraction_sum = fsum(
        other.mole_fraction * sqrt(component.a_alpha * other.a_alpha)
        for other in parameters.component_parameters
    )
    b_ratio = component.b / parameters.b_mix
    bracket = 2.0 * attraction_sum / parameters.a_alpha_mix - b_ratio
    sqrt_two = sqrt(2.0)
    logarithm_ratio = log(
        (root + (1.0 + sqrt_two) * parameters.B_mix)
        / (root + (1.0 - sqrt_two) * parameters.B_mix)
    )
    return (
        b_ratio * (root - 1.0)
        - log(root - parameters.B_mix)
        - parameters.A_mix
        / (2.0 * sqrt_two * parameters.B_mix)
        * bracket
        * logarithm_ratio
    )


@pytest.mark.parametrize("pressure_pa", [100.0, 1.0, 0.1, 1e-3])
def test_conditioned_low_pressure_fugacity_matches_decimal_reference(
    pressure_pa: float,
) -> None:
    parameters = calculate_peng_robinson_mixture_parameters(
        _mixture(), TEMPERATURE_K, pressure_pa
    )
    root = calculate_mixture_compressibility_roots(
        _mixture(), TEMPERATURE_K, pressure_pa
    )[-1]
    results = calculate_mixture_fugacity_coefficients(parameters, root)
    references = LOW_PRESSURE_DECIMAL_LOG_PHI[pressure_pa]

    for component, result, reference in zip(
        parameters.component_parameters,
        results,
        references,
        strict=True,
    ):
        old_error = abs(
            _direct_low_pressure_log_phi(component, parameters, root) - reference
        )
        new_error = abs(result.log_fugacity_coefficient - reference)
        assert result.log_fugacity_coefficient == pytest.approx(
            reference, rel=2e-15, abs=1e-27
        )
        assert new_error < old_error * 1e-4
        assert isfinite(result.log_fugacity_coefficient)
        assert isfinite(result.fugacity_coefficient)
        assert result.log_fugacity_coefficient != 0.0
        assert result.fugacity_coefficient != 1.0
        assert abs(result.fugacity_coefficient - 1.0) < pressure_pa * 1e-6


def test_low_pressure_branch_is_continuous_at_switch() -> None:
    pressures = (2_770.0, 2_771.0, 2_772.0, 2_773.0)
    roots: list[float] = []
    methane_logs: list[float] = []
    for pressure_pa in pressures:
        parameters = calculate_peng_robinson_mixture_parameters(
            _mixture(), TEMPERATURE_K, pressure_pa
        )
        root = calculate_mixture_compressibility_roots(
            _mixture(), TEMPERATURE_K, pressure_pa
        )[-1]
        roots.append(root)
        methane_logs.append(
            calculate_mixture_fugacity_coefficients(parameters, root)[
                0
            ].log_fugacity_coefficient
        )

    assert abs(roots[1] - 1.0) < LOW_PRESSURE_ROOT_OFFSET_THRESHOLD
    assert abs(roots[2] - 1.0) >= LOW_PRESSURE_ROOT_OFFSET_THRESHOLD
    increments = tuple(
        methane_logs[index + 1] - methane_logs[index]
        for index in range(len(methane_logs) - 1)
    )
    assert increments[1] == pytest.approx(increments[0], rel=5e-7)
    assert increments[2] == pytest.approx(increments[1], rel=5e-7)


@pytest.mark.parametrize("field", ["A_mix", "B_mix"])
def test_tiny_parameters_reject_large_relative_inconsistency(field: str) -> None:
    parameters = calculate_peng_robinson_mixture_parameters(
        _mixture(), TEMPERATURE_K, CONSISTENCY_TEST_PRESSURE_PA
    )
    assert 0.0 < getattr(parameters, field) < 1e-17
    inconsistent = replace(parameters, **{field: 5e-13})
    with pytest.raises(ValueError, match=field):
        calculate_mixture_fugacity_coefficients(inconsistent, 1.0)


def test_independently_reconstructed_aggregate_parameters_are_accepted() -> None:
    parameters = _parameters()
    a_alpha_mix = calculate_mixture_a_alpha(parameters.component_parameters)
    b_mix = calculate_mixture_b(parameters.component_parameters)
    reconstructed = replace(
        parameters,
        a_alpha_mix=a_alpha_mix,
        b_mix=b_mix,
        A_mix=calculate_mixture_A_parameter(
            a_alpha_mix,
            parameters.pressure_pa,
            parameters.temperature_k,
        ),
        B_mix=calculate_mixture_B_parameter(
            b_mix,
            parameters.pressure_pa,
            parameters.temperature_k,
        ),
    )
    assert calculate_mixture_fugacity_coefficients(reconstructed, REFERENCE_ROOT)


@pytest.mark.parametrize(
    "field",
    ["a_alpha_mix", "b_mix", "A_mix", "B_mix"],
)
def test_one_ulp_aggregate_reconstruction_difference_is_accepted(field: str) -> None:
    parameters = _parameters()
    adjusted = replace(
        parameters,
        **{field: nextafter(getattr(parameters, field), float("inf"))},
    )
    assert calculate_mixture_fugacity_coefficients(adjusted, REFERENCE_ROOT)


def test_pure_methane_limit_matches_existing_fugacity_equation() -> None:
    mixture = FluidMixture((MixtureComponent(METHANE, 1.0),))
    parameters = calculate_peng_robinson_mixture_parameters(
        mixture, TEMPERATURE_K, PRESSURE_PA
    )
    root = calculate_mixture_compressibility_roots(mixture, TEMPERATURE_K, PRESSURE_PA)[
        0
    ]
    result = calculate_mixture_fugacity_coefficients(parameters, root)[0]
    expected_log_phi = calculate_log_fugacity_coefficient(
        root, parameters.A_mix, parameters.B_mix
    )
    assert result.log_fugacity_coefficient == pytest.approx(expected_log_phi, rel=1e-13)
    assert result.fugacity_coefficient == pytest.approx(exp(expected_log_phi))


@pytest.mark.parametrize("compressibility_factor", [0.0, 0.1])
def test_compressibility_factor_below_B_mix_is_rejected(
    compressibility_factor: float,
) -> None:
    parameters = _parameters()
    assert compressibility_factor < parameters.B_mix
    with pytest.raises(ValueError, match="greater than B_mix"):
        calculate_mixture_fugacity_coefficients(parameters, compressibility_factor)


def test_Z_minus_B_logarithm_argument_equal_to_zero_is_rejected() -> None:
    parameters = _parameters()
    with pytest.raises(ValueError, match="greater than B_mix"):
        calculate_mixture_fugacity_coefficients(parameters, parameters.B_mix)


@pytest.mark.parametrize("compressibility_factor", [float("nan"), float("inf")])
def test_non_finite_compressibility_factor_is_rejected(
    compressibility_factor: float,
) -> None:
    with pytest.raises(ValueError, match="must be finite"):
        calculate_mixture_fugacity_coefficients(_parameters(), compressibility_factor)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("a_alpha_mix", 1.0),
        ("b_mix", 1.0),
        ("A_mix", 1.0),
        ("B_mix", 1.0),
    ],
)
def test_inconsistent_mixture_parameters_are_rejected(
    field: str,
    value: float,
) -> None:
    inconsistent = replace(_parameters(), **{field: value})
    with pytest.raises(ValueError, match=field):
        calculate_mixture_fugacity_coefficients(inconsistent, REFERENCE_ROOT)


def test_component_must_belong_to_parameter_collection() -> None:
    parameters = _parameters()
    foreign_component = replace(
        parameters.component_parameters[0],
        component=Component(
            name="Foreign",
            critical_temperature_k=METHANE.critical_temperature_k,
            critical_pressure_pa=METHANE.critical_pressure_pa,
            acentric_factor=METHANE.acentric_factor,
        ),
    )
    with pytest.raises(ValueError, match="exactly match"):
        calculate_log_component_fugacity_coefficient(
            foreign_component, parameters, REFERENCE_ROOT
        )


def test_non_finite_pair_attraction_is_rejected() -> None:
    component = replace(
        _parameters().component_parameters[0],
        a_alpha=float("inf"),
    )
    with pytest.raises(ValueError, match="finite"):
        calculate_component_pair_attraction_parameter(component, component)


def test_result_is_immutable() -> None:
    result = calculate_mixture_fugacity_coefficients(_parameters(), REFERENCE_ROOT)[0]
    with pytest.raises(FrozenInstanceError):
        result.fugacity_coefficient = 1.0  # type: ignore[misc]


def test_root_level_result_reports_stable_and_unstable_three_root_candidates() -> None:
    """Outer and middle roots retain explicit local mechanical status."""

    mixture = FluidMixture((MixtureComponent(METHANE, 1.0),))
    parameters = calculate_peng_robinson_mixture_parameters(
        mixture,
        0.99 * METHANE.critical_temperature_k,
        0.94 * METHANE.critical_pressure_pa,
    )
    roots = calculate_compressibility_roots(parameters.A_mix, parameters.B_mix)
    assert len(roots) == 3

    results = tuple(
        calculate_mixture_root_fugacity_result(parameters, root) for root in roots
    )
    assert tuple(result.mechanical_stability.classification for result in results) == (
        MechanicalStabilityClassification.STABLE,
        MechanicalStabilityClassification.UNSTABLE,
        MechanicalStabilityClassification.STABLE,
    )
    assert tuple(result.compressibility_factor for result in results) == roots


def test_root_level_result_reports_marginal_spinodal_candidate() -> None:
    """A near-spinodal root remains evaluable but is explicitly marginal."""

    mixture = FluidMixture((MixtureComponent(METHANE, 1.0),))
    parameters = calculate_peng_robinson_mixture_parameters(
        mixture,
        0.99 * METHANE.critical_temperature_k,
        0.9333632122923137 * METHANE.critical_pressure_pa,
    )
    roots = calculate_compressibility_roots(parameters.A_mix, parameters.B_mix)
    marginal = calculate_mixture_root_fugacity_result(parameters, roots[0])
    assert (
        marginal.mechanical_stability.classification
        is MechanicalStabilityClassification.MARGINAL
    )


def test_root_level_container_preserves_component_results_and_order() -> None:
    """The safer container leaves established component values untouched."""

    parameters = _parameters()
    legacy = calculate_mixture_fugacity_coefficients(parameters, REFERENCE_ROOT)
    result = calculate_mixture_root_fugacity_result(parameters, REFERENCE_ROOT)
    assert isinstance(result, MixtureRootFugacityResult)
    assert result.component_results == legacy
    assert tuple(item.component_name for item in result.component_results) == (
        "Methane",
        "Ethane",
    )


def test_root_level_result_exposes_binary_interaction_assumptions() -> None:
    parameters = _parameters()
    result = calculate_mixture_root_fugacity_result(parameters, REFERENCE_ROOT)
    assert result.binary_interaction_policy is BinaryInteractionPolicy.DEFAULT_ZERO
    assert result.defaulted_binary_interaction_pairs == (("Ethane", "Methane"),)
    assert (
        result.mechanical_stability.classification
        is MechanicalStabilityClassification.STABLE
    )
    with pytest.raises(FrozenInstanceError):
        result.compressibility_factor = 1.0  # type: ignore[misc]


def test_root_level_api_explicitly_disclaims_global_stability() -> None:
    """Public documentation must distinguish mechanical from global stability."""

    docstring = calculate_mixture_root_fugacity_result.__doc__ or ""
    assert "not a global mixture phase-stability" in docstring


def test_factory_parameters_preserve_immutable_component_provenance() -> None:
    """Each row retains the exact component object and calculation temperature."""

    parameters = _parameters()
    methane, ethane = parameters.component_parameters
    assert methane.component is METHANE
    assert ethane.component is ETHANE
    assert methane.temperature_k == ethane.temperature_k == TEMPERATURE_K
    with pytest.raises(ValidationError):
        methane.component.critical_temperature_k = 200.0


def test_forged_parent_temperature_is_rejected() -> None:
    """Derived rows calculated at 300 K cannot support a parent claiming 400 K."""

    forged = replace(_parameters(), temperature_k=400.0)
    with pytest.raises(ValueError, match="component temperature_k"):
        calculate_mixture_fugacity_coefficients(forged, REFERENCE_ROOT)


def test_forged_component_identity_is_rejected() -> None:
    """Replacing methane provenance with propane invalidates methane derivatives."""

    parameters = _parameters()
    forged_methane = replace(parameters.component_parameters[0], component=PROPANE)
    forged = replace(
        parameters,
        component_parameters=(forged_methane, parameters.component_parameters[1]),
    )
    with pytest.raises(ValueError, match="component provenance"):
        calculate_mixture_fugacity_coefficients(forged, REFERENCE_ROOT)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("critical_temperature_k", 200.0),
        ("critical_pressure_pa", 5_000_000.0),
        ("acentric_factor", 0.02),
    ],
)
def test_forged_component_properties_are_rejected(field: str, value: float) -> None:
    """Tc, Pc, and omega remain tied to all stored derived parameters."""

    parameters = _parameters()
    component_values = METHANE.model_dump()
    component_values[field] = value
    forged_component = Component(**component_values)
    forged_row = replace(
        parameters.component_parameters[0],
        component=forged_component,
    )
    forged = replace(
        parameters,
        component_parameters=(forged_row, parameters.component_parameters[1]),
    )
    with pytest.raises(ValueError, match="component provenance"):
        calculate_mixture_fugacity_coefficients(forged, REFERENCE_ROOT)


@pytest.mark.parametrize("field", ["alpha", "a_alpha", "b"])
def test_forged_derived_component_parameters_are_rejected(field: str) -> None:
    """Stored alpha, a_alpha, and b must match property-based re-derivation."""

    parameters = _parameters()
    row = parameters.component_parameters[0]
    forged_row = replace(row, **{field: 1.01 * getattr(row, field)})
    forged = replace(
        parameters,
        component_parameters=(forged_row, parameters.component_parameters[1]),
    )
    with pytest.raises(ValueError, match=field):
        calculate_mixture_fugacity_coefficients(forged, REFERENCE_ROOT)


def test_binary_mixture_satisfies_residual_gibbs_euler_invariant() -> None:
    """Weighted partial ln(phi_i) equals the mixture residual molar result."""

    parameters = _parameters()
    results = calculate_mixture_fugacity_coefficients(parameters, REFERENCE_ROOT)
    weighted_log_phi = fsum(
        result.mole_fraction * result.log_fugacity_coefficient for result in results
    )
    mixture_log_phi = calculate_log_fugacity_coefficient(
        REFERENCE_ROOT,
        parameters.A_mix,
        parameters.B_mix,
    )
    assert weighted_log_phi == pytest.approx(mixture_log_phi, abs=5e-15)


def test_ternary_independent_reference_and_euler_invariant() -> None:
    """Match the independent high-precision ternary PR calculation."""

    mixture = FluidMixture(
        (
            MixtureComponent(METHANE, 0.50),
            MixtureComponent(ETHANE, 0.30),
            MixtureComponent(PROPANE, 0.20),
        )
    )
    interactions = {
        ("Methane", "Ethane"): 0.02,
        ("Ethane", "Methane"): 0.02,
        ("Methane", "Propane"): 0.01,
        ("Propane", "Methane"): 0.01,
        ("Ethane", "Propane"): 0.03,
        ("Propane", "Ethane"): 0.03,
    }
    parameters = calculate_peng_robinson_mixture_parameters(
        mixture,
        TEMPERATURE_K,
        PRESSURE_PA,
        interactions,
    )
    root = calculate_compressibility_roots(parameters.A_mix, parameters.B_mix)[0]
    results = calculate_mixture_fugacity_coefficients(
        parameters,
        root,
        interactions,
    )

    assert parameters.a_alpha_mix == pytest.approx(0.44698507942275817, abs=3e-16)
    assert parameters.b_mix == pytest.approx(3.682545160140038e-05, abs=3e-19)
    assert parameters.A_mix == pytest.approx(0.71842617483525639, abs=4e-16)
    assert parameters.B_mix == pytest.approx(0.1476361263204117, abs=2e-16)
    assert root == pytest.approx(0.45760418330746788, abs=3e-15)
    assert tuple(
        result.log_fugacity_coefficient for result in results
    ) == pytest.approx(
        (0.017815239519453154, -0.92843623603219205, -1.6962978201699417),
        abs=3e-14,
    )
    assert tuple(result.fugacity_coefficient for result in results) == pytest.approx(
        (1.0179748774861579, 0.39517118191128942, 0.18336110479973641),
        abs=3e-14,
    )

    weighted_log_phi = fsum(
        result.mole_fraction * result.log_fugacity_coefficient for result in results
    )
    mixture_log_phi = calculate_log_fugacity_coefficient(
        root,
        parameters.A_mix,
        parameters.B_mix,
    )
    assert weighted_log_phi == pytest.approx(mixture_log_phi, abs=5e-15)
