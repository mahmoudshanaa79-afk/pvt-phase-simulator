# Module 21 scientific plotting

## Purpose and boundary

Module 21 provides reusable Plotly figures for the existing phase-behavior
engine. It visualizes structured saturation, envelope, pseudo-arclength,
experimental-validation, criticality, and critical-point results. It does not
modify thermodynamics, fit parameters, choose roots, or add a scientific model.

The plotting module is outside `eos/`. Its pure renderers accept precomputed
data or immutable solver results and return `plotly.graph_objects.Figure`.
They never call `show`, open a browser, write a file, access a network, alter a
global template, invoke Streamlit, or launch a thermodynamic solver.

## Figure-returning API

The production module is `pvt_phase_simulator.plotting`. Its main APIs are:

- `plot_phase_envelope` and `phase_envelope_plot_data`
- `plot_phase_compositions` and `plot_binary_xy`
- `plot_pseudo_arclength_trace` and `plot_pseudo_arclength_diagnostic`
- `load_validation_plot_records` and `validation_plot_records`
- `plot_validation_pressure_parity`, `plot_validation_pressure_error`,
  `plot_validation_composition_parity`, and `plot_validation_status`
- `plot_validation_retrospective_diagnostics`
- `criticality_grid_from_scan` and `plot_criticality_map`
- `plot_critical_solver_convergence`, `plot_critical_solver_conditioning`, and
  `plot_critical_solver_path`

Optional titles are accepted. Major figures can retain caller-supplied factual
metadata such as interaction policy, property provenance, or source DOI in
Plotly figure metadata without inventing provenance.

## Phase envelope and critical overlay

The P-T figure keeps bubble and dew branches separate. Bubble points use a
solid line with circles; dew points use a dashed line with diamonds. Identity
therefore remains visible without color. Failed or unavailable plotting points
use isolated open-x markers and never join a converged line.

Natural-continuation `near_critical` and `branch_lost` terminations can be
marked separately. A termination marker records why continuation stopped; it
is not a critical-point certificate.

Only a Module 20 result with `CriticalPointStatus.CONVERGED` receives the star
labelled `Certified critical point`. Hover data include T, P, composition,
`lambda_min`, and C. An uncertified result is not plotted as critical. For the
reviewed 50/50 methane/propane case, the marker is exactly at
`321.5829183194 K` and `8.53444323606381 MPa`, using final rather than initial
solver coordinates.

## Pseudo-arclength figures

The Module 18 P-T visualizer marks pressure and temperature turns with distinct
symbols and explicitly labels them `not critical`. Near-critical,
phase-role-lost, and trivial-state terminations remain distinct.

Separate diagnostic figures expose `dln(P)/ds`, `dln(T)/ds`, accepted
arclength step, and corrector iterations. Derivative figures include a neutral
zero line so a pressure-tangent sign reversal is visible without fabricating a
temperature reversal.

## Composition figures

Adapters retain only source-provided liquid and vapor compositions.
Composition-versus-T/P figures label phase roles directly. Binary data can also
be shown as liquid x versus vapor y with an `x=y` reference. Missing
compositions are rejected rather than inferred.

Mole fractions can be displayed as `fraction` or `mol %`. Mol-percent display
applies a factor of 100 and changes the axis labels; stored data remain intact.

## Experimental validation

One centralized adapter reads the canonical Module 17 result artifact,
DataFrames using that schema, or immutable result objects. The parity plot
contains production-selected predictions only and derives its `y=x` extent
from the plotted range. Both pressure axes use the same unit and equal aspect.

Relative error preserves Module 17's signed definition:

```text
100 * (P_pred - P_exp) / P_exp.
```

Composition parity uses available production-predicted incipient composition.
Status figures preserve exact status, selected dew root class, and failure
classifications including `PR_ROOT_DEMONSTRATED_PRODUCTION_UNREACHED` and
`NO_PR_ROOT_FOUND_IN_DIAGNOSTIC_SCAN`.

