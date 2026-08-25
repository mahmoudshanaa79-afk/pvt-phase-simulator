Removed the optional untracked `.streamlit/config.toml`, eliminating the erroneous `.streamlit/` scope token. Scope and protected-artifact checks now pass.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "pytest: 1155 passed, 1 non-failing cache ACL warning (rerun with TEMP/TMP redirected after the direct invocation hit a system temp-directory ACL error); ruff check: passed; ruff format --check: 122 files already formatted; mypy src app: passed; compileall src app: passed; git diff --check: passed with line-ending warnings; orchestrator scope check: scope ok; all protected artifact hashes unchanged",
  "files_changed": ["README.md", "app/__init__.py", "app/adapters.py", "app/state.py", "app/streamlit_app.py", "app/styles.py", "docs/STREAMLIT_APPLICATION.md", "tests/test_app_adapters.py"],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>