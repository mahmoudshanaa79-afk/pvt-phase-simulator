# OpenPhase user guide

A short walk through the app. For what the model can and cannot do, see the
[README](../README.md); for the technical design of each page, see
[`STREAMLIT_APPLICATION.md`](STREAMLIT_APPLICATION.md).

## 1. Open the app

- **Online:** <https://pvt-phase-simulator-wpykmumyxwefbv3prht7gv.streamlit.app/>.
  If it has been asleep, it takes a minute to wake up.
- **On your computer:** `uv sync --locked`, then
  `uv run streamlit run streamlit_app.py`.

On a phone the sidebar starts closed; open it with **»** at the top left.

## 2. Enter a case

In the sidebar:

1. Choose an **Example case**, or type a composition in mol % for methane,
   ethane and propane. The composition must add up to 100 %. The app refuses
   other totals instead of rescaling them.
2. Enter the temperature and pressure. **Display and entry units** lets you
   choose K, °C or °F and Pa, MPa, bar or psi. The engine always works in K
   and Pa.
3. Press **RUN FLASH**.

Choosing an example only fills the inputs; nothing runs until you press a
button.

## 3. Read the result (Overview)

- Whether the feed is **single-phase** or **two-phase**, with the engine's
  status and reason.
- For two phases: the liquid and vapour fractions (in a bar and in words) and
  each phase's composition.
- The **Model and limitations** panel: what this model covers and on what
  evidence.
- **Download CSV**, **Download JSON** and **Download report** export the
  current case at full precision. They are offered only when the current
  inputs have a current result.

If you change an input after a calculation, every earlier result is marked
**stale**. It stays visible behind a warning, but it is never presented as
the answer to the new inputs.

## 4. Other pages

- **Phase Envelope.** Press **RUN PHASE ENVELOPE**. The first run of a case is
  the slowest, and the page states how long to expect. The plot shows the
  bubble and dew curves, the extended trace towards the critical region and
  your operating point. A branch that stops early says why. The envelope is
  called closed only when both extended branches reach the engine's
  near-critical guard.
- **Critical Point.** **RUN CRITICAL SOLVER** looks for the mixture critical
  point from a seed. Only a *converged* result is a certified critical point.
  **RUN CRITICALITY MAP** shows the stability curvature around it.
- **Engineering Sweeps.** Choose pressure or temperature, set the bounds and
  press **RUN SWEEP**. Each point is an ordinary flash. A failed point stays
  failed, and the line breaks there instead of joining across it.
- **Validation.** **GENERATE VALIDATION FIGURES** draws the protected
  comparison with the measured May et al. (2015) data, always at kij = 0.
  The *Further evidence* tabs show the dew-conditioning study, the Newton
  comparison and the pure-component check.
- **Diagnostics.** The solver codes from your last runs, explained in plain
  language.

## 5. Options

- **Learn mode** (sidebar switch) adds a short explanation and "Try this"
  exercises to each page, and links to the five teaching labs. It never
  changes a result.
- **Advanced: binary interaction (kij).** kij = 0 unless you enter a value for
  a pair in the mixture. A non-zero kij carries a *user-supplied kij* badge
  and is recorded in every result, export and saved case.
- **Advanced: volume translation (Péneloux)**, off by default, adds a table
  of each phase's molar volume and density with and without the shift. It
  changes no result, export or saved case. The shifts are fitted to pure
  saturated liquids; mixture densities are not validated
  ([`VOLUME_TRANSLATION.md`](VOLUME_TRANSLATION.md)).
- **Save or load case** stores the inputs as a JSON file and loads them back.
  A file is checked before anything runs; a bad file is refused with a
  specific message. A browser reload starts a new session and clears results,
  but not saved cases.

## 6. Reading statuses honestly

- *Converged* means the solver met its own checks. It does not mean the model
  matches experiment; see the Validation page for that.
- *Inconclusive* and *not found* are real outcomes. For dew points, an
  inconclusive result usually means PR itself has two dew pressures at that
  state ([`DEW_INVESTIGATION.md`](DEW_INVESTIGATION.md)).
- Near a critical point, the stability test can wrongly report a state as
  stable.

## 7. Teaching labs

Lab worksheets with instructor keys are in [`teaching/`](teaching/). Every
number in the keys is recomputed from the engine by the tests.

- [Lab 1: methane–propane phase behaviour](teaching/LAB_01_METHANE_PROPANE.md)
- [Lab 2: methane–ethane bubble pressures](teaching/LAB_02_METHANE_ETHANE.md)
- [Lab 3: composition and the envelope](teaching/LAB_03_COMPOSITION_AND_THE_ENVELOPE.md)
- [Lab 4: what kij does](teaching/LAB_04_BINARY_INTERACTION.md)
- [Lab 5: liquid density and volume translation](teaching/LAB_05_LIQUID_DENSITY.md)
