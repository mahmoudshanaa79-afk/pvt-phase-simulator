"""Audit the dew results the validation record counts as unique (read-only).

P2 (docs/ENGINE_CHANGE_PROPOSALS.md) walks each grid interval next to a failed
node, but the walk stops at the first failed evaluation. Near a mixture critical
point the inner calculation can fail just before a second dew root, so that root
stays hidden and the one visible root is reported as unique. The methane +
n-butane preview (docs/NEW_COMPONENTS_PROPOSAL.md) has such a case.

This tool checks every dew state that ``docs/validation/module17_vle_validation.csv``
reports as converged by a route that does not use the dew solver at all: it
traces PR's bubble isotherm at the state's temperature (the same converged
``(x, P, y)`` samples as tools/run_dew_conditioning_study.py) and counts where
the isotherm's vapour CH4 fraction crosses the measured ``y``. Each crossing is a
PR dew point of that vapour; two crossings mean the dew problem has two roots.
A crossing hidden inside a gap of failed bubble solves would be missed, so a
count of one is evidence, not proof. No engine path changes.

The committed output,
``docs/investigations/dew_uniqueness_audit.csv``,
records the solver *before* proposals P7 and P8 (applied 1 November 2026) and
is kept unchanged as the evidence for them (PR #27). Rerunning this tool on the
current engine gives different results; do not overwrite that output.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from pvt_phase_simulator.experimental_validation import load_experimental_vle_dataset
from tools.run_dew_conditioning_study import HEAVY, _isotherm

OUTPUT = "docs/investigations/dew_uniqueness_audit.csv"


def isotherm_dew_crossings(
    samples: list[tuple[float, float, float]], vapor_methane: float
) -> list[float]:
    """Pressures where the isotherm's vapour CH4 fraction equals ``vapor_methane``.

    Samples are ``(x, P, y)`` ordered by ``x``; each crossing is located by linear
    interpolation between the two neighbouring converged samples.
    """

    crossings = []
    for (_, low_p, low_y), (_, high_p, high_y) in zip(
        samples, samples[1:], strict=False
    ):
        low, high = low_y - vapor_methane, high_y - vapor_methane
        if low == 0.0:
            crossings.append(low_p)
        elif low * high < 0.0:
            crossings.append(low_p + (high_p - low_p) * low / (low - high))
    if samples and samples[-1][2] == vapor_methane:
        crossings.append(samples[-1][1])
    return crossings


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
    stored = {
        row["source_point_id"]: row
        for row in csv.DictReader(
            (root / "docs/validation/module17_vle_validation.csv").open(
                encoding="utf-8"
            )
        )
    }
    isotherms: dict[tuple[float, str], list[tuple[float, float, float]]] = {}
    rows = []
    for point in dataset.points:
        production = stored[point.source_point_id]
        if production["dew_status"] != "converged":
            continue
        key = (point.temperature_k, point.component_ids[1])
        if key not in isotherms:
            isotherms[key] = _isotherm(point.temperature_k, HEAVY[key[1]])
        samples = isotherms[key]
        crossings = isotherm_dew_crossings(samples, point.vapor_mole_fractions[0])
        production_pressure = float(production["dew_predicted_pressure_pa"])
        row = {
            "source_point_id": point.source_point_id,
            "temperature_k": point.temperature_k,
            "experimental_pressure_pa": point.pressure_pa,
            "experimental_vapor_ch4": point.vapor_mole_fractions[0],
            "production_dew_pressure_pa": production_pressure,
            "isotherm_samples": len(samples),
            "highest_isotherm_pressure_pa": max(sample[1] for sample in samples),
            "isotherm_dew_crossings": len(crossings),
            "isotherm_dew_pressures_pa": "|".join(repr(value) for value in crossings),
        }
        rows.append(row)
        print(json.dumps(row), flush=True)
    output = root / OUTPUT
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
