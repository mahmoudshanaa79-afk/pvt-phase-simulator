"""Every number in docs/investigations/p10_survey.md comes from its CSV.

The CSV is written by tools/run_p10_survey.py (the app's envelope with and
without the corrector's global fallback, on the 16 cases of
tools/run_envelope_survey.py). Wall times are a record of one run on one
machine and are not recomputed; everything else in the CSV is deterministic.
"""

from __future__ import annotations

from pathlib import Path

from tools.run_envelope_survey import CASES
from tools.run_p10_survey import FIELDS, read, summary, table

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "docs/investigations/p10_survey.csv"
NOTE = (ROOT / "docs/investigations/p10_survey.md").read_text(encoding="utf-8")
FLAT = " ".join(NOTE.split())
ROWS = read(CSV)


def test_the_csv_covers_every_survey_case_once_in_order() -> None:
    assert list(ROWS[0]) == list(FIELDS)
    assert [row["case"] for row in ROWS] == [label for label, _, _ in CASES]
    for row, (_, composition, temperature) in zip(ROWS, CASES, strict=True):
        assert (
            float(row["methane_pct"]),
            float(row["ethane_pct"]),
            float(row["propane_pct"]),
        ) == composition
        assert float(row["temperature_k"]) == temperature


def test_the_per_case_table_is_the_csv() -> None:
    assert table(ROWS) in NOTE


def test_the_quoted_totals() -> None:
    numbers = summary(ROWS)
    quoted = [
        f"{numbers['cases']} cases",
        f"{numbers['branches']} branches",
        f"{numbers['points_on']} accepted points with the fallback and "
        f"{numbers['points_off']} without",
        f"identical on {numbers['records_identical']} of {numbers['branches']} "
        "branches",
        f"termination reasons agree on {numbers['reasons_identical']} of "
        f"{numbers['branches']} branches",
        f"global fallback produced {numbers['fallback_points_on']} accepted points",
        f"tried {numbers['fallback_tries_on']} times",
        f"rejected attempts fall from {numbers['rejected_on']} to "
        f"{numbers['rejected_off']}",
        f"{numbers['seconds_on']:.1f} s with the fallback and "
        f"{numbers['seconds_off']:.1f} s without",
        f"{numbers['saving_percent']:.1f} % less",
    ]
    for text in quoted:
        assert text in FLAT, text


def test_the_time_split_between_cases_with_and_without_fallback_tries() -> None:
    def tries(row: dict[str, str]) -> int:
        return int(row["bubble_fallback_tries_on"]) + int(row["dew_fallback_tries_on"])

    tried = [row for row in ROWS if tries(row) > 0]
    never = [row for row in ROWS if tries(row) == 0]

    def total(rows: list[dict[str, str]], key: str) -> float:
        return sum(float(row[key]) for row in rows)

    quoted = (
        f"the {len(tried)} cases where the fallback was tried: "
        f"{total(tried, 'seconds_on'):.1f} s → {total(tried, 'seconds_off'):.1f} s"
    )
    assert quoted in FLAT, quoted
    gap = max(abs(float(r["seconds_on"]) - float(r["seconds_off"])) for r in never)
    quoted = (
        f"In the {len(never)} cases where it was never tried, both runs do exactly "
        f"the same work. Their times ({total(never, 'seconds_on'):.1f} s → "
        f"{total(never, 'seconds_off'):.1f} s in total, up to {gap:.1f} s apart"
    )
    assert quoted in FLAT, quoted
    for row in never:
        assert row["bubble_rejected_on"] == row["bubble_rejected_off"]
        assert row["dew_rejected_on"] == row["dew_rejected_off"]
