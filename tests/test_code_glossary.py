"""Every diagnostic code the engine can emit has a plain-language explanation.

The codes are read from the engine's own source (string literals shaped like
``WORD_WORD`` outside enum classes), so a new engine code without a glossary
entry, or a glossary entry for a code the engine no longer has, fails here.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from streamlit.testing.v1 import AppTest

from pvt_phase_simulator_ui import views
from pvt_phase_simulator_ui.solver_codes import (
    CODE_GLOSSARY,
    EXPLANATIONS,
    glossary_rows,
)

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "src" / "pvt_phase_simulator"
CODE = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+")


def engine_codes() -> set[str]:
    codes: set[str] = set()
    for path in ENGINE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        enum_values = {
            id(statement.value)
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef)
            for statement in node.body
            if isinstance(statement, ast.Assign)
        }
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and CODE.fullmatch(node.value)
                and id(node) not in enum_values
            ):
                codes.add(node.value)
    return codes


def test_the_scan_finds_the_known_codes() -> None:
    codes = engine_codes()
    assert {
        "DEFAULTED_BINARY_INTERACTIONS",
        "FLASH_MAXIMUM_ITERATIONS",
        "HIDDEN_SATURATION_ROOT",
        "ENVELOPE_NEAR_CRITICAL_ROOTS",
        "NO_RELIABLE_PHASE_STABILITY_TRIAL",
    } <= codes
    assert len(codes) >= 40


def test_every_engine_code_has_exactly_one_glossary_entry() -> None:
    codes = engine_codes()
    assert sorted(codes - set(CODE_GLOSSARY)) == [], "codes without an explanation"
    assert sorted(set(CODE_GLOSSARY) - codes) == [], "entries for unknown codes"


def test_entries_are_sentences_and_agree_with_the_detailed_explanations() -> None:
    for code, text in CODE_GLOSSARY.items():
        assert text[0].isupper() and text.endswith("."), code
        assert code not in text, code
        assert 30 <= len(text) <= 240, code
    detailed = {codes[0]: text for codes, text in EXPLANATIONS if len(codes) == 1}
    for code, text in detailed.items():
        assert CODE_GLOSSARY[code] == text, code


def test_failure_codes_say_that_no_result_is_reported() -> None:
    for code in CODE_GLOSSARY:
        if code.startswith("FLASH_"):
            assert "no phase split is reported" in CODE_GLOSSARY[code], code
    for code in (
        "SATURATION_BRACKET_NOT_FOUND",
        "SATURATION_SOLVER_FAILURE",
        "SATURATION_SOLVER_NON_CONVERGENCE",
        "SATURATION_FINAL_RECONSTRUCTION",
        "SATURATION_FINAL_GATES",
        "HIDDEN_SATURATION_ROOT",
        "MULTIPLE_SATURATION_ROOTS",
    ):
        assert "no pressure is reported" in CODE_GLOSSARY[code], code


def test_an_unknown_code_is_listed_not_dropped() -> None:
    rows = glossary_rows(["HIDDEN_SATURATION_ROOT", "SOME_FUTURE_CODE"])
    assert [row["Code"] for row in rows] == [
        "HIDDEN_SATURATION_ROOT",
        "SOME_FUTURE_CODE",
    ]
    assert "No plain-language entry" in rows[1]["Meaning"]


def test_the_diagnostics_page_shows_the_glossary_before_any_calculation() -> None:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=60).run()
    app.switch_page(str(ROOT / "src/pvt_phase_simulator_ui/pages/diagnostics.py")).run()
    assert not app.exception
    assert "What the diagnostic codes mean" in [item.value for item in app.subheader]
    assert views.DIAGNOSTIC_GLOSSARY_CAPTION in [item.value for item in app.caption]
    tables = [frame.value for frame in app.dataframe]
    glossary = next(
        table for table in tables if list(table.columns) == ["Code", "Meaning"]
    )
    assert set(glossary["Code"]) == set(CODE_GLOSSARY)


def test_the_flash_diagnostics_table_explains_each_code() -> None:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=120).run()
    next(item for item in app.button if item.label == "RUN FLASH").click().run()
    app.switch_page(str(ROOT / "src/pvt_phase_simulator_ui/pages/diagnostics.py")).run()
    assert not app.exception
    tables = [frame.value for frame in app.dataframe]
    flash = next(table for table in tables if "Message" in table.columns)
    assert "Meaning" in flash.columns
    assert len(flash) > 0
    for code, meaning in zip(flash["Code"], flash["Meaning"], strict=True):
        assert meaning == CODE_GLOSSARY[code]
