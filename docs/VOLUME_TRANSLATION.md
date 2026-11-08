# Optional volume translation (Péneloux)

Owner approval C, 8 November 2026. Proposal P11 in
`docs/ENGINE_CHANGE_PROPOSALS.md`.

## What it is

Peng–Robinson overpredicts saturated-liquid density for methane, ethane and
propane by up to about 12 % (`docs/PURE_COMPONENT_SATURATION.md`). Péneloux
volume translation shifts every molar volume by a constant per component:

    v_translated = v_PR − c_mix,   c_mix = Σ xᵢ cᵢ

`src/pvt_phase_simulator/eos/volume_translation.py` implements it as a separate,
optional module:

- **Off by default.** No solver in the engine imports it
  (`tests/test_volume_translation.py` checks this), so every engine result is
  byte-identical. The engine fingerprint (801 cases) was compared before and
  after: see the PR.
- **Only volumes change.** A constant shift adds the same `−cᵢ P / (R T)` to
  `ln φᵢ` in every phase. Fugacity ratios, K-values, the phase split, the
  phase compositions and the saturation pressures therefore stay those of the
  untranslated model. The module only post-processes a volume the engine
  already computed. The tests prove the cancellation on a real flash and check
  that a flash and a bubble-pressure calculation are unchanged.
- **App.** The collapsed *Advanced: volume translation (Péneloux)* switch in
  the sidebar adds one Overview table, with PR and translated molar volume and
  density for each phase. It is display only: exports, saved cases and every
  other page are unchanged.

## Where the shifts come from

The shifts are a **stated fit, not a published correlation**. No published PR
shift values were verified in this session, so none are used.

Each shift is anchored at one state, the saturated liquid at reduced
temperature 0.7 of the reference equations of state in
`docs/investigations/pure_saturation_reference.csv`. Those values come from
CoolProp 6.6.0 (Setzmann–Wagner methane, Bücker–Wagner ethane, Lemmon
propane); the owner accepted this file as a reference source on 30 October
2026.

    cᵢ = 1 / ρ_PR,liquid(T_r = 0.7) − 1 / ρ_reference,liquid(T_r = 0.7)

Here ρ_PR is the unchanged engine's saturated-liquid density at its own
saturation pressure. `tools/fit_volume_translation.py` computes the shifts and
the table below, and writes `docs/investigations/volume_translation_fit.csv`.
The tests recompute both.

## Errors on held-out states, before and after

All the other reference states are held out: T_r = 0.50 to 0.98 in steps of
0.02, except 0.70. Shift c is in cm³/mol. Errors are absolute relative
errors against the reference equation of state.

| Component | c (cm³/mol) | Held-out states | Liquid AARD before | Liquid AARD after | Liquid max before | Liquid max after | Vapour AARD before | Vapour AARD after |
|---|---|---|---|---|---|---|---|---|
| methane | -4.114 | 24 | 8.74 % | 2.64 % | 12.77 % | 13.15 % | 1.63 % | 1.05 % |
| ethane | -4.425 | 24 | 6.51 % | 2.69 % | 10.42 % | 13.92 % | 1.24 % | 0.94 % |
| propane | -4.941 | 24 | 5.51 % | 2.76 % | 11.49 % | 14.31 % | 1.24 % | 1.04 % |

**Reading the table.**

- The average liquid-density error falls by a factor of 2 to 3.
- The **worst** liquid error gets slightly worse for every component. It sits
  at T_r = 0.98, next to the critical point, where PR already underpredicts
  the liquid density and a constant negative shift pushes it further.
- A constant shift cannot fix the near-critical region. Temperature-dependent
  shifts could, but they would break the K-value cancellation above, so they
  are out of scope.

## What is not validated

- **There is no mixture-density validation.** Mixture shifts use the linear
  rule above, and no measured mixture density has been compared.
- The fit uses saturated states of pure components only. Compressed-liquid
  and supercritical states were not checked.
- The reference values are equations of state, not raw measurements. Their
  own uncertainty is not propagated.
