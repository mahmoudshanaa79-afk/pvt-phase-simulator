"""tools/compare_thermoml_vle.py reproduces the validation record.

TEST FIXTURE, NOT A NEW SOURCE: the ThermoML-shaped document below is built at
test time from rows of the committed May et al. (2015) data file. It only
exercises the parser and the engine calls. The test shows the tool gives the
same statuses and pressures as the protected Module 17 record for those
states.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from tools import compare_thermoml_vle as tool

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/experimental/may_2015_ch4_c2_ch4_c3_vle.csv"
RECORD = ROOT / "docs/validation/module17_vle_validation.csv"
#: A mix of outcomes: converged bubbles, unique and ambiguous dews.
STATES = (
    "may2015_ch4_c3_009",
    "may2015_ch4_c3_010",
    "may2015_ch4_c3_012",
    "may2015_ch4_c3_014",
    "may2015_ch4_c3_020",
)
INCHIKEY = {
    "methane": "VNWKTOKETHGBQD-UHFFFAOYSA-N",
    "propane": "ATUOYWHBWRKTHZ-UHFFFAOYSA-N",
}


def _csv(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return {row["source_point_id"]: row for row in csv.DictReader(stream)}


def _variables() -> list[dict[str, Any]]:
    return [
        {
            "nVarNumber": 1,
            "VariableID": {"VariableType": {"eTemperature": "Temperature, K"}},
            "VarPhaseID": {"eVarPhase": "Liquid"},
        },
        {
            "nVarNumber": 2,
            "VariableID": {
                "VariableType": {"eComponentComposition": "Mole fraction"},
                "RegNum": {"nOrgNum": 1},
            },
            "VarPhaseID": {"eVarPhase": "Liquid"},
        },
    ]


def _row(temperature: str, x: str, value: str, uncertainty: str) -> dict[str, Any]:
    return {
        "VariableValue": [
            {"nVarNumber": 1, "nVarValue": temperature},
            {"nVarNumber": 2, "nVarValue": x},
        ],
        "PropertyValue": [
            {
                "nPropValue": value,
                "CombinedUncertainty": {"nCombExpandUncertValue": uncertainty},
            }
        ],
    }


def fixture_document(ids: tuple[str, ...] = STATES) -> dict[str, Any]:
    rows = [_csv(SOURCE)[item] for item in ids]
    components = [{"RegNum": {"nOrgNum": 1}}, {"RegNum": {"nOrgNum": 3}}]
    return {
        "Citation": {"sTitle": "TEST FIXTURE built from committed May (2015) rows"},
        "Compound": [
            {"RegNum": {"nOrgNum": 1}, "sStandardInChIKey": INCHIKEY["methane"]},
            {"RegNum": {"nOrgNum": 3}, "sStandardInChIKey": INCHIKEY["propane"]},
            {
                "RegNum": {"nOrgNum": 9},
                "sStandardInChIKey": "NOT-AN-ADMITTED-COMPONENT",
            },
        ],
        "PureOrMixtureData": [
            {
                "nPureOrMixtureDataNumber": 1,
                "Component": components,
                "Property": [
                    {
                        "Property-MethodID": {
                            "PropertyGroup": {
                                "VaporPBoilingTAzeotropTandP": {
                                    "ePropName": "Vapor or sublimation pressure, kPa"
                                }
                            }
                        },
                        "PropPhaseID": {"ePropPhase": "Liquid"},
                    }
                ],
                "Variable": _variables(),
                "NumValues": [
                    _row(
                        r["temperature_k"],
                        r["liquid_methane_mole_fraction"],
                        r["pressure_kpa"],
                        r["pressure_expanded_uncertainty_kpa"],
                    )
                    for r in rows
                ],
            },
            {
                "nPureOrMixtureDataNumber": 2,
                "Component": components,
                "Property": [
                    {
                        "Property-MethodID": {
                            "PropertyGroup": {
                                "CompositionAtPhaseEquilibrium": {
                                    "ePropName": "Mole fraction"
                                }
                            },
                            "RegNum": {"nOrgNum": 3},
                        },
                        "PropPhaseID": {"ePropPhase": "Gas"},
                    }
                ],
                "Variable": _variables(),
                "NumValues": [
                    _row(
                        r["temperature_k"],
                        r["liquid_methane_mole_fraction"],
                        r["vapor_heavy_mole_fraction"],
                        r["vapor_heavy_expanded_uncertainty"],
                    )
                    for r in rows
                ],
            },
            {
                "nPureOrMixtureDataNumber": 3,
                "Component": [{"RegNum": {"nOrgNum": 1}}, {"RegNum": {"nOrgNum": 9}}],
                "Property": [],
                "Variable": [],
                "NumValues": [],
            },
        ],
    }


def _close(a: float, b: float) -> bool:
    # The record was generated on another machine; the last bits of a float can
    # differ between machines (docs/investigations/butanes_admission_dry_run.md).
    return abs(a - b) <= 1e-9 * abs(b)


def test_the_fixture_parses_into_paired_states() -> None:
    states, skipped = tool.read_states(fixture_document())
    assert len(states) == len(STATES)
    assert skipped == ["dataset 3: not a binary of admitted components"]
    source = _csv(SOURCE)
    for state in states:
        assert [c.name for c in state.components] == ["Methane", "Propane"]
        match = next(
            row
            for row in (source[item] for item in STATES)
            if float(row["temperature_k"]) == state.temperature_k
            and float(row["liquid_methane_mole_fraction"])
            == state.liquid_mole_fraction_1
        )
        assert state.pressure_pa == float(match["pressure_pa"])
        assert state.vapor_mole_fraction_1 == float(
            match["vapor_methane_mole_fraction"]
        )
        assert state.pressure_uncertainty_pa == float(
            match["pressure_expanded_uncertainty_pa"]
        )


@pytest.mark.parametrize("point", STATES)
def test_the_tool_reproduces_the_validation_record(point: str) -> None:
    states, _ = tool.read_states(fixture_document((point,)))
    (state,) = states
    row = tool.compare_state(state)
    recorded = _csv(RECORD)[point]
    for direction in ("bubble", "dew"):
        assert row[f"{direction}_status"] == recorded[f"{direction}_status"], direction
        expected = recorded[f"{direction}_predicted_pressure_pa"]
        if expected:
            assert _close(float(str(row[f"{direction}_pressure_pa"])), float(expected))
            assert _close(
                float(str(row[f"{direction}_percent_error"])),
                float(recorded[f"{direction}_pressure_percent_error"]),
            )
        else:
            assert row[f"{direction}_pressure_pa"] is None
            assert (
                row[f"{direction}_failure_reason"]
                == recorded[f"{direction}_failure_reason"]
            )
        codes = "|".join(json.loads(recorded[f"{direction}_diagnostic_codes"]))
        assert row[f"{direction}_diagnostic_codes"] == codes


def test_the_summary_reports_every_failure_with_the_engine_reason(
    tmp_path: Path,
) -> None:
    states, skipped = tool.read_states(fixture_document())
    rows = [tool.compare_state(state) for state in states]
    text = tool.summary_markdown(rows, skipped, "fixture.json", "0" * 64)
    record = _csv(RECORD)
    for point in STATES:
        recorded = record[point]
        if recorded["dew_status"] != "converged":
            assert recorded["dew_failure_reason"] in text
    bubble = tool.summarize(rows, "bubble")
    errors = [abs(float(record[p]["bubble_pressure_percent_error"])) for p in STATES]
    assert bubble["converged"] == len(STATES)
    assert abs(float(str(bubble["aard_percent"])) - sum(errors) / len(errors)) < 1e-9
    csv_text = tool.rows_to_csv(rows)
    assert len(list(csv.DictReader(csv_text.splitlines()))) == len(STATES)
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(fixture_document()), encoding="utf-8")


def test_a_kij_changes_the_result_and_is_recorded() -> None:
    states, _ = tool.read_states(fixture_document(("may2015_ch4_c3_010",)))
    zero = tool.compare_state(states[0])
    fitted = tool.compare_state(states[0], kij=0.0021)
    assert fitted["kij"] == 0.0021
    assert float(str(fitted["bubble_pressure_pa"])) > float(
        str(zero["bubble_pressure_pa"])
    )
