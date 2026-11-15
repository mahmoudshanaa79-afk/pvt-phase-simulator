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


def test_the_real_file_reproduction_equals_the_record() -> None:
    """The desktop's run on the real May (2015) file gives the record's metrics."""

    with RECORD.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 40
    for direction in ("bubble", "dew"):
        converged = [row for row in rows if row[f"{direction}_status"] == "converged"]
        errors = [
            float(row[f"{direction}_pressure_percent_error"]) for row in converged
        ]
        aard = sum(abs(error) for error in errors) / len(errors)
        largest = max(abs(error) for error in errors)
        quoted = (
            f"{direction}: {len(converged)} of {len(rows)} converged"
            if direction == "bubble"
            else f"{direction}: {len(converged)} of {len(rows)} converged ("
            f"{sum(row['system_id'] == 'ch4_c2' for row in converged)} CH4+C2, "
            f"{sum(row['system_id'] == 'ch4_c3' for row in converged)} CH4+C3)"
        )
        assert quoted in PLAN, quoted
        assert f"AARD {aard:.3f} %, maximum" in PLAN
        assert f"maximum {largest:.3f} %" in PLAN
        if direction == "bubble":
            bias = sum(errors) / len(errors)
            assert f"bias {bias:.3f} %".replace("-", "−") in PLAN
    statuses = [row["dew_status"] for row in rows]
    inconclusive, not_found = (
        statuses.count("inconclusive"),
        statuses.count("not_found"),
    )
    assert f"{inconclusive} inconclusive and {not_found} not found" in PLAN


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
