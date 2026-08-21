# Module 15 safeguarded Newton saturation design

## Purpose and scope

Module 15 adds an optional local derivative-based corrector ahead of the
historical Module 8 saturation solver. It changes the numerical method, not the
Peng--Robinson equations. `saturation_newton_enabled` defaults to `False`; in
that state the public entry point returns directly into the unchanged
historical implementation and performs no Newton or derivative evaluation.

Newton is not a global solver, critical-point solver, or replacement for the
bracketed pressure search. Any rejected or failed Newton attempt falls back to
the complete historical path, including Module 12 acceleration and Module 11
damping when those independent controls are enabled.

## Square nonlinear system

Let the fixed parent composition be `z`, the normalized incipient composition
be `w`, and let `m` be the number of strictly positive feed components. Only
those active components enter the system. The last active component in the
input order is the explicit reference `r`. The unknown vector is

```text
q = (u_0, ..., u_(m-2), p)
u_k = w_k                         (k != r)
w_r = 1 - sum(u_k)
p = ln(P),  P = exp(p)
```

There are `m-1` composition coordinates and one pressure coordinate. For every
active component the dimensionless residual is

```text
R_i = ln(z_i) + ln(phi_i^parent)
      - ln(w_i) - ln(phi_i^incipient).
```

The common `ln(P)` in the two dimensional fugacities cancels, but pressure
continues to affect both fugacity coefficients. Bubble calculations use a
liquid parent and vapor incipient phase; dew calculations use a vapor parent
and liquid incipient phase. This produces exactly `m` equations in `m`
unknowns.

Direct simplex coordinates match Module 13 without a transformation or hidden
chain rule. Every active fraction must remain strictly positive. An invalid
proposal is rejected by the line search; it is never clipped or silently
renormalized into the simplex.

## Active components and pure specialization

Zero-feed components are removed before any logarithm, residual equation, or
Jacobian row is formed. Their original positions are restored with exact zero
incipient fractions during final reconstruction. Binary-interaction input is
validated in the full component system before being restricted to the active
system. A ternary state with one zero feed fraction is therefore physically
equivalent to the corresponding binary state.

For `m=1`, `q=(ln(P))`; there are no composition columns. The scalar residual
is the log-fugacity-coefficient difference between the distinct smallest and
largest mechanically stable roots. A one-root state is rejected. A
near-multiple root for which Module 13 reports derivatives as non-applicable is
also rejected and sent to historical fallback.

## Analytical Jacobian

The pressure column uses the verified Module 13 log-pressure derivatives:

```text
dR_i/dln(P) = dln(phi_i^parent)/dln(P)
              - dln(phi_i^incipient)/dln(P).
```

For an incipient simplex coordinate `u_k`, the fixed parent contributes no
composition term. The complete column is

```text
dR_i/du_k = -(delta(i,k) - delta(i,r))/w_i
             - dln(phi_i^incipient)/du_k.
```

The first term is the explicit derivative of `-ln(w_i)`. It is intentionally
separate from the residual fugacity-coefficient derivative and is covered by a
targeted omission-sensitive test. Module 13 derivatives are consumed only
after Module 14's independent verification passed.

The assembled saturation Jacobian has its own independent verification. Tests
perturb each complete Newton coordinate, recompute the complete residual on
the same root branches at `h` and `h/2`, and compare the analytical matrix with
the second-order Richardson estimate. The matrix covers binary bubble/dew,
ternary bubble/dew, pure, near-pure, and component-permuted cases. Root count,
classification, phase role, and nearest-root correspondence must remain
continuous for every perturbed state.

## Linear solve and globalization

Each iteration solves `J delta_q = -R` with `numpy.linalg.solve`; an inverse is
never formed. The residual and Jacobian, condition number, and step must all be
finite. The default maximum allowed 2-norm condition number is `1e12`.
Singular solves and stronger ill-conditioning reject the attempt.

The merit function is `||R||_infinity`. Deterministic backtracking starts at
`alpha=1` and multiplies by `0.5`. It stops after 20 rejected reductions or
before the factor would fall below `1e-6`. A trial is accepted only when:

- log pressure is finite and inside the configured bounds;
- every active composition is strictly inside the simplex;
- both phase states and fixed-root derivatives are valid;
- root count and mechanical classifications are unchanged;
- each selected root is the unambiguous nearest continuation of its prior root;
- the multicomponent candidate is not the established trivial `K~=1` state;
- and `||R_trial||_infinity < ||R_current||_infinity`.

Root merger/split, ambiguous correspondence, classification change, root-role
change, invalid EOS state, or lack of strict merit improvement causes rejection
and backtracking. Newton does not step through a discontinuous root-selection
boundary.

