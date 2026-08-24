"""Safeguarded fixed-composition mixture critical-point solver.

Module 20 solves the two signed Module 19 conditions ``lambda_min = 0`` and
``C = 0`` in ``q = (ln(T), ln(P))``.  It does not redefine criticality,
change composition, fit interactions, or merge phase-boundary continuation
with critical-point solving.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from math import exp, isfinite, log, sqrt
from typing import Final

import numpy as np
from numpy.typing import NDArray

from pvt_phase_simulator.eos.criticality import (
    CriticalityStatus,
    MixtureCriticalityResult,
    calculate_stable_root_mixture_criticality,
    criticality_residual_pair,
)
from pvt_phase_simulator.eos.mixing_rules import (
    BinaryInteractionMapping,
    BinaryInteractionPolicy,
    calculate_peng_robinson_mixture_parameters,
)
from pvt_phase_simulator.eos.peng_robinson import (
    calculate_compressibility_roots,
    classify_mechanical_stability,
)
from pvt_phase_simulator.fluid_models import FluidMixture

Vector = NDArray[np.float64]
ResidualEvaluator = Callable[
    [tuple[float, float], tuple[float, ...] | None], "CriticalResidualEvaluation"
]

DEFAULT_TEMPERATURE_MIN_K: Final = 100.0
DEFAULT_TEMPERATURE_MAX_K: Final = 1_000.0
DEFAULT_PRESSURE_MIN_PA: Final = 1_000.0
DEFAULT_PRESSURE_MAX_PA: Final = 100_000_000.0


class CriticalPointStatus(StrEnum):
    """Structured disposition of a mixture critical-point solve."""

    CONVERGED = "converged"
    INITIALIZATION_FAILED = "initialization_failed"
    CRITICALITY_NOT_APPLICABLE = "criticality_not_applicable"
    JACOBIAN_FAILED = "jacobian_failed"
    ILL_CONDITIONED = "ill_conditioned"
    LINE_SEARCH_FAILED = "line_search_failed"
    BOUNDS_REACHED = "bounds_reached"
    MAXIMUM_ITERATIONS = "maximum_iterations"
    FINAL_VALIDATION_FAILED = "final_validation_failed"
    INSUFFICIENT_ACTIVE_COMPONENTS = "insufficient_active_components"


class _CriticalityNotApplicableError(ValueError):
    """A candidate has a structured non-applicable Module 19 result."""


class _RootContinuityError(ValueError):
    """A finite-difference or line-search sample changed PR root branch."""


class JacobianStepFailure(StrEnum):
    """Deterministic disposition of one attempted Richardson stencil."""

    ROOT_CONTINUITY = "root_continuity"
    NON_APPLICABLE = "non_applicable"
    NUMERICAL_NONCONVERGENCE = "numerical_nonconvergence"
    NONFINITE = "nonfinite"
    BOUNDS = "bounds"


@dataclass(frozen=True, slots=True)
class CriticalPointSolverSettings:
    """Deterministic controls for the ``(ln(T), ln(P))`` solve."""

    minimum_temperature_k: float = DEFAULT_TEMPERATURE_MIN_K
    maximum_temperature_k: float = DEFAULT_TEMPERATURE_MAX_K
    minimum_pressure_pa: float = DEFAULT_PRESSURE_MIN_PA
    maximum_pressure_pa: float = DEFAULT_PRESSURE_MAX_PA
    lambda_tolerance: float = 1.0e-7
    cubic_tolerance: float = 1.0e-6
    scaled_norm_tolerance: float = 1.0e-6
    lambda_scale: float | None = None
    cubic_scale: float | None = None
    lambda_scale_floor: float = 1.0
    cubic_scale_floor: float = 1.0
    jacobian_log_step: float = 1.0e-3
    minimum_jacobian_log_step: float = 1.0e-7
    jacobian_absolute_tolerance: float = 1.0e-6
    jacobian_relative_tolerance: float = 2.0e-4
    maximum_jacobian_step_reductions: int = 8
    maximum_iterations: int = 20
    maximum_jacobian_condition_number: float = 1.0e10
    maximum_log_temperature_step: float = 0.15
    maximum_log_pressure_step: float = 0.35
    line_search_reduction_factor: float = 0.5
    minimum_line_search_factor: float = 1.0e-6
    maximum_backtracking_iterations: int = 20

    def __post_init__(self) -> None:
        positive = (
            self.minimum_temperature_k,
            self.maximum_temperature_k,
            self.minimum_pressure_pa,
            self.maximum_pressure_pa,
            self.lambda_tolerance,
            self.cubic_tolerance,
            self.scaled_norm_tolerance,
            self.lambda_scale_floor,
            self.cubic_scale_floor,
            self.jacobian_log_step,
            self.minimum_jacobian_log_step,
            self.jacobian_absolute_tolerance,
            self.jacobian_relative_tolerance,
            self.maximum_jacobian_condition_number,
            self.maximum_log_temperature_step,
            self.maximum_log_pressure_step,
            self.line_search_reduction_factor,
            self.minimum_line_search_factor,
        )
        if not all(isfinite(value) and value > 0.0 for value in positive):
            raise ValueError("critical-point scalar controls must be positive finite")
        optional_scales = (self.lambda_scale, self.cubic_scale)
        if any(
            value is not None and (not isfinite(value) or value <= 0.0)
            for value in optional_scales
        ):
            raise ValueError("explicit residual scales must be positive finite")
        if self.minimum_temperature_k >= self.maximum_temperature_k:
            raise ValueError("minimum temperature must be below maximum temperature")
        if self.minimum_pressure_pa >= self.maximum_pressure_pa:
            raise ValueError("minimum pressure must be below maximum pressure")
        if self.minimum_jacobian_log_step > self.jacobian_log_step:
            raise ValueError(
                "minimum_jacobian_log_step must not exceed jacobian_log_step"
            )
        if not 0.0 < self.line_search_reduction_factor < 1.0:
            raise ValueError("line-search reduction must lie between zero and one")
        if not 0.0 < self.minimum_line_search_factor < 1.0:
            raise ValueError("minimum line-search factor must lie between zero and one")
        integer_controls = (
            self.maximum_jacobian_step_reductions,
            self.maximum_iterations,
            self.maximum_backtracking_iterations,
        )
        if any(type(value) is not int or value < 0 for value in integer_controls):
            raise ValueError(
                "critical-point iteration controls must be non-negative integers"
            )
        if self.maximum_iterations == 0:
            raise ValueError("maximum_iterations must be positive")


DEFAULT_CRITICAL_POINT_SETTINGS: Final = CriticalPointSolverSettings()


@dataclass(frozen=True, slots=True)
class ResidualScaling:
    """Fixed diagonal scaling retained for the entire nonlinear solve."""

    lambda_scale: float
    cubic_scale: float

    def scaled(self, raw: tuple[float, float]) -> tuple[float, float]:
        return raw[0] / self.lambda_scale, raw[1] / self.cubic_scale


@dataclass(frozen=True, slots=True)
class RootBranchIdentity:
    """Ordered PR-root topology and selected stable-parent branch."""

    root_count: int
    classifications: tuple[str, ...]
    selected_index: int
    selected_compressibility_factor: float
    ordered_roots: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class JacobianStepAttempt:
    """Audit evidence for one complete Richardson stencil attempt."""

    step: float
    outcome: JacobianStepFailure
    maximum_error_ratio: float | None
    reason: str


@dataclass(frozen=True, slots=True)
class CriticalResidualEvaluation:
    """One finite signed residual evaluation in ``q=(ln(T),ln(P))``."""

    log_coordinates: tuple[float, float]
    temperature_k: float
    pressure_pa: float
    raw_residuals: tuple[float, float]
    critical_direction: tuple[float, ...]
    criticality_result: MixtureCriticalityResult | None = None
    root_identity: RootBranchIdentity | None = None


@dataclass(frozen=True, slots=True)
class CriticalResidualJacobian:
    """Richardson Jacobian and its finite-difference evidence."""

    raw_jacobian: tuple[tuple[float, float], tuple[float, float]] | None
    scaled_jacobian: tuple[tuple[float, float], tuple[float, float]] | None
    requested_step: float
    base_step: float | None
    refined_step: float | None
    refined_jacobian: tuple[tuple[float, float], tuple[float, float]] | None
    estimated_errors: tuple[tuple[float, float], tuple[float, float]] | None
    error_thresholds: tuple[tuple[float, float], tuple[float, float]] | None
    attempts: tuple[JacobianStepAttempt, ...]
    step_reductions: int
    function_evaluations: int
    applicable: bool
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class CriticalPointIteration:
    """Compact evidence for the initial state or one accepted Newton step."""

    iteration: int
    temperature_k: float
    pressure_pa: float
    lambda_min: float
    cubic_coefficient: float
    scaled_residual_norm: float
    merit: float
    jacobian_condition_number: float | None
    step_norm: float
    line_search_factor: float
    rejected_trials: int
    jacobian_base_step: float | None
    jacobian_estimated_errors: tuple[tuple[float, float], tuple[float, float]] | None


@dataclass(frozen=True, slots=True)
class QuarticDiagnostic:
    """Optional higher-order regularity evidence (not a solve residual)."""

    coefficient: float | None
    classification: str
    reason: str


@dataclass(frozen=True, slots=True)
class MixtureCriticalPointResult:
    """Immutable critical solve, convergence, and certification evidence."""

    status: CriticalPointStatus
    temperature_k: float | None
    pressure_pa: float | None
    composition: tuple[float, ...]
    lambda_min: float | None
    cubic_coefficient: float | None
    scaled_residual_norm: float | None
    critical_direction: tuple[float, ...] | None
    criticality_result: MixtureCriticalityResult | None
    iterations: int
    accepted_steps: int
    rejected_steps: int
    function_evaluations: int
    residual_scaling: ResidualScaling | None
    history: tuple[CriticalPointIteration, ...]
    jacobian_condition_history: tuple[float, ...]
    initialization_source: str
    termination_reason: str
    quartic_diagnostic: QuarticDiagnostic | None


@dataclass(frozen=True, slots=True)
class CriticalPointScanSettings:
    """User-bounded deterministic diagnostic grid; not a critical solver."""

    minimum_temperature_k: float
    maximum_temperature_k: float
    minimum_pressure_pa: float
    maximum_pressure_pa: float
    temperature_points: int = 7
    pressure_points: int = 7
    lambda_scale: float = 1.0
    cubic_scale: float = 1.0

    def __post_init__(self) -> None:
        values = (
            self.minimum_temperature_k,
            self.maximum_temperature_k,
            self.minimum_pressure_pa,
            self.maximum_pressure_pa,
            self.lambda_scale,
            self.cubic_scale,
        )
        if not all(isfinite(value) and value > 0.0 for value in values):
            raise ValueError("scan bounds and scales must be positive finite")
        if self.minimum_temperature_k >= self.maximum_temperature_k:
            raise ValueError("scan temperature bounds are reversed")
        if self.minimum_pressure_pa >= self.maximum_pressure_pa:
            raise ValueError("scan pressure bounds are reversed")
        if any(
            type(value) is not int or value < 2
            for value in (self.temperature_points, self.pressure_points)
        ):
            raise ValueError("scan dimensions must be integers of at least two")


@dataclass(frozen=True, slots=True)
class CriticalPointScanEntry:
    temperature_k: float
    pressure_pa: float
    status: CriticalityStatus
    lambda_min: float | None
    cubic_coefficient: float | None
    scaled_residual_norm: float | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class CriticalPointScanResult:
    settings: CriticalPointScanSettings
    composition: tuple[float, ...]
    entries: tuple[CriticalPointScanEntry, ...]
    best_applicable_entry: CriticalPointScanEntry | None


def log_coordinates(temperature_k: float, pressure_pa: float) -> tuple[float, float]:
    """Return the documented coordinate order ``(ln(T), ln(P))``."""

    if not all(
        isfinite(value) and value > 0.0 for value in (temperature_k, pressure_pa)
    ):
        raise ValueError("temperature and pressure must be positive finite")
    return log(temperature_k), log(pressure_pa)


def physical_coordinates(log_state: tuple[float, float]) -> tuple[float, float]:
    """Map ``(ln(T), ln(P))`` to positive ``(T, P)``."""

    if len(log_state) != 2 or not all(isfinite(value) for value in log_state):
        raise ValueError("log state must contain two finite coordinates")
    try:
        temperature_k, pressure_pa = (exp(log_state[0]), exp(log_state[1]))
    except OverflowError as error:
        raise ValueError("log state cannot be transformed to finite T and P") from error
    if not all(
        isfinite(value) and value > 0.0 for value in (temperature_k, pressure_pa)
    ):
        raise ValueError("transformed temperature and pressure must be positive finite")
    return temperature_k, pressure_pa


def _within_bounds(
    temperature_k: float, pressure_pa: float, settings: CriticalPointSolverSettings
) -> bool:
    return (
        settings.minimum_temperature_k
        <= temperature_k
        <= settings.maximum_temperature_k
        and settings.minimum_pressure_pa <= pressure_pa <= settings.maximum_pressure_pa
    )


def _norm(values: tuple[float, float]) -> float:
    return sqrt(values[0] ** 2 + values[1] ** 2)


def _converged(
    evaluation: CriticalResidualEvaluation,
    scaling: ResidualScaling,
    settings: CriticalPointSolverSettings,
) -> bool:
    raw = evaluation.raw_residuals
    return (
        abs(raw[0]) <= settings.lambda_tolerance
        and abs(raw[1]) <= settings.cubic_tolerance
        and _norm(scaling.scaled(raw)) <= settings.scaled_norm_tolerance
    )


def _scaling_from_initial(
    raw: tuple[float, float], settings: CriticalPointSolverSettings
) -> ResidualScaling:
    return ResidualScaling(
        settings.lambda_scale
        if settings.lambda_scale is not None
        else max(abs(raw[0]), settings.lambda_scale_floor),
        settings.cubic_scale
        if settings.cubic_scale is not None
        else max(abs(raw[1]), settings.cubic_scale_floor),
    )


def _validate_evaluation(
    evaluation: CriticalResidualEvaluation,
    previous_direction: tuple[float, ...] | None,
) -> None:
    if not all(isfinite(value) for value in evaluation.raw_residuals):
        raise ValueError("critical residuals must be finite")
    direction = np.asarray(evaluation.critical_direction, dtype=float)
    if direction.ndim != 1 or direction.size == 0 or not np.all(np.isfinite(direction)):
        raise ValueError("critical direction must be a nonempty finite vector")
    if previous_direction is not None:
        previous = np.asarray(previous_direction, dtype=float)
        if previous.shape != direction.shape:
            raise ValueError("critical-direction dimension changed")
        if float(np.dot(direction, previous)) <= 0.0:
            raise ValueError("critical-direction orientation continuity was lost")
    result = evaluation.criticality_result
    if result is not None:
        if result.status is not CriticalityStatus.APPLICABLE:
            raise ValueError("attached Module 19 result is not applicable")
        if not result.fixed_root_applicable:
            raise ValueError("attached Module 19 result is not fixed-root applicable")
        if (
            result.symmetry_defect is None
            or result.symmetry_tolerance is None
            or result.symmetry_defect > result.symmetry_tolerance
        ):
            raise ValueError("attached Module 19 Hessian failed its symmetry policy")
        if abs(float(np.sum(direction))) > 1.0e-12:
            raise ValueError("critical direction is outside the composition tangent")
        if abs(float(np.linalg.norm(direction)) - 1.0) > 1.0e-12:
            raise ValueError("critical direction is not normalized")


def _validate_root_continuity(
    base: CriticalResidualEvaluation,
    trial: CriticalResidualEvaluation,
) -> None:
    """Require a sample to remain on the base evaluation's selected PR root."""

    base_identity = base.root_identity
    trial_identity = trial.root_identity
    if base_identity is None and trial_identity is None:
        return
    if base_identity is None or trial_identity is None:
        raise _RootContinuityError(
            "PR root-branch identity was not supplied consistently"
        )
    if base_identity.root_count != trial_identity.root_count:
        raise _RootContinuityError("physical PR root count changed across the sample")
    if base_identity.classifications != trial_identity.classifications:
        raise _RootContinuityError(
            "ordered PR mechanical-stability classifications changed"
        )
    if base_identity.selected_index != trial_identity.selected_index:
        raise _RootContinuityError("stable-parent PR root index changed")

    distances = tuple(
        abs(root - base_identity.selected_compressibility_factor)
        for root in trial_identity.ordered_roots
    )
    minimum_distance = min(distances)
    scale = max(
        1.0,
        abs(base_identity.selected_compressibility_factor),
        *(abs(root) for root in trial_identity.ordered_roots),
    )
    near_indices = tuple(
        index
        for index, distance in enumerate(distances)
        if abs(distance - minimum_distance) <= 1.0e-12 * scale
    )
    if near_indices != (trial_identity.selected_index,):
        raise _RootContinuityError(
            "selected PR root was not the unique continuation of the base root"
        )


