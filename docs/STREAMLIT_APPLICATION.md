# Streamlit application

## Purpose and launch

The optional Streamlit frontend is an interactive presentation layer over the
completed v1.0 Hydrocarbon Phase-Behavior & PVT Simulator. It supports
educational exploration and review of production scientific result objects. It
is not a commercial PVT package or a substitute for engineering review.

Launch it from the repository root:

```powershell
uv run streamlit run streamlit_app.py
```

This reproducibly installs the project and requires no manual `PYTHONPATH`.
`uv run streamlit run app/streamlit_app.py` remains a tested compatibility
entrypoint.

Prerequisites are Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).
`uv sync --locked` installs the exact dependency graph recorded in `uv.lock`. No
service, account, or credential is required.

For a bounded final-QA startup and HTTP health check using localhost only, run:

```powershell
uv run python tools/streamlit_smoke.py
```

`.venv/Scripts/python.exe tools/streamlit_smoke.py` is the equivalent direct
Windows invocation. The helper selects an available loopback port, waits at most
20 seconds by default, checks Streamlit's health endpoint, and always terminates
its child server process. Pass `--timeout` to allow more time on a cold machine;
continuous integration uses `--timeout 60`.

## Architecture

The application layer is installed separately from the frozen scientific
package:

- `streamlit_app.py` is the thin, stable root entrypoint.
- `src/pvt_phase_simulator_ui/app.py` owns navigation and submitted inputs.
- `src/pvt_phase_simulator_ui/pages/` contains the five page scripts.
- `src/pvt_phase_simulator_ui/adapters.py` validates inputs, converts boundary
  units, and selects public
  result fields without changing them.
- `src/pvt_phase_simulator_ui/state.py` associates each result with a scientific
  input signature.
- `.streamlit/config.toml` supplies the light engineering theme. Narrow custom
  styling is limited to the phase-split visualization.
- `src/pvt_phase_simulator/plotting.py` remains the source of scientific Plotly
  figures.

No EOS, fugacity, stability, flash, saturation, continuation, or criticality
equation is implemented in the UI package.

## Inputs and views

The persistent Fluid inputs form supports the verified v1.0 Methane, Ethane,
and Propane components. Composition is entered in mol %, temperature in K, and
pressure in MPa. On submission, the panel shows the composition total and rejects
nonfinite, negative, above-100, zero-total, and materially non-100% values. It
does not silently normalize invalid composition.

The native example selector can fill the form with the default
two-phase-oriented case, the known 50/50 methane/propane single-phase case at
300 K and 20 MPa, or the audited 50/50 methane/propane critical-solver seed near
321.5829183194 K and 8.53444323606381 MPa. Selection changes input values only;
it never submits the form or starts a scientific calculation. Every populated
value remains editable and passes through the same validation and conversion
boundary when the user explicitly submits it.

Valid composition is divided by 100 exactly for mole fractions. Valid pressure
is multiplied by `1e6` exactly before it reaches an SI-pressure API, and public
Pa results are divided by `1e6` for MPa display.

- **Overview:** entered state, phase and convergence statuses, available phase
  fractions and Z factors, source-provided compositions, and envelope location.
- **Phase Envelope:** independent bubble and dew traces using Module 21,
  status-aware unavailable points, terminations, critical overlay, and phase
  compositions when available.
- **Critical Point:** Module 20 certification evidence and optional Module 19
  maps, including Tc, Pc, lambda_min, C, direction, convergence, and conditioning.
- **Validation:** Module 17 artifacts rendered through Module 21 parity, error,
  composition, status, and retrospective figures.
- **Diagnostics:** public status, termination, iteration, residual, stability,
  continuation, Jacobian, and root evidence.

## API separation, state, and failure handling

The UI calls existing flash, envelope, critical-point, and criticality APIs
unchanged. Invalid input is rejected before a production call. Every expensive
calculation requires an explicit button action. Validation and advanced solver
figures are guarded too; navigation and cosmetic reruns do not start them.

Results persist in Streamlit session state. Each stores the exact composition,
temperature, and internal-pressure signature used to produce it. Changed or
invalid current input marks the prior result stale until explicitly recalculated.
Stale results remain visible with a warning, but downloads are unavailable until
the changed inputs have a current calculated result.

Structured statuses such as `LINE_SEARCH_FAILED`, `JACOBIAN_FAILED`,
`NOT_FOUND`, and `BRANCH_LOST` remain failures or information. Only
`CriticalPointStatus.CONVERGED` is a certified critical point. `lambda_min=0`
alone is a spinodal condition, and turning points are continuation geometry.
Neither is labelled a critical point.

Single-phase results do not fabricate liquid or vapor fractions, compositions,
or phase-specific Z factors. A public single-phase root is labelled only as a
single-phase root.

Module 17 data is consumed from its protected artifact through the Module 21
adapter. Validation remains `kij=0` with no fitted binary interaction
parameters. Signed pressure error remains `100*(P_pred-P_exp)/P_exp`.
Retrospective nearest-root diagnostics are separate and explicitly labelled
**not production prediction**.

## Limitations and relationship to v1.0

The frontend inherits all v1.0 applicability limits. Supported property scope
is Methane, Ethane, and Propane with the documented default-zero interaction
assumption. Bounded envelope continuation begins at the entered temperature and
may legitimately return unavailable branches or structured termination.

This extension adds no reservoir depletion, CCE/CVD, separator trains,
pseudocomponents or C7+, EOS tuning, kij fitting, new components, experimental
datasets, arbitrary reservoir-fluid validation, or commercial-PVT readiness.
Scientific source, validation evidence, golden masters, tolerances, and public
APIs remain unchanged.

## Continuous verification

`.github/workflows/quality.yml` reproduces the authoritative gates on a clean
Ubuntu runner with Python 3.12 installed from the locked dependency graph:
`uv lock --check`, Ruff, Ruff formatting, mypy over `src` and `app`,
`compileall`, the application import smoke, the full test suite, and the
localhost Streamlit health smoke. The workflow holds read-only repository
permissions and uses no secret.

## Public release-candidate deployment

The application is published as the **public v1.1 release-candidate
deployment**. It is a candidate offered for review, not an approved release, and
it inherits every applicability limit recorded above.

| | |
| --- | --- |
| Public application | <https://pvt-phase-simulator.streamlit.app/> |
| Deployment | Streamlit Community Cloud |
| Repository | `mahmoudshanaa79-afk/pvt-phase-simulator` |
| Release-candidate branch | `app-v1.1-autonomous` |
| Entrypoint | `streamlit_app.py` |
| Python | 3.12 |
| Secrets | none |

Dependencies are installed by Streamlit Community Cloud from `uv.lock` using
`uv sync`, so the hosted environment resolves from the same locked graph the
gates use. The deployment stores and requires no credential, and no release
automation publishes it: it was created as a deliberate, separately authorized
step and is not wired to the default branch.

Deployment remains outside `.github/workflows/quality.yml`, which verifies only
and holds read-only repository permissions.

One operational limit is worth stating for anyone using the public link. On the
Community Cloud free tier, accumulating several heavy results in a single
session — a flash, a full phase envelope, and a critical-point solve together —
has made the container stop responding and require a reboot. Each calculation
completes correctly on its own, and a fresh container runs any one of them to a
complete render. Reload the page to obtain a fresh session.
