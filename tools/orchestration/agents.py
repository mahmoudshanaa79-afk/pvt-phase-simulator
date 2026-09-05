"""Agent transports and their strict machine-readable output contracts.

Codex is the builder; Claude is the independent auditor. Neither agent's prose
is trusted: every run must end with an ``<ORCHESTRATOR_RESULT>`` block holding
JSON. A missing or malformed block never means approval.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from .config import AgentConfig, OrchestratorConfig

RESULT_PATTERN = re.compile(
    r"<ORCHESTRATOR_RESULT>\s*(?P<body>\{.*?\})\s*</ORCHESTRATOR_RESULT>",
    re.DOTALL,
)

VALID_VERDICTS = frozenset({"APPROVED", "CONDITIONAL", "NOT_APPROVED"})
VALID_PROVISIONAL_VERDICTS = frozenset({"APPROVED", "NOT_APPROVED"})

#: Tools Claude may use while auditing: read and investigate, never mutate.
AUDIT_ALLOWED_TOOLS = "Read,Glob,Grep,Bash,TodoWrite"

#: Tools explicitly withheld during an audit.
AUDIT_DISALLOWED_TOOLS = "Edit,Write,NotebookEdit,MultiEdit"


class ContractError(ValueError):
    """Raised when an agent's machine-readable block is missing or malformed."""


class AgentUnavailable(RuntimeError):
    """Raised when an agent CLI cannot be located."""


@dataclass(slots=True)
class AgentRun:
    """One agent invocation: raw transcript plus the parsed contract."""

    name: str
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    raw_report: str
    contract: dict[str, Any] | None = None
    contract_error: str | None = None
    transcript_path: Path | None = None
    duration_seconds: float = 0.0
    #: Reported spend for this invocation, or ``None`` when the agent did not
    #: report it. Never estimated or fabricated.
    cost_usd: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and self.contract is not None


