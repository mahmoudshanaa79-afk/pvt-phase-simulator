"""Type-separated, data-class-homogeneous summary containers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

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
    """Experimental records available for later accuracy calculations."""

    accuracy_records: tuple[ValidationRecord, ...]

    def __post_init__(self) -> None:
        records = tuple(self.accuracy_records)
        object.__setattr__(self, "accuracy_records", records)
        data_class = homogeneous_data_class(records)
        if data_class is not DataClass.EXPERIMENTAL_VALIDATION:
            raise MixedDataClassError(
                "ExperimentalAccuracySummary accepts only "
                "EXPERIMENTAL_VALIDATION records"
            )


@dataclass(frozen=True, slots=True)
class CrossCheckAgreementSummary:
    """Numerical cross-check records available for later agreement calculations."""

    agreement_records: tuple[ValidationRecord, ...]

    def __post_init__(self) -> None:
        records = tuple(self.agreement_records)
        object.__setattr__(self, "agreement_records", records)
        data_class = homogeneous_data_class(records)
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
