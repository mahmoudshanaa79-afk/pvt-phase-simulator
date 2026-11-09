# Project status

Last updated: 8 November 2026 (v1.6.0 is being published from PR #36; the
next release, v1.7.0, will be prepared for the owner).

This page brings together what OpenPhase does today, what supports it, and what
waits on a decision. Details live in the linked documents.

## What exists

**Scientific engine (frozen; changed only with the owner's approval).**

- Peng–Robinson EOS with classical mixing for verified methane, ethane and
  propane; kij = 0 by default, with optional user-supplied kij.
- Tangent-plane-distance stability and two-phase flash.
- Bubble and dew pressures with an optional Newton refinement, and honest
  reporting of hidden, multiple and unbracketed roots (P2, P7, P8).
- P–T envelope tracing with natural and pseudo-arclength continuation.
- Mixture criticality derivatives and a critical-point solver that requires
  both Gibbs conditions.
- Scientific plotting.

**Validation framework (V2-01-A to E).**

- Typed records, provenance and serialization.
- Generalized metrics that keep model accuracy separate from software
  correctness.
- A reproducible evidence report over the protected Module 17 data (May et al.,
  2015; CH4+C2 and CH4+C3), and pure-component saturation references.

**Application (public on Streamlit Community Cloud).**

- Flash, phase envelope with the extended display overlay and the operating
  point, critical point, engineering sweeps, validation and diagnostics pages.
- Field units, save and load of cases, an engineering report, and exports.
- An optional, clearly labelled kij input (Option 2 of P6).
- Plain-language explanations next to the solver's diagnostic codes.
- Learn mode, with explanations and exercises that are checked against the
  engine, and links to the teaching labs.
- A supported input range of 50–1000 K and 1 Pa–1 GPa, checked before any
  engine call.

**Teaching.** Four labs in [docs/teaching](teaching/) (methane–propane,
methane–ethane, composition and the envelope, what kij does), each with an
instructor key whose numbers are recomputed from the engine by the tests.

## Evidence

- About 1,800 test cases. CI runs lint, types, the full suite in parallel, a
  real-browser test, a localhost health check and a run with only the deployed
  dependencies on every push.
- Experimental bubble pressures (record regenerated after P7 and P8):
  - CH4+C2: 1.02 % AARD, 17 of 17 states;
  - CH4+C3: 1.01 % AARD, 23 of 23 states.
- Certified critical point of 50/50 methane/propane: 321.58 K, 8.534 MPa.
- [Dew investigation](DEW_INVESTIGATION.md): the large CH4+C3 dew-pressure
  error comes mostly from an ill-posed question and from hidden second roots,
  not from model error.
- App robustness, performance and usability checks:
  `docs/investigations/app_performance.md`,
  `docs/investigations/usability_review.md` and the robustness tests.

## Decided

| Item | Outcome |
|---|---|
| P1: root-count-tolerant continuation | Done, PR #15. The extended-envelope survey now closes 14 of 16 cases (10 with the pre-P1 rule, both on the P7 solver; 13 and 9 before P7). The 2 that still stop early are trivial-state bubble stops. |
| P5: neutral dew stop marker label | Done, PR #16, in the app layer. The engine's own label is unchanged. |
| P2: refine grid boundaries in the saturation scan | Done, owner-approved. Nine dew results that looked unique are now reported as ambiguous (`HIDDEN_SATURATION_ROOT`); each second root is confirmed. The Module 17 artifacts were regenerated: CH4+C3 dew 7 → 1 unique results, CH4+C2 dew 15 → 12. Bubble results unchanged. |
| Pure-component reference data (V2-01-E) | Accepted, PR #10 (`docs/PURE_COMPONENT_SATURATION.md`). |
| P3: conditioning-aware dew metric | Done for both binaries (`docs/investigations/dew_conditioning.csv`). PR's vapour composition at the measured pressure is within the stated uncertainty at 22 of 23 CH4+C3 states and 16 of 16 assessable CH4+C2 states (15 of 15 before P7). Shown on the Validation page. |
| P4: Newton refinement in validation | Option B, done in PR #18: both runs are reported side by side in `docs/investigations/validation_newton_comparison.md`. The frozen artifacts are unchanged. Newton's extra dew results at multi-root states are labelled one root of several, not accuracy. |
| P6: non-zero kij | Option 2, owner-approved (2 Nov 2026): kij = 0 stays the default and the validation reference; the app offers an optional, labelled kij input (PR #32). Study: `docs/investigations/kij_study.md` (CH4+C3 fitted kij +0.0021). |
| P7: refine boundaries when the scan finds no root | Done, owner-approved (1 Nov 2026). All nine `not_found` bubble states of the record now converge (CH4+C2 bubble 11 → 17, CH4+C3 20 → 23); 7 agree with the Newton option to 1e-8 and 250 K agrees with the independent envelope reference to 5e-14. |
| P8: check past a failed walk step | Done, owner-approved (1 Nov 2026). CH4+C2 dew 008, 009, 013 and 017 have an upper root the solver missed and are now ambiguous; CH4+C2 dew 12 states at 5.34 % → 8 states at 2.07 %. Lab 2 updated. |
| P9: skip repeated validation of the same inputs | Owner-approved (8 Nov 2026) on the condition that every result stays byte-identical; see PR #43 and `tools/engine_fingerprint.py`. |
| Parallel CI | Accepted default: the full suite runs with pytest-xdist (`-n auto --dist loadfile`); every test still runs once. |
| Supported input range | Accepted default: 50–1000 K and 1 Pa–1 GPa, checked by the form, sweeps and case files (`adapters.py`). |

## Waiting on an owner decision

| Item | Where | Effect |
|---|---|---|
| Release v1.6.0 | PR #36 (being published by the desktop session) | Public app picks up v1.6 |
| Release v1.7.0 | prepared at the end of the 8 November session | Not released or tagged until approved |
| Butane Table 5 values | `docs/BUTANES_ADMISSION_PLAN.md` and the draft butanes PR | Admits isobutane and n-butane (validation only) |
| P10: faster envelope continuation that changes recorded results | `docs/ENGINE_CHANGE_PROPOSALS.md` | Option (b) about 25 % faster with identical envelope points on six states |
| Faculty review | review brief (private artifact) | Six scientific questions for a reviewer |

## Not implemented (by design, for now)

- Three-phase or multiphase flash.
- Volume translation (approved as an optional module; not yet built). Liquid
  densities are not quantitative.
- Components beyond C1–C3 (butanes waiting for verified constants; CO2 and N2
  not started).
- Fitted kij as a default: kij is optional and user-supplied, never applied
  silently.
- More than one experimental source.

## Suggested next steps, in order

1. Publish v1.6.0 and, after review, v1.7.0.
2. Supply the six Yang & Richter (2025) Table 5 values and finish the butanes
   draft PR (validation only).
3. Decide on P10 (b).
4. Volume translation as an optional module, then a CO2/N2 plan with measured
   VLE data.
5. A second experimental source for methane + propane, to test kij beyond one
   laboratory.

## Session log

Newest first. One short entry per task, written by whichever account did the
work and added in that task's PR. Sessions read only the latest few entries.

- **2026-11-09, web (butanes DRAFT, owner approval B, not merged):**
  - Done: draft PR "Butanes: DRAFT, do not merge until Table 5 values
    arrive". Second data file and manifest (36 May 2015 points), optional
    butane systems, and `tools/admit_butanes.py`, the one final-step
    command. Consumers (validation adapter, kij report, count tests) now work
    before and after admission. Dry run on provisional CoolProp values: C1-C3
    rows byte-identical to master, golden master unchanged. Suite after
    admission: 1860 passed; the only failure is the provenance gate for
    provisional rows, which final-mode rows pass. Provisional bubble AARD
    3.45 % (C1+iC4) and 3.56 % (C1+nC4); all 36 dew states stop with the
    engine's own reason. See `docs/investigations/butanes_admission_dry_run.md`.
  - Next: the owner enters the Table 5 values and runs the final step.

- **2026-11-09, desktop (volume translation table was hidden):**
  - Done: flipping "Show volume-translated densities" changed nothing visible,
    because the table sat inside the collapsed "Technical details" section.
    AppTest reads collapsed content, so the tests passed. It now follows the
    phase compositions on Overview; an AppTest check (which fails on the old
    code) and a browser step guard it.
  - Next: merge master into PR 51; the owner decides v1.7.0.

- **2026-11-09, desktop (v1.6.0 published; review of the finalize session):**
  - Done: published v1.6.0 at `34ac3e5` (owner-approved; the fix for repeated
    sweeps went in first). Independently checked the finalize session: the P9
    caches give identical results serially and in 8 threads; a separate script
    reproduces the volume-translation density errors; a real-browser walk of
    every page shows no errors, and the public app runs current master.
  - Fixed: the app said the first envelope takes "half a minute to a minute".
    Timed from click to plot it takes 103 s on the public app and 115-162 s on
    a laptop, so the note now says one to three minutes.
  - Open PRs: 51 (release v1.7.0, owner), 47 (butanes draft, Table 5 values).
  - Next: owner decides v1.7.0, P10 and P11 defaults.

- **2026-11-08, web (CO2/N2 plan, owner approval D, docs only):**
  - Done: `docs/CO2_N2_ADMISSION_PLAN.md`: why CO2 and N2 are harder (kij,
    solid CO2, supercritical N2), property sources, provisional CoolProp
    6.6.0 constants run in the session, candidate VLE datasets (all marked
    not verified: ThermoML, doi.org and publishers did not resolve from the
    web session), steps and owner decisions. Nothing in data/, engine or app.
  - Open PRs: butanes draft (do not merge).
  - Next: release v1.7.0 PR (awaiting owner approval).

- **2026-11-08, web (volume translation P11, owner approval C):**
  - Done: optional Péneloux module `eos/volume_translation.py`, off by
    default and called by no solver (engine fingerprint unchanged). App
    switch "Advanced: volume translation (Péneloux)" adds one Overview table.
    Shifts fitted at T_r = 0.7 against the accepted pure-component reference
    file. Held-out liquid-density AARD 8.74/6.51/5.51 % falls to
    2.64/2.69/2.76 % (C1/C2/C3). The worst error, at T_r = 0.98, gets slightly
    worse. No mixture-density validation. See `docs/VOLUME_TRANSLATION.md`.
  - Open PRs: butanes draft (do not merge).
  - Next: release v1.7.0 PR (awaiting owner approval).

- **2026-11-08, web (final docs):**
  - Done: new README (what OpenPhase is and is not, quick start, public app,
    pages, labs, evidence, known limits); `docs/USER_GUIDE.md`;
    `docs/README.md` index split into current, design and historical
    documents; `CHANGELOG.md` from the GitHub releases and release notes. The
    README evidence table is checked against the record by
    `tests/test_validation_claims.py`.
  - Open PRs: butanes draft (do not merge).
  - Next: release v1.7.0 PR (awaiting owner approval).

- **2026-11-08, web (final polish):**
  - Done: rewrote the top of this page (what exists, decided items incl.
    P6-P9, waiting items, not implemented, next steps); parallel CI and the
    50-1000 K / 1 Pa-1 GPa input range recorded as accepted defaults.
    Usability findings #8 (all downloads `openphase-`), #10 (capitalised
    Validation direction labels, same stored values) and #11 (operating point
    marked on the envelope plot) fixed with tests. New
    `tests/test_docs_references.py` checks that every path the docs mention
    exists (none were dead).
  - Next: butanes draft PR, final docs.

