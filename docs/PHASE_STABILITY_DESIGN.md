# Module 6 phase-stability design note

This batch implements Michelsen-style stability trials, not a flash
calculation. It determines whether a distinct trial composition can lower the
tangent-plane distance; it does not calculate phase fractions or final phase
compositions.

For normalized feed composition `z`, the selected homogeneous feed reference
defines:

\[
d_i=\ln z_i+\ln\phi_i(z)
\]

For normalized trial composition `w`:

\[
TPD(w)=\sum_i w_i[\ln w_i+\ln\phi_i(w)-d_i]
\]

Components with zero feed fraction remain outside the active support: their
trial fraction must also be zero, and their limiting zero contribution is
omitted rather than evaluating `log(0)`.

Wilson estimates are initialization only:

\[
K_i=\frac{P_{c,i}}P\exp[5.373(1+\omega_i)(1-T_{c,i}/T)]
\]

The vapor-like initial trial is proportional to `z_i K_i`; the liquid-like
trial is proportional to `z_i/K_i`. Log-sum-exp normalization is used so this
solver step remains stable for very large or small positive K-values and never
mutates the supplied feed.

Wilson trials remain the primary workflow. A deterministic fallback is run for
a trial character only if its Wilson attempt is inconclusive. A successful
Wilson result is retained directly and never replaced by multi-start results.
For active feed components, fallback candidates are ordered as:

1. the feed composition;
2. a uniform composition over the active feed support; and
3. one component-rich composition per active component, with the selected
   fraction set to `1 - 10^-3` and the remaining `10^-3` distributed among
   other active components in proportion to their feed fractions.

Zero-feed components remain exactly zero. Candidates are immutable, normalized,
deduplicated within an absolute composition tolerance of `10^-12`, and capped
at 10 starts in deterministic component order. The same successive-substitution
implementation is used for Wilson and fallback attempts.

Successive substitution uses unnormalized positive weights:

\[
\ln W_i^{new}=\ln z_i+\ln\phi_i(z)-\ln\phi_i(w)
\]

and normalizes `W` before each EOS evaluation. Convergence uses the
scale-invariant stationary residual
`max_i |ln(w_i_new) - ln(w_i_old)|` after normalization, plus maximum
composition change and TPD change. A common multiplicative change in all
unnormalized weights therefore cannot alter the residual. Iteration history is
immutable. Maximum-iteration, two-cycle, invalid numerical state, and
root-selection failures are
reported rather than converted to a stable answer.

Every feed or trial state rebuilds PR mixture parameters and solves the shared
PR cubic. Unstable roots are never used. Vapor-like trials choose the largest
mechanically stable root; liquid-like trials choose the smallest. Marginal
roots are preserved diagnostically and excluded from selection. Root size is a
trial-character policy, not a claim of global stability.

The character policy is reapplied at every iteration and every candidate root
is stored in the iteration record. It does not assign persistent branch IDs or
force nearest-root continuation. If an outer branch appears or disappears at a
spinodal, the selected root may therefore change discontinuously; convergence,
TPD history, and oscillation handling must expose the consequence rather than
silently treating root size as continuity evidence.

A non-blocking `DISCONTINUOUS_TRIAL_ROOT_SWITCH` diagnostic records an observed
branch-character discontinuity. It is raised when the policy-selected current
root is not the closest current stable root to the preceding selection, or when
the number of stable roots changes together with a selected-root jump larger
than 5% of the local dimensionless `Z` scale. The comparison band is
`10^-8 * max(1, |Z_old|, |Z_new|)`. The diagnostic does not alter root choice,
force continuation, or automatically make a trial fail.

For the feed reference, all mechanically stable homogeneous roots are evaluated
with Module 5 fugacity coefficients. The root minimizing
`sum(z_i ln(phi_i))` is selected, while every candidate and classification is
retained. This chooses the lowest-Gibbs homogeneous feed branch only; it does
not decide stability against composition splitting.

A converged trial is trivial when its normalized composition returns to the
feed within the documented composition tolerance. A distinct converged trial
with `TPD < -TPD_TOLERANCE` makes the feed `UNSTABLE`. The result is `STABLE`
only when both required characters have a reliable converged result and neither
finds a distinct negative TPD. Any required character without a reliable result
is `INCONCLUSIVE`.

For an inconclusive Wilson character, every fallback attempt is retained. Any
distinct converged negative-TPD stationary points are deduplicated by final
composition, and the lowest TPD is selected. If none exists, the lowest reliable
converged result at or above the negative tolerance is selected. Marginal or
failed attempts are never stable evidence. The character record preserves the
Wilson attempt, fallback trigger, starts, all attempt results, selection reason,
diagnostics, and count of distinct negative stationary points.

This bounded multi-start policy reduces dependence on a single initialization,
but it is not an exhaustive search and does not prove a global TPD minimum. The
analysis remains a stability test only: it does not calculate phase fractions,
equilibrium phase compositions, or a flash solution.

## Independent audit references

An independent binary composition-grid scan and bounded local refinement use
only the committed mixing/root/fugacity APIs and a separately reconstructed TPD
expression; they do not call the Module 6 iteration or TPD function.

- `z = (0.7 methane, 0.3 ethane)`, 300 K, 10 MPa: the full interior grid has
  no negative TPD beyond float64 noise, and the minimum returns to the feed.
- `z = (0.5 methane, 0.5 ethane)`, 170 K, 0.1 MPa: the refined minimum is
  `TPD = -0.1380056497983253` at methane fraction
  `0.018915506721665004`. The liquid-like production trial independently
  recovers the same stationary region.

A deterministic audit over 90 binary feed states (`z_CH4 = 0.2, 0.5, 0.8`,
six temperatures from 160–300 K, and five pressures from 0.1–10 MPa) found no
stable/unstable mismatch between the two Wilson trials and an independent
coarse full-composition scan. This is evidence for the tested domain, not proof
that two starts locate the global TPD minimum for every mixture.
