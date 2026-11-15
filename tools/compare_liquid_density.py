"""Compare measured liquid densities with Peng–Robinson, with and without the shift.

Ready to run once a ThermoML file of measured liquid densities can be
downloaded (the web sessions' proxy blocks trc.nist.gov; the desktop can fetch
it). Input is the JSON rendering of a ThermoML record.

For every liquid-density dataset of one or two admitted components (methane,
ethane, propane), the tool reads each measured state (T, P and, for a binary,
the mole fraction of the composition variable) and computes:

- the untranslated PR molar volume of the liquid root, the smallest real root
  above B of the PR cubic at that T, P and composition, from the frozen
  engine's public functions;
- the translated molar volume, with the shipped Péneloux shifts, through the
  public functions of ``src/pvt_phase_simulator/eos/volume_translation.py``
  (unchanged);
- the relative density error of each against the measurement.

Supported properties:
- "Molar density, mol/m3", "Molar density, mol/dm3" and "Molar volume, m3/mol";
- "Mass density, kg/m3", only with ``--molar-mass NAME=g/mol`` for every
  component. The engine stores no molar masses, so the caller must supply
  them and cite their source; the summary records them.

Anything else is listed as skipped with the reason. Writes a per-state CSV and
a summary Markdown file (AARD, maximum error and bias, before and after the
shift), with the input's SHA-256.

    uv run python tools/compare_liquid_density.py --input record.json --output-dir out
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from io import StringIO
from math import fsum
from pathlib import Path
from typing import Any

from pvt_phase_simulator.eos.mixing_rules import (
    calculate_peng_robinson_mixture_parameters,
)
from pvt_phase_simulator.eos.peng_robinson import calculate_compressibility_roots
from pvt_phase_simulator.eos.volume_translation import (
    eos_molar_volume,
    translated_molar_volume,
)
from pvt_phase_simulator.fluid_models import Component, FluidMixture, MixtureComponent
from tools.compare_thermoml_vle import ADMITTED_BY_INCHIKEY

PRESSURE_TO_PA = {"Pressure, kPa": 1.0e3, "Pressure, MPa": 1.0e6, "Pressure, Pa": 1.0}
FIELDS = (
    "state_id",
    "components",
    "temperature_k",
    "pressure_pa",
    "mole_fraction_1",
    "measured_molar_density_mol_m3",
    "measured_expanded_uncertainty_mol_m3",
    "pr_liquid_z",
    "pr_molar_density_mol_m3",
    "translated_molar_density_mol_m3",
    "pr_relative_error",
    "translated_relative_error",
    "note",
)


class DensityLayoutError(ValueError):
    """The record does not have a layout this tool reads."""


@dataclass(frozen=True, slots=True)
class DensityState:
    state_id: str
    components: tuple[Component, ...]
    temperature_k: float
    pressure_pa: float
    mole_fractions: tuple[float, ...]
    molar_density_mol_m3: float
    uncertainty_mol_m3: float | None


def _group(container: dict[str, Any]) -> tuple[str, Any]:
    name = next(key for key in container if key != "tml_elements")
    return name, container[name]


def _to_molar_density(
    name: str,
    value: float,
    components: tuple[Component, ...],
    fractions: tuple[float, ...],
    molar_masses: dict[str, float],
) -> float | None:
    if name == "Molar density, mol/m3":
        return value
    if name == "Molar density, mol/dm3":
        return value * 1.0e3
    if name == "Molar volume, m3/mol":
        return 1.0 / value
    if name == "Mass density, kg/m3":
        if not all(component.name in molar_masses for component in components):
            return None
        grams_per_mol = fsum(
            fraction * molar_masses[component.name]
            for component, fraction in zip(components, fractions, strict=True)
        )
        return value / (grams_per_mol * 1.0e-3)
    return None


def read_states(
    document: dict[str, Any], molar_masses: dict[str, float] | None = None
) -> tuple[list[DensityState], list[str]]:
    masses = molar_masses or {}
    compounds = {
        int(item["RegNum"]["nOrgNum"]): ADMITTED_BY_INCHIKEY.get(
            str(item.get("sStandardInChIKey"))
        )
        for item in document["Compound"]
    }
    states: list[DensityState] = []
    skipped: list[str] = []
    for dataset in document["PureOrMixtureData"]:
        number = dataset.get("nPureOrMixtureDataNumber")
        members = sorted(
            int(item["RegNum"]["nOrgNum"]) for item in dataset["Component"]
        )
        if not 1 <= len(members) <= 2 or any(compounds.get(m) is None for m in members):
            skipped.append(f"dataset {number}: not one or two admitted components")
            continue
        if not dataset.get("Property"):
            skipped.append(f"dataset {number}: no property")
            continue
        prop = dataset["Property"][0]
        _, details = _group(prop["Property-MethodID"]["PropertyGroup"])
        name = str(details["ePropName"])
        if prop["PropPhaseID"]["ePropPhase"] != "Liquid" or not (
            "density" in name.lower() or "volume" in name.lower()
        ):
            skipped.append(
                f"dataset {number}: property {name!r} is not a liquid density"
            )
            continue
        t_var = p_var = x_var = None
        p_factor = 1.0
        x_compound = None
        for variable in dataset["Variable"]:
            type_name, label = _group(variable["VariableID"]["VariableType"])
            var_number = int(variable["nVarNumber"])
            if type_name == "eTemperature" and label == "Temperature, K":
                t_var = var_number
            elif type_name == "ePressure" and label in PRESSURE_TO_PA:
                p_var, p_factor = var_number, PRESSURE_TO_PA[label]
            elif type_name == "eComponentComposition" and label == "Mole fraction":
                x_var = var_number
                x_compound = int(variable["VariableID"]["RegNum"]["nOrgNum"])
        if t_var is None or p_var is None or (len(members) == 2 and x_var is None):
            skipped.append(f"dataset {number}: variables are not T, P (and x)")
            continue
        order = (
            members
            if len(members) == 1
            else [x_compound, next(m for m in members if m != x_compound)]
        )
        components = tuple(compounds[m] for m in order)  # type: ignore[misc]
        for index, row in enumerate(dataset["NumValues"], start=1):
            values = {
                int(v["nVarNumber"]): float(v["nVarValue"])
                for v in row["VariableValue"]
            }
            fractions = (
                (1.0,) if len(members) == 1 else (values[x_var], 1.0 - values[x_var])  # type: ignore[index]
            )
            prop_value = row["PropertyValue"][0]
            measured = _to_molar_density(
                name,
                float(prop_value["nPropValue"]),
                components,
                fractions,
                masses,  # type: ignore[arg-type]
            )
            if measured is None:
                skipped.append(
                    f"dataset {number}: {name!r} needs --molar-mass for every component"
                )
                break
            raw_u = prop_value.get("CombinedUncertainty", {}).get(
                "nCombExpandUncertValue"
            )
            uncertainty = None
            if raw_u is not None:
                scaled = _to_molar_density(
                    name,
                    float(raw_u),
                    components,
                    fractions,
                    masses,  # type: ignore[arg-type]
                )
                uncertainty = None if name == "Molar volume, m3/mol" else scaled
            states.append(
                DensityState(
                    state_id=f"dataset{number}-{index:03d}",
                    components=components,  # type: ignore[arg-type]
                    temperature_k=values[t_var],
                    pressure_pa=values[p_var] * p_factor,
                    mole_fractions=fractions,
                    molar_density_mol_m3=measured,
                    uncertainty_mol_m3=uncertainty,
                )
            )
    return states, skipped


def compare_state(state: DensityState) -> dict[str, object]:
    mixture = FluidMixture(
        tuple(
            MixtureComponent(component, fraction)
            for component, fraction in zip(
                state.components, state.mole_fractions, strict=True
            )
        )
    )
    parameters = calculate_peng_robinson_mixture_parameters(
        mixture, state.temperature_k, state.pressure_pa
    )
    roots = [
        root
        for root in calculate_compressibility_roots(parameters.A_mix, parameters.B_mix)
        if root > parameters.B_mix
    ]
    row: dict[str, object] = {
        "state_id": state.state_id,
        "components": "+".join(component.name for component in state.components),
        "temperature_k": state.temperature_k,
        "pressure_pa": state.pressure_pa,
        "mole_fraction_1": state.mole_fractions[0],
        "measured_molar_density_mol_m3": state.molar_density_mol_m3,
        "measured_expanded_uncertainty_mol_m3": state.uncertainty_mol_m3,
        "pr_liquid_z": None,
        "pr_molar_density_mol_m3": None,
        "translated_molar_density_mol_m3": None,
        "pr_relative_error": None,
        "translated_relative_error": None,
        "note": "",
    }
    if not roots:
        row["note"] = "no PR root above B at this state"
        return row
    z_liquid = min(roots)
    if len(roots) == 1:
        row["note"] = "one real root only: a liquid-like root is assumed, not proven"
    plain = eos_molar_volume(z_liquid, state.temperature_k, state.pressure_pa)
    shifted = translated_molar_volume(
        z_liquid,
        state.temperature_k,
        state.pressure_pa,
        list(state.components),
        list(state.mole_fractions),
    )
    measured = state.molar_density_mol_m3
    row |= {
        "pr_liquid_z": z_liquid,
        "pr_molar_density_mol_m3": 1.0 / plain,
        "translated_molar_density_mol_m3": 1.0 / shifted,
        "pr_relative_error": (1.0 / plain - measured) / measured,
        "translated_relative_error": (1.0 / shifted - measured) / measured,
    }
    return row


def summarize(rows: list[dict[str, object]]) -> dict[str, float | int | None]:
    def stats(key: str) -> tuple[float | None, float | None, float | None]:
        values = [float(str(row[key])) for row in rows if row[key] is not None]
        if not values:
            return None, None, None
        return (
            100 * fsum(abs(v) for v in values) / len(values),
            100 * max(abs(v) for v in values),
            100 * fsum(values) / len(values),
        )

    pr = stats("pr_relative_error")
    shifted = stats("translated_relative_error")
    return {
        "states": len(rows),
        "compared": sum(row["pr_relative_error"] is not None for row in rows),
        "pr_aard_percent": pr[0],
        "pr_max_percent": pr[1],
        "pr_bias_percent": pr[2],
        "translated_aard_percent": shifted[0],
        "translated_max_percent": shifted[1],
        "translated_bias_percent": shifted[2],
        "worse_after_shift": sum(
            row["pr_relative_error"] is not None
            and abs(float(str(row["translated_relative_error"])))
            > abs(float(str(row["pr_relative_error"])))
            for row in rows
        ),
    }


def rows_to_csv(rows: list[dict[str, object]]) -> str:
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: "" if row[key] is None else row[key] for key in FIELDS})
    return stream.getvalue()


def summary_markdown(
    rows: list[dict[str, object]],
    skipped: list[str],
    source: str,
    sha256: str,
    molar_masses: dict[str, float],
) -> str:
    s = summarize(rows)

    def number(value: object) -> str:
        return "n/a" if value is None else f"{float(str(value)):.2f}"

    lines = [
        "# Liquid-density comparison with Peng–Robinson (with and without the shift)",
        "",
        f"Input: `{source}` (SHA-256 `{sha256}`). States: {s['states']}; compared: "
        f"{s['compared']}.",
        "",
        "| | AARD (%) | Max abs. error (%) | Bias (%) |",
        "|---|---:|---:|---:|",
        f"| PR | {number(s['pr_aard_percent'])} | {number(s['pr_max_percent'])} | "
        f"{number(s['pr_bias_percent'])} |",
        f"| PR + Péneloux shift | {number(s['translated_aard_percent'])} | "
        f"{number(s['translated_max_percent'])} | "
        f"{number(s['translated_bias_percent'])} |",
        "",
        f"The shift makes the error worse at {s['worse_after_shift']} of "
        f"{s['compared']} states.",
        "",
        "Molar masses supplied: "
        + (", ".join(f"{k} {v} g/mol" for k, v in molar_masses.items()) or "none"),
        "",
        "## Notes and skipped datasets",
        "",
    ]
    notes = [f"- {row['state_id']}: {row['note']}" for row in rows if row["note"]]
    lines += notes + [f"- skipped {item}" for item in skipped] or ["- none"]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--molar-mass",
        action="append",
        default=[],
        metavar="NAME=G_PER_MOL",
        help="needed only for mass densities, for example Methane=16.04; cite it",
    )
    arguments = parser.parse_args()
    masses = {
        item.split("=", 1)[0]: float(item.split("=", 1)[1])
        for item in arguments.molar_mass
    }
    raw = arguments.input.read_bytes()
    states, skipped = read_states(json.loads(raw.decode("utf-8")), masses)
    if not states:
        print("No usable liquid-density states of admitted components were found.")
        for item in skipped:
            print(f"  skipped {item}")
        return 1
    rows = [compare_state(state) for state in states]
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    stem = arguments.input.stem
    (arguments.output_dir / f"{stem}_density.csv").write_text(
        rows_to_csv(rows), encoding="utf-8", newline=""
    )
    summary = summary_markdown(
        rows,
        skipped,
        arguments.input.name,
        hashlib.sha256(raw).hexdigest().upper(),
        masses,
    )
    (arguments.output_dir / f"{stem}_density_summary.md").write_text(
        summary, encoding="utf-8"
    )
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
