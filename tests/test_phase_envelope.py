"""Tests for natural-temperature phase-envelope branch continuation."""

from dataclasses import FrozenInstanceError, replace
from math import exp, fsum, isfinite, log, log1p, sqrt
from time import perf_counter

import numpy as np
import pytest
from scipy.optimize import toms748

import pvt_phase_simulator.eos.phase_envelope as envelope_module
from pvt_phase_simulator.eos.flash import calculate_two_phase_flash
from pvt_phase_simulator.eos.mixing_rules import (
    calculate_peng_robinson_mixture_parameters,
)
from pvt_phase_simulator.eos.phase_envelope import (
    EnvelopeBranchKind,
    EnvelopeContinuationSettings,
    EnvelopeCorrectionSource,
    EnvelopePointStatus,
    EnvelopePrediction,
    EnvelopePredictionKind,
    EnvelopeTerminationReason,
    calculate_phase_envelope,
    correct_envelope_prediction,
    predict_envelope_state,
    trace_bubble_branch,
    trace_dew_branch,
)
from pvt_phase_simulator.eos.saturation_pressure import (
    TRIVIAL_STATE_DIAGNOSTIC_CODE,
    InnerSaturationStatus,
    SaturationKind,
    SaturationStatus,
    calculate_saturation_pressure,
    evaluate_saturation_pressure,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    Component,
    FluidMixture,
    MixtureComponent,
)


def _methane_ethane() -> FluidMixture:
    return FluidMixture((MixtureComponent(METHANE, 0.5), MixtureComponent(ETHANE, 0.5)))


def _methane_propane() -> FluidMixture:
    return FluidMixture(
        (MixtureComponent(METHANE, 0.6), MixtureComponent(PROPANE, 0.4))
    )


def _ternary() -> FluidMixture:
    return FluidMixture(
        (
            MixtureComponent(METHANE, 0.6),
            MixtureComponent(ETHANE, 0.3),
            MixtureComponent(PROPANE, 0.1),
        )
    )


def _settings(
    target: float = 220.0,
    step: float = 5.0,
    maximum_points: int = 8,
    **changes: object,
) -> EnvelopeContinuationSettings:
    values: dict[str, object] = {
        "target_temperature_k": target,
        "initial_temperature_step_k": step,
        "maximum_points": maximum_points,
    }
    values.update(changes)
    return EnvelopeContinuationSettings(**values)  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def binary_bubble() -> envelope_module.PhaseEnvelopeBranchResult:
    return trace_bubble_branch(_methane_ethane(), _settings(), 200.0)


@pytest.fixture(scope="module")
def binary_dew() -> envelope_module.PhaseEnvelopeBranchResult:
    return trace_dew_branch(_methane_ethane(), _settings(), 200.0)


@pytest.fixture(scope="module")
def methane_propane_bubble() -> envelope_module.PhaseEnvelopeBranchResult:
    return trace_bubble_branch(_methane_propane(), _settings(250.0, 5.0, 8), 230.0)


@pytest.fixture(scope="module")
def methane_propane_dew() -> envelope_module.PhaseEnvelopeBranchResult:
    return trace_dew_branch(_methane_propane(), _settings(250.0, 5.0, 8), 230.0)


@pytest.fixture(scope="module")
def ternary_bubble() -> envelope_module.PhaseEnvelopeBranchResult:
    return trace_bubble_branch(_ternary(), _settings(), 200.0)


def _independent_phase(
    components: tuple[Component, ...],
    composition: tuple[float, ...],
    temperature_k: float,
    pressure_pa: float,
    liquid: bool,
) -> tuple[float, tuple[float, ...]]:
    """Evaluate PR roots and fugacities from test-local equations.

    The reference cases use the project's documented zero binary-interaction
    assumption. Only immutable component property data are reused.
    """

    gas_constant = 8.31446261815324
    omega_a = 0.45724
    omega_b = 0.07780
    sqrt_two = sqrt(2.0)
    a_alpha = tuple(
        omega_a
        * gas_constant**2
        * component.critical_temperature_k**2
        / component.critical_pressure_pa
        * (
            1.0
            + (
                0.37464
                + 1.54226 * component.acentric_factor
                - 0.26992 * component.acentric_factor**2
            )
            * (1.0 - sqrt(temperature_k / component.critical_temperature_k))
        )
        ** 2
        for component in components
    )
    b_values = tuple(
        omega_b
        * gas_constant
        * component.critical_temperature_k
        / component.critical_pressure_pa
        for component in components
    )
    a_mix = fsum(
        composition[i] * composition[j] * sqrt(a_alpha[i] * a_alpha[j])
        for i in range(len(components))
        for j in range(len(components))
    )
    b_mix = fsum(
        fraction * b_value
        for fraction, b_value in zip(composition, b_values, strict=True)
    )
    dimensionless_a = a_mix * pressure_pa / (gas_constant**2 * temperature_k**2)
    dimensionless_b = b_mix * pressure_pa / (gas_constant * temperature_k)
    roots = np.roots(
        (
            1.0,
            dimensionless_b - 1.0,
            dimensionless_a - 3.0 * dimensionless_b**2 - 2.0 * dimensionless_b,
            -(
                dimensionless_a * dimensionless_b
                - dimensionless_b**2
                - dimensionless_b**3
            ),
        )
    )
    physical_roots = tuple(
        sorted(
            float(candidate.real)
            for candidate in roots
            if abs(float(candidate.imag)) <= 1e-9
            and float(candidate.real) > dimensionless_b
        )
    )
    if not physical_roots:
        raise ValueError("test-local PR calculation found no physical root")
    root = min(physical_roots) if liquid else max(physical_roots)
    logarithm_ratio = log1p((1.0 + sqrt_two) * dimensionless_b / root) - log1p(
        (1.0 - sqrt_two) * dimensionless_b / root
    )
    log_phi = tuple(
        b_values[i] / b_mix * (root - 1.0)
        - log(root - dimensionless_b)
        - dimensionless_a
        / (2.0 * sqrt_two * dimensionless_b)
        * (
            2.0
            * fsum(
                composition[j] * sqrt(a_alpha[i] * a_alpha[j])
                for j in range(len(components))
            )
            / a_mix
            - b_values[i] / b_mix
        )
        * logarithm_ratio
        for i in range(len(components))
    )
    return root, log_phi


