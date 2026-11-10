"""Every number in Lab 5 (liquid density and volume translation) is recomputed.

Parts A and C are worked in the app, so each value comes from the app's own
flash boundary (``run_validated_flash``) and the same table function Overview
shows (``phase_volume_rows``). Part B reads the committed fit table, which
``tests/test_volume_translation.py`` regenerates from the engine.
"""

from __future__ import annotations

import csv
from functools import cache
from pathlib import Path

from pvt_phase_simulator.eos.flash import FlashPhaseState, TwoPhaseFlashResult
from pvt_phase_simulator.eos.volume_translation import ANCHORED_SHIFTS
from pvt_phase_simulator.physical_constants import UNIVERSAL_GAS_CONSTANT
from pvt_phase_simulator_ui.adapters import run_validated_flash
from pvt_phase_simulator_ui.learn import LABS
from pvt_phase_simulator_ui.volume_translation_view import phase_volume_rows

ROOT = Path(__file__).resolve().parents[1]
LAB = (ROOT / "docs" / "teaching" / "LAB_05_LIQUID_DENSITY.md").read_text(
    encoding="utf-8"
)
STUDENT, _, KEY_TEXT = LAB.partition("## Instructor answer key")
STUDENT = " ".join(STUDENT.split())
KEY = " ".join(KEY_TEXT.split())
FIT = ROOT / "docs" / "investigations" / "volume_translation_fit.csv"

PART_A = ((0.0, 0.0, 100.0), 258.923, 1.0)
PART_C = ((50.0, 0.0, 50.0), 250.0, 5.0)
PART_B_REDUCED = (0.5, 0.7, 0.9, 0.98)
VOLUME = "PR molar volume (cm³/mol)"
TRANSLATED_VOLUME = "Translated molar volume (cm³/mol)"
DENSITY = "PR density (mol/m³)"
TRANSLATED_DENSITY = "Translated density (mol/m³)"


def _signed(value: float) -> str:
    return f"{value:+.2f}".replace("-", "−")


def _minus(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}f}".replace("-", "−")


@cache
def _flash(case: tuple) -> TwoPhaseFlashResult:  # type: ignore[type-arg]
    composition, temperature, pressure = case
    return run_validated_flash(composition, temperature, pressure)[1]


def _shift_cm3(component_id: str) -> float:
    return ANCHORED_SHIFTS[component_id].shift_m3_per_mol * 1e6


def test_the_background_quotes_the_shipped_shifts() -> None:
    quoted = (
        f"methane {_minus(_shift_cm3('methane'))}, ethane "
        f"{_minus(_shift_cm3('ethane'))} and propane {_minus(_shift_cm3('propane'))} "
        "cm³/mol"
    )
    assert quoted in STUDENT, quoted
    assert f"R = {UNIVERSAL_GAS_CONSTANT!r} J/(mol·K)" in STUDENT


def test_part_a_pure_propane_liquid() -> None:
    result = _flash(PART_A)
    assert result.phase_state is FlashPhaseState.SINGLE_PHASE
    (row,) = phase_volume_rows(result)
    assert row["Phase"] == "Single phase"
    volume, translated = float(row[VOLUME]), float(row[TRANSLATED_VOLUME])
    density, translated_density = float(row[DENSITY]), float(row[TRANSLATED_DENSITY])
    assert f"| Molar volume (cm³/mol) | {volume:.2f} | {translated:.2f} |" in KEY
    assert (
        f"| Molar density (mol/m³) | {density:.0f} | {translated_density:.0f} |" in KEY
    )
    z_factor = 1.0e6 * volume * 1e-6 / (UNIVERSAL_GAS_CONSTANT * 258.923)
    assert result.single_phase_root is not None
    assert abs(z_factor - result.single_phase_root) < 1e-12
    assert f"Z = Pv/(RT) = {z_factor:.5f}" in KEY
    added = translated - volume
    assert f"adds {-_shift_cm3('propane'):.3f} cm³/mol" in KEY
    assert abs(added + _shift_cm3("propane")) < 1e-9
    fall = 100 * (1 - translated_density / density)
    assert f"density falls by {fall:.2f} %" in KEY


