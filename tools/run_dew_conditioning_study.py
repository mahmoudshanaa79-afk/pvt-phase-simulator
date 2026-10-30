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
#: Liquid CH4 fractions at which PR's isotherm is sampled. Only converged bubble
#: solves are kept, so an isolated failure inside the range is simply skipped.
GRID = tuple(round(0.01 * index, 2) for index in range(1, 100))
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
    #: "solved" (refined with the solver), "grid_interpolated" (a refinement
    #: step failed, so the value is interpolated between converged grid
    #: points) or "above_isotherm" (no converged bubble pressure reaches P_exp).
    comparison_method: str


class _BubbleFailure(Exception):
    pass


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


def _require(state: tuple[float, float] | None) -> tuple[float, float]:
    if state is None:
        raise _BubbleFailure
    return state


def _isotherm(
    temperature_k: float, heavy: Component
) -> list[tuple[float, float, float]]:
    """Converged ``(x, P, y)`` samples of PR's bubble isotherm, by ``x``."""

    samples = []
    for methane in GRID:
        state = _bubble(temperature_k, methane, heavy)
        if state is not None:
            samples.append((methane, state[0], state[1]))
    if not samples:
        raise RuntimeError(f"no converged bubble state at {temperature_k} K")
    return samples


def analyze_dew_state(point: ExperimentalVLEPoint) -> DewConditioning:
    """Compare one measured dew state with PR's isotherm at its temperature."""

    temperature = point.temperature_k
    pressure = point.pressure_pa
    vapor = point.vapor_mole_fractions[0]
    uncertainty = point.vapor_expanded_uncertainties[0]
    if uncertainty is None:
        raise ValueError(f"{point.source_point_id} has no vapour uncertainty")
    heavy = HEAVY[point.component_ids[1]]
    samples = _isotherm(temperature, heavy)

    # Vapour-composition maximum: refine around the best grid sample.
    best = max(range(len(samples)), key=lambda index: samples[index][2])
    window = (
        samples[max(best - 1, 0)][0],
        samples[min(best + 1, len(samples) - 1)][0],
    )
    pressure_at_maximum, vapor_maximum = samples[best][1], samples[best][2]
    if window[0] < window[1]:
        try:
            maximum = minimize_scalar(
                lambda x: -_require(_bubble(temperature, x, heavy))[1],
                bounds=window,
                method="bounded",
                options={"xatol": 1e-5},
            )
            refined = _require(_bubble(temperature, maximum.x, heavy))
            if refined[1] >= vapor_maximum:
                pressure_at_maximum, vapor_maximum = refined
        except _BubbleFailure:
            pass

    comparison: dict[str, float | None] = dict.fromkeys(
        (
            "model_vapor_ch4_at_experimental_pressure",
            "vapor_ch4_difference",
            "vapor_difference_over_uncertainty",
            "pressure_composition_slope_pa",
            "pressure_spread_from_vapor_uncertainty_pa",
        )
    )
    method = "above_isotherm"
    bracket = next(
        (
            (low, high)
            for low, high in zip(samples, samples[1:], strict=False)
            if low[1] <= pressure <= high[1]
        ),
        None,
    )
    if bracket is not None:
        low, high = bracket
        try:
            methane = brentq(
                lambda x: _require(_bubble(temperature, x, heavy))[0] - pressure,
                low[0],
                high[0],
                xtol=1e-10,
            )
            model_vapor = _require(_bubble(temperature, methane, heavy))[1]
            below = _require(
                _bubble(temperature, max(low[0], methane - DERIVATIVE_STEP), heavy)
            )
            above = _require(
                _bubble(temperature, min(high[0], methane + DERIVATIVE_STEP), heavy)
            )
            slope = (above[0] - below[0]) / (above[1] - below[1])
            method = "solved"
        except _BubbleFailure:
            weight = (pressure - low[1]) / (high[1] - low[1])
            model_vapor = low[2] + weight * (high[2] - low[2])
            slope = (high[1] - low[1]) / (high[2] - low[2])
            method = "grid_interpolated"
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
        highest_converged_bubble_pressure_pa=max(sample[1] for sample in samples),
        **comparison,
        comparison_method=method,
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
