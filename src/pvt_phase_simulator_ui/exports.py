"""Deterministic, calculation-free exports for the submitted UI case."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator, Mapping, Sequence
from io import StringIO
from typing import Literal

from pvt_phase_simulator.eos.critical_point import MixtureCriticalPointResult
from pvt_phase_simulator.eos.flash import TwoPhaseFlashResult
from pvt_phase_simulator.eos.phase_envelope import (
    PhaseEnvelopeBranchResult,
    PhaseEnvelopePoint,
    PhaseEnvelopeResult,
)
from pvt_phase_simulator_ui.adapters import (
    COMPONENT_NAMES,
    ScientificInputs,
    adapt_critical_result,
    adapt_flash_result,
)

EXPORT_SCHEMA_NAME = "pvt-phase-simulator-current-case"
EXPORT_SCHEMA_VERSION = "1.0.0"


def _enum_value(value: object) -> str:
    return str(value.value if hasattr(value, "value") else value)


def _available(value: object) -> dict[str, object]:
    return {"status": "available", "value": value}


def _missing(
    status: Literal["not_applicable", "unavailable"], reason: str
) -> dict[str, object]:
    return {"status": status, "value": None, "reason": reason}


def _optional_result_value(
    value: object | None, *, not_applicable: bool, reason: str
) -> dict[str, object]:
    if value is not None:
        return _available(value)
    if not_applicable:
        return _missing("not_applicable", reason)
    return _missing(
        "unavailable", "The calculated production result did not supply it."
    )


def _flash_export(result: TwoPhaseFlashResult) -> dict[str, object]:
    view = adapt_flash_result(result)
    phase_state = _enum_value(view.phase_state)
    single_phase = phase_state == "single_phase"
    two_phase = phase_state == "two_phase"
    split_reason = "No two-phase split was required for this single-phase result."
    single_reason = "A selected single-phase Z is not applicable to a two-phase result."
    split_required: object
    if single_phase:
        split_required = False
    elif two_phase:
        split_required = True
    else:
        split_required = _missing(
            "unavailable",
            "The phase classification does not establish whether a split is required.",
        )
    return {
        "calculation_status": "calculated",
        "phase_classification": phase_state,
        "phase_stability_status": _enum_value(result.phase_stability.status),
        "solver_status": _enum_value(view.convergence_status),
        "termination_or_failure_reason": view.failure_reason,
        "two_phase_split_required": split_required,
        "iteration_count": view.iteration_count,
        "vapor_fraction": _optional_result_value(
            view.vapor_fraction, not_applicable=single_phase, reason=split_reason
        ),
        "liquid_fraction": _optional_result_value(
            view.liquid_fraction, not_applicable=single_phase, reason=split_reason
        ),
        "liquid_z": _optional_result_value(
            view.liquid_z, not_applicable=single_phase, reason=split_reason
        ),
        "vapor_z": _optional_result_value(
            view.vapor_z, not_applicable=single_phase, reason=split_reason
        ),
        "selected_single_phase_z": _optional_result_value(
            view.single_phase_z, not_applicable=two_phase, reason=single_reason
        ),
        "liquid_composition": _optional_result_value(
            view.liquid_composition, not_applicable=single_phase, reason=split_reason
        ),
        "vapor_composition": _optional_result_value(
            view.vapor_composition, not_applicable=single_phase, reason=split_reason
        ),
        "k_values": _optional_result_value(
            view.final_k_values, not_applicable=single_phase, reason=split_reason
        ),
        "equilibrium_residuals": _optional_result_value(
            view.equilibrium_residuals or None,
            not_applicable=single_phase,
            reason=split_reason,
        ),
        "material_balance_residuals": _optional_result_value(
            view.material_balance_residuals or None,
            not_applicable=single_phase,
            reason=split_reason,
        ),
    }


def _envelope_point_export(point: PhaseEnvelopePoint) -> dict[str, object]:
    saturation = point.saturation_result
    return {
        "status": _enum_value(point.status),
        "temperature_k": point.temperature_k,
        "pressure_pa": point.pressure_pa,
        "parent_composition": saturation.parent_composition,
        "incipient_composition": saturation.incipient_composition,
        "k_values": saturation.k_values,
        "equilibrium_residuals": saturation.fugacity_equilibrium_residuals,
        "maximum_equilibrium_residual": (
            saturation.maximum_fugacity_equilibrium_residual
        ),
        "composition_sum_residual": saturation.composition_sum_residual,
        "pressure_residual": saturation.pressure_residual,
    }


def _envelope_branch_export(
    branch: PhaseEnvelopeBranchResult,
) -> dict[str, object]:
    return {
        "branch_kind": _enum_value(branch.branch_kind),
        "termination_status": _enum_value(branch.termination_reason),
        "termination_message": branch.termination_message,
        "accepted_point_count": len(branch.points),
        "rejected_attempt_count": len(branch.rejected_attempts),
        "points": [_envelope_point_export(point) for point in branch.points],
    }


def _envelope_export(result: PhaseEnvelopeResult) -> dict[str, object]:
    return {
        "calculation_status": "calculated",
        "bubble_branch": _envelope_branch_export(result.bubble_branch),
        "dew_branch": _envelope_branch_export(result.dew_branch),
    }


def _critical_export(result: MixtureCriticalPointResult) -> dict[str, object]:
    view = adapt_critical_result(result)
    reason = "No certified critical value is available from this production result."
    return {
        "calculation_status": "calculated",
        "solver_status": _enum_value(view.status),
        "certified": view.certified,
        "termination_reason": view.termination_reason,
        "iteration_count": view.iterations,
        "temperature_k": _optional_result_value(
            view.temperature_k, not_applicable=False, reason=reason
        ),
        "pressure_pa": _optional_result_value(
            view.pressure_pa, not_applicable=False, reason=reason
        ),
        "lambda_min": _optional_result_value(
            result.lambda_min, not_applicable=False, reason=reason
        ),
        "cubic_coefficient": _optional_result_value(
            result.cubic_coefficient, not_applicable=False, reason=reason
        ),
        "scaled_residual_norm": _optional_result_value(
            result.scaled_residual_norm, not_applicable=False, reason=reason
        ),
        "critical_direction": _optional_result_value(
            result.critical_direction, not_applicable=False, reason=reason
        ),
    }


def build_export_document(
    inputs: ScientificInputs,
    *,
    flash_result: TwoPhaseFlashResult | None = None,
    envelope_result: PhaseEnvelopeResult | None = None,
    critical_result: MixtureCriticalPointResult | None = None,
) -> dict[str, object]:
    """Build an export solely from submitted inputs and already-held results."""

    components = [
        {
            "name": name,
            "overall_mole_fraction": mole_fraction,
            "composition_mol_percent": mol_percent,
        }
        for name, mole_fraction, mol_percent in zip(
            COMPONENT_NAMES,
            inputs.mole_fractions,
            inputs.composition_mol_percent,
            strict=True,
        )
    ]
    return {
        "schema": {
            "name": EXPORT_SCHEMA_NAME,
            "version": EXPORT_SCHEMA_VERSION,
        },
        "metadata": {
            "eos": "Peng-Robinson",
            "unit_system": "SI",
            "binary_interaction_assumption": "kij = 0",
            "verified_component_scope": list(COMPONENT_NAMES),
            "export_timestamp": {
                "status": "omitted",
                "reason": "Omitted to keep exports reproducible.",
            },
        },
        "case": {
            "temperature_k": inputs.temperature_k,
            "pressure_pa": inputs.pressure_pa,
            "pressure_mpa": inputs.pressure_mpa,
            "model": "Peng-Robinson",
            "binary_interaction_assumption": "kij = 0",
            "components": components,
        },
        "results": {
            "flash": (
                {"calculation_status": "not_calculated"}
                if flash_result is None
                else _flash_export(flash_result)
            ),
            "phase_envelope": (
                {"calculation_status": "not_calculated"}
                if envelope_result is None
                else _envelope_export(envelope_result)
            ),
            "critical_point": (
                {"calculation_status": "not_calculated"}
                if critical_result is None
                else _critical_export(critical_result)
            ),
        },
    }


def export_json_bytes(document: Mapping[str, object]) -> bytes:
    """Serialize deterministic, round-trippable JSON without float rounding."""

    return (
        json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _flatten(value: object, path: str = "") -> Iterator[tuple[str, str, object]]:
    if isinstance(value, Mapping):
        for key in sorted(value, key=str):
            child = f"{path}.{key}" if path else str(key)
            yield from _flatten(value[key], child)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if not value:
            section, _, nested_path = path.partition(".")
            yield section, nested_path, "[]"
            return
        for index, item in enumerate(value):
            yield from _flatten(item, f"{path}[{index}]")
        return
    section, _, nested_path = path.partition(".")
    yield section, nested_path, value


def _csv_value(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return repr(value)
    return str(value)


def export_csv_bytes(document: Mapping[str, object]) -> bytes:
    """Serialize a deterministic path/value CSV with Excel-friendly UTF-8 BOM."""

    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("section", "path", "value"))
    for section, path, value in _flatten(document):
        writer.writerow((section, path, _csv_value(value)))
    return output.getvalue().encode("utf-8-sig")
