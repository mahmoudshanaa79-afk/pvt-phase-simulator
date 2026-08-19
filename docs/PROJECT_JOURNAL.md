# Project journal

This journal is the permanent technical history of the PVT phase-behavior
simulator. For every module or stage it records why the work existed, the
scientific problem, numerical method, software-engineering work, equations and
concepts introduced, affected files, important functions and classes, design
decisions, bugs and fixes, verification, regression values, limitations,
commit provenance, and the connection to the next stage.

Each entry keeps three categories distinct:

- **SCIENCE** describes the physical model and thermodynamic meaning.
- **NUMERICAL METHODS** describes algorithms, tolerances, safeguards, and
  failure semantics used to solve the model.
- **SOFTWARE ENGINEERING** describes APIs, data structures, provenance,
  diagnostics, tests, and repository organization.

Numerical agreement and test coverage establish consistency with the
implemented model; they do not establish experimental accuracy, global
thermodynamic completeness, industrial readiness, or the authority of property
data. Unless explicitly supplied under a strict policy, binary interaction
coefficients are zero/defaulted, not fitted values.

Every future module must update this journal before being considered complete.
Historical entries must not be rewritten except to correct factual errors or
add clearly identified missing provenance.

## Milestone 0 — Repository and development foundation

### Purpose

Create a reproducible typed Python project in which EOS work could be added and
tested incrementally.

### SCIENCE

Established SI-unit conventions and a data location for component properties;
it did not yet claim a complete thermodynamic calculation.

### NUMERICAL METHODS

Introduced the initial Peng–Robinson module boundary and unit-conversion
utilities. No phase-equilibrium solver existed.

### SOFTWARE ENGINEERING

Added the `src/` package, tests, documentation, Streamlit placeholder,
notebook, locked dependencies, linting/type-checking configuration, and ignored
generated files. Main files were `pyproject.toml`, `uv.lock`, `README.md`,
`src/pvt_phase_simulator/`, `tests/`, `app/`, `data/`, and `docs/`.

### Verification, limitations, and provenance

Project-setup tests checked imports and the development skeleton. The milestone
did not provide validated EOS results. Commit:
`1110063bc0882832cb2459ab9b3d7a42e900f096`. It enabled the component and pure
PR work that followed.

## Module 1 — Component model and pure Peng–Robinson parameters

### Purpose

Represent components with validated critical properties and calculate the
temperature-dependent pure-component PR parameters.

### SCIENCE

For critical temperature `Tc`, critical pressure `Pc`, acentric factor `ω`,
and reduced temperature `Tr = T/Tc`, the implementation introduced the PR
`κ(ω)` correlation, `α(T)`, dimensional attraction/co-volume parameters `a`
and `b`, and `aα`. The dimensional quantities are distinct from the later
dimensionless reduced parameters `A` and `B`.

### NUMERICAL METHODS

Inputs are finite and domain checked. Calculations use explicit SI units and
retain float64 results rather than embedding solver behavior.

### SOFTWARE ENGINEERING

`Component`, `ComponentPropertyProvenance`, and validation were added in
`fluid_models.py`; `calculate_kappa`, `calculate_reduced_temperature`,
`calculate_alpha`, `calculate_a_parameter`, `calculate_b_parameter`, and
`calculate_peng_robinson_parameters` were built in `peng_robinson.py` with
focused tests.

### Verification, limitations, and provenance

Tests pin validation and pure methane parameter calculations. This work did not
solve the cubic or select a phase. The historical shorthand calls the completed
module M1 at `2c17c809d9d0fa7500f8350b677672734e172db4`; two precursor commits are
also part of its actual evolution:
`912bb8b8ccdeadc4cc7519c82d65b00014148d2e` (methane component model) and
`7e5c00cb5fedc75564e4cdf8ac8133c6bc6efef0` (`κ`). The next stage used these
parameters to form and solve the PR cubic.

## Module 2 — Cubic compressibility roots

### Purpose

Solve the PR compressibility polynomial and distinguish algebraic roots from
physically admissible EOS states.

### SCIENCE

The dimensional `a`, `aα`, and `b` are converted to dimensionless
`A = aαP/(R²T²)` and `B = bP/(RT)`. These define the cubic in compressibility
factor `Z`. A usable PR state must satisfy the EOS domain, including `Z > B`.

### NUMERICAL METHODS

The cubic coefficients, discriminant, real-root filtering, scale-aware
residual bounds, root deduplication, and admissibility checks were implemented.
Near-multiple roots are retained only when numerically real and residual-valid.

### SOFTWARE ENGINEERING

Important APIs in `peng_robinson.py` include
`calculate_cubic_coefficients`, `calculate_cubic_residual`,
`solve_compressibility_roots`, `filter_physical_compressibility_roots`, and
`validate_compressibility_root`; `test_peng_robinson.py` gained root and
failure-domain coverage.

### Verification, limitations, and provenance

Tests cover one- and three-real-root regions, residuals, ordering, and invalid
roots. Algebraic admissibility alone did not yet choose the stable phase.
Commit: `9525eebbaf21456a29484b450a642a6acad45936`. The next stage added mechanical
classification and fugacity-based root selection.

## Module 3 — Fugacity and stable-root selection

### Purpose

Attach thermodynamic phase meaning to admissible pure-fluid roots.

### SCIENCE