def calculate_critical_residual_jacobian(
    evaluator: ResidualEvaluator,
    base: CriticalResidualEvaluation,
    scaling: ResidualScaling,
    settings: CriticalPointSolverSettings,
) -> CriticalResidualJacobian:
    """Differentiate signed residuals in ``(ln(T),ln(P))`` by Richardson FD."""

    requested = settings.jacobian_log_step
    evaluations = 0
    attempts: list[JacobianStepAttempt] = []
    last_reason: str | None = None
    for reduction in range(settings.maximum_jacobian_step_reductions + 1):
        step = requested * 0.5**reduction
        if step < settings.minimum_jacobian_log_step:
            last_reason = "Jacobian step fell below minimum_jacobian_log_step"
            attempts.append(
                JacobianStepAttempt(step, JacobianStepFailure.BOUNDS, None, last_reason)
            )
            break
        coarse = np.empty((2, 2), dtype=float)
        refined = np.empty((2, 2), dtype=float)
        failed = False
        failure_outcome = JacobianStepFailure.NON_APPLICABLE
        for column in range(2):
            samples: list[Vector] = []
            for displacement in (step, -step, step / 2.0, -step / 2.0):
                coordinates = list(base.log_coordinates)
                coordinates[column] += displacement
                trial_q = (float(coordinates[0]), float(coordinates[1]))
                try:
                    temperature_k, pressure_pa = physical_coordinates(trial_q)
                    if not _within_bounds(temperature_k, pressure_pa, settings):
                        failure_outcome = JacobianStepFailure.BOUNDS
                        raise ValueError(
                            "Jacobian sample temperature or pressure was outside bounds"
                        )
                    evaluations += 1
                    trial = evaluator(trial_q, base.critical_direction)
                    _validate_evaluation(trial, base.critical_direction)
                    _validate_root_continuity(base, trial)
                except _RootContinuityError as error:
                    last_reason = str(error)
                    failure_outcome = JacobianStepFailure.ROOT_CONTINUITY
                    failed = True
                    break
                except (FloatingPointError, OverflowError) as error:
                    last_reason = str(error)
                    failure_outcome = JacobianStepFailure.NONFINITE
                    failed = True
                    break
                except (TypeError, ValueError) as error:
                    last_reason = str(error)
                    failed = True
                    break
                samples.append(np.asarray(trial.raw_residuals, dtype=float))
            if failed:
                break
            coarse[:, column] = (samples[0] - samples[1]) / (2.0 * step)
            refined[:, column] = (samples[2] - samples[3]) / step
        if failed:
            attempts.append(
                JacobianStepAttempt(step, failure_outcome, None, last_reason or "")
            )
            continue
        richardson = (4.0 * refined - coarse) / 3.0
        errors = np.abs(richardson - refined)
        if not np.all(np.isfinite(richardson)) or not np.all(np.isfinite(errors)):
            last_reason = "critical-residual Jacobian was non-finite"
            attempts.append(
                JacobianStepAttempt(
                    step, JacobianStepFailure.NONFINITE, None, last_reason
                )
            )
            continue
        thresholds = settings.jacobian_absolute_tolerance + (
            settings.jacobian_relative_tolerance
            * np.maximum(1.0, np.maximum(np.abs(richardson), np.abs(refined)))
        )
        error_ratios = errors / thresholds
        maximum_error_ratio = float(np.max(error_ratios))
        if maximum_error_ratio > 1.0:
            last_reason = (
                "Richardson Jacobian failed numerical-convergence tolerance "
                f"(maximum error ratio {maximum_error_ratio:.6g})"
            )
            attempts.append(
                JacobianStepAttempt(
                    step,
                    JacobianStepFailure.NUMERICAL_NONCONVERGENCE,
                    maximum_error_ratio,
                    last_reason,
                )
            )
            continue
        scaled = (
            np.diag((1.0 / scaling.lambda_scale, 1.0 / scaling.cubic_scale))
            @ richardson
        )
        raw_tuple = tuple(tuple(float(value) for value in row) for row in richardson)
        scaled_tuple = tuple(tuple(float(value) for value in row) for row in scaled)
        error_tuple = tuple(tuple(float(value) for value in row) for row in errors)
        refined_tuple = tuple(tuple(float(value) for value in row) for row in refined)
        threshold_tuple = tuple(
            tuple(float(value) for value in row) for row in thresholds
        )
        return CriticalResidualJacobian(
            raw_tuple,  # type: ignore[arg-type]
            scaled_tuple,  # type: ignore[arg-type]
            requested,
            step,
            step / 2.0,
            refined_tuple,  # type: ignore[arg-type]
            error_tuple,  # type: ignore[arg-type]
            threshold_tuple,  # type: ignore[arg-type]
            tuple(attempts),
            reduction,
            evaluations,
            True,
            None,
        )
    return CriticalResidualJacobian(
        None,
        None,
        requested,
        None,
        None,
        None,
        None,
        None,
        tuple(attempts),
        settings.maximum_jacobian_step_reductions + 1,
        evaluations,
        False,
        last_reason or "no applicable symmetric Jacobian stencil was available",
    )