def _independent_saturation(
    components: tuple[Component, ...],
    feed: tuple[float, ...],
    temperature_k: float,
    kind: SaturationKind,
    initial_log_k: tuple[float, ...] | None = None,
) -> tuple[float, tuple[float, ...], tuple[float, ...], float, float]:
    """Partially independent wide-search pressure/composition correction.

    Only immutable component property data are reused. PR mixing, cubic-root,
    fugacity, pressure-search, and composition-correction equations are
    implemented locally; Modules 8--9 and their solution seeds are not used.
    """

    def normalize(values: tuple[float, ...]) -> tuple[float, ...]:
        direction = 1.0 if kind is SaturationKind.BUBBLE_POINT else -1.0
        logs = tuple(
            log(fraction) + direction * value
            for fraction, value in zip(feed, values, strict=True)
            if fraction > 0.0
        )
        largest = max(logs)
        weights = tuple(
            0.0 if fraction == 0.0 else exp(log(fraction) + direction * value - largest)
            for fraction, value in zip(feed, values, strict=True)
        )
        total = fsum(weights)
        return tuple(value / total for value in weights)

    def objective(
        pressure_pa: float,
        details: bool = False,
    ) -> float | tuple[float, tuple[float, ...], tuple[float, ...], float, float]:
        values = initial_log_k
        if values is None:
            values = tuple(
                log(component.critical_pressure_pa / pressure_pa)
                + 5.373
                * (1.0 + component.acentric_factor)
                * (1.0 - component.critical_temperature_k / temperature_k)
                for component in components
            )
        parent_root, parent_phi = _independent_phase(
            components,
            feed,
            temperature_k,
            pressure_pa,
            kind is SaturationKind.BUBBLE_POINT,
        )
        incipient = feed
        incipient_root = parent_root
        for _ in range(400):
            incipient = normalize(values)
            incipient_root, incipient_phi = _independent_phase(
                components,
                incipient,
                temperature_k,
                pressure_pa,
                kind is SaturationKind.DEW_POINT,
            )
            liquid_phi, vapor_phi = (
                (parent_phi, incipient_phi)
                if kind is SaturationKind.BUBBLE_POINT
                else (incipient_phi, parent_phi)
            )
            updated = tuple(
                liquid - vapor
                for liquid, vapor in zip(liquid_phi, vapor_phi, strict=True)
            )
            if (
                max(abs(new - old) for new, old in zip(updated, values, strict=True))
                <= 1e-13
            ):
                values = updated
                break
            values = updated
        direction = 1.0 if kind is SaturationKind.BUBBLE_POINT else -1.0
        residual = (
            fsum(
                fraction * exp(direction * value)
                for fraction, value in zip(feed, values, strict=True)
            )
            - 1.0
        )
        if details:
            return residual, incipient, values, parent_root, incipient_root
        return residual

    minimum_pressure_pa = 1_000.0
    maximum_pressure_pa = 100_000_000.0
    search_points = 241
    lower_log = log(minimum_pressure_pa)
    upper_log = log(maximum_pressure_pa)
    pressures = tuple(
        exp(lower_log + index * (upper_log - lower_log) / (search_points - 1))
        for index in range(search_points)
    )
    brackets: list[tuple[float, float]] = []
    previous: tuple[float, float] | None = None
    for pressure_pa in pressures:
        try:
            residual = float(objective(pressure_pa))
        except (ArithmeticError, ValueError):
            previous = None
            continue
        if not isfinite(residual):
            previous = None
            continue
        if residual == 0.0:
            brackets.append((pressure_pa, pressure_pa))
        elif previous is not None and (
            previous[1] < 0.0 < residual or residual < 0.0 < previous[1]
        ):
            brackets.append((previous[0], pressure_pa))
        previous = pressure_pa, residual

    candidates: list[
        tuple[float, tuple[float, ...], tuple[float, ...], float, float]
    ] = []
    for lower, upper in brackets:
        pressure = (
            lower
            if lower == upper
            else toms748(
                lambda pressure_pa: float(objective(pressure_pa)),
                lower,
                upper,
                xtol=1e-7,
                rtol=1e-13,
            )
        )
        details = objective(pressure, True)
        if not isinstance(details, tuple):
            raise AssertionError("independent details are required")
        candidate = pressure, details[1], details[2], details[3], details[4]
        if max(abs(value) for value in candidate[2]) > 1e-7:
            candidates.append(candidate)
    if not candidates:
        raise AssertionError("independent wide search found no nontrivial saturation")
    selector = max if kind is SaturationKind.BUBBLE_POINT else min
    return selector(candidates, key=lambda candidate: candidate[0])


@pytest.mark.parametrize(
    "changes",
    [
        {"target_temperature_k": 0.0},
        {"target_temperature_k": float("nan")},
        {"initial_temperature_step_k": 0.0},
        {"initial_temperature_step_k": float("inf")},
        {"minimum_temperature_step_k": 3.0, "maximum_temperature_step_k": 2.0},
        {"initial_temperature_step_k": 0.1},
        {"maximum_points": 0},
        {"minimum_pressure_pa": 1.0e6, "maximum_pressure_pa": 1.0e6},
        {"local_expansion_factor": 1.0},
        {"easy_predictor_log_pressure_error": 0.0},
        {"easy_predictor_log_k_error": float("nan")},
        {"retry_step_reduction_factor": 0.0},
        {"retry_step_reduction_factor": 1.0},
        {"step_decrease_factor": 1.0},
        {"saturation_objective_tolerance": 1e-7},
        {"log_k_tolerance": 1e-9},
    ],
)
def test_invalid_settings_are_rejected(changes: dict[str, object]) -> None:
    values: dict[str, object] = {
        "target_temperature_k": 220.0,
        "initial_temperature_step_k": 5.0,
    }
    values.update(changes)
    with pytest.raises(ValueError):
        EnvelopeContinuationSettings(**values)  # type: ignore[arg-type]


def test_settings_are_immutable() -> None:
    settings = _settings()
    with pytest.raises(FrozenInstanceError):
        settings.maximum_points = 2  # type: ignore[misc]


def test_named_threshold_defaults_preserve_the_audited_policy() -> None:
    settings = _settings()
    assert settings.easy_predictor_log_pressure_error == 0.1
    assert settings.easy_predictor_log_k_error == 0.2
    assert settings.retry_step_reduction_factor == 0.5
    assert envelope_module.PHASE_COMPOSITION_DISTINGUISHABILITY_TOLERANCE == 1e-10
    assert envelope_module.PHASE_ROOT_DISTINGUISHABILITY_TOLERANCE == 1e-8
    assert envelope_module.CROSS_BRANCH_PRESSURE_RELATIVE_TOLERANCE == 0.02


def test_easy_predictor_threshold_changes_only_adaptive_step_policy() -> None:
    default = trace_bubble_branch(_methane_ethane(), _settings(220.0, 5.0, 4), 200.0)
    restrictive = trace_bubble_branch(
        _methane_ethane(),
        _settings(220.0, 5.0, 4, easy_predictor_log_pressure_error=1e-12),
        200.0,
    )
    assert default.points[:3] == restrictive.points[:3]
    assert (
        default.points[3].accepted_temperature_step_k
        == default.points[2].accepted_temperature_step_k
        * default.settings.step_increase_factor
    )
    assert (
        restrictive.points[3].accepted_temperature_step_k
        == restrictive.points[2].accepted_temperature_step_k
        * restrictive.settings.step_decrease_factor
    )


def test_result_models_are_immutable(
    binary_bubble: envelope_module.PhaseEnvelopeBranchResult,
) -> None:
    with pytest.raises(FrozenInstanceError):
        binary_bubble.termination_message = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        binary_bubble.points[0].accepted_temperature_step_k = 4.0  # type: ignore[misc]


