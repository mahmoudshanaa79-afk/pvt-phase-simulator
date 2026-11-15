# The state of OpenPhase (November 2026)

A short summary for a faculty reader. Every number on this page is recomputed
from the engine or from a committed record by `tests/test_state_of_openphase.py`.

## What it is

OpenPhase is an educational phase-behaviour simulator for light hydrocarbons,
built on the Peng–Robinson equation of state with classical mixing rules. It
covers methane, ethane and propane, whose critical constants come from Yang &
Richter (2025). It calculates:
- phase stability (tangent-plane distance);
- two-phase flashes;
- bubble and dew pressures;
- phase envelopes;
- certified mixture critical points.

A public Streamlit app exposes all of it, with Learn mode and five teaching
labs whose numbers are checked against the engine. Results always carry the
solver's status and reason. An ambiguous or failed calculation is reported as
such, never replaced by a guess.

## Evidence

**Measured VLE, no fitting.** Comparison with May et al. (2015) at kij = 0:

| System | Bubble pressure | Unique dew pressure found |
|---|---|---|
| methane + ethane | 1.02 % AARD at 17 of 17 states | 8 of 17 states, 2.07 % AARD |
| methane + propane | 1.01 % AARD at 23 of 23 states | 1 of 23 states |

**Dew points are often ill-posed in PR, not wrong.** At most methane +
propane states, PR has two dew pressures for the measured vapour, so the
solver reports *inconclusive*. Comparing PR's vapour composition at the
measured pressure instead, it lies within the stated measurement uncertainty
at 22 of 23 states.

**Pure components.** Against reference equations of state from saturation
down to T_r = 0.5:
- vapour pressures agree to 0.73 % (methane), 0.59 % (ethane) and 0.72 %
  (propane) AARD;
- saturated-liquid densities are off by up to 12.77 %, the known PR bias.

**Critical point.** The certified critical point of 50/50 methane/propane is
321.58 K and 8.534 MPa. Both Gibbs criticality conditions are solved and
re-checked.

**Software.** CI runs lint, type checks, the full test suite in parallel, a
real-browser test and a check with only the deployed dependencies on every
change. A fingerprint of 801 engine results guards changes that must not
alter results.

## Limitations

- **One experimental source.** Every measured state comes from May et al.
  (2015), one laboratory. A fitted kij of +0.0021 for methane + propane is
  calibration on that source, not validation.
- **Dew ambiguity.** Most measured methane + propane dew states have no
  unique PR answer, and the app shows none.
- **Volume translation is not validated for mixtures.** The optional Péneloux
  shift is fitted to pure saturated liquids. It lowers the average
  liquid-density error of the held-out pure states from 8.74 % to 2.64 %
  (methane), but makes the worst near-critical error worse, and no measured
  mixture density has been compared.
- **Components C1–C3 only.** Isobutane and n-butane are prepared on a draft
  branch and wait for the owner's check of the published constants. CO2 and
  N2 exist only as a plan.
- **Near a critical point** the stability test can wrongly call a state
  stable. No three-phase flash, C7+ characterisation or EOS tuning.

## Open decisions, with a recommendation

| Decision | Recommendation |
|---|---|
| Supply the six Yang & Richter (2025) Table 5 values for the butanes | **Do it.** Admission is one command, already dry-run on provisional values with the methane–ethane and methane–propane results unchanged (draft PR 47). |
| P10: faster envelope options that change result objects | **Approve option (b) only after a wider survey** shows no lost envelope points. Reject (a): it loses a branch and the hidden-root safety net. |
| A second experimental source | **Fetch NIST ThermoML data from the desktop** (the web sessions' proxy blocks trc.nist.gov) and compare it with the engine at kij = 0. It is the most useful next piece of evidence. |
| Volume translation default | **Keep it off** until measured mixture liquid densities are compared. |
| Faculty review of the dew interpretation and the evidence | **Ask for it.** It is the main scientific claim a reviewer should check. |
