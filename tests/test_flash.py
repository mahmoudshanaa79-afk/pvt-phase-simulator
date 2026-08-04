"""Tests for the stability-gated two-phase flash foundation."""

from dataclasses import FrozenInstanceError, replace
from math import exp, fsum, isfinite, log
from pathlib import Path

import pytest
from scipy.optimize import brentq

import pvt_phase_simulator.eos.flash as flash_module
from pvt_phase_simulator.eos.diagnostics import (
    DiagnosticCategory,
    DiagnosticSeverity,
    EOSDiagnostic,
)
from pvt_phase_simulator.eos.flash import (
    COMPOSITION_SUM_TOLERANCE,
    FUGACITY_EQUILIBRIUM_TOLERANCE,
    LOG_K_UPDATE_TOLERANCE,
    MATERIAL_BALANCE_TOLERANCE,
    FlashConvergenceStatus,
    FlashIteratePattern,
    FlashPhaseState,
    RachfordRiceStatus,
    calculate_phase_compositions,
    calculate_rachford_rice_value,
    calculate_two_phase_flash,
    detect_flash_iterate_pattern,
    evaluate_flash_phase,
    flash_iteration_satisfies_convergence,
    k_values_from_log_values,
    solve_rachford_rice,
)
from pvt_phase_simulator.eos.mixing_rules import (
    BinaryInteractionPolicy,
    calculate_peng_robinson_mixture_parameters,
)
from pvt_phase_simulator.eos.mixture_fugacity import (
    calculate_mixture_fugacity_coefficients,
)
from pvt_phase_simulator.eos.peng_robinson import (
    MechanicalStabilityClassification,
    calculate_compressibility_roots,
    classify_mechanical_stability,
)
from pvt_phase_simulator.eos.phase_stability import (
    PhaseStabilityStatus,
    PhaseTrialKind,
    analyze_mixture_phase_stability,
    calculate_wilson_k_values,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    Component,
    FluidMixture,
    MixtureComponent,
)

STABLE_TEMPERATURE_K = 300.0
STABLE_PRESSURE_PA = 10_000_000.0
UNSTABLE_TEMPERATURE_K = 170.0
UNSTABLE_PRESSURE_PA = 100_000.0

INDEPENDENT_BETA = 0.8761085504752338
INDEPENDENT_LIQUID_COMPOSITION = (0.02467362135475502, 0.9753263786452451)
INDEPENDENT_VAPOR_COMPOSITION = (0.5672164128700419, 0.4327835871299582)
INDEPENDENT_LIQUID_ROOT = 0.0034638943229121626
INDEPENDENT_VAPOR_ROOT = 0.9794765828836043
INDEPENDENT_LIQUID_FUGACITIES_PA = (56166.91840431327, 41824.13813507185)
INDEPENDENT_VAPOR_FUGACITIES_PA = (56166.91840431317, 41824.13813507185)


def _stable_mixture() -> FluidMixture:
    return FluidMixture((MixtureComponent(METHANE, 0.7), MixtureComponent(ETHANE, 0.3)))


def _unstable_mixture() -> FluidMixture:
    return FluidMixture((MixtureComponent(METHANE, 0.5), MixtureComponent(ETHANE, 0.5)))


@pytest.fixture(scope="module")
def stable_flash() -> flash_module.TwoPhaseFlashResult:
    return calculate_two_phase_flash(
        _stable_mixture(), STABLE_TEMPERATURE_K, STABLE_PRESSURE_PA
    )


@pytest.fixture(scope="module")
def unstable_flash() -> flash_module.TwoPhaseFlashResult:
    return calculate_two_phase_flash(
        _unstable_mixture(), UNSTABLE_TEMPERATURE_K, UNSTABLE_PRESSURE_PA
    )


def _independent_phase_state(
    composition: tuple[float, float],
    liquid: bool,
) -> tuple[float, tuple[float, float]]:
    """Evaluate one reference phase without importing production flash logic."""

    mixture = FluidMixture(
        tuple(
            MixtureComponent(component, fraction)
            for component, fraction in zip((METHANE, ETHANE), composition, strict=True)
        )
    )
    parameters = calculate_peng_robinson_mixture_parameters(
        mixture,
        UNSTABLE_TEMPERATURE_K,
        UNSTABLE_PRESSURE_PA,
    )
    stable_roots = tuple(
        root
        for root in calculate_compressibility_roots(parameters.A_mix, parameters.B_mix)
        if classify_mechanical_stability(
            root, parameters.A_mix, parameters.B_mix
        ).classification
        is MechanicalStabilityClassification.STABLE
    )
    root = min(stable_roots) if liquid else max(stable_roots)
    results = calculate_mixture_fugacity_coefficients(parameters, root)
    return root, tuple(result.log_fugacity_coefficient for result in results)  # type: ignore[return-value]


