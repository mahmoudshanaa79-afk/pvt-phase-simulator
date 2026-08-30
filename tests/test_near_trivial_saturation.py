"""Module 15.2 regressions for near-trivial saturation collapse."""

from __future__ import annotations

from dataclasses import replace
from math import log

import pytest

import pvt_phase_simulator.eos.phase_envelope as envelope_module
from pvt_phase_simulator.eos.phase_envelope import (
    EnvelopeContinuationSettings,
    EnvelopeTerminationReason,
    trace_bubble_branch,
)
from pvt_phase_simulator.eos.saturation_pressure import (
    FUGACITY_EQUILIBRIUM_TOLERANCE,
    NEAR_TRIVIAL_COMPOSITION_TOLERANCE,
    NEAR_TRIVIAL_LOG_K_TOLERANCE,
    NEAR_TRIVIAL_ROOT_TOLERANCE,
    SaturationKind,
    SaturationPressureResult,
    SaturationStatus,
    calculate_saturation_pressure,
    multicomponent_saturation_is_near_trivial,
    saturation_phase_roles_are_consistent,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    Component,
    FluidMixture,
    MixtureComponent,
)


def _mixture(items: tuple[tuple[Component, float], ...]) -> FluidMixture:
    return FluidMixture(tuple(MixtureComponent(*item) for item in items))


BINARY = _mixture(((METHANE, 0.5), (ETHANE, 0.5)))
TERNARY = _mixture(((METHANE, 0.5), (ETHANE, 0.3), (PROPANE, 0.2)))
METHANE_PROPANE = _mixture(((METHANE, 0.6), (PROPANE, 0.4)))
B2_SEED = (0.1, -0.1)
TRUE_BUBBLE_PRESSURE_PA = 7_391_642.208227274
TRUE_DEW_PRESSURE_PA = 575_360.2360506197
SPURIOUS_B2_PRESSURE_PA = 3_322_705.621296047


def _assert_distinct_requested_state(result: SaturationPressureResult) -> None:
    assert result.status is SaturationStatus.CONVERGED
    assert result.parent_phase is not None and result.incipient_phase is not None
    assert (
        saturation_phase_roles_are_consistent(
            result.saturation_kind,
            result.parent_phase.selected_compressibility_factor,
            result.incipient_phase.selected_compressibility_factor,
        )
        is True
    )
    assert not multicomponent_saturation_is_near_trivial(
        result.feed_composition,
        result.incipient_composition,
        result.saturation_kind,
        result.parent_phase,
        result.incipient_phase,
    )


def test_b2_default_limit_recovers_the_true_bubble_by_fallback() -> None:
    result = calculate_saturation_pressure(
        METHANE_PROPANE,
        250.0,
        SaturationKind.BUBBLE_POINT,
        initial_log_k_values=B2_SEED,
        saturation_newton_enabled=True,
    )
    _assert_distinct_requested_state(result)
    assert result.pressure_pa == pytest.approx(TRUE_BUBBLE_PRESSURE_PA, rel=1e-11)
    assert result.pressure_pa != pytest.approx(SPURIOUS_B2_PRESSURE_PA, rel=1e-6)
    assert result.incipient_composition == pytest.approx(
        (0.9067415660364109, 0.09325843396358915), abs=2e-10
    )
    assert max(abs(log(value)) for value in result.k_values) > 1.0
    assert (
        abs(
            result.parent_phase.selected_compressibility_factor
            - result.incipient_phase.selected_compressibility_factor
        )
        > 0.3
    )
    assert result.maximum_fugacity_equilibrium_residual is not None
    assert (
        result.maximum_fugacity_equilibrium_residual <= FUGACITY_EQUILIBRIUM_TOLERANCE
    )
    assert result.newton_attempt is not None
    assert not result.newton_attempt.converged
    assert "trivial" in (result.newton_attempt.failure_reason or "").lower()


