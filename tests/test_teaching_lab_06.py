"""Every number in Lab 6 (phase stability and the flash) is recomputed here.

The lab is worked in the app, so each value comes through the app's own flash
boundary (``run_validated_flash``), the same call Overview makes, and the
stability trials it returns. Part D also uses the extended envelope the Phase
Envelope page draws.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from pvt_phase_simulator.eos.flash import TwoPhaseFlashResult
from pvt_phase_simulator.eos.phase_stability import (
    PhaseStabilityTrialResult,
    calculate_wilson_k_values,
)
from pvt_phase_simulator.fluid_models import METHANE, PROPANE
from pvt_phase_simulator_ui.adapters import (
    run_validated_flash,
    validate_scientific_inputs,
)
from pvt_phase_simulator_ui.envelope_extension import trace_extended_envelope
from pvt_phase_simulator_ui.learn import LABS

ROOT = Path(__file__).resolve().parents[1]
LAB = (ROOT / "docs/teaching/LAB_06_STABILITY_AND_FLASH.md").read_text(encoding="utf-8")
STUDENT, _, KEY_TEXT = LAB.partition("## Instructor answer key")
STUDENT = " ".join(STUDENT.split())
KEY = " ".join(KEY_TEXT.split())
FEED = (50.0, 0.0, 50.0)
PRESSURES_MPA = (2.0, 5.0, 8.0, 20.0)
CRITICAL_PRESSURE_MPA = 8.534
PART_D_TEMPERATURES = (312.0, 316.0)


def _signed(value: float, digits: int = 5) -> str:
    return f"{value:+.{digits}f}".replace("-", "−")


@cache
def _flash(temperature: float, pressure_mpa: float) -> TwoPhaseFlashResult:
    return run_validated_flash(FEED, temperature, pressure_mpa)[1]


def _trial_text(trial: PhaseStabilityTrialResult) -> str:
    if trial.trivial_solution:
        return "trivial"
    assert trial.converged and trial.tangent_plane_distance is not None
    return _signed(trial.tangent_plane_distance)


def _state(result: TwoPhaseFlashResult) -> str:
    return result.phase_state.value.replace("_", " ")


def test_student_inputs() -> None:
    assert "50 / 0 / 50 mol % methane / propane and 300 K" in STUDENT
    assert "at 2, 5, 8 and 20 MPa" in STUDENT
    assert "8.534 MPa and 312 K, then at 316 K" in STUDENT


def test_part_a_verdicts_and_tangent_plane_distances() -> None:
    for pressure in PRESSURES_MPA:
        result = _flash(300.0, pressure)
        stability = result.phase_stability
        row = (
            f"| {pressure:g} | {_state(result)} | {stability.status.value} | "
            f"{_trial_text(stability.vapor_like_trial)} | "
            f"{_trial_text(stability.liquid_like_trial)} |"
        )
        assert row in KEY, row
    eight = _flash(300.0, 8.0).phase_stability
    vapour = eight.vapor_like_trial.final_trial_composition
    liquid = eight.liquid_like_trial.final_trial_composition
    assert abs(vapour[0] - liquid[0]) < 1e-9
    assert f"same composition ({100 * vapour[0]:.2f} mol % methane)" in KEY
    twenty = _flash(300.0, 20.0).phase_stability
    assert twenty.status.value == "stable"
    assert twenty.vapor_like_trial.trivial_solution
    assert twenty.liquid_like_trial.trivial_solution


def test_part_b_rachford_rice_by_hand() -> None:
    result = _flash(300.0, 5.0)
    assert result.final_k_values is not None and result.vapor_fraction is not None
    assert result.liquid_phase is not None and result.vapor_phase is not None
    k1, k3 = result.final_k_values[0], result.final_k_values[2]
    assert f"K(methane) = {k1:.4f} and K(propane) = {k3:.4f}" in KEY
    beta = (0.5 * (k1 - 1) + 0.5 * (k3 - 1)) / ((k1 - 1) * (1 - k3))
    assert abs(beta - result.vapor_fraction) < 1e-8
    assert (
        f"[0.5 × ({k1:.4f} − 1) + 0.5 × ({k3:.4f} − 1)] / "
        f"[({k1:.4f} − 1) × (1 − {k3:.4f})] = {result.vapor_fraction:.4f}"
    ) in KEY
    x1 = 100 * result.liquid_phase.composition[0]
    y1 = 100 * result.vapor_phase.composition[0]
    assert abs(x1 - 100 * 0.5 / (1 + beta * (k1 - 1))) < 1e-6
    assert f"x(methane) = {x1:.2f} mol % and y(methane) = {y1:.2f} mol %" in KEY
    balance = result.vapor_fraction * y1 + (1 - result.vapor_fraction) * x1
    assert (
        f"{result.vapor_fraction:.4f} × {y1:.2f} + "
        f"{1 - result.vapor_fraction:.4f} × {x1:.2f} = {balance:.2f} mol %"
    ) in KEY


def test_part_c_constants_and_wilson_k_values() -> None:
    for component in (METHANE, PROPANE):
        row = (
            f"| {component.name} | {component.critical_temperature_k:g} | "
            f"{component.critical_pressure_pa / 1e6:g} | "
            f"{component.acentric_factor:g} |"
        )
        assert row in STUDENT, row
    wilson = calculate_wilson_k_values((METHANE, PROPANE), 300.0, 5.0e6)
    result = _flash(300.0, 5.0)
    assert result.final_k_values is not None
    methane = f"| Methane | {wilson[0].k_value:.3f} | {result.final_k_values[0]:.3f} |"
    propane = f"| Propane | {wilson[1].k_value:.4f} | {result.final_k_values[2]:.4f} |"
    assert methane in KEY, methane
    assert propane in KEY, propane


def test_part_d_near_critical_verdicts() -> None:
    for temperature in PART_D_TEMPERATURES:
        result = _flash(temperature, CRITICAL_PRESSURE_MPA)
        stability = result.phase_stability
        trivial = (
            stability.vapor_like_trial.trivial_solution
            and stability.liquid_like_trial.trivial_solution
        )
        row = (
            f"| {temperature:g} | {_state(result)} | {stability.status.value} | "
            f"{'yes' if trivial else 'no'} |"
        )
        assert row in KEY, row


def test_part_d_the_316_k_state_is_inside_the_envelope() -> None:
    mixture = validate_scientific_inputs(FEED, 300.0, 5.0).mixture()
    points = sorted(
        (point.temperature_k, point.pressure_pa)
        for point in trace_extended_envelope(mixture, 300.0).bubble.points
    )
    below = max(point for point in points if point[0] <= 316.0)
    above = min(point for point in points if point[0] >= 316.0)
    assert (
        f"passes {below[1] / 1e6:.4f} MPa at {below[0]:.2f} K and "
        f"{above[1] / 1e6:.4f} MPa at {above[0]:.2f} K"
    ) in KEY
    assert below[1] > CRITICAL_PRESSURE_MPA * 1e6
    assert above[1] > CRITICAL_PRESSURE_MPA * 1e6
    certified = "certified critical point of this mixture is 321.58 K and 8.534 MPa"
    assert certified in STUDENT


def test_learn_mode_links_the_lab() -> None:
    title = LAB.splitlines()[0].removeprefix("# ")
    assert (title, "LAB_06_STABILITY_AND_FLASH.md") in LABS
