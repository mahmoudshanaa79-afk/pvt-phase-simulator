"""Opt-in pseudo-arclength continuation for saturation branches.

The historical temperature-parameter continuation remains in
``phase_envelope``.  This module augments the audited local saturation Newton
system by adding ``ln(T)`` to its state and one weighted arclength equation.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from math import exp, isfinite, log
from typing import Final

import numpy as np

from pvt_phase_simulator.eos.derivatives import (
    calculate_fixed_root_mixture_fugacity_derivatives,
)
from pvt_phase_simulator.eos.flash import FlashPhaseResult
from pvt_phase_simulator.eos.mixing_rules import (
    BinaryInteractionMapping,
    BinaryInteractionPolicy,
    calculate_peng_robinson_mixture_parameters,
)
from pvt_phase_simulator.eos.phase_envelope import (
    EnvelopeBranchKind,
    EnvelopeContinuationSettings,
)
from pvt_phase_simulator.eos.saturation_pressure import (
    FUGACITY_EQUILIBRIUM_TOLERANCE,
    SaturationKind,
    SaturationPressureResult,
    SaturationStatus,
    _active_interactions,
    _active_newton_mixture,
    _evaluate_saturation_newton_system,
    _root_branch_is_continuous,
    calculate_saturation_pressure,
    multicomponent_saturation_is_near_trivial,
    saturation_phase_roles_are_consistent,
)
from pvt_phase_simulator.fluid_models import FluidMixture, MixtureComponent

Array = np.ndarray
SystemEvaluator = Callable[[Array], tuple[Array, Array]]
StateValidator = Callable[[Array], bool]

DEFAULT_NULL_SPACE_RELATIVE_TOLERANCE: Final = 1e-11
DEFAULT_TURNING_COMPONENT_TOLERANCE: Final = 1e-4


class PseudoArclengthTerminationReason(StrEnum):
    """Structured outcome of an opt-in pseudo-arclength trace."""

    MAXIMUM_POINTS = "maximum_points"
    INITIALIZATION_FAILED = "initialization_failed"
    TANGENT_FAILED = "tangent_failed"
    MINIMUM_ARCLENGTH_STEP_REACHED = "minimum_arclength_step_reached"
    PHASE_ROLE_LOST = "phase_role_lost"
    TRIVIAL_STATE = "trivial_state"
    NEAR_CRITICAL = "near_critical"


class PseudoArclengthCorrectorStatus(StrEnum):
    """Outcome of one augmented safeguarded Newton correction."""

    CONVERGED = "converged"
    MAXIMUM_ITERATIONS = "maximum_iterations"
    SINGULAR_JACOBIAN = "singular_jacobian"
    LINE_SEARCH_FAILED = "line_search_failed"
    INVALID_STATE = "invalid_state"
    EVALUATION_FAILED = "evaluation_failed"


@dataclass(frozen=True, slots=True)
class PseudoArclengthSettings:
    """Deterministic controls for dimensionless pseudo-arclength steps."""

    initial_temperature_step_k: float
    initial_arclength_step: float = 0.02
    minimum_arclength_step: float = 0.001
    maximum_arclength_step: float = 0.08
    maximum_points: int = 20
    maximum_step_retries: int = 6
    maximum_corrector_iterations: int = 15
    corrector_tolerance: float = FUGACITY_EQUILIBRIUM_TOLERANCE
    maximum_jacobian_condition_number: float = 1e12
    line_search_reduction_factor: float = 0.5
    minimum_line_search_factor: float = 1e-6
    easy_corrector_iteration_limit: int = 4
    step_increase_factor: float = 1.25
    step_decrease_factor: float = 0.5
    minimum_pressure_pa: float = 1_000.0
    maximum_pressure_pa: float = 100_000_000.0
    state_weights: tuple[float, ...] | None = None
    turning_component_tolerance: float = DEFAULT_TURNING_COMPONENT_TOLERANCE

    def __post_init__(self) -> None:
        positive = (
            self.initial_arclength_step,
            self.minimum_arclength_step,
            self.maximum_arclength_step,
            self.corrector_tolerance,
            self.maximum_jacobian_condition_number,
            self.line_search_reduction_factor,
            self.minimum_line_search_factor,
            self.step_increase_factor,
            self.step_decrease_factor,
            self.minimum_pressure_pa,
            self.maximum_pressure_pa,
            self.turning_component_tolerance,
        )
        if not all(isfinite(value) and value > 0.0 for value in positive):
            raise ValueError("pseudo-arclength scalar controls must be positive finite")
        if (
            not isfinite(self.initial_temperature_step_k)
            or self.initial_temperature_step_k == 0.0
        ):
            raise ValueError("initial_temperature_step_k must be finite and non-zero")
        if (
            not self.minimum_arclength_step
            <= self.initial_arclength_step
            <= self.maximum_arclength_step
        ):
            raise ValueError("initial arclength step must lie within step bounds")
        if self.minimum_pressure_pa >= self.maximum_pressure_pa:
            raise ValueError("minimum pressure must be below maximum pressure")
        if not 0.0 < self.line_search_reduction_factor < 1.0:
            raise ValueError("line-search reduction must lie between zero and one")
        if not 0.0 < self.minimum_line_search_factor < 1.0:
            raise ValueError("minimum line-search factor must lie between zero and one")
        if self.step_increase_factor <= 1.0:
            raise ValueError("step increase factor must exceed one")
        if not 0.0 < self.step_decrease_factor < 1.0:
            raise ValueError("step decrease factor must lie between zero and one")
        integer_controls = (
            self.maximum_points,
            self.maximum_step_retries,
            self.maximum_corrector_iterations,
            self.easy_corrector_iteration_limit,
        )
        if any(type(value) is not int or value < 1 for value in integer_controls):
            raise ValueError(
                "pseudo-arclength integer controls must be positive integers"
            )
        if self.state_weights is not None and (
            not self.state_weights
            or not all(isfinite(value) and value > 0.0 for value in self.state_weights)
        ):
            raise ValueError("state weights must be positive finite values")


@dataclass(frozen=True, slots=True)
class PseudoArclengthCorrectorIteration:
    iteration: int
    residual_norm: float
    jacobian_condition_number: float
    step_norm: float
    line_search_factor: float
    rejected_trials: int


@dataclass(frozen=True, slots=True)
class PseudoArclengthCorrectorResult:
    status: PseudoArclengthCorrectorStatus
    state: tuple[float, ...] | None
    residual_norm: float | None
    function_evaluations: int
    history: tuple[PseudoArclengthCorrectorIteration, ...]
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class SaturationContinuationEvaluation:
    """Physical residual/Jacobian and reconstructed phase state at one ``u``."""

    state: tuple[float, ...]
    residuals: tuple[float, ...]
    jacobian: tuple[tuple[float, ...], ...]
    temperature_k: float
    pressure_pa: float
    parent_composition: tuple[float, ...]
    incipient_composition: tuple[float, ...]
    parent_phase: FlashPhaseResult
    incipient_phase: FlashPhaseResult
    k_values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class PseudoArclengthPoint:
    state: tuple[float, ...]
    temperature_k: float
    pressure_pa: float
    incipient_composition: tuple[float, ...]
    parent_root: float
    incipient_root: float
    maximum_fugacity_residual: float
    tangent: tuple[float, ...] | None
    predictor_state: tuple[float, ...] | None
    accepted_step: float
    corrector_iterations: int
    function_evaluations: int
    temperature_turning_point: bool
    pressure_turning_point: bool


@dataclass(frozen=True, slots=True)
class PseudoArclengthBranchResult:
    branch_kind: EnvelopeBranchKind
    feed_mixture: FluidMixture
    settings: PseudoArclengthSettings
    points: tuple[PseudoArclengthPoint, ...]
    termination_reason: PseudoArclengthTerminationReason
    termination_message: str
    accepted_arclength_steps: int
    rejected_steps: int
    step_size_history: tuple[float, ...]
    corrector_iteration_history: tuple[int, ...]
    temperature_turning_point_count: int
    pressure_turning_point_count: int
    equilibrium_evaluations: int
    step_size_reductions: int
    step_size_increases: int
    initialization_source: str


@dataclass(frozen=True, slots=True)
class NumericalPseudoArclengthTrace:
    """Compact evidence from the reusable non-EOS continuation core."""

    states: tuple[tuple[float, ...], ...]
    tangents: tuple[tuple[float, ...], ...]
    termination_reason: PseudoArclengthTerminationReason
    accepted_steps: int
    rejected_steps: int
    step_size_history: tuple[float, ...]
    corrector_iteration_history: tuple[int, ...]
    step_size_reductions: int
    step_size_increases: int


def _weights_array(weights: tuple[float, ...] | Array, dimension: int) -> Array:
    values = np.asarray(weights, dtype=float)
    if (
        values.shape != (dimension,)
        or not np.all(np.isfinite(values))
        or np.any(values <= 0.0)
    ):
        raise ValueError(
            "weights must be a positive finite vector matching state dimension"
        )
    return values


def weighted_norm(
    vector: tuple[float, ...] | Array, weights: tuple[float, ...] | Array
) -> float:
    """Return ``sqrt(v.T W v)`` for diagonal positive ``W``."""

    values = np.asarray(vector, dtype=float)
    weight_values = _weights_array(weights, len(values))
    if not np.all(np.isfinite(values)):
        raise ValueError("weighted-norm vector must be finite")
    return float(np.sqrt(np.dot(weight_values * values, values)))


def calculate_pseudo_arclength_tangent(
    physical_jacobian: tuple[tuple[float, ...], ...] | Array,
    weights: tuple[float, ...] | Array,
    *,
    previous_tangent: tuple[float, ...] | Array | None = None,
    orientation_hint: tuple[float, ...] | Array | None = None,
    null_space_relative_tolerance: float = DEFAULT_NULL_SPACE_RELATIVE_TOLERANCE,
) -> tuple[float, ...]:
    """Extract, normalize, and deterministically orient the 1-D SVD null space."""

    jacobian = np.asarray(physical_jacobian, dtype=float)
    if jacobian.ndim != 2 or not np.all(np.isfinite(jacobian)):
        raise ValueError("physical Jacobian must be a finite matrix")
    rows, columns = jacobian.shape
    if columns != rows + 1:
        raise ValueError(
            "physical Jacobian must have exactly one more column than rows"
        )
    weight_values = _weights_array(weights, columns)
    if (
        not isfinite(null_space_relative_tolerance)
        or null_space_relative_tolerance <= 0.0
    ):
        raise ValueError("null-space tolerance must be positive and finite")
    _, singular_values, right = np.linalg.svd(jacobian, full_matrices=True)
    threshold = (
        null_space_relative_tolerance
        * max(jacobian.shape)
        * max(float(singular_values[0]) if singular_values.size else 0.0, 1.0)
    )
    rank = int(np.count_nonzero(singular_values > threshold))
    if columns - rank != 1:
        raise ValueError("physical Jacobian does not have a one-dimensional null space")
    tangent = right[-1].copy()
    norm = weighted_norm(tangent, weight_values)
    if not isfinite(norm) or norm <= 0.0:
        raise ValueError("null-space tangent cannot be normalized")
    tangent /= norm
    reference = previous_tangent if previous_tangent is not None else orientation_hint
    if reference is not None:
        reference_values = np.asarray(reference, dtype=float)
        if reference_values.shape != (columns,) or not np.all(
            np.isfinite(reference_values)
        ):
            raise ValueError(
                "orientation reference must match the finite state dimension"
            )
        dot = float(np.dot(weight_values * tangent, reference_values))
        if dot < 0.0:
            tangent = -tangent
        elif dot == 0.0:
            raise ValueError("orientation reference is orthogonal to the tangent")
    else:
        pivot = int(np.argmax(np.abs(tangent)))
        if tangent[pivot] < 0.0:
            tangent = -tangent
    return tuple(float(value) for value in tangent)


def predict_pseudo_arclength_state(
    current_state: tuple[float, ...] | Array,
    tangent: tuple[float, ...] | Array,
    step_size: float,
) -> tuple[float, ...]:
    """Return ``u_predictor = u_current + delta_s * tangent``."""

    state = np.asarray(current_state, dtype=float)
    direction = np.asarray(tangent, dtype=float)
    if state.shape != direction.shape or state.ndim != 1:
        raise ValueError("state and tangent must be equal-length vectors")
    if not np.all(np.isfinite(state)) or not np.all(np.isfinite(direction)):
        raise ValueError("state and tangent must be finite")
    if not isfinite(step_size) or step_size <= 0.0:
        raise ValueError("step_size must be positive and finite")
    return tuple(float(value) for value in state + step_size * direction)


def pseudo_arclength_constraint(
    state: tuple[float, ...] | Array,
    predictor: tuple[float, ...] | Array,
    tangent: tuple[float, ...] | Array,
    weights: tuple[float, ...] | Array,
) -> float:
    """Return ``t.T W (u-u_predictor)``."""

    state_values = np.asarray(state, dtype=float)
    predictor_values = np.asarray(predictor, dtype=float)
    tangent_values = np.asarray(tangent, dtype=float)
    if (
        state_values.shape != predictor_values.shape
        or state_values.shape != tangent_values.shape
    ):
        raise ValueError("state, predictor, and tangent dimensions must match")
    weight_values = _weights_array(weights, len(state_values))
    return float(
        np.dot(weight_values * tangent_values, state_values - predictor_values)
    )


def build_augmented_jacobian(
    physical_jacobian: tuple[tuple[float, ...], ...] | Array,
    tangent: tuple[float, ...] | Array,
    weights: tuple[float, ...] | Array,
) -> tuple[tuple[float, ...], ...]:
    """Append the exact arclength row ``t.T W`` to ``dF/du``."""

    jacobian = np.asarray(physical_jacobian, dtype=float)
    tangent_values = np.asarray(tangent, dtype=float)
    if jacobian.ndim != 2 or tangent_values.shape != (jacobian.shape[1],):
        raise ValueError("tangent must match physical Jacobian columns")
    weight_values = _weights_array(weights, jacobian.shape[1])
    augmented = np.vstack((jacobian, tangent_values * weight_values))
    if augmented.shape[0] != augmented.shape[1]:
        raise ValueError("augmented pseudo-arclength Jacobian must be square")
    return tuple(tuple(float(value) for value in row) for row in augmented)


def correct_pseudo_arclength_prediction(
    evaluator: SystemEvaluator,
    predictor: tuple[float, ...] | Array,
    tangent: tuple[float, ...] | Array,
    weights: tuple[float, ...] | Array,
    *,
    tolerance: float = 1e-10,
    maximum_iterations: int = 15,
    maximum_condition_number: float = 1e12,
    line_search_reduction_factor: float = 0.5,
    minimum_line_search_factor: float = 1e-6,
    validator: StateValidator | None = None,
) -> PseudoArclengthCorrectorResult:
    """Solve the augmented system with conditioned, backtracked Newton steps."""

    state = np.asarray(predictor, dtype=float).copy()
    direction = np.asarray(tangent, dtype=float)
    weight_values = _weights_array(weights, len(state))
    evaluations = 0
    history: list[PseudoArclengthCorrectorIteration] = []
    if validator is not None and not validator(state):
        return PseudoArclengthCorrectorResult(
            PseudoArclengthCorrectorStatus.INVALID_STATE,
            None,
            None,
            0,
            (),
            "predictor is outside the admissible state domain",
        )
    for iteration in range(maximum_iterations + 1):
        try:
            residual, jacobian = evaluator(state)
            evaluations += 1
        except (ArithmeticError, ValueError, np.linalg.LinAlgError) as error:
            return PseudoArclengthCorrectorResult(
                PseudoArclengthCorrectorStatus.EVALUATION_FAILED,
                None,
                None,
                evaluations,
                tuple(history),
                str(error),
            )
        residual_values = np.asarray(residual, dtype=float)
        jacobian_values = np.asarray(jacobian, dtype=float)
        constraint = pseudo_arclength_constraint(
            state, predictor, direction, weight_values
        )
        augmented_residual = np.append(residual_values, constraint)
        norm = float(np.linalg.norm(augmented_residual, ord=np.inf))
        if not isfinite(norm):
            return PseudoArclengthCorrectorResult(
                PseudoArclengthCorrectorStatus.EVALUATION_FAILED,
                None,
                None,
                evaluations,
                tuple(history),
                "augmented residual is non-finite",
            )
        if norm <= tolerance:
            return PseudoArclengthCorrectorResult(
                PseudoArclengthCorrectorStatus.CONVERGED,
                tuple(float(value) for value in state),
                norm,
                evaluations,
                tuple(history),
                None,
            )
        if iteration == maximum_iterations:
            break
        augmented = np.asarray(
            build_augmented_jacobian(jacobian_values, direction, weight_values)
        )
        condition = float(np.linalg.cond(augmented))
        if not isfinite(condition) or condition > maximum_condition_number:
            return PseudoArclengthCorrectorResult(
                PseudoArclengthCorrectorStatus.SINGULAR_JACOBIAN,
                None,
                norm,
                evaluations,
                tuple(history),
                "augmented Jacobian is singular or ill-conditioned",
            )
        try:
            newton_step = np.linalg.solve(augmented, -augmented_residual)
        except np.linalg.LinAlgError as error:
            return PseudoArclengthCorrectorResult(
                PseudoArclengthCorrectorStatus.SINGULAR_JACOBIAN,
                None,
                norm,
                evaluations,
                tuple(history),
                str(error),
            )
        factor = 1.0
        rejected = 0
        accepted = False
        trial_norm = norm
        while factor >= minimum_line_search_factor:
            trial = state + factor * newton_step
            if validator is not None and not validator(trial):
                factor *= line_search_reduction_factor
                rejected += 1
                continue
            try:
                trial_residual, _ = evaluator(trial)
                evaluations += 1
                trial_augmented = np.append(
                    np.asarray(trial_residual, dtype=float),
                    pseudo_arclength_constraint(
                        trial, predictor, direction, weight_values
                    ),
                )
                trial_norm = float(np.linalg.norm(trial_augmented, ord=np.inf))
            except (ArithmeticError, ValueError, np.linalg.LinAlgError):
                trial_norm = float("inf")
            if isfinite(trial_norm) and trial_norm < norm:
                state = trial
                accepted = True
                break
            factor *= line_search_reduction_factor
            rejected += 1
        history.append(
            PseudoArclengthCorrectorIteration(
                iteration + 1,
                trial_norm,
                condition,
                weighted_norm(newton_step, weight_values),
                factor if accepted else 0.0,
                rejected,
            )
        )
        if not accepted:
            return PseudoArclengthCorrectorResult(
                PseudoArclengthCorrectorStatus.LINE_SEARCH_FAILED,
                None,
                norm,
                evaluations,
                tuple(history),
                "backtracking could not reduce the augmented residual",
            )
    return PseudoArclengthCorrectorResult(
        PseudoArclengthCorrectorStatus.MAXIMUM_ITERATIONS,
        None,
        None,
        evaluations,
        tuple(history),
        "maximum corrector iterations reached",
    )


def trace_pseudo_arclength_curve(
    evaluator: SystemEvaluator,
    first_state: tuple[float, ...],
    second_state: tuple[float, ...],
    weights: tuple[float, ...],
    *,
    initial_step: float = 0.1,
    minimum_step: float = 0.001,
    maximum_step: float = 0.2,
    maximum_points: int = 20,
    maximum_step_retries: int = 6,
    tolerance: float = 1e-10,
    easy_iteration_limit: int = 3,
    step_increase_factor: float = 1.25,
    step_decrease_factor: float = 0.5,
    validator: StateValidator | None = None,
) -> NumericalPseudoArclengthTrace:
    """Trace a smooth one-dimensional manifold for isolated numerical tests."""

    first = np.asarray(first_state, dtype=float)
    second = np.asarray(second_state, dtype=float)
    if first.shape != second.shape or first.ndim != 1:
        raise ValueError("initial curve states must be equal-length vectors")
    if not 0.0 < minimum_step <= initial_step <= maximum_step:
        raise ValueError("generic trace step controls are inconsistent")
    if maximum_points < 2 or maximum_step_retries < 0:
        raise ValueError("generic trace count controls are inconsistent")
    _, second_jacobian = evaluator(second)
    tangent = calculate_pseudo_arclength_tangent(
        second_jacobian,
        weights,
        orientation_hint=second - first,
    )
    states = [
        tuple(float(value) for value in first),
        tuple(float(value) for value in second),
    ]
    tangents = [tangent]
    step = initial_step
    step_history: list[float] = []
    iteration_history: list[int] = []
    rejected = reductions = increases = 0
    termination = PseudoArclengthTerminationReason.MAXIMUM_POINTS
    while len(states) < maximum_points:
        accepted = False
        for _ in range(maximum_step_retries + 1):
            predictor = predict_pseudo_arclength_state(states[-1], tangent, step)
            corrected = correct_pseudo_arclength_prediction(
                evaluator,
                predictor,
                tangent,
                weights,
                tolerance=tolerance,
                validator=validator,
            )
            if (
                corrected.status is PseudoArclengthCorrectorStatus.CONVERGED
                and corrected.state is not None
            ):
                _, candidate_jacobian = evaluator(np.asarray(corrected.state))
                tangent = calculate_pseudo_arclength_tangent(
                    candidate_jacobian,
                    weights,
                    previous_tangent=tangent,
                )
                states.append(corrected.state)
                tangents.append(tangent)
                step_history.append(step)
                iteration_history.append(len(corrected.history))
                accepted = True
                if len(corrected.history) <= easy_iteration_limit:
                    grown = min(maximum_step, step * step_increase_factor)
                    if grown > step:
                        increases += 1
                    step = grown
                else:
                    reduced = max(minimum_step, step * step_decrease_factor)
                    if reduced < step:
                        reductions += 1
                    step = reduced
                break
            rejected += 1
            reduced = step * step_decrease_factor
            if reduced < minimum_step:
                termination = (
                    PseudoArclengthTerminationReason.MINIMUM_ARCLENGTH_STEP_REACHED
                )
                break
            step = reduced
            reductions += 1
        if not accepted:
            break
    return NumericalPseudoArclengthTrace(
        tuple(states),
        tuple(tangents),
        termination,
        max(0, len(states) - 2),
        rejected,
        tuple(step_history),
        tuple(iteration_history),
        reductions,
        increases,
    )


def _kind(branch_kind: EnvelopeBranchKind) -> SaturationKind:
    if branch_kind is EnvelopeBranchKind.BUBBLE:
        return SaturationKind.BUBBLE_POINT
    if branch_kind is EnvelopeBranchKind.DEW:
        return SaturationKind.DEW_POINT
    raise ValueError("branch_kind must be an EnvelopeBranchKind")


def _state_from_saturation(
    result: SaturationPressureResult, active_indices: tuple[int, ...]
) -> tuple[float, ...]:
    pressure = result.pressure_pa
    temperature = result.temperature_k
    composition = tuple(result.incipient_composition[index] for index in active_indices)
    if pressure is None:
        raise ValueError("initial saturation result has no pressure")
    return (*tuple(composition[:-1]), log(pressure), log(temperature))


def evaluate_saturation_continuation_system(
    mixture: FluidMixture,
    branch_kind: EnvelopeBranchKind,
    state: tuple[float, ...] | Array,
    minimum_pressure_pa: float = 1_000.0,
    maximum_pressure_pa: float = 100_000_000.0,
    binary_interactions: BinaryInteractionMapping | None = None,
    binary_interaction_policy: BinaryInteractionPolicy = (
        BinaryInteractionPolicy.DEFAULT_ZERO
    ),
) -> SaturationContinuationEvaluation:
    """Evaluate ``F`` and analytical ``dF/du`` for ``u=[w[:-1],lnP,lnT]``."""

    active_mixture, _ = _active_newton_mixture(mixture)
    values = np.asarray(state, dtype=float)
    component_count = len(active_mixture.components)
    if values.shape != (component_count + 1,) or not np.all(np.isfinite(values)):
        raise ValueError("continuation state has the wrong dimension or is non-finite")
    coordinates = tuple(float(value) for value in values[: component_count - 1])
    log_pressure = float(values[-2])
    log_temperature = float(values[-1])
    temperature_k = exp(log_temperature)
    fixed = _evaluate_saturation_newton_system(
        mixture,
        temperature_k,
        _kind(branch_kind),
        coordinates,
        log_pressure,
        minimum_pressure_pa,
        maximum_pressure_pa,
        binary_interactions,
        binary_interaction_policy,
    )
    active_interactions = _active_interactions(binary_interactions, active_mixture)
    incipient_mixture = FluidMixture(
        tuple(
            MixtureComponent(item.component, fraction)
            for item, fraction in zip(
                active_mixture.components,
                fixed.active_incipient_composition,
                strict=True,
            )
        )
    )
    parent_parameters = calculate_peng_robinson_mixture_parameters(
        active_mixture,
        temperature_k,
        fixed.pressure_pa,
        active_interactions,
        binary_interaction_policy,
    )
    incipient_parameters = calculate_peng_robinson_mixture_parameters(
        incipient_mixture,
        temperature_k,
        fixed.pressure_pa,
        active_interactions,
        binary_interaction_policy,
    )
    parent_derivatives = calculate_fixed_root_mixture_fugacity_derivatives(
        parent_parameters,
        fixed.parent_phase.selected_compressibility_factor,
        active_interactions,
    )
    incipient_derivatives = calculate_fixed_root_mixture_fugacity_derivatives(
        incipient_parameters,
        fixed.incipient_phase.selected_compressibility_factor,
        active_interactions,
    )
    parent_temperature = parent_derivatives.log_fugacity_temperature_derivatives_per_k
    incipient_temperature = (
        incipient_derivatives.log_fugacity_temperature_derivatives_per_k
    )
    if (
        not parent_derivatives.applicable
        or not incipient_derivatives.applicable
        or parent_temperature is None
        or incipient_temperature is None
    ):
        reason = (
            parent_derivatives.failure_reason or incipient_derivatives.failure_reason
        )
        raise ValueError(
            f"analytical temperature derivatives are unavailable: {reason}"
        )
    temperature_column = tuple(
        temperature_k * (parent - incipient)
        for parent, incipient in zip(
            parent_temperature, incipient_temperature, strict=True
        )
    )
    jacobian = tuple(
        (*row, temperature_derivative)
        for row, temperature_derivative in zip(
            fixed.jacobian, temperature_column, strict=True
        )
    )
    parent_composition = tuple(item.mole_fraction for item in active_mixture.components)
    if branch_kind is EnvelopeBranchKind.BUBBLE:
        k_values = tuple(
            incipient / parent
            for parent, incipient in zip(
                parent_composition, fixed.active_incipient_composition, strict=True
            )
        )
    else:
        k_values = tuple(
            parent / incipient
            for parent, incipient in zip(
                parent_composition, fixed.active_incipient_composition, strict=True
            )
        )
    return SaturationContinuationEvaluation(
        tuple(float(value) for value in values),
        fixed.residuals,
        jacobian,
        temperature_k,
        fixed.pressure_pa,
        parent_composition,
        fixed.active_incipient_composition,
        fixed.parent_phase,
        fixed.incipient_phase,
        k_values,
    )


def _valid_eos_state(
    state: Array, component_count: int, settings: PseudoArclengthSettings
) -> bool:
    if state.shape != (component_count + 1,) or not np.all(np.isfinite(state)):
        return False
    coordinates = state[: component_count - 1]
    reference = 1.0 - float(np.sum(coordinates))
    if np.any(coordinates <= 0.0) or reference <= 0.0:
        return False
    try:
        pressure = exp(float(state[-2]))
        temperature = exp(float(state[-1]))
    except OverflowError:
        return False
    return (
        isfinite(pressure)
        and isfinite(temperature)
        and settings.minimum_pressure_pa <= pressure <= settings.maximum_pressure_pa
        and temperature > 0.0
    )


def _point_from_evaluation(
    evaluation: SaturationContinuationEvaluation,
    tangent: tuple[float, ...] | None,
    predictor: tuple[float, ...] | None,
    step: float,
    corrector: PseudoArclengthCorrectorResult | None,
    temperature_turning: bool = False,
    pressure_turning: bool = False,
) -> PseudoArclengthPoint:
    return PseudoArclengthPoint(
        evaluation.state,
        evaluation.temperature_k,
        evaluation.pressure_pa,
        evaluation.incipient_composition,
        evaluation.parent_phase.selected_compressibility_factor,
        evaluation.incipient_phase.selected_compressibility_factor,
        max(abs(value) for value in evaluation.residuals),
        tangent,
        predictor,
        step,
        0 if corrector is None else len(corrector.history),
        1 if corrector is None else corrector.function_evaluations,
        temperature_turning,
        pressure_turning,
    )


def _physical_stop_reason(
    evaluation: SaturationContinuationEvaluation,
    branch_kind: EnvelopeBranchKind,
    safeguards: EnvelopeContinuationSettings,
) -> PseudoArclengthTerminationReason | None:
    role = saturation_phase_roles_are_consistent(
        _kind(branch_kind),
        evaluation.parent_phase.selected_compressibility_factor,
        evaluation.incipient_phase.selected_compressibility_factor,
    )
    if role is None or not role:
        return PseudoArclengthTerminationReason.PHASE_ROLE_LOST
    if multicomponent_saturation_is_near_trivial(
        evaluation.parent_composition,
        evaluation.incipient_composition,
        _kind(branch_kind),
        evaluation.parent_phase,
        evaluation.incipient_phase,
    ):
        return PseudoArclengthTerminationReason.TRIVIAL_STATE
    root_separation = abs(
        evaluation.parent_phase.selected_compressibility_factor
        - evaluation.incipient_phase.selected_compressibility_factor
    )
    composition_separation = max(
        abs(parent - incipient)
        for parent, incipient in zip(
            evaluation.parent_composition, evaluation.incipient_composition, strict=True
        )
    )
    maximum_log_k = max(abs(log(value)) for value in evaluation.k_values)
    multiple_active_components = len(evaluation.parent_composition) > 1
    severe = int(root_separation <= safeguards.near_critical_root_stop)
    if multiple_active_components:
        severe += int(
            composition_separation <= safeguards.near_critical_composition_stop
        )
        severe += int(maximum_log_k <= safeguards.near_critical_log_k_stop)
    required_indicators = 2 if multiple_active_components else 1
    if severe >= required_indicators:
        return PseudoArclengthTerminationReason.NEAR_CRITICAL
    return None


def trace_pseudo_arclength_branch(
    mixture: FluidMixture,
    branch_kind: EnvelopeBranchKind,
    settings: PseudoArclengthSettings,
    start_temperature_k: float,
    binary_interactions: BinaryInteractionMapping | None = None,
    binary_interaction_policy: BinaryInteractionPolicy = (
        BinaryInteractionPolicy.DEFAULT_ZERO
    ),
    *,
    physical_safeguards: EnvelopeContinuationSettings | None = None,
) -> PseudoArclengthBranchResult:
    """Trace a saturation branch with explicit opt-in pseudo-arclength steps."""

    if not isfinite(start_temperature_k) or start_temperature_k <= 0.0:
        raise ValueError("start temperature must be positive and finite")
    second_temperature_k = start_temperature_k + settings.initial_temperature_step_k
    if second_temperature_k <= 0.0:
        raise ValueError("second initialization temperature must be positive")
    safeguards = physical_safeguards or EnvelopeContinuationSettings(
        target_temperature_k=second_temperature_k,
        initial_temperature_step_k=settings.initial_temperature_step_k,
        minimum_temperature_step_k=min(0.25, abs(settings.initial_temperature_step_k)),
        maximum_temperature_step_k=max(10.0, abs(settings.initial_temperature_step_k)),
        minimum_pressure_pa=settings.minimum_pressure_pa,
        maximum_pressure_pa=settings.maximum_pressure_pa,
    )
    kind = _kind(branch_kind)
    initial_results = tuple(
        calculate_saturation_pressure(
            mixture,
            temperature,
            kind,
            settings.minimum_pressure_pa,
            settings.maximum_pressure_pa,
            binary_interactions,
            binary_interaction_policy,
            saturation_newton_enabled=True,
        )
        for temperature in (
            start_temperature_k,
            second_temperature_k,
        )
    )
    if any(
        result.status is not SaturationStatus.CONVERGED or result.pressure_pa is None
        for result in initial_results
    ):
        return PseudoArclengthBranchResult(
            branch_kind,
            mixture,
            settings,
            (),
            PseudoArclengthTerminationReason.INITIALIZATION_FAILED,
            "two trusted fixed-temperature saturation states could not be initialized",
            0,
            0,
            (),
            (),
            0,
            0,
            0,
            0,
            0,
            "two production fixed-temperature saturation solves",
        )
    _, active_indices = _active_newton_mixture(mixture)
    states = tuple(
        _state_from_saturation(result, active_indices) for result in initial_results
    )
    dimension = len(states[0])
    weights = settings.state_weights or (1.0,) * dimension
    if len(weights) != dimension:
        raise ValueError(
            "state_weights must match [composition coordinates, ln(P), ln(T)]"
        )
    evaluations = tuple(
        evaluate_saturation_continuation_system(
            mixture,
            branch_kind,
            state,
            settings.minimum_pressure_pa,
            settings.maximum_pressure_pa,
            binary_interactions,
            binary_interaction_policy,
        )
        for state in states
    )
    secant = np.asarray(states[1]) - np.asarray(states[0])
    try:
        tangent = calculate_pseudo_arclength_tangent(
            evaluations[1].jacobian, weights, orientation_hint=secant
        )
    except ValueError as error:
        return PseudoArclengthBranchResult(
            branch_kind,
            mixture,
            settings,
            (),
            PseudoArclengthTerminationReason.TANGENT_FAILED,
            str(error),
            0,
            0,
            (),
            (),
            0,
            0,
            2,
            0,
            0,
            "two production fixed-temperature saturation solves",
        )
    points = [
        _point_from_evaluation(evaluations[0], None, None, 0.0, None),
        _point_from_evaluation(
            evaluations[1], tangent, None, weighted_norm(secant, weights), None
        ),
    ]
    initial_stop = _physical_stop_reason(evaluations[1], branch_kind, safeguards)
    if initial_stop is not None:
        return PseudoArclengthBranchResult(
            branch_kind,
            mixture,
            settings,
            tuple(points),
            initial_stop,
            "initial states already meet an authoritative physical stop condition",
            0,
            0,
            (),
            (),
            0,
            0,
            2,
            0,
            0,
            "two production fixed-temperature saturation solves",
        )
    step = settings.initial_arclength_step
    step_history: list[float] = []
    iteration_history: list[int] = []
    rejected = reductions = increases = 0
    equilibrium_evaluations = 2
    termination = PseudoArclengthTerminationReason.MAXIMUM_POINTS
    message = "maximum accepted point count reached"
    while len(points) < settings.maximum_points:
        accepted = False
        for _ in range(settings.maximum_step_retries + 1):
            predictor = predict_pseudo_arclength_state(points[-1].state, tangent, step)

            def system(state: Array) -> tuple[Array, Array]:
                evaluated = evaluate_saturation_continuation_system(
                    mixture,
                    branch_kind,
                    state,
                    settings.minimum_pressure_pa,
                    settings.maximum_pressure_pa,
                    binary_interactions,
                    binary_interaction_policy,
                )
                return np.asarray(evaluated.residuals), np.asarray(evaluated.jacobian)

            corrector = correct_pseudo_arclength_prediction(
                system,
                predictor,
                tangent,
                weights,
                tolerance=settings.corrector_tolerance,
                maximum_iterations=settings.maximum_corrector_iterations,
                maximum_condition_number=settings.maximum_jacobian_condition_number,
                line_search_reduction_factor=settings.line_search_reduction_factor,
                minimum_line_search_factor=settings.minimum_line_search_factor,
                validator=lambda state: _valid_eos_state(
                    state, len(evaluations[0].parent_composition), settings
                ),
            )
            equilibrium_evaluations += corrector.function_evaluations
            if (
                corrector.status is not PseudoArclengthCorrectorStatus.CONVERGED
                or corrector.state is None
            ):
                rejected += 1
                next_step = step * settings.step_decrease_factor
                if next_step < settings.minimum_arclength_step:
                    termination = (
                        PseudoArclengthTerminationReason.MINIMUM_ARCLENGTH_STEP_REACHED
                    )
                    message = (
                        corrector.failure_reason or "minimum arclength step failed"
                    )
                    break
                step = next_step
                reductions += 1
                continue
            candidate = evaluate_saturation_continuation_system(
                mixture,
                branch_kind,
                corrector.state,
                settings.minimum_pressure_pa,
                settings.maximum_pressure_pa,
                binary_interactions,
                binary_interaction_policy,
            )
            equilibrium_evaluations += 1
            stop = _physical_stop_reason(candidate, branch_kind, safeguards)
            previous_evaluation = evaluate_saturation_continuation_system(
                mixture,
                branch_kind,
                points[-1].state,
                settings.minimum_pressure_pa,
                settings.maximum_pressure_pa,
                binary_interactions,
                binary_interaction_policy,
            )
            equilibrium_evaluations += 1
            if stop is None and (
                not _root_branch_is_continuous(
                    previous_evaluation.parent_phase, candidate.parent_phase
                )
                or not _root_branch_is_continuous(
                    previous_evaluation.incipient_phase, candidate.incipient_phase
                )
            ):
                stop = PseudoArclengthTerminationReason.PHASE_ROLE_LOST
            if stop is not None:
                termination = stop
                message = (
                    "physical phase distinguishability or fixed-root continuity "
                    "was lost"
                )
                break
            try:
                next_tangent = calculate_pseudo_arclength_tangent(
                    candidate.jacobian, weights, previous_tangent=tangent
                )
            except ValueError as error:
                termination = PseudoArclengthTerminationReason.TANGENT_FAILED
                message = str(error)
                break
            temperature_turning = tangent[-1] * next_tangent[-1] < 0.0 or (
                abs(next_tangent[-1]) <= settings.turning_component_tolerance
                and abs(tangent[-1]) > settings.turning_component_tolerance
            )
            pressure_turning = tangent[-2] * next_tangent[-2] < 0.0 or (
                abs(next_tangent[-2]) <= settings.turning_component_tolerance
                and abs(tangent[-2]) > settings.turning_component_tolerance
            )
            points.append(
                _point_from_evaluation(
                    candidate,
                    next_tangent,
                    predictor,
                    step,
                    corrector,
                    temperature_turning,
                    pressure_turning,
                )
            )
            step_history.append(step)
            iteration_history.append(len(corrector.history))
            tangent = next_tangent
            accepted = True
            if len(corrector.history) <= settings.easy_corrector_iteration_limit:
                grown = min(
                    settings.maximum_arclength_step,
                    step * settings.step_increase_factor,
                )
                if grown > step:
                    increases += 1
                step = grown
            else:
                reduced = max(
                    settings.minimum_arclength_step,
                    step * settings.step_decrease_factor,
                )
                if reduced < step:
                    reductions += 1
                step = reduced
            break
        if not accepted:
            break
    return PseudoArclengthBranchResult(
        branch_kind,
        mixture,
        settings,
        tuple(points),
        termination,
        message,
        max(0, len(points) - 2),
        rejected,
        tuple(step_history),
        tuple(iteration_history),
        sum(point.temperature_turning_point for point in points),
        sum(point.pressure_turning_point for point in points),
        equilibrium_evaluations,
        reductions,
        increases,
        "two production fixed-temperature saturation solves followed by an SVD tangent",
    )
