# Butanes admission plan (isobutane and n-butane)

**Status: plan only, waiting for two things from the owner.**

1. The six Yang & Richter (2025) Table 5 values: T_c, p_c and ω for
   n-butane and isobutane (doi:10.1021/acs.jced.5c00110).
2. Approval to edit the frozen paths listed in step 1 to step 4 below.

Nothing in this plan has been applied. Every step is written so it can be done
mechanically once the values and the approval arrive. The evidence for adding
the butanes is in `docs/NEW_COMPONENTS_PROPOSAL.md`. Its butane preview ran on
provisional CoolProp constants and on the solver before P7 and P8, so all of its
numbers will change.

## Values to fill in

Replace each `‹…›` with the Table 5 value exactly as printed. Record the
printed unit, then convert the same way the methane rows do: 1 kPa = 1000 Pa,
written with one decimal in Pa.

| Component | T_c (K) | p_c as printed | p_c (Pa) | ω |
|---|---|---|---|---|
| isobutane (2-methylpropane, CAS 75-28-5) | ‹Tc› | ‹pc› kPa | ‹pc×1000› | ‹ω› |
| n-butane (butane, CAS 106-97-8) | ‹Tc› | ‹pc› kPa | ‹pc×1000› | ‹ω› |

Then compare the values with the provisional CoolProp constants of the preview
(`tools/run_butane_preview.py`, `PROVISIONAL_COMPONENTS`). Record the
differences in the PR description. A difference does not block admission: the
Table 5 value is the source of record.

## Step 1: component database (frozen: `data/`, `src/pvt_phase_simulator/`)

The database exists twice and the two copies must stay identical:
`data/component_properties.csv` and the packaged copy
`src/pvt_phase_simulator/data/component_properties.csv` (`cmp` reports no
difference today).

Add six rows to both files: three properties (`critical_temperature`,
`critical_pressure`, `acentric_factor`) for each of two components. Copy every
column from the matching methane row, changing only the identity and value
fields:

| Column | isobutane | n-butane |
|---|---|---|
| `component_id` | `isobutane` | `n_butane` |
| `canonical_name` | `Isobutane` | `n-Butane` |
| `aliases` | `iC4\|i-C4H10\|2-methylpropane` | `nC4\|n-C4H10\|butane` |
| `value`, `unit` | Table 5 value; K, Pa or dimensionless as in the methane rows | same |
| `source_status` | `verified` | `verified` |
| `property_source_identity` | `Yang & Richter (2025) Table 5; Isobutane; CAS RN 75-28-5; <property>; <original source as printed>` | same pattern, `n-Butane; CAS RN 106-97-8` |
| `notes` | `Primary article Table 5 independently inspected; …` (say who read it and when) | same |
| `original_unit`, `conversion` | `kPa`, `1 kPa = 1000 Pa` for p_c only | same |

`component_id` values must match the extractor's heavy-component ids
(`isobutane`, `n_butane` in `tools/extract_may_2015_thermoml.py`,
`BUTANE_SYSTEMS`).

Tests that change:
- `tests/test_component_database.py` (row counts, the verified-component list);
- `tests/test_validation_metrics.py` and `tests/test_app_adapters.py`, which pin
  the database hash or file list (search for `component_properties.csv`). The
  pinned hashes are regenerated from the new file and recorded in the PR.
  Nothing is loosened.

## Step 2: engine component objects (frozen: `src/pvt_phase_simulator/`)

- `fluid_models.py`: add `ISOBUTANE` and `N_BUTANE` next to
  `METHANE = DEFAULT_COMPONENT_DATABASE.get_component("methane")`.
- `experimental_validation.py`: add to `SYSTEM_COMPONENTS`:
  `"ch4_ic4": ("methane", "isobutane")` and `"ch4_nc4": ("methane", "n_butane")`.
  Add the two components to `COMPONENT_OBJECTS`.

## Step 3: validation dataset (frozen: `data/experimental/`)

