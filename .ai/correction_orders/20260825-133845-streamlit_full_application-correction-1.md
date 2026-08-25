# Correction order: streamlit_full_application

## Repository state
- Branch: `master`
- HEAD: `341bc3d27479eca60d323e2f209d4f8865721ffa`
- Working tree: DIRTY — .ai/codex_reports/20260825-032435-streamlit_full_application-report.last-message.txt, .ai/codex_reports/20260825-032435-streamlit_full_application-report.md, .ai/codex_reports/20260825-032435-streamlit_full_application-report.transcript.json, .ai/verification/20260825-025502-resume.json, .ai/verification/20260825-133845-streamlit_full_application.json, .ai/work_orders/20260825-023522-streamlit_full_application-order.md, .ai/work_orders/20260825-032435-streamlit_full_application-order.md, .ai/work_packages/streamlit_full_application.json, .ai/workflow_state.json, .streamlit/

## Objective
Close the following findings from the independent audit. Change nothing else, and do not weaken any test or tolerance to make a finding disappear.

- **VERIFY** (severity B):         PASS  .venv/Scripts/python.exe -m pytest -q
        PASS  .venv/Scripts/python.exe -m ruff check .
        PASS  .venv/Scripts/python.exe -m ruff format --check .
        PASS  .venv/Scripts/python.exe -m mypy src app
        PASS  .venv/Scripts/python.exe -m compileall -q src app
        PASS  git diff --check
        FAIL  scope: files outside allowed_files: ['.streamlit/']

## Allowed files
  - `app`
  - `.streamlit/config.toml`
  - `tests/test_app*.py`
  - `docs/STREAMLIT_APPLICATION.md`
  - `README.md`

## Files you must NOT modify
  - `src/pvt_phase_simulator`
  - `data`
  - `docs/validation`
  - `tests/golden_master`
  - `tests/__init__.py`
  - `tests/conftest.py`
  - `tests/derivative_reference.py`
  - `tests/derivative_verification.py`
  - `tests/run_derivative_verification.py`
  - `tests/run_newton_saturation_benchmarks.py`
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
  - `tests/test_project_setup.py`
  - `tests/test_properties.py`
  - `tests/test_pseudo_arclength.py`
  - `tests/test_saturation_pressure.py`

## Protected artifacts — never regenerate
  - `tests/golden_master/baseline.csv` — SHA256 530C667AA70EF1EA182F4EDB98624A0A9B9908F149354276CDAC44A87EA7D2BE
  - `data/component_properties.csv` — SHA256 C6F6BA9AE9C2F4C7F257BBC09A75DF0D7065255868AA46BF3E8C81AC5A8B9B3A
  - `docs/validation/module17_vle_validation.csv` — SHA256 B14728D51AAC06AF38FC4F4E5F408942B253FEBE32D3E12EC26E9623CFA42482
  - `docs/validation/module17_vle_validation_summary.json` — SHA256 5B120B77BF05567FCC6A0EE0D0054C6D1DEBA35FE26A7C837352C92017D24870

## Scientific invariants that must continue to hold
  - Modules 1-21 and every file under src/pvt_phase_simulator remain unchanged; the application calls existing public scientific APIs and Module 21 Plotly APIs.
  - No Peng-Robinson, fugacity, Rachford-Rice, TPD, saturation, phase-envelope, pseudo-arclength, Gibbs-curvature, or critical-point equations are duplicated in app code.
  - Internal pressure remains SI Pa; UI conversion is exactly MPa * 1e6 on input and Pa / 1e6 on display.
  - Composition input is mol %, converted exactly to mole fractions only after finite, nonnegative, positive-total, production-compatible 100% validation; clearly invalid input is not silently normalized.
  - Invalid UI input cannot invoke a production scientific API, and expensive calculations occur only on explicit user action.
  - Production result objects remain the scientific source of truth; adapters do not alter phase, vapor/liquid fractions, x/y compositions, Z factors, statuses, residuals, or iteration data.
  - Unavailable phase quantities are displayed as unavailable and are never fabricated for single-phase or failed states.
  - Bubble and dew identities are preserved; failed/unavailable envelope points are not rendered as converged states; pressure or temperature turning points are never labelled critical points.
  - Only CriticalPointStatus.CONVERGED results may be presented as certified critical points; lambda_min=0 alone and spinodal states are not critical certification.
  - The approved zero-kij 50/50 methane/propane result remains 321.5829183194 K and 8,534,443.23606381 Pa, displayed as 8.53444323606381 MPa, when supplied by the production result.
  - Module 17 production predictions remain separate from retrospective nearest-root diagnostics, which retain explicit 'not production prediction' semantics.
  - Module 17 relative pressure error remains 100*(P_pred-P_exp)/P_exp and reported validation remains kij=0 with no fitted binary interaction parameters.
  - Expected scientific failures remain structured failures/information and are never converted into plausible success or valid-looking critical metrics.
  - Session state preserves deliberate calculation results across cosmetic reruns while stale results are invalidated or clearly identified after scientific inputs change.
  - The existing 1137 scientific tests are retained and continue to pass; no historical test, tolerance, baseline, or expected scientific value is deleted or weakened.
  - Golden, property, and Module 17 protected artifacts remain byte-identical and are never regenerated.
  - Supported verified frontend property scope remains methane, ethane, and propane; no arbitrary reservoir-fluid or commercial-PVT claim is introduced.
  - No reservoir depletion, CCE/CVD, separator, pseudocomponent/C7+, EOS tuning, kij fitting, component expansion, or experimental-data extension is implemented.

## Required tests
  - `.venv/Scripts/python.exe -m pytest -q`
  - `.venv/Scripts/python.exe -m ruff check .`
  - `.venv/Scripts/python.exe -m ruff format --check .`
  - `.venv/Scripts/python.exe -m mypy src app`
  - `.venv/Scripts/python.exe -m compileall -q src app`
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
