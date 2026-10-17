"""Display-only extension of the phase envelope through its turning points.

The standard envelope steps in temperature, so it cannot follow a branch where the
pressure turns (the cricondenbar side of the bubble curve) or where the temperature
turns (the cricondentherm side of the dew curve). The engine already provides an
opt-in pseudo-arclength continuation that can. This module only *chooses among and
calls* that existing continuation; it implements no numerical method and does not
alter any engine result.

Rules kept on purpose:

* Every attempt, including failed ones, is recorded with the engine's own
  termination reason; nothing is retried silently or hidden.
* A branch is called ``reached_critical_region`` only when the engine itself stopped
  it with its near-critical guard. That is not a certified critical point; the
  Critical Point solver remains the only source of one.
* The extension is bounded: at most one bubble attempt and three dew attempts, each
  limited to ``MAXIMUM_POINTS`` accepted points.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final, Literal

import plotly.graph_objects as go  # type: ignore[import-untyped]

from pvt_phase_simulator.eos.phase_envelope import EnvelopeBranchKind
from pvt_phase_simulator.eos.pseudo_arclength import (
    PseudoArclengthBranchResult,
    PseudoArclengthSettings,
    trace_pseudo_arclength_branch,
)
from pvt_phase_simulator.fluid_models import FluidMixture
from pvt_phase_simulator.plotting import BLUE, GREY, ORANGE

MAXIMUM_POINTS: Final = 60
INITIAL_TEMPERATURE_STEP_K: Final = 5.0
#: The standard envelope cold-starts this far below the operating temperature, and
#: the bubble extension starts from the same place so the two agree where they overlap.
BUBBLE_START_OFFSET_K: Final = -30.0
#: The dew extension starts at, then above, then below the operating temperature. A
#: start inside a region where the engine cannot assign phase roles is rejected by
#: the engine; the next start is then tried.
DEW_START_OFFSETS_K: Final = (0.0, 10.0, -10.0)
NEAR_CRITICAL: Final = "near_critical"

BranchName = Literal["bubble", "dew"]


@dataclass(frozen=True, slots=True)
class ExtensionPoint:
    temperature_k: float
    pressure_pa: float
    temperature_turning_point: bool
    pressure_turning_point: bool


@dataclass(frozen=True, slots=True)
class ExtensionAttempt:
    """One engine call: where it started and how the engine ended it."""

    start_temperature_k: float
    point_count: int
    termination_reason: str
    termination_message: str


@dataclass(frozen=True, slots=True)
class ExtendedBranch:
    branch: BranchName
    points: tuple[ExtensionPoint, ...]
    start_temperature_k: float | None
    termination_reason: str
    termination_message: str
    attempts: tuple[ExtensionAttempt, ...]

    @property
    def reached_critical_region(self) -> bool:
        return bool(self.points) and self.termination_reason == NEAR_CRITICAL


@dataclass(frozen=True, slots=True)
class ExtendedEnvelope:
    bubble: ExtendedBranch
    dew: ExtendedBranch

    @property
    def both_reached_critical_region(self) -> bool:
        return self.bubble.reached_critical_region and self.dew.reached_critical_region


def _attempt(
    mixture: FluidMixture, kind: EnvelopeBranchKind, start_temperature_k: float
) -> tuple[ExtensionAttempt, tuple[ExtensionPoint, ...]]:
    settings = PseudoArclengthSettings(
        initial_temperature_step_k=INITIAL_TEMPERATURE_STEP_K,
        maximum_points=MAXIMUM_POINTS,
    )
    try:
        result: PseudoArclengthBranchResult = trace_pseudo_arclength_branch(
            mixture, kind, settings, start_temperature_k
        )
    except ValueError as error:
        # The engine rejects an unusable start (for example a non-positive
        # temperature). Record it as a rejected attempt rather than crashing.
        return (
            ExtensionAttempt(start_temperature_k, 0, "start_rejected", str(error)),
            (),
        )
    points = tuple(
        ExtensionPoint(
            temperature_k=point.temperature_k,
            pressure_pa=point.pressure_pa,
            temperature_turning_point=point.temperature_turning_point,
            pressure_turning_point=point.pressure_turning_point,
        )
        for point in result.points
    )
    return (
        ExtensionAttempt(
            start_temperature_k,
            len(points),
            result.termination_reason.value,
            result.termination_message,
        ),
        points,
    )


def _extend_branch(
    mixture: FluidMixture,
    branch: BranchName,
    kind: EnvelopeBranchKind,
    starts_k: tuple[float, ...],
) -> ExtendedBranch:
    attempts: list[ExtensionAttempt] = []
    best_points: tuple[ExtensionPoint, ...] = ()
    best_attempt: ExtensionAttempt | None = None
    for start in starts_k:
        attempt, points = _attempt(mixture, kind, start)
        attempts.append(attempt)
        if points and attempt.termination_reason == NEAR_CRITICAL:
            best_points, best_attempt = points, attempt
            break
        if len(points) > len(best_points):
            best_points, best_attempt = points, attempt
    if best_attempt is None:
        best_attempt = attempts[-1]
    return ExtendedBranch(
        branch=branch,
        points=best_points,
        start_temperature_k=best_attempt.start_temperature_k if best_points else None,
        termination_reason=best_attempt.termination_reason,
        termination_message=best_attempt.termination_message,
        attempts=tuple(attempts),
    )


def trace_extended_envelope(
    mixture: FluidMixture, operating_temperature_k: float
) -> ExtendedEnvelope:
    """Trace both branches with the engine's pseudo-arclength continuation."""

    return ExtendedEnvelope(
        bubble=_extend_branch(
            mixture,
            "bubble",
            EnvelopeBranchKind.BUBBLE,
            (operating_temperature_k + BUBBLE_START_OFFSET_K,),
        ),
        dew=_extend_branch(
            mixture,
            "dew",
            EnvelopeBranchKind.DEW,
            tuple(operating_temperature_k + offset for offset in DEW_START_OFFSETS_K),
        ),
    )


