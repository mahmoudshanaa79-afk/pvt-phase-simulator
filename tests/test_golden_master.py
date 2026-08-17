"""Behavioral tests for the numerical golden-master infrastructure."""

import csv
from io import StringIO
from pathlib import Path

import pytest

from tests.golden_master.cases import build_cases, validate_case_ids
from tests.golden_master.core import (
    FIELDS,
    compare_rows,
    load_csv,
    rows_to_csv,
    serialize_value,
    source_commit,
)


def _row(case_id: str = "case") -> dict[str, str]:
    return {field: case_id if field == "case_id" else "" for field in FIELDS}


def test_serialization_is_deterministic_and_round_trip_precise() -> None:
    value = 0.12345678901234568
    assert serialize_value(value) == repr(value)
    assert serialize_value((value, 1.0)) == serialize_value((value, 1.0))


def test_case_ids_are_stable_unique_and_semantic() -> None:
    first = build_cases()
    assert first == build_cases()
    assert len(first) == len({case.case_id for case in first})
    assert all(not case.case_id.startswith("case_") for case in first)


def test_duplicate_case_ids_are_rejected() -> None:
    case = build_cases()[0]
    with pytest.raises(ValueError, match="duplicate case IDs"):
        validate_case_ids((case, case))


@pytest.mark.parametrize(
    ("field", "old", "new", "classification"),
    [
        ("pressure_pa", "1000000.0", "1000000.0001", "PHYSICAL_RESULT_DRIFT"),
        (
            "liquid_composition",
            "[0.5,0.5]",
            "[0.50000000001,0.49999999999]",
            "PLATFORM_OR_FORMATTING_NOISE",
        ),
        (
            "liquid_composition",
            "[0.5,0.5]",
            "[0.500001,0.499999]",
            "PHYSICAL_RESULT_DRIFT",
        ),
        ("beta", "0.5", "0.500001", "PHYSICAL_RESULT_DRIFT"),
        ("liquid_root", "0.1", "0.100001", "PHYSICAL_RESULT_DRIFT"),
        ("status", "stable", "unstable", "PHYSICAL_RESULT_DRIFT"),
        (
            "termination_reason",
            "target_reached",
            "branch_lost",
            "PHYSICAL_RESULT_DRIFT",
        ),
        ("inner_iterations", "10", "11", "NUMERICAL_PATH_CHANGE"),
        ("fallback_used", "False", "True", "NUMERICAL_PATH_CHANGE"),
        (
            "correction_source",
            "local",
            "expanded_local",
            "NUMERICAL_PATH_CHANGE",
        ),
        ("platform", "win32", "linux", "PLATFORM_OR_FORMATTING_NOISE"),
        (
            "pressure_pa",
            "1000000.0",
            "1000000.000001",
            "PLATFORM_OR_FORMATTING_NOISE",
        ),
    ],
)
def test_comparison_tolerances_and_classifications(
    field: str, old: str, new: str, classification: str | None
) -> None:
    expected, actual = _row(), _row()
    expected[field], actual[field] = old, new
    differences = compare_rows([expected], [actual])
    populated = [name for name, items in differences.items() if items]
    assert populated == ([] if classification is None else [classification])


def test_diagnostic_membership_is_an_exact_unordered_set() -> None:
    expected, actual = _row(), _row()
    expected["diagnostic_codes"] = '["A","B"]'
    actual["diagnostic_codes"] = '["B","A"]'
    assert not any(compare_rows([expected], [actual]).values())
    actual["diagnostic_codes"] = '["A","C"]'
    assert compare_rows([expected], [actual])["PHYSICAL_RESULT_DRIFT"]


def test_missing_and_extra_cases_are_reported() -> None:
    differences = compare_rows([_row("expected")], [_row("actual")])
    assert differences["MISSING_CASE"] == ["expected"]
    assert differences["EXTRA_CASE"] == ["actual"]


def test_source_commit_is_recorded_from_repository() -> None:
    commit = source_commit(Path(__file__).resolve().parents[1])
    assert len(commit) == 40 and all(
        character in "0123456789abcdef" for character in commit
    )


def test_loader_validates_schema_duplicates_and_order(tmp_path: Path) -> None:
    valid = [_row("a"), _row("b")]
    path = tmp_path / "baseline.csv"
    path.write_text(rows_to_csv(valid), encoding="utf-8")
    assert [row["case_id"] for row in load_csv(path)] == ["a", "b"]
    path.write_text(rows_to_csv([_row("a"), _row("a")]), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_csv(path)
    reversed_rows = StringIO()
    writer = csv.DictWriter(reversed_rows, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows([_row("b"), _row("a")])
    path.write_text(reversed_rows.getvalue(), encoding="utf-8")
    with pytest.raises(ValueError, match="not sorted"):
        load_csv(path)
    malformed = _row("a")
    malformed["feed_composition"] = "[invalid"
    path.write_text(rows_to_csv([malformed]), encoding="utf-8")
    with pytest.raises(ValueError, match="malformed value"):
        load_csv(path)
    stream = StringIO()
    writer = csv.DictWriter(stream, fieldnames=("case_id",))
    writer.writeheader()
    writer.writerow({"case_id": "a"})
    path.write_text(stream.getvalue(), encoding="utf-8")
    with pytest.raises(ValueError, match="schema"):
        load_csv(path)
