# Independent derivative verification

## Purpose and conclusion boundary

Module 14 independently verifies the local fixed-root Peng--Robinson
derivatives introduced in Module 13 before any equilibrium solver may consume
them. No production thermodynamic or solver source is changed.

Passing Module 14 verifies local analytical derivative implementation within
the tested smooth fixed-root domain. It does not prove global phase smoothness,
root-selection differentiability, critical-point correctness, Newton global
convergence, or experimental physical accuracy.

## Independence hierarchy

Verification deliberately differs from the production derivative code:

1. Exact pressure/log-pressure chain rules and independently evaluated cubic
   partials check algebraic identities.
2. `tests/derivative_reference.py` contains separately written complex-safe PR
   algebra for alpha, `a*alpha`, pair/mixing quantities, and `A/B`. It duplicates
   published rounded PR constants intentionally and does not import
   `eos.derivatives`.
3. Complex-step is used only inside that isolated algebra for temperature,
   pressure, and tangent-simplex coordinates. No root, sorting, comparison,
   admissibility, mechanical classification, fugacity, or phase-selection path
   receives a complex number.
4. Ordinary real value APIs are recomputed at positive and negative
   perturbations. Central differences use `h`, `h/2`, `h/4`, and `h/8`, and the
   declared primary reference is
   `D_R=D(h/2)+[D(h/2)-D(h)]/3`.
5. Tests inspect multi-step error behavior. Smooth nonlinear cases show the
   expected initial second-order reduction; exact linear or quadratic cases
   are allowed to enter the float64 roundoff floor immediately.

The normal focused command is:

```console
uv run pytest tests/test_derivative_verification.py -q
```

The deterministic extended report is:

```console
uv run python -m tests.run_derivative_verification
```

Measured wall runtimes on the final verification environment were 2.502
seconds for the focused pytest suite and 1.162 seconds for the extended report.
The complete 760-test repository run took 191.37 seconds of pytest time and
193.169 seconds wall time.

## Root tracking and exclusions

Every finite-difference `Z` or `ln(phi_i)` evaluation starts from a named
baseline root. A perturbed candidate is accepted only if:

- the number of admissible real roots is unchanged;
- the same sorted branch is also the uniquely nearest continuation;
- nearest-root distance is not ambiguous;
- `Z>B` remains true; and
- mechanical classification is unchanged.

An inconsistency raises a verification-only `RootTrackingError`; it is never
forced into an accuracy comparison. Tests demonstrate rejection when a
three-root state is perturbed into a single-root state.

There is one planned exclusion: the ethane simplex coordinate in the
`(0.6, 0.0, 0.4)` ternary state cannot be perturbed centrally without leaving
the physical simplex. It is classified as `composition_boundary` and verified
separately with a labeled second-order forward formula. There are no root
ambiguity, root-count, admissibility, or mechanical-classification exclusions
in the ordinary smooth matrix.

## Step-size policy

- Pressure: `h=10^-3 P`, followed by three halvings.
- Log pressure: `h=10^-3`, followed by three halvings; pressure is reconstructed
  as `P exp(delta)`.
- Temperature: `h=10^-3 T`, followed by three halvings.
- Composition: `h=min(10^-3, 0.2 min(x_k,x_r))`, followed by three halvings.
- Complex-step: imaginary step `10^-30` in isolated complex-safe algebra.
- Near-singular `A` study: `h=10^-7`, followed by three halvings.

These rules are fixed by variable scale and are not tuned by component, root,
or desired result.

## Deterministic case matrix

The 21 explicit specifications comprise nine pure-temperature cases and twelve
EOS/root cases. Methane, ethane, and propane each cover subcritical,
moderately near-critical but differentiable, and supercritical pure
temperatures. EOS states cover pure, CH4/C2, CH4/C3, and CH4/C2/C3 systems;
balanced, asymmetric, near-pure, zero-fraction, and reversed order
compositions; low, moderate, and high pressure; single-root states; and
separated liquid-like and vapor-like roots of a three-root state.

Every public derivative output is mapped: pure alpha and `a*alpha`; pair terms,
component attraction sums, `a_mix`, `b_mix`, `A`, and `B`; pressure,
log-pressure, temperature, and simplex coordinates; fixed-root `Z`; and the
complete ordered `ln(phi_i)` derivative matrix.

## Tolerance policy

Assertions use `abs_error <= abs_tol + rel_tol*max(|analytical|,|reference|)`.
This makes absolute error authoritative near a true zero. Tolerances were set
after observing float64 truncation, roundoff, and conditioning behavior, with
separate classes for complex/algebraic mixing checks, Richardson root/fugacity
checks, and the near-singular study. Production tolerances are unchanged.

