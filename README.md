# PVT Phase Simulator

`pvt-phase-simulator` is a Python 3.12 educational and portfolio project for
building auditable petroleum-fluid thermodynamics calculations. The current
release implements the Peng–Robinson equation of state for pure fluids and
fixed-composition mixtures. It emphasizes explicit units, immutable inputs,
traceable assumptions, numerical conditioning, and independently specified
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

The equations and their implementation mapping are documented in
[`docs/EQUATIONS.md`](docs/EQUATIONS.md).

## Package structure

```text
src/pvt_phase_simulator/
├── fluid_models.py              # Components, provenance, and mixtures
├── physical_constants.py        # SI gas constant
├── unit_conversions.py          # Reserved; no conversion API yet
└── eos/
    ├── peng_robinson.py         # Pure-fluid parameters, roots, and fugacity
    ├── mixing_rules.py          # Fixed-composition classical mixing rules
    ├── mixture_fugacity.py      # Component fugacity at a supplied mixture root
    └── diagnostics.py           # Advisory, non-blocking EOS diagnostics
tests/                           # Independent references and validation tests
docs/                            # Scientific documentation
data/                            # Future property-database scaffold
notebooks/                       # Exploration scaffold
app/                             # Reserved Streamlit entry point; no UI yet
```

The package includes a `py.typed` marker and exposes inline type information.

## Calculation flow

1. Define immutable `Component` objects and a normalized `FluidMixture`.
2. Calculate pure-component temperature-dependent parameters.
3. Apply the chosen binary-interaction policy and classical mixing rules.
4. Form dimensionless mixture `A_mix` and `B_mix`.
5. Solve the PR cubic and retain roots satisfying `Z > B_mix`.
6. Optionally classify local mechanical stability.
7. Evaluate component fugacity coefficients at a validated cubic root.
8. Evaluate advisory diagnostics separately; diagnostics never modify results.

The mixture fugacity API deliberately accepts stable, unstable, or marginal
genuine roots. It does not choose a globally stable mixture phase.

## Reference components and provenance

The built-in reference objects are methane, ethane, and propane. Their current
critical properties and acentric factors are retained from the original
project without numerical modification. Their metadata is explicitly marked
`provisional`: they are standard approximate engineering values whose exact
source still requires confirmation. They must not be treated as an
authoritative property database.

`ComponentPropertyProvenance` can store source title, author or organization,
edition/version, table/section/record, retrieval date, notes, and verification
status. Scientific values remain separate from citation metadata so the same
model can support a future versioned CSV or TOML database.

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

The current suite contains 284 tests covering ordinary, critical,
near-critical, three-root, spinodal/marginal, zero-pressure, and very-low-
pressure states; pure-component reduction; binary and ternary independent
references; Euler/Gibbs–Duhem invariants; provenance forgery; interaction
policies; and diagnostic non-interference.

## Current limitations

The project does **not** yet implement:

- flash calculations, Wilson K-values, or Rachford–Rice
- phase fractions or phase compositions
- mixture global phase-stability analysis
- bubble point, dew point, or phase envelopes
- reservoir depletion
- Péneloux volume translation or another EOS
- an authoritative versioned property database
- engineering unit conversion functions
- a Streamlit user interface

The current mixture calculations apply to a fixed overall composition and a
specified state/root. Pure-fluid stable-root selection must not be generalized
to multicomponent global phase stability.

Passing tests demonstrates consistency with the documented equations and
regression cases; it does not replace experimental validation, calibrated
binary-interaction data, uncertainty analysis, or peer review for engineering
decisions.
