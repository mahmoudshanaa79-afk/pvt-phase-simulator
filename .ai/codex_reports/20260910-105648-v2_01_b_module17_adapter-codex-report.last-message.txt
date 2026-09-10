Implemented the Module 17 adapter and vector-uncertainty schema v1.1.

Key results:

- Emits 40 bubble + 40 dew records.
- Preserves coverage exactly: bubble 31/9; dew 22/4/14.
- Keeps retrospective root data isolated in diagnostics.
- Preserves provenance and leaves coverage factor unset.
- Protected artifact hashes remain unchanged.
- Focused validation tests: 65 passed.
- Ruff, mypy, compileall passed.
- Repository-wide format check only flags a pre-existing `.ai` audit file outside the allowed scope; all changed files pass formatting.
- Full pytest was not run, per the work order’s build-time testing policy.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "Focused pytest: 65 passed, 1 non-test pytest-cache permission warning. Ruff check passed. Ruff format check passed for all changed/in-scope files; repository-wide format check flags only the pre-existing out-of-scope .ai/claude_audits/20260909-172636-v2_01_a_validation_core-audit.md. Mypy passed for 58 source files. Compileall passed. Protected artifact SHA-256 hashes verified unchanged. Full pytest intentionally not run per build-time testing policy.",
  "files_changed": ["docs/VALIDATION_FRAMEWORK.md", "src/pvt_phase_simulator_validation/__init__.py", "src/pvt_phase_simulator_validation/models.py", "src/pvt_phase_simulator_validation/provenance.py", "src/pvt_phase_simulator_validation/serialization.py", "src/pvt_phase_simulator_validation/module17_adapter.py", "tests/test_validation_core.py", "tests/test_validation_serialization.py", "tests/test_validation_module17_adapter.py"],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>