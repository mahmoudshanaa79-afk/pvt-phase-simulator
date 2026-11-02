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
