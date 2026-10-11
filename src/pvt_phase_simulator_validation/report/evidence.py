"""Assemble professor-facing evidence exclusively from A/B/C public objects."""

from __future__ import annotations

import platform
import subprocess
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from types import MappingProxyType

from pvt_phase_simulator.component_database import get_component
from pvt_phase_simulator.eos.mixing_rules import BinaryInteractionPolicy
from pvt_phase_simulator.eos.peng_robinson import (
    PENG_ROBINSON_OMEGA_A,
    PENG_ROBINSON_OMEGA_B,
    calculate_kappa,
)
from pvt_phase_simulator_validation.aggregates import (
    ExperimentalQuantityAggregate,
    ObservationUnit,
    VectorReduction,
)
from pvt_phase_simulator_validation.aggregation import aggregate_experimental_accuracy
from pvt_phase_simulator_validation.comparisons import (
    CaseComparison,
    SolverOutcome,
    compare_record,
)
from pvt_phase_simulator_validation.enums import (
    CapabilityUnderTest,
    DataClass,
    PredictionOutcome,
    ValidationQuantity,
    ValidationStatus,
)
from pvt_phase_simulator_validation.json_values import JsonValue
from pvt_phase_simulator_validation.models import (
    SCHEMA_VERSION,
    DatasetIdentity,
    DatasetPin,
    PredictionValue,
    ReferenceDataset,
    ReferenceValue,
)
from pvt_phase_simulator_validation.module17_adapter import (
    Module17Adaptation,
    load_module17_validation_evidence,
)
from pvt_phase_simulator_validation.module17_legacy import (
    LegacyDescriptiveStatistics,
    LegacyDiscrepancy,
    legacy_descriptive_statistics,
    module17_anomaly_subset,
    module17_discrepancies,
)
from pvt_phase_simulator_validation.sensitivity import (
    SensitivityAnalysis,
    SubsetDefinition,
    analyze_sensitivity,
)

from .declarations import EvidenceDeclaration, load_declaration
from .membership import (
    AggregateMembership,
    EvidenceInconsistencyError,
    prove_aggregate_membership,
)

REPORT_FORMAT = "openphase.validation_evidence"
REPORT_SCHEMA_VERSION = "1.0.0"


class UnsupportedDataClassError(ValueError):
    """D v1 intentionally refuses cross-check or mixed-class evidence."""


@dataclass(frozen=True, slots=True)
class ProductionCase:
    dataset_id: str
    dataset_version: str
    data_class: DataClass
    capability: CapabilityUnderTest
    case_id: str
    system_id: str
    component_ids: tuple[str, ...]
    source_reference: str
    specified_conditions: tuple[ReferenceValue, ...]
    reference_values: tuple[ReferenceValue, ...]
    prediction_outcome: PredictionOutcome
    prediction_values: tuple[PredictionValue, ...]
    failure_reason: str | None
    validation_status: ValidationStatus
    exclusion_reason: str | None
    solver_outcome: SolverOutcome


@dataclass(frozen=True, slots=True)
class AggregateEvidence:
    aggregate: ExperimentalQuantityAggregate
    membership: AggregateMembership


@dataclass(frozen=True, slots=True)
class ProductionEvidence:
    cases: tuple[ProductionCase, ...]
    comparisons: tuple[CaseComparison, ...]
    aggregates: tuple[AggregateEvidence, ...]
    vector_aggregates: tuple[AggregateEvidence, ...]
    pooled_coverage: tuple[ExperimentalQuantityAggregate, ...]


@dataclass(frozen=True, slots=True)
class DiagnosticCase:
    case_id: str
    capability: CapabilityUnderTest
    diagnostics: tuple[JsonValue, ...]


@dataclass(frozen=True, slots=True)
class DiagnosticEvidence:
    interpretation: MappingProxyType[str, JsonValue]
    cases: tuple[DiagnosticCase, ...]


