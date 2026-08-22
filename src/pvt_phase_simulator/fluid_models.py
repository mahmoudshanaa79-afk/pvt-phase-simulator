"""Data models for hydrocarbon components and fluid conditions."""

from dataclasses import dataclass
from math import fsum, isclose, isfinite
from typing import Final

from pvt_phase_simulator.component_models import (
    Component as Component,
)
from pvt_phase_simulator.component_models import (
    ComponentPropertyName as ComponentPropertyName,
)
from pvt_phase_simulator.component_models import (
    ComponentPropertyProvenance as ComponentPropertyProvenance,
)
from pvt_phase_simulator.component_models import (
    ComponentPropertyProvenanceSet as ComponentPropertyProvenanceSet,
)
from pvt_phase_simulator.component_models import (
    PropertySourceStatus as PropertySourceStatus,
)

MOLE_FRACTION_TOLERANCE: Final = 1e-10


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


# These compatibility constants are loaded from the single canonical CSV source.
# The late import leaves the Component model as the database conversion boundary.
from pvt_phase_simulator.component_database import (  # noqa: E402
    DEFAULT_COMPONENT_DATABASE,
)

METHANE = DEFAULT_COMPONENT_DATABASE.get_component("methane")
ETHANE = DEFAULT_COMPONENT_DATABASE.get_component("ethane")
PROPANE = DEFAULT_COMPONENT_DATABASE.get_component("propane")
