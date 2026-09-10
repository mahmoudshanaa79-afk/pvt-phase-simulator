"""Synthetic tests for the immutable validation-core contract."""

from __future__ import annotations

import copy
import hashlib
from dataclasses import FrozenInstanceError, is_dataclass, replace
from datetime import date

import pytest

from pvt_phase_simulator_validation import (
    SCHEMA_VERSION,
    CapabilityUnderTest,
    CompoundIdentity,
    CrossCheckAgreementSummary,
    DataClass,
    DatasetIdentity,
    DeclaredTolerance,
    ExperimentalAccuracySummary,
    FrozenJsonObject,
    HashMismatchError,
    InvariantViolationError,
    MixedDataClassError,
    OriginalUnit,
    PredictionOutcome,
    PredictionValue,
    ReferenceDataset,
    ReferenceValue,
    SourceManifest,
    Uncertainty,
    UncertaintyKind,
    UnitConversion,
    UnsupportedValueError,
    ValidationCase,
    ValidationPrediction,
    ValidationQuantity,
    ValidationRecord,
    ValidationStatus,
    aggregation,
    homogeneous_data_class,
    models,
    normalize_sha256,
    provenance,
    summarize_cross_check_agreement,
    summarize_experimental_accuracy,
    verify_sha256,
)

RAW_CONTENT = b"synthetic raw reference content\n"
NORMALIZED_CONTENT = b"temperature_k,pressure_pa\n250.0,1250000.0\n"
RAW_HASH = hashlib.sha256(RAW_CONTENT).hexdigest()
NORMALIZED_HASH = hashlib.sha256(NORMALIZED_CONTENT).hexdigest()


def _identity(
    data_class: DataClass = DataClass.EXPERIMENTAL_VALIDATION,
) -> DatasetIdentity:
    return DatasetIdentity("synthetic-vle", "2026-09-09", data_class)


def _manifest(
    data_class: DataClass = DataClass.EXPERIMENTAL_VALIDATION,
) -> SourceManifest:
    return SourceManifest(
        source_id="synthetic-source",
        citation_text="A. Researcher, Synthetic Measurements (2026).",
        doi="10.0000/synthetic",
        archive_name="Synthetic archive",
        archive_url="https://example.invalid/archive",
        access_date=date(2026, 9, 9),
        raw_sha256=RAW_HASH,
        normalized_sha256=NORMALIZED_HASH,
        raw_snapshot_retained=False,
        raw_snapshot_policy="Synthetic bytes exist only inside this test.",
        measurement_methods=("Synthetic static-cell method",),
        uncertainty_definition="Expanded uncertainty stated by the synthetic source.",
        coverage_factor=2.0,
        confidence_level_percent=95.0,
        original_units=(
            OriginalUnit(
                ValidationQuantity.PRESSURE,
                "kPa",
                "reported saturation pressure",
            ),
        ),
        unit_conversions=(
            UnitConversion(
                ValidationQuantity.PRESSURE,
                "kPa",
                "Pa",
                "pressure_pa = pressure_kpa * 1000",
            ),
        ),
        compound_identities=(
            CompoundIdentity(
                "methane",
                "methane",
                "CH4",
                "VNWKTOKETHGBQD-UHFFFAOYSA-N",
                "74-82-8",
            ),
            CompoundIdentity(
                "ethane",
                "ethane",
                "C2H6",
                "OTMSDBZUPAUEDD-UHFFFAOYSA-N",
                "74-84-0",
            ),
        ),
        extraction_method="Synthetic in-memory fixture construction.",
        data_class=data_class,
    )


def _case(
    data_class: DataClass = DataClass.EXPERIMENTAL_VALIDATION,
    *,
    case_id: str = "case-002",
) -> ValidationCase:
    return ValidationCase(
        case_id=case_id,
        identity=_identity(data_class),
        system_id="methane-ethane",
        component_ids=("methane", "ethane"),
        specified_conditions=(
            ReferenceValue(ValidationQuantity.TEMPERATURE, 250.0),
            ReferenceValue(ValidationQuantity.MOLE_FRACTION, (0.25, 0.75)),
        ),
        reference_values=(
            ReferenceValue(
                ValidationQuantity.PRESSURE,
                1_250_000.0,
                Uncertainty(
                    value=1_250.0,
                    kind=UncertaintyKind.EXPANDED,
                    coverage_factor=2.0,
                    confidence_level_percent=95.0,
                    source="Synthetic table footnote.",
                ),
            ),
            ReferenceValue(ValidationQuantity.MOLE_FRACTION, (0.8, 0.2)),
        ),
        source_reference="table=1,row=2",
    )


