"""Deterministic property-based tests for thermodynamic invariants."""

from dataclasses import FrozenInstanceError
from itertools import permutations
from math import fsum, isfinite, log

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pvt_phase_simulator.eos.flash import (
    MATERIAL_BALANCE_TOLERANCE,
    FlashConvergenceStatus,
    FlashPhaseState,
    RachfordRiceStatus,
    calculate_phase_compositions,
    calculate_rachford_rice_value,
    calculate_two_phase_flash,
    solve_rachford_rice,
)
from pvt_phase_simulator.eos.mixing_rules import (
    BinaryInteractionPolicy,
    calculate_peng_robinson_mixture_parameters,
)
from pvt_phase_simulator.eos.mixture_fugacity import (
    calculate_mixture_fugacity_coefficients,
)
from pvt_phase_simulator.eos.peng_robinson import (
    SUPPLIED_ROOT_RESIDUAL_RELATIVE_TOLERANCE,
    MechanicalStabilityClassification,
    calculate_compressibility_roots,
    calculate_cubic_coefficients,
    calculate_cubic_residual,
    calculate_log_fugacity_coefficient,
    calculate_peng_robinson_parameters,
    validate_compressibility_root,
)
from pvt_phase_simulator.eos.phase_envelope import (
    EnvelopeBranchKind,
    EnvelopeContinuationSettings,
    EnvelopePointStatus,
    EnvelopeTerminationReason,
    trace_phase_envelope_branch,
)
from pvt_phase_simulator.eos.saturation_pressure import (
    FUGACITY_EQUILIBRIUM_TOLERANCE,
    TRIVIAL_LOG_K_TOLERANCE,
    SaturationKind,
    SaturationStatus,
    calculate_saturation_pressure,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    FluidMixture,
    MixtureComponent,
)

_COMPONENTS = (METHANE, ETHANE, PROPANE)
_BINARY_PERMUTATIONS = tuple(permutations(_COMPONENTS[:2]))
_TERNARY_PERMUTATIONS = tuple(permutations(_COMPONENTS))
_CHEAP_EXAMPLES = 60
_EOS_EXAMPLES = 36
_FLASH_EXAMPLES = 8
_SATURATION_EXAMPLES = 5
_ENVELOPE_EXAMPLES = 3


@st.composite
def _binary_fractions(draw: st.DrawFn) -> tuple[float, float]:
    """Return two active fractions with a stable normalized representation."""

    first = draw(
        st.floats(
            min_value=0.05,
            max_value=0.95,
            allow_nan=False,
            allow_infinity=False,
            width=64,
        )
    )
    return first, 1.0 - first


@st.composite
def _ternary_fractions(draw: st.DrawFn) -> tuple[float, float, float]:
    """Normalize bounded positive integer weights without extreme fractions."""

    weights = draw(
        st.tuples(
            st.integers(min_value=1, max_value=20),
            st.integers(min_value=1, max_value=20),
            st.integers(min_value=1, max_value=20),
        )
    )
    total = fsum(weights)
    first = weights[0] / total
    second = weights[1] / total
    return first, second, 1.0 - first - second


_TEMPERATURES = st.floats(
    min_value=150.0,
    max_value=450.0,
    allow_nan=False,
    allow_infinity=False,
    width=64,
)
_LOG_PRESSURES = st.floats(
    min_value=4.0,
    max_value=6.7,
    allow_nan=False,
    allow_infinity=False,
    width=64,
)


def _mixture(components: tuple, fractions: tuple[float, ...]) -> FluidMixture:
    return FluidMixture(
        tuple(
            MixtureComponent(component, fraction)
            for component, fraction in zip(components, fractions, strict=True)
        )
    )


def _by_name(values: tuple, names: tuple[str, ...]) -> dict[str, float]:
    return dict(zip(names, values, strict=True))