- **2026-11-08, web (engine speed-up P9, owner approval A):**
  - Done: `tools/engine_fingerprint.py` hashes the complete canonical form of
    801 results (all 40 May states both ways, with and without Newton and kij;
    synthetic binaries and ternaries; flash; stability; the app's envelope,
    overlay, saturation pair, critical point and map). P9 as applied: a
    validation that already succeeded for the very same immutable row, row
    tuple, interaction mapping or (Z, A, B) root is not repeated; every call
    path and every public check is unchanged. 801 of 801 results identical,
    full suite green with no test edited. First envelope 82 -> 35 s (default
    example), 107 -> 48 s (critical seed), same machine. App time note
    updated and pinned to the measured CSV. P10 (result-changing speed-ups)
    measured and written up for the owner.
  - Next: final polish, butanes draft PR, final docs.

- **2026-11-08, desktop (release v1.6.0):**
  - Done: the owner approved v1.6. After this PR merges and master CI passes,
    the desktop session publishes the release (tag `v1.6.0`), and the owner
    reboots the Streamlit app.
  - Owner approvals for the next session (2026-11-08): engine speed-ups with
    byte-identical results (P9); a butanes draft PR on provisional values, not
    merged until the Table 5 values arrive; optional volume translation; a
    CO2/N2 plan (docs only).
  - Next: the finalize session (toward v1.7).

