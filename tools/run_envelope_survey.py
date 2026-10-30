"""Survey the app's extended phase-envelope branches on a fixed list of cases.

The Phase Envelope page overlays the engine's pseudo-arclength branches. A case is
"closed" when both branches stop at the engine's own near-critical guard; any other
stop is reported with the engine's reason and is not shown as closed.

Each case is traced twice with the unchanged engine:

* **before P1**: the root-count rule the pseudo-arclength tracer used before
  proposal P1, restored inside this process only;
* **current**: the shipped code.

The original 16-case list behind the older wording in
``docs/STREAMLIT_APPLICATION.md`` was not kept, so this list is a stated
reconstruction: the three shipped examples, the ten mixtures of
``tools/run_root_count_whatif.py`` and a few more binaries and ternaries. Nothing is
fitted and no result is hidden. Output goes to ``docs/investigations``.
"""

from __future__ import annotations

import argparse
import csv
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

import pvt_phase_simulator.eos.pseudo_arclength as arclength
from pvt_phase_simulator_ui.adapters import validate_scientific_inputs
from pvt_phase_simulator_ui.envelope_extension import (
    NEAR_CRITICAL,
    ExtendedEnvelope,
    trace_extended_envelope,
)
from pvt_phase_simulator_ui.state import INPUT_EXAMPLES

Composition = tuple[float, float, float]  # methane, ethane, propane mol %

#: (label, composition, operating temperature K).
SHIPPED_CASES: tuple[tuple[str, Composition, float], ...] = tuple(
    (
        f"shipped: {example.label}",
        (example.methane_pct, example.ethane_pct, example.propane_pct),
        example.temperature_k,
    )
    for example in INPUT_EXAMPLES
)
OTHER_CASES: tuple[tuple[str, Composition, float], ...] = (
    ("C1/C3 50/50, warm start", (50.0, 0.0, 50.0), 330.0),
    ("C1/C3 10/90", (10.0, 0.0, 90.0), 330.0),
    ("C1/C3 30/70", (30.0, 0.0, 70.0), 310.0),
    ("C1/C3 70/30", (70.0, 0.0, 30.0), 270.0),
    ("C1/C3 90/10", (90.0, 0.0, 10.0), 230.0),
    ("C2/C3 30/70", (0.0, 30.0, 70.0), 315.5),
    ("C2/C3 70/30", (0.0, 70.0, 30.0), 300.0),
    ("C1/C2 50/50", (50.0, 50.0, 0.0), 250.0),
    ("C1/C2/C3 40/30/30", (40.0, 30.0, 30.0), 290.0),
    ("C1/C3 20/80", (20.0, 0.0, 80.0), 320.0),
    ("C2/C3 50/50", (0.0, 50.0, 50.0), 310.0),
    ("C1/C2/C3 30/40/30", (30.0, 40.0, 30.0), 300.0),
    ("C1/C3 80/20", (80.0, 0.0, 20.0), 250.0),
)
CASES: tuple[tuple[str, Composition, float], ...] = SHIPPED_CASES + OTHER_CASES

CSV_FIELDS = (
    "case",
    "methane_pct",
    "ethane_pct",
    "propane_pct",
    "temperature_k",
    "before_bubble",
    "before_dew",
    "before_closed",
    "current_bubble",
    "current_dew",
    "current_closed",
)


@dataclass(frozen=True, slots=True)
class CaseResult:
    label: str
    composition: Composition
    temperature_k: float
    before: ExtendedEnvelope
    current: ExtendedEnvelope


@contextmanager
def pre_p1_continuity_rule() -> Iterator[None]:
    """Restore the shared root-count rule in the tracer, in this process only."""

    module: Any = arclength
    patched = module._arclength_root_is_continuous
    module._arclength_root_is_continuous = module._root_branch_is_continuous
    try:
        yield
    finally:
        module._arclength_root_is_continuous = patched


