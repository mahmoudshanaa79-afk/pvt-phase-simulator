"""Scientific and safeguard tests for Module 15 Newton saturation."""

from dataclasses import replace
from math import log

import numpy as np
import pytest

import pvt_phase_simulator.eos.saturation_pressure as saturation_module
from pvt_phase_simulator.eos.derivatives import (
    FixedRootMixtureFugacityDerivatives,
)
from pvt_phase_simulator.eos.phase_envelope import (
    EnvelopeContinuationSettings,
    EnvelopeTerminationReason,
    trace_bubble_branch,
)
from pvt_phase_simulator.eos.saturation_pressure import (
    INNER_LOG_K_TOLERANCE,
    SaturationKind,
    SaturationNewtonStatus,
    SaturationStatus,
    calculate_saturation_pressure,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    Component,
    FluidMixture,
    MixtureComponent,
)


def _mixture(items: tuple[tuple[Component, float], ...]) -> FluidMixture:
    return FluidMixture(tuple(MixtureComponent(*item) for item in items))


BINARY = _mixture(((METHANE, 0.5), (ETHANE, 0.5)))
TERNARY = _mixture(((METHANE, 0.6), (ETHANE, 0.3), (PROPANE, 0.1)))
METHANE_PROPANE = _mixture(((METHANE, 0.6), (PROPANE, 0.4)))
PURE = _mixture(((METHANE, 1.0),))
NEAR_PURE = _mixture(((METHANE, 0.999), (ETHANE, 0.001)))


def _assert_same_physical_state(
    newton: saturation_module.SaturationPressureResult,
    historical: saturation_module.SaturationPressureResult,
) -> None:
    assert newton.status is historical.status is SaturationStatus.CONVERGED
    assert newton.pressure_pa == pytest.approx(historical.pressure_pa, rel=1e-11)
    assert newton.incipient_composition == pytest.approx(
        historical.incipient_composition, abs=1e-10
    )
    assert tuple(log(value) for value in newton.k_values) == pytest.approx(
        tuple(log(value) for value in historical.k_values), abs=1e-9
    )
    assert newton.parent_phase is not None and historical.parent_phase is not None
    assert newton.incipient_phase is not None and historical.incipient_phase is not None
    assert newton.parent_phase.selected_compressibility_factor == pytest.approx(
        historical.parent_phase.selected_compressibility_factor, abs=1e-11
    )
    assert newton.incipient_phase.selected_compressibility_factor == pytest.approx(
        historical.incipient_phase.selected_compressibility_factor, abs=1e-11
    )


@pytest.mark.parametrize(
    ("mixture", "temperature_k", "kind"),
    [
        (BINARY, 220.0, SaturationKind.BUBBLE_POINT),
        (BINARY, 220.0, SaturationKind.DEW_POINT),
        (TERNARY, 220.0, SaturationKind.BUBBLE_POINT),
        (TERNARY, 220.0, SaturationKind.DEW_POINT),
        (PURE, 170.0, SaturationKind.BUBBLE_POINT),
        (NEAR_PURE, 170.0, SaturationKind.BUBBLE_POINT),
    ],
)
def test_newton_converges_to_historical_physical_state(
    mixture: FluidMixture,
    temperature_k: float,
    kind: SaturationKind,
) -> None:
    historical = calculate_saturation_pressure(mixture, temperature_k, kind)
    newton = calculate_saturation_pressure(
        mixture, temperature_k, kind, saturation_newton_enabled=True
    )
    assert newton.newton_attempt is not None
    assert newton.newton_attempt.status is SaturationNewtonStatus.CONVERGED
    assert newton.newton_attempt.final_residual_norm is not None
    assert newton.newton_attempt.final_residual_norm <= INNER_LOG_K_TOLERANCE
    _assert_same_physical_state(newton, historical)


