"""The Lab 3 (composition and the envelope) answer key must match the engine."""

from __future__ import annotations

from functools import cache
from pathlib import Path

import pytest

from pvt_phase_simulator.eos.critical_point import (
    MixtureCriticalPointResult,
    solve_mixture_critical_point,
)
from pvt_phase_simulator.eos.flash import TwoPhaseFlashResult, calculate_two_phase_flash
from pvt_phase_simulator.eos.saturation_pressure import (
    SaturationKind,
    calculate_saturation_pressure,
)
from pvt_phase_simulator.fluid_models import METHANE, PROPANE, FluidMixture
from pvt_phase_simulator_ui.adapters import validate_scientific_inputs
from pvt_phase_simulator_ui.envelope_extension import (
    ExtendedEnvelope,
    ExtensionPoint,
    trace_extended_envelope,
)

ROOT = Path(__file__).resolve().parents[1]
LAB = (ROOT / "docs" / "teaching" / "LAB_03_COMPOSITION_AND_THE_ENVELOPE.md").read_text(
    encoding="utf-8"
)
STUDENT, _, KEY_TEXT = LAB.partition("## Instructor answer key")
STUDENT = " ".join(STUDENT.split())
KEY = " ".join(KEY_TEXT.split())

#: Methane mol % -> (operating temperature K, critical-solver seed K, MPa).
MIXTURES = {
    30.0: (310.0, (345.0, 6.7)),
    50.0: (300.0, (320.0, 8.5)),
    70.0: (260.0, (283.0, 9.9)),
}
#: Alternative seeds the key says give the same answer.
OTHER_SEEDS = {30.0: (340.0, 6.5), 50.0: (315.0, 8.0), 70.0: (280.0, 9.5)}
RESERVOIR_T = 300.0
SWEEP_MPA = tuple(1.0 + 0.25 * index for index in range(37))


def _name(methane: float) -> str:
    return f"{methane:.0f} / {100 - methane:.0f}"


def _mixture(methane: float) -> FluidMixture:
    return validate_scientific_inputs(
        (methane, 0.0, 100.0 - methane), MIXTURES[methane][0], 5.0e6
    ).mixture()


@cache
def _envelope(methane: float, operating_k: float | None = None) -> ExtendedEnvelope:
    temperature = MIXTURES[methane][0] if operating_k is None else operating_k
    return trace_extended_envelope(_mixture(methane), temperature)


def _landmarks(
    methane: float,
) -> tuple[ExtensionPoint, str, ExtensionPoint, str]:
    envelope = _envelope(methane)
    labelled = [(point, "bubble") for point in envelope.bubble.points] + [
        (point, "dew") for point in envelope.dew.points
    ]
    bar = max(labelled, key=lambda item: item[0].pressure_pa)
    therm = max(labelled, key=lambda item: item[0].temperature_k)
    return bar[0], bar[1], therm[0], therm[1]


@cache
def _critical(methane: float, seed: tuple[float, float]) -> MixtureCriticalPointResult:
    temperature, pressure_mpa = seed
    return solve_mixture_critical_point(
        _mixture(methane), temperature, pressure_mpa * 1e6
    )


@cache
def _flash(methane: float, pressure_mpa: float) -> TwoPhaseFlashResult:
    return calculate_two_phase_flash(_mixture(methane), RESERVOIR_T, pressure_mpa * 1e6)


def _liquid(methane: float, pressure_mpa: float) -> float | None:
    flash = _flash(methane, pressure_mpa)
    if flash.phase_state.value != "two_phase":
        return None
    return 1.0 - flash.vapor_fraction


def test_student_inputs_and_seeds() -> None:
    for methane, (operating, (seed_t, seed_p)) in MIXTURES.items():
        assert f"| {methane:.0f} / 0 / {100 - methane:.0f} | {operating:.0f} K |" in (
            STUDENT
        )
        assert f"{seed_t:.0f} K and {seed_p} MPa for {_name(methane)}" in STUDENT