def _result(
    status: CriticalPointStatus,
    current: CriticalResidualEvaluation | None,
    composition: tuple[float, ...],
    scaling: ResidualScaling | None,
    history: list[CriticalPointIteration],
    conditions: list[float],
    accepted_steps: int,
    rejected_steps: int,
    function_evaluations: int,
    initialization_source: str,
    reason: str,
) -> MixtureCriticalPointResult:
    raw = None if current is None else current.raw_residuals
    return MixtureCriticalPointResult(
        status,
        None if current is None else current.temperature_k,
        None if current is None else current.pressure_pa,
        composition,
        None if raw is None else raw[0],
        None if raw is None else raw[1],
        None if raw is None or scaling is None else _norm(scaling.scaled(raw)),
        None if current is None else current.critical_direction,
        None if current is None else current.criticality_result,
        accepted_steps,
        accepted_steps,
        rejected_steps,
        function_evaluations,
        scaling,
        tuple(history),
        tuple(conditions),
        initialization_source,
        reason,
        None,
    )


def solve_critical_residual_system(
    evaluator: ResidualEvaluator,
    initial_temperature_k: float,
    initial_pressure_pa: float,
    *,
    settings: CriticalPointSolverSettings = DEFAULT_CRITICAL_POINT_SETTINGS,
    composition: tuple[float, ...] = (),
    initialization_source: str = "user_specified",
) -> MixtureCriticalPointResult:
    """Solve a signed two-residual criticality system with safeguarded Newton."""

    if not initialization_source:
        raise ValueError("initialization_source must not be blank")
    q = log_coordinates(initial_temperature_k, initial_pressure_pa)
    if not _within_bounds(initial_temperature_k, initial_pressure_pa, settings):
        return _result(
            CriticalPointStatus.INITIALIZATION_FAILED,
            None,
            composition,
            None,
            [],
            [],
            0,
            0,
            0,
            initialization_source,
            "initial temperature or pressure lies outside configured bounds",
        )
    function_evaluations = 0
    try:
        function_evaluations += 1
        current = evaluator(q, None)
        _validate_evaluation(current, None)
    except _CriticalityNotApplicableError as error:
        return _result(
            CriticalPointStatus.CRITICALITY_NOT_APPLICABLE,
            None,
            composition,
            None,
            [],
            [],
            0,
            0,
            function_evaluations,
            initialization_source,
            f"initial criticality evaluation was not applicable: {error}",
        )
    except (FloatingPointError, OverflowError, TypeError, ValueError) as error:
        return _result(
            CriticalPointStatus.INITIALIZATION_FAILED,
            None,
            composition,
            None,
            [],
            [],
            0,
            0,
            function_evaluations,
            initialization_source,
            f"initial criticality evaluation failed: {error}",
        )
    scaling = _scaling_from_initial(current.raw_residuals, settings)
    scaled = scaling.scaled(current.raw_residuals)
    current_norm = _norm(scaled)
    history = [
        CriticalPointIteration(
            0,
            current.temperature_k,
            current.pressure_pa,
            current.raw_residuals[0],
            current.raw_residuals[1],
            current_norm,
            0.5 * current_norm**2,
            None,
            0.0,
            0.0,
            0,
            None,
            None,
        )
    ]
    conditions: list[float] = []
    accepted_steps = 0
    rejected_steps = 0

    for iteration in range(1, settings.maximum_iterations + 1):
        if _converged(current, scaling, settings):
            break
        jacobian = calculate_critical_residual_jacobian(
            evaluator, current, scaling, settings
        )
        function_evaluations += jacobian.function_evaluations
        if not jacobian.applicable or jacobian.scaled_jacobian is None:
            return _result(
                CriticalPointStatus.JACOBIAN_FAILED,
                current,
                composition,
                scaling,
                history,
                conditions,
                accepted_steps,
                rejected_steps,
                function_evaluations,
                initialization_source,
                jacobian.failure_reason or "critical-residual Jacobian failed",
            )
        matrix = np.asarray(jacobian.scaled_jacobian, dtype=float)
        try:
            condition = float(np.linalg.cond(matrix))
        except np.linalg.LinAlgError as error:
            return _result(
                CriticalPointStatus.JACOBIAN_FAILED,
                current,
                composition,
                scaling,
                history,
                conditions,
                accepted_steps,
                rejected_steps,
                function_evaluations,
                initialization_source,
                f"Jacobian condition evaluation failed: {error}",
            )
        conditions.append(condition)
        if (
            not isfinite(condition)
            or condition > settings.maximum_jacobian_condition_number
        ):
            return _result(
                CriticalPointStatus.ILL_CONDITIONED,
                current,
                composition,
                scaling,
                history,
                conditions,
                accepted_steps,
                rejected_steps,
                function_evaluations,
                initialization_source,
                "critical-residual Jacobian exceeds the conditioning safeguard",
            )
        try:
            step = np.linalg.solve(matrix, -np.asarray(scaled, dtype=float))
        except np.linalg.LinAlgError as error:
            return _result(
                CriticalPointStatus.JACOBIAN_FAILED,
                current,
                composition,
                scaling,
                history,
                conditions,
                accepted_steps,
                rejected_steps,
                function_evaluations,
                initialization_source,
                f"Newton linear solve failed: {error}",
            )
        if not np.all(np.isfinite(step)):
            return _result(
                CriticalPointStatus.JACOBIAN_FAILED,
                current,
                composition,
                scaling,
                history,
                conditions,
                accepted_steps,
                rejected_steps,
                function_evaluations,
                initialization_source,
                "Newton step was non-finite",
            )
        step[0] = np.clip(
            step[0],
            -settings.maximum_log_temperature_step,
            settings.maximum_log_temperature_step,
        )
        step[1] = np.clip(
            step[1],
            -settings.maximum_log_pressure_step,
            settings.maximum_log_pressure_step,
        )
        step_norm = float(np.linalg.norm(step, ord=np.inf))
        factor = 1.0
        accepted: CriticalResidualEvaluation | None = None
        rejected_this_iteration = 0
        bounds_only = True
        last_reason = "no line-search trial was evaluated"
        for _ in range(settings.maximum_backtracking_iterations + 1):
            trial_q = (
                float(q[0] + factor * step[0]),
                float(q[1] + factor * step[1]),
            )
            try:
                trial_temperature, trial_pressure = physical_coordinates(trial_q)
            except ValueError as error:
                last_reason = str(error)
            else:
                if not _within_bounds(trial_temperature, trial_pressure, settings):
                    last_reason = "trial temperature or pressure was outside bounds"
                else:
                    bounds_only = False
                    try:
                        function_evaluations += 1
                        trial = evaluator(trial_q, current.critical_direction)
                        _validate_evaluation(trial, current.critical_direction)
                        _validate_root_continuity(current, trial)
                        trial_scaled = scaling.scaled(trial.raw_residuals)
                        trial_norm = _norm(trial_scaled)
                        if trial_norm < current_norm:
                            accepted = trial
                            break
                        last_reason = "scaled residual merit did not decrease"
                    except (
                        FloatingPointError,
                        OverflowError,
                        TypeError,
                        ValueError,
                    ) as error:
                        last_reason = str(error)
            rejected_steps += 1
            rejected_this_iteration += 1
            factor *= settings.line_search_reduction_factor
            if factor < settings.minimum_line_search_factor:
                break
        if accepted is None:
            status = (
                CriticalPointStatus.BOUNDS_REACHED
                if bounds_only
                else CriticalPointStatus.LINE_SEARCH_FAILED
            )
            return _result(
                status,
                current,
                composition,
                scaling,
                history,
                conditions,
                accepted_steps,
                rejected_steps,
                function_evaluations,
                initialization_source,
                f"line search found no applicable improving step: {last_reason}",
            )
        q = accepted.log_coordinates
        current = accepted
        scaled = scaling.scaled(current.raw_residuals)
        current_norm = _norm(scaled)
        accepted_steps += 1
        history.append(
            CriticalPointIteration(
                iteration,
                current.temperature_k,
                current.pressure_pa,
                current.raw_residuals[0],
                current.raw_residuals[1],
                current_norm,
                0.5 * current_norm**2,
                condition,
                step_norm,
                factor,
                rejected_this_iteration,
                jacobian.base_step,
                jacobian.estimated_errors,
            )
        )
    if not _converged(current, scaling, settings):
        return _result(
            CriticalPointStatus.MAXIMUM_ITERATIONS,
            current,
            composition,
            scaling,
            history,
            conditions,
            accepted_steps,
            rejected_steps,
            function_evaluations,
            initialization_source,
            "maximum iterations reached before both critical residuals converged",
        )

    try:
        function_evaluations += 1
        first = evaluator(q, None)
        function_evaluations += 1
        second = evaluator(q, None)
        _validate_evaluation(first, None)
        _validate_evaluation(second, None)
    except (FloatingPointError, OverflowError, TypeError, ValueError) as error:
        return _result(
            CriticalPointStatus.FINAL_VALIDATION_FAILED,
            current,
            composition,
            scaling,
            history,
            conditions,
            accepted_steps,
            rejected_steps,
            function_evaluations,
            initialization_source,
            f"fresh final evaluation failed: {error}",
        )
    deterministic = (
        first.raw_residuals == second.raw_residuals
        and first.critical_direction == second.critical_direction
    )
    if not deterministic or not _converged(first, scaling, settings):
        return _result(
            CriticalPointStatus.FINAL_VALIDATION_FAILED,
            first,
            composition,
            scaling,
            history,
            conditions,
            accepted_steps,
            rejected_steps,
            function_evaluations,
            initialization_source,
            "fresh final residual certification was not converged and deterministic",
        )
    return _result(
        CriticalPointStatus.CONVERGED,
        first,
        composition,
        scaling,
        history,
        conditions,
        accepted_steps,
        rejected_steps,
        function_evaluations,
        initialization_source,
        "both signed critical residuals converged and passed fresh certification",
    )


