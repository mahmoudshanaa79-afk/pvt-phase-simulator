# Verified pure-component property migration

## Scope and source decision

Module 16.1 replaces the nine provisional Peng–Robinson inputs for methane,
ethane, and propane with values traceable to Xiaoxian Yang and Markus Richter,
“Effective Thermophysical Constants of Thousands of Fluids. I: Critical
Temperature, Critical Pressure, Critical Density, and Acentric Factor,”
*Journal of Chemical & Engineering Data* **70**(8), 2911–2946 (2025), DOI
`10.1021/acs.jced.5c00110`, American Chemical Society.

The primary article's Table 5 independently confirms all nine selected values,
component names, CAS registry numbers, and REFPROP as the original source. The
article states that Supporting Information Table S3 is the same table with
complete names. Canonical property identities therefore cite Table 5 by
component name and CAS RN; they do not claim an SI row number. The honest
evidence chain is production CSV → Yang and Richter Table 5 → table attribution
to REFPROP. The project did not query REFPROP directly.

The source describes its constants as compiled, optimized, or effective
values. `VERIFIED` means that the exact value and structured source metadata
were checked; it does not authenticate experimental truth or remove EOS and
source uncertainty.

## Exact migration and deterministic delta report

Relative differences below are `(new - old) / old`. All old rows were
`PROVISIONAL`; all new rows are `VERIFIED` and cite the source above.

| Component | Property | Unit | Old | New | Absolute difference | Relative difference |
|---|---|---:|---:|---:|---:|---:|
| methane | Tc | K | 190.56 | 190.564 | +0.004 | +2.09907640638119e-5 |
| methane | Pc | Pa | 4599200.0 | 4599200.0 | 0.0 | 0.0 |
| methane | omega | 1 | 0.011 | 0.011420 | +0.000420 | +3.81818181818182e-2 |
| ethane | Tc | K | 305.32 | 305.322 | +0.002 | +6.55050438883794e-6 |
| ethane | Pc | Pa | 4872000.0 | 4872200.0 | +200.0 | +4.10509031198686e-5 |
| ethane | omega | 1 | 0.099 | 0.099500 | +0.000500 | +5.05050505050505e-3 |
| propane | Tc | K | 369.83 | 369.890 | +0.060 | +1.62236703350188e-4 |
| propane | Pc | Pa | 4248000.0 | 4251200.0 | +3200.0 | +7.53295668549906e-4 |
| propane | omega | 1 | 0.152 | 0.152100 | +0.000100 | +6.57894736842105e-4 |

Primary Table 5 labels critical pressure in kPa. The exact audited path is
kPa → Pa using `1 kPa = 1000 Pa`. Thus 4599.20, 4872.20, and 4251.20 kPa
become 4,599,200, 4,872,200, and 4,251,200 Pa. The canonical numerical values
did not change in this correction pass. Both CSV copies are byte-identical at
SHA-256 `C6F6BA9AE9C2F4C7F257BBC09A75DF0D7065255868AA46BF3E8C81AC5A8B9B3A`.
This corrects the earlier Module 16.1 provenance metadata that described the
source unit as MPa; only source-location and conversion metadata changed.

## Peng–Robinson parameter impact

The values below were independently recalculated from the documented PR
equations at 300 K and 10 MPa. `aα` has units Pa·m⁶/mol² and `b` has units
m³/mol; the other listed quantities are dimensionless except `a`, which also
has units Pa·m⁶/mol².