Retrospective nearest-root diagnostics depend on post hoc enumeration relative
to experimental pressure. They have a separate plotting function labelled
`not production prediction`; they never enter production parity series.

## Criticality residual map

`plot_criticality_map` accepts a precomputed rectangular `CriticalityGrid` or a
small `CriticalPointScanResult`; it never launches a scan. The adapter performs
only deterministic reshaping.

The signed `lambda_min` grid supplies the `lambda_min=0` contour and the signed
C grid supplies the visually distinct `C=0` contour. Their intersection is the
local two-condition critical candidate. This demonstrates that
`lambda_min=0` alone is a spinodal condition, not a critical certificate.
Non-applicable samples have separate markers. A converged Module 20 result may
be overlaid under the same certification policy as the envelope figure.

## Critical-solver figures

The convergence figure plots scaled residual norm and optionally
`|lambda_min|` and `|C|` against accepted iteration on a logarithmic magnitude
axis. Signed residuals are never misleadingly placed on a log axis. Jacobian
condition numbers have a separate log figure.

The T-P path shows the initial seed, accepted Newton iterates, and certified
final state. Its trace and annotation explicitly call it a nonlinear solver
trajectory, not a thermodynamic phase boundary.

## Pressure and composition units

All source pressures remain in Pa. `convert_pressure` is the single display
path:

```text
Pa:  divisor 1
kPa: divisor 1e3
MPa: divisor 1e6
bar: divisor 1e5
```

The petroleum-facing default is MPa. Unsupported units and nonfinite values
raise `ValueError`. Composition remains mole fraction internally and can be
labelled/displayed either as fraction or mol percent.

## Status, invalid data, and immutability

Status remains in trace identity, hover data, or classification figures.
Converged scientific states never share line semantics with failed points.
Empty required datasets, malformed grids, missing required compositions,
unsupported units, and NaN/Inf inputs raise clear `ValueError` exceptions.
Optional overlays may be omitted intentionally.

Adapters materialize read-only tuples and renderers construct new Plotly
objects. Tests cover lists, tuples, NumPy arrays, dataclasses, and DataFrames.
No caller input is modified.

## Determinism and testing philosophy

There is no random sampling, timestamp, environment title, or global template
mutation. Identical inputs produce identical normalized Plotly JSON.

Module 21 avoids screenshot and pixel goldens. Tests pin scientific structure:
trace names/styles, x/y source fidelity, unit factors, critical coordinates and
hover metadata, dynamic parity line, error sign, failure classes, contour
matrices, log-axis labels, status markers, composition units, immutability,
serialization determinism, and absence of solver calls from pure renderers.

Real regressions consume an audited CH4/C2 envelope, the 40-row Module 17
artifact, a bounded CH4/C3 criticality scan, and the approved Module 20 result.
Expected figure coordinates come from structured source objects rather than
being independently recomputed by the renderer tests.

## Accessibility, limitations, and future layers

Scientific distinctions use dashes, marker symbols, outlines, and explicit
legend labels in addition to a restrained palette. Reference lines are neutral,
default font size is 14, and normal Plotly template inheritance is preserved.

Figures are diagnostics, not proof of a globally complete phase diagram.
Contour quality depends on caller-supplied resolution. The first critical
overlay remains validated only for the reviewed zero-kij CH4/C3 case. No
image-export dependency, automatic HTML output, pixel testing, final UI, or
automatic uncertainty visualization is added.

A future Streamlit or report layer may arrange and export returned figures.
Module 21 contains no Streamlit calls and does not implement a GUI. Reservoir
depletion, separators, and pseudocomponent characterization remain outside
scope.

The safe-defer backlog is unchanged: individual redundant Module 20 root-
continuity sub-checks are not all mutation-pinned, and the pre-existing
near-critical phase-stability false-stability band remains separate work.
