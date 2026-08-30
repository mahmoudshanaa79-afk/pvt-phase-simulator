# Work order: v1_1_application_release_qa

## Repository state
- Branch: `app-v1.1-autonomous`
- HEAD: `c29ae4961543e74a271e8e2e54de22852892cf00`
- Working tree: DIRTY — .ai/application_gap_report_openphase_v1_1.md, .ai/claude_audits/20260830-120041-v1_1_first_use_examples-audit-prompt.md, .ai/claude_audits/20260830-120041-v1_1_first_use_examples-audit.md, .ai/claude_audits/20260830-120041-v1_1_first_use_examples-audit.transcript.json, .ai/codex_reports/20260826-153136-streamlit_public_release_p1_fixes-report.md, .ai/codex_reports/20260826-153136-streamlit_public_release_p1_fixes-report.transcript.json, .ai/codex_reports/20260829-193150-streamlit_public_release_p1_fixes-report.last-message.txt, .ai/codex_reports/20260829-193150-streamlit_public_release_p1_fixes-report.md, .ai/codex_reports/20260829-193150-streamlit_public_release_p1_fixes-report.transcript.json, .ai/codex_reports/20260829-203854-v1_1_first_use_examples-report.md

## Objective
Close the remaining application-specific release QA gaps without changing scientific behavior. Add deterministic semantic tests for a valid two-phase submitted case, a valid single-phase submitted case, genuine structured failure presentation, actual CSV/JSON download payloads and MIME metadata, stale-result behavior after input changes, all five page destinations, disabled-action explanations, and absence of deprecated Streamlit APIs. Add a lightweight local Streamlit startup and HTTP health smoke helper or test using the existing environment only; it must use a bounded timeout, terminate its own child process, require no network beyond localhost, and expose a clear command for final QA. Make only narrowly necessary application fixes revealed by those tests. Never weaken a test or scientific expectation.

## Allowed files
  - `src/pvt_phase_simulator_ui`
  - `app`
  - `streamlit_app.py`
  - `tests/test_app_adapters.py`
  - `tests/test_app_streamlit.py`
  - `tests/test_app_release.py`
  - `tools/streamlit_smoke.py`
  - `docs/STREAMLIT_APPLICATION.md`

## Files you must NOT modify
  - `src/pvt_phase_simulator`
  - `data`
  - `docs/validation`
  - `tests/golden_master`
  - `tests/test_acceleration.py`
  - `tests/test_component_database.py`
  - `tests/test_critical_point.py`
  - `tests/test_criticality.py`
  - `tests/test_damping.py`
  - `tests/test_derivative_verification.py`
  - `tests/test_derivatives.py`
  - `tests/test_diagnostics.py`
  - `tests/test_experimental_validation.py`
  - `tests/test_flash.py`
  - `tests/test_fluid_models.py`
  - `tests/test_golden_master.py`
  - `tests/test_mixing_rules.py`
  - `tests/test_mixture_fugacity.py`
  - `tests/test_near_trivial_saturation.py`
  - `tests/test_newton_saturation.py`
  - `tests/test_peng_robinson.py`
  - `tests/test_phase_envelope.py`
  - `tests/test_phase_identity_corrections.py`
  - `tests/test_phase_stability.py`
  - `tests/test_plotting.py`
  - `tests/test_properties.py`
  - `tests/test_pseudo_arclength.py`
  - `tests/test_saturation_pressure.py`
  - `.ai/config.json`
  - `tools/orchestration`

## Protected artifacts — never regenerate
  - `tests/golden_master/baseline.csv` — SHA256 530C667AA70EF1EA182F4EDB98624A0A9B9908F149354276CDAC44A87EA7D2BE
  - `data/component_properties.csv` — SHA256 C6F6BA9AE9C2F4C7F257BBC09A75DF0D7065255868AA46BF3E8C81AC5A8B9B3A
  - `docs/validation/module17_vle_validation.csv` — SHA256 B14728D51AAC06AF38FC4F4E5F408942B253FEBE32D3E12EC26E9623CFA42482
  - `docs/validation/module17_vle_validation_summary.json` — SHA256 5B120B77BF05567FCC6A0EE0D0054C6D1DEBA35FE26A7C837352C92017D24870

## Scientific invariants that must continue to hold
  - Every file under src/pvt_phase_simulator remains byte-unchanged.
  - Tests pin existing public scientific results and presentation semantics; they do not redefine expected science.
  - No scientific equation, algorithm, tolerance, status, result object, dataset, or baseline changes.
  - A valid two-phase result remains two-phase, a valid single-phase result remains informational, and genuine failures remain failures.
  - Exports use only current non-stale calculated results, preserve source floats, and never trigger or fabricate calculations.
  - Protected artifacts and all pre-existing scientific tests remain byte-unchanged.

## Required tests
  - `.venv/Scripts/python.exe -m pytest -q`
  - `.venv/Scripts/python.exe -m ruff check .`
  - `.venv/Scripts/python.exe -m ruff format --check .`
  - `.venv/Scripts/python.exe -m mypy src app`
  - `.venv/Scripts/python.exe -m compileall -q src app`
  - `uv lock --check`
  - `uv run python -c import pvt_phase_simulator_ui; import pvt_phase_simulator_ui.app; import pvt_phase_simulator_ui.views`
  - `git diff --check`

## Required quality gates
  (orchestrator default gates)

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
