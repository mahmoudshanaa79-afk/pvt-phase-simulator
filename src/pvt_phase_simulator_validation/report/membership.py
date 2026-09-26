"""C-backed aggregate and per-metric membership proofs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pvt_phase_simulator_validation.aggregates import (
    QuantityAggregate,
    aggregate_group,
)
from pvt_phase_simulator_validation.comparisons import (
    CaseComparison,
    ComparisonState,
    UndefinedMetric,
)
from pvt_phase_simulator_validation.metrics import MetricName


class EvidenceInconsistencyError(ValueError):
    """Evidence identities or counts disagree with C's scientific objects."""


@dataclass(frozen=True, slots=True, order=True)
class ObservationIdentity:
    case_id: str
    component_id: str | None = None


@dataclass(frozen=True, slots=True)
class MetricMembership:
    metric: MetricName
    contributors: tuple[ObservationIdentity, ...]


@dataclass(frozen=True, slots=True)
class AggregateMembership:
    case_ids: tuple[str, ...]
    metric_memberships: tuple[MetricMembership, ...]


def _group_cases(
    cases: tuple[CaseComparison, ...], aggregate: QuantityAggregate
) -> tuple[CaseComparison, ...]:
    key = aggregate.grouping_key
    selected = tuple(
        sorted(
            (
                case
                for case in cases
                if case.identity == key.identity
                and case.capability == key.capability
                and (key.pooled_across_systems or case.system_id == key.system_id)
            ),
            key=lambda case: case.case_id,
        )
    )
    if len({case.case_id for case in selected}) != len(selected):
        raise EvidenceInconsistencyError("duplicate case identity in aggregate group")
    return selected


def _comparison(case: CaseComparison, aggregate: QuantityAggregate):  # type: ignore[no-untyped-def]
    return next(
        (
            comparison
            for comparison in case.quantity_comparisons
            if comparison.key == aggregate.grouping_key.comparison_key
        ),
        None,
    )


def _contributors(
    cases: tuple[CaseComparison, ...],
    aggregate: QuantityAggregate,
    metric_name: MetricName,
) -> tuple[ObservationIdentity, ...]:
    metric = next(metric for metric in aggregate.metrics if metric.name is metric_name)
    relative_metric = metric.unit == "%"
    contributors: list[ObservationIdentity] = []
    for case in cases:
        comparison = _comparison(case, aggregate)
        if (
            comparison is None
            or comparison.comparison_state is not ComparisonState.COMPARED
        ):
            continue
        if relative_metric:
            assert comparison.errors is not None
            relative = comparison.errors.relative_error
            if relative is None or isinstance(relative, UndefinedMetric):
                continue
        if aggregate.observation_unit.value == "PER_COMPONENT":
            if not comparison.component_ids:
                raise EvidenceInconsistencyError(
                    "PER_COMPONENT comparison has no component identity"
                )
            contributors.extend(
                ObservationIdentity(case.case_id, component_id)
                for component_id in comparison.component_ids
            )
        else:
            contributors.append(ObservationIdentity(case.case_id))
    return tuple(sorted(contributors))


def prove_aggregate_membership(
    cases: tuple[CaseComparison, ...],
    aggregate: QuantityAggregate,
    *,
    declared_metric_contributors: Mapping[MetricName, tuple[ObservationIdentity, ...]]
    | None = None,
) -> AggregateMembership:
    """Prove group and metric contributors by re-invoking C's public aggregator.

    ``declared_metric_contributors`` exists for import/validation paths and adversarial
    tests. It cannot override C-derived membership.
    """

    group = _group_cases(cases, aggregate)
    rerun = aggregate_group(
        group,
        aggregate.grouping_key,
        aggregate.observation_unit,
        aggregate.reduction,
    )
    if rerun != aggregate:
        raise EvidenceInconsistencyError(
            "aggregate group does not reproduce C's frozen aggregate"
        )

    memberships: list[MetricMembership] = []
    by_case = {case.case_id: case for case in group}
    for metric in aggregate.metrics:
        actual = _contributors(group, aggregate, metric.name)
        supplied = (
            actual
            if declared_metric_contributors is None
            else tuple(sorted(declared_metric_contributors.get(metric.name, actual)))
        )
        if supplied != actual:
            raise EvidenceInconsistencyError(
                f"declared membership for {metric.name.value} differs from C state"
            )
        if len(supplied) != metric.sample_count:
            raise EvidenceInconsistencyError(
                f"membership count for {metric.name.value} is {len(supplied)}, "
                f"expected {metric.sample_count}"
            )
        contributor_case_ids = tuple(sorted({item.case_id for item in supplied}))
        if any(case_id not in by_case for case_id in contributor_case_ids):
            raise EvidenceInconsistencyError("metric contributor is outside its group")
        contributor_cases = tuple(by_case[case_id] for case_id in contributor_case_ids)
        proof = aggregate_group(
            contributor_cases,
            aggregate.grouping_key,
            aggregate.observation_unit,
            aggregate.reduction,
        )
        proof_metric = next(item for item in proof.metrics if item.name is metric.name)
        if (
            proof_metric.sample_count != metric.sample_count
            or proof_metric.value != metric.value
            or proof_metric.state is not metric.state
        ):
            raise EvidenceInconsistencyError(
                f"contributors do not reproduce {metric.name.value} through C"
            )
        memberships.append(MetricMembership(metric.name, supplied))
    return AggregateMembership(
        tuple(case.case_id for case in group), tuple(memberships)
    )
