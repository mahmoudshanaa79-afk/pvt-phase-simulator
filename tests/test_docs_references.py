"""Every repository path the current documents mention exists.

Checks backtick-quoted paths under the repository's top-level folders and
relative Markdown links in README.md and docs/. Cheap, and it catches a
renamed or deleted file that a document still points to.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = re.compile(
    r"`((?:docs|tools|src|tests|data|app|notebooks|\.github|\.streamlit)/"
    r"[A-Za-z0-9_./\-]+)`"
    r"|\]\(((?!https?:|#|mailto:)[^)\s#]+)"
)


def _documents() -> list[Path]:
    return sorted([*ROOT.glob("*.md"), *(ROOT / "docs").glob("**/*.md")])


def test_every_referenced_file_exists() -> None:
    missing = []
    for document in _documents():
        for match in PATH.finditer(document.read_text(encoding="utf-8")):
            reference = match.group(1) or match.group(2)
            if any(mark in reference for mark in "*{<"):
                continue
            if (
                not (ROOT / reference).exists()
                and not (document.parent / reference).exists()
            ):
                missing.append(f"{document.relative_to(ROOT)}: {reference}")
    assert not missing, missing
