"""Synthetic round-trip and adversarial serialization tests."""

from __future__ import annotations

import copy
import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

from pvt_phase_simulator_validation import (
    SCHEMA_VERSION,
    DataClass,
    DatasetPin,
    DeclaredTolerance,
    InvariantViolationError,
    MixedDataClassError,
    PredictionOutcome,
    RunMetadata,
    SchemaVersionError,
    SerializationError,
    Uncertainty,
    UncertaintyKind,
    UnsupportedValueError,
    ValidationPrediction,
    ValidationQuantity,
    ValidationRecord,
    ValidationRun,
    ValidationStatus,
    decode_reference_dataset,
    decode_validation_record,
    decode_validation_run,
    encode_reference_dataset,
    encode_validation_record,
    encode_validation_run,
)

from .test_validation_core import (
    NORMALIZED_HASH,
    RAW_HASH,
    _dataset,
    _identity,
    _record,
)


def _document(encoded: bytes) -> dict[str, object]:
    result = json.loads(encoded)
    assert isinstance(result, dict)
    return result


def _encoded(document: dict[str, object]) -> bytes:
    return (json.dumps(document, separators=(",", ":")) + "\n").encode()


def _run(*, run_id: str = "run-a", timestamp_hour: int = 10) -> ValidationRun:
    first = _record(case_id="case-002")
    second = _record(case_id="case-001")
    return ValidationRun(
        metadata=RunMetadata(
            run_id=run_id,
            timestamp_utc=datetime(2026, 9, 9, timestamp_hour, tzinfo=UTC),
        ),
        framework_schema_version=SCHEMA_VERSION,
        openphase_package_version="0.1.0",
        git_commit_sha="610057c878a231565f2beff10e5fd13825458e46",
        python_version="3.12.11",
        platform="synthetic-platform",
        datasets=(DatasetPin(_identity(), RAW_HASH, NORMALIZED_HASH),),
        reproduction_command="python -m synthetic_validation",
        records=(first, second),
    )


def test_dataset_record_and_run_round_trips_are_byte_identical() -> None:
    dataset_bytes = encode_reference_dataset(_dataset())
    record_bytes = encode_validation_record(_record())
    run = _run()
    run_bytes = encode_validation_run(run)
    assert (
        encode_reference_dataset(decode_reference_dataset(dataset_bytes))
        == dataset_bytes
    )
    assert (
        encode_validation_record(decode_validation_record(record_bytes)) == record_bytes
    )
    assert encode_validation_run(decode_validation_run(run_bytes)) == run_bytes
    assert [item.case.case_id for item in run.records] == ["case-001", "case-002"]


def test_float_typed_integer_inputs_are_canonicalized_before_encoding() -> None:
    dataset = _dataset()
    manifest = replace(
        dataset.source_manifest,
        coverage_factor=2,
        confidence_level_percent=95,
    )
    integer_input = replace(dataset, source_manifest=manifest)
    first = encode_reference_dataset(integer_input)
    assert encode_reference_dataset(decode_reference_dataset(first)) == first
    assert b'"coverage_factor":2.0' in first


def test_float_serialization_uses_python_round_trip_representation() -> None:
    value = 1_249_999.9999999998
    encoded = encode_validation_record(_record()).decode()
    assert repr(value) in encoded
    decoded = decode_validation_record(encoded)
    assert decoded.prediction.values[0].value == value


def test_uncertainty_scalar_and_vector_shapes_survive_round_trip() -> None:
    dataset = _dataset()
    vector_uncertainty = Uncertainty(
        value=(0.025, 0.01),
        kind=UncertaintyKind.EXPANDED,
        coverage_factor=None,
        confidence_level_percent=95.0,
        source="Synthetic per-component expanded uncertainty.",
    )
    composition = dataset.cases[0].reference_values[1]
    case = replace(
        dataset.cases[0],
        reference_values=(
            dataset.cases[0].reference_values[0],
            replace(composition, uncertainty=vector_uncertainty),
        ),
    )
    encoded = encode_reference_dataset(replace(dataset, cases=(case,)))
    document = _document(encoded)
    decoded = decode_reference_dataset(encoded)
    decoded_pressure = decoded.cases[0].reference_values[0].uncertainty
    decoded_composition = decoded.cases[0].reference_values[1].uncertainty

    assert decoded_pressure is not None
    assert isinstance(decoded_pressure.value, float)
    assert decoded_composition is not None
    assert decoded_composition.value == (0.025, 0.01)
    assert isinstance(decoded_composition.value, tuple)
    assert document["reference_dataset"]["cases"][0]["reference_values"][1][
        "uncertainty"
    ]["value"] == [0.025, 0.01]
    assert encode_reference_dataset(decoded) == encoded