- **2026-11-08, desktop (repeated sweep bug):**
  - Done: an independent review of PR 39 found that repeating a sweep with the
    same inputs failed ("stopped unexpectedly") and removed the earlier result:
    the cached function updated a progress bar created outside it, which
    Streamlit cannot replay on a cache hit. Sweeps now use a small bounded
    store, with the progress bar outside it. A new test repeats flash, critical
    solver, criticality map and sweep through their real pages; it fails on the
    old code.
  - Next: merge master into PR 36, then release v1.6.0.

- **2026-11-03, web (Diagnostics raw-objects freeze, owner report):**
  - Done: the owner reported the app freezing after the Diagnostics "Show
    advanced raw public objects" switch. Reproduced in a real browser: with
    nothing run the switch is harmless, but after a phase envelope it drew
    the full envelope object (about 43 MB of JSON) and froze the tab. The
    page now shows a short envelope summary and offers the full object as a
    download built only on click. Tests: `tests/test_app_diagnostics_raw.py`
    and a browser step that turns the switch on and off.
  - Next: owner decisions on PR 36 (v1.6.0), P9 and the input range.

- **2026-11-03, web (v1.6.0 release notes updated, not merged):**
  - Done: merged master (crash hunt, performance, usability, deployment
    health, and the Diagnostics fix) into
    `release-v1.6.0` and added them to
    `docs/release_notes/v1.6.0.md`. PR 36 stays open; no tag.
  - Waiting for the owner: approve PR 36 (then merge, tag, reboot and run
    the checklist in `docs/STREAMLIT_APPLICATION.md`); P9; the input range;
    the butane values.

