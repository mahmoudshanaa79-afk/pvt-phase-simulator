# OpenPhase

*An open phase-behaviour simulator built on the Peng–Robinson equation of state.*

OpenPhase (repository and distribution name `pvt-phase-simulator`) calculates
the phase behaviour of light-hydrocarbon mixtures. It is an educational and
portfolio project: every result states its status and the engine's own reason,
and every number shown to students is recomputed from the engine by a test.

- **Public app:** <https://pvt-phase-simulator-wpykmumyxwefbv3prht7gv.streamlit.app/>
  (Streamlit Community Cloud, served from `master`; it can take a minute to
  wake up).
- **Where the project stands:** [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md).
- **How to use the app:** [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md).
- **All documentation:** [`docs/README.md`](docs/README.md).
- **Changes by version:** [`CHANGELOG.md`](CHANGELOG.md).

## What OpenPhase is

- A Peng–Robinson model with classical mixing rules for **methane, ethane and
  propane**, whose critical constants and acentric factors are verified
  against Yang & Richter (2025), doi:10.1021/acs.jced.5c00110.
- Phase-stability tests (tangent-plane distance), a two-phase flash, bubble
  and dew pressures, phase-envelope tracing (with an optional extension
  towards the critical region) and a certified mixture critical-point solver.
- Compared, without any fitting, with 40 measured methane + ethane and
  methane + propane states from May et al. (2015).
- A Streamlit app with a Learn mode and four teaching labs.

## What OpenPhase is not

- **Not commercial PVT software**, and not a substitute for engineering
  review.
- Not a reservoir-fluid characterisation tool: no C7+ or pseudo-components,
  no CCE/CVD, separators or depletion, and no EOS tuning.
- Not a three-phase or multiphase flash.
- Not a density tool: there is no volume translation, so liquid densities are
  not quantitative.

## Quick start

You need Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --locked
```

```bash
uv run streamlit run streamlit_app.py
```

The app opens in your browser. Pick an example in the sidebar, press
**RUN FLASH**, then open the other pages. The
[user guide](docs/USER_GUIDE.md) walks through each one.

## App pages

| Page | What it does |
|---|---|
| Overview | The flash result for the submitted case: phases, fractions, compositions, model scope, downloads |
| Phase Envelope | Bubble and dew curves, the optional extended trace towards the critical region, and the operating point |
| Critical Point | The certified critical-point solver and a criticality map |
| Engineering Sweeps | Flash results over a pressure or temperature range; failed points stay failed |
| Validation | The protected comparison with measured data, plus further evidence tabs |
| Diagnostics | Solver codes and engine messages in plain language |

The sidebar also holds **Learn mode** (explanations and "Try this"
exercises), **Save or load case**, and the collapsed **Advanced: binary
interaction (kij)** inputs. kij = 0 unless you set a value; a non-zero kij is
labelled as user-supplied in every result and export.

## Teaching labs

- [Lab 1: methane–propane phase behaviour](docs/teaching/LAB_01_METHANE_PROPANE.md)
- [Lab 2: methane–ethane bubble pressures and the P–x–y diagram](docs/teaching/LAB_02_METHANE_ETHANE.md)
- [Lab 3: how composition moves the phase envelope](docs/teaching/LAB_03_COMPOSITION_AND_THE_ENVELOPE.md)
- [Lab 4: what kij does](docs/teaching/LAB_04_BINARY_INTERACTION.md)

## Evidence

From the protected validation record
([`docs/EXPERIMENTAL_VALIDATION.md`](docs/EXPERIMENTAL_VALIDATION.md)),
at kij = 0:

| System | Bubble pressure | Unique dew pressure found |
|---|---|---|
| methane + ethane | 1.02 % AARD, 17 of 17 states | 8 of 17 states |
| methane + propane | 1.01 % AARD, 23 of 23 states | 1 of 23 states |

Most dew failures are not solver crashes. At those states PR itself has two
dew pressures, and the engine reports *inconclusive* instead of picking one
([`docs/DEW_INVESTIGATION.md`](docs/DEW_INVESTIGATION.md)). Further evidence:

- the kij study: [`docs/investigations/kij_study.md`](docs/investigations/kij_study.md);
- a pure-component check against reference equations of state:
  [`docs/PURE_COMPONENT_SATURATION.md`](docs/PURE_COMPONENT_SATURATION.md);
- the equations and where each is implemented:
  [`docs/EQUATIONS.md`](docs/EQUATIONS.md).

## Known limits

- **One experimental source.** Every validation state comes from May et al.
  (2015).
- **Dew pressures** are often not unique in PR near the maximum vapour
  composition. The app then reports none, by design.
- **Three components only.** Isobutane and n-butane are prepared on a draft
  branch but wait for the owner's check of the published constants
  ([`docs/BUTANES_ADMISSION_PLAN.md`](docs/BUTANES_ADMISSION_PLAN.md)).
- **Near a critical point**, the stability test can wrongly call a state
  stable. Treat near-critical classifications with caution.
- **The first phase envelope of a case is slow** (the page states the expected
  time). Running the same case again is answered from a cache.
- The extended envelope can stop early. When it does, it shows the engine's
  reason and the envelope is not called closed.

## Development

```bash
uv sync
```

```bash
uv run ruff check . && uv run ruff format --check .
```

```bash
uv run mypy
```

```bash
uv run pytest -q -n auto
```

CI ([`.github/workflows/quality.yml`](.github/workflows/quality.yml)) runs
the lockfile check, Ruff, formatting, mypy, the full test suite, a
real-browser test and a Streamlit health check on every push. It never
deploys. The scientific engine (`src/pvt_phase_simulator/`), the property data
(`data/`), the validation record (`docs/validation/`) and the golden master
(`tests/golden_master/`) change only with the owner's explicit approval
([`docs/ENGINE_CHANGE_PROPOSALS.md`](docs/ENGINE_CHANGE_PROPOSALS.md)).

Package layout:

```text
src/pvt_phase_simulator/        # scientific engine (frozen)
  eos/                          # PR roots, mixing, fugacity, stability, flash,
                                # saturation, envelope, criticality
src/pvt_phase_simulator_ui/     # Streamlit app
src/pvt_phase_simulator_validation/  # validation framework and reports
streamlit_app.py                # app entry point
tests/                          # tests, including the golden master
tools/                          # generators, studies, smoke checks
docs/                           # documentation (see docs/README.md)
```

All engine APIs take SI units (K, Pa, mol). The app converts field units only
at its inputs and outputs.
