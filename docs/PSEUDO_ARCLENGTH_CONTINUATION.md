# Pseudo-Arclength Phase-Envelope Continuation

## 1. Motivation and scope

The historical phase-envelope engine advances temperature and corrects pressure
and incipient composition at the requested temperature. That natural-parameter
method is deterministic and remains the production default. It is appropriate
while temperature is a valid local coordinate, but it cannot pass a regular
geometric fold where `dT/ds` vanishes and reverses.

Module 18 adds a separate, explicit `trace_pseudo_arclength_branch` API. It
advances along the local tangent of the saturation manifold. It does not change
the Peng–Robinson EOS, mixing rules, properties, `kij=0` default, saturation
solver, or legacy phase-envelope path. It is not a critical-point solver.

## 2. Geometric fold picture

Parameter continuation asks for one state at each chosen temperature. Near a
temperature turning point, two neighboring physical states can share nearly
the same temperature and `T` ceases to label the curve uniquely.
Pseudo-arclength instead intersects the equilibrium manifold with a local
hyperplane normal to the previous tangent. Temperature and pressure are both
allowed to move during correction, so either may reverse along the ordered
curve.

## 3. Continuation state and scaling

For `m` active components, the state is

```text
u = [w_1, ..., w_(m-1), ln(P), ln(T)]
```

where `w` is the incipient-phase composition. The final fraction is
`w_m = 1 - sum(w_1, ..., w_(m-1))`. This is the same direct simplex treatment
used by the safeguarded saturation Newton system; no redundant composition
coordinate is introduced.

Both pressure and temperature are positive by construction. `ln(P)` and
`ln(T)` are dimensionless, as are mole fractions, so the default diagonal
weight matrix is the identity. This avoids combining raw kelvin or pascals with
composition increments. Positive user-supplied diagonal state weights are
supported for sensitivity studies; all tangent normalization, orientation,
prediction, and constraint operations use the same weights.

## 4. Physical equilibrium equations

The physical residual is the full component fugacity equality already used by
the local saturation Newton formulation:

```text
F_i(u) = ln(z_i) + ln(phi_i^parent)
         - ln(w_i) - ln(phi_i^incipient) = 0
```

There are `m` residuals and `m+1` continuation unknowns. The parent composition
`z` is fixed. Bubble continuation uses a liquid parent and incipient vapor; dew
continuation uses a vapor parent and incipient liquid.

The physical Jacobian has shape `m × (m+1)`. Its composition and `ln(P)`
columns come directly from the Module 15 saturation Newton system. The
temperature column uses Module 13 fixed-root derivatives and the exact chain
rule

```text
dF/dln(T) = T dF/dT.
```

Root selection is reevaluated at each state. No derivative is taken through a
root-selection switch.

## 5. Tangent and orientation

At a regular point, the tangent satisfies

```text
J_F t = 0
t^T W t = 1.
```

The implementation obtains the one-dimensional null space from a full SVD. It
rejects a Jacobian whose numerical nullity is not exactly one. With a previous
tangent, the new sign is chosen so `t_new^T W t_previous > 0`. At
initialization, the orientation is aligned with the secant between two trusted
fixed-temperature saturation states. The fallback deterministic rule makes the
largest-magnitude component positive. These policies prevent arbitrary sign
flips.

Focused tests independently verify the null-space residual, weighted norm,
scaled-coordinate behavior, deterministic sign, previous-tangent alignment,
and failure for unsupported nullity. An adversarial orientation test checks
every consecutive weighted dot product.

## 6. Predictor and arclength constraint

For accepted state `u_k`, oriented tangent `t_k`, and dimensionless step
`delta_s`, the predictor is

```text
u_predictor = u_k + delta_s t_k.
```

It is only an initial guess. The corrector solves

```text
G(u) = [F(u), t_k^T W (u - u_predictor)] = 0.
```

The final equation is a tangent hyperplane, not a temperature target. The
augmented Jacobian is square with structure

```text
[ dF/du ]
[ t_k^T W ].
```

## 7. Safeguarded augmented Newton corrector

Each correction checks finite residuals and a finite augmented-Jacobian
condition number before solving the Newton step. Backtracking reduces the step
until the infinity norm of the augmented residual decreases. Trial states must
retain positive temperature and pressure, remain within configured pressure
bounds, and reconstruct a strictly interior normalized composition. Failure is
reported through structured corrector and continuation enums.

The defaults are 15 corrector iterations, condition-number ceiling `1e12`,
line-search reduction `0.5`, and minimum line-search factor `1e-6`. The
equilibrium tolerance is the existing `1e-8` saturation fugacity tolerance;
existing tolerances are not weakened.

## 8. Adaptive arclength step

The default initial, minimum, and maximum steps are `0.02`, `0.001`, and
`0.08`. A correction taking at most four Newton iterations grows the next step
by `1.25`, bounded by the maximum. A harder accepted correction halves the next
step. A failed correction is retried after halving. Reduction below the minimum
returns `MINIMUM_ARCLENGTH_STEP_REACHED`; it cannot continue indefinitely.

Results retain accepted and rejected counts, step-size and corrector-iteration
histories, equilibrium evaluation counts, step increases/reductions, turning
indicators, termination, and initialization source. Large internal matrices
and per-trial phase objects are not accumulated.

## 9. Physical safeguards and critical-region policy

The saturation evaluation preserves requested liquid/vapor root roles through
the audited phase-role classifier and deadband. Candidate states are rejected
if fixed-root continuity is lost. The Module 15.2 multicomponent trivial-state
predicate rejects unity-`K`, coincident-composition, same-root collapse; its
pure/effectively-pure behavior is retained.

