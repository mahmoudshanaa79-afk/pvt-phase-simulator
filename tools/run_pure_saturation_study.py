"""Compare Peng-Robinson pure-component saturation with reference EOS values.

Reads ``docs/investigations/pure_saturation_reference.csv`` (generated offline by
``tools/generate_pure_saturation_reference.py`` from published reference
equations of state) and evaluates the unchanged engine at the same temperatures:
saturation pressure (production solver, Newton refinement on) and the saturated
liquid and vapour molar densities from the selected PR roots. Writes
``docs/investigations/pure_saturation_comparison.csv`` and prints a summary.
Read-only with respect to the engine, data and protected validation artifacts.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean

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
from pvt_phase_simulator.physical_constants import UNIVERSAL_GAS_CONSTANT

COMPONENTS: dict[str, Component] = {
    "methane": METHANE,
    "ethane": ETHANE,
    "propane": PROPANE,
}


@dataclass(frozen=True, slots=True)
class PureSaturationComparison:
    component_id: str
    reduced_temperature: float
    temperature_k: float
    reference_pressure_pa: float
    model_pressure_pa: float | None
    pressure_relative_error: float | None
    reference_liquid_density_mol_m3: float
    model_liquid_density_mol_m3: float | None
    liquid_density_relative_error: float | None
    reference_vapor_density_mol_m3: float
    model_vapor_density_mol_m3: float | None
    vapor_density_relative_error: float | None
    model_status: str


def _relative(model: float | None, reference: float) -> float | None:
    return None if model is None else (model - reference) / reference


def compare_state(row: dict[str, str]) -> PureSaturationComparison:
    """Evaluate PR at one reference saturation temperature."""

    component = COMPONENTS[row["component_id"]]
    temperature = float(row["temperature_k"])
    result = calculate_saturation_pressure(
        FluidMixture((MixtureComponent(component, 1.0),)),
        temperature,
        SaturationKind.BUBBLE_POINT,
        saturation_newton_enabled=True,
    )
    pressure: float | None = None
    liquid: float | None = None
    vapor: float | None = None
    if (
        result.status is SaturationStatus.CONVERGED
        and result.pressure_pa is not None
        and result.parent_phase is not None
        and result.incipient_phase is not None
    ):
        pressure = result.pressure_pa
        scale = pressure / (UNIVERSAL_GAS_CONSTANT * temperature)
        # Bubble point: the parent phase is the liquid, the incipient the vapour.
        liquid = scale / result.parent_phase.selected_compressibility_factor
        vapor = scale / result.incipient_phase.selected_compressibility_factor
    reference_pressure = float(row["saturation_pressure_pa"])
    reference_liquid = float(row["liquid_molar_density_mol_m3"])
    reference_vapor = float(row["vapor_molar_density_mol_m3"])
    return PureSaturationComparison(
        component_id=row["component_id"],
        reduced_temperature=float(row["reduced_temperature"]),
        temperature_k=temperature,
        reference_pressure_pa=reference_pressure,
        model_pressure_pa=pressure,
        pressure_relative_error=_relative(pressure, reference_pressure),
        reference_liquid_density_mol_m3=reference_liquid,
        model_liquid_density_mol_m3=liquid,
        liquid_density_relative_error=_relative(liquid, reference_liquid),
        reference_vapor_density_mol_m3=reference_vapor,
        model_vapor_density_mol_m3=vapor,
        vapor_density_relative_error=_relative(vapor, reference_vapor),
        model_status=result.status.value,
    )


def _aard(values: list[float | None]) -> str:
    present = [abs(value) for value in values if value is not None]
    return f"{100 * mean(present):6.2f} %" if present else "   n/a"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    root = parser.parse_args().root.resolve()
    directory = root / "docs/investigations"
    reference_rows = list(
        csv.DictReader(
            (directory / "pure_saturation_reference.csv").open(encoding="utf-8")
        )
    )
    results = [compare_state(row) for row in reference_rows]
    with (directory / "pure_saturation_comparison.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(results[0])))
        writer.writeheader()
        writer.writerows(asdict(result) for result in results)
    print("component  states  solved  Psat AARD  liquid-density AARD  vapour AARD")
    for component_id in COMPONENTS:
        group = [item for item in results if item.component_id == component_id]
        solved = sum(item.model_pressure_pa is not None for item in group)
        print(
            f"{component_id:9s}  {len(group):6d}  {solved:6d}  "
            f"{_aard([item.pressure_relative_error for item in group])}  "
            f"{_aard([item.liquid_density_relative_error for item in group]):>18s}  "
            f"{_aard([item.vapor_density_relative_error for item in group]):>11s}"
        )


if __name__ == "__main__":
    main()
