"""Real-browser smoke coverage for the primary Streamlit user journeys."""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, Playwright, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "streamlit_app.py"
SHIPPED_EXAMPLES = (
    "Default two-phase-oriented case",
    "Known single-phase case at 300 K and 20 MPa",
    "Audited critical-solver seed",
)
RAW_EXCEPTION_MARKERS = (
    "This app has encountered an error",
    "Traceback:",
    "KeyError:",
    "TypeError:",
    "ValueError:",
)


def _available_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_until_healthy(url: str, process: subprocess.Popen[str]) -> None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + 60.0
    last_error = "server did not answer"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"Streamlit exited before becoming healthy ({process.returncode})."
            )
        try:
            with opener.open(f"{url}/_stcore/health", timeout=1) as response:
                if response.status == 200 and response.read().strip() == b"ok":
                    return
                last_error = f"HTTP {response.status}"
        except (TimeoutError, urllib.error.URLError) as error:
            last_error = str(error)
        time.sleep(0.1)
    raise TimeoutError(f"Streamlit health check timed out: {last_error}")


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


@pytest.fixture(scope="module")
def evidence_directory(tmp_path_factory: pytest.TempPathFactory) -> Path:
    configured = os.environ.get("OPENPHASE_BROWSER_EVIDENCE_DIR")
    if configured:
        directory = Path(configured).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        return directory
    return tmp_path_factory.mktemp("browser-evidence")


@pytest.fixture(scope="module")
def streamlit_url(evidence_directory: Path) -> Iterator[str]:
    port = _available_local_port()
    url = f"http://127.0.0.1:{port}"
    log_path = evidence_directory / "streamlit.log"
    environment = os.environ.copy()
    environment["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(ENTRYPOINT),
                "--server.headless=true",
                "--server.address=127.0.0.1",
                f"--server.port={port}",
                "--server.fileWatcherType=none",
                "--client.showErrorDetails=false",
            ],
            cwd=ROOT,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            _wait_until_healthy(url, process)
            yield url
        finally:
            _stop_process(process)


