"""Offline experimental VLE validation against the unchanged production EOS."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from io import StringIO
from math import exp, fsum, isclose, isfinite, log, sqrt
from pathlib import Path
from sys import float_info
from typing import Any, Final, cast

from scipy.optimize import brentq  # type: ignore[import-untyped]

from pvt_phase_simulator.eos.flash import PhaseInteractionProvenance
from pvt_phase_simulator.eos.mixing_rules import (
    BinaryInteractionPolicy,
    calculate_mixture_compressibility_roots,
    calculate_peng_robinson_mixture_parameters,
)
from pvt_phase_simulator.eos.mixture_fugacity import (
    calculate_mixture_root_fugacity_result,
)
from pvt_phase_simulator.eos.saturation_pressure import (
    FUGACITY_EQUILIBRIUM_TOLERANCE,
    INCIPIENT_SUM_TOLERANCE,
    INNER_COMPOSITION_TOLERANCE,
    INNER_LOG_K_TOLERANCE,
    SATURATION_OBJECTIVE_TOLERANCE,
    SaturationKind,
    SaturationPressureEvaluation,
    SaturationStatus,
    calculate_saturation_pressure,
    evaluate_saturation_pressure,
    multicomponent_saturation_is_near_trivial,
    saturation_phase_roles_are_consistent,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    Component,
    FluidMixture,
    MixtureComponent,
)

SYSTEM_COMPONENTS: Final = {
    "ch4_c2": ("methane", "ethane"),
    "ch4_c3": ("methane", "propane"),
}
DEW_DIAGNOSTIC_MINIMUM_PRESSURE_PA: Final = 50_000.0
DEW_DIAGNOSTIC_MAXIMUM_PRESSURE_PA: Final = 15_000_000.0
DEW_DIAGNOSTIC_PRESSURE_STEP_PA: Final = 50_000.0
DEW_DIAGNOSTIC_ROOT_RELATIVE_TOLERANCE: Final = 1e-7
DEW_DIAGNOSTIC_ROOT_ABSOLUTE_TOLERANCE_PA: Final = 1.0
COMPONENT_OBJECTS: Final[dict[str, Component]] = {
    "methane": METHANE,
    "ethane": ETHANE,
    "propane": PROPANE,
}
NORMALIZED_FIELDS: Final = (
    "source_point_id",
    "source_pair_key",
    "system_id",
    "component_1_id",
    "component_2_id",
    "temperature_k",
    "temperature_unit",
    "pressure_kpa",
    "pressure_original_unit",
    "pressure_pa",
    "pressure_canonical_unit",
    "liquid_methane_mole_fraction",
    "liquid_heavy_mole_fraction",
    "vapor_methane_mole_fraction",
    "vapor_heavy_mole_fraction",
    "composition_unit",
    "pressure_expanded_uncertainty_kpa",
    "pressure_expanded_uncertainty_pa",
    "vapor_heavy_expanded_uncertainty",
    "uncertainty_confidence_level_percent",
    "pressure_dataset_number",
    "pressure_source_row",
    "vapor_dataset_number",
    "vapor_source_row",
)


def _finite(value: float, name: str) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite.")


@dataclass(frozen=True, slots=True)
class ExperimentalSource:
    """Immutable provenance for one external experimental source."""

    source_id: str
    citation: str
    doi: str
    archive_name: str
    page_url: str
    json_url: str
    access_date: str
    raw_json_sha256: str
    normalized_csv_sha256: str
    raw_snapshot_retained: bool
    raw_snapshot_policy: str
    pressure_measurement_method: str
    vapor_composition_measurement_method: str
    confidence_level_percent: float

    def __post_init__(self) -> None:
        required = (
            self.source_id,
            self.citation,
            self.doi,
            self.archive_name,
            self.page_url,
            self.json_url,
            self.access_date,
            self.raw_json_sha256,
            self.normalized_csv_sha256,
            self.raw_snapshot_policy,
            self.pressure_measurement_method,
            self.vapor_composition_measurement_method,
        )
        if any(not value.strip() for value in required):
            raise ValueError("experimental source provenance fields must be populated.")
        if self.doi != "10.1021/acs.jced.5b00610":
            raise ValueError("unexpected experimental source DOI.")
        for digest in (self.raw_json_sha256, self.normalized_csv_sha256):
            if len(digest) != 64 or any(c not in "0123456789ABCDEF" for c in digest):
                raise ValueError("source SHA-256 values must be uppercase hexadecimal.")
        if self.confidence_level_percent != 95.0:
            raise ValueError("only the source-reported 95% uncertainty is supported.")


@dataclass(frozen=True, slots=True)
class ExperimentalVLEPoint:
    """One paired and SI-normalized experimental ``p,T,x,y`` state."""

    source_point_id: str
    source_pair_key: str
    system_id: str
    component_ids: tuple[str, str]
    temperature_k: float
    pressure_kpa: float
    pressure_pa: float
    liquid_mole_fractions: tuple[float, float]
    vapor_mole_fractions: tuple[float, float]
    pressure_expanded_uncertainty_kpa: float | None
    pressure_expanded_uncertainty_pa: float | None
    vapor_expanded_uncertainties: tuple[float | None, float | None]
    uncertainty_confidence_level_percent: float | None
    pressure_dataset_number: int
    pressure_source_row: int
    vapor_dataset_number: int
    vapor_source_row: int

    def __post_init__(self) -> None:
        if not self.source_point_id or not self.source_pair_key:
            raise ValueError("source point identity must be populated.")
        expected = SYSTEM_COMPONENTS.get(self.system_id)
        if expected is None or self.component_ids != expected:
            raise ValueError("incorrect component mapping for experimental system.")
        _finite(self.temperature_k, "temperature_k")
        _finite(self.pressure_kpa, "pressure_kpa")
        _finite(self.pressure_pa, "pressure_pa")
        if self.temperature_k <= 0.0 or self.pressure_kpa <= 0.0:
            raise ValueError("experimental temperature and pressure must be positive.")
        if self.pressure_pa != self.pressure_kpa * 1000.0:
            raise ValueError("pressure conversion must be exactly 1 kPa = 1000 Pa.")
        for name, values in (
            ("liquid", self.liquid_mole_fractions),
            ("vapor", self.vapor_mole_fractions),
        ):
            if len(values) != 2 or any(not isfinite(value) for value in values):
                raise ValueError(f"{name} composition must contain two finite values.")
            if any(value < 0.0 or value > 1.0 for value in values):
                raise ValueError(f"{name} mole fractions must be in [0, 1].")
            if not isclose(fsum(values), 1.0, rel_tol=0.0, abs_tol=1e-12):
                raise ValueError(f"{name} mole fractions must sum to one.")
        if self.vapor_mole_fractions[0] <= self.liquid_mole_fractions[0]:
            raise ValueError(
                "vapor methane fraction must exceed liquid methane fraction; "
                "liquid/vapor data may be swapped."
            )
        if (self.pressure_expanded_uncertainty_kpa is None) != (
            self.pressure_expanded_uncertainty_pa is None
        ):
            raise ValueError("pressure uncertainty units must be populated together.")
        if self.pressure_expanded_uncertainty_kpa is not None:
            if self.pressure_expanded_uncertainty_kpa <= 0.0:
                raise ValueError("pressure uncertainty must be positive.")
            if (
                self.pressure_expanded_uncertainty_pa
                != self.pressure_expanded_uncertainty_kpa * 1000.0
            ):
                raise ValueError("pressure uncertainty conversion is inconsistent.")
        if self.vapor_expanded_uncertainties[0] != self.vapor_expanded_uncertainties[1]:
            raise ValueError("binary complementary vapor fractions share uncertainty.")
        if any(
            value is not None and value <= 0.0
            for value in self.vapor_expanded_uncertainties
        ):
            raise ValueError("vapor composition uncertainty must be positive.")
        if any(
            value <= 0
            for value in (
                self.pressure_dataset_number,
                self.pressure_source_row,
                self.vapor_dataset_number,
                self.vapor_source_row,
            )
        ):
            raise ValueError("source dataset and row numbers must be positive.")


@dataclass(frozen=True, slots=True)
class ExperimentalVLEDataset:
    """A validated immutable source and its complete normalized point set."""

    source: ExperimentalSource
    points: tuple[ExperimentalVLEPoint, ...]


class DewRootClass(StrEnum):
    """Position of a root in the independently diagnosed pressure ordering."""

    SINGLE = "SINGLE"
    LOWER = "LOWER"
    UPPER = "UPPER"
    INTERMEDIATE = "INTERMEDIATE"
    UNMATCHED = "UNMATCHED"


class DewFailureClassification(StrEnum):
    """Validation-only interpretation of a production dew failure."""

    NOT_APPLICABLE = "NOT_APPLICABLE"
    PR_ROOT_DEMONSTRATED_PRODUCTION_UNREACHED = (
        "PR_ROOT_DEMONSTRATED_PRODUCTION_UNREACHED"
    )
    NO_PR_ROOT_FOUND_IN_DIAGNOSTIC_SCAN = "NO_PR_ROOT_FOUND_IN_DIAGNOSTIC_SCAN"


@dataclass(frozen=True, slots=True)
class DewDiagnosticRoot:
    """One independently bracketed and refined valid PR dew root."""

    pressure_pa: float
    bracket_pressures_pa: tuple[float, float]
    liquid_composition: tuple[float, ...]
    vapor_root: float
    liquid_root: float
    maximum_fugacity_equilibrium_residual: float


@dataclass(frozen=True, slots=True)
class DewBranchDiagnostic:
    """Read-only PR dew-root landscape at one experimental ``T,y`` state."""

    scan_pressure_bounds_pa: tuple[float, float]
    scan_pressure_step_pa: float
    roots: tuple[DewDiagnosticRoot, ...]
    multiple_dew_roots_detected: bool
    production_selected_root_class: DewRootClass | None
    nearest_pr_root_to_experiment_pressure_pa: float | None
    nearest_pr_root_to_experiment_relative_error: float | None
    nearest_pr_root_class: DewRootClass | None
    failure_classification: DewFailureClassification


@dataclass(frozen=True, slots=True)
class ValidationDirectionResult:
    """Bubble- or dew-direction comparison for one source state."""

    status: str
    failure_reason: str | None
    predicted_pressure_pa: float | None
    pressure_error_pa: float | None
    pressure_relative_error: float | None
    pressure_percent_error: float | None
    pressure_uncertainty_normalized_residual: float | None
    predicted_composition: tuple[float, ...]
    composition_errors: tuple[float, ...]
    maximum_absolute_composition_error: float | None
    maximum_composition_uncertainty_normalized_residual: float | None
    pressure_solver_iterations: int
    inner_iteration_count: int
    selected_parent_root: float | None
    selected_incipient_root: float | None
    phase_root_ordering_consistent: bool | None
    maximum_fugacity_equilibrium_residual: float | None
    diagnostic_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExperimentalStateResidual:
    """Direct PR fugacity inconsistency at measured ``T,P,x,y``."""

    component_log_fugacity_ratio_residuals: tuple[float, float]
    maximum_absolute_residual: float
    liquid_root: float
    vapor_root: float


@dataclass(frozen=True, slots=True)
class ExperimentalVLEValidationResult:
    """Complete predictive and direct-residual evidence for one source point."""

    point: ExperimentalVLEPoint
    bubble: ValidationDirectionResult
    dew: ValidationDirectionResult
    dew_branch_diagnostic: DewBranchDiagnostic
    experimental_state: ExperimentalStateResidual


@dataclass(frozen=True, slots=True)
class DirectionMetricSummary:
    source_count: int
    success_count: int
    failure_count: int
    pressure_mean_absolute_error_pa: float | None
    pressure_aard_percent: float | None
    pressure_rms_relative_percent: float | None
    pressure_maximum_absolute_relative_percent: float | None
    pressure_bias_percent: float | None
    composition_mean_absolute_component_error: float | None
    composition_maximum_absolute_component_error: float | None
    pressure_uncertainty_available_count: int
    pressure_within_one_uncertainty_count: int
    pressure_within_two_uncertainties_count: int
    composition_uncertainty_available_count: int | None
    composition_within_one_uncertainty_count: int | None
    composition_within_two_uncertainties_count: int | None


@dataclass(frozen=True, slots=True)
class ResidualMetricSummary:
    count: int
    mean: float
    rms: float
    maximum: float


@dataclass(frozen=True, slots=True)
class PressureMetricSummary:
    """Pressure-error metrics over one explicitly identified subset."""

    count: int
    mean_absolute_error_pa: float | None
    aard_percent: float | None
    rms_relative_percent: float | None
    maximum_absolute_relative_percent: float | None
    bias_percent: float | None


@dataclass(frozen=True, slots=True)
class DewBranchDiagnosticSummary:
    """System-level accounting for the validation-only dew-root scan."""

    states_examined: int
    zero_root_state_count: int
    single_root_state_count: int
    multiple_root_state_count: int
    production_success_count: int
    production_single_root_count: int
    production_lower_root_count: int
    production_upper_root_count: int
    production_intermediate_root_count: int
    production_unmatched_root_count: int
    production_failure_count: int
    failed_root_demonstrated_count: int
    failed_no_root_found_in_scan_count: int
    nearest_available_root_all_states: PressureMetricSummary
    nearest_available_root_production_successful_states: PressureMetricSummary


@dataclass(frozen=True, slots=True)
class SensitivityMetricSummary:
    """Effect of retaining the source-recorded 283.38 K point."""

    included_success_count: int
    excluded_success_count: int
    included_aard_percent: float
    excluded_aard_percent: float
    aard_shift_when_excluded_percentage_points: float
    included_rms_relative_percent: float
    excluded_rms_relative_percent: float
    rms_shift_when_excluded_percentage_points: float
    included_bias_percent: float
    excluded_bias_percent: float
    bias_shift_when_excluded_percentage_points: float


@dataclass(frozen=True, slots=True)
class SystemValidationSummary:
    system_id: str
    production_selected_bubble_metrics: DirectionMetricSummary
    production_selected_dew_metrics: DirectionMetricSummary
    dew_branch_diagnostics: DewBranchDiagnosticSummary
    experimental_state_fugacity_residual: ResidualMetricSummary


def _manifest_source(manifest: dict[str, Any]) -> ExperimentalSource:
    return ExperimentalSource(
        source_id=str(manifest["source_id"]),
        citation=str(manifest["citation"]),
        doi=str(manifest["doi"]),
        archive_name=str(manifest["archive_name"]),
        page_url=str(manifest["thermoml_page_url"]),
        json_url=str(manifest["thermoml_json_url"]),
        access_date=str(manifest["access_date"]),
        raw_json_sha256=str(manifest["raw_json_sha256"]),
        normalized_csv_sha256=str(manifest["normalized_csv_sha256"]),
        raw_snapshot_retained=bool(manifest["raw_snapshot_retained"]),
        raw_snapshot_policy=str(manifest["raw_snapshot_policy"]),
        pressure_measurement_method=str(manifest["pressure_measurement_method"]),
        vapor_composition_measurement_method=str(
            manifest["vapor_composition_measurement_method"]
        ),
        confidence_level_percent=float(manifest["confidence_level_percent"]),
    )


def _required_float(row: dict[str, str], field: str) -> float:
    text = row[field].strip()
    if not text:
        raise ValueError(f"{field} must not be missing.")
    try:
        value = float(text)
    except ValueError as error:
        raise ValueError(f"{field} must be numeric.") from error
    _finite(value, field)
    return value


def _optional_float(row: dict[str, str], field: str) -> float | None:
    return _required_float(row, field) if row[field].strip() else None


def _point_from_row(row: dict[str, str]) -> ExperimentalVLEPoint:
    if row["temperature_unit"] != "K":
        raise ValueError("experimental temperature unit must be K.")
    if row["pressure_original_unit"] != "kPa":
        raise ValueError("experimental source pressure unit must be kPa.")
    if row["pressure_canonical_unit"] != "Pa":
        raise ValueError("canonical pressure unit must be Pa.")
    if row["composition_unit"] != "1":
        raise ValueError("composition unit must be dimensionless 1.")
    pressure_uncertainty_kpa = _optional_float(row, "pressure_expanded_uncertainty_kpa")
    pressure_uncertainty_pa = _optional_float(row, "pressure_expanded_uncertainty_pa")
    vapor_heavy_uncertainty = _optional_float(row, "vapor_heavy_expanded_uncertainty")
    return ExperimentalVLEPoint(
        source_point_id=row["source_point_id"].strip(),
        source_pair_key=row["source_pair_key"].strip(),
        system_id=row["system_id"].strip(),
        component_ids=(row["component_1_id"].strip(), row["component_2_id"].strip()),
        temperature_k=_required_float(row, "temperature_k"),
        pressure_kpa=_required_float(row, "pressure_kpa"),
        pressure_pa=_required_float(row, "pressure_pa"),
        liquid_mole_fractions=(
            _required_float(row, "liquid_methane_mole_fraction"),
            _required_float(row, "liquid_heavy_mole_fraction"),
        ),
        vapor_mole_fractions=(
            _required_float(row, "vapor_methane_mole_fraction"),
            _required_float(row, "vapor_heavy_mole_fraction"),
        ),
        pressure_expanded_uncertainty_kpa=pressure_uncertainty_kpa,
        pressure_expanded_uncertainty_pa=pressure_uncertainty_pa,
        vapor_expanded_uncertainties=(
            vapor_heavy_uncertainty,
            vapor_heavy_uncertainty,
        ),
        uncertainty_confidence_level_percent=_optional_float(
            row, "uncertainty_confidence_level_percent"
        ),
        pressure_dataset_number=int(row["pressure_dataset_number"]),
        pressure_source_row=int(row["pressure_source_row"]),
        vapor_dataset_number=int(row["vapor_dataset_number"]),
        vapor_source_row=int(row["vapor_source_row"]),
    )


def load_experimental_vle_dataset(
    csv_path: Path, manifest_path: Path
) -> ExperimentalVLEDataset:
    """Load and strictly validate the offline normalized experimental dataset."""

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("source manifest must be a JSON object.")
    source = _manifest_source(manifest)
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest().upper()
    if digest != source.normalized_csv_sha256:
        raise ValueError(
            "normalized experimental dataset SHA-256 does not match manifest."
        )
    with csv_path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != NORMALIZED_FIELDS:
            raise ValueError("normalized experimental dataset schema is invalid.")
        points = tuple(_point_from_row(dict(row)) for row in reader)
    ids = [point.source_point_id for point in points]
    keys = [(point.system_id, point.source_pair_key) for point in points]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate experimental source point ID.")
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate experimental source pairing key.")
    expected_order = sorted(
        points,
        key=lambda point: (
            point.system_id,
            point.temperature_k,
            point.liquid_mole_fractions[0],
            point.source_point_id,
        ),
    )
    if list(points) != expected_order:
        raise ValueError(
            "normalized experimental points are not deterministically sorted."
        )
    expected_counts = {
        str(key): int(value)
        for key, value in dict(manifest["normalized_point_counts"]).items()
    }
    actual_counts = {
        system: sum(point.system_id == system for point in points)
        for system in SYSTEM_COMPONENTS
    }
    if actual_counts != expected_counts:
        raise ValueError("normalized experimental point counts do not match manifest.")
    return ExperimentalVLEDataset(source=source, points=points)


def _mixture(
    component_ids: tuple[str, str], mole_fractions: tuple[float, float]
) -> FluidMixture:
    return FluidMixture(
        tuple(
            MixtureComponent(COMPONENT_OBJECTS[component_id], mole_fraction)
            for component_id, mole_fraction in zip(
                component_ids, mole_fractions, strict=True
            )
        )
    )


def _direction_result(
    point: ExperimentalVLEPoint, saturation_kind: SaturationKind
) -> ValidationDirectionResult:
    parent = (
        point.liquid_mole_fractions
        if saturation_kind is SaturationKind.BUBBLE_POINT
        else point.vapor_mole_fractions
    )
    expected_incipient = (
        point.vapor_mole_fractions
        if saturation_kind is SaturationKind.BUBBLE_POINT
        else point.liquid_mole_fractions
    )
    result = calculate_saturation_pressure(
        _mixture(point.component_ids, parent),
        point.temperature_k,
        saturation_kind,
    )
    inner_iterations = sum(
        len(evaluation.history) for evaluation in result.evaluation_history
    )
    diagnostics = tuple(sorted({item.code for item in result.diagnostics}))
    if result.status is not SaturationStatus.CONVERGED or result.pressure_pa is None:
        return ValidationDirectionResult(
            status=result.status.value,
            failure_reason=result.failure_reason,
            predicted_pressure_pa=None,
            pressure_error_pa=None,
            pressure_relative_error=None,
            pressure_percent_error=None,
            pressure_uncertainty_normalized_residual=None,
            predicted_composition=(),
            composition_errors=(),
            maximum_absolute_composition_error=None,
            maximum_composition_uncertainty_normalized_residual=None,
            pressure_solver_iterations=result.pressure_solver_iterations,
            inner_iteration_count=inner_iterations,
            selected_parent_root=None,
            selected_incipient_root=None,
            phase_root_ordering_consistent=None,
            maximum_fugacity_equilibrium_residual=None,
            diagnostic_codes=diagnostics,
        )
    pressure_error = result.pressure_pa - point.pressure_pa
    relative_error = pressure_error / point.pressure_pa
    composition_errors = tuple(
        predicted - experimental
        for predicted, experimental in zip(
            result.incipient_composition, expected_incipient, strict=True
        )
    )
    pressure_normalized_residual = (
        pressure_error / point.pressure_expanded_uncertainty_pa
        if point.pressure_expanded_uncertainty_pa is not None
        else None
    )
    composition_normalized_residual = None
    if saturation_kind is SaturationKind.BUBBLE_POINT and all(
        value is not None for value in point.vapor_expanded_uncertainties
    ):
        uncertainties = cast(tuple[float, float], point.vapor_expanded_uncertainties)
        composition_normalized_residual = max(
            abs(error) / uncertainty
            for error, uncertainty in zip(
                composition_errors, uncertainties, strict=True
            )
        )
    parent_root = (
        result.parent_phase.selected_compressibility_factor
        if result.parent_phase is not None
        else None
    )
    incipient_root = (
        result.incipient_phase.selected_compressibility_factor
        if result.incipient_phase is not None
        else None
    )
    if parent_root is None or incipient_root is None:
        ordering = None
    elif saturation_kind is SaturationKind.BUBBLE_POINT:
        ordering = parent_root < incipient_root
    else:
        ordering = parent_root > incipient_root
    return ValidationDirectionResult(
        status=result.status.value,
        failure_reason=None,
        predicted_pressure_pa=result.pressure_pa,
        pressure_error_pa=pressure_error,
        pressure_relative_error=relative_error,
        pressure_percent_error=100.0 * relative_error,
        pressure_uncertainty_normalized_residual=pressure_normalized_residual,
        predicted_composition=result.incipient_composition,
        composition_errors=composition_errors,
        maximum_absolute_composition_error=max(map(abs, composition_errors)),
        maximum_composition_uncertainty_normalized_residual=(
            composition_normalized_residual
        ),
        pressure_solver_iterations=result.pressure_solver_iterations,
        inner_iteration_count=inner_iterations,
        selected_parent_root=parent_root,
        selected_incipient_root=incipient_root,
        phase_root_ordering_consistent=ordering,
        maximum_fugacity_equilibrium_residual=(
            result.maximum_fugacity_equilibrium_residual
        ),
        diagnostic_codes=diagnostics,
    )


def _interaction_provenance(
    mixture: FluidMixture, temperature_k: float
) -> PhaseInteractionProvenance:
    parameters = calculate_peng_robinson_mixture_parameters(
        mixture,
        temperature_k,
        DEW_DIAGNOSTIC_MINIMUM_PRESSURE_PA,
        binary_interaction_policy=BinaryInteractionPolicy.DEFAULT_ZERO,
    )
    return PhaseInteractionProvenance(
        binary_interaction_policy=parameters.binary_interaction_policy,
        binary_interactions=parameters.binary_interactions,
        supplied_binary_interaction_pairs=parameters.supplied_binary_interaction_pairs,
        defaulted_binary_interaction_pairs=(
            parameters.defaulted_binary_interaction_pairs
        ),
    )


def _valid_dew_root(
    evaluation: SaturationPressureEvaluation,
    bracket_pressures_pa: tuple[float, float],
) -> DewDiagnosticRoot | None:
    if (
        not evaluation.converged
        or evaluation.objective is None
        or evaluation.parent_phase is None
        or evaluation.incipient_phase is None
        or evaluation.maximum_log_k_residual is None
        or evaluation.composition_change is None
        or evaluation.incipient_sum_residual is None
    ):
        return None
    maximum_fugacity_residual = max(
        (
            abs(value)
            for value in evaluation.fugacity_equilibrium_residuals
            if value is not None
        ),
        default=0.0,
    )
    phase_roles = saturation_phase_roles_are_consistent(
        SaturationKind.DEW_POINT,
        evaluation.parent_phase.selected_compressibility_factor,
        evaluation.incipient_phase.selected_compressibility_factor,
    )
    if (
        abs(evaluation.objective) > SATURATION_OBJECTIVE_TOLERANCE
        or evaluation.maximum_log_k_residual > INNER_LOG_K_TOLERANCE
        or evaluation.composition_change > INNER_COMPOSITION_TOLERANCE
        or abs(evaluation.incipient_sum_residual) > INCIPIENT_SUM_TOLERANCE
        or maximum_fugacity_residual > FUGACITY_EQUILIBRIUM_TOLERANCE
        or phase_roles is False
        or multicomponent_saturation_is_near_trivial(
            evaluation.parent_composition,
            evaluation.incipient_composition,
            SaturationKind.DEW_POINT,
            evaluation.parent_phase,
            evaluation.incipient_phase,
        )
    ):
        return None
    return DewDiagnosticRoot(
        pressure_pa=evaluation.pressure_pa,
        bracket_pressures_pa=bracket_pressures_pa,
        liquid_composition=evaluation.incipient_composition,
        vapor_root=evaluation.parent_phase.selected_compressibility_factor,
        liquid_root=evaluation.incipient_phase.selected_compressibility_factor,
        maximum_fugacity_equilibrium_residual=maximum_fugacity_residual,
    )


def _root_class(index: int, count: int) -> DewRootClass:
    if count == 1:
        return DewRootClass.SINGLE
    if index == 0:
        return DewRootClass.LOWER
    if index == count - 1:
        return DewRootClass.UPPER
    return DewRootClass.INTERMEDIATE


def _matched_root_class(
    pressure_pa: float | None, roots: tuple[DewDiagnosticRoot, ...]
) -> DewRootClass:
    if pressure_pa is None:
        return DewRootClass.UNMATCHED
    for index, root in enumerate(roots):
        if isclose(
            pressure_pa,
            root.pressure_pa,
            rel_tol=DEW_DIAGNOSTIC_ROOT_RELATIVE_TOLERANCE,
            abs_tol=DEW_DIAGNOSTIC_ROOT_ABSOLUTE_TOLERANCE_PA,
        ):
            return _root_class(index, len(roots))
    return DewRootClass.UNMATCHED


def diagnose_dew_branches(
    point: ExperimentalVLEPoint,
    production_dew: ValidationDirectionResult,
) -> DewBranchDiagnostic:
    """Diagnose valid PR dew roots without changing the production prediction.

    The fixed validation policy scans 50 kPa through 15 MPa at 50 kPa linear
    increments. Every converged objective sign change is independently refined
    in logarithmic pressure and subjected to the production convergence,
    non-triviality, and phase-role gates.
    """

    mixture = _mixture(point.component_ids, point.vapor_mole_fractions)
    provenance = _interaction_provenance(mixture, point.temperature_k)
    cache: dict[float, SaturationPressureEvaluation] = {}

    def evaluate(pressure_pa: float) -> SaturationPressureEvaluation:
        cached = cache.get(pressure_pa)
        if cached is not None:
            return cached
        result = evaluate_saturation_pressure(
            mixture,
            point.temperature_k,
            pressure_pa,
            SaturationKind.DEW_POINT,
            provenance,
            binary_interaction_policy=BinaryInteractionPolicy.DEFAULT_ZERO,
        )
        cache[pressure_pa] = result
        return result

    pressure_count = round(
        (DEW_DIAGNOSTIC_MAXIMUM_PRESSURE_PA - DEW_DIAGNOSTIC_MINIMUM_PRESSURE_PA)
        / DEW_DIAGNOSTIC_PRESSURE_STEP_PA
    )
    pressures = tuple(
        DEW_DIAGNOSTIC_MINIMUM_PRESSURE_PA + index * DEW_DIAGNOSTIC_PRESSURE_STEP_PA
        for index in range(pressure_count + 1)
    )
    scanned = tuple(evaluate(pressure) for pressure in pressures)
    candidates: list[tuple[float, float]] = []
    for evaluation in scanned:
        if (
            evaluation.converged
            and evaluation.objective is not None
            and abs(evaluation.objective) <= SATURATION_OBJECTIVE_TOLERANCE
        ):
            candidates.append((evaluation.pressure_pa, evaluation.pressure_pa))
    exact_pressures = {left for left, right in candidates if left == right}
    for left, right in zip(scanned[:-1], scanned[1:], strict=True):
        if (
            not left.converged
            or not right.converged
            or left.objective is None
            or right.objective is None
            or left.pressure_pa in exact_pressures
            or right.pressure_pa in exact_pressures
        ):
            continue
        if left.objective * right.objective < 0.0:
            candidates.append((left.pressure_pa, right.pressure_pa))

    roots: list[DewDiagnosticRoot] = []
    for lower_pressure, upper_pressure in candidates:
        if lower_pressure == upper_pressure:
            final = evaluate(lower_pressure)
        else:

            class InnerEvaluationFailure(Exception):
                pass

            def objective(log_pressure: float) -> float:
                evaluation = evaluate(exp(log_pressure))
                if not evaluation.converged or evaluation.objective is None:
                    raise InnerEvaluationFailure
                return evaluation.objective

            try:
                root_log_pressure = brentq(
                    objective,
                    log(lower_pressure),
                    log(upper_pressure),
                    xtol=1e-12,
                    rtol=4.0 * float_info.epsilon,
                    maxiter=100,
                )
            except (InnerEvaluationFailure, RuntimeError, ValueError):
                continue
            final = evaluate(exp(root_log_pressure))
        root = _valid_dew_root(final, (lower_pressure, upper_pressure))
        if root is None:
            continue
        if any(
            isclose(
                root.pressure_pa,
                existing.pressure_pa,
                rel_tol=DEW_DIAGNOSTIC_ROOT_RELATIVE_TOLERANCE,
                abs_tol=DEW_DIAGNOSTIC_ROOT_ABSOLUTE_TOLERANCE_PA,
            )
            for existing in roots
        ):
            continue
        roots.append(root)
    ordered_roots = tuple(sorted(roots, key=lambda item: item.pressure_pa))
    production_successful = production_dew.status == SaturationStatus.CONVERGED.value
    production_class = (
        _matched_root_class(production_dew.predicted_pressure_pa, ordered_roots)
        if production_successful
        else None
    )
    nearest = min(
        ordered_roots,
        key=lambda item: (abs(item.pressure_pa - point.pressure_pa), item.pressure_pa),
        default=None,
    )
    nearest_index = ordered_roots.index(nearest) if nearest is not None else None
    if production_successful:
        failure_classification = DewFailureClassification.NOT_APPLICABLE
    elif ordered_roots:
        failure_classification = (
            DewFailureClassification.PR_ROOT_DEMONSTRATED_PRODUCTION_UNREACHED
        )
    else:
        failure_classification = (
            DewFailureClassification.NO_PR_ROOT_FOUND_IN_DIAGNOSTIC_SCAN
        )
    return DewBranchDiagnostic(
        scan_pressure_bounds_pa=(
            DEW_DIAGNOSTIC_MINIMUM_PRESSURE_PA,
            DEW_DIAGNOSTIC_MAXIMUM_PRESSURE_PA,
        ),
        scan_pressure_step_pa=DEW_DIAGNOSTIC_PRESSURE_STEP_PA,
        roots=ordered_roots,
        multiple_dew_roots_detected=len(ordered_roots) > 1,
        production_selected_root_class=production_class,
        nearest_pr_root_to_experiment_pressure_pa=(
            nearest.pressure_pa if nearest is not None else None
        ),
        nearest_pr_root_to_experiment_relative_error=(
            (nearest.pressure_pa - point.pressure_pa) / point.pressure_pa
            if nearest is not None
            else None
        ),
        nearest_pr_root_class=(
            _root_class(nearest_index, len(ordered_roots))
            if nearest_index is not None
            else None
        ),
        failure_classification=failure_classification,
    )


def _experimental_state_residual(
    point: ExperimentalVLEPoint,
) -> ExperimentalStateResidual:
    liquid_mixture = _mixture(point.component_ids, point.liquid_mole_fractions)
    vapor_mixture = _mixture(point.component_ids, point.vapor_mole_fractions)
    liquid_parameters = calculate_peng_robinson_mixture_parameters(
        liquid_mixture,
        point.temperature_k,
        point.pressure_pa,
        binary_interaction_policy=BinaryInteractionPolicy.DEFAULT_ZERO,
    )
    vapor_parameters = calculate_peng_robinson_mixture_parameters(
        vapor_mixture,
        point.temperature_k,
        point.pressure_pa,
        binary_interaction_policy=BinaryInteractionPolicy.DEFAULT_ZERO,
    )
    liquid_roots = calculate_mixture_compressibility_roots(
        liquid_mixture, point.temperature_k, point.pressure_pa
    )
    vapor_roots = calculate_mixture_compressibility_roots(
        vapor_mixture, point.temperature_k, point.pressure_pa
    )
    liquid_root = min(liquid_roots)
    vapor_root = max(vapor_roots)
    liquid = calculate_mixture_root_fugacity_result(liquid_parameters, liquid_root)
    vapor = calculate_mixture_root_fugacity_result(vapor_parameters, vapor_root)
    residuals = tuple(
        log(x_value)
        + liquid_result.log_fugacity_coefficient
        - log(y_value)
        - vapor_result.log_fugacity_coefficient
        for x_value, y_value, liquid_result, vapor_result in zip(
            point.liquid_mole_fractions,
            point.vapor_mole_fractions,
            liquid.component_results,
            vapor.component_results,
            strict=True,
        )
    )
    return ExperimentalStateResidual(
        component_log_fugacity_ratio_residuals=(residuals[0], residuals[1]),
        maximum_absolute_residual=max(map(abs, residuals)),
        liquid_root=liquid_root,
        vapor_root=vapor_root,
    )


def validate_experimental_dataset(
    dataset: ExperimentalVLEDataset,
) -> tuple[ExperimentalVLEValidationResult, ...]:
    """Evaluate every source point without fitting or silently dropping failures."""

    results: list[ExperimentalVLEValidationResult] = []
    for point in dataset.points:
        dew = _direction_result(point, SaturationKind.DEW_POINT)
        results.append(
            ExperimentalVLEValidationResult(
                point=point,
                bubble=_direction_result(point, SaturationKind.BUBBLE_POINT),
                dew=dew,
                dew_branch_diagnostic=diagnose_dew_branches(point, dew),
                experimental_state=_experimental_state_residual(point),
            )
        )
    return tuple(results)


def _direction_summary(
    results: tuple[ExperimentalVLEValidationResult, ...], direction: str
) -> DirectionMetricSummary:
    selected = tuple(getattr(result, direction) for result in results)
    successful = tuple(
        item for item in selected if item.status == SaturationStatus.CONVERGED.value
    )
    relatives = tuple(
        item.pressure_relative_error
        for item in successful
        if item.pressure_relative_error is not None
    )
    pressure_errors = tuple(
        item.pressure_error_pa
        for item in successful
        if item.pressure_error_pa is not None
    )
    component_errors = tuple(
        error for item in successful for error in item.composition_errors
    )
    pressure_one = pressure_two = 0
    composition_one = composition_two = 0
    pressure_uncertainty_available = 0
    composition_uncertainty_available_count = 0
    composition_uncertainty_available = direction == "bubble"
    for result, item in zip(results, selected, strict=True):
        if item.status != SaturationStatus.CONVERGED.value:
            continue
        pressure_uncertainty = result.point.pressure_expanded_uncertainty_pa
        if pressure_uncertainty is not None and item.pressure_error_pa is not None:
            pressure_uncertainty_available += 1
            normalized = abs(item.pressure_error_pa) / pressure_uncertainty
            pressure_one += int(normalized <= 1.0)
            pressure_two += int(normalized <= 2.0)
        if direction == "bubble":
            uncertainties = result.point.vapor_expanded_uncertainties
            if all(value is not None for value in uncertainties):
                composition_uncertainty_available_count += 1
                available_uncertainties = cast(tuple[float, float], uncertainties)
                normalized_composition = max(
                    abs(error) / uncertainty
                    for error, uncertainty in zip(
                        item.composition_errors,
                        available_uncertainties,
                        strict=True,
                    )
                )
                composition_one += int(normalized_composition <= 1.0)
                composition_two += int(normalized_composition <= 2.0)
    count = len(successful)
    return DirectionMetricSummary(
        source_count=len(results),
        success_count=count,
        failure_count=len(results) - count,
        pressure_mean_absolute_error_pa=(
            fsum(map(abs, pressure_errors)) / count if count else None
        ),
        pressure_aard_percent=(
            100.0 * fsum(map(abs, relatives)) / count if count else None
        ),
        pressure_rms_relative_percent=(
            100.0 * sqrt(fsum(value * value for value in relatives) / count)
            if count
            else None
        ),
        pressure_maximum_absolute_relative_percent=(
            100.0 * max(map(abs, relatives)) if count else None
        ),
        pressure_bias_percent=(100.0 * fsum(relatives) / count if count else None),
        composition_mean_absolute_component_error=(
            fsum(map(abs, component_errors)) / len(component_errors)
            if component_errors
            else None
        ),
        composition_maximum_absolute_component_error=(
            max(map(abs, component_errors)) if component_errors else None
        ),
        pressure_uncertainty_available_count=pressure_uncertainty_available,
        pressure_within_one_uncertainty_count=pressure_one,
        pressure_within_two_uncertainties_count=pressure_two,
        composition_uncertainty_available_count=(
            composition_uncertainty_available_count
            if composition_uncertainty_available
            else None
        ),
        composition_within_one_uncertainty_count=(
            composition_one if composition_uncertainty_available else None
        ),
        composition_within_two_uncertainties_count=(
            composition_two if composition_uncertainty_available else None
        ),
    )


def _pressure_metrics(
    pairs: Iterable[tuple[float, float]],
) -> PressureMetricSummary:
    materialized = tuple(pairs)
    if not materialized:
        return PressureMetricSummary(0, None, None, None, None, None)
    errors = tuple(predicted - experimental for predicted, experimental in materialized)
    relatives = tuple(
        error / experimental
        for error, (_, experimental) in zip(errors, materialized, strict=True)
    )
    count = len(materialized)
    return PressureMetricSummary(
        count=count,
        mean_absolute_error_pa=fsum(map(abs, errors)) / count,
        aard_percent=100.0 * fsum(map(abs, relatives)) / count,
        rms_relative_percent=(
            100.0 * sqrt(fsum(value * value for value in relatives) / count)
        ),
        maximum_absolute_relative_percent=100.0 * max(map(abs, relatives)),
        bias_percent=100.0 * fsum(relatives) / count,
    )


def _dew_branch_summary(
    results: tuple[ExperimentalVLEValidationResult, ...],
) -> DewBranchDiagnosticSummary:
    root_counts = tuple(len(result.dew_branch_diagnostic.roots) for result in results)
    production_successful = tuple(
        result
        for result in results
        if result.dew.status == SaturationStatus.CONVERGED.value
    )
    production_failed = tuple(
        result
        for result in results
        if result.dew.status != SaturationStatus.CONVERGED.value
    )

    def class_count(root_class: DewRootClass) -> int:
        return sum(
            result.dew_branch_diagnostic.production_selected_root_class is root_class
            for result in production_successful
        )

    nearest_all = (
        (
            result.dew_branch_diagnostic.nearest_pr_root_to_experiment_pressure_pa,
            result.point.pressure_pa,
        )
        for result in results
        if result.dew_branch_diagnostic.nearest_pr_root_to_experiment_pressure_pa
        is not None
    )
    nearest_successful = (
        (
            result.dew_branch_diagnostic.nearest_pr_root_to_experiment_pressure_pa,
            result.point.pressure_pa,
        )
        for result in production_successful
        if result.dew_branch_diagnostic.nearest_pr_root_to_experiment_pressure_pa
        is not None
    )
    return DewBranchDiagnosticSummary(
        states_examined=len(results),
        zero_root_state_count=sum(count == 0 for count in root_counts),
        single_root_state_count=sum(count == 1 for count in root_counts),
        multiple_root_state_count=sum(count > 1 for count in root_counts),
        production_success_count=len(production_successful),
        production_single_root_count=class_count(DewRootClass.SINGLE),
        production_lower_root_count=class_count(DewRootClass.LOWER),
        production_upper_root_count=class_count(DewRootClass.UPPER),
        production_intermediate_root_count=class_count(DewRootClass.INTERMEDIATE),
        production_unmatched_root_count=class_count(DewRootClass.UNMATCHED),
        production_failure_count=len(production_failed),
        failed_root_demonstrated_count=sum(
            result.dew_branch_diagnostic.failure_classification
            is DewFailureClassification.PR_ROOT_DEMONSTRATED_PRODUCTION_UNREACHED
            for result in production_failed
        ),
        failed_no_root_found_in_scan_count=sum(
            result.dew_branch_diagnostic.failure_classification
            is DewFailureClassification.NO_PR_ROOT_FOUND_IN_DIAGNOSTIC_SCAN
            for result in production_failed
        ),
        nearest_available_root_all_states=_pressure_metrics(nearest_all),
        nearest_available_root_production_successful_states=_pressure_metrics(
            nearest_successful
        ),
    )


def summarize_validation_results(
    results: Iterable[ExperimentalVLEValidationResult],
) -> tuple[SystemValidationSummary, ...]:
    """Calculate explicitly defined metrics independently for each binary."""

    materialized = tuple(results)
    summaries: list[SystemValidationSummary] = []
    for system_id in SYSTEM_COMPONENTS:
        system_results = tuple(
            result for result in materialized if result.point.system_id == system_id
        )
        residuals = tuple(
            result.experimental_state.maximum_absolute_residual
            for result in system_results
        )
        if not residuals:
            raise ValueError(f"validation results contain no {system_id} points.")
        summaries.append(
            SystemValidationSummary(
                system_id=system_id,
                production_selected_bubble_metrics=_direction_summary(
                    system_results, "bubble"
                ),
                production_selected_dew_metrics=_direction_summary(
                    system_results, "dew"
                ),
                dew_branch_diagnostics=_dew_branch_summary(system_results),
                experimental_state_fugacity_residual=ResidualMetricSummary(
                    count=len(residuals),
                    mean=fsum(residuals) / len(residuals),
                    rms=sqrt(
                        fsum(value * value for value in residuals) / len(residuals)
                    ),
                    maximum=max(residuals),
                ),
            )
        )
    return tuple(summaries)


def summarize_283_38_k_sensitivity(
    results: Iterable[ExperimentalVLEValidationResult],
) -> dict[str, SensitivityMetricSummary]:
    """Recompute CH4+C3 production metrics with and without the 283.38 K point."""

    included = tuple(result for result in results if result.point.system_id == "ch4_c3")
    excluded = tuple(
        result for result in included if result.point.temperature_k != 283.38
    )
    if len(included) != 23 or len(excluded) != 22:
        raise ValueError("283.38 K sensitivity requires the complete CH4+C3 dataset.")
    summaries: dict[str, SensitivityMetricSummary] = {}
    for direction in ("bubble", "dew"):
        with_point = _direction_summary(included, direction)
        without_point = _direction_summary(excluded, direction)
        required = (
            with_point.pressure_aard_percent,
            without_point.pressure_aard_percent,
            with_point.pressure_rms_relative_percent,
            without_point.pressure_rms_relative_percent,
            with_point.pressure_bias_percent,
            without_point.pressure_bias_percent,
        )
        if any(value is None for value in required):
            raise ValueError("sensitivity pressure metrics must be available.")
        values = cast(tuple[float, float, float, float, float, float], required)
        summaries[direction] = SensitivityMetricSummary(
            included_success_count=with_point.success_count,
            excluded_success_count=without_point.success_count,
            included_aard_percent=values[0],
            excluded_aard_percent=values[1],
            aard_shift_when_excluded_percentage_points=values[1] - values[0],
            included_rms_relative_percent=values[2],
            excluded_rms_relative_percent=values[3],
            rms_shift_when_excluded_percentage_points=values[3] - values[2],
            included_bias_percent=values[4],
            excluded_bias_percent=values[5],
            bias_shift_when_excluded_percentage_points=values[5] - values[4],
        )
    return summaries


RESULT_FIELDS: Final = (
    "source_point_id",
    "system_id",
    "temperature_k",
    "experimental_pressure_pa",
    "liquid_mole_fractions",
    "vapor_mole_fractions",
    "pressure_expanded_uncertainty_pa",
    "vapor_expanded_uncertainties",
    "bubble_status",
    "bubble_failure_reason",
    "bubble_predicted_pressure_pa",
    "bubble_pressure_error_pa",
    "bubble_pressure_relative_error",
    "bubble_pressure_percent_error",
    "bubble_pressure_uncertainty_normalized_residual",
    "bubble_predicted_vapor_composition",
    "bubble_vapor_composition_errors",
    "bubble_maximum_absolute_composition_error",
    "bubble_maximum_composition_uncertainty_normalized_residual",
    "bubble_pressure_solver_iterations",
    "bubble_inner_iteration_count",
    "bubble_selected_parent_root",
    "bubble_selected_incipient_root",
    "bubble_phase_root_ordering_consistent",
    "bubble_maximum_fugacity_equilibrium_residual",
    "bubble_diagnostic_codes",
    "dew_status",
    "dew_failure_reason",
    "dew_predicted_pressure_pa",
    "dew_pressure_error_pa",
    "dew_pressure_relative_error",
    "dew_pressure_percent_error",
    "dew_pressure_uncertainty_normalized_residual",
    "dew_predicted_liquid_composition",
    "dew_liquid_composition_errors",
    "dew_maximum_absolute_composition_error",
    "dew_maximum_composition_uncertainty_normalized_residual",
    "dew_pressure_solver_iterations",
    "dew_inner_iteration_count",
    "dew_selected_parent_root",
    "dew_selected_incipient_root",
    "dew_phase_root_ordering_consistent",
    "dew_maximum_fugacity_equilibrium_residual",
    "dew_diagnostic_codes",
    "dew_branch_scan_pressure_bounds_pa",
    "dew_branch_scan_pressure_step_pa",
    "dew_diagnostic_root_count",
    "dew_diagnostic_root_pressures_pa",
    "dew_diagnostic_root_brackets_pa",
    "dew_lowest_root_pressure_pa",
    "dew_highest_root_pressure_pa",
    "dew_multiple_roots_detected",
    "dew_production_selected_root_class",
    "dew_nearest_experimental_root_pressure_pa",
    "dew_nearest_experimental_root_class",
    "dew_nearest_experimental_root_relative_error",
    "dew_failure_classification",
    "experimental_state_log_fugacity_ratio_residuals",
    "experimental_state_maximum_absolute_fugacity_residual",
    "experimental_state_liquid_root",
    "experimental_state_vapor_root",
)


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, tuple):
        return json.dumps(value, separators=(",", ":"))
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def validation_results_to_csv(
    results: Iterable[ExperimentalVLEValidationResult],
) -> str:
    """Serialize complete point accounting with deterministic float precision."""

    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=RESULT_FIELDS, lineterminator="\n")
    writer.writeheader()
    for result in results:
        point, bubble, dew, branch, state = (
            result.point,
            result.bubble,
            result.dew,
            result.dew_branch_diagnostic,
            result.experimental_state,
        )
        root_pressures = tuple(root.pressure_pa for root in branch.roots)
        root_brackets = tuple(root.bracket_pressures_pa for root in branch.roots)
        writer.writerow(
            {
                key: _cell(value)
                for key, value in {
                    "source_point_id": point.source_point_id,
                    "system_id": point.system_id,
                    "temperature_k": point.temperature_k,
                    "experimental_pressure_pa": point.pressure_pa,
                    "liquid_mole_fractions": point.liquid_mole_fractions,
                    "vapor_mole_fractions": point.vapor_mole_fractions,
                    "pressure_expanded_uncertainty_pa": (
                        point.pressure_expanded_uncertainty_pa
                    ),
                    "vapor_expanded_uncertainties": point.vapor_expanded_uncertainties,
                    "bubble_status": bubble.status,
                    "bubble_failure_reason": bubble.failure_reason,
                    "bubble_predicted_pressure_pa": bubble.predicted_pressure_pa,
                    "bubble_pressure_error_pa": bubble.pressure_error_pa,
                    "bubble_pressure_relative_error": bubble.pressure_relative_error,
                    "bubble_pressure_percent_error": bubble.pressure_percent_error,
                    "bubble_pressure_uncertainty_normalized_residual": (
                        bubble.pressure_uncertainty_normalized_residual
                    ),
                    "bubble_predicted_vapor_composition": bubble.predicted_composition,
                    "bubble_vapor_composition_errors": bubble.composition_errors,
                    "bubble_maximum_absolute_composition_error": (
                        bubble.maximum_absolute_composition_error
                    ),
                    "bubble_maximum_composition_uncertainty_normalized_residual": (
                        bubble.maximum_composition_uncertainty_normalized_residual
                    ),
                    "bubble_pressure_solver_iterations": (
                        bubble.pressure_solver_iterations
                    ),
                    "bubble_inner_iteration_count": bubble.inner_iteration_count,
                    "bubble_selected_parent_root": bubble.selected_parent_root,
                    "bubble_selected_incipient_root": bubble.selected_incipient_root,
                    "bubble_phase_root_ordering_consistent": (
                        bubble.phase_root_ordering_consistent
                    ),
                    "bubble_maximum_fugacity_equilibrium_residual": (
                        bubble.maximum_fugacity_equilibrium_residual
                    ),
                    "bubble_diagnostic_codes": bubble.diagnostic_codes,
                    "dew_status": dew.status,
                    "dew_failure_reason": dew.failure_reason,
                    "dew_predicted_pressure_pa": dew.predicted_pressure_pa,
                    "dew_pressure_error_pa": dew.pressure_error_pa,
                    "dew_pressure_relative_error": dew.pressure_relative_error,
                    "dew_pressure_percent_error": dew.pressure_percent_error,
                    "dew_pressure_uncertainty_normalized_residual": (
                        dew.pressure_uncertainty_normalized_residual
                    ),
                    "dew_predicted_liquid_composition": dew.predicted_composition,
                    "dew_liquid_composition_errors": dew.composition_errors,
                    "dew_maximum_absolute_composition_error": (
                        dew.maximum_absolute_composition_error
                    ),
                    "dew_maximum_composition_uncertainty_normalized_residual": (
                        dew.maximum_composition_uncertainty_normalized_residual
                    ),
                    "dew_pressure_solver_iterations": dew.pressure_solver_iterations,
                    "dew_inner_iteration_count": dew.inner_iteration_count,
                    "dew_selected_parent_root": dew.selected_parent_root,
                    "dew_selected_incipient_root": dew.selected_incipient_root,
                    "dew_phase_root_ordering_consistent": (
                        dew.phase_root_ordering_consistent
                    ),
                    "dew_maximum_fugacity_equilibrium_residual": (
                        dew.maximum_fugacity_equilibrium_residual
                    ),
                    "dew_diagnostic_codes": dew.diagnostic_codes,
                    "dew_branch_scan_pressure_bounds_pa": (
                        branch.scan_pressure_bounds_pa
                    ),
                    "dew_branch_scan_pressure_step_pa": branch.scan_pressure_step_pa,
                    "dew_diagnostic_root_count": len(branch.roots),
                    "dew_diagnostic_root_pressures_pa": root_pressures,
                    "dew_diagnostic_root_brackets_pa": root_brackets,
                    "dew_lowest_root_pressure_pa": (
                        root_pressures[0] if root_pressures else None
                    ),
                    "dew_highest_root_pressure_pa": (
                        root_pressures[-1] if root_pressures else None
                    ),
                    "dew_multiple_roots_detected": (branch.multiple_dew_roots_detected),
                    "dew_production_selected_root_class": (
                        branch.production_selected_root_class
                    ),
                    "dew_nearest_experimental_root_pressure_pa": (
                        branch.nearest_pr_root_to_experiment_pressure_pa
                    ),
                    "dew_nearest_experimental_root_class": (
                        branch.nearest_pr_root_class
                    ),
                    "dew_nearest_experimental_root_relative_error": (
                        branch.nearest_pr_root_to_experiment_relative_error
                    ),
                    "dew_failure_classification": branch.failure_classification,
                    "experimental_state_log_fugacity_ratio_residuals": (
                        state.component_log_fugacity_ratio_residuals
                    ),
                    "experimental_state_maximum_absolute_fugacity_residual": (
                        state.maximum_absolute_residual
                    ),
                    "experimental_state_liquid_root": state.liquid_root,
                    "experimental_state_vapor_root": state.vapor_root,
                }.items()
            }
        )
    return stream.getvalue()
