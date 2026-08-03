"""Minimal smoke tests for the Milestone 0 development environment."""

from pathlib import Path

import numpy
import pandas
import plotly
import pydantic
import pytest
import scipy
import streamlit

import pvt_phase_simulator

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _assert_required_folders_exist(project_root: Path) -> None:
    expected_names = ("app", "data", "docs", "notebooks", "src", "tests")
    for name in expected_names:
        directory = project_root / name
        assert directory.exists(), f"Missing expected directory: {directory}"


def test_package_imports_and_required_folders_exist() -> None:
    """The package and core dependencies should be importable."""
    assert pvt_phase_simulator.__name__ == "pvt_phase_simulator"

    assert numpy.__name__
    assert pandas.__name__
    assert plotly.__name__
    assert pydantic.__name__
    assert scipy.__name__
    assert streamlit.__name__

    _assert_required_folders_exist(PROJECT_ROOT)


def test_required_folder_check_is_independent_of_working_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Folder checks should resolve from this test file, not the process CWD."""

    monkeypatch.chdir(PROJECT_ROOT.parent)
    _assert_required_folders_exist(PROJECT_ROOT)
