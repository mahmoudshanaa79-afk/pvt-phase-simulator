# Dew-branch investigation

Status: investigation complete; **no engine change made**. Two findings need a
decision from the project owner before any engine change (see the last section).

This note answers the two open dew questions:

1. Why does the CH4+C3 production dew direction show about 36.7% pressure AARD
   and 16 failures in 23 states?
2. Why do some extended phase-envelope branches stop early with `phase_role_lost`?

All results were produced with the unchanged engine: Peng–Robinson, classical
mixing, kij = 0, verified component properties, no fitting. The measured pressure
is used only as the point at which a composition is compared. It never selects a
root.

Reproduce:

```
uv run python tools/run_dew_conditioning_study.py
uv run python tools/run_root_count_whatif.py
```

The first writes `docs/investigations/ch4_c3_dew_conditioning.csv`. The protected
Module 17 artifacts under `docs/validation` are only read.

## 1. CH4+C3 dew error is mostly an ill-posed question, not model error

### The question being asked

The dew direction fixes the measured `T` and vapour composition `y` and asks PR
for the pressure at which that vapour starts to condense. Along an isotherm of a
binary, the coexisting vapour CH4 fraction `y(P)` rises to a maximum `y_max` and
then falls toward the critical point. Near `y_max`:

- `dP/dy → ∞`, so a tiny change in `y` moves the dew pressure a lot;
- just below `y_max` there are two dew pressures for the same `y`;
- above `y_max` there is none.

The May (2015) CH4+C3 vapour compositions sit almost exactly at PR's `y_max`. On
the 243.6 K isotherm, PR's maximum is `y_max = 0.9301`. Twelve of the 23 states
are on that isotherm. Eleven of them have measured `y` between 0.907 and 0.9296,
with a stated expanded uncertainty of about ±0.0041. The twelfth, 009, is a
low-pressure state at `y = 0.79`.

### Method

For each measured dew state, the tool follows PR's own isotherm with the
production bubble solver. Newton refinement is on; it is an existing engine
option. The tool then reports:

- PR's `y_max` on the isotherm;
- `y_PR(P_exp)`, PR's coexisting vapour composition at the measured pressure.
  `dy = y_exp − y_PR(P_exp)` is a well-conditioned comparison of model and data;
- `|dP/dy|` at the measured pressure, and `|dP/dy|·U_y`, the dew-pressure spread
  that the stated composition uncertainty alone allows.

### Results (all 23 CH4+C3 states)