def _prediction(*, case_id: str = "case-002") -> ValidationPrediction:
    return ValidationPrediction(
        case_id=case_id,
        outcome=PredictionOutcome.VALUE,
        values=(
            PredictionValue(ValidationQuantity.PRESSURE, 1_249_999.9999999998),
            PredictionValue(ValidationQuantity.MOLE_FRACTION, (0.79, 0.21)),
        ),
        diagnostics=(
            "solver diagnostic preserved verbatim",
            {"iterations": 7, "history": [1.0, 0.125]},
        ),
        solver_metadata=FrozenJsonObject(
            {"solver": "synthetic", "settings": {"mode": "strict"}}
        ),
    )


def _record(
    data_class: DataClass = DataClass.EXPERIMENTAL_VALIDATION,
    *,
    case_id: str = "case-002",
) -> ValidationRecord:
    return ValidationRecord(
        case=_case(data_class, case_id=case_id),
        prediction=_prediction(case_id=case_id),
    )


def _dataset(
    data_class: DataClass = DataClass.EXPERIMENTAL_VALIDATION,
) -> ReferenceDataset:
    return ReferenceDataset(
        identity=_identity(data_class),
        schema_version=SCHEMA_VERSION,
        source_manifest=_manifest(data_class),
        capability=CapabilityUnderTest.BUBBLE_POINT,
        cases=(_case(data_class),),
    )


def test_dataset_identity_is_propagated_and_checked() -> None:
    dataset = _dataset()
    assert dataset.cases[0].identity == dataset.identity
    assert _record().identity == dataset.identity
    assert dataset.data_class is DataClass.EXPERIMENTAL_VALIDATION
    assert dataset.cases[0].data_class is DataClass.EXPERIMENTAL_VALIDATION
    assert _record().data_class is DataClass.EXPERIMENTAL_VALIDATION
    mismatched = _case(DataClass.NUMERICAL_CROSS_CHECK)
    with pytest.raises(InvariantViolationError, match="identity disagrees"):
        replace(dataset, cases=(mismatched,))
    with pytest.raises(InvariantViolationError, match="manifest data_class"):
        ReferenceDataset(
            identity=_identity(DataClass.NUMERICAL_CROSS_CHECK),
            schema_version=SCHEMA_VERSION,
            source_manifest=_manifest(DataClass.EXPERIMENTAL_VALIDATION),
            capability=CapabilityUnderTest.BUBBLE_POINT,
            cases=(),
        )


def test_record_has_no_independent_data_class_constructor_argument() -> None:
    with pytest.raises(TypeError, match="unexpected keyword argument 'identity'"):
        ValidationRecord(  # type: ignore[call-arg]
            case=_case(),
            prediction=_prediction(),
            identity=_identity(DataClass.NUMERICAL_CROSS_CHECK),
        )
    with pytest.raises(ValueError, match="init=False"):
        replace(
            _record(),
            identity=_identity(DataClass.NUMERICAL_CROSS_CHECK),
        )


def test_dataclasses_replace_cannot_swap_a_record_to_a_cross_class_case() -> None:
    with pytest.raises(ValueError, match="init=False"):
        replace(
            _record(),
            case=_case(DataClass.NUMERICAL_CROSS_CHECK),
        )


def test_record_and_nested_identity_resist_mutation_and_copying() -> None:
    record = _record()
    with pytest.raises(FrozenInstanceError):
        record.identity = _identity(DataClass.NUMERICAL_CROSS_CHECK)  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        record.case.identity.data_class = DataClass.NUMERICAL_CROSS_CHECK  # type: ignore[misc]
    assert copy.copy(record).identity == record.identity
    assert copy.deepcopy(record).identity == record.identity


def test_every_core_dataclass_is_frozen() -> None:
    dataclass_types = [
        value
        for module in (aggregation, models, provenance)
        for value in vars(module).values()
        if isinstance(value, type)
        and value.__module__ == module.__name__
        and is_dataclass(value)
    ]
    assert dataclass_types
    assert all(value.__dataclass_params__.frozen for value in dataclass_types)


def test_aggregation_rejects_mixed_data_classes_before_summary_construction() -> None:
    experimental = _record()
    cross_check = _record(DataClass.NUMERICAL_CROSS_CHECK)
    with pytest.raises(MixedDataClassError):
        homogeneous_data_class((experimental, cross_check))
    with pytest.raises(MixedDataClassError):
        summarize_experimental_accuracy((experimental, cross_check))
    with pytest.raises(MixedDataClassError):
        summarize_cross_check_agreement((experimental, cross_check))


