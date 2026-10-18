"""The CH4+C3 dew-conditioning diagnostic separates ill-posed states from good ones."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from pvt_phase_simulator.experimental_validation import (
    ExperimentalVLEPoint,
    load_experimental_vle_dataset,
)

ROOT = Path(__file__).resolve().parents[1]


def _tool() -> ModuleType:
    path = ROOT / "tools" / "run_dew_conditioning_study.py"
    spec = importlib.util.spec_from_file_location("run_dew_conditioning_study", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Dataclasses resolve their module through sys.modules while being created.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def points() -> dict[str, ExperimentalVLEPoint]:
    dataset = load_experimental_vle_dataset(
        ROOT / "data/experimental/may_2015_ch4_c2_ch4_c3_vle.csv",
        ROOT / "data/experimental/may_2015_source_manifest.json",
    )
    return {point.source_point_id: point for point in dataset.points}


def test_low_pressure_state_is_well_conditioned(
    points: dict[str, ExperimentalVLEPoint],
) -> None:
    result = _tool().analyze_dew_state(points["may2015_ch4_c3_009"])

    assert result.vapor_difference_over_uncertainty is not None
    assert abs(result.vapor_difference_over_uncertainty) < 0.1
    # 0.89 MPa, far below the composition maximum: a modest slope.
    assert abs(result.pressure_composition_slope_pa) < 2.0e7


def test_state_near_the_vapour_maximum_is_ill_conditioned(
    points: dict[str, ExperimentalVLEPoint],
) -> None:
    result = _tool().analyze_dew_state(points["may2015_ch4_c3_016"])

    # PR's own isotherm peaks just above the measured vapour composition, so the
    # dew pressure at fixed y is ill-posed while the composition still agrees.
    assert result.isotherm_vapor_ch4_maximum == pytest.approx(0.9301, abs=2e-4)
    assert 0.0 < result.isotherm_vapor_ch4_maximum - result.experimental_vapor_ch4
    assert abs(result.vapor_difference_over_uncertainty) < 0.2
    # The stated vapour uncertainty alone allows megapascals of dew pressure.
    assert result.pressure_spread_from_vapor_uncertainty_pa > 3.0e6
