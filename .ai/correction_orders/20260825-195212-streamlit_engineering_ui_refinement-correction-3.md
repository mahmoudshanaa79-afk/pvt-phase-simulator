# Correction order: streamlit_engineering_ui_refinement

## Repository state
- Branch: `master`
- HEAD: `94af1204b16d4b606eefb0ec2186c45a89e28f2c`
- Working tree: DIRTY — .ai/codex_reports/20260825-175711-streamlit_engineering_ui_refinement-report.last-message.txt, .ai/codex_reports/20260825-175711-streamlit_engineering_ui_refinement-report.md, .ai/codex_reports/20260825-175711-streamlit_engineering_ui_refinement-report.transcript.json, .ai/codex_reports/20260825-185853-streamlit_engineering_ui_refinement-correction-report-1.last-message.txt, .ai/codex_reports/20260825-185853-streamlit_engineering_ui_refinement-correction-report-1.md, .ai/codex_reports/20260825-185853-streamlit_engineering_ui_refinement-correction-report-1.transcript.json, .ai/codex_reports/20260825-192942-streamlit_engineering_ui_refinement-correction-report-2.last-message.txt, .ai/codex_reports/20260825-192942-streamlit_engineering_ui_refinement-correction-report-2.md, .ai/codex_reports/20260825-192942-streamlit_engineering_ui_refinement-correction-report-2.transcript.json, .ai/correction_orders/20260825-185853-streamlit_engineering_ui_refinement-correction-1.md

## Objective
Close the following findings from the independent audit. Change nothing else, and do not weaken any test or tolerance to make a finding disappear.

- **VERIFY** (severity B):         PASS  .venv/Scripts/python.exe -m pytest -q
        PASS  .venv/Scripts/python.exe -m ruff check .
   FAIL(101)  .venv/Scripts/python.exe -m ruff format --check .
        PASS  .venv/Scripts/python.exe -m mypy src
        PASS  .venv/Scripts/python.exe -m compileall -q src
        PASS  uv lock --check
        PASS  uv run python -c import pvt_phase_simulator_ui; import pvt_phase_simulator_ui.styles
        PASS  git diff --check
        FAIL  scope: files outside allowed_files: ['.streamlit/']

## Allowed files
  - `src/pvt_phase_simulator_ui`
  - `app`
  - `streamlit_app.py`
  - `.streamlit/config.toml`
  - `pyproject.toml`
  - `uv.lock`
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
  - `tools`
  - `.ai/config.json`

## Protected artifacts — never regenerate
  - `tests/golden_master/baseline.csv` — SHA256 530C667AA70EF1EA182F4EDB98624A0A9B9908F149354276CDAC44A87EA7D2BE
  - `data/component_properties.csv` — SHA256 C6F6BA9AE9C2F4C7F257BBC09A75DF0D7065255868AA46BF3E8C81AC5A8B9B3A
  - `docs/validation/module17_vle_validation.csv` — SHA256 B14728D51AAC06AF38FC4F4E5F408942B253FEBE32D3E12EC26E9623CFA42482
  - `docs/validation/module17_vle_validation_summary.json` — SHA256 5B120B77BF05567FCC6A0EE0D0054C6D1DEBA35FE26A7C837352C92017D24870

## Scientific invariants that must continue to hold
  - Every file under src/pvt_phase_simulator remains unchanged; the separately installed UI package may import only existing public scientific and Module 21 plotting APIs.
  - No Peng-Robinson, mixing-rule, fugacity, Rachford-Rice, TPD, saturation, phase-envelope, pseudo-arclength, Gibbs-curvature, or critical-point equation is duplicated in the UI.
  - Internal pressure remains SI Pa; validated UI input converts MPa to Pa exactly once with MPa * 1e6, and display converts Pa to MPa without changing production results.
  - Methane, Ethane, and Propane mol-percent input is converted to mole fractions only after finite, nonnegative, positive-total, materially 100-percent validation; invalid input is never silently normalized and cannot invoke a scientific API.
  - The existing flash result remains the source of phase, convergence, vapor/liquid fractions, x/y compositions, Z factors, K values, residuals, iterations, roots, and failure information; presentation code does not reclassify or fill unavailable values.
  - Bubble and dew identities, structured unavailable points, and continuation terminations remain unchanged; operating-point presentation does not fabricate an envelope, and turning points are never labelled critical points.
  - Only a production MixtureCriticalPointResult with CriticalPointStatus.CONVERGED may display certified Tc/Pc; lambda_min=0 or a spinodal condition alone never certifies criticality.
  - Module 17 production predictions remain separate from retrospective nearest-root diagnostics labelled NOT PRODUCTION PREDICTIONS, relative pressure error remains 100*(P_pred-P_exp)/P_exp, and validation remains kij=0 with no fitted interaction parameters.
  - Session state remains per-user and preserves deliberate calculation results across navigation/cosmetic reruns while identifying results as stale after scientific inputs change.
  - Golden master, component-property, and Module 17 validation artifacts remain byte-identical and are never regenerated.
  - All 1137 pre-existing scientific tests remain present and unchanged; application tests add coverage without weakening any scientific test, tolerance, baseline, or expected value.
  - Verified frontend property scope remains Methane, Ethane, and Propane; no claim of arbitrary reservoir-fluid validation or commercial-PVT readiness is introduced.
  - No new thermodynamic feature, component, interaction-parameter editor, C7+ model, density/Bo/GOR output, CCE/CVD/depletion/separator workflow, sweep, field-unit system, desktop packaging, case management, dataset, or deployment is added.

## Required tests
  - `.venv/Scripts/python.exe -m pytest -q`

## Required quality gates
  - `.venv/Scripts/python.exe -m ruff check .`
  - `.venv/Scripts/python.exe -m ruff format --check .`
  - `.venv/Scripts/python.exe -m mypy src`
  - `.venv/Scripts/python.exe -m compileall -q src`
  - `uv lock --check`
  - `uv run python -c import pvt_phase_simulator_ui; import pvt_phase_simulator_ui.styles`
  - `git diff --check`

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
