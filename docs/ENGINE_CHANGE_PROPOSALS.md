# Engine change proposals

Status: **proposed, not applied.** The scientific engine (`src/pvt_phase_simulator`),
data and protected validation artifacts are frozen. Each proposal below needs an
explicit owner decision before it is implemented, and should then land on its own
branch with the tests listed, a full CI run, and an independent review.

Evidence comes from `docs/DEW_INVESTIGATION.md` and the read-only tools
`tools/run_dew_conditioning_study.py` and `tools/run_root_count_whatif.py`.

---

## P1. Accept a cubic root-count change in pseudo-arclength continuity

**Status: approved by the owner on 2026-10-30 and implemented in PR #15.**

**Problem.** `trace_pseudo_arclength_branch` rejects a step when
`_root_branch_is_continuous` fails, and that shared rule requires the number of
real cubic roots to be unchanged. Along a saturation curve, one phase's cubic
can lose its two other roots while the selected root moves smoothly. The branch
then ends with `phase_role_lost`, and the step is not retried.

**Evidence.**

- Default 50/50 C1/C3 dew branch started at 270 K: it stops at 292.2 K. The
  incipient liquid's roots go from `[0.0637, 0.3505, 0.5443]` to `[0.0690]`.
  With the rule relaxed, the branch reaches 322.5 K / 8.47 MPa, close to the
  certified critical point (321.58 K, 8.534 MPa). All 17 new points agree with
  independent fixed-temperature solves to a relative 5×10⁻⁹.
- 10-mixture survey: all 7 `phase_role_lost` branches close. Fixed-temperature
  solves agree wherever they converge.

**Proposed change** (pseudo-arclength only; the shared rule and the Newton
saturation solver are untouched):

```python
ROOT_COUNT_CHANGE_MAXIMUM_RELATIVE_JUMP: Final = 0.25


def _arclength_root_is_continuous(
    previous: FlashPhaseResult, current: FlashPhaseResult
) -> bool:
    if _root_branch_is_continuous(previous, current):
        return True
    if previous.trial_kind is not current.trial_kind:
        return False
    if len(previous.root_selection.candidates) == len(
        current.root_selection.candidates
    ):
        return False  # same topology: the shared rejection stands
    stable = tuple(
        candidate.compressibility_factor
        for candidate in current.root_selection.candidates
        if candidate.classification is MechanicalStabilityClassification.STABLE
    )
    if not stable:
        return False
    previous_z = previous.selected_compressibility_factor
    current_z = current.selected_compressibility_factor
    tolerance = 1e-8 * max(1.0, abs(previous_z), abs(current_z))
    distances = sorted(abs(value - previous_z) for value in stable)
    if len(distances) > 1 and abs(distances[1] - distances[0]) <= tolerance:
        return False
    nearest = min(stable, key=lambda value: abs(value - previous_z))
    if abs(nearest - current_z) > tolerance:
        return False
    return abs(current_z - previous_z) <= (
        ROOT_COUNT_CHANGE_MAXIMUM_RELATIVE_JUMP * abs(previous_z)
    )
```

Both calls at the continuity check in `trace_pseudo_arclength_branch` would use
`_arclength_root_is_continuous`.

**Why the jump guard.** If the *selected* root itself vanishes, the nearest
remaining stable root belongs to the other phase (for example a liquid Z of 0.06
whose only remaining root is 0.5). That is a phase switch, not continuation. The
25% bound rejects it. The observed legitimate change was 8%. The phase-role,
near-critical and trivial-state gates still run afterwards.

**Tests to add.**

- The default dew branch from 270 K reaches `near_critical` within 3 K / 0.2 MPa
  of the certified critical point.
- Every point agrees with a fixed-temperature solve to 1e-6 wherever one exists.
- The C2/C3 30/70 and 70/30 bubble and dew branches close.
- Synthetic phase results show three things:
  - a 3→1 root change with an 8% jump is accepted;
  - a 3→1 change onto the other phase's root is rejected;
  - an equal-count discontinuity is still rejected.

**Effect on the app.** More extended branches close. The app's multi-start dew
logic could then be simplified, but not before the change is reviewed.

---

## P2. Do not report a unique dew pressure when a second root is hidden

**Status: applied on 30 October 2026** with the owner's approval (best-science
option: report the state as ambiguous). It is implemented as a stepwise walk
from the converged node, which stops at the first failed evaluation, rather
than a dense 41-point scan. It changed nine dew results, not eight. The ninth,
CH4+C2 010, has a second root at 6.6076 MPa that the Module 17 diagnostic scan
had also missed. The Module 17 artifacts were regenerated; see
`docs/EXPERIMENTAL_VALIDATION.md`.

