"""Narrow CSS: the phase-split bar and a visible keyboard-focus ring."""

from __future__ import annotations

import html

import streamlit as st

#: A clear focus ring for keyboard users (WCAG 2.4.7). Streamlit gives a focused
#: sidebar page link only a faint background tint and a focused number field
#: no ring at all. The colour is the theme's link colour (.streamlit/config.toml).
#: Only focus is styled; nothing else about the theme changes.
FOCUS_STYLE = """
<style>
[data-testid="stSidebarNav"] a:focus-visible {
  outline: 3px solid #075F8C;
  outline-offset: -3px;
  border-radius: 0.4rem;
}
[data-testid="stNumberInputContainer"]:focus-within,
[data-baseweb="input"]:focus-within,
[data-baseweb="select"]:focus-within,
[data-baseweb="textarea"]:focus-within {
  outline: 2px solid #075F8C;
  outline-offset: 1px;
}
</style>
"""


def apply_focus_styles() -> None:
    """Add the keyboard-focus ring to the current page."""

    st.html(FOCUS_STYLE)


def phase_split_bar(vapor_fraction: float, liquid_fraction: float) -> None:
    """Render a labelled engineering phase-split bar from source fractions."""

    vapor = float(vapor_fraction)
    liquid = float(liquid_fraction)
    label = html.escape(f"Liquid {liquid:.6g}; vapor {vapor:.6g}", quote=True)
    st.html(
        f"""
        <style>
        .pvt-phase-split {{display:flex;height:1rem;border:1px solid #9aaabd;
          border-radius:.3rem;overflow:hidden;background:#fff}}
        .pvt-liquid {{width:{liquid * 100:.12g}%;background:#176b87}}
        .pvt-vapor {{width:{vapor * 100:.12g}%;background:#64b7b1}}
        </style>
        <div class="pvt-phase-split" role="img" aria-label="{label}">
          <div class="pvt-liquid"></div><div class="pvt-vapor"></div>
        </div>
        """
    )
