"""Local verification. This — not any agent's claim — is authoritative."""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .config import OrchestratorConfig, sha256_file
from .gitops import diff_check, read_repo


@dataclass(slots=True)
class CommandResult:
    command: tuple[str, ...]
    exit_code: int
    started: str
    ended: str
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "command": list(self.command),
            "exit_code": self.exit_code,
            "started": self.started,
            "ended": self.ended,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


@dataclass(slots=True)
class VerificationReport:
    passed: bool
    commands: list[CommandResult] = field(default_factory=list)
    protected_ok: bool = True
    protected_detail: dict[str, str] = field(default_factory=dict)
    scope_ok: bool = True
    scope_detail: str = ""
    diff_check_ok: bool = True
    diff_check_detail: str = ""
    changed_files: tuple[str, ...] = ()
    report_path: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "protected_ok": self.protected_ok,
            "protected_detail": self.protected_detail,
            "scope_ok": self.scope_ok,
            "scope_detail": self.scope_detail,
            "diff_check_ok": self.diff_check_ok,
            "diff_check_detail": self.diff_check_detail,
            "changed_files": list(self.changed_files),
            "report_path": self.report_path,
            "commands": [c.to_dict() for c in self.commands],
        }

    def summary(self) -> str:
        lines = []
        for command in self.commands:
            mark = "PASS" if command.ok else f"FAIL({command.exit_code})"
            lines.append(f"  {mark:>10}  {' '.join(command.command)}")
        if not self.protected_ok:
            lines.append(
                f"  {'FAIL':>10}  protected artifacts: {self.protected_detail}"
            )
        if not self.scope_ok:
            lines.append(f"  {'FAIL':>10}  scope: {self.scope_detail}")
        if not self.diff_check_ok:
            lines.append(f"  {'FAIL':>10}  git diff --check")
        return "\n".join(lines)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _exclude_orchestrator_artifacts(
    config: OrchestratorConfig, paths: tuple[str, ...]
) -> tuple[str, ...]:
    """Drop the orchestrator's own bookkeeping from a work package's diff.

    Work orders, agent transcripts, verification records and workflow state are
    written into the AI directory while a package runs. They are not part of the
    package's change: counting them would trip the scope guard on every run and
    would sweep scratch files into a science commit.
    """

    try:
        marker = config.ai_dir.relative_to(config.repo).as_posix()
    except ValueError:
        return paths
    prefix = marker.rstrip("/") + "/"
    return tuple(
        path
        for path in paths
        if not (
            path.replace("\\", "/") == marker
            or path.replace("\\", "/").startswith(prefix)
        )
    )


def _resolve_command(config: OrchestratorConfig, command: tuple[str, ...]) -> list[str]:
    """Make a relative executable absolute against the repository root.

    Windows resolves a relative program path against the *calling* process's
    working directory, not the ``cwd`` passed to ``subprocess.run``, so a
    configured command like ``.venv/Scripts/python.exe`` would not be found.
    """

    if not command:
        return []
    head, *rest = command
    candidate = Path(head)
    if not candidate.is_absolute():
        local = config.repo / candidate
        if local.exists():
            return [str(local), *rest]
    return list(command)


def run_command(
    config: OrchestratorConfig, command: tuple[str, ...], timeout: int | None = None
) -> CommandResult:
    started = _now()
    try:
        completed = subprocess.run(
            _resolve_command(config, command),
            cwd=str(config.repo),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout or config.limits.max_agent_runtime_minutes * 60,
        )
        return CommandResult(
            command=command,
            exit_code=completed.returncode,
            started=started,
            ended=_now(),
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    except OSError as error:
        # A missing or unrunnable command is a verification failure, not an
        # orchestrator crash: record it and let the gate fail normally.
        return CommandResult(
            command=command,
            exit_code=127,
            started=started,
            ended=_now(),
            stdout="",
            stderr=f"could not execute {command[0]!r}: {error}",
        )
    except subprocess.TimeoutExpired as error:
        return CommandResult(
            command=command,
            exit_code=124,
            started=started,
            ended=_now(),
            stdout=(error.stdout or b"").decode(errors="replace")
            if isinstance(error.stdout, bytes)
            else (error.stdout or ""),
            stderr=f"timeout after {error.timeout}s",
        )


def check_protected_artifacts(
    config: OrchestratorConfig,
) -> tuple[bool, dict[str, str]]:
    """Recompute every configured immutable hash. Never regenerate them."""

    detail: dict[str, str] = {}
    ok = True
    for relative, expected in config.protected_artifacts.items():
        path = config.repo / relative
        if not path.exists():
            detail[relative] = "MISSING"
            ok = False
            continue
        actual = sha256_file(path)
        if actual != expected.upper():
            detail[relative] = (
                f"CHANGED expected={expected[:16]}… actual={actual[:16]}…"
            )
            ok = False
        else:
            detail[relative] = "unchanged"
    return ok, detail


def check_scope(
    config: OrchestratorConfig,
    changed: tuple[str, ...],
    allowed: tuple[str, ...],
    protected: tuple[str, ...],
) -> tuple[bool, str]:
    """Confirm the change touched only allowed paths and no protected path."""

    def matches(path: str, patterns: tuple[str, ...]) -> bool:
        normalized = path.replace("\\", "/")
        for pattern in patterns:
            clean = pattern.replace("\\", "/").rstrip("/")
            if normalized == clean or normalized.startswith(clean + "/"):
                return True
            if Path(normalized).match(clean):
                return True
        return False

    violated = [p for p in changed if matches(p, protected)]
    if violated:
        return False, f"protected paths modified: {violated}"
    if allowed:
        outside = [p for p in changed if not matches(p, allowed)]
        if outside:
            return False, f"files outside allowed_files: {outside}"
    return True, "scope ok"


def verify(
    config: OrchestratorConfig,
    *,
    allowed_files: tuple[str, ...] = (),
    protected_files: tuple[str, ...] = (),
    commands: tuple[tuple[str, ...], ...] | None = None,
    label: str = "verification",
    on_command: Callable[[int, int, tuple[str, ...]], None] | None = None,
) -> VerificationReport:
    """Run the full local gate and persist every output, including failures."""

    facts = read_repo(config.repo)
    changed = _exclude_orchestrator_artifacts(config, facts.dirty_paths)

    protected_ok, protected_detail = check_protected_artifacts(config)
    scope_ok, scope_detail = check_scope(
        config, changed, allowed_files, protected_files or config.protected_paths
    )
    check_ok, check_detail = diff_check(config.repo)

    selected = commands if commands is not None else config.verification_commands
    # Report progress between gates. A single gate can legitimately run for many
    # minutes, so without this a healthy long run looks like a dead one.
    results = []
    for index, command in enumerate(selected, start=1):
        if on_command is not None:
            on_command(index, len(selected), command)
        results.append(run_command(config, command))

    report = VerificationReport(
        passed=all(r.ok for r in results) and protected_ok and scope_ok and check_ok,
        commands=results,
        protected_ok=protected_ok,
        protected_detail=protected_detail,
        scope_ok=scope_ok,
        scope_detail=scope_detail,
        diff_check_ok=check_ok,
        diff_check_detail=check_detail,
        changed_files=changed,
    )

    directory = config.subdir("verification")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = directory / f"{stamp}-{label}.json"
    report.report_path = str(path.relative_to(config.repo))
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return report
