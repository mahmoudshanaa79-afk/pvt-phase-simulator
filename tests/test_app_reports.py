"""Truthfulness and integration tests for the printable engineering report."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pvt_phase_simulator.eos.critical_point import (
    CriticalPointStatus,
    solve_mixture_critical_point,
)
from pvt_phase_simulator.eos.flash import FlashConvergenceStatus
from pvt_phase_simulator_ui.adapters import (
    run_validated_flash,
    validate_scientific_inputs,
)
from pvt_phase_simulator_ui.exports import (
    build_export_document,
    export_csv_bytes,
    export_json_bytes,
)
from pvt_phase_simulator_ui.model_scope import load_model_scope
from pvt_phase_simulator_ui.reports import export_engineering_report_html
from pvt_phase_simulator_ui.units import (
    PressureUnit,
    TemperatureUnit,
    UnitPreferences,
)

ROOT = Path(__file__).resolve().parents[1]
GENERATED_AT = datetime(2026, 9, 8, 12, 30, tzinfo=UTC)


def _report_text(document: dict[str, object], **kwargs: object) -> str:
    return export_engineering_report_html(
        document,
        scope=load_model_scope(ROOT),
        generated_at=GENERATED_AT,
        application_version="0.1.0-test",
        **kwargs,  # type: ignore[arg-type]
    ).decode("utf-8")


def test_report_renders_a_real_already_computed_case() -> None:
    inputs, result = run_validated_flash((50.0, 0.0, 50.0), 300.0, 5.0)
    assert result.convergence_status is FlashConvergenceStatus.CONVERGED

    text = _report_text(build_export_document(inputs, flash_result=result))

    assert text.startswith("<!doctype html>")
    assert "Engineering case report" in text
    assert "Current submitted case" in text
    assert "2026-09-08T12:30:00Z UTC" in text
    assert "Usable two-phase flash result" in text
    assert ">CONVERGED<" in text
    assert "Phase-stability status" in text
    assert "Liquid fraction" in text
    assert "Vapor fraction" in text
    assert "Source-provided phase compositions" in text
    assert all(name in text for name in ("Methane", "Ethane", "Propane"))
    assert "10.1021/acs.jced.5c00110" in text
    assert "docs/validation/module17_vle_validation.csv" in text


def test_unavailable_sections_and_fields_are_never_blank() -> None:
    inputs = validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 20.0)

    text = _report_text(build_export_document(inputs))

    assert "The flash calculation has not been run." in text
    assert "The phase-envelope calculation has not been run." in text
    assert "The production critical-point solve has not been run." in text
    assert "No engineering sweep has been calculated for this case." in text
    assert text.count(">UNAVAILABLE<") >= 20
    assert "<td></td>" not in text
    assert "<th></th>" not in text


def test_failed_flash_fields_are_labelled_failed_and_source_values_are_hidden() -> None:
    inputs, result = run_validated_flash((50.0, 0.0, 50.0), 300.0, 5.0)
    failed = replace(
        result,
        convergence_status=FlashConvergenceStatus.FAILED,
        failure_reason="STRUCTURED_TEST_FAILURE",
    )
    assert result.vapor_fraction is not None

    text = _report_text(build_export_document(inputs, flash_result=failed))

    assert "STRUCTURED_TEST_FAILURE" in text
    assert re.search(
        r"Vapor fraction</th><td><span class=\"status failed\">FAILED</span>",
        text,
    )
    assert re.search(
        r"Liquid Z</th><td><span class=\"status failed\">FAILED</span>", text
    )
    assert f"{result.vapor_fraction:.12g}" not in text


def test_uncertified_critical_values_are_reported_failed_not_as_results() -> None:
    inputs = validate_scientific_inputs((50.0, 0.0, 50.0), 320.0, 8.5)
    document = build_export_document(inputs)
    results = document["results"]
    assert isinstance(results, dict)
    results["critical_point"] = {
        "calculation_status": "calculated",
        "solver_status": "line_search_failed",
        "certified": False,
        "termination_reason": "LINE_SEARCH_FAILED",
        "iteration_count": 7,
        "temperature": {"status": "available", "value": 12345.67890123},
        "temperature_unit": "K",
        "pressure": {"status": "available", "value": 98765.43210987},
        "pressure_unit": "Pa",
        "temperature_k": {"status": "available", "value": 12345.67890123},
        "pressure_pa": {"status": "available", "value": 98765.43210987},
        "lambda_min": {"status": "available", "value": 0.0},
        "cubic_coefficient": {"status": "available", "value": 0.0},
        "scaled_residual_norm": {"status": "available", "value": 0.0},
        "critical_direction": {"status": "available", "value": (1.0, 0.0)},
    }

    text = _report_text(document)

    assert "CriticalPointStatus.CONVERGED is absent" in text
    assert re.search(
        r"Critical temperature</th><td><span class=\"status failed\">FAILED</span>",
        text,
    )
    assert "12345.6789012" not in text
    assert "98765.4321099" not in text


def test_converged_envelope_points_render_and_failed_branch_stays_failed() -> None:
    inputs = validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 5.0)
    document = build_export_document(inputs)
    results = document["results"]
    assert isinstance(results, dict)
    results["phase_envelope"] = {
        "calculation_status": "calculated",
        "bubble_branch": {
            "branch_kind": "bubble",
            "termination_status": "target_reached",
            "termination_message": "Bubble target reached.",
            "accepted_point_count": 1,
            "rejected_attempt_count": 0,
            "points": [
                {
                    "status": "converged",
                    "temperature": 300.25,
                    "temperature_unit": "K",
                    "pressure": 5.75,
                    "pressure_unit": "MPa",
                    "parent_composition": (0.5, 0.0, 0.5),
                    "incipient_composition": (0.8, 0.0, 0.2),
                }
            ],
        },
        "dew_branch": {
            "branch_kind": "dew",
            "termination_status": "corrector_failed",
            "termination_message": "Dew corrector stopped safely.",
            "accepted_point_count": 0,
            "rejected_attempt_count": 1,
            "points": [],
        },
    }

    text = _report_text(document)

    assert "Bubble target reached." in text
    assert "300.25 K" in text
    assert "5.75 MPa" in text
    assert "Methane=0.5; Ethane=0; Propane=0.5 mol/mol" in text
    assert "Dew corrector stopped safely." in text
    assert re.search(r"Dew branch.*?>FAILED<", text, flags=re.DOTALL)


def test_only_a_real_converged_critical_solve_is_presented_as_certified() -> None:
    inputs = validate_scientific_inputs((50.0, 0.0, 50.0), 320.0, 8.5)
    result = solve_mixture_critical_point(
        inputs.mixture(), inputs.temperature_k, inputs.pressure_pa
    )
    assert result.status is CriticalPointStatus.CONVERGED

    text = _report_text(build_export_document(inputs, critical_result=result))

    assert ">CERTIFIED<" in text
    assert "CriticalPointStatus.CONVERGED is present." in text
    assert f"{result.temperature_k:.12g} K" in text
    assert f"{result.pressure_pa:.12g} Pa" in text


def test_report_states_presentation_and_engine_units_explicitly() -> None:
    inputs, result = run_validated_flash((50.0, 0.0, 50.0), 300.0, 20.0)
    units = UnitPreferences(TemperatureUnit.CELSIUS, PressureUnit.BAR)

    text = _report_text(build_export_document(inputs, flash_result=result, units=units))

    assert "Temperature (presentation)" in text
    assert "°C" in text
    assert "Pressure (presentation)" in text
    assert "bar" in text
    assert "Temperature (engine)" in text
    assert ">K<" in text or " K<" in text
    assert "Pressure (engine)" in text
    assert "Pa" in text
    assert "mol %" in text
    assert "mol/mol" in text
    assert "dimensionless" in text


def test_report_summarizes_an_existing_partial_sweep_without_point_fabrication() -> (
    None
):
    inputs, result = run_validated_flash((50.0, 0.0, 50.0), 300.0, 5.0)
    sweep_document = {
        "request": {
            "kind": "pressure",
            "fixed_temperature": 300.0,
            "fixed_temperature_unit": "K",
            "fixed_pressure": None,
            "fixed_pressure_unit": "MPa",
            "start": 1.0,
            "end": 20.0,
            "sweep_unit": "MPa",
            "points": 5,
        },
        "summary": {
            "requested_points": 5,
            "calculated_points": 4,
            "failed_points": 1,
        },
    }

    text = _report_text(
        build_export_document(inputs, flash_result=result),
        sweep_document=sweep_document,
    )

    assert ">PARTIAL<" in text
    assert "1 requested point(s) failed and remain failed." in text
    assert "1 to 20 MPa" in text
    assert "Failed and unavailable sweep values are not interpolated" in text


def test_report_generation_never_calls_a_scientific_calculation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pvt_phase_simulator.eos import critical_point, flash, phase_envelope

    inputs, result = run_validated_flash((50.0, 0.0, 50.0), 300.0, 5.0)
    document = build_export_document(inputs, flash_result=result)
    calls: list[str] = []

    def forbidden(*_: object, **__: object) -> None:
        calls.append("scientific API called")
        raise AssertionError("report generation must not calculate")

    monkeypatch.setattr(flash, "calculate_two_phase_flash", forbidden)
    monkeypatch.setattr(phase_envelope, "calculate_phase_envelope", forbidden)
    monkeypatch.setattr(critical_point, "solve_mixture_critical_point", forbidden)

    payload = export_engineering_report_html(
        document,
        scope=load_model_scope(ROOT),
        generated_at=GENERATED_AT,
        application_version="test",
    )

    assert payload.startswith(b"<!doctype html>")
    assert calls == []


def test_report_generation_leaves_existing_csv_and_json_exports_unchanged() -> None:
    inputs, result = run_validated_flash((50.0, 0.0, 50.0), 300.0, 20.0)
    document = build_export_document(inputs, flash_result=result)
    csv_before = export_csv_bytes(document)
    json_before = export_json_bytes(document)

    _report_text(document)

    assert export_csv_bytes(document) == csv_before
    assert export_json_bytes(document) == json_before
    assert csv_before.startswith(b"\xef\xbb\xbf")
    assert b'"version": "1.1.0"' in json_before


def _envelope_document(termination_status: str, message: str, points: list[dict]):
    inputs = validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 5.0)
    document = build_export_document(inputs)
    results = document["results"]
    assert isinstance(results, dict)
    results["phase_envelope"] = {
        "calculation_status": "calculated",
        "bubble_branch": {
            "branch_kind": "bubble",
            "termination_status": termination_status,
            "termination_message": message,
            "accepted_point_count": len(points),
            "rejected_attempt_count": 3,
            "points": points,
        },
        "dew_branch": {
            "branch_kind": "dew",
            "termination_status": "target_reached",
            "termination_message": "Dew target reached.",
            "accepted_point_count": 0,
            "rejected_attempt_count": 0,
            "points": [],
        },
    }
    return document


_CONVERGED_POINT = {
    "status": "converged",
    "temperature": 305.5,
    "temperature_unit": "K",
    "pressure": 8.25,
    "pressure_unit": "MPa",
    "parent_composition": (0.5, 0.0, 0.5),
    "incipient_composition": (0.8, 0.0, 0.2),
}

_MINIMUM_STEP_MESSAGE = (
    "Minimum temperature step reached without an acceptable correction."
)


def test_minimum_step_branch_is_not_presented_as_a_completed_traverse() -> None:
    """A stalled continuation must not look like a finished envelope.

    The engine emits ``minimum_step_reached`` only when a retry loop accepted no
    point at all, so presenting it exactly like ``target_reached`` would let a
    reader take a numerical breakdown for a completed traverse.
    """

    document = _envelope_document(
        "minimum_step_reached", _MINIMUM_STEP_MESSAGE, [dict(_CONVERGED_POINT)]
    )
    text = _report_text(document)

    assert re.search(r"Bubble branch.*?>INCOMPLETE<", text, flags=re.DOTALL)
    assert "not a complete envelope traverse" in text
    # The partial result is preserved, not hidden, and so is the real reason.
    assert "305.5 K" in text
    assert "8.25 MPa" in text
    assert _MINIMUM_STEP_MESSAGE in text

    # A genuinely completed branch carries no such warning, so the two cases
    # cannot be confused for one another.
    completed = _report_text(
        _envelope_document(
            "target_reached", "Bubble target reached.", [dict(_CONVERGED_POINT)]
        )
    )
    assert "INCOMPLETE" not in completed
    assert "not a complete envelope traverse" not in completed


def test_minimum_step_branch_without_points_is_not_merely_unavailable() -> None:
    """Nothing converged because continuation broke down: say so, not "unavailable"."""

    text = _report_text(
        _envelope_document("minimum_step_reached", _MINIMUM_STEP_MESSAGE, [])
    )

    assert re.search(r"Bubble branch.*?>INCOMPLETE<", text, flags=re.DOTALL)
    assert _MINIMUM_STEP_MESSAGE in text
    assert not re.search(
        r"Bubble branch.*?>UNAVAILABLE<.*?Dew branch", text, flags=re.DOTALL
    )


def test_structured_envelope_failures_are_still_reported_as_failed() -> None:
    for status in ("corrector_failed", "branch_lost", "numerical_failure"):
        text = _report_text(
            _envelope_document(status, f"Bubble {status}.", [dict(_CONVERGED_POINT)])
        )
        assert re.search(r"Bubble branch.*?>FAILED<", text, flags=re.DOTALL), (
            f"{status} should be reported as a failure"
        )


def test_every_envelope_termination_reason_is_explicitly_classified() -> None:
    """No termination reason may fall through to "normal" by default.

    The previous substring test silently treated any unrecognised reason as a
    normal ending. If the engine gains a termination reason, this fails until
    somebody decides how the report should present it.
    """

    from pvt_phase_simulator.eos.phase_envelope import EnvelopeTerminationReason
    from pvt_phase_simulator_ui import reports

    classified = (
        reports._TERMINATION_NORMAL
        | reports._TERMINATION_INCOMPLETE
        | reports._TERMINATION_FAILED
    )
    every = {reason.value for reason in EnvelopeTerminationReason}
    assert every == classified, (
        "every EnvelopeTerminationReason must be explicitly classified; "
        f"unclassified: {sorted(every - classified)}"
    )
    # The three groups must stay disjoint or a reason would have two meanings.
    assert not (reports._TERMINATION_NORMAL & reports._TERMINATION_INCOMPLETE)
    assert not (reports._TERMINATION_NORMAL & reports._TERMINATION_FAILED)
    assert not (reports._TERMINATION_INCOMPLETE & reports._TERMINATION_FAILED)