def test_disabled_path_is_exact_historical_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("disabled path called Newton or derivative code")

    monkeypatch.setattr(saturation_module, "_attempt_saturation_newton", forbidden)
    monkeypatch.setattr(
        saturation_module,
        "calculate_fixed_root_mixture_fugacity_derivatives",
        forbidden,
    )
    public = calculate_saturation_pressure(BINARY, 220.0, SaturationKind.BUBBLE_POINT)
    historical = saturation_module._calculate_saturation_pressure_historical(
        BINARY, 220.0, SaturationKind.BUBBLE_POINT
    )
    assert public == historical
    assert public.newton_attempt is None


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("saturation_newton_enabled", 1),
        ("newton_max_iterations", 0),
        ("newton_max_iterations", 1.5),
        ("newton_max_jacobian_condition_number", 0.0),
        ("newton_max_jacobian_condition_number", float("nan")),
        ("newton_line_search_reduction_factor", 0.0),
        ("newton_line_search_reduction_factor", 1.0),
        ("newton_minimum_line_search_factor", 0.0),
        ("newton_minimum_line_search_factor", 1.0),
        ("newton_max_backtracking_iterations", -1),
        ("newton_max_backtracking_iterations", 1.5),
    ],
)
def test_newton_setting_validation(name: str, value: object) -> None:
    kwargs = {name: value}
    with pytest.raises(ValueError):
        calculate_saturation_pressure(
            BINARY,
            220.0,
            SaturationKind.BUBBLE_POINT,
            **kwargs,  # type: ignore[arg-type]
        )


def _newton_coordinates(
    result: saturation_module.SaturationPressureResult,
) -> tuple[tuple[float, ...], float]:
    active = tuple(
        fraction
        for feed, fraction in zip(
            result.feed_composition, result.incipient_composition, strict=True
        )
        if feed > 0.0
    )
    if result.pressure_pa is None:
        raise AssertionError("converged reference requires pressure")
    return active[:-1], log(result.pressure_pa)


@pytest.mark.parametrize(
    ("mixture", "temperature_k", "kind"),
    [
        (BINARY, 220.0, SaturationKind.BUBBLE_POINT),
        (BINARY, 220.0, SaturationKind.DEW_POINT),
        (TERNARY, 220.0, SaturationKind.BUBBLE_POINT),
        (TERNARY, 220.0, SaturationKind.DEW_POINT),
        (PURE, 170.0, SaturationKind.BUBBLE_POINT),
        (NEAR_PURE, 170.0, SaturationKind.BUBBLE_POINT),
        (
            _mixture(((ETHANE, 0.5), (METHANE, 0.5))),
            220.0,
            SaturationKind.BUBBLE_POINT,
        ),
    ],
)
def test_complete_newton_jacobian_matches_independent_richardson_difference(
    mixture: FluidMixture,
    temperature_k: float,
    kind: SaturationKind,
) -> None:
    reference = calculate_saturation_pressure(mixture, temperature_k, kind)
    coordinates, log_pressure = _newton_coordinates(reference)
    baseline = saturation_module._evaluate_saturation_newton_system(
        mixture,
        temperature_k,
        kind,
        coordinates,
        log_pressure,
        1_000.0,
        100_000_000.0,
        None,
        saturation_module.BinaryInteractionPolicy.DEFAULT_ZERO,
    )
    analytical = np.asarray(baseline.jacobian)
    numerical = np.empty_like(analytical)
    q = (*coordinates, log_pressure)
    for column in range(len(q)):
        if column < len(coordinates):
            reference_fraction = 1.0 - sum(coordinates)
            h = min(2e-4, 0.02 * min(coordinates[column], reference_fraction))
        else:
            h = 2e-4

        estimates: list[np.ndarray] = []
        for step in (h, h / 2.0):
            plus_q = tuple(
                value + (step if index == column else 0.0)
                for index, value in enumerate(q)
            )
            minus_q = tuple(
                value - (step if index == column else 0.0)
                for index, value in enumerate(q)
            )
            plus = saturation_module._evaluate_saturation_newton_system(
                mixture,
                temperature_k,
                kind,
                plus_q[:-1],
                plus_q[-1],
                1_000.0,
                100_000_000.0,
                None,
                saturation_module.BinaryInteractionPolicy.DEFAULT_ZERO,
            )
            minus = saturation_module._evaluate_saturation_newton_system(
                mixture,
                temperature_k,
                kind,
                minus_q[:-1],
                minus_q[-1],
                1_000.0,
                100_000_000.0,
                None,
                saturation_module.BinaryInteractionPolicy.DEFAULT_ZERO,
            )
            assert saturation_module._root_branch_is_continuous(
                baseline.parent_phase, plus.parent_phase
            )
            assert saturation_module._root_branch_is_continuous(
                baseline.parent_phase, minus.parent_phase
            )
            assert saturation_module._root_branch_is_continuous(
                baseline.incipient_phase, plus.incipient_phase
            )
            assert saturation_module._root_branch_is_continuous(
                baseline.incipient_phase, minus.incipient_phase
            )
            estimates.append(
                (np.asarray(plus.residuals) - np.asarray(minus.residuals))
                / (2.0 * step)
            )
        numerical[:, column] = estimates[1] + (estimates[1] - estimates[0]) / 3.0
    assert analytical == pytest.approx(numerical, rel=3e-6, abs=3e-7)