@pytest.mark.parametrize("start", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_start_temperature_is_rejected(start: float) -> None:
    with pytest.raises(ValueError):
        trace_bubble_branch(_methane_ethane(), _settings(), start)


def test_wrong_continuation_direction_is_rejected() -> None:
    with pytest.raises(ValueError, match="away"):
        trace_bubble_branch(_methane_ethane(), _settings(step=-5.0), 200.0)


def test_descending_temperature_direction_is_preserved() -> None:
    result = trace_bubble_branch(_methane_ethane(), _settings(210.0, -5.0, 5), 220.0)
    temperatures = tuple(point.temperature_k for point in result.points)
    assert result.termination_reason is EnvelopeTerminationReason.TARGET_REACHED
    assert temperatures == tuple(sorted(temperatures, reverse=True))
    assert all(point.accepted_temperature_step_k < 0.0 for point in result.points[1:])


def test_feed_is_not_mutated(
    binary_bubble: envelope_module.PhaseEnvelopeBranchResult,
) -> None:
    mixture = _methane_ethane()
    original = mixture.components
    result = trace_bubble_branch(mixture, _settings(205.0, 5.0, 2), 200.0)
    assert mixture.components == original
    assert result.feed_mixture is mixture
    assert binary_bubble.feed_composition == (0.5, 0.5)


def test_module_8_generated_starts_are_used(
    binary_bubble: envelope_module.PhaseEnvelopeBranchResult,
    binary_dew: envelope_module.PhaseEnvelopeBranchResult,
) -> None:
    assert (
        binary_bubble.points[0].correction_source
        is EnvelopeCorrectionSource.STARTING_SATURATION
    )
    assert (
        binary_dew.points[0].correction_source
        is EnvelopeCorrectionSource.STARTING_SATURATION
    )
    assert binary_bubble.points[0].pressure_pa == pytest.approx(2_640_548.36913065)
    assert binary_dew.points[0].pressure_pa == pytest.approx(440_070.388255435)


def test_supplied_converged_start_is_used_without_mutation() -> None:
    mixture = _methane_ethane()
    start = calculate_saturation_pressure(mixture, 200.0, SaturationKind.BUBBLE_POINT)
    result = trace_bubble_branch(
        mixture, _settings(205.0, 5.0, 2), starting_result=start
    )
    assert result.points[0].saturation_result is start
    assert start.temperature_k == 200.0


def test_nonconverged_start_is_rejected() -> None:
    mixture = _methane_ethane()
    valid = calculate_saturation_pressure(mixture, 200.0, SaturationKind.BUBBLE_POINT)
    invalid = replace(valid, status=SaturationStatus.NOT_FOUND)
    with pytest.raises(ValueError, match="converged"):
        trace_bubble_branch(mixture, _settings(), starting_result=invalid)


def test_wrong_kind_start_is_rejected() -> None:
    mixture = _methane_ethane()
    dew = calculate_saturation_pressure(mixture, 200.0, SaturationKind.DEW_POINT)
    with pytest.raises(ValueError, match="kind"):
        trace_bubble_branch(mixture, _settings(), starting_result=dew)


def test_mismatched_start_composition_is_rejected() -> None:
    start = calculate_saturation_pressure(
        _methane_ethane(), 200.0, SaturationKind.BUBBLE_POINT
    )
    with pytest.raises(ValueError, match="composition"):
        trace_bubble_branch(_methane_propane(), _settings(), starting_result=start)


def test_mismatched_start_provenance_is_rejected() -> None:
    mixture = _methane_ethane()
    start = calculate_saturation_pressure(mixture, 200.0, SaturationKind.BUBBLE_POINT)
    interactions = {
        ("Methane", "Ethane"): 0.02,
        ("Ethane", "Methane"): 0.02,
    }
    with pytest.raises(ValueError, match="provenance"):
        trace_bubble_branch(
            mixture,
            _settings(),
            starting_result=start,
            binary_interactions=interactions,
        )


def test_first_predictor_copies_previous_state(
    binary_bubble: envelope_module.PhaseEnvelopeBranchResult,
) -> None:
    previous = binary_bubble.points[0]
    prediction = predict_envelope_state(previous, 201.0)
    assert prediction.kind is EnvelopePredictionKind.PREVIOUS_STATE
    assert prediction.log_pressure == log(previous.pressure_pa)
    assert prediction.log_k_values == previous.log_k_values
    assert (
        prediction.incipient_composition
        == previous.saturation_result.incipient_composition
    )


def test_secant_predictor_equations(
    binary_bubble: envelope_module.PhaseEnvelopeBranchResult,
) -> None:
    older, previous = binary_bubble.points[:2]
    prediction = predict_envelope_state(previous, 210.0, older)
    scale = (210.0 - previous.temperature_k) / (
        previous.temperature_k - older.temperature_k
    )
    assert prediction.kind is EnvelopePredictionKind.SECANT
    assert prediction.log_pressure == pytest.approx(
        log(previous.pressure_pa)
        + scale * (log(previous.pressure_pa) - log(older.pressure_pa))
    )
    assert prediction.log_k_values == pytest.approx(
        tuple(
            current + scale * (current - old)
            for current, old in zip(
                previous.log_k_values, older.log_k_values, strict=True
            )
        )
    )


def test_duplicate_temperature_predictor_falls_back(
    binary_bubble: envelope_module.PhaseEnvelopeBranchResult,
) -> None:
    previous = binary_bubble.points[1]
    duplicate_result = replace(
        binary_bubble.points[0].saturation_result,
        temperature_k=previous.temperature_k,
    )
    duplicate = replace(binary_bubble.points[0], saturation_result=duplicate_result)
    prediction = predict_envelope_state(previous, 210.0, duplicate)
    assert prediction.kind is EnvelopePredictionKind.PREVIOUS_STATE_FALLBACK
    assert prediction.diagnostics[0].code == "ENVELOPE_PREDICTOR_DUPLICATE_TEMPERATURE"


def test_nonfinite_secant_predictor_falls_back(
    binary_bubble: envelope_module.PhaseEnvelopeBranchResult,
) -> None:
    older, previous = binary_bubble.points[:2]
    extreme = replace(older, log_k_values=(-700.0, 700.0))
    prediction = predict_envelope_state(previous, 1.0e308, extreme)
    assert prediction.kind is EnvelopePredictionKind.PREVIOUS_STATE_FALLBACK
    assert all(isfinite(value) for value in prediction.log_k_values)


def test_local_continuation_seeded_correction(
    binary_bubble: envelope_module.PhaseEnvelopeBranchResult,
) -> None:
    previous = binary_bubble.points[0]
    prediction = predict_envelope_state(previous, 201.0)
    result, attempts = correct_envelope_prediction(
        _methane_ethane(),
        EnvelopeBranchKind.BUBBLE,
        prediction,
        1.0,
        _settings(201.0, 1.0, 2),
    )
    assert result is not None and result.status is SaturationStatus.CONVERGED
    assert attempts[-1].source is EnvelopeCorrectionSource.LOCAL
    assert (
        attempts[-1].saturation_result.evaluation_history[0].history[0].log_k_values
        == prediction.log_k_values
    )


def test_local_bracket_expansion_is_recorded(
    binary_bubble: envelope_module.PhaseEnvelopeBranchResult,
) -> None:
    second = binary_bubble.points[1]
    assert second.correction_source is EnvelopeCorrectionSource.EXPANDED_LOCAL
    assert len(second.correction_attempts) >= 2
    spans = tuple(
        attempt.log_pressure_half_span
        for attempt in second.correction_attempts
        if attempt.log_pressure_half_span is not None
    )
    assert spans == tuple(sorted(spans))


def test_global_fallback_occurs_only_after_local_failure(
    binary_bubble: envelope_module.PhaseEnvelopeBranchResult,
) -> None:
    prediction = predict_envelope_state(binary_bubble.points[0], 205.0)
    settings = _settings(
        205.0,
        5.0,
        2,
        local_log_pressure_half_span=0.001,
        maximum_local_expansions=0,
    )
    result, attempts = correct_envelope_prediction(
        _methane_ethane(),
        EnvelopeBranchKind.BUBBLE,
        prediction,
        5.0,
        settings,
    )
    assert result is not None
    assert tuple(item.source for item in attempts) == (
        EnvelopeCorrectionSource.LOCAL,
        EnvelopeCorrectionSource.GLOBAL_FALLBACK,
    )


def test_final_state_is_fresh_and_contains_no_stale_values(
    binary_bubble: envelope_module.PhaseEnvelopeBranchResult,
) -> None:
    point = binary_bubble.points[-1]
    result = point.saturation_result
    final = result.evaluation_history[-1]
    assert final.pressure_pa == point.pressure_pa
    assert final.k_values == result.k_values
    assert final.parent_phase is result.parent_phase
    assert final.incipient_phase is result.incipient_phase
    assert point.log_k_values == pytest.approx(
        tuple(log(value) for value in result.k_values)
    )


def test_unity_k_start_is_rejected_for_multicomponent() -> None:
    mixture = _methane_ethane()
    valid = calculate_saturation_pressure(mixture, 200.0, SaturationKind.BUBBLE_POINT)
    invalid = replace(valid, k_values=(1.0, 1.0))
    with pytest.raises(ValueError, match="unity-K"):
        trace_bubble_branch(mixture, _settings(), starting_result=invalid)


def test_former_methane_propane_false_dew_state_is_rejected() -> None:
    mixture = _methane_propane()
    parameters = calculate_peng_robinson_mixture_parameters(
        mixture, 250.0, 4_869_675.25165864
    )
    provenance = envelope_module.PhaseInteractionProvenance(
        parameters.binary_interaction_policy,
        parameters.binary_interactions,
        parameters.supplied_binary_interaction_pairs,
        parameters.defaulted_binary_interaction_pairs,
    )
    evaluation = evaluate_saturation_pressure(
        mixture,
        250.0,
        4_869_675.25165864,
        SaturationKind.DEW_POINT,
        provenance,
        initial_log_k_values=(0.0, 0.0),
    )
    assert evaluation.status is InnerSaturationStatus.FAILED
    assert evaluation.failure_reason is not None
    assert "trivial" in evaluation.failure_reason.lower()


def test_trivial_state_cannot_form_local_bracket() -> None:
    prediction = EnvelopePrediction(
        EnvelopePredictionKind.PREVIOUS_STATE,
        250.0,
        log(4_869_675.25165864),
        (0.0, 0.0),
        (0.6, 0.4),
        (),
    )
    result, attempts = correct_envelope_prediction(
        _methane_propane(),
        EnvelopeBranchKind.DEW,
        prediction,
        1.0,
        _settings(
            250.0,
            1.0,
            2,
            maximum_local_expansions=0,
            allow_global_fallback=False,
        ),
    )
    assert result is None
    assert attempts and all(
        item.status is not EnvelopePointStatus.CONVERGED for item in attempts
    )


def test_nonrepresentable_log_k_seed_is_preserved_as_numerical_failure() -> None:
    prediction = EnvelopePrediction(
        EnvelopePredictionKind.PREVIOUS_STATE,
        220.0,
        log(3_974_616.95899),
        (1_000.0, -1_000.0),
        (0.5, 0.5),
        (),
    )
    result, attempts = correct_envelope_prediction(
        _methane_ethane(),
        EnvelopeBranchKind.BUBBLE,
        prediction,
        1.0,
        _settings(220.0, 1.0, 2, allow_global_fallback=False),
    )
    assert result is None
    assert attempts
    assert all(item.saturation_result is None for item in attempts)
    assert all(item.status is EnvelopePointStatus.FAILED for item in attempts)
    assert all(
        "seeded correction failed" in (item.failure_reason or "") for item in attempts
    )


def test_numerical_corrector_failure_terminates_partial_branch(
    monkeypatch: pytest.MonkeyPatch,
    binary_bubble: envelope_module.PhaseEnvelopeBranchResult,
) -> None:
    def extreme_prediction(
        previous: object,
        target_temperature_k: float,
        two_points_back: object = None,
    ) -> EnvelopePrediction:
        return EnvelopePrediction(
            EnvelopePredictionKind.PREVIOUS_STATE,
            target_temperature_k,
            log(3_974_616.95899),
            (1_000.0, -1_000.0),
            (0.5, 0.5),
            (),
        )

    monkeypatch.setattr(envelope_module, "predict_envelope_state", extreme_prediction)
    result = trace_bubble_branch(
        _methane_ethane(),
        _settings(
            201.0,
            1.0,
            2,
            maximum_step_retries=0,
            allow_global_fallback=False,
        ),
        starting_result=binary_bubble.points[0].saturation_result,
    )
    assert result.termination_reason is EnvelopeTerminationReason.NUMERICAL_FAILURE
    assert len(result.points) == 1
    assert result.rejected_attempts


def test_pure_component_unity_k_start_is_allowed() -> None:
    mixture = FluidMixture((MixtureComponent(METHANE, 1.0),))
    start = calculate_saturation_pressure(mixture, 170.0, SaturationKind.BUBBLE_POINT)
    result = trace_bubble_branch(
        mixture,
        _settings(170.0, 1.0, 2),
        starting_result=start,
    )
    assert result.termination_reason is EnvelopeTerminationReason.TARGET_REACHED
    assert result.points[0].log_k_values == pytest.approx((0.0,), abs=1e-9)


@pytest.mark.parametrize(
    "fixture_name",
    [
        "binary_bubble",
        "binary_dew",
        "methane_propane_bubble",
        "methane_propane_dew",
        "ternary_bubble",
    ],
)
def test_reference_branches_reach_target(
    request: pytest.FixtureRequest,
    fixture_name: str,
) -> None:
    branch = request.getfixturevalue(fixture_name)
    assert branch.termination_reason is EnvelopeTerminationReason.TARGET_REACHED
    assert branch.points[-1].temperature_k == pytest.approx(
        branch.settings.target_temperature_k
    )
    assert all(point.status is EnvelopePointStatus.CONVERGED for point in branch.points)


@pytest.mark.parametrize("fixture_name", ["binary_bubble", "binary_dew"])
def test_points_are_ordered_unique_and_directional(
    request: pytest.FixtureRequest,
    fixture_name: str,
) -> None:
    branch = request.getfixturevalue(fixture_name)
    temperatures = tuple(point.temperature_k for point in branch.points)
    pairs = tuple((point.temperature_k, point.pressure_pa) for point in branch.points)
    assert temperatures == tuple(sorted(temperatures))
    assert len(temperatures) == len(set(temperatures))
    assert len(pairs) == len(set(pairs))
    assert all(point.accepted_temperature_step_k > 0.0 for point in branch.points[1:])


def test_branch_jump_is_rejected_and_step_reduced() -> None:
    settings = _settings(
        205.0,
        5.0,
        4,
        maximum_predictor_log_pressure_error=0.08,
    )
    result = trace_bubble_branch(_methane_ethane(), settings, 200.0)
    assert result.points[-1].temperature_k == pytest.approx(205.0)
    assert (
        result.points[1].accepted_temperature_step_k
        < settings.initial_temperature_step_k
    )
    assert result.rejected_attempts
    assert any(
        item.status is EnvelopePointStatus.REJECTED for item in result.rejected_attempts
    )


def test_adaptive_step_increases_after_easy_correction(
    binary_bubble: envelope_module.PhaseEnvelopeBranchResult,
) -> None:
    easy_point = binary_bubble.points[2]
    following_point = binary_bubble.points[3]
    assert easy_point.correction_source is EnvelopeCorrectionSource.LOCAL
    assert (
        easy_point.predictor_log_pressure_error
        < binary_bubble.settings.easy_predictor_log_pressure_error
    )
    assert (
        easy_point.predictor_log_k_error
        < binary_bubble.settings.easy_predictor_log_k_error
    )
    assert (
        following_point.accepted_temperature_step_k
        > easy_point.accepted_temperature_step_k
    )


def test_adaptive_step_decreases_after_expansion(
    binary_bubble: envelope_module.PhaseEnvelopeBranchResult,
) -> None:
    assert (
        binary_bubble.points[1].correction_source
        is EnvelopeCorrectionSource.EXPANDED_LOCAL
    )
    assert (
        binary_bubble.points[2].accepted_temperature_step_k
        < binary_bubble.points[1].accepted_temperature_step_k
    )


def test_maximum_step_is_respected() -> None:
    result = trace_bubble_branch(
        _methane_ethane(),
        _settings(215.0, 2.0, 10, maximum_temperature_step_k=3.0),
        200.0,
    )
    assert (
        max(abs(point.accepted_temperature_step_k) for point in result.points[1:])
        <= result.settings.maximum_temperature_step_k
    )


def test_minimum_step_terminates_after_branch_loss() -> None:
    result = trace_bubble_branch(
        _methane_ethane(),
        _settings(
            205.0,
            5.0,
            5,
            minimum_temperature_step_k=2.5,
            maximum_predictor_log_pressure_error=1e-6,
        ),
        200.0,
    )
    assert result.termination_reason is EnvelopeTerminationReason.BRANCH_LOST
    assert len(result.points) == 1
    assert result.rejected_attempts


def test_minimum_step_reached_without_branch_or_trivial_evidence() -> None:
    """Plain corrector failure should retain the minimum-step fallback reason."""

    result = trace_bubble_branch(
        _methane_ethane(),
        _settings(
            205.0,
            5.0,
            6,
            allow_global_fallback=False,
            local_log_pressure_half_span=1e-9,
            maximum_local_expansions=0,
        ),
        200.0,
    )
    assert result.termination_reason is EnvelopeTerminationReason.MINIMUM_STEP_REACHED
    assert len(result.points) == 1
    assert result.rejected_attempts
    assert not any(
        attempt.status is EnvelopePointStatus.REJECTED
        for attempt in result.rejected_attempts
    )
    assert all(
        attempt.saturation_result is not None for attempt in result.rejected_attempts
    )
    assert not any(
        diagnostic.code == TRIVIAL_STATE_DIAGNOSTIC_CODE
        for attempt in result.rejected_attempts
        for diagnostic in attempt.diagnostics
    )


def test_retry_limit_is_respected() -> None:
    result = trace_bubble_branch(
        _methane_ethane(),
        _settings(
            205.0,
            5.0,
            5,
            maximum_step_retries=0,
            maximum_predictor_log_pressure_error=1e-6,
        ),
        200.0,
    )
    assert len(result.points) == 1
    assert result.rejected_attempts
    # Every attempt converged and was rejected only by the branch-identity
    # thresholds, so the honest reason is branch loss. Which limit ended the
    # retry loop must not change that classification.
    assert result.termination_reason is EnvelopeTerminationReason.BRANCH_LOST
    assert all(
        item.status is EnvelopePointStatus.REJECTED for item in result.rejected_attempts
    )


def test_retry_and_minimum_step_exits_agree_on_branch_loss() -> None:
    """The retry counter and the minimum step must classify the same evidence."""

    common = {"maximum_predictor_log_pressure_error": 1e-6}
    by_minimum_step = trace_bubble_branch(
        _methane_ethane(),
        _settings(205.0, 5.0, 5, minimum_temperature_step_k=2.5, **common),
        200.0,
    )
    by_retry_counter = trace_bubble_branch(
        _methane_ethane(),
        _settings(
            205.0,
            5.0,
            5,
            minimum_temperature_step_k=0.001,
            maximum_step_retries=3,
            **common,
        ),
        200.0,
    )
    assert by_minimum_step.termination_reason is EnvelopeTerminationReason.BRANCH_LOST
    assert by_retry_counter.termination_reason is EnvelopeTerminationReason.BRANCH_LOST
    assert by_retry_counter.termination_reason is by_minimum_step.termination_reason


def test_corrector_failure_without_branch_rejection_is_still_reported() -> None:
    """A genuine corrector failure must not be relabelled as branch loss."""

    start = calculate_saturation_pressure(
        _methane_ethane(), 200.0, SaturationKind.BUBBLE_POINT
    )
    result = trace_bubble_branch(
        _methane_ethane(),
        _settings(
            205.0,
            5.0,
            4,
            minimum_pressure_pa=2_600_000.0,
            maximum_pressure_pa=2_700_000.0,
            allow_global_fallback=False,
            maximum_step_retries=2,
            minimum_temperature_step_k=0.001,
            maximum_local_expansions=0,
            local_log_pressure_half_span=0.0005,
        ),
        starting_result=start,
    )
    assert result.termination_reason is EnvelopeTerminationReason.CORRECTOR_FAILED
    assert len(result.points) == 1
    assert result.rejected_attempts
    assert not any(
        item.status is EnvelopePointStatus.REJECTED for item in result.rejected_attempts
    )


@pytest.mark.parametrize(
    ("attribute", "code"),
    [
        ("near_critical_root_warning", "ENVELOPE_NEAR_CRITICAL_ROOTS"),
        ("near_critical_composition_warning", "ENVELOPE_NEAR_CRITICAL_COMPOSITION"),
        ("near_critical_log_k_warning", "ENVELOPE_NEAR_CRITICAL_LOG_K"),
    ],
)
def test_near_critical_warning_metrics(
    attribute: str,
    code: str,
) -> None:
    settings = _settings(201.0, 1.0, 2, **{attribute: 100.0})
    result = trace_bubble_branch(_methane_ethane(), settings, 200.0)
    assert any(item.code == code for item in result.diagnostics)


@pytest.mark.parametrize(
    ("start", "target", "step"),
    [(150.0, 175.0, 5.0), (175.0, 150.0, -5.0)],
)
def test_pure_component_continuation_is_not_falsely_near_critical(
    start: float,
    target: float,
    step: float,
) -> None:
    """A pure component has x = y and K = 1 at every saturation temperature.

    Those two near-critical indicators are therefore identically degenerate
    and must not be counted, exactly as the unity-K rule already exempts them.
    Only root separation carries near-critical information here.
    """

    mixture = FluidMixture((MixtureComponent(METHANE, 1.0),))
    result = trace_bubble_branch(mixture, _settings(target, step, 10), start)
    assert result.termination_reason is EnvelopeTerminationReason.TARGET_REACHED
    assert len(result.points) > 2
    assert result.points[-1].temperature_k == pytest.approx(target)
    assert all(point.composition_separation == 0.0 for point in result.points)
    assert all(point.maximum_active_log_k < 1e-8 for point in result.points)
    assert all(point.root_separation > 0.1 for point in result.points)
    assert not any(
        item.code
        in {"ENVELOPE_NEAR_CRITICAL_COMPOSITION", "ENVELOPE_NEAR_CRITICAL_LOG_K"}
        for item in result.diagnostics
    )


def test_single_active_component_is_not_falsely_near_critical() -> None:
    mixture = FluidMixture(
        (MixtureComponent(METHANE, 1.0), MixtureComponent(ETHANE, 0.0))
    )
    result = trace_bubble_branch(mixture, _settings(170.0, 5.0, 8), 150.0)
    assert result.termination_reason is EnvelopeTerminationReason.TARGET_REACHED
    assert result.points[-1].temperature_k == pytest.approx(170.0)


def test_pure_component_near_critical_still_uses_root_separation() -> None:
    """The one meaningful pure-component indicator must still terminate alone."""

    mixture = FluidMixture((MixtureComponent(METHANE, 1.0),))
    result = trace_bubble_branch(
        mixture,
        _settings(
            175.0,
            5.0,
            8,
            near_critical_root_stop=1.0,
            near_critical_root_warning=1.0,
        ),
        150.0,
    )
    assert result.termination_reason is EnvelopeTerminationReason.NEAR_CRITICAL
    assert any(
        item.code == "ENVELOPE_NEAR_CRITICAL_ROOTS" for item in result.diagnostics
    )


def test_repeated_trivial_collapse_terminates_as_near_critical() -> None:
    """Trivial collapse is recorded as a diagnostic, not in the failure reason.

    Module 8 reports its own bracket failure at branch level, so the tracer
    must read the diagnostic to see that the inner solve kept returning the
    trivial parent phase.
    """

    result = trace_bubble_branch(
        _methane_ethane(),
        _settings(
            300.0,
            2.5,
            2,
            allow_global_fallback=False,
            maximum_local_expansions=0,
            maximum_step_retries=1,
        ),
        255.0,
    )
    assert result.termination_reason is EnvelopeTerminationReason.NEAR_CRITICAL
    assert "not an exact critical point" in result.termination_message
    assert len(result.points) == 1
    assert result.rejected_attempts
    assert all(
        any(item.code == "SATURATION_TRIVIAL_STATE" for item in attempt.diagnostics)
        for attempt in result.rejected_attempts
    )
    assert not any(
        attempt.failure_reason is not None
        and "trivial" in attempt.failure_reason.lower()
        for attempt in result.rejected_attempts
    )


def test_near_critical_termination_is_honest() -> None:
    settings = _settings(
        205.0,
        1.0,
        5,
        near_critical_composition_stop=100.0,
        near_critical_log_k_stop=100.0,
        near_critical_root_stop=100.0,
        near_critical_composition_warning=101.0,
        near_critical_log_k_warning=101.0,
        near_critical_root_warning=101.0,
    )
    result = trace_bubble_branch(_methane_ethane(), settings, 200.0)
    assert result.termination_reason is EnvelopeTerminationReason.NEAR_CRITICAL
    assert "not an exact critical point" in result.termination_message


@pytest.mark.parametrize(
    ("fixture_name", "kind"),
    [
        ("binary_bubble", SaturationKind.BUBBLE_POINT),
        ("binary_dew", SaturationKind.DEW_POINT),
        ("methane_propane_bubble", SaturationKind.BUBBLE_POINT),
        ("methane_propane_dew", SaturationKind.DEW_POINT),
    ],
)
def test_module_8_agrees_at_envelope_endpoint(
    request: pytest.FixtureRequest,
    fixture_name: str,
    kind: SaturationKind,
) -> None:
    branch = request.getfixturevalue(fixture_name)
    point = branch.points[-1]
    isolated = calculate_saturation_pressure(
        branch.feed_mixture, point.temperature_k, kind
    )
    assert isolated.status is SaturationStatus.CONVERGED
    assert point.pressure_pa == pytest.approx(isolated.pressure_pa, rel=2e-11)
    assert point.saturation_result.incipient_composition == pytest.approx(
        isolated.incipient_composition, abs=2e-10
    )
    assert point.saturation_result.k_values == pytest.approx(
        isolated.k_values, rel=4e-10
    )
    assert (
        point.saturation_result.parent_phase is not None
        and isolated.parent_phase is not None
    )
    assert (
        point.saturation_result.parent_phase.selected_compressibility_factor
        == pytest.approx(
            isolated.parent_phase.selected_compressibility_factor, abs=2e-10
        )
    )


def test_seeded_continuation_path_can_succeed_without_global_fallback(
    binary_bubble: envelope_module.PhaseEnvelopeBranchResult,
) -> None:
    assert all(
        point.correction_source is not EnvelopeCorrectionSource.GLOBAL_FALLBACK
        for point in binary_bubble.points[1:]
    )


def test_continuation_reaches_a_state_isolated_module_8_cannot_find() -> None:
    """A real continuation-only success, with no monkeypatching.

    At 250 K the isolated Wilson-seeded Module 8 search collapses to the
    trivial solution across its grid and reports NOT_FOUND. The continuation
    seed keeps the inner iteration on the nontrivial branch. The expected
    pressure comes from an independent solver that shares no code with
    Module 8 or Module 9 (audit/independent_phase_envelope_reference.py).
    """

    mixture = _methane_ethane()
    isolated = calculate_saturation_pressure(
        mixture, 250.0, SaturationKind.BUBBLE_POINT
    )
    assert isolated.status is SaturationStatus.NOT_FOUND
    assert isolated.pressure_pa is None

    result = trace_bubble_branch(mixture, _settings(250.0, 5.0, 6), 240.0)
    assert result.termination_reason is EnvelopeTerminationReason.TARGET_REACHED
    point = result.points[-1]
    assert point.temperature_k == pytest.approx(250.0)
    assert point.pressure_pa == pytest.approx(6_172_720.661334422, rel=1e-11)
    assert point.maximum_active_log_k > 1e-8
    assert point.root_separation > 1e-8
    assert point.composition_separation > 1e-8


def test_ternary_continuation_reaches_an_isolated_not_found_state() -> None:
    mixture = _ternary()
    isolated = calculate_saturation_pressure(
        mixture, 230.0, SaturationKind.BUBBLE_POINT
    )
    assert isolated.status is SaturationStatus.NOT_FOUND

    result = trace_bubble_branch(mixture, _settings(230.0, 5.0, 6), 220.0)
    assert result.termination_reason is EnvelopeTerminationReason.TARGET_REACHED
    point = result.points[-1]
    assert point.temperature_k == pytest.approx(230.0)
    assert point.pressure_pa == pytest.approx(5_626_462.905554884, rel=1e-11)
    assert point.maximum_active_log_k > 1e-8


def test_forward_and_reverse_traces_agree_at_shared_temperatures() -> None:
    """Deterministic continuation must not depend on the direction travelled."""

    mixture = _methane_ethane()
    forward = trace_bubble_branch(mixture, _settings(210.0, 5.0, 6), 200.0)
    reverse = trace_bubble_branch(mixture, _settings(200.0, -5.0, 6), 210.0)
    forward_points = {round(item.temperature_k, 9): item for item in forward.points}
    reverse_points = {round(item.temperature_k, 9): item for item in reverse.points}
    shared = sorted(set(forward_points) & set(reverse_points))
    assert len(shared) >= 3
    for temperature in shared:
        ahead = forward_points[temperature]
        behind = reverse_points[temperature]
        assert ahead.pressure_pa == pytest.approx(behind.pressure_pa, rel=1e-11)
        assert ahead.saturation_result.incipient_composition == pytest.approx(
            behind.saturation_result.incipient_composition, abs=1e-10
        )
        assert ahead.log_k_values == pytest.approx(behind.log_k_values, abs=1e-9)


@pytest.mark.parametrize("step", [2.5, 5.0, 10.0])
def test_initial_step_size_does_not_change_the_target_state(step: float) -> None:
    """Only the path may depend on the initial step, never the final state."""

    result = trace_bubble_branch(
        _methane_ethane(),
        _settings(220.0, step, 20, maximum_temperature_step_k=10.0),
        200.0,
    )
    assert result.termination_reason is EnvelopeTerminationReason.TARGET_REACHED
    point = result.points[-1]
    assert point.temperature_k == pytest.approx(220.0)
    assert point.pressure_pa == pytest.approx(3_974_616.958989909, rel=1e-11)
    assert point.saturation_result.incipient_composition == pytest.approx(
        (0.848549034, 0.151450966), abs=1e-9
    )


def test_local_pressure_grid_is_symmetric_around_the_prediction(
    binary_bubble: envelope_module.PhaseEnvelopeBranchResult,
) -> None:
    """The unclipped local window is log-symmetric and samples the prediction."""

    prediction = predict_envelope_state(binary_bubble.points[0], 201.0)
    settings = _settings(201.0, 1.0, 2)
    result, attempts = correct_envelope_prediction(
        _methane_ethane(),
        EnvelopeBranchKind.BUBBLE,
        prediction,
        1.0,
        settings,
    )
    assert result is not None
    lower, upper = attempts[0].pressure_bounds_pa
    half = settings.local_log_pressure_half_span
    assert log(lower) == pytest.approx(prediction.log_pressure - half, abs=1e-12)
    assert log(upper) == pytest.approx(prediction.log_pressure + half, abs=1e-12)
    evaluated = tuple(
        item.pressure_pa for item in attempts[0].saturation_result.evaluation_history
    )
    assert any(
        log(value) == pytest.approx(prediction.log_pressure, abs=1e-12)
        for value in evaluated
    )
    scan = sorted({value for value in evaluated if lower <= value <= upper})
    assert len(scan) >= 5


def test_seeded_continuation_survives_an_unavailable_isolated_path(
    monkeypatch: pytest.MonkeyPatch,
    binary_bubble: envelope_module.PhaseEnvelopeBranchResult,
) -> None:
    """A continuation seed remains usable when the unseeded path is unavailable."""

    original = envelope_module.calculate_saturation_pressure
    unavailable = replace(
        binary_bubble.points[0].saturation_result,
        status=SaturationStatus.NOT_FOUND,
        pressure_pa=None,
        failure_reason="controlled isolated-search bracket failure",
    )

    def isolated_unavailable(*args: object, **kwargs: object) -> object:
        if kwargs.get("initial_log_k_values") is None:
            return unavailable
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        envelope_module, "calculate_saturation_pressure", isolated_unavailable
    )
    result = trace_bubble_branch(
        _methane_ethane(),
        _settings(201.0, 1.0, 2, allow_global_fallback=False),
        starting_result=binary_bubble.points[0].saturation_result,
    )
    assert result.termination_reason is EnvelopeTerminationReason.TARGET_REACHED
    assert result.points[-1].temperature_k == 201.0


