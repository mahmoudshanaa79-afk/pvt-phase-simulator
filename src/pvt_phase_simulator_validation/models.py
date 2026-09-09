"""Immutable validation dataset, case, prediction, record, and run types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import fsum

from ._validation import (
    require_enum,
    require_finite,
    require_non_empty,
)
from .enums import (
    CapabilityUnderTest,
    DataClass,
    PredictionOutcome,
    ValidationQuantity,
    ValidationStatus,
)
from .exceptions import InvariantViolationError, MixedDataClassError, SchemaVersionError
from .hashing import normalize_sha256
from .json_values import FrozenJsonObject, JsonValue, freeze_json
from .provenance import SourceManifest, Uncertainty

SCHEMA_VERSION = "1.0"
SUPPORTED_SCHEMA_VERSIONS = frozenset({SCHEMA_VERSION})
MOLE_FRACTION_SUM_ABSOLUTE_TOLERANCE = 1.0e-12


def require_supported_schema_version(schema_version: str) -> None:
    """Reject contracts this reader does not implement."""

    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise SchemaVersionError(
            f"unsupported schema_version {schema_version!r}; "
            f"supported versions: {sorted(SUPPORTED_SCHEMA_VERSIONS)!r}"
        )


@dataclass(frozen=True, slots=True)
class DatasetIdentity:
    """The exact immutable identity propagated to every case and record."""

    dataset_id: str
    dataset_version: str
    data_class: DataClass

    def __post_init__(self) -> None:
        require_non_empty(self.dataset_id, "dataset_id")
        require_non_empty(self.dataset_version, "dataset_version")
        require_enum(self.data_class, DataClass, "data_class")


Value = float | tuple[float, ...]


def _normalize_value(value: Value, field_name: str) -> Value:
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be a scalar or vector of real numbers")
    if isinstance(value, (int, float)):
        normalized = float(value)
        require_finite(normalized, field_name)
        return normalized
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} vectors must be immutable tuples")
    if not value:
        raise ValueError(f"{field_name} vectors must not be empty")
    for item in value:
        require_finite(item, field_name)
    normalized_vector = tuple(float(item) for item in value)
    return normalized_vector


@dataclass(frozen=True, slots=True)
class ReferenceValue:
    """A canonical-SI source value, optionally with reported uncertainty."""

    quantity: ValidationQuantity
    value: Value
    uncertainty: Uncertainty | None = None

    def __post_init__(self) -> None:
        require_enum(self.quantity, ValidationQuantity, "quantity")
        object.__setattr__(
            self, "value", _normalize_value(self.value, "reference value")
        )
        if self.uncertainty is not None and not isinstance(
            self.uncertainty, Uncertainty
        ):
            raise TypeError("uncertainty must be Uncertainty or None")


@dataclass(frozen=True, slots=True)
class PredictionValue:
    """A solver-returned canonical-SI value."""

    quantity: ValidationQuantity
    value: Value

    def __post_init__(self) -> None:
        require_enum(self.quantity, ValidationQuantity, "quantity")
        object.__setattr__(
            self, "value", _normalize_value(self.value, "prediction value")
        )


def _validate_mole_fraction_vector(
    value: ReferenceValue | PredictionValue, component_ids: tuple[str, ...]
) -> None:
    if value.quantity is not ValidationQuantity.MOLE_FRACTION:
        return
    if not isinstance(value.value, tuple):
        raise ValueError("MOLE_FRACTION values must be component-indexed vectors")
    if len(value.value) != len(component_ids):
        raise ValueError(
            "MOLE_FRACTION vector length must match the ordered component_ids"
        )
    if any(item < 0.0 or item > 1.0 for item in value.value):
        raise ValueError("MOLE_FRACTION vector entries must be between 0 and 1")
    if abs(fsum(value.value) - 1.0) > MOLE_FRACTION_SUM_ABSOLUTE_TOLERANCE:
        raise ValueError(
            "MOLE_FRACTION vector must sum to 1 within the declared absolute "
            f"tolerance {MOLE_FRACTION_SUM_ABSOLUTE_TOLERANCE!r}"
        )


@dataclass(frozen=True, slots=True)
class ValidationCase:
    """One source-agnostic reference case with dataset-bound identity."""

    case_id: str
    identity: DatasetIdentity
    system_id: str
    component_ids: tuple[str, ...]
    specified_conditions: tuple[ReferenceValue, ...]
    reference_values: tuple[ReferenceValue, ...]
    source_reference: str

    @property
    def data_class(self) -> DataClass:
        """Return the data class carried only by the parent dataset identity."""

        return self.identity.data_class

    def __post_init__(self) -> None:
        require_non_empty(self.case_id, "case_id")
        if not isinstance(self.identity, DatasetIdentity):
            raise TypeError("identity must be a DatasetIdentity")
        require_non_empty(self.system_id, "system_id")
        object.__setattr__(self, "component_ids", tuple(self.component_ids))
        if not self.component_ids:
            raise ValueError("component_ids must not be empty")
        for component_id in self.component_ids:
            require_non_empty(component_id, "component_id")
        if len(self.component_ids) != len(set(self.component_ids)):
            raise ValueError("component_ids must be unique and ordered")
        object.__setattr__(
            self, "specified_conditions", tuple(self.specified_conditions)
        )
        object.__setattr__(self, "reference_values", tuple(self.reference_values))
        for value in (*self.specified_conditions, *self.reference_values):
            if not isinstance(value, ReferenceValue):
                raise TypeError(
                    "specified_conditions and reference_values must contain "
                    "ReferenceValue objects"
                )
            _validate_mole_fraction_vector(value, self.component_ids)
        require_non_empty(self.source_reference, "source_reference")


@dataclass(frozen=True, slots=True)
class ReferenceDataset:
    """A complete immutable reference dataset and its provenance."""

    identity: DatasetIdentity
    schema_version: str
    source_manifest: SourceManifest
    capability: CapabilityUnderTest
    cases: tuple[ValidationCase, ...]

    @property
    def data_class(self) -> DataClass:
        """Return the dataset's sole declared data class."""

        return self.identity.data_class

    def __post_init__(self) -> None:
        if not isinstance(self.identity, DatasetIdentity):
            raise TypeError("identity must be a DatasetIdentity")
        require_supported_schema_version(self.schema_version)
        if not isinstance(self.source_manifest, SourceManifest):
            raise TypeError("source_manifest must be a SourceManifest")
        if self.source_manifest.data_class is not self.identity.data_class:
            raise InvariantViolationError(
                "source manifest data_class disagrees with dataset identity"
            )
        require_enum(self.capability, CapabilityUnderTest, "capability")
        cases = tuple(self.cases)
        for case in cases:
            if not isinstance(case, ValidationCase):
                raise TypeError("cases must contain ValidationCase objects")
        object.__setattr__(
            self, "cases", tuple(sorted(cases, key=lambda item: item.case_id))
        )
        case_ids: list[str] = []
        for case in self.cases:
            if case.identity != self.identity:
                raise InvariantViolationError(
                    f"case {case.case_id!r} identity disagrees with its dataset"
                )
            case_ids.append(case.case_id)
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("dataset case_ids must be unique")


