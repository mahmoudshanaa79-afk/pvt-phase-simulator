"""Run Module 17 validation with and without Newton refinement (read-only).

Proposal P4, option B. The frozen validation calls the saturation solver with its
defaults, which leave Newton refinement off. This tool evaluates the same immutable
dataset twice with the unchanged engine:

* **default**: exactly the production record, which must reproduce the frozen
  ``docs/validation/module17_vle_validation.csv`` byte for byte;
* **Newton**: the same call with the engine's existing ``saturation_newton_enabled``
  option switched on, applied inside this process only.

No engine file, dataset or protected artifact is modified. The frozen artifacts under
``docs/validation`` are only read, and results are written to ``docs/investigations``.
Nothing is fitted, and no failure is hidden: a state that does not converge keeps the
engine's own status and reason.
"""

from __future__ import annotations

import argparse
import csv
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

import pvt_phase_simulator.experimental_validation as validation
from pvt_phase_simulator.experimental_validation import (
    ExperimentalVLEDataset,
    ExperimentalVLEValidationResult,
    ValidationDirectionResult,
    load_experimental_vle_dataset,
    validate_experimental_dataset,
)

DIRECTIONS = ("bubble", "dew")
#: The frozen artifact was written on another machine; floats agree to ~1e-13 across
#: platforms, so "reproduces" means identical outcomes and pressures within this.
REPRODUCTION_RELATIVE_TOLERANCE = 1e-9
#: Pressures closer than this are the same answer; only larger moves count as changes.
CHANGE_RELATIVE_TOLERANCE = 1e-6
CSV_FIELDS = (
    "system_id",
    "source_point_id",
    "temperature_k",
    "measured_pressure_pa",
    "direction",
    "default_status",
    "default_predicted_pressure_pa",
    "default_percent_error",
    "newton_status",
    "newton_predicted_pressure_pa",
    "newton_percent_error",
    "newton_failure_reason",
    "outcome_changed",
    "pr_dew_roots",
    "default_counts_as_accuracy",
    "newton_counts_as_accuracy",
)


@dataclass(frozen=True, slots=True)
class Comparison:
    """Both validation runs over one dataset."""

    default: tuple[ExperimentalVLEValidationResult, ...]
    newton: tuple[ExperimentalVLEValidationResult, ...]
    default_matches_frozen_csv: bool | None


