"""What-if: are "not found" saturation results roots hidden next to failed nodes?

P2 (docs/ENGINE_CHANGE_PROPOSALS.md) walks each grid interval between a
converged and a non-converged node, but only when the scan already found exactly
one root. When the scan finds no root, nothing is walked and the result is
``not_found``. Near a mixture critical point the inner calculation collapses to
the trivial solution at the grid node just above the root, so a real root can sit
in exactly such an interval.

For every default ``not_found`` state this tool replays the P2 walk (same step
count, same tolerance, the engine's own pressure evaluation) from each
converged/non-converged boundary, solves any sign change it finds with
``brentq`` on the engine objective, and compares the root with an independent
solve using the engine's Newton option. Only the evaluation function and a
provenance helper are called; no engine file or production path changes. This
is evidence for a design decision, not a production path.

The committed output,
``docs/investigations/empty_scan_whatif.csv``,
records the solver *before* proposals P7 and P8 (applied 1 November 2026) and
is kept unchanged as the evidence for them (PR #27). Rerunning this tool on the
current engine gives different results; do not overwrite that output.
"""

from __future__ import annotations

import argparse
import csv
import json
from math import exp, log
from pathlib import Path

from scipy.optimize import brentq  # type: ignore[import-untyped]

from pvt_phase_simulator.eos.mixing_rules import BinaryInteractionPolicy
from pvt_phase_simulator.eos.saturation_pressure import (
    BOUNDARY_REFINEMENT_STEPS,
    SATURATION_OBJECTIVE_TOLERANCE,
    SaturationKind,
    SaturationPressureEvaluation,
    SaturationStatus,
    _phase_interaction_provenance,
    calculate_saturation_pressure,
    calculate_wilson_pressure_estimates,
    evaluate_saturation_pressure,
)
from pvt_phase_simulator.experimental_validation import (
    COMPONENT_OBJECTS,
    load_experimental_vle_dataset,
)
from pvt_phase_simulator.fluid_models import FluidMixture, MixtureComponent

OUTPUT = "docs/investigations/empty_scan_whatif.csv"


def boundary_roots(
    mixture: FluidMixture, temperature_k: float, kind: SaturationKind
) -> tuple[SaturationStatus, list[tuple[float, float]]]:
    """Default status and every ``(low, high)`` sign change found by the walk."""

    result = calculate_saturation_pressure(mixture, temperature_k, kind)
    if result.status is not SaturationStatus.NOT_FOUND:
        return result.status, []
    estimates = calculate_wilson_pressure_estimates(mixture, temperature_k)
    estimate = (
        estimates.bubble_pressure_pa
        if kind is SaturationKind.BUBBLE_POINT
        else estimates.dew_pressure_pa
    )
    provenance = _phase_interaction_provenance(
        mixture, temperature_k, estimate, None, BinaryInteractionPolicy.DEFAULT_ZERO
    )

    def evaluate(pressure: float) -> SaturationPressureEvaluation:
        return evaluate_saturation_pressure(
            mixture, temperature_k, pressure, kind, provenance
        )

    scanned = sorted(result.evaluation_history, key=lambda item: item.pressure_pa)
    brackets = []
    for left, right in zip(scanned[:-1], scanned[1:], strict=True):
        left_ok = left.converged and left.objective is not None
        right_ok = right.converged and right.objective is not None
        if left_ok == right_ok:
            continue
        start, end = (left, right) if left_ok else (right, left)
        assert start.objective is not None
        start_log = log(start.pressure_pa)
        step = (log(end.pressure_pa) - start_log) / BOUNDARY_REFINEMENT_STEPS
        previous_pressure, previous = start.pressure_pa, start.objective
        for index in range(1, BOUNDARY_REFINEMENT_STEPS):
            pressure = exp(start_log + index * step)
            evaluation = evaluate(pressure)
            if not evaluation.converged or evaluation.objective is None:
                break
            if abs(evaluation.objective) <= SATURATION_OBJECTIVE_TOLERANCE:
                brackets.append((pressure, pressure))
                break
            if evaluation.objective * previous < 0.0:
                brackets.append(
                    (min(previous_pressure, pressure), max(previous_pressure, pressure))
                )
                break
            previous_pressure, previous = pressure, evaluation.objective
    return result.status, brackets


def _root(
    mixture: FluidMixture,
    temperature_k: float,
    kind: SaturationKind,
    bracket: tuple[float, float],
) -> float:
    low, high = bracket
    if low == high:
        return low
    provenance = _phase_interaction_provenance(
        mixture, temperature_k, low, None, BinaryInteractionPolicy.DEFAULT_ZERO
    )

    def objective(log_pressure: float) -> float:
        evaluation = evaluate_saturation_pressure(
            mixture, temperature_k, exp(log_pressure), kind, provenance
        )
        if not evaluation.converged or evaluation.objective is None:
            raise RuntimeError("evaluation failed inside a confirmed bracket")
        return float(evaluation.objective)

    return exp(brentq(objective, log(low), log(high), xtol=1e-12))


def analyze(
    mixture: FluidMixture, temperature_k: float, kind: SaturationKind
) -> dict[str, object]:
    status, brackets = boundary_roots(mixture, temperature_k, kind)
    roots = [_root(mixture, temperature_k, kind, item) for item in brackets]
    newton = calculate_saturation_pressure(
        mixture, temperature_k, kind, saturation_newton_enabled=True
    )
    row: dict[str, object] = {
        "default_status": status.value,
        "walk_root_count": len(roots),
        "walk_roots_pa": "|".join(repr(root) for root in roots),
        "walk_root_incipient_first_component": None,
        "walk_root_max_fugacity_residual": None,
        "newton_status": newton.status.value,
        "newton_pressure_pa": newton.pressure_pa,
    }
    if len(roots) == 1:
        # Evidence that the root is a real, non-trivial equilibrium state.
        provenance = _phase_interaction_provenance(
            mixture, temperature_k, roots[0], None, BinaryInteractionPolicy.DEFAULT_ZERO
        )
        state = evaluate_saturation_pressure(
            mixture, temperature_k, roots[0], kind, provenance
        )
        row["walk_root_incipient_first_component"] = state.incipient_composition[0]
        row["walk_root_max_fugacity_residual"] = max(
            abs(value)
            for value in state.fugacity_equilibrium_residuals
            if value is not None
        )
    return row


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return parser.parse_args()


def main() -> None:
    root = _arguments().root.resolve()
    dataset = load_experimental_vle_dataset(
        root / "data/experimental/may_2015_ch4_c2_ch4_c3_vle.csv",
        root / "data/experimental/may_2015_source_manifest.json",
    )
    rows = []
    for point in dataset.points:
        for kind, parent in (
            (SaturationKind.BUBBLE_POINT, point.liquid_mole_fractions),
            (SaturationKind.DEW_POINT, point.vapor_mole_fractions),
        ):
            mixture = FluidMixture(
                tuple(
                    MixtureComponent(COMPONENT_OBJECTS[component], fraction)
                    for component, fraction in zip(
                        point.component_ids, parent, strict=True
                    )
                )
            )
            status = calculate_saturation_pressure(
                mixture, point.temperature_k, kind
            ).status
            if status is not SaturationStatus.NOT_FOUND:
                continue
            row: dict[str, object] = {
                "source_point_id": point.source_point_id,
                "direction": kind.value,
                "temperature_k": point.temperature_k,
                "measured_pressure_pa": point.pressure_pa,
            }
            row |= analyze(mixture, point.temperature_k, kind)
            rows.append(row)
            print(json.dumps(row), flush=True)
    output = root / OUTPUT
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
