"""Tests for the Michelsen-style phase-stability foundation."""

from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace
from math import fsum, isfinite, log
from time import perf_counter

import pytest
from scipy.optimize import minimize_scalar

from pvt_phase_simulator.eos.mixing_rules import (
    BinaryInteractionPolicy,
    calculate_peng_robinson_mixture_parameters,
)
from pvt_phase_simulator.eos.mixture_fugacity import (
    calculate_mixture_fugacity_coefficients,
)
from pvt_phase_simulator.eos.peng_robinson import (
    MechanicalStabilityClassification,
    MechanicalStabilityResult,
    calculate_compressibility_roots,
    classify_mechanical_stability,
)
from pvt_phase_simulator.eos.phase_stability import (
    COMPOSITION_CONVERGENCE_TOLERANCE,
    FALLBACK_COMPONENT_RICH_EPSILON,
    MAXIMUM_FALLBACK_STARTS,
    PhaseRootSelection,
    PhaseStabilityStatus,
    PhaseTrialKind,
    PhaseTrialSelectionReason,
    WilsonKValueResult,
    analyze_mixture_phase_stability,
    calculate_stationarity_residual,
    calculate_tangent_plane_distance,
    calculate_wilson_k_values,
    classify_phase_stability_trials,
    detect_phase_root_switch,
    evaluate_feed_phase_reference,
    generate_fallback_trial_compositions,
    initialize_trial_composition,
    run_phase_stability_character,
    run_phase_stability_trial,
    select_phase_stability_trial_attempts,
    select_phase_trial_root,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    FluidMixture,
    MixtureComponent,
)

TEMPERATURE_K = 300.0
PRESSURE_PA = 10_000_000.0

# Independent direct evaluation of the Wilson equation using the decimal input
# properties retained by fluid_models.py.
WILSON_REFERENCE = (
    3.3365203639607345,
    0.4387635588198514,
    0.10057096164199821,
)
UNSTABLE_TEMPERATURE_K = 170.0
UNSTABLE_PRESSURE_PA = 100_000.0
UNSTABLE_FEED_METHANE_FRACTION = 0.5
INDEPENDENT_UNSTABLE_METHANE_FRACTION = 0.018915506721665004
INDEPENDENT_UNSTABLE_TPD = -0.1380056497983253


def _binary_mixture() -> FluidMixture:
    return FluidMixture((MixtureComponent(METHANE, 0.7), MixtureComponent(ETHANE, 0.3)))


def _ternary_mixture() -> FluidMixture:
    return FluidMixture(
        (
            MixtureComponent(METHANE, 0.5),
            MixtureComponent(ETHANE, 0.3),
            MixtureComponent(PROPANE, 0.2),
        )
    )


def _independent_binary_root_states(
    methane_fraction: float,
    temperature_k: float,
    pressure_pa: float,
) -> tuple[tuple[float, tuple[float, float], float], ...]:
    """Evaluate homogeneous binary branches without Module 6 functions."""

    mixture = FluidMixture(
        (
            MixtureComponent(METHANE, methane_fraction),
            MixtureComponent(ETHANE, 1.0 - methane_fraction),
        )
    )
    parameters = calculate_peng_robinson_mixture_parameters(
        mixture,
        temperature_k,
        pressure_pa,
    )
    states: list[tuple[float, tuple[float, float], float]] = []
    for root in calculate_compressibility_roots(parameters.A_mix, parameters.B_mix):
        mechanical = classify_mechanical_stability(
            root,
            parameters.A_mix,
            parameters.B_mix,
        )
        if mechanical.classification is not MechanicalStabilityClassification.STABLE:
            continue
        results = calculate_mixture_fugacity_coefficients(parameters, root)
        log_phi = (
            results[0].log_fugacity_coefficient,
            results[1].log_fugacity_coefficient,
        )
        residual_gibbs = fsum(
            (
                methane_fraction * log_phi[0],
                (1.0 - methane_fraction) * log_phi[1],
            )
        )
        states.append((root, log_phi, residual_gibbs))
    return tuple(states)


