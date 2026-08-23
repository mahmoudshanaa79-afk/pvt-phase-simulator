# Module 17 Experimental VLE Validation

## A. Experimental source and data quality

Module 17 asks how the unchanged Peng--Robinson (PR) implementation compares
with measured binary vapor--liquid equilibrium (VLE). Verification establishes
that code solves its stated equations; validation measures how the model and
current production solver compare with reality. This distinction is essential
where the PR dew objective has more than one valid root.

The source is E. F. May, J. Y. Guo, J. H. Oakley, T. J. Hughes, B. F. Graham,
K. N. Marsh, and S. H. Huang, "Reference Quality Vapor-Liquid Equilibrium Data
for the Binary Systems Methane + Ethane, + Propane, + Butane and,
+ 2-Methylpropane, at Temperatures from (203 to 273) K and Pressures to 9 MPa,"
*Journal of Chemical & Engineering Data* **60** (2015), 3606--3620,
[DOI 10.1021/acs.jced.5b00610](https://doi.org/10.1021/acs.jced.5b00610).
The machine-readable source is the [NIST ThermoML record](https://trc.nist.gov/ThermoML/10.1021/acs.jced.5b00610.html)
and [JSON representation](https://trc.nist.gov/ThermoML/10.1021/acs.jced.5b00610.json).

Source inspection confirmed the citation, seven authors, DOI, compound numbers
(1 methane, 2 ethane, 3 propane), independent variables, properties, units,
methods, uncertainties, and counts. The selected records contain 17 CH4+C2 and
23 CH4+C3 paired `p,T,x,y` states. Pressure used a closed-cell static method and
vapor composition used chromatography. ThermoML supplies InChI identities but
not CAS fields for these records; manifest CAS values are explicitly labeled
production-database cross-references.

ThermoML stores pressure and vapor-heavy composition separately. The extractor
validates both schemas and joins unique observations by exact system,
temperature, and liquid methane mole fraction--never array index. Every row
retains both source dataset and row identities. Duplicate, missing, ambiguous,
or unpairable observations fail loudly. Source kPa is converted exactly using
`P_Pa = 1000 P_kPa`; K and dimensionless mole fractions require no numerical
conversion. The 40-row normalized CSV remains SHA-256
`04ED00B661A90222583F591855A6847580E9A173F0A7BBCC185E02E9C71407BD`.

The source JSON inspected on 2026-08-22 had SHA-256
`77630E90DB70BB6AABFDFA520F61F14CEE5076ECE0265754140A25F771659662`.
It is not redistributed because the archive states no redistribution license.
The normalized facts, exact URLs/hash, manifest, row provenance, and extractor
provide offline reproducibility.

### Out-of-title-range temperatures

The title states 203--273 K, while paired CH4+C3 observations contain both
273.48 K and 283.38 K. The 273.48 K value exceeds 273 K by only 0.48 K and is
plausibly compatible with a rounded title range. The 283.38 K value is the
material discrepancy. Each temperature occurs independently in both the
pressure and vapor-composition source observations; neither is an extractor
pairing artifact. Both are retained rather than silently removed.

### Uncertainty semantics

ThermoML supplies per-point 95% expanded uncertainty `U` for pressure and the
vapor heavy-component fraction. The complementary methane fraction has the same
absolute uncertainty. Numerical temperature and liquid-composition uncertainty
are unavailable, so dew liquid-composition uncertainty scoring is unavailable.
The normalized residual is `(prediction - experiment)/U`; within 1U means
`|prediction - experiment| <= U`, not one standard deviation. Failed production
solves never enter uncertainty or error denominators.

## B. Production-selected solver validation

All calculations retain verified `Tc/Pc/omega`, classical PR mixing, `kij=0`,
and unchanged production defaults. No parameter was fitted, no search bound or
tolerance was tuned, and no source state was removed because of error or
nonconvergence.

Bubble validation specifies experimental `(T,x)` and compares the production
pressure and vapor composition with `(P_exp,y_exp)`. Dew validation specifies
experimental `(T,y)` and records what the current production dew solver actually
returns. The production-selected prediction remains prospective: experimental
pressure is not used to select its branch.

For successful predictions, `e_j=P_pred,j-P_exp,j` and
`r_j=e_j/P_exp,j`. Pressure MAE is `mean(|e_j|)`; AARD is
`100 mean(|r_j|)`; RMS relative error is `100 sqrt(mean(r_j^2))`; maximum
absolute relative error is `100 max(|r_j|)`; bias is `100 mean(r_j)`.
Composition MAE averages absolute component errors. Failures have missing
errors, never zero, infinite, or arbitrary errors.

| System/direction | Source / success / failure | Pressure AARD (%) | RMS (%) | Bias (%) | Composition MAE / maximum |
|---|---:|---:|---:|---:|---:|
| CH4+C2 bubble | 17 / 11 / 6 | 0.454690 | 0.695762 | -0.290249 | 0.00370912 / 0.00881340 |
| CH4+C2 production-selected dew | 17 / 15 / 2 | 6.045523 | 9.847260 | -4.646067 | 0.03902500 / 0.18938747 |
| CH4+C3 bubble | 23 / 20 / 3 | 1.033805 | 1.247494 | -1.022857 | 0.00228860 / 0.00704091 |
| CH4+C3 production-selected dew | 23 / 7 / 16 | 36.668238 | 42.402174 | -35.858326 | 0.22488983 / 0.51006121 |

The production-selected CH4+C3 dew AARD of approximately 36.7% characterizes
the current solver's selected branches on its seven successful states. It must
not be read as the intrinsic PR error across all available dew branches.

Pressure uncertainty results remain: CH4+C2 bubble 10/11 within 1U and 11/11
within 2U; CH4+C2 dew 8/15 and 13/15; CH4+C3 bubble 11/20 and 15/20; CH4+C3 dew
1/7 and 1/7. Bubble-composition counts are CH4+C2 10/11 and 11/11, and CH4+C3
20/20 and 20/20. Dew composition uncertainty is unavailable.

## C. PR dew branch-landscape diagnostics

The validation layer independently scans the PR dew objective at each measured
`(T_exp,y_exp)` from 50,000 Pa through 15,000,000 Pa in fixed 50,000 Pa linear
increments. Every trustworthy converged sign-change bracket is refined in
log-pressure with deterministic Brent iteration. A retained root must satisfy
the production objective, inner convergence, fugacity, stable-root,
non-triviality, and phase-role gates. Duplicate roots are collapsed within a
documented numerical tolerance and valid roots are ordered by pressure.

This scan is read-only and is not part of the production saturation solver.
More than one root is described as multiple/retrograde dew-root structure only
within the examined domain; it is not a formal proof of global retrograde phase
behavior.

| Diagnostic accounting | CH4+C2 | CH4+C3 |
|---|---:|---:|
| Dew states examined | 17 | 23 |
| Zero / one / multiple roots | 0 / 13 / 4 | 2 / 1 / 20 |
| Production success | 15 | 7 |
| Production class: single / lower / upper / intermediate / unmatched | 13 / 2 / 0 / 0 / 0 | 1 / 6 / 0 / 0 / 0 |
| Production failures with demonstrated root | 2 | 14 |
| Production failures with no root found in scan | 0 | 2 |

Across all states with a diagnostic root, nearest available PR dew-root AARD is
5.031582% for CH4+C2 (17 states) and 10.710868% for CH4+C3 (21 states). On only
the production-successful subsets it is 5.112453% (15) and 13.517856% (7).
These are **nearest available PR dew-root agreement** metrics. They use
experimental pressure retrospectively to identify which already-existing PR
root is nearest. They are not corrected predictions, improved model
predictions, or a prospective branch-selection algorithm.

### Independently reproduced multiple-root cases

| Point | P experimental (Pa) | Production P / class | Alternative P / class | Production error | Nearest-root diagnostic error |
|---|---:|---:|---:|---:|---:|
| `may2015_ch4_c3_014` | 7,943,000 | 2,930,670.14 / LOWER | 7,773,260.51 / UPPER | -63.1037% | -2.1370% |
| `may2015_ch4_c3_015` | 8,320,000 | 2,550,204.25 / LOWER | 8,158,606.57 / UPPER | -69.3485% | -1.9398% |
| `may2015_ch4_c3_023` | 7,630,000 | 5,840,051.39 / LOWER | 7,701,834.63 / UPPER | -23.4594% | +0.9415% |

The large production error at point 015 is retained. The alternative upper root
is reported alongside it, never substituted for it.

An upper-root heuristic would be scientifically invalid. At
`may2015_ch4_c3_001`, the lower root 2,226,405.88 Pa is nearer the 3,576,000 Pa
experiment than the upper root 5,318,788.78 Pa. At
`may2015_ch4_c3_003`, the upper root 5,761,102.38 Pa is nearer the 4,628,000 Pa
experiment than the lower production root 3,223,680.98 Pa. The diagnostic
reports the landscape; it does not invent a new selection rule.

### Production failure interpretation

Production failure is not automatically model error. Both CH4+C2 dew failures
and 14 of 16 CH4+C3 dew failures have a valid diagnostic PR root that the
current production search does not reach. Thus 16 of 18 failures primarily
expose current solver reachability/branch-selection limitations. Points
`may2015_ch4_c3_020` and `may2015_ch4_c3_021` have no valid dew root found in the
documented scan; this does **not** claim that no PR solution exists outside the
grid or by another valid numerical path. Failed states remain excluded from
successful-production error metrics.

### 283.38 K retention sensitivity

Recomputed production-selected sensitivity is:

| Direction | With point: n / AARD / RMS / bias (%) | Without point: n / AARD / RMS / bias (%) | AARD shift when excluded |
|---|---:|---:|---:|
| CH4+C3 bubble | 20 / 1.033805 / 1.247494 / -1.022857 | 19 / 0.980767 / 1.191129 / -0.969243 | -0.053038 percentage points |
| CH4+C3 dew | 7 / 36.668238 / 42.402174 / -35.858326 | 6 / 38.869719 / 44.787032 / -37.924821 | +2.201481 percentage points |

Removing 283.38 K makes the problematic production-selected dew AARD worse,
not better. Retaining it is therefore not favorable cherry-picking.

## D. Measured-state fugacity residuals

The direct measured-state check evaluates
`r_f,i=ln(f_i^L/f_i^V)=ln(x_i phi_i^L)-ln(y_i phi_i^V)` at experimental
`(T,P,x,y)`, using the minimum liquid and maximum vapor admissible PR roots. Its
norm `max_i |r_f,i|` does not depend on which outer dew-pressure root the
production solver selects.

CH4+C2 mean/RMS/maximum is
0.01453822/0.01996714/0.06560599. CH4+C3 is
0.03251196/0.05193279/0.18643184. These residuals help distinguish direct PR
thermodynamic mismatch from outer pressure-search and branch-selection behavior.

## Artifacts, limitations, and review gate

`tools/run_module17_validation.py` regenerates the result CSV and machine-readable
summary. Their SHA-256 values are currently:

- result CSV: `B14728D51AAC06AF38FC4F4E5F408942B253FEBE32D3E12EC26E9623CFA42482`;
- summary JSON: `5B120B77BF05567FCC6A0EE0D0054C6D1DEBA35FE26A7C837352C92017D24870`.

Coverage remains limited to two binaries, one source, its sampled domain,
`kij=0`, and a finite diagnostic scan. No numerical T or liquid-x uncertainty
is available. The nearest-root diagnostic is retrospective and cannot select a
prospective production branch. No production solver issue is fixed here.
Module 18 has not started. A second independent audit must review branch
discovery, classification, artifact accounting, no-fitting compliance, and
wording before Module 17 is committed.
