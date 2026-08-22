"""Tests for fluid component data models."""

import pytest
from pydantic import ValidationError

from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    Component,
    ComponentPropertyName,
    ComponentPropertyProvenance,
    FluidMixture,
    MixtureComponent,
    PropertySourceStatus,
)


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


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize(
    "field",
    ["critical_temperature_k", "critical_pressure_pa", "acentric_factor"],
)
def test_component_rejects_non_finite_numeric_properties(
    field: str,
    value: float,
) -> None:
    """Every stored scientific property must be finite."""

    values = {
        "name": "Invalid component",
        "critical_temperature_k": 190.56,
        "critical_pressure_pa": 4_599_200.0,
        "acentric_factor": 0.011,
    }
    values[field] = value
    with pytest.raises(ValidationError):
        Component(**values)


def test_component_is_immutable() -> None:
    """A valid component cannot be changed after validation."""

    component = Component(
        name="Test component",
        critical_temperature_k=200.0,
        critical_pressure_pa=5_000_000.0,
        acentric_factor=0.1,
    )
    with pytest.raises(ValidationError):
        component.critical_temperature_k = 250.0


@pytest.mark.parametrize("component", [METHANE, ETHANE, PROPANE])
def test_global_components_are_immutable(component: Component) -> None:
    """Shared component constants cannot be corrupted by assignment."""

    original_name = component.name
    with pytest.raises(ValidationError):
        component.name = "Changed"
    assert component.name == original_name


def test_component_remains_immutable_when_nested_in_a_mixture() -> None:
    """Frozen mixture containers must not expose a mutable nested component."""

    mixture = FluidMixture((MixtureComponent(METHANE, 1.0),))
    with pytest.raises(ValidationError):
        mixture.components[0].component.acentric_factor = 0.5
    assert mixture.components[0].component is METHANE
    assert METHANE.acentric_factor == 0.011


@pytest.mark.parametrize("component", [METHANE, ETHANE, PROPANE])
def test_reference_components_retain_honest_provisional_provenance(
    component: Component,
) -> None:
    """Existing values must clearly retain their unverified source status."""

    assert component.provenance is not None
    records = (
        component.provenance.critical_temperature,
        component.provenance.critical_pressure,
        component.provenance.acentric_factor,
    )
    assert all(record.status is PropertySourceStatus.PROVISIONAL for record in records)
    assert all("source confirmation" in (record.notes or "") for record in records)


def test_component_property_provenance_is_immutable() -> None:
    """Citation records cannot be mutated after attachment to a component."""

    provenance = ComponentPropertyProvenance(
        property_name=ComponentPropertyName.CRITICAL_TEMPERATURE,
        source_reference_name="Local verified reference",
        property_source_identity="Table 1",
        canonical_unit="K",
        notes="Test-only citation metadata.",
        status=PropertySourceStatus.VERIFIED,
    )
    with pytest.raises(ValidationError):
        provenance.source_reference_name = "Changed"
