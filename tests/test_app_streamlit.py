"""Semantic startup and interaction tests for the installed Streamlit UI."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

import pvt_phase_simulator_ui
import pvt_phase_simulator_ui.styles

ROOT = Path(__file__).resolve().parents[1]


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
    assert [field.label for field in app.number_input] == [
        "Methane (mol %)",
        "Ethane (mol %)",
        "Propane (mol %)",
        "Temperature (K)",
        "Pressure (MPa)",
    ]
    assert [button.label for button in app.button] == ["RUN FLASH"]


def test_every_navigation_page_renders_without_hidden_calculation() -> None:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
    expected = {
        "overview.py": "Overview",
        "phase_envelope.py": "Phase envelope",
        "critical_point.py": "Critical point",
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
    app.button[0].click().run()
    assert "flash" not in app.session_state["results"]
    assert any("Submission unavailable" in error.value for error in app.error)


def test_valid_single_phase_uses_information_semantics_and_offers_exports() -> None:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
    app.number_input[4].set_value(20.0)
    app.button[0].click().run()

    assert not app.exception
    assert not any("Solver status" in error.value for error in app.error)
    assert any(
        "No two-phase split was required" in info.value
        and "0.5828298153218298" in info.value
        for info in app.info
    )
    downloads = app.get("download_button")
    assert [button.label for button in downloads] == ["Download CSV", "Download JSON"]
    assert [button.key for button in downloads] == [
        "download_current_case_csv",
        "download_current_case_json",
    ]


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
    assert app_source.count("st.Page(") == 5
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
