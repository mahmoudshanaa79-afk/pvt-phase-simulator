"""Numbers quoted in the v1.8.0 release notes come from the code and records."""

from __future__ import annotations

import json
from pathlib import Path

from pvt_phase_simulator_ui.learn import LABS
from pvt_phase_simulator_ui.solver_codes import CODE_GLOSSARY
from pvt_phase_simulator_ui.views import ENVELOPE_TIME_NOTE
from tools import reproduce_near_critical_false_stable as p12

ROOT = Path(__file__).resolve().parents[1]
NOTES = " ".join(
    (ROOT / "docs/release_notes/v1.8.0.md").read_text(encoding="utf-8").split()
)
WORDS = {6: "six", 7: "seven", 8: "eight"}


def test_glossary_and_lab_counts() -> None:
    assert f"lists all {len(CODE_GLOSSARY)} codes" in NOTES
    assert f"links {WORDS[len(LABS)]} teaching labs" in NOTES


def test_the_p12_temperature_band() -> None:
    rows = p12.rows()
    stable = [row.temperature_k for row in rows if row.stability_status == "stable"]
    assert all(row.inside_envelope for row in rows)
    quoted = f"from {min(stable):g} K to {max(stable):g} K"
    assert quoted in NOTES, quoted
    assert f"at {p12.PRESSURE_PA / 1e6:g} MPa" in NOTES


def test_the_dew_claim() -> None:
    summary = json.loads(
        (ROOT / "docs/validation/module17_vle_validation_summary.json").read_text(
            encoding="utf-8"
        )
    )
    c3 = next(item for item in summary["systems"] if item["system_id"] == "ch4_c3")
    dew = c3["production_selected_dew_metrics"]
    quoted = f"unique dew answer at {dew['success_count']} of {dew['source_count']}"
    assert quoted in NOTES, quoted


def test_the_retrograde_temperature_and_envelope_time() -> None:
    lab7 = (ROOT / "docs/teaching/LAB_07_CRITICAL_POINT_AND_RETROGRADE.md").read_text(
        encoding="utf-8"
    )
    assert "Retrograde condensation at 327 K" in lab7
    assert "retrograde condensation at 327 K" in NOTES
    assert "about one to three minutes" in ENVELOPE_TIME_NOTE
    assert "about one to three minutes" in NOTES
