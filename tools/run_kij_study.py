"""What does a non-zero kij do for Peng-Robinson on the measured data? (read-only)

Proposal P6. The engine already accepts a binary interaction parameter kij, but
the validation module fixes kij = 0, so this tool calls the production
saturation solver state by state with the same arguments Module 17 uses (the
scanning solver, Newton refinement off) plus ``binary_interactions``.

For each binary and each kij on a grid from -0.02 to 0.06 it records, per
direction, the engine's own status and reason codes for every measured state:

* converged (unique root), ``not_found``, and ``inconclusive`` split by the
  engine's diagnostics into ``HIDDEN_SATURATION_ROOT`` and the other
  ``MULTIPLE_SATURATION_ROOTS`` cases;
* the pressure AARD over the converged states only, always with its n.

kij is then fitted per binary by minimising the bubble-pressure AARD over a
FIXED set of states, those that converge at every kij on a fine grid, so that
states dropping in or out of convergence cannot move the optimum. Dew pressure
is only an out-of-sample check (it is ill-conditioned, see
docs/DEW_INVESTIGATION.md). A leave-one-isotherm-out refit and a bootstrap over
states show how stable the optimum is. The P3 dew-composition comparison
(``tools/run_dew_conditioning_study.py``) is repeated at kij = 0 and at the
fitted kij.

The May (2015) CH4+C2 and CH4+C3 data are the production dataset. CH4+isobutane
and CH4+n-butane come from the butane preview (``tools/run_butane_preview.py``)
with PROVISIONAL critical constants and are reported separately.

Nothing under src/, data/ or docs/validation/ is written. Output goes to
docs/investigations/. ``--render-only`` rebuilds kij_study.md from the committed
CSV and JSON without solving anything.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections.abc import Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Any

from scipy.optimize import minimize_scalar  # type: ignore[import-untyped]

from pvt_phase_simulator.eos.saturation_pressure import (
    SaturationKind,
    SaturationStatus,
    calculate_saturation_pressure,
)
from pvt_phase_simulator.experimental_validation import load_experimental_vle_dataset
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    Component,
    FluidMixture,
    MixtureComponent,
)

COARSE_GRID: tuple[float, ...] = tuple(round(-0.02 + 0.005 * i, 3) for i in range(17))
FINE_GRID: tuple[float, ...] = tuple(round(-0.02 + 0.001 * i, 3) for i in range(81))
DIRECTIONS = ("bubble", "dew")
PRODUCTION_SYSTEMS = ("ch4_c2", "ch4_c3")
PROVISIONAL_SYSTEMS = ("ch4_ic4", "ch4_nc4")
SYSTEM_LABELS = {
    "ch4_c2": "CH4+C2",
    "ch4_c3": "CH4+C3",
    "ch4_ic4": "CH4+iC4 (provisional)",
    "ch4_nc4": "CH4+nC4 (provisional)",
}
#: kij band reported as the sensitivity of the fit: every kij whose fixed-set
#: bubble AARD is within this many percentage points of the minimum.
AARD_BAND_PERCENTAGE_POINTS = 0.1
BOOTSTRAP_RESAMPLES = 1000
BOOTSTRAP_SEED = 20261101
#: Temperatures closer than this belong to the same isotherm.
ISOTHERM_GAP_K = 1.0

SUMMARY_FILE = "docs/investigations/kij_study.csv"
STATES_FILE = "docs/investigations/kij_study_states.csv"
FINE_FILE = "docs/investigations/kij_study_fine_bubble.csv"
FIT_FILE = "docs/investigations/kij_study_fit.json"
REPORT_FILE = "docs/investigations/kij_study.md"
DATA_FILE = "data/experimental/may_2015_ch4_c2_ch4_c3_vle.csv"
MANIFEST_FILE = "data/experimental/may_2015_source_manifest.json"


@dataclass(frozen=True, slots=True)
class State:
    """One measured VLE state of a methane + heavy binary."""

    system_id: str
    point_id: str
    heavy: str
    temperature_k: float
    pressure_pa: float
    liquid_methane: float
    vapor_methane: float


@dataclass(frozen=True, slots=True)
class Outcome:
    """The production solver's answer for one state, direction and kij."""

    system_id: str
    point_id: str
    kind: str
    kij: float
    temperature_k: float
    measured_pressure_pa: float
    status: str
    category: str
    predicted_pressure_pa: float | None
    percent_error: float | None
    diagnostic_codes: str
    failure_reason: str


