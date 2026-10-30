# Lab 2: Bubble pressures and the P–x–y diagram of methane–ethane

**Tool:** OpenPhase (Peng–Robinson EOS, kij = 0), live app or a local copy.
**Fluid:** methane–ethane binary (propane set to 0 mol %).
**Temperature:** 243.6 K (−29.55 °C), the main isotherm of the May et al. (2015)
data used on the **Validation** page.
**Time:** about 75 minutes.
**Prerequisites:** Lab 1, K-values, and binary phase diagrams at the level of an
introductory reservoir-fluids course.

Switch on **Learn mode** in the sidebar for short explanations on each page.

## Learning outcomes

By the end of the lab you should be able to:

1. Find a bubble pressure from a pressure sweep and explain what it means.
2. Build a P–x–y diagram of a binary from flash results and explain its shape.
3. Explain how K-values change with pressure and why they approach 1.
4. Compare model bubble pressures with measurements, and say where and why the
   agreement gets worse.

## Part A: One flash at 243.6 K and 4 MPa

1. Enter 50 / 50 / 0 mol % (methane / ethane / propane), 243.6 K and 4 MPa, and
   press **RUN FLASH**.
2. Record the vapour fraction β and the methane mole fractions *x*(C1) in the
   liquid and *y*(C1) in the vapour.
3. Compute K(C1) and K(C2). Check that one is above 1 and the other below 1.
   Why must that be true for a two-phase binary?
4. Check the methane material balance.

## Part B: Bubble pressures across compositions

The bubble pressure of a liquid is the pressure at which its first bubble of
vapour forms as the pressure falls.

1. For each liquid methane fraction in the table, enter the composition at
   243.6 K. Open **Engineering Sweeps**, choose **Pressure**, and sweep from
   1 to 7 MPa with 31 points (0.2 MPa steps).
2. The bubble pressure is the highest pressure at which the fluid is still
   two-phase. Refine with a narrower sweep around it if you like.
3. For pure ethane (0 / 100 / 0 mol %) the bubble pressure is the vapour
   pressure.
4. Fill in the table and plot bubble pressure against *x*(C1).

| *x*(C1) | Bubble pressure (MPa) |
|---|---|
| 0 (pure ethane) | |
| 0.10 | |
| 0.20 | |
| 0.30 | |
| 0.40 | |
| 0.50 | |
| 0.60 | |

5. Is the bubble curve a straight line? Where does it bend?

## Part C: The P–x–y diagram from flash results

At fixed temperature and pressure, a two-phase binary splits into a liquid of
composition *x* and a vapour of composition *y*. For a binary these two
compositions do not depend on the feed, as long as the feed is two-phase.

1. Run a flash at 243.6 K at each pressure below. Use a feed that is two-phase
   there: 30 / 70 mol % at 2 and 3 MPa, 50 / 50 at 4 and 5 MPa, and 65 / 35 at
   6 and 6.5 MPa.
2. Record *x*(C1), *y*(C1), K(C1) and K(C2).

| P (MPa) | *x*(C1) | *y*(C1) | K(C1) | K(C2) |
|---|---|---|---|---|
| 2.0 | | | | |
| 3.0 | | | | |
| 4.0 | | | | |
| 5.0 | | | | |
| 6.0 | | | | |
| 6.5 | | | | |

3. At 3 MPa, repeat the flash with the 50 / 50 feed. Do *x* and *y* change?
   What does change?
4. Plot *x*(C1) and *y*(C1) against pressure on one graph, and add your Part B
   bubble pressures. Which curve is the bubble curve?
5. Where does the two-phase region start at the bottom, and where does it end
   at the top? Why does it never reach pure methane?
6. How do K(C1) and K(C2) change as pressure rises? What value do both approach,
   and what happens there?
7. Look at *y*(C1) at 5, 6 and 6.5 MPa. What happens to the vapour composition
   near the top of the diagram?

## Part D: Comparison with the May (2015) bubble data

