"""Natural-temperature continuation of fixed-composition saturation branches."""

from dataclasses import dataclass
from enum import StrEnum
from math import exp, isclose, isfinite, log
from typing import Final

from pvt_phase_simulator.eos.diagnostics import (
    DiagnosticCategory,
    DiagnosticSeverity,
    EOSDiagnostic,
)
from pvt_phase_simulator.eos.flash import PhaseInteractionProvenance
from pvt_phase_simulator.eos.mixing_rules import (
    BinaryInteractionMapping,
    BinaryInteractionPolicy,
    calculate_peng_robinson_mixture_parameters,
)
from pvt_phase_simulator.eos.peng_robinson import (
    MechanicalStabilityClassification,
)
from pvt_phase_simulator.eos.saturation_pressure import (
    FUGACITY_EQUILIBRIUM_TOLERANCE,
    INNER_COMPOSITION_TOLERANCE,
    INNER_LOG_K_TOLERANCE,
    SATURATION_OBJECTIVE_TOLERANCE,
    TRIVIAL_LOG_K_TOLERANCE,
    TRIVIAL_STATE_DIAGNOSTIC_CODE,
    SaturationKind,
    SaturationPressureResult,
    SaturationStatus,
    calculate_saturation_pressure,
)
from pvt_phase_simulator.fluid_models import MOLE_FRACTION_TOLERANCE, FluidMixture

TEMPERATURE_UNIQUENESS_TOLERANCE_K: Final = 1e-10
# Fixed safeguards for rejecting reconstructed phases that are numerically
# indistinguishable in composition and selected compressibility factor.
PHASE_COMPOSITION_DISTINGUISHABILITY_TOLERANCE: Final = 1e-10
PHASE_ROOT_DISTINGUISHABILITY_TOLERANCE: Final = 1e-8
# Diagnostic-only relative pressure proximity for matched bubble/dew points.
CROSS_BRANCH_PRESSURE_RELATIVE_TOLERANCE: Final = 0.02


class EnvelopeBranchKind(StrEnum):
    """Saturation branch followed by continuation."""

    BUBBLE = "bubble"
    DEW = "dew"


class EnvelopePointStatus(StrEnum):
    """Outcome of one predicted continuation correction."""

    CONVERGED = "converged"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"
    FAILED = "failed"


class EnvelopeTerminationReason(StrEnum):
    """Reason an ordered branch trace stopped."""

    TARGET_REACHED = "target_reached"
    MAXIMUM_POINTS = "maximum_points"
    MINIMUM_STEP_REACHED = "minimum_step_reached"
    CORRECTOR_FAILED = "corrector_failed"
    BRANCH_LOST = "branch_lost"
    NEAR_CRITICAL = "near_critical"
    PRESSURE_OUT_OF_BOUNDS = "pressure_out_of_bounds"
    NUMERICAL_FAILURE = "numerical_failure"


class EnvelopePredictionKind(StrEnum):
    """Predictor formula actually used."""

    PREVIOUS_STATE = "previous_state"
    SECANT = "secant"
    PREVIOUS_STATE_FALLBACK = "previous_state_fallback"


class EnvelopeCorrectionSource(StrEnum):
    """Pressure-search path that produced or attempted a point."""

    STARTING_SATURATION = "starting_saturation"
    LOCAL = "local"
    EXPANDED_LOCAL = "expanded_local"
    GLOBAL_FALLBACK = "global_fallback"