@given(fractions=_binary_fractions(), order=st.sampled_from(_BINARY_PERMUTATIONS))
@settings(max_examples=_CHEAP_EXAMPLES)
def test_generated_binary_mixture_preserves_model_invariants(
    fractions: tuple[float, float], order: tuple
) -> None:
    """Generated mixtures remain normalized, ordered, and immutable."""

    mixture = _mixture(order, fractions)

    assert fsum(item.mole_fraction for item in mixture.components) == pytest.approx(1.0)
    assert tuple(item.component for item in mixture.components) == order
    with pytest.raises(FrozenInstanceError):
        mixture.components = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        mixture.components[0].mole_fraction = 0.0  # type: ignore[misc]


@given(fractions=_ternary_fractions())
@settings(max_examples=_CHEAP_EXAMPLES)
def test_generated_ternary_mixture_is_normalized_and_ordered(
    fractions: tuple[float, float, float],
) -> None:
    """Safely normalized ternary fractions preserve their component order."""

    mixture = _mixture(_COMPONENTS, fractions)

    assert fsum(item.mole_fraction for item in mixture.components) == pytest.approx(1.0)
    assert tuple(item.component for item in mixture.components) == _COMPONENTS


@given(
    fractions=_ternary_fractions(),
    temperature_k=_TEMPERATURES,
    log_pressure=_LOG_PRESSURES,
    order=st.sampled_from(_TERNARY_PERMUTATIONS),
)
@settings(max_examples=_EOS_EXAMPLES)
def test_mixture_parameters_and_mixing_rules_are_permutation_equivariant(
    fractions: tuple[float, float, float],
    temperature_k: float,
    log_pressure: float,
    order: tuple,
) -> None:
    """Mixture parameters are finite and independent of aligned ordering."""

    pressure_pa = 10.0**log_pressure
    fractions_by_name = {
        component.name: fraction
        for component, fraction in zip(_COMPONENTS, fractions, strict=True)
    }
    canonical = _mixture(_COMPONENTS, fractions)
    reordered_fractions = tuple(fractions_by_name[item.name] for item in order)
    reordered = _mixture(order, reordered_fractions)
    zero_interactions = {
        (METHANE.name, ETHANE.name): 0.0,
        (ETHANE.name, METHANE.name): 0.0,
        (METHANE.name, PROPANE.name): 0.0,
        (PROPANE.name, METHANE.name): 0.0,
        (ETHANE.name, PROPANE.name): 0.0,
        (PROPANE.name, ETHANE.name): 0.0,
    }
    first = calculate_peng_robinson_mixture_parameters(
        canonical,
        temperature_k,
        pressure_pa,
        zero_interactions,
        BinaryInteractionPolicy.REQUIRE_ALL_PAIRS,
    )
    second = calculate_peng_robinson_mixture_parameters(
        reordered,
        temperature_k,
        pressure_pa,
        zero_interactions,
        BinaryInteractionPolicy.REQUIRE_ALL_PAIRS,
    )

    assert all(
        isfinite(value)
        for value in (first.a_alpha_mix, first.b_mix, first.A_mix, first.B_mix)
    )
    pure_b = tuple(item.b for item in first.component_parameters)
    assert min(pure_b) <= first.b_mix <= max(pure_b)
    assert second.a_alpha_mix == pytest.approx(first.a_alpha_mix, rel=2e-15)
    assert second.b_mix == pytest.approx(first.b_mix, rel=2e-15)
    assert second.A_mix == pytest.approx(first.A_mix, rel=3e-15)
    assert second.B_mix == pytest.approx(first.B_mix, rel=3e-15)


@given(
    component=st.sampled_from(_COMPONENTS),
    temperature_k=_TEMPERATURES,
    log_pressure=_LOG_PRESSURES,
)
@settings(max_examples=_EOS_EXAMPLES)
def test_pure_component_mixture_parameters_match_pure_pr(
    component, temperature_k: float, log_pressure: float
) -> None:
    """The one-component mixture limit reproduces pure PR parameters."""

    pressure_pa = 10.0**log_pressure
    mixture_parameters = calculate_peng_robinson_mixture_parameters(
        _mixture((component,), (1.0,)), temperature_k, pressure_pa
    )
    pure_parameters = calculate_peng_robinson_parameters(
        temperature_k,
        pressure_pa,
        component.critical_temperature_k,
        component.critical_pressure_pa,
        component.acentric_factor,
    )

    assert mixture_parameters.A_mix == pytest.approx(pure_parameters.A, rel=2e-15)
    assert mixture_parameters.B_mix == pytest.approx(pure_parameters.B, rel=2e-15)
    assert mixture_parameters.b_mix == pytest.approx(pure_parameters.b, rel=2e-15)
    assert mixture_parameters.a_alpha_mix == pytest.approx(
        pure_parameters.a * pure_parameters.alpha, rel=2e-15
    )


