"""Strict deterministic loader for provenanced pure-component properties."""

from __future__ import annotations

import csv
import re
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path
from types import MappingProxyType
from typing import Final

from pvt_phase_simulator.component_models import (
    Component,
    ComponentPropertyName,
    ComponentPropertyProvenance,
    ComponentPropertyProvenanceSet,
    PropertySourceStatus,
)

DATABASE_HEADER: Final = (
    "component_id",
    "canonical_name",
    "aliases",
    "property",
    "value",
    "unit",
    "source_status",
    "source_reference_name",
    "property_source_identity",
    "citation_text",
    "url",
    "doi",
    "edition_or_version",
    "notes",
    "original_unit",
    "conversion",
)
DEFAULT_COMPONENT_DATABASE_PATH: Final = (
    Path(__file__).resolve().parent / "data" / "component_properties.csv"
)
_ID_PATTERN: Final = re.compile(r"[a-z][a-z0-9_]*\Z")
_CANONICAL_UNITS: Final = {
    ComponentPropertyName.CRITICAL_TEMPERATURE: "K",
    ComponentPropertyName.CRITICAL_PRESSURE: "Pa",
    ComponentPropertyName.ACENTRIC_FACTOR: "1",
}
_PRESSURE_SOURCE_UNIT: Final = "kPa"
_PRESSURE_CONVERSION_EVIDENCE: Final = "1 kPa = 1000 Pa"


class ComponentDatabaseError(ValueError):
    """A component-property database violates its explicit schema."""


class UnsupportedComponentError(LookupError):
    """A requested component identifier or alias is not in the database."""


@dataclass(frozen=True, slots=True)
class ComponentPropertyRecord:
    """One immutable database component and its lookup metadata."""

    component_id: str
    canonical_name: str
    aliases: tuple[str, ...]
    component: Component


@dataclass(frozen=True, slots=True)
class ComponentDatabase:
    """Ordered immutable component records with deterministic exact lookup."""

    records: tuple[ComponentPropertyRecord, ...]
    _lookup: Mapping[str, ComponentPropertyRecord] = field(
        repr=False, compare=False, hash=False
    )

    def get_record(self, identifier_or_alias: str) -> ComponentPropertyRecord:
        """Resolve one deliberate ID, name, or alias without fuzzy matching."""

        key = _lookup_key(identifier_or_alias)
        try:
            return self._lookup[key]
        except KeyError as error:
            raise UnsupportedComponentError(
                f"Unsupported component identifier or alias: {identifier_or_alias!r}."
            ) from error

    def get_component(self, identifier_or_alias: str) -> Component:
        """Return the calculation model for a resolved database record."""

        return self.get_record(identifier_or_alias).component

    def list_components(self) -> tuple[ComponentPropertyRecord, ...]:
        """Return records in their deterministic database order."""

        return self.records


@dataclass(slots=True)
class _PendingComponent:
    canonical_name: str
    aliases: tuple[str, ...]
    values: dict[ComponentPropertyName, float] = field(default_factory=dict)
    provenance: dict[ComponentPropertyName, ComponentPropertyProvenance] = field(
        default_factory=dict
    )


def _lookup_key(value: str) -> str:
    key = value.strip().casefold()
    if not key:
        raise UnsupportedComponentError("Component identifier or alias is blank.")
    return key


def _optional(value: str) -> str | None:
    stripped = value.strip()
    return stripped or None


def _aliases(value: str, row_number: int) -> tuple[str, ...]:
    aliases = tuple(item.strip() for item in value.split("|") if item.strip())
    normalized = tuple(item.casefold() for item in aliases)
    if len(normalized) != len(set(normalized)):
        raise ComponentDatabaseError(f"Row {row_number}: duplicate alias in row.")
    return aliases


def _numeric_value(
    text: str, property_name: ComponentPropertyName, row_number: int
) -> float:
    if not text:
        raise ComponentDatabaseError(f"Row {row_number}: missing required value.")
    try:
        value = float(text)
    except ValueError as error:
        raise ComponentDatabaseError(
            f"Row {row_number}: invalid numeric value {text!r}."
        ) from error
    if not isfinite(value):
        raise ComponentDatabaseError(f"Row {row_number}: value must be finite.")
    if (
        property_name
        in {
            ComponentPropertyName.CRITICAL_TEMPERATURE,
            ComponentPropertyName.CRITICAL_PRESSURE,
        }
        and value <= 0.0
    ):
        raise ComponentDatabaseError(
            f"Row {row_number}: {property_name.value} must be greater than zero."
        )
    return value


