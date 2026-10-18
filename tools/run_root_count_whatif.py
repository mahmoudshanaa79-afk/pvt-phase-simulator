"""What-if: do early ``phase_role_lost`` stops come from cubic root-count changes?

The pseudo-arclength tracer rejects a step whenever the fixed-root continuity
check fails, and that check requires the NUMBER of real cubic roots to be
unchanged (see docs/NEWTON_SATURATION_DESIGN.md). Along a saturation curve the
cubic of one phase can legitimately go from three real roots to one while the
selected root moves smoothly.

This diagnostic traces each case twice with the engine's extended-envelope path:
once as shipped, and once with the continuity check replaced, *inside this
process only*, by a variant that additionally accepts a root-count change when
the selected root is still the nearest stable continuation of the previous one.
Every what-if point is then compared with an independent production
fixed-temperature saturation solve. No engine file is modified; the replacement
is undone before the tool exits. This is evidence for a design decision, not a
production path.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pvt_phase_simulator.eos.pseudo_arclength as arclength
from pvt_phase_simulator.eos.flash import FlashPhaseResult
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

#: (methane, ethane, propane) mol %, operating temperature K.
CASES: tuple[tuple[tuple[float, float, float], float], ...] = (
    ((50.0, 0.0, 50.0), 300.0),
    ((50.0, 0.0, 50.0), 330.0),
    ((10.0, 0.0, 90.0), 330.0),
    ((30.0, 0.0, 70.0), 310.0),
    ((70.0, 0.0, 30.0), 270.0),
    ((90.0, 0.0, 10.0), 230.0),
    ((0.0, 30.0, 70.0), 315.5),
    ((0.0, 70.0, 30.0), 300.0),
    ((50.0, 50.0, 0.0), 250.0),
    ((40.0, 30.0, 30.0), 290.0),
)
AGREEMENT = 1e-6

SHIPPED: Callable[[FlashPhaseResult, FlashPhaseResult], bool] = (
    arclength._root_branch_is_continuous
)


def _tolerate_root_count_change(
    previous: FlashPhaseResult, current: FlashPhaseResult
) -> bool:
    if SHIPPED(previous, current):
        return True
    if previous.trial_kind is not current.trial_kind:
        return False
    if len(previous.root_selection.candidates) == len(
        current.root_selection.candidates
    ):
        return False  # the shipped rejection had another cause; keep it
    stable = [
        candidate.compressibility_factor
        for candidate in current.root_selection.candidates
        if candidate.classification.name == "STABLE"
    ]
    if not stable:
        return False
    previous_z = previous.selected_compressibility_factor
    nearest = min(stable, key=lambda value: abs(value - previous_z))
    tolerance = 1e-8 * max(1.0, abs(previous_z))
    return abs(nearest - current.selected_compressibility_factor) <= tolerance


def _trace(
    mixture: FluidMixture, temperature_k: float, *, relaxed: bool
) -> ExtendedEnvelope:
    module: Any = arclength
    module._root_branch_is_continuous = (
        _tolerate_root_count_change if relaxed else SHIPPED
    )
    try:
        return trace_extended_envelope(mixture, temperature_k)
    finally:
        module._root_branch_is_continuous = SHIPPED


def _check(
    mixture: FluidMixture, branch: ExtendedBranch, kind: SaturationKind
) -> tuple[int, int, int]:
    agree = other = unsolved = 0
    for point in branch.points:
        fixed = calculate_saturation_pressure(
            mixture, point.temperature_k, kind, saturation_newton_enabled=True
        )
        if fixed.pressure_pa is None:
            unsolved += 1
        elif abs(fixed.pressure_pa - point.pressure_pa) / point.pressure_pa < AGREEMENT:
            agree += 1
        else:
            other += 1  # the fixed-T solve found the other root of a turning branch
    return agree, other, unsolved


def _summary(branch: ExtendedBranch) -> str:
    if not branch.points:
        return f"{branch.termination_reason:24s}  0 pts"
    end = branch.points[-1]
    return (
        f"{branch.termination_reason:24s}{len(branch.points):3d} pts, end "
        f"{end.temperature_k:6.1f} K {end.pressure_pa / 1e6:6.3f} MPa"
    )


def main() -> None:
    for composition, temperature in CASES:
        mixture = validate_scientific_inputs(composition, temperature, 5.0e6).mixture()
        shipped = _trace(mixture, temperature, relaxed=False)
        whatif = _trace(mixture, temperature, relaxed=True)
        print(f"{composition} mol % @ {temperature} K")
        for name, kind in (
            ("bubble", SaturationKind.BUBBLE_POINT),
            ("dew", SaturationKind.DEW_POINT),
        ):
            before: ExtendedBranch = getattr(shipped, name)
            after: ExtendedBranch = getattr(whatif, name)
            print(f"  {name:6s} shipped  {_summary(before)}")
            if (before.termination_reason, before.points) != (
                after.termination_reason,
                after.points,
            ):
                agree, other, unsolved = _check(mixture, after, kind)
                print(
                    f"         what-if  {_summary(after)}; fixed-T: {agree} agree, "
                    f"{other} other root, {unsolved} unsolved"
                )


if __name__ == "__main__":
    main()
