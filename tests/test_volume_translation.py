"""Optional Péneloux volume translation (owner approval C).

- The stored shifts come from the stated T_r = 0.7 fit, recomputed here from
  the engine and the reference file.
- The held-out errors quoted in docs/VOLUME_TRANSLATION.md and the committed
  fit table are recomputed here.
- A constant shift moves ln(phi_i) by the same amount in every phase, so
  K-values, phase split, compositions and saturation pressures are unchanged;
  only volumes change.
- Off by default: no engine module calls it, and the app shows nothing new
  until the user turns it on.
"""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from pvt_phase_simulator.eos import volume_translation as vt
from pvt_phase_simulator.eos.flash import calculate_two_phase_flash
from pvt_phase_simulator.eos.saturation_pressure import (
    SaturationKind,
    calculate_saturation_pressure,
)
from pvt_phase_simulator.fluid_models import ETHANE, METHANE, PROPANE, FluidMixture
from pvt_phase_simulator.fluid_models import MixtureComponent as Item
from pvt_phase_simulator.physical_constants import UNIVERSAL_GAS_CONSTANT
from pvt_phase_simulator_ui import volume_translation_view as view
from tools import fit_volume_translation as fit

ROOT = Path(__file__).resolve().parents[1]
INVESTIGATIONS = ROOT / "docs" / "investigations"
COMPONENTS = (METHANE, ETHANE, PROPANE)


def _rows(name: str) -> list[dict[str, str]]:
    with (INVESTIGATIONS / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _shifts() -> dict[str, float]:
    return {key: item.shift_m3_per_mol for key, item in vt.ANCHORED_SHIFTS.items()}


def test_the_stored_shifts_are_the_anchored_fit() -> None:
    fresh = fit.fit_shifts(_rows("pure_saturation_reference.csv"))
    # The fit goes through the saturation solver; the last bits of a float can
    # differ between machines (docs/investigations/butanes_admission_dry_run.md
    # records such differences), so compare to 1e-9 relative, far below the
    # 1e-3 precision any quoted density carries.
    for key, value in _shifts().items():
        assert fresh[key] == pytest.approx(value, rel=1e-9, abs=0.0)
    assert set(vt.ANCHORED_SHIFTS) == {"methane", "ethane", "propane"}


def test_the_committed_fit_table_regenerates_exactly() -> None:
    rows = fit.held_out_rows(_rows("pure_saturation_comparison.csv"), _shifts())
    committed = _rows("volume_translation_fit.csv")
    assert len(rows) == len(committed) == 75
    for fresh, stored in zip(rows, committed, strict=True):
        assert {key: str(value) for key, value in fresh.items()} == stored


def test_the_design_doc_quotes_the_held_out_errors() -> None:
    doc = " ".join((ROOT / "docs/VOLUME_TRANSLATION.md").read_text("utf-8").split())
    rows = fit.held_out_rows(_rows("pure_saturation_comparison.csv"), _shifts())
    for component_id, entry in fit.summary(rows).items():
        cells = " | ".join(
            f"{entry[key]:.2f} %"
            for key in (
                "liquid_error_before_aard_percent",
                "liquid_error_after_aard_percent",
                "liquid_error_before_max_percent",
                "liquid_error_after_max_percent",
                "vapor_error_before_aard_percent",
                "vapor_error_after_aard_percent",
            )
        )
        shift = vt.ANCHORED_SHIFTS[component_id].shift_m3_per_mol * 1e6
        row = f"| {component_id} | {shift:.3f} | {int(entry['states'])} | {cells} |"
        assert row in doc, row
    assert "no mixture-density validation" in doc.lower()


def test_the_readme_quotes_the_plain_pr_liquid_error() -> None:
    errors = [
        abs(float(row["liquid_density_relative_error"]))
        for row in _rows("pure_saturation_comparison.csv")
        if row["model_status"] == "converged"
    ]
    readme = " ".join((ROOT / "README.md").read_text("utf-8").split())
    quoted = f"off by up to about {round(100 * max(errors))} %"
    assert quoted in readme, quoted


def test_the_mixture_shift_is_the_mole_fraction_average() -> None:
    composition = (0.5, 0.2, 0.3)
    expected = math.fsum(
        x * vt.ANCHORED_SHIFTS[c.name.casefold()].shift_m3_per_mol
        for c, x in zip(COMPONENTS, composition, strict=True)
    )
    assert vt.mixture_volume_shift(COMPONENTS, composition) == expected


def test_bad_inputs_are_refused() -> None:
    with pytest.raises(ValueError, match="aligned"):
        vt.mixture_volume_shift(COMPONENTS, (1.0,))
    with pytest.raises(ValueError, match="no volume shift"):
        vt.mixture_volume_shift(COMPONENTS, (0.5, 0.5, 0.0), shifts={})
    with pytest.raises(ValueError, match="non-negative"):
        vt.mixture_volume_shift(COMPONENTS, (1.2, -0.2, 0.0))
    with pytest.raises(ValueError, match="positive"):
        vt.eos_molar_volume(0.5, 300.0, 0.0)
    huge = {"methane": vt.VolumeShift("methane", 1.0, 0.7, "test")}
    with pytest.raises(ValueError, match="not positive"):
        vt.translated_molar_volume(0.9, 300.0, 1e6, (METHANE,), (1.0,), huge)
    with pytest.raises(ValueError, match="finite"):
        vt.VolumeShift("methane", math.nan, 0.7, "test")


def _flash():  # type: ignore[no-untyped-def]
    mixture = FluidMixture((Item(METHANE, 0.5), Item(PROPANE, 0.5)))
    return mixture, calculate_two_phase_flash(mixture, 280.0, 5.0e6)


def test_k_values_are_unchanged_by_a_constant_shift() -> None:
    mixture, result = _flash()
    assert result.liquid_phase is not None and result.vapor_phase is not None
    components = [item.component for item in mixture.components]
    args = (result.temperature_k, result.pressure_pa, components)
    liquid = vt.translated_log_fugacity_coefficients(
        result.liquid_phase.component_log_fugacity_coefficients, *args
    )
    vapor = vt.translated_log_fugacity_coefficients(
        result.vapor_phase.component_log_fugacity_coefficients, *args
    )
    for index, (l_new, v_new) in enumerate(zip(liquid, vapor, strict=True)):
        l_old = result.liquid_phase.component_log_fugacity_coefficients[index]
        v_old = result.vapor_phase.component_log_fugacity_coefficients[index]
        offset = (
            vt.ANCHORED_SHIFTS[components[index].name.casefold()].shift_m3_per_mol
            * result.pressure_pa
            / (UNIVERSAL_GAS_CONSTANT * result.temperature_k)
        )
        assert l_new - l_old == pytest.approx(-offset, rel=1e-12)
        assert v_new - v_old == pytest.approx(-offset, rel=1e-12)
        # ln K = ln phi_L - ln phi_V: the offsets cancel.
        assert (l_new - v_new) == pytest.approx(l_old - v_old, abs=1e-14)


def test_only_volumes_change() -> None:
    mixture, result = _flash()
    before = calculate_saturation_pressure(mixture, 280.0, SaturationKind.BUBBLE_POINT)
    rows = view.phase_volume_rows(result)
    again = calculate_two_phase_flash(mixture, 280.0, 5.0e6)
    after = calculate_saturation_pressure(mixture, 280.0, SaturationKind.BUBBLE_POINT)
    assert repr(again) == repr(result)  # split, compositions and K-values
    assert after.pressure_pa == before.pressure_pa
    assert [row["Phase"] for row in rows] == ["Liquid", "Vapor"]
    for row, phase in zip(rows, (result.liquid_phase, result.vapor_phase), strict=True):
        assert phase is not None
        shift = vt.mixture_volume_shift(
            [item.component for item in mixture.components], phase.composition
        )
        pr = phase.selected_compressibility_factor * UNIVERSAL_GAS_CONSTANT * 280.0
        pr /= 5.0e6
        assert row["PR molar volume (cm³/mol)"] == pr * 1e6
        assert row["Translated molar volume (cm³/mol)"] == (pr - shift) * 1e6
        assert row["Translated density (mol/m³)"] == 1.0 / (pr - shift)


def test_a_single_phase_result_uses_the_feed() -> None:
    mixture = FluidMixture((Item(METHANE, 0.5), Item(PROPANE, 0.5)))
    result = calculate_two_phase_flash(mixture, 300.0, 20.0e6)
    assert result.liquid_phase is None and result.vapor_phase is None
    rows = view.phase_volume_rows(result)
    assert [row["Phase"] for row in rows] == ["Single phase"]


def test_a_component_without_a_shift_is_reported_not_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shown: list[str] = []
    _, result = _flash()
    monkeypatch.setattr(view, "volume_translation_enabled", lambda: True)
    monkeypatch.setattr(view.st, "info", shown.append)
    monkeypatch.setattr(
        view,
        "translated_molar_volume",
        lambda *args: vt.translated_molar_volume(*args, shifts={}),
    )
    view.render_translated_volumes(result)
    assert shown == [
        "Volume translation is unavailable for this result: no volume shift is "
        "available for Methane."
    ]


def test_no_engine_module_uses_volume_translation() -> None:
    engine = ROOT / "src" / "pvt_phase_simulator"
    users = [
        path.relative_to(ROOT).as_posix()
        for path in engine.rglob("*.py")
        if path.name != "volume_translation.py"
        and re.search(r"volume_translation", path.read_text(encoding="utf-8"))
    ]
    assert users == []


def _app() -> AppTest:
    return AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=300).run()