- **2026-11-03, web (deployment health):**
  - Done: `tests/test_app_deployment.py` (runtime imports declared, lock pins
    the project and its dependencies, Python 3.12 everywhere, every
    `config.toml` option is a Streamlit option, the app and engine import only
    built modules, the known-limits text). `tools/deploy_check.py` runs every
    page and a flash with only the deployed dependencies; it and
    `tools/streamlit_smoke.py` pass in a `--no-dev` environment. The app's
    known limits now name the validation source (May et al. (2015), via NIST
    ThermoML) and the input range. Reboot steps and a post-reboot checklist in
    `docs/STREAMLIT_APPLICATION.md`.
  - Next: the v1.6 release notes in PR 36 (owner decides the release).

- **2026-11-03, web (usability review):**
  - Done: `docs/investigations/usability_review.md` (12 findings from desktop,
    phone and dark-scheme screenshots). Fixed the 2 high and 5 medium ones:
    an honest envelope time note (minutes, not 20-30 s), Overview starts with
    "Start here" and shows the result before the model panel, the sidebar is
    collapsed on phones, empty states name the button, the composition table
    shows 6 significant figures with mol % (its format string was invalid),
    the phase split is stated in words, and Learn mode links the four labs.
    `tests/test_app_usability.py` pins each fix; the browser test adds a
    390 px page load and flash.
  - Open (low, for the owner): download names mix `pvt-` and `openphase-`.
  - Next: deployment health, then the v1.6 release notes.