| Component | Quantity | Old | New | New − old |
|---|---|---:|---:|---:|
| methane | kappa | 0.391572199680000 | 0.392217407205312 | +6.45207525312e-4 |
| methane | alpha | 0.810469986561017 | 0.810183407490909 | -2.86579070109e-4 |
| methane | a | 0.249570804421016 | 0.249581281894725 | +1.04774737095e-5 |
| methane | aα | 0.202269646505123 | 0.202206613411417 | -6.30330937054e-5 |
| methane | b | 2.68017548549506e-5 | 2.68023174442633e-5 | +5.62589312654e-10 |
| methane | A | 0.325102145717296 | 0.325000834451029 | -1.01311266267e-4 |
| methane | B | 0.107450339189424 | 0.107452594654143 | +2.25546471849e-6 |
| ethane | kappa | 0.524678254080000 | 0.525422594520000 | +7.44340440000e-4 |
| ethane | alpha | 1.00920342691361 | 1.00921994073793 | +1.65138243184e-5 |
| ethane | a | 0.604805614316304 | 0.604788710783143 | -1.69035331608e-5 |
| ethane | aα | 0.610371898584607 | 0.610364826855533 | -7.07172907310e-6 |
| ethane | b | 4.05379475220648e-5 | 4.05365490041220e-5 | -1.39851794282e-9 |
| ethane | A | 0.981033078091477 | 0.981021711906114 | -1.13661853636e-5 |
| ethane | B | 0.162519813902573 | 0.162514207134354 | -5.60676821842e-6 |
| propane | kappa | 0.602827288320000 | 0.602973306052800 | +1.46017732800e-4 |
| propane | alpha | 1.12335941187437 | 1.12348353558039 | +1.24123706024e-4 |
| propane | a | 1.01772947643031 | 1.01729340665115 | -4.36069779157e-4 |
| propane | aα | 1.14327598608996 | 1.14291239322706 | -3.63592862902e-4 |
| propane | b | 5.63159495865281e-5 | 5.62826885950021e-5 | -3.32609915260e-8 |
| propane | A | 1.83755438666617 | 1.83696999438616 | -5.84392280006e-4 |
| propane | B | 0.225775062774639 | 0.225641716848576 | -1.33345926063e-4 |

## Representative physical-result impact

Every scalar shown uses the unchanged implementation and conditions. Relative
difference is `|new-old|/|old|`. Composition rows report maximum absolute
component difference, for which a relative comparison is not meaningful.

| Calculation and output | Old | New | Absolute difference | Relative difference |
|---|---:|---:|---:|---:|
| pure CH4, 300 K/10 MPa, A | 0.325102145717296 | 0.325000834451029 | 1.01311266267e-4 | 3.11629029835e-4 |
| pure CH4, 300 K/10 MPa, B | 0.107450339189424 | 0.107452594654143 | 2.25546471849e-6 | 2.09907640637e-5 |
| pure CH4, 300 K/10 MPa, Z | 0.833776791485675 | 0.833891473736882 | 1.14682251207e-4 | 1.37545506636e-4 |
| pure CH4, 300 K/10 MPa, ln(phi) | -0.194918728442465 | -0.194806323101407 | 1.12405341058e-4 | 5.766779926997e-4 |
| CH4/C2 70/30, 300 K/10 MPa, aαmix | 0.301620299150652 | 0.301564925642191 | 5.53735084610e-5 | 1.83586809697e-4 |
| CH4/C2 70/30, 300 K/10 MPa, Bmix | 0.123971181603369 | 0.123971078398206 | 1.03205162597e-7 | 8.32493175121e-7 |
| CH4/C2 70/30, 300 K/10 MPa, Z | 0.689475751282300 | 0.689598425112177 | 1.22673829876e-4 | 1.77923341971e-4 |
| CH4/C2 70/30, methane ln(phi) | -0.165962561672498 | -0.165845955427423 | 1.16606245076e-4 | 7.02605719631e-4 |
| CH4/C2 70/30, ethane ln(phi) | -0.765907685610249 | -0.765810099853612 | 9.75857566368e-5 | 1.27411904163e-4 |
| CH4/C2 50/50 stability, 250 K/5 MPa, minimum TPD | -0.0482762441409997 | -0.0483582310786693 | 8.19869376696e-5 | 1.69828741089e-3 |
| CH4/C3 60/40 flash, 250 K/5 MPa, vapor fraction | 0.375299150262433 | 0.375725249450379 | 4.26099187946e-4 | 1.13535878685e-3 |
| same flash, liquid composition max | — | — | 3.85434981464e-4 | — |
| same flash, vapor composition max | — | — | 7.01210575693e-5 | — |
| CH4/C3 60/40 bubble, 250 K, pressure Pa | 7385216.135238444 | 7391642.208227274 | 6426.072988830 | 8.70126597672e-4 |
| same bubble, incipient composition max | — | — | 2.17012013315e-5 | — |
| CH4/C3 60/40 dew, 250 K, pressure Pa | 575969.5124486194 | 575360.2360506197 | 609.2763979997 | 1.05782751488e-3 |
| same dew, incipient composition max | — | — | 7.66278179718e-5 | — |
| pure CH4 Newton saturation, 170 K, pressure Pa | 2348696.1055850405 | 2347774.2603319585 | 921.845253082 | 3.92492349645e-4 |
| CH4/C3 dew envelope endpoint, 250 K, pressure Pa | 575969.512448602 | 575360.2360506033 | 609.276397999 | 1.05782751488e-3 |
| CH4/C3 bubble envelope endpoint, 250 K, pressure Pa | 7385216.1352384705 | 7391642.208227248 | 6426.072988777 | 8.70126597665e-4 |