def _flash_in_app(app: AppTest) -> AppTest:
    return next(b for b in app.button if b.label == "RUN FLASH").click().run()


def _markdown(app: AppTest) -> list[str]:
    return [str(item.value) for item in app.markdown]


def test_the_app_option_is_off_by_default_and_display_only() -> None:
    app = _flash_in_app(_app())
    assert not app.exception
    toggle = app.toggle(key=view.VOLUME_TRANSLATION_KEY)
    assert toggle.value is False
    assert "**Phase volumes with volume translation**" not in _markdown(app)
    stored = repr(app.session_state["results"]["flash"])
    frames = len(app.dataframe)

    app = toggle.set_value(True).run()
    assert not app.exception
    assert "**Phase volumes with volume translation**" in _markdown(app)
    assert view.VOLUME_TRANSLATION_CAPTION in [str(c.value) for c in app.caption]
    assert len(app.dataframe) == frames + 1
    assert repr(app.session_state["results"]["flash"]) == stored
    # Visible when switched on: not inside a collapsed section of the page.
    # (AppTest lists an expander that has an icon under ``status``.)
    collapsed = [*app.main.expander, *app.main.status]
    assert "Technical details" in [section.label for section in collapsed]
    for section in collapsed:
        assert "**Phase volumes with volume translation**" not in [
            str(item.value) for item in section.markdown
        ], section.label

    app = app.toggle(key=view.VOLUME_TRANSLATION_KEY).set_value(False).run()
    assert "**Phase volumes with volume translation**" not in _markdown(app)
    assert repr(app.session_state["results"]["flash"]) == stored
