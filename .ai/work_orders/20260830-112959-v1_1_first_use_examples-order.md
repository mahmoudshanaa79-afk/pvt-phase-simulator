# Work order: v1_1_first_use_examples

## Repository state
- Branch: `app-v1.1-autonomous`
- HEAD: `1f01975f30b3e9ea9197323fd2f00c8b7da411bc`
- Working tree: DIRTY — .ai/application_gap_report_openphase_v1_1.md, .ai/codex_reports/20260826-153136-streamlit_public_release_p1_fixes-report.md, .ai/codex_reports/20260826-153136-streamlit_public_release_p1_fixes-report.transcript.json, .ai/codex_reports/20260829-193150-streamlit_public_release_p1_fixes-report.last-message.txt, .ai/codex_reports/20260829-193150-streamlit_public_release_p1_fixes-report.md, .ai/codex_reports/20260829-193150-streamlit_public_release_p1_fixes-report.transcript.json, .ai/codex_reports/20260829-203854-v1_1_first_use_examples-report.md, .ai/codex_reports/20260829-203854-v1_1_first_use_examples-report.transcript.json, .ai/provisional_reviews/20260829-203046-streamlit_public_release_p1_fixes-provisional-review-prompt.md, .ai/provisional_reviews/20260829-203046-streamlit_public_release_p1_fixes-provisional-review.last-message.txt

## Objective
Polish first use without rebuilding the application. Add a compact native Streamlit example selector for a small set of truthful cases already within the verified methane/ethane/propane scope: the existing default two-phase-oriented case, the known valid 50/50 methane/propane 300 K and 20 MPa single-phase case, and the existing audited 50/50 methane/propane critical-solver seed near 321.5829183194 K and 8.53444323606381 MPa. Selecting an example may populate input widgets but must never submit the form or run a scientific calculation. Preserve exact user-editable values, explicit validation, stable widget keys, sidebar navigation, native layout, and sentence-case public copy. Add semantic tests proving selection only changes input state and does not populate results, and that custom edits still validate and submit normally. Do not add custom CSS, new components, new calculations, or claims beyond the documented verified scope.

## Allowed files
  - `src/pvt_phase_simulator_ui/app.py`
  - `src/pvt_phase_simulator_ui/state.py`
  - `tests/test_app_streamlit.py`
  - `tests/test_app_adapters.py`
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
  - Examples only assign input values; selection never invokes flash, stability, saturation, envelope, criticality, or critical-point APIs.
  - No scientific classification, equation, tolerance, convergence rule, or production result changes.
  - Example values and labels are truthful and remain within the verified methane/ethane/propane default-zero-kij scope.
  - User-entered values still pass through the existing explicit validation and exact unit-conversion boundary.
  - Protected data, validation artifacts, golden baselines, and pre-existing scientific tests remain byte-unchanged.

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
