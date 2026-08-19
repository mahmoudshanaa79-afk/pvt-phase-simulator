"""Independent numerical references for Module 14 derivative verification.

This verification-only module deliberately does not import ``eos.derivatives``.
It uses ordinary real EOS value APIs for finite differences and a separately
written complex-safe algebraic PR evaluator for complex-step checks.
"""

from collections.abc import Callable
from dataclasses import dataclass
from math import exp, log, sqrt

from pvt_phase_simulator.eos.mixing_rules import (
    PengRobinsonMixtureParameters,
    calculate_component_pair_attraction_parameter,
    calculate_peng_robinson_mixture_parameters,
)
from pvt_phase_simulator.eos.mixture_fugacity import (
    calculate_component_attraction_sum,
    calculate_mixture_fugacity_coefficients,
)
from pvt_phase_simulator.eos.peng_robinson import (
    MechanicalStabilityClassification,
    calculate_compressibility_roots,
    classify_mechanical_stability,
)
from pvt_phase_simulator.fluid_models import Component, FluidMixture, MixtureComponent
from pvt_phase_simulator.physical_constants import UNIVERSAL_GAS_CONSTANT

Vector = tuple[float, ...]
VectorEvaluator = Callable[[float], Vector]

# Duplicated published rounded PR constants make this isolated evaluator
# independent of the production parameter and derivative implementations.
_OMEGA_A = 0.45724
_OMEGA_B = 0.07780
_KAPPA_0 = 0.37464
_KAPPA_1 = 1.54226
_KAPPA_2 = 0.26992


class RootTrackingError(RuntimeError):
    """Raised when a perturbed root cannot be matched without ambiguity."""


@dataclass(frozen=True, slots=True)
class VerificationState:
    """One deterministic smooth-state specification for verification."""

    case_id: str
    components: tuple[Component, ...]
    fractions: tuple[float, ...]
    temperature_k: float
    pressure_pa: float
    root_index: int
    reference_component_index: int | None = None


@dataclass(frozen=True, slots=True)
class OrdinaryState:
    """Ordinary real EOS values at one explicitly tracked root."""

    parameters: PengRobinsonMixtureParameters
    roots: tuple[float, ...]
    root: float
    root_order_index: int
    mechanical_classification: MechanicalStabilityClassification
    log_fugacity_coefficients: Vector
    pair_attraction_parameters: tuple[tuple[float, ...], ...]
    component_attraction_sums: Vector


@dataclass(frozen=True, slots=True)
class RichardsonVectorResult:
    """Central differences and adjacent second-order Richardson estimates."""

    step_sizes: tuple[float, float, float, float]
    central_differences: tuple[Vector, Vector, Vector, Vector]
    richardson_estimates: tuple[Vector, Vector, Vector]

    @property
    def reference(self) -> Vector:
        """Return the predetermined h/h/2 Richardson estimate."""

        return self.richardson_estimates[0]


@dataclass(frozen=True, slots=True)
class ComplexAlgebraValues:
    """Complex-safe independently evaluated PR algebraic quantities."""

    alpha: tuple[complex, ...]
    a_alpha: tuple[complex, ...]
    pair_attraction: tuple[tuple[complex, ...], ...]
    attraction_sums: tuple[complex, ...]
    a_mix: complex
    b_mix: complex
    A: complex
    B: complex


def build_mixture(
    components: tuple[Component, ...], fractions: tuple[float, ...]
) -> FluidMixture:
    """Build an ordinary immutable mixture in the supplied component order."""

    return FluidMixture(
        tuple(
            MixtureComponent(component, fraction)
            for component, fraction in zip(components, fractions, strict=True)
        )
    )


