# Work order: v2_01_a_validation_core

## Repository state
- Branch: `v2-validation-framework`
- HEAD: `610057c878a231565f2beff10e5fd13825458e46`
- Working tree: DIRTY — .ai/work_packages/v2_01_a_validation_core.json, .ai/workflow_state.json

## Objective
Create the type system, provenance model and serialization contract that every future
OpenPhase validation dataset will use, so that adding a new publication later means
writing a manifest and a small loader rather than building another bespoke validation
pipeline. This package writes NO science, computes NO error metrics, and adds NO data.
Its value is that it makes certain scientific mistakes structurally difficult.

THE CENTRAL REQUIREMENT
A comparison against EXPERIMENT and a comparison against ANOTHER MODEL must never be
combinable into one statistic. Enforce this with types, not conventions:

- DataClass is EXPERIMENTAL_VALIDATION or NUMERICAL_CROSS_CHECK.
- It is declared once on the dataset and propagated immutably into every case and
  record. There must be NO public API through which a caller supplies or overrides a
  record's DataClass independently of its parent dataset.
- Aggregation entry points accept only a homogeneous collection and raise
  MixedDataClassError otherwise.
- Summary containers are DISTINCT TYPES with distinct vocabulary:
  ExperimentalAccuracySummary (speaks of accuracy) and CrossCheckAgreementSummary
  (speaks of agreement). There must be no type into which both kinds of record can be
  placed.

CLARIFICATION 1 - DATASET AND DATA-CLASS IDENTITY
Introduce a small immutable DatasetIdentity value object carrying exactly dataset_id,
dataset_version and data_class. A ValidationCase and a ValidationRecord each hold that
identity, so they know their own provenance without any caller re-supplying it. Cases
are created through, or reference, their parent dataset identity, and construction
validates that a case's identity agrees with the dataset that contains it;
disagreement is an error, never a silent fix.

Serialized records explicitly retain the immutable dataset identity, including
data_class, and decoding restores it from the payload rather than from any caller
argument. Provide adversarial tests proving that a record decoded from serialized form
cannot be reclassified from EXPERIMENTAL_VALIDATION to NUMERICAL_CROSS_CHECK or the
reverse, through constructors, decoding, copying, dataclasses.replace, or mutation.

CLARIFICATION 2 - HASH VERIFICATION RESPONSIBILITY
This package does not load real datasets, so it must NOT claim that constructing a
ReferenceDataset proves normalized_sha256 matches external content: no content bytes
or path are supplied here. The responsibility of this package is limited to
representing source hashes, validating their syntax and shape (64 hexadecimal
characters for SHA-256, normalized consistently), preserving them faithfully through
serialization, and providing one deterministic helper that verifies SUPPLIED bytes or
content against an expected hash.

Actual verification of normalized dataset content happens later, in V2-01-B or
V2-01-E, where a loader holds the real content. Test the helper with synthetic
in-memory bytes only. Do not read anything under data/ or docs/validation/.

CLARIFICATION 3 - SCHEMA AND ENUM EVOLUTION
Do not claim new quantities or capabilities can be added "without schema change"
unqualified. Define this behaviour explicitly and simply:
- schema_version identifies the serialization contract.
- Adding an enum member may be backward compatible for writers and readers that
  support it.
- A reader encountering an unknown or unsupported required enum value, or an
  unsupported schema_version, MUST fail explicitly with a clear error
  (SchemaVersionError or an unsupported-value error).
- Never silently coerce, default, or drop an unknown quantity or capability.
Do NOT build a migration framework in this package.

DATA MODEL
Canonical SI throughout; original units and conversions recorded as provenance.
- ReferenceDataset: identity (DatasetIdentity), schema_version, SourceManifest,
  CapabilityUnderTest, and its cases.
- ValidationCase: case_id, dataset identity, system_id, ordered component_ids,
  specified_conditions (what is given) and reference_values (what is compared), plus a
  reference back to the source point (row or dataset number).
  Separating specified conditions from reference values is what makes the schema
  source-agnostic: a bubble point specifies temperature and liquid composition and
  references pressure and vapour composition; a pure saturation point specifies
  temperature and references pressure; a flash specifies temperature, pressure and
  feed and references vapour fraction and phase compositions. One schema, no
  per-publication special cases.
