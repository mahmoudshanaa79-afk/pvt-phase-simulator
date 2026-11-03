"""Every RUN action with the other shipped examples and with a kij at its edge.

Production engine throughout; see ``tests/_robustness.py`` for what "clean"
means. The default example is in ``test_app_robustness_actions.py``.
"""

from __future__ import annotations

import logging

import pytest

from pvt_phase_simulator_ui.state import INPUT_EXAMPLES
from tests._robustness import (
    app_errors,
    assert_clean,
    has_result,
    new_app,
    run_every_action,
    run_flash,
    set_inputs,
)

__all__ = ["app_errors"]  # the fixture is used by name

Errors = list[logging.LogRecord]


@pytest.mark.parametrize("example", [item.label for item in INPUT_EXAMPLES[1:]])
def test_every_action_with_the_other_shipped_examples(
    example: str, app_errors: Errors
) -> None:
    app = new_app(timeout=600)
    app.selectbox(key="input_example").set_value(example).run()
    run_flash(app)
    assert_clean(app, app_errors, f"{example}: flash")
    assert has_result(app, "flash")
    run_every_action(app, app_errors, example)


def test_every_action_with_a_user_kij_at_its_upper_edge(app_errors: Errors) -> None:
    app = new_app(timeout=600)
    set_inputs(app, composition=(50.0, 0.0, 50.0), kij=(0.0, 0.2, 0.0))
    run_flash(app)
    assert app.session_state["submitted_inputs"].kij == (0.0, 0.2, 0.0)
    run_every_action(app, app_errors, "kij C1–C3 = 0.2")