@pytest.mark.parametrize("maximum_iterations", [14, 15, 16, 20])
def test_b2_cannot_move_to_another_iteration_limit(maximum_iterations: int) -> None:
    result = calculate_saturation_pressure(
        METHANE_PROPANE,
        250.0,
        SaturationKind.BUBBLE_POINT,
        initial_log_k_values=B2_SEED,
        saturation_newton_enabled=True,
        newton_max_iterations=maximum_iterations,
    )
    _assert_distinct_requested_state(result)
    assert result.pressure_pa == pytest.approx(TRUE_BUBBLE_PRESSURE_PA, rel=1e-11)
    assert result.newton_attempt is not None
    assert not result.newton_attempt.converged
    # BLAS implementations can detect the same terminal trivial collapse on the
    # final or penultimate iteration. Both paths must remain bounded by the
    # requested limit and preserve the accepted physical saturation result.
    assert maximum_iterations - 1 <= result.newton_attempt.iteration_count
    assert result.newton_attempt.iteration_count <= maximum_iterations
    assert "trivial" in (result.newton_attempt.failure_reason or "").lower()


def test_shared_policy_requires_combined_near_collapse_evidence() -> None:
    physical = calculate_saturation_pressure(
        METHANE_PROPANE, 250.0, SaturationKind.BUBBLE_POINT
    )
    assert physical.parent_phase is not None and physical.incipient_phase is not None
    feed = (0.6, 0.4)
    collapsed = (0.6000836046122376, 0.39991639538776236)
    parent = replace(
        physical.parent_phase, selected_compressibility_factor=0.1207729770111963
    )
    incipient = replace(
        physical.incipient_phase, selected_compressibility_factor=0.1207885546426564
    )
    assert multicomponent_saturation_is_near_trivial(
        feed, collapsed, SaturationKind.BUBBLE_POINT, parent, incipient
    )

    root_distinct = replace(
        incipient, selected_compressibility_factor=0.1207729770111963 + 2.0e-4
    )
    assert not multicomponent_saturation_is_near_trivial(
        feed, collapsed, SaturationKind.BUBBLE_POINT, parent, root_distinct
    )
    assert not multicomponent_saturation_is_near_trivial(
        feed,
        (0.601, 0.399),
        SaturationKind.BUBBLE_POINT,
        parent,
        incipient,
    )
    assert not multicomponent_saturation_is_near_trivial(
        feed,
        (0.61, 0.39),
        SaturationKind.BUBBLE_POINT,
        parent,
        incipient,
    )
    assert multicomponent_saturation_is_near_trivial(
        feed,
        feed,
        SaturationKind.BUBBLE_POINT,
        physical.parent_phase,
        physical.incipient_phase,
    )
    assert not multicomponent_saturation_is_near_trivial(
        (1.0,),
        (1.0,),
        SaturationKind.BUBBLE_POINT,
        physical.parent_phase,
        physical.incipient_phase,
    )
    assert NEAR_TRIVIAL_LOG_K_TOLERANCE == 2e-3
    assert NEAR_TRIVIAL_COMPOSITION_TOLERANCE == 5e-4
    assert NEAR_TRIVIAL_ROOT_TOLERANCE == 1e-4


def test_ch4_c3_near_k_seed_sweep_has_zero_false_convergence() -> None:
    magnitudes = (0.005, 0.010, 0.025, 0.050, 0.075, 0.100, 0.125, 0.250, 0.500)
    references = {
        SaturationKind.BUBBLE_POINT: TRUE_BUBBLE_PRESSURE_PA,
        SaturationKind.DEW_POINT: TRUE_DEW_PRESSURE_PA,
    }
    attempts = 0
    for newton_enabled in (False, True):
        for kind in (SaturationKind.BUBBLE_POINT, SaturationKind.DEW_POINT):
            for magnitude in magnitudes:
                for orientation in (1.0, -1.0):
                    attempts += 1
                    result = calculate_saturation_pressure(
                        METHANE_PROPANE,
                        250.0,
                        kind,
                        initial_log_k_values=(
                            orientation * magnitude,
                            -orientation * magnitude,
                        ),
                        saturation_newton_enabled=newton_enabled,
                    )
                    if result.status is SaturationStatus.CONVERGED:
                        _assert_distinct_requested_state(result)
                        assert result.pressure_pa == pytest.approx(
                            references[kind], rel=1e-7
                        )
    assert attempts == 72


