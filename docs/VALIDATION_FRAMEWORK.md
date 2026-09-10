# Validation framework core contract

`pvt_phase_simulator_validation` is the data and serialization boundary for future
OpenPhase validation work. It contains no thermodynamic calculation, error metric,
dataset loader, accuracy threshold, or bundled reference data.

## Data-class separation

Every dataset has one immutable `DatasetIdentity`, containing exactly its ID, version,
and `DataClass`. The identity is retained by every `ValidationCase` and derived by
every `ValidationRecord` from its case. A record constructor has no independent
data-class or identity parameter. Dataset construction rejects any case or source
manifest whose identity disagrees.

Experimental comparisons and numerical cross-checks use distinct summary types:
`ExperimentalAccuracySummary` exposes `accuracy_records`, while
`CrossCheckAgreementSummary` exposes `agreement_records`. Every aggregation entry
point first requires a non-empty homogeneous collection and raises
`MixedDataClassError` if the classes differ. Neither type computes a metric or returns
an accuracy-pass boolean.

## Canonical values and provenance

Numeric values are canonical SI. `ValidationQuantity` declares the canonical unit and
whether relative error is meaningful. Relative error is structurally marked
meaningless for mole fraction and vapor fraction because both approach bounded
endpoints where percentage error misleads.

A `ValidationCase` separates specified conditions from reference values. Vector mole
fractions use the case's ordered `component_ids`, must contain one entry per component,
must lie in `[0, 1]`, and must sum to one within the explicitly declared structural
normalization tolerance `MOLE_FRACTION_SUM_ABSOLUTE_TOLERANCE`. This is an input-shape
invariant, not an accuracy threshold.

`SourceManifest` requires citation text and both raw and normalized SHA-256 fields,
along with archive, extraction, unit-conversion, measurement, uncertainty, compound,
snapshot-policy, and data-class provenance. Digest construction checks only syntax and
normalizes hexadecimal spelling to uppercase. It does **not** verify a file or make an
external-content claim. A later loader holding actual bytes must call `verify_sha256`;
the helper accepts supplied bytes or UTF-8 text, returns `None` on a match, and raises
`HashMismatchError` on a mismatch.

Missing source uncertainty is represented only as `None`. A source-reported zero is a
valid explicit `Uncertainty(value=0.0, ...)`; the framework never imputes it.

## Predictions and statuses

A `ValidationPrediction` has either `VALUE` with one or more values and no failure
reason, or `FAILURE` with no values and a non-empty failure reason. A failure can only
form a record with `SOLVER_FAILURE`; successful values cannot use that status.
Diagnostics are preserved as deeply immutable JSON values, and solver metadata is a
canonical immutable JSON object.

`EXCLUDED` requires a non-empty exclusion reason. Declared-tolerance statuses require
a `DeclaredTolerance`, and that type requires canonical units, justification, source
citation, and scope. The package creates and ships no tolerance instances. The honest
default record status is `REPORTED_NO_TOLERANCE`.

## Serialization and evolution

`SCHEMA_VERSION` identifies the JSON contract. Encoders emit deterministic compact
UTF-8 JSON with a trailing newline; Python's JSON encoder uses the language's
round-trip float representation. Decoders validate all required fields, reject unknown
fields, restore identity from the payload, and check the record identity against its
embedded case. Encoding, decoding, and encoding again is byte-identical.

Adding an enum member can be backward compatible only for writers and readers that
both support it. A reader that encounters an unsupported schema version or a required
enum value it does not know fails explicitly with `SchemaVersionError` or
`UnsupportedValueError`. No value is coerced, defaulted, or dropped, and this package
contains no migration framework.

`ValidationRun` deterministically orders dataset pins and records. Its serialized
`run_metadata` block contains only `run_id` and UTC `timestamp_utc`; stable package,
commit, interpreter, platform, dataset identity/hash, command, and record content live
outside that volatile block so run diffs remain meaningful.

## Deferred to V2-01-C

**C-1 — the uncertainty-status guard is too permissive.** `ValidationRecord`
currently accepts `AGREES_WITHIN_UNCERTAINTY` or `OUTSIDE_UNCERTAINTY` when *any*
reference value in the case carries an uncertainty, rather than requiring the
uncertainty to belong to the quantity actually being compared. A case whose pressure
has a published uncertainty but whose composition does not could therefore carry an
uncertainty-based status on the composition comparison, implying a rigour the source
does not support.

Nothing assigns these statuses yet, so no result is currently affected. The check must
match on `value.quantity` against the quantity under comparison, and that is an
explicit acceptance criterion for V2-01-C, which is the package that first computes
comparisons and assigns statuses from them.

Found by the independent audit of V2-01-A, which reached it by writing its own
adversarial probe rather than reading the shipped tests.
