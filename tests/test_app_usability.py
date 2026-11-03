"""Usability fixes from docs/investigations/usability_review.md, one test each.

Each finding fixed in the app layer is pinned here so it cannot regress. No
number changes: the texts quote values the engine already returned.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from pvt_phase_simulator.eos.phase_envelope import (
    EnvelopeContinuationSettings,
    calculate_phase_envelope,
)
from pvt_phase_simulator_ui import app as ui_app
from pvt_phase_simulator_ui import views
from pvt_phase_simulator_ui.adapters import ScientificInputs
from pvt_phase_simulator_ui.learn import LAB_BASE_URL, LABS, labs_markdown

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "src" / "pvt_phase_simulator_ui" / "pages"


def _app() -> AppTest:
    return AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=300).run()


def _button(app: AppTest, label: str) -> Any:
    return next(item for item in app.button if item.label == label)


def _walk(node: Any) -> Iterator[Any]:
    """Every element of the main area, in page order."""

    children = getattr(node, "children", None)
    if isinstance(children, dict):
        for key in sorted(children):
            yield from _walk(children[key])
    else:
        yield node


def _texts_in_order(app: AppTest) -> list[str]:
    return [
        str(getattr(element, "value", ""))
        for element in _walk(app.main)
        if isinstance(getattr(element, "value", None), str)
    ]


def _index(texts: list[str], fragment: str) -> int:
    return next(index for index, text in enumerate(texts) if fragment in text)


# Finding 1: an honest time expectation for the envelope.


def test_the_envelope_page_states_an_honest_first_run_time() -> None:
    assert "20–30 seconds" not in Path(views.__file__).read_text(encoding="utf-8")
    app = _app()
    _button(app, "RUN FLASH").click().run()
    app.switch_page(PAGES / "phase_envelope.py").run()
    info = [item.value for item in app.info]
    assert any(
        "Press RUN PHASE ENVELOPE above." in text and views.ENVELOPE_TIME_NOTE in text
        for text in info
    )


def test_the_running_status_shows_the_same_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def short(inputs: ScientificInputs) -> object:
        settings = EnvelopeContinuationSettings(
            target_temperature_k=inputs.temperature_k,
            initial_temperature_step_k=5.0,
            maximum_points=2,
        )
        start = inputs.temperature_k - 10.0
        return calculate_phase_envelope(
            inputs.mixture(), settings, settings, start, start
        )

    monkeypatch.setattr(views, "_calculate_envelope", short)
    monkeypatch.setattr(views, "_calculate_extended_envelope", lambda _inputs: None)
    monkeypatch.setattr(views, "_calculate_operating_saturation", lambda _inputs: None)
    app = _app()
    _button(app, "RUN FLASH").click().run()
    app.switch_page(PAGES / "phase_envelope.py").run()
    _button(app, "RUN PHASE ENVELOPE").click().run()
    assert not app.exception
    assert views.ENVELOPE_TIME_NOTE in [item.value for item in app.markdown]


# Finding 2: what to do first, and the result before the model panel.


def test_overview_starts_with_what_to_do_first() -> None:
    texts = _texts_in_order(_app())
    start = _index(texts, "**Start here.**")
    assert start < _index(texts, "Model and limitations")
    for step in ("**Example case**", "**RUN FLASH**", "Turn on Learn mode"):
        assert step in texts[start]


def test_after_a_flash_the_result_comes_before_the_model_panel() -> None:
    app = _app()
    _button(app, "RUN FLASH").click().run()
    texts = _texts_in_order(app)
    assert not any("**Start here.**" in text for text in texts)
    assert _index(texts, "Two phase") < _index(texts, "Model and limitations")


# Finding 3: the sidebar does not cover the page on a phone.


def test_the_sidebar_starts_expanded_only_where_there_is_room() -> None:
    source = Path(ui_app.__file__).read_text(encoding="utf-8")
    assert 'initial_sidebar_state="auto"' in source
    # tests/test_app_browser.py checks the collapsed sidebar at 390 px.


# Finding 4: empty states say what to press.


@pytest.mark.parametrize(
    ("page", "message"),
    (
        ("phase_envelope.py", "Press RUN PHASE ENVELOPE above."),
        ("critical_point.py", "Press RUN CRITICAL SOLVER above"),
        ("engineering_sweeps.py", "then press RUN SWEEP."),
    ),
)
def test_each_empty_state_names_the_button_to_press(page: str, message: str) -> None:
    app = _app()
    _button(app, "RUN FLASH").click().run()
    app.switch_page(PAGES / page).run()
    assert any(message in item.value for item in app.info)


def test_the_lock_caption_says_where_run_flash_is() -> None:
    app = _app()
    app.switch_page(PAGES / "phase_envelope.py").run()
    assert any(
        "Submit RUN FLASH to enable this action." in item.value
        and "in the sidebar" in item.value
        for item in app.caption
    )


# Finding 5: the composition table states its unit and precision.


def test_the_composition_table_format_is_valid_and_states_the_unit() -> None:
    app = _app()
    _button(app, "RUN FLASH").click().run()
    frames = [frame for frame in app.dataframe if "Methane" in frame.value.columns]
    assert frames
    config = json.loads(frames[0].proto.columns)
    formats = {config[name]["type_config"]["format"] for name in ("Methane",)}
    assert formats == {"%.6g mol %%"}


# Finding 6: the phase split in words, not colour alone.


def test_the_phase_split_is_stated_in_words() -> None:
    app = _app()
    _button(app, "RUN FLASH").click().run()
    result = app.session_state["results"]["flash"]
    liquid = result.liquid_fraction
    vapor = result.vapor_fraction
    expected = f"Liquid {liquid:.6g} · Vapor {vapor:.6g} (mole fractions)"
    assert any(expected in item.value for item in app.caption)
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["Liquid fraction"] == f"{liquid:.6g}"
    assert metrics["Vapor fraction"] == f"{vapor:.6g}"


# Finding 7: the teaching labs are reachable from the app.


def test_learn_mode_links_every_teaching_lab() -> None:
    files = sorted(path.name for path in (ROOT / "docs" / "teaching").glob("LAB_*.md"))
    assert [name for _, name in LABS] == files
    for title, name in LABS:
        heading = (ROOT / "docs" / "teaching" / name).read_text(encoding="utf-8")
        assert heading.splitlines()[0] == f"# {title}"
        assert f"[{title}]({LAB_BASE_URL}{name})" in labs_markdown()
    app = _app()
    app.toggle(key="learn_mode").set_value(True).run()
    assert labs_markdown() in [item.value for item in app.markdown]
    assert re.match(
        r"https://github\.com/[\w-]+/[\w-]+/blob/master/docs/", LAB_BASE_URL
    )
