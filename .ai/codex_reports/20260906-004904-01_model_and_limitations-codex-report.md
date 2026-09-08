Implemented the Overview “Model and limitations” panel with repository-backed components, validation scope, and provenance. Added semantic UI tests and documentation. Scientific and protected artifacts remain unchanged.

All required tests and quality gates pass. Pytest emitted one non-failing cache-permission warning.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "pytest: 1238 passed, 1 warning; ruff check: passed; ruff format --check: 192 files formatted; mypy: no issues in 44 source files; compileall: passed",
  "files_changed": ["src/pvt_phase_simulator_ui/model_scope.py", "src/pvt_phase_simulator_ui/adapters.py", "src/pvt_phase_simulator_ui/views.py", "tests/test_app_streamlit.py", "docs/STREAMLIT_APPLICATION.md"],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>