"""Pure-component PR saturation against reference-EOS values (investigation)."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from pvt_phase_simulator.fluid_models import ETHANE, METHANE, PROPANE

ROOT = Path(__file__).resolve().parents[1]
INVESTIGATIONS = ROOT / "docs" / "investigations"


def _tool() -> ModuleType:
    path = ROOT / "tools" / "run_pure_saturation_study.py"
    spec = importlib.util.spec_from_file_location("run_pure_saturation_study", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _reference_row(component_id: str, reduced: str) -> dict[str, str]:
    rows = csv.DictReader(
        (INVESTIGATIONS / "pure_saturation_reference.csv").open(encoding="utf-8")
    )
    return next(
        row
        for row in rows
        if row["component_id"] == component_id and row["reduced_temperature"] == reduced
    )


def test_reference_critical_points_match_the_verified_components() -> None:
    provenance = json.loads(
        (INVESTIGATIONS / "pure_saturation_reference_provenance.json").read_text(
            encoding="utf-8"
        )
    )
    for component_id, component in (
        ("methane", METHANE),
        ("ethane", ETHANE),
        ("propane", PROPANE),
    ):
        fluid = provenance["fluids"][component_id]
        assert fluid["reference_critical_temperature_k"] == pytest.approx(
            component.critical_temperature_k, abs=1e-9
        )
        assert fluid["reference_critical_pressure_pa"] == pytest.approx(
            component.critical_pressure_pa, abs=1e-6
        )


def test_vapour_pressure_is_closest_near_the_acentric_factor_anchor() -> None:
    result = _tool().compare_state(_reference_row("propane", "0.7"))

    assert result.model_status == "converged"
    assert abs(result.pressure_relative_error) < 0.005


def test_liquid_density_shows_the_known_pr_bias() -> None:
    tool = _tool()
    cold = tool.compare_state(_reference_row("methane", "0.5"))
    near_critical = tool.compare_state(_reference_row("propane", "0.98"))

    # Too dense far below Tc, not dense enough near Tc: the behaviour that
    # Peneloux volume translation exists to correct.
    assert 0.05 < cold.liquid_density_relative_error < 0.20
    assert -0.20 < near_critical.liquid_density_relative_error < -0.05
