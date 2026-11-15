"""Compare a NIST ThermoML VLE record with the frozen engine (bubble and dew).

Ready to run once a ThermoML file can be downloaded (the web sessions' proxy
blocks trc.nist.gov; the desktop can fetch it). Input is the JSON rendering of
a ThermoML record, the format ``tools/extract_may_2015_thermoml.py`` reads.

The tool:

1. identifies the record's compounds by standard InChIKey and keeps only
   binary datasets of components the engine admits (methane, ethane,
   propane);
2. finds pressure datasets (property "...pressure, kPa" or "..., MPa", liquid
   phase) and vapour-composition datasets (property "Mole fraction", gas
   phase), both with temperature (K) and a liquid mole fraction as their
   independent variables, and pairs them by (T, x), never by row order;
3. runs the frozen engine at each state, the same call the validation record
   makes: a bubble pressure from the measured liquid; a dew pressure from the
   measured vapour where one was measured. kij = 0 unless ``--kij`` is given;
4. writes a per-state CSV and a summary Markdown file: AARD, maximum absolute
   error, bias, convergence counts, and the engine's own reason for every
   state that did not converge to a unique pressure.

Datasets in any other layout are listed as skipped, with the reason; nothing
is guessed. A file is evidence only after it was parsed: the summary records
the input's SHA-256 so the comparison can be traced to the exact file.

    uv run python tools/compare_thermoml_vle.py --input record.json --output-dir out
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from io import StringIO
from math import fsum
from pathlib import Path
from typing import Any

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

#: Standard InChIKeys of the components the engine admits.
ADMITTED_BY_INCHIKEY: dict[str, Component] = {
    "VNWKTOKETHGBQD-UHFFFAOYSA-N": METHANE,
    "OTMSDBZUPAUEDD-UHFFFAOYSA-N": ETHANE,
    "ATUOYWHBWRKTHZ-UHFFFAOYSA-N": PROPANE,
}
PRESSURE_UNITS_TO_PA = {"kPa": 1.0e3, "MPa": 1.0e6, "Pa": 1.0, "bar": 1.0e5}
FIELDS = (
    "state_id",
    "components",
    "temperature_k",
    "liquid_mole_fraction_1",
    "vapor_mole_fraction_1",
    "measured_pressure_pa",
    "pressure_expanded_uncertainty_pa",
    "vapor_expanded_uncertainty",
    "kij",
    "bubble_status",
    "bubble_pressure_pa",
    "bubble_percent_error",
    "bubble_incipient_vapor_mole_fraction_1",
    "bubble_failure_reason",
    "bubble_diagnostic_codes",
    "dew_status",
    "dew_pressure_pa",
    "dew_percent_error",
    "dew_failure_reason",
    "dew_diagnostic_codes",
)


class ThermoMLLayoutError(ValueError):
    """The record does not have the layout this tool reads."""


@dataclass(frozen=True, slots=True)
class MeasuredState:
    state_id: str
    components: tuple[Component, Component]
    temperature_k: float
    liquid_mole_fraction_1: float
    vapor_mole_fraction_1: float | None
    pressure_pa: float
    pressure_uncertainty_pa: float | None
    vapor_uncertainty: float | None


def _group_value(container: dict[str, Any]) -> tuple[str, Any]:
    name = next(key for key in container if key != "tml_elements")
    return name, container[name]


def _property(dataset: dict[str, Any]) -> tuple[str, str, int | None]:
    prop = dataset["Property"][0]
    _, details = _group_value(prop["Property-MethodID"]["PropertyGroup"])
    return (
        str(details["ePropName"]),
        str(prop["PropPhaseID"]["ePropPhase"]),
        prop["Property-MethodID"].get("RegNum", {}).get("nOrgNum"),
    )


def _variables(dataset: dict[str, Any]) -> list[tuple[int, str, str, str, int | None]]:
    out = []
    for variable in dataset["Variable"]:
        type_name, label = _group_value(variable["VariableID"]["VariableType"])
        out.append(
            (
                int(variable["nVarNumber"]),
                type_name,
                str(label),
                str(variable["VarPhaseID"]["eVarPhase"]),
                variable["VariableID"].get("RegNum", {}).get("nOrgNum"),
            )
        )
    return out


def _independent(dataset: dict[str, Any]) -> tuple[int, int, int] | None:
    """(temperature variable, composition variable, composition compound)."""

    temperature = composition = compound = None
    for number, type_name, label, phase, org in _variables(dataset):
        if type_name == "eTemperature" and label == "Temperature, K":
            temperature = number
        elif (
            type_name == "eComponentComposition"
            and label == "Mole fraction"
            and phase == "Liquid"
            and org is not None
        ):
            composition, compound = number, int(org)
    if temperature is None or composition is None or compound is None:
        return None
    return temperature, composition, compound


def _rows(
    dataset: dict[str, Any], temperature: int, composition: int
) -> dict[tuple[float, float], tuple[float, float | None]]:
    rows: dict[tuple[float, float], tuple[float, float | None]] = {}
    for row in dataset["NumValues"]:
        values = {
            int(item["nVarNumber"]): float(item["nVarValue"])
            for item in row["VariableValue"]
        }
        key = (values[temperature], values[composition])
        prop = row["PropertyValue"][0]
        uncertainty = prop.get("CombinedUncertainty", {}).get("nCombExpandUncertValue")
        value = (
            float(prop["nPropValue"]),
            None if uncertainty is None else float(uncertainty),
        )
        if key in rows and rows[key] != value:
            raise ThermoMLLayoutError(f"conflicting rows for T, x = {key}")
        rows[key] = value
    return rows


def read_states(document: dict[str, Any]) -> tuple[list[MeasuredState], list[str]]:
    """Paired measured states and the reasons datasets were skipped."""

    compounds = {
        int(item["RegNum"]["nOrgNum"]): ADMITTED_BY_INCHIKEY.get(
            str(item.get("sStandardInChIKey"))
        )
        for item in document["Compound"]
    }
    pressure_sets: dict[tuple[int, int], tuple[dict[str, Any], float]] = {}
    vapour_sets: dict[tuple[int, int], dict[str, Any]] = {}
    skipped: list[str] = []
    for dataset in document["PureOrMixtureData"]:
        number = dataset.get("nPureOrMixtureDataNumber")
        members = sorted(
            int(item["RegNum"]["nOrgNum"]) for item in dataset["Component"]
        )
        if len(members) != 2 or any(
            compounds.get(member) is None for member in members
        ):
            skipped.append(f"dataset {number}: not a binary of admitted components")
            continue
        independent = _independent(dataset)
        if independent is None:
            skipped.append(
                f"dataset {number}: independent variables are not T and liquid x"
            )
            continue
        name, phase, org = _property(dataset)
        pair = (members[0], members[1])
        if "pressure" in name.lower() and phase == "Liquid":
            unit = name.rsplit(", ", 1)[-1]
            if unit not in PRESSURE_UNITS_TO_PA:
                skipped.append(
                    f"dataset {number}: pressure unit {unit!r} not supported"
                )
                continue
            pressure_sets[pair] = (dataset, PRESSURE_UNITS_TO_PA[unit])
        elif name == "Mole fraction" and phase == "Gas" and org is not None:
            vapour_sets[pair] = dataset
        else:
            skipped.append(f"dataset {number}: property {name!r} ({phase}) not used")
    states: list[MeasuredState] = []
    for pair, (dataset, factor) in sorted(pressure_sets.items()):
        t_var, x_var, x_compound = _independent(dataset)  # type: ignore[misc]
        first = x_compound
        second = pair[1] if pair[0] == first else pair[0]
        components = (compounds[first], compounds[second])
        assert components[0] is not None and components[1] is not None
        pressures = _rows(dataset, t_var, x_var)
        vapour: dict[tuple[float, float], tuple[float, float | None]] = {}
        vapour_dataset = vapour_sets.get(pair)
        y_compound = None
        if vapour_dataset is not None:
            vt, vx, vx_compound = _independent(vapour_dataset)  # type: ignore[misc]
            if vx_compound != first:
                raise ThermoMLLayoutError(
                    "vapour and pressure datasets use different x"
                )
            y_compound = int(_property(vapour_dataset)[2])  # type: ignore[arg-type]
            vapour = _rows(vapour_dataset, vt, vx)
        for index, key in enumerate(sorted(pressures), start=1):
            pressure, pressure_u = pressures[key]
            y1: float | None = None
            y_u: float | None = None
            if key in vapour:
                y_value, y_u = vapour[key]
                y1 = y_value if y_compound == first else 1.0 - y_value
            states.append(
                MeasuredState(
                    state_id=f"{components[0].name}-{components[1].name}-{index:03d}".lower(),
                    components=(components[0], components[1]),  # type: ignore[arg-type]
                    temperature_k=key[0],
                    liquid_mole_fraction_1=key[1],
                    vapor_mole_fraction_1=y1,
                    pressure_pa=pressure * factor,
                    pressure_uncertainty_pa=None
                    if pressure_u is None
                    else pressure_u * factor,
                    vapor_uncertainty=y_u,
                )
            )
    return states, skipped


def _interactions(
    state: MeasuredState, kij: float
) -> dict[tuple[str, str], float] | None:
    if kij == 0.0:
        return None
    a, b = (component.name for component in state.components)
    return {(a, b): kij, (b, a): kij}


def _solve(
    state: MeasuredState, first_fraction: float, kind: SaturationKind, kij: float
):  # type: ignore[no-untyped-def]
    mixture = FluidMixture(
        (
            MixtureComponent(state.components[0], first_fraction),
            MixtureComponent(state.components[1], 1.0 - first_fraction),
        )
    )
    return calculate_saturation_pressure(
        mixture,
        state.temperature_k,
        kind,
        binary_interactions=_interactions(state, kij),
    )


def compare_state(state: MeasuredState, kij: float = 0.0) -> dict[str, object]:
    """One per-state row: the engine's bubble (and dew) result at the state."""

    bubble = _solve(
        state, state.liquid_mole_fraction_1, SaturationKind.BUBBLE_POINT, kij
    )
    row: dict[str, object] = {
        "state_id": state.state_id,
        "components": "+".join(component.name for component in state.components),
        "temperature_k": state.temperature_k,
        "liquid_mole_fraction_1": state.liquid_mole_fraction_1,
        "vapor_mole_fraction_1": state.vapor_mole_fraction_1,
        "measured_pressure_pa": state.pressure_pa,
        "pressure_expanded_uncertainty_pa": state.pressure_uncertainty_pa,
        "vapor_expanded_uncertainty": state.vapor_uncertainty,
        "kij": kij,
        "bubble_status": bubble.status.value,
        "bubble_pressure_pa": bubble.pressure_pa,
        "bubble_percent_error": None,
        "bubble_incipient_vapor_mole_fraction_1": None,
        "bubble_failure_reason": bubble.failure_reason,
        "bubble_diagnostic_codes": "|".join(
            sorted({d.code for d in bubble.diagnostics})
        ),
        "dew_status": "not_measured",
        "dew_pressure_pa": None,
        "dew_percent_error": None,
        "dew_failure_reason": None,
        "dew_diagnostic_codes": "",
    }
    if bubble.status is SaturationStatus.CONVERGED and bubble.pressure_pa is not None:
        row["bubble_percent_error"] = (
            100 * (bubble.pressure_pa - state.pressure_pa) / state.pressure_pa
        )
        row["bubble_incipient_vapor_mole_fraction_1"] = bubble.incipient_composition[0]
    if state.vapor_mole_fraction_1 is not None:
        dew = _solve(state, state.vapor_mole_fraction_1, SaturationKind.DEW_POINT, kij)
        row["dew_status"] = dew.status.value
        row["dew_pressure_pa"] = dew.pressure_pa
        row["dew_failure_reason"] = dew.failure_reason
        row["dew_diagnostic_codes"] = "|".join(
            sorted({d.code for d in dew.diagnostics})
        )
        if dew.status is SaturationStatus.CONVERGED and dew.pressure_pa is not None:
            row["dew_percent_error"] = (
                100 * (dew.pressure_pa - state.pressure_pa) / state.pressure_pa
            )
    return row