@contextmanager
def newton_refinement_enabled() -> Iterator[None]:
    """Switch the engine's Newton option on for validation calls, in-process only."""

    original: Callable[..., Any] = validation.calculate_saturation_pressure

    def with_newton(*args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("saturation_newton_enabled", True)
        return original(*args, **kwargs)

    validation.calculate_saturation_pressure = with_newton  # type: ignore[assignment]
    try:
        yield
    finally:
        validation.calculate_saturation_pressure = original  # type: ignore[assignment]


def compare(
    dataset: ExperimentalVLEDataset, frozen_csv: Path | None = None
) -> Comparison:
    """Evaluate the dataset with the defaults and again with Newton refinement."""

    default = validate_experimental_dataset(dataset)
    with newton_refinement_enabled():
        newton = validate_experimental_dataset(dataset)
    matches: bool | None = None
    if frozen_csv is not None:
        matches = reproduces_frozen_record(default, frozen_csv.read_text("utf-8"))
    return Comparison(default, newton, matches)


def reproduces_frozen_record(
    results: tuple[ExperimentalVLEValidationResult, ...], frozen_csv_text: str
) -> bool:
    """True when every row has the frozen outcome and a pressure within tolerance."""

    frozen = {
        row["source_point_id"]: row
        for row in csv.DictReader(StringIO(frozen_csv_text, newline=""))
    }
    for result in results:
        row = frozen.get(result.point.source_point_id)
        if row is None:
            return False
        for direction in DIRECTIONS:
            current = _direction(result, direction)
            if row[f"{direction}_status"] != current.status:
                return False
            if row[f"{direction}_failure_reason"] != (current.failure_reason or ""):
                return False
            recorded = row[f"{direction}_predicted_pressure_pa"]
            if (recorded == "") != (current.predicted_pressure_pa is None):
                return False
            if current.predicted_pressure_pa is not None and not _close(
                float(recorded),
                current.predicted_pressure_pa,
                REPRODUCTION_RELATIVE_TOLERANCE,
            ):
                return False
    return True


def _close(first: float, second: float, relative_tolerance: float) -> bool:
    return abs(first - second) <= relative_tolerance * abs(first)


def _direction(
    result: ExperimentalVLEValidationResult, direction: str
) -> ValidationDirectionResult:
    return result.bubble if direction == "bubble" else result.dew


def _changed(
    before: ValidationDirectionResult, after: ValidationDirectionResult
) -> bool:
    if before.status != after.status:
        return True
    if before.predicted_pressure_pa is None or after.predicted_pressure_pa is None:
        return before.predicted_pressure_pa is not after.predicted_pressure_pa
    return not _close(
        before.predicted_pressure_pa,
        after.predicted_pressure_pa,
        CHANGE_RELATIVE_TOLERANCE,
    )


def largest_relative_pressure_difference(comparison: Comparison) -> float:
    """Largest move among states both runs converge on (zero if none)."""

    largest = 0.0
    for before, after in zip(comparison.default, comparison.newton, strict=True):
        for direction in DIRECTIONS:
            old, new = _direction(before, direction), _direction(after, direction)
            if old.predicted_pressure_pa and new.predicted_pressure_pa:
                largest = max(
                    largest,
                    abs(new.predicted_pressure_pa - old.predicted_pressure_pa)
                    / old.predicted_pressure_pa,
                )
    return largest


def changed_states(comparison: Comparison) -> list[tuple[str, str, str]]:
    """(system, source point, direction) for every state whose outcome differs."""

    changes: list[tuple[str, str, str]] = []
    for before, after in zip(comparison.default, comparison.newton, strict=True):
        for direction in DIRECTIONS:
            if _changed(_direction(before, direction), _direction(after, direction)):
                changes.append(
                    (before.point.system_id, before.point.source_point_id, direction)
                )
    return changes


def _number(value: float | None, digits: int) -> str:
    return "" if value is None else f"{value:.{digits}f}"


def one_root_of_several(
    result: ExperimentalVLEValidationResult, direction: str
) -> bool:
    """A dew result at a state where PR has more than one dew root (the P2 issue)."""

    return (
        direction == "dew" and result.dew_branch_diagnostic.multiple_dew_roots_detected
    )


def counts_as_accuracy(result: ExperimentalVLEValidationResult, direction: str) -> bool:
    """Converged, and not just one root of several, so it says something about PR."""

    return _direction(result, direction).predicted_pressure_pa is not None and (
        not one_root_of_several(result, direction)
    )


def render_csv(comparison: Comparison) -> str:
    """One row per state and direction with both runs' engine outcomes."""

    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for before, after in zip(comparison.default, comparison.newton, strict=True):
        point = before.point
        for direction in DIRECTIONS:
            old, new = _direction(before, direction), _direction(after, direction)
            writer.writerow(
                {
                    "system_id": point.system_id,
                    "source_point_id": point.source_point_id,
                    "temperature_k": f"{point.temperature_k:.2f}",
                    "measured_pressure_pa": f"{point.pressure_pa:.1f}",
                    "direction": direction,
                    "default_status": old.status,
                    "default_predicted_pressure_pa": _number(
                        old.predicted_pressure_pa, 1
                    ),
                    "default_percent_error": _number(old.pressure_percent_error, 3),
                    "newton_status": new.status,
                    "newton_predicted_pressure_pa": _number(
                        new.predicted_pressure_pa, 1
                    ),
                    "newton_percent_error": _number(new.pressure_percent_error, 3),
                    "newton_failure_reason": new.failure_reason or "",
                    "outcome_changed": str(_changed(old, new)).lower(),
                    "pr_dew_roots": (
                        len(before.dew_branch_diagnostic.roots)
                        if direction == "dew"
                        else ""
                    ),
                    "default_counts_as_accuracy": str(
                        counts_as_accuracy(before, direction)
                    ).lower(),
                    "newton_counts_as_accuracy": str(
                        counts_as_accuracy(after, direction)
                    ).lower(),
                }
            )
    return stream.getvalue()


@dataclass(frozen=True, slots=True)
class RunStatistics:
    """Counts and AARD for one system, direction and run."""

    sources: int
    converged: int
    one_root_of_several: int
    accuracy_states: int
    aard_percent: float | None


def _statistics(
    results: tuple[ExperimentalVLEValidationResult, ...], system_id: str, direction: str
) -> RunStatistics:
    chosen = [item for item in results if item.point.system_id == system_id]
    converged = [
        item for item in chosen if _direction(item, direction).predicted_pressure_pa
    ]
    accuracy = [item for item in chosen if counts_as_accuracy(item, direction)]
    errors = [
        abs(float(_direction(item, direction).pressure_percent_error or 0.0))
        for item in accuracy
    ]
    return RunStatistics(
        sources=len(chosen),
        converged=len(converged),
        one_root_of_several=sum(
            one_root_of_several(item, direction) for item in converged
        ),
        accuracy_states=len(accuracy),
        aard_percent=sum(errors) / len(errors) if errors else None,
    )


def _aard(statistics: RunStatistics) -> str:
    value = statistics.aard_percent
    return "n/a" if value is None else f"{value:.2f} % (n={statistics.accuracy_states})"


def _systems(comparison: Comparison) -> list[str]:
    return list(dict.fromkeys(item.point.system_id for item in comparison.default))


def _outcome(result: ExperimentalVLEValidationResult, direction: str) -> str:
    direction_result = _direction(result, direction)
    if direction_result.predicted_pressure_pa is None:
        return direction_result.status
    text = f"{direction_result.predicted_pressure_pa / 1e6:.3f} MPa"
    if one_root_of_several(result, direction):
        roots = len(result.dew_branch_diagnostic.roots)
        return f"{text}, one root of {roots}"
    return f"{text} ({_number(direction_result.pressure_percent_error, 1)} %)"


def render_markdown(comparison: Comparison) -> str:
    """The side-by-side report. Every number is recomputed from the engine."""

    if comparison.default_matches_frozen_csv is None:
        reproduces = "not checked"
    else:
        reproduces = "yes" if comparison.default_matches_frozen_csv else "NO"
    lines = [
        "# Validation with and without Newton refinement",
        "",
        "Generated by `tools/run_validation_newton_comparison.py` (proposal P4,",
        "option B). The frozen Module 17 artifacts are not regenerated; this report",
        "only sits beside them.",
        "",
        "- **Default**: the production record. The solver's defaults leave Newton",
        "  refinement off.",
        "- **Newton**: the same dataset and solver with the engine's existing",
        "  `saturation_newton_enabled` option on.",
        "- Default run reproduces the frozen record (same status and reason, pressure",
        f"  within {REPRODUCTION_RELATIVE_TOLERANCE:.0e} relative; the last digits",
        f"  differ across platforms): **{reproduces}**.",
        "- A state counts as changed when its status differs or its pressure moves",
        f"  by more than {CHANGE_RELATIVE_TOLERANCE:.0e} relative.",
        "",
        "## Bubble pressure",
        "",
        "| System | Sources | Converged (default) | Converged (Newton) |"
        " AARD (default) | AARD (Newton) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for system_id in _systems(comparison):
        old = _statistics(comparison.default, system_id, "bubble")
        new = _statistics(comparison.newton, system_id, "bubble")
        lines.append(
            f"| {system_id} | {old.sources} | {old.converged} | {new.converged} | "
            f"{_aard(old)} | {_aard(new)} |"
        )
    lines += [
        "",
        "## Dew pressure",
        "",
        "A converged dew pressure at a state where PR has more than one dew root is",
        "**one root of several**. It is not an accuracy result, because the measured",
        "state does not say which root is meant (`docs/DEW_INVESTIGATION.md`). Those",
        "states are counted in the converged columns, listed in the next columns, and",
        "left out of the AARD.",
        "",
        "Since P2 the default (scanning) solver reports such states as ambiguous, so",
        "its column of multi-root results is zero. Newton refinement is a local",
        "solve from the Wilson estimate: it returns the root near that estimate and",
        "does not check whether another root exists.",
        "",
        "| System | Sources | Converged (default) | Converged (Newton) |"
        " One root of several (default) | One root of several (Newton) |"
        " AARD, other states (default) | AARD, other states (Newton) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for system_id in _systems(comparison):
        old = _statistics(comparison.default, system_id, "dew")
        new = _statistics(comparison.newton, system_id, "dew")
        lines.append(
            f"| {system_id} | {old.sources} | {old.converged} | {new.converged} | "
            f"{old.one_root_of_several} | {new.one_root_of_several} | "
            f"{_aard(old)} | {_aard(new)} |"
        )
    by_point = {item.point.source_point_id: item for item in comparison.default}
    newton_by_point = {item.point.source_point_id: item for item in comparison.newton}
    lines += ["", "## States whose outcome changes", ""]
    changes = changed_states(comparison)
    if not changes:
        lines.append("None.")
    else:
        lines += [
            "| System | State | Direction | Default | Newton |",
            "|---|---|---|---|---|",
        ]
        for system_id, point_id, direction in changes:
            lines.append(
                f"| {system_id} | {point_id} | {direction} | "
                f"{_outcome(by_point[point_id], direction)} | "
                f"{_outcome(newton_by_point[point_id], direction)} |"
            )
    lines += ["", "## Converged in both runs at different pressures", ""]
    differing = [
        (system_id, point_id, direction)
        for system_id, point_id, direction in changes
        if _direction(by_point[point_id], direction).predicted_pressure_pa
        and _direction(newton_by_point[point_id], direction).predicted_pressure_pa
    ]
    if not differing:
        lines.append("None.")
    else:
        lines += [
            "Each run returned a different root. Neither is an accuracy result.",
            "",
            "| System | State | Direction | Default | Newton |",
            "|---|---|---|---|---|",
        ]
        for system_id, point_id, direction in differing:
            lines.append(
                f"| {system_id} | {point_id} | {direction} | "
                f"{_outcome(by_point[point_id], direction)} | "
                f"{_outcome(newton_by_point[point_id], direction)} |"
            )
    lines += [
        "",
        "A state that does not converge keeps the engine's own status and reason in",
        "the CSV next to this report. The measured pressure is only the comparison",
        "value; it never selects a root.",
        "",
    ]
    return "\n".join(lines)


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
    comparison = compare(dataset, root / "docs/validation/module17_vle_validation.csv")
    output = root / "docs/investigations"
    output.mkdir(parents=True, exist_ok=True)
    (output / "validation_newton_comparison.csv").write_text(
        render_csv(comparison), encoding="utf-8", newline=""
    )
    (output / "validation_newton_comparison.md").write_text(
        render_markdown(comparison), encoding="utf-8", newline=""
    )
    print(render_markdown(comparison))
    frozen_rows = (root / "docs/validation/module17_vle_validation.csv").read_text(
        "utf-8"
    )
    if (
        comparison.default_matches_frozen_csv is False
        or len(comparison.default) != len(frozen_rows.splitlines()) - 1
    ):
        raise SystemExit("The default run no longer reproduces the frozen artifact.")


if __name__ == "__main__":
    main()
