"""Work-package definitions and risk assessment.

The orchestrator never invents project scope. Every run is driven by an
explicit, inspectable work-package file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class Risk(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class PackageStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    VERIFIED = "VERIFIED"
    AUDITED = "AUDITED"
    COMMITTED = "COMMITTED"
    BLOCKED = "BLOCKED"


class AuditPolicy(StrEnum):
    BATCH = "BATCH"  # counts toward the milestone batch
    IMMEDIATE = "IMMEDIATE"  # audit before the package is considered done
    NONE = "NONE"  # never audited (documentation-only chores)


class CommitPolicy(StrEnum):
    AFTER_VERIFY = "AFTER_VERIFY"
    AFTER_AUDIT = "AFTER_AUDIT"
    MANUAL = "MANUAL"


@dataclass(slots=True)
class WorkPackage:
    name: str
    objective: str
    risk: Risk = Risk.MEDIUM
    allowed_files: tuple[str, ...] = ()
    protected_files: tuple[str, ...] = ()
    scientific_invariants: tuple[str, ...] = ()
    required_tests: tuple[tuple[str, ...], ...] = ()
    required_quality_gates: tuple[tuple[str, ...], ...] = ()
    audit_policy: AuditPolicy = AuditPolicy.BATCH
    commit_policy: CommitPolicy = CommitPolicy.AFTER_VERIFY
    dependencies: tuple[str, ...] = ()
    status: PackageStatus = PackageStatus.PENDING
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> WorkPackage:
        for key in ("name", "objective"):
            if key not in raw:
                raise ValueError(f"work package missing required key {key!r}")
        return cls(
            name=str(raw["name"]),
            objective=str(raw["objective"]),
            risk=Risk(raw.get("risk", "MEDIUM")),
            allowed_files=tuple(raw.get("allowed_files", ())),
            protected_files=tuple(raw.get("protected_files", ())),
            scientific_invariants=tuple(raw.get("scientific_invariants", ())),
            required_tests=tuple(tuple(c) for c in raw.get("required_tests", ())),
            required_quality_gates=tuple(
                tuple(c) for c in raw.get("required_quality_gates", ())
            ),
            audit_policy=AuditPolicy(raw.get("audit_policy", "BATCH")),
            commit_policy=CommitPolicy(raw.get("commit_policy", "AFTER_VERIFY")),
            dependencies=tuple(raw.get("dependencies", ())),
            status=PackageStatus(raw.get("status", "PENDING")),
            notes=str(raw.get("notes", "")),
            extra=raw,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "objective": self.objective,
            "risk": self.risk.value,
            "allowed_files": list(self.allowed_files),
            "protected_files": list(self.protected_files),
            "scientific_invariants": list(self.scientific_invariants),
            "required_tests": [list(c) for c in self.required_tests],
            "required_quality_gates": [list(c) for c in self.required_quality_gates],
            "audit_policy": self.audit_policy.value,
            "commit_policy": self.commit_policy.value,
            "dependencies": list(self.dependencies),
            "status": self.status.value,
            "notes": self.notes,
        }


def load_package(path: Path) -> WorkPackage:
    return WorkPackage.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_package(path: Path, package: WorkPackage) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(package.to_dict(), indent=2) + "\n", encoding="utf-8")


def list_packages(directory: Path) -> list[WorkPackage]:
    if not directory.exists():
        return []
    packages = []
    for path in sorted(directory.glob("*.json")):
        try:
            packages.append(load_package(path))
        except (ValueError, json.JSONDecodeError):
            continue
    return packages


def next_package(directory: Path) -> WorkPackage | None:
    """First package whose dependencies are all committed."""

    packages = list_packages(directory)
    done = {p.name for p in packages if p.status is PackageStatus.COMMITTED}
    for package in packages:
        if package.status in (PackageStatus.COMMITTED, PackageStatus.BLOCKED):
            continue
        if all(dependency in done for dependency in package.dependencies):
            return package
    return None


def assess_risk(
    declared: Risk, changed_files: tuple[str, ...], high_risk_paths: tuple[str, ...]
) -> tuple[Risk, str]:
    """Escalate declared risk when a change actually touches scientific code.

    Risk is never *lowered* by this function, and a package cannot declare its
    way out of an audit by touching EOS code under a LOW label.
    """

    def touches(path: str) -> bool:
        normalized = path.replace("\\", "/")
        for pattern in high_risk_paths:
            clean = pattern.replace("\\", "/").rstrip("/")
            if normalized == clean or normalized.startswith(clean + "/"):
                return True
            if Path(normalized).match(clean):
                return True
        return False

    hits = [p for p in changed_files if touches(p)]
    if hits and declared is not Risk.HIGH:
        return Risk.HIGH, (
            "escalated to HIGH: change touches scientific paths "
            f"{hits[:6]}{'…' if len(hits) > 6 else ''}"
        )
    if hits:
        return Risk.HIGH, f"HIGH as declared; scientific paths touched: {hits[:6]}"
    return declared, f"{declared.value} as declared; no scientific path touched"