**Problem.** The production fixed-temperature solver scans an 81-point log grid
from 1 kPa to 100 MPa. It counts sign changes only between nodes where the inner
iteration converged. When the second root lies next to a non-converged node, it
is invisible, and the solver reports `converged` with one root.

**Evidence.** Production reported a single converged dew pressure at eight
states where the Module 17 scan shows a second root:

- six CH4+C3 states: 001, 003, 004, 014, 015 and 023;
- two CH4+C2 states: 012 and 015.

In every case the second root lies in the interval between the last converged
grid node and the first non-converged one (for example CH4+C3 014: nodes 7.50
and 8.66 MPa, root 7.773 MPa). A dense local search inside exactly that interval
(public API, 41 points) found the missed root in **all eight** cases, matching
the scan to every printed digit. Reproduce with
`tools/run_hidden_dew_root_check.py`. The six CH4+C3 results cause most of the
36.7% production dew AARD (for example −63% and −69%).

**Proposed change.** After the global scan, refine each interval that has one
converged and one non-converged end with a local scan of the same objective. Add
any converged sign change to the bracket count before the existing
multiple-root decision. The existing rule then reports these states as
`inconclusive` (multiple roots), which is the true answer.

**Consequences to decide.**

- CH4+C3 production dew successes fall from 7 to 1. The remaining success, 009,
  has an error of 2.8%. The headline dew AARD becomes uninformative (n = 1)
  rather than misleading.
- CH4+C2 dew successes fall from 15 to 13.
- This changes the frozen Module 17 artifacts.
- Cost: up to about 40 extra inner solves per boundary interval, only when such
  an interval exists. This needs timing on the envelope path.
- An alternative that changes no status: keep `converged`, but add a
  `UNIQUENESS_NOT_ESTABLISHED` diagnostic whenever a converged/non-converged
  boundary was not refined.

---

## P3. Report dew accuracy with a conditioning-aware metric

**Status: applied on 30 October 2026** for both binaries, as an evidence table
(`docs/investigations/dew_conditioning.csv`) shown on the Validation page. The
frozen Module 17 metric definitions are unchanged.

**Problem.** Near the maximum of PR's vapour composition on an isotherm,
`dP/dy → ∞`. At 15 of 23 CH4+C3 states, the stated composition uncertainty alone
allows more than 1 MPa of dew pressure. A dew-pressure error there says almost
nothing about the model.

**Proposal.** For each dew state, report alongside the existing dew-pressure
metrics:

- `dy = y_exp − y_PR(P_exp)`, PR's coexisting vapour composition at the measured
  pressure, normalised by the stated expanded uncertainty;
- the conditioning number `|dP/dy|·U_y`;
- a flag when that number exceeds the pressure uncertainty.

With this metric, PR agrees within 1 U at 22 of 23 states and within 2 U at 23
of 23. `tools/run_dew_conditioning_study.py` already computes it. Production use
means a new validation module and new report rows. This changes how frozen
Module 17 results are summarised, so it needs the same review gate.

---

## P4. Run validation with the engine's Newton saturation refinement

**Status: option B approved by the owner on 2026-10-30 and implemented in PR #18. The frozen artifacts are unchanged; the side-by-side report is `docs/investigations/validation_newton_comparison.md`.**

**Problem.** `experimental_validation.py` calls the saturation solver with
defaults, which leave Newton refinement off. Three near-critical CH4+C3 bubble
states (013–015) then fail with "No trustworthy saturation-pressure bracket".

**Evidence.** With `saturation_newton_enabled=True`, all three converge:

| State | PR bubble P | Measured P | Error |
|---|---:|---:|---:|
| 013 | 7.566 MPa | 7.530 MPa | +0.5% |
| 014 | 7.998 MPa | 7.943 MPa | +0.7% |
| 015 | 8.427 MPa | 8.320 MPa | +1.3% |

**Decision needed.**

- **Option A:** switch validation to the Newton option. This regenerates the
  frozen artifacts, and the bubble success count rises from 20 to 23.
- **Option B:** report both runs side by side, keeping the default run as the
  production record.

---

## P5. Neutral wording for the standard trace's dew stop marker

**Status: approved by the owner on 2026-10-30 and implemented in the application layer in PR #16. The engine's own label is unchanged.**

