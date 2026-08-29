"""Workflow state machine with schema validation and atomic persistence.

The orchestrator's memory. Git and real command exit codes remain authoritative
for facts about the repository; this file only tracks where the workflow is.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Final


class WorkflowStatus(StrEnum):
    """Explicit workflow states. Never encode the process as bare booleans."""

    IDLE = "IDLE"
    PLANNING = "PLANNING"
    CODEX_RUNNING = "CODEX_RUNNING"
    CODEX_REVIEW = "CODEX_REVIEW"
    LOCAL_VERIFY = "LOCAL_VERIFY"
    AUDIT_PENDING = "AUDIT_PENDING"
    CLAUDE_RUNNING = "CLAUDE_RUNNING"
    PROVISIONAL_CODEX_REVIEW = "PROVISIONAL_CODEX_REVIEW"
    CORRECTION_REQUIRED = "CORRECTION_REQUIRED"
    CODEX_CORRECTION = "CODEX_CORRECTION"
    REAUDIT_PENDING = "REAUDIT_PENDING"
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    HUMAN_ACTION_REQUIRED = "HUMAN_ACTION_REQUIRED"
    FAILED = "FAILED"
    READY_FOR_CLAUDE_RELEASE_AUDIT = "READY_FOR_CLAUDE_RELEASE_AUDIT"


TERMINAL_STATES: Final = frozenset(
    {
        WorkflowStatus.APPROVED,
        WorkflowStatus.BLOCKED,
        WorkflowStatus.HUMAN_ACTION_REQUIRED,
        WorkflowStatus.FAILED,
        WorkflowStatus.READY_FOR_CLAUDE_RELEASE_AUDIT,
    }
)

#: States from which `resume` must re-check the agent boundary rather than
#: assume the step completed.
INTERRUPTIBLE_STATES: Final = frozenset(
    {
        WorkflowStatus.CODEX_RUNNING,
        WorkflowStatus.CLAUDE_RUNNING,
        WorkflowStatus.CODEX_CORRECTION,
        WorkflowStatus.LOCAL_VERIFY,
    }
)


#: Keys a persisted state file must carry. Declared at module scope because a
#: ``slots=True`` dataclass turns class-body constants into slot descriptors.
REQUIRED_STATE_KEYS: Final = (
    "project",
    "phase",
    "workflow_status",
    "work_packages_since_audit",
    "audit_required",
)


class StateSchemaError(ValueError):
    """Raised when the persisted state file does not match the expected schema."""


@dataclass(slots=True)
class WorkflowState:
    """Persisted orchestration state."""

    project: str = "pvt-phase-simulator"
    phase: str = "post-roadmap"
    workflow_status: WorkflowStatus = WorkflowStatus.IDLE
    last_scientific_commit: str | None = None
    last_independent_audit_commit: str | None = None
    work_packages_since_audit: int = 0
    current_work_package: str | None = None
    current_risk: str | None = None
    audit_required: bool = False
    audit_reason: str | None = None
    blocking_findings: list[dict[str, Any]] = field(default_factory=list)
    safe_defer_findings: list[dict[str, Any]] = field(default_factory=list)
    deferred_independent_audits: list[dict[str, Any]] = field(default_factory=list)
    planned_scope: str | None = None
    planned_scope_complete: bool = False
    codex_correction_cycles: int = 0
    claude_reaudit_cycles: int = 0
    provisional_review_cycles: int = 0
    #: Cumulative reported auditor spend for the current work package.
    claude_cost_usd_this_package: float = 0.0
    #: Auditor runs whose cost the CLI did not report. Cost is never estimated,
    #: so these runs are governed by the cycle limits instead of the budget.
    claude_cost_unknown_runs: int = 0
    last_error: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)

    # ---------------------------------------------------------------- schema

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> WorkflowState:
        if not isinstance(raw, dict):
            raise StateSchemaError("workflow state must be a JSON object")
        missing = [key for key in REQUIRED_STATE_KEYS if key not in raw]
        if missing:
            raise StateSchemaError(f"workflow state missing required keys: {missing}")

        status_raw = raw["workflow_status"]
        try:
            status = WorkflowStatus(status_raw)
        except ValueError as error:
            raise StateSchemaError(
                f"unknown workflow_status {status_raw!r}; "
                f"expected one of {[s.value for s in WorkflowStatus]}"
            ) from error

        if not isinstance(raw["work_packages_since_audit"], int):
            raise StateSchemaError("work_packages_since_audit must be an integer")
        if not isinstance(raw["audit_required"], bool):
            raise StateSchemaError("audit_required must be a boolean")

        for list_key in (
            "blocking_findings",
            "safe_defer_findings",
            "deferred_independent_audits",
            "history",
        ):
            value = raw.get(list_key, [])
            if not isinstance(value, list):
                raise StateSchemaError(f"{list_key} must be a list")

        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        payload = {k: v for k, v in raw.items() if k in known}
        payload["workflow_status"] = status
        return cls(**payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "phase": self.phase,
            "workflow_status": self.workflow_status.value,
            "last_scientific_commit": self.last_scientific_commit,
            "last_independent_audit_commit": self.last_independent_audit_commit,
            "work_packages_since_audit": self.work_packages_since_audit,
            "current_work_package": self.current_work_package,
            "current_risk": self.current_risk,
            "audit_required": self.audit_required,
            "audit_reason": self.audit_reason,
            "blocking_findings": self.blocking_findings,
            "safe_defer_findings": self.safe_defer_findings,
            "deferred_independent_audits": self.deferred_independent_audits,
            "planned_scope": self.planned_scope,
            "planned_scope_complete": self.planned_scope_complete,
            "codex_correction_cycles": self.codex_correction_cycles,
            "claude_reaudit_cycles": self.claude_reaudit_cycles,
            "provisional_review_cycles": self.provisional_review_cycles,
            "claude_cost_usd_this_package": self.claude_cost_usd_this_package,
            "claude_cost_unknown_runs": self.claude_cost_unknown_runs,
            "last_error": self.last_error,
            "history": self.history[-200:],
        }

    # ------------------------------------------------------------ transitions

    def transition(self, new_status: WorkflowStatus, reason: str) -> None:
        """Record a state change with its reason so the log explains itself."""

        self.history.append(
            {
                "from": self.workflow_status.value,
                "to": new_status.value,
                "reason": reason,
            }
        )
        self.workflow_status = new_status


def load_state(path: Path) -> WorkflowState:
    """Load and validate state, returning a fresh IDLE state when absent."""

    if not path.exists():
        return WorkflowState()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return WorkflowState.from_dict(raw)


def save_state(path: Path, state: WorkflowState) -> None:
    """Persist atomically so an interrupted write cannot corrupt the file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state.to_dict(), indent=2) + "\n"
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
