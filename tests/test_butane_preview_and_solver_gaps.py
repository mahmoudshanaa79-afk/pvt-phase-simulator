"""Evidence behind docs/NEW_COMPONENTS_PROPOSAL.md, recomputed from the engine."""

from __future__ import annotations

import csv
import statistics
from pathlib import Path

import pytest

from pvt_phase_simulator.eos.saturation_pressure import (
    SaturationKind,
    SaturationStatus,
    calculate_saturation_pressure,
)
from pvt_phase_simulator.experimental_validation import COMPONENT_OBJECTS
from pvt_phase_simulator.fluid_models import FluidMixture, MixtureComponent
from tests.test_experimental_validation import _source_dataset, _thermoml_fixture
from tools import extract_may_2015_thermoml as extractor
from tools.run_butane_preview import PROVISIONAL_COMPONENTS, _mixture, solve_point
from tools.run_dew_uniqueness_audit import isotherm_dew_crossings

ROOT = Path(__file__).resolve().parents[1]
INVESTIGATIONS = ROOT / "docs/investigations"
ONE_SYSTEM = (("ch4_c2", "ethane", 1, 2, 1, 2, 3),)


def _rows(name: str) -> list[dict[str, str]]:
    with (INVESTIGATIONS / name).open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _fixture_with_repeat(repeat_vapor: float) -> dict[str, object]:
    document = _thermoml_fixture([(210.0, 0.2, 0.05, 0.002), (220.0, 0.4, 0.1, 0.001)])
    pressure = [
        (210.0, 0.2, 1000.0, 1.0),
        (220.0, 0.4, 2000.0, 2.0),
        (210.0, 0.2, 1000.0, 1.0),
    ]
    vapor = [
        (210.0, 0.2, 0.05, 0.002),
        (220.0, 0.4, 0.1, 0.001),
        (210.0, 0.2, repeat_vapor, 0.002),
    ]
    document["PureOrMixtureData"] = [
        _source_dataset(1, 2, pressure, pressure=True),
        _source_dataset(2, 2, vapor, pressure=False),
    ]
    return document


def test_identical_repeat_is_skipped_only_on_request() -> None:
    document = _fixture_with_repeat(0.05)
    with pytest.raises(ValueError, match="duplicate.*pairing key"):
        extractor.extract_normalized_rows(document, ONE_SYSTEM)
    rows = extractor.extract_normalized_rows(
        document, ONE_SYSTEM, skip_identical_duplicates=True
    )
    assert [row["pressure_source_row"] for row in rows] == ["1", "2"]


def test_repeat_with_different_values_is_still_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate.*pairing key"):
        extractor.extract_normalized_rows(
            _fixture_with_repeat(0.06), ONE_SYSTEM, skip_identical_duplicates=True
        )


def test_butane_points_keep_one_copy_of_each_repeated_measurement() -> None:
    points = _rows("butane_preview_points.csv")
    counts = {
        system: sum(row["system_id"] == system for row in points)
        for system in ("ch4_ic4", "ch4_nc4")
    }
    assert counts == {"ch4_ic4": 17, "ch4_nc4": 19}
    keys = [(row["system_id"], row["source_pair_key"]) for row in points]
    assert len(keys) == len(set(keys))


def test_butane_summary_numbers_match_the_committed_results() -> None:
    results = _rows("butane_preview.csv")

    def selected(system: str, direction: str) -> list[dict[str, str]]:
        return [
            row
            for row in results
            if row["system_id"] == system and row["direction"] == direction
        ]

    expected = (("ch4_ic4", 17, 3.448693), ("ch4_nc4", 17, 3.511995))
    for system, converged, aard in expected:
        bubble = selected(system, "bubble_point")
        errors = [
            abs(float(row["pressure_percent_error"]))
            for row in bubble
            if row["status"] == "converged"
        ]
        assert len(errors) == converged
        assert statistics.fmean(errors) == pytest.approx(aard, abs=5e-7)
    assert {row["status"] for row in selected("ch4_ic4", "dew_point")} == {
        "inconclusive"
    }
    nc4_dew = selected("ch4_nc4", "dew_point")
    assert [row["status"] for row in nc4_dew].count("inconclusive") == 16
    assert [row["status"] for row in nc4_dew].count("not_found") == 2
    (unique,) = [row for row in nc4_dew if row["status"] == "converged"]
    assert unique["source_point_id"] == "may2015_ch4_nc4_008"
    assert float(unique["pressure_percent_error"]) == pytest.approx(-94.3746, abs=1e-4)


def test_one_butane_state_is_recomputed_from_the_engine() -> None:
    points = {row["source_point_id"]: row for row in _rows("butane_preview_points.csv")}
    stored = next(
        row
        for row in _rows("butane_preview.csv")
        if row["source_point_id"] == "may2015_ch4_ic4_017"
        and row["direction"] == "bubble_point"
    )
    fresh = solve_point(points["may2015_ch4_ic4_017"], SaturationKind.BUBBLE_POINT)
    assert fresh["status"] == stored["status"] == "converged"
    assert fresh["predicted_pressure_pa"] == pytest.approx(
        float(stored["predicted_pressure_pa"]), rel=1e-9
    )


