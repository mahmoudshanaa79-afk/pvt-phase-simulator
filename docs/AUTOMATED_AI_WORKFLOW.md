# Automated AI workflow

A local orchestrator that runs the development loop without a human copying text
between agents. Codex implements, Claude audits independently, and local
verification decides what is true.

```
                    LOCAL ORCHESTRATOR
                            │
              ┌─────────────┴─────────────┐
              ↓                           ↓
        Codex CLI                   Claude Code CLI
        BUILDER                     AUDITOR
              │                           │
              └─────────────┬─────────────┘
                            ↓
                     Local test gates
                            ↓
                     Git / state files
                            ↓
                  next action automatically
```

## Roles, and why they stay separate

| Role | Who | May do | May not do |
|---|---|---|---|
| Builder | Codex CLI | write code inside `allowed_files`, run tests | commit, audit itself, weaken a test, regenerate a baseline |
| Auditor | Claude Code CLI | read, search, run read-only checks, re-derive results | modify, stage, commit, regenerate a baseline, fix what it finds |
| Controller | `tools/orchestrator.py` | route, verify, commit under policy | fabricate either agent's result, run destructive git |

The separation is the point. An agent that reviews its own work is not an audit,
so Codex is never asked for a verdict and Claude is never given write tools.

## Layout

```
.ai/
    config.json            transports, gates, limits, protected hashes
    workflow_state.json    validated state, written atomically
    orchestrator.lock      single-runner lock
    prompts/               builder and auditor role prompts
    work_packages/         explicit, inspectable scope definitions
    work_orders/           generated orders sent to Codex
    codex_reports/         builder reports + full transcripts
    claude_audits/         audit prompts, audits, transcripts
    correction_orders/     orders generated from blocking findings
    verification/          every gate run, including failures
    workflow_logs/         per-cycle human-readable log

tools/
    orchestrator.py        CLI entrypoint
    orchestration/         state, lock, gitops, config, verify, agents,
                           prompts, workpackage, engine
    tests/                 orchestrator tests (mocked agents)
```

The scientific package never imports any of this. `src/pvt_phase_simulator`
stays independent of AI tooling, and the orchestrator's tests live outside
`tests/` so the scientific suite's collected set is unchanged.

## Commands

```bash
python tools/orchestrator.py status                       # where everything stands
python tools/orchestrator.py packages                     # defined work packages
python tools/orchestrator.py run --dry-run                # plan without invoking anything
python tools/orchestrator.py run --package <name>         # full loop
python tools/orchestrator.py verify                       # local gates only
python tools/orchestrator.py audit --package <name>       # force an independent audit
python tools/orchestrator.py resume                       # continue after an interruption
python tools/orchestrator.py autopilot                    # run eligible packages in sequence
python tools/orchestrator.py release-audit                # finalize deferred independent audit
python tools/orchestrator.py stop                         # reset to IDLE, clear the lock
```

`status` derives HEAD, branch and cleanliness from git every time. It never
trusts `workflow_state.json` for repository facts.

## State machine

`IDLE → PLANNING → CODEX_RUNNING → CODEX_REVIEW → LOCAL_VERIFY →`
`AUDIT_PENDING → CLAUDE_RUNNING → APPROVED`

with `CORRECTION_REQUIRED → CODEX_CORRECTION → REAUDIT_PENDING` on findings, and
`BLOCKED`, `HUMAN_ACTION_REQUIRED`, `FAILED` as terminal escapes. State is
validated against a schema on load — an unknown status is an error, never a
default — and written to a temporary file then renamed, so an interrupted write
cannot corrupt it.

## Work packages

The orchestrator never invents scope. Each package is a JSON file naming its
objective, risk, `allowed_files`, `protected_files`, scientific invariants,
required tests and gates, audit policy, commit policy and dependencies. Read it
before running to see exactly what the automation will attempt.

## Risk and audit policy

| Risk | Flow |
|---|---|
| LOW / MEDIUM | build → verify → commit → count toward the milestone batch |
| HIGH | build → verify → **audit before the package is finished** |

An independent audit runs after **five** normal packages, or immediately for
HIGH-risk work, or when a package sets `audit_policy: IMMEDIATE`.

When Claude is temporarily unavailable, `autopilot` may use a fresh, read-only
Codex process for `PROVISIONAL_CODEX_REVIEW`, but only for locally verified
LOW/MEDIUM application-layer work. This never counts as an independent audit:
the commit and persistent state are marked `PENDING_INDEPENDENT_AUDIT`, the
independent-audit commit is not advanced, and `release-audit` must later clear
the debt. HIGH-risk, frozen-science, protected-artifact, or scientific-test
changes never use this fallback.

