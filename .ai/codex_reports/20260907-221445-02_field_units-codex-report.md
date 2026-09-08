Implemented the structural fix:

- Canonical K/Pa input state remains authoritative during unit changes.
- Display conversions no longer alter scientific signatures.
- Exact stale detection remains, including for a `1e-9` genuine temperature edit.
- Added regressions for known non-exact °F/bar and °C/psi round trips.
- Protected artifacts retain their required hashes.

Focused verification: 62 tests passed. Ruff, formatting, mypy, and compileall passed. The full suite was intentionally not run per policy.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "Focused pytest: tests/test_app_streamlit.py and tests/test_app_adapters.py — 62 passed; Ruff check passed; Ruff format --check passed (217 files formatted); mypy passed with no issues in 45 source files; compileall completed successfully.",
  "files_changed": ["src/pvt_phase_simulator_ui/app.py", "src/pvt_phase_simulator_ui/state.py", "tests/test_app_streamlit.py"],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>