def _fit_rows() -> dict[float, dict[str, str]]:
    with FIT.open(encoding="utf-8", newline="") as stream:
        return {
            float(row["reduced_temperature"]): row
            for row in csv.DictReader(stream)
            if row["component_id"] == "propane"
        }


def test_part_b_saturation_table() -> None:
    rows = _fit_rows()
    for reduced in PART_B_REDUCED:
        row = rows[reduced]
        before = 100 * float(row["liquid_error_before"])
        after = 100 * float(row["liquid_error_after"])
        line = (
            f"| {reduced:.2f} | {float(row['reference_liquid_density_mol_m3']):.0f} | "
            f"{float(row['model_liquid_density_mol_m3']):.0f} | "
            f"{float(row['translated_liquid_density_mol_m3']):.0f} | "
            f"{_signed(before)} % | {_signed(after)} % |"
        )
        assert line in KEY, line
    anchor = rows[0.7]
    assert anchor["role"] == "anchor"
    assert abs(float(anchor["liquid_error_after"])) < 1e-12
    near = rows[0.98]
    assert (
        float(near["liquid_error_before"]) < 0 < float(rows[0.5]["liquid_error_before"])
    )
    assert (
        f"from {_signed(100 * float(near['liquid_error_before']))} % to "
        f"{_signed(100 * float(near['liquid_error_after']))} % at T_r = 0.98"
    ) in KEY


def test_part_c_two_phase_mixture() -> None:
    result = _flash(PART_C)
    assert result.phase_state is FlashPhaseState.TWO_PHASE
    assert result.liquid_phase is not None and result.vapor_phase is not None
    assert result.liquid_fraction is not None
    assert f"The liquid fraction ({result.liquid_fraction:.4f})" in KEY
    rows = phase_volume_rows(result)
    assert [row["Phase"] for row in rows] == ["Liquid", "Vapor"]
    falls = []
    for row, phase in zip(rows, (result.liquid_phase, result.vapor_phase), strict=True):
        line = (
            f"| {row['Phase']} | {100 * phase.composition[0]:.2f} | "
            f"{float(row[VOLUME]):.2f} | {float(row[TRANSLATED_VOLUME]):.2f} | "
            f"{float(row[DENSITY]):.0f} | {float(row[TRANSLATED_DENSITY]):.0f} |"
        )
        assert line in KEY, line
        c_mix = phase.composition[0] * _shift_cm3("methane") + phase.composition[
            2
        ] * _shift_cm3("propane")
        assert abs(float(row[TRANSLATED_VOLUME]) - float(row[VOLUME]) + c_mix) < 1e-9
        falls.append(100 * (1 - float(row[TRANSLATED_DENSITY]) / float(row[DENSITY])))
        if row["Phase"] == "Liquid":
            x1, x3 = phase.composition[0], phase.composition[2]
            assert (
                f"c_mix = {x1:.4f} × ({_minus(_shift_cm3('methane'))}) + {x3:.4f} × "
                f"({_minus(_shift_cm3('propane'))}) = {_minus(c_mix)} cm³/mol"
            ) in KEY
            assert f"volume grows by {-c_mix:.3f} cm³/mol" in KEY
        else:
            assert f"Vapour: c_mix = {_minus(c_mix)} cm³/mol" in KEY
    assert (
        f"the liquid density falls by {falls[0]:.2f} %, the vapour density by only "
        f"{falls[1]:.2f} %"
    ) in KEY


def test_part_c_the_switch_changes_no_phase_result() -> None:
    # The Overview table is the only thing the switch adds; the flash result
    # it reads is the same object either way (tests/test_volume_translation.py
    # checks the app session state across the switch).
    first = _flash(PART_C)
    again = run_validated_flash(*PART_C)[1]
    assert repr(again) == repr(first)


def test_the_student_inputs_match_the_key() -> None:
    assert "pure propane (0 / 0 / 100 mol %), 258.923 K (T_r = 0.70) and 1.0 MPa" in (
        STUDENT
    )
    assert "50 / 0 / 50 mol % methane / propane, 250 K and 5.0 MPa" in STUDENT
    assert "T_r = 0.50, 0.70, 0.90 and 0.98" in STUDENT


def test_learn_mode_links_the_lab() -> None:
    assert (
        "Lab 5: Liquid density and volume translation (propane, methane + propane)",
        "LAB_05_LIQUID_DENSITY.md",
    ) in (LABS)
