"""Explicit failures raised by the validation data contract."""

from __future__ import annotations


class ValidationFrameworkError(ValueError):
    """Base class for invalid validation data or serialized payloads."""


class InvariantViolationError(ValidationFrameworkError):
    """Raised when related validation objects disagree."""


class MixedDataClassError(InvariantViolationError):
    """Raised when experimental and cross-check records are mixed."""


class SchemaVersionError(ValidationFrameworkError):
    """Raised when a serialized contract version is unsupported."""


class UnsupportedValueError(ValidationFrameworkError):
    """Raised for an unknown required enum value."""


class SerializationError(ValidationFrameworkError):
    """Raised when a serialized payload does not match the contract."""


class HashMismatchError(ValidationFrameworkError):
    """Raised when supplied content does not have the expected digest."""
