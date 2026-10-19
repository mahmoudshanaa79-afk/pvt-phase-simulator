"""The Lab 1 answer key must match the unchanged engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from pvt_phase_simulator.eos.flash import calculate_two_phase_flash
from pvt_phase_simulator.eos.saturation_pressure import (
    SaturationKind,
    calculate_saturation_pressure,
)
from pvt_phase_simulator.fluid_models import FluidMixture
from pvt_phase_simulator_ui.adapters import validate_scientific_inputs
from pvt_phase_simulator_ui.envelope_extension import trace_extended_envelope
from pvt_phase_simulator_ui.state import INPUT_EXAMPLES

ROOT = Path(__file__).resolve().parents[1]
LAB = (ROOT / "docs" / "teaching" / "LAB_01_METHANE_PROPANE.md").read_text(
    encoding="utf-8"
)
# Markdown wraps lines; compare against the key with whitespace collapsed.
KEY = " ".join(LAB.split("## Instructor answer key", 1)[1].split())


def _mixture() -> FluidMixture:
    return validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 5.0e6).mixture()


def test_part_a_flash_values() -> None:
    flash = calculate_two_phase_flash(_mixture(), 300.0, 5.0e6)
    assert flash.liquid_phase is not None and flash.vapor_phase is not None
    assert flash.final_k_values is not None
    x = flash.liquid_phase.composition
    y = flash.vapor_phase.composition

    quoted = {
        "β = ": flash.vapor_fraction,
        "*x*(C1) = ": x[0],
        "*y*(C1) = ": y[0],
        "*x*(C3) = ": x[2],
        "*y*(C3) = ": y[2],
    }
    for label, value in quoted.items():
        assert f"{label}{value:.4f}" in KEY, label
    assert f"K(C1) = {flash.final_k_values[0]:.3f}" in KEY
    assert f"K(C3) = {flash.final_k_values[2]:.3f}" in KEY
    liquid_z = flash.liquid_phase.selected_compressibility_factor
    vapor_z = flash.vapor_phase.selected_compressibility_factor
    assert f"Z(liquid) = {liquid_z:.3f}" in KEY
    assert f"Z(vapour) = {vapor_z:.3f}" in KEY
    balance = flash.vapor_fraction * y[0] + (1 - flash.vapor_fraction) * x[0]
    assert balance == pytest.approx(0.5, abs=1e-9)
    assert len(flash.iteration_history) == 15
    assert flash.iteration_history[-1].maximum_fugacity_equilibrium_residual < 1e-8


def test_part_b_envelope_landmarks() -> None:
    extension = trace_extended_envelope(_mixture(), 300.0)
    cricondenbar = max(extension.bubble.points, key=lambda point: point.pressure_pa)
    cricondentherm = max(extension.dew.points, key=lambda point: point.temperature_k)

    assert (
        f"about {cricondenbar.pressure_pa / 1e6:.2f} MPa, at about "
        f"{cricondenbar.temperature_k:.1f} K" in KEY
    )
    assert (
        f"about {cricondentherm.temperature_k:.1f} K, at about "
        f"{cricondentherm.pressure_pa / 1e6:.2f} MPa" in KEY
    )
    seed = INPUT_EXAMPLES[2]
    assert f"{seed.temperature_k:.2f} K and {seed.pressure_pa / 1e6:.3f} MPa" in KEY


def _two_phase(temperature: float, pressure: float) -> bool:
    flash = calculate_two_phase_flash(_mixture(), temperature, pressure)
    return flash.phase_state.value == "two_phase"


def test_part_c_two_phase_range_at_300_k() -> None:
    dew = calculate_saturation_pressure(
        _mixture(), 300.0, SaturationKind.DEW_POINT, saturation_newton_enabled=True
    )
    assert dew.pressure_pa is not None
    assert f"about {dew.pressure_pa / 1e6:.2f} MPa up to about 8.67 MPa" in KEY
    assert _two_phase(300.0, 8.67e6)
    assert not _two_phase(300.0, 8.675e6)


def test_part_d_retrograde_values() -> None:
    lower_dew = calculate_saturation_pressure(
        _mixture(), 325.0, SaturationKind.DEW_POINT, saturation_newton_enabled=True
    )
    assert lower_dew.pressure_pa is not None
    assert f"about {lower_dew.pressure_pa / 1e6:.2f} MPa (the lower dew point)" in KEY
    near_minimum = calculate_two_phase_flash(_mixture(), 325.0, 7.7e6)
    assert near_minimum.vapor_fraction == pytest.approx(0.80, abs=0.005)
    assert "minimum of about 0.80 near 7.7 MPa" in KEY
    inconclusive = calculate_two_phase_flash(_mixture(), 325.0, 7.9e6)
    assert inconclusive.phase_state.value == "inconclusive"
