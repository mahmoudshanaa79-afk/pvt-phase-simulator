"""Generation, serialization, loading, and comparison primitives."""

from __future__ import annotations

import csv
import json
import platform
import subprocess
from collections import Counter
from collections.abc import Iterable
from enum import Enum
from io import StringIO
from math import isfinite, log
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pydantic
import pytest
import scipy

from pvt_phase_simulator.eos.flash import calculate_two_phase_flash
from pvt_phase_simulator.eos.peng_robinson import (
    calculate_compressibility_roots,
    calculate_peng_robinson_parameters,
    calculate_stable_compressibility_result,
    classify_mechanical_stability,
)
from pvt_phase_simulator.eos.phase_envelope import (
    EnvelopeContinuationSettings,
    trace_bubble_branch,
    trace_dew_branch,
)
from pvt_phase_simulator.eos.phase_stability import analyze_mixture_phase_stability
from pvt_phase_simulator.eos.saturation_pressure import (
    SaturationKind,
    calculate_saturation_pressure,
)
from pvt_phase_simulator.fluid_models import FluidMixture, MixtureComponent
from tests.golden_master.cases import GoldenCase

FIELDS = (
    "case_id",
    "source_commit",
    "calculation_type",
    "component_names",
    "component_order",
    "feed_composition",
    "kij_values",
    "kij_provenance",
    "temperature_k",
    "pressure_pa",
    "status",
    "convergence_status",
    "failure_reason",
    "termination_reason",
    "message",
    "beta",
    "liquid_composition",
    "vapor_composition",
    "incipient_composition",
    "saturation_pressure_pa",
    "dimensionless_a",
    "dimensionless_b",
    "k_values",
    "log_k_values",
    "log_fugacity_coefficients",
    "compressibility_roots",
    "selected_parent_root",
    "selected_incipient_root",
    "liquid_root",
    "vapor_root",
    "mechanical_classifications",
    "tpd_minimum",
    "objective_residual",
    "fugacity_residual",
    "material_balance_residual",
    "composition_sum_residual",
    "inner_iterations",
    "outer_iterations",
    "fallback_used",
    "correction_source",
    "diagnostic_codes",
    "accepted_point_count",
    "rejected_attempt_count",
    "branch_points",
    "rejected_attempts",
    "trial_statuses",
    "python_version",
    "numpy_version",
    "scipy_version",
    "pandas_version",
    "pydantic_version",
    "pytest_version",
    "platform",
)

EXACT_FIELDS = {
    "calculation_type",
    "component_names",
    "component_order",
    "feed_composition",
    "kij_values",
    "kij_provenance",
    "status",
    "convergence_status",
    "failure_reason",
    "termination_reason",
    "message",
    "diagnostic_codes",
    "trial_statuses",
}
PATH_FIELDS = {
    "inner_iterations",
    "outer_iterations",
    "fallback_used",
    "correction_source",
    "rejected_attempt_count",
    "rejected_attempts",
}
METADATA_FIELDS = {
    "source_commit",
    "python_version",
    "numpy_version",
    "scipy_version",
    "pandas_version",
    "pydantic_version",
    "pytest_version",
    "platform",
}
COMPOSITION_FIELDS = {
    "feed_composition",
    "liquid_composition",
    "vapor_composition",
    "incipient_composition",
}
LOG_K_FIELDS = {"log_k_values"}
ROOT_FIELDS = {
    "compressibility_roots",
    "selected_parent_root",
    "selected_incipient_root",
    "liquid_root",
    "vapor_root",
}
PRESSURE_FIELDS = {"pressure_pa", "saturation_pressure_pa"}
TOLERANCES = {
    "pressure_rel": 1e-11,
    "composition_abs": 1e-10,
    "log_k_abs": 1e-9,
    "root_abs": 1e-11,
    "beta_abs": 1e-9,
    "other_rel": 1e-11,
    "other_abs": 1e-12,
}


def _value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, float):
        return value
    if isinstance(value, tuple):
        return [_value(item) for item in value]
    if isinstance(value, list):
        return [_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    return value


def serialize_value(value: Any) -> str:
    """Serialize scalars/vectors deterministically with float round-trip precision."""

    if value is None:
        return ""
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (tuple, list, dict)):
        return json.dumps(
            _value(value), ensure_ascii=True, separators=(",", ":"), allow_nan=False
        )
    return str(_value(value))


