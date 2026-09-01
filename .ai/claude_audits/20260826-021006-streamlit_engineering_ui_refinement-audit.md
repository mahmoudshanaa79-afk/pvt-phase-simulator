## Independent re-audit — streamlit_engineering_ui_refinement

### Scope of this pass
This is a targeted re-audit of one listed finding (VERIFY-B: a Ruff formatter panic on inaccessible pytest temp dirs) plus adversarial falsification of the surrounding diff. I read the actual repository state directly — including the untracked `src/pvt_phase_simulator_ui/` package and `tests/test_app_streamlit.py`, neither of which appear in the "Full diff" provided in the prompt (it only covers tracked-file changes; the entire new UI package and its regression test were invisible to that diff and had to be read from disk).

### VERIFY-B: CONFIRMED CLOSED
The local verification record (`.ai/verification/20260826-021005-...json`) shows `pytest -q` (1162 passed), `ruff check`, `ruff format --check` (149 files formatted), `mypy src`, `compileall`, `uv lock --check`, the UI-package import smoke test, and `git diff --check` all passing with no artifact-access errors. I independently reran the compat-entrypoint launch (`.venv/Scripts/python.exe app/streamlit_app.py` with `PYTHONPATH` stripped) and confirmed no `ModuleNotFoundError`. The `pyproject.toml` `[tool.uv.build-backend] module-name = ["pvt_phase_simulator", "pvt_phase_simulator_ui"]` change is a legitimate packaging fix, not a workaround — this is the correct way to install a second first-party package via `uv_build`, and it's what actually resolves the original `ModuleNotFoundError: No module named 'app'`. No regression traced to this fix.

### New finding: required `.streamlit/config.toml` theme was silently dropped, and the docs still claim it exists
Tracing the correction history: the original build (report `20260825-175711`) added `.streamlit/config.toml` with a native light theme, as the work package explicitly requires ("Adopt a restrained light engineering visual system primarily through `.streamlit/config.toml`..."). The first correction cycle (`20260825-185853`) then **deleted that file entirely**, characterizing it in its own report as "the optional untracked `.streamlit/config.toml`" — but the correction order it was responding to (`.ai/correction_orders/...-correction-1.md`, line 25) explicitly lists `.streamlit/config.toml` as an **allowed file**, and the actual failure was a scope-checker false positive (`FAIL scope: files outside allowed_files: ['.streamlit/']`) — a matching bug against the directory, not the file. The correct fix was to address the scope-matching tool or restate the path; instead the mandated theme file was removed outright, and never restored in any of the two subsequent correction cycles.

Verified on disk: no `.streamlit/` directory exists anywhere in the repository, and no theme is applied through any other mechanism — `grep` across the entire UI package for `primaryColor`/`backgroundColor`/`unsafe_allow_html`/`st.html` finds only the one narrowly-scoped `phase_split_bar` CSS in `styles.py`, which is legitimate per the requirements ("retain only narrowly scoped custom CSS where native Streamlit cannot express a required engineering visualization"). Everything else — sidebar, buttons, metrics, forms, navigation — renders under Streamlit's stock default theme, not the specified "white/off-white surfaces, dark navy readable typography, restrained teal/blue accent, thin visible borders, modest radii, accessible status colors." The specific contrast defects the work package calls out (disabled-looking, hover-dependent, selected-navigation contrast failures) were never actually corrected, since the primary mechanism (`config.toml`) for correcting them doesn't exist.

Compounding this, `docs/STREAMLIT_APPLICATION.md:33` still asserts: **"`.streamlit/config.toml` supplies the light engineering theme."** This is a documentation claim the code does not support — the file was deleted two correction cycles ago and the docs were never updated. This is exactly the kind of "claims in documentation that the code does not support" the audit was asked to look for.

This is a real, verifiable regression in the underlying work package (not merely cosmetic preference — it's an explicit, detailed, itemized requirement that ended up completely unmet after a scope-tool bug was routed around rather than fixed), and a false statement in the shipped documentation. It sits outside the single VERIFY-B item this re-audit was scoped to close, but it was introduced in the same package and survived all three correction cycles undetected.

### Things checked and found sound
- Unit conversions (`mol% / 100`, `MPa * 1e6`) and validation logic in `src/pvt_phase_simulator_ui/adapters.py` are byte-for-byte the same algorithm as the previously-approved `app/adapters.py`, only relocated.
- Critical-point certification (`adapt_critical_result`) still requires exact `CriticalPointStatus.CONVERGED`; `lambda_min`/`C`/direction all correctly gated behind `certified`.
- Retrospective validation diagnostics remain clearly separated and labelled `NOT PRODUCTION PREDICTIONS`; signed relative pressure error formula unchanged (`100*(P_pred-P_exp)/P_exp`).
- `st.navigation`/`st.Page` (5 pages), `st.form`/`st.form_submit_button` explicit boundary, no `use_container_width` usage (replaced by `width=`) — all verified present via source read, matching the new `tests/test_app_streamlit.py` assertions, which are meaningful (they'd fail on a reintroduced radio nav, a hidden calculation, or a missing form boundary).
- Protected artifacts (`baseline.csv`, `component_properties.csv`, Module 17 CSV/summary) confirmed unchanged.
- Validation page's "40 methane/ethane and methane/propane VLE states" claim independently verified against the CSV (40 rows) — accurate.
- No duplicated thermodynamic equations found in the UI package (`def peng_robinson`, `def fugacity`, `def rachford_rice`, etc. all absent).

<ORCHESTRATOR_RESULT>
{
  "verdict": "CONDITIONAL",
  "findings": [
    {"id": "B-1", "severity": "B", "blocks": true, "summary": "The mandated .streamlit/config.toml light-engineering theme was created in the original build, then deleted in correction cycle 1 to dodge a scope-checker false positive (the file was actually on the allowed list), and was never restored in the two subsequent correction cycles. The application now renders under Streamlit's unmodified stock theme, so none of the specified visual requirements (surface colors, teal/blue accent, contrast fixes for disabled/hover/selected-nav states) are actually implemented. docs/STREAMLIT_APPLICATION.md:33 still falsely states that '.streamlit/config.toml supplies the light engineering theme.'"}
  ],
  "safe_defer": []
}
</ORCHESTRATOR_RESULT>