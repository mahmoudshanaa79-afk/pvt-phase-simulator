# Documentation

Start with the [project README](../README.md) for what OpenPhase is and how to
run it.

## Current: read these first

- [Project status, open decisions and session log](PROJECT_STATUS.md)
- [User guide](USER_GUIDE.md)
- [Streamlit application: pages, behaviour, deployment](STREAMLIT_APPLICATION.md)
- [Experimental VLE validation (Module 17)](EXPERIMENTAL_VALIDATION.md)
- [Dew-branch investigation](DEW_INVESTIGATION.md)
- [Engine change proposals P1–P11](ENGINE_CHANGE_PROPOSALS.md)
- [Validation framework](VALIDATION_FRAMEWORK.md)
- [Pure-component saturation check](PURE_COMPONENT_SATURATION.md)
- [Optional volume translation (Péneloux, P11)](VOLUME_TRANSLATION.md)
- [Next components: butanes proposal](NEW_COMPONENTS_PROPOSAL.md) and
  [butanes admission plan](BUTANES_ADMISSION_PLAN.md)
- [CO2 and N2 admission plan (documentation only)](CO2_N2_ADMISSION_PLAN.md)
- [Changelog](../CHANGELOG.md) and [release notes](release_notes/)

### Teaching

- [Lab 1: methane–propane phase behaviour](teaching/LAB_01_METHANE_PROPANE.md)
- [Lab 2: methane–ethane bubble pressures and the P–x–y diagram](teaching/LAB_02_METHANE_ETHANE.md)
- [Lab 3: how composition moves the phase envelope](teaching/LAB_03_COMPOSITION_AND_THE_ENVELOPE.md)
- [Lab 4: what kij does (methane + propane)](teaching/LAB_04_BINARY_INTERACTION.md)
- [Lab 5: liquid density and volume translation](teaching/LAB_05_LIQUID_DENSITY.md)

### Investigations (evidence behind decisions)

- [kij study (P6)](investigations/kij_study.md)
- [Extended-envelope survey](investigations/envelope_survey.md)
- [Validation with and without Newton refinement (P4)](investigations/validation_newton_comparison.md)
- [App performance, before and after P9](investigations/app_performance.md)
- [Usability review](investigations/usability_review.md)
- The CSV and JSON files next to them are the data each study reads.

## Design references (describe the current engine)

- [Scientific equations and where they are implemented](EQUATIONS.md)
- [Module 6: phase stability and fallback](PHASE_STABILITY_DESIGN.md)
- [Module 7: two-phase flash](FLASH_DESIGN.md)
- [Module 8: saturation pressure](SATURATION_PRESSURE_DESIGN.md)
- [Module 9: phase-envelope continuation](PHASE_ENVELOPE_DESIGN.md)
- [Module 13: thermodynamic derivatives](DERIVATIVE_DESIGN.md)
- [Module 14: independent derivative verification](DERIVATIVE_VERIFICATION.md)
- [Module 15: safeguarded Newton saturation](NEWTON_SATURATION_DESIGN.md)
- [Module 16: component-property database](COMPONENT_PROPERTY_DATABASE_DESIGN.md)
- [Module 18: pseudo-arclength continuation](PSEUDO_ARCLENGTH_CONTINUATION.md)
- [Module 19: mixture criticality derivatives](CRITICALITY_DERIVATIVES.md)
- [Module 20: mixture critical-point solver](CRITICAL_POINT_SOLVER.md)
- [Module 21: scientific plotting](SCIENTIFIC_PLOTTING.md)

## Historical (kept as a record; not updated)

- [Project journal, Milestone 0 onwards](PROJECT_JOURNAL.md)
- [Module 16.1: verified property migration](PROPERTY_SOURCE_MIGRATION.md)
  (with its golden-impact table, `PROPERTY_SOURCE_MIGRATION_GOLDEN_IMPACT.csv`)
- [Module 16.2: verified-property golden rebaseline](VERIFIED_PROPERTY_GOLDEN_REBASELINE.md)
- [Automated AI workflow (the earlier orchestrator)](AUTOMATED_AI_WORKFLOW.md)

## Protected records

`validation/` holds the Module 17 validation record and its summary. It is
regenerated only with the owner's approval; `tests/test_validation_claims.py`
checks that numbers quoted in the docs match it.