def _local_browser_executable() -> str | None:
    configured = os.environ.get("OPENPHASE_BROWSER_EXECUTABLE")
    candidates = (
        configured,
        shutil.which("google-chrome"),
        shutil.which("chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("msedge"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    )
    return next(
        (
            str(Path(candidate).resolve())
            for candidate in candidates
            if candidate and Path(candidate).is_file()
        ),
        None,
    )


@pytest.fixture(scope="module")
def browser(playwright: Playwright) -> Iterator[Browser]:
    executable = _local_browser_executable()
    arguments: dict[str, object] = {"headless": True}
    if executable is not None:
        arguments["executable_path"] = executable
    instance = playwright.chromium.launch(**arguments)
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture(scope="module")
def playwright() -> Iterator[Playwright]:
    with sync_playwright() as instance:
        yield instance


def _screenshot(page: Page, directory: Path, name: str) -> None:
    page.screenshot(path=str(directory / f"{name}.png"), full_page=True)


def _assert_healthy_ui(page: Page) -> None:
    body = page.locator("body").inner_text()
    assert page.locator('[data-testid="stException"]').count() == 0
    assert str(ROOT) not in body
    for marker in RAW_EXCEPTION_MARKERS:
        assert marker not in body


def _open_page(page: Page, title: str, heading: str) -> None:
    page.get_by_role("link").filter(has_text=title).click()
    page.get_by_role("heading", name=heading, exact=True).wait_for(timeout=60_000)
    _assert_healthy_ui(page)


def _click_button(page: Page, label: str) -> None:
    page.locator("button").filter(has_text=label).click()


def test_primary_workflows_do_not_crash_in_a_real_browser(
    browser: Browser,
    streamlit_url: str,
    evidence_directory: Path,
) -> None:
    console_errors: list[str] = []
    page_errors: list[str] = []
    failed_requests: list[str] = []
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.set_default_timeout(60_000)
    page.on(
        "console",
        lambda message: (
            console_errors.append(message.text) if message.type == "error" else None
        ),
    )
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on(
        "requestfailed",
        lambda request: failed_requests.append(
            f"{request.method} {request.url}: {request.failure}"
        ),
    )

    page.goto(streamlit_url, wait_until="domcontentloaded", timeout=60_000)
    page.get_by_text("Hydrocarbon Phase Behavior", exact=True).wait_for(timeout=60_000)
    page.get_by_role("heading", name="Overview", exact=True).wait_for(timeout=60_000)
    _assert_healthy_ui(page)
    _screenshot(page, evidence_directory, "00-overview-default")

    example = page.get_by_role("combobox", name="Example case")
    for label in SHIPPED_EXAMPLES:
        example.click()
        page.get_by_text(label, exact=True).last.click()
        page.get_by_text(
            re.compile(r"Composition total: 100(?:\.0+)? mol %.*ready")
        ).wait_for()
        page.wait_for_timeout(750)
        _assert_healthy_ui(page)
    example.click()
    page.get_by_text(SHIPPED_EXAMPLES[0], exact=True).last.click()
    page.wait_for_timeout(1_000)

    page.get_by_text("Save or load case", exact=True).click()
    page.get_by_text("Save case", exact=True).wait_for()
    with page.expect_download() as download_info:
        page.get_by_text("Save case", exact=True).click()
    saved_case = download_info.value.path()
    page.locator('input[type="file"]').set_input_files(
        {
            "name": "openphase-case.json",
            "mimeType": "application/json",
            "buffer": Path(saved_case).read_bytes(),
        }
    )
    page.get_by_text("openphase-case.json", exact=True).wait_for()
    _click_button(page, "Load case")
    page.get_by_text("Case loaded. Inputs restored; no calculation was run.").wait_for()
    _assert_healthy_ui(page)
    _screenshot(page, evidence_directory, "01-save-load")

    _click_button(page, "RUN FLASH")
    page.get_by_role(
        "heading", name="Source-provided phase compositions", exact=True
    ).wait_for(timeout=180_000)
    _assert_healthy_ui(page)
    _screenshot(page, evidence_directory, "02-overview-flash")

    _open_page(page, "Phase Envelope", "Phase envelope")
    _click_button(page, "RUN PHASE ENVELOPE")
    page.get_by_text("Envelope trace complete", exact=False).wait_for(timeout=180_000)
    page.get_by_text("Bubble branch", exact=True).first.wait_for(timeout=60_000)
    _assert_healthy_ui(page)
    _screenshot(page, evidence_directory, "03-phase-envelope")

    _open_page(page, "Critical Point", "Critical point")
    _click_button(page, "RUN CRITICAL SOLVER")
    page.get_by_text("Critical solver complete", exact=False).wait_for(timeout=180_000)
    _assert_healthy_ui(page)
    _click_button(page, "RUN CRITICALITY MAP")
    page.get_by_text("Criticality map complete", exact=False).wait_for(timeout=180_000)
    _assert_healthy_ui(page)
    _screenshot(page, evidence_directory, "04-critical-point-and-map")

    _open_page(page, "Engineering Sweeps", "Engineering sweeps")
    pressure = page.get_by_role("radio", name="Pressure", exact=True)
    temperature = page.get_by_role("radio", name="Temperature", exact=True)
    expect(pressure).to_be_checked()
    assert (
        page.get_by_role(
            "spinbutton", name="Start pressure (MPa)", exact=True
        ).input_value()
        == "1.00"
    )
    assert (
        page.get_by_role(
            "spinbutton", name="End pressure (MPa)", exact=True
        ).input_value()
        == "20.00"
    )
    assert page.get_by_role("spinbutton", name="Points", exact=True).input_value() == (
        "21"
    )
    pressure.click()
    expect(pressure).to_be_checked()
    temperature.click()
    expect(temperature).to_be_checked()
    pressure.click()
    expect(pressure).to_be_checked()
    _click_button(page, "RUN SWEEP")
    page.get_by_role("heading", name="Phase-state results", exact=True).wait_for(
        timeout=180_000
    )
    _assert_healthy_ui(page)
    _screenshot(page, evidence_directory, "05-engineering-sweeps")

    _open_page(page, "Validation", "Validation")
    _click_button(page, "GENERATE VALIDATION FIGURES")
    page.get_by_role(
        "heading", name="Retrospective nearest-root diagnostics", exact=True
    ).wait_for(timeout=180_000)
    _assert_healthy_ui(page)
    _screenshot(page, evidence_directory, "06-validation")

    _open_page(page, "Diagnostics", "Diagnostics")
    page.get_by_role("heading", name="Flash and stability", exact=True).wait_for()
    _assert_healthy_ui(page)
    _screenshot(page, evidence_directory, "07-diagnostics")

    blocking_console_errors = [
        message
        for message in console_errors
        if any(
            token in message
            for token in ("Uncaught", "ReferenceError", "TypeError", "WebSocket")
        )
    ]
    assert not page_errors
    assert not failed_requests
    assert not blocking_console_errors