The historical and Newton CH4/C3 dew values moved to
575360.2360506197 Pa and 575360.2360506136 Pa, respectively. Both solvers still
select the same physical dew branch. Bubble/dew phase ordering, nontrivial
multicomponent separation, mole-fraction bounds and sums, admissible roots,
fugacity convergence, flash material balance, and repeat determinism remain
satisfied.

## Frozen golden-master impact

The canonical `tests/golden_master/baseline.csv` was not regenerated. Its
pre- and post-migration SHA-256 remains
`CBDA39461C9F5B839EF59F60710DF4558C5A588B6C1C90913ECADF099356A27D`.
Strict comparison of all 328 cases against that frozen baseline found:

- 1,503 physical field differences across 322 cases;
- 48 numerical-path field differences across 37 cases;
- zero status changes and zero termination changes;
- zero missing cases and zero extra cases.

The 48 path differences are 24 inner-iteration counts, nine outer-iteration
counts, and 15 pressure-dependent rejected-attempt records. They do not change
accepted status or termination. The complete deterministic case manifest is
[`PROPERTY_SOURCE_MIGRATION_GOLDEN_IMPACT.csv`](PROPERTY_SOURCE_MIGRATION_GOLDEN_IMPACT.csv);
it lists all 324 cases with a physical and/or numerical-path change and the
changed fields. Four remaining cases differ only in frozen-source-commit or
within-tolerance formatting/noise metadata.

One focused pre-migration A-1 test began a binary near-critical trace at exactly
260 K. An independent high-precision calculation confirms that the verified-
property CH4/C2 50/50 physical bubble point still exists there at approximately
`6735786.55695833 Pa`, with parent and incipient roots approximately
`0.2975485` and `0.4256901` and root separation approximately `0.12814`. This
is not root coalescence. Production safely returns structured `NOT_FOUND`
because its deterministic 81-point logarithmic pressure scan misses a
trustworthy bracket in a narrow window around 260–260.25 K; converged states
exist immediately below and above it. This is a fixed-grid bracketing/
reachability regression, not evidence that the physical boundary moved away.

The A-1 continuation regression remains at 259 K because that valid start still
approaches the same near-critical endpoint, accepts no phase-role inversion,
and terminates safely as `NEAR_CRITICAL`. A separate 260 K regression pins the
current safe `NOT_FOUND` limitation. No saturation algorithm was changed in
Module 16.1. B-1 phase-role recovery, B-2 near-trivial rejection, and C-6
envelope defence-in-depth remain closed.

## Independent consistency check and limitations

Public NIST Chemistry WebBook phase-change pages provide broad independent
Tc/Pc agreement: methane about 190.6 K and 46.1 bar, ethane about 305.3 K and
49 bar, and propane about 369.9 K and 42.5 bar. Their displayed rounding and
uncertainties differ from Table 5; they were not substituted for the selected
Yang and Richter values.

This migration does not validate Peng–Robinson against experiment, calibrate
binary interactions, establish uncertainty, certify phase-diagram completeness,
or prove critical points. `kij=0` remains a modelling assumption. The final
independent audit found no Category A or B numerical defect, and the primary-
source corrections close the pre-rebaseline Category C findings. After Module
16.1 is committed, this evidence is ready for the dedicated Module 16.2
intentional rebaseline. Module 17 remains blocked until that work is reviewed.