def test_broader_near_k_seed_sweep_has_zero_false_convergence() -> None:
    specifications = (
        (_mixture(((METHANE, 0.2), (ETHANE, 0.8))), 180.0),
        (_mixture(((METHANE, 0.5), (ETHANE, 0.5))), 220.0),
        (_mixture(((METHANE, 0.8), (ETHANE, 0.2))), 250.0),
        (_mixture(((METHANE, 0.2), (PROPANE, 0.8))), 180.0),
        (METHANE_PROPANE, 250.0),
        (_mixture(((METHANE, 0.8), (PROPANE, 0.2))), 220.0),
        (_mixture(((ETHANE, 0.2), (PROPANE, 0.8))), 250.0),
        (_mixture(((ETHANE, 0.5), (PROPANE, 0.5))), 280.0),
        (_mixture(((ETHANE, 0.8), (PROPANE, 0.2))), 250.0),
        (TERNARY, 220.0),
        (_mixture(((METHANE, 0.6), (ETHANE, 0.3), (PROPANE, 0.1))), 280.0),
        (_mixture(((METHANE, 0.3), (ETHANE, 0.3), (PROPANE, 0.4))), 250.0),
    )
    attempts = 0
    for mixture, temperature_k in specifications:
        for kind in (SaturationKind.BUBBLE_POINT, SaturationKind.DEW_POINT):
            for magnitude in (0.01, 0.10):
                for orientation in (1.0, -1.0):
                    attempts += 1
                    seed = tuple(
                        orientation * magnitude
                        if index % 2 == 0
                        else -orientation * magnitude
                        for index in range(len(mixture.components))
                    )
                    result = calculate_saturation_pressure(
                        mixture,
                        temperature_k,
                        kind,
                        initial_log_k_values=seed,
                        saturation_newton_enabled=True,
                    )
                    if result.status is SaturationStatus.CONVERGED:
                        _assert_distinct_requested_state(result)
    assert attempts == 96


@pytest.mark.parametrize(
    ("mixture", "temperature_k", "kind"),
    [
        (BINARY, 220.0, SaturationKind.BUBBLE_POINT),
        (BINARY, 220.0, SaturationKind.DEW_POINT),
        (TERNARY, 220.0, SaturationKind.BUBBLE_POINT),
        (TERNARY, 220.0, SaturationKind.DEW_POINT),
        (METHANE_PROPANE, 250.0, SaturationKind.BUBBLE_POINT),
        (METHANE_PROPANE, 250.0, SaturationKind.DEW_POINT),
    ],
)
def test_canonical_noncritical_states_remain_accepted(
    mixture: FluidMixture,
    temperature_k: float,
    kind: SaturationKind,
) -> None:
    result = calculate_saturation_pressure(
        mixture, temperature_k, kind, saturation_newton_enabled=True
    )
    _assert_distinct_requested_state(result)


def test_verified_property_260k_bubble_is_a_known_safe_bracketing_gap() -> None:
    """Pin NOT_FOUND without accepting a wrong, trivial, or inverted branch."""

    result = calculate_saturation_pressure(
        BINARY,
        260.0,
        SaturationKind.BUBBLE_POINT,
    )
    assert result.status is SaturationStatus.NOT_FOUND
    assert (
        result.failure_reason == "No trustworthy saturation-pressure bracket was found."
    )
    assert {diagnostic.code for diagnostic in result.diagnostics} >= {
        "SATURATION_BRACKET_NOT_FOUND",
        "SATURATION_TRIVIAL_STATE",
    }
    assert result.pressure_pa is None
    assert result.parent_phase is None and result.incipient_phase is None
    assert result.incipient_composition == ()
    assert result.k_values == ()


