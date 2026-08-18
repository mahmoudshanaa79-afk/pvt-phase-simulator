"""Stability-gated isothermal-isobaric Peng–Robinson two-phase flash."""

from dataclasses import dataclass
from enum import StrEnum
from math import exp, fsum, isclose, isfinite, log
from sys import float_info
from typing import Final

from scipy.optimize import brentq  # type: ignore[import-untyped]

from pvt_phase_simulator._validation import require_finite as _require_finite
from pvt_phase_simulator._validation import require_positive as _require_positive
from pvt_phase_simulator.eos.diagnostics import (
    DiagnosticCategory,
    DiagnosticSeverity,
    EOSDiagnostic,
    evaluate_mixture_eos_diagnostics,
)
from pvt_phase_simulator.eos.mixing_rules import (
    BinaryInteractionMapping,
    BinaryInteractionPolicy,
    CanonicalBinaryInteractionPairs,
    CanonicalBinaryInteractions,
    calculate_peng_robinson_mixture_parameters,
)
from pvt_phase_simulator.eos.mixture_fugacity import (
    calculate_mixture_fugacity_coefficients,
)
from pvt_phase_simulator.eos.peng_robinson import (
    MechanicalStabilityClassification,
)
from pvt_phase_simulator.eos.phase_stability import (
    DEFAULT_MAXIMUM_ITERATIONS as DEFAULT_STABILITY_MAXIMUM_ITERATIONS,
)
from pvt_phase_simulator.eos.phase_stability import (
    MixturePhaseStabilityResult,
    PhaseRootSelection,
    PhaseStabilityStatus,
    PhaseTrialKind,
    analyze_mixture_phase_stability,
    detect_phase_root_switch,
    select_phase_trial_root,
)
from pvt_phase_simulator.fluid_models import (
    MOLE_FRACTION_TOLERANCE,
    FluidMixture,
    MixtureComponent,
)

RACHFORD_RICE_ENDPOINT_TOLERANCE: Final = 1e-12
RACHFORD_RICE_RESIDUAL_TOLERANCE: Final = 1e-12
LOG_K_DEGENERACY_TOLERANCE: Final = 1e-12
COMPOSITION_SUM_TOLERANCE: Final = 1e-10
COMPOSITION_NORMALIZATION_TRIGGER: Final = 64.0 * float_info.epsilon
MATERIAL_BALANCE_TOLERANCE: Final = 1e-10
FUGACITY_EQUILIBRIUM_TOLERANCE: Final = 1e-8
LOG_K_UPDATE_TOLERANCE: Final = 1e-8
ITERATE_REPEAT_TOLERANCE: Final = 1e-12
DEFAULT_MAXIMUM_FLASH_ITERATIONS: Final = 100
ACCELERATION_MAXIMUM_STEP_FACTOR: Final = 2.0
ACCELERATION_MINIMUM_PREDICTED_RESIDUAL_REDUCTION: Final = 0.20
ACCELERATION_RESIDUAL_WORSENING_FACTOR: Final = 1.05
ACCELERATION_SECANT_DENOMINATOR_FACTOR: Final = 64.0 * float_info.epsilon
_LOG_FLOAT_MAX: Final = log(float_info.max)
_LOG_FLOAT_MIN: Final = log(float_info.min)


class FlashPhaseState(StrEnum):
    """Thermodynamic state reported by the stability-gated flash workflow."""

    SINGLE_PHASE = "single_phase"
    TWO_PHASE = "two_phase"
    INCONCLUSIVE = "inconclusive"


class RachfordRiceStatus(StrEnum):
    """Classification of the physical Rachford–Rice interval."""

    TWO_PHASE_ROOT = "two_phase_root"
    ALL_LIQUID = "all_liquid"
    ALL_VAPOR = "all_vapor"
    DEGENERATE = "degenerate"
    INCONCLUSIVE = "inconclusive"


class FlashConvergenceStatus(StrEnum):
    """Numerical status of the two-phase iteration."""

    CONVERGED = "converged"
    NOT_CONVERGED = "not_converged"
    FAILED = "failed"
    NOT_ATTEMPTED = "not_attempted"


class FlashIteratePattern(StrEnum):
    """Repeat pattern observed in an unconverged log-K update."""

    NORMAL = "normal"
    STAGNATION = "stagnation"
    OSCILLATION = "oscillation"


class SuccessiveSubstitutionAccelerationStatus(StrEnum):
    """Disposition of one optional vector-secant acceleration proposal."""

    DISABLED = "disabled"
    INSUFFICIENT_HISTORY = "insufficient_history"
    ACCEPTED = "accepted"
    REJECTED_NONFINITE_HISTORY = "rejected_nonfinite_history"
    REJECTED_RESIDUAL_WORSENING = "rejected_residual_worsening"
    REJECTED_DEGENERATE_SECANT = "rejected_degenerate_secant"
    REJECTED_EXTRAPOLATION_DIRECTION = "rejected_extrapolation_direction"
    REJECTED_PREDICTED_RESIDUAL = "rejected_predicted_residual"
    REJECTED_STEP_LIMIT = "rejected_step_limit"
    REJECTED_NONFINITE_PROPOSAL = "rejected_nonfinite_proposal"


@dataclass(frozen=True, slots=True)
class RachfordRiceResult:
    """Immutable bracketed Rachford–Rice result and endpoint evidence."""

    status: RachfordRiceStatus
    beta: float | None
    lower_bound: float
    upper_bound: float
    function_at_lower_bound: float
    function_at_upper_bound: float
    residual: float | None
    iterations: int
    function_calls: int
    converged: bool
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class PhaseCompositionResult:
    """Immutable phase compositions and material-balance verification."""

    beta: float
    denominators: tuple[float, ...]
    liquid_composition: tuple[float, ...]
    vapor_composition: tuple[float, ...]
    raw_liquid_sum: float
    raw_vapor_sum: float
    liquid_sum_residual: float
    vapor_sum_residual: float
    material_balance_residuals: tuple[float, ...]
    maximum_material_balance_residual: float
    liquid_renormalized: bool
    vapor_renormalized: bool


