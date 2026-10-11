"""Deeply immutable, JSON-compatible diagnostic and metadata values."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from math import isfinite

from .exceptions import SerializationError

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | tuple[JsonValue, ...] | FrozenJsonObject


class FrozenJsonObject(Mapping[str, JsonValue]):
    """An immutable JSON object with canonical key ordering."""

    __slots__ = ("_items",)
    _items: tuple[tuple[str, JsonValue], ...]

    def __init__(self, values: Mapping[str, object] | None = None) -> None:
        source = {} if values is None else values
        if not isinstance(source, Mapping):
            raise TypeError("JSON object values must be a mapping")
        items: list[tuple[str, JsonValue]] = []
        for key, value in source.items():
            if not isinstance(key, str):
                raise SerializationError("JSON object keys must be strings")
            items.append((key, freeze_json(value)))
        object.__setattr__(
            self, "_items", tuple(sorted(items, key=lambda item: item[0]))
        )

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise TypeError("FrozenJsonObject is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise TypeError("FrozenJsonObject is immutable")

    def __getitem__(self, key: str) -> JsonValue:
        for candidate, value in self._items:
            if candidate == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (key for key, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        return f"FrozenJsonObject({dict(self._items)!r})"

    def __hash__(self) -> int:
        return hash(self._items)

    def __copy__(self) -> FrozenJsonObject:
        return self

    def __deepcopy__(self, memo: dict[int, object]) -> FrozenJsonObject:
        del memo
        return self


def freeze_json(value: object) -> JsonValue:
    """Validate and recursively freeze one JSON-compatible value."""

    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise SerializationError("JSON numeric values must be finite")
        return value
    if isinstance(value, FrozenJsonObject):
        return value
    if isinstance(value, Mapping):
        return FrozenJsonObject(value)
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item) for item in value)
    raise SerializationError(
        f"unsupported JSON value type {type(value).__name__}; "
        "diagnostics and metadata must be JSON-compatible"
    )


def mutable_json(value: JsonValue) -> JsonScalar | list[object] | dict[str, object]:
    """Convert an immutable JSON value to standard encoder inputs."""

    if isinstance(value, FrozenJsonObject):
        return {key: mutable_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [mutable_json(item) for item in value]
    return value
