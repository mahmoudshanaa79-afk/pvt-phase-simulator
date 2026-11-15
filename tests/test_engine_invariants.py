"""Thermodynamic invariants of engine results, checked independently.

These tests only read and call the frozen engine. Each converged result is
checked against quantities recomputed here from the engine's public
equation-of-state functions, using the engine's own tolerances:

- flash: material balance, normalized phase compositions, equal component
  fugacities in the two phases, and K-values equal to y/x;
- stability: the reported tangent-plane distance of each trial, recomputed
  from its composition, and the stable/unstable verdict that follows from it;
- bubble and dew points: the parent is the feed, the incipient phase is
  normalized, K-values match the two compositions, and the component
  fugacities are equal at the reported pressure.
"""

from __future__ import annotations

from functools import cache
from itertools import product
from math import fsum, log

import pytest

from pvt_phase_simulator.eos.flash import (
    COMPOSITION_SUM_TOLERANCE,
    FUGACITY_EQUILIBRIUM_TOLERANCE,
    MATERIAL_BALANCE_TOLERANCE,
    FlashConvergenceStatus,
    FlashPhaseResult,
    FlashPhaseState,
    TwoPhaseFlashResult,
    calculate_two_phase_flash,
)
from pvt_phase_simulator.eos.mixing_rules import (
    calculate_peng_robinson_mixture_parameters,
)
from pvt_phase_simulator.eos.mixture_fugacity import (
    calculate_mixture_fugacity_coefficients,
)
from pvt_phase_simulator.eos.phase_stability import (
    TPD_STABILITY_TOLERANCE,
    PhaseStabilityStatus,
)
from pvt_phase_simulator.eos.saturation_pressure import (
    FUGACITY_EQUILIBRIUM_TOLERANCE as SATURATION_FUGACITY_TOLERANCE,
)
from pvt_phase_simulator.eos.saturation_pressure import (
    INCIPIENT_SUM_TOLERANCE,
    SaturationKind,
    SaturationPressureResult,
    SaturationStatus,
    calculate_saturation_pressure,
)
from pvt_phase_simulator.fluid_models import ETHANE, METHANE, PROPANE, FluidMixture
from pvt_phase_simulator.fluid_models import MixtureComponent as Item

COMPONENTS = (METHANE, ETHANE, PROPANE)
COMPOSITIONS = (
    (0.5, 0.0, 0.5),
    (0.7, 0.2, 0.1),
    (0.3, 0.3, 0.4),
    (0.2, 0.0, 0.8),
    (0.8, 0.0, 0.2),
    (0.4, 0.6, 0.0),
)
TEMPERATURES_K = (220.0, 260.0, 300.0)
PRESSURES_PA = (1.0e6, 3.0e6, 6.0e6)
FLASH_STATES = tuple(product(COMPOSITIONS, TEMPERATURES_K, PRESSURES_PA))
SATURATION_STATES = (
    ((0.5, 0.0, 0.5), 250.0, SaturationKind.BUBBLE_POINT),
    ((0.5, 0.0, 0.5), 300.0, SaturationKind.BUBBLE_POINT),
    ((0.7, 0.3, 0.0), 220.0, SaturationKind.BUBBLE_POINT),
    ((0.3, 0.3, 0.4), 260.0, SaturationKind.BUBBLE_POINT),
    ((0.1, 0.0, 0.9), 300.0, SaturationKind.DEW_POINT),
    ((0.2, 0.3, 0.5), 300.0, SaturationKind.DEW_POINT),
    ((0.05, 0.15, 0.8), 320.0, SaturationKind.DEW_POINT),
)


def _mixture(composition: tuple[float, ...]) -> FluidMixture:
    return FluidMixture(
        tuple(
            Item(component, fraction)
            for component, fraction in zip(COMPONENTS, composition, strict=True)
            if fraction > 0.0
        )
    )


@cache
def _flash(
    composition: tuple[float, ...], temperature: float, pressure: float
) -> TwoPhaseFlashResult:
    return calculate_two_phase_flash(_mixture(composition), temperature, pressure)


