"""The Validation page's further-evidence section reads the committed results."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from pvt_phase_simulator_ui.validation_evidence import (
    NEWTON_COMPARISON,
    PURE_COMPARISON,
    dew_conditioning_summary,
    newton_summary,
    pure_summary,
)

ROOT = Path(__file__).resolve().parents[1]


def test_pure_component_summary_matches_the_documented_aard() -> None:
    summary = pure_summary(pd.read_csv(ROOT / PURE_COMPARISON)).set_index("Component")

    assert summary.loc["Methane", "Vapour pressure AARD (%)"] == pytest.approx(0.73)
    assert summary.loc["Propane", "Liquid density AARD (%)"] == pytest.approx(5.55)
    assert set(summary["States"]) == {25}


def test_newton_summary_counts_converged_and_accuracy_results_separately() -> None:
    frame = pd.read_csv(ROOT / NEWTON_COMPARISON)
    summary = newton_summary(frame)
    dew = summary[summary["Direction"] == "Dew"].set_index("System")

    propane = dew.loc["Methane + propane"]
    assert propane["Converged (Newton)"] >= propane["Accuracy results (Newton)"]
    # A converged dew pressure that is one root of several is not an accuracy
    # result, so these two counts must be able to differ.
    assert propane["Converged (Newton)"] > propane["Accuracy results (Newton)"]


def test_dew_conditioning_summary_counts() -> None:
    frame = pd.DataFrame(
        {
            "system_id": ["ch4_c3", "ch4_c3", "ch4_c3"],
            "vapor_difference_over_uncertainty": [0.5, -1.5, 2.5],
            "pressure_spread_from_vapor_uncertainty_pa": [2.0e6, 0.5e6, 3.0e6],
            "experimental_vapor_ch4": [0.90, 0.95, 0.80],
            "isotherm_vapor_ch4_maximum": [0.93, 0.94, 0.85],
        }
    )
    row = dew_conditioning_summary(frame).iloc[0]

    assert row["Dew states"] == 3
    assert row["Within 1 U"] == 1
    assert row["Within 2 U"] == 2
    assert row["Ill-posed (> 1 MPa from U_y)"] == 2
    assert row["Measured y above PR maximum"] == 1


def test_validation_page_shows_the_evidence_tabs_without_errors() -> None:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=60).run()
    app.switch_page(
        ROOT / "src" / "pvt_phase_simulator_ui" / "pages" / "validation.py"
    ).run()

    assert not app.exception
    assert any(item.value == "Further evidence" for item in app.subheader)
    assert [tab.label for tab in app.tabs] == [
        "Dew conditioning",
        "Newton refinement",
        "Pure components",
    ]
