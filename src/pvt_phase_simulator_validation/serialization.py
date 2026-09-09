"""Deterministic, explicit JSON serialization for validation artifacts."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import date, datetime
from enum import Enum
from typing import Any, cast

from .enums import (
    CapabilityUnderTest,
    DataClass,
    PredictionOutcome,
    UncertaintyKind,
    ValidationQuantity,
    ValidationStatus,
)
from .exceptions import (
    InvariantViolationError,
    SerializationError,
    UnsupportedValueError,
)
from .json_values import FrozenJsonObject, freeze_json, mutable_json
from .models import (
    SCHEMA_VERSION,
    DatasetIdentity,
    DatasetPin,
    DeclaredTolerance,
    PredictionValue,
    ReferenceDataset,
    ReferenceValue,
    RunMetadata,
    ValidationCase,
    ValidationPrediction,
    ValidationRecord,
    ValidationRun,
    require_supported_schema_version,
)
from .provenance import (
    CompoundIdentity,
    OriginalUnit,
    SourceManifest,
    Uncertainty,
    UnitConversion,
)


def _enum[EnumT: Enum](value: object, enum_type: type[EnumT], field_name: str) -> EnumT:
    if not isinstance(value, str):
        raise SerializationError(f"{field_name} must be a string enum value")
    try:
        return enum_type(value)
    except ValueError as error:
        raise UnsupportedValueError(
            f"unsupported {field_name} {value!r} for {enum_type.__name__}"
        ) from error


def _object(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise SerializationError(f"{field_name} must be a JSON object")
    return cast(dict[str, object], value)


def _array(value: object, field_name: str) -> list[object]:
    if not isinstance(value, list):
        raise SerializationError(f"{field_name} must be a JSON array")
    return cast(list[object], value)


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise SerializationError(f"{field_name} must be a string")
    return value


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _text(value, field_name)


def _number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SerializationError(f"{field_name} must be a number")
    return float(value)


def _optional_number(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    return _number(value, field_name)


def _boolean(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise SerializationError(f"{field_name} must be a boolean")
    return value


def _require_keys(
    payload: Mapping[str, object], expected: tuple[str, ...], field_name: str
) -> None:
    present = set(payload)
    required = set(expected)
    missing = sorted(required - present)
    unknown = sorted(present - required)
    if missing or unknown:
        raise SerializationError(
            f"{field_name} fields do not match schema; "
            f"missing={missing!r}, unknown={unknown!r}"
        )


def _identity_payload(identity: DatasetIdentity) -> dict[str, object]:
    return {
        "dataset_id": identity.dataset_id,
        "dataset_version": identity.dataset_version,
        "data_class": identity.data_class.value,
    }


def _identity_from(payload: object) -> DatasetIdentity:
    item = _object(payload, "identity")
    _require_keys(item, ("dataset_id", "dataset_version", "data_class"), "identity")
    return DatasetIdentity(
        dataset_id=_text(item["dataset_id"], "identity.dataset_id"),
        dataset_version=_text(item["dataset_version"], "identity.dataset_version"),
        data_class=_enum(item["data_class"], DataClass, "identity.data_class"),
    )


def _uncertainty_payload(value: Uncertainty) -> dict[str, object]:
    return {
        "value": value.value,
        "kind": value.kind.value,
        "coverage_factor": value.coverage_factor,
        "confidence_level_percent": value.confidence_level_percent,
        "source": value.source,
    }


def _uncertainty_from(payload: object) -> Uncertainty:
    item = _object(payload, "uncertainty")
    fields = (
        "value",
        "kind",
        "coverage_factor",
        "confidence_level_percent",
        "source",
    )
    _require_keys(item, fields, "uncertainty")
    return Uncertainty(
        value=_number(item["value"], "uncertainty.value"),
        kind=_enum(item["kind"], UncertaintyKind, "uncertainty.kind"),
        coverage_factor=_optional_number(
            item["coverage_factor"], "uncertainty.coverage_factor"
        ),
        confidence_level_percent=_optional_number(
            item["confidence_level_percent"],
            "uncertainty.confidence_level_percent",
        ),
        source=_text(item["source"], "uncertainty.source"),
    )


def _value_payload(value: float | tuple[float, ...]) -> float | list[float]:
    return list(value) if isinstance(value, tuple) else value


def _value_from(payload: object, field_name: str) -> float | tuple[float, ...]:
    if isinstance(payload, list):
        return tuple(_number(item, field_name) for item in payload)
    return _number(payload, field_name)


def _reference_value_payload(value: ReferenceValue) -> dict[str, object]:
    return {
        "quantity": value.quantity.value,
        "value": _value_payload(value.value),
        "uncertainty": (
            None
            if value.uncertainty is None
            else _uncertainty_payload(value.uncertainty)
        ),
    }


def _reference_value_from(payload: object) -> ReferenceValue:
    item = _object(payload, "reference_value")
    _require_keys(item, ("quantity", "value", "uncertainty"), "reference_value")
    uncertainty = item["uncertainty"]
    return ReferenceValue(
        quantity=_enum(
            item["quantity"], ValidationQuantity, "reference_value.quantity"
        ),
        value=_value_from(item["value"], "reference_value.value"),
        uncertainty=(None if uncertainty is None else _uncertainty_from(uncertainty)),
    )


def _prediction_value_payload(value: PredictionValue) -> dict[str, object]:
    return {"quantity": value.quantity.value, "value": _value_payload(value.value)}


def _prediction_value_from(payload: object) -> PredictionValue:
    item = _object(payload, "prediction_value")
    _require_keys(item, ("quantity", "value"), "prediction_value")
    return PredictionValue(
        quantity=_enum(
            item["quantity"], ValidationQuantity, "prediction_value.quantity"
        ),
        value=_value_from(item["value"], "prediction_value.value"),
    )


def _case_payload(case: ValidationCase) -> dict[str, object]:
    return {
        "case_id": case.case_id,
        "identity": _identity_payload(case.identity),
        "system_id": case.system_id,
        "component_ids": list(case.component_ids),
        "specified_conditions": [
            _reference_value_payload(item) for item in case.specified_conditions
        ],
        "reference_values": [
            _reference_value_payload(item) for item in case.reference_values
        ],
        "source_reference": case.source_reference,
    }


def _case_from(payload: object) -> ValidationCase:
    item = _object(payload, "case")
    fields = (
        "case_id",
        "identity",
        "system_id",
        "component_ids",
        "specified_conditions",
        "reference_values",
        "source_reference",
    )
    _require_keys(item, fields, "case")
    return ValidationCase(
        case_id=_text(item["case_id"], "case.case_id"),
        identity=_identity_from(item["identity"]),
        system_id=_text(item["system_id"], "case.system_id"),
        component_ids=tuple(
            _text(value, "case.component_ids[]")
            for value in _array(item["component_ids"], "case.component_ids")
        ),
        specified_conditions=tuple(
            _reference_value_from(value)
            for value in _array(
                item["specified_conditions"], "case.specified_conditions"
            )
        ),
        reference_values=tuple(
            _reference_value_from(value)
            for value in _array(item["reference_values"], "case.reference_values")
        ),
        source_reference=_text(item["source_reference"], "case.source_reference"),
    )


def _prediction_payload(prediction: ValidationPrediction) -> dict[str, object]:
    return {
        "case_id": prediction.case_id,
        "outcome": prediction.outcome.value,
        "values": [_prediction_value_payload(item) for item in prediction.values],
        "failure_reason": prediction.failure_reason,
        "diagnostics": [mutable_json(item) for item in prediction.diagnostics],
        "solver_metadata": mutable_json(prediction.solver_metadata),
    }


def _prediction_from(payload: object) -> ValidationPrediction:
    item = _object(payload, "prediction")
    fields = (
        "case_id",
        "outcome",
        "values",
        "failure_reason",
        "diagnostics",
        "solver_metadata",
    )
    _require_keys(item, fields, "prediction")
    diagnostics = tuple(
        freeze_json(value)
        for value in _array(item["diagnostics"], "prediction.diagnostics")
    )
    solver_metadata = _object(item["solver_metadata"], "prediction.solver_metadata")
    return ValidationPrediction(
        case_id=_text(item["case_id"], "prediction.case_id"),
        outcome=_enum(item["outcome"], PredictionOutcome, "prediction.outcome"),
        values=tuple(
            _prediction_value_from(value)
            for value in _array(item["values"], "prediction.values")
        ),
        failure_reason=_optional_text(
            item["failure_reason"], "prediction.failure_reason"
        ),
        diagnostics=diagnostics,
        solver_metadata=FrozenJsonObject(solver_metadata),
    )


def _tolerance_payload(value: DeclaredTolerance) -> dict[str, object]:
    return {
        "quantity": value.quantity.value,
        "value": value.value,
        "unit": value.unit,
        "justification": value.justification,
        "source_citation": value.source_citation,
        "scope": value.scope,
    }


def _tolerance_from(payload: object) -> DeclaredTolerance:
    item = _object(payload, "declared_tolerance")
    fields = (
        "quantity",
        "value",
        "unit",
        "justification",
        "source_citation",
        "scope",
    )
    _require_keys(item, fields, "declared_tolerance")
    return DeclaredTolerance(
        quantity=_enum(
            item["quantity"], ValidationQuantity, "declared_tolerance.quantity"
        ),
        value=_number(item["value"], "declared_tolerance.value"),
        unit=_text(item["unit"], "declared_tolerance.unit"),
        justification=_text(item["justification"], "declared_tolerance.justification"),
        source_citation=_text(
            item["source_citation"], "declared_tolerance.source_citation"
        ),
        scope=_text(item["scope"], "declared_tolerance.scope"),
    )


def _record_payload(record: ValidationRecord) -> dict[str, object]:
    return {
        "identity": _identity_payload(record.identity),
        "case": _case_payload(record.case),
        "prediction": _prediction_payload(record.prediction),
        "status": record.status.value,
        "exclusion_reason": record.exclusion_reason,
        "declared_tolerance": (
            None
            if record.declared_tolerance is None
            else _tolerance_payload(record.declared_tolerance)
        ),
    }


def _record_from(payload: object) -> ValidationRecord:
    item = _object(payload, "record")
    fields = (
        "identity",
        "case",
        "prediction",
        "status",
        "exclusion_reason",
        "declared_tolerance",
    )
    _require_keys(item, fields, "record")
    serialized_identity = _identity_from(item["identity"])
    case = _case_from(item["case"])
    if serialized_identity != case.identity:
        raise InvariantViolationError(
            "serialized record identity disagrees with serialized case identity"
        )
    tolerance = item["declared_tolerance"]
    return ValidationRecord(
        case=case,
        prediction=_prediction_from(item["prediction"]),
        status=_enum(item["status"], ValidationStatus, "record.status"),
        exclusion_reason=_optional_text(
            item["exclusion_reason"], "record.exclusion_reason"
        ),
        declared_tolerance=(None if tolerance is None else _tolerance_from(tolerance)),
    )


def _compound_payload(value: CompoundIdentity) -> dict[str, object]:
    return {
        "component_id": value.component_id,
        "name": value.name,
        "formula": value.formula,
        "inchikey": value.inchikey,
        "cas": value.cas,
    }


def _compound_from(payload: object) -> CompoundIdentity:
    item = _object(payload, "compound_identity")
    fields = ("component_id", "name", "formula", "inchikey", "cas")
    _require_keys(item, fields, "compound_identity")
    return CompoundIdentity(
        component_id=_text(item["component_id"], "compound_identity.component_id"),
        name=_text(item["name"], "compound_identity.name"),
        formula=_text(item["formula"], "compound_identity.formula"),
        inchikey=_text(item["inchikey"], "compound_identity.inchikey"),
        cas=_text(item["cas"], "compound_identity.cas"),
    )


def _original_unit_payload(value: OriginalUnit) -> dict[str, object]:
    return {
        "quantity": value.quantity.value,
        "unit": value.unit,
        "context": value.context,
    }


def _original_unit_from(payload: object) -> OriginalUnit:
    item = _object(payload, "original_unit")
    _require_keys(item, ("quantity", "unit", "context"), "original_unit")
    return OriginalUnit(
        quantity=_enum(item["quantity"], ValidationQuantity, "original_unit.quantity"),
        unit=_text(item["unit"], "original_unit.unit"),
        context=_text(item["context"], "original_unit.context"),
    )


def _conversion_payload(value: UnitConversion) -> dict[str, object]:
    return {
        "quantity": value.quantity.value,
        "original_unit": value.original_unit,
        "canonical_si_unit": value.canonical_si_unit,
        "expression": value.expression,
    }


def _conversion_from(payload: object) -> UnitConversion:
    item = _object(payload, "unit_conversion")
    fields = ("quantity", "original_unit", "canonical_si_unit", "expression")
    _require_keys(item, fields, "unit_conversion")
    return UnitConversion(
        quantity=_enum(
            item["quantity"], ValidationQuantity, "unit_conversion.quantity"
        ),
        original_unit=_text(item["original_unit"], "unit_conversion.original_unit"),
        canonical_si_unit=_text(
            item["canonical_si_unit"], "unit_conversion.canonical_si_unit"
        ),
        expression=_text(item["expression"], "unit_conversion.expression"),
    )


def _manifest_payload(manifest: SourceManifest) -> dict[str, object]:
    return {
        "source_id": manifest.source_id,
        "citation_text": manifest.citation_text,
        "doi": manifest.doi,
        "archive_name": manifest.archive_name,
        "archive_url": manifest.archive_url,
        "access_date": manifest.access_date.isoformat(),
        "raw_sha256": manifest.raw_sha256,
        "normalized_sha256": manifest.normalized_sha256,
        "raw_snapshot_retained": manifest.raw_snapshot_retained,
        "raw_snapshot_policy": manifest.raw_snapshot_policy,
        "measurement_methods": list(manifest.measurement_methods),
        "uncertainty_definition": manifest.uncertainty_definition,
        "coverage_factor": manifest.coverage_factor,
        "confidence_level_percent": manifest.confidence_level_percent,
        "original_units": [
            _original_unit_payload(item) for item in manifest.original_units
        ],
        "unit_conversions": [
            _conversion_payload(item) for item in manifest.unit_conversions
        ],
        "compound_identities": [
            _compound_payload(item) for item in manifest.compound_identities
        ],
        "extraction_method": manifest.extraction_method,
        "data_class": manifest.data_class.value,
    }


def _manifest_from(payload: object) -> SourceManifest:
    item = _object(payload, "source_manifest")
    fields = (
        "source_id",
        "citation_text",
        "doi",
        "archive_name",
        "archive_url",
        "access_date",
        "raw_sha256",
        "normalized_sha256",
        "raw_snapshot_retained",
        "raw_snapshot_policy",
        "measurement_methods",
        "uncertainty_definition",
        "coverage_factor",
        "confidence_level_percent",
        "original_units",
        "unit_conversions",
        "compound_identities",
        "extraction_method",
        "data_class",
    )
    _require_keys(item, fields, "source_manifest")
    access_date_text = _text(item["access_date"], "source_manifest.access_date")
    try:
        parsed_date = date.fromisoformat(access_date_text)
    except ValueError as error:
        raise SerializationError(
            "source_manifest.access_date must be ISO 8601"
        ) from error
    return SourceManifest(
        source_id=_text(item["source_id"], "source_manifest.source_id"),
        citation_text=_text(item["citation_text"], "source_manifest.citation_text"),
        doi=_optional_text(item["doi"], "source_manifest.doi"),
        archive_name=_text(item["archive_name"], "source_manifest.archive_name"),
        archive_url=_text(item["archive_url"], "source_manifest.archive_url"),
        access_date=parsed_date,
        raw_sha256=_text(item["raw_sha256"], "source_manifest.raw_sha256"),
        normalized_sha256=_text(
            item["normalized_sha256"], "source_manifest.normalized_sha256"
        ),
        raw_snapshot_retained=_boolean(
            item["raw_snapshot_retained"], "source_manifest.raw_snapshot_retained"
        ),
        raw_snapshot_policy=_text(
            item["raw_snapshot_policy"], "source_manifest.raw_snapshot_policy"
        ),
        measurement_methods=tuple(
            _text(value, "source_manifest.measurement_methods[]")
            for value in _array(
                item["measurement_methods"], "source_manifest.measurement_methods"
            )
        ),
        uncertainty_definition=_optional_text(
            item["uncertainty_definition"],
            "source_manifest.uncertainty_definition",
        ),
        coverage_factor=_optional_number(
            item["coverage_factor"], "source_manifest.coverage_factor"
        ),
        confidence_level_percent=_optional_number(
            item["confidence_level_percent"],
            "source_manifest.confidence_level_percent",
        ),
        original_units=tuple(
            _original_unit_from(value)
            for value in _array(
                item["original_units"], "source_manifest.original_units"
            )
        ),
        unit_conversions=tuple(
            _conversion_from(value)
            for value in _array(
                item["unit_conversions"], "source_manifest.unit_conversions"
            )
        ),
        compound_identities=tuple(
            _compound_from(value)
            for value in _array(
                item["compound_identities"], "source_manifest.compound_identities"
            )
        ),
        extraction_method=_text(
            item["extraction_method"], "source_manifest.extraction_method"
        ),
        data_class=_enum(item["data_class"], DataClass, "source_manifest.data_class"),
    )


def _dataset_payload(dataset: ReferenceDataset) -> dict[str, object]:
    return {
        "identity": _identity_payload(dataset.identity),
        "schema_version": dataset.schema_version,
        "source_manifest": _manifest_payload(dataset.source_manifest),
        "capability": dataset.capability.value,
        "cases": [_case_payload(case) for case in dataset.cases],
    }


def _dataset_from(payload: object) -> ReferenceDataset:
    item = _object(payload, "dataset")
    fields = ("identity", "schema_version", "source_manifest", "capability", "cases")
    _require_keys(item, fields, "dataset")
    return ReferenceDataset(
        identity=_identity_from(item["identity"]),
        schema_version=_text(item["schema_version"], "dataset.schema_version"),
        source_manifest=_manifest_from(item["source_manifest"]),
        capability=_enum(item["capability"], CapabilityUnderTest, "dataset.capability"),
        cases=tuple(
            _case_from(value) for value in _array(item["cases"], "dataset.cases")
        ),
    )


def _pin_payload(pin: DatasetPin) -> dict[str, object]:
    return {
        "identity": _identity_payload(pin.identity),
        "raw_sha256": pin.raw_sha256,
        "normalized_sha256": pin.normalized_sha256,
    }


def _pin_from(payload: object) -> DatasetPin:
    item = _object(payload, "dataset_pin")
    fields = ("identity", "raw_sha256", "normalized_sha256")
    _require_keys(item, fields, "dataset_pin")
    return DatasetPin(
        identity=_identity_from(item["identity"]),
        raw_sha256=_text(item["raw_sha256"], "dataset_pin.raw_sha256"),
        normalized_sha256=_text(
            item["normalized_sha256"], "dataset_pin.normalized_sha256"
        ),
    )


def _run_payload(run: ValidationRun) -> dict[str, object]:
    timestamp = run.metadata.timestamp_utc.isoformat().replace("+00:00", "Z")
    return {
        "run_metadata": {
            "run_id": run.metadata.run_id,
            "timestamp_utc": timestamp,
        },
        "reproducibility": {
            "framework_schema_version": run.framework_schema_version,
            "openphase_package_version": run.openphase_package_version,
            "git_commit_sha": run.git_commit_sha,
            "python_version": run.python_version,
            "platform": run.platform,
            "datasets": [_pin_payload(item) for item in run.datasets],
            "reproduction_command": run.reproduction_command,
        },
        "records": [_record_payload(record) for record in run.records],
    }


def _run_from(payload: object) -> ValidationRun:
    item = _object(payload, "run")
    _require_keys(item, ("run_metadata", "reproducibility", "records"), "run")
    metadata = _object(item["run_metadata"], "run.run_metadata")
    _require_keys(metadata, ("run_id", "timestamp_utc"), "run.run_metadata")
    timestamp_text = _text(metadata["timestamp_utc"], "run.run_metadata.timestamp_utc")
    try:
        timestamp = datetime.fromisoformat(timestamp_text.replace("Z", "+00:00"))
    except ValueError as error:
        raise SerializationError("run timestamp_utc must be ISO 8601") from error
    reproducibility = _object(item["reproducibility"], "run.reproducibility")
    fields = (
        "framework_schema_version",
        "openphase_package_version",
        "git_commit_sha",
        "python_version",
        "platform",
        "datasets",
        "reproduction_command",
    )
    _require_keys(reproducibility, fields, "run.reproducibility")
    return ValidationRun(
        metadata=RunMetadata(
            run_id=_text(metadata["run_id"], "run.run_metadata.run_id"),
            timestamp_utc=timestamp,
        ),
        framework_schema_version=_text(
            reproducibility["framework_schema_version"],
            "run.reproducibility.framework_schema_version",
        ),
        openphase_package_version=_text(
            reproducibility["openphase_package_version"],
            "run.reproducibility.openphase_package_version",
        ),
        git_commit_sha=_text(
            reproducibility["git_commit_sha"],
            "run.reproducibility.git_commit_sha",
        ),
        python_version=_text(
            reproducibility["python_version"], "run.reproducibility.python_version"
        ),
        platform=_text(reproducibility["platform"], "run.reproducibility.platform"),
        datasets=tuple(
            _pin_from(value)
            for value in _array(
                reproducibility["datasets"], "run.reproducibility.datasets"
            )
        ),
        reproduction_command=_text(
            reproducibility["reproduction_command"],
            "run.reproducibility.reproduction_command",
        ),
        records=tuple(
            _record_from(value) for value in _array(item["records"], "run.records")
        ),
    )


def _encode_artifact(artifact_type: str, payload: dict[str, object]) -> bytes:
    document = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": artifact_type,
        artifact_type: payload,
    }
    try:
        text = json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        raise SerializationError("artifact contains a non-JSON value") from error
    return (text + "\n").encode("utf-8")


def _decode_artifact(
    encoded: bytes | str,
    artifact_type: str,
    decoder: Callable[[object], Any],
) -> Any:
    if isinstance(encoded, bytes):
        try:
            text = encoded.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SerializationError("artifact must be UTF-8") from error
    elif isinstance(encoded, str):
        text = encoded
    else:
        raise TypeError("encoded artifact must be bytes or text")

    def reject_duplicate_keys(
        pairs: list[tuple[str, object]],
    ) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise SerializationError(f"duplicate JSON object key {key!r}")
            result[key] = value
        return result

    try:
        raw = json.loads(text, object_pairs_hook=reject_duplicate_keys)
    except json.JSONDecodeError as error:
        raise SerializationError("artifact is not valid JSON") from error
    document = _object(raw, "artifact")
    _require_keys(
        document,
        ("schema_version", "artifact_type", artifact_type),
        "artifact",
    )
    schema_version = _text(document["schema_version"], "artifact.schema_version")
    require_supported_schema_version(schema_version)
    actual_type = _text(document["artifact_type"], "artifact.artifact_type")
    if actual_type != artifact_type:
        raise SerializationError(
            f"expected artifact_type {artifact_type!r}, got {actual_type!r}"
        )
    return decoder(document[artifact_type])


def encode_reference_dataset(dataset: ReferenceDataset) -> bytes:
    """Encode a reference dataset as canonical UTF-8 JSON."""

    return _encode_artifact("reference_dataset", _dataset_payload(dataset))


def decode_reference_dataset(encoded: bytes | str) -> ReferenceDataset:
    """Decode and fully validate a reference dataset."""

    return cast(
        ReferenceDataset,
        _decode_artifact(encoded, "reference_dataset", _dataset_from),
    )


def encode_validation_record(record: ValidationRecord) -> bytes:
    """Encode a record, including its immutable dataset identity."""

    return _encode_artifact("validation_record", _record_payload(record))


def decode_validation_record(encoded: bytes | str) -> ValidationRecord:
    """Decode a record using only identity retained in the payload."""

    return cast(
        ValidationRecord,
        _decode_artifact(encoded, "validation_record", _record_from),
    )


def encode_validation_run(run: ValidationRun) -> bytes:
    """Encode a run with volatile metadata isolated in ``run_metadata``."""

    return _encode_artifact("validation_run", _run_payload(run))


def decode_validation_run(encoded: bytes | str) -> ValidationRun:
    """Decode and fully validate a validation run."""

    return cast(
        ValidationRun,
        _decode_artifact(encoded, "validation_run", _run_from),
    )
