"""Small shared validators with no scientific-engine dependencies."""

from __future__ import annotations

from enum import Enum
from math import isfinite

from .exceptions import UnsupportedValueError


def require_non_empty(value: str, field_name: str) -> None:
    """Require meaningful, non-whitespace text."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def require_optional_non_empty(value: str | None, field_name: str) -> None:
    """Reject a present but blank optional text field."""

    if value is not None:
        require_non_empty(value, field_name)


def require_finite(value: float, field_name: str) -> None:
    """Require a finite float and reject booleans as numbers."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a real number")
    if not isfinite(value):
        raise ValueError(f"{field_name} must be finite")


def require_enum[EnumT: Enum](
    value: object, enum_type: type[EnumT], field_name: str
) -> None:
    """Require an already-decoded member of a supported enum."""

    if not isinstance(value, enum_type):
        raise UnsupportedValueError(
            f"unsupported {field_name} {value!r}; expected a {enum_type.__name__}"
        )
