"""Application shell, navigation, and explicit scientific input boundary."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from pvt_phase_simulator_ui.adapters import (
    InputValidationError,
    ScientificInputs,
    composition_total,
    run_validated_flash,
    validate_scientific_inputs,
)
from pvt_phase_simulator_ui.context import session
from pvt_phase_simulator_ui.state import initialize_session, store_result

PAGES_DIRECTORY = Path(__file__).with_name("pages")


@st.cache_data(show_spinner=False, max_entries=16)
def _cached_flash(inputs: ScientificInputs) -> object:
    """Cache an unchanged submitted case without changing its calculations."""

    _, result = run_validated_flash(
        inputs.composition_mol_percent,
        inputs.temperature_k,
        inputs.pressure_mpa,
    )
    return result


def _input_form() -> tuple[ScientificInputs | None, bool]:
    with st.sidebar:
        st.subheader("Fluid inputs")
        st.caption("Verified components · precise mol %, K, and MPa entry")
        with st.form("scientific_inputs", border=True):
            methane = st.number_input(
                "Methane (mol %)", value=50.0, format="%.10g", key="methane_pct"
            )
            ethane = st.number_input(
                "Ethane (mol %)", value=0.0, format="%.10g", key="ethane_pct"
            )
            propane = st.number_input(
                "Propane (mol %)", value=50.0, format="%.10g", key="propane_pct"
            )
            temperature = st.number_input(
                "Temperature (K)", value=300.0, format="%.10g", key="temperature_k"
            )
            pressure = st.number_input(
                "Pressure (MPa)", value=5.0, format="%.10g", key="pressure_mpa"
            )
            values = (methane, ethane, propane)
            try:
                validated = validate_scientific_inputs(values, temperature, pressure)
                validation_error = None
            except InputValidationError as error:
                validated = None
                validation_error = str(error)
            total = composition_total(values)
            if validation_error is None:
                st.caption(f"Composition total: {total:.12g} mol % · ready")
            else:
                st.error(
                    f"Submission unavailable: {validation_error} "
                    f"Current total: {total:.12g} mol %."
                )
            submitted = st.form_submit_button(
                "RUN FLASH",
                type="primary",
                width="stretch",
                icon=":material/play_arrow:",
            )
        st.caption(
            "A submit converts mol % to fractions and MPa to internal Pa exactly once."
        )
    if submitted:
        session()["submitted_inputs"] = validated
        session()["input_error"] = validation_error
    return validated, bool(submitted and validated is not None)


def _header() -> None:
    st.caption("PVT PHASE SIMULATOR")
    st.title("Hydrocarbon Phase Behavior")
    st.caption("Peng-Robinson EOS - 3 verified components - kij = 0")


def run_app() -> None:
    """Render the installed UI and run heavy flash work after stable page chrome."""

    st.set_page_config(
        page_title="PVT Phase Simulator",
        page_icon=":material/science:",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    initialize_session(session())
    inputs, run_flash = _input_form()
    _header()
    page = st.navigation(
        [
            st.Page(
                PAGES_DIRECTORY / "overview.py",
                title="Overview",
                icon=":material/dashboard:",
                default=True,
            ),
            st.Page(
                PAGES_DIRECTORY / "phase_envelope.py",
                title="Phase Envelope",
                icon=":material/show_chart:",
            ),
            st.Page(
                PAGES_DIRECTORY / "critical_point.py",
                title="Critical Point",
                icon=":material/target:",
            ),
            st.Page(
                PAGES_DIRECTORY / "validation.py",
                title="Validation",
                icon=":material/fact_check:",
            ),
            st.Page(
                PAGES_DIRECTORY / "diagnostics.py",
                title="Diagnostics",
                icon=":material/monitoring:",
            ),
        ],
        position="sidebar",
    )
    page.run()
    if run_flash:
        assert inputs is not None
        with st.sidebar.status("Running production flash…", expanded=True) as status:
            status.write("Evaluating stability and phase split for the submitted case.")
            status.caption("An unchanged submitted case reuses the bounded UI cache.")
            try:
                result = _cached_flash(inputs)
                store_result(session(), "flash", result, inputs)
                status.update(label="Flash complete", state="complete", expanded=False)
            except (ValueError, ArithmeticError) as error:
                session()["flash_startup_error"] = str(error)
                status.update(label="Flash failed", state="error", expanded=True)
                st.error(f"Production flash failure: {error}")
            else:
                st.rerun()
