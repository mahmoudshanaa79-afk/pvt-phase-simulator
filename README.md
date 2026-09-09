# PVT Phase Simulator

`pvt-phase-simulator` is a Python 3.12 educational and portfolio project for
building auditable petroleum-fluid thermodynamics calculations. The current
work implements the Peng–Robinson equation of state for pure fluids,
fixed-composition mixtures, phase-stability trials, a stability-gated
two-phase flash foundation, fixed-temperature saturation pressures, and
natural-temperature phase-envelope branch continuation, an opt-in
pseudo-arclength continuation mode with turning-point diagnostics, local
mixture-criticality derivatives, and a safeguarded fixed-composition mixture
critical-point solver. It
emphasizes explicit units, immutable inputs, traceable assumptions, numerical
conditioning, and independently specified
regression cases.

## Implemented functionality

- Pure-component Peng–Robinson parameters: reduced temperature, kappa, alpha,
  `a`, `b`, `A`, and `B`.
- Scale-aware solution and validation of the Peng–Robinson compressibility
  cubic, including conditioned handling of near-repeated roots.
- Local mechanical classification of roots as stable, unstable, or marginal.
- Pure-fluid fugacity coefficients and lowest-fugacity stable-root selection.
- Immutable fixed-composition fluid mixtures.
- Classical quadratic attraction and linear co-volume mixing rules.
- Symmetric binary interaction coefficients with explicit missing-data policy.
- Component fugacity coefficients at an already selected genuine mixture root.
- Non-blocking numerical-conditioning, model-applicability, and data-quality
  diagnostics.
- A shifted `w = Z - 1` formulation for accurate low-pressure fugacity.
- A Michelsen-style, two-trial tangent-plane-distance stability-analysis
  foundation with Wilson initialization, conditional deterministic fallback,
  and explicit inconclusive outcomes.
- A stability-gated isothermal-isobaric two-phase flash with bracketed
  Rachford–Rice solution, PR fugacity-ratio updates, material-balance checks,
  and immutable iteration history.
- Fixed-temperature bubble- and dew-pressure solvers with Wilson search
  estimates, self-consistent incipient compositions, logarithmic pressure
  bracketing, explicit PR root policies, and immutable failure evidence.
- Fixed-composition bubble/dew branch tracing with continuation-seeded log-K
  correction, secant prediction, adaptive temperature steps, local pressure
  searches, branch-identity checks, and near-critical warning termination.
- Opt-in pseudo-arclength bubble/dew continuation using a dimensionless
  composition/`ln(P)`/`ln(T)` state, SVD tangents, a safeguarded augmented
  Newton corrector, adaptive arclength steps, and geometric turning indicators.
- Local mixture-criticality derivative analysis using orthonormal
  composition-tangent Gibbs curvature, a unique soft eigenmode, and a
  safeguarded fixed-direction cubic derivative. This evaluates specified
  states; it does not locate critical points.
- A fixed-composition mixture critical-point solver in `ln(T)`/`ln(P)` using
  signed Gibbs soft-mode residuals, numerically converged and root-branch-
  continuous Richardson Jacobians, bounded Newton steps, backtracking, and
  fresh final certification.
- Reusable Plotly visualizations for phase envelopes, phase compositions,
  pseudo-arclength traces, experimental validation, criticality residuals, and
  nonlinear-solver diagnostics, with explicit status and unit semantics.
- Experimental validation against 40 reference-quality methane/ethane and
  methane/propane VLE states, including explicit solver-coverage and
  multiple-dew-branch diagnostics with no fitting.

The equations and their implementation mapping are documented in
[`docs/EQUATIONS.md`](docs/EQUATIONS.md).
The first experimental comparison and its limitations are documented in
[`docs/EXPERIMENTAL_VALIDATION.md`](docs/EXPERIMENTAL_VALIDATION.md).

## Streamlit application

