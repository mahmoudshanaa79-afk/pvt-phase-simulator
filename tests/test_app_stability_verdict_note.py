"""P12 (b) in the app: a plain note when "stable" rests only on trivial trials.

The Overview shows one short note under the single-phase message, and the
Diagnostics page lists the engine's code, message and glossary meaning. A state
that the stability test proves unstable shows neither.
"""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from pvt_phase_simulator.eos.phase_stability import STABILITY_TRIVIAL_TRIALS_ONLY
from pvt_phase_simulator_ui.adapters import TRIVIAL_TRIALS_NOTE
from pvt_phase_simulator_ui.solver_codes import CODE_GLOSSARY
from tests.test_app_solver_codes import PAGES, ROOT


def _flash(temperature_k: float, pressure_mpa: float) -> AppTest:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=120).run()
    app.session_state["pressure_unit"] = "MPa"
    app.run()
    for index, value in enumerate((50.0, 0.0, 50.0)):
        app.number_input[index].set_value(value)
    app.number_input[3].set_value(temperature_k)
    app.number_input[4].set_value(pressure_mpa)
    app.run()
    next(b for b in app.button if b.label == "RUN FLASH").click().run()
    assert not app.exception
    return app


def _captions(app: AppTest) -> list[str]:
    return [item.value for item in app.caption]


def test_the_note_and_the_code_appear_inside_the_false_stable_band() -> None:
    app = _flash(316.0, 8.534)
    assert [item.value for item in app.subheader][0] == "Single phase"
    assert TRIVIAL_TRIALS_NOTE in _captions(app)
    app.switch_page(PAGES / "diagnostics.py").run()
    assert not app.exception
    table = next(
        frame.value
        for frame in app.dataframe
        if {"Code", "Meaning", "Message"} <= set(frame.value.columns)
    ).set_index("Code")
    row = table.loc[STABILITY_TRIVIAL_TRIALS_ONLY]
    assert row["Meaning"] == CODE_GLOSSARY[STABILITY_TRIVIAL_TRIALS_ONLY]
    assert row["Message"].startswith("Stable here means no instability was found")
    assert row["Severity"] == "warning"
    assert row["Category"] == "numerical_conditioning"


@pytest.mark.parametrize(("temperature_k", "pressure_mpa"), ((312.0, 8.534),))
def test_no_note_when_the_state_is_proved_unstable(
    temperature_k: float, pressure_mpa: float
) -> None:
    app = _flash(temperature_k, pressure_mpa)
    assert [item.value for item in app.subheader][0] == "Two phase"
    assert TRIVIAL_TRIALS_NOTE not in _captions(app)
