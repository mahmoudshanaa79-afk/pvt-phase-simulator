"""Show where the production dew scan misses a second root (read-only).

For every CH4+C2 and CH4+C3 dew state that production reports as converged while the
Module 17 diagnostic scan found more than one PR dew root, this tool finds the
first grid interval above the returned root whose lower node converged and whose
upper node did not, then searches densely inside only that interval with the
public solver. It prints whether the hidden root is recovered there. Evidence
for proposal P2 in docs/ENGINE_CHANGE_PROPOSALS.md; nothing is modified.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from pvt_phase_simulator.eos.saturation_pressure import (
    SaturationKind,
    calculate_saturation_pressure,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    FluidMixture,
    MixtureComponent,
)

LOCAL_SEARCH_POINTS = 41
HEAVY = {"ch4_c2": ETHANE, "ch4_c3": PROPANE}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = parser.parse_args().root.resolve()
    rows = csv.DictReader(
        (root / "docs/validation/module17_vle_validation.csv").open(encoding="utf-8")
    )
    for row in rows:
        roots = json.loads(row["dew_diagnostic_root_pressures_pa"] or "[]")
        if row["dew_status"] != "converged":
            continue
        if len(roots) < 2:
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
        assert result.pressure_pa is not None
        nodes = sorted(result.evaluation_history, key=lambda item: item.pressure_pa)
        boundary = next(
            (
                (low.pressure_pa, high.pressure_pa)
                for low, high in zip(nodes, nodes[1:], strict=False)
                if low.pressure_pa > result.pressure_pa
                and low.converged
                and not high.converged
            ),
            None,
        )
        if boundary is None:
            print(f"{row['source_point_id']}: no converged/non-converged boundary")
            continue
        local = calculate_saturation_pressure(
            mixture,
            temperature,
            SaturationKind.DEW_POINT,
            boundary[0],
            boundary[1],
            pressure_search_points=LOCAL_SEARCH_POINTS,
        )
        recovered = (
            "none"
            if local.pressure_pa is None
            else f"{local.pressure_pa / 1e6:.4f} MPa ({local.status.value})"
        )
        print(
            f"{row['source_point_id']}: production {result.pressure_pa / 1e6:.4f} MPa; "
            f"scan roots {[round(p / 1e6, 4) for p in roots]} MPa; boundary "
            f"{boundary[0] / 1e6:.3f}-{boundary[1] / 1e6:.3f} MPa -> {recovered}"
        )


if __name__ == "__main__":
    main()
