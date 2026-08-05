# Scientific equations

This document maps the scientific equations currently implemented by
`pvt-phase-simulator` to their Python APIs. Unless stated otherwise,
temperature is in kelvin, pressure is in pascals, and calculations use binary64
(`float`) arithmetic. Mathematical admissibility, local mechanical stability,
and global thermodynamic stability are different concepts throughout.

## Symbols and units

| Symbol | Meaning | Unit |
|---|---|---|
| `T`, `T_c` | temperature and critical temperature | K |
| `P`, `P_c` | pressure and critical pressure | Pa |
| `R` | universal gas constant | J·mol⁻¹·K⁻¹ |
| `omega` | acentric factor | dimensionless |
| `a`, `a_alpha` | PR attraction parameters | Pa·m⁶·mol⁻² |
| `b` | PR co-volume parameter | m³·mol⁻¹ |
| `A`, `B` | dimensionless PR parameters | dimensionless |
| `x_i` | liquid/overall fixed-mixture mole fraction in this project | dimensionless |
| `Z` | compressibility factor | dimensionless |
| `phi`, `phi_i` | fugacity coefficient | dimensionless |
| `f` | fugacity | Pa |

The implementation retains the conventional rounded PR constants
`Omega_a = 0.45724` and `Omega_b = 0.07780` for compatibility with the
project's reference calculations.

## Pure-component parameters

### Reduced temperature

\[
T_r = \frac{T}{T_c}
\]

Meaning: temperature relative to the component critical temperature. It is
dimensionless and implemented by `calculate_reduced_temperature`. Both
temperatures must be finite and strictly positive. This is parameter
construction, not a stability criterion.

### Kappa correlation

\[
\kappa = 0.37464 + 1.54226\omega - 0.26992\omega^2
\]

Meaning: standard PR acentric-factor correlation, dimensionless. Implemented
by `calculate_kappa`. The acentric factor and result must be finite. The
diagnostic layer can warn when use of the resulting alpha correlation is
questionable; no universal applicability limit is imposed.

### Alpha correction

\[
\alpha(T)=\left[1+\kappa\left(1-\sqrt{T_r}\right)\right]^2
\]

Meaning: dimensionless temperature correction to attraction. Implemented by
`calculate_alpha`. The square remains mathematically non-negative even after
the bracket crosses zero, so that region produces a non-blocking model-
applicability diagnostic rather than a validation error.

### Pure `a`, `b`, and `a_alpha`

\[
a = 0.45724\frac{R^2T_c^2}{P_c}
\]

\[
b = 0.07780\frac{RT_c}{P_c}
\]

\[
(a\alpha)_i = a_i\alpha_i
\]

`a` has units Pa·m⁶·mol⁻² and `b` has units m³·mol⁻¹. They are implemented by
`calculate_a_parameter`, `calculate_b_parameter`, and the orchestration in
`calculate_peng_robinson_parameters` or
`calculate_pure_component_mixture_parameters`. Critical properties must be
finite and positive. These definitions build the model; they do not establish
phase stability.

### Dimensionless `A` and `B`

\[
A = \frac{a\alpha P}{R^2T^2}, \qquad
B = \frac{bP}{RT}
\]

Implemented by `calculate_A_parameter` and `calculate_B_parameter`. Both are
dimensionless. Pressure must be finite and non-negative, temperature positive,
and the dimensional parameters positive. At exactly zero pressure, both are
exactly zero.

## Peng–Robinson compressibility cubic

The implemented monic cubic is:

\[
Z^3 + (B-1)Z^2 + (A-3B^2-2B)Z
- (AB-B^2-B^3)=0
\]

Therefore:

\[
c_3=1,\quad c_2=B-1,\quad
c_1=A-3B^2-2B,\quad
c_0=-(AB-B^2-B^3)
\]

`calculate_cubic_coefficients` constructs these dimensionless coefficients.
For a supplied root, `calculate_cubic_residual` evaluates the Horner form:

\[
r(Z)=((c_3Z+c_2)Z+c_1)Z+c_0
\]

`solve_compressibility_roots` retains numerically real roots only after
scale-aware residual checks and conditioning-aware deduplication.
`validate_compressibility_root` additionally requires finite `Z`, `Z > B`, a
scaled residual within `1e-10`, and proximity to an independently solved
admissible root within a scale-aware `1e-9` distance/conditioning tolerance.
These checks establish mathematical admissibility, not mechanical or global
thermodynamic stability.

## Local mechanical derivative

The implementation evaluates the dimensionless sign-equivalent quantity:

