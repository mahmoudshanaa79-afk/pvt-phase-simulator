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