def test_record_identity_is_retained_and_decoder_takes_no_identity_argument() -> None:
    encoded = encode_validation_record(_record())
    decoded = decode_validation_record(encoded)
    assert decoded.identity == _identity(DataClass.EXPERIMENTAL_VALIDATION)
    with pytest.raises(TypeError):
        decode_validation_record(  # type: ignore[call-arg]
            encoded,
            data_class=DataClass.NUMERICAL_CROSS_CHECK,
        )


def test_tampered_record_identity_cannot_reclassify_its_case() -> None:
    document = _document(encode_validation_record(_record()))
    record = document["validation_record"]
    assert isinstance(record, dict)
    identity = record["identity"]
    assert isinstance(identity, dict)
    identity["data_class"] = DataClass.NUMERICAL_CROSS_CHECK.value
    with pytest.raises(InvariantViolationError, match="identity disagrees"):
        decode_validation_record(_encoded(document))


def test_replacing_decoded_record_identity_is_rejected() -> None:
    decoded = decode_validation_record(encode_validation_record(_record()))
    with pytest.raises(ValueError, match="init=False"):
        replace(
            decoded,
            identity=_identity(DataClass.NUMERICAL_CROSS_CHECK),
        )


def test_decoded_record_cannot_be_reclassified_by_public_copy_apis() -> None:
    decoded = decode_validation_record(encode_validation_record(_record()))
    cross_identity = _identity(DataClass.NUMERICAL_CROSS_CHECK)
    with pytest.raises(FrozenInstanceError):
        decoded.identity = cross_identity  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        decoded.case.identity.data_class = (  # type: ignore[misc]
            DataClass.NUMERICAL_CROSS_CHECK
        )
    with pytest.raises(ValueError, match="init=False"):
        replace(decoded, identity=cross_identity)
    with pytest.raises(ValueError, match="init=False"):
        replace(
            decoded,
            case=replace(decoded.case, identity=cross_identity),
        )
    with pytest.raises(TypeError, match="unexpected keyword argument 'data_class'"):
        ValidationRecord(  # type: ignore[call-arg]
            case=decoded.case,
            prediction=decoded.prediction,
            data_class=DataClass.NUMERICAL_CROSS_CHECK,
        )
    assert copy.copy(decoded).data_class is DataClass.EXPERIMENTAL_VALIDATION
    assert copy.deepcopy(decoded).data_class is DataClass.EXPERIMENTAL_VALIDATION


def test_unknown_schema_version_fails_explicitly() -> None:
    document = _document(encode_validation_record(_record()))
    document["schema_version"] = "99.0"
    with pytest.raises(SchemaVersionError, match="unsupported schema_version"):
        decode_validation_record(_encoded(document))
    with pytest.raises(SchemaVersionError):
        replace(_dataset(), schema_version="99.0")


def test_unknown_capability_fails_explicitly() -> None:
    document = _document(encode_reference_dataset(_dataset()))
    dataset = document["reference_dataset"]
    assert isinstance(dataset, dict)
    dataset["capability"] = "FUTURE_CAPABILITY"
    with pytest.raises(UnsupportedValueError, match="capability"):
        decode_reference_dataset(_encoded(document))


@pytest.mark.parametrize(
    ("path", "unknown"),
    [
        (("validation_record", "identity", "data_class"), "FUTURE_CLASS"),
        (
            (
                "validation_record",
                "case",
                "reference_values",
                0,
                "quantity",
            ),
            "FUTURE_QUANTITY",
        ),
        (("validation_record", "prediction", "outcome"), "FUTURE_OUTCOME"),
        (("validation_record", "status"), "FUTURE_STATUS"),
    ],
)
def test_unknown_required_enum_values_fail_explicitly(
    path: tuple[str | int, ...], unknown: str
) -> None:
    root = _document(encode_validation_record(_record()))
    document: object = root
    for key in path[:-1]:
        if isinstance(key, int):
            assert isinstance(document, list)
        else:
            assert isinstance(document, dict)
        document = document[key]
    assert isinstance(document, dict)
    final = path[-1]
    assert isinstance(final, str)
    document[final] = unknown
    with pytest.raises(UnsupportedValueError, match="unsupported"):
        decode_validation_record(_encoded(root))


