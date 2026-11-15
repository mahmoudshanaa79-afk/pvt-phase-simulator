"""Every number in Lab 7 (critical point, envelope, retrograde) is recomputed here.

Values come through the same calls the app makes: the critical solver from the
audited seed, the extended envelope the Phase Envelope page draws (operating
temperature 300 K), and the app's flash boundary (``run_validated_flash``).
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from pvt_phase_simulator.eos.critical_point import (
    MixtureCriticalPointResult,
    solve_mixture_critical_point,
)
from pvt_phase_simulator.eos.flash import TwoPhaseFlashResult
from pvt_phase_simulator_ui.adapters import (
    adapt_critical_result,
    run_validated_flash,
    stability_verdict_note,
    validate_scientific_inputs,
)
from pvt_phase_simulator_ui.envelope_extension import (
    ExtendedEnvelope,
    trace_extended_envelope,
)
from pvt_phase_simulator_ui.learn import LABS
from pvt_phase_simulator_ui.state import INPUT_EXAMPLES

ROOT = Path(__file__).resolve().parents[1]
LAB = (ROOT / "docs/teaching/LAB_07_CRITICAL_POINT_AND_RETROGRADE.md").read_text(
    encoding="utf-8"
)
STUDENT, _, KEY_TEXT = LAB.partition("## Instructor answer key")
STUDENT = " ".join(STUDENT.split())
KEY = " ".join(KEY_TEXT.split())
FEED = (50.0, 0.0, 50.0)
RETROGRADE_T = 327.0
PART_C_MPA = (7.70, 7.50, 7.25, 7.00, 6.50, 6.00, 5.80, 5.70)
PART_D_MPA = (7.85, 7.80, 7.75)


@cache
def _critical() -> MixtureCriticalPointResult:
    seed = next(
        item for item in INPUT_EXAMPLES if item.label == "Audited critical-solver seed"
    )
    mixture = validate_scientific_inputs(
        FEED, seed.temperature_k, seed.pressure_pa / 1e6
    ).mixture()
    return solve_mixture_critical_point(mixture, seed.temperature_k, seed.pressure_pa)


@cache
def _envelope() -> ExtendedEnvelope:
    mixture = validate_scientific_inputs(FEED, 300.0, 5.0).mixture()
    return trace_extended_envelope(mixture, 300.0)


@cache
def _flash(pressure_mpa: float) -> TwoPhaseFlashResult:
    return run_validated_flash(FEED, RETROGRADE_T, pressure_mpa)[1]


def _dew_crossings(temperature: float) -> list[float]:
    points = [
        (point.temperature_k, point.pressure_pa) for point in _envelope().dew.points
    ]
    crossings = []
    for (t0, p0), (t1, p1) in zip(points, points[1:], strict=False):
        if (t0 - temperature) * (t1 - temperature) <= 0 and t0 != t1:
            crossings.append(p0 + (p1 - p0) * (temperature - t0) / (t1 - t0))
    return sorted(crossings)


@cache
def _critical_from(
    temperature: float, pressure_mpa: float
) -> MixtureCriticalPointResult:
    mixture = validate_scientific_inputs(FEED, temperature, pressure_mpa).mixture()
    return solve_mixture_critical_point(mixture, temperature, pressure_mpa * 1e6)


def test_part_a_certified_critical_point() -> None:
    result = _critical()
    assert result.status.value == "converged"
    assert adapt_critical_result(result).certified
    assert result.temperature_k is not None and result.pressure_pa is not None
    quoted = (
        f"From the audited seed: {result.temperature_k:.2f} K and "
        f"{result.pressure_pa / 1e6:.3f} MPa. Status *converged*, certified, after "
        f"{result.iterations} iterations"
    )
    assert quoted in KEY, quoted
    assert f'"{result.termination_reason}"' in KEY
    assert "near 321.58 K and 8.534 MPa" in STUDENT
    other = _critical_from(320.0, 8.5)
    assert other.status.value == "converged"
    assert adapt_critical_result(other).certified
    assert other.temperature_k is not None and other.pressure_pa is not None
    assert abs(other.temperature_k - result.temperature_k) < 1e-6
    assert abs(other.pressure_pa - result.pressure_pa) < 1e-2
    assert (
        f"From the 320 K, 8.5 MPa seed: the same point, {other.temperature_k:.2f} K "
        f"and {other.pressure_pa / 1e6:.3f} MPa, certified after "
        f"{other.iterations} iterations."
    ) in KEY
    assert "enter 320 K and 8.5 MPa as the case (50/50)" in STUDENT


def test_part_b_landmarks() -> None:
    envelope = _envelope()
    labelled = [(point, "bubble") for point in envelope.bubble.points] + [
        (point, "dew") for point in envelope.dew.points
    ]
    bar, bar_branch = max(labelled, key=lambda item: item[0].pressure_pa)
    therm, therm_branch = max(labelled, key=lambda item: item[0].temperature_k)
    critical = _critical()
    assert critical.temperature_k is not None and critical.pressure_pa is not None
    assert (
        f"| Cricondenbar | {bar.temperature_k:.2f} | {bar.pressure_pa / 1e6:.3f} | "
        f"{bar_branch} |"
    ) in KEY
    assert (
        f"| Cricondentherm | {therm.temperature_k:.2f} | "
        f"{therm.pressure_pa / 1e6:.3f} | {therm_branch} |"
    ) in KEY
    assert (
        f"| Critical point | {critical.temperature_k:.2f} | "
        f"{critical.pressure_pa / 1e6:.3f} | – |"
    ) in KEY
    assert bar.temperature_k < critical.temperature_k < therm.temperature_k
    assert critical.pressure_pa < bar.pressure_pa
    assert (
        f"{bar.temperature_k:.2f} K < T_c = {critical.temperature_k:.2f} K < "
        f"cricondentherm = {therm.temperature_k:.2f} K"
    ) in KEY
    assert (
        f"P_c = {critical.pressure_pa / 1e6:.3f} MPa < cricondenbar = "
        f"{bar.pressure_pa / 1e6:.3f} MPa"
    ) in KEY
    assert critical.temperature_k < RETROGRADE_T < therm.temperature_k


def test_part_c_dew_pressures_and_retrograde_table() -> None:
    lower, upper = _dew_crossings(RETROGRADE_T)
    assert (f"{upper / 1e6:.3f} MPa (upper) and {lower / 1e6:.3f} MPa (lower)") in KEY
    assert "7.70, 7.50, 7.25, 7.00, 6.50, 6.00, 5.80, 5.70" in STUDENT
    liquid = {}
    for pressure in PART_C_MPA:
        result = _flash(pressure)
        if result.phase_state.value == "two_phase":
            assert result.liquid_fraction is not None
            liquid[pressure] = result.liquid_fraction
            row = f"| {pressure:.2f} | two phase | {result.liquid_fraction:.4f} |"
        else:
            assert pressure * 1e6 < lower
            row = f"| {pressure:.2f} | single phase | – |"
        assert row in KEY, row
    peak = max(liquid, key=liquid.__getitem__)
    assert f"peaks at about {liquid[peak]:.2f} near {peak:.2f} MPa" in KEY
    assert liquid[7.70] < liquid[peak] > liquid[5.80]
    assert f"near the lower dew point ({lower / 1e6:.3f} MPa)" in KEY
    assert f"({liquid[7.70]:.4f} at 7.70 MPa)" in KEY


def test_part_d_states_inside_the_envelope_reported_single_phase() -> None:
    lower, upper = _dew_crossings(RETROGRADE_T)
    assert "7.85, 7.80 and 7.75 MPa" in STUDENT
    for pressure in PART_D_MPA:
        assert lower < pressure * 1e6 < upper
        result = _flash(pressure)
        stability = result.phase_stability
        trivial = (
            stability.vapor_like_trial.trivial_solution
            and stability.liquid_like_trial.trivial_solution
        )
        note = stability_verdict_note(result) is not None
        row = (
            f"| {pressure:.2f} | {result.phase_state.value.replace('_', ' ')} | "
            f"{stability.status.value} | {'yes' if trivial else 'no'} | "
            f"{'yes' if note else 'no'} |"
        )
        assert row in KEY, row
    assert f"below the upper dew pressure ({upper / 1e6:.3f} MPa)" in KEY


def test_learn_mode_links_the_lab() -> None:
    title = LAB.splitlines()[0].removeprefix("# ")
    assert (title, "LAB_07_CRITICAL_POINT_AND_RETROGRADE.md") in LABS