def _independent_unstable_flash_reference() -> tuple[
    float,
    tuple[float, float],
    tuple[float, float],
    float,
    float,
    tuple[float, float],
    tuple[float, float],
]:
    """Independently iterate RR and Module 4–5 EOS/fugacity APIs."""

    feed = (0.5, 0.5)
    log_k = tuple(
        log(item.k_value)
        for item in calculate_wilson_k_values(
            (METHANE, ETHANE),
            UNSTABLE_TEMPERATURE_K,
            UNSTABLE_PRESSURE_PA,
        )
    )

    def rr_value(beta: float, k_values: tuple[float, float]) -> float:
        return fsum(
            fraction * (k_value - 1.0) / (1.0 + beta * (k_value - 1.0))
            for fraction, k_value in zip(feed, k_values, strict=True)
        )

    for _ in range(100):
        k_values = tuple(exp(value) for value in log_k)
        beta = brentq(
            lambda value, values=k_values: rr_value(value, values),
            0.0,
            1.0,
            xtol=5e-15,
            rtol=1e-14,
        )
        liquid = tuple(
            fraction / (1.0 + beta * (k_value - 1.0))
            for fraction, k_value in zip(feed, k_values, strict=True)
        )
        vapor = tuple(
            k_value * fraction
            for k_value, fraction in zip(k_values, liquid, strict=True)
        )
        liquid_root, liquid_log_phi = _independent_phase_state(liquid, True)
        vapor_root, vapor_log_phi = _independent_phase_state(vapor, False)
        updated_log_k = tuple(
            liquid_value - vapor_value
            for liquid_value, vapor_value in zip(
                liquid_log_phi, vapor_log_phi, strict=True
            )
        )
        if (
            max(
                abs(updated - current)
                for updated, current in zip(updated_log_k, log_k, strict=True)
            )
            < 1e-14
        ):
            log_k = updated_log_k
            break
        log_k = updated_log_k

    final_k = tuple(exp(value) for value in log_k)
    beta = brentq(
        lambda value: rr_value(value, final_k),
        0.0,
        1.0,
        xtol=5e-15,
        rtol=1e-14,
    )
    liquid = tuple(
        fraction / (1.0 + beta * (k_value - 1.0))
        for fraction, k_value in zip(feed, final_k, strict=True)
    )
    vapor = tuple(
        k_value * fraction for k_value, fraction in zip(final_k, liquid, strict=True)
    )
    liquid_root, liquid_log_phi = _independent_phase_state(liquid, True)
    vapor_root, vapor_log_phi = _independent_phase_state(vapor, False)
    liquid_fugacities = tuple(
        fraction * exp(log_phi) * UNSTABLE_PRESSURE_PA
        for fraction, log_phi in zip(liquid, liquid_log_phi, strict=True)
    )
    vapor_fugacities = tuple(
        fraction * exp(log_phi) * UNSTABLE_PRESSURE_PA
        for fraction, log_phi in zip(vapor, vapor_log_phi, strict=True)
    )
    return (
        beta,
        liquid,  # type: ignore[return-value]
        vapor,  # type: ignore[return-value]
        liquid_root,
        vapor_root,
        liquid_fugacities,  # type: ignore[return-value]
        vapor_fugacities,  # type: ignore[return-value]
    )


def test_analytical_binary_rachford_rice_root() -> None:
    result = solve_rachford_rice((0.5, 0.5), (2.0, 0.5))
    assert result.status is RachfordRiceStatus.TWO_PHASE_ROOT
    assert result.converged
    assert result.beta == pytest.approx(0.5, abs=2e-15)
    assert result.residual == pytest.approx(0.0, abs=2e-15)
    assert result.function_at_lower_bound == pytest.approx(0.25)
    assert result.function_at_upper_bound == pytest.approx(-0.25)


@pytest.mark.parametrize(
    ("k_values", "expected"),
    [
        ((0.8, 0.5), RachfordRiceStatus.ALL_LIQUID),
        ((1.2, 2.0), RachfordRiceStatus.ALL_VAPOR),
        ((1.0, 1.0), RachfordRiceStatus.DEGENERATE),
        ((2.0, 0.5), RachfordRiceStatus.ALL_VAPOR),
    ],
)
def test_rachford_rice_endpoint_classifications(
    k_values: tuple[float, float],
    expected: RachfordRiceStatus,
) -> None:
    composition = (0.99, 0.01) if k_values == (2.0, 0.5) else (0.5, 0.5)
    result = solve_rachford_rice(composition, k_values)
    assert result.status is expected
    assert not result.converged
    assert isfinite(result.function_at_lower_bound)
    assert isfinite(result.function_at_upper_bound)


def test_rachford_rice_exact_phase_boundaries_are_not_interior_roots() -> None:
    lower = solve_rachford_rice((1.0 / 3.0, 2.0 / 3.0), (2.0, 0.5))
    upper = solve_rachford_rice((2.0 / 3.0, 1.0 / 3.0), (2.0, 0.5))
    assert lower.status is RachfordRiceStatus.ALL_LIQUID
    assert lower.beta == 0.0
    assert upper.status is RachfordRiceStatus.ALL_VAPOR
    assert upper.beta == 1.0


def test_rachford_rice_roots_can_approach_each_physical_endpoint() -> None:
    near_liquid = solve_rachford_rice(
        (1.0 / 3.0 + 1e-8, 2.0 / 3.0 - 1e-8),
        (2.0, 0.5),
    )
    near_vapor = solve_rachford_rice(
        (2.0 / 3.0 - 1e-8, 1.0 / 3.0 + 1e-8),
        (2.0, 0.5),
    )
    assert near_liquid.status is RachfordRiceStatus.TWO_PHASE_ROOT
    assert near_liquid.beta is not None and 0.0 < near_liquid.beta < 1e-6
    assert near_vapor.status is RachfordRiceStatus.TWO_PHASE_ROOT
    assert near_vapor.beta is not None and 1.0 - 1e-6 < near_vapor.beta < 1.0


def test_zero_feed_component_is_ignored_safely_by_rachford_rice() -> None:
    reference = solve_rachford_rice((0.5, 0.5), (2.0, 0.5))
    with_zero = solve_rachford_rice((0.5, 0.5, 0.0), (2.0, 0.5, 1e100))
    assert with_zero.status is reference.status
    assert with_zero.beta == pytest.approx(reference.beta, abs=2e-15)


