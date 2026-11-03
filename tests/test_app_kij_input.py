"""The optional kij input (owner-approved Option 2 of proposal P6).

* With every kij = 0 the app makes exactly the engine calls it made before (no
  ``binary_interactions``), so every result and export is identical.
* A non-zero kij reaches every engine call, and the app's numbers equal direct
  engine calls with the same ``binary_interactions``.
* The kij used is stated in the header badge, on result pages, in exports, in
  the HTML report and in case files; old case files load as kij = 0.
* The Validation page keeps the kij = 0 record.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from pvt_phase_simulator.eos.critical_point import (
    solve_mixture_critical_point,
)
from pvt_phase_simulator.eos.flash import calculate_two_phase_flash
from pvt_phase_simulator.eos.phase_envelope import (
    EnvelopeContinuationSettings,
    calculate_phase_envelope,
)
from pvt_phase_simulator.eos.saturation_pressure import (
    SaturationKind,
    calculate_saturation_pressure,
)
from pvt_phase_simulator_ui import app as ui_app
from pvt_phase_simulator_ui import views
from pvt_phase_simulator_ui.adapters import (
    KIJ_FITTED_C1_C2,
    KIJ_FITTED_C1_C3,
    KIJ_HELP,
    InputValidationError,
    ScientificInputs,
    validate_scientific_inputs,
)
from pvt_phase_simulator_ui.case_files import (
    CASE_SCHEMA_VERSION,
    CASE_SCHEMA_VERSION_WITH_KIJ,
    apply_case_to_state,
    case_from_state,
    load_case,
    serialize_case,
)
from pvt_phase_simulator_ui.exports import (
    build_export_document,
    build_sweep_export_document,
    export_csv_bytes,
    export_json_bytes,
)
from pvt_phase_simulator_ui.model_scope import load_model_scope
from pvt_phase_simulator_ui.reports import export_engineering_report_html
from pvt_phase_simulator_ui.state import initialize_session
from pvt_phase_simulator_ui.sweeps import run_sweep, validate_sweep_request

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "src" / "pvt_phase_simulator_ui" / "pages"
C1_C3 = {("Methane", "Propane"): 0.002, ("Propane", "Methane"): 0.002}
FIT = ROOT / "docs" / "investigations" / "kij_study_fit.json"


def _inputs(kij: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> ScientificInputs:
    return validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 5.0, kij=kij)


# --- the input boundary ---------------------------------------------------------


def test_kij_zero_passes_no_interactions_and_absent_pairs_are_ignored() -> None:
    zero = _inputs()
    assert zero.binary_interactions() is None
    assert zero.binary_interaction_assumption == "kij = 0"
    assert zero.model_metadata == "Peng-Robinson EOS; kij=0"
    # -0.0 and a kij for a pair absent from the mixture are both kij = 0.
    assert _inputs((-0.0, 0.0, 0.0)) == zero
    absent = _inputs((0.05, 0.0, 0.03))
    assert absent.effective_kij == (0.0, 0.0, 0.0)
    assert absent.binary_interactions() is None
    used = _inputs((0.0, 0.002, 0.0))
    assert used.binary_interactions() == C1_C3
    assert used.binary_interaction_assumption == "user-supplied kij: C1–C3 = +0.002"


@pytest.mark.parametrize("value", [-0.1001, 0.2001, float("nan"), float("inf")])
def test_kij_outside_the_range_is_rejected(value: float) -> None:
    with pytest.raises(InputValidationError, match="kij C1–C2"):
        validate_scientific_inputs((50.0, 50.0, 0.0), 250.0, 5.0, kij=(value, 0.0, 0.0))


def test_the_help_text_quotes_the_fitted_values_of_the_kij_study() -> None:
    fits = json.loads(FIT.read_text(encoding="utf-8"))["fits"]
    assert round(fits["ch4_c2"]["optimum"], 4) == KIJ_FITTED_C1_C2
    assert round(fits["ch4_c3"]["optimum"], 4) == KIJ_FITTED_C1_C3
    assert f"C1–C3 {KIJ_FITTED_C1_C3:+.4f}" in KIJ_HELP
    assert "C1–C2 0 (no gain over kij = 0)" in KIJ_HELP
    assert "one source" in KIJ_HELP and "non-predictive" in KIJ_HELP


# --- kij = 0 is byte-identical --------------------------------------------------


class _Recorder:
    """Stands in for an engine function and records the interactions it got."""

    def __init__(self) -> None:
        self.calls: list[object] = []

    def __call__(self, *args: object, **kwargs: object) -> object:
        # trace_pseudo_arclength_branch takes the mapping as its fifth argument.
        positional = args[4] if len(args) > 4 else None
        self.calls.append(kwargs.get("binary_interactions", positional))
        raise _Recorded


class _Recorded(ValueError):
    """Raised by a recorder; the extended overlay records it as a rejected start."""


def _engine_calls(
    monkeypatch: pytest.MonkeyPatch, inputs: ScientificInputs
) -> dict[str, list[object]]:
    """Run every app engine call site once with the engine replaced."""

    import pvt_phase_simulator_ui.envelope_extension as extension
    import pvt_phase_simulator_ui.sweeps as sweeps

    targets = {
        "flash": (ui_app, "calculate_two_phase_flash"),
        "sweep": (sweeps, "calculate_two_phase_flash"),
        "envelope": (views, "calculate_phase_envelope"),
        "saturation": (views, "calculate_saturation_pressure"),
        "critical": (views, "solve_mixture_critical_point"),
        "map": (views, "scan_mixture_criticality"),
        "extended": (extension, "trace_pseudo_arclength_branch"),
    }
    recorders = {name: _Recorder() for name in targets}
    for name, (module, attribute) in targets.items():
        monkeypatch.setattr(module, attribute, recorders[name])
    calls = (
        ("flash", lambda: ui_app._cached_flash.__wrapped__(inputs)),
        ("envelope", lambda: views._calculate_envelope.__wrapped__(inputs)),
        (
            "saturation",
            lambda: views._calculate_operating_saturation.__wrapped__(inputs),
        ),
        ("critical", lambda: views._calculate_critical.__wrapped__(inputs)),
        ("map", lambda: views._calculate_scan.__wrapped__(inputs)),
    )
    for _, call in calls:
        with pytest.raises(_Recorded):
            call()
    # The extended overlay and the sweep record failures instead of raising.
    views._calculate_extended_envelope.__wrapped__(inputs)
    request = validate_sweep_request(
        "pressure",
        inputs.composition_mol_percent,
        fixed_value=inputs.temperature_k,
        start=4.0,
        end=5.0,
        points=2,
        kij=inputs.kij,
    )
    run_sweep(request)
    return {name: recorder.calls for name, recorder in recorders.items()}


def test_with_kij_zero_every_app_engine_call_passes_no_interactions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """kij = 0 makes exactly the engine calls of the app without the input."""

    calls = _engine_calls(monkeypatch, _inputs())
    assert all(calls.values()), calls
    for name, received in calls.items():
        assert all(item is None for item in received), (name, received)


def test_a_nonzero_kij_reaches_every_app_engine_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _engine_calls(monkeypatch, _inputs((0.0, 0.002, 0.0)))
    assert all(calls.values()), calls
    for name, received in calls.items():
        assert all(item == C1_C3 for item in received), (name, received)


def test_with_kij_zero_exports_are_byte_identical_to_inputs_without_kij() -> None:
    legacy = ScientificInputs((50.0, 0.0, 50.0), (0.5, 0.0, 0.5), 300.0, 5.0e6)
    assert legacy == _inputs()
    flash = calculate_two_phase_flash(legacy.mixture(), 300.0, 5.0e6)
    for inputs in (legacy, _inputs()):
        document = build_export_document(inputs, flash_result=flash)
        assert document["metadata"]["binary_interaction_assumption"] == "kij = 0"  # type: ignore[index]
        assert "binary_interaction_parameters" not in document["metadata"]  # type: ignore[operator]
    reference = build_export_document(legacy, flash_result=flash)
    current = build_export_document(_inputs(), flash_result=flash)
    assert export_json_bytes(current) == export_json_bytes(reference)
    assert export_csv_bytes(current) == export_csv_bytes(reference)


def test_with_kij_zero_the_app_pages_hold_the_same_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Overview, Phase Envelope and Critical Point at the default case."""

    short = EnvelopeContinuationSettings(
        target_temperature_k=305.0, initial_temperature_step_k=5.0, maximum_points=2
    )

    def short_envelope(inputs: ScientificInputs) -> object:
        return calculate_phase_envelope(
            inputs.mixture(),
            short,
            short,
            295.0,
            295.0,
            binary_interactions=inputs.binary_interactions(),
        )

    monkeypatch.setattr(views, "_calculate_envelope", short_envelope)
    monkeypatch.setattr(views, "_calculate_extended_envelope", lambda _inputs: None)
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=120).run()
    next(b for b in app.button if b.label == "RUN FLASH").click().run()
    app.switch_page(PAGES / "phase_envelope.py").run()
    next(b for b in app.button if b.label == "RUN PHASE ENVELOPE").click().run()
    app.switch_page(PAGES / "critical_point.py").run()
    next(b for b in app.button if b.label == "RUN CRITICAL SOLVER").click().run()
    assert not app.exception
    results = app.session_state["results"]
    mixture = _inputs().mixture()
    assert results["flash"] == calculate_two_phase_flash(mixture, 300.0, 5.0e6)
    assert results["envelope"] == calculate_phase_envelope(
        mixture, short, short, 295.0, 295.0
    )
    assert results["saturation"][0] == calculate_saturation_pressure(
        mixture, 300.0, SaturationKind.BUBBLE_POINT
    )
    assert results["critical"] == solve_mixture_critical_point(
        mixture, 300.0, 5.0e6, initialization_source="streamlit_user_conditions"
    )
    assert not [item for item in app.warning if "user-supplied kij" in item.value]
    assert "Peng-Robinson EOS - 3 verified components - kij = 0" in [
        item.value for item in app.caption
    ]


