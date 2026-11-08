"""Exact fingerprint of the engine's results over a broad case matrix.

Every case's complete result object is written canonically (``repr`` of every
float, every enum value, status, reason, diagnostic code and nested history)
and hashed with SHA-256. Two runs give the same file if and only if every
result is byte-identical. A short readable summary (status, pressure, reason,
codes) is kept next to each hash so a difference can be located quickly.

The matrix covers saturation (both directions, on all 40 May (2015) states and
on a grid of synthetic binaries and ternaries, including near-critical and
not-found cases), flash, phase stability, the app's phase envelope and extended
overlay, the app's operating-temperature saturation pair, the critical-point
solver and the criticality map; with and without Newton refinement and with and
without a non-zero kij.

Usage::

    uv run python tools/engine_fingerprint.py --output BASELINE.txt
    uv run python tools/engine_fingerprint.py --output AFTER.txt
    uv run python tools/engine_fingerprint.py --compare BASELINE.txt AFTER.txt

Nothing here changes the engine; it only calls its public functions (and the
app's cached-function bodies, which are the calls users actually run).
"""

from __future__ import annotations

import argparse
import dataclasses
import enum
import hashlib
import logging
import multiprocessing
import sys
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "experimental" / "may_2015_ch4_c2_ch4_c3_vle.csv"
MANIFEST = ROOT / "data" / "experimental" / "may_2015_source_manifest.json"
NAMES = ("methane", "ethane", "propane")

Case = tuple[str, str, tuple[Any, ...]]


# --- canonical form -------------------------------------------------------------


def canonical(value: Any) -> str:
    """A complete, exact text form of a result (floats as ``repr``)."""

    import numpy as np
    from pydantic import BaseModel

    if value is None or isinstance(value, (bool, int, str)):
        return repr(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, enum.Enum):
        return f"{type(value).__name__}.{value.name}"
    if isinstance(value, np.ndarray):
        return (
            f"ndarray<{value.dtype}>[{','.join(canonical(v) for v in value.tolist())}]"
        )
    if isinstance(value, np.generic):
        return canonical(value.item())
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        fields = ",".join(
            f"{field.name}={canonical(getattr(value, field.name))}"
            for field in dataclasses.fields(value)
        )
        return f"{type(value).__name__}({fields})"
    if isinstance(value, BaseModel):
        fields = ",".join(
            f"{name}={canonical(getattr(value, name))}"
            for name in type(value).model_fields
        )
        return f"{type(value).__name__}({fields})"
    if isinstance(value, (tuple, list)):
        return "[" + ",".join(canonical(item) for item in value) + "]"
    if isinstance(value, dict):
        items = sorted((canonical(k), canonical(v)) for k, v in value.items())
        return "{" + ",".join(f"{k}:{v}" for k, v in items) + "}"
    if isinstance(value, (set, frozenset)):
        return "set{" + ",".join(sorted(canonical(item) for item in value)) + "}"
    raise TypeError(f"no canonical form for {type(value).__name__}")


def _codes(result: Any) -> str:
    diagnostics = getattr(result, "diagnostics", ()) or ()
    return " ".join(sorted({getattr(item, "code", str(item)) for item in diagnostics}))


def _summary(result: Any) -> str:
    """A short readable line; the hash is what proves identity."""

    if isinstance(result, tuple):
        return " | ".join(_summary(item) for item in result)
    parts = []
    for name in ("status", "convergence_status", "phase_state"):
        if hasattr(result, name):
            parts.append(f"{name}={canonical(getattr(result, name))}")
    for name in ("pressure_pa", "temperature_k", "vapor_fraction"):
        if hasattr(result, name):
            parts.append(f"{name}={canonical(getattr(result, name))}")
    for name in ("bubble_branch", "dew_branch"):
        branch = getattr(result, name, None)
        if branch is not None and hasattr(branch, "points"):
            parts.append(
                f"{name}={len(branch.points)}pts/"
                f"{canonical(getattr(branch, 'termination_reason', None))}"
            )
    reason = getattr(result, "failure_reason", None)
    if reason:
        parts.append(f"reason={reason!r}")
    codes = _codes(result)
    if codes:
        parts.append(f"codes={codes}")
    return " ".join(parts) or type(result).__name__


# --- case matrix -------------------------------------------------------------------


def _kij(pair: tuple[int, int], value: float) -> tuple[float, float, float]:
    index = {(0, 1): 0, (0, 2): 1, (1, 2): 2}[pair]
    kij = [0.0, 0.0, 0.0]
    kij[index] = value
    return (kij[0], kij[1], kij[2])


