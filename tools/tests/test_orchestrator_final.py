"""Final Orchestrator v2 blockers: submodules, workflow identity, corrections.

Every agent boundary is mocked. These never spend a real Codex or Claude call.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

from orchestration import agents, evidence, roles  # noqa: E402
from orchestration import resume as resume_mod  # noqa: E402
from orchestration.config import (  # noqa: E402
    AgentConfig,
    Limits,
    OrchestratorConfig,
)
from orchestration.engine import Engine  # noqa: E402
from orchestration.gitops import read_repo  # noqa: E402
from orchestration.roles import AgentIdentity  # noqa: E402
from orchestration.state import Stage, WorkflowState, WorkflowStatus  # noqa: E402
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
            max_codex_correction_cycles=3,
            max_claude_reaudit_cycles=3,
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
        "audit_policy": AuditPolicy.IMMEDIATE,
        "commit_policy": CommitPolicy.AFTER_AUDIT,
    }
    base.update(overrides)
    return WorkPackage(**base)  # type: ignore[arg-type]


def saved_package(config, package) -> Path:
    directory = config.ai_dir / "work_packages"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{package.name}.json"
    save_package(path, package)
    return path


# ------------------------------------------------------------------- doubles


def _contract(payload: dict) -> str:
    import json

    return (
        "<ORCHESTRATOR_RESULT>\n" + json.dumps(payload) + "\n</ORCHESTRATOR_RESULT>\n"
    )


def recording_builder(name: str, log: list[str], *, kind: str = "build"):
    """A builder that records who ran and persists a transcript."""

    def runner(config, order_path, *, stem, **kwargs):
        log.append(f"{name}:{kind}")
        (config.repo / "work.txt").write_text(
            f"authored by {name} ({len(log)})\n", encoding="utf-8"
        )
        body = _contract(
            {
                "status": "COMPLETE",
                "tests_claimed": "green",
                "files_changed": ["work.txt"],
                "ready_for_local_verification": True,
            }
        )
        run = agents.AgentRun(
            name=name,
            command=[f"{name}-stub"],
            exit_code=0,
            stdout=body,
            stderr="",
            raw_report=body,
        )
        run.contract = agents.validate_builder_contract(agents.parse_contract(body))
        transcript = config.subdir(f"{name}_reports") / f"{stem}.md"
        transcript.write_text(body, encoding="utf-8")
        run.transcript_path = transcript
        return run

    return runner


def scripted_auditor(name: str, log: list[str], verdicts: list[str]):
    """A reviewer returning a scripted sequence of verdicts."""

    state = {"i": 0}

    def runner(config, prompt, *, stem, **kwargs):
        index = min(state["i"], len(verdicts) - 1)
        verdict = verdicts[index]
        state["i"] += 1
        log.append(f"{name}:audit:{verdict}")
        findings = (
            []
            if verdict == "APPROVED"
            else [
                {
                    "id": "F1",
                    "severity": "B",
                    "blocks": True,
                    "summary": "needs a correction",
                }
            ]
        )
        body = _contract({"verdict": verdict, "findings": findings})
        run = agents.AgentRun(
            name=name,
            command=[],
            exit_code=0,
            stdout=body,
            stderr="",
            raw_report=body,
        )
        run.contract = agents.validate_audit_contract(agents.parse_contract(body))
        return run

    return runner


def unavailable_builder(name: str, log: list[str]):
    def runner(config, order_path, *, stem, **kwargs):
        log.append(f"{name}:unavailable")
        raise agents.AgentUnavailable(f"{name} CLI not found")

    return runner


# ============================================ submodule fingerprint safety


def _make_submodule(repo: Path, tmp_path: Path, name: str = "sub"):
    inner = tmp_path / f"inner-{name}"
    inner.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=inner, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"], cwd=inner, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=inner, check=True)
    (inner / "a.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=inner, check=True)
    subprocess.run(["git", "commit", "-qm", "one"], cwd=inner, check=True)

    added = subprocess.run(
        [
            "git",
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            "-q",
            str(inner),
            name,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if added.returncode != 0:
        pytest.skip(f"submodule unsupported here: {added.stderr.strip()}")
    subprocess.run(["git", "commit", "-qm", "add submodule"], cwd=repo, check=True)
    return inner, repo / name


class TestSubmoduleReusePolicy:
    """A submodule is reusable only when it is pristine; otherwise refuse."""

    def _state(self, repo) -> WorkflowState:
        state = WorkflowState()
        state.current_work_package = "demo"
        state.builder = "codex"
        state.base_commit = read_repo(repo).head
        state.last_completed_stage = Stage.BUILT.value
        state.workflow_status = WorkflowStatus.LOCAL_VERIFY
        (repo / "work.txt").write_text("built\n", encoding="utf-8")
        return state

    def _resume(self, config, repo):
        return resume_mod.plan(
            config,
            self._state(repo),
            make_package(),
            read_repo(repo),
            roles.availability_map(config),
        )

    # 1 -----------------------------------------------------------------
    def test_a_clean_initialized_submodule_gives_a_stable_fingerprint(
        self, config, repo, tmp_path
    ) -> None:
        _make_submodule(repo, tmp_path)
        first = evidence.tree_fingerprint(config, make_package())
        assert evidence.tree_fingerprint(config, make_package()) == first

    def test_a_clean_submodule_records_path_index_and_head(
        self, config, repo, tmp_path
    ) -> None:
        _inner, working = _make_submodule(repo, tmp_path)
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=working,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        described = evidence._submodule_state(repo, "sub", head)
        assert "path=sub" in described
        assert f"index={head}" in described
        assert f"head={head}" in described

    # 2 -----------------------------------------------------------------
    def test_a_dirty_tracked_file_refuses(self, config, repo, tmp_path) -> None:
        _inner, working = _make_submodule(repo, tmp_path)
        (working / "a.txt").write_text("edited\n", encoding="utf-8")
        with pytest.raises(evidence.SubmoduleNotReusable, match="uncommitted"):
            evidence.tree_fingerprint(config, make_package())
        with pytest.raises(resume_mod.ResumeRefused):
            self._resume(config, repo)

    # 3 -----------------------------------------------------------------
    def test_different_dirty_content_is_still_refused(
        self, config, repo, tmp_path
    ) -> None:
        """Two different dirty trees must both refuse, not compare equal."""

        _inner, working = _make_submodule(repo, tmp_path)
        (working / "a.txt").write_text("edit one\n", encoding="utf-8")
        with pytest.raises(evidence.SubmoduleNotReusable):
            evidence.tree_fingerprint(config, make_package())
        (working / "a.txt").write_text("edit two\n", encoding="utf-8")
        with pytest.raises(evidence.SubmoduleNotReusable):
            evidence.tree_fingerprint(config, make_package())

    # 4 -----------------------------------------------------------------
    def test_an_untracked_file_refuses(self, config, repo, tmp_path) -> None:
        _inner, working = _make_submodule(repo, tmp_path)
        (working / "stray.txt").write_text("stray\n", encoding="utf-8")
        with pytest.raises(evidence.SubmoduleNotReusable, match="untracked"):
            evidence.tree_fingerprint(config, make_package())
        with pytest.raises(resume_mod.ResumeRefused):
            self._resume(config, repo)

    # 5 -----------------------------------------------------------------
    def test_an_advanced_submodule_head_refuses(self, config, repo, tmp_path) -> None:
        _inner, working = _make_submodule(repo, tmp_path)
        (working / "a.txt").write_text("two\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=working, check=True)
        subprocess.run(["git", "commit", "-qm", "two"], cwd=working, check=True)
        with pytest.raises(evidence.SubmoduleNotReusable, match="checked out at"):
            evidence.tree_fingerprint(config, make_package())
        with pytest.raises(resume_mod.ResumeRefused):
            self._resume(config, repo)

    # 6 -----------------------------------------------------------------
    def test_an_uninitialized_submodule_refuses(self, config, repo, tmp_path) -> None:
        _inner, working = _make_submodule(repo, tmp_path)
        shutil.rmtree(working)
        with pytest.raises(evidence.SubmoduleNotReusable, match="not checked out"):
            evidence.tree_fingerprint(config, make_package())
        with pytest.raises(resume_mod.ResumeRefused):
            self._resume(config, repo)

    # 7 -----------------------------------------------------------------
    def test_a_directory_that_is_not_an_independent_worktree_refuses(
        self, config, repo, tmp_path
    ) -> None:
        """Git resolves upwards, so a bare directory answers from the parent."""

        _inner, working = _make_submodule(repo, tmp_path)
        shutil.rmtree(working)
        working.mkdir()
        (working / "a.txt").write_text("looks right\n", encoding="utf-8")
        assert not (working / ".git").exists()

        with pytest.raises(
            evidence.SubmoduleNotReusable, match="not an independent git worktree"
        ):
            evidence.tree_fingerprint(config, make_package())
        with pytest.raises(resume_mod.ResumeRefused):
            self._resume(config, repo)

    def test_the_parent_head_is_never_mistaken_for_the_submodule_head(
        self, config, repo, tmp_path
    ) -> None:
        """Proves the hazard is real and that the check is what blocks it."""

        _inner, working = _make_submodule(repo, tmp_path)
        shutil.rmtree(working)
        working.mkdir()

        # Git really does answer from the parent here.
        leaked = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=working,
            capture_output=True,
            text=True,
        )
        assert leaked.returncode == 0
        assert leaked.stdout.strip() == read_repo(repo).head

        # And the fingerprint refuses rather than recording that value.
        with pytest.raises(evidence.SubmoduleNotReusable):
            evidence._submodule_state(repo, "sub", "0" * 40)

    # 8 -----------------------------------------------------------------
    def test_an_unreadable_submodule_refuses(
        self, config, repo, tmp_path, monkeypatch
    ) -> None:
        _make_submodule(repo, tmp_path)
        from orchestration import evidence as evidence_module

        real_git = evidence_module.git

        def exploding_git(target, *args, **kwargs):
            if "HEAD" in args:
                raise RuntimeError("object store is unreadable")
            return real_git(target, *args, **kwargs)

        monkeypatch.setattr(evidence_module, "git", exploding_git)
        with pytest.raises(evidence.SubmoduleUnreadable, match="cannot read HEAD"):
            evidence.tree_fingerprint(config, make_package())
        with pytest.raises(resume_mod.ResumeRefused):
            self._resume(config, repo)

    # 9 -----------------------------------------------------------------
    def test_a_clean_matching_submodule_allows_evidence_reuse(
        self, config, repo, tmp_path
    ) -> None:
        _make_submodule(repo, tmp_path)
        state = self._state(repo)
        state.last_completed_stage = Stage.VERIFIED.value
        state.verification_status = "passed"
        state.tree_fingerprint = evidence.tree_fingerprint(
            config, make_package(), base_commit=state.base_commit
        )
        ok, reason = resume_mod.verification_evidence_valid(
            config, state, make_package()
        )
        assert ok, reason

    def test_a_submodule_going_dirty_after_verification_refuses_reuse(
        self, config, repo, tmp_path
    ) -> None:
        _inner, working = _make_submodule(repo, tmp_path)
        state = self._state(repo)
        state.last_completed_stage = Stage.VERIFIED.value
        state.verification_status = "passed"
        state.tree_fingerprint = evidence.tree_fingerprint(
            config, make_package(), base_commit=state.base_commit
        )
        (working / "a.txt").write_text("changed after\n", encoding="utf-8")
        with pytest.raises(resume_mod.ResumeRefused):
            resume_mod.verification_evidence_valid(config, state, make_package())

    def test_a_verification_over_a_dirty_submodule_records_no_fingerprint(
        self, config, repo, tmp_path
    ) -> None:
        """The gate still passes; it simply leaves nothing reusable behind."""

        from orchestration.engine import StepOutcome

        _inner, working = _make_submodule(repo, tmp_path)
        (working / "a.txt").write_text("dirty\n", encoding="utf-8")
        state = WorkflowState()
        engine = Engine(
            config,
            state,
            codex_runner=recording_builder("codex", []),
            claude_runner=lambda *a, **k: None,
        )
        # The submodule is in scope here, so the gates themselves pass and the
        # only question left is whether a fingerprint gets recorded.
        package = make_package(allowed_files=("work.txt", "sub"))
        outcome = StepOutcome(status=WorkflowStatus.LOCAL_VERIFY)
        report = engine.run_verification(package, outcome)
        assert report.passed, report.summary()
        assert state.tree_fingerprint is None
        assert any("no reusable tree fingerprint" in m for m in outcome.messages)


# ============================================ strict workflow identity


class TestStrictWorkflowIdentity:
    def _record(self, tmp_path: Path, workflow_id):
        report = tmp_path / "report.md"
        report.write_text("builder said this\n", encoding="utf-8")
        return evidence.record_builder_evidence(
            builder="codex",
            package="demo",
            workflow_id=workflow_id,
            report_path=report,
        )

    def test_an_exact_match_passes(self, tmp_path) -> None:
        record = self._record(tmp_path, "wf-1")
        assert evidence.load_builder_evidence(
            record,
            package="demo",
            expected_builder="codex",
            expected_workflow_id="wf-1",
        )

    def test_a_missing_workflow_id_is_rejected(self, tmp_path) -> None:
        record = self._record(tmp_path, None)
        with pytest.raises(evidence.EvidenceRefused, match="no workflow identity"):
            evidence.load_builder_evidence(
                record,
                package="demo",
                expected_builder="codex",
                expected_workflow_id="wf-1",
            )

    def test_an_empty_workflow_id_is_rejected(self, tmp_path) -> None:
        record = self._record(tmp_path, "")
        with pytest.raises(evidence.EvidenceRefused, match="no workflow identity"):
            evidence.load_builder_evidence(
                record,
                package="demo",
                expected_builder="codex",
                expected_workflow_id="wf-1",
            )

    def test_a_different_workflow_id_is_rejected(self, tmp_path) -> None:
        record = self._record(tmp_path, "wf-2")
        with pytest.raises(evidence.EvidenceRefused, match="belongs to workflow"):
            evidence.load_builder_evidence(
                record,
                package="demo",
                expected_builder="codex",
                expected_workflow_id="wf-1",
            )

    def test_legacy_evidence_needs_the_explicit_opt_in(self, tmp_path) -> None:
        record = self._record(tmp_path, None)
        assert evidence.load_builder_evidence(
            record,
            package="demo",
            expected_builder="codex",
            expected_workflow_id="wf-1",
            allow_missing_workflow_id=True,
        )

    def test_normal_resume_never_opts_in(self) -> None:
        source = (TOOLS / "orchestration" / "engine.py").read_text(encoding="utf-8")
        assert "allow_missing_workflow_id" not in source

    def test_a_resume_stops_on_a_workflow_mismatch(self, config, repo) -> None:
        state = WorkflowState()
        state.current_work_package = "demo"
        state.builder = "codex"
        state.workflow_id = "wf-current"
        state.base_commit = read_repo(repo).head
        state.last_completed_stage = Stage.BUILT.value
        state.workflow_status = WorkflowStatus.LOCAL_VERIFY
        state.revisions = [{"author": "codex", "kind": "build", "revision": 1}]
        (repo / "work.txt").write_text("built earlier\n", encoding="utf-8")

        report = config.subdir("codex_reports") / "old.md"
        report.write_text("from another run\n", encoding="utf-8")
        state.builder_evidence = evidence.record_builder_evidence(
            builder="codex",
            package="demo",
            workflow_id="wf-other",
            report_path=report,
            revision=1,
        ).to_dict()

        package = make_package(audit_policy=AuditPolicy.NONE)
        engine = Engine(
            config,
            state,
            codex_runner=recording_builder("codex", []),
            claude_runner=lambda *a, **k: None,
        )
        plan = resume_mod.plan(
            config,
            state,
            package,
            read_repo(repo),
            roles.availability_map(config),
        )
        outcome = engine.execute(
            package, saved_package(config, package), resume_plan=plan
        )
        assert outcome.status is WorkflowStatus.HUMAN_ACTION_REQUIRED
        assert "belongs to workflow" in (outcome.human_action or "")


# ============================================ real correction ownership


class TestRealCorrectionFlow:
    def _engine(self, config, state, log, *, verdicts_for):
        """Both agents can build and both can review; the engine chooses."""

        return Engine(
            config,
            state,
            codex_runner=recording_builder("codex", log),
            claude_builder_runner=recording_builder("claude", log),
            claude_runner=scripted_auditor("claude", log, verdicts_for["claude"]),
            codex_auditor_runner=scripted_auditor("codex", log, verdicts_for["codex"]),
        )

    def test_codex_builds_claude_audits_claude_corrects_codex_reaudits(
        self, config, repo
    ) -> None:
        """The full flow, executed - not simulated by editing revisions."""

        log: list[str] = []
        state = WorkflowState()
        package = make_package()
        engine = self._engine(
            config,
            state,
            log,
            # Claude rejects the build, forcing a correction; Codex then
            # approves the corrected revision.
            verdicts_for={"claude": ["NOT_APPROVED"], "codex": ["APPROVED"]},
        )
        outcome = engine.execute(package, saved_package(config, package))

        assert log[0] == "codex:build"
        assert log[1] == "claude:audit:NOT_APPROVED"
        assert log[2] == "claude:build", "the reviewer authors the correction"
        assert log[3] == "codex:audit:APPROVED", "the builder re-audits"
        assert outcome.status is WorkflowStatus.APPROVED
        assert [entry["author"] for entry in state.revisions] == ["codex", "claude"]

    def test_claude_builds_codex_audits_codex_corrects_claude_reaudits(
        self, config, repo
    ) -> None:
        log: list[str] = []
        state = WorkflowState()
        package = make_package()
        engine = Engine(
            config,
            state,
            codex_runner=recording_builder("codex", log),
            claude_builder_runner=recording_builder("claude", log),
            claude_runner=scripted_auditor("claude", log, ["APPROVED"]),
            codex_auditor_runner=scripted_auditor("codex", log, ["NOT_APPROVED"]),
            preferred_builder=AgentIdentity.CLAUDE,
        )
        outcome = engine.execute(package, saved_package(config, package))

        assert log[0] == "claude:build"
        assert log[1] == "codex:audit:NOT_APPROVED"
        assert log[2] == "codex:build", "the reviewer authors the correction"
        assert log[3] == "claude:audit:APPROVED", "the builder re-audits"
        assert outcome.status is WorkflowStatus.APPROVED
        assert [entry["author"] for entry in state.revisions] == ["claude", "codex"]

    def test_the_correction_author_never_reviews_its_own_revision(
        self, config, repo
    ) -> None:
        log: list[str] = []
        state = WorkflowState()
        package = make_package()
        engine = self._engine(
            config,
            state,
            log,
            verdicts_for={"claude": ["NOT_APPROVED"], "codex": ["APPROVED"]},
        )
        engine.execute(package, saved_package(config, package))

        authors = [entry["author"] for entry in state.revisions]
        audits = [line for line in log if ":audit:" in line]
        # The agent that authored the final revision is not the one that
        # approved it.
        assert authors[-1] == "claude"
        assert audits[-1].startswith("codex")

    def test_persisted_correction_evidence_names_the_correction_author(
        self, config, repo
    ) -> None:
        log: list[str] = []
        state = WorkflowState()
        package = make_package()
        engine = self._engine(
            config,
            state,
            log,
            verdicts_for={"claude": ["NOT_APPROVED"], "codex": ["APPROVED"]},
        )
        engine.execute(package, saved_package(config, package))

        record = evidence.BuilderEvidence.from_dict(state.builder_evidence)
        assert record is not None
        assert record.builder == "claude", "evidence must name the corrector"
        assert record.kind == "correction"
        assert record.revision == 2
        assert evidence.load_builder_evidence(
            record,
            package="demo",
            expected_builder="claude",
            expected_revision=2,
        )

    def test_an_unavailable_corrector_falls_over_and_stays_independent(
        self, config, repo
    ) -> None:
        """Failover must not let one agent author and review the same diff."""

        log: list[str] = []
        state = WorkflowState()
        package = make_package()
        engine = Engine(
            config,
            state,
            codex_runner=recording_builder("codex", log),
            claude_builder_runner=unavailable_builder("claude", log),
            claude_runner=scripted_auditor("claude", log, ["NOT_APPROVED"]),
            codex_auditor_runner=scripted_auditor("codex", log, ["APPROVED"]),
        )
        engine.execute(package, saved_package(config, package))

        # Claude was the preferred corrector and could not run.
        assert "claude:unavailable" in log
        author = engine.current_author()
        reviewer = roles.COUNTERPART[author]
        assert reviewer != author
        roles.assert_independent(author, reviewer)

    def test_both_correctors_unavailable_stops_safely(self, config, repo) -> None:
        log: list[str] = []
        state = WorkflowState()
        package = make_package()
        engine = Engine(
            config,
            state,
            codex_runner=recording_builder("codex", log),
            claude_builder_runner=unavailable_builder("claude", log),
            claude_runner=scripted_auditor("claude", log, ["NOT_APPROVED"]),
            codex_auditor_runner=scripted_auditor("codex", log, ["APPROVED"]),
        )
        # Make the fallback corrector unavailable as well, after the build.
        original = engine._dispatch_builder
        calls = {"n": 0}

        def failing_after_build(builder, package_, order_path):
            calls["n"] += 1
            if calls["n"] == 1:
                return original(builder, package_, order_path)
            raise agents.AgentUnavailable(f"{builder.value} CLI not found")

        engine._dispatch_builder = failing_after_build  # type: ignore[method-assign]
        outcome = engine.execute(package, saved_package(config, package))
        assert outcome.status is WorkflowStatus.HUMAN_ACTION_REQUIRED

    def test_the_corrector_is_chosen_from_the_current_author(
        self, config, repo
    ) -> None:
        """Source-level guard against reverting to 'prefer the original builder'."""

        source = (TOOLS / "orchestration" / "engine.py").read_text(encoding="utf-8")
        assert (
            "preferred_corrector = roles.COUNTERPART[self.current_author()]" in source
        )