@dataclass(frozen=True, slots=True)
class ComponentConfiguration:
    component_id: str
    name: str
    critical_temperature_k: float
    critical_pressure_pa: float
    acentric_factor: float
    kappa: float
    provenance: MappingProxyType[str, object]


@dataclass(frozen=True, slots=True)
class ModelConfiguration:
    eos: str
    omega_a: float
    omega_b: float
    kappa_expression: str
    mixing_rule: str
    binary_interaction_policy: str
    prediction_artifact_introduced_revision: str
    generating_revision_embedded: bool
    components: tuple[ComponentConfiguration, ...]
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReproducibilityEvidence:
    git_commit_sha: str
    tree_state: str
    package_version: str
    framework_schema_version: str
    python_version: str
    platform: str
    dataset_pins: tuple[DatasetPin, ...]
    reproduction_command: str


@dataclass(frozen=True, slots=True)
class VolatileMetadata:
    run_id: str
    generated_at_utc: datetime


@dataclass(frozen=True, slots=True)
class LegacyEvidence:
    descriptive_statistics: tuple[LegacyDescriptiveStatistics, ...]
    discrepancies: tuple[LegacyDiscrepancy, ...]


@dataclass(frozen=True, slots=True)
class ValidationEvidence:
    format: str
    schema_version: str
    volatile: VolatileMetadata
    declaration: EvidenceDeclaration
    datasets: tuple[ReferenceDataset, ...]
    production: ProductionEvidence
    diagnostics: DiagnosticEvidence
    model_configuration: ModelConfiguration
    sensitivity: tuple[SensitivityAnalysis, ...]
    sensitivity_subset: SubsetDefinition
    legacy: LegacyEvidence
    reproducibility: ReproducibilityEvidence
    repository_root: Path = field(repr=False, compare=False)


def _package_version() -> str:
    try:
        return version("pvt-phase-simulator")
    except PackageNotFoundError:
        return "UNKNOWN"


