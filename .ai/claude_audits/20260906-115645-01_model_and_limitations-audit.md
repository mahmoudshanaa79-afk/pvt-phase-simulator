## Independent Audit: 01_model_and_limitations

**Scope verified:** HEAD `46b1d8e7`, diff touches `docs/STREAMLIT_APPLICATION.md`, `src/pvt_phase_simulator_ui/{adapters.py,views.py,model_scope.py}`, `tests/test_app_streamlit.py`, plus orchestrator bookkeeping in `.ai/`.

### Protected-artifact check
`git diff HEAD` against `src/pvt_phase_simulator/`, `data/component_properties.csv`, `docs/validation/module17_vle_validation.csv`, `docs/validation/module17_vle_validation_summary.json`, and `tests/golden_master/baseline.csv` returns zero lines — nothing in the frozen scientific engine or protected artifacts was touched. Confirmed directly, not from the orchestrator's claim.

### Independent re-derivation of every number in the panel
I did not trust the builder's report or the code's own comments; I recomputed each quantity from the raw files with `awk`, and separately by actually executing `load_model_scope()` in the project's venv:

- **Validation state count**: `docs/validation/module17_vle_validation.csv` has 40 data rows (17 `ch4_c2` + 23 `ch4_c3`) → matches the claimed 40.
- **Systems**: `SYSTEM_COMPONENTS` maps `ch4_c2`→(methane, ethane), `ch4_c3`→(methane, propane); `resolve_component(...).canonical_name` join produces exactly "Methane + Ethane" / "Methane + Propane".
- **Temperature range**: min/max of column 3 = 203.22 / 283.38 K → matches exactly.
- **Pressure range**: min/max of column 4 (Pa) = 891000 / 8320000 → 0.891 / 8.32 MPa → matches exactly.
- **Property DOI**: all 9 rows (3 components × 3 properties) in `data/component_properties.csv` are `source_status=verified` with DOI `10.1021/acs.jced.5c00110` → matches, and correctly collapses to one distinct `RecordedSource` since all nine rows cite the same paper.
- **Validation-source DOI**: `data/experimental/may_2015_source_manifest.json` DOI is `10.1021/acs.jced.5b00610` → matches.
- **kij policy**: `BinaryInteractionPolicy.DEFAULT_ZERO = "default_zero"` in `mixing_rules.py`, and grepping the UI package shows no caller ever passes `binary_interactions`/`binary_interaction_policy` to the engine — every flash/sweep call in the app silently takes the engine's own default, which is `DEFAULT_ZERO`. The panel's "no fitted interaction parameters are used" claim is actually true of the app's behavior, not just asserted.
- **`CriticalPointStatus.CONVERGED`**: matches the literal enum member name in `eos/critical_point.py`.
- Actually ran `load_model_scope(Path('.'))` end-to-end in the repo's `.venv` — it succeeds and produces exactly the values above with no exceptions, confirming this is live code, not aspirational.

### Negative-claim check ("known limitations" list)
Grepped the whole `src/` tree for CCE/CVD, separator, pseudocomponent, C7+, reservoir-depletion, and kij-fitting/tuning code — the only hits are the panel's own prose in `views.py` and unrelated diagnostic-code string literals in `experimental_validation.py`/`flash.py`. None of these capabilities actually exist in the engine, so the "not supported" claims are true, not just asserted.

### No fabrication path
`model_scope.py` only reads CSV/JSON files and does dictionary/dataclass lookups — it never calls into `eos/`, never runs a flash, and never interpolates. `_doi_link` returns "DOI unavailable" rather than fabricating a URL when `doi is None`. `_verified_component_names` only includes a component if **all** of its critical-property records are `PropertySourceStatus.VERIFIED`; an unverified/missing-provenance component would silently and correctly drop out of the list rather than being invented.

### Test quality
- `test_model_scope_reads_recorded_component_and_validation_provenance` hardcodes literal expected values (40, system names, temp/pressure ranges, DOIs, artifact path) independently of the code under test — a genuine regression test, and I've verified every one of those literals against the raw data myself above.
- `test_overview_exposes_repository_backed_model_and_limitations_panel` boots the real `streamlit_app.py` via `AppTest` and checks the rendered markdown/warning against a freshly loaded `ModelScope` — this is an integration/wiring test (it can't catch a bug shared between production and test in `load_model_scope` itself, but that's normal for this kind of coupling and the sibling test above covers correctness of the values).
- I ran both new tests plus the export/streamlit/composition test subset (79 tests) against the actual venv — all pass, no regressions from the `adapters.py` change.

### Minor observation (non-blocking)
`adapters.py`'s `COMPONENT_NAMES` changed from a hardcoded literal tuple to `tuple(component.name for component in COMPONENTS)`. This is outside the literal "documentation and presentation only" framing since it touches a shared adapter constant used by `exports.py` and other views, not just the new panel. However: it removes a restated duplicate of already-verified data (exactly the spirit the work package asks for elsewhere), values are unchanged in practice (`METHANE.name == "Methane"` etc., confirmed by test pass), and it doesn't approximate or touch any thermodynamic relation. I flag it only as a scope note, not a defect.

I found no scientific error, no weakened/tautological test, no silent scope creep into protected paths, no fabricated-value path, and no unsupported documentation claim.

<ORCHESTRATOR_RESULT>
{
  "verdict": "APPROVED",
  "findings": [],
  "safe_defer": [
    {"id": "D-1", "severity": "D", "blocks": false, "summary": "adapters.py's COMPONENT_NAMES was changed from a hardcoded literal to a value derived from COMPONENTS; harmless and value-preserving (confirmed by test run) but technically broader than the 'documentation/presentation only, new panel' framing of the work package."}
  ]
}
</ORCHESTRATOR_RESULT>