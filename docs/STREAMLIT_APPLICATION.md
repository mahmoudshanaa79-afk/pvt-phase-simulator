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
- `src/pvt_phase_simulator_ui/case_files.py` owns the versioned, deterministic
  JSON case-file boundary and restores validated inputs only.
- `src/pvt_phase_simulator_ui/pages/` contains the six page scripts.
- `src/pvt_phase_simulator_ui/adapters.py` validates inputs, converts boundary
  units to K and Pa, and selects public result fields without changing them.
- `src/pvt_phase_simulator_ui/units.py` is the single application-boundary
  implementation for pressure and temperature unit conversion.
- `src/pvt_phase_simulator_ui/state.py` associates each result with a scientific
  input signature.
- `src/pvt_phase_simulator_ui/reports.py` renders printable HTML solely from the
  existing result-export documents and repository-backed model scope. It has no
  scientific API entry point.
- `src/pvt_phase_simulator_ui/sweeps.py` chooses swept abscissae and calls the
  existing verified flash API once per point. It implements no thermodynamics.
- `.streamlit/config.toml` supplies the light engineering theme. Narrow custom
  styling is limited to the phase-split visualization.
- `src/pvt_phase_simulator/plotting.py` remains the source of scientific Plotly
  figures.

No EOS, fugacity, stability, flash, saturation, continuation, or criticality
equation is implemented in the UI package.

## Inputs and views

The default Overview includes an always-visible **Model and limitations** panel.
It names the Peng–Robinson EOS and its default-zero binary-interaction policy,
lists the property-verified components, distinguishes supported calculations
from unsupported commercial-PVT workflows, and states the critical-point and
unavailable-value safeguards. It explicitly says that the application is not a
commercial PVT package or a substitute for engineering review.

The panel does not maintain a second copy of repository facts. Component names,
property verification states, and property citations come from the packaged
component database; the validation state count, systems, and observed domain
come from the protected Module 17 artifact; and the experimental citation comes
from the checked source manifest. The recorded citations and exact artifact path
are available in the panel's **Recorded provenance** expander. Opening the panel
does not run a scientific calculation.

The persistent Fluid inputs form supports the verified v1.0 Methane, Ethane,
and Propane components. Composition is entered in mol %. Temperature can be
entered and displayed in K, °C, or °F; pressure can be entered and displayed in
Pa, MPa, bar, or psi. Changing a unit converts the editable value and preserves
the physical state; it does not run a calculation or make a current scientific
result stale. On submission, the panel shows the composition total and rejects
nonfinite, negative, above-100, zero-total, and materially non-100% composition.
It rejects pressure at or below zero and temperature at or below absolute zero
in every supported unit, and rejects finite field values whose conversion would
fall outside the supported floating-point range. It does not silently normalize
invalid composition.

The native example selector can fill the form with the default
two-phase-oriented case, the known 50/50 methane/propane single-phase case at
300 K and 20 MPa, or the audited 50/50 methane/propane critical-solver seed near
321.5829183194 K and 8.53444323606381 MPa. Examples are stored as documented SI
states and shown in the currently selected field units. Selection changes input
values only; it never submits the form or starts a scientific calculation. Every
populated value remains editable and passes through the same validation and
conversion boundary when the user explicitly submits it.

The sidebar **Save or load case** panel persists a complete reproducible input
case as `openphase-case.json`. A case records the explicit `openphase.case`
schema identifier and schema version `1.0.0`; the named component mol
percentages; canonical temperature in K and pressure in Pa; selected
temperature and pressure presentation units; the active engineering sweep; and
the canonical bounds and point counts for both pressure and temperature sweeps.
JSON output is UTF-8 with sorted object keys and compact separators, so an
unchanged case serializes to the same bytes.

Loading uses only the standard JSON parser. The complete document is checked
before session input state changes: object shape, required and unknown fields,
duplicate keys, schema identifier, exact supported version, component names,
units, scientific inputs, composition total, and both sweep definitions. A
malformed document, invalid schema, unsupported or future version, or invalid
composition produces a specific application error. Invalid composition is
never normalized or repaired. A successful load restores inputs without
running flash, envelope, critical-point, criticality, or sweep calculations;
the user must still explicitly submit or run the desired calculation.

Valid composition is divided by 100 exactly for mole fractions. The selected
temperature and pressure units are converted once to K and Pa at submission.
Only the canonical K/Pa state is passed to the scientific APIs and stored in a
result signature. Public K/Pa result values are converted once at presentation
to the selected units. Unit-only changes therefore redraw existing results
without recomputing or changing their scientific identity. The pressure factors
are 1 Pa/Pa, 1,000,000 Pa/MPa, 100,000 Pa/bar, and 6,894.757293168 Pa/psi;
temperature uses the standard 273.15 and 459.67 offsets.

