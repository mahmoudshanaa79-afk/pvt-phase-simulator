"""Current-state numbers in the status page, the v1.6.0 notes and the guides.

Health check 2026-11, docs truth: every number these documents state about the
project as it is now is recomputed here from the protected record, a committed
study file or the engine. "Before" numbers in the decision table (for example
"CH4+C2 bubble 11 → 17") describe the record before an approved change; only
their "after" side is a current claim, and that side is checked.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from pvt_phase_simulator.eos.critical_point import solve_mixture_critical_point
from pvt_phase_simulator_ui.adapters import (
    MAXIMUM_PRESSURE_PA,
    MAXIMUM_TEMPERATURE_K,
    MINIMUM_PRESSURE_PA,
    MINIMUM_TEMPERATURE_K,
    validate_scientific_inputs,
)
from pvt_phase_simulator_ui.learn import LABS

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "docs/validation/module17_vle_validation_summary.json"
INVESTIGATIONS = ROOT / "docs/investigations"
WORDS = {4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}


def _flat(relative: str) -> str:
    return " ".join((ROOT / relative).read_text(encoding="utf-8").split())


STATUS = _flat("docs/PROJECT_STATUS.md").split("## Session log")[0]
NOTES_16 = _flat("docs/release_notes/v1.6.0.md")


def _rows(name: str) -> list[dict[str, str]]:
    with (INVESTIGATIONS / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _metrics(system: str, kind: str) -> dict[str, object]:
    systems = json.loads(SUMMARY.read_text(encoding="utf-8"))["systems"]
    record = next(item for item in systems if item["system_id"] == system)
    return dict(record[f"production_selected_{kind}_metrics"])


def test_the_certified_critical_point() -> None:
    mixture = validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 5.0).mixture()
    result = solve_mixture_critical_point(mixture, 320.0, 8.5e6)
    assert result.status.value == "converged"
    assert result.temperature_k is not None and result.pressure_pa is not None
    quoted = (
        f"50/50 methane/propane: {result.temperature_k:.2f} K, "
        f"{result.pressure_pa / 1e6:.3f} MPa"
    )
    assert quoted in STATUS, quoted


def test_the_envelope_survey_count() -> None:
    rows = _rows("envelope_survey.csv")
    closed = sum(row["current_closed"] == "true" for row in rows)
    quoted = f"{closed} of {len(rows)}"
    assert f"now closes {quoted} cases" in STATUS
    assert f"now closes {quoted} cases" in NOTES_16


def test_the_dew_composition_counts() -> None:
    rows = _rows("dew_conditioning.csv")
    counts = {}
    for system in ("ch4_c3", "ch4_c2"):
        assessed = [
            row
            for row in rows
            if row["system_id"] == system
            and row["vapor_difference_over_uncertainty"] not in ("", "None")
        ]
        within = sum(
            abs(float(row["vapor_difference_over_uncertainty"])) <= 1.0
            for row in assessed
        )
        counts[system] = (within, len(assessed))
    quoted = (
        f"at {counts['ch4_c3'][0]} of {counts['ch4_c3'][1]} CH4+C3 states and "
        f"{counts['ch4_c2'][0]} of {counts['ch4_c2'][1]} assessable CH4+C2 states"
    )
    assert quoted in STATUS, quoted


def test_the_bubble_counts_after_p7() -> None:
    c2, c3 = _metrics("ch4_c2", "bubble"), _metrics("ch4_c3", "bubble")
    for text in (STATUS, NOTES_16):
        assert f"11 → {c2['success_count']}" in text
        assert f"20 → {c3['success_count']}" in text


def test_the_ch4_c2_dew_after_p8() -> None:
    dew = _metrics("ch4_c2", "dew")
    aard = float(str(dew["pressure_aard_percent"]))
    assert f"{dew['success_count']} states at {aard:.2f} %" in STATUS
    assert f"{aard:.2f} %" in NOTES_16


def test_the_ch4_c3_unique_dew_count_in_the_v16_notes() -> None:
    dew = _metrics("ch4_c3", "dew")
    assert (
        f"{dew['success_count']} of {dew['source_count']} measured states" in NOTES_16
    )


def test_the_fitted_kij_numbers() -> None:
    fit = json.loads(
        (INVESTIGATIONS / "kij_study_fit.json").read_text(encoding="utf-8")
    )
    c3 = fit["fits"]["ch4_c3"]
    assert f"CH4+C3 fitted kij {c3['optimum']:+.4f}" in STATUS
    assert f"{c3['aard_at_zero']:.2f} %" in NOTES_16
    assert f"{c3['aard_at_optimum']:.2f} %" in NOTES_16


def test_the_supported_input_range() -> None:
    quoted = (
        f"{MINIMUM_TEMPERATURE_K:g}–{MAXIMUM_TEMPERATURE_K:g} K and "
        f"{MINIMUM_PRESSURE_PA:g} Pa–{MAXIMUM_PRESSURE_PA / 1e9:g} GPa"
    )
    assert quoted in STATUS, quoted


def test_the_number_of_labs_in_every_guide() -> None:
    words = f"{WORDS[len(LABS)]} teaching labs"
    for document in (
        "README.md",
        "docs/USER_GUIDE.md",
        "docs/STREAMLIT_APPLICATION.md",
    ):
        assert words in _flat(document), document
    assert f"{WORDS[len(LABS)].capitalize()} labs in" in STATUS
    for _, name in LABS:
        assert name in _flat("README.md"), name
        assert name in _flat("docs/USER_GUIDE.md"), name
        assert name in _flat("docs/README.md"), name
