"""Isolated Module 17 legacy descriptive statistics, never modern agreement.

The historical 2U band below describes twice an already-expanded uncertainty.
It has no uncertainty-coverage interpretation and cannot enter modern aggregation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ._validation import require_non_empty
from .aggregates import (
    CoverageBlock,
    ExperimentalQuantityAggregate,
    GroupingKey,
    ObservationUnit,
    VectorReduction,
    aggregate_group,
)
from .comparisons import (
    CaseComparison,
    UncertaintyAssessment,
    UncertaintyDerivation,
    components,
)
from .enums import UncertaintyKind
from .exceptions import InvariantViolationError
from .json_values import JsonValue, freeze_json
from .metrics import MetricName
from .sensitivity import SubsetDefinition


@dataclass(frozen=True, slots=True)
class LegacyDescriptiveStatistics:
    grouping_key: GroupingKey
    coverage: CoverageBlock
    sample_count: int
    within_two_expanded_uncertainties_count: int
    label: str = "LEGACY DESCRIPTIVE STATISTICS: 2U band, not uncertainty agreement"

    def __post_init__(self) -> None:
        if (
            not 0
            <= self.within_two_expanded_uncertainties_count
            <= self.sample_count
            <= self.coverage.compared_cases
        ):
            raise InvariantViolationError("legacy descriptive counts do not reconcile")
        require_non_empty(self.label, "legacy descriptive label")


@dataclass(frozen=True, slots=True)
class LegacyDiscrepancy:
    identifier: str
    metric: str
    legacy_definition: str
    legacy_value: JsonValue
    new_definition: str
    new_value: JsonValue
    cause: str
    scientific_assessment: str
    changes_documented_conclusion: bool

    def __post_init__(self) -> None:
        for text in (
            self.identifier,
            self.metric,
            self.legacy_definition,
            self.new_definition,
            self.cause,
            self.scientific_assessment,
        ):
            require_non_empty(text, "legacy discrepancy provenance")
        object.__setattr__(self, "legacy_value", freeze_json(self.legacy_value))
        object.__setattr__(self, "new_value", freeze_json(self.new_value))


def legacy_descriptive_statistics(
    cases: tuple[CaseComparison, ...], aggregate: ExperimentalQuantityAggregate
) -> LegacyDescriptiveStatistics:
    """Reproduce the historical residual <= 2 count only in this legacy type."""
    if not aggregate.grouping_key.identity.dataset_id.startswith(
        "may_et_al_2015_thermoml:"
    ):
        raise ValueError("legacy descriptive path is Module 17 only")
    if (
        aggregate_group(
            cases,
            aggregate.grouping_key,
            aggregate.observation_unit,
            aggregate.reduction,
        )
        != aggregate
    ):
        raise InvariantViolationError(
            "legacy statistics must use the aggregate's cases"
        )
    available = within = 0
    for case in cases:
        if case.excluded:
            continue
        for q in case.quantity_comparisons:
            if q.key != aggregate.grouping_key.comparison_key:
                continue
            a = q.uncertainty_assessment
            if not isinstance(a, UncertaintyAssessment):
                continue
            if (
                a.applied.kind_used is not UncertaintyKind.EXPANDED
                or a.applied.derivation is not UncertaintyDerivation.PUBLISHED
            ):
                raise ValueError("legacy Module 17 band requires published expanded U")
            assert a.expanded_normalized_residual is not None
            available += 1
            within += int(
                max(abs(v) for v in components(a.expanded_normalized_residual)) <= 2
            )
    return LegacyDescriptiveStatistics(
        aggregate.grouping_key, aggregate.coverage, available, within
    )


def module17_discrepancies(
    cases: tuple[CaseComparison, ...], composition: ExperimentalQuantityAggregate
) -> tuple[LegacyDiscrepancy, ...]:
    """Surface LD-1 framing, LD-2 observation units and LD-3 failure accounting."""
    legacy = legacy_descriptive_statistics(cases, composition)
    per_case = aggregate_group(
        cases,
        composition.grouping_key,
        ObservationUnit.PER_CASE_VECTOR,
        VectorReduction.MEAN_ABS_COMPONENT,
    )
    old = next(m for m in composition.metrics if m.name is MetricName.MAE)
    new = next(m for m in per_case.metrics if m.name is MetricName.MAE)
    c = composition.coverage
    return (
        LegacyDiscrepancy(
            "LD-1",
            "within-two expanded uncertainties",
            "abs(error/U) <= 2 for published expanded U",
            legacy.within_two_expanded_uncertainties_count,
            "No modern uncertainty-agreement statistic for a 2U band",
            None,
            "Historical descriptive band exceeds the published uncertainty band.",
            "Framing distinction only; the legacy count remains"
            " reproducible and labelled.",
            False,
        ),
        LegacyDiscrepancy(
            "LD-2",
            "composition MAE",
            "PER_COMPONENT, flattened components",
            freeze_json({"value": old.value, "sample_count": old.sample_count}),
            "PER_CASE_VECTOR, MEAN_ABS_COMPONENT",
            freeze_json({"value": new.value, "sample_count": new.sample_count}),
            "Binary component errors are correlated;"
            " these are distinct observation units.",
            "Both statistics are exposed; rounding differences"
            " do not alter documented conclusions.",
            False,
        ),
        LegacyDiscrepancy(
            "LD-3",
            "failure_count",
            "not_found + inconclusive + other_failure",
            c.not_found + c.inconclusive + c.other_failure,
            "Separate structured solver outcomes",
            freeze_json(
                {
                    "not_found": c.not_found,
                    "inconclusive": c.inconclusive,
                    "other_failure": c.other_failure,
                }
            ),
            "Legacy failure_count merged distinct numerical outcomes.",
            "Additive decomposition preserves coverage"
            " and makes no physical non-existence claim.",
            False,
        ),
    )


def module17_anomaly_subset(repository_root: str | Path) -> SubsetDefinition:
    """Read the source's anomaly reason; select cases solely by stable identity."""
    source = "data/experimental/may_2015_source_manifest.json"
    manifest = json.loads((Path(repository_root) / source).read_text(encoding="utf-8"))
    reasons = manifest["source_anomalies"]
    if (
        not isinstance(reasons, list)
        or len(reasons) != 1
        or not isinstance(reasons[0], str)
    ):
        raise ValueError(
            "Module 17 anomaly provenance changed; explicit review required"
        )
    return SubsetDefinition(
        "module17_ch4_c3_source_anomaly",
        ("may2015_ch4_c3_023::bubble_point", "may2015_ch4_c3_023::dew_point"),
        "ch4_c3",
        reasons[0],
        source,
    )
