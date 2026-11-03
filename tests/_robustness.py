"""Shared harness for the application robustness tests.

A scenario passes only when the app shows no raw exception, no generic
"unexpected error" message from a safe boundary, and logs no error from the
application package. A crash hidden behind a generic message is still a crash.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from pvt_phase_simulator_ui import app as ui_app
from pvt_phase_simulator_ui import views

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "streamlit_app.py"
PAGES = ROOT / "src" / "pvt_phase_simulator_ui" / "pages"
PAGE_FILES = (
    "overview.py",
    "phase_envelope.py",
    "critical_point.py",
    "engineering_sweeps.py",
    "validation.py",
    "diagnostics.py",
)
COMPOSITION_KEYS = ("methane_pct", "ethane_pct", "propane_pct")
KIJ_KEYS = ("kij_c1_c2", "kij_c1_c3", "kij_c2_c3")

#: Every message a safe boundary shows instead of a traceback.
GENERIC_FAILURES = (
    ui_app.PAGE_RENDER_FAILURE,
    ui_app.INPUT_PANEL_FAILURE,
    ui_app.FLASH_ACTION_FAILURE,
    ui_app.CASE_LOAD_FAILURE,
    ui_app.CASE_SAVE_FAILURE,
    views.ENVELOPE_ACTION_FAILURE,
    views.EXTENSION_ACTION_FAILURE,
    views.SATURATION_ACTION_FAILURE,
    views.CRITICAL_ACTION_FAILURE,
    views.CRITICAL_SCAN_ACTION_FAILURE,
    views.SWEEP_ACTION_FAILURE,
)


class _Collector(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def app_errors() -> Iterator[list[logging.LogRecord]]:
    """Errors logged by the application package while the test runs."""

    collector = _Collector()
    logger = logging.getLogger("pvt_phase_simulator_ui")
    logger.addHandler(collector)
    try:
        yield collector.records
    finally:
        logger.removeHandler(collector)


def new_app(timeout: float = 300) -> AppTest:
    return AppTest.from_file(ENTRY, default_timeout=timeout).run()


def messages(app: AppTest) -> list[str]:
    return [item.value for item in (*app.error, *app.warning, *app.info)]


def assert_clean(app: AppTest, errors: list[logging.LogRecord], where: str) -> None:
    """No traceback, no generic safe-boundary message, no logged app error."""

    assert not app.exception, (where, [item.value for item in app.exception])
    shown = messages(app)
    hidden = [text for text in shown for generic in GENERIC_FAILURES if generic in text]
    assert not hidden, (where, hidden)
    logged = [
        f"{record.getMessage()}: {record.exc_info[1]!r}"
        if record.exc_info
        else record.getMessage()
        for record in errors
    ]
    assert not logged, (where, logged)


def button(app: AppTest, label: str) -> Any:
    return next(item for item in app.button if item.label == label)


def set_inputs(
    app: AppTest,
    composition: tuple[float, float, float] | None = None,
    temperature: float | None = None,
    pressure: float | None = None,
    kij: tuple[float, float, float] | None = None,
) -> None:
    if composition is not None:
        for key, value in zip(COMPOSITION_KEYS, composition, strict=True):
            app.number_input(key=key).set_value(value)
    if temperature is not None:
        app.number_input(key="temperature_value").set_value(temperature)
    if pressure is not None:
        app.number_input(key="pressure_value").set_value(pressure)
    if kij is not None:
        # The kij fields follow the submitted composition, so submit it first
        # to enable the pairs that are present before setting them.
        button(app, "RUN FLASH").click().run()
        for key, value in zip(KIJ_KEYS, kij, strict=True):
            field = app.number_input(key=key)
            if not field.disabled:
                field.set_value(value)


def run_flash(app: AppTest) -> AppTest:
    return button(app, "RUN FLASH").click().run()


def go(app: AppTest, page: str) -> AppTest:
    return app.switch_page(PAGES / page).run()


def has_result(app: AppTest, name: str) -> bool:
    return name in app.session_state["results"]


def submission_error(app: AppTest) -> str:
    return next(
        item.value for item in app.error if "Submission unavailable" in item.value
    )


#: (page, button label, stored result name) for every calculation action.
ACTIONS = (
    ("phase_envelope.py", "RUN PHASE ENVELOPE", "envelope"),
    ("critical_point.py", "RUN CRITICAL SOLVER", "critical"),
    ("critical_point.py", "RUN CRITICALITY MAP", "critical_scan"),
    ("engineering_sweeps.py", "RUN SWEEP", "sweep"),
)


def run_every_action(app: AppTest, errors: list[logging.LogRecord], where: str) -> None:
    """Click every RUN button on every page, then revisit every page.

    Overview rebuilds every export and the HTML report from the stored results,
    so it is revisited after each action: a failing export shows up as well.
    """

    for page, label, name in ACTIONS:
        go(app, page)
        button(app, label).click().run()
        assert_clean(app, errors, f"{where}: {label}")
        assert has_result(app, name), (where, label)
        go(app, "overview.py")
        assert_clean(app, errors, f"{where}: exports after {label}")
    go(app, "phase_envelope.py")
    button(app, "SHOW PHASE COMPOSITIONS").click().run()
    assert_clean(app, errors, f"{where}: phase compositions")
    go(app, "validation.py")
    button(app, "GENERATE VALIDATION FIGURES").click().run()
    assert_clean(app, errors, f"{where}: validation figures")
    for page in PAGE_FILES:
        go(app, page)
        assert_clean(app, errors, f"{where}: {page}")
