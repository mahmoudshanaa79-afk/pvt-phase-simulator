"""The Lab 2 (methane-ethane) answer key must match the unchanged engine."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

import pytest

from pvt_phase_simulator.eos.flash import TwoPhaseFlashResult, calculate_two_phase_flash
from pvt_phase_simulator.eos.saturation_pressure import (
    SaturationKind,
    SaturationPressureResult,
    calculate_saturation_pressure,
)
from pvt_phase_simulator.experimental_validation import (
    ExperimentalVLEPoint,
    load_experimental_vle_dataset,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    FluidMixture,
    MixtureComponent,
)
from pvt_phase_simulator_ui.adapters import validate_scientific_inputs

ROOT = Path(__file__).resolve().parents[1]
LAB = (ROOT / "docs" / "teaching" / "LAB_02_METHANE_ETHANE.md").read_text(
    encoding="utf-8"
)
STUDENT, _, KEY_TEXT = LAB.partition("## Instructor answer key")
# Markdown wraps lines; compare against collapsed whitespace.
STUDENT = " ".join(STUDENT.split())
KEY = " ".join(KEY_TEXT.split())
SUMMARY = json.loads(
    (ROOT / "docs/validation/module17_vle_validation_summary.json").read_text(
        encoding="utf-8"
    )
)
T = 243.6
BUBBLE_COMPOSITIONS = (0.10, 0.20, 0.30, 0.40, 0.50, 0.60)
#: Pressure (MPa) -> feed (methane mol %) the lab tells students to use there.
PXY_FEEDS = {2.0: 30.0, 3.0: 30.0, 4.0: 50.0, 5.0: 50.0, 6.0: 65.0, 6.5: 65.0}
PART_D_STATES = ("006", "007", "008", "010", "011", "015", "013")


def _feed(methane_pct: float) -> FluidMixture:
    return validate_scientific_inputs(
        (methane_pct, 100.0 - methane_pct, 0.0), T, 4.0e6
    ).mixture()


def _binary(x_methane: float) -> FluidMixture:
    return FluidMixture(
        (MixtureComponent(METHANE, x_methane), MixtureComponent(ETHANE, 1 - x_methane))
    )


@cache
def _flash(methane_pct: float, pressure_mpa: float) -> TwoPhaseFlashResult:
    return calculate_two_phase_flash(_feed(methane_pct), T, pressure_mpa * 1e6)


@cache
def _bubble(x_methane: float, *, newton: bool = True) -> SaturationPressureResult:
    mixture = _feed(100.0 * x_methane) if x_methane > 0 else _feed(0.0)
    return calculate_saturation_pressure(
        mixture, T, SaturationKind.BUBBLE_POINT, saturation_newton_enabled=newton
    )


@cache
def _points() -> dict[str, ExperimentalVLEPoint]:
    dataset = load_experimental_vle_dataset(
        ROOT / "data/experimental/may_2015_ch4_c2_ch4_c3_vle.csv",
        ROOT / "data/experimental/may_2015_source_manifest.json",
    )
    return {
        point.source_point_id[-3:]: point
        for point in dataset.points
        if point.system_id == "ch4_c2"
    }


@cache
def _record_bubble(state: str, *, newton: bool) -> SaturationPressureResult:
    """The validation's own bubble solve: measured T and x, two components."""
    point = _points()[state]
    return calculate_saturation_pressure(
        _binary(point.liquid_mole_fractions[0]),
        point.temperature_k,
        SaturationKind.BUBBLE_POINT,
        saturation_newton_enabled=newton,
    )


def _error_percent(state: str, *, newton: bool) -> float | None:
    result = _record_bubble(state, newton=newton)
    if result.pressure_pa is None:
        return None
    measured = _points()[state].pressure_pa
    return 100.0 * (result.pressure_pa - measured) / measured


def test_setting_and_constants() -> None:
    assert f"({T - 273.15:.2f} °C)".replace("-", "−") in STUDENT
    assert f"({METHANE.critical_temperature_k:.1f} K)" in STUDENT
    assert f"above {METHANE.critical_temperature_k:.1f} K" in KEY


def test_part_a_flash() -> None:
    flash = _flash(50.0, 4.0)
    assert flash.phase_state.value == "two_phase"
    assert flash.liquid_phase is not None and flash.vapor_phase is not None
    assert flash.final_k_values is not None
    x, y, beta = (
        flash.liquid_phase.composition[0],
        flash.vapor_phase.composition[0],
        flash.vapor_fraction,
    )
    assert f"β = {beta:.4f}; *x*(C1) = {x:.4f}, *y*(C1) = {y:.4f}" in KEY
    k1, k2 = flash.final_k_values[0], flash.final_k_values[1]
    assert f"K(C1) = {k1:.3f} and K(C2) = {k2:.3f}" in KEY
    assert k1 > 1.0 > k2
    assert (
        f"{beta:.4f} × {y:.4f} + {1 - beta:.4f} × {x:.4f} = "
        f"{beta * y + (1 - beta) * x:.3f}" in KEY
    )
    assert beta * y + (1 - beta) * x == pytest.approx(0.5, abs=1e-9)
    assert f"converges in {len(flash.iteration_history)} iterations" in KEY
    assert flash.iteration_history[-1].maximum_fugacity_equilibrium_residual < 1e-8


