"""Every number in docs/STATE_OF_OPENPHASE.md is recomputed here.

The page is written for a faculty reader, so each quoted value comes from the
protected validation record, a committed study file or the engine.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from pvt_phase_simulator.eos.critical_point import solve_mixture_critical_point
from pvt_phase_simulator.eos.volume_translation import ANCHORED_SHIFTS
from pvt_phase_simulator_ui.adapters import validate_scientific_inputs
from pvt_phase_simulator_ui.learn import LABS
from tools import engine_fingerprint
from tools import fit_volume_translation as fit

ROOT = Path(__file__).resolve().parents[1]
DOC = " ".join(
    (ROOT / "docs/STATE_OF_OPENPHASE.md").read_text(encoding="utf-8").split()
)
SUMMARY = ROOT / "docs/validation/module17_vle_validation_summary.json"
INVESTIGATIONS = ROOT / "docs/investigations"
WORDS = {3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}


def _rows(name: str) -> list[dict[str, str]]:
    with (INVESTIGATIONS / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _metrics(system: str, kind: str) -> dict[str, object]:
    systems = json.loads(SUMMARY.read_text(encoding="utf-8"))["systems"]
    record = next(item for item in systems if item["system_id"] == system)
    return dict(record[f"production_selected_{kind}_metrics"])


def test_the_validation_table() -> None:
    c2_bubble, c2_dew = _metrics("ch4_c2", "bubble"), _metrics("ch4_c2", "dew")
    c3_bubble, c3_dew = _metrics("ch4_c3", "bubble"), _metrics("ch4_c3", "dew")
    c2 = (
        f"| methane + ethane | {float(str(c2_bubble['pressure_aard_percent'])):.2f} % "
        f"AARD at {c2_bubble['success_count']} of {c2_bubble['source_count']} states | "
        f"{c2_dew['success_count']} of {c2_dew['source_count']} states, "
        f"{float(str(c2_dew['pressure_aard_percent'])):.2f} % AARD |"
    )
    c3 = (
        f"| methane + propane | {float(str(c3_bubble['pressure_aard_percent'])):.2f} % "
        f"AARD at {c3_bubble['success_count']} of {c3_bubble['source_count']} states | "
        f"{c3_dew['success_count']} of {c3_dew['source_count']} states |"
    )
    assert c2 in DOC, c2
    assert c3 in DOC, c3


def test_the_dew_composition_claim() -> None:
    rows = [
        row for row in _rows("dew_conditioning.csv") if row["system_id"] == "ch4_c3"
    ]
    within = sum(
        abs(float(row["vapor_difference_over_uncertainty"])) <= 1.0 for row in rows
    )
    assert f"at {within} of {len(rows)} states" in DOC


def test_the_pure_component_numbers() -> None:
    rows = [
        row
        for row in _rows("pure_saturation_comparison.csv")
        if row["model_status"] == "converged"
    ]
    quoted = []
    for component in ("methane", "ethane", "propane"):
        group = [row for row in rows if row["component_id"] == component]
        errors = [abs(float(row["pressure_relative_error"])) for row in group]
        quoted.append(f"{100 * sum(errors) / len(errors):.2f} % ({component})")
    text = f"{quoted[0]}, {quoted[1]} and {quoted[2]} AARD"
    assert text in DOC, text
    worst = max(abs(float(row["liquid_density_relative_error"])) for row in rows)
    assert f"off by up to {100 * worst:.2f} %" in DOC
    lowest = min(float(row["reduced_temperature"]) for row in rows)
    assert f"down to T_r = {lowest:g}" in DOC


def test_the_certified_critical_point() -> None:
    mixture = validate_scientific_inputs((50.0, 0.0, 50.0), 300.0, 5.0).mixture()
    result = solve_mixture_critical_point(mixture, 320.0, 8.5e6)
    assert result.status.value == "converged"
    assert result.temperature_k is not None and result.pressure_pa is not None
    quoted = f"{result.temperature_k:.2f} K and {result.pressure_pa / 1e6:.3f} MPa"
    assert quoted in DOC, quoted


def test_the_fingerprint_and_lab_counts() -> None:
    assert f"fingerprint of {len(engine_fingerprint.cases())} engine results" in DOC
    assert f"{WORDS[len(LABS)]} teaching labs" in DOC


def test_the_kij_and_volume_translation_numbers() -> None:
    fits = json.loads(
        (INVESTIGATIONS / "kij_study_fit.json").read_text(encoding="utf-8")
    )
    kij = fits["fits"]["ch4_c3"]["optimum"]
    assert f"fitted kij of {kij:+.4f} for methane + propane" in DOC
    shifts = {key: item.shift_m3_per_mol for key, item in ANCHORED_SHIFTS.items()}
    summary = fit.summary(
        fit.held_out_rows(_rows("pure_saturation_comparison.csv"), shifts)
    )
    methane = summary["methane"]
    quoted = (
        f"from {methane['liquid_error_before_aard_percent']:.2f} % to "
        f"{methane['liquid_error_after_aard_percent']:.2f} % (methane)"
    )
    assert quoted in DOC, quoted
    assert (
        methane["liquid_error_after_max_percent"]
        > methane["liquid_error_before_max_percent"]
    )


@pytest.mark.parametrize("phrase", ("May et al. (2015)", "Yang & Richter (2025)"))
def test_sources_are_named(phrase: str) -> None:
    assert phrase in DOC
