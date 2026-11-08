"""Admit isobutane and n-butane, validation only, from one small values file.

The owner's final step (docs/BUTANES_ADMISSION_PLAN.md), once the Yang & Richter
(2025) Table 5 values are entered exactly as printed in
``data/butanes_table5_values.json`` with ``"status": "table5"``::

    uv run python tools/admit_butanes.py

Dry run on the provisional CoolProp values, in a throwaway copy::

    git worktree add --detach /tmp/butanes-dry-run
    uv run python tools/admit_butanes.py --provisional --root /tmp/butanes-dry-run

What it does, in order, and nothing else:

1. reads and checks the values file (a provisional file is accepted only with
   ``--provisional``; a ``table5`` file only without it);
2. appends six rows (T_c, p_c, omega for each butane) to both identical copies of
   the component-property CSV: ``verified`` with Table 5 provenance, or, with
   ``--provisional``, ``provisional`` with CoolProp 6.6.0 named as the source;
3. final mode only: adds the two butanes to the pinned source tables of
   ``tests/test_component_database.py``;
4. regenerates ``docs/validation`` with ``tools/run_module17_validation.py``,
   which now also validates the butane data file (option (b): validation
   only, the app's inputs are unchanged);
5. regenerates the record on this machine before and after adding the rows
   and requires the methane-ethane and methane-propane rows of the two runs to
   be byte-identical; then writes the committed C1-C3 rows and summary entries
   unchanged, followed by the new butane rows and summaries, so the C1-C3 rows
   stay byte-identical to master on any machine (the last digits of a fresh
   regeneration can differ between machines); checks the golden master file
   is unchanged;
6. refreshes the pinned SHA-256 values of the changed protected files in
   ``tests/test_validation_metrics.py`` and ``tests/test_app_adapters.py``;
7. prints the butane results.

It never edits ``data/experimental`` and never changes a C1-C3 row. In
``--provisional`` mode the verified-provenance test of
``tests/test_component_database.py`` is expected to fail for the butane rows:
that test is right, and only verified Table 5 values can satisfy it.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

DATABASE_FILES = (
    "data/component_properties.csv",
    "src/pvt_phase_simulator/data/component_properties.csv",
)
RECORD = "docs/validation/module17_vle_validation.csv"
SUMMARY = "docs/validation/module17_vle_validation_summary.json"
GOLDEN = "tests/golden_master/baseline.csv"
PIN_FILES = ("tests/test_validation_metrics.py", "tests/test_app_adapters.py")
VALUES = "data/butanes_table5_values.json"
C1_C3 = ("ch4_c2", "ch4_c3")

COMPONENTS = {
    "isobutane": {
        "canonical_name": "Isobutane",
        "aliases": "iC4|i-C4H10|2-methylpropane",
        "cas": "75-28-5",
        "coolprop": "IsoButane",
    },
    "n_butane": {
        "canonical_name": "n-Butane",
        "aliases": "nC4|n-C4H10|butane",
        "cas": "106-97-8",
        "coolprop": "n-Butane",
    },
}
PROPERTIES = (
    ("critical_temperature", "K", "critical temperature", "Tcrit"),
    ("critical_pressure", "Pa", "critical pressure", "pcrit"),
    ("acentric_factor", "1", "acentric factor", "acentric"),
)
TABLE5_REFERENCE = "Yang & Richter (2025), Journal of Chemical & Engineering Data"
TABLE5_CITATION = (
    "X. Yang and M. Richter, Effective Thermophysical Constants of Thousands of "
    "Fluids. I: Critical Temperature, Critical Pressure, Critical Density, and "
    "Acentric Factor, J. Chem. Eng. Data 2025 70 (8) 2911-2946"
)
TABLE5_DOI = "10.1021/acs.jced.5c00110"
TABLE5_EDITION = "2025; 70(8); 2911-2946"


class AdmissionError(ValueError):
    """The values file or the repository is not in a state to admit."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def read_values(path: Path, provisional: bool) -> dict[str, Any]:
    values = json.loads(path.read_text(encoding="utf-8"))
    status = values.get("status")
    if provisional and status != "provisional":
        raise AdmissionError(
            "--provisional needs a values file with status provisional."
        )
    if not provisional:
        if status != "table5":
            raise AdmissionError(
                "The values file is not marked table5. Enter the Yang & Richter "
                "(2025) Table 5 values as printed and set status to table5, or "
                "use --provisional for a dry run."
            )
        for field in ("read_by", "read_on"):
            if not values.get(field):
                raise AdmissionError(f"The values file needs {field}.")
    for component_id in COMPONENTS:
        entry = values["components"][component_id]
        for field in (
            "critical_temperature_k",
            "critical_pressure_kpa",
            "acentric_factor",
        ):
            number = entry[field]
            if not isinstance(number, (int, float)) or not number > 0:
                raise AdmissionError(
                    f"{component_id}.{field} must be a positive number."
                )
        if not provisional and not entry.get("original_source_as_printed"):
            raise AdmissionError(f"{component_id} needs original_source_as_printed.")
    return values


