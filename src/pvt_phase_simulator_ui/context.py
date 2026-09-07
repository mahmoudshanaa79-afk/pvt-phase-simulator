"""Shared Streamlit session access for page scripts."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any, cast

import streamlit as st

from pvt_phase_simulator_ui.adapters import ScientificInputs
from pvt_phase_simulator_ui.units import (
    DEFAULT_UNITS,
    PressureUnit,
    TemperatureUnit,
    UnitPreferences,
)


def session() -> MutableMapping[str, Any]:
    return cast(MutableMapping[str, Any], st.session_state)


def current_inputs() -> ScientificInputs | None:
    value = st.session_state.get("current_inputs")
    return cast(ScientificInputs | None, value)


def unit_preferences() -> UnitPreferences:
    """Return the current presentation units without changing scientific state."""

    return UnitPreferences(
        temperature=TemperatureUnit(
            str(st.session_state.get("temperature_unit", DEFAULT_UNITS.temperature))
        ),
        pressure=PressureUnit(
            str(st.session_state.get("pressure_unit", DEFAULT_UNITS.pressure))
        ),
    )