@dataclass(frozen=True, slots=True)
class EnvelopeContinuationSettings:
    """Validated deterministic controls for one temperature continuation."""

    target_temperature_k: float
    initial_temperature_step_k: float
    minimum_temperature_step_k: float = 0.25
    maximum_temperature_step_k: float = 10.0
    maximum_points: int = 25
    minimum_pressure_pa: float = 1_000.0
    maximum_pressure_pa: float = 100_000_000.0
    local_log_pressure_half_span: float = 0.08
    local_expansion_factor: float = 1.8
    maximum_local_expansions: int = 5
    maximum_step_retries: int = 6
    allow_global_fallback: bool = True
    easy_iteration_limit: int = 30
    easy_predictor_log_pressure_error: float = 0.1
    easy_predictor_log_k_error: float = 0.2
    retry_step_reduction_factor: float = 0.5
    step_increase_factor: float = 1.25
    step_decrease_factor: float = 0.70
    maximum_predictor_log_pressure_error: float = 0.50
    maximum_predictor_log_k_error: float = 1.00
    maximum_composition_change: float = 0.35
    maximum_consecutive_log_pressure_change: float = 0.75
    maximum_root_change: float = 0.50
    saturation_objective_tolerance: float = SATURATION_OBJECTIVE_TOLERANCE
    fugacity_equilibrium_tolerance: float = FUGACITY_EQUILIBRIUM_TOLERANCE
    log_k_tolerance: float = INNER_LOG_K_TOLERANCE
    composition_tolerance: float = INNER_COMPOSITION_TOLERANCE
    near_critical_composition_warning: float = 0.02
    near_critical_log_k_warning: float = 0.05
    near_critical_root_warning: float = 0.02
    near_critical_composition_stop: float = 0.005
    near_critical_log_k_stop: float = 0.01
    near_critical_root_stop: float = 0.005
    successive_substitution_damping_factor: float = 1.0

    def __post_init__(self) -> None:
        positive_finite = {
            "target_temperature_k": self.target_temperature_k,
            "minimum_temperature_step_k": self.minimum_temperature_step_k,
            "maximum_temperature_step_k": self.maximum_temperature_step_k,
            "minimum_pressure_pa": self.minimum_pressure_pa,
            "maximum_pressure_pa": self.maximum_pressure_pa,
            "local_log_pressure_half_span": self.local_log_pressure_half_span,
            "local_expansion_factor": self.local_expansion_factor,
            "easy_predictor_log_pressure_error": (
                self.easy_predictor_log_pressure_error
            ),
            "easy_predictor_log_k_error": self.easy_predictor_log_k_error,
            "retry_step_reduction_factor": self.retry_step_reduction_factor,
            "step_increase_factor": self.step_increase_factor,
            "step_decrease_factor": self.step_decrease_factor,
            "maximum_predictor_log_pressure_error": (
                self.maximum_predictor_log_pressure_error
            ),
            "maximum_predictor_log_k_error": self.maximum_predictor_log_k_error,
            "maximum_composition_change": self.maximum_composition_change,
            "maximum_consecutive_log_pressure_change": (
                self.maximum_consecutive_log_pressure_change
            ),
            "maximum_root_change": self.maximum_root_change,
            "saturation_objective_tolerance": self.saturation_objective_tolerance,
            "fugacity_equilibrium_tolerance": self.fugacity_equilibrium_tolerance,
            "log_k_tolerance": self.log_k_tolerance,
            "composition_tolerance": self.composition_tolerance,
            "near_critical_composition_warning": (
                self.near_critical_composition_warning
            ),
            "near_critical_log_k_warning": self.near_critical_log_k_warning,
            "near_critical_root_warning": self.near_critical_root_warning,
            "near_critical_composition_stop": self.near_critical_composition_stop,
            "near_critical_log_k_stop": self.near_critical_log_k_stop,
            "near_critical_root_stop": self.near_critical_root_stop,
            "successive_substitution_damping_factor": (
                self.successive_substitution_damping_factor
            ),
        }
        for name, value in positive_finite.items():
            if not isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and strictly positive.")
        if (
            not isfinite(self.initial_temperature_step_k)
            or self.initial_temperature_step_k == 0.0
        ):
            raise ValueError("initial_temperature_step_k must be finite and non-zero.")
        if self.minimum_temperature_step_k > self.maximum_temperature_step_k:
            raise ValueError("minimum temperature step cannot exceed maximum step.")
        if not (
            self.minimum_temperature_step_k
            <= abs(self.initial_temperature_step_k)
            <= self.maximum_temperature_step_k
        ):
            raise ValueError("initial temperature step must lie within step limits.")
        if self.minimum_pressure_pa >= self.maximum_pressure_pa:
            raise ValueError("minimum pressure must be less than maximum pressure.")
        if not isinstance(self.maximum_points, int) or self.maximum_points < 1:
            raise ValueError("maximum_points must be a positive integer.")
        if (
            not isinstance(self.maximum_local_expansions, int)
            or self.maximum_local_expansions < 0
        ):
            raise ValueError("maximum_local_expansions must be a non-negative integer.")
        if (
            not isinstance(self.maximum_step_retries, int)
            or self.maximum_step_retries < 0
        ):
            raise ValueError("maximum_step_retries must be a non-negative integer.")
        if (
            not isinstance(self.easy_iteration_limit, int)
            or self.easy_iteration_limit < 1
        ):
            raise ValueError("easy_iteration_limit must be a positive integer.")
        if self.local_expansion_factor <= 1.0:
            raise ValueError("local_expansion_factor must be greater than one.")
        if self.step_increase_factor <= 1.0:
            raise ValueError("step_increase_factor must be greater than one.")
        if self.retry_step_reduction_factor >= 1.0:
            raise ValueError("retry step reduction factor must be less than one.")
        if not 0.0 < self.step_decrease_factor < 1.0:
            raise ValueError(
                "step_decrease_factor must lie strictly between zero and one."
            )
        if self.saturation_objective_tolerance > SATURATION_OBJECTIVE_TOLERANCE:
            raise ValueError("saturation objective tolerance cannot weaken Module 8.")
        if self.fugacity_equilibrium_tolerance > FUGACITY_EQUILIBRIUM_TOLERANCE:
            raise ValueError("fugacity tolerance cannot weaken Module 8.")
        if self.log_k_tolerance > INNER_LOG_K_TOLERANCE:
            raise ValueError("log-K tolerance cannot weaken Module 8.")
        if self.composition_tolerance > INNER_COMPOSITION_TOLERANCE:
            raise ValueError("composition tolerance cannot weaken Module 8.")
        if (
            self.near_critical_composition_stop > self.near_critical_composition_warning
            or self.near_critical_log_k_stop > self.near_critical_log_k_warning
            or self.near_critical_root_stop > self.near_critical_root_warning
        ):
            raise ValueError(
                "near-critical stop thresholds cannot exceed warning thresholds."
            )
        if self.successive_substitution_damping_factor > 1.0:
            raise ValueError(
                "successive_substitution_damping_factor must be at most one."
            )