The pure PR fugacity coefficient `φ`, fugacity `f = φP`, and local mechanical
stability were introduced. Among mechanically stable outer roots, the stable
homogeneous root minimizes fugacity/Gibbs energy at fixed `T` and `P`.

### NUMERICAL METHODS

The implementation classifies roots as stable, marginal, or unstable using the
local reduced pressure derivative with cancellation-aware tolerances. Fugacity
is evaluated only on validated roots. Small/large-root selection is separated
from thermodynamic stable-root selection.

### SOFTWARE ENGINEERING

`MechanicalStabilityClassification`, `FugacityRootResult`, `StableRootResult`,
`classify_mechanical_stability`, `calculate_log_fugacity_coefficient`,
`evaluate_fugacity_roots`, and `select_stable_root` were added to
`peng_robinson.py`; README and tests documented result semantics.

### Verification, limitations, and provenance

Tests pin root classification and minimum-fugacity selection. Mechanical
stability is local and does not prove mixture stability. Commit:
`88e965c55ffa65298a7014b17b04c870582c597a`. The next work generalized PR to
mixtures and component fugacities.

## Modules 4–5 — Mixture rules and mixture fugacity

### Purpose

Build a provenance-aware mixture EOS foundation that later equilibrium solvers
could reuse without duplicating thermodynamics.

### SCIENCE

Classical quadratic attraction mixing and linear co-volume mixing were added:
`a_mix = Σ_iΣ_j x_i x_j sqrt(a_i a_j)(1-kij)` and
`b_mix = Σ_i x_i b_i`. The mixture `A`, `B`, component attraction sums, and PR
component fugacity coefficients connect composition to chemical potential.
Equality of each component fugacity across phases is the later equilibrium
condition.

### NUMERICAL METHODS

Component order, composition support, pair symmetry, parameter provenance,
root admissibility, low-pressure evaluation, and finite logarithms are checked.
The binary-interaction policy either requires supplied pairs or explicitly
records defaulted zero interactions; it never invents nonzero `kij` values.

### SOFTWARE ENGINEERING

`FluidMixture` and `MixtureComponent` were completed. New modules
`mixing_rules.py`, `mixture_fugacity.py`, and `diagnostics.py` introduced
`BinaryInteractionPolicy`, `PengRobinsonMixtureParameters`,
`calculate_peng_robinson_mixture_parameters`,
`calculate_mixture_compressibility_roots`,
`calculate_mixture_fugacity_coefficients`, and immutable diagnostic/results
types. Equations, package exports, application plumbing, and broad tests were
updated.

### Verification, limitations, and provenance

Tests cover symmetry, order invariance, provenance mismatch, zero/defaulted
interactions, pure-limit consistency, roots, and fugacity identities. These
tests verify implementation consistency, not property accuracy. Combined
commit: `afb9df02bc1ce20c92e7c66469ac405623c1733a`. The next stage used these APIs
for tangent-plane stability analysis.

## Module 6 — Mixture phase stability and TPD

### Purpose

Decide whether a homogeneous feed can lower Gibbs energy by forming a distinct
trial composition before allowing a flash calculation.

### SCIENCE

For feed `z`, `d_i = ln(z_i) + ln(φ_i(z))`; for normalized trial `w`,
`TPD(w) = Σ_i w_i[ln(w_i)+ln(φ_i(w))-d_i]`. A distinct converged negative TPD
indicates instability. Zero-feed components stay outside active support.

### NUMERICAL METHODS

Michelsen-style vapor- and liquid-character successive-substitution trials use
Wilson `K` estimates only as starts, log-sum-exp normalization, a scale-invariant
stationarity residual, deterministic bounded fallback starts, root-switch and
two-cycle diagnostics, and explicit `STABLE`, `UNSTABLE`, or `INCONCLUSIVE`
classification. The feed reference minimizes `Σ z_i ln φ_i` over mechanically
stable roots. The bounded search does not prove the global TPD minimum.

### SOFTWARE ENGINEERING

`phase_stability.py` introduced `PhaseStabilityStatus`, trial/result records,
`calculate_wilson_k_values`, `initialize_trial_composition`,
`calculate_tangent_plane_distance`, `run_phase_stability_trial`, and
`analyze_mixture_phase_stability`; design/equation docs and tests were added.

### Verification, limitations, and provenance

Independent binary-grid/reference checks include a stable 300 K/10 MPa
methane–ethane state and a 170 K/0.1 MPa minimum
`TPD = -0.1380056497983253` near methane fraction
`0.018915506721665004`; the documented 90-state audit is evidence only for its
tested domain. Commit: `544cfab7ffd6c18a6536a29c273c7821803a49e6`. The
stability status became the gate for Module 7 flash.

## Module 7 — Stability-gated two-phase flash

### Purpose

Calculate phase fraction and equilibrium liquid/vapor compositions only when
the feed stability analysis supports phase splitting.

### SCIENCE

`K_i = y_i/x_i = φ_i^L/φ_i^V` at equilibrium. Rachford–Rice solves material
balance for vapor fraction `β`, and phase compositions satisfy
`z_i = (1-β)x_i + βy_i`. Component fugacities must agree across phases.

### NUMERICAL METHODS

The solver brackets Rachford–Rice on the physical denominator-safe interval,
uses current log K to form normalized phases, selects smallest/largest
mechanically stable liquid/vapor roots, and performs log-K successive
substitution. Convergence requires the full log-fugacity target residual,
Rachford–Rice residual, normalized compositions, strict `0 < β < 1`, material
balance, finite values, and stable roots. Structured stagnation, oscillation,
single-phase, inconclusive, and failed results are preserved.

