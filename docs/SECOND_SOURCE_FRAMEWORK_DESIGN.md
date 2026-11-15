# Design proposal: a second experimental source in the validation framework

**Status: design only (web session, 15 November 2026). Nothing is
implemented.** It needs the owner's decision. The draft butanes PR 47 notes it
as a separate design change. `src/pvt_phase_simulator_validation/module17_adapter.py`
is unchanged; PR 47 edits it.

## Today

- **The record.** `tools/run_module17_validation.py` writes one record,
  `docs/validation/module17_vle_validation.csv`, and its summary. They hold
  every validation state, so far from one source: May et al. (2015).
- **The framework.** The validation framework (`pvt_phase_simulator_validation`)
  turns that record into typed objects through
  `load_module17_validation_evidence()`. That function:
  - reads exactly one data file and one source manifest
    (`data/experimental/may_2015_source_manifest.json`);
  - checks the CSV hash against the manifest;
  - requires the record's state IDs to equal the data file's;
  - emits **exactly two** `ReferenceDataset` objects (bubble and dew), each
    carrying that single `SourceManifest`.
- **The report.** The evidence report and the metrics are built from those two
  datasets.
- **PR 47.** It lets the adapter accept extra record rows only when they all
  belong to the hash-verified butane data file. The framework's datasets still
  cover the C1–C3 source only; butane results appear in the record and its
  summary, not in the framework's objects.

## Goal

Admit a second measured source, for example a second methane + propane set
from `docs/SECOND_SOURCE_PLAN.md`, so that the framework, the report and the
Validation page show it with **its own provenance**. Nothing about the May
(2015) results may change: same states, same numbers, same hashes.

## Proposed design

1. **A source registry file**, for example `data/experimental/<sources>.json`
   (a frozen path; owner approval needed). It holds one entry per admitted source: source ID,
   data CSV path, manifest path and the systems it covers. Today it would have
   one entry, May (2015) C1–C3. PR 47 would add the butanes file.
2. **One loader per source, one dataset pair per source.** The adapter
   becomes:
   - `load_validation_evidence(root) -> ValidationAdaptation`;
   - `ValidationAdaptation` holds `datasets: tuple[ReferenceDataset, ...]`,
     two per source (bubble, dew), each with that source's manifest;
   - it keeps `records` and `interpretation`.

   `load_module17_validation_evidence()` stays as a thin wrapper that returns
   the May (2015) pair only, so existing callers and tests are unchanged.
3. **Record rows say where they came from.** The record CSV gains a
   `source_id` column, filled from the data file of each state. A state ID must
   be unique across sources; the existing `may2015_` prefix already is.
4. **Checks per source.** For every source:
   - the CSV hash matches its manifest;
   - the record rows with that `source_id` match its data file exactly
     (temperature, pressure, compositions, uncertainties), using the existing
     `_reference_match`;
   - its point count equals its manifest's counts.

   Rows of an unknown source are an error, never silently ignored.
5. **Metrics and report.** Aggregates are grouped by (source, system,
   capability). The report gets one section per source. The headline numbers
   (README, `docs/STATE_OF_OPENPHASE.md`) keep quoting May (2015) separately
   until the owner decides how sources are combined, if ever. Pooling sources
   with different uncertainties is a scientific decision, not a software one.
6. **kij stays separate.** A second source is first compared at kij = 0. A
   kij fitted on one source and tested on the other is the first real
   out-of-sample check of the kij study.

## Migration and proof of no change

1. **No-op step.** Add the registry with the single May (2015) entry and the
   generalized loader with the wrapper.
   - The May (2015) dataset objects and the report must be byte-identical:
     compare the canonical JSON of the adaptation before and after, as
     `tools/engine_fingerprint.py` does for the engine.
   - The record CSV changes only by the new `source_id` column, so its hash
     pins move. That is an owner-approved regeneration with an explanation
     for every change, never a silent rebaseline.
2. **Second source.** Add its data file, its manifest, its registry entry and
   its record rows (`tools/run_module17_validation.py` with the new source).
   Prove the May (2015) rows and the golden master are unchanged, as PR 47's
   final step does for the butanes.

## Interaction with PR 47

PR 47 is waiting for the owner's Table 5 values and should merge first, with
its narrow rule ("extra rows must be the butane file"). This design then
replaces that rule with the registry, and the butanes become the registry's
second entry. Doing this design before PR 47 merges would create conflicts in
the files PR 47 changes, so it should wait.

## Decisions for the owner

- Approve the registry file and the `source_id` column (frozen paths).
- Decide whether headline numbers ever pool sources (recommended: no; report
  each source separately).
