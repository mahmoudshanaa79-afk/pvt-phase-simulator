"""Release-level checks for the local Streamlit application."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _application_sources() -> str:
    paths = [
        ROOT / "streamlit_app.py",
        *(ROOT / "app").rglob("*.py"),
        *(ROOT / "src" / "pvt_phase_simulator_ui").rglob("*.py"),
    ]
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def test_application_uses_no_deprecated_streamlit_apis() -> None:
    source = _application_sources()
    deprecated_patterns = {
        "legacy cache": r"\bst\.cache\s*\(",
        "experimental API": r"\bst\.experimental_[A-Za-z_]+",
        "legacy component API": r"\bst\.components\.v1\b",
        "deprecated width argument": r"\buse_container_width\s*=",
    }
    matches = {
        name: sorted(set(re.findall(pattern, source)))
        for name, pattern in deprecated_patterns.items()
        if re.search(pattern, source)
    }
    assert matches == {}


def test_local_streamlit_startup_and_health_smoke() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "streamlit_smoke.py"), "--timeout", "20"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    combined = completed.stdout + completed.stderr
    assert completed.returncode == 0, combined
    assert "Streamlit health check passed" in combined