@pytest.mark.parametrize(
    ("mixture", "start_temperature_k", "target_temperature_k", "last_temperature_k"),
    [
        (BINARY, 259.0, 285.0, 265.4375),
        (TERNARY, 280.0, 330.0, 290.654296875),
    ],
)
def test_near_critical_a1_branches_are_not_prematurely_truncated(
    mixture: FluidMixture,
    start_temperature_k: float,
    target_temperature_k: float,
    last_temperature_k: float,
) -> None:
    # The binary case starts at 259 K because standalone saturation at 260 K
    # currently lies in a deterministic fixed-grid bracketing reachability gap.
    branch = trace_bubble_branch(
        mixture,
        EnvelopeContinuationSettings(
            target_temperature_k=target_temperature_k,
            initial_temperature_step_k=5.0,
            maximum_points=50,
            saturation_newton_enabled=True,
        ),
        start_temperature_k,
    )
    assert branch.termination_reason is EnvelopeTerminationReason.NEAR_CRITICAL
    assert branch.points[-1].temperature_k == last_temperature_k
    assert all(
        saturation_phase_roles_are_consistent(
            point.saturation_result.saturation_kind,
            point.saturation_result.parent_phase.selected_compressibility_factor,
            point.saturation_result.incipient_phase.selected_compressibility_factor,
        )
        is True
        for point in branch.points
    )


def test_zero_fraction_and_permutation_remain_physical() -> None:
    reference = calculate_saturation_pressure(
        BINARY, 220.0, SaturationKind.BUBBLE_POINT, saturation_newton_enabled=True
    )
    with_zero = calculate_saturation_pressure(
        _mixture(((METHANE, 0.5), (PROPANE, 0.0), (ETHANE, 0.5))),
        220.0,
        SaturationKind.BUBBLE_POINT,
        saturation_newton_enabled=True,
    )
    permuted = calculate_saturation_pressure(
        _mixture(((ETHANE, 0.5), (METHANE, 0.5))),
        220.0,
        SaturationKind.BUBBLE_POINT,
        saturation_newton_enabled=True,
    )
    for result in (reference, with_zero, permuted):
        _assert_distinct_requested_state(result)
    assert with_zero.pressure_pa == pytest.approx(reference.pressure_pa, rel=1e-11)
    assert permuted.pressure_pa == pytest.approx(reference.pressure_pa, rel=1e-11)


def test_pure_methane_remains_exempt() -> None:
    result = calculate_saturation_pressure(
        _mixture(((METHANE, 1.0),)),
        170.0,
        SaturationKind.BUBBLE_POINT,
        saturation_newton_enabled=True,
    )
    assert result.status is SaturationStatus.CONVERGED
    assert result.pressure_pa == pytest.approx(2_347_774.2603319585, rel=1e-11)
    assert result.k_values == (1.0,)
    assert result.parent_phase is not None and result.incipient_phase is not None
    assert not multicomponent_saturation_is_near_trivial(
        result.feed_composition,
        result.incipient_composition,
        result.saturation_kind,
        result.parent_phase,
        result.incipient_phase,
    )


def test_c6_branch_jump_gate_independently_rejects_inverted_phase_roles() -> None:
    settings = EnvelopeContinuationSettings(
        target_temperature_k=210.0,
        initial_temperature_step_k=5.0,
        maximum_points=4,
    )
    branch = trace_bubble_branch(BINARY, settings, 200.0)
    assert len(branch.points) >= 2
    previous, candidate = branch.points[:2]
    assert envelope_module._branch_jump_reason(previous, candidate, settings) is None
    result = candidate.saturation_result
    assert result.parent_phase is not None and result.incipient_phase is not None
    # Construct the continuation candidate directly, bypassing the lower
    # saturation acceptance gate, so this test isolates the envelope defence.
    inverted_result = replace(
        result,
        parent_phase=result.incipient_phase,
        incipient_phase=result.parent_phase,
    )
    inverted_candidate = replace(candidate, saturation_result=inverted_result)
    assert (
        envelope_module._branch_jump_reason(previous, inverted_candidate, settings)
        == "candidate parent and incipient phase roles are inverted."
    )