def _root_branch_identity(
    mixture: FluidMixture,
    temperature_k: float,
    pressure_pa: float,
    selected_compressibility_factor: float,
    binary_interactions: BinaryInteractionMapping | None,
    binary_interaction_policy: BinaryInteractionPolicy,
) -> RootBranchIdentity:
    """Identify the selected root within the full ordered physical PR root set."""

    parameters = calculate_peng_robinson_mixture_parameters(
        mixture,
        temperature_k,
        pressure_pa,
        binary_interactions,
        binary_interaction_policy,
    )
    roots = calculate_compressibility_roots(parameters.A_mix, parameters.B_mix)
    classifications = tuple(
        classify_mechanical_stability(
            root, parameters.A_mix, parameters.B_mix
        ).classification.value
        for root in roots
    )
    distances = tuple(abs(root - selected_compressibility_factor) for root in roots)
    selected_index = int(np.argmin(distances))
    tolerance = 1.0e-8 * max(
        1.0, abs(selected_compressibility_factor), abs(roots[selected_index])
    )
    if distances[selected_index] > tolerance:
        raise ValueError("Module 19 selected root was absent from the PR root set")
    if sum(distance <= tolerance for distance in distances) != 1:
        raise ValueError(
            "Module 19 selected root did not map uniquely to the PR root set"
        )
    return RootBranchIdentity(
        len(roots),
        classifications,
        selected_index,
        selected_compressibility_factor,
        tuple(float(root) for root in roots),
    )


