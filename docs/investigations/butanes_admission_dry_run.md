# Butanes admission: dry run of the final step

Web session, 8 November 2026. Draft only: nothing here is merged, and every
butane number below comes from **provisional** CoolProp 6.6.0 constants, not
from Yang & Richter (2025) Table 5. All of them will change once the Table 5
values are entered.

## What ran

In a throwaway copy of the `admit-butanes` branch:

```bash
uv run python tools/admit_butanes.py --provisional --root <copy> --report dry_run.json
```

It finished with exit code 0 in about 8 minutes on the web container (two
regenerations of the Module 17 record). The command:

1. read `data/butanes_table5_values.json` (status `provisional`);
2. regenerated the record on this machine **before** adding any row;
3. appended six provisional rows to both component-property CSVs;
4. regenerated the record again, now with the second data file
   `data/experimental/may_2015_butanes_vle.csv` (36 points);
5. required the methane–ethane and methane–propane rows of runs 2 and 4 to be
   byte-identical (they were);
6. wrote the committed C1–C3 rows and summary entries unchanged, followed by
   the 36 butane rows and two butane summary entries;
7. checked that the written C1–C3 rows equal master's and that
   `tests/golden_master/baseline.csv` is unchanged;
8. refreshed the hash pins in `tests/test_validation_metrics.py` and
   `tests/test_app_adapters.py`.

## Identity proof

| Check | Result |
|---|---|
| C1–C3 rows of the written record equal master's, byte for byte | yes |
| C1–C3 rows unchanged by admitting the butanes (same machine, before vs after) | yes |
| Golden master SHA-256 before and after | `530C667A…A7D2BE`, unchanged |
| A fresh regeneration on this machine reproduces the committed C1–C3 rows bit for bit | **no** |

The last row is not caused by the butanes. Regenerating the record from
unmodified `master` on this machine also changes the last digit of some floats
(80 lines of the CSV and 114 lines of the summary) and two iteration counts.
The committed record was produced on another machine. For that reason the
command compares two runs on the same machine, then keeps master's C1–C3 rows
exactly, so the result does not depend on where the final step runs.

## Provisional butane results

Source: May et al. (2015), the same ThermoML record as the C1–C3 data
(normalized CSV SHA-256 `1FBC16D9…1D70450`). Per-point values are in
`butanes_admission_dry_run.csv`. Default kij = 0 (no fitted interaction
parameters exist for these pairs).

| System | Points | Bubble converged | Bubble AARD | Bubble max abs. error | Bubble bias | Dew converged |
|---|---|---|---|---|---|---|
| methane + isobutane | 17 | 17 | 3.45 % | 7.62 % | −3.45 % | 0 |
| methane + n-butane | 19 | 19 | 3.56 % | 7.77 % | −2.59 % | 0 |

Every dew calculation stopped with the engine's own reason:

- 34 states: *Multiple apparent saturation-pressure roots were observed.*
  (`inconclusive`)
- 2 methane + n-butane states: *No trustworthy saturation-pressure bracket was
  found.* (`not_found`)

This matches the known dew behaviour of the C1–C3 systems
(`docs/DEW_INVESTIGATION.md`). It is reported, not hidden.

## Test suite after admission (in the copy)

First run (8 November): 1791 passed, 20 failed and 22 errors. Several
consumers assumed a single data file and two systems. They were changed on
this branch (9 November) so that they work both before and after admission:

| Consumer | Change |
|---|---|
| `pvt_phase_simulator_validation/module17_adapter.py` | Keeps to the required C1–C3 source. Any other record rows must all belong to the hash-verified butane data file and match it exactly, or the adapter refuses as before. |
| Point, system and component counts in the tests | Follow `butanes_admitted()`: 40 or 76 points, 2 or 4 systems, 3 or 5 database components. |
| `tests/test_validation_metrics.py` summary check | Compares the required systems, and proves that every other system is a butane system. |
| `tools/kij_study_report.py` reproduction table | Stays on the required systems; the study ran the butanes only on provisional constants. |
| `tests/test_hidden_dew_root_check.py` | Stays on the required systems; a butane check is plan step 6. |
| `tests/test_experimental_validation.py` | Accounts for both data files; a system with no converged state must report undefined (None) metrics, not 0. |

Second dry run (9 November, fresh copy of the branch): same result hashes as
the first, and the full suite in the admitted copy gave **1860 passed, 1
failed**. The one failure is the expected
`test_every_property_exposes_exact_verified_source_provenance`, because
provisional rows are not verified.

**Mechanics check of the final mode** (throwaway copy, placeholder values,
nothing committed). The rows `tools/admit_butanes.py` writes in final mode,
with `original_source_as_printed` = `REFPROP`, plus its extension of the
test's source tables, make that test pass. The command now refuses any other
original source. The test expects "originally taken from REFPROP", like the
C1–C3 rows, and changing that expectation is the owner's decision.

On the branch itself, with nothing admitted, the full suite passes (1861).