@pytest.mark.parametrize(
    ("composition", "k_values"),
    [
        ((0.5, 0.5), (2.0, 0.0)),
        ((0.5, 0.5), (2.0, -1.0)),
        ((0.5, 0.5), (2.0, float("nan"))),
        ((0.5, 0.5), (2.0, float("inf"))),
        ((0.5, float("nan")), (2.0, 0.5)),
        ((0.6, 0.5), (2.0, 0.5)),
        ((0.5, 0.5), (2.0,)),
    ],
)
def test_rachford_rice_rejects_invalid_inputs(
    composition: tuple[float, ...],
    k_values: tuple[float, ...],
) -> None:
    with pytest.raises(ValueError):
        solve_rachford_rice(composition, k_values)


def test_rachford_rice_function_is_monotone_and_denominator_safe() -> None:
    composition = (0.5, 0.5)
    k_values = (2.0, 0.5)
    values = tuple(
        calculate_rachford_rice_value(beta, composition, k_values)
        for beta in (0.0, 0.25, 0.5, 0.75, 1.0)
    )
    assert all(
        left > right for left, right in zip(values[:-1], values[1:], strict=True)
    )
    with pytest.raises(ValueError, match="denominators"):
        calculate_rachford_rice_value(2.0, composition, k_values)


def test_rachford_rice_is_deterministic_and_residual_is_accurate() -> None:
    first = solve_rachford_rice((0.5, 0.5), (2.0, 0.5))
    second = solve_rachford_rice((0.5, 0.5), (2.0, 0.5))
    assert first == second
    assert first.residual is not None
    assert abs(first.residual) <= 1e-14


def test_manual_binary_phase_compositions_and_material_balance() -> None:
    result = calculate_phase_compositions((0.5, 0.5), (2.0, 0.5), 0.5)
    assert result.denominators == pytest.approx((1.5, 0.75))
    assert result.liquid_composition == pytest.approx((1.0 / 3.0, 2.0 / 3.0))
    assert result.vapor_composition == pytest.approx((2.0 / 3.0, 1.0 / 3.0))
    assert fsum(result.liquid_composition) == pytest.approx(1.0)
    assert fsum(result.vapor_composition) == pytest.approx(1.0)
    assert result.maximum_material_balance_residual <= 2e-16


def test_manual_ternary_phase_compositions_preserve_order() -> None:
    result = calculate_phase_compositions(
        (0.32, 0.3, 0.38),
        (2.5, 1.0, 0.4),
        0.4,
    )
    assert result.liquid_composition == pytest.approx((0.2, 0.3, 0.5))
    assert result.vapor_composition == pytest.approx((0.5, 0.3, 0.2))
    assert result.maximum_material_balance_residual <= 2e-16


@pytest.mark.parametrize("beta", [0.0, 1.0])
def test_phase_composition_unity_k_endpoint_limits(beta: float) -> None:
    result = calculate_phase_compositions((0.6, 0.4), (1.0, 1.0), beta)
    assert result.liquid_composition == (0.6, 0.4)
    assert result.vapor_composition == (0.6, 0.4)


def test_phase_compositions_preserve_zero_feed_support_and_input() -> None:
    feed = (0.5, 0.5, 0.0)
    result = calculate_phase_compositions(feed, (2.0, 0.5, 3.0), 0.5)
    assert result.liquid_composition[2] == 0.0
    assert result.vapor_composition[2] == 0.0
    assert feed == (0.5, 0.5, 0.0)


@pytest.mark.parametrize(
    ("k_values", "beta"),
    [
        ((2.0, 0.5), -0.1),
        ((2.0, 0.5), 1.1),
        ((2.0, 0.5), float("nan")),
        ((2.0, 0.5), 0.25),
    ],
)
def test_phase_composition_rejects_invalid_or_inconsistent_inputs(
    k_values: tuple[float, float],
    beta: float,
) -> None:
    with pytest.raises(ValueError):
        calculate_phase_compositions((0.5, 0.5), k_values, beta)


def test_stable_reference_skips_two_phase_flash(
    stable_flash: flash_module.TwoPhaseFlashResult,
) -> None:
    assert stable_flash.phase_stability.status is PhaseStabilityStatus.STABLE
    assert stable_flash.phase_state is FlashPhaseState.SINGLE_PHASE
    assert stable_flash.convergence_status is FlashConvergenceStatus.NOT_ATTEMPTED
    assert stable_flash.iteration_history == ()
    assert stable_flash.vapor_fraction is None
    assert stable_flash.liquid_fraction is None
    assert stable_flash.liquid_phase is None
    assert stable_flash.vapor_phase is None
    assert stable_flash.single_phase_root is not None
    assert stable_flash.single_phase_mechanical_classification is (
        MechanicalStabilityClassification.STABLE
    )
    assert len(stable_flash.single_phase_log_fugacity_coefficients) == 2


def test_inconclusive_stability_does_not_enter_flash() -> None:
    result = calculate_two_phase_flash(
        _unstable_mixture(),
        UNSTABLE_TEMPERATURE_K,
        UNSTABLE_PRESSURE_PA,
        stability_maximum_iterations=1,
    )
    assert result.phase_stability.status is PhaseStabilityStatus.INCONCLUSIVE
    assert result.phase_state is FlashPhaseState.INCONCLUSIVE
    assert result.convergence_status is FlashConvergenceStatus.NOT_ATTEMPTED
    assert result.iteration_history == ()
    assert "stability is inconclusive" in (result.failure_reason or "").lower()


def test_unstable_reference_enters_and_converges_flash(
    unstable_flash: flash_module.TwoPhaseFlashResult,
) -> None:
    assert unstable_flash.phase_stability.status is PhaseStabilityStatus.UNSTABLE
    assert unstable_flash.phase_state is FlashPhaseState.TWO_PHASE
    assert unstable_flash.convergence_status is FlashConvergenceStatus.CONVERGED
    assert unstable_flash.failure_reason is None
    assert unstable_flash.iteration_history
    assert unstable_flash.initial_k_values == pytest.approx(
        (23.84328296051549, 0.4429792859543136),
        rel=2e-14,
    )