def test_part_a_landmarks() -> None:
    for methane in MIXTURES:
        envelope = _envelope(methane)
        assert envelope.bubble.termination_reason == "near_critical", methane
        assert envelope.dew.termination_reason == "near_critical", methane
        bar, bar_branch, therm, therm_branch = _landmarks(methane)
        assert (
            f"{_name(methane)}: the cricondenbar is about {bar.pressure_pa / 1e6:.2f} "
            f"MPa, at about {bar.temperature_k:.1f} K" in KEY
        ), methane
        assert (
            f"The cricondentherm is about {therm.temperature_k:.1f} K, at about "
            f"{therm.pressure_pa / 1e6:.2f} MPa, on the {therm_branch} branch" in KEY
        ), methane
        assert therm_branch == "dew"
        if methane == 70.0:
            assert bar_branch == "bubble"
            assert bar == envelope.bubble.points[-1]
            assert "at the end of the bubble branch" in KEY
        else:
            assert bar_branch == "bubble"


def test_part_a_optional_early_stop_at_270_k() -> None:
    envelope = _envelope(70.0, 270.0)
    assert envelope.bubble.termination_reason == "trivial_state"
    assert envelope.dew.termination_reason == "near_critical"
    assert not envelope.both_reached_critical_region
    assert "*trivial_state*" in KEY


def test_part_b_certified_critical_points() -> None:
    for methane, (_, seed) in MIXTURES.items():
        result = _critical(methane, seed)
        assert result.status.value == "converged", methane
        assert "certification" in result.termination_reason
        assert result.temperature_k is not None and result.pressure_pa is not None
        assert (
            f"| {_name(methane)} | {result.temperature_k:.2f} | "
            f"{result.pressure_pa / 1e6:.3f} |" in KEY
        ), methane
        other = _critical(methane, OTHER_SEEDS[methane])
        assert other.status.value == "converged"
        assert other.temperature_k == pytest.approx(result.temperature_k, abs=1e-6)
        assert other.pressure_pa == pytest.approx(result.pressure_pa, rel=1e-8)
        other_t, other_p = OTHER_SEEDS[methane]
        assert f"{other_t:.0f} K and {other_p} MPa" in KEY
    # The 50/50 point is the audited one used in Lab 1.
    fifty = _critical(50.0, MIXTURES[50.0][1])
    assert fifty.temperature_k is not None and fifty.pressure_pa is not None
    assert (fifty.temperature_k, fifty.pressure_pa / 1e6) == pytest.approx(
        (321.58, 8.534), abs=0.005
    )


def test_part_c_trend_table_and_statements() -> None:
    criticals = {}
    for methane, (_, seed) in MIXTURES.items():
        result = _critical(methane, seed)
        assert result.temperature_k is not None and result.pressure_pa is not None
        bar, _, therm, _ = _landmarks(methane)
        window = therm.temperature_k - result.temperature_k
        row = (
            f"| {_name(methane)} | {result.temperature_k:.2f} | "
            f"{result.pressure_pa / 1e6:.3f} | {therm.temperature_k:.1f} | "
            f"{bar.pressure_pa / 1e6:.2f} | {window:.1f} |"
        )
        assert row in KEY, methane
        criticals[methane] = (result.temperature_k, result.pressure_pa, bar, therm)

    lean_t, lean_p, lean_bar, _ = criticals[30.0]
    mid_t, _, mid_bar, mid_therm = criticals[50.0]
    rich_t, rich_p, rich_bar, rich_therm = criticals[70.0]
    assert f"falls by about {lean_t - rich_t:.0f} K" in KEY
    assert f"rises by about {(rich_p - lean_p) / 1e6:.1f} MPa" in KEY
    assert (
        f"(methane {METHANE.critical_pressure_pa / 1e6:.2f} MPa, propane "
        f"{PROPANE.critical_pressure_pa / 1e6:.2f} MPa)" in KEY
    )
    assert min(lean_p, rich_p) > max(
        METHANE.critical_pressure_pa, PROPANE.critical_pressure_pa
    )
    # Position of the critical point relative to the cricondenbar.
    assert lean_t > lean_bar.temperature_k
    assert mid_bar.temperature_k < mid_t < mid_therm.temperature_k
    assert abs(rich_t - rich_bar.temperature_k) < 2.5
    assert abs(rich_p - rich_bar.pressure_pa) < 0.02e6
    assert rich_therm.temperature_k - rich_t > 15.0
    assert (
        f"({rich_p / 1e6:.3f} MPa and about {rich_bar.pressure_pa / 1e6:.2f} MPa)"
        in (KEY)
    )