**Observation.** On the default case, the standard (natural-temperature) dew
branch stops near 329 K / 6.7 MPa, at the cricondentherm, not at the critical
point. The engine plot labels that marker "Dew Near-critical termination". Users
and students read this as "the critical point is here".

**Proposal.** Either the engine's near-critical guard should not fire at a pure
temperature turning point (needs investigation), or the plot label should say
what happened: "Dew branch stopped (engine near-critical guard)". A label change
could be done in the application layer, but the label belongs to the engine
plotting API, so it is listed here.

---

## P6. Non-zero binary interaction parameters (kij)

**Status: Option 2 approved by the owner on 2026-11-02; app input in Task 4
(PR #32). Study complete (PR #28).** kij = 0 stays the default and the
validation reference; the app offers an optional, labelled kij input.

**Question.** What does a non-zero kij do for Peng–Robinson on the May (2015)
data, and should OpenPhase use one? The engine already accepts kij; the study
changes no engine file and leaves the kij = 0 validation record as it is.

The evidence, the fitted values and the options are in
`docs/investigations/kij_study.md`.

## P7. Refine boundary intervals when the grid finds no root

**Status: applied on 1 November 2026** with the owner's approval.

**Finding.** The P2 walk ran only when the grid had already found exactly one
root. When it found none, a root beside a non-converged node stayed hidden and
the result was `not_found`. All nine `not_found` bubble states of the May
(2015) record are of this kind (`tools/run_empty_scan_whatif.py`,
`docs/investigations/empty_scan_whatif.csv`).

**Change.** Run the walk when the grid finds no root as well. One root found:
solve its bracket as usual (`BOUNDARY_SATURATION_ROOT`). More than one:
`INCONCLUSIVE`. None: `NOT_FOUND` as before.

**Effect.** CH4+C2 bubble 11 → 17 successes, CH4+C3 bubble 20 → 23. The
recovered pressures equal the independent Newton option's to 1e-8 where it
converges.

## P8. Check the rest of an interval when the walk stops at a failure

**Status: applied on 1 November 2026** with the owner's approval.

**Finding.** The walk stops at the first non-converged evaluation. Near a
critical point the inner iteration fails just before an upper dew root, so the
lower root was reported as unique. An independent audit
(`tools/run_dew_uniqueness_audit.py`) found this at CH4+C2 009 and 013; the
CH4+n-butane preview found it at state 008 (`docs/NEW_COMPONENTS_PROPOSAL.md`).

**Change.** When an interval's walk finds no sign change, a bounded local
Newton solve seeded with the last converged walk state looks for a root in the
rest of the interval. A converged, non-trivial root strictly inside the
interval counts as a root; it makes the result ambiguous and is never reported
as the pressure. See `docs/SATURATION_PRESSURE_DESIGN.md`.

**Effect.** CH4+C2 dew 008, 009, 013 and 017 become ambiguous (upper roots
6.88, 6.76, 6.80 and 6.67 MPa). CH4+C2 dew goes from 12 states at 5.34 % AARD
to 8 states at 2.07 %. The former worst result, 013 at −25.8 %, was the lower
of two roots; its upper root is 1.3 % from the measurement.


## P9. Validate component parameters once per evaluation, not per pair

**Status: applied on 8 November 2026** with the owner's approval of engine
speed-ups that keep every result byte-identical (approval A). Proposed on
3 November 2026.

**As applied.** Passing pre-validated values to private kernels would have
bypassed the single authoritative pair helper that existing tests require, so
the applied form keeps every call path and makes the repeated checks cheap
instead: a validation that already succeeded for the very same immutable
object is not repeated. Component rows and row tuples (frozen dataclasses) are
keyed by object identity plus temperature, with the object held so its id
cannot be reused; interaction mappings are reused only while they hold exactly
the same key and value objects; supplied cubic roots are keyed by the exact
bit patterns of (Z, A, B). Failures are never cached and the caches are
bounded. Every public entry point validates exactly as before.

**Identity.** `tools/engine_fingerprint.py` hashes the complete canonical form
of 801 results (all 40 May (2015) states in both directions, with and without
Newton and kij; synthetic binaries and ternaries; flash; stability; the app's
envelope, extended overlay, saturation pair, critical point and criticality
map). All 801 are byte-identical to master, and the full test suite, the golden
master and the Module 17 pins pass with no test edited.

**Effect.** Measured on one machine before and after (median of 3), the app's
first phase envelope takes 34.6 s instead of 82.1 s for the default example and
48.4 s instead of 106.9 s for the critical-solver seed (2.1 to 2.4 times
faster; `docs/investigations/app_performance.md`). The remaining time is the
cubic-root arithmetic itself.

The original proposal follows.

**Finding.** The phase-envelope action is the app's only slow action: about
125 s of engine time for the default example (179 s for the critical-solver
seed) against under 5 s for every other action
(`docs/investigations/app_performance.md`). A cProfile of the app's
`calculate_phase_envelope` call at 300 K shows where the time goes (cProfile
roughly triples wall time; the shares are what matter):

- every corrector step runs a full saturation solve: 49 solves, 1,548 pressure
  evaluations, 66,291 flash-phase evaluations and 67,725 mixture fugacity
  calculations;
- about half of the profile is repeated validation of the same three
  components' parameters: `_validate_single_component_parameter` 4.6 million
  calls (199 s cumulative of 410 s), `_require_derived_parameter` 31 million
  calls, `require_finite` 200 million calls and provenance validation
  (`validate_component_parameter_provenance`) 346,000 calls;
- `calculate_component_pair_attraction_parameter` alone is called 1.8 million
  times (206 s cumulative), mostly validating its inputs;
- the P2/P7/P8 boundary walk (`_boundary_roots`) is 66 % of the cumulative time,
  because every corrector solve runs it.

**Proposal.** Validate each mixture's component parameters and kij once per
evaluation (per temperature) and pass validated values to the pair and
fugacity kernels, instead of re-validating them inside every pair call. The
arithmetic and its order stay the same, so every result should be
bit-for-bit identical; the golden master and the Module 17 record would show
it. Expected saving: roughly half of the envelope time.

**Not proposed here.** Narrowing the corrector's saturation bracket from the
predictor would also cut time but can change which root is found, so it is a
scientific decision, not a speed-up.

**Measurement to repeat after a change.** `tools/profile_app.py` (before and
after tables) and the golden-master suite.


## P10. Faster envelope continuation that changes recorded results

**Status: proposed (web session, 8 November 2026). Awaiting owner decision.**
Nothing in the engine has been changed. Both options below change the result
objects, so they were outside the byte-identical speed-up (P9) and were measured
only on a scratch copy, by replacing the engine function or setting at run time.

**Measurement.** The app's `calculate_phase_envelope` call on six states (the
three shipped examples' 50/50 C1/C3 at 300 K and 321.58 K, 50/50 C1/C3 at 250 K,
50/50 C1/C2 at 250 K, 71.23/28.77 C1/C2 at 243.6 K, 40/30/30 at 250 K with
kij = 0.01), after P9, three variants run side by side on one machine:

