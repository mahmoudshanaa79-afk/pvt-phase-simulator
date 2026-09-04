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
from typing import Any, Final

from .config import OrchestratorConfig
from .gitops import git, read_repo
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

#: Paths the orchestrator itself writes while a package is in flight. They
#: change after verification by design - a heartbeat is written every few
#: seconds - so including them would make every fingerprint unstable.
RUNTIME_EXCLUDED_PREFIXES: Final = (
    ".ai/runtime/",
    ".ai/workflow_state.json",
    ".ai/orchestrator.lock",
    ".ai/verification/",
    ".ai/codex_reports/",
    ".ai/codex_audits/",
    ".ai/claude_audits/",
    ".ai/claude_builds/",
    ".ai/work_orders/",
    ".ai/workflow_logs/",
    ".ai/provisional_reviews/",
    ".ai/builder_reports/",
)

#: Git's mode for a submodule entry. Its content is another repository, so the
#: fingerprint records the commit it points at rather than recursing into it.
GITLINK_MODE: Final = "160000"


def _excluded(relative: str) -> bool:
    return any(relative.startswith(prefix) for prefix in RUNTIME_EXCLUDED_PREFIXES)


def _tracked_entries(repo: Path) -> list[tuple[str, str]]:
    """Every tracked path with its index mode, from git's own index.

    Deliberately not ``git status``: status can be told to hide a modified file
    (``assume-unchanged``/``skip-worktree``), and a fingerprint that trusts
    status inherits that blindness. ``ls-files -s`` lists what is tracked
    regardless of any such flag.
    """

    raw = git(repo, "ls-files", "-s", "-z")
    entries: list[tuple[str, str]] = []
    for record in raw.split("\0"):
        if not record:
            continue
        # "<mode> <sha> <stage>	<path>"
        meta, _, path = record.partition("	")
        if not path:
            continue
        parts = meta.split()
        mode = parts[0] if parts else ""
        sha = parts[1] if len(parts) > 1 else ""
        entries.append((path.replace("\\", "/"), f"{mode}:{sha}"))
    return entries


def _untracked_paths(repo: Path) -> list[str]:
    """Untracked, non-ignored files. Ignored files are not package content."""

    raw = git(repo, "ls-files", "-o", "--exclude-standard", "-z")
    return [path.replace("\\", "/") for path in raw.split("\0") if path]


def _submodule_state(repo: Path, relative: str, index_sha: str) -> str:
    """Describe a submodule without hashing its whole content tree.

    The index gitlink alone says only which commit the parent *expects*. It says
    nothing about the commit actually checked out, and nothing about uncommitted
    edits inside the submodule - so a submodule advanced or dirtied underneath a
    verification would leave the fingerprint unchanged. Recording the checked-out
    HEAD and a dirty flag closes both without walking the submodule's files.
    """

    working = repo / relative
    if not working.exists():
        # Declared in the index but not checked out. That is a real, describable
        # state, not a failure to read one.
        return f"submodule:index={index_sha}:head=absent:dirty=unknown"

    try:
        head = git(working, "rev-parse", "HEAD").strip()
    except (RuntimeError, OSError) as error:
        raise SubmoduleUnreadable(
            f"cannot read HEAD of submodule {relative!r}: {error}"
        ) from error
    if not head:
        raise SubmoduleUnreadable(f"submodule {relative!r} reported no HEAD")

    try:
        status = git(working, "status", "--porcelain", "--untracked-files=normal")
    except (RuntimeError, OSError) as error:
        raise SubmoduleUnreadable(
            f"cannot read the working tree of submodule {relative!r}: {error}"
        ) from error

    dirty = "yes" if status.strip() else "no"
    return f"submodule:index={index_sha}:head={head}:dirty={dirty}"


