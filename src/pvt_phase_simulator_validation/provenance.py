"""Immutable source and measurement provenance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ._validation import (
    require_enum,
    require_finite,
    require_non_empty,
    require_optional_non_empty,
)
from .enums import DataClass, UncertaintyKind, ValidationQuantity
from .hashing import normalize_sha256


@dataclass(frozen=True, slots=True)
class CompoundIdentity:
    """A dataset component identifier mapped to publication identifiers."""

    component_id: str
    name: str
    formula: str
    inchikey: str
    cas: str

    def __post_init__(self) -> None:
        for field_name in ("component_id", "name", "formula", "inchikey", "cas"):
            require_non_empty(getattr(self, field_name), field_name)


@dataclass(frozen=True, slots=True)
class OriginalUnit:
    """An original source unit and the context in which it appeared."""

    quantity: ValidationQuantity
    unit: str
    context: str

    def __post_init__(self) -> None:
        require_enum(self.quantity, ValidationQuantity, "quantity")
        require_non_empty(self.unit, "unit")
        require_non_empty(self.context, "context")


@dataclass(frozen=True, slots=True)
class UnitConversion:
    """A textual, auditable declaration of a source-to-SI conversion."""

    quantity: ValidationQuantity
    original_unit: str
    canonical_si_unit: str
    expression: str

    def __post_init__(self) -> None:
        require_enum(self.quantity, ValidationQuantity, "quantity")
        require_non_empty(self.original_unit, "original_unit")
        require_non_empty(self.canonical_si_unit, "canonical_si_unit")
        require_non_empty(self.expression, "expression")
        if self.canonical_si_unit != self.quantity.canonical_si_unit:
            raise ValueError(
                "canonical_si_unit must match the unit declared by quantity"
            )


@dataclass(frozen=True, slots=True)
class Uncertainty:
    """A source-reported uncertainty in the quantity's canonical SI unit."""

    value: float
    kind: UncertaintyKind
    coverage_factor: float | None
    confidence_level_percent: float | None
    source: str

    def __post_init__(self) -> None:
        require_finite(self.value, "uncertainty value")
        if self.value < 0.0:
            raise ValueError("uncertainty value must be non-negative")
        object.__setattr__(self, "value", float(self.value))
        require_enum(self.kind, UncertaintyKind, "uncertainty kind")
        if self.coverage_factor is not None:
            require_finite(self.coverage_factor, "coverage_factor")
            if self.coverage_factor <= 0.0:
                raise ValueError("coverage_factor must be positive when present")
            object.__setattr__(self, "coverage_factor", float(self.coverage_factor))
        if self.confidence_level_percent is not None:
            require_finite(self.confidence_level_percent, "confidence_level_percent")
            if not 0.0 <= self.confidence_level_percent <= 100.0:
                raise ValueError("confidence_level_percent must be between 0 and 100")
            object.__setattr__(
                self,
                "confidence_level_percent",
                float(self.confidence_level_percent),
            )
        require_non_empty(self.source, "uncertainty source")


@dataclass(frozen=True, slots=True)
class SourceManifest:
    """Complete provenance needed to identify a reference source.

    Digest construction validates syntax only. It does not claim that any external
    file has been loaded or verified.
    """

    source_id: str
    citation_text: str
    doi: str | None
    archive_name: str
    archive_url: str
    access_date: date
    raw_sha256: str
    normalized_sha256: str
    raw_snapshot_retained: bool
    raw_snapshot_policy: str
    measurement_methods: tuple[str, ...]
    uncertainty_definition: str | None
    coverage_factor: float | None
    confidence_level_percent: float | None
    original_units: tuple[OriginalUnit, ...]
    unit_conversions: tuple[UnitConversion, ...]
    compound_identities: tuple[CompoundIdentity, ...]
    extraction_method: str
    data_class: DataClass

    def __post_init__(self) -> None:
        require_non_empty(self.source_id, "source_id")
        require_non_empty(self.citation_text, "citation_text")
        require_optional_non_empty(self.doi, "doi")
        require_non_empty(self.archive_name, "archive_name")
        require_non_empty(self.archive_url, "archive_url")
        if type(self.access_date) is not date:
            raise TypeError("access_date must be a date")
        object.__setattr__(self, "raw_sha256", normalize_sha256(self.raw_sha256))
        object.__setattr__(
            self, "normalized_sha256", normalize_sha256(self.normalized_sha256)
        )
        if not isinstance(self.raw_snapshot_retained, bool):
            raise TypeError("raw_snapshot_retained must be a boolean")
        require_non_empty(self.raw_snapshot_policy, "raw_snapshot_policy")
        object.__setattr__(self, "measurement_methods", tuple(self.measurement_methods))
        for method in self.measurement_methods:
            require_non_empty(method, "measurement method")
        require_optional_non_empty(
            self.uncertainty_definition, "uncertainty_definition"
        )
        if self.coverage_factor is not None:
            require_finite(self.coverage_factor, "coverage_factor")
            if self.coverage_factor <= 0.0:
                raise ValueError("coverage_factor must be positive when present")
            object.__setattr__(self, "coverage_factor", float(self.coverage_factor))
        if self.confidence_level_percent is not None:
            require_finite(self.confidence_level_percent, "confidence_level_percent")
            if not 0.0 <= self.confidence_level_percent <= 100.0:
                raise ValueError("confidence_level_percent must be between 0 and 100")
            object.__setattr__(
                self,
                "confidence_level_percent",
                float(self.confidence_level_percent),
            )
        object.__setattr__(self, "original_units", tuple(self.original_units))
        object.__setattr__(self, "unit_conversions", tuple(self.unit_conversions))
        object.__setattr__(self, "compound_identities", tuple(self.compound_identities))
        for original_unit in self.original_units:
            if not isinstance(original_unit, OriginalUnit):
                raise TypeError("original_units must contain OriginalUnit values")
        for conversion in self.unit_conversions:
            if not isinstance(conversion, UnitConversion):
                raise TypeError("unit_conversions must contain UnitConversion values")
        for compound in self.compound_identities:
            if not isinstance(compound, CompoundIdentity):
                raise TypeError(
                    "compound_identities must contain CompoundIdentity values"
                )
        component_ids = tuple(item.component_id for item in self.compound_identities)
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("compound identity component_ids must be unique")
        require_non_empty(self.extraction_method, "extraction_method")
        require_enum(self.data_class, DataClass, "data_class")