- **2026-11-03, web (app performance):**
  - Done: `tools/profile_app.py` and `docs/investigations/app_performance.md`
    (before/after, median of 3). The phase envelope is the only slow action
    (about 2-3 min, engine time); everything else is under 5 s. Engine results
    are now cached with `st.cache_resource` (deeply immutable, bounded), so a
    repeated envelope takes 0.13 s instead of 3.4 s; the sweep is cached too.
    `tests/test_app_performance.py` proves byte-identical results and exports,
    complete keys and bounded memory. Engine proposal P9 (validate component
    parameters once per evaluation, about half the envelope time) waits for
    the owner.
  - Next: usability review and fixes.

- **2026-11-03, web (crash hunt):**
  - Done: robustness AppTests (`tests/test_app_robustness*.py`, harness in
    `tests/_robustness.py`) drive every page with hostile inputs, every unit,
    kij edges, odd sweeps, broken case files and every RUN action with each
    shipped example; a scenario fails on a raw exception, a generic
    safe-boundary message or a logged app error. Fixed: inputs the engine
    raises on (supported input range 50-1000 K, 1 Pa-1 GPa, now checked in
    the form), engine reasons shown when an action still raises, and deeply
    nested case files. No number changed.
  - Open: the input range is a web-session choice; the owner may change it.
  - Next: app performance (profile, caching), then usability.

- **2026-11-03, desktop (kij input visual check):**
  - Done: checked the web session's PRs 28 and 30-35 on GitHub (all merged,
    master CI green) and the kij expander in the real app: fields, disabled
    absent pairs, badge, caption and result note all correct. One fix: the
    Overview "Model and limitations" text still said "no fitted interaction
    parameters are used" with a user kij set; it now states the kij used.
  - Open: PR 36 (release v1.6.0) waits for the owner.
  - Next: owner approves v1.6 (then merge, tag, reboot and check the live
    app); butane values from Yang & Richter (2025) Table 5.

- **2026-11-02, web (v1.6.0 release prepared, not merged):**
  - Done: version 1.6.0 in `pyproject.toml` and `uv.lock`, the "(v1.6)"
    deployment wording in the README and `STREAMLIT_APPLICATION.md`, and
    `docs/release_notes/v1.6.0.md`. PR "Release v1.6.0 (awaiting owner
    approval)" is open and not merged; no tag.
  - Waiting for the owner: approval of the release PR, then the tag and the
    Streamlit Cloud reboot; the butane Table 5 values.
  - Next: after approval, merge, tag v1.6.0 and check the public app.

- **2026-11-02, web (butanes admission plan, docs only):**
  - Done: `docs/BUTANES_ADMISSION_PLAN.md`, a step-by-step plan for admitting
    isobutane and n-butane once the owner supplies the six Yang & Richter
    (2025) Table 5 values and approves the frozen-path edits. Nothing applied;
    `data/` and the engine are untouched.
  - Waiting for the owner: the six values and the approval; the choice of a
    second CSV versus extending the existing one; app option (a) or (b).

- **2026-11-02, web (Lab 4: what kij does):**
  - Done: `docs/teaching/LAB_04_BINARY_INTERACTION.md` (CH4+C3 at 243.62 K):
    bubble pressures at kij = 0 and the fitted +0.0021 against four measured
    states, a P-x-y table at both kij, and the state 013 dew solve, which
    stays ambiguous at both kij (20 of 23 CH4+C3 dew states ambiguous either
    way). No dew pressure is quoted at an ambiguous state.
    `tests/test_teaching_lab_04.py` recomputes every number through the app's
    input boundary and the engine.
  - Next: the v1.6.0 release PR (owner approval needed), the butanes plan.

- **2026-11-02, web (optional kij input, Option 2):**
  - Done: the owner approved Option 2 of P6. The sidebar form has a collapsed
    *Advanced: binary interaction (kij)* expander (one field per pair in the
    mixture, default 0, range -0.10 to +0.20). The submitted kij reaches every
    engine call the app makes; with kij = 0 no `binary_interactions` is passed,
    so results and exports are byte-identical. A non-zero kij shows a
    *user-supplied kij* badge and is stated on result pages, in exports, the
    HTML report and case files (schema 1.1.0 only when non-zero). The
    Validation page keeps the kij = 0 record. The operating-temperature
    readout also lists the incipient phase, for Lab 4.
  - Next: Lab 4 (kij), then the v1.6 release PR for the owner.

