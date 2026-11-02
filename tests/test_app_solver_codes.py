"""Plain-language text for the saturation solver codes added by P2, P7 and P8.

Each code is exercised with a real state that the engine reports with it, both
directly and through the app (Phase Envelope and Diagnostics pages, the
Validation record table, the export and the HTML report). The engine's own code
must stay visible next to every explanation.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from pvt_phase_simulator.eos.flash import calculate_two_phase_flash
from pvt_phase_simulator.eos.phase_envelope import (
    EnvelopeContinuationSettings,
    calculate_phase_envelope,
)
from pvt_phase_simulator.eos.saturation_pressure import (
    SaturationKind,
    SaturationPressureResult,
    SaturationStatus,
    calculate_saturation_pressure,
)
from pvt_phase_simulator_ui import app as ui_app
from pvt_phase_simulator_ui import views
from pvt_phase_simulator_ui.adapters import validate_scientific_inputs
from pvt_phase_simulator_ui.exports import build_export_document, export_json_bytes
from pvt_phase_simulator_ui.model_scope import load_model_scope
from pvt_phase_simulator_ui.reports import export_engineering_report_html
from pvt_phase_simulator_ui.solver_codes import (
    BOUNDARY,
    EXPLANATIONS,
    HIDDEN,
    MULTIPLE,
    UNBRACKETED,
    explain_codes,
    record_solver_outcomes,
)

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "src" / "pvt_phase_simulator_ui" / "pages"
TEXT = {group: text for group, text in EXPLANATIONS}

#: (composition mol %, temperature K, direction, expected code group, status).
STATES = {
    "boundary": ((50.0, 50.0, 0.0), 250.0, "bubble", (BOUNDARY,), "converged"),
    "unbracketed": ((50.0, 50.0, 0.0), 260.0, "bubble", (UNBRACKETED,), "inconclusive"),
    "hidden": ((71.23, 28.77, 0.0), 243.6, "dew", (HIDDEN, MULTIPLE), "inconclusive"),
}


@cache
def _solve(name: str) -> tuple[SaturationPressureResult, SaturationPressureResult]:
    composition, temperature, _, _, _ = STATES[name]
    mixture = validate_scientific_inputs(composition, temperature, 5.0).mixture()
    return (
        calculate_saturation_pressure(
            mixture, temperature, SaturationKind.BUBBLE_POINT
        ),
        calculate_saturation_pressure(mixture, temperature, SaturationKind.DEW_POINT),
    )


def _direction(name: str) -> SaturationPressureResult:
    bubble, dew = _solve(name)
    return bubble if STATES[name][2] == "bubble" else dew


def test_a_code_pair_is_explained_once_and_unknown_codes_are_left_alone() -> None:
    assert explain_codes(["DEFAULTED_BINARY_INTERACTIONS"]) == ()
    pair = explain_codes([MULTIPLE, "SATURATION_TRIVIAL_STATE", HIDDEN])
    assert [item.codes for item in pair] == [(HIDDEN, MULTIPLE)]
    assert pair[0].label == f"{HIDDEN} + {MULTIPLE}"
    assert [item.codes for item in explain_codes([MULTIPLE])] == [(MULTIPLE,)]
    assert [item.codes for item in explain_codes([BOUNDARY, UNBRACKETED])] == [
        (BOUNDARY,),
        (UNBRACKETED,),
    ]


@pytest.mark.parametrize("name", STATES)
def test_the_engine_reports_each_state_with_its_code(name: str) -> None:
    _, _, _, group, status = STATES[name]
    result = _direction(name)
    codes = [item.code for item in result.diagnostics]
    assert set(group) <= set(codes)
    assert result.status.value == status
    if result.status is SaturationStatus.CONVERGED:
        assert result.pressure_pa is not None
    else:
        assert result.pressure_pa is None
        assert result.failure_reason
    assert [item.codes for item in explain_codes(codes)] == [group]


@cache
def _small_envelope() -> object:
    """A two-point envelope; the page tests need one to render, not its numbers."""

    settings = EnvelopeContinuationSettings(
        target_temperature_k=305.0, initial_temperature_step_k=5.0, maximum_points=2
    )
    mixture = validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 5.0).mixture()
    return calculate_phase_envelope(mixture, settings, settings, 295.0, 295.0)


@cache
def _small_flash() -> object:
    mixture = validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 5.0).mixture()
    return calculate_two_phase_flash(mixture, 300.0, 5.0e6)


def test_the_page_calls_the_engine_with_production_defaults() -> None:
    """The page's saturation function returns exactly the direct engine results."""

    composition, temperature, _, _, _ = STATES["hidden"]
    inputs = validate_scientific_inputs(composition, temperature, 5.0)
    assert views._calculate_operating_saturation.__wrapped__(inputs) == _solve("hidden")


