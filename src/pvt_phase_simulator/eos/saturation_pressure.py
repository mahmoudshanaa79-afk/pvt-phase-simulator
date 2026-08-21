"""Fixed-temperature Peng–Robinson bubble- and dew-pressure calculations."""

from dataclasses import dataclass, replace
from enum import StrEnum
from math import exp, expm1, fsum, isclose, isfinite, log
from sys import float_info
from typing import Final

import numpy as np
from scipy.optimize import brentq  # type: ignore[import-untyped]

from pvt_phase_simulator._validation import require_finite as _require_finite
from pvt_phase_simulator._validation import require_positive as _require_positive
from pvt_phase_simulator.eos.derivatives import (
    calculate_fixed_root_mixture_fugacity_derivatives,
)
from pvt_phase_simulator.eos.diagnostics import (
    DiagnosticCategory,
    DiagnosticSeverity,
    EOSDiagnostic,
)
from pvt_phase_simulator.eos.flash import (
    FlashIteratePattern,
    FlashPhaseResult,
    PhaseInteractionProvenance,
    SafeguardedLogKAccelerationResult,
    calculate_damped_log_k_values,
    calculate_safeguarded_log_k_acceleration,
    detect_flash_iterate_pattern,
    evaluate_flash_phase,
    k_values_from_log_values,
)
from pvt_phase_simulator.eos.mixing_rules import (
    BinaryInteractionMapping,
    BinaryInteractionPolicy,
    CanonicalBinaryInteractionPairs,
    CanonicalBinaryInteractions,
    PengRobinsonMixtureParameters,
    calculate_peng_robinson_mixture_parameters,
)
from pvt_phase_simulator.eos.peng_robinson import (
    MechanicalStabilityClassification,
)
from pvt_phase_simulator.eos.phase_stability import (
    WILSON_COEFFICIENT,
    PhaseTrialKind,
    calculate_wilson_k_values,
    detect_phase_root_switch,
)
from pvt_phase_simulator.fluid_models import (
    MOLE_FRACTION_TOLERANCE,
    FluidMixture,
    MixtureComponent,
)

SATURATION_OBJECTIVE_TOLERANCE: Final = 1e-8
INNER_LOG_K_TOLERANCE: Final = 1e-10
INNER_COMPOSITION_TOLERANCE: Final = 1e-10
INCIPIENT_SUM_TOLERANCE: Final = 1e-10
FUGACITY_EQUILIBRIUM_TOLERANCE: Final = 1e-8
PURE_PHASE_ROOT_SEPARATION_TOLERANCE: Final = 1e-8
# A multicomponent state with every active K at unity is the trivial solution:
# the incipient phase is thermodynamically the parent phase, and the objective
# sum(z_i K_i^{+-1}) - 1 is then identically zero at any single-phase pressure.
# Matches the Module 6 trivial-composition scale. A pure component is excluded
# because K = 1 is its genuine saturation condition, not a degeneracy.
TRIVIAL_LOG_K_TOLERANCE: Final = 1e-8
# Named so continuation callers can recognise a trivial inner collapse. The
# enclosing search reports its own bracket failure, so this diagnostic is the
# only place the trivial evidence survives.
TRIVIAL_STATE_DIAGNOSTIC_CODE: Final = "SATURATION_TRIVIAL_STATE"
DEFAULT_MAXIMUM_INNER_ITERATIONS: Final = 100
DEFAULT_PRESSURE_SEARCH_POINTS: Final = 81
DEFAULT_MAXIMUM_OUTER_ITERATIONS: Final = 100
DEFAULT_MAXIMUM_NEWTON_ITERATIONS: Final = 15
DEFAULT_MAXIMUM_NEWTON_JACOBIAN_CONDITION_NUMBER: Final = 1e12
DEFAULT_NEWTON_LINE_SEARCH_REDUCTION_FACTOR: Final = 0.5
DEFAULT_MINIMUM_NEWTON_LINE_SEARCH_FACTOR: Final = 1e-6
DEFAULT_MAXIMUM_NEWTON_BACKTRACKING_ITERATIONS: Final = 20
_LOG_FLOAT_MAX: Final = log(float_info.max)
_LOG_FLOAT_MIN: Final = log(float_info.min)


class SaturationKind(StrEnum):
    """Fixed-temperature saturation boundary to calculate."""

    BUBBLE_POINT = "bubble_point"
    DEW_POINT = "dew_point"


class SaturationStatus(StrEnum):
    """Outcome of a saturation-pressure calculation."""

    CONVERGED = "converged"
    NOT_FOUND = "not_found"
    INCONCLUSIVE = "inconclusive"
    FAILED = "failed"


class InnerSaturationStatus(StrEnum):
    """Outcome of one fixed-pressure incipient-composition solve."""

    CONVERGED = "converged"
    NOT_CONVERGED = "not_converged"
    FAILED = "failed"


class SaturationNewtonStatus(StrEnum):
    """Disposition of the optional local Newton saturation attempt."""

    CONVERGED = "converged"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class WilsonPressureEstimates:
    """Finite positive Wilson pressure estimates in Pa."""

    component_pressure_factors_pa: tuple[float, ...]
    bubble_pressure_pa: float
    dew_pressure_pa: float


@dataclass(frozen=True, slots=True)
class SaturationNewtonIteration:
    """Immutable evidence for one accepted local Newton iteration."""

    iteration: int
    pressure_pa: float
    incipient_composition: tuple[float, ...]
    residual_norm: float
    jacobian_condition_number: float
    step_norm: float
    line_search_factor: float
    rejected_trial_count: int


@dataclass(frozen=True, slots=True)
class SaturationNewtonAttempt:
    """Compact evidence from the optional safeguarded Newton layer."""

    status: SaturationNewtonStatus
    converged: bool
    iteration_count: int
    function_evaluations: int
    initial_residual_norm: float | None
    final_residual_norm: float | None
    full_steps: int
    backtracked_steps: int
    rejected_steps: int
    failure_reason: str | None
    history: tuple[SaturationNewtonIteration, ...]


