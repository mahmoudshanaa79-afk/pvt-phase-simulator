"""Numbers quoted in the v1.7.0 release notes come from the committed records."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from tools import engine_fingerprint

ROOT = Path(__file__).resolve().parents[1]
NOTES = ROOT / "docs/release_notes/v1.7.0.md"
PERFORMANCE = ROOT / "docs/investigations"


def _flat() -> str:
    return " ".join(NOTES.read_text(encoding="utf-8").split())


def _first_envelope(name: str) -> dict[str, float]:
    with (PERFORMANCE / name).open(encoding="utf-8", newline="") as stream:
        return {
            row["case"]: float(row["median_s"])
            for row in csv.DictReader(stream)
            if row["label"] == "RUN PHASE ENVELOPE"
        }


def test_the_speed_up_range() -> None:
    before = _first_envelope("app_performance_before_p9.csv")
    after = _first_envelope("app_performance_after_p9.csv")
    assert before.keys() == after.keys() and len(before) == 3
    ratios = [before[case] / after[case] for case in before]
    quoted = f"about {min(ratios):.1f} to {max(ratios):.1f} times faster"
    assert quoted in _flat(), quoted


def test_the_fingerprint_case_count() -> None:
    count = len(engine_fingerprint.cases())
    assert f"complete result of {count} cases" in _flat()
    assert f"{count} of {count} fingerprints identical" in _flat()


def test_the_dew_claim() -> None:
    summary = json.loads(
        (ROOT / "docs/validation/module17_vle_validation_summary.json").read_text(
            encoding="utf-8"
        )
    )
    c3 = next(item for item in summary["systems"] if item["system_id"] == "ch4_c3")
    dew = c3["production_selected_dew_metrics"]
    quoted = f"unique dew answer at {dew['success_count']} of {dew['source_count']}"
    assert quoted in _flat(), quoted
