"""Regression tests for the Module 15.1 independent-audit corrections."""

from __future__ import annotations

import json
from math import log
from pathlib import Path

import numpy as np
import pytest

import pvt_phase_simulator.eos.saturation_pressure as saturation_module
from pvt_phase_simulator.eos.phase_envelope import (
    EnvelopeContinuationSettings,
    EnvelopeTerminationReason,
    trace_bubble_branch,
)
from pvt_phase_simulator.eos.saturation_pressure import (
    INITIAL_LOG_K_PHASE_ROLE_DIAGNOSTIC_CODE,
    INNER_LOG_K_TOLERANCE,
    PHASE_ROOT_DISTINGUISHABILITY_TOLERANCE,
    SaturationKind,
    SaturationStatus,
    calculate_saturation_pressure,
    saturation_phase_roles_are_consistent,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    Component,
    FluidMixture,
    MixtureComponent,
)
from tests.golden_master.core import TOLERANCES, load_csv


def _mixture(items: tuple[tuple[Component, float], ...]) -> FluidMixture:
    return FluidMixture(tuple(MixtureComponent(*item) for item in items))


BINARY = _mixture(((METHANE, 0.5), (ETHANE, 0.5)))
TERNARY = _mixture(((METHANE, 0.5), (ETHANE, 0.3), (PROPANE, 0.2)))
METHANE_PROPANE = _mixture(((METHANE, 0.6), (PROPANE, 0.4)))
ZERO_FRACTION = _mixture(((METHANE, 0.5), (PROPANE, 0.0), (ETHANE, 0.5)))
BASELINE = Path(__file__).parent / "golden_master" / "baseline.csv"


def _assert_requested_phase_roles(
    result: saturation_module.SaturationPressureResult,
) -> None:
    assert result.status is SaturationStatus.CONVERGED
    assert result.parent_phase is not None and result.incipient_phase is not None
    assert (
        saturation_phase_roles_are_consistent(
            result.saturation_kind,
            result.parent_phase.selected_compressibility_factor,
            result.incipient_phase.selected_compressibility_factor,
        )
        is True
    )


def _baseline_row(case_id: str) -> dict[str, str]:
    return next(row for row in load_csv(BASELINE) if row["case_id"] == case_id)


def test_phase_role_classifier_reuses_the_existing_dead_band() -> None:
    tolerance = PHASE_ROOT_DISTINGUISHABILITY_TOLERANCE
    assert (
        saturation_phase_roles_are_consistent(
            SaturationKind.BUBBLE_POINT, 0.2, 0.2 + tolerance
        )
        is None
    )
    assert saturation_phase_roles_are_consistent(
        SaturationKind.BUBBLE_POINT, 0.2, 0.2 + 2.0 * tolerance
    )
    assert not saturation_phase_roles_are_consistent(
        SaturationKind.BUBBLE_POINT, 0.2 + 2.0 * tolerance, 0.2
    )
    assert saturation_phase_roles_are_consistent(SaturationKind.DEW_POINT, 0.8, 0.2)
    assert not saturation_phase_roles_are_consistent(SaturationKind.DEW_POINT, 0.2, 0.8)


@pytest.mark.parametrize("newton_enabled", [False, True])
@pytest.mark.parametrize(
    ("mixture", "temperature_k", "kind"),
    [
        (BINARY, 220.0, SaturationKind.BUBBLE_POINT),
        (BINARY, 220.0, SaturationKind.DEW_POINT),
        (TERNARY, 220.0, SaturationKind.BUBBLE_POINT),
        (TERNARY, 220.0, SaturationKind.DEW_POINT),
    ],
)
def test_natural_saturation_results_preserve_requested_phase_roles(
    mixture: FluidMixture,
    temperature_k: float,
    kind: SaturationKind,
    newton_enabled: bool,
) -> None:
    result = calculate_saturation_pressure(
        mixture,
        temperature_k,
        kind,
        saturation_newton_enabled=newton_enabled,
    )
    _assert_requested_phase_roles(result)


