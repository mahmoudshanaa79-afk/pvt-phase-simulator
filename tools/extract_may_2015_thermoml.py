"""Extract the selected May et al. (2015) VLE states from NIST ThermoML JSON."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from io import StringIO
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))

from pvt_phase_simulator.experimental_validation import NORMALIZED_FIELDS  # noqa: E402

EXPECTED_DOI = "10.1021/acs.jced.5b00610"
EXPECTED_TITLE = (
    "Reference Quality Vapor-Liquid Equilibrium Data for the Binary Systems "
    "Methane + Ethane, + Propane, + Butane and, + 2-Methylpropane, at "
    "Temperatures from (203 to 273) K and Pressures to 9 MPa"
)
EXPECTED_AUTHORS = (
    "May, E. F.[Eric F.]",
    "Guo, J. Y.[Jerry Y.]",
    "Oakley, J. H.[Jordan H.]",
    "Hughes, T. J.[Thomas J.]",
    "Graham, B. F.[Brendan F.]",
    "Marsh, K. N.[Kenneth N.]",
    "Huang, S. H.[Stanley H.]",
)
EXPECTED_COMPOUNDS = {
    1: ("methane", "VNWKTOKETHGBQD-UHFFFAOYSA-N"),
    2: ("ethane", "OTMSDBZUPAUEDD-UHFFFAOYSA-N"),
    3: ("propane", "ATUOYWHBWRKTHZ-UHFFFAOYSA-N"),
}
SELECTED_SYSTEMS = (
    ("ch4_c2", "ethane", 1, 2, 1, 2, 17),
    ("ch4_c3", "propane", 1, 3, 3, 4, 23),
)


def _property_descriptor(dataset: dict[str, Any]) -> tuple[str, str, str, int | None]:
    prop = dataset["Property"][0]
    group = prop["Property-MethodID"]["PropertyGroup"]
    group_name = next(name for name in group if name != "tml_elements")
    details = group[group_name]
    return (
        str(details["ePropName"]),
        str(details.get("sMethodName") or details.get("eMethodName")),
        str(prop["PropPhaseID"]["ePropPhase"]),
        prop["Property-MethodID"].get("RegNum", {}).get("nOrgNum"),
    )


def _variable_descriptors(dataset: dict[str, Any]) -> tuple[tuple[object, ...], ...]:
    descriptors = []
    for variable in dataset["Variable"]:
        variable_type = variable["VariableID"]["VariableType"]
        type_name = next(name for name in variable_type if name != "tml_elements")
        descriptors.append(
            (
                variable["nVarNumber"],
                type_name,
                variable_type[type_name],
                variable["VarPhaseID"]["eVarPhase"],
                variable["VariableID"].get("RegNum", {}).get("nOrgNum"),
            )
        )
    return tuple(descriptors)


def _validate_source(document: dict[str, Any]) -> dict[int, dict[str, Any]]:
    citation = document["Citation"]
    if citation["sDOI"] != EXPECTED_DOI or citation["sTitle"] != EXPECTED_TITLE:
        raise ValueError("ThermoML citation identity does not match May et al. (2015).")
    if tuple(citation["sAuthor"]) != EXPECTED_AUTHORS:
        raise ValueError("ThermoML author list does not match the selected source.")
    compounds = {
        int(compound["RegNum"]["nOrgNum"]): compound
        for compound in document["Compound"]
    }
    for number, (name, inchikey) in EXPECTED_COMPOUNDS.items():
        compound = compounds.get(number)
        if (
            compound is None
            or compound["sCommonName"][0] != name
            or compound["sStandardInChIKey"] != inchikey
        ):
            raise ValueError("ThermoML compound mapping is incorrect.")
    return {
        int(dataset["nPureOrMixtureDataNumber"]): dataset
        for dataset in document["PureOrMixtureData"]
    }


def _dataset_values(
    dataset: dict[str, Any], *, expected_count: int
) -> dict[tuple[float, float], tuple[int, float, float]]:
    rows: dict[tuple[float, float], tuple[int, float, float]] = {}
    values = dataset["NumValues"]
    if len(values) != expected_count:
        raise ValueError("ThermoML dataset point count is unexpected.")
    for row_number, row in enumerate(values, start=1):
        variables = {
            int(value["nVarNumber"]): float(value["nVarValue"])
            for value in row["VariableValue"]
        }
        key = (variables[1], variables[2])
        if key in rows:
            raise ValueError("duplicate ThermoML independent-variable pairing key.")
        property_value = row["PropertyValue"][0]
        uncertainty = property_value.get("CombinedUncertainty", {}).get(
            "nCombExpandUncertValue"
        )
        if uncertainty is None:
            raise ValueError("selected ThermoML property uncertainty is missing.")
        rows[key] = (
            row_number,
            float(property_value["nPropValue"]),
            float(uncertainty),
        )
    return rows


def extract_normalized_rows(document: dict[str, Any]) -> tuple[dict[str, str], ...]:
    """Pair pressure and vapor observations by ``(T, x_CH4)``, never by index."""

    datasets = _validate_source(document)
    normalized: list[dict[str, str]] = []
    for (
        system_id,
        heavy_component,
        methane_number,
        heavy_number,
        pressure_number,
        vapor_number,
        expected_count,
    ) in SELECTED_SYSTEMS:
        pressure_dataset = datasets[pressure_number]
        vapor_dataset = datasets[vapor_number]
        expected_components = {methane_number, heavy_number}
        for dataset in (pressure_dataset, vapor_dataset):
            actual_components = {
                int(item["RegNum"]["nOrgNum"]) for item in dataset["Component"]
            }
            if actual_components != expected_components:
                raise ValueError("ThermoML dataset component mapping is incorrect.")
            if _variable_descriptors(dataset) != (
                (1, "eTemperature", "Temperature, K", "Liquid", None),
                (2, "eComponentComposition", "Mole fraction", "Liquid", 1),
            ):
                raise ValueError(
                    "ThermoML independent-variable definition is unexpected."
                )
        if _property_descriptor(pressure_dataset) != (
            "Vapor or sublimation pressure, kPa",
            "Closed cell (Static) method",
            "Liquid",
            None,
        ):
            raise ValueError("ThermoML pressure property or unit is unexpected.")
        if _property_descriptor(vapor_dataset) != (
            "Mole fraction",
            "Chromatography",
            "Gas",
            heavy_number,
        ):
            raise ValueError("ThermoML vapor-composition property is unexpected.")
        pressure_values = _dataset_values(
            pressure_dataset, expected_count=expected_count
        )
        vapor_values = _dataset_values(vapor_dataset, expected_count=expected_count)
        if pressure_values.keys() != vapor_values.keys():
            missing_vapor = sorted(pressure_values.keys() - vapor_values.keys())
            missing_pressure = sorted(vapor_values.keys() - pressure_values.keys())
            raise ValueError(
                "ThermoML pressure/vapor observations are unpairable: "
                f"missing vapor={missing_vapor}, missing pressure={missing_pressure}."
            )
        for ordinal, (temperature_k, x_methane) in enumerate(
            sorted(pressure_values), start=1
        ):
            pressure_row, pressure_kpa, pressure_uncertainty_kpa = pressure_values[
                (temperature_k, x_methane)
            ]
            vapor_row, y_heavy, vapor_uncertainty = vapor_values[
                (temperature_k, x_methane)
            ]
            normalized.append(
                {
                    "source_point_id": f"may2015_{system_id}_{ordinal:03d}",
                    "source_pair_key": (f"T={temperature_k:g} K|x_CH4={x_methane:g}"),
                    "system_id": system_id,
                    "component_1_id": "methane",
                    "component_2_id": heavy_component,
                    "temperature_k": repr(temperature_k),
                    "temperature_unit": "K",
                    "pressure_kpa": repr(pressure_kpa),
                    "pressure_original_unit": "kPa",
                    "pressure_pa": repr(pressure_kpa * 1000.0),
                    "pressure_canonical_unit": "Pa",
                    "liquid_methane_mole_fraction": repr(x_methane),
                    "liquid_heavy_mole_fraction": repr(1.0 - x_methane),
                    "vapor_methane_mole_fraction": repr(1.0 - y_heavy),
                    "vapor_heavy_mole_fraction": repr(y_heavy),
                    "composition_unit": "1",
                    "pressure_expanded_uncertainty_kpa": repr(pressure_uncertainty_kpa),
                    "pressure_expanded_uncertainty_pa": repr(
                        pressure_uncertainty_kpa * 1000.0
                    ),
                    "vapor_heavy_expanded_uncertainty": repr(vapor_uncertainty),
                    "uncertainty_confidence_level_percent": "95.0",
                    "pressure_dataset_number": str(pressure_number),
                    "pressure_source_row": str(pressure_row),
                    "vapor_dataset_number": str(vapor_number),
                    "vapor_source_row": str(vapor_row),
                }
            )
    return tuple(normalized)


def normalized_rows_to_csv(rows: tuple[dict[str, str], ...]) -> str:
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=NORMALIZED_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = json.loads(args.input.read_text(encoding="utf-8"))
    output = normalized_rows_to_csv(extract_normalized_rows(document))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8", newline="")
    print(f"wrote {output.count(chr(10)) - 1} normalized VLE points to {args.output}")


if __name__ == "__main__":
    main()
