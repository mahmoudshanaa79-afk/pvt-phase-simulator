"""Read-only adapter for the protected Module 17 validation evidence."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

from .enums import (
    CapabilityUnderTest,
    DataClass,
    PredictionOutcome,
    UncertaintyKind,
    ValidationQuantity,
    ValidationStatus,
)
from .hashing import verify_sha256
from .json_values import FrozenJsonObject
from .models import (
    SCHEMA_VERSION,
    DatasetIdentity,
    PredictionValue,
    ReferenceDataset,
    ReferenceValue,
    ValidationCase,
    ValidationPrediction,
    ValidationRecord,
)
from .provenance import (
    CompoundIdentity,
    OriginalUnit,
    SourceManifest,
    Uncertainty,
    UnitConversion,
)

LEGACY_SOLVER_OUTCOME_KEY = "legacy_solver_outcome"
RETROSPECTIVE_DIAGNOSTIC_KIND = "RETROSPECTIVE_DIAGNOSTIC"

_SOURCE_RELATIVE_PATH = Path("data/experimental/may_2015_ch4_c2_ch4_c3_vle.csv")
_MANIFEST_RELATIVE_PATH = Path("data/experimental/may_2015_source_manifest.json")
_RESULT_RELATIVE_PATH = Path("docs/validation/module17_vle_validation.csv")
_SUMMARY_RELATIVE_PATH = Path("docs/validation/module17_vle_validation_summary.json")
_CAPABILITIES = (
    CapabilityUnderTest.BUBBLE_POINT,
    CapabilityUnderTest.DEW_POINT,
)
_RETROSPECTIVE_FIELDS = (
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
_JSON_RETROSPECTIVE_FIELDS = frozenset(
    {
        "dew_branch_scan_pressure_bounds_pa",
        "dew_diagnostic_root_pressures_pa",
        "dew_diagnostic_root_brackets_pa",
        "experimental_state_log_fugacity_ratio_residuals",
    }
)
_INTEGER_RETROSPECTIVE_FIELDS = frozenset({"dew_diagnostic_root_count"})
_BOOLEAN_RETROSPECTIVE_FIELDS = frozenset({"dew_multiple_roots_detected"})
_TEXT_RETROSPECTIVE_FIELDS = frozenset(
    {
        "dew_production_selected_root_class",
        "dew_nearest_experimental_root_class",
        "dew_failure_classification",
    }
)


@dataclass(frozen=True, slots=True)
class Module17Adaptation:
    """The two datasets and all records read from the protected evidence."""

    datasets: tuple[ReferenceDataset, ReferenceDataset]
    records: tuple[ValidationRecord, ...]
    interpretation: FrozenJsonObject


def _read_json_object(path: Path) -> dict[str, object]:
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or not all(isinstance(key, str) for key in loaded):
        raise ValueError(f"{path} must contain a JSON object")
    return cast(dict[str, object], loaded)


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no CSV header")
        rows: list[dict[str, str]] = []
        for raw_row in reader:
            if None in raw_row or any(value is None for value in raw_row.values()):
                raise ValueError(f"{path} contains a malformed CSV row")
            rows.append(cast(dict[str, str], raw_row))
    return rows


def _manifest_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"manifest {field_name} must be non-empty text")
    return value


def _manifest_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"manifest {field_name} must be a number")
    return float(value)


def _manifest_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"manifest {field_name} must be a boolean")
    return value


def _manifest_list(value: object, field_name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"manifest {field_name} must be an array")
    return cast(list[object], value)


def _manifest_mapping(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"manifest {field_name} must be an object")
    return cast(dict[str, object], value)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _source_manifest(raw: Mapping[str, object]) -> SourceManifest:
    mapping_rows = _manifest_list(
        raw["thermoml_compound_mapping"], "thermoml_compound_mapping"
    )
    compound_identities: list[CompoundIdentity] = []
    for raw_mapping in mapping_rows:
        mapping = _manifest_mapping(raw_mapping, "thermoml_compound_mapping[]")
        compound_identities.append(
            CompoundIdentity(
                component_id=_manifest_text(mapping["name"], "compound name"),
                name=_manifest_text(mapping["name"], "compound name"),
                formula=_manifest_text(mapping["formula"], "compound formula"),
                inchikey=_manifest_text(mapping["inchikey"], "compound inchikey"),
                cas=_manifest_text(
                    mapping["production_cross_reference_cas"], "compound CAS"
                ),
            )
        )

    uncertainty_availability = _manifest_mapping(
        raw["uncertainty_availability"], "uncertainty_availability"
    )
    preserved_extraction_metadata = {
        "normalized_point_counts": raw["normalized_point_counts"],
        "selected_datasets": raw["selected_datasets"],
        "source_anomalies": raw["source_anomalies"],
        "thermoml_compound_mapping": raw["thermoml_compound_mapping"],
        "thermoml_json_url": raw["thermoml_json_url"],
    }
    return SourceManifest(
        source_id=_manifest_text(raw["source_id"], "source_id"),
        citation_text=_manifest_text(raw["citation"], "citation"),
        doi=_manifest_text(raw["doi"], "doi"),
        archive_name=_manifest_text(raw["archive_name"], "archive_name"),
        archive_url=_manifest_text(raw["thermoml_page_url"], "thermoml_page_url"),
        access_date=date.fromisoformat(
            _manifest_text(raw["access_date"], "access_date")
        ),
        raw_sha256=_manifest_text(raw["raw_json_sha256"], "raw_json_sha256"),
        normalized_sha256=_manifest_text(
            raw["normalized_csv_sha256"], "normalized_csv_sha256"
        ),
        raw_snapshot_retained=_manifest_bool(
            raw["raw_snapshot_retained"], "raw_snapshot_retained"
        ),
        raw_snapshot_policy=_manifest_text(
            raw["raw_snapshot_policy"], "raw_snapshot_policy"
        ),
        measurement_methods=(
            _manifest_text(
                raw["pressure_measurement_method"], "pressure_measurement_method"
            ),
            _manifest_text(
                raw["vapor_composition_measurement_method"],
                "vapor_composition_measurement_method",
            ),
        ),
        uncertainty_definition=_canonical_json(uncertainty_availability),
        coverage_factor=None,
        confidence_level_percent=_manifest_number(
            raw["confidence_level_percent"], "confidence_level_percent"
        ),
        original_units=(
            OriginalUnit(
                quantity=ValidationQuantity.PRESSURE,
                unit=_manifest_text(
                    raw["source_pressure_unit"], "source_pressure_unit"
                ),
                context="experimental saturation pressure in the ThermoML source",
            ),
        ),
        unit_conversions=(
            UnitConversion(
                quantity=ValidationQuantity.PRESSURE,
                original_unit=_manifest_text(
                    raw["source_pressure_unit"], "source_pressure_unit"
                ),
                canonical_si_unit=_manifest_text(
                    raw["canonical_pressure_unit"], "canonical_pressure_unit"
                ),
                expression=_manifest_text(
                    raw["pressure_conversion"], "pressure_conversion"
                ),
            ),
        ),
        compound_identities=tuple(compound_identities),
        extraction_method=(
            "The normalized CSV retains source_pair_key plus the pressure and vapor "
            "ThermoML dataset/row coordinates. Additional source-manifest extraction "
            f"metadata is preserved verbatim as canonical JSON: "
            f"{_canonical_json(preserved_extraction_metadata)}"
        ),
        data_class=DataClass.EXPERIMENTAL_VALIDATION,
    )


def _float(row: Mapping[str, str], field_name: str) -> float:
    text = row[field_name]
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return float(text)


def _optional_float(row: Mapping[str, str], field_name: str) -> float | None:
    text = row[field_name]
    return None if text == "" else float(text)


def _integer(row: Mapping[str, str], field_name: str) -> int:
    text = row[field_name]
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return int(text)


def _optional_integer(row: Mapping[str, str], field_name: str) -> int | None:
    text = row[field_name]
    return None if text == "" else int(text)


def _optional_boolean(row: Mapping[str, str], field_name: str) -> bool | None:
    text = row[field_name]
    if text == "":
        return None
    if text == "true":
        return True
    if text == "false":
        return False
    raise ValueError(f"{field_name} must be true, false, or empty")


def _json_array(row: Mapping[str, str], field_name: str) -> list[object]:
    loaded: object = json.loads(row[field_name])
    if not isinstance(loaded, list):
        raise ValueError(f"{field_name} must be a JSON array")
    return cast(list[object], loaded)


def _float_vector(row: Mapping[str, str], field_name: str) -> tuple[float, ...]:
    values = _json_array(row, field_name)
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        for value in values
    ):
        raise ValueError(f"{field_name} must contain only numbers")
    return tuple(float(cast(int | float, value)) for value in values)


def _text_vector(row: Mapping[str, str], field_name: str) -> tuple[str, ...]:
    values = _json_array(row, field_name)
    if not all(isinstance(value, str) for value in values):
        raise ValueError(f"{field_name} must contain only strings")
    return tuple(cast(str, value) for value in values)


def _case_id(source_point_id: str, capability: CapabilityUnderTest) -> str:
    return f"{source_point_id}::{capability.value.lower()}"


def _source_reference(row: Mapping[str, str]) -> str:
    return _canonical_json(
        {
            "pressure_dataset_number": _integer(row, "pressure_dataset_number"),
            "pressure_source_row": _integer(row, "pressure_source_row"),
            "source_pair_key": row["source_pair_key"],
            "source_point_id": row["source_point_id"],
            "vapor_dataset_number": _integer(row, "vapor_dataset_number"),
            "vapor_source_row": _integer(row, "vapor_source_row"),
        }
    )


def _uncertainties(
    source_row: Mapping[str, str], uncertainty_definition: Mapping[str, object]
) -> tuple[Uncertainty, Uncertainty]:
    confidence = _float(source_row, "uncertainty_confidence_level_percent")
    pressure = Uncertainty(
        value=_float(source_row, "pressure_expanded_uncertainty_pa"),
        kind=UncertaintyKind.EXPANDED,
        coverage_factor=None,
        confidence_level_percent=confidence,
        source=_manifest_text(
            uncertainty_definition["pressure"], "pressure uncertainty"
        ),
    )
    vapor_component = _float(source_row, "vapor_heavy_expanded_uncertainty")
    vapor = Uncertainty(
        value=(vapor_component, vapor_component),
        kind=UncertaintyKind.EXPANDED,
        coverage_factor=None,
        confidence_level_percent=confidence,
        source=_manifest_text(
            uncertainty_definition["vapor_composition"],
            "vapor composition uncertainty",
        ),
    )
    return pressure, vapor


def _reference_match(
    source_row: Mapping[str, str], legacy_row: Mapping[str, str]
) -> None:
    source_liquid = (
        _float(source_row, "liquid_methane_mole_fraction"),
        _float(source_row, "liquid_heavy_mole_fraction"),
    )
    source_vapor = (
        _float(source_row, "vapor_methane_mole_fraction"),
        _float(source_row, "vapor_heavy_mole_fraction"),
    )
    source_vapor_uncertainty = (
        _float(source_row, "vapor_heavy_expanded_uncertainty"),
    ) * 2
    checks = {
        "system_id": source_row["system_id"] == legacy_row["system_id"],
        "temperature_k": _float(source_row, "temperature_k")
        == _float(legacy_row, "temperature_k"),
        "experimental_pressure_pa": _float(source_row, "pressure_pa")
        == _float(legacy_row, "experimental_pressure_pa"),
        "liquid_mole_fractions": source_liquid
        == _float_vector(legacy_row, "liquid_mole_fractions"),
        "vapor_mole_fractions": source_vapor
        == _float_vector(legacy_row, "vapor_mole_fractions"),
        "pressure_expanded_uncertainty_pa": _float(
            source_row, "pressure_expanded_uncertainty_pa"
        )
        == _float(legacy_row, "pressure_expanded_uncertainty_pa"),
        "vapor_expanded_uncertainties": source_vapor_uncertainty
        == _float_vector(legacy_row, "vapor_expanded_uncertainties"),
    }
    mismatches = sorted(field for field, agrees in checks.items() if not agrees)
    if mismatches:
        raise ValueError(
            f"reference evidence disagrees for {source_row['source_point_id']!r}: "
            f"{mismatches!r}"
        )


def _case(
    source_row: Mapping[str, str],
    identity: DatasetIdentity,
    capability: CapabilityUnderTest,
    uncertainty_definition: Mapping[str, object],
) -> ValidationCase:
    pressure_uncertainty, vapor_uncertainty = _uncertainties(
        source_row, uncertainty_definition
    )
    liquid = (
        _float(source_row, "liquid_methane_mole_fraction"),
        _float(source_row, "liquid_heavy_mole_fraction"),
    )
    vapor = (
        _float(source_row, "vapor_methane_mole_fraction"),
        _float(source_row, "vapor_heavy_mole_fraction"),
    )
    temperature = ReferenceValue(
        quantity=ValidationQuantity.TEMPERATURE,
        value=_float(source_row, "temperature_k"),
    )
    pressure = ReferenceValue(
        quantity=ValidationQuantity.PRESSURE,
        value=_float(source_row, "pressure_pa"),
        uncertainty=pressure_uncertainty,
    )
    if capability is CapabilityUnderTest.BUBBLE_POINT:
        specified_composition = ReferenceValue(
            quantity=ValidationQuantity.MOLE_FRACTION,
            value=liquid,
        )
        opposite_composition = ReferenceValue(
            quantity=ValidationQuantity.MOLE_FRACTION,
            value=vapor,
            uncertainty=vapor_uncertainty,
        )
    else:
        specified_composition = ReferenceValue(
            quantity=ValidationQuantity.MOLE_FRACTION,
            value=vapor,
            uncertainty=vapor_uncertainty,
        )
        opposite_composition = ReferenceValue(
            quantity=ValidationQuantity.MOLE_FRACTION,
            value=liquid,
        )
    return ValidationCase(
        case_id=_case_id(source_row["source_point_id"], capability),
        identity=identity,
        system_id=source_row["system_id"],
        component_ids=(source_row["component_1_id"], source_row["component_2_id"]),
        specified_conditions=(temperature, specified_composition),
        reference_values=(pressure, opposite_composition),
        source_reference=_source_reference(source_row),
    )


def _solver_metadata(legacy_row: Mapping[str, str], direction: str) -> FrozenJsonObject:
    prefix = f"{direction}_"
    return FrozenJsonObject(
        {
            LEGACY_SOLVER_OUTCOME_KEY: legacy_row[f"{prefix}status"],
            "pressure_solver_iterations": _integer(
                legacy_row, f"{prefix}pressure_solver_iterations"
            ),
            "inner_iteration_count": _integer(
                legacy_row, f"{prefix}inner_iteration_count"
            ),
            "selected_parent_root": _optional_float(
                legacy_row, f"{prefix}selected_parent_root"
            ),
            "selected_incipient_root": _optional_float(
                legacy_row, f"{prefix}selected_incipient_root"
            ),
            "phase_root_ordering_consistent": _optional_boolean(
                legacy_row, f"{prefix}phase_root_ordering_consistent"
            ),
            "maximum_fugacity_equilibrium_residual": _optional_float(
                legacy_row, f"{prefix}maximum_fugacity_equilibrium_residual"
            ),
            "diagnostic_codes": _text_vector(legacy_row, f"{prefix}diagnostic_codes"),
        }
    )


def _retrospective_value(row: Mapping[str, str], field_name: str) -> object:
    if field_name in _JSON_RETROSPECTIVE_FIELDS:
        return _json_array(row, field_name)
    if field_name in _INTEGER_RETROSPECTIVE_FIELDS:
        return _optional_integer(row, field_name)
    if field_name in _BOOLEAN_RETROSPECTIVE_FIELDS:
        return _optional_boolean(row, field_name)
    if field_name in _TEXT_RETROSPECTIVE_FIELDS:
        return row[field_name] or None
    return _optional_float(row, field_name)


def _retrospective_diagnostic(
    legacy_row: Mapping[str, str], interpretation: str
) -> FrozenJsonObject:
    return FrozenJsonObject(
        {
            "kind": RETROSPECTIVE_DIAGNOSTIC_KIND,
            "interpretation": interpretation,
            "values": {
                field_name: _retrospective_value(legacy_row, field_name)
                for field_name in _RETROSPECTIVE_FIELDS
            },
        }
    )


def _prediction(
    legacy_row: Mapping[str, str],
    case_id: str,
    capability: CapabilityUnderTest,
    retrospective_interpretation: str,
) -> ValidationPrediction:
    direction = "bubble" if capability is CapabilityUnderTest.BUBBLE_POINT else "dew"
    legacy_outcome = legacy_row[f"{direction}_status"]
    metadata = _solver_metadata(legacy_row, direction)
    diagnostics = (
        ()
        if direction == "bubble"
        else (
            _retrospective_diagnostic(
                legacy_row,
                retrospective_interpretation,
            ),
        )
    )
    predicted_pressure = _optional_float(
        legacy_row, f"{direction}_predicted_pressure_pa"
    )
    predicted_composition = _float_vector(
        legacy_row,
        (
            "bubble_predicted_vapor_composition"
            if direction == "bubble"
            else "dew_predicted_liquid_composition"
        ),
    )
    if legacy_outcome == "converged":
        if predicted_pressure is None or not predicted_composition:
            raise ValueError(
                f"converged prediction {case_id!r} lacks production values"
            )
        if legacy_row[f"{direction}_failure_reason"]:
            raise ValueError(f"converged prediction {case_id!r} has a failure reason")
        return ValidationPrediction(
            case_id=case_id,
            outcome=PredictionOutcome.VALUE,
            values=(
                PredictionValue(ValidationQuantity.PRESSURE, predicted_pressure),
                PredictionValue(
                    ValidationQuantity.MOLE_FRACTION,
                    predicted_composition,
                ),
            ),
            diagnostics=diagnostics,
            solver_metadata=metadata,
        )
    if legacy_outcome not in {"not_found", "inconclusive"}:
        raise ValueError(f"unsupported legacy solver outcome {legacy_outcome!r}")
    if predicted_pressure is not None or predicted_composition:
        raise ValueError(f"failed prediction {case_id!r} contains production values")
    return ValidationPrediction(
        case_id=case_id,
        outcome=PredictionOutcome.FAILURE,
        failure_reason=legacy_row[f"{direction}_failure_reason"],
        diagnostics=diagnostics,
        solver_metadata=metadata,
    )


def _identity(
    manifest: SourceManifest, capability: CapabilityUnderTest
) -> DatasetIdentity:
    return DatasetIdentity(
        dataset_id=f"{manifest.source_id}:{capability.value.lower()}",
        dataset_version=manifest.normalized_sha256,
        data_class=manifest.data_class,
    )


def load_module17_validation_evidence(
    repository_root: str | Path,
) -> Module17Adaptation:
    """Adapt protected Module 17 CSV/JSON evidence without recalculating science."""

    root = Path(repository_root)
    manifest_raw = _read_json_object(root / _MANIFEST_RELATIVE_PATH)
    source_path = root / _SOURCE_RELATIVE_PATH
    verify_sha256(
        source_path.read_bytes(),
        _manifest_text(manifest_raw["normalized_csv_sha256"], "normalized_csv_sha256"),
    )
    source_manifest = _source_manifest(manifest_raw)
    source_rows = _read_csv_rows(source_path)
    legacy_rows = _read_csv_rows(root / _RESULT_RELATIVE_PATH)
    summary = _read_json_object(root / _SUMMARY_RELATIVE_PATH)

    source_by_id = {row["source_point_id"]: row for row in source_rows}
    legacy_by_id = {row["source_point_id"]: row for row in legacy_rows}
    if len(source_by_id) != len(source_rows):
        raise ValueError(
            "experimental evidence contains duplicate source_point_id values"
        )
    if len(legacy_by_id) != len(legacy_rows):
        raise ValueError("legacy evidence contains duplicate source_point_id values")
    if source_by_id.keys() != legacy_by_id.keys():
        raise ValueError("experimental and legacy evidence source_point_id sets differ")

    expected_point_counts = _manifest_mapping(
        manifest_raw["normalized_point_counts"], "normalized_point_counts"
    )
    expected_count = sum(
        int(_manifest_number(value, f"normalized_point_counts.{system_id}"))
        for system_id, value in expected_point_counts.items()
    )
    if len(source_rows) != expected_count:
        raise ValueError(
            f"experimental evidence has {len(source_rows)} points; "
            f"expected {expected_count}"
        )
    if summary["source_id"] != source_manifest.source_id:
        raise ValueError("summary source_id disagrees with the source manifest")
    if summary["normalized_csv_sha256"] != source_manifest.normalized_sha256:
        raise ValueError(
            "summary normalized CSV hash disagrees with the source manifest"
        )
    if summary["source_point_count"] != expected_count:
        raise ValueError("summary point count disagrees with the source manifest")

    interpretation_raw = _manifest_mapping(summary["interpretation"], "interpretation")
    retrospective_interpretation = _manifest_text(
        interpretation_raw["dew_branch_diagnostics"],
        "interpretation.dew_branch_diagnostics",
    )
    interpretation = FrozenJsonObject(interpretation_raw)
    uncertainty_definition = _manifest_mapping(
        manifest_raw["uncertainty_availability"], "uncertainty_availability"
    )

    datasets: list[ReferenceDataset] = []
    records: list[ValidationRecord] = []
    sorted_ids = sorted(source_by_id)
    for capability in _CAPABILITIES:
        identity = _identity(source_manifest, capability)
        cases: list[ValidationCase] = []
        capability_records: list[ValidationRecord] = []
        for source_point_id in sorted_ids:
            source_row = source_by_id[source_point_id]
            legacy_row = legacy_by_id[source_point_id]
            _reference_match(source_row, legacy_row)
            case = _case(
                source_row,
                identity,
                capability,
                uncertainty_definition,
            )
            prediction = _prediction(
                legacy_row,
                case.case_id,
                capability,
                retrospective_interpretation,
            )
            status = (
                ValidationStatus.REPORTED_NO_TOLERANCE
                if prediction.outcome is PredictionOutcome.VALUE
                else ValidationStatus.SOLVER_FAILURE
            )
            cases.append(case)
            capability_records.append(
                ValidationRecord(case=case, prediction=prediction, status=status)
            )
        datasets.append(
            ReferenceDataset(
                identity=identity,
                schema_version=SCHEMA_VERSION,
                source_manifest=source_manifest,
                capability=capability,
                cases=tuple(cases),
            )
        )
        records.extend(capability_records)

    if len(datasets) != 2:
        raise AssertionError("Module 17 adaptation must emit exactly two datasets")
    return Module17Adaptation(
        datasets=(datasets[0], datasets[1]),
        records=tuple(records),
        interpretation=interpretation,
    )


adapt_module17_evidence = load_module17_validation_evidence
