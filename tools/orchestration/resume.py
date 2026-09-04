"""Deciding what a resumed run may safely skip.

The state file already records how far a package got. This module decides
whether that record can still be trusted, and if so which stages must run
again. Every check here exists to answer one question: does the persisted state
still describe *this* repository? When it does not, the answer is never a guess
- it is a refusal.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .auditdebt import AuditDebt, load, open_debts
from .config import OrchestratorConfig
from .gitops import RepoFacts
from .roles import COUNTERPART, AgentIdentity, Availability
from .state import Stage, WorkflowState, WorkflowStatus, stage_reached
from .verify import check_protected_artifacts
from .workpackage import WorkPackage


class ResumeRefused(RuntimeError):
    """The persisted state and the repository disagree; stop rather than guess."""


@dataclass(frozen=True, slots=True)
class ResumePlan:
    """What a resumed run will skip, what it will do, and why."""

    package: str
    completed: Stage
    skip_build: bool
    skip_verification: bool
    skip_audit: bool
    reason: str
    builder: AgentIdentity | None = None
    reviewer_required: AgentIdentity | None = None
    reviewer_available: bool = False
    debt: AuditDebt | None = None
    builder_report: str = ""

    @property
    def nothing_to_do(self) -> bool:
        return self.completed is Stage.COMMITTED

    @property
    def first_stage_to_run(self) -> str:
        if self.nothing_to_do:
            return "none"
        if not self.skip_build:
            return "build"
        if not self.skip_verification:
            return "verify"
        if not self.skip_audit:
            return "audit"
        return "commit"

    def describe(self) -> str:
        skipped = [
            name
            for name, skipped_flag in (
                ("build", self.skip_build),
                ("verification", self.skip_verification),
                ("audit", self.skip_audit),
            )
            if skipped_flag
        ]
        joined = ", ".join(skipped) if skipped else "nothing"
        return f"completed={self.completed.value}; skipping {joined}"


def _completed_stage(state: WorkflowState) -> Stage:
    """The last stage the state claims finished, defaulting to nothing."""

    raw = state.last_completed_stage
    if not raw:
        return Stage.NOT_STARTED
    try:
        return Stage(raw)
    except ValueError as error:
        raise ResumeRefused(
            f"persisted last_completed_stage {raw!r} is not a known stage"
        ) from error


def _open_debt_for(state: WorkflowState, package: str) -> AuditDebt | None:
    for debt in open_debts(load(state.deferred_independent_audits)):
        if debt.package == package:
            return debt
    return None


def _read_builder_report(state: WorkflowState) -> str:
    """Recover the builder's report so a resumed audit still sees it.

    The AgentRun itself died with the previous process; its transcript did not.
    """

    raw = state.builder_report_path
    if not raw:
        return ""
    path = Path(raw)
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def validate(
    config: OrchestratorConfig,
    state: WorkflowState,
    package: WorkPackage,
    facts: RepoFacts,
) -> Stage:
    """Confirm the persisted state still describes this repository.

    Returns the completed stage when the state is trustworthy, and raises
    :class:`ResumeRefused` with a specific reason when it is not.
    """

    if not state.current_work_package:
        raise ResumeRefused("no work package is recorded in the persisted state")
    if state.current_work_package != package.name:
        raise ResumeRefused(
            f"persisted state is for package {state.current_work_package!r}, "
            f"but {package.name!r} was selected; refusing to mix them"
        )

    completed = _completed_stage(state)

    protected_ok, protected_detail = check_protected_artifacts(config)
    if not protected_ok:
        raise ResumeRefused(
            f"protected artifacts no longer match their recorded hashes: "
            f"{protected_detail}"
        )

    # The commit boundary must be exactly where the state left it. Anything
    # else means work happened outside the workflow and the recorded stages no
    # longer describe the current diff.
    if state.resulting_commit:
        if facts.head != state.resulting_commit:
            raise ResumeRefused(
                f"state records the package as committed at "
                f"{state.resulting_commit[:12]}, but HEAD is {facts.short_head}"
            )
    elif state.base_commit:
        if facts.head != state.base_commit:
            raise ResumeRefused(
                f"state records an uncommitted package based on "
                f"{state.base_commit[:12]}, but HEAD is {facts.short_head}; "
                "the recorded stages no longer describe this diff"
            )
    elif completed is not Stage.NOT_STARTED:
        raise ResumeRefused(
            "state records completed stages but no commit boundary; "
            "there is nothing to anchor the resume to"
        )

    # Checked before the general build check below so the diagnostic names the
    # actual inconsistency rather than a symptom of it.
    if completed is Stage.COMMITTED and not state.resulting_commit:
        raise ResumeRefused(
            "state records a committed package without recording its commit"
        )

    # A completed build that left no trace cannot be skipped: either the work
    # was reverted or it was committed without the state being updated.
    if (
        stage_reached(completed, Stage.BUILT)
        and not state.resulting_commit
        and facts.is_clean
    ):
        raise ResumeRefused(
            "state records a completed build, but the working tree is clean and "
            "no package commit is recorded; the built work is not present"
        )

    return completed


def plan(
    config: OrchestratorConfig,
    state: WorkflowState,
    package: WorkPackage,
    facts: RepoFacts,
    availability: dict[AgentIdentity, Availability],
) -> ResumePlan:
    """Validate, then decide which stages a resumed run may skip."""

    completed = validate(config, state, package, facts)

    builder: AgentIdentity | None = None
    if state.builder:
        try:
            builder = AgentIdentity(state.builder)
        except ValueError:
            builder = None

    reviewer_required = None if builder is None else COUNTERPART[builder]
    reviewer_status = (
        None if reviewer_required is None else availability.get(reviewer_required)
    )
    reviewer_available = bool(reviewer_status and reviewer_status.available)

    debt = _open_debt_for(state, package.name)

    # A verification that was running when the process died is not a completed
    # verification, whatever the stage marker says about earlier work.
    verification_trustworthy = state.verification_status == "passed"
    skip_verification = (
        stage_reached(completed, Stage.VERIFIED) and verification_trustworthy
    )

    reason = f"resuming {package.name} from {completed.value}"
    if stage_reached(completed, Stage.VERIFIED) and not verification_trustworthy:
        reason += (
            "; verification is re-run because its recorded status is "
            f"{state.verification_status!r}"
        )

    return ResumePlan(
        package=package.name,
        completed=completed,
        skip_build=stage_reached(completed, Stage.BUILT),
        skip_verification=skip_verification,
        skip_audit=stage_reached(completed, Stage.AUDITED),
        reason=reason,
        builder=builder,
        reviewer_required=reviewer_required,
        reviewer_available=reviewer_available,
        debt=debt,
        builder_report=_read_builder_report(state),
    )


def resumable(state: WorkflowState, package_name: str) -> tuple[bool, str]:
    """Whether a resume may be attempted at all from the current status.

    A workflow blocked for a human is normally not resumable. The one exception
    is a deferred independent audit: that block exists because a reviewer was
    missing, so it clears itself the moment the reviewer is back.
    """

    status = state.workflow_status
    if status is WorkflowStatus.HUMAN_ACTION_REQUIRED:
        debt = _open_debt_for(state, package_name)
        if debt is not None:
            return True, (
                f"blocked by a deferred independent audit ({debt.id}); "
                f"resume will attempt {debt.reviewer_required}"
            )
        return False, f"blocked for a human: {state.last_error}"
    if status in {
        WorkflowStatus.CODEX_RUNNING,
        WorkflowStatus.CLAUDE_RUNNING,
        WorkflowStatus.CODEX_CORRECTION,
        WorkflowStatus.LOCAL_VERIFY,
        WorkflowStatus.CODEX_REVIEW,
        WorkflowStatus.AUDIT_PENDING,
        WorkflowStatus.REAUDIT_PENDING,
        WorkflowStatus.CORRECTION_REQUIRED,
        WorkflowStatus.PLANNING,
    }:
        return True, f"interrupted during {status.value}"
    return False, f"nothing to resume from {status.value}; use `run`"
