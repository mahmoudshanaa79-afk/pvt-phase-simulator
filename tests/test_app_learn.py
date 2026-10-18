"""Learn mode: off by default, present on every page, and numerically honest."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from pvt_phase_simulator.eos.flash import calculate_two_phase_flash
from pvt_phase_simulator.eos.saturation_pressure import (
    SaturationKind,
    calculate_saturation_pressure,
)
from pvt_phase_simulator.fluid_models import METHANE, PROPANE, FluidMixture
from pvt_phase_simulator_ui.adapters import validate_scientific_inputs
from pvt_phase_simulator_ui.envelope_extension import trace_extended_envelope
from pvt_phase_simulator_ui.learn import LEARN_MODE_KEY, TOPICS
from pvt_phase_simulator_ui.state import INPUT_EXAMPLES

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "src" / "pvt_phase_simulator_ui" / "pages"


def _text(page: str) -> str:
    topic = TOPICS[page]  # type: ignore[index]
    return " ".join((topic.explanation, *topic.exercises))


def _default_mixture() -> FluidMixture:
    return validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 5.0e6).mixture()


def _shows_topic(app: AppTest, page: str) -> bool:
    # AppTest does not list expanders that carry an icon, so check the rendered
    # explanation itself.
    explanation = TOPICS[page].explanation  # type: ignore[index]
    return any(item.value == explanation for item in app.markdown)


def test_learn_mode_is_off_by_default_and_adds_nothing() -> None:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()

    assert not app.exception
    assert app.toggle(key=LEARN_MODE_KEY).value is False
    assert not any(_shows_topic(app, page) for page in TOPICS)


@pytest.mark.parametrize(
    ("page_file", "page_name"),
    (
        (None, "overview"),
        ("phase_envelope.py", "phase_envelope"),
        ("critical_point.py", "critical_point"),
        ("engineering_sweeps.py", "engineering_sweeps"),
        ("validation.py", "validation"),
        ("diagnostics.py", "diagnostics"),
    ),
)
def test_learn_mode_shows_the_page_topic(page_file: str | None, page_name: str) -> None:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=60).run()
    app.toggle(key=LEARN_MODE_KEY).set_value(True).run()
    if page_file is not None:
        app.switch_page(PAGES / page_file).run()

    assert not app.exception
    assert _shows_topic(app, page_name)
    others = [page for page in TOPICS if page != page_name]
    assert not any(_shows_topic(app, page) for page in others)


def test_learn_mode_runs_no_calculation() -> None:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
    before = dict(app.session_state["results"])
    app.toggle(key=LEARN_MODE_KEY).set_value(True).run()

    assert dict(app.session_state["results"]) == before


# The exercises quote numbers. Each is recomputed here from the engine so the text
# can never drift from the model without a failing test.


def test_overview_and_diagnostics_numbers() -> None:
    flash = calculate_two_phase_flash(_default_mixture(), 300.0, 5.0e6)

    assert flash.vapor_fraction == pytest.approx(0.57, abs=0.005)
    assert "about 0.57" in _text("overview")
    assert len(flash.iteration_history) == 15
    assert "15 iterations" in _text("diagnostics")
    residual = flash.iteration_history[-1].maximum_fugacity_equilibrium_residual
    assert residual < 1e-8
    assert "below 1e-8" in _text("diagnostics")
    low = calculate_two_phase_flash(_default_mixture(), 300.0, 2.0e6)
    assert low.phase_state.value == "single_phase"


def test_dew_points_quoted_in_the_text() -> None:
    mixture = _default_mixture()
    for temperature, quoted in ((300.0, "2.35 MPa"), (325.0, "5.24 MPa")):
        result = calculate_saturation_pressure(
            mixture,
            temperature,
            SaturationKind.DEW_POINT,
            saturation_newton_enabled=True,
        )
        assert result.pressure_pa is not None
        assert f"{result.pressure_pa / 1e6:.2f} MPa" == quoted
    assert "2.35 MPa" in _text("overview")
    assert "5.24 MPa" in _text("engineering_sweeps")


def test_isothermal_sweep_numbers_at_300_k() -> None:
    mixture = _default_mixture()
    at_8 = calculate_two_phase_flash(mixture, 300.0, 8.0e6)
    at_8_8 = calculate_two_phase_flash(mixture, 300.0, 8.8e6)
    at_8_5 = calculate_two_phase_flash(mixture, 300.0, 8.5e6)

    assert at_8.vapor_fraction == pytest.approx(0.20, abs=0.005)
    assert at_8_5.phase_state.value == "two_phase"
    assert at_8_8.phase_state.value == "single_phase"
    sweeps = _text("engineering_sweeps")
    assert "about 0.20 at 8 MPa" in sweeps
    assert "by 8.8 MPa" in sweeps
    assert "between 8.5 and 8.8 MPa" in _text("phase_envelope")


def test_retrograde_numbers_at_325_k() -> None:
    mixture = _default_mixture()
    fractions = {
        pressure: calculate_two_phase_flash(mixture, 325.0, pressure * 1e6)
        for pressure in (5.5, 7.0, 7.7, 7.85, 7.9)
    }

    # Liquid grows with pressure (vapour fraction falls), reaches about 0.80
    # near 7.7 MPa and then shrinks again before the flash becomes inconclusive.
    assert fractions[5.5].vapor_fraction > fractions[7.0].vapor_fraction
    assert fractions[7.7].vapor_fraction == pytest.approx(0.80, abs=0.005)
    assert fractions[7.85].vapor_fraction > fractions[7.7].vapor_fraction
    assert fractions[7.9].phase_state.value == "inconclusive"
    sweeps = _text("engineering_sweeps")
    assert "about 0.80 near 7.7 MPa" in sweeps
    assert "Near 7.9 MPa the flash becomes inconclusive" in sweeps


def test_envelope_and_critical_numbers() -> None:
    extension = trace_extended_envelope(_default_mixture(), 300.0)
    points = extension.bubble.points + extension.dew.points

    assert max(point.pressure_pa for point in points) == pytest.approx(
        8.8e6, abs=0.05e6
    )
    assert max(point.temperature_k for point in points) == pytest.approx(329.0, abs=0.5)
    envelope = _text("phase_envelope")
    assert "about 8.8 MPa (cricondenbar)" in envelope
    assert "about 329 K (cricondentherm)" in envelope
    seed = INPUT_EXAMPLES[2]
    assert seed.label == "Audited critical-solver seed"
    assert seed.temperature_k == pytest.approx(321.58, abs=0.005)
    assert seed.pressure_pa == pytest.approx(8.534e6, abs=0.0005e6)
    assert "321.58 K and 8.534 MPa" in _text("critical_point")
    at_seed = calculate_two_phase_flash(
        _default_mixture(), seed.temperature_k, seed.pressure_pa
    )
    assert at_seed.phase_state.value == "single_phase"


def test_pure_component_critical_temperatures_quoted() -> None:
    critical = _text("critical_point")

    assert f"about {METHANE.critical_temperature_k:.1f} K" in critical
    assert f"about {PROPANE.critical_temperature_k:.1f} K" in critical