def _run_app(name: str, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    """Submit the state and run the envelope action.

    The page's saturation results are the engine results of ``_solve`` (shown
    to be identical above); the flash and envelope are stand-ins, because only
    the saturation readout is under test here.
    """

    monkeypatch.setattr(ui_app, "_cached_flash", lambda _inputs: _small_flash())
    monkeypatch.setattr(views, "_calculate_envelope", lambda _inputs: _small_envelope())
    monkeypatch.setattr(views, "_calculate_extended_envelope", lambda _inputs: None)
    monkeypatch.setattr(
        views, "_calculate_operating_saturation", lambda _inputs: _solve(name)
    )
    composition, temperature, _, _, _ = STATES[name]
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=120).run()
    for index, value in enumerate(composition):
        app.number_input[index].set_value(value)
    app.number_input[3].set_value(temperature)
    app.run()
    next(b for b in app.button if b.label == "RUN FLASH").click().run()
    app.switch_page(PAGES / "phase_envelope.py").run()
    next(b for b in app.button if b.label == "RUN PHASE ENVELOPE").click().run()
    assert not app.exception
    return app


@pytest.mark.parametrize("name", STATES)
def test_the_phase_envelope_page_explains_the_code_next_to_the_code(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, direction, group, _ = STATES[name]
    app = _run_app(name, monkeypatch)
    stored = app.session_state["results"]["saturation"]
    assert stored == _solve(name)
    label = " + ".join(group)
    assert f"`{label}` — {TEXT[group]}" in [item.value for item in app.markdown]
    frames = [frame.value for frame in app.dataframe]
    rows = next(
        frame for frame in frames if "Bubble pressure" in list(frame["Field"])
    ).set_index("Field")
    row = rows.loc[f"{direction.capitalize()} pressure"]
    result = _direction(name)
    if result.status is SaturationStatus.CONVERGED:
        assert row["Value"].endswith("MPa")
    else:
        assert row["Value"] == "No pressure reported (Inconclusive)"
        assert result.failure_reason in row["Units / meaning"]
    for code in group:
        assert code in row["Units / meaning"]

    app.switch_page(PAGES / "diagnostics.py").run()
    assert not app.exception
    table = next(
        frame.value
        for frame in app.dataframe
        if "Plain language" in frame.value.columns
        and "Direction" in frame.value.columns
    ).set_index("Direction")
    assert TEXT[group] in table.loc[direction, "Plain language"]
    for code in group:
        assert code in table.loc[direction, "Codes"]


@pytest.mark.parametrize("name", STATES)
def test_exports_and_report_carry_the_code_and_its_reading(name: str) -> None:
    composition, temperature, direction, group, _ = STATES[name]
    inputs = validate_scientific_inputs(composition, temperature, 5.0)
    document = build_export_document(inputs, saturation_results=_solve(name))
    exported = json.loads(export_json_bytes(document))
    saturation = exported["results"]["saturation_at_operating_temperature"]
    record = saturation[f"{direction}_point"]
    assert set(group) <= set(record["diagnostic_codes"])
    assert {"codes": " + ".join(group), "text": TEXT[group]} in record[
        "diagnostic_explanations"
    ]
    html = export_engineering_report_html(
        document, scope=load_model_scope(ROOT), application_version="test"
    ).decode()
    assert "Saturation at the operating temperature" in html
    assert TEXT[group] in html
    for code in group:
        assert code in html


def test_an_export_without_saturation_says_it_was_not_calculated() -> None:
    inputs = validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 5.0)
    results = build_export_document(inputs)["results"]
    assert results["saturation_at_operating_temperature"] == {
        "calculation_status": "not_calculated"
    }


def test_the_validation_record_table_lists_hidden_and_boundary_states() -> None:
    dew = {item.source_point_id: item for item in record_solver_outcomes(ROOT, "dew")}
    hidden = dew["may2015_ch4_c2_013"]
    assert hidden.status == "inconclusive"
    assert {HIDDEN, MULTIPLE} <= set(hidden.codes)
    assert TEXT[(HIDDEN, MULTIPLE)] in hidden.explanation
    bubble = record_solver_outcomes(ROOT, "bubble")
    assert bubble, "P7 recovered bubble states carry BOUNDARY_SATURATION_ROOT"
    assert all(BOUNDARY in item.codes for item in bubble)
    assert all(item.status == "converged" for item in bubble)


def test_the_validation_page_shows_the_record_table() -> None:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=120).run()
    app.switch_page(PAGES / "validation.py").run()
    next(
        control
        for control in app.segmented_control
        if control.label == "Prediction direction"
    ).set_value("dew").run()
    next(b for b in app.button if b.label == "GENERATE VALIDATION FIGURES").click()
    app.run()
    assert not app.exception
    assert "Solver codes in the record" in [item.value for item in app.subheader]
    table = next(
        frame.value for frame in app.dataframe if "State" in frame.value.columns
    ).set_index("State")
    assert TEXT[(HIDDEN, MULTIPLE)] in table.loc["may2015_ch4_c2_013", "Plain language"]