def test_with_kij_zero_a_sweep_is_unchanged() -> None:
    request = validate_sweep_request(
        "pressure", (50.0, 0.0, 50.0), fixed_value=300.0, start=1.0, end=8.0, points=3
    )
    for point, pressure in zip(run_sweep(request).points, (1.0, 4.5, 8.0), strict=True):
        flash = calculate_two_phase_flash(_inputs().mixture(), 300.0, pressure * 1e6)
        assert point.vapor_fraction == flash.vapor_fraction


# --- a non-zero kij reaches the engine ------------------------------------------


def _submit_kij_case(app: AppTest, kij: float) -> AppTest:
    """Enter CH4+C3 50/50 with a C1–C3 kij and submit it."""

    field = next(item for item in app.number_input if item.label == "kij C1–C3")
    field.set_value(kij)
    next(b for b in app.button if b.label == "RUN FLASH").click().run()
    return app


def test_the_app_bubble_pressure_at_kij_0_002_equals_a_direct_engine_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        views,
        "_calculate_envelope",
        lambda inputs: calculate_phase_envelope(
            inputs.mixture(),
            EnvelopeContinuationSettings(
                target_temperature_k=305.0,
                initial_temperature_step_k=5.0,
                maximum_points=2,
            ),
            EnvelopeContinuationSettings(
                target_temperature_k=305.0,
                initial_temperature_step_k=5.0,
                maximum_points=2,
            ),
            295.0,
            295.0,
            binary_interactions=inputs.binary_interactions(),
        ),
    )
    monkeypatch.setattr(views, "_calculate_extended_envelope", lambda _inputs: None)
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=120).run()
    _submit_kij_case(app, 0.002)
    submitted = app.session_state["submitted_inputs"]
    assert submitted.kij == (0.0, 0.002, 0.0)
    app.switch_page(PAGES / "phase_envelope.py").run()
    next(b for b in app.button if b.label == "RUN PHASE ENVELOPE").click().run()
    assert not app.exception
    bubble = app.session_state["results"]["saturation"][0]
    direct = calculate_saturation_pressure(
        _inputs().mixture(),
        300.0,
        SaturationKind.BUBBLE_POINT,
        binary_interactions=C1_C3,
    )
    assert bubble.pressure_pa == direct.pressure_pa
    assert (
        bubble.pressure_pa
        != calculate_saturation_pressure(
            _inputs().mixture(), 300.0, SaturationKind.BUBBLE_POINT
        ).pressure_pa
    )
    notes = [item.value for item in app.warning]
    assert any("user-supplied kij: C1–C3 = +0.002" in note for note in notes)


