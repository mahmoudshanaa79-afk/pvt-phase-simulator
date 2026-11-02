"""Confirm every dew root behind a HIDDEN_SATURATION_ROOT result (read-only).

Since proposal P2, the production saturation solver refines grid intervals next
to a non-converged node and reports a state as ambiguous when that reveals a
second root. Since P8 it also runs a bounded Newton solve past a failed walk
step, and a root found that way can make a state ambiguous although it was never
bracketed between two converged evaluations.

For every Module 17 dew state whose record carries the
``HIDDEN_SATURATION_ROOT`` diagnostic, this tool confirms the roots
independently of the production verdict, by two routes:

* **bracketed**: re-run the production solve, list each sign change of the
  saturation objective between converged evaluations, and solve inside each of
  those narrow intervals with the public solver;
* **bubble isotherm**: trace PR's bubble isotherm at the state's temperature
  (the converged ``(x, P, y)`` samples of tools/run_dew_conditioning_study.py)
  and find where its vapour CH4 fraction crosses the measured ``y``, as
  tools/run_dew_uniqueness_audit.py does. This route never calls the dew solver;
  it misses a root that lies beyond the last converged bubble solve near the
  critical point;
* **dew branch**: trace the dew curve of the measured vapour with the engine's
  pseudo-arclength continuation (the tracer behind the app's extended envelope)
  from ``BRANCH_START_K`` upward, and list where it crosses the state's
  temperature. Crossing pressures are linear interpolations between
  continuation points, so they locate a root to about 1 %, not exactly. This
  route does not use the saturation scan at all.

A state is confirmed when one route alone finds at least two distinct roots.
Routes are tried in the order above, and the output names the first that
confirms.
The output says which route confirmed each state. Nothing is modified.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from pvt_phase_simulator.eos.phase_envelope import EnvelopeBranchKind
from pvt_phase_simulator.eos.pseudo_arclength import (
    PseudoArclengthSettings,
    trace_pseudo_arclength_branch,
)
from pvt_phase_simulator.eos.saturation_pressure import (
    SaturationKind,
    SaturationStatus,
    calculate_saturation_pressure,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    Component,
    FluidMixture,
    MixtureComponent,
)
from tools.run_dew_conditioning_study import _isotherm
from tools.run_dew_uniqueness_audit import isotherm_dew_crossings

LOCAL_SEARCH_POINTS = 11
HEAVY: dict[str, Component] = {"ch4_c2": ETHANE, "ch4_c3": PROPANE}
OUTPUT = "docs/investigations/hidden_dew_root_check.csv"
#: Two roots closer than this (relative) count as the same root.
SAME_ROOT_RELATIVE = 0.005
#: Same-root tolerance for the interpolated dew-branch crossings.
BRANCH_SAME_ROOT_RELATIVE = 0.02
#: Dew-branch continuation: start temperature, first step and point budget.
BRANCH_START_K = {"ch4_c2": 200.0, "ch4_c3": 180.0}
BRANCH_TEMPERATURE_STEP_K = 2.0
BRANCH_MAXIMUM_POINTS = 300


def distinct(
    pressures: list[float], relative: float = SAME_ROOT_RELATIVE
) -> list[float]:
    """Sorted pressures with near-duplicates (within ``relative``) merged."""

    kept: list[float] = []
    for value in sorted(pressures):
        if not kept or value - kept[-1] > relative * kept[-1]:
            kept.append(value)
    return kept


def bracketed_roots(mixture: FluidMixture, temperature_k: float) -> list[float]:
    """Roots solved inside the sign changes between converged evaluations."""

    result = calculate_saturation_pressure(
        mixture, temperature_k, SaturationKind.DEW_POINT
    )
    converged = sorted(
        (
            item
            for item in result.evaluation_history
            if item.converged and item.objective is not None
        ),
        key=lambda item: item.pressure_pa,
    )
    roots = []
    for low, high in zip(converged, converged[1:], strict=False):
        assert low.objective is not None and high.objective is not None
        if low.objective * high.objective >= 0.0:
            continue
        local = calculate_saturation_pressure(
            mixture,
            temperature_k,
            SaturationKind.DEW_POINT,
            low.pressure_pa,
            high.pressure_pa,
            pressure_search_points=LOCAL_SEARCH_POINTS,
        )
        if local.status is SaturationStatus.CONVERGED and local.pressure_pa is not None:
            roots.append(local.pressure_pa)
    return distinct(roots)


def branch_crossings(
    mixture: FluidMixture, temperature_k: float, start_temperature_k: float
) -> tuple[list[float], str]:
    """Pressures where the traced dew branch crosses ``temperature_k``."""

    result = trace_pseudo_arclength_branch(
        mixture,
        EnvelopeBranchKind.DEW,
        PseudoArclengthSettings(
            initial_temperature_step_k=BRANCH_TEMPERATURE_STEP_K,
            maximum_points=BRANCH_MAXIMUM_POINTS,
        ),
        start_temperature_k,
    )
    points = [(point.temperature_k, point.pressure_pa) for point in result.points]
    crossings = []
    for (t_low, p_low), (t_high, p_high) in zip(points, points[1:], strict=False):
        if t_low == temperature_k:
            crossings.append(p_low)
        elif (t_low - temperature_k) * (t_high - temperature_k) < 0.0:
            fraction = (temperature_k - t_low) / (t_high - t_low)
            crossings.append(p_low + fraction * (p_high - p_low))
    return (
        distinct(crossings, BRANCH_SAME_ROOT_RELATIVE),
        result.termination_reason.value,
    )


def route(bracketed: list[float], isotherm: list[float], branch: list[float]) -> str:
    """Name the first route that confirms two or more roots, or say none does."""

    if len(bracketed) >= 2:
        return "bracketed"
    if len(isotherm) >= 2:
        return "bubble isotherm"
    if len(branch) >= 2:
        return "dew branch"
    return "not confirmed"


def _mpa(values: list[float]) -> str:
    return "|".join(f"{value / 1e6:.4f}" for value in values)


def check(root: Path) -> list[dict[str, object]]:
    rows = []
    isotherms: dict[tuple[float, str], list[tuple[float, float, float]]] = {}
    with (root / "docs/validation/module17_vle_validation.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        records = list(csv.DictReader(stream))
    for record in records:
        codes = json.loads(record["dew_diagnostic_codes"])
        if "HIDDEN_SATURATION_ROOT" not in codes:
            continue
        system = record["system_id"]
        vapor = json.loads(record["vapor_mole_fractions"])
        temperature = float(record["temperature_k"])
        mixture = FluidMixture(
            (
                MixtureComponent(METHANE, vapor[0]),
                MixtureComponent(HEAVY[system], vapor[1]),
            )
        )
        bracketed = bracketed_roots(mixture, temperature)
        key = (temperature, system)
        if key not in isotherms:
            isotherms[key] = _isotherm(temperature, HEAVY[system])
        isotherm = distinct(isotherm_dew_crossings(isotherms[key], vapor[0]))
        branch, branch_stop = branch_crossings(
            mixture, temperature, BRANCH_START_K[system]
        )
        scan = [
            float(value)
            for value in json.loads(record["dew_diagnostic_root_pressures_pa"])
        ]
        row: dict[str, object] = {
            "source_point_id": record["source_point_id"],
            "system_id": system,
            "temperature_k": temperature,
            "vapor_ch4": vapor[0],
            "dew_status": record["dew_status"],
            "module17_root_pressures_mpa": _mpa(scan),
            "bracketed_roots_mpa": _mpa(bracketed),
            "isotherm_crossings_mpa": _mpa(isotherm),
            "dew_branch_crossings_mpa": _mpa(branch),
            "dew_branch_stop": branch_stop,
            "confirmed_by": route(bracketed, isotherm, branch),
        }
        rows.append(row)
        print(json.dumps(row), flush=True)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = parser.parse_args().root.resolve()
    rows = check(root)
    with (root / OUTPUT).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
