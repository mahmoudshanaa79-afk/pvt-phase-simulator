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
from types import SimpleNamespace

import pytest

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import orchestrator as orchestrator_cli  # noqa: E402
from orchestration import agents, prompts  # noqa: E402
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
from orchestration.verify import (  # noqa: E402
    VerificationReport,
    check_protected_artifacts,
    check_scope,
)
from orchestration.workpackage import (  # noqa: E402
    AuditPolicy,
    CommitPolicy,
    PackageStatus,
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


def provisional_stub(verdict="APPROVED", findings=(), malformed=False):
    """Fake fresh read-only Codex reviewer."""

    calls = {"n": 0}

    def runner(config, prompt_path, *, stem):
        calls["n"] += 1
        report = (
            "not structured"
            if malformed
            else (
                "Provisional review only.\n<ORCHESTRATOR_RESULT>\n"
                + json.dumps(
                    {
                        "review_type": "PROVISIONAL_CODEX_REVIEW",
                        "verdict": verdict,
                        "findings": list(findings),
                    }
                )
                + "\n</ORCHESTRATOR_RESULT>"
            )
        )
        path = config.ai_dir / "provisional_reviews" / f"{stem}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report, encoding="utf-8")
        run = agents.AgentRun(
            name="codex-provisional-review",
            command=["codex-stub", "exec", "-s", "read-only"],
            exit_code=0,
            stdout=report,
            stderr="",
            raw_report=report,
            transcript_path=path,
        )
        try:
            run.contract = agents.validate_provisional_review_contract(
                agents.parse_contract(report)
            )
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
        state = WorkflowState(
            work_packages_since_audit=3,
            audit_required=True,
            deferred_independent_audits=[{"package": "demo"}],
        )
        save_state(path, state)
        assert load_state(path).work_packages_since_audit == 3
        assert load_state(path).audit_required is True
        assert load_state(path).deferred_independent_audits == [{"package": "demo"}]

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

    def test_provisional_review_requires_truthful_type_and_bounded_verdict(
        self,
    ) -> None:
        valid = {
            "review_type": "PROVISIONAL_CODEX_REVIEW",
            "verdict": "APPROVED",
            "findings": [],
        }
        assert agents.validate_provisional_review_contract(valid) is valid
        with pytest.raises(agents.ContractError, match="provisional verdict"):
            agents.validate_provisional_review_contract(
                {**valid, "verdict": "CONDITIONAL"}
            )
        with pytest.raises(agents.ContractError, match="review_type"):
            agents.validate_provisional_review_contract(
                {**valid, "review_type": "INDEPENDENT_AUDIT"}
            )

    def test_claude_usage_limit_is_temporary_unavailability(self) -> None:
        run = agents.AgentRun(
            name="claude",
            command=["claude"],
            exit_code=1,
            stdout="",
            stderr="ERROR: You've hit your usage limit",
            raw_report="",
        )
        unavailable, reason = agents.claude_temporarily_unavailable(run)
        assert unavailable is True
        assert "usage limit" in reason

    def test_generic_claude_failure_is_not_mislabelled_as_quota(self) -> None:
        run = agents.AgentRun(
            name="claude",
            command=["claude"],
            exit_code=1,
            stdout="",
            stderr="unexpected internal error",
            raw_report="",
        )
        assert agents.claude_temporarily_unavailable(run) == (False, "")


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

    def test_any_frozen_scientific_source_path_escalates(self) -> None:
        risk, _ = assess_risk(
            Risk.LOW,
            ("src/pvt_phase_simulator/properties.py",),
            ("src/pvt_phase_simulator",),
        )
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

    def test_scope_accepts_allowed_file_inside_untracked_directory(
        self, config
    ) -> None:
        theme = config.repo / ".streamlit" / "config.toml"
        theme.parent.mkdir()
        theme.write_text('[theme]\nbase = "light"\n', encoding="utf-8")

        changed = read_repo(config.repo).dirty_paths

        assert ".streamlit/config.toml" in changed
        assert ".streamlit/" not in changed
        ok, detail = check_scope(
            config,
            changed,
            (".streamlit/config.toml",),
            ("protected.csv",),
        )
        assert ok, detail


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
        message = git(config.repo, "log", "-1", "--format=%B")
        assert "Co-Authored-By: Claude" not in message

    def test_high_risk_audits_before_finishing(self, config) -> None:
        state = WorkflowState()
        claude = claude_stub("APPROVED")
        outcome = self._run(
            config, state, make_package(risk=Risk.HIGH), codex_stub(), claude
        )
        assert claude.calls["n"] == 1
        assert outcome.status is WorkflowStatus.APPROVED
        assert state.work_packages_since_audit == 0
        assert "Co-Authored-By: Claude" in git(config.repo, "log", "-1", "--format=%B")

    def test_claude_unavailable_uses_provisional_review_and_records_debt(
        self, config
    ) -> None:
        state = WorkflowState(last_independent_audit_commit="seed-audit")
        package = make_package(
            audit_policy=AuditPolicy.IMMEDIATE,
            commit_policy=CommitPolicy.AFTER_AUDIT,
        )
        provisional = provisional_stub()
        directory = config.ai_dir / "work_packages"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "demo.json"
        save_package(path, package)
        outcome = Engine(
            config,
            state,
            codex_runner=codex_stub(),
            provisional_runner=provisional,
        ).execute(package, path)

        assert outcome.commit is not None
        assert provisional.calls["n"] == 1
        assert state.last_independent_audit_commit == "seed-audit"
        assert state.audit_required is True
        assert state.deferred_independent_audits == [
            {
                "status": "PENDING_INDEPENDENT_AUDIT",
                "package": "demo",
                "base_commit": state.deferred_independent_audits[0]["base_commit"],
                "resulting_commit": outcome.commit,
                "effective_risk": "LOW",
                "verification_report": state.deferred_independent_audits[0][
                    "verification_report"
                ],
                "provisional_review_report": state.deferred_independent_audits[0][
                    "provisional_review_report"
                ],
                "reason": (
                    "Claude unavailable; approved only by fresh read-only Codex "
                    "provisional review."
                ),
            }
        ]
        message = git(config.repo, "log", "-1", "--format=%B")
        assert "PROVISIONAL_CODEX_REVIEW" in message
        assert "Co-Authored-By: Claude" not in message

    def test_high_risk_never_uses_provisional_reviewer(self, config) -> None:
        state = WorkflowState()
        package = make_package(
            risk=Risk.HIGH,
            audit_policy=AuditPolicy.IMMEDIATE,
            commit_policy=CommitPolicy.AFTER_AUDIT,
        )
        provisional = provisional_stub()
        outcome = self._run_with_provisional(
            config, state, package, codex_stub(), provisional
        )
        assert outcome.status is WorkflowStatus.HUMAN_ACTION_REQUIRED
        assert provisional.calls["n"] == 0
        assert outcome.commit is None

    def test_installed_claude_quota_failure_falls_back_provisionally(
        self, config
    ) -> None:
        state = WorkflowState(last_independent_audit_commit="seed-audit")
        package = make_package(
            audit_policy=AuditPolicy.IMMEDIATE,
            commit_policy=CommitPolicy.AFTER_AUDIT,
        )

        def quota_stub(config, prompt_path, *, stem):
            return agents.AgentRun(
                name="claude",
                command=["claude-stub"],
                exit_code=1,
                stdout="",
                stderr="ERROR: You've hit your usage limit",
                raw_report="",
            )

        provisional = provisional_stub()
        directory = config.ai_dir / "work_packages"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "demo.json"
        save_package(path, package)
        outcome = Engine(
            config,
            state,
            codex_runner=codex_stub(),
            claude_runner=quota_stub,
            provisional_runner=provisional,
        ).execute(package, path)

        assert outcome.commit is not None
        assert provisional.calls["n"] == 1
        assert len(state.deferred_independent_audits) == 1
        assert state.last_independent_audit_commit == "seed-audit"

    def _run_with_provisional(self, config, state, package, codex, provisional):
        directory = config.ai_dir / "work_packages"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{package.name}.json"
        save_package(path, package)
        return Engine(
            config,
            state,
            codex_runner=codex,
            provisional_runner=provisional,
        ).execute(package, path)

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


class TestSubprocessEncoding:
    """Every subprocess in the package must pin UTF-8.

    A live audit crashed decoding git diff output with the platform codepage;
    this guards the whole package rather than one call site.
    """

    def test_no_call_site_omits_encoding(self) -> None:
        import re

        package = TOOLS / "orchestration"
        offenders = []
        for path in sorted(package.glob("*.py")):
            src = path.read_text(encoding="utf-8")
            for match in re.finditer(r"subprocess\.run\(", src):
                index, depth = match.end(), 1
                while index < len(src) and depth:
                    if src[index] == "(":
                        depth += 1
                    elif src[index] == ")":
                        depth -= 1
                    index += 1
                if "encoding=" not in src[match.start() : index]:
                    line = src[: match.start()].count(chr(10)) + 1
                    offenders.append(f"{path.name}:{line}")
        assert not offenders, f"subprocess.run without encoding=: {offenders}"

    def test_git_reads_non_ascii_diff(self, repo: Path) -> None:
        from orchestration.gitops import git

        (repo / "unicode.txt").write_text("lambda → 7.86 K — ✓\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "u"], cwd=repo, check=True)
        (repo / "unicode.txt").write_text("lambda → 8.00 K — ✗\n", encoding="utf-8")
        out = git(repo, "diff")
        assert out  # would raise UnicodeDecodeError under the locale codepage

    def test_clip_tolerates_missing_text(self) -> None:
        from orchestration.prompts import _clip

        assert _clip(None, 10) == "(unavailable)"
        assert _clip("", 10) == "(unavailable)"

    def test_provisional_prompt_includes_untracked_file_content(self, config) -> None:
        (config.repo / "new.py").write_text("answer = 42\n", encoding="utf-8")
        noise = config.ai_dir / "codex_reports" / "noise.md"
        noise.parent.mkdir(parents=True, exist_ok=True)
        noise.write_text("must not crowd out package diff", encoding="utf-8")
        prompt = prompts.build_provisional_review_prompt(
            config,
            make_package(allowed_files=("new.py",)),
            verification=VerificationReport(
                passed=True, changed_files=("new.py",), protected_ok=True
            ),
            base_commit=read_repo(config.repo).head,
        )
        assert "diff --git a/new.py b/new.py" in prompt
        assert "+answer = 42" in prompt
        assert "must not crowd out package diff" not in prompt
        assert "NOT an independent audit" in prompt


class TestAgentResolution:
    """Regression: a transient miss escalated a good run to HUMAN_ACTION_REQUIRED."""

    def test_transient_miss_is_retried(self, monkeypatch) -> None:
        from orchestration.config import AgentConfig

        calls = {"n": 0}

        def flaky(self):
            calls["n"] += 1
            return None if calls["n"] < 3 else "agent-exe"

        monkeypatch.setattr(AgentConfig, "resolve", flaky)
        monkeypatch.setattr(agents.time, "sleep", lambda *_: None)
        assert agents._resolve(AgentConfig(executable="x"), "Test") == "agent-exe"
        assert calls["n"] == 3

    def test_persistent_miss_still_raises_with_search_paths(self, monkeypatch) -> None:
        from orchestration.config import AgentConfig

        monkeypatch.setattr(AgentConfig, "resolve", lambda self: None)
        monkeypatch.setattr(agents.time, "sleep", lambda *_: None)
        config = AgentConfig(executable="", search_paths=("C:/nope/*/x.exe",))
        with pytest.raises(agents.AgentUnavailable) as excinfo:
            agents._resolve(config, "Test")
        message = str(excinfo.value)
        # The original failure was hard to diagnose because search_paths was
        # omitted from the message.
        assert "search_paths" in message and "C:/nope" in message
        assert "3 attempts" in message


class TestCommandResolution:
    """Regression: a live run crashed on a relative executable path."""

    def test_relative_executable_is_resolved_against_repo(self, config) -> None:
        from orchestration.verify import _resolve_command

        target = config.repo / "bin" / "tool.exe"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("", encoding="utf-8")
        resolved = _resolve_command(config, ("bin/tool.exe", "-m", "x"))
        assert Path(resolved[0]).is_absolute()
        assert Path(resolved[0]) == target
        assert resolved[1:] == ["-m", "x"]

    def test_absolute_and_bare_names_are_left_alone(self, config) -> None:
        from orchestration.verify import _resolve_command

        assert _resolve_command(config, ("git", "status")) == ["git", "status"]
        absolute = str(Path(sys.executable))
        assert _resolve_command(config, (absolute, "-c", "pass"))[0] == absolute

    def test_missing_executable_fails_gracefully(self, config) -> None:
        """A bad command must fail the gate, not crash the orchestrator."""

        from orchestration.verify import run_command

        result = run_command(config, ("definitely-not-a-real-binary-xyz",))
        assert result.exit_code == 127
        assert not result.ok
        assert "could not execute" in result.stderr


class TestTransportEncoding:
    """Regression: a live run failed because Windows encoded stdin as cp1252."""

    @pytest.mark.parametrize("runner", ["codex", "claude"])
    def test_agent_stdin_is_utf8(self, config, monkeypatch, runner) -> None:
        captured: dict[str, object] = {}

        class FakeCompleted:
            returncode = 0
            stdout = '{"result": "ok"}'
            stderr = ""

        def fake_run(command, **kwargs):
            captured.update(kwargs)
            return FakeCompleted()

        monkeypatch.setattr(agents.subprocess, "run", fake_run)
        monkeypatch.setattr(agents, "_resolve", lambda agent, name: "agent-exe")
        # Non-ASCII is what broke the real run: em dash, arrow, Greek.
        prompt = config.repo / "p.md"
        prompt.write_text("audit — λ → C, 7.86 K", encoding="utf-8")
        if runner == "codex":
            agents.run_codex(config, prompt, stem="enc")
        else:
            agents.run_claude_audit(config, prompt, stem="enc")
        assert captured.get("encoding") == "utf-8", (
            "subprocess stdin must be pinned to UTF-8; the platform locale "
            "codepage corrupts non-ASCII prompt text"
        )

    def test_provisional_reviewer_uses_read_only_sandbox(
        self, config, monkeypatch
    ) -> None:
        captured: dict[str, object] = {}

        class FakeCompleted:
            returncode = 0
            stdout = (
                '<ORCHESTRATOR_RESULT>{"review_type":'
                '"PROVISIONAL_CODEX_REVIEW","verdict":"APPROVED",'
                '"findings":[]}</ORCHESTRATOR_RESULT>'
            )
            stderr = ""

        def fake_run(command, **kwargs):
            captured["command"] = command
            captured.update(kwargs)
            return FakeCompleted()

        monkeypatch.setattr(agents.subprocess, "run", fake_run)
        monkeypatch.setattr(agents, "_resolve", lambda agent, name: "codex-exe")
        prompt = config.repo / "review.md"
        prompt.write_text("review", encoding="utf-8")
        agents.run_codex_review(config, prompt, stem="readonly")
        command = captured["command"]
        assert isinstance(command, list)
        assert command[command.index("-s") + 1] == "read-only"
        assert captured.get("encoding") == "utf-8"


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
    assert "autopilot" in result.stdout
    assert "release-audit" in result.stdout


class TestAutopilotCli:
    def test_autopilot_runs_each_eligible_package_then_requests_release_audit(
        self, config, monkeypatch, capsys
    ) -> None:
        directory = config.ai_dir / "work_packages"
        directory.mkdir(parents=True, exist_ok=True)
        first = make_package(name="a")
        second = make_package(name="b", dependencies=("a",))
        save_package(directory / "a.json", first)
        save_package(directory / "b.json", second)
        calls: list[str] = []

        class FakeEngine:
            def __init__(self, config, state):
                self.state = state

            def execute(self, package, path):
                calls.append(package.name)
                package.status = PackageStatus.COMMITTED
                save_package(path, package)
                return SimpleNamespace(
                    status=WorkflowStatus.IDLE,
                    messages=[f"completed {package.name}"],
                    commit=f"commit-{package.name}",
                )

        monkeypatch.setattr(orchestrator_cli, "Engine", FakeEngine)
        code = orchestrator_cli.cmd_autopilot(config, SimpleNamespace())
        state = load_state(config.state_path)
        assert code == 0
        assert calls == ["a", "b"]
        assert state.workflow_status is WorkflowStatus.READY_FOR_CLAUDE_RELEASE_AUDIT
        assert "python tools/orchestrator.py release-audit" in capsys.readouterr().out

    def test_autopilot_refuses_a_no_progress_loop(self, config, monkeypatch) -> None:
        directory = config.ai_dir / "work_packages"
        directory.mkdir(parents=True, exist_ok=True)
        save_package(directory / "demo.json", make_package())

        class NoProgressEngine:
            def __init__(self, config, state):
                pass

            def execute(self, package, path):
                return SimpleNamespace(
                    status=WorkflowStatus.IDLE, messages=[], commit=None
                )

        monkeypatch.setattr(orchestrator_cli, "Engine", NoProgressEngine)
        assert orchestrator_cli.cmd_autopilot(config, SimpleNamespace()) == 2
        state = load_state(config.state_path)
        assert state.workflow_status is WorkflowStatus.HUMAN_ACTION_REQUIRED
        assert "forward progress" in (state.last_error or "")

    def test_release_audit_unavailable_preserves_debt_and_resume_command(
        self, config, capsys
    ) -> None:
        state = WorkflowState(
            deferred_independent_audits=[{"package": "demo"}],
            audit_required=True,
        )
        save_state(config.state_path, state)
        assert orchestrator_cli.cmd_release_audit(config, SimpleNamespace()) == 2
        reloaded = load_state(config.state_path)
        assert reloaded.deferred_independent_audits == [{"package": "demo"}]
        assert reloaded.workflow_status is WorkflowStatus.READY_FOR_CLAUDE_RELEASE_AUDIT
        assert "python tools/orchestrator.py release-audit" in capsys.readouterr().out
