Closed B-1 with narrowly scoped numeric-boundary hardening and regression coverage.

- Oversized integers and non-finite values now produce field-specific `CaseFileError`s.
- Added four numeric-field regression cases and coverage for `NaN`, `Infinity`, and `-Infinity`.
- Added AppTest coverage confirming a clean UI error and empty `app.exception`.
- Protected artifacts and frozen engine paths remain unchanged.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "Focused tests: tests/test_app_case_files.py — 22 passed; AppTest regression — 1 passed. Quality gates: Ruff check passed, Ruff format check passed (229 files formatted), mypy passed (46 source files), compileall passed. Full pytest suite was not run per this correction's focused-testing policy.",
  "files_changed": ["src/pvt_phase_simulator_ui/case_files.py", "tests/test_app_case_files.py", "tests/test_app_streamlit.py"],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>