# --- data -----------------------------------------------------------------------


def _production_states(root: Path) -> list[State]:
    dataset = load_experimental_vle_dataset(root / DATA_FILE, root / MANIFEST_FILE)
    return [
        State(
            system_id=point.system_id,
            point_id=point.source_point_id,
            heavy=point.component_ids[1],
            temperature_k=point.temperature_k,
            pressure_pa=point.pressure_pa,
            liquid_methane=point.liquid_mole_fractions[0],
            vapor_methane=point.vapor_mole_fractions[0],
        )
        for point in dataset.points
    ]


def _butane_states(root: Path) -> list[State]:
    from tools import run_butane_preview as butanes

    with (root / butanes.POINTS_FILE).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    return [
        State(
            system_id=row["system_id"],
            point_id=row["source_point_id"],
            heavy=row["component_2_id"],
            temperature_k=float(row["temperature_k"]),
            pressure_pa=float(row["pressure_pa"]),
            liquid_methane=float(row["liquid_methane_mole_fraction"]),
            vapor_methane=float(row["vapor_methane_mole_fraction"]),
        )
        for row in rows
    ]


@cache
def heavy_component(name: str) -> Component:
    if name == "ethane":
        return ETHANE
    if name == "propane":
        return PROPANE
    from tools import run_butane_preview as butanes

    return butanes.PROVISIONAL_COMPONENTS[name]


def interactions(heavy: Component, kij: float) -> dict[tuple[str, str], float] | None:
    """Symmetric kij for the binary, or None (the engine's kij = 0 default) at 0."""

    if kij == 0.0:
        return None
    return {(METHANE.name, heavy.name): kij, (heavy.name, METHANE.name): kij}


# --- solving --------------------------------------------------------------------


def classify(status: str, codes: Iterable[str]) -> str:
    """Name the outcome from the engine's own status and diagnostic codes."""

    code_set = set(codes)
    if status == SaturationStatus.CONVERGED.value:
        return "converged"
    if status == SaturationStatus.INCONCLUSIVE.value:
        if "HIDDEN_SATURATION_ROOT" in code_set:
            return "hidden_root"
        if "MULTIPLE_SATURATION_ROOTS" in code_set:
            return "multiple_roots"
        return "inconclusive_other"
    return status


def solve(state: State, kind: str, kij: float) -> Outcome:
    """The production default solve (Newton off), as in Module 17, plus kij."""

    heavy = heavy_component(state.heavy)
    parent = state.liquid_methane if kind == "bubble" else state.vapor_methane
    result = calculate_saturation_pressure(
        FluidMixture(
            (MixtureComponent(METHANE, parent), MixtureComponent(heavy, 1.0 - parent))
        ),
        state.temperature_k,
        SaturationKind.BUBBLE_POINT if kind == "bubble" else SaturationKind.DEW_POINT,
        binary_interactions=interactions(heavy, kij),
    )
    codes = tuple(sorted({item.code for item in result.diagnostics}))
    converged = (
        result.status is SaturationStatus.CONVERGED and result.pressure_pa is not None
    )
    pressure = result.pressure_pa if converged else None
    return Outcome(
        system_id=state.system_id,
        point_id=state.point_id,
        kind=kind,
        kij=kij,
        temperature_k=state.temperature_k,
        measured_pressure_pa=state.pressure_pa,
        status=result.status.value,
        category=classify(result.status.value, codes),
        predicted_pressure_pa=pressure,
        percent_error=(
            None
            if pressure is None
            else 100.0 * (pressure - state.pressure_pa) / state.pressure_pa
        ),
        diagnostic_codes="|".join(codes),
        failure_reason=result.failure_reason or "",
    )


