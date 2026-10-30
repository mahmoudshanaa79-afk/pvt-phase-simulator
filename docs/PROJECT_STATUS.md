# Project status

Last updated: 19 October 2026 (release v1.3.0).

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

## Waiting on an owner decision

| Item | Where | Effect |
|---|---|---|
| P1: root-count-tolerant continuation | [proposals](ENGINE_CHANGE_PROPOSALS.md) | Closes every early-stopped envelope branch surveyed |
| P2: refine grid boundaries in the saturation scan | [proposals](ENGINE_CHANGE_PROPOSALS.md) | Stops 8 known hidden-second-root results from being reported as unique; changes the Module 17 artifacts |
| P3: conditioning-aware dew metric | [proposals](ENGINE_CHANGE_PROPOSALS.md) | Honest dew accuracy reporting |
| P4: Newton refinement in validation | [proposals](ENGINE_CHANGE_PROPOSALS.md) | Three more CH4+C3 bubble states solved |
| P5: neutral dew stop marker label | [proposals](ENGINE_CHANGE_PROPOSALS.md) | Avoids implying a critical point at the cricondentherm |
| Pure-component reference data (V2-01-E) | draft PR, `docs/PURE_COMPONENT_SATURATION.md` | Accept CoolProp-evaluated reference EOS values as a source |
| Faculty review | review brief (private artifact) | Six scientific questions for a reviewer |

## Not implemented (by design, for now)

- Three-phase or multiphase flash.
- Volume translation. Liquid densities are not quantitative.
- Components beyond C1–C3.
- kij other than zero.
- More than one experimental source.

## Suggested next steps, in order

1. Decide P1–P5 and the pure-component data source. Each engine change then
   lands on its own branch with the tests named in the proposal and an
   independent review.
2. Send the faculty brief and act on the answers, especially on kij and on
   which components and datasets come next.
3. Add CO2 and N2, or the butanes, with verified properties and at least one
   experimental dataset each.
4. Consider Péneloux volume translation as a new engine module.

## Session log

Newest first. One short entry per session, written by whichever account did the
work.

- **2026-10-30, desktop:**
  - Done: added `CLAUDE.md` with the project rules and this two-account
    workflow.
  - Open: draft PR #10 (pure-component reference data) awaits an owner
    decision.
  - Next: the owner decides on engine proposals P1–P5 and PR #10; send the
    faculty brief.