@pytest.mark.parametrize("newton_enabled", [False, True])
def test_inverted_dew_seed_recovers_the_true_dew_branch(
    newton_enabled: bool,
) -> None:
    result = calculate_saturation_pressure(
        METHANE_PROPANE,
        250.0,
        SaturationKind.DEW_POINT,
        initial_log_k_values=(-3.0, 3.0),
        saturation_newton_enabled=newton_enabled,
    )
    _assert_requested_phase_roles(result)
    assert result.pressure_pa == pytest.approx(575_969.5124486194, rel=1e-11)
    assert result.pressure_pa != pytest.approx(7_385_216.135, rel=1e-6)
    assert any(
        item.code == INITIAL_LOG_K_PHASE_ROLE_DIAGNOSTIC_CODE
        for item in result.diagnostics
    )


def test_dew_seed_cannot_return_dew_pressure_as_a_bubble() -> None:
    dew = calculate_saturation_pressure(
        METHANE_PROPANE, 250.0, SaturationKind.DEW_POINT
    )
    assert dew.pressure_pa is not None
    seed = tuple(log(value) for value in dew.k_values)
    bubble = calculate_saturation_pressure(
        METHANE_PROPANE,
        250.0,
        SaturationKind.BUBBLE_POINT,
        0.9 * dew.pressure_pa,
        1.1 * dew.pressure_pa,
        pressure_search_points=9,
        initial_log_k_values=seed,
    )
    assert bubble.status is not SaturationStatus.CONVERGED


@pytest.mark.parametrize(
    ("mixture", "start_temperature_k", "target_temperature_k"),
    [(BINARY, 260.0, 285.0), (TERNARY, 280.0, 330.0)],
)
def test_newton_bubble_trace_stops_before_phase_role_inversion(
    mixture: FluidMixture,
    start_temperature_k: float,
    target_temperature_k: float,
) -> None:
    branch = trace_bubble_branch(
        mixture,
        EnvelopeContinuationSettings(
            target_temperature_k=target_temperature_k,
            initial_temperature_step_k=5.0,
            maximum_points=50,
            saturation_newton_enabled=True,
        ),
        start_temperature_k,
    )
    assert branch.termination_reason is EnvelopeTerminationReason.NEAR_CRITICAL
    assert branch.points
    assert branch.points[-1].temperature_k < target_temperature_k
    assert all(
        saturation_phase_roles_are_consistent(
            point.saturation_result.saturation_kind,
            point.saturation_result.parent_phase.selected_compressibility_factor,
            point.saturation_result.incipient_phase.selected_compressibility_factor,
        )
        is True
        for point in branch.points
    )


def test_zero_fraction_and_permutation_preserve_phase_identity() -> None:
    reduced = calculate_saturation_pressure(
        BINARY, 220.0, SaturationKind.BUBBLE_POINT, saturation_newton_enabled=True
    )
    with_zero = calculate_saturation_pressure(
        ZERO_FRACTION,
        220.0,
        SaturationKind.BUBBLE_POINT,
        saturation_newton_enabled=True,
    )
    reversed_result = calculate_saturation_pressure(
        _mixture(((ETHANE, 0.5), (METHANE, 0.5))),
        220.0,
        SaturationKind.BUBBLE_POINT,
        saturation_newton_enabled=True,
    )
    for result in (reduced, with_zero, reversed_result):
        _assert_requested_phase_roles(result)
    assert with_zero.pressure_pa == pytest.approx(reduced.pressure_pa, rel=1e-11)
    assert reversed_result.pressure_pa == pytest.approx(reduced.pressure_pa, rel=1e-11)


@pytest.mark.parametrize(
    ("case_id", "mixture", "temperature_k", "kind"),
    [
        (
            "bubble_ch4_c2_50_50_180k",
            BINARY,
            180.0,
            SaturationKind.BUBBLE_POINT,
        ),
        ("dew_ch4_c2_50_50_250k", BINARY, 250.0, SaturationKind.DEW_POINT),
        (
            "dew_ch4_c3_60_40_250k_physical_branch",
            METHANE_PROPANE,
            250.0,
            SaturationKind.DEW_POINT,
        ),
    ],
)
def test_newton_matches_selected_canonical_golden_saturation_cases(
    case_id: str,
    mixture: FluidMixture,
    temperature_k: float,
    kind: SaturationKind,
) -> None:
    expected = _baseline_row(case_id)
    result = calculate_saturation_pressure(
        mixture, temperature_k, kind, saturation_newton_enabled=True
    )
    _assert_requested_phase_roles(result)
    assert result.pressure_pa == pytest.approx(
        float(expected["saturation_pressure_pa"]), rel=TOLERANCES["pressure_rel"]
    )
    assert result.incipient_composition == pytest.approx(
        json.loads(expected["incipient_composition"]),
        abs=TOLERANCES["composition_abs"],
    )
    assert result.parent_phase is not None and result.incipient_phase is not None
    assert result.parent_phase.selected_compressibility_factor == pytest.approx(
        float(expected["selected_parent_root"]), abs=TOLERANCES["root_abs"]
    )
    assert result.incipient_phase.selected_compressibility_factor == pytest.approx(
        float(expected["selected_incipient_root"]), abs=TOLERANCES["root_abs"]
    )


