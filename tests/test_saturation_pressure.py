"""Tests for fixed-temperature bubble- and dew-pressure calculations."""

from dataclasses import FrozenInstanceError
from math import exp, fsum, isfinite, log
from time import perf_counter

import pytest
from scipy.optimize import brentq

import pvt_phase_simulator.eos.saturation_pressure as saturation_module
from pvt_phase_simulator.eos.flash import (
    FlashIteratePattern,
    PhaseInteractionProvenance,
    calculate_two_phase_flash,
    evaluate_flash_phase,
)
from pvt_phase_simulator.eos.mixing_rules import (
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
from pvt_phase_simulator.eos.phase_stability import PhaseTrialKind
from pvt_phase_simulator.eos.saturation_pressure import (
    FUGACITY_EQUILIBRIUM_TOLERANCE,
    SATURATION_OBJECTIVE_TOLERANCE,
    InnerSaturationStatus,
    SaturationKind,
    SaturationStatus,
    calculate_bubble_pressure_objective,
    calculate_dew_pressure_objective,
    calculate_saturation_pressure,
    calculate_wilson_pressure_estimates,
    evaluate_saturation_pressure,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    Component,
    FluidMixture,
    MixtureComponent,
)

BINARY_TEMPERATURE_K = 220.0
PURE_TEMPERATURE_K = 170.0
METHANE_PROPANE_TEMPERATURE_K = 250.0

BINARY_BUBBLE_PRESSURE_PA = 3_974_616.9589899518
BINARY_BUBBLE_VAPOR = (0.8485490339572008, 0.15145096604279926)
BINARY_BUBBLE_ROOTS = (0.12546185678633281, 0.664808266117495)
BINARY_DEW_PRESSURE_PA = 1_018_389.8672448754
BINARY_DEW_LIQUID = (0.07885037391071013, 0.92114962608929)
BINARY_DEW_ROOTS = (0.8756553803455087, 0.03113823915083837)
PURE_SATURATION_PRESSURE_PA = 2_348_696.105585
METHANE_PROPANE_BUBBLE_PRESSURE_PA = 7_385_216.135238511
METHANE_PROPANE_VAPOR = (0.9067198648233541, 0.09328013517664596)
TERNARY_BUBBLE_PRESSURE_PA = 4_784_010.455073108
TERNARY_DEW_PRESSURE_PA = 471_795.5444563909


def _binary_mixture() -> FluidMixture:
    return FluidMixture((MixtureComponent(METHANE, 0.5), MixtureComponent(ETHANE, 0.5)))


def _methane_propane_mixture() -> FluidMixture:
    return FluidMixture(
        (MixtureComponent(METHANE, 0.6), MixtureComponent(PROPANE, 0.4))
    )


def _ternary_mixture() -> FluidMixture:
    return FluidMixture(
        (
            MixtureComponent(METHANE, 0.6),
            MixtureComponent(ETHANE, 0.3),
            MixtureComponent(PROPANE, 0.1),
        )
    )


def _provenance(
    mixture: FluidMixture,
    temperature_k: float,
    pressure_pa: float = 1_000_000.0,
) -> PhaseInteractionProvenance:
    parameters = calculate_peng_robinson_mixture_parameters(
        mixture, temperature_k, pressure_pa
    )
    return PhaseInteractionProvenance(
        parameters.binary_interaction_policy,
        parameters.binary_interactions,
        parameters.supplied_binary_interaction_pairs,
        parameters.defaulted_binary_interaction_pairs,
    )


@pytest.fixture(scope="module")
def binary_bubble() -> saturation_module.SaturationPressureResult:
    return calculate_saturation_pressure(
        _binary_mixture(), BINARY_TEMPERATURE_K, SaturationKind.BUBBLE_POINT
    )


@pytest.fixture(scope="module")
def binary_dew() -> saturation_module.SaturationPressureResult:
    return calculate_saturation_pressure(
        _binary_mixture(), BINARY_TEMPERATURE_K, SaturationKind.DEW_POINT
    )


@pytest.fixture(scope="module")
def pure_results() -> tuple[
    saturation_module.SaturationPressureResult,
    saturation_module.SaturationPressureResult,
]:
    mixture = FluidMixture((MixtureComponent(METHANE, 1.0),))
    return (
        calculate_saturation_pressure(
            mixture, PURE_TEMPERATURE_K, SaturationKind.BUBBLE_POINT
        ),
        calculate_saturation_pressure(
            mixture, PURE_TEMPERATURE_K, SaturationKind.DEW_POINT
        ),
    )


def _independent_phase(
    components: tuple[Component, ...],
    composition: tuple[float, ...],
    temperature_k: float,
    pressure_pa: float,
    liquid: bool,
) -> tuple[float, tuple[float, ...]]:
    mixture = FluidMixture(
        tuple(
            MixtureComponent(component, fraction)
            for component, fraction in zip(components, composition, strict=True)
        )
    )
    parameters = calculate_peng_robinson_mixture_parameters(
        mixture, temperature_k, pressure_pa
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
    return root, tuple(item.log_fugacity_coefficient for item in results)


def _independent_saturation_reference(
    components: tuple[Component, ...],
    feed: tuple[float, ...],
    temperature_k: float,
    kind: SaturationKind,
    pressure_bracket: tuple[float, float],
) -> tuple[float, tuple[float, ...], float, float]:
    """Solve saturation independently of production Module 8 logic."""

    def normalize(log_k: tuple[float, ...]) -> tuple[float, ...]:
        direction = 1.0 if kind is SaturationKind.BUBBLE_POINT else -1.0
        logs = tuple(
            log(fraction) + direction * value
            for fraction, value in zip(feed, log_k, strict=True)
        )
        largest = max(logs)
        weights = tuple(exp(value - largest) for value in logs)
        total = fsum(weights)
        return tuple(value / total for value in weights)

    def pressure_objective(
        pressure_pa: float,
        details: bool = False,
    ) -> float | tuple[float, tuple[float, ...], float, float]:
        log_k = tuple(
            log(component.critical_pressure_pa / pressure_pa)
            + 5.373
            * (1.0 + component.acentric_factor)
            * (1.0 - component.critical_temperature_k / temperature_k)
            for component in components
        )
        parent_root, parent_log_phi = _independent_phase(
            components,
            feed,
            temperature_k,
            pressure_pa,
            kind is SaturationKind.BUBBLE_POINT,
        )
        incipient_root = 0.0
        incipient = feed
        for _ in range(400):
            incipient = normalize(log_k)
            incipient_root, incipient_log_phi = _independent_phase(
                components,
                incipient,
                temperature_k,
                pressure_pa,
                kind is SaturationKind.DEW_POINT,
            )
            liquid_log_phi, vapor_log_phi = (
                (parent_log_phi, incipient_log_phi)
                if kind is SaturationKind.BUBBLE_POINT
                else (incipient_log_phi, parent_log_phi)
            )
            updated = tuple(
                liquid - vapor
                for liquid, vapor in zip(liquid_log_phi, vapor_log_phi, strict=True)
            )
            if (
                max(abs(new - old) for new, old in zip(updated, log_k, strict=True))
                < 1e-13
            ):
                log_k = updated
                break
            log_k = updated
        direction = 1.0 if kind is SaturationKind.BUBBLE_POINT else -1.0
        objective = (
            fsum(
                fraction * exp(direction * value)
                for fraction, value in zip(feed, log_k, strict=True)
            )
            - 1.0
        )
        if details:
            return objective, incipient, parent_root, incipient_root
        return objective

    log_pressure = brentq(
        lambda value: float(pressure_objective(exp(value))),
        log(pressure_bracket[0]),
        log(pressure_bracket[1]),
        xtol=5e-15,
        rtol=1e-14,
    )
    pressure = exp(log_pressure)
    details = pressure_objective(pressure, True)
    if not isinstance(details, tuple):
        raise AssertionError("independent reference details are required.")
    return pressure, details[1], details[2], details[3]


def _independent_pure_saturation_pressure() -> float:
    """Solve pure-methane coexistence from distinct Module 4--5 roots."""

    mixture = FluidMixture((MixtureComponent(METHANE, 1.0),))

    def residual(pressure_pa: float) -> float:
        parameters = calculate_peng_robinson_mixture_parameters(
            mixture, PURE_TEMPERATURE_K, pressure_pa
        )
        roots = tuple(
            root
            for root in calculate_compressibility_roots(
                parameters.A_mix, parameters.B_mix
            )
            if classify_mechanical_stability(
                root, parameters.A_mix, parameters.B_mix
            ).classification
            is MechanicalStabilityClassification.STABLE
        )
        liquid = calculate_mixture_fugacity_coefficients(parameters, min(roots))[0]
        vapor = calculate_mixture_fugacity_coefficients(parameters, max(roots))[0]
        return liquid.log_fugacity_coefficient - vapor.log_fugacity_coefficient

    return brentq(residual, 2_200_000.0, 2_500_000.0, xtol=1e-7, rtol=1e-13)


@pytest.mark.parametrize("temperature_k", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_temperature_is_rejected(temperature_k: float) -> None:
    with pytest.raises(ValueError):
        calculate_saturation_pressure(
            _binary_mixture(), temperature_k, SaturationKind.BUBBLE_POINT
        )


@pytest.mark.parametrize(
    ("minimum_pressure_pa", "maximum_pressure_pa"),
    [
        (0.0, 1.0e6),
        (-1.0, 1.0e6),
        (1.0e6, 1.0e6),
        (2.0e6, 1.0e6),
        (float("nan"), 1.0e6),
        (1.0e3, float("inf")),
    ],
)
def test_invalid_pressure_bounds_are_rejected(
    minimum_pressure_pa: float,
    maximum_pressure_pa: float,
) -> None:
    with pytest.raises(ValueError):
        calculate_saturation_pressure(
            _binary_mixture(),
            BINARY_TEMPERATURE_K,
            SaturationKind.BUBBLE_POINT,
            minimum_pressure_pa,
            maximum_pressure_pa,
        )


def test_invalid_saturation_kind_is_rejected() -> None:
    with pytest.raises(ValueError, match="SaturationKind"):
        calculate_saturation_pressure(
            _binary_mixture(),
            BINARY_TEMPERATURE_K,
            "bubble",  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"pressure_search_points": 2},
        {"maximum_outer_iterations": 0},
        {"maximum_inner_iterations": 0},
    ],
)
def test_invalid_iteration_controls_are_rejected(changes: dict[str, int]) -> None:
    expected_name = next(iter(changes))
    with pytest.raises(ValueError, match=expected_name):
        calculate_saturation_pressure(
            _binary_mixture(),
            BINARY_TEMPERATURE_K,
            SaturationKind.BUBBLE_POINT,
            **changes,  # type: ignore[arg-type]
        )


def test_minimum_pressure_search_grid_is_accepted() -> None:
    result = calculate_saturation_pressure(
        _binary_mixture(),
        BINARY_TEMPERATURE_K,
        SaturationKind.BUBBLE_POINT,
        pressure_search_points=3,
    )
    assert isinstance(result, saturation_module.SaturationPressureResult)


def test_inner_evaluation_rejects_zero_iterations_at_validation_boundary() -> None:
    mixture = _binary_mixture()
    with pytest.raises(ValueError, match="maximum_iterations"):
        evaluate_saturation_pressure(
            mixture,
            BINARY_TEMPERATURE_K,
            BINARY_BUBBLE_PRESSURE_PA,
            SaturationKind.BUBBLE_POINT,
            _provenance(
                mixture,
                BINARY_TEMPERATURE_K,
                BINARY_BUBBLE_PRESSURE_PA,
            ),
            maximum_iterations=0,
        )


@pytest.mark.parametrize(
    ("objective", "composition", "k_values"),
    [
        (calculate_bubble_pressure_objective, (), ()),
        (calculate_dew_pressure_objective, (), ()),
        (calculate_bubble_pressure_objective, (0.5, 0.5), (2.0,)),
        (calculate_dew_pressure_objective, (0.5, 0.5), (2.0,)),
        (calculate_bubble_pressure_objective, (-0.1, 1.1), (2.0, 0.5)),
        (calculate_dew_pressure_objective, (-0.1, 1.1), (2.0, 0.5)),
        (calculate_bubble_pressure_objective, (0.6, 0.5), (2.0, 0.5)),
        (calculate_dew_pressure_objective, (0.6, 0.5), (2.0, 0.5)),
    ],
)
def test_pressure_objectives_reject_invalid_inputs(
    objective: object,
    composition: tuple[float, ...],
    k_values: tuple[float, ...],
) -> None:
    expected = "non-empty" if not composition else "aligned|non-negative|sum to one"
    with pytest.raises(ValueError, match=expected):
        objective(composition, k_values)  # type: ignore[operator]


def test_inner_evaluation_rejects_misaligned_log_k_seed_directly() -> None:
    mixture = _binary_mixture()
    with pytest.raises(ValueError, match="aligned immutable tuple"):
        evaluate_saturation_pressure(
            mixture,
            BINARY_TEMPERATURE_K,
            BINARY_BUBBLE_PRESSURE_PA,
            SaturationKind.BUBBLE_POINT,
            _provenance(
                mixture,
                BINARY_TEMPERATURE_K,
                BINARY_BUBBLE_PRESSURE_PA,
            ),
            initial_log_k_values=(0.0,),
        )


def test_log_objective_ignores_zero_feed_support() -> None:
    objective = saturation_module._saturation_objective_from_log_k(
        (1.0, 0.0),
        (0.0, 1_000.0),
        SaturationKind.BUBBLE_POINT,
    )
    assert objective == 0.0


def test_result_models_are_immutable(
    binary_bubble: saturation_module.SaturationPressureResult,
) -> None:
    with pytest.raises(FrozenInstanceError):
        binary_bubble.pressure_pa = 1.0  # type: ignore[misc]


def test_calculation_does_not_mutate_feed(
    binary_bubble: saturation_module.SaturationPressureResult,
) -> None:
    mixture = _binary_mixture()
    original = mixture.components
    result = calculate_saturation_pressure(
        mixture, BINARY_TEMPERATURE_K, SaturationKind.BUBBLE_POINT
    )
    assert mixture.components == original
    assert result.feed_mixture is mixture
    assert result.pressure_pa == pytest.approx(binary_bubble.pressure_pa)


def test_interaction_provenance_is_preserved_and_mismatch_fails() -> None:
    mixture = _binary_mixture()
    interactions = {
        ("Methane", "Ethane"): 0.03,
        ("Ethane", "Methane"): 0.03,
    }
    result = calculate_saturation_pressure(
        mixture,
        BINARY_TEMPERATURE_K,
        SaturationKind.BUBBLE_POINT,
        binary_interactions=interactions,
    )
    assert result.binary_interactions == (("Ethane", "Methane", 0.03),)
    provenance = _provenance(mixture, BINARY_TEMPERATURE_K)
    evaluation = evaluate_saturation_pressure(
        mixture,
        BINARY_TEMPERATURE_K,
        BINARY_BUBBLE_PRESSURE_PA,
        SaturationKind.BUBBLE_POINT,
        provenance,
        interactions,
    )
    assert evaluation.status is InnerSaturationStatus.FAILED
    assert evaluation.failure_reason is not None
    assert "provenance" in evaluation.failure_reason.lower()


def test_direct_phase_provenance_matches_backward_compatible_path() -> None:
    mixture = _binary_mixture()
    pressure = BINARY_BUBBLE_PRESSURE_PA
    provenance = _provenance(mixture, BINARY_TEMPERATURE_K, pressure)
    direct = evaluate_flash_phase(
        mixture,
        (0.5, 0.5),
        BINARY_TEMPERATURE_K,
        pressure,
        PhaseTrialKind.LIQUID_LIKE,
        interaction_provenance=provenance,
    )
    assert direct.composition == (0.5, 0.5)
    assert direct.selected_compressibility_factor == pytest.approx(
        BINARY_BUBBLE_ROOTS[0], abs=2e-12
    )


def test_wilson_estimates_match_independent_expressions() -> None:
    mixture = _binary_mixture()
    result = calculate_wilson_pressure_estimates(mixture, BINARY_TEMPERATURE_K)
    factors = tuple(
        component.component.critical_pressure_pa
        * exp(
            5.373
            * (1.0 + component.component.acentric_factor)
            * (1.0 - component.component.critical_temperature_k / BINARY_TEMPERATURE_K)
        )
        for component in mixture.components
    )
    expected_bubble = fsum(
        item.mole_fraction * factor
        for item, factor in zip(mixture.components, factors, strict=True)
    )
    expected_dew = 1.0 / fsum(
        item.mole_fraction / factor
        for item, factor in zip(mixture.components, factors, strict=True)
    )
    assert result.component_pressure_factors_pa == pytest.approx(factors)
    assert result.bubble_pressure_pa == pytest.approx(expected_bubble, rel=2e-15)
    assert result.dew_pressure_pa == pytest.approx(expected_dew, rel=2e-15)
    assert all(isfinite(value) and value > 0.0 for value in factors)


def test_wilson_estimates_preserve_zero_feed_support() -> None:
    mixture = FluidMixture(
        (
            MixtureComponent(METHANE, 0.5),
            MixtureComponent(ETHANE, 0.5),
            MixtureComponent(PROPANE, 0.0),
        )
    )
    result = calculate_wilson_pressure_estimates(mixture, BINARY_TEMPERATURE_K)
    binary = calculate_wilson_pressure_estimates(
        _binary_mixture(), BINARY_TEMPERATURE_K
    )
    assert len(result.component_pressure_factors_pa) == 3
    assert result.bubble_pressure_pa == pytest.approx(binary.bubble_pressure_pa)
    assert result.dew_pressure_pa == pytest.approx(binary.dew_pressure_pa)


def test_objective_functions_are_independently_calculable() -> None:
    composition = (0.7, 0.3)
    k_values = (1.4, 0.4)
    assert calculate_bubble_pressure_objective(composition, k_values) == pytest.approx(
        0.1
    )
    assert calculate_dew_pressure_objective(composition, k_values) == pytest.approx(
        0.7 / 1.4 + 0.3 / 0.4 - 1.0
    )


def test_binary_bubble_point_matches_independent_reference(
    binary_bubble: saturation_module.SaturationPressureResult,
) -> None:
    independent = _independent_saturation_reference(
        (METHANE, ETHANE),
        (0.5, 0.5),
        BINARY_TEMPERATURE_K,
        SaturationKind.BUBBLE_POINT,
        (3.5e6, 4.2e6),
    )
    assert binary_bubble.status is SaturationStatus.CONVERGED
    assert binary_bubble.pressure_pa == pytest.approx(independent[0], abs=2e-6)
    assert binary_bubble.incipient_composition == pytest.approx(
        independent[1], abs=2e-10
    )
    assert binary_bubble.parent_phase is not None
    assert binary_bubble.incipient_phase is not None
    assert binary_bubble.parent_phase.selected_compressibility_factor == pytest.approx(
        independent[2], abs=2e-10
    )
    assert (
        binary_bubble.incipient_phase.selected_compressibility_factor
        == pytest.approx(independent[3], abs=2e-10)
    )


def test_binary_bubble_state_satisfies_all_contracts(
    binary_bubble: saturation_module.SaturationPressureResult,
) -> None:
    assert binary_bubble.parent_composition == (0.5, 0.5)
    assert fsum(binary_bubble.incipient_composition) == pytest.approx(1.0, abs=1e-14)
    assert binary_bubble.incipient_composition == pytest.approx(
        BINARY_BUBBLE_VAPOR, abs=2e-10
    )
    assert binary_bubble.maximum_fugacity_equilibrium_residual is not None
    assert (
        binary_bubble.maximum_fugacity_equilibrium_residual
        <= FUGACITY_EQUILIBRIUM_TOLERANCE
    )
    assert binary_bubble.pressure_residual is not None
    assert abs(binary_bubble.pressure_residual) <= SATURATION_OBJECTIVE_TOLERANCE
    assert binary_bubble.parent_phase is not None
    assert binary_bubble.incipient_phase is not None
    assert binary_bubble.parent_phase.selected_compressibility_factor == min(
        candidate.compressibility_factor
        for candidate in binary_bubble.parent_phase.root_selection.candidates
        if candidate.classification is MechanicalStabilityClassification.STABLE
    )
    assert binary_bubble.incipient_phase.selected_compressibility_factor == max(
        candidate.compressibility_factor
        for candidate in binary_bubble.incipient_phase.root_selection.candidates
        if candidate.classification is MechanicalStabilityClassification.STABLE
    )


def test_active_fugacity_residuals_are_preserved_and_aggregated(
    binary_bubble: saturation_module.SaturationPressureResult,
) -> None:
    final_iteration = binary_bubble.evaluation_history[-1]
    residuals = final_iteration.fugacity_equilibrium_residuals
    assert all(value is not None for value in residuals)
    active_residuals = tuple(abs(value) for value in residuals if value is not None)
    assert final_iteration.history[-1].maximum_fugacity_equilibrium_residual == max(
        active_residuals
    )


def test_binary_bubble_is_deterministic(
    binary_bubble: saturation_module.SaturationPressureResult,
) -> None:
    repeated = calculate_saturation_pressure(
        _binary_mixture(), BINARY_TEMPERATURE_K, SaturationKind.BUBBLE_POINT
    )
    assert repeated.pressure_pa == binary_bubble.pressure_pa
    assert repeated.incipient_composition == binary_bubble.incipient_composition
    assert repeated.k_values == binary_bubble.k_values


def test_binary_dew_point_matches_independent_reference(
    binary_dew: saturation_module.SaturationPressureResult,
) -> None:
    independent = _independent_saturation_reference(
        (METHANE, ETHANE),
        (0.5, 0.5),
        BINARY_TEMPERATURE_K,
        SaturationKind.DEW_POINT,
        (0.8e6, 1.2e6),
    )
    assert binary_dew.status is SaturationStatus.CONVERGED
    assert binary_dew.pressure_pa == pytest.approx(independent[0], abs=2e-6)
    assert binary_dew.incipient_composition == pytest.approx(independent[1], abs=2e-10)
    assert binary_dew.parent_phase is not None
    assert binary_dew.incipient_phase is not None
    assert binary_dew.parent_phase.selected_compressibility_factor == pytest.approx(
        independent[2], abs=2e-10
    )
    assert binary_dew.incipient_phase.selected_compressibility_factor == pytest.approx(
        independent[3], abs=2e-10
    )


def test_binary_dew_state_satisfies_all_contracts(
    binary_dew: saturation_module.SaturationPressureResult,
) -> None:
    assert binary_dew.parent_composition == (0.5, 0.5)
    assert fsum(binary_dew.incipient_composition) == pytest.approx(1.0, abs=1e-14)
    assert binary_dew.incipient_composition == pytest.approx(
        BINARY_DEW_LIQUID, abs=2e-10
    )
    assert binary_dew.maximum_fugacity_equilibrium_residual is not None
    assert (
        binary_dew.maximum_fugacity_equilibrium_residual
        <= FUGACITY_EQUILIBRIUM_TOLERANCE
    )
    assert binary_dew.pressure_residual is not None
    assert abs(binary_dew.pressure_residual) <= SATURATION_OBJECTIVE_TOLERANCE
    assert binary_dew.parent_phase is not None
    assert binary_dew.incipient_phase is not None
    assert binary_dew.parent_phase.selected_compressibility_factor == max(
        candidate.compressibility_factor
        for candidate in binary_dew.parent_phase.root_selection.candidates
        if candidate.classification is MechanicalStabilityClassification.STABLE
    )
    assert binary_dew.incipient_phase.selected_compressibility_factor == min(
        candidate.compressibility_factor
        for candidate in binary_dew.incipient_phase.root_selection.candidates
        if candidate.classification is MechanicalStabilityClassification.STABLE
    )


def test_binary_dew_is_deterministic(
    binary_dew: saturation_module.SaturationPressureResult,
) -> None:
    repeated = calculate_saturation_pressure(
        _binary_mixture(), BINARY_TEMPERATURE_K, SaturationKind.DEW_POINT
    )
    assert repeated.pressure_pa == binary_dew.pressure_pa
    assert repeated.incipient_composition == binary_dew.incipient_composition
    assert repeated.k_values == binary_dew.k_values


def test_pure_component_bubble_and_dew_equal_independent_coexistence(
    pure_results: tuple[
        saturation_module.SaturationPressureResult,
        saturation_module.SaturationPressureResult,
    ],
) -> None:
    bubble, dew = pure_results
    independent = _independent_pure_saturation_pressure()
    assert bubble.status is SaturationStatus.CONVERGED
    assert dew.status is SaturationStatus.CONVERGED
    assert bubble.pressure_pa == pytest.approx(independent, abs=2e-5)
    assert dew.pressure_pa == pytest.approx(independent, abs=2e-5)
    assert bubble.pressure_pa == pytest.approx(dew.pressure_pa, abs=2e-5)
    assert bubble.incipient_composition == (1.0,)
    assert dew.incipient_composition == (1.0,)
    assert bubble.parent_phase is not None and bubble.incipient_phase is not None
    assert (
        abs(
            bubble.parent_phase.selected_compressibility_factor
            - bubble.incipient_phase.selected_compressibility_factor
        )
        > 0.5
    )


def test_module_7_flash_approaches_bubble_from_two_phase_side(
    binary_bubble: saturation_module.SaturationPressureResult,
) -> None:
    assert binary_bubble.pressure_pa is not None
    flash = calculate_two_phase_flash(
        _binary_mixture(), BINARY_TEMPERATURE_K, binary_bubble.pressure_pa * 0.999
    )
    assert flash.vapor_fraction is not None
    assert 0.0 < flash.vapor_fraction < 0.003
    assert flash.liquid_phase is not None and flash.vapor_phase is not None
    assert flash.liquid_phase.composition == pytest.approx((0.5, 0.5), abs=7e-4)
    assert flash.vapor_phase.composition == pytest.approx(
        binary_bubble.incipient_composition, abs=2e-4
    )


def test_module_7_flash_approaches_dew_from_two_phase_side(
    binary_dew: saturation_module.SaturationPressureResult,
) -> None:
    assert binary_dew.pressure_pa is not None
    flash = calculate_two_phase_flash(
        _binary_mixture(), BINARY_TEMPERATURE_K, binary_dew.pressure_pa * 1.001
    )
    assert flash.vapor_fraction is not None
    assert 0.997 < flash.vapor_fraction < 1.0
    assert flash.liquid_phase is not None and flash.vapor_phase is not None
    assert flash.vapor_phase.composition == pytest.approx((0.5, 0.5), abs=7e-4)
    assert flash.liquid_phase.composition == pytest.approx(
        binary_dew.incipient_composition, abs=2e-4
    )


def test_methane_propane_bubble_matches_independent_reference() -> None:
    result = calculate_saturation_pressure(
        _methane_propane_mixture(),
        METHANE_PROPANE_TEMPERATURE_K,
        SaturationKind.BUBBLE_POINT,
    )
    independent = _independent_saturation_reference(
        (METHANE, PROPANE),
        (0.6, 0.4),
        METHANE_PROPANE_TEMPERATURE_K,
        SaturationKind.BUBBLE_POINT,
        (7.0e6, 7.8e6),
    )
    assert result.status is SaturationStatus.CONVERGED
    assert result.pressure_pa == pytest.approx(
        METHANE_PROPANE_BUBBLE_PRESSURE_PA, abs=3e-5
    )
    assert result.pressure_pa == pytest.approx(independent[0], abs=3e-5)
    assert result.incipient_composition == pytest.approx(
        METHANE_PROPANE_VAPOR, abs=2e-10
    )


@pytest.mark.parametrize(
    ("kind", "expected_pressure"),
    [
        (SaturationKind.BUBBLE_POINT, TERNARY_BUBBLE_PRESSURE_PA),
        (SaturationKind.DEW_POINT, TERNARY_DEW_PRESSURE_PA),
    ],
)
def test_ternary_saturation_matches_independent_reference(
    kind: SaturationKind,
    expected_pressure: float,
) -> None:
    result = calculate_saturation_pressure(
        _ternary_mixture(), BINARY_TEMPERATURE_K, kind
    )
    bracket = (4.4e6, 5.1e6) if kind is SaturationKind.BUBBLE_POINT else (0.4e6, 0.6e6)
    independent = _independent_saturation_reference(
        (METHANE, ETHANE, PROPANE),
        (0.6, 0.3, 0.1),
        BINARY_TEMPERATURE_K,
        kind,
        bracket,
    )
    assert result.status is SaturationStatus.CONVERGED
    assert result.pressure_pa == pytest.approx(expected_pressure, abs=3e-5)
    assert result.pressure_pa == pytest.approx(independent[0], abs=3e-5)
    assert result.incipient_composition == pytest.approx(independent[1], abs=3e-10)


def test_pressure_search_expands_from_wilson_center_and_preserves_bracket(
    binary_bubble: saturation_module.SaturationPressureResult,
) -> None:
    assert binary_bubble.bracket_pressures_pa is not None
    assert binary_bubble.bracket_objective_values is not None
    lower, upper = binary_bubble.bracket_pressures_pa
    left, right = binary_bubble.bracket_objective_values
    assert upper < binary_bubble.initial_pressure_estimate_pa
    assert lower < BINARY_BUBBLE_PRESSURE_PA < upper
    assert left * right < 0.0
    assert len(binary_bubble.evaluation_history) > 81


def test_bracket_failure_returns_not_found() -> None:
    result = calculate_saturation_pressure(
        _binary_mixture(),
        BINARY_TEMPERATURE_K,
        SaturationKind.BUBBLE_POINT,
        1_000.0,
        10_000.0,
    )
    assert result.status is SaturationStatus.NOT_FOUND
    assert result.pressure_pa is None
    assert result.failure_reason is not None
    assert "bracket" in result.failure_reason.lower()


def test_inner_non_convergence_preserves_history() -> None:
    evaluation = evaluate_saturation_pressure(
        _binary_mixture(),
        BINARY_TEMPERATURE_K,
        3_500_000.0,
        SaturationKind.BUBBLE_POINT,
        _provenance(_binary_mixture(), BINARY_TEMPERATURE_K),
        maximum_iterations=1,
    )
    assert evaluation.status is InnerSaturationStatus.NOT_CONVERGED
    assert not evaluation.converged
    assert len(evaluation.history) == 1
    assert evaluation.failure_reason is not None


def test_marginal_or_missing_stable_root_is_not_converted_to_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_phase(*args: object, **kwargs: object) -> None:
        raise ValueError("Only marginal roots are available; no stable root.")

    monkeypatch.setattr(saturation_module, "evaluate_flash_phase", reject_phase)
    evaluation = evaluate_saturation_pressure(
        _binary_mixture(),
        BINARY_TEMPERATURE_K,
        BINARY_BUBBLE_PRESSURE_PA,
        SaturationKind.BUBBLE_POINT,
        _provenance(_binary_mixture(), BINARY_TEMPERATURE_K),
    )
    assert evaluation.status is InnerSaturationStatus.FAILED
    assert not evaluation.converged
    assert evaluation.parent_phase is None
    assert evaluation.failure_reason is not None
    assert "marginal" in evaluation.failure_reason.lower()


@pytest.mark.parametrize(
    "pattern", [FlashIteratePattern.OSCILLATION, FlashIteratePattern.STAGNATION]
)
def test_inner_iterate_failures_are_explicit(
    monkeypatch: pytest.MonkeyPatch,
    pattern: FlashIteratePattern,
) -> None:
    monkeypatch.setattr(
        saturation_module,
        "detect_flash_iterate_pattern",
        lambda *args, **kwargs: pattern,
    )
    evaluation = evaluate_saturation_pressure(
        _binary_mixture(),
        BINARY_TEMPERATURE_K,
        3_500_000.0,
        SaturationKind.BUBBLE_POINT,
        _provenance(_binary_mixture(), BINARY_TEMPERATURE_K),
    )
    assert evaluation.status is InnerSaturationStatus.FAILED
    assert not evaluation.converged
    assert evaluation.failure_reason is not None
    expected_word = (
        "oscillation" if pattern is FlashIteratePattern.OSCILLATION else "stagnat"
    )
    assert expected_word in evaluation.failure_reason.lower()


def test_outer_pressure_progress_cannot_mask_inner_non_convergence() -> None:
    result = calculate_saturation_pressure(
        _binary_mixture(),
        BINARY_TEMPERATURE_K,
        SaturationKind.BUBBLE_POINT,
        maximum_inner_iterations=1,
    )
    assert result.status is SaturationStatus.NOT_FOUND
    assert result.pressure_pa is None
    assert all(not evaluation.converged for evaluation in result.evaluation_history)


def test_outer_iteration_limit_cannot_be_reported_as_converged() -> None:
    result = calculate_saturation_pressure(
        _binary_mixture(),
        BINARY_TEMPERATURE_K,
        SaturationKind.BUBBLE_POINT,
        maximum_outer_iterations=1,
    )
    assert result.status is SaturationStatus.INCONCLUSIVE
    assert result.pressure_pa is None
    assert result.failure_reason is not None
    assert "iteration limit" in result.failure_reason.lower()


@pytest.mark.parametrize(
    "kind", [SaturationKind.BUBBLE_POINT, SaturationKind.DEW_POINT]
)
def test_final_state_is_reconstructed_and_self_consistent(
    kind: SaturationKind,
    binary_bubble: saturation_module.SaturationPressureResult,
    binary_dew: saturation_module.SaturationPressureResult,
) -> None:
    result = binary_bubble if kind is SaturationKind.BUBBLE_POINT else binary_dew
    assert result.pressure_pa is not None
    assert result.parent_phase is not None and result.incipient_phase is not None
    assert result.evaluation_history[-1].pressure_pa == result.pressure_pa
    assert result.evaluation_history[-1].k_values == result.k_values
    liquid_log_phi, vapor_log_phi = (
        (
            result.parent_phase.component_log_fugacity_coefficients,
            result.incipient_phase.component_log_fugacity_coefficients,
        )
        if kind is SaturationKind.BUBBLE_POINT
        else (
            result.incipient_phase.component_log_fugacity_coefficients,
            result.parent_phase.component_log_fugacity_coefficients,
        )
    )
    expected_k = tuple(
        exp(liquid - vapor)
        for liquid, vapor in zip(liquid_log_phi, vapor_log_phi, strict=True)
    )
    assert result.k_values == pytest.approx(expected_k, rel=2e-10)
    objective = (
        calculate_bubble_pressure_objective
        if kind is SaturationKind.BUBBLE_POINT
        else calculate_dew_pressure_objective
    )
    assert objective(result.feed_composition, result.k_values) == pytest.approx(
        result.pressure_residual, abs=2e-10
    )


METHANE_PROPANE_DEW_PRESSURE_PA = 575_969.512449
METHANE_PROPANE_DEW_LIQUID = (0.033608972987924916, 0.9663910270120751)
METHANE_PROPANE_DEW_ROOTS = (0.9375620580537904, 0.020307992099381264)
ETHANE_PURE_TEMPERATURE_K = 250.0


def test_methane_propane_dew_is_not_a_trivial_solution() -> None:
    """A trivial state must never be reported as a saturation pressure.

    Every ``K_i`` at unity makes ``sum(z_i/K_i) - 1`` identically zero at any
    single-phase pressure, so the objective alone cannot distinguish it from a
    dew point. This state previously converged at 4_869_675 Pa with the
    incipient composition equal to the feed, all K-values at unity, and both
    phases on the same compressibility root.
    """

    result = calculate_saturation_pressure(
        _methane_propane_mixture(),
        METHANE_PROPANE_TEMPERATURE_K,
        SaturationKind.DEW_POINT,
    )
    assert result.status is SaturationStatus.CONVERGED
    assert result.pressure_pa is not None
    assert result.pressure_pa == pytest.approx(
        METHANE_PROPANE_DEW_PRESSURE_PA, rel=1e-9
    )
    assert result.incipient_composition == pytest.approx(
        METHANE_PROPANE_DEW_LIQUID, abs=2e-9
    )
    assert result.parent_phase is not None
    assert result.incipient_phase is not None
    assert result.parent_phase.selected_compressibility_factor == pytest.approx(
        METHANE_PROPANE_DEW_ROOTS[0], abs=2e-10
    )
    assert result.incipient_phase.selected_compressibility_factor == pytest.approx(
        METHANE_PROPANE_DEW_ROOTS[1], abs=2e-10
    )
    # the incipient phase must be genuinely distinct from the parent
    assert (
        max(
            abs(parent - trial)
            for parent, trial in zip(
                result.feed_composition, result.incipient_composition, strict=True
            )
        )
        > 1e-3
    )
    assert max(abs(value - 1.0) for value in result.k_values) > 1e-3
    assert (
        abs(
            result.parent_phase.selected_compressibility_factor
            - result.incipient_phase.selected_compressibility_factor
        )
        > 0.5
    )


def test_unity_equilibrium_ratios_are_rejected_as_trivial() -> None:
    """The inner solve must refuse a state whose active K-values are all one."""

    mixture = _methane_propane_mixture()
    evaluation = evaluate_saturation_pressure(
        mixture,
        METHANE_PROPANE_TEMPERATURE_K,
        4_869_675.25165864,
        SaturationKind.DEW_POINT,
        _provenance(mixture, METHANE_PROPANE_TEMPERATURE_K),
    )
    assert not evaluation.converged
    assert evaluation.status is InnerSaturationStatus.FAILED
    assert evaluation.failure_reason is not None
    assert "trivial" in evaluation.failure_reason.lower()


def test_pure_component_unity_k_is_not_treated_as_trivial(
    pure_results: tuple[
        saturation_module.SaturationPressureResult,
        saturation_module.SaturationPressureResult,
    ],
) -> None:
    """K = 1 is a pure component's genuine saturation condition, not degeneracy."""

    bubble, _ = pure_results
    assert bubble.status is SaturationStatus.CONVERGED
    assert bubble.k_values == pytest.approx((1.0,), abs=1e-9)


def test_second_pure_component_matches_independent_coexistence() -> None:
    mixture = FluidMixture((MixtureComponent(ETHANE, 1.0),))

    def residual(pressure_pa: float) -> float:
        parameters = calculate_peng_robinson_mixture_parameters(
            mixture, ETHANE_PURE_TEMPERATURE_K, pressure_pa
        )
        roots = tuple(
            root
            for root in calculate_compressibility_roots(
                parameters.A_mix, parameters.B_mix
            )
            if classify_mechanical_stability(
                root, parameters.A_mix, parameters.B_mix
            ).classification
            is MechanicalStabilityClassification.STABLE
        )
        liquid = calculate_mixture_fugacity_coefficients(parameters, min(roots))[0]
        vapor = calculate_mixture_fugacity_coefficients(parameters, max(roots))[0]
        return liquid.log_fugacity_coefficient - vapor.log_fugacity_coefficient

    independent = brentq(residual, 1.0e6, 1.6e6, xtol=1e-7, rtol=1e-13)
    bubble = calculate_saturation_pressure(
        mixture, ETHANE_PURE_TEMPERATURE_K, SaturationKind.BUBBLE_POINT
    )
    dew = calculate_saturation_pressure(
        mixture, ETHANE_PURE_TEMPERATURE_K, SaturationKind.DEW_POINT
    )
    assert bubble.status is SaturationStatus.CONVERGED
    assert dew.status is SaturationStatus.CONVERGED
    assert bubble.pressure_pa == pytest.approx(independent, rel=1e-9)
    assert dew.pressure_pa == pytest.approx(bubble.pressure_pa, rel=1e-12)


def test_one_exact_hit_plus_a_separate_bracket_is_inconclusive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two distinct apparent roots must never be silently reduced to one.

    Disabling only the unity-K trivial rejection restores a spurious exact grid
    hit alongside the genuine bracket. The result must be INCONCLUSIVE, not the
    arbitrary selection of whichever root was found first.
    """

    monkeypatch.setattr(saturation_module, "TRIVIAL_LOG_K_TOLERANCE", -1.0)
    monkeypatch.setattr(saturation_module, "NEAR_TRIVIAL_LOG_K_TOLERANCE", -1.0)
    monkeypatch.setattr(saturation_module, "NEAR_TRIVIAL_COMPOSITION_TOLERANCE", -1.0)
    monkeypatch.setattr(saturation_module, "NEAR_TRIVIAL_ROOT_TOLERANCE", -1.0)
    result = calculate_saturation_pressure(
        _methane_propane_mixture(),
        METHANE_PROPANE_TEMPERATURE_K,
        SaturationKind.DEW_POINT,
    )
    assert result.status is SaturationStatus.INCONCLUSIVE
    assert result.pressure_pa is None
    assert result.failure_reason is not None
    assert "multiple" in result.failure_reason.lower()


@pytest.mark.parametrize("offset", [1e-2, 1e-3, 1e-4, 1e-5])
def test_module_7_dew_endpoint_trend_over_several_offsets(offset: float) -> None:
    """Below a dew point the flash must be two-phase with beta approaching one."""

    mixture = _methane_propane_mixture()
    result = calculate_saturation_pressure(
        mixture, METHANE_PROPANE_TEMPERATURE_K, SaturationKind.DEW_POINT
    )
    assert result.pressure_pa is not None
    flash = calculate_two_phase_flash(
        mixture, METHANE_PROPANE_TEMPERATURE_K, result.pressure_pa * (1.0 + offset)
    )
    assert flash.vapor_fraction is not None
    assert 1.0 - 10.0 * offset < flash.vapor_fraction < 1.0
    assert flash.vapor_phase is not None
    assert flash.liquid_phase is not None
    assert flash.vapor_phase.composition == pytest.approx((0.6, 0.4), abs=20.0 * offset)
    assert flash.liquid_phase.composition == pytest.approx(
        result.incipient_composition, abs=20.0 * offset
    )


def test_bubble_pressure_is_not_below_dew_pressure() -> None:
    for mixture, temperature_k in (
        (_binary_mixture(), BINARY_TEMPERATURE_K),
        (_methane_propane_mixture(), METHANE_PROPANE_TEMPERATURE_K),
        (_ternary_mixture(), BINARY_TEMPERATURE_K),
    ):
        bubble = calculate_saturation_pressure(
            mixture, temperature_k, SaturationKind.BUBBLE_POINT
        )
        dew = calculate_saturation_pressure(
            mixture, temperature_k, SaturationKind.DEW_POINT
        )
        assert bubble.status is SaturationStatus.CONVERGED
        assert dew.status is SaturationStatus.CONVERGED
        assert bubble.pressure_pa is not None and dew.pressure_pa is not None
        assert bubble.pressure_pa > dew.pressure_pa


def test_saturation_workflow_has_acceptable_runtime() -> None:
    started = perf_counter()
    bubble = calculate_saturation_pressure(
        _binary_mixture(),
        BINARY_TEMPERATURE_K,
        SaturationKind.BUBBLE_POINT,
        pressure_search_points=31,
    )
    dew = calculate_saturation_pressure(
        _binary_mixture(),
        BINARY_TEMPERATURE_K,
        SaturationKind.DEW_POINT,
        pressure_search_points=31,
    )
    elapsed = perf_counter() - started
    assert bubble.status is SaturationStatus.CONVERGED
    assert dew.status is SaturationStatus.CONVERGED
    assert elapsed < 15.0
