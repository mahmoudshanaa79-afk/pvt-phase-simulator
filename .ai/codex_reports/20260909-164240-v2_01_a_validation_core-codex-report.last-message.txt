Implemented the validation core with immutable identities, provenance, strict data-class separation, deterministic serialization, schema rejection, hash verification, status invariants, documentation, and 40 synthetic tests.

No protected scientific files were modified. Full-suite pytest remains for the orchestrator per the build-time policy.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "Focused pytest: 40 passed, 1 non-failing pytest-cache permission warning. Ruff check: passed. Ruff format --check: 257 files formatted. mypy src app: success, 57 source files. compileall src app: passed.",
  "files_changed": [
    "docs/VALIDATION_FRAMEWORK.md",
    "src/pvt_phase_simulator_validation/__init__.py",
    "src/pvt_phase_simulator_validation/_validation.py",
    "src/pvt_phase_simulator_validation/aggregation.py",
    "src/pvt_phase_simulator_validation/enums.py",
    "src/pvt_phase_simulator_validation/exceptions.py",
    "src/pvt_phase_simulator_validation/hashing.py",
    "src/pvt_phase_simulator_validation/json_values.py",
    "src/pvt_phase_simulator_validation/models.py",
    "src/pvt_phase_simulator_validation/provenance.py",
    "src/pvt_phase_simulator_validation/py.typed",
    "src/pvt_phase_simulator_validation/serialization.py",
    "tests/test_validation_core.py",
    "tests/test_validation_serialization.py"
  ],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>