Both systems come from the **same** NIST ThermoML record as the production data.
Its SHA-256 `77630E90…9662` is already pinned in
`data/experimental/may_2015_source_manifest.json`. The extractor reads them
with the opt-in that already exists:

```python
extract_normalized_rows(
    document,
    SYSTEMS + BUTANE_SYSTEMS,
    {**COMPOUNDS, **BUTANE_COMPOUNDS},
    skip_identical_duplicates=True,
)
```

- `skip_identical_duplicates=True` drops the single exact repeat in each butane
  binary: 243.6 K, x = 0.5523 for isobutane, and 244.52 K, x = 0.4601 for
  n-butane. A repeated key with any differing value is still rejected.
  Expected rows: 17 (CH4+iC4) and 19 (CH4+nC4).
- Decision for the owner: either extend the existing CSV, which changes its
  SHA-256 `04ED00B6…07BD` in the manifest, or write a second CSV with its own
  manifest entry. A second file keeps the C1–C3 record byte-identical and is
  recommended. In either case the extractor gets a CLI flag
  (`--with-butanes`), and its default output stays byte-identical.
- Update the manifest: system list, row counts, the new normalized-CSV SHA-256,
  and the note on the skipped repeats.

## Step 4: regenerate the validation record (frozen: `docs/validation/`, `tests/golden_master/`)

- Rerun the Module 17 generator (as in the P7/P8 PR). It writes
  `docs/validation/module17_vle_validation.csv`, the summary JSON and the
  figures, now with four systems.
- The C1–C3 rows must be byte-identical to today's. Check with a diff restricted
  to those systems before committing.
- Tests that read the summary pick up the new systems. Tests that hard-code
  "40 states" or two systems change:
  - `tests/test_experimental_validation.py`;
  - `tests/test_validation_module17_adapter.py`;
  - the Validation page text "40 methane/ethane and methane/propane VLE states"
    in `src/pvt_phase_simulator_ui/views.py`;
  - `SYSTEM_LABELS` in `src/pvt_phase_simulator_ui/validation_evidence.py`.
- `docs/EXPERIMENTAL_VALIDATION.md` gets the new systems' counts and AARD,
  quoted from the summary JSON.

## Step 5: application component list (not frozen)

The app is built around exactly three components:
- `COMPONENTS` and `COMPONENT_NAMES` in `src/pvt_phase_simulator_ui/adapters.py`;
- three composition fields in `app.py`;
- `case_files.py` requires "exactly Methane, Ethane, and Propane";
- `KIJ_PAIRS` has three pairs.

Choose one of two ways to grow it:

- **(a) Five components.** Make the number of components data-driven.
  Composition fields, case files (schema bump, old three-component files still
  load with zeros), the kij pairs (ten), exports and the model-scope panel all
  follow `COMPONENTS`. This is the larger change, but the cleaner one.
- **(b) Validation only.** Admit the butanes to the engine and the validation
  record, but not yet to the app's inputs. Say so on the Validation page.

Recommendation: **(b) first**, in the same PR as steps 1 to 4. Then (a) as a
separate app PR with its own AppTests and browser test.

## Step 6: follow-on evidence (not frozen)

- Rerun `tools/run_kij_study.py`. The butane systems become production systems
  instead of "provisional butane evidence". Move them from
  `PROVISIONAL_SYSTEMS` to `PRODUCTION_SYSTEMS`, and drop the preview loader.
- `tools/run_dew_conditioning_study.py` and
  `tools/run_hidden_dew_root_check.py`: add `HEAVY` entries for the butanes and
  rerun.
- Leave `docs/investigations/butane_preview*.csv` untouched. They are evidence
  of the pre-P7/P8 solver and the provisional constants. In
  `docs/NEW_COMPONENTS_PROPOSAL.md`, mark the butane decision as taken.

## Order and checks

1. The owner sends the six values and approves the frozen-path edits.
2. One branch (`admit-butanes`): steps 1 to 4 and 5(b). Run the full suite
   locally, because this touches engine and shared app code.
3. CI green, normal merge.
4. A separate branch for step 6, and another for 5(a) if wanted.
