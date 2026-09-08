"""Bounded pressure and temperature sweeps over the existing verified flash API.

No thermodynamic relation is implemented, restated, or approximated here. Each
swept point is one call into the audited production flash entry point through the
same validated boundary the single-case UI already uses. This module only chooses
the abscissae, selects public result fields, and records a failed point as
failed.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Final, Literal

from pvt_phase_simulator.eos.flash import TwoPhaseFlashResult, calculate_two_phase_flash
from pvt_phase_simulator_ui.adapters import (
    FlashCallable,
    InputValidationError,
    ScientificInputs,
    adapt_flash_result,
    flash_presentation_kind,
    validate_scientific_inputs,
)
from pvt_phase_simulator_ui.units import (
    PressureUnit,
    TemperatureUnit,
    pressure_from_pa,
)

#: Sweeps are an engineering overview, not a continuation study. The bounds keep
#: a hosted session responsive and make the cost of a run predictable.
MIN_SWEEP_POINTS: Final = 2
MAX_SWEEP_POINTS: Final = 60
DEFAULT_SWEEP_POINTS: Final = 21

SweepKind = Literal["pressure", "temperature"]
PointStatus = Literal["calculated", "failed"]

#: Progress reporting seam: called with (completed, total) after each point.
ProgressCallback = Callable[[int, int], None]


class SweepValidationError(ValueError):
    """A sweep request is invalid before any production call is attempted."""


def sweep_axis_values(start: float, end: float, points: int) -> tuple[float, ...]:
    """Return evenly spaced abscissae whose first and last values are exact.

    Accumulating ``start + index * step`` would leave the final point a rounding
    error away from the requested end, so the endpoint is written verbatim.
    """

    if points == 1:
        return (float(start),)
    step = (float(end) - float(start)) / (points - 1)
    interior = tuple(float(start) + step * index for index in range(points - 1))
    return (*interior, float(end))


@dataclass(frozen=True, slots=True)
class SweepRequest:
    """A validated sweep specification."""

    kind: SweepKind
    composition_mol_percent: tuple[float, float, float]
    fixed_temperature: float | None
    fixed_pressure: float | None
    start: float
    end: float
    points: int
    temperature_unit: TemperatureUnit = TemperatureUnit.KELVIN
    pressure_unit: PressureUnit = PressureUnit.MPA

    @property
    def axis_label(self) -> str:
        unit = self.pressure_unit if self.kind == "pressure" else self.temperature_unit
        return f"{self.kind.capitalize()} ({unit.value})"

    def axis_values(self) -> tuple[float, ...]:
        return sweep_axis_values(self.start, self.end, self.points)

    def state_at(self, value: float) -> tuple[float, float]:
        """Return a state in the request's explicitly recorded field units."""

        if self.kind == "pressure":
            assert self.fixed_temperature is not None
            return self.fixed_temperature, value
        assert self.fixed_pressure is not None
        return value, self.fixed_pressure


@dataclass(frozen=True, slots=True)
class SweepPoint:
    """One swept state and the public fields the production result supplied."""

    index: int
    temperature_k: float
    pressure_pa: float
    status: PointStatus
    phase_state: str | None
    convergence_status: str | None
    stability_status: str | None
    vapor_fraction: float | None
    liquid_fraction: float | None
    liquid_z: float | None
    vapor_z: float | None
    single_phase_z: float | None
    iteration_count: int | None
    failure_reason: str | None
    error: str | None

    @property
    def pressure_mpa(self) -> float:
        """Compatibility presentation of the canonical pressure in MPa."""

        return pressure_from_pa(self.pressure_pa, PressureUnit.MPA)


@dataclass(frozen=True, slots=True)
class SweepResult:
    """A completed sweep: every requested point, successful or not."""

    request: SweepRequest
    points: tuple[SweepPoint, ...]

    @property
    def calculated_count(self) -> int:
        return sum(1 for point in self.points if point.status == "calculated")

    @property
    def failed_count(self) -> int:
        return sum(1 for point in self.points if point.status == "failed")

    def abscissae(self) -> tuple[float, ...]:
        """The requested swept coordinates in their explicitly recorded unit."""

        return self.request.axis_values()


def _validate_axis(
    start: float, end: float, points: int, *, require_positive: bool
) -> tuple[float, float, int]:
    if isinstance(points, bool) or not isinstance(points, int):
        raise SweepValidationError("Number of points must be an integer.")
    if points < MIN_SWEEP_POINTS or points > MAX_SWEEP_POINTS:
        raise SweepValidationError(
            f"Number of points must be between {MIN_SWEEP_POINTS} "
            f"and {MAX_SWEEP_POINTS}."
        )
    first = float(start)
    last = float(end)
    if not isfinite(first) or not isfinite(last):
        raise SweepValidationError("Sweep bounds must be finite.")
    if require_positive and (first <= 0.0 or last <= 0.0):
        raise SweepValidationError("Sweep bounds must be positive.")
    if first == last:
        raise SweepValidationError("Sweep start and end must differ.")
    return first, last, points


