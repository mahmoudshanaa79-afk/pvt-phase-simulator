"""Deployment health: what Streamlit Community Cloud installs and runs.

The public app installs from ``pyproject.toml`` and ``uv.lock`` (no dev group)
with Python 3.12, and runs ``streamlit_app.py`` with ``.streamlit/config.toml``.
These tests check that those files agree with each other and with the code.
``tools/deploy_check.py`` runs the app with only the deployed dependencies.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

import streamlit.config
from streamlit.testing.v1 import AppTest

from pvt_phase_simulator_ui.adapters import (
    MAXIMUM_PRESSURE_PA,
    MAXIMUM_TEMPERATURE_K,
    MINIMUM_PRESSURE_PA,
    MINIMUM_TEMPERATURE_K,
)
from pvt_phase_simulator_ui.model_scope import load_model_scope
from pvt_phase_simulator_ui.views import short_citation

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
LOCK = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
#: Import name -> distribution name, where they differ.
DISTRIBUTION = {"yaml": "pyyaml", "sklearn": "scikit-learn"}
FIRST_PARTY = {
    "pvt_phase_simulator",
    "pvt_phase_simulator_ui",
    "pvt_phase_simulator_validation",
    "app",
}


def _runtime_dependencies() -> set[str]:
    names = set()
    for requirement in PYPROJECT["project"]["dependencies"]:
        names.add(re.split(r"[<>=!~\[; ]", requirement, maxsplit=1)[0].lower())
    return names


def _third_party_imports(directory: Path) -> set[str]:
    found = set()
    for path in directory.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules = [node.module]
            else:
                continue
            for module in modules:
                top = module.split(".")[0]
                if top not in sys.stdlib_module_names and top not in FIRST_PARTY:
                    found.add(DISTRIBUTION.get(top, top).lower())
    return found


def test_every_import_of_the_app_and_engine_is_a_runtime_dependency() -> None:
    imported = _third_party_imports(ROOT / "src") | _third_party_imports(ROOT / "app")
    missing = imported - _runtime_dependencies()
    assert not missing, f"imported but not in [project].dependencies: {missing}"


def _first_party_imports(directory: Path) -> set[str]:
    found = set()
    for path in directory.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                top = node.module.split(".")[0]
            elif isinstance(node, ast.Import):
                top = node.names[0].name.split(".")[0]
            else:
                continue
            if top in FIRST_PARTY - {"app"}:
                found.add(top)
    return found


def test_the_app_and_engine_import_only_packages_the_build_ships() -> None:
    """A non-editable install (a wheel) contains only the built modules."""

    built = set(PYPROJECT["tool"]["uv"]["build-backend"]["module-name"])
    for package in ("pvt_phase_simulator", "pvt_phase_simulator_ui"):
        assert _first_party_imports(ROOT / "src" / package) <= built, package


def test_the_lock_file_pins_the_project_version_and_every_runtime_dependency() -> None:
    packages = {package["name"]: package for package in LOCK["package"]}
    project = packages[PYPROJECT["project"]["name"]]
    assert project["version"] == PYPROJECT["project"]["version"]
    for name in _runtime_dependencies():
        assert name in packages, name


def test_the_python_version_file_satisfies_requires_python() -> None:
    pinned = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    assert pinned == "3.12"
    assert PYPROJECT["project"]["requires-python"] == ">=3.12"
    workflow = (ROOT / ".github" / "workflows" / "quality.yml").read_text(
        encoding="utf-8"
    )
    assert "uv python install 3.12" in workflow


def test_every_config_option_is_a_streamlit_option() -> None:
    config = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text("utf-8"))
    options = streamlit.config._config_options_template  # noqa: SLF001 - no public list

    def keys(table: dict[str, object], prefix: str = "") -> list[str]:
        found = []
        for key, value in table.items():
            name = f"{prefix}{key}"
            if isinstance(value, dict):
                found += keys(value, f"{name}.")
            else:
                found.append(name)
        return found

    unknown = [key for key in keys(config) if key not in options]
    assert not unknown, unknown


def test_the_entrypoint_is_the_installed_app() -> None:
    entry = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
    assert "from pvt_phase_simulator_ui.app import run_app" in entry
    assert "run_app()" in entry


# The app's own known-limits text.


def test_the_known_limits_name_components_kij_source_and_input_range() -> None:
    scope = load_model_scope(ROOT)
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=60).run()
    text = " ".join(item.value for item in app.markdown)
    assert "**Methane, Ethane, Propane**" in text
    assert "**kij = 0**" in text
    source = short_citation(scope.validation_source.citation)
    assert source == "May et al. (2015)"
    assert f"from one source: {source}, via {scope.validation_source.name}" in text
    assert (
        f"{MINIMUM_TEMPERATURE_K:g}–{MAXIMUM_TEMPERATURE_K:g} K and "
        f"{MINIMUM_PRESSURE_PA:g} Pa–{MAXIMUM_PRESSURE_PA / 1e9:g} GPa"
    ) in text
