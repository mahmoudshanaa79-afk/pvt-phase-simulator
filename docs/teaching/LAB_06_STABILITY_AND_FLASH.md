# Lab 6: Phase stability and the flash (methane + propane)

**Tool:** OpenPhase (Peng–Robinson EOS), live app or a local copy.
**Fluid:** 50/50 methane–propane.
**Time:** about 60 minutes.
**Prerequisites:** Lab 1, and the idea of a K-value from a thermodynamics
course.

Switch on **Learn mode** in the sidebar for short explanations on each page.

## Learning outcomes

By the end of the lab you should be able to:

1. Say what the tangent-plane distance (TPD) measures and what its sign means.
2. Read the engine's stability verdict and the evidence behind it.
3. Solve the Rachford–Rice equation for a two-component flash by hand.
4. Explain why "stable" near a critical point can mean "no instability found"
   rather than "proven stable".

## Background

Before splitting a feed into two phases, the engine tests whether the feed is
stable. It runs two trials, one starting vapour-like and one liquid-like, and
for each converged trial composition w it computes the tangent-plane distance

    TPD(w) = Σ wᵢ [ ln wᵢ + ln φᵢ(w) − ln zᵢ − ln φᵢ(z) ]

A negative TPD means a phase of composition w would lower the Gibbs energy, so
the feed is **unstable** and splits. If a trial simply returns the feed itself
(TPD = 0), it is called **trivial**. A trivial trial found nothing; it did not
prove anything.

For an unstable feed, the flash solves the **Rachford–Rice** equation for the
vapour fraction β:

    Σ zᵢ (Kᵢ − 1) / (1 + β (Kᵢ − 1)) = 0,   xᵢ = zᵢ / (1 + β (Kᵢ − 1)),   yᵢ = Kᵢ xᵢ

**Where to read the numbers.**
- Overview shows the phase state, the vapour fraction, the phase compositions
  and the stability status.
- The trial details are on **Diagnostics → Show advanced raw public objects**
  → `phase_stability` → `vapor_like_trial` and `liquid_like_trial`, as
  `tangent_plane_distance`, `trivial_solution` and `final_trial_composition`.
- The K-values are `final_k_values` in the same tree.

## Part A: Four pressures at 300 K

Enter 50 / 0 / 50 mol % methane / propane and 300 K. Run the flash at 2, 5, 8
and 20 MPa.

1. For each pressure, record the phase state, the stability status, and each
   trial's TPD (or "trivial").
2. Which sign of TPD goes with "unstable"?
3. At one pressure both trials end at the same composition. Which one, and
   what does it suggest about how close the two phases are?
4. At 20 MPa both trials are trivial. Why is the feed still called stable
   there?

## Part B: Rachford–Rice by hand at 5 MPa

At 5 MPa read the converged K-values of methane and propane.

1. For two components the Rachford–Rice equation has a closed-form solution:

       β = [z₁(K₁ − 1) + z₂(K₂ − 1)] / [(K₁ − 1)(1 − K₂)]

   Compute β, then x and y for methane. Compare with Overview.
2. Check the material balance zᵢ = β yᵢ + (1 − β) xᵢ for methane.

## Part C: Where the K-values start

The engine starts from Wilson's correlation,
Kᵢ = (P_c,i / P) exp[5.373 (1 + ωᵢ)(1 − T_c,i / T)].

The engine's verified constants (Yang & Richter, 2025):

| Component | T_c (K) | P_c (MPa) | ω |
|---|---:|---:|---:|
| Methane | 190.564 | 4.5992 | 0.01142 |
| Propane | 369.89 | 4.2512 | 0.1521 |

1. Compute the Wilson K-values of methane and propane at 300 K and 5 MPa.
2. Compare them with the converged K-values from Part B. Why does the engine
   iterate instead of using Wilson's values directly?

## Part D: Near the critical point

The certified critical point of this mixture is 321.58 K and 8.534 MPa. Run the
flash at 8.534 MPa and 312 K, then at 316 K.

1. Record the phase state, the stability status, whether both trials are
   trivial, and whether the Overview shows a note under the single-phase
   message.
2. On **Phase Envelope** (operating temperature 300 K, RUN PHASE ENVELOPE),
   read the extended bubble branch between about 311 K and 319 K. Is the state
   at 316 K and 8.534 MPa inside or outside the envelope?
3. What does that say about a "stable" verdict that rests only on trivial
   trials? (Engine proposal P12 in `docs/ENGINE_CHANGE_PROPOSALS.md`
   discusses this.)

---

## Instructor answer key

All values are from the unchanged engine with production defaults, through the
same calls the app makes. `tests/test_teaching_lab_06.py` recomputes every
number below.

**Part A** (50/50, 300 K).

| P (MPa) | Phase state | Stability | Vapour-like TPD | Liquid-like TPD |
|---:|---|---|---|---|
| 2 | single phase | stable | trivial | +0.09297 |
| 5 | two phase | unstable | −0.00091 | −0.13164 |
| 8 | two phase | unstable | −0.01205 | −0.01205 |
| 20 | single phase | stable | trivial | trivial |

- A negative TPD means unstable.
- At 8 MPa both trials converge to the same composition (73.14 mol %
  methane): the two possible phases are becoming similar, as they do on the
  way to the critical region.
- At 20 MPa both trials are trivial, and the engine calls the feed stable
  because no trial found a lower-Gibbs-energy phase. Far from the critical
  point this is reliable; compare Part D.

**Part B** (5 MPa). K(methane) = 2.7192 and K(propane) = 0.4190.

- β = [0.5 × (2.7192 − 1) + 0.5 × (0.4190 − 1)] / [(2.7192 − 1) × (1 − 0.4190)]
  = 0.5698, the vapour fraction on Overview.
- x(methane) = 25.26 mol % and y(methane) = 68.68 mol %.
- Material balance: 0.5698 × 68.68 + 0.4302 × 25.26 = 50.00 mol %.

**Part C.**

| | Wilson K | Converged K |
|---|---:|---:|
| Methane | 6.678 | 2.719 |
| Propane | 0.2010 | 0.4190 |

- Wilson's correlation ignores composition and the real phase behaviour, so it
  overestimates how differently the components distribute. The engine uses it
  only as a starting point and iterates until the fugacities of every
  component are equal in both phases.

**Part D** (8.534 MPa).

| T (K) | Phase state | Stability | Both trials trivial | Note on Overview |
|---:|---|---|---|---|
| 312 | two phase | unstable | no | no |
| 316 | single phase | stable | yes | yes |

- The extended bubble branch passes 8.8092 MPa at 311.43 K and 8.6648 MPa at
  318.97 K. At 316 K the bubble pressure is therefore above 8.534 MPa, and
  the state is **inside** the envelope.
- So the flash's "single phase, stable" at 316 K is wrong: both trials
  collapsed to the trivial solution, and the test found nothing rather than
  proving stability. Near a critical point the tangent plane is nearly flat,
  and the bounded set of trial starts can miss the instability.
- The engine says so. When "stable" rests only on trivial trials, it adds the
  diagnostic `STABILITY_TRIVIAL_TRIALS_ONLY`, and the Overview shows a short
  note: stable here means no instability was found. The verdict itself does
  not change (proposal P12, part (b), implemented in November 2026). The same
  note appears at 20 MPa in Part A, where the feed really is single-phase, so
  the note means "check", not "wrong". Near a critical point, check the
  verdict against the envelope.
