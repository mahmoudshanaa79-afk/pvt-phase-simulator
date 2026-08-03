"""Data models for hydrocarbon components and fluid conditions."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from math import fsum, isclose, isfinite
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

MOLE_FRACTION_TOLERANCE: Final = 1e-10


class PropertySourceStatus(StrEnum):
    """Verification status for component-property source metadata."""

    PROVISIONAL = "provisional"
    VERIFIED = "verified"


class ComponentPropertyProvenance(BaseModel):
    """Citation metadata kept separate from numerical component properties.

    Optional fields map cleanly to a future versioned CSV or TOML property
    database. Missing fields are not inferred or silently fabricated.
    """

    model_config = ConfigDict(frozen=True)

    source_title: str = Field(min_length=1)
    author_or_organization: str | None = None
    edition_or_version: str | None = None
    table_section_or_record: str | None = None
    retrieval_date: date | None = None
    notes: str | None = None
    status: PropertySourceStatus


class Component(BaseModel):
    """Immutable pure-component properties in SI units.

    Critical temperature is in K, critical pressure is in Pa, and acentric
    factor is dimensionless. Citation metadata is stored separately in
    ``provenance`` and does not participate in EOS equations.
    """

    model_config = ConfigDict(frozen=True, allow_inf_nan=False)

    name: str = Field(min_length=1)
    critical_temperature_k: float = Field(gt=0)
    critical_pressure_pa: float = Field(gt=0)
    acentric_factor: float
    provenance: ComponentPropertyProvenance | None = None


PROVISIONAL_ENGINEERING_PROPERTY_SOURCE = ComponentPropertyProvenance(
    source_title="Unverified standard approximate engineering values",
    notes=(
        "Existing project values retained without modification; exact source "
        "confirmation is required before authoritative scientific use."
    ),
    status=PropertySourceStatus.PROVISIONAL,
)


METHANE = Component(
    name="Methane",
    critical_temperature_k=190.56,
    critical_pressure_pa=4_599_200.0,
    acentric_factor=0.011,
    provenance=PROVISIONAL_ENGINEERING_PROPERTY_SOURCE,
)

# Standard approximate reference values suitable for the current teaching scope.
ETHANE = Component(
    name="Ethane",
    critical_temperature_k=305.32,
    critical_pressure_pa=4_872_000.0,
    acentric_factor=0.099,
    provenance=PROVISIONAL_ENGINEERING_PROPERTY_SOURCE,
)

PROPANE = Component(
    name="Propane",
    critical_temperature_k=369.83,
    critical_pressure_pa=4_248_000.0,
    acentric_factor=0.152,
    provenance=PROVISIONAL_ENGINEERING_PROPERTY_SOURCE,
)


@dataclass(frozen=True, slots=True)
class MixtureComponent:
    """A component and its mole fraction in a fluid mixture."""

    component: Component
    mole_fraction: float

    def __post_init__(self) -> None:
        """Validate the individual mole fraction."""

        if not isfinite(self.mole_fraction):
            raise ValueError("mole_fraction must be finite.")
        if not 0.0 <= self.mole_fraction <= 1.0:
            raise ValueError("mole_fraction must be between zero and one.")


@dataclass(frozen=True, slots=True)
class FluidMixture:
    """An immutable collection of uniquely named mixture components."""

    components: tuple[MixtureComponent, ...]

    def __post_init__(self) -> None:
        """Validate mixture membership and total composition."""

        if not isinstance(self.components, tuple):
            raise ValueError("components must be provided as an immutable tuple.")
        if not self.components:
            raise ValueError("components must not be empty.")

        component_names = [item.component.name.casefold() for item in self.components]
        if len(component_names) != len(set(component_names)):
            raise ValueError("component names must be unique within a mixture.")

        total_mole_fraction = fsum(item.mole_fraction for item in self.components)
        if total_mole_fraction <= 0.0:
            raise ValueError("total mole fraction must be greater than zero.")
        if not isclose(
            total_mole_fraction,
            1.0,
            rel_tol=0.0,
            abs_tol=MOLE_FRACTION_TOLERANCE,
        ):
            raise ValueError("mole fractions must sum to one within tolerance.")
