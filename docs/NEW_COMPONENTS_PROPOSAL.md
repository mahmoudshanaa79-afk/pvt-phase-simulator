# Next components: butanes first (proposal)

Status: **awaiting owner decision** (1 November 2026). Nothing here changes the
engine, `data/` or the validation record. Every number below comes from a
committed tool and its CSV, and `tests/test_butane_preview_and_solver_gaps.py`
recomputes the key values from the engine.

## Recommendation in one paragraph

Add **isobutane and n-butane** next, before CO2 or N2. The data are already in
hand: May et al. (2015), the source of the current CH4+C2 and CH4+C3 record,
also measured CH4+isobutane and CH4+n-butane. The same NIST ThermoML record
(the file whose SHA-256 is already pinned in the manifest) holds both. The
existing extractor reads them with one opt-in change. CO2 and N2 need a new
experimental source with stated uncertainties, which has not been chosen yet.

The preview also found two solver behaviours that matter more than the new
components. They are proposed below as **P7** and **P8**, and both affect the
current record:

- P7: 9 `not_found` bubble states have a real root.
- P8: 2 CH4+C2 dew results reported as unique have a second root. One of them,
  CH4+C2 013, is the record's worst dew result (−25.8 %), and its other root
  is 1.4 % from the measurement.

## 1. The butane data

| | CH4 + isobutane | CH4 + n-butane |
|---|---|---|
| ThermoML datasets (pressure, vapour) | 5, 6 | 7, 8 |
| Rows in the archive | 18 | 20 |
| Exact repeats | 1 (243.6 K, x = 0.5523) | 1 (244.52 K, x = 0.4601) |
| Distinct measured states | 17 | 19 |
| Temperatures | 203–273 K, one 243.6 K isotherm | 203–273 K, one 244.5 K isotherm |

**Repeats.** Each binary lists one measurement twice, identical in T, x, P, y
and both uncertainties. It is one measurement printed in two places, not a
repeat experiment. `tools/extract_may_2015_thermoml.py` therefore gained an
opt-in, `skip_identical_duplicates`, which keeps the first copy. A repeated key
with any differing value is still rejected. The default behaviour is unchanged,
and the production CSV it writes is byte-identical (SHA-256 `04ED00B6…07BD`).

The normalized points are in `docs/investigations/butane_preview_points.csv`.
As for the production data, the raw ThermoML file is not redistributed.

## 2. Critical constants: provisional

The project's source of record for C1–C3 is Yang & Richter (2025),
J. Chem. Eng. Data, doi:10.1021/acs.jced.5c00110, Table 5. That paper is behind
a paywall and could not be checked from here. The preview therefore uses
**provisional** values from CoolProp 6.6.0, which evaluates the Bücker–Wagner
(2006) reference equations of state:

| Component | T_c (K) | p_c (Pa) | ω |
|---|---|---|---|
| isobutane | 407.817 | 3 629 000 | 0.183532 |
| n-butane | 425.125 | 3 796 000 | 0.20081 |

For C1–C3 CoolProp reproduces the database's T_c and p_c exactly, but not
every ω: ethane is 0.099 in CoolProp and 0.0995 in Yang & Richter. **Before
these rows enter `data/component_properties.csv`, the owner (or anyone with
journal access) should read the four butane values from Yang & Richter Table 5.**
If they differ, the preview should be rerun with them.

## 3. What PR (kij = 0) does on the butane data

Production defaults throughout (scanning solver, Newton off, kij = 0), the same
path as Module 17. Results: `docs/investigations/butane_preview.csv`, written by
`tools/run_butane_preview.py`.

| | CH4 + isobutane | CH4 + n-butane |
|---|---|---|
| Bubble: converged | 17 of 17 | 17 of 19 (2 `not_found`, see P7) |
| Bubble pressure AARD (bias) | 3.45 % (−3.45 %) | 3.51 % (−3.36 %) |
| Bubble pressure within U | 1 of 17 | 1 of 17 |
| Bubble vapour composition within U | 10 of 17 | 17 of 17 |
| Dew: converged unique | 0 of 17 | 1 of 19 (wrong root, see P8) |
| Dew: ambiguous (`inconclusive`) | 17 | 16 |
| Dew: `not_found` | 0 | 2 |

For comparison, the committed CH4+C3 bubble AARD is 1.03 %. At kij = 0, PR
systematically under-predicts the butane bubble pressures by about 3.5 %. That
is the pattern a non-zero kij would be expected to correct, so the kij study
running in the web session (`P6: kij`) should include the butanes once they are
admitted. Vapour compositions are reproduced well. As for CH4+C3, almost every
measured dew state has two PR dew roots, so a single dew pressure is not well
posed there.

## 4. P7 (proposed): refine boundaries when the scan finds no root

**Finding.** P2 walks the grid intervals between a converged and a failed node
only when the scan has already found exactly one root. When the scan finds none,
nothing is walked and the result is `not_found`. Near a mixture critical point
the inner calculation collapses to the trivial solution at the grid node just
above the root, so a real root hides in exactly such an interval.

Example, CH4 + n-butane, x = 0.66, 244.48 K: grid nodes at 8.66 MPa (converged,
objective +0.0072) and 10.0 MPa (failed). The root at 8.86 MPa lies between
them, and the default result is `not_found`.

**Evidence on the current record** (`tools/run_empty_scan_whatif.py`,
`docs/investigations/empty_scan_whatif.csv`). The tool replays the P2 walk on
every default `not_found` state of the Module 17 data, with the same step count
and tolerance and the engine's own pressure evaluation:

- All **9** `not_found` bubble states (CH4+C2 009, 012, 013, 015, 016, 017;
  CH4+C3 013, 014, 015) have exactly one root next to a failed node.