def _log_phi(
    mixture: FluidMixture,
    composition: tuple[float, ...],
    z_factor: float,
    temperature: float,
    pressure: float,
) -> list[float]:
    """ln(phi_i) recomputed at a phase's composition and selected root."""

    phase = FluidMixture(
        tuple(
            Item(item.component, fraction)
            for item, fraction in zip(mixture.components, composition, strict=True)
        )
    )
    parameters = calculate_peng_robinson_mixture_parameters(
        phase, temperature, pressure
    )
    return [
        item.log_fugacity_coefficient
        for item in calculate_mixture_fugacity_coefficients(parameters, z_factor)
    ]


def _log_fugacities(
    mixture: FluidMixture, phase: FlashPhaseResult, temperature: float, pressure: float
) -> list[float]:
    log_phi = _log_phi(
        mixture,
        phase.composition,
        phase.selected_compressibility_factor,
        temperature,
        pressure,
    )
    return [
        log(fraction) + value + log(pressure)
        for fraction, value in zip(phase.composition, log_phi, strict=True)
    ]


def _two_phase(states: tuple) -> list[tuple]:  # type: ignore[type-arg]
    return [
        state
        for state in states
        if _flash(*state).phase_state is FlashPhaseState.TWO_PHASE
        and _flash(*state).convergence_status is FlashConvergenceStatus.CONVERGED
    ]


def test_the_grid_covers_both_outcomes() -> None:
    states = [_flash(*state).phase_state for state in FLASH_STATES]
    assert FlashPhaseState.TWO_PHASE in states
    assert FlashPhaseState.SINGLE_PHASE in states
    assert len(_two_phase(FLASH_STATES)) >= 10


@pytest.mark.parametrize("state", FLASH_STATES)
def test_flash_material_balance_and_normalization(state: tuple) -> None:  # type: ignore[type-arg]
    result = _flash(*state)
    if result.phase_state is not FlashPhaseState.TWO_PHASE:
        return
    assert result.convergence_status is FlashConvergenceStatus.CONVERGED
    assert result.liquid_phase is not None and result.vapor_phase is not None
    assert result.vapor_fraction is not None and result.liquid_fraction is not None
    beta = result.vapor_fraction
    assert 0.0 < beta < 1.0
    assert abs(beta + result.liquid_fraction - 1.0) <= MATERIAL_BALANCE_TOLERANCE
    x, y = result.liquid_phase.composition, result.vapor_phase.composition
    assert abs(fsum(x) - 1.0) <= COMPOSITION_SUM_TOLERANCE
    assert abs(fsum(y) - 1.0) <= COMPOSITION_SUM_TOLERANCE
    feed = [item.mole_fraction for item in result.feed_mixture.components]
    for z_i, x_i, y_i in zip(feed, x, y, strict=True):
        assert (
            abs(z_i - (beta * y_i + (1.0 - beta) * x_i)) <= MATERIAL_BALANCE_TOLERANCE
        )


@pytest.mark.parametrize("state", FLASH_STATES)
def test_flash_fugacities_are_equal_and_k_values_are_y_over_x(state: tuple) -> None:  # type: ignore[type-arg]
    result = _flash(*state)
    if result.phase_state is not FlashPhaseState.TWO_PHASE:
        return
    assert result.liquid_phase is not None and result.vapor_phase is not None
    mixture = result.feed_mixture
    liquid = _log_fugacities(
        mixture, result.liquid_phase, result.temperature_k, result.pressure_pa
    )
    vapor = _log_fugacities(
        mixture, result.vapor_phase, result.temperature_k, result.pressure_pa
    )
    for ln_f_liquid, ln_f_vapor in zip(liquid, vapor, strict=True):
        assert abs(ln_f_liquid - ln_f_vapor) <= FUGACITY_EQUILIBRIUM_TOLERANCE
    assert result.final_k_values is not None
    x, y = result.liquid_phase.composition, result.vapor_phase.composition
    for k_value, x_i, y_i in zip(result.final_k_values, x, y, strict=True):
        assert abs(log(k_value) - log(y_i / x_i)) <= FUGACITY_EQUILIBRIUM_TOLERANCE


