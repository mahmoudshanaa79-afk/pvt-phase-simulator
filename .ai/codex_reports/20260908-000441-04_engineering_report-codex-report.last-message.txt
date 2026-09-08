Implemented a printable, dependency-free HTML engineering report generated only from stored, non-stale result exports.

- Covers inputs, units, model scope, flash/stability, compositions, Z factors, envelope, critical point, sweep summary, limitations, and provenance.
- Explicitly labels unavailable, not-applicable, and failed values.
- Preserves existing CSV/JSON behavior.
- Protected artifact hashes remain unchanged.
- Full pytest suite was intentionally not run per the build-time testing policy.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "10 report tests passed; 6 focused Streamlit tests passed; 4 export-adapter tests and 1 sweep-export test passed; 5 final Streamlit/release tests passed including startup health smoke. Ruff check and format check passed; mypy passed for 47 source files; compileall passed.",
  "files_changed": ["src/pvt_phase_simulator_ui/reports.py", "src/pvt_phase_simulator_ui/views.py", "tests/test_app_reports.py", "tests/test_app_streamlit.py", "docs/STREAMLIT_APPLICATION.md"],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>