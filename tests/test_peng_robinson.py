"""Tests for Peng–Robinson calculations."""

import pytest

from pvt_phase_simulator.eos.peng_robinson import calculate_kappa


def test_calculate_kappa_for_methane() -> None:
    """Methane kappa should match the expected value."""

    result = calculate_kappa(0.011)

    assert result == pytest.approx(0.39157, abs=1e-5)