The **Validation** page compares the model with the May et al. (2015)
measurements in the protected Module 17 record. The bubble direction takes the
measured liquid composition and temperature, and predicts the pressure.

1. Open **Validation** and display the bubble-pressure figures. Find the
   methane–ethane points.
2. For the states below, all at 243.6 K, compare the measured pressure with
   your Part B bubble curve at the same *x*(C1).

| State | *x*(C1) | Measured P (MPa) | Measured *y*(C1) |
|---|---|---|---|
| 006 | 0.2812 | 3.675 | 0.6510 |
| 007 | 0.3082 | 3.942 | 0.6660 |
| 008 | 0.3973 | 4.831 | 0.7046 |
| 010 | 0.4553 | 5.395 | 0.7212 |
| 011 | 0.4741 | 5.564 | 0.7255 |
| 015 | 0.5273 | 6.080 | 0.7222 |
| 013 | 0.6218 | 6.885 | 0.7123 |

3. Is the model error random, or does it follow a trend with pressure?
4. For some states the production record shows *not found* instead of a
   pressure. Where are they, and why is "not found" a better answer than a
   number the solver does not trust?

## Part E: Discussion

1. Methane is above its critical temperature (190.6 K) at 243.6 K. Why does that
   rule out Raoult's law for this mixture?
2. The model uses kij = 0. How would a small positive kij move the bubble
   curve, and would that help in Part D?
3. Your Part C table shows the vapour methane fraction levelling off and then
   falling near the top. Lab 1 Part E met the same feature for methane–propane.
   Why does it make a dew pressure at a measured vapour composition hard to
   pin down?

---

## Instructor answer key

All values are from the unchanged engine for methane–ethane at 243.6 K,
kij = 0. `tests/test_teaching_lab_02.py` checks them, so this key stays
consistent with the model. Bubble pressures in Parts B and C use the engine's
saturation solver with Newton refinement. Part D also reports the production
validation record, which uses the solver's defaults.

**Part A.**

- β = 0.5245; *x*(C1) = 0.3152, *y*(C1) = 0.6676.
- K(C1) = 2.118 and K(C2) = 0.485. If both K-values were above 1 (or both
  below), the vapour (or the liquid) mole fractions could not both sum to 1, so
  a two-phase binary always has one of each.
- Material balance: 0.5245 × 0.6676 + 0.4755 × 0.3152 = 0.500.
- The flash converges in 14 iterations, with a final equilibrium residual
  below 1e-8.

**Part B.**

| *x*(C1) | Bubble pressure (MPa) | First-bubble *y*(C1) |
|---|---|---|
| 0 (pure ethane) | 1.081 | 0 |
| 0.10 | 1.988 | 0.420 |
| 0.20 | 2.915 | 0.579 |
| 0.30 | 3.856 | 0.659 |
| 0.40 | 4.801 | 0.703 |
| 0.50 | 5.726 | 0.724 |
| 0.60 | 6.556 | 0.723 |

- Students reading a 0.2 MPa sweep should land within one step of these values.
- The curve is close to a straight line up to *x*(C1) = 0.5, rising by 0.91 to
  0.95 MPa per 0.1 of methane. From 0.5 to 0.6 it rises by only 0.83 MPa: it
  bends over as the mixture approaches its critical point at this temperature.
- With the solver's defaults, the bubble solve reports *not found* at
  *x*(C1) = 0.50 and 0.60; Newton refinement converges there. A pressure sweep
  is a different method and does not depend on that solver setting.

**Part C.**

| P (MPa) | *x*(C1) | *y*(C1) | K(C1) | K(C2) |
|---|---|---|---|---|
| 2.0 | 0.101 | 0.423 | 4.173 | 0.642 |
| 3.0 | 0.209 | 0.588 | 2.814 | 0.520 |
| 4.0 | 0.315 | 0.668 | 2.118 | 0.485 |
| 5.0 | 0.421 | 0.709 | 1.684 | 0.502 |
| 6.0 | 0.531 | 0.727 | 1.368 | 0.583 |
| 6.5 | 0.592 | 0.724 | 1.222 | 0.677 |

