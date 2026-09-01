# Orchestration artifacts

Machine-readable workflow state and permanent records for the
Codex-builds / Claude-audits / local-gates development loop.

| Path | Contents |
|---|---|
| `workflow_state.json` | Current module, audit counter, pending and safe-defer findings |
| `work_orders/` | Work orders issued to the Codex builder |
| `codex_reports/` | Codex implementation reports (claims, not evidence) |
| `claude_audits/` | Independent adversarial audit records and verdicts |
| `provisional_reviews/` | Fresh read-only Codex reviews; explicitly not independent audits |
| `correction_orders/` | Structured correction orders derived from audit findings |
| `workflow_logs/` | Per-cycle log of risk, gates, verdicts and commits |

Git history and actual test results remain authoritative. Nothing in this
directory is scientific truth; audit records here are permanent and are not
overwritten.

`workflow_state.json` keeps a `deferred_independent_audits` ledger for every
package committed under `PROVISIONAL_CODEX_REVIEW`. Those entries remain
`PENDING_INDEPENDENT_AUDIT` until a comprehensive Claude release audit approves
the corresponding commit range.

## Worker invocation

```
codex exec -s workspace-write -C . --output-last-message <report> < <work_order>
```

Codex CLI 0.149.1, authenticated via ChatGPT.
