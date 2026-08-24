"""Tests for the orchestration layer.

Every agent boundary is mocked: these tests never spend a real Codex or Claude
call. They live outside `tests/` so the scientific suite's collected set is
unchanged; run them with `pytest tools/tests`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

from orchestration import agents  # noqa: E402
from orchestration.config import AgentConfig, Limits, OrchestratorConfig  # noqa: E402
from orchestration.engine import Engine  # noqa: E402
from orchestration.gitops import ForbiddenGitOperation, git, read_repo  # noqa: E402
from orchestration.lock import LockHeld, OrchestratorLock  # noqa: E402
from orchestration.state import (  # noqa: E402
    StateSchemaError,
    WorkflowState,
    WorkflowStatus,
    load_state,
    save_state,
)
from orchestration.verify import check_protected_artifacts, check_scope  # noqa: E402
from orchestration.workpackage import (  # noqa: E402
    AuditPolicy,
    CommitPolicy,
    Risk,
    WorkPackage,
    assess_risk,
    save_package,
)

# --------------------------------------------------------------------- fixtures


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throwaway git repository with one committed file."""

    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"], cwd=root, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    (root / "protected.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=root, check=True)
    return root


@pytest.fixture
def config(repo: Path) -> OrchestratorConfig:
    import hashlib

    digest = hashlib.sha256((repo / "protected.csv").read_bytes()).hexdigest().upper()
    return OrchestratorConfig(
        repo=repo,
        ai_dir=repo / ".ai",
        codex=AgentConfig(executable="codex-stub"),
        claude=AgentConfig(executable="claude-stub"),
        limits=Limits(
            max_codex_correction_cycles=2,
            max_claude_reaudit_cycles=2,
            max_agent_runtime_minutes=1,
            audit_batch_size=5,
        ),
        verification_commands=((sys.executable, "-c", "pass"),),
        fast_verification_commands=(),
        protected_artifacts={"protected.csv": digest},
        protected_paths=("protected.csv",),
        high_risk_paths=("science/",),
    )


def make_package(**overrides) -> WorkPackage:
    base = {
        "name": "demo",
        "objective": "Add a harmless marker file.",
        "risk": Risk.LOW,
        "allowed_files": ("work.txt",),
        "audit_policy": AuditPolicy.BATCH,
        "commit_policy": CommitPolicy.AFTER_VERIFY,
    }
    base.update(overrides)
    return WorkPackage(**base)  # type: ignore[arg-type]


def codex_stub(*, status="COMPLETE", writes="work.txt", body=None):
    """Build a fake Codex runner that optionally touches the working tree."""

    def runner(config, order_path, *, stem, sandbox="workspace-write"):
        if writes:
            (config.repo / writes).write_text("built\n", encoding="utf-8")
        report = body or (
            "Implemented.\n\n<ORCHESTRATOR_RESULT>\n"
            + json.dumps(
                {
                    "status": status,
                    "tests_claimed": "all green",
                    "files_changed": [writes] if writes else [],
                    "ready_for_local_verification": True,
                }
            )
            + "\n</ORCHESTRATOR_RESULT>\n"
        )
        run = agents.AgentRun(
            name="codex",
            command=["codex-stub"],
            exit_code=0,
            stdout=report,
            stderr="",
            raw_report=report,
        )
        try:
            run.contract = agents.validate_builder_contract(
                agents.parse_contract(report)
            )
        except agents.ContractError as error:
            run.contract_error = str(error)
        return run

    return runner


