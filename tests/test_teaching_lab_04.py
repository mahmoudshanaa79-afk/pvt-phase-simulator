"""Every number in Lab 4 (what kij does) is recomputed from the engine here.

The lab is worked in the app, so each value is computed through the app's own
input boundary (``validate_scientific_inputs`` with the kij field) and the same
engine call the Phase Envelope page makes. ``tests/test_app_kij_input.py``
shows that the page returns exactly these engine results.
"""

from __future__ import annotations

import csv
import json
from functools import cache
from pathlib import Path

import pytest

from pvt_phase_simulator.eos.saturation_pressure import (
    SaturationKind,
    SaturationPressureResult,
    calculate_saturation_pressure,
)
from pvt_phase_simulator_ui.adapters import KIJ_FITTED_C1_C3, validate_scientific_inputs

ROOT = Path(__file__).resolve().parents[1]
LAB = (ROOT / "docs" / "teaching" / "LAB_04_BINARY_INTERACTION.md").read_text(
    encoding="utf-8"
)
STUDENT, _, KEY_TEXT = LAB.partition("## Instructor answer key")
STUDENT = " ".join(STUDENT.split())
KEY = " ".join(KEY_TEXT.split())
FIT = json.loads(
    (ROOT / "docs" / "investigations" / "kij_study_fit.json").read_text(
        encoding="utf-8"
    )
)["fits"]["ch4_c3"]
STUDY = ROOT / "docs" / "investigations" / "kij_study.csv"
RECORD = ROOT / "docs" / "validation" / "module17_vle_validation.csv"

TEMPERATURE_K = 243.62
#: State id -> (liquid CH4 mol %, measured pressure MPa).
STATES = {
    "009": (7.10, 0.891),
    "010": (34.42, 3.909),
    "012": (55.65, 6.402),
    "014": (69.61, 7.943),
}
PXY_METHANE = (10.0, 30.0, 50.0, 65.0)
DEW_STATE = ("013", 92.21)
KIJ_VALUES = (0.0, KIJ_FITTED_C1_C3)


def _signed(value: float) -> str:
    return f"{value:+.2f}".replace("-", "−")


@cache
def _solve(methane: float, kij: float, kind: SaturationKind) -> SaturationPressureResult:
    inputs = validate_scientific_inputs(
        (methane, 0.0, 100.0 - methane), TEMPERATURE_K, 5.0, kij=(0.0, kij, 0.0)
    )
    return calculate_saturation_pressure(
        inputs.mixture(),
        TEMPERATURE_K,
        kind,
        binary_interactions=inputs.binary_interactions(),
    )


def _bubble(methane: float, kij: float) -> SaturationPressureResult:
    result = _solve(methane, kij, SaturationKind.BUBBLE_POINT)
    assert result.status.value == "converged", (methane, kij)
    assert result.pressure_pa is not None
    return result


def _pressure(methane: float, kij: float) -> float:
    pressure = _bubble(methane, kij).pressure_pa
    assert pressure is not None
    return pressure / 1e6


def test_the_fitted_kij_is_the_study_value() -> None:
    assert round(FIT["optimum"], 4) == KIJ_FITTED_C1_C3 == 0.0021
    assert f"kij = +{KIJ_FITTED_C1_C3}" in STUDENT
    assert f"enter **{KIJ_FITTED_C1_C3}** for the C1–C3 pair" in STUDENT


def test_part_a_states_are_the_measured_record() -> None:
    with RECORD.open(encoding="utf-8", newline="") as stream:
        rows = {
            row["source_point_id"]: row
            for row in csv.DictReader(stream)
            if row["system_id"] == "ch4_c3"
        }
    for state, (methane, pressure) in STATES.items():
        row = rows[f"may2015_ch4_c3_{state}"]
        assert float(row["temperature_k"]) == TEMPERATURE_K
        assert float(row["experimental_pressure_pa"]) / 1e6 == pressure
        assert json.loads(row["liquid_mole_fractions"])[0] * 100 == pytest.approx(
            methane, abs=1e-9
        )
        assert f"| {state} | {methane:.2f} | {pressure} |" in STUDENT