def _git_value(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def _revision(root: Path) -> tuple[str, str]:
    try:
        commit = _git_value(root, "rev-parse", "HEAD")
        state = "CLEAN" if not _git_value(root, "status", "--porcelain=v1") else "DIRTY"
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN", "UNKNOWN"
    return commit, state


def _as_tuple_of_text(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise EvidenceInconsistencyError(f"declaration {field} must be a text array")
    return tuple(value)


def _declared_number(item: dict[str, object], field: str) -> float:
    value = item.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceInconsistencyError(f"declared {field} must be numeric")
    return float(value)


def _root_number(item: dict[str, object], field: str) -> float:
    return _declared_number(item, field)


def _model_configuration(declaration: EvidenceDeclaration) -> ModelConfiguration:
    raw = dict(declaration.model_configuration)
    if (
        _root_number(raw, "omega_a") != PENG_ROBINSON_OMEGA_A
        or _root_number(raw, "omega_b") != PENG_ROBINSON_OMEGA_B
    ):
        raise EvidenceInconsistencyError(
            "declared Peng-Robinson constants differ from the engine"
        )
    if raw["binary_interaction_policy"] != BinaryInteractionPolicy.DEFAULT_ZERO.value:
        raise EvidenceInconsistencyError(
            "declared binary-interaction policy differs from the engine"
        )
    raw_components = raw["components"]
    if not isinstance(raw_components, list):
        raise EvidenceInconsistencyError("declared components must be a list")
    components: list[ComponentConfiguration] = []
    for raw_component in raw_components:
        if not isinstance(raw_component, dict):
            raise EvidenceInconsistencyError("declared component must be an object")
        item = {str(key): value for key, value in raw_component.items()}
        identifier = str(item["component_id"])
        component = get_component(identifier)
        actual = (
            component.critical_temperature_k,
            component.critical_pressure_pa,
            component.acentric_factor,
            calculate_kappa(component.acentric_factor),
        )
        declared = tuple(
            _declared_number(item, field)
            for field in (
                "critical_temperature_k",
                "critical_pressure_pa",
                "acentric_factor",
                "kappa",
            )
        )
        if declared != actual:
            raise EvidenceInconsistencyError(
                f"declared model properties for {identifier} differ from the engine"
            )
        provenance = (
            {}
            if component.provenance is None
            else component.provenance.model_dump(mode="json")
        )
        components.append(
            ComponentConfiguration(
                identifier,
                component.name,
                *actual,
                MappingProxyType(provenance),
            )
        )
    return ModelConfiguration(
        str(raw["eos"]),
        PENG_ROBINSON_OMEGA_A,
        PENG_ROBINSON_OMEGA_B,
        str(raw["kappa_expression"]),
        str(raw["mixing_rule"]),
        BinaryInteractionPolicy.DEFAULT_ZERO.value,
        str(raw["prediction_artifact_introduced_revision"]),
        bool(raw["generating_revision_embedded"]),
        tuple(components),
        _as_tuple_of_text(raw["evidence"], "model_configuration.evidence"),
    )


def _group(
    comparisons: tuple[CaseComparison, ...], aggregate: ExperimentalQuantityAggregate
) -> tuple[CaseComparison, ...]:
    key = aggregate.grouping_key
    return tuple(
        case
        for case in comparisons
        if case.identity == key.identity
        and case.capability == key.capability
        and (key.pooled_across_systems or case.system_id == key.system_id)
    )


def _validate_data_class(adaptation: Module17Adaptation) -> None:
    classes = {
        *(dataset.identity.data_class for dataset in adaptation.datasets),
        *(record.identity.data_class for record in adaptation.records),
    }
    if classes != {DataClass.EXPERIMENTAL_VALIDATION}:
        raise UnsupportedDataClassError(
            "validation evidence report v1 accepts EXPERIMENTAL_VALIDATION only"
        )


def _build_production(
    adaptation: Module17Adaptation,
) -> tuple[ProductionEvidence, tuple[CaseComparison, ...]]:
    capabilities = {
        dataset.identity: dataset.capability for dataset in adaptation.datasets
    }
    comparisons = tuple(
        compare_record(record, capabilities[record.identity])
        for record in adaptation.records
    )
    default = aggregate_experimental_accuracy(comparisons).accuracy_aggregates
    vector = aggregate_experimental_accuracy(
        comparisons,
        vector_observation_unit=ObservationUnit.PER_CASE_VECTOR,
        reduction=VectorReduction.MEAN_ABS_COMPONENT,
    ).accuracy_aggregates
    pooled = aggregate_experimental_accuracy(
        comparisons, pooled_across_systems=True
    ).accuracy_aggregates
    aggregates = tuple(
        AggregateEvidence(item, prove_aggregate_membership(comparisons, item))
        for item in default
    )
    vector_aggregates = tuple(
        AggregateEvidence(item, prove_aggregate_membership(comparisons, item))
        for item in vector
        if item.observation_unit is ObservationUnit.PER_CASE_VECTOR
    )
    production_cases = []
    by_case = {comparison.case_id: comparison for comparison in comparisons}
    for record in adaptation.records:
        capability = capabilities[record.identity]
        comparison = by_case[record.case.case_id]
        production_cases.append(
            ProductionCase(
                record.identity.dataset_id,
                record.identity.dataset_version,
                record.data_class,
                capability,
                record.case.case_id,
                record.case.system_id,
                record.case.component_ids,
                record.case.source_reference,
                record.case.specified_conditions,
                record.case.reference_values,
                record.prediction.outcome,
                record.prediction.values,
                record.prediction.failure_reason,
                record.status,
                record.exclusion_reason,
                comparison.solver_outcome,
            )
        )
    ordered_cases = tuple(sorted(production_cases, key=lambda item: item.case_id))
    return (
        ProductionEvidence(
            ordered_cases,
            tuple(sorted(comparisons, key=lambda item: item.case_id)),
            aggregates,
            vector_aggregates,
            tuple(item for item in pooled if item.grouping_key.pooled_across_systems),
        ),
        comparisons,
    )


def _legacy(
    comparisons: tuple[CaseComparison, ...], production: ProductionEvidence
) -> LegacyEvidence:
    statistics: list[LegacyDescriptiveStatistics] = []
    discrepancies: list[LegacyDiscrepancy] = []
    for item in production.aggregates:
        aggregate = item.aggregate
        cases = _group(comparisons, aggregate)
        statistics.append(legacy_descriptive_statistics(cases, aggregate))
        if (
            aggregate.grouping_key.comparison_key.quantity
            is ValidationQuantity.MOLE_FRACTION
        ):
            discrepancies.extend(module17_discrepancies(cases, aggregate))
    return LegacyEvidence(tuple(statistics), tuple(discrepancies))


def _sensitivity(
    root: Path,
    comparisons: tuple[CaseComparison, ...],
    production: ProductionEvidence,
) -> tuple[SubsetDefinition, tuple[SensitivityAnalysis, ...]]:
    subset = module17_anomaly_subset(root)
    analyses: list[SensitivityAnalysis] = []
    for item in production.aggregates:
        aggregate = item.aggregate
        key = aggregate.grouping_key
        if (
            key.system_id == subset.scope_system
            and key.comparison_key.quantity is ValidationQuantity.PRESSURE
        ):
            analyses.append(
                analyze_sensitivity(_group(comparisons, aggregate), aggregate, subset)
            )
    return subset, tuple(analyses)


def _diagnostics(
    adaptation: Module17Adaptation,
    capabilities: dict[DatasetIdentity, CapabilityUnderTest],
) -> DiagnosticEvidence:
    cases = tuple(
        DiagnosticCase(
            record.case.case_id,
            capabilities[record.identity],
            record.prediction.diagnostics,
        )
        for record in adaptation.records
        if record.prediction.diagnostics
    )
    return DiagnosticEvidence(
        MappingProxyType(dict(adaptation.interpretation)),
        tuple(sorted(cases, key=lambda item: item.case_id)),
    )


def build_validation_evidence(
    repository_root: str | Path,
    *,
    dataset: str = "module17",
    run_id: str | None = None,
    clock: Callable[[], datetime] | None = None,
) -> ValidationEvidence:
    """Build D evidence without recomputing or changing A/B/C science."""

    if dataset != "module17":
        raise ValueError(f"unsupported report dataset {dataset!r}")
    root = Path(repository_root).resolve()
    declaration = load_declaration(dataset)
    adaptation = load_module17_validation_evidence(root)
    _validate_data_class(adaptation)
    production, comparisons = _build_production(adaptation)
    if len(production.cases) != len(adaptation.records):
        raise EvidenceInconsistencyError(
            "case ledger does not preserve every adapter record"
        )
    subset, sensitivity = _sensitivity(root, comparisons, production)
    capabilities = {item.identity: item.capability for item in adaptation.datasets}
    generated = (clock or (lambda: datetime.now(UTC)))()
    if generated.tzinfo is None:
        raise ValueError("clock must return a timezone-aware datetime")
    generated = generated.astimezone(UTC)
    commit, tree_state = _revision(root)
    pins = tuple(
        DatasetPin(
            item.identity,
            item.source_manifest.raw_sha256,
            item.source_manifest.normalized_sha256,
        )
        for item in adaptation.datasets
    )
    reproducibility = ReproducibilityEvidence(
        commit,
        tree_state,
        _package_version(),
        SCHEMA_VERSION,
        platform.python_version(),
        f"{platform.system()} {platform.machine()}",
        tuple(sorted(pins, key=lambda item: item.identity.dataset_id)),
        "python -m pvt_phase_simulator_validation.report --output <directory>",
    )
    return ValidationEvidence(
        REPORT_FORMAT,
        REPORT_SCHEMA_VERSION,
        VolatileMetadata(run_id or uuid.uuid4().hex, generated),
        declaration,
        adaptation.datasets,
        production,
        _diagnostics(adaptation, capabilities),
        _model_configuration(declaration),
        sensitivity,
        subset,
        _legacy(comparisons, production),
        reproducibility,
        root,
    )
