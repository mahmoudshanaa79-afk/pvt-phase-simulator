"""Michelsen-style mixture phase-stability analysis foundation.

This module tests tangent-plane-distance tendencies. It does not calculate
phase fractions, equilibrium phase compositions, or a two-phase flash.
"""

from dataclasses import dataclass
from enum import StrEnum
from math import exp, fsum, isclose, isfinite, log
from sys import float_info
from typing import Final

from pvt_phase_simulator._validation import (
    require_finite as _require_finite,
)
from pvt_phase_simulator._validation import (
    require_positive as _require_positive,
)
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
    canonical_binary_interactions_to_mapping,
)
from pvt_phase_simulator.eos.mixture_fugacity import (
    calculate_mixture_fugacity_coefficients,
)
from pvt_phase_simulator.eos.peng_robinson import (
    MechanicalStabilityClassification,
    MechanicalStabilityResult,
    calculate_compressibility_roots,
    classify_mechanical_stability,
)
from pvt_phase_simulator.fluid_models import (
    MOLE_FRACTION_TOLERANCE,
    Component,
    FluidMixture,
    MixtureComponent,
)

WILSON_COEFFICIENT: Final = 5.373
DEFAULT_MAXIMUM_ITERATIONS: Final = 100
STATIONARITY_CONVERGENCE_TOLERANCE: Final = 1e-10
COMPOSITION_CONVERGENCE_TOLERANCE: Final = 1e-10
TPD_CHANGE_CONVERGENCE_TOLERANCE: Final = 1e-12
TRIVIAL_COMPOSITION_TOLERANCE: Final = 1e-8
TPD_STABILITY_TOLERANCE: Final = 1e-8
FALLBACK_COMPONENT_RICH_EPSILON: Final = 1e-3
FALLBACK_START_EQUIVALENCE_TOLERANCE: Final = 1e-12
MAXIMUM_FALLBACK_STARTS: Final = 10
ROOT_SWITCH_COMPARISON_TOLERANCE: Final = 1e-8
ROOT_SWITCH_RELATIVE_JUMP_TOLERANCE: Final = 5e-2
_LOG_FLOAT_MAX: Final = log(float_info.max)
_LOG_FLOAT_MIN: Final = log(float_info.min)


class PhaseTrialKind(StrEnum):
    """Character of a phase-stability trial and its root-selection policy."""

    VAPOR_LIKE = "vapor_like"
    LIQUID_LIKE = "liquid_like"


class PhaseStabilityStatus(StrEnum):
    """Outcome of both required tangent-plane-distance trials."""

    STABLE = "stable"
    UNSTABLE = "unstable"
    INCONCLUSIVE = "inconclusive"


class PhaseTrialSelectionReason(StrEnum):
    """Reason a final result was or was not selected for one trial character."""

    WILSON_CONCLUSIVE = "wilson_conclusive"
    FALLBACK_LOWEST_NEGATIVE_TPD = "fallback_lowest_negative_tpd"
    FALLBACK_LOWEST_NONNEGATIVE_TPD = "fallback_lowest_nonnegative_tpd"
    NO_RELIABLE_CONVERGED_TRIAL = "no_reliable_converged_trial"


@dataclass(frozen=True, slots=True)
class WilsonKValueResult:
    """Immutable dimensionless Wilson initial estimate for one component."""

    component_name: str
    k_value: float


@dataclass(frozen=True, slots=True)
class PhaseRootSelection:
    """Mechanical root candidates and a trial-character selection."""

    trial_kind: PhaseTrialKind
    candidates: tuple[MechanicalStabilityResult, ...]
    selected_compressibility_factor: float | None
    selected_classification: MechanicalStabilityClassification | None
    diagnostics: tuple[EOSDiagnostic, ...]
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class FeedPhaseReference:
    """Immutable homogeneous feed reference used in TPD calculations."""

    composition: tuple[float, ...]
    selected_compressibility_factor: float | None
    selected_mechanical_classification: MechanicalStabilityClassification | None
    component_log_fugacity_coefficients: tuple[float, ...]
    root_candidates: tuple[MechanicalStabilityResult, ...]
    diagnostics: tuple[EOSDiagnostic, ...]
    failure_reason: str | None
    binary_interaction_policy: BinaryInteractionPolicy
    binary_interactions: CanonicalBinaryInteractions
    supplied_binary_interaction_pairs: CanonicalBinaryInteractionPairs
    defaulted_binary_interaction_pairs: CanonicalBinaryInteractionPairs


@dataclass(frozen=True, slots=True)
class PhaseStabilityIteration:
    """Immutable numerical record for one evaluated trial composition."""

    iteration: int
    log_weights: tuple[float | None, ...]
    composition: tuple[float, ...]
    selected_compressibility_factor: float
    mechanical_classification: MechanicalStabilityClassification
    root_candidates: tuple[MechanicalStabilityResult, ...]
    component_log_fugacity_coefficients: tuple[float, ...]
    tangent_plane_distance: float
    stationarity_residual: float
    composition_change: float
    tangent_plane_distance_change: float | None