def _independent_binary_tpd_function(
    feed_methane_fraction: float,
    temperature_k: float,
    pressure_pa: float,
) -> Callable[[float], tuple[float, float]]:
    """Construct an independent full-branch binary TPD evaluator."""

    feed_states = _independent_binary_root_states(
        feed_methane_fraction,
        temperature_k,
        pressure_pa,
    )
    feed_root = min(feed_states, key=lambda item: (item[2], item[0]))
    reference = (
        log(feed_methane_fraction) + feed_root[1][0],
        log(1.0 - feed_methane_fraction) + feed_root[1][1],
    )

    def evaluate(methane_fraction: float) -> tuple[float, float]:
        values: list[tuple[float, float]] = []
        for root, log_phi, _ in _independent_binary_root_states(
            methane_fraction,
            temperature_k,
            pressure_pa,
        ):
            tpd = fsum(
                (
                    methane_fraction
                    * (log(methane_fraction) + log_phi[0] - reference[0]),
                    (1.0 - methane_fraction)
                    * (log(1.0 - methane_fraction) + log_phi[1] - reference[1]),
                )
            )
            values.append((tpd, root))
        return min(values, key=lambda item: item[0])

    return evaluate


def test_wilson_k_values_match_independent_reference_and_order() -> None:
    results = calculate_wilson_k_values(
        (METHANE, ETHANE, PROPANE), TEMPERATURE_K, PRESSURE_PA
    )
    assert tuple(item.component_name for item in results) == (
        "Methane",
        "Ethane",
        "Propane",
    )
    assert tuple(item.k_value for item in results) == pytest.approx(
        WILSON_REFERENCE,
        rel=2e-15,
    )
    assert all(isfinite(item.k_value) and item.k_value > 0.0 for item in results)


def test_wilson_k_values_are_repeatable_and_immutable() -> None:
    first = calculate_wilson_k_values((METHANE, ETHANE), 250.0, 2_000_000.0)
    second = calculate_wilson_k_values((METHANE, ETHANE), 250.0, 2_000_000.0)
    assert first == second
    with pytest.raises(FrozenInstanceError):
        first[0].k_value = 2.0  # type: ignore[misc]


@pytest.mark.parametrize("value", [0.0, -1.0, float("nan"), float("inf")])
@pytest.mark.parametrize("field", ["temperature", "pressure"])
def test_wilson_rejects_invalid_temperature_and_pressure(
    value: float,
    field: str,
) -> None:
    temperature = value if field == "temperature" else TEMPERATURE_K
    pressure = value if field == "pressure" else PRESSURE_PA
    with pytest.raises(ValueError):
        calculate_wilson_k_values((METHANE,), temperature, pressure)


def test_wilson_rejects_exponential_overflow_and_underflow() -> None:
    with pytest.raises(ValueError, match="overflow or underflow"):
        calculate_wilson_k_values((METHANE,), TEMPERATURE_K, 1e-305)
    with pytest.raises(ValueError, match="overflow or underflow"):
        calculate_wilson_k_values((METHANE,), 1e-6, PRESSURE_PA)


def test_wilson_result_constructor_is_typed_and_immutable() -> None:
    result = WilsonKValueResult(component_name="Methane", k_value=1.5)
    assert result.component_name == "Methane"
    with pytest.raises(FrozenInstanceError):
        result.component_name = "Changed"  # type: ignore[misc]


def test_binary_trial_composition_initialization_matches_manual_arithmetic() -> None:
    feed = (0.7, 0.3)
    k_values = (2.0, 0.5)
    vapor = initialize_trial_composition(feed, k_values, PhaseTrialKind.VAPOR_LIKE)
    liquid = initialize_trial_composition(feed, k_values, PhaseTrialKind.LIQUID_LIKE)
    assert vapor == pytest.approx((1.4 / 1.55, 0.15 / 1.55), abs=1e-15)
    assert liquid == pytest.approx((0.35 / 0.95, 0.6 / 0.95), abs=1e-15)
    assert feed == (0.7, 0.3)


def test_ternary_trial_initialization_preserves_order_and_normalization() -> None:
    feed = (0.5, 0.3, 0.2)
    result = initialize_trial_composition(
        feed,
        WILSON_REFERENCE,
        PhaseTrialKind.VAPOR_LIKE,
    )
    assert len(result) == 3
    assert sum(result) == pytest.approx(1.0, abs=1e-15)
    assert result[0] > result[1] > result[2]


@pytest.mark.parametrize(
    "trial_kind",
    [PhaseTrialKind.VAPOR_LIKE, PhaseTrialKind.LIQUID_LIKE],
)
def test_unity_k_values_return_the_feed_composition(
    trial_kind: PhaseTrialKind,
) -> None:
    feed = (0.5, 0.3, 0.2)
    assert initialize_trial_composition(
        feed,
        (1.0, 1.0, 1.0),
        trial_kind,
    ) == pytest.approx(feed, abs=1e-15)