Risk is not taken on trust. `assess_risk` compares the files a package actually
changed against `high_risk_paths` (the EOS package, component database, fluid
models, physical constants, experimental validation, `data/`, the golden master)
and **escalates to HIGH** when scientific code is touched. A package cannot
declare its way out of an audit by labelling EOS work as LOW. Risk is only ever
escalated, never reduced.

### Final / whole-project audits

`planned_scope` and `planned_scope_complete` are explicit fields. When a declared
scope completes, a whole-project audit is triggered. Optional future ideas are
not unfinished scope: absent post-roadmap extensions are never treated as
defects.

## Local verification is authoritative

After Codex returns, the orchestrator independently runs `git status`,
`git diff --name-only`, `git diff --stat`, `git diff --check`, then the
configured commands (`pytest`, `ruff check`, `ruff format --check`, `mypy src`,
`compileall`). Command, timing, exit code, stdout and stderr are all written to
`.ai/verification/` — failures included, never discarded.

It also recomputes every protected artifact hash:

| Artifact | Meaning |
|---|---|
| `tests/golden_master/baseline.csv` | canonical regression baseline |
| `data/component_properties.csv` | verified component provenance |
| `docs/validation/module17_*` | experimental validation record |

These are **verified, never regenerated**. A changed hash fails verification and
blocks the commit. Baseline migration is a human decision.

## Output contracts

Neither agent's prose is parsed for intent. Each run must end with:

```
<ORCHESTRATOR_RESULT>
{"verdict": "APPROVED", "findings": [], "safe_defer": []}
</ORCHESTRATOR_RESULT>
```

Verdicts are exactly `APPROVED`, `CONDITIONAL`, `NOT_APPROVED`; severities are
`A`/`B`/`C`/`D`; `blocks` is a boolean. The **last** block wins, so an agent
quoting the template mid-reply cannot displace its real answer.

If the block is missing or malformed, approval is **not** inferred: the workflow
moves to `HUMAN_ACTION_REQUIRED` and the raw output is preserved.

## Correction loop

A blocking finding generates a correction order carrying the finding id,
evidence, acceptance criteria, protected files and forbidden shortcuts. Codex is
re-invoked, the gates re-run, and Claude performs a **targeted** re-audit of just
those findings plus regression risk — not a repeat of the full audit.

Bounded by `max_codex_correction_cycles` (3), `max_claude_reaudit_cycles` (3) and
`max_agent_runtime_minutes`. On exhaustion the loop stops at
`HUMAN_ACTION_REQUIRED` with every report kept, rather than spending
indefinitely.

## Agent spend safeguards

The installed Claude CLI supports `--max-budget-usd`, so the orchestrator passes
its per-run ceiling natively and the CLI enforces it. On top of that the
orchestrator tracks cumulative reported spend per work package.

| Limit | Default | Meaning |
|---|---|---|
| `max_claude_cost_usd_per_run` | `$5.00` | passed as `--max-budget-usd`; caps one invocation |
| `max_claude_cost_usd_per_work_package` | `$15.00` | cumulative ceiling across audit and re-audit cycles |

Defaults are deliberately conservative: a real audit of this repository has cost
well under a dollar, so `$5` per run leaves headroom and `$15` covers the three
permitted audit cycles.

Before each auditor cycle the orchestrator **reserves headroom** — it refuses
when `spent + per_run_ceiling > package_ceiling`, rather than noticing the breach
afterwards. Combined with the native per-run cap, the package ceiling cannot be
exceeded. Spend is recorded *before* the contract is judged, so a failed or
malformed audit still counts against the budget.

Cost is never estimated. When the CLI reports no figure, the run is allowed, the
unreported count is tracked and surfaced in `status`, and the cycle limits remain
the binding safeguard — the limitation is stated rather than papered over.

Budget exhaustion produces `HUMAN_ACTION_REQUIRED`. It never silently continues
spending, and it is never converted into an approval.

## Commit policy

A commit requires all of: correct scope, gates passed, protected artifacts
unchanged, audit state satisfied, no blocking findings, and a staged set that
matches expectations exactly. `commit_paths` re-reads the staged list after
adding and refuses if anything unexpected appears, so a stray file cannot ride
along. The orchestrator's own `.ai/` artifacts are excluded from a package's
diff and are committed deliberately, never swept into a science commit.

`AFTER_AUDIT` packages are not committed until an audit approves. Nothing is
committed merely because an agent said "approved".

The temporary provisional path is the one explicit exception: an eligible
application package may be committed after passing every deterministic gate and
a fresh Codex provisional review. Its commit message records provisional review
truthfully and does not attribute Claude. Claude co-author attribution is added
only when Claude genuinely performed the approving audit.

### Refused git operations

