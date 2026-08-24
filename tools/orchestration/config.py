"""Orchestrator configuration: agent transports, gates, limits, protected artifacts."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when configuration is missing or malformed."""


def _resolve_glob_path(raw: str) -> str | None:
    """Resolve a path that may contain a wildcard in any segment.

    Versioned installs (``claude-code/2.1.237/claude.exe``) are matched with a
    ``*`` and the highest-sorting match wins, so an upgrade is picked up without
    editing configuration.
    """

    candidate = Path(raw)
    if "*" not in raw and "?" not in raw:
        return str(candidate) if candidate.exists() else None

    parts = candidate.parts
    fixed: list[str] = []
    for part in parts:
        if "*" in part or "?" in part:
            break
        fixed.append(part)
    root = Path(*fixed) if fixed else Path(".")
    if not root.exists():
        return None
    pattern = str(Path(*parts[len(fixed) :])).replace("\\", "/")
    matches = sorted((m for m in root.glob(pattern) if m.exists()), reverse=True)
    return str(matches[0]) if matches else None


@dataclass(frozen=True, slots=True)
class AgentConfig:
    """How to reach one agent CLI."""

    executable: str
    search_names: tuple[str, ...] = ()
    search_paths: tuple[str, ...] = ()
    args: tuple[str, ...] = ()
    timeout_seconds: int = 3600

    def resolve(self) -> str | None:
        """Locate the executable: explicit path, then PATH, then known dirs."""

        if self.executable:
            candidate = Path(self.executable)
            if candidate.exists():
                return str(candidate)
            found = shutil.which(self.executable)
            if found:
                return found
        for name in self.search_names:
            found = shutil.which(name)
            if found:
                return found
        for raw in self.search_paths:
            resolved = _resolve_glob_path(raw)
            if resolved is not None:
                return resolved
        return None


@dataclass(frozen=True, slots=True)
class Limits:
    max_codex_correction_cycles: int = 3
    max_claude_reaudit_cycles: int = 3
    max_agent_runtime_minutes: int = 60
    audit_batch_size: int = 5
    #: Passed to Claude as ``--max-budget-usd`` so the CLI enforces it natively,
    #: and also checked by the orchestrator before each audit cycle.
    max_claude_cost_usd_per_run: float = 5.0
    #: Cumulative ceiling across every audit and re-audit of one work package.
    max_claude_cost_usd_per_work_package: float = 15.0


@dataclass(frozen=True, slots=True)
class OrchestratorConfig:
    repo: Path
    ai_dir: Path
    codex: AgentConfig
    claude: AgentConfig
    limits: Limits
    verification_commands: tuple[tuple[str, ...], ...]
    fast_verification_commands: tuple[tuple[str, ...], ...]
    protected_artifacts: dict[str, str]
    protected_paths: tuple[str, ...]
    high_risk_paths: tuple[str, ...]
    browser_fallback_enabled: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    # convenience paths -------------------------------------------------
    @property
    def state_path(self) -> Path:
        return self.ai_dir / "workflow_state.json"

    @property
    def lock_path(self) -> Path:
        return self.ai_dir / "orchestrator.lock"

    def subdir(self, name: str) -> Path:
        path = self.ai_dir / name
        path.mkdir(parents=True, exist_ok=True)
        return path


def load_config(repo: Path, config_path: Path | None = None) -> OrchestratorConfig:
    path = config_path or (repo / ".ai" / "config.json")
    if not path.exists():
        raise ConfigError(f"orchestrator config not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))

    def agent(key: str) -> AgentConfig:
        section = raw.get("agents", {}).get(key)
        if not isinstance(section, dict):
            raise ConfigError(f"config.agents.{key} must be an object")
        return AgentConfig(
            executable=str(section.get("executable", "")),
            search_names=tuple(section.get("search_names", ())),
            search_paths=tuple(section.get("search_paths", ())),
            args=tuple(section.get("args", ())),
            timeout_seconds=int(section.get("timeout_seconds", 3600)),
        )

    limits_raw = raw.get("limits", {})
    limits = Limits(
        max_codex_correction_cycles=int(
            limits_raw.get("max_codex_correction_cycles", 3)
        ),
        max_claude_reaudit_cycles=int(limits_raw.get("max_claude_reaudit_cycles", 3)),
        max_agent_runtime_minutes=int(limits_raw.get("max_agent_runtime_minutes", 60)),
        audit_batch_size=int(limits_raw.get("audit_batch_size", 5)),
        max_claude_cost_usd_per_run=float(
            limits_raw.get("max_claude_cost_usd_per_run", 5.0)
        ),
        max_claude_cost_usd_per_work_package=float(
            limits_raw.get("max_claude_cost_usd_per_work_package", 15.0)
        ),
    )

    def commands(key: str) -> tuple[tuple[str, ...], ...]:
        return tuple(tuple(item) for item in raw.get(key, ()))

    return OrchestratorConfig(
        repo=repo,
        ai_dir=repo / raw.get("ai_dir", ".ai"),
        codex=agent("codex"),
        claude=agent("claude"),
        limits=limits,
        verification_commands=commands("verification_commands"),
        fast_verification_commands=commands("fast_verification_commands"),
        protected_artifacts=dict(raw.get("protected_artifacts", {})),
        protected_paths=tuple(raw.get("protected_paths", ())),
        high_risk_paths=tuple(raw.get("high_risk_paths", ())),
        browser_fallback_enabled=bool(raw.get("browser_fallback_enabled", False)),
        extra=raw,
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()