def cases() -> list[Case]:
    from pvt_phase_simulator.experimental_validation import (
        load_experimental_vle_dataset,
    )

    matrix: list[Case] = []
    dataset = load_experimental_vle_dataset(DATA, MANIFEST)
    for point in dataset.points:
        for direction, fractions in (
            ("bubble", point.liquid_mole_fractions),
            ("dew", point.vapor_mole_fractions),
        ):
            for newton in (False, True):
                for kij_value in (0.0, 0.01):
                    matrix.append(
                        (
                            f"sat/may/{point.source_point_id}/{direction}/"
                            f"newton={newton}/kij={kij_value}",
                            "saturation_binary",
                            (
                                point.component_ids,
                                tuple(fractions),
                                point.temperature_k,
                                direction,
                                newton,
                                kij_value,
                            ),
                        )
                    )
    binaries = ((0, 1), (0, 2), (1, 2))
    for pair in binaries:
        for light in (5.0, 30.0, 50.0, 70.0, 95.0):
            composition = [0.0, 0.0, 0.0]
            composition[pair[0]] = light
            composition[pair[1]] = 100.0 - light
            for temperature in (200.0, 250.0, 300.0, 340.0, 370.0):
                for direction in ("bubble", "dew"):
                    matrix.append(
                        (
                            f"sat/synth/{pair}/{light}/{temperature}/{direction}",
                            "saturation",
                            (tuple(composition), temperature, direction, False, 0.0),
                        )
                    )
            # Newton and kij on a subset.
            for direction in ("bubble", "dew"):
                matrix.append(
                    (
                        f"sat/synth/{pair}/{light}/250.0/{direction}/newton",
                        "saturation",
                        (tuple(composition), 250.0, direction, True, 0.0),
                    )
                )
                matrix.append(
                    (
                        f"sat/synth/{pair}/{light}/250.0/{direction}/kij",
                        "saturation",
                        (tuple(composition), 250.0, direction, False, 0.02),
                    )
                )
    ternaries = ((40.0, 30.0, 30.0), (70.0, 20.0, 10.0), (20.0, 30.0, 50.0))
    for composition in ternaries:
        for temperature in (220.0, 280.0, 330.0):
            for direction in ("bubble", "dew"):
                for newton in (False, True):
                    matrix.append(
                        (
                            f"sat/ternary/{composition}/{temperature}/{direction}/"
                            f"newton={newton}",
                            "saturation",
                            (composition, temperature, direction, newton, 0.0),
                        )
                    )
    flash_compositions = (
        (50.0, 0.0, 50.0),
        (50.0, 50.0, 0.0),
        (40.0, 30.0, 30.0),
        (95.0, 5.0, 0.0),
        (100.0, 0.0, 0.0),
    )
    for composition in flash_compositions:
        for temperature in (200.0, 250.0, 300.0, 330.0):
            for pressure in (1.0, 3.0, 5.0, 8.0, 20.0):
                for kij_value in (0.0, 0.01):
                    matrix.append(
                        (
                            f"flash/{composition}/{temperature}/{pressure}/kij={kij_value}",
                            "flash",
                            (composition, temperature, pressure, kij_value),
                        )
                    )
        matrix.append(
            (f"stability/{composition}/250/5", "stability", (composition, 250.0, 5.0))
        )
    app_states = (
        ((50.0, 0.0, 50.0), 300.0, 5.0, 0.0),  # the default example
        ((50.0, 0.0, 50.0), 250.0, 5.0, 0.0),
        ((50.0, 0.0, 50.0), 321.5829183194, 8.53444323606381, 0.0),
        ((50.0, 50.0, 0.0), 250.0, 5.0, 0.0),
        ((71.23, 28.77, 0.0), 243.6, 5.0, 0.0),
        ((40.0, 30.0, 30.0), 250.0, 5.0, 0.01),
    )
    for composition, temperature, pressure, kij_value in app_states:
        for action in ("envelope", "extended", "saturation_pair", "critical", "scan"):
            matrix.append(
                (
                    f"app/{action}/{composition}/{temperature}/{pressure}/kij={kij_value}",
                    action,
                    (composition, temperature, pressure, kij_value),
                )
            )
    return matrix


# --- evaluation ----------------------------------------------------------------------


def _inputs(
    composition: Iterable[float], temperature: float, pressure: float, kij: float
):
    from pvt_phase_simulator_ui.adapters import validate_scientific_inputs

    values = tuple(composition)
    present = [index for index, value in enumerate(values) if value > 0.0]
    interaction = (0.0, 0.0, 0.0)
    if kij and len(present) >= 2:
        interaction = _kij((present[0], present[1]), kij)
    return validate_scientific_inputs(values, temperature, pressure, kij=interaction)


def evaluate(case: Case) -> tuple[str, str, str, float]:
    """Run one case; return (id, sha256, summary, seconds)."""

    logging.disable(logging.CRITICAL)
    case_id, kind, arguments = case
    start = time.perf_counter()
    try:
        result = _run(kind, arguments)
        text = canonical(result)
        summary = _summary(result)
    except Exception as error:  # noqa: BLE001 - a raised error is part of the result
        text = f"raised {type(error).__name__}: {error}"
        summary = text
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return case_id, digest, summary, time.perf_counter() - start


