"""Fixed-temperature Peng–Robinson bubble- and dew-pressure calculations."""

from dataclasses import dataclass
from enum import StrEnum
from math import exp, expm1, fsum, isclose, isfinite, log
from sys import float_info
from typing import Final

from scipy.optimize import brentq  # type: ignore[import-untyped]

from pvt_phase_simulator._validation import require_finite as _require_finite
from pvt_phase_simulator._validation import require_positive as _require_positive
from pvt_phase_simulator.eos.diagnostics import (
    DiagnosticCategory,
    DiagnosticSeverity,
    EOSDiagnostic,
)
from pvt_phase_simulator.eos.flash import (
    FlashIteratePattern,
    FlashPhaseResult,
    PhaseInteractionProvenance,
    calculate_damped_log_k_values,
    detect_flash_iterate_pattern,
    evaluate_flash_phase,
    k_values_from_log_values,
)
from pvt_phase_simulator.eos.mixing_rules import (
    BinaryInteractionMapping,
    BinaryInteractionPolicy,
    CanonicalBinaryInteractionPairs,
    CanonicalBinaryInteractions,
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


@dataclass(frozen=True, slots=True)
class WilsonPressureEstimates:
    """Finite positive Wilson pressure estimates in Pa."""

    component_pressure_factors_pa: tuple[float, ...]
    bubble_pressure_pa: float
    dew_pressure_pa: float


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
            updated_log_k = calculate_damped_log_k_values(
                log_k_values,
                target_log_k,
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