def test_independent_reference_solver_matches_documented_constants() -> None:
    beta, liquid, vapor, liquid_root, vapor_root, liquid_f, vapor_f = (
        _independent_unstable_flash_reference()
    )
    assert beta == pytest.approx(INDEPENDENT_BETA, abs=3e-15)
    assert liquid == pytest.approx(INDEPENDENT_LIQUID_COMPOSITION, abs=3e-14)
    assert vapor == pytest.approx(INDEPENDENT_VAPOR_COMPOSITION, abs=3e-14)
    assert liquid_root == pytest.approx(INDEPENDENT_LIQUID_ROOT, abs=3e-15)
    assert vapor_root == pytest.approx(INDEPENDENT_VAPOR_ROOT, abs=3e-15)
    assert liquid_f == pytest.approx(INDEPENDENT_LIQUID_FUGACITIES_PA, rel=3e-14)
    assert vapor_f == pytest.approx(INDEPENDENT_VAPOR_FUGACITIES_PA, rel=3e-14)


def test_production_flash_matches_independent_unstable_reference(
    unstable_flash: flash_module.TwoPhaseFlashResult,
) -> None:
    assert unstable_flash.vapor_fraction == pytest.approx(INDEPENDENT_BETA, abs=2e-12)
    assert unstable_flash.liquid_fraction == pytest.approx(
        1.0 - INDEPENDENT_BETA, abs=2e-12
    )
    assert unstable_flash.liquid_phase is not None
    assert unstable_flash.vapor_phase is not None
    assert unstable_flash.liquid_phase.composition == pytest.approx(
        INDEPENDENT_LIQUID_COMPOSITION, abs=6e-12
    )
    assert unstable_flash.vapor_phase.composition == pytest.approx(
        INDEPENDENT_VAPOR_COMPOSITION, abs=6e-12
    )
    assert unstable_flash.liquid_phase.selected_compressibility_factor == (
        pytest.approx(INDEPENDENT_LIQUID_ROOT, abs=5e-15)
    )
    assert unstable_flash.vapor_phase.selected_compressibility_factor == (
        pytest.approx(INDEPENDENT_VAPOR_ROOT, abs=5e-15)
    )


def test_flash_root_policies_preserve_all_candidates(
    unstable_flash: flash_module.TwoPhaseFlashResult,
) -> None:
    assert unstable_flash.liquid_phase is not None
    assert unstable_flash.vapor_phase is not None
    for phase, chooser in (
        (unstable_flash.liquid_phase, min),
        (unstable_flash.vapor_phase, max),
    ):
        stable_roots = tuple(
            candidate.compressibility_factor
            for candidate in phase.root_selection.candidates
            if candidate.classification is MechanicalStabilityClassification.STABLE
        )
        assert phase.selected_compressibility_factor == chooser(stable_roots)
        assert phase.mechanical_classification is (
            MechanicalStabilityClassification.STABLE
        )


def test_final_fugacity_equality_and_material_balance(
    unstable_flash: flash_module.TwoPhaseFlashResult,
) -> None:
    assert unstable_flash.liquid_phase is not None
    assert unstable_flash.vapor_phase is not None
    assert unstable_flash.liquid_phase.component_fugacities_pa == pytest.approx(
        INDEPENDENT_LIQUID_FUGACITIES_PA,
        rel=5e-10,
    )
    assert unstable_flash.vapor_phase.component_fugacities_pa == pytest.approx(
        INDEPENDENT_VAPOR_FUGACITIES_PA,
        rel=5e-10,
    )
    assert (
        max(
            abs(value)
            for value in unstable_flash.equilibrium_residuals
            if value is not None
        )
        <= FUGACITY_EQUILIBRIUM_TOLERANCE
    )
    assert (
        max(
            (abs(value) for value in unstable_flash.material_balance_residuals),
            default=0.0,
        )
        <= MATERIAL_BALANCE_TOLERANCE
    )
    assert unstable_flash.vapor_fraction is not None
    assert 0.0 < unstable_flash.vapor_fraction < 1.0
    assert unstable_flash.final_k_values is not None
    assert unstable_flash.final_k_values == pytest.approx(
        tuple(
            vapor_fraction / liquid_fraction
            for liquid_fraction, vapor_fraction in zip(
                unstable_flash.liquid_phase.composition,
                unstable_flash.vapor_phase.composition,
                strict=True,
            )
        ),
        rel=2e-15,
    )


def test_flash_preserves_feed_and_is_deterministic() -> None:
    mixture = _unstable_mixture()
    original = mixture.components
    first = calculate_two_phase_flash(
        mixture, UNSTABLE_TEMPERATURE_K, UNSTABLE_PRESSURE_PA
    )
    second = calculate_two_phase_flash(
        mixture, UNSTABLE_TEMPERATURE_K, UNSTABLE_PRESSURE_PA
    )
    assert first == second
    assert mixture.components == original


def test_flash_results_and_history_are_immutable(
    unstable_flash: flash_module.TwoPhaseFlashResult,
) -> None:
    with pytest.raises(FrozenInstanceError):
        unstable_flash.phase_state = FlashPhaseState.SINGLE_PHASE  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        unstable_flash.iteration_history[0].beta = 0.1  # type: ignore[misc]
    with pytest.raises(TypeError):
        unstable_flash.material_balance_residuals[0] = 1.0  # type: ignore[index]