def _value_text(component: dict[str, Any], property_name: str) -> str:
    if property_name == "critical_temperature":
        return repr(float(component["critical_temperature_k"]))
    if property_name == "critical_pressure":
        # Exact decimal conversion of the printed kPa value: 1 kPa = 1000 Pa.
        pascal = Decimal(str(component["critical_pressure_kpa"])) * 1000
        return repr(float(pascal))
    return repr(float(component["acentric_factor"]))


def database_rows(values: dict[str, Any], provisional: bool) -> list[dict[str, str]]:
    rows = []
    for component_id, meta in COMPONENTS.items():
        entry = values["components"][component_id]
        for property_name, unit, description, coolprop_key in PROPERTIES:
            row = {
                "component_id": component_id,
                "canonical_name": meta["canonical_name"],
                "aliases": meta["aliases"],
                "property": property_name,
                "value": _value_text(entry, property_name),
                "unit": unit,
                "original_unit": "",
                "conversion": "",
                "url": "",
            }
            if provisional:
                row |= {
                    "source_status": "provisional",
                    "source_reference_name": "CoolProp 6.6.0 (provisional)",
                    "property_source_identity": (
                        f"CoolProp 6.6.0 reference equation of state; "
                        f"{meta['coolprop']}; PropsSI {coolprop_key}; "
                        "PROVISIONAL, not Yang & Richter (2025)"
                    ),
                    "citation_text": "",
                    "doi": "",
                    "edition_or_version": "CoolProp 6.6.0",
                    "notes": (
                        "Provisional dry-run value; reproduce with the command in "
                        "tools/run_butane_preview.py. Never verified."
                    ),
                }
            else:
                original = entry["original_source_as_printed"]
                row |= {
                    "source_status": "verified",
                    "source_reference_name": TABLE5_REFERENCE,
                    "property_source_identity": (
                        f"Yang & Richter (2025) Table 5; {meta['canonical_name']}; "
                        f"CAS RN {meta['cas']}; {description}; originally taken "
                        f"from {original}"
                    ),
                    "citation_text": TABLE5_CITATION,
                    "doi": TABLE5_DOI,
                    "edition_or_version": TABLE5_EDITION,
                    "notes": (
                        f"Primary article Table 5 independently inspected by "
                        f"{values['read_by']} on {values['read_on']}; the article "
                        f"identifies {original} as the original source; no direct "
                        f"{original} query was made."
                    ),
                }
                if property_name == "critical_pressure":
                    row |= {"original_unit": "kPa", "conversion": "1 kPa = 1000 Pa"}
            rows.append(row)
    return rows


def append_rows(path: Path, rows: list[dict[str, str]]) -> None:
    text = path.read_text(encoding="utf-8")
    header = next(csv.reader(io.StringIO(text)))
    existing = {row["component_id"] for row in csv.DictReader(io.StringIO(text))}
    if existing & set(COMPONENTS):
        raise AdmissionError(f"{path} already holds butane rows.")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=header, lineterminator="\n")
    writer.writerows(rows)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text + stream.getvalue(), encoding="utf-8", newline="")


def extend_source_tables(path: Path, values: dict[str, Any]) -> None:
    """Final mode: add the verified butanes to the test's pinned source tables."""

    text = path.read_text(encoding="utf-8")
    sourced = "".join(
        f'    "{component_id}": ("{meta["canonical_name"]}", '
        f"{_value_text(values['components'][component_id], 'critical_temperature')}, "
        f"{_value_text(values['components'][component_id], 'critical_pressure')}, "
        f"{_value_text(values['components'][component_id], 'acentric_factor')}),\n"
        for component_id, meta in COMPONENTS.items()
    )
    records = "".join(
        f'    "{component_id}": "{meta["cas"]}",\n'
        for component_id, meta in COMPONENTS.items()
    )
    for anchor, addition in (
        ('    "propane": ("Propane", 369.890, 4_251_200.0, 0.152100),\n', sourced),
        ('    "propane": "74-98-6",\n', records),
    ):
        if text.count(anchor) != 1:
            raise AdmissionError(f"cannot find {anchor.strip()!r} in {path}.")
        text = text.replace(anchor, anchor + addition)
    path.write_text(text, encoding="utf-8", newline="")


