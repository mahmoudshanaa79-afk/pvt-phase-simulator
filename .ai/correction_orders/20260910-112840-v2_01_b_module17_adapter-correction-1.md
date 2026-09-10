# Correction order: v2_01_b_module17_adapter

## Repository state
- Branch: `v2-validation-framework`
- HEAD: `5230e870628685f91be0249c9674e17832ebcae6`
- Working tree: DIRTY — .ai/codex_reports/20260910-105648-v2_01_b_module17_adapter-codex-report.last-message.txt, .ai/codex_reports/20260910-105648-v2_01_b_module17_adapter-codex-report.md, .ai/codex_reports/20260910-105648-v2_01_b_module17_adapter-codex-report.transcript.json, .ai/verification/20260910-112840-v2_01_b_module17_adapter.json, .ai/work_orders/20260910-105648-v2_01_b_module17_adapter-order.md, .ai/work_packages/v2_01_b_module17_adapter.json, .ai/workflow_state.json, docs/VALIDATION_FRAMEWORK.md, src/pvt_phase_simulator_validation/__init__.py, src/pvt_phase_simulator_validation/models.py

## Objective
Close the following review or verification findings. Change nothing else, and do not weaken any test or tolerance to make a finding disappear.

- **VERIFY** (severity B):         PASS  .venv/Scripts/python.exe -m pytest -q
        PASS  .venv/Scripts/python.exe -m ruff check .
     FAIL(1)  .venv/Scripts/python.exe -m ruff format --check .
        PASS  .venv/Scripts/python.exe -m mypy src app
        PASS  .venv/Scripts/python.exe -m compileall -q src app

## Allowed files
  - `src/pvt_phase_simulator_validation/**`
  - `tests/test_validation_*.py`
  - `docs/VALIDATION_FRAMEWORK.md`

## Files you must NOT modify
  - `src/pvt_phase_simulator`
  - `data`
  - `docs/validation`
  - `tests/golden_master`
  - `src/pvt_phase_simulator_ui`
  - `tools/orchestration`

## Protected artifacts — never regenerate
  - `tests/golden_master/baseline.csv` — SHA256 530C667AA70EF1EA182F4EDB98624A0A9B9908F149354276CDAC44A87EA7D2BE
  - `data/component_properties.csv` — SHA256 C6F6BA9AE9C2F4C7F257BBC09A75DF0D7065255868AA46BF3E8C81AC5A8B9B3A
  - `docs/validation/module17_vle_validation.csv` — SHA256 B14728D51AAC06AF38FC4F4E5F408942B253FEBE32D3E12EC26E9623CFA42482
  - `docs/validation/module17_vle_validation_summary.json` — SHA256 5B120B77BF05567FCC6A0EE0D0054C6D1DEBA35FE26A7C837352C92017D24870

## Scientific invariants that must continue to hold
  - The scientific engine is frozen: no file under src/pvt_phase_simulator/, data/, docs/validation/ or tests/golden_master/ may change.
  - The adapter performs no thermodynamic calculation and imports nothing from pvt_phase_simulator.eos.
  - Retrospective nearest-root diagnostics can never reach a production prediction value; they remain structurally separate diagnostics.
  - All 40 Module 17 source states survive in both capabilities: 80 records, no case dropped for failure, non-convergence or large model error.
  - Legacy solver coverage is reproduced exactly: bubble 31/40 converged with 9 not_found; dew 22/40 converged with 4 not_found and 14 inconclusive.
  - The converged / not_found / inconclusive distinction is preserved structurally and queryably, not only in free-text prose.
  - The dataset remains EXPERIMENTAL_VALIDATION and cannot be reclassified.
  - coverage_factor stays None when the source does not state k; a 95 percent confidence level never implies k = 2.
  - No published provenance is silently discarded; a field that cannot be represented is reported as a schema gap.
  - Values mapped from stored legacy evidence reproduce exactly after float round-trip parsing; no tolerance is introduced to make tests pass.
  - No accuracy threshold, error metric, or boolean meaning 'accuracy passed' is added by this package.

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