def test_module_7_near_bubble_endpoint(
    binary_bubble: envelope_module.PhaseEnvelopeBranchResult,
) -> None:
    point = binary_bubble.points[-1]
    flash = calculate_two_phase_flash(
        binary_bubble.feed_mixture, point.temperature_k, point.pressure_pa * 0.999
    )
    assert flash.vapor_fraction is not None and 0.0 < flash.vapor_fraction < 0.003
    assert flash.liquid_phase is not None and flash.vapor_phase is not None
    assert flash.liquid_phase.composition == pytest.approx((0.5, 0.5), abs=7e-4)
    assert flash.vapor_phase.composition == pytest.approx(
        point.saturation_result.incipient_composition, abs=2e-4
    )


def test_module_7_near_dew_endpoint(
    binary_dew: envelope_module.PhaseEnvelopeBranchResult,
) -> None:
    point = binary_dew.points[-1]
    flash = calculate_two_phase_flash(
        binary_dew.feed_mixture, point.temperature_k, point.pressure_pa * 1.001
    )
    assert flash.vapor_fraction is not None and 0.997 < flash.vapor_fraction < 1.0
    assert flash.liquid_phase is not None and flash.vapor_phase is not None
    assert flash.vapor_phase.composition == pytest.approx((0.5, 0.5), abs=7e-4)
    assert flash.liquid_phase.composition == pytest.approx(
        point.saturation_result.incipient_composition, abs=2e-4
    )