def test_the_badge_and_caption_state_the_kij_and_validation_keeps_kij_zero() -> None:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=120).run()
    expander = next(
        item
        for item in app.expander
        if item.label == "Advanced: binary interaction (kij)"
    )
    assert expander.proto.expanded is False
    labels = {item.label: item for item in app.number_input}
    # The default case is methane/propane: only C1–C3 can be set.
    assert labels["kij C1–C3"].value == 0.0
    assert not labels["kij C1–C3"].disabled
    assert labels["kij C1–C2 (not in mixture)"].disabled
    assert labels["kij C2–C3 (not in mixture)"].disabled
    assert not [item for item in app.markdown if "user-supplied kij" in item.value]
    assert any(
        "No fitted interaction parameters are used." in item.value
        for item in app.markdown
    )

    _submit_kij_case(app, 0.002)
    assert any("user-supplied kij" in item.value for item in app.markdown)
    assert (
        "Peng-Robinson EOS - 3 verified components - user-supplied kij: "
        "C1–C3 = +0.002" in [item.value for item in app.caption]
    )
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["Interactions"] == "user-supplied kij"
    # The model panel must not claim that no fitted interactions are used.
    model = next(item.value for item in app.markdown if "**Model.**" in item.value)
    assert "No fitted interaction parameters are used." not in model
    assert "user-supplied kij: C1–C3 = +0.002" in model

    app.switch_page(PAGES / "validation.py").run()
    assert not app.exception
    assert any(
        "always shows the kij = 0 validation record" in item.value
        for item in app.warning
    )