def _solve_task(task: tuple[State, str, float]) -> Outcome:
    return solve(*task)


def solve_all(tasks: Sequence[tuple[State, str, float]], workers: int) -> list[Outcome]:
    if workers <= 1:
        return [_solve_task(task) for task in tasks]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_solve_task, tasks, chunksize=4))


# --- statistics -----------------------------------------------------------------


def summarize(outcomes: Sequence[Outcome]) -> dict[str, Any]:
    """Status counts and the AARD over converged states, with its n."""

    categories = [item.category for item in outcomes]
    errors = [item.percent_error for item in outcomes if item.percent_error is not None]
    return {
        "states": len(outcomes),
        "converged": categories.count("converged"),
        "not_found": categories.count("not_found"),
        "hidden_root": categories.count("hidden_root"),
        "multiple_roots": categories.count("multiple_roots"),
        "inconclusive_other": categories.count("inconclusive_other"),
        "failed": categories.count("failed"),
        "aard_n": len(errors),
        "aard_percent": sum(abs(e) for e in errors) / len(errors) if errors else None,
        "bias_percent": sum(errors) / len(errors) if errors else None,
        "max_abs_percent": max(abs(e) for e in errors) if errors else None,
    }


def isotherms(states: Sequence[State]) -> list[list[State]]:
    """Group states into isotherms: a new group starts after a gap of 1 K."""

    ordered = sorted(states, key=lambda state: state.temperature_k)
    groups: list[list[State]] = []
    for state in ordered:
        if (
            groups
            and state.temperature_k - groups[-1][-1].temperature_k < ISOTHERM_GAP_K
        ):
            groups[-1].append(state)
        else:
            groups.append([state])
    return groups


def _aard(errors: Iterable[float]) -> float:
    values = [abs(e) for e in errors]
    return sum(values) / len(values)


def fit_system(
    states: Sequence[State], bubble: dict[tuple[str, float], Outcome]
) -> dict[str, Any]:
    """Fit kij to the bubble AARD over the states converged at every fine kij."""

    common = [
        state
        for state in states
        if all(
            bubble[(state.point_id, kij)].percent_error is not None for kij in FINE_GRID
        )
    ]
    changing = sorted(
        {
            state.point_id
            for state in states
            if len({bubble[(state.point_id, kij)].category for kij in FINE_GRID}) > 1
        }
    )
    if not common:
        return {"common_n": 0, "status_changes_with_kij": changing}

    def errors_at(kij: float, chosen: Sequence[State]) -> list[float]:
        return [float(bubble[(s.point_id, kij)].percent_error or 0.0) for s in chosen]

    curve = {kij: _aard(errors_at(kij, common)) for kij in FINE_GRID}
    best_grid = min(curve, key=curve.__getitem__)

    def objective(kij: float) -> float:
        outcomes = [solve(state, "bubble", float(kij)) for state in common]
        if any(item.percent_error is None for item in outcomes):
            return float("inf")
        return _aard(float(item.percent_error or 0.0) for item in outcomes)

    low = max(FINE_GRID[0], best_grid - 0.001)
    high = min(FINE_GRID[-1], best_grid + 0.001)
    refined = minimize_scalar(
        objective, bounds=(low, high), method="bounded", options={"xatol": 1e-5}
    )
    optimum = round(float(refined.x), 4)
    if objective(optimum) > curve[best_grid]:
        optimum = best_grid

    minimum = min(curve.values())
    band = [
        kij
        for kij, value in curve.items()
        if value <= minimum + AARD_BAND_PERCENTAGE_POINTS
    ]

    rng = random.Random(BOOTSTRAP_SEED)
    resampled = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        sample = [rng.choice(common) for _ in common]
        resampled.append(min(FINE_GRID, key=lambda kij: _aard(errors_at(kij, sample))))
    resampled.sort()

    leave_one_out = []
    common_ids = {state.point_id for state in common}
    for group in isotherms(states):
        held_ids = {state.point_id for state in group}
        train = [state for state in common if state.point_id not in held_ids]
        if not train:
            continue
        train_best = min(FINE_GRID, key=lambda kij: _aard(errors_at(kij, train)))
        held = [
            state
            for state in group
            if bubble[(state.point_id, 0.0)].percent_error is not None
            and bubble[(state.point_id, train_best)].percent_error is not None
        ]
        leave_one_out.append(
            {
                "temperature_k_min": group[0].temperature_k,
                "temperature_k_max": group[-1].temperature_k,
                "held_out_states": len(group),
                "held_out_in_fixed_set": len(held_ids & common_ids),
                "held_out_scored": len(held),
                "train_n": len(train),
                "train_kij": train_best,
                "held_out_aard_at_zero": _aard(errors_at(0.0, held)) if held else None,
                "held_out_aard_at_train_kij": (
                    _aard(errors_at(train_best, held)) if held else None
                ),
            }
        )

    return {
        "common_n": len(common),
        "common_point_ids": [state.point_id for state in common],
        "status_changes_with_kij": changing,
        "grid_optimum": best_grid,
        "optimum": optimum,
        "aard_at_zero": curve[0.0],
        "aard_at_grid_optimum": curve[best_grid],
        "aard_at_optimum": objective(optimum),
        "band_low": min(band),
        "band_high": max(band),
        "bootstrap_low": resampled[int(0.025 * BOOTSTRAP_RESAMPLES)],
        "bootstrap_high": resampled[int(0.975 * BOOTSTRAP_RESAMPLES) - 1],
        "leave_one_isotherm_out": leave_one_out,
        "fine_curve": [[kij, curve[kij]] for kij in FINE_GRID],
    }


