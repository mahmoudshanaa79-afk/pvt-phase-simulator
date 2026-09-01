Implemented and verified the native example selector, input-only state updates, editable precision, semantic tests, and documentation. Scientific sources and protected artifacts remain unchanged.

Full suite: 1,176 passed. All required quality gates passed; pytest used a writable temporary directory due sandbox permissions.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "pytest: 1176 passed; ruff check: passed; ruff format --check: 168 files formatted; mypy: passed; compileall: passed; uv lock --check: passed; uv import smoke test: passed; git diff --check: passed; protected artifact hashes: matched",
  "files_changed": ["src/pvt_phase_simulator_ui/app.py", "src/pvt_phase_simulator_ui/state.py", "tests/test_app_streamlit.py", "tests/test_app_adapters.py", "docs/STREAMLIT_APPLICATION.md"],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>