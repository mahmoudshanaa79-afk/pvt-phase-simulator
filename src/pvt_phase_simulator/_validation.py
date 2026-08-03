"""Shared numerical validation helpers for scientific calculations."""

from math import isfinite


def require_finite(value: float, name: str) -> None:
    """Require a finite numeric value."""

    try:
        finite = isfinite(value)
    except TypeError as error:
        raise ValueError(f"{name} must be a finite number.") from error
    if not finite:
        raise ValueError(f"{name} must be finite.")


def require_positive(value: float, name: str) -> None:
    """Require a finite value greater than zero."""

    require_finite(value, name)
    if value <= 0.0:
        raise ValueError(f"{name} must be greater than zero.")


def require_non_negative(value: float, name: str) -> None:
    """Require a finite value greater than or equal to zero."""

    require_finite(value, name)
    if value < 0.0:
        raise ValueError(f"{name} must be greater than or equal to zero.")