def test_unknown_fields_are_not_silently_dropped() -> None:
    document = _document(encode_validation_record(_record()))
    record = document["validation_record"]
    assert isinstance(record, dict)
    record["future_required_field"] = "meaningful"
    with pytest.raises(SerializationError, match="unknown"):
        decode_validation_record(_encoded(document))


def test_duplicate_json_keys_are_rejected_instead_of_overwritten() -> None:
    encoded = encode_validation_record(_record()).decode()
    tampered = encoded.replace(
        f'"schema_version":"{SCHEMA_VERSION}"',
        f'"schema_version":"{SCHEMA_VERSION}","schema_version":"99.0"',
        1,
    )
    with pytest.raises(SerializationError, match="duplicate JSON object key"):
        decode_validation_record(tampered)


def test_all_record_status_shapes_round_trip_without_reclassification() -> None:
    base = _record()
    tolerance = DeclaredTolerance(
        quantity=ValidationQuantity.PRESSURE,
        value=100.0,
        unit="Pa",
        justification="Synthetic benchmark protocol requirement.",
        source_citation="Synthetic protocol, section 2.",
        scope="synthetic pressure comparison",
    )
    failure_prediction = ValidationPrediction(
        case_id=base.case.case_id,
        outcome=PredictionOutcome.FAILURE,
        failure_reason="synthetic non-convergence",
        diagnostics=("failure retained",),
    )
    records = (
        ValidationRecord(
            case=base.case,
            prediction=base.prediction,
            status=ValidationStatus.AGREES_WITHIN_UNCERTAINTY,
        ),
        ValidationRecord(
            case=base.case,
            prediction=base.prediction,
            status=ValidationStatus.OUTSIDE_DECLARED_TOLERANCE,
            declared_tolerance=tolerance,
        ),
        ValidationRecord(
            case=base.case,
            prediction=base.prediction,
            status=ValidationStatus.EXCLUDED,
            exclusion_reason="synthetic exclusion",
        ),
        ValidationRecord(
            case=base.case,
            prediction=failure_prediction,
            status=ValidationStatus.SOLVER_FAILURE,
        ),
    )
    for record in records:
        encoded = encode_validation_record(record)
        decoded = decode_validation_record(encoded)
        assert encode_validation_record(decoded) == encoded
        assert decoded.identity == base.identity


def test_run_volatile_values_are_confined_to_run_metadata_block() -> None:
    left = _document(encode_validation_run(_run(run_id="left", timestamp_hour=10)))
    right = _document(encode_validation_run(_run(run_id="right", timestamp_hour=11)))
    assert left["validation_run"] != right["validation_run"]
    left_run = left["validation_run"]
    right_run = right["validation_run"]
    assert isinstance(left_run, dict)
    assert isinstance(right_run, dict)
    left_run.pop("run_metadata")
    right_run.pop("run_metadata")
    assert left == right


def test_validation_run_cannot_hold_both_data_classes() -> None:
    run = _run()
    with pytest.raises(MixedDataClassError, match="multiple data classes"):
        ValidationRun(
            metadata=run.metadata,
            framework_schema_version=run.framework_schema_version,
            openphase_package_version=run.openphase_package_version,
            git_commit_sha=run.git_commit_sha,
            python_version=run.python_version,
            platform=run.platform,
            datasets=(
                *run.datasets,
                DatasetPin(
                    _identity(DataClass.NUMERICAL_CROSS_CHECK),
                    RAW_HASH,
                    NORMALIZED_HASH,
                ),
            ),
            reproduction_command=run.reproduction_command,
            records=(
                *run.records,
                _record(
                    DataClass.NUMERICAL_CROSS_CHECK,
                    case_id="cross-check-case",
                ),
            ),
        )


def test_validation_run_rejects_mixed_pins_even_without_cross_check_records() -> None:
    run = _run()
    with pytest.raises(MixedDataClassError, match="multiple data classes"):
        replace(
            run,
            datasets=(
                *run.datasets,
                DatasetPin(
                    _identity(DataClass.NUMERICAL_CROSS_CHECK),
                    RAW_HASH,
                    NORMALIZED_HASH,
                ),
            ),
        )


def test_dataset_hashes_survive_serialization() -> None:
    decoded = decode_reference_dataset(encode_reference_dataset(_dataset()))
    assert decoded.source_manifest.raw_sha256 == RAW_HASH.upper()
    assert decoded.source_manifest.normalized_sha256 == NORMALIZED_HASH.upper()