def _run(kind: str, arguments: tuple[Any, ...]) -> Any:
    from pvt_phase_simulator.eos.flash import calculate_two_phase_flash
    from pvt_phase_simulator.eos.phase_stability import (
        analyze_mixture_phase_stability,
    )
    from pvt_phase_simulator.eos.saturation_pressure import (
        SaturationKind,
        calculate_saturation_pressure,
    )
    from pvt_phase_simulator.experimental_validation import (
        COMPONENT_OBJECTS,
        _mixture,
    )
    from pvt_phase_simulator_ui import app as ui_app
    from pvt_phase_simulator_ui import views

    kinds = {
        "bubble": SaturationKind.BUBBLE_POINT,
        "dew": SaturationKind.DEW_POINT,
    }
    if kind == "saturation_binary":
        component_ids, fractions, temperature, direction, newton, kij = arguments
        mixture = _mixture(component_ids, fractions)
        interactions = None
        if kij:
            first, second = (COMPONENT_OBJECTS[name].name for name in component_ids)
            interactions = {(first, second): kij, (second, first): kij}
        return calculate_saturation_pressure(
            mixture,
            temperature,
            kinds[direction],
            binary_interactions=interactions,
            saturation_newton_enabled=newton,
        )
    if kind == "saturation":
        composition, temperature, direction, newton, kij = arguments
        inputs = _inputs(composition, temperature, 5.0, kij)
        return calculate_saturation_pressure(
            inputs.mixture(),
            temperature,
            kinds[direction],
            binary_interactions=inputs.binary_interactions(),
            saturation_newton_enabled=newton,
        )
    if kind == "flash":
        composition, temperature, pressure, kij = arguments
        inputs = _inputs(composition, temperature, pressure, kij)
        return calculate_two_phase_flash(
            inputs.mixture(),
            inputs.temperature_k,
            inputs.pressure_pa,
            binary_interactions=inputs.binary_interactions(),
        )
    if kind == "stability":
        composition, temperature, pressure = arguments
        inputs = _inputs(composition, temperature, pressure, 0.0)
        return analyze_mixture_phase_stability(
            inputs.mixture(), inputs.temperature_k, inputs.pressure_pa
        )
    inputs = _inputs(*arguments)
    calls: dict[str, Callable[[Any], Any]] = {
        "envelope": views._calculate_envelope.__wrapped__,
        "extended": views._calculate_extended_envelope.__wrapped__,
        "saturation_pair": views._calculate_operating_saturation.__wrapped__,
        "critical": views._calculate_critical.__wrapped__,
        "scan": views._calculate_scan.__wrapped__,
        "app_flash": ui_app._cached_flash.__wrapped__,
    }
    return calls[kind](inputs)


# --- files ---------------------------------------------------------------------------


def write(path: Path, rows: list[tuple[str, str, str, float]]) -> None:
    rows = sorted(rows)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("# case_id\tsha256\tsummary\n")
        for case_id, digest, summary, _ in rows:
            stream.write(f"{case_id}\t{digest}\t{summary}\n")


def read(path: Path) -> dict[str, tuple[str, str]]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        case_id, digest, summary = line.split("\t", 2)
        rows[case_id] = (digest, summary)
    return rows


def compare(before: Path, after: Path) -> int:
    first, second = read(before), read(after)
    missing = sorted(set(first) ^ set(second))
    changed = sorted(
        key for key in set(first) & set(second) if first[key][0] != second[key][0]
    )
    print(f"{len(first)} cases before, {len(second)} after; {len(changed)} differ.")
    for key in missing:
        print(f"only in one file: {key}")
    for key in changed:
        print(f"DIFFERS: {key}\n  before: {first[key][1]}\n  after:  {second[key][1]}")
    return 1 if (missing or changed) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("BEFORE", "AFTER"))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--filter", default="", help="only cases whose id contains this"
    )
    parser.add_argument("--timings", type=Path, help="also write per-case seconds")
    arguments = parser.parse_args()
    if arguments.compare:
        return compare(*arguments.compare)
    if arguments.output is None:
        parser.error("--output or --compare is required")
    matrix = [case for case in cases() if arguments.filter in case[0]]
    # Slow cases first, so the pool stays busy to the end.
    matrix.sort(key=lambda case: (not case[0].startswith("app/envelope"), case[0]))
    start = time.perf_counter()
    rows = []
    with multiprocessing.get_context("spawn").Pool(arguments.workers) as pool:
        for index, row in enumerate(pool.imap_unordered(evaluate, matrix), 1):
            rows.append(row)
            if index % 50 == 0 or row[3] > 30:
                print(f"{index}/{len(matrix)} {row[0]} {row[3]:.1f}s", flush=True)
    write(arguments.output, rows)
    if arguments.timings:
        with arguments.timings.open("w", encoding="utf-8") as stream:
            for case_id, _, _, seconds in sorted(rows):
                stream.write(f"{case_id}\t{seconds:.3f}\n")
    elapsed = time.perf_counter() - start
    print(f"{len(rows)} cases in {elapsed:.0f} s -> {arguments.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
