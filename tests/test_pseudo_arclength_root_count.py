"""Root-count-tolerant continuity in the pseudo-arclength tracer (proposal P1).

Along a saturation curve one phase's cubic can lose its two outer roots while the
selected root moves smoothly. The pseudo-arclength tracer must accept that, and
must still reject a jump onto another phase's root. See
docs/ENGINE_CHANGE_PROPOSALS.md (P1) and docs/DEW_INVESTIGATION.md.
"""

from functools import cache

import pytest

from pvt_phase_simulator.eos.flash import FlashPhaseResult
from pvt_phase_simulator.eos.peng_robinson import (
    MechanicalStabilityClassification,
    MechanicalStabilityResult,
)
from pvt_phase_simulator.eos.phase_stability import PhaseRootSelection, PhaseTrialKind
from pvt_phase_simulator.eos.pseudo_arclength import (
    ROOT_COUNT_CHANGE_MAXIMUM_RELATIVE_JUMP,
    _arclength_root_is_continuous,
)
from pvt_phase_simulator.eos.saturation_pressure import (
    SaturationKind,
    calculate_saturation_pressure,
)
from pvt_phase_simulator.fluid_models import FluidMixture
from pvt_phase_simulator_ui.adapters import validate_scientific_inputs
from pvt_phase_simulator_ui.envelope_extension import (
    ExtendedBranch,
    ExtendedEnvelope,
    trace_extended_envelope,
)

STABLE = MechanicalStabilityClassification.STABLE
UNSTABLE = MechanicalStabilityClassification.UNSTABLE

#: Certified critical point of 50/50 methane/propane (docs/PROJECT_STATUS.md).
CERTIFIED_CRITICAL_TEMPERATURE_K = 321.58
CERTIFIED_CRITICAL_PRESSURE_PA = 8.534e6

#: Relative agreement required with an independent fixed-temperature solve.
FIXED_TEMPERATURE_AGREEMENT = 1e-6

#: Phase results from the proposal's evidence: the incipient liquid's roots at
#: 292.2 K, and the same phase one step later.
THREE_ROOTS = ((0.0637, STABLE), (0.3505, UNSTABLE), (0.5443, STABLE))


def _phase(
    roots: tuple[tuple[float, MechanicalStabilityClassification], ...],
    selected: float,
    kind: PhaseTrialKind = PhaseTrialKind.LIQUID_LIKE,
) -> FlashPhaseResult:
    candidates = tuple(
        MechanicalStabilityResult(z, 0.0, 0.0, classification)
        for z, classification in roots
    )
    selection = PhaseRootSelection(
        kind, candidates, selected, STABLE, diagnostics=(), failure_reason=None
    )
    return FlashPhaseResult(
        trial_kind=kind,
        composition=(1.0,),
        root_selection=selection,
        selected_compressibility_factor=selected,
        mechanical_classification=STABLE,
        component_log_fugacity_coefficients=(0.0,),
        component_fugacity_coefficients=(1.0,),
        component_fugacities_pa=(1.0,),
        diagnostics=(),
    )


# --- synthetic phase results: the rule itself -------------------------------------


def test_three_to_one_roots_with_small_jump_is_accepted() -> None:
    previous = _phase(THREE_ROOTS, 0.0637)
    current = _phase(((0.0690, STABLE),), 0.0690)  # the observed 8% move
    assert abs(current.selected_compressibility_factor - 0.0637) / 0.0637 < 0.09
    assert _arclength_root_is_continuous(previous, current)


def test_one_to_three_roots_with_small_jump_is_accepted() -> None:
    previous = _phase(((0.0690, STABLE),), 0.0690)
    current = _phase(THREE_ROOTS, 0.0637)
    assert _arclength_root_is_continuous(previous, current)


def test_three_to_one_roots_onto_the_other_phase_is_rejected() -> None:
    """The selected liquid root vanished; the only root left belongs to the vapour."""
    previous = _phase(THREE_ROOTS, 0.0637)
    current = _phase(((0.5000, STABLE),), 0.5000)
    jump = abs(0.5000 - 0.0637) / 0.0637
    assert jump > ROOT_COUNT_CHANGE_MAXIMUM_RELATIVE_JUMP
    assert not _arclength_root_is_continuous(previous, current)


def test_the_jump_guard_alone_blocks_the_phase_switch() -> None:
    """Without the guard the nearest-root test passes, so the guard must do the work."""
    previous = _phase(THREE_ROOTS, 0.0637)
    current = _phase(((0.5000, STABLE),), 0.5000)
    nearest = min((0.5000,), key=lambda z: abs(z - 0.0637))
    assert nearest == current.selected_compressibility_factor
    assert not _arclength_root_is_continuous(previous, current)


def test_equal_count_discontinuity_is_still_rejected() -> None:
    """Same topology: the shared rejection stands. The selected root hops roots."""
    previous = _phase(THREE_ROOTS, 0.0637)
    jumped = _phase(THREE_ROOTS, 0.5443)
    assert not _arclength_root_is_continuous(previous, jumped)