- ReferenceValue: quantity, value (scalar or component-indexed vector), optional
  Uncertainty.
- ValidationPrediction: case_id, outcome (VALUE or FAILURE), values (empty on
  failure), failure_reason, diagnostics preserved verbatim, solver metadata.
- ValidationRecord: case + prediction + status + dataset identity. Error metrics are
  attached later by V2-01-C and are NOT computed here.
- ValidationRun: records plus reproducibility metadata.

CapabilityUnderTest: PURE_SATURATION_PRESSURE, BUBBLE_POINT, DEW_POINT, FLASH,
CRITICAL_POINT, COMPRESSIBILITY.

ValidationQuantity: PRESSURE, TEMPERATURE, MOLE_FRACTION, VAPOR_FRACTION,
COMPRESSIBILITY_FACTOR, DENSITY. Each quantity carries its canonical SI unit and a
relative_error_meaningful boolean with a short rationale. MOLE_FRACTION and
VAPOR_FRACTION are False because they approach 0 and 1, so percentage error is
meaningless there. V2-01-C will consume this flag; encoding it here makes the rule
structural rather than a convention.

PROVENANCE
SourceManifest generalizes the existing may_2015 manifest, which is already the right
shape: source_id, citation_text, doi, archive_name, archive_url, access_date,
raw_sha256, normalized_sha256, raw_snapshot_retained, raw_snapshot_policy,
measurement_methods, uncertainty_definition, coverage_factor,
confidence_level_percent, original_units, unit_conversions, compound identity mapping
(name, formula, InChIKey, CAS), extraction_method and data_class. A dataset cannot be
constructed without citation and hash fields present.

Uncertainty: value in SI, kind (STANDARD or EXPANDED), coverage_factor,
confidence_level_percent, source. Absent uncertainty is None - never zero, never
imputed.

STATUS VOCABULARY
AGREES_WITHIN_UNCERTAINTY, OUTSIDE_UNCERTAINTY, AGREES_WITHIN_DECLARED_TOLERANCE,
OUTSIDE_DECLARED_TOLERANCE, REPORTED_NO_TOLERANCE, SOLVER_FAILURE,
REFERENCE_UNAVAILABLE, EXCLUDED.

REPORTED_NO_TOLERANCE is the honest default: a quantitative error is recorded and no
badge is asserted. Define the vocabulary and its consistency rules here; V2-01-C
computes and assigns statuses.

DeclaredTolerance is a record type carrying quantity, value, unit, justification,
source_citation and scope. It cannot be constructed without a justification and a
citation. SHIP ZERO INSTANCES of it in this package. Invent no thresholds anywhere.

REPRODUCIBILITY
ValidationRun pins run_id, UTC timestamp, framework schema_version, OpenPhase package
version, git commit SHA, Python version, platform, dataset ids with versions and
content hashes, and the reproduction command. Records are ordered deterministically by
case_id. Two runs on the same commit and dataset must produce byte-identical output
apart from run_id and timestamp, which stay confined to one clearly delimited metadata
block so diffs remain meaningful.

INVARIANTS TO ENFORCE AND TEST
1. A record's data_class always equals its dataset's; it cannot be set independently.
2. Building a summary from records of more than one data_class raises
   MixedDataClassError.
3. ExperimentalAccuracySummary rejects NUMERICAL_CROSS_CHECK records, and vice versa.
4. A prediction with outcome FAILURE carries no values and forces SOLVER_FAILURE
   status.
5. A record with status EXCLUDED must carry a non-empty exclusion_reason.
6. A DeclaredTolerance without justification and source_citation cannot be constructed.
7. Absent uncertainty is None; zero is representable only if the source states it.
8. Mole-fraction vectors are ordered by the dataset's component_ids and sum to 1
   within a stated tolerance, or the case is rejected at construction.
