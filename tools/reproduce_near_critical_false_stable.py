"""Reproducer for proposal P12: false "stable" verdicts just below the critical point.

Read-only: it calls the frozen engine and changes nothing. For 50/50
methane/propane at 8.534 MPa (the audited critical pressure) it prints, at a
few temperatures below the certified critical temperature (321.58 K):

- the production flash verdict and whether both stability trials collapsed to
  the trivial solution;
- the extended phase envelope's bubble pressure at that temperature, which
  shows whether the state lies inside the two-phase region;
- the lowest tangent-plane distance found by extra trial starts near the feed,
  through the engine's own public ``run_phase_stability_trial``.

Run it from the repository root:

    uv run python tools/reproduce_near_critical_false_stable.py
"""

from __future__ import annotations

from dataclasses import dataclass

from pvt_phase_simulator.eos.flash import calculate_two_phase_flash
from pvt_phase_simulator.eos.phase_stability import (
    TPD_STABILITY_TOLERANCE,
    PhaseTrialKind,
    evaluate_feed_phase_reference,
    run_phase_stability_trial,
)
from pvt_phase_simulator.fluid_models import METHANE, PROPANE, FluidMixture
from pvt_phase_simulator.fluid_models import MixtureComponent as Item
from pvt_phase_simulator_ui.envelope_extension import (
    ExtendedEnvelope,
    trace_extended_envelope,
)

MIXTURE = FluidMixture((Item(METHANE, 0.5), Item(PROPANE, 0.5)))
PRESSURE_PA = 8.534e6
TEMPERATURES_K = (312.0, 314.0, 316.0, 318.0, 320.0)
#: Extra starts near the 50/50 feed (methane fraction); not used by the engine.
EXTRA_STARTS = (0.55, 0.6, 0.65, 0.45, 0.4, 0.35)


@dataclass(frozen=True, slots=True)
class Row:
    temperature_k: float
    flash_phase_state: str
    stability_status: str
    both_trials_trivial: bool
    envelope_bubble_pressure_pa: float | None
    inside_envelope: bool | None
    extra_start_lowest_tpd: float | None
    extra_start: float | None


def bubble_pressure_on_envelope(
    envelope: ExtendedEnvelope, temperature_k: float
) -> float | None:
    """Linear interpolation of the extended bubble branch at ``temperature_k``."""

    points = sorted(
        (point.temperature_k, point.pressure_pa) for point in envelope.bubble.points
    )
    for (t0, p0), (t1, p1) in zip(points, points[1:], strict=False):
        if t0 <= temperature_k <= t1 and t1 > t0:
            return p0 + (p1 - p0) * (temperature_k - t0) / (t1 - t0)
    return None


def lowest_extra_start_tpd(temperature_k: float) -> tuple[float | None, float | None]:
    feed = evaluate_feed_phase_reference(MIXTURE, temperature_k, PRESSURE_PA)
    best: tuple[float | None, float | None] = (None, None)
    for methane in EXTRA_STARTS:
        for kind in (PhaseTrialKind.VAPOR_LIKE, PhaseTrialKind.LIQUID_LIKE):
            trial = run_phase_stability_trial(
                MIXTURE,
                temperature_k,
                PRESSURE_PA,
                feed,
                (methane, 1.0 - methane),
                kind,
            )
            value = trial.tangent_plane_distance
            if trial.converged and not trial.trivial_solution and value is not None:
                if best[0] is None or value < best[0]:
                    best = (value, methane)
    return best


def rows() -> list[Row]:
    envelope = trace_extended_envelope(MIXTURE, 300.0)
    result = []
    for temperature in TEMPERATURES_K:
        flash = calculate_two_phase_flash(MIXTURE, temperature, PRESSURE_PA)
        stability = flash.phase_stability
        trivial = (
            stability.vapor_like_trial.trivial_solution
            and stability.liquid_like_trial.trivial_solution
        )
        bubble = bubble_pressure_on_envelope(envelope, temperature)
        tpd, start = lowest_extra_start_tpd(temperature)
        result.append(
            Row(
                temperature,
                flash.phase_state.value,
                stability.status.value,
                trivial,
                bubble,
                None if bubble is None else PRESSURE_PA < bubble,
                tpd,
                start,
            )
        )
    return result


def main() -> None:
    print(f"50/50 methane/propane at {PRESSURE_PA / 1e6} MPa")
    print(
        "T (K)  flash         stability  both trivial  envelope bubble (MPa)  "
        f"inside  lowest extra-start TPD (negative < -{TPD_STABILITY_TOLERANCE:g})"
    )
    for row in rows():
        bubble = (
            "n/a"
            if row.envelope_bubble_pressure_pa is None
            else f"{row.envelope_bubble_pressure_pa / 1e6:.4f}"
        )
        tpd = (
            "none converged"
            if row.extra_start_lowest_tpd is None
            else f"{row.extra_start_lowest_tpd:+.6f} (start x_C1 = {row.extra_start})"
        )
        print(
            f"{row.temperature_k:5.1f}  {row.flash_phase_state:12s}  "
            f"{row.stability_status:9s}  {row.both_trials_trivial!s:12s}  "
            f"{bubble:>21s}  {row.inside_envelope!s:6s}  {tpd}"
        )


if __name__ == "__main__":
    main()
