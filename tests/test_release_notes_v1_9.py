"""Numbers quoted in the v1.9.0 release notes come from the code and records."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pvt_phase_simulator.eos.flash import calculate_two_phase_flash
from pvt_phase_simulator_ui.solver_codes import CODE_GLOSSARY
from pvt_phase_simulator_ui.views import ENVELOPE_TIME_NOTE
from tools import reproduce_near_critical_false_stable as p12
from tools.engine_fingerprint import cases
from tools.run_p10_survey import read, summary

ROOT = Path(__file__).resolve().parents[1]
NOTES = " ".join(
    (ROOT / "docs/release_notes/v1.9.0.md").read_text(encoding="utf-8").split()
)
HEALTH = (ROOT / "docs/investigations/health_check_2026_11.md").read_text(
    encoding="utf-8"
)


def test_the_glossary_count_and_the_new_code() -> None:
    assert f"explains all {len(CODE_GLOSSARY)} codes" in NOTES
    assert "`STABILITY_TRIVIAL_TRIALS_ONLY`" in NOTES
    assert "STABILITY_TRIVIAL_TRIALS_ONLY" in CODE_GLOSSARY


def test_the_fingerprint_case_count() -> None:
    assert f"engine fingerprint over {len(cases())} cases" in NOTES


def test_the_p12_band_still_reported_stable() -> None:
    rows = p12.rows()
    stable = [row.temperature_k for row in rows if row.stability_status == "stable"]
    assert all(row.inside_envelope for row in rows)
    assert all(row.both_trials_trivial for row in rows if row.temperature_k in stable)
    for temperature in stable:
        flash = calculate_two_phase_flash(p12.MIXTURE, temperature, p12.PRESSURE_PA)
        codes = [item.code for item in flash.phase_stability.verdict_diagnostics]
        assert codes == ["STABILITY_TRIVIAL_TRIALS_ONLY"]
    assert f"from {min(stable):g} K to {max(stable):g} K" in NOTES
    assert f"at {p12.PRESSURE_PA / 1e6:g} MPa" in NOTES


def test_the_p10_survey_numbers() -> None:
    numbers = summary(read(ROOT / "docs/investigations/p10_survey.csv"))
    assert numbers["records_identical"] == numbers["branches"]
    assert numbers["reasons_identical"] == numbers["branches"]
    assert numbers["fallback_points_on"] == 0
    assert f"on {numbers['cases']} cases" in NOTES
    assert f"identical on all {numbers['branches']} branches" in NOTES
    assert "the fallback never rescued a step" in NOTES
    assert f"{numbers['saving_percent']:.1f} % less time" in NOTES


def test_the_mutation_scores_match_the_health_check() -> None:
    row = re.search(
        r"\| `adapters\.py` \(all (\d+) mutants\) \| \d+ \| [^|]+ \| [^|]+ \| "
        r"\d+ / \d+ \(([\d.]+) %\) \| \d+ / \d+ \(([\d.]+) %\) \|",
        HEALTH,
    )
    assert row is not None
    total, before, after = row.groups()
    assert f"covers all {total} mutants" in NOTES
    assert f"from {before} % to {after} %" in NOTES


def test_the_dew_claim_and_the_envelope_time() -> None:
    summary_json = json.loads(
        (ROOT / "docs/validation/module17_vle_validation_summary.json").read_text(
            encoding="utf-8"
        )
    )
    c3 = next(s for s in summary_json["systems"] if s["system_id"] == "ch4_c3")
    dew = c3["production_selected_dew_metrics"]
    assert (
        f"unique dew answer at {dew['success_count']} of {dew['source_count']}" in NOTES
    )
    assert "about one to three minutes" in ENVELOPE_TIME_NOTE
    assert "about one to three minutes" in NOTES
