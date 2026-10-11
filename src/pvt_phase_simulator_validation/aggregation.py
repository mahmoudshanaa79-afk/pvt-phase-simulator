"""Type-separated, data-class-homogeneous summary containers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .aggregates import (
    ExperimentalQuantityAggregate,
    GroupingKey,
    ObservationUnit,
    QuantityAggregate,
    VectorReduction,
    aggregate_group,
)
from .comparisons import CaseComparison
from .enums import DataClass
from .exceptions import MixedDataClassError
from .models import ValidationRecord


def homogeneous_data_class(records: Iterable[ValidationRecord]) -> DataClass:
    """Return the sole data class in a non-empty collection.

    This is a structural precondition for every aggregation entry point. It returns
    the class, never an accuracy verdict.
    """

    materialized = tuple(records)
    if not materialized:
        raise ValueError("cannot aggregate an empty record collection")
    for record in materialized:
        if not isinstance(record, ValidationRecord):
            raise TypeError("aggregation inputs must be ValidationRecord objects")
    classes = {record.identity.data_class for record in materialized}
    if len(classes) != 1:
        labels = sorted(item.value for item in classes)
        raise MixedDataClassError(
            f"records from multiple data classes cannot be aggregated: {labels!r}"
        )
    return next(iter(classes))


@dataclass(frozen=True, slots=True)
class ExperimentalAccuracySummary:
    """Experimental error, accuracy and reference-uncertainty agreement."""

    accuracy_records: tuple[ValidationRecord, ...]
    accuracy_aggregates: tuple[ExperimentalQuantityAggregate, ...] = ()

    def __post_init__(self) -> None:
        aggregates = tuple(self.accuracy_aggregates)
        if any(
            not isinstance(a, ExperimentalQuantityAggregate)
            or a.grouping_key.identity.data_class
            is not DataClass.EXPERIMENTAL_VALIDATION
            for a in aggregates
        ):
            raise MixedDataClassError("accuracy aggregates must be experimental")
        object.__setattr__(self, "accuracy_aggregates", aggregates)
        records = tuple(self.accuracy_records)
        object.__setattr__(self, "accuracy_records", records)
        data_class = (
            homogeneous_data_class(records)
            if records
            else DataClass.EXPERIMENTAL_VALIDATION
        )
        if data_class is not DataClass.EXPERIMENTAL_VALIDATION:
            raise MixedDataClassError(
                "ExperimentalAccuracySummary accepts only "
                "EXPERIMENTAL_VALIDATION records"
            )


@dataclass(frozen=True, slots=True)
class CrossCheckAgreementSummary:
    """Numerical differences and model-to-model discrepancy."""

    agreement_records: tuple[ValidationRecord, ...]
    agreement_aggregates: tuple[QuantityAggregate, ...] = ()

    def __post_init__(self) -> None:
        aggregates = tuple(self.agreement_aggregates)
        if any(
            type(a) is not QuantityAggregate
            or a.grouping_key.identity.data_class is not DataClass.NUMERICAL_CROSS_CHECK
            for a in aggregates
        ):
            raise MixedDataClassError(
                "agreement aggregates must be numerical cross-checks"
            )
        object.__setattr__(self, "agreement_aggregates", aggregates)
        records = tuple(self.agreement_records)
        object.__setattr__(self, "agreement_records", records)
        data_class = (
            homogeneous_data_class(records)
            if records
            else DataClass.NUMERICAL_CROSS_CHECK
        )
        if data_class is not DataClass.NUMERICAL_CROSS_CHECK:
            raise MixedDataClassError(
                "CrossCheckAgreementSummary accepts only NUMERICAL_CROSS_CHECK records"
            )


def summarize_experimental_accuracy(
    records: Iterable[ValidationRecord],
) -> ExperimentalAccuracySummary:
    """Build the experimental-only summary type."""

    materialized = tuple(records)
    homogeneous_data_class(materialized)
    return ExperimentalAccuracySummary(materialized)


def summarize_cross_check_agreement(
    records: Iterable[ValidationRecord],
) -> CrossCheckAgreementSummary:
    """Build the numerical-cross-check-only summary type."""

    materialized = tuple(records)
    homogeneous_data_class(materialized)
    return CrossCheckAgreementSummary(materialized)


def _aggregate_comparisons(
    cases: Iterable[CaseComparison],
    expected: DataClass,
    *,
    pooled_across_systems: bool = False,
    vector_observation_unit: ObservationUnit = ObservationUnit.PER_COMPONENT,
    reduction: VectorReduction | None = None,
) -> tuple[QuantityAggregate, ...]:
    materialized = tuple(cases)
    if any(not isinstance(c, CaseComparison) for c in materialized):
        raise TypeError("modern aggregation accepts CaseComparison only")
    if any(c.identity.data_class is not expected for c in materialized):
        raise MixedDataClassError("aggregate input has an incompatible data class")
    keys = {
        GroupingKey(c.identity, c.system_id, c.capability, q.key)
        for c in materialized
        for q in c.quantity_comparisons
    }
    if pooled_across_systems:
        keys |= {
            GroupingKey(k.identity, None, k.capability, k.comparison_key, True)
            for k in tuple(keys)
        }
    results = []
    for key in sorted(keys, key=repr):
        group = tuple(
            c
            for c in materialized
            if c.identity == key.identity
            and c.capability == key.capability
            and (key.pooled_across_systems or c.system_id == key.system_id)
        )
        vector = any(
            q.component_ids is not None
            for c in group
            for q in c.quantity_comparisons
            if q.key == key.comparison_key
        )
        unit = vector_observation_unit if vector else ObservationUnit.PER_CASE_SCALAR
        results.append(aggregate_group(group, key, unit, reduction if vector else None))
    return tuple(results)


def aggregate_experimental_accuracy(
    cases: Iterable[CaseComparison],
    *,
    pooled_across_systems: bool = False,
    vector_observation_unit: ObservationUnit = ObservationUnit.PER_COMPONENT,
    reduction: VectorReduction | None = None,
) -> ExperimentalAccuracySummary:
    """Experimental error, accuracy and reference-uncertainty agreement."""
    aggregates = _aggregate_comparisons(
        cases,
        DataClass.EXPERIMENTAL_VALIDATION,
        pooled_across_systems=pooled_across_systems,
        vector_observation_unit=vector_observation_unit,
        reduction=reduction,
    )
    experimental = tuple(
        a for a in aggregates if isinstance(a, ExperimentalQuantityAggregate)
    )
    return ExperimentalAccuracySummary((), experimental)


def aggregate_cross_check_agreement(
    cases: Iterable[CaseComparison],
    *,
    pooled_across_systems: bool = False,
    vector_observation_unit: ObservationUnit = ObservationUnit.PER_COMPONENT,
    reduction: VectorReduction | None = None,
) -> CrossCheckAgreementSummary:
    """Numerical difference and model-to-model discrepancy, never experimental truth."""
    return CrossCheckAgreementSummary(
        (),
        _aggregate_comparisons(
            cases,
            DataClass.NUMERICAL_CROSS_CHECK,
            pooled_across_systems=pooled_across_systems,
            vector_observation_unit=vector_observation_unit,
            reduction=reduction,
        ),
    )