@pytest.mark.parametrize("temperature", [200.0, 220.0])
def test_bubble_not_below_dew_for_binary_reference(
    binary_bubble: envelope_module.PhaseEnvelopeBranchResult,
    binary_dew: envelope_module.PhaseEnvelopeBranchResult,
    temperature: float,
) -> None:
    bubble = next(
        point for point in binary_bubble.points if point.temperature_k == temperature
    )
    dew = next(
        point for point in binary_dew.points if point.temperature_k == temperature
    )
    assert bubble.pressure_pa >= dew.pressure_pa


@pytest.mark.parametrize(
    ("fixture_name", "point_index", "components", "feed", "kind"),
    [
        (
            "binary_bubble",
            0,
            (METHANE, ETHANE),
            (0.5, 0.5),
            SaturationKind.BUBBLE_POINT,
        ),
        (
            "binary_bubble",
            2,
            (METHANE, ETHANE),
            (0.5, 0.5),
            SaturationKind.BUBBLE_POINT,
        ),
        (
            "binary_bubble",
            -1,
            (METHANE, ETHANE),
            (0.5, 0.5),
            SaturationKind.BUBBLE_POINT,
        ),
        (
            "binary_dew",
            0,
            (METHANE, ETHANE),
            (0.5, 0.5),
            SaturationKind.DEW_POINT,
        ),
        (
            "binary_dew",
            2,
            (METHANE, ETHANE),
            (0.5, 0.5),
            SaturationKind.DEW_POINT,
        ),
        (
            "binary_dew",
            -1,
            (METHANE, ETHANE),
            (0.5, 0.5),
            SaturationKind.DEW_POINT,
        ),
        (
            "methane_propane_bubble",
            0,
            (METHANE, PROPANE),
            (0.6, 0.4),
            SaturationKind.BUBBLE_POINT,
        ),
        (
            "methane_propane_bubble",
            2,
            (METHANE, PROPANE),
            (0.6, 0.4),
            SaturationKind.BUBBLE_POINT,
        ),
        (
            "methane_propane_bubble",
            -1,
            (METHANE, PROPANE),
            (0.6, 0.4),
            SaturationKind.BUBBLE_POINT,
        ),
        (
            "methane_propane_dew",
            0,
            (METHANE, PROPANE),
            (0.6, 0.4),
            SaturationKind.DEW_POINT,
        ),
        (
            "methane_propane_dew",
            2,
            (METHANE, PROPANE),
            (0.6, 0.4),
            SaturationKind.DEW_POINT,
        ),
        (
            "methane_propane_dew",
            -1,
            (METHANE, PROPANE),
            (0.6, 0.4),
            SaturationKind.DEW_POINT,
        ),
        (
            "ternary_bubble",
            0,
            (METHANE, ETHANE, PROPANE),
            (0.6, 0.3, 0.1),
            SaturationKind.BUBBLE_POINT,
        ),
        (
            "ternary_bubble",
            2,
            (METHANE, ETHANE, PROPANE),
            (0.6, 0.3, 0.1),
            SaturationKind.BUBBLE_POINT,
        ),
        (
            "ternary_bubble",
            -1,
            (METHANE, ETHANE, PROPANE),
            (0.6, 0.3, 0.1),
            SaturationKind.BUBBLE_POINT,
        ),
    ],
)
def test_independent_endpoint_reference(
    request: pytest.FixtureRequest,
    fixture_name: str,
    point_index: int,
    components: tuple[Component, ...],
    feed: tuple[float, ...],
    kind: SaturationKind,
) -> None:
    branch = request.getfixturevalue(fixture_name)
    point = branch.points[point_index]
    independent = _independent_saturation(
        components,
        feed,
        point.temperature_k,
        kind,
    )
    assert point.pressure_pa == pytest.approx(independent[0], abs=5e-5)
    assert point.saturation_result.incipient_composition == pytest.approx(
        independent[1], abs=4e-10
    )
    assert point.log_k_values == pytest.approx(independent[2], abs=4e-10)
    assert point.saturation_result.parent_phase is not None
    assert point.saturation_result.incipient_phase is not None
    assert (
        point.saturation_result.parent_phase.selected_compressibility_factor
        == pytest.approx(independent[3], abs=4e-10)
    )
    assert (
        point.saturation_result.incipient_phase.selected_compressibility_factor
        == pytest.approx(independent[4], abs=4e-10)
    )


