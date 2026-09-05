"""Regression tests for the second round of Orchestrator v2 blockers.

Hidden tracked-file mutations, runtime-file noise, correction ownership in both
directions end to end, per-commit debt identity, autopilot refusal, and heartbeat
freshness during a long call.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import orchestrator as orchestrator_cli  # noqa: E402
from orchestration import agents, auditdebt, evidence, roles  # noqa: E402
from orchestration import heartbeat as hb  # noqa: E402
from orchestration import resume as resume_mod  # noqa: E402
from orchestration.config import (  # noqa: E402
    AgentConfig,
    Limits,
    OrchestratorConfig,
)
from orchestration.engine import Engine  # noqa: E402
from orchestration.gitops import git, read_repo  # noqa: E402
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
    (root / "tracked.py").write_text("value = 1\n", encoding="utf-8")
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


# =========================================================== fingerprint


class TestFingerprintCompleteness:
    def test_a_tracked_change_hidden_from_status_is_still_caught(
        self, config, repo
    ) -> None:
        """The exact hole: `assume-unchanged` hides a file from `git status`."""

        before = evidence.tree_fingerprint(config, make_package())

        git(repo, "update-index", "--assume-unchanged", "tracked.py")
        (repo / "tracked.py").write_text("value = 999\n", encoding="utf-8")

        # git status genuinely does not report it...
        assert "tracked.py" not in read_repo(repo).dirty_paths
        # ...but the fingerprint does.
        assert evidence.tree_fingerprint(config, make_package()) != before

    def test_skip_worktree_is_also_caught(self, config, repo) -> None:
        before = evidence.tree_fingerprint(config, make_package())
        git(repo, "update-index", "--skip-worktree", "tracked.py")
        (repo / "tracked.py").write_text("value = 42\n", encoding="utf-8")
        assert "tracked.py" not in read_repo(repo).dirty_paths
        assert evidence.tree_fingerprint(config, make_package()) != before

    def test_runtime_files_do_not_destabilise_the_fingerprint(
        self, config, repo
    ) -> None:
        """A heartbeat is written every few seconds; it must not count."""

        first = evidence.tree_fingerprint(config, make_package())
        beat = hb.Heartbeat(config)
        beat.beat(package="demo", stage="verifying")
        assert hb.heartbeat_path(config).exists()
        assert evidence.tree_fingerprint(config, make_package()) == first

    def test_workflow_state_writes_do_not_change_the_fingerprint(
        self, config, repo
    ) -> None:
        from orchestration.state import save_state

        first = evidence.tree_fingerprint(config, make_package())
        save_state(config.state_path, WorkflowState())
        assert evidence.tree_fingerprint(config, make_package()) == first

    def test_a_real_source_change_still_changes_the_fingerprint(
        self, config, repo
    ) -> None:
        first = evidence.tree_fingerprint(config, make_package())
        (repo / "work.txt").write_text("new work\n", encoding="utf-8")
        assert evidence.tree_fingerprint(config, make_package()) != first

    def test_ignored_files_are_not_package_content(self, config, repo) -> None:
        (repo / ".gitignore").write_text("junk/\n", encoding="utf-8")
        subprocess.run(["git", "add", ".gitignore"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "ignore"], cwd=repo, check=True)
        first = evidence.tree_fingerprint(config, make_package())
        (repo / "junk").mkdir()
        (repo / "junk" / "noise.txt").write_text("noise\n", encoding="utf-8")
        assert evidence.tree_fingerprint(config, make_package()) == first

    def test_a_submodule_is_recorded_by_commit_not_walked(
        self, config, repo, tmp_path
    ) -> None:
        """A gitlink must not be read as a file or recursed into."""

        inner = tmp_path / "inner"
        inner.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=inner, check=True)
        subprocess.run(
            ["git", "config", "user.email", "t@example.com"], cwd=inner, check=True
        )
        subprocess.run(["git", "config", "user.name", "Test"], cwd=inner, check=True)
        (inner / "a.txt").write_text("inner\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=inner, check=True)
        subprocess.run(["git", "commit", "-qm", "inner"], cwd=inner, check=True)

        added = subprocess.run(
            [
                "git",
                "-c",
                "protocol.file.allow=always",
                "submodule",
                "add",
                "-q",
                str(inner),
                "sub",
            ],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        if added.returncode != 0:
            pytest.skip(f"submodule unsupported here: {added.stderr.strip()}")

        digest = evidence.tree_fingerprint(config, make_package())
        assert digest  # completed without trying to read a directory as a file

    def test_head_is_part_of_the_identity(self, config, repo) -> None:
        first = evidence.tree_fingerprint(config, make_package())
        (repo / "work.txt").write_text("committed\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "advance"], cwd=repo, check=True)
        assert evidence.tree_fingerprint(config, make_package()) != first


# =========================================================== correction flow


def _correction_engine(config, state, *, order: list[str]):
    """An engine whose agents record the order in which they were used."""

    def codex_builder(config_, order_path, *, stem, **kwargs):
        order.append("codex-build")
        (config_.repo / "work.txt").write_text("codex work\n", encoding="utf-8")
        return builder_stub("codex")(config_, order_path, stem=stem)

    def claude_builder(config_, order_path, *, stem, **kwargs):
        order.append("claude-build")
        (config_.repo / "work.txt").write_text("claude work\n", encoding="utf-8")
        return builder_stub("claude")(config_, order_path, stem=stem)

    return Engine(
        config,
        state,
        codex_runner=codex_builder,
        claude_builder_runner=claude_builder,
        claude_runner=lambda *a, **k: None,
    )


class TestCorrectionOwnershipEndToEnd:
    def _report(self, engine, package):
        from orchestration.verify import VerificationReport

        return VerificationReport(
            passed=True, protected_ok=True, scope_ok=True, changed_files=()
        )

    def test_claude_builds_codex_audits_codex_corrects_claude_reaudits(
        self, config, repo
    ) -> None:
        state = WorkflowState()
        engine = _correction_engine(config, state, order=[])
        package = make_package()

        engine._record_revision(AgentIdentity.CLAUDE, "build")
        assert engine.current_author() is AgentIdentity.CLAUDE
        mode, _ = engine.review_mode(
            package, Risk.LOW, self._report(engine, package), needs_audit=True
        )
        assert mode == "codex_audit", "Codex must audit Claude's build"

        engine._record_revision(AgentIdentity.CODEX, "correction")
        assert engine.current_author() is AgentIdentity.CODEX
        mode, _ = engine.review_mode(
            package, Risk.LOW, self._report(engine, package), needs_audit=True
        )
        assert mode == "claude", "Claude must re-audit Codex's correction"

    def test_codex_builds_claude_audits_claude_corrects_codex_reaudits(
        self, config, repo
    ) -> None:
        state = WorkflowState()
        engine = _correction_engine(config, state, order=[])
        package = make_package()

        engine._record_revision(AgentIdentity.CODEX, "build")
        mode, _ = engine.review_mode(
            package, Risk.LOW, self._report(engine, package), needs_audit=True
        )
        assert mode == "claude", "Claude must audit Codex's build"

        engine._record_revision(AgentIdentity.CLAUDE, "correction")
        mode, _ = engine.review_mode(
            package, Risk.LOW, self._report(engine, package), needs_audit=True
        )
        assert mode == "codex_audit", "Codex must re-audit Claude's correction"

    def test_every_revision_records_its_author_and_kind(self, config) -> None:
        state = WorkflowState()
        engine = Engine(config, state, claude_runner=lambda *a, **k: None)
        engine._record_revision(AgentIdentity.CLAUDE, "build")
        engine._record_revision(AgentIdentity.CODEX, "correction")
        engine._record_revision(AgentIdentity.CLAUDE, "correction")
        assert [entry["author"] for entry in state.revisions] == [
            "claude",
            "codex",
            "claude",
        ]
        assert [entry["kind"] for entry in state.revisions] == [
            "build",
            "correction",
            "correction",
        ]
        assert [entry["revision"] for entry in state.revisions] == [1, 2, 3]

    def test_the_author_of_the_current_revision_never_audits_it(self, config) -> None:
        for author in AgentIdentity:
            state = WorkflowState()
            engine = Engine(config, state, claude_runner=lambda *a, **k: None)
            engine._record_revision(roles.COUNTERPART[author], "build")
            engine._record_revision(author, "correction")
            reviewer = roles.COUNTERPART[engine.current_author()]
            assert reviewer != author
            roles.assert_independent(engine.current_author(), reviewer)


# =========================================================== audit debt


class TestExactDebtIdentity:
    def _two_debts(self, repo) -> tuple[WorkflowState, str, str]:
        """Two debts for the same package at two different commits."""

        (repo / "work.txt").write_text("first\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "first"], cwd=repo, check=True)
        first = read_repo(repo).head

        (repo / "work.txt").write_text("second\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "second"], cwd=repo, check=True)
        second = read_repo(repo).head

        state = WorkflowState()
        state.current_work_package = "demo"
        state.builder = "claude"
        state.revisions = [{"author": "claude", "kind": "build", "revision": 1}]
        state.resulting_commit = second
        debts: list[auditdebt.AuditDebt] = []
        for commit in (first, second):
            auditdebt.record(
                debts,
                package="demo",
                resulting_commit=commit,
                builder="claude",
                reviewer_required="codex",
                reason="codex unavailable",
            )
        state.deferred_independent_audits = auditdebt.dump(debts)
        return state, first, second

    def test_two_commits_produce_two_distinct_debts(self, config, repo) -> None:
        state, first, second = self._two_debts(repo)
        debts = auditdebt.load(state.deferred_independent_audits)
        assert len(auditdebt.open_debts(debts)) == 2
        assert debts[0].id != debts[1].id

    def test_settlement_clears_only_the_reviewed_commit(self, config, repo) -> None:
        state, first, second = self._two_debts(repo)
        engine = Engine(config, state, claude_runner=lambda *a, **k: None)
        from orchestration.engine import StepOutcome

        outcome = StepOutcome(status=WorkflowStatus.AUDIT_PENDING)
        run = agents.AgentRun(
            name="codex", command=[], exit_code=0, stdout="", stderr="", raw_report=""
        )
        cleared = engine.settle_audit_debt(make_package(), run, outcome)

        assert cleared is not None
        assert cleared.resulting_commit == second
        remaining = auditdebt.open_debts(
            auditdebt.load(state.deferred_independent_audits)
        )
        assert len(remaining) == 1
        assert remaining[0].resulting_commit == first

    def test_settlement_reports_when_no_debt_matches_the_commit(
        self, config, repo
    ) -> None:
        state, first, _second = self._two_debts(repo)
        # Point the state at a commit that owes nothing.
        state.resulting_commit = "f" * 40
        subprocess.run(
            ["git", "commit", "-qm", "extra", "--allow-empty"], cwd=repo, check=True
        )
        engine = Engine(config, state, claude_runner=lambda *a, **k: None)
        from orchestration.engine import StepOutcome

        outcome = StepOutcome(status=WorkflowStatus.AUDIT_PENDING)
        run = agents.AgentRun(
            name="codex", command=[], exit_code=0, stdout="", stderr="", raw_report=""
        )
        assert engine.settle_audit_debt(make_package(), run, outcome) is None
        assert (
            len(auditdebt.open_debts(auditdebt.load(state.deferred_independent_audits)))
            == 2
        )
        assert any("no audit debt matches" in m for m in outcome.messages)


# =========================================================== autopilot


class TestAutopilotStopsOnRefusal:
    def test_a_refused_plan_raises_rather_than_returning_none(
        self, config, repo
    ) -> None:
        state = WorkflowState()
        state.current_work_package = "demo"
        state.builder = "codex"
        state.base_commit = "0" * 40
        state.last_completed_stage = Stage.BUILT.value
        state.workflow_status = WorkflowStatus.LOCAL_VERIFY
        with pytest.raises(resume_mod.ResumeRefused):
            orchestrator_cli._autopilot_resume_plan(config, state, make_package())

    def test_tampered_science_refuses_a_resume_rather_than_rebuilding(
        self, config, repo
    ) -> None:
        state = WorkflowState()
        state.current_work_package = "demo"
        state.builder = "codex"
        state.base_commit = read_repo(repo).head
        state.last_completed_stage = Stage.BUILT.value
        state.workflow_status = WorkflowStatus.LOCAL_VERIFY
        (repo / "work.txt").write_text("built\n", encoding="utf-8")
        (repo / "protected.csv").write_text("tampered\n", encoding="utf-8")
        with pytest.raises(resume_mod.ResumeRefused, match="protected artifacts"):
            orchestrator_cli._autopilot_resume_plan(config, state, make_package())


# =========================================================== heartbeat


class TestHeartbeatFreshness:
    def test_a_long_blocking_call_stays_fresh(self, config) -> None:
        """The point of the ticker: a slow call must not become STALE."""

        beat = hb.Heartbeat(config)
        with hb.HeartbeatTicker(beat, interval_seconds=0.1, stage="long") as ticker:
            time.sleep(0.6)
            mid = hb.read_heartbeat(config)
            assert mid is not None
            assert mid.age_seconds() < 0.5, "a guarded call must stay fresh"
        assert ticker.ticks >= 2

    def test_the_ticker_stops_when_the_call_returns(self, config) -> None:
        beat = hb.Heartbeat(config)
        with hb.HeartbeatTicker(beat, interval_seconds=0.1, stage="long") as ticker:
            time.sleep(0.35)
        settled = ticker.ticks
        time.sleep(0.35)
        assert ticker.ticks == settled, "no beats after the guarded call returned"

    def test_a_stale_record_is_still_detected_without_a_ticker(self, config) -> None:
        beat = hb.Heartbeat(config)
        beat.beat()
        beat.record.last_heartbeat = time.time() - (hb.STALE_AFTER_SECONDS + 60)
        assert beat.record.is_stale()

    def test_the_ticker_tolerates_a_missing_heartbeat(self) -> None:
        with hb.HeartbeatTicker(None, interval_seconds=0.05) as ticker:
            time.sleep(0.15)
        assert ticker.ticks >= 0  # no exception is the assertion

    def test_verification_ticks_while_gates_run(self, config, repo) -> None:
        from orchestration.engine import StepOutcome

        beat = hb.Heartbeat(config)
        state = WorkflowState()
        engine = Engine(
            config,
            state,
            codex_runner=builder_stub("codex"),
            claude_runner=lambda *a, **k: None,
            heartbeat=beat,
        )
        outcome = StepOutcome(status=WorkflowStatus.LOCAL_VERIFY)
        engine.run_verification(make_package(), outcome)
        record = hb.read_heartbeat(config)
        assert record is not None
        assert not record.is_stale()


# =========================================================== legacy path


class TestNoUnsafeLegacyPath:
    def test_resume_from_alone_authorises_no_skipping(self, config, repo) -> None:
        calls: list[str] = []
        state = WorkflowState()
        state.current_work_package = "demo"
        state.builder = "codex"
        state.base_commit = read_repo(repo).head
        state.last_completed_stage = Stage.AUDITED.value
        state.workflow_status = WorkflowStatus.LOCAL_VERIFY

        engine = Engine(
            config,
            state,
            codex_runner=builder_stub("codex", calls=calls),
            claude_runner=lambda *a, **k: None,
        )
        engine.execute(
            make_package(audit_policy=AuditPolicy.NONE),
            config.subdir("work_packages") / "demo.json",
            resume_from=Stage.AUDITED,
        )
        # Even claiming everything was done, the builder still runs.
        assert calls == ["codex"]

    def test_the_engine_source_derives_skips_only_from_a_plan(self) -> None:
        source = (TOOLS / "orchestration" / "engine.py").read_text(encoding="utf-8")
        assert "resume_plan.skips(Stage.BUILT)" in source
        assert "stage_reached(resume_from" not in source