def _mixture_evaluator(
    mixture: FluidMixture,
    binary_interactions: BinaryInteractionMapping | None,
    binary_interaction_policy: BinaryInteractionPolicy,
    reference_active_component_index: int | None,
    settings: CriticalPointSolverSettings,
) -> ResidualEvaluator:
    interaction_snapshot = (
        None if binary_interactions is None else dict(binary_interactions)
    )

    def evaluate(
        q: tuple[float, float], previous_direction: tuple[float, ...] | None
    ) -> CriticalResidualEvaluation:
        temperature_k, pressure_pa = physical_coordinates(q)
        if not _within_bounds(temperature_k, pressure_pa, settings):
            raise ValueError("candidate temperature or pressure lies outside bounds")
        result = calculate_stable_root_mixture_criticality(
            mixture,
            temperature_k,
            pressure_pa,
            interaction_snapshot,
            binary_interaction_policy,
            reference_active_component_index=reference_active_component_index,
            previous_critical_direction=previous_direction,
        )
        if result.status is not CriticalityStatus.APPLICABLE:
            raise _CriticalityNotApplicableError(
                f"Module 19 criticality is {result.status.value}: "
                f"{result.reason or 'no reason supplied'}"
            )
        residuals = criticality_residual_pair(result)
        direction = result.critical_composition_direction
        if direction is None:
            raise ValueError(
                "applicable Module 19 result omitted its critical direction"
            )
        selected_root = result.selected_compressibility_factor
        if selected_root is None:
            raise ValueError("applicable Module 19 result omitted its selected PR root")
        root_identity = _root_branch_identity(
            mixture,
            temperature_k,
            pressure_pa,
            selected_root,
            interaction_snapshot,
            binary_interaction_policy,
        )
        return CriticalResidualEvaluation(
            q,
            temperature_k,
            pressure_pa,
            residuals,
            direction,
            result,
            root_identity,
        )

    return evaluate


