# PVT Phase Simulator

`pvt-phase-simulator` is a Python 3.12 educational and portfolio project for
building auditable petroleum-fluid thermodynamics calculations. The current
work implements the Peng–Robinson equation of state for pure fluids,
fixed-composition mixtures, phase-stability trials, a stability-gated
two-phase flash foundation, fixed-temperature saturation pressures, and
natural-temperature phase-envelope branch continuation. It
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

The equations and their implementation mapping are documented in
[`docs/EQUATIONS.md`](docs/EQUATIONS.md).

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
└── eos/
    ├── peng_robinson.py         # Pure-fluid parameters, roots, and fugacity
    ├── mixing_rules.py          # Fixed-composition classical mixing rules
    ├── mixture_fugacity.py      # Component fugacity at a supplied mixture root
    ├── diagnostics.py           # Advisory, non-blocking EOS diagnostics
    ├── phase_stability.py       # TPD trials and conditional fallback starts
    ├── flash.py                 # Stability-gated two-phase flash foundation
    ├── saturation_pressure.py   # Fixed-temperature bubble/dew pressure
    └── phase_envelope.py        # Natural-temperature branch continuation
tests/                           # Independent references and validation tests
docs/                            # Scientific documentation
data/
└── component_properties.csv     # Human-review/source-tree property mirror
notebooks/                       # Exploration scaffold
app/                             # Reserved Streamlit entry point; no UI yet
```

The package includes a `py.typed` marker and exposes inline type information.
The packaged CSV is the runtime resource; the root CSV is its human-review
source-tree mirror. Their byte identity is tested. This duplication is an
intentional current packaging compromise, and the values remain provisional.

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

The mixture fugacity API deliberately accepts stable, unstable, or marginal
genuine roots. It does not choose a globally stable mixture phase.

## Reference components and provenance

The built-in reference objects are methane, ethane, and propane. Their current
critical properties and acentric factors are retained from the original
project without numerical modification. Their metadata is explicitly marked
`provisional`: their exact authoritative sources still require confirmation.
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

No automatic unit conversion is currently performed.

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
- exact critical-point or critical-locus solving
- pseudo-arclength or demonstrated retrograde continuation
- reservoir depletion
- Péneloux volume translation or another EOS
- authoritatively sourced component-property values (the database
  infrastructure exists, but its current values remain provisional)
- engineering unit conversion functions
- a Streamlit user interface

The current flash and saturation inner solves use undamped successive
substitution. Saturation calculations search only the requested finite pressure
interval and can return `NOT_FOUND` or `INCONCLUSIVE`; they do not establish a
globally complete phase diagram. Envelope tracing uses natural temperature
continuation and may terminate near folds or indistinguishable phase states;
near-critical diagnostics are not exact critical points. Pure-fluid stable-root
selection must not be generalized to multicomponent global phase stability.

Passing tests demonstrates consistency with the documented equations and
regression cases; it does not replace experimental validation, calibrated
binary-interaction data, uncertainty analysis, or peer review for engineering
decisions.
