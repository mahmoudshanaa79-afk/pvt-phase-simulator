"""Pure validation and lossless presentation adapters for the UI boundary."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from math import fsum, isfinite
from pathlib import Path
from statistics import median
from typing import Final, Literal

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
from pvt_phase_simulator_ui.units import (
    PressureUnit,
    TemperatureUnit,
    pressure_from_pa,
    pressure_to_pa,
    temperature_from_k,
    temperature_to_k,
)

COMPONENTS: Final = (METHANE, ETHANE, PROPANE)
COMPONENT_NAMES: Final = tuple(component.name for component in COMPONENTS)
COMPOSITION_TOTAL_MOL_PERCENT: Final = 100.0
COMPOSITION_TOLERANCE_MOL_PERCENT: Final = 1.0e-8

#: The application's supported input range, checked before any engine call.
#: Outside it the engine raises instead of returning a status (below about 1 K
#: and above about 1e12 Pa), and the phase-envelope action, which cold-starts
#: 30 K below the operating temperature, needs more than 30 K. The range is an
#: input limit, not a validated applicability range (that is the Module 17
#: record, shown on the Validation page).
MINIMUM_TEMPERATURE_K: Final = 50.0
MAXIMUM_TEMPERATURE_K: Final = 1000.0
MINIMUM_PRESSURE_PA: Final = 1.0
MAXIMUM_PRESSURE_PA: Final = 1.0e9

#: Binary pairs, as component indices, in the order the kij inputs use.
KIJ_PAIRS: Final = ((0, 1), (0, 2), (1, 2))
KIJ_PAIR_LABELS: Final = ("C1–C2", "C1–C3", "C2–C3")
KIJ_MINIMUM: Final = -0.10
KIJ_MAXIMUM: Final = 0.20
KIJ_STEP: Final = 0.001
ZERO_KIJ: Final = (0.0, 0.0, 0.0)
#: Session keys of the three kij inputs, in ``KIJ_PAIRS`` order.
KIJ_KEYS: Final = ("kij_c1_c2", "kij_c1_c3", "kij_c2_c3")
#: Fitted values quoted to users; tests/test_app_kij_input.py checks them
#: against docs/investigations/kij_study_fit.json.
KIJ_FITTED_C1_C2: Final = 0.0
KIJ_FITTED_C1_C3: Final = 0.0021
KIJ_HELP: Final = (
    "Optional. kij = 0 is the default and the validation reference. Fits to "
    "bubble pressures from one source, May et al. (2015), in "
    "docs/investigations/kij_study.md: C1–C2 0 (no gain over kij = 0) and "
    f"C1–C3 {KIJ_FITTED_C1_C3:+.4f}. A non-zero kij is a fitted, non-predictive "
    "choice, not part of the validated model. A pair whose component is absent "
    "from the mixture has no effect."
)


def pairs_present(fractions: Sequence[float]) -> tuple[bool, bool, bool]:
    """Whether both components of each kij pair have a positive amount."""

    return (
        fractions[0] > 0.0 and fractions[1] > 0.0,
        fractions[0] > 0.0 and fractions[2] > 0.0,
        fractions[1] > 0.0 and fractions[2] > 0.0,
    )


def effective_kij(
    fractions: Sequence[float], kij: Sequence[float]
) -> tuple[float, float, float]:
    """kij with every pair absent from the mixture set to 0."""

    present = pairs_present(fractions)
    return (
        kij[0] if present[0] else 0.0,
        kij[1] if present[1] else 0.0,
        kij[2] if present[2] else 0.0,
    )


def binary_interaction_assumption(
    fractions: Sequence[float], kij: Sequence[float]
) -> str:
    """``kij = 0``, or the user-supplied value of every pair in the mixture."""

    used = effective_kij(fractions, kij)
    if not any(value != 0.0 for value in used):
        return "kij = 0"
    present = pairs_present(fractions)
    text = ", ".join(
        f"{label} = {value:+g}"
        for label, value, here in zip(KIJ_PAIR_LABELS, used, present, strict=True)
        if here
    )
    return f"user-supplied kij: {text}"


class InputValidationError(ValueError):
    """One or more scientific UI inputs are invalid."""


@dataclass(frozen=True, slots=True)
class ScientificInputs:
    """Validated, converted scientific input supplied to production APIs."""

    composition_mol_percent: tuple[float, float, float]
    mole_fractions: tuple[float, float, float]
    temperature_k: float
    pressure_pa: float
    #: User-supplied kij for C1–C2, C1–C3 and C2–C3; zero is the engine default.
    kij: tuple[float, float, float] = ZERO_KIJ

    @property
    def pairs_present(self) -> tuple[bool, bool, bool]:
        """Whether both components of each kij pair are in the mixture."""

        return pairs_present(self.mole_fractions)

    @property
    def effective_kij(self) -> tuple[float, float, float]:
        """The kij that reach the engine: pairs absent from the mixture are 0."""

        return effective_kij(self.mole_fractions, self.kij)

    @property
    def uses_kij(self) -> bool:
        return any(value != 0.0 for value in self.effective_kij)

    def binary_interactions(self) -> dict[tuple[str, str], float] | None:
        """Symmetric engine mapping, or ``None`` (the engine default) at kij = 0."""

        if not self.uses_kij:
            return None
        mapping: dict[tuple[str, str], float] = {}
        for (i, j), value, present in zip(
            KIJ_PAIRS, self.effective_kij, self.pairs_present, strict=True
        ):
            if present:
                mapping[(COMPONENT_NAMES[i], COMPONENT_NAMES[j])] = value
                mapping[(COMPONENT_NAMES[j], COMPONENT_NAMES[i])] = value
        return mapping

    @property
    def binary_interaction_assumption(self) -> str:
        """The kij actually used, as stated in results, exports and reports."""

        return binary_interaction_assumption(self.mole_fractions, self.kij)

    @property
    def model_metadata(self) -> str:
        """Figure metadata; unchanged (``kij=0``) when no kij is set."""

        if not self.uses_kij:
            return "Peng-Robinson EOS; kij=0"
        return f"Peng-Robinson EOS; {self.binary_interaction_assumption}"

    @property
    def pressure_mpa(self) -> float:
        """Compatibility presentation of the canonical pressure in MPa."""

        return pressure_from_pa(self.pressure_pa, PressureUnit.MPA)

    @property
    def signature(
        self,
    ) -> tuple[tuple[float, float, float], float, float, tuple[float, float, float]]:
        return self.mole_fractions, self.temperature_k, self.pressure_pa, self.kij

    def mixture(self) -> FluidMixture:
        return FluidMixture(
            tuple(
                MixtureComponent(component, fraction)
                for component, fraction in zip(
                    COMPONENTS, self.mole_fractions, strict=True
                )
            )
        )


def composition_total(values: Sequence[float]) -> float:
    """Return the floating-point sum displayed at the input boundary."""

    numeric = tuple(float(value) for value in values)
    try:
        return fsum(numeric)
    except (OverflowError, ValueError):
        # Display invalid extreme inputs without allowing fsum's strict overflow
        # handling to escape the ordinary validation path.
        return sum(numeric)


def _temperature_bounds(unit: TemperatureUnit | str) -> str:
    """The supported temperature range in kelvin and, if different, ``unit``."""

    kelvin = f"{MINIMUM_TEMPERATURE_K:g} K and {MAXIMUM_TEMPERATURE_K:g} K"
    try:
        selected = TemperatureUnit(unit)
    except ValueError:
        return kelvin
    if selected is TemperatureUnit.KELVIN:
        return kelvin
    low = temperature_from_k(MINIMUM_TEMPERATURE_K, selected)
    high = temperature_from_k(MAXIMUM_TEMPERATURE_K, selected)
    return f"{kelvin} ({low:g} {selected.value} to {high:g} {selected.value})"


def _pressure_bounds(unit: PressureUnit | str) -> str:
    """The supported pressure range in pascal and, if different, ``unit``."""

    pascal = f"{MINIMUM_PRESSURE_PA:g} Pa and {MAXIMUM_PRESSURE_PA:g} Pa"
    try:
        selected = PressureUnit(unit)
    except ValueError:
        return pascal
    if selected is PressureUnit.PA:
        return pascal
    low = pressure_from_pa(MINIMUM_PRESSURE_PA, selected)
    high = pressure_from_pa(MAXIMUM_PRESSURE_PA, selected)
    return f"{pascal} ({low:g} {selected.value} to {high:g} {selected.value})"


def validate_scientific_inputs(
    composition_mol_percent: Sequence[float],
    temperature: float,
    pressure: float,
    *,
    temperature_unit: TemperatureUnit | str = TemperatureUnit.KELVIN,
    pressure_unit: PressureUnit | str = PressureUnit.MPA,
    kij: Sequence[float] = ZERO_KIJ,
    supported_range: bool = False,
) -> ScientificInputs:
    """Validate and convert user-facing values to the engine's K/Pa contract.

    ``supported_range`` also enforces the application's supported input range.
    Every place a user's values enter the app (the form, sweeps and case files)
    sets it; library callers that only build a mixture need not.
    """

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
    try:
        temperature_k = temperature_to_k(temperature, temperature_unit)
        pressure_pa = pressure_to_pa(pressure, pressure_unit)
    except ValueError as error:
        raise InputValidationError(str(error)) from error
    if temperature_k <= 0.0:
        raise InputValidationError("Temperature must be above absolute zero.")
    if pressure_pa <= 0.0:
        raise InputValidationError("Pressure must be positive.")
    if supported_range and not (
        MINIMUM_TEMPERATURE_K <= temperature_k <= MAXIMUM_TEMPERATURE_K
    ):
        raise InputValidationError(
            "Temperature must be between "
            f"{_temperature_bounds(temperature_unit)}, the application's "
            "supported input range."
        )
    if (
        supported_range
        and not MINIMUM_PRESSURE_PA <= pressure_pa <= MAXIMUM_PRESSURE_PA
    ):
        raise InputValidationError(
            f"Pressure must be between {_pressure_bounds(pressure_unit)}, the "
            "application's supported input range."
        )
    if len(kij) != len(KIJ_PAIRS):
        raise InputValidationError("Exactly three kij values are required.")
    interaction = tuple(float(value) for value in kij)
    for label, value in zip(KIJ_PAIR_LABELS, interaction, strict=True):
        if not isfinite(value) or not KIJ_MINIMUM <= value <= KIJ_MAXIMUM:
            raise InputValidationError(
                f"kij {label} must be between {KIJ_MINIMUM:.2f} and {KIJ_MAXIMUM:.2f}."
            )
    fractions = tuple(value / 100.0 for value in values)
    return ScientificInputs(
        (values[0], values[1], values[2]),
        (fractions[0], fractions[1], fractions[2]),
        temperature_k,
        pressure_pa,
        (interaction[0], interaction[1], interaction[2])
        if any(interaction)
        else ZERO_KIJ,
    )


FlashCallable = Callable[[FluidMixture, float, float], TwoPhaseFlashResult]


def run_validated_flash(
    composition_mol_percent: Sequence[float],
    temperature: float,
    pressure: float,
    *,
    temperature_unit: TemperatureUnit | str = TemperatureUnit.KELVIN,
    pressure_unit: PressureUnit | str = PressureUnit.MPA,
    flash_api: FlashCallable = calculate_two_phase_flash,
) -> tuple[ScientificInputs, TwoPhaseFlashResult]:
    inputs = validate_scientific_inputs(
        composition_mol_percent,
        temperature,
        pressure,
        temperature_unit=temperature_unit,
        pressure_unit=pressure_unit,
    )
    result = flash_api(inputs.mixture(), inputs.temperature_k, inputs.pressure_pa)
    return inputs, result


@dataclass(frozen=True, slots=True)
class FlashView:
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
    """Select public result fields without reclassification or gap filling."""

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


def flash_presentation_kind(
    result: TwoPhaseFlashResult,
) -> Literal["success", "information", "error"]:
    """Map public result semantics to UI styling without reclassifying science."""

    view = adapt_flash_result(result)
    phase_state = getattr(view.phase_state, "value", view.phase_state)
    convergence = getattr(view.convergence_status, "value", view.convergence_status)
    stability = getattr(
        result.phase_stability.status, "value", result.phase_stability.status
    )
    if convergence == "converged":
        return "success"
    if (
        phase_state == "single_phase"
        and convergence == "not_attempted"
        and stability == "stable"
        and view.single_phase_z is not None
    ):
        return "information"
    return "error"


@dataclass(frozen=True, slots=True)
class CriticalView:
    status: CriticalPointStatus
    certified: bool
    temperature_k: float | None
    pressure_pa: float | None
    lambda_min: float | None
    cubic_coefficient: float | None
    scaled_residual_norm: float | None
    critical_direction: tuple[float, ...] | None
    iterations: int
    termination_reason: str
    jacobian_condition_history: tuple[float, ...]


def adapt_critical_result(result: MixtureCriticalPointResult) -> CriticalView:
    """Expose Tc and Pc only for an exactly converged production result."""

    certified = result.status is CriticalPointStatus.CONVERGED
    return CriticalView(
        result.status,
        certified,
        result.temperature_k if certified else None,
        result.pressure_pa if certified else None,
        result.lambda_min if certified else None,
        result.cubic_coefficient if certified else None,
        result.scaled_residual_norm if certified else None,
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
    if result is None:
        return "Unavailable until a phase envelope has been calculated."
    bubble, dew = _converged_pressures_at_temperature(result, temperature_k)
    if bubble is None and dew is None:
        return (
            "No interpolated branch is available at this temperature. "
            f"Bubble branch: {result.bubble_branch.termination_message} "
            f"Dew branch: {result.dew_branch.termination_message}"
        )
    if bubble is None:
        assert dew is not None
        relationship = _relationship_to_branch(pressure_pa, dew, "dew")
        return (
            f"{relationship} Bubble branch unavailable: "
            f"{result.bubble_branch.termination_message}"
        )
    if dew is None:
        relationship = _relationship_to_branch(pressure_pa, bubble, "bubble")
        return (
            f"{relationship} Dew branch unavailable: "
            f"{result.dew_branch.termination_message}"
        )
    lower, upper = sorted((bubble, dew))
    if lower <= pressure_pa <= upper:
        return "Inside the interpolated two-phase envelope."
    if pressure_pa < lower:
        return "Below both interpolated saturation branches."
    return "Above both interpolated saturation branches."


def _relationship_to_branch(
    pressure_pa: float, branch_pressure_pa: float, branch_name: str
) -> str:
    if pressure_pa < branch_pressure_pa:
        return f"Below the interpolated {branch_name} branch."
    if pressure_pa > branch_pressure_pa:
        return f"Above the interpolated {branch_name} branch."
    return f"On the interpolated {branch_name} branch."


def validation_pressure_error_summary(
    records: Sequence[ValidationPlotRecord], direction: str
) -> tuple[int, int, float | None, float | None]:
    """Summarize only pressure-error values present in Module 17 records."""

    if direction not in {"bubble", "dew"}:
        raise ValueError("direction must be 'bubble' or 'dew'")
    values = tuple(
        abs(float(value))
        for record in records
        if (value := getattr(record, f"{direction}_pressure_relative_error"))
        is not None
    )
    if not values:
        return len(records), 0, None, None
    return len(records), len(values), median(values) * 100.0, max(values) * 100.0


def status_text(value: object) -> str:
    raw = value.value if hasattr(value, "value") else str(value)
    return str(raw).replace("_", " ").capitalize()


def load_module17_records(repository_root: Path) -> tuple[ValidationPlotRecord, ...]:
    return load_validation_plot_records(
        repository_root / "docs" / "validation" / "module17_vle_validation.csv"
    )


def relative_pressure_error_percent(
    predicted_pa: float, experimental_pa: float
) -> float:
    predicted = float(predicted_pa)
    experimental = float(experimental_pa)
    if not all(isfinite(value) for value in (predicted, experimental)):
        raise ValueError("pressures must be finite")
    if experimental <= 0.0:
        raise ValueError("experimental pressure must be positive")
    return 100.0 * (predicted - experimental) / experimental