def test_summary_types_have_distinct_vocabulary_and_reject_other_class() -> None:
    experimental = _record()
    cross_check = _record(DataClass.NUMERICAL_CROSS_CHECK)
    accuracy = ExperimentalAccuracySummary((experimental,))
    agreement = CrossCheckAgreementSummary((cross_check,))
    assert accuracy.accuracy_records == (experimental,)
    assert not hasattr(accuracy, "agreement_records")
    assert agreement.agreement_records == (cross_check,)
    assert not hasattr(agreement, "accuracy_records")
    with pytest.raises(MixedDataClassError):
        ExperimentalAccuracySummary((cross_check,))
    with pytest.raises(MixedDataClassError):
        CrossCheckAgreementSummary((experimental,))


def test_failure_prediction_has_no_values_and_forces_failure_status() -> None:
    with pytest.raises(InvariantViolationError, match="must not contain values"):
        ValidationPrediction(
            case_id="case-002",
            outcome=PredictionOutcome.FAILURE,
            values=(PredictionValue(ValidationQuantity.PRESSURE, 1.0),),
            failure_reason="did not converge",
        )
    with pytest.raises(ValueError, match="failure_reason"):
        ValidationPrediction(
            case_id="case-002",
            outcome=PredictionOutcome.FAILURE,
        )
    failure = ValidationPrediction(
        case_id="case-002",
        outcome=PredictionOutcome.FAILURE,
        failure_reason="did not converge",
        diagnostics=("last iterate retained",),
    )
    with pytest.raises(InvariantViolationError, match="requires SOLVER_FAILURE"):
        ValidationRecord(case=_case(), prediction=failure)
    record = ValidationRecord(
        case=_case(),
        prediction=failure,
        status=ValidationStatus.SOLVER_FAILURE,
    )
    assert record.prediction.outcome is PredictionOutcome.FAILURE


def test_exclusion_and_declared_tolerance_consistency_rules() -> None:
    with pytest.raises(ValueError, match="exclusion_reason"):
        ValidationRecord(
            case=_case(),
            prediction=_prediction(),
            status=ValidationStatus.EXCLUDED,
        )
    excluded = ValidationRecord(
        case=_case(),
        prediction=_prediction(),
        status=ValidationStatus.EXCLUDED,
        exclusion_reason="Synthetic case is outside declared source scope.",
    )
    assert excluded.exclusion_reason
    with pytest.raises(InvariantViolationError, match="DeclaredTolerance"):
        ValidationRecord(
            case=_case(),
            prediction=_prediction(),
            status=ValidationStatus.AGREES_WITHIN_DECLARED_TOLERANCE,
        )


@pytest.mark.parametrize("field", ["justification", "source_citation"])
def test_declared_tolerance_requires_justification_and_citation(field: str) -> None:
    values = {
        "quantity": ValidationQuantity.PRESSURE,
        "value": 100.0,
        "unit": "Pa",
        "justification": "Requirement in cited benchmark protocol.",
        "source_citation": "Synthetic benchmark protocol, section 2.",
        "scope": "pressure for the synthetic example",
    }
    values[field] = " "
    with pytest.raises(ValueError, match=field):
        DeclaredTolerance(**values)  # type: ignore[arg-type]


def test_uncertainty_absence_is_none_and_reported_zero_is_representable() -> None:
    without = ReferenceValue(ValidationQuantity.PRESSURE, 100_000.0)
    reported_zero = ReferenceValue(
        ValidationQuantity.PRESSURE,
        100_000.0,
        uncertainty=Uncertainty(
            value=0.0,
            kind=UncertaintyKind.STANDARD,
            coverage_factor=None,
            confidence_level_percent=None,
            source="Synthetic source explicitly reports zero.",
        ),
    )
    assert without.uncertainty is None
    assert reported_zero.uncertainty is not None
    assert reported_zero.uncertainty.value == 0.0


def _uncertainty(value: float | tuple[float, ...]) -> Uncertainty:
    return Uncertainty(
        value=value,
        kind=UncertaintyKind.EXPANDED,
        coverage_factor=None,
        confidence_level_percent=95.0,
        source="Synthetic source-reported expanded uncertainty.",
    )


@pytest.mark.parametrize(
    ("reference_value", "uncertainty_value"),
    [
        (1.0, (0.1,)),
        ((0.25, 0.75), 0.1),
    ],
)
def test_reference_value_rejects_scalar_vector_uncertainty_shape_mismatches(
    reference_value: float | tuple[float, ...],
    uncertainty_value: float | tuple[float, ...],
) -> None:
    with pytest.raises(ValueError, match="same scalar/vector shape"):
        ReferenceValue(
            ValidationQuantity.MOLE_FRACTION,
            reference_value,
            _uncertainty(uncertainty_value),
        )


