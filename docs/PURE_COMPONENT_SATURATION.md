# Pure-component saturation check (V2-01-E, investigation)

Status: investigation; **proposed new reference data source, awaiting owner
review.** No engine, validation artifact or application behaviour is changed.

## Question

How well does the project's Peng–Robinson model reproduce the vapour pressure
and saturated densities of its three verified pure components? This is the most
basic check of an equation of state. It separates pure-component behaviour from
mixing-rule and kij effects.

## Reference values

The reference values come from the published reference equations of state,
evaluated with CoolProp 6.6.0 (MIT licence):

| Component | Reference equation of state | Tc (K) | Pc (MPa) |
|---|---|---:|---:|
| Methane | Setzmann & Wagner, J. Phys. Chem. Ref. Data (1991) | 190.564 | 4.5992 |
| Ethane | Bücker & Wagner, J. Phys. Chem. Ref. Data (2006) | 305.322 | 4.8722 |
| Propane | Lemmon, McLinden & Wagner, J. Chem. Eng. Data (2009) | 369.890 | 4.2512 |

These critical constants are identical to the project's verified component
properties (Yang & Richter, 2025), so the reduced temperatures mean the same
thing on both sides.

`tools/generate_pure_saturation_reference.py` produced 75 reference states
(Tr = 0.50 to 0.98 in steps of 0.02). It ran once, in a throwaway environment,
so CoolProp is **not** a project dependency. The output is
`docs/investigations/pure_saturation_reference.csv`. Its provenance (CoolProp
version, equation-of-state identifiers, reference critical and triple points)
is in `pure_saturation_reference_provenance.json`.

`tools/run_pure_saturation_study.py` evaluates the unchanged engine at the same
temperatures:

- saturation pressure from the production solver, with Newton refinement on;
- liquid and vapour molar densities from the selected PR roots.

It writes `docs/investigations/pure_saturation_comparison.csv`.

## Results (all 75 states solved)

| Component | Saturation pressure AARD | Saturated liquid density AARD | Saturated vapour density AARD |
|---|---:|---:|---:|
| Methane | 0.73 % | 8.83 % | 1.58 % |
| Ethane | 0.59 % | 6.57 % | 1.21 % |
| Propane | 0.72 % | 5.55 % | 1.22 % |

Selected states (signed relative error, PR minus reference):

| Component | Tr | P_sat | Liquid density | Vapour density |
|---|---:|---:|---:|---:|
| Methane | 0.50 | +1.22 % | +12.77 % | +1.02 % |
| Methane | 0.70 | +0.57 % | +11.06 % | +0.44 % |
| Methane | 0.98 | +0.42 % | −8.26 % | +4.63 % |
| Ethane | 0.70 | +0.01 % | +8.03 % | −0.35 % |
| Propane | 0.50 | +4.07 % | +6.49 % | +3.95 % |
| Propane | 0.70 | −0.21 % | +6.53 % | −0.67 % |
| Propane | 0.98 | +0.40 % | −11.49 % | +2.66 % |

## Interpretation

- **Vapour pressure is good.** The error is below 1 % on average and smallest
  near Tr = 0.7. This is expected: the acentric factor is defined from the
  vapour pressure at Tr = 0.7, and PR's α(T) correlation is built around it.
  The errors grow at low reduced temperature (propane +4 % at Tr = 0.5).
- **Saturated liquid density is PR's known weakness.** It is too high at low
  temperature (methane +12 %, propane +6.5 %) and too low near the critical
  point (−8 to −11 % at Tr = 0.98). The model's critical compressibility,
  Zc = 0.307, is larger than the real fluids' (about 0.28). This is the
  behaviour that Péneloux volume translation corrects. The project does not
  implement volume translation (README, Current limitations), so liquid
  densities from this app should not be used quantitatively.
- **Saturated vapour density is good** (about 1–2 %), except close to the
  critical point.

These are pure-component results. They do not test mixing rules or kij.

## Decisions for the project owner

1. Accept CoolProp-evaluated reference equations as a reference source for
   pure-component checks. The alternative is tabulated literature data, which
   would need its own provenance work.
2. Decide whether this becomes part of the formal validation framework (V2-01)
   or stays an investigation.
3. Decide whether to show liquid densities in the app with a warning, or to add
   Péneloux volume translation as a future engine module.