- **2026-11-02, web (plain-language solver codes):**
  - Done: `src/pvt_phase_simulator_ui/solver_codes.py` gives one sentence each
    for `BOUNDARY_SATURATION_ROOT`, `HIDDEN_SATURATION_ROOT` +
    `MULTIPLE_SATURATION_ROOTS` and `SATURATION_ROOT_UNBRACKETED`, always next
    to the code. The Phase Envelope action also solves bubble and dew pressure
    at the operating temperature; codes are explained there, on Diagnostics,
    in a Validation-page table of record states, in the export (schema 1.2.0)
    and in the HTML report. AppTests cover one real state per code.
  - Next: the owner-approved optional kij input (Option 2), then Lab 4.

- **2026-11-02, web (P7/P8 follow-ups):**
  - Done: reran the envelope survey (14 of 16 closed; P7 also fixed the 330 K
    warm start) and extended `tools/run_hidden_dew_root_check.py` to confirm
    every `HIDDEN_SATURATION_ROOT` state without the production verdict, by
    bracketing, PR's bubble isotherm or the traced dew branch, recorded per
    state in `docs/investigations/hidden_dew_root_check.csv` (13 of 13
    confirmed; CH4+C2 008 only by the dew branch). Stale numbers fixed in Lab 1,
    Learn mode, `PROJECT_STATUS.md`, `VALIDATION_FRAMEWORK.md`,
    `DEW_INVESTIGATION.md` and `STREAMLIT_APPLICATION.md`, with a test that
    recomputes each from the record. PR #27's evidence files are labelled
    pre-P7/P8 and left unchanged.
  - Next: plain-language solver codes in the app, then the kij input.