def test_interaction_policy_and_mapping_provenance_are_preserved() -> None:
    interactions = {("Methane", "Ethane"): 0.02, ("Ethane", "Methane"): 0.02}
    original = interactions.copy()
    result = calculate_two_phase_flash(
        _unstable_mixture(),
        UNSTABLE_TEMPERATURE_K,
        UNSTABLE_PRESSURE_PA,
        interactions,
        BinaryInteractionPolicy.REQUIRE_ALL_PAIRS,
    )
    assert result.binary_interaction_policy is BinaryInteractionPolicy.REQUIRE_ALL_PAIRS
    assert result.binary_interactions == (("Ethane", "Methane", 0.02),)
    assert result.supplied_binary_interaction_pairs == (("Ethane", "Methane"),)
    assert result.defaulted_binary_interaction_pairs == ()
    assert interactions == original


def test_maximum_iteration_failure_preserves_attempt() -> None:
    result = calculate_two_phase_flash(
        _unstable_mixture(),
        UNSTABLE_TEMPERATURE_K,
        UNSTABLE_PRESSURE_PA,
        maximum_iterations=1,
    )
    assert result.phase_state is FlashPhaseState.INCONCLUSIVE
    assert result.convergence_status is FlashConvergenceStatus.NOT_CONVERGED
    assert len(result.iteration_history) == 1
    assert "Maximum flash iterations" in (result.failure_reason or "")
    assert any(item.code == "FLASH_MAXIMUM_ITERATIONS" for item in result.diagnostics)


def test_iterate_pattern_detects_stagnation_oscillation_and_normal_motion() -> None:
    assert detect_flash_iterate_pattern((1.0, -1.0), (1.0, -1.0), None) is (
        FlashIteratePattern.STAGNATION
    )
    assert (
        detect_flash_iterate_pattern(
            (0.5, -0.5),
            (1.0, -1.0),
            (1.0, -1.0),
        )
        is FlashIteratePattern.OSCILLATION
    )
    assert (
        detect_flash_iterate_pattern(
            (0.5, -0.5),
            (0.6, -0.6),
            (1.0, -1.0),
        )
        is FlashIteratePattern.NORMAL
    )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 1e4, -1e4])
def test_log_k_conversion_rejects_nonfinite_overflow_and_underflow(
    value: float,
) -> None:
    with pytest.raises(ValueError):
        k_values_from_log_values((value,))


def test_every_convergence_metric_is_required(
    unstable_flash: flash_module.TwoPhaseFlashResult,
) -> None:
    converged = unstable_flash.iteration_history[-1]
    assert flash_iteration_satisfies_convergence(converged)

    bad_rr = replace(
        converged,
        rachford_rice=replace(converged.rachford_rice, residual=1e-6),
    )
    bad_log_k = replace(converged, maximum_log_k_residual=1e-4)
    bad_equilibrium = replace(
        converged,
        maximum_fugacity_equilibrium_residual=1e-4,
    )
    bad_liquid_sum = replace(
        converged,
        phase_compositions=replace(
            converged.phase_compositions,
            liquid_sum_residual=1e-6,
        ),
    )
    bad_vapor_sum = replace(
        converged,
        phase_compositions=replace(
            converged.phase_compositions,
            vapor_sum_residual=1e-6,
        ),
    )
    bad_material_balance = replace(
        converged,
        phase_compositions=replace(
            converged.phase_compositions,
            maximum_material_balance_residual=1e-6,
        ),
    )
    bad_beta = replace(converged, beta=0.0)
    bad_root = replace(
        converged,
        liquid_phase=replace(
            converged.liquid_phase,
            mechanical_classification=MechanicalStabilityClassification.MARGINAL,
        ),
    )
    assert all(
        not flash_iteration_satisfies_convergence(item)
        for item in (
            bad_rr,
            bad_log_k,
            bad_equilibrium,
            bad_liquid_sum,
            bad_vapor_sum,
            bad_material_balance,
            bad_beta,
            bad_root,
        )
    )


def test_small_k_change_alone_does_not_create_false_convergence(
    unstable_flash: flash_module.TwoPhaseFlashResult,
) -> None:
    iteration = unstable_flash.iteration_history[-1]
    synthetic = replace(
        iteration,
        maximum_log_k_residual=0.0,
        maximum_fugacity_equilibrium_residual=1e-3,
    )
    assert not flash_iteration_satisfies_convergence(synthetic)


def test_small_beta_change_alone_does_not_create_false_convergence(
    unstable_flash: flash_module.TwoPhaseFlashResult,
) -> None:
    iteration = unstable_flash.iteration_history[0]
    synthetic = replace(iteration, beta_change=0.0)
    assert synthetic.maximum_log_k_residual > LOG_K_UPDATE_TOLERANCE
    assert not flash_iteration_satisfies_convergence(synthetic)


def test_marginal_only_phase_roots_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mixture = _stable_mixture()
    stability = analyze_mixture_phase_stability(
        mixture, STABLE_TEMPERATURE_K, STABLE_PRESSURE_PA
    )
    parameters = calculate_peng_robinson_mixture_parameters(
        mixture, STABLE_TEMPERATURE_K, STABLE_PRESSURE_PA
    )
    marginal_parameters = replace(
        parameters,
        A_mix=0.4572355289213822,
        B_mix=0.07779607390388846,
    )
    monkeypatch.setattr(
        flash_module,
        "calculate_peng_robinson_mixture_parameters",
        lambda *args, **kwargs: marginal_parameters,
    )
    with pytest.raises(ValueError, match="mechanically stable.*root"):
        evaluate_flash_phase(
            mixture,
            (0.7, 0.3),
            STABLE_TEMPERATURE_K,
            STABLE_PRESSURE_PA,
            PhaseTrialKind.LIQUID_LIKE,
            stability,
        )