def test_jacobian_contains_explicit_ideal_composition_derivative() -> None:
    reference = calculate_saturation_pressure(
        BINARY, 220.0, SaturationKind.BUBBLE_POINT
    )
    coordinates, log_pressure = _newton_coordinates(reference)
    evaluation = saturation_module._evaluate_saturation_newton_system(
        BINARY,
        220.0,
        SaturationKind.BUBBLE_POINT,
        coordinates,
        log_pressure,
        1_000.0,
        100_000_000.0,
        None,
        saturation_module.BinaryInteractionPolicy.DEFAULT_ZERO,
    )
    incipient = evaluation.active_incipient_composition
    ideal_column = np.asarray((-1.0 / incipient[0], 1.0 / incipient[1]))
    actual = np.asarray(evaluation.jacobian)[:, 0]
    assert np.linalg.norm(ideal_column, ord=np.inf) > 1.0
    assert np.linalg.norm(actual - ideal_column, ord=np.inf) > 1e-3


def test_ch4_c3_dew_stays_on_nontrivial_physical_branch() -> None:
    result = calculate_saturation_pressure(
        METHANE_PROPANE,
        250.0,
        SaturationKind.DEW_POINT,
        saturation_newton_enabled=True,
    )
    assert result.newton_attempt is not None and result.newton_attempt.converged
    assert result.pressure_pa == pytest.approx(575_969.5124486194, rel=1e-11)
    assert max(abs(log(value)) for value in result.k_values) > 1e-8


def test_zero_fraction_reduced_system_matches_binary() -> None:
    with_zero = _mixture(((METHANE, 0.5), (PROPANE, 0.0), (ETHANE, 0.5)))
    binary = calculate_saturation_pressure(
        BINARY,
        220.0,
        SaturationKind.BUBBLE_POINT,
        saturation_newton_enabled=True,
    )
    ternary = calculate_saturation_pressure(
        with_zero,
        220.0,
        SaturationKind.BUBBLE_POINT,
        saturation_newton_enabled=True,
    )
    assert ternary.newton_attempt is not None and ternary.newton_attempt.converged
    assert ternary.pressure_pa == pytest.approx(binary.pressure_pa, rel=1e-11)
    assert (
        ternary.incipient_composition[0],
        ternary.incipient_composition[2],
    ) == pytest.approx(binary.incipient_composition, abs=1e-10)
    assert ternary.incipient_composition[1] == 0.0


@pytest.mark.parametrize("kind", list(SaturationKind))
def test_component_permutation_is_covariant(kind: SaturationKind) -> None:
    reversed_mixture = _mixture(((ETHANE, 0.5), (METHANE, 0.5)))
    forward = calculate_saturation_pressure(
        BINARY, 220.0, kind, saturation_newton_enabled=True
    )
    reverse = calculate_saturation_pressure(
        reversed_mixture, 220.0, kind, saturation_newton_enabled=True
    )
    assert forward.pressure_pa == pytest.approx(reverse.pressure_pa, rel=1e-11)
    assert forward.incipient_composition == pytest.approx(
        tuple(reversed(reverse.incipient_composition)), abs=1e-10
    )
    assert forward.parent_phase is not None and reverse.parent_phase is not None
    assert forward.incipient_phase is not None and reverse.incipient_phase is not None
    assert forward.parent_phase.selected_compressibility_factor == pytest.approx(
        reverse.parent_phase.selected_compressibility_factor, abs=1e-11
    )
    assert forward.incipient_phase.selected_compressibility_factor == pytest.approx(
        reverse.incipient_phase.selected_compressibility_factor, abs=1e-11
    )