def claude_stub(
    verdict="APPROVED", findings=(), malformed=False, sequence=None, cost=0.25
):
    """Fake Claude runner; `sequence` yields a different verdict per call."""

    calls = {"n": 0}

    def runner(config, prompt_path, *, stem, **kwargs):
        index = calls["n"]
        calls["n"] += 1
        this_verdict, this_findings = (
            sequence[min(index, len(sequence) - 1)] if sequence else (verdict, findings)
        )
        if malformed:
            report = "I audited it and it looks fine to me."
        else:
            report = (
                "Full audit text.\n\n<ORCHESTRATOR_RESULT>\n"
                + json.dumps(
                    {
                        "verdict": this_verdict,
                        "findings": list(this_findings),
                        "safe_defer": [],
                    }
                )
                + "\n</ORCHESTRATOR_RESULT>\n"
            )
        run = agents.AgentRun(
            name="claude",
            command=["claude-stub"],
            exit_code=0,
            stdout=report,
            stderr="",
            raw_report=report,
            cost_usd=cost,
        )
        try:
            run.contract = agents.validate_audit_contract(agents.parse_contract(report))
        except agents.ContractError as error:
            run.contract_error = str(error)
        return run

    runner.calls = calls  # type: ignore[attr-defined]
    return runner


BLOCKER = {"id": "C-1", "severity": "C", "blocks": True, "summary": "bad thing"}


# ------------------------------------------------------------------ state tests


