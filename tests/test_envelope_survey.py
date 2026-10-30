"""The extended-envelope survey tool and the numbers the docs quote from it."""

from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pvt_phase_simulator.eos.pseudo_arclength as arclength

ROOT = Path(__file__).resolve().parents[1]
SURVEY_CSV = ROOT / "docs/investigations/envelope_survey.csv"
STREAMLIT_DOC = ROOT / "docs/STREAMLIT_APPLICATION.md"


def _tool() -> ModuleType:
    path = ROOT / "tools" / "run_envelope_survey.py"
    spec = importlib.util.spec_from_file_location("run_envelope_survey", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_survey_has_sixteen_cases_starting_with_the_shipped_examples() -> None:
    tool = _tool()

    assert len(tool.CASES) == 16
    assert len({(c[1], c[2]) for c in tool.CASES}) >= 15
    assert [case[0] for case in tool.CASES[:3]] == [
        case[0] for case in tool.SHIPPED_CASES
    ]


def test_the_pre_p1_rule_is_restored_only_inside_the_context() -> None:
    tool = _tool()
    current = arclength._arclength_root_is_continuous

    with tool.pre_p1_continuity_rule():
        assert (
            arclength._arclength_root_is_continuous
            is arclength._root_branch_is_continuous
        )
    assert arclength._arclength_root_is_continuous is current


def test_p1_closes_a_case_the_earlier_rule_stopped_and_leaves_other_stops_alone() -> (
    None
):
    tool = _tool()
    results = tool.survey(
        (
            ("C2/C3 30/70", (0.0, 30.0, 70.0), 315.5),
            ("C1/C3 70/30", (70.0, 0.0, 30.0), 270.0),
        )
    )
    closed_by_p1, trivial = results

    assert not tool.closed(closed_by_p1.before)
    assert closed_by_p1.before.bubble.termination_reason == "phase_role_lost"
    assert closed_by_p1.before.dew.termination_reason == "phase_role_lost"
    assert tool.closed(closed_by_p1.current)
    # A stop with another cause is the same before and after P1.
    assert trivial.before.bubble.termination_reason == "trivial_state"
    assert trivial.current.bubble.termination_reason == "trivial_state"
    assert tool.counts(results, "before") == (0, 2)
    assert tool.counts(results, "current") == (1, 1)
    report = tool.render_markdown(results)
    assert (
        "**Before P1** (the earlier root-count rule): 0 closed, 2 stopped early"
        in report
    )
    assert "**Current code**: 1 closed, 1 stopped early" in report


def test_the_committed_survey_and_the_docs_quote_the_same_numbers() -> None:
    with SURVEY_CSV.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    before_closed = sum(row["before_closed"] == "true" for row in rows)
    current_closed = sum(row["current_closed"] == "true" for row in rows)
    text = " ".join(STREAMLIT_DOC.read_text(encoding="utf-8").split())

    assert len(rows) == 16
    assert (
        f"closes both branches in {current_closed} cases and stops early in "
        f"{len(rows) - current_closed}"
    ) in text
    assert (
        f"the same list closed {before_closed} and stopped early in "
        f"{len(rows) - before_closed}"
    ) in text
    # Every case still stopped early after P1 has a cause that is not a root count.
    for row in rows:
        if row["current_closed"] == "false":
            assert "phase_role_lost" not in (row["current_bubble"], row["current_dew"])
