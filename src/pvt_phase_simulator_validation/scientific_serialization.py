"""Closed-registry, deterministic schema 1.2 serialization for scientific types."""

from __future__ import annotations

import json
import types
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from math import isfinite
from typing import Any, TypeAliasType, get_args, get_origin, get_type_hints

from . import (
    aggregates,
    aggregation,
    comparisons,
    enums,
    metrics,
    models,
    module17_legacy,
    provenance,
    sensitivity,
)
from .exceptions import SerializationError, UnsupportedValueError
from .json_values import FrozenJsonObject, mutable_json
from .models import SCHEMA_VERSION, ValidationRecord, require_supported_schema_version
from .serialization import _record_from, _record_payload


def _registry() -> dict[str, type[Any]]:
    registered: dict[str, type[Any]] = {}
    for module in (
        aggregates,
        aggregation,
        comparisons,
        enums,
        metrics,
        models,
        module17_legacy,
        provenance,
        sensitivity,
    ):
        for name, value in vars(module).items():
            if (
                isinstance(value, type)
                and value.__module__ == module.__name__
                and (is_dataclass(value) or issubclass(value, Enum))
            ):
                registered[name] = value
    return registered


def _encode(value: object) -> object:
    if isinstance(value, Enum):
        return {"enum": type(value).__name__, "value": value.value}
    if isinstance(value, ValidationRecord):
        return {"type": "ValidationRecord", "fields": _record_payload(value)}
    if is_dataclass(value) and not isinstance(value, type):
        if type(value).__name__ not in _registry():
            raise SerializationError("unregistered scientific type")
        return {
            "type": type(value).__name__,
            "fields": {
                field.name: _encode(getattr(value, field.name))
                for field in fields(value)
                if field.init
            },
        }
    if isinstance(value, FrozenJsonObject):
        return {"json_object": mutable_json(value)}
    if isinstance(value, (datetime, date)):
        return {
            "datetime" if isinstance(value, datetime) else "date": value.isoformat()
        }
    if isinstance(value, tuple):
        return [_encode(v) for v in value]
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise SerializationError(f"unsupported scientific value {type(value).__name__}")


def _matches(value: object, annotation: Any) -> bool:
    if annotation is Any:
        return True
    if isinstance(annotation, TypeAliasType):
        return _matches(value, annotation.__value__)
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is types.UnionType:
        return any(_matches(value, member) for member in args)
    if origin is tuple:
        if not isinstance(value, tuple):
            return False
        if len(args) == 2 and args[1] is Ellipsis:
            return all(_matches(v, args[0]) for v in value)
        return len(value) == len(args) and all(
            _matches(v, a) for v, a in zip(value, args, strict=True)
        )
    if annotation is float:
        return type(value) in (int, float)
    if annotation in (int, bool, str):
        return type(value) is annotation
    if annotation is type(None):
        return value is None
    if isinstance(annotation, type):
        return isinstance(value, annotation)
    return False


def _decode(value: object) -> Any:
    if isinstance(value, float) and not isfinite(value):
        raise SerializationError("scientific numbers must be finite")
    if isinstance(value, list):
        return tuple(_decode(v) for v in value)
    if not isinstance(value, dict):
        return value
    if set(value) == {"json_object"}:
        return FrozenJsonObject(value["json_object"])
    if set(value) == {"date"}:
        return date.fromisoformat(value["date"])
    if set(value) == {"datetime"}:
        return datetime.fromisoformat(value["datetime"])
    registry = _registry()
    if set(value) == {"enum", "value"}:
        enum = registry.get(value["enum"])
        if enum is None or not issubclass(enum, Enum):
            raise UnsupportedValueError("unknown scientific enum")
        try:
            return enum(value["value"])
        except ValueError as error:
            raise UnsupportedValueError("unknown scientific enum value") from error
    if set(value) != {"type", "fields"}:
        raise SerializationError("unknown scientific payload fields")
    cls = registry.get(value["type"])
    if cls is None or not is_dataclass(cls):
        raise UnsupportedValueError("unknown scientific type")
    if cls is ValidationRecord:
        return _record_from(value["fields"])
    payload = value["fields"]
    expected = {field.name for field in fields(cls) if field.init}
    if not isinstance(payload, dict) or set(payload) != expected:
        raise SerializationError("scientific fields do not match schema")
    decoded = {key: _decode(v) for key, v in payload.items()}
    annotations = get_type_hints(cls)
    for key, v in decoded.items():
        if not _matches(v, annotations[key]):
            raise SerializationError(
                f"invalid scientific field type: {cls.__name__}.{key}"
            )
    return cls(**decoded)


def encode_scientific_artifact(value: object) -> bytes:
    """Encode any registered comparison, aggregate, assessment or legacy type."""
    if not is_dataclass(value) and not isinstance(value, Enum):
        raise SerializationError("scientific artifact must be a registered type")
    try:
        return (
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "scientific_artifact": _encode(value),
                },
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise SerializationError(
            "scientific artifact contains a non-JSON value"
        ) from error


def decode_scientific_artifact(encoded: bytes | str) -> Any:
    """Validate version before constructing any scientific objects; no migration."""

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise SerializationError("duplicate scientific JSON key")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise SerializationError(f"non-finite JSON constant {value}")

    try:
        document = json.loads(
            encoded, object_pairs_hook=pairs, parse_constant=reject_constant
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise SerializationError("invalid scientific JSON") from error
    if not isinstance(document, dict) or set(document) != {
        "schema_version",
        "scientific_artifact",
    }:
        raise SerializationError("invalid scientific artifact envelope")
    require_supported_schema_version(document["schema_version"])
    return _decode(document["scientific_artifact"])
