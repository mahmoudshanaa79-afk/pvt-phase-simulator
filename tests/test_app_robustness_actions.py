"""Every RUN action on every page, with real engine results, never crashes.

The default example runs every action with the production engine, and the
failure paths (interrupted runs, engine rejections, defects) show readable
messages. The other examples are in ``test_app_robustness_examples.py`` and the
solver outcomes in ``test_app_robustness_solver_states.py``, so the parallel CI
run can spread them. See ``tests/_robustness.py`` for what "clean" means.
"""

from __future__ import annotations

import logging

import pytest
from streamlit.runtime.scriptrunner_utils.exceptions import StopException

from pvt_phase_simulator_ui import views
from pvt_phase_simulator_ui.state import INPUT_EXAMPLES
from tests._robustness import (
    app_errors,
    assert_clean,
    button,
    go,
    has_result,
    new_app,
    run_every_action,
    run_flash,
    set_inputs,
)

__all__ = ["app_errors"]  # the fixture is used by name

Errors = list[logging.LogRecord]


def test_every_action_with_the_default_example(app_errors: Errors) -> None:
    example = INPUT_EXAMPLES[0].label
    app = new_app(timeout=600)
    app.selectbox(key="input_example").set_value(example).run()
    run_flash(app)
    assert_clean(app, app_errors, f"{example}: flash")
    assert has_result(app, "flash")
    run_every_action(app, app_errors, example)

    # Running the same action again reuses the bounded cache: same answer.
    first = app.session_state["results"]["envelope"]
    go(app, "phase_envelope.py")
    button(app, "RUN PHASE ENVELOPE").click().run()
    assert_clean(app, app_errors, f"{example}: second envelope run")
    assert app.session_state["results"]["envelope"] == first


def test_an_interrupted_action_leaves_no_result_and_no_error(
    app_errors: Errors, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Switching page mid-run interrupts the script with a control exception."""

    app = new_app()
    run_flash(app)

    def interrupted(_inputs: object) -> object:
        raise StopException()

    monkeypatch.setattr(views, "_calculate_envelope", interrupted)
    go(app, "phase_envelope.py")
    button(app, "RUN PHASE ENVELOPE").click().run()
    monkeypatch.undo()
    go(app, "critical_point.py")
    go(app, "phase_envelope.py")
    assert_clean(app, app_errors, "after an interrupted envelope")
    assert not has_result(app, "envelope")
    assert any(
        item.value.startswith("No calculated envelope is available.")
        for item in app.info
    )


def test_an_engine_rejection_shows_the_engine_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Should the engine still raise, the user reads its reason, not just a
    generic message; the earlier result is not kept."""

    app = new_app()
    run_flash(app)

    def rejected(_inputs: object) -> object:
        raise ValueError("fugacity coefficient must be finite.")

    monkeypatch.setattr(views, "_calculate_critical", rejected)
    go(app, "critical_point.py")
    button(app, "RUN CRITICAL SOLVER").click().run()
    assert not app.exception
    assert not has_result(app, "critical")
    assert any(
        views.CRITICAL_ACTION_FAILURE in item.value
        and "Engine reason: fugacity coefficient must be finite." in item.value
        for item in app.error
    )


def test_an_application_defect_stays_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = new_app()
    run_flash(app)

    def defect(_inputs: object) -> object:
        raise KeyError("internal detail")

    monkeypatch.setattr(views, "_calculate_critical", defect)
    go(app, "critical_point.py")
    button(app, "RUN CRITICAL SOLVER").click().run()
    assert not app.exception
    shown = [item.value for item in app.error]
    assert views.CRITICAL_ACTION_FAILURE in shown
    assert not any("internal detail" in text for text in shown)


def test_a_failed_critical_solve_shows_the_engine_status(app_errors: Errors) -> None:
    """At 250 K the default mixture's critical solve does not converge."""

    app = new_app()
    set_inputs(app, temperature=250.0)
    run_flash(app)
    go(app, "critical_point.py")
    button(app, "RUN CRITICAL SOLVER").click().run()
    assert_clean(app, app_errors, "critical")
    result = app.session_state["results"]["critical"]
    assert result.status.value != "converged"
    shown = " ".join(
        [str(frame.value.to_dict()) for frame in app.dataframe]
        + [item.value for item in (*app.error, *app.warning, *app.info, *app.markdown)]
    )
    readable = result.status.value.replace("_", " ")
    assert readable.lower() in shown.lower()