@dataclass(frozen=True, slots=True)
class ValidationPrediction:
    """A solver result that preserves either values or a failure."""

    case_id: str
    outcome: PredictionOutcome
    values: tuple[PredictionValue, ...] = ()
    failure_reason: str | None = None
    diagnostics: tuple[JsonValue, ...] = ()
    solver_metadata: FrozenJsonObject = field(default_factory=FrozenJsonObject)

    def __post_init__(self) -> None:
        require_non_empty(self.case_id, "case_id")
        require_enum(self.outcome, PredictionOutcome, "prediction outcome")
        object.__setattr__(self, "values", tuple(self.values))
        for value in self.values:
            if not isinstance(value, PredictionValue):
                raise TypeError("values must contain PredictionValue objects")
        frozen_diagnostics = tuple(freeze_json(item) for item in self.diagnostics)
        object.__setattr__(self, "diagnostics", frozen_diagnostics)
        if not isinstance(self.solver_metadata, FrozenJsonObject):
            object.__setattr__(
                self, "solver_metadata", FrozenJsonObject(self.solver_metadata)
            )
        if self.outcome is PredictionOutcome.FAILURE:
            if self.values:
                raise InvariantViolationError(
                    "a FAILURE prediction must not contain values"
                )
            require_non_empty(self.failure_reason or "", "failure_reason")
        else:
            if not self.values:
                raise InvariantViolationError(
                    "a VALUE prediction must contain at least one value"
                )
            if self.failure_reason is not None:
                raise InvariantViolationError(
                    "a VALUE prediction must not contain a failure_reason"
                )