def test_reference_value_rejects_wrong_uncertainty_vector_length() -> None:
    with pytest.raises(ValueError, match="uncertainty vector length"):
        ReferenceValue(
            ValidationQuantity.MOLE_FRACTION,
            (0.25, 0.75),
            _uncertainty((0.01, 0.01, 0.01)),
        )


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        (0.1, float("nan")),
        (0.1, float("inf")),
    ],
)
def test_uncertainty_rejects_non_finite_scalar_and_vector_values(
    value: float | tuple[float, ...],
) -> None:
    with pytest.raises(ValueError, match="finite"):
        _uncertainty(value)


@pytest.mark.parametrize("value", [-0.1, (0.1, -0.01)])
def test_uncertainty_rejects_negative_scalar_and_vector_values(
    value: float | tuple[float, ...],
) -> None:
    with pytest.raises(ValueError, match="non-negative"):
        _uncertainty(value)


@pytest.mark.parametrize("value", [True, (0.1, True), [0.1, 0.2]])
def test_uncertainty_rejects_non_numeric_or_mutable_values(value: object) -> None:
    with pytest.raises(TypeError, match="uncertainty value"):
        _uncertainty(value)  # type: ignore[arg-type]


def test_vector_uncertainty_retains_explicit_zero_and_component_order() -> None:
    value = ReferenceValue(
        ValidationQuantity.MOLE_FRACTION,
        (0.25, 0.75),
        _uncertainty((0.0, 0.02)),
    )
    case = replace(_case(), reference_values=(value,))
    assert case.component_ids == ("methane", "ethane")
    assert value.uncertainty is not None
    assert value.uncertainty.value == (0.0, 0.02)


@pytest.mark.parametrize(
    "composition",
    [(0.2, 0.2), (-0.1, 1.1), (0.1, 0.2, 0.7)],
)
def test_mole_fraction_vectors_are_component_ordered_and_normalized(
    composition: tuple[float, ...],
) -> None:
    with pytest.raises(ValueError, match="MOLE_FRACTION"):
        replace(
            _case(),
            specified_conditions=(
                ReferenceValue(ValidationQuantity.MOLE_FRACTION, composition),
            ),
        )


def test_quantities_expose_si_units_and_relative_error_semantics() -> None:
    assert ValidationQuantity.PRESSURE.canonical_si_unit == "Pa"
    assert ValidationQuantity.DENSITY.canonical_si_unit == "kg/m^3"
    assert not ValidationQuantity.MOLE_FRACTION.relative_error_meaningful
    assert not ValidationQuantity.VAPOR_FRACTION.relative_error_meaningful
    assert ValidationQuantity.MOLE_FRACTION.relative_error_rationale


def test_provenance_hashes_are_syntax_checked_normalized_and_not_verified() -> None:
    manifest = _manifest()
    assert manifest.raw_sha256 == RAW_HASH.upper()
    assert manifest.normalized_sha256 == NORMALIZED_HASH.upper()
    assert normalize_sha256("a" * 64) == "A" * 64
    with pytest.raises(ValueError, match="64 hexadecimal"):
        replace(manifest, normalized_sha256="not-a-sha256")
    wrong_but_well_formed = "0" * 64
    constructed = replace(manifest, normalized_sha256=wrong_but_well_formed)
    assert constructed.normalized_sha256 == wrong_but_well_formed
    with pytest.raises(ValueError, match="citation_text"):
        replace(manifest, citation_text=" ")


def test_hash_helper_checks_only_supplied_in_memory_content() -> None:
    assert verify_sha256(NORMALIZED_CONTENT, NORMALIZED_HASH) is None
    assert verify_sha256(NORMALIZED_CONTENT.decode(), NORMALIZED_HASH) is None
    with pytest.raises(HashMismatchError, match="does not match expected"):
        verify_sha256(b"different supplied bytes", NORMALIZED_HASH)


def test_diagnostics_and_solver_metadata_are_deeply_immutable() -> None:
    prediction = _prediction()
    diagnostic = prediction.diagnostics[1]
    assert isinstance(diagnostic, FrozenJsonObject)
    history = diagnostic["history"]
    assert history == (1.0, 0.125)
    with pytest.raises(TypeError):
        prediction.solver_metadata["solver"] = "changed"  # type: ignore[index]
    with pytest.raises(TypeError, match="immutable"):
        prediction.solver_metadata._items = ()  # type: ignore[misc]


def test_unknown_constructor_enum_values_fail_explicitly() -> None:
    with pytest.raises(UnsupportedValueError, match="data_class"):
        DatasetIdentity("source", "1", "FUTURE_CLASS")  # type: ignore[arg-type]
    with pytest.raises(UnsupportedValueError, match="quantity"):
        ReferenceValue("FUTURE_QUANTITY", 1.0)  # type: ignore[arg-type]