def _read_rows(path: Path) -> list[tuple[int, dict[str, str]]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as database_file:
            reader = csv.reader(database_file, strict=True)
            rows = [
                (reader.line_num, [cell.strip() for cell in row])
                for row in reader
                if any(cell.strip() for cell in row)
            ]
    except (OSError, UnicodeError, csv.Error) as error:
        raise ComponentDatabaseError(
            f"Could not read database {path}: {error}"
        ) from error
    if not rows:
        raise ComponentDatabaseError("Component database is empty.")
    header_number, header = rows[0]
    if tuple(header) != DATABASE_HEADER:
        raise ComponentDatabaseError(
            f"Row {header_number}: database header must exactly match DATABASE_HEADER."
        )
    parsed: list[tuple[int, dict[str, str]]] = []
    for row_number, row in rows[1:]:
        if len(row) != len(DATABASE_HEADER):
            raise ComponentDatabaseError(
                f"Row {row_number}: expected {len(DATABASE_HEADER)} columns, "
                f"found {len(row)}."
            )
        parsed.append((row_number, dict(zip(DATABASE_HEADER, row, strict=True))))
    return parsed


def _parse_provenance(
    row: dict[str, str],
    property_name: ComponentPropertyName,
    row_number: int,
) -> ComponentPropertyProvenance:
    original_unit = _optional(row["original_unit"])
    conversion = _optional(row["conversion"])
    if (original_unit is None) != (conversion is None):
        raise ComponentDatabaseError(
            f"Row {row_number}: original_unit and conversion must be supplied together."
        )
    if original_unit is not None and (
        property_name is not ComponentPropertyName.CRITICAL_PRESSURE
        or original_unit != _PRESSURE_SOURCE_UNIT
        or conversion != _PRESSURE_CONVERSION_EVIDENCE
    ):
        raise ComponentDatabaseError(
            f"Row {row_number}: unsupported source-unit conversion evidence."
        )
    try:
        status = PropertySourceStatus(row["source_status"])
    except ValueError as error:
        raise ComponentDatabaseError(
            f"Row {row_number}: invalid source status {row['source_status']!r}."
        ) from error
    try:
        return ComponentPropertyProvenance(
            property_name=property_name,
            status=status,
            source_reference_name=_optional(row["source_reference_name"]),
            property_source_identity=_optional(row["property_source_identity"]),
            citation_text=_optional(row["citation_text"]),
            url=_optional(row["url"]),
            doi=_optional(row["doi"]),
            edition_or_version=_optional(row["edition_or_version"]),
            notes=_optional(row["notes"]),
            original_unit=original_unit,
            canonical_unit=row["unit"],
            conversion=conversion,
        )
    except ValueError as error:
        raise ComponentDatabaseError(
            f"Row {row_number}: invalid provenance: {error}"
        ) from error


def _build_records(
    pending: OrderedDict[str, _PendingComponent],
) -> tuple[ComponentPropertyRecord, ...]:
    required = tuple(ComponentPropertyName)
    records: list[ComponentPropertyRecord] = []
    for component_id, item in pending.items():
        missing = tuple(name.value for name in required if name not in item.values)
        if missing:
            raise ComponentDatabaseError(
                f"Component {component_id!r} is missing properties: "
                f"{', '.join(missing)}."
            )
        provenance = ComponentPropertyProvenanceSet(
            critical_temperature=item.provenance[
                ComponentPropertyName.CRITICAL_TEMPERATURE
            ],
            critical_pressure=item.provenance[ComponentPropertyName.CRITICAL_PRESSURE],
            acentric_factor=item.provenance[ComponentPropertyName.ACENTRIC_FACTOR],
        )
        component = Component(
            name=item.canonical_name,
            critical_temperature_k=item.values[
                ComponentPropertyName.CRITICAL_TEMPERATURE
            ],
            critical_pressure_pa=item.values[ComponentPropertyName.CRITICAL_PRESSURE],
            acentric_factor=item.values[ComponentPropertyName.ACENTRIC_FACTOR],
            provenance=provenance,
        )
        records.append(
            ComponentPropertyRecord(
                component_id=component_id,
                canonical_name=item.canonical_name,
                aliases=item.aliases,
                component=component,
            )
        )
    return tuple(records)


def _build_lookup(
    records: tuple[ComponentPropertyRecord, ...],
) -> Mapping[str, ComponentPropertyRecord]:
    lookup: dict[str, ComponentPropertyRecord] = {}
    for record in records:
        for candidate in (record.component_id, record.canonical_name, *record.aliases):
            key = _lookup_key(candidate)
            previous = lookup.get(key)
            if previous is not None and previous.component_id != record.component_id:
                raise ComponentDatabaseError(
                    f"Ambiguous identifier or alias {candidate!r} is shared by "
                    f"{previous.component_id!r} and {record.component_id!r}."
                )
            lookup[key] = record
    return MappingProxyType(lookup)


def load_component_database(path: str | Path | None = None) -> ComponentDatabase:
    """Load, strictly validate, and freeze a component-property CSV database."""

    database_path = DEFAULT_COMPONENT_DATABASE_PATH if path is None else Path(path)
    pending: OrderedDict[str, _PendingComponent] = OrderedDict()
    previous_component_id: str | None = None
    closed_component_ids: set[str] = set()
    for row_number, row in _read_rows(database_path):
        component_id = row["component_id"]
        if not _ID_PATTERN.fullmatch(component_id):
            raise ComponentDatabaseError(
                f"Row {row_number}: invalid component_id {component_id!r}."
            )
        if previous_component_id is not None and component_id != previous_component_id:
            closed_component_ids.add(previous_component_id)
        if component_id in closed_component_ids:
            raise ComponentDatabaseError(
                f"Row {row_number}: duplicate non-contiguous component ID "
                f"{component_id!r}."
            )
        previous_component_id = component_id
        if not row["canonical_name"]:
            raise ComponentDatabaseError(f"Row {row_number}: canonical_name is blank.")
        aliases = _aliases(row["aliases"], row_number)
        try:
            property_name = ComponentPropertyName(row["property"])
        except ValueError as error:
            raise ComponentDatabaseError(
                f"Row {row_number}: unsupported property {row['property']!r}."
            ) from error
        expected_unit = _CANONICAL_UNITS[property_name]
        if row["unit"] != expected_unit:
            raise ComponentDatabaseError(
                f"Row {row_number}: {property_name.value} requires unit "
                f"{expected_unit!r}, found {row['unit']!r}."
            )
        item = pending.get(component_id)
        if item is None:
            item = _PendingComponent(row["canonical_name"], aliases)
            pending[component_id] = item
        elif (item.canonical_name, item.aliases) != (row["canonical_name"], aliases):
            raise ComponentDatabaseError(
                f"Row {row_number}: inconsistent metadata for component "
                f"{component_id!r}."
            )
        if property_name in item.values:
            raise ComponentDatabaseError(
                f"Row {row_number}: duplicate {property_name.value} row for "
                f"component {component_id!r}."
            )
        item.values[property_name] = _numeric_value(
            row["value"], property_name, row_number
        )
        item.provenance[property_name] = _parse_provenance(
            row, property_name, row_number
        )
    records = _build_records(pending)
    if not records:
        raise ComponentDatabaseError("Component database has no property records.")
    return ComponentDatabase(records, _build_lookup(records))


DEFAULT_COMPONENT_DATABASE: Final = load_component_database()


def get_component(identifier_or_alias: str) -> Component:
    """Resolve a component from the default database."""

    return DEFAULT_COMPONENT_DATABASE.get_component(identifier_or_alias)


def resolve_component(identifier_or_alias: str) -> ComponentPropertyRecord:
    """Resolve a component and expose its stable ID and aliases."""

    return DEFAULT_COMPONENT_DATABASE.get_record(identifier_or_alias)


def list_components() -> tuple[ComponentPropertyRecord, ...]:
    """List default records in deterministic CSV order."""

    return DEFAULT_COMPONENT_DATABASE.list_components()