# --- exports, report and case files ---------------------------------------------


def test_exports_and_the_report_state_the_kij_actually_used() -> None:
    inputs = _inputs((0.0, 0.002, 0.0))
    flash = calculate_two_phase_flash(
        inputs.mixture(), 300.0, 5.0e6, binary_interactions=C1_C3
    )
    document = build_export_document(inputs, flash_result=flash)
    metadata = document["metadata"]
    assert metadata["binary_interaction_assumption"] == (  # type: ignore[index]
        "user-supplied kij: C1–C3 = +0.002"
    )
    assert metadata["binary_interaction_parameters"] == {"C1–C3": 0.002}  # type: ignore[index]
    assert document["case"]["binary_interaction_assumption"] == (  # type: ignore[index]
        "user-supplied kij: C1–C3 = +0.002"
    )
    html = export_engineering_report_html(
        document, scope=load_model_scope(ROOT), application_version="test"
    ).decode()
    assert "user-supplied kij: C1–C3 = +0.002" in html
    assert "non-predictive" in html

    request = validate_sweep_request(
        "pressure",
        (50.0, 0.0, 50.0),
        fixed_value=300.0,
        start=4.0,
        end=5.0,
        points=2,
        kij=(0.0, 0.002, 0.0),
    )
    sweep = build_sweep_export_document(run_sweep(request))
    assert sweep["metadata"]["binary_interaction_assumption"] == (  # type: ignore[index]
        "user-supplied kij: C1–C3 = +0.002"
    )


def _state(kij: tuple[float, float, float]) -> dict[str, object]:
    state: dict[str, object] = {}
    initialize_session(state)
    state.update(dict(zip(("kij_c1_c2", "kij_c1_c3", "kij_c2_c3"), kij, strict=True)))
    return state


def test_case_files_round_trip_kij_and_kij_zero_files_are_unchanged() -> None:
    zero = serialize_case(case_from_state(_state((0.0, 0.0, 0.0))))
    document = json.loads(zero)
    assert document["schema_version"] == CASE_SCHEMA_VERSION
    assert "binary_interactions" not in document["inputs"]

    payload = serialize_case(case_from_state(_state((0.0, 0.002, 0.0))))
    saved = json.loads(payload)
    assert saved["schema_version"] == CASE_SCHEMA_VERSION_WITH_KIJ
    assert saved["inputs"]["binary_interactions"] == {
        "ethane_propane": 0.0,
        "methane_ethane": 0.0,
        "methane_propane": 0.002,
    }
    loaded = load_case(payload)
    assert loaded.inputs.kij == (0.0, 0.002, 0.0)
    assert serialize_case(loaded) == payload
    restored: dict[str, object] = {}
    initialize_session(restored)
    apply_case_to_state(loaded, restored)
    assert restored["kij_c1_c3"] == 0.002


def test_an_old_case_file_without_kij_loads_as_kij_zero() -> None:
    old = serialize_case(case_from_state(_state((0.0, 0.0, 0.0))))
    loaded = load_case(old)
    assert loaded.inputs.kij == (0.0, 0.0, 0.0)
    state = _state((0.0, 0.05, 0.0))
    apply_case_to_state(loaded, state)
    assert (state["kij_c1_c2"], state["kij_c1_c3"], state["kij_c2_c3"]) == (
        0.0,
        0.0,
        0.0,
    )
