"""End-to-end tests for the five Orchestrator v2 release blockers.

These prove behaviour, not planner return values: each one drives the engine and
asserts what actually ran, what was committed, and what was recorded.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import orchestrator as orchestrator_cli  # noqa: E402
from orchestration import agents, auditdebt, evidence, roles  # noqa: E402
from orchestration import resume as resume_mod  # noqa: E402
from orchestration.config import (  # noqa: E402
    AgentConfig,
    Limits,
    OrchestratorConfig,
)
from orchestration.engine import Engine, StepOutcome  # noqa: E402
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


def package_path(config) -> Path:
    return config.subdir("work_packages") / "demo.json"


def plan_for(config, repo, state, package=None):
    return resume_mod.plan(
        config,
        state,
        package or make_package(),
        read_repo(repo),
        roles.availability_map(config),
    )


def attach_builder_evidence(config, state, *, builder: str = "codex") -> Path:
    """Give a state the builder evidence a real interrupted run would have."""

    report = config.subdir("codex_reports") / "earlier-report.md"
    report.write_text("earlier builder report\n", encoding="utf-8")
    state.builder_report_path = str(report)
    state.builder_evidence = evidence.record_builder_evidence(
        builder=builder,
        package=state.current_work_package or "demo",
        workflow_id=state.workflow_id,
        report_path=report,
    ).to_dict()
    return report


def audit_stub(verdict: str = "APPROVED", *, calls: list[str] | None = None):
    """A reviewer that returns a valid auditor contract."""

    import json as _json

    def runner(config, prompt, *, stem, **kwargs):
        if calls is not None:
            calls.append("audit")
        body = (
            "<ORCHESTRATOR_RESULT>\n"
            + _json.dumps({"verdict": verdict, "findings": []})
            + "\n</ORCHESTRATOR_RESULT>\n"
        )
        run = agents.AgentRun(
            name="reviewer",
            command=[],
            exit_code=0,
            stdout=body,
            stderr="",
            raw_report=body,
        )
        run.contract = agents.validate_audit_contract(agents.parse_contract(body))
        return run

    return runner


# =============================================================== P1-1


class TestPlanSurvivesIntoExecution:
    """The executor must obey the plan, not re-derive skipping from a stage."""

    def _state_verified_without_fingerprint(self, repo) -> WorkflowState:
        facts = read_repo(repo)
        state = WorkflowState()
        state.current_work_package = "demo"
        state.builder = "codex"
        state.base_commit = facts.head
        state.last_completed_stage = Stage.VERIFIED.value
        state.verification_status = "passed"
        state.tree_fingerprint = None  # evidence cannot be trusted
        state.workflow_status = WorkflowStatus.LOCAL_VERIFY
        (repo / "work.txt").write_text("built earlier\n", encoding="utf-8")
        return state

    def _with_evidence(self, config, repo) -> WorkflowState:
        """As above, but carrying the builder evidence a real run would have."""

        state = self._state_verified_without_fingerprint(repo)
        attach_builder_evidence(config, state)
        return state

    def test_plan_requires_verification_rerun_when_evidence_is_untrusted(
        self, config, repo
    ) -> None:
        plan = plan_for(config, repo, self._state_verified_without_fingerprint(repo))
        assert Stage.VERIFIED in plan.must_rerun
        assert not plan.skips(Stage.VERIFIED)
        assert plan.first_stage_to_run == "verify"

    def test_executor_obeys_must_rerun_instead_of_the_stage_marker(
        self, config, repo
    ) -> None:
        """The defect: passing only `completed` skipped a verification the
        planner had explicitly required to run again."""

        state = self._with_evidence(config, repo)
        plan = plan_for(config, repo, state)
        gate_runs: list[str] = []
        engine = Engine(
            config,
            state,
            codex_runner=builder_stub("codex"),
            claude_runner=lambda *a, **k: None,
        )
        original = engine.run_verification

        def spy(package, outcome):
            gate_runs.append(package.name)
            return original(package, outcome)

        engine.run_verification = spy  # type: ignore[method-assign]
        engine.execute(
            make_package(audit_policy=AuditPolicy.NONE),
            package_path(config),
            resume_plan=plan,
        )
        assert gate_runs == ["demo"], "verification must rerun when the plan says so"

    def test_the_stage_only_path_can_no_longer_skip_anything(
        self, config, repo
    ) -> None:
        """Only a plan may authorise skipping; `resume_from` alone must not."""

        state = self._with_evidence(config, repo)
        gate_runs: list[str] = []
        engine = Engine(
            config,
            state,
            codex_runner=builder_stub("codex"),
            claude_runner=lambda *a, **k: None,
        )
        original = engine.run_verification

        def spy(package, outcome):
            gate_runs.append(package.name)
            return original(package, outcome)

        engine.run_verification = spy  # type: ignore[method-assign]
        engine.execute(
            make_package(audit_policy=AuditPolicy.NONE),
            package_path(config),
            resume_from=Stage.VERIFIED,
        )
        assert gate_runs == ["demo"], (
            "without a plan nothing may be skipped, so verification must run"
        )

    def test_plan_reports_the_evidence_it_reuses(self, config, repo) -> None:
        state = self._state_verified_without_fingerprint(repo)
        state.tree_fingerprint = evidence.tree_fingerprint(
            config, make_package(), base_commit=state.base_commit
        )
        plan = plan_for(config, repo, state)
        assert "verification" in plan.reused_evidence
        assert "builder report" in plan.reused_evidence


# =============================================================== P1-2


class TestTreeFingerprint:
    def _verified_state(self, config, repo) -> WorkflowState:
        state = WorkflowState()
        state.current_work_package = "demo"
        state.builder = "codex"
        state.base_commit = read_repo(repo).head
        state.last_completed_stage = Stage.VERIFIED.value
        state.verification_status = "passed"
        state.workflow_status = WorkflowStatus.LOCAL_VERIFY
        (repo / "work.txt").write_text("built earlier\n", encoding="utf-8")
        state.tree_fingerprint = evidence.tree_fingerprint(
            config, make_package(), base_commit=state.base_commit
        )
        return state

    def test_fingerprint_covers_contents_not_only_names(self, config, repo) -> None:
        (repo / "work.txt").write_text("one\n", encoding="utf-8")
        first = evidence.tree_fingerprint(config, make_package())
        (repo / "work.txt").write_text("two\n", encoding="utf-8")
        assert evidence.tree_fingerprint(config, make_package()) != first

    def test_fingerprint_is_stable_for_an_unchanged_tree(self, config, repo) -> None:
        (repo / "work.txt").write_text("one\n", encoding="utf-8")
        assert evidence.tree_fingerprint(config, make_package()) == (
            evidence.tree_fingerprint(config, make_package())
        )

    def test_fingerprint_covers_untracked_files(self, config, repo) -> None:
        first = evidence.tree_fingerprint(config, make_package())
        (repo / "brand_new.txt").write_text("new\n", encoding="utf-8")
        assert evidence.tree_fingerprint(config, make_package()) != first

    def test_fingerprint_includes_the_base_commit(self, config, repo) -> None:
        a = evidence.tree_fingerprint(config, make_package(), base_commit="aaa")
        b = evidence.tree_fingerprint(config, make_package(), base_commit="bbb")
        assert a != b

    def test_evidence_is_valid_for_the_tree_it_described(self, config, repo) -> None:
        state = self._verified_state(config, repo)
        ok, reason = resume_mod.verification_evidence_valid(
            config, state, make_package()
        )
        assert ok, reason

    def test_a_changed_file_at_the_same_head_invalidates_evidence(
        self, config, repo
    ) -> None:
        """The mutation the blocker describes: same HEAD, different content."""

        state = self._verified_state(config, repo)
        before = read_repo(repo).head
        (repo / "work.txt").write_text("edited after verification\n", encoding="utf-8")
        assert read_repo(repo).head == before, "HEAD must be unchanged for this test"

        ok, reason = resume_mod.verification_evidence_valid(
            config, state, make_package()
        )
        assert not ok
        assert "working tree changed" in reason

    def test_resume_refuses_to_reuse_stale_verification(self, config, repo) -> None:
        state = self._verified_state(config, repo)
        (repo / "work.txt").write_text("edited after verification\n", encoding="utf-8")
        plan = plan_for(config, repo, state)
        assert Stage.VERIFIED in plan.must_rerun
        assert not plan.skips(Stage.VERIFIED)

    def test_a_stale_tree_also_invalidates_the_audit(self, config, repo) -> None:
        state = self._verified_state(config, repo)
        state.last_completed_stage = Stage.AUDITED.value
        (repo / "work.txt").write_text("edited after the audit\n", encoding="utf-8")
        plan = plan_for(config, repo, state)
        assert Stage.AUDITED in plan.must_rerun
        assert not plan.skips(Stage.AUDITED)

    def test_missing_fingerprint_is_never_trusted(self, config, repo) -> None:
        state = self._verified_state(config, repo)
        state.tree_fingerprint = None
        ok, reason = resume_mod.verification_evidence_valid(
            config, state, make_package()
        )
        assert not ok
        assert "no working-tree fingerprint" in reason

    def test_protected_hashes_remain_a_separate_layer(self, config, repo) -> None:
        """A protected-artifact change is caught even if the fingerprint agrees."""

        state = self._verified_state(config, repo)
        (repo / "protected.csv").write_text("tampered\n", encoding="utf-8")
        with pytest.raises(resume_mod.ResumeRefused, match="protected artifacts"):
            plan_for(config, repo, state)

    def test_verification_records_a_fingerprint(self, config, repo) -> None:
        state = WorkflowState()
        engine = Engine(
            config,
            state,
            codex_runner=builder_stub("codex"),
            claude_runner=lambda *a, **k: None,
        )
        engine.execute(
            make_package(audit_policy=AuditPolicy.NONE), package_path(config)
        )
        assert state.tree_fingerprint


# =============================================================== P1-3


class TestCorrectionOwnership:
    def test_the_current_author_is_the_latest_revision(self, config) -> None:
        state = WorkflowState()
        state.builder = "claude"
        engine = Engine(config, state, claude_runner=lambda *a, **k: None)
        engine._record_revision(AgentIdentity.CLAUDE, "build")
        assert engine.current_author() is AgentIdentity.CLAUDE
        engine._record_revision(AgentIdentity.CODEX, "correction")
        assert engine.current_author() is AgentIdentity.CODEX

    def test_codex_correcting_claude_work_requires_claude_to_reaudit(
        self, config, repo
    ) -> None:
        """Claude builds, Codex reviews, Codex corrects, Claude must re-audit."""

        state = WorkflowState()
        engine = Engine(
            config,
            state,
            codex_runner=builder_stub("codex"),
            claude_runner=lambda *a, **k: None,
        )
        engine._record_revision(AgentIdentity.CLAUDE, "build")
        engine._record_revision(AgentIdentity.CODEX, "correction")

        from orchestration.verify import VerificationReport

        report = VerificationReport(
            passed=True, protected_ok=True, scope_ok=True, changed_files=()
        )
        mode, reason = engine.review_mode(
            make_package(), Risk.LOW, report, needs_audit=True
        )
        assert mode == "claude", reason
        assert "claude" in reason

    def test_claude_correcting_codex_work_requires_codex_to_reaudit(
        self, config, repo
    ) -> None:
        state = WorkflowState()
        engine = Engine(
            config,
            state,
            codex_runner=builder_stub("codex"),
            claude_runner=lambda *a, **k: None,
        )
        engine._record_revision(AgentIdentity.CODEX, "build")
        engine._record_revision(AgentIdentity.CLAUDE, "correction")

        from orchestration.verify import VerificationReport

        report = VerificationReport(
            passed=True, protected_ok=True, scope_ok=True, changed_files=()
        )
        mode, reason = engine.review_mode(
            make_package(), Risk.LOW, report, needs_audit=True
        )
        assert mode == "codex_audit", reason
        assert "codex" in reason

    def test_a_correction_author_can_never_review_itself(self, config) -> None:
        for author in AgentIdentity:
            state = WorkflowState()
            engine = Engine(config, state, claude_runner=lambda *a, **k: None)
            engine._record_revision(author, "correction")
            reviewer = roles.COUNTERPART[engine.current_author()]
            assert reviewer != author
            roles.assert_independent(engine.current_author(), reviewer)

    def test_a_build_resets_the_revision_history(self, config, repo) -> None:
        state = WorkflowState()
        state.revisions = [{"author": "claude", "kind": "correction"}]
        engine = Engine(
            config,
            state,
            codex_runner=builder_stub("codex"),
            claude_runner=lambda *a, **k: None,
        )
        engine.run_builder(make_package())
        assert [entry["kind"] for entry in state.revisions] == ["build"]
        assert engine.current_author() is AgentIdentity.CODEX

    def test_ownership_falls_back_to_the_builder_without_revisions(
        self, config
    ) -> None:
        state = WorkflowState()
        state.builder = "claude"
        engine = Engine(config, state, claude_runner=lambda *a, **k: None)
        assert engine.current_author() is AgentIdentity.CLAUDE


# =============================================================== P1-4


class TestAuditDebtCloses:
    def _committed_with_debt(self, config, repo) -> WorkflowState:
        """A package already committed, still owing an independent review."""

        (repo / "work.txt").write_text("shipped\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "package"], cwd=repo, check=True)
        head = read_repo(repo).head

        state = WorkflowState()
        state.current_work_package = "demo"
        state.builder = "claude"
        state.reviewer = "codex"
        state.revisions = [{"author": "claude", "kind": "build"}]
        state.base_commit = head
        state.resulting_commit = head
        state.last_completed_stage = Stage.COMMITTED.value
        state.verification_status = "passed"
        state.workflow_status = WorkflowStatus.HUMAN_ACTION_REQUIRED
        debts: list[auditdebt.AuditDebt] = []
        auditdebt.record(
            debts,
            package="demo",
            resulting_commit=head,
            builder="claude",
            reviewer_required="codex",
            reason="codex unavailable at the time",
        )
        state.deferred_independent_audits = auditdebt.dump(debts)
        return state

    def test_a_committed_package_with_debt_is_not_nothing_to_do(
        self, config, repo
    ) -> None:
        state = self._committed_with_debt(config, repo)
        plan = plan_for(config, repo, state)
        assert not plan.nothing_to_do
        assert plan.review_only
        assert plan.first_stage_to_run == "review"

    def test_the_returning_reviewer_clears_the_exact_debt(self, config, repo) -> None:
        state = self._committed_with_debt(config, repo)
        head_before = read_repo(repo).head
        counted = state.work_packages_since_audit

        engine = Engine(
            config,
            state,
            codex_auditor_runner=audit_stub("APPROVED"),
            codex_runner=builder_stub("codex"),
            claude_runner=lambda *a, **k: None,
        )
        outcome = engine.review_only(make_package(), package_path(config))

        assert outcome.status is WorkflowStatus.APPROVED
        remaining = auditdebt.open_debts(
            auditdebt.load(state.deferred_independent_audits)
        )
        assert remaining == []
        assert read_repo(repo).head == head_before, "must not recommit"
        assert state.work_packages_since_audit == counted, "must not recount"

    def test_the_cleared_debt_records_reviewer_and_evidence(self, config, repo) -> None:
        state = self._committed_with_debt(config, repo)
        engine = Engine(
            config,
            state,
            codex_auditor_runner=audit_stub("APPROVED"),
            codex_runner=builder_stub("codex"),
            claude_runner=lambda *a, **k: None,
        )
        engine.review_only(make_package(), package_path(config))
        debts = auditdebt.load(state.deferred_independent_audits)
        assert debts[0].cleared_by == "codex"
        assert debts[0].evidence

    def test_a_second_review_does_nothing(self, config, repo) -> None:
        state = self._committed_with_debt(config, repo)
        engine = Engine(
            config,
            state,
            codex_auditor_runner=audit_stub("APPROVED"),
            codex_runner=builder_stub("codex"),
            claude_runner=lambda *a, **k: None,
        )
        engine.review_only(make_package(), package_path(config))
        head_after = read_repo(repo).head

        plan = plan_for(config, repo, state)
        assert plan.nothing_to_do
        assert read_repo(repo).head == head_after

    def test_a_rejected_review_leaves_the_debt_open(self, config, repo) -> None:
        state = self._committed_with_debt(config, repo)
        engine = Engine(
            config,
            state,
            codex_auditor_runner=audit_stub("NOT_APPROVED"),
            codex_runner=builder_stub("codex"),
            claude_runner=lambda *a, **k: None,
        )
        outcome = engine.review_only(make_package(), package_path(config))
        assert outcome.status is WorkflowStatus.HUMAN_ACTION_REQUIRED
        assert auditdebt.open_debts(auditdebt.load(state.deferred_independent_audits))

    def test_the_builder_cannot_clear_its_own_debt(self, config, repo) -> None:
        state = self._committed_with_debt(config, repo)
        debts = auditdebt.load(state.deferred_independent_audits)
        with pytest.raises(auditdebt.DebtError, match="cannot supply"):
            auditdebt.reconcile(
                debts,
                identifier=debts[0].id,
                reviewer="claude",
                evidence="self review",
            )

    def test_the_wrong_reviewer_cannot_clear_the_debt(self, config, repo) -> None:
        """Settlement names the counterpart of the author, never the author."""

        state = self._committed_with_debt(config, repo)
        engine = Engine(config, state, claude_runner=lambda *a, **k: None)
        assert engine.current_author() is AgentIdentity.CLAUDE
        assert roles.COUNTERPART[engine.current_author()] is AgentIdentity.CODEX

    def test_an_approved_inline_audit_also_settles_the_debt(self, config, repo) -> None:
        state = self._committed_with_debt(config, repo)
        outcome = StepOutcome(status=WorkflowStatus.AUDIT_PENDING)
        engine = Engine(config, state, claude_runner=lambda *a, **k: None)
        run = agents.AgentRun(
            name="codex", command=[], exit_code=0, stdout="", stderr="", raw_report=""
        )
        cleared = engine.settle_audit_debt(make_package(), run, outcome)
        assert cleared is not None
        assert not auditdebt.open_debts(
            auditdebt.load(state.deferred_independent_audits)
        )


# =============================================================== P1-5


class TestAutopilotResumes:
    def test_autopilot_resumes_an_interrupted_package(self, config, repo) -> None:
        state = WorkflowState()
        state.current_work_package = "demo"
        state.builder = "codex"
        state.base_commit = read_repo(repo).head
        state.last_completed_stage = Stage.BUILT.value
        state.verification_status = None
        state.workflow_status = WorkflowStatus.LOCAL_VERIFY
        (repo / "work.txt").write_text("built earlier\n", encoding="utf-8")

        plan = orchestrator_cli._autopilot_resume_plan(config, state, make_package())
        assert plan is not None
        assert plan.skips(Stage.BUILT)
        assert plan.first_stage_to_run == "verify"

    def test_autopilot_starts_fresh_for_a_different_package(self, config, repo) -> None:
        state = WorkflowState()
        state.current_work_package = "another"
        state.workflow_status = WorkflowStatus.LOCAL_VERIFY
        assert (
            orchestrator_cli._autopilot_resume_plan(config, state, make_package())
            is None
        )

    def test_autopilot_starts_fresh_when_nothing_is_interrupted(
        self, config, repo
    ) -> None:
        state = WorkflowState()
        state.current_work_package = "demo"
        state.workflow_status = WorkflowStatus.IDLE
        assert (
            orchestrator_cli._autopilot_resume_plan(config, state, make_package())
            is None
        )

    def test_autopilot_raises_rather_than_rebuilding_after_a_refusal(
        self, config, repo
    ) -> None:
        """A refusal must stop the run, never become a fresh build."""

        state = WorkflowState()
        state.current_work_package = "demo"
        state.builder = "codex"
        state.base_commit = "0" * 40  # disagrees with the repository
        state.last_completed_stage = Stage.BUILT.value
        state.workflow_status = WorkflowStatus.LOCAL_VERIFY
        with pytest.raises(resume_mod.ResumeRefused):
            orchestrator_cli._autopilot_resume_plan(config, state, make_package())

    def test_autopilot_resumes_a_deferred_audit_as_review_only(
        self, config, repo
    ) -> None:
        (repo / "work.txt").write_text("shipped\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "package"], cwd=repo, check=True)
        head = read_repo(repo).head

        state = WorkflowState()
        state.current_work_package = "demo"
        state.builder = "claude"
        state.base_commit = head
        state.resulting_commit = head
        state.last_completed_stage = Stage.COMMITTED.value
        state.verification_status = "passed"
        state.workflow_status = WorkflowStatus.HUMAN_ACTION_REQUIRED
        debts: list[auditdebt.AuditDebt] = []
        auditdebt.record(
            debts,
            package="demo",
            resulting_commit=head,
            builder="claude",
            reviewer_required="codex",
            reason="codex unavailable",
        )
        state.deferred_independent_audits = auditdebt.dump(debts)

        plan = orchestrator_cli._autopilot_resume_plan(config, state, make_package())
        assert plan is not None
        assert plan.review_only


# =============================================== synthetic evidence hardening


class TestBuilderEvidence:
    def _evidence(self, tmp_path: Path) -> tuple[evidence.BuilderEvidence, Path]:
        report = tmp_path / "report.md"
        report.write_text("builder said this\n", encoding="utf-8")
        return (
            evidence.record_builder_evidence(
                builder="codex",
                package="demo",
                workflow_id="wf1",
                report_path=report,
            ),
            report,
        )

    def test_valid_evidence_returns_the_report(self, tmp_path) -> None:
        record, _ = self._evidence(tmp_path)
        text = evidence.load_builder_evidence(
            record, package="demo", expected_builder="codex"
        )
        assert "builder said this" in text

    def test_missing_evidence_is_refused(self) -> None:
        with pytest.raises(evidence.EvidenceRefused, match="no builder evidence"):
            evidence.load_builder_evidence(
                None, package="demo", expected_builder="codex"
            )

    def test_evidence_from_another_package_is_refused(self, tmp_path) -> None:
        record, _ = self._evidence(tmp_path)
        with pytest.raises(evidence.EvidenceRefused, match="belongs to package"):
            evidence.load_builder_evidence(
                record, package="other", expected_builder="codex"
            )

    def test_evidence_from_another_builder_is_refused(self, tmp_path) -> None:
        record, _ = self._evidence(tmp_path)
        with pytest.raises(evidence.EvidenceRefused, match="names"):
            evidence.load_builder_evidence(
                record, package="demo", expected_builder="claude"
            )

    def test_a_deleted_report_is_refused(self, tmp_path) -> None:
        record, report = self._evidence(tmp_path)
        report.unlink()
        with pytest.raises(evidence.EvidenceRefused, match="missing"):
            evidence.load_builder_evidence(
                record, package="demo", expected_builder="codex"
            )

    def test_an_altered_report_is_refused(self, tmp_path) -> None:
        record, report = self._evidence(tmp_path)
        report.write_text("tampered\n", encoding="utf-8")
        with pytest.raises(evidence.EvidenceRefused, match="has changed"):
            evidence.load_builder_evidence(
                record, package="demo", expected_builder="codex"
            )

    def test_a_build_records_validatable_evidence(self, config, repo) -> None:
        """A real builder persists a transcript; the run records proof of it."""

        def transcript_writing_builder(config_, order_path, *, stem, **kwargs):
            run = builder_stub("codex")(config_, order_path, stem=stem)
            path = config_.subdir("codex_reports") / f"{stem}.md"
            path.write_text(run.raw_report, encoding="utf-8")
            run.transcript_path = path
            return run

        state = WorkflowState()
        engine = Engine(
            config,
            state,
            codex_runner=transcript_writing_builder,
            claude_runner=lambda *a, **k: None,
        )
        engine.run_builder(make_package())
        record = evidence.BuilderEvidence.from_dict(state.builder_evidence)
        assert record is not None
        assert record.package == "demo"
        assert record.report_sha256
        assert evidence.load_builder_evidence(
            record, package="demo", expected_builder=record.builder
        )

    def test_reused_evidence_is_labelled_not_disguised(self, config, repo) -> None:
        """The stand-in must not look like a fresh successful agent run."""

        state = WorkflowState()
        state.current_work_package = "demo"
        state.builder = "codex"
        state.base_commit = read_repo(repo).head
        state.last_completed_stage = Stage.BUILT.value
        state.workflow_status = WorkflowStatus.LOCAL_VERIFY
        state.revisions = [{"author": "codex", "kind": "build", "revision": 1}]
        (repo / "work.txt").write_text("built earlier\n", encoding="utf-8")
        attach_builder_evidence(config, state)

        engine = Engine(
            config,
            state,
            codex_runner=builder_stub("codex"),
            claude_runner=lambda *a, **k: None,
        )
        plan = plan_for(config, repo, state)
        outcome = engine.execute(
            make_package(audit_policy=AuditPolicy.NONE),
            package_path(config),
            resume_plan=plan,
        )
        assert any("skipping build" in message for message in outcome.messages)

    def test_reuse_stops_when_evidence_cannot_be_validated(self, config, repo) -> None:
        """No fallback to unvalidated text: a refusal stops the run."""

        state = WorkflowState()
        state.current_work_package = "demo"
        state.builder = "codex"
        state.base_commit = read_repo(repo).head
        state.last_completed_stage = Stage.BUILT.value
        state.workflow_status = WorkflowStatus.LOCAL_VERIFY
        (repo / "work.txt").write_text("built earlier\n", encoding="utf-8")
        # Deliberately no builder evidence recorded.

        engine = Engine(
            config,
            state,
            codex_runner=builder_stub("codex"),
            claude_runner=lambda *a, **k: None,
        )
        plan = plan_for(config, repo, state)
        outcome = engine.execute(
            make_package(audit_policy=AuditPolicy.NONE),
            package_path(config),
            resume_plan=plan,
            builder_report="unvalidated text that must not be trusted",
        )
        assert outcome.status is WorkflowStatus.HUMAN_ACTION_REQUIRED
        assert "cannot reuse the builder's work" in (outcome.human_action or "")

    def test_a_tampered_report_stops_the_run(self, config, repo) -> None:
        state = WorkflowState()
        state.current_work_package = "demo"
        state.builder = "codex"
        state.base_commit = read_repo(repo).head
        state.last_completed_stage = Stage.BUILT.value
        state.workflow_status = WorkflowStatus.LOCAL_VERIFY
        (repo / "work.txt").write_text("built earlier\n", encoding="utf-8")
        report = attach_builder_evidence(config, state)
        report.write_text("tampered\n", encoding="utf-8")

        engine = Engine(
            config,
            state,
            codex_runner=builder_stub("codex"),
            claude_runner=lambda *a, **k: None,
        )
        plan = plan_for(config, repo, state)
        outcome = engine.execute(
            make_package(audit_policy=AuditPolicy.NONE),
            package_path(config),
            resume_plan=plan,
        )
        assert outcome.status is WorkflowStatus.HUMAN_ACTION_REQUIRED
        assert "has changed" in (outcome.human_action or "")

    def test_a_workflow_id_mismatch_refuses(self, tmp_path) -> None:
        report = tmp_path / "report.md"
        report.write_text("builder said this\n", encoding="utf-8")
        record = evidence.record_builder_evidence(
            builder="codex",
            package="demo",
            workflow_id="workflow-A",
            report_path=report,
        )
        with pytest.raises(evidence.EvidenceRefused, match="belongs to workflow"):
            evidence.load_builder_evidence(
                record,
                package="demo",
                expected_builder="codex",
                expected_workflow_id="workflow-B",
            )

    def test_a_revision_mismatch_refuses(self, tmp_path) -> None:
        report = tmp_path / "report.md"
        report.write_text("builder said this\n", encoding="utf-8")
        record = evidence.record_builder_evidence(
            builder="codex",
            package="demo",
            workflow_id="wf",
            report_path=report,
            revision=1,
        )
        with pytest.raises(evidence.EvidenceRefused, match="revision"):
            evidence.load_builder_evidence(
                record,
                package="demo",
                expected_builder="codex",
                expected_revision=2,
            )


# ===================================================================== heartbeat


class TestHeartbeatDuringGates:
    def test_a_beat_is_emitted_between_verification_gates(self, config, repo) -> None:
        from orchestration import heartbeat as hb

        beat = hb.Heartbeat(config)
        state = WorkflowState()
        engine = Engine(
            config,
            state,
            codex_runner=builder_stub("codex"),
            claude_runner=lambda *a, **k: None,
            heartbeat=beat,
        )
        # Capture every gate value as it is written, not just the final one:
        # the point is that a beat happens *during* the run.
        seen: list[str] = []
        original_beat = beat.beat

        def recording_beat(**updates):
            if "verification_gate" in updates:
                seen.append(str(updates["verification_gate"]))
            return original_beat(**updates)

        beat.beat = recording_beat  # type: ignore[method-assign]
        outcome = StepOutcome(status=WorkflowStatus.LOCAL_VERIFY)
        engine.run_verification(make_package(), outcome)
        assert any("1/1" in value for value in seen), seen
        assert seen[-1] == "complete"

    def test_the_hook_reaches_verify(self, config, repo) -> None:
        from orchestration.verify import verify

        seen: list[tuple[int, int]] = []
        verify(
            config,
            commands=((sys.executable, "-c", "pass"), (sys.executable, "-c", "pass")),
            label="hook",
            on_command=lambda index, total, command: seen.append((index, total)),
        )
        assert seen == [(1, 2), (2, 2)]
