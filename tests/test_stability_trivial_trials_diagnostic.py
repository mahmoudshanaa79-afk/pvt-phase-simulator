"""P12 (b): a stable verdict that rests only on trivial trials is labelled.

Owner-approved on 15 November 2026. The engine adds the diagnostic
``STABILITY_TRIVIAL_TRIALS_ONLY`` to a new field,
``MixturePhaseStabilityResult.verdict_diagnostics``, when the verdict is stable
and both production trials returned the trivial solution. The verdict, the
feed-reference and trial-character diagnostics and the flash diagnostics are
unchanged, so every existing result stays byte-identical.
"""

from __future__ import annotations

import pytest

from pvt_phase_simulator.eos.diagnostics import DiagnosticCategory, DiagnosticSeverity
from pvt_phase_simulator.eos.flash import TwoPhaseFlashResult, calculate_two_phase_flash
from pvt_phase_simulator.eos.phase_stability import (
    STABILITY_TRIVIAL_TRIALS_ONLY,
    PhaseStabilityStatus,
)
from pvt_phase_simulator_ui.adapters import TRIVIAL_TRIALS_NOTE, stability_verdict_note
from tools.reproduce_near_critical_false_stable import MIXTURE, PRESSURE_PA

ALARMING = ("error", "fail", "wrong", "invalid", "unreliable", "danger")


def _flash(temperature_k: float, pressure_pa: float) -> TwoPhaseFlashResult:
    return calculate_two_phase_flash(MIXTURE, temperature_k, pressure_pa)


def _verdict_codes(result: TwoPhaseFlashResult) -> list[str]:
    return [item.code for item in result.phase_stability.verdict_diagnostics]


def _older_codes(result: TwoPhaseFlashResult) -> set[str]:
    stability = result.phase_stability
    return {
        item.code
        for item in (
            *result.diagnostics,
            *stability.feed_reference.diagnostics,
            *stability.vapor_like_character.diagnostics,
            *stability.liquid_like_character.diagnostics,
        )
    }


@pytest.mark.parametrize("temperature_k", (314.0, 316.0, 318.0, 320.0))
def test_the_near_critical_false_stable_band_carries_the_diagnostic(
    temperature_k: float,
) -> None:
    result = _flash(temperature_k, PRESSURE_PA)
    stability = result.phase_stability
    assert stability.status is PhaseStabilityStatus.STABLE
    assert stability.vapor_like_trial.trivial_solution
    assert stability.liquid_like_trial.trivial_solution
    assert _verdict_codes(result) == [STABILITY_TRIVIAL_TRIALS_ONLY]
    (diagnostic,) = stability.verdict_diagnostics
    assert diagnostic.severity is DiagnosticSeverity.WARNING
    assert diagnostic.category is DiagnosticCategory.NUMERICAL_CONDITIONING
    assert diagnostic.message.startswith(
        "Stable here means no instability was found: both stability trials "
        "returned the trivial solution"
    )
    assert "phase envelope" in diagnostic.message
    assert diagnostic.value is None
    assert stability_verdict_note(result) == TRIVIAL_TRIALS_NOTE


def test_the_unstable_state_at_312_k_does_not() -> None:
    result = _flash(312.0, PRESSURE_PA)
    assert result.phase_stability.status is PhaseStabilityStatus.UNSTABLE
    assert _verdict_codes(result) == []
    assert stability_verdict_note(result) is None


def test_a_genuine_single_phase_carries_it_without_alarm() -> None:
    result = _flash(300.0, 20e6)
    stability = result.phase_stability
    assert result.phase_state.value == "single_phase"
    assert stability.status is PhaseStabilityStatus.STABLE
    assert stability.vapor_like_trial.trivial_solution
    assert stability.liquid_like_trial.trivial_solution
    assert _verdict_codes(result) == [STABILITY_TRIVIAL_TRIALS_ONLY]
    texts = (stability.verdict_diagnostics[0].message, TRIVIAL_TRIALS_NOTE)
    for text in texts:
        assert not any(word in text.lower() for word in ALARMING), text
    assert "normal for a clear single phase" in TRIVIAL_TRIALS_NOTE


def test_a_stable_verdict_with_a_converged_non_trivial_trial_does_not() -> None:
    result = _flash(250.0, 1e5)
    stability = result.phase_stability
    assert stability.status is PhaseStabilityStatus.STABLE
    trials = (stability.vapor_like_trial, stability.liquid_like_trial)
    assert any(trial.converged and not trial.trivial_solution for trial in trials)
    assert _verdict_codes(result) == []
    assert stability_verdict_note(result) is None


@pytest.mark.parametrize(
    ("temperature_k", "pressure_pa"),
    ((316.0, PRESSURE_PA), (312.0, PRESSURE_PA), (300.0, 20e6), (250.0, 1e5)),
)
def test_the_new_code_never_enters_the_older_diagnostic_tuples(
    temperature_k: float, pressure_pa: float
) -> None:
    # Those tuples feed the golden master, the flash diagnostics and the exports.
    assert STABILITY_TRIVIAL_TRIALS_ONLY not in _older_codes(
        _flash(temperature_k, pressure_pa)
    )