9. All dataclasses are frozen; datasets, cases and records are immutable.
10. encode then decode then encode is byte-identical.
11. Serialized floats use round-trip repr, matching the golden-master convention.
12. Source hashes are syntactically validated and preserved through serialization; the
    content-verification helper accepts matching and rejects non-matching supplied
    bytes. Construction does NOT claim to have verified external content.
13. Unknown or unsupported enum values and schema versions are rejected explicitly.
14. No API returns a boolean meaning "accuracy passed".

BUILD-TIME TESTING POLICY
Run only focused tests for what you changed, plus Ruff and mypy if useful. Do NOT run
the whole pytest suite for reassurance; the orchestrator runs the authoritative
full-suite verification after you finish, and duplicating it wastes a great deal of
wall-clock time. All fixtures in this package are synthetic and in-memory: no test may
read data/ or docs/validation/, which keeps this package independent of V2-01-B and E.

## Allowed files
  - `src/pvt_phase_simulator_validation/**`
  - `tests/test_validation_*.py`
  - `docs/VALIDATION_FRAMEWORK.md`

## Files you must NOT modify
  - `src/pvt_phase_simulator`
  - `data`
  - `docs/validation`
  - `tests/golden_master`
  - `src/pvt_phase_simulator_ui`
  - `tools/orchestration`

## Protected artifacts — never regenerate
  - `tests/golden_master/baseline.csv` — SHA256 530C667AA70EF1EA182F4EDB98624A0A9B9908F149354276CDAC44A87EA7D2BE
  - `data/component_properties.csv` — SHA256 C6F6BA9AE9C2F4C7F257BBC09A75DF0D7065255868AA46BF3E8C81AC5A8B9B3A
  - `docs/validation/module17_vle_validation.csv` — SHA256 B14728D51AAC06AF38FC4F4E5F408942B253FEBE32D3E12EC26E9623CFA42482
  - `docs/validation/module17_vle_validation_summary.json` — SHA256 5B120B77BF05567FCC6A0EE0D0054C6D1DEBA35FE26A7C837352C92017D24870

## Scientific invariants that must continue to hold
  - The scientific engine is frozen: no file under src/pvt_phase_simulator/, data/, docs/validation/ or tests/golden_master/ may change.
  - This package performs no thermodynamic calculation and imports nothing from pvt_phase_simulator.eos.
  - EXPERIMENTAL_VALIDATION and NUMERICAL_CROSS_CHECK records can never be combined into one statistic or summary.
  - A record's DataClass is inseparable from its dataset identity and survives serialization and decoding unchanged.
  - No accuracy threshold, default tolerance, or boolean meaning 'accuracy passed' may exist anywhere in this package.
  - Solver failures are preserved as failures and can never become ordinary successful records.
  - Provenance cannot be constructed incomplete: a dataset requires citation and hash fields.
  - Hash claims must not exceed what is actually verified: construction validates hash syntax only; content verification requires supplied bytes.
  - Unknown or unsupported enum values and schema versions are rejected explicitly and never silently coerced.

## Required tests
  - `.venv/Scripts/python.exe -m pytest -q`

## Required quality gates
  - `.venv/Scripts/python.exe -m ruff check .`
  - `.venv/Scripts/python.exe -m ruff format --check .`
  - `.venv/Scripts/python.exe -m mypy src app`
  - `.venv/Scripts/python.exe -m compileall -q src app`

## Rules
- Do NOT weaken a test to make it pass. Do not loosen a tolerance, edit an
  expected value to match output, delete a test, swallow an exception, or
  regenerate a baseline. Any of those is a blocking failure.
- Do NOT commit, stage, reset, or clean. The orchestrator owns git.
- Do NOT write your own audit — an independent auditor reviews your work.
- Keep the change within the objective; no unrelated cleanup.

## Required final output

End your reply with exactly one machine-readable block:

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "<what you ran and what it reported>",
  "files_changed": ["<path>", "..."],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>

`status` must be COMPLETE, BLOCKED or FAILED. The orchestrator re-runs every
check locally, so an inaccurate claim here will simply be caught.