class TestState:
    def test_roundtrip_is_atomic_and_lossless(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        state = WorkflowState(work_packages_since_audit=3, audit_required=True)
        save_state(path, state)
        assert load_state(path).work_packages_since_audit == 3
        assert load_state(path).audit_required is True

    def test_missing_file_yields_idle(self, tmp_path: Path) -> None:
        assert load_state(tmp_path / "nope.json").workflow_status is WorkflowStatus.IDLE

    def test_unknown_status_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        path.write_text(
            json.dumps(
                {
                    "project": "p",
                    "phase": "x",
                    "workflow_status": "NOT_A_STATE",
                    "work_packages_since_audit": 0,
                    "audit_required": False,
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(StateSchemaError, match="unknown workflow_status"):
            load_state(path)

    def test_missing_required_key_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        path.write_text(json.dumps({"project": "p"}), encoding="utf-8")
        with pytest.raises(StateSchemaError, match="missing required keys"):
            load_state(path)

    def test_transition_records_reason(self) -> None:
        state = WorkflowState()
        state.transition(WorkflowStatus.CODEX_RUNNING, "because")
        assert state.workflow_status is WorkflowStatus.CODEX_RUNNING
        assert state.history[-1]["reason"] == "because"

    def test_interrupted_write_leaves_previous_file_intact(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "state.json"
        save_state(path, WorkflowState(work_packages_since_audit=1))
        before = path.read_text(encoding="utf-8")
        # Temp files are written beside the target then renamed; a leftover
        # temp must never be mistaken for the state file.
        assert not any(p.suffix == ".tmp" for p in tmp_path.iterdir())
        assert path.read_text(encoding="utf-8") == before


# ------------------------------------------------------------------- contracts


class TestContracts:
    def test_parses_trailing_block(self) -> None:
        text = (
            'prose\n<ORCHESTRATOR_RESULT>\n{"verdict": "APPROVED"}\n'
            "</ORCHESTRATOR_RESULT>"
        )
        assert agents.parse_contract(text)["verdict"] == "APPROVED"

    def test_last_block_wins_over_quoted_template(self) -> None:
        text = (
            '<ORCHESTRATOR_RESULT>{"verdict": "NOT_APPROVED"}</ORCHESTRATOR_RESULT>\n'
            "actually:\n"
            '<ORCHESTRATOR_RESULT>{"verdict": "APPROVED"}</ORCHESTRATOR_RESULT>'
        )
        assert agents.parse_contract(text)["verdict"] == "APPROVED"

    def test_missing_block_raises(self) -> None:
        with pytest.raises(agents.ContractError, match="no <ORCHESTRATOR_RESULT>"):
            agents.parse_contract("looks good to me")

    def test_malformed_json_raises(self) -> None:
        with pytest.raises(agents.ContractError, match="not valid JSON"):
            agents.parse_contract("<ORCHESTRATOR_RESULT>{nope}</ORCHESTRATOR_RESULT>")

    @pytest.mark.parametrize("verdict", ["approved", "OK", "LGTM", "", None])
    def test_invalid_verdict_is_never_approval(self, verdict) -> None:
        with pytest.raises(agents.ContractError, match="verdict"):
            agents.validate_audit_contract({"verdict": verdict})

    def test_finding_requires_boolean_blocks(self) -> None:
        with pytest.raises(agents.ContractError, match="must be a boolean"):
            agents.validate_audit_contract(
                {
                    "verdict": "CONDITIONAL",
                    "findings": [
                        {"id": "x", "severity": "C", "blocks": "yes", "summary": "s"}
                    ],
                }
            )

    def test_invalid_severity_is_rejected(self) -> None:
        with pytest.raises(agents.ContractError, match="severity"):
            agents.validate_audit_contract(
                {
                    "verdict": "CONDITIONAL",
                    "findings": [
                        {"id": "x", "severity": "Z", "blocks": True, "summary": "s"}
                    ],
                }
            )

    def test_builder_status_must_be_known(self) -> None:
        with pytest.raises(agents.ContractError, match="builder status"):
            agents.validate_builder_contract({"status": "DONE-ISH"})


# ------------------------------------------------------------------ risk policy


class TestRisk:
    def test_declared_low_stays_low_off_science_paths(self) -> None:
        risk, _ = assess_risk(Risk.LOW, ("docs/readme.md",), ("src/eos/",))
        assert risk is Risk.LOW

    def test_low_escalates_when_science_touched(self) -> None:
        risk, why = assess_risk(Risk.LOW, ("src/eos/flash.py",), ("src/eos/",))
        assert risk is Risk.HIGH
        assert "escalated" in why

    def test_high_stays_high(self) -> None:
        risk, _ = assess_risk(Risk.HIGH, ("docs/x.md",), ("src/eos/",))
        assert risk is Risk.HIGH


class TestAuditDecision:
    def _engine(self, config, state):
        return Engine(config, state)

    def test_high_risk_audits_immediately(self, config) -> None:
        engine = self._engine(config, WorkflowState())
        needs, why = engine.audit_decision(make_package(), Risk.HIGH)
        assert needs is True and "HIGH-risk" in why

    def test_batches_below_threshold(self, config) -> None:
        engine = self._engine(config, WorkflowState(work_packages_since_audit=2))
        needs, why = engine.audit_decision(make_package(), Risk.LOW)
        assert needs is False and "3/5" in why

    def test_fifth_package_triggers_milestone(self, config) -> None:
        engine = self._engine(config, WorkflowState(work_packages_since_audit=4))
        needs, why = engine.audit_decision(make_package(), Risk.LOW)
        assert needs is True and "milestone" in why

    def test_policy_none_never_audits(self, config) -> None:
        engine = self._engine(config, WorkflowState(work_packages_since_audit=99))
        needs, _ = engine.audit_decision(
            make_package(audit_policy=AuditPolicy.NONE), Risk.LOW
        )
        assert needs is False

    def test_policy_immediate_audits(self, config) -> None:
        engine = self._engine(config, WorkflowState())
        needs, _ = engine.audit_decision(
            make_package(audit_policy=AuditPolicy.IMMEDIATE), Risk.LOW
        )
        assert needs is True


# ------------------------------------------------------------------ protection


class TestProtection:
    def test_unchanged_artifact_passes(self, config) -> None:
        ok, detail = check_protected_artifacts(config)
        assert ok and detail["protected.csv"] == "unchanged"

    def test_changed_artifact_is_detected(self, config) -> None:
        (config.repo / "protected.csv").write_text("tampered\n", encoding="utf-8")
        ok, detail = check_protected_artifacts(config)
        assert not ok and "CHANGED" in detail["protected.csv"]

    def test_missing_artifact_is_detected(self, config) -> None:
        (config.repo / "protected.csv").unlink()
        ok, detail = check_protected_artifacts(config)
        assert not ok and detail["protected.csv"] == "MISSING"

    def test_scope_rejects_protected_path(self, config) -> None:
        ok, detail = check_scope(
            config, ("protected.csv",), ("work.txt",), ("protected.csv",)
        )
        assert not ok and "protected" in detail

    def test_scope_rejects_file_outside_allowed(self, config) -> None:
        ok, detail = check_scope(config, ("sneaky.py",), ("work.txt",), ())
        assert not ok and "outside" in detail

    def test_scope_accepts_allowed_directory(self, config) -> None:
        ok, _ = check_scope(config, ("pkg/a.py", "pkg/b.py"), ("pkg",), ())
        assert ok


# ------------------------------------------------------------------ git safety


class TestGitSafety:
    @pytest.mark.parametrize(
        "args",
        [
            ("reset", "--hard"),
            ("clean", "-fd"),
            ("push", "--force"),
            ("commit", "--amend"),
            ("rebase", "-i", "HEAD~2"),
        ],
    )
    def test_destructive_operations_are_refused(self, repo: Path, args) -> None:
        with pytest.raises(ForbiddenGitOperation):
            git(repo, *args)

    def test_read_only_commands_are_allowed(self, repo: Path) -> None:
        assert git(repo, "rev-parse", "HEAD").strip()

    def test_read_repo_reports_dirty(self, repo: Path) -> None:
        (repo / "new.txt").write_text("x", encoding="utf-8")
        facts = read_repo(repo)
        assert not facts.is_clean and "new.txt" in facts.dirty_paths


# ----------------------------------------------------------------------- lock


class TestLock:
    def test_second_acquire_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "l.lock"
        with OrchestratorLock(path):
            with pytest.raises(LockHeld):
                OrchestratorLock(path).acquire()

    def test_lock_is_released_on_exit(self, tmp_path: Path) -> None:
        path = tmp_path / "l.lock"
        with OrchestratorLock(path):
            assert path.exists()
        assert not path.exists()

    def test_stale_lock_from_dead_pid_is_recovered(self, tmp_path: Path) -> None:
        path = tmp_path / "l.lock"
        path.write_text(
            json.dumps({"pid": 999_999_999, "started": 0}), encoding="utf-8"
        )
        held, detail = OrchestratorLock(path).inspect()
        assert not held and "stale" in detail
        OrchestratorLock(path).acquire()  # must not raise

    def test_corrupt_lock_is_not_treated_as_held(self, tmp_path: Path) -> None:
        path = tmp_path / "l.lock"
        path.write_text("{{{not json", encoding="utf-8")
        held, _ = OrchestratorLock(path).inspect()
        assert not held


# ------------------------------------------------------------- end-to-end loop


class TestEndToEnd:
    def _run(self, config, state, package, codex, claude):
        directory = config.ai_dir / "work_packages"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{package.name}.json"
        save_package(path, package)
        engine = Engine(config, state, codex_runner=codex, claude_runner=claude)
        return engine.execute(package, path)

    def test_low_risk_commits_without_audit(self, config) -> None:
        state = WorkflowState()
        claude = claude_stub()
        outcome = self._run(config, state, make_package(), codex_stub(), claude)
        assert outcome.status is WorkflowStatus.IDLE
        assert outcome.commit is not None
        assert claude.calls["n"] == 0  # auditor not spent on batched work
        assert state.work_packages_since_audit == 1

    def test_high_risk_audits_before_finishing(self, config) -> None:
        state = WorkflowState()
        claude = claude_stub("APPROVED")
        outcome = self._run(
            config, state, make_package(risk=Risk.HIGH), codex_stub(), claude
        )
        assert claude.calls["n"] == 1
        assert outcome.status is WorkflowStatus.APPROVED
        assert state.work_packages_since_audit == 0

    def test_fifth_package_triggers_milestone_audit(self, config) -> None:
        state = WorkflowState(work_packages_since_audit=4)
        claude = claude_stub("APPROVED")
        self._run(config, state, make_package(), codex_stub(), claude)
        assert claude.calls["n"] == 1
        assert state.work_packages_since_audit == 0

    def test_codex_failure_escalates(self, config) -> None:
        state = WorkflowState()
        outcome = self._run(
            config, state, make_package(), codex_stub(status="FAILED"), claude_stub()
        )
        assert outcome.status is WorkflowStatus.HUMAN_ACTION_REQUIRED

    def test_malformed_codex_contract_escalates(self, config) -> None:
        state = WorkflowState()
        outcome = self._run(
            config,
            state,
            make_package(),
            codex_stub(body="I finished, trust me."),
            claude_stub(),
        )
        assert outcome.status is WorkflowStatus.HUMAN_ACTION_REQUIRED
        assert "contract" in (outcome.human_action or "")

    def test_malformed_claude_output_never_approves(self, config) -> None:
        state = WorkflowState()
        outcome = self._run(
            config,
            state,
            make_package(risk=Risk.HIGH),
            codex_stub(),
            claude_stub(malformed=True),
        )
        assert outcome.status is WorkflowStatus.HUMAN_ACTION_REQUIRED
        assert outcome.commit is None

    def test_protected_artifact_change_blocks_commit(self, config) -> None:
        state = WorkflowState()

        def tamper(cfg, order, *, stem, sandbox="workspace-write"):
            (cfg.repo / "protected.csv").write_text("tampered\n", encoding="utf-8")
            return codex_stub(writes=None)(cfg, order, stem=stem)

        outcome = self._run(config, state, make_package(), tamper, claude_stub())
        assert outcome.commit is None

    def test_unexpected_file_blocks_commit(self, config) -> None:
        state = WorkflowState()
        outcome = self._run(
            config,
            state,
            make_package(),
            codex_stub(writes="not_allowed.py"),
            claude_stub(),
        )
        assert outcome.commit is None

    def test_conditional_verdict_runs_correction_then_approves(self, config) -> None:
        state = WorkflowState()
        claude = claude_stub(sequence=[("CONDITIONAL", [BLOCKER]), ("APPROVED", [])])
        outcome = self._run(
            config, state, make_package(risk=Risk.HIGH), codex_stub(), claude
        )
        assert claude.calls["n"] == 2  # initial audit + targeted re-audit
        assert outcome.status is WorkflowStatus.APPROVED
        # Counters reset once an audit approves, so the surviving evidence that a
        # correction ran is the second (targeted) auditor call above.
        assert state.codex_correction_cycles == 0
        assert state.blocking_findings == []

    def test_correction_cycle_limit_escalates(self, config) -> None:
        state = WorkflowState()
        claude = claude_stub("NOT_APPROVED", [BLOCKER])
        outcome = self._run(
            config, state, make_package(risk=Risk.HIGH), codex_stub(), claude
        )
        assert outcome.status is WorkflowStatus.HUMAN_ACTION_REQUIRED
        assert "cycles" in (outcome.human_action or "")
        assert (
            state.codex_correction_cycles <= config.limits.max_codex_correction_cycles
        )

    def test_commit_policy_after_audit_defers_commit(self, config) -> None:
        state = WorkflowState()
        outcome = self._run(
            config,
            state,
            make_package(commit_policy=CommitPolicy.AFTER_AUDIT),
            codex_stub(),
            claude_stub(),
        )
        assert outcome.commit is None

    def test_dry_run_invokes_nothing(self, config) -> None:
        state = WorkflowState()
        claude = claude_stub()
        engine = Engine(config, state, codex_runner=codex_stub(), claude_runner=claude)
        before = read_repo(config.repo).head
        outcome = engine.plan(make_package(risk=Risk.HIGH))
        assert claude.calls["n"] == 0
        assert read_repo(config.repo).head == before
        assert any("dry run" in line for line in outcome.messages)
        assert not (config.repo / "work.txt").exists()


class TestRecovery:
    def test_interrupted_state_is_recognised(self, config) -> None:
        state = WorkflowState()
        state.transition(WorkflowStatus.CODEX_RUNNING, "interrupted")
        save_state(config.state_path, state)
        from orchestration.state import INTERRUPTIBLE_STATES

        reloaded = load_state(config.state_path)
        assert reloaded.workflow_status in INTERRUPTIBLE_STATES

    def test_completed_commit_is_not_repeated(self, config) -> None:
        """A second run over an already-clean tree must not re-commit."""

        state = WorkflowState()
        directory = config.ai_dir / "work_packages"
        directory.mkdir(parents=True, exist_ok=True)
        package = make_package()
        path = directory / "demo.json"
        save_package(path, package)
        engine = Engine(
            config, state, codex_runner=codex_stub(), claude_runner=claude_stub()
        )
        first = engine.execute(package, path)
        assert first.commit is not None
        # Nothing new to build: the builder writes the same content, so the tree
        # stays clean and there is nothing to commit a second time.
        second = engine.execute(package, path)
        assert second.commit is None


class TestAuditorBudget:
    """Spend safeguards. No real paid call is made anywhere in this class."""

    @staticmethod
    def _envelope(cost: float | None) -> str:
        """A realistic Claude JSON envelope, optionally carrying a cost."""

        body = {
            "result": (
                "audit text\n<ORCHESTRATOR_RESULT>\n"
                + json.dumps({"verdict": "APPROVED", "findings": []})
                + "\n</ORCHESTRATOR_RESULT>"
            )
        }
        if cost is not None:
            body["total_cost_usd"] = cost
        return json.dumps(body)

    def test_native_budget_flag_is_passed_to_claude(self, config, monkeypatch) -> None:
        captured: dict[str, list[str]] = {}
        envelope = self._envelope(0.5)

        class FakeCompleted:
            returncode = 0
            stdout = envelope
            stderr = ""

        def fake_run(command, **kwargs):
            captured["command"] = command
            return FakeCompleted()

        monkeypatch.setattr(agents.subprocess, "run", fake_run)
        monkeypatch.setattr(agents, "_resolve", lambda agent, name: "claude-exe")
        prompt = config.repo / "p.md"
        prompt.write_text("audit please", encoding="utf-8")
        run = agents.run_claude_audit(config, prompt, stem="budget")
        assert "--max-budget-usd" in captured["command"]
        index = captured["command"].index("--max-budget-usd")
        assert captured["command"][index + 1] == str(
            config.limits.max_claude_cost_usd_per_run
        )
        assert run.cost_usd == 0.5

    def test_missing_cost_metadata_is_not_fabricated(self, config, monkeypatch) -> None:
        envelope = self._envelope(None)

        class FakeCompleted:
            returncode = 0
            stdout = envelope
            stderr = ""

        monkeypatch.setattr(
            agents.subprocess, "run", lambda command, **k: FakeCompleted()
        )
        monkeypatch.setattr(agents, "_resolve", lambda agent, name: "claude-exe")
        prompt = config.repo / "p.md"
        prompt.write_text("audit please", encoding="utf-8")
        run = agents.run_claude_audit(config, prompt, stem="nocost")
        assert run.cost_usd is None  # never estimated

    def test_run_below_budget_proceeds(self, config) -> None:
        state = WorkflowState(claude_cost_usd_this_package=1.0)
        engine = Engine(config, state)
        allowed, note = engine.budget_check()
        assert allowed and "1.0000" in note

    def test_run_at_budget_is_refused(self, config) -> None:
        ceiling = config.limits.max_claude_cost_usd_per_work_package
        state = WorkflowState(claude_cost_usd_this_package=ceiling)
        engine = Engine(config, state)
        allowed, note = engine.budget_check()
        assert not allowed and "exhausted" in note

    def test_headroom_is_reserved_for_the_next_run(self, config) -> None:
        """Refuse while there is still nominal room but not a full run's worth."""

        ceiling = config.limits.max_claude_cost_usd_per_work_package
        per_run = config.limits.max_claude_cost_usd_per_run
        state = WorkflowState(claude_cost_usd_this_package=ceiling - per_run + 0.01)
        allowed, note = Engine(config, state).budget_check()
        assert not allowed
        assert "another run may cost up to" in note

    def test_exactly_one_run_of_headroom_is_allowed(self, config) -> None:
        ceiling = config.limits.max_claude_cost_usd_per_work_package
        per_run = config.limits.max_claude_cost_usd_per_run
        state = WorkflowState(claude_cost_usd_this_package=ceiling - per_run)
        allowed, _ = Engine(config, state).budget_check()
        assert allowed

    def test_unknown_cost_is_disclosed_but_allowed(self, config) -> None:
        state = WorkflowState(claude_cost_unknown_runs=2)
        engine = Engine(config, state)
        allowed, note = engine.budget_check()
        assert allowed
        assert "no cost" in note and "cycle limits" in note

    def test_budget_exhaustion_escalates_and_never_approves(self, config) -> None:
        directory = config.ai_dir / "work_packages"
        directory.mkdir(parents=True, exist_ok=True)
        package = make_package(risk=Risk.HIGH)
        path = directory / f"{package.name}.json"
        save_package(path, package)
        state = WorkflowState(
            claude_cost_usd_this_package=config.limits.max_claude_cost_usd_per_work_package
        )
        state.current_work_package = package.name  # same package: budget carries over
        claude = claude_stub("APPROVED")
        engine = Engine(config, state, codex_runner=codex_stub(), claude_runner=claude)
        outcome = engine.execute(package, path)
        assert outcome.status is WorkflowStatus.HUMAN_ACTION_REQUIRED
        assert claude.calls["n"] == 0  # refused before spending
        assert outcome.commit is None
        assert outcome.audit_contract is None

    def test_correction_cycles_accumulate_cost_until_ceiling(self, config) -> None:
        """Repeated re-audits must stop at the ceiling, not loop spending."""

        directory = config.ai_dir / "work_packages"
        directory.mkdir(parents=True, exist_ok=True)
        package = make_package(risk=Risk.HIGH)
        path = directory / f"{package.name}.json"
        save_package(path, package)
        # Tighten the package ceiling so the BUDGET binds before the cycle limit;
        # otherwise the cycle cutoff would stop the loop first and this test
        # would not be exercising the budget at all.
        import dataclasses

        tight = dataclasses.replace(
            config,
            limits=dataclasses.replace(
                config.limits,
                max_claude_cost_usd_per_run=5.0,
                max_claude_cost_usd_per_work_package=8.0,
            ),
        )
        state = WorkflowState()
        claude = claude_stub("NOT_APPROVED", [BLOCKER], cost=5.0)
        engine = Engine(tight, state, codex_runner=codex_stub(), claude_runner=claude)
        outcome = engine.execute(package, path)
        assert outcome.status is WorkflowStatus.HUMAN_ACTION_REQUIRED
        assert "budget" in (outcome.human_action or "").lower()
        # One audit fits; a second cannot be afforded, so the loop stops there.
        assert claude.calls["n"] == 1
        assert state.claude_cost_usd_this_package == pytest.approx(5.0)
        assert state.claude_cost_usd_this_package <= 8.0

    def test_cost_counters_reset_on_approval(self, config) -> None:
        directory = config.ai_dir / "work_packages"
        directory.mkdir(parents=True, exist_ok=True)
        package = make_package(risk=Risk.HIGH)
        path = directory / f"{package.name}.json"
        save_package(path, package)
        state = WorkflowState()
        engine = Engine(
            config, state, codex_runner=codex_stub(), claude_runner=claude_stub()
        )
        engine.execute(package, path)
        assert state.claude_cost_usd_this_package == 0.0
        assert state.claude_cost_unknown_runs == 0


def test_orchestrator_cli_help_runs() -> None:
    result = subprocess.run(
        [sys.executable, str(TOOLS / "orchestrator.py"), "--help"],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 0
    assert "status" in result.stdout
