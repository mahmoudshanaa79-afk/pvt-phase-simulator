"""Non-converged and inconclusive engine answers reach the pages in plain words.

Real flash and real operating-temperature saturation solves for one state per
solver code. The phase envelope is the engine's own envelope of the same
mixture, traced for two points only, and the display-only extended overlay is
skipped: neither is under test here, and the full trace takes minutes. Every
action with the full envelope is covered in ``test_app_robustness_actions.py``.
"""

from __future__ import annotations

import logging

import pytest

from pvt_phase_simulator.eos.phase_envelope import (
    EnvelopeContinuationSettings,
    calculate_phase_envelope,
)
from pvt_phase_simulator_ui import views
from pvt_phase_simulator_ui.adapters import ScientificInputs
from pvt_phase_simulator_ui.solver_codes import (
    BOUNDARY,
    EXPLANATIONS,
    HIDDEN,
    MULTIPLE,
    UNBRACKETED,
)
from tests._robustness import (
    app_errors,
    assert_clean,
    button,
    go,
    new_app,
    run_flash,
    set_inputs,
)

__all__ = ["app_errors"]  # the fixture is used by name

Errors = list[logging.LogRecord]
TEXT = {group: text for group, text in EXPLANATIONS}

#: (composition, temperature K, direction, code group, expected status).
SOLVER_STATES = {
    "boundary": ((50.0, 50.0, 0.0), 250.0, "bubble", (BOUNDARY,), "Converged"),
    "unbracketed": (
        (50.0, 50.0, 0.0),
        260.0,
        "bubble",
        (UNBRACKETED,),
        "Inconclusive",
    ),
    "hidden": ((71.23, 28.77, 0.0), 243.6, "dew", (HIDDEN, MULTIPLE), "Inconclusive"),
}


def _short_envelope(inputs: ScientificInputs) -> object:
    settings = EnvelopeContinuationSettings(
        target_temperature_k=inputs.temperature_k,
        initial_temperature_step_k=5.0,
        maximum_points=2,
    )
    start = inputs.temperature_k - 10.0
    return calculate_phase_envelope(inputs.mixture(), settings, settings, start, start)


@pytest.mark.parametrize("name", SOLVER_STATES)
def test_solver_outcomes_reach_every_page_in_plain_language(
    name: str, app_errors: Errors, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(views, "_calculate_envelope", _short_envelope)
    monkeypatch.setattr(views, "_calculate_extended_envelope", lambda _inputs: None)
    composition, temperature, direction, group, status = SOLVER_STATES[name]
    app = new_app(timeout=600)
    set_inputs(app, composition=composition, temperature=temperature)
    run_flash(app)
    go(app, "phase_envelope.py")
    button(app, "RUN PHASE ENVELOPE").click().run()
    assert_clean(app, app_errors, name)

    label = " + ".join(group)
    assert f"`{label}` — {TEXT[group]}" in [item.value for item in app.markdown]
    rows = next(
        frame.value
        for frame in app.dataframe
        if "Bubble pressure" in list(frame.value["Field"])
    ).set_index("Field")
    row = rows.loc[f"{direction.capitalize()} pressure"]
    assert row["Units / meaning"].startswith(status)
    for code in group:
        assert code in row["Units / meaning"]
    if status == "Inconclusive":
        assert row["Value"] == "No pressure reported (Inconclusive)"

    go(app, "diagnostics.py")
    assert_clean(app, app_errors, f"{name}: diagnostics")
    table = next(
        frame.value
        for frame in app.dataframe
        if "Plain language" in frame.value.columns
        and "Direction" in frame.value.columns
    ).set_index("Direction")
    assert TEXT[group] in table.loc[direction, "Plain language"]

    go(app, "overview.py")
    assert_clean(app, app_errors, f"{name}: overview and exports")
