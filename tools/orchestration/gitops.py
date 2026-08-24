"""Read-only git inspection plus a deliberately narrow commit helper.

Repository facts come from here, never from the workflow state file. The
orchestrator is forbidden from running history-rewriting or destructive git
commands; those are enumerated and refused rather than merely avoided.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

#: Operations the orchestrator must never run autonomously.
FORBIDDEN_GIT: tuple[tuple[str, ...], ...] = (
    ("reset", "--hard"),
    ("clean", "-fd"),
    ("push", "--force"),
    ("push", "-f"),
    ("rebase",),
    ("commit", "--amend"),
    ("filter-branch",),
    ("reflog", "expire"),
)


class ForbiddenGitOperation(RuntimeError):
    """Raised when a destructive git operation is attempted."""


def _guard(args: list[str]) -> None:
    lowered = [a.lower() for a in args]
    for pattern in FORBIDDEN_GIT:
        if all(token in lowered for token in pattern):
            raise ForbiddenGitOperation(
                f"refusing destructive git operation: git {' '.join(args)}"
            )


def git(repo: Path, *args: str, check: bool = True) -> str:
    """Run a guarded git command and return stdout."""

    _guard(list(args))
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed ({result.returncode}): "
            f"{result.stderr.strip()}"
        )
    return result.stdout


@dataclass(frozen=True, slots=True)
class RepoFacts:
    """Authoritative repository state, read fresh from git."""

    head: str
    short_head: str
    branch: str
    is_clean: bool
    staged: tuple[str, ...]
    modified: tuple[str, ...]
    untracked: tuple[str, ...]

    @property
    def dirty_paths(self) -> tuple[str, ...]:
        return tuple(sorted({*self.staged, *self.modified, *self.untracked}))


def read_repo(repo: Path) -> RepoFacts:
    head = git(repo, "rev-parse", "HEAD").strip()
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    staged = tuple(
        line
        for line in git(repo, "diff", "--cached", "--name-only").splitlines()
        if line
    )
    porcelain = git(repo, "status", "--porcelain").splitlines()
    modified: list[str] = []
    untracked: list[str] = []
    for line in porcelain:
        if not line.strip():
            continue
        code, _, path = line[:2], line[2:3], line[3:]
        if code.strip() == "??":
            untracked.append(path)
        elif code[1] != " ":
            modified.append(path)
    return RepoFacts(
        head=head,
        short_head=head[:7],
        branch=branch,
        is_clean=not porcelain,
        staged=staged,
        modified=tuple(modified),
        untracked=tuple(untracked),
    )


def changed_files(repo: Path, base: str | None = None) -> tuple[str, ...]:
    """Files changed in the working tree, or since `base` when given."""

    args = ["diff", "--name-only"] if base is None else ["diff", "--name-only", base]
    tracked = [line for line in git(repo, *args).splitlines() if line]
    untracked = [
        line
        for line in git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
        if line
    ]
    return tuple(sorted({*tracked, *untracked}))


def diff_stat(repo: Path, base: str | None = None) -> str:
    return (
        git(repo, "diff", "--stat")
        if base is None
        else git(repo, "diff", "--stat", base)
    )


def diff_check(repo: Path) -> tuple[bool, str]:
    """`git diff --check` — whitespace/conflict-marker damage detector."""

    result = subprocess.run(
        ["git", "diff", "--check"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0, result.stdout + result.stderr


def commit_paths(repo: Path, paths: list[str], message: str) -> str:
    """Stage exactly `paths`, verify the staged set, then commit.

    Returns the new commit hash. Raises if the staged set does not match
    exactly what was requested, so an unexpected file can never ride along.
    """

    git(repo, "add", "--", *paths)
    staged = sorted(
        line
        for line in git(repo, "diff", "--cached", "--name-only").splitlines()
        if line
    )
    expected = sorted(set(paths))
    unexpected = [p for p in staged if p not in expected and not _within(p, expected)]
    if unexpected:
        raise RuntimeError(
            f"refusing commit: unexpected staged files {unexpected} "
            f"(expected {expected})"
        )
    if not staged:
        raise RuntimeError("refusing commit: nothing staged")
    subprocess.run(
        ["git", "commit", "-F", "-"],
        cwd=str(repo),
        input=message,
        text=True,
        capture_output=True,
        check=True,
    )
    return git(repo, "rev-parse", "HEAD").strip()


def _within(path: str, roots: list[str]) -> bool:
    """True when `path` sits under one of the requested directory roots."""

    normalized = path.replace("\\", "/")
    for root in roots:
        root_normalized = root.replace("\\", "/").rstrip("/")
        if normalized == root_normalized or normalized.startswith(
            root_normalized + "/"
        ):
            return True
    return False
