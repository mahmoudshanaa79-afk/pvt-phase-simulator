"""Proof that persisted evidence still describes the work it was recorded for.

Two things get reused across process boundaries: a verification result, and a
builder's report. Both were trustworthy when they were written. Neither is
trustworthy later unless something ties it to the exact tree and the exact run
that produced it - git HEAD alone does not, because a package's whole diff lives
in the working tree while HEAD stays where it was.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import OrchestratorConfig
from .gitops import read_repo
from .workpackage import WorkPackage

#: Marker for a path that the fingerprint expected but could not read.
ABSENT = "ABSENT"


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _file_digest(path: Path) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError:
        return ABSENT


# ------------------------------------------------------------ tree fingerprint


def tree_fingerprint(
    config: OrchestratorConfig,
    package: WorkPackage | None = None,
    *,
    base_commit: str | None = None,
) -> str:
    """A deterministic digest of the working tree at the package boundary.

    Covers file *contents*, not just names, for every path git reports as
    modified or untracked, plus the commit the work sits on. Two runs at the
    same HEAD with different edits produce different fingerprints, which is
    exactly the case git HEAD cannot distinguish.

    Protected-artifact hashes remain a separate layer: this answers "is the tree
    the one I verified", that one answers "is the science still untouched".
    """

    facts = read_repo(config.repo)
    entries: list[tuple[str, str]] = []
    for relative in sorted(set(facts.dirty_paths)):
        normalized = relative.replace("\\", "/")
        candidate = config.repo / normalized
        entries.append(
            (normalized, _file_digest(candidate) if candidate.is_file() else ABSENT)
        )

    payload = json.dumps(
        {
            "base_commit": base_commit or "",
            "head": facts.head,
            "package": None if package is None else package.name,
            "entries": entries,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return _sha256_text(payload)


# ----------------------------------------------------------- builder evidence


@dataclass(frozen=True, slots=True)
class BuilderEvidence:
    """A previous builder run, recorded so a later process can trust it.

    This is deliberately not an ``AgentRun``: nothing here pretends a fresh
    agent call happened. It carries who built, where the report is, what the
    report said, and which workflow and package it belongs to.
    """

    builder: str
    package: str
    workflow_id: str | None
    report_path: str
    report_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "builder": self.builder,
            "package": self.package,
            "workflow_id": self.workflow_id,
            "report_path": self.report_path,
            "report_sha256": self.report_sha256,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> BuilderEvidence | None:
        if not isinstance(raw, dict):
            return None
        try:
            return cls(
                builder=str(raw["builder"]),
                package=str(raw["package"]),
                workflow_id=raw.get("workflow_id"),
                report_path=str(raw["report_path"]),
                report_sha256=str(raw["report_sha256"]),
            )
        except KeyError:
            return None


class EvidenceRefused(RuntimeError):
    """Persisted evidence cannot be trusted for this run."""


def record_builder_evidence(
    *,
    builder: str,
    package: str,
    workflow_id: str | None,
    report_path: Path,
) -> BuilderEvidence:
    """Capture a builder report so a later run can prove it is unchanged."""

    return BuilderEvidence(
        builder=builder,
        package=package,
        workflow_id=workflow_id,
        report_path=str(report_path),
        report_sha256=_file_digest(report_path),
    )


def load_builder_evidence(
    evidence: BuilderEvidence | None,
    *,
    package: str,
    expected_builder: str | None,
) -> str:
    """Return the recorded report text, or refuse to reuse it.

    Refuses when there is no evidence, when it belongs to another package or
    builder, when the report is gone, or when its contents no longer hash to
    what was recorded. Any of those means the thing being reused is not the
    thing that was verified.
    """

    if evidence is None:
        raise EvidenceRefused("no builder evidence was recorded for this package")
    if evidence.package != package:
        raise EvidenceRefused(
            f"builder evidence belongs to package {evidence.package!r}, not {package!r}"
        )
    if expected_builder is not None and evidence.builder != expected_builder:
        raise EvidenceRefused(
            f"builder evidence names {evidence.builder!r} but the state records "
            f"{expected_builder!r} as the builder"
        )
    path = Path(evidence.report_path)
    if not path.exists():
        raise EvidenceRefused(
            f"recorded builder report is missing: {evidence.report_path}"
        )
    digest = _file_digest(path)
    if digest == ABSENT:
        raise EvidenceRefused(
            f"recorded builder report could not be read: {evidence.report_path}"
        )
    if digest != evidence.report_sha256:
        raise EvidenceRefused(
            "recorded builder report has changed since it was written "
            f"(expected {evidence.report_sha256[:12]}, found {digest[:12]})"
        )
    return path.read_text(encoding="utf-8")
