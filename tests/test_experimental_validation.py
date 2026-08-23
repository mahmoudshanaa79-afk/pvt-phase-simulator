"""Tests for the offline Module 17 experimental-validation infrastructure."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from io import StringIO
from math import fsum, sqrt
from pathlib import Path
from typing import Any

import pytest

from pvt_phase_simulator.experimental_validation import (
    NORMALIZED_FIELDS,
    RESULT_FIELDS,
    ExperimentalVLEDataset,
    load_experimental_vle_dataset,
    validate_experimental_dataset,
    validation_results_to_csv,
)
from tools import extract_may_2015_thermoml as extractor

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data/experimental/may_2015_ch4_c2_ch4_c3_vle.csv"
MANIFEST_PATH = ROOT / "data/experimental/may_2015_source_manifest.json"
RESULT_PATH = ROOT / "docs/validation/module17_vle_validation.csv"
SUMMARY_PATH = ROOT / "docs/validation/module17_vle_validation_summary.json"


def _dataset() -> ExperimentalVLEDataset:
    return load_experimental_vle_dataset(DATA_PATH, MANIFEST_PATH)


def _result_rows() -> list[dict[str, str]]:
    with RESULT_PATH.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _mutated_source(
    tmp_path: Path, mutation: Callable[[list[dict[str, str]]], None]
) -> tuple[Path, Path]:
    with DATA_PATH.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    mutation(rows)
    csv_stream = StringIO(newline="")
    writer = csv.DictWriter(
        csv_stream, fieldnames=NORMALIZED_FIELDS, lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    data = csv_stream.getvalue().encode()
    csv_path = tmp_path / "data.csv"
    csv_path.write_bytes(data)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["normalized_csv_sha256"] = hashlib.sha256(data).hexdigest().upper()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return csv_path, manifest_path


def test_source_provenance_normalization_and_immutability() -> None:
    dataset = _dataset()
    assert dataset.source.doi == "10.1021/acs.jced.5b00610"
    assert dataset.source.archive_name == "NIST ThermoML"
    assert dataset.source.raw_json_sha256
    assert (
        dataset.source.normalized_csv_sha256
        == hashlib.sha256(DATA_PATH.read_bytes()).hexdigest().upper()
    )
    assert len(dataset.points) == 40
    assert sum(point.system_id == "ch4_c2" for point in dataset.points) == 17
    assert sum(point.system_id == "ch4_c3" for point in dataset.points) == 23
    assert len({point.source_point_id for point in dataset.points}) == 40
    for point in dataset.points:
        assert point.pressure_pa == point.pressure_kpa * 1000.0
        assert fsum(point.liquid_mole_fractions) == pytest.approx(1.0, abs=1e-12)
        assert fsum(point.vapor_mole_fractions) == pytest.approx(1.0, abs=1e-12)
        assert all(0.0 <= value <= 1.0 for value in point.liquid_mole_fractions)
        assert all(0.0 <= value <= 1.0 for value in point.vapor_mole_fractions)
    with pytest.raises(FrozenInstanceError):
        dataset.points[0].pressure_pa = 1.0  # type: ignore[misc]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda rows: rows[0].update(temperature_unit="degC"), "unit must be K"),
        (
            lambda rows: rows[0].update(
                liquid_methane_mole_fraction=rows[0]["vapor_methane_mole_fraction"],
                liquid_heavy_mole_fraction=rows[0]["vapor_heavy_mole_fraction"],
                vapor_methane_mole_fraction=rows[0]["liquid_methane_mole_fraction"],
                vapor_heavy_mole_fraction=rows[0]["liquid_heavy_mole_fraction"],
            ),
            "may be swapped",
        ),
        (
            lambda rows: rows[1].update(source_point_id=rows[0]["source_point_id"]),
            "duplicate experimental source point ID",
        ),
        (lambda rows: rows[0].update(pressure_kpa=""), "must not be missing"),
        (
            lambda rows: rows[0].update(
                liquid_methane_mole_fraction="1.1",
                liquid_heavy_mole_fraction="-0.1",
            ),
            "mole fractions must be in",
        ),
        (
            lambda rows: rows[0].update(component_2_id="propane"),
            "incorrect component mapping",
        ),
    ],
)
def test_corrupt_normalized_data_are_rejected(
    tmp_path: Path,
    mutation: Callable[[list[dict[str, str]]], None],
    message: str,
) -> None:
    csv_path, manifest_path = _mutated_source(tmp_path, mutation)
    with pytest.raises(ValueError, match=message):
        load_experimental_vle_dataset(csv_path, manifest_path)


def _variable(number: int, kind: str, value: str, phase: str, compound: int | None):
    regnum = {} if compound is None else {"RegNum": {"nOrgNum": compound}}
    return {
        "nVarNumber": number,
        "VariableID": {"VariableType": {kind: value}, **regnum},
        "VarPhaseID": {"eVarPhase": phase},
    }


def _source_dataset(
    number: int,
    heavy_number: int,
    values: list[tuple[float, float, float, float]],
    *,
    pressure: bool,
) -> dict[str, Any]:
    property_details = (
        {
            "ePropName": "Vapor or sublimation pressure, kPa",
            "sMethodName": "Closed cell (Static) method",
        }
        if pressure
        else {"ePropName": "Mole fraction", "sMethodName": "Chromatography"}
    )
    property_regnum = {} if pressure else {"RegNum": {"nOrgNum": heavy_number}}
    return {
        "nPureOrMixtureDataNumber": number,
        "Component": [
            {"RegNum": {"nOrgNum": 1}},
            {"RegNum": {"nOrgNum": heavy_number}},
        ],
        "Variable": [
            _variable(1, "eTemperature", "Temperature, K", "Liquid", None),
            _variable(2, "eComponentComposition", "Mole fraction", "Liquid", 1),
        ],
        "Property": [
            {
                "Property-MethodID": {
                    "PropertyGroup": {"VaporPBoilingTA": property_details},
                    **property_regnum,
                },
                "PropPhaseID": {"ePropPhase": "Liquid" if pressure else "Gas"},
            }
        ],
        "NumValues": [
            {
                "VariableValue": [
                    {"nVarNumber": 1, "nVarValue": temperature},
                    {"nVarNumber": 2, "nVarValue": liquid_methane},
                ],
                "PropertyValue": [
                    {
                        "nPropValue": measured,
                        "CombinedUncertainty": {"nCombExpandUncertValue": uncertainty},
                    }
                ],
            }
            for temperature, liquid_methane, measured, uncertainty in values
        ],
    }


def _thermoml_fixture(vapor_values: list[tuple[float, float, float, float]]):
    compounds = [
        (1, "methane", "VNWKTOKETHGBQD-UHFFFAOYSA-N"),
        (2, "ethane", "OTMSDBZUPAUEDD-UHFFFAOYSA-N"),
        (3, "propane", "ATUOYWHBWRKTHZ-UHFFFAOYSA-N"),
    ]
    pressure_values = [(210.0, 0.2, 1000.0, 1.0), (220.0, 0.4, 2000.0, 2.0)]
    return {
        "Citation": {
            "sDOI": extractor.EXPECTED_DOI,
            "sTitle": extractor.EXPECTED_TITLE,
            "sAuthor": list(extractor.EXPECTED_AUTHORS),
        },
        "Compound": [
            {
                "RegNum": {"nOrgNum": number},
                "sCommonName": [name],
                "sStandardInChIKey": key,
            }
            for number, name, key in compounds
        ],
        "PureOrMixtureData": [
            _source_dataset(1, 2, pressure_values, pressure=True),
            _source_dataset(2, 2, vapor_values, pressure=False),
        ],
    }


def test_extractor_pairs_by_independent_variables_not_array_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        extractor, "SELECTED_SYSTEMS", (("ch4_c2", "ethane", 1, 2, 1, 2, 2),)
    )
    reversed_vapor = [(220.0, 0.4, 0.1, 0.001), (210.0, 0.2, 0.05, 0.002)]
    rows = extractor.extract_normalized_rows(_thermoml_fixture(reversed_vapor))
    assert [row["pressure_source_row"] for row in rows] == ["1", "2"]
    assert [row["vapor_source_row"] for row in rows] == ["2", "1"]
    assert [row["vapor_heavy_mole_fraction"] for row in rows] == ["0.05", "0.1"]


def test_extractor_rejects_ambiguous_and_unpairable_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        extractor, "SELECTED_SYSTEMS", (("ch4_c2", "ethane", 1, 2, 1, 2, 2),)
    )
    duplicate = [(210.0, 0.2, 0.05, 0.002), (210.0, 0.2, 0.06, 0.002)]
    with pytest.raises(ValueError, match="duplicate.*pairing key"):
        extractor.extract_normalized_rows(_thermoml_fixture(duplicate))
    unpairable = [(210.0, 0.2, 0.05, 0.002), (230.0, 0.4, 0.1, 0.001)]
    with pytest.raises(ValueError, match="unpairable"):
        extractor.extract_normalized_rows(_thermoml_fixture(unpairable))


def test_result_artifact_accounts_for_every_point_and_metrics_are_reproducible():
    dataset = _dataset()
    with RESULT_PATH.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        assert tuple(reader.fieldnames or ()) == RESULT_FIELDS
        rows = list(reader)
    assert len(rows) == len(dataset.points)
    assert {row["source_point_id"] for row in rows} == {
        point.source_point_id for point in dataset.points
    }
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    for system_summary in summary["systems"]:
        system_rows = [
            row for row in rows if row["system_id"] == system_summary["system_id"]
        ]
        for direction in ("bubble", "dew"):
            successful = [
                row for row in system_rows if row[f"{direction}_status"] == "converged"
            ]
            relative_errors = [
                float(row[f"{direction}_pressure_relative_error"]) for row in successful
            ]
            metrics = system_summary[f"production_selected_{direction}_metrics"]
            assert metrics["source_count"] == len(system_rows)
            assert metrics["success_count"] == len(successful)
            assert metrics["failure_count"] == len(system_rows) - len(successful)
            assert metrics["pressure_aard_percent"] == pytest.approx(
                100.0 * fsum(map(abs, relative_errors)) / len(relative_errors)
            )
            assert metrics["pressure_rms_relative_percent"] == pytest.approx(
                100.0
                * sqrt(
                    fsum(value * value for value in relative_errors)
                    / len(relative_errors)
                )
            )


def test_one_point_production_validation_and_serialization_are_deterministic():
    dataset = _dataset()
    audit_point = next(
        point
        for point in dataset.points
        if point.source_point_id == "may2015_ch4_c3_015"
    )
    one_point = ExperimentalVLEDataset(dataset.source, (audit_point,))
    first = validate_experimental_dataset(one_point)
    second = validate_experimental_dataset(one_point)
    assert first == second
    assert validation_results_to_csv(first) == validation_results_to_csv(second)
    result = first[0]
    assert result.dew.predicted_pressure_pa == pytest.approx(2_550_204.2506093)
    assert result.dew_branch_diagnostic.production_selected_root_class == "LOWER"
    assert len(result.dew_branch_diagnostic.roots) == 2
    assert result.dew_branch_diagnostic.roots[-1].pressure_pa == pytest.approx(
        8_158_606.566932067
    )
    assert (
        result.dew.predicted_pressure_pa
        != result.dew_branch_diagnostic.nearest_pr_root_to_experiment_pressure_pa
    )


def test_branch_artifact_reproduces_root_and_failure_accounting() -> None:
    rows = _result_rows()
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    by_system = {item["system_id"]: item for item in summary["systems"]}
    c2 = by_system["ch4_c2"]["dew_branch_diagnostics"]
    c3 = by_system["ch4_c3"]["dew_branch_diagnostics"]
    assert (c2["zero_root_state_count"], c2["single_root_state_count"]) == (0, 13)
    assert c2["multiple_root_state_count"] == 4
    assert (c3["zero_root_state_count"], c3["single_root_state_count"]) == (2, 1)
    assert c3["multiple_root_state_count"] == 20
    assert c2["failed_root_demonstrated_count"] == 2
    assert c2["failed_no_root_found_in_scan_count"] == 0
    assert c3["failed_root_demonstrated_count"] == 14
    assert c3["failed_no_root_found_in_scan_count"] == 2
    no_root_ids = {
        row["source_point_id"]
        for row in rows
        if row["dew_failure_classification"] == "NO_PR_ROOT_FOUND_IN_DIAGNOSTIC_SCAN"
    }
    assert no_root_ids == {"may2015_ch4_c3_020", "may2015_ch4_c3_021"}
    c2_failed = [
        row
        for row in rows
        if row["system_id"] == "ch4_c2" and row["dew_status"] != "converged"
    ]
    assert len(c2_failed) == 2
    assert {row["dew_failure_classification"] for row in c2_failed} == {
        "PR_ROOT_DEMONSTRATED_PRODUCTION_UNREACHED"
    }


def test_production_and_nearest_branch_metrics_remain_separate() -> None:
    rows = _result_rows()
    audit = {
        row["source_point_id"]: row
        for row in rows
        if row["source_point_id"]
        in {
            "may2015_ch4_c3_014",
            "may2015_ch4_c3_015",
            "may2015_ch4_c3_023",
        }
    }
    expected = {
        "may2015_ch4_c3_014": (2_930_670.1363515155, 7_773_260.512799223),
        "may2015_ch4_c3_015": (2_550_204.2506093043, 8_158_606.566932067),
        "may2015_ch4_c3_023": (5_840_051.393478824, 7_701_834.625901307),
    }
    for point_id, (production_pressure, nearest_pressure) in expected.items():
        row = audit[point_id]
        assert float(row["dew_predicted_pressure_pa"]) == pytest.approx(
            production_pressure
        )
        assert row["dew_production_selected_root_class"] == "LOWER"
        assert float(row["dew_nearest_experimental_root_pressure_pa"]) == pytest.approx(
            nearest_pressure
        )
        assert row["dew_nearest_experimental_root_class"] == "UPPER"
        assert (
            row["dew_predicted_pressure_pa"]
            != row["dew_nearest_experimental_root_pressure_pa"]
        )


def test_highest_root_is_not_a_universal_selection_rule() -> None:
    rows = {row["source_point_id"]: row for row in _result_rows()}
    point_001 = rows["may2015_ch4_c3_001"]
    point_003 = rows["may2015_ch4_c3_003"]
    assert point_001["dew_nearest_experimental_root_class"] == "LOWER"
    assert point_003["dew_nearest_experimental_root_class"] == "UPPER"
    roots_001 = json.loads(point_001["dew_diagnostic_root_pressures_pa"])
    assert len(roots_001) == 2
    assert float(
        point_001["dew_nearest_experimental_root_pressure_pa"]
    ) == pytest.approx(roots_001[0])
    assert float(
        point_001["dew_nearest_experimental_root_pressure_pa"]
    ) != pytest.approx(roots_001[-1])


def test_failed_states_never_enter_production_metric_denominators() -> None:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    for system in summary["systems"]:
        metrics = system["production_selected_dew_metrics"]
        diagnostics = system["dew_branch_diagnostics"]
        assert metrics["source_count"] == (
            metrics["success_count"] + metrics["failure_count"]
        )
        assert diagnostics["production_success_count"] == metrics["success_count"]
        assert diagnostics["production_failure_count"] == metrics["failure_count"]
        assert (
            metrics["pressure_uncertainty_available_count"] == metrics["success_count"]
        )


def test_out_of_title_points_and_283_38_k_sensitivity_are_pinned() -> None:
    dataset = _dataset()
    c3_temperatures = {
        point.temperature_k for point in dataset.points if point.system_id == "ch4_c3"
    }
    assert {273.48, 283.38} <= c3_temperatures
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    sensitivity = summary["source_anomaly_sensitivity_283_38_k"]
    bubble = sensitivity["bubble"]
    dew = sensitivity["dew"]
    assert (bubble["included_success_count"], bubble["excluded_success_count"]) == (
        20,
        19,
    )
    assert bubble["included_aard_percent"] == pytest.approx(1.0338049113443992)
    assert bubble["excluded_aard_percent"] == pytest.approx(0.9807666332366116)
    assert bubble["aard_shift_when_excluded_percentage_points"] == pytest.approx(
        -0.053038278107787606
    )
    assert (dew["included_success_count"], dew["excluded_success_count"]) == (7, 6)
    assert dew["included_aard_percent"] == pytest.approx(36.668237970426496)
    assert dew["excluded_aard_percent"] == pytest.approx(38.86971885863611)
    assert dew["aard_shift_when_excluded_percentage_points"] == pytest.approx(
        2.201480888209616
    )
