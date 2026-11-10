# Lab 5: Liquid density and volume translation (propane, methane + propane)

**Tool:** OpenPhase (Peng–Robinson EOS), live app or a local copy, with the
optional volume translation.
**Fluids:** pure propane and methane–propane.
**Time:** about 60 minutes.
**Prerequisites:** Lab 1, and the compressibility factor Z = Pv/(RT) from a
thermodynamics course.

Switch on **Learn mode** in the sidebar for short explanations on each page.

## Learning outcomes

By the end of the lab you should be able to:

1. Turn a compressibility factor into a molar volume and a molar density.
2. Say how well Peng–Robinson predicts saturated-liquid density, and where it
   is worst.
3. Apply a Péneloux volume shift by hand and check it against the app.
4. Explain why a constant shift changes volumes but not phase equilibrium.

## Background

Peng–Robinson predicts vapour pressures well, but its liquid volumes are
biased. Péneloux volume translation corrects this by shifting every molar
volume by a constant per component:

    v_translated = v_PR − c_mix,   c_mix = Σ xᵢ cᵢ

OpenPhase ships one shift per component, fitted to the saturated liquid at
reduced temperature 0.7 of reference equations of state
(`docs/VOLUME_TRANSLATION.md`). The shifts are methane −4.114, ethane −4.425
and propane −4.941 cm³/mol. They are negative, so translation makes volumes
**larger** and densities **smaller**.

To see translated values, open **Advanced: volume translation (Péneloux)** in
the sidebar and switch on **Show volume-translated densities**. After **RUN
FLASH**, Overview shows a table with the PR and translated molar volume and
density of each phase. The switch changes no calculation.

Use R = 8.31446261815324 J/(mol·K).

## Part A: Liquid propane by hand

Enter pure propane (0 / 0 / 100 mol %), 258.923 K (T_r = 0.70) and 1.0 MPa,
then press **RUN FLASH**. The feed is a single liquid phase.

1. From the PR molar volume in the table, compute Z = Pv/(RT).
2. Compute the PR molar density 1/v in mol/m³ and check it against the table.
3. Apply the propane shift by hand to get the translated molar volume and
   density. Check both against the table.

## Part B: How good is PR along the saturation curve?

`docs/investigations/volume_translation_fit.csv` compares PR saturated-liquid
densities of propane with the reference equation of state (Lemmon et al.),
before and after the shift. Read the rows for propane at T_r = 0.50, 0.70,
0.90 and 0.98.

1. Tabulate the reference density, the PR and translated densities, and the
   error 100·(ρ_model − ρ_ref)/ρ_ref before and after.
2. Why is the error after the shift exactly zero at one of these
   temperatures?
3. Where does the shift help, and where does it make the error worse? Explain
   using the sign of the PR error.

## Part C: A two-phase mixture

Enter 50 / 0 / 50 mol % methane / propane, 250 K and 5.0 MPa, and press **RUN
FLASH** with volume translation **off**. Note the liquid fraction and both
phase compositions. Then switch translation **on**.

1. Did the liquid fraction or any phase composition change? Why not?
2. From the liquid composition, compute c_mix for the liquid by hand. Check
   that v_translated − v_PR from the table equals −c_mix.
3. Do the same for the vapour. Which phase's density changes more, in
   percent, and why?

## Part D: Discussion

1. A constant shift adds the same term −cᵢP/(RT) to ln φᵢ in the liquid and in
   the vapour. Use this to explain your answer to Part C, question 1.
2. The shifts were fitted to pure saturated liquids. What measurements would
   you need before trusting translated densities of methane + propane
   liquids?
3. Why might an engineer still prefer the untranslated PR model near the
   critical point?

---

## Instructor answer key

All values are from the unchanged engine with production defaults, through the
same calls the app makes, and from the committed fit table.
`tests/test_teaching_lab_05.py` recomputes every number below.

**Part A** (propane, 258.923 K, 1.0 MPa, single liquid phase).

| Quantity | PR | Translated |
|---|---:|---:|
| Molar volume (cm³/mol) | 75.42 | 80.36 |
| Molar density (mol/m³) | 13259 | 12444 |

- Z = Pv/(RT) = 0.03503.
- The shift adds 4.941 cm³/mol to the volume (c = −4.941 cm³/mol). The
  density falls by 6.15 %.

**Part B** (propane, saturated liquid; densities in mol/m³).

| T_r | Reference | PR | Translated | Error before | Error after |
|---:|---:|---:|---:|---:|---:|
| 0.50 | 14320 | 15249 | 14180 | +6.49 % | −0.97 % |
| 0.70 | 12410 | 13220 | 12410 | +6.53 % | +0.00 % |
| 0.90 | 9718 | 9607 | 9171 | −1.15 % | −5.63 % |
| 0.98 | 7544 | 6678 | 6464 | −11.49 % | −14.31 % |

- At T_r = 0.70 the shift was fitted, so the error after is zero by
  construction. That state is not a test of the method.
- At low temperature PR **over**-predicts the liquid density, so lowering it
  helps. Near the critical point PR already **under**-predicts it, and a
  constant negative shift lowers it further: the error grows from −11.49 % to
  −14.31 % at T_r = 0.98.

**Part C** (50 / 0 / 50 mol %, 250 K, 5.0 MPa, two phases).

| Phase | CH4 (mol %) | PR volume (cm³/mol) | Translated volume (cm³/mol) | PR density (mol/m³) | Translated density (mol/m³) |
|---|---:|---:|---:|---:|---:|
| Liquid | 41.09 | 67.18 | 71.78 | 14885 | 13931 |
| Vapor | 91.42 | 306.81 | 310.99 | 3259 | 3216 |

- The liquid fraction (0.8230) and both compositions are the same with the
  switch on or off. The switch only post-processes volumes.
- Liquid: c_mix = 0.4109 × (−4.114) + 0.5891 × (−4.941) = −4.601 cm³/mol, so
  the volume grows by 4.601 cm³/mol.
- Vapour: c_mix = −4.185 cm³/mol. A shift of a few cm³/mol matters much more
  for the small liquid volume: the liquid density falls by 6.41 %, the vapour
  density by only 1.35 %.

**Part D.**

- ln Kᵢ = ln φᵢ(liquid) − ln φᵢ(vapour). The extra −cᵢP/(RT) appears in both
  terms and cancels, so K-values, the phase split, the compositions and the
  saturation pressures do not change.
- Measured liquid densities of methane + propane mixtures, with stated
  uncertainties, over the temperatures and pressures of interest. OpenPhase
  has **no mixture-density validation** yet.
- Near the critical point the constant shift makes PR's liquid density worse
  (Part B). A temperature-dependent shift could fix that, but it would no
  longer cancel in the fugacity ratio.