def validate_sweep_request(
    kind: SweepKind,
    composition_mol_percent: Sequence[float],
    *,
    fixed_value: float,
    start: float,
    end: float,
    points: int,
    temperature_unit: TemperatureUnit | str = TemperatureUnit.KELVIN,
    pressure_unit: PressureUnit | str = PressureUnit.MPA,
) -> SweepRequest:
    """Validate a sweep before any production call is attempted.

    Composition and the fixed variable are checked by the same boundary the
    single-case UI uses, evaluated at the first swept state.
    """

    if kind not in ("pressure", "temperature"):
        raise SweepValidationError("Sweep kind must be 'pressure' or 'temperature'.")
    first, last, count = _validate_axis(
        start, end, points, require_positive=kind == "pressure"
    )

    fixed = float(fixed_value)
    if not isfinite(fixed):
        raise SweepValidationError(
            "Fixed temperature must be finite."
            if kind == "pressure"
            else "Fixed pressure must be finite."
        )

    try:
        selected_temperature_unit = TemperatureUnit(temperature_unit)
        selected_pressure_unit = PressureUnit(pressure_unit)
    except ValueError as error:
        raise SweepValidationError(str(error)) from error
    states = (
        (fixed, first) if kind == "pressure" else (first, fixed),
        (fixed, last) if kind == "pressure" else (last, fixed),
    )
    try:
        validated_states = tuple(
            validate_scientific_inputs(
                composition_mol_percent,
                temperature,
                pressure,
                temperature_unit=selected_temperature_unit,
                pressure_unit=selected_pressure_unit,
            )
            for temperature, pressure in states
        )
    except InputValidationError as error:
        raise SweepValidationError(str(error)) from error
    validated = validated_states[0]

    return SweepRequest(
        kind=kind,
        composition_mol_percent=validated.composition_mol_percent,
        fixed_temperature=fixed if kind == "pressure" else None,
        fixed_pressure=None if kind == "pressure" else fixed,
        start=first,
        end=last,
        points=count,
        temperature_unit=selected_temperature_unit,
        pressure_unit=selected_pressure_unit,
    )


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _failed_point(
    index: int,
    inputs: ScientificInputs,
    error: str,
) -> SweepPoint:
    """A point the production API could not evaluate stays explicitly failed."""

    return SweepPoint(
        index=index,
        temperature_k=inputs.temperature_k,
        pressure_pa=inputs.pressure_pa,
        status="failed",
        phase_state=None,
        convergence_status=None,
        stability_status=None,
        vapor_fraction=None,
        liquid_fraction=None,
        liquid_z=None,
        vapor_z=None,
        single_phase_z=None,
        iteration_count=None,
        failure_reason=None,
        error=error,
    )


def _adapt_point(
    index: int, inputs: ScientificInputs, result: TwoPhaseFlashResult
) -> SweepPoint:
    """Select public fields; a structured failure remains a failure."""

    view = adapt_flash_result(result)
    presentation = flash_presentation_kind(result)
    stability = getattr(getattr(result, "phase_stability", None), "status", None)
    status: PointStatus = "failed" if presentation == "error" else "calculated"
    return SweepPoint(
        index=index,
        temperature_k=inputs.temperature_k,
        pressure_pa=inputs.pressure_pa,
        status=status,
        phase_state=_enum_value(view.phase_state),
        convergence_status=_enum_value(view.convergence_status),
        stability_status=None if stability is None else _enum_value(stability),
        vapor_fraction=view.vapor_fraction,
        liquid_fraction=view.liquid_fraction,
        liquid_z=view.liquid_z,
        vapor_z=view.vapor_z,
        single_phase_z=view.single_phase_z,
        iteration_count=view.iteration_count,
        failure_reason=view.failure_reason,
        error=None,
    )


def run_sweep(
    request: SweepRequest,
    *,
    flash_api: FlashCallable | None = None,
    progress: ProgressCallback | None = None,
) -> SweepResult:
    """Evaluate every requested state through the existing verified flash API."""

    axis = request.axis_values()
    total = len(axis)
    points: list[SweepPoint] = []

    for index, value in enumerate(axis):
        temperature, pressure = request.state_at(value)
        inputs = validate_scientific_inputs(
            request.composition_mol_percent,
            temperature,
            pressure,
            temperature_unit=request.temperature_unit,
            pressure_unit=request.pressure_unit,
        )
        try:
            api = calculate_two_phase_flash if flash_api is None else flash_api
            result = api(inputs.mixture(), inputs.temperature_k, inputs.pressure_pa)
        except Exception as error:  # noqa: BLE001 - a failed point stays failed
            points.append(
                _failed_point(
                    index,
                    inputs,
                    f"{type(error).__name__}: {error}",
                )
            )
        else:
            points.append(_adapt_point(index, inputs, result))

        if progress is not None:
            progress(index + 1, total)

    return SweepResult(request=request, points=tuple(points))


def run_pressure_sweep(
    composition_mol_percent: Sequence[float],
    *,
    temperature_k: float,
    start_pressure_mpa: float,
    end_pressure_mpa: float,
    points: int = DEFAULT_SWEEP_POINTS,
    flash_api: FlashCallable | None = None,
    progress: ProgressCallback | None = None,
) -> SweepResult:
    """Sweep pressure at fixed temperature through the existing flash API."""

    request = validate_sweep_request(
        "pressure",
        composition_mol_percent,
        fixed_value=temperature_k,
        start=start_pressure_mpa,
        end=end_pressure_mpa,
        points=points,
    )
    return run_sweep(request, flash_api=flash_api, progress=progress)


def run_temperature_sweep(
    composition_mol_percent: Sequence[float],
    *,
    pressure_mpa: float,
    start_temperature_k: float,
    end_temperature_k: float,
    points: int = DEFAULT_SWEEP_POINTS,
    flash_api: FlashCallable | None = None,
    progress: ProgressCallback | None = None,
) -> SweepResult:
    """Sweep temperature at fixed pressure through the existing flash API."""

    request = validate_sweep_request(
        "temperature",
        composition_mol_percent,
        fixed_value=pressure_mpa,
        start=start_temperature_k,
        end=end_temperature_k,
        points=points,
    )
    return run_sweep(request, flash_api=flash_api, progress=progress)