def test_flash_phase_rejects_binary_interaction_provenance_mismatch() -> None:
    mixture = _unstable_mixture()
    stability = analyze_mixture_phase_stability(
        mixture, UNSTABLE_TEMPERATURE_K, UNSTABLE_PRESSURE_PA
    )
    with pytest.raises(ValueError, match="provenance"):
        evaluate_flash_phase(
            mixture,
            (0.1, 0.9),
            UNSTABLE_TEMPERATURE_K,
            UNSTABLE_PRESSURE_PA,
            PhaseTrialKind.LIQUID_LIKE,
            stability,
            {("Methane", "Ethane"): 0.02, ("Ethane", "Methane"): 0.02},
            BinaryInteractionPolicy.REQUIRE_ALL_PAIRS,
        )


def test_root_switch_diagnostic_is_preserved_without_forcing_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostic = EOSDiagnostic(
        code="SYNTHETIC_FLASH_ROOT_SWITCH",
        severity=DiagnosticSeverity.WARNING,
        category=DiagnosticCategory.NUMERICAL_CONDITIONING,
        message="Synthetic observational root switch.",
    )
    monkeypatch.setattr(
        flash_module,
        "detect_phase_root_switch",
        lambda previous, current: diagnostic,
    )
    result = calculate_two_phase_flash(
        _unstable_mixture(), UNSTABLE_TEMPERATURE_K, UNSTABLE_PRESSURE_PA
    )
    assert result.convergence_status is FlashConvergenceStatus.CONVERGED
    assert diagnostic in result.diagnostics


def test_no_physical_rr_root_after_unstable_gate_is_failed_not_stable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stability = analyze_mixture_phase_stability(
        _unstable_mixture(), UNSTABLE_TEMPERATURE_K, UNSTABLE_PRESSURE_PA
    )
    invalid_initialization = replace(
        stability,
        wilson_k_values=tuple(
            replace(item, k_value=2.0) for item in stability.wilson_k_values
        ),
    )
    monkeypatch.setattr(
        flash_module,
        "analyze_mixture_phase_stability",
        lambda *args, **kwargs: invalid_initialization,
    )
    result = calculate_two_phase_flash(
        _unstable_mixture(), UNSTABLE_TEMPERATURE_K, UNSTABLE_PRESSURE_PA
    )
    assert result.phase_state is FlashPhaseState.INCONCLUSIVE
    assert result.convergence_status is FlashConvergenceStatus.FAILED
    assert result.iteration_history == ()
    assert any(item.code == "FLASH_NO_RR_ROOT" for item in result.diagnostics)


def test_flash_documentation_contains_implemented_equations_and_scope() -> None:
    repository = Path(__file__).resolve().parents[1]
    design = (repository / "docs" / "FLASH_DESIGN.md").read_text(encoding="utf-8")
    assert "F(\\beta)" in design
    assert "K_i=\\frac{\\phi_i^L}{\\phi_i^V}" in design
    assert "r_i^{eq}" in design
    assert "stability" in design.lower()
    assert "does not calculate bubble points" in design.lower()


def test_tolerances_are_not_weaker_than_documented_module_7_limits() -> None:
    assert COMPOSITION_SUM_TOLERANCE <= 1e-10
    assert MATERIAL_BALANCE_TOLERANCE <= 1e-10
    assert FUGACITY_EQUILIBRIUM_TOLERANCE <= 1e-8
    assert LOG_K_UPDATE_TOLERANCE <= 1e-8


@pytest.mark.parametrize(
    ("composition", "k_values", "expected_beta"),
    [
        # F(b) = 0.5(K1-1)/((1-b)+bK1) + 0.5(K2-1)/((1-b)+bK2); for K1 -> inf
        # and K2 -> 0 this is 0.5/b - 0.5/(1-b), whose root is exactly b = 1/2.
        ((0.5, 0.5), (1e50, 1e-50), 0.5),
        # 3.6/(1+9b) - 0.3/(1-b) = 0  =>  3.3 = 6.3b  =>  b = 11/21.
        ((0.4, 0.3, 0.3), (10.0, 1.0, 1e-18), 11.0 / 21.0),
    ],
)
def test_extreme_k_spread_keeps_the_denominator_positive(
    composition: tuple[float, ...],
    k_values: tuple[float, ...],
    expected_beta: float,
) -> None:
    """A K below the spacing of one must not collapse the beta-one denominator.

    The literal form ``1 + beta*(K - 1)`` evaluates to exactly zero at
    ``beta = 1`` for every ``K < 5.6e-17``, which rejected these mathematically
    valid states as a denominator failure.
    """

    result = solve_rachford_rice(composition, k_values)
    assert result.status is RachfordRiceStatus.TWO_PHASE_ROOT
    assert result.converged
    assert result.beta == pytest.approx(expected_beta, abs=1e-14)
    assert result.residual is not None
    assert abs(result.residual) <= 1e-14


def test_rachford_rice_endpoint_is_exact_for_a_vanishing_k_value() -> None:
    """F(1) = sum z_i (K_i - 1)/K_i stays finite for a vanishing K-value."""

    value = calculate_rachford_rice_value(1.0, (0.5, 0.5), (2.0, 1e-17))
    assert isfinite(value)
    assert value == pytest.approx(0.25 + 0.5 * (1e-17 - 1.0) / 1e-17, rel=1e-15)


def test_phase_composition_denominator_equals_k_at_beta_one() -> None:
    """At beta = 1 the exact denominator is K_i, so x_i = z_i/K_i and y_i = z_i."""

    result = calculate_phase_compositions((0.5, 0.5), (2.0, 2.0 / 3.0), 1.0)
    assert result.denominators == (2.0, 2.0 / 3.0)
    assert result.liquid_composition == (0.25, 0.75)
    assert result.vapor_composition == (0.5, 0.5)
    assert result.raw_liquid_sum == 1.0
    assert result.raw_vapor_sum == 1.0
    assert not result.liquid_renormalized
    assert not result.vapor_renormalized
    assert result.maximum_material_balance_residual == 0.0