@given(
    fractions=_binary_fractions(),
    temperature_k=_TEMPERATURES,
    log_pressure=_LOG_PRESSURES,
)
@settings(max_examples=_EOS_EXAMPLES)
def test_all_accepted_mixture_roots_satisfy_the_pr_contract(
    fractions: tuple[float, float], temperature_k: float, log_pressure: float
) -> None:
    """Every returned root is finite, physical, and cubic-residual valid."""

    parameters = calculate_peng_robinson_mixture_parameters(
        _mixture(_COMPONENTS[:2], fractions), temperature_k, 10.0**log_pressure
    )
    coefficients = calculate_cubic_coefficients(parameters.A_mix, parameters.B_mix)
    roots = calculate_compressibility_roots(parameters.A_mix, parameters.B_mix)

    for root in roots:
        validate_compressibility_root(root, parameters.A_mix, parameters.B_mix)
        residual = abs(calculate_cubic_residual(root, coefficients))
        scale = max(
            1.0,
            abs(coefficients.z3 * root**3)
            + abs(coefficients.z2 * root**2)
            + abs(coefficients.z1 * root)
            + abs(coefficients.z0),
        )
        assert isfinite(root)
        assert root > parameters.B_mix
        assert residual <= SUPPLIED_ROOT_RESIDUAL_RELATIVE_TOLERANCE * scale


@given(
    fractions=_binary_fractions(),
    temperature_k=st.floats(
        min_value=220.0,
        max_value=420.0,
        allow_nan=False,
        allow_infinity=False,
    ),
    log_pressure=st.floats(
        min_value=4.0,
        max_value=6.3,
        allow_nan=False,
        allow_infinity=False,
    ),
)
@settings(max_examples=_EOS_EXAMPLES)
def test_mixture_fugacity_is_finite_and_permutation_equivariant(
    fractions: tuple[float, float], temperature_k: float, log_pressure: float
) -> None:
    """Component fugacities preserve identities under component permutation."""

    pressure_pa = 10.0**log_pressure
    canonical = _mixture(_COMPONENTS[:2], fractions)
    reordered = _mixture(tuple(reversed(_COMPONENTS[:2])), tuple(reversed(fractions)))
    first_parameters = calculate_peng_robinson_mixture_parameters(
        canonical, temperature_k, pressure_pa
    )
    second_parameters = calculate_peng_robinson_mixture_parameters(
        reordered, temperature_k, pressure_pa
    )
    first_root = max(
        calculate_compressibility_roots(first_parameters.A_mix, first_parameters.B_mix)
    )
    second_root = max(
        calculate_compressibility_roots(
            second_parameters.A_mix, second_parameters.B_mix
        )
    )
    first = calculate_mixture_fugacity_coefficients(first_parameters, first_root)
    second = calculate_mixture_fugacity_coefficients(second_parameters, second_root)
    first_by_name = {
        item.component_name: item.log_fugacity_coefficient for item in first
    }
    second_by_name = {
        item.component_name: item.log_fugacity_coefficient for item in second
    }

    assert tuple(item.component_name for item in first) == tuple(
        item.component.name for item in canonical.components
    )
    assert all(isfinite(item.log_fugacity_coefficient) for item in first)
    assert all(isfinite(item.fugacity_coefficient) for item in first)
    assert second_by_name == pytest.approx(first_by_name, rel=2e-11, abs=2e-12)


