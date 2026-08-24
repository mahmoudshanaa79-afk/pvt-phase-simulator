#!/usr/bin/env python
"""Local orchestrator CLI: Codex builds, Claude audits, local gates decide.

python tools/orchestrator.py status
python tools/orchestrator.py run [--package NAME] [--dry-run]
python tools/orchestrator.py verify
python tools/orchestrator.py audit [--package NAME]
python tools/orchestrator.py resume
python tools/orchestrator.py stop
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

from orchestration import agents  # noqa: E402
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
    assess_risk,
    list_packages,
    load_package,
    next_package,
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

    if package is None:
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
    return 0


# ------------------------------------------------------------------ run/audit


def cmd_run(config, args) -> int:
    state = load_state(config.state_path)
    package, package_path = _resolve_package(config, args.package)
    if package is None:
        print("No eligible work package. Define one in .ai/work_packages/.")
        return 1

    engine = Engine(config, state)
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
    engine = Engine(config, state)
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
    state = load_state(config.state_path)
    facts = read_repo(config.repo)
    print(f"workflow status: {state.workflow_status.value}")
    if state.workflow_status is WorkflowStatus.HUMAN_ACTION_REQUIRED:
        print(f"blocked on: {state.last_error}")
        print("resolve the issue, then run `stop` to clear or `run` to continue.")
        return 2
    if state.workflow_status not in INTERRUPTIBLE_STATES:
        print("nothing to resume; use `run`.")
        return 0
    print(f"interrupted during {state.workflow_status.value}; re-verifying from git")
    report = verify(config, label="resume")
    print(report.summary() or "  (no commands configured)")
    print(
        f"tree {'clean' if facts.is_clean else 'dirty'}; "
        f"verification passed={report.passed}"
    )
    print(
        "re-run `run` to continue from this boundary; "
        "completed commits are not repeated."
    )
    return 0


def cmd_stop(config, args) -> int:
    state = load_state(config.state_path)
    state.transition(WorkflowStatus.IDLE, "manually stopped")
    state.blocking_findings = []
    state.codex_correction_cycles = 0
    state.claude_reaudit_cycles = 0
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


COMMANDS = {
    "status": cmd_status,
    "run": cmd_run,
    "verify": cmd_verify,
    "audit": cmd_audit,
    "resume": cmd_resume,
    "stop": cmd_stop,
    "packages": cmd_packages,
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
    args = parser.parse_args(argv)

    try:
        config = load_config(REPO, Path(args.config) if args.config else None)
    except ConfigError as error:
        print(f"configuration error: {error}")
        return 1
    return COMMANDS[args.command](config, args)


if __name__ == "__main__":
    raise SystemExit(main())
