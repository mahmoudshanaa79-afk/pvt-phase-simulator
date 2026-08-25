"""Light scientific-engineering visual system for native Streamlit widgets."""

# ruff: noqa: E501

from __future__ import annotations

import streamlit as st

CSS = """
<style>
:root {
  --pvt-ink: #102a43;
  --pvt-muted: #52677d;
  --pvt-accent: #0f6b72;
  --pvt-accent-dark: #09535a;
  --pvt-border: #d8e1e8;
  --pvt-surface: #ffffff;
  --pvt-canvas: #f6f8fa;
  --pvt-soft: #edf5f5;
}
.stApp { background: var(--pvt-canvas); color: var(--pvt-ink); }
[data-testid="stHeader"] { background: rgba(246, 248, 250, 0.96); }
[data-testid="stSidebar"] { background: var(--pvt-surface); border-right: 1px solid var(--pvt-border); }
[data-testid="stMainBlockContainer"] { max-width: 1280px; padding-top: 1.5rem; padding-bottom: 4rem; }
h1, h2, h3 { color: var(--pvt-ink); letter-spacing: -0.02em; }
p, label, [data-testid="stCaptionContainer"] { color: var(--pvt-muted); }
.pvt-header { border-bottom: 1px solid var(--pvt-border); padding: 0 0 1.2rem; margin-bottom: 1.25rem; }
.pvt-kicker { color: var(--pvt-accent); font-size: .78rem; font-weight: 750; letter-spacing: .12em; text-transform: uppercase; }
.pvt-title { color: var(--pvt-ink); font-size: clamp(1.7rem, 3vw, 2.7rem); font-weight: 760; margin: .25rem 0 .15rem; line-height: 1.08; }
.pvt-subtitle { color: var(--pvt-muted); font-size: 1rem; margin: 0; }
.pvt-status { border: 1px solid var(--pvt-border); border-left: 4px solid var(--pvt-accent); border-radius: 10px; background: var(--pvt-surface); padding: .8rem 1rem; margin: .5rem 0 1rem; }
.pvt-stale { border-left-color: #a76316; background: #fff9ef; }
div[data-testid="stMetric"] { background: var(--pvt-surface); border: 1px solid var(--pvt-border); border-radius: 10px; padding: .8rem 1rem; }
div[data-testid="stMetricValue"] { color: var(--pvt-ink); font-variant-numeric: tabular-nums; }
div[data-testid="stButton"] > button { border-radius: 9px; border: 1px solid var(--pvt-accent); font-weight: 700; }
div[data-testid="stButton"] > button[kind="primary"] { background: var(--pvt-accent); color: #ffffff; }
div[data-testid="stButton"] > button[kind="primary"]:hover { background: var(--pvt-accent-dark); border-color: var(--pvt-accent-dark); }
div[data-testid="stNumberInput"] input { font-variant-numeric: tabular-nums; }
div[data-testid="stExpander"] { background: var(--pvt-surface); border-color: var(--pvt-border); border-radius: 10px; }
@media (max-width: 768px) {
  [data-testid="stMainBlockContainer"] { padding-left: 1rem; padding-right: 1rem; }
  .pvt-title { font-size: 1.8rem; }
}
</style>
"""


def apply_styles() -> None:
    """Install scoped application CSS."""

    st.markdown(CSS, unsafe_allow_html=True)
