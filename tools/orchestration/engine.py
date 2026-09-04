"""Routing engine: the deterministic decisions between the two agents.

The engine decides *what happens next*. It never fabricates an agent result and
never treats an agent's claim as evidence — local verification and git are the
only sources of truth.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import agents, auditdebt, prompts, roles
from . import evidence as evidence_mod
from .config import OrchestratorConfig
from .gitops import commit_paths, read_repo
from .heartbeat import Heartbeat, HeartbeatTicker
from .roles import AgentIdentity, RoleAssignment
from .state import (
    Stage,
    WorkflowState,
    WorkflowStatus,
    save_state,
)
from .verify import VerificationReport, check_protected_artifacts, verify
from .workpackage import (
    AuditPolicy,
    CommitPolicy,
    PackageStatus,
    Risk,
    WorkPackage,
    assess_risk,
    save_package,
)


@dataclass(slots=True)
class StepOutcome:
    """What one `run` produced, for the CLI to print."""

    status: WorkflowStatus
    messages: list[str] = field(default_factory=list)
    verification: VerificationReport | None = None
    audit_contract: dict[str, Any] | None = None
    provisional_review_contract: dict[str, Any] | None = None
    review_unavailable_reason: str | None = None
    commit: str | None = None
    human_action: str | None = None
    #: Who built and who must review, once decided.
    role_assignment: RoleAssignment | None = None

    def say(self, text: str) -> None:
        self.messages.append(text)


CodexRunner = Callable[..., agents.AgentRun]
ClaudeRunner = Callable[..., agents.AgentRun]
ProvisionalRunner = Callable[..., agents.AgentRun]
BuilderRunner = Callable[..., agents.AgentRun]
ReviewerRunner = Callable[..., agents.AgentRun]


class Engine:
    """Drives one work package from plan to commit or escalation."""

    def __init__(
        self,
        config: OrchestratorConfig,
        state: WorkflowState,
        *,
        codex_runner: CodexRunner | None = None,
        claude_runner: ClaudeRunner | None = None,
        provisional_runner: ProvisionalRunner | None = None,
        claude_builder_runner: BuilderRunner | None = None,
        codex_auditor_runner: ReviewerRunner | None = None,
        heartbeat: Heartbeat | None = None,
        preferred_builder: AgentIdentity | None = None,
    ) -> None:
        self.config = config
        self.state = state
        # Injectable so tests never spend a real agent call.
        self._run_codex = codex_runner or agents.run_codex
        self._run_claude = claude_runner or agents.run_claude_audit
        self._run_provisional = provisional_runner or agents.run_codex_review
        self._run_claude_builder = claude_builder_runner or agents.run_claude_builder
        self._run_codex_auditor = codex_auditor_runner or agents.run_codex_audit
        self._claude_injected = claude_runner is not None
        self._codex_injected = codex_runner is not None
        self.heartbeat = heartbeat
        #: Agents this run has already observed to be out of capacity.
        self._exhausted: set[AgentIdentity] = set()
        self.roles: RoleAssignment | None = None
        self._preferred_builder = preferred_builder

    # ------------------------------------------------------------- utilities

    def _persist(self) -> None:
        save_state(self.config.state_path, self.state)

    def _escalate(self, outcome: StepOutcome, reason: str) -> StepOutcome:
        self.state.transition(WorkflowStatus.HUMAN_ACTION_REQUIRED, reason)
        self.state.last_error = reason
        self._persist()
        outcome.status = WorkflowStatus.HUMAN_ACTION_REQUIRED
        outcome.human_action = reason
        outcome.say(f"HUMAN ACTION REQUIRED: {reason}")
        return outcome

    def _stamp(self, package: WorkPackage, suffix: str) -> str:
        return f"{time.strftime('%Y%m%d-%H%M%S')}-{package.name}-{suffix}"

    # ------------------------------------------------------------ v2 plumbing

    def _injected(self) -> frozenset[AgentIdentity]:
        """Agents backed by a test double, which are always reachable."""

        injected: set[AgentIdentity] = set()
        if self._claude_injected:
            injected.add(AgentIdentity.CLAUDE)
        if self._codex_injected:
            injected.add(AgentIdentity.CODEX)
        return frozenset(injected)

    def _beat(self, **updates: Any) -> None:
        """Update the runtime status when one is being kept."""

        if self.heartbeat is not None:
            self.heartbeat.beat(**updates)

    def _complete_stage(self, stage: Stage) -> None:
        self.state.last_completed_stage = stage.value
        self._persist()
        self._beat(stage=stage.value, workflow_status=self.state.workflow_status.value)

    def _record_role_transition(self, assignment: RoleAssignment) -> None:
        self.state.builder = assignment.builder.value
        self.state.reviewer = (
            None if assignment.reviewer is None else assignment.reviewer.value
        )
        if assignment.failed_over:
            self.state.role_transitions.append(
                {
                    "package": self.state.current_work_package,
                    "from_builder": (
                        None
                        if assignment.previous_builder is None
                        else assignment.previous_builder.value
                    ),
                    "to_builder": assignment.builder.value,
                    "reason": assignment.reason,
                    "at": time.time(),
                }
            )
        self._persist()

    def assign_roles(self, *, preferred: AgentIdentity | None = None) -> RoleAssignment:
        """Decide builder and reviewer for the current package."""

        previous = None
        if self.state.builder:
            try:
                previous = AgentIdentity(self.state.builder)
            except ValueError:
                previous = None
        assignment = roles.assign_roles(
            self.config,
            preferred_builder=(
                preferred or self._preferred_builder or previous or AgentIdentity.CODEX
            ),
            injected=self._injected(),
            unavailable=frozenset(self._exhausted),
            previous_builder=previous,
        )
        self.roles = assignment
        self._record_role_transition(assignment)
        return assignment

    def _dispatch_builder(
        self, builder: AgentIdentity, package: WorkPackage, order_path: Path
    ) -> agents.AgentRun:
        stem = self._stamp(package, f"{builder.value}-report")
        if builder is AgentIdentity.CODEX:
            return self._run_codex(self.config, order_path, stem=stem)
        return self._run_claude_builder(self.config, order_path, stem=stem)

    # ------------------------------------------------------------ audit rules

    def audit_decision(
        self, package: WorkPackage, effective_risk: Risk
    ) -> tuple[bool, str]:
        """Decide whether an independent audit is required now."""

        if package.audit_policy is AuditPolicy.NONE:
            return False, "package audit_policy=NONE"
        if effective_risk is Risk.HIGH:
            return True, "HIGH-risk work package requires an immediate audit"
        if package.audit_policy is AuditPolicy.IMMEDIATE:
            return True, "package audit_policy=IMMEDIATE"
        pending = self.state.work_packages_since_audit + 1
        if pending >= self.config.limits.audit_batch_size:
            return True, (
                f"milestone batch reached ({pending} work packages since last "
                f"independent audit)"
            )
        return False, (
            f"batched: {pending}/{self.config.limits.audit_batch_size} "
            "work packages since last independent audit"
        )

    def _claude_available(self) -> tuple[bool, str]:
        if self._claude_injected:
            return True, "injected test auditor"
        return agents.agent_available(self.config.claude)

    def provisional_review_eligibility(
        self,
        package: WorkPackage,
        effective_risk: Risk,
        report: VerificationReport,
    ) -> tuple[bool, str]:
        """Enforce the absolute boundary around the temporary Codex fallback."""

        if effective_risk is Risk.HIGH:
            return False, "effective risk is HIGH"
        if package.risk not in {Risk.LOW, Risk.MEDIUM}:
            return False, "declared risk is not LOW/MEDIUM"
        if not report.passed or not report.protected_ok or not report.scope_ok:
            return False, "deterministic verification or protection checks did not pass"
        normalized = tuple(path.replace("\\", "/") for path in report.changed_files)
        scientific = [
            path
            for path in normalized
            if path == "src/pvt_phase_simulator"
            or path.startswith("src/pvt_phase_simulator/")
        ]
        if scientific:
            return False, f"scientific source changed: {scientific}"
        scientific_tests = [
            path
            for path in normalized
            if path.startswith("tests/") and not Path(path).match("tests/test_app*.py")
        ]
        if scientific_tests:
            return False, f"scientific tests changed: {scientific_tests}"
        return True, "LOW/MEDIUM application-only change with all local gates passing"

    def review_mode(
        self,
        package: WorkPackage,
        effective_risk: Risk,
        report: VerificationReport,
        *,
        needs_audit: bool,
    ) -> tuple[str, str]:
        """Choose how this package gets reviewed.

        The reviewer is always the agent that did *not* build. When that agent
        cannot run, the review is deferred as recorded debt or falls back to an
        explicitly non-independent provisional review - never to the builder
        reviewing itself.
        """

        if not needs_audit:
            return "none", "independent review is not due for this package"

        builder = self._current_builder()
        availability = roles.availability_map(
            self.config,
            injected=self._injected(),
            unavailable=frozenset(self._exhausted),
        )
        reviewer, deferred, reason = roles.select_reviewer(builder, availability)
        if not deferred and reviewer is not None:
            roles.assert_independent(builder, reviewer)
            mode = "claude" if reviewer is AgentIdentity.CLAUDE else "codex_audit"
            return mode, (
                f"{reviewer.value} independently reviews {builder.value}: {reason}"
            )

        eligible, fallback = self.provisional_review_eligibility(
            package, effective_risk, report
        )
        if eligible:
            return "provisional", f"{reason}; {fallback}"
        return "deferred", f"{reason}; provisional fallback refused: {fallback}"

    def _record_revision(self, author: AgentIdentity, kind: str) -> None:
        """Record who authored the current implementation revision.

        Ownership is per revision, not per package. After Codex corrects work
        that Claude built, the diff under review is Codex's, and Codex is the
        agent that may not audit it.
        """

        self.state.revisions.append(
            {
                "package": self.state.current_work_package,
                "revision": len(self.state.revisions) + 1,
                "author": author.value,
                "kind": kind,
                "at": time.time(),
            }
        )
        self._persist()

    def current_author(self) -> AgentIdentity:
        """The agent that authored the diff currently under review."""

        for entry in reversed(self.state.revisions):
            raw = entry.get("author")
            if raw:
                try:
                    return AgentIdentity(str(raw))
                except ValueError:
                    continue
        if self.roles is not None:
            return self.roles.builder
        if self.state.builder:
            try:
                return AgentIdentity(self.state.builder)
            except ValueError:
                pass
        return AgentIdentity.CODEX

    def _current_builder(self) -> AgentIdentity:
        """Backwards-compatible alias; ownership now follows the revision."""

        return self.current_author()

    def settle_audit_debt(
        self,
        package: WorkPackage,
        audit: agents.AgentRun,
        outcome: StepOutcome,
    ) -> auditdebt.AuditDebt | None:
        """Clear this package's outstanding debt when a real reviewer approves.

        Clearing is independent of whether the implementation is already
        committed: the debt is about who reviewed the work, not about where the
        work landed. Reconciliation itself refuses a reviewer that built the
        code and refuses to approve one debt twice.
        """

        debts = auditdebt.load(self.state.deferred_independent_audits)
        outstanding = [
            debt for debt in auditdebt.open_debts(debts) if debt.package == package.name
        ]
        if not outstanding:
            return None

        # Identity is package *and* commit. A package rebuilt at a later commit
        # owes a separate review, so approving one revision must never clear the
        # debt recorded against a different one.
        head = read_repo(self.config.repo).head
        candidates = [
            debt
            for debt in outstanding
            if debt.resulting_commit in {head, self.state.resulting_commit}
        ]
        if not candidates:
            outcome.say(
                f"no audit debt matches the reviewed commit {head[:12]}; "
                f"{len(outstanding)} debt(s) for this package remain open"
            )
            return None
        if len(candidates) > 1:
            outcome.say(
                f"{len(candidates)} debts share the reviewed commit; "
                "settling the earliest and leaving the rest open"
            )
        debt = candidates[0]

        reviewer = roles.COUNTERPART[self.current_author()].value
        try:
            cleared = auditdebt.reconcile(
                debts,
                identifier=debt.id,
                reviewer=reviewer,
                evidence=(
                    f"independent {reviewer} audit approved "
                    f"({audit.transcript_path or 'transcript preserved'})"
                ),
            )
        except auditdebt.DebtError as error:
            outcome.say(f"audit debt {debt.id} not cleared: {error}")
            return None
        outcome.say(f"cleared audit debt {debt.id} (reviewed by {reviewer})")
        self.state.deferred_independent_audits = auditdebt.dump(debts)
        if not auditdebt.open_debts(debts):
            self.state.audit_required = False
            self.state.audit_reason = None
        self._persist()
        self._beat(audit_debt=len(auditdebt.open_debts(debts)))
        return cleared

    def review_only(
        self,
        package: WorkPackage,
        package_path: Path,
        *,
        builder_report: str = "",
    ) -> StepOutcome:
        """Run only the missing independent review for committed work.

        Used when a package was committed with a deferred audit and the required
        reviewer has since returned. It never rebuilds, never re-verifies, never
        commits and never re-counts the package - the implementation is already
        in history; only the review was missing.
        """

        outcome = StepOutcome(status=WorkflowStatus.AUDIT_PENDING)
        outcome.say("independent review only: implementation is already committed")
        report = self.reconstruct_verification(package)
        if not report.protected_ok:
            return self._escalate(
                outcome,
                f"protected artifacts changed since the commit: "
                f"{report.protected_detail}",
            )

        audit = self.run_audit(
            package,
            outcome,
            codex_report=builder_report,
            verification=report,
            base_commit=self.state.base_commit,
        )
        if audit is None:
            if outcome.status is WorkflowStatus.HUMAN_ACTION_REQUIRED:
                return outcome
            return self._escalate(
                outcome,
                outcome.review_unavailable_reason
                or "the independent reviewer produced no usable result",
            )

        contract = audit.contract or {}
        verdict = contract.get("verdict")
        blocking = agents.blocking_findings(contract)
        outcome.say(f"verdict: {verdict} ({len(blocking)} blocking findings)")
        if verdict != "APPROVED" or blocking:
            self.state.blocking_findings = blocking
            self._persist()
            return self._escalate(
                outcome,
                f"independent review of committed work returned {verdict} with "
                f"{len(blocking)} blocking findings; the commit stands but the "
                "debt is not cleared",
            )

        self.settle_audit_debt(package, audit, outcome)
        self.state.last_independent_audit_commit = (
            self.state.resulting_commit or read_repo(self.config.repo).head
        )
        package.status = PackageStatus.COMMITTED
        save_package(package_path, package)
        self.state.transition(
            WorkflowStatus.APPROVED, "deferred independent audit completed"
        )
        self._persist()
        outcome.status = WorkflowStatus.APPROVED
        return outcome

    def record_audit_debt(
        self,
        package: WorkPackage,
        *,
        resulting_commit: str,
        base_commit: str | None,
        effective_risk: Risk,
        reason: str,
    ) -> auditdebt.AuditDebt:
        """Record that this package still owes an independent review.

        The debt names who built it and which agent must review it, so it can
        later be cleared by evidence rather than by assumption.
        """

        builder = self._current_builder()
        required = roles.COUNTERPART[builder]
        debts = auditdebt.load(self.state.deferred_independent_audits)
        debt = auditdebt.record(
            debts,
            package=package.name,
            resulting_commit=resulting_commit,
            builder=builder.value,
            reviewer_required=required.value,
            reason=reason,
            base_commit=base_commit,
            effective_risk=effective_risk.value,
        )
        self.state.deferred_independent_audits = auditdebt.dump(debts)
        self._persist()
        self._beat(audit_debt=len(auditdebt.open_debts(debts)))
        return debt

    # -------------------------------------------------------------- dry run

    def plan(self, package: WorkPackage) -> StepOutcome:
        """Describe exactly what a real run would do, touching nothing."""

        outcome = StepOutcome(status=self.state.workflow_status)
        facts = read_repo(self.config.repo)
        codex_ok, codex_where = agents.agent_available(self.config.codex)
        claude_ok, claude_where = agents.agent_available(self.config.claude)
        risk, rationale = assess_risk(
            package.risk, facts.dirty_paths, self.config.high_risk_paths
        )
        would_audit, reason = self.audit_decision(package, risk)
        tests = package.required_tests or self.config.verification_commands

        outcome.say(f"work package     : {package.name}")
        outcome.say(f"objective        : {package.objective}")
        outcome.say(f"declared risk    : {package.risk.value}")
        outcome.say(f"effective risk   : {risk.value} ({rationale})")
        outcome.say(
            f"codex            : {'available' if codex_ok else 'UNAVAILABLE'}"
            f" - {codex_where}"
        )
        outcome.say(
            f"claude           : {'available' if claude_ok else 'UNAVAILABLE'}"
            f" - {claude_where}"
        )
        outcome.say(
            "codex command    : "
            f"{codex_where if codex_ok else '<codex>'} exec -s workspace-write "
            f"-C {self.config.repo} --output-last-message <report> < <work_order>"
        )
        outcome.say("tests that would run:")
        for command in tests:
            outcome.say(f"    {' '.join(command)}")
        outcome.say(f"claude would run : {'YES' if would_audit else 'no'} ({reason})")
        outcome.say(f"commit policy    : {package.commit_policy.value}")
        outcome.say("nothing was invoked and git was not touched (dry run)")
        return outcome

    # ---------------------------------------------------------------- stages

    def run_builder(
        self, package: WorkPackage
    ) -> tuple[StepOutcome, agents.AgentRun | None]:
        outcome = StepOutcome(status=WorkflowStatus.CODEX_RUNNING)
        if self.state.current_work_package != package.name:
            # New package: start its auditor budget fresh.
            self.state.claude_cost_usd_this_package = 0.0
            self.state.claude_cost_unknown_runs = 0
            self.state.provisional_review_cycles = 0
        self.state.current_work_package = package.name
        self.state.current_risk = package.risk.value
        self.state.transition(WorkflowStatus.PLANNING, f"planning {package.name}")
        self._persist()

        order = prompts.build_work_order(self.config, package)
        order_path = prompts.write_prompt(
            self.config.subdir("work_orders"), self._stamp(package, "order"), order
        )
        outcome.say(f"work order: {order_path}")

        self._complete_stage(Stage.PLANNED)

        # Try each permitted builder in turn. A builder that cannot run is a
        # capacity problem, not a verdict on the work, so it hands over instead
        # of escalating. A builder that runs and returns bad work still stops.
        attempted: list[str] = []
        run: agents.AgentRun | None = None
        # At most one attempt per permitted agent: a handover is a last resort,
        # not a retry loop, and the bound makes that impossible to get wrong.
        for _ in range(len(AgentIdentity)):
            try:
                assignment = self.assign_roles()
            except roles.NoBuilderAvailable as error:
                return self._escalate(outcome, str(error)), run
            builder = assignment.builder
            outcome.role_assignment = assignment
            if assignment.failed_over:
                outcome.say(f"builder failover: {assignment.reason}")
            outcome.say(
                f"builder={builder.value} reviewer="
                f"{assignment.reviewer.value if assignment.reviewer else 'DEFERRED'}"
            )
            attempted.append(builder.value)

            self.state.transition(
                WorkflowStatus.CODEX_RUNNING, f"invoking {builder.value} builder"
            )
            self._persist()
            self._beat(
                stage="building",
                builder=builder.value,
                reviewer=(
                    None if assignment.reviewer is None else assignment.reviewer.value
                ),
                current_command=f"{builder.value} build",
                workflow_status=self.state.workflow_status.value,
            )

            try:
                with HeartbeatTicker(
                    self.heartbeat,
                    stage="building",
                    current_command=f"{builder.value} build",
                ):
                    run = self._dispatch_builder(builder, package, order_path)
            except agents.AgentUnavailable as error:
                # Could not start at all: mark it out and let the loop retry the
                # counterpart. Completed work on disk is untouched.
                self._exhausted.add(builder)
                outcome.say(f"{builder.value} unavailable: {error}")
                if len(self._exhausted) >= len(AgentIdentity):
                    return (
                        self._escalate(
                            outcome,
                            f"no builder could be started (tried {attempted}): {error}",
                        ),
                        run,
                    )
                continue

            outcome.say(
                f"{builder.value} exit={run.exit_code} report={run.transcript_path}"
            )

            if roles.is_capacity_failure(run):
                reason = roles.classify_run_failure(run)
                self._exhausted.add(builder)
                outcome.say(
                    f"{builder.value} builder lost capacity ({reason.value}); "
                    "preserving completed work and looking for a failover builder"
                )
                if len(self._exhausted) >= len(AgentIdentity):
                    return (
                        self._escalate(
                            outcome,
                            f"every permitted builder is unavailable "
                            f"({reason.value}); tried {attempted}. Completed work "
                            "is preserved on disk and in the persisted state.",
                        ),
                        run,
                    )
                continue

            break
        else:
            return (
                self._escalate(
                    outcome,
                    f"every permitted builder was attempted without success "
                    f"(tried {attempted})",
                ),
                run,
            )

        if run is None:
            return (
                self._escalate(outcome, "no builder produced a result"),
                None,
            )
        if run.contract is None:
            return (
                self._escalate(
                    outcome,
                    f"{run.name} output contract unusable: {run.contract_error}. "
                    f"Raw report preserved at {run.transcript_path}.",
                ),
                run,
            )
        if run.contract.get("status") != "COMPLETE":
            return (
                self._escalate(
                    outcome,
                    f"{run.name} reported status={run.contract.get('status')!r}; "
                    "human decision required.",
                ),
                run,
            )
        self.state.transition(
            WorkflowStatus.CODEX_REVIEW, f"{run.name} returned COMPLETE"
        )
        if run.transcript_path is not None:
            self.state.builder_report_path = str(run.transcript_path)
            pending_report = run.transcript_path
        else:
            pending_report = None
        self.state.revisions = []
        self._record_revision(builder, "build")
        if pending_report is not None:
            self.state.builder_evidence = evidence_mod.record_builder_evidence(
                builder=run.name,
                package=package.name,
                workflow_id=self.state.workflow_id,
                report_path=pending_report,
                revision=len(self.state.revisions),
                kind="build",
            ).to_dict()
            self._persist()
        self._complete_stage(Stage.BUILT)
        return outcome, run

    def run_verification(
        self, package: WorkPackage, outcome: StepOutcome
    ) -> VerificationReport:
        self.state.transition(WorkflowStatus.LOCAL_VERIFY, "running local gates")
        self.state.verification_status = "running"
        self._persist()
        self._beat(
            stage="verifying",
            current_command="local gates",
            workflow_status=self.state.workflow_status.value,
        )
        commands = (
            tuple(package.required_tests) + tuple(package.required_quality_gates)
        ) or None

        def beat_between_gates(
            index: int, total: int, command: tuple[str, ...]
        ) -> None:
            self._beat(
                verification_gate=f"{index}/{total}: {' '.join(command[:3])}",
                current_command=" ".join(command),
            )

        with HeartbeatTicker(
            self.heartbeat, stage="verifying", current_command="local gates"
        ):
            report = verify(
                self.config,
                allowed_files=package.allowed_files,
                protected_files=package.protected_files,
                commands=commands,
                label=package.name,
                on_command=beat_between_gates,
            )
        outcome.verification = report
        outcome.say(f"local verification passed={report.passed}")
        if report.summary():
            outcome.say(report.summary())
        self.state.verification_status = "passed" if report.passed else "failed"
        if report.passed:
            # Bind this result to the exact tree it describes, so a later run
            # can prove the tree has not changed underneath it.
            self.state.tree_fingerprint = evidence_mod.tree_fingerprint(
                self.config, package, base_commit=self.state.base_commit
            )
            self._complete_stage(Stage.VERIFIED)
        else:
            # A failed verification leaves no reusable evidence behind.
            self.state.tree_fingerprint = None
            self._persist()
        self._beat(
            verification_gate="complete",
            science_firewall="SAFE" if report.protected_ok else "VIOLATION",
        )
        return report

    def reconstruct_verification(self, package: WorkPackage) -> VerificationReport:
        """Rebuild the report for a verification that already passed.

        This deliberately does not re-run the gates: they passed for this exact
        commit boundary, and resume exists so they are not paid for twice. The
        protected-artifact hashes *are* re-checked, because that is a safety
        check rather than a gate, and it is cheap.
        """

        facts = read_repo(self.config.repo)
        protected_ok, protected_detail = check_protected_artifacts(self.config)
        report = VerificationReport(
            passed=protected_ok,
            protected_ok=protected_ok,
            protected_detail=protected_detail,
            scope_ok=True,
            scope_detail="carried forward from the completed verification",
            changed_files=tuple(facts.dirty_paths),
        )
        self.state.verification_status = "passed" if protected_ok else "failed"
        self._persist()
        self._beat(
            verification_gate="carried forward",
            science_firewall="SAFE" if protected_ok else "VIOLATION",
        )
        return report

    def budget_check(self) -> tuple[bool, str]:
        """Decide whether another auditor cycle is affordable.

        Returns ``(allowed, explanation)``. Cost is never estimated: when the CLI
        does not report a figure the run is permitted and the cycle limits remain
        the binding safeguard, which the explanation states plainly.
        """

        ceiling = self.config.limits.max_claude_cost_usd_per_work_package
        per_run = self.config.limits.max_claude_cost_usd_per_run
        spent = self.state.claude_cost_usd_this_package
        unknown = self.state.claude_cost_unknown_runs
        # Reserve headroom for the run about to start. Combined with the native
        # per-run --max-budget-usd cap, this keeps the package ceiling from being
        # breached rather than merely detecting the breach afterwards.
        if spent + per_run > ceiling:
            return False, (
                f"Claude budget exhausted for this work package: ${spent:.4f} spent, "
                f"another run may cost up to ${per_run:.2f}, ceiling ${ceiling:.2f}"
            )
        note = f"${spent:.4f} of ${ceiling:.2f} spent"
        if unknown:
            note += (
                f"; {unknown} run(s) reported no cost, so spend is a lower bound "
                "and cycle limits govern those runs"
            )
        return True, note

    def _record_cost(self, run: agents.AgentRun, outcome: StepOutcome) -> None:
        if run.cost_usd is None:
            self.state.claude_cost_unknown_runs += 1
            outcome.say("auditor cost not reported; not estimated - cycle limits apply")
            return
        self.state.claude_cost_usd_this_package += run.cost_usd
        outcome.say(
            f"auditor cost ${run.cost_usd:.4f} "
            f"(package total ${self.state.claude_cost_usd_this_package:.4f} of "
            f"${self.config.limits.max_claude_cost_usd_per_work_package:.2f})"
        )

    def run_audit(
        self,
        package: WorkPackage,
        outcome: StepOutcome,
        *,
        codex_report: str,
        verification: VerificationReport,
        base_commit: str | None,
        previous_findings: list[dict[str, Any]] | None = None,
        targeted: bool = False,
    ) -> agents.AgentRun | None:
        outcome.review_unavailable_reason = None
        affordable, note = self.budget_check()
        outcome.say(f"auditor budget: {note}")
        if not affordable:
            self._escalate(outcome, note)
            return None
        reviewer_name = roles.COUNTERPART[self._current_builder()].value
        self.state.transition(
            WorkflowStatus.CLAUDE_RUNNING, f"invoking {reviewer_name} auditor"
        )
        self._persist()
        self._beat(stage="auditing", current_command=f"{reviewer_name} audit")
        prompt = prompts.build_audit_prompt(
            self.config,
            package,
            codex_report=codex_report,
            verification=verification,
            base_commit=base_commit,
            previous_findings=previous_findings,
            targeted=targeted,
        )
        prompt_path = prompts.write_prompt(
            self.config.subdir("claude_audits"),
            self._stamp(package, "audit-prompt"),
            prompt,
        )
        outcome.say(f"audit prompt: {prompt_path}")
        reviewer = roles.COUNTERPART[self._current_builder()]
        try:
            with HeartbeatTicker(
                self.heartbeat,
                stage="auditing",
                current_command=f"{reviewer.value} audit",
            ):
                if reviewer is AgentIdentity.CLAUDE:
                    run = self._run_claude(
                        self.config, prompt_path, stem=self._stamp(package, "audit")
                    )
                else:
                    run = self._run_codex_auditor(
                        self.config, prompt_path, stem=self._stamp(package, "audit")
                    )
        except agents.AgentUnavailable as error:
            outcome.review_unavailable_reason = str(error)
            outcome.say(str(error))
            return None
        outcome.say(
            f"{reviewer.value} exit={run.exit_code} audit={run.transcript_path}"
        )
        # Spend is recorded before the contract is judged: a malformed or failed
        # audit still cost money and must count against the package ceiling.
        self._record_cost(run, outcome)
        self._persist()
        if run.contract is None:
            unavailable, reason = agents.claude_temporarily_unavailable(run)
            if unavailable:
                outcome.review_unavailable_reason = reason
                outcome.say(reason)
                return None
            self._escalate(
                outcome,
                f"Claude audit contract unusable: {run.contract_error}. "
                f"Raw audit preserved at {run.transcript_path}. "
                "Approval is NOT inferred.",
            )
            return None
        outcome.audit_contract = run.contract
        return run

    def run_provisional_review(
        self,
        package: WorkPackage,
        outcome: StepOutcome,
        *,
        verification: VerificationReport,
        base_commit: str | None,
        previous_findings: list[dict[str, Any]] | None = None,
        targeted: bool = False,
    ) -> agents.AgentRun | None:
        """Run a fresh read-only Codex review and label it non-independent."""

        self.state.transition(
            WorkflowStatus.PROVISIONAL_CODEX_REVIEW,
            "invoking fresh Codex provisional reviewer",
        )
        self._persist()
        prompt = prompts.build_provisional_review_prompt(
            self.config,
            package,
            verification=verification,
            base_commit=base_commit,
            previous_findings=previous_findings,
            targeted=targeted,
        )
        prompt_path = prompts.write_prompt(
            self.config.subdir("provisional_reviews"),
            self._stamp(package, "provisional-review-prompt"),
            prompt,
        )
        outcome.say(f"provisional review prompt: {prompt_path}")
        try:
            run = self._run_provisional(
                self.config,
                prompt_path,
                stem=self._stamp(package, "provisional-review"),
            )
        except agents.AgentUnavailable as error:
            self._escalate(outcome, str(error))
            return None
        outcome.say(
            f"provisional Codex review exit={run.exit_code} "
            f"report={run.transcript_path}"
        )
        if run.contract is None:
            self._escalate(
                outcome,
                f"Provisional Codex review contract unusable: "
                f"{run.contract_error}. Approval is NOT inferred.",
            )
            return None
        outcome.provisional_review_contract = run.contract
        return run

    # ------------------------------------------------------------ commitment

    def maybe_commit(
        self,
        package: WorkPackage,
        outcome: StepOutcome,
        report: VerificationReport,
        *,
        audited: bool,
        provisional: bool = False,
    ) -> None:
        """Commit only when every precondition is independently satisfied."""

        policy = package.commit_policy
        if policy is CommitPolicy.MANUAL:
            outcome.say("commit policy MANUAL — leaving changes uncommitted")
            return
        if policy is CommitPolicy.AFTER_AUDIT and not audited and not provisional:
            outcome.say(
                "commit policy AFTER_AUDIT — audit not yet approved; not committing"
            )
            return
        if not report.passed:
            outcome.say("verification failed — not committing")
            return
        if self.state.blocking_findings:
            outcome.say("blocking findings outstanding — not committing")
            return
        if not report.protected_ok:
            outcome.say("protected artifact changed — not committing")
            return
        paths = list(report.changed_files)
        if not paths:
            outcome.say("nothing to commit")
            return
        outcome.say(f"planned staged files: {paths}")
        provenance = ""
        if audited:
            provenance = (
                "\nIndependent audit: APPROVED."
                "\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>\n"
            )
        elif provisional:
            provenance = (
                "\nReview: PROVISIONAL_CODEX_REVIEW; independent audit pending.\n"
            )
        message = (
            f"{package.objective.strip().splitlines()[0][:68]}\n\n"
            f"Work package: {package.name} (risk {package.risk.value}).\n"
            f"Local verification passed; protected artifacts unchanged." + provenance
        )
        commit = commit_paths(self.config.repo, paths, message)
        outcome.commit = commit
        outcome.say(f"committed {commit[:7]}")
        package.status = PackageStatus.COMMITTED
        self.state.resulting_commit = commit
        self._complete_stage(Stage.COMMITTED)

    def _handle_provisional_verdict(
        self,
        package: WorkPackage,
        package_path: Path,
        outcome: StepOutcome,
        report: VerificationReport,
        review: agents.AgentRun,
        base_commit: str,
        builder: agents.AgentRun,
    ) -> StepOutcome:
        contract = review.contract or {}
        blocking = agents.blocking_findings(contract)
        verdict = contract.get("verdict")
        outcome.say(
            f"provisional verdict: {verdict} ({len(blocking)} blocking findings)"
        )
        if verdict == "APPROVED" and not blocking:
            self.state.blocking_findings = []
            self.state.work_packages_since_audit += 1
            self.maybe_commit(package, outcome, report, audited=False, provisional=True)
            if outcome.commit is None:
                return self._escalate(
                    outcome,
                    "provisional review approved but no package commit was produced",
                )
            debt = {
                "status": "PENDING_INDEPENDENT_AUDIT",
                "package": package.name,
                "base_commit": base_commit,
                "resulting_commit": outcome.commit,
                "effective_risk": package.risk.value,
                "verification_report": report.report_path,
                "provisional_review_report": (
                    str(review.transcript_path.relative_to(self.config.repo))
                    if review.transcript_path is not None
                    else None
                ),
                "reason": (
                    "Claude unavailable; approved only by fresh read-only Codex "
                    "provisional review."
                ),
            }
            self.state.deferred_independent_audits.append(debt)
            self.state.audit_required = True
            self.state.audit_reason = "deferred independent-audit debt exists"
            package.notes = (
                package.notes.rstrip()
                + f"\nPENDING_INDEPENDENT_AUDIT at {outcome.commit}."
            ).strip()
            save_package(package_path, package)
            self.state.transition(
                WorkflowStatus.IDLE,
                "package committed with PENDING_INDEPENDENT_AUDIT",
            )
            self._persist()
            outcome.status = WorkflowStatus.IDLE
            return outcome

        self.state.blocking_findings = blocking
        return self._correction_loop(
            package,
            package_path,
            outcome,
            base_commit,
            builder,
            reason=f"provisional review verdict {verdict}",
            findings=blocking
            or [
                {
                    "id": "PROVISIONAL_VERDICT",
                    "severity": "C",
                    "blocks": True,
                    "summary": f"provisional reviewer returned {verdict}",
                }
            ],
        )

    # ------------------------------------------------------------- main loop

    def execute(
        self,
        package: WorkPackage,
        package_path: Path,
        *,
        resume_plan: Any | None = None,
        resume_from: Stage | None = None,
        builder_report: str = "",
    ) -> StepOutcome:
        """Full builder → verify → audit → correction loop for one package.

        ``resume_from`` names the last stage a previous run completed. Stages at
        or before it are skipped; everything after it runs normally. A fresh run
        passes nothing and starts from the beginning.
        """

        # The plan is the authority. Deriving skipping from a stage marker alone
        # loses the planner's decisions - most importantly that a verification
        # whose evidence no longer matches the tree MUST run again.
        if resume_plan is not None:
            resume_from = resume_plan.completed
            builder_report = builder_report or resume_plan.builder_report
        resuming = resume_from is not None
        if resuming:
            # Trust the boundary the previous run recorded rather than today's
            # HEAD: resume.validate has already confirmed they agree.
            base_commit = self.state.base_commit or read_repo(self.config.repo).head
        else:
            base_commit = read_repo(self.config.repo).head
            self.state.base_commit = base_commit
            self.state.resulting_commit = None
            self.state.verification_status = None
            self.state.last_completed_stage = Stage.NOT_STARTED.value
            self.state.builder_report_path = None
            self._persist()

        # Only a plan may authorise skipping. `resume_from` on its own once
        # inferred its own skips, which is how a verification the planner had
        # required could still be skipped; it now names the stage for logging
        # and nothing else.
        if resume_plan is not None:
            skip_build = resume_plan.skips(Stage.BUILT)
            skip_verification = resume_plan.skips(Stage.VERIFIED)
            skip_audit = resume_plan.skips(Stage.AUDITED)
        else:
            skip_build = skip_verification = skip_audit = False

        if skip_build:
            # The builder process is gone; its report is not. Downstream stages
            # only ever read raw_report, so a transcript-backed stand-in carries
            # everything they need without pretending a new run happened.
            outcome = StepOutcome(status=WorkflowStatus.CODEX_REVIEW)
            outcome.say(
                f"skipping build: already completed by "
                f"{self.state.builder or 'a previous run'}"
            )
            try:
                validated = evidence_mod.load_builder_evidence(
                    evidence_mod.BuilderEvidence.from_dict(self.state.builder_evidence),
                    package=package.name,
                    expected_builder=self.state.builder,
                    expected_workflow_id=self.state.workflow_id,
                    expected_revision=len(self.state.revisions) or None,
                )
            except evidence_mod.EvidenceRefused as error:
                # There is no safe fallback here. Unvalidated report text is
                # exactly the thing that must not be trusted across a process
                # boundary, so a refusal stops the run.
                return self._escalate(
                    outcome, f"cannot reuse the builder's work: {error}"
                )
            builder = agents.AgentRun(
                name=self.state.builder or "previous-builder",
                command=[],
                exit_code=0,
                stdout="",
                stderr="",
                raw_report=validated,
                extra={"persisted_evidence": True, "resumed": True},
            )
        else:
            outcome, builder = self.run_builder(package)
            if (
                outcome.status is WorkflowStatus.HUMAN_ACTION_REQUIRED
                or builder is None
            ):
                return outcome

        if skip_verification:
            outcome.say("skipping verification: already passed for this boundary")
            report = self.reconstruct_verification(package)
        else:
            report = self.run_verification(package, outcome)
        outcome.verification = report
        effective_risk, rationale = assess_risk(
            package.risk, report.changed_files, self.config.high_risk_paths
        )
        outcome.say(f"effective risk: {effective_risk.value} ({rationale})")

        needs_audit, reason = self.audit_decision(package, effective_risk)
        outcome.say(f"audit required: {'YES' if needs_audit else 'no'} ({reason})")

        if not report.passed:
            return self._correction_loop(
                package,
                package_path,
                outcome,
                base_commit,
                builder,
                reason="local verification failed",
                findings=[
                    {
                        "id": "VERIFY",
                        "severity": "B",
                        "blocks": True,
                        "summary": report.summary() or "local verification failed",
                    }
                ],
            )

        if not needs_audit:
            self.state.work_packages_since_audit += 1
            self.maybe_commit(package, outcome, report, audited=False)
            if outcome.commit is None:
                package.status = PackageStatus.VERIFIED
            save_package(package_path, package)
            self.state.transition(WorkflowStatus.IDLE, "package complete without audit")
            self._persist()
            outcome.status = WorkflowStatus.IDLE
            return outcome

        if skip_audit:
            # The independent review already happened and approved this exact
            # boundary. Re-running it would spend a second review and risk a
            # second recorded approval for one piece of work.
            outcome.say(
                "skipping audit: an independent review already approved this boundary"
            )
            self.maybe_commit(package, outcome, report, audited=True)
            save_package(package_path, package)
            self.state.transition(
                WorkflowStatus.IDLE, "package complete on resume after audit"
            )
            self._persist()
            outcome.status = WorkflowStatus.IDLE
            return outcome

        self.state.audit_required = True
        self.state.audit_reason = reason
        mode, mode_reason = self.review_mode(
            package, effective_risk, report, needs_audit=True
        )
        outcome.say(f"review mode: {mode} ({mode_reason})")
        if mode == "deferred":
            # The required independent reviewer cannot run and the provisional
            # fallback is refused. Record what is owed so the persisted state
            # tells the truth, then stop: recording a debt is bookkeeping, not
            # permission to commit unreviewed work. The refusal reasons here are
            # the hard ones - HIGH risk, changed scientific source or tests, or
            # failing gates - and none of them may proceed unattended.
            debt = self.record_audit_debt(
                package,
                resulting_commit=read_repo(self.config.repo).head,
                base_commit=base_commit,
                effective_risk=effective_risk,
                reason=mode_reason,
            )
            outcome.say(
                f"DEFERRED_INDEPENDENT_AUDIT recorded as {debt.id}: "
                f"built by {debt.builder}, awaiting {debt.reviewer_required}"
            )
            return self._escalate(outcome, mode_reason)
        if mode == "provisional":
            review = self.run_provisional_review(
                package,
                outcome,
                verification=report,
                base_commit=base_commit,
            )
            if review is None:
                return outcome
            return self._handle_provisional_verdict(
                package,
                package_path,
                outcome,
                report,
                review,
                base_commit,
                builder,
            )
        audit = self.run_audit(
            package,
            outcome,
            codex_report=builder.raw_report,
            verification=report,
            base_commit=base_commit,
        )
        if audit is None:
            if outcome.review_unavailable_reason:
                eligible, fallback_reason = self.provisional_review_eligibility(
                    package, effective_risk, report
                )
                if not eligible:
                    return self._escalate(
                        outcome,
                        f"{outcome.review_unavailable_reason}; provisional fallback "
                        f"refused: {fallback_reason}",
                    )
                outcome.say(
                    f"falling back to PROVISIONAL_CODEX_REVIEW: {fallback_reason}"
                )
                review = self.run_provisional_review(
                    package,
                    outcome,
                    verification=report,
                    base_commit=base_commit,
                )
                if review is None:
                    return outcome
                return self._handle_provisional_verdict(
                    package,
                    package_path,
                    outcome,
                    report,
                    review,
                    base_commit,
                    builder,
                )
            return outcome
        return self._handle_verdict(
            package, package_path, outcome, report, audit, base_commit, builder
        )

    def _handle_verdict(
        self,
        package: WorkPackage,
        package_path: Path,
        outcome: StepOutcome,
        report: VerificationReport,
        audit: agents.AgentRun,
        base_commit: str,
        builder: agents.AgentRun,
    ) -> StepOutcome:
        contract = audit.contract or {}
        verdict = contract.get("verdict")
        blocking = agents.blocking_findings(contract)
        self.state.safe_defer_findings = [
            f for f in contract.get("findings", []) if not f.get("blocks")
        ] + list(contract.get("safe_defer", []))

        outcome.say(f"verdict: {verdict} ({len(blocking)} blocking findings)")

        if verdict == "APPROVED" and not blocking:
            self.state.blocking_findings = []
            self.state.audit_required = False
            self.state.audit_reason = None
            self.state.work_packages_since_audit = 0
            self.state.codex_correction_cycles = 0
            self.state.claude_reaudit_cycles = 0
            self.state.claude_cost_usd_this_package = 0.0
            self.state.claude_cost_unknown_runs = 0
            self.state.provisional_review_cycles = 0
            # Mark the audit done *before* committing, so an interruption
            # between the two resumes at commit rather than re-auditing.
            self._complete_stage(Stage.AUDITED)
            self.settle_audit_debt(package, audit, outcome)
            self.maybe_commit(package, outcome, report, audited=True)
            self.state.last_independent_audit_commit = (
                outcome.commit or read_repo(self.config.repo).head
            )
            package.status = (
                PackageStatus.AUDITED if not outcome.commit else PackageStatus.COMMITTED
            )
            save_package(package_path, package)
            self.state.transition(WorkflowStatus.APPROVED, "independent audit approved")
            self._persist()
            outcome.status = WorkflowStatus.APPROVED
            return outcome

        self.state.blocking_findings = blocking
        return self._correction_loop(
            package,
            package_path,
            outcome,
            base_commit,
            builder,
            reason=f"audit verdict {verdict}",
            findings=blocking
            or [
                {
                    "id": "VERDICT",
                    "severity": "C",
                    "blocks": True,
                    "summary": f"auditor returned {verdict}",
                }
            ],
        )

    def _correction_loop(
        self,
        package: WorkPackage,
        package_path: Path,
        outcome: StepOutcome,
        base_commit: str,
        builder: agents.AgentRun,
        *,
        reason: str,
        findings: list[dict[str, Any]],
    ) -> StepOutcome:
        """Codex correction → verify → policy-selected re-review, bounded."""

        limits = self.config.limits
        self.state.transition(WorkflowStatus.CORRECTION_REQUIRED, reason)
        self._persist()

        current = findings
        while True:
            if self.state.codex_correction_cycles >= limits.max_codex_correction_cycles:
                return self._escalate(
                    outcome,
                    "max_codex_correction_cycles "
                    f"({limits.max_codex_correction_cycles}) "
                    "exhausted; all reports preserved.",
                )
            self.state.codex_correction_cycles += 1
            self.state.transition(
                WorkflowStatus.CODEX_CORRECTION,
                f"correction cycle {self.state.codex_correction_cycles}",
            )
            self._persist()

            detail = "\n".join(
                f"- **{f.get('id')}** (severity {f.get('severity')}): "
                f"{f.get('summary')}"
                for f in current
            )
            order = prompts.build_work_order(
                self.config,
                package,
                correction=(
                    "Close the following review or verification findings. Change "
                    "nothing else, and do not weaken any test or tolerance to make a "
                    f"finding disappear.\n\n{detail}"
                ),
            )
            path = prompts.write_prompt(
                self.config.subdir("correction_orders"),
                self._stamp(
                    package, f"correction-{self.state.codex_correction_cycles}"
                ),
                order,
            )
            outcome.say(f"correction order: {path}")

            try:
                corrector = self.assign_roles().builder
            except roles.NoBuilderAvailable as error:
                return self._escalate(outcome, str(error))
            outcome.say(f"correction author: {corrector.value}")
            try:
                with HeartbeatTicker(
                    self.heartbeat,
                    stage="correcting",
                    current_command=f"{corrector.value} correction",
                ):
                    fix = self._dispatch_builder(corrector, package, path)
            except agents.AgentUnavailable as error:
                return self._escalate(outcome, str(error))
            if fix.contract is None:
                return self._escalate(
                    outcome,
                    f"{corrector.value} correction contract unusable: "
                    f"{fix.contract_error}",
                )
            # The diff under review is now this agent's work, so the reviewer
            # selected below must be the other one.
            self._record_revision(corrector, "correction")
            if fix.transcript_path is not None:
                self.state.builder_report_path = str(fix.transcript_path)
                self.state.builder_evidence = evidence_mod.record_builder_evidence(
                    builder=corrector.value,
                    package=package.name,
                    workflow_id=self.state.workflow_id,
                    report_path=fix.transcript_path,
                    revision=len(self.state.revisions),
                    kind="correction",
                ).to_dict()
                self._persist()

            report = self.run_verification(package, outcome)
            if not report.passed:
                outcome.say("correction still fails local verification; retrying")
                continue

            effective_risk, rationale = assess_risk(
                package.risk, report.changed_files, self.config.high_risk_paths
            )
            outcome.say(
                f"effective risk after correction: {effective_risk.value} ({rationale})"
            )
            needs_audit, audit_reason = self.audit_decision(package, effective_risk)
            mode, mode_reason = self.review_mode(
                package, effective_risk, report, needs_audit=needs_audit
            )
            outcome.say(f"review mode after correction: {mode} ({mode_reason})")
            if mode == "deferred":
                # review_mode returns "deferred" in v2; the old "blocked" name
                # never matched, which let an unreviewable correction fall
                # through to the auditor path.
                debt = self.record_audit_debt(
                    package,
                    resulting_commit=read_repo(self.config.repo).head,
                    base_commit=base_commit,
                    effective_risk=effective_risk,
                    reason=mode_reason,
                )
                outcome.say(f"DEFERRED_INDEPENDENT_AUDIT recorded as {debt.id}")
                return self._escalate(outcome, mode_reason)
            if mode == "none":
                self.state.work_packages_since_audit += 1
                self.state.blocking_findings = []
                self.maybe_commit(package, outcome, report, audited=False)
                if outcome.commit is None:
                    return self._escalate(
                        outcome,
                        "verification passed but no package commit was produced",
                    )
                save_package(package_path, package)
                self.state.transition(
                    WorkflowStatus.IDLE, "corrected package complete without audit"
                )
                self._persist()
                outcome.status = WorkflowStatus.IDLE
                return outcome
            self.state.audit_required = True
            self.state.audit_reason = audit_reason
            if mode == "provisional":
                if (
                    self.state.provisional_review_cycles
                    >= limits.max_claude_reaudit_cycles
                ):
                    return self._escalate(
                        outcome,
                        "provisional review cycle limit "
                        f"({limits.max_claude_reaudit_cycles}) exhausted",
                    )
                self.state.provisional_review_cycles += 1
                review = self.run_provisional_review(
                    package,
                    outcome,
                    verification=report,
                    base_commit=base_commit,
                    previous_findings=current,
                    targeted=True,
                )
                if review is None:
                    return outcome
                contract = review.contract or {}
                blocking = agents.blocking_findings(contract)
                if contract.get("verdict") == "APPROVED" and not blocking:
                    return self._handle_provisional_verdict(
                        package,
                        package_path,
                        outcome,
                        report,
                        review,
                        base_commit,
                        fix,
                    )
                current = blocking or current
                self.state.blocking_findings = current
                self._persist()
                continue

            if self.state.claude_reaudit_cycles >= limits.max_claude_reaudit_cycles:
                return self._escalate(
                    outcome,
                    f"max_claude_reaudit_cycles ({limits.max_claude_reaudit_cycles}) "
                    "exhausted; all reports preserved.",
                )
            self.state.claude_reaudit_cycles += 1
            self.state.transition(
                WorkflowStatus.REAUDIT_PENDING,
                f"targeted re-audit {self.state.claude_reaudit_cycles}",
            )
            self._persist()

            audit = self.run_audit(
                package,
                outcome,
                codex_report=fix.raw_report,
                verification=report,
                base_commit=base_commit,
                previous_findings=current,
                targeted=True,
            )
            if audit is None:
                if outcome.review_unavailable_reason:
                    eligible, fallback_reason = self.provisional_review_eligibility(
                        package, effective_risk, report
                    )
                    if not eligible:
                        return self._escalate(
                            outcome,
                            f"{outcome.review_unavailable_reason}; provisional "
                            f"fallback refused: {fallback_reason}",
                        )
                    review = self.run_provisional_review(
                        package,
                        outcome,
                        verification=report,
                        base_commit=base_commit,
                        previous_findings=current,
                        targeted=True,
                    )
                    if review is None:
                        return outcome
                    contract = review.contract or {}
                    blocking = agents.blocking_findings(contract)
                    if contract.get("verdict") == "APPROVED" and not blocking:
                        return self._handle_provisional_verdict(
                            package,
                            package_path,
                            outcome,
                            report,
                            review,
                            base_commit,
                            fix,
                        )
                    current = blocking or current
                    self.state.blocking_findings = current
                    self._persist()
                    continue
                return outcome

            contract = audit.contract or {}
            blocking = agents.blocking_findings(contract)
            outcome.say(
                f"re-audit verdict: {contract.get('verdict')} "
                f"({len(blocking)} blocking)"
            )
            if contract.get("verdict") == "APPROVED" and not blocking:
                return self._handle_verdict(
                    package, package_path, outcome, report, audit, base_commit, fix
                )
            current = blocking or current
            self.state.blocking_findings = current
            self._persist()