def test_k_values_near_unity_still_resolve_an_interior_root() -> None:
    """0.502(1 - 0.01b) = 0.498(1 + 0.01b) gives 0.004 = 0.01b, so b = 0.4."""

    result = solve_rachford_rice((0.502, 0.498), (1.01, 0.99))
    assert result.status is RachfordRiceStatus.TWO_PHASE_ROOT
    assert result.beta == pytest.approx(0.4, abs=1e-12)
    assert result.residual is not None
    assert abs(result.residual) <= 1e-14


def test_symmetric_near_unity_k_values_are_not_forced_into_a_split() -> None:
    result = solve_rachford_rice((0.5, 0.5), (1.0 + 1e-11, 1.0 - 1e-11))
    assert result.status is RachfordRiceStatus.ALL_LIQUID
    assert not result.converged
    assert result.function_at_upper_bound < 0.0


def test_converged_state_is_self_consistent_and_not_stale(
    unstable_flash: flash_module.TwoPhaseFlashResult,
) -> None:
    """Every reported final quantity must belong to one thermodynamic state.

    The reported ln(phi) values are re-derived from the reported compositions
    and roots, and the reported compositions are re-derived from the feed, the
    reported beta, and the reported final K-values.
    """

    assert unstable_flash.liquid_phase is not None
    assert unstable_flash.vapor_phase is not None
    assert unstable_flash.final_k_values is not None
    assert unstable_flash.vapor_fraction is not None

    for phase in (unstable_flash.liquid_phase, unstable_flash.vapor_phase):
        parameters = calculate_peng_robinson_mixture_parameters(
            FluidMixture(
                tuple(
                    MixtureComponent(component, fraction)
                    for component, fraction in zip(
                        (METHANE, ETHANE), phase.composition, strict=True
                    )
                )
            ),
            UNSTABLE_TEMPERATURE_K,
            UNSTABLE_PRESSURE_PA,
        )
        rebuilt = calculate_mixture_fugacity_coefficients(
            parameters,
            phase.selected_compressibility_factor,
        )
        assert tuple(item.log_fugacity_coefficient for item in rebuilt) == (
            phase.component_log_fugacity_coefficients
        )

    feed = tuple(item.mole_fraction for item in unstable_flash.feed_mixture.components)
    beta = unstable_flash.vapor_fraction
    liquid = tuple(
        fraction / ((1.0 - beta) + beta * k_value)
        for fraction, k_value in zip(feed, unstable_flash.final_k_values, strict=True)
    )
    vapor = tuple(
        k_value * fraction
        for k_value, fraction in zip(unstable_flash.final_k_values, liquid, strict=True)
    )
    assert unstable_flash.liquid_phase.composition == liquid
    assert unstable_flash.vapor_phase.composition == vapor

    last = unstable_flash.iteration_history[-1]
    assert last.k_values == unstable_flash.final_k_values
    assert last.beta == beta
    assert last.liquid_phase is unstable_flash.liquid_phase
    assert last.vapor_phase is unstable_flash.vapor_phase
    assert last.fugacity_equilibrium_residuals == unstable_flash.equilibrium_residuals


def test_zero_feed_component_matches_the_binary_unstable_reference(
    unstable_flash: flash_module.TwoPhaseFlashResult,
) -> None:
    """An inert zero-fraction component must not perturb the two-phase split."""

    result = calculate_two_phase_flash(
        FluidMixture(
            (
                MixtureComponent(METHANE, 0.5),
                MixtureComponent(ETHANE, 0.5),
                MixtureComponent(PROPANE, 0.0),
            )
        ),
        UNSTABLE_TEMPERATURE_K,
        UNSTABLE_PRESSURE_PA,
    )
    assert result.phase_state is FlashPhaseState.TWO_PHASE
    assert result.convergence_status is FlashConvergenceStatus.CONVERGED
    assert result.liquid_phase is not None
    assert result.vapor_phase is not None
    assert result.vapor_fraction == pytest.approx(INDEPENDENT_BETA, abs=2e-12)
    assert result.liquid_phase.composition[:2] == pytest.approx(
        INDEPENDENT_LIQUID_COMPOSITION, abs=6e-12
    )
    assert result.vapor_phase.composition[:2] == pytest.approx(
        INDEPENDENT_VAPOR_COMPOSITION, abs=6e-12
    )
    assert result.liquid_phase.composition[2] == 0.0
    assert result.vapor_phase.composition[2] == 0.0
    assert result.equilibrium_residuals[2] is None
    assert result.liquid_phase.component_fugacities_pa[2] == 0.0
    assert result.vapor_phase.component_fugacities_pa[2] == 0.0