def source_commit(repository: Path) -> str:
    """Read the current commit automatically, with a direct .git fallback."""

    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        git_dir = repository / ".git"
        head = (git_dir / "HEAD").read_text(encoding="ascii").strip()
        if not head.startswith("ref: "):
            return head
        reference = head[5:]
        loose = git_dir / Path(reference)
        if loose.exists():
            return loose.read_text(encoding="ascii").strip()
        for line in (git_dir / "packed-refs").read_text(encoding="ascii").splitlines():
            if line.endswith(f" {reference}"):
                return line.split(" ", 1)[0]
        raise RuntimeError(f"cannot resolve Git reference {reference}") from None


def environment_metadata() -> dict[str, str]:
    return {
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "scipy_version": scipy.__version__,
        "pandas_version": pd.__version__,
        "pydantic_version": pydantic.__version__,
        "pytest_version": pytest.__version__,
        "platform": platform.platform(),
    }


def _base(case: GoldenCase, commit: str, metadata: dict[str, str]) -> dict[str, Any]:
    names = tuple(component.name for component in case.components)
    pairs = tuple(
        (names[i], names[j], 0.0)
        for i in range(len(names))
        for j in range(i + 1, len(names))
    )
    return {
        **{field: None for field in FIELDS},
        "case_id": case.case_id,
        "source_commit": commit,
        "calculation_type": case.calculation_type,
        "component_names": names,
        "component_order": names,
        "feed_composition": case.composition,
        "kij_values": pairs,
        "kij_provenance": "default_zero",
        "temperature_k": case.temperature_k,
        "pressure_pa": case.pressure_pa,
        **metadata,
    }


def _mixture(case: GoldenCase) -> FluidMixture:
    return FluidMixture(
        tuple(
            MixtureComponent(component, fraction)
            for component, fraction in zip(
                case.components, case.composition, strict=True
            )
        )
    )


def _codes(*groups: Iterable[Any]) -> tuple[str, ...]:
    return tuple(sorted({item.code for group in groups for item in group}))


