"""Separate PR model error from dew-problem conditioning (read-only).

The production dew direction asks for the pressure at which a vapour of the
measured composition ``y`` starts to condense at the measured ``T``. Near the
maximum of ``y`` along an isotherm that question is ill-conditioned: ``dP/dy``
grows without bound, two dew pressures exist just below the maximum and none
above it. This tool quantifies that for every measured dew state (CH4+C2 and
CH4+C3), using only the
unchanged engine:

* PR's own isotherm is followed with the bubble solver (Newton refinement on, an
  existing engine option), which gives coexisting ``(P, x, y)``;
* ``y_max`` is PR's largest vapour CH4 fraction on that isotherm;
* ``y_PR(P_exp)`` is PR's coexisting vapour composition at the measured
  pressure, so ``dy = y_exp - y_PR(P_exp)`` is a well-conditioned composition
  comparison;
* ``|dP/dy|`` at the measured pressure, times the stated vapour uncertainty
  ``U_y``, is the dew-pressure spread implied by the composition uncertainty alone.

The measured pressure is only the point at which a composition is compared. It
never selects a dew root, and no parameter, tolerance or engine path is changed.
Output is written to ``docs/investigations``; the protected Module 17 artifacts
under ``docs/validation`` are only read.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from scipy.optimize import brentq, minimize_scalar  # type: ignore[import-untyped]

from pvt_phase_simulator.eos.saturation_pressure import (
    SaturationKind,
    SaturationStatus,
    calculate_saturation_pressure,
)
from pvt_phase_simulator.experimental_validation import (
    ExperimentalVLEPoint,
    load_experimental_vle_dataset,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    Component,
    FluidMixture,
    MixtureComponent,
)

HEAVY: dict[str, Component] = {"ethane": ETHANE, "propane": PROPANE}
#: Isotherm coordinate grid used only to find how far the bubble solver reaches.
REACH_START = 0.01
REACH_STEP = 0.01
DERIVATIVE_STEP = 2e-4


@dataclass(frozen=True, slots=True)
class DewConditioning:
    source_point_id: str
    system_id: str
    temperature_k: float
    experimental_pressure_pa: float
    experimental_vapor_ch4: float
    vapor_uncertainty: float
    isotherm_vapor_ch4_maximum: float
    pressure_at_vapor_maximum_pa: float
    highest_converged_bubble_pressure_pa: float
    model_vapor_ch4_at_experimental_pressure: float | None
    vapor_ch4_difference: float | None
    vapor_difference_over_uncertainty: float | None
    pressure_composition_slope_pa: float | None
    pressure_spread_from_vapor_uncertainty_pa: float | None


def _bubble(
    temperature_k: float, methane: float, heavy: Component
) -> tuple[float, float] | None:
    mixture = FluidMixture(
        (
            MixtureComponent(METHANE, methane),
            MixtureComponent(heavy, 1.0 - methane),
        )
    )
    result = calculate_saturation_pressure(
        mixture,
        temperature_k,
        SaturationKind.BUBBLE_POINT,
        saturation_newton_enabled=True,
    )
    if result.status is not SaturationStatus.CONVERGED or result.pressure_pa is None:
        return None
    return result.pressure_pa, result.incipient_composition[0]


def _reach(temperature_k: float, heavy: Component) -> float:
    last: float | None = None
    methane = REACH_START
    while methane < 0.995:
        if _bubble(temperature_k, methane, heavy) is None:
            break
        last = methane
        methane = round(methane + REACH_STEP, 10)
    if last is None:
        raise RuntimeError(f"no converged bubble state at {temperature_k} K")
    return last


def _require(state: tuple[float, float] | None) -> tuple[float, float]:
    if state is None:
        raise RuntimeError("bubble solve failed inside the converged isotherm range")
    return state


def analyze_dew_state(point: ExperimentalVLEPoint) -> DewConditioning:
    """Compare one measured dew state with PR's isotherm at its temperature."""

    temperature = point.temperature_k
    pressure = point.pressure_pa
    vapor = point.vapor_mole_fractions[0]
    uncertainty = point.vapor_expanded_uncertainties[0]
    if uncertainty is None:
        raise ValueError(f"{point.source_point_id} has no vapour uncertainty")
    heavy = HEAVY[point.component_ids[1]]
    upper = _reach(temperature, heavy)
    maximum = minimize_scalar(
        lambda x: -_require(_bubble(temperature, x, heavy))[1],
        bounds=(REACH_START, upper),
        method="bounded",
        options={"xatol": 1e-5},
    )
    pressure_at_maximum, vapor_maximum = _require(
        _bubble(temperature, maximum.x, heavy)
    )
    highest_pressure = _require(_bubble(temperature, upper, heavy))[0]
    comparison: dict[str, float | None] = dict.fromkeys(
        (
            "model_vapor_ch4_at_experimental_pressure",
            "vapor_ch4_difference",
            "vapor_difference_over_uncertainty",
            "pressure_composition_slope_pa",
            "pressure_spread_from_vapor_uncertainty_pa",
        )
    )
    if pressure <= highest_pressure:
        methane = brentq(
            lambda x: _require(_bubble(temperature, x, heavy))[0] - pressure,
            REACH_START,
            upper,
            xtol=1e-10,
        )
        model_vapor = _require(_bubble(temperature, methane, heavy))[1]
        low = _require(
            _bubble(temperature, max(REACH_START, methane - DERIVATIVE_STEP), heavy)
        )
        high = _require(
            _bubble(temperature, min(upper, methane + DERIVATIVE_STEP), heavy)
        )
        slope = (high[0] - low[0]) / (high[1] - low[1])
        comparison = {
            "model_vapor_ch4_at_experimental_pressure": model_vapor,
            "vapor_ch4_difference": vapor - model_vapor,
            "vapor_difference_over_uncertainty": (vapor - model_vapor) / uncertainty,
            "pressure_composition_slope_pa": slope,
            "pressure_spread_from_vapor_uncertainty_pa": abs(slope) * uncertainty,
        }
    return DewConditioning(
        source_point_id=point.source_point_id,
        system_id=point.system_id,
        temperature_k=temperature,
        experimental_pressure_pa=pressure,
        experimental_vapor_ch4=vapor,
        vapor_uncertainty=uncertainty,
        isotherm_vapor_ch4_maximum=vapor_maximum,
        pressure_at_vapor_maximum_pa=pressure_at_maximum,
        highest_converged_bubble_pressure_pa=highest_pressure,
        **comparison,
    )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return parser.parse_args()


def main() -> None:
    root = _arguments().root.resolve()
    dataset = load_experimental_vle_dataset(
        root / "data/experimental/may_2015_ch4_c2_ch4_c3_vle.csv",
        root / "data/experimental/may_2015_source_manifest.json",
    )
    stored = {
        row["source_point_id"]: row
        for row in csv.DictReader(
            (root / "docs/validation/module17_vle_validation.csv").open(
                encoding="utf-8"
            )
        )
    }
    rows = []
    for point in dataset.points:
        result = asdict(analyze_dew_state(point))
        production = stored[point.source_point_id]
        result |= {
            "production_dew_status": production["dew_status"],
            "production_dew_pressure_pa": production["dew_predicted_pressure_pa"],
            "diagnostic_dew_root_pressures_pa": production[
                "dew_diagnostic_root_pressures_pa"
            ],
        }
        rows.append(result)
        print(json.dumps(result), flush=True)
    output = root / "docs/investigations/dew_conditioning.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