def _independent_flash_reference(
    components: tuple[Component, ...],
    feed: tuple[float, ...],
    temperature_k: float,
    pressure_pa: float,
) -> tuple[float, tuple[float, ...], tuple[float, ...], float, float]:
    """Iterate RR, x/y, and the K update independently of ``flash.py``."""

    def phase_state(
        composition: tuple[float, ...],
        liquid: bool,
    ) -> tuple[float, tuple[float, ...]]:
        parameters = calculate_peng_robinson_mixture_parameters(
            FluidMixture(
                tuple(
                    MixtureComponent(component, fraction)
                    for component, fraction in zip(components, composition, strict=True)
                )
            ),
            temperature_k,
            pressure_pa,
        )
        stable = tuple(
            root
            for root in calculate_compressibility_roots(
                parameters.A_mix, parameters.B_mix
            )
            if classify_mechanical_stability(
                root, parameters.A_mix, parameters.B_mix
            ).classification
            is MechanicalStabilityClassification.STABLE
        )
        root = min(stable) if liquid else max(stable)
        results = calculate_mixture_fugacity_coefficients(parameters, root)
        return root, tuple(item.log_fugacity_coefficient for item in results)

    def rr_value(beta: float, k_values: tuple[float, ...]) -> float:
        return fsum(
            fraction * (k_value - 1.0) / ((1.0 - beta) + beta * k_value)
            for fraction, k_value in zip(feed, k_values, strict=True)
        )

    log_k = tuple(
        log(item.k_value)
        for item in calculate_wilson_k_values(components, temperature_k, pressure_pa)
    )
    liquid: tuple[float, ...] = feed
    vapor: tuple[float, ...] = feed
    beta = 0.0
    liquid_root = 0.0
    vapor_root = 0.0
    for _ in range(400):
        k_values = tuple(exp(value) for value in log_k)
        beta = brentq(
            lambda value, values=k_values: rr_value(value, values),
            0.0,
            1.0,
            xtol=5e-15,
            rtol=1e-14,
        )
        liquid = tuple(
            fraction / ((1.0 - beta) + beta * k_value)
            for fraction, k_value in zip(feed, k_values, strict=True)
        )
        vapor = tuple(
            k_value * fraction
            for k_value, fraction in zip(k_values, liquid, strict=True)
        )
        liquid_root, liquid_log_phi = phase_state(liquid, True)
        vapor_root, vapor_log_phi = phase_state(vapor, False)
        updated = tuple(
            liquid_value - vapor_value
            for liquid_value, vapor_value in zip(
                liquid_log_phi, vapor_log_phi, strict=True
            )
        )
        converged = (
            max(abs(new - old) for new, old in zip(updated, log_k, strict=True)) < 1e-13
        )
        log_k = updated
        if converged:
            break
    return beta, liquid, vapor, liquid_root, vapor_root


# Values produced by a separate reference implementation written directly from
# the Peng-Robinson equations, independent of this package's log1p-transformed
# fugacity form, root de-duplication, and bracketed Rachford-Rice solver.
ADDITIONAL_UNSTABLE_REFERENCES = (
    (
        (METHANE, ETHANE),
        (0.5, 0.5),
        200.0,
        2_000_000.0,
        0.25029630064364417,
        (0.37073325140474767, 0.6292667485952523),
        (0.8871881421196288, 0.11281185788037112),
        0.06129439777780863,
        0.8067040770133005,
    ),
    (
        (METHANE, PROPANE),
        (0.6, 0.4),
        250.0,
        3_000_000.0,
        0.5444820546845486,
        (0.247976963998312, 0.752023036001688),
        (0.8945052250732085, 0.10549477492679131),
        0.09989839485514644,
        0.8348098565412085,
    ),
    (
        (METHANE, ETHANE, PROPANE),
        (0.6, 0.3, 0.1),
        220.0,
        2_000_000.0,
        0.6357152799316232,
        (0.23268890481155485, 0.518889547692782, 0.24842154749566314),
        (0.8104807351856064, 0.17456944936774968, 0.014949815446643986),
        0.06325423297623155,
        0.833978653251134,
    ),
)


@pytest.mark.parametrize(
    (
        "components",
        "feed",
        "temperature_k",
        "pressure_pa",
        "beta",
        "liquid",
        "vapor",
        "liquid_root",
        "vapor_root",
    ),
    ADDITIONAL_UNSTABLE_REFERENCES,
)
def test_additional_binary_and_ternary_unstable_references(
    components: tuple[Component, ...],
    feed: tuple[float, ...],
    temperature_k: float,
    pressure_pa: float,
    beta: float,
    liquid: tuple[float, ...],
    vapor: tuple[float, ...],
    liquid_root: float,
    vapor_root: float,
) -> None:
    in_test = _independent_flash_reference(components, feed, temperature_k, pressure_pa)
    assert in_test[0] == pytest.approx(beta, abs=1e-9)
    assert in_test[1] == pytest.approx(liquid, abs=1e-9)
    assert in_test[2] == pytest.approx(vapor, abs=1e-9)
    assert in_test[3] == pytest.approx(liquid_root, abs=1e-10)
    assert in_test[4] == pytest.approx(vapor_root, abs=1e-10)

    result = calculate_two_phase_flash(
        FluidMixture(
            tuple(
                MixtureComponent(component, fraction)
                for component, fraction in zip(components, feed, strict=True)
            )
        ),
        temperature_k,
        pressure_pa,
    )
    assert result.phase_stability.status is PhaseStabilityStatus.UNSTABLE
    assert result.phase_state is FlashPhaseState.TWO_PHASE
    assert result.convergence_status is FlashConvergenceStatus.CONVERGED
    assert result.liquid_phase is not None
    assert result.vapor_phase is not None
    assert result.vapor_fraction == pytest.approx(beta, abs=1e-8)
    assert result.liquid_phase.composition == pytest.approx(liquid, abs=1e-8)
    assert result.vapor_phase.composition == pytest.approx(vapor, abs=1e-8)
    assert result.liquid_phase.selected_compressibility_factor == pytest.approx(
        liquid_root, abs=1e-9
    )
    assert result.vapor_phase.selected_compressibility_factor == pytest.approx(
        vapor_root, abs=1e-9
    )
    assert (
        max(abs(value) for value in result.equilibrium_residuals if value is not None)
        <= FUGACITY_EQUILIBRIUM_TOLERANCE
    )
    assert (
        max(abs(value) for value in result.material_balance_residuals)
        <= MATERIAL_BALANCE_TOLERANCE
    )