## Convergence, reconstruction, and fallback

Newton converges only when the full raw equilibrium norm is at most the
existing `INNER_LOG_K_TOLERANCE = 1e-10`. Step size, pressure movement, or a
small line-search factor cannot establish convergence. The accepted active
state is mapped back to full component order and freshly reevaluated. It must
then satisfy the historical saturation objective, incipient sum, fugacity
equilibrium, mechanical stability, finite pressure, bounds, root identity, and
trivial-state gates. A failure at reconstruction also falls back.

The standalone seed uses the Wilson pressure and Wilson K-values. When an
existing log-K continuation seed is supplied, the logarithmic midpoint of the
local pressure bounds supplies the pressure seed; the Module 9 local interval
is constructed around its predicted pressure. This is deliberately local and
does not solve the historical problem first.

`SaturationNewtonAttempt` records convergence/rejection, residuals, iteration
and evaluation counts, full/backtracked/rejected steps, history, and failure
reason. On fallback, the historical `SaturationStatus`, search history, and
failure semantics remain authoritative.

## Public controls and solver hierarchy

| Setting | Default |
| --- | ---: |
| `saturation_newton_enabled` | `False` |
| `newton_max_iterations` | `15` |
| `newton_max_jacobian_condition_number` | `1e12` |
| `newton_line_search_reduction_factor` | `0.5` |
| `newton_minimum_line_search_factor` | `1e-6` |
| `newton_max_backtracking_iterations` | `20` |

Every control is type-, finiteness-, sign-, and range-validated. Envelope
settings carry the same controls into saturation correction without duplicating
Newton code. The hierarchy is:

```text
optional safeguarded Newton
  -> success: reconstruct and apply historical physical gates
  -> rejection: historical bracketed saturation solver
       -> historical successive substitution
       -> optional Module 12 vector-secant target
       -> Module 11 damping exactly once
```

Acceleration and damping never operate inside a Newton iteration.

## Deterministic benchmark

The benchmark command is:

```console
uv run python -m tests.run_newton_saturation_benchmarks
```

It compares historical, accelerated, and Newton modes across 12 cases. Work is
reported as actual EOS and fugacity evaluations made by the saturation layer,
including the duplicate value evaluations required by fixed-root derivatives.
All 12 Newton cases improved this defined work count; none tied, worsened, or
fell back. Mean work reduction among improved cases was `94.9116%`. This is a
deterministic representative matrix, not a universal speed guarantee.

| Case | Historical work | Accelerated work | Newton work | Newton iterations | Backtracked/rejected | Fallback |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| easy binary bubble | 1728 | 1442 | 60 | 6 | 0/0 | no |
| difficult binary bubble | 2286 | 1756 | 68 | 7 | 0/0 | no |
| easy binary dew | 1976 | 1572 | 44 | 4 | 0/0 | no |
| difficult binary dew | 1358 | 1322 | 36 | 3 | 0/0 | no |
| CH4/C3 60/40 dew, 250 K | 2638 | 2226 | 52 | 5 | 0/0 | no |
| ternary bubble | 1848 | 1482 | 60 | 6 | 0/0 | no |
| ternary dew | 2110 | 1792 | 44 | 4 | 0/0 | no |
| pure methane | 440 | 440 | 36 | 3 | 0/0 | no |
| near-critical derivative-applicable | 220 | 220 | 36 | 3 | 0/0 | no |
| continuation-only bubble | 3382 | 2672 | 164 | 15 | 1/1 | no |
| short bubble envelope | 2262 | 1904 | 160 | 14 | 0/0 | no |
| short dew envelope | 2414 | 2106 | 144 | 12 | 0/0 | no |

The CH4/C3 60/40 dew regression converged at
`575969.5124486142 Pa`, with incipient composition
`(0.03360897298792507, 0.9663910270120749)`. Pure methane at 170 K
converged at `2348696.1055850405 Pa`.

The final verification gate passed 54 focused Module 15 tests and 814 complete
repository tests. Module 13 remained 41/41; Module 14 remained 23/23 and its
extended 21-specification / 774-comparison report passed with the one documented
boundary exclusion. Ruff lint and formatting, strict mypy, and compileall were
clean. With Newton disabled, the strict golden comparison reported zero
physical, numerical-path, status, termination, missing, or extra changes; the
328 notices were source-commit metadata only.

## Limitations

Newton remains locally convergent and conservative. It does not prove global
root uniqueness or branch completeness, cross unresolved root switches,
identify a critical point, implement pseudo-arclength continuation, validate
property data, or compare with experiment. Fallback may repeat work already
spent by a rejected Newton attempt. The benchmark contains no fallback in its
12 physical cases; adversarial and poor-seed tests separately verify safe
fallback behavior.
