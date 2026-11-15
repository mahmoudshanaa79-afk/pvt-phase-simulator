"""P10 survey: the app's phase envelope with and without the global fallback.

Proposal P10 (b) would turn off the envelope corrector's global fallback in the
app's envelope settings (``allow_global_fallback=False``) to save time. The
owner asked for a wider survey first, with no engine or app change. This tool
runs the app's own envelope calculation (the body of the Phase Envelope page's
cached function) on the 16 cases of ``tools/run_envelope_survey.py``, twice:

* **on**: the shipped settings (``allow_global_fallback=True``);
* **off**: the same settings with ``allow_global_fallback=False``, set inside
  this process only.

For each case and branch it records the accepted points (count, exact equality
of their values and of their full records, largest differences), the
termination reason, whether any accepted point came from the global fallback,
how often the fallback was tried, the rejected-attempt counts, and the wall
time. Nothing in the engine or the app is changed.

Usage::

    uv run python tools/run_p10_survey.py --output docs/investigations/p10_survey.csv
"""

from __future__ import annotations

import argparse
import csv
import logging
import math
import sys
import time
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pvt_phase_simulator.eos.phase_envelope import (  # noqa: E402
    EnvelopeContinuationSettings,
    EnvelopeCorrectionSource,
    PhaseEnvelopeBranchResult,
    PhaseEnvelopePoint,
    PhaseEnvelopeResult,
)
from pvt_phase_simulator_ui import views  # noqa: E402
from pvt_phase_simulator_ui.adapters import validate_scientific_inputs  # noqa: E402
from tools.engine_fingerprint import canonical  # noqa: E402
from tools.run_envelope_survey import CASES  # noqa: E402

#: Any pressure in range; the envelope depends on composition and temperature.
OPERATING_PRESSURE_MPA = 5.0
BRANCHES = ("bubble", "dew")
FIELDS = (
    "case",
    "methane_pct",
    "ethane_pct",
    "propane_pct",
    "temperature_k",
    "seconds_on",
    "seconds_off",
    *(
        f"{branch}_{name}"
        for branch in BRANCHES
        for name in (
            "points_on",
            "points_off",
            "values_identical",
            "records_identical",
            "max_abs_temperature_diff_k",
            "max_rel_pressure_diff",
            "reason_on",
            "reason_off",
            "fallback_points_on",
            "fallback_tries_on",
            "rejected_on",
            "rejected_off",
        )
    ),
)


def _settings_without_fallback(**kwargs: Any) -> EnvelopeContinuationSettings:
    return EnvelopeContinuationSettings(**kwargs, allow_global_fallback=False)


def run_envelope(
    composition: tuple[float, float, float], temperature_k: float, fallback: bool
) -> tuple[PhaseEnvelopeResult, float]:
    """The Phase Envelope page's calculation, with or without the fallback."""

    inputs = validate_scientific_inputs(
        composition, temperature_k, OPERATING_PRESSURE_MPA
    )
    body = views._calculate_envelope.__wrapped__
    original = views.EnvelopeContinuationSettings
    if not fallback:
        views.EnvelopeContinuationSettings = _settings_without_fallback
    try:
        start = time.perf_counter()
        result = body(inputs)
        seconds = time.perf_counter() - start
    finally:
        views.EnvelopeContinuationSettings = original
    settings = result.bubble_branch.settings
    assert settings.allow_global_fallback is fallback
    return result, seconds


def _values(point: PhaseEnvelopePoint) -> str:
    saturation = point.saturation_result
    return canonical(
        (
            saturation.temperature_k,
            saturation.pressure_pa,
            saturation.incipient_composition,
            point.log_k_values,
            point.root_separation,
            point.composition_separation,
        )
    )


def _all_attempts(branch: PhaseEnvelopeBranchResult) -> Iterable[Any]:
    yield from branch.rejected_attempts
    for point in branch.points:
        yield from point.correction_attempts


def compare_branch(
    on: PhaseEnvelopeBranchResult, off: PhaseEnvelopeBranchResult
) -> dict[str, object]:
    common = list(zip(on.points, off.points, strict=False))
    same_count = len(on.points) == len(off.points)
    temperature_diffs = [abs(a.temperature_k - b.temperature_k) for a, b in common]
    pressure_diffs = [
        abs(a.pressure_pa - b.pressure_pa) / abs(a.pressure_pa) for a, b in common
    ]
    return {
        "points_on": len(on.points),
        "points_off": len(off.points),
        "values_identical": same_count
        and all(_values(a) == _values(b) for a, b in common),
        "records_identical": same_count
        and all(canonical(a) == canonical(b) for a, b in common),
        "max_abs_temperature_diff_k": max(temperature_diffs, default=0.0),
        "max_rel_pressure_diff": max(pressure_diffs, default=0.0),
        "reason_on": on.termination_reason.value,
        "reason_off": off.termination_reason.value,
        "fallback_points_on": sum(
            point.correction_source is EnvelopeCorrectionSource.GLOBAL_FALLBACK
            for point in on.points
        ),
        "fallback_tries_on": sum(
            attempt.source is EnvelopeCorrectionSource.GLOBAL_FALLBACK
            for attempt in _all_attempts(on)
        ),
        "rejected_on": len(on.rejected_attempts),
        "rejected_off": len(off.rejected_attempts),
    }


