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
- `original_unit` and `conversion` retain explicit source-to-canonical
  conversion evidence. Module 16.1 accepts only the audited critical-pressure
  path `kPa` to canonical `Pa`, recorded as `1 kPa = 1000 Pa`. This is
  provenance validation, not a
  general runtime unit-conversion engine.

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

CSV values use canonical units. Primary Table 5 reports critical pressure in
kPa, so Module 16.1 records and strictly validates its explicit conversion
evidence. No conversion function is activated in `unit_conversions.py`;
unsupported conversion claims remain rejected.

## Provenance and source status

`ComponentPropertyProvenance` is frozen and belongs to exactly one named
property. It exposes status, source reference, property-source identity,
citation text, optional URL/DOI/version, notes, original unit, canonical unit,
and conversion information. `ComponentPropertyProvenanceSet` attaches the
three correctly named records to a calculation `Component`.

`provisional` means exact source confirmation is absent. It remains a supported
schema state for alternate databases, but no production row remains
provisional after Module 16.1.

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

## Verified migration and frozen-baseline impact

| Component | Tc (K) | Pc (Pa) | omega | Status |
|---|---:|---:|---:|---|
| methane | 190.564 | 4599200.0 | 0.011420 | verified |
| ethane | 305.322 | 4872200.0 | 0.099500 | verified |
| propane | 369.890 | 4251200.0 | 0.152100 | verified |

The earlier provisional values remain only in the private
`PRE_MODULE_16_1_PROVISIONAL_VALUES` test fixture and the migration report.
`METHANE`, `ETHANE`, and `PROPANE` are compatibility constants obtained from
the default database, not second Python literals. Tests pin exact sourced
values, provenance, conversions, pure PR, mixture fugacity, flash,
historical/Newton bubble and dew, envelope, and component-order behavior. The
pre-migration golden baseline is deliberately not regenerated; see the
[migration report](PROPERTY_SOURCE_MIGRATION.md).

## Binary interactions, limitations, and Module 17

No `kij` appears in this CSV. `DEFAULT_ZERO` remains a modelling assumption,
not experimental evidence; future provenanced interaction data must be
separate.

The production `Tc`, `Pc`, and acentric-factor rows now have verified
traceability to Yang and Richter (2025). This does not establish absolute
experimental truth. A molar-mass source would still be required if molar mass
is introduced. Module 17 may add experimental validation only after independent
review of Module 16.1 and an explicit golden-rebaseline decision; this module
contains no experiments, fitting, or calibration.
