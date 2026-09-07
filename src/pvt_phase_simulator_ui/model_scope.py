"""Repository-backed model-scope metadata for the presentation layer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pvt_phase_simulator.component_database import resolve_component
from pvt_phase_simulator.component_models import (
    Component,
    ComponentPropertyProvenance,
    PropertySourceStatus,
)
from pvt_phase_simulator.eos.mixing_rules import BinaryInteractionPolicy
from pvt_phase_simulator.experimental_validation import (
    SYSTEM_COMPONENTS,
    load_experimental_vle_dataset,
)
from pvt_phase_simulator_ui.adapters import (
    COMPONENTS,
    load_module17_records,
)
from pvt_phase_simulator_ui.units import PressureUnit, pressure_from_pa

EOS_DISPLAY_NAME: Final = "Peng–Robinson EOS"
VALIDATION_ARTIFACT: Final = Path("docs/validation/module17_vle_validation.csv")
EXPERIMENTAL_DATA: Final = Path("data/experimental/may_2015_ch4_c2_ch4_c3_vle.csv")
EXPERIMENTAL_MANIFEST: Final = Path("data/experimental/may_2015_source_manifest.json")


@dataclass(frozen=True, slots=True)
class RecordedSource:
    """One citation already attached to repository-owned scientific data."""

    name: str
    citation: str
    doi: str | None


@dataclass(frozen=True, slots=True)
class ModelScope:
    """Presentation-only summary assembled from authoritative repository data."""

    eos_name: str
    verified_component_names: tuple[str, ...]
    interaction_policy: BinaryInteractionPolicy
    validation_state_count: int
    validation_system_names: tuple[str, ...]
    validation_temperature_range_k: tuple[float, float]
    validation_pressure_range_pa: tuple[float, float]
    property_sources: tuple[RecordedSource, ...]
    validation_source: RecordedSource
    validation_artifact: Path

    @property
    def validation_pressure_range_mpa(self) -> tuple[float, float]:
        """Compatibility presentation of the recorded canonical Pa range."""

        lower, upper = self.validation_pressure_range_pa
        return (
            pressure_from_pa(lower, PressureUnit.MPA),
            pressure_from_pa(upper, PressureUnit.MPA),
        )


def _property_records(component: Component) -> tuple[ComponentPropertyProvenance, ...]:
    provenance = component.provenance
    if provenance is None:
        return ()
    return (
        provenance.critical_temperature,
        provenance.critical_pressure,
        provenance.acentric_factor,
    )


def _verified_component_names() -> tuple[str, ...]:
    return tuple(
        component.name
        for component in COMPONENTS
        if _property_records(component)
        and all(
            record.status is PropertySourceStatus.VERIFIED
            for record in _property_records(component)
        )
    )


def _property_sources() -> tuple[RecordedSource, ...]:
    sources: dict[tuple[str, str, str | None], RecordedSource] = {}
    for component in COMPONENTS:
        for record in _property_records(component):
            name = record.source_reference_name or "Unspecified source"
            citation = (
                record.citation_text
                or record.property_source_identity
                or record.source_reference_name
                or "Citation unavailable"
            )
            key = (name, citation, record.doi)
            sources[key] = RecordedSource(name, citation, record.doi)
    return tuple(sources.values())


def _validation_system_name(system_id: str) -> str:
    component_ids = SYSTEM_COMPONENTS.get(system_id)
    if component_ids is None:
        return system_id
    return " + ".join(
        resolve_component(component_id).canonical_name for component_id in component_ids
    )


def load_model_scope(repository_root: Path) -> ModelScope:
    """Read model scope and provenance without running a scientific calculation."""

    records = load_module17_records(repository_root)
    dataset = load_experimental_vle_dataset(
        repository_root / EXPERIMENTAL_DATA,
        repository_root / EXPERIMENTAL_MANIFEST,
    )
    temperatures = tuple(record.temperature_k for record in records)
    pressures_pa = tuple(record.experimental_pressure_pa for record in records)
    systems = tuple(dict.fromkeys(record.system_id for record in records))
    source = dataset.source
    return ModelScope(
        eos_name=EOS_DISPLAY_NAME,
        verified_component_names=_verified_component_names(),
        interaction_policy=BinaryInteractionPolicy.DEFAULT_ZERO,
        validation_state_count=len(records),
        validation_system_names=tuple(
            _validation_system_name(item) for item in systems
        ),
        validation_temperature_range_k=(min(temperatures), max(temperatures)),
        validation_pressure_range_pa=(min(pressures_pa), max(pressures_pa)),
        property_sources=_property_sources(),
        validation_source=RecordedSource(
            source.archive_name,
            source.citation,
            source.doi,
        ),
        validation_artifact=VALIDATION_ARTIFACT,
    )
