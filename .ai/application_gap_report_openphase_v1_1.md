# OpenPhase v1.1 application gap report

Status date: 2026-08-29
Assessed commit: `1f01975f30b3e9ea9197323fd2f00c8b7da411bc`

## Current application inventory

| Area | Current implementation | v1.1 assessment |
| --- | --- | --- |
| Shell and navigation | Stable root and compatibility entry points; native five-page sidebar navigation; wide layout; engineering theme | Complete |
| Inputs | Methane/ethane/propane mol %, K, MPa; exact boundary conversion; explicit validation; submitted form boundary | Complete, but no first-use examples/presets |
| Overview and flash | Stability-gated production flash, valid single-phase and structured failure semantics, phase split, compositions, Z factors, operating-point context | Complete |
| Saturation/envelope | Explicit bounded bubble/dew trace, branch termination evidence, operating-point interpolation, production Plotly views | Complete |
| Critical point | Explicit production solve, certification gating, criticality map, residual and conditioning evidence | Complete |
| Validation | Protected Module 17 records through existing plotting APIs, compact recorded-error summary, retrospective data kept separate | Complete |
| Diagnostics | Flash/stability, continuation, and critical solver evidence with progressive disclosure | Complete |
| Exports | Deterministic current-case JSON and UTF-8 CSV; exact source floats; explicit availability states; no hidden calculations | Complete after P1 |
| State and failures | Per-session result signatures, stale warnings, explicit calculation actions, bounded caches, structured exceptions | Complete; add release-level interaction coverage |
| Layout and accessibility | Native Streamlit layout, sidebar navigation, responsive-width charts, limited accessible custom phase bar | Complete; first-use presets must remain native and narrow-layout safe |
| Methodology | Architecture, assumptions, limitations, verified scope, exact local run commands | Complete |
| Deployment and automation | Reproducible `uv` lock and Streamlit entry point | Gap: no repository CI workflow or automated live health smoke |

## Required remaining packages

1. `v1_1_first_use_examples`: add a small set of truthful, non-computing input examples and first-use guidance using native Streamlit controls.
2. `v1_1_application_release_qa`: close semantic coverage for two-phase interaction, stale state, export payloads, genuine failure presentation, navigation, and live startup/health behavior.
3. `v1_1_ci_deployment_readiness`: add locked CI gates and exact deployment/run documentation without credentials or automatic production deployment.

## Explicitly not gaps

- No new components, EOS models, thermodynamic algorithms, pressure sweep, ML, chatbot, or research extension is required for v1.1.
- No existing page, scientific calculation, plot, diagnostics surface, or export path should be rebuilt.
- Deployment credentials and a public URL are external human steps, not blockers to a locally verified release candidate.

