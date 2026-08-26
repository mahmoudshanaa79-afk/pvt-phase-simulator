Implemented the engineering UI refinement and installed-package migration.

Key outcomes:

- Fixed clean-shell Streamlit imports with `pvt_phase_simulator_ui`.
- Added root and compatibility Streamlit entrypoints.
- Added five-page `st.navigation` architecture.
- Added explicit submitted-input and heavy-calculation boundaries.
- Reworked engineering results, diagnostics, validation, and critical certification.
- Added native light theme and narrow phase-split CSS.
- Preserved protected scientific files and artifact hashes.
- Full suite: 1,162 passed. All required quality gates passed.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "Full pytest suite passed: 1162 passed, 1 non-failing pytest cache permission warning in 526.31s; pytest used a fresh permitted basetemp via PYTEST_ADDOPTS because the managed sandbox denied its default temp directory. Application suite passed: 25 passed. ruff check, ruff format --check, mypy src, compileall src, uv lock --check, installed UI imports, clean-shell compatibility startup, protected artifact hashes, and git diff --check all passed.",
  "files_changed": [
    ".streamlit/config.toml",
    "README.md",
    "app/adapters.py",
    "app/state.py",
    "app/streamlit_app.py",
    "app/styles.py",
    "docs/STREAMLIT_APPLICATION.md",
    "pyproject.toml",
    "src/pvt_phase_simulator_ui/__init__.py",
    "src/pvt_phase_simulator_ui/adapters.py",
    "src/pvt_phase_simulator_ui/app.py",
    "src/pvt_phase_simulator_ui/context.py",
    "src/pvt_phase_simulator_ui/pages/__init__.py",
    "src/pvt_phase_simulator_ui/pages/critical_point.py",
    "src/pvt_phase_simulator_ui/pages/diagnostics.py",
    "src/pvt_phase_simulator_ui/pages/overview.py",
    "src/pvt_phase_simulator_ui/pages/phase_envelope.py",
    "src/pvt_phase_simulator_ui/pages/validation.py",
    "src/pvt_phase_simulator_ui/state.py",
    "src/pvt_phase_simulator_ui/styles.py",
    "src/pvt_phase_simulator_ui/views.py",
    "streamlit_app.py",
    "tests/test_app_adapters.py",
    "tests/test_app_streamlit.py"
  ],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>