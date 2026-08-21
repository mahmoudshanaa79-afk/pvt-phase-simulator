# Module 8 saturation-pressure design

This module calculates isolated bubble-point and dew-point pressures at fixed
temperature with the Peng–Robinson EOS. It does not trace a phase envelope,
locate a critical point, or claim retrograde or global-continuation handling.

## Bubble point

At the bubble point the fixed parent liquid composition is `x = z`, vapor
fraction approaches zero, and an infinitesimal normalized vapor `y` appears.
At equal pressure:

\[
z_i\phi_i^L P=y_i\phi_i^V P,
\qquad K_i=\frac{y_i}{z_i}=\frac{\phi_i^L}{\phi_i^V}
\]

The saturation objective is therefore:

\[
F_b(P)=\sum_i z_iK_i(P)-1
\]

The parent liquid uses the smallest mechanically stable root and the incipient
vapor uses the largest mechanically stable root.

## Dew point

At the dew point the fixed parent vapor composition is `y = z`, vapor fraction
approaches one, and an infinitesimal normalized liquid `x` appears:

\[
x_i\phi_i^L P=z_i\phi_i^V P,
\qquad K_i=\frac{z_i}{x_i}=\frac{\phi_i^L}{\phi_i^V}
\]

The saturation objective is:

\[
F_d(P)=\sum_i\frac{z_i}{K_i(P)}-1
\]

The parent vapor uses the largest mechanically stable root and the incipient
liquid uses the smallest mechanically stable root.

These are the beta-zero and beta-one endpoint relations of Rachford–Rice, but
saturation pressure is not obtained by merely forcing beta to an endpoint.
Pressure, both PR phase states, incipient composition, and component fugacity
equilibrium must be satisfied together.

## Wilson estimates

Define the pressure-like Wilson factor:

\[
C_i=P_{c,i}\exp\left[5.373(1+\omega_i)
\left(1-\frac{T_{c,i}}T\right)\right]
\]

Then:

\[
P_{bubble}^{Wilson}=\sum_i z_iC_i
\]

\[
P_{dew}^{Wilson}=\left(\sum_i\frac{z_i}{C_i}\right)^{-1}
\]

These finite positive values initialize the pressure search and K-values only;
they are not reported as EOS-equilibrium saturation pressures.

## Inner incipient-composition iteration

At every trial pressure the parent composition remains exactly `z`. Wilson
K-values initialize immutable log K-values. For a bubble calculation, trial
vapor log weights are `ln(z_i) + ln(K_i)`; for a dew calculation, trial liquid
log weights are `ln(z_i) - ln(K_i)`. Log-sum-exp normalization preserves zero
feed support and avoids avoidable overflow.

The parent and normalized incipient phase are evaluated with the shared Module
7 phase evaluator and explicit immutable binary-interaction provenance. The
equilibrium target is:

\[
\ln K_i^{new}=\ln\phi_i^L-\ln\phi_i^V
\]

The optional fixed damping factor applies in log-K space:

\[
\ln K_i^{next}=\ln K_i+\lambda(\ln K_i^{new}-\ln K_i),
\qquad 0 < \lambda \le 1.
\]

`lambda = 1` is the exact historical update. The full difference between the
EOS target and current log K remains the convergence residual; the smaller
damped movement cannot establish convergence. Damping changes only the
numerical path, not the pressure objective or equilibrium equations.

The independently enabled Module 12 vector-secant accelerator is shared with
flash. From consecutive current/target pairs it forms the documented
`tau = -(r^T y)/(y^T y)` proposal in log-K space, subjects it to finite,
residual-history, predicted-improvement, direction, denominator, and step-size
safeguards, and otherwise returns the ordinary fugacity-ratio target. The
accepted or fallback target is then damped exactly once. Each inner iteration
records the acceleration disposition. Outer pressure objectives, trivial-state
rejection, final fugacity equality, and all convergence tolerances continue to
use the raw EOS state and are unchanged. Acceleration is disabled by default.

The normalized incipient fixed point can converge at a pressure that is not a
saturation pressure. Away from the outer root, normalization introduces one
common fugacity mismatch. Consequently the live inner convergence gates are
maximum log-K update and incipient-composition change, both `<= 1e-10`; final
component fugacity equality is required only together with the outer objective.
Every inner iteration, phase root candidate, mechanical classification,
diagnostic, and failure is retained.

### Trivial-state rejection

Successive substitution also has a trivial fixed point at which the incipient
phase *is* the parent phase. There every `K_i = 1`, so both objectives collapse
to `sum(z_i) - 1 = 0` identically, at any single-phase pressure. The objective
therefore cannot distinguish a trivial state from a saturation boundary, and a
trivial state must be rejected before it can supply an outer objective value.

A converged multicomponent inner state is rejected as exactly trivial when
every active `|ln(K_i)| <= 1e-8`, matching the Module 6 trivial-composition
scale. Module 15.2 adds a separate near-trivial same-phase policy. It rejects a
candidate only when all three measured indicators collapse simultaneously:
maximum active `|ln K_i| <= 2e-3`, maximum parent/incipient composition
separation `<= 5e-4`, and selected-root separation `<= 1e-4`. Fugacity equality
alone cannot distinguish this numerical equilibrium branch because the same
phase is necessarily in equilibrium with itself.