@dataclass(frozen=True, slots=True)
class SaturationPressureIteration:
    """Immutable record of one inner incipient-composition iteration."""

    iteration: int
    pressure_pa: float
    log_k_values: tuple[float, ...]
    k_values: tuple[float, ...]
    incipient_composition: tuple[float, ...]
    parent_phase: FlashPhaseResult
    incipient_phase: FlashPhaseResult
    acceleration: SafeguardedLogKAccelerationResult | None
    updated_log_k_values: tuple[float, ...]
    maximum_log_k_residual: float
    composition_change: float
    saturation_objective: float
    incipient_sum_residual: float
    fugacity_equilibrium_residuals: tuple[float | None, ...]
    maximum_fugacity_equilibrium_residual: float
    diagnostics: tuple[EOSDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class SaturationPressureEvaluation:
    """Immutable fully solved or failed inner problem at one pressure."""

    saturation_kind: SaturationKind
    pressure_pa: float
    status: InnerSaturationStatus
    converged: bool
    objective: float | None
    parent_composition: tuple[float, ...]
    incipient_composition: tuple[float, ...]
    k_values: tuple[float, ...]
    parent_phase: FlashPhaseResult | None
    incipient_phase: FlashPhaseResult | None
    fugacity_equilibrium_residuals: tuple[float | None, ...]
    maximum_log_k_residual: float | None
    composition_change: float | None
    incipient_sum_residual: float | None
    history: tuple[SaturationPressureIteration, ...]
    failure_reason: str | None
    diagnostics: tuple[EOSDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class SaturationPressureResult:
    """Immutable bubble- or dew-pressure result and complete search history."""

    saturation_kind: SaturationKind
    status: SaturationStatus
    feed_mixture: FluidMixture
    feed_composition: tuple[float, ...]
    temperature_k: float
    pressure_pa: float | None
    initial_pressure_estimate_pa: float
    pressure_bounds_pa: tuple[float, float]
    bracket_pressures_pa: tuple[float, float] | None
    bracket_objective_values: tuple[float, float] | None
    parent_composition: tuple[float, ...]
    incipient_composition: tuple[float, ...]
    k_values: tuple[float, ...]
    parent_phase: FlashPhaseResult | None
    incipient_phase: FlashPhaseResult | None
    fugacity_equilibrium_residuals: tuple[float | None, ...]
    maximum_fugacity_equilibrium_residual: float | None
    composition_sum_residual: float | None
    pressure_residual: float | None
    pressure_solver_iterations: int
    pressure_solver_function_calls: int
    evaluation_history: tuple[SaturationPressureEvaluation, ...]
    convergence_status: SaturationStatus
    failure_reason: str | None
    diagnostics: tuple[EOSDiagnostic, ...]
    binary_interaction_policy: BinaryInteractionPolicy
    binary_interactions: CanonicalBinaryInteractions
    supplied_binary_interaction_pairs: CanonicalBinaryInteractionPairs
    defaulted_binary_interaction_pairs: CanonicalBinaryInteractionPairs
    newton_attempt: SaturationNewtonAttempt | None = None


@dataclass(frozen=True, slots=True)
class _SaturationNewtonSystemEvaluation:
    """One complete residual/Jacobian evaluation on fixed selected roots."""

    pressure_pa: float
    active_incipient_composition: tuple[float, ...]
    residuals: tuple[float, ...]
    jacobian: tuple[tuple[float, ...], ...]
    parent_phase: FlashPhaseResult
    incipient_phase: FlashPhaseResult


def _feed_composition(mixture: FluidMixture) -> tuple[float, ...]:
    return tuple(item.mole_fraction for item in mixture.components)


def _require_kind(saturation_kind: SaturationKind) -> None:
    if not isinstance(saturation_kind, SaturationKind):
        raise ValueError("saturation_kind must be a SaturationKind.")


def _append_unique_diagnostics(
    destination: list[EOSDiagnostic],
    additions: tuple[EOSDiagnostic, ...],
) -> None:
    for item in additions:
        if item not in destination:
            destination.append(item)


def _failure_diagnostic(code: str, message: str) -> EOSDiagnostic:
    return EOSDiagnostic(
        code=code,
        severity=DiagnosticSeverity.WARNING,
        category=DiagnosticCategory.NUMERICAL_CONDITIONING,
        message=message,
    )


def calculate_wilson_pressure_estimates(
    mixture: FluidMixture,
    temperature_k: float,
) -> WilsonPressureEstimates:
    """Return Wilson bubble/dew estimates used only to center the search."""

    _require_positive(temperature_k, "temperature_k")
    feed = _feed_composition(mixture)
    factors: list[float] = []
    for item in mixture.components:
        component = item.component
        log_factor = log(component.critical_pressure_pa) + WILSON_COEFFICIENT * (
            1.0 + component.acentric_factor
        ) * (1.0 - component.critical_temperature_k / temperature_k)
        _require_finite(log_factor, f"Wilson pressure factor for {component.name}")
        if log_factor > _LOG_FLOAT_MAX or log_factor < _LOG_FLOAT_MIN:
            raise ValueError("Wilson pressure factor would overflow or underflow.")
        factor = exp(log_factor)
        _require_positive(factor, f"Wilson pressure factor for {component.name}")
        factors.append(factor)
    bubble_pressure = fsum(
        fraction * factor for fraction, factor in zip(feed, factors, strict=True)
    )
    inverse_dew_pressure = fsum(
        fraction / factor
        for fraction, factor in zip(feed, factors, strict=True)
        if fraction > 0.0
    )
    _require_positive(bubble_pressure, "Wilson bubble pressure")
    _require_positive(inverse_dew_pressure, "inverse Wilson dew pressure")
    dew_pressure = 1.0 / inverse_dew_pressure
    _require_positive(dew_pressure, "Wilson dew pressure")
    return WilsonPressureEstimates(
        component_pressure_factors_pa=tuple(factors),
        bubble_pressure_pa=bubble_pressure,
        dew_pressure_pa=dew_pressure,
    )


def _normalize_incipient_composition(
    feed: tuple[float, ...],
    log_k_values: tuple[float, ...],
    saturation_kind: SaturationKind,
) -> tuple[float, ...]:
    direction = 1.0 if saturation_kind is SaturationKind.BUBBLE_POINT else -1.0
    log_weights = tuple(
        None if fraction == 0.0 else log(fraction) + direction * log_k
        for fraction, log_k in zip(feed, log_k_values, strict=True)
    )
    active = tuple(value for value in log_weights if value is not None)
    if not active:
        raise ValueError("at least one incipient component must be active.")
    largest = max(active)
    weights = tuple(
        0.0 if value is None else exp(value - largest) for value in log_weights
    )
    total = fsum(weights)
    _require_positive(total, "incipient composition normalization")
    composition = tuple(value / total for value in weights)
    if not isclose(
        fsum(composition),
        1.0,
        rel_tol=0.0,
        abs_tol=MOLE_FRACTION_TOLERANCE,
    ):
        raise ValueError("incipient composition must sum to one.")
    return composition


def _saturation_objective_from_log_k(
    feed: tuple[float, ...],
    log_k_values: tuple[float, ...],
    saturation_kind: SaturationKind,
) -> float:
    direction = 1.0 if saturation_kind is SaturationKind.BUBBLE_POINT else -1.0
    log_terms = tuple(
        log(fraction) + direction * log_k
        for fraction, log_k in zip(feed, log_k_values, strict=True)
        if fraction > 0.0
    )
    largest = max(log_terms)
    log_sum = largest + log(fsum(exp(value - largest) for value in log_terms))
    _require_finite(log_sum, "saturation objective log sum")
    if log_sum > _LOG_FLOAT_MAX:
        raise ValueError("saturation objective would overflow.")
    objective = expm1(log_sum)
    _require_finite(objective, "saturation objective")
    return objective


def calculate_bubble_pressure_objective(
    composition: tuple[float, ...],
    k_values: tuple[float, ...],
) -> float:
    """Return ``sum(z_i K_i) - 1`` for finite positive K-values."""

    if not isinstance(composition, tuple) or not composition:
        raise ValueError("composition must be a non-empty immutable tuple.")
    if not isinstance(k_values, tuple) or len(k_values) != len(composition):
        raise ValueError("k_values must be an aligned immutable tuple.")
    for index, (fraction, k_value) in enumerate(
        zip(composition, k_values, strict=True)
    ):
        _require_finite(fraction, f"composition[{index}]")
        if fraction < 0.0:
            raise ValueError("composition values must be non-negative.")
        _require_positive(k_value, f"k_values[{index}]")
    if not isclose(
        fsum(composition), 1.0, rel_tol=0.0, abs_tol=MOLE_FRACTION_TOLERANCE
    ):
        raise ValueError("composition must sum to one within tolerance.")
    objective = (
        fsum(
            fraction * k_value
            for fraction, k_value in zip(composition, k_values, strict=True)
        )
        - 1.0
    )
    _require_finite(objective, "bubble-pressure objective")
    return objective


def calculate_dew_pressure_objective(
    composition: tuple[float, ...],
    k_values: tuple[float, ...],
) -> float:
    """Return ``sum(z_i / K_i) - 1`` for finite positive K-values."""

    if not isinstance(composition, tuple) or not composition:
        raise ValueError("composition must be a non-empty immutable tuple.")
    if not isinstance(k_values, tuple) or len(k_values) != len(composition):
        raise ValueError("k_values must be an aligned immutable tuple.")
    for index, (fraction, k_value) in enumerate(
        zip(composition, k_values, strict=True)
    ):
        _require_finite(fraction, f"composition[{index}]")
        if fraction < 0.0:
            raise ValueError("composition values must be non-negative.")
        _require_positive(k_value, f"k_values[{index}]")
    if not isclose(
        fsum(composition), 1.0, rel_tol=0.0, abs_tol=MOLE_FRACTION_TOLERANCE
    ):
        raise ValueError("composition must sum to one within tolerance.")
    objective = (
        fsum(
            fraction / k_value
            for fraction, k_value in zip(composition, k_values, strict=True)
        )
        - 1.0
    )
    _require_finite(objective, "dew-pressure objective")
    return objective


def _phase_kinds(
    saturation_kind: SaturationKind,
) -> tuple[PhaseTrialKind, PhaseTrialKind]:
    if saturation_kind is SaturationKind.BUBBLE_POINT:
        return PhaseTrialKind.LIQUID_LIKE, PhaseTrialKind.VAPOR_LIKE
    return PhaseTrialKind.VAPOR_LIKE, PhaseTrialKind.LIQUID_LIKE


def _phase_log_phi(
    saturation_kind: SaturationKind,
    parent_phase: FlashPhaseResult,
    incipient_phase: FlashPhaseResult,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    if saturation_kind is SaturationKind.BUBBLE_POINT:
        return (
            parent_phase.component_log_fugacity_coefficients,
            incipient_phase.component_log_fugacity_coefficients,
        )
    return (
        incipient_phase.component_log_fugacity_coefficients,
        parent_phase.component_log_fugacity_coefficients,
    )


def _fugacity_residuals(
    feed: tuple[float, ...],
    incipient: tuple[float, ...],
    parent_phase: FlashPhaseResult,
    incipient_phase: FlashPhaseResult,
) -> tuple[float | None, ...]:
    """Return ``ln(f_i^incipient / f_i^parent)`` for active components."""

    residuals: list[float | None] = []
    for index, (feed_fraction, incipient_fraction) in enumerate(
        zip(feed, incipient, strict=True)
    ):
        if feed_fraction == 0.0:
            residuals.append(None)
            continue
        if incipient_fraction <= 0.0:
            raise ValueError("active incipient fraction must be positive.")
        parent_log_phi = parent_phase.component_log_fugacity_coefficients[index]
        incipient_log_phi = incipient_phase.component_log_fugacity_coefficients[index]
        residual = (
            log(incipient_fraction)
            + incipient_log_phi
            - log(feed_fraction)
            - parent_log_phi
        )
        _require_finite(residual, f"fugacity equilibrium residual[{index}]")
        residuals.append(residual)
    return tuple(residuals)


def _failed_evaluation(
    saturation_kind: SaturationKind,
    pressure_pa: float,
    feed: tuple[float, ...],
    history: list[SaturationPressureIteration],
    diagnostics: list[EOSDiagnostic],
    reason: str,
    status: InnerSaturationStatus = InnerSaturationStatus.FAILED,
) -> SaturationPressureEvaluation:
    last = history[-1] if history else None
    return SaturationPressureEvaluation(
        saturation_kind=saturation_kind,
        pressure_pa=pressure_pa,
        status=status,
        converged=False,
        objective=(last.saturation_objective if last else None),
        parent_composition=feed,
        incipient_composition=(last.incipient_composition if last else ()),
        k_values=(last.k_values if last else ()),
        parent_phase=(last.parent_phase if last else None),
        incipient_phase=(last.incipient_phase if last else None),
        fugacity_equilibrium_residuals=(
            last.fugacity_equilibrium_residuals if last else ()
        ),
        maximum_log_k_residual=(last.maximum_log_k_residual if last else None),
        composition_change=(last.composition_change if last else None),
        incipient_sum_residual=(last.incipient_sum_residual if last else None),
        history=tuple(history),
        failure_reason=reason,
        diagnostics=tuple(diagnostics),
    )


def evaluate_saturation_pressure(
    mixture: FluidMixture,
    temperature_k: float,
    pressure_pa: float,
    saturation_kind: SaturationKind,
    interaction_provenance: PhaseInteractionProvenance,
    binary_interactions: BinaryInteractionMapping | None = None,
    binary_interaction_policy: BinaryInteractionPolicy = (
        BinaryInteractionPolicy.DEFAULT_ZERO
    ),
    maximum_iterations: int = DEFAULT_MAXIMUM_INNER_ITERATIONS,
    *,
    initial_log_k_values: tuple[float, ...] | None = None,
    successive_substitution_damping_factor: float = 1.0,
    successive_substitution_acceleration_enabled: bool = False,
) -> SaturationPressureEvaluation:
    """Solve the normalized incipient phase at one fixed trial pressure.

    ``initial_log_k_values`` supports continuation callers. Omitting it retains
    the isolated-saturation Wilson initialization used before Module 9.
    """

    _require_positive(temperature_k, "temperature_k")
    _require_positive(pressure_pa, "pressure_pa")
    _require_kind(saturation_kind)
    if not isinstance(maximum_iterations, int) or maximum_iterations <= 0:
        raise ValueError("maximum_iterations must be a positive integer.")
    calculate_damped_log_k_values(
        (0.0,), (0.0,), successive_substitution_damping_factor
    )
    calculate_safeguarded_log_k_acceleration(
        (0.0,),
        (0.0,),
        None,
        None,
        successive_substitution_acceleration_enabled,
    )
    feed = _feed_composition(mixture)
    parent_kind, incipient_kind = _phase_kinds(saturation_kind)
    if initial_log_k_values is None:
        initial_k = calculate_wilson_k_values(
            tuple(item.component for item in mixture.components),
            temperature_k,
            pressure_pa,
        )
        log_k_values = tuple(log(item.k_value) for item in initial_k)
    else:
        if not isinstance(initial_log_k_values, tuple) or len(
            initial_log_k_values
        ) != len(mixture.components):
            raise ValueError("initial_log_k_values must be an aligned immutable tuple.")
        for index, value in enumerate(initial_log_k_values):
            _require_finite(value, f"initial_log_k_values[{index}]")
        # Validate that every seed maps to a representable, strictly positive K.
        k_values_from_log_values(initial_log_k_values)
        log_k_values = initial_log_k_values
    history: list[SaturationPressureIteration] = []
    diagnostics: list[EOSDiagnostic] = []
    prior_log_k_values: list[tuple[float, ...]] = []
    previous_target_log_k_values: tuple[float, ...] | None = None
    previous_parent_selection = None
    previous_incipient_selection = None

    try:
        parent_phase = evaluate_flash_phase(
            mixture,
            feed,
            temperature_k,
            pressure_pa,
            parent_kind,
            None,
            binary_interactions,
            binary_interaction_policy,
            interaction_provenance=interaction_provenance,
        )
    except ValueError as error:
        reason = f"Parent phase evaluation failed: {error}"
        diagnostics.append(_failure_diagnostic("SATURATION_PARENT_FAILURE", reason))
        return _failed_evaluation(
            saturation_kind, pressure_pa, feed, history, diagnostics, reason
        )

    for iteration_number in range(1, maximum_iterations + 1):
        try:
            k_values = k_values_from_log_values(log_k_values)
            incipient = _normalize_incipient_composition(
                feed, log_k_values, saturation_kind
            )
            incipient_phase = evaluate_flash_phase(
                mixture,
                incipient,
                temperature_k,
                pressure_pa,
                incipient_kind,
                None,
                binary_interactions,
                binary_interaction_policy,
                interaction_provenance=interaction_provenance,
            )
            if (
                len(mixture.components) == 1
                and abs(
                    parent_phase.selected_compressibility_factor
                    - incipient_phase.selected_compressibility_factor
                )
                <= PURE_PHASE_ROOT_SEPARATION_TOLERANCE
            ):
                raise ValueError(
                    "pure-component saturation requires distinct liquid and "
                    "vapor roots."
                )
            liquid_log_phi, vapor_log_phi = _phase_log_phi(
                saturation_kind, parent_phase, incipient_phase
            )
            target_log_k = tuple(
                liquid_value - vapor_value
                for liquid_value, vapor_value in zip(
                    liquid_log_phi, vapor_log_phi, strict=True
                )
            )
            for index, value in enumerate(target_log_k):
                _require_finite(value, f"target saturation log K[{index}]")
            acceleration = (
                calculate_safeguarded_log_k_acceleration(
                    log_k_values,
                    target_log_k,
                    prior_log_k_values[-1] if prior_log_k_values else None,
                    previous_target_log_k_values,
                    True,
                )
                if successive_substitution_acceleration_enabled
                else None
            )
            update_target_log_k = (
                target_log_k
                if acceleration is None
                else acceleration.target_log_k_values
            )
            updated_log_k = calculate_damped_log_k_values(
                log_k_values,
                update_target_log_k,
                successive_substitution_damping_factor,
            )
            updated_incipient = _normalize_incipient_composition(
                feed, target_log_k, saturation_kind
            )
            maximum_log_k_residual = max(
                abs(target - current)
                for target, current in zip(target_log_k, log_k_values, strict=True)
            )
            composition_change = max(
                abs(updated - current)
                for updated, current in zip(updated_incipient, incipient, strict=True)
            )
            objective = _saturation_objective_from_log_k(
                feed, target_log_k, saturation_kind
            )
            sum_residual = fsum(incipient) - 1.0
            fugacity_residuals = _fugacity_residuals(
                feed,
                incipient,
                parent_phase,
                incipient_phase,
            )
            maximum_fugacity_residual = max(
                (abs(value) for value in fugacity_residuals if value is not None),
                default=0.0,
            )
        except ValueError as error:
            reason = f"Incipient phase iteration failed: {error}"
            diagnostics.append(_failure_diagnostic("SATURATION_INNER_FAILURE", reason))
            return _failed_evaluation(
                saturation_kind, pressure_pa, feed, history, diagnostics, reason
            )

        _append_unique_diagnostics(diagnostics, parent_phase.diagnostics)
        _append_unique_diagnostics(diagnostics, incipient_phase.diagnostics)
        if previous_parent_selection is not None:
            switched = detect_phase_root_switch(
                previous_parent_selection, parent_phase.root_selection
            )
            if switched is not None:
                _append_unique_diagnostics(diagnostics, (switched,))
        if previous_incipient_selection is not None:
            switched = detect_phase_root_switch(
                previous_incipient_selection, incipient_phase.root_selection
            )
            if switched is not None:
                _append_unique_diagnostics(diagnostics, (switched,))

        iteration = SaturationPressureIteration(
            iteration=iteration_number,
            pressure_pa=pressure_pa,
            log_k_values=log_k_values,
            k_values=k_values,
            incipient_composition=incipient,
            parent_phase=parent_phase,
            incipient_phase=incipient_phase,
            acceleration=acceleration,
            updated_log_k_values=updated_log_k,
            maximum_log_k_residual=maximum_log_k_residual,
            composition_change=composition_change,
            saturation_objective=objective,
            incipient_sum_residual=sum_residual,
            fugacity_equilibrium_residuals=fugacity_residuals,
            maximum_fugacity_equilibrium_residual=maximum_fugacity_residual,
            diagnostics=tuple(diagnostics),
        )
        history.append(iteration)
        if (
            maximum_log_k_residual <= INNER_LOG_K_TOLERANCE
            and composition_change <= INNER_COMPOSITION_TOLERANCE
            and abs(sum_residual) <= INCIPIENT_SUM_TOLERANCE
            and parent_phase.mechanical_classification
            is MechanicalStabilityClassification.STABLE
            and incipient_phase.mechanical_classification
            is MechanicalStabilityClassification.STABLE
        ):
            composition_separation = max(
                abs(parent - trial)
                for parent, trial in zip(feed, incipient, strict=True)
            )
            root_separation = abs(
                parent_phase.selected_compressibility_factor
                - incipient_phase.selected_compressibility_factor
            )
            active_log_k = tuple(
                value
                for fraction, value in zip(feed, target_log_k, strict=True)
                if fraction > 0.0
            )
            unity_equilibrium_ratios = (
                len(active_log_k) > 1
                and max(abs(value) for value in active_log_k) <= TRIVIAL_LOG_K_TOLERANCE
            )
            if unity_equilibrium_ratios or (
                composition_separation <= INNER_COMPOSITION_TOLERANCE
                and root_separation <= PURE_PHASE_ROOT_SEPARATION_TOLERANCE
            ):
                reason = (
                    "The inner iteration returned the trivial parent phase, "
                    "not a distinct incipient phase."
                )
                diagnostics.append(
                    _failure_diagnostic(TRIVIAL_STATE_DIAGNOSTIC_CODE, reason)
                )
                return _failed_evaluation(
                    saturation_kind,
                    pressure_pa,
                    feed,
                    history,
                    diagnostics,
                    reason,
                )
            return SaturationPressureEvaluation(
                saturation_kind=saturation_kind,
                pressure_pa=pressure_pa,
                status=InnerSaturationStatus.CONVERGED,
                converged=True,
                objective=objective,
                parent_composition=feed,
                incipient_composition=incipient,
                k_values=k_values,
                parent_phase=parent_phase,
                incipient_phase=incipient_phase,
                fugacity_equilibrium_residuals=fugacity_residuals,
                maximum_log_k_residual=maximum_log_k_residual,
                composition_change=composition_change,
                incipient_sum_residual=sum_residual,
                history=tuple(history),
                failure_reason=None,
                diagnostics=tuple(diagnostics),
            )

        pattern = detect_flash_iterate_pattern(
            log_k_values,
            updated_log_k,
            prior_log_k_values[-1] if prior_log_k_values else None,
        )
        if pattern is FlashIteratePattern.OSCILLATION:
            reason = "A two-cycle oscillation was detected in saturation log K."
            diagnostics.append(
                _failure_diagnostic("SATURATION_INNER_OSCILLATION", reason)
            )
            return _failed_evaluation(
                saturation_kind, pressure_pa, feed, history, diagnostics, reason
            )
        if pattern is FlashIteratePattern.STAGNATION:
            reason = "The saturation inner iteration stagnated before convergence."
            diagnostics.append(
                _failure_diagnostic("SATURATION_INNER_STAGNATION", reason)
            )
            return _failed_evaluation(
                saturation_kind, pressure_pa, feed, history, diagnostics, reason
            )
        prior_log_k_values.append(log_k_values)
        previous_parent_selection = parent_phase.root_selection
        previous_incipient_selection = incipient_phase.root_selection
        previous_target_log_k_values = target_log_k
        log_k_values = updated_log_k

    reason = "Maximum saturation inner iterations reached without convergence."
    diagnostics.append(_failure_diagnostic("SATURATION_INNER_MAXIMUM", reason))
    return _failed_evaluation(
        saturation_kind,
        pressure_pa,
        feed,
        history,
        diagnostics,
        reason,
        InnerSaturationStatus.NOT_CONVERGED,
    )


def _phase_interaction_provenance(
    mixture: FluidMixture,
    temperature_k: float,
    pressure_pa: float,
    binary_interactions: BinaryInteractionMapping | None,
    binary_interaction_policy: BinaryInteractionPolicy,
) -> PhaseInteractionProvenance:
    parameters = calculate_peng_robinson_mixture_parameters(
        mixture,
        temperature_k,
        pressure_pa,
        binary_interactions,
        binary_interaction_policy,
    )
    return PhaseInteractionProvenance(
        binary_interaction_policy=parameters.binary_interaction_policy,
        binary_interactions=parameters.binary_interactions,
        supplied_binary_interaction_pairs=parameters.supplied_binary_interaction_pairs,
        defaulted_binary_interaction_pairs=(
            parameters.defaulted_binary_interaction_pairs
        ),
    )


def _validate_newton_controls(
    saturation_newton_enabled: bool,
    newton_max_iterations: int,
    newton_max_jacobian_condition_number: float,
    newton_line_search_reduction_factor: float,
    newton_minimum_line_search_factor: float,
    newton_max_backtracking_iterations: int,
) -> None:
    if not isinstance(saturation_newton_enabled, bool):
        raise ValueError("saturation_newton_enabled must be a boolean.")
    if type(newton_max_iterations) is not int or newton_max_iterations <= 0:
        raise ValueError("newton_max_iterations must be a positive integer.")
    if isinstance(newton_max_jacobian_condition_number, bool):
        raise ValueError(
            "newton_max_jacobian_condition_number must be a finite positive number."
        )
    if isinstance(newton_line_search_reduction_factor, bool):
        raise ValueError(
            "newton_line_search_reduction_factor must be a finite positive number."
        )
    _require_positive(
        newton_max_jacobian_condition_number,
        "newton_max_jacobian_condition_number",
    )
    if isinstance(newton_minimum_line_search_factor, bool):
        raise ValueError(
            "newton_minimum_line_search_factor must be a finite positive number."
        )
    _require_positive(
        newton_line_search_reduction_factor,
        "newton_line_search_reduction_factor",
    )
    if newton_line_search_reduction_factor >= 1.0:
        raise ValueError("newton_line_search_reduction_factor must be less than one.")
    _require_positive(
        newton_minimum_line_search_factor,
        "newton_minimum_line_search_factor",
    )
    if newton_minimum_line_search_factor >= 1.0:
        raise ValueError("newton_minimum_line_search_factor must be less than one.")
    if (
        type(newton_max_backtracking_iterations) is not int
        or newton_max_backtracking_iterations < 0
    ):
        raise ValueError(
            "newton_max_backtracking_iterations must be a non-negative integer."
        )


def _active_newton_mixture(
    mixture: FluidMixture,
) -> tuple[FluidMixture, tuple[int, ...]]:
    active_indices = tuple(
        index
        for index, item in enumerate(mixture.components)
        if item.mole_fraction > 0.0
    )
    active_mixture = FluidMixture(
        tuple(
            MixtureComponent(
                mixture.components[index].component,
                mixture.components[index].mole_fraction,
            )
            for index in active_indices
        )
    )
    return active_mixture, active_indices


def _active_interactions(
    binary_interactions: BinaryInteractionMapping | None,
    active_mixture: FluidMixture,
) -> BinaryInteractionMapping | None:
    if binary_interactions is None:
        return None
    names = {item.component.name.casefold() for item in active_mixture.components}
    return {
        pair: value
        for pair, value in binary_interactions.items()
        if pair[0].casefold() in names and pair[1].casefold() in names
    }


def _provenance_from_parameters(
    parameters: PengRobinsonMixtureParameters,
) -> PhaseInteractionProvenance:
    # Kept local so Newton phase evaluation uses the exact metadata generated
    # for its reduced active-component mixture.
    return PhaseInteractionProvenance(
        binary_interaction_policy=parameters.binary_interaction_policy,
        binary_interactions=parameters.binary_interactions,
        supplied_binary_interaction_pairs=parameters.supplied_binary_interaction_pairs,
        defaulted_binary_interaction_pairs=(
            parameters.defaulted_binary_interaction_pairs
        ),
    )


def _newton_composition_from_coordinates(
    coordinates: tuple[float, ...],
    active_component_count: int,
) -> tuple[float, ...]:
    if len(coordinates) != active_component_count - 1:
        raise ValueError("Newton composition-coordinate count is inconsistent.")
    for index, value in enumerate(coordinates):
        _require_finite(value, f"Newton composition coordinate[{index}]")
        if value <= 0.0:
            raise ValueError("Newton active composition coordinates must be positive.")
    reference_fraction = 1.0 - fsum(coordinates)
    if reference_fraction <= 0.0:
        raise ValueError("Newton reference-component fraction must be positive.")
    composition = (*coordinates, reference_fraction)
    if not isclose(
        fsum(composition),
        1.0,
        rel_tol=0.0,
        abs_tol=MOLE_FRACTION_TOLERANCE,
    ):
        raise ValueError("Newton incipient composition must remain normalized.")
    return composition


def _evaluate_saturation_newton_system(
    mixture: FluidMixture,
    temperature_k: float,
    saturation_kind: SaturationKind,
    coordinates: tuple[float, ...],
    log_pressure: float,
    minimum_pressure_pa: float,
    maximum_pressure_pa: float,
    binary_interactions: BinaryInteractionMapping | None,
    binary_interaction_policy: BinaryInteractionPolicy,
) -> _SaturationNewtonSystemEvaluation:
    """Evaluate the complete local saturation residual and analytical Jacobian.

    For active component ``i``, ``R_i = ln(z_i) + ln(phi_i^parent)
    - ln(w_i) - ln(phi_i^incipient)``. The unknown vector contains the
    ``m-1`` direct simplex coordinates followed by ``ln(P)``.
    """

    _require_finite(log_pressure, "Newton log pressure")
    lower_log = log(minimum_pressure_pa)
    upper_log = log(maximum_pressure_pa)
    if not lower_log <= log_pressure <= upper_log:
        raise ValueError("Newton pressure proposal lies outside configured bounds.")
    pressure_pa = exp(log_pressure)
    active_mixture, _ = _active_newton_mixture(mixture)
    active_feed = _feed_composition(active_mixture)
    incipient = _newton_composition_from_coordinates(
        coordinates, len(active_mixture.components)
    )
    active_binary_interactions = _active_interactions(
        binary_interactions, active_mixture
    )
    parent_parameters = calculate_peng_robinson_mixture_parameters(
        active_mixture,
        temperature_k,
        pressure_pa,
        active_binary_interactions,
        binary_interaction_policy,
    )
    provenance = _provenance_from_parameters(parent_parameters)
    parent_kind, incipient_kind = _phase_kinds(saturation_kind)
    parent_phase = evaluate_flash_phase(
        active_mixture,
        active_feed,
        temperature_k,
        pressure_pa,
        parent_kind,
        None,
        active_binary_interactions,
        binary_interaction_policy,
        interaction_provenance=provenance,
    )
    incipient_phase = evaluate_flash_phase(
        active_mixture,
        incipient,
        temperature_k,
        pressure_pa,
        incipient_kind,
        None,
        active_binary_interactions,
        binary_interaction_policy,
        interaction_provenance=provenance,
    )
    if (
        len(active_mixture.components) == 1
        and abs(
            parent_phase.selected_compressibility_factor
            - incipient_phase.selected_compressibility_factor
        )
        <= PURE_PHASE_ROOT_SEPARATION_TOLERANCE
    ):
        raise ValueError(
            "pure-component Newton saturation requires distinct physical roots."
        )
    incipient_mixture = FluidMixture(
        tuple(
            MixtureComponent(item.component, fraction)
            for item, fraction in zip(active_mixture.components, incipient, strict=True)
        )
    )
    incipient_parameters = calculate_peng_robinson_mixture_parameters(
        incipient_mixture,
        temperature_k,
        pressure_pa,
        active_binary_interactions,
        binary_interaction_policy,
    )
    parent_derivatives = calculate_fixed_root_mixture_fugacity_derivatives(
        parent_parameters,
        parent_phase.selected_compressibility_factor,
        active_binary_interactions,
    )
    incipient_derivatives = calculate_fixed_root_mixture_fugacity_derivatives(
        incipient_parameters,
        incipient_phase.selected_compressibility_factor,
        active_binary_interactions,
    )
    if not parent_derivatives.applicable or not incipient_derivatives.applicable:
        reason = (
            parent_derivatives.failure_reason
            if not parent_derivatives.applicable
            else incipient_derivatives.failure_reason
        )
        raise ValueError(f"fixed-root derivatives are unavailable: {reason}")
    parent_pressure = parent_derivatives.log_fugacity_log_pressure_derivatives
    incipient_pressure = incipient_derivatives.log_fugacity_log_pressure_derivatives
    incipient_composition = incipient_derivatives.log_fugacity_composition_derivatives
    if (
        parent_pressure is None
        or incipient_pressure is None
        or incipient_composition is None
    ):
        raise ValueError("applicable Newton derivatives are incomplete.")
    phase_values = zip(
        active_feed,
        parent_phase.component_log_fugacity_coefficients,
        incipient,
        incipient_phase.component_log_fugacity_coefficients,
        strict=True,
    )
    residual_values: list[float] = []
    for (
        parent_fraction,
        parent_log_phi,
        incipient_fraction,
        incipient_log_phi,
    ) in phase_values:
        residual_values.append(
            log(parent_fraction)
            + parent_log_phi
            - log(incipient_fraction)
            - incipient_log_phi
        )
    residuals = tuple(residual_values)
    reference_index = len(incipient) - 1
    rows: list[tuple[float, ...]] = []
    for component_index, fraction in enumerate(incipient):
        composition_columns = tuple(
            -(
                (1.0 if component_index == coordinate_index else 0.0)
                - (1.0 if component_index == reference_index else 0.0)
            )
            / fraction
            - incipient_composition[component_index][column]
            for column, coordinate_index in enumerate(
                incipient_derivatives.parameter_derivatives.independent_component_indices
            )
        )
        rows.append(
            (
                *composition_columns,
                parent_pressure[component_index] - incipient_pressure[component_index],
            )
        )
    for index, value in enumerate(residuals):
        _require_finite(value, f"Newton residual[{index}]")
    for row_index, row in enumerate(rows):
        for column_index, value in enumerate(row):
            _require_finite(value, f"Newton Jacobian[{row_index},{column_index}]")
    return _SaturationNewtonSystemEvaluation(
        pressure_pa=pressure_pa,
        active_incipient_composition=incipient,
        residuals=residuals,
        jacobian=tuple(rows),
        parent_phase=parent_phase,
        incipient_phase=incipient_phase,
    )


def _root_branch_is_continuous(
    previous: FlashPhaseResult,
    current: FlashPhaseResult,
) -> bool:
    if previous.trial_kind is not current.trial_kind:
        return False
    previous_candidates = previous.root_selection.candidates
    current_candidates = current.root_selection.candidates
    if len(previous_candidates) != len(current_candidates):
        return False
    if tuple(item.classification for item in previous_candidates) != tuple(
        item.classification for item in current_candidates
    ):
        return False
    current_stable = tuple(
        item.compressibility_factor
        for item in current_candidates
        if item.classification is MechanicalStabilityClassification.STABLE
    )
    if not current_stable:
        return False
    previous_z = previous.selected_compressibility_factor
    current_z = current.selected_compressibility_factor
    distances = sorted(abs(value - previous_z) for value in current_stable)
    scale = max(1.0, abs(previous_z), abs(current_z))
    tolerance = 1e-8 * scale
    if len(distances) > 1 and abs(distances[1] - distances[0]) <= tolerance:
        return False
    closest = min(current_stable, key=lambda value: abs(value - previous_z))
    return abs(closest - current_z) <= tolerance


def _newton_is_trivial(
    feed: tuple[float, ...],
    incipient: tuple[float, ...],
    saturation_kind: SaturationKind,
    parent_phase: FlashPhaseResult,
    incipient_phase: FlashPhaseResult,
) -> bool:
    if len(feed) <= 1:
        return False
    direction = 1.0 if saturation_kind is SaturationKind.BUBBLE_POINT else -1.0
    log_k = tuple(
        direction * (log(trial) - log(parent))
        for parent, trial in zip(feed, incipient, strict=True)
    )
    composition_separation = max(
        abs(parent - trial) for parent, trial in zip(feed, incipient, strict=True)
    )
    root_separation = abs(
        parent_phase.selected_compressibility_factor
        - incipient_phase.selected_compressibility_factor
    )
    return max(abs(value) for value in log_k) <= TRIVIAL_LOG_K_TOLERANCE or (
        composition_separation <= INNER_COMPOSITION_TOLERANCE
        and root_separation <= PURE_PHASE_ROOT_SEPARATION_TOLERANCE
    )


def _empty_result(
    saturation_kind: SaturationKind,
    status: SaturationStatus,
    mixture: FluidMixture,
    temperature_k: float,
    estimate: float,
    bounds: tuple[float, float],
    provenance: PhaseInteractionProvenance,
    evaluations: list[SaturationPressureEvaluation],
    diagnostics: list[EOSDiagnostic],
    reason: str,
) -> SaturationPressureResult:
    return SaturationPressureResult(
        saturation_kind=saturation_kind,
        status=status,
        feed_mixture=mixture,
        feed_composition=_feed_composition(mixture),
        temperature_k=temperature_k,
        pressure_pa=None,
        initial_pressure_estimate_pa=estimate,
        pressure_bounds_pa=bounds,
        bracket_pressures_pa=None,
        bracket_objective_values=None,
        parent_composition=_feed_composition(mixture),
        incipient_composition=(),
        k_values=(),
        parent_phase=None,
        incipient_phase=None,
        fugacity_equilibrium_residuals=(),
        maximum_fugacity_equilibrium_residual=None,
        composition_sum_residual=None,
        pressure_residual=None,
        pressure_solver_iterations=0,
        pressure_solver_function_calls=0,
        evaluation_history=tuple(evaluations),
        convergence_status=status,
        failure_reason=reason,
        diagnostics=tuple(diagnostics),
        binary_interaction_policy=provenance.binary_interaction_policy,
        binary_interactions=provenance.binary_interactions,
        supplied_binary_interaction_pairs=(
            provenance.supplied_binary_interaction_pairs
        ),
        defaulted_binary_interaction_pairs=(
            provenance.defaulted_binary_interaction_pairs
        ),
    )


def _rejected_newton_attempt(
    reason: str,
    *,
    iteration_count: int = 0,
    function_evaluations: int = 0,
    initial_residual_norm: float | None = None,
    final_residual_norm: float | None = None,
    full_steps: int = 0,
    backtracked_steps: int = 0,
    rejected_steps: int = 0,
    history: tuple[SaturationNewtonIteration, ...] = (),
) -> SaturationNewtonAttempt:
    return SaturationNewtonAttempt(
        status=SaturationNewtonStatus.REJECTED,
        converged=False,
        iteration_count=iteration_count,
        function_evaluations=function_evaluations,
        initial_residual_norm=initial_residual_norm,
        final_residual_norm=final_residual_norm,
        full_steps=full_steps,
        backtracked_steps=backtracked_steps,
        rejected_steps=rejected_steps,
        failure_reason=reason,
        history=history,
    )


def _attempt_saturation_newton(
    mixture: FluidMixture,
    temperature_k: float,
    saturation_kind: SaturationKind,
    minimum_pressure_pa: float,
    maximum_pressure_pa: float,
    binary_interactions: BinaryInteractionMapping | None,
    binary_interaction_policy: BinaryInteractionPolicy,
    initial_log_k_values: tuple[float, ...] | None,
    newton_max_iterations: int,
    newton_max_jacobian_condition_number: float,
    newton_line_search_reduction_factor: float,
    newton_minimum_line_search_factor: float,
    newton_max_backtracking_iterations: int,
) -> tuple[
    SaturationNewtonAttempt,
    _SaturationNewtonSystemEvaluation | None,
    float | None,
]:
    """Attempt the local Newton layer without invoking the historical solver."""

    function_evaluations = 0
    initial_norm: float | None = None
    final_norm: float | None = None
    full_steps = 0
    backtracked_steps = 0
    rejected_steps = 0
    history: list[SaturationNewtonIteration] = []

    def reject(
        reason: str,
    ) -> tuple[
        SaturationNewtonAttempt,
        _SaturationNewtonSystemEvaluation | None,
        float | None,
    ]:
        return (
            _rejected_newton_attempt(
                reason,
                iteration_count=len(history),
                function_evaluations=function_evaluations,
                initial_residual_norm=initial_norm,
                final_residual_norm=final_norm,
                full_steps=full_steps,
                backtracked_steps=backtracked_steps,
                rejected_steps=rejected_steps,
                history=tuple(history),
            ),
            None,
            None,
        )

    try:
        _require_positive(temperature_k, "temperature_k")
        _require_positive(minimum_pressure_pa, "minimum_pressure_pa")
        _require_positive(maximum_pressure_pa, "maximum_pressure_pa")
        _require_kind(saturation_kind)
        if minimum_pressure_pa >= maximum_pressure_pa:
            raise ValueError("minimum pressure must be less than maximum pressure.")
        estimates = calculate_wilson_pressure_estimates(mixture, temperature_k)
        estimate = (
            estimates.bubble_pressure_pa
            if saturation_kind is SaturationKind.BUBBLE_POINT
            else estimates.dew_pressure_pa
        )
        if initial_log_k_values is None:
            pressure_seed = min(max(estimate, minimum_pressure_pa), maximum_pressure_pa)
            initial_k = calculate_wilson_k_values(
                tuple(item.component for item in mixture.components),
                temperature_k,
                pressure_seed,
            )
            seed_log_k = tuple(log(item.k_value) for item in initial_k)
        else:
            if len(initial_log_k_values) != len(mixture.components):
                raise ValueError(
                    "initial_log_k_values must be an aligned immutable tuple."
                )
            k_values_from_log_values(initial_log_k_values)
            seed_log_k = initial_log_k_values
            pressure_seed = exp(
                0.5 * (log(minimum_pressure_pa) + log(maximum_pressure_pa))
            )
        full_feed = _feed_composition(mixture)
        initial_incipient = _normalize_incipient_composition(
            full_feed, seed_log_k, saturation_kind
        )
        _, active_indices = _active_newton_mixture(mixture)
        active_incipient = tuple(initial_incipient[index] for index in active_indices)
        active_total = fsum(active_incipient)
        active_incipient = tuple(value / active_total for value in active_incipient)
        coordinates = active_incipient[:-1]
        log_pressure = log(pressure_seed)
        interaction_snapshot = (
            None if binary_interactions is None else dict(binary_interactions)
        )
        # Validate the complete, unreduced interaction input before an active-
        # component Newton system is allowed to accept a result.
        _phase_interaction_provenance(
            mixture,
            temperature_k,
            pressure_seed,
            interaction_snapshot,
            binary_interaction_policy,
        )
        current = _evaluate_saturation_newton_system(
            mixture,
            temperature_k,
            saturation_kind,
            coordinates,
            log_pressure,
            minimum_pressure_pa,
            maximum_pressure_pa,
            interaction_snapshot,
            binary_interaction_policy,
        )
        function_evaluations += 1
        current_norm = max(abs(value) for value in current.residuals)
        initial_norm = current_norm
        final_norm = current_norm
        active_mixture, _ = _active_newton_mixture(mixture)
        active_feed = _feed_composition(active_mixture)
        if _newton_is_trivial(
            active_feed,
            current.active_incipient_composition,
            saturation_kind,
            current.parent_phase,
            current.incipient_phase,
        ):
            return reject("Newton initialization collapsed to the trivial state.")
    except (OverflowError, TypeError, ValueError) as error:
        return reject(f"Newton initialization was unsuitable: {error}")

    for iteration_number in range(1, newton_max_iterations + 1):
        if current_norm <= INNER_LOG_K_TOLERANCE:
            attempt = SaturationNewtonAttempt(
                status=SaturationNewtonStatus.CONVERGED,
                converged=True,
                iteration_count=len(history),
                function_evaluations=function_evaluations,
                initial_residual_norm=initial_norm,
                final_residual_norm=current_norm,
                full_steps=full_steps,
                backtracked_steps=backtracked_steps,
                rejected_steps=rejected_steps,
                failure_reason=None,
                history=tuple(history),
            )
            return attempt, current, estimate
        matrix = np.asarray(current.jacobian, dtype=float)
        residual = np.asarray(current.residuals, dtype=float)
        if not np.all(np.isfinite(matrix)) or not np.all(np.isfinite(residual)):
            return reject("Newton Jacobian or residual is non-finite.")
        try:
            condition_number = float(np.linalg.cond(matrix))
        except np.linalg.LinAlgError as error:
            return reject(f"Newton Jacobian conditioning failed: {error}")
        if not isfinite(condition_number):
            return reject("Newton Jacobian condition number is non-finite.")
        if condition_number > newton_max_jacobian_condition_number:
            return reject(
                "Newton Jacobian exceeds the configured condition-number safeguard."
            )
        try:
            step = np.linalg.solve(matrix, -residual)
        except np.linalg.LinAlgError as error:
            return reject(f"Newton linear solve failed: {error}")
        if not np.all(np.isfinite(step)):
            return reject("Newton linear solve returned a non-finite step.")
        step_norm = float(np.linalg.norm(step, ord=np.inf))
        alpha = 1.0
        accepted: _SaturationNewtonSystemEvaluation | None = None
        accepted_coordinates: tuple[float, ...] | None = None
        accepted_log_pressure: float | None = None
        rejected_this_iteration = 0
        last_rejection_reason = "no trial was evaluated"
        for _ in range(newton_max_backtracking_iterations + 1):
            trial_coordinates = tuple(
                coordinate + alpha * float(step[index])
                for index, coordinate in enumerate(coordinates)
            )
            trial_log_pressure = log_pressure + alpha * float(step[-1])
            try:
                trial = _evaluate_saturation_newton_system(
                    mixture,
                    temperature_k,
                    saturation_kind,
                    trial_coordinates,
                    trial_log_pressure,
                    minimum_pressure_pa,
                    maximum_pressure_pa,
                    interaction_snapshot,
                    binary_interaction_policy,
                )
                function_evaluations += 1
                trial_norm = max(abs(value) for value in trial.residuals)
                branch_continuous = _root_branch_is_continuous(
                    current.parent_phase, trial.parent_phase
                ) and _root_branch_is_continuous(
                    current.incipient_phase, trial.incipient_phase
                )
                trivial = _newton_is_trivial(
                    active_feed,
                    trial.active_incipient_composition,
                    saturation_kind,
                    trial.parent_phase,
                    trial.incipient_phase,
                )
                if branch_continuous and not trivial and trial_norm < current_norm:
                    accepted = trial
                    accepted_coordinates = trial_coordinates
                    accepted_log_pressure = trial_log_pressure
                    break
                if not branch_continuous:
                    last_rejection_reason = "root branch continuity was not preserved"
                elif trivial:
                    last_rejection_reason = "the trial was a prohibited trivial state"
                else:
                    last_rejection_reason = "the equilibrium merit did not improve"
            except (OverflowError, TypeError, ValueError) as error:
                last_rejection_reason = str(error)
            rejected_steps += 1
            rejected_this_iteration += 1
            alpha *= newton_line_search_reduction_factor
            if alpha < newton_minimum_line_search_factor:
                break
        if (
            accepted is None
            or accepted_coordinates is None
            or accepted_log_pressure is None
        ):
            return reject(
                "Newton line search found no branch-compatible improving step; "
                f"last rejection: {last_rejection_reason}."
            )
        if alpha == 1.0:
            full_steps += 1
        else:
            backtracked_steps += 1
        coordinates = accepted_coordinates
        log_pressure = accepted_log_pressure
        current = accepted
        current_norm = max(abs(value) for value in current.residuals)
        final_norm = current_norm
        history.append(
            SaturationNewtonIteration(
                iteration=iteration_number,
                pressure_pa=current.pressure_pa,
                incipient_composition=current.active_incipient_composition,
                residual_norm=current_norm,
                jacobian_condition_number=condition_number,
                step_norm=step_norm,
                line_search_factor=alpha,
                rejected_trial_count=rejected_this_iteration,
            )
        )
    return reject(
        "Maximum Newton iterations reached without full residual convergence."
    )


def _build_newton_saturation_result(
    mixture: FluidMixture,
    temperature_k: float,
    saturation_kind: SaturationKind,
    minimum_pressure_pa: float,
    maximum_pressure_pa: float,
    binary_interactions: BinaryInteractionMapping | None,
    binary_interaction_policy: BinaryInteractionPolicy,
    attempt: SaturationNewtonAttempt,
    state: _SaturationNewtonSystemEvaluation,
    estimate: float,
) -> SaturationPressureResult:
    """Reconstruct a full-order state and apply the historical physical gates."""

    full_feed = _feed_composition(mixture)
    _, active_indices = _active_newton_mixture(mixture)
    active_by_index = dict(
        zip(active_indices, state.active_incipient_composition, strict=True)
    )
    incipient = tuple(
        active_by_index.get(index, 0.0) for index in range(len(full_feed))
    )
    interaction_snapshot = (
        None if binary_interactions is None else dict(binary_interactions)
    )
    provenance = _phase_interaction_provenance(
        mixture,
        temperature_k,
        state.pressure_pa,
        interaction_snapshot,
        binary_interaction_policy,
    )
    parent_kind, incipient_kind = _phase_kinds(saturation_kind)
    parent_phase = evaluate_flash_phase(
        mixture,
        full_feed,
        temperature_k,
        state.pressure_pa,
        parent_kind,
        None,
        interaction_snapshot,
        binary_interaction_policy,
        interaction_provenance=provenance,
    )
    incipient_phase = evaluate_flash_phase(
        mixture,
        incipient,
        temperature_k,
        state.pressure_pa,
        incipient_kind,
        None,
        interaction_snapshot,
        binary_interaction_policy,
        interaction_provenance=provenance,
    )
    if (
        abs(
            parent_phase.selected_compressibility_factor
            - state.parent_phase.selected_compressibility_factor
        )
        > 1e-11
        or abs(
            incipient_phase.selected_compressibility_factor
            - state.incipient_phase.selected_compressibility_factor
        )
        > 1e-11
    ):
        raise ValueError("full-order Newton reconstruction changed the selected root.")
    direction = 1.0 if saturation_kind is SaturationKind.BUBBLE_POINT else -1.0
    log_k_values = tuple(
        0.0
        if feed_fraction == 0.0
        else direction * (log(trial_fraction) - log(feed_fraction))
        for feed_fraction, trial_fraction in zip(full_feed, incipient, strict=True)
    )
    k_values = k_values_from_log_values(log_k_values)
    liquid_log_phi, vapor_log_phi = _phase_log_phi(
        saturation_kind, parent_phase, incipient_phase
    )
    target_log_k = tuple(
        liquid - vapor
        for liquid, vapor in zip(liquid_log_phi, vapor_log_phi, strict=True)
    )
    maximum_log_k_residual = max(
        abs(target - current)
        for fraction, target, current in zip(
            full_feed, target_log_k, log_k_values, strict=True
        )
        if fraction > 0.0
    )
    objective = _saturation_objective_from_log_k(
        full_feed, log_k_values, saturation_kind
    )
    sum_residual = fsum(incipient) - 1.0
    fugacity_residuals = _fugacity_residuals(
        full_feed, incipient, parent_phase, incipient_phase
    )
    maximum_fugacity_residual = max(
        (abs(value) for value in fugacity_residuals if value is not None),
        default=0.0,
    )
    diagnostics: list[EOSDiagnostic] = []
    _append_unique_diagnostics(diagnostics, parent_phase.diagnostics)
    _append_unique_diagnostics(diagnostics, incipient_phase.diagnostics)
    iteration = SaturationPressureIteration(
        iteration=max(1, attempt.iteration_count),
        pressure_pa=state.pressure_pa,
        log_k_values=log_k_values,
        k_values=k_values,
        incipient_composition=incipient,
        parent_phase=parent_phase,
        incipient_phase=incipient_phase,
        acceleration=None,
        updated_log_k_values=log_k_values,
        maximum_log_k_residual=maximum_log_k_residual,
        composition_change=0.0,
        saturation_objective=objective,
        incipient_sum_residual=sum_residual,
        fugacity_equilibrium_residuals=fugacity_residuals,
        maximum_fugacity_equilibrium_residual=maximum_fugacity_residual,
        diagnostics=tuple(diagnostics),
    )
    evaluation = SaturationPressureEvaluation(
        saturation_kind=saturation_kind,
        pressure_pa=state.pressure_pa,
        status=InnerSaturationStatus.CONVERGED,
        converged=True,
        objective=objective,
        parent_composition=full_feed,
        incipient_composition=incipient,
        k_values=k_values,
        parent_phase=parent_phase,
        incipient_phase=incipient_phase,
        fugacity_equilibrium_residuals=fugacity_residuals,
        maximum_log_k_residual=maximum_log_k_residual,
        composition_change=0.0,
        incipient_sum_residual=sum_residual,
        history=(iteration,),
        failure_reason=None,
        diagnostics=tuple(diagnostics),
    )
    final_converged = (
        abs(objective) <= SATURATION_OBJECTIVE_TOLERANCE
        and maximum_log_k_residual <= INNER_LOG_K_TOLERANCE
        and abs(sum_residual) <= INCIPIENT_SUM_TOLERANCE
        and maximum_fugacity_residual <= FUGACITY_EQUILIBRIUM_TOLERANCE
        and parent_phase.mechanical_classification
        is MechanicalStabilityClassification.STABLE
        and incipient_phase.mechanical_classification
        is MechanicalStabilityClassification.STABLE
        and isfinite(state.pressure_pa)
        and minimum_pressure_pa <= state.pressure_pa <= maximum_pressure_pa
    )
    active_feed = tuple(value for value in full_feed if value > 0.0)
    active_incipient = tuple(
        value
        for feed_fraction, value in zip(full_feed, incipient, strict=True)
        if feed_fraction > 0.0
    )
    if _newton_is_trivial(
        active_feed,
        active_incipient,
        saturation_kind,
        state.parent_phase,
        state.incipient_phase,
    ):
        final_converged = False
    if not final_converged:
        raise ValueError(
            "Newton state failed the historical saturation acceptance gates."
        )
    return SaturationPressureResult(
        saturation_kind=saturation_kind,
        status=SaturationStatus.CONVERGED,
        feed_mixture=mixture,
        feed_composition=full_feed,
        temperature_k=temperature_k,
        pressure_pa=state.pressure_pa,
        initial_pressure_estimate_pa=estimate,
        pressure_bounds_pa=(minimum_pressure_pa, maximum_pressure_pa),
        bracket_pressures_pa=None,
        bracket_objective_values=None,
        parent_composition=full_feed,
        incipient_composition=incipient,
        k_values=k_values,
        parent_phase=parent_phase,
        incipient_phase=incipient_phase,
        fugacity_equilibrium_residuals=fugacity_residuals,
        maximum_fugacity_equilibrium_residual=maximum_fugacity_residual,
        composition_sum_residual=sum_residual,
        pressure_residual=objective,
        pressure_solver_iterations=attempt.iteration_count,
        pressure_solver_function_calls=attempt.function_evaluations,
        evaluation_history=(evaluation,),
        convergence_status=SaturationStatus.CONVERGED,
        failure_reason=None,
        diagnostics=tuple(diagnostics),
        binary_interaction_policy=provenance.binary_interaction_policy,
        binary_interactions=provenance.binary_interactions,
        supplied_binary_interaction_pairs=provenance.supplied_binary_interaction_pairs,
        defaulted_binary_interaction_pairs=provenance.defaulted_binary_interaction_pairs,
        newton_attempt=attempt,
    )


def calculate_saturation_pressure(
    mixture: FluidMixture,
    temperature_k: float,
    saturation_kind: SaturationKind,
    minimum_pressure_pa: float = 1_000.0,
    maximum_pressure_pa: float = 100_000_000.0,
    binary_interactions: BinaryInteractionMapping | None = None,
    binary_interaction_policy: BinaryInteractionPolicy = (
        BinaryInteractionPolicy.DEFAULT_ZERO
    ),
    maximum_inner_iterations: int = DEFAULT_MAXIMUM_INNER_ITERATIONS,
    pressure_search_points: int = DEFAULT_PRESSURE_SEARCH_POINTS,
    maximum_outer_iterations: int = DEFAULT_MAXIMUM_OUTER_ITERATIONS,
    *,
    initial_log_k_values: tuple[float, ...] | None = None,
    successive_substitution_damping_factor: float = 1.0,
    successive_substitution_acceleration_enabled: bool = False,
    saturation_newton_enabled: bool = False,
    newton_max_iterations: int = DEFAULT_MAXIMUM_NEWTON_ITERATIONS,
    newton_max_jacobian_condition_number: float = (
        DEFAULT_MAXIMUM_NEWTON_JACOBIAN_CONDITION_NUMBER
    ),
    newton_line_search_reduction_factor: float = (
        DEFAULT_NEWTON_LINE_SEARCH_REDUCTION_FACTOR
    ),
    newton_minimum_line_search_factor: float = (
        DEFAULT_MINIMUM_NEWTON_LINE_SEARCH_FACTOR
    ),
    newton_max_backtracking_iterations: int = (
        DEFAULT_MAXIMUM_NEWTON_BACKTRACKING_ITERATIONS
    ),
) -> SaturationPressureResult:
    """Calculate saturation pressure with an optional local Newton first layer."""

    _validate_newton_controls(
        saturation_newton_enabled,
        newton_max_iterations,
        newton_max_jacobian_condition_number,
        newton_line_search_reduction_factor,
        newton_minimum_line_search_factor,
        newton_max_backtracking_iterations,
    )

    def historical() -> SaturationPressureResult:
        return _calculate_saturation_pressure_historical(
            mixture,
            temperature_k,
            saturation_kind,
            minimum_pressure_pa,
            maximum_pressure_pa,
            binary_interactions,
            binary_interaction_policy,
            maximum_inner_iterations,
            pressure_search_points,
            maximum_outer_iterations,
            initial_log_k_values=initial_log_k_values,
            successive_substitution_damping_factor=(
                successive_substitution_damping_factor
            ),
            successive_substitution_acceleration_enabled=(
                successive_substitution_acceleration_enabled
            ),
        )

    if not saturation_newton_enabled:
        return historical()
    attempt, state, estimate = _attempt_saturation_newton(
        mixture,
        temperature_k,
        saturation_kind,
        minimum_pressure_pa,
        maximum_pressure_pa,
        binary_interactions,
        binary_interaction_policy,
        initial_log_k_values,
        newton_max_iterations,
        newton_max_jacobian_condition_number,
        newton_line_search_reduction_factor,
        newton_minimum_line_search_factor,
        newton_max_backtracking_iterations,
    )
    if attempt.converged and state is not None and estimate is not None:
        try:
            return _build_newton_saturation_result(
                mixture,
                temperature_k,
                saturation_kind,
                minimum_pressure_pa,
                maximum_pressure_pa,
                binary_interactions,
                binary_interaction_policy,
                attempt,
                state,
                estimate,
            )
        except (OverflowError, TypeError, ValueError) as error:
            attempt = replace(
                attempt,
                status=SaturationNewtonStatus.REJECTED,
                converged=False,
                failure_reason=f"Newton final reconstruction was rejected: {error}",
            )
    return replace(historical(), newton_attempt=attempt)


def _calculate_saturation_pressure_historical(
    mixture: FluidMixture,
    temperature_k: float,
    saturation_kind: SaturationKind,
    minimum_pressure_pa: float = 1_000.0,
    maximum_pressure_pa: float = 100_000_000.0,
    binary_interactions: BinaryInteractionMapping | None = None,
    binary_interaction_policy: BinaryInteractionPolicy = (
        BinaryInteractionPolicy.DEFAULT_ZERO
    ),
    maximum_inner_iterations: int = DEFAULT_MAXIMUM_INNER_ITERATIONS,
    pressure_search_points: int = DEFAULT_PRESSURE_SEARCH_POINTS,
    maximum_outer_iterations: int = DEFAULT_MAXIMUM_OUTER_ITERATIONS,
    *,
    initial_log_k_values: tuple[float, ...] | None = None,
    successive_substitution_damping_factor: float = 1.0,
    successive_substitution_acceleration_enabled: bool = False,
) -> SaturationPressureResult:
    """Bracket and solve a fixed-temperature bubble- or dew-point pressure.

    The optional log-K seed is intended for continuation. The default remains
    the original isolated Wilson-seeded calculation.
    """

    _require_positive(temperature_k, "temperature_k")
    _require_positive(minimum_pressure_pa, "minimum_pressure_pa")
    _require_positive(maximum_pressure_pa, "maximum_pressure_pa")
    _require_kind(saturation_kind)
    if minimum_pressure_pa >= maximum_pressure_pa:
        raise ValueError("minimum pressure must be less than maximum pressure.")
    if not isinstance(pressure_search_points, int) or pressure_search_points < 3:
        raise ValueError("pressure_search_points must be an integer of at least 3.")
    if not isinstance(maximum_outer_iterations, int) or maximum_outer_iterations <= 0:
        raise ValueError("maximum_outer_iterations must be a positive integer.")
    if not isinstance(maximum_inner_iterations, int) or maximum_inner_iterations <= 0:
        raise ValueError("maximum_inner_iterations must be a positive integer.")
    calculate_damped_log_k_values(
        (0.0,), (0.0,), successive_substitution_damping_factor
    )
    calculate_safeguarded_log_k_acceleration(
        (0.0,),
        (0.0,),
        None,
        None,
        successive_substitution_acceleration_enabled,
    )

    estimates = calculate_wilson_pressure_estimates(mixture, temperature_k)
    estimate = (
        estimates.bubble_pressure_pa
        if saturation_kind is SaturationKind.BUBBLE_POINT
        else estimates.dew_pressure_pa
    )
    center = min(max(estimate, minimum_pressure_pa), maximum_pressure_pa)
    interaction_snapshot = (
        None if binary_interactions is None else dict(binary_interactions)
    )
    provenance = _phase_interaction_provenance(
        mixture,
        temperature_k,
        center,
        interaction_snapshot,
        binary_interaction_policy,
    )
    lower_log = log(minimum_pressure_pa)
    upper_log = log(maximum_pressure_pa)
    pressure_logs = {
        lower_log + index * (upper_log - lower_log) / (pressure_search_points - 1)
        for index in range(pressure_search_points)
    }
    pressure_logs.add(log(center))
    evaluations: list[SaturationPressureEvaluation] = []
    diagnostics: list[EOSDiagnostic] = []

    def evaluate_log_pressure(log_pressure: float) -> SaturationPressureEvaluation:
        pressure = exp(log_pressure)
        evaluation = evaluate_saturation_pressure(
            mixture,
            temperature_k,
            pressure,
            saturation_kind,
            provenance,
            interaction_snapshot,
            binary_interaction_policy,
            maximum_inner_iterations,
            initial_log_k_values=initial_log_k_values,
            successive_substitution_damping_factor=(
                successive_substitution_damping_factor
            ),
            successive_substitution_acceleration_enabled=(
                successive_substitution_acceleration_enabled
            ),
        )
        evaluations.append(evaluation)
        _append_unique_diagnostics(diagnostics, evaluation.diagnostics)
        return evaluation

    scanned = tuple(evaluate_log_pressure(value) for value in sorted(pressure_logs))
    exact = tuple(
        item
        for item in scanned
        if item.converged
        and item.objective is not None
        and abs(item.objective) <= SATURATION_OBJECTIVE_TOLERANCE
    )
    candidate_brackets: list[
        tuple[SaturationPressureEvaluation, SaturationPressureEvaluation]
    ] = []
    for left, right in zip(scanned[:-1], scanned[1:], strict=True):
        if (
            not left.converged
            or not right.converged
            or left.objective is None
            or right.objective is None
        ):
            continue
        if left.objective * right.objective < 0.0:
            candidate_brackets.append((left, right))

    # A grid point that is already an exact hit also changes sign against a
    # neighbour, which is the same root seen twice. Drop those brackets before
    # counting so that one exact hit plus one genuinely separate bracket is
    # still reported as multiple roots instead of silently taking the hit.
    exact_pressures = {item.pressure_pa for item in exact}
    distinct_brackets = [
        (left, right)
        for left, right in candidate_brackets
        if left.pressure_pa not in exact_pressures
        and right.pressure_pa not in exact_pressures
    ]
    if len(exact) + len(distinct_brackets) > 1:
        reason = "Multiple apparent saturation-pressure roots were observed."
        diagnostics.append(_failure_diagnostic("MULTIPLE_SATURATION_ROOTS", reason))
        return _empty_result(
            saturation_kind,
            SaturationStatus.INCONCLUSIVE,
            mixture,
            temperature_k,
            estimate,
            (minimum_pressure_pa, maximum_pressure_pa),
            provenance,
            evaluations,
            diagnostics,
            reason,
        )

    solver_iterations = 0
    solver_calls = 0
    if exact:
        final_evaluation = exact[0]
        bracket_pressures = (
            final_evaluation.pressure_pa,
            final_evaluation.pressure_pa,
        )
        bracket_values = (
            final_evaluation.objective or 0.0,
            final_evaluation.objective or 0.0,
        )
    elif distinct_brackets:
        left, right = distinct_brackets[0]
        if left.objective is None or right.objective is None:
            raise ValueError("bracket objectives must be present.")
        bracket_pressures = (left.pressure_pa, right.pressure_pa)
        bracket_values = (left.objective, right.objective)

        class InnerEvaluationFailure(Exception):
            pass

        def objective(log_pressure: float) -> float:
            evaluation = evaluate_log_pressure(log_pressure)
            if not evaluation.converged or evaluation.objective is None:
                raise InnerEvaluationFailure(
                    evaluation.failure_reason or "inner saturation solve failed."
                )
            return evaluation.objective

        try:
            root_log_pressure, solver = brentq(
                objective,
                log(left.pressure_pa),
                log(right.pressure_pa),
                xtol=1e-12,
                rtol=4.0 * float_info.epsilon,
                maxiter=maximum_outer_iterations,
                full_output=True,
                disp=False,
            )
        except (InnerEvaluationFailure, RuntimeError, ValueError) as error:
            reason = f"Bracketed saturation-pressure solve failed: {error}"
            diagnostics.append(_failure_diagnostic("SATURATION_SOLVER_FAILURE", reason))
            return _empty_result(
                saturation_kind,
                SaturationStatus.INCONCLUSIVE,
                mixture,
                temperature_k,
                estimate,
                (minimum_pressure_pa, maximum_pressure_pa),
                provenance,
                evaluations,
                diagnostics,
                reason,
            )
        if not solver.converged:
            reason = (
                "Bracketed saturation-pressure solve reached its iteration "
                "limit without convergence."
            )
            diagnostics.append(
                _failure_diagnostic("SATURATION_SOLVER_NON_CONVERGENCE", reason)
            )
            return _empty_result(
                saturation_kind,
                SaturationStatus.INCONCLUSIVE,
                mixture,
                temperature_k,
                estimate,
                (minimum_pressure_pa, maximum_pressure_pa),
                provenance,
                evaluations,
                diagnostics,
                reason,
            )
        solver_iterations = solver.iterations
        solver_calls = solver.function_calls
        final_evaluation = evaluate_log_pressure(root_log_pressure)
    else:
        reason = "No trustworthy saturation-pressure bracket was found."
        diagnostics.append(_failure_diagnostic("SATURATION_BRACKET_NOT_FOUND", reason))
        return _empty_result(
            saturation_kind,
            SaturationStatus.NOT_FOUND,
            mixture,
            temperature_k,
            estimate,
            (minimum_pressure_pa, maximum_pressure_pa),
            provenance,
            evaluations,
            diagnostics,
            reason,
        )

    if (
        not final_evaluation.converged
        or final_evaluation.objective is None
        or final_evaluation.parent_phase is None
        or final_evaluation.incipient_phase is None
        or final_evaluation.maximum_log_k_residual is None
        or final_evaluation.composition_change is None
        or final_evaluation.incipient_sum_residual is None
    ):
        reason = "Final saturation state reconstruction was inconclusive."
        diagnostics.append(
            _failure_diagnostic("SATURATION_FINAL_RECONSTRUCTION", reason)
        )
        return _empty_result(
            saturation_kind,
            SaturationStatus.INCONCLUSIVE,
            mixture,
            temperature_k,
            estimate,
            (minimum_pressure_pa, maximum_pressure_pa),
            provenance,
            evaluations,
            diagnostics,
            reason,
        )
    maximum_fugacity_residual = max(
        (
            abs(value)
            for value in final_evaluation.fugacity_equilibrium_residuals
            if value is not None
        ),
        default=0.0,
    )
    final_converged = (
        abs(final_evaluation.objective) <= SATURATION_OBJECTIVE_TOLERANCE
        and final_evaluation.maximum_log_k_residual <= INNER_LOG_K_TOLERANCE
        and final_evaluation.composition_change <= INNER_COMPOSITION_TOLERANCE
        and abs(final_evaluation.incipient_sum_residual) <= INCIPIENT_SUM_TOLERANCE
        and maximum_fugacity_residual <= FUGACITY_EQUILIBRIUM_TOLERANCE
        and final_evaluation.parent_phase.mechanical_classification
        is MechanicalStabilityClassification.STABLE
        and final_evaluation.incipient_phase.mechanical_classification
        is MechanicalStabilityClassification.STABLE
        and isfinite(final_evaluation.pressure_pa)
        and final_evaluation.pressure_pa > 0.0
    )
    if not final_converged:
        reason = "Final saturation state did not satisfy every convergence gate."
        diagnostics.append(_failure_diagnostic("SATURATION_FINAL_GATES", reason))
        return _empty_result(
            saturation_kind,
            SaturationStatus.INCONCLUSIVE,
            mixture,
            temperature_k,
            estimate,
            (minimum_pressure_pa, maximum_pressure_pa),
            provenance,
            evaluations,
            diagnostics,
            reason,
        )
    return SaturationPressureResult(
        saturation_kind=saturation_kind,
        status=SaturationStatus.CONVERGED,
        feed_mixture=mixture,
        feed_composition=_feed_composition(mixture),
        temperature_k=temperature_k,
        pressure_pa=final_evaluation.pressure_pa,
        initial_pressure_estimate_pa=estimate,
        pressure_bounds_pa=(minimum_pressure_pa, maximum_pressure_pa),
        bracket_pressures_pa=bracket_pressures,
        bracket_objective_values=bracket_values,
        parent_composition=final_evaluation.parent_composition,
        incipient_composition=final_evaluation.incipient_composition,
        k_values=final_evaluation.k_values,
        parent_phase=final_evaluation.parent_phase,
        incipient_phase=final_evaluation.incipient_phase,
        fugacity_equilibrium_residuals=(
            final_evaluation.fugacity_equilibrium_residuals
        ),
        maximum_fugacity_equilibrium_residual=maximum_fugacity_residual,
        composition_sum_residual=final_evaluation.incipient_sum_residual,
        pressure_residual=final_evaluation.objective,
        pressure_solver_iterations=solver_iterations,
        pressure_solver_function_calls=solver_calls,
        evaluation_history=tuple(evaluations),
        convergence_status=SaturationStatus.CONVERGED,
        failure_reason=None,
        diagnostics=tuple(diagnostics),
        binary_interaction_policy=provenance.binary_interaction_policy,
        binary_interactions=provenance.binary_interactions,
        supplied_binary_interaction_pairs=(
            provenance.supplied_binary_interaction_pairs
        ),
        defaulted_binary_interaction_pairs=(
            provenance.defaulted_binary_interaction_pairs
        ),
    )
