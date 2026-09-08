# Work order: 04_engineering_report

## Repository state
- Branch: `app-v1.2-engineering`
- HEAD: `9a34001c12d6718bfa9745405b51daf922da901b`
- Working tree: DIRTY — .ai/claude_audits/20260906-115645-01_model_and_limitations-audit-prompt.md, .ai/claude_audits/20260906-115645-01_model_and_limitations-audit.md, .ai/claude_audits/20260906-115645-01_model_and_limitations-audit.transcript.json, .ai/claude_audits/20260906-150728-02_field_units-audit-prompt.md, .ai/claude_audits/20260906-150728-02_field_units-audit.md, .ai/claude_audits/20260906-150728-02_field_units-audit.transcript.json, .ai/claude_audits/20260907-220100-02_field_units-audit-prompt.md, .ai/claude_audits/20260907-220100-02_field_units-audit.md, .ai/claude_audits/20260907-220100-02_field_units-audit.transcript.json, .ai/claude_audits/20260907-224421-02_field_units-audit-prompt.md

## Objective
Provide a useful downloadable engineering/scientific case report built ENTIRELY from results OpenPhase has already computed. The report renders results; it never recomputes them and never starts a calculation.

CONTENT, where available: case identification; date and version where appropriate; fluid composition; temperature and pressure with their units; the model (Peng-Robinson EOS); the verified component scope; the kij assumption; the calculation inputs; phase and stability result; flash result; liquid and vapour fractions; phase compositions; Z factors; bubble and dew outputs if calculated; sweep summaries if calculated; the critical point if calculated; convergence and status information; model assumptions; limitations; and the validation/provenance references the repository already supports.

TRUTHFULNESS. The report must never fabricate a missing result. Every field that is unavailable or that failed appears explicitly as unavailable or failed - never blank, never zero, never interpolated. Only a genuinely converged result may be presented as a result.

FORMAT. Choose the lightest robust format the existing infrastructure already supports - HTML or Markdown assembled from the existing adapters is sufficient, and a printable HTML report is preferred. Do NOT add a reporting framework or any heavy new dependency for visual polish. Add PDF only if it is reliable with dependencies already present and does not become a reporting detour; if in doubt, do not add PDF. Keep the existing CSV and JSON exports working unchanged.

SCOPE. No new thermodynamics. The scientific engine is frozen and must not change, and no thermodynamic relation may be implemented or restated in the application layer.

TESTS. Cover: a report generated from a real computed case; unavailable and failed fields being labelled as such rather than blank; units being stated explicitly; the report never triggering a calculation; and the existing exports still working. Avoid brittle hard-coded one-ULP float strings.

BUILD-TIME TESTING POLICY. Run only focused tests for the files and behaviour you changed, plus Ruff and mypy if useful. Do NOT run the whole pytest suite for reassurance - the orchestrator runs the authoritative full-suite verification after you finish, and duplicating it wastes a great deal of wall-clock time.

## Allowed files
  - `src/pvt_phase_simulator_ui/**`
  - `tests/test_app_*.py`
  - `docs/STREAMLIT_APPLICATION.md`

## Files you must NOT modify
  - `src/pvt_phase_simulator`
  - `data`
  - `docs/validation`
  - `tests/golden_master`

## Protected artifacts — never regenerate
  - `tests/golden_master/baseline.csv` — SHA256 530C667AA70EF1EA182F4EDB98624A0A9B9908F149354276CDAC44A87EA7D2BE
  - `data/component_properties.csv` — SHA256 C6F6BA9AE9C2F4C7F257BBC09A75DF0D7065255868AA46BF3E8C81AC5A8B9B3A
  - `docs/validation/module17_vle_validation.csv` — SHA256 B14728D51AAC06AF38FC4F4E5F408942B253FEBE32D3E12EC26E9623CFA42482
  - `docs/validation/module17_vle_validation_summary.json` — SHA256 5B120B77BF05567FCC6A0EE0D0054C6D1DEBA35FE26A7C837352C92017D24870

## Scientific invariants that must continue to hold
  - The scientific engine is frozen: no file under src/pvt_phase_simulator/, data/, docs/validation/ or tests/golden_master/ may change.
  - No thermodynamic relation may be implemented, restated or approximated in the application layer.
  - Unavailable quantities are reported as unavailable and never fabricated or interpolated.
  - Structured failures remain failures; only CriticalPointStatus.CONVERGED is a certified critical point.

## Required tests
  - `.venv/Scripts/python.exe -m pytest -q`

## Required quality gates
  - `.venv/Scripts/python.exe -m ruff check .`
  - `.venv/Scripts/python.exe -m ruff format --check .`
  - `.venv/Scripts/python.exe -m mypy src app`
  - `.venv/Scripts/python.exe -m compileall -q src app`

## Rules
- Do NOT weaken a test to make it pass. Do not loosen a tolerance, edit an
  expected value to match output, delete a test, swallow an exception, or
  regenerate a baseline. Any of those is a blocking failure.
- Do NOT commit, stage, reset, or clean. The orchestrator owns git.
- Do NOT write your own audit — an independent auditor reviews your work.
- Keep the change within the objective; no unrelated cleanup.

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