### SOFTWARE ENGINEERING

`flash.py` introduced `solve_rachford_rice`,
`calculate_phase_compositions`, `evaluate_flash_phase`,
`calculate_two_phase_flash`, immutable iteration/results, interaction
provenance, and convergence helpers. `FLASH_DESIGN.md`, equations, README, and
`test_flash.py` were added.

### Verification, limitations, and provenance

Tests cover endpoint classification, extreme K denominators, balance,
permutation, stability gating, fugacity consistency, and failures. The module
does not compute saturation pressures or an envelope. Commit:
`ba9a119c9265e2bfa4564d32869361e8cf07dfc4`. Module 8 reused the phase evaluator
for incipient phases.

## Module 8 — Bubble- and dew-pressure calculation

### Purpose

Find an isolated fixed-temperature pressure where a parent phase is in
equilibrium with an infinitesimal incipient phase.

### SCIENCE

Bubble points use fixed liquid `x=z` and
`F_b(P)=Σ_i z_iK_i(P)-1`; dew points use fixed vapor `y=z` and
`F_d(P)=Σ_i z_i/K_i(P)-1`. Both require phase fugacity equality and the
appropriate mechanically stable roots. Wilson pressures are starts, not EOS
answers.

### NUMERICAL METHODS

An inner normalized incipient-composition fixed point supplies an objective to
a deterministic log-pressure search and bracketed Brent solve. A nontrivial
branch can collapse to `K≈1`, which makes either objective zero at arbitrary
single-phase pressures. Multicomponent unity-log-K and composition/root tests
therefore reject this false solution before bracketing. Pure components are
exempt from unity-K rejection because `K=1` is their real saturation condition;
they instead require distinct stable liquid and vapor roots. Failed grid points
cannot bridge a bracket, and multiple roots remain inconclusive.

### SOFTWARE ENGINEERING

`saturation_pressure.py` added `SaturationKind`, structured statuses and
history, `calculate_wilson_pressure_estimates`, bubble/dew objective helpers,
`evaluate_saturation_pressure`, and `calculate_saturation_pressure`.
`flash.py` exposed shared phase evaluation. Saturation docs and tests were
added.

### Verification, limitations, and provenance

Tests pin bubble/dew physics, trivial rejection, pure-component behavior,
failure/status semantics, roots, fugacities, and permutations. The important
methane/propane 60/40 true dew regression at 250 K is
`575969.5124486194 Pa`; the trivial `K=1` state is not accepted as that result.
The finite search does not prove all roots found. Commit:
`06ad4f4f32cdcf54f3a8bcdc8b0433a2256cbcc9`. Module 9 added branch
continuation where isolated searches fail.

## Module 9 — Natural-temperature phase-envelope continuation

### Purpose

Trace ordered bubble and dew saturation states while preserving branch
identity between temperatures.

### SCIENCE

Each point still satisfies the Module 8 bubble/dew objective, component
fugacity equality, mechanical-root requirements, and fixed overall
composition. `NEAR_CRITICAL` means phases become numerically difficult to
distinguish; it is not an exact critical point.

### NUMERICAL METHODS

The first predictor copies the prior state to the next temperature; later
predictors use secants in `ln P` and vector `ln K`. A corrector tries a local
log-pressure window around the prediction, expands it on failure, and can use
a separately recorded global Wilson fallback. Predictor/consecutive pressure,
log-K, composition, and root-distance tests protect branch identity. Adaptive
temperature steps grow after easy corrections and shrink after difficult or
rejected attempts. Near-critical diagnostics monitor composition, log K, and
root separation. Continuation seeds can retain a nontrivial branch at states
where isolated saturation returns `NOT_FOUND`.

### SOFTWARE ENGINEERING

`phase_envelope.py` added `EnvelopeContinuationSettings`, predictions,
correction attempts, points, branch/termination enums,
`predict_envelope_state`, `correct_envelope_prediction`,
`trace_phase_envelope_branch`, bubble/dew wrappers, and combined results.
`saturation_pressure.py` gained continuation seeding. Design/equation docs and
`test_phase_envelope.py` record every accepted and rejected attempt.

### Bugs, fixes, verification, and limitations

The audited implementation fixed a pure-component near-critical false positive
by not counting composition and log-K indicators that are identically zero for
one active component; root separation alone decides. Failure evidence was also
made authoritative so branch loss was not mislabeled as whichever retry limit
was reached. Forward/reverse, continuation-only, branch-loss, near-critical,
fallback, and adaptive-step tests pin behavior. Natural-temperature
continuation cannot trace every fold; pseudo-arclength and exact criticality
are absent. Audited commit:
`d51b3103564652e752c696d8687a60c1c7aaf206`. A separate minimum-step regression
was added by `e07d5c8f6c140e425b7154cefd879f3ba9476aa1` before hardening stages 9A–9E.

## Stage 9A — Continuation control-flow refactor

### Purpose and categories

- **SCIENCE:** No equilibrium equations or branch definitions changed.
- **NUMERICAL METHODS:** Retry ordering and termination evidence were kept
  explicit while preserving the accepted numerical path.
- **SOFTWARE ENGINEERING:** The large continuation loop was decomposed around
  `_attempt_continuation_step`, `_ContinuationStepOutcome`, and finish/empty
  helpers so retry and termination behavior could be reviewed independently.