@given(
    component=st.sampled_from(_COMPONENTS),
    temperature_k=st.floats(
        min_value=220.0,
        max_value=420.0,
        allow_nan=False,
        allow_infinity=False,
    ),
    log_pressure=st.floats(
        min_value=4.0,
        max_value=6.3,
        allow_nan=False,
        allow_infinity=False,
    ),
)
@settings(max_examples=_EOS_EXAMPLES)
def test_pure_component_fugacity_matches_pure_pr(
    component, temperature_k: float, log_pressure: float
) -> None:
    """One-component mixture fugacity agrees with the pure PR expression."""

    parameters = calculate_peng_robinson_mixture_parameters(
        _mixture((component,), (1.0,)), temperature_k, 10.0**log_pressure
    )
    root = max(calculate_compressibility_roots(parameters.A_mix, parameters.B_mix))
    mixture_result = calculate_mixture_fugacity_coefficients(parameters, root)[0]
    pure_log_phi = calculate_log_fugacity_coefficient(
        root, parameters.A_mix, parameters.B_mix
    )

    assert mixture_result.log_fugacity_coefficient == pytest.approx(
        pure_log_phi, rel=2e-12, abs=2e-13
    )


_POSITIVE_K = st.floats(
    min_value=0.05,
    max_value=20.0,
    allow_nan=False,
    allow_infinity=False,
    width=64,
)
_ABOVE_ONE_K = st.floats(
    min_value=1.01,
    max_value=20.0,
    allow_nan=False,
    allow_infinity=False,
)
_BELOW_ONE_K = st.floats(
    min_value=0.05,
    max_value=0.99,
    allow_nan=False,
    allow_infinity=False,
)
_NEAR_ONE_K = st.floats(
    min_value=1e-10,
    max_value=1e-4,
    allow_nan=False,
    allow_infinity=False,
).flatmap(lambda offset: st.sampled_from((1.0 - offset, 1.0 + offset)))
_K_VALUE_SETS = st.one_of(
    st.tuples(_ABOVE_ONE_K, _ABOVE_ONE_K, _ABOVE_ONE_K),
    st.tuples(_BELOW_ONE_K, _BELOW_ONE_K, _BELOW_ONE_K),
    st.tuples(_ABOVE_ONE_K, _BELOW_ONE_K, _POSITIVE_K),
    st.tuples(_NEAR_ONE_K, _NEAR_ONE_K, _NEAR_ONE_K),
    st.sampled_from(((1e-6, 1.0, 1e6), (1e6, 1e-6, 2.0))),
)


@given(
    fractions=_ternary_fractions(),
    k_values=_K_VALUE_SETS,
)
@settings(max_examples=_CHEAP_EXAMPLES)
def test_rachford_rice_is_monotone_and_interior_solutions_close_balance(
    fractions: tuple[float, float, float], k_values: tuple[float, float, float]
) -> None:
    """Rachford–Rice is non-increasing and physical roots close all balances."""

    sample_values = tuple(
        calculate_rachford_rice_value(beta, fractions, k_values)
        for beta in (0.0, 0.25, 0.5, 0.75, 1.0)
    )
    assert all(
        later <= earlier + 2e-14
        for earlier, later in zip(sample_values, sample_values[1:], strict=False)
    )

    solution = solve_rachford_rice(fractions, k_values)
    if solution.status is not RachfordRiceStatus.TWO_PHASE_ROOT:
        return
    assert solution.beta is not None
    assert 0.0 < solution.beta < 1.0
    phases = calculate_phase_compositions(fractions, k_values, solution.beta)
    assert fsum(phases.liquid_composition) == pytest.approx(1.0, abs=1e-12)
    assert fsum(phases.vapor_composition) == pytest.approx(1.0, abs=1e-12)
    assert max(map(abs, phases.material_balance_residuals)) <= (
        MATERIAL_BALANCE_TOLERANCE
    )
    for liquid, vapor, k_value in zip(
        phases.liquid_composition,
        phases.vapor_composition,
        k_values,
        strict=True,
    ):
        assert vapor / liquid == pytest.approx(k_value, rel=2e-12)


_FLASH_CASES = (
    ((_COMPONENTS[0], _COMPONENTS[1]), (0.5, 0.5), 170.0, 100_000.0),
    ((_COMPONENTS[0], _COMPONENTS[1]), (0.7, 0.3), 300.0, 10_000_000.0),
    ((_COMPONENTS[0], _COMPONENTS[2]), (0.6, 0.4), 250.0, 3_000_000.0),
)


