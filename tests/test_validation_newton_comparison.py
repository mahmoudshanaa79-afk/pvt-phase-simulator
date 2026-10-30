"""Validation with and without Newton refinement, side by side (proposal P4, option B).

The comparison runs on a small subset so the suite stays fast. The tool's full output
is generated, not re-run here, in line with the other investigation tools.
"""

from __future__ import annotations

import csv
import importlib.util
import sys
from io import StringIO
from pathlib import Path
from types import ModuleType

import pytest

import pvt_phase_simulator.experimental_validation as validation
from pvt_phase_simulator.experimental_validation import (
    ExperimentalVLEDataset,
    load_experimental_vle_dataset,
)

ROOT = Path(__file__).resolve().parents[1]
FROZEN_CSV = ROOT / "docs/validation/module17_vle_validation.csv"

#: A CH4+C2 state, the CH4+C3 states whose bubble pressure the default run cannot
#: bracket (docs/DEW_INVESTIGATION.md), and one well-behaved CH4+C3 state.
SUBSET = (
    "may2015_ch4_c2_001",
    "may2015_ch4_c3_009",
    "may2015_ch4_c3_013",
)


def _tool() -> ModuleType:
    path = ROOT / "tools" / "run_validation_newton_comparison.py"
    spec = importlib.util.spec_from_file_location(
        "run_validation_newton_comparison", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def dataset() -> ExperimentalVLEDataset:
    full = load_experimental_vle_dataset(
        ROOT / "data/experimental/may_2015_ch4_c2_ch4_c3_vle.csv",
        ROOT / "data/experimental/may_2015_source_manifest.json",
    )
    points = tuple(p for p in full.points if p.source_point_id in SUBSET)
    assert tuple(p.source_point_id for p in points) == SUBSET
    return ExperimentalVLEDataset(source=full.source, points=points)


@pytest.fixture(scope="module")
def comparison(dataset: ExperimentalVLEDataset):
    return _tool().compare(dataset, FROZEN_CSV)


def test_the_default_run_is_the_frozen_production_record(comparison) -> None:
    """The default side reproduces the frozen outcomes: nothing is regenerated."""

    assert comparison.default_matches_frozen_csv is True


def test_a_changed_default_would_be_reported_as_not_reproducing(comparison) -> None:
    tool = _tool()
    frozen = FROZEN_CSV.read_text(encoding="utf-8")

    assert tool.reproduces_frozen_record(comparison.default, frozen)
    # The Newton run differs from the frozen record on the state it newly solves.
    assert not tool.reproduces_frozen_record(comparison.newton, frozen)


def test_newton_converges_the_bubble_state_the_default_cannot_bracket(
    comparison,
) -> None:
    default = next(
        r for r in comparison.default if r.point.source_point_id.endswith("c3_013")
    )
    newton = next(
        r for r in comparison.newton if r.point.source_point_id.endswith("c3_013")
    )

    assert default.bubble.status != "converged"
    assert default.bubble.failure_reason is not None
    assert newton.bubble.status == "converged"
    # Measured 7.530 MPa; docs/ENGINE_CHANGE_PROPOSALS.md lists +0.5 %.
    assert newton.bubble.pressure_percent_error == pytest.approx(0.5, abs=0.1)


def test_only_the_state_the_default_cannot_solve_changes(comparison) -> None:
    changes = _tool().changed_states(comparison)

    assert any(point.endswith("c3_013") and d == "bubble" for _, point, d in changes)
    assert not any(point.endswith("c2_001") for _, point, _ in changes)
    assert not any(point.endswith("c3_009") for _, point, _ in changes)


def test_the_csv_has_both_runs_for_every_state_and_direction(
    comparison,
) -> None:
    rows = list(csv.DictReader(StringIO(_tool().render_csv(comparison))))

    assert len(rows) == 2 * len(SUBSET)
    failed = next(
        row
        for row in rows
        if row["source_point_id"].endswith("c3_013") and row["direction"] == "bubble"
    )
    assert failed["default_status"] != "converged"
    assert failed["default_predicted_pressure_pa"] == ""
    assert failed["newton_status"] == "converged"
    assert failed["outcome_changed"] == "true"


def test_the_report_states_the_numbers_it_recomputed(comparison) -> None:
    report = _tool().render_markdown(comparison)

    assert "within 1e-09 relative" in report
    assert "**yes**" in report
    assert "may2015_ch4_c3_013" in report
    assert "| ch4_c3 | 2 | 1 | 2 |" in report


def test_newton_is_enabled_only_inside_the_context_and_then_restored() -> None:
    tool = _tool()
    original = validation.calculate_saturation_pressure

    with tool.newton_refinement_enabled():
        assert validation.calculate_saturation_pressure is not original
    assert validation.calculate_saturation_pressure is original

    with pytest.raises(RuntimeError), tool.newton_refinement_enabled():
        raise RuntimeError("boom")
    assert validation.calculate_saturation_pressure is original


def test_dew_results_at_multi_root_states_are_not_counted_as_accuracy(
    comparison,
) -> None:
    """013 has two PR dew roots: a converged dew pressure there is one root of two."""

    tool = _tool()
    rows = {
        (row["source_point_id"], row["direction"]): row
        for row in csv.DictReader(StringIO(tool.render_csv(comparison)))
    }

    two_roots = rows[("may2015_ch4_c3_013", "dew")]
    assert two_roots["pr_dew_roots"] == "2"
    assert two_roots["default_counts_as_accuracy"] == "false"
    assert two_roots["newton_counts_as_accuracy"] == "false"
    unique_root = rows[("may2015_ch4_c3_009", "dew")]
    assert unique_root["pr_dew_roots"] == "1"
    assert unique_root["default_counts_as_accuracy"] == "true"
    assert unique_root["newton_counts_as_accuracy"] == "true"
    # Bubble results have no root-multiplicity caveat.
    assert rows[("may2015_ch4_c3_013", "bubble")]["pr_dew_roots"] == ""
    assert rows[("may2015_ch4_c3_013", "bubble")]["newton_counts_as_accuracy"] == "true"


def test_the_dew_aard_leaves_out_one_root_of_several(comparison) -> None:
    tool = _tool()
    for results in (comparison.default, comparison.newton):
        statistics = tool._statistics(results, "ch4_c3", "dew")

        assert statistics.accuracy_states == 1  # only the unique-root state 009
        assert statistics.converged - statistics.one_root_of_several == 1
        assert statistics.aard_percent is not None
        assert statistics.aard_percent < 5.0  # 009 alone, not the two-root states


def test_the_report_labels_one_root_of_several_and_omits_it_from_the_aard(
    comparison,
) -> None:
    report = _tool().render_markdown(comparison)

    assert "**one root of several**" in report
    assert "not an accuracy result" in report
    assert "AARD, other states" in report
    assert "one root of 2" in report
