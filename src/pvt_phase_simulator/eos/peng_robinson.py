"""Peng–Robinson equation-of-state calculations."""


def calculate_kappa(acentric_factor: float) -> float:
    """Calculate the Peng–Robinson kappa parameter."""

    return (
        0.37464
        + 1.54226 * acentric_factor
        - 0.26992 * acentric_factor**2
    )