def test_trial_initialization_handles_extreme_positive_k_values() -> None:
    result = initialize_trial_composition(
        (0.5, 0.5),
        (1e300, 1e-300),
        PhaseTrialKind.VAPOR_LIKE,
    )
    assert all(isfinite(value) and value >= 0.0 for value in result)
    assert sum(result) == pytest.approx(1.0)
    assert result[0] == 1.0


def test_fallback_starts_are_deterministic_normalized_and_bounded() -> None:
    feed = (0.5, 0.3, 0.2)
    first = generate_fallback_trial_compositions(feed)
    second = generate_fallback_trial_compositions(feed)
    assert first == second
    assert first[0] == feed
    assert first[1] == pytest.approx((1.0 / 3.0,) * 3, abs=1e-15)
    assert len(first) == 5
    assert len(first) <= MAXIMUM_FALLBACK_STARTS
    assert all(sum(start) == pytest.approx(1.0, abs=1e-15) for start in first)


def test_component_rich_starts_use_documented_epsilon_and_feed_proportions() -> None:
    starts = generate_fallback_trial_compositions((0.5, 0.3, 0.2))
    methane_rich = starts[2]
    assert methane_rich[0] == pytest.approx(
        1.0 - FALLBACK_COMPONENT_RICH_EPSILON,
        abs=2e-16,
    )
    assert methane_rich[1] == pytest.approx(0.0006, abs=2e-16)
    assert methane_rich[2] == pytest.approx(0.0004, abs=2e-16)


def test_fallback_starts_preserve_zero_feed_support() -> None:
    starts = generate_fallback_trial_compositions((0.6, 0.0, 0.4))
    assert all(start[1] == 0.0 for start in starts)
    assert starts[1] == (0.5, 0.0, 0.5)


def test_fallback_starts_deduplicate_equivalent_feed_and_uniform_cases() -> None:
    binary = generate_fallback_trial_compositions((0.5, 0.5))
    pure = generate_fallback_trial_compositions((1.0, 0.0))
    assert len(binary) == 3
    assert binary.count((0.5, 0.5)) == 1
    assert pure == ((1.0, 0.0),)


@pytest.mark.parametrize(
    ("feed", "k_values"),
    [
        ((0.6, 0.5), (1.0, 1.0)),
        ((0.5, 0.5), (1.0,)),
        ((0.5, 0.5), (1.0, 0.0)),
        ((0.5, 0.5), (1.0, float("nan"))),
    ],
)
def test_trial_initialization_rejects_invalid_values(
    feed: tuple[float, ...],
    k_values: tuple[float, ...],
) -> None:
    with pytest.raises(ValueError):
        initialize_trial_composition(feed, k_values, PhaseTrialKind.VAPOR_LIKE)


def test_tpd_is_zero_when_trial_equals_feed() -> None:
    composition = (0.7, 0.3)
    log_phi = (-0.1, -0.3)
    assert calculate_tangent_plane_distance(
        composition,
        composition,
        log_phi,
        log_phi,
    ) == pytest.approx(0.0, abs=1e-16)


def test_tpd_matches_independent_manual_binary_reference() -> None:
    result = calculate_tangent_plane_distance(
        (0.6, 0.4),
        (0.5, 0.5),
        (-0.1, -0.2),
        (-0.05, -0.25),
    )
    assert result == pytest.approx(0.02041099726012756, abs=2e-16)


def test_tpd_ternary_synthetic_case_is_finite() -> None:
    result = calculate_tangent_plane_distance(
        (0.5, 0.3, 0.2),
        (0.2, 0.3, 0.5),
        (-0.1, -0.2, -0.3),
        (-0.2, -0.1, -0.4),
    )
    assert isfinite(result)


def test_tpd_near_zero_positive_and_clearly_negative_cases() -> None:
    composition = (0.6, 0.4)
    assert calculate_tangent_plane_distance(
        composition,
        composition,
        (0.0, 0.0),
        (1e-10, 1e-10),
    ) == pytest.approx(1e-10, abs=2e-17)
    assert calculate_tangent_plane_distance(
        composition,
        composition,
        (0.0, 0.0),
        (-0.1, -0.1),
    ) == pytest.approx(-0.1, abs=2e-16)


def test_stationarity_residual_is_invariant_to_common_weight_scale() -> None:
    composition = (0.6, 0.4)
    base_logs = (log(0.3), log(0.2))
    shifted_logs = tuple(value + 500.0 for value in base_logs)
    base = calculate_stationarity_residual(composition, base_logs)
    shifted = calculate_stationarity_residual(composition, shifted_logs)
    assert base == pytest.approx(0.0, abs=3e-16)
    assert shifted == pytest.approx(base, abs=6e-14)
    assert (
        calculate_stationarity_residual(
            composition,
            (log(0.4), log(0.1)),
        )
        > 0.1
    )


