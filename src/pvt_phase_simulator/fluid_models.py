"""Data models for hydrocarbon components and fluid conditions."""

from pydantic import BaseModel, Field


class Component(BaseModel):
    """Physical properties of a pure chemical component."""

    name: str = Field(min_length=1)
    critical_temperature_k: float = Field(gt=0)
    critical_pressure_pa: float = Field(gt=0)
    acentric_factor: float


METHANE = Component(
    name="Methane",
    critical_temperature_k=190.56,
    critical_pressure_pa=4_599_200.0,
    acentric_factor=0.011,
)