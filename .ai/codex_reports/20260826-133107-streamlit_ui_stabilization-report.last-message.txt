Implemented the Streamlit UI stabilization entirely in the allowed application layer.

Key outcomes:

- Visible native sidebar navigation with all five destinations and working direct routes.
- Centered envelope tracing produces both branches for the default case and correctly reports the operating point inside the envelope.
- Missing branches report engine termination details in both page content and figure annotations.
- Added bounded caching and realistic progress feedback.
- Added disabled-action explanations, engineering-language critical-point copy, display-only rounding, validation summary metrics, square parity charts, and accessible muted captions.
- Frozen engine paths remain unchanged; all protected hashes match.
- Browser automation was unavailable, so rendering was verified with Streamlit AppTest and HTTP 200 checks for every route.

Verification:

- Pytest: 1,167 passed.
- Ruff check and format: passed.
- MyPy: passed.
- Compileall: passed.
- `git diff --check`: passed.
- Default envelope runtime: 22.26 s; bubble 15 points, dew 11 points.
- Critical regression test: passed at full precision.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "pytest: 1167 passed in 329.20s using a workspace-local temporary directory because the sandbox denied pytest's default Windows temp path; ruff check: passed; ruff format --check: 154 files formatted; mypy src app: passed; compileall src app: passed; git diff --check: passed; focused critical regression: passed; all protected artifact hashes matched",
  "files_changed": [".streamlit/config.toml", "src/pvt_phase_simulator_ui/adapters.py", "src/pvt_phase_simulator_ui/app.py", "src/pvt_phase_simulator_ui/views.py", "tests/test_app_adapters.py", "tests/test_app_streamlit.py"],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>