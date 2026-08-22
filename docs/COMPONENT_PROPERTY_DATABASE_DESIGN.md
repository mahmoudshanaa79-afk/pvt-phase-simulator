# Component-property database design

## Purpose and scope

Module 16 replaces the three Python property literals with a strict,
provenanced data-loading boundary. It does not add experimental data, validate
EOS predictions against experiments, calibrate `kij`, or start Module 17.

Only properties already consumed by Peng–Robinson are in scope: critical
temperature (`Tc`), critical pressure (`Pc`), and acentric factor (`omega`).
Molar mass appeared only in the old header scaffold; no value was present and
no calculation consumes it, so Module 16 does not invent or add it. Other
possible properties are likewise excluded.

## Canonical data and packaging

The review-facing file is `data/component_properties.csv`. A byte-identical
runtime copy is stored at
`src/pvt_phase_simulator/data/component_properties.csv` so the default database
is included by the existing `uv_build` backend and remains available in an
installed wheel. A focused equality test makes divergence a hard failure. This
two-file packaging compatibility layer is intentionally narrow; a later build
configuration that maps the root data file into the wheel should consolidate it
without changing the schema or API.

The loader resolves the runtime file relative to `component_database.py`, never
the process working directory. Callers may supply an alternate path. Files are
opened as strict UTF-8 CSV with newline-aware parsing.

## Schema

The exact header is:

```text
component_id,canonical_name,aliases,property,value,unit,source_status,source_reference_name,property_source_identity,citation_text,url,doi,edition_or_version,notes,original_unit,conversion
```

Each row represents one exact property value, not a whole component. This lets
`Tc` and `Pc` come from source A and `omega` from source B without redesign.
Column order and spelling are exact; extra or missing columns are rejected.
Empty lines are ignored, cell-edge whitespace is trimmed, and missing
scientific fields are never defaulted.

- `component_id` is a stable lowercase machine ID.
- `canonical_name` is the display name.
- `aliases` is a `|`-separated deliberate alias list.
- `property`, `value`, and `unit` define one canonical numerical value.
- `source_status` is `provisional` or `verified`.
- the remaining fields identify and describe that property's source.
- `original_unit` and `conversion` reserve explicit conversion evidence. They
  must be blank in Module 16 because no conversion is needed or implemented.

Database order is first component appearance, with contiguous property rows.
The current order is methane, ethane, propane. Loading preserves it. Database
order never changes a caller's mixture: `FluidMixture` retains caller tuple
order.

## Identifiers, aliases, and lookup

| ID | Canonical name | Aliases |
|---|---|---|
| `methane` | Methane | `CH4`, `C1` |
| `ethane` | Ethane | `C2H6`, `C2` |
| `propane` | Propane | `C3H8`, `C3` |

Lookup strips surrounding whitespace and is case-insensitive, but not fuzzy.
IDs, names, and aliases must map to exactly one component. Ambiguous aliases
and unsupported requests raise explicit errors; there is no `None`, methane
substitution, or approximate match.

## Properties and canonical units

| Property | CSV name | Canonical unit | Basic validation |
|---|---|---|---|
| Critical temperature | `critical_temperature` | `K` | finite and greater than zero |
| Critical pressure | `critical_pressure` | `Pa` | finite and greater than zero |
| Acentric factor | `acentric_factor` | `1` | finite |

The retained values already use canonical units. Module 16 therefore activates
no conversion function in `unit_conversions.py`. Unsupported units and claimed
conversion metadata are rejected; no undocumented conversion is implied.

## Provenance and source status

`ComponentPropertyProvenance` is frozen and belongs to exactly one named
property. It exposes status, source reference, property-source identity,
citation text, optional URL/DOI/version, notes, original unit, canonical unit,
and conversion information. `ComponentPropertyProvenanceSet` attaches the
three correctly named records to a calculation `Component`.

`provisional` means exact authoritative confirmation is absent. All current
rows remain provisional and point only to the known pre-Module-16 repository
location. Citation, DOI, URL, edition, source-record identity, original unit,
and conversion fields remain blank. No familiar database or publication name
is inferred.

`verified` is the structured provenance-metadata state. It requires a
meaningful, non-placeholder source name plus at least one non-placeholder
citation, stable property-source identity, structurally valid absolute HTTP(S)
URL, or syntactically valid DOI. Placeholder comparison trims and case-folds
complete field values; it does not reject substrings inside legitimate names.
Malformed supplied URLs or DOIs reject a verified record. DOI fields use the
canonical `10.<registrant>/<suffix>` identifier only, not `doi:` or resolver-URL
wrappers. This software gate establishes traceability; it does not authenticate
the source or its scientific quality. Human scientific review remains required
before changing a row to verified.

## Loader, immutable models, and errors

`load_component_database(path=None)` strictly parses and freezes a database.
`get_component`, `resolve_component`, and `list_components` form the small
default API. Records, tuple collections, nested Pydantic models, and the lookup
mapping are immutable. A database record converts explicitly into the existing
`Component`, so the EOS has no second incompatible calculation model.

The loader rejects malformed UTF-8/CSV, a non-exact header, wrong row width,
invalid IDs/properties/statuses/numbers, non-finite values, nonpositive `Tc` or
`Pc`, unsupported units/conversions, missing or duplicate properties,
inconsistent metadata, duplicate component blocks, and ambiguous aliases. It
does not silently skip or repair rows.

## Legacy migration and numerical invariance

| Component | Tc (K) | Pc (Pa) | omega | Status |
|---|---:|---:|---:|---|
| methane | 190.56 | 4599200.0 | 0.011 | provisional |
| ethane | 305.32 | 4872000.0 | 0.099 | provisional |
| propane | 369.83 | 4248000.0 | 0.152 | provisional |

These exact pre-Module-16 decimal strings are retained. `METHANE`, `ETHANE`,
and `PROPANE` are compatibility constants obtained from the default database,
not second Python literals. Tests pin exact float equality and `repr`, pure PR,
mixture fugacity, flash, historical/Newton bubble and dew, envelope, and
component-order behavior. The golden baseline is not regenerated.

## Binary interactions, limitations, and Module 17

No `kij` appears in this CSV. `DEFAULT_ZERO` remains a modelling assumption,
not experimental evidence; future provenanced interaction data must be
separate.

Software infrastructure can be verified while property sources remain
unconfirmed. Authoritative source data are still required for `Tc`, `Pc`, and
acentric factor for methane, ethane, and propane. A molar-mass source would also
be required if molar mass is later introduced. Module 17 may add experimental
validation only after respecting this gate; Module 16 contains no experiments,
metrics, plots, fitting, or calibration.
