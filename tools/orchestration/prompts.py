"""Prompt generation for the builder and the auditor.

Audit prompts are written to *falsify* an implementation, never to confirm it.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

from .config import OrchestratorConfig
from .gitops import diff_stat, git, read_repo
from .verify import VerificationReport
from .workpackage import WorkPackage

BUILDER_CONTRACT = textwrap.dedent(
    """
    ## Required final output

    End your reply with exactly one machine-readable block:

    <ORCHESTRATOR_RESULT>
    {
      "status": "COMPLETE",
      "tests_claimed": "<what you ran and what it reported>",
      "files_changed": ["<path>", "..."],
      "ready_for_local_verification": true
    }
    </ORCHESTRATOR_RESULT>

    `status` must be COMPLETE, BLOCKED or FAILED. The orchestrator re-runs every
    check locally, so an inaccurate claim here will simply be caught.
    """
).strip()

AUDITOR_CONTRACT = textwrap.dedent(
    """
    ## Required final output

    Write the full human-readable audit first, then end with exactly one
    machine-readable block:

    <ORCHESTRATOR_RESULT>
    {
      "verdict": "APPROVED",
      "findings": [
        {"id": "C-1", "severity": "C", "blocks": true, "summary": "..."}
      ],
      "safe_defer": []
    }
    </ORCHESTRATOR_RESULT>

    `verdict` must be exactly one of APPROVED, CONDITIONAL, NOT_APPROVED.
    `severity` must be A (critical), B (major), C (moderate) or D (minor).
    `blocks` must be a boolean.

    If you cannot complete the audit, return NOT_APPROVED with a finding that
    explains why. A missing or malformed block is never read as approval.
    """
).strip()

AUDITOR_RULES = textwrap.dedent(
    """
    ## Your role and its limits

    You are an INDEPENDENT ADVERSARIAL AUDITOR. You did not write this code and
    you are not here to confirm it.

    - Do NOT modify, stage, or commit anything. You are read-only.
    - Do NOT regenerate any baseline or golden artifact.
    - Do NOT start new features or fix what you find — report it.
    - Re-derive equations independently where it matters; do not accept a
      formula because a comment or document agrees with the code.
    - Do not trust a test merely because it passes. Ask what it would fail on.
    - Prefer different numerical machinery from production when building a
      reference.
    - Distinguish a genuine defect from a cosmetic preference. Do not inflate.
    """
).strip()


def _clip(text: str | None, limit: int) -> str:
    if not text:
        return "(unavailable)"
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… [truncated, {len(text) - limit} more characters]"


def build_work_order(
    config: OrchestratorConfig, package: WorkPackage, *, correction: str | None = None
) -> str:
    facts = read_repo(config.repo)
    protected = "\n".join(
        f"  - `{path}` — SHA256 {digest}"
        for path, digest in config.protected_artifacts.items()
    )
    invariants = "\n".join(f"  - {item}" for item in package.scientific_invariants)
    tests = "\n".join(f"  - `{' '.join(cmd)}`" for cmd in package.required_tests)
    gates = "\n".join(
        f"  - `{' '.join(cmd)}`" for cmd in package.required_quality_gates
    )
    tree_state = (
        "clean" if facts.is_clean else "DIRTY — " + ", ".join(facts.dirty_paths[:10])
    )
    allowed_block = "\n".join(f"  - `{item}`" for item in package.allowed_files) or (
        "  (not restricted — stay within the objective)"
    )
    protected_block = "\n".join(
        f"  - `{item}`" for item in package.protected_files
    ) or ("  (see protected artifacts below)")

    header = "# Correction order" if correction else "# Work order"
    body = f"""{header}: {package.name}

## Repository state
- Branch: `{facts.branch}`
- HEAD: `{facts.head}`
- Working tree: {tree_state}

## Objective
{correction or package.objective}

## Allowed files
{allowed_block}

## Files you must NOT modify
{protected_block}

## Protected artifacts — never regenerate
{protected or "  (none configured)"}

## Scientific invariants that must continue to hold
{invariants or "  (none declared for this package)"}

## Required tests
{tests or "  (orchestrator default suite)"}

## Required quality gates
{gates or "  (orchestrator default gates)"}

## Rules
- Do NOT weaken a test to make it pass. Do not loosen a tolerance, edit an
  expected value to match output, delete a test, swallow an exception, or
  regenerate a baseline. Any of those is a blocking failure.
- Do NOT commit, stage, reset, or clean. The orchestrator owns git.
- Do NOT write your own audit — an independent auditor reviews your work.
- Keep the change within the objective; no unrelated cleanup.

{BUILDER_CONTRACT}
"""
    return body


def build_audit_prompt(
    config: OrchestratorConfig,
    package: WorkPackage,
    *,
    codex_report: str,
    verification: VerificationReport,
    base_commit: str | None,
    previous_findings: list[dict[str, Any]] | None = None,
    targeted: bool = False,
) -> str:
    facts = read_repo(config.repo)
    diff = (
        diff_stat(config.repo, base_commit) if base_commit else diff_stat(config.repo)
    )
    try:
        full_diff = (
            git(config.repo, "diff", base_commit)
            if base_commit
            else git(config.repo, "diff")
        )
    except (RuntimeError, OSError, ValueError):
        full_diff = "(diff unavailable)"

    protected = "\n".join(
        f"  - `{path}`: {status}"
        for path, status in verification.protected_detail.items()
    )
    findings_block = ""
    if previous_findings:
        rows = "\n".join(
            f"  - **{f.get('id')}** ({f.get('severity')}): {f.get('summary')}"
            for f in previous_findings
        )
        findings_block = f"\n## Findings this correction was meant to close\n{rows}\n"

    scope = (
        "This is a TARGETED RE-AUDIT. Confirm only whether each listed finding is "
        "genuinely closed, and whether the fix caused any regression. Do NOT repeat "
        "a whole-project audit."
        if targeted
        else "This is a full audit of the work package described below."
    )

    return f"""# Independent audit: {package.name}

{scope}

{AUDITOR_RULES}

## Work package under audit
- Name: {package.name}
- Declared risk: {package.risk.value}
- Objective: {package.objective}

## Scientific invariants claimed to hold
{chr(10).join(f"  - {i}" for i in package.scientific_invariants) or "  (none declared)"}

## Repository state
- Branch: `{facts.branch}`
- HEAD: `{facts.head}`
- Base for this change: `{base_commit or "working tree"}`
{findings_block}
## Protected artifact hashes (recomputed locally)
{protected or "  (none configured)"}

## Local verification the orchestrator already ran
Passed: **{verification.passed}**
```
{_clip(verification.summary(), 4000)}
```
Changed files: {list(verification.changed_files)}

## Builder's own report — treat as an unverified claim
```
{_clip(codex_report, 8000)}
```

## Diff stat
```
{_clip(diff, 4000)}
```

## Full diff
```diff
{_clip(full_diff, 60000)}
```

## Your task

Attempt to FALSIFY this implementation.

Investigate the repository directly with your read-only tools — do not rely on
the summaries above. Independently reproduce anything numerical that matters.
Look specifically for:

- scientific error: wrong equation, wrong units, wrong sign, wrong branch
- tests that cannot fail, or that were weakened to pass
- silent scope creep, or a protected artifact quietly changed
- failure paths that return a plausible answer instead of an error
- claims in documentation that the code does not support

{AUDITOR_CONTRACT}
"""


def write_prompt(directory: Path, stem: str, content: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stem}.md"
    path.write_text(content, encoding="utf-8")
    return path
