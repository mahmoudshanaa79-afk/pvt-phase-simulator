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

`uv run pytest -q -n auto` in the admitted copy: 1791 passed, 20 failed and
22 errors. Most of them are expected, because several consumers assume a
single data file and two systems:

| Group | Tests | Cause | What the final step still needs |
|---|---|---|---|
| Provenance gate | `test_every_property_exposes_exact_verified_source_provenance` | provisional rows are not verified | none: the final run writes verified Table 5 rows and extends the test's source tables |
| Component list | `test_default_database_loads_all_components_in_stable_order`, `test_model_scope_reads_recorded_component_and_validation_provenance` | the expected component list has three names | add the two butanes to the expected lists |
| Validation adapter and report | 9 in `test_validation_module17_adapter.py`, 22 errors and 1 failure in `test_validation_report.py` and `test_validation_metrics.py` | `pvt_phase_simulator_validation/module17_adapter.py` reads one manifest and requires the record's point IDs to equal that file's | let the adapter read the second dataset and manifest when the butanes are admitted, with its own provenance block |
| Point counts | 2 in `test_experimental_validation.py`, 2 in `test_plotting.py` | the tests load only the main dataset (40 points; the record now has 76) | load both datasets when admitted |
| Hidden dew roots | `test_the_check_covers_exactly_the_hidden_root_states` | the butane dew states join the hidden-root set | rerun `tools/run_hidden_dew_root_check.py` with butane entries (plan step 6) |
| kij study report | `test_the_report_renders_from_the_committed_files` | a butane system with no dew results gives `None` metrics that the report formats as numbers | render undefined metrics as "undefined" |

So the command does its job (rows, record, identity, pins), but **a fully green
suite after admission needs the consumer changes in the right-hand column
first**. They can be built and tested on the provisional values in a later
session, on this same draft branch.
