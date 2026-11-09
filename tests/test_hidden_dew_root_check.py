"""The committed hidden-dew-root check covers and confirms every ambiguous state.

``tools/run_hidden_dew_root_check.py`` confirms, by a route independent of the
production verdict, that each Module 17 dew state carrying
``HIDDEN_SATURATION_ROOT`` really has two PR dew roots. These tests check that
the committed output covers exactly those states, that each one is confirmed,
and that the confirming route reproduces with the engine for the states whose
second root P8 found beside a failed walk step.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from pvt_phase_simulator.experimental_validation import REQUIRED_SYSTEMS
from pvt_phase_simulator.fluid_models import METHANE, FluidMixture, MixtureComponent
from tools import run_hidden_dew_root_check as tool

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs/validation/module17_vle_validation.csv"
#: CH4+C2 states whose upper root P8 found by its bounded Newton solve.
P8_STATES = (
    "may2015_ch4_c2_008",
    "may2015_ch4_c2_009",
    "may2015_ch4_c2_013",
    "may2015_ch4_c2_017",
)


def _rows() -> dict[str, dict[str, str]]:
    with (ROOT / tool.OUTPUT).open(encoding="utf-8", newline="") as stream:
        return {row["source_point_id"]: row for row in csv.DictReader(stream)}


def _pressures(text: str) -> list[float]:
    return [float(value) * 1e6 for value in text.split("|")] if text else []


def test_the_check_covers_exactly_the_hidden_root_states() -> None:
    with RECORD.open(encoding="utf-8", newline="") as stream:
        hidden = {
            row["source_point_id"]
            for row in csv.DictReader(stream)
            if "HIDDEN_SATURATION_ROOT" in json.loads(row["dew_diagnostic_codes"])
            # The check covers the required systems; admitted butane systems
            # get their own check (docs/BUTANES_ADMISSION_PLAN.md, step 6).
            and row["system_id"] in REQUIRED_SYSTEMS
        }
    assert set(_rows()) == hidden
    assert set(P8_STATES) <= hidden


def test_every_state_is_confirmed_by_a_named_route() -> None:
    for point, row in _rows().items():
        bracketed = _pressures(row["bracketed_roots_mpa"])
        isotherm = _pressures(row["isotherm_crossings_mpa"])
        branch = _pressures(row["dew_branch_crossings_mpa"])
        assert row["dew_status"] == "inconclusive", point
        assert row["confirmed_by"] == tool.route(bracketed, isotherm, branch), point
        assert row["confirmed_by"] != "not confirmed", point


@pytest.mark.parametrize("point", P8_STATES)
def test_p8_states_reproduce_with_the_engine(point: str) -> None:
    row = _rows()[point]
    mixture = FluidMixture(
        (
            MixtureComponent(METHANE, float(row["vapor_ch4"])),
            MixtureComponent(tool.HEAVY["ch4_c2"], 1.0 - float(row["vapor_ch4"])),
        )
    )
    temperature = float(row["temperature_k"])
    bracketed = tool.bracketed_roots(mixture, temperature)
    assert [f"{value / 1e6:.4f}" for value in bracketed] == (
        row["bracketed_roots_mpa"].split("|")
    )
    branch, stop = tool.branch_crossings(
        mixture, temperature, tool.BRANCH_START_K["ch4_c2"]
    )
    assert [f"{value / 1e6:.4f}" for value in branch] == (
        row["dew_branch_crossings_mpa"].split("|")
    )
    assert stop == row["dew_branch_stop"]
    # The production scan brackets only the lower root at these states, so
    # the second root is confirmed by a route that does not use the scan.
    assert len(bracketed) == 1
    assert row["confirmed_by"] in ("bubble isotherm", "dew branch")
