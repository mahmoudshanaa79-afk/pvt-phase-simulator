"""Preview PR against the May (2015) methane + butane data (read-only).

May et al. (2015), the source of the production CH4+C2 and CH4+C3 dataset,
also measured CH4+isobutane and CH4+n-butane, and the same NIST ThermoML
record holds both. This tool answers one question for the owner before any
change to ``data/``: how does the unchanged engine do on those two binaries?

* The ThermoML JSON is read from ``--thermoml`` and must match the SHA-256
  already recorded in ``data/experimental/may_2015_source_manifest.json``. It
  is not redistributed; only normalized numerical facts are written, as for
  the production dataset.
* Each butane dataset lists one measurement twice with every value identical.
  The repeat is skipped (``skip_identical_duplicates``); any duplicate key with
  different values would still be rejected.
* Butane critical constants are not in ``data/component_properties.csv``. The
  values below are PROVISIONAL: they come from CoolProp 6.6.0, which evaluates
  the Buecker-Wagner (2006) reference equations of state, and have not yet been
  checked against the project's source of record (Yang & Richter 2025).
* Every state is solved with the production defaults (scanning solver, Newton
  off, kij = 0), as in Module 17. Non-converged and ambiguous results are
  reported with the engine's own status, reason and diagnostic codes.

Output goes to ``docs/investigations``; nothing under ``data/`` or
``docs/validation`` is written.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from pvt_phase_simulator.eos.saturation_pressure import (
    SaturationKind,
    SaturationStatus,
    calculate_saturation_pressure,
)
from pvt_phase_simulator.fluid_models import (
    METHANE,
    Component,
    FluidMixture,
    MixtureComponent,
)
from tools import extract_may_2015_thermoml as extractor

#: PROVISIONAL constants from CoolProp 6.6.0 (``Tcrit``, ``pcrit``, ``acentric``),
#: reproduced with:
#: uv run --no-project --python 3.12 --with "CoolProp==6.6.0" python -c
#: "import CoolProp.CoolProp as CP; print([CP.PropsSI(k, 'IsoButane')
#: for k in ('Tcrit', 'pcrit', 'acentric')])"
PROVISIONAL_COMPONENTS: dict[str, Component] = {
    "isobutane": Component(
        name="isobutane",
        critical_temperature_k=407.817,
        critical_pressure_pa=3629000.0,
        acentric_factor=0.183532,
    ),
    "n_butane": Component(
        name="n_butane",
        critical_temperature_k=425.125,
        critical_pressure_pa=3796000.0,
        acentric_factor=0.20081,
    ),
}
POINTS_FILE = "docs/investigations/butane_preview_points.csv"
RESULTS_FILE = "docs/investigations/butane_preview.csv"


def _mixture(heavy: Component, methane: float) -> FluidMixture:
    return FluidMixture(
        (
            MixtureComponent(METHANE, methane),
            MixtureComponent(heavy, 1.0 - methane),
        )
    )


def solve_point(row: dict[str, str], kind: SaturationKind) -> dict[str, object]:
    """Solve one measured state in one direction with the production defaults."""

    heavy = PROVISIONAL_COMPONENTS[row["component_2_id"]]
    bubble = kind is SaturationKind.BUBBLE_POINT
    parent = float(
        row["liquid_methane_mole_fraction" if bubble else "vapor_methane_mole_fraction"]
    )
    measured = float(row["pressure_pa"])
    result = calculate_saturation_pressure(
        _mixture(heavy, parent), float(row["temperature_k"]), kind
    )
    converged = (
        result.status is SaturationStatus.CONVERGED and result.pressure_pa is not None
    )
    pressure = result.pressure_pa if converged else None
    incipient = result.incipient_composition[0] if converged else None
    expected_incipient = float(
        row["vapor_methane_mole_fraction" if bubble else "liquid_methane_mole_fraction"]
    )
    return {
        "source_point_id": row["source_point_id"],
        "system_id": row["system_id"],
        "direction": kind.value,
        "temperature_k": float(row["temperature_k"]),
        "experimental_pressure_pa": measured,
        "pressure_expanded_uncertainty_pa": float(
            row["pressure_expanded_uncertainty_pa"]
        ),
        "status": result.status.value,
        "failure_reason": result.failure_reason or "",
        "predicted_pressure_pa": pressure,
        "pressure_percent_error": (
            None if pressure is None else 100.0 * (pressure - measured) / measured
        ),
        "predicted_incipient_methane": incipient,
        "incipient_methane_error": (
            None if incipient is None else incipient - expected_incipient
        ),
        "diagnostic_codes": "|".join(
            sorted({item.code for item in result.diagnostics})
        ),
    }


def _verified_document(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest().upper()
    if digest != manifest["raw_json_sha256"].upper():
        raise ValueError(f"ThermoML JSON SHA-256 {digest} does not match the manifest.")
    return dict(json.loads(raw.decode("utf-8")))


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thermoml", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return parser.parse_args()


def main() -> None:
    arguments = _arguments()
    root = arguments.root.resolve()
    manifest = json.loads(
        (root / "data/experimental/may_2015_source_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    points = extractor.extract_normalized_rows(
        _verified_document(arguments.thermoml, manifest),
        extractor.BUTANE_SYSTEMS,
        extractor.BUTANE_COMPOUNDS,
        skip_identical_duplicates=True,
    )
    _write_csv(root / POINTS_FILE, [dict(point) for point in points])
    results = []
    for point in points:
        for kind in (SaturationKind.BUBBLE_POINT, SaturationKind.DEW_POINT):
            result = solve_point(point, kind)
            results.append(result)
            print(json.dumps(result), flush=True)
    _write_csv(root / RESULTS_FILE, results)


if __name__ == "__main__":
    main()
