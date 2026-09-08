Implemented deterministic, versioned OpenPhase case save/load.

- Saves all scientific inputs, presentation units, and both sweep configurations.
- Strictly validates JSON/schema/version/composition before mutating state.
- Loading never runs scientific calculations or restores cached results.
- Added focused persistence and Streamlit regression coverage.
- Protected artifacts retain their required hashes.
- No Streamlit server is currently running.

Focused tests: 136 passed. Ruff, formatting, mypy, and compileall all passed. The full suite was intentionally left to the orchestrator per build-time policy.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "Focused pytest: 136 passed (tests/test_app_case_files.py, tests/test_app_streamlit.py, tests/test_app_sweeps.py, tests/test_app_adapters.py, tests/test_app_release.py); Ruff check passed; Ruff format check passed; mypy src app passed; compileall src app passed.",
  "files_changed": ["docs/STREAMLIT_APPLICATION.md", "src/pvt_phase_simulator_ui/__init__.py", "src/pvt_phase_simulator_ui/app.py", "src/pvt_phase_simulator_ui/case_files.py", "src/pvt_phase_simulator_ui/state.py", "src/pvt_phase_simulator_ui/views.py", "tests/test_app_case_files.py", "tests/test_app_streamlit.py"],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>