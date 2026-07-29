"""Tests for fluid component data models."""

import pytest
from pydantic import ValidationError

from pvt_phase_simulator.fluid_models import METHANE, Component


def test_methane_properties() -> None:
    """Methane should contain the expected physical properties."""

    assert METHANE.name == "Methane"
    assert METHANE.critical_temperature_k == 190.56
    assert METHANE.critical_pressure_pa == 4_599_200.0
    assert METHANE.acentric_factor == 0.011


def test_component_rejects_negative_critical_temperature() -> None:
    """Critical temperature must be greater than zero."""

    with pytest.raises(ValidationError):
        Component(
            name="Invalid component",
            critical_temperature_k=-100.0,
            critical_pressure_pa=1_000_000.0,
            acentric_factor=0.1,
        )


def test_component_rejects_negative_critical_pressure() -> None:
    """Critical pressure must be greater than zero."""

    with pytest.raises(ValidationError):
        Component(
            name="Invalid component",
            critical_temperature_k=190.56,
            critical_pressure_pa=-1_000_000.0,
            acentric_factor=0.011,
        )
