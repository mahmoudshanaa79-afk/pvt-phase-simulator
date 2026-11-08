"""Validation numbers quoted to students and the owner match the current record.

Proposals P7 and P8 regenerated the Module 17 record on 1 November 2026. Lab 1,
Learn mode and the project status quote numbers from it; these tests recompute
each quoted number from the protected record (and the P3 study), so a stale
claim fails here instead of reaching a student.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from pvt_phase_simulator_ui.learn import TOPICS

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "docs/validation/module17_vle_validation_summary.json"
STATES = ROOT / "docs/validation/module17_vle_validation.csv"
P3 = ROOT / "docs/investigations/dew_conditioning.csv"


def _flat(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def _metrics(system: str, kind: str) -> dict[str, object]:
    systems = json.loads(SUMMARY.read_text(encoding="utf-8"))["systems"]
    record = next(item for item in systems if item["system_id"] == system)
    return dict(record[f"production_selected_{kind}_metrics"])


def _status_count(system: str, kind: str, status: str) -> int:
    with STATES.open(encoding="utf-8", newline="") as stream:
        return sum(
            row["system_id"] == system and row[f"{kind}_status"] == status
            for row in csv.DictReader(stream)
        )


def test_ch4_c3_dew_claims_in_lab_1_and_learn_mode() -> None:
    bubble = _metrics("ch4_c3", "bubble")
    dew = _metrics("ch4_c3", "dew")
    aard = float(str(bubble["pressure_aard_percent"]))
    assert round(aard) == 1  # "about 1 %"
    assert (dew["success_count"], dew["source_count"]) == (1, 23)
    inconclusive = _status_count("ch4_c3", "dew", "inconclusive")
    assert inconclusive == 20

    lab = _flat(ROOT / "docs/teaching/LAB_01_METHANE_PROPANE.md")
    assert "within about 1 %" in lab
    assert "unique dew pressure at only 1 of the 23 states" in lab
    assert f"at {inconclusive} of the 23 states PR has two dew pressures" in lab

    exercise = " ".join(" ".join(TOPICS["validation"].exercises).split())
    assert "has about 1 % AARD" in exercise
    assert "unique answer at only 1 of the 23 states" in exercise


def test_p3_agreement_quoted_in_lab_1() -> None:
    with P3.open(encoding="utf-8", newline="") as stream:
        rows = [row for row in csv.DictReader(stream) if row["system_id"] == "ch4_c3"]
    within = sum(
        abs(float(row["vapor_difference_over_uncertainty"])) <= 1.0 for row in rows
    )
    assert (within, len(rows)) == (22, 23)
    lab = _flat(ROOT / "docs/teaching/LAB_01_METHANE_PROPANE.md")
    assert f"at {within} of {len(rows)} states" in lab


def test_bubble_evidence_in_the_project_status() -> None:
    status = _flat(ROOT / "docs/PROJECT_STATUS.md")
    for system, label in (("ch4_c2", "CH4+C2"), ("ch4_c3", "CH4+C3")):
        bubble = _metrics(system, "bubble")
        aard = float(str(bubble["pressure_aard_percent"]))
        quoted = (
            f"{label}: {aard:.2f} % AARD, {bubble['success_count']} of "
            f"{bubble['source_count']} states"
        )
        assert quoted in status, quoted


def test_readme_evidence_matches_the_record() -> None:
    readme = _flat(ROOT / "README.md")
    total = 0
    for system, label in (
        ("ch4_c2", "methane + ethane"),
        ("ch4_c3", "methane + propane"),
    ):
        bubble = _metrics(system, "bubble")
        dew = _metrics(system, "dew")
        aard = float(str(bubble["pressure_aard_percent"]))
        row = (
            f"| {label} | {aard:.2f} % AARD, {bubble['success_count']} of "
            f"{bubble['source_count']} states | {dew['success_count']} of "
            f"{dew['source_count']} states |"
        )
        assert row in readme, row
        total += int(str(bubble["source_count"]))
    assert f"with {total} measured methane + ethane and methane + propane" in readme
