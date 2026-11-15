"""Plain-language text for the saturation solver's diagnostic codes.

The engine reports why a saturation result is what it is with diagnostic codes.
The app always shows the code itself; this module adds one short, honest
sentence for the codes that proposals P2, P7 and P8 introduced, so a reader who
does not know the solver can tell what the code means for the number shown (or
not shown). Nothing here changes a result or hides a code.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

MODULE17_STATES: Final = Path("docs") / "validation" / "module17_vle_validation.csv"

BOUNDARY: Final = "BOUNDARY_SATURATION_ROOT"
HIDDEN: Final = "HIDDEN_SATURATION_ROOT"
MULTIPLE: Final = "MULTIPLE_SATURATION_ROOTS"
UNBRACKETED: Final = "SATURATION_ROOT_UNBRACKETED"

#: One explanation per code (or code pair). The order is the display order.
EXPLANATIONS: Final[tuple[tuple[tuple[str, ...], str], ...]] = (
    (
        (BOUNDARY,),
        "Root found by refining next to a pressure-grid point where the inner "
        "calculation did not converge. The pressure is still a converged root, "
        "bracketed between two converged evaluations.",
    ),
    (
        (HIDDEN, MULTIPLE),
        "Two possible answers: refining next to a failed grid point revealed a "
        "second root, so the solver reports no pressure rather than pick one.",
    ),
    (
        (MULTIPLE,),
        "More than one saturation pressure fits this state, so the answer is not "
        "unique and no pressure is reported.",
    ),
    (
        (UNBRACKETED,),
        "A root was found next to a failed grid point, but it could not be "
        "bracketed between two converged evaluations, so no number is reported.",
    ),
)

#: Every code this module explains.
EXPLAINED_CODES: Final = frozenset(code for codes, _ in EXPLANATIONS for code in codes)

#: One plain-language sentence for every diagnostic code the engine can emit.
#: ``tests/test_code_glossary.py`` reads the codes from the engine's source and
#: fails if one is missing here or if an entry names a code the engine no
#: longer has. The Diagnostics page shows this glossary next to the codes.
CODE_GLOSSARY: Final[dict[str, str]] = {
    # Advisory model diagnostics.
    "DEFAULTED_BINARY_INTERACTIONS": (
        "No binary interaction coefficient was supplied for at least one pair, so "
        "kij = 0 was used (the default)."
    ),
    "NEAR_NOMINAL_COMPONENT_CRITICAL_POINT": (
        "A component is close to its own critical temperature and pressure, where "
        "cubic equation-of-state results are sensitive. A warning, not a failure."
    ),
    "ALPHA_CORRELATION_TURNING_REGION": (
        "A component is at a reduced temperature beyond the turning point of the "
        "Peng–Robinson alpha correlation, outside the range it was built for; "
        "treat that component's attraction term with caution."
    ),
    # Phase stability.
    "FALLBACK_MULTISTART_TRIGGERED": (
        "The standard Wilson starting guess for a stability trial was "
        "inconclusive, so a small fixed set of extra starting guesses was tried."
    ),
    "NO_RELIABLE_PHASE_STABILITY_TRIAL": (
        "Neither the standard nor the fallback stability trials gave a reliable "
        "answer, so stability is reported as inconclusive."
    ),
    "DISCONTINUOUS_TRIAL_ROOT_SWITCH": (
        "During a stability trial the selected equation-of-state root jumped to "
        "another branch. The trial result stands, but its path was not smooth."
    ),
    "MULTIPLE_STABLE_FEED_ROOTS": (
        "The feed has more than one mechanically stable root (liquid-like and "
        "vapour-like); the one with the lower Gibbs energy is the reference."
    ),
    "MARGINAL_FEED_ROOTS_EXCLUDED": (
        "Some roots of the feed are on the edge of mechanical stability; they are "
        "kept in the record but not used as the reference state."
    ),
    "MARGINAL_TRIAL_ROOTS_EXCLUDED": (
        "Some roots of a trial phase are on the edge of mechanical stability; they "
        "are kept in the record but not used in the trial."
    ),
    # Two-phase flash failures: no phase split is reported.
    "FLASH_RR_FAILURE": (
        "The Rachford–Rice equation could not be evaluated with the current "
        "K-values, so no phase split is reported."
    ),
    "FLASH_NO_RR_ROOT": (
        "The feed is unstable, but the Rachford–Rice equation has no physical "
        "vapour fraction between 0 and 1, so no phase split is reported."
    ),
    "FLASH_PHASE_FAILURE": (
        "The equation of state could not be evaluated for one of the phases, so "
        "no phase split is reported."
    ),
    "FLASH_OSCILLATION": (
        "The K-values jumped back and forth between two sets instead of "
        "converging, so no phase split is reported."
    ),
    "FLASH_STAGNATION": (
        "The flash stopped making progress before every convergence check "
        "passed, so no phase split is reported."
    ),
    "FLASH_MAXIMUM_ITERATIONS": (
        "The flash reached its iteration limit without converging, so no phase "
        "split is reported."
    ),
    # Saturation pressure: steps at one trial pressure.
    "SATURATION_PARENT_FAILURE": (
        "At one trial pressure the equation of state could not be evaluated for "
        "the feed (parent) phase."
    ),
    "SATURATION_INNER_FAILURE": (
        "At one trial pressure the calculation of the new (incipient) phase failed."
    ),
    "SATURATION_INNER_MAXIMUM": (
        "At one trial pressure the incipient-phase iteration reached its limit "
        "without converging."
    ),
    "SATURATION_INNER_OSCILLATION": (
        "At one trial pressure the incipient-phase K-values jumped back and forth "
        "between two sets."
    ),
    "SATURATION_INNER_STAGNATION": (
        "At one trial pressure the incipient-phase iteration stopped making progress."
    ),
    "SATURATION_TRIVIAL_STATE": (
        "At one trial pressure the iteration returned the feed itself instead of a "
        "distinct new phase (a trivial solution)."
    ),
    "SATURATION_PHASES_INDISTINGUISHABLE": (
        "The parent and incipient phases are too similar to tell apart at that "
        "pressure."
    ),
    "SATURATION_PHASE_ROLE_INVERTED": (
        "The phases came out in the wrong roles (the requested liquid behaves as a "
        "vapour, or the reverse), so that solution is rejected."
    ),
    "SATURATION_INITIAL_LOG_K_PHASE_ROLE": (
        "The starting K-values put the phases in the wrong roles, so that "
        "starting guess was rejected."
    ),
    # Saturation pressure: the root search.
    "BOUNDARY_SATURATION_ROOT": EXPLANATIONS[0][1],
    "HIDDEN_SATURATION_ROOT": (
        "Refining next to a failed grid point revealed a second saturation "
        "pressure, so the answer is not unique and no pressure is reported."
    ),
    "MULTIPLE_SATURATION_ROOTS": EXPLANATIONS[2][1],
    "SATURATION_ROOT_UNBRACKETED": EXPLANATIONS[3][1],
    "SATURATION_BRACKET_NOT_FOUND": (
        "No pressure interval that safely contains a saturation pressure was "
        "found in the search range, so no pressure is reported."
    ),
    "SATURATION_SOLVER_FAILURE": (
        "The bracketed pressure solve failed, so no pressure is reported."
    ),
    "SATURATION_SOLVER_NON_CONVERGENCE": (
        "The bracketed pressure solve reached its iteration limit without "
        "converging, so no pressure is reported."
    ),
    "SATURATION_FINAL_RECONSTRUCTION": (
        "Rebuilding the final state from the solver's pressure was inconclusive, "
        "so no pressure is reported."
    ),
    "SATURATION_FINAL_GATES": (
        "The final state did not pass every convergence check, so no pressure is "
        "reported."
    ),
    # Phase-envelope tracing.
    "ENVELOPE_PREDICTOR_DUPLICATE_TEMPERATURE": (
        "Two accepted points had the same temperature, so the next point was "
        "predicted by a simpler method."
    ),
    "ENVELOPE_PREDICTOR_NONFINITE_SLOPE": (
        "Extrapolating to the next point gave an infinite or undefined value, so a "
        "simpler prediction was used."
    ),
    "ENVELOPE_CORRECTOR_NUMERICAL_FAILURE": (
        "Correcting a predicted envelope point failed numerically, so that point "
        "was rejected."
    ),
    "ENVELOPE_FALLBACK_NUMERICAL_FAILURE": (
        "The wider fallback search for an envelope point also failed numerically, "
        "so that point was rejected."
    ),
    "ENVELOPE_BRANCH_JUMP": (
        "A candidate point was rejected because it jumped to another branch or "
        "swapped the phase roles; the trace continues from accepted points only."
    ),
    "ENVELOPE_NEAR_CRITICAL_COMPOSITION": (
        "The two phases' compositions are becoming equal, as they do near a "
        "critical point."
    ),
    "ENVELOPE_NEAR_CRITICAL_LOG_K": (
        "The K-values are approaching 1, as they do near a critical point."
    ),
    "ENVELOPE_NEAR_CRITICAL_ROOTS": (
        "The two phases' equation-of-state roots are approaching each other, as "
        "they do near a critical point."
    ),
    "ENVELOPE_BRANCH_PRESSURES_APPROACHING": (
        "Bubble and dew pressures are close at the same temperature, a sign of the "
        "critical region; this is not a calculated critical point."
    ),
}


def glossary_rows(codes: Iterable[str] | None = None) -> list[dict[str, str]]:
    """Code and meaning for ``codes`` (every engine code when omitted).

    A code the glossary does not know is listed with that fact rather than
    dropped, so a new engine code is never hidden.
    """

    selected = list(dict.fromkeys(CODE_GLOSSARY if codes is None else codes))
    return [
        {
            "Code": code,
            "Meaning": CODE_GLOSSARY.get(
                code, "No plain-language entry yet; see the engine message."
            ),
        }
        for code in selected
    ]


@dataclass(frozen=True, slots=True)
class CodeExplanation:
    """The engine's own code(s), verbatim, and a plain-language sentence."""

    codes: tuple[str, ...]
    text: str

    @property
    def label(self) -> str:
        return " + ".join(self.codes)


