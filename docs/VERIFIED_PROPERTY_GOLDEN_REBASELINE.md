# Verified-Property Golden Rebaseline

## Purpose

Module 16.2 intentionally replaces the scientifically stale provisional-
property numerical regression baseline with output generated from the audited
VERIFIED methane, ethane, and propane property state. It changes regression
expectations only. It introduces neither new property data nor new EOS, flash,
stability, saturation, or continuation mathematics.

The golden master is a numerical regression reference. It is **not
experimental validation**.

## Baseline identity and generation

| Item | Value |
| --- | --- |
| Old baseline SHA-256 | `CBDA39461C9F5B839EF59F60710DF4558C5A588B6C1C90913ECADF099356A27D` |
| Old scientific state | Pre-Module-16.1 provisional component properties |
| New baseline SHA-256 | `530C667AA70EF1EA182F4EDB98624A0A9B9908F149354276CDAC44A87EA7D2BE` |
| New scientific state | Nine independently audited VERIFIED component properties |
| Generation source commit | `b711645fcd6141e5c4ecd02867d4d74b0e9ad1f8` |
| Case count | 328 |

The normal production generator created two independent temporary candidates:

```console
uv run python tests/golden_master/generate.py --output <temporary-candidate>
```

Both candidates had the new SHA-256 above, identical row order, and
byte-identical contents. The first verified candidate was then adopted without
manual row edits. Git history preserves the exact old baseline; no redundant
tracked copy was added.

## Scientific justification and reconciliation

Module 16.1 independently sourced, audited, and approved the property
migration before this rebaseline. The old-to-candidate comparison exactly
reproduced its committed evidence in
`PROPERTY_SOURCE_MIGRATION_GOLDEN_IMPACT.csv`:

- 322 cases and 1,503 fields with physical-result drift;
- 37 cases and 48 numerical-path field changes;
- 24 `inner_iterations`, nine `outer_iterations`, and 15
  `rejected_attempts` changes;
- zero status changes and zero termination changes; and
- zero missing cases and zero extra cases.

Case IDs, physical field paths, numerical-path field paths, per-case counts,
and status/termination flags reconcile exactly with the impact CSV. There are
zero omitted generated changes and zero evidence rows absent from generation.
The path changes contain only the three bookkeeping fields listed above; there
are no changes to fallback use, correction source, phase or branch identity,
accepted-point count, diagnostics, failure reason, convergence status, or
termination reason.

The six cases without physical-field drift remain structured `NOT_FOUND`
results and therefore have no converged pressure, composition, or root fields
to move:

- `bubble_ch4_c2_50_50_250k`
- `bubble_ch4_c2_80_20_250k`
- `bubble_ch4_c2_c3_60_30_10_250k`
- `bubble_ch4_c2_c3_80_10_10_250k`
- `bubble_ch4_c3_80_20_250k`
- `dew_ch4_c2_80_20_250k`

The last two have only the already-reviewed `inner_iterations` bookkeeping
change; their status and failure meaning are unchanged.

Representative verified-property baseline results include CH4/C3 60/40 dew at
250 K at `575360.2360506197 Pa`, CH4/C3 60/40 bubble at 250 K at
`7391642.208227274 Pa`, and the pure-methane bubble-envelope 170 K endpoint at
`2347774.2603316954 Pa`. The independently pinned Newton value for the last
state is `2347774.2603319585 Pa`; the two agree within the unchanged golden
pressure tolerance.

## Canonical anchoring and strict verification

The Newton saturation and envelope regressions that temporarily used inline
verified-property literals now again resolve expected physics by canonical
case ID from `baseline.csv`. Newton remains enabled, and the pressure,
composition, root, phase-role, and termination assertions retain their prior
tolerances and coverage.

Strict comparison of current production against the adopted baseline reports
zero physical drift, zero numerical-path drift, zero status/termination drift,
and zero missing/extra cases. Golden infrastructure tests continue to protect
schema, ordering, unique semantic IDs, category/status representation,
deterministic serialization, and deliberate mutation detection.

Verification passed with 19 golden-infrastructure tests, 43 focused safety and
phase-identity tests, 41 Module 13 derivative tests, 23 Module 14 focused tests,
and the Module 14 extended matrix of 21 specifications and 774 comparisons
with one documented boundary exclusion. The complete repository passed all 965
tests. Ruff lint and formatting, mypy over 17 source files, compileall, and
`git diff --check` also passed. Post-change generation remained byte-identical
to the canonical baseline at the new SHA-256.

## Known limitation

The CH4/C2 50/50 bubble calculation at 260 K remains a known numerical
reachability limitation. Independent work locates a physical solution near
`6735786.55695833 Pa`, but production's deterministic 81-point logarithmic
pressure scan misses a trustworthy bracket and safely returns structured
`NOT_FOUND` with `SATURATION_BRACKET_NOT_FOUND`. The canonical baseline does
not fabricate a converged state, and Module 16.2 does not change the solver.

The baseline inherits the scope of its 328 deterministic cases and their
documented tolerances. VERIFIED property traceability is not experimental EOS
validation, uncertainty quantification, or binary-interaction calibration.
The deferred fixed-grid reachability improvement and golden `source_commit`
notice-noise cleanup remain outside Module 16.2. Module 17 has not started.