@dataclass(frozen=True, slots=True)
class DeclaredTolerance:
    """A cited, justified tolerance supplied by a later validation package."""

    quantity: ValidationQuantity
    value: float
    unit: str
    justification: str
    source_citation: str
    scope: str

    def __post_init__(self) -> None:
        require_enum(self.quantity, ValidationQuantity, "quantity")
        require_finite(self.value, "tolerance value")
        if self.value < 0.0:
            raise ValueError("tolerance value must be non-negative")
        object.__setattr__(self, "value", float(self.value))
        require_non_empty(self.unit, "unit")
        if self.unit != self.quantity.canonical_si_unit:
            raise ValueError("tolerance unit must be the quantity's canonical SI unit")
        require_non_empty(self.justification, "justification")
        require_non_empty(self.source_citation, "source_citation")
        require_non_empty(self.scope, "scope")


_UNCERTAINTY_STATUSES = frozenset(
    {
        ValidationStatus.AGREES_WITHIN_UNCERTAINTY,
        ValidationStatus.OUTSIDE_UNCERTAINTY,
    }
)
_TOLERANCE_STATUSES = frozenset(
    {
        ValidationStatus.AGREES_WITHIN_DECLARED_TOLERANCE,
        ValidationStatus.OUTSIDE_DECLARED_TOLERANCE,
    }
)


@dataclass(frozen=True, slots=True, init=False)
class ValidationRecord:
    """A dataset-bound case/prediction pairing with no computed error metrics."""

    case: ValidationCase = field(init=False)
    prediction: ValidationPrediction
    status: ValidationStatus = ValidationStatus.REPORTED_NO_TOLERANCE
    exclusion_reason: str | None = None
    declared_tolerance: DeclaredTolerance | None = None
    identity: DatasetIdentity = field(init=False)

    @property
    def data_class(self) -> DataClass:
        """Return the data class derived from the case's dataset identity."""

        return self.identity.data_class

    def __init__(
        self,
        case: ValidationCase,
        prediction: ValidationPrediction,
        status: ValidationStatus = ValidationStatus.REPORTED_NO_TOLERANCE,
        exclusion_reason: str | None = None,
        declared_tolerance: DeclaredTolerance | None = None,
    ) -> None:
        object.__setattr__(self, "case", case)
        object.__setattr__(self, "prediction", prediction)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "exclusion_reason", exclusion_reason)
        object.__setattr__(self, "declared_tolerance", declared_tolerance)
        self.__post_init__()

    def __post_init__(self) -> None:
        if not isinstance(self.case, ValidationCase):
            raise TypeError("case must be a ValidationCase")
        if not isinstance(self.prediction, ValidationPrediction):
            raise TypeError("prediction must be a ValidationPrediction")
        if self.prediction.case_id != self.case.case_id:
            raise InvariantViolationError("prediction case_id disagrees with case")
        require_enum(self.status, ValidationStatus, "validation status")
        object.__setattr__(self, "identity", self.case.identity)
        if self.prediction.outcome is PredictionOutcome.FAILURE:
            if self.status is not ValidationStatus.SOLVER_FAILURE:
                raise InvariantViolationError(
                    "a FAILURE prediction requires SOLVER_FAILURE status"
                )
        elif self.status is ValidationStatus.SOLVER_FAILURE:
            raise InvariantViolationError(
                "SOLVER_FAILURE status requires a FAILURE prediction"
            )
        if self.status is ValidationStatus.EXCLUDED:
            require_non_empty(self.exclusion_reason or "", "exclusion_reason")
        elif self.exclusion_reason is not None:
            raise InvariantViolationError(
                "exclusion_reason is only valid with EXCLUDED status"
            )
        if self.status in _TOLERANCE_STATUSES:
            if self.declared_tolerance is None:
                raise InvariantViolationError(
                    "declared-tolerance status requires a DeclaredTolerance"
                )
        elif self.declared_tolerance is not None:
            raise InvariantViolationError(
                "DeclaredTolerance is only valid with a declared-tolerance status"
            )
        if self.status in _UNCERTAINTY_STATUSES:
            if self.identity.data_class is not DataClass.EXPERIMENTAL_VALIDATION:
                raise InvariantViolationError(
                    "uncertainty status is only valid for experimental validation"
                )
            if not any(
                value.uncertainty is not None for value in self.case.reference_values
            ):
                raise InvariantViolationError(
                    "uncertainty status requires a source-reported uncertainty"
                )
        for value in self.prediction.values:
            _validate_mole_fraction_vector(value, self.case.component_ids)


