"""tools/compare_liquid_density.py on ThermoML-shaped fixtures.

TEST FIXTURES, NOT NEW SOURCES:
- the pure-propane states come from the owner-accepted reference file
  ``docs/investigations/pure_saturation_reference.csv`` (reference EOS
  values), reshaped as ThermoML;
- the binary state is SYNTHETIC: its density and molar masses are arbitrary
  test inputs that exercise the mass-density path, not measurements.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pytest

from pvt_phase_simulator.eos.mixing_rules import (
    calculate_peng_robinson_mixture_parameters,
)
from pvt_phase_simulator.eos.peng_robinson import calculate_compressibility_roots
from pvt_phase_simulator.eos.volume_translation import ANCHORED_SHIFTS
from pvt_phase_simulator.fluid_models import FluidMixture, MixtureComponent
from pvt_phase_simulator.physical_constants import UNIVERSAL_GAS_CONSTANT
from tools import compare_liquid_density as tool

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "docs/investigations/pure_saturation_reference.csv"
REDUCED = ("0.5", "0.7", "0.9")
METHANE_KEY = "VNWKTOKETHGBQD-UHFFFAOYSA-N"
PROPANE_KEY = "ATUOYWHBWRKTHZ-UHFFFAOYSA-N"


def _reference_rows() -> list[dict[str, str]]:
    with REFERENCE.open(encoding="utf-8", newline="") as stream:
        return [
            row
            for row in csv.DictReader(stream)
            if row["component_id"] == "propane"
            and row["reduced_temperature"] in REDUCED
        ]


def _variable(
    number: int, kind: str, label: str, org: int | None = None
) -> dict[str, Any]:
    identifier: dict[str, Any] = {"VariableType": {kind: label}}
    if org is not None:
        identifier["RegNum"] = {"nOrgNum": org}
    return {
        "nVarNumber": number,
        "VariableID": identifier,
        "VarPhaseID": {"eVarPhase": "Liquid"},
    }


def _property(name: str, phase: str = "Liquid") -> list[dict[str, Any]]:
    return [
        {
            "Property-MethodID": {
                "PropertyGroup": {"VolumetricProp": {"ePropName": name}}
            },
            "PropPhaseID": {"ePropPhase": phase},
        }
    ]


def fixture() -> dict[str, Any]:
    pure_rows = [
        {
            "VariableValue": [
                {"nVarNumber": 1, "nVarValue": row["temperature_k"]},
                {
                    "nVarNumber": 2,
                    "nVarValue": str(float(row["saturation_pressure_pa"]) / 1e3),
                },
            ],
            "PropertyValue": [{"nPropValue": row["liquid_molar_density_mol_m3"]}],
        }
        for row in _reference_rows()
    ]
    synthetic_binary = [
        {
            "VariableValue": [
                {"nVarNumber": 1, "nVarValue": "250"},
                {"nVarNumber": 2, "nVarValue": "10000"},
                {"nVarNumber": 3, "nVarValue": "0.3"},
            ],
            "PropertyValue": [
                {
                    "nPropValue": "500",
                    "CombinedUncertainty": {"nCombExpandUncertValue": "1"},
                }
            ],
        }
    ]
    return {
        "Citation": {
            "sTitle": "TEST FIXTURE (reference-EOS states and synthetic values)"
        },
        "Compound": [
            {"RegNum": {"nOrgNum": 1}, "sStandardInChIKey": METHANE_KEY},
            {"RegNum": {"nOrgNum": 3}, "sStandardInChIKey": PROPANE_KEY},
        ],
        "PureOrMixtureData": [
            {
                "nPureOrMixtureDataNumber": 1,
                "Component": [{"RegNum": {"nOrgNum": 3}}],
                "Property": _property("Molar density, mol/m3"),
                "Variable": [
                    _variable(1, "eTemperature", "Temperature, K"),
                    _variable(2, "ePressure", "Pressure, kPa"),
                ],
                "NumValues": pure_rows,
            },
            {
                "nPureOrMixtureDataNumber": 2,
                "Component": [{"RegNum": {"nOrgNum": 1}}, {"RegNum": {"nOrgNum": 3}}],
                "Property": _property("Mass density, kg/m3"),
                "Variable": [
                    _variable(1, "eTemperature", "Temperature, K"),
                    _variable(2, "ePressure", "Pressure, kPa"),
                    _variable(3, "eComponentComposition", "Mole fraction", org=1),
                ],
                "NumValues": synthetic_binary,
            },
            {
                "nPureOrMixtureDataNumber": 3,
                "Component": [{"RegNum": {"nOrgNum": 3}}],
                "Property": _property("Speed of sound, m/s"),
                "Variable": [],
                "NumValues": [],
            },
        ],
    }


SYNTHETIC_MASSES = {"Methane": 16.0, "Propane": 44.0}


def test_parsing_and_skips() -> None:
    states, skipped = tool.read_states(fixture(), SYNTHETIC_MASSES)
    assert len(states) == 4
    assert skipped == [
        "dataset 3: property 'Speed of sound, m/s' is not a liquid density"
    ]
    binary = states[-1]
    assert [c.name for c in binary.components] == ["Methane", "Propane"]
    assert binary.mole_fractions == (0.3, 0.7)
    grams = 0.3 * 16.0 + 0.7 * 44.0
    assert binary.molar_density_mol_m3 == pytest.approx(500 / (grams * 1e-3))
    assert binary.uncertainty_mol_m3 == pytest.approx(1 / (grams * 1e-3))
    assert binary.pressure_pa == 1.0e7


def test_mass_density_without_molar_masses_is_skipped_with_a_reason() -> None:
    states, skipped = tool.read_states(fixture())
    assert len(states) == 3
    assert "needs --molar-mass for every component" in skipped[0]


def _independent(state: tool.DensityState) -> tuple[float, float]:
    mixture = FluidMixture(
        tuple(
            MixtureComponent(c, x)
            for c, x in zip(state.components, state.mole_fractions, strict=True)
        )
    )
    parameters = calculate_peng_robinson_mixture_parameters(
        mixture, state.temperature_k, state.pressure_pa
    )
    z = min(
        root
        for root in calculate_compressibility_roots(parameters.A_mix, parameters.B_mix)
        if root > parameters.B_mix
    )
    volume = z * UNIVERSAL_GAS_CONSTANT * state.temperature_k / state.pressure_pa
    shift = sum(
        x * ANCHORED_SHIFTS[c.name.casefold()].shift_m3_per_mol
        for c, x in zip(state.components, state.mole_fractions, strict=True)
    )
    return 1.0 / volume, 1.0 / (volume - shift)


def test_every_density_is_recomputed_independently() -> None:
    states, _ = tool.read_states(fixture(), SYNTHETIC_MASSES)
    for state in states:
        row = tool.compare_state(state)
        plain, shifted = _independent(state)
        assert float(str(row["pr_molar_density_mol_m3"])) == pytest.approx(
            plain, rel=1e-12
        )
        assert float(str(row["translated_molar_density_mol_m3"])) == pytest.approx(
            shifted, rel=1e-12
        )
        measured = state.molar_density_mol_m3
        assert float(str(row["pr_relative_error"])) == pytest.approx(
            (plain - measured) / measured
        )


def test_the_shift_helps_at_low_temperature_and_hurts_near_critical() -> None:
    states, _ = tool.read_states(fixture())
    rows = {state.temperature_k: tool.compare_state(state) for state in states}
    low, anchor, high = (rows[t] for t in sorted(rows))
    for row, better in ((low, True), (high, False)):
        before = abs(float(str(row["pr_relative_error"])))
        after = abs(float(str(row["translated_relative_error"])))
        assert (after < before) is better
    assert abs(float(str(anchor["translated_relative_error"]))) < 1e-3
    summary = tool.summarize(list(rows.values()))
    assert summary["compared"] == 3
    assert summary["worse_after_shift"] == 1
    text = tool.summary_markdown(list(rows.values()), [], "fixture.json", "0" * 64, {})
    assert "The shift makes the error worse at 1 of 3 states." in text
