"""Strict, versioned declarations for report-only provenance claims."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast


class DeclarationError(ValueError):
    """A report declaration is missing, malformed, or unsupported."""


@dataclass(frozen=True, slots=True)
class RoleDeclaration:
    status: str
    basis: str
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceDeclaration:
    dataset: str
    dataset_role: MappingProxyType[str, RoleDeclaration]
    archive_verification: MappingProxyType[str, object]
    uncertainty_source: MappingProxyType[str, object]
    model_configuration: MappingProxyType[str, object]
    software_verification_pointers: tuple[str, ...]


_ROOT_KEYS = {
    "format",
    "version",
    "dataset",
    "dataset_role",
    "archive_verification",
    "uncertainty_source",
    "model_configuration",
    "software_verification_pointers",
}
_ROLES = {
    "parameter_fitting",
    "solver_development",
    "regression_testing",
    "evaluation",
    "held_out_from_development",
}
_ROLE_STATUSES = {"USED", "NOT_USED", "NOT_ESTABLISHED"}
_BASES = {"DERIVED", "DECLARED_VERIFIED", "DECLARED"}
_FROZEN_ROLES = {
    "parameter_fitting": ("NOT_USED", "DECLARED_VERIFIED"),
    "solver_development": ("NOT_ESTABLISHED", "DECLARED"),
    "regression_testing": ("USED", "DECLARED"),
    "evaluation": ("USED", "DECLARED"),
    "held_out_from_development": ("NOT_ESTABLISHED", "DECLARED"),
}
_ARCHIVE_KEYS = {
    "verified_state_case_id",
    "temperature_k",
    "pressure_pa",
    "liquid_methane_fraction",
    "vapor_propane_fraction",
    "pressure_uncertainty_pa",
    "vapor_propane_uncertainty",
    "pressure_dataset_number",
    "vapor_dataset_number",
    "raw_sha256_matches_manifest",
    "extractor_reproduces_normalized_csv",
    "paired_datasets_independently_contain_state",
    "citation_title_range_ends_k",
    "article_table_check",
    "article_level_consistency",
    "evidence",
}
_UNCERTAINTY_KEYS = {
    "evaluator",
    "method",
    "description",
    "confidence_level_percent",
    "coverage_factor",
    "manifest_metadata_gap",
    "evidence",
}
_MODEL_KEYS = {
    "eos",
    "omega_a",
    "omega_b",
    "kappa_expression",
    "mixing_rule",
    "binary_interaction_policy",
    "prediction_artifact_introduced_revision",
    "generating_revision_embedded",
    "components",
    "evidence",
}
_COMPONENT_KEYS = {
    "component_id",
    "critical_temperature_k",
    "critical_pressure_pa",
    "acentric_factor",
    "kappa",
}


def _reject_constant(value: str) -> None:
    raise DeclarationError(f"non-finite JSON constant {value!r} is forbidden")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DeclarationError(f"duplicate declaration key {key!r}")
        result[key] = value
    return result


def _object(value: object, label: str, keys: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        missing = sorted(keys - set(value) if isinstance(value, dict) else keys)
        extra = sorted(set(value) - keys if isinstance(value, dict) else ())
        raise DeclarationError(f"{label} keys differ; missing={missing}, extra={extra}")
    return cast(dict[str, object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DeclarationError(f"{label} must be non-empty text")
    return value


def _texts(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise DeclarationError(f"{label} must be a non-empty array")
    return tuple(_text(item, label) for item in value)


def _validate_evidence_paths(value: object, label: str) -> None:
    for pointer in _texts(value, label):
        if "\\" in pointer or pointer.startswith(("/", "C:", "c:")):
            raise DeclarationError(f"{label} must contain repository-relative pointers")


def load_declaration(
    dataset: str = "module17", path: Path | None = None
) -> EvidenceDeclaration:
    """Load one supported declaration with exact keys and strict JSON."""

    location = path or Path(__file__).with_name("declarations") / f"{dataset}.json"
    try:
        raw_value = json.loads(
            location.read_text(encoding="utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_pairs,
        )
    except (OSError, json.JSONDecodeError) as error:
        raise DeclarationError(
            f"cannot read declaration {location.name}: {error}"
        ) from error
    root = _object(raw_value, "declaration", _ROOT_KEYS)
    if root["format"] != "openphase.validation_evidence_declaration":
        raise DeclarationError("unsupported declaration format")
    if root["version"] != "1.0.0":
        raise DeclarationError("unsupported declaration version")
    if root["dataset"] != dataset:
        raise DeclarationError("declaration dataset does not match request")

    raw_roles = _object(root["dataset_role"], "dataset_role", _ROLES)
    roles: dict[str, RoleDeclaration] = {}
    for name in sorted(_ROLES):
        item = _object(
            raw_roles[name], f"dataset_role.{name}", {"status", "basis", "evidence"}
        )
        status = _text(item["status"], f"dataset_role.{name}.status")
        basis = _text(item["basis"], f"dataset_role.{name}.basis")
        if status not in _ROLE_STATUSES or basis not in _BASES:
            raise DeclarationError(f"unsupported dataset-role declaration for {name}")
        if (status, basis) != _FROZEN_ROLES[name]:
            raise DeclarationError(
                f"frozen dataset-role declaration differs for {name}"
            )
        _validate_evidence_paths(item["evidence"], f"dataset_role.{name}.evidence")
        roles[name] = RoleDeclaration(
            status, basis, _texts(item["evidence"], "evidence")
        )

    archive = _object(
        root["archive_verification"], "archive_verification", _ARCHIVE_KEYS
    )
    uncertainty = _object(
        root["uncertainty_source"], "uncertainty_source", _UNCERTAINTY_KEYS
    )
    model = _object(root["model_configuration"], "model_configuration", _MODEL_KEYS)
    for label, item in (
        ("archive_verification", archive),
        ("uncertainty_source", uncertainty),
        ("model_configuration", model),
    ):
        _validate_evidence_paths(item["evidence"], f"{label}.evidence")
    if (
        archive["article_table_check"] != "not performed (article inaccessible)"
        or archive["article_level_consistency"] != "UNRESOLVED"
    ):
        raise DeclarationError(
            "the 283.38 K article-level finding must remain unresolved"
        )
    if uncertainty["coverage_factor"] is not None:
        raise DeclarationError("Module 17 coverage factor must remain unstated")
    if model["generating_revision_embedded"] is not False:
        raise DeclarationError(
            "stored predictions do not embed their generating revision"
        )
    components = model["components"]
    if not isinstance(components, list) or not components:
        raise DeclarationError("model_configuration.components must be non-empty")
    for index, component in enumerate(components):
        _object(component, f"model_configuration.components[{index}]", _COMPONENT_KEYS)
    pointers = _texts(
        root["software_verification_pointers"], "software_verification_pointers"
    )
    _validate_evidence_paths(list(pointers), "software_verification_pointers")
    return EvidenceDeclaration(
        dataset,
        MappingProxyType(roles),
        MappingProxyType(archive),
        MappingProxyType(uncertainty),
        MappingProxyType(model),
        pointers,
    )