@dataclass(frozen=True, slots=True)
class PhaseStabilityTrialResult:
    """Immutable result of one vapor-like or liquid-like stability trial."""

    trial_kind: PhaseTrialKind
    converged: bool
    iteration_count: int
    initial_composition: tuple[float, ...]
    final_trial_composition: tuple[float, ...]
    selected_compressibility_factor: float | None
    mechanical_classification: MechanicalStabilityClassification | None
    component_log_fugacity_coefficients: tuple[float, ...]
    tangent_plane_distance: float | None
    convergence_metric: float | None
    trivial_solution: bool
    diagnostics: tuple[EOSDiagnostic, ...]
    root_candidates: tuple[MechanicalStabilityResult, ...]
    history: tuple[PhaseStabilityIteration, ...]
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class PhaseStabilityCharacterResult:
    """Immutable Wilson and fallback provenance for one trial character."""

    trial_kind: PhaseTrialKind
    wilson_trial: PhaseStabilityTrialResult
    fallback_triggered: bool
    fallback_starting_compositions: tuple[tuple[float, ...], ...]
    fallback_trials: tuple[PhaseStabilityTrialResult, ...]
    selected_trial: PhaseStabilityTrialResult | None
    selection_reason: PhaseTrialSelectionReason
    distinct_negative_trial_count: int
    diagnostics: tuple[EOSDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class MixturePhaseStabilityResult:
    """Immutable two-trial stability result; no phase fractions are calculated."""

    feed_composition: tuple[float, ...]
    temperature_k: float
    pressure_pa: float
    feed_reference: FeedPhaseReference
    wilson_k_values: tuple[WilsonKValueResult, ...]
    vapor_like_character: PhaseStabilityCharacterResult
    liquid_like_character: PhaseStabilityCharacterResult
    vapor_like_trial: PhaseStabilityTrialResult
    liquid_like_trial: PhaseStabilityTrialResult
    status: PhaseStabilityStatus
    binary_interaction_policy: BinaryInteractionPolicy
    binary_interactions: CanonicalBinaryInteractions
    supplied_binary_interaction_pairs: CanonicalBinaryInteractionPairs
    defaulted_binary_interaction_pairs: CanonicalBinaryInteractionPairs


def _require_composition(
    composition: tuple[float, ...],
    name: str,
) -> None:
    if not isinstance(composition, tuple) or not composition:
        raise ValueError(f"{name} must be a non-empty immutable tuple.")
    for index, value in enumerate(composition):
        _require_finite(value, f"{name}[{index}]")
        if value < 0.0:
            raise ValueError(f"{name} values must be non-negative.")
    total = fsum(composition)
    if not isclose(total, 1.0, rel_tol=0.0, abs_tol=MOLE_FRACTION_TOLERANCE):
        raise ValueError(f"{name} must sum to one within tolerance.")


def _require_same_length(
    reference: tuple[object, ...], *values: tuple[object, ...]
) -> None:
    if any(len(value) != len(reference) for value in values):
        raise ValueError("component-aligned inputs must have equal lengths.")


def calculate_wilson_k_values(
    components: tuple[Component, ...],
    temperature_k: float,
    pressure_pa: float,
) -> tuple[WilsonKValueResult, ...]:
    """Return finite positive Wilson K-values used only as initial estimates.

    Temperature is in K and pressure is in Pa. Wilson values do not prove phase
    equilibrium or thermodynamic stability. Invalid inputs and exponential
    overflow or underflow raise ``ValueError``.
    """

    _require_positive(temperature_k, "temperature_k")
    _require_positive(pressure_pa, "pressure_pa")
    if not isinstance(components, tuple) or not components:
        raise ValueError("components must be a non-empty immutable tuple.")

    results: list[WilsonKValueResult] = []
    for component in components:
        if not isinstance(component, Component):
            raise ValueError("components must contain immutable Component records.")
        log_k_value = (
            log(component.critical_pressure_pa)
            - log(pressure_pa)
            + WILSON_COEFFICIENT
            * (1.0 + component.acentric_factor)
            * (1.0 - component.critical_temperature_k / temperature_k)
        )
        _require_finite(log_k_value, f"Wilson log K for {component.name}")
        if log_k_value > _LOG_FLOAT_MAX or log_k_value < _LOG_FLOAT_MIN:
            raise ValueError(
                f"Wilson K-value for {component.name} would overflow or underflow."
            )
        k_value = exp(log_k_value)
        _require_positive(k_value, f"Wilson K-value for {component.name}")
        results.append(WilsonKValueResult(component.name, k_value))
    return tuple(results)


def _normalize_log_weights(
    log_weights: tuple[float | None, ...],
) -> tuple[float, ...]:
    finite_logs = tuple(value for value in log_weights if value is not None)
    if not finite_logs:
        raise ValueError("at least one trial weight must be strictly positive.")
    for value in finite_logs:
        _require_finite(value, "trial log weight")
    largest = max(finite_logs)
    scaled = tuple(
        0.0 if value is None else exp(value - largest) for value in log_weights
    )
    total = fsum(scaled)
    _require_positive(total, "trial normalization sum")
    normalized = tuple(value / total for value in scaled)
    if not isclose(
        fsum(normalized),
        1.0,
        rel_tol=0.0,
        abs_tol=MOLE_FRACTION_TOLERANCE,
    ):
        raise ValueError("normalized trial composition must sum to one.")
    return normalized


def initialize_trial_composition(
    feed_composition: tuple[float, ...],
    k_values: tuple[float, ...],
    trial_kind: PhaseTrialKind,
) -> tuple[float, ...]:
    """Return a normalized Wilson vapor-like or liquid-like composition.

    Vapor-like log weights are ``ln(z_i) + ln(K_i)`` and liquid-like log
    weights are ``ln(z_i) - ln(K_i)``. The immutable feed is never modified.
    """

    _require_composition(feed_composition, "feed_composition")
    if not isinstance(k_values, tuple):
        raise ValueError("k_values must be an immutable tuple.")
    _require_same_length(feed_composition, k_values)
    if not isinstance(trial_kind, PhaseTrialKind):
        raise ValueError("trial_kind must be a PhaseTrialKind.")

    direction = 1.0 if trial_kind is PhaseTrialKind.VAPOR_LIKE else -1.0
    log_weights: list[float | None] = []
    for index, (feed_fraction, k_value) in enumerate(
        zip(feed_composition, k_values, strict=True)
    ):
        _require_positive(k_value, f"k_values[{index}]")
        log_weights.append(
            None
            if feed_fraction == 0.0
            else log(feed_fraction) + direction * log(k_value)
        )
    return _normalize_log_weights(tuple(log_weights))


def generate_fallback_trial_compositions(
    feed_composition: tuple[float, ...],
    component_rich_epsilon: float = FALLBACK_COMPONENT_RICH_EPSILON,
    maximum_starts: int = MAXIMUM_FALLBACK_STARTS,
) -> tuple[tuple[float, ...], ...]:
    """Return bounded deterministic fallback starts on the feed support.

    Starts are ordered as the feed, a uniform composition over active feed
    components, and active-component-rich compositions. In a rich start the
    selected component receives ``1 - epsilon`` and epsilon is distributed
    over the other active components in proportion to their feed fractions.
    Numerically equivalent starts are retained only once.
    """

    _require_composition(feed_composition, "feed_composition")
    _require_finite(component_rich_epsilon, "component_rich_epsilon")
    if not 0.0 < component_rich_epsilon < 1.0:
        raise ValueError("component_rich_epsilon must be between zero and one.")
    if not isinstance(maximum_starts, int) or maximum_starts <= 0:
        raise ValueError("maximum_starts must be a positive integer.")

    active_indices = tuple(
        index for index, fraction in enumerate(feed_composition) if fraction > 0.0
    )
    uniform_fraction = 1.0 / len(active_indices)
    candidates: list[tuple[float, ...]] = [
        feed_composition,
        tuple(
            uniform_fraction if index in active_indices else 0.0
            for index in range(len(feed_composition))
        ),
    ]
    if len(active_indices) > 1:
        for rich_index in active_indices:
            other_feed_total = 1.0 - feed_composition[rich_index]
            candidate = tuple(
                0.0
                if index not in active_indices
                else 1.0 - component_rich_epsilon
                if index == rich_index
                else component_rich_epsilon * feed_composition[index] / other_feed_total
                for index in range(len(feed_composition))
            )
            total = fsum(candidate)
            candidates.append(tuple(value / total for value in candidate))

    unique: list[tuple[float, ...]] = []
    for candidate in candidates:
        _require_composition(candidate, "fallback composition")
        if any(
            max(
                abs(left - right)
                for left, right in zip(candidate, existing, strict=True)
            )
            <= FALLBACK_START_EQUIVALENCE_TOLERANCE
            for existing in unique
        ):
            continue
        unique.append(candidate)
        if len(unique) == maximum_starts:
            break
    return tuple(unique)


def calculate_tangent_plane_distance(
    feed_composition: tuple[float, ...],
    trial_composition: tuple[float, ...],
    feed_log_fugacity_coefficients: tuple[float, ...],
    trial_log_fugacity_coefficients: tuple[float, ...],
) -> float:
    """Return dimensionless tangent-plane distance for normalized compositions.

    If ``z_i`` is zero, ``w_i`` must also be zero because a new component
    cannot appear outside the feed support. Terms with ``w_i = 0`` contribute
    their mathematical zero limit and ``log(0)`` is never evaluated.
    """

    _require_composition(feed_composition, "feed_composition")
    _require_composition(trial_composition, "trial_composition")
    _require_same_length(
        feed_composition,
        trial_composition,
        feed_log_fugacity_coefficients,
        trial_log_fugacity_coefficients,
    )
    terms: list[float] = []
    for index, (
        feed_fraction,
        trial_fraction,
        feed_log_phi,
        trial_log_phi,
    ) in enumerate(
        zip(
            feed_composition,
            trial_composition,
            feed_log_fugacity_coefficients,
            trial_log_fugacity_coefficients,
            strict=True,
        )
    ):
        _require_finite(feed_log_phi, f"feed_log_fugacity_coefficients[{index}]")
        _require_finite(trial_log_phi, f"trial_log_fugacity_coefficients[{index}]")
        if feed_fraction == 0.0:
            if trial_fraction != 0.0:
                raise ValueError(
                    "trial composition must be zero where feed composition is zero."
                )
            continue
        if trial_fraction == 0.0:
            continue
        terms.append(
            trial_fraction
            * (log(trial_fraction) + trial_log_phi - log(feed_fraction) - feed_log_phi)
        )
    tangent_plane_distance = fsum(terms)
    _require_finite(tangent_plane_distance, "tangent_plane_distance")
    return tangent_plane_distance


def calculate_stationarity_residual(
    trial_composition: tuple[float, ...],
    updated_log_weights: tuple[float | None, ...],
) -> float:
    """Return a common-scale-invariant stationary-composition residual.

    Updated weights are normalized first. The residual is
    ``max_i |ln(w_i_new) - ln(w_i_old)|`` over the active support, so adding a
    common constant to every updated log weight leaves it unchanged.
    """

    _require_composition(trial_composition, "trial_composition")
    if not isinstance(updated_log_weights, tuple):
        raise ValueError("updated_log_weights must be an immutable tuple.")
    _require_same_length(trial_composition, updated_log_weights)
    updated_composition = _normalize_log_weights(updated_log_weights)
    residuals: list[float] = []
    for index, (old_fraction, new_fraction, log_weight) in enumerate(
        zip(
            trial_composition,
            updated_composition,
            updated_log_weights,
            strict=True,
        )
    ):
        if log_weight is None:
            if old_fraction != 0.0:
                raise ValueError(
                    "inactive updated weight must match zero trial support."
                )
            continue
        _require_positive(old_fraction, f"active trial_composition[{index}]")
        _require_positive(new_fraction, f"active updated composition[{index}]")
        residuals.append(abs(log(new_fraction) - log(old_fraction)))
    stationarity_residual = max(residuals, default=0.0)
    _require_finite(stationarity_residual, "stationarity_residual")
    return stationarity_residual


def _root_diagnostic(
    code: str,
    category: DiagnosticCategory,
    message: str,
    value: float | None = None,
) -> EOSDiagnostic:
    return EOSDiagnostic(
        code=code,
        severity=DiagnosticSeverity.WARNING,
        category=category,
        message=message,
        value=value,
    )


def select_phase_trial_root(
    A_mix: float,
    B_mix: float,
    trial_kind: PhaseTrialKind,
) -> PhaseRootSelection:
    """Select a mechanically stable root by trial character.

    The largest stable root is used for a vapor-like trial and the smallest for
    a liquid-like trial. Marginal and unstable roots are retained but excluded.
    Root size is not interpreted as global thermodynamic stability.
    """

    if not isinstance(trial_kind, PhaseTrialKind):
        raise ValueError("trial_kind must be a PhaseTrialKind.")
    roots = calculate_compressibility_roots(A_mix, B_mix)
    candidates = tuple(
        classify_mechanical_stability(root, A_mix, B_mix) for root in roots
    )
    stable = tuple(
        item
        for item in candidates
        if item.classification is MechanicalStabilityClassification.STABLE
    )
    diagnostics: list[EOSDiagnostic] = []
    marginal_count = sum(
        item.classification is MechanicalStabilityClassification.MARGINAL
        for item in candidates
    )
    if marginal_count:
        diagnostics.append(
            _root_diagnostic(
                "MARGINAL_TRIAL_ROOTS_EXCLUDED",
                DiagnosticCategory.NUMERICAL_CONDITIONING,
                "Marginal roots were retained diagnostically but excluded "
                "from trial-root selection.",
                float(marginal_count),
            )
        )
    if not stable:
        return PhaseRootSelection(
            trial_kind=trial_kind,
            candidates=candidates,
            selected_compressibility_factor=None,
            selected_classification=None,
            diagnostics=tuple(diagnostics),
            failure_reason="No mechanically stable trial root is available.",
        )
    selected = (
        max(stable, key=lambda item: item.compressibility_factor)
        if trial_kind is PhaseTrialKind.VAPOR_LIKE
        else min(stable, key=lambda item: item.compressibility_factor)
    )
    return PhaseRootSelection(
        trial_kind=trial_kind,
        candidates=candidates,
        selected_compressibility_factor=selected.compressibility_factor,
        selected_classification=selected.classification,
        diagnostics=tuple(diagnostics),
        failure_reason=None,
    )


def detect_phase_root_switch(
    previous: PhaseRootSelection,
    current: PhaseRootSelection,
) -> EOSDiagnostic | None:
    """Return an observational diagnostic for a discontinuous root change.

    No branch continuation is enforced. A switch is reported when the current
    character-selected root is not the closest current stable root to the
    previous selection, or when the stable-root count changes together with a
    selected-root jump exceeding five percent of the local dimensionless
    ``Z`` scale. The comparison tolerance is ``1e-8 * max(1, |Z_old|, |Z_new|)``.
    """

    if previous.trial_kind is not current.trial_kind:
        raise ValueError("root selections must have the same trial character.")
    previous_z = previous.selected_compressibility_factor
    current_z = current.selected_compressibility_factor
    if previous_z is None or current_z is None:
        return None
    previous_stable = tuple(
        item.compressibility_factor
        for item in previous.candidates
        if item.classification is MechanicalStabilityClassification.STABLE
    )
    current_stable = tuple(
        item.compressibility_factor
        for item in current.candidates
        if item.classification is MechanicalStabilityClassification.STABLE
    )
    if not current_stable:
        return None

    scale = max(1.0, abs(previous_z), abs(current_z))
    comparison_tolerance = ROOT_SWITCH_COMPARISON_TOLERANCE * scale
    closest_current = min(current_stable, key=lambda value: abs(value - previous_z))
    selected_is_not_continuous = abs(closest_current - current_z) > comparison_tolerance
    relative_jump = abs(current_z - previous_z) / scale
    branch_count_changed_with_jump = (
        len(previous_stable) != len(current_stable)
        and relative_jump > ROOT_SWITCH_RELATIVE_JUMP_TOLERANCE
    )
    if not selected_is_not_continuous and not branch_count_changed_with_jump:
        return None
    return EOSDiagnostic(
        code="DISCONTINUOUS_TRIAL_ROOT_SWITCH",
        severity=DiagnosticSeverity.WARNING,
        category=DiagnosticCategory.NUMERICAL_CONDITIONING,
        message=(
            "The character-selected mechanically stable root changed "
            "discontinuously; branch continuity remains observational only."
        ),
        value=abs(current_z - previous_z),
    )


def _extend_unique_diagnostics(
    destination: list[EOSDiagnostic],
    additions: tuple[EOSDiagnostic, ...],
) -> None:
    for diagnostic in additions:
        if diagnostic not in destination:
            destination.append(diagnostic)


def _snapshot_supplied_interactions(
    feed_reference: FeedPhaseReference,
) -> dict[tuple[str, str], float]:
    component_names = {
        first_name
        for pair in (
            *feed_reference.supplied_binary_interaction_pairs,
            *feed_reference.defaulted_binary_interaction_pairs,
        )
        for first_name in pair
    }
    if not component_names:
        component_names = {
            name
            for first_name, second_name, _ in feed_reference.binary_interactions
            for name in (first_name, second_name)
        }
    snapshot = canonical_binary_interactions_to_mapping(
        feed_reference.binary_interactions,
        component_names,
    )
    for first_name, second_name in feed_reference.supplied_binary_interaction_pairs:
        snapshot.setdefault((first_name, second_name), 0.0)
        snapshot.setdefault((second_name, first_name), 0.0)
    return snapshot


def _feed_composition(mixture: FluidMixture) -> tuple[float, ...]:
    return tuple(item.mole_fraction for item in mixture.components)


def evaluate_feed_phase_reference(
    mixture: FluidMixture,
    temperature_k: float,
    pressure_pa: float,
    binary_interactions: BinaryInteractionMapping | None = None,
    binary_interaction_policy: BinaryInteractionPolicy = (
        BinaryInteractionPolicy.DEFAULT_ZERO
    ),
) -> FeedPhaseReference:
    """Evaluate all feed roots and select the lowest-Gibbs homogeneous branch.

    The comparison metric is ``sum(z_i ln(phi_i))``. This selects a homogeneous
    feed reference only and does not establish stability against phase splitting.
    """

    _require_positive(temperature_k, "temperature_k")
    _require_positive(pressure_pa, "pressure_pa")
    parameters = calculate_peng_robinson_mixture_parameters(
        mixture,
        temperature_k,
        pressure_pa,
        binary_interactions,
        binary_interaction_policy,
    )
    composition = _feed_composition(mixture)
    diagnostics = list(evaluate_mixture_eos_diagnostics(parameters))
    roots = calculate_compressibility_roots(parameters.A_mix, parameters.B_mix)
    candidates = tuple(
        classify_mechanical_stability(root, parameters.A_mix, parameters.B_mix)
        for root in roots
    )
    stable = tuple(
        item
        for item in candidates
        if item.classification is MechanicalStabilityClassification.STABLE
    )
    marginal_count = sum(
        item.classification is MechanicalStabilityClassification.MARGINAL
        for item in candidates
    )
    if marginal_count:
        diagnostics.append(
            _root_diagnostic(
                "MARGINAL_FEED_ROOTS_EXCLUDED",
                DiagnosticCategory.NUMERICAL_CONDITIONING,
                "Marginal feed roots were retained but excluded from the "
                "homogeneous reference selection.",
                float(marginal_count),
            )
        )
    if len(stable) > 1:
        diagnostics.append(
            EOSDiagnostic(
                code="MULTIPLE_STABLE_FEED_ROOTS",
                severity=DiagnosticSeverity.INFO,
                category=DiagnosticCategory.MODEL_APPLICABILITY,
                message=(
                    "Multiple mechanically stable homogeneous feed roots exist; "
                    "the lowest residual-Gibbs branch is used as a reference."
                ),
                value=float(len(stable)),
            )
        )
    if not stable:
        return FeedPhaseReference(
            composition=composition,
            selected_compressibility_factor=None,
            selected_mechanical_classification=None,
            component_log_fugacity_coefficients=(),
            root_candidates=candidates,
            diagnostics=tuple(diagnostics),
            failure_reason="No mechanically stable feed root is available.",
            binary_interaction_policy=parameters.binary_interaction_policy,
            binary_interactions=parameters.binary_interactions,
            supplied_binary_interaction_pairs=(
                parameters.supplied_binary_interaction_pairs
            ),
            defaulted_binary_interaction_pairs=(
                parameters.defaulted_binary_interaction_pairs
            ),
        )

    evaluated: list[tuple[float, MechanicalStabilityResult, tuple[float, ...]]] = []
    for candidate in stable:
        fugacity_results = calculate_mixture_fugacity_coefficients(
            parameters,
            candidate.compressibility_factor,
        )
        log_phi = tuple(result.log_fugacity_coefficient for result in fugacity_results)
        residual_gibbs = fsum(
            fraction * coefficient
            for fraction, coefficient in zip(composition, log_phi, strict=True)
        )
        evaluated.append((residual_gibbs, candidate, log_phi))
    _, selected, selected_log_phi = min(
        evaluated,
        key=lambda item: (item[0], item[1].compressibility_factor),
    )
    return FeedPhaseReference(
        composition=composition,
        selected_compressibility_factor=selected.compressibility_factor,
        selected_mechanical_classification=selected.classification,
        component_log_fugacity_coefficients=selected_log_phi,
        root_candidates=candidates,
        diagnostics=tuple(diagnostics),
        failure_reason=None,
        binary_interaction_policy=parameters.binary_interaction_policy,
        binary_interactions=parameters.binary_interactions,
        supplied_binary_interaction_pairs=parameters.supplied_binary_interaction_pairs,
        defaulted_binary_interaction_pairs=parameters.defaulted_binary_interaction_pairs,
    )


def _mixture_with_composition(
    feed: FluidMixture,
    composition: tuple[float, ...],
) -> FluidMixture:
    return FluidMixture(
        tuple(
            MixtureComponent(item.component, fraction)
            for item, fraction in zip(feed.components, composition, strict=True)
        )
    )


def _log_weights_from_composition(
    feed_composition: tuple[float, ...],
    composition: tuple[float, ...],
) -> tuple[float | None, ...]:
    values: list[float | None] = []
    for feed_fraction, trial_fraction in zip(
        feed_composition, composition, strict=True
    ):
        if feed_fraction == 0.0:
            if trial_fraction != 0.0:
                raise ValueError(
                    "trial composition must be zero where feed composition is zero."
                )
            values.append(None)
        else:
            _require_positive(trial_fraction, "active trial fraction")
            values.append(log(trial_fraction))
    return tuple(values)


def _trial_failure(
    trial_kind: PhaseTrialKind,
    initial_composition: tuple[float, ...],
    final_composition: tuple[float, ...],
    history: list[PhaseStabilityIteration],
    diagnostics: tuple[EOSDiagnostic, ...],
    root_selection: PhaseRootSelection | None,
    failure_reason: str,
) -> PhaseStabilityTrialResult:
    last = history[-1] if history else None
    return PhaseStabilityTrialResult(
        trial_kind=trial_kind,
        converged=False,
        iteration_count=len(history),
        initial_composition=initial_composition,
        final_trial_composition=final_composition,
        selected_compressibility_factor=(
            last.selected_compressibility_factor if last is not None else None
        ),
        mechanical_classification=(
            last.mechanical_classification if last is not None else None
        ),
        component_log_fugacity_coefficients=(
            last.component_log_fugacity_coefficients if last is not None else ()
        ),
        tangent_plane_distance=(
            last.tangent_plane_distance if last is not None else None
        ),
        convergence_metric=(last.stationarity_residual if last is not None else None),
        trivial_solution=False,
        diagnostics=diagnostics,
        root_candidates=(root_selection.candidates if root_selection else ()),
        history=tuple(history),
        failure_reason=failure_reason,
    )


def run_phase_stability_trial(
    mixture: FluidMixture,
    temperature_k: float,
    pressure_pa: float,
    feed_reference: FeedPhaseReference,
    initial_composition: tuple[float, ...],
    trial_kind: PhaseTrialKind,
    binary_interactions: BinaryInteractionMapping | None = None,
    binary_interaction_policy: BinaryInteractionPolicy = (
        BinaryInteractionPolicy.DEFAULT_ZERO
    ),
    maximum_iterations: int = DEFAULT_MAXIMUM_ITERATIONS,
) -> PhaseStabilityTrialResult:
    """Run one log-space successive-substitution TPD stability trial."""

    _require_positive(temperature_k, "temperature_k")
    _require_positive(pressure_pa, "pressure_pa")
    if not isinstance(maximum_iterations, int) or maximum_iterations <= 0:
        raise ValueError("maximum_iterations must be a positive integer.")
    if not isinstance(trial_kind, PhaseTrialKind):
        raise ValueError("trial_kind must be a PhaseTrialKind.")
    feed_composition = _feed_composition(mixture)
    _require_composition(initial_composition, "initial_composition")
    _require_same_length(feed_composition, initial_composition)
    if feed_reference.composition != feed_composition:
        raise ValueError("feed_reference composition does not match mixture.")
    if feed_reference.failure_reason is not None:
        return _trial_failure(
            trial_kind,
            initial_composition,
            initial_composition,
            [],
            feed_reference.diagnostics,
            None,
            f"Feed reference unavailable: {feed_reference.failure_reason}",
        )
    _require_same_length(
        feed_composition,
        feed_reference.component_log_fugacity_coefficients,
    )
    for index, value in enumerate(feed_reference.component_log_fugacity_coefficients):
        _require_finite(value, f"feed log fugacity coefficient[{index}]")

    log_weights = _log_weights_from_composition(
        feed_composition,
        initial_composition,
    )
    history: list[PhaseStabilityIteration] = []
    previous_tpd: float | None = None
    prior_compositions: list[tuple[float, ...]] = []
    accumulated_diagnostics: list[EOSDiagnostic] = []
    final_diagnostics: tuple[EOSDiagnostic, ...] = ()
    final_root_selection: PhaseRootSelection | None = None

    for iteration in range(1, maximum_iterations + 1):
        composition = _normalize_log_weights(log_weights)
        if any(
            feed_fraction > 0.0 and trial_fraction == 0.0
            for feed_fraction, trial_fraction in zip(
                feed_composition, composition, strict=True
            )
        ):
            return _trial_failure(
                trial_kind,
                initial_composition,
                composition,
                history,
                final_diagnostics,
                final_root_selection,
                "An active trial component underflowed to zero.",
            )

        trial_mixture = _mixture_with_composition(mixture, composition)
        try:
            parameters = calculate_peng_robinson_mixture_parameters(
                trial_mixture,
                temperature_k,
                pressure_pa,
                binary_interactions,
                binary_interaction_policy,
            )
            if (
                parameters.binary_interaction_policy
                is not feed_reference.binary_interaction_policy
                or parameters.binary_interactions != feed_reference.binary_interactions
                or parameters.supplied_binary_interaction_pairs
                != feed_reference.supplied_binary_interaction_pairs
                or parameters.defaulted_binary_interaction_pairs
                != feed_reference.defaulted_binary_interaction_pairs
            ):
                raise ValueError(
                    "trial binary-interaction provenance does not match the feed."
                )
            root_selection = select_phase_trial_root(
                parameters.A_mix,
                parameters.B_mix,
                trial_kind,
            )
        except ValueError as error:
            return _trial_failure(
                trial_kind,
                initial_composition,
                composition,
                history,
                final_diagnostics,
                final_root_selection,
                f"Trial EOS evaluation failed: {error}",
            )
        iteration_diagnostics = (
            *evaluate_mixture_eos_diagnostics(parameters),
            *root_selection.diagnostics,
        )
        _extend_unique_diagnostics(
            accumulated_diagnostics,
            tuple(iteration_diagnostics),
        )
        if final_root_selection is not None:
            switch_diagnostic = detect_phase_root_switch(
                final_root_selection,
                root_selection,
            )
            if switch_diagnostic is not None:
                _extend_unique_diagnostics(
                    accumulated_diagnostics,
                    (switch_diagnostic,),
                )
        final_root_selection = root_selection
        final_diagnostics = tuple(accumulated_diagnostics)
        if root_selection.selected_compressibility_factor is None:
            return _trial_failure(
                trial_kind,
                initial_composition,
                composition,
                history,
                final_diagnostics,
                root_selection,
                root_selection.failure_reason or "Trial root selection failed.",
            )

        selected_classification = root_selection.selected_classification
        if selected_classification is None:
            return _trial_failure(
                trial_kind,
                initial_composition,
                composition,
                history,
                final_diagnostics,
                root_selection,
                "Selected trial root has no mechanical classification.",
            )
        try:
            fugacity_results = calculate_mixture_fugacity_coefficients(
                parameters,
                root_selection.selected_compressibility_factor,
            )
            trial_log_phi = tuple(
                result.log_fugacity_coefficient for result in fugacity_results
            )
            tangent_plane_distance = calculate_tangent_plane_distance(
                feed_composition,
                composition,
                feed_reference.component_log_fugacity_coefficients,
                trial_log_phi,
            )
        except ValueError as error:
            return _trial_failure(
                trial_kind,
                initial_composition,
                composition,
                history,
                final_diagnostics,
                root_selection,
                f"Trial fugacity or TPD evaluation failed: {error}",
            )
        updated_log_weights: list[float | None] = []
        for feed_fraction, feed_log_phi, trial_coefficient, old_log_weight in zip(
            feed_composition,
            feed_reference.component_log_fugacity_coefficients,
            trial_log_phi,
            log_weights,
            strict=True,
        ):
            if feed_fraction == 0.0:
                updated_log_weights.append(None)
                continue
            if old_log_weight is None:
                raise ValueError("active trial log weight must be present.")
            new_log_weight = log(feed_fraction) + feed_log_phi - trial_coefficient
            _require_finite(new_log_weight, "updated trial log weight")
            updated_log_weights.append(new_log_weight)
        try:
            update_metric = calculate_stationarity_residual(
                composition,
                tuple(updated_log_weights),
            )
            updated_composition = _normalize_log_weights(tuple(updated_log_weights))
        except ValueError as error:
            return _trial_failure(
                trial_kind,
                initial_composition,
                composition,
                history,
                final_diagnostics,
                root_selection,
                f"Trial composition update failed: {error}",
            )
        composition_change = max(
            abs(new - old)
            for new, old in zip(updated_composition, composition, strict=True)
        )
        tpd_change = (
            None if previous_tpd is None else abs(tangent_plane_distance - previous_tpd)
        )
        history.append(
            PhaseStabilityIteration(
                iteration=iteration,
                log_weights=log_weights,
                composition=composition,
                selected_compressibility_factor=(
                    root_selection.selected_compressibility_factor
                ),
                mechanical_classification=selected_classification,
                root_candidates=root_selection.candidates,
                component_log_fugacity_coefficients=trial_log_phi,
                tangent_plane_distance=tangent_plane_distance,
                stationarity_residual=update_metric,
                composition_change=composition_change,
                tangent_plane_distance_change=tpd_change,
            )
        )

        converged = (
            update_metric <= STATIONARITY_CONVERGENCE_TOLERANCE
            and composition_change <= COMPOSITION_CONVERGENCE_TOLERANCE
            and (tpd_change is None or tpd_change <= TPD_CHANGE_CONVERGENCE_TOLERANCE)
        )
        if converged:
            trivial = (
                max(
                    abs(trial_fraction - feed_fraction)
                    for trial_fraction, feed_fraction in zip(
                        composition, feed_composition, strict=True
                    )
                )
                <= TRIVIAL_COMPOSITION_TOLERANCE
            )
            return PhaseStabilityTrialResult(
                trial_kind=trial_kind,
                converged=True,
                iteration_count=iteration,
                initial_composition=initial_composition,
                final_trial_composition=composition,
                selected_compressibility_factor=(
                    root_selection.selected_compressibility_factor
                ),
                mechanical_classification=root_selection.selected_classification,
                component_log_fugacity_coefficients=trial_log_phi,
                tangent_plane_distance=tangent_plane_distance,
                convergence_metric=update_metric,
                trivial_solution=trivial,
                diagnostics=final_diagnostics,
                root_candidates=root_selection.candidates,
                history=tuple(history),
                failure_reason=None,
            )

        if (
            update_metric > 100.0 * STATIONARITY_CONVERGENCE_TOLERANCE
            and prior_compositions
            and max(
                abs(current - two_steps_back)
                for current, two_steps_back in zip(
                    updated_composition,
                    prior_compositions[-1],
                    strict=True,
                )
            )
            <= COMPOSITION_CONVERGENCE_TOLERANCE
        ):
            return _trial_failure(
                trial_kind,
                initial_composition,
                composition,
                history,
                final_diagnostics,
                root_selection,
                "A two-cycle oscillation was detected.",
            )
        prior_compositions.append(composition)
        previous_tpd = tangent_plane_distance
        log_weights = tuple(updated_log_weights)

    return _trial_failure(
        trial_kind,
        initial_composition,
        _normalize_log_weights(log_weights),
        history,
        final_diagnostics,
        final_root_selection,
        "Maximum stability iterations reached without convergence.",
    )


def _is_reliable_trial(trial: PhaseStabilityTrialResult) -> bool:
    return (
        trial.converged
        and trial.failure_reason is None
        and trial.tangent_plane_distance is not None
        and isfinite(trial.tangent_plane_distance)
        and trial.mechanical_classification is MechanicalStabilityClassification.STABLE
    )


def _distinct_stationary_trials(
    trials: tuple[PhaseStabilityTrialResult, ...],
) -> tuple[PhaseStabilityTrialResult, ...]:
    distinct: list[PhaseStabilityTrialResult] = []
    for trial in sorted(
        trials,
        key=lambda item: (
            item.tangent_plane_distance
            if item.tangent_plane_distance is not None
            else float("inf")
        ),
    ):
        if any(
            max(
                abs(left - right)
                for left, right in zip(
                    trial.final_trial_composition,
                    existing.final_trial_composition,
                    strict=True,
                )
            )
            <= TRIVIAL_COMPOSITION_TOLERANCE
            for existing in distinct
        ):
            continue
        distinct.append(trial)
    return tuple(distinct)


def select_phase_stability_trial_attempts(
    wilson_trial: PhaseStabilityTrialResult,
    fallback_trials: tuple[PhaseStabilityTrialResult, ...] = (),
    tpd_tolerance: float = TPD_STABILITY_TOLERANCE,
) -> PhaseStabilityCharacterResult:
    """Select one reliable trial while preserving every attempted result."""

    _require_positive(tpd_tolerance, "tpd_tolerance")
    if not isinstance(fallback_trials, tuple):
        raise ValueError("fallback_trials must be an immutable tuple.")
    if any(
        trial.trial_kind is not wilson_trial.trial_kind for trial in fallback_trials
    ):
        raise ValueError("all fallback trials must have the Wilson trial character.")
    if wilson_trial.converged:
        if fallback_trials:
            raise ValueError(
                "fallback trials must not follow a conclusive Wilson trial."
            )
        return PhaseStabilityCharacterResult(
            trial_kind=wilson_trial.trial_kind,
            wilson_trial=wilson_trial,
            fallback_triggered=False,
            fallback_starting_compositions=(),
            fallback_trials=(),
            selected_trial=wilson_trial,
            selection_reason=PhaseTrialSelectionReason.WILSON_CONCLUSIVE,
            distinct_negative_trial_count=(
                1
                if not wilson_trial.trivial_solution
                and wilson_trial.tangent_plane_distance is not None
                and wilson_trial.tangent_plane_distance < -tpd_tolerance
                else 0
            ),
            diagnostics=(),
        )

    diagnostics: list[EOSDiagnostic] = []
    if fallback_trials:
        diagnostics.append(
            EOSDiagnostic(
                code="FALLBACK_MULTISTART_TRIGGERED",
                severity=DiagnosticSeverity.INFO,
                category=DiagnosticCategory.NUMERICAL_CONDITIONING,
                message=(
                    "The Wilson trial was inconclusive, so bounded deterministic "
                    "fallback starts were evaluated for this trial character."
                ),
                value=float(len(fallback_trials)),
            )
        )
    reliable = tuple(trial for trial in fallback_trials if _is_reliable_trial(trial))
    negative = tuple(
        trial
        for trial in reliable
        if not trial.trivial_solution
        and trial.tangent_plane_distance is not None
        and trial.tangent_plane_distance < -tpd_tolerance
    )
    distinct_negative = _distinct_stationary_trials(negative)
    nonnegative: tuple[PhaseStabilityTrialResult, ...] = ()
    selected: PhaseStabilityTrialResult | None
    if distinct_negative:
        selected = min(
            distinct_negative,
            key=lambda item: (
                item.tangent_plane_distance
                if item.tangent_plane_distance is not None
                else float("inf")
            ),
        )
        reason = PhaseTrialSelectionReason.FALLBACK_LOWEST_NEGATIVE_TPD
    else:
        nonnegative = tuple(
            trial
            for trial in reliable
            if trial.tangent_plane_distance is not None
            and trial.tangent_plane_distance >= -tpd_tolerance
        )
    if not distinct_negative and nonnegative:
        selected = min(
            nonnegative,
            key=lambda item: (
                item.tangent_plane_distance
                if item.tangent_plane_distance is not None
                else float("inf")
            ),
        )
        reason = PhaseTrialSelectionReason.FALLBACK_LOWEST_NONNEGATIVE_TPD
    elif not distinct_negative:
        selected = None
        reason = PhaseTrialSelectionReason.NO_RELIABLE_CONVERGED_TRIAL
        diagnostics.append(
            EOSDiagnostic(
                code="NO_RELIABLE_PHASE_STABILITY_TRIAL",
                severity=DiagnosticSeverity.WARNING,
                category=DiagnosticCategory.NUMERICAL_CONDITIONING,
                message=(
                    "Neither the Wilson attempt nor a fallback attempt produced "
                    "a reliable converged result for this trial character."
                ),
                value=None,
            )
        )
    return PhaseStabilityCharacterResult(
        trial_kind=wilson_trial.trial_kind,
        wilson_trial=wilson_trial,
        fallback_triggered=bool(fallback_trials),
        fallback_starting_compositions=tuple(
            trial.initial_composition for trial in fallback_trials
        ),
        fallback_trials=fallback_trials,
        selected_trial=selected,
        selection_reason=reason,
        distinct_negative_trial_count=len(distinct_negative),
        diagnostics=tuple(diagnostics),
    )


def run_phase_stability_character(
    mixture: FluidMixture,
    temperature_k: float,
    pressure_pa: float,
    feed_reference: FeedPhaseReference,
    wilson_trial: PhaseStabilityTrialResult,
    binary_interactions: BinaryInteractionMapping | None = None,
    binary_interaction_policy: BinaryInteractionPolicy = (
        BinaryInteractionPolicy.DEFAULT_ZERO
    ),
    maximum_iterations: int = DEFAULT_MAXIMUM_ITERATIONS,
) -> PhaseStabilityCharacterResult:
    """Return a Wilson result directly or run bounded deterministic fallbacks."""

    if wilson_trial.converged:
        return select_phase_stability_trial_attempts(wilson_trial)
    starts = generate_fallback_trial_compositions(feed_reference.composition)
    fallback_trials = tuple(
        run_phase_stability_trial(
            mixture,
            temperature_k,
            pressure_pa,
            feed_reference,
            start,
            wilson_trial.trial_kind,
            binary_interactions,
            binary_interaction_policy,
            maximum_iterations,
        )
        for start in starts
    )
    return select_phase_stability_trial_attempts(wilson_trial, fallback_trials)


def classify_phase_stability_trials(
    vapor_like_trial: PhaseStabilityTrialResult,
    liquid_like_trial: PhaseStabilityTrialResult,
    tpd_tolerance: float = TPD_STABILITY_TOLERANCE,
) -> PhaseStabilityStatus:
    """Combine two required trials without converting failure into stability.

    A distinct converged negative-TPD trial establishes instability. Stability
    requires both trials to converge without such a result. This decision does
    not calculate phase fractions or equilibrium phase compositions.
    """

    _require_positive(tpd_tolerance, "tpd_tolerance")
    if vapor_like_trial.trial_kind is not PhaseTrialKind.VAPOR_LIKE:
        raise ValueError("vapor_like_trial must have vapor-like trial provenance.")
    if liquid_like_trial.trial_kind is not PhaseTrialKind.LIQUID_LIKE:
        raise ValueError("liquid_like_trial must have liquid-like trial provenance.")
    trials = (vapor_like_trial, liquid_like_trial)
    if any(
        trial.converged
        and not trial.trivial_solution
        and trial.tangent_plane_distance is not None
        and trial.tangent_plane_distance < -tpd_tolerance
        for trial in trials
    ):
        return PhaseStabilityStatus.UNSTABLE
    if all(trial.converged for trial in trials):
        return PhaseStabilityStatus.STABLE
    return PhaseStabilityStatus.INCONCLUSIVE


def analyze_mixture_phase_stability(
    mixture: FluidMixture,
    temperature_k: float,
    pressure_pa: float,
    binary_interactions: BinaryInteractionMapping | None = None,
    binary_interaction_policy: BinaryInteractionPolicy = (
        BinaryInteractionPolicy.DEFAULT_ZERO
    ),
    maximum_iterations: int = DEFAULT_MAXIMUM_ITERATIONS,
) -> MixturePhaseStabilityResult:
    """Run vapor-like and liquid-like TPD trials without performing a flash."""

    feed_reference = evaluate_feed_phase_reference(
        mixture,
        temperature_k,
        pressure_pa,
        binary_interactions,
        binary_interaction_policy,
    )
    interaction_snapshot = _snapshot_supplied_interactions(feed_reference)
    wilson_results = calculate_wilson_k_values(
        tuple(item.component for item in mixture.components),
        temperature_k,
        pressure_pa,
    )
    k_values = tuple(item.k_value for item in wilson_results)
    feed_composition = _feed_composition(mixture)
    vapor_initial = initialize_trial_composition(
        feed_composition,
        k_values,
        PhaseTrialKind.VAPOR_LIKE,
    )
    liquid_initial = initialize_trial_composition(
        feed_composition,
        k_values,
        PhaseTrialKind.LIQUID_LIKE,
    )
    vapor_wilson_trial = run_phase_stability_trial(
        mixture,
        temperature_k,
        pressure_pa,
        feed_reference,
        vapor_initial,
        PhaseTrialKind.VAPOR_LIKE,
        interaction_snapshot,
        binary_interaction_policy,
        maximum_iterations,
    )
    liquid_wilson_trial = run_phase_stability_trial(
        mixture,
        temperature_k,
        pressure_pa,
        feed_reference,
        liquid_initial,
        PhaseTrialKind.LIQUID_LIKE,
        interaction_snapshot,
        binary_interaction_policy,
        maximum_iterations,
    )
    vapor_character = run_phase_stability_character(
        mixture,
        temperature_k,
        pressure_pa,
        feed_reference,
        vapor_wilson_trial,
        interaction_snapshot,
        binary_interaction_policy,
        maximum_iterations,
    )
    liquid_character = run_phase_stability_character(
        mixture,
        temperature_k,
        pressure_pa,
        feed_reference,
        liquid_wilson_trial,
        interaction_snapshot,
        binary_interaction_policy,
        maximum_iterations,
    )
    vapor_trial = vapor_character.selected_trial or vapor_wilson_trial
    liquid_trial = liquid_character.selected_trial or liquid_wilson_trial
    status = classify_phase_stability_trials(vapor_trial, liquid_trial)
    return MixturePhaseStabilityResult(
        feed_composition=feed_composition,
        temperature_k=temperature_k,
        pressure_pa=pressure_pa,
        feed_reference=feed_reference,
        wilson_k_values=wilson_results,
        vapor_like_character=vapor_character,
        liquid_like_character=liquid_character,
        vapor_like_trial=vapor_trial,
        liquid_like_trial=liquid_trial,
        status=status,
        binary_interaction_policy=feed_reference.binary_interaction_policy,
        binary_interactions=feed_reference.binary_interactions,
        supplied_binary_interaction_pairs=(
            feed_reference.supplied_binary_interaction_pairs
        ),
        defaulted_binary_interaction_pairs=(
            feed_reference.defaulted_binary_interaction_pairs
        ),
    )