@given(case=st.sampled_from(_FLASH_CASES), reverse=st.booleans())
@settings(max_examples=_FLASH_EXAMPLES, suppress_health_check=(HealthCheck.too_slow,))
def test_flash_results_are_structured_deterministic_and_order_equivariant(
    case, reverse: bool
) -> None:
    """Valid generated flash states are deterministic and physically structured."""

    components, fractions, temperature_k, pressure_pa = case
    if reverse:
        components = tuple(reversed(components))
        fractions = tuple(reversed(fractions))
    mixture = _mixture(components, fractions)
    first = calculate_two_phase_flash(mixture, temperature_k, pressure_pa)
    second = calculate_two_phase_flash(mixture, temperature_k, pressure_pa)

    assert first == second
    assert isinstance(first.convergence_status, FlashConvergenceStatus)
    reference = calculate_two_phase_flash(
        _mixture(case[0], case[1]), temperature_k, pressure_pa
    )
    assert first.phase_state is reference.phase_state
    assert first.convergence_status is reference.convergence_status
    if (
        first.phase_state is FlashPhaseState.TWO_PHASE
        and reference.phase_state is FlashPhaseState.TWO_PHASE
    ):
        assert first.vapor_fraction == pytest.approx(
            reference.vapor_fraction, rel=2e-10, abs=2e-12
        )
        assert first.liquid_phase is not None and first.vapor_phase is not None
        assert reference.liquid_phase is not None and reference.vapor_phase is not None
        names = tuple(item.component.name for item in mixture.components)
        reference_names = tuple(
            item.component.name for item in reference.feed_mixture.components
        )
        for phase, reference_phase in (
            (first.liquid_phase, reference.liquid_phase),
            (first.vapor_phase, reference.vapor_phase),
        ):
            assert _by_name(phase.composition, names) == pytest.approx(
                _by_name(reference_phase.composition, reference_names),
                rel=2e-9,
                abs=2e-11,
            )
    if first.phase_state is not FlashPhaseState.TWO_PHASE:
        return
    assert first.vapor_fraction is not None
    assert first.liquid_phase is not None and first.vapor_phase is not None
    assert 0.0 < first.vapor_fraction < 1.0
    assert fsum(first.liquid_phase.composition) == pytest.approx(1.0, abs=1e-12)
    assert fsum(first.vapor_phase.composition) == pytest.approx(1.0, abs=1e-12)
    assert all(isfinite(value) and value > 0.0 for value in first.final_k_values or ())
    assert all(
        isfinite(value)
        for value in (
            first.liquid_phase.selected_compressibility_factor,
            first.vapor_phase.selected_compressibility_factor,
        )
    )
    assert (
        first.liquid_phase.mechanical_classification
        is MechanicalStabilityClassification.STABLE
    )
    assert (
        first.vapor_phase.mechanical_classification
        is MechanicalStabilityClassification.STABLE
    )
    assert max(map(abs, first.material_balance_residuals)) <= MATERIAL_BALANCE_TOLERANCE


@given(
    kind=st.sampled_from(tuple(SaturationKind)),
    temperature_k=st.sampled_from((190.0, 210.0, 230.0, 250.0, 270.0)),
)
@settings(
    max_examples=_SATURATION_EXAMPLES,
    suppress_health_check=(HealthCheck.too_slow,),
)
def test_saturation_results_are_deterministic_and_contract_valid(
    kind: SaturationKind, temperature_k: float
) -> None:
    """Saturation results are structured, deterministic, and valid if accepted."""

    mixture = _mixture(_COMPONENTS[:2], (0.5, 0.5))
    first = calculate_saturation_pressure(mixture, temperature_k, kind)
    second = calculate_saturation_pressure(mixture, temperature_k, kind)

    assert first == second
    assert isinstance(first.status, SaturationStatus)
    if first.status is not SaturationStatus.CONVERGED:
        return
    assert first.pressure_pa is not None and isfinite(first.pressure_pa)
    assert first.pressure_pa > 0.0
    assert fsum(first.incipient_composition) == pytest.approx(1.0, abs=1e-10)
    for fraction, k_value in zip(first.feed_composition, first.k_values, strict=True):
        if fraction > 0.0:
            assert isfinite(k_value) and k_value > 0.0
    assert max(abs(log(value)) for value in first.k_values) > (TRIVIAL_LOG_K_TOLERANCE)
    assert first.maximum_fugacity_equilibrium_residual is not None
    assert first.maximum_fugacity_equilibrium_residual <= FUGACITY_EQUILIBRIUM_TOLERANCE


