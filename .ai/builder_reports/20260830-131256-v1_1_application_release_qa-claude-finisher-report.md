# Package completion report — v1_1_application_release_qa

- **Builder of record:** Codex (partial), then **Claude as finisher**
- **Why:** Codex exhausted its usage quota mid-run (exit 1 after 1405 s) and never
  emitted an `<ORCHESTRATOR_RESULT>` block, so the orchestrator correctly escalated
  to `HUMAN_ACTION_REQUIRED` rather than inferring success. Its 0-byte report is
  preserved at `.ai/codex_reports/20260830-120626-v1_1_application_release_qa-report.md`.
- **Independent review:** **NOT PERFORMED.** See "Audit debt" below.

## Starting state inherited

Branch `app-v1.1-autonomous`, HEAD `c29ae49`, working tree carrying Codex's
uncommitted package-2 work. `codex_correction_cycles = 0` — no correction cycle
had been consumed. No orphan Streamlit process was present.

## What Codex had already implemented (preserved unchanged)

| File | Change |
|---|---|
| `tools/streamlit_smoke.py` | new — bounded localhost startup + `/_stcore/health` check |
| `tests/test_app_release.py` | new — deprecated-API scan, startup/health smoke |
| `tests/test_app_streamlit.py` | +4 tests: two-phase semantics, structured failure presentation, download payload/MIME, stale-result export gating |
| `src/pvt_phase_simulator_ui/context.py` | `current_inputs()` now reads live-validated `current_inputs` rather than last-submitted |
| `src/pvt_phase_simulator_ui/app.py` | resolves the example-selection / widget-ordering race; publishes `current_inputs` |
| `src/pvt_phase_simulator_ui/state.py` | initializes `current_inputs`, `rendered_input_example` |
| `src/pvt_phase_simulator_ui/views.py` | `_action_inputs()` gates scientific actions on a present, non-stale flash; disables exports when stale with an explanation |
| `docs/STREAMLIT_APPLICATION.md` | documents the health-smoke command |

## Finisher changes

**None.** Review and verification found no incomplete or failing QA item. Every
objective element of the package was already implemented and passing, so nothing
was added, rewritten, or "fixed" for its own sake.

## Fresh-context diff review

| Concern | Finding |
|---|---|
| Fake tests / tests not exercising real behaviour | None. The failure test drives the real app through `AppTest`, asserts on rendered error text and carries negative assertions (`not app.success`). The download test captures real `download_button` kwargs, decodes the CSV and JSON payloads, and cross-checks values against the live session result. |
| Brittle localhost handling | Not found. Ephemeral port via bind-to-0, `--server.address=127.0.0.1`, headless, file watcher off, proxy bypassed, bounded deadline, early-exit detection. |
| Orphan Streamlit processes | Not found. `run_smoke` stops the child in a `finally` with terminate → wait → kill. No listening 850x port after the suite. |
| UI duplicating science | Not found. No PR constants, cubic solving, or fugacity math in the UI package; `_cached_flash` delegates to `run_validated_flash`. |
| Scope violations | None. Eight changed files, all inside `allowed_files`. |
| Misleading error/status presentation | Not found in this diff; the changes improve it by gating stale exports. |
| Deployment-hostile assumptions | One observation, not a defect: `test_app_release.py` allows the smoke 20 s with a 30 s subprocess timeout. Adequate locally; a cold CI runner may need more headroom. Carried into package 3. |

## Verification (machine-generated)

`.ai/verification/*-v1_1_application_release_qa-claude-finisher.json`

| Gate | Result |
|---|---|
| pytest | **1182 passed** |
| ruff check | pass |
| ruff format --check | 175 files formatted |
| mypy src app | 41 files, no issues |
| compileall src app | pass |
| uv lock --check | 83 packages resolved |
| app import smoke | pass |
| git diff --check | pass |
| scope | pass |
| protected artifacts | 4/4 unchanged |

Science firewall: `src/pvt_phase_simulator/`, `data/`, `docs/validation/`,
`tests/golden_master/` all show an empty diff. No test was weakened.

## Audit debt created by this commit

This package was **built and verified by the same agent**. It carries no
independent review. `commit_policy` is `AFTER_AUDIT` and `audit_policy` is
`IMMEDIATE`; neither was satisfied. It is committed anyway under the operator's
explicit instruction to continue while Codex is unavailable, and is recorded in
`deferred_independent_audits` so the debt is visible rather than implied.

**Codex must perform the independent final diff / release-candidate review.**