def c1_c3_rows(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    header = lines[0].rstrip("\r\n").split(",")
    index = header.index("system_id")
    return [lines[0]] + [
        line for line in lines[1:] if next(csv.reader([line]))[index] in C1_C3
    ]


def refresh_pins(root: Path, digests: dict[str, tuple[str, str]]) -> list[str]:
    changed = []
    for name in PIN_FILES:
        path = root / name
        text = path.read_text(encoding="utf-8")
        for _, (old, new) in digests.items():
            if old != new and old in text:
                text = text.replace(old, new)
                changed.append(name)
        path.write_text(text, encoding="utf-8", newline="")
    return sorted(set(changed))


def _regenerate(root: Path) -> None:
    environment = os.environ | {"PYTHONPATH": f"{root / 'src'}{os.pathsep}{root}"}
    subprocess.run(
        [sys.executable, "tools/run_module17_validation.py", "--root", str(root)],
        cwd=root,
        env=environment,
        check=True,
        stdout=subprocess.DEVNULL,
    )


def _rows_by_system(text: str) -> tuple[str, list[str], list[str]]:
    """Header, C1-C3 lines and butane lines of a record, in file order."""

    lines = text.splitlines(keepends=True)
    index = lines[0].rstrip("\r\n").split(",").index("system_id")
    core, butanes = [], []
    for line in lines[1:]:
        (core if next(csv.reader([line]))[index] in C1_C3 else butanes).append(line)
    return lines[0], core, butanes


def run(root: Path, provisional: bool) -> dict[str, Any]:
    values = read_values(root / VALUES, provisional)
    for name in DATABASE_FILES:
        if not (root / name).exists():
            raise AdmissionError(f"missing {name}")
    if _sha256(root / DATABASE_FILES[0]) != _sha256(root / DATABASE_FILES[1]):
        raise AdmissionError("the two component-property CSVs differ before admission.")
    protected = (DATABASE_FILES[0], RECORD, SUMMARY, GOLDEN)
    before = {name: _sha256(root / name) for name in protected}
    committed_record = (root / RECORD).read_text(encoding="utf-8")
    committed_summary = json.loads((root / SUMMARY).read_text(encoding="utf-8"))
    header, committed_core, committed_butanes = _rows_by_system(committed_record)
    if committed_butanes:
        raise AdmissionError("the committed record already holds butane rows.")

    # 1. The C1-C3 record as this machine computes it, before admission. Floating
    # point can differ in the last digits between machines, so the identity
    # check below compares two runs on the same machine.
    _regenerate(root)
    _, reference_core, _ = _rows_by_system((root / RECORD).read_text(encoding="utf-8"))
    reproduces = reference_core == committed_core

    # 2. Admit the rows and regenerate with the butane data file.
    rows = database_rows(values, provisional)
    for name in DATABASE_FILES:
        append_rows(root / name, rows)
    if not provisional:
        extend_source_tables(root / "tests/test_component_database.py", values)
    _regenerate(root)
    _, admitted_core, butane_lines = _rows_by_system(
        (root / RECORD).read_text(encoding="utf-8")
    )
    if admitted_core != reference_core:
        raise AdmissionError(
            "admitting the butanes changed the C1-C3 rows computed on this machine."
        )
    if len(butane_lines) != 36:
        raise AdmissionError(f"expected 36 butane rows, found {len(butane_lines)}.")

    # 3. Keep the committed C1-C3 rows and summary entries exactly; add the
    # butane rows and summaries computed now.
    regenerated_summary = json.loads((root / SUMMARY).read_text(encoding="utf-8"))
    summary = dict(committed_summary)
    summary["systems"] = list(committed_summary["systems"]) + [
        system
        for system in regenerated_summary["systems"]
        if system["system_id"] not in C1_C3
    ]
    summary["butane_source"] = regenerated_summary["butane_source"]
    (root / RECORD).write_text(
        header + "".join(committed_core) + "".join(butane_lines),
        encoding="utf-8",
        newline="",
    )
    (root / SUMMARY).write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )

    after = {name: _sha256(root / name) for name in protected}
    if c1_c3_rows(root / RECORD) != [header, *committed_core]:
        raise AdmissionError("the written record's C1-C3 rows differ from master.")
    if after[GOLDEN] != before[GOLDEN]:
        raise AdmissionError("the golden master changed.")
    pinned = refresh_pins(
        root, {name: (before[name], after[name]) for name in protected}
    )
    return {
        "mode": "provisional dry run" if provisional else "final (Table 5)",
        "c1_c3_rows_identical_to_master": True,
        "c1_c3_rows_unchanged_by_admission_on_this_machine": True,
        "committed_c1_c3_rows_reproduce_bit_for_bit_on_this_machine": reproduces,
        "golden_master_unchanged": True,
        "hashes": {
            name: {"before": before[name], "after": after[name]} for name in protected
        },
        "pins_refreshed_in": pinned,
        "butane_source": summary["butane_source"],
        "systems": [
            system for system in summary["systems"] if system["system_id"] not in C1_C3
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--provisional", action="store_true")
    parser.add_argument("--report", type=Path, help="also write the result as JSON")
    arguments = parser.parse_args()
    try:
        report = run(arguments.root.resolve(), arguments.provisional)
    except AdmissionError as error:
        print(f"Not admitted: {error}")
        return 2
    text = json.dumps(report, indent=2, sort_keys=True)
    if arguments.report:
        arguments.report.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
