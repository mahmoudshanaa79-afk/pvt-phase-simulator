"""The kij study (P6): its kij = 0 baseline, its committed numbers, the P3 hook.

The full study takes about an hour, so the suite does not rerun it. It checks
instead that:

* kij = 0 through the study's solve path reproduces the protected Module 17
  record (engine, all 40 states, both directions);
* the summary CSV aggregates the per-state CSV, the fit follows from the
  committed fine grid, and the report re-renders byte for byte from the CSV and
  JSON, so every number in kij_study.md comes from the data;
* a sample of committed per-state results at the fitted kij reproduces with
  the engine;
* the optional kij in the P3 tool leaves the published P3 output unchanged.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from functools import cache
from pathlib import Path

import pytest

from pvt_phase_simulator.experimental_validation import load_experimental_vle_dataset
from pvt_phase_simulator.fluid_models import ETHANE, METHANE
from tools import run_kij_study as study
from tools.kij_study_report import render
from tools.run_dew_conditioning_study import analyze_dew_state

ROOT = Path(__file__).resolve().parents[1]
MODULE17 = ROOT / "docs/validation/module17_vle_validation_summary.json"
P3_RESULTS = ROOT / "docs/investigations/dew_conditioning.csv"


def _rows(path: str) -> list[dict[str, str]]:
    with (ROOT / path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


@cache
def _fit() -> dict:
    return json.loads((ROOT / study.FIT_FILE).read_text(encoding="utf-8"))


@cache
def _states() -> tuple[study.State, ...]:
    return tuple(study._production_states(ROOT) + study._butane_states(ROOT))


def _system_states(system: str) -> list[study.State]:
    return [state for state in _states() if state.system_id == system]


def _value(text: str) -> float | None:
    return None if text == "" else float(text)


# --- building blocks ----------------------------------------------------------


def test_kij_zero_passes_no_interactions_and_others_are_symmetric() -> None:
    assert study.interactions(ETHANE, 0.0) is None
    assert study.interactions(ETHANE, 0.01) == {
        (METHANE.name, ETHANE.name): 0.01,
        (ETHANE.name, METHANE.name): 0.01,
    }


def test_outcomes_are_named_from_the_engine_codes() -> None:
    assert study.classify("converged", ()) == "converged"
    assert study.classify("not_found", ("SATURATION_BRACKET_NOT_FOUND",)) == "not_found"
    hidden = ("HIDDEN_SATURATION_ROOT", "MULTIPLE_SATURATION_ROOTS")
    assert study.classify("inconclusive", hidden) == "hidden_root"
    assert study.classify("inconclusive", hidden[1:]) == "multiple_roots"
    assert study.classify("inconclusive", ()) == "inconclusive_other"
    assert study.classify("failed", ()) == "failed"


def test_isotherms_group_states_within_one_kelvin() -> None:
    groups = study.isotherms(_system_states("ch4_c3"))
    assert sum(len(group) for group in groups) == 23
    for group in groups:
        temperatures = [state.temperature_k for state in group]
        assert all(
            b - a < 1.0 for a, b in zip(temperatures, temperatures[1:], strict=False)
        )
    for before, after in zip(groups, groups[1:], strict=False):
        assert after[0].temperature_k - before[-1].temperature_k >= 1.0


# --- kij = 0 is the validation record -------------------------------------------


@pytest.mark.parametrize("system", study.PRODUCTION_SYSTEMS)
@pytest.mark.parametrize("kind", study.DIRECTIONS)
def test_kij_zero_reproduces_the_module17_record(system: str, kind: str) -> None:
    record = next(
        item
        for item in json.loads(MODULE17.read_text(encoding="utf-8"))["systems"]
        if item["system_id"] == system
    )[f"production_selected_{kind}_metrics"]
    outcomes = [study.solve(state, kind, 0.0) for state in _system_states(system)]
    stats = study.summarize(outcomes)

    assert stats["states"] == record["source_count"]
    assert stats["converged"] == record["success_count"]
    assert stats["states"] - stats["converged"] == record["failure_count"]
    assert stats["aard_percent"] == pytest.approx(
        record["pressure_aard_percent"], rel=1e-9
    )
    # The committed study row at kij = 0 says the same.
    row = next(
        r
        for r in _rows(study.SUMMARY_FILE)
        if r["system_id"] == system and float(r["kij"]) == 0.0 and r["kind"] == kind
    )
    assert int(row["converged"]) == record["success_count"]
    assert float(row["aard_percent"]) == pytest.approx(
        record["pressure_aard_percent"], rel=1e-9
    )


# --- the committed files are consistent with each other -------------------------


def test_summary_csv_aggregates_the_state_rows() -> None:
    groups: dict[tuple[str, float, str], list[study.Outcome]] = {}
    for row in _rows(study.STATES_FILE):
        outcome = study.Outcome(
            system_id=row["system_id"],
            point_id=row["point_id"],
            kind=row["kind"],
            kij=float(row["kij"]),
            temperature_k=float(row["temperature_k"]),
            measured_pressure_pa=float(row["measured_pressure_pa"]),
            status=row["status"],
            category=row["category"],
            predicted_pressure_pa=_value(row["predicted_pressure_pa"]),
            percent_error=_value(row["percent_error"]),
            diagnostic_codes=row["diagnostic_codes"],
            failure_reason=row["failure_reason"],
        )
        groups.setdefault((outcome.system_id, outcome.kij, outcome.kind), []).append(
            outcome
        )
    summary = _rows(study.SUMMARY_FILE)
    assert len(summary) == len(groups)
    for row in summary:
        stats = study.summarize(
            groups[(row["system_id"], float(row["kij"]), row["kind"])]
        )
        for key in (
            "states",
            "converged",
            "not_found",
            "hidden_root",
            "multiple_roots",
        ):
            assert int(row[key]) == stats[key], (row["system_id"], row["kij"], key)
        assert _value(row["aard_percent"]) == (
            None
            if stats["aard_percent"] is None
            else pytest.approx(stats["aard_percent"])
        )


def test_every_category_comes_from_the_engine_status_and_codes() -> None:
    for row in _rows(study.STATES_FILE):
        codes = row["diagnostic_codes"].split("|") if row["diagnostic_codes"] else []
        assert row["category"] == study.classify(row["status"], codes)
        assert (row["predicted_pressure_pa"] != "") == (row["category"] == "converged")


def test_the_fit_follows_from_the_committed_fine_grid() -> None:
    grid: dict[str, study.BubbleGrid] = {}
    for row in _rows(study.FINE_FILE):
        grid.setdefault(row["system_id"], {})[(row["point_id"], float(row["kij"]))] = (
            row["category"],
            _value(row["percent_error"]),
        )
    for system, committed in _fit()["fits"].items():
        recomputed = study.fit_from_grid(_system_states(system), grid[system])
        for key, value in recomputed.items():
            # CSV and JSON both store floats by repr, so equality is exact.
            assert committed[key] == value, (system, key)


def test_the_report_renders_from_the_committed_files() -> None:
    assert render(ROOT) == (ROOT / study.REPORT_FILE).read_text(encoding="utf-8")


# --- committed results reproduce with the engine --------------------------------


@pytest.mark.parametrize("system", study.PRODUCTION_SYSTEMS)
def test_the_refined_optimum_reproduces(system: str) -> None:
    fit = _fit()["fits"][system]
    fixed = [s for s in _system_states(system) if s.point_id in fit["common_point_ids"]]
    assert len(fixed) == fit["common_n"]
    assert study.fixed_set_aard(fixed, fit["optimum"]) == pytest.approx(
        fit["aard_at_optimum"], rel=1e-9
    )
    assert fit["aard_at_optimum"] <= fit["aard_at_grid_optimum"] + 1e-12


@pytest.mark.parametrize("system", study.PRODUCTION_SYSTEMS)
def test_dew_rows_at_the_fitted_kij_reproduce(system: str) -> None:
    optimum = _fit()["fits"][system]["optimum"]
    rows = [
        r
        for r in _rows(study.STATES_FILE)
        if r["system_id"] == system
        and r["kind"] == "dew"
        and float(r["kij"]) == optimum
    ]
    by_id = {state.point_id: state for state in _system_states(system)}
    # One state per outcome category, so every kind of answer is re-checked.
    sample = {row["category"]: row for row in rows}.values()
    for row in sample:
        outcome = study.solve(by_id[row["point_id"]], "dew", optimum)
        assert outcome.category == row["category"], row["point_id"]
        assert outcome.diagnostic_codes == row["diagnostic_codes"]
        if row["predicted_pressure_pa"]:
            assert outcome.predicted_pressure_pa == pytest.approx(
                float(row["predicted_pressure_pa"]), rel=1e-9
            )


# --- the P3 hook ----------------------------------------------------------------


def test_the_optional_kij_leaves_the_published_p3_output_unchanged() -> None:
    dataset = load_experimental_vle_dataset(
        ROOT / study.DATA_FILE, ROOT / study.MANIFEST_FILE
    )
    point = next(p for p in dataset.points if p.source_point_id == "may2015_ch4_c3_009")
    default = asdict(analyze_dew_state(point))
    explicit = asdict(analyze_dew_state(point, 0.0))
    assert explicit == default
    published = next(
        row
        for row in csv.DictReader(P3_RESULTS.open(encoding="utf-8", newline=""))
        if row["source_point_id"] == point.source_point_id
    )
    for key, value in default.items():
        if isinstance(value, float):
            assert float(published[key]) == pytest.approx(value, rel=1e-9), key
        elif value is not None:
            assert published[key] == str(value), key