def test_the_production_solver_now_returns_the_what_if_root() -> None:
    """The what-if CSV records the pre-P7 solver; P7 now returns its root."""

    stored = next(
        row
        for row in _rows("empty_scan_whatif.csv")
        if row["source_point_id"] == "may2015_ch4_c3_013"
    )
    assert stored["default_status"] == "not_found"
    mixture = FluidMixture(
        (
            MixtureComponent(COMPONENT_OBJECTS["methane"], 0.6572),
            MixtureComponent(COMPONENT_OBJECTS["propane"], 1.0 - 0.6572),
        )
    )
    fresh = calculate_saturation_pressure(mixture, 243.62, SaturationKind.BUBBLE_POINT)
    assert fresh.status is SaturationStatus.CONVERGED
    assert fresh.pressure_pa == pytest.approx(float(stored["walk_roots_pa"]), rel=1e-9)
    assert fresh.pressure_pa == pytest.approx(
        float(stored["newton_pressure_pa"]), rel=1e-8
    )


def test_every_c1_c3_not_found_bubble_has_one_walk_root() -> None:
    rows = _rows("empty_scan_whatif.csv")
    bubble = [row for row in rows if row["direction"] == "bubble_point"]
    dew = [row for row in rows if row["direction"] == "dew_point"]
    assert len(bubble) == 9
    assert all(row["walk_root_count"] == "1" for row in bubble)
    assert all(float(row["walk_root_max_fugacity_residual"]) < 1e-9 for row in bubble)
    confirmed = [row for row in bubble if row["newton_status"] == "converged"]
    assert len(confirmed) == 7
    for row in confirmed:
        assert float(row["walk_roots_pa"]) == pytest.approx(
            float(row["newton_pressure_pa"]), rel=1e-8
        )
    assert len(dew) == 4
    assert all(row["walk_root_count"] == "0" for row in dew)


def test_n_butane_state_008_has_a_second_dew_root() -> None:
    """PR's isotherm reaches y_exp at about 10.6 MPa, not only at 0.57 MPa.

    The preview CSV records the pre-P8 solver's unique 0.57 MPa answer. Since
    P7 the bubble point of the measured liquid converges at 10.58 MPa, and since
    P8 the dew state is ambiguous.
    """

    heavy = PROVISIONAL_COMPONENTS["n_butane"]
    bubble = calculate_saturation_pressure(
        _mixture(heavy, 0.7764), 244.48, SaturationKind.BUBBLE_POINT
    )
    assert bubble.status is SaturationStatus.CONVERGED
    assert bubble.pressure_pa == pytest.approx(10583492.67, rel=1e-8)
    assert bubble.incipient_composition[0] == pytest.approx(0.941325, abs=1e-6)
    dew = calculate_saturation_pressure(
        _mixture(heavy, 0.9406), 244.48, SaturationKind.DEW_POINT
    )
    assert dew.status is SaturationStatus.INCONCLUSIVE
    assert "HIDDEN_SATURATION_ROOT" in {item.code for item in dew.diagnostics}


def test_isotherm_crossings_are_counted_and_interpolated() -> None:
    samples = [(0.1, 1.0e6, 0.80), (0.5, 5.0e6, 0.95), (0.9, 9.0e6, 0.85)]
    crossings = isotherm_dew_crossings(samples, 0.90)
    assert len(crossings) == 2
    assert crossings[0] == pytest.approx(1.0e6 + 4.0e6 * (0.10 / 0.15))
    assert crossings[1] == pytest.approx(5.0e6 + 4.0e6 * 0.5)
    assert isotherm_dew_crossings(samples, 0.99) == []
    # An exact hit on the last sample is a crossing too.
    end_hit = isotherm_dew_crossings(samples, 0.85)
    assert end_hit == pytest.approx([1.0e6 + 4.0e6 * (0.05 / 0.15), 9.0e6])


def test_audit_finds_second_dew_roots_in_the_published_record() -> None:
    rows = {row["source_point_id"]: row for row in _rows("dew_uniqueness_audit.csv")}
    assert len(rows) == 13
    doubled = {key for key, row in rows.items() if row["isotherm_dew_crossings"] == "2"}
    assert doubled == {"may2015_ch4_c2_009", "may2015_ch4_c2_013"}
    assert all(row["isotherm_dew_crossings"] in {"1", "2"} for row in rows.values())
    crossings = rows["may2015_ch4_c2_013"]["isotherm_dew_pressures_pa"].split("|")
    second = float(crossings[1])
    assert 100.0 * (second - 6.885e6) / 6.885e6 == pytest.approx(-1.38, abs=0.01)
    # The 243.61 K isotherm stops below CH4+C2 017's measured pressure.
    assert float(rows["may2015_ch4_c2_017"]["highest_isotherm_pressure_pa"]) < 6.691e6


def test_converged_bubble_states_bracket_the_measured_vapours() -> None:
    """Two PR equilibrium states at 243.6 K straddle y = 0.7144 and 0.7123."""

    states = []
    for methane in (0.61, 0.64):
        mixture = FluidMixture(
            (
                MixtureComponent(COMPONENT_OBJECTS["methane"], methane),
                MixtureComponent(COMPONENT_OBJECTS["ethane"], 1.0 - methane),
            )
        )
        result = calculate_saturation_pressure(
            mixture,
            243.6,
            SaturationKind.BUBBLE_POINT,
            saturation_newton_enabled=True,
        )
        assert result.status is SaturationStatus.CONVERGED
        assert result.maximum_fugacity_equilibrium_residual < 1e-12
        states.append((result.pressure_pa, result.incipient_composition[0]))
    (low_pressure, low_vapor), (high_pressure, high_vapor) = states
    assert low_pressure == pytest.approx(6.6262e6, rel=1e-4)
    assert high_pressure == pytest.approx(6.8107e6, rel=1e-4)
    for measured in (0.7144, 0.7123):
        assert high_vapor < measured < low_vapor
