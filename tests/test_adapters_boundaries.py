"""Exact boundaries and kij pair logic of the input adapter (mutation testing).

The surviving mutants of ``adapters.py`` were mostly in the kij pair logic and
at the exact edges of the supported range; these pin both.
"""

from __future__ import annotations

import pytest

from pvt_phase_simulator_ui.adapters import (
    KIJ_MAXIMUM,
    KIJ_MINIMUM,
    MAXIMUM_PRESSURE_PA,
    MAXIMUM_TEMPERATURE_K,
    MINIMUM_PRESSURE_PA,
    MINIMUM_TEMPERATURE_K,
    InputValidationError,
    binary_interaction_assumption,
    effective_kij,
    pairs_present,
    validate_scientific_inputs,
)
from pvt_phase_simulator_ui.units import PressureUnit

KIJ = (0.01, 0.02, 0.03)


@pytest.mark.parametrize(
    ("fractions", "present"),
    (
        ((0.5, 0.5, 0.0), (True, False, False)),
        ((0.5, 0.0, 0.5), (False, True, False)),
        ((0.0, 0.5, 0.5), (False, False, True)),
        ((1 / 3, 1 / 3, 1 / 3), (True, True, True)),
        ((1.0, 0.0, 0.0), (False, False, False)),
        ((0.0, 0.0, 1.0), (False, False, False)),
    ),
)
def test_pairs_present_and_effective_kij(
    fractions: tuple[float, float, float], present: tuple[bool, bool, bool]
) -> None:
    assert pairs_present(fractions) == present
    expected = tuple(
        value if here else 0.0 for value, here in zip(KIJ, present, strict=True)
    )
    assert effective_kij(fractions, KIJ) == expected


def test_the_kij_statement_names_only_pairs_in_the_mixture() -> None:
    assert (
        binary_interaction_assumption((0.5, 0.0, 0.5), KIJ)
        == "user-supplied kij: C1–C3 = +0.02"
    )
    assert (
        binary_interaction_assumption((0.5, 0.0, 0.5), (0.01, 0.0, 0.03)) == "kij = 0"
    )
    assert binary_interaction_assumption((1 / 3, 1 / 3, 1 / 3), KIJ) == (
        "user-supplied kij: C1–C2 = +0.01, C1–C3 = +0.02, C2–C3 = +0.03"
    )


def test_engine_mapping_holds_only_present_pairs_both_ways() -> None:
    inputs = validate_scientific_inputs((50, 0, 50), 300.0, 5.0, kij=KIJ)
    assert inputs.uses_kij
    assert inputs.binary_interactions() == {
        ("Methane", "Propane"): 0.02,
        ("Propane", "Methane"): 0.02,
    }
    absent = validate_scientific_inputs((50, 0, 50), 300.0, 5.0, kij=(0.05, 0.0, 0.05))
    assert not absent.uses_kij
    assert absent.binary_interactions() is None


def test_the_supported_range_edges_are_inclusive() -> None:
    for temperature in (MINIMUM_TEMPERATURE_K, MAXIMUM_TEMPERATURE_K):
        for pressure in (MINIMUM_PRESSURE_PA, MAXIMUM_PRESSURE_PA):
            inputs = validate_scientific_inputs(
                (50, 0, 50),
                temperature,
                pressure,
                pressure_unit=PressureUnit.PA,
                supported_range=True,
            )
            assert (inputs.temperature_k, inputs.pressure_pa) == (temperature, pressure)
    assert (MINIMUM_TEMPERATURE_K, MAXIMUM_TEMPERATURE_K) == (50.0, 1000.0)
    assert (MINIMUM_PRESSURE_PA, MAXIMUM_PRESSURE_PA) == (1.0, 1.0e9)


def test_without_the_supported_range_only_positive_values_are_required() -> None:
    inputs = validate_scientific_inputs((50, 0, 50), 20.0, 1e-6)
    assert inputs.temperature_k == 20.0
    with pytest.raises(InputValidationError, match="Temperature"):
        validate_scientific_inputs((50, 0, 50), 0.0, 5.0)
    with pytest.raises(InputValidationError, match="Pressure"):
        validate_scientific_inputs((50, 0, 50), 300.0, 0.0)


def test_kij_edges_are_inclusive() -> None:
    assert (KIJ_MINIMUM, KIJ_MAXIMUM) == (-0.10, 0.20)
    for value in (KIJ_MINIMUM, KIJ_MAXIMUM):
        inputs = validate_scientific_inputs(
            (40, 30, 30), 300.0, 5.0, kij=(value, value, value)
        )
        assert inputs.kij == (value, value, value)
    with pytest.raises(InputValidationError):
        validate_scientific_inputs((40, 30, 30), 300.0, 5.0, kij=(0.0, 0.0))


@pytest.mark.parametrize(
    ("composition", "message"),
    (
        ((50.0, 50.0), "Exactly Methane, Ethane, and Propane are required."),
        ((150.0, -25.0, -25.0), "Composition values cannot be negative."),
        ((101.0, 0.0, 0.0), "Each composition value must not exceed 100 mol %."),
        ((100.0, 0.0, 0.0), None),
    ),
)
def test_composition_checks(
    composition: tuple[float, ...], message: str | None
) -> None:
    if message is None:
        assert validate_scientific_inputs(composition, 300.0, 5.0).mole_fractions == (
            1.0,
            0.0,
            0.0,
        )
        return
    with pytest.raises(InputValidationError) as refused:
        validate_scientific_inputs(composition, 300.0, 5.0)
    assert str(refused.value) == message
