# Project status

Last updated: 30 October 2026 (release v1.4.0).

This page brings together what OpenPhase does today, what supports it, and what
waits on a decision. Details live in the linked documents.

## What exists

**Scientific engine (Modules 1–21, frozen).**

- Peng–Robinson EOS with classical mixing and kij = 0, for verified methane,
  ethane and propane.
- Tangent-plane-distance stability and two-phase flash.
- Bubble and dew pressures with an optional Newton refinement.
- P–T envelope tracing with natural and pseudo-arclength continuation.
- Mixture criticality derivatives and a critical-point solver that requires
  both Gibbs conditions.
- Scientific plotting.

**Validation framework (V2-01-A to D).**

- Typed records, provenance and serialization.
- Generalized metrics that keep model accuracy separate from software
  correctness.
- A reproducible evidence report over the protected Module 17 data (May et al.,
  2015; CH4+C2 and CH4+C3).

**Application (public on Streamlit Community Cloud).**

- Flash, phase envelope with the extended display overlay, critical point,
  engineering sweeps, validation and diagnostics pages.
- Field units, save and load of cases, an engineering report, and exports.
- Learn mode, with explanations and exercises that are checked against the
  engine.

**Teaching.** [Lab 1](teaching/LAB_01_METHANE_PROPANE.md), with an instructor
key whose numbers are recomputed from the engine by the tests.

## Evidence

- About 1,000 test functions (about 1,500 test cases with parameters). CI runs
  lint, types, the full suite, a real-browser smoke test and a health check on
  every push.
- Experimental bubble pressures:
  - CH4+C2: 0.45 % AARD;
  - CH4+C3: 1.03 % AARD.
- Certified critical point of 50/50 methane/propane: 321.58 K, 8.534 MPa.
- [Dew investigation](DEW_INVESTIGATION.md): the large CH4+C3 dew-pressure
  error comes mostly from an ill-posed question and from hidden second roots,
  not from model error.

## Decided

| Item | Outcome |
|---|---|
| P1: root-count-tolerant continuation | Done, PR #15. The extended-envelope survey now closes 13 of 16 cases (9 before). The 3 that still stop early have other causes. |
| P5: neutral dew stop marker label | Done, PR #16, in the app layer. The engine's own label is unchanged. |
| P4: Newton refinement in validation | Option B, done in PR #18: both runs are reported side by side in `docs/investigations/validation_newton_comparison.md`. The frozen artifacts are unchanged. Newton's extra dew results at multi-root states are labelled one root of several, not accuracy. |

## Waiting on an owner decision

| Item | Where | Effect |
|---|---|---|
| P2: refine grid boundaries in the saturation scan | [proposals](ENGINE_CHANGE_PROPOSALS.md) | Stops 8 known hidden-second-root results from being reported as unique; changes the Module 17 artifacts |
| P3: conditioning-aware dew metric | [proposals](ENGINE_CHANGE_PROPOSALS.md) | Honest dew accuracy reporting |
| Pure-component reference data (V2-01-E) | draft PR, `docs/PURE_COMPONENT_SATURATION.md` | Accept CoolProp-evaluated reference EOS values as a source |
| Faculty review | review brief (private artifact) | Six scientific questions for a reviewer |

## Not implemented (by design, for now)

- Three-phase or multiphase flash.
- Volume translation. Liquid densities are not quantitative.
- Components beyond C1–C3.
- kij other than zero.
- More than one experimental source.

## Suggested next steps, in order

1. P1 and P5 are done. P2, P3 and the pure-component data source are on hold
   until the faculty review; each engine change then lands on its own branch
   with the tests named in the proposal and an independent review.
2. Send the faculty brief and act on the answers, especially on kij and on
   which components and datasets come next.
3. Add CO2 and N2, or the butanes, with verified properties and at least one
   experimental dataset each.
4. Consider Péneloux volume translation as a new engine module.

## Session log

Newest first. One short entry per task, written by whichever account did the
work and added in that task's PR. Sessions read only the latest few entries.

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