def test_part_b_bubble_pressures() -> None:
    pure = _bubble(0.0)
    assert pure.pressure_pa is not None
    assert f"| 0 (pure ethane) | {pure.pressure_pa / 1e6:.3f} | 0 |" in KEY
    pressures = [pure.pressure_pa / 1e6]
    for x in BUBBLE_COMPOSITIONS:
        result = _bubble(x)
        assert result.pressure_pa is not None, x
        pressure = result.pressure_pa / 1e6
        first_bubble_y = result.incipient_composition[0]
        assert f"| {x:.2f} | {pressure:.3f} | {first_bubble_y:.3f} |" in KEY
        pressures.append(pressure)
    rises = [b - a for a, b in zip(pressures, pressures[1:], strict=False)]
    assert all(0.905 <= rise < 0.955 for rise in rises[:5])  # "0.91 to 0.95"
    assert f"rises by only {rises[5]:.2f} MPa" in KEY
    # The solver's defaults give up on the last two; Newton refinement does not.
    for x in BUBBLE_COMPOSITIONS:
        default = _bubble(x, newton=False)
        assert (default.pressure_pa is None) == (x >= 0.5), x


def test_part_c_pxy_table() -> None:
    rows = {}
    for pressure, feed in PXY_FEEDS.items():
        flash = _flash(feed, pressure)
        assert flash.phase_state.value == "two_phase", pressure
        assert flash.liquid_phase is not None and flash.vapor_phase is not None
        assert flash.final_k_values is not None
        x = flash.liquid_phase.composition[0]
        y = flash.vapor_phase.composition[0]
        k1, k2 = flash.final_k_values[0], flash.final_k_values[1]
        assert f"| {pressure:.1f} | {x:.3f} | {y:.3f} | {k1:.3f} | {k2:.3f} |" in KEY, (
            pressure
        )
        rows[pressure] = (x, y, k1, k2)
    # K(C1) falls throughout; K(C2) has a shallow minimum at 4 MPa, then rises.
    k1s = [row[2] for row in rows.values()]
    k2s = [row[3] for row in rows.values()]
    assert all(b < a for a, b in zip(k1s, k1s[1:], strict=False))
    assert min(k2s) == rows[4.0][3]
    assert all(b > a for a, b in zip(k2s[2:], k2s[3:], strict=False))
    # y(C1) peaks at 6 MPa among the rows, then falls slightly.
    ys = {pressure: row[1] for pressure, row in rows.items()}
    assert max(ys, key=ys.__getitem__) == 6.0
    assert f"maximum of about {ys[6.0]:.3f} near 6 MPa" in KEY
    # The lens starts at the ethane vapour pressure.
    pure = _bubble(0.0)
    assert pure.pressure_pa is not None
    assert f"ethane vapour pressure, {pure.pressure_pa / 1e6:.3f} MPa" in KEY


def test_part_c_compositions_do_not_depend_on_the_feed() -> None:
    lean, rich = _flash(30.0, 3.0), _flash(50.0, 3.0)
    for first, second in (
        (lean.liquid_phase, rich.liquid_phase),
        (lean.vapor_phase, rich.vapor_phase),
    ):
        assert first is not None and second is not None
        assert first.composition[0] == pytest.approx(second.composition[0], abs=1e-6)
    assert abs(lean.vapor_fraction - rich.vapor_fraction) > 0.1


def test_part_c_the_lens_closes_below_7_mpa() -> None:
    assert _flash(65.0, 6.5).phase_state.value == "two_phase"
    for methane_pct in range(5, 100, 5):
        assert _flash(float(methane_pct), 7.0).phase_state.value == "single_phase"
    assert "between 6.5 and 7 MPa" in KEY
    assert "At 7 MPa no feed is two-phase" in KEY


def test_part_d_student_table_is_the_may_2015_data() -> None:
    for state in PART_D_STATES:
        point = _points()[state]
        assert point.temperature_k == pytest.approx(T, abs=0.02)
        row = (
            f"| {state} | {point.liquid_mole_fractions[0]:.4f} | "
            f"{point.pressure_pa / 1e6:.3f} | {point.vapor_mole_fractions[0]:.4f} |"
        )
        assert row in STUDENT, state