| Point | T (K) | P exp (MPa) | y exp | PR y_max | dy / U_y | dew-P spread from U_y (MPa) | Production | PR dew roots | Nearest root error |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|
| 001 | 203.40 | 3.576 | 0.9838 | 0.9868 | −0.60 | 7.90 | converged (lower) | 2 | −37.7% |
| 002 | 213.38 | 4.108 | 0.9755 | 0.9780 | −0.63 | 39.5 | inconclusive | 2 | −32.0% |
| 003 | 223.36 | 4.628 | 0.9634 | 0.9661 | −0.66 | 9.85 | converged (lower) | 2 | +24.5% |
| 004 | 223.54 | 4.622 | 0.9632 | 0.9659 | −0.66 | 10.6 | converged (lower) | 2 | +24.5% |
| 005 | 233.61 | 5.077 | 0.9480 | 0.9501 | −0.49 | 6.24 | inconclusive | 2 | +17.1% |
| 006 | 233.67 | 5.119 | 0.9482 | 0.9500 | −0.41 | 5.11 | inconclusive | 2 | +14.6% |
| 007 | 243.61 | 5.544 | 0.9266 | 0.9302 | −0.61 | 5.68 | inconclusive | 2 | +18.8% |
| 008 | 243.61 | 5.611 | 0.9285 | 0.9302 | −0.36 | 3.23 | inconclusive | 2 | +10.3% |
| 009 | 243.62 | 0.891 | 0.7924 | 0.9301 | +0.02 | 0.98 | converged | 1 | +2.8% |
| 010 | 243.62 | 3.909 | 0.9257 | 0.9301 | +0.04 | 0.59 | inconclusive | 2 | +0.6% |
| 011 | 243.62 | 5.544 | 0.9285 | 0.9301 | −0.37 | 4.17 | inconclusive | 2 | +11.5% |
| 012 | 243.62 | 6.402 | 0.9274 | 0.9301 | −0.04 | 0.84 | inconclusive | 2 | +0.5% |
| 013 | 243.62 | 7.530 | 0.9221 | 0.9301 | +0.99 | 0.31 | inconclusive | 2 | −4.8% |
| 014 | 243.62 | 7.943 | 0.9145 | 0.9301 | +0.72 | 0.22 | converged (lower) | 2 | −2.1% |
| 015 | 243.62 | 8.320 | 0.9070 | 0.9301 | +1.01 | 0.14 | converged (lower) | 2 | −1.9% |
| 016 | 243.63 | 5.500 | 0.9296 | 0.9301 | −0.11 | 5.15 | inconclusive | 2 | +5.5% |
| 017 | 243.63 | 6.989 | 0.9232 | 0.9301 | −0.12 | 0.49 | inconclusive | 2 | +0.9% |
| 018 | 243.64 | 5.635 | 0.9281 | 0.9301 | −0.43 | 3.00 | inconclusive | 2 | +11.3% |
| 019 | 253.59 | 6.100 | 0.9053 | 0.9056 | +0.01 | 2.23 | inconclusive | 2 | −0.5% |
| 020 | 263.51 | 6.597 | 0.8803 | 0.8760 | +0.90 | 2.01 | not found | 0 | — |
| 021 | 263.56 | 6.560 | 0.8826 | 0.8759 | +0.96 | 3.03 | not found | 0 | — |
| 022 | 273.48 | 7.102 | 0.8386 | 0.8405 | −0.14 | 1.06 | inconclusive | 2 | +1.9% |
| 023 | 283.38 | 7.630 | 0.7955 | 0.7990 | −0.12 | 0.64 | converged (lower) | 2 | +0.9% |

"Nearest root error" is the retrospective Module 17 nearest-root diagnostic,
repeated for context. It is not a prediction.

### What this shows

- **Measured at the measured pressure, PR and the data agree.** PR's vapour
  composition matches the measurement within the stated expanded uncertainty at
  22 of 23 states, and within twice it at 23 of 23. The worst case is 015, at
  1.01 U. Mean `|dy|` is 0.0022 mole fraction, excluding point 009, whose stated
  uncertainty is unusually large.
- **The dew pressure itself is ill-posed at most states.** At 15 of 23 states,
  the stated composition uncertainty alone allows more than 1 MPa of dew
  pressure, against pressure uncertainties of about 0.05 MPa. At state 002 it
  allows about 40 MPa. A dew-pressure error at these states says almost nothing
  about model accuracy.
- **"No PR root" is explained.** At 020 and 021 the measured `y` lies above PR's
  `y_max`, so no dew pressure can exist. Both are within 1 U of PR's composition.
- **Where the question is well-posed, PR does well.** At 009 (`dP/dy` about
  5 MPa) the production dew pressure is within 2.8%. At 010, 012, 017, 019, 022
  and 023 the appropriate PR root is within 2% of the measurement.

### Limits and a real bias

- At 203–244 K (001–008), PR's vapour CH4 fraction is consistently higher than
  measured, by 0.0015–0.0034 (0.36–0.66 U). This is a small systematic
  bias, not noise. kij = 0 is a plausible contributor, but it was not tested,
  because fitting kij is out of scope.
- The comparison follows PR's isotherm with the bubble solver. Its own
  validation on the same data is 1.03% pressure AARD.
- One source, one binary, the sampled domain only.

### The real solver weakness