def test_equal_count_continuous_step_is_accepted_by_the_shared_rule() -> None:
    previous = _phase(THREE_ROOTS, 0.0637)
    current = _phase(THREE_ROOTS, 0.0637)
    assert _arclength_root_is_continuous(previous, current)


def test_a_change_of_trial_kind_is_rejected() -> None:
    previous = _phase(THREE_ROOTS, 0.0637)
    current = _phase(((0.0690, STABLE),), 0.0690, PhaseTrialKind.VAPOR_LIKE)
    assert not _arclength_root_is_continuous(previous, current)


def test_no_stable_root_is_rejected() -> None:
    previous = _phase(THREE_ROOTS, 0.0637)
    current = _phase(((0.0690, UNSTABLE),), 0.0690)
    assert not _arclength_root_is_continuous(previous, current)


def test_a_tie_between_two_stable_roots_is_rejected() -> None:
    previous = _phase(((0.30, STABLE),), 0.30)
    current = _phase(((0.20, STABLE), (0.30, UNSTABLE), (0.40, STABLE)), 0.20)
    assert not _arclength_root_is_continuous(previous, current)


def test_selected_root_that_is_not_the_nearest_stable_root_is_rejected() -> None:
    previous = _phase(((0.30, STABLE),), 0.30)
    current = _phase(((0.28, STABLE), (0.35, UNSTABLE), (0.55, STABLE)), 0.55)
    assert not _arclength_root_is_continuous(previous, current)


# --- the engine's extended envelope, end to end -----------------------------------


@cache
def _traced(
    composition: tuple[float, float, float], temperature_k: float
) -> tuple[FluidMixture, ExtendedEnvelope]:
    mixture = validate_scientific_inputs(composition, temperature_k, 5.0e6).mixture()
    return mixture, trace_extended_envelope(mixture, temperature_k)


def _disagreements(
    mixture: FluidMixture,
    kind: SaturationKind,
    branch: ExtendedBranch,
    *,
    through_index: int | None = None,
) -> tuple[int, list[float]]:
    """Compare points with a fixed-temperature solve; return (compared, rel. diffs)."""
    compared = 0
    differences: list[float] = []
    points = (
        branch.points if through_index is None else branch.points[: through_index + 1]
    )
    for point in points:
        fixed = calculate_saturation_pressure(
            mixture, point.temperature_k, kind, saturation_newton_enabled=True
        )
        if fixed.pressure_pa is None:
            continue
        compared += 1
        differences.append(
            abs(fixed.pressure_pa - point.pressure_pa) / point.pressure_pa
        )
    return compared, differences


def test_default_dew_branch_from_270_k_reaches_the_certified_critical_point() -> None:
    _, envelope = _traced((50.0, 0.0, 50.0), 270.0)
    dew = envelope.dew
    assert dew.termination_reason == "near_critical"
    end = dew.points[-1]
    assert abs(end.temperature_k - CERTIFIED_CRITICAL_TEMPERATURE_K) < 3.0
    assert abs(end.pressure_pa - CERTIFIED_CRITICAL_PRESSURE_PA) < 0.2e6
    # The branch now passes the 292.2 K point where it used to stop.
    assert max(point.temperature_k for point in dew.points) > 320.0


def test_dew_points_agree_with_fixed_temperature_solves_until_the_turning_point() -> (
    None
):
    mixture, envelope = _traced((50.0, 0.0, 50.0), 270.0)
    dew = envelope.dew
    turning = next(
        index
        for index, point in enumerate(dew.points)
        if point.temperature_turning_point
    )
    # Up to the cricondentherm the fixed-temperature solver finds the same root.
    compared, differences = _disagreements(
        mixture, SaturationKind.DEW_POINT, dew, through_index=turning
    )
    assert compared == turning + 1
    assert compared > 25
    assert max(differences) < FIXED_TEMPERATURE_AGREEMENT
    # Past the turn the trace is on the upper-pressure root, which a fixed-temperature
    # solve at the same temperature does not return: it finds the lower one.
    for point in dew.points[turning + 1 :]:
        fixed = calculate_saturation_pressure(
            mixture,
            point.temperature_k,
            SaturationKind.DEW_POINT,
            saturation_newton_enabled=True,
        )
        assert fixed.pressure_pa is not None
        assert fixed.pressure_pa < point.pressure_pa


@pytest.mark.parametrize(
    ("composition", "temperature_k"),
    [
        pytest.param((0.0, 30.0, 70.0), 315.5, id="C2-C3-30-70"),
        pytest.param((0.0, 70.0, 30.0), 300.0, id="C2-C3-70-30"),
    ],
)
def test_ethane_propane_bubble_and_dew_branches_close(
    composition: tuple[float, float, float], temperature_k: float
) -> None:
    mixture, envelope = _traced(composition, temperature_k)
    assert envelope.bubble.termination_reason == "near_critical"
    assert envelope.dew.termination_reason == "near_critical"
    for kind, branch in (
        (SaturationKind.BUBBLE_POINT, envelope.bubble),
        (SaturationKind.DEW_POINT, envelope.dew),
    ):
        compared, differences = _disagreements(mixture, kind, branch)
        assert compared > 10
        assert max(differences) < FIXED_TEMPERATURE_AGREEMENT