Only `phase_envelope.py` changed. Existing envelope regressions verified the
refactor. Commit: `6679a6c29bae30413d6f67cc4eb46a77107f2f68`. This made
threshold exposure safer in Stage 9B.

## Stage 9B — Exposed numerical thresholds

### Purpose and categories

- **SCIENCE:** Thermodynamic equations and physical meaning remained fixed.
- **NUMERICAL METHODS:** Predictor-error, retry-step, near-critical, branch
  identity, pressure-bound, and adaptation thresholds became named validated
  `EnvelopeContinuationSettings` fields with historical defaults.
- **SOFTWARE ENGINEERING:** Settings validation, docs, equations, and focused
  tests replaced hidden literals without changing default behavior.

Files changed were `phase_envelope.py`, `test_phase_envelope.py`,
`EQUATIONS.md`, and `PHASE_ENVELOPE_DESIGN.md`. Commit:
`12092293c2d16879ca0e86484b8537764b096097`. The exposed controls enabled more
independent reference and branch tests.

## Stage 9C — Stronger independent/reference tests

### Purpose and categories

- **SCIENCE:** No production science changed. Reference comparisons exercise
  the same equilibrium requirements through independently assembled checks.
- **NUMERICAL METHODS:** Tests strengthened predictor, corrector, branch, and
  continuation-only expectations without changing solver paths.
- **SOFTWARE ENGINEERING:** Only `test_phase_envelope.py` changed.

The exact commit recovered from repository history is
`3ea3e3670814aaca660da460f07fdb881b4d818a` (“Strengthen phase-envelope
reference tests”). Reference agreement is not experimental validation. This
stage supplied stronger oracles for mutation-oriented Stage 9D.

## Stage 9D — Branch coverage and mutation testing

### Purpose and categories

- **SCIENCE:** No physical equations or properties changed.
- **NUMERICAL METHODS:** Boundary and failure-path tests pin flash,
  saturation, and envelope decisions, including branch loss and minimum-step
  behavior.
- **SOFTWARE ENGINEERING:** Test coverage was expanded and mutation-testing
  configuration/dependencies were added in `pyproject.toml`, `uv.lock`, and
  `.gitignore`; production source did not change.

Commit: `3e70a07c0b0249fac3ca012a8b9eaafeefa661e4`. Mutation resistance supports
implementation confidence but not physical truth. Stage 9E then generalized
deterministic invariants across generated inputs.

## Stage 9E — Deterministic property-based testing

### Purpose and categories

- **SCIENCE:** Tested invariants include normalization, material balance,
  permutation equivariance, finite/domain behavior, and thermodynamic
  consistency; no model equations changed.
- **NUMERICAL METHODS:** Hypothesis strategies use fixed deterministic profiles
  and reproducible examples rather than random production behavior.
- **SOFTWARE ENGINEERING:** Added `tests/conftest.py`, `test_properties.py`,
  Hypothesis configuration/dependency changes, and ignored its local cache.

Commit: `e296fc157a28c357c68b49cad9525f87b021d75e`. The tests cover broader input
families but do not prove experimental accuracy. Their audited state became
the source commit embedded in the Module 10 baseline.

## Module 10 — Deterministic numerical golden master

### Purpose

Detect unintended changes in physical results, solver paths, statuses,
termination reasons, diagnostics, and branch selection across the completed
solver stack.

### SCIENCE

No thermodynamic model changed. Numerical regression protection is not
experimental validation and cannot certify component properties or `kij`.

### NUMERICAL METHODS

The canonical CSV stores float64 values with deterministic round-trip text and
classifies differences as physical drift, numerical-path change,
platform/formatting noise, missing case, or extra case. Pressure, composition,
log-K, root, and beta comparisons have documented tolerances; statuses,
termination reasons, branches, and diagnostics are semantic/exact.

### SOFTWARE ENGINEERING

`tests/golden_master/` added 328 pure, mixture, order-reversal, zero-fraction,
near-pure, stability, flash, saturation, continuation-only, and envelope cases,
plus generation/comparison tooling and infrastructure tests. Canonical
replacement is explicit and must never be silent.

### Verification, limitations, and provenance

The canonical baseline SHA-256 is
`CBDA39461C9F5B839EF59F60710DF4558C5A588B6C1C90913ECADF099356A27D` and
retains source commit `e296fc157a28c357c68b49cad9525f87b021d75e`. Commit:
`cc69c83f368364b1450e94dde66877283f0faf99`. Module 11 used this baseline to
prove that a new opt-in iteration control left historical defaults unchanged.

## Module 11 — Safeguarded successive-substitution damping

### Purpose

Add an optional conservative fixed relaxation to flash, saturation, and
envelope correction without changing equilibrium equations or the historical
default path.

### SCIENCE

The PR EOS, fugacity equality, material balances, objectives, root policies,
stability logic, and convergence tolerances are unchanged.

### NUMERICAL METHODS

For `0 < λ ≤ 1`,

`lnK_next = lnK_current + λ(lnK_target - lnK_current)`.

The shared helper returns the target tuple directly at `λ=1`, preserving the
exact historical floating-point path. Convergence still uses the full EOS
fixed-point/physical residual, not the smaller damped movement, which prevents
false convergence at tiny λ. Damping occurs in log space and cannot create a
non-positive K value.

### SOFTWARE ENGINEERING

