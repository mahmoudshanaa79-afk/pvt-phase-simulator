"""Tests for the Orchestrator v2 core: failover, resume, independence, debt.

Every agent boundary is mocked. These never spend a real Codex or Claude call.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import orchestrator as orchestrator_cli  # noqa: E402
from orchestration import agents, auditdebt, roles  # noqa: E402
from orchestration import heartbeat as hb  # noqa: E402
from orchestration.config import (  # noqa: E402
    AgentConfig,
    Limits,
    OrchestratorConfig,
)
from orchestration.engine import Engine  # noqa: E402
from orchestration.roles import AgentIdentity, Unavailable  # noqa: E402
from orchestration.state import (  # noqa: E402
    Stage,
    WorkflowState,
    WorkflowStatus,
    load_state,
    save_state,
    stage_reached,
)
from orchestration.workpackage import (  # noqa: E402
    AuditPolicy,
    CommitPolicy,
    Risk,
    WorkPackage,
    save_package,
)

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


def _builder_report(status: str = "COMPLETE", writes: str = "work.txt") -> str:
    return (
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


def builder_stub(
    name: str, *, writes: str = "work.txt", calls: list[str] | None = None
):
    def runner(config, order_path, *, stem, **kwargs):
        if calls is not None:
            calls.append(name)
        if writes:
            (config.repo / writes).write_text(f"built by {name}\n", encoding="utf-8")
        report = _builder_report(writes=writes)
        run = agents.AgentRun(
            name=name,
            command=[f"{name}-stub"],
            exit_code=0,
            stdout=report,
            stderr="",
            raw_report=report,
        )
        run.contract = agents.validate_builder_contract(agents.parse_contract(report))
        return run

    return runner


def quota_exhausted_stub(name: str, calls: list[str] | None = None):
    """A builder that ran but has no capacity left."""

    def runner(config, order_path, *, stem, **kwargs):
        if calls is not None:
            calls.append(name)
        message = f"{name}: usage limit reached; try again later"
        return agents.AgentRun(
            name=name,
            command=[f"{name}-stub"],
            exit_code=1,
            stdout="",
            stderr=message,
            raw_report=message,
        )

    return runner


def unavailable_stub(name: str, calls: list[str] | None = None):
    """A builder whose CLI cannot be started at all."""

    def runner(config, order_path, *, stem, **kwargs):
        if calls is not None:
            calls.append(name)
        raise agents.AgentUnavailable(f"{name} CLI not found")

    return runner


# ------------------------------------------------------------------ availability


class TestAvailabilityAndFailover:
    def test_quota_message_is_a_capacity_failure(self) -> None:
        run = agents.AgentRun(
            name="codex",
            command=[],
            exit_code=1,
            stdout="",
            stderr="Error: usage limit reached",
            raw_report="",
        )
        assert roles.classify_run_failure(run) is Unavailable.QUOTA_EXHAUSTED
        assert roles.is_capacity_failure(run)

    def test_launch_failure_is_a_capacity_failure(self) -> None:
        run = agents.AgentRun(
            name="codex",
            command=[],
            exit_code=1,
            stdout="",
            stderr="[WinError 2] The system cannot find the file specified",
            raw_report="",
        )
        assert roles.classify_run_failure(run) is Unavailable.LAUNCH_FAILURE

    def test_a_bad_contract_is_not_an_availability_problem(self) -> None:
        """An agent that ran and produced junk is present, just wrong."""

        run = agents.AgentRun(
            name="codex",
            command=[],
            exit_code=1,
            stdout="I could not parse the request",
            stderr="assertion failed in user code",
            raw_report="",
        )
        assert roles.classify_run_failure(run) is Unavailable.NONE
        assert not roles.is_capacity_failure(run)

    def test_successful_run_is_never_a_capacity_failure(self) -> None:
        run = agents.AgentRun(
            name="codex",
            command=[],
            exit_code=0,
            stdout="usage limit mentioned in prose",
            stderr="",
            raw_report="",
        )
        assert not roles.is_capacity_failure(run)

    def test_codex_unavailable_falls_over_to_claude(self, config, repo) -> None:
        calls: list[str] = []
        state = WorkflowState()
        engine = Engine(
            config,
            state,
            codex_runner=quota_exhausted_stub("codex", calls),
            claude_builder_runner=builder_stub("claude", calls=calls),
            claude_runner=lambda *a, **k: None,  # marks claude injected
        )
        outcome, run = engine.run_builder(make_package())
        assert calls == ["codex", "claude"]
        assert run is not None and run.name == "claude"
        assert state.builder == AgentIdentity.CLAUDE.value
        assert state.role_transitions
        assert state.role_transitions[-1]["to_builder"] == "claude"

    def test_claude_unavailable_falls_over_to_codex(self, config, repo) -> None:
        calls: list[str] = []
        # Prefer Claude so the failover runs in the opposite direction.
        state2 = WorkflowState()
        engine2 = Engine(
            config,
            state2,
            codex_runner=builder_stub("codex", calls=calls),
            claude_builder_runner=quota_exhausted_stub("claude", calls),
            claude_runner=lambda *a, **k: None,
            preferred_builder=AgentIdentity.CLAUDE,
        )
        calls.clear()
        outcome2, run2 = engine2.run_builder(make_package())
        assert calls == ["claude", "codex"]
        assert run2 is not None and run2.name == "codex"
        assert state2.builder == AgentIdentity.CODEX.value
        assert state2.role_transitions[-1]["to_builder"] == "codex"

    def test_launch_failure_also_fails_over(self, config, repo) -> None:
        calls: list[str] = []
        state = WorkflowState()
        engine = Engine(
            config,
            state,
            codex_runner=unavailable_stub("codex", calls),
            claude_builder_runner=builder_stub("claude", calls=calls),
            claude_runner=lambda *a, **k: None,
        )
        outcome, run = engine.run_builder(make_package())
        assert calls == ["codex", "claude"]
        assert run is not None and run.name == "claude"

    def test_both_unavailable_requires_a_human(self, config, repo) -> None:
        calls: list[str] = []
        state = WorkflowState()
        engine = Engine(
            config,
            state,
            codex_runner=quota_exhausted_stub("codex", calls),
            claude_builder_runner=quota_exhausted_stub("claude", calls),
            claude_runner=lambda *a, **k: None,
        )
        outcome, _ = engine.run_builder(make_package())
        assert outcome.status is WorkflowStatus.HUMAN_ACTION_REQUIRED
        assert "unavailable" in (outcome.human_action or "").lower()
        assert sorted(calls) == ["claude", "codex"]

    def test_failover_preserves_work_already_on_disk(self, config, repo) -> None:
        """A handover must not discard what the first builder produced."""

        (repo / "work.txt").write_text("partial work\n", encoding="utf-8")

        def preserving(config_, order_path, *, stem, **kwargs):
            assert (config_.repo / "work.txt").exists()
            message = "usage limit reached"
            return agents.AgentRun(
                name="codex",
                command=[],
                exit_code=1,
                stdout="",
                stderr=message,
                raw_report=message,
            )

        state = WorkflowState()
        engine = Engine(
            config,
            state,
            codex_runner=preserving,
            claude_builder_runner=builder_stub("claude"),
            claude_runner=lambda *a, **k: None,
        )
        engine.run_builder(make_package())
        assert (repo / "work.txt").exists()

    def test_no_builder_available_raises(self, config) -> None:
        availability = {
            AgentIdentity.CODEX: roles.Availability(
                AgentIdentity.CODEX, False, "gone", Unavailable.NOT_FOUND
            ),
            AgentIdentity.CLAUDE: roles.Availability(
                AgentIdentity.CLAUDE, False, "gone", Unavailable.NOT_FOUND
            ),
        }
        with pytest.raises(roles.NoBuilderAvailable):
            roles.select_builder(availability)


# ------------------------------------------------------------ review independence


class TestReviewIndependence:
    def test_builder_can_never_be_its_own_reviewer(self) -> None:
        for agent in AgentIdentity:
            with pytest.raises(roles.ReviewIndependenceError):
                roles.assert_independent(agent, agent)

    def test_reviewer_is_always_the_counterpart(self) -> None:
        both = {agent: roles.Availability(agent, True, "ok") for agent in AgentIdentity}
        for builder in AgentIdentity:
            reviewer, deferred, _ = roles.select_reviewer(builder, both)
            assert reviewer is roles.COUNTERPART[builder]
            assert reviewer != builder
            assert not deferred

    def test_missing_counterpart_defers_rather_than_self_reviewing(self) -> None:
        availability = {
            AgentIdentity.CODEX: roles.Availability(AgentIdentity.CODEX, True, "ok"),
            AgentIdentity.CLAUDE: roles.Availability(
                AgentIdentity.CLAUDE, False, "gone", Unavailable.NOT_FOUND
            ),
        }
        reviewer, deferred, reason = roles.select_reviewer(
            AgentIdentity.CODEX, availability
        )
        assert reviewer is None
        assert deferred
        assert "codex" in reason

    def test_engine_review_mode_names_the_counterpart(self, config) -> None:
        state = WorkflowState()
        engine = Engine(
            config,
            state,
            codex_runner=builder_stub("codex"),
            claude_runner=lambda *a, **k: None,
        )
        engine.assign_roles()
        from orchestration.verify import VerificationReport

        report = VerificationReport(
            passed=True, protected_ok=True, scope_ok=True, changed_files=()
        )
        mode, reason = engine.review_mode(
            make_package(), Risk.LOW, report, needs_audit=True
        )
        # Codex built, so Claude must review.
        assert mode == "claude"
        assert "claude" in reason


# ------------------------------------------------------------------- audit debt


class TestAuditDebt:
    def _debt(self, **overrides) -> dict:
        base = {
            "package": "demo",
            "resulting_commit": "abcdef1234567890",
            "builder": "claude",
            "reviewer_required": "codex",
            "reason": "codex unavailable",
        }
        base.update(overrides)
        return base

    def test_recording_is_idempotent_for_the_same_commit(self) -> None:
        debts: list[auditdebt.AuditDebt] = []
        first = auditdebt.record(debts, **self._debt())
        second = auditdebt.record(debts, **self._debt())
        assert first is second
        assert len(debts) == 1

    def test_a_different_commit_is_a_different_debt(self) -> None:
        debts: list[auditdebt.AuditDebt] = []
        auditdebt.record(debts, **self._debt())
        auditdebt.record(debts, **self._debt(resulting_commit="ffffffffffff"))
        assert len(debts) == 2

    def test_builder_cannot_be_recorded_as_its_own_reviewer(self) -> None:
        debts: list[auditdebt.AuditDebt] = []
        with pytest.raises(auditdebt.DebtError, match="own required reviewer"):
            auditdebt.record(debts, **self._debt(reviewer_required="claude"))

    def test_reconciliation_clears_the_right_debt(self) -> None:
        debts: list[auditdebt.AuditDebt] = []
        target = auditdebt.record(debts, **self._debt())
        other = auditdebt.record(debts, **self._debt(package="other"))
        auditdebt.reconcile(
            debts,
            identifier=target.id,
            reviewer="codex",
            evidence="codex review APPROVED, 0 blocking",
        )
        assert not target.is_open
        assert target.cleared_by == "codex"
        assert other.is_open
        assert auditdebt.open_debts(debts) == [other]

    def test_the_builder_cannot_clear_its_own_debt(self) -> None:
        debts: list[auditdebt.AuditDebt] = []
        debt = auditdebt.record(debts, **self._debt())
        with pytest.raises(auditdebt.DebtError, match="cannot supply"):
            auditdebt.reconcile(
                debts, identifier=debt.id, reviewer="claude", evidence="looks fine"
            )
        assert debt.is_open

    def test_a_debt_cannot_be_approved_twice(self) -> None:
        debts: list[auditdebt.AuditDebt] = []
        debt = auditdebt.record(debts, **self._debt())
        auditdebt.reconcile(
            debts, identifier=debt.id, reviewer="codex", evidence="first"
        )
        with pytest.raises(auditdebt.DebtError, match="already cleared"):
            auditdebt.reconcile(
                debts, identifier=debt.id, reviewer="codex", evidence="second"
            )

    def test_clearing_requires_evidence(self) -> None:
        debts: list[auditdebt.AuditDebt] = []
        debt = auditdebt.record(debts, **self._debt())
        with pytest.raises(auditdebt.DebtError, match="evidence"):
            auditdebt.reconcile(
                debts, identifier=debt.id, reviewer="codex", evidence="   "
            )

    def test_unknown_debt_is_refused(self) -> None:
        with pytest.raises(auditdebt.DebtError, match="no audit debt"):
            auditdebt.reconcile(
                [], identifier="nope@000", reviewer="codex", evidence="x"
            )

    def test_external_review_evidence_is_recorded_as_such(self) -> None:
        debts: list[auditdebt.AuditDebt] = []
        debt = auditdebt.record(debts, **self._debt())
        auditdebt.reconcile(
            debts,
            identifier=debt.id,
            reviewer="human",
            evidence="read-only review, transcript attached",
            kind=auditdebt.EvidenceKind.EXTERNAL,
        )
        assert debt.evidence_kind == "external_review"

    def test_legacy_v1_entries_load_without_roles(self) -> None:
        legacy = [
            {
                "status": "PENDING_INDEPENDENT_AUDIT",
                "package": "v1_1_application_release_qa",
                "resulting_commit": "514d963",
                "reason": "Codex exhausted its quota",
            }
        ]
        debts = auditdebt.load(legacy)
        assert len(debts) == 1
        assert debts[0].builder == "unknown"
        assert debts[0].is_open

    def test_round_trip_through_dump_preserves_state(self) -> None:
        debts: list[auditdebt.AuditDebt] = []
        debt = auditdebt.record(debts, **self._debt())
        auditdebt.reconcile(debts, identifier=debt.id, reviewer="codex", evidence="ok")
        restored = auditdebt.load(auditdebt.dump(debts))
        assert not restored[0].is_open
        assert restored[0].cleared_by == "codex"

    def test_engine_records_debt_naming_builder_and_reviewer(self, config) -> None:
        state = WorkflowState()
        engine = Engine(
            config,
            state,
            codex_runner=builder_stub("codex"),
            claude_runner=lambda *a, **k: None,
        )
        engine.assign_roles()
        debt = engine.record_audit_debt(
            make_package(),
            resulting_commit="deadbeefcafe",
            base_commit="0000",
            effective_risk=Risk.LOW,
            reason="claude unavailable",
        )
        assert debt.builder == "codex"
        assert debt.reviewer_required == "claude"
        assert state.deferred_independent_audits


# -------------------------------------------------------------------- heartbeat


class TestHeartbeat:
    def test_heartbeat_persists_and_reloads(self, config) -> None:
        beat = hb.Heartbeat(config)
        beat.beat(package="demo", stage="building", builder="codex")
        record = hb.read_heartbeat(config)
        assert record is not None
        assert record.package == "demo"
        assert record.stage == "building"
        assert record.builder == "codex"
        assert record.workflow_id == beat.record.workflow_id

    def test_heartbeat_file_lands_where_documented(self, config) -> None:
        beat = hb.Heartbeat(config)
        beat.beat()
        expected = config.ai_dir / "runtime" / "current_status.json"
        assert expected.exists()
        assert hb.heartbeat_path(config) == expected

    def test_fresh_heartbeat_is_not_stale(self, config) -> None:
        beat = hb.Heartbeat(config)
        beat.beat()
        assert not beat.record.is_stale()

    def test_old_heartbeat_is_stale(self, config) -> None:
        beat = hb.Heartbeat(config)
        beat.beat()
        beat.record.last_heartbeat = time.time() - (hb.STALE_AFTER_SECONDS + 60)
        assert beat.record.is_stale()
        assert not beat.record.is_running()

    def test_a_dead_process_is_never_running(self, config) -> None:
        beat = hb.Heartbeat(config)
        beat.beat()
        beat.record.pid = 2**31 - 1  # a pid that cannot plausibly exist
        assert not beat.record.is_running()

    def test_finished_run_is_not_running_even_if_fresh(self, config) -> None:
        beat = hb.Heartbeat(config)
        beat.finish()
        assert beat.record.finished
        assert not beat.record.is_running()

    def test_corrupt_heartbeat_reads_as_absent(self, config) -> None:
        path = hb.heartbeat_path(config)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        assert hb.read_heartbeat(config) is None

    def test_missing_heartbeat_reads_as_absent(self, config) -> None:
        assert hb.read_heartbeat(config) is None

    def test_unknown_fields_go_to_extra(self, config) -> None:
        beat = hb.Heartbeat(config)
        beat.beat(some_new_signal="value")
        assert beat.record.extra["some_new_signal"] == "value"

    def test_duration_formatting_is_hms(self) -> None:
        assert hb.format_duration(0) == "00:00:00"
        assert hb.format_duration(511) == "00:08:31"
        assert hb.format_duration(3661) == "01:01:01"

    def test_current_process_is_alive(self) -> None:
        import os

        assert hb.process_alive(os.getpid())
        assert not hb.process_alive(None)
        assert not hb.process_alive(0)
        assert not hb.process_alive(-1)


# ----------------------------------------------------------------------- resume


class TestResumeState:
    def test_stage_ordering_answers_at_least_as_far_as(self) -> None:
        assert stage_reached(Stage.BUILT.value, Stage.PLANNED)
        assert stage_reached(Stage.COMMITTED.value, Stage.AUDITED)
        assert not stage_reached(Stage.PLANNED.value, Stage.VERIFIED)
        assert not stage_reached(None, Stage.PLANNED)
        assert not stage_reached("nonsense", Stage.PLANNED)

    def test_resume_fields_survive_a_save_load_cycle(self, config) -> None:
        state = WorkflowState()
        state.workflow_id = "abc123"
        state.builder = "claude"
        state.reviewer = "codex"
        state.last_completed_stage = Stage.VERIFIED.value
        state.verification_status = "passed"
        state.base_commit = "1111"
        state.resulting_commit = "2222"
        state.role_transitions.append({"to_builder": "claude"})
        save_state(config.state_path, state)

        restored = load_state(config.state_path)
        assert restored.workflow_id == "abc123"
        assert restored.builder == "claude"
        assert restored.reviewer == "codex"
        assert restored.last_completed_stage == Stage.VERIFIED.value
        assert restored.verification_status == "passed"
        assert restored.base_commit == "1111"
        assert restored.resulting_commit == "2222"
        assert restored.role_transitions[-1]["to_builder"] == "claude"

    def test_a_v1_state_file_still_loads(self, config) -> None:
        """State written before v2 must not become unreadable."""

        legacy = {
            "project": "pvt-phase-simulator",
            "phase": "post-roadmap",
            "workflow_status": "IDLE",
            "work_packages_since_audit": 2,
            "audit_required": False,
        }
        config.state_path.parent.mkdir(parents=True, exist_ok=True)
        config.state_path.write_text(json.dumps(legacy), encoding="utf-8")
        state = load_state(config.state_path)
        assert state.workflow_status is WorkflowStatus.IDLE
        assert state.builder is None
        assert state.last_completed_stage is None

    def test_interrupted_builder_records_the_stage_it_reached(self, config) -> None:
        state = WorkflowState()
        engine = Engine(
            config,
            state,
            codex_runner=builder_stub("codex"),
            claude_runner=lambda *a, **k: None,
        )
        engine.run_builder(make_package())
        assert state.last_completed_stage == Stage.BUILT.value
        assert stage_reached(state.last_completed_stage, Stage.PLANNED)

    def test_interrupted_verification_records_its_outcome(self, config) -> None:
        from orchestration.engine import StepOutcome

        state = WorkflowState()
        engine = Engine(
            config,
            state,
            codex_runner=builder_stub("codex"),
            claude_runner=lambda *a, **k: None,
        )
        outcome = StepOutcome(status=WorkflowStatus.LOCAL_VERIFY)
        engine.run_verification(make_package(), outcome)
        assert state.verification_status in {"passed", "failed"}
        if state.verification_status == "passed":
            assert state.last_completed_stage == Stage.VERIFIED.value

    def test_interrupted_audit_leaves_state_readable(self, config) -> None:
        state = WorkflowState()
        state.transition(WorkflowStatus.CLAUDE_RUNNING, "audit interrupted")
        state.last_completed_stage = Stage.VERIFIED.value
        save_state(config.state_path, state)
        restored = load_state(config.state_path)
        assert restored.workflow_status is WorkflowStatus.CLAUDE_RUNNING
        assert stage_reached(restored.last_completed_stage, Stage.VERIFIED)
        assert not stage_reached(restored.last_completed_stage, Stage.AUDITED)

    def test_invalid_persisted_state_is_refused(self, config) -> None:
        from orchestration.state import StateSchemaError

        config.state_path.parent.mkdir(parents=True, exist_ok=True)
        config.state_path.write_text(
            json.dumps({"workflow_status": "NOT_A_REAL_STATUS"}), encoding="utf-8"
        )
        with pytest.raises(StateSchemaError):
            load_state(config.state_path)

    def test_a_resumed_run_keeps_its_workflow_id(self, config) -> None:
        state = WorkflowState()
        first = orchestrator_cli._heartbeat(config, state)
        identifier = state.workflow_id
        assert identifier == first.record.workflow_id
        second = orchestrator_cli._heartbeat(config, state)
        assert second.record.workflow_id == identifier


# --------------------------------------------------------------- generalization


class TestReleaseGeneralization:
    def test_goal_slug_is_filename_safe(self, config) -> None:
        assert config.release_goal == "v1.2"
        assert config.goal_slug == "v1_2"

    @pytest.mark.parametrize("goal", ["v1.2", "v1.3", "v2.0"])
    def test_future_goals_are_accepted(self, config, goal: str) -> None:
        from dataclasses import replace

        updated = replace(config, release_goal=goal)
        assert updated.release_goal == goal
        assert updated.goal_slug == goal.replace(".", "_")

    def test_goal_override_beats_configuration(self, config) -> None:
        from types import SimpleNamespace

        assert orchestrator_cli._goal(config, SimpleNamespace(goal=None)) == "v1.2"
        assert orchestrator_cli._goal(config, SimpleNamespace(goal="v2.0")) == "v2.0"

    def test_no_version_number_is_hard_coded_in_the_orchestrator(self) -> None:
        source = (TOOLS / "orchestrator.py").read_text(encoding="utf-8")
        assert "v1_1" not in source
        assert "v1.1" not in source

    def test_a_v1_2_package_name_round_trips(self, config, repo) -> None:
        package = make_package(name="v1_2_field_units")
        directory = config.subdir("work_packages")
        path = directory / "v1_2_field_units.json"
        save_package(path, package)
        from orchestration.workpackage import load_package

        assert load_package(path).name == "v1_2_field_units"


# ---------------------------------------------------------------- science guard


class TestScienceFirewallPreserved:
    def test_protected_paths_are_still_enforced(self, config, repo) -> None:
        from orchestration.verify import check_protected_artifacts

        ok, detail = check_protected_artifacts(config)
        assert ok, detail
        (repo / "protected.csv").write_text("tampered\n", encoding="utf-8")
        tampered_ok, tampered_detail = check_protected_artifacts(config)
        assert not tampered_ok
        assert "protected.csv" in tampered_detail

    def test_v2_modules_touch_no_scientific_path(self) -> None:
        for module in ("roles.py", "heartbeat.py", "auditdebt.py"):
            source = (TOOLS / "orchestration" / module).read_text(encoding="utf-8")
            assert "pvt_phase_simulator" not in source
            assert "golden_master" not in source

    def test_firewall_status_is_reported_from_verification(self, config) -> None:
        from orchestration.engine import StepOutcome

        state = WorkflowState()
        beat = hb.Heartbeat(config)
        engine = Engine(
            config,
            state,
            codex_runner=builder_stub("codex"),
            claude_runner=lambda *a, **k: None,
            heartbeat=beat,
        )
        outcome = StepOutcome(status=WorkflowStatus.LOCAL_VERIFY)
        engine.run_verification(make_package(), outcome)
        assert beat.record.science_firewall in {"SAFE", "VIOLATION"}


# ------------------------------------------------------------------------- CLI


class TestVerboseStatus:
    def _run_cli(self, config, repo, capsys, argv):
        state = WorkflowState()
        save_state(config.state_path, state)
        from types import SimpleNamespace

        args = SimpleNamespace(
            package=None,
            dry_run=False,
            allow_dirty=False,
            config=None,
            verbose="--verbose" in argv,
            goal=None,
            debt=None,
            reviewer=None,
            evidence=None,
        )
        code = orchestrator_cli.cmd_status(config, args)
        return code, capsys.readouterr().out

    def test_plain_status_stays_concise(self, config, repo, capsys) -> None:
        code, out = self._run_cli(config, repo, capsys, [])
        assert code == 0
        assert "Workflow status" in out
        assert "---- runtime" not in out

    def test_verbose_status_reports_no_runtime_when_none_exists(
        self, config, repo, capsys
    ) -> None:
        code, out = self._run_cli(config, repo, capsys, ["--verbose"])
        assert code == 0
        assert "---- runtime" in out
        assert "No runtime status recorded" in out

    def test_verbose_status_describes_a_live_run(self, config, repo, capsys) -> None:
        beat = hb.Heartbeat(config)
        beat.beat(
            package="field_units",
            stage="verifying",
            builder="claude",
            reviewer="codex",
            verification_gate="pytest",
            science_firewall="SAFE",
        )
        code, out = self._run_cli(config, repo, capsys, ["--verbose"])
        assert code == 0
        assert "ACTIVE PACKAGE  : field_units" in out
        assert "BUILDER         : claude" in out
        assert "REVIEWER        : codex" in out
        assert "CURRENT GATE    : pytest" in out
        assert "SCIENCE FIREWALL: SAFE" in out
        assert "ELAPSED" in out
        assert "LAST HEARTBEAT" in out

    def test_verbose_status_flags_a_dead_process(self, config, repo, capsys) -> None:
        beat = hb.Heartbeat(config)
        beat.record.pid = 2**31 - 1
        beat.beat(package="demo")
        code, out = self._run_cli(config, repo, capsys, ["--verbose"])
        assert "DEAD" in out
        assert "RUNNING         : NO" in out

    def test_verbose_status_flags_a_stale_heartbeat(self, config, repo, capsys) -> None:
        beat = hb.Heartbeat(config)
        beat.beat(package="demo")
        beat.record.last_heartbeat = time.time() - (hb.STALE_AFTER_SECONDS + 120)
        hb.write_heartbeat(config, beat.record)
        code, out = self._run_cli(config, repo, capsys, ["--verbose"])
        assert "STALE" in out or "DEAD" in out

    def test_cli_exposes_the_new_commands(self) -> None:
        assert "reconcile" in orchestrator_cli.COMMANDS
        assert "autopilot" in orchestrator_cli.COMMANDS

    def test_reconcile_lists_outstanding_debt(self, config, repo, capsys) -> None:
        from types import SimpleNamespace

        state = WorkflowState()
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
        save_state(config.state_path, state)

        args = SimpleNamespace(debt=None, reviewer=None, evidence=None)
        code = orchestrator_cli.cmd_reconcile(config, args)
        out = capsys.readouterr().out
        assert code == 0
        assert "demo@abc123abc123" in out
        assert "built by : claude" in out

    def test_reconcile_clears_and_persists(self, config, repo, capsys) -> None:
        from types import SimpleNamespace

        state = WorkflowState()
        debts: list[auditdebt.AuditDebt] = []
        debt = auditdebt.record(
            debts,
            package="demo",
            resulting_commit="abc123abc123",
            builder="claude",
            reviewer_required="codex",
            reason="codex unavailable",
        )
        state.deferred_independent_audits = auditdebt.dump(debts)
        save_state(config.state_path, state)

        args = SimpleNamespace(
            debt=debt.id, reviewer="codex", evidence="APPROVED, 0 blocking"
        )
        code = orchestrator_cli.cmd_reconcile(config, args)
        assert code == 0
        restored = load_state(config.state_path)
        reloaded = auditdebt.load(restored.deferred_independent_audits)
        assert auditdebt.open_debts(reloaded) == []

    def test_reconcile_refuses_a_self_review(self, config, repo, capsys) -> None:
        from types import SimpleNamespace

        state = WorkflowState()
        debts: list[auditdebt.AuditDebt] = []
        debt = auditdebt.record(
            debts,
            package="demo",
            resulting_commit="abc123abc123",
            builder="claude",
            reviewer_required="codex",
            reason="codex unavailable",
        )
        state.deferred_independent_audits = auditdebt.dump(debts)
        save_state(config.state_path, state)

        args = SimpleNamespace(debt=debt.id, reviewer="claude", evidence="fine")
        code = orchestrator_cli.cmd_reconcile(config, args)
        out = capsys.readouterr().out
        assert code == 1
        assert "refused" in out
        assert auditdebt.open_debts(
            auditdebt.load(load_state(config.state_path).deferred_independent_audits)
        )


# ------------------------------------------------------------------ retry caps


class TestLimitsPreserved:
    def test_correction_and_reaudit_caps_still_exist(self, config) -> None:
        assert config.limits.max_codex_correction_cycles == 2
        assert config.limits.max_claude_reaudit_cycles == 2

    def test_failover_does_not_reset_the_correction_counter(self, config) -> None:
        state = WorkflowState()
        state.codex_correction_cycles = 2
        engine = Engine(
            config,
            state,
            codex_runner=quota_exhausted_stub("codex"),
            claude_builder_runner=builder_stub("claude"),
            claude_runner=lambda *a, **k: None,
        )
        engine.run_builder(make_package())
        assert state.codex_correction_cycles == 2

    def test_each_builder_is_tried_at_most_once_per_run(self, config) -> None:
        calls: list[str] = []
        state = WorkflowState()
        engine = Engine(
            config,
            state,
            codex_runner=quota_exhausted_stub("codex", calls),
            claude_builder_runner=quota_exhausted_stub("claude", calls),
            claude_runner=lambda *a, **k: None,
        )
        engine.run_builder(make_package())
        assert calls.count("codex") == 1
        assert calls.count("claude") == 1


class TestLegacyProvenance:
    def _legacy(self) -> list[auditdebt.AuditDebt]:
        return auditdebt.load(
            [
                {
                    "status": "PENDING_INDEPENDENT_AUDIT",
                    "package": "v1_1_application_release_qa",
                    "resulting_commit": "514d963",
                    "reason": "Claude finished the package as builder",
                }
            ]
        )

    def test_naming_a_builder_restores_the_independence_check(self) -> None:
        debts = self._legacy()
        debt = debts[0]
        assert debt.builder == "unknown"
        auditdebt.name_builder(debt, "claude")
        assert debt.builder == "claude"
        assert debt.reviewer_required == "codex"
        with pytest.raises(auditdebt.DebtError, match="cannot supply"):
            auditdebt.reconcile(
                debts, identifier=debt.id, reviewer="claude", evidence="self"
            )

    def test_recorded_provenance_is_never_rewritten(self) -> None:
        debts: list[auditdebt.AuditDebt] = []
        debt = auditdebt.record(
            debts,
            package="demo",
            resulting_commit="abc123abc123",
            builder="codex",
            reviewer_required="claude",
            reason="claude unavailable",
        )
        with pytest.raises(auditdebt.DebtError, match="already records"):
            auditdebt.name_builder(debt, "claude")

    def test_reconcile_can_name_the_builder_inline(self) -> None:
        debts = self._legacy()
        debt = debts[0]
        auditdebt.reconcile(
            debts,
            identifier=debt.id,
            reviewer="codex",
            evidence="independent Codex review, APPROVED",
            builder="claude",
        )
        assert debt.builder == "claude"
        assert debt.cleared_by == "codex"
        assert not debt.is_open

    def test_naming_requires_a_value(self) -> None:
        debts = self._legacy()
        with pytest.raises(auditdebt.DebtError, match="requires a value"):
            auditdebt.name_builder(debts[0], "  ")
