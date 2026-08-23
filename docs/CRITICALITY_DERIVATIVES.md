# Mixture Criticality Derivatives and Local Stability Curvature

## 1. Motivation and scope

Module 19 evaluates the local thermodynamic quantities that a later
critical-point algorithm will need. At a specified temperature, pressure, and
mixture composition it calculates the composition-tangent Gibbs Hessian, its
softest eigenmode, and the third derivative along that mode.

Module 19 does **not** calculate a critical point. It does not iterate
temperature or pressure and it does not solve criticality residuals. Module 20
will own that separate task.

## 2. Criticality is not phase coalescence

Small differences between liquid and vapor compositions or compressibility
roots are useful phase-distinguishability diagnostics. They are not the local
mixture criticality conditions. Module 19 instead evaluates

```text
lambda_min = smallest eigenvalue of the tangent Gibbs Hessian
C = D^3(g/RT)[d,d,d]
```

where `d` is the normalized physical composition direction associated with
`lambda_min`. At an ordinary mixture critical point both quantities vanish.
No such state is claimed merely because two phase roots approach one another.

## 3. Gibbs and tangent-plane local expansion

At fixed `T` and `P`, the dimensionless chemical potential contains
`ln(x_i) + ln(phi_i)` plus common terms that cancel in chemical-potential
differences. At the parent composition `z`, the tangent-plane distance is zero
and its first tangent derivative vanishes. Along a normalized direction `d`
with `sum(d_i)=0`, the local expansion is

```text
TPD(z + epsilon d)
  = 1/2 lambda_direction epsilon^2
  + 1/6 C_direction epsilon^3
  + O(epsilon^4).
```

The production TPD iteration is unchanged. Focused tests use the existing TPD
scalar as an independent integrated check of the new local derivatives.

## 4. Active composition space

Terms such as `1/x_i` are singular at zero mole fraction. The evaluator first
forms a deterministic active set in original component order. Zero-fraction
components are reported as inactive, omitted from the derivative space, and
given zero entries when the physical direction is mapped back to full order.
If fewer than two active components remain, mixture-composition criticality is
reported as not applicable; no zero-dimensional Hessian is invented.

## 5. Direct simplex coordinates and reduced gradient

Choose an explicit reference component `r`. The independent coordinates are
`w_j=x_j` for `j != r`, with

```text
x_r = 1 - sum_j w_j.
```

The reduced chemical-potential gradient is

```text
q_j = ln(x_j phi_j) - ln(x_r phi_r).
```

Differentiating gives the direct-coordinate Hessian

```text
H_w[j,k]
  = delta_jk/x_j + 1/x_r
  + d ln(phi_j)/dw_k - d ln(phi_r)/dw_k.
```

The `ln(phi)` columns come from the audited Module 13 analytical fixed-root
composition API. Module 19 does not finite-difference these first derivatives
or duplicate Peng-Robinson fugacity algebra.

## 6. Deterministic orthonormal tangent basis

Let `C_r` contain columns `e_j-e_r`. A reduced QR factorization of the canonical
last-reference form `C_n` produces `Q` with

```text
1^T Q = 0
Q^T Q = I.
```

Each QR column is signed so the first numerically tied largest-magnitude entry
is positive. This exact tie rule makes the basis reproducible. For a different
direct reference, the coordinate map is

```text
M = (C_r^T C_r)^-1 C_r^T Q,
```

because `C_r M = Q`. Therefore the orthonormal physical Hessian is

```text
H = M^T H_w M,
```

and `eta^T H eta` equals the original quadratic form for `dx=Q eta`. Tests use
multiple references and component permutations to show that the eigenvalue
spectrum and physical criticality invariants do not acquire reference-component
physics.

## 7. Symmetry policy

A Gibbs Hessian is symmetric. Module 19 records

```text
symmetry_defect = max(abs(H - H^T))
```

before any symmetrization. The allowed defect is `1e-8` times
`max(1,max(abs(H)))`. A defect within that scale is retained diagnostically and
the symmetric part is passed to `numpy.linalg.eigh`. A larger defect returns
`SYMMETRY_UNRELIABLE`; it is not hidden by eigendecomposition. Synthetic
mutations cover both sides of this policy. Representative PR defects are zero
for the two binary cases and `2.22e-16` for the tested ternary state.

## 8. Soft eigenmode, uniqueness, and orientation

`numpy.linalg.eigh` supplies ordered eigenpairs of the symmetric tangent
Hessian. `lambda_min` is the smallest algebraic eigenvalue, so unstable
homogeneous states may legitimately have a negative value. The tangent-basis
eigenvector `v` and full active direction `d=Qv` satisfy

```text
v^T H v = lambda_min
sum(d_i) = 0
||d||_2 = 1.
```

For more than two active components, the gap `lambda_2-lambda_1` must exceed
`1e-8*max(1,max(abs(lambda)))`. Otherwise the evaluator returns
`CRITICAL_MODE_DEGENERATE` rather than selecting an arbitrary direction. A
binary tangent space is one-dimensional and needs no gap check.

If a previous full physical direction is supplied, the new direction is
oriented for positive dot product with it. Otherwise the first numerically tied
largest-magnitude component is made positive. Reversing `d` leaves `lambda_min`
unchanged and reverses `C`; deterministic orientation restores a reproducible
diagnostic sign.

## 9. Cubic derivative with the base direction fixed

The production cubic derivative defines

```text
kappa(s) = d^T H(x + s d) d
C = dkappa/ds at s=0.
```

The base direction `d` is held fixed at every sample. The evaluator does not
recompute a soft eigenvector at `x+s*d`, so eigenvector rotation is not mixed
into the thermodynamic third derivative.

