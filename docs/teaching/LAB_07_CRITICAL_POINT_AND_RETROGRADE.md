# Lab 7: The critical point, the envelope and retrograde condensation (methane + propane)

**Tool:** OpenPhase (Peng–Robinson EOS), live app or a local copy.
**Fluid:** 50/50 methane–propane.
**Time:** about 60 minutes.
**Prerequisites:** Labs 1, 3 and 6.

Switch on **Learn mode** in the sidebar for short explanations on each page.

## Learning outcomes

By the end of the lab you should be able to:

1. Say what makes a mixture critical point "certified" and why a seed is
   needed.
2. Locate the cricondenbar and cricondentherm on a phase envelope and place
   the critical point between them.
3. Show retrograde condensation along an isotherm between the critical
   temperature and the cricondentherm.
4. Recognise where the flash's near-critical stability test misses a
   two-phase state, and use the envelope to check it.

## Background

At a mixture critical point the two phases become identical. OpenPhase's
solver requires two conditions:
- the Gibbs energy loses its curvature in one composition direction;
- the cubic term along that direction also vanishes.

It starts from a seed (T, P) and reports a *certified* point only when both
residuals converge and pass a fresh check. Otherwise it reports the failure.

For a mixture, the critical point is generally **not** the highest pressure
(the *cricondenbar*) or the highest temperature (the *cricondentherm*) of the
envelope. Between the critical temperature and the cricondentherm, lowering
the pressure from above the dew curve first **condenses** liquid, then
re-vaporises it: retrograde condensation, the basis of gas-condensate
reservoir behaviour.

## Part A: The certified critical point

Choose the example *Audited critical-solver seed* (50/50, near 321.58 K and
8.534 MPa), press **RUN FLASH**, then on **Critical Point** press **RUN
CRITICAL SOLVER**.

1. Record the critical temperature, the critical pressure, the status, whether
   it is certified, the number of iterations and the termination reason.
2. Now enter 320 K and 8.5 MPa as the case (50/50), press **RUN FLASH**, then
   **RUN CRITICAL SOLVER** again. The submitted temperature and pressure are
   the solver's seed. Compare the result and the number of iterations.
3. Why does the solver need a seed, and why does it refuse to return an
   uncertified point?

## Part B: Cricondenbar and cricondentherm

Choose the default example (50/50, 300 K) and press **RUN PHASE ENVELOPE**.
Use the extended branches, which continue past the standard trace towards the
critical region.

1. Find the highest-pressure point (cricondenbar) and the highest-temperature
   point (cricondentherm). On which branch does each lie?
2. Order the critical temperature and the cricondentherm, and the critical
   pressure and the cricondenbar.

## Part C: Retrograde condensation at 327 K

327 K lies between the critical temperature and the cricondentherm. On the
extended dew branch, read the two dew pressures at 327 K (one high, one low).
Then run the flash at 327 K and these pressures (MPa): 7.70, 7.50, 7.25, 7.00,
6.50, 6.00, 5.80, 5.70.

1. Tabulate the liquid fraction (1 − vapour fraction) at each pressure.
2. As the pressure falls from the upper dew point, does liquid appear or
   disappear? Where is the liquid fraction largest?
3. Why does this matter for producing a gas-condensate reservoir?

## Part D: Where the stability test misses the two-phase state

Still at 327 K, run the flash at 7.85, 7.80 and 7.75 MPa.

1. Record the phase state, the stability status, whether both stability
   trials are trivial (Diagnostics → Show advanced raw public objects), and
   whether the Overview shows a note under the single-phase message.
2. Compare with the upper dew pressure from Part C. Are these states inside the
   envelope?
3. What should a user do with a near-critical "single phase" result? (See Lab 6
   Part D and engine proposal P12.)

---

## Instructor answer key

All values are from the unchanged engine with production defaults, through the
same calls the app makes. `tests/test_teaching_lab_07.py` recomputes every
number below.

**Part A.**

- From the audited seed: 321.58 K and 8.534 MPa. Status *converged*,
  certified, after 0 iterations: the seed already is the critical point.
- From the 320 K, 8.5 MPa seed: the same point, 321.58 K and 8.534 MPa,
  certified after 3 iterations.
- Termination reason, verbatim: "both signed critical residuals converged and
  passed fresh certification".
- A mixture can have more than one solution of the two conditions, and Newton's
  method needs a nearby start. An uncertified point might be a spinodal (first
  condition only) or an unconverged iterate, so reporting it as critical would
  mislead.

**Part B** (extended envelope, operating temperature 300 K).

| Landmark | T (K) | P (MPa) | Branch |
|---|---:|---:|---|
| Cricondenbar | 311.43 | 8.809 | bubble |
| Critical point | 321.58 | 8.534 | – |
| Cricondentherm | 329.10 | 6.782 | dew |

- 311.43 K < T_c = 321.58 K < cricondentherm = 329.10 K.
- P_c = 8.534 MPa < cricondenbar = 8.809 MPa.
- The critical point sits on the envelope between the two landmarks, where the
  bubble and dew branches meet.

**Part C** (327 K). Dew pressures from the extended dew branch: 7.904 MPa
(upper) and 5.758 MPa (lower).

| P (MPa) | Phase state | Liquid fraction |
|---:|---|---:|
| 7.70 | two phase | 0.0818 |
| 7.50 | two phase | 0.0999 |
| 7.25 | two phase | 0.1034 |
| 7.00 | two phase | 0.0969 |
| 6.50 | two phase | 0.0684 |
| 6.00 | two phase | 0.0262 |
| 5.80 | two phase | 0.0058 |
| 5.70 | single phase | – |

- Below the upper dew point, lowering the pressure **creates** liquid. The
  liquid fraction peaks at about 0.10 near 7.25 MPa, then falls back to zero
  near the lower dew point (5.758 MPa). The flash at 5.70 MPa is single
  phase, consistent with the envelope.
- In a gas-condensate reservoir the pressure falls during production. The
  liquid that condenses in the rock is mostly immobile, so valuable heavier
  components are left behind. That is why such reservoirs are often kept
  above the dew point, for example by gas cycling.

**Part D** (327 K).

| P (MPa) | Phase state | Stability | Both trials trivial | Note on Overview |
|---:|---|---|---|---|
| 7.85 | single phase | stable | yes | yes |
| 7.80 | single phase | stable | yes | yes |
| 7.75 | single phase | stable | yes | yes |

- All three pressures are below the upper dew pressure (7.904 MPa) and above
  the lower one, so these states are **inside** the envelope and should be
  two-phase.
- The flash calls them single phase because both stability trials returned the
  trivial solution: the test found no instability, it did not prove
  stability. This is the same near-critical limitation as Lab 6 Part D
  (proposal P12). The Overview's note (diagnostic
  `STABILITY_TRIVIAL_TRIALS_ONLY`) says exactly this; the verdict itself is
  unchanged.
- A user should treat a near-critical "single phase" result with caution,
  check it against the phase envelope, and note that the liquid fraction just
  inside the dew curve is small anyway (0.0818 at 7.70 MPa).
