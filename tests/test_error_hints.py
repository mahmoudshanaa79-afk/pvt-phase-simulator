"""Error messages say how to fix the problem, not only what is wrong.

Health check 2026-11 (docs/investigations/health_check_2026_11.md): a refused
case file and an all-zero composition named the problem but gave no next step.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from pvt_phase_simulator_ui import app as ui_app
from pvt_phase_simulator_ui.adapters import (
    InputValidationError,
    validate_scientific_inputs,
)

ROOT = Path(__file__).resolve().parents[1]


def _load(payload: bytes, name: str) -> AppTest:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=60).run()
    app.file_uploader[0].set_value((name, payload, "application/json")).run()
    next(item for item in app.button if item.label == "Load case").click().run()
    assert not app.exception
    return app


@pytest.mark.parametrize(
    ("payload", "reason"),
    (
        (b"not json at all", "Case file is not valid JSON."),
        (b"[1, 2, 3]", "root must be an object."),
        (b'{"schema_version": "0.9.0"}', "root is missing schema."),
    ),
)
def test_a_refused_case_file_says_how_to_get_a_valid_one(
    payload: bytes, reason: str
) -> None:
    app = _load(payload, "broken.json")
    shown = [item.value for item in app.error if "Case load unavailable" in item.value]
    assert len(shown) == 1
    assert reason in shown[0]
    assert ui_app.CASE_LOAD_HINT in shown[0]
    assert "Save case" in ui_app.CASE_LOAD_HINT


def test_an_all_zero_composition_says_what_to_enter() -> None:
    with pytest.raises(InputValidationError) as refused:
        validate_scientific_inputs((0.0, 0.0, 0.0), 300.0, 5.0)
    message = str(refused.value)
    assert message.startswith("Composition total must be greater than zero.")
    assert "Enter a positive mol % for at least one component" in message