def test_combined_manager_preserves_independent_branches() -> None:
    result = calculate_phase_envelope(
        _methane_ethane(),
        _settings(205.0, 5.0, 2),
        _settings(205.0, 5.0, 2),
        200.0,
        200.0,
    )
    assert result.bubble_branch.branch_kind is EnvelopeBranchKind.BUBBLE
    assert result.dew_branch.branch_kind is EnvelopeBranchKind.DEW
    assert result.bubble_branch.feed_mixture is result.feed_mixture
    assert result.dew_branch.feed_mixture is result.feed_mixture
    assert result.matched_temperature_pressure_separations
    assert all(
        value > 0.0 for _, value in result.matched_temperature_pressure_separations
    )


def test_local_and_global_bracket_failures_are_preserved() -> None:
    point = trace_bubble_branch(
        _methane_ethane(), _settings(200.0, 1.0, 2), 200.0
    ).points[0]
    prediction = predict_envelope_state(point, 201.0)
    result, attempts = correct_envelope_prediction(
        _methane_ethane(),
        EnvelopeBranchKind.BUBBLE,
        prediction,
        1.0,
        _settings(
            201.0,
            1.0,
            2,
            minimum_pressure_pa=1_000.0,
            maximum_pressure_pa=10_000.0,
            maximum_local_expansions=1,
        ),
    )
    assert result is None
    assert attempts == ()  # predicted pressure is outside validity bounds