- At 3 MPa the 50 / 50 feed gives the same *x* and *y* as the 30 / 70 feed.
  Only the vapour fraction changes, by the lever rule.
- The *x*(C1) curve is the bubble curve; it matches Part B. The *y*(C1) curve
  is the dew curve.
- The two-phase region starts at the ethane vapour pressure, 1.081 MPa, where
  *x* = *y* = 0. It closes at the mixture critical point at this temperature,
  between 6.5 and 7 MPa, where *x* = *y*. At 7 MPa no feed is two-phase. It
  never reaches pure methane because methane cannot be liquid above 190.6 K.
- K(C1) falls and K(C2) rises with pressure (after a shallow minimum near
  4 MPa). Both approach 1 at the mixture critical point, where the two phases
  become identical.
- *y*(C1) rises to a maximum of about 0.727 near 6 MPa and then falls slightly.
  Near the top of the diagram one vapour composition can coexist with two
  different liquids at two different pressures.

**Part D.**

Model bubble pressures at the measured liquid composition:

| State | Measured P (MPa) | Production record (MPa) | Error | With Newton refinement (MPa) | Error |
|---|---|---|---|---|---|
| 006 | 3.675 | 3.679 | +0.10 % | 3.679 | +0.10 % |
| 007 | 3.942 | 3.934 | -0.21 % | 3.934 | -0.21 % |
| 008 | 4.831 | 4.776 | -1.14 % | 4.776 | -1.14 % |
| 010 | 5.395 | 5.318 | -1.43 % | 5.318 | -1.43 % |
| 011 | 5.564 | 5.491 | -1.32 % | 5.491 | -1.32 % |
| 015 | 6.080 | not found | | 5.968 | -1.84 % |
| 013 | 6.885 | not found | | 6.704 | -2.62 % |

- The production record behind the **Validation** page, for methane–ethane
  bubble pressures: 11 of 17 states solved, average absolute deviation 0.45 %,
  largest error 1.43 %, mean signed error -0.29 %.
- The error is not random. All states below 4 MPa (at every temperature) are
  within 0.31 %. Above 4 MPa every error is negative and the largest are at the
  highest pressures, about -2.6 % near 6.9 MPa: the model under-predicts the
  bubble pressure as the critical region is approached.
- All six *not found* states (009, 012, 013, 015, 016, 017) lie at 243.6 K and
  above 5 MPa, close to the mixture critical point. The solver could not find a
  trustworthy pressure bracket there. Reporting that keeps a doubtful number out
  of the statistics. With Newton refinement 4 of them converge (009, 013, 015,
  016) and 2 still do not (012, 017); see
  `docs/investigations/validation_newton_comparison.md`.
- The predicted first-bubble vapour compositions are also close: for state 008
  the model gives *y*(C1) = 0.7023 against 0.7046 measured.

**Part E.**

- Raoult's law needs each pure component's vapour pressure at the system
  temperature. Methane is supercritical at 243.6 K and has no vapour pressure,
  which is also why the P–x–y lens cannot reach *x*(C1) = 1.
- A positive kij weakens the attraction between unlike molecules, which raises
  the bubble pressure. The engine can evaluate this, although the app keeps
  kij = 0: with kij = 0.01 the bubble pressure of state 008 rises from 4.776 to
  4.867 MPa, which moves the error from -1.14 % to +0.75 %. The Part D errors
  are negative, so a small positive kij would reduce them. The model
  deliberately uses kij = 0 and no fitting.
- Near the maximum of *y*(C1) the dew pressure is extremely sensitive to *y*,
  and just below the maximum two dew pressures share one *y*. A small
  uncertainty in the measured *y* then allows a large range of dew pressure
  (`docs/DEW_INVESTIGATION.md`). That is why this lab compares bubble pressures
  and flash compositions, and quotes no dew pressures.
