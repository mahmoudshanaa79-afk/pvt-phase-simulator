"""Deterministic session-state helpers independent of Streamlit runtime."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any, Final, cast

from app.adapters import ScientificInputs

RESULT_KEYS: Final = ("flash", "envelope", "critical", "critical_scan")


def initialize_session(state: MutableMapping[str, Any]) -> None:
    """Initialize application state without replacing existing results."""

    state.setdefault("results", {})
    state.setdefault("result_signatures", {})


def store_result(
    state: MutableMapping[str, Any],
    name: str,
    value: object,
    inputs: ScientificInputs,
) -> None:
    """Store one deliberate calculation with its scientific input signature."""

    initialize_session(state)
    state["results"][name] = value
    state["result_signatures"][name] = inputs.signature


def get_result(state: MutableMapping[str, Any], name: str) -> object | None:
    """Return a prior result across cosmetic reruns."""

    initialize_session(state)
    results = cast(dict[str, object], state["results"])
    return results.get(name)


def result_is_stale(
    state: MutableMapping[str, Any], name: str, inputs: ScientificInputs | None
) -> bool:
    """Mark a stored result stale after scientific input changes or invalidates."""

    initialize_session(state)
    if name not in state["results"]:
        return False
    if inputs is None:
        return True
    signatures = cast(
        dict[str, tuple[tuple[float, float, float], float, float]],
        state["result_signatures"],
    )
    return signatures.get(name) != inputs.signature
