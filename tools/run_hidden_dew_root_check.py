"""Confirm every dew root behind a HIDDEN_SATURATION_ROOT result (read-only).

Since proposal P2, the production saturation solver refines grid intervals next
to a non-converged node and reports a state as ambiguous when that reveals a
second root. For every Module 17 dew state whose record carries the
``HIDDEN_SATURATION_ROOT`` diagnostic, this tool re-runs the production solve,
lists each sign change of the saturation objective between converged
evaluations, and solves inside each of those narrow intervals with the public
solver. Each interval must yield a converged root. That is independent
confirmation that the state really has more than one PR dew pressure. Nothing is
modified.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from pvt_phase_simulator.eos.saturation_pressure import (
    SaturationKind,
    SaturationStatus,
    calculate_saturation_pressure,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    FluidMixture,
    MixtureComponent,
)

LOCAL_SEARCH_POINTS = 11
HEAVY = {"ch4_c2": ETHANE, "ch4_c3": PROPANE}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = parser.parse_args().root.resolve()
    rows = csv.DictReader(
        (root / "docs/validation/module17_vle_validation.csv").open(encoding="utf-8")
    )
    for row in rows:
        if "HIDDEN_SATURATION_ROOT" not in json.loads(row["dew_diagnostic_codes"]):
            continue
        vapor = json.loads(row["vapor_mole_fractions"])
        temperature = float(row["temperature_k"])
        mixture = FluidMixture(
            (
                MixtureComponent(METHANE, vapor[0]),
                MixtureComponent(HEAVY[row["system_id"]], vapor[1]),
            )
        )
        result = calculate_saturation_pressure(
            mixture, temperature, SaturationKind.DEW_POINT
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
                temperature,
                SaturationKind.DEW_POINT,
                low.pressure_pa,
                high.pressure_pa,
                pressure_search_points=LOCAL_SEARCH_POINTS,
            )
            if (
                local.status is SaturationStatus.CONVERGED
                and local.pressure_pa is not None
            ):
                roots.append(round(local.pressure_pa / 1e6, 4))
        scan = json.loads(row["dew_diagnostic_root_pressures_pa"])
        print(
            f"{row['source_point_id']}: production {result.status.value}; "
            f"confirmed dew roots {roots} MPa; Module 17 scan roots "
            f"{[round(value / 1e6, 4) for value in scan]} MPa"
        )


if __name__ == "__main__":
    main()