`calculate_damped_log_k_values` and the keyword-only
`successive_substitution_damping_factor=1.0` were added to `flash.py` and passed
through `evaluate_saturation_pressure`, `calculate_saturation_pressure`, and
`EnvelopeContinuationSettings`. The envelope does not duplicate damping logic.
`test_damping.py` and four design/equation documents cover validation,
equivalence, determinism, physics, failures, continuation, and false
convergence. Phase-stability code was unchanged.

### Verification, regressions, limitations, and provenance

The 25 focused tests and 669-test repository state passed; strict golden
comparison at historical defaults reported zero physical drift and zero path,
status, termination, missing, or extra changes. Methane/propane 60/40 dew at
250 K remained `575969.5124486194 Pa`. Sampled `λ=0.5` runs were slower than
`λ=1`, although their largest individual movement could be smaller; no sampled
previously failing state was rescued. Fixed damping is therefore a robustness
control, not acceleration or a convergence guarantee. Commit:
`4ac5d7c118ac3c99a9f3587d8038be1bf15f6662`. Module 12 may add independently
disabled acceleration around this fixed-point path while retaining these
safeguards.

## Module 12 — Safeguarded vector-secant acceleration

### Purpose

Add one conservative, independently disabled acceleration candidate around the
existing flash and saturation log-K fixed point. Historical behavior remains
the default; this module does not add Newton, derivatives, or new science.

### Science

The Peng–Robinson EOS, mixing rules, component fugacity equations, phase
stability, Rachford–Rice balance, bubble/dew objectives, root policies, trivial
state rules, and physical convergence gates are unchanged. Acceleration changes
only which log-K iterate is tried next.

### Numerical Method

For current log-K vector `x_n`, raw EOS target `g_n`, residual
`r_n = g_n-x_n`, previous displacement `s_n=x_n-x_(n-1)`, and residual change
`y_n=r_n-r_(n-1)`, the derivative-free vector secant candidate is

`tau_n = -(r_n^T y_n)/(y_n^T y_n)` and
`x_acc = x_n + tau_n s_n`.

This is a scalar secant extrapolation of a vector residual, not Anderson,
Aitken component-wise Δ², Newton, or a derivative API. A proposal is rejected
unless values are finite, the actual residual did not worsen by more than 5%,
the secant denominator is numerically resolved, `tau_n > 0`, the secant model
predicts at least 20% infinity-norm residual reduction, and movement is at most
twice the ordinary fixed-point movement. Rejection or insufficient history
returns the exact raw target.

The fixed order is raw target → optional acceleration/safeguard → ordinary
target fallback if needed → one damping operation. The existing factor `λ`
therefore acts once:

`x_(n+1) = x_n + λ(candidate_or_raw_target - x_n)`.

Convergence continues to use `||g_n-x_n||` and the existing physical residuals,
never the accelerated or damped step size.

### Software Engineering

`flash.py` owns the shared `calculate_safeguarded_log_k_acceleration` helper,
status enum, immutable evidence record, constants, and flash integration.
`saturation_pressure.py` imports that helper and records evidence in every
enabled inner iteration. `phase_envelope.py` exposes/pass-throughs the same
boolean without duplicating the algorithm. `test_acceleration.py` covers the
helper, validation, disabled equivalence, accepted and rejected proposals,
NaN/inf containment, damping interaction, physical invariants, false
convergence, saturation branches, trivial/pure states, continuation, and
structured failures. Equations and three numerical design documents explain
the method.

### Main Equations / Algorithms

- Residual: `r_n = g(x_n)-x_n`.
- Secant change: `y_n=r_n-r_(n-1)`.
- Proposal: `x_acc=x_n-[r_n^T y_n/(y_n^T y_n)]s_n`.
- Predicted residual: `r_n+tau_n y_n`.
- Accepted target is damped once; fallback is the exact ordinary target.

### Files Changed

- `docs/PROJECT_JOURNAL.md`, `docs/EQUATIONS.md`, `docs/FLASH_DESIGN.md`,
  `docs/SATURATION_PRESSURE_DESIGN.md`, `docs/PHASE_ENVELOPE_DESIGN.md`
- `src/pvt_phase_simulator/eos/flash.py`
- `src/pvt_phase_simulator/eos/saturation_pressure.py`
- `src/pvt_phase_simulator/eos/phase_envelope.py`
- `tests/test_acceleration.py`

### Important Functions / Classes

`calculate_safeguarded_log_k_acceleration`,
`SafeguardedLogKAccelerationResult`,
`SuccessiveSubstitutionAccelerationStatus`, `FlashIteration`,
`SaturationPressureIteration`, `calculate_two_phase_flash`,
`evaluate_saturation_pressure`, `calculate_saturation_pressure`, and
`EnvelopeContinuationSettings`.

### Design Decisions

Acceleration defaults to disabled and the disabled loops bypass the helper.
Only the enable flag is public; safeguard constants are intentionally fixed for
this conservative first module. Evidence is recorded per enabled iteration.
The shared helper returns the original target object on every rejection so
fallback does not perturb ordinary arithmetic.

### Bugs / Failure Modes Found

An initial draft built evidence objects on every disabled iteration. Although
it did not change results, that added avoidable historical-path overhead. The
disabled loop was changed to bypass acceleration entirely and record `None`.
An early envelope test incorrectly assumed enabled acceleration must retain the
historical adaptive temperature sequence; the correct invariant is ordered
branch identity and equivalent endpoint, because enabled numerical paths may
change.