def build_parameters(
    state: VerificationState,
    *,
    temperature_k: float | None = None,
    pressure_pa: float | None = None,
    fractions: tuple[float, ...] | None = None,
) -> PengRobinsonMixtureParameters:
    """Recompute ordinary production values without derivative helpers."""

    return calculate_peng_robinson_mixture_parameters(
        build_mixture(state.components, fractions or state.fractions),
        state.temperature_k if temperature_k is None else temperature_k,
        state.pressure_pa if pressure_pa is None else pressure_pa,
    )


def _normalized_root_index(root_index: int, count: int) -> int:
    index = root_index if root_index >= 0 else count + root_index
    if not 0 <= index < count:
        raise RootTrackingError("requested root index is outside the baseline roots")
    return index


def ordinary_state(
    state: VerificationState,
    *,
    temperature_k: float | None = None,
    pressure_pa: float | None = None,
    fractions: tuple[float, ...] | None = None,
    baseline: OrdinaryState | None = None,
) -> OrdinaryState:
    """Evaluate ordinary real EOS values and safely continue one root.

    A perturbed root is accepted only when root count, ordered branch,
    admissibility, nearest-root identity, and mechanical classification agree
    with the baseline state.
    """

    parameters = build_parameters(
        state,
        temperature_k=temperature_k,
        pressure_pa=pressure_pa,
        fractions=fractions,
    )
    roots = calculate_compressibility_roots(parameters.A_mix, parameters.B_mix)
    if baseline is None:
        order_index = _normalized_root_index(state.root_index, len(roots))
    else:
        if len(roots) != len(baseline.roots):
            raise RootTrackingError("root_count_changed")
        order_index = baseline.root_order_index
    root = roots[order_index]
    classification = classify_mechanical_stability(
        root, parameters.A_mix, parameters.B_mix
    ).classification
    if baseline is not None:
        distances = sorted(abs(candidate - baseline.root) for candidate in roots)
        if len(distances) > 1 and distances[1] <= 4.0 * max(distances[0], 1e-15):
            raise RootTrackingError("nearest_root_ambiguous")
        nearest_index = min(
            range(len(roots)), key=lambda index: abs(roots[index] - baseline.root)
        )
        if nearest_index != order_index:
            raise RootTrackingError("ordered_and_nearest_root_disagree")
        if classification is not baseline.mechanical_classification:
            raise RootTrackingError("mechanical_classification_changed")
    if root <= parameters.B_mix:
        raise RootTrackingError("root_became_inadmissible")
    log_phi = tuple(
        item.log_fugacity_coefficient
        for item in calculate_mixture_fugacity_coefficients(parameters, root)
    )
    pair = tuple(
        tuple(
            calculate_component_pair_attraction_parameter(first, second)
            for second in parameters.component_parameters
        )
        for first in parameters.component_parameters
    )
    sums = tuple(
        calculate_component_attraction_sum(component, parameters.component_parameters)
        for component in parameters.component_parameters
    )
    return OrdinaryState(
        parameters=parameters,
        roots=roots,
        root=root,
        root_order_index=order_index,
        mechanical_classification=classification,
        log_fugacity_coefficients=log_phi,
        pair_attraction_parameters=pair,
        component_attraction_sums=sums,
    )


def perturb_simplex(
    fractions: tuple[float, ...],
    independent_index: int,
    reference_index: int,
    delta: float,
) -> tuple[float, ...]:
    """Perturb one Module 13 simplex coordinate and reconstruct the reference."""

    result = list(fractions)
    result[independent_index] += delta
    result[reference_index] -= delta
    if any(value < 0.0 or value > 1.0 for value in result):
        raise ValueError("simplex perturbation left the physical simplex")
    return tuple(result)