def solve_mixture_critical_point(
    mixture: FluidMixture,
    initial_temperature_k: float,
    initial_pressure_pa: float,
    binary_interactions: BinaryInteractionMapping | None = None,
    binary_interaction_policy: BinaryInteractionPolicy = (
        BinaryInteractionPolicy.DEFAULT_ZERO
    ),
    *,
    settings: CriticalPointSolverSettings = DEFAULT_CRITICAL_POINT_SETTINGS,
    reference_active_component_index: int | None = None,
    initialization_source: str = "user_specified",
) -> MixtureCriticalPointResult:
    """Solve ``(lambda_min, C)=(0,0)`` at the mixture's fixed composition."""

    composition = tuple(item.mole_fraction for item in mixture.components)
    if sum(value > 0.0 for value in composition) < 2:
        return _result(
            CriticalPointStatus.INSUFFICIENT_ACTIVE_COMPONENTS,
            None,
            composition,
            None,
            [],
            [],
            0,
            0,
            0,
            initialization_source,
            "mixture criticality requires at least two active components",
        )
    evaluator = _mixture_evaluator(
        mixture,
        binary_interactions,
        binary_interaction_policy,
        reference_active_component_index,
        settings,
    )
    return solve_critical_residual_system(
        evaluator,
        initial_temperature_k,
        initial_pressure_pa,
        settings=settings,
        composition=composition,
        initialization_source=initialization_source,
    )


