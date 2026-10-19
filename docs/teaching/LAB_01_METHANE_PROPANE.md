# Lab 1: Phase behaviour of a methane–propane mixture

**Tool:** OpenPhase (Peng–Robinson EOS, kij = 0), live app or a local copy.
**Fluid:** 50 mol % methane, 50 mol % propane (the default case).
**Time:** about 60 minutes.
**Prerequisites:** vapour–liquid equilibrium, K-values and phase diagrams at the
level of an introductory reservoir-fluids course.

Switch on **Learn mode** in the sidebar for short explanations on each page.

## Learning outcomes

By the end of the lab you should be able to:

1. Interpret a two-phase flash result and check it with a material balance.
2. Read the bubble curve, dew curve, cricondenbar, cricondentherm and critical
   point from a P–T envelope.
3. Explain retrograde condensation with numbers from a pressure sweep.
4. Say when a model result should not be trusted, and why.

## Part A: Flash at 300 K and 5 MPa

1. Leave the default inputs (50 / 0 / 50 mol %, 300 K, 5 MPa) and press
   **RUN FLASH**.
2. Record the vapour fraction β, the liquid and vapour methane mole fractions
   *x*(C1) and *y*(C1), and both compressibility factors.
3. Compute K(C1) = *y*/*x* and K(C3) for propane. Which component prefers the
   vapour, and why?
4. Check the material balance for methane: does β·*y* + (1 − β)·*x* equal the
   feed fraction 0.50?
5. Explain why the liquid compressibility factor is much smaller than the
   vapour one.

## Part B: The phase envelope

1. Open **Phase Envelope** and press **RUN PHASE ENVELOPE**.
2. From the extended (dotted) curves, read the cricondenbar (highest pressure)
   and the cricondentherm (highest temperature), each with its matching
   temperature or pressure.
3. Open **Critical Point**, choose the example **Audited critical-solver
   seed**, press **RUN FLASH**, then **RUN CRITICAL SOLVER**. Record the
   critical temperature and pressure.
4. Is the critical point the highest-pressure or the highest-temperature
   point of the envelope? Explain.

## Part C: Isothermal sweep at 300 K

1. Return to 300 K and 5 MPa, press **RUN FLASH**, open **Engineering
   Sweeps**, choose **Pressure**, and sweep from 1 to 10 MPa with 37 points.
2. Between which pressures is the fluid two-phase? Compare with the envelope
   at 300 K.
3. Describe how the vapour fraction changes as pressure rises.

## Part D: Retrograde condensation at 325 K

1. Set the temperature to 325 K, press **RUN FLASH**, and sweep pressure from 5
   to 8 MPa.
2. Where does liquid first appear? Does liquid appear as pressure rises or as
   it falls?
3. Find the smallest vapour fraction in your sweep and the pressure where it
   occurs.
4. Near 7.9 MPa the flash reports *inconclusive*, and just above it a single
   phase. Why might a calculation become hard this close to the critical point?
   Why is "inconclusive" a better answer than a number?

## Part E: Model limits (discussion)

1. The model uses kij = 0 and no volume translation. Which of your Part A
   numbers would you trust least, and why?
2. Open **Validation**. The CH4+C3 bubble pressures agree with experiment
   within about 1 %, but the dew pressures look far worse. Using
   `docs/DEW_INVESTIGATION.md`, explain why a large dew-pressure error here is
   not mainly a model error.

---

## Instructor answer key

All values are from the unchanged engine for 50/50 methane/propane, kij = 0.
`tests/test_teaching_lab.py` checks them, so this key stays consistent with the
model.

**Part A.**

- β = 0.5698; *x*(C1) = 0.2526, *y*(C1) = 0.6868; *x*(C3) = 0.7474,
  *y*(C3) = 0.3132.
- K(C1) = 2.719 and K(C3) = 0.419. Methane is the lighter, more volatile
  component, so it concentrates in the vapour.
- Material balance: 0.5698 × 0.6868 + 0.4302 × 0.2526 = 0.500.
- Z(liquid) = 0.172 and Z(vapour) = 0.724. The liquid occupies a far smaller
  volume per mole at the same T and P.
- The flash converges in 15 iterations, with a final equilibrium residual
  below 1e-8.

**Part B.**

- The cricondenbar is about 8.81 MPa, at about 311.4 K.
- The cricondentherm is about 329.1 K, at about 6.78 MPa.
- The critical point is 321.58 K and 8.534 MPa. It is neither the highest
  pressure nor the highest temperature. For this mixture it lies on the envelope
  between the cricondenbar and the cricondentherm. For a mixture, the critical
  point is generally not an extreme of the envelope.

**Part C.**

- The fluid is two-phase from the dew point at about 2.35 MPa up to about
  8.67 MPa, where the bubble curve is reached.
- The vapour fraction falls from 1 at the dew point, through about 0.57 at
  5 MPa and about 0.20 at 8 MPa, to 0 at the bubble point.

**Part D.**

- Liquid appears at about 5.24 MPa (the lower dew point) as pressure **rises**.
  That is retrograde condensation, because 325 K lies between the critical
  temperature and the cricondentherm.
- The vapour fraction reaches a minimum of about 0.80 near 7.7 MPa, then rises
  again toward the upper dew point.
- Near 7.9 MPa the two phases are becoming similar and the calculation is
  numerically difficult. Reporting *inconclusive* avoids presenting a guess as a
  result.

**Part E.**

- Liquid volume and density from the liquid Z are least reliable. Without
  volume translation, Peng–Robinson saturated-liquid densities are typically off
  by several percent and up to about 12 % for these components. kij = 0 adds a
  small composition bias.
- The measured vapour compositions sit at the maximum of PR's *y*(P) isotherm,
  where dew pressure is extremely sensitive to *y*. The stated composition
  uncertainty alone allows megapascals of dew pressure. Compared at the measured
  pressure, the model's vapour composition agrees within the stated uncertainty
  at 22 of 23 states.