def test_newton_path_is_deterministic() -> None:
    first = calculate_saturation_pressure(
        TERNARY, 220.0, SaturationKind.DEW_POINT, saturation_newton_enabled=True
    )
    second = calculate_saturation_pressure(
        TERNARY, 220.0, SaturationKind.DEW_POINT, saturation_newton_enabled=True
    )
    assert first == second
    assert first.newton_attempt == second.newton_attempt


def _forced_failure_still_returns_historical(
    monkeypatch: pytest.MonkeyPatch,
    attribute: str,
    replacement: object,
    **settings: object,
) -> saturation_module.SaturationPressureResult:
    historical = calculate_saturation_pressure(BINARY, 220.0, SaturationKind.DEW_POINT)
    monkeypatch.setattr(saturation_module, attribute, replacement)
    result = calculate_saturation_pressure(
        BINARY,
        220.0,
        SaturationKind.DEW_POINT,
        saturation_newton_enabled=True,
        **settings,  # type: ignore[arg-type]
    )
    _assert_same_physical_state(result, historical)
    assert result.newton_attempt is not None
    assert result.newton_attempt.status is SaturationNewtonStatus.REJECTED
    return result


def test_singular_jacobian_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    def singular(*args: object, **kwargs: object) -> object:
        raise np.linalg.LinAlgError("forced singular matrix")

    historical = saturation_module._calculate_saturation_pressure_historical(
        BINARY, 220.0, SaturationKind.DEW_POINT
    )
    monkeypatch.setattr(saturation_module.np.linalg, "solve", singular)
    result = calculate_saturation_pressure(
        BINARY,
        220.0,
        SaturationKind.DEW_POINT,
        saturation_newton_enabled=True,
    )
    _assert_same_physical_state(result, historical)
    assert result.newton_attempt is not None
    assert "linear solve" in (result.newton_attempt.failure_reason or "")


def test_ill_conditioned_jacobian_falls_back() -> None:
    historical = calculate_saturation_pressure(BINARY, 220.0, SaturationKind.DEW_POINT)
    result = calculate_saturation_pressure(
        BINARY,
        220.0,
        SaturationKind.DEW_POINT,
        saturation_newton_enabled=True,
        newton_max_jacobian_condition_number=1.0,
    )
    _assert_same_physical_state(result, historical)
    assert result.newton_attempt is not None
    assert "condition-number" in (result.newton_attempt.failure_reason or "")


def test_nonfinite_step_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        saturation_module.np.linalg,
        "solve",
        lambda *args, **kwargs: np.asarray((float("nan"), float("nan"))),
    )
    historical = saturation_module._calculate_saturation_pressure_historical(
        BINARY, 220.0, SaturationKind.DEW_POINT
    )
    result = calculate_saturation_pressure(
        BINARY,
        220.0,
        SaturationKind.DEW_POINT,
        saturation_newton_enabled=True,
    )
    _assert_same_physical_state(result, historical)
    assert result.newton_attempt is not None
    assert "non-finite step" in (result.newton_attempt.failure_reason or "")


def test_nonfinite_jacobian_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    original = saturation_module._evaluate_saturation_newton_system

    def nonfinite(*args: object, **kwargs: object) -> object:
        result = original(*args, **kwargs)  # type: ignore[arg-type]
        size = len(result.jacobian)
        return replace(
            result,
            jacobian=tuple(
                tuple(float("nan") for _ in range(size)) for _ in range(size)
            ),
        )

    result = _forced_failure_still_returns_historical(
        monkeypatch, "_evaluate_saturation_newton_system", nonfinite
    )
    assert "non-finite" in (result.newton_attempt.failure_reason or "")


def test_derivative_non_applicability_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = saturation_module.calculate_fixed_root_mixture_fugacity_derivatives

    def unavailable(
        *args: object, **kwargs: object
    ) -> FixedRootMixtureFugacityDerivatives:
        result = original(*args, **kwargs)  # type: ignore[arg-type]
        return replace(result, applicable=False, failure_reason="forced unavailable")

    result = _forced_failure_still_returns_historical(
        monkeypatch,
        "calculate_fixed_root_mixture_fugacity_derivatives",
        unavailable,
    )
    assert "derivatives are unavailable" in (result.newton_attempt.failure_reason or "")


