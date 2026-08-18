# Thermodynamic derivative design

## Scope and future residual

Module 13 supplies analytical Peng--Robinson derivative infrastructure for a
later fixed-temperature saturation Newton corrector. It does not implement or
enable Newton and does not change flash, saturation-pressure, or phase-envelope
execution.

For a specified parent composition, a future saturation corrector needs one
pressure coordinate and `n-1` independent coordinates for the incipient
composition. A natural equation set is the `n` component fugacity-equality
residuals in logarithmic form. Module 13 therefore exposes pressure,
temperature, and constrained-composition derivatives of mixture parameters,
the selected compressibility root, and `ln(phi_i)`. Temperature derivatives
are included for later continuation work, although temperature is fixed in the
first planned saturation Newton system.

No automatic-differentiation framework is introduced. Component critical
properties, acentric factors, universal gas constant, component order, and the
stored binary-interaction mapping are fixed. Pressure derivatives also fix
temperature and composition; temperature derivatives fix pressure and
composition; composition derivatives fix pressure and temperature.

## Composition coordinates

Mole fractions are constrained by `sum(x_i)=1`. The API chooses one explicit
reference component `r`, defaulting to the last component, and defines

```text
u_k = x_k                                      (k != r)
x_r = 1 - sum(u_k)
d/du_k = partial/partial(x_k) - partial/partial(x_r)
```

The independent component indices and reference index accompany every mixture
result. This is a tangent derivative on the composition simplex, not a claim
that all mole fractions are independent. Rows retain input component order;
columns retain the reported independent-coordinate order. The algebra remains
defined at a zero mole fraction and approaches pure limits continuously, but a
central finite difference across a composition boundary is not valid.

## Fixed-root contract

Derivatives are valid locally on a fixed physical root and do not include root
switching or branch-selection discontinuities.

The caller must first provide a genuine root of the current cubic. The API
differentiates that root implicitly; it does not differentiate root finding,
sorting, admissibility tests, mechanical classification, or liquid/vapor root
selection. Consequently a derivative must not be continued across a root
switch or branch boundary.

For cubic residual `F(Z,A,B)=0`,

```text
dZ/dq = -(F_A dA/dq + F_B dB/dq) / F_Z
```

The result records `F_Z`, the fixed-`Z` parameter partial, units,
applicability, and a failure reason. If `F_Z` is unresolved at float64 scale,
the derivative is returned as non-applicable with `derivative=None`; NaN or a
misleading finite quotient is never returned. This is a local numerical
safeguard, not a critical-point solver.

## Public surface and units

- `calculate_pure_component_temperature_derivatives`: `alpha` and dimensional
  `a*alpha` temperature derivatives. `dalpha/dT` has units `K^-1` and
  `d(a*alpha)/dT` has units `Pa m^6 mol^-2 K^-1`; PR `a` and `b` themselves
  are constant with temperature.
- `calculate_pure_dimensionless_parameter_derivatives`: pure `A` and `B`
  derivatives per Pa, per K, and with respect to dimensionless `ln(P)`.
- `calculate_mixture_parameter_derivatives`: pair terms, attraction sums,
  `a_mix`, `b_mix`, `A`, and `B` derivatives. Pressure derivatives are per Pa,
  temperature derivatives per K, and composition derivatives per mole-fraction
  coordinate.
- `calculate_fixed_root_compressibility_derivative`: one explicitly named and
  unit-labelled local derivative of an already selected `Z`.
- `calculate_fixed_root_mixture_fugacity_derivatives`: ordered derivatives of
  `ln(phi_i)` per Pa, per K, per mole-fraction coordinate, plus the explicit
  identity `d/dln(P)=P d/dP`.

All multi-value outputs are frozen, slotted dataclasses. Binary-interaction
coefficients are fixed during differentiation and must match the canonical
provenance stored in the evaluated mixture parameters.

## Fugacity differentiation

The derivative follows every pathway in the existing stable `ln(phi_i)`
expression: explicit `A` and `B`, `b_i/b_mix`, component attraction sum,
`a_mix`, the implicit selected-root derivative, `ln(Z-B)`, and the stable
logarithm ratio. It uses the same root-offset and `log1p` representation as the
value calculation. The existing fugacity evaluator is not rewritten.

## Verification boundary

Module 13 tests exact algebraic identities and limited central-difference
sanity checks at multiple fixed step sizes, away from branch changes and
multiple roots. Those finite differences catch obvious implementation errors;
they are not independent scientific verification. Module 14 must independently
verify these derivatives before any Newton solver is permitted to consume
them. Module 15 is the earliest planned solver integration point.
