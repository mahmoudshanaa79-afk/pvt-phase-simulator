"""Scientific-equivalence tests for the read-only Module 17 adapter."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import cast

from pvt_phase_simulator_validation import (
    LEGACY_SOLVER_OUTCOME_KEY,
    RETROSPECTIVE_DIAGNOSTIC_KIND,
    CapabilityUnderTest,
    DataClass,
    FrozenJsonObject,
    PredictionOutcome,
    ValidationQuantity,
    ValidationStatus,
    decode_reference_dataset,
    decode_validation_record,
    encode_reference_dataset,
    encode_validation_record,
    load_module17_validation_evidence,
)
from pvt_phase_simulator_validation.models import PredictionValue, ReferenceValue

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "data/experimental/may_2015_ch4_c2_ch4_c3_vle.csv"
MANIFEST_PATH = ROOT / "data/experimental/may_2015_source_manifest.json"
LEGACY_PATH = ROOT / "docs/validation/module17_vle_validation.csv"
SUMMARY_PATH = ROOT / "docs/validation/module17_vle_validation_summary.json"


def _csv_rows(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    return {row["source_point_id"]: row for row in rows}


def _json_vector(text: str) -> tuple[float, ...]:
    raw: object = json.loads(text)
    assert isinstance(raw, list)
    assert all(
        not isinstance(item, bool) and isinstance(item, (int, float)) for item in raw
    )
    return tuple(float(cast(int | float, item)) for item in raw)


def _optional_float(text: str) -> float | None:
    return None if text == "" else float(text)


def _optional_bool(text: str) -> bool | None:
    if text == "":
        return None
    assert text in {"true", "false"}
    return text == "true"


def _frozen_json_array(text: str) -> tuple[object, ...]:
    def freeze(value: object) -> object:
        if isinstance(value, list):
            return tuple(freeze(item) for item in value)
        return value

    raw: object = json.loads(text)
    assert isinstance(raw, list)
    return cast(tuple[object, ...], freeze(raw))


def _value(
    values: tuple[ReferenceValue, ...] | tuple[PredictionValue, ...],
    quantity: ValidationQuantity,
) -> float | tuple[float, ...]:
    matches = [item.value for item in values if item.quantity is quantity]
    assert len(matches) == 1
    return matches[0]


def _source_point_id(source_reference: str) -> str:
    raw: object = json.loads(source_reference)
    assert isinstance(raw, dict)
    value = raw["source_point_id"]
    assert isinstance(value, str)
    return value


def _records_by_capability():
    adapted = load_module17_validation_evidence(ROOT)
    identities = {dataset.identity: dataset.capability for dataset in adapted.datasets}
    result = {
        capability: {
            _source_point_id(record.case.source_reference): record
            for record in adapted.records
            if identities[record.identity] is capability
        }
        for capability in CapabilityUnderTest
        if capability in identities.values()
    }
    return adapted, result


def test_adapter_emits_two_complete_experimental_datasets_and_all_records() -> None:
    adapted, records = _records_by_capability()
    assert tuple(dataset.capability for dataset in adapted.datasets) == (
        CapabilityUnderTest.BUBBLE_POINT,
        CapabilityUnderTest.DEW_POINT,
    )
    assert len(adapted.records) == 80
    assert set(records) == {
        CapabilityUnderTest.BUBBLE_POINT,
        CapabilityUnderTest.DEW_POINT,
    }
    for dataset in adapted.datasets:
        assert dataset.data_class is DataClass.EXPERIMENTAL_VALIDATION
        assert dataset.source_manifest.data_class is DataClass.EXPERIMENTAL_VALIDATION
        assert len(dataset.cases) == 40
        assert sum(case.system_id == "ch4_c2" for case in dataset.cases) == 17
        assert sum(case.system_id == "ch4_c3" for case in dataset.cases) == 23
        assert len({case.case_id for case in dataset.cases}) == 40
    assert len(records[CapabilityUnderTest.BUBBLE_POINT]) == 40
    assert len(records[CapabilityUnderTest.DEW_POINT]) == 40
    assert all(
        record.status is not ValidationStatus.EXCLUDED
        and record.exclusion_reason is None
        for record in adapted.records
    )


def test_legacy_solver_coverage_and_outcomes_are_preserved_structurally() -> None:
    _, records = _records_by_capability()
    bubble = tuple(records[CapabilityUnderTest.BUBBLE_POINT].values())
    dew = tuple(records[CapabilityUnderTest.DEW_POINT].values())

    assert len(bubble) == 40
    assert Counter(
        record.prediction.solver_metadata[LEGACY_SOLVER_OUTCOME_KEY]
        for record in bubble
    ) == {"converged": 31, "not_found": 9}
    assert len(dew) == 40
    assert Counter(
        record.prediction.solver_metadata[LEGACY_SOLVER_OUTCOME_KEY] for record in dew
    ) == {"converged": 22, "not_found": 4, "inconclusive": 14}

    for record in (*bubble, *dew):
        legacy_outcome = record.prediction.solver_metadata[LEGACY_SOLVER_OUTCOME_KEY]
        if legacy_outcome == "converged":
            assert record.prediction.outcome is PredictionOutcome.VALUE
            assert record.status is ValidationStatus.REPORTED_NO_TOLERANCE
        else:
            assert record.prediction.outcome is PredictionOutcome.FAILURE
            assert record.status is ValidationStatus.SOLVER_FAILURE
            assert not record.prediction.values


def test_solver_metadata_and_retrospective_diagnostics_map_every_legacy_field() -> None:
    legacy_rows = _csv_rows(LEGACY_PATH)
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    _, records = _records_by_capability()
    retrospective_fields = (
        "dew_branch_scan_pressure_bounds_pa",
        "dew_branch_scan_pressure_step_pa",
        "dew_diagnostic_root_count",
        "dew_diagnostic_root_pressures_pa",
        "dew_diagnostic_root_brackets_pa",
        "dew_lowest_root_pressure_pa",
        "dew_highest_root_pressure_pa",
        "dew_multiple_roots_detected",
        "dew_production_selected_root_class",
        "dew_nearest_experimental_root_pressure_pa",
        "dew_nearest_experimental_root_class",
        "dew_nearest_experimental_root_relative_error",
        "dew_failure_classification",
        "experimental_state_log_fugacity_ratio_residuals",
        "experimental_state_maximum_absolute_fugacity_residual",
        "experimental_state_liquid_root",
        "experimental_state_vapor_root",
    )
    json_fields = {
        "dew_branch_scan_pressure_bounds_pa",
        "dew_diagnostic_root_pressures_pa",
        "dew_diagnostic_root_brackets_pa",
        "experimental_state_log_fugacity_ratio_residuals",
    }
    text_fields = {
        "dew_production_selected_root_class",
        "dew_nearest_experimental_root_class",
        "dew_failure_classification",
    }

    for capability, capability_records in records.items():
        direction = (
            "bubble" if capability is CapabilityUnderTest.BUBBLE_POINT else "dew"
        )
        for source_point_id, record in capability_records.items():
            legacy = legacy_rows[source_point_id]
            prefix = f"{direction}_"
            assert dict(record.prediction.solver_metadata) == {
                "diagnostic_codes": _frozen_json_array(
                    legacy[f"{prefix}diagnostic_codes"]
                ),
                "inner_iteration_count": int(legacy[f"{prefix}inner_iteration_count"]),
                LEGACY_SOLVER_OUTCOME_KEY: legacy[f"{prefix}status"],
                "maximum_fugacity_equilibrium_residual": _optional_float(
                    legacy[f"{prefix}maximum_fugacity_equilibrium_residual"]
                ),
                "phase_root_ordering_consistent": _optional_bool(
                    legacy[f"{prefix}phase_root_ordering_consistent"]
                ),
                "pressure_solver_iterations": int(
                    legacy[f"{prefix}pressure_solver_iterations"]
                ),
                "selected_incipient_root": _optional_float(
                    legacy[f"{prefix}selected_incipient_root"]
                ),
                "selected_parent_root": _optional_float(
                    legacy[f"{prefix}selected_parent_root"]
                ),
            }
            if direction == "bubble":
                assert not record.prediction.diagnostics
                continue

            assert len(record.prediction.diagnostics) == 1
            diagnostic = record.prediction.diagnostics[0]
            assert isinstance(diagnostic, FrozenJsonObject)
            assert diagnostic["kind"] == RETROSPECTIVE_DIAGNOSTIC_KIND
            assert (
                diagnostic["interpretation"]
                == summary["interpretation"]["dew_branch_diagnostics"]
            )
            values = diagnostic["values"]
            assert isinstance(values, FrozenJsonObject)
            assert set(values) == set(retrospective_fields)
            for field in retrospective_fields:
                if field in json_fields:
                    expected: object = _frozen_json_array(legacy[field])
                elif field == "dew_diagnostic_root_count":
                    expected = int(legacy[field]) if legacy[field] else None
                elif field == "dew_multiple_roots_detected":
                    expected = _optional_bool(legacy[field])
                elif field in text_fields:
                    expected = legacy[field] or None
                else:
                    expected = _optional_float(legacy[field])
                assert values[field] == expected


def test_cases_and_predictions_are_exact_float_mappings_of_legacy_evidence() -> None:
    source_rows = _csv_rows(SOURCE_PATH)
    legacy_rows = _csv_rows(LEGACY_PATH)
    _, records = _records_by_capability()

    for capability, capability_records in records.items():
        direction = (
            "bubble" if capability is CapabilityUnderTest.BUBBLE_POINT else "dew"
        )
        for source_point_id, record in capability_records.items():
            source = source_rows[source_point_id]
            legacy = legacy_rows[source_point_id]
            case = record.case
            assert case.system_id == source["system_id"]
            assert case.component_ids == (
                source["component_1_id"],
                source["component_2_id"],
            )
            assert _value(
                case.specified_conditions, ValidationQuantity.TEMPERATURE
            ) == float(source["temperature_k"])
            assert _value(case.reference_values, ValidationQuantity.PRESSURE) == float(
                source["pressure_pa"]
            )

            specified = _value(
                case.specified_conditions, ValidationQuantity.MOLE_FRACTION
            )
            opposite = _value(case.reference_values, ValidationQuantity.MOLE_FRACTION)
            liquid = (
                float(source["liquid_methane_mole_fraction"]),
                float(source["liquid_heavy_mole_fraction"]),
            )
            vapor = (
                float(source["vapor_methane_mole_fraction"]),
                float(source["vapor_heavy_mole_fraction"]),
            )
            assert (specified, opposite) == (
                (liquid, vapor) if direction == "bubble" else (vapor, liquid)
            )

            if legacy[f"{direction}_status"] != "converged":
                assert not record.prediction.values
                continue
            predicted_pressure = cast(
                float,
                _value(record.prediction.values, ValidationQuantity.PRESSURE),
            )
            predicted_composition = cast(
                tuple[float, ...],
                _value(record.prediction.values, ValidationQuantity.MOLE_FRACTION),
            )
            expected_composition_field = (
                "bubble_predicted_vapor_composition"
                if direction == "bubble"
                else "dew_predicted_liquid_composition"
            )
            assert predicted_pressure == float(
                legacy[f"{direction}_predicted_pressure_pa"]
            )
            assert predicted_composition == _json_vector(
                legacy[expected_composition_field]
            )

            reference_pressure = cast(
                float, _value(case.reference_values, ValidationQuantity.PRESSURE)
            )
            reference_composition = cast(
                tuple[float, ...],
                _value(case.reference_values, ValidationQuantity.MOLE_FRACTION),
            )
            assert predicted_pressure - reference_pressure == float(
                legacy[f"{direction}_pressure_error_pa"]
            )
            pressure_error = predicted_pressure - reference_pressure
            relative_pressure_error = pressure_error / reference_pressure
            assert relative_pressure_error == float(
                legacy[f"{direction}_pressure_relative_error"]
            )
            assert relative_pressure_error * 100.0 == float(
                legacy[f"{direction}_pressure_percent_error"]
            )
            pressure_reference_value = next(
                value
                for value in case.reference_values
                if value.quantity is ValidationQuantity.PRESSURE
            )
            assert pressure_reference_value.uncertainty is not None
            pressure_uncertainty = cast(
                float, pressure_reference_value.uncertainty.value
            )
            assert pressure_error / pressure_uncertainty == float(
                legacy[f"{direction}_pressure_uncertainty_normalized_residual"]
            )
            error_field = (
                "bubble_vapor_composition_errors"
                if direction == "bubble"
                else "dew_liquid_composition_errors"
            )
            composition_errors = tuple(
                predicted - reference
                for predicted, reference in zip(
                    predicted_composition, reference_composition, strict=True
                )
            )
            assert composition_errors == _json_vector(legacy[error_field])
            assert max(abs(error) for error in composition_errors) == float(
                legacy[f"{direction}_maximum_absolute_composition_error"]
            )
            if direction == "bubble":
                composition_reference_value = next(
                    value
                    for value in case.reference_values
                    if value.quantity is ValidationQuantity.MOLE_FRACTION
                )
                assert composition_reference_value.uncertainty is not None
                composition_uncertainties = cast(
                    tuple[float, ...],
                    composition_reference_value.uncertainty.value,
                )
                assert max(
                    abs(error / uncertainty)
                    for error, uncertainty in zip(
                        composition_errors,
                        composition_uncertainties,
                        strict=True,
                    )
                ) == float(
                    legacy["bubble_maximum_composition_uncertainty_normalized_residual"]
                )
            else:
                assert (
                    legacy["dew_maximum_composition_uncertainty_normalized_residual"]
                    == ""
                )


def test_published_uncertainty_shape_and_absence_are_preserved() -> None:
    _, records = _records_by_capability()
    for capability, capability_records in records.items():
        for record in capability_records.values():
            pressure = next(
                value
                for value in record.case.reference_values
                if value.quantity is ValidationQuantity.PRESSURE
            )
            specified_composition = next(
                value
                for value in record.case.specified_conditions
                if value.quantity is ValidationQuantity.MOLE_FRACTION
            )
            opposite_composition = next(
                value
                for value in record.case.reference_values
                if value.quantity is ValidationQuantity.MOLE_FRACTION
            )
            assert pressure.uncertainty is not None
            assert isinstance(pressure.uncertainty.value, float)
            if capability is CapabilityUnderTest.BUBBLE_POINT:
                assert specified_composition.uncertainty is None
                vapor = opposite_composition
            else:
                vapor = specified_composition
                assert opposite_composition.uncertainty is None
            assert vapor.uncertainty is not None
            assert isinstance(vapor.uncertainty.value, tuple)
            assert len(vapor.uncertainty.value) == len(record.case.component_ids)
            assert vapor.uncertainty.coverage_factor is None


def test_retrospective_nearest_root_cannot_replace_production_prediction() -> None:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    legacy = _csv_rows(LEGACY_PATH)["may2015_ch4_c2_012"]
    adapted, records = _records_by_capability()
    record = records[CapabilityUnderTest.DEW_POINT]["may2015_ch4_c2_012"]
    production_pressure = cast(
        float, _value(record.prediction.values, ValidationQuantity.PRESSURE)
    )
    nearest_pressure = float(legacy["dew_nearest_experimental_root_pressure_pa"])

    assert production_pressure == float(legacy["dew_predicted_pressure_pa"])
    assert production_pressure != nearest_pressure
    assert (
        adapted.interpretation["dew_branch_diagnostics"]
        == summary["interpretation"]["dew_branch_diagnostics"]
    )
    assert len(record.prediction.diagnostics) == 1
    diagnostic = record.prediction.diagnostics[0]
    assert isinstance(diagnostic, FrozenJsonObject)
    assert diagnostic["kind"] == RETROSPECTIVE_DIAGNOSTIC_KIND
    assert (
        diagnostic["interpretation"]
        == summary["interpretation"]["dew_branch_diagnostics"]
    )
    values = diagnostic["values"]
    assert isinstance(values, FrozenJsonObject)
    assert values["dew_nearest_experimental_root_pressure_pa"] == nearest_pressure
    assert "dew_nearest_experimental_root_pressure_pa" not in (
        record.prediction.solver_metadata
    )
    assert all(value.value != nearest_pressure for value in record.prediction.values)


def test_anomaly_is_an_ordinary_retained_case_and_case_ids_are_stable() -> None:
    first, first_records = _records_by_capability()
    second = load_module17_validation_evidence(ROOT)
    assert [case.case_id for dataset in first.datasets for case in dataset.cases] == [
        case.case_id for dataset in second.datasets for case in dataset.cases
    ]
    for capability_records in first_records.values():
        anomaly_records = [
            record
            for record in capability_records.values()
            if _value(record.case.specified_conditions, ValidationQuantity.TEMPERATURE)
            == 283.38
        ]
        assert anomaly_records
        assert all(
            record.status is not ValidationStatus.EXCLUDED
            and record.exclusion_reason is None
            for record in anomaly_records
        )


def test_module17_provenance_is_preserved_without_inferred_coverage_factor() -> None:
    raw_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    adapted = load_module17_validation_evidence(ROOT)
    manifest = adapted.datasets[0].source_manifest

    assert adapted.datasets[1].source_manifest == manifest
    assert manifest.citation_text == raw_manifest["citation"]
    assert manifest.doi == raw_manifest["doi"]
    assert manifest.archive_name == raw_manifest["archive_name"]
    assert manifest.archive_url == raw_manifest["thermoml_page_url"]
    assert raw_manifest["thermoml_json_url"] in manifest.extraction_method
    assert manifest.access_date.isoformat() == raw_manifest["access_date"]
    assert manifest.raw_sha256 == raw_manifest["raw_json_sha256"]
    assert manifest.normalized_sha256 == raw_manifest["normalized_csv_sha256"]
    assert manifest.raw_snapshot_policy == raw_manifest["raw_snapshot_policy"]
    assert manifest.measurement_methods == (
        raw_manifest["pressure_measurement_method"],
        raw_manifest["vapor_composition_measurement_method"],
    )
    assert (
        json.loads(manifest.uncertainty_definition or "null")
        == raw_manifest["uncertainty_availability"]
    )
    assert manifest.confidence_level_percent == 95.0
    assert manifest.coverage_factor is None
    assert len(manifest.compound_identities) == 3
    assert all(
        key in manifest.extraction_method
        for key in (
            "selected_datasets",
            "thermoml_compound_mapping",
            "source_anomalies",
            "normalized_point_counts",
        )
    )
    assert all(record.case.source_reference for record in adapted.records)


def test_adapted_artifacts_round_trip_without_shape_or_value_changes() -> None:
    adapted = load_module17_validation_evidence(ROOT)
    for dataset in adapted.datasets:
        encoded = encode_reference_dataset(dataset)
        decoded = decode_reference_dataset(encoded)
        assert encode_reference_dataset(decoded) == encoded
        for case in decoded.cases:
            uncertainties = (
                value.uncertainty
                for value in (*case.specified_conditions, *case.reference_values)
                if value.uncertainty is not None
            )
            assert any(
                isinstance(uncertainty.value, tuple) for uncertainty in uncertainties
            )
    for record in adapted.records:
        encoded = encode_validation_record(record)
        decoded = decode_validation_record(encoded)
        assert encode_validation_record(decoded) == encoded


def test_legacy_error_metric_columns_are_not_stored_in_adapted_records() -> None:
    adapted = load_module17_validation_evidence(ROOT)
    encoded = b"".join(encode_validation_record(record) for record in adapted.records)
    forbidden_fields = (
        "bubble_pressure_error_pa",
        "bubble_pressure_relative_error",
        "bubble_pressure_percent_error",
        "bubble_pressure_uncertainty_normalized_residual",
        "bubble_vapor_composition_errors",
        "bubble_maximum_absolute_composition_error",
        "bubble_maximum_composition_uncertainty_normalized_residual",
        "dew_pressure_error_pa",
        "dew_pressure_relative_error",
        "dew_pressure_percent_error",
        "dew_pressure_uncertainty_normalized_residual",
        "dew_liquid_composition_errors",
        "dew_maximum_absolute_composition_error",
        "dew_maximum_composition_uncertainty_normalized_residual",
    )
    assert all(field.encode() not in encoded for field in forbidden_fields)
