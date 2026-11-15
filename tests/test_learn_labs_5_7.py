"""Learn-mode exercises added with Labs 5-7 quote numbers the engine gives."""

from __future__ import annotations

from pvt_phase_simulator_ui.adapters import (
    run_validated_flash,
    validate_scientific_inputs,
)
from pvt_phase_simulator_ui.envelope_extension import trace_extended_envelope
from pvt_phase_simulator_ui.learn import TOPICS
from pvt_phase_simulator_ui.volume_translation_view import phase_volume_rows


def _text(page: str) -> str:
    return " ".join(" ".join(TOPICS[page].exercises).split())  # type: ignore[index]


def test_volume_translation_exercise() -> None:
    _, result = run_validated_flash((50.0, 0.0, 50.0), 300.0, 5.0)
    liquid, vapour = phase_volume_rows(result)
    assert liquid["Phase"] == "Liquid" and vapour["Phase"] == "Vapor"
    text = _text("overview")
    assert (
        f"from about {float(liquid['PR density (mol/m³)']):.0f} to "
        f"{float(liquid['Translated density (mol/m³)']):.0f} mol/m³"
    ) in text
    assert (
        f"from about {float(vapour['PR density (mol/m³)']):.0f} to "
        f"{float(vapour['Translated density (mol/m³)']):.0f} mol/m³"
    ) in text


def test_tangent_plane_distance_exercise() -> None:
    _, result = run_validated_flash((50.0, 0.0, 50.0), 300.0, 5.0)
    trial = result.phase_stability.liquid_like_trial
    assert trial.converged and not trial.trivial_solution
    assert trial.tangent_plane_distance is not None
    assert f"about {trial.tangent_plane_distance:.3f}: negative" in _text("diagnostics")
    assert result.phase_stability.status.value == "unstable"


def test_retrograde_exercise() -> None:
    mixture = validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 5.0).mixture()
    envelope = trace_extended_envelope(mixture, 300.0)
    therm = max(point.temperature_k for point in envelope.dew.points)
    text = _text("critical_point")
    assert f"cricondentherm (about {therm:.1f} K)" in text
    pressures = (7.70, 7.50, 7.25, 7.00, 6.50, 6.00)
    liquid = {}
    for pressure in pressures:
        _, result = run_validated_flash((50.0, 0.0, 50.0), 327.0, pressure)
        assert result.liquid_fraction is not None
        liquid[pressure] = result.liquid_fraction
    peak = max(liquid, key=liquid.__getitem__)
    assert f"peaks near {liquid[peak]:.2f} at {peak:.2f} MPa" in text
