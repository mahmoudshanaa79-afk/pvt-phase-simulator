Field-units package is complete. I preserved the existing implementation and centralized the final legacy pressure conversion in `units.py`. Protected artifacts remain unchanged; no Streamlit server was started.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "pytest: 1255 passed in 648.64s (TEMP/TMP redirected to a workspace-local directory and pytest cache disabled due sandbox ACLs); ruff check: all checks passed; ruff format --check: 203 files already formatted; mypy: success, no issues in 45 source files; compileall: exit 0",
  "files_changed": [
    "docs/STREAMLIT_APPLICATION.md",
    "src/pvt_phase_simulator_ui/adapters.py",
    "src/pvt_phase_simulator_ui/app.py",
    "src/pvt_phase_simulator_ui/context.py",
    "src/pvt_phase_simulator_ui/exports.py",
    "src/pvt_phase_simulator_ui/model_scope.py",
    "src/pvt_phase_simulator_ui/state.py",
    "src/pvt_phase_simulator_ui/sweeps.py",
    "src/pvt_phase_simulator_ui/units.py",
    "src/pvt_phase_simulator_ui/views.py",
    "tests/test_app_adapters.py",
    "tests/test_app_streamlit.py",
    "tests/test_app_sweeps.py"
  ],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>