- **2026-11-02, web (kij study, P6):**
  - Done: `tools/run_kij_study.py`, the rendered `docs/investigations/kij_study.md`
    and `tests/test_kij_study.py` (PR #28), rerun on the P7/P8 engine; kij = 0
    reproduces the regenerated Module 17 record state by state. No engine
    change. Fits to bubble pressure: CH4+C2 0, CH4+C3 +0.0021 (AARD 0.99 % to
    0.68 % on a fixed set of 22); provisional butanes +0.0121 (iC4) and +0.0098
    (nC4). A constant kij does not reduce the ambiguous dew states. Published
    PR kij values could not be verified from the web session.
  - Next: P7/P8 follow-ups (stale numbers, survey rerun), plain-language
    solver codes, the owner-approved optional kij input (Option 2), Lab 4.

- **2026-11-02, web (CI: run the full suite in parallel):**
  - Done: the "Full test suite" step runs `pytest -n auto --dist loadfile`
    (pytest-xdist added to the dev group, `uv.lock` updated). After P7/P8 the
    serial suite took about 15.5 min of its 20-min step on master, and the kij
    study PR timed out at 84 %. Same tests, same gates, same timeout.
  - Open: PRs #28, #30, #31 and #32 merge master in after this.
  - Next: finish the kij study PR, then the chain.

- **2026-11-01, desktop (engine P7 + P8, owner-approved):**
  - Done: `saturation_pressure.py` runs the boundary walk when the grid finds
    no root (P7) and, where a walk stops at a failed step, checks the rest of
    the interval with a bounded Newton solve that may only make a result
    ambiguous, never supply its pressure (P8). Module 17 artifacts, the
    Newton comparison and the P3 study regenerated; Lab 2 and the validation
    write-up updated. The Newton comparison now also treats states the
    default solver calls ambiguous as multi-root.
  - Parallel: the web session's kij study (PR #28) must merge master and
    rerun on the new engine.
  - Next: release v1.6 (owner approval); then the butanes decision.

- **2026-11-01, desktop (new components proposal):**
  - Done: `docs/NEW_COMPONENTS_PROPOSAL.md`. The May (2015) ThermoML record
    already holds CH4+isobutane (17 states) and CH4+n-butane (19 states); a PR
    preview at kij = 0 gives bubble AARD 3.45 % and 3.51 % (bias about -3.5 %)
    with provisional CoolProp critical constants. Two solver findings, proposed
    as P7 (refine boundaries when the scan finds no root: recovers all 9
    `not_found` bubble states of the current record) and P8 (the P2 walk stops
    one step short: one butane dew result is the wrong root of two). An
    independent audit finds the same in the published record: CH4+C2 dew 009
    and 013 have a second PR root (013: reported -25.8 %, other root -1.4 %).
  - Parallel: the web session runs the kij study (P6) on branch `kij-study`.
  - Next: owner decisions in section 7 of the proposal; read the butane values
    in Yang & Richter (2025) Table 5.

- **2026-10-31, desktop (release v1.5.0):**
  - Done: the owner approved v1.5. This PR bumps the version to 1.5.0. After it
    merges and master CI passes, the desktop session publishes the release
    (tag `v1.5.0`) and the owner reboots the Streamlit app.
  - Next: choose the next large step from `## Suggested next steps` (new
    components, kij, volume translation) or the faculty review.

- **2026-10-31, desktop (Validation page):**
  - Done: the Validation page has a "Further evidence" section with three tabs,
    each read from committed results with no calculation at page load:
    - dew conditioning (P3);
    - Newton refinement (P4);
    - pure components (V2-01-E).

    Checked visually in the local app; tests cover the summaries and the page.
  - Next: release v1.5 (owner approval), then the owner reboots the app.

- **2026-10-30, desktop (P3):**
  - Done: the dew conditioning study now covers CH4+C2 and CH4+C3 and survives
    isolated bubble-solve failures (grid of converged solves, interpolation
    fallback recorded per state). CH4+C3 values reproduce the earlier study to
    1e-8. CH4+C2: 15 of 15 assessable states within 1 U, 2 states above the
    converged isotherm.
  - Next: the Validation page "Further evidence" tabs (branch
    `validation-page`), then release v1.5.

- **2026-10-30, desktop (P2):**
  - Done: applied P2 in `saturation_pressure.py` as a stepwise walk from each
    converged node beside a failed one. Nine dew states became ambiguous. The
    ninth, CH4+C2 010, has a second root the Module 17 scan had missed. All nine
    second roots are confirmed by `tools/run_hidden_dew_root_check.py`.
    Regenerated the Module 17 artifacts and the Newton comparison, and updated
    the pinned values with explanations. Labs 2 and 3 quote no dew values and
    are unaffected.
  - Next: P3 (conditioning-aware dew metric for both binaries), then the
    Validation page "Further evidence" tabs (branch `validation-page`).

- **2026-10-30, web (Lab 3):**
  - Done: teaching Lab 3 (methane-propane 30/70, 50/50 and 70/30: envelope
    landmarks, certified critical points, trends with composition, and oil
    versus gas-condensate behaviour at 300 K), in PR #22. No fixed-temperature
    dew pressures are quoted (P2). Every key number is recomputed by
    `tests/test_teaching_lab_03.py`.
  - Open: PR #22 awaits CI. The desktop session is working on P2, P3 and the
    Validation page; if P2 changes bubble or critical results, the lab tests
    will flag the key.
  - Next: the desktop session continues with P2, then P3 and the Validation
    page.

- **2026-10-30, web (Lab 2):**
  - Done: teaching Lab 2 (methane-ethane at 243.6 K: bubble pressures, a P-x-y
    diagram from flash results, comparison with the May 2015 bubble data and the
    protected validation record), in PR #21. No dew pressures are quoted (P2).
    Every key number is recomputed by `tests/test_teaching_lab_02.py`.
  - Merged in PR #21 after CI passed. Lab 3 (composition effects on the
    methane-propane envelope) is in PR #22. If P2 changes bubble results, the
    lab tests will flag the key.
  - Next: Lab 3.

