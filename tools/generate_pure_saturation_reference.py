"""Generate pure-component saturation reference values from CoolProp (offline).

This script is NOT part of the application or its dependencies. It is run once,
in a throwaway environment, to produce a small reference table:

    uv run --no-project --python 3.12 --with "CoolProp==6.6.0" \
        python tools/generate_pure_saturation_reference.py

CoolProp (MIT licence) evaluates the published reference equations of state named
in the provenance file (Setzmann & Wagner 1991 for methane, Buecker & Wagner 2006
for ethane, Lemmon et al. 2009 for propane). The output is the reference side of
``tools/run_pure_saturation_study.py``; the Peng-Robinson side is computed by the
unchanged engine.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import CoolProp  # type: ignore[import-not-found]
import CoolProp.CoolProp as CP  # type: ignore[import-not-found]  # noqa: N811

FLUIDS = {"methane": "Methane", "ethane": "Ethane", "propane": "Propane"}
#: Reduced temperatures T/Tc of the reference states (Tc from the reference EOS).
REDUCED_TEMPERATURES = tuple(round(0.50 + 0.02 * index, 2) for index in range(25))
OUTPUT = Path("docs/investigations")


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows = []
    provenance: dict[str, object] = {
        "generator": "tools/generate_pure_saturation_reference.py",
        "coolprop_version": CoolProp.__version__,
        "reduced_temperatures": list(REDUCED_TEMPERATURES),
        "fluids": {},
    }
    fluids = provenance["fluids"]
    assert isinstance(fluids, dict)
    for component_id, name in FLUIDS.items():
        critical_temperature = CP.PropsSI("Tcrit", name)
        triple_temperature = CP.PropsSI("Ttriple", name)
        fluids[component_id] = {
            "coolprop_name": name,
            "equation_of_state": CP.get_fluid_param_string(name, "BibTeX-EOS"),
            "reference_critical_temperature_k": critical_temperature,
            "reference_critical_pressure_pa": CP.PropsSI("pcrit", name),
            "reference_triple_temperature_k": triple_temperature,
        }
        for reduced in REDUCED_TEMPERATURES:
            temperature = reduced * critical_temperature
            if temperature <= triple_temperature:
                continue
            rows.append(
                {
                    "component_id": component_id,
                    "reduced_temperature": reduced,
                    "temperature_k": temperature,
                    "saturation_pressure_pa": CP.PropsSI(
                        "P", "T", temperature, "Q", 0, name
                    ),
                    "liquid_molar_density_mol_m3": CP.PropsSI(
                        "Dmolar", "T", temperature, "Q", 0, name
                    ),
                    "vapor_molar_density_mol_m3": CP.PropsSI(
                        "Dmolar", "T", temperature, "Q", 1, name
                    ),
                }
            )
    with (OUTPUT / "pure_saturation_reference.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (OUTPUT / "pure_saturation_reference_provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{len(rows)} reference states written")


if __name__ == "__main__":
    main()