- **Overview:** entered state, phase and convergence statuses, available phase
  fractions and Z factors, source-provided compositions, envelope location, and
  a downloadable printable engineering case report.
- **Phase Envelope:** independent bubble and dew traces using Module 21,
  status-aware unavailable points, terminations, critical overlay, and phase
  compositions when available.
- **Critical Point:** Module 20 certification evidence and optional Module 19
  maps, including Tc, Pc, lambda_min, C, direction, convergence, and conditioning.
- **Engineering Sweeps:** bounded pressure or temperature sweeps at the other
  submitted variable, with vapor-fraction and Z-factor curves, a phase-state
  table, a progress indicator, and CSV/JSON export in the selected units. Each point is one call into
  the existing verified flash and stability API; nothing is re-derived. A point
  that fails is reported as **FAILED** and breaks the plotted line rather than
  being interpolated across: the abscissa is kept and its value left empty, so
  the curve shows a real gap. A quantity a point never supplied, such as a vapor
  fraction at a single-phase state, breaks the line the same way. Failed
  abscissae are additionally marked on both charts. Displayed values are rounded
  for reading; exports carry full precision. Each exported state includes both
  selected-unit values with explicit unit fields and canonical `temperature_k`
  and `pressure_pa` values. The default is 21 points, bounded to 60.
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
the changed inputs have a current calculated result. Starting an explicit retry
removes the prior result for that calculation. If an unexpected exception stops
the retry before a new result exists, the application keeps a plain-language
failure notice instead of redisplaying the old result or exposing a raw traceback;
technical details remain in server logs. Structured scientific failure results
remain visible with their public status and termination evidence.

Case files are distinct from result exports: they contain reproducible inputs
only and do not serialize cached scientific result objects.

Current-case and sweep JSON exports use schema version 1.1.0. Their metadata
states the engine units (K and Pa) and selected presentation units. CSV headers
use explicit temperature and pressure unit columns and retain canonical
`temperature_k` and `pressure_pa` columns for unambiguous downstream use.

The Overview also offers `openphase-engineering-report.html`, a self-contained
printable report with no added reporting framework or runtime dependency. It is
assembled only from the current non-stale export documents already held in the
session; creating or downloading it never starts or repeats a calculation. The
report identifies the submitted case and generation time, states the application
and report-format versions, and includes the calculation inputs, model and kij
assumption, verified scope, flash and stability outcome, phase fractions,
source-provided compositions, Z factors, available bubble/dew points, a certified
critical point when present, an engineering-sweep summary, statuses, limitations,
and repository-backed validation provenance.

Every missing report quantity is labelled **UNAVAILABLE** or **NOT APPLICABLE**.
Failed flash quantities and uncertified critical values are labelled **FAILED**
and are not displayed as usable results. Envelope tables render values only for
points whose stored status is `converged`; structured branch terminations remain
visible. A sweep report gives the recorded requested, calculated, and failed
counts without filling failed point values. CSV and JSON exports are independent
and retain their existing schemas and serialization.

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
assumption. The bounded UI envelope trace cold-starts 30 K below the entered
temperature and continues both branches through the operating temperature; it
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

## Public deployment

The application is published as the **public v1.2 deployment**. It is the
released application rather than a candidate, and it inherits every
applicability limit recorded above.

| | |
| --- | --- |
| Public application | <https://pvt-phase-simulator-wpykmumyxwefbv3prht7gv.streamlit.app/> |
| Deployment | Streamlit Community Cloud |
| Repository | `mahmoudshanaa79-afk/pvt-phase-simulator` |
| Branch | `master` |
| Entrypoint | `streamlit_app.py` |
| Python | 3.12 |
| Secrets | none |

The v1.1 release candidate was previously served from `app-v1.1-autonomous` at
`pvt-phase-simulator.streamlit.app`. Republishing from `master` for v1.2
recreated the app, which released that original subdomain, so the public URL
changed to the one above.

Dependencies are installed by Streamlit Community Cloud from `uv.lock` using
`uv sync`, so the hosted environment resolves from the same locked graph the
gates use. The deployment stores and requires no credential, and no release
automation publishes it: it was created as a deliberate, separately authorized
step and is not wired to the default branch.

Deployment remains outside `.github/workflows/quality.yml`, which verifies only
and holds read-only repository permissions.

One hosting observation is recorded for completeness. During initial deployment
testing, one hosted session became unresponsive after several computationally
heavy calculations were run sequentially. Two subsequent fresh-session
reliability runs completed successfully without reproducing the failure, and no
host log recorded any memory, resource, or process-termination message. No
application or scientific defect has been identified. The event is therefore
recorded as a non-reproducible hosting observation and will be revisited only
if it recurs with diagnostic log evidence.
