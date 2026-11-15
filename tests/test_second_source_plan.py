"""Numbers and commands in docs/SECOND_SOURCE_PLAN.md are true and runnable."""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = " ".join(
    (ROOT / "docs/SECOND_SOURCE_PLAN.md").read_text(encoding="utf-8").split()
)
RECORD = ROOT / "docs/validation/module17_vle_validation.csv"
SUMMARY = ROOT / "docs/validation/module17_vle_validation_summary.json"


def test_the_ch4_c3_numbers() -> None:
    systems = json.loads(SUMMARY.read_text(encoding="utf-8"))["systems"]
    bubble = next(s for s in systems if s["system_id"] == "ch4_c3")[
        "production_selected_bubble_metrics"
    ]
    quoted = (
        f"{bubble['pressure_aard_percent']:.2f} % AARD at {bubble['success_count']} of "
        f"{bubble['source_count']} states, kij = 0"
    )
    assert quoted in PLAN, quoted
    with RECORD.open(encoding="utf-8", newline="") as stream:
        temperatures = [
            float(row["temperature_k"])
            for row in csv.DictReader(stream)
            if row["system_id"] == "ch4_c3"
        ]
    assert f"({min(temperatures):g}–{max(temperatures):g} K)" in PLAN


def test_every_candidate_is_marked_not_verified() -> None:
    rows = [
        line
        for line in (ROOT / "docs/SECOND_SOURCE_PLAN.md")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.startswith("| ") and not line.startswith(("| Candidate", "|---"))
    ]
    assert len(rows) >= 5
    assert all("NOT VERIFIED: not downloaded" in row for row in rows)


def test_the_commands_name_existing_tools() -> None:
    for tool in ("tools/compare_thermoml_vle.py", "tools/compare_liquid_density.py"):
        assert f"uv run python {tool} --input <file>.json --output-dir" in PLAN
        assert (ROOT / tool).is_file()