def test_part_d_prediction_follows_the_critical_temperatures() -> None:
    lean = _critical(30.0, MIXTURES[30.0][1]).temperature_k
    mid = _critical(50.0, MIXTURES[50.0][1]).temperature_k
    rich = _critical(70.0, MIXTURES[70.0][1]).temperature_k
    assert lean is not None and mid is not None and rich is not None
    _, _, rich_therm, _ = _landmarks(70.0)
    assert RESERVOIR_T < mid < lean
    assert rich < RESERVOIR_T < rich_therm.temperature_k
    assert f"critical temperature ({rich:.2f} K)" in KEY
    assert f"cricondentherm ({rich_therm.temperature_k:.1f} K)" in KEY


def test_part_d_liquid_fraction_table() -> None:
    for methane in MIXTURES:
        cells = []
        for pressure in (3.0, 5.0, 7.0):
            liquid = _liquid(methane, pressure)
            cells.append("single phase" if liquid is None else f"{liquid:.3f}")
        row = f"| {_name(methane)} | " + " | ".join(cells) + " |"
        assert row in KEY, row


def test_part_d_bubble_points_and_sweep_boundaries() -> None:
    two_phase_lean = [p for p in SWEEP_MPA if _liquid(30.0, p) is not None]
    assert max(two_phase_lean) == 5.75
    bubble = calculate_saturation_pressure(
        _mixture(30.0),
        RESERVOIR_T,
        SaturationKind.BUBBLE_POINT,
        saturation_newton_enabled=True,
    )
    assert bubble.pressure_pa is not None
    assert 5.75 < bubble.pressure_pa / 1e6 < 6.0
    assert (
        f"highest two-phase pressure in the sweep is 5.75 MPa. The bubble point is "
        f"{bubble.pressure_pa / 1e6:.3f} MPa" in KEY
    )
    assert (_liquid(30.0, 5.75) or 0.0) > 0.99

    # 50/50: two-phase at 8.67 MPa, single phase just above (as in Lab 1).
    assert _flash(50.0, 8.67).phase_state.value == "two_phase"
    assert _flash(50.0, 8.675).phase_state.value == "single_phase"
    assert all(_liquid(50.0, p) is not None for p in SWEEP_MPA if 3.0 <= p <= 8.5)
    assert all(_liquid(50.0, p) is None for p in SWEEP_MPA if p >= 8.75)


def test_part_d_retrograde_dropout_of_the_rich_mixture() -> None:
    liquids = {p: _liquid(70.0, p) for p in SWEEP_MPA}
    two_phase = {p: value for p, value in liquids.items() if value is not None}
    peak = max(two_phase, key=two_phase.__getitem__)
    assert peak == 7.25
    assert (
        f"peaks at about {two_phase[peak]:.3f} ({100 * two_phase[peak]:.1f} mol %) "
        f"at {peak} MPa" in KEY
    )
    assert liquids[5.0] is None and liquids[10.0] is None
    assert all(value < 0.045 for value in two_phase.values())
    assert "never exceeds about 4 %" in KEY
    lean, mid = _liquid(30.0, 5.0), _liquid(50.0, 5.0)
    assert lean is not None and mid is not None
    assert f"30 / 70 mixture is {100 * lean:.0f} % liquid" in KEY
    assert f"50 / 50 mixture {100 * mid:.0f} %" in KEY


def test_no_fixed_temperature_dew_pressure_is_quoted() -> None:
    # P2 is changing how ambiguous dew states are reported.
    assert "dew point is" not in KEY.lower()
    assert "This lab quotes no dew pressures at fixed temperature" in STUDENT