Near-critical decisions reuse `EnvelopeContinuationSettings` thresholds. For a
multicomponent state, at least two of composition, `ln(K)`, and root separation
must enter their stop bands. For a pure active component only root separation
is informative. Pseudo-arclength may cross a regular pressure or temperature
turning point, but it stops rather than accepting root-role inversion, trivial
collapse, or phase coalescence. Module 20 remains the planned critical solver.

## 10. Generic fold proof

The non-EOS regression uses the parabola

```text
F(x, y) = x - y^2 = 0.
```

Ordinary `x`-parameter continuation cannot pass the minimum at `(0, 0)` while
remaining monotonic in `x`. Starting from `(1, -1)` and `(0.81, -0.9)`, 16
pseudo-arclength steps of `0.12` produce 18 states, progress from `y=-1` to
`y=+0.56035`, and cross the fold between `y=-0.06164` and `y=+0.05923`.
The `x` tangent changes sign, every consecutive tangent preserves orientation,
and maximum manifold error is below `1e-11`. Corrector histories contain two or
three iterations with no rejected continuation step.

This isolated test proves the continuation mathematics without relying on EOS
root behavior.

## 11. EOS monotonic-branch equivalence

The deterministic reference is the 50/50 CH4/C2 bubble branch initialized at
200 K and 202 K. Three corrected pseudo-arclength steps reach approximately
202.86905 K, 203.96699 K, and 205.35798 K. Independent production saturation
solutions at each pseudo state agree with maximum relative pressure error
`8.93e-15`, maximum incipient-composition error `6.67e-15`, and maximum selected
root error `8.22e-15`. All parent liquid roots remain below their incipient
vapor roots.

The representative pseudo trace accepts three steps, rejects none, uses
corrector history `(2, 2, 2)`, records 23 equilibrium evaluations, grows the
step three times, and performs no reduction. These are trace-specific work
figures, not universal performance claims. Pseudo-arclength generally costs
more per point because temperature is an additional Newton unknown.

## 12. Supported-fluid physical fold search

`tools/run_module18_fold_search.py` reproduces a bounded zero-`kij` search. It
covers CH4/C2 and CH4/C3 binaries at methane fractions 0.2, 0.5, and 0.8 plus
CH4/C2/C3 compositions 0.6/0.3/0.1 and 0.3/0.3/0.4. Bubble and dew branches are
initialized in both temperature directions, giving 32 traces. Starts are 180 K
for CH4/C2, 210 K for CH4/C3, and 190/210 K for the ternaries. Each trace uses
up to 25 points, initial arclength `0.04`, maximum `0.08`, pressure bounds
0.001–100 MPa, verified properties, and `kij=0`.

One regular pressure turning point is retained as a regression: the 50/50
CH4/C3 bubble branch starting at 210 K. Pressure rises from 3.396 MPa to a
maximum near 8.805 MPa at 308.456 K and then falls to 8.737 MPa at 316.726 K.
Across that accepted step, the pressure tangent changes from `+0.0747517` to
`-0.258157`, while the temperature tangent stays positive from `+0.366715` to
`+0.277437`. At the first point after the turn, the maximum fugacity residual is
`1.26e-9`, root separation is `0.06958`, composition separation is `0.05687`,
and liquid-parent/vapor-incipient identity remains correct. This is a geometric
pressure maximum, not a critical point. Continuing the exploratory trace later
terminates under the existing near-critical policy near 320.86 K; no
indistinguishable state is accepted.

No temperature tangent reversal was found in these 32 bounded traces. The
generic fold test is therefore the formal temperature-like fold traversal
proof, while the CH4/C3 regression demonstrates useful physical pressure-fold
diagnostics without relaxing critical safeguards.

## 13. Relation to Module 17

Module 17 found multiple dew pressures for many fixed `(T,y)` experimental
states. That is a multiplicity of saturation roots in a fixed-temperature,
fixed-parent-composition problem. A geometric fold is instead a tangent
property of one ordered fixed-overall-composition envelope curve. Neither fact
implies the other. Module 17 motivated examining CH4/C3, but no experimental
pressure is used as a pseudo-arclength predictor or replacement prediction.

## 14. Public API and legacy isolation

The opt-in production API is:

```python
trace_pseudo_arclength_branch(
    mixture,
    branch_kind,
    PseudoArclengthSettings(initial_temperature_step_k=2.0),
    start_temperature_k=200.0,
)
```

The existing `trace_phase_envelope_branch`, `trace_bubble_branch`,
`trace_dew_branch`, and `calculate_phase_envelope` APIs still invoke only
natural-temperature continuation. They do not import or dispatch to the new
engine. A mutation test replaces the pseudo entry point with a function that
raises and confirms the legacy trace remains byte-for-byte structurally equal.

## 15. Limitations and future work

- Only methane, ethane, and propane with `kij=0` are currently supported by the
  verified property set.
- The bounded search is evidence, not a proof that no other supported-fluid
  temperature fold exists.
- The direct-simplex coordinates require strictly positive active fractions;
  zero-feed components are removed using the saturation Newton active set.
- SVD and derivatives are local to already selected smooth roots. A root switch
  or unsupported nullity terminates continuation.
- Identity weights are dimensionally consistent but not universally optimal;
  alternate positive weights require sensitivity review.
- Pseudo-arclength improves geometric continuation. It does not locate an exact
  critical point, certify global phase stability, select among every possible
  disconnected saturation branch, or replace Module 20.
- Computational cost and robustness are reported separately; no universal
  speed claim is made from representative traces.

Module 19 may build on this continuation evidence only after independent
adversarial review of formulation, scaling, tangent orientation, augmented
Jacobian, fold traversal, phase identity, critical-region safety, adaptation,
and legacy-path immutability.
