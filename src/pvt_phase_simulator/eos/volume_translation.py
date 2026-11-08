"""Optional Péneloux volume translation for Peng–Robinson volumes.

Owner approval C (8 November 2026). Off by default: no solver in this package
calls this module. It only post-processes a volume the engine already
computed, with the Péneloux convention

    v_translated = v_PR - c_mix,   c_mix = sum_i x_i c_i,

where each shift ``c_i`` is a constant (independent of temperature and
pressure). A constant shift adds the same ``-c_i P / (R T)`` to ``ln phi_i`` in
every phase, so fugacity ratios, K-values, phase splits, compositions and
saturation pressures are exactly those of the untranslated model; only molar
volumes and densities change. ``translated_log_fugacity_coefficients`` exists
to make that cancellation testable.

The shifts are a stated fit, not a published correlation. Each one is anchored
at a single state: the saturated liquid at reduced temperature 0.7 of the
reference equations of state in
``docs/investigations/pure_saturation_reference.csv``. See
``tools/fit_volume_translation.py`` and ``docs/VOLUME_TRANSLATION.md`` for the
held-out errors before and after. There is **no mixture-density
validation**: mixture shifts use the linear rule above without any comparison
with measured mixture densities.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import fsum, isfinite
from types import MappingProxyType
from typing import Final

from pvt_phase_simulator.component_models import Component
from pvt_phase_simulator.physical_constants import UNIVERSAL_GAS_CONSTANT

ANCHOR_REDUCED_TEMPERATURE: Final[float] = 0.7
SHIFT_SOURCE: Final[str] = (
    "Fit anchored at the saturated liquid at T_r = 0.7: c = 1/rho_PR - 1/rho_ref, "
    "with rho_ref from the reference equations of state (CoolProp 6.6.0: "
    "Setzmann-Wagner methane, Bücker-Wagner ethane, Lemmon propane) in "
    "docs/investigations/pure_saturation_reference.csv; "
    "tools/fit_volume_translation.py. Not a published correlation."
)


@dataclass(frozen=True, slots=True)
class VolumeShift:
    """A constant Péneloux shift for one component."""

    component_id: str
    shift_m3_per_mol: float
    anchor_reduced_temperature: float
    source: str

    def __post_init__(self) -> None:
        if not isfinite(self.shift_m3_per_mol):
            raise ValueError("shift_m3_per_mol must be finite.")


def _shift(component_id: str, value: float) -> VolumeShift:
    return VolumeShift(component_id, value, ANCHOR_REDUCED_TEMPERATURE, SHIFT_SOURCE)


#: Shifts in m3/mol, printed by ``tools/fit_volume_translation.py`` and checked
#: against a fresh fit by ``tests/test_volume_translation.py``.
ANCHORED_SHIFTS: Final[Mapping[str, VolumeShift]] = MappingProxyType(
    {
        "methane": _shift("methane", -4.114189956781053e-06),
        "ethane": _shift("ethane", -4.424694988440499e-06),
        "propane": _shift("propane", -4.940671984335855e-06),
    }
)


def _key(component: Component) -> str:
    return component.name.casefold()


def mixture_volume_shift(
    components: Sequence[Component],
    composition: Sequence[float],
    shifts: Mapping[str, VolumeShift] = ANCHORED_SHIFTS,
) -> float:
    """``c_mix = sum_i x_i c_i`` in m3/mol; every component needs a shift."""

    if len(components) != len(composition) or not components:
        raise ValueError("components and composition must be non-empty and aligned.")
    terms = []
    for component, fraction in zip(components, composition, strict=True):
        if not isfinite(fraction) or fraction < 0.0:
            raise ValueError("mole fractions must be finite and non-negative.")
        shift = shifts.get(_key(component))
        if shift is None:
            raise ValueError(f"no volume shift is available for {component.name}.")
        terms.append(fraction * shift.shift_m3_per_mol)
    return fsum(terms)


def eos_molar_volume(
    compressibility_factor: float, temperature_k: float, pressure_pa: float
) -> float:
    """The untranslated PR molar volume ``Z R T / P`` in m3/mol."""

    for name, value in (
        ("compressibility_factor", compressibility_factor),
        ("temperature_k", temperature_k),
        ("pressure_pa", pressure_pa),
    ):
        if not isfinite(value) or value <= 0.0:
            raise ValueError(f"{name} must be finite and positive.")
    return compressibility_factor * UNIVERSAL_GAS_CONSTANT * temperature_k / pressure_pa


def translated_molar_volume(
    compressibility_factor: float,
    temperature_k: float,
    pressure_pa: float,
    components: Sequence[Component],
    composition: Sequence[float],
    shifts: Mapping[str, VolumeShift] = ANCHORED_SHIFTS,
) -> float:
    """``Z R T / P - c_mix`` in m3/mol; raises if the result is not positive."""

    volume = eos_molar_volume(
        compressibility_factor, temperature_k, pressure_pa
    ) - mixture_volume_shift(components, composition, shifts)
    if not volume > 0.0:
        raise ValueError("the translated molar volume is not positive.")
    return volume


def translated_log_fugacity_coefficients(
    log_fugacity_coefficients: Sequence[float],
    temperature_k: float,
    pressure_pa: float,
    components: Sequence[Component],
    shifts: Mapping[str, VolumeShift] = ANCHORED_SHIFTS,
) -> tuple[float, ...]:
    """``ln phi_i - c_i P / (R T)``: the same offset in every phase."""

    if len(log_fugacity_coefficients) != len(components):
        raise ValueError("log fugacity coefficients and components must align.")
    scale = pressure_pa / (UNIVERSAL_GAS_CONSTANT * temperature_k)
    result = []
    for value, component in zip(log_fugacity_coefficients, components, strict=True):
        shift = shifts.get(_key(component))
        if shift is None:
            raise ValueError(f"no volume shift is available for {component.name}.")
        result.append(value - shift.shift_m3_per_mol * scale)
    return tuple(result)