\[
D = -\frac{1}{(Z-B)^2}
+\frac{2A(Z+B)}{(Z^2+2BZ-B^2)^2}
\]

`D` has the sign of `(dP/dV)_T` under the PR reduced-variable transformation.
`classify_mechanical_stability` classifies:

- `D < -tolerance`: locally mechanically stable
- `D > tolerance`: locally mechanically unstable
- `|D| <= tolerance`: numerically marginal

The tolerance is 64 times a local float64 rounding scale built from the two
derivative terms. This is local mechanical classification only; it does not
determine global mixture phase stability.

## Pure-fluid fugacity

At a validated PR root:

\[
\ln\phi = Z-1-\ln(Z-B)
-\frac{A}{2\sqrt{2}B}
\ln\left(
\frac{Z+(1+\sqrt{2})B}{Z+(1-\sqrt{2})B}
\right)
\]

\[
\phi=\exp(\ln\phi), \qquad f=\phi P
\]

Implemented by `calculate_log_fugacity_coefficient`,
`calculate_fugacity_coefficient`, and `calculate_fugacity_pa`. Logarithm
arguments and final values must be finite and in-domain; `phi` must be strictly
positive. The low-level functions accept any genuine admissible root, including
a mechanically unstable or marginal one. `calculate_stable_compressibility_result`
first filters local mechanical candidates and, for a pure fluid, selects the
outer candidate with lowest fugacity. That pure-fluid selection is not a
multicomponent phase-stability algorithm.

At exact zero pressure, the implemented limit is `Z = 1`, `ln(phi) = 0`, and
`phi = 1`.

## Classical fixed-mixture rules

### Pair attraction

\[
a_{ij}=\sqrt{(a\alpha)_i(a\alpha)_j}(1-k_{ij})
\]

Implemented authoritatively by
`mixing_rules.calculate_component_pair_attraction_parameter`; the public
mixture-fugacity wrapper delegates to it rather than duplicating the equation.
Units are Pa·m⁶·mol⁻². `k_ij` is dimensionless, symmetric, and exactly zero on
the diagonal. Missing off-diagonal values either default to the explicit
approximation zero or raise, according to `BinaryInteractionPolicy`.

### Mixture attraction and co-volume

\[
(a\alpha)_{mix}=\sum_i\sum_j x_ix_ja_{ij}
\]

\[
b_{mix}=\sum_i x_ib_i
\]

Implemented by `calculate_mixture_a_alpha` and `calculate_mixture_b`.
`(a alpha)_mix` has units Pa·m⁶·mol⁻² and `b_mix` has units m³·mol⁻¹. Mole
fractions must be finite, non-negative, and sum to one within the documented
composition tolerance. The component parameters are re-derived from immutable
property and temperature provenance before aggregation.

### Dimensionless mixture parameters

\[
A_{mix}=\frac{(a\alpha)_{mix}P}{R^2T^2}, \qquad
B_{mix}=\frac{b_{mix}P}{RT}
\]

Implemented by `calculate_mixture_A_parameter` and
`calculate_mixture_B_parameter`. Units and zero-pressure behavior match the
pure definitions.

### Component attraction sum

\[
S_i=\sum_j x_ja_{ij}
\]

Implemented by `calculate_component_attraction_sum`. Units are
Pa·m⁶·mol⁻². Component identity, temperature provenance, and the exact stored
binary-interaction set are validated.

## Mixture component fugacity

For component `i` at an already selected genuine mixture root:

\[
\begin{aligned}
\ln\phi_i={}&\frac{b_i}{b_{mix}}(Z-1)-\ln(Z-B_{mix})\\
&-\frac{A_{mix}}{2\sqrt{2}B_{mix}}
\left[
\frac{2S_i}{(a\alpha)_{mix}}-\frac{b_i}{b_{mix}}
\right]
\ln\left(
\frac{Z+(1+\sqrt{2})B_{mix}}
{Z+(1-\sqrt{2})B_{mix}}
\right)
\end{aligned}
\]

\[
\phi_i=\exp(\ln\phi_i)
\]

Implemented by `calculate_log_component_fugacity_coefficient`,
`calculate_component_fugacity_coefficient`, and
`calculate_mixture_fugacity_coefficients`. Coefficients are dimensionless and
strictly positive after exponentiation. The API validates that `Z` is a root
of the supplied `A_mix`, `B_mix` cubic, but deliberately permits genuine
stable, unstable, and marginal roots. `calculate_mixture_root_fugacity_result`
adds local mechanical status and binary-interaction assumptions; it still does
not calculate global phase stability, phase fractions, or phase compositions.

