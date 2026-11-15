"""Keyboard focus is clearly visible (real browser, Chromium).

Health check 2026-11: a sidebar page link gained only a 15 % background tint on
keyboard focus, and a focused number field showed no border or ring at all.
This drives the real page with the keyboard and checks for a solid focus
outline.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Page, sync_playwright

from pvt_phase_simulator_ui.styles import FOCUS_STYLE
from tools.browser_walk import _browser_executable, streamlit_server

OUTLINE = """(element) => {
    const target = element.closest(
        '[data-testid="stNumberInputContainer"], [data-baseweb="input"]'
    ) || element;
    const style = getComputedStyle(target);
    return [style.outlineStyle, parseFloat(style.outlineWidth)];
}"""


@pytest.fixture(scope="module")
def page(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Page]:
    log = Path(tmp_path_factory.mktemp("focus")) / "streamlit.log"
    with streamlit_server(log) as url, sync_playwright() as playwright:
        options: dict[str, object] = {"headless": True}
        executable = _browser_executable()
        if executable:
            options["executable_path"] = executable
        browser = playwright.chromium.launch(**options)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(120_000)
        page.goto(url, wait_until="domcontentloaded")
        page.get_by_role("heading", name="Overview", exact=True).wait_for()
        try:
            yield page
        finally:
            browser.close()


def _tab_to(page: Page, predicate: str, limit: int = 60) -> None:
    for _ in range(limit):
        page.keyboard.press("Tab")
        script = "() => { const e = document.activeElement; return !!e && (%s); }"
        if page.evaluate(script % predicate):
            return
    pytest.fail(f"no focusable element matched {predicate}")


def test_a_focused_sidebar_page_link_has_a_solid_outline(page: Page) -> None:
    _tab_to(page, "e.closest('[data-testid=\"stSidebarNav\"]') && e.tagName === 'A'")
    style, width = page.evaluate("() => (" + OUTLINE + ")(document.activeElement)")
    assert style == "solid" and width >= 2


def test_a_focused_number_field_has_a_solid_outline(page: Page) -> None:
    _tab_to(page, "e.getAttribute('aria-label') === 'Methane (mol %)'")
    style, width = page.evaluate("() => (" + OUTLINE + ")(document.activeElement)")
    assert style == "solid" and width >= 2


def test_the_focus_style_uses_the_theme_link_colour() -> None:
    config = (
        Path(__file__).resolve().parents[1] / ".streamlit/config.toml"
    ).read_text()
    link = re.search(r'linkColor = "(#[0-9A-Fa-f]{6})"', config)
    assert link is not None
    assert link.group(1) in FOCUS_STYLE
    assert ":focus-visible" in FOCUS_STYLE and ":focus-within" in FOCUS_STYLE
