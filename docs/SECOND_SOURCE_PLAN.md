# Second experimental source: plan and ready-to-run tools

**Status:** tools built and tested; **no dataset downloaded**. The web
sessions' network proxy blocks trc.nist.gov (NIST ThermoML), doi.org and
publisher sites. Every candidate below is **NOT VERIFIED: not downloaded**.
Citations marked "from memory" may contain errors; check each one in the
ThermoML archive before using it. No number on this page is a measurement.

## Why

Every validation state comes from one laboratory: May et al. (2015). The CH4+C3
bubble accuracy (1.01 % AARD at 23 of 23 states, kij = 0) has not been tested
against an independent source. The optional Péneloux shift has no
mixture-density validation (`docs/VOLUME_TRANSLATION.md`).

## The tools (offline, ready now)

- `tools/compare_thermoml_vle.py` reads a ThermoML JSON record and pairs
  pressure and vapour-composition observations by (T, x). It runs the frozen
  engine's bubble pressure (and dew pressure where y was measured), at kij = 0
  unless `--kij` is given. It writes a per-state CSV and a summary: AARD,
  maximum error, bias, convergence counts, and the engine's reason for every
  failed or ambiguous state.
  `tests/test_compare_thermoml_vle.py` shows that it reproduces the
  validation record (statuses, pressures, failure reasons, diagnostic codes)
  on a fixture built from committed May (2015) rows.
- `tools/compare_liquid_density.py` reads measured liquid densities and
  compares PR with and without the shipped Péneloux shifts, using the
  unchanged public functions of
  `src/pvt_phase_simulator/eos/volume_translation.py`. It reads molar density
  and molar volume directly. Mass density needs `--molar-mass NAME=g/mol` for
  each component, with a cited source, because the engine stores no molar
  masses. `tests/test_compare_liquid_density.py` covers it on fixtures.

## What to do on the desktop, per candidate

1. Open `https://trc.nist.gov/ThermoML/<DOI>.html`. Confirm the compounds, the
   properties (P–x–y or liquid density), the temperature and pressure range,
   the number of points, and the stated uncertainties. Write them into the
   candidate's row below.
2. Download `https://trc.nist.gov/ThermoML/<DOI>.json` into a new, empty
   folder and record its SHA-256.
3. Run one of these, depending on the data:

```bash
uv run python tools/compare_thermoml_vle.py --input <file>.json --output-dir docs/investigations/second_source
```

```bash
uv run python tools/compare_liquid_density.py --input <file>.json --output-dir docs/investigations/vt_mixture_density
```

4. Commit the outputs with an investigation note and a test that recomputes
   every quoted number from the committed CSV, as for the kij study. Nothing
   goes into `data/`: admitting a source needs the owner's approval
   (`docs/SECOND_SOURCE_FRAMEWORK_DESIGN.md`).
5. If the tool lists a dataset as skipped, read the reason. Extend the tool
   only for a layout that you have actually seen in a parsed file.

## Candidate CH4+C3 VLE datasets

| Candidate | What to check | Status |
|---|---|---|
| Wichterle & Kobayashi, J. Chem. Eng. Data (1972), methane + propane at low temperatures and high pressures (citation from memory) | whether a ThermoML record exists; P–x–y or P–x only; stated uncertainties | NOT VERIFIED: not downloaded |
| Reamer, Sage & Lacey, Ind. Eng. Chem. (1950), volumetric and phase behaviour of methane + propane (citation from memory) | older data, often without stated uncertainties; the tool needs them for the uncertainty columns but runs without | NOT VERIFIED: not downloaded |
| Any recent J. Chem. Eng. Data or Fluid Phase Equilibria methane + propane VLE set with a ThermoML record, found by searching the archive for both compounds | a full P–x–y set with expanded uncertainties, preferably overlapping the May (2015) CH4+C3 temperatures in the committed record (203.4–283.38 K) so the results are comparable | NOT VERIFIED: not downloaded |

## Candidate C1–C3 mixture liquid-density datasets

| Candidate | What to check | Status |
|---|---|---|
| NIST LNG-mixture orthobaric liquid density studies (Haynes, Hiza, McCarty and co-workers, J. Chem. Thermodyn., 1970s–1980s; citations from memory) | binary CH4+C2, CH4+C3 or C2+C3 sets; whether densities are molar or mass; temperatures (mostly below 140 K, outside most app states); uncertainties | NOT VERIFIED: not downloaded |
| Any ThermoML record with a liquid "Molar density" or "Mass density" of these binaries at T, P and composition | that the record gives the composition as a liquid mole fraction and the pressure as a variable | NOT VERIFIED: not downloaded |

## What would count as success

- **VLE:** a second laboratory's CH4+C3 bubble pressures at kij = 0 with an
  AARD of the same order as May (2015). If the result differs, report it as
  found. Ambiguous dew results are reported with the engine's reason, as in
  the record.
- **Densities:** a table of PR and shifted errors for mixtures, stating where
  the shift makes things worse, near the critical point in particular. If the
  result argues for a different shift or mixing rule, it becomes an engine
  proposal; it is not implemented directly.