def parse_contract(text: str) -> dict[str, Any]:
    """Extract and strictly parse the ORCHESTRATOR_RESULT block.

    The last block wins, so an agent quoting the template earlier in its prose
    cannot displace its real answer.
    """

    matches = list(RESULT_PATTERN.finditer(text or ""))
    if not matches:
        raise ContractError("no <ORCHESTRATOR_RESULT> block found in agent output")
    body = matches[-1].group("body")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise ContractError(
            f"ORCHESTRATOR_RESULT is not valid JSON: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise ContractError("ORCHESTRATOR_RESULT must be a JSON object")
    return payload


def validate_audit_contract(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate an auditor contract. Unknown verdicts are never approvals."""

    verdict = payload.get("verdict")
    if verdict not in VALID_VERDICTS:
        raise ContractError(
            f"verdict {verdict!r} is not one of {sorted(VALID_VERDICTS)}"
        )
    _validate_findings(payload)
    return payload


def _validate_findings(payload: dict[str, Any]) -> None:
    """Validate the shared structured finding contract."""

    findings = payload.get("findings", [])
    if not isinstance(findings, list):
        raise ContractError("findings must be a list")
    for item in findings:
        if not isinstance(item, dict):
            raise ContractError("each finding must be an object")
        for key in ("id", "severity", "blocks", "summary"):
            if key not in item:
                raise ContractError(f"finding missing required key {key!r}: {item}")
        if not isinstance(item["blocks"], bool):
            raise ContractError(f"finding {item['id']!r}: 'blocks' must be a boolean")
        if item["severity"] not in {"A", "B", "C", "D"}:
            raise ContractError(
                f"finding {item['id']!r}: severity must be A, B, C or D"
            )


def validate_provisional_review_contract(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a non-independent Codex review without blurring provenance."""

    verdict = payload.get("verdict")
    if verdict not in VALID_PROVISIONAL_VERDICTS:
        raise ContractError(
            f"provisional verdict {verdict!r} is not one of "
            f"{sorted(VALID_PROVISIONAL_VERDICTS)}"
        )
    if payload.get("review_type") != "PROVISIONAL_CODEX_REVIEW":
        raise ContractError(
            "provisional review must declare review_type='PROVISIONAL_CODEX_REVIEW'"
        )
    _validate_findings(payload)
    return payload


def validate_builder_contract(payload: dict[str, Any]) -> dict[str, Any]:
    status = payload.get("status")
    if status not in {"COMPLETE", "BLOCKED", "FAILED"}:
        raise ContractError(
            f"builder status {status!r} must be COMPLETE, BLOCKED or FAILED"
        )
    return payload


def blocking_findings(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [f for f in payload.get("findings", []) if f.get("blocks")]


def claude_temporarily_unavailable(run: AgentRun) -> tuple[bool, str]:
    """Recognize explicit quota/rate-limit failures without masking other errors."""

    combined = "\n".join((run.stderr, run.stdout, run.raw_report)).lower()
    markers = (
        "usage limit",
        "quota limit",
        "quota exceeded",
        "rate limit",
        "rate_limit",
        "credit balance",
    )
    hit = next((marker for marker in markers if marker in combined), None)
    if run.exit_code != 0 and hit is not None:
        return True, f"Claude temporarily unavailable ({hit}; exit {run.exit_code})"
    return False, ""


# --------------------------------------------------------------------- runner


#: Transient resolution misses happen when an agent CLI is mid-auto-update and
#: its versioned directory is briefly incomplete. Retry before escalating: a
#: momentary miss must not discard an otherwise-good run.
RESOLVE_ATTEMPTS: Final = 3
RESOLVE_BACKOFF_SECONDS: Final = 2.0


def _resolve(agent: AgentConfig, name: str) -> str:
    for attempt in range(RESOLVE_ATTEMPTS):
        executable = agent.resolve()
        if executable is not None:
            return executable
        if attempt < RESOLVE_ATTEMPTS - 1:
            time.sleep(RESOLVE_BACKOFF_SECONDS * (attempt + 1))
    raise AgentUnavailable(
        f"{name} CLI not found after {RESOLVE_ATTEMPTS} attempts "
        f"(executable={agent.executable!r}, "
        f"search_names={list(agent.search_names)}, "
        f"search_paths={list(agent.search_paths)})"
    )


def agent_available(agent: AgentConfig) -> tuple[bool, str]:
    executable = agent.resolve()
    if executable is None:
        return False, "not found"
    return True, executable


def _persist(config: OrchestratorConfig, subdir: str, stem: str, run: AgentRun) -> Path:
    directory = config.subdir(subdir)
    path = directory / f"{stem}.md"
    path.write_text(run.raw_report or run.stdout, encoding="utf-8")
    (directory / f"{stem}.transcript.json").write_text(
        json.dumps(
            {
                "name": run.name,
                "command": run.command,
                "exit_code": run.exit_code,
                "duration_seconds": run.duration_seconds,
                "cost_usd": run.cost_usd,
                "contract": run.contract,
                "contract_error": run.contract_error,
                "stdout": run.stdout[-200_000:],
                "stderr": run.stderr[-50_000:],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def run_codex(
    config: OrchestratorConfig,
    work_order: Path,
    *,
    stem: str,
    sandbox: str = "workspace-write",
) -> AgentRun:
    """Invoke the Codex builder non-interactively on a work-order file."""

    executable = _resolve(config.codex, "Codex")
    report_file = config.subdir("codex_reports") / f"{stem}.last-message.txt"
    command = [
        executable,
        "exec",
        "-s",
        sandbox,
        "-C",
        str(config.repo),
        "--output-last-message",
        str(report_file),
        *config.codex.args,
    ]
    started = time.time()
    completed = subprocess.run(
        command,
        cwd=str(config.repo),
        input=work_order.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        # Windows would otherwise encode stdin with the locale codepage, which
        # mangles non-ASCII prompt text into bytes the agent rejects.
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=config.codex.timeout_seconds,
    )
    raw = (
        report_file.read_text(encoding="utf-8")
        if report_file.exists()
        else completed.stdout
    )
    run = AgentRun(
        name="codex",
        command=command,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        raw_report=raw,
        duration_seconds=time.time() - started,
    )
    try:
        run.contract = validate_builder_contract(parse_contract(raw))
    except ContractError as error:
        run.contract_error = str(error)
    run.transcript_path = _persist(config, "codex_reports", stem, run)
    return run


def run_codex_review(
    config: OrchestratorConfig,
    prompt: Path,
    *,
    stem: str,
) -> AgentRun:
    """Invoke a fresh Codex process as a read-only, non-independent reviewer."""

    executable = _resolve(config.codex, "Codex")
    report_file = config.subdir("provisional_reviews") / f"{stem}.last-message.txt"
    command = [
        executable,
        "exec",
        "-s",
        "read-only",
        "-C",
        str(config.repo),
        "--output-last-message",
        str(report_file),
        *config.codex.args,
    ]
    started = time.time()
    completed = subprocess.run(
        command,
        cwd=str(config.repo),
        input=prompt.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=config.codex.timeout_seconds,
    )
    raw = (
        report_file.read_text(encoding="utf-8")
        if report_file.exists()
        else completed.stdout
    )
    run = AgentRun(
        name="codex-provisional-review",
        command=command,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        raw_report=raw,
        duration_seconds=time.time() - started,
    )
    try:
        run.contract = validate_provisional_review_contract(parse_contract(raw))
    except ContractError as error:
        run.contract_error = str(error)
    run.transcript_path = _persist(config, "provisional_reviews", stem, run)
    return run


def run_claude_audit(
    config: OrchestratorConfig,
    prompt: Path,
    *,
    stem: str,
    allowed_tools: str = AUDIT_ALLOWED_TOOLS,
    disallowed_tools: str = AUDIT_DISALLOWED_TOOLS,
) -> AgentRun:
    """Invoke Claude Code headlessly as a strictly read-only auditor."""

    executable = _resolve(config.claude, "Claude Code")
    command = [
        executable,
        "--print",
        "--output-format",
        "json",
        "--permission-mode",
        "plan",
        "--allowed-tools",
        allowed_tools,
        "--disallowed-tools",
        disallowed_tools,
        "--add-dir",
        str(config.repo),
        # Native per-invocation ceiling; the orchestrator additionally tracks the
        # cumulative spend across audit and re-audit cycles.
        "--max-budget-usd",
        str(config.limits.max_claude_cost_usd_per_run),
        *config.claude.args,
    ]
    started = time.time()
    completed = subprocess.run(
        command,
        cwd=str(config.repo),
        input=prompt.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        # Same locale-codepage hazard as the builder transport.
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=config.claude.timeout_seconds,
    )

    # Claude's JSON envelope carries the assistant text in "result".
    text = completed.stdout
    envelope: dict[str, Any] | None = None
    try:
        envelope = json.loads(completed.stdout)
        if isinstance(envelope, dict):
            text = str(envelope.get("result", completed.stdout))
    except json.JSONDecodeError:
        envelope = None

    reported = (envelope or {}).get("total_cost_usd")
    cost = float(reported) if isinstance(reported, (int, float)) else None

    run = AgentRun(
        name="claude",
        command=command,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        raw_report=text,
        duration_seconds=time.time() - started,
        cost_usd=cost,
        extra={"cost_reported": cost is not None},
    )
    try:
        run.contract = validate_audit_contract(parse_contract(text))
    except ContractError as error:
        run.contract_error = str(error)
    run.transcript_path = _persist(config, "claude_audits", stem, run)
    return run


#: Tools Claude may use while *building*. Unlike an audit, a build must write.
BUILD_ALLOWED_TOOLS = "Read,Glob,Grep,Bash,Edit,Write,MultiEdit,TodoWrite"


def _claude_envelope_text(stdout: str) -> tuple[str, float | None]:
    """Unwrap Claude's JSON envelope into (assistant text, reported cost)."""

    text = stdout
    envelope: dict[str, Any] | None = None
    try:
        envelope = json.loads(stdout)
        if isinstance(envelope, dict):
            text = str(envelope.get("result", stdout))
    except json.JSONDecodeError:
        envelope = None
    reported = (envelope or {}).get("total_cost_usd")
    cost = float(reported) if isinstance(reported, (int, float)) else None
    return text, cost


def run_claude_builder(
    config: OrchestratorConfig,
    work_order: Path,
    *,
    stem: str,
) -> AgentRun:
    """Invoke Claude Code as a builder when it has taken over from Codex.

    This is the failover counterpart of :func:`run_codex`, and it is deliberately
    a different entry point from :func:`run_claude_audit`: building needs write
    tools, auditing must never have them, and keeping the two transports separate
    is what stops an audit from silently gaining edit permission.
    """

    executable = _resolve(config.claude, "Claude Code")
    command = [
        executable,
        "--print",
        "--output-format",
        "json",
        "--permission-mode",
        "acceptEdits",
        "--allowed-tools",
        BUILD_ALLOWED_TOOLS,
        "--add-dir",
        str(config.repo),
        "--max-budget-usd",
        str(config.limits.max_claude_cost_usd_per_run),
        *config.claude.args,
    ]
    started = time.time()
    completed = subprocess.run(
        command,
        cwd=str(config.repo),
        input=work_order.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=config.claude.timeout_seconds,
    )
    text, cost = _claude_envelope_text(completed.stdout)
    run = AgentRun(
        name="claude",
        command=command,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        raw_report=text,
        duration_seconds=time.time() - started,
        cost_usd=cost,
        extra={"role": "builder", "cost_reported": cost is not None},
    )
    try:
        run.contract = validate_builder_contract(parse_contract(text))
    except ContractError as error:
        run.contract_error = str(error)
    run.transcript_path = _persist(config, "claude_builds", stem, run)
    return run


def run_codex_audit(
    config: OrchestratorConfig,
    prompt: Path,
    *,
    stem: str,
) -> AgentRun:
    """Invoke Codex as the *independent* reviewer of work Claude built.

    Distinct from :func:`run_codex_review`, which is the non-independent
    provisional fallback used when Codex reviews work Codex itself built. This
    one carries the full auditor contract because it genuinely is independent.
    """

    executable = _resolve(config.codex, "Codex")
    report_file = config.subdir("codex_audits") / f"{stem}.last-message.txt"
    command = [
        executable,
        "exec",
        "-s",
        "read-only",
        "-C",
        str(config.repo),
        "--output-last-message",
        str(report_file),
        *config.codex.args,
    ]
    started = time.time()
    completed = subprocess.run(
        command,
        cwd=str(config.repo),
        input=prompt.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=config.codex.timeout_seconds,
    )
    raw = (
        report_file.read_text(encoding="utf-8")
        if report_file.exists()
        else completed.stdout
    )
    run = AgentRun(
        name="codex",
        command=command,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        raw_report=raw,
        duration_seconds=time.time() - started,
        extra={"role": "independent_reviewer"},
    )
    try:
        run.contract = validate_audit_contract(parse_contract(raw))
    except ContractError as error:
        run.contract_error = str(error)
    run.transcript_path = _persist(config, "codex_audits", stem, run)
    return run