def test_pure_single_root_and_unavailable_derivative_are_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="distinct physical roots"):
        saturation_module._evaluate_saturation_newton_system(
            PURE,
            170.0,
            SaturationKind.BUBBLE_POINT,
            (),
            log(10_000_000.0),
            1_000.0,
            100_000_000.0,
            None,
            saturation_module.BinaryInteractionPolicy.DEFAULT_ZERO,
        )
    original = saturation_module.calculate_fixed_root_mixture_fugacity_derivatives

    def unavailable(*args: object, **kwargs: object) -> object:
        result = original(*args, **kwargs)  # type: ignore[arg-type]
        return replace(result, applicable=False, failure_reason="multiple root")

    monkeypatch.setattr(
        saturation_module,
        "calculate_fixed_root_mixture_fugacity_derivatives",
        unavailable,
    )
    result = calculate_saturation_pressure(
        PURE,
        170.0,
        SaturationKind.BUBBLE_POINT,
        saturation_newton_enabled=True,
    )
    assert result.status is SaturationStatus.CONVERGED
    assert result.newton_attempt is not None and not result.newton_attempt.converged


@pytest.mark.parametrize(
    ("step", "expected"),
    [
        (np.asarray((0.0, 1e6)), "pressure"),
        (np.asarray((1e6, 0.0)), "reference-component fraction"),
    ],
)
def test_invalid_trial_is_rejected_and_falls_back(
    monkeypatch: pytest.MonkeyPatch,
    step: np.ndarray,
    expected: str,
) -> None:
    monkeypatch.setattr(saturation_module.np.linalg, "solve", lambda *args: step)
    historical = saturation_module._calculate_saturation_pressure_historical(
        BINARY, 220.0, SaturationKind.DEW_POINT
    )
    result = calculate_saturation_pressure(
        BINARY,
        220.0,
        SaturationKind.DEW_POINT,
        saturation_newton_enabled=True,
        newton_max_backtracking_iterations=2,
    )
    _assert_same_physical_state(result, historical)
    assert result.newton_attempt is not None
    assert result.newton_attempt.rejected_steps > 0
    assert expected in (result.newton_attempt.failure_reason or "")


def test_root_switch_candidate_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        saturation_module, "_root_branch_is_continuous", lambda *args: False
    )
    historical = saturation_module._calculate_saturation_pressure_historical(
        BINARY, 220.0, SaturationKind.DEW_POINT
    )
    result = calculate_saturation_pressure(
        BINARY,
        220.0,
        SaturationKind.DEW_POINT,
        saturation_newton_enabled=True,
        newton_max_backtracking_iterations=1,
    )
    _assert_same_physical_state(result, historical)
    assert result.newton_attempt is not None and not result.newton_attempt.converged


def test_trivial_candidate_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(saturation_module, "_newton_is_trivial", lambda *args: True)
    historical = saturation_module._calculate_saturation_pressure_historical(
        BINARY, 220.0, SaturationKind.DEW_POINT
    )
    result = calculate_saturation_pressure(
        BINARY,
        220.0,
        SaturationKind.DEW_POINT,
        saturation_newton_enabled=True,
    )
    _assert_same_physical_state(result, historical)
    assert result.newton_attempt is not None
    assert "trivial" in (result.newton_attempt.failure_reason or "")


def test_tiny_step_with_large_residual_does_not_converge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        saturation_module.np.linalg,
        "solve",
        lambda *args: np.asarray((0.0, 0.0)),
    )
    result = calculate_saturation_pressure(
        BINARY,
        220.0,
        SaturationKind.DEW_POINT,
        saturation_newton_enabled=True,
        newton_max_backtracking_iterations=0,
    )
    assert result.status is SaturationStatus.CONVERGED
    assert result.newton_attempt is not None and not result.newton_attempt.converged
    assert result.newton_attempt.initial_residual_norm is not None
    assert result.newton_attempt.initial_residual_norm > INNER_LOG_K_TOLERANCE


def test_maximum_newton_iterations_falls_back() -> None:
    result = calculate_saturation_pressure(
        BINARY,
        220.0,
        SaturationKind.DEW_POINT,
        saturation_newton_enabled=True,
        newton_max_iterations=1,
    )
    assert result.status is SaturationStatus.CONVERGED
    assert result.newton_attempt is not None and not result.newton_attempt.converged
    assert "Maximum Newton iterations" in (result.newton_attempt.failure_reason or "")


