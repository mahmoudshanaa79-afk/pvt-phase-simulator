"""Identity-defined alternate views that retain the primary scientific result."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from ._validation import require_enum, require_non_empty
from .aggregates import QuantityAggregate, aggregate_group
from .comparisons import CaseComparison, Reason
from .exceptions import InvariantViolationError
from .metrics import MetricName, MetricState


@dataclass(frozen=True, slots=True)
class SubsetDefinition:
    subset_id: str
    excluded_case_ids: tuple[str, ...]
    scope_system: str
    reason: str
    source: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "excluded_case_ids", tuple(self.excluded_case_ids))
        for value in (self.subset_id, self.scope_system, self.reason, self.source):
            require_non_empty(value, "subset provenance")
        if not self.excluded_case_ids or len(set(self.excluded_case_ids)) != len(
            self.excluded_case_ids
        ):
            raise ValueError("subset requires unique excluded case identities")
        for identity in self.excluded_case_ids:
            require_non_empty(identity, "excluded case identity")


@dataclass(frozen=True, slots=True)
class MetricShift:
    metric: MetricName
    value: float | None
    reason: Reason | None = None

    def __post_init__(self) -> None:
        require_enum(self.metric, MetricName, "metric")
        if self.reason is not None:
            require_enum(self.reason, Reason, "reason")
        if (self.value is None) != (self.reason is not None):
            raise InvariantViolationError("undefined shifts require a reason")
        if self.value is not None and not isfinite(self.value):
            raise ValueError("shift must be finite")


@dataclass(frozen=True, slots=True)
class SensitivityAnalysis:
    primary: QuantityAggregate
    alternate: QuantityAggregate
    subset: SubsetDefinition
    shifts: tuple[MetricShift, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "shifts", tuple(self.shifts))
        if self.primary.grouping_key != self.alternate.grouping_key:
            raise InvariantViolationError(
                "sensitivity cannot change scientific grouping"
            )
        if (
            self.primary.observation_unit != self.alternate.observation_unit
            or self.primary.reduction != self.alternate.reduction
        ):
            raise InvariantViolationError(
                "sensitivity cannot change observation semantics"
            )
        if self.primary.grouping_key.system_id != self.subset.scope_system:
            raise InvariantViolationError("subset scope disagrees with aggregate")
        if self.alternate.coverage.total_cases > self.primary.coverage.total_cases:
            raise InvariantViolationError("alternate cannot add cases")
        if self.shifts != _shifts(self.primary, self.alternate):
            raise InvariantViolationError("shifts must equal alternate minus primary")


def _shifts(
    primary: QuantityAggregate, alternate: QuantityAggregate
) -> tuple[MetricShift, ...]:
    if tuple(m.name for m in primary.metrics) != tuple(
        m.name for m in alternate.metrics
    ):
        raise InvariantViolationError("sensitivity metric sets differ")
    result = []
    for p, a in zip(primary.metrics, alternate.metrics, strict=True):
        if p.state is MetricState.DEFINED and a.state is MetricState.DEFINED:
            assert p.value is not None and a.value is not None
            shift = a.value - p.value
            result.append(
                MetricShift(
                    p.name,
                    shift if isfinite(shift) else None,
                    None if isfinite(shift) else Reason.NON_FINITE_RESULT,
                )
            )
        else:
            result.append(MetricShift(p.name, None, a.reason or p.reason))
    return tuple(result)


def analyze_sensitivity(
    cases: tuple[CaseComparison, ...],
    primary: QuantityAggregate,
    subset: SubsetDefinition,
) -> SensitivityAnalysis:
    """Preserve the full-dataset result and select the alternate by identity only."""
    full = aggregate_group(
        cases, primary.grouping_key, primary.observation_unit, primary.reduction
    )
    if full != primary:
        raise InvariantViolationError(
            "primary must be the supplied full-dataset aggregate"
        )
    selected = tuple(
        c
        for c in cases
        if not (
            c.system_id == subset.scope_system and c.case_id in subset.excluded_case_ids
        )
    )
    alternate = aggregate_group(
        selected, primary.grouping_key, primary.observation_unit, primary.reduction
    )
    return SensitivityAnalysis(primary, alternate, subset, _shifts(primary, alternate))
