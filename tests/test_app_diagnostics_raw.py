"""The Diagnostics "raw public objects" switch never freezes the page.

The raw phase envelope is about 40 MB of JSON. Drawn as a JSON tree it froze
the browser tab, so the page shows a summary and offers the full object as a
download built only when clicked. Nothing about the numbers changes: the
download is the same ``asdict`` of the same result.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from pvt_phase_simulator.eos.phase_envelope import (
    EnvelopeContinuationSettings,
    calculate_phase_envelope,
)
from pvt_phase_simulator_ui import views
from pvt_phase_simulator_ui.adapters import ScientificInputs

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "src" / "pvt_phase_simulator_ui" / "pages"
#: Anything drawn inline must stay small enough for a browser to render.
INLINE_LIMIT_BYTES = 1_000_000


def _app() -> AppTest:
    return AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=300).run()


def _button(app: AppTest, label: str) -> Any:
    return next(item for item in app.button if item.label == label)


def test_with_nothing_run_the_switch_turns_on_and_off_and_the_app_responds() -> None:
    app = _app()
    app.toggle(key="learn_mode").set_value(True).run()
    app.switch_page(PAGES / "diagnostics.py").run()
    assert "Run a calculation to populate diagnostics." in [i.value for i in app.info]
    for value in (True, False, True, False):
        app.toggle(key="diagnostics_raw").set_value(value).run()
        assert not app.exception
        assert not app.json
    # Everything still works afterwards.
    app.switch_page(PAGES / "overview.py").run()
    _button(app, "RUN FLASH").click().run()
    assert not app.exception
    assert "flash" in app.session_state["results"]


def _short_envelope(inputs: ScientificInputs) -> object:
    settings = EnvelopeContinuationSettings(
        target_temperature_k=inputs.temperature_k,
        initial_temperature_step_k=5.0,
        maximum_points=3,
    )
    start = inputs.temperature_k - 15.0
    return calculate_phase_envelope(inputs.mixture(), settings, settings, start, start)


def test_with_an_envelope_the_page_shows_a_summary_and_a_lazy_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(views, "_calculate_envelope", _short_envelope)
    monkeypatch.setattr(views, "_calculate_extended_envelope", lambda _inputs: None)
    monkeypatch.setattr(views, "_calculate_operating_saturation", lambda _inputs: None)
    downloads: dict[str, Any] = {}
    original = st.download_button

    def capture(label: str, *args: Any, **kwargs: Any) -> Any:
        downloads[label] = kwargs.get("data")
        return original(label, *args, **kwargs)

    monkeypatch.setattr(st, "download_button", capture)
    app = _app()
    _button(app, "RUN FLASH").click().run()
    app.switch_page(PAGES / "phase_envelope.py").run()
    _button(app, "RUN PHASE ENVELOPE").click().run()
    app.switch_page(PAGES / "diagnostics.py").run()
    app.toggle(key="diagnostics_raw").set_value(True).run()
    assert not app.exception

    result = app.session_state["results"]["envelope"]
    drawn = [
        item.value if isinstance(item.value, str) else json.dumps(item.value)
        for item in app.json
    ]
    assert drawn and all(len(text) < INLINE_LIMIT_BYTES for text in drawn)
    summary = views.envelope_summary(result)
    assert summary["bubble_branch"]["accepted_points"] == len(
        result.bubble_branch.points
    )
    assert summary["dew_branch"]["rejected_attempts"] == len(
        result.dew_branch.rejected_attempts
    )
    assert summary["bubble_branch"]["termination_reason"] == (
        result.bubble_branch.termination_reason.value
    )
    assert any(json.loads(text) == summary for text in drawn)

    # The full object is built only when the download is clicked.
    lazy = downloads["Download raw envelope (JSON)"]
    assert callable(lazy)
    full = lazy()
    assert full == json.dumps(asdict(result), default=str).encode("utf-8")
    assert json.loads(full)["bubble_branch"]["termination_message"] == (
        result.bubble_branch.termination_message
    )

    app.toggle(key="diagnostics_raw").set_value(False).run()
    assert not app.exception and not app.json