| State | P9 (s) | (a) no boundary walk (s) | (b) no global fallback (s) |
|---|---:|---:|---:|
| 50/50 C1/C3, 300 K (default example) | 29.2 | 10.5 | 22.6 |
| 50/50 C1/C3, 321.58 K (critical seed) | 38.6 | 14.2 | 30.4 |
| 50/50 C1/C2, 250 K | 43.3 | 12.6 | 34.2 |
| 71.23/28.77 C1/C2, 243.6 K | 39.6 | 8.7 | 30.6 |
| 50/50 C1/C3, 250 K | 3.7 | 2.2 | 3.8 |
| 40/30/30, 250 K, kij = 0.01 | 3.1 | 2.0 | 3.3 |

**(a) Skip the P2/P7/P8 boundary walk inside the envelope's saturation
solves.** About three times faster, but it changes results and removes the
hidden-root safety net:

- 71.23/28.77 C1/C2 at 243.6 K: the bubble branch fails entirely
  (`corrector_failed`, 0 points instead of 10);
- 50/50 C1/C2 at 250 K: the bubble branch ends at `maximum_points` instead of
  `near_critical`, with 15 instead of 13 points; pressures differ by up to
  0.74 % and temperatures by up to 1.05 K;
- the critical-solver seed: the same 15 points (to 2e-14) but 6 rejected
  attempts instead of 0.

Not recommended.

**(b) Turn off the corrector's global fallback in the app's envelope settings
(`allow_global_fallback=False`).** About a quarter faster on the slow states. On
all six states every accepted envelope point, every termination reason and
every point count is identical; only the record of rejected corrector attempts
is shorter (for example 23 → 20 on the default example's dew branch), because
the failed full-range retries are no longer attempted. The plotted envelope and
everything the app shows from it would be unchanged, but the exported result
objects would differ, and states where the fallback rescues a step were not
found in this set but cannot be ruled out in general.

A reasonable path, if wanted: adopt (b) in the app only, after a wider survey
(for example the 16 cases of `tools/run_envelope_survey.py`) shows no lost
points.