### Fixes

Disabled-path work is limited to one public-setting validation call per solver;
the iteration arithmetic uses the exact Module 11 target. Tests now distinguish
historical-default equivalence from acceleration-enabled path freedom.

### Verification

The focused Module 12 suite contains 27 passing tests. The following benchmark
uses genuine existing states. “Iterations” is flash iterations or aggregate
inner saturation iterations; `A/R` is accepted/rejected acceleration proposals.
Fixed damping uses `λ=0.5`; accelerated runs use `λ=1`.

| Case | Historical iterations | Damped iterations | Accelerated iterations | Accelerated A/R | Physical result |
| --- | ---: | ---: | ---: | ---: | --- |
| easy CH4/C2 flash, 170 K, 0.1 MPa | 5 | 24 | 5 | 2/2 | `beta=0.8761085505135564` accelerated |
| difficult CH4/C3 flash, 150 K, 0.1 MPa | 6 | 27 | 5 | 1/3 | `beta=0.4569527853765382` accelerated |
| CH4/C2 bubble, 180 K | 665 | 3292 | 562 | 186/286 | `1574190.5836895173 Pa` |
| CH4/C2 dew, 180 K | 763 | 3239 | 642 | 226/326 | `158620.84358078014 Pa` |
| CH4/C3 60/40 dew, 250 K | 1229 | 3837 | 1023 | 211/722 | `575969.5124486102 Pa` |
| continuation-only bubble, 240→250 K | 1574 | 6207 | 1219 | 323/779 | `6172720.661334707 Pa` endpoint |
| CH4/C2 bubble branch, 200→220 K | 1304 | 5537 | 1094 | 365/570 | `3974616.95899046 Pa` endpoint |

All modes retained their expected status and physical branch. The accelerated
CH4/C3 60/40 value is within the golden pressure tolerance of the historical
`575969.5124486194 Pa`. The accelerator improved iteration totals in six of
seven sampled cases and tied the easy flash. Fixed `λ=0.5` was slower in every
sample. No formerly failing case was recovered, and no sampled converged case
regressed.

Final verification collected 696 passing repository tests. Ruff, format
checking, mypy over 14 source files, compileall, and whitespace checks passed.
The strict golden comparison with acceleration disabled reported zero physical
drift, numerical-path changes, missing cases, and extra cases; status and
termination changes were zero. The 328 notices were solely the expected
baseline source-commit metadata difference. `baseline.csv` was not regenerated
and retained its Module 10 SHA-256.

### Important Numerical Regression Values

Historical/default methane/propane 60/40 dew remains
`575969.5124486194 Pa`. The continuation-only 250 K bubble endpoint remains
within golden tolerance of `6172720.661334422 Pa`; the 220 K branch endpoint is
`3974616.95899046 Pa`.

### Limitations

The predicted residual uses a scalar secant model; even an accepted candidate
is not guaranteed to improve the next nonlinear EOS residual. Actual residuals
are therefore checked again on the next iteration. The fixed safeguards may be
too conservative or ineffective for other mixtures, damping plus acceleration
was slower in sampled Module 12 tests, and no global convergence or branch
completeness follows. Function-call savings are limited because saturation
outer pressure calls were unchanged. No experimental validation was added.

### Commit / Provenance

Work began from clean `master` commit
`4ac5d7c118ac3c99a9f3587d8038be1bf15f6662`. Module 12 is intentionally
uncommitted pending review.

### Connection to Next Stage

No Module 13 work has begun. Any next stage must first preserve the disabled
golden path and review the conservative safeguard evidence rather than assume
that benchmark iteration reductions generalize.

## Module 13 — Thermodynamic Derivative APIs

### Purpose

Add the smallest scientifically complete analytical derivative surface needed
for a future fixed-temperature saturation Newton formulation, without adding
Newton or connecting derivatives to any existing solver.

### Science

Pure PR alpha, dimensional attraction, quadratic mixing-rule, dimensionless
`A/B`, selected-root `Z`, and mixture `ln(phi_i)` derivatives are defined
analytically. Component properties and binary interactions remain fixed.
Composition uses an explicit `n-1` coordinate chart on the mole-fraction
simplex. Derivatives are valid locally on a fixed physical root and do not
include root switching or branch-selection discontinuities.

### Numerical Method

No finite difference is used in production. The cubic is differentiated
implicitly as `dZ/dq=-(F_A A_q+F_B B_q)/F_Z`. A float64-scaled test on `F_Z`
returns structured non-applicability at a repeated or numerically unresolved
root. The fugacity derivative follows the existing root-offset and `log1p`
formula, including every explicit mixing pathway and the implicit root path.

### Software Engineering

A new isolated `eos.derivatives` module contains frozen, slotted result records
and precisely named calculation functions. Existing EOS value functions are
reused for provenance validation and base fugacity values. Flash, saturation,
envelope, damping, acceleration, and all default call paths remain untouched.

### Main Equations / Algorithms

- `dalpha_i/dT=-kappa_i m_i/(Tc_i sqrt(Tr_i))`.
- `daij/dT=(aij/2)[(ai alpha_i)'/(ai alpha_i)+(aj alpha_j)'/(aj alpha_j)]`.
- `da_mix/du_k=2(S_k-S_r)` and `db_mix/du_k=b_k-b_r`.
- `dA/dP=A/P`, `dB/dP=B/P`, `dA/dlnP=A`, and `dB/dlnP=B`.
- `dA/dT=A[(da_mix/dT)/a_mix-2/T]` and `dB/dT=-B/T`.
- `dZ/dq=-(F_A dA/dq+F_B dB/dq)/F_Z` on one selected root.