@dataclass(frozen=True, slots=True)
class DatasetPin:
    """Dataset identity and source hashes pinned by a validation run."""

    identity: DatasetIdentity
    raw_sha256: str
    normalized_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.identity, DatasetIdentity):
            raise TypeError("identity must be a DatasetIdentity")
        object.__setattr__(self, "raw_sha256", normalize_sha256(self.raw_sha256))
        object.__setattr__(
            self, "normalized_sha256", normalize_sha256(self.normalized_sha256)
        )


@dataclass(frozen=True, slots=True)
class RunMetadata:
    """The intentionally volatile portion of a serialized run."""

    run_id: str
    timestamp_utc: datetime

    def __post_init__(self) -> None:
        require_non_empty(self.run_id, "run_id")
        if not isinstance(self.timestamp_utc, datetime):
            raise TypeError("timestamp_utc must be a datetime")
        if self.timestamp_utc.tzinfo is None:
            raise ValueError("timestamp_utc must be timezone-aware UTC")
        if self.timestamp_utc.utcoffset() != UTC.utcoffset(None):
            raise ValueError("timestamp_utc must use UTC")


@dataclass(frozen=True, slots=True)
class ValidationRun:
    """Deterministically ordered records and pinned reproduction inputs."""

    metadata: RunMetadata
    framework_schema_version: str
    openphase_package_version: str
    git_commit_sha: str
    python_version: str
    platform: str
    datasets: tuple[DatasetPin, ...]
    reproduction_command: str
    records: tuple[ValidationRecord, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.metadata, RunMetadata):
            raise TypeError("metadata must be RunMetadata")
        require_supported_schema_version(self.framework_schema_version)
        for field_name in (
            "openphase_package_version",
            "python_version",
            "platform",
            "reproduction_command",
        ):
            require_non_empty(getattr(self, field_name), field_name)
        require_non_empty(self.git_commit_sha, "git_commit_sha")
        if len(self.git_commit_sha) not in {40, 64} or any(
            character not in "0123456789abcdefABCDEF"
            for character in self.git_commit_sha
        ):
            raise ValueError("git_commit_sha must be a 40- or 64-character hex digest")
        datasets = tuple(self.datasets)
        for dataset in datasets:
            if not isinstance(dataset, DatasetPin):
                raise TypeError("datasets must contain DatasetPin objects")
        normalized_datasets = tuple(
            sorted(
                datasets,
                key=lambda item: (
                    item.identity.dataset_id,
                    item.identity.dataset_version,
                    item.identity.data_class.value,
                ),
            )
        )
        object.__setattr__(self, "datasets", normalized_datasets)
        identities = tuple(item.identity for item in self.datasets)
        records = tuple(self.records)
        for record in records:
            if not isinstance(record, ValidationRecord):
                raise TypeError("records must contain ValidationRecord objects")
        normalized_records = tuple(
            sorted(
                records,
                key=lambda item: (
                    item.case.case_id,
                    item.identity.dataset_id,
                    item.identity.dataset_version,
                ),
            )
        )
        object.__setattr__(self, "records", normalized_records)
        data_classes = {
            *(identity.data_class for identity in identities),
            *(record.identity.data_class for record in self.records),
        }
        if len(data_classes) > 1:
            labels = sorted(item.value for item in data_classes)
            raise MixedDataClassError(
                f"a ValidationRun cannot contain multiple data classes: {labels!r}"
            )
        dataset_keys = tuple(
            (item.dataset_id, item.dataset_version) for item in identities
        )
        if len(dataset_keys) != len(set(dataset_keys)):
            raise ValueError("dataset pins must be unique by dataset ID and version")
        for record in self.records:
            if record.identity not in identities:
                raise InvariantViolationError(
                    f"record {record.case.case_id!r} has no matching dataset pin"
                )
        case_keys = tuple(
            (record.case.case_id, record.identity) for record in self.records
        )
        if len(case_keys) != len(set(case_keys)):
            raise ValueError(
                "run records must be unique by dataset identity and case_id"
            )
