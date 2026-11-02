# Lab 4: What kij does (methane + propane)

**Tool:** OpenPhase (Peng–Robinson EOS), live app or a local copy, with the
optional kij input.
**Fluid:** methane–propane, compared with the May et al. (2015) measurements.
**Time:** about 60 minutes.
**Prerequisites:** Labs 1 and 2, and the van der Waals mixing rule with a
binary interaction parameter kij from a thermodynamics course.

Switch on **Learn mode** in the sidebar for short explanations on each page.

## Learning outcomes

By the end of the lab you should be able to:

1. Say what a binary interaction parameter changes in Peng–Robinson and what it
   leaves alone.
2. Compare model bubble pressures at kij = 0 and at a fitted kij against
   measurements, and judge whether the fit helps everywhere.
3. Read a P–x–y diagram at one temperature and see how kij moves it.
4. Explain why a fitted kij does not make an ambiguous dew-point question
   answerable.

## Background

OpenPhase uses kij = 0 by default, and its validation record is a pure
prediction at kij = 0. The study `docs/investigations/kij_study.md` fitted one
constant kij for methane + propane to the measured bubble pressures:
**kij = +0.0021**. That value is a fit to one source, not a prediction.

To set it, open **Advanced: binary interaction (kij)** in the sidebar form,
enter **0.0021** for the C1–C3 pair and press **RUN FLASH**. A *user-supplied
kij* badge appears while a non-zero kij is in use. Set the field back to 0 to
return to the default.

All work in this lab is at **243.62 K**, one of the measured isotherms. The
**Phase Envelope** page, after **RUN PHASE ENVELOPE**, lists the bubble and dew
pressure at the operating temperature with the engine's status and codes, and
the composition of the incipient phase.

This lab quotes no dew pressure where the solver reports the dew answer as
ambiguous.

## Part A: Bubble pressures at four measured states

Each state is a measured liquid at 243.62 K. Enter the liquid as the mixture
(methane mol %, 0 ethane, the rest propane), set 243.62 K, run, and read the
bubble pressure. Do it at kij = 0 and at kij = 0.0021.

| State | Liquid CH4 (mol %) | Measured P (MPa) |
|---|---:|---:|
| 009 | 7.10 | 0.891 |
| 010 | 34.42 | 3.909 |
| 012 | 55.65 | 6.402 |
| 014 | 69.61 | 7.943 |

1. Fill in the model bubble pressure and the signed error
   100·(P_model − P_measured)/P_measured at both kij values.
2. At which states does the fitted kij help, and at which does it hurt?
3. The fit minimised the *average* error over many states. Why can a constant
   kij still make one state worse?

## Part B: The P–x–y diagram at 243.62 K

For liquid methane fractions of 10, 30, 50 and 65 mol %, run the bubble point
at both kij values. Record the bubble pressure (the P–x curve) and the methane
fraction of the incipient vapour (the P–y curve).

1. Sketch both curves at kij = 0 and at kij = 0.0021 on one diagram.
2. Which curve moves more with kij: P–x or P–y? By roughly how much, in
   percent?
3. Using the mixing rule, explain why a small positive kij raises the bubble
   pressure.

## Part C: Does kij fix the dew question?

State 013 has a measured vapour of 92.21 mol % methane at 243.62 K. Enter that
vapour as the mixture (92.21 / 0 / 7.79), set 243.62 K and read the **dew**
pressure line at kij = 0 and at kij = 0.0021.

1. What status and diagnostic code does the engine report each time?
2. The kij study counts the CH4+C3 dew states the solver calls ambiguous at
   kij = 0 and at the fitted kij. Look up both numbers in
   `docs/investigations/kij_study.md`. What do they tell you?
3. Why is "two possible dew pressures" a better answer than a number here?

## Part D: Discussion

1. The fitted kij is scored on the same measurements it was fitted to. Why is
   that calibration rather than validation?
2. All the data come from one laboratory. What would you want before adopting
   kij = 0.0021 as a default?

---

## Instructor answer key

All values are from the unchanged engine with the production defaults
(scanning solver, Newton refinement off), at 243.62 K, through the same calls
the app makes. `tests/test_teaching_lab_04.py` recomputes every number below.

**Part A.**

| State | Measured P (MPa) | kij = 0: P (MPa) | error | kij = 0.0021: P (MPa) | error |
|---|---:|---:|---:|---:|---:|
| 009 | 0.891 | 0.8842 | −0.76 % | 0.8911 | +0.01 % |
| 010 | 3.909 | 3.8597 | −1.26 % | 3.8871 | −0.56 % |
| 012 | 6.402 | 6.3791 | −0.36 % | 6.4104 | +0.13 % |
| 014 | 7.943 | 7.9978 | +0.69 % | 8.0218 | +0.99 % |

- The fitted kij raises every bubble pressure. That helps at 009, 010 and 012,
  where kij = 0 under-predicts, and hurts at 014, close to the critical
  region, where kij = 0 already over-predicts.
- One constant kij is a compromise. In the study, each state's own best kij
  is between +0.002 and +0.004 at 009 to 012 but −0.005 at 014, near the
  critical region, so the average fit cannot be best everywhere.

**Part B.**

| Liquid CH4 (mol %) | kij = 0: P (MPa) | vapour CH4 (mol %) | kij = 0.0021: P (MPa) | vapour CH4 (mol %) |
|---:|---:|---:|---:|---:|
| 10 | 1.1827 | 83.35 | 1.1922 | 83.45 |
| 30 | 3.3540 | 92.04 | 3.3790 | 92.06 |
| 50 | 5.7001 | 92.98 | 5.7318 | 92.96 |
| 65 | 7.4836 | 91.86 | 7.5110 | 91.80 |

- The P–x curve rises by about 0.4 % to 0.8 % at fixed liquid composition; the
  vapour composition changes by at most about 0.1 mol %.
- A positive kij lowers the unlike-pair attraction a₁₂ = √(a₁a₂)(1 − kij), so
  the liquid holds methane less strongly and a higher pressure is needed to
  keep it in solution.
- At 65 mol % the fitted-kij bubble point carries
  `BOUNDARY_SATURATION_ROOT`: a converged root found next to a failed grid
  point, still bracketed, so the pressure stands.

**Part C.**

- At both kij values the dew solve at 92.21 mol % methane returns
  *inconclusive* with `MULTIPLE_SATURATION_ROOTS`: PR has two dew pressures
  for this vapour, so the app reports none.
- The study finds 20 of 23 CH4+C3 dew states ambiguous at kij = 0 and 20 of 23
  at the fitted kij. A constant kij shifts the curves slightly but does not
  move the measured vapours off the top of the y(P) isotherm, where the dew
  question has two answers.
- A single number would hide that the measurement cannot pick between the two
  roots. Reporting both possibilities (or none) is the honest answer.

**Part D.**

- The fit uses the measured bubble pressures to choose kij, so a smaller error
  on those same states is expected and proves little. Validation needs data the
  fit did not see.
- A second, independent dataset for methane + propane, ideally over a wider
  temperature range, and a check that one constant kij holds across it.