### Files Changed

- `src/pvt_phase_simulator/eos/derivatives.py`
- `tests/test_derivatives.py`
- `docs/DERIVATIVE_DESIGN.md`, `docs/EQUATIONS.md`, `docs/README.md`
- `docs/PROJECT_JOURNAL.md`

### Important Functions / Classes

`calculate_pure_component_temperature_derivatives`,
`calculate_pure_dimensionless_parameter_derivatives`,
`calculate_mixture_parameter_derivatives`,
`calculate_fixed_root_compressibility_derivative`, and
`calculate_fixed_root_mixture_fugacity_derivatives`; result structures
`PureComponentTemperatureDerivatives`,
`PureDimensionlessParameterDerivatives`, `MixtureParameterDerivatives`,
`FixedRootCompressibilityDerivative`, and
`FixedRootMixtureFugacityDerivatives`.

### Design Decisions

The future fixed-temperature saturation residual has `n` log-fugacity
equalities and naturally uses pressure plus `n-1` incipient-composition
coordinates. The last component is the default dependent reference, while an
explicit alternative reference is supported. Pressure-per-Pa and log-pressure
derivatives are separate named fields. The API differentiates an already
selected root, never the selection pipeline. Temperature derivatives are also
included for later continuation, but no general AD framework is added.

### Bugs / Failure Modes Found

An early provenance check compared supplied mapping entries individually and
could miss the semantic difference between an omitted pair and an explicitly
supplied zero pair. Direct exact-equality assertions for the pressure chain
rule also exposed ordinary last-bit multiplication rounding. Central
differences showed the expected truncation-error variation between the two
fixed temperature step sizes.

### Fixes

Binary interactions are compared with the repository's canonical coefficient
and supplied-pair representations. Chain-rule tests use a near-machine
precision comparison, while finite-difference checks use one declared tolerance
for both predetermined step sizes rather than tuning each case.

### Verification

The focused derivative suite contains 41 passing tests split into structural
API, algebraic identity, analytical-versus-central-difference sanity, and
singularity/failure groups. It covers methane, ethane, and propane; subcritical,
near-critical nonsingular, and supercritical pure states; binary and ternary
mixtures; low, moderate, and high pressures; liquid-like, vapor-like,
three-root, and single-root states; reversal, pure, zero-fraction, and near-pure
cases. Full repository gates and the post-edit strict golden comparison are
clean: 737 tests passed in 448.05 seconds; Ruff, format checking, mypy over 15
source files, compileall, and whitespace checks passed. The post-edit strict
golden comparison reported zero physical drift, numerical-path, status,
termination, missing, and extra changes. Its 328 notices were solely the
expected baseline source-commit metadata difference.

### Important Numerical Regression Values

The Module 10 baseline remains 328 cases with SHA-256
`CBDA39461C9F5B839EF59F60710DF4558C5A588B6C1C90913ECADF099356A27D`.
The pre-edit strict comparison reported zero physical drift, numerical-path,
status, termination, missing, and extra changes; 328 notices were baseline
source-commit metadata only. The identical post-edit counts confirm that the
new derivative module is absent from all historical solver paths.

### Limitations

Derivatives are local and can be undefined or extremely ill-conditioned near
a multiple root. They do not include root switching, phase-branch selection,
critical-point solution, derivatives of binary interactions or physical
properties, automatic differentiation, or solver globalization. Central
differences in this module are sanity checks, not independent verification.

### Commit / Provenance

Work began from clean `master` commit
`f73009c5494fcff3de6435030ed48925f3cfdffa`. Module 13 is intentionally
uncommitted pending review; no final commit hash is invented.

### Connection to Next Stage

Module 14 must independently verify these derivatives before any Newton solver
is allowed to use them. Newton implementation and solver integration remain
outside Module 13.

## Module 14 — Independent Derivative Verification

### Purpose

Independently verify every public fixed-root derivative output from Module 13
before any Newton saturation solver may use it. Verification must exercise
different numerical and algebraic routes from production and must not change
solver behavior.

### Science

The verification domain is explicitly local and smooth: pressure,
log-pressure, temperature, and `n-1` tangent-simplex coordinates are perturbed
while the same admissible mechanical root is tracked. The matrix covers pure
methane, ethane, and propane; CH4/C2, CH4/C3, and ternary mixtures; balanced,
asymmetric, reversed, near-pure, and zero-fraction compositions; and single,
liquid-like, and vapor-like roots. No global root-selection derivative is
claimed.

### Numerical Method

Exact chain rules and independently evaluated cubic partials form the first
layer. A separately written complex-safe PR algebra checks pure, mixing, and
`A/B` derivatives with a `1e-30` imaginary step. Complex values never enter
roots or fugacity. Ordinary real EOS values use central differences at `h`,
`h/2`, `h/4`, and `h/8`; the primary reference is the fixed second-order
Richardson estimate from `h` and `h/2`. Root continuation requires unchanged
root count, ordered/nearest agreement, admissibility, unambiguous distance, and
unchanged mechanical classification.

### Software Engineering

