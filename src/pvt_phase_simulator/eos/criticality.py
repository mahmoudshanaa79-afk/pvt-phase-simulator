"""Local mixture-criticality derivatives on one fixed Peng-Robinson root.

This module evaluates Gibbs/TPD curvature at a user-specified ``T``, ``P``,
and composition. It does not locate a critical point. Analytical Module 13
simplex derivatives build the Hessian; only the derivative of that analytical
Hessian along a fixed soft mode is evaluated numerically.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from math import fsum, isfinite
from typing import Final

import numpy as np
from numpy.typing import NDArray

from pvt_phase_simulator.eos.derivatives import (
    calculate_fixed_root_mixture_fugacity_derivatives,
)
from pvt_phase_simulator.eos.mixing_rules import (
    BinaryInteractionMapping,
    BinaryInteractionPolicy,
    calculate_peng_robinson_mixture_parameters,
)
from pvt_phase_simulator.eos.peng_robinson import (
    MechanicalStabilityClassification,
    calculate_compressibility_roots,
    classify_mechanical_stability,
)
from pvt_phase_simulator.eos.phase_stability import evaluate_feed_phase_reference
from pvt_phase_simulator.fluid_models import FluidMixture, MixtureComponent

FloatArray = NDArray[np.float64]

DEFAULT_SYMMETRY_RELATIVE_TOLERANCE: Final = 1.0e-8
DEFAULT_MODE_GAP_RELATIVE_TOLERANCE: Final = 1.0e-8
DEFAULT_CUBIC_STEP: Final = 1.0e-3
DEFAULT_BOUNDARY_SAFETY_FACTOR: Final = 0.25
DEFAULT_MAXIMUM_STEP_REDUCTIONS: Final = 12
ROOT_CONTINUITY_RELATIVE_TOLERANCE: Final = 1.0e-8


class CriticalityStatus(StrEnum):
    """Outcome of a local criticality-derivative evaluation."""

    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"
    DERIVATIVES_UNAVAILABLE = "derivatives_unavailable"
    SYMMETRY_UNRELIABLE = "symmetry_unreliable"
    CRITICAL_MODE_DEGENERATE = "critical_mode_degenerate"
    CUBIC_DERIVATIVE_UNAVAILABLE = "cubic_derivative_unavailable"


@dataclass(frozen=True, slots=True)
class TangentHessianAnalysis:
    """Symmetry and eigensystem analysis of one tangent-space Hessian."""

    raw_hessian: tuple[tuple[float, ...], ...]
    symmetric_hessian: tuple[tuple[float, ...], ...] | None
    symmetry_defect: float
    symmetry_tolerance: float
    eigenvalues: tuple[float, ...]
    lambda_min: float | None
    tangent_mode: tuple[float, ...] | None
    physical_direction: tuple[float, ...] | None
    eigenvalue_gap: float | None
    mode_gap_tolerance: float | None
    status: CriticalityStatus
    reason: str | None


@dataclass(frozen=True, slots=True)
class DirectionalDerivativeDiagnostics:
    """Richardson evidence for the fixed-direction cubic derivative."""

    requested_step: float
    maximum_symmetric_step: float
    base_step: float | None
    refined_step: float | None
    coarse_estimate: float | None
    refined_estimate: float | None
    richardson_estimate: float | None
    estimated_error: float | None
    step_reductions: int
    sampled_steps: tuple[float, ...]
    sampled_curvatures: tuple[float, ...]
    sampled_roots: tuple[float, ...]
    applicable: bool
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class MixtureCriticalityResult:
    """Complete immutable local mixture-criticality derivative result."""

    temperature_k: float
    pressure_pa: float
    component_names: tuple[str, ...]
    composition: tuple[float, ...]
    active_component_indices: tuple[int, ...]
    inactive_component_indices: tuple[int, ...]
    active_composition: tuple[float, ...]
    selected_compressibility_factor: float | None
    root_selection_policy: str
    reference_active_component_index: int | None
    tangent_basis_identifier: str
    tangent_basis: tuple[tuple[float, ...], ...]
    raw_direct_hessian: tuple[tuple[float, ...], ...]
    raw_tangent_hessian: tuple[tuple[float, ...], ...]
    symmetric_tangent_hessian: tuple[tuple[float, ...], ...] | None
    symmetry_defect: float | None
    symmetry_tolerance: float | None
    eigenvalues: tuple[float, ...]
    lambda_min: float | None
    critical_tangent_vector: tuple[float, ...] | None
    active_critical_direction: tuple[float, ...] | None
    critical_composition_direction: tuple[float, ...] | None
    eigenvalue_gap: float | None
    mode_gap_tolerance: float | None
    cubic_directional_derivative: float | None
    cubic_diagnostics: DirectionalDerivativeDiagnostics | None
    fixed_root_applicable: bool
    status: CriticalityStatus
    reason: str | None


def _matrix_tuple(matrix: FloatArray) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(float(value) for value in row) for row in matrix)


def _largest_magnitude_index(values: FloatArray) -> int:
    """Return the first numerically tied largest-magnitude entry."""

    magnitudes = np.abs(values)
    largest = float(np.max(magnitudes))
    tolerance = 32.0 * np.finfo(float).eps * max(1.0, largest)
    return int(np.flatnonzero(magnitudes >= largest - tolerance)[0])


def construct_orthonormal_tangent_basis(
    component_count: int,
) -> tuple[tuple[float, ...], ...]:
    """Return a deterministic orthonormal basis for ``sum(dx_i)=0``.

    A reduced QR factorization is applied to columns ``e_j-e_n``. Each QR
    column is then signed so its first largest-magnitude entry is positive.
    """

    if not isinstance(component_count, int) or isinstance(component_count, bool):
        raise ValueError("component_count must be an integer.")
    if component_count < 2:
        raise ValueError("at least two components are required for a tangent basis.")
    direct = np.zeros((component_count, component_count - 1), dtype=float)
    direct[:-1, :] = np.eye(component_count - 1)
    direct[-1, :] = -1.0
    basis, _ = np.linalg.qr(direct, mode="reduced")
    for column in range(basis.shape[1]):
        pivot = _largest_magnitude_index(basis[:, column])
        if basis[pivot, column] < 0.0:
            basis[:, column] *= -1.0
    return _matrix_tuple(basis)


def calculate_direct_simplex_hessian(
    composition: tuple[float, ...],
    log_fugacity_composition_derivatives: tuple[tuple[float, ...], ...],
    *,
    reference_component_index: int | None = None,
) -> tuple[tuple[float, ...], ...]:
    """Build ``dq_j/dw_k`` from analytical fixed-root ``ln(phi)`` columns."""

    count = len(composition)
    if count < 2:
        raise ValueError("at least two active components are required.")
    reference = (
        count - 1 if reference_component_index is None else reference_component_index
    )
    if not 0 <= reference < count:
        raise ValueError("reference_component_index is outside component order.")
    if len(log_fugacity_composition_derivatives) != count:
        raise ValueError("fugacity derivative row count must match composition.")
    independent = tuple(index for index in range(count) if index != reference)
    if any(value <= 0.0 or not isfinite(value) for value in composition):
        raise ValueError("active composition must be finite and strictly positive.")
    if abs(fsum(composition) - 1.0) > 1.0e-10:
        raise ValueError("active composition must sum to one.")
    if any(len(row) != count - 1 for row in log_fugacity_composition_derivatives):
        raise ValueError("fugacity derivative columns must match simplex dimension.")
    hessian = np.empty((count - 1, count - 1), dtype=float)
    for row, component_index in enumerate(independent):
        for column, _coordinate_index in enumerate(independent):
            ideal = 1.0 / composition[component_index] if row == column else 0.0
            ideal += 1.0 / composition[reference]
            residual = (
                log_fugacity_composition_derivatives[component_index][column]
                - log_fugacity_composition_derivatives[reference][column]
            )
            hessian[row, column] = ideal + residual
    if not np.all(np.isfinite(hessian)):
        raise ValueError("direct simplex Hessian must be finite.")
    return _matrix_tuple(hessian)


def transform_direct_hessian_to_orthonormal_basis(
    direct_hessian: tuple[tuple[float, ...], ...],
    tangent_basis: tuple[tuple[float, ...], ...],
    *,
    reference_component_index: int | None = None,
) -> tuple[tuple[float, ...], ...]:
    """Transform the direct-coordinate quadratic form to ``dx=Q eta``."""

    q = np.asarray(tangent_basis, dtype=float)
    if q.ndim != 2 or q.shape[0] != q.shape[1] + 1:
        raise ValueError("tangent_basis must have shape (n, n-1).")
    count = q.shape[0]
    reference = (
        count - 1 if reference_component_index is None else reference_component_index
    )
    if not 0 <= reference < count:
        raise ValueError("reference_component_index is outside component order.")
    if not np.allclose(q.T @ q, np.eye(count - 1), rtol=0.0, atol=1.0e-12):
        raise ValueError("tangent_basis columns must be orthonormal.")
    if not np.allclose(np.sum(q, axis=0), 0.0, rtol=0.0, atol=1.0e-12):
        raise ValueError("tangent_basis columns must sum to zero.")
    direct_basis = np.zeros((count, count - 1), dtype=float)
    independent = tuple(index for index in range(count) if index != reference)
    for column, index in enumerate(independent):
        direct_basis[index, column] = 1.0
        direct_basis[reference, column] = -1.0
    coordinate_map = np.linalg.solve(direct_basis.T @ direct_basis, direct_basis.T @ q)
    h_w = np.asarray(direct_hessian, dtype=float)
    if h_w.shape != (count - 1, count - 1):
        raise ValueError("direct_hessian shape must match tangent dimension.")
    transformed = coordinate_map.T @ h_w @ coordinate_map
    if not np.all(np.isfinite(transformed)):
        raise ValueError("transformed Hessian must be finite.")
    return _matrix_tuple(transformed)


def _orient_mode(
    tangent_mode: FloatArray,
    physical_direction: FloatArray,
    previous_direction: tuple[float, ...] | None,
) -> tuple[FloatArray, FloatArray]:
    if previous_direction is not None:
        previous = np.asarray(previous_direction, dtype=float)
        if previous.shape != physical_direction.shape or not np.all(
            np.isfinite(previous)
        ):
            raise ValueError("previous_direction must match the physical direction.")
        orientation = float(np.dot(physical_direction, previous))
        if orientation < 0.0:
            return -tangent_mode, -physical_direction
        if orientation > 0.0:
            return tangent_mode, physical_direction
    pivot = _largest_magnitude_index(physical_direction)
    if physical_direction[pivot] < 0.0:
        return -tangent_mode, -physical_direction
    return tangent_mode, physical_direction


def analyze_tangent_hessian(
    tangent_hessian: tuple[tuple[float, ...], ...],
    tangent_basis: tuple[tuple[float, ...], ...],
    *,
    previous_direction: tuple[float, ...] | None = None,
    symmetry_relative_tolerance: float = DEFAULT_SYMMETRY_RELATIVE_TOLERANCE,
    mode_gap_relative_tolerance: float = DEFAULT_MODE_GAP_RELATIVE_TOLERANCE,
) -> TangentHessianAnalysis:
    """Check symmetry, find the soft mode, and enforce mode uniqueness."""

    raw = np.asarray(tangent_hessian, dtype=float)
    q = np.asarray(tangent_basis, dtype=float)
    if raw.ndim != 2 or raw.shape[0] != raw.shape[1] or raw.shape[0] == 0:
        raise ValueError("tangent_hessian must be a nonempty square matrix.")
    if q.shape != (raw.shape[0] + 1, raw.shape[0]):
        raise ValueError("tangent_basis shape is inconsistent with the Hessian.")
    if not np.all(np.isfinite(raw)) or not np.all(np.isfinite(q)):
        raise ValueError("Hessian and tangent basis must be finite.")
    if not np.allclose(q.T @ q, np.eye(raw.shape[0]), rtol=0.0, atol=1.0e-12):
        raise ValueError("tangent_basis columns must be orthonormal.")
    if not np.allclose(np.sum(q, axis=0), 0.0, rtol=0.0, atol=1.0e-12):
        raise ValueError("tangent_basis columns must sum to zero.")
    if symmetry_relative_tolerance <= 0.0 or mode_gap_relative_tolerance <= 0.0:
        raise ValueError("analysis tolerances must be positive.")
    defect = float(np.max(np.abs(raw - raw.T)))
    scale = max(1.0, float(np.max(np.abs(raw))))
    symmetry_tolerance = symmetry_relative_tolerance * scale
    if defect > symmetry_tolerance:
        return TangentHessianAnalysis(
            _matrix_tuple(raw),
            None,
            defect,
            symmetry_tolerance,
            (),
            None,
            None,
            None,
            None,
            None,
            CriticalityStatus.SYMMETRY_UNRELIABLE,
            "The raw Gibbs Hessian antisymmetry exceeds the supported tolerance.",
        )
    symmetric = 0.5 * (raw + raw.T)
    eigenvalues, eigenvectors = np.linalg.eigh(symmetric)
    gap = float(eigenvalues[1] - eigenvalues[0]) if len(eigenvalues) > 1 else None
    gap_tolerance = (
        mode_gap_relative_tolerance * max(1.0, float(np.max(np.abs(eigenvalues))))
        if gap is not None
        else None
    )
    if gap is not None and gap_tolerance is not None and gap <= gap_tolerance:
        return TangentHessianAnalysis(
            _matrix_tuple(raw),
            _matrix_tuple(symmetric),
            defect,
            symmetry_tolerance,
            tuple(float(value) for value in eigenvalues),
            float(eigenvalues[0]),
            None,
            None,
            gap,
            gap_tolerance,
            CriticalityStatus.CRITICAL_MODE_DEGENERATE,
            "The two lowest curvature eigenvalues do not define a unique soft mode.",
        )
    tangent_mode = eigenvectors[:, 0]
    direction = q @ tangent_mode
    tangent_mode, direction = _orient_mode(tangent_mode, direction, previous_direction)
    return TangentHessianAnalysis(
        _matrix_tuple(raw),
        _matrix_tuple(symmetric),
        defect,
        symmetry_tolerance,
        tuple(float(value) for value in eigenvalues),
        float(eigenvalues[0]),
        tuple(float(value) for value in tangent_mode),
        tuple(float(value) for value in direction),
        gap,
        gap_tolerance,
        CriticalityStatus.APPLICABLE,
        None,
    )


def maximum_symmetric_simplex_step(
    composition: tuple[float, ...], direction: tuple[float, ...]
) -> float:
    """Return the open-simplex boundary distance along both ``+d`` and ``-d``."""

    if len(composition) != len(direction) or not composition:
        raise ValueError("composition and direction must have equal nonzero length.")
    if any(not isfinite(value) for value in direction):
        raise ValueError("direction must be finite.")
    direction_scale = max(1.0, fsum(abs(value) for value in direction))
    if abs(fsum(direction)) > 1.0e-12 * direction_scale:
        raise ValueError("direction must lie in the composition tangent space.")
    bounds = tuple(
        fraction / abs(component)
        for fraction, component in zip(composition, direction, strict=True)
        if component != 0.0
    )
    if any(value <= 0.0 or not isfinite(value) for value in composition):
        raise ValueError("composition must be finite and strictly positive.")
    if not bounds:
        raise ValueError("direction must not be zero.")
    bound = min(bounds)
    if not isfinite(bound) or bound <= 0.0:
        raise ValueError("no finite symmetric simplex step is available.")
    return bound


def richardson_directional_derivative(
    curvature_evaluator: Callable[[float], tuple[float, float]],
    maximum_symmetric_step: float,
    *,
    requested_step: float = DEFAULT_CUBIC_STEP,
    boundary_safety_factor: float = DEFAULT_BOUNDARY_SAFETY_FACTOR,
    maximum_step_reductions: int = DEFAULT_MAXIMUM_STEP_REDUCTIONS,
) -> DirectionalDerivativeDiagnostics:
    """Differentiate curvature with a centered, second-order Richardson pair.

    The callback returns ``(curvature, continued_root)``. Any ``ValueError``
    denotes an inapplicable sample and causes deterministic step reduction.
    """

    if requested_step <= 0.0 or not isfinite(requested_step):
        raise ValueError("requested_step must be positive and finite.")
    if maximum_symmetric_step <= 0.0 or not isfinite(maximum_symmetric_step):
        raise ValueError("maximum_symmetric_step must be positive and finite.")
    if not 0.0 < boundary_safety_factor < 1.0:
        raise ValueError(
            "boundary_safety_factor must lie strictly between zero and one."
        )
    if maximum_step_reductions < 0:
        raise ValueError("maximum_step_reductions must be non-negative.")
    step = min(requested_step, boundary_safety_factor * maximum_symmetric_step)
    last_reason: str | None = None
    for reduction in range(maximum_step_reductions + 1):
        sampled_steps = (step, -step, step / 2.0, -step / 2.0)
        try:
            samples = tuple(curvature_evaluator(value) for value in sampled_steps)
        except (ValueError, FloatingPointError) as error:
            last_reason = str(error)
            step *= 0.5
            continue
        curvatures = tuple(value[0] for value in samples)
        roots = tuple(value[1] for value in samples)
        if not all(isfinite(value) for value in (*curvatures, *roots)):
            last_reason = "A directional-derivative sample was non-finite."
            step *= 0.5
            continue
        coarse = (curvatures[0] - curvatures[1]) / (2.0 * step)
        refined = (curvatures[2] - curvatures[3]) / step
        richardson = (4.0 * refined - coarse) / 3.0
        estimated_error = abs(richardson - refined)
        if not all(
            isfinite(value) for value in (coarse, refined, richardson, estimated_error)
        ):
            last_reason = "The Richardson derivative was non-finite."
            step *= 0.5
            continue
        return DirectionalDerivativeDiagnostics(
            requested_step,
            maximum_symmetric_step,
            step,
            step / 2.0,
            coarse,
            refined,
            richardson,
            estimated_error,
            reduction,
            sampled_steps,
            curvatures,
            roots,
            True,
            None,
        )
    return DirectionalDerivativeDiagnostics(
        requested_step,
        maximum_symmetric_step,
        None,
        None,
        None,
        None,
        None,
        None,
        maximum_step_reductions + 1,
        (),
        (),
        (),
        False,
        last_reason or "No trustworthy symmetric derivative step was available.",
    )


def _active_mixture(
    mixture: FluidMixture,
    interactions: BinaryInteractionMapping | None,
) -> tuple[
    FluidMixture | None,
    tuple[int, ...],
    tuple[int, ...],
    BinaryInteractionMapping | None,
]:
    active = tuple(
        index
        for index, item in enumerate(mixture.components)
        if item.mole_fraction > 0.0
    )
    inactive = tuple(
        index for index in range(len(mixture.components)) if index not in active
    )
    if len(active) < 2:
        return None, active, inactive, None
    reduced = FluidMixture(tuple(mixture.components[index] for index in active))
    if interactions is None:
        return reduced, active, inactive, None
    names = {item.component.name.casefold() for item in reduced.components}
    reduced_interactions = {
        pair: value
        for pair, value in interactions.items()
        if pair[0].casefold() in names and pair[1].casefold() in names
    }
    return reduced, active, inactive, reduced_interactions


def _empty_result(
    mixture: FluidMixture,
    temperature_k: float,
    pressure_pa: float,
    active: tuple[int, ...],
    inactive: tuple[int, ...],
    root: float | None,
    policy: str,
    status: CriticalityStatus,
    reason: str,
) -> MixtureCriticalityResult:
    return MixtureCriticalityResult(
        temperature_k,
        pressure_pa,
        tuple(item.component.name for item in mixture.components),
        tuple(item.mole_fraction for item in mixture.components),
        active,
        inactive,
        tuple(mixture.components[index].mole_fraction for index in active),
        root,
        policy,
        None,
        "reduced_qr(e_j-e_last); first tied maximum positive",
        (),
        (),
        (),
        None,
        None,
        None,
        (),
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        False,
        status,
        reason,
    )


def _root_signature(
    a_mix: float, b_mix: float
) -> tuple[tuple[float, ...], tuple[MechanicalStabilityClassification, ...]]:
    roots = calculate_compressibility_roots(a_mix, b_mix)
    classifications = tuple(
        classify_mechanical_stability(root, a_mix, b_mix).classification
        for root in roots
    )
    return roots, classifications


def _continued_index(roots: tuple[float, ...], reference_root: float) -> int:
    distances = tuple(abs(root - reference_root) for root in roots)
    index = min(range(len(roots)), key=distances.__getitem__)
    scale = max(1.0, abs(reference_root), abs(roots[index]))
    if len(roots) > 1:
        ordered = sorted(distances)
        if ordered[1] - ordered[0] <= ROOT_CONTINUITY_RELATIVE_TOLERANCE * scale:
            raise ValueError("The continued root is numerically ambiguous.")
    return index


def calculate_fixed_root_mixture_criticality(
    mixture: FluidMixture,
    temperature_k: float,
    pressure_pa: float,
    compressibility_factor: float,
    binary_interactions: BinaryInteractionMapping | None = None,
    binary_interaction_policy: BinaryInteractionPolicy = (
        BinaryInteractionPolicy.DEFAULT_ZERO
    ),
    *,
    reference_active_component_index: int | None = None,
    previous_critical_direction: tuple[float, ...] | None = None,
    cubic_step: float = DEFAULT_CUBIC_STEP,
    symmetry_relative_tolerance: float = DEFAULT_SYMMETRY_RELATIVE_TOLERANCE,
    mode_gap_relative_tolerance: float = DEFAULT_MODE_GAP_RELATIVE_TOLERANCE,
) -> MixtureCriticalityResult:
    """Evaluate local criticality derivatives on an explicitly supplied root."""

    reduced, active, inactive, active_interactions = _active_mixture(
        mixture, binary_interactions
    )
    if reduced is None:
        return _empty_result(
            mixture,
            temperature_k,
            pressure_pa,
            active,
            inactive,
            compressibility_factor,
            "explicit_fixed_root",
            CriticalityStatus.NOT_APPLICABLE,
            "Fewer than two active components remain after deterministic reduction.",
        )
    active_composition = tuple(item.mole_fraction for item in reduced.components)
    count = len(active_composition)
    reference = (
        count - 1
        if reference_active_component_index is None
        else reference_active_component_index
    )
    if not 0 <= reference < count:
        raise ValueError("reference_active_component_index is outside active order.")
    parameters = calculate_peng_robinson_mixture_parameters(
        reduced,
        temperature_k,
        pressure_pa,
        active_interactions,
        binary_interaction_policy,
    )
    base_roots, base_classifications = _root_signature(
        parameters.A_mix, parameters.B_mix
    )
    base_index = _continued_index(base_roots, compressibility_factor)
    root_scale = max(1.0, abs(compressibility_factor))
    if (
        abs(base_roots[base_index] - compressibility_factor)
        > ROOT_CONTINUITY_RELATIVE_TOLERANCE * root_scale
    ):
        return _empty_result(
            mixture,
            temperature_k,
            pressure_pa,
            active,
            inactive,
            compressibility_factor,
            "explicit_fixed_root",
            CriticalityStatus.DERIVATIVES_UNAVAILABLE,
            (
                "The supplied compressibility factor is not the current indexed "
                "cubic root."
            ),
        )
    derivatives = calculate_fixed_root_mixture_fugacity_derivatives(
        parameters,
        compressibility_factor,
        active_interactions,
        reference_component_index=reference,
    )
    derivative_rows = derivatives.log_fugacity_composition_derivatives
    if not derivatives.applicable or derivative_rows is None:
        return _empty_result(
            mixture,
            temperature_k,
            pressure_pa,
            active,
            inactive,
            compressibility_factor,
            "explicit_fixed_root",
            CriticalityStatus.DERIVATIVES_UNAVAILABLE,
            derivatives.failure_reason
            or "Fixed-root fugacity derivatives are unavailable.",
        )
    direct = calculate_direct_simplex_hessian(
        active_composition, derivative_rows, reference_component_index=reference
    )
    basis = construct_orthonormal_tangent_basis(count)
    tangent = transform_direct_hessian_to_orthonormal_basis(
        direct, basis, reference_component_index=reference
    )
    previous_active = None
    if previous_critical_direction is not None:
        if len(previous_critical_direction) != len(mixture.components):
            raise ValueError(
                "previous_critical_direction must match full component order."
            )
        previous_active = tuple(previous_critical_direction[index] for index in active)
    analysis = analyze_tangent_hessian(
        tangent,
        basis,
        previous_direction=previous_active,
        symmetry_relative_tolerance=symmetry_relative_tolerance,
        mode_gap_relative_tolerance=mode_gap_relative_tolerance,
    )
    if analysis.status is not CriticalityStatus.APPLICABLE:
        return MixtureCriticalityResult(
            temperature_k,
            pressure_pa,
            tuple(item.component.name for item in mixture.components),
            tuple(item.mole_fraction for item in mixture.components),
            active,
            inactive,
            active_composition,
            compressibility_factor,
            "explicit_fixed_root",
            reference,
            "reduced_qr(e_j-e_last); first tied maximum positive",
            basis,
            direct,
            analysis.raw_hessian,
            analysis.symmetric_hessian,
            analysis.symmetry_defect,
            analysis.symmetry_tolerance,
            analysis.eigenvalues,
            analysis.lambda_min,
            analysis.tangent_mode,
            analysis.physical_direction,
            None,
            analysis.eigenvalue_gap,
            analysis.mode_gap_tolerance,
            None,
            None,
            True,
            analysis.status,
            analysis.reason,
        )
    if analysis.physical_direction is None:
        raise RuntimeError("applicable Hessian analysis must contain a direction.")
    direction = analysis.physical_direction
    boundary = maximum_symmetric_simplex_step(active_composition, direction)
    independent = tuple(index for index in range(count) if index != reference)

    def curvature_at(step: float) -> tuple[float, float]:
        fractions_list = [
            fraction + step * component
            for fraction, component in zip(active_composition, direction, strict=True)
        ]
        fractions_list[reference] = 1.0 - fsum(
            fractions_list[index] for index in independent
        )
        fractions = tuple(fractions_list)
        if any(value <= 0.0 or not isfinite(value) for value in fractions):
            raise ValueError("A directional sample left the open active simplex.")
        trial_mixture = FluidMixture(
            tuple(
                MixtureComponent(item.component, fraction)
                for item, fraction in zip(reduced.components, fractions, strict=True)
            )
        )
        trial_parameters = calculate_peng_robinson_mixture_parameters(
            trial_mixture,
            temperature_k,
            pressure_pa,
            active_interactions,
            binary_interaction_policy,
        )
        trial_roots, trial_classifications = _root_signature(
            trial_parameters.A_mix, trial_parameters.B_mix
        )
        if (
            len(trial_roots) != len(base_roots)
            or trial_classifications != base_classifications
        ):
            raise ValueError("The cubic-root topology or classification changed.")
        trial_index = _continued_index(trial_roots, compressibility_factor)
        if trial_index != base_index:
            raise ValueError("The closest continued root changed its indexed branch.")
        trial_root = trial_roots[trial_index]
        trial_derivatives = calculate_fixed_root_mixture_fugacity_derivatives(
            trial_parameters,
            trial_root,
            active_interactions,
            reference_component_index=reference,
        )
        rows = trial_derivatives.log_fugacity_composition_derivatives
        if not trial_derivatives.applicable or rows is None:
            raise ValueError(
                trial_derivatives.failure_reason
                or "Perturbed fixed-root derivatives are unavailable."
            )
        trial_direct = np.asarray(
            calculate_direct_simplex_hessian(
                fractions, rows, reference_component_index=reference
            ),
            dtype=float,
        )
        direct_direction = np.asarray(tuple(direction[index] for index in independent))
        curvature = float(direct_direction @ trial_direct @ direct_direction)
        if not isfinite(curvature):
            raise ValueError("Directional curvature is non-finite.")
        return curvature, trial_root

    cubic = richardson_directional_derivative(
        curvature_at, boundary, requested_step=cubic_step
    )
    full_direction = [0.0] * len(mixture.components)
    for index, value in zip(active, direction, strict=True):
        full_direction[index] = value
    status = (
        CriticalityStatus.APPLICABLE
        if cubic.applicable
        else CriticalityStatus.CUBIC_DERIVATIVE_UNAVAILABLE
    )
    return MixtureCriticalityResult(
        temperature_k,
        pressure_pa,
        tuple(item.component.name for item in mixture.components),
        tuple(item.mole_fraction for item in mixture.components),
        active,
        inactive,
        active_composition,
        compressibility_factor,
        "explicit_fixed_root",
        reference,
        "reduced_qr(e_j-e_last); first tied maximum positive",
        basis,
        direct,
        analysis.raw_hessian,
        analysis.symmetric_hessian,
        analysis.symmetry_defect,
        analysis.symmetry_tolerance,
        analysis.eigenvalues,
        analysis.lambda_min,
        analysis.tangent_mode,
        direction,
        tuple(full_direction),
        analysis.eigenvalue_gap,
        analysis.mode_gap_tolerance,
        cubic.richardson_estimate,
        cubic,
        cubic.applicable,
        status,
        cubic.failure_reason,
    )


def calculate_stable_root_mixture_criticality(
    mixture: FluidMixture,
    temperature_k: float,
    pressure_pa: float,
    binary_interactions: BinaryInteractionMapping | None = None,
    binary_interaction_policy: BinaryInteractionPolicy = (
        BinaryInteractionPolicy.DEFAULT_ZERO
    ),
    *,
    reference_active_component_index: int | None = None,
    previous_critical_direction: tuple[float, ...] | None = None,
    cubic_step: float = DEFAULT_CUBIC_STEP,
    symmetry_relative_tolerance: float = DEFAULT_SYMMETRY_RELATIVE_TOLERANCE,
    mode_gap_relative_tolerance: float = DEFAULT_MODE_GAP_RELATIVE_TOLERANCE,
) -> MixtureCriticalityResult:
    """Select Module 5's stable homogeneous parent root, then evaluate locally."""

    reduced, active, inactive, active_interactions = _active_mixture(
        mixture, binary_interactions
    )
    if reduced is None:
        return _empty_result(
            mixture,
            temperature_k,
            pressure_pa,
            active,
            inactive,
            None,
            "stable_parent_root",
            CriticalityStatus.NOT_APPLICABLE,
            "Fewer than two active components remain after deterministic reduction.",
        )
    reference = evaluate_feed_phase_reference(
        reduced,
        temperature_k,
        pressure_pa,
        active_interactions,
        binary_interaction_policy,
    )
    root = reference.selected_compressibility_factor
    if root is None:
        return _empty_result(
            mixture,
            temperature_k,
            pressure_pa,
            active,
            inactive,
            None,
            "stable_parent_root",
            CriticalityStatus.DERIVATIVES_UNAVAILABLE,
            reference.failure_reason
            or "No stable homogeneous parent root is available.",
        )
    result = calculate_fixed_root_mixture_criticality(
        mixture,
        temperature_k,
        pressure_pa,
        root,
        binary_interactions,
        binary_interaction_policy,
        reference_active_component_index=reference_active_component_index,
        previous_critical_direction=previous_critical_direction,
        cubic_step=cubic_step,
        symmetry_relative_tolerance=symmetry_relative_tolerance,
        mode_gap_relative_tolerance=mode_gap_relative_tolerance,
    )
    return MixtureCriticalityResult(
        result.temperature_k,
        result.pressure_pa,
        result.component_names,
        result.composition,
        result.active_component_indices,
        result.inactive_component_indices,
        result.active_composition,
        result.selected_compressibility_factor,
        "stable_parent_root",
        result.reference_active_component_index,
        result.tangent_basis_identifier,
        result.tangent_basis,
        result.raw_direct_hessian,
        result.raw_tangent_hessian,
        result.symmetric_tangent_hessian,
        result.symmetry_defect,
        result.symmetry_tolerance,
        result.eigenvalues,
        result.lambda_min,
        result.critical_tangent_vector,
        result.active_critical_direction,
        result.critical_composition_direction,
        result.eigenvalue_gap,
        result.mode_gap_tolerance,
        result.cubic_directional_derivative,
        result.cubic_diagnostics,
        result.fixed_root_applicable,
        result.status,
        result.reason,
    )


def criticality_residual_pair(result: MixtureCriticalityResult) -> tuple[float, float]:
    """Return ``(lambda_min, C)`` without performing a critical-point solve."""

    if (
        result.status is not CriticalityStatus.APPLICABLE
        or result.lambda_min is None
        or result.cubic_directional_derivative is None
    ):
        raise ValueError(result.reason or "Criticality residuals are not applicable.")
    return result.lambda_min, result.cubic_directional_derivative
