# Carbon dioxide and nitrogen: admission plan

**Status: plan only (owner approval D, 8 November 2026: documentation only).**
Nothing in `data/`, the engine or the app is changed. Every literature source
below is marked **not verified**: from the web session, the NIST ThermoML
pages (trc.nist.gov), doi.org and the publishers' sites did not resolve, so no
record could be opened. No number from an unverified source is used here.

## Why these two

CO2 and N2 are the commonest non-hydrocarbons in natural gas. Without them the
app cannot describe most real gases. Each, however, brings a problem that the
methane, ethane and propane scope does not have:

- **Non-zero kij matters.** PR with kij = 0 is widely reported to be poor for
  CO2 + hydrocarbon pairs, and noticeably off for N2 + hydrocarbon pairs. This
  is not verified here, and no literature kij value is used. The app today
  validates only at kij = 0. Admitting these components therefore probably
  needs the kij policy decided first (see step 5).
- **Solid CO2.** At low temperature CO2 can freeze out. OpenPhase has no
  solid phase, so states where CO2 would freeze must be refused or flagged,
  not silently computed as fluid.
- **N2 is supercritical** at almost every temperature of interest (its
  provisional critical temperature is 126.192 K, below). Envelopes of N2-rich mixtures will be narrow and
  can show retrograde behaviour that tests the continuation code.

## Property sources

| Property | Candidate source | Status |
|---|---|---|
| T_c, p_c, ω | Yang & Richter (2025), doi:10.1021/acs.jced.5c00110, Table 5, the source of the current verified rows | **not verified** that Table 5 includes CO2 and N2; the owner must check |
| T_c, p_c, ω (provisional, for previews only) | CoolProp 6.6.0 reference equations of state, run in this session (see below) | reproducible; **provisional**, never to be marked verified |
| Reference saturation data for a pure-component check | CoolProp 6.6.0 (Span–Wagner CO2, Span et al. N2), like `docs/investigations/pure_saturation_reference.csv` | reproducible; same standing as the accepted C1–C3 file |

Provisional constants, from this command run on 8 November 2026:

```bash
uv run --no-project --python 3.12 --with "CoolProp==6.6.0" python -I -c "import CoolProp.CoolProp as CP; print([[CP.PropsSI(k, f) for k in ('Tcrit', 'pcrit', 'acentric', 'Ttriple')] for f in ('CarbonDioxide', 'Nitrogen')])"
```

| Fluid (CoolProp EOS) | T_c (K) | p_c (Pa) | ω | Triple point (K) |
|---|---|---|---|---|
| CarbonDioxide (Span-JPCRD-1996) | 304.1282 | 7377300.0 | 0.22394 | 216.592 |
| Nitrogen (Span-JPCRD-2000) | 126.192 | 3395800.0 | 0.0372 | 63.151 |

Like the butane constants, these are for previews only. The component
database accepts only verified rows
(`tests/test_component_database.py::test_every_property_exposes_exact_verified_source_provenance`),
which is the right gate.

## Candidate measured VLE data (all not verified)

The first dataset to look for is one comparable to May et al. (2015): one
laboratory, reference quality, with stated expanded uncertainties and a NIST
ThermoML record, so it can be extracted like
`tools/extract_may_2015_thermoml.py` does.

| Pair | Candidate (from search-result titles only) | Status |
|---|---|---|
| CH4 + CO2 | Petropoulou et al., Fluid Phase Equilibria (2018), doi:10.1016/j.fluid.2018.01.011; ThermoML record listed at trc.nist.gov | **not verified**: record not opened; temperatures, point count and uncertainties unknown |
| CH4 + N2 | Han et al., J. Chem. Eng. Data 57 (2012), doi:10.1021/je201299u, "VLE for N2 + CH4 in the temperature range of (110 to 125) K" | **not verified**: record not opened; uncertainties unknown |
| CH4 + N2, CH4 + CO2 | The same University of Western Australia group as May et al. (2015) may have reference-quality data on these pairs | **not verified**: no record found or opened |
| C2H6 + CO2, C3H8 + CO2, N2 + C2H6, N2 + C3H8 | none identified yet | to search once ThermoML is reachable |

**How to verify each candidate.**

1. Open its ThermoML record and download the XML.
2. Record the SHA-256, the compounds, the property types, the T and p ranges,
   the point count and the stated uncertainties (expanded, with coverage).
3. Check that it gives both phase compositions, which bubble and dew
   comparisons need.
4. Reject any dataset without stated uncertainties.

## Steps (each needs the owner's approval when it reaches a frozen path)

1. **Verify a source for T_c, p_c and ω** (Table 5 or another primary
   reference), exactly as for the butanes.
2. **Verify at least one dataset per pair with methane** from the table
   above. Add a pure-component saturation check for CO2 and N2 against the
   CoolProp reference EOS, like V2-01-E.
3. **Preview without admitting**, like `tools/run_butane_preview.py`. Run
   provisional constants and kij = 0 over the verified data. Report the bubble
   and dew coverage and AARD, with the engine's own reasons for every failure.
4. **Freezing guard.** Before any calculation with CO2, refuse states below
   the CO2 triple point. Flag states where solid CO2 may form, with the reason
   stated. This is an app and engine design decision for the owner.
5. **kij policy.** Run `tools/run_kij_study.py` on the new pairs and show the
   effect of a fitted kij against kij = 0. A fitted kij is calibration, not
   validation, so hold some states out. The owner then decides whether the
   app keeps kij = 0 as default for these pairs, or ships fitted values with
   their provenance.
6. **Admission**, following `docs/BUTANES_ADMISSION_PLAN.md`:
   - database rows;
   - a second (or third) data file with its own manifest;
   - optional systems in the validation loader;
   - the regenerated record with the C1–C3 rows byte-identical and the golden
     master unchanged;
   - the consumer updates listed in the butanes draft PR's dry-run note
     (validation adapter, report, plots, kij study, expected component
     lists).
7. **App.** The composition inputs are hard-coded to three components
   (`src/pvt_phase_simulator_ui/app.py`, `state.py`, `case_files.py`). Adding
   two more needs a component-list redesign, a saved-case schema version bump
   and new tests. This is the largest app change in the plan.

## What the owner decides

- Whether CO2 and N2 come before or after the butanes.
- The source of record for their critical constants.
- The kij policy for CO2 and N2 pairs (step 5).
- How freezing is handled (step 4).