All implementation is verification-only. `derivative_reference.py` does not
import Module 13 and owns ordinary-state reconstruction, safe root tracking,
Richardson logic, isolated complex algebra, and independent cubic/fugacity
algebra. `derivative_verification.py` constructs immutable metrics. The pytest
suite checks tolerances, coverage, determinism, convergence, exclusions,
permutation covariance, conditioning, and adversarial mutations. A separate
module command prints the full extended report. Production source is unchanged.

### Main Equations / Algorithms

- `D(h)=[f(q+h)-f(q-h)]/(2h)` for ordinary real values.
- `D_R=D(h/2)+[D(h/2)-D(h)]/3` is the declared reference.
- `h`, `h/2`, `h/4`, and `h/8` expose second-order behavior and roundoff.
- `F_q+F_Z(dZ/dq)=0` is checked with independently written cubic partials.
- Near zero, `abs_error <= abs_tol + rel_tol*scale` avoids meaningless
  relative-only claims.

### Files Changed

- `tests/derivative_reference.py`
- `tests/derivative_verification.py`
- `tests/test_derivative_verification.py`
- `tests/run_derivative_verification.py`
- `docs/DERIVATIVE_VERIFICATION.md`, `docs/README.md`
- `docs/PROJECT_JOURNAL.md`

### Important Functions / Classes

`ordinary_state`, `richardson_vector`, `pressure_richardson`,
`log_pressure_richardson`, `temperature_richardson`,
`composition_richardson`, `complex_algebra_values`,
`independent_cubic_partials`, `independent_log_fugacity_algebra`,
`run_verification_matrix`, `VerificationState`, `OrdinaryState`,
`RichardsonVectorResult`, `VerificationEntry`, and `VerificationReport`.

### Design Decisions

The reference code duplicates the published rounded PR constants so a defect
in a production helper cannot automatically reproduce itself. Complex-step is
restricted to algebra that contains no real-only decisions. The full root and
fugacity pipeline is verified only through ordinary real recomputation.
Composition columns reconstruct the dependent reference fraction directly.
The zero-fraction boundary coordinate is excluded from central differences and
checked separately with a labeled one-sided formula.

### Bugs / Failure Modes Found

No Module 13 analytical defect was found. Verification infrastructure explicitly
encountered the expected composition-boundary limitation: the zero ethane
coordinate cannot take a negative central perturbation. The near-singular
study also confirmed increasing finite-difference sensitivity as `|F_Z|`
decreases; mathematically large derivatives are not treated as defects.

### Fixes

No production correction was made. The boundary coordinate is classified as
an exclusion rather than forced through an invalid state, and its analytical
mixing derivative is checked by a second-order forward difference. Root-count
changes and ambiguous correspondence raise verification-only errors.

### Verification

The deterministic matrix uses 21 explicit case specifications and 774 scalar
comparisons. The sole excluded central coordinate is
`ternary_zero_ethane:u[1|r=2]`, reason `composition_boundary`; it has a separate
one-sided check. The Module 14 focused suite has 23 passing tests in 2.502
seconds wall time, and the extended report passes in 1.162 seconds wall time.
Module 13's original 41 tests remain unchanged and pass. The full repository
has 760 passing tests in 191.37 seconds pytest time (193.169 seconds wall
time). Ruff, format checking, mypy over 15 source files, and compileall pass.

Maximum regular-domain absolute discrepancies by family are:

- pure alpha/a-alpha T: `2.8874472257633954e-15`
- A: `1.3344880755994382e-13`; B: `3.464589726220879e-14`
- mixing T: `9.90960785651751e-16`; mixing composition:
  `1.2312373343092986e-13`
- Z pressure: `5.676636938289903e-10`; Z temperature:
  `1.474964827358205e-9`; Z composition: `5.953649040435494e-8`
- lnphi pressure: `9.0153684517702e-10`; lnphi temperature:
  `2.2481950988362254e-9`; lnphi composition: `8.223608194413146e-8`

The independent cubic-identity residual is at most
`1.6653345369377348e-16`.

### Important Numerical Regression Values

The Module 10 baseline remains 328 cases with SHA-256
`CBDA39461C9F5B839EF59F60710DF4558C5A588B6C1C90913ECADF099356A27D`.
The pre-edit strict golden comparison reported zero physical drift,
numerical-path, status, termination, missing, and extra changes; 328 notices
were source-commit metadata only.
The post-implementation strict comparison was identical: zero physical drift,
numerical-path, status, termination, missing, and extra changes, with 328
source-commit metadata notices. `baseline.csv` was not regenerated.

### Limitations

This finite deterministic matrix does not establish differentiability across
root switches, global phase smoothness, critical-point correctness,
experimental accuracy, or Newton convergence. Repeated roots are excluded from
ordinary relative-error claims. No nonzero `kij` data, property uncertainty,
or solver globalization is studied.

### Commit / Provenance

Work began from clean `master` commit
`874d00043f07ff2ea69bfcef0189c4f9101f2b1c`. Module 14 is intentionally
uncommitted pending review; no final commit hash is invented.

### Connection to Next Stage

Only after Module 14 passes may Module 15 use these derivatives inside a
safeguarded Newton saturation solver. Module 15 and Newton implementation have
not started.

## Module/Stage X — Name

### Purpose

### Science

### Numerical Method

### Software Engineering

### Main Equations / Algorithms

### Files Changed

### Important Functions / Classes

### Design Decisions

### Bugs / Failure Modes Found

### Fixes

### Verification

### Important Numerical Regression Values

### Limitations

### Commit / Provenance

### Connection to Next Stage