def test_part_d_model_comparison_rows() -> None:
    for state in PART_D_STATES:
        measured = _points()[state].pressure_pa / 1e6
        default = _record_bubble(state, newton=False)
        newton = _record_bubble(state, newton=True)
        assert newton.pressure_pa is not None, state
        newton_cell = (
            f"{newton.pressure_pa / 1e6:.3f} | "
            f"{_error_percent(state, newton=True):+.2f} % |"
        )
        if default.pressure_pa is None:
            row = f"| {state} | {measured:.3f} | not found | | {newton_cell}"
        else:
            row = (
                f"| {state} | {measured:.3f} | {default.pressure_pa / 1e6:.3f} | "
                f"{_error_percent(state, newton=False):+.2f} % | {newton_cell}"
            )
        assert row in KEY, state


def test_part_d_production_record_summary() -> None:
    errors = {state: _error_percent(state, newton=False) for state in sorted(_points())}
    solved = [value for value in errors.values() if value is not None]
    aard = sum(abs(value) for value in solved) / len(solved)
    worst = max(abs(value) for value in solved)
    bias = sum(solved) / len(solved)
    assert (
        f"{len(solved)} of {len(errors)} states solved, average absolute deviation "
        f"{aard:.2f} %, largest error {worst:.2f} %, mean signed error {bias:.2f} %"
        in KEY
    )
    # The same numbers as the protected record the Validation page reads.
    record = next(
        system["production_selected_bubble_metrics"]
        for system in SUMMARY["systems"]
        if system["system_id"] == "ch4_c2"
    )
    assert record["success_count"] == len(solved)
    assert record["pressure_aard_percent"] == pytest.approx(aard, rel=1e-6)

    # Error pattern: small below 4 MPa, negative above it, worst near 6.9 MPa.
    low = [
        abs(value)
        for state, value in errors.items()
        if value is not None and _points()[state].pressure_pa < 4.0e6
    ]
    assert max(low) < 0.31
    above = {
        state: _error_percent(state, newton=True)
        for state in errors
        if _points()[state].pressure_pa > 4.0e6
    }
    converged_above = {s: v for s, v in above.items() if v is not None}
    assert all(value < 0 for value in converged_above.values())
    worst_state = min(converged_above, key=converged_above.__getitem__)
    assert _points()[worst_state].pressure_pa / 1e6 == pytest.approx(6.9, abs=0.05)
    assert f"about {converged_above[worst_state]:.1f} % near 6.9 MPa" in KEY


def test_part_d_not_found_states() -> None:
    not_found = sorted(
        state
        for state in _points()
        if _record_bubble(state, newton=False).pressure_pa is None
    )
    assert not_found == ["009", "012", "013", "015", "016", "017"]
    assert "(009, 012, 013, 015, 016, 017)" in KEY
    for state in not_found:
        point = _points()[state]
        assert point.temperature_k == pytest.approx(T, abs=0.02)
        assert point.pressure_pa > 5.0e6
        reason = _record_bubble(state, newton=False).failure_reason or ""
        assert "bracket" in reason
    rescued = [s for s in not_found if _record_bubble(s, newton=True).pressure_pa]
    assert rescued == ["009", "013", "015", "016"]
    assert (
        "4 of them converge (009, 013, 015, 016) and 2 still do not (012, 017)" in KEY
    )


def test_part_d_first_bubble_composition_of_state_008() -> None:
    result = _record_bubble("008", newton=False)
    measured = _points()["008"].vapor_mole_fractions[0]
    assert (
        f"*y*(C1) = {result.incipient_composition[0]:.4f} against {measured:.4f}" in KEY
    )


def test_part_e_kij_raises_the_bubble_pressure() -> None:
    point = _points()["008"]
    kij = 0.01
    interactions = {("Methane", "Ethane"): kij, ("Ethane", "Methane"): kij}
    with_kij = calculate_saturation_pressure(
        _binary(point.liquid_mole_fractions[0]),
        point.temperature_k,
        SaturationKind.BUBBLE_POINT,
        binary_interactions=interactions,
        saturation_newton_enabled=True,
    )
    without = _record_bubble("008", newton=False)
    assert with_kij.pressure_pa is not None and without.pressure_pa is not None
    assert with_kij.pressure_pa > without.pressure_pa
    error = 100.0 * (with_kij.pressure_pa - point.pressure_pa) / point.pressure_pa
    assert (
        f"rises from {without.pressure_pa / 1e6:.3f} to "
        f"{with_kij.pressure_pa / 1e6:.3f} MPa, which moves the error from "
        f"{_error_percent('008', newton=False):+.2f} % to {error:+.2f} %" in KEY
    )


def test_no_dew_pressure_is_quoted() -> None:
    # P2 is changing how ambiguous dew states are reported, so the lab compares
    # bubble pressures and flash compositions only.
    lowered = KEY.lower()
    assert "dew pressure of" not in lowered
    assert "quotes no dew pressures" in KEY