def summarize(rows: list[dict[str, object]], direction: str) -> dict[str, object]:
    errors = [
        float(str(row[f"{direction}_percent_error"]))
        for row in rows
        if row[f"{direction}_percent_error"] is not None
    ]
    statuses = Counter(str(row[f"{direction}_status"]) for row in rows)
    return {
        "states": sum(
            count for status, count in statuses.items() if status != "not_measured"
        ),
        "statuses": dict(sorted(statuses.items())),
        "converged": len(errors),
        "aard_percent": None
        if not errors
        else fsum(abs(e) for e in errors) / len(errors),
        "maximum_absolute_percent": None if not errors else max(abs(e) for e in errors),
        "bias_percent": None if not errors else fsum(errors) / len(errors),
    }


def rows_to_csv(rows: list[dict[str, object]]) -> str:
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: "" if row[key] is None else row[key] for key in FIELDS})
    return stream.getvalue()


def _number(value: object, digits: int = 3) -> str:
    return "n/a" if value is None else f"{float(str(value)):.{digits}f}"


def summary_markdown(
    rows: list[dict[str, object]], skipped: list[str], source: str, sha256: str
) -> str:
    lines = [
        "# ThermoML VLE comparison with the frozen engine",
        "",
        f"Input: `{source}` (SHA-256 `{sha256}`). Peng–Robinson, classical mixing, "
        f"kij = {rows[0]['kij'] if rows else 0.0}.",
        "",
        "| Direction | States | Converged | AARD (%) | Max abs. error (%) | Bias (%) "
        "| Statuses |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for direction in ("bubble", "dew"):
        s = summarize(rows, direction)
        counts = s["statuses"]
        assert isinstance(counts, dict)
        statuses = ", ".join(f"{k}: {v}" for k, v in counts.items())
        lines.append(
            f"| {direction} | {s['states']} | {s['converged']} | "
            f"{_number(s['aard_percent'])} | "
            f"{_number(s['maximum_absolute_percent'])} | "
            f"{_number(s['bias_percent'])} | {statuses} |"
        )
    lines += [
        "",
        "## States without a unique converged pressure (engine's own reason)",
        "",
    ]
    failures = [
        f"- {row['state_id']} {direction}: {row[f'{direction}_status']}: "
        f"{row[f'{direction}_failure_reason']} [{row[f'{direction}_diagnostic_codes']}]"
        for row in rows
        for direction in ("bubble", "dew")
        if row[f"{direction}_status"] not in ("converged", "not_measured")
    ]
    lines += failures or ["- none"]
    lines += ["", "## Skipped datasets", ""] + (
        [f"- {item}" for item in skipped] or ["- none"]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, required=True, help="ThermoML JSON file")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--kij", type=float, default=0.0)
    arguments = parser.parse_args()
    raw = arguments.input.read_bytes()
    states, skipped = read_states(json.loads(raw.decode("utf-8")))
    if not states:
        print("No usable binary VLE states of admitted components were found.")
        for item in skipped:
            print(f"  skipped {item}")
        return 1
    rows = [compare_state(state, arguments.kij) for state in states]
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    stem = arguments.input.stem
    (arguments.output_dir / f"{stem}_comparison.csv").write_text(
        rows_to_csv(rows), encoding="utf-8", newline=""
    )
    summary = summary_markdown(
        rows, skipped, arguments.input.name, hashlib.sha256(raw).hexdigest().upper()
    )
    (arguments.output_dir / f"{stem}_summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["MeasuredState", "asdict", "compare_state", "read_states", "summarize"]
