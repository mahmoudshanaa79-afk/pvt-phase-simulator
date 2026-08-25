"""Pure validation and presentation adapters for the Streamlit application.

This module deliberately contains no thermodynamic equations. Production result
objects remain the sole source of scientific values and statuses.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from math import fsum, isfinite
from pathlib import Path
from typing import Final

from pvt_phase_simulator.eos.critical_point import (
    CriticalPointStatus,
    MixtureCriticalPointResult,
)
from pvt_phase_simulator.eos.flash import TwoPhaseFlashResult, calculate_two_phase_flash
from pvt_phase_simulator.eos.phase_envelope import (
    PhaseEnvelopePoint,
    PhaseEnvelopeResult,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    FluidMixture,
    MixtureComponent,
)
from pvt_phase_simulator.plotting import (
    ValidationPlotRecord,
    load_validation_plot_records,
)

COMPONENT_NAMES: Final = ("Methane", "Ethane", "Propane")
COMPONENTS: Final = (METHANE, ETHANE, PROPANE)
COMPOSITION_TOTAL_MOL_PERCENT: Final = 100.0
COMPOSITION_TOLERANCE_MOL_PERCENT: Final = 1.0e-8
PA_PER_MPA: Final = 1.0e6


class InputValidationError(ValueError):
    """One or more scientific UI inputs are invalid."""


@dataclass(frozen=True, slots=True)
class ScientificInputs:
    """Validated, converted scientific input supplied to production APIs."""

    composition_mol_percent: tuple[float, float, float]
    mole_fractions: tuple[float, float, float]
    temperature_k: float
    pressure_mpa: float
    pressure_pa: float

    @property
    def signature(self) -> tuple[tuple[float, float, float], float, float]:
        """Return a deterministic state key for stale-result detection."""

        return self.mole_fractions, self.temperature_k, self.pressure_pa

    def mixture(self) -> FluidMixture:
        """Build the verified three-component production mixture."""

        return FluidMixture(
            tuple(
                MixtureComponent(component, fraction)
                for component, fraction in zip(
                    COMPONENTS, self.mole_fractions, strict=True
                )
            )
        )


def composition_total(values: Sequence[float]) -> float:
    """Return the exact floating-point sum shown in the UI."""

    return fsum(float(value) for value in values)


def validate_scientific_inputs(
    composition_mol_percent: Sequence[float],
    temperature_k: float,
    pressure_mpa: float,
) -> ScientificInputs:
    """Validate UI units and convert once to immutable production inputs."""

    if len(composition_mol_percent) != len(COMPONENTS):
        raise InputValidationError("Exactly Methane, Ethane, and Propane are required.")
    values = tuple(float(value) for value in composition_mol_percent)
    if not all(isfinite(value) for value in values):
        raise InputValidationError("Composition values must be finite.")
    if any(value < 0.0 for value in values):
        raise InputValidationError("Composition values cannot be negative.")
    if any(value > COMPOSITION_TOTAL_MOL_PERCENT for value in values):
        raise InputValidationError("Each composition value must not exceed 100 mol %.")
    total = composition_total(values)
    if total <= 0.0:
        raise InputValidationError("Composition total must be greater than zero.")
    if abs(total - COMPOSITION_TOTAL_MOL_PERCENT) > COMPOSITION_TOLERANCE_MOL_PERCENT:
        raise InputValidationError(
            "Composition must total 100 mol %. Values are not automatically normalized."
        )
    temperature = float(temperature_k)
    pressure = float(pressure_mpa)
    if not isfinite(temperature) or temperature <= 0.0:
        raise InputValidationError("Temperature must be positive and finite.")
    if not isfinite(pressure) or pressure <= 0.0:
        raise InputValidationError("Pressure must be positive and finite.")
    mole_fractions = tuple(value / 100.0 for value in values)
    return ScientificInputs(
        (values[0], values[1], values[2]),
        (mole_fractions[0], mole_fractions[1], mole_fractions[2]),
        temperature,
        pressure,
        pressure * PA_PER_MPA,
    )


FlashCallable = Callable[[FluidMixture, float, float], TwoPhaseFlashResult]


def run_validated_flash(
    composition_mol_percent: Sequence[float],
    temperature_k: float,
    pressure_mpa: float,
    *,
    flash_api: FlashCallable = calculate_two_phase_flash,
) -> tuple[ScientificInputs, TwoPhaseFlashResult]:
    """Validate before invoking the unchanged production flash API."""

    inputs = validate_scientific_inputs(
        composition_mol_percent, temperature_k, pressure_mpa
    )
    result = flash_api(inputs.mixture(), inputs.temperature_k, inputs.pressure_pa)
    return inputs, result


@dataclass(frozen=True, slots=True)
class FlashView:
    """Lossless selection of public flash fields used by the Overview."""

    phase_state: object
    convergence_status: object
    temperature_k: float
    pressure_pa: float
    vapor_fraction: float | None
    liquid_fraction: float | None
    liquid_composition: tuple[float, ...] | None
    vapor_composition: tuple[float, ...] | None
    liquid_z: float | None
    vapor_z: float | None
    single_phase_z: float | None
    final_k_values: tuple[float, ...] | None
    equilibrium_residuals: tuple[float | None, ...]
    material_balance_residuals: tuple[float, ...]
    iteration_count: int
    failure_reason: str | None


def adapt_flash_result(result: TwoPhaseFlashResult) -> FlashView:
    """Expose public result fields without changing identity or filling gaps."""

    liquid = result.liquid_phase
    vapor = result.vapor_phase
    return FlashView(
        result.phase_state,
        result.convergence_status,
        result.temperature_k,
        result.pressure_pa,
        result.vapor_fraction,
        result.liquid_fraction,
        None if liquid is None else liquid.composition,
        None if vapor is None else vapor.composition,
        None if liquid is None else liquid.selected_compressibility_factor,
        None if vapor is None else vapor.selected_compressibility_factor,
        result.single_phase_root,
        result.final_k_values,
        result.equilibrium_residuals,
        result.material_balance_residuals,
        len(result.iteration_history),
        result.failure_reason,
    )


@dataclass(frozen=True, slots=True)
class CriticalView:
    """Certification-safe selection of a public critical-point result."""

    status: CriticalPointStatus
    certified: bool
    temperature_k: float | None
    pressure_pa: float | None
    lambda_min: float | None
    cubic_coefficient: float | None
    critical_direction: tuple[float, ...] | None
    iterations: int
    termination_reason: str
    jacobian_condition_history: tuple[float, ...]


def adapt_critical_result(result: MixtureCriticalPointResult) -> CriticalView:
    """Certify only a production result whose status is exactly CONVERGED."""

    certified = result.status is CriticalPointStatus.CONVERGED
    return CriticalView(
        result.status,
        certified,
        result.temperature_k if certified else None,
        result.pressure_pa if certified else None,
        result.lambda_min if certified else None,
        result.cubic_coefficient if certified else None,
        result.critical_direction if certified else None,
        result.iterations,
        result.termination_reason,
        result.jacobian_condition_history,
    )


def _converged_pressures_at_temperature(
    result: PhaseEnvelopeResult, temperature_k: float
) -> tuple[float | None, float | None]:
    def interpolate(points: Sequence[PhaseEnvelopePoint]) -> float | None:
        accepted = sorted(
            (
                (float(point.temperature_k), float(point.pressure_pa))
                for point in points
                if str(point.status) == "converged"
            ),
            key=lambda pair: pair[0],
        )
        for left, right in zip(accepted, accepted[1:], strict=False):
            if left[0] <= temperature_k <= right[0] and right[0] != left[0]:
                weight = (temperature_k - left[0]) / (right[0] - left[0])
                return left[1] + weight * (right[1] - left[1])
        for point_temperature, point_pressure in accepted:
            if point_temperature == temperature_k:
                return point_pressure
        return None

    return (
        interpolate(result.bubble_branch.points),
        interpolate(result.dew_branch.points),
    )


def location_relative_to_envelope(
    result: PhaseEnvelopeResult | None, temperature_k: float, pressure_pa: float
) -> str:
    """Describe a state against available converged branch interpolation only."""

    if result is None:
        return "Unavailable until a phase envelope has been calculated."
    bubble, dew = _converged_pressures_at_temperature(result, temperature_k)
    if bubble is None or dew is None:
        return "Unavailable at this temperature from converged envelope points."
    lower, upper = sorted((bubble, dew))
    if lower <= pressure_pa <= upper:
        return "Inside the interpolated two-phase envelope."
    if pressure_pa < lower:
        return "Below both interpolated saturation branches."
    return "Above both interpolated saturation branches."


def status_text(value: object) -> str:
    """Format a public enum or scalar status without reclassifying it."""

    raw = value.value if hasattr(value, "value") else str(value)
    return str(raw).replace("_", " ").title()


def load_module17_records(repository_root: Path) -> tuple[ValidationPlotRecord, ...]:
    """Load the protected Module 17 artifact through the Module 21 adapter."""

    return load_validation_plot_records(
        repository_root / "docs" / "validation" / "module17_vle_validation.csv"
    )


def relative_pressure_error_percent(
    predicted_pa: float, experimental_pa: float
) -> float:
    """Return the documented Module 17 signed relative pressure error."""

    predicted = float(predicted_pa)
    experimental = float(experimental_pa)
    if not all(isfinite(value) for value in (predicted, experimental)):
        raise ValueError("pressures must be finite")
    if experimental <= 0.0:
        raise ValueError("experimental pressure must be positive")
    return 100.0 * (predicted - experimental) / experimental