def evaluate_case(
    case: GoldenCase, commit: str, metadata: dict[str, str]
) -> dict[str, Any]:
    row = _base(case, commit, metadata)
    if case.calculation_type == "pure_pr":
        assert case.pressure_pa is not None
        component = case.components[0]
        parameters = calculate_peng_robinson_parameters(
            case.temperature_k,
            case.pressure_pa,
            component.critical_temperature_k,
            component.critical_pressure_pa,
            component.acentric_factor,
        )
        roots = calculate_compressibility_roots(parameters.A, parameters.B)
        mechanics = tuple(
            classify_mechanical_stability(root, parameters.A, parameters.B)
            for root in roots
        )
        stable = calculate_stable_compressibility_result(
            parameters.A, parameters.B, case.pressure_pa
        )
        row.update(
            status="evaluated",
            compressibility_roots=roots,
            selected_parent_root=stable.stable.compressibility_factor,
            mechanical_classifications=tuple(item.classification for item in mechanics),
            dimensionless_a=parameters.A,
            dimensionless_b=parameters.B,
            log_fugacity_coefficients=tuple(
                item.log_fugacity_coefficient for item in stable.candidates
            ),
        )
        return row

    mixture = _mixture(case)
    if case.calculation_type == "stability":
        assert case.pressure_pa is not None
        result = analyze_mixture_phase_stability(
            mixture, case.temperature_k, case.pressure_pa
        )
        trials = (result.vapor_like_trial, result.liquid_like_trial)
        tpds = [
            trial.tangent_plane_distance
            for trial in trials
            if trial.tangent_plane_distance is not None
        ]
        row.update(
            status=result.status,
            selected_parent_root=result.feed_reference.selected_compressibility_factor,
            tpd_minimum=min(tpds) if tpds else None,
            inner_iterations=sum(trial.iteration_count for trial in trials),
            fallback_used=result.vapor_like_character.fallback_triggered
            or result.liquid_like_character.fallback_triggered,
            trial_statuses=tuple(
                "converged" if trial.converged else "failed" for trial in trials
            ),
            diagnostic_codes=_codes(
                result.feed_reference.diagnostics,
                result.vapor_like_character.diagnostics,
                result.liquid_like_character.diagnostics,
            ),
        )
        return row

    if case.calculation_type == "flash":
        assert case.pressure_pa is not None
        result = calculate_two_phase_flash(
            mixture, case.temperature_k, case.pressure_pa
        )
        last = result.iteration_history[-1] if result.iteration_history else None
        row.update(
            status=result.phase_state,
            convergence_status=result.convergence_status,
            failure_reason=result.failure_reason,
            beta=result.vapor_fraction,
            liquid_composition=result.liquid_phase.composition
            if result.liquid_phase
            else None,
            vapor_composition=result.vapor_phase.composition
            if result.vapor_phase
            else None,
            k_values=result.final_k_values or result.initial_k_values,
            log_k_values=tuple(
                log(value)
                for value in (result.final_k_values or result.initial_k_values)
            ),
            liquid_root=result.liquid_phase.selected_compressibility_factor
            if result.liquid_phase
            else None,
            vapor_root=result.vapor_phase.selected_compressibility_factor
            if result.vapor_phase
            else None,
            selected_parent_root=result.single_phase_root,
            fugacity_residual=max(
                (
                    abs(value)
                    for value in result.equilibrium_residuals
                    if value is not None
                ),
                default=None,
            ),
            material_balance_residual=max(
                (abs(value) for value in result.material_balance_residuals),
                default=None,
            ),
            composition_sum_residual=max(
                last.phase_compositions.liquid_sum_residual,
                last.phase_compositions.vapor_sum_residual,
            )
            if last
            else None,
            inner_iterations=len(result.iteration_history),
            fallback_used=result.phase_stability.vapor_like_character.fallback_triggered
            or result.phase_stability.liquid_like_character.fallback_triggered,
            diagnostic_codes=_codes(result.diagnostics),
        )
        return row

    if case.calculation_type in {"bubble", "dew"}:
        kind = (
            SaturationKind.BUBBLE_POINT
            if case.calculation_type == "bubble"
            else SaturationKind.DEW_POINT
        )
        result = calculate_saturation_pressure(mixture, case.temperature_k, kind)
        row.update(
            status=result.status,
            convergence_status=result.convergence_status,
            failure_reason=result.failure_reason,
            saturation_pressure_pa=result.pressure_pa,
            incipient_composition=result.incipient_composition or None,
            k_values=result.k_values or None,
            log_k_values=tuple(log(value) for value in result.k_values)
            if result.k_values
            else None,
            selected_parent_root=result.parent_phase.selected_compressibility_factor
            if result.parent_phase
            else None,
            selected_incipient_root=result.incipient_phase.selected_compressibility_factor
            if result.incipient_phase
            else None,
            objective_residual=result.pressure_residual,
            fugacity_residual=result.maximum_fugacity_equilibrium_residual,
            composition_sum_residual=result.composition_sum_residual,
            inner_iterations=sum(
                len(item.history) for item in result.evaluation_history
            ),
            outer_iterations=result.pressure_solver_iterations,
            diagnostic_codes=_codes(result.diagnostics),
        )
        return row

    assert (
        case.target_temperature_k is not None
        and case.temperature_step_k is not None
        and case.envelope_kind is not None
    )
    settings_kwargs: dict[str, Any] = dict(
        target_temperature_k=case.target_temperature_k,
        initial_temperature_step_k=case.temperature_step_k,
        maximum_points=case.maximum_points,
    )
    if case.envelope_variant == "near_critical":
        settings_kwargs.update(
            near_critical_root_stop=1.0, near_critical_root_warning=1.0
        )
    elif case.envelope_variant == "pressure_bounds":
        settings_kwargs.update(
            minimum_pressure_pa=1_000.0, maximum_pressure_pa=2_700_000.0
        )
    elif case.envelope_variant == "branch_lost":
        settings_kwargs.update(
            minimum_temperature_step_k=2.5,
            maximum_predictor_log_pressure_error=1e-6,
        )
    elif case.envelope_variant == "minimum_step":
        settings_kwargs.update(
            allow_global_fallback=False,
            local_log_pressure_half_span=1e-9,
            maximum_local_expansions=0,
        )
    elif case.envelope_variant == "corrector_failed":
        settings_kwargs.update(
            allow_global_fallback=False,
            maximum_step_retries=2,
            minimum_temperature_step_k=0.001,
            maximum_local_expansions=0,
            local_log_pressure_half_span=0.0005,
        )
    settings = EnvelopeContinuationSettings(**settings_kwargs)
    trace = trace_bubble_branch if case.envelope_kind == "bubble" else trace_dew_branch
    result = trace(mixture, settings, case.temperature_k)
    point = result.points[-1] if result.points else None
    branch_points = tuple(
        {
            "status": item.status.value,
            "temperature_k": item.temperature_k,
            "pressure_pa": item.pressure_pa,
            "incipient_composition": item.saturation_result.incipient_composition,
            "k_values": item.saturation_result.k_values,
            "log_k_values": item.log_k_values,
            "selected_parent_root": (
                item.saturation_result.parent_phase.selected_compressibility_factor
                if item.saturation_result.parent_phase
                else None
            ),
            "selected_incipient_root": (
                item.saturation_result.incipient_phase.selected_compressibility_factor
                if item.saturation_result.incipient_phase
                else None
            ),
            "objective_residual": item.saturation_result.pressure_residual,
            "fugacity_residual": (
                item.saturation_result.maximum_fugacity_equilibrium_residual
            ),
            "composition_sum_residual": (
                item.saturation_result.composition_sum_residual
            ),
            "outer_iterations": item.saturation_result.pressure_solver_iterations,
            "root_separation": item.root_separation,
            "correction_source": item.correction_source.value,
            "accepted_temperature_step_k": item.accepted_temperature_step_k,
            "diagnostic_codes": tuple(
                sorted(
                    {
                        diagnostic.code
                        for diagnostic in (
                            *item.diagnostics,
                            *item.saturation_result.diagnostics,
                        )
                    }
                )
            ),
        }
        for item in result.points
    )
    rejected_attempts = tuple(
        {
            "source": attempt.source.value,
            "status": attempt.status.value,
            "temperature_k": attempt.temperature_k,
            "requested_temperature_step_k": attempt.requested_temperature_step_k,
            "pressure_bounds_pa": attempt.pressure_bounds_pa,
            "log_pressure_half_span": attempt.log_pressure_half_span,
            "accepted": attempt.accepted,
            "failure_reason": attempt.failure_reason,
            "diagnostic_codes": tuple(
                sorted(diagnostic.code for diagnostic in attempt.diagnostics)
            ),
        }
        for attempt in result.rejected_attempts
    )
    row.update(
        status=point.status if point else "no_accepted_point",
        convergence_status=point.saturation_result.convergence_status
        if point
        else None,
        failure_reason=point.saturation_result.failure_reason if point else None,
        termination_reason=result.termination_reason,
        message=result.termination_message,
        saturation_pressure_pa=point.pressure_pa if point else None,
        incipient_composition=point.saturation_result.incipient_composition
        if point
        else None,
        k_values=point.saturation_result.k_values if point else None,
        log_k_values=point.log_k_values if point else None,
        selected_parent_root=point.saturation_result.parent_phase.selected_compressibility_factor
        if point and point.saturation_result.parent_phase
        else None,
        selected_incipient_root=point.saturation_result.incipient_phase.selected_compressibility_factor
        if point and point.saturation_result.incipient_phase
        else None,
        objective_residual=point.saturation_result.pressure_residual if point else None,
        fugacity_residual=point.saturation_result.maximum_fugacity_equilibrium_residual
        if point
        else None,
        composition_sum_residual=point.saturation_result.composition_sum_residual
        if point
        else None,
        inner_iterations=sum(
            len(item.saturation_result.evaluation_history) for item in result.points
        ),
        outer_iterations=sum(
            item.saturation_result.pressure_solver_iterations for item in result.points
        ),
        fallback_used=any(
            item.correction_source.value == "global_fallback" for item in result.points
        ),
        correction_source=point.correction_source if point else None,
        diagnostic_codes=_codes(
            result.diagnostics,
            *(item.diagnostics for item in result.points),
            *(item.saturation_result.diagnostics for item in result.points),
            *(item.diagnostics for item in result.rejected_attempts),
        ),
        accepted_point_count=len(result.points),
        rejected_attempt_count=len(result.rejected_attempts),
        branch_points=branch_points,
        rejected_attempts=rejected_attempts,
    )
    return row


