"""P2: a saturation root hidden beside a non-converged grid node is not missed."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pvt_phase_simulator.eos import saturation_pressure as module
from pvt_phase_simulator.eos.saturation_pressure import (
    BOUNDARY_REFINEMENT_STEPS,
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


def test_walk_finds_a_sign_change_before_the_non_converged_node() -> None:
    calls: list[float] = []

    def evaluate(log_pressure: float) -> SimpleNamespace:
        pressure = float(module.exp(log_pressure))
        calls.append(pressure)
        return _node(pressure, 1.0 if pressure < 7.7e6 else -1.0)

    scanned = (_node(7.0e6, 1.0), _node(8.0e6, None))
    assert module._boundary_hides_another_root(scanned, evaluate)  # type: ignore[arg-type]
    assert calls and max(calls) < 8.0e6


def test_walk_stops_at_the_first_non_converged_evaluation() -> None:
    calls: list[float] = []

    def evaluate(log_pressure: float) -> SimpleNamespace:
        pressure = float(module.exp(log_pressure))
        calls.append(pressure)
        # Converged with the same sign only very close to the start, then fails.
        return _node(pressure, 1.0 if len(calls) < 3 else None)

    scanned = (_node(7.0e6, 1.0), _node(8.0e6, None))
    assert not module._boundary_hides_another_root(scanned, evaluate)  # type: ignore[arg-type]
    assert len(calls) == 3


def test_intervals_with_both_ends_alike_are_not_walked() -> None:
    def evaluate(log_pressure: float) -> SimpleNamespace:
        raise AssertionError("no interval should be refined")

    scanned = (
        _node(1.0e6, 1.0),
        _node(2.0e6, 0.5),
        _node(3.0e6, None),
        _node(4.0e6, None),
    )
    # 2-3 MPa is a boundary, so allow exactly that one walk; the others must not run.
    walked: list[float] = []

    def evaluate_boundary(log_pressure: float) -> SimpleNamespace:
        pressure = float(module.exp(log_pressure))
        assert 2.0e6 < pressure < 3.0e6
        walked.append(pressure)
        return _node(pressure, 0.5)

    assert not module._boundary_hides_another_root(scanned, evaluate_boundary)  # type: ignore[arg-type]
    assert len(walked) == BOUNDARY_REFINEMENT_STEPS - 1
    assert not module._boundary_hides_another_root(scanned[:2], evaluate)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("heavy", "methane", "temperature_k"),
    (
        (PROPANE, 0.9145, 243.62),  # May (2015) CH4+C3 014: roots 2.93, 7.77 MPa
        (ETHANE, 0.7212, 243.6),  # CH4+C2 010: roots 5.51, 6.61 MPa
    ),
)
def test_known_two_root_dew_states_are_reported_as_ambiguous(
    heavy: object, methane: float, temperature_k: float
) -> None:
    result = calculate_saturation_pressure(
        _binary(heavy, methane), temperature_k, SaturationKind.DEW_POINT
    )

    assert result.status is SaturationStatus.INCONCLUSIVE
    assert result.pressure_pa is None
    codes = {item.code for item in result.diagnostics}
    assert {"HIDDEN_SATURATION_ROOT", "MULTIPLE_SATURATION_ROOTS"} <= codes


def test_the_hidden_root_is_a_real_converged_root() -> None:
    # CH4+C2 010: the second root, which the Module 17 scan missed.
    result = calculate_saturation_pressure(
        _binary(ETHANE, 0.7212), 243.6, SaturationKind.DEW_POINT, 6.55e6, 6.65e6
    )

    assert result.status is SaturationStatus.CONVERGED
    assert result.pressure_pa == pytest.approx(6.6076e6, rel=1e-4)
    assert result.maximum_fugacity_equilibrium_residual < 1e-8


def test_a_single_root_dew_state_still_converges() -> None:
    # CH4+C3 009, the only state with one PR dew root: 0.916 MPa.
    result = calculate_saturation_pressure(
        _binary(PROPANE, 0.7924), 243.62, SaturationKind.DEW_POINT
    )

    assert result.status is SaturationStatus.CONVERGED
    assert result.pressure_pa == pytest.approx(916_257.1145, rel=1e-6)
    assert "HIDDEN_SATURATION_ROOT" not in {item.code for item in result.diagnostics}
