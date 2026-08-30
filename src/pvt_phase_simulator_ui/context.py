"""Shared Streamlit session access for page scripts."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any, cast

import streamlit as st

from pvt_phase_simulator_ui.adapters import ScientificInputs


def session() -> MutableMapping[str, Any]:
    return cast(MutableMapping[str, Any], st.session_state)


def current_inputs() -> ScientificInputs | None:
    value = st.session_state.get("current_inputs")
    return cast(ScientificInputs | None, value)
