"""Application shell, navigation, and explicit scientific input boundary."""

from __future__ import annotations

import logging
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

import streamlit as st

from pvt_phase_simulator.eos.flash import calculate_two_phase_flash
from pvt_phase_simulator_ui.adapters import (
    InputValidationError,
    ScientificInputs,
    composition_total,
    validate_scientific_inputs,
)
from pvt_phase_simulator_ui.case_files import (
    CaseFileError,
    OpenPhaseCase,
    apply_case_to_state,
    case_from_state,
    load_case,
    serialize_case,
)
from pvt_phase_simulator_ui.context import session
from pvt_phase_simulator_ui.state import (
    INPUT_EXAMPLES,
    apply_selected_input_example,
    begin_result_attempt,
    initialize_session,
    store_result,
    store_result_action_failure,
    synchronize_unit_inputs,
)
from pvt_phase_simulator_ui.units import (
    PRESSURE_UNITS,
    TEMPERATURE_UNITS,
    PressureUnit,
    TemperatureUnit,
)

PAGES_DIRECTORY = Path(__file__).with_name("pages")
LOGGER = logging.getLogger(__name__)

FLASH_ACTION_FAILURE = (
    "The flash calculation stopped unexpectedly and did not return a result. "
    "Any earlier flash result was removed so it cannot be mistaken for the "
    "current calculation. Review the inputs and try again."
)
PAGE_RENDER_FAILURE = (
    "This view could not be displayed because the application encountered an "
    "unexpected error. No failed calculation has been presented as a result. "
    "Return to Overview or retry the action."
)
INPUT_PANEL_FAILURE = (
    "The input panel could not be prepared because the application encountered "
    "an unexpected error. No calculation was run. Refresh the page and try again."
)
CASE_LOAD_FAILURE = (
    "Case load unavailable because the file could not be processed safely. "
    "No inputs were changed and no calculation was run."
)
CASE_SAVE_FAILURE = (
    "Case save unavailable because the current inputs could not be serialized "
    "safely. Review the inputs and try again."
)


@st.cache_data(show_spinner=False, max_entries=16)
def _cached_flash(inputs: ScientificInputs) -> object:
    """Cache an unchanged submitted case without changing its calculations."""

    return calculate_two_phase_flash(
        inputs.mixture(),
        inputs.temperature_k,
        inputs.pressure_pa,
    )


def _load_case_inputs(
    data: bytes | str, state: MutableMapping[str, Any]
) -> OpenPhaseCase:
    """Validate a complete file before atomically restoring input state."""

    case = load_case(data)
    apply_case_to_state(case, state)
    return case


def _case_controls() -> None:
    """Render input-only case persistence without submitting a calculation."""

    with st.expander("Save or load case"):
        st.caption(
            "Cases are versioned JSON inputs only. Loading validates the entire "
            "file and never runs a calculation."
        )
        uploaded = st.file_uploader(
            "OpenPhase case file",
            type="json",
            max_upload_size=1,
            key="openphase_case_file",
        )
        load_requested = st.button(
            "Load case",
            disabled=uploaded is None,
            key="load_openphase_case",
            icon=":material/upload_file:",
        )
        if load_requested and uploaded is not None:
            try:
                _load_case_inputs(uploaded.getvalue(), session())
            except CaseFileError as error:
                st.error(f"Case load unavailable: {error}")
            except Exception:  # noqa: BLE001 - uploaded data must not expose internals
                LOGGER.exception("Unexpected failure while loading a case file")
                st.error(CASE_LOAD_FAILURE)
            else:
                st.success("Case loaded. Inputs restored; no calculation was run.")

        try:
            payload = serialize_case(case_from_state(session()))
        except CaseFileError as error:
            st.caption(f"Save unavailable until all case inputs are valid: {error}")
        except Exception:  # noqa: BLE001 - session data must not expose internals
            LOGGER.exception("Unexpected failure while serializing a case file")
            st.caption(CASE_SAVE_FAILURE)
        else:
            st.download_button(
                "Save case",
                data=payload,
                file_name="openphase-case.json",
                mime="application/json",
                key="save_openphase_case",
                on_click="ignore",
                width="content",
                icon=":material/download:",
            )


def _input_form() -> tuple[ScientificInputs | None, bool]:
    with st.sidebar:
        # Capture any field edits from the prior browser event before building
        # the downloadable case, and before any load can replace widget state.
        synchronize_unit_inputs(session())
        _case_controls()
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
    try:
        initialize_session(session())
        inputs, run_flash = _input_form()
    except Exception:  # noqa: BLE001 - never expose Streamlit's raw exception UI
        LOGGER.exception("Unexpected error while preparing the scientific input panel")
        st.error(INPUT_PANEL_FAILURE, icon=":material/error:")
        return
    if run_flash:
        begin_result_attempt(session(), "flash")
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
    try:
        page.run()
    except Exception:  # noqa: BLE001 - never expose Streamlit's raw exception UI
        LOGGER.exception("Unexpected error while rendering Streamlit page %s", page)
        st.error(PAGE_RENDER_FAILURE, icon=":material/error:")
    if run_flash:
        assert inputs is not None
        with st.sidebar.status("Running production flash…", expanded=True) as status:
            status.write("Evaluating stability and phase split for the submitted case.")
            status.caption("An unchanged submitted case reuses the bounded UI cache.")
            try:
                result = _cached_flash(inputs)
                store_result(session(), "flash", result, inputs)
                status.update(label="Flash complete", state="complete", expanded=False)
            except Exception:  # noqa: BLE001 - preserve a safe application boundary
                LOGGER.exception("Unexpected failure in the production flash action")
                store_result_action_failure(session(), "flash", FLASH_ACTION_FAILURE)
                status.update(label="Flash failed", state="error", expanded=True)
                st.error(FLASH_ACTION_FAILURE, icon=":material/error:")
            else:
                st.rerun()