@dataclass(frozen=True, slots=True)
class FlashPhaseResult:
    """Immutable EOS and fugacity state for one flash phase."""

    trial_kind: PhaseTrialKind
    composition: tuple[float, ...]
    root_selection: PhaseRootSelection
    selected_compressibility_factor: float
    mechanical_classification: MechanicalStabilityClassification
    component_log_fugacity_coefficients: tuple[float, ...]
    component_fugacity_coefficients: tuple[float, ...]
    component_fugacities_pa: tuple[float, ...]
    diagnostics: tuple[EOSDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class PhaseInteractionProvenance:
    """Immutable interaction assumptions required by a phase evaluation."""

    binary_interaction_policy: BinaryInteractionPolicy
    binary_interactions: CanonicalBinaryInteractions
    supplied_binary_interaction_pairs: CanonicalBinaryInteractionPairs
    defaulted_binary_interaction_pairs: CanonicalBinaryInteractionPairs


@dataclass(frozen=True, slots=True)
class SafeguardedLogKAccelerationResult:
    """Immutable evidence for an accepted or rejected acceleration proposal."""

    target_log_k_values: tuple[float, ...]
    status: SuccessiveSubstitutionAccelerationStatus
    extrapolation_factor: float | None
    current_residual_norm: float
    previous_residual_norm: float | None
    predicted_residual_norm: float | None
    proposal_step_norm: float | None
    ordinary_step_norm: float


@dataclass(frozen=True, slots=True)
class FlashIteration:
    """Immutable record of one successive-substitution flash iteration."""

    iteration: int
    log_k_values: tuple[float, ...]
    k_values: tuple[float, ...]
    rachford_rice: RachfordRiceResult
    beta: float
    beta_change: float | None
    phase_compositions: PhaseCompositionResult
    liquid_phase: FlashPhaseResult
    vapor_phase: FlashPhaseResult
    acceleration: SafeguardedLogKAccelerationResult | None
    updated_log_k_values: tuple[float, ...]
    log_k_residuals: tuple[float, ...]
    maximum_log_k_residual: float
    fugacity_equilibrium_residuals: tuple[float | None, ...]
    maximum_fugacity_equilibrium_residual: float
    composition_change: float | None
    diagnostics: tuple[EOSDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class TwoPhaseFlashResult:
    """Immutable stability-gated flash result with optional phase fields."""

    phase_state: FlashPhaseState
    convergence_status: FlashConvergenceStatus
    feed_mixture: FluidMixture
    temperature_k: float
    pressure_pa: float
    phase_stability: MixturePhaseStabilityResult
    initial_k_values: tuple[float, ...]
    final_k_values: tuple[float, ...] | None
    vapor_fraction: float | None
    liquid_fraction: float | None
    liquid_phase: FlashPhaseResult | None
    vapor_phase: FlashPhaseResult | None
    equilibrium_residuals: tuple[float | None, ...]
    material_balance_residuals: tuple[float, ...]
    iteration_history: tuple[FlashIteration, ...]
    failure_reason: str | None
    diagnostics: tuple[EOSDiagnostic, ...]
    single_phase_root: float | None
    single_phase_mechanical_classification: MechanicalStabilityClassification | None
    single_phase_log_fugacity_coefficients: tuple[float, ...]
    binary_interaction_policy: BinaryInteractionPolicy
    binary_interactions: CanonicalBinaryInteractions
    supplied_binary_interaction_pairs: CanonicalBinaryInteractionPairs
    defaulted_binary_interaction_pairs: CanonicalBinaryInteractionPairs


def _require_composition(composition: tuple[float, ...], name: str) -> None:
    if not isinstance(composition, tuple) or not composition:
        raise ValueError(f"{name} must be a non-empty immutable tuple.")
    for index, fraction in enumerate(composition):
        _require_finite(fraction, f"{name}[{index}]")
        if fraction < 0.0:
            raise ValueError(f"{name} values must be non-negative.")
    if not isclose(
        fsum(composition),
        1.0,
        rel_tol=0.0,
        abs_tol=MOLE_FRACTION_TOLERANCE,
    ):
        raise ValueError(f"{name} must sum to one within tolerance.")


def _require_k_values(
    composition: tuple[float, ...],
    k_values: tuple[float, ...],
) -> None:
    if not isinstance(k_values, tuple) or len(k_values) != len(composition):
        raise ValueError("k_values must be an aligned immutable tuple.")
    for index, value in enumerate(k_values):
        _require_positive(value, f"k_values[{index}]")


def _rachford_rice_denominator(beta: float, k_value: float) -> float:
    """Return ``1 + beta*(K - 1)`` without float64 cancellation.

    ``(1 - beta) + beta*K`` is algebraically identical but sums two
    non-negative terms for ``0 <= beta <= 1`` and ``K > 0``, so it is exact to
    within one rounding. The literal form loses the whole denominator when
    ``K`` is below the local spacing of one: at ``beta = 1`` it evaluates
    ``1 + (K - 1)`` as exactly zero for every ``K < 5.6e-17``, even though the
    true denominator is ``K > 0``. The transformed form returns ``K`` there.
    """

    return (1.0 - beta) + beta * k_value


def calculate_rachford_rice_value(
    beta: float,
    composition: tuple[float, ...],
    k_values: tuple[float, ...],
) -> float:
    """Return the dimensionless Rachford–Rice function at supplied beta."""

    _require_finite(beta, "beta")
    _require_composition(composition, "composition")
    _require_k_values(composition, k_values)
    terms: list[float] = []
    for index, (fraction, k_value) in enumerate(
        zip(composition, k_values, strict=True)
    ):
        denominator = _rachford_rice_denominator(beta, k_value)
        _require_finite(denominator, f"Rachford-Rice denominator[{index}]")
        if denominator <= 0.0:
            raise ValueError("Rachford-Rice denominators must be positive.")
        if fraction != 0.0:
            terms.append(fraction * (k_value - 1.0) / denominator)
    value = fsum(terms)
    _require_finite(value, "Rachford-Rice value")
    return value


def _physical_beta_bounds(k_values: tuple[float, ...]) -> tuple[float, float]:
    lower_bound = 0.0
    upper_bound = 1.0
    for k_value in k_values:
        if k_value > 1.0:
            lower_bound = max(lower_bound, -1.0 / (k_value - 1.0))
        elif k_value < 1.0:
            upper_bound = min(upper_bound, 1.0 / (1.0 - k_value))
    return lower_bound, upper_bound


def solve_rachford_rice(
    composition: tuple[float, ...],
    k_values: tuple[float, ...],
    endpoint_tolerance: float = RACHFORD_RICE_ENDPOINT_TOLERANCE,
) -> RachfordRiceResult:
    """Classify endpoints and solve a bracketed physical two-phase root."""

    _require_composition(composition, "composition")
    _require_k_values(composition, k_values)
    _require_positive(endpoint_tolerance, "endpoint_tolerance")
    lower_bound, upper_bound = _physical_beta_bounds(k_values)
    if not lower_bound < upper_bound:
        return RachfordRiceResult(
            RachfordRiceStatus.INCONCLUSIVE,
            None,
            lower_bound,
            upper_bound,
            float("nan"),
            float("nan"),
            None,
            0,
            0,
            False,
            "No denominator-safe physical beta interval is available.",
        )
    lower_value = calculate_rachford_rice_value(lower_bound, composition, k_values)
    upper_value = calculate_rachford_rice_value(upper_bound, composition, k_values)
    active_log_k = tuple(
        log(k_value)
        for fraction, k_value in zip(composition, k_values, strict=True)
        if fraction > 0.0
    )
    if max((abs(value) for value in active_log_k), default=0.0) <= (
        LOG_K_DEGENERACY_TOLERANCE
    ):
        return RachfordRiceResult(
            RachfordRiceStatus.DEGENERATE,
            None,
            lower_bound,
            upper_bound,
            lower_value,
            upper_value,
            None,
            0,
            2,
            False,
            "All active equilibrium ratios are numerically unity.",
        )
    if abs(lower_value) <= endpoint_tolerance or lower_value < 0.0:
        beta = lower_bound if abs(lower_value) <= endpoint_tolerance else None
        return RachfordRiceResult(
            RachfordRiceStatus.ALL_LIQUID,
            beta,
            lower_bound,
            upper_bound,
            lower_value,
            upper_value,
            lower_value if beta is not None else None,
            0,
            2,
            False,
            "No strict interior root; the endpoint tendency is all liquid.",
        )
    if abs(upper_value) <= endpoint_tolerance or upper_value > 0.0:
        beta = upper_bound if abs(upper_value) <= endpoint_tolerance else None
        return RachfordRiceResult(
            RachfordRiceStatus.ALL_VAPOR,
            beta,
            lower_bound,
            upper_bound,
            lower_value,
            upper_value,
            upper_value if beta is not None else None,
            0,
            2,
            False,
            "No strict interior root; the endpoint tendency is all vapor.",
        )
    if not lower_value > 0.0 or not upper_value < 0.0:
        return RachfordRiceResult(
            RachfordRiceStatus.INCONCLUSIVE,
            None,
            lower_bound,
            upper_bound,
            lower_value,
            upper_value,
            None,
            0,
            2,
            False,
            "Rachford-Rice endpoints do not bracket a classified root.",
        )
    try:
        beta, solver = brentq(
            lambda value: calculate_rachford_rice_value(value, composition, k_values),
            lower_bound,
            upper_bound,
            xtol=4.0 * float_info.epsilon,
            rtol=4.0 * float_info.epsilon,
            full_output=True,
            disp=False,
        )
    except (RuntimeError, ValueError) as error:
        return RachfordRiceResult(
            RachfordRiceStatus.INCONCLUSIVE,
            None,
            lower_bound,
            upper_bound,
            lower_value,
            upper_value,
            None,
            0,
            2,
            False,
            f"Bracketed Rachford-Rice solve failed: {error}",
        )
    residual = calculate_rachford_rice_value(beta, composition, k_values)
    if not 0.0 < beta < 1.0 or not solver.converged:
        return RachfordRiceResult(
            RachfordRiceStatus.INCONCLUSIVE,
            beta,
            lower_bound,
            upper_bound,
            lower_value,
            upper_value,
            residual,
            solver.iterations,
            solver.function_calls,
            False,
            "The bracketed solve did not produce a strict physical root.",
        )
    return RachfordRiceResult(
        RachfordRiceStatus.TWO_PHASE_ROOT,
        beta,
        lower_bound,
        upper_bound,
        lower_value,
        upper_value,
        residual,
        solver.iterations,
        solver.function_calls,
        True,
        None,
    )


def calculate_phase_compositions(
    composition: tuple[float, ...],
    k_values: tuple[float, ...],
    beta: float,
) -> PhaseCompositionResult:
    """Calculate normalized liquid/vapor compositions and verify balance."""

    _require_composition(composition, "composition")
    _require_k_values(composition, k_values)
    _require_finite(beta, "beta")
    if not 0.0 <= beta <= 1.0:
        raise ValueError("beta must lie in the physical closed interval [0, 1].")
    denominators: list[float] = []
    raw_liquid: list[float] = []
    raw_vapor: list[float] = []
    for index, (fraction, k_value) in enumerate(
        zip(composition, k_values, strict=True)
    ):
        denominator = _rachford_rice_denominator(beta, k_value)
        _require_finite(denominator, f"phase denominator[{index}]")
        if denominator <= 0.0:
            raise ValueError("phase-composition denominators must be positive.")
        liquid_fraction = fraction / denominator
        vapor_fraction = k_value * liquid_fraction
        _require_finite(liquid_fraction, f"liquid composition[{index}]")
        _require_finite(vapor_fraction, f"vapor composition[{index}]")
        denominators.append(denominator)
        raw_liquid.append(liquid_fraction)
        raw_vapor.append(vapor_fraction)
    raw_liquid_sum = fsum(raw_liquid)
    raw_vapor_sum = fsum(raw_vapor)
    liquid_raw_residual = raw_liquid_sum - 1.0
    vapor_raw_residual = raw_vapor_sum - 1.0
    if abs(liquid_raw_residual) > COMPOSITION_SUM_TOLERANCE:
        raise ValueError("raw liquid composition does not sum to one within tolerance.")
    if abs(vapor_raw_residual) > COMPOSITION_SUM_TOLERANCE:
        raise ValueError("raw vapor composition does not sum to one within tolerance.")
    liquid_renormalized = abs(liquid_raw_residual) > COMPOSITION_NORMALIZATION_TRIGGER
    vapor_renormalized = abs(vapor_raw_residual) > COMPOSITION_NORMALIZATION_TRIGGER
    liquid = tuple(
        value / raw_liquid_sum if liquid_renormalized else value for value in raw_liquid
    )
    vapor = tuple(
        value / raw_vapor_sum if vapor_renormalized else value for value in raw_vapor
    )
    liquid_sum_residual = fsum(liquid) - 1.0
    vapor_sum_residual = fsum(vapor) - 1.0
    material_residuals = tuple(
        feed_fraction - ((1.0 - beta) * liquid_fraction + beta * vapor_fraction)
        for feed_fraction, liquid_fraction, vapor_fraction in zip(
            composition, liquid, vapor, strict=True
        )
    )
    maximum_material_residual = max(
        (abs(value) for value in material_residuals), default=0.0
    )
    if maximum_material_residual > MATERIAL_BALANCE_TOLERANCE:
        raise ValueError("component material balance exceeds tolerance.")
    return PhaseCompositionResult(
        beta=beta,
        denominators=tuple(denominators),
        liquid_composition=liquid,
        vapor_composition=vapor,
        raw_liquid_sum=raw_liquid_sum,
        raw_vapor_sum=raw_vapor_sum,
        liquid_sum_residual=liquid_sum_residual,
        vapor_sum_residual=vapor_sum_residual,
        material_balance_residuals=material_residuals,
        maximum_material_balance_residual=maximum_material_residual,
        liquid_renormalized=liquid_renormalized,
        vapor_renormalized=vapor_renormalized,
    )


def _mixture_with_composition(
    feed_mixture: FluidMixture,
    composition: tuple[float, ...],
) -> FluidMixture:
    return FluidMixture(
        tuple(
            MixtureComponent(item.component, fraction)
            for item, fraction in zip(feed_mixture.components, composition, strict=True)
        )
    )


def _interaction_provenance_matches(
    parameters_policy: BinaryInteractionPolicy,
    parameters_interactions: CanonicalBinaryInteractions,
    parameters_supplied: CanonicalBinaryInteractionPairs,
    parameters_defaulted: CanonicalBinaryInteractionPairs,
    expected: PhaseInteractionProvenance,
) -> bool:
    return (
        parameters_policy is expected.binary_interaction_policy
        and parameters_interactions == expected.binary_interactions
        and parameters_supplied == expected.supplied_binary_interaction_pairs
        and parameters_defaulted == expected.defaulted_binary_interaction_pairs
    )


def phase_interaction_provenance_from_stability(
    stability: MixturePhaseStabilityResult,
) -> PhaseInteractionProvenance:
    """Extract the compact phase-evaluation provenance from Module 6 output."""

    return PhaseInteractionProvenance(
        binary_interaction_policy=stability.binary_interaction_policy,
        binary_interactions=stability.binary_interactions,
        supplied_binary_interaction_pairs=stability.supplied_binary_interaction_pairs,
        defaulted_binary_interaction_pairs=(
            stability.defaulted_binary_interaction_pairs
        ),
    )


def evaluate_flash_phase(
    feed_mixture: FluidMixture,
    composition: tuple[float, ...],
    temperature_k: float,
    pressure_pa: float,
    trial_kind: PhaseTrialKind,
    phase_stability: MixturePhaseStabilityResult | None = None,
    binary_interactions: BinaryInteractionMapping | None = None,
    binary_interaction_policy: BinaryInteractionPolicy = (
        BinaryInteractionPolicy.DEFAULT_ZERO
    ),
    *,
    interaction_provenance: PhaseInteractionProvenance | None = None,
) -> FlashPhaseResult:
    """Evaluate a phase using direct provenance or a legacy stability result.

    ``phase_stability`` remains accepted for Module 7 compatibility. New
    callers can provide the smaller ``interaction_provenance`` record instead.
    Supplying both or neither is rejected.
    """

    if (phase_stability is None) == (interaction_provenance is None):
        raise ValueError(
            "provide exactly one interaction provenance source: "
            "phase_stability or interaction_provenance."
        )
    expected_provenance = (
        phase_interaction_provenance_from_stability(phase_stability)
        if phase_stability is not None
        else interaction_provenance
    )
    if expected_provenance is None:
        raise ValueError("interaction provenance is required.")

    phase_mixture = _mixture_with_composition(feed_mixture, composition)
    parameters = calculate_peng_robinson_mixture_parameters(
        phase_mixture,
        temperature_k,
        pressure_pa,
        binary_interactions,
        binary_interaction_policy,
    )
    if not _interaction_provenance_matches(
        parameters.binary_interaction_policy,
        parameters.binary_interactions,
        parameters.supplied_binary_interaction_pairs,
        parameters.defaulted_binary_interaction_pairs,
        expected_provenance,
    ):
        raise ValueError(
            "flash phase binary-interaction provenance does not match stability."
        )
    selection = select_phase_trial_root(
        parameters.A_mix,
        parameters.B_mix,
        trial_kind,
    )
    if (
        selection.selected_compressibility_factor is None
        or selection.selected_classification
        is not MechanicalStabilityClassification.STABLE
    ):
        raise ValueError(
            selection.failure_reason
            or "No mechanically stable root is available for the flash phase."
        )
    fugacity_results = calculate_mixture_fugacity_coefficients(
        parameters,
        selection.selected_compressibility_factor,
    )
    log_phi = tuple(item.log_fugacity_coefficient for item in fugacity_results)
    phi = tuple(item.fugacity_coefficient for item in fugacity_results)
    fugacities = tuple(
        fraction * coefficient * pressure_pa
        for fraction, coefficient in zip(composition, phi, strict=True)
    )
    for index, value in enumerate(fugacities):
        _require_finite(value, f"component fugacity[{index}]")
        if value < 0.0:
            raise ValueError("component fugacities must be non-negative.")
        if composition[index] > 0.0 and value == 0.0:
            raise ValueError("active component fugacity underflowed to zero.")
    diagnostics = (
        *evaluate_mixture_eos_diagnostics(parameters),
        *selection.diagnostics,
    )
    return FlashPhaseResult(
        trial_kind=trial_kind,
        composition=composition,
        root_selection=selection,
        selected_compressibility_factor=(selection.selected_compressibility_factor),
        mechanical_classification=selection.selected_classification,
        component_log_fugacity_coefficients=log_phi,
        component_fugacity_coefficients=phi,
        component_fugacities_pa=fugacities,
        diagnostics=tuple(diagnostics),
    )


def k_values_from_log_values(log_k_values: tuple[float, ...]) -> tuple[float, ...]:
    """Exponentiate finite log K-values without clamping overflow/underflow."""

    if not isinstance(log_k_values, tuple) or not log_k_values:
        raise ValueError("log_k_values must be a non-empty immutable tuple.")
    values: list[float] = []
    for index, value in enumerate(log_k_values):
        _require_finite(value, f"log_k_values[{index}]")
        if value > _LOG_FLOAT_MAX or value < _LOG_FLOAT_MIN:
            raise ValueError("K-value exponentiation would overflow or underflow.")
        k_value = exp(value)
        _require_positive(k_value, f"K-value[{index}]")
        values.append(k_value)
    return tuple(values)


def calculate_damped_log_k_values(
    current_log_k_values: tuple[float, ...],
    target_log_k_values: tuple[float, ...],
    successive_substitution_damping_factor: float = 1.0,
) -> tuple[float, ...]:
    """Return one safeguarded successive-substitution update in log-K space.

    A factor of one returns the target tuple directly, preserving the exact
    historical undamped path without additional floating-point operations.
    """

    _require_finite(
        successive_substitution_damping_factor,
        "successive_substitution_damping_factor",
    )
    if not 0.0 < successive_substitution_damping_factor <= 1.0:
        raise ValueError(
            "successive_substitution_damping_factor must be greater than zero "
            "and at most one."
        )
    if (
        not isinstance(current_log_k_values, tuple)
        or not current_log_k_values
        or len(target_log_k_values) != len(current_log_k_values)
    ):
        raise ValueError(
            "current and target log K-values must be non-empty tuples of equal length."
        )
    for label, values in (
        ("current_log_k_values", current_log_k_values),
        ("target_log_k_values", target_log_k_values),
    ):
        for index, value in enumerate(values):
            _require_finite(value, f"{label}[{index}]")
    if successive_substitution_damping_factor == 1.0:
        return target_log_k_values
    damped = tuple(
        current + successive_substitution_damping_factor * (target - current)
        for current, target in zip(
            current_log_k_values, target_log_k_values, strict=True
        )
    )
    for index, value in enumerate(damped):
        _require_finite(value, f"damped_log_k_values[{index}]")
    return damped


def calculate_safeguarded_log_k_acceleration(
    current_log_k_values: tuple[float, ...],
    target_log_k_values: tuple[float, ...],
    previous_log_k_values: tuple[float, ...] | None,
    previous_target_log_k_values: tuple[float, ...] | None,
    successive_substitution_acceleration_enabled: bool = False,
) -> SafeguardedLogKAccelerationResult:
    """Return a safeguarded vector-secant target for a log-K fixed point.

    Let ``r_n = g(x_n) - x_n``, ``s_n = x_n - x_(n-1)``, and
    ``y_n = r_n - r_(n-1)``. The scalar secant model proposes
    ``x_acc = x_n + tau*s_n`` with
    ``tau = -dot(r_n, y_n) / dot(y_n, y_n)``. The proposal is accepted only
    when the actual residual improved since the prior iterate, the secant model
    predicts at least a 20% infinity-norm reduction, and the proposed movement
    is no more than twice the ordinary fixed-point movement. This is a
    derivative-free candidate; rejection returns the exact ordinary target.
    """

    ordinary_target = calculate_damped_log_k_values(
        current_log_k_values, target_log_k_values, 1.0
    )
    if not isinstance(successive_substitution_acceleration_enabled, bool):
        raise ValueError(
            "successive_substitution_acceleration_enabled must be a boolean."
        )
    current_residual = tuple(
        target - current
        for current, target in zip(
            current_log_k_values, target_log_k_values, strict=True
        )
    )
    current_norm = max((abs(value) for value in current_residual), default=0.0)

    def result(
        status: SuccessiveSubstitutionAccelerationStatus,
        *,
        extrapolation_factor: float | None = None,
        previous_residual_norm: float | None = None,
        predicted_residual_norm: float | None = None,
        proposal_step_norm: float | None = None,
        target: tuple[float, ...] = ordinary_target,
    ) -> SafeguardedLogKAccelerationResult:
        return SafeguardedLogKAccelerationResult(
            target_log_k_values=target,
            status=status,
            extrapolation_factor=extrapolation_factor,
            current_residual_norm=current_norm,
            previous_residual_norm=previous_residual_norm,
            predicted_residual_norm=predicted_residual_norm,
            proposal_step_norm=proposal_step_norm,
            ordinary_step_norm=current_norm,
        )

    if not successive_substitution_acceleration_enabled:
        return result(SuccessiveSubstitutionAccelerationStatus.DISABLED)
    if previous_log_k_values is None and previous_target_log_k_values is None:
        return result(SuccessiveSubstitutionAccelerationStatus.INSUFFICIENT_HISTORY)
    if previous_log_k_values is None or previous_target_log_k_values is None:
        raise ValueError("previous log K-values and targets must be supplied together.")
    if len(previous_log_k_values) != len(current_log_k_values) or len(
        previous_target_log_k_values
    ) != len(current_log_k_values):
        raise ValueError("previous log K-values and targets must remain aligned.")
    if not all(
        isfinite(value)
        for value in (*previous_log_k_values, *previous_target_log_k_values)
    ):
        return result(
            SuccessiveSubstitutionAccelerationStatus.REJECTED_NONFINITE_HISTORY
        )

    previous_residual = tuple(
        target - current
        for current, target in zip(
            previous_log_k_values,
            previous_target_log_k_values,
            strict=True,
        )
    )
    previous_norm = max((abs(value) for value in previous_residual), default=0.0)
    if current_norm > ACCELERATION_RESIDUAL_WORSENING_FACTOR * previous_norm:
        return result(
            SuccessiveSubstitutionAccelerationStatus.REJECTED_RESIDUAL_WORSENING,
            previous_residual_norm=previous_norm,
        )

    iterate_step = tuple(
        current - previous
        for current, previous in zip(
            current_log_k_values, previous_log_k_values, strict=True
        )
    )
    residual_change = tuple(
        current - previous
        for current, previous in zip(current_residual, previous_residual, strict=True)
    )
    denominator = fsum(value * value for value in residual_change)
    residual_scale = max(
        fsum(value * value for value in current_residual),
        fsum(value * value for value in previous_residual),
        float_info.min,
    )
    if denominator <= ACCELERATION_SECANT_DENOMINATOR_FACTOR * residual_scale:
        return result(
            SuccessiveSubstitutionAccelerationStatus.REJECTED_DEGENERATE_SECANT,
            previous_residual_norm=previous_norm,
        )
    extrapolation_factor = (
        -fsum(
            residual * change
            for residual, change in zip(current_residual, residual_change, strict=True)
        )
        / denominator
    )
    if not isfinite(extrapolation_factor) or extrapolation_factor <= 0.0:
        return result(
            SuccessiveSubstitutionAccelerationStatus.REJECTED_EXTRAPOLATION_DIRECTION,
            extrapolation_factor=extrapolation_factor,
            previous_residual_norm=previous_norm,
        )

    predicted_residual = tuple(
        residual + extrapolation_factor * change
        for residual, change in zip(current_residual, residual_change, strict=True)
    )
    predicted_norm = max((abs(value) for value in predicted_residual), default=0.0)
    if (
        not isfinite(predicted_norm)
        or predicted_norm
        > (1.0 - ACCELERATION_MINIMUM_PREDICTED_RESIDUAL_REDUCTION) * current_norm
    ):
        return result(
            SuccessiveSubstitutionAccelerationStatus.REJECTED_PREDICTED_RESIDUAL,
            extrapolation_factor=extrapolation_factor,
            previous_residual_norm=previous_norm,
            predicted_residual_norm=predicted_norm,
        )

    proposal = tuple(
        current + extrapolation_factor * step
        for current, step in zip(current_log_k_values, iterate_step, strict=True)
    )
    proposal_step_norm = max(
        (
            abs(proposed - current)
            for proposed, current in zip(proposal, current_log_k_values, strict=True)
        ),
        default=0.0,
    )
    if not all(isfinite(value) for value in proposal):
        return result(
            SuccessiveSubstitutionAccelerationStatus.REJECTED_NONFINITE_PROPOSAL,
            extrapolation_factor=extrapolation_factor,
            previous_residual_norm=previous_norm,
            predicted_residual_norm=predicted_norm,
            proposal_step_norm=proposal_step_norm,
        )
    if proposal_step_norm > ACCELERATION_MAXIMUM_STEP_FACTOR * current_norm:
        return result(
            SuccessiveSubstitutionAccelerationStatus.REJECTED_STEP_LIMIT,
            extrapolation_factor=extrapolation_factor,
            previous_residual_norm=previous_norm,
            predicted_residual_norm=predicted_norm,
            proposal_step_norm=proposal_step_norm,
        )
    return result(
        SuccessiveSubstitutionAccelerationStatus.ACCEPTED,
        extrapolation_factor=extrapolation_factor,
        previous_residual_norm=previous_norm,
        predicted_residual_norm=predicted_norm,
        proposal_step_norm=proposal_step_norm,
        target=proposal,
    )


def detect_flash_iterate_pattern(
    current_log_k_values: tuple[float, ...],
    updated_log_k_values: tuple[float, ...],
    two_steps_back_log_k_values: tuple[float, ...] | None,
    repeat_tolerance: float = ITERATE_REPEAT_TOLERANCE,
) -> FlashIteratePattern:
    """Classify exact-scale stagnation or a two-cycle in log K-values."""

    _require_positive(repeat_tolerance, "repeat_tolerance")
    if (
        not isinstance(current_log_k_values, tuple)
        or not current_log_k_values
        or len(updated_log_k_values) != len(current_log_k_values)
    ):
        raise ValueError("current and updated log K-values must be aligned tuples.")
    for index, value in enumerate((*current_log_k_values, *updated_log_k_values)):
        _require_finite(value, f"iterate log K-value[{index}]")
    if (
        max(
            abs(updated - current)
            for updated, current in zip(
                updated_log_k_values, current_log_k_values, strict=True
            )
        )
        <= repeat_tolerance
    ):
        return FlashIteratePattern.STAGNATION
    if two_steps_back_log_k_values is not None:
        if len(two_steps_back_log_k_values) != len(current_log_k_values):
            raise ValueError("two-steps-back log K-values must be aligned.")
        for index, value in enumerate(two_steps_back_log_k_values):
            _require_finite(value, f"two-steps-back log K-value[{index}]")
        if (
            max(
                abs(updated - previous)
                for updated, previous in zip(
                    updated_log_k_values,
                    two_steps_back_log_k_values,
                    strict=True,
                )
            )
            <= repeat_tolerance
        ):
            return FlashIteratePattern.OSCILLATION
    return FlashIteratePattern.NORMAL


def flash_iteration_satisfies_convergence(iteration: FlashIteration) -> bool:
    """Require every documented numerical and mechanical convergence gate."""

    rr_residual = iteration.rachford_rice.residual
    phase_compositions = iteration.phase_compositions
    return (
        iteration.rachford_rice.status is RachfordRiceStatus.TWO_PHASE_ROOT
        and iteration.rachford_rice.converged
        and rr_residual is not None
        and abs(rr_residual) <= RACHFORD_RICE_RESIDUAL_TOLERANCE
        and iteration.maximum_log_k_residual <= LOG_K_UPDATE_TOLERANCE
        and iteration.maximum_fugacity_equilibrium_residual
        <= FUGACITY_EQUILIBRIUM_TOLERANCE
        and abs(phase_compositions.liquid_sum_residual) <= COMPOSITION_SUM_TOLERANCE
        and abs(phase_compositions.vapor_sum_residual) <= COMPOSITION_SUM_TOLERANCE
        and phase_compositions.maximum_material_balance_residual
        <= MATERIAL_BALANCE_TOLERANCE
        and 0.0 < iteration.beta < 1.0
        and iteration.liquid_phase.mechanical_classification
        is MechanicalStabilityClassification.STABLE
        and iteration.vapor_phase.mechanical_classification
        is MechanicalStabilityClassification.STABLE
    )


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
        value=None,
    )


def _base_result(
    phase_state: FlashPhaseState,
    convergence_status: FlashConvergenceStatus,
    mixture: FluidMixture,
    temperature_k: float,
    pressure_pa: float,
    stability: MixturePhaseStabilityResult,
    initial_k_values: tuple[float, ...],
    failure_reason: str | None,
    diagnostics: tuple[EOSDiagnostic, ...],
) -> TwoPhaseFlashResult:
    feed_reference = stability.feed_reference
    return TwoPhaseFlashResult(
        phase_state=phase_state,
        convergence_status=convergence_status,
        feed_mixture=mixture,
        temperature_k=temperature_k,
        pressure_pa=pressure_pa,
        phase_stability=stability,
        initial_k_values=initial_k_values,
        final_k_values=None,
        vapor_fraction=None,
        liquid_fraction=None,
        liquid_phase=None,
        vapor_phase=None,
        equilibrium_residuals=(),
        material_balance_residuals=(),
        iteration_history=(),
        failure_reason=failure_reason,
        diagnostics=diagnostics,
        single_phase_root=feed_reference.selected_compressibility_factor,
        single_phase_mechanical_classification=(
            feed_reference.selected_mechanical_classification
        ),
        single_phase_log_fugacity_coefficients=(
            feed_reference.component_log_fugacity_coefficients
        ),
        binary_interaction_policy=stability.binary_interaction_policy,
        binary_interactions=stability.binary_interactions,
        supplied_binary_interaction_pairs=stability.supplied_binary_interaction_pairs,
        defaulted_binary_interaction_pairs=(
            stability.defaulted_binary_interaction_pairs
        ),
    )


def _failed_flash_result(
    mixture: FluidMixture,
    temperature_k: float,
    pressure_pa: float,
    stability: MixturePhaseStabilityResult,
    initial_k_values: tuple[float, ...],
    history: list[FlashIteration],
    diagnostics: list[EOSDiagnostic],
    failure_reason: str,
    convergence_status: FlashConvergenceStatus = FlashConvergenceStatus.FAILED,
) -> TwoPhaseFlashResult:
    last = history[-1] if history else None
    return TwoPhaseFlashResult(
        phase_state=FlashPhaseState.INCONCLUSIVE,
        convergence_status=convergence_status,
        feed_mixture=mixture,
        temperature_k=temperature_k,
        pressure_pa=pressure_pa,
        phase_stability=stability,
        initial_k_values=initial_k_values,
        final_k_values=(last.k_values if last is not None else None),
        vapor_fraction=(last.beta if last is not None else None),
        liquid_fraction=(1.0 - last.beta if last is not None else None),
        liquid_phase=(last.liquid_phase if last is not None else None),
        vapor_phase=(last.vapor_phase if last is not None else None),
        equilibrium_residuals=(
            last.fugacity_equilibrium_residuals if last is not None else ()
        ),
        material_balance_residuals=(
            last.phase_compositions.material_balance_residuals
            if last is not None
            else ()
        ),
        iteration_history=tuple(history),
        failure_reason=failure_reason,
        diagnostics=tuple(diagnostics),
        single_phase_root=None,
        single_phase_mechanical_classification=None,
        single_phase_log_fugacity_coefficients=(),
        binary_interaction_policy=stability.binary_interaction_policy,
        binary_interactions=stability.binary_interactions,
        supplied_binary_interaction_pairs=stability.supplied_binary_interaction_pairs,
        defaulted_binary_interaction_pairs=(
            stability.defaulted_binary_interaction_pairs
        ),
    )


def calculate_two_phase_flash(
    mixture: FluidMixture,
    temperature_k: float,
    pressure_pa: float,
    binary_interactions: BinaryInteractionMapping | None = None,
    binary_interaction_policy: BinaryInteractionPolicy = (
        BinaryInteractionPolicy.DEFAULT_ZERO
    ),
    maximum_iterations: int = DEFAULT_MAXIMUM_FLASH_ITERATIONS,
    stability_maximum_iterations: int = DEFAULT_STABILITY_MAXIMUM_ITERATIONS,
    *,
    successive_substitution_damping_factor: float = 1.0,
    successive_substitution_acceleration_enabled: bool = False,
) -> TwoPhaseFlashResult:
    """Run a stability-gated successive-substitution two-phase flash."""

    _require_positive(temperature_k, "temperature_k")
    _require_positive(pressure_pa, "pressure_pa")
    if not isinstance(maximum_iterations, int) or maximum_iterations <= 0:
        raise ValueError("maximum_iterations must be a positive integer.")
    if (
        not isinstance(stability_maximum_iterations, int)
        or stability_maximum_iterations <= 0
    ):
        raise ValueError("stability_maximum_iterations must be a positive integer.")
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
    interaction_snapshot = (
        None if binary_interactions is None else dict(binary_interactions)
    )
    stability = analyze_mixture_phase_stability(
        mixture,
        temperature_k,
        pressure_pa,
        interaction_snapshot,
        binary_interaction_policy,
        stability_maximum_iterations,
    )
    initial_k_values = tuple(item.k_value for item in stability.wilson_k_values)
    stability_diagnostics = tuple(stability.feed_reference.diagnostics)
    if stability.status is PhaseStabilityStatus.STABLE:
        return _base_result(
            FlashPhaseState.SINGLE_PHASE,
            FlashConvergenceStatus.NOT_ATTEMPTED,
            mixture,
            temperature_k,
            pressure_pa,
            stability,
            initial_k_values,
            "Phase stability is conclusive; no two-phase split was attempted.",
            stability_diagnostics,
        )
    if stability.status is PhaseStabilityStatus.INCONCLUSIVE:
        return _base_result(
            FlashPhaseState.INCONCLUSIVE,
            FlashConvergenceStatus.NOT_ATTEMPTED,
            mixture,
            temperature_k,
            pressure_pa,
            stability,
            initial_k_values,
            "Phase stability is inconclusive; a flash was not attempted.",
            stability_diagnostics,
        )

    feed_composition = tuple(item.mole_fraction for item in mixture.components)
    log_k_values = tuple(log(value) for value in initial_k_values)
    history: list[FlashIteration] = []
    diagnostics: list[EOSDiagnostic] = list(stability_diagnostics)
    previous_beta: float | None = None
    previous_liquid: tuple[float, ...] | None = None
    previous_vapor: tuple[float, ...] | None = None
    previous_liquid_root: PhaseRootSelection | None = None
    previous_vapor_root: PhaseRootSelection | None = None
    prior_log_k_values: list[tuple[float, ...]] = []
    previous_target_log_k_values: tuple[float, ...] | None = None

    for iteration_number in range(1, maximum_iterations + 1):
        try:
            k_values = k_values_from_log_values(log_k_values)
            rr_result = solve_rachford_rice(feed_composition, k_values)
        except ValueError as error:
            reason = f"Rachford-Rice evaluation failed: {error}"
            diagnostics.append(_failure_diagnostic("FLASH_RR_FAILURE", reason))
            return _failed_flash_result(
                mixture,
                temperature_k,
                pressure_pa,
                stability,
                initial_k_values,
                history,
                diagnostics,
                reason,
            )
        if (
            rr_result.status is not RachfordRiceStatus.TWO_PHASE_ROOT
            or rr_result.beta is None
            or rr_result.residual is None
        ):
            reason = (
                "Unstable feed did not produce a physical two-phase "
                f"Rachford-Rice root: {rr_result.status.value}."
            )
            diagnostics.append(_failure_diagnostic("FLASH_NO_RR_ROOT", reason))
            return _failed_flash_result(
                mixture,
                temperature_k,
                pressure_pa,
                stability,
                initial_k_values,
                history,
                diagnostics,
                reason,
            )
        beta = rr_result.beta
        try:
            phase_compositions = calculate_phase_compositions(
                feed_composition,
                k_values,
                beta,
            )
            liquid_phase = evaluate_flash_phase(
                mixture,
                phase_compositions.liquid_composition,
                temperature_k,
                pressure_pa,
                PhaseTrialKind.LIQUID_LIKE,
                stability,
                interaction_snapshot,
                binary_interaction_policy,
            )
            vapor_phase = evaluate_flash_phase(
                mixture,
                phase_compositions.vapor_composition,
                temperature_k,
                pressure_pa,
                PhaseTrialKind.VAPOR_LIKE,
                stability,
                interaction_snapshot,
                binary_interaction_policy,
            )
        except ValueError as error:
            reason = f"Flash phase evaluation failed: {error}"
            diagnostics.append(_failure_diagnostic("FLASH_PHASE_FAILURE", reason))
            return _failed_flash_result(
                mixture,
                temperature_k,
                pressure_pa,
                stability,
                initial_k_values,
                history,
                diagnostics,
                reason,
            )

        iteration_diagnostics = (
            *liquid_phase.diagnostics,
            *vapor_phase.diagnostics,
        )
        _append_unique_diagnostics(diagnostics, tuple(iteration_diagnostics))
        if previous_liquid_root is not None:
            liquid_switch = detect_phase_root_switch(
                previous_liquid_root,
                liquid_phase.root_selection,
            )
            if liquid_switch is not None:
                _append_unique_diagnostics(diagnostics, (liquid_switch,))
        if previous_vapor_root is not None:
            vapor_switch = detect_phase_root_switch(
                previous_vapor_root,
                vapor_phase.root_selection,
            )
            if vapor_switch is not None:
                _append_unique_diagnostics(diagnostics, (vapor_switch,))

        target_log_k_values = tuple(
            liquid_log_phi - vapor_log_phi
            for liquid_log_phi, vapor_log_phi in zip(
                liquid_phase.component_log_fugacity_coefficients,
                vapor_phase.component_log_fugacity_coefficients,
                strict=True,
            )
        )
        for index, value in enumerate(target_log_k_values):
            _require_finite(value, f"target_log_k_values[{index}]")
        acceleration = (
            calculate_safeguarded_log_k_acceleration(
                log_k_values,
                target_log_k_values,
                prior_log_k_values[-1] if prior_log_k_values else None,
                previous_target_log_k_values,
                True,
            )
            if successive_substitution_acceleration_enabled
            else None
        )
        update_target_log_k_values = (
            target_log_k_values
            if acceleration is None
            else acceleration.target_log_k_values
        )
        updated_log_k_values = calculate_damped_log_k_values(
            log_k_values,
            update_target_log_k_values,
            successive_substitution_damping_factor,
        )
        log_k_residuals = tuple(
            current - target
            for current, target in zip(log_k_values, target_log_k_values, strict=True)
        )
        maximum_log_k_residual = max(
            (abs(value) for value in log_k_residuals), default=0.0
        )
        equilibrium_residuals: list[float | None] = []
        for feed_fraction, liquid_fugacity, vapor_fugacity in zip(
            feed_composition,
            liquid_phase.component_fugacities_pa,
            vapor_phase.component_fugacities_pa,
            strict=True,
        ):
            if feed_fraction == 0.0:
                equilibrium_residuals.append(None)
                continue
            _require_positive(liquid_fugacity, "active liquid fugacity")
            _require_positive(vapor_fugacity, "active vapor fugacity")
            equilibrium_residuals.append(log(vapor_fugacity) - log(liquid_fugacity))
        maximum_equilibrium_residual = max(
            (abs(value) for value in equilibrium_residuals if value is not None),
            default=0.0,
        )
        beta_change = None if previous_beta is None else abs(beta - previous_beta)
        composition_change = (
            None
            if previous_liquid is None or previous_vapor is None
            else max(
                *(
                    abs(current - previous)
                    for current, previous in zip(
                        phase_compositions.liquid_composition,
                        previous_liquid,
                        strict=True,
                    )
                ),
                *(
                    abs(current - previous)
                    for current, previous in zip(
                        phase_compositions.vapor_composition,
                        previous_vapor,
                        strict=True,
                    )
                ),
            )
        )
        iteration = FlashIteration(
            iteration=iteration_number,
            log_k_values=log_k_values,
            k_values=k_values,
            rachford_rice=rr_result,
            beta=beta,
            beta_change=beta_change,
            phase_compositions=phase_compositions,
            liquid_phase=liquid_phase,
            vapor_phase=vapor_phase,
            acceleration=acceleration,
            updated_log_k_values=updated_log_k_values,
            log_k_residuals=log_k_residuals,
            maximum_log_k_residual=maximum_log_k_residual,
            fugacity_equilibrium_residuals=tuple(equilibrium_residuals),
            maximum_fugacity_equilibrium_residual=(maximum_equilibrium_residual),
            composition_change=composition_change,
            diagnostics=tuple(diagnostics),
        )
        history.append(iteration)

        converged = flash_iteration_satisfies_convergence(iteration)
        if converged:
            return TwoPhaseFlashResult(
                phase_state=FlashPhaseState.TWO_PHASE,
                convergence_status=FlashConvergenceStatus.CONVERGED,
                feed_mixture=mixture,
                temperature_k=temperature_k,
                pressure_pa=pressure_pa,
                phase_stability=stability,
                initial_k_values=initial_k_values,
                final_k_values=k_values,
                vapor_fraction=beta,
                liquid_fraction=1.0 - beta,
                liquid_phase=liquid_phase,
                vapor_phase=vapor_phase,
                equilibrium_residuals=tuple(equilibrium_residuals),
                material_balance_residuals=(
                    phase_compositions.material_balance_residuals
                ),
                iteration_history=tuple(history),
                failure_reason=None,
                diagnostics=tuple(diagnostics),
                single_phase_root=None,
                single_phase_mechanical_classification=None,
                single_phase_log_fugacity_coefficients=(),
                binary_interaction_policy=stability.binary_interaction_policy,
                binary_interactions=stability.binary_interactions,
                supplied_binary_interaction_pairs=(
                    stability.supplied_binary_interaction_pairs
                ),
                defaulted_binary_interaction_pairs=(
                    stability.defaulted_binary_interaction_pairs
                ),
            )

        pattern = detect_flash_iterate_pattern(
            log_k_values,
            updated_log_k_values,
            prior_log_k_values[-1] if prior_log_k_values else None,
        )
        if (
            pattern is FlashIteratePattern.OSCILLATION
            and maximum_log_k_residual > LOG_K_UPDATE_TOLERANCE
        ):
            reason = "A two-cycle oscillation was detected in log K-values."
            diagnostics.append(_failure_diagnostic("FLASH_OSCILLATION", reason))
            return _failed_flash_result(
                mixture,
                temperature_k,
                pressure_pa,
                stability,
                initial_k_values,
                history,
                diagnostics,
                reason,
            )
        if pattern is FlashIteratePattern.STAGNATION:
            reason = "The flash iteration stagnated before all criteria passed."
            diagnostics.append(_failure_diagnostic("FLASH_STAGNATION", reason))
            return _failed_flash_result(
                mixture,
                temperature_k,
                pressure_pa,
                stability,
                initial_k_values,
                history,
                diagnostics,
                reason,
            )
        prior_log_k_values.append(log_k_values)
        previous_beta = beta
        previous_liquid = phase_compositions.liquid_composition
        previous_vapor = phase_compositions.vapor_composition
        previous_liquid_root = liquid_phase.root_selection
        previous_vapor_root = vapor_phase.root_selection
        previous_target_log_k_values = target_log_k_values
        log_k_values = updated_log_k_values

    reason = "Maximum flash iterations reached without convergence."
    diagnostics.append(_failure_diagnostic("FLASH_MAXIMUM_ITERATIONS", reason))
    return _failed_flash_result(
        mixture,
        temperature_k,
        pressure_pa,
        stability,
        initial_k_values,
        history,
        diagnostics,
        reason,
        FlashConvergenceStatus.NOT_CONVERGED,
    )