## Low-pressure shifted variable

When direct subtraction would lose precision, define:

\[
w=Z-1
\]

Substitution into the PR cubic gives:

\[
w^3+(B+2)w^2+(1+A-3B^2)w
+A-B-2B^2-AB+B^3=0
\]

`calculate_compressibility_root_offset` validates the supplied `Z` first. For
`|Z-1| < 10^-4`, it refines the same selected root in `w` using Newton steps
started from the linearized solution. It does not perform phase selection. The
fugacity calculations then use stable forms such as:

\[
\ln(Z-B)=\log1p(w-B)
\]

and:

\[
\log1p(w+(1+\sqrt2)B)-\log1p(w+(1-\sqrt2)B)
\]

The exact zero-pressure branch bypasses division by `B`.

## Euler/Gibbs–Duhem consistency invariant

For the implemented classical mixing rules at fixed composition, the component
fugacity expression satisfies:

\[
\sum_i x_i\ln\phi_i
=Z-1-\ln(Z-B_{mix})
-\frac{A_{mix}}{2\sqrt2B_{mix}}
\ln\left(
\frac{Z+(1+\sqrt2)B_{mix}}
{Z+(1-\sqrt2)B_{mix}}
\right)
\]

The right-hand side is the mixture residual Gibbs-energy departure divided by
`RT` for this PR formulation. Independent binary and ternary tests verify this
identity. It is a thermodynamic consistency invariant for the implemented
fixed-composition equations; by itself it does not prove experimental accuracy
or global phase stability.

## Module 6: mixture phase-stability foundation

This section describes the two Michelsen-style tangent-plane-distance trials
implemented by `phase_stability.py`. The result detects a thermodynamic
tendency to form a distinct trial phase. It does not calculate phase fractions,
final equilibrium compositions, or a flash solution.

### Wilson initial estimates

\[
K_i^{Wilson}=\frac{P_{c,i}}{P}
\exp\left[5.373(1+\omega_i)\left(1-\frac{T_{c,i}}T\right)\right]
\]

`calculate_wilson_k_values` returns finite positive dimensionless estimates in
component order. `T`, `P`, `T_c`, and `P_c` use SI units. The implementation
forms `ln(K_i)` first and rejects float64 exponential overflow or underflow.
Wilson values initialize trials only and are not equilibrium results.

### Trial-composition initialization

For vapor-like and liquid-like trials respectively:

\[
\widetilde w_i^V=z_iK_i,\qquad
\widetilde w_i^L=\frac{z_i}{K_i}
\]

\[
w_i=\frac{\widetilde w_i}{\sum_j\widetilde w_j}
\]

`initialize_trial_composition` evaluates these relations in log space using a
log-sum-exp normalization. This normalization is an explicit solver operation;
the immutable feed composition is not altered. Zero feed fractions remain zero.

Wilson starts are primary. If one Wilson character is inconclusive, bounded
deterministic fallback starts are evaluated only for that character: the feed,
a uniform composition over active components, and component-rich compositions
with `epsilon = 10^-3`. In a component-rich start, `w_i = 1 - epsilon` and the
remainder is distributed over other active components in proportion to their
feed fractions. Equivalent starts are deduplicated within `10^-12`, zero-feed
support is preserved, and no more than 10 starts are used.

### Tangent-plane distance

For the selected homogeneous feed reference:

\[
d_i=\ln z_i+\ln\phi_i(z)
\]

and for a normalized trial composition:

\[
TPD(w)=\sum_iw_i
\left[\ln w_i+\ln\phi_i(w)-d_i\right]
\]

`calculate_tangent_plane_distance` uses compensated `fsum` accumulation and
returns a finite dimensionless result. A component with `z_i=0` must also have
`w_i=0`; its limiting zero contribution is omitted, so `log(0)` is never
evaluated. A positive trial fraction outside the feed support is rejected.

### Successive-substitution update

The trial stores unnormalized weights in log space:

\[
\ln W_i^{new}=\ln z_i+\ln\phi_i(z)-\ln\phi_i(w)
\]

The new weights are normalized before the next EOS evaluation. Every iteration
rebuilds the trial mixture parameters, solves the shared PR cubic, classifies
all roots, and recalculates Module 5 component fugacity coefficients. A
vapor-like trial selects the largest mechanically stable root; a liquid-like
trial selects the smallest. Unstable roots are excluded, and marginal roots
are retained diagnostically rather than used.

### Convergence and trivial solutions