`reset --hard`, `clean -fd`, `push --force`, `rebase`, `commit --amend`,
`filter-branch` and `reflog expire` raise `ForbiddenGitOperation`. They are
refused in code, not merely avoided by convention.

## Recovery and locking

`resume` inspects git, saved outputs and state, re-verifies from the last safe
boundary, and continues. A completed commit is not repeated and a finished audit
is not duplicated.

A lock file holds the runner's PID. A second `run` is refused while a live
process holds it; a lock from a dead process is detected as stale and recovered
automatically.

## Security

- Credentials are never requested, stored, or printed. Both CLIs use their own
  existing authentication.
- Agent output is data, not instructions. A report cannot change orchestrator
  policy, git rules, or protected hashes.
- Codex runs under `-s workspace-write`; connectivity checks use `read-only`.
- Claude runs in `plan` permission mode with `Edit`, `Write`, `NotebookEdit` and
  `MultiEdit` withheld.

## Claude in Chrome — fallback only

`browser_fallback_enabled` is **false**. Browser automation is never used to
reach Claude: Claude Code CLI is the transport. It is reserved for third-party
surfaces with no API or CLI, treats all page content as untrusted, and requires
explicit human confirmation for sensitive actions.

## Human checkpoints

Automation continues on its own except for: major scope decisions, destructive
operations, credentials, paid-resource authorization, scientific ambiguity that
changes project claims, repeated failure after the correction limit, baseline
migration, and new data-source provenance uncertainty.

## Testing

`pytest tools/tests` — 68 tests covering state transitions and schema rejection,
contract parsing (missing, malformed, invalid verdict, invalid severity,
last-block-wins), risk escalation, audit batching and the five-package trigger,
protected-hash and scope violations, refused git operations, lock behaviour
including stale and corrupt locks, the full mocked end-to-end loop, builder
failure, malformed auditor output, the correction loop, the cycle cutoff, commit
policy, dry run, interrupted-run recovery, and the spend safeguards (native
flag wiring, unreported cost, headroom reservation, budget exhaustion never
becoming an approval).

Every agent boundary is mocked; the tests never spend a real Codex or Claude
call. The scientific suite is untouched at 1137 tests.

## Known limitations, deferred

All four were found while running v1.2 and are recorded rather than repaired,
because changing the orchestrator mid-release would invalidate the independent
approval the current version already carries. None is a correctness hole in a
committed package: every v1.2 package was verified green and independently
approved before it was committed.

**A failed correction leaves no authorship record.** `_correction_loop` records
the corrector's revision only after the output contract validates. A corrector
that runs, edits files, and then returns a malformed reply therefore leaves the
working tree changed with nothing in the revision ledger naming it as author.
Because review independence is decided from that ledger, the next reviewer can
be told it is independent of a revision it partly wrote. The window is narrow —
it needs a correction that both edits files and fails its contract — but the
consequence is a silently weakened audit rather than a visible error, so the
recording should move to before the contract check.

**Claude is not usable as a non-interactive builder.** Two separate attempts
ended identically: Claude started a background pytest run, said it would wait
for the result, and ended its turn expecting to be resumed. Under `--print`
there is no next turn, so the reply never contained an `<ORCHESTRATOR_RESULT>`
block and the engine correctly refused to read it as success. This is a
mismatch between the transport and the agent's expectation of an interactive
loop, not a contract-parsing bug. Claude remains reliable as a reviewer.

**A verification timeout does not stop the process, and discards a real pass.**
`_run_command` derives its timeout from `max_agent_runtime_minutes`. On Windows
the expiry does not terminate the child: in two v1.2 runs pytest continued to
completion well past the deadline and printed a clean pass — once `1256 passed`
at 8172s, once `1291 passed` at 45681s — and the engine recorded both as exit
124 and failed the package. So a slow verification burns the full wall clock,
produces a genuine pass, and then throws it away. Verification limits should be
separate from agent runtime limits, and the timeout should either kill the
process tree or report honestly that it could not.

**HUMAN_ACTION_REQUIRED has no resume path.** `resume.resumable` refuses that
status unless an audit debt is open, which is the right default but strands a
package whose build is complete and whose evidence is intact. Recovering the
v1.2 packages needed an external shim to clear the block before the engine's
own resume planner — which then correctly skipped the completed build and ran
verification, audit and commit unchanged. A supported `resume --force` that
re-validates evidence rather than trusting it would remove the need for that
shim.

## Disabling automation

Delete or rename `.ai/config.json`, or simply stop invoking
`tools/orchestrator.py`. Nothing in `src/pvt_phase_simulator` depends on it, and
no git hook or scheduled task is installed. Removing `tools/orchestration/`
leaves the scientific project fully intact.