#: Figure-trace names, shared with the tests so the overlay stays identifiable.
BUBBLE_TRACE_NAME: Final = "Bubble branch, extended (pseudo-arclength)"
DEW_TRACE_NAME: Final = "Dew branch, extended (pseudo-arclength)"
PRESSURE_TURNING_TRACE_NAME: Final = "Pressure turning point"
TEMPERATURE_TURNING_TRACE_NAME: Final = "Temperature turning point"


def add_extended_branches(figure: Any, extension: ExtendedEnvelope) -> Any:
    """Overlay the extension on a figure whose axes are K and Pa.

    Called before the presentation-unit conversion so the overlay is converted with
    every other trace. Turning points are flagged by the engine, not detected here,
    and are not critical points.
    """

    for name, branch, color in (
        (BUBBLE_TRACE_NAME, extension.bubble, BLUE),
        (DEW_TRACE_NAME, extension.dew, ORANGE),
    ):
        if not branch.points:
            continue
        figure.add_trace(
            go.Scatter(
                x=tuple(point.temperature_k for point in branch.points),
                y=tuple(point.pressure_pa for point in branch.points),
                mode="lines",
                name=name,
                line={"dash": "dot", "width": 2, "color": color},
                hovertemplate=(
                    f"{name}<br>T=%{{x:.8g}} K<br>P=%{{y:.8g}} Pa<extra></extra>"
                ),
            )
        )
    turning_specs: tuple[tuple[str, str, Callable[[ExtensionPoint], bool]], ...] = (
        (
            PRESSURE_TURNING_TRACE_NAME,
            "triangle-up",
            lambda point: point.pressure_turning_point,
        ),
        (
            TEMPERATURE_TURNING_TRACE_NAME,
            "triangle-right",
            lambda point: point.temperature_turning_point,
        ),
    )
    for name, symbol, selector in turning_specs:
        flagged = tuple(
            point
            for branch in (extension.bubble, extension.dew)
            for point in branch.points
            if selector(point)
        )
        if not flagged:
            continue
        figure.add_trace(
            go.Scatter(
                x=tuple(point.temperature_k for point in flagged),
                y=tuple(point.pressure_pa for point in flagged),
                mode="markers",
                name=name,
                marker={"symbol": symbol, "size": 11, "color": GREY},
                hovertemplate=(
                    f"{name} (not a critical point)<br>T=%{{x:.8g}} K"
                    "<br>P=%{y:.8g} Pa<extra></extra>"
                ),
            )
        )
    return figure


def describe_branch(branch: ExtendedBranch) -> tuple[str, str]:
    """Return ``(status, detail)`` text for one branch, from the engine's reasons."""

    reason = branch.termination_reason.replace("_", " ")
    if not branch.points:
        tried = ", ".join(f"{a.start_temperature_k:.0f} K" for a in branch.attempts)
        return (
            f"Not extended ({reason})",
            f"No point was accepted from start temperature(s) {tried}. "
            f"{branch.termination_message}",
        )
    suffix = (
        " - the engine's near-critical guard stopped this branch"
        if branch.reached_critical_region
        else ""
    )
    return (
        f"{reason.capitalize()}{suffix}",
        f"{len(branch.points)} points from {branch.start_temperature_k:.0f} K. "
        f"{branch.termination_message}",
    )


CLOSURE_NOTE: Final = (
    "Both extended branches were stopped by the engine's near-critical guard, so the "
    "curve closes toward the critical region. This is not a certified critical "
    "point; run the Critical Point solver for that."
)
PARTIAL_NOTE: Final = (
    "At least one extended branch stopped for another reason before reaching the "
    "near-critical region, so the envelope is not shown as closed. The stop reasons "
    "above are the engine's own and are not hidden."
)
DISPLAY_ONLY_NOTE: Final = (
    "Extended branches are a display overlay. Exports and the engineering report "
    "contain the standard envelope only."
)
