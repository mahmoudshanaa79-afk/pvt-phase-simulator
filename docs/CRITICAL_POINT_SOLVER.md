# Module 20 mixture critical-point solver

## 1. Purpose

Module 20 locates a local Peng–Robinson mixture critical-point candidate at a
fixed user-specified overall composition. It solves the two Module 19
Gibbs-stability conditions simultaneously in temperature and pressure. It does
not vary composition, fit binary interactions, redefine criticality, or trace a
critical locus.

## 2. Module 19 contract

At each candidate state, the solver calls
`calculate_stable_root_mixture_criticality`. Only an `APPLICABLE` result can
enter the nonlinear iteration. The raw dimensionless residual is

```text
r_phys = (lambda_min, C),
```

where `lambda_min` is the smallest algebraic composition-tangent Gibbs
curvature and `C = D^3(g/RT)[d,d,d]` is the signed fixed-direction cubic
derivative. The solver never substitutes a Hessian determinant, root
separation, phase-composition separation, or `abs(C)`.

## 3. Why both conditions are required

`lambda_min = 0` alone describes loss of quadratic composition stability. A
spinodal-like state can meet that condition while retaining a large nonzero
cubic term and is not accepted as a critical point. Success requires both

```text
abs(lambda_min) <= 1e-7
abs(C)          <= 1e-6
```

and a scaled Euclidean norm no larger than `1e-6`.
These are three independent gates. Fixed residual scaling never replaces either
raw physical tolerance.

## 4. Variables and fixed composition

The exact solver ordering is

```text
q = (ln(T), ln(P));  T = exp(q[0]);  P = exp(q[1]).
```

This enforces positive physical variables. The supplied `FluidMixture`, its
component order, and every mole fraction remain fixed. Zero-fraction components
are carried through Module 19's active reduction; fewer than two active
components return `INSUFFICIENT_ACTIVE_COMPONENTS`. Pure-component criticality
is outside this mixture solver.

## 5. Critical-direction orientation

The first residual evaluation uses Module 19's deterministic orientation. Every
Jacobian and line-search evaluation receives the current accepted physical
critical direction through `previous_critical_direction`. A candidate is
rejected unless its new direction has a strictly positive dot product with the
previous direction. Only an accepted nonlinear iterate becomes the orientation
reference for the next iteration.

## 6. Residual scaling

Scaling is diagonal and fixed after initialization:

```text
s_lambda = configured value or max(abs(lambda_initial), 1)
s_C      = configured value or max(abs(C_initial), 1)
r_scaled = (lambda_min/s_lambda, C/s_C).
```

The unit floors avoid magnifying small initial residuals. User-provided fixed
positive scales are supported. Scaling changes conditioning and the merit
function, never the physical zero. Results retain raw residuals and scales.

## 7. Residual Jacobian

The Jacobian is with respect to `(ln(T), ln(P))`, including both logarithmic
chain factors. For each column and step `h`, the production calculation uses

```text
D(h)   = [r(q+h e_j)-r(q-h e_j)]/(2h)
D(h/2) = [r(q+h e_j/2)-r(q-h e_j/2)]/h
J[:,j] = [4D(h/2)-D(h)]/3.
```

The default requested log step is `1e-3`. The entrywise Richardson error must
satisfy

```text
abs(J-D(h/2)) <= 1e-6 + 2e-4*max(1, abs(J), abs(D(h/2))).
```

If the complete stencil is numerically unresolved, or if any symmetric sample
is outside bounds, nonfinite, non-applicable, loses direction continuity, or
changes PR root branch, `h` is halved deterministically up to eight times (and
never below `1e-7`). A finite but unresolved derivative is not accepted. The
accepted steps, refined matrix, error and threshold matrices, rejected-attempt
classifications, reductions, and evaluation count are recorded. Exhaustion
returns structured `JACOBIAN_FAILED` evidence.

Each production PR evaluation records the ordered physical-root count,
mechanical classifications, selected root index and Z, and ordered root values.
Every T/P stencil sample must retain compatible topology and select the unique
nearest continuation of the base root. This is separate from Module 19's
composition-perturbation continuity. At the deterministic 200 K Maxwell-locus
regression, symmetric states select liquid-like and vapor-like roots near
`Z=0.0112` and `Z=0.9207`; all candidate stencil sizes are rejected instead of
forming a mixed-root derivative.

An independent five-point stencil at the 50/50 methane/propane 320 K, 8.5 MPa
seed gives the production and independent raw Jacobians

```text
production  [[  4.23471068,   3.13340975],
             [227.48780486, -35.20412820]]

five-point  [[  4.23471071,   3.13340975],
             [227.48781149, -35.20412820]].
```

The maximum discrepancy is `6.63e-6` absolute and `2.91e-8` relative.

## 8. Safeguarded Newton method

Each iteration solves the scaled system

```text
J_scaled delta_q = -r_scaled.
```

The matrix and right-hand side must be finite. The default maximum condition
number is `1e10`; a singular or more ill-conditioned Jacobian returns
`ILL_CONDITIONED` rather than taking a least-squares or arbitrary giant step.
Per-iteration proposals are clipped to

```text
abs(delta ln(T)) <= 0.15
abs(delta ln(P)) <= 0.35.
```

The deterministic merit is `0.5*dot(r_scaled,r_scaled)`. A full step is tried
first, then factors `1, 1/2, 1/4, ...` down to `1e-6`. A trial must be within
bounds, Module 19 applicable, finite, orientation- and root-branch-continuous,
and strictly lower in scaled residual norm. Rejected trials are counted.

## 9. Physical bounds and applicability