def explain_codes(codes: Iterable[str]) -> tuple[CodeExplanation, ...]:
    """Explanations for the explained codes present in ``codes``.

    A code pair (``HIDDEN`` with ``MULTIPLE``) is explained once, as a pair.
    Codes this module does not explain are left out; callers still show every
    code verbatim.
    """

    present = set(codes)
    used: set[str] = set()
    explanations = []
    for group, text in EXPLANATIONS:
        if set(group) <= present and not set(group) & used:
            explanations.append(CodeExplanation(group, text))
            used.update(group)
    return tuple(explanations)


def explanation_text(codes: Sequence[str]) -> str:
    """One line, ``CODE: sentence`` per explanation, or an empty string."""

    return " ".join(f"{item.label}: {item.text}" for item in explain_codes(codes))


@dataclass(frozen=True, slots=True)
class RecordedOutcome:
    """One committed Module 17 state whose codes include an explained code."""

    source_point_id: str
    temperature_k: float
    status: str
    codes: tuple[str, ...]
    explanation: str


def record_solver_outcomes(
    repository_root: Path, direction: Literal["bubble", "dew"]
) -> tuple[RecordedOutcome, ...]:
    """Read the committed record; nothing is solved at page load."""

    with (repository_root / MODULE17_STATES).open(
        encoding="utf-8", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    outcomes = []
    for row in rows:
        codes = tuple(json.loads(row[f"{direction}_diagnostic_codes"]))
        if not EXPLAINED_CODES & set(codes):
            continue
        outcomes.append(
            RecordedOutcome(
                source_point_id=row["source_point_id"],
                temperature_k=float(row["temperature_k"]),
                status=row[f"{direction}_status"],
                codes=codes,
                explanation=explanation_text(codes),
            )
        )
    return tuple(outcomes)