def generate_rows(
    cases: Iterable[GoldenCase], repository: Path
) -> list[dict[str, Any]]:
    commit = source_commit(repository)
    metadata = environment_metadata()
    return [
        evaluate_case(case, commit, metadata)
        for case in sorted(cases, key=lambda item: item.case_id)
    ]


def rows_to_csv(rows: Iterable[dict[str, Any]]) -> str:
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in sorted(rows, key=lambda item: str(item["case_id"])):
        writer.writerow({field: serialize_value(row.get(field)) for field in FIELDS})
    return output.getvalue()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError(
                "baseline schema does not match the required ordered fields"
            )
        rows = list(reader)
    identifiers = [row["case_id"] for row in rows]
    if not identifiers or any(not item for item in identifiers):
        raise ValueError("baseline must contain non-empty case IDs")
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("baseline contains duplicate case IDs")
    if identifiers != sorted(identifiers):
        raise ValueError("baseline rows are not sorted by case ID")
    for row in rows:
        for field in FIELDS:
            try:
                _parsed(row[field])
            except (ValueError, json.JSONDecodeError) as error:
                raise ValueError(
                    f"malformed value for {row['case_id']}.{field}"
                ) from error
    return rows


def _parsed(value: str) -> Any:
    if not value:
        return None
    if value[0] in "[{":
        return json.loads(value)
    try:
        number = float(value)
        if not isfinite(number):
            raise ValueError("non-finite numeric value")
        return number
    except ValueError:
        return value


