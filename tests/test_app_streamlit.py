"""Semantic startup and interaction tests for the installed Streamlit UI."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from dataclasses import replace
from io import StringIO
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import pvt_phase_simulator_ui
import pvt_phase_simulator_ui.styles
from pvt_phase_simulator.eos.flash import FlashConvergenceStatus
from pvt_phase_simulator_ui import app as ui_app
from pvt_phase_simulator_ui import views
from pvt_phase_simulator_ui.adapters import (
    run_validated_flash,
    validate_scientific_inputs,
)
from pvt_phase_simulator_ui.case_files import case_from_state, serialize_case
from pvt_phase_simulator_ui.model_scope import load_model_scope
from pvt_phase_simulator_ui.units import (
    PressureUnit,
    TemperatureUnit,
    pressure_from_pa,
    temperature_from_k,
)

ROOT = Path(__file__).resolve().parents[1]


def _button(app: AppTest, label: str) -> object:
    return next(button for button in app.button if button.label == label)


def test_ui_and_styles_are_installed_packages() -> None:
    package_path = Path(pvt_phase_simulator_ui.__file__).resolve()
    styles_path = Path(pvt_phase_simulator_ui.styles.__file__).resolve()
    assert "src" in package_path.parts
    assert package_path.parent.name == "pvt_phase_simulator_ui"
    assert styles_path.parent == package_path.parent


def test_clean_shell_compatibility_entrypoint_imports_without_pythonpath() -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [sys.executable, str(ROOT / "app" / "streamlit_app.py")],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    combined = completed.stdout + completed.stderr
    assert completed.returncode == 0, combined
    assert "ModuleNotFoundError" not in combined
    assert "No module named 'app'" not in combined


def test_streamlit_apptest_starts_and_exposes_explicit_form_boundary() -> None:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
    assert not app.exception
    assert [selector.label for selector in app.selectbox] == ["Example case"]
    assert [(control.label, control.options) for control in app.segmented_control] == [
        ("Temperature unit", ["K", "°C", "°F"]),
        ("Pressure unit", ["Pa", "MPa", "bar", "psi"]),
    ]
    assert app.selectbox[0].options == [
        "Default two-phase-oriented case",
        "Known single-phase case at 300 K and 20 MPa",
        "Audited critical-solver seed",
    ]
    assert [field.label for field in app.number_input] == [
        "Methane (mol %)",
        "Ethane (mol %)",
        "Propane (mol %)",
        "Temperature (K)",
        "Pressure (MPa)",
    ]
    assert [button.label for button in app.button] == ["Load case", "RUN FLASH"]
    assert app.button[0].disabled
    assert [button.label for button in app.get("download_button")] == ["Save case"]


def test_case_upload_with_out_of_range_integer_surfaces_clean_error() -> None:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
    document = json.loads(serialize_case(case_from_state(app.session_state)))
    document["inputs"]["temperature_k"] = 10**400
    payload = json.dumps(document).encode()

    app.file_uploader[0].set_value(
        ("out-of-range.json", payload, "application/json")
    ).run()
    _button(app, "Load case").click().run()

    assert not app.exception
    assert any(
        "Case load unavailable: Case file schema is invalid: "
        "inputs.temperature_k must be a finite number." in error.value
        for error in app.error
    )


def test_field_unit_selection_preserves_state_and_submits_si_to_engine() -> None:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()

    app.segmented_control[0].set_value("°F")
    app.segmented_control[1].set_value("psi")
    app.run()

    fields = {field.label: field.value for field in app.number_input}
    assert fields["Temperature (°F)"] == pytest.approx(80.33)
    assert fields["Pressure (psi)"] == pytest.approx(725.1886886510841)

    _button(app, "RUN FLASH").click().run()
    submitted = app.session_state["submitted_inputs"]
    assert submitted.temperature_k == pytest.approx(300.0, abs=1e-13)
    assert submitted.pressure_pa == 5_000_000.0
    result = app.session_state["results"]["flash"]
    assert result.temperature_k == submitted.temperature_k
    assert result.pressure_pa == submitted.pressure_pa
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["Temperature"] == "80.33 °F"
    assert metrics["Pressure"] == "725.189 psi"


def test_presentation_unit_change_does_not_stale_a_calculated_result() -> None:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
    _button(app, "RUN FLASH").click().run()
    result = app.session_state["results"]["flash"]

    app.segmented_control[0].set_value("°C")
    app.segmented_control[1].set_value("bar")
    app.run()

    assert app.session_state["results"]["flash"] is result
    assert not any("Stale result" in message.value for message in app.warning)
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["Temperature"] == "26.85 °C"
    assert metrics["Pressure"] == "50 bar"
    assert len(app.get("download_button")) == 4


@pytest.mark.parametrize(
    ("temperature_k", "pressure_mpa", "temperature_unit", "pressure_unit"),
    [
        (
            373.7993794602593,
            4.045258429683001,
            TemperatureUnit.FAHRENHEIT,
            PressureUnit.BAR,
        ),
        (
            287.1234567890123,
            16.725351632253563,
            TemperatureUnit.CELSIUS,
            PressureUnit.PSI,
        ),
    ],
)
def test_non_exact_unit_round_trip_preserves_result_identity(
    temperature_k: float,
    pressure_mpa: float,
    temperature_unit: TemperatureUnit,
    pressure_unit: PressureUnit,
) -> None:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
    app.number_input[3].set_value(temperature_k)
    app.number_input[4].set_value(pressure_mpa)
    _button(app, "RUN FLASH").click().run()
    result = app.session_state["results"]["flash"]
    submitted = app.session_state["submitted_inputs"]

    displayed_temperature = temperature_from_k(
        submitted.temperature_k, temperature_unit
    )
    displayed_pressure = pressure_from_pa(submitted.pressure_pa, pressure_unit)
    round_tripped = validate_scientific_inputs(
        submitted.composition_mol_percent,
        displayed_temperature,
        displayed_pressure,
        temperature_unit=temperature_unit,
        pressure_unit=pressure_unit,
    )
    assert round_tripped.signature != submitted.signature

    app.segmented_control[0].set_value(temperature_unit.value)
    app.segmented_control[1].set_value(pressure_unit.value)
    app.run()

    assert app.session_state["results"]["flash"] is result
    assert app.session_state["current_inputs"].signature == submitted.signature
    assert not any("Stale result" in message.value for message in app.warning)
    assert len(app.get("download_button")) == 4

    app.number_input[3].set_value(displayed_temperature + 1.0e-9)
    app.run()

    assert any("Stale result" in message.value for message in app.warning)
    assert [button.label for button in app.get("download_button")] == ["Save case"]


def test_overview_exposes_repository_backed_model_and_limitations_panel() -> None:
    scope = load_model_scope(ROOT)
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()

    assert not app.exception
    assert "Model and limitations" in [item.value for item in app.subheader]
    copy = "\n".join(item.value for item in app.markdown)
    assert scope.eos_name in copy
    assert ", ".join(scope.verified_component_names) in copy
    assert scope.interaction_policy.value in copy
    assert f"{scope.validation_state_count} experimental VLE states" in copy
    assert all(system in copy for system in scope.validation_system_names)
    assert "CriticalPointStatus.CONVERGED" in copy
    assert "never fabricated or interpolated" in copy
    assert all(source.citation in copy for source in scope.property_sources)
    assert scope.validation_source.citation in copy
    assert all(source.doi in copy for source in scope.property_sources if source.doi)
    assert scope.validation_source.doi in copy
    assert any("not a commercial PVT package" in item.value for item in app.warning)


def test_model_scope_reads_recorded_component_and_validation_provenance() -> None:
    scope = load_model_scope(ROOT)

    assert scope.verified_component_names == ("Methane", "Ethane", "Propane")
    assert scope.validation_state_count == 40
    assert scope.validation_system_names == (
        "Methane + Ethane",
        "Methane + Propane",
    )
    assert scope.validation_temperature_range_k == (203.22, 283.38)
    assert scope.validation_pressure_range_mpa == (0.891, 8.32)
    assert {source.doi for source in scope.property_sources} == {
        "10.1021/acs.jced.5c00110"
    }
    assert scope.validation_source.doi == "10.1021/acs.jced.5b00610"
    assert scope.validation_artifact == Path(
        "docs/validation/module17_vle_validation.csv"
    )


def test_example_selection_populates_inputs_without_populating_results() -> None:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()

    app.selectbox[0].select("Audited critical-solver seed").run()

    assert not app.exception
    assert [field.value for field in app.number_input] == [
        50.0,
        0.0,
        50.0,
        321.5829183194,
        8.53444323606381,
    ]
    assert app.session_state["submitted_inputs"] is None
    assert app.session_state["results"] == {}


def test_custom_edits_after_example_selection_validate_and_submit_normally() -> None:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
    app.selectbox[0].select("Known single-phase case at 300 K and 20 MPa").run()
    app.number_input[0].set_value(49.0)
    app.number_input[1].set_value(1.0)
    app.number_input[3].set_value(301.25)
    _button(app, "RUN FLASH").click().run()

    assert not app.exception
    submitted = app.session_state["submitted_inputs"]
    assert submitted.composition_mol_percent == (49.0, 1.0, 50.0)
    assert submitted.temperature_k == 301.25
    assert submitted.pressure_mpa == 20.0
    assert "flash" in app.session_state["results"]


def test_every_navigation_page_renders_without_hidden_calculation() -> None:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
    expected = {
        "overview.py": "Overview",
        "phase_envelope.py": "Phase envelope",
        "critical_point.py": "Critical point",
        "engineering_sweeps.py": "Engineering sweeps",
        "validation.py": "Validation",
        "diagnostics.py": "Diagnostics",
    }
    for filename, heading in expected.items():
        page = ROOT / "src" / "pvt_phase_simulator_ui" / "pages" / filename
        app.switch_page(page).run()
        assert not app.exception
        assert heading in [header.value for header in app.header]
        assert app.session_state["results"] == {}


def test_invalid_form_submission_never_creates_a_flash_result() -> None:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
    app.number_input[0].set_value(40.0)
    _button(app, "RUN FLASH").click().run()
    assert "flash" not in app.session_state["results"]
    assert any("Submission unavailable" in error.value for error in app.error)


def test_valid_two_phase_submission_preserves_science_and_success_semantics() -> None:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
    _button(app, "RUN FLASH").click().run()

    assert not app.exception
    result = app.session_state["results"]["flash"]
    assert str(result.phase_state) == "two_phase"
    assert str(result.convergence_status) == "converged"
    assert result.vapor_fraction == pytest.approx(0.5697996937735098, abs=2e-12)
    assert result.liquid_fraction == pytest.approx(0.4302003062264902, abs=2e-12)
    assert result.liquid_phase.selected_compressibility_factor == pytest.approx(
        0.1724373888123013, abs=2e-12
    )
    assert result.vapor_phase.selected_compressibility_factor == pytest.approx(
        0.7243397958656836, abs=2e-12
    )
    assert result.single_phase_root is None
    assert result.failure_reason is None
    assert [message.value for message in app.success] == ["Solver status: Converged"]
    assert not app.error
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["Vapor fraction"] == "0.5698"
    assert metrics["Liquid fraction"] == "0.4302"
    assert metrics["Vapor Z"] == "0.72434"
    assert metrics["Liquid Z"] == "0.172437"


def test_valid_single_phase_uses_information_semantics_and_offers_exports() -> None:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
    app.number_input[4].set_value(20.0)
    _button(app, "RUN FLASH").click().run()

    assert not app.exception
    result = app.session_state["results"]["flash"]
    assert str(result.phase_state) == "single_phase"
    assert str(result.convergence_status) == "not_attempted"
    assert result.vapor_fraction is None
    assert result.liquid_fraction is None
    assert result.single_phase_root == pytest.approx(0.5828298153218298, abs=2e-12)
    assert not any("Solver status" in error.value for error in app.error)
    assert any(
        "No two-phase split was required" in info.value
        and repr(result.single_phase_root) in info.value
        for info in app.info
    )
    downloads = app.get("download_button")
    downloads_by_label = {button.label: button for button in downloads}
    assert set(downloads_by_label) == {
        "Save case",
        "Download report",
        "Download CSV",
        "Download JSON",
    }
    assert downloads_by_label["Save case"].key == "save_openphase_case"
    assert downloads_by_label["Download report"].key == "download_engineering_report"
    assert downloads_by_label["Download CSV"].key == "download_current_case_csv"
    assert downloads_by_label["Download JSON"].key == "download_current_case_json"


def test_structured_flash_failure_is_presented_as_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, baseline = run_validated_flash((50.0, 0.0, 50.0), 300.0, 5.0)
    failure = replace(
        baseline,
        convergence_status=FlashConvergenceStatus.FAILED,
        failure_reason="STRUCTURED_TEST_FAILURE",
    )
    monkeypatch.setattr(ui_app, "_cached_flash", lambda _inputs: failure)

    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
    _button(app, "RUN FLASH").click().run()

    assert not app.exception
    stored = app.session_state["results"]["flash"]
    assert stored.convergence_status is FlashConvergenceStatus.FAILED
    assert stored.failure_reason == "STRUCTURED_TEST_FAILURE"
    assert any(
        "Solver status: Failed" in message.value
        and "STRUCTURED_TEST_FAILURE" in message.value
        for message in app.error
    )
    assert not app.success
    assert not any("No two-phase split was required" in item.value for item in app.info)


def test_download_widgets_receive_real_payloads_and_mime_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, dict[str, object]] = {}

    def capture_download(label: str, **kwargs: object) -> bool:
        captured[label] = kwargs
        return False

    monkeypatch.setattr(views.st, "download_button", capture_download)
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
    app.number_input[4].set_value(20.0)
    _button(app, "RUN FLASH").click().run()

    assert not app.exception
    assert set(captured) == {
        "Save case",
        "Download report",
        "Download CSV",
        "Download JSON",
    }
    saved_case = captured["Save case"]
    assert saved_case["file_name"] == "openphase-case.json"
    assert saved_case["mime"] == "application/json"
    assert json.loads(saved_case["data"])["schema_version"] == "1.0.0"
    csv_download = captured["Download CSV"]
    json_download = captured["Download JSON"]
    report_download = captured["Download report"]
    assert report_download["file_name"] == "openphase-engineering-report.html"
    assert report_download["mime"] == "text/html;charset=utf-8"
    assert isinstance(report_download["data"], bytes)
    assert b"<!doctype html>" in report_download["data"]
    assert csv_download["file_name"] == "pvt-current-case.csv"
    assert csv_download["mime"] == "text/csv;charset=utf-8"
    assert json_download["file_name"] == "pvt-current-case.json"
    assert json_download["mime"] == "application/json"

    csv_payload = csv_download["data"]
    json_payload = json_download["data"]
    assert isinstance(csv_payload, bytes)
    assert isinstance(json_payload, bytes)
    rows = list(csv.DictReader(StringIO(csv_payload.decode("utf-8-sig"))))
    values = {(row["section"], row["path"]): row["value"] for row in rows}
    document = json.loads(json_payload)
    result = app.session_state["results"]["flash"]
    assert values[("case", "pressure_pa")] == "20000000.0"
    assert values[("results", "flash.selected_single_phase_z.value")] == repr(
        result.single_phase_root
    )
    assert document["case"]["pressure_pa"] == 20_000_000.0
    assert (
        document["results"]["flash"]["selected_single_phase_z"]["value"]
        == result.single_phase_root
    )


def test_changed_inputs_keep_result_visible_but_stale_and_disable_exports() -> None:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
    _button(app, "RUN FLASH").click().run()
    original = app.session_state["results"]["flash"]
    assert len(app.get("download_button")) == 4

    app.selectbox[0].select("Known single-phase case at 300 K and 20 MPa").run()

    assert not app.exception
    assert app.session_state["results"]["flash"] is original
    assert app.session_state["submitted_inputs"].pressure_mpa == 5.0
    assert app.number_input[4].value == 20.0
    assert any("Stale result" in message.value for message in app.warning)
    assert [button.label for button in app.get("download_button")] == ["Save case"]
    assert any(
        "Downloads are unavailable until RUN FLASH recalculates" in caption.value
        for caption in app.caption
    )


def test_navigation_module21_reuse_and_no_deprecated_width_argument() -> None:
    app_source = (ROOT / "src" / "pvt_phase_simulator_ui" / "app.py").read_text(
        encoding="utf-8"
    )
    view_source = (ROOT / "src" / "pvt_phase_simulator_ui" / "views.py").read_text(
        encoding="utf-8"
    )
    all_ui_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "src" / "pvt_phase_simulator_ui").rglob("*.py")
    )
    assert "st.navigation" in app_source
    assert 'position="sidebar"' in app_source
    assert app_source.count("st.Page(") == 6
    assert "st.form(" in app_source
    assert "st.form_submit_button(" in app_source
    assert "plot_phase_envelope(" in view_source
    assert "plot_validation_pressure_parity(" in view_source
    assert "plot_validation_retrospective_diagnostics(" in view_source
    assert "NOT PRODUCTION PREDICTIONS" in view_source
    assert "use_container_width" not in all_ui_source


def test_disabled_scientific_actions_explain_flash_requirement() -> None:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
    phase_page = ROOT / "src" / "pvt_phase_simulator_ui" / "pages" / "phase_envelope.py"
    app.switch_page(phase_page).run()
    phase_action = next(
        button for button in app.button if button.label == "RUN PHASE ENVELOPE"
    )
    assert phase_action.disabled
    assert any("Submit RUN FLASH to enable" in caption.value for caption in app.caption)

    critical_page = (
        ROOT / "src" / "pvt_phase_simulator_ui" / "pages" / "critical_point.py"
    )
    app.switch_page(critical_page).run()
    critical_actions = [
        button for button in app.button if button.label.startswith("RUN CRITICAL")
    ]
    assert len(critical_actions) == 2
    assert all(button.disabled for button in critical_actions)
    assert any("Submit RUN FLASH to enable" in caption.value for caption in app.caption)


def test_ui_contains_no_duplicated_thermodynamic_implementations() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in (ROOT / "src" / "pvt_phase_simulator_ui").rglob("*.py")
    )
    forbidden_definitions = (
        "def peng_robinson",
        "def fugacity",
        "def rachford_rice",
        "def tpd",
        "def saturation_pressure",
        "def criticality",
    )
    assert not any(definition in source for definition in forbidden_definitions)