def test_tpd_zero_feed_fraction_policy_avoids_log_zero() -> None:
    assert (
        calculate_tangent_plane_distance(
            (1.0, 0.0),
            (1.0, 0.0),
            (0.0, 0.0),
            (0.0, 0.0),
        )
        == 0.0
    )
    with pytest.raises(ValueError, match="where feed composition is zero"):
        calculate_tangent_plane_distance(
            (1.0, 0.0),
            (0.9, 0.1),
            (0.0, 0.0),
            (0.0, 0.0),
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_tpd_rejects_non_finite_log_fugacity(value: float) -> None:
    with pytest.raises(ValueError):
        calculate_tangent_plane_distance(
            (0.5, 0.5),
            (0.5, 0.5),
            (0.0, value),
            (0.0, 0.0),
        )


def test_three_root_trial_selection_rejects_the_unstable_middle_root() -> None:
    vapor = select_phase_trial_root(0.05, 0.005, PhaseTrialKind.VAPOR_LIKE)
    liquid = select_phase_trial_root(0.05, 0.005, PhaseTrialKind.LIQUID_LIKE)
    assert tuple(item.classification for item in vapor.candidates) == (
        MechanicalStabilityClassification.STABLE,
        MechanicalStabilityClassification.UNSTABLE,
        MechanicalStabilityClassification.STABLE,
    )
    assert vapor.selected_compressibility_factor == pytest.approx(
        0.9533696347481707,
        abs=1e-14,
    )
    assert liquid.selected_compressibility_factor == pytest.approx(
        0.006765344821898573,
        abs=1e-14,
    )


def test_marginal_root_is_reported_and_not_selected() -> None:
    selection = select_phase_trial_root(
        0.4572355289213822,
        0.07779607390388846,
        PhaseTrialKind.VAPOR_LIKE,
    )
    assert selection.selected_compressibility_factor is None
    assert selection.failure_reason is not None
    assert selection.candidates[0].classification is (
        MechanicalStabilityClassification.MARGINAL
    )
    assert any(
        item.code == "MARGINAL_TRIAL_ROOTS_EXCLUDED" for item in selection.diagnostics
    )


def test_discontinuous_character_root_change_is_reported_observationally() -> None:
    def stable_root(value: float) -> MechanicalStabilityResult:
        return MechanicalStabilityResult(
            compressibility_factor=value,
            derivative=-1.0,
            derivative_tolerance=1e-14,
            classification=MechanicalStabilityClassification.STABLE,
        )

    previous = PhaseRootSelection(
        trial_kind=PhaseTrialKind.VAPOR_LIKE,
        candidates=(stable_root(0.2), stable_root(0.85)),
        selected_compressibility_factor=0.85,
        selected_classification=MechanicalStabilityClassification.STABLE,
        diagnostics=(),
        failure_reason=None,
    )
    current = PhaseRootSelection(
        trial_kind=PhaseTrialKind.VAPOR_LIKE,
        candidates=(stable_root(0.84), stable_root(0.95)),
        selected_compressibility_factor=0.95,
        selected_classification=MechanicalStabilityClassification.STABLE,
        diagnostics=(),
        failure_reason=None,
    )
    diagnostic = detect_phase_root_switch(previous, current)
    assert diagnostic is not None
    assert diagnostic.code == "DISCONTINUOUS_TRIAL_ROOT_SWITCH"
    assert current.selected_compressibility_factor == 0.95


def test_continuous_character_root_motion_has_no_switch_diagnostic() -> None:
    previous = select_phase_trial_root(0.05, 0.005, PhaseTrialKind.VAPOR_LIKE)
    current = select_phase_trial_root(0.051, 0.005, PhaseTrialKind.VAPOR_LIKE)
    assert detect_phase_root_switch(previous, current) is None


def test_feed_reference_preserves_roots_diagnostics_and_interaction_policy() -> None:
    feed = evaluate_feed_phase_reference(_binary_mixture(), TEMPERATURE_K, PRESSURE_PA)
    assert feed.failure_reason is None
    assert feed.selected_mechanical_classification is (
        MechanicalStabilityClassification.STABLE
    )
    assert feed.root_candidates
    assert len(feed.component_log_fugacity_coefficients) == 2
    assert feed.binary_interaction_policy is BinaryInteractionPolicy.DEFAULT_ZERO
    assert feed.defaulted_binary_interaction_pairs == (("Ethane", "Methane"),)
    assert any(
        item.code == "DEFAULTED_BINARY_INTERACTIONS" for item in feed.diagnostics
    )


def test_pure_component_limit_is_an_analytically_trivial_stable_case() -> None:
    mixture = FluidMixture((MixtureComponent(METHANE, 1.0),))
    result = analyze_mixture_phase_stability(mixture, 300.0, 1_000_000.0)
    assert result.status is PhaseStabilityStatus.STABLE
    assert result.vapor_like_trial.converged
    assert result.liquid_like_trial.converged
    assert result.vapor_like_trial.trivial_solution
    assert result.liquid_like_trial.trivial_solution
    assert result.vapor_like_trial.tangent_plane_distance == 0.0
    assert result.liquid_like_trial.tangent_plane_distance == 0.0


def test_independent_full_binary_scan_confirms_stable_reference_state() -> None:
    evaluate = _independent_binary_tpd_function(0.7, TEMPERATURE_K, PRESSURE_PA)
    grid = tuple(
        (fraction, evaluate(fraction)[0])
        for fraction in (index / 100.0 for index in range(1, 100))
    )
    minimum_fraction, minimum_tpd = min(grid, key=lambda item: item[1])
    assert minimum_fraction == pytest.approx(0.7)
    assert minimum_tpd == pytest.approx(0.0, abs=2e-15)
    assert all(tpd >= -2e-14 for _, tpd in grid)

    production = analyze_mixture_phase_stability(
        _binary_mixture(), TEMPERATURE_K, PRESSURE_PA
    )
    assert production.status is PhaseStabilityStatus.STABLE


def test_independent_binary_scan_and_refinement_confirm_unstable_state() -> None:
    evaluate = _independent_binary_tpd_function(
        UNSTABLE_FEED_METHANE_FRACTION,
        UNSTABLE_TEMPERATURE_K,
        UNSTABLE_PRESSURE_PA,
    )
    grid = tuple((index / 500.0, evaluate(index / 500.0)[0]) for index in range(1, 250))
    coarse_fraction, coarse_tpd = min(grid, key=lambda item: item[1])
    assert coarse_tpd < -0.13
    refined = minimize_scalar(
        lambda methane_fraction: evaluate(float(methane_fraction))[0],
        bounds=(coarse_fraction - 0.004, coarse_fraction + 0.004),
        method="bounded",
        options={"xatol": 1e-14},
    )
    assert refined.success
    assert refined.x == pytest.approx(
        INDEPENDENT_UNSTABLE_METHANE_FRACTION,
        abs=2e-8,
    )
    assert refined.fun == pytest.approx(INDEPENDENT_UNSTABLE_TPD, abs=3e-14)

    mixture = FluidMixture(
        (MixtureComponent(METHANE, 0.5), MixtureComponent(ETHANE, 0.5))
    )
    production = analyze_mixture_phase_stability(
        mixture,
        UNSTABLE_TEMPERATURE_K,
        UNSTABLE_PRESSURE_PA,
    )
    assert production.status is PhaseStabilityStatus.UNSTABLE
    assert production.liquid_like_trial.final_trial_composition[0] == pytest.approx(
        INDEPENDENT_UNSTABLE_METHANE_FRACTION,
        abs=2e-8,
    )
    assert production.liquid_like_trial.tangent_plane_distance == pytest.approx(
        INDEPENDENT_UNSTABLE_TPD,
        abs=5e-14,
    )


def test_deterministic_multistart_recovers_same_unstable_stationary_point() -> None:
    mixture = FluidMixture(
        (MixtureComponent(METHANE, 0.5), MixtureComponent(ETHANE, 0.5))
    )
    feed = evaluate_feed_phase_reference(
        mixture,
        UNSTABLE_TEMPERATURE_K,
        UNSTABLE_PRESSURE_PA,
    )
    for methane_fraction in (0.001, 0.1, 0.5, 0.9, 0.999):
        result = run_phase_stability_trial(
            mixture,
            UNSTABLE_TEMPERATURE_K,
            UNSTABLE_PRESSURE_PA,
            feed,
            (methane_fraction, 1.0 - methane_fraction),
            PhaseTrialKind.LIQUID_LIKE,
        )
        assert result.converged
        assert result.final_trial_composition[0] == pytest.approx(
            INDEPENDENT_UNSTABLE_METHANE_FRACTION,
            abs=3e-8,
        )
        assert result.tangent_plane_distance == pytest.approx(
            INDEPENDENT_UNSTABLE_TPD,
            abs=3e-13,
        )


def test_binary_case_runs_both_trials_without_mutating_feed() -> None:
    mixture = _binary_mixture()
    original = mixture.components
    result = analyze_mixture_phase_stability(mixture, TEMPERATURE_K, PRESSURE_PA)
    assert result.feed_composition == (0.7, 0.3)
    assert result.vapor_like_trial.converged
    assert result.liquid_like_trial.converged
    assert result.status in tuple(PhaseStabilityStatus)
    assert mixture.components == original


def test_conclusive_wilson_results_bypass_fallback_without_result_changes() -> None:
    result = analyze_mixture_phase_stability(
        _binary_mixture(), TEMPERATURE_K, PRESSURE_PA
    )
    for character, selected in (
        (result.vapor_like_character, result.vapor_like_trial),
        (result.liquid_like_character, result.liquid_like_trial),
    ):
        assert character.wilson_trial.converged
        assert not character.fallback_triggered
        assert character.fallback_starting_compositions == ()
        assert character.fallback_trials == ()
        assert character.selected_trial is character.wilson_trial
        assert selected is character.wilson_trial
        assert character.selection_reason is (
            PhaseTrialSelectionReason.WILSON_CONCLUSIVE
        )


def test_ternary_case_preserves_component_order_and_is_deterministic() -> None:
    mixture = _ternary_mixture()
    first = analyze_mixture_phase_stability(mixture, TEMPERATURE_K, PRESSURE_PA)
    second = analyze_mixture_phase_stability(mixture, TEMPERATURE_K, PRESSURE_PA)
    assert first == second
    assert tuple(item.component_name for item in first.wilson_k_values) == (
        "Methane",
        "Ethane",
        "Propane",
    )
    assert len(first.vapor_like_trial.final_trial_composition) == 3
    assert len(first.liquid_like_trial.final_trial_composition) == 3


def test_every_iteration_applies_explicit_root_character_policy() -> None:
    mixture = FluidMixture(
        (MixtureComponent(METHANE, 0.5), MixtureComponent(ETHANE, 0.5))
    )
    result = analyze_mixture_phase_stability(
        mixture,
        UNSTABLE_TEMPERATURE_K,
        UNSTABLE_PRESSURE_PA,
    )
    for trial in (result.vapor_like_trial, result.liquid_like_trial):
        for iteration in trial.history:
            stable_roots = tuple(
                candidate.compressibility_factor
                for candidate in iteration.root_candidates
                if candidate.classification is MechanicalStabilityClassification.STABLE
            )
            expected = (
                max(stable_roots)
                if trial.trial_kind is PhaseTrialKind.VAPOR_LIKE
                else min(stable_roots)
            )
            assert iteration.selected_compressibility_factor == expected
            assert iteration.mechanical_classification is (
                MechanicalStabilityClassification.STABLE
            )


def test_fallback_recovers_when_both_wilson_trials_are_iteration_limited() -> None:
    result = analyze_mixture_phase_stability(
        _binary_mixture(),
        TEMPERATURE_K,
        PRESSURE_PA,
        maximum_iterations=1,
    )
    assert result.status is PhaseStabilityStatus.STABLE
    for character in (
        result.vapor_like_character,
        result.liquid_like_character,
    ):
        assert not character.wilson_trial.converged
        assert character.fallback_triggered
        assert character.selected_trial is not None
        assert character.selected_trial.converged
        assert character.selection_reason is (
            PhaseTrialSelectionReason.FALLBACK_LOWEST_NONNEGATIVE_TPD
        )


def test_fallback_runs_only_for_the_inconclusive_required_character() -> None:
    result = analyze_mixture_phase_stability(
        _binary_mixture(),
        TEMPERATURE_K,
        PRESSURE_PA,
        maximum_iterations=14,
    )
    assert result.vapor_like_character.wilson_trial.converged
    assert not result.vapor_like_character.fallback_triggered
    assert result.vapor_like_character.fallback_trials == ()
    assert not result.liquid_like_character.wilson_trial.converged
    assert result.liquid_like_character.fallback_triggered
    assert result.status is PhaseStabilityStatus.STABLE


def test_all_failed_attempts_remain_inconclusive() -> None:
    mixture = FluidMixture(
        (MixtureComponent(METHANE, 0.5), MixtureComponent(ETHANE, 0.5))
    )
    result = analyze_mixture_phase_stability(
        mixture,
        UNSTABLE_TEMPERATURE_K,
        UNSTABLE_PRESSURE_PA,
        maximum_iterations=1,
    )
    liquid = result.liquid_like_character
    assert liquid.fallback_triggered
    assert not liquid.wilson_trial.converged
    assert all(not trial.converged for trial in liquid.fallback_trials)
    assert liquid.selected_trial is None
    assert liquid.selection_reason is (
        PhaseTrialSelectionReason.NO_RELIABLE_CONVERGED_TRIAL
    )
    assert result.status is PhaseStabilityStatus.INCONCLUSIVE


def test_overall_decision_policy_uses_distinct_negative_tpd_and_failures() -> None:
    mixture = FluidMixture((MixtureComponent(METHANE, 1.0),))
    base = analyze_mixture_phase_stability(mixture, 300.0, 1_000_000.0)
    negative_distinct = replace(
        base.vapor_like_trial,
        tangent_plane_distance=-2e-8,
        trivial_solution=False,
    )
    assert (
        classify_phase_stability_trials(
            negative_distinct,
            base.liquid_like_trial,
        )
        is PhaseStabilityStatus.UNSTABLE
    )

    negative_trivial = replace(
        negative_distinct,
        trivial_solution=True,
    )
    assert (
        classify_phase_stability_trials(
            negative_trivial,
            base.liquid_like_trial,
        )
        is PhaseStabilityStatus.STABLE
    )

    failed_liquid = replace(
        base.liquid_like_trial,
        converged=False,
        failure_reason="Synthetic convergence failure.",
    )
    assert (
        classify_phase_stability_trials(
            base.vapor_like_trial,
            failed_liquid,
        )
        is PhaseStabilityStatus.INCONCLUSIVE
    )


def test_attempt_selection_chooses_lowest_distinct_negative_tpd() -> None:
    base = analyze_mixture_phase_stability(
        _binary_mixture(), TEMPERATURE_K, PRESSURE_PA
    ).vapor_like_trial
    failed_wilson = replace(
        base,
        converged=False,
        failure_reason="Synthetic Wilson failure.",
    )
    shallow = replace(
        base,
        initial_composition=(0.2, 0.8),
        final_trial_composition=(0.2, 0.8),
        tangent_plane_distance=-0.02,
        trivial_solution=False,
    )
    deep = replace(
        base,
        initial_composition=(0.9, 0.1),
        final_trial_composition=(0.9, 0.1),
        tangent_plane_distance=-0.08,
        trivial_solution=False,
    )
    duplicate_deep = replace(
        deep,
        initial_composition=(0.999, 0.001),
        tangent_plane_distance=-0.079,
    )
    result = select_phase_stability_trial_attempts(
        failed_wilson,
        (shallow, deep, duplicate_deep),
    )
    assert result.selected_trial is deep
    assert result.distinct_negative_trial_count == 2
    assert result.selection_reason is (
        PhaseTrialSelectionReason.FALLBACK_LOWEST_NEGATIVE_TPD
    )


def test_attempt_selection_chooses_lowest_reliable_nonnegative_tpd() -> None:
    base = analyze_mixture_phase_stability(
        _binary_mixture(), TEMPERATURE_K, PRESSURE_PA
    ).vapor_like_trial
    failed_wilson = replace(
        base,
        converged=False,
        failure_reason="Synthetic Wilson failure.",
    )
    higher = replace(base, tangent_plane_distance=0.02)
    lower = replace(base, tangent_plane_distance=2e-6)
    result = select_phase_stability_trial_attempts(
        failed_wilson,
        (higher, lower),
    )
    assert result.selected_trial is lower
    assert result.distinct_negative_trial_count == 0
    assert result.selection_reason is (
        PhaseTrialSelectionReason.FALLBACK_LOWEST_NONNEGATIVE_TPD
    )


def test_forced_inconclusive_wilson_fallback_recovers_negative_reference() -> None:
    mixture = FluidMixture(
        (MixtureComponent(METHANE, 0.5), MixtureComponent(ETHANE, 0.5))
    )
    normal = analyze_mixture_phase_stability(
        mixture,
        UNSTABLE_TEMPERATURE_K,
        UNSTABLE_PRESSURE_PA,
    )
    failed_wilson = replace(
        normal.liquid_like_character.wilson_trial,
        converged=False,
        failure_reason="Synthetic Wilson failure for fallback audit.",
    )
    character = run_phase_stability_character(
        mixture,
        UNSTABLE_TEMPERATURE_K,
        UNSTABLE_PRESSURE_PA,
        normal.feed_reference,
        failed_wilson,
    )
    assert character.fallback_triggered
    assert character.selected_trial is not None
    assert character.selection_reason is (
        PhaseTrialSelectionReason.FALLBACK_LOWEST_NEGATIVE_TPD
    )
    assert character.selected_trial.tangent_plane_distance == pytest.approx(
        INDEPENDENT_UNSTABLE_TPD,
        abs=3e-13,
    )
    assert (
        classify_phase_stability_trials(
            normal.vapor_like_trial,
            character.selected_trial,
        )
        is PhaseStabilityStatus.UNSTABLE
    )


def test_phase_stability_results_and_history_are_immutable() -> None:
    result = analyze_mixture_phase_stability(
        _binary_mixture(), TEMPERATURE_K, PRESSURE_PA
    )
    assert result.vapor_like_trial.history
    with pytest.raises(FrozenInstanceError):
        result.status = PhaseStabilityStatus.UNSTABLE  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.vapor_like_trial.history[0].composition = (1.0, 0.0)  # type: ignore[misc]

    fallback_result = analyze_mixture_phase_stability(
        _binary_mixture(), TEMPERATURE_K, PRESSURE_PA, maximum_iterations=1
    )
    character = fallback_result.vapor_like_character
    with pytest.raises(FrozenInstanceError):
        character.fallback_triggered = False  # type: ignore[misc]
    with pytest.raises(TypeError):
        character.fallback_starting_compositions[0][0] = 0.1  # type: ignore[index]


def test_converged_trial_residuals_satisfy_documented_tolerance() -> None:
    result = analyze_mixture_phase_stability(
        _binary_mixture(), TEMPERATURE_K, PRESSURE_PA
    )
    for trial in (result.vapor_like_trial, result.liquid_like_trial):
        assert trial.convergence_metric is not None
        assert trial.convergence_metric <= 1e-10
        assert trial.history[-1].composition_change <= (
            COMPOSITION_CONVERGENCE_TOLERANCE
        )


def test_strict_explicit_zero_interaction_provenance_is_preserved() -> None:
    interactions = {("Methane", "Ethane"): 0.0, ("Ethane", "Methane"): 0.0}
    original_interactions = interactions.copy()
    result = analyze_mixture_phase_stability(
        _binary_mixture(),
        TEMPERATURE_K,
        PRESSURE_PA,
        interactions,
        BinaryInteractionPolicy.REQUIRE_ALL_PAIRS,
    )
    assert result.binary_interaction_policy is BinaryInteractionPolicy.REQUIRE_ALL_PAIRS
    assert result.binary_interactions == ()
    assert result.supplied_binary_interaction_pairs == (("Ethane", "Methane"),)
    assert result.defaulted_binary_interaction_pairs == ()
    assert interactions == original_interactions


def test_fallback_preserves_feed_and_interaction_mapping() -> None:
    mixture = _binary_mixture()
    original_components = mixture.components
    interactions = {("Methane", "Ethane"): 0.02, ("Ethane", "Methane"): 0.02}
    original_interactions = interactions.copy()
    result = analyze_mixture_phase_stability(
        mixture,
        TEMPERATURE_K,
        PRESSURE_PA,
        interactions,
        BinaryInteractionPolicy.REQUIRE_ALL_PAIRS,
        maximum_iterations=1,
    )
    assert result.vapor_like_character.fallback_triggered
    assert result.liquid_like_character.fallback_triggered
    assert mixture.components == original_components
    assert interactions == original_interactions
    assert result.feed_composition == (0.7, 0.3)
    assert result.binary_interactions == (("Ethane", "Methane", 0.02),)


def test_binary_and_ternary_fallback_runtime_is_bounded() -> None:
    started = perf_counter()
    binary = analyze_mixture_phase_stability(
        _binary_mixture(), TEMPERATURE_K, PRESSURE_PA, maximum_iterations=1
    )
    ternary = analyze_mixture_phase_stability(
        _ternary_mixture(), TEMPERATURE_K, PRESSURE_PA, maximum_iterations=1
    )
    elapsed = perf_counter() - started
    assert binary.status is PhaseStabilityStatus.STABLE
    assert ternary.status is PhaseStabilityStatus.STABLE
    assert len(binary.vapor_like_character.fallback_trials) == 4
    assert len(ternary.vapor_like_character.fallback_trials) == 5
    assert elapsed < 5.0