@given(reverse=st.booleans(), kind=st.sampled_from(tuple(SaturationKind)))
@settings(max_examples=4, suppress_health_check=(HealthCheck.too_slow,))
def test_saturation_is_component_order_equivariant(
    reverse: bool, kind: SaturationKind
) -> None:
    """Reversing aligned components preserves a converged saturation state."""

    components = _COMPONENTS[:2]
    fractions = (0.5, 0.5)
    if reverse:
        components = tuple(reversed(components))
        fractions = tuple(reversed(fractions))
    result = calculate_saturation_pressure(_mixture(components, fractions), 220.0, kind)
    reference = calculate_saturation_pressure(
        _mixture(_COMPONENTS[:2], (0.5, 0.5)), 220.0, kind
    )

    assert result.status is reference.status
    if result.status is SaturationStatus.CONVERGED:
        assert result.pressure_pa == pytest.approx(reference.pressure_pa, rel=2e-10)
        result_by_name = _by_name(
            result.incipient_composition,
            tuple(item.component.name for item in result.feed_mixture.components),
        )
        reference_by_name = _by_name(
            reference.incipient_composition,
            tuple(item.component.name for item in reference.feed_mixture.components),
        )
        assert result_by_name == pytest.approx(reference_by_name, rel=2e-9, abs=2e-11)


@given(
    branch_kind=st.sampled_from(tuple(EnvelopeBranchKind)),
    direction=st.sampled_from((-1.0, 1.0)),
)
@settings(
    max_examples=_ENVELOPE_EXAMPLES,
    suppress_health_check=(HealthCheck.too_slow,),
)
def test_short_envelope_traces_are_deterministic_and_structurally_valid(
    branch_kind: EnvelopeBranchKind, direction: float
) -> None:
    """Short traces preserve ordering, point contracts, and termination semantics."""

    start_temperature_k = 220.0
    settings_value = EnvelopeContinuationSettings(
        target_temperature_k=start_temperature_k + direction * 5.0,
        initial_temperature_step_k=direction * 2.5,
        maximum_points=3,
    )
    mixture = _mixture(_COMPONENTS[:2], (0.5, 0.5))
    first = trace_phase_envelope_branch(
        mixture,
        branch_kind,
        settings_value,
        start_temperature_k=start_temperature_k,
    )
    second = trace_phase_envelope_branch(
        mixture,
        branch_kind,
        settings_value,
        start_temperature_k=start_temperature_k,
    )

    assert first == second
    assert isinstance(first.termination_reason, EnvelopeTerminationReason)
    assert first.termination_message
    assert len(first.points) <= settings_value.maximum_points
    temperatures = tuple(point.temperature_k for point in first.points)
    assert all(
        direction * (later - earlier) > 0.0
        for earlier, later in zip(temperatures, temperatures[1:], strict=False)
    )
    expected_names = tuple(item.component.name for item in mixture.components)
    for point in first.points:
        assert point.status is EnvelopePointStatus.CONVERGED
        assert point.pressure_pa is not None and isfinite(point.pressure_pa)
        assert point.pressure_pa > 0.0
        assert point.saturation_result.status is SaturationStatus.CONVERGED
        assert (
            tuple(
                item.component.name
                for item in point.saturation_result.feed_mixture.components
            )
            == expected_names
        )
    if first.termination_reason is EnvelopeTerminationReason.TARGET_REACHED:
        assert first.points
        assert first.points[-1].temperature_k == pytest.approx(
            settings_value.target_temperature_k,
            abs=1e-10,
        )
