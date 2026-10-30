# Lab 3: How composition moves the phase envelope

**Tool:** OpenPhase (Peng–Robinson EOS, kij = 0), live app or a local copy.
**Fluids:** methane–propane at 30 / 70, 50 / 50 and 70 / 30 mol %.
**Time:** about 75 minutes.
**Prerequisites:** Lab 1, and the idea of bubble-point and dew-point reservoir
fluids from an introductory reservoir-fluids course.

Switch on **Learn mode** in the sidebar for short explanations on each page.

## Learning outcomes

By the end of the lab you should be able to:

1. Read the cricondenbar, cricondentherm and critical point of a mixture from
   the extended envelope and the critical solver.
2. Describe how those three landmarks move as a mixture gets richer in the
   light component.
3. Use the position of the critical point to predict whether a fluid behaves
   like an oil or like a gas condensate at a given temperature.
4. Check that prediction with a pressure sweep.

## Part A: Three envelopes

Use these inputs. The operating temperature sets where the app starts tracing
the envelope, so use the value given for each mixture.

| Mixture (C1 / C2 / C3 mol %) | Operating temperature | Pressure |
|---|---|---|
| 30 / 0 / 70 | 310 K | 5 MPa |
| 50 / 0 / 50 | 300 K | 5 MPa |
| 70 / 0 / 30 | 260 K | 5 MPa |

1. For each mixture, enter the inputs, press **RUN FLASH**, open **Phase
   Envelope** and press **RUN PHASE ENVELOPE**.
2. From the extended (dotted) curves, read the cricondenbar (highest pressure)
   and the cricondentherm (highest temperature), each with its matching
   temperature or pressure. Note which branch, bubble or dew, each lies on.
3. Note where the two extended branches end, and the reason the page gives.
4. Optional: repeat the 70 / 30 mixture with an operating temperature of
   270 K. What happens to the bubble branch, and how does the page report it?

## Part B: Three critical points

1. For each mixture, set the temperature and pressure to a rounded point near
   where the extended branches end. Suggested seeds: 345 K and 6.7 MPa for
   30 / 70, 320 K and 8.5 MPa for 50 / 50, and 283 K and 9.9 MPa for 70 / 30.
2. Press **RUN FLASH**, open **Critical Point** and press **RUN CRITICAL
   SOLVER**. Record the critical temperature and pressure, and check that the
   result is certified.
3. Try a different seed a few kelvin and a few tenths of a megapascal away.
   Does the answer change?

## Part C: Trends

1. Fill in the table.

| Mixture | Critical T (K) | Critical P (MPa) | Cricondentherm (K) | Cricondenbar (MPa) | Cricondentherm − critical T (K) |
|---|---|---|---|---|---|
| 30 / 70 | | | | | |
| 50 / 50 | | | | | |
| 70 / 30 | | | | | |

2. How do the critical temperature and pressure change as methane increases?
3. Is the critical point to the right of the cricondenbar (closer to the
   cricondentherm) or to the left? How does that change with composition?
4. Between the critical temperature and the cricondentherm, a fluid can show
   retrograde condensation. How does the width of that window change?

## Part D: Oil or gas condensate at 300 K?

Take 300 K as a reservoir temperature, and imagine the pressure falling from
10 MPa during production.

1. Using only your Part B and Part C results, predict for each mixture whether
   the fluid first meets a bubble point (oil-like) or a dew point (gas
   condensate).
2. Check: for each mixture at 300 K, run a pressure sweep from 1 to 10 MPa with
   37 points (0.25 MPa steps). Record the liquid mole fraction, 1 − β, at 3, 5
   and 7 MPa (write "single phase" where there is one phase).

| Mixture | 3 MPa | 5 MPa | 7 MPa |
|---|---|---|---|
| 30 / 70 | | | |
| 50 / 50 | | | |
| 70 / 30 | | | |

3. For 30 / 70 and 50 / 50, find the highest pressure that is still
   two-phase. What kind of saturation point is it?
4. For 70 / 30, find the largest liquid fraction in your sweep and its
   pressure. What happens to the liquid as the pressure keeps falling?

## Part E: Discussion

1. Real reservoir oils and condensates contain many heavier components. Which
   of your conclusions would carry over, and which would not?
2. For 70 / 30 the highest-pressure point of the trace sits almost on the
   critical point. Why does the trace resolution matter there?
3. This lab quotes no dew pressures at fixed temperature. Using Lab 2 Part E,
   explain why a single dew pressure can be ill-posed.

---

## Instructor answer key

All values are from the unchanged engine for methane–propane, kij = 0.
`tests/test_teaching_lab_03.py` checks them, so this key stays consistent with
the model. Envelope landmarks are read from the app's extended envelope at the
operating temperatures in Part A; the trace is a set of discrete points, so
student readings can differ slightly in the last digit.

**Part A.**

- 30 / 70: the cricondenbar is about 6.86 MPa, at about 340.5 K, on the bubble
  branch. The cricondentherm is about 348.5 K, at about 6.13 MPa, on the dew
  branch.