def richardson_vector(
    evaluator: VectorEvaluator,
    base_step: float,
) -> RichardsonVectorResult:
    """Use the predetermined sequence h, h/2, h/4, h/8."""

    steps = (
        base_step,
        base_step / 2.0,
        base_step / 4.0,
        base_step / 8.0,
    )
    central: list[Vector] = []
    for step in steps:
        high = evaluator(step)
        low = evaluator(-step)
        central.append(
            tuple(
                (high_value - low_value) / (2.0 * step)
                for high_value, low_value in zip(high, low, strict=True)
            )
        )
    richardson = tuple(
        tuple(
            fine_value + (fine_value - coarse_value) / 3.0
            for coarse_value, fine_value in zip(coarse, fine, strict=True)
        )
        for coarse, fine in zip(central[:-1], central[1:], strict=True)
    )
    return RichardsonVectorResult(
        step_sizes=steps,
        central_differences=(central[0], central[1], central[2], central[3]),
        richardson_estimates=(richardson[0], richardson[1], richardson[2]),
    )


def pressure_richardson(
    state: VerificationState,
    baseline: OrdinaryState,
    extractor: Callable[[OrdinaryState], Vector],
) -> RichardsonVectorResult:
    """Differentiate ordinary values with respect to pressure in Pa."""

    return richardson_vector(
        lambda delta: extractor(
            ordinary_state(
                state,
                pressure_pa=state.pressure_pa + delta,
                baseline=baseline,
            )
        ),
        1e-3 * state.pressure_pa,
    )


def log_pressure_richardson(
    state: VerificationState,
    baseline: OrdinaryState,
    extractor: Callable[[OrdinaryState], Vector],
) -> RichardsonVectorResult:
    """Differentiate ordinary values with respect to dimensionless ln(P)."""

    return richardson_vector(
        lambda delta: extractor(
            ordinary_state(
                state,
                pressure_pa=state.pressure_pa * exp(delta),
                baseline=baseline,
            )
        ),
        1e-3,
    )


def temperature_richardson(
    state: VerificationState,
    baseline: OrdinaryState,
    extractor: Callable[[OrdinaryState], Vector],
) -> RichardsonVectorResult:
    """Differentiate ordinary values with respect to temperature in K."""

    return richardson_vector(
        lambda delta: extractor(
            ordinary_state(
                state,
                temperature_k=state.temperature_k + delta,
                baseline=baseline,
            )
        ),
        1e-3 * state.temperature_k,
    )


def composition_richardson(
    state: VerificationState,
    baseline: OrdinaryState,
    independent_index: int,
    reference_index: int,
    extractor: Callable[[OrdinaryState], Vector],
) -> RichardsonVectorResult:
    """Differentiate by direct reconstruction of one simplex coordinate."""

    positive_margin = min(
        state.fractions[independent_index], state.fractions[reference_index]
    )
    if positive_margin <= 0.0:
        raise RootTrackingError("composition_boundary")
    base_step = min(1e-3, 0.2 * positive_margin)
    return richardson_vector(
        lambda delta: extractor(
            ordinary_state(
                state,
                fractions=perturb_simplex(
                    state.fractions,
                    independent_index,
                    reference_index,
                    delta,
                ),
                baseline=baseline,
            )
        ),
        base_step,
    )


