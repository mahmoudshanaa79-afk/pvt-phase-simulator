# Engine change proposals

Status: **proposed, not applied.** The scientific engine (`src/pvt_phase_simulator`),
data and protected validation artifacts are frozen. Each proposal below needs an
explicit owner decision before it is implemented, and should then land on its own
branch with the tests listed, a full CI run, and an independent review.

Evidence comes from `docs/DEW_INVESTIGATION.md` and the read-only tools
`tools/run_dew_conditioning_study.py` and `tools/run_root_count_whatif.py`.

---

## P1. Accept a cubic root-count change in pseudo-arclength continuity

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