- 50 / 50: the cricondenbar is about 8.81 MPa, at about 311.4 K, on the bubble
  branch. The cricondentherm is about 329.1 K, at about 6.78 MPa, on the dew
  branch. These match Lab 1.
- 70 / 30: the cricondenbar is about 9.95 MPa, at about 280.9 K, at the end of
  the bubble branch. The cricondentherm is about 302.2 K, at about 7.08 MPa, on
  the dew branch.
- In all three cases both branches end at the engine's near-critical guard.
  That is not a certified critical point; Part B finds it.
- Optional step: at 270 K the 70 / 30 bubble branch stops early with the
  reason *trivial_state*, and the page says the envelope is not closed. The
  dew branch still reaches the near-critical guard.

**Part B.**

| Mixture | Critical T (K) | Critical P (MPa) |
|---|---|---|
| 30 / 70 | 346.36 | 6.644 |
| 50 / 50 | 321.58 | 8.534 |
| 70 / 30 | 283.09 | 9.943 |

- All three are certified: both critical conditions converged and passed a
  fresh check.
- Seeds a few kelvin and a few tenths of a megapascal away (for example 340 K
  and 6.5 MPa, 315 K and 8.0 MPa, 280 K and 9.5 MPa) give the same answers.

**Part C.**

| Mixture | Critical T (K) | Critical P (MPa) | Cricondentherm (K) | Cricondenbar (MPa) | Cricondentherm − critical T (K) |
|---|---|---|---|---|---|
| 30 / 70 | 346.36 | 6.644 | 348.5 | 6.86 | 2.1 |
| 50 / 50 | 321.58 | 8.534 | 329.1 | 8.81 | 7.5 |
| 70 / 30 | 283.09 | 9.943 | 302.2 | 9.95 | 19.1 |

- As methane increases from 30 to 70 mol %, the critical temperature falls by
  about 63 K and the critical pressure rises by about 3.3 MPa. The mixture
  critical pressures are well above both pure-component critical pressures
  (methane 4.60 MPa, propane 4.25 MPa): a binary's critical locus is not a
  straight line between its components.
- For 30 / 70 the critical point lies to the right of the cricondenbar, close
  to the cricondentherm. For 50 / 50 it lies between the two. For 70 / 30 it
  sits at the cricondenbar, far to the left of the cricondentherm.
- The retrograde window widens from about 2 K to about 19 K. Lean, light-rich
  fluids have a wide range of temperatures where liquid condenses as pressure
  falls.

**Part D.**

- Prediction: at 300 K, both 30 / 70 and 50 / 50 are below their critical
  temperatures, so on the way down they meet the bubble curve: oil-like,
  bubble-point fluids. 70 / 30 is between its critical temperature (283.09 K)
  and its cricondentherm (302.2 K), so it meets the dew curve: a retrograde
  gas condensate.

| Mixture | 3 MPa | 5 MPa | 7 MPa |
|---|---|---|---|
| 30 / 70 | 0.620 | 0.891 | single phase |
| 50 / 50 | 0.178 | 0.430 | 0.639 |
| 70 / 30 | single phase | single phase | 0.039 |

- 30 / 70: the highest two-phase pressure in the sweep is 5.75 MPa. The
  bubble point is 5.759 MPa, and just below it the fluid is almost all liquid.
- 50 / 50: the bubble point is about 8.67 MPa (Lab 1 Part C). The sweep is
  single phase at 8.75 MPa and above, and every sweep point from 3 to 8.5 MPa is
  two-phase.
- 70 / 30: the liquid fraction peaks at about 0.041 (4.1 mol %) at 7.25 MPa
  in the sweep. As pressure falls further the liquid re-vaporizes, and at 5 MPa
  the fluid is single phase again. That is retrograde condensation: liquid
  forms as pressure falls, then disappears.
- The two oil-like mixtures carry far more liquid than the condensate. At
  5 MPa the 30 / 70 mixture is 89 % liquid and the 50 / 50 mixture 43 %; the
  70 / 30 condensate never exceeds about 4 %.

**Part E.**

- The qualitative picture carries over: adding light components lowers the
  critical temperature and moves the critical point to the left, widening the
  retrograde window, so richer gases behave as condensates and heavier mixtures
  as oils. The numbers do not carry over: real fluids with heavy ends have much
  higher critical temperatures and cricondentherms, and need more components,
  fitted kij values and usually volume translation.
- For 70 / 30 the critical point and the cricondenbar almost coincide
  (9.943 MPa and about 9.95 MPa). The trace is a set of discrete points close
  to that region, so whether the highest trace point lies just above or just
  below the critical pressure depends on where the points fall. The certified
  critical solver, not the trace, gives the critical point.
- Near the maximum of the vapour composition on an isotherm, the dew pressure
  is extremely sensitive to the vapour composition, and two dew pressures can
  share one composition (`docs/DEW_INVESTIGATION.md`). This lab therefore uses
  the envelope trace, the critical solver, bubble points and flash results.
