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

from . import agents, prompts
from .config import OrchestratorConfig
from .gitops import commit_paths, read_repo
from .state import WorkflowState, WorkflowStatus, save_state
from .verify import VerificationReport, verify
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
    commit: str | None = None
    human_action: str | None = None

    def say(self, text: str) -> None:
        self.messages.append(text)


CodexRunner = Callable[..., agents.AgentRun]
ClaudeRunner = Callable[..., agents.AgentRun]


class Engine:
    """Drives one work package from plan to commit or escalation."""

    def __init__(
        self,
        config: OrchestratorConfig,
        state: WorkflowState,
        *,
        codex_runner: CodexRunner | None = None,
        claude_runner: ClaudeRunner | None = None,
    ) -> None:
        self.config = config
        self.state = state
        # Injectable so tests never spend a real agent call.
        self._run_codex = codex_runner or agents.run_codex
        self._run_claude = claude_runner or agents.run_claude_audit

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
        self.state.current_work_package = package.name
        self.state.current_risk = package.risk.value
        self.state.transition(WorkflowStatus.PLANNING, f"planning {package.name}")
        self._persist()

        order = prompts.build_work_order(self.config, package)
        order_path = prompts.write_prompt(
            self.config.subdir("work_orders"), self._stamp(package, "order"), order
        )
        outcome.say(f"work order: {order_path}")

        self.state.transition(WorkflowStatus.CODEX_RUNNING, "invoking Codex builder")
        self._persist()
        try:
            run = self._run_codex(
                self.config, order_path, stem=self._stamp(package, "report")
            )
        except agents.AgentUnavailable as error:
            return self._escalate(outcome, str(error)), None

        outcome.say(f"codex exit={run.exit_code} report={run.transcript_path}")
        if run.contract is None:
            return (
                self._escalate(
                    outcome,
                    f"Codex output contract unusable: {run.contract_error}. "
                    f"Raw report preserved at {run.transcript_path}.",
                ),
                run,
            )
        if run.contract.get("status") != "COMPLETE":
            return (
                self._escalate(
                    outcome,
                    f"Codex reported status={run.contract.get('status')!r}; "
                    "human decision required.",
                ),
                run,
            )
        self.state.transition(WorkflowStatus.CODEX_REVIEW, "Codex returned COMPLETE")
        self._persist()
        return outcome, run

    def run_verification(
        self, package: WorkPackage, outcome: StepOutcome
    ) -> VerificationReport:
        self.state.transition(WorkflowStatus.LOCAL_VERIFY, "running local gates")
        self._persist()
        commands = (
            tuple(package.required_tests) + tuple(package.required_quality_gates)
        ) or None
        report = verify(
            self.config,
            allowed_files=package.allowed_files,
            protected_files=package.protected_files,
            commands=commands,
            label=package.name,
        )
        outcome.verification = report
        outcome.say(f"local verification passed={report.passed}")
        if report.summary():
            outcome.say(report.summary())
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
        affordable, note = self.budget_check()
        outcome.say(f"auditor budget: {note}")
        if not affordable:
            self._escalate(outcome, note)
            return None
        self.state.transition(WorkflowStatus.CLAUDE_RUNNING, "invoking Claude auditor")
        self._persist()
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
        try:
            run = self._run_claude(
                self.config, prompt_path, stem=self._stamp(package, "audit")
            )
        except agents.AgentUnavailable as error:
            self._escalate(outcome, str(error))
            return None
        outcome.say(f"claude exit={run.exit_code} audit={run.transcript_path}")
        # Spend is recorded before the contract is judged: a malformed or failed
        # audit still cost money and must count against the package ceiling.
        self._record_cost(run, outcome)
        self._persist()
        if run.contract is None:
            self._escalate(
                outcome,
                f"Claude audit contract unusable: {run.contract_error}. "
                f"Raw audit preserved at {run.transcript_path}. "
                "Approval is NOT inferred.",
            )
            return None
        outcome.audit_contract = run.contract
        return run

    # ------------------------------------------------------------ commitment

    def maybe_commit(
        self,
        package: WorkPackage,
        outcome: StepOutcome,
        report: VerificationReport,
        *,
        audited: bool,
    ) -> None:
        """Commit only when every precondition is independently satisfied."""

        policy = package.commit_policy
        if policy is CommitPolicy.MANUAL:
            outcome.say("commit policy MANUAL — leaving changes uncommitted")
            return
        if policy is CommitPolicy.AFTER_AUDIT and not audited:
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
        message = (
            f"{package.objective.strip().splitlines()[0][:68]}\n\n"
            f"Work package: {package.name} (risk {package.risk.value}).\n"
            f"Local verification passed; protected artifacts unchanged."
            + ("\nIndependent audit: APPROVED." if audited else "")
            + "\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>\n"
        )
        commit = commit_paths(self.config.repo, paths, message)
        outcome.commit = commit
        outcome.say(f"committed {commit[:7]}")
        package.status = PackageStatus.COMMITTED
        self.state.last_scientific_commit = commit

    # ------------------------------------------------------------- main loop

    def execute(self, package: WorkPackage, package_path: Path) -> StepOutcome:
        """Full builder → verify → audit → correction loop for one package."""

        base_commit = read_repo(self.config.repo).head
        outcome, builder = self.run_builder(package)
        if outcome.status is WorkflowStatus.HUMAN_ACTION_REQUIRED or builder is None:
            return outcome

        report = self.run_verification(package, outcome)
        facts = read_repo(self.config.repo)
        effective_risk, rationale = assess_risk(
            package.risk, facts.dirty_paths, self.config.high_risk_paths
        )
        outcome.say(f"effective risk: {effective_risk.value} ({rationale})")

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

        needs_audit, reason = self.audit_decision(package, effective_risk)
        outcome.say(f"audit required: {'YES' if needs_audit else 'no'} ({reason})")

        if not needs_audit:
            self.state.work_packages_since_audit += 1
            self.maybe_commit(package, outcome, report, audited=False)
            package.status = package.status or PackageStatus.VERIFIED
            save_package(package_path, package)
            self.state.transition(WorkflowStatus.IDLE, "package complete without audit")
            self._persist()
            outcome.status = WorkflowStatus.IDLE
            return outcome

        self.state.audit_required = True
        self.state.audit_reason = reason
        audit = self.run_audit(
            package,
            outcome,
            codex_report=builder.raw_report,
            verification=report,
            base_commit=base_commit,
        )
        if audit is None:
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
            self.state.last_independent_audit_commit = base_commit
            self.state.codex_correction_cycles = 0
            self.state.claude_reaudit_cycles = 0
            self.state.claude_cost_usd_this_package = 0.0
            self.state.claude_cost_unknown_runs = 0
            self.maybe_commit(package, outcome, report, audited=True)
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
        """Codex correction → verify → targeted Claude re-audit, bounded."""

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
                    "Close the following findings from the independent audit. Change "
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
                fix = self._run_codex(
                    self.config,
                    path,
                    stem=self._stamp(
                        package,
                        f"correction-report-{self.state.codex_correction_cycles}",
                    ),
                )
            except agents.AgentUnavailable as error:
                return self._escalate(outcome, str(error))
            if fix.contract is None:
                return self._escalate(
                    outcome, f"Codex correction contract unusable: {fix.contract_error}"
                )

            report = self.run_verification(package, outcome)
            if not report.passed:
                outcome.say("correction still fails local verification; retrying")
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