def survey_case(
    label: str, composition: Composition, temperature_k: float
) -> CaseResult:
    mixture = validate_scientific_inputs(composition, temperature_k, 5.0e6).mixture()
    with pre_p1_continuity_rule():
        before = trace_extended_envelope(mixture, temperature_k)
    current = trace_extended_envelope(mixture, temperature_k)
    return CaseResult(label, composition, temperature_k, before, current)


def survey(
    cases: tuple[tuple[str, Composition, float], ...] = CASES,
) -> tuple[CaseResult, ...]:
    return tuple(survey_case(*case) for case in cases)


def closed(envelope: ExtendedEnvelope) -> bool:
    return envelope.both_reached_critical_region


def counts(results: tuple[CaseResult, ...], which: str) -> tuple[int, int]:
    """(closed, stopped early) for ``before`` or ``current``."""

    closed_count = sum(closed(getattr(item, which)) for item in results)
    return closed_count, len(results) - closed_count


def _reasons(envelope: ExtendedEnvelope) -> tuple[str, str]:
    return envelope.bubble.termination_reason, envelope.dew.termination_reason


def render_csv(results: tuple[CaseResult, ...]) -> str:
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for item in results:
        before_bubble, before_dew = _reasons(item.before)
        current_bubble, current_dew = _reasons(item.current)
        writer.writerow(
            {
                "case": item.label,
                "methane_pct": item.composition[0],
                "ethane_pct": item.composition[1],
                "propane_pct": item.composition[2],
                "temperature_k": item.temperature_k,
                "before_bubble": before_bubble,
                "before_dew": before_dew,
                "before_closed": str(closed(item.before)).lower(),
                "current_bubble": current_bubble,
                "current_dew": current_dew,
                "current_closed": str(closed(item.current)).lower(),
            }
        )
    return stream.getvalue()


def _cell(envelope: ExtendedEnvelope) -> str:
    if closed(envelope):
        return "closed"
    bubble, dew = _reasons(envelope)
    parts = [
        f"{name} {reason}"
        for name, reason in (("bubble", bubble), ("dew", dew))
        if reason != NEAR_CRITICAL
    ]
    return "stopped: " + ", ".join(parts)


def render_markdown(results: tuple[CaseResult, ...]) -> str:
    before_closed, before_stopped = counts(results, "before")
    current_closed, current_stopped = counts(results, "current")
    lines = [
        "# Extended-envelope survey",
        "",
        "Generated by `tools/run_envelope_survey.py`. A case is closed when both",
        "extended branches stop at the engine's own near-critical guard. That is not",
        "a certified critical point. Any other stop keeps the engine's reason.",
        "",
        "The 16-case list behind the older wording in",
        "`docs/STREAMLIT_APPLICATION.md` was not kept, so this list is a",
        "reconstruction (the three shipped examples plus binaries and ternaries) and",
        "its counts are not a re-measurement of the older ones.",
        "",
        f"- **Before P1** (the earlier root-count rule): {before_closed} closed, "
        f"{before_stopped} stopped early.",
        f"- **Current code**: {current_closed} closed, {current_stopped} stopped "
        "early.",
        "",
        "| Case | Mol % C1/C2/C3 | T (K) | Before P1 | Current |",
        "|---|---|---:|---|---|",
    ]
    for item in results:
        c1, c2, c3 = item.composition
        lines.append(
            f"| {item.label} | {c1:g}/{c2:g}/{c3:g} | {item.temperature_k:g} | "
            f"{_cell(item.before)} | {_cell(item.current)} |"
        )
    lines.append("")
    return "\n".join(lines)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return parser.parse_args()


def main() -> None:
    root = _arguments().root.resolve()
    results = survey()
    output = root / "docs/investigations"
    output.mkdir(parents=True, exist_ok=True)
    (output / "envelope_survey.csv").write_text(
        render_csv(results), encoding="utf-8", newline=""
    )
    (output / "envelope_survey.md").write_text(
        render_markdown(results), encoding="utf-8", newline=""
    )
    print(render_markdown(results))


if __name__ == "__main__":
    main()