| Family | Absolute tolerance | Relative tolerance |
| --- | ---: | ---: |
| pure alpha / a-alpha T | `1e-13` | `5e-11` |
| A, B, mixing T/composition | `1e-11` or tighter | `5e-10` |
| Z pressure | `2e-9` | `5e-7` |
| Z temperature | `3e-9` | `5e-7` |
| Z composition | `1e-7` | `5e-7` |
| lnphi pressure | `2e-9` | `5e-7` |
| lnphi temperature | `4e-9` | `5e-7` |
| lnphi composition | `2e-7` | `5e-7` |
| cubic identity | `3e-15` | `0` |

## Observed error metrics

The extended matrix contains 774 scalar comparisons. Counts include separate
independent routes when the same analytical output is checked by both
complex-step and Richardson recomputation.

| Family | Scalars | Maximum absolute error | Maximum meaningful relative error | Worst case |
| --- | ---: | ---: | ---: | --- |
| pure alpha/a-alpha T | 36 | `2.8874472257633954e-15` | `1.3856105312118763e-12` | methane near-critical alpha T |
| A derivatives | 111 | `1.3344880755994382e-13` | `1.1257003285055172e-12` | high-pressure CH4/C2 composition |
| B derivatives | 111 | `3.464589726220879e-14` | `8.649549626649329e-13` | high-pressure CH4/C2 composition |
| mixing temperature | 216 | `9.90960785651751e-16` | `8.9648070089676e-13` | CH4/C3 liquid-like pair term |
| mixing composition | 110 | `1.2312373343092986e-13` | `5.404947773561071e-13` | CH4/C3 liquid-like a-mix |
| Z pressure / lnP | 24 | `5.676636938289903e-10` | `5.746235796403413e-10` | CH4/C3 vapor-like Z-lnP |
| Z temperature | 12 | `1.474964827358205e-9` | `1.1184211268438702e-7` | CH4/C3 vapor-like |
| Z composition | 12 | `5.953649040435494e-8` | `2.5352797400681356e-8` | CH4/C3 vapor-like |
| lnphi pressure / lnP | 50 | `9.0153684517702e-10` | `1.1962179773894886e-9` | CH4/C3 vapor-like propane lnP |
| lnphi temperature | 25 | `2.2481950988362254e-9` | `2.2546317427705644e-7` | CH4/C3 vapor-like propane |
| lnphi composition | 31 | `8.223608194413146e-8` | `3.5228379552877544e-8` | CH4/C3 vapor-like propane |
| differentiated cubic identity | 36 | `1.6653345369377348e-16` | near-zero: not used | ternary balanced composition |

The largest ordinary smooth-domain absolute discrepancy is
`8.223608194413146e-8` for the propane log-fugacity composition derivative on
the vapor-like CH4/C3 three-root branch. It is a Richardson/root-conditioning
error and is well within the predeclared combined tolerance.

## Near-singular conditioning study

At fixed `B=0.0778`, the selected root was followed through five `A` values:

| A | abs(F_Z) | abs(dZ/dA) | analytical/reference absolute error |
| ---: | ---: | ---: | ---: |
| `0.456` | `1.4418569993932484e-2` | `20.934997566231353` | `4.051169000263144e-8` |
| `0.457` | `4.740059758105819e-3` | `57.03615735378339` | `1.616905507262345e-7` |
| `0.4572` | `1.6055929890594345e-3` | `157.5995019981951` | `1.945511485246243e-7` |
| `0.45723` | `8.888501460958542e-4` | `277.81553552855837` | `7.179405656643212e-7` |
| `0.45724` | `5.834394344114147e-4` | `417.48810726055325` | `2.030393488894333e-7` |

As `|F_Z|` falls, derivative magnitude rises and the finite-difference
sensitivity increases. Error need not be monotone because truncation and root
roundoff compete. The exact repeated-root construction still returns
`applicable=False`, `derivative=None`, and an explicit reason. This is not a
critical-point solver.

## Permutation and adversarial checks

The full `3 x 2` log-fugacity composition Jacobian is covariant after mapping
both component rows and independent-coordinate columns by component name.
Tests also demonstrate detection of a missing `P` factor, a missing quadratic
factor of two, wrong simplex sign, omitted implicit `Z` contribution, omitted
explicit composition contribution, wrong temperature sign, component-order
mismatch, and a transposed Jacobian. No production mutation is retained.

## Limitations

The verification matrix is deterministic but finite. It excludes global root
switches, unresolved repeated roots from normal accuracy claims, phase-boundary
smoothness, nonzero binary-interaction data, property uncertainty, experimental
validation, and any Newton convergence behavior. Those exclusions are part of
the scientific contract, not evidence that the omitted operations are
differentiable.
