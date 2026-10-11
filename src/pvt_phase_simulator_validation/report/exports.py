"""Deterministic JSON/CSV exports and the four-artifact writer."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path

from pvt_phase_simulator_validation.comparisons import (
    ToleranceAssessment,
    UncertaintyAssessment,
    UndefinedMetric,
    align_values,
)
from pvt_phase_simulator_validation.enums import ValidationQuantity
from pvt_phase_simulator_validation.json_values import mutable_json
from pvt_phase_simulator_validation.models import (
    PredictionValue,
    ReferenceValue,
    Value,
)
from pvt_phase_simulator_validation.scientific_serialization import (
    encode_scientific_artifact,
)

from .evidence import AggregateEvidence, ValidationEvidence


@dataclass(frozen=True, slots=True)
class ArtifactFile:
    path: Path
    sha256: str


@dataclass(frozen=True, slots=True)
class ReportArtifacts:
    html: ArtifactFile
    json: ArtifactFile
    comparisons_csv: ArtifactFile
    case_ledger_csv: ArtifactFile


def _strict_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r}")


def _scientific(value: object) -> object:
    return json.loads(
        encode_scientific_artifact(value),
        parse_constant=_strict_constant,
    )


def _aggregate_id(item: AggregateEvidence) -> str:
    aggregate = item.aggregate
    key = aggregate.grouping_key
    phase = (
        "none"
        if key.comparison_key.phase is None
        else key.comparison_key.phase.value.lower()
    )
    system = "pooled" if key.system_id is None else key.system_id
    reduction = (
        "none" if aggregate.reduction is None else aggregate.reduction.value.lower()
    )
    return "--".join(
        (
            key.identity.dataset_id,
            system,
            key.capability.value.lower(),
            key.comparison_key.quantity.value.lower(),
            phase,
            aggregate.observation_unit.value.lower(),
            reduction,
        )
    )


def _membership(item: AggregateEvidence) -> dict[str, object]:
    return {
        "case_ids": list(item.membership.case_ids),
        "metrics": [
            {
                "metric": membership.metric.value,
                "contributors": [
                    {
                        "case_id": contributor.case_id,
                        "component_id": contributor.component_id,
                    }
                    for contributor in membership.contributors
                ],
            }
            for membership in item.membership.metric_memberships
        ],
    }


def _role(evidence: ValidationEvidence) -> dict[str, object]:
    return {
        name: {
            "status": role.status,
            "basis": role.basis,
            "evidence": list(role.evidence),
        }
        for name, role in sorted(evidence.declaration.dataset_role.items())
    }


def _scope(evidence: ValidationEvidence) -> dict[str, object]:
    result: list[dict[str, object]] = []
    groups = sorted(
        {(case.system_id, case.capability) for case in evidence.production.cases},
        key=lambda item: (item[0], item[1].value),
    )
    for system_id, capability in groups:
        cases = tuple(
            case
            for case in evidence.production.cases
            if case.system_id == system_id and case.capability is capability
        )
        temperatures: list[float] = []
        pressures: list[float] = []
        methane_fractions: list[float] = []
        specified_phase: str | None = None
        for case in cases:
            for value in case.specified_conditions:
                if value.quantity is ValidationQuantity.TEMPERATURE and isinstance(
                    value.value, float
                ):
                    temperatures.append(value.value)
                if value.quantity is ValidationQuantity.MOLE_FRACTION and isinstance(
                    value.value, tuple
                ):
                    by_id = dict(
                        zip(value.component_ids or (), value.value, strict=True)
                    )
                    methane_fractions.append(by_id["methane"])
                    specified_phase = None if value.phase is None else value.phase.value
            for value in case.reference_values:
                if value.quantity is ValidationQuantity.PRESSURE and isinstance(
                    value.value, float
                ):
                    pressures.append(value.value)
        result.append(
            {
                "system_id": system_id,
                "capability": capability.value,
                "case_count": len(cases),
                "temperature_k": {
                    "minimum": min(temperatures),
                    "maximum": max(temperatures),
                },
                "reference_pressure_pa": {
                    "minimum": min(pressures),
                    "maximum": max(pressures),
                },
                "specified_methane_fraction": {
                    "phase": specified_phase,
                    "minimum": min(methane_fractions),
                    "maximum": max(methane_fractions),
                },
            }
        )
    return {"groups": result, "source_anomaly": evidence.sensitivity_subset.reason}


def _model(evidence: ValidationEvidence) -> dict[str, object]:
    model = evidence.model_configuration
    return {
        "eos": model.eos,
        "omega_a": model.omega_a,
        "omega_b": model.omega_b,
        "kappa_expression": model.kappa_expression,
        "mixing_rule": model.mixing_rule,
        "binary_interaction_policy": model.binary_interaction_policy,
        "prediction_artifact": {
            "introduced_revision": model.prediction_artifact_introduced_revision,
            "generating_revision_embedded": model.generating_revision_embedded,
        },
        "components": [
            {
                "component_id": item.component_id,
                "name": item.name,
                "critical_temperature_k": item.critical_temperature_k,
                "critical_pressure_pa": item.critical_pressure_pa,
                "acentric_factor": item.acentric_factor,
                "kappa": item.kappa,
                "provenance": dict(item.provenance),
            }
            for item in model.components
        ],
        "evidence": list(model.evidence),
    }


def _cases(evidence: ValidationEvidence) -> list[dict[str, object]]:
    comparison_by_id = {case.case_id: case for case in evidence.production.comparisons}
    return [
        {
            "dataset_id": case.dataset_id,
            "dataset_version": case.dataset_version,
            "data_class": case.data_class.value,
            "capability": case.capability.value,
            "case_id": case.case_id,
            "system_id": case.system_id,
            "component_ids": list(case.component_ids),
            "source_reference": case.source_reference,
            "specified_conditions": [
                _scientific(item) for item in case.specified_conditions
            ],
            "reference_values": [_scientific(item) for item in case.reference_values],
            "prediction_outcome": case.prediction_outcome.value,
            "prediction_values": [_scientific(item) for item in case.prediction_values],
            "failure_reason": case.failure_reason,
            "validation_status": case.validation_status.value,
            "exclusion_reason": case.exclusion_reason,
            "comparison": _scientific(comparison_by_id[case.case_id]),
        }
        for case in evidence.production.cases
    ]


def _json_payload(evidence: ValidationEvidence) -> dict[str, object]:
    source_manifest = evidence.datasets[0].source_manifest
    all_aggregates = (
        *evidence.production.aggregates,
        *evidence.production.vector_aggregates,
    )
    failures = [
        {
            "case_id": case.case_id,
            "system_id": case.system_id,
            "capability": case.capability.value,
            "solver_outcome": case.solver_outcome.value,
            "failure_reason": case.failure_reason,
        }
        for case in evidence.production.cases
        if case.solver_outcome.value != "CONVERGED"
    ]
    uncertainty = []
    for case in evidence.production.comparisons:
        for comparison in case.quantity_comparisons:
            uncertainty.append(
                {
                    "case_id": case.case_id,
                    "comparison_key": _scientific(comparison.key),
                    "assessment": _scientific(comparison.uncertainty_assessment),
                }
            )
    return {
        "format": {
            "namespace": evidence.format,
            "schema_version": evidence.schema_version,
            "canonicalization": (
                "UTF-8 JSON, sorted keys, compact separators, non-finite numeric "
                "constants forbidden; content hash excludes volatile and "
                "content_sha256"
            ),
        },
        "volatile": {
            "run_id": evidence.volatile.run_id,
            "generated_at_utc": evidence.volatile.generated_at_utc.isoformat().replace(
                "+00:00", "Z"
            ),
        },
        "report_metadata": {
            "title": "OpenPhase Module 17 Validation Evidence Report",
            "dataset": evidence.declaration.dataset,
            "scientific_verdict": None,
        },
        "dataset": {
            "declaration": evidence.declaration.dataset,
            "reference_datasets": [_scientific(item) for item in evidence.datasets],
        },
        "dataset_role": _role(evidence),
        "source_provenance": {
            "manifest": _scientific(source_manifest),
            "archive_verification": dict(evidence.declaration.archive_verification),
            "uncertainty_source": dict(evidence.declaration.uncertainty_source),
        },
        "model_configuration": _model(evidence),
        "scope": _scope(evidence),
        "coverage": {
            "groups": [
                {
                    "aggregate_id": _aggregate_id(item),
                    "grouping_key": _scientific(item.aggregate.grouping_key),
                    "coverage": _scientific(item.aggregate.coverage),
                }
                for item in evidence.production.aggregates
            ],
            "pooled_by_capability": [
                {
                    "grouping_key": _scientific(item.grouping_key),
                    "coverage": _scientific(item.coverage),
                }
                for item in evidence.production.pooled_coverage
            ],
        },
        "aggregates": [
            {
                "aggregate_id": _aggregate_id(item),
                "scientific_object": _scientific(item.aggregate),
                "membership": _membership(item),
            }
            for item in all_aggregates
        ],
        "uncertainty_assessments": uncertainty,
        "cases": _cases(evidence),
        "failures": failures,
        "sensitivity": [_scientific(item) for item in evidence.sensitivity],
        "legacy": {
            "descriptive_statistics": [
                _scientific(item) for item in evidence.legacy.descriptive_statistics
            ],
            "discrepancies": [
                _scientific(item) for item in evidence.legacy.discrepancies
            ],
        },
        "diagnostics": {
            "heading": "RETROSPECTIVE DIAGNOSTICS — NOT PRODUCTION PREDICTIONS",
            "interpretation": {
                key: mutable_json(value)
                for key, value in evidence.diagnostics.interpretation.items()
            },
            "cases": [
                {
                    "case_id": item.case_id,
                    "capability": item.capability.value,
                    "diagnostics": [mutable_json(value) for value in item.diagnostics],
                }
                for item in evidence.diagnostics.cases
            ],
        },
        "reproducibility": {
            "git_commit_sha": evidence.reproducibility.git_commit_sha,
            "tree_state": evidence.reproducibility.tree_state,
            "package_version": evidence.reproducibility.package_version,
            "framework_schema_version": (
                evidence.reproducibility.framework_schema_version
            ),
            "python_version": evidence.reproducibility.python_version,
            "platform": evidence.reproducibility.platform,
            "dataset_pins": [
                _scientific(item) for item in evidence.reproducibility.dataset_pins
            ],
            "reproduction_command": evidence.reproducibility.reproduction_command,
        },
        "content_sha256": None,
    }


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def export_json(evidence: ValidationEvidence) -> str:
    """Return strict canonical JSON with a stable non-volatile content hash."""

    payload = _json_payload(evidence)
    stable = {
        key: value
        for key, value in payload.items()
        if key not in {"volatile", "content_sha256"}
    }
    payload["content_sha256"] = hashlib.sha256(_canonical_bytes(stable)).hexdigest()
    encoded = _canonical_bytes(payload) + b"\n"
    json.loads(encoded, parse_constant=_strict_constant)
    return encoded.decode("utf-8")


def _value_component(
    value: ReferenceValue | PredictionValue | None, component_id: str | None
) -> float | None:
    if value is None:
        return None
    if isinstance(value.value, tuple):
        if component_id is None:
            return None
        by_id = dict(zip(value.component_ids or (), value.value, strict=True))
        return by_id[component_id]
    return value.value


def _error_component(value: Value | None, index: int) -> float | None:
    if isinstance(value, tuple):
        return value[index]
    return value if isinstance(value, float) else None


def _csv_text(value: object) -> object:
    if not isinstance(value, str):
        return value
    return "'" + value if value.startswith(("=", "+", "-", "@", "\t", "\r")) else value


def _write_csv(fieldnames: tuple[str, ...], rows: list[dict[str, object]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _csv_text(row.get(key, "")) for key in fieldnames})
    return stream.getvalue()


_COMPARISON_FIELDS = (
    "dataset_id",
    "dataset_version",
    "data_class",
    "system_id",
    "capability",
    "case_id",
    "source_reference",
    "quantity",
    "phase",
    "component_id",
    "unit",
    "comparison_state",
    "solver_outcome",
    "specified_temperature_k",
    "specified_composition_phase",
    "specified_methane_fraction",
    "reference_value",
    "reference_value_state",
    "predicted_value",
    "predicted_value_state",
    "signed_error",
    "absolute_error",
    "relative_error",
    "relative_error_state",
    "relative_error_reason",
    "uncertainty_kind",
    "uncertainty_derivation",
    "uncertainty_denominator",
    "coverage_factor",
    "coverage_factor_state",
    "coverage_factor_reason",
    "confidence_level_percent",
    "uncertainty_scope",
    "expanded_normalized_residual",
    "expanded_normalized_residual_state",
    "expanded_normalized_residual_reason",
    "standard_normalized_residual",
    "standard_normalized_residual_state",
    "standard_normalized_residual_reason",
    "uncertainty_criterion",
    "uncertainty_agreement",
    "uncertainty_state",
    "uncertainty_reason",
    "tolerance_agreement",
    "tolerance_state",
    "tolerance_reason",
    "tolerance_kind",
    "tolerance_value",
    "tolerance_citation",
)


def export_comparisons_csv(evidence: ValidationEvidence) -> str:
    """Write one row per quantity comparison and component, including all states."""

    case_by_id = {case.case_id: case for case in evidence.production.cases}
    rows: list[dict[str, object]] = []
    for case_comparison in evidence.production.comparisons:
        case = case_by_id[case_comparison.case_id]
        specified_temperature = next(
            (
                item.value
                for item in case.specified_conditions
                if item.quantity is ValidationQuantity.TEMPERATURE
            ),
            None,
        )
        specified_composition = next(
            (
                item
                for item in case.specified_conditions
                if item.quantity is ValidationQuantity.MOLE_FRACTION
            ),
            None,
        )
        specified_methane = _value_component(specified_composition, "methane")
        references = {
            (item.quantity, item.phase): item for item in case.reference_values
        }
        predictions = {
            (item.quantity, item.phase): item for item in case.prediction_values
        }
        for comparison in case_comparison.quantity_comparisons:
            key = (comparison.key.quantity, comparison.key.phase)
            reference, prediction = references.get(key), predictions.get(key)
            aligned_reference: Value | None
            aligned_prediction: Value | None
            if reference is not None and prediction is not None:
                aligned_reference, aligned_prediction = align_values(
                    reference, prediction
                )
            else:
                aligned_reference = None if reference is None else reference.value
                aligned_prediction = None if prediction is None else prediction.value
            component_ids = comparison.component_ids or (None,)
            for index, component_id in enumerate(component_ids):
                errors = comparison.errors
                relative = None if errors is None else errors.relative_error
                if isinstance(relative, UndefinedMetric):
                    relative_state, relative_reason, relative_value = (
                        "UNDEFINED",
                        relative.reason.value,
                        None,
                    )
                elif relative is None:
                    relative_state, relative_reason, relative_value = (
                        "NOT_APPLICABLE",
                        "NOT_COMPARED_OR_DISABLED",
                        None,
                    )
                else:
                    relative_state, relative_reason = "DEFINED", None
                    relative_value = _error_component(relative, index)
                assessment = comparison.uncertainty_assessment
                if isinstance(assessment, UncertaintyAssessment):
                    applied = assessment.applied
                    coverage_factor_state = (
                        "AVAILABLE"
                        if applied.coverage_factor is not None
                        else "NOT_STATED"
                    )
                    coverage_factor_reason = (
                        None
                        if applied.coverage_factor is not None
                        else "NOT_STATED_BY_SOURCE"
                    )
                    expanded_available = (
                        assessment.expanded_normalized_residual is not None
                    )
                    standard_available = (
                        assessment.standard_normalized_residual is not None
                    )
                    uncertainty = {
                        "uncertainty_kind": applied.kind_used.value,
                        "uncertainty_derivation": applied.derivation.value,
                        "uncertainty_denominator": _error_component(
                            applied.denominator, index
                        ),
                        "coverage_factor": applied.coverage_factor,
                        "coverage_factor_state": coverage_factor_state,
                        "coverage_factor_reason": coverage_factor_reason,
                        "confidence_level_percent": applied.confidence_level_percent,
                        "uncertainty_scope": applied.scope.value,
                        "expanded_normalized_residual": _error_component(
                            assessment.expanded_normalized_residual, index
                        ),
                        "expanded_normalized_residual_state": (
                            "AVAILABLE" if expanded_available else "NOT_APPLICABLE"
                        ),
                        "expanded_normalized_residual_reason": (
                            None
                            if expanded_available
                            else f"KIND_USED_{applied.kind_used.value}"
                        ),
                        "standard_normalized_residual": _error_component(
                            assessment.standard_normalized_residual, index
                        ),
                        "standard_normalized_residual_state": (
                            "AVAILABLE" if standard_available else "NOT_APPLICABLE"
                        ),
                        "standard_normalized_residual_reason": (
                            None
                            if standard_available
                            else f"KIND_USED_{applied.kind_used.value}"
                        ),
                        "uncertainty_criterion": assessment.criterion.value,
                        "uncertainty_agreement": assessment.agreement.value,
                        "uncertainty_state": "ASSESSED",
                        "uncertainty_reason": None,
                    }
                else:
                    uncertainty = {
                        "uncertainty_kind": None,
                        "uncertainty_derivation": None,
                        "uncertainty_denominator": None,
                        "coverage_factor": None,
                        "coverage_factor_state": "NOT_APPLICABLE",
                        "coverage_factor_reason": assessment.reason.value,
                        "confidence_level_percent": None,
                        "uncertainty_scope": None,
                        "expanded_normalized_residual": None,
                        "expanded_normalized_residual_state": "NOT_APPLICABLE",
                        "expanded_normalized_residual_reason": assessment.reason.value,
                        "standard_normalized_residual": None,
                        "standard_normalized_residual_state": "NOT_APPLICABLE",
                        "standard_normalized_residual_reason": assessment.reason.value,
                        "uncertainty_criterion": None,
                        "uncertainty_agreement": None,
                        "uncertainty_state": "NOT_ASSESSED",
                        "uncertainty_reason": assessment.reason.value,
                    }
                tolerance = comparison.tolerance_assessment
                if isinstance(tolerance, ToleranceAssessment):
                    tolerance_values = {
                        "tolerance_agreement": tolerance.agreement.value,
                        "tolerance_state": "ASSESSED",
                        "tolerance_reason": None,
                        "tolerance_kind": tolerance.tolerance.tolerance_kind.value,
                        "tolerance_value": tolerance.tolerance.value,
                        "tolerance_citation": tolerance.tolerance.source_citation,
                    }
                else:
                    tolerance_values = {
                        "tolerance_agreement": None,
                        "tolerance_state": "NOT_ASSESSED",
                        "tolerance_reason": tolerance.reason.value,
                        "tolerance_kind": None,
                        "tolerance_value": None,
                        "tolerance_citation": None,
                    }
                rows.append(
                    {
                        "dataset_id": case.dataset_id,
                        "dataset_version": case.dataset_version,
                        "data_class": case.data_class.value,
                        "system_id": case.system_id,
                        "capability": case.capability.value,
                        "case_id": case.case_id,
                        "source_reference": case.source_reference,
                        "quantity": comparison.key.quantity.value,
                        "phase": None
                        if comparison.key.phase is None
                        else comparison.key.phase.value,
                        "component_id": component_id,
                        "unit": comparison.key.quantity.canonical_si_unit,
                        "comparison_state": comparison.comparison_state.value,
                        "solver_outcome": case.solver_outcome.value,
                        "specified_temperature_k": specified_temperature,
                        "specified_composition_phase": None
                        if specified_composition is None
                        or specified_composition.phase is None
                        else specified_composition.phase.value,
                        "specified_methane_fraction": specified_methane,
                        "reference_value": _error_component(aligned_reference, index),
                        "reference_value_state": "AVAILABLE"
                        if reference is not None
                        else "UNAVAILABLE",
                        "predicted_value": _error_component(aligned_prediction, index),
                        "predicted_value_state": "AVAILABLE"
                        if prediction is not None
                        else "UNAVAILABLE",
                        "signed_error": None
                        if errors is None
                        else _error_component(errors.error, index),
                        "absolute_error": None
                        if errors is None
                        else _error_component(errors.absolute_error, index),
                        "relative_error": relative_value,
                        "relative_error_state": relative_state,
                        "relative_error_reason": relative_reason,
                        **uncertainty,
                        **tolerance_values,
                    }
                )
    rows.sort(
        key=lambda row: (
            str(row["case_id"]),
            str(row["quantity"]),
            str(row["phase"]),
            str(row["component_id"]),
        )
    )
    return _write_csv(_COMPARISON_FIELDS, rows)


_LEDGER_FIELDS = (
    "dataset_id",
    "dataset_version",
    "data_class",
    "system_id",
    "capability",
    "case_id",
    "source_reference",
    "component_ids",
    "specified_conditions",
    "solver_outcome",
    "prediction_outcome",
    "failure_reason",
    "excluded",
    "exclusion_reason",
    "reference_available_keys",
    "compared_keys",
    "sensitivity_subset_member",
    "has_retrospective_diagnostics",
)


def export_case_ledger_csv(evidence: ValidationEvidence) -> str:
    """Write one auditable row for every adapter case."""

    comparison_by_id = {case.case_id: case for case in evidence.production.comparisons}
    diagnostic_ids = {case.case_id for case in evidence.diagnostics.cases}
    subset_ids = set(evidence.sensitivity_subset.excluded_case_ids)
    rows: list[dict[str, object]] = []
    for case in evidence.production.cases:
        comparison = comparison_by_id[case.case_id]
        rows.append(
            {
                "dataset_id": case.dataset_id,
                "dataset_version": case.dataset_version,
                "data_class": case.data_class.value,
                "system_id": case.system_id,
                "capability": case.capability.value,
                "case_id": case.case_id,
                "source_reference": case.source_reference,
                "component_ids": json.dumps(case.component_ids, separators=(",", ":")),
                "specified_conditions": json.dumps(
                    [_scientific(item) for item in case.specified_conditions],
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ),
                "solver_outcome": case.solver_outcome.value,
                "prediction_outcome": case.prediction_outcome.value,
                "failure_reason": case.failure_reason,
                "excluded": case.validation_status.value == "EXCLUDED",
                "exclusion_reason": case.exclusion_reason,
                "reference_available_keys": json.dumps(
                    [
                        (
                            f"{item.key.quantity.value}:"
                            f"{'' if item.key.phase is None else item.key.phase.value}"
                        )
                        for item in comparison.quantity_comparisons
                        if item.reference_available
                    ],
                    separators=(",", ":"),
                ),
                "compared_keys": json.dumps(
                    [
                        (
                            f"{item.key.quantity.value}:"
                            f"{'' if item.key.phase is None else item.key.phase.value}"
                        )
                        for item in comparison.quantity_comparisons
                        if item.comparison_state.value == "COMPARED"
                    ],
                    separators=(",", ":"),
                ),
                "sensitivity_subset_member": case.case_id in subset_ids,
                "has_retrospective_diagnostics": case.case_id in diagnostic_ids,
            }
        )
    return _write_csv(_LEDGER_FIELDS, rows)


def _artifact(path: Path, content: str) -> ArtifactFile:
    encoded = content.encode("utf-8")
    path.write_bytes(encoded)
    return ArtifactFile(path, hashlib.sha256(encoded).hexdigest())


def write_validation_report(
    evidence: ValidationEvidence, output_dir: str | Path
) -> ReportArtifacts:
    """Write exactly the four approved files and return their byte hashes."""

    from .html import render_html

    directory = Path(output_dir).resolve()
    if directory.is_relative_to(evidence.repository_root):
        raise ValueError(
            "generated report artifacts must be outside the repository tree"
        )
    directory.mkdir(parents=True, exist_ok=True)
    json_artifact = _artifact(
        directory / "validation_evidence.json", export_json(evidence)
    )
    comparisons = _artifact(
        directory / "comparisons.csv", export_comparisons_csv(evidence)
    )
    ledger = _artifact(directory / "case_ledger.csv", export_case_ledger_csv(evidence))
    html = _artifact(directory / "validation_evidence.html", render_html(evidence))
    return ReportArtifacts(html, json_artifact, comparisons, ledger)
