# Module 7 two-phase flash design

This module is an isothermal-isobaric Peng–Robinson two-phase flash
foundation. It does not calculate bubble points, dew points, phase envelopes,
depletion paths, separator trains, or volume translation.

## Stability gate

Every high-level flash call first runs the Module 6 tangent-plane-distance
analysis with the same feed, temperature, pressure, and binary-interaction
policy. A `STABLE` result returns a single-phase result without inventing a
second phase. An `INCONCLUSIVE` result remains inconclusive. Only `UNSTABLE`
permits the two-phase iteration to start. Rachford–Rice is a material-balance
equation and is never used by itself to prove phase splitting.

## Equilibrium ratios and initialization

For component `i`:

\[
K_i=\frac{y_i}{x_i}
\]

At equal phase pressure, fugacity equilibrium requires:

\[
x_i\phi_i^L P=y_i\phi_i^V P
\]

and therefore:

\[
K_i=\frac{\phi_i^L}{\phi_i^V}
\]

The default initial `K_i` values are the existing Module 6 Wilson estimates.
They are initialization only. The implementation stores `ln(K_i)` and updates
it from `ln(phi_i^L) - ln(phi_i^V)` without silently clamping K-values.

## Rachford–Rice solution

For overall composition `z` and vapor fraction `beta`:

\[
F(\beta)=\sum_i\frac{z_i(K_i-1)}{1+\beta(K_i-1)}=0
\]

Each denominator must be strictly positive. The theoretical denominator bounds
are intersected with the physical closed interval `[0, 1]`; an actual two-phase
root must satisfy `0 < beta < 1`. For positive finite K-values the physical
interval is denominator-safe, and:

\[
F(0)=\sum_i z_i(K_i-1),\qquad
F(1)=\sum_i\frac{z_i(K_i-1)}{K_i}
\]

Also:

\[
F'(\beta)=-\sum_i
\frac{z_i(K_i-1)^2}{[1+\beta(K_i-1)]^2}\le0
\]

Each denominator is evaluated as `(1 - beta) + beta*K_i`, which is
algebraically identical to `1 + beta*(K_i - 1)` but sums two non-negative
terms over the physical interval. The literal form cancels: at `beta = 1` it
evaluates to exactly zero for every `K_i` below about `5.6e-17`, although the
true denominator is `K_i > 0`. The transformed form returns `K_i` there and
keeps extreme K-value spreads solvable instead of rejecting them as a
denominator failure.

The implementation uses bracketed `scipy.optimize.brentq`, never an
unbracketed Newton iteration. With endpoint tolerance `1e-12`:

- `TWO_PHASE_ROOT`: `F(0) > tolerance` and `F(1) < -tolerance`;
- `ALL_LIQUID`: `F(0) <= tolerance`, including a beta-zero boundary;
- `ALL_VAPOR`: `F(1) >= -tolerance`, including a beta-one boundary;
- `DEGENERATE`: every active `ln(K_i)` is within `1e-12` of zero;
- `INCONCLUSIVE`: invalid bounds or a bracketed numerical failure.

Input validation failures raise `ValueError`; they are not physical phase
classifications. Endpoint values, admissible bounds, root residual, and solver
metadata remain in the immutable result.

## Phase compositions and material balance

At a physical beta:

\[
x_i=\frac{z_i}{1+\beta(K_i-1)},\qquad y_i=K_ix_i
\]

Zero-feed components remain zero. The raw sums are checked before any
normalization. Renormalization is permitted only when each raw sum differs from
one by at most `1e-10`; it is recorded explicitly. Larger inconsistencies are
rejected. Final component material-balance residuals use:

\[
r_i^{MB}=z_i-[(1-\beta)x_i+\beta y_i]
\]

and must be within `1e-10` for convergence.

## Phase roots and fugacity

Every iteration rebuilds the liquid mixture at `x` and vapor mixture at `y`
using the same immutable component order and binary-interaction provenance.
All admissible PR roots are mechanically classified:

- liquid: smallest mechanically stable root;
- vapor: largest mechanically stable root.

Unstable and marginal roots remain in diagnostics but are not selected. Module
5 evaluates component fugacity coefficients at the selected genuine roots.
Root continuity is observed using the Module 6 discontinuous-switch diagnostic;
it is not enforced and root size alone is not a global-stability proof.

## Successive substitution and convergence

One successive-substitution iteration performs:

1. solve Rachford–Rice using current `ln(K)`;
2. calculate and validate `x`, `y`, and material balance;
3. evaluate liquid and vapor roots and component `ln(phi)` values;
4. form the equilibrium update
   `ln(K_i^new) = ln(phi_i^L) - ln(phi_i^V)`;
5. record all numerical and thermodynamic residuals;
6. repeat using either the historical undamped target or a fixed damped step.

With `successive_substitution_damping_factor = lambda`, the next iterate is

\[
\ln K_i^{next}=\ln K_i+\lambda(\ln K_i^{target}-\ln K_i),
\qquad 0 < \lambda \le 1.
\]

The default `lambda = 1` returns the target directly and exactly preserves the
historical numerical path. Damping is performed in log space, so it cannot
create a non-positive K-value. It may reduce overshoot or oscillation, but it is
a robustness control rather than acceleration and is not a proof of
convergence.

The signed log-space equilibrium residual is:

\[
r_i^{eq}=\ln(K_i)-[\ln(\phi_i^L)-\ln(\phi_i^V)]
\]

This is equivalent to `ln(f_i^V) - ln(f_i^L)` for active components. Component
fugacities are stored as `x_i phi_i^L P` and `y_i phi_i^V P`.

A result is `CONVERGED` only when all of these hold simultaneously:

- maximum absolute log-K/equilibrium residual `<= 1e-8`;
- Rachford–Rice residual `<= 1e-12`;
- maximum material-balance residual `<= 1e-10`;
- liquid and vapor sum residuals `<= 1e-10`;
- beta is strictly inside `(0, 1)`;
- both selected roots are mechanically stable;
- all required quantities are finite;
- no unresolved failure exists.

The convergence gate uses the full target residual above, never the smaller
damped movement. Beta change and maximum phase-composition change are tracked diagnostically but
cannot establish convergence by themselves. Exact repeated states before full
convergence are classified as stagnation; alternating repeated states are
classified as oscillation. Maximum-iteration, invalid Rachford–Rice status,
root-selection failure, provenance mismatch, exponent overflow/underflow, or
fugacity failure returns a preserved non-converged or failed result. Damping is
opt-in; the default remains undamped.

## Result interpretation and limitations

The result distinguishes stable single phase, converged two phase, and
inconclusive calculation. Single-phase results preserve the selected feed root
and feed fugacity coefficients but leave beta and phase-composition fields
absent. Failed two-phase attempts are never converted into stable results.

Successful numerical convergence establishes consistency with the implemented
PR model and tolerances. It does not prove exhaustive global minimization,
experimental accuracy, or industrial reliability. Component properties and
binary interactions still require authoritative engineering validation.
