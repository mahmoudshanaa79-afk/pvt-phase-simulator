"""Narrow CSS for the one visualization native Streamlit cannot express."""

from __future__ import annotations

import html

import streamlit as st


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
