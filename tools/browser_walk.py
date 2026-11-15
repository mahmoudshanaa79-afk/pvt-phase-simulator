"""A real-browser walk of every OpenPhase page, every main action run twice.

AppTest runs in-process and has missed real bugs before (a repeated sweep that
failed on its cache hit; a table hidden in a collapsed section). This walk
drives the app in Chromium on localhost:

- every main action twice: flash, phase envelope, critical solver, criticality
  map, sweep, validation figures;
- page switches away and back, checking that results are still shown;
- Learn mode on every page, and every teaching-lab link points to a lab file
  in ``docs/teaching/``;
- the volume-translation table becomes visible when switched on;
- a kij entry is stated on Overview;
- save a case, reload the app, load the case, rerun: the results match;
- every download button: the file is non-empty and parses (CSV, JSON, HTML);
- at 390 px width, no page scrolls sideways;
- no browser page errors, no blocking console errors, and none of the app's
  generic "stopped unexpectedly" messages, raw tracebacks or exception text.

It is a tool, not part of the CI suite (it takes several minutes, mostly the
first phase envelope). Run it from the repository root:

    uv run python tools/browser_walk.py --output walk-evidence

It writes ``report.json`` and screenshots to the output folder and exits 1 if
any check fails. Set ``OPENPHASE_BROWSER_EXECUTABLE`` to use a local Chrome.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path

from playwright.sync_api import Browser, Page, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pvt_phase_simulator_ui import app as ui_app  # noqa: E402
from pvt_phase_simulator_ui import views  # noqa: E402
from pvt_phase_simulator_ui.learn import LAB_BASE_URL, LABS, TOPICS  # noqa: E402

GENERIC_FAILURES = (
    ui_app.PAGE_RENDER_FAILURE,
    ui_app.INPUT_PANEL_FAILURE,
    ui_app.FLASH_ACTION_FAILURE,
    ui_app.CASE_LOAD_FAILURE,
    ui_app.CASE_SAVE_FAILURE,
    views.ENVELOPE_ACTION_FAILURE,
    views.EXTENSION_ACTION_FAILURE,
    views.SATURATION_ACTION_FAILURE,
    views.CRITICAL_ACTION_FAILURE,
    views.CRITICAL_SCAN_ACTION_FAILURE,
    views.SWEEP_ACTION_FAILURE,
)
RAW_MARKERS = (
    "This app has encountered an error",
    "Traceback",
    "stopped unexpectedly",
    "KeyError:",
    "TypeError:",
    "ValueError:",
    "AttributeError:",
)
#: (sidebar link text, page heading, Learn topic key)
PAGES = (
    ("Overview", "Overview", "overview"),
    ("Phase Envelope", "Phase envelope", "phase_envelope"),
    ("Critical Point", "Critical point", "critical_point"),
    ("Engineering Sweeps", "Engineering sweeps", "engineering_sweeps"),
    ("Validation", "Validation", "validation"),
    ("Diagnostics", "Diagnostics", "diagnostics"),
)
LONG = 300_000  # ms; the first phase envelope of a case takes minutes


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""
    seconds: float = 0.0


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks) and not self.page_errors


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@contextmanager
def streamlit_server(log_path: Path) -> Iterator[str]:
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    environment = os.environ | {"STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false"}
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(ROOT / "streamlit_app.py"),
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
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            deadline = time.monotonic() + 90
            while True:
                if process.poll() is not None:
                    raise RuntimeError("Streamlit exited before it became healthy.")
                try:
                    with opener.open(f"{url}/_stcore/health", timeout=1) as answer:
                        if answer.read().strip() == b"ok":
                            break
                except (TimeoutError, urllib.error.URLError):
                    pass
                if time.monotonic() > deadline:
                    raise TimeoutError("Streamlit did not become healthy in 90 s.")
                time.sleep(0.2)
            yield url
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


def _browser_executable() -> str | None:
    for candidate in (
        os.environ.get("OPENPHASE_BROWSER_EXECUTABLE"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    ):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


class Walk:
    def __init__(self, browser: Browser, url: str, output: Path) -> None:
        self.browser = browser
        self.url = url
        self.output = output
        self.report = Report()
        self.page = self._new_page(1440, 1000)

    def _new_page(self, width: int, height: int) -> Page:
        page = self.browser.new_page(
            viewport={"width": width, "height": height}, accept_downloads=True
        )
        page.set_default_timeout(60_000)
        page.on(
            "console",
            lambda message: (
                self.report.console_errors.append(message.text)
                if message.type == "error"
                else None
            ),
        )
        page.on("pageerror", lambda error: self.report.page_errors.append(str(error)))
        return page

    # -- checks ---------------------------------------------------------------

    def check(self, name: str, action: Callable[[], str | None]) -> None:
        start = time.monotonic()
        try:
            detail = action() or ""
            self.assert_clean()
            self.report.checks.append(
                Check(name, True, detail, round(time.monotonic() - start, 1))
            )
            print(f"PASS  {name}  {detail}", flush=True)
        except Exception as error:  # noqa: BLE001 - a walk records every failure
            self.report.checks.append(
                Check(
                    name, False, repr(error)[:500], round(time.monotonic() - start, 1)
                )
            )
            print(f"FAIL  {name}  {error!r}"[:600], flush=True)
            self.screenshot(f"FAIL-{re.sub(r'[^a-z0-9]+', '-', name.lower())}")

    def assert_clean(self, page: Page | None = None) -> None:
        page = page or self.page
        body = page.locator("body").inner_text()
        found = [
            marker for marker in (*RAW_MARKERS, *GENERIC_FAILURES) if marker in body
        ]
        if page.locator('[data-testid="stException"]').count():
            found.append("stException element")
        if str(ROOT) in body:
            found.append("repository path shown")
        if found:
            raise AssertionError(f"unhealthy page text: {found}")

    def screenshot(self, name: str, page: Page | None = None) -> None:
        (page or self.page).screenshot(
            path=str(self.output / f"{name}.png"), full_page=True
        )

    # -- helpers --------------------------------------------------------------

    def open_page(self, link: str, heading: str, page: Page | None = None) -> None:
        page = page or self.page
        page.get_by_role("link").filter(has_text=link).first.click()
        page.get_by_role("heading", name=heading, exact=True).wait_for()

    def click(self, label: str) -> None:
        """Press a button and wait until Streamlit has finished the rerun."""

        self.page.locator("button").filter(has_text=label).first.click()
        self.wait_idle()

    def wait_idle(self, page: Page | None = None) -> None:
        page = page or self.page
        page.wait_for_timeout(500)
        expect(page.get_by_test_id("stStatusWidget")).to_have_count(0, timeout=LONG)

    def download(self, label: str) -> bytes:
        with self.page.expect_download() as info:
            self.page.locator(
                f'[data-testid="stDownloadButton"] button:has-text("{label}")'
            ).first.click()
        path = info.value.path()
        data = Path(path).read_bytes()
        if not data:
            raise AssertionError(f"{label}: empty file")
        return data

    def overview_numbers(self) -> list[str]:
        """The flash metrics and phase-split caption as shown."""

        texts = self.page.locator('[data-testid="stMetric"]').all_inner_texts()
        caption = self.page.get_by_text(
            re.compile(r"^Liquid .* · Vapor ")
        ).all_inner_texts()
        return [" ".join(text.split()) for text in (*texts, *caption)]

    # -- the walk -------------------------------------------------------------

    def run(self) -> Report:
        page = self.page
        self.check("app loads with Overview and Start here", self.load)
        self.check("Learn mode on every page, lab links resolve", self.learn_mode)
        for attempt in (1, 2):
            self.check(f"RUN FLASH ({attempt})", self.flash)
        self.check("volume-translation table visible when on", self.volume_translation)
        for label in ("Download CSV", "Download JSON", "Download report"):
            self.check(
                f"Overview {label} parses",
                lambda label=label: self.overview_download(label),
            )
        self.open_page("Phase Envelope", "Phase envelope")
        for attempt in (1, 2):
            self.check(f"RUN PHASE ENVELOPE ({attempt})", self.envelope)
        self.check("envelope survives a page switch", self.envelope_round_trip)
        self.open_page("Critical Point", "Critical point")
        for attempt in (1, 2):
            self.check(
                f"RUN CRITICAL SOLVER ({attempt})",
                lambda: self.action("RUN CRITICAL SOLVER", "Critical solver complete"),
            )
            self.check(
                f"RUN CRITICALITY MAP ({attempt})",
                lambda: self.action("RUN CRITICALITY MAP", "Criticality map complete"),
            )
        self.open_page("Engineering Sweeps", "Engineering sweeps")
        for attempt in (1, 2):
            self.check(f"RUN SWEEP ({attempt})", self.sweep)
        for label in ("Download CSV", "Download JSON"):
            self.check(
                f"Sweep {label} parses", lambda label=label: self.sweep_download(label)
            )
        self.open_page("Validation", "Validation")
        for attempt in (1, 2):
            self.check(f"GENERATE VALIDATION FIGURES ({attempt})", self.validation)
        self.check("Diagnostics raw envelope download parses", self.diagnostics)
        self.check("Diagnostics shows the code glossary", self.glossary)
        self.check("pages keep their results after a round trip", self.round_trip)
        self.check("kij is stated on Overview", self.kij)
        self.check(
            "save, reload, load, rerun gives the same results", self.save_reload_load
        )
        self.check("a refused case file says how to fix it", self.bad_case_file)
        self.check("an all-zero composition says what to enter", self.zero_composition)
        self.check("no sideways scroll at 390 px on any page", self.phone)
        blocking = [
            text
            for text in self.report.console_errors
            if any(
                token in text for token in ("Uncaught", "ReferenceError", "TypeError")
            )
        ]
        self.report.checks.append(
            Check("no blocking console errors", not blocking, "; ".join(blocking)[:500])
        )
        self.report.checks.append(
            Check(
                "no browser page errors",
                not self.report.page_errors,
                "; ".join(self.report.page_errors)[:500],
            )
        )
        del page
        return self.report

    def load(self) -> str:
        self.page.goto(self.url, wait_until="domcontentloaded", timeout=120_000)
        self.page.get_by_role("heading", name="Overview", exact=True).wait_for(
            timeout=120_000
        )
        expect(self.page.get_by_text("Start here.", exact=False)).to_be_visible()
        self.screenshot("01-start")
        return ""

    def learn_mode(self) -> str:
        self.page.get_by_text("Learn mode", exact=True).click()
        links: set[str] = set()
        for link, heading, topic in PAGES:
            self.open_page(link, heading)
            title = TOPICS[topic].title  # type: ignore[index]
            expect(self.page.get_by_text(f"Learn: {title}", exact=True)).to_be_visible()
            for anchor in self.page.locator(f'a[href^="{LAB_BASE_URL}"]').all():
                links.add(anchor.get_attribute("href") or "")
        expected = {LAB_BASE_URL + name for _, name in LABS}
        if links != expected:
            raise AssertionError(f"lab links {sorted(links)} != {sorted(expected)}")
        missing = [
            name
            for _, name in LABS
            if not (ROOT / "docs" / "teaching" / name).is_file()
        ]
        if missing:
            raise AssertionError(f"lab files missing: {missing}")
        self.page.get_by_text("Learn mode", exact=True).click()
        self.open_page("Overview", "Overview")
        return f"{len(links)} lab links on {len(PAGES)} pages"

    def flash(self) -> str:
        self.click("RUN FLASH")
        self.page.get_by_role(
            "heading", name="Source-provided phase compositions", exact=True
        ).wait_for(timeout=LONG)
        numbers = self.overview_numbers()
        if not numbers:
            raise AssertionError("no flash metrics shown")
        return " | ".join(numbers)[:200]

    def volume_translation(self) -> str:
        table = self.page.get_by_text(
            "Phase volumes with volume translation", exact=True
        )
        expect(table).to_have_count(0)
        self.page.get_by_text("Advanced: volume translation", exact=False).click()
        self.page.get_by_text("Show volume-translated densities", exact=True).click()
        expect(table).to_be_visible()
        self.screenshot("02-volume-translation")
        self.page.get_by_text("Show volume-translated densities", exact=True).click()
        expect(table).to_have_count(0)
        return ""

    @staticmethod
    def _parse(label: str, data: bytes) -> str:
        text = data.decode("utf-8")
        if "CSV" in label:
            rows = list(csv.reader(io.StringIO(text)))
            if len(rows) < 2:
                raise AssertionError(f"{label}: {len(rows)} CSV rows")
            return f"{len(rows)} CSV rows"
        if "JSON" in label:
            document = json.loads(text)
            if not document:
                raise AssertionError(f"{label}: empty JSON")
            return f"JSON with {len(document)} top-level entries"
        if "<html" not in text.lower():
            raise AssertionError(f"{label}: not an HTML document")
        return f"HTML, {len(text)} characters"

    def overview_download(self, label: str) -> str:
        return self._parse(label, self.download(label))

    def envelope(self) -> str:
        self.click("RUN PHASE ENVELOPE")
        self.page.get_by_text("Envelope trace complete", exact=False).first.wait_for(
            timeout=LONG
        )
        self.page.get_by_text("Bubble branch", exact=True).first.wait_for(timeout=LONG)
        self.screenshot("03-envelope")
        return ""

    def envelope_round_trip(self) -> str:
        self.open_page("Overview", "Overview")
        self.open_page("Phase Envelope", "Phase envelope")
        expect(self.page.get_by_text("Bubble branch", exact=True).first).to_be_visible()
        return ""

    def action(self, button: str, done: str) -> str:
        self.click(button)
        self.page.get_by_text(done, exact=False).first.wait_for(timeout=LONG)
        return ""

    def sweep(self) -> str:
        self.click("RUN SWEEP")
        self.page.get_by_role(
            "heading", name="Phase-state results", exact=True
        ).wait_for(timeout=LONG)
        return ""

    def sweep_download(self, label: str) -> str:
        return self._parse(label, self.download(label))

    def validation(self) -> str:
        self.click("GENERATE VALIDATION FIGURES")
        self.page.get_by_role(
            "heading", name="Retrospective nearest-root diagnostics", exact=True
        ).wait_for(timeout=LONG)
        return ""

    def diagnostics(self) -> str:
        self.open_page("Diagnostics", "Diagnostics")
        self.page.get_by_text("Show advanced raw public objects", exact=True).click()
        detail = self._parse(
            "Download raw envelope (JSON)",
            self.download("Download raw envelope (JSON)"),
        )
        self.page.get_by_text("Show advanced raw public objects", exact=True).click()
        return detail

    def round_trip(self) -> str:
        expectations = (
            ("Overview", "Overview", "Source-provided phase compositions"),
            ("Phase Envelope", "Phase envelope", "Bubble branch"),
            ("Engineering Sweeps", "Engineering sweeps", "Phase-state results"),
            ("Validation", "Validation", "Retrospective nearest-root diagnostics"),
        )
        for link, heading, marker in expectations:
            self.open_page(link, heading)
            expect(self.page.get_by_text(marker, exact=True).first).to_be_visible()
        return ""

    def kij(self) -> str:
        self.open_page("Overview", "Overview")
        self.page.get_by_text("Advanced: binary interaction (kij)", exact=True).click()
        field_ = self.page.get_by_role("spinbutton", name="kij C1–C3", exact=False)
        field_.fill("0.002")
        field_.press("Tab")
        self.click("RUN FLASH")
        expect(
            self.page.get_by_text(
                "user-supplied kij: C1–C3 = +0.002", exact=False
            ).first
        ).to_be_visible(timeout=LONG)
        field_.fill("0")
        field_.press("Tab")
        self.click("RUN FLASH")
        expect(self.page.get_by_text("user-supplied kij", exact=False)).to_have_count(
            0, timeout=LONG
        )
        return ""

    def save_reload_load(self) -> str:
        self.flash()
        before = self.overview_numbers()
        self.page.get_by_text("Save or load case", exact=True).click()
        saved = self.download("Save case")
        json.loads(saved)
        self.page.reload(wait_until="domcontentloaded")
        self.page.get_by_role("heading", name="Overview", exact=True).wait_for(
            timeout=120_000
        )
        expect(self.page.get_by_text("Start here.", exact=False)).to_be_visible()
        self.page.get_by_text("Save or load case", exact=True).click()
        self.page.locator('input[type="file"]').set_input_files(
            {
                "name": "openphase-case.json",
                "mimeType": "application/json",
                "buffer": saved,
            }
        )
        self.page.get_by_text("openphase-case.json", exact=True).wait_for()
        self.click("Load case")
        self.page.get_by_text("Case loaded.", exact=False).wait_for()
        after_numbers = self.flash()
        after = self.overview_numbers()
        if before != after:
            raise AssertionError(f"results differ after reload: {before} != {after}")
        return after_numbers[:120]

    def glossary(self) -> str:
        self.open_page("Diagnostics", "Diagnostics")
        expect(
            self.page.get_by_role(
                "heading", name="What the diagnostic codes mean", exact=True
            )
        ).to_be_visible()
        return ""

    def bad_case_file(self) -> str:
        self.open_page("Overview", "Overview")
        self.page.locator('input[type="file"]').set_input_files(
            {"name": "broken.json", "mimeType": "application/json", "buffer": b"nope"}
        )
        self.page.get_by_text("broken.json", exact=True).wait_for()
        self.click("Load case")
        message = self.page.get_by_text("Case load unavailable", exact=False).first
        expect(message).to_be_visible()
        expect(message).to_contain_text(ui_app.CASE_LOAD_HINT)
        return ""

    def zero_composition(self) -> str:
        for label in ("Methane (mol %)", "Propane (mol %)"):
            field_ = self.page.get_by_role("spinbutton", name=label, exact=True)
            field_.fill("0")
            field_.press("Tab")
        self.click("RUN FLASH")
        message = self.page.get_by_text("Submission unavailable", exact=False).first
        expect(message).to_contain_text("Enter a positive mol % for at least one")
        example = self.page.get_by_role("combobox", name="Example case")
        example.click()
        self.page.get_by_text(
            "Default two-phase-oriented case", exact=True
        ).last.click()
        self.wait_idle()
        return ""

    def phone(self) -> str:
        phone = self._new_page(390, 844)
        phone.goto(self.url, wait_until="domcontentloaded", timeout=120_000)
        phone.get_by_role("heading", name="Overview", exact=True).wait_for(
            timeout=120_000
        )
        wide = []
        for link, heading, _ in PAGES:
            if link != "Overview":
                # The sidebar starts closed on a phone; open it only if it is.
                expand = phone.get_by_test_id("stExpandSidebarButton")
                if expand.is_visible():
                    expand.click()
                self.open_page(link, heading, page=phone)
                collapse = phone.get_by_test_id("stSidebarCollapseButton")
                if collapse.is_visible():
                    collapse.click()
            phone.wait_for_timeout(500)
            overflow = phone.evaluate(
                "document.documentElement.scrollWidth - window.innerWidth"
            )
            if overflow > 0:
                wide.append(f"{link}: {overflow}px")
            self.assert_clean(phone)
            self.screenshot(f"09-phone-{link.lower().replace(' ', '-')}", page=phone)
        phone.close()
        if wide:
            raise AssertionError(f"horizontal overflow: {wide}")
        return f"{len(PAGES)} pages checked"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=Path("walk-evidence"))
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    with streamlit_server(output / "streamlit.log") as url, sync_playwright() as play:
        executable = _browser_executable()
        options: dict[str, object] = {"headless": True}
        if executable:
            options["executable_path"] = executable
        browser = play.chromium.launch(**options)
        try:
            report = Walk(browser, url, output).run()
        finally:
            browser.close()
    summary = {
        "passed": report.passed,
        "seconds": round(time.monotonic() - start, 1),
        "checks": [asdict(check) for check in report.checks],
        "page_errors": report.page_errors,
        "console_errors": report.console_errors,
    }
    (output / "report.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    failed = [check.name for check in report.checks if not check.passed]
    print(
        f"\n{len(report.checks) - len(failed)} of {len(report.checks)} checks passed "
        f"in {summary['seconds']} s; report: {output / 'report.json'}"
    )
    if failed:
        print("FAILED: " + "; ".join(failed))
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