def test_in_bounds_local_and_global_failures_are_both_preserved(
    binary_bubble: envelope_module.PhaseEnvelopeBranchResult,
) -> None:
    prediction = predict_envelope_state(binary_bubble.points[0], 205.0)
    result, attempts = correct_envelope_prediction(
        _methane_ethane(),
        EnvelopeBranchKind.BUBBLE,
        prediction,
        5.0,
        _settings(
            205.0,
            5.0,
            2,
            minimum_pressure_pa=2_500_000.0,
            maximum_pressure_pa=2_700_000.0,
            maximum_local_expansions=1,
        ),
    )
    assert result is None
    assert attempts[-1].source is EnvelopeCorrectionSource.GLOBAL_FALLBACK
    assert all(not item.accepted for item in attempts)


@pytest.mark.parametrize(
    "failure_reason",
    [
        "distinct roots disappeared",
        "only marginal roots are available",
        "numerical overflow in fugacity evaluation",
    ],
)
def test_corrector_preserves_root_and_numerical_failures(
    monkeypatch: pytest.MonkeyPatch,
    binary_bubble: envelope_module.PhaseEnvelopeBranchResult,
    failure_reason: str,
) -> None:
    valid = binary_bubble.points[0].saturation_result
    failed = replace(
        valid,
        status=SaturationStatus.INCONCLUSIVE,
        pressure_pa=None,
        failure_reason=failure_reason,
    )
    monkeypatch.setattr(
        envelope_module,
        "calculate_saturation_pressure",
        lambda *args, **kwargs: failed,
    )
    prediction = predict_envelope_state(binary_bubble.points[0], 201.0)
    result, attempts = correct_envelope_prediction(
        _methane_ethane(),
        EnvelopeBranchKind.BUBBLE,
        prediction,
        1.0,
        _settings(201.0, 1.0, 2, allow_global_fallback=False),
    )
    assert result is None
    assert attempts
    assert all(item.failure_reason == failure_reason for item in attempts)