def tree_fingerprint(
    config: OrchestratorConfig,
    package: WorkPackage | None = None,
    *,
    base_commit: str | None = None,
) -> str:
    """A deterministic digest of the package's working tree.

    The path set comes from git's index and its untracked listing, not from
    ``git status``, so a tracked file whose modification status is suppressed is
    still fingerprinted. Contents are hashed from disk; submodules record the
    commit they point at rather than being walked. Orchestrator runtime files are
    excluded because they change while a package is in flight and would make
    every fingerprint differ from itself.
    """

    facts = read_repo(config.repo)
    entries: list[tuple[str, str]] = []

    for relative, index_meta in _tracked_entries(config.repo):
        if _excluded(relative):
            continue
        if index_meta.startswith(f"{GITLINK_MODE}:"):
            entries.append(
                (
                    relative,
                    _submodule_state(
                        config.repo, relative, index_meta.split(":", 1)[1]
                    ),
                )
            )
            continue
        candidate = config.repo / relative
        entries.append(
            (relative, _file_digest(candidate) if candidate.is_file() else ABSENT)
        )

    for relative in _untracked_paths(config.repo):
        if _excluded(relative):
            continue
        candidate = config.repo / relative
        if candidate.is_file():
            entries.append((relative, _file_digest(candidate)))

    entries.sort()
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
    #: Which implementation revision this report belongs to. A correction
    #: produces a new revision, and reusing an earlier revision's report would
    #: describe work that has since been replaced.
    revision: int = 1
    #: "build" or "correction".
    kind: str = "build"

    def to_dict(self) -> dict[str, Any]:
        return {
            "builder": self.builder,
            "package": self.package,
            "workflow_id": self.workflow_id,
            "report_path": self.report_path,
            "report_sha256": self.report_sha256,
            "revision": self.revision,
            "kind": self.kind,
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
                revision=int(raw.get("revision", 1)),
                kind=str(raw.get("kind", "build")),
            )
        except KeyError:
            return None


class EvidenceRefused(RuntimeError):
    """Persisted evidence cannot be trusted for this run."""


class SubmoduleUnreadable(RuntimeError):
    """A submodule's state could not be read, so the tree cannot be described."""


def record_builder_evidence(
    *,
    builder: str,
    package: str,
    workflow_id: str | None,
    report_path: Path,
    revision: int = 1,
    kind: str = "build",
) -> BuilderEvidence:
    """Capture a builder report so a later run can prove it is unchanged."""

    return BuilderEvidence(
        builder=builder,
        package=package,
        workflow_id=workflow_id,
        report_path=str(report_path),
        report_sha256=_file_digest(report_path),
        revision=revision,
        kind=kind,
    )


def load_builder_evidence(
    evidence: BuilderEvidence | None,
    *,
    package: str,
    expected_builder: str | None,
    expected_workflow_id: str | None = None,
    expected_revision: int | None = None,
    allow_missing_workflow_id: bool = False,
) -> str:
    """Return the recorded report text, or refuse to reuse it.

    Refuses when there is no evidence, when it belongs to another package,
    builder, workflow or revision, when the report is gone, or when its contents
    no longer hash to what was recorded. Any of those means the thing being
    reused is not the thing that was verified.

    ``allow_missing_workflow_id`` exists only for explicit manual reconciliation
    of evidence written before workflow identity was recorded. Normal resume
    never sets it.
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
    if expected_workflow_id is not None:
        # Strict: when this run has an identity, the evidence must carry the
        # same one. Absent identity is not a pass - it is evidence that cannot
        # prove it belongs to this run, which is the whole question being asked.
        if evidence.workflow_id is None or evidence.workflow_id == "":
            if not allow_missing_workflow_id:
                raise EvidenceRefused(
                    "builder evidence records no workflow identity, so it cannot "
                    f"be shown to belong to workflow {expected_workflow_id!r}; "
                    "reconcile it explicitly if it is genuinely this run's work"
                )
        elif evidence.workflow_id != expected_workflow_id:
            raise EvidenceRefused(
                f"builder evidence belongs to workflow {evidence.workflow_id!r}, "
                f"not {expected_workflow_id!r}"
            )
    if expected_revision is not None and evidence.revision != expected_revision:
        raise EvidenceRefused(
            f"builder evidence is for revision {evidence.revision}, but the "
            f"current implementation revision is {expected_revision}"
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
