"""The evidence for proposal P12 is what the engine and the reproducer give.

This pins the current engine behaviour that P12 describes, a known limitation,
not a desired outcome. If an approved engine change resolves it, this test and
the proposal are updated together.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from tools import reproduce_near_critical_false_stable as reproducer

ROOT = Path(__file__).resolve().parents[1]
PROPOSAL = " ".join(
    (ROOT / "docs/ENGINE_CHANGE_PROPOSALS.md").read_text(encoding="utf-8").split()
)


@cache
def _rows() -> tuple[reproducer.Row, ...]:
    return tuple(reproducer.rows())


def test_every_state_is_inside_the_extended_envelope() -> None:
    assert all(row.inside_envelope for row in _rows())


def test_the_production_verdicts() -> None:
    first, *rest = _rows()
    assert first.temperature_k == 312.0
    assert (first.flash_phase_state, first.stability_status) == (
        "two_phase",
        "unstable",
    )
    for row in rest:
        assert (row.flash_phase_state, row.stability_status) == (
            "single_phase",
            "stable",
        )
        assert row.both_trials_trivial


def test_an_extra_start_finds_the_missed_instability_at_314_k() -> None:
    row = next(row for row in _rows() if row.temperature_k == 314.0)
    assert row.extra_start_lowest_tpd is not None
    assert row.extra_start_lowest_tpd < -reproducer.TPD_STABILITY_TOLERANCE


def test_the_proposal_table_matches_the_reproducer() -> None:
    for row in _rows():
        assert row.envelope_bubble_pressure_pa is not None
        bubble = f"{row.envelope_bubble_pressure_pa / 1e6:.4f}"
        if row.extra_start_lowest_tpd is None:
            extra = "no extra trial converged"
        else:
            extra = f"TPD {row.extra_start_lowest_tpd:.6f} (x_C1 = {row.extra_start})"
        prefix = f"| {row.temperature_k:.1f} |"
        assert prefix in PROPOSAL
        assert f"| {bubble} | yes |" in PROPOSAL, bubble
        assert extra in PROPOSAL, extra