def test_pressure_bounds_termination_preserves_partial_branch() -> None:
    start = calculate_saturation_pressure(
        _methane_ethane(), 200.0, SaturationKind.BUBBLE_POINT
    )
    result = trace_bubble_branch(
        _methane_ethane(),
        _settings(
            205.0,
            5.0,
            4,
            minimum_pressure_pa=1_000.0,
            maximum_pressure_pa=2_700_000.0,
        ),
        starting_result=start,
    )
    assert result.termination_reason is EnvelopeTerminationReason.PRESSURE_OUT_OF_BOUNDS
    assert 1 <= len(result.points) < result.settings.maximum_points
    assert all(point.pressure_pa <= 2_700_000.0 for point in result.points)


def test_maximum_points_termination() -> None:
    result = trace_bubble_branch(_methane_ethane(), _settings(220.0, 5.0, 2), 200.0)
    assert result.termination_reason is EnvelopeTerminationReason.MAXIMUM_POINTS
    assert len(result.points) == 2


def test_failed_start_returns_empty_partial_result() -> None:
    result = trace_bubble_branch(
        _methane_ethane(),
        _settings(
            210.0,
            5.0,
            4,
            minimum_pressure_pa=1_000.0,
            maximum_pressure_pa=10_000.0,
        ),
        200.0,
    )
    assert result.termination_reason is EnvelopeTerminationReason.CORRECTOR_FAILED
    assert result.points == ()
    assert result.termination_message


def test_deterministic_repeated_trace() -> None:
    settings = _settings(205.0, 5.0, 2)
    first = trace_bubble_branch(_methane_ethane(), settings, 200.0)
    second = trace_bubble_branch(_methane_ethane(), settings, 200.0)
    assert tuple(
        (item.temperature_k, item.pressure_pa) for item in first.points
    ) == tuple((item.temperature_k, item.pressure_pa) for item in second.points)
    assert first.termination_reason is second.termination_reason


def test_short_trace_runtime_is_acceptable() -> None:
    started = perf_counter()
    result = trace_bubble_branch(_methane_ethane(), _settings(205.0, 5.0, 2), 200.0)
    elapsed = perf_counter() - started
    assert len(result.points) == 2
    assert elapsed < 15.0


def test_documentation_does_not_claim_exact_critical_solver() -> None:
    text = open("docs/PHASE_ENVELOPE_DESIGN.md", encoding="utf-8").read()
    normalized = " ".join(text.split())
    assert "does not solve an exact critical point" in normalized
    assert "pseudo-arclength continuation is not implemented" in normalized
