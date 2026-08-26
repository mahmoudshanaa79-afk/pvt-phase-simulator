"""Per-session result identity and submitted-input state."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any, Final, cast

from pvt_phase_simulator_ui.adapters import ScientificInputs

RESULT_KEYS: Final = ("flash", "envelope", "critical", "critical_scan")


def initialize_session(state: MutableMapping[str, Any]) -> None:
    state.setdefault("results", {})
    state.setdefault("result_signatures", {})
    state.setdefault("submitted_inputs", None)


def store_result(
    state: MutableMapping[str, Any],
    name: str,
    value: object,
    inputs: ScientificInputs,
) -> None:
    initialize_session(state)
    state["results"][name] = value
    state["result_signatures"][name] = inputs.signature


def get_result(state: MutableMapping[str, Any], name: str) -> object | None:
    initialize_session(state)
    return cast(dict[str, object], state["results"]).get(name)


def result_is_stale(
    state: MutableMapping[str, Any], name: str, inputs: ScientificInputs | None
) -> bool:
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
