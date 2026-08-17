# Numerical golden master

This directory contains the deterministic, versioned numerical baseline for the
completed PVT simulator. It answers whether physical results, solver paths,
statuses, termination reasons, or branch selection changed.

The golden master protects numerical behavior relative to the independently
audited baseline. It is not experimental validation.

`cases.py` defines stable pure-PR, binary, ternary, order-reversal,
zero-fraction, near-pure, stability, flash, saturation, continuation-only, and
short phase-envelope cases. `baseline.csv` is authoritative, text based, and
stores float64 values using Python round-trip `repr` formatting. Vectors are
compact deterministic JSON in component order. Envelope rows preserve every
accepted point in continuation order and every rejected correction attempt;
that list position is the deterministic branch subrecord index.

Generate a review file without touching the baseline:

```console
uv run python tests/golden_master/generate.py --output build/golden-master.csv
```

Canonical replacement is intentionally explicit:

```console
uv run python tests/golden_master/generate.py --output tests/golden_master/baseline.csv --replace-canonical
```

Compare current calculations (use `--strict-path` to fail on path changes):

```console
uv run python tests/golden_master/compare.py --strict-path
```

Pressure uses relative tolerance `1e-11`; composition absolute `1e-10`; log K
absolute `1e-9`; roots absolute `1e-11`; beta absolute `1e-9`. Calculation
type, component order, statuses, termination/failure reasons, and diagnostics
are exact. Diagnostics compare as sets. Iterations, fallback use, correction
source, and rejected attempts are recorded as numerical-path information but do
not fail by default. Environment metadata changes are formatting/platform
noise. Within-tolerance float changes are reported as non-failing formatting
noise rather than silently discarded. A status, termination, branch, missing
case, or extra case is never noise.

Never update silently. Regenerate twice, confirm byte identity in one
environment, run the comparator, inspect every classified change, run the full
repository checks, and obtain independent review before accepting any physical
result drift. Run this gate before and after solver changes, before release or
audit, and in CI when runtime is acceptable. Normal pytest runs unit-test the
infrastructure but intentionally do not regenerate the full baseline.
