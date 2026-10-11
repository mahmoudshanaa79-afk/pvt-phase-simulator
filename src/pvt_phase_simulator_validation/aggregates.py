"""Explicit observation units, coverage accounting and scientific grouping."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import fsum, isfinite, sqrt

from ._validation import require_enum
from .comparisons import (
    Agreement,
    CaseComparison,
    ComparisonKey,
    ComparisonState,
    Reason,
    SolverOutcome,
    UncertaintyAssessment,
    UncertaintyDerivation,
    UndefinedMetric,
    components,
)
from .enums import CapabilityUnderTest, DataClass, UncertaintyKind
from .exceptions import (
    ComparisonAlignmentError,
    InvariantViolationError,
    MixedDataClassError,
)
from .metrics import METRIC_POLICY, MetricName, MetricState
from .models import DatasetIdentity


class ObservationUnit(StrEnum):
    PER_CASE_SCALAR = "PER_CASE_SCALAR"
    PER_COMPONENT = "PER_COMPONENT"
    PER_CASE_VECTOR = "PER_CASE_VECTOR"


class VectorReduction(StrEnum):
    MAX_ABS_COMPONENT = "MAX_ABS_COMPONENT"
    MEAN_ABS_COMPONENT = "MEAN_ABS_COMPONENT"


@dataclass(frozen=True, slots=True)
class CoverageBlock:
    total_cases: int
    excluded_cases: int
    eligible_cases: int
    reference_available_cases: int
    converged: int
    not_found: int
    inconclusive: int
    other_failure: int
    compared_cases: int
    metric_observation_count: int
    uncertainty_assessable_count: int

    def __post_init__(self) -> None:
        from dataclasses import fields

        if any(
            type(getattr(self, f.name)) is not int or getattr(self, f.name) < 0
            for f in fields(self)
        ):
            raise InvariantViolationError(
                "coverage counts must be non-negative integers"
            )
        if self.eligible_cases != self.total_cases - self.excluded_cases:
            raise InvariantViolationError(
                "eligible_cases must equal total minus excluded"
            )
        if (
            self.converged + self.not_found + self.inconclusive + self.other_failure
            != self.eligible_cases
        ):
            raise InvariantViolationError(
                "solver counts must reconcile with eligible cases"
            )
        if self.compared_cases > min(self.converged, self.reference_available_cases):
            raise InvariantViolationError(
                "compared_cases exceeds available converged cases"
            )
        if (
            self.reference_available_cases > self.total_cases
            or self.uncertainty_assessable_count > self.compared_cases
        ):
            raise InvariantViolationError("coverage availability exceeds cases")


@dataclass(frozen=True, slots=True)
class GroupingKey:
    identity: DatasetIdentity
    system_id: str | None
    capability: CapabilityUnderTest
    comparison_key: ComparisonKey
    pooled_across_systems: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.identity, DatasetIdentity) or not isinstance(
            self.comparison_key, ComparisonKey
        ):
            raise TypeError("grouping requires dataset identity and ComparisonKey")
        require_enum(self.capability, CapabilityUnderTest, "capability")
        if self.pooled_across_systems != (self.system_id is None):
            raise InvariantViolationError("pooled grouping must be separately labelled")


@dataclass(frozen=True, slots=True)
class MetricResult:
    name: MetricName
    state: MetricState
    value: float | None
    unit: str
    sample_count: int
    coverage: CoverageBlock
    reason: Reason | None = None

    def __post_init__(self) -> None:
        require_enum(self.name, MetricName, "metric name")
        require_enum(self.state, MetricState, "metric state")
        if (
            self.sample_count < 0
            or self.sample_count > self.coverage.metric_observation_count
        ):
            raise InvariantViolationError(
                "metric sample_count inconsistent with coverage"
            )
        if self.state is MetricState.DEFINED:
            if (
                self.value is None
                or not isfinite(self.value)
                or self.sample_count == 0
                or self.reason is not None
            ):
                raise InvariantViolationError(
                    "defined metrics require finite values and observations"
                )
        elif self.value is not None or self.reason is None:
            raise InvariantViolationError(
                "undefined metrics require a reason and no value"
            )
        if self.reason is not None:
            require_enum(self.reason, Reason, "reason")


@dataclass(frozen=True, slots=True)
class UncertaintyAgreementCount:
    kind_used: UncertaintyKind
    derivation: UncertaintyDerivation
    coverage_factor: float | None
    confidence_level_percent: float | None
    assessable_count: int
    within_count: int
    outside_count: int

    def __post_init__(self) -> None:
        require_enum(self.kind_used, UncertaintyKind, "kind_used")
        require_enum(self.derivation, UncertaintyDerivation, "derivation")
        if self.coverage_factor is not None and (
            not isfinite(self.coverage_factor) or self.coverage_factor <= 0
        ):
            raise ValueError("coverage_factor must be finite and positive")
        if self.confidence_level_percent is not None and (
            not isfinite(self.confidence_level_percent)
            or not 0 <= self.confidence_level_percent <= 100
        ):
            raise ValueError("invalid confidence level")
        if self.derivation is UncertaintyDerivation.EXPANDED_FROM_STANDARD and (
            self.kind_used is not UncertaintyKind.EXPANDED
            or self.coverage_factor is None
        ):
            raise InvariantViolationError(
                "derived uncertainty group requires explicit k"
            )
        if (
            min(self.assessable_count, self.within_count, self.outside_count) < 0
            or self.within_count + self.outside_count != self.assessable_count
        ):
            raise InvariantViolationError("uncertainty counts do not reconcile")


@dataclass(frozen=True, slots=True)
class QuantityAggregate:
    grouping_key: GroupingKey
    observation_unit: ObservationUnit
    reduction: VectorReduction | None
    sample_count: int
    coverage: CoverageBlock
    metrics: tuple[MetricResult, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "metrics", tuple(self.metrics))
        require_enum(self.observation_unit, ObservationUnit, "observation_unit")
        if (self.observation_unit is ObservationUnit.PER_CASE_VECTOR) != (
            self.reduction is not None
        ):
            raise InvariantViolationError("PER_CASE_VECTOR requires a named reduction")
        if self.reduction is not None:
            require_enum(self.reduction, VectorReduction, "reduction")
        if self.sample_count != self.coverage.metric_observation_count:
            raise InvariantViolationError("sample_count must match coverage")
        if len({m.name for m in self.metrics}) != len(self.metrics):
            raise InvariantViolationError("duplicate aggregate metrics")
        for metric in self.metrics:
            if (
                metric.coverage != self.coverage
                or metric.name
                not in METRIC_POLICY[self.grouping_key.comparison_key.quantity].enabled
            ):
                raise InvariantViolationError(
                    "metric violates coverage or quantity policy"
                )


@dataclass(frozen=True, slots=True)
class ExperimentalQuantityAggregate(QuantityAggregate):
    uncertainty_agreement: tuple[UncertaintyAgreementCount, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "uncertainty_agreement", tuple(self.uncertainty_agreement)
        )
        QuantityAggregate.__post_init__(self)
        if (
            self.grouping_key.identity.data_class
            is not DataClass.EXPERIMENTAL_VALIDATION
        ):
            raise MixedDataClassError(
                "experimental aggregate requires experimental data"
            )
        groups = [
            (g.kind_used, g.derivation, g.coverage_factor, g.confidence_level_percent)
            for g in self.uncertainty_agreement
        ]
        if len(groups) != len(set(groups)):
            raise InvariantViolationError("duplicate uncertainty strata")
        if (
            sum(g.assessable_count for g in self.uncertainty_agreement)
            != self.coverage.uncertainty_assessable_count
        ):
            raise InvariantViolationError(
                "uncertainty strata do not reconcile with coverage"
            )


def aggregate_group(
    cases: tuple[CaseComparison, ...],
    grouping_key: GroupingKey,
    observation_unit: ObservationUnit,
    reduction: VectorReduction | None = None,
) -> QuantityAggregate:
    """Aggregate an explicitly declared group, including empty and failed groups."""
    if (observation_unit is ObservationUnit.PER_CASE_VECTOR) != (reduction is not None):
        raise InvariantViolationError("vector observation requires a named reduction")
    require_enum(observation_unit, ObservationUnit, "observation_unit")
    seen = set()
    errors: list[float] = []
    relatives: list[float] = []
    relative_reasons: list[Reason] = []
    excluded = reference_available = compared = assessable = 0
    outcomes = dict.fromkeys(SolverOutcome, 0)
    strata: dict[
        tuple[UncertaintyKind, UncertaintyDerivation, float | None, float | None],
        list[int],
    ] = {}
    for case in cases:
        if not isinstance(case, CaseComparison):
            raise TypeError("modern aggregation accepts CaseComparison only")
        if case.identity.data_class is not grouping_key.identity.data_class:
            raise MixedDataClassError("mixed experimental and cross-check comparisons")
        if (
            case.identity != grouping_key.identity
            or case.capability != grouping_key.capability
            or (
                not grouping_key.pooled_across_systems
                and case.system_id != grouping_key.system_id
            )
        ):
            raise ComparisonAlignmentError("case does not belong to grouping key")
        identity = (case.identity, case.case_id)
        if identity in seen:
            raise ComparisonAlignmentError("duplicate case identity")
        seen.add(identity)
        q = next(
            (
                q
                for q in case.quantity_comparisons
                if q.key == grouping_key.comparison_key
            ),
            None,
        )
        reference_available += int(q is not None and q.reference_available)
        if case.excluded:
            excluded += 1
            continue
        outcomes[case.solver_outcome] += 1
        if q is None or q.comparison_state is not ComparisonState.COMPARED:
            continue
        compared += 1
        assert q.errors is not None
        vector = isinstance(q.errors.error, tuple)
        if vector == (observation_unit is ObservationUnit.PER_CASE_SCALAR):
            raise ComponentAlignmentErrorForObservation(
                "observation unit does not match scalar/vector shape"
            )
        es = components(q.errors.error)
        if reduction is VectorReduction.MEAN_ABS_COMPONENT:
            errors.append(fsum(abs(e) for e in es) / len(es))
        elif reduction is VectorReduction.MAX_ABS_COMPONENT:
            errors.append(max(abs(e) for e in es))
        else:
            errors.extend(es)
        rel = q.errors.relative_error
        if isinstance(rel, UndefinedMetric):
            relative_reasons.append(rel.reason)
        elif rel is not None:
            rs = components(rel)
            if reduction is VectorReduction.MEAN_ABS_COMPONENT:
                relatives.append(fsum(abs(r) for r in rs) / len(rs))
            elif reduction is VectorReduction.MAX_ABS_COMPONENT:
                relatives.append(max(abs(r) for r in rs))
            else:
                relatives.extend(rs)
        assessment = q.uncertainty_assessment
        if isinstance(assessment, UncertaintyAssessment):
            assessable += 1
            a = assessment.applied
            counts = strata.setdefault(
                (
                    a.kind_used,
                    a.derivation,
                    a.coverage_factor,
                    a.confidence_level_percent,
                ),
                [0, 0],
            )
            counts[0 if assessment.agreement is Agreement.WITHIN else 1] += 1
    coverage = CoverageBlock(
        len(cases),
        excluded,
        len(cases) - excluded,
        reference_available,
        outcomes[SolverOutcome.CONVERGED],
        outcomes[SolverOutcome.NOT_FOUND],
        outcomes[SolverOutcome.INCONCLUSIVE],
        outcomes[SolverOutcome.OTHER_FAILURE],
        compared,
        len(errors),
        assessable,
    )
    metrics = []
    qtype = grouping_key.comparison_key.quantity
    for metric in METRIC_POLICY[qtype].enabled:
        percent = metric in {
            MetricName.AARD_PERCENT,
            MetricName.BIAS_PERCENT,
            MetricName.RMS_RELATIVE_PERCENT,
            MetricName.MAX_ABS_RELATIVE_PERCENT,
        }
        observations = relatives if percent else errors
        n = len(observations)
        reason = None
        result = None
        if not n:
            reason = (
                relative_reasons[0]
                if percent and relative_reasons
                else Reason.NO_USABLE_OBSERVATIONS
            )
        else:
            try:
                match metric:
                    case MetricName.MAE:
                        result = fsum(abs(e) for e in errors) / n
                    case MetricName.BIAS:
                        result = fsum(errors) / n
                    case MetricName.RMSE:
                        result = sqrt(fsum(e * e for e in errors) / n)
                    case MetricName.MAX_ABS_ERROR:
                        result = max(abs(e) for e in errors)
                    case MetricName.AARD_PERCENT:
                        result = 100.0 * fsum(abs(r) for r in relatives) / n
                    case MetricName.BIAS_PERCENT:
                        result = 100.0 * fsum(relatives) / n
                    case MetricName.RMS_RELATIVE_PERCENT:
                        result = 100.0 * sqrt(fsum(r * r for r in relatives) / n)
                    case MetricName.MAX_ABS_RELATIVE_PERCENT:
                        result = 100.0 * max(abs(r) for r in relatives)
            except OverflowError:
                reason = Reason.NON_FINITE_RESULT
            if result is not None and not isfinite(result):
                reason = Reason.NON_FINITE_RESULT
            if reason is not None:
                result = None
        metrics.append(
            MetricResult(
                metric,
                MetricState.UNDEFINED if result is None else MetricState.DEFINED,
                result,
                "%" if percent else qtype.canonical_si_unit,
                n,
                coverage,
                reason,
            )
        )
    arguments = (
        grouping_key,
        observation_unit,
        reduction,
        len(errors),
        coverage,
        tuple(metrics),
    )
    if grouping_key.identity.data_class is DataClass.EXPERIMENTAL_VALIDATION:
        agreement = tuple(
            UncertaintyAgreementCount(*key, sum(counts), *counts)
            for key, counts in sorted(strata.items(), key=lambda item: repr(item[0]))
        )
        return ExperimentalQuantityAggregate(*arguments, agreement)
    return QuantityAggregate(*arguments)


# A named alignment error keeps observation misuse distinct from numerical results.
class ComponentAlignmentErrorForObservation(ComparisonAlignmentError):
    """The declared observation unit is incompatible with the comparison shape."""


def format_metric(metric: MetricResult) -> str:
    """Keep sample coverage adjacent to every displayed metric."""
    c = metric.coverage
    value = (
        f"{metric.value}{metric.unit}"
        if metric.value is not None
        else f"UNDEFINED ({metric.reason})"
    )
    return (
        f"{metric.name} = {value} over {c.compared_cases} compared "
        f"of {c.total_cases} cases "
        f"({c.not_found} not_found, {c.inconclusive} inconclusive, "
        f"{c.other_failure} other failures, "
        f"{c.excluded_cases} excluded; {metric.sample_count} observations)"
    )
