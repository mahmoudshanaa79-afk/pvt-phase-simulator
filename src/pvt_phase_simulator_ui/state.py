"""Per-session result identity and submitted-input state."""

from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import Any, Final, cast

from pvt_phase_simulator_ui.adapters import ScientificInputs

RESULT_KEYS: Final = ("flash", "envelope", "critical", "critical_scan")


@dataclass(frozen=True)
class InputExample:
    """A documented input-only case for the verified component scope."""

    label: str
    methane_pct: float
    ethane_pct: float
    propane_pct: float
    temperature_k: float
    pressure_mpa: float


INPUT_EXAMPLES: Final = (
    InputExample(
        label="Default two-phase-oriented case",
        methane_pct=50.0,
        ethane_pct=0.0,
        propane_pct=50.0,
        temperature_k=300.0,
        pressure_mpa=5.0,
    ),
    InputExample(
        label="Known single-phase case at 300 K and 20 MPa",
        methane_pct=50.0,
        ethane_pct=0.0,
        propane_pct=50.0,
        temperature_k=300.0,
        pressure_mpa=20.0,
    ),
    InputExample(
        label="Audited critical-solver seed",
        methane_pct=50.0,
        ethane_pct=0.0,
        propane_pct=50.0,
        temperature_k=321.5829183194,
        pressure_mpa=8.53444323606381,
    ),
)

_DEFAULT_INPUTS: Final = INPUT_EXAMPLES[0]


def initialize_session(state: MutableMapping[str, Any]) -> None:
    state.setdefault("results", {})
    state.setdefault("result_signatures", {})
    state.setdefault("submitted_inputs", None)
    state.setdefault("current_inputs", None)
    state.setdefault("input_example", None)
    state.setdefault("rendered_input_example", None)
    state.setdefault("methane_pct", _DEFAULT_INPUTS.methane_pct)
    state.setdefault("ethane_pct", _DEFAULT_INPUTS.ethane_pct)
    state.setdefault("propane_pct", _DEFAULT_INPUTS.propane_pct)
    state.setdefault("temperature_k", _DEFAULT_INPUTS.temperature_k)
    state.setdefault("pressure_mpa", _DEFAULT_INPUTS.pressure_mpa)


def apply_selected_input_example(state: MutableMapping[str, Any]) -> None:
    """Copy a selected example into input state without submitting any work."""

    selected = state.get("input_example")
    example = next((item for item in INPUT_EXAMPLES if item.label == selected), None)
    if example is None:
        return
    state["methane_pct"] = example.methane_pct
    state["ethane_pct"] = example.ethane_pct
    state["propane_pct"] = example.propane_pct
    state["temperature_k"] = example.temperature_k
    state["pressure_mpa"] = example.pressure_mpa


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