@pytest.mark.parametrize("state", FLASH_STATES)
def test_stability_verdict_follows_the_recomputed_tangent_plane_distance(
    state: tuple,  # type: ignore[type-arg]
) -> None:
    result = _flash(*state)
    stability = result.phase_stability
    feed = stability.feed_reference
    mixture = result.feed_mixture
    d = [
        log(fraction) + value
        for fraction, value in zip(
            feed.composition, feed.component_log_fugacity_coefficients, strict=True
        )
    ]
    negative = False
    for trial in (stability.vapor_like_trial, stability.liquid_like_trial):
        if not trial.converged or trial.tangent_plane_distance is None:
            continue
        assert trial.selected_compressibility_factor is not None
        w = trial.final_trial_composition
        log_phi = _log_phi(
            mixture,
            w,
            trial.selected_compressibility_factor,
            result.temperature_k,
            result.pressure_pa,
        )
        recomputed = fsum(
            w_i * (log(w_i) + phi_i - d_i)
            for w_i, phi_i, d_i in zip(w, log_phi, d, strict=True)
            if w_i > 0.0
        )
        assert recomputed == pytest.approx(trial.tangent_plane_distance, abs=1e-12)
        if not trial.trivial_solution and recomputed < -TPD_STABILITY_TOLERANCE:
            negative = True
    if negative:
        assert stability.status is PhaseStabilityStatus.UNSTABLE
    elif stability.status is PhaseStabilityStatus.UNSTABLE:  # pragma: no cover
        pytest.fail("unstable verdict without a negative tangent-plane distance")
    if stability.status is PhaseStabilityStatus.STABLE:
        assert result.phase_state is FlashPhaseState.SINGLE_PHASE
    if result.phase_state is FlashPhaseState.TWO_PHASE:
        assert stability.status is PhaseStabilityStatus.UNSTABLE


@cache
def _saturation(
    composition: tuple[float, ...], temperature: float, kind: SaturationKind
) -> SaturationPressureResult:
    return calculate_saturation_pressure(_mixture(composition), temperature, kind)


def test_the_saturation_states_converge() -> None:
    converged = [
        _saturation(*state).status is SaturationStatus.CONVERGED
        for state in SATURATION_STATES
    ]
    assert sum(converged) >= 5


@pytest.mark.parametrize("state", SATURATION_STATES)
def test_saturation_k_values_compositions_and_fugacities(state: tuple) -> None:  # type: ignore[type-arg]
    result = _saturation(*state)
    if result.status is not SaturationStatus.CONVERGED:
        return
    assert result.pressure_pa is not None
    assert result.parent_phase is not None and result.incipient_phase is not None
    feed = tuple(item.mole_fraction for item in result.feed_mixture.components)
    assert result.parent_composition == pytest.approx(feed, abs=1e-15)
    incipient = result.incipient_composition
    assert abs(fsum(incipient) - 1.0) <= INCIPIENT_SUM_TOLERANCE
    bubble = result.saturation_kind is SaturationKind.BUBBLE_POINT
    for k_value, parent_i, incipient_i in zip(
        result.k_values, result.parent_composition, incipient, strict=True
    ):
        expected = incipient_i / parent_i if bubble else parent_i / incipient_i
        assert abs(log(k_value) - log(expected)) <= SATURATION_FUGACITY_TOLERANCE
    mixture = result.feed_mixture
    parent = _log_fugacities(
        mixture, result.parent_phase, result.temperature_k, result.pressure_pa
    )
    new = _log_fugacities(
        mixture, result.incipient_phase, result.temperature_k, result.pressure_pa
    )
    for ln_parent, ln_new in zip(parent, new, strict=True):
        assert abs(ln_parent - ln_new) <= SATURATION_FUGACITY_TOLERANCE
