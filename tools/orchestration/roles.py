"""Agent identity, availability, failover, and review-independence rules.

v1 hard-coded the roles: Codex built and Claude audited. That worked until Codex
exhausted its quota mid-run, and the workflow had no way to say "the other agent
builds instead". This module makes the roles data rather than assumption, and
enforces the one invariant that must never bend: **the builder cannot be its own
independent reviewer.**
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from . import agents
from .config import AgentConfig, OrchestratorConfig

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .agents import AgentRun


class AgentIdentity(StrEnum):
    """Every agent the orchestrator is permitted to drive."""

    CODEX = "codex"
    CLAUDE = "claude"


#: The permitted builder/reviewer pairing. With two agents this is an involution,
#: but the lookup keeps the rule explicit rather than implied by ``!=``.
COUNTERPART: Final[dict[AgentIdentity, AgentIdentity]] = {
    AgentIdentity.CODEX: AgentIdentity.CLAUDE,
    AgentIdentity.CLAUDE: AgentIdentity.CODEX,
}


class Unavailable(StrEnum):
    """Why an agent cannot be used right now."""

    NONE = "none"
    NOT_FOUND = "executable_not_found"
    QUOTA_EXHAUSTED = "quota_exhausted"
    LAUNCH_FAILURE = "launch_failure"


#: Markers that identify a *temporary* capacity failure rather than a defect in
#: the work. A contract error or a failing gate is never one of these: those mean
#: the run was bad, not that the agent was absent.
QUOTA_MARKERS: Final = (
    "usage limit",
    "quota limit",
    "quota exceeded",
    "quota_exceeded",
    "rate limit",
    "rate_limit",
    "credit balance",
    "insufficient credit",
    "too many requests",
)

#: Markers that identify a failure to start the process at all.
LAUNCH_MARKERS: Final = (
    "no such file or directory",
    "is not recognized as an internal or external command",
    "cannot find the path",
    "permission denied",
    "winerror 2",
    "winerror 5",
    "oserror",
)


class ReviewIndependenceError(RuntimeError):
    """Raised when a reviewer assignment would let a builder audit itself."""


class NoBuilderAvailable(RuntimeError):
    """Raised when no permitted agent can build."""


@dataclass(frozen=True, slots=True)
class Availability:
    """One agent's current usability and why."""

    agent: AgentIdentity
    available: bool
    detail: str
    reason: Unavailable = Unavailable.NONE

    def describe(self) -> str:
        if self.available:
            return f"{self.agent.value}: available ({self.detail})"
        return f"{self.agent.value}: unavailable ({self.reason.value}: {self.detail})"


def agent_config(config: OrchestratorConfig, agent: AgentIdentity) -> AgentConfig:
    return config.codex if agent is AgentIdentity.CODEX else config.claude


def probe(
    config: OrchestratorConfig,
    agent: AgentIdentity,
    *,
    injected: frozenset[AgentIdentity] = frozenset(),
    unavailable: frozenset[AgentIdentity] = frozenset(),
) -> Availability:
    """Report whether one agent can be used.

    ``injected`` marks agents supplied by a test double, which are always usable.
    ``unavailable`` marks agents the current run has already observed to be out
    of capacity, so a quota failure is not rediscovered by calling the CLI again.
    """

    # Observed capacity loss outranks everything, including a test double:
    # an agent this run has already seen fail is not usable just because a
    # runner object exists for it.
    if agent in unavailable:
        return Availability(
            agent,
            False,
            "observed out of capacity this run",
            Unavailable.QUOTA_EXHAUSTED,
        )
    if agent in injected:
        return Availability(agent, True, "injected runner")
    ok, detail = agents.agent_available(agent_config(config, agent))
    if ok:
        return Availability(agent, True, detail)
    return Availability(agent, False, detail, Unavailable.NOT_FOUND)


def availability_map(
    config: OrchestratorConfig,
    *,
    injected: frozenset[AgentIdentity] = frozenset(),
    unavailable: frozenset[AgentIdentity] = frozenset(),
) -> dict[AgentIdentity, Availability]:
    return {
        agent: probe(config, agent, injected=injected, unavailable=unavailable)
        for agent in AgentIdentity
    }


