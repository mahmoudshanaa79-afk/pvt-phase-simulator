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
from .evidence import fingerprint_reusable, tree_fingerprint
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

    #: Stages this plan requires to run again even though an earlier stage
    #: marker is at or past them. The executor obeys this rather than
    #: re-deriving skipping from ``completed``.
    must_rerun: frozenset[Stage] = frozenset()
    #: A committed package whose only outstanding work is the independent
    #: review it never received.
    review_only: bool = False
    #: What persisted evidence this plan intends to reuse.
    reused_evidence: tuple[str, ...] = ()

    @property
    def nothing_to_do(self) -> bool:
        return (
            self.completed is Stage.COMMITTED
            and not self.review_only
            and self.debt is None
        )

    def skips(self, stage: Stage) -> bool:
        """Whether this plan skips one stage. The plan is the authority."""

        if stage in self.must_rerun:
            return False
        return {
            Stage.BUILT: self.skip_build,
            Stage.VERIFIED: self.skip_verification,
            Stage.AUDITED: self.skip_audit,
        }.get(stage, False)

    @property
    def first_stage_to_run(self) -> str:
        if self.nothing_to_do:
            return "none"
        if self.review_only:
            return "review"
        if not self.skips(Stage.BUILT):
            return "build"
        if not self.skips(Stage.VERIFIED):
            return "verify"
        if not self.skips(Stage.AUDITED):
            return "audit"
        return "commit"

    def describe(self) -> str:
        skipped = [
            name
            for name, stage in (
                ("build", Stage.BUILT),
                ("verification", Stage.VERIFIED),
                ("audit", Stage.AUDITED),
            )
            if self.skips(stage)
        ]
        rerun = sorted(stage.value for stage in self.must_rerun)
        joined = ", ".join(skipped) if skipped else "nothing"
        text = f"completed={self.completed.value}; skipping {joined}"
        if rerun:
            text += f"; must rerun {', '.join(rerun)}"
        if self.reused_evidence:
            text += f"; reusing {', '.join(self.reused_evidence)}"
        if self.review_only:
            text += "; independent review only"
        return text


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

    # Reuse is what resume exists for, so a repository whose fingerprints can
    # never be trusted has nothing to resume into: it needs a fresh run.
    reusable, reuse_reason = fingerprint_reusable(config)
    if not reusable and completed is not Stage.NOT_STARTED:
        raise ResumeRefused(
            f"{reuse_reason}; run this package fresh rather than resuming it"
        )

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


def verification_evidence_valid(
    config: OrchestratorConfig,
    state: WorkflowState,
    package: WorkPackage,
) -> tuple[bool, str]:
    """Whether the recorded verification still describes this working tree.

    HEAD is not enough. A package's entire diff normally lives in the working
    tree, so an edit to any non-protected file leaves HEAD untouched while
    making the recorded verification describe something that no longer exists.
    """

    if state.verification_status != "passed":
        return False, f"recorded verification status is {state.verification_status!r}"
    if not state.tree_fingerprint:
        return False, "no working-tree fingerprint was recorded with the verification"
    reusable, reuse_reason = fingerprint_reusable(config)
    if not reusable:
        return False, reuse_reason
    current = tree_fingerprint(config, package, base_commit=state.base_commit)
    if current != state.tree_fingerprint:
        return False, (
            "the working tree changed since verification passed "
            f"(recorded {state.tree_fingerprint[:12]}, now {current[:12]})"
        )
    return True, "working-tree fingerprint matches the recorded verification"


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

    # A verification is reusable only if it passed *and* the tree it described
    # is still the tree in front of us.
    evidence_ok, evidence_reason = verification_evidence_valid(config, state, package)

    must_rerun: set[Stage] = set()
    reused: list[str] = []

    if stage_reached(completed, Stage.VERIFIED) and not evidence_ok:
        # Verification cannot be reused, and neither can anything that was only
        # justified by it: an audit approved a tree that no longer exists.
        must_rerun.add(Stage.VERIFIED)
        if stage_reached(completed, Stage.AUDITED):
            must_rerun.add(Stage.AUDITED)
    elif stage_reached(completed, Stage.VERIFIED):
        reused.append("verification")
    if stage_reached(completed, Stage.BUILT):
        reused.append("builder report")
    if stage_reached(completed, Stage.AUDITED) and Stage.AUDITED not in must_rerun:
        reused.append("independent audit")

    # A committed package with an open debt is not finished: it still owes the
    # independent review it never received, and that review is all it needs.
    review_only = completed is Stage.COMMITTED and debt is not None

    reason = f"resuming {package.name} from {completed.value}"
    if must_rerun:
        reason += f"; {evidence_reason}"
    if review_only:
        reason += "; committed work still owes an independent review"

    return ResumePlan(
        package=package.name,
        completed=completed,
        skip_build=stage_reached(completed, Stage.BUILT),
        skip_verification=stage_reached(completed, Stage.VERIFIED),
        skip_audit=stage_reached(completed, Stage.AUDITED),
        reason=reason,
        builder=builder,
        reviewer_required=reviewer_required,
        reviewer_available=reviewer_available,
        debt=debt,
        builder_report=_read_builder_report(state),
        must_rerun=frozenset(must_rerun),
        review_only=review_only,
        reused_evidence=tuple(reused),
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
