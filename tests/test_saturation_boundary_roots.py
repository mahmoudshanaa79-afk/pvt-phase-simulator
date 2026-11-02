"""P7 and P8: roots beside non-converged grid nodes when the scan finds none,
or when the boundary walk stops one step short of a sign change."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pvt_phase_simulator.eos import saturation_pressure as module
from pvt_phase_simulator.eos.saturation_pressure import (
    SaturationKind,
    SaturationStatus,
    calculate_saturation_pressure,
)
from pvt_phase_simulator.fluid_models import (
    ETHANE,
    METHANE,
    PROPANE,
    FluidMixture,
    MixtureComponent,
)


def _binary(heavy: object, methane: float) -> FluidMixture:
    return FluidMixture(
        (MixtureComponent(METHANE, methane), MixtureComponent(heavy, 1.0 - methane))  # type: ignore[arg-type]
    )


def _node(pressure: float, objective: float | None) -> SimpleNamespace:
    return SimpleNamespace(
        pressure_pa=pressure, converged=objective is not None, objective=objective
    )


def test_walk_reports_its_bracket_with_the_converged_ends() -> None:
    def evaluate(log_pressure: float) -> SimpleNamespace:
        pressure = float(module.exp(log_pressure))
        return _node(pressure, 1.0 if pressure < 7.7e6 else -1.0)

    scanned = (_node(7.0e6, 1.0), _node(8.0e6, None))
    (root,) = module._boundary_roots(scanned, evaluate)  # type: ignore[arg-type]
    assert root.bracket is not None
    low, high = root.bracket
    assert low.pressure_pa < 7.7e6 < high.pressure_pa < 8.0e6
    assert low.objective > 0.0 > high.objective


def test_confirmation_runs_only_when_the_walk_finds_nothing() -> None:
    requests: list[tuple[float, float]] = []

    def confirm(last: SimpleNamespace, far: float) -> float | None:
        requests.append((last.pressure_pa, far))
        return 7.9e6

    def stops_early(log_pressure: float) -> SimpleNamespace:
        pressure = float(module.exp(log_pressure))
        return _node(pressure, 0.5 if pressure < 7.5e6 else None)

    scanned = (_node(7.0e6, 1.0), _node(8.0e6, None))
    (root,) = module._boundary_roots(scanned, stops_early, confirm)  # type: ignore[arg-type]
    assert root.bracket is None and root.pressure_pa == 7.9e6
    ((last, far),) = requests
    assert 7.0e6 < last < 7.5e6 and far == 8.0e6

    def crosses(log_pressure: float) -> SimpleNamespace:
        pressure = float(module.exp(log_pressure))
        return _node(pressure, 1.0 if pressure < 7.7e6 else -1.0)

    requests.clear()
    (root,) = module._boundary_roots(scanned, crosses, confirm)  # type: ignore[arg-type]
    assert root.bracket is not None and not requests


@pytest.mark.parametrize(
    ("heavy", "methane", "temperature_k", "expected_pa"),
    (
        # May (2015) CH4+C3 013 and CH4+C2 012 bubble: formerly not_found (P7).
        (PROPANE, 0.6572, 243.62, 7565885.228861917),
        (ETHANE, 0.5754, 243.6, 6368928.025392923),
    ),
)
def test_a_root_beside_a_failed_node_is_found_when_the_scan_is_empty(
    heavy: object, methane: float, temperature_k: float, expected_pa: float
) -> None:
    result = calculate_saturation_pressure(
        _binary(heavy, methane), temperature_k, SaturationKind.BUBBLE_POINT
    )
    assert result.status is SaturationStatus.CONVERGED
    assert result.pressure_pa == pytest.approx(expected_pa, rel=1e-9)
    codes = {item.code for item in result.diagnostics}
    assert "BOUNDARY_SATURATION_ROOT" in codes
    assert "HIDDEN_SATURATION_ROOT" not in codes


def test_newton_landing_on_the_trivial_solution_is_not_a_second_root() -> None:
    """At CH4+C2 012 bubble, Newton converges at 4.67 MPa with the incipient
    vapour within 6e-5 of the feed. That must not make the state ambiguous."""

    result = calculate_saturation_pressure(
        _binary(ETHANE, 0.5754), 243.6, SaturationKind.BUBBLE_POINT
    )
    assert result.status is SaturationStatus.CONVERGED
    assert result.incipient_composition[0] == pytest.approx(0.725856, abs=1e-6)


@pytest.mark.parametrize(
    ("methane", "temperature_k"),
    (
        (0.7046, 243.6),  # CH4+C2 008: lower 4.85 MPa, upper 6.88 MPa
        (0.7144, 243.6),  # CH4+C2 009: lower 5.19 MPa, upper 6.76 MPa
        (0.7123, 243.6),  # CH4+C2 013: lower 5.11 MPa, upper 6.80 MPa
        (0.7188, 243.61),  # CH4+C2 017: lower 5.39 MPa, upper 6.67 MPa
    ),
)
def test_an_upper_dew_root_past_a_failed_walk_step_makes_the_state_ambiguous(
    methane: float, temperature_k: float
) -> None:
    result = calculate_saturation_pressure(
        _binary(ETHANE, methane), temperature_k, SaturationKind.DEW_POINT
    )
    assert result.status is SaturationStatus.INCONCLUSIVE
    assert result.pressure_pa is None
    codes = {item.code for item in result.diagnostics}
    assert {"HIDDEN_SATURATION_ROOT", "MULTIPLE_SATURATION_ROOTS"} <= codes


def test_a_single_low_pressure_dew_root_stays_unique() -> None:
    """CH4+C2 001 at 203.22 K has one PR dew root; P7/P8 leave it unchanged."""

    result = calculate_saturation_pressure(
        _binary(ETHANE, 0.8667), 203.22, SaturationKind.DEW_POINT
    )
    assert result.status is SaturationStatus.CONVERGED
    assert result.pressure_pa == pytest.approx(1978223.0913044063, rel=1e-9)
