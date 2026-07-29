"""Minimal smoke tests for the Milestone 0 development environment."""

from pathlib import Path

import numpy
import pandas
import plotly
import pydantic
import scipy
import streamlit

import pvt_phase_simulator


def test_package_imports_and_required_folders_exist() -> None:
    """The package and core dependencies should be importable."""
    assert pvt_phase_simulator.__name__ == "pvt_phase_simulator"

    assert numpy.__name__
    assert pandas.__name__
    assert plotly.__name__
    assert pydantic.__name__
    assert scipy.__name__
    assert streamlit.__name__

    expected_dirs = [
        Path("app"),
        Path("data"),
        Path("docs"),
        Path("notebooks"),
        Path("src"),
        Path("tests"),
    ]

    for directory in expected_dirs:
        assert directory.exists(), f"Missing expected directory: {directory}"
