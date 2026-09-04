"""Tests for stage-aware resume: what may be skipped, and what must refuse.

Every agent boundary is mocked. These never spend a real Codex or Claude call.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

from orchestration import auditdebt, roles  # noqa: E402
from orchestration import resume as resume_mod  # noqa: E402
from orchestration.config import (  # noqa: E402
    AgentConfig,
    Limits,
    OrchestratorConfig,
)
from orchestration.engine import Engine  # noqa: E402
from orchestration.gitops import read_repo  # noqa: E402
from orchestration.roles import AgentIdentity  # noqa: E402
from orchestration.state import (  # noqa: E402
    Stage,
    WorkflowState,
    WorkflowStatus,
)
from orchestration.workpackage import (  # noqa: E402
    AuditPolicy,
    CommitPolicy,
    Risk,
    WorkPackage,
)
from test_orchestrator_v2 import builder_stub  # noqa: E402

# --------------------------------------------------------------------- fixtures


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"], cwd=root, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    (root / "protected.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=root, check=True)
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
        release_goal="v1.2",
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


def prepare(
    repo: Path,
    *,
    completed: Stage,
    verification: str | None = "passed",
    dirty: bool = True,
    **overrides: object,
) -> WorkflowState:
    """A state that looks like a run interrupted at a given stage."""

    facts = read_repo(repo)
    state = WorkflowState()
    state.current_work_package = "demo"
    state.builder = "codex"
    state.reviewer = "claude"
    state.base_commit = facts.head
    state.last_completed_stage = completed.value
    state.verification_status = verification
    state.workflow_status = WorkflowStatus.LOCAL_VERIFY
    for key, value in overrides.items():
        setattr(state, key, value)
    if dirty:
        (repo / "work.txt").write_text("built earlier\n", encoding="utf-8")
    if verification == "passed" and "tree_fingerprint" not in overrides:
        # A passed verification is only reusable together with the fingerprint
        # of the tree it described, so a realistic state carries both.
        from orchestration.evidence import tree_fingerprint

        state.tree_fingerprint = tree_fingerprint(
            _fingerprint_config(repo), make_package(), base_commit=state.base_commit
        )
    return state


def _fingerprint_config(repo: Path):
    """A minimal config for fingerprinting; only ``repo`` is consulted."""

    from orchestration.config import AgentConfig, Limits, OrchestratorConfig

    return OrchestratorConfig(
        repo=repo,
        ai_dir=repo / ".ai",
        codex=AgentConfig(executable="codex-stub"),
        claude=AgentConfig(executable="claude-stub"),
        limits=Limits(),
        verification_commands=(),
        fast_verification_commands=(),
        protected_artifacts={},
        protected_paths=(),
        high_risk_paths=(),
    )


def plan_for(config, repo, state, package=None):
    return resume_mod.plan(
        config,
        state,
        package or make_package(),
        read_repo(repo),
        roles.availability_map(config),
    )


# ------------------------------------------------------------------- planning


class TestResumePlanning:
    def test_build_complete_resumes_at_verify(self, config, repo) -> None:
        state = prepare(repo, completed=Stage.BUILT, verification=None)
        plan = plan_for(config, repo, state)
        assert plan.skip_build
        assert not plan.skip_verification
        assert not plan.skip_audit
        assert plan.first_stage_to_run == "verify"

    def test_verify_complete_resumes_at_audit(self, config, repo) -> None:
        state = prepare(repo, completed=Stage.VERIFIED)
        plan = plan_for(config, repo, state)
        assert plan.skips(Stage.BUILT)
        assert plan.skips(Stage.VERIFIED)
        assert not plan.skips(Stage.AUDITED)
        assert plan.first_stage_to_run == "audit"

    def test_audit_complete_resumes_at_commit(self, config, repo) -> None:
        state = prepare(repo, completed=Stage.AUDITED)
        plan = plan_for(config, repo, state)
        assert plan.skips(Stage.BUILT)
        assert plan.skips(Stage.VERIFIED)
        assert plan.skips(Stage.AUDITED)
        assert plan.first_stage_to_run == "commit"

    def test_committed_package_has_nothing_to_do(self, config, repo) -> None:
        facts = read_repo(repo)
        state = prepare(
            repo,
            completed=Stage.COMMITTED,
            dirty=False,
            resulting_commit=facts.head,
        )
        plan = plan_for(config, repo, state)
        assert plan.nothing_to_do
        assert plan.first_stage_to_run == "none"

    def test_interrupted_build_reruns_only_the_build(self, config, repo) -> None:
        state = prepare(repo, completed=Stage.PLANNED, verification=None, dirty=False)
        plan = plan_for(config, repo, state)
        assert not plan.skip_build
        assert plan.first_stage_to_run == "build"

    def test_interrupted_verification_does_not_rebuild(self, config, repo) -> None:
        """A verification still running when the process died is not complete."""

        state = prepare(repo, completed=Stage.BUILT, verification="running")
        plan = plan_for(config, repo, state)
        assert plan.skip_build
        assert not plan.skip_verification
        assert plan.first_stage_to_run == "verify"

    def test_a_failed_verification_is_rerun_not_skipped(self, config, repo) -> None:
        state = prepare(repo, completed=Stage.VERIFIED, verification="failed")
        plan = plan_for(config, repo, state)
        assert plan.skips(Stage.BUILT)
        assert not plan.skips(Stage.VERIFIED)
        assert Stage.VERIFIED in plan.must_rerun
        assert "failed" in plan.reason

    def test_recorded_roles_are_carried_and_stay_independent(
        self, config, repo
    ) -> None:
        state = prepare(repo, completed=Stage.VERIFIED)
        plan = plan_for(config, repo, state)
        assert plan.builder is AgentIdentity.CODEX
        assert plan.reviewer_required is AgentIdentity.CLAUDE
        roles.assert_independent(plan.builder, plan.reviewer_required)

    def test_a_claude_built_package_requires_codex_to_review(
        self, config, repo
    ) -> None:
        state = prepare(repo, completed=Stage.VERIFIED, builder="claude")
        plan = plan_for(config, repo, state)
        assert plan.builder is AgentIdentity.CLAUDE
        assert plan.reviewer_required is AgentIdentity.CODEX
        roles.assert_independent(plan.builder, plan.reviewer_required)

    def test_builder_report_is_recovered_from_disk(self, config, repo) -> None:
        report = config.subdir("codex_reports") / "earlier.md"
        report.write_text("earlier builder report\n", encoding="utf-8")
        state = prepare(repo, completed=Stage.VERIFIED, builder_report_path=str(report))
        assert "earlier builder report" in plan_for(config, repo, state).builder_report

    def test_a_missing_report_does_not_break_planning(self, config, repo) -> None:
        state = prepare(
            repo,
            completed=Stage.VERIFIED,
            builder_report_path=str(repo / "gone.md"),
        )
        assert plan_for(config, repo, state).builder_report == ""

    def test_describe_names_what_is_skipped(self, config, repo) -> None:
        state = prepare(repo, completed=Stage.VERIFIED)
        text = plan_for(config, repo, state).describe()
        assert "skipping" in text
        assert "build" in text
        assert "reusing" in text


# ------------------------------------------------------------------- refusal


class TestResumeRefusal:
    def test_a_different_package_is_refused(self, config, repo) -> None:
        state = prepare(repo, completed=Stage.VERIFIED)
        state.current_work_package = "something_else"
        with pytest.raises(resume_mod.ResumeRefused, match="refusing to mix"):
            plan_for(config, repo, state)

    def test_a_moved_head_is_refused(self, config, repo) -> None:
        state = prepare(repo, completed=Stage.VERIFIED)
        state.base_commit = "0" * 40
        with pytest.raises(resume_mod.ResumeRefused, match="no longer describe"):
            plan_for(config, repo, state)

    def test_a_mismatched_resulting_commit_is_refused(self, config, repo) -> None:
        state = prepare(repo, completed=Stage.COMMITTED, dirty=False)
        state.resulting_commit = "1" * 40
        with pytest.raises(resume_mod.ResumeRefused, match="but HEAD is"):
            plan_for(config, repo, state)

    def test_a_completed_build_with_a_clean_tree_is_refused(self, config, repo) -> None:
        state = prepare(repo, completed=Stage.BUILT, dirty=False)
        with pytest.raises(resume_mod.ResumeRefused, match="not present"):
            plan_for(config, repo, state)

    def test_tampered_protected_science_is_refused(self, config, repo) -> None:
        state = prepare(repo, completed=Stage.VERIFIED)
        (repo / "protected.csv").write_text("tampered\n", encoding="utf-8")
        with pytest.raises(resume_mod.ResumeRefused, match="protected artifacts"):
            plan_for(config, repo, state)

    def test_an_unknown_stage_is_refused(self, config, repo) -> None:
        state = prepare(repo, completed=Stage.VERIFIED)
        state.last_completed_stage = "teleported"
        with pytest.raises(resume_mod.ResumeRefused, match="not a known stage"):
            plan_for(config, repo, state)

    def test_completed_stages_without_a_boundary_are_refused(
        self, config, repo
    ) -> None:
        state = prepare(repo, completed=Stage.BUILT)
        state.base_commit = None
        with pytest.raises(resume_mod.ResumeRefused, match="nothing to anchor"):
            plan_for(config, repo, state)

    def test_no_recorded_package_is_refused(self, config, repo) -> None:
        state = prepare(repo, completed=Stage.VERIFIED)
        state.current_work_package = None
        with pytest.raises(resume_mod.ResumeRefused, match="no work package"):
            plan_for(config, repo, state)

    def test_a_committed_stage_without_its_commit_is_refused(
        self, config, repo
    ) -> None:
        state = prepare(repo, completed=Stage.COMMITTED, dirty=False)
        state.resulting_commit = None
        with pytest.raises(resume_mod.ResumeRefused, match="without recording"):
            plan_for(config, repo, state)


# ------------------------------------------------------------------- gating


class TestResumeGating:
    def test_an_idle_workflow_is_not_resumable(self) -> None:
        allowed, why = resume_mod.resumable(WorkflowState(), "demo")
        assert not allowed
        assert "use `run`" in why

    def test_an_interrupted_workflow_is_resumable(self) -> None:
        state = WorkflowState()
        state.workflow_status = WorkflowStatus.LOCAL_VERIFY
        allowed, _ = resume_mod.resumable(state, "demo")
        assert allowed

    def test_a_human_block_is_not_resumable(self) -> None:
        state = WorkflowState()
        state.workflow_status = WorkflowStatus.HUMAN_ACTION_REQUIRED
        state.last_error = "something went wrong"
        allowed, why = resume_mod.resumable(state, "demo")
        assert not allowed
        assert "blocked for a human" in why

    def test_a_deferred_audit_block_resumes_for_the_reviewer(self) -> None:
        state = WorkflowState()
        state.workflow_status = WorkflowStatus.HUMAN_ACTION_REQUIRED
        debts: list[auditdebt.AuditDebt] = []
        auditdebt.record(
            debts,
            package="demo",
            resulting_commit="abc123abc123",
            builder="claude",
            reviewer_required="codex",
            reason="codex unavailable",
        )
        state.deferred_independent_audits = auditdebt.dump(debts)
        allowed, why = resume_mod.resumable(state, "demo")
        assert allowed
        assert "codex" in why

    def test_a_cleared_debt_no_longer_unblocks_a_human_stop(self) -> None:
        state = WorkflowState()
        state.workflow_status = WorkflowStatus.HUMAN_ACTION_REQUIRED
        state.last_error = "blocked"
        debts: list[auditdebt.AuditDebt] = []
        debt = auditdebt.record(
            debts,
            package="demo",
            resulting_commit="abc123abc123",
            builder="claude",
            reviewer_required="codex",
            reason="codex unavailable",
        )
        auditdebt.reconcile(
            debts, identifier=debt.id, reviewer="codex", evidence="APPROVED"
        )
        state.deferred_independent_audits = auditdebt.dump(debts)
        allowed, _ = resume_mod.resumable(state, "demo")
        assert not allowed

    def test_another_packages_debt_does_not_unblock_this_one(self) -> None:
        state = WorkflowState()
        state.workflow_status = WorkflowStatus.HUMAN_ACTION_REQUIRED
        state.last_error = "blocked"
        debts: list[auditdebt.AuditDebt] = []
        auditdebt.record(
            debts,
            package="other",
            resulting_commit="abc123abc123",
            builder="claude",
            reviewer_required="codex",
            reason="codex unavailable",
        )
        state.deferred_independent_audits = auditdebt.dump(debts)
        allowed, _ = resume_mod.resumable(state, "demo")
        assert not allowed


# ----------------------------------------------------------------- execution


class TestResumeExecution:
    def _engine(self, config, state, calls):
        return Engine(
            config,
            state,
            codex_runner=builder_stub("codex", calls=calls),
            claude_runner=lambda *a, **k: None,
        )

    def _path(self, config) -> Path:
        return config.subdir("work_packages") / "demo.json"

    def test_resuming_from_built_does_not_invoke_the_builder(
        self, config, repo
    ) -> None:
        calls: list[str] = []
        state = prepare(repo, completed=Stage.BUILT, verification=None)
        engine = self._engine(config, state, calls)
        engine.execute(
            make_package(audit_policy=AuditPolicy.NONE),
            self._path(config),
            resume_from=Stage.BUILT,
        )
        assert calls == []

    def test_resuming_from_verified_skips_the_gates(self, config, repo) -> None:
        calls: list[str] = []
        gate_runs: list[str] = []
        state = prepare(repo, completed=Stage.VERIFIED)
        engine = self._engine(config, state, calls)
        original = engine.run_verification

        def spy(package, outcome):
            gate_runs.append(package.name)
            return original(package, outcome)

        engine.run_verification = spy  # type: ignore[method-assign]
        engine.execute(
            make_package(audit_policy=AuditPolicy.NONE),
            self._path(config),
            resume_from=Stage.VERIFIED,
        )
        assert calls == []
        assert gate_runs == []

    def test_a_fresh_run_still_builds_and_verifies(self, config, repo) -> None:
        calls: list[str] = []
        state = WorkflowState()
        engine = self._engine(config, state, calls)
        engine.execute(make_package(audit_policy=AuditPolicy.NONE), self._path(config))
        assert calls == ["codex"]
        assert state.verification_status == "passed"

    def test_reconstructed_verification_rechecks_protected_artifacts(
        self, config, repo
    ) -> None:
        state = prepare(repo, completed=Stage.VERIFIED)
        engine = self._engine(config, state, [])
        report = engine.reconstruct_verification(make_package())
        assert report.passed and report.protected_ok

        (repo / "protected.csv").write_text("tampered\n", encoding="utf-8")
        tampered = engine.reconstruct_verification(make_package())
        assert not tampered.passed
        assert not tampered.protected_ok

    def test_the_resumed_builder_report_reaches_downstream_stages(
        self, config, repo
    ) -> None:
        state = prepare(repo, completed=Stage.BUILT, verification=None)
        engine = self._engine(config, state, [])
        outcome = engine.execute(
            make_package(audit_policy=AuditPolicy.NONE),
            self._path(config),
            resume_from=Stage.BUILT,
            builder_report="report recovered from disk",
        )
        assert any("skipping build" in message for message in outcome.messages)

    def test_resume_does_not_commit_a_second_time(self, config, repo) -> None:
        """A committed package is complete; a further resume must be a no-op."""

        calls: list[str] = []
        state = WorkflowState()
        engine = self._engine(config, state, calls)
        package = make_package(audit_policy=AuditPolicy.NONE)
        first = engine.execute(package, self._path(config))
        assert first.commit is not None
        head_after_first = read_repo(repo).head
        counted = state.work_packages_since_audit

        state.workflow_status = WorkflowStatus.LOCAL_VERIFY
        plan = plan_for(config, repo, state, package)
        assert plan.nothing_to_do
        assert read_repo(repo).head == head_after_first
        assert state.work_packages_since_audit == counted
        assert calls == ["codex"]

    def test_a_fresh_run_resets_the_recorded_boundary(self, config, repo) -> None:
        """Starting a package over must not inherit the previous boundary."""

        state = prepare(repo, completed=Stage.AUDITED, resulting_commit="1" * 40)
        engine = self._engine(config, state, [])
        engine.execute(make_package(audit_policy=AuditPolicy.NONE), self._path(config))
        assert state.resulting_commit != "1" * 40
        assert state.base_commit is not None
