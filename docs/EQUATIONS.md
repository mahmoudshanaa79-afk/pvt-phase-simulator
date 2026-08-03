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