def _analyze_task(task: tuple[Any, float]) -> dict[str, Any]:
    from tools.run_dew_conditioning_study import analyze_dew_state

    point, kij = task
    return asdict(analyze_dew_state(point, kij))


def dew_composition(
    system: str, kij: float, root: Path, workers: int
) -> dict[str, Any]:
    """The P3 comparison y_PR(P_exp) - y_exp over U_y, at one kij."""

    dataset = load_experimental_vle_dataset(root / DATA_FILE, root / MANIFEST_FILE)
    tasks = [(point, kij) for point in dataset.points if point.system_id == system]
    if workers <= 1:
        rows = [_analyze_task(task) for task in tasks]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(_analyze_task, tasks))
    assessed = [
        row for row in rows if row["vapor_difference_over_uncertainty"] is not None
    ]
    ratios = [abs(row["vapor_difference_over_uncertainty"]) for row in assessed]
    differences = [row["vapor_ch4_difference"] for row in assessed]
    return {
        "kij": kij,
        "states": len(rows),
        "assessed": len(assessed),
        "above_isotherm": len(rows) - len(assessed),
        "within_one_u": sum(value <= 1.0 for value in ratios),
        "within_two_u": sum(value <= 2.0 for value in ratios),
        "mean_abs_difference": (
            sum(abs(d) for d in differences) / len(differences) if differences else None
        ),
        "mean_difference": sum(differences) / len(differences) if differences else None,
        "rows": rows,
    }


# --- output ---------------------------------------------------------------------

SUMMARY_FIELDS = (
    "system_id",
    "provisional",
    "kij",
    "kij_role",
    "kind",
    "states",
    "converged",
    "not_found",
    "hidden_root",
    "multiple_roots",
    "inconclusive_other",
    "failed",
    "aard_n",
    "aard_percent",
    "bias_percent",
    "max_abs_percent",
)


FINE_FIELDS = ("system_id", "point_id", "kij", "category", "percent_error")


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return repr(value)
    return str(value)


def write_csv(
    path: Path, fields: Sequence[str], rows: Iterable[dict[str, Any]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _cell(row.get(key)) for key in fields})


