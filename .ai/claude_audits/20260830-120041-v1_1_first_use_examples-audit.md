# Independent Audit: v1_1_first_use_examples

## Scope of change
`git diff --name-only HEAD~1 HEAD` confirms the only source touched is `src/pvt_phase_simulator_ui/` (the application layer). `git diff --stat` against `src/pvt_phase_simulator/`, `data/component_properties.csv`, `docs/validation/`, and `tests/golden_master/` is empty — the scientific core and all protected artifacts are byte-unchanged, satisfying the declared invariant.

## What the change does
- `state.py` adds an `InputExample` frozen dataclass, a tuple `INPUT_EXAMPLES` of three cases, and `apply_selected_input_example`, a pure function that copies five float fields (`methane_pct`, `ethane_pct`, `propane_pct`, `temperature_k`, `pressure_mpa`) into session state and touches nothing else — no `results`, no `submitted_inputs`, no import of any flash/envelope/critical API.
- `app.py` adds an `st.selectbox` outside the `st.form` block (necessary, since widgets inside a form don't rerun on `on_change` until submit), wired via `on_change=apply_selected_input_example, args=(session(),)`. It also raises the `number_input` display format from `%.10g` to `%.15g` and drops the redundant `value=` args now that session-state defaults exist.
- `docs/STREAMLIT_APPLICATION.md` gets a truthful two-paragraph description matching the code.

## Independent verification performed (not taken on faith)
1. **Truthfulness of all three example labels**, checked by running the actual production engine (`run_validated_flash`) myself:
   - "Default two-phase-oriented case" (50/50 CH4/C3, 300 K, 5 MPa) → `phase_state: two_phase`. Confirmed.
   - "Known single-phase case at 300 K and 20 MPa" → `phase_state: single_phase`. Confirmed. This value also traces to a separately-audited P1 finding (`streamlit_public_release_p1_fixes.json`) from an earlier package, not fabricated here.
   - "Audited critical-solver seed" (321.5829183194 K, 8.53444323606381 MPa) — traced via grep through `docs/CRITICAL_POINT_SOLVER.md`, `docs/PROJECT_JOURNAL.md`, and the much earlier `streamlit_full_application.json`/`streamlit_ui_stabilization.json` work packages, which state this exact value as "the approved zero-kij 50/50 methane/propane critical regression." It is a pre-existing, previously-audited value reused verbatim, not new science.
2. **Precision claim**: verified `%.10g % 8.53444323606381` truncates to `8.534443236` (10 sig figs) vs. the actual 15-sig-fig value — so the `%.10g → %.15g` format bump is a real, necessary fix to avoid display truncation of the new example's values, not unexplained scope creep.
3. **No hidden computation on selection**: read `apply_selected_input_example` in full — it only assigns five primitive floats, never imports or calls `run_validated_flash`/adapters compute paths. The `test_example_selection_populates_inputs_without_populating_results` test independently exercises the real `on_change` wiring (not just the pure function) and asserts `results == {}` and `submitted_inputs is None` after selection — I ran this test myself and it passed.
4. **Callback doesn't fire on unrelated reruns**: confirmed via `test_custom_edits_after_example_selection_validate_and_submit_normally`, which selects an example, edits fields, then submits — the submitted values reflect the edits, not a reversion to the example. If the `on_change` callback fired spuriously on the submit click, this test would fail; it doesn't.
5. **Widget-default ordering**: traced that `_input_form()` is called exactly once, from `run_app()`, always immediately after `initialize_session(session())` — so the `number_input` keys always have session-state defaults before the `value=`-less widgets are instantiated. No path renders the form without defaults.
6. Ran `pytest tests/test_app_adapters.py tests/test_app_streamlit.py` (39 passed), `ruff check`, and `mypy` on the two changed source files myself — all clean, independent of the builder's report.

## Findings
None that rise to a defect. The tests are not tautological — they assert on sentinel prior state remaining untouched, on exact widget values through the real Streamlit `AppTest` harness, and on edited (not example) values surviving submission, any of which would plausibly fail under a buggy implementation. No sign, unit, or branch error. No protected artifact touched. No documentation claim unsupported by the code or the engine.

One minor observation, not blocking: the `%.15g` precision bump applies to all five fields globally rather than only the two needed for the new critical-seed example. This is a reasonable, minimal side effect of the same objective (undistorted editable values) rather than unrelated scope creep, so I record it as informational only.

<ORCHESTRATOR_RESULT>
{
  "verdict": "APPROVED",
  "findings": [],
  "safe_defer": [
    {"id": "D-1", "severity": "D", "blocks": false, "summary": "Display-format precision (%.10g -> %.15g) was widened for all five input fields, not just the two needed for the new critical-solver-seed example; harmless and justified by the same 'preserve exact editable values' objective, but broader than strictly necessary."}
  ]
}
</ORCHESTRATOR_RESULT>