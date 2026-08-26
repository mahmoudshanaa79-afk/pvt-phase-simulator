Removed the optional untracked `.streamlit/config.toml`, resolving the verifier’s collapsed `.streamlit/` scope failure. No scientific or Python application code was changed.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "pytest: 1162 passed, 1 non-failing cache ACL warning in 514.29s with TEMP/TMP redirected after the direct run encountered sandbox temp-directory ACL errors; ruff check: passed; ruff format --check: 144 files already formatted; mypy src: passed; compileall src: passed; uv lock --check: passed with writable temporary cache; UI package imports: passed; git diff --check: passed with line-ending warnings; scope: scope ok; protected artifacts: unchanged",
  "files_changed": [".streamlit/config.toml"],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>