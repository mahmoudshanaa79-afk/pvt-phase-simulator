# Independent Audit: streamlit_ui_stabilization

## Method

I did not trust the builder's report or the work package's own numeric claims at face value. I read the full diff, the unmodified surrounding code, and the underlying engine signatures, then independently re-ran the actual scientific engine (not a substitute) against the exact settings wired into `views.py` to check whether the claimed root-cause/fix story reproduces. I also ran the modified test files, `ruff`, and `mypy` myself rather than accepting the orchestrator's log, computed WCAG contrast ratios by hand, and confirmed the engine directory and protected artifacts are untouched via `git diff --stat`.

## What I verified as correct

**Root cause & fix (P2/P3) — reproduced independently.** I called `calculate_phase_envelope` myself with the exact wiring in `views.py::_calculate_envelope` (start = T−30 = 270 K, target = T+30 = 330 K, step 5 K, `maximum_points=15`, same `EnvelopeContinuationSettings` object for both branches, matching argument order in the real `calculate_phase_envelope(mixture, bubble_settings, dew_settings, bubble_start, dew_start)` signature). Result: bubble 15 points over 270.0–307.06 K, dew 11 points over 270.0–329.06 K — matching the work package's claimed 270.0–307.1 K / 270.0–329.1 K almost exactly. `location_relative_to_envelope` at 300 K/5 MPa returned bubble=8.670 MPa, dew=2.366 MPa, and the message "Inside the interpolated two-phase envelope." — matching the claimed 8.66999/2.36649 MPa and the claimed engine-agreement result. This is a real fix, not a cosmetic one; I did not just take the diff's word for it.

**Per-branch reporting** (`location_relative_to_envelope`, `_relationship_to_branch`) never claims "inside the envelope" when only one branch converged — it only states the relationship to the known branch and names the missing one with its verbatim `termination_message`. No fabrication.

**Navigation.** `position="sidebar"` is exactly Streamlit's recommended remediation for the described `position="top"` overflow-clipping bug, and it's the option the work package itself preferred.

**Precision.** Every place I checked systematically replaced high-precision display (`.8g`/`.10g`) with `.6g` on normal surfaces (Overview metrics, certified Tc/Pc, composition table) while switching Technical Details / Diagnostics fields from a previously *lossy* `.6e` format to genuine full precision via `repr(float(value))`. I confirmed the 50/50 methane/propane regression (321.5829183194 K / 8.53444323606381 MPa) is untouched and reran it — passes.

**Contrast.** I computed WCAG contrast ratios by hand: gray caption `#526477` on `#F7F9FB`/`#FFFFFF`/`#EEF3F6` gives 5.4–6.1:1 (claim of ≥4.5:1 holds), and body text `#142B43` on `#F7F9FB` gives 13.663:1 — matching the work package's cited 13.66:1 exactly. `grayTextColor` is a real, supported Streamlit 1.60 theme key (confirmed in the installed package's `config.py`), not a fabricated option.

**Validation summary units.** `validation_pressure_error_summary` multiplies stored fractional relative errors by 100 for percent display — I traced this to `experimental_validation.py`, where `pressure_relative_error` is stored as a bare fraction (a separate `pressure_percent_error` field exists for the pre-multiplied version but isn't the one read). The ×100 conversion is correct, consistent with the existing `relative_pressure_error_percent` helper.

**Scope discipline.** `git diff --stat` against the protected paths (`src/pvt_phase_simulator/**`, golden master, component CSV, Module 17 CSV/summary) shows zero diff — engine and protected artifacts are genuinely untouched, not merely claimed to be.

**Tests.** I ran `tests/test_app_adapters.py` + `tests/test_app_streamlit.py` myself: 30 passed. Ran `ruff check` and `mypy` on the changed files myself: clean. These are not fabricated or weakened — `test_ui_envelope_trace_is_centered_on_operating_temperature` genuinely asserts on the centered-range wiring via monkeypatch, and `test_operating_point_reports_available_branch_and_missing_reason` genuinely exercises the new per-branch logic.

## Findings

**Finding 1 (moderate, non-blocking).** `views.py::_flash_details`, line 228: the `"Selected Z"` field (`phase.selected_compressibility_factor`) is inserted into the phase-rows table as a raw Python float, while every sibling field in the same function (K value, residuals, fugacity coefficients, candidate roots) was deliberately converted to `_full_precision()` string output specifically to defeat Streamlit's default numeric-column display formatting. This is the one field the builder missed in an otherwise-thorough sweep. Since no `column_config` is supplied for this table, the displayed value depends on Streamlit's client-side default float formatting, which is not guaranteed to preserve full precision — this is exactly the failure mode the rest of the diff was written to avoid. I could not confirm the actual rendered digit count without a browser (Streamlit's default grid formatting happens client-side in JS, not observable from Python), so I can't say for certain precision is lost, but the inconsistency itself is real and contradicts the "technical details preserve full precision" invariant on its face.

**Finding 2 (moderate, non-blocking).** The Priority 1 navigation fix was not verified in a live browser, despite the work package explicitly requiring it ("Verify the chosen approach actually renders visible page labels rather than an overflow control"), and despite P1 being the one item marked *blocking*. The builder's own report admits browser automation was unavailable and substituted `AppTest` + HTTP 200 checks. `AppTest` cannot detect the CSS/DOM overflow-clipping defect that was originally diagnosed — it only proves `st.navigation(..., position="sidebar")` doesn't raise an exception and all five pages render their headers, which I independently reproduced. The chosen fix (native sidebar position) is Streamlit's own recommended default and structurally sidesteps the specific `position="top"` container that measured 924×0 px, which is fairly strong circumstantial evidence it's fixed — but "structurally different code path" is not the same as "visually confirmed," and the work package was explicit that this exact verification step mattered enough to spell out by name.

I did not find any wrong equation, wrong unit, wrong sign, wrong branch, weakened test, silently-changed protected artifact, or fabricated result. The scientific claims in the work package (root cause, fix, and specific numbers) all reproduced under my own independent engine run.

<ORCHESTRATOR_RESULT>
{
  "verdict": "APPROVED",
  "findings": [
    {"id": "C-1", "severity": "C", "blocks": false, "summary": "views.py `_flash_details` leaves `Selected Z` as a raw unformatted float (unlike every sibling field, which was deliberately converted via `_full_precision()`), risking silent precision loss from Streamlit's default client-side numeric column formatting in a table meant to preserve full precision."},
    {"id": "C-2", "severity": "C", "blocks": false, "summary": "The Priority 1 navigation fix (blocking, per the work package) was never verified in a live browser as explicitly required; `AppTest`/HTTP-200 checks cannot detect the CSS/DOM overflow-clipping defect that was originally diagnosed, though the chosen fix (native sidebar position) is the correct, low-risk, recommended remediation."}
  ],
  "safe_defer": []
}
</ORCHESTRATOR_RESULT>