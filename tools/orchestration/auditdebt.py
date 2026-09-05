"""Deferred independent audits, and the reconciliation that later clears them.

v1 recorded that a package still owed an independent audit, but nothing could
ever mark that debt paid. The entries went stale, and a package that had in fact
been reviewed still read as ``PENDING_INDEPENDENT_AUDIT`` forever. This module
gives the debt a lifecycle: it is opened by whoever built without an independent
reviewer, and closed only by evidence naming a reviewer who is not that builder.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

PENDING: Final = "PENDING_INDEPENDENT_AUDIT"
CLEARED: Final = "INDEPENDENT_AUDIT_COMPLETE"


class EvidenceKind(StrEnum):
    """How an independent review was actually obtained."""

    AGENT = "agent_review"
    #: A review a human ran outside the orchestrator and explicitly vouched for.
    EXTERNAL = "external_review"


class DebtError(ValueError):
    """Raised when a debt operation would record something untrue."""


def debt_id(package: str, commit: str) -> str:
    """Identity of one debt: a package at a specific resulting commit.

    Keying on both is what prevents the same package from being counted twice
    when it is rebuilt, and prevents two different commits collapsing into one
    approval.
    """

    return f"{package}@{(commit or '')[:12]}"


@dataclass(slots=True)
class AuditDebt:
    """One package that was committed without an independent review."""

    package: str
    resulting_commit: str
    builder: str
    reviewer_required: str
    reason: str
    status: str = PENDING
    base_commit: str | None = None
    effective_risk: str | None = None
    opened_at: float = field(default_factory=time.time)
    cleared_at: float | None = None
    cleared_by: str | None = None
    evidence_kind: str | None = None
    evidence: str | None = None

    @property
    def id(self) -> str:
        return debt_id(self.package, self.resulting_commit)

    @property
    def is_open(self) -> bool:
        return self.status == PENDING

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "package": self.package,
            "resulting_commit": self.resulting_commit,
            "base_commit": self.base_commit,
            "builder": self.builder,
            "reviewer_required": self.reviewer_required,
            "reason": self.reason,
            "status": self.status,
            "effective_risk": self.effective_risk,
            "opened_at": self.opened_at,
            "cleared_at": self.cleared_at,
            "cleared_by": self.cleared_by,
            "evidence_kind": self.evidence_kind,
            "evidence": self.evidence,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AuditDebt:
        known = set(cls.__dataclass_fields__)
        payload = {key: value for key, value in raw.items() if key in known}
        # v1 entries used different key names and carried no roles at all.
        payload.setdefault(
            "package", raw.get("package") or raw.get("work_package") or ""
        )
        payload.setdefault("resulting_commit", raw.get("resulting_commit") or "")
        payload.setdefault("builder", raw.get("builder") or "unknown")
        payload.setdefault(
            "reviewer_required", raw.get("reviewer_required") or "unknown"
        )
        payload.setdefault("reason", raw.get("reason") or "")
        payload.setdefault("status", raw.get("status") or PENDING)
        return cls(**payload)


def load(entries: list[dict[str, Any]]) -> list[AuditDebt]:
    return [AuditDebt.from_dict(entry) for entry in entries if isinstance(entry, dict)]


def dump(debts: list[AuditDebt]) -> list[dict[str, Any]]:
    return [debt.to_dict() for debt in debts]


def open_debts(debts: list[AuditDebt]) -> list[AuditDebt]:
    return [debt for debt in debts if debt.is_open]


def find(debts: list[AuditDebt], identifier: str) -> AuditDebt | None:
    for debt in debts:
        if debt.id == identifier:
            return debt
    return None


def record(
    debts: list[AuditDebt],
    *,
    package: str,
    resulting_commit: str,
    builder: str,
    reviewer_required: str,
    reason: str,
    base_commit: str | None = None,
    effective_risk: str | None = None,
) -> AuditDebt:
    """Open a debt, or return the existing one for the same package+commit.

    Re-recording the same package at the same commit must not create a second
    entry, otherwise the outstanding count drifts upward every time a run is
    resumed.
    """

    if builder == reviewer_required:
        raise DebtError(
            f"{builder} cannot be its own required reviewer; "
            "an independent review must name the other agent"
        )
    identifier = debt_id(package, resulting_commit)
    existing = find(debts, identifier)
    if existing is not None:
        return existing
    debt = AuditDebt(
        package=package,
        resulting_commit=resulting_commit,
        builder=builder,
        reviewer_required=reviewer_required,
        reason=reason,
        base_commit=base_commit,
        effective_risk=effective_risk,
    )
    debts.append(debt)
    return debt


UNKNOWN: Final = "unknown"


def name_builder(debt: AuditDebt, builder: str) -> AuditDebt:
    """Attach the true builder to a legacy entry that never recorded one.

    v1 debts carry no provenance, which leaves the self-review guard with
    nothing to compare against. Naming the builder is allowed exactly once, and
    never to overwrite provenance the orchestrator itself recorded.
    """

    if debt.builder not in (UNKNOWN, "", None):
        raise DebtError(
            f"audit debt {debt.id!r} already records {debt.builder!r} as its "
            "builder; refusing to rewrite recorded provenance"
        )
    if not builder or not builder.strip():
        raise DebtError("naming a builder requires a value")
    debt.builder = builder.strip()
    if debt.reviewer_required in (UNKNOWN, "", None):
        counterpart = {"codex": "claude", "claude": "codex"}.get(debt.builder)
        if counterpart is not None:
            debt.reviewer_required = counterpart
    return debt


def reconcile(
    debts: list[AuditDebt],
    *,
    identifier: str,
    reviewer: str,
    evidence: str,
    kind: EvidenceKind = EvidenceKind.AGENT,
    builder: str | None = None,
    now: float | None = None,
) -> AuditDebt:
    """Clear one debt with evidence of a genuinely independent review.

    Refuses when the debt is unknown, already cleared, or when the reviewer is
    the agent that built the work. Those are exactly the three ways a persisted
    approval could come to mean something that never happened.
    """

    debt = find(debts, identifier)
    if debt is None:
        raise DebtError(f"no audit debt with id {identifier!r}")
    if not debt.is_open:
        raise DebtError(
            f"audit debt {identifier!r} was already cleared by "
            f"{debt.cleared_by!r}; refusing to approve it twice"
        )
    if builder is not None:
        name_builder(debt, builder)
    if reviewer == debt.builder:
        raise DebtError(
            f"{reviewer} built {debt.package}; it cannot supply that package's "
            "independent review"
        )
    if not evidence or not evidence.strip():
        raise DebtError("clearing an audit debt requires evidence")
    debt.status = CLEARED
    debt.cleared_at = time.time() if now is None else now
    debt.cleared_by = reviewer
    debt.evidence_kind = kind.value
    debt.evidence = evidence.strip()
    return debt


def summary(debts: list[AuditDebt]) -> str:
    outstanding = open_debts(debts)
    if not outstanding:
        return "none"
    return ", ".join(f"{debt.id} (built by {debt.builder})" for debt in outstanding)