def classify_run_failure(run: AgentRun) -> Unavailable:
    """Decide whether a failed run means the agent is unusable, not just wrong.

    A non-zero exit is necessary but never sufficient: an agent that ran and
    returned a bad contract is available and produced bad work, which is a very
    different situation from an agent that could not run at all.
    """

    if run.exit_code == 0:
        return Unavailable.NONE
    combined = "\n".join(
        part for part in (run.stderr, run.stdout, run.raw_report) if part
    ).lower()
    if any(marker in combined for marker in QUOTA_MARKERS):
        return Unavailable.QUOTA_EXHAUSTED
    if any(marker in combined for marker in LAUNCH_MARKERS):
        return Unavailable.LAUNCH_FAILURE
    return Unavailable.NONE


def is_capacity_failure(run: AgentRun) -> bool:
    """True when a failed run should trigger failover rather than escalation."""

    return classify_run_failure(run) is not Unavailable.NONE


@dataclass(frozen=True, slots=True)
class RoleAssignment:
    """Who builds, who reviews, and how that was decided."""

    builder: AgentIdentity
    reviewer: AgentIdentity | None
    reason: str
    reviewer_deferred: bool = False
    reviewer_reason: str = ""
    previous_builder: AgentIdentity | None = None

    @property
    def failed_over(self) -> bool:
        return (
            self.previous_builder is not None and self.previous_builder != self.builder
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "builder": self.builder.value,
            "reviewer": None if self.reviewer is None else self.reviewer.value,
            "reviewer_deferred": self.reviewer_deferred,
            "reason": self.reason,
            "reviewer_reason": self.reviewer_reason,
            "previous_builder": (
                None if self.previous_builder is None else self.previous_builder.value
            ),
            "failed_over": self.failed_over,
        }


def assert_independent(builder: AgentIdentity, reviewer: AgentIdentity | None) -> None:
    """The one rule that never bends."""

    if reviewer is not None and reviewer == builder:
        raise ReviewIndependenceError(
            f"{builder.value} cannot independently review its own work; "
            "an independent review requires the other agent"
        )


def select_builder(
    availability: dict[AgentIdentity, Availability],
    *,
    preferred: AgentIdentity = AgentIdentity.CODEX,
    previous: AgentIdentity | None = None,
) -> tuple[AgentIdentity, str]:
    """Choose a builder, falling back to the counterpart when the preferred one
    cannot run. Raises when neither agent is usable."""

    chosen = availability.get(preferred)
    if chosen is not None and chosen.available:
        return preferred, f"preferred builder {preferred.value} is available"
    alternate = COUNTERPART[preferred]
    if availability.get(alternate) is not None and availability[alternate].available:
        blocked = availability[preferred]
        return alternate, (
            f"{preferred.value} unavailable ({blocked.reason.value}); "
            f"{alternate.value} takes over as builder"
        )
    raise NoBuilderAvailable(
        "no permitted builder is available: "
        + "; ".join(availability[agent].describe() for agent in AgentIdentity)
    )


def select_reviewer(
    builder: AgentIdentity,
    availability: dict[AgentIdentity, Availability],
) -> tuple[AgentIdentity | None, bool, str]:
    """Choose the independent reviewer for a given builder.

    Returns ``(reviewer, deferred, reason)``. The reviewer is never the builder.
    When the required counterpart cannot run, the review is *deferred* - it is
    never reassigned to the builder and never silently treated as done.
    """

    required = COUNTERPART[builder]
    status = availability.get(required)
    if status is not None and status.available:
        assert_independent(builder, required)
        return (
            required,
            False,
            f"{required.value} is available to review {builder.value}",
        )
    detail = "unknown" if status is None else status.describe()
    return (
        None,
        True,
        (
            f"independent review by {required.value} is required because "
            f"{builder.value} built this package, but {detail}"
        ),
    )


def assign_roles(
    config: OrchestratorConfig,
    *,
    preferred_builder: AgentIdentity = AgentIdentity.CODEX,
    injected: frozenset[AgentIdentity] = frozenset(),
    unavailable: frozenset[AgentIdentity] = frozenset(),
    previous_builder: AgentIdentity | None = None,
) -> RoleAssignment:
    """Resolve the full builder/reviewer assignment for one package."""

    availability = availability_map(config, injected=injected, unavailable=unavailable)
    builder, reason = select_builder(
        availability, preferred=preferred_builder, previous=previous_builder
    )
    reviewer, deferred, reviewer_reason = select_reviewer(builder, availability)
    return RoleAssignment(
        builder=builder,
        reviewer=reviewer,
        reason=reason,
        reviewer_deferred=deferred,
        reviewer_reason=reviewer_reason,
        previous_builder=previous_builder,
    )