The production refusals (`inconclusive`, "multiple apparent saturation-pressure
roots") are **correct behaviour**: the question has two answers. The weakness is
the opposite case. At 001, 003, 004, 014, 015 and 023, PR has two dew roots
(shown by the Module 17 scan), but the production solver returned `converged`
with the lower root, because its bracket search did not see the second one. A
user is told the answer is unique when it is not. That accounts for most of the
36.7% AARD (for example 014 at −63% and 015 at −69%).

### Related: three CH4+C3 bubble failures are solver reach

The bubble direction fails (`not_found`, "no trustworthy bracket") at 013, 014
and 015. These are near-critical states, 7.5–8.3 MPa at 243.6 K. With the
engine's existing Newton refinement switched on, all three converge:

| Point | PR bubble P | Measured P | Error |
|---|---:|---:|---:|
| 013 | 7.566 MPa | 7.530 MPa | +0.5% |
| 014 | 7.998 MPa | 7.943 MPa | +0.7% |
| 015 | 8.427 MPa | 8.320 MPa | +1.3% |

The Module 17 validation calls the solver with defaults, which leave Newton off.

## 2. Early `phase_role_lost` stops on the extended envelope

The pseudo-arclength tracer rejects a step when fixed-root continuity is lost,
and that check requires the **number of real cubic roots** to stay the same
(docs/NEWTON_SATURATION_DESIGN.md). Along a saturation curve, one phase's cubic
can go from three real roots to one while the selected root moves smoothly. The
tracer then stops instead of continuing.

Default 50/50 CH4/C3 case, dew branch started at 270 K:

- The shipped engine stops at 292.2 K / 1.86 MPa with `phase_role_lost`.
- At that step, the incipient liquid's cubic went from roots
  `[0.0637, 0.3505, 0.5443]` to `[0.0690]`. The two upper roots merged and
  vanished; the selected liquid root moved smoothly.
- With only that check relaxed, in-process (a root-count change is accepted when
  the selected root is still the nearest stable continuation), the branch
  continues through the cricondentherm (329.15 K, 6.98 MPa) and stops with the
  engine's near-critical guard at 322.5 K / 8.47 MPa. That is close to the
  certified critical point (321.58 K, 8.534 MPa).
- An independent production fixed-temperature dew solve at each of the 17 new
  points agrees within a relative 5×10⁻⁹.

Across 10 surveyed mixtures, every `phase_role_lost` stop came from a root-count
change:

- C1/C3 10/90 dew;
- C2/C3 30/70 bubble and dew;
- C2/C3 70/30 bubble and dew.

With the check relaxed, all reached the near-critical region. Fixed-temperature
solves agreed wherever one converged. The disagreements were on the far side of
a turning point, where the fixed-temperature solver picks the other root.

The C1/C3 30/70 dew branch also met one root-count change. It reached the same
end region either way, because the shipped path took a slightly different route.

Two other early stops have different causes and are not explained by this:

- the bubble initialisation failure at a 300 K start (50/50 at 330 K);
- the `trivial_state` stop near 9.9 MPa (70/30 at 270 K).

## Decisions for the project owner

Both findings point at frozen engine policy. Neither has been changed.

1. **Root-count continuity rule.** Allow a change in the number of cubic roots
   when the selected root is the unambiguous nearest stable continuation, in the
   pseudo-arclength tracer only. The evidence above supports it. The rule was a
   deliberate, audited choice, so changing it needs a design note, tests on the
   cases above, and an independent review.
2. **Ambiguous "converged" dew results.** When PR has more than one dew root at
   `(T, y)`, the production dew solver should not report a single converged
   root. The Module 17 scan already finds the roots; the production path does
   not use it.
3. **Dew validation metric.** Report dew-direction accuracy with a
   conditioning-aware metric, composition at the measured pressure, alongside
   dew pressure, and flag states where `|dP/dy|·U_y` exceeds the pressure
   uncertainty. This changes how the frozen Module 17 results are summarised, so
   it needs the same review gate.
4. **Validation solver options.** Decide whether validation should run the
   bubble and dew solvers with the engine's Newton refinement on. It would have
   converged at 013–015.
