"""Fit and check the optional Péneloux volume shifts (owner approval C).

The shift of each component is anchored at one state: the saturated liquid at
reduced temperature 0.7 in ``docs/investigations/pure_saturation_reference.csv``
(reference equations of state through CoolProp 6.6.0; see the provenance JSON
next to it). With the Péneloux convention ``v = v_PR - c``,

    c = 1 / rho_PR,liquid(T_r = 0.7) - 1 / rho_reference,liquid(T_r = 0.7),

where rho_PR is the unchanged engine's saturated-liquid density at its own
saturation pressure (``tools/run_pure_saturation_study.compare_state``).

Every other reference state is held out. For each one this tool reports the
liquid and vapour density errors before and after the shift. It writes
``docs/investigations/volume_translation_fit.csv`` and prints the shifts in the
form ``src/pvt_phase_simulator/eos/volume_translation.py`` stores them. It is
read-only with respect to the engine, data and protected validation records.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from statistics import mean

from tools.run_pure_saturation_study import COMPONENTS, compare_state

ANCHOR_REDUCED_TEMPERATURE = 0.7
FIELDS = (
    "component_id",
    "reduced_temperature",
    "role",
    "reference_liquid_density_mol_m3",
    "model_liquid_density_mol_m3",
    "translated_liquid_density_mol_m3",
    "liquid_error_before",
    "liquid_error_after",
    "reference_vapor_density_mol_m3",
    "model_vapor_density_mol_m3",
    "translated_vapor_density_mol_m3",
    "vapor_error_before",
    "vapor_error_after",
)


def translated_density(model_density: float, shift: float) -> float:
    """Molar density after the Péneloux shift ``v = v_PR - c``."""

    return 1.0 / (1.0 / model_density - shift)


def fit_shifts(rows: list[dict[str, str]]) -> dict[str, float]:
    """The anchored shift of each component, in m3/mol, from the engine."""

    shifts = {}
    for row in rows:
        if float(row["reduced_temperature"]) != ANCHOR_REDUCED_TEMPERATURE:
            continue
        state = compare_state(row)
        if state.model_liquid_density_mol_m3 is None:
            raise RuntimeError(f"{row['component_id']}: anchor state did not converge")
        shifts[row["component_id"]] = (
            1.0 / state.model_liquid_density_mol_m3
            - 1.0 / state.reference_liquid_density_mol_m3
        )
    if sorted(shifts) != sorted(COMPONENTS):
        raise RuntimeError("every component needs exactly one anchor state")
    return shifts


def held_out_rows(
    comparison: list[dict[str, str]], shifts: dict[str, float]
) -> list[dict[str, object]]:
    """Before/after density errors from the committed comparison file."""

    rows: list[dict[str, object]] = []
    for item in comparison:
        if item["model_status"] != "converged":
            continue
        shift = shifts[item["component_id"]]
        reduced = float(item["reduced_temperature"])
        out: dict[str, object] = {
            "component_id": item["component_id"],
            "reduced_temperature": reduced,
            "role": "anchor" if reduced == ANCHOR_REDUCED_TEMPERATURE else "held_out",
        }
        for phase in ("liquid", "vapor"):
            reference = float(item[f"reference_{phase}_density_mol_m3"])
            model = float(item[f"model_{phase}_density_mol_m3"])
            translated = translated_density(model, shift)
            out |= {
                f"reference_{phase}_density_mol_m3": reference,
                f"model_{phase}_density_mol_m3": model,
                f"translated_{phase}_density_mol_m3": translated,
                f"{phase}_error_before": (model - reference) / reference,
                f"{phase}_error_after": (translated - reference) / reference,
            }
        rows.append(out)
    return rows


def summary(rows: list[dict[str, object]]) -> dict[str, dict[str, float]]:
    """Held-out AARD (%) and maximum |error| (%) per component, before/after."""

    result: dict[str, dict[str, float]] = {}
    for component_id in COMPONENTS:
        group = [
            row
            for row in rows
            if row["component_id"] == component_id and row["role"] == "held_out"
        ]
        entry: dict[str, float] = {"states": float(len(group))}
        for key in (
            "liquid_error_before",
            "liquid_error_after",
            "vapor_error_before",
            "vapor_error_after",
        ):
            values = [abs(float(str(row[key]))) for row in group]
            entry[f"{key}_aard_percent"] = 100 * mean(values)
            entry[f"{key}_max_percent"] = 100 * max(values)
        result[component_id] = entry
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = parser.parse_args().root.resolve()
    directory = root / "docs/investigations"
    with (directory / "pure_saturation_reference.csv").open(encoding="utf-8") as f:
        reference = list(csv.DictReader(f))
    with (directory / "pure_saturation_comparison.csv").open(encoding="utf-8") as f:
        comparison = list(csv.DictReader(f))
    shifts = fit_shifts(reference)
    rows = held_out_rows(comparison, shifts)
    with (directory / "volume_translation_fit.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    for component_id, shift in shifts.items():
        print(f"{component_id}: c = {shift!r} m3/mol ({shift * 1e6:.3f} cm3/mol)")
    for component_id, entry in summary(rows).items():
        print(component_id, {key: round(value, 3) for key, value in entry.items()})


if __name__ == "__main__":
    main()
