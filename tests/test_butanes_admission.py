"""The butane draft: second dataset, optional systems and the final-step command.

These checks are fast and leave the committed files alone. The full dry run of
``tools/admit_butanes.py`` regenerates the validation record (about 25 minutes)
and is recorded in ``docs/investigations/butanes_admission_dry_run.md``.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest

from pvt_phase_simulator.experimental_validation import (
    REQUIRED_SYSTEMS,
    butanes_admitted,
    load_experimental_vle_dataset,
)
from tools import admit_butanes

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "experimental"


def test_the_butane_dataset_loads_with_its_own_manifest() -> None:
    dataset = load_experimental_vle_dataset(
        DATA / "may_2015_butanes_vle.csv", DATA / "may_2015_butanes_manifest.json"
    )
    counts: dict[str, int] = {}
    for point in dataset.points:
        counts[point.system_id] = counts.get(point.system_id, 0) + 1
    assert counts == {"ch4_ic4": 17, "ch4_nc4": 19}


def test_the_main_dataset_is_unchanged() -> None:
    dataset = load_experimental_vle_dataset(
        DATA / "may_2015_ch4_c2_ch4_c3_vle.csv",
        DATA / "may_2015_source_manifest.json",
    )
    systems = sorted({point.system_id for point in dataset.points})
    assert systems == sorted(REQUIRED_SYSTEMS)
    assert len(dataset.points) == 40


def test_admission_state_is_consistent() -> None:
    # On the draft branch nothing is admitted: the verified-provenance gate
    # keeps provisional rows out of the shared database, and only the final
    # step adds them. After the final step all three move together.
    text = (ROOT / admit_butanes.RECORD).read_text(encoding="utf-8")
    _, _, butane_rows = admit_butanes._rows_by_system(text)
    database = (ROOT / admit_butanes.DATABASE_FILES[0]).read_text(encoding="utf-8")
    in_database = {
        row["component_id"] for row in csv.DictReader(io.StringIO(database))
    } >= set(admit_butanes.COMPONENTS)
    assert butanes_admitted() is in_database
    assert len(butane_rows) == (36 if in_database else 0)


def _provisional() -> dict:
    return admit_butanes.read_values(ROOT / admit_butanes.VALUES, provisional=True)


def test_the_values_file_is_provisional_and_refused_as_final() -> None:
    values = _provisional()
    assert values["status"] == "provisional"
    with pytest.raises(admit_butanes.AdmissionError, match="not marked table5"):
        admit_butanes.read_values(ROOT / admit_butanes.VALUES, provisional=False)


def test_a_final_values_file_needs_who_read_it_and_the_original_source(
    tmp_path: Path,
) -> None:
    values = _provisional()
    values["status"] = "table5"
    path = tmp_path / "values.json"
    path.write_text(json.dumps(values), encoding="utf-8")
    with pytest.raises(admit_butanes.AdmissionError, match="read_by"):
        admit_butanes.read_values(path, provisional=False)
    values |= {"read_by": "Owner", "read_on": "2026-11-09"}
    path.write_text(json.dumps(values), encoding="utf-8")
    with pytest.raises(admit_butanes.AdmissionError, match="original_source"):
        admit_butanes.read_values(path, provisional=False)
    for entry in values["components"].values():
        entry["original_source_as_printed"] = "DIPPR"
    path.write_text(json.dumps(values), encoding="utf-8")
    with pytest.raises(admit_butanes.AdmissionError, match="expects REFPROP"):
        admit_butanes.read_values(path, provisional=False)
    for entry in values["components"].values():
        entry["original_source_as_printed"] = "REFPROP"
    path.write_text(json.dumps(values), encoding="utf-8")
    assert admit_butanes.read_values(path, provisional=False)["status"] == "table5"
    values["components"]["isobutane"]["acentric_factor"] = -1
    path.write_text(json.dumps(values), encoding="utf-8")
    with pytest.raises(admit_butanes.AdmissionError, match="positive number"):
        admit_butanes.read_values(path, provisional=False)


def test_provisional_rows_never_claim_verification() -> None:
    rows = admit_butanes.database_rows(_provisional(), provisional=True)
    assert len(rows) == 6
    for row in rows:
        assert row["source_status"] == "provisional"
        assert "Yang" not in row["source_reference_name"]
        assert "not Yang & Richter" in row["property_source_identity"]
        assert "Never verified" in row["notes"]
    pressures = {
        r["component_id"]: r["value"] for r in rows if "pressure" in r["property"]
    }
    assert pressures == {"isobutane": "3629000.0", "n_butane": "3796000.0"}


def test_final_rows_use_the_wording_the_provenance_gate_expects() -> None:
    values = _provisional() | {"read_by": "Owner", "read_on": "2026-11-09"}
    for entry in values["components"].values():
        entry["original_source_as_printed"] = "REFPROP"
    rows = admit_butanes.database_rows(values, provisional=False)
    for row in rows:
        assert row["source_status"] == "verified"
        assert row["property_source_identity"].startswith(
            "Yang & Richter (2025) Table 5; "
        )
        assert "originally taken from REFPROP" in row["property_source_identity"]
        assert "no direct REFPROP query was made." in row["notes"]


def test_rows_append_once_and_keep_the_header(tmp_path: Path) -> None:
    target = tmp_path / "component_properties.csv"
    # Start from the C1-C3 rows, whether or not the butanes are admitted.
    source = (ROOT / admit_butanes.DATABASE_FILES[0]).read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    before = lines[0] + "".join(
        line
        for line in lines[1:]
        if next(csv.reader([line]))[0] not in admit_butanes.COMPONENTS
    )
    target.write_text(before, encoding="utf-8", newline="")
    rows = admit_butanes.database_rows(_provisional(), provisional=True)
    admit_butanes.append_rows(target, rows)
    after = target.read_text(encoding="utf-8")
    assert after.startswith(before)
    added = list(csv.DictReader(io.StringIO(after)))[-6:]
    assert [row["component_id"] for row in added] == ["isobutane"] * 3 + [
        "n_butane"
    ] * 3
    with pytest.raises(admit_butanes.AdmissionError, match="already holds"):
        admit_butanes.append_rows(target, rows)


def test_pins_are_refreshed_only_where_the_old_digest_appears(tmp_path: Path) -> None:
    for name in admit_butanes.PIN_FILES:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
    first, second = (tmp_path / name for name in admit_butanes.PIN_FILES)
    first.write_text('PIN = "AAAA"\n', encoding="utf-8")
    second.write_text('OTHER = "CCCC"\n', encoding="utf-8")
    changed = admit_butanes.refresh_pins(
        tmp_path, {"record": ("AAAA", "BBBB"), "golden": ("DDDD", "DDDD")}
    )
    assert changed == [admit_butanes.PIN_FILES[0]]
    assert first.read_text(encoding="utf-8") == 'PIN = "BBBB"\n'
    assert second.read_text(encoding="utf-8") == 'OTHER = "CCCC"\n'


def test_the_committed_record_splits_into_c1_c3_rows_only() -> None:
    text = (ROOT / admit_butanes.RECORD).read_text(encoding="utf-8")
    header, core, butanes = admit_butanes._rows_by_system(text)
    assert header.startswith("source_point_id,system_id,")
    assert len(core) == 40
    assert len(butanes) == (36 if butanes_admitted() else 0)