- Each root is a real equilibrium state: fugacity residual ≤ 1e-10, and the
  vapour differs clearly from the liquid.
- For 7 of the 9, the engine's independent Newton option finds the same
  pressure to 1e-8 relative. For CH4+C2 012 and 017, Newton also fails.
- Against the measurements: −2.6 % to +1.3 % in pressure, and the vapour CH4
  fraction is within 0.008 of the measured value.
- The 4 `not_found` dew states have no such root, and P7 would leave them as
  they are.
- For CH4 + n-butane, P7 would recover both `not_found` bubble states:
  10.58 MPa (+4.5 %) and 10.26 MPa (+3.5 %), both equal to the Newton result.

**Proposed change.** Run the existing P2 walk also when the grid finds no root.
If it finds exactly one sign change, solve it as today and report it. If it
finds more than one, report `inconclusive` with `MULTIPLE_SATURATION_ROOTS`. If
it finds none, keep `not_found`.

**Effect.** Bubble coverage in the validation record would grow by 9 states,
all in the near-critical 243.6 K isotherm, which is the region the record
covers worst today. The Module 17 artifacts would need to be regenerated.

**Approval needed.** This edits `saturation_pressure.py` and regenerates
`docs/validation/`, so it needs the owner's explicit approval.

## 5. P8 (proposed): the P2 walk stops one step short

**Finding.** CH4 + n-butane state 008 (244.48 K, measured 10.132 MPa,
y = 0.9406). The default dew solve reports a converged, unique root at
0.570 MPa (−94 %). P2 walked the boundary interval: the evaluations from 10.0
to 10.55 MPa all converged, with the objective falling to +0.0011. The inner
calculation then failed at 10.59 MPa, and the walk stopped there, one step
before the sign change at about 10.6 MPa.

Independent evidence that the second root exists comes from a route that does
not use the dew solver at all. Following PR's bubble isotherm with the Newton
option, the vapour equals the measured y = 0.9406 at x = 0.77846 and
**10.610 MPa** (residual 1e-13). That is PR's upper dew point for this vapour,
+4.7 % from the measurement. So the production solver labels the wrong root of
two as unique.

**Proposed change** (to be designed with the owner). When the walk meets a
failed evaluation, do not stop. Continue the remaining steps of that interval,
so that a sign change beyond an isolated failure is still seen. Alternatively,
when the last converged objective is within a small margin of zero, report
`inconclusive` instead of unique.

**Audit of the current record.** See section 6: the same mechanism affects
two CH4+C2 dew results in the published record.

## 6. Do the 13 "unique" dew results in the current record have the same problem?

`tools/run_dew_uniqueness_audit.py` (output
`docs/investigations/dew_uniqueness_audit.csv`) checks every dew state that the
validation record counts as unique: 12 CH4+C2 states and CH4+C3 009. For each
one it traces PR's bubble isotherm at that temperature and counts where the
isotherm's vapour CH4 fraction crosses the measured y. This route is
independent of the dew solver.

**Result: 2 of the 13 have a second PR dew root that the solver misses. Two
more cannot be settled by this route.**

| State | T (K) | Measured (MPa) | Reported root | Isotherm crossings |
|---|---|---|---|---|
| CH4+C2 009 | 243.60 | 5.094 | 5.187 (+1.8 %) | 5.187 and **6.748 (+32.5 %)** |
| CH4+C2 013 | 243.60 | 6.885 | 5.105 (−25.8 %) | 5.106 and **6.790 (−1.4 %)** |
| CH4+C2 014, 017 | 243.61 | 3.718, 6.691 | one root each | one each, but the converged isotherm stops at 6.627 MPa, below 017's measured pressure: **unresolved** |
| the other 9 | 203–243.62 | | | one, at the reported root (within interpolation) |

The second roots of 009 and 013 rest on two converged PR bubble states at
243.6 K, with residuals ≤ 1.6e-13:

- x = 0.61: 6.626 MPa, y = 0.7206;
- x = 0.64: 6.811 MPa, y = 0.7112.

Both measured vapours (y = 0.7144 and 0.7123) lie between these two values, so
PR's isotherm reaches them again between 6.63 and 6.81 MPa. The bubble solves at
x = 0.62 and 0.63 fail, so the crossings are interpolated, not solved. On the
dew side the objective falls smoothly to +0.0004 on converged evaluations and
changes sign only where the inner calculation stops converging. This is the
same P8 mechanism as the butane case.

**What this means for the current record.**

- 009 and 013 should be reported as ambiguous, not unique.
- CH4+C2 013 is the worst dew result in the record (−25.8 %). It is a
  wrong-root pick, not a model error: the other root is 1.4 % from the
  measurement.
- The CH4+C2 dew AARD of 5.34 % over 12 states would become an AARD over at
  most 10 states.
- Correcting this needs P8 or an equivalent check, and the regeneration of the
  frozen artifacts, so it waits for the owner's approval. Until then the record
  stays as published, and this document is where the issue is recorded.

## 7. What the owner decides

1. **Butanes.** Approve adding isobutane and n-butane to `data/` once their
   Yang & Richter values are read? If yes, the experimental rows would join the
   validation record and be regenerated with the existing tooling, and the app's
   component list would grow.
2. **P7.** Approve refining boundaries when the scan finds no root? This adds
   9 bubble results to the current record.
3. **P8.** Approve designing a walk that does not stop at the first failed
   evaluation? This would change CH4+C2 dew 009 and 013 in the current record
   from unique to ambiguous. It is the most important item here, because it
   corrects a published result.
4. **CO2 and N2.** Later. They need a new experimental source with stated
   uncertainties, which has not been chosen yet.

When the kij study (P6, web session) merges, P7 and P8 will be added to
`docs/ENGINE_CHANGE_PROPOSALS.md` next to it.
