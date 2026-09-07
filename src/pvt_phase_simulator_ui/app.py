"""Application shell, navigation, and explicit scientific input boundary."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from pvt_phase_simulator.eos.flash import calculate_two_phase_flash
from pvt_phase_simulator_ui.adapters import (
    InputValidationError,
    ScientificInputs,
    composition_total,
    validate_scientific_inputs,
)
from pvt_phase_simulator_ui.context import session
from pvt_phase_simulator_ui.state import (
    INPUT_EXAMPLES,
    apply_selected_input_example,
    initialize_session,
    store_result,
    synchronize_unit_inputs,
)
from pvt_phase_simulator_ui.units import (
    PRESSURE_UNITS,
    TEMPERATURE_UNITS,
    PressureUnit,
    TemperatureUnit,
)

PAGES_DIRECTORY = Path(__file__).with_name("pages")


@st.cache_data(show_spinner=False, max_entries=16)
def _cached_flash(inputs: ScientificInputs) -> object:
    """Cache an unchanged submitted case without changing its calculations."""

    return calculate_two_phase_flash(
        inputs.mixture(),
        inputs.temperature_k,
        inputs.pressure_pa,
    )


def _input_form() -> tuple[ScientificInputs | None, bool]:
    with st.sidebar:
        st.subheader("Fluid inputs")
        st.caption("Display and entry units")
        st.segmented_control(
            "Temperature unit",
            options=[unit.value for unit in TEMPERATURE_UNITS],
            key="temperature_unit",
            on_change=synchronize_unit_inputs,
            args=(session(),),
        )
        st.segmented_control(
            "Pressure unit",
            options=[unit.value for unit in PRESSURE_UNITS],
            key="pressure_unit",
            on_change=synchronize_unit_inputs,
            args=(session(),),
        )
        synchronize_unit_inputs(session())
        st.selectbox(
            "Example case",
            options=[example.label for example in INPUT_EXAMPLES],
            index=None,
            placeholder="Choose an example",
            key="input_example",
            on_change=apply_selected_input_example,
            args=(session(),),
        )
        selected_label = session().get("input_example")
        prior_label = session().get("rendered_input_example")
        selected_example = next(
            (
                example
                for example in INPUT_EXAMPLES
                if example.label == selected_label and selected_label != prior_label
            ),
            None,
        )
        st.caption("Examples fill the inputs only; they do not run a calculation.")
        temperature_unit = str(session()["temperature_unit"])
        pressure_unit = str(session()["pressure_unit"])
        st.caption(
            "Verified components · precise mol % entry · "
            f"{temperature_unit} and {pressure_unit} field units"
        )
        with st.form("scientific_inputs", border=True):
            methane = st.number_input(
                "Methane (mol %)", format="%.15g", key="methane_pct"
            )
            ethane = st.number_input("Ethane (mol %)", format="%.15g", key="ethane_pct")
            propane = st.number_input(
                "Propane (mol %)", format="%.15g", key="propane_pct"
            )
            temperature = st.number_input(
                f"Temperature ({temperature_unit})",
                format="%.17g",
                key="temperature_value",
            )
            pressure = st.number_input(
                f"Pressure ({pressure_unit})",
                format="%.17g",
                key="pressure_value",
            )
            if selected_example is None:
                values = (methane, ethane, propane)
            else:
                values = (
                    selected_example.methane_pct,
                    selected_example.ethane_pct,
                    selected_example.propane_pct,
                )
                temperature = float(session()["temperature_value"])
                pressure = float(session()["pressure_value"])
            try:
                # Validate the displayed fields, but construct scientific identity
                # from the authoritative SI state maintained by the unit callback.
                validate_scientific_inputs(
                    values,
                    temperature,
                    pressure,
                    temperature_unit=temperature_unit,
                    pressure_unit=pressure_unit,
                )
                validated = validate_scientific_inputs(
                    values,
                    float(session()["temperature_k"]),
                    float(session()["pressure_pa"]),
                    temperature_unit=TemperatureUnit.KELVIN,
                    pressure_unit=PressureUnit.PA,
                )
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
        st.caption("A submit converts field values to internal K and Pa exactly once.")
    session()["rendered_input_example"] = session().get("input_example")
    session()["current_inputs"] = validated
    if submitted:
        session()["submitted_inputs"] = validated
        session()["input_error"] = validation_error
        if validated is not None:
            session()["temperature_k"] = validated.temperature_k
            session()["pressure_pa"] = validated.pressure_pa
            session()["pressure_mpa"] = validated.pressure_mpa
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
                PAGES_DIRECTORY / "engineering_sweeps.py",
                title="Engineering Sweeps",
                icon=":material/ssid_chart:",
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