The updated weights are normalized to `w_new`. The primary stationary-
composition residual is:

\[
r_s=\max_i\left|\ln w_i^{new}-\ln w_i^{old}\right|
\]

Normalizing before evaluating this residual makes it invariant to an arbitrary
common scaling of the unnormalized `W_i`. The implementation also tracks
maximum normalized-composition change and TPD change. Default convergence
tolerances are `1e-10`, `1e-10`, and `1e-12` respectively. Iteration history
and failures are immutable. Maximum-iteration,
two-cycle, numerical, provenance, or root-selection failure produces an
inconclusive trial rather than a stable result.

All root candidates and mechanical classifications remain in every iteration.
The largest/smallest-root policy is reapplied rather than enforcing persistent
continuity. A discontinuous selected-root change is recorded diagnostically
using nearest-current-root and scale-aware jump observations; the diagnostic
does not change the chosen root or classify the trial by itself.

A converged solution is marked trivial when:

\[
\max_i|w_i-z_i|\le 10^{-8}
\]

Returning to the feed is recorded separately from finding a distinct trial
composition.

### Stability interpretation

With dimensionless `TPD_STABILITY_TOLERANCE = 1e-8`:

- `UNSTABLE`: at least one distinct converged trial has `TPD < -1e-8`.
- `STABLE`: both required characters have a reliable converged result and
  neither finds a distinct negative TPD below the tolerance.
- `INCONCLUSIVE`: either required character cannot establish a reliable result.

For a character whose Wilson attempt is inconclusive, selection first considers
distinct converged trials with `TPD < -1e-8` and chooses the lowest TPD. If no
such point exists, it chooses the lowest reliable converged result at or above
the negative tolerance. If no reliable attempt exists, the character remains
inconclusive. All failed and successful attempts remain available in immutable
result records.

The feed reference is the mechanically stable homogeneous root minimizing
`sum(z_i ln(phi_i))`; all candidate roots remain visible. This homogeneous-root
comparison and the trial root-size policies do not independently prove global
mixture stability. Bounded deterministic multi-start reduces dependence on two
Wilson starts but does not certify exhaustive global minimization, and none of
these equations supplies a vapor fraction or final phase composition.

## Module 7: stability-gated two-phase flash foundation

`flash.py` calls Module 6 first. A stable feed returns a single-phase result,
an inconclusive stability result remains inconclusive, and only a conclusively
unstable feed enters the two-phase iteration. Rachford–Rice is not treated as
proof of phase splitting.

### Equilibrium ratios and Rachford–Rice

For vapor composition `y`, liquid composition `x`, and vapor fraction `beta`:

\[
K_i=\frac{y_i}{x_i}
\]

\[
F(\beta)=\sum_i
\frac{z_i(K_i-1)}{1+\beta(K_i-1)}=0
\]

Every denominator is evaluated in the algebraically identical, cancellation-free
form `(1 - beta) + beta*K_i`, which adds two non-negative terms for
`0 <= beta <= 1` and `K_i > 0`. Evaluating the literal `1 + beta*(K_i - 1)`
loses the entire denominator when `K_i` falls below the float64 spacing of one:
at `beta = 1` it returns exactly zero for every `K_i` below about `5.6e-17`,
even though the exact denominator is `K_i`.

The implementation requires positive finite denominators and solves a strict
interior root on `0 < beta < 1` with bracketed `brentq`. It retains:

\[
F(0)=\sum_i z_i(K_i-1)
\]

\[
F(1)=\sum_i\frac{z_i(K_i-1)}{K_i}
\]

and uses their signs to distinguish a two-phase root, all-liquid tendency,
all-vapor tendency, and the degenerate `K_i`-near-unity case.

### Phase compositions and balance

\[
x_i=\frac{z_i}{1+\beta(K_i-1)},\qquad y_i=K_ix_i
\]

\[
r_i^{MB}=z_i-[(1-\beta)x_i+\beta y_i]
\]

Raw liquid and vapor sums are checked before normalization. Only discrepancies
within `1e-10` may be normalized, and that action is recorded. Component
material-balance residuals must be within `1e-10` for convergence.

### Fugacity update and residual

At equal phase pressure:

\[
x_i\phi_i^L P=y_i\phi_i^V P
\]

so the undamped log-space update is:

\[
\ln K_i^{new}=\ln\phi_i^L-\ln\phi_i^V
\]

The implemented signed equilibrium residual is:

\[
r_i^{eq}=\ln K_i-[\ln\phi_i^L-\ln\phi_i^V]
=\ln f_i^V-\ln f_i^L
\]