An optional Streamlit frontend now provides Overview, Phase Envelope, Critical
Point, Engineering Sweeps, Validation, and Diagnostics views for the verified
methane, ethane, and propane scope. It calls the existing scientific APIs and
Module 21 Plotly figures without changing the v1.0 engine.

```powershell
uv run streamlit run streamlit_app.py
```

The UI is installed as the separate `pvt_phase_simulator_ui` package. The
compatibility command `uv run streamlit run app/streamlit_app.py` also works
from a clean shell without `PYTHONPATH` configuration.

Prerequisites are Python 3.12 or newer and [uv](https://docs.astral.sh/uv/); no
other tooling, service, or account is required. `uv sync --locked` installs the
exact dependency graph recorded in `uv.lock`.

For a bounded localhost startup and HTTP health check, run:

```powershell
uv run python tools/streamlit_smoke.py
```

It selects a free loopback port, runs Streamlit headless, checks the health
endpoint, and always terminates the server it started.

Input validation, explicit calculation actions, stale-result handling, failure
semantics, supported views, and limitations are documented in
[`docs/STREAMLIT_APPLICATION.md`](docs/STREAMLIT_APPLICATION.md).

### Continuous verification and deployment status

[`.github/workflows/quality.yml`](.github/workflows/quality.yml) reproduces the
authoritative gates on a clean Ubuntu runner with Python 3.12, installing from
the locked dependency graph: lockfile check, Ruff, Ruff formatting, mypy,
`compileall`, application import smoke, the full test suite, and the localhost
Streamlit health smoke. It requires no secret and has read-only repository
permissions.

**Public v1.2 deployment:**
<https://pvt-phase-simulator-wpykmumyxwefbv3prht7gv.streamlit.app/>

It is hosted on Streamlit Community Cloud from the `master` branch of
`mahmoudshanaa79-afk/pvt-phase-simulator`, with `streamlit_app.py` as the entry
point, Python 3.12, and `uv.lock` as the dependency source. **No secrets are
stored or required.** It serves the released v1.2 application and remains
subject to every applicability limit recorded in the application itself.

Deployment is not automated. It was a deliberate, separate, human-authorized
step, and no release automation configures or republishes it.
`.github/workflows/quality.yml` verifies only and never deploys. See
[`docs/STREAMLIT_APPLICATION.md`](docs/STREAMLIT_APPLICATION.md) for the hosted
deployment's recorded observations.

## Package structure

```text
src/pvt_phase_simulator/
├── component_models.py          # Immutable component and provenance models
├── component_database.py        # Strict ordered CSV loader and lookup API
├── data/
│   └── component_properties.csv # Packaged runtime property resource
├── fluid_models.py              # Mixtures and database-backed compatibility objects
├── physical_constants.py        # SI gas constant
├── unit_conversions.py          # Explicitly unsupported conversion boundary
├── plotting.py                  # Pure Plotly scientific visualizations
└── eos/
    ├── peng_robinson.py         # Pure-fluid parameters, roots, and fugacity
    ├── mixing_rules.py          # Fixed-composition classical mixing rules
    ├── mixture_fugacity.py      # Component fugacity at a supplied mixture root
    ├── diagnostics.py           # Advisory, non-blocking EOS diagnostics
    ├── phase_stability.py       # TPD trials and conditional fallback starts
    ├── flash.py                 # Stability-gated two-phase flash foundation
    ├── saturation_pressure.py   # Fixed-temperature bubble/dew pressure
    ├── phase_envelope.py        # Natural-temperature branch continuation
    ├── pseudo_arclength.py      # Opt-in geometric branch continuation
    ├── criticality.py           # Local mixture criticality derivatives
    └── critical_point.py        # Safeguarded fixed-composition critical solve
tests/                           # Independent references and validation tests
docs/                            # Scientific documentation
data/
└── component_properties.csv     # Human-review/source-tree property mirror
notebooks/                       # Exploration scaffold
src/pvt_phase_simulator_ui/      # Installed Streamlit application layer
streamlit_app.py                 # Stable Streamlit entrypoint
```

The package includes a `py.typed` marker and exposes inline type information.
The packaged CSV is the runtime resource; the root CSV is its human-review
source-tree mirror. Their byte identity is tested. This duplication is an
intentional current packaging compromise. The nine production Tc/Pc/omega
records have verified source metadata; this traceability status is not a claim
of absolute experimental truth.

## Calculation flow

1. Define immutable `Component` objects and a normalized `FluidMixture`.
2. Calculate pure-component temperature-dependent parameters.
3. Apply the chosen binary-interaction policy and classical mixing rules.
4. Form dimensionless mixture `A_mix` and `B_mix`.
5. Solve the PR cubic and retain roots satisfying `Z > B_mix`.
6. Optionally classify local mechanical stability.
7. Evaluate component fugacity coefficients at a validated cubic root.
8. Evaluate advisory diagnostics separately; diagnostics never modify results.
9. For phase-stability analysis, run distinct vapor-like and liquid-like TPD
   Wilson trials, using bounded deterministic starts only for an inconclusive
   character. This does not calculate phase fractions or equilibrium
   compositions.
10. Only for a conclusively unstable feed, solve the two-phase material balance
    and iterate liquid/vapor PR fugacity equality. Stable and inconclusive feeds
    do not enter the two-phase iteration.
11. At fixed temperature, independently solve a bubble- or dew-pressure
    boundary by coupling an incipient-composition iteration to a bracketed
    pressure root solve. This is a single boundary calculation, not envelope
    tracing.
12. Trace neighboring saturation states in temperature using the previous
    pressure and log-K state, then correct through narrow Module 8 pressure
    searches. Rejected steps and termination evidence remain explicit.
13. When explicitly requested, trace the same saturation manifold with an SVD
    tangent and weighted pseudo-arclength constraint while preserving the
    existing phase-role, triviality, fixed-root, and near-critical safeguards.
14. At a specified mixture state and explicit or stable parent root, optionally
    evaluate the orthonormal Gibbs-stability Hessian, soft composition mode,
    and fixed-direction cubic derivative. No temperature/pressure solve occurs.
15. For an explicitly seeded fixed mixture, optionally solve the simultaneous
    signed soft-curvature and cubic conditions in `ln(T)` and `ln(P)`, with
    bounds, orientation continuity, backtracking, and final revalidation.
16. Convert precomputed phase behavior, validation, criticality, and nonlinear-
    solver results into reusable Plotly figures without changing thermodynamics.

The mixture fugacity API deliberately accepts stable, unstable, or marginal
genuine roots. It does not choose a globally stable mixture phase.

## Reference components and provenance

The built-in reference objects are methane, ethane, and propane. Their critical
properties and acentric factors are sourced from Yang and Richter (2025), DOI
`10.1021/acs.jced.5c00110`, whose supporting table identifies REFPROP as the
original data source. Their property-level metadata is marked `verified` after
exact value, provenance, and pressure-conversion checks.
The strict UTF-8 CSV database stores one row and one provenance record per
property, with stable IDs, deliberate aliases, explicit units, and deterministic
ordering. See the [component-property database design](docs/COMPONENT_PROPERTY_DATABASE_DESIGN.md).

## Units

All calculation APIs currently require SI units:

- temperature: K
- pressure and fugacity: Pa
- molar co-volume: m³/mol
- attraction parameter: Pa·m⁶/mol²
- compressibility factor, reduced temperature, kappa, alpha, `A`, `B`, mole
  fractions, acentric factors, and fugacity coefficients: dimensionless

No automatic runtime unit conversion is currently performed. Primary-source
pressure conversion evidence (kPa → Pa) is retained in the property database.

## Root validation and classification

Supplied roots must be finite, satisfy `Z > B`, meet a scale-aware cubic
residual tolerance, and lie near a computed admissible root. Root solving uses
residual verification and conditioning-aware deduplication.

Mechanical classification uses the sign of the fixed-temperature pressure
derivative. A float64 cancellation band is reported as `marginal`; it is not
forced into stable or unstable. Mechanical stability is local and is not the
same as global mixture thermodynamic stability.

## Binary-interaction policies

- `DEFAULT_ZERO` preserves the educational default `k_ij = 0` for omitted
  pairs and records every defaulted pair as a data-quality assumption.
- `REQUIRE_ALL_PAIRS` requires every unique off-diagonal pair. Explicit zero
  values count as supplied data.

Names are exact and case-sensitive, diagonal interactions must be exactly
zero, and off-diagonal mappings must be symmetric. Stored interaction and
policy provenance is immutable and is exposed by high-level mixture results.
Defaulting `k_ij` to zero is an approximation, not a universal physical fact.

## Diagnostics

Diagnostics are immutable advisory records with a code, severity, category,
message, and optional numerical value. Current checks cover nominal critical
region sensitivity, the alpha-correlation turning region, and defaulted binary
interactions. Diagnostics do not clamp inputs, reject mathematically valid
states, select phases, or alter scientific results.

## Development and verification

Install from the repository root with `uv`:

```powershell
uv sync --locked
uv run pytest --durations=25
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run python -m compileall src
```

The test suite covers ordinary, critical,
near-critical, three-root, spinodal/marginal, zero-pressure, and very-low-
pressure states; pure-component reduction; binary and ternary independent
references; Euler/Gibbs–Duhem invariants; provenance forgery; interaction
policies; and diagnostic non-interference.

## Current limitations

The project does **not** yet implement:

- three-phase or multiphase flash calculations
- accelerated, damped, or globally convergent flash algorithms
- exhaustive/global phase-stability certification beyond the bounded
  Wilson-plus-fallback Michelsen-style trials
- critical-locus continuation or a supported-fluid temperature-fold
  regression (the pseudo-arclength core has generic-fold and CH4/C3
  pressure-turning evidence)
- reservoir depletion
- Péneloux volume translation or another EOS
- experimental authentication and uncertainty quantification beyond the
  verified bibliographic traceability of component-property values
- engineering unit conversion functions

Near a mixture critical point, the bounded stability trials can collapse to the
trivial solution and falsely classify a state as stable. In the independently
audited 50/50 methane/propane regression at `P = Pc`, this produced an observed
false-stable band of approximately 7.86 K below that mixture's audited critical
temperature; this width is specific to that audited example and must not be
generalized to other fluids, compositions, or pressures, so near-critical
stability classifications require caution.

The current flash and saturation inner solves use undamped successive
substitution. Saturation calculations search only the requested finite pressure
interval and can return `NOT_FOUND` or `INCONCLUSIVE`; they do not establish a
globally complete phase diagram. Envelope tracing defaults to natural
temperature continuation. The opt-in pseudo-arclength mode can cross regular
geometric turns but still terminates at root-role loss or indistinguishable
phase states; near-critical diagnostics are not exact critical points. Pure-fluid stable-root
selection must not be generalized to multicomponent global phase stability.
The local criticality API is restricted to fixed, differentiable cubic-root
branches and the active open simplex; it reports root ambiguity, mode
degeneracy, excessive Hessian antisymmetry, and unavailable symmetric
perturbations instead of crossing them.
The critical-point solver inherits those local restrictions, requires an
explicit seed and finite bounds, and currently has physical regression evidence
only for the verified methane/propane binary with default-zero interactions. A
positive quartic regularity diagnostic and global basin certification remain
outside the current result.

Passing tests demonstrates consistency with the documented equations and
regression cases; it does not replace experimental validation, calibrated
binary-interaction data, uncertainty analysis, or peer review for engineering
decisions.
