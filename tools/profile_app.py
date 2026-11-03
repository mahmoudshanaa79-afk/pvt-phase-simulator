"""Time the Streamlit app: import, page renders, RUN actions, exports.

Every timing is the median of ``--runs`` repetitions with the app's caches
cleared before each repetition, so it is a first-run (cold-cache) time. A
"warm" row repeats an action with the cache populated. Actions are timed both
through Streamlit's AppTest (what a user waits for, including page rendering)
and as direct engine calls with the same inputs (the engine's share).

Usage::

    uv run python tools/profile_app.py --runs 3 \
        --output docs/investigations/app_performance_before.csv

Nothing here changes the app or the engine; it only measures.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import platform
import statistics
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "streamlit_app.py"
PAGES = ROOT / "src" / "pvt_phase_simulator_ui" / "pages"
PAGE_FILES = (
    "overview.py",
    "phase_envelope.py",
    "critical_point.py",
    "engineering_sweeps.py",
    "validation.py",
    "diagnostics.py",
)
#: (page, button label) in the order a user would run them.
ACTIONS = (
    ("phase_envelope.py", "RUN PHASE ENVELOPE"),
    ("critical_point.py", "RUN CRITICAL SOLVER"),
    ("critical_point.py", "RUN CRITICALITY MAP"),
    ("engineering_sweeps.py", "RUN SWEEP"),
    ("validation.py", "GENERATE VALIDATION FIGURES"),
)


@dataclass(frozen=True)
class Timing:
    group: str
    label: str
    case: str
    seconds: tuple[float, ...]

    @property
    def median(self) -> float:
        return statistics.median(self.seconds)


def machine() -> str:
    model = "unknown CPU"
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                model = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return (
        f"{model}, {os.cpu_count()} logical CPUs, {platform.system()} "
        f"{platform.release()}, Python {platform.python_version()}"
    )


def _timed(action: Callable[[], Any]) -> float:
    start = time.perf_counter()
    action()
    return time.perf_counter() - start


def _subprocess_seconds(code: str) -> float:
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return float(completed.stdout.strip().splitlines()[-1])


def time_cold_start(runs: int) -> list[Timing]:
    imports = tuple(
        _subprocess_seconds(
            "import time; t = time.perf_counter(); "
            "import pvt_phase_simulator_ui.app, pvt_phase_simulator_ui.views; "
            "print(time.perf_counter() - t)"
        )
        for _ in range(runs)
    )
    first_run = tuple(
        _subprocess_seconds(
            "import logging, time; logging.disable(logging.CRITICAL); "
            "from streamlit.testing.v1 import AppTest; t = time.perf_counter(); "
            f"AppTest.from_file({str(ENTRY)!r}, default_timeout=300).run(); "
            "print(time.perf_counter() - t)"
        )
        for _ in range(runs)
    )
    return [
        Timing("start", "Import the app modules (fresh process)", "-", imports),
        Timing("start", "First script run (fresh process)", "-", first_run),
    ]


def _clear_caches() -> None:
    import streamlit as st

    st.cache_data.clear()
    st.cache_resource.clear()


def _button(app: Any, label: str) -> Any:
    return next(item for item in app.button if item.label == label)


def time_page_renders(runs: int) -> list[Timing]:
    from streamlit.testing.v1 import AppTest

    samples: dict[str, list[float]] = {page: [] for page in PAGE_FILES}
    for _ in range(runs):
        _clear_caches()
        app = AppTest.from_file(ENTRY, default_timeout=300).run()
        for page in PAGE_FILES:
            samples[page].append(
                _timed(lambda page=page, app=app: app.switch_page(PAGES / page).run())
            )
    return [
        Timing(
            "page",
            f"First render: {page.removesuffix('.py')}",
            "no results",
            tuple(values),
        )
        for page, values in samples.items()
    ]


def _example_labels() -> list[str]:
    from pvt_phase_simulator_ui.state import INPUT_EXAMPLES

    return [example.label for example in INPUT_EXAMPLES]


def time_actions(runs: int, examples: list[str]) -> list[Timing]:
    from streamlit.testing.v1 import AppTest

    timings: list[Timing] = []
    for example in examples:
        samples: dict[str, list[float]] = {}
        for _ in range(runs):
            _clear_caches()
            app = AppTest.from_file(ENTRY, default_timeout=900).run()
            app.selectbox(key="input_example").set_value(example).run()
            samples.setdefault("RUN FLASH", []).append(
                _timed(lambda app=app: _button(app, "RUN FLASH").click().run())
            )
            for page, label in ACTIONS:
                app.switch_page(PAGES / page).run()
                samples.setdefault(label, []).append(
                    _timed(
                        lambda label=label, app=app: _button(app, label).click().run()
                    )
                )
            samples.setdefault(
                "Overview with every result (exports, report)", []
            ).append(
                _timed(lambda app=app: app.switch_page(PAGES / "overview.py").run())
            )
            # The same envelope again: the bounded cache answers.
            app.switch_page(PAGES / "phase_envelope.py").run()
            samples.setdefault("RUN PHASE ENVELOPE again (warm cache)", []).append(
                _timed(lambda app=app: _button(app, "RUN PHASE ENVELOPE").click().run())
            )
        timings += [
            Timing("action (AppTest)", label, example, tuple(values))
            for label, values in samples.items()
        ]
    return timings


def _default_inputs() -> Any:
    from pvt_phase_simulator_ui.adapters import validate_scientific_inputs
    from pvt_phase_simulator_ui.state import INPUT_EXAMPLES

    example = INPUT_EXAMPLES[0]
    return validate_scientific_inputs(
        (example.methane_pct, example.ethane_pct, example.propane_pct),
        example.temperature_k,
        example.pressure_pa,
        pressure_unit="Pa",
    )


def _sweep_request(inputs: Any) -> Any:
    from pvt_phase_simulator_ui.sweeps import (
        DEFAULT_SWEEP_POINTS,
        validate_sweep_request,
    )

    return validate_sweep_request(
        "pressure",
        inputs.composition_mol_percent,
        fixed_value=inputs.temperature_k,
        start=1.0e6,
        end=20.0e6,
        points=DEFAULT_SWEEP_POINTS,
        temperature_unit="K",
        pressure_unit="Pa",
        kij=inputs.kij,
    )


def time_direct_calls(runs: int) -> tuple[list[Timing], dict[str, Any]]:
    from pvt_phase_simulator_ui import app as ui_app
    from pvt_phase_simulator_ui import views
    from pvt_phase_simulator_ui.sweeps import run_sweep

    inputs = _default_inputs()
    calls: dict[str, Callable[[], Any]] = {
        "flash": lambda: ui_app._cached_flash.__wrapped__(inputs),
        "phase envelope": lambda: views._calculate_envelope.__wrapped__(inputs),
        "extended overlay": lambda: views._calculate_extended_envelope.__wrapped__(
            inputs
        ),
        "bubble and dew at the operating temperature": (
            lambda: views._calculate_operating_saturation.__wrapped__(inputs)
        ),
        "critical point": lambda: views._calculate_critical.__wrapped__(inputs),
        "criticality map": lambda: views._calculate_scan.__wrapped__(inputs),
        "sweep (21 points)": lambda: run_sweep(_sweep_request(inputs)),
    }
    results: dict[str, Any] = {}
    timings = []
    for label, call in calls.items():
        samples = []
        for _ in range(runs):
            start = time.perf_counter()
            results[label] = call()
            samples.append(time.perf_counter() - start)
        timings.append(
            Timing(
                "engine (direct)",
                label,
                "Default two-phase-oriented case",
                tuple(samples),
            )
        )
    return timings, results


def time_exports(runs: int, results: dict[str, Any]) -> list[Timing]:
    from pvt_phase_simulator_ui.exports import (
        build_export_document,
        build_sweep_export_document,
        export_csv_bytes,
        export_json_bytes,
        export_sweep_csv_bytes,
    )
    from pvt_phase_simulator_ui.model_scope import load_model_scope
    from pvt_phase_simulator_ui.reports import export_engineering_report_html
    from pvt_phase_simulator_ui.units import DEFAULT_UNITS

    inputs = _default_inputs()

    def document() -> dict[str, object]:
        return build_export_document(
            inputs,
            flash_result=results["flash"],
            envelope_result=results["phase envelope"],
            critical_result=results["critical point"],
            saturation_results=results["bubble and dew at the operating temperature"],
            units=DEFAULT_UNITS,
        )

    built = document()
    sweep = results["sweep (21 points)"]
    sweep_document = build_sweep_export_document(sweep, DEFAULT_UNITS)
    scope = load_model_scope(ROOT)
    calls: dict[str, Callable[[], Any]] = {
        "Build the export document": document,
        "JSON export": lambda: export_json_bytes(built),
        "CSV export": lambda: export_csv_bytes(built),
        "HTML report": lambda: export_engineering_report_html(
            built, scope=scope, sweep_document=sweep_document
        ),
        "Sweep CSV export": lambda: export_sweep_csv_bytes(sweep, DEFAULT_UNITS),
        "Read the model scope (CSV and JSON)": lambda: load_model_scope(ROOT),
    }
    return [
        Timing(
            "export",
            label,
            "every result",
            tuple(_timed(call) for _ in range(runs)),
        )
        for label, call in calls.items()
    ]


def write(timings: list[Timing], output: Path | None, runs: int) -> None:
    header = f"Machine: {machine()}. Median of {runs} runs, seconds."
    print(header)
    print("| Group | What | Case | Median (s) | Runs (s) |")
    print("|---|---|---|---:|---|")
    for item in timings:
        runs_text = ", ".join(f"{value:.2f}" for value in item.seconds)
        print(
            f"| {item.group} | {item.label} | {item.case} | "
            f"{item.median:.2f} | {runs_text} |"
        )
    if output is None:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("group", "label", "case", "median_s", "runs_s", "machine"))
        for item in timings:
            writer.writerow(
                (
                    item.group,
                    item.label,
                    item.case,
                    f"{item.median:.3f}",
                    " ".join(f"{value:.3f}" for value in item.seconds),
                    machine(),
                )
            )


def compare(before: Path, after: Path) -> None:
    """Print a before/after table from two CSV files written by ``--output``."""

    def read(path: Path) -> dict[tuple[str, str, str], float]:
        with path.open(encoding="utf-8", newline="") as stream:
            return {
                (row["group"], row["label"], row["case"]): float(row["median_s"])
                for row in csv.DictReader(stream)
            }

    first, second = read(before), read(after)
    print("| Group | What | Case | Before (s) | After (s) |")
    print("|---|---|---|---:|---:|")
    for key, value in first.items():
        if key in second:
            group, label, case = key
            print(f"| {group} | {label} | {case} | {value:.2f} | {second[key]:.2f} |")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--skip",
        default="",
        help="comma-separated groups to skip: start, pages, actions, direct, exports",
    )
    parser.add_argument(
        "--examples",
        default="all",
        help="'all' or 'default': which shipped examples the AppTest actions use",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        type=Path,
        metavar=("BEFORE", "AFTER"),
        help="print a before/after table from two CSV files and exit",
    )
    arguments = parser.parse_args()
    if arguments.compare:
        compare(*arguments.compare)
        return
    logging.disable(logging.CRITICAL)
    skip = set(filter(None, arguments.skip.split(",")))
    timings: list[Timing] = []
    if "start" not in skip:
        timings += time_cold_start(arguments.runs)
    if "pages" not in skip:
        timings += time_page_renders(arguments.runs)
    if "actions" not in skip:
        examples = _example_labels()
        if arguments.examples == "default":
            examples = examples[:1]
        timings += time_actions(arguments.runs, examples)
    if "direct" not in skip or "exports" not in skip:
        direct, results = time_direct_calls(arguments.runs)
        if "direct" not in skip:
            timings += direct
        if "exports" not in skip:
            timings += time_exports(arguments.runs, results)
    write(timings, arguments.output, arguments.runs)


if __name__ == "__main__":
    main()
