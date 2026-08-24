Updated only:

- `README.md`: documents the near-critical trivial-solution collapse and mixture-specific observed 7.86 K false-stable band.
- `docs/PROJECT_JOURNAL.md`: appends Module 21’s final acceptance entry without altering history.

All protected hashes match. Ruff gates pass. Full suite: 1,137 passed. Existing `.ai` changes were untouched.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": ".venv/Scripts/python.exe -m pytest -q: 1137 passed in 433.15s using a redirected pytest temp directory after the default Windows temp path produced permission-only setup errors; .venv/Scripts/python.exe -m ruff check .: All checks passed; .venv/Scripts/python.exe -m ruff format --check .: 107 files already formatted",
  "files_changed": ["README.md", "docs/PROJECT_JOURNAL.md"],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>