def survey_case(
    label: str, composition: tuple[float, float, float], temperature_k: float
) -> dict[str, object]:
    logging.disable(logging.CRITICAL)
    on, seconds_on = run_envelope(composition, temperature_k, fallback=True)
    off, seconds_off = run_envelope(composition, temperature_k, fallback=False)
    row: dict[str, object] = {
        "case": label,
        "methane_pct": composition[0],
        "ethane_pct": composition[1],
        "propane_pct": composition[2],
        "temperature_k": temperature_k,
        "seconds_on": round(seconds_on, 1),
        "seconds_off": round(seconds_off, 1),
    }
    for branch in BRANCHES:
        compared = compare_branch(
            getattr(on, f"{branch}_branch"), getattr(off, f"{branch}_branch")
        )
        row.update({f"{branch}_{key}": value for key, value in compared.items()})
    return row


def write(path: Path, rows: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: (repr(value) if isinstance(value, float) else value)
                    for key, value in row.items()
                }
            )


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _flag(text: str) -> bool:
    return text == "True"


def summary(rows: Sequence[dict[str, str]]) -> dict[str, object]:
    """Every number the investigation note quotes, from the CSV."""

    def branches(row: dict[str, str]) -> Iterable[str]:
        return (f"{branch}_" for branch in BRANCHES)

    pairs = [(row, prefix) for row in rows for prefix in branches(row)]
    seconds_on = sum(float(row["seconds_on"]) for row in rows)
    seconds_off = sum(float(row["seconds_off"]) for row in rows)
    return {
        "cases": len(rows),
        "branches": len(pairs),
        "points_on": sum(int(row[p + "points_on"]) for row, p in pairs),
        "points_off": sum(int(row[p + "points_off"]) for row, p in pairs),
        "values_identical": sum(_flag(row[p + "values_identical"]) for row, p in pairs),
        "records_identical": sum(
            _flag(row[p + "records_identical"]) for row, p in pairs
        ),
        "reasons_identical": sum(
            row[p + "reason_on"] == row[p + "reason_off"] for row, p in pairs
        ),
        "fallback_points_on": sum(
            int(row[p + "fallback_points_on"]) for row, p in pairs
        ),
        "fallback_tries_on": sum(int(row[p + "fallback_tries_on"]) for row, p in pairs),
        "rejected_on": sum(int(row[p + "rejected_on"]) for row, p in pairs),
        "rejected_off": sum(int(row[p + "rejected_off"]) for row, p in pairs),
        "max_abs_temperature_diff_k": max(
            float(row[p + "max_abs_temperature_diff_k"]) for row, p in pairs
        ),
        "max_rel_pressure_diff": max(
            float(row[p + "max_rel_pressure_diff"]) for row, p in pairs
        ),
        "seconds_on": round(seconds_on, 1),
        "seconds_off": round(seconds_off, 1),
        "saving_percent": round(100.0 * (1.0 - seconds_off / seconds_on), 1)
        if seconds_on > 0
        else math.nan,
    }


def table(rows: Sequence[dict[str, str]]) -> str:
    """The per-case table of the investigation note, from the CSV."""

    lines = [
        "| Case | Points on/off (bubble, dew) | Identical points "
        "| Reasons (bubble, dew) | Fallback points / tries (on) "
        "| Rejected on/off | Time on/off (s) |",
        "|---|---|---|---|---|---|---:|",
    ]
    for row in rows:
        points = ", ".join(
            f"{row[f'{b}_points_on']}/{row[f'{b}_points_off']}" for b in BRANCHES
        )
        identical = (
            "yes"
            if all(_flag(row[f"{b}_records_identical"]) for b in BRANCHES)
            else "values only"
            if all(_flag(row[f"{b}_values_identical"]) for b in BRANCHES)
            else "**no**"
        )
        reasons = ", ".join(
            row[f"{b}_reason_on"]
            if row[f"{b}_reason_on"] == row[f"{b}_reason_off"]
            else f"**{row[f'{b}_reason_on']} → {row[f'{b}_reason_off']}**"
            for b in BRANCHES
        )
        fallback = ", ".join(
            f"{row[f'{b}_fallback_points_on']} / {row[f'{b}_fallback_tries_on']}"
            for b in BRANCHES
        )
        rejected = ", ".join(
            f"{row[f'{b}_rejected_on']}/{row[f'{b}_rejected_off']}" for b in BRANCHES
        )
        lines.append(
            f"| {row['case']} | {points} | {identical} | {reasons} | {fallback} | "
            f"{rejected} | {float(row['seconds_on']):.1f} / "
            f"{float(row['seconds_off']):.1f} |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--cases", type=str, default="", help="comma-separated case indexes"
    )
    arguments = parser.parse_args()
    indexes = (
        [int(item) for item in arguments.cases.split(",")]
        if arguments.cases
        else list(range(len(CASES)))
    )
    rows = []
    for index in indexes:
        label, composition, temperature = CASES[index]
        row = survey_case(label, composition, temperature)
        rows.append(row)
        print(
            f"{index:2d} {label}: on {row['seconds_on']} s, "
            f"off {row['seconds_off']} s, "
            f"bubble {row['bubble_points_on']}/{row['bubble_points_off']}, "
            f"dew {row['dew_points_on']}/{row['dew_points_off']}",
            flush=True,
        )
    write(arguments.output, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