def test_newton_matches_canonical_golden_envelope_physics() -> None:
    expected = _baseline_row("bubble_ch4_c2_forward_200_220")
    expected_points = json.loads(expected["branch_points"])
    branch = trace_bubble_branch(
        BINARY,
        EnvelopeContinuationSettings(
            target_temperature_k=220.0,
            initial_temperature_step_k=5.0,
            maximum_points=8,
            saturation_newton_enabled=True,
        ),
        200.0,
    )
    assert branch.termination_reason.value == expected["termination_reason"]
    assert len(branch.points) == len(expected_points)
    for point, reference in zip(branch.points, expected_points, strict=True):
        _assert_requested_phase_roles(point.saturation_result)
        assert point.temperature_k == reference["temperature_k"]
        assert point.pressure_pa == pytest.approx(
            reference["pressure_pa"], rel=TOLERANCES["pressure_rel"]
        )
        assert point.saturation_result.incipient_composition == pytest.approx(
            reference["incipient_composition"], abs=TOLERANCES["composition_abs"]
        )


def test_line_search_rejects_a_nonimproving_finite_trial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        saturation_module.np.linalg,
        "solve",
        lambda *args: np.asarray((0.0, 0.0)),
    )
    monkeypatch.setattr(
        saturation_module, "_root_branch_is_continuous", lambda *args: True
    )
    monkeypatch.setattr(saturation_module, "_newton_is_trivial", lambda *args: False)
    result = calculate_saturation_pressure(
        BINARY,
        220.0,
        SaturationKind.DEW_POINT,
        saturation_newton_enabled=True,
        newton_max_backtracking_iterations=0,
    )
    assert result.newton_attempt is not None and not result.newton_attempt.converged
    assert "equilibrium merit did not improve" in (
        result.newton_attempt.failure_reason or ""
    )


def test_primary_trivial_log_k_band_is_independently_pinned() -> None:
    physical = calculate_saturation_pressure(BINARY, 220.0, SaturationKind.BUBBLE_POINT)
    assert physical.parent_phase is not None and physical.incipient_phase is not None
    inside = (0.5 + 2.0e-9, 0.5 - 2.0e-9)
    outside = (0.5 + 1.0e-8, 0.5 - 1.0e-8)
    assert saturation_module._newton_is_trivial(
        (0.5, 0.5),
        inside,
        SaturationKind.BUBBLE_POINT,
        physical.parent_phase,
        physical.incipient_phase,
    )
    assert not saturation_module._newton_is_trivial(
        (0.5, 0.5),
        outside,
        SaturationKind.BUBBLE_POINT,
        physical.parent_phase,
        physical.incipient_phase,
    )


def test_newton_accepts_convergence_on_the_final_permitted_iteration() -> None:
    result = calculate_saturation_pressure(
        BINARY,
        220.0,
        SaturationKind.DEW_POINT,
        saturation_newton_enabled=True,
        newton_max_iterations=4,
    )
    assert result.newton_attempt is not None and result.newton_attempt.converged
    assert result.newton_attempt.iteration_count == 4
    assert result.newton_attempt.final_residual_norm is not None
    assert result.newton_attempt.final_residual_norm <= INNER_LOG_K_TOLERANCE


def test_pure_methane_regression_keeps_distinct_roots() -> None:
    pure = _mixture(((METHANE, 1.0),))
    result = calculate_saturation_pressure(
        pure,
        170.0,
        SaturationKind.BUBBLE_POINT,
        saturation_newton_enabled=True,
    )
    _assert_requested_phase_roles(result)
    assert result.pressure_pa == pytest.approx(2_348_696.1055850405, rel=1e-11)
