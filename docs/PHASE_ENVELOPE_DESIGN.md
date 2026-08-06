# Module 9 phase-envelope continuation design

This module traces ordered saturation states for one fixed overall composition.
It uses natural temperature continuation and does not solve an exact critical
point, trace a critical locus, or guarantee a globally complete envelope.

## Saturation branches

On the bubble branch the parent liquid remains `x = z`, the incipient vapor
composition varies, component fugacities satisfy `f_i^L = f_i^V`, and
`sum(z_i K_i) = 1`. On the dew branch the parent vapor remains `y = z`, the
incipient liquid varies, fugacities are equal, and `sum(z_i / K_i) = 1`.

An isolated pressure search can miss a nontrivial branch when Wilson-seeded
iteration returns to `K_i = 1`, when failed inner evaluations break a pressure
bracket, or when distinct phase roots approach one another between grid points.
Continuation uses a neighboring converged pressure, log K-values, and incipient
composition to preserve branch identity and reduce dependence on Wilson starts.

## Natural-temperature predictor

For the first step, `T_pred = T_n + Delta T`, while `ln(P)`, `ln(K_i)`, and the
incipient composition are copied from the last point. After two accepted points,
a secant predictor is used when its temperature denominator and every slope are
finite:

\[
\ln P_{pred}=\ln P_n+(T_{pred}-T_n)
\frac{\ln P_n-\ln P_{n-1}}{T_n-T_{n-1}}
\]

\[
\ln K_{i,pred}=\ln K_{i,n}+(T_{pred}-T_n)
\frac{\ln K_{i,n}-\ln K_{i,n-1}}{T_n-T_{n-1}}
\]

Duplicate temperatures or non-finite slopes cause an explicit previous-state
fallback. Predictions are not clamped. Natural temperature continuation can
fail at vertical or folded sections; pseudo-arclength continuation is not
implemented.

## Corrector and local pressure search

The corrector passes predicted log K-values into Module 8's unchanged
equilibrium iteration, and into every fixed-pressure evaluation that search
makes. The local interval is symmetric in log pressure around the predicted
pressure and is then clipped to the configured pressure bounds. Module 8
samples five evenly spaced log-pressure points spanning the interval, so an
unclipped interval samples the predicted pressure exactly; a clipped interval
is neither symmetric nor centred on it. Module 8 also adds its own Wilson
centring pressure, clamped into the interval, which coincides with an interval
edge for a narrow window and becomes a sixth distinct sample for a wide one.
The interval expands by a configured factor after failure. Only fully
converged, nontrivial inner states can form a bracket, and Module 8
reconstructs the final state at the solved pressure. A full Wilson-seeded
Module 8 search is an optional, separately recorded fallback after every local
attempt fails.

The continuation path retains Module 8's `1e-8` multicomponent unity-log-K
rejection, composition/root triviality check, mechanical root policies, and
final convergence gates. A trivial attempt cannot supply an objective, bracket,
or accepted point. Pure components remain exempt from the unity-K rule.

Because a continuation seed can hold the inner iteration on the nontrivial
branch where a Wilson start collapses to `K_i = 1`, continuation reaches
saturation states at which an isolated Module 8 search reports `NOT_FOUND`.
`tests/test_phase_envelope.py` pins two such states against an independent
solver.

## Branch identity and adaptive steps

A corrected point is compared with both its predictor and the last accepted
point. Default rejection thresholds are `0.50` in predicted log pressure,
`1.00` in maximum predicted log K, `0.35` in incipient composition, `0.75` in
consecutive log pressure, and `0.50` in selected root. A rejected step is
halved and retried. When no acceptable point survives, the evidence gathered
during the retries chooses the reason -- trivial collapse, numerical failure,
or branch loss -- and only when none of those applies does the loop report the
limit that stopped it, either the minimum step or the retry counter. The same
situation therefore never reports two different reasons.

An easy unexpanded correction with small predictor errors increases the next
temperature-step magnitude by `1.25`. Expanded, fallback, or difficult
corrections reduce it by `0.70`. Every step stays within configured minimum and
maximum magnitudes and preserves direction. There is no random behavior.

## Near-critical warnings and termination

At each accepted point the tracer monitors phase-composition separation,
maximum active `|ln K_i|`, and liquid/vapor root separation. Default warning
thresholds are `0.02`, `0.05`, and `0.02`, respectively. Two simultaneous
severe indicators (`0.005`, `0.01`, and `0.005`) terminate the branch as
`NEAR_CRITICAL`. With a single active component the first two indicators are
identically zero at every temperature, for the same reason the unity-K rule
exempts pure components, so only root separation is counted and it alone
decides.

Separately, a step whose corrections all collapse to the trivial solution ends
the branch as `NEAR_CRITICAL` regardless of which retry limit stopped it. That
evidence is carried by Module 8's `SATURATION_TRIVIAL_STATE` diagnostic, not by
the enclosing bracket-failure reason. In practice this is how a real
near-critical approach ends: the inner iteration stops resolving two phases
well before the accepted-point indicators enter their warning band.

`NEAR_CRITICAL` means phases are becoming numerically difficult to
distinguish. It is not an exact critical point.

## Result and termination semantics

Accepted points, predictions, correction attempts, rejected steps, diagnostics,
root candidates, fugacity data, and binary-interaction provenance are immutable.
A partial branch is valid evidence. Termination distinguishes reaching the
target, maximum accepted points, minimum step, corrector failure, branch loss,
near-critical approach, bounds, and numerical failure.

The method does not implement exact criticality equations, pseudo-arclength or
retrograde continuation, global branch completeness, experimental validation,
property regression, depletion, or plotting.