def compute(root: Path, include_butanes: bool, workers: int) -> None:
    states = _production_states(root)
    if include_butanes:
        states += _butane_states(root)
    systems = PRODUCTION_SYSTEMS + (PROVISIONAL_SYSTEMS if include_butanes else ())

    bubble_tasks = [(state, "bubble", kij) for state in states for kij in FINE_GRID]
    dew_tasks = [(state, "dew", kij) for state in states for kij in COARSE_GRID]
    outcomes = solve_all(bubble_tasks + dew_tasks, workers)
    by_key = {(o.system_id, o.point_id, o.kind, o.kij): o for o in outcomes}

    fits: dict[str, Any] = {}
    for system in systems:
        system_states = [state for state in states if state.system_id == system]
        bubble = {
            (state.point_id, kij): by_key[(system, state.point_id, "bubble", kij)]
            for state in system_states
            for kij in FINE_GRID
        }
        fits[system] = fit_system(system_states, bubble)

    # A fitted kij off the coarse grid needs its own solves in both directions.
    optimum_tasks = [
        (state, kind, fits[state.system_id]["optimum"])
        for state in states
        if fits[state.system_id].get("optimum", 0.0) not in COARSE_GRID
        for kind in DIRECTIONS
    ]
    for outcome in solve_all(optimum_tasks, workers):
        by_key[(outcome.system_id, outcome.point_id, outcome.kind, outcome.kij)] = (
            outcome
        )

    summary_rows = []
    state_rows = []
    for system in systems:
        kijs = list(COARSE_GRID)
        if "optimum" in fits[system] and fits[system]["optimum"] not in kijs:
            kijs.append(fits[system]["optimum"])
        for kij in sorted(kijs):
            for kind in DIRECTIONS:
                selected = [
                    o
                    for (s, _, k, value), o in by_key.items()
                    if s == system and k == kind and value == kij
                ]
                role = "optimum" if kij == fits[system].get("optimum") else "grid"
                if kij == 0.0:
                    role = "zero" if role == "grid" else "zero_optimum"
                summary_rows.append(
                    {
                        "system_id": system,
                        "provisional": system in PROVISIONAL_SYSTEMS,
                        "kij": kij,
                        "kij_role": role,
                        "kind": kind,
                        **summarize(selected),
                    }
                )
                state_rows.extend(
                    asdict(o) for o in sorted(selected, key=lambda o: o.point_id)
                )

    composition = {
        system: [
            dew_composition(system, 0.0, root, workers),
            dew_composition(system, fits[system]["optimum"], root, workers),
        ]
        for system in PRODUCTION_SYSTEMS
        if "optimum" in fits[system]
    }

    fine_rows = [
        {
            "system_id": o.system_id,
            "point_id": o.point_id,
            "kij": o.kij,
            "category": o.category,
            "percent_error": o.percent_error,
        }
        for o in outcomes
        if o.kind == "bubble"
    ]
    write_csv(root / SUMMARY_FILE, SUMMARY_FIELDS, summary_rows)
    write_csv(root / FINE_FILE, FINE_FIELDS, fine_rows)
    write_csv(root / STATES_FILE, tuple(Outcome.__dataclass_fields__), state_rows)
    document = {
        "coarse_grid": list(COARSE_GRID),
        "fine_grid_step": 0.001,
        "aard_band_percentage_points": AARD_BAND_PERCENTAGE_POINTS,
        "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "fits": fits,
        "dew_composition": {
            system: [
                {k: v for k, v in entry.items() if k != "rows"} for entry in entries
            ]
            for system, entries in composition.items()
        },
    }
    (root / FIT_FILE).write_text(
        json.dumps(document, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--no-butanes", action="store_true")
    parser.add_argument("--render-only", action="store_true")
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    if not arguments.render_only:
        compute(root, not arguments.no_butanes, arguments.workers)
    from tools.kij_study_report import render

    (root / REPORT_FILE).write_text(render(root), encoding="utf-8")


if __name__ == "__main__":
    main()