def test_part_a_bubble_pressures_and_errors() -> None:
    errors = {}
    for state, (methane, measured) in STATES.items():
        cells = [state, f"{measured}"]
        for kij in KIJ_VALUES:
            pressure = _pressure(methane, kij)
            error = 100.0 * (pressure - measured) / measured
            errors[(state, kij)] = error
            cells += [f"{pressure:.4f}", f"{_signed(error)} %"]
        assert "| " + " | ".join(cells) + " |" in KEY, cells
    fitted = KIJ_FITTED_C1_C3
    assert all(_pressure(m, fitted) > _pressure(m, 0.0) for m, _ in STATES.values())
    helped = [s for s in STATES if abs(errors[(s, fitted)]) < abs(errors[(s, 0.0)])]
    assert helped == ["009", "010", "012"]
    assert errors[("014", 0.0)] > 0.0
    assert all(errors[(s, 0.0)] < 0.0 for s in helped)
    assert "helps at 009, 010 and 012" in KEY and "hurts at 014" in KEY


def test_part_a_own_best_kij_drifts_with_pressure() -> None:
    best = {
        item["point_id"][-3:]: item["best_kij"] for item in FIT["per_state_best_kij"]
    }
    assert best["009"] < best["014"]
    assert "drifting with pressure along this isotherm" in KEY


def test_part_b_pxy_table_and_statements() -> None:
    rises, shifts = [], []
    for methane in PXY_METHANE:
        cells = [f"{methane:.0f}"]
        values = {}
        for kij in KIJ_VALUES:
            result = _bubble(methane, kij)
            pressure = _pressure(methane, kij)
            vapour = 100.0 * result.incipient_composition[0]
            values[kij] = (pressure, vapour)
            cells += [f"{pressure:.4f}", f"{vapour:.2f}"]
        assert "| " + " | ".join(cells) + " |" in KEY, cells
        zero, fitted = values[0.0], values[KIJ_FITTED_C1_C3]
        rises.append(100.0 * (fitted[0] - zero[0]) / zero[0])
        shifts.append(abs(fitted[1] - zero[1]))
    assert round(min(rises), 1) == 0.4 and round(max(rises), 1) == 0.8
    assert "rises by about 0.4 % to 0.8 %" in KEY
    assert round(max(shifts), 1) <= 0.1
    assert "at most about 0.1 mol %" in KEY


def test_part_b_boundary_code_at_65_mol_percent() -> None:
    codes = [item.code for item in _bubble(65.0, KIJ_FITTED_C1_C3).diagnostics]
    assert "BOUNDARY_SATURATION_ROOT" in codes
    assert "At 65 mol % the fitted-kij bubble point carries" in KEY


def test_part_c_the_dew_state_is_ambiguous_at_both_kij() -> None:
    state, methane = DEW_STATE
    with RECORD.open(encoding="utf-8", newline="") as stream:
        row = next(
            r
            for r in csv.DictReader(stream)
            if r["source_point_id"] == f"may2015_ch4_c3_{state}"
        )
    assert json.loads(row["vapor_mole_fractions"])[0] * 100 == pytest.approx(
        methane, abs=1e-9
    )
    for kij in KIJ_VALUES:
        result = _solve(methane, kij, SaturationKind.DEW_POINT)
        assert result.status.value == "inconclusive", kij
        assert result.pressure_pa is None
        assert "MULTIPLE_SATURATION_ROOTS" in [item.code for item in result.diagnostics]
    assert "*inconclusive* with `MULTIPLE_SATURATION_ROOTS`" in KEY


def test_part_c_ambiguous_counts_come_from_the_study() -> None:
    with STUDY.open(encoding="utf-8", newline="") as stream:
        rows = [
            r
            for r in csv.DictReader(stream)
            if r["system_id"] == "ch4_c3" and r["kind"] == "dew"
        ]

    def ambiguous(kij: float) -> tuple[int, int]:
        row = next(r for r in rows if float(r["kij"]) == kij)
        return int(row["hidden_root"]) + int(row["multiple_roots"]), int(row["states"])

    zero = ambiguous(0.0)
    fitted = ambiguous(FIT["optimum"])
    assert zero == fitted == (20, 23)
    assert (
        f"{zero[0]} of {zero[1]} CH4+C3 dew states ambiguous at kij = 0 and "
        f"{fitted[0]} of {fitted[1]} at the fitted kij" in KEY
    )


def test_no_dew_pressure_is_quoted() -> None:
    assert "This lab quotes no dew pressure where the solver reports" in STUDENT
    lowered = KEY.lower()
    assert "dew point is" not in lowered
    assert "dew pressure is" not in lowered