Default bounds are 100–1000 K and 1 kPa–100 MPa. They are conservative solver
safeguards, not experimental validity claims. Configuration exposes all four
bounds. Module 19 failures—root ambiguity/coalescence, mode degeneracy,
unreliable symmetry, unavailable derivatives, or insufficient active support—
remain structured events. No zero, NaN, or arbitrary penalty residual replaces
an unavailable state.

## 10. Initialization and diagnostic scan

`solve_mixture_critical_point` requires explicit `initial_temperature_k` and
`initial_pressure_pa` and records an initialization-source label. The optional
`scan_mixture_criticality` evaluates a user-bounded deterministic linear-T,
geometric-P grid and reports every status plus the lowest scaled residual
candidate. It neither solves nor silently searches outside the supplied box.

## 11. Final certification

After iteration tolerances are met, the final state is evaluated twice from
scratch without a carried direction. Certification requires identical raw
residuals and directions, applicability, fixed-root derivative support,
acceptable Hessian symmetry, a unit tangent direction, zero composition sum,
and both raw and scaled tolerances. Otherwise the result is
`FINAL_VALIDATION_FAILED`.

## 12. Result and statuses

The immutable result records status, T, P, unchanged composition, raw and scaled
residuals, critical direction, full final Module 19 diagnostics, accepted and
rejected work, evaluation count, fixed scales, compact residual history,
Jacobian-condition history, initialization source, and termination reason.
Reachable structured statuses distinguish initialization, Module 19
applicability, Jacobian calculation/conditioning, bounds, line search, iteration
limit, final certification, and insufficient active components.

## 13. Synthetic verification and adversarial controls

Known linear and nonlinear two-variable systems verify convergence and
Jacobian column ordering. Separate tests cover log-chain factors, independent
five-point differentiation, deterministic step reduction, singular matrices,
real line-search backtracking, bounds, non-applicable states, eigenvector sign
flips, fresh final validation, and repeated-result determinism. An aliasing
field forces four Jacobian halvings before its known derivative passes the
error gate; a persistent oscillatory field exhausts the gate structurally. A
large-scale synthetic residual independently mutation-pins the raw cubic
tolerance. A residual with `lambda=0` and `C!=0` is never accepted, killing the
spinodal-only mutation.
Tests also pin fixed composition, zero-fraction reduction, no pure-component
reinterpretation, no hidden interaction fitting, and default-zero `kij`.

## 14. First Peng–Robinson result

The selected predictive case is 50/50 methane/propane with `kij=0`. A bounded
coarse inspection of the existing Module 18/19 near-critical region supplied a
transparent 320 K, 8.5 MPa seed. The default solve converges in three accepted
full steps to

```text
T_c = 321.5829183194 K
P_c = 8,534,443.2361 Pa
lambda_min = 5.40e-10
C          = 1.11e-10
||r_scaled||_2 = 5.51e-10
d = (0.7071067811865472, -0.7071067811865475).
```

The residual-norm history is approximately
`0.941224 -> 0.0450968 -> 3.19484e-4 -> 5.51441e-10`. Jacobian condition
numbers are `61.50`, `57.49`, and `57.54`.

## 15. Initialization sensitivity

Seeds `(320 K, 8.5 MPa)`, `(325 K, 9 MPa)`, `(315 K, 8 MPa)`, and
`(330 K, 10 MPa)` converge to the same state within `1e-5 K` and `0.2 Pa`.
They require 3, 3, 4, and 4 accepted steps. The widest seed records one rejected
full trial and a half-step before convergence. Out-of-bounds and unsuitable
seeds return structured outcomes rather than being silently replaced.

## 16. Spinodal control and local crossing

At the independently identified 294.178237 K, 7 MPa spinodal-like control,
`lambda_min` is about `6.61e-9` while `C` is about `-11.519`; it is not
accepted. Around the
certified solution, T perturbations of ±0.05 K change both residual signs:

```text
T-0.05 K: lambda=-9.70e-4, C=-3.32e-2
T+0.05 K: lambda=+9.81e-4, C=+3.32e-2.
```

Pressure perturbations of ±5 kPa likewise cross both residual surfaces.

## 17. Permutation and reference invariance

Solving the physically identical propane/methane ordering recovers the same T
and P within `1e-6 K` and `0.1 Pa` after undoing representation. Explicit
active reference choices 0 and 1 also recover the same critical state and raw
conditions. The direction representation follows Module 19's deterministic
orientation policy.

## 18. Supporting phase-coalescence evidence

Module 18 remains a separate algorithm. Its 50/50 methane/propane bubble trace
approaches the critical solution and stops under its existing near-critical
policy at 320.8551 K and 8.57685 MPa. At that endpoint, root separation is
`0.0117546`, composition separation is `0.00939846`, and
`max(abs(ln(K)))=0.0189758`. These trends support phase coalescence but are not
used as Module 20 residuals or acceptance conditions.

## 19. Limitations

The first verified physical case is binary methane/propane with verified pure
properties and default-zero interactions. A positive quartic stabilization
coefficient is not yet evaluated; `quartic_diagnostic` is therefore `None` and
fourth-order regularity remains an independent-review item. The result is a
local EOS-model candidate, not universal reservoir-fluid truth. No uncertainty
propagation, calibrated `kij`, broader-component validation, global root-basin
proof, or critical-locus continuation is supplied.

A pre-existing near-critical phase-stability weakness can collapse candidate
TPD trials to a trivial solution. Module 20 does not use that analysis as its
critical certificate, and this correction pass deliberately does not change
`phase_stability.py`. It remains separate backlog work.

## 20. Relation to Module 21

Module 20 stops at one fixed-composition critical solve. A future Module 21 may
use reviewed critical states for a distinct continuation or validation task.
Module 21 is not implemented here.
