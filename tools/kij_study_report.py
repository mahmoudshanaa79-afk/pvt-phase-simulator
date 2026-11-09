"""Render docs/investigations/kij_study.md from the committed study files.

Every number in the report comes from ``kij_study.csv``, ``kij_study_fit.json``
or the protected Module 17 summary; nothing is solved here. The test suite
re-renders the report and compares it with the committed file, so a number in
the report cannot drift away from the data behind it.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from pvt_phase_simulator.experimental_validation import REQUIRED_SYSTEMS
from tools import kij_study_text as text

SUMMARY_FILE = "docs/investigations/kij_study.csv"
FIT_FILE = "docs/investigations/kij_study_fit.json"
MODULE17_SUMMARY = "docs/validation/module17_vle_validation_summary.json"
LABELS = {
    "ch4_c2": "CH4+C2",
    "ch4_c3": "CH4+C3",
    "ch4_ic4": "CH4+iC4",
    "ch4_nc4": "CH4+nC4",
}


def load(root: Path) -> tuple[list[dict[str, str]], dict[str, Any], dict[str, Any]]:
    with (root / SUMMARY_FILE).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    fit = json.loads((root / FIT_FILE).read_text(encoding="utf-8"))
    module17 = json.loads((root / MODULE17_SUMMARY).read_text(encoding="utf-8"))
    return rows, fit, module17


def kij_text(value: float) -> str:
    return f"{value:+.4f}".replace("+0.0000", "0").replace("-0.0000", "0")


def percent(value: str | float | None, digits: int = 2) -> str:
    if value in (None, ""):
        return "n/a"
    return f"{float(value):.{digits}f} %"


def aard_cell(row: dict[str, str]) -> str:
    if row["aard_percent"] == "":
        return "n/a (n=0)"
    return f"{float(row['aard_percent']):.2f} % (n={row['aard_n']})"


def row_for(
    rows: list[dict[str, str]], system: str, kij: float, kind: str
) -> dict[str, str]:
    return next(
        row
        for row in rows
        if row["system_id"] == system
        and float(row["kij"]) == kij
        and row["kind"] == kind
    )


def systems_in(rows: list[dict[str, str]], provisional: bool) -> list[str]:
    wanted = "True" if provisional else "False"
    return list(
        dict.fromkeys(r["system_id"] for r in rows if r["provisional"] == wanted)
    )


def kij_values(rows: list[dict[str, str]], system: str) -> list[float]:
    return sorted({float(r["kij"]) for r in rows if r["system_id"] == system})


def grid_table(rows: list[dict[str, str]], system: str, optimum: float | None) -> str:
    lines = [
        "| kij | Bubble converged | Bubble not found | Bubble inconclusive | "
        "Bubble AARD | Dew unique | Dew hidden root | Dew multiple roots | "
        "Dew not found | Dew AARD (unique only) |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for kij in kij_values(rows, system):
        bubble = row_for(rows, system, kij, "bubble")
        dew = row_for(rows, system, kij, "dew")
        inconclusive = sum(
            int(bubble[key])
            for key in ("hidden_root", "multiple_roots", "inconclusive_other", "failed")
        )
        dew_other = int(dew["inconclusive_other"]) + int(dew["failed"])
        label = kij_text(kij)
        if optimum is not None and kij == optimum:
            label = f"**{label} (fit)**"
        dew_nf = dew["not_found"] + (f" (+{dew_other} other)" if dew_other else "")
        lines.append(
            f"| {label} | {bubble['converged']} | {bubble['not_found']} | "
            f"{inconclusive} | {aard_cell(bubble)} | {dew['converged']} | "
            f"{dew['hidden_root']} | {dew['multiple_roots']} | {dew_nf} | "
            f"{aard_cell(dew)} |"
        )
    return "\n".join(lines)


def fit_section(system: str, fit: dict[str, Any]) -> str:
    label = LABELS[system]
    if not fit.get("common_n"):
        return f"No state of {label} converges at every kij on the fine grid; no fit.\n"
    changing = fit["status_changes_with_kij"]
    changing_text = ", ".join(point[-3:] for point in changing) if changing else "none"
    return "\n".join(
        [
            f"- **Fitted kij = {kij_text(fit['optimum'])}** (fine-grid minimum "
            f"{kij_text(fit['grid_optimum'])}, refined).",
            f"- Bubble AARD over the fixed set of {fit['common_n']} states: "
            f"{fit['aard_at_zero']:.2f} % at kij = 0, "
            f"{fit['aard_at_optimum']:.2f} % at the fitted kij.",
            f"- Sensitivity band (AARD within "
            f"{text.BAND_PP} percentage points of the minimum): "
            f"{kij_text(fit['band_low'])} to {kij_text(fit['band_high'])}.",
            f"- Bootstrap over states, 95 % interval of the optimum: "
            f"{kij_text(fit['bootstrap_low'])} to {kij_text(fit['bootstrap_high'])}.",
            f"- States whose bubble status changes somewhere on the fine grid: "
            f"{changing_text}.",
        ]
    )


def leave_one_out_table(fit: dict[str, Any]) -> str:
    lines = [
        "| Held-out isotherm (K) | States | In fixed set | Scored | Training n | "
        "kij fitted without it | Held-out AARD at kij = 0 | at that kij |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in fit.get("leave_one_isotherm_out", []):
        low, high = item["temperature_k_min"], item["temperature_k_max"]
        span = f"{low:.2f}" if abs(high - low) < 0.005 else f"{low:.2f}–{high:.2f}"
        lines.append(
            f"| {span} | {item['held_out_states']} | {item['held_out_in_fixed_set']} | "
            f"{item['held_out_scored']} | {item['train_n']} | "
            f"{kij_text(item['train_kij'])} | "
            f"{percent(item['held_out_aard_at_zero'])} | "
            f"{percent(item['held_out_aard_at_train_kij'])} |"
        )
    return "\n".join(lines)


def per_state_table(fit: dict[str, Any]) -> str:
    lines = [
        "| State | T (K) | Measured P (MPa) | Error at kij = 0 | Own best kij | "
        "Error there |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for item in fit.get("per_state_best_kij", []):
        best = item["best_kij"]
        zero = item["error_at_zero"]
        zero_text = "not converged" if zero is None else percent(zero)
        lines.append(
            f"| {item['point_id'][-3:]} | {item['temperature_k']:.2f} | "
            f"{item['pressure_pa'] / 1e6:.3f} | "
            f"{zero_text} | "
            f"{'none converges' if best is None else kij_text(best)} | "
            f"{percent(item['error_at_best'])} |"
        )
    return "\n".join(lines)


def loo_spread(fit: dict[str, Any]) -> tuple[float, float]:
    values = [item["train_kij"] for item in fit.get("leave_one_isotherm_out", [])]
    return min(values), max(values)


def composition_table(entries: list[dict[str, Any]]) -> str:
    lines = [
        "| kij | Dew states | Assessable | Within 1 U | Within 2 U | Mean abs(dy) | "
        "Mean dy | Above the converged isotherm |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    shown: list[float] = []
    for entry in entries:
        if entry["kij"] in shown:  # the fitted kij is 0: one row says it all
            continue
        shown.append(entry["kij"])
        lines.append(
            f"| {kij_text(entry['kij'])} | {entry['states']} | {entry['assessed']} | "
            f"{entry['within_one_u']} | {entry['within_two_u']} | "
            f"{entry['mean_abs_difference']:.4f} | {entry['mean_difference']:+.4f} | "
            f"{entry['above_isotherm']} |"
        )
    return "\n".join(lines)


def reproduction_table(rows: list[dict[str, str]], module17: dict[str, Any]) -> str:
    lines = [
        "| System | Direction | Module 17 successes | Study at kij = 0 | "
        "Module 17 AARD | Study AARD |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for system in module17["systems"]:
        system_id = system["system_id"]
        if system_id not in REQUIRED_SYSTEMS:
            # Admitted butane systems: the study ran them only on provisional
            # constants, so there is no production run to reproduce.
            continue
        for kind in ("bubble", "dew"):
            record = system[f"production_selected_{kind}_metrics"]
            study = row_for(rows, system_id, 0.0, kind)
            lines.append(
                f"| {LABELS[system_id]} | {kind} | {record['success_count']} | "
                f"{study['converged']} | {record['pressure_aard_percent']:.6f} % | "
                f"{float(study['aard_percent']):.6f} % |"
            )
    return "\n".join(lines)


def render(root: Path) -> str:
    rows, fit, module17 = load(root)
    fits = fit["fits"]
    production = systems_in(rows, provisional=False)
    provisional = systems_in(rows, provisional=True)
    parts = [text.title_and_summary(rows, fits, fit), text.METHOD]
    parts += [
        "## Check: kij = 0 reproduces the validation record\n",
        reproduction_table(rows, module17),
        "",
    ]
    for system in production:
        system_fit = fits[system]
        parts += [
            f"## {LABELS[system]}\n",
            "### Status counts and AARD across kij\n",
            grid_table(rows, system, system_fit.get("optimum")),
            "",
            "### Fit to bubble pressure\n",
            fit_section(system, system_fit),
            "",
            "### Leave one isotherm out\n",
            leave_one_out_table(system_fit),
            "",
            "### Each state's own best kij\n",
            per_state_table(system_fit),
            "",
            "### Dew composition at the measured pressure (P3 metric)\n",
            composition_table(fit["dew_composition"][system]),
            "",
            text.system_discussion(system, rows, system_fit, fit),
        ]
    if provisional:
        parts.append(text.BUTANE_INTRO)
        for system in provisional:
            system_fit = fits[system]
            parts += [
                f"### {LABELS[system]} (provisional)\n",
                grid_table(rows, system, system_fit.get("optimum")),
                "",
                fit_section(system, system_fit),
                "",
                leave_one_out_table(system_fit),
                "",
            ]
    parts += [
        text.literature(),
        text.limits(),
        text.proposal(rows, fits),
        text.APP_DESIGN,
    ]
    return "\n\n".join(part.strip("\n") for part in parts if part.strip()) + "\n"
