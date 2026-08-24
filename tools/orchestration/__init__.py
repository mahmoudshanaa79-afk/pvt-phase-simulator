"""Local multi-agent orchestration for the PVT simulator.

Codex builds, Claude audits independently, local gates decide. This package is
development tooling only: the scientific library in ``src/pvt_phase_simulator``
must never import from it.
"""

from __future__ import annotations

__all__ = [
    "agents",
    "config",
    "engine",
    "gitops",
    "lock",
    "prompts",
    "state",
    "verify",
    "workpackage",
]