def scan_mixture_criticality(
    mixture: FluidMixture,
    settings: CriticalPointScanSettings,
    binary_interactions: BinaryInteractionMapping | None = None,
    binary_interaction_policy: BinaryInteractionPolicy = (
        BinaryInteractionPolicy.DEFAULT_ZERO
    ),
    *,
    reference_active_component_index: int | None = None,
) -> CriticalPointScanResult:
    """Evaluate a bounded diagnostic grid without solving or changing composition."""

    temperatures = np.linspace(
        settings.minimum_temperature_k,
        settings.maximum_temperature_k,
        settings.temperature_points,
    )
    pressures = np.geomspace(
        settings.minimum_pressure_pa,
        settings.maximum_pressure_pa,
        settings.pressure_points,
    )
    entries: list[CriticalPointScanEntry] = []
    for temperature in temperatures:
        for pressure in pressures:
            result = calculate_stable_root_mixture_criticality(
                mixture,
                float(temperature),
                float(pressure),
                binary_interactions,
                binary_interaction_policy,
                reference_active_component_index=reference_active_component_index,
            )
            if (
                result.status is CriticalityStatus.APPLICABLE
                and result.lambda_min is not None
                and result.cubic_directional_derivative is not None
            ):
                norm = _norm(
                    (
                        result.lambda_min / settings.lambda_scale,
                        result.cubic_directional_derivative / settings.cubic_scale,
                    )
                )
                entries.append(
                    CriticalPointScanEntry(
                        float(temperature),
                        float(pressure),
                        result.status,
                        result.lambda_min,
                        result.cubic_directional_derivative,
                        norm,
                        None,
                    )
                )
            else:
                entries.append(
                    CriticalPointScanEntry(
                        float(temperature),
                        float(pressure),
                        result.status,
                        result.lambda_min,
                        result.cubic_directional_derivative,
                        None,
                        result.reason,
                    )
                )
    applicable = tuple(
        entry for entry in entries if entry.scaled_residual_norm is not None
    )
    best = (
        min(applicable, key=lambda entry: entry.scaled_residual_norm or 0.0)
        if applicable
        else None
    )
    return CriticalPointScanResult(
        settings,
        tuple(item.mole_fraction for item in mixture.components),
        tuple(entries),
        best,
    )