def _close(expected: Any, actual: Any, field: str) -> bool:
    if expected is None or actual is None:
        return expected is actual
    if (
        field == "diagnostic_codes"
        and isinstance(expected, list)
        and isinstance(actual, list)
    ):
        return set(expected) == set(actual)
    if isinstance(expected, list) and isinstance(actual, list):
        return len(expected) == len(actual) and all(
            _close(a, b, field) for a, b in zip(expected, actual, strict=True)
        )
    if isinstance(expected, dict) and isinstance(actual, dict):
        return expected.keys() == actual.keys() and all(
            _close(expected[key], actual[key], field) for key in expected
        )
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if field in PRESSURE_FIELDS:
            return bool(
                np.isclose(expected, actual, rtol=TOLERANCES["pressure_rel"], atol=0.0)
            )
        absolute = (
            TOLERANCES["composition_abs"]
            if field in COMPOSITION_FIELDS
            else TOLERANCES["log_k_abs"]
            if field in LOG_K_FIELDS
            else TOLERANCES["root_abs"]
            if field in ROOT_FIELDS
            else TOLERANCES["beta_abs"]
            if field == "beta"
            else TOLERANCES["other_abs"]
        )
        relative = (
            0.0
            if field in COMPOSITION_FIELDS | LOG_K_FIELDS | ROOT_FIELDS | {"beta"}
            else TOLERANCES["other_rel"]
        )
        return bool(np.isclose(expected, actual, rtol=relative, atol=absolute))
    return expected == actual


def compare_rows(
    expected_rows: Iterable[dict[str, str]], actual_rows: Iterable[dict[str, str]]
) -> dict[str, list[str]]:
    expected = {row["case_id"]: row for row in expected_rows}
    actual = {row["case_id"]: row for row in actual_rows}
    result = {
        "PHYSICAL_RESULT_DRIFT": [],
        "NUMERICAL_PATH_CHANGE": [],
        "PLATFORM_OR_FORMATTING_NOISE": [],
        "MISSING_CASE": [],
        "EXTRA_CASE": [],
    }
    result["MISSING_CASE"] = sorted(set(expected) - set(actual))
    result["EXTRA_CASE"] = sorted(set(actual) - set(expected))
    for case_id in sorted(set(expected) & set(actual)):
        for field in FIELDS:
            if field == "case_id":
                continue
            left, right = (
                _parsed(expected[case_id][field]),
                _parsed(actual[case_id][field]),
            )
            if _close(left, right, field):
                if left != right and field != "diagnostic_codes":
                    before = expected[case_id][field]
                    after = actual[case_id][field]
                    result["PLATFORM_OR_FORMATTING_NOISE"].append(
                        f"{case_id}: {field}: {before!r} -> {after!r}"
                    )
                continue
            label = (
                "NUMERICAL_PATH_CHANGE"
                if field in PATH_FIELDS
                else "PLATFORM_OR_FORMATTING_NOISE"
                if field in METADATA_FIELDS
                else "PHYSICAL_RESULT_DRIFT"
            )
            before = expected[case_id][field]
            after = actual[case_id][field]
            result[label].append(f"{case_id}: {field}: {before!r} -> {after!r}")
    return result


def counts(rows: Iterable[dict[str, Any]]) -> dict[str, Counter[str]]:
    materialized = list(rows)
    return {
        field: Counter(
            str(_value(row.get(field)))
            for row in materialized
            if row.get(field) is not None
        )
        for field in ("calculation_type", "status", "termination_reason")
    }
