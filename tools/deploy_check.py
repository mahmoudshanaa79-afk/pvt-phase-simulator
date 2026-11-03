"""Run the app script with only the deployed (non-dev) dependencies.

``tools/streamlit_smoke.py`` checks that the server starts and answers its
health endpoint; it does not run the app script. This check runs the script
through Streamlit's own AppTest (part of Streamlit, not a dev dependency): every
page renders, and RUN FLASH on the default case gives a result, with no
exception. Run it with an environment that has only the runtime dependencies:

    UV_PROJECT_ENVIRONMENT=/tmp/openphase-deploy uv sync --no-dev --locked
    /tmp/openphase-deploy/bin/python tools/streamlit_smoke.py --timeout 90
    /tmp/openphase-deploy/bin/python tools/deploy_check.py

It exits non-zero on the first problem and names it.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "src" / "pvt_phase_simulator_ui" / "pages"
PAGE_FILES = (
    "overview.py",
    "phase_envelope.py",
    "critical_point.py",
    "engineering_sweeps.py",
    "validation.py",
    "diagnostics.py",
)
DEV_ONLY = ("pytest", "playwright", "hypothesis", "mypy", "ruff")


def main() -> int:
    logging.disable(logging.CRITICAL)
    present = [name for name in DEV_ONLY if importlib.util.find_spec(name)]
    if present:
        print(f"Not a deployed environment: dev packages present: {present}")
        return 2
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=120).run()
    for page in PAGE_FILES:
        app.switch_page(PAGES / page).run()
        if app.exception:
            print(f"{page}: {[item.value for item in app.exception]}")
            return 1
    app.switch_page(PAGES / "overview.py").run()
    next(item for item in app.button if item.label == "RUN FLASH").click().run()
    if app.exception or "flash" not in app.session_state["results"]:
        print("RUN FLASH did not give a result:", [item.value for item in app.error])
        return 1
    print(
        "Deployed dependencies: every page renders and RUN FLASH gives a result "
        f"(Python {sys.version.split()[0]})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
