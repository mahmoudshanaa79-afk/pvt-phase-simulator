"""Immutable scientific models for pure-component property data."""

import re
from enum import StrEnum
from typing import Final
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_PROVENANCE_PLACEHOLDERS: Final = frozenset(
    {
        "n/a",
        "na",
        "none",
        "null",
        "unknown",
        "unspecified",
        "not available",
        "not applicable",
        "missing",
        "tbd",
        "to be determined",
    }
)
_DOI_IDENTIFIER_PATTERN: Final = re.compile(
    r"10\.\d{4,9}/(?=[-._;()/:a-z0-9]*[a-z0-9])[-._;()/:a-z0-9]+\Z",
    re.IGNORECASE,
)


def _normalized_provenance_value(value: str) -> str:
    """Normalize a complete provenance field for placeholder comparison."""

    return " ".join(value.strip().casefold().split())


def _is_provenance_placeholder(value: str) -> bool:
    return _normalized_provenance_value(value) in _PROVENANCE_PLACEHOLDERS


def _is_valid_provenance_url(value: str) -> bool:
    if any(character.isspace() for character in value) or "\\" in value:
        return False
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError:
        return False
    return parsed.scheme.casefold() in {"http", "https"} and bool(hostname)


def _is_valid_doi_identifier(value: str) -> bool:
    return _DOI_IDENTIFIER_PATTERN.fullmatch(value) is not None


class PropertySourceStatus(StrEnum):
    """Verification status for component-property source metadata."""

    PROVISIONAL = "provisional"
    VERIFIED = "verified"


class ComponentPropertyName(StrEnum):
    """Canonical names for scientific properties consumed by the simulator."""

    CRITICAL_TEMPERATURE = "critical_temperature"
    CRITICAL_PRESSURE = "critical_pressure"
    ACENTRIC_FACTOR = "acentric_factor"


class ComponentPropertyProvenance(BaseModel):
    """Immutable source metadata for one exact component-property value."""

    model_config = ConfigDict(frozen=True)

    property_name: ComponentPropertyName
    status: PropertySourceStatus
    source_reference_name: str | None = None
    property_source_identity: str | None = None
    citation_text: str | None = None
    url: str | None = None
    doi: str | None = None
    edition_or_version: str | None = None
    notes: str | None = None
    original_unit: str | None = None
    canonical_unit: str = Field(min_length=1)
    conversion: str | None = None

    @field_validator(
        "source_reference_name",
        "property_source_identity",
        "citation_text",
        "url",
        "doi",
        mode="before",
    )
    @classmethod
    def trim_traceability_fields(cls, value: object) -> object:
        """Trim traceability text while preserving non-string type validation."""

        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @model_validator(mode="after")
    def validate_confirmed_source(self) -> "ComponentPropertyProvenance":
        """Require structurally traceable metadata before marking VERIFIED."""

        if self.status is not PropertySourceStatus.VERIFIED:
            return self
        source_name = self.source_reference_name
        if source_name is None or _is_provenance_placeholder(source_name):
            raise ValueError("verified provenance requires a meaningful source name.")

        free_text_evidence = (
            self.property_source_identity,
            self.citation_text,
        )
        if any(
            value is not None and _is_provenance_placeholder(value)
            for value in free_text_evidence
        ):
            raise ValueError(
                "verified provenance evidence must not be a placeholder value."
            )

        if self.url is not None:
            if _is_provenance_placeholder(self.url) or not _is_valid_provenance_url(
                self.url
            ):
                raise ValueError(
                    "verified provenance URL must be an absolute HTTP(S) URL "
                    "with a host."
                )
        if self.doi is not None:
            if _is_provenance_placeholder(self.doi) or not _is_valid_doi_identifier(
                self.doi
            ):
                raise ValueError(
                    "verified provenance DOI must be a canonical 10.<registrant>/"
                    "<suffix> identifier."
                )

        # This gate establishes software traceability only. It does not
        # authenticate the source or its scientific quality.
        if not any((*free_text_evidence, self.url, self.doi)):
            raise ValueError(
                "verified provenance requires a citation or stable source identity."
            )
        return self


class ComponentPropertyProvenanceSet(BaseModel):
    """Property-specific provenance for every EOS input on a component."""

    model_config = ConfigDict(frozen=True)

    critical_temperature: ComponentPropertyProvenance
    critical_pressure: ComponentPropertyProvenance
    acentric_factor: ComponentPropertyProvenance

    @model_validator(mode="after")
    def validate_property_names(self) -> "ComponentPropertyProvenanceSet":
        """Prevent source records from being attached to the wrong property."""

        expected = (
            (self.critical_temperature, ComponentPropertyName.CRITICAL_TEMPERATURE),
            (self.critical_pressure, ComponentPropertyName.CRITICAL_PRESSURE),
            (self.acentric_factor, ComponentPropertyName.ACENTRIC_FACTOR),
        )
        if any(record.property_name is not name for record, name in expected):
            raise ValueError("property provenance is attached to the wrong field.")
        return self


class Component(BaseModel):
    """Immutable pure-component properties in SI units."""

    model_config = ConfigDict(frozen=True, allow_inf_nan=False)

    name: str = Field(min_length=1)
    critical_temperature_k: float = Field(gt=0)
    critical_pressure_pa: float = Field(gt=0)
    acentric_factor: float
    provenance: ComponentPropertyProvenanceSet | None = None
