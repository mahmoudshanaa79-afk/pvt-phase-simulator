Closed B-1 narrowly:

- Certified critical-point `trace.text` now converts K/Pa values to selected units using the existing boundary converters and 12-significant-digit plot formatting.
- Added °F/psi regression coverage using dynamically derived expectations.
- Protected paths remain unchanged; all protected hashes match.

Full suite: 1,256 passed.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "Focused regression: 1 passed. Full pytest suite with workspace TEMP/TMP: 1256 passed, 1 cache-permission warning. Ruff check passed; Ruff format check passed (210 files formatted); mypy passed (45 source files); compileall passed.",
  "files_changed": ["src/pvt_phase_simulator_ui/views.py", "tests/test_app_adapters.py"],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>