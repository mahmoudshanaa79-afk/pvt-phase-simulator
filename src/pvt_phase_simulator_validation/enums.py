"""Closed vocabularies in the validation serialization contract."""

from __future__ import annotations

from enum import StrEnum


class DataClass(StrEnum):
    """The scientific role of a reference dataset."""

    EXPERIMENTAL_VALIDATION = "EXPERIMENTAL_VALIDATION"
    NUMERICAL_CROSS_CHECK = "NUMERICAL_CROSS_CHECK"


class CapabilityUnderTest(StrEnum):
    """A solver capability exercised by a reference case."""

    PURE_SATURATION_PRESSURE = "PURE_SATURATION_PRESSURE"
    BUBBLE_POINT = "BUBBLE_POINT"
    DEW_POINT = "DEW_POINT"
    FLASH = "FLASH"
    CRITICAL_POINT = "CRITICAL_POINT"
    COMPRESSIBILITY = "COMPRESSIBILITY"


class ValidationQuantity(StrEnum):
    """A quantity and its structural comparison metadata."""

    canonical_si_unit: str
    relative_error_meaningful: bool
    relative_error_rationale: str

    def __new__(
        cls,
        value: str,
        canonical_si_unit: str,
        relative_error_meaningful: bool,
        relative_error_rationale: str,
    ) -> ValidationQuantity:
        member = str.__new__(cls, value)
        member._value_ = value
        member.canonical_si_unit = canonical_si_unit
        member.relative_error_meaningful = relative_error_meaningful
        member.relative_error_rationale = relative_error_rationale
        return member

    PRESSURE = (
        "PRESSURE",
        "Pa",
        True,
        "Pressure has a meaningful ratio scale away from zero.",
    )
    TEMPERATURE = (
        "TEMPERATURE",
        "K",
        True,
        "Absolute temperature in kelvin has a physical ratio scale.",
    )
    MOLE_FRACTION = (
        "MOLE_FRACTION",
        "1",
        False,
        "Mole fractions approach both zero and one, so percentage error misleads.",
    )
    VAPOR_FRACTION = (
        "VAPOR_FRACTION",
        "1",
        False,
        "Vapor fraction approaches both zero and one, so percentage error misleads.",
    )
    COMPRESSIBILITY_FACTOR = (
        "COMPRESSIBILITY_FACTOR",
        "1",
        True,
        "The compressibility factor has a meaningful dimensionless ratio scale.",
    )
    DENSITY = (
        "DENSITY",
        "kg/m^3",
        True,
        "Density has a meaningful ratio scale away from zero.",
    )


class UncertaintyKind(StrEnum):
    """How a reported uncertainty value is defined."""

    STANDARD = "STANDARD"
    EXPANDED = "EXPANDED"


class PredictionOutcome(StrEnum):
    """Whether a solver returned values or a preserved failure."""

    VALUE = "VALUE"
    FAILURE = "FAILURE"


class ValidationStatus(StrEnum):
    """Allowed interpretation attached to a validation record."""

    AGREES_WITHIN_UNCERTAINTY = "AGREES_WITHIN_UNCERTAINTY"
    OUTSIDE_UNCERTAINTY = "OUTSIDE_UNCERTAINTY"
    AGREES_WITHIN_DECLARED_TOLERANCE = "AGREES_WITHIN_DECLARED_TOLERANCE"
    OUTSIDE_DECLARED_TOLERANCE = "OUTSIDE_DECLARED_TOLERANCE"
    REPORTED_NO_TOLERANCE = "REPORTED_NO_TOLERANCE"
    SOLVER_FAILURE = "SOLVER_FAILURE"
    REFERENCE_UNAVAILABLE = "REFERENCE_UNAVAILABLE"
    EXCLUDED = "EXCLUDED"