The three-way condition is empirical and conservative, not a critical-point
detector. Across 88 frozen valid multicomponent saturation/envelope states the
ordinary minima are much larger. The closest accepted Module 15.1 critical-
region point measures approximately `(3.03e-4, 1.51e-4, 2.43e-4)` in log-K,
composition, and root separation, while the deliberately generated false
collapses measured at most `(1.10e-3, 2.19e-4, 7.46e-5)`. The first two signals
overlap a real near-critical state, so neither is safe alone; the root bound
supplies the observed separation and all three must agree.

Pure or effectively pure feeds are excluded from both multicomponent tests
because `K = 1` and equal compositions are precisely their genuine coexistence
conditions. For one active component, two distinct mechanically stable roots
supply the physical protection.

Rejecting these states can leave a genuine boundary without a usable bracket,
because the non-trivial incipient branch does not always extend past the
saturation pressure on the grid. That is reported as `NOT_FOUND` rather than
resolved; converting a trivial state into a saturation pressure would be worse.

## Outer logarithmic-pressure solve

User bounds must be finite, positive, and strictly ordered. The Wilson estimate
is clipped only for choosing a search center; returned pressure is never forced
into the bounds. A deterministic logarithmic grid evaluates fully converged
inner problems from the lower bound through the Wilson center to the upper
bound. Failed inner evaluations are not usable objective values.

Adjacent usable evaluations with opposite objective signs form candidate
brackets, and a grid point whose objective is already within `1e-8` of zero is
an exact hit. An exact hit also changes sign against its neighbour, so brackets
touching an exact-hit pressure are discarded as the same root seen twice. The
remaining exact hits and brackets are then counted together: more than one
distinct apparent root returns `INCONCLUSIVE`, and none returns `NOT_FOUND`.
Counting the two kinds separately would let one exact hit plus one genuinely
separate bracket pass as a unique answer.

A sign change spanning a failed evaluation is never trusted, so a root can be
missed and honestly reported as `NOT_FOUND`. One bracket is solved in `ln(P)`
with bracketed `brentq`, never Newton alone. The final pressure state is
reconstructed from a fresh, fully converged inner solve rather than borrowing a
partially converged state.

The outer dimensionless objective tolerance is `1e-8`. Pressure endpoints,
objective values, all search evaluations, solver iteration metadata, and the
final reconstruction remain immutable.

## Final convergence and failure policy

A result is `CONVERGED` only when:

- the bracketed pressure solver and final inner problem converge;
- `|F_b|` or `|F_d| <= 1e-8`;
- maximum inner log-K residual and composition change are `<= 1e-10`;
- the incipient composition sum residual is `<= 1e-10`;
- maximum active-component `|ln(f_i^{incipient})-ln(f_i^{parent})| <= 1e-8`;
- parent and incipient roots are mechanically stable;
- a multicomponent state passes the shared exact/near-trivial phase-distinction
  policy;
- pressure and every required value are finite and in-domain;
- no unresolved failure remains.

The result is not converged merely because pressure change is small. Bracketing
failure, multiple apparent roots, inner non-convergence, marginal-only roots,
component underflow, K overflow/underflow, fugacity failure, provenance
mismatch, oscillation, stagnation, or a failed final reconstruction remains
explicitly `NOT_FOUND`, `INCONCLUSIVE`, or `FAILED`.

For a pure component, a valid saturation evaluation requires distinct liquid
and vapor roots; otherwise the identical one-root fugacity ratio would create a
spurious zero objective at every single-phase pressure.

Every reconstructed two-phase state also passes a shared physical phase-role
gate. Outside the existing `1e-8` selected-root distinguishability dead band,
a bubble calculation requires `Z_parent < Z_incipient` and a dew calculation
requires `Z_parent > Z_incipient`. Roots inside the dead band are treated as
ordering-ambiguous rather than forced into an inequality. A clearly inverted
caller-provided log-K seed is discarded after an evaluable trial and normal
Wilson initialization is used; unusual near-unity seeds are not banned
pre-emptively. If their Newton trajectory later supplies combined evidence of
same-phase collapse, that numerical branch is rejected and the historical
solver retries from normal initialization. Historical inner and Newton
trial/final acceptance use the same phase-distinction and phase-role rules, and
the requested saturation kind is never silently changed.

## Optional Module 15 Newton layer

`saturation_newton_enabled=False` preserves the exact historical workflow
above. When enabled, a local square system of active-component logarithmic
fugacity-equality residuals is attempted before the pressure grid. Its unknowns
are the `m-1` direct incipient simplex coordinates and `ln(P)`. The analytical
Jacobian uses Module 13 fixed-root derivatives, including the explicit
derivative of `-ln(w_i)`, and `numpy.linalg.solve` with a `1e12` condition
safeguard.

Every step is globalized by deterministic residual-norm backtracking and must
preserve pressure bounds, the open active simplex, mechanical root identity,
phase role, and the existing trivial-state exclusion. Full raw equilibrium
residual convergence is required; a small step never suffices. A converged
candidate, including one produced on the final permitted iteration, is freshly
reconstructed and subjected to all Module 8 physical
gates. Any unsuitable seed, invalid derivative, singular/ill-conditioned
Jacobian, rejected line search, root ambiguity, non-convergence, or final-gate
failure invokes the complete historical solver. See
`NEWTON_SATURATION_DESIGN.md` for equations, controls, verification, and the
benchmark.

## Limitations

This is a deterministic isolated-pressure solver using optional fixed damping,
optional safeguarded vector-secant acceleration, an optional local safeguarded
Newton first layer, and finite search bounds.
Neither numerical control is a convergence guarantee. The solver does not prove
that all roots have been found, trace retrograde branches, identify the critical
point, or replace experimental validation and authoritative property or
binary-interaction data.