Module 13 does not expose an audited complete second-composition-derivative
tensor. Module 19 therefore differentiates the analytical Hessian with centered
differences and second-order Richardson extrapolation:

```text
D(h)   = [kappa(+h)   - kappa(-h)]   / (2h)
D(h/2) = [kappa(+h/2) - kappa(-h/2)] / h
C_R    = [4 D(h/2) - D(h)] / 3.
```

The result records the requested, base, and refined steps, all four sampled
curvatures and roots, both raw estimates, `C_R`, `abs(C_R-D(h/2))`, and the
number of rejected step levels.

## 10. Boundary and root-continuity safeguards

The exact symmetric open-simplex bound is

```text
h_boundary = min_i x_i/abs(d_i), for d_i != 0.
```

The initial step is the smaller of `1e-3` and one quarter of this bound. Invalid
compositions are rejected, never clipped. A trace-component test produces the
expected large ideal curvature while keeping every sample positive and finite.

At the base state the supplied root is matched to its sorted cubic-root index.
Every directional sample must preserve the number and mechanical
classifications of the roots, retain an unambiguous closest continuation, and
retain the same indexed branch. The Module 13 derivative must remain
applicable. Failure halves `h` up to the documented limit; persistent failure
returns `CUBIC_DERIVATIVE_UNAVAILABLE`. No derivative evaluates different
thermodynamic branches on opposite sides.

## 11. APIs and structured results

`calculate_fixed_root_mixture_criticality` is the primary local evaluator. Its
compressibility factor is explicit and no selection operation is
differentiated. `calculate_stable_root_mixture_criticality` first reuses Module
5's lowest-residual-Gibbs homogeneous parent selection, then calls the same
fixed-root evaluator. `criticality_residual_pair` returns
`(lambda_min,C)` only for a fully applicable result; it performs no solve.

The frozen result retains state and component mapping, root policy and selected
root, basis identity and values, direct and tangent Hessians, raw symmetry
evidence, eigensystem, mode gap, oriented active/full directions, cubic value
and convergence diagnostics, applicability, status, and reason.

## 12. Synthetic verification

With `ln(phi_i)=0`, the direct Hessian exactly reduces to

```text
H_w[j,k] = delta_jk/x_j + 1/x_r.
```

Tests verify this formula, transformation, positive definiteness, basis
properties, and permutation-invariant spectrum. A polynomial
`g(s)=a*s^2/2+b*s^3/6+c*s^4/24` has `kappa(s)=a+b*s+c*s^2/2`; the generic
Richardson helper recovers `a` and `b`, including the synthetic critical case
`a=b=0,c>0`.

Adversarial matrices verify small/large antisymmetry handling and degenerate
soft modes. Synthetic callbacks verify step reduction and structured rejection
at root-continuity boundaries. Direction reversal verifies the sign parity of
the cubic term.

## 13. Peng-Robinson verification

Regular zero-`kij` CH4/C2, CH4/C3, and CH4/C2/C3 states return finite Hessians,
small symmetry defects, the expected tangent dimension, finite eigenvalues,
and deterministic results. At 280 K and 3 MPa for composition 0.5/0.3/0.2
CH4/C2/C3, representative results are

```text
eigenvalues = (2.3158179770, 4.1235683652)
d = (0.8049652960, -0.5209020475, -0.2840632485)
C = 0.5032413494
symmetry_defect = 2.22e-16.
```

The production Hessian is independently compared with Richardson finite
differences of `q_j` for CH4/C2, CH4/C3, and CH4/C2/C3. The production cubic is
compared with a separate five-point curvature stencil. The local TPD expansion
error decreases across `epsilon=2e-3,1e-3,5e-4`, as expected before
floating-point cancellation dominates.

The worst Hessian differences are `6.52e-11` absolute and `1.66e-9` relative,
both from the CH4/C3 case. The independent five-point cubic value differs by
`1.89e-11` absolute (`3.77e-11` relative). The corresponding TPD expansion
errors are `7.98e-12`, `4.99e-13`, and `3.11e-14`. Reducing the production base
step from `2e-3` to `1e-3` changes the Richardson result from `0.503241349350`
to `0.503241349395` and reduces its internal error estimate from `2.40e-6` to
`6.00e-7`.

Permutation tests compare spectra, `lambda_min`, aligned physical directions,
and `abs(C)`. Reference tests build the same state using first and last direct
reference components and compare the final orthonormal invariants.

## 14. Near-critical diagnostic

The existing 50/50 CH4/C3 Module 18 bubble trace is used only as a diagnostic
path. From its 210 K initial state to its authoritative near-critical stop near
320.855 K, phase-root separation falls from about `0.63353` to `0.01175` while
the stable-parent `lambda_min` falls from about `1.41812` to `0.00147945`.
The intermediate state near 319.965 K has separation `0.02538` and
`lambda_min=0.00686359`. This is physically plausible local-softening evidence,
not a monotonicity rule, critical temperature, or critical pressure claim.

## 15. Limitations and relationship to Module 20

The analysis is local, float64, fixed-root, and restricted to the active
interior simplex. Its cubic derivative is numerical, though it differentiates
an analytical Hessian. Root coalescence, ambiguous continuation, large Hessian
antisymmetry, degenerate soft modes, and insufficient symmetric composition
room are explicit non-applicability conditions. Validation currently covers
the repository's verified methane, ethane, and propane properties with the
default zero interactions; it is not a universal mixture-criticality
certificate.

Module 20 may use `(lambda_min,C)` as two residuals in `ln(P),ln(T)` at fixed
overall composition. That solver does not exist in Module 19.