def test_inverted_local_guess_is_discarded_without_losing_success() -> None:
    historical = calculate_saturation_pressure(BINARY, 220.0, SaturationKind.DEW_POINT)
    assert historical.pressure_pa is not None
    poor_seed = tuple(
        log(value) - 2.0 * (-1.0) ** index
        for index, value in enumerate(historical.k_values)
    )
    result = calculate_saturation_pressure(
        BINARY,
        220.0,
        SaturationKind.DEW_POINT,
        historical.pressure_pa * 0.4,
        historical.pressure_pa * 1.8,
        initial_log_k_values=poor_seed,
        saturation_newton_enabled=True,
    )
    assert result.status is SaturationStatus.CONVERGED
    assert result.newton_attempt is not None and result.newton_attempt.converged
    assert any(
        item.code == saturation_module.INITIAL_LOG_K_PHASE_ROLE_DIAGNOSTIC_CODE
        for item in result.diagnostics
    )


def test_real_backtracking_step_converges() -> None:
    historical = calculate_saturation_pressure(BINARY, 220.0, SaturationKind.DEW_POINT)
    assert historical.pressure_pa is not None
    seed = tuple(
        log(value) - (-1.0) ** index for index, value in enumerate(historical.k_values)
    )
    result = calculate_saturation_pressure(
        BINARY,
        220.0,
        SaturationKind.DEW_POINT,
        historical.pressure_pa * 0.4,
        historical.pressure_pa * 1.8,
        initial_log_k_values=seed,
        saturation_newton_enabled=True,
    )
    _assert_same_physical_state(result, historical)
    assert result.newton_attempt is not None and result.newton_attempt.converged
    assert result.newton_attempt.backtracked_steps >= 1
    assert result.newton_attempt.rejected_steps >= 1


def test_newton_uses_accelerated_or_damped_historical_fallback() -> None:
    for kwargs in (
        {"successive_substitution_acceleration_enabled": True},
        {"successive_substitution_damping_factor": 0.5},
    ):
        result = calculate_saturation_pressure(
            BINARY,
            220.0,
            SaturationKind.DEW_POINT,
            saturation_newton_enabled=True,
            newton_max_jacobian_condition_number=1.0,
            **kwargs,  # type: ignore[arg-type]
        )
        assert result.status is SaturationStatus.CONVERGED
        assert result.newton_attempt is not None and not result.newton_attempt.converged


def test_envelope_passes_newton_configuration() -> None:
    settings = EnvelopeContinuationSettings(
        target_temperature_k=202.0,
        initial_temperature_step_k=2.0,
        maximum_points=3,
        saturation_newton_enabled=True,
    )
    branch = trace_bubble_branch(BINARY, settings, 200.0)
    assert branch.termination_reason is EnvelopeTerminationReason.TARGET_REACHED
    assert all(
        point.saturation_result.newton_attempt is not None for point in branch.points
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"saturation_newton_enabled": 1},
        {"newton_max_iterations": 0},
        {"newton_max_jacobian_condition_number": 0.0},
        {"newton_line_search_reduction_factor": 1.0},
        {"newton_minimum_line_search_factor": 1.0},
        {"newton_max_backtracking_iterations": -1},
    ],
)
def test_envelope_newton_setting_validation(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        EnvelopeContinuationSettings(
            target_temperature_k=202.0,
            initial_temperature_step_k=2.0,
            **changes,  # type: ignore[arg-type]
        )


def test_continuation_only_state_is_preserved_with_newton_layer() -> None:
    settings = EnvelopeContinuationSettings(
        target_temperature_k=250.0,
        initial_temperature_step_k=5.0,
        maximum_points=6,
        saturation_newton_enabled=True,
    )
    branch = trace_bubble_branch(BINARY, settings, 240.0)
    assert branch.termination_reason is EnvelopeTerminationReason.TARGET_REACHED
    assert branch.points[-1].pressure_pa == pytest.approx(
        6_172_720.661334422, rel=1e-11
    )
    assert branch.points[-1].saturation_result.newton_attempt is not None