@dataclass(frozen=True, slots=True)
class EnvelopePrediction:
    """Immutable natural-parameter prediction for the next state."""

    kind: EnvelopePredictionKind
    temperature_k: float
    log_pressure: float
    log_k_values: tuple[float, ...]
    incipient_composition: tuple[float, ...]
    diagnostics: tuple[EOSDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class EnvelopeCorrectionAttempt:
    """One local, expanded-local, or global correction attempt."""

    source: EnvelopeCorrectionSource
    status: EnvelopePointStatus
    temperature_k: float
    requested_temperature_step_k: float
    pressure_bounds_pa: tuple[float, float]
    log_pressure_half_span: float | None
    saturation_result: SaturationPressureResult | None
    accepted: bool
    failure_reason: str | None
    diagnostics: tuple[EOSDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class PhaseEnvelopePoint:
    """One accepted, fully reconstructed saturation state on a branch."""

    branch_kind: EnvelopeBranchKind
    status: EnvelopePointStatus
    saturation_result: SaturationPressureResult
    prediction: EnvelopePrediction | None
    correction_source: EnvelopeCorrectionSource
    accepted_temperature_step_k: float
    correction_attempts: tuple[EnvelopeCorrectionAttempt, ...]
    log_k_values: tuple[float, ...]
    root_separation: float
    composition_separation: float
    maximum_active_log_k: float
    predictor_log_pressure_error: float
    predictor_log_k_error: float
    diagnostics: tuple[EOSDiagnostic, ...]

    @property
    def temperature_k(self) -> float:
        return self.saturation_result.temperature_k

    @property
    def pressure_pa(self) -> float:
        pressure = self.saturation_result.pressure_pa
        if pressure is None:
            raise ValueError("an accepted envelope point must have pressure.")
        return pressure


@dataclass(frozen=True, slots=True)
class PhaseEnvelopeBranchResult:
    """Ordered accepted points plus every rejected correction attempt."""

    branch_kind: EnvelopeBranchKind
    feed_mixture: FluidMixture
    feed_composition: tuple[float, ...]
    settings: EnvelopeContinuationSettings
    points: tuple[PhaseEnvelopePoint, ...]
    rejected_attempts: tuple[EnvelopeCorrectionAttempt, ...]
    termination_reason: EnvelopeTerminationReason
    termination_message: str
    diagnostics: tuple[EOSDiagnostic, ...]
    binary_interaction_policy: BinaryInteractionPolicy
    binary_interactions: tuple[tuple[str, str, float], ...]
    supplied_binary_interaction_pairs: tuple[tuple[str, str], ...]
    defaulted_binary_interaction_pairs: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class PhaseEnvelopeResult:
    """Independent bubble and dew branch traces for one feed."""

    feed_mixture: FluidMixture
    bubble_branch: PhaseEnvelopeBranchResult
    dew_branch: PhaseEnvelopeBranchResult
    matched_temperature_pressure_separations: tuple[tuple[float, float], ...]
    diagnostics: tuple[EOSDiagnostic, ...]


def _diagnostic(code: str, message: str) -> EOSDiagnostic:
    return EOSDiagnostic(
        code=code,
        severity=DiagnosticSeverity.WARNING,
        category=DiagnosticCategory.NUMERICAL_CONDITIONING,
        message=message,
    )


def _feed(mixture: FluidMixture) -> tuple[float, ...]:
    return tuple(item.mole_fraction for item in mixture.components)


def _saturation_kind(branch_kind: EnvelopeBranchKind) -> SaturationKind:
    if branch_kind is EnvelopeBranchKind.BUBBLE:
        return SaturationKind.BUBBLE_POINT
    if branch_kind is EnvelopeBranchKind.DEW:
        return SaturationKind.DEW_POINT
    raise ValueError("branch_kind must be an EnvelopeBranchKind.")


def _provenance(
    mixture: FluidMixture,
    temperature_k: float,
    pressure_pa: float,
    binary_interactions: BinaryInteractionMapping | None,
    policy: BinaryInteractionPolicy,
) -> PhaseInteractionProvenance:
    parameters = calculate_peng_robinson_mixture_parameters(
        mixture, temperature_k, pressure_pa, binary_interactions, policy
    )
    return PhaseInteractionProvenance(
        parameters.binary_interaction_policy,
        parameters.binary_interactions,
        parameters.supplied_binary_interaction_pairs,
        parameters.defaulted_binary_interaction_pairs,
    )


def _result_provenance(result: SaturationPressureResult) -> PhaseInteractionProvenance:
    return PhaseInteractionProvenance(
        result.binary_interaction_policy,
        result.binary_interactions,
        result.supplied_binary_interaction_pairs,
        result.defaulted_binary_interaction_pairs,
    )


def _result_log_k(result: SaturationPressureResult) -> tuple[float, ...]:
    values = tuple(log(value) for value in result.k_values)
    if not values or not all(isfinite(value) for value in values):
        raise ValueError("starting result must contain finite positive K-values.")
    return values


def predict_envelope_state(
    previous: PhaseEnvelopePoint,
    target_temperature_k: float,
    two_points_back: PhaseEnvelopePoint | None = None,
) -> EnvelopePrediction:
    """Predict log pressure and log K by previous-state or secant continuation."""

    if not isfinite(target_temperature_k) or target_temperature_k <= 0.0:
        raise ValueError("target_temperature_k must be finite and positive.")
    previous_log_pressure = log(previous.pressure_pa)
    diagnostics: list[EOSDiagnostic] = []
    if two_points_back is None:
        return EnvelopePrediction(
            EnvelopePredictionKind.PREVIOUS_STATE,
            target_temperature_k,
            previous_log_pressure,
            previous.log_k_values,
            previous.saturation_result.incipient_composition,
            (),
        )
    temperature_delta = previous.temperature_k - two_points_back.temperature_k
    if abs(temperature_delta) <= TEMPERATURE_UNIQUENESS_TOLERANCE_K:
        diagnostics.append(
            _diagnostic(
                "ENVELOPE_PREDICTOR_DUPLICATE_TEMPERATURE",
                "Secant prediction fell back because accepted temperatures coincide.",
            )
        )
        return EnvelopePrediction(
            EnvelopePredictionKind.PREVIOUS_STATE_FALLBACK,
            target_temperature_k,
            previous_log_pressure,
            previous.log_k_values,
            previous.saturation_result.incipient_composition,
            tuple(diagnostics),
        )
    scale = (target_temperature_k - previous.temperature_k) / temperature_delta
    predicted_log_pressure = previous_log_pressure + scale * (
        previous_log_pressure - log(two_points_back.pressure_pa)
    )
    predicted_log_k = tuple(
        current + scale * (current - older)
        for current, older in zip(
            previous.log_k_values, two_points_back.log_k_values, strict=True
        )
    )
    if not isfinite(predicted_log_pressure) or not all(
        isfinite(value) for value in predicted_log_k
    ):
        diagnostics.append(
            _diagnostic(
                "ENVELOPE_PREDICTOR_NONFINITE_SLOPE",
                "Secant prediction fell back after a non-finite extrapolation.",
            )
        )
        return EnvelopePrediction(
            EnvelopePredictionKind.PREVIOUS_STATE_FALLBACK,
            target_temperature_k,
            previous_log_pressure,
            previous.log_k_values,
            previous.saturation_result.incipient_composition,
            tuple(diagnostics),
        )
    return EnvelopePrediction(
        EnvelopePredictionKind.SECANT,
        target_temperature_k,
        predicted_log_pressure,
        predicted_log_k,
        previous.saturation_result.incipient_composition,
        (),
    )


def _attempt_status(result: SaturationPressureResult) -> EnvelopePointStatus:
    if result.status is SaturationStatus.CONVERGED:
        return EnvelopePointStatus.CONVERGED
    if result.status is SaturationStatus.INCONCLUSIVE:
        return EnvelopePointStatus.INCONCLUSIVE
    return EnvelopePointStatus.FAILED


def correct_envelope_prediction(
    mixture: FluidMixture,
    branch_kind: EnvelopeBranchKind,
    prediction: EnvelopePrediction,
    requested_step_k: float,
    settings: EnvelopeContinuationSettings,
    binary_interactions: BinaryInteractionMapping | None = None,
    binary_interaction_policy: BinaryInteractionPolicy = (
        BinaryInteractionPolicy.DEFAULT_ZERO
    ),
) -> tuple[SaturationPressureResult | None, tuple[EnvelopeCorrectionAttempt, ...]]:
    """Correct one prediction by expanding local Module 8 pressure searches."""

    if prediction.log_pressure < log(settings.minimum_pressure_pa) or (
        prediction.log_pressure > log(settings.maximum_pressure_pa)
    ):
        return None, ()
    attempts: list[EnvelopeCorrectionAttempt] = []
    kind = _saturation_kind(branch_kind)
    for expansion in range(settings.maximum_local_expansions + 1):
        half_span = settings.local_log_pressure_half_span * (
            settings.local_expansion_factor**expansion
        )
        lower = exp(prediction.log_pressure - half_span)
        upper = exp(prediction.log_pressure + half_span)
        lower = max(lower, settings.minimum_pressure_pa)
        upper = min(upper, settings.maximum_pressure_pa)
        if lower >= upper:
            break
        source = (
            EnvelopeCorrectionSource.LOCAL
            if expansion == 0
            else EnvelopeCorrectionSource.EXPANDED_LOCAL
        )
        try:
            result = calculate_saturation_pressure(
                mixture,
                prediction.temperature_k,
                kind,
                lower,
                upper,
                binary_interactions,
                binary_interaction_policy,
                pressure_search_points=5,
                initial_log_k_values=prediction.log_k_values,
                successive_substitution_damping_factor=(
                    settings.successive_substitution_damping_factor
                ),
            )
        except (OverflowError, ValueError) as error:
            reason = f"Continuation-seeded correction failed: {error}"
            attempts.append(
                EnvelopeCorrectionAttempt(
                    source=source,
                    status=EnvelopePointStatus.FAILED,
                    temperature_k=prediction.temperature_k,
                    requested_temperature_step_k=requested_step_k,
                    pressure_bounds_pa=(lower, upper),
                    log_pressure_half_span=half_span,
                    saturation_result=None,
                    accepted=False,
                    failure_reason=reason,
                    diagnostics=(
                        _diagnostic("ENVELOPE_CORRECTOR_NUMERICAL_FAILURE", reason),
                    ),
                )
            )
            continue
        attempt = EnvelopeCorrectionAttempt(
            source=source,
            status=_attempt_status(result),
            temperature_k=prediction.temperature_k,
            requested_temperature_step_k=requested_step_k,
            pressure_bounds_pa=(lower, upper),
            log_pressure_half_span=half_span,
            saturation_result=result,
            accepted=False,
            failure_reason=result.failure_reason,
            diagnostics=result.diagnostics,
        )
        attempts.append(attempt)
        if result.status is SaturationStatus.CONVERGED:
            return result, tuple(attempts)
    if settings.allow_global_fallback:
        try:
            result = calculate_saturation_pressure(
                mixture,
                prediction.temperature_k,
                kind,
                settings.minimum_pressure_pa,
                settings.maximum_pressure_pa,
                binary_interactions,
                binary_interaction_policy,
                successive_substitution_damping_factor=(
                    settings.successive_substitution_damping_factor
                ),
            )
        except (OverflowError, ValueError) as error:
            reason = f"Wilson fallback correction failed: {error}"
            attempts.append(
                EnvelopeCorrectionAttempt(
                    source=EnvelopeCorrectionSource.GLOBAL_FALLBACK,
                    status=EnvelopePointStatus.FAILED,
                    temperature_k=prediction.temperature_k,
                    requested_temperature_step_k=requested_step_k,
                    pressure_bounds_pa=(
                        settings.minimum_pressure_pa,
                        settings.maximum_pressure_pa,
                    ),
                    log_pressure_half_span=None,
                    saturation_result=None,
                    accepted=False,
                    failure_reason=reason,
                    diagnostics=(
                        _diagnostic("ENVELOPE_FALLBACK_NUMERICAL_FAILURE", reason),
                    ),
                )
            )
            return None, tuple(attempts)
        attempts.append(
            EnvelopeCorrectionAttempt(
                source=EnvelopeCorrectionSource.GLOBAL_FALLBACK,
                status=_attempt_status(result),
                temperature_k=prediction.temperature_k,
                requested_temperature_step_k=requested_step_k,
                pressure_bounds_pa=(
                    settings.minimum_pressure_pa,
                    settings.maximum_pressure_pa,
                ),
                log_pressure_half_span=None,
                saturation_result=result,
                accepted=False,
                failure_reason=result.failure_reason,
                diagnostics=result.diagnostics,
            )
        )
        if result.status is SaturationStatus.CONVERGED:
            return result, tuple(attempts)
    return None, tuple(attempts)


def _point_metrics(
    result: SaturationPressureResult,
) -> tuple[tuple[float, ...], float, float, float]:
    if result.parent_phase is None or result.incipient_phase is None:
        raise ValueError("accepted saturation result must preserve both phases.")
    log_k_values = _result_log_k(result)
    root_separation = abs(
        result.parent_phase.selected_compressibility_factor
        - result.incipient_phase.selected_compressibility_factor
    )
    composition_separation = max(
        abs(parent - incipient)
        for parent, incipient in zip(
            result.parent_composition, result.incipient_composition, strict=True
        )
    )
    active_log_k = tuple(
        value
        for fraction, value in zip(result.feed_composition, log_k_values, strict=True)
        if fraction > 0.0
    )
    return (
        log_k_values,
        root_separation,
        composition_separation,
        max(abs(value) for value in active_log_k),
    )


def _validate_converged_result(
    result: SaturationPressureResult,
    mixture: FluidMixture,
    branch_kind: EnvelopeBranchKind,
    expected_provenance: PhaseInteractionProvenance,
    settings: EnvelopeContinuationSettings,
) -> None:
    if result.status is not SaturationStatus.CONVERGED:
        raise ValueError("starting saturation result must be converged.")
    if result.saturation_kind is not _saturation_kind(branch_kind):
        raise ValueError("starting saturation kind does not match the branch.")
    if len(result.feed_composition) != len(mixture.components) or any(
        abs(left - right) > MOLE_FRACTION_TOLERANCE
        for left, right in zip(result.feed_composition, _feed(mixture), strict=True)
    ):
        raise ValueError("starting saturation composition does not match the feed.")
    if tuple(item.component for item in result.feed_mixture.components) != tuple(
        item.component for item in mixture.components
    ):
        raise ValueError("starting saturation components do not match the feed.")
    if _result_provenance(result) != expected_provenance:
        raise ValueError("starting saturation interaction provenance does not match.")
    if (
        not isfinite(result.temperature_k)
        or result.temperature_k <= 0.0
        or result.pressure_pa is None
        or not isfinite(result.pressure_pa)
        or result.pressure_pa <= 0.0
    ):
        raise ValueError("starting saturation temperature and pressure must be valid.")
    if result.failure_reason is not None:
        raise ValueError("starting saturation result contains an unresolved failure.")
    if (
        result.pressure_residual is None
        or abs(result.pressure_residual) > settings.saturation_objective_tolerance
        or result.maximum_fugacity_equilibrium_residual is None
        or result.maximum_fugacity_equilibrium_residual
        > settings.fugacity_equilibrium_tolerance
        or result.composition_sum_residual is None
        or abs(result.composition_sum_residual) > settings.composition_tolerance
        or result.parent_phase is None
        or result.incipient_phase is None
        or result.parent_phase.mechanical_classification
        is not MechanicalStabilityClassification.STABLE
        or result.incipient_phase.mechanical_classification
        is not MechanicalStabilityClassification.STABLE
    ):
        raise ValueError("starting saturation result fails equilibrium gates.")
    if not result.evaluation_history:
        raise ValueError("starting saturation result has no reconstruction history.")
    final_evaluation = result.evaluation_history[-1]
    if (
        final_evaluation.maximum_log_k_residual is None
        or final_evaluation.maximum_log_k_residual > settings.log_k_tolerance
        or final_evaluation.composition_change is None
        or final_evaluation.composition_change > settings.composition_tolerance
    ):
        raise ValueError("starting saturation result fails an inner convergence gate.")
    log_k_values, root_separation, composition_separation, maximum_log_k = (
        _point_metrics(result)
    )
    active_count = sum(fraction > 0.0 for fraction in result.feed_composition)
    if active_count > 1 and maximum_log_k <= TRIVIAL_LOG_K_TOLERANCE:
        raise ValueError("starting saturation result is a trivial unity-K state.")
    if (
        composition_separation <= PHASE_COMPOSITION_DISTINGUISHABILITY_TOLERANCE
        and root_separation <= PHASE_ROOT_DISTINGUISHABILITY_TOLERANCE
    ):
        raise ValueError("starting saturation result has indistinguishable phases.")
    if not all(isfinite(value) for value in log_k_values):
        raise ValueError("starting saturation log K-values must be finite.")


def _make_point(
    branch_kind: EnvelopeBranchKind,
    result: SaturationPressureResult,
    prediction: EnvelopePrediction | None,
    source: EnvelopeCorrectionSource,
    accepted_step_k: float,
    attempts: tuple[EnvelopeCorrectionAttempt, ...],
) -> PhaseEnvelopePoint:
    log_k_values, root_separation, composition_separation, maximum_log_k = (
        _point_metrics(result)
    )
    predictor_pressure_error = (
        0.0
        if prediction is None
        else abs(log(result.pressure_pa or 0.0) - prediction.log_pressure)
    )
    predictor_log_k_error = (
        0.0
        if prediction is None
        else max(
            abs(actual - predicted)
            for actual, predicted in zip(
                log_k_values, prediction.log_k_values, strict=True
            )
        )
    )
    return PhaseEnvelopePoint(
        branch_kind=branch_kind,
        status=EnvelopePointStatus.CONVERGED,
        saturation_result=result,
        prediction=prediction,
        correction_source=source,
        accepted_temperature_step_k=accepted_step_k,
        correction_attempts=attempts,
        log_k_values=log_k_values,
        root_separation=root_separation,
        composition_separation=composition_separation,
        maximum_active_log_k=maximum_log_k,
        predictor_log_pressure_error=predictor_pressure_error,
        predictor_log_k_error=predictor_log_k_error,
        diagnostics=result.diagnostics,
    )


def _branch_jump_reason(
    previous: PhaseEnvelopePoint,
    candidate: PhaseEnvelopePoint,
    settings: EnvelopeContinuationSettings,
) -> str | None:
    composition_change = max(
        abs(new - old)
        for new, old in zip(
            candidate.saturation_result.incipient_composition,
            previous.saturation_result.incipient_composition,
            strict=True,
        )
    )
    consecutive_pressure_change = abs(log(candidate.pressure_pa / previous.pressure_pa))
    if (
        candidate.saturation_result.parent_phase is None
        or candidate.saturation_result.incipient_phase is None
        or previous.saturation_result.parent_phase is None
        or previous.saturation_result.incipient_phase is None
    ):
        return "a branch point lost its reconstructed phase state."
    parent_root_change = abs(
        candidate.saturation_result.parent_phase.selected_compressibility_factor
        - previous.saturation_result.parent_phase.selected_compressibility_factor
    )
    incipient_root_change = abs(
        candidate.saturation_result.incipient_phase.selected_compressibility_factor
        - previous.saturation_result.incipient_phase.selected_compressibility_factor
    )
    if (
        candidate.predictor_log_pressure_error
        > settings.maximum_predictor_log_pressure_error
    ):
        return "corrected log pressure is too far from the continuation predictor."
    if candidate.predictor_log_k_error > settings.maximum_predictor_log_k_error:
        return "corrected log K-values are too far from the continuation predictor."
    if composition_change > settings.maximum_composition_change:
        return "incipient composition changed beyond the branch threshold."
    if consecutive_pressure_change > settings.maximum_consecutive_log_pressure_change:
        return "consecutive pressure change exceeded the branch threshold."
    if max(parent_root_change, incipient_root_change) > settings.maximum_root_change:
        return "selected root change exceeded the branch threshold."
    return None


def _near_critical_diagnostics(
    point: PhaseEnvelopePoint,
    settings: EnvelopeContinuationSettings,
) -> tuple[tuple[EOSDiagnostic, ...], bool]:
    warnings: list[EOSDiagnostic] = []
    severe = 0
    # With one active component the incipient phase has the same composition as
    # the parent and K = 1 is the genuine coexistence condition, exactly as the
    # Module 8 trivial-K rule already recognises. Composition separation and
    # maximum active |ln K| are then identically zero at every temperature, so
    # they carry no near-critical information and only root separation does.
    multiple_active_components = (
        sum(fraction > 0.0 for fraction in point.saturation_result.feed_composition) > 1
    )
    if multiple_active_components:
        if point.composition_separation <= settings.near_critical_composition_warning:
            warnings.append(
                _diagnostic(
                    "ENVELOPE_NEAR_CRITICAL_COMPOSITION",
                    "Parent and incipient compositions are approaching each other.",
                )
            )
        if point.composition_separation <= settings.near_critical_composition_stop:
            severe += 1
        if point.maximum_active_log_k <= settings.near_critical_log_k_warning:
            warnings.append(
                _diagnostic(
                    "ENVELOPE_NEAR_CRITICAL_LOG_K",
                    "Active equilibrium ratios are approaching unity.",
                )
            )
        if point.maximum_active_log_k <= settings.near_critical_log_k_stop:
            severe += 1
    if point.root_separation <= settings.near_critical_root_warning:
        warnings.append(
            _diagnostic(
                "ENVELOPE_NEAR_CRITICAL_ROOTS",
                "Parent and incipient PR roots are approaching each other.",
            )
        )
    if point.root_separation <= settings.near_critical_root_stop:
        severe += 1
    required_indicators = 2 if multiple_active_components else 1
    return tuple(warnings), severe >= required_indicators


def _retry_termination(
    trivial_collapse: bool,
    numerical_failure: bool,
    possible_branch_loss: bool,
    exhausted_reason: EnvelopeTerminationReason,
    exhausted_message: str,
) -> tuple[EnvelopeTerminationReason, str]:
    """Classify why a retry loop produced no acceptable point.

    The evidence gathered during the retries decides the reason. Which limit
    ended the loop -- the minimum temperature step or the retry counter --
    only selects the fallback outcome, so the same physical situation is
    never reported two different ways. The message is returned with the
    reason so the two cannot disagree.
    """

    if trivial_collapse:
        return (
            EnvelopeTerminationReason.NEAR_CRITICAL,
            (
                "Repeated trivial inner collapse ended the branch; the phases "
                "are becoming numerically indistinguishable and this is not an "
                "exact critical point."
            ),
        )
    if numerical_failure:
        return (
            EnvelopeTerminationReason.NUMERICAL_FAILURE,
            "Every correction attempt failed before producing a saturation state.",
        )
    if possible_branch_loss:
        return (
            EnvelopeTerminationReason.BRANCH_LOST,
            "Every corrected point failed a branch-identity check.",
        )
    return exhausted_reason, exhausted_message


@dataclass(frozen=True, slots=True)
class _ContinuationStepOutcome:
    """Immutable outcome of correcting one requested continuation step."""

    accepted_point: PhaseEnvelopePoint | None
    rejected_attempts: tuple[EnvelopeCorrectionAttempt, ...]
    diagnostics: tuple[EOSDiagnostic, ...]
    retry_count: int
    requested_temperature_step_k: float
    termination: tuple[EnvelopeTerminationReason, str] | None


def _attempt_continuation_step(
    mixture: FluidMixture,
    branch_kind: EnvelopeBranchKind,
    settings: EnvelopeContinuationSettings,
    points: tuple[PhaseEnvelopePoint, ...],
    requested_temperature_step_k: float,
    initial_prediction: EnvelopePrediction,
    diagnostics: tuple[EOSDiagnostic, ...],
    expected_provenance: PhaseInteractionProvenance,
    binary_interactions: BinaryInteractionMapping | None,
    binary_interaction_policy: BinaryInteractionPolicy,
) -> _ContinuationStepOutcome:
    """Correct one temperature step, including retries and failure evidence."""

    current = points[-1]
    rejected: list[EnvelopeCorrectionAttempt] = []
    collected_diagnostics = list(diagnostics)
    requested_step = requested_temperature_step_k
    retry = 0
    possible_branch_loss = False
    trivial_collapse = False
    numerical_failure = False
    prediction = initial_prediction
    while retry <= settings.maximum_step_retries:
        if retry > 0:
            target_temperature = current.temperature_k + requested_step
            prediction = predict_envelope_state(
                current,
                target_temperature,
                points[-2] if len(points) > 1 else None,
            )
        collected_diagnostics.extend(
            item for item in prediction.diagnostics if item not in collected_diagnostics
        )
        if prediction.log_pressure < log(settings.minimum_pressure_pa) or (
            prediction.log_pressure > log(settings.maximum_pressure_pa)
        ):
            return _ContinuationStepOutcome(
                None,
                tuple(rejected),
                tuple(collected_diagnostics),
                retry,
                requested_step,
                (
                    EnvelopeTerminationReason.PRESSURE_OUT_OF_BOUNDS,
                    "Predicted pressure lies outside the configured bounds.",
                ),
            )
        result, attempts = correct_envelope_prediction(
            mixture,
            branch_kind,
            prediction,
            requested_step,
            settings,
            binary_interactions,
            binary_interaction_policy,
        )
        if result is not None:
            _validate_converged_result(
                result, mixture, branch_kind, expected_provenance, settings
            )
            source = attempts[-1].source
            candidate = _make_point(
                branch_kind,
                result,
                prediction,
                source,
                requested_step,
                attempts,
            )
            jump_reason = _branch_jump_reason(current, candidate, settings)
            duplicate = any(
                abs(existing.temperature_k - candidate.temperature_k)
                <= TEMPERATURE_UNIQUENESS_TOLERANCE_K
                for existing in points
            )
            if jump_reason is None and not duplicate:
                accepted_attempt = EnvelopeCorrectionAttempt(
                    source=attempts[-1].source,
                    status=attempts[-1].status,
                    temperature_k=attempts[-1].temperature_k,
                    requested_temperature_step_k=(
                        attempts[-1].requested_temperature_step_k
                    ),
                    pressure_bounds_pa=attempts[-1].pressure_bounds_pa,
                    log_pressure_half_span=attempts[-1].log_pressure_half_span,
                    saturation_result=attempts[-1].saturation_result,
                    accepted=True,
                    failure_reason=None,
                    diagnostics=attempts[-1].diagnostics,
                )
                candidate = PhaseEnvelopePoint(
                    branch_kind=candidate.branch_kind,
                    status=candidate.status,
                    saturation_result=candidate.saturation_result,
                    prediction=candidate.prediction,
                    correction_source=candidate.correction_source,
                    accepted_temperature_step_k=candidate.accepted_temperature_step_k,
                    correction_attempts=(*attempts[:-1], accepted_attempt),
                    log_k_values=candidate.log_k_values,
                    root_separation=candidate.root_separation,
                    composition_separation=candidate.composition_separation,
                    maximum_active_log_k=candidate.maximum_active_log_k,
                    predictor_log_pressure_error=candidate.predictor_log_pressure_error,
                    predictor_log_k_error=candidate.predictor_log_k_error,
                    diagnostics=candidate.diagnostics,
                )
                rejected.extend(attempts[:-1])
                collected_diagnostics.extend(
                    item
                    for item in candidate.diagnostics
                    if item not in collected_diagnostics
                )
                return _ContinuationStepOutcome(
                    candidate,
                    tuple(rejected),
                    tuple(collected_diagnostics),
                    retry,
                    requested_step,
                    None,
                )
            possible_branch_loss = jump_reason is not None
            failure = jump_reason or "duplicate envelope point was rejected."
            rejected.extend(
                EnvelopeCorrectionAttempt(
                    source=item.source,
                    status=EnvelopePointStatus.REJECTED,
                    temperature_k=item.temperature_k,
                    requested_temperature_step_k=item.requested_temperature_step_k,
                    pressure_bounds_pa=item.pressure_bounds_pa,
                    log_pressure_half_span=item.log_pressure_half_span,
                    saturation_result=item.saturation_result,
                    accepted=False,
                    failure_reason=failure,
                    diagnostics=(
                        *item.diagnostics,
                        _diagnostic("ENVELOPE_BRANCH_JUMP", failure),
                    ),
                )
                for item in attempts
            )
        else:
            rejected.extend(attempts)
            numerical_failure = (
                numerical_failure
                or bool(attempts)
                and all(item.saturation_result is None for item in attempts)
            )
            # The Module 8 diagnostic preserves trivial-collapse evidence when
            # its enclosing bracket failure has a more general reason string.
            trivial_collapse = trivial_collapse or any(
                (
                    item.failure_reason is not None
                    and "trivial" in item.failure_reason.lower()
                )
                or any(
                    entry.code == TRIVIAL_STATE_DIAGNOSTIC_CODE
                    for entry in item.diagnostics
                )
                for item in attempts
            )
        retry += 1
        next_magnitude = abs(requested_step) * settings.retry_step_reduction_factor
        if next_magnitude < settings.minimum_temperature_step_k:
            termination = _retry_termination(
                trivial_collapse,
                numerical_failure,
                possible_branch_loss,
                EnvelopeTerminationReason.MINIMUM_STEP_REACHED,
                "Minimum temperature step reached without an acceptable correction.",
            )
            return _ContinuationStepOutcome(
                None,
                tuple(rejected),
                tuple(collected_diagnostics),
                retry,
                requested_step,
                termination,
            )
        requested_step = (1.0 if requested_step > 0.0 else -1.0) * next_magnitude
    termination = _retry_termination(
        trivial_collapse,
        numerical_failure,
        possible_branch_loss,
        EnvelopeTerminationReason.CORRECTOR_FAILED,
        "Continuation retry limit reached without an acceptable point.",
    )
    return _ContinuationStepOutcome(
        None,
        tuple(rejected),
        tuple(collected_diagnostics),
        retry,
        requested_step,
        termination,
    )


def trace_phase_envelope_branch(
    mixture: FluidMixture,
    branch_kind: EnvelopeBranchKind,
    settings: EnvelopeContinuationSettings,
    start_temperature_k: float | None = None,
    starting_result: SaturationPressureResult | None = None,
    binary_interactions: BinaryInteractionMapping | None = None,
    binary_interaction_policy: BinaryInteractionPolicy = (
        BinaryInteractionPolicy.DEFAULT_ZERO
    ),
) -> PhaseEnvelopeBranchResult:
    """Trace one ordered bubble or dew branch by natural temperature continuation."""

    if not isinstance(branch_kind, EnvelopeBranchKind):
        raise ValueError("branch_kind must be an EnvelopeBranchKind.")
    if starting_result is None:
        if (
            start_temperature_k is None
            or not isfinite(start_temperature_k)
            or start_temperature_k <= 0.0
        ):
            raise ValueError("a finite positive start temperature is required.")
        initial = calculate_saturation_pressure(
            mixture,
            start_temperature_k,
            _saturation_kind(branch_kind),
            settings.minimum_pressure_pa,
            settings.maximum_pressure_pa,
            binary_interactions,
            binary_interaction_policy,
            successive_substitution_damping_factor=(
                settings.successive_substitution_damping_factor
            ),
        )
        if initial.status is not SaturationStatus.CONVERGED:
            return _empty_branch(
                mixture,
                branch_kind,
                settings,
                EnvelopeTerminationReason.CORRECTOR_FAILED,
                initial.failure_reason or "starting saturation solve failed.",
                binary_interaction_policy,
                _result_provenance(initial),
                initial.diagnostics,
            )
    else:
        initial = starting_result
        if start_temperature_k is not None and not isclose(
            start_temperature_k,
            initial.temperature_k,
            rel_tol=0.0,
            abs_tol=TEMPERATURE_UNIQUENESS_TOLERANCE_K,
        ):
            raise ValueError("start temperature does not match the supplied result.")
    if initial.pressure_pa is None:
        raise ValueError("starting result must contain pressure.")
    if not (
        settings.minimum_pressure_pa
        <= initial.pressure_pa
        <= settings.maximum_pressure_pa
    ):
        raise ValueError("starting result pressure lies outside configured bounds.")
    expected_provenance = _provenance(
        mixture,
        initial.temperature_k,
        initial.pressure_pa,
        binary_interactions,
        binary_interaction_policy,
    )
    _validate_converged_result(
        initial, mixture, branch_kind, expected_provenance, settings
    )
    direction = 1.0 if settings.target_temperature_k > initial.temperature_k else -1.0
    if isclose(
        settings.target_temperature_k,
        initial.temperature_k,
        rel_tol=0.0,
        abs_tol=TEMPERATURE_UNIQUENESS_TOLERANCE_K,
    ):
        direction = 1.0 if settings.initial_temperature_step_k > 0.0 else -1.0
    if settings.initial_temperature_step_k * direction <= 0.0:
        raise ValueError("initial temperature step points away from the target.")
    initial_point = _make_point(
        branch_kind,
        initial,
        None,
        EnvelopeCorrectionSource.STARTING_SATURATION,
        0.0,
        (),
    )
    points = [initial_point]
    rejected: list[EnvelopeCorrectionAttempt] = []
    diagnostics = list(initial.diagnostics)
    if isclose(
        settings.target_temperature_k,
        initial.temperature_k,
        rel_tol=0.0,
        abs_tol=TEMPERATURE_UNIQUENESS_TOLERANCE_K,
    ):
        return _finish_branch(
            mixture,
            branch_kind,
            settings,
            points,
            rejected,
            EnvelopeTerminationReason.TARGET_REACHED,
            "Starting point is already at the target temperature.",
            diagnostics,
            expected_provenance,
        )
    if settings.maximum_points == 1:
        return _finish_branch(
            mixture,
            branch_kind,
            settings,
            points,
            rejected,
            EnvelopeTerminationReason.MAXIMUM_POINTS,
            "Maximum accepted point count reached.",
            diagnostics,
            expected_provenance,
        )
    step = settings.initial_temperature_step_k
    while len(points) < settings.maximum_points:
        current = points[-1]
        remaining = settings.target_temperature_k - current.temperature_k
        if direction * remaining <= TEMPERATURE_UNIQUENESS_TOLERANCE_K:
            return _finish_branch(
                mixture,
                branch_kind,
                settings,
                points,
                rejected,
                EnvelopeTerminationReason.TARGET_REACHED,
                "Target temperature reached.",
                diagnostics,
                expected_provenance,
            )
        requested_step = direction * min(abs(step), abs(remaining))
        prediction = predict_envelope_state(
            current,
            current.temperature_k + requested_step,
            points[-2] if len(points) > 1 else None,
        )
        outcome = _attempt_continuation_step(
            mixture,
            branch_kind,
            settings,
            tuple(points),
            requested_step,
            prediction,
            tuple(diagnostics),
            expected_provenance,
            binary_interactions,
            binary_interaction_policy,
        )
        rejected.extend(outcome.rejected_attempts)
        diagnostics = list(outcome.diagnostics)
        if outcome.termination is not None:
            termination, message = outcome.termination
            return _finish_branch(
                mixture,
                branch_kind,
                settings,
                points,
                rejected,
                termination,
                message,
                diagnostics,
                expected_provenance,
            )
        candidate = outcome.accepted_point
        assert candidate is not None
        points.append(candidate)
        near_diagnostics, terminate_near = _near_critical_diagnostics(
            candidate, settings
        )
        diagnostics.extend(item for item in near_diagnostics if item not in diagnostics)
        if terminate_near:
            return _finish_branch(
                mixture,
                branch_kind,
                settings,
                points,
                rejected,
                EnvelopeTerminationReason.NEAR_CRITICAL,
                (
                    "Phase distinctions entered the near-critical stop band; "
                    "this is not an exact critical point."
                ),
                diagnostics,
                expected_provenance,
            )
        if (
            direction * (settings.target_temperature_k - candidate.temperature_k)
            <= TEMPERATURE_UNIQUENESS_TOLERANCE_K
        ):
            return _finish_branch(
                mixture,
                branch_kind,
                settings,
                points,
                rejected,
                EnvelopeTerminationReason.TARGET_REACHED,
                "Target temperature reached.",
                diagnostics,
                expected_provenance,
            )
        final_inner_iterations = len(
            candidate.saturation_result.evaluation_history[-1].history
        )
        easy = (
            candidate.correction_source is EnvelopeCorrectionSource.LOCAL
            and outcome.retry_count == 0
            and final_inner_iterations <= settings.easy_iteration_limit
            and candidate.predictor_log_pressure_error
            < settings.easy_predictor_log_pressure_error
            and candidate.predictor_log_k_error < settings.easy_predictor_log_k_error
        )
        factor = (
            settings.step_increase_factor if easy else settings.step_decrease_factor
        )
        step = direction * min(
            settings.maximum_temperature_step_k,
            max(
                settings.minimum_temperature_step_k,
                abs(outcome.requested_temperature_step_k) * factor,
            ),
        )
    return _finish_branch(
        mixture,
        branch_kind,
        settings,
        points,
        rejected,
        EnvelopeTerminationReason.MAXIMUM_POINTS,
        "Maximum accepted point count reached.",
        diagnostics,
        expected_provenance,
    )


def _finish_branch(
    mixture: FluidMixture,
    branch_kind: EnvelopeBranchKind,
    settings: EnvelopeContinuationSettings,
    points: list[PhaseEnvelopePoint],
    rejected: list[EnvelopeCorrectionAttempt],
    reason: EnvelopeTerminationReason,
    message: str,
    diagnostics: list[EOSDiagnostic],
    provenance: PhaseInteractionProvenance,
) -> PhaseEnvelopeBranchResult:
    return PhaseEnvelopeBranchResult(
        branch_kind=branch_kind,
        feed_mixture=mixture,
        feed_composition=_feed(mixture),
        settings=settings,
        points=tuple(points),
        rejected_attempts=tuple(rejected),
        termination_reason=reason,
        termination_message=message,
        diagnostics=tuple(dict.fromkeys(diagnostics)),
        binary_interaction_policy=provenance.binary_interaction_policy,
        binary_interactions=provenance.binary_interactions,
        supplied_binary_interaction_pairs=provenance.supplied_binary_interaction_pairs,
        defaulted_binary_interaction_pairs=provenance.defaulted_binary_interaction_pairs,
    )


def _empty_branch(
    mixture: FluidMixture,
    branch_kind: EnvelopeBranchKind,
    settings: EnvelopeContinuationSettings,
    reason: EnvelopeTerminationReason,
    message: str,
    policy: BinaryInteractionPolicy,
    provenance: PhaseInteractionProvenance,
    diagnostics: tuple[EOSDiagnostic, ...],
) -> PhaseEnvelopeBranchResult:
    if policy is not provenance.binary_interaction_policy:
        raise ValueError("empty branch provenance policy is inconsistent.")
    return _finish_branch(
        mixture,
        branch_kind,
        settings,
        [],
        [],
        reason,
        message,
        list(diagnostics),
        provenance,
    )


def trace_bubble_branch(
    mixture: FluidMixture,
    settings: EnvelopeContinuationSettings,
    start_temperature_k: float | None = None,
    starting_result: SaturationPressureResult | None = None,
    binary_interactions: BinaryInteractionMapping | None = None,
    binary_interaction_policy: BinaryInteractionPolicy = (
        BinaryInteractionPolicy.DEFAULT_ZERO
    ),
) -> PhaseEnvelopeBranchResult:
    """Trace the bubble branch independently from a valid bubble start."""

    return trace_phase_envelope_branch(
        mixture,
        EnvelopeBranchKind.BUBBLE,
        settings,
        start_temperature_k,
        starting_result,
        binary_interactions,
        binary_interaction_policy,
    )


def trace_dew_branch(
    mixture: FluidMixture,
    settings: EnvelopeContinuationSettings,
    start_temperature_k: float | None = None,
    starting_result: SaturationPressureResult | None = None,
    binary_interactions: BinaryInteractionMapping | None = None,
    binary_interaction_policy: BinaryInteractionPolicy = (
        BinaryInteractionPolicy.DEFAULT_ZERO
    ),
) -> PhaseEnvelopeBranchResult:
    """Trace the dew branch independently from a valid dew start."""

    return trace_phase_envelope_branch(
        mixture,
        EnvelopeBranchKind.DEW,
        settings,
        start_temperature_k,
        starting_result,
        binary_interactions,
        binary_interaction_policy,
    )


def calculate_phase_envelope(
    mixture: FluidMixture,
    bubble_settings: EnvelopeContinuationSettings,
    dew_settings: EnvelopeContinuationSettings,
    bubble_start_temperature_k: float,
    dew_start_temperature_k: float,
    binary_interactions: BinaryInteractionMapping | None = None,
    binary_interaction_policy: BinaryInteractionPolicy = (
        BinaryInteractionPolicy.DEFAULT_ZERO
    ),
) -> PhaseEnvelopeResult:
    """Trace bubble and dew branches from independently solved starting states."""

    bubble = trace_bubble_branch(
        mixture,
        bubble_settings,
        bubble_start_temperature_k,
        binary_interactions=binary_interactions,
        binary_interaction_policy=binary_interaction_policy,
    )
    dew = trace_dew_branch(
        mixture,
        dew_settings,
        dew_start_temperature_k,
        binary_interactions=binary_interactions,
        binary_interaction_policy=binary_interaction_policy,
    )
    separations: list[tuple[float, float]] = []
    diagnostics: list[EOSDiagnostic] = []
    for bubble_point in bubble.points:
        for dew_point in dew.points:
            if (
                abs(bubble_point.temperature_k - dew_point.temperature_k)
                <= TEMPERATURE_UNIQUENESS_TOLERANCE_K
            ):
                relative_separation = abs(
                    bubble_point.pressure_pa - dew_point.pressure_pa
                ) / max(bubble_point.pressure_pa, dew_point.pressure_pa)
                separations.append((bubble_point.temperature_k, relative_separation))
                if relative_separation <= CROSS_BRANCH_PRESSURE_RELATIVE_TOLERANCE:
                    diagnostics.append(
                        _diagnostic(
                            "ENVELOPE_BRANCH_PRESSURES_APPROACHING",
                            (
                                "Bubble and dew pressures are approaching at "
                                "a shared temperature; this is not an exact "
                                "critical-point calculation."
                            ),
                        )
                    )
                break
    return PhaseEnvelopeResult(
        mixture,
        bubble,
        dew,
        tuple(separations),
        tuple(dict.fromkeys(diagnostics)),
    )