def complex_algebra_values(
    components: tuple[Component, ...],
    fractions: tuple[complex, ...],
    temperature_k: complex,
    pressure_pa: complex,
) -> ComplexAlgebraValues:
    """Evaluate isolated PR algebra with operations valid for complex-step.

    No real-root, sorting, comparison, admissibility, mechanical, phase, or
    fugacity code is used here.
    """

    alpha: list[complex] = []
    a_alpha: list[complex] = []
    b_values: list[float] = []
    for component in components:
        kappa = (
            _KAPPA_0
            + _KAPPA_1 * component.acentric_factor
            - _KAPPA_2 * component.acentric_factor**2
        )
        reduced = temperature_k / component.critical_temperature_k
        alpha_value = (1.0 + kappa * (1.0 - reduced**0.5)) ** 2
        a_value = (
            _OMEGA_A
            * UNIVERSAL_GAS_CONSTANT**2
            * component.critical_temperature_k**2
            / component.critical_pressure_pa
        )
        b_value = (
            _OMEGA_B
            * UNIVERSAL_GAS_CONSTANT
            * component.critical_temperature_k
            / component.critical_pressure_pa
        )
        alpha.append(alpha_value)
        a_alpha.append(a_value * alpha_value)
        b_values.append(b_value)
    pair = tuple(
        tuple((a_alpha[i] * a_alpha[j]) ** 0.5 for j in range(len(components)))
        for i in range(len(components))
    )
    sums = tuple(
        sum(fractions[j] * pair[i][j] for j in range(len(components)))
        for i in range(len(components))
    )
    a_mix = sum(fractions[i] * sums[i] for i in range(len(components)))
    b_mix = sum(fractions[i] * b_values[i] for i in range(len(components)))
    A = a_mix * pressure_pa / (UNIVERSAL_GAS_CONSTANT**2 * temperature_k**2)
    B = b_mix * pressure_pa / (UNIVERSAL_GAS_CONSTANT * temperature_k)
    return ComplexAlgebraValues(
        alpha=tuple(alpha),
        a_alpha=tuple(a_alpha),
        pair_attraction=pair,
        attraction_sums=sums,
        a_mix=a_mix,
        b_mix=b_mix,
        A=A,
        B=B,
    )


def complex_step_temperature(
    state: VerificationState, step: float = 1e-30
) -> ComplexAlgebraValues:
    """Return complex values for an isolated temperature complex-step."""

    return complex_algebra_values(
        state.components,
        tuple(complex(value) for value in state.fractions),
        complex(state.temperature_k, step),
        complex(state.pressure_pa),
    )


def complex_step_pressure(
    state: VerificationState, step: float = 1e-30
) -> ComplexAlgebraValues:
    """Return complex values for an isolated pressure complex-step."""

    return complex_algebra_values(
        state.components,
        tuple(complex(value) for value in state.fractions),
        complex(state.temperature_k),
        complex(state.pressure_pa, step),
    )


def complex_step_composition(
    state: VerificationState,
    independent_index: int,
    reference_index: int,
    step: float = 1e-30,
) -> ComplexAlgebraValues:
    """Return complex values for one tangent-simplex complex-step."""

    fractions = [complex(value) for value in state.fractions]
    fractions[independent_index] += complex(0.0, step)
    fractions[reference_index] -= complex(0.0, step)
    return complex_algebra_values(
        state.components,
        tuple(fractions),
        complex(state.temperature_k),
        complex(state.pressure_pa),
    )


def independent_cubic_partials(
    z: float, A: float, B: float
) -> tuple[float, float, float]:
    """Evaluate F_Z, F_A, and F_B independently from the published cubic."""

    return (
        3.0 * z * z + 2.0 * (B - 1.0) * z + A - 3.0 * B * B - 2.0 * B,
        z - B,
        z * z - (6.0 * B + 2.0) * z - A + 2.0 * B + 3.0 * B * B,
    )


def independent_log_fugacity_algebra(
    parameters: PengRobinsonMixtureParameters, z: float
) -> Vector:
    """Evaluate the published ln(phi) algebra without root validation.

    This verification-only evaluator permits fixed-Z adversarial decompositions.
    It uses direct logarithms rather than the production root-offset/log1p path.
    """

    A = parameters.A_mix
    B = parameters.B_mix
    a_mix = parameters.a_alpha_mix
    b_mix = parameters.b_mix
    sqrt_two = sqrt(2.0)
    logarithm_ratio = log((z + (1.0 + sqrt_two) * B) / (z + (1.0 - sqrt_two) * B))
    results: list[float] = []
    for component in parameters.component_parameters:
        attraction_sum = calculate_component_attraction_sum(
            component, parameters.component_parameters
        )
        b_ratio = component.b / b_mix
        results.append(
            b_ratio * (z - 1.0)
            - log(z - B)
            - A
            / (2.0 * sqrt_two * B)
            * (2.0 * attraction_sum / a_mix - b_ratio)
            * logarithm_ratio
        )
    return tuple(results)