- **2026-10-30, desktop (pure-component data):**
  - Done: the owner dropped the wait for faculty review and approved P2, P3 and
    the pure-component reference data, each with the best-science option.
    Accepted the CoolProp-evaluated reference EOS data (PR #10). Published the
    v1.4.0 release on master `9787226`, with code identical to `609a809`.
  - Next: P2 (refine hidden-root grid intervals and report several roots as
    inconclusive), then P3 (conditioning-aware dew metric), then show both and
    the pure-component check on the Validation page.

- **2026-10-30, web (release v1.4.0):**
  - Done: the owner approved release v1.4. PRs #15 (P1), #16 (P5), #18 (P4
    report) and #17 (survey docs) are merged, each after CI passed. PR #19 bumps
    the version to 1.4.0 and describes the public deployment as v1.4 once it is
    rebooted.
  - PR #19 merged as commit 609a809 and master CI passed on it. The web session
    could not push the tag: the git proxy returned HTTP 403 for `v1.4.0`, while
    branch pushes work.
  - Open: the desktop session creates the tag `v1.4.0` on commit 609a809 (not on
    the current master head) and publishes the GitHub release. The notes are in
    the web session's last message. The owner then reboots the Streamlit app.
    Draft PR #10 awaits the faculty review. P2, P3 and the pure-component data
    stay on hold.
  - Next: send the faculty brief and act on the answers.

- **2026-10-30, web (survey):**
  - Done: re-ran the extended-envelope survey with the current code and added
    `tools/run_envelope_survey.py`. The old "10 closed, 6 early" case list was not
    kept, so the new list is a stated reconstruction. Before P1 it closes 9 and
    stops early in 7. Now it closes 13 and stops early in 3 (a warm-start bubble
    initialization failure and two trivial-state stops). Updated
    `docs/STREAMLIT_APPLICATION.md` and marked decision 1 done here and in
    `docs/DEW_INVESTIGATION.md`. Moved P1 and P5 to a "Decided" table.
  - Open: draft PR #10 awaits the faculty review. P2, P3 and the
    pure-component data are on hold until then.
  - Next: release v1.4.0 once this PR is merged and master CI is green.

- **2026-10-30, web (P4):**
  - Done: P4 option B. `tools/run_validation_newton_comparison.py` runs the Module
    17 data with and without Newton refinement and writes
    `docs/investigations/validation_newton_comparison.md`, in PR #18. The frozen
    artifacts are not regenerated, and the default run is checked against them.
    Newton solves 4 more CH4+C2 and 3 more CH4+C3 bubble states. Its extra dew
    results are labelled one root of several and left out of accuracy (P2, on
    hold). State CH4+C3 023 converges to different roots in the two runs.
  - Merged in PR #18 after CI passed. Draft PR #10 awaits the faculty review.
  - Next: merge the survey docs (PR #17), then release v1.4.0.

- **2026-10-30, web (P5):**
  - Done: the owner approved P5. The app now labels the standard dew stop marker
    "Dew branch stopped (engine near-critical guard)", in PR #16. Application
    layer only; the engine's own label in `plotting.py` is unchanged because the
    approval did not name that file.
  - Open: PR #16 awaits CI. P2, P3 and the pure-component data are on hold
    until the faculty review. P4 (option B) is queued.
  - Next: P4 option B as a separate PR.

- **2026-10-30, web (P1):**
  - Done: the owner approved P1. Implemented root-count-tolerant continuity in
    `pseudo_arclength.py` only, with the 25% jump guard and the proposal's
    tests, in PR #15. The 50/50 methane/propane dew branch now reaches
    322.52 K / 8.472 MPa. One existing test changed its example input, because
    P1 closes the case it used.
  - Merged in PR #15 after CI passed and an independent review. The review
    found three vacuous rejection tests, which were rewritten before merge.
  - Open: draft PR #10 awaits the faculty review. P2, P3 and the
    pure-component data are on hold until then.
  - Next: P5 (PR #16), then P4 option B.

- **2026-10-30, desktop:**
  - Done: added `CLAUDE.md` with the project rules, the two-account workflow
    and token-saving defaults that sessions follow without being asked.
  - Open: draft PR #10 (pure-component reference data) awaits an owner
    decision.
  - Next: the owner decides on engine proposals P1–P5 and PR #10; send the
    faculty brief.