Liquid phases use the smallest mechanically stable PR root and vapor phases use
the largest. All candidates and classifications remain recorded. Marginal and
unstable roots are not used, and root switching is diagnostic rather than
enforced continuation.

A two-phase result converges only when the Rachford–Rice residual is within
`1e-12`, maximum log-K and fugacity-equilibrium residuals are within `1e-8`,
composition-sum and material-balance residuals are within `1e-10`, beta is
strictly physical, and both phase roots are mechanically stable. Beta change
or composition change alone cannot establish convergence. This undamped
successive-substitution implementation is not a bubble-point, dew-point,
phase-envelope, or global multiphase solver.

## Module 8: fixed-temperature saturation pressure

`saturation_pressure.py` calculates one bubble- or dew-pressure boundary at a
specified temperature. It does not trace a phase envelope. Wilson correlations
initialize the deterministic search but are not EOS-equilibrium answers.

### Wilson pressure estimates

Define a component pressure factor:

\[
Q_i=P_{c,i}\exp\left[
5.373(1+\omega_i)\left(1-\frac{T_{c,i}}{T}\right)
\right]
\]

The initial estimates are:

\[
P_{bubble}^{Wilson}=\sum_i z_iQ_i,
\qquad
\frac{1}{P_{dew}^{Wilson}}=\sum_i\frac{z_i}{Q_i}
\]

These finite positive values only center the logarithmic pressure search.

### Bubble pressure

At the bubble point the parent liquid remains `x = z`, and an infinitesimal
vapor phase appears. Fugacity equality gives:

\[
z_i\phi_i^L P=y_i\phi_i^V P,
\qquad
K_i=\frac{y_i}{z_i}=\frac{\phi_i^L}{\phi_i^V}
\]

The inner iteration normalizes `y_i` proportional to `z_i K_i`, evaluates the
largest mechanically stable vapor root, and updates
`ln(K_i) = ln(phi_i^L) - ln(phi_i^V)`. The outer objective is:

\[
F_b(P)=\sum_i z_iK_i(P)-1
\]

The parent liquid always uses the smallest mechanically stable root.

### Dew pressure

At the dew point the parent vapor remains `y = z`, and an infinitesimal liquid
phase appears:

\[
x_i\phi_i^L P=z_i\phi_i^V P,
\qquad
K_i=\frac{z_i}{x_i}=\frac{\phi_i^L}{\phi_i^V}
\]

The inner iteration normalizes `x_i` proportional to `z_i / K_i`, evaluates
the smallest mechanically stable liquid root, and applies the same
fugacity-ratio log-K update. The outer objective is:

\[
F_d(P)=\sum_i\frac{z_i}{K_i(P)}-1
\]

The parent vapor always uses the largest mechanically stable root.

### Pressure solve and convergence

Only fully converged inner evaluations may supply an outer objective. The
solver samples a deterministic logarithmic pressure grid, preserves a genuine
sign-changing bracket, and applies `scipy.optimize.brentq` in log pressure. It
then reconstructs the complete state at the final pressure.

Both objectives vanish identically when every `K_i` equals one, because the
incipient phase is then the parent phase and `sum(z_i K_i^{\pm1}) = sum(z_i)`.
That trivial fixed point exists at single-phase pressures, so a converged
multicomponent inner state with every active `|ln(K_i)| <= 1e-8` is rejected
before it can supply an objective value. A pure component is exempt: `K = 1` is
its genuine coexistence condition, and there the requirement of two distinct
mechanically stable roots plays the same role.

A result is `CONVERGED` only when the objective is within `1e-8`, the maximum
log-K residual and incipient-composition change are each within `1e-10`, the
incipient sum residual is within `1e-10`, the maximum log-fugacity equilibrium
residual is within `1e-8`, both selected roots are mechanically stable, and
the pressure is finite and positive. Exact pure-component coexistence also
requires distinct liquid and vapor roots. Failure to find one trustworthy
bracket returns `NOT_FOUND`; ambiguous roots or numerical failures remain
`INCONCLUSIVE` or `FAILED` evidence rather than being converted to a boundary.

Bubble and dew conditions correspond respectively to the Rachford--Rice limits
`beta -> 0` and `beta -> 1`. The pressure is not obtained by forcing those
endpoint values: pressure, incipient composition, PR roots, and component
fugacities must be self-consistent together. Root size is a local branch policy,
not proof of global thermodynamic stability. The implementation does not trace
critical or retrograde regions and makes no global-convergence claim.
