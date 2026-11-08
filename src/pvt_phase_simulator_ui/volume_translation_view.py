"""The optional volume-translation display (owner approval C).

Off by default. When the user turns it on, Overview adds one table of phase
molar volumes and densities: the untranslated Peng–Robinson values next to the
Péneloux-translated ones from ``pvt_phase_simulator.eos.volume_translation``.
It never runs or changes a calculation: phase split, compositions, K-values,
saturation pressures, exports and saved cases are the same either way.
"""

from __future__ import annotations

from typing import Final

import pandas as pd  # type: ignore[import-untyped]
import streamlit as st

from pvt_phase_simulator.eos.flash import TwoPhaseFlashResult
from pvt_phase_simulator.eos.volume_translation import (
    eos_molar_volume,
    translated_molar_volume,
)
from pvt_phase_simulator_ui.context import session

VOLUME_TRANSLATION_KEY: Final = "volume_translation_enabled"
VOLUME_TRANSLATION_EXPANDER: Final = "Advanced: volume translation (Péneloux)"
VOLUME_TRANSLATION_LABEL: Final = "Show volume-translated densities"
VOLUME_TRANSLATION_HELP: Final = (
    "Adds Péneloux-shifted molar volumes and densities to Overview. Display "
    "only: it does not change any calculation, export or saved case."
)
VOLUME_TRANSLATION_CAPTION: Final = (
    "Optional Péneloux volume translation: v = v_PR − Σ xᵢ cᵢ, with constant "
    "shifts fitted to the saturated liquid at T_r = 0.7 of reference "
    "equations of state (docs/VOLUME_TRANSLATION.md). It changes only volumes "
    "and densities. There is no mixture-density validation."
)
CM3_PER_M3: Final = 1.0e6


def volume_translation_enabled() -> bool:
    return bool(session().get(VOLUME_TRANSLATION_KEY, False))


def render_volume_translation_option() -> None:
    """The collapsed sidebar switch; off by default."""

    with st.expander(VOLUME_TRANSLATION_EXPANDER, expanded=False):
        st.toggle(
            VOLUME_TRANSLATION_LABEL,
            key=VOLUME_TRANSLATION_KEY,
            help=VOLUME_TRANSLATION_HELP,
        )


def phase_volume_rows(result: TwoPhaseFlashResult) -> list[dict[str, object]]:
    """Untranslated and translated volume and density of each reported phase."""

    components = [item.component for item in result.feed_mixture.components]
    phases: list[tuple[str, float, tuple[float, ...]]] = []
    for name, phase in (("Liquid", result.liquid_phase), ("Vapor", result.vapor_phase)):
        if phase is not None:
            phases.append(
                (name, phase.selected_compressibility_factor, phase.composition)
            )
    if not phases and result.single_phase_root is not None:
        feed = tuple(item.mole_fraction for item in result.feed_mixture.components)
        phases.append(("Single phase", result.single_phase_root, feed))
    rows: list[dict[str, object]] = []
    for name, z_factor, composition in phases:
        untranslated = eos_molar_volume(
            z_factor, result.temperature_k, result.pressure_pa
        )
        translated = translated_molar_volume(
            z_factor,
            result.temperature_k,
            result.pressure_pa,
            components,
            composition,
        )
        rows.append(
            {
                "Phase": name,
                "PR molar volume (cm³/mol)": untranslated * CM3_PER_M3,
                "Translated molar volume (cm³/mol)": translated * CM3_PER_M3,
                "PR density (mol/m³)": 1.0 / untranslated,
                "Translated density (mol/m³)": 1.0 / translated,
            }
        )
    return rows


def render_translated_volumes(result: TwoPhaseFlashResult) -> None:
    """Overview table, only when the option is on and a phase is available."""

    if not volume_translation_enabled():
        return
    rows = phase_volume_rows(result)
    if not rows:
        return
    st.markdown("**Phase volumes with volume translation**")
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption(VOLUME_TRANSLATION_CAPTION)
