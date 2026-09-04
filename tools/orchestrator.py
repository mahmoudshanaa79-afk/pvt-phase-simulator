#!/usr/bin/env python
"""Local orchestrator CLI: Codex builds, Claude audits, local gates decide.

python tools/orchestrator.py status
python tools/orchestrator.py run [--package NAME] [--dry-run]
python tools/orchestrator.py verify
python tools/orchestrator.py audit [--package NAME]
python tools/orchestrator.py resume
python tools/orchestrator.py autopilot
python tools/orchestrator.py release-audit
python tools/orchestrator.py stop
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

from orchestration import agents, auditdebt, resume, roles  # noqa: E402
from orchestration import heartbeat as hb  # noqa: E402
from orchestration.config import ConfigError, load_config  # noqa: E402
from orchestration.engine import Engine  # noqa: E402
from orchestration.gitops import read_repo  # noqa: E402
from orchestration.lock import LockHeld, OrchestratorLock  # noqa: E402
from orchestration.state import (  # noqa: E402
    INTERRUPTIBLE_STATES,
    WorkflowStatus,
    load_state,
    save_state,
)
from orchestration.verify import verify  # noqa: E402
from orchestration.workpackage import (  # noqa: E402
    AuditPolicy,
    CommitPolicy,
    PackageStatus,
    Risk,
    WorkPackage,
    assess_risk,
    list_packages,
    load_package,
    next_package,
    save_package,
)


def _resolve_package(config, name: str | None):
    directory = config.ai_dir / "work_packages"
    if name:
        path = directory / f"{name}.json"
        if not path.exists():
            raise SystemExit(f"work package not found: {path}")
        return load_package(path), path
    package = next_package(directory)
    if package is None:
        return None, None
    return package, directory / f"{package.name}.json"


# --------------------------------------------------------------------- status


def cmd_status(config, args) -> int:
    state = load_state(config.state_path)
    facts = read_repo(config.repo)
    codex_ok, codex_where = agents.agent_available(config.codex)
    claude_ok, claude_where = agents.agent_available(config.claude)
    package, _ = _resolve_package(config, None)
    lock = OrchestratorLock(config.lock_path)
    held, lock_detail = lock.inspect()

    effective = None
    if package is not None:
        effective, rationale = assess_risk(
            package.risk, facts.dirty_paths, config.high_risk_paths
        )

    print(f"Project                : {state.project}")
    print(f"HEAD                   : {facts.short_head}  ({facts.head})")
    print(f"Branch                 : {facts.branch}")
    print(f"Working tree           : {'clean' if facts.is_clean else 'DIRTY'}")
    if not facts.is_clean:
        for path in facts.dirty_paths[:10]:
            print(f"                         {path}")
    print(f"Workflow status        : {state.workflow_status.value}")
    print(f"Phase                  : {state.phase}")
    print(f"Planned scope          : {state.planned_scope or '(none declared)'}")
    print(f"Planned scope complete : {state.planned_scope_complete}")
    print(f"Last completed package : {state.current_work_package or '(none)'}")
    print(f"Last audit commit      : {state.last_independent_audit_commit or '(none)'}")
    print(
        f"Packages since audit   : {state.work_packages_since_audit}"
        f" / {config.limits.audit_batch_size}"
    )
    print(f"Audit required         : {'YES' if state.audit_required else 'NO'}")
    print(f"Audit reason           : {state.audit_reason or '-'}")
    print(f"Blocking findings      : {len(state.blocking_findings)}")
    for finding in state.blocking_findings[:5]:
        print(f"                         {finding.get('id')}: {finding.get('summary')}")
    print(f"Safe-defer findings    : {len(state.safe_defer_findings)}")
    debts = auditdebt.load(state.deferred_independent_audits)
    outstanding = auditdebt.open_debts(debts)
    print(f"Deferred audit debt    : {len(outstanding)} open / {len(debts)} recorded")
    for debt in outstanding[:5]:
        print(
            f"                         {debt.id}: built by {debt.builder}, "
            f"awaiting {debt.reviewer_required}"
        )
    print(
        f"Auditor spend          : ${state.claude_cost_usd_this_package:.4f}"
        f" / ${config.limits.max_claude_cost_usd_per_work_package:.2f} per package"
        f" (${config.limits.max_claude_cost_usd_per_run:.2f} per run)"
    )
    if state.claude_cost_unknown_runs:
        print(
            f"                         {state.claude_cost_unknown_runs} run(s) "
            "reported no cost; cycle limits govern those"
        )
    print(
        f"Codex                  : {'available' if codex_ok else 'UNAVAILABLE'}"
        f" - {codex_where}"
    )
    print(
        f"Claude                 : {'available' if claude_ok else 'UNAVAILABLE'}"
        f" - {claude_where}"
    )
    print(f"Lock                   : {lock_detail}")

    if state.workflow_status is WorkflowStatus.READY_FOR_CLAUDE_RELEASE_AUDIT:
        next_action = "`release-audit` when Claude is available"
    elif package is None:
        next_action = "define a work package in .ai/work_packages/ then `run`"
    elif held:
        next_action = "another orchestrator is running; wait or investigate"
    elif state.workflow_status is WorkflowStatus.HUMAN_ACTION_REQUIRED:
        next_action = f"resolve: {state.last_error}"
    elif state.workflow_status in INTERRUPTIBLE_STATES:
        next_action = "`resume` — a previous run was interrupted"
    else:
        next_action = f"`run` work package '{package.name}' (risk {effective.value})"
    print(f"Next action            : {next_action}")

    if getattr(args, "verbose", False):
        _print_runtime_detail(config, state, next_action)
    return 0


def _print_runtime_detail(config, state, next_action: str) -> None:
    """The live view: is anything actually working on this right now?"""

    record = hb.read_heartbeat(config)
    print()
    print("---- runtime ----------------------------------------------")
    if record is None:
        print("No runtime status recorded. Nothing has run since .ai/runtime was")
        print("last cleared, so there is no live process to describe.")
        return

    alive = hb.process_alive(record.pid)
    running = record.is_running()
    if record.finished:
        process_state = "finished"
    elif not alive:
        process_state = "DEAD (process gone)"
    elif record.is_stale():
        age = hb.format_duration(record.age_seconds())
        process_state = f"STALE (no beat for {age})"
    else:
        process_state = "alive"

    debts = auditdebt.load(state.deferred_independent_audits)
    corrections = (
        f"{state.codex_correction_cycles}/{config.limits.max_codex_correction_cycles}"
    )

    print(f"WORKFLOW ID     : {record.workflow_id}")
    package_name = record.package or state.current_work_package or "(none)"
    print(f"ACTIVE PACKAGE  : {package_name}")
    print(f"STATE           : {record.workflow_status or state.workflow_status.value}")
    print(f"STAGE           : {record.stage or state.last_completed_stage or '(none)'}")
    print(f"BUILDER         : {record.builder or state.builder or '(unassigned)'}")
    print(f"REVIEWER        : {record.reviewer or state.reviewer or '(unassigned)'}")
    gate = record.verification_gate or record.current_command or "-"
    print(f"CURRENT GATE    : {gate}")
    print(f"PROCESS         : {process_state} (pid {record.pid})")
    print(f"ELAPSED         : {hb.format_duration(record.elapsed_seconds())}")
    print(f"LAST HEARTBEAT  : {hb.format_duration(record.age_seconds())} ago")
    print(f"CORRECTIONS     : {corrections}")
    print(f"AUDIT DEBT      : {auditdebt.summary(debts)}")
    print(f"SCIENCE FIREWALL: {record.science_firewall}")
    print(f"RUNNING         : {'YES' if running else 'NO'}")
    print(f"NEXT ACTION     : {record.next_action or next_action}")


# ------------------------------------------------------------- audit debt


def cmd_reconcile(config, args) -> int:
    """Clear one deferred independent audit with evidence of a real review."""

    state = load_state(config.state_path)
    debts = auditdebt.load(state.deferred_independent_audits)
    outstanding = auditdebt.open_debts(debts)

    if not args.debt:
        if not outstanding:
            print("No outstanding independent-audit debt.")
            return 0
        print("Outstanding independent-audit debt:")
        for debt in outstanding:
            print(f"  {debt.id}")
            print(f"      package  : {debt.package}")
            print(f"      built by : {debt.builder}")
            print(f"      needs    : {debt.reviewer_required}")
            print(f"      reason   : {debt.reason}")
        print()
        print("Clear one with:")
        print(
            "  python tools/orchestrator.py reconcile --debt <id> "
            "--reviewer <agent> --evidence <text>"
        )
        return 0

    if not args.reviewer or not args.evidence:
        print("reconcile requires --reviewer and --evidence")
        return 1

    kind = (
        auditdebt.EvidenceKind.AGENT
        if args.reviewer in {"codex", "claude"}
        else auditdebt.EvidenceKind.EXTERNAL
    )
    try:
        debt = auditdebt.reconcile(
            debts,
            identifier=args.debt,
            reviewer=args.reviewer,
            evidence=args.evidence,
            kind=kind,
            builder=getattr(args, "builder", None),
        )
    except auditdebt.DebtError as error:
        print(f"refused: {error}")
        return 1

    state.deferred_independent_audits = auditdebt.dump(debts)
    remaining = auditdebt.open_debts(debts)
    if not remaining:
        state.audit_required = False
        state.audit_reason = None
    save_state(config.state_path, state)
    print(f"cleared {debt.id}")
    print(f"  built by  : {debt.builder}")
    print(f"  reviewed  : {debt.cleared_by} ({debt.evidence_kind})")
    print(f"  evidence  : {debt.evidence}")
    print(f"  remaining : {len(remaining)} open debt(s)")
    return 0


def _heartbeat(config, state) -> hb.Heartbeat:
    """Start (or continue) the runtime status for this invocation.

    The workflow id is carried on the state so a resumed run keeps the same
    identity rather than looking like a brand new one.
    """

    beat = hb.Heartbeat(config, workflow_id=state.workflow_id)
    state.workflow_id = beat.record.workflow_id
    beat.beat(
        package=state.current_work_package,
        workflow_status=state.workflow_status.value,
        builder=state.builder,
        reviewer=state.reviewer,
        stage=state.last_completed_stage,
        max_corrections=config.limits.max_codex_correction_cycles,
        correction_count=state.codex_correction_cycles,
        audit_debt=len(
            auditdebt.open_debts(auditdebt.load(state.deferred_independent_audits))
        ),
    )
    return beat


def _goal(config, args) -> str:
    """Which release this invocation is driving.

    Explicit --goal wins, then the configured release_goal. Nothing here knows
    about any particular version number.
    """

    override = getattr(args, "goal", None)
    return str(override or config.release_goal)


# ------------------------------------------------------------------ run/audit


def cmd_run(config, args) -> int:
    state = load_state(config.state_path)
    package, package_path = _resolve_package(config, args.package)
    if package is None:
        print("No eligible work package. Define one in .ai/work_packages/.")
        return 1

    engine = Engine(config, state, heartbeat=_heartbeat(config, state))
    if args.dry_run:
        outcome = engine.plan(package)
        print("DRY RUN — no agent invoked, git untouched\n")
        for line in outcome.messages:
            print(line)
        return 0

    facts = read_repo(config.repo)
    if not facts.is_clean and not args.allow_dirty:
        print("Working tree is dirty. Commit, stash, or pass --allow-dirty.")
        for path in facts.dirty_paths[:20]:
            print(f"  {path}")
        return 1

    try:
        with OrchestratorLock(config.lock_path):
            outcome = engine.execute(package, package_path)
    except LockHeld as error:
        print(f"REFUSED: {error}")
        return 1

    print()
    for line in outcome.messages:
        print(line)
    print(f"\nfinal state: {outcome.status.value}")
    return (
        0
        if outcome.status
        not in {
            WorkflowStatus.HUMAN_ACTION_REQUIRED,
            WorkflowStatus.FAILED,
            WorkflowStatus.BLOCKED,
        }
        else 2
    )


def cmd_audit(config, args) -> int:
    """Force an independent audit of the current state."""

    state = load_state(config.state_path)
    package, package_path = _resolve_package(config, args.package)
    if package is None:
        print("No work package to audit.")
        return 1
    engine = Engine(config, state, heartbeat=_heartbeat(config, state))
    report = verify(config, label=f"{package.name}-audit-preflight")
    outcome_holder = engine.plan(package)
    outcome_holder.status = state.workflow_status
    try:
        with OrchestratorLock(config.lock_path):
            run = engine.run_audit(
                package,
                outcome_holder,
                codex_report="(audit invoked directly; no builder report)",
                verification=report,
                base_commit=state.last_independent_audit_commit,
            )
    except LockHeld as error:
        print(f"REFUSED: {error}")
        return 1
    for line in outcome_holder.messages:
        print(line)
    if run is None or run.contract is None:
        print("audit did not produce a usable contract — HUMAN_ACTION_REQUIRED")
        return 2
    print(f"\nverdict: {run.contract.get('verdict')}")
    save_state(config.state_path, state)
    return 0


def cmd_verify(config, args) -> int:
    package, _ = _resolve_package(config, args.package)
    allowed = package.allowed_files if package else ()
    protected = package.protected_files if package else ()
    report = verify(
        config,
        allowed_files=allowed,
        protected_files=protected,
        label=package.name if package else "manual",
    )
    print(report.summary() or "  (no commands configured)")
    print(f"\nprotected artifacts: {'OK' if report.protected_ok else 'CHANGED'}")
    for path, status in report.protected_detail.items():
        print(f"  {path}: {status}")
    print(f"scope: {report.scope_detail}")
    print(f"passed: {report.passed}")
    return 0 if report.passed else 1


def cmd_resume(config, args) -> int:
    """Continue an interrupted package from the last stage that completed."""

    state = load_state(config.state_path)
    facts = read_repo(config.repo)
    print(f"workflow status: {state.workflow_status.value}")

    package, package_path = _resolve_package(config, state.current_work_package)
    if package is None or package_path is None:
        print(
            f"no work package named {state.current_work_package!r} is available; "
            "nothing to resume."
        )
        return 1

    allowed, why = resume.resumable(state, package.name)
    print(f"resumable: {'yes' if allowed else 'no'} ({why})")
    if not allowed:
        if state.workflow_status is WorkflowStatus.HUMAN_ACTION_REQUIRED:
            print("resolve the issue, then run `stop` to clear or `run` to continue.")
            return 2
        print("nothing to resume; use `run`.")
        return 0

    try:
        plan = resume.plan(
            config,
            state,
            package,
            facts,
            roles.availability_map(config),
        )
    except resume.ResumeRefused as error:
        # Persisted state and repository disagree. Record the refusal rather
        # than guessing which one is right.
        state.transition(
            WorkflowStatus.HUMAN_ACTION_REQUIRED, f"resume refused: {error}"
        )
        state.last_error = f"resume refused: {error}"
        save_state(config.state_path, state)
        print(f"REFUSED: {error}")
        print("state and repository disagree; resolve manually, then `run`.")
        return 2

    print(f"plan: {plan.describe()}")
    print(f"first stage to run: {plan.first_stage_to_run}")
    if plan.builder:
        print(f"builder (recorded)  : {plan.builder.value}")
    if plan.reviewer_required:
        availability = "available" if plan.reviewer_available else "UNAVAILABLE"
        print(f"reviewer (required) : {plan.reviewer_required.value} [{availability}]")

    if plan.nothing_to_do:
        print("package already committed with no outstanding review; nothing to do.")
        state.transition(WorkflowStatus.IDLE, "resume found the package complete")
        save_state(config.state_path, state)
        return 0

    if plan.debt is not None and not plan.reviewer_available:
        print(
            f"deferred audit {plan.debt.id} still needs "
            f"{plan.debt.reviewer_required}, which is unavailable; not resuming."
        )
        return 2

    if getattr(args, "dry_run", False):
        print("(dry run: no agent invoked)")
        return 0

    lock = OrchestratorLock(config.lock_path)
    try:
        with lock.acquire():
            engine = Engine(
                config,
                state,
                heartbeat=_heartbeat(config, state),
                preferred_builder=plan.builder,
            )
            if plan.review_only:
                outcome = engine.review_only(
                    package, package_path, builder_report=plan.builder_report
                )
            else:
                outcome = engine.execute(package, package_path, resume_plan=plan)
    except LockHeld as error:
        print(f"another orchestrator run holds the lock: {error}")
        return 1

    for message in outcome.messages:
        print(f"  {message}")
    print(f"status: {outcome.status.value}")
    if outcome.commit:
        print(f"commit: {outcome.commit[:12]}")
    return 0 if outcome.status is not WorkflowStatus.HUMAN_ACTION_REQUIRED else 2


def cmd_stop(config, args) -> int:
    state = load_state(config.state_path)
    state.transition(WorkflowStatus.IDLE, "manually stopped")
    state.blocking_findings = []
    state.codex_correction_cycles = 0
    state.claude_reaudit_cycles = 0
    state.provisional_review_cycles = 0
    state.last_error = None
    save_state(config.state_path, state)
    OrchestratorLock(config.lock_path).path.unlink(missing_ok=True)
    print("workflow reset to IDLE and lock cleared")
    return 0


def cmd_packages(config, args) -> int:
    packages = list_packages(config.ai_dir / "work_packages")
    if not packages:
        print("no work packages defined")
        return 0
    for package in packages:
        print(
            f"  {package.status.value:<10} {package.risk.value:<7} {package.name:<28} "
            f"{package.objective[:60]}"
        )
    return 0


def _autopilot_resume_plan(config, state, package):
    """A resume plan for an interrupted package, or None to start fresh.

    Autopilot must not rebuild work that already completed. When the persisted
    state describes this package mid-flight, resume it; when the state and the
    repository disagree, return None so the normal path re-derives everything
    rather than acting on a plan that cannot be trusted.
    """

    if state.current_work_package != package.name:
        return None
    allowed, _why = resume.resumable(state, package.name)
    if not allowed:
        return None
    try:
        return resume.plan(
            config,
            state,
            package,
            read_repo(config.repo),
            roles.availability_map(config),
        )
    except resume.ResumeRefused:
        # A refusal means the persisted state and the repository disagree.
        # Rebuilding from scratch on top of that disagreement is exactly the
        # unsafe act the refusal exists to prevent, so it is raised, not
        # swallowed.
        raise


def cmd_autopilot(config, args) -> int:
    """Run eligible packages sequentially with bounded package-level progress."""

    state = load_state(config.state_path)
    attempted: set[str] = set()
    try:
        with OrchestratorLock(config.lock_path):
            while True:
                package, package_path = _resolve_package(config, None)
                if package is None:
                    state.transition(
                        WorkflowStatus.READY_FOR_CLAUDE_RELEASE_AUDIT,
                        "all eligible packages completed; release-level audit required",
                    )
                    state.audit_required = True
                    state.audit_reason = (
                        f"comprehensive {_goal(config, args)} release audit required"
                    )
                    save_state(config.state_path, state)
                    print("All eligible work packages completed.")
                    print("Final status: READY_FOR_CLAUDE_RELEASE_AUDIT")
                    print("Resume command: python tools/orchestrator.py release-audit")
                    return 0
                if package.name in attempted:
                    reason = (
                        f"autopilot made no package progress on {package.name}; "
                        "refusing an implementation loop"
                    )
                    state.transition(WorkflowStatus.HUMAN_ACTION_REQUIRED, reason)
                    state.last_error = reason
                    save_state(config.state_path, state)
                    print(reason)
                    return 2
                attempted.add(package.name)
                print(f"\n=== AUTOPILOT: {package.name} ===")
                engine = Engine(config, state, heartbeat=_heartbeat(config, state))
                try:
                    plan = _autopilot_resume_plan(config, state, package)
                except resume.ResumeRefused as error:
                    reason = f"resume refused for {package.name}: {error}"
                    state.transition(WorkflowStatus.HUMAN_ACTION_REQUIRED, reason)
                    state.last_error = reason
                    save_state(config.state_path, state)
                    print(reason)
                    print("autopilot stopped: HUMAN_ACTION_REQUIRED")
                    return 2
                if plan is None:
                    outcome = engine.execute(package, package_path)
                elif plan.review_only:
                    print(f"resuming: {plan.describe()}")
                    outcome = engine.review_only(
                        package, package_path, builder_report=plan.builder_report
                    )
                else:
                    print(f"resuming: {plan.describe()}")
                    outcome = engine.execute(package, package_path, resume_plan=plan)
                for line in outcome.messages:
                    print(line)
                if outcome.status in {
                    WorkflowStatus.HUMAN_ACTION_REQUIRED,
                    WorkflowStatus.FAILED,
                    WorkflowStatus.BLOCKED,
                }:
                    print(f"autopilot stopped: {outcome.status.value}")
                    return 2
                if outcome.commit is None:
                    reason = (
                        f"package {package.name} finished without a commit; "
                        "autopilot cannot prove forward progress"
                    )
                    state.transition(WorkflowStatus.HUMAN_ACTION_REQUIRED, reason)
                    state.last_error = reason
                    save_state(config.state_path, state)
                    print(reason)
                    return 2
    except LockHeld as error:
        print(f"REFUSED: {error}")
        return 1


def cmd_release_audit(config, args) -> int:
    """Run the comprehensive independent audit over all deferred release work."""

    state = load_state(config.state_path)
    available, location = agents.agent_available(config.claude)
    if not available:
        state.transition(
            WorkflowStatus.READY_FOR_CLAUDE_RELEASE_AUDIT,
            f"Claude unavailable ({location})",
        )
        state.audit_required = True
        state.audit_reason = "Claude unavailable for comprehensive release audit"
        save_state(config.state_path, state)
        print("READY_FOR_CLAUDE_RELEASE_AUDIT")
        print("Resume command: python tools/orchestrator.py release-audit")
        return 2

    goal = _goal(config, args)
    report = verify(config, label=f"openphase-{goal}-release-audit-preflight")
    if not report.passed:
        reason = "release-audit preflight verification failed"
        state.transition(WorkflowStatus.HUMAN_ACTION_REQUIRED, reason)
        state.last_error = reason
        save_state(config.state_path, state)
        print(report.summary())
        print(reason)
        return 2

    package = WorkPackage(
        name=f"openphase_{config.goal_slug}_release_audit",
        objective=(
            f"Comprehensively audit OpenPhase {goal}: every commit since the last "
            "independent audit, all deferred packages, application architecture, "
            "scientific separation, result/export/error integrity, Streamlit "
            "behavior, tests, deployment readiness, security, documentation "
            "truthfulness, and scope control."
        ),
        risk=Risk.MEDIUM,
        protected_files=(
            "src/pvt_phase_simulator",
            "data",
            "docs/validation",
            "tests/golden_master",
        ),
        scientific_invariants=(
            "The frozen scientific engine and protected artifacts remain unchanged.",
            "Provisional Codex reviews are audit debt, not independent approval.",
        ),
        audit_policy=AuditPolicy.IMMEDIATE,
        commit_policy=CommitPolicy.MANUAL,
    )
    engine = Engine(config, state, heartbeat=_heartbeat(config, state))
    outcome = engine.plan(package)
    outcome.status = state.workflow_status
    debt_summary = "\n".join(str(item) for item in state.deferred_independent_audits)
    try:
        with OrchestratorLock(config.lock_path):
            run = engine.run_audit(
                package,
                outcome,
                codex_report=(
                    "Deferred independent-audit debt:\n"
                    + (debt_summary or "(none recorded)")
                ),
                verification=report,
                base_commit=state.last_independent_audit_commit,
            )
    except LockHeld as error:
        print(f"REFUSED: {error}")
        return 1
    for line in outcome.messages:
        print(line)
    if run is None or run.contract is None:
        if outcome.review_unavailable_reason:
            state.transition(
                WorkflowStatus.READY_FOR_CLAUDE_RELEASE_AUDIT,
                outcome.review_unavailable_reason,
            )
            state.audit_required = True
            state.audit_reason = outcome.review_unavailable_reason
            save_state(config.state_path, state)
            print("READY_FOR_CLAUDE_RELEASE_AUDIT")
            print("Resume command: python tools/orchestrator.py release-audit")
        return 2
    blocking = agents.blocking_findings(run.contract)
    if run.contract.get("verdict") == "APPROVED" and not blocking:
        state.deferred_independent_audits = []
        state.blocking_findings = []
        state.audit_required = False
        state.audit_reason = None
        state.last_independent_audit_commit = read_repo(config.repo).head
        state.transition(WorkflowStatus.APPROVED, f"{goal} release audit approved")
        save_state(config.state_path, state)
        print("INDEPENDENT_AUDIT_APPROVED")
        return 0

    correction = WorkPackage(
        name=f"openphase_{config.goal_slug}_release_audit_corrections",
        objective=(
            f"Close only the blocking findings from the comprehensive {goal} "
            "release audit:\n"
            + "\n".join(
                f"- {item.get('id')}: {item.get('summary')}" for item in blocking
            )
        ),
        risk=Risk.MEDIUM,
        allowed_files=(
            "src/pvt_phase_simulator_ui",
            "app",
            "streamlit_app.py",
            ".streamlit/config.toml",
            "tests/test_app*.py",
            "docs/STREAMLIT_APPLICATION.md",
            "README.md",
        ),
        protected_files=package.protected_files,
        scientific_invariants=package.scientific_invariants,
        required_tests=config.verification_commands,
        audit_policy=AuditPolicy.IMMEDIATE,
        commit_policy=CommitPolicy.AFTER_AUDIT,
        status=PackageStatus.PENDING,
        notes="Generated automatically from blocking release-audit findings.",
    )
    correction_path = (
        config.ai_dir
        / "work_packages"
        / f"openphase_{config.goal_slug}_release_audit_corrections.json"
    )
    save_package(correction_path, correction)
    state.blocking_findings = blocking
    state.transition(
        WorkflowStatus.IDLE,
        "blocking release-audit findings converted to a correction package",
    )
    save_state(config.state_path, state)
    print(f"Correction package: {correction_path}")
    print("Resume command: python tools/orchestrator.py autopilot")
    return 2


COMMANDS = {
    "status": cmd_status,
    "run": cmd_run,
    "verify": cmd_verify,
    "audit": cmd_audit,
    "resume": cmd_resume,
    "stop": cmd_stop,
    "packages": cmd_packages,
    "autopilot": cmd_autopilot,
    "release-audit": cmd_release_audit,
    "reconcile": cmd_reconcile,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="orchestrator",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("--package", default=None, help="work package name")
    parser.add_argument(
        "--dry-run", action="store_true", help="plan without invoking agents"
    )
    parser.add_argument(
        "--allow-dirty", action="store_true", help="permit a dirty tree"
    )
    parser.add_argument("--config", default=None, help="path to .ai/config.json")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="status: include live runtime detail from the heartbeat",
    )
    parser.add_argument(
        "--goal",
        default=None,
        help="release goal to drive, e.g. v1.2 (defaults to the configured goal)",
    )
    parser.add_argument("--debt", default=None, help="audit-debt id to reconcile")
    parser.add_argument(
        "--reviewer", default=None, help="agent that performed the independent review"
    )
    parser.add_argument(
        "--evidence", default=None, help="evidence for an external independent review"
    )
    parser.add_argument(
        "--builder",
        default=None,
        help="name the builder of a legacy debt that recorded no provenance",
    )
    args = parser.parse_args(argv)

    try:
        config = load_config(REPO, Path(args.config) if args.config else None)
    except ConfigError as error:
        print(f"configuration error: {error}")
        return 1
    return COMMANDS[args.command](config, args)


if __name__ == "__main__":
    raise SystemExit(main())
