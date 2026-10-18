"""Identity-aligned scientific comparisons, independent of solver success."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from ._validation import require_enum, require_non_empty
from .enums import (
    CapabilityUnderTest,
    DataClass,
    PredictionOutcome,
    ToleranceKind,
    UncertaintyKind,
    ValidationQuantity,
    ValidationStatus,
    ValuePhase,
)
from .exceptions import (
    ComparisonAlignmentError,
    ComponentAlignmentError,
    InvariantViolationError,
)
from .metrics import MetricState
from .models import (
    DatasetIdentity,
    DeclaredTolerance,
    PredictionValue,
    ReferenceValue,
    ValidationPrediction,
    ValidationRecord,
    Value,
    validate_value_identity,
)


class SolverOutcome(StrEnum):
    """NOT_FOUND means the configured search found no acceptable solution.

    It does NOT prove that no physical solution exists. INCONCLUSIVE remains
    distinct from both NOT_FOUND and an otherwise unclassified failure.
    """

    CONVERGED = "CONVERGED"
    NOT_FOUND = "NOT_FOUND"
    INCONCLUSIVE = "INCONCLUSIVE"
    OTHER_FAILURE = "OTHER_FAILURE"


class ComparisonState(StrEnum):
    COMPARED = "COMPARED"
    REFERENCE_UNAVAILABLE = "REFERENCE_UNAVAILABLE"
    NOT_PREDICTED = "NOT_PREDICTED"
    PREDICTION_UNAVAILABLE = "PREDICTION_UNAVAILABLE"
    EXCLUDED = "EXCLUDED"


class Reason(StrEnum):
    NOT_COMPARED = "NOT_COMPARED"
    NOT_EXPERIMENTAL = "NOT_EXPERIMENTAL"
    NO_REFERENCE_UNCERTAINTY = "NO_REFERENCE_UNCERTAINTY"
    MISSING_COMPONENT_UNCERTAINTY = "MISSING_COMPONENT_UNCERTAINTY"
    ZERO_UNCERTAINTY_DENOMINATOR = "ZERO_UNCERTAINTY_DENOMINATOR"
    ZERO_REFERENCE_DENOMINATOR = "ZERO_REFERENCE_DENOMINATOR"
    NEGATIVE_REFERENCE_DENOMINATOR = "NEGATIVE_REFERENCE_DENOMINATOR"
    NO_DECLARED_TOLERANCE = "NO_DECLARED_TOLERANCE"
    NO_USABLE_OBSERVATIONS = "NO_USABLE_OBSERVATIONS"
    NON_FINITE_RESULT = "NON_FINITE_RESULT"


class Agreement(StrEnum):
    WITHIN = "WITHIN"
    OUTSIDE = "OUTSIDE"


class UncertaintyDerivation(StrEnum):
    PUBLISHED = "PUBLISHED"
    EXPANDED_FROM_STANDARD = "EXPANDED_FROM_STANDARD"


class UncertaintyScope(StrEnum):
    REFERENCE_ONLY = "REFERENCE_ONLY"


class UncertaintyCriterion(StrEnum):
    WITHIN_REFERENCE_UNCERTAINTY = "WITHIN_REFERENCE_UNCERTAINTY"
    ALL_COMPONENTS_WITHIN_REFERENCE_UNCERTAINTY = (
        "ALL_COMPONENTS_WITHIN_REFERENCE_UNCERTAINTY"
    )


@dataclass(frozen=True, slots=True)
class ComparisonKey:
    quantity: ValidationQuantity
    phase: ValuePhase | None = None

    def __post_init__(self) -> None:
        require_enum(self.quantity, ValidationQuantity, "quantity")
        validate_value_identity(self.quantity, self.phase, 1.0, None)


@dataclass(frozen=True, slots=True)
class ToleranceBinding:
    identity: DatasetIdentity
    key: ComparisonKey
    tolerance: DeclaredTolerance

    def __post_init__(self) -> None:
        if not isinstance(self.identity, DatasetIdentity):
            raise TypeError("binding requires dataset identity")
        if not isinstance(self.key, ComparisonKey):
            raise TypeError("binding requires ComparisonKey")
        if not isinstance(self.tolerance, DeclaredTolerance):
            raise TypeError("binding requires DeclaredTolerance")
        if self.key.quantity is not self.tolerance.quantity:
            raise ComparisonAlignmentError("tolerance quantity does not match key")


@dataclass(frozen=True, slots=True)
class NotAssessed:
    reason: Reason

    def __post_init__(self) -> None:
        require_enum(self.reason, Reason, "reason")


def components(value: Value) -> tuple[float, ...]:
    """Keep scalar and component observation handling explicit at the boundary."""
    return value if isinstance(value, tuple) else (value,)


def _shape(values: tuple[float, ...], vector: bool) -> Value:
    if not values or not all(isfinite(v) for v in values):
        raise ValueError("scientific result must be non-empty and finite")
    return values if vector else values[0]


@dataclass(frozen=True, slots=True)
class AppliedUncertainty:
    kind_used: UncertaintyKind
    derivation: UncertaintyDerivation
    denominator: Value
    coverage_factor: float | None
    confidence_level_percent: float | None
    scope: UncertaintyScope = UncertaintyScope.REFERENCE_ONLY

    def __post_init__(self) -> None:
        require_enum(self.kind_used, UncertaintyKind, "kind_used")
        require_enum(self.derivation, UncertaintyDerivation, "derivation")
        require_enum(self.scope, UncertaintyScope, "scope")
        if any(not isfinite(v) or v <= 0 for v in components(self.denominator)):
            raise ValueError("applied uncertainty denominators must be positive finite")
        if self.coverage_factor is not None and (
            not isfinite(self.coverage_factor) or self.coverage_factor <= 0
        ):
            raise ValueError("coverage_factor must be positive finite")
        if self.confidence_level_percent is not None and (
            not isfinite(self.confidence_level_percent)
            or not 0 <= self.confidence_level_percent <= 100
        ):
            raise ValueError("invalid confidence_level_percent")
        if self.derivation is UncertaintyDerivation.EXPANDED_FROM_STANDARD and (
            self.kind_used is not UncertaintyKind.EXPANDED
            or self.coverage_factor is None
        ):
            raise InvariantViolationError("derived expansion requires explicit k")


@dataclass(frozen=True, slots=True)
class UncertaintyAssessment:
    agreement: Agreement
    applied: AppliedUncertainty
    criterion: UncertaintyCriterion
    expanded_normalized_residual: Value | None = None
    standard_normalized_residual: Value | None = None

    def __post_init__(self) -> None:
        require_enum(self.agreement, Agreement, "agreement")
        require_enum(self.criterion, UncertaintyCriterion, "criterion")
        expanded = self.applied.kind_used is UncertaintyKind.EXPANDED
        residual = (
            self.expanded_normalized_residual
            if expanded
            else self.standard_normalized_residual
        )
        other = (
            self.standard_normalized_residual
            if expanded
            else self.expanded_normalized_residual
        )
        if residual is None or other is not None:
            raise InvariantViolationError(
                "exactly the residual for kind_used is required"
            )
        if isinstance(residual, tuple) != isinstance(self.applied.denominator, tuple):
            raise ComponentAlignmentError("residual and denominator shapes differ")
        values = components(residual)
        if len(values) != len(components(self.applied.denominator)) or not all(
            isfinite(v) for v in values
        ):
            raise ComponentAlignmentError("residuals must be finite and fully aligned")
        expected = (
            Agreement.WITHIN if max(abs(v) for v in values) <= 1 else Agreement.OUTSIDE
        )
        if self.agreement is not expected:
            raise InvariantViolationError(
                "agreement disagrees with normalized residual"
            )
        vector = isinstance(residual, tuple)
        if vector != (
            self.criterion
            is UncertaintyCriterion.ALL_COMPONENTS_WITHIN_REFERENCE_UNCERTAINTY
        ):
            raise InvariantViolationError(
                "criterion must describe the observation shape"
            )


@dataclass(frozen=True, slots=True)
class ToleranceAssessment:
    agreement: Agreement
    tolerance: DeclaredTolerance

    def __post_init__(self) -> None:
        require_enum(self.agreement, Agreement, "agreement")
        if not isinstance(self.tolerance, DeclaredTolerance):
            raise TypeError("assessment must retain full declared tolerance")


@dataclass(frozen=True, slots=True)
class UndefinedMetric:
    """An observation metric whose denominator or arithmetic is undefined."""

    reason: Reason
    state: MetricState = MetricState.UNDEFINED

    def __post_init__(self) -> None:
        require_enum(self.reason, Reason, "reason")
        if self.state is not MetricState.UNDEFINED:
            raise InvariantViolationError(
                "undefined observation requires UNDEFINED state"
            )


@dataclass(frozen=True, slots=True)
class ObservationErrors:
    error: Value
    absolute_error: Value
    relative_error: Value | UndefinedMetric | None
    absolute_relative_error: Value | UndefinedMetric | None

    def __post_init__(self) -> None:
        if self.absolute_error != _shape(
            tuple(abs(v) for v in components(self.error)), isinstance(self.error, tuple)
        ):
            raise InvariantViolationError("absolute error does not match signed error")
        for value in (self.relative_error, self.absolute_relative_error):
            if value is not None and not isinstance(value, UndefinedMetric):
                if not all(isfinite(v) for v in components(value)):
                    raise ValueError("relative results must be finite")


@dataclass(frozen=True, slots=True)
class QuantityComparison:
    key: ComparisonKey
    comparison_state: ComparisonState
    component_ids: tuple[str, ...] | None
    reference_available: bool
    errors: ObservationErrors | None
    uncertainty_assessment: UncertaintyAssessment | NotAssessed
    tolerance_assessment: ToleranceAssessment | NotAssessed
    exclusion_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.key, ComparisonKey):
            raise TypeError("quantity comparison requires ComparisonKey")
        if not isinstance(
            self.uncertainty_assessment, (UncertaintyAssessment, NotAssessed)
        ):
            raise TypeError("invalid uncertainty assessment")
        if not isinstance(
            self.tolerance_assessment, (ToleranceAssessment, NotAssessed)
        ):
            raise TypeError("invalid tolerance assessment")
        require_enum(self.comparison_state, ComparisonState, "comparison_state")
        compared = self.comparison_state is ComparisonState.COMPARED
        if compared != (self.errors is not None):
            raise InvariantViolationError("errors exist only for COMPARED")
        if compared and not self.reference_available:
            raise InvariantViolationError("COMPARED requires reference")
        if not compared and (
            not isinstance(self.uncertainty_assessment, NotAssessed)
            or not isinstance(self.tolerance_assessment, NotAssessed)
        ):
            raise InvariantViolationError("assessments exist only for COMPARED")
        if self.comparison_state is ComparisonState.EXCLUDED:
            require_non_empty(self.exclusion_reason or "", "exclusion_reason")
        elif self.exclusion_reason is not None:
            raise InvariantViolationError("exclusion reason requires EXCLUDED")
        if self.errors is not None:
            validate_value_identity(
                self.key.quantity, self.key.phase, self.errors.error, self.component_ids
            )
            if (
                not self.key.quantity.relative_error_meaningful
                and self.errors.relative_error is not None
            ):
                raise InvariantViolationError(
                    "relative metrics forbidden for fractions"
                )
            if isinstance(self.uncertainty_assessment, UncertaintyAssessment):
                denominator = self.uncertainty_assessment.applied.denominator
                if isinstance(denominator, tuple) != isinstance(
                    self.errors.error, tuple
                ) or len(components(denominator)) != len(components(self.errors.error)):
                    raise ComponentAlignmentError(
                        "assessment component shape differs from errors"
                    )
            if isinstance(self.tolerance_assessment, ToleranceAssessment):
                if (
                    self.tolerance_assessment.tolerance.quantity
                    is not self.key.quantity
                ):
                    raise ComparisonAlignmentError(
                        "bound tolerance quantity differs from comparison"
                    )


@dataclass(frozen=True, slots=True)
class CaseComparison:
    identity: DatasetIdentity
    case_id: str
    system_id: str
    capability: CapabilityUnderTest
    solver_outcome: SolverOutcome
    quantity_comparisons: tuple[QuantityComparison, ...]
    excluded: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.identity, DatasetIdentity):
            raise TypeError("case comparison requires dataset identity")
        object.__setattr__(
            self, "quantity_comparisons", tuple(self.quantity_comparisons)
        )
        if any(
            not isinstance(q, QuantityComparison) for q in self.quantity_comparisons
        ):
            raise TypeError("case comparison requires quantity comparisons")
        require_enum(self.capability, CapabilityUnderTest, "capability")
        require_enum(self.solver_outcome, SolverOutcome, "solver_outcome")
        require_non_empty(self.case_id, "case_id")
        require_non_empty(self.system_id, "system_id")
        keys = [q.key for q in self.quantity_comparisons]
        if len(keys) != len(set(keys)):
            raise ComparisonAlignmentError("duplicate comparison keys")
        for q in self.quantity_comparisons:
            if self.excluded != (q.comparison_state is ComparisonState.EXCLUDED):
                raise InvariantViolationError("inconsistent exclusion lifecycle")
            if (
                q.comparison_state
                in {
                    ComparisonState.COMPARED,
                    ComparisonState.NOT_PREDICTED,
                    ComparisonState.REFERENCE_UNAVAILABLE,
                }
                and self.solver_outcome is not SolverOutcome.CONVERGED
            ):
                raise InvariantViolationError("comparison state requires convergence")
            if (
                q.comparison_state is ComparisonState.PREDICTION_UNAVAILABLE
                and self.solver_outcome is SolverOutcome.CONVERGED
            ):
                raise InvariantViolationError("converged outcome cannot be unavailable")
            if (
                self.identity.data_class is DataClass.NUMERICAL_CROSS_CHECK
                and q.uncertainty_assessment != NotAssessed(Reason.NOT_EXPERIMENTAL)
            ):
                raise InvariantViolationError(
                    "cross-check uncertainty is NOT_EXPERIMENTAL"
                )


def solver_outcome(prediction: ValidationPrediction) -> SolverOutcome:
    """Read structured outcome only; prose is never interpreted."""
    raw = prediction.solver_metadata.get("legacy_solver_outcome")
    if raw is None:
        return (
            SolverOutcome.CONVERGED
            if prediction.outcome is PredictionOutcome.VALUE
            else SolverOutcome.OTHER_FAILURE
        )
    mapping = {
        "converged": SolverOutcome.CONVERGED,
        "not_found": SolverOutcome.NOT_FOUND,
        "inconclusive": SolverOutcome.INCONCLUSIVE,
    }
    if not isinstance(raw, str) or raw not in mapping:
        raise InvariantViolationError("unknown structured solver outcome")
    result = mapping[raw]
    if (result is SolverOutcome.CONVERGED) != (
        prediction.outcome is PredictionOutcome.VALUE
    ):
        raise InvariantViolationError("CONVERGED if and only if VALUE")
    return result


def align_values(
    reference: ReferenceValue, prediction: PredictionValue
) -> tuple[Value, Value]:
    """Reorder predictions to reference component identities before subtraction."""
    if (reference.quantity, reference.phase) != (prediction.quantity, prediction.phase):
        raise ComparisonAlignmentError("quantity and phase must be identical")
    if isinstance(reference.value, tuple):
        if not isinstance(prediction.value, tuple) or set(
            reference.component_ids or ()
        ) != set(prediction.component_ids or ()):
            raise ComponentAlignmentError("component identity sets must be identical")
        by_id = dict(zip(prediction.component_ids or (), prediction.value, strict=True))
        return reference.value, tuple(by_id[c] for c in reference.component_ids or ())
    if isinstance(prediction.value, tuple):
        raise ComponentAlignmentError("scalar/vector mismatch")
    return reference.value, prediction.value


def _denominator_reason(values: tuple[float, ...]) -> Reason | None:
    if any(v == 0 for v in values):
        return Reason.ZERO_REFERENCE_DENOMINATOR
    if any(v < 0 for v in values):
        return Reason.NEGATIVE_REFERENCE_DENOMINATOR
    return None


def _errors(
    reference: Value, prediction: Value, quantity: ValidationQuantity
) -> ObservationErrors:
    refs, preds = components(reference), components(prediction)
    vector = isinstance(reference, tuple)
    error = _shape(tuple(p - r for p, r in zip(preds, refs, strict=True)), vector)
    relative: Value | UndefinedMetric | None = None
    absolute_relative: Value | UndefinedMetric | None = None
    # Policy, rather than the quantity permission alone, enables observation metrics.
    from .metrics import METRIC_POLICY

    if "relative" in METRIC_POLICY[quantity].per_observation:
        reason = _denominator_reason(refs)
        if reason is not None:
            relative = absolute_relative = UndefinedMetric(reason)
        else:
            ratios = tuple(e / r for e, r in zip(components(error), refs, strict=True))
            if all(isfinite(v) for v in ratios):
                relative = _shape(ratios, vector)
                absolute_relative = _shape(tuple(abs(v) for v in ratios), vector)
            else:
                relative = absolute_relative = UndefinedMetric(Reason.NON_FINITE_RESULT)
    return ObservationErrors(
        error,
        _shape(tuple(abs(v) for v in components(error)), vector),
        relative,
        absolute_relative,
    )


def _uncertainty(
    reference: ReferenceValue, error: Value, derive_expanded: bool
) -> UncertaintyAssessment | NotAssessed:
    source = reference.uncertainty
    if source is None:
        return NotAssessed(Reason.NO_REFERENCE_UNCERTAINTY)
    denominators = source.value if isinstance(source.value, tuple) else (source.value,)
    if any(v is None for v in denominators):
        return NotAssessed(Reason.MISSING_COMPONENT_UNCERTAINTY)
    usable = tuple(v for v in denominators if v is not None)
    if any(v == 0 for v in usable):
        return NotAssessed(Reason.ZERO_UNCERTAINTY_DENOMINATOR)
    kind = source.kind
    derivation = UncertaintyDerivation.PUBLISHED
    if derive_expanded and kind is UncertaintyKind.STANDARD:
        if source.coverage_factor is None:
            raise ValueError("explicit expansion requires a published coverage_factor")
        usable = tuple(v * source.coverage_factor for v in usable)
        kind = UncertaintyKind.EXPANDED
        derivation = UncertaintyDerivation.EXPANDED_FROM_STANDARD
    if any(v == 0 for v in usable):
        return NotAssessed(Reason.ZERO_UNCERTAINTY_DENOMINATOR)
    if any(not isfinite(v) for v in usable):
        return NotAssessed(Reason.NON_FINITE_RESULT)
    residuals = tuple(e / u for e, u in zip(components(error), usable, strict=True))
    if any(not isfinite(v) for v in residuals):
        return NotAssessed(Reason.NON_FINITE_RESULT)
    vector = isinstance(error, tuple)
    residual = _shape(residuals, vector)
    return UncertaintyAssessment(
        Agreement.WITHIN if max(abs(v) for v in residuals) <= 1 else Agreement.OUTSIDE,
        AppliedUncertainty(
            kind,
            derivation,
            _shape(usable, vector),
            source.coverage_factor,
            source.confidence_level_percent,
        ),
        UncertaintyCriterion.ALL_COMPONENTS_WITHIN_REFERENCE_UNCERTAINTY
        if vector
        else UncertaintyCriterion.WITHIN_REFERENCE_UNCERTAINTY,
        residual if kind is UncertaintyKind.EXPANDED else None,
        residual if kind is UncertaintyKind.STANDARD else None,
    )


def compare_record(
    record: ValidationRecord,
    capability: CapabilityUnderTest,
    *,
    tolerance_bindings: tuple[ToleranceBinding, ...] = (),
    derive_expanded: bool = False,
) -> CaseComparison:
    """Derive comparisons without modifying the source record or its lifecycle."""
    outcome = solver_outcome(record.prediction)
    refs: dict[ComparisonKey, ReferenceValue] = {}
    preds: dict[ComparisonKey, PredictionValue] = {}
    for value in record.case.reference_values:
        key = ComparisonKey(value.quantity, value.phase)
        if key in refs:
            raise ComparisonAlignmentError("duplicate reference key")
        refs[key] = value
    for predicted in record.prediction.values:
        key = ComparisonKey(predicted.quantity, predicted.phase)
        if key in preds:
            raise ComparisonAlignmentError("duplicate prediction key")
        preds[key] = predicted
    bound: dict[ComparisonKey, DeclaredTolerance] = {}
    for binding in tolerance_bindings:
        if binding.identity == record.identity:
            if binding.key in bound:
                raise ComparisonAlignmentError("duplicate tolerance binding")
            bound[binding.key] = binding.tolerance
    comparisons = []
    experimental = record.data_class is DataClass.EXPERIMENTAL_VALIDATION
    excluded = record.status is ValidationStatus.EXCLUDED
    for key in sorted(
        refs.keys() | preds.keys(), key=lambda k: (k.quantity.value, k.phase or "")
    ):
        ref, pred = refs.get(key), preds.get(key)
        errors = None
        uncertainty: UncertaintyAssessment | NotAssessed = NotAssessed(
            Reason.NOT_COMPARED if experimental else Reason.NOT_EXPERIMENTAL
        )
        tolerance: ToleranceAssessment | NotAssessed = NotAssessed(Reason.NOT_COMPARED)
        if excluded:
            state = ComparisonState.EXCLUDED
        elif outcome is not SolverOutcome.CONVERGED:
            state = ComparisonState.PREDICTION_UNAVAILABLE
        elif ref is None:
            state = ComparisonState.REFERENCE_UNAVAILABLE
        elif pred is None:
            state = ComparisonState.NOT_PREDICTED
        else:
            state = ComparisonState.COMPARED
            r, p = align_values(ref, pred)
            errors = _errors(r, p, key.quantity)
            if experimental:
                uncertainty = _uncertainty(ref, errors.error, derive_expanded)
            declared = bound.get(key)
            tolerance = NotAssessed(Reason.NO_DECLARED_TOLERANCE)
            if declared is not None:
                criterion = components(errors.error)
                reason = None
                if declared.tolerance_kind is ToleranceKind.RELATIVE:
                    reason = _denominator_reason(components(r))
                    if reason is None:
                        criterion = tuple(
                            e / v for e, v in zip(criterion, components(r), strict=True)
                        )
                tolerance = (
                    NotAssessed(reason)
                    if reason is not None
                    else ToleranceAssessment(
                        Agreement.WITHIN
                        if all(abs(v) <= declared.value for v in criterion)
                        else Agreement.OUTSIDE,
                        declared,
                    )
                )
        owner = ref if ref is not None else pred
        comparisons.append(
            QuantityComparison(
                key,
                state,
                None if owner is None else owner.component_ids,
                ref is not None,
                errors,
                uncertainty,
                tolerance,
                record.exclusion_reason,
            )
        )
    return CaseComparison(
        record.identity,
        record.case.case_id,
        record.case.system_id,
        capability,
        outcome,
        tuple(comparisons),
        excluded,
    )
