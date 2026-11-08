# Changelog

Newest first. Each version links to its full notes: the GitHub release for
v1.0–v1.5, and `docs/release_notes/` from v1.6 on. Every version keeps the same
Peng–Robinson model (classical mixing, kij = 0 by default); engine changes are
made only with the owner's approval and are named below.

## Unreleased (on `master`)

- **Engine speed-up, P9 (owner approval A).** Repeated validation of the same
  immutable inputs is skipped. Every result is byte-identical: 801 of 801
  fingerprinted results match, and the full suite passes. The first phase
  envelope of the shipped examples became about 2.1–2.4 times faster on the
  same machine (`docs/investigations/app_performance.md`). P10 records the
  ideas that would change results; none is applied.
- **Sweep fix.** Repeating the same sweep no longer fails on the cache hit.
- **Polish.** The operating point is marked on the envelope plot. Every
  download is named `openphase-…`. The Validation direction labels are
  capitalised. A test checks that every file the docs mention exists.
- **Docs.** A new README, a user guide (`docs/USER_GUIDE.md`), a documentation
  index that separates current from historical documents, and this changelog.

## 1.6.0 (version on `master` since 8 November 2026; not yet tagged)

Full notes: [`docs/release_notes/v1.6.0.md`](docs/release_notes/v1.6.0.md).

- **Engine (P7, P8, owner-approved).** The saturation solver refines the
  boundary when its scan finds no root, and checks past a failed walk step.
  The validation record was regenerated.
- **kij study (P6) and the optional kij input (Option 2).** kij = 0 stays the
  default and the Validation page always shows the kij = 0 record.
- **App.** Plain-language solver codes, a robustness suite with fixes, cached
  engine results, usability fixes and deployment health checks.
- **Teaching.** Lab 4 (what kij does).

## 1.5.0 (31 October 2026)

[Release notes](https://github.com/mahmoudshanaa79-afk/pvt-phase-simulator/releases/tag/v1.5.0).

- **Engine (P2, owner-approved).** Hidden second dew roots are reported as
  ambiguous (`HIDDEN_SATURATION_ROOT`) instead of as a unique answer.
- **Evidence.** The conditioning-aware dew metric (P3), the pure-component
  check against reference equations of state, and a *Further evidence*
  section on the Validation page.
- **Teaching.** Labs 2 and 3.

## 1.4.0 (30 October 2026)

[Release notes](https://github.com/mahmoudshanaa79-afk/pvt-phase-simulator/releases/tag/v1.4.0).

- **Engine (P1, owner-approved).** Pseudo-arclength continuation tolerates a
  change in the number of cubic roots when the selected root moves smoothly,
  so more extended envelopes close.
- **App.** An honest dew-stop marker (P5) and Learn mode.
- **Teaching and evidence.** Lab 1, the Newton comparison (P4), the dew
  investigation, the engine change proposals and the project status page.

## 1.3.0 (18 October 2026)

[Release notes](https://github.com/mahmoudshanaa79-afk/pvt-phase-simulator/releases/tag/v1.3.0).

- The Phase Envelope page overlays the extended pseudo-arclength trace towards
  the critical region.
- Fixed a crash when re-selecting the sweep variable.
- Real-browser tests in CI.
- The validation framework (typed records, provenance, metrics, evidence
  report).
- The OpenPhase name.

## 1.2.0 (8 September 2026)

[Release notes](https://github.com/mahmoudshanaa79-afk/pvt-phase-simulator/releases/tag/v1.2.0).

- Engineering pressure and temperature sweeps.
- A visible model-scope panel.
- Field units (Pa, MPa, bar, psi; K, °C, °F).
- Save and load cases.
- Downloadable engineering reports.
- An envelope branch that ended in `minimum_step_reached` is now reported as
  incomplete.

## 1.1.0 (1 September 2026)

[Release notes](https://github.com/mahmoudshanaa79-afk/pvt-phase-simulator/releases/tag/v1.1.0).

- The public Streamlit app (Overview, Phase Envelope, Critical Point,
  Validation, Diagnostics), with stale-result handling, CSV/JSON export, a
  localhost smoke check and CI.
- The engine is unchanged.

## 1.0.0 (24 August 2026)

[Release notes](https://github.com/mahmoudshanaa79-afk/pvt-phase-simulator/releases/tag/v1.0.0).

- The Peng–Robinson engine:
  - mixture fugacity and stable-root selection;
  - stability analysis, flash, and bubble and dew pressures;
  - phase-envelope tracing with pseudo-arclength continuation;
  - criticality analysis and a mixture critical-point solver;
  - Plotly figures.
- Validation against methane + ethane and methane + propane VLE data at
  kij = 0.
- Verified property provenance for methane, ethane and propane.
