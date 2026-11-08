"""The app's caches change speed only: same bytes, complete keys, bounded size.

Engine results are cached with ``st.cache_resource`` (see
``LARGE_RESULT_CACHE_ENTRIES`` in ``views.py``). These tests show that:

- every cached result is deeply immutable, so sharing one object is safe;
- a cold call, a warm call and a direct uncached engine call give the same
  bytes, and the app's results and JSON/CSV exports are byte-identical with a
  cold and a warm cache;
- changing any one scientific input (composition, temperature, pressure, any
  kij pair, the example case) changes the key, while units only change the
  display;
- every cache is bounded, and the bounds keep memory well inside Streamlit
  Community Cloud's limit.
"""

from __future__ import annotations

import dataclasses
import enum
import pickle
import tracemalloc
from collections.abc import Callable, Iterator
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import streamlit as st
from pydantic import BaseModel
from streamlit.testing.v1 import AppTest

from pvt_phase_simulator_ui import app as ui_app
from pvt_phase_simulator_ui import views
from pvt_phase_simulator_ui.adapters import ScientificInputs, validate_scientific_inputs
from pvt_phase_simulator_ui.state import INPUT_EXAMPLES
from pvt_phase_simulator_ui.sweeps import validate_sweep_request

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "src" / "pvt_phase_simulator_ui" / "pages"

#: A state where every action is quick (the envelope takes seconds, not
#: minutes); the cached functions do not depend on the state for correctness.
FAST = validate_scientific_inputs((50.0, 0.0, 50.0), 250.0, 5.0)

#: Cached function -> the engine name it calls, patched in the cache-key tests.
CACHED: dict[str, tuple[Any, Any, str]] = {
    "flash": (ui_app._cached_flash, ui_app, "calculate_two_phase_flash"),
    "envelope": (views._calculate_envelope, views, "calculate_phase_envelope"),
    "saturation": (
        views._calculate_operating_saturation,
        views,
        "calculate_saturation_pressure",
    ),
    "extended": (views._calculate_extended_envelope, views, "trace_extended_envelope"),
    "critical": (views._calculate_critical, views, "solve_mixture_critical_point"),
    "scan": (views._calculate_scan, views, "scan_mixture_criticality"),
}

#: Memory budget for all engine caches together. Streamlit Community Cloud
#: allows about 1 GB per app, shared with the interpreter and every session.
CACHE_MEMORY_BUDGET_BYTES = 300e6


def _clear_all() -> None:
    st.cache_data.clear()
    st.cache_resource.clear()


@pytest.fixture(autouse=True)
def _isolated_caches() -> Iterator[None]:
    _clear_all()
    yield
    _clear_all()


@cache
def _direct(name: str) -> Any:
    """The uncached engine result for ``FAST`` (the function body itself)."""

    function = CACHED[name][0]
    return function.__wrapped__(FAST)


# --- immutability ---------------------------------------------------------------


def _mutable_parts(value: Any, seen: set[int] | None = None) -> list[str]:
    seen = set() if seen is None else seen
    if id(value) in seen:
        return []
    seen.add(id(value))
    if isinstance(
        value, (str, bytes, int, float, complex, bool, type(None), enum.Enum)
    ):
        return []
    if isinstance(value, np.generic):
        return []
    if isinstance(value, np.ndarray):
        return ["writable ndarray"] if value.flags.writeable else []
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        found = (
            [] if type(value).__dataclass_params__.frozen else [type(value).__name__]
        )
        for field in dataclasses.fields(value):
            found += _mutable_parts(getattr(value, field.name), seen)
        return found
    if isinstance(value, BaseModel):
        found = [] if value.model_config.get("frozen") else [type(value).__name__]
        for field in type(value).model_fields:
            found += _mutable_parts(getattr(value, field), seen)
        return found
    if isinstance(value, (tuple, frozenset)):
        return [part for item in value for part in _mutable_parts(item, seen)]
    return [type(value).__name__]


@pytest.mark.parametrize("name", CACHED)
def test_every_cached_result_is_deeply_immutable(name: str) -> None:
    assert _mutable_parts(_direct(name)) == []


def test_the_sweep_result_is_deeply_immutable() -> None:
    assert _mutable_parts(views.run_sweep(_sweep_request())) == []


# --- byte-identical results ------------------------------------------------------


@pytest.mark.parametrize("name", CACHED)
def test_cold_warm_and_direct_calls_give_the_same_bytes(name: str) -> None:
    function = CACHED[name][0]
    cold = function(FAST)
    warm = function(FAST)
    assert warm is cold
    assert pickle.dumps(cold) == pickle.dumps(_direct(name))


def _sweep_request(start: float = 1.0, points: int = 5) -> Any:
    return validate_sweep_request(
        "pressure",
        FAST.composition_mol_percent,
        fixed_value=FAST.temperature_k,
        start=start,
        end=20.0,
        points=points,
        temperature_unit="K",
        pressure_unit="MPa",
    )


def test_a_cached_sweep_gives_the_same_bytes_and_reports_progress() -> None:
    request = _sweep_request()
    seen: list[tuple[int, int]] = []
    cold = views._calculate_sweep(
        request, lambda done, total: seen.append((done, total))
    )
    assert seen[-1] == (5, 5)
    warm = views._calculate_sweep(request)
    assert warm is cold
    assert pickle.dumps(cold) == pickle.dumps(views.run_sweep(request))


def test_the_sweep_store_is_bounded_and_evicts_the_oldest_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(views, "run_sweep", _Engine())
    bound = views.SWEEP_CACHE_ENTRIES
    requests = [_sweep_request(start=1.0 + index / 10) for index in range(bound + 2)]
    for request in requests:
        views._calculate_sweep(request)
    store = views._sweep_store()
    assert len(store) == bound
    assert store.get(requests[0]) is None
    assert store.get(requests[-1]) is not None


@pytest.mark.parametrize(
    ("page", "button", "result"),
    (
        ("overview.py", "RUN FLASH", "flash"),
        ("critical_point.py", "RUN CRITICAL SOLVER", "critical"),
        ("critical_point.py", "RUN CRITICALITY MAP", "critical_scan"),
        ("engineering_sweeps.py", "RUN SWEEP", "sweep"),
    ),
)
def test_an_action_can_be_repeated_on_its_page(
    page: str, button: str, result: str
) -> None:
    """A cache hit through the real page must work, progress elements included.

    A cached function that updates an element created outside it raises on the
    hit, and the page's safety boundary turned that into a failure message.
    """

    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=600).run()
    app.number_input(key="temperature_value").set_value(FAST.temperature_k)
    next(b for b in app.button if b.label == "RUN FLASH").click().run()
    app.switch_page(PAGES / page).run()
    stored = []
    for _ in range(2):
        next(b for b in app.button if b.label == button).click().run()
        assert not app.exception
        # An engine verdict such as NOT CERTIFIED is a correct error box; only
        # the action's safety-boundary failure message is a defect here.
        assert not [item.value for item in app.error if "unexpectedly" in item.value]
        stored.append(app.session_state["results"][result])
    assert stored[0] is not None
    assert pickle.dumps(stored[1]) == pickle.dumps(stored[0])


def _capture_downloads(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    captured: dict[str, bytes] = {}
    original = st.download_button

    def capture(label: str, *args: Any, **kwargs: Any) -> Any:
        data = kwargs.get("data", args[0] if args else None)
        if isinstance(data, bytes):
            captured[label] = data
        return original(label, *args, **kwargs)

    monkeypatch.setattr(st, "download_button", capture)
    return captured


def _run_app_case(monkeypatch: pytest.MonkeyPatch) -> tuple[dict[str, bytes], bytes]:
    """Flash, envelope and critical point at ``FAST``; the results and exports."""

    downloads = _capture_downloads(monkeypatch)
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=600).run()
    app.number_input(key="temperature_value").set_value(FAST.temperature_k)
    next(b for b in app.button if b.label == "RUN FLASH").click().run()
    app.switch_page(PAGES / "phase_envelope.py").run()
    next(b for b in app.button if b.label == "RUN PHASE ENVELOPE").click().run()
    app.switch_page(PAGES / "critical_point.py").run()
    next(b for b in app.button if b.label == "RUN CRITICAL SOLVER").click().run()
    app.switch_page(PAGES / "overview.py").run()
    assert not app.exception
    results = app.session_state["results"]
    names = ("flash", "envelope", "envelope_extension", "saturation", "critical")
    stored = pickle.dumps(tuple(results[name] for name in names))
    exports = {
        label: data
        for label, data in downloads.items()
        if label in ("Download CSV", "Download JSON")
    }
    assert set(exports) == {"Download CSV", "Download JSON"}
    return exports, stored


def test_the_app_gives_the_same_results_and_exports_cold_and_warm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cold_exports, cold_results = _run_app_case(monkeypatch)
    warm_exports, warm_results = _run_app_case(monkeypatch)  # caches now warm
    assert warm_results == cold_results
    assert warm_exports == cold_exports
    direct = (
        _direct("flash"),
        _direct("envelope"),
        _direct("extended"),
        _direct("saturation"),
        _direct("critical"),
    )
    assert cold_results == pickle.dumps(direct)


# --- cache keys --------------------------------------------------------------------


class _Engine:
    """Stands in for one engine function and counts its calls."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *_args: Any, **_kwargs: Any) -> object:
        self.calls += 1
        return ("result", self.calls)


def _variants() -> dict[str, ScientificInputs]:
    base = validate_scientific_inputs((40.0, 30.0, 30.0), 300.0, 5.0)

    def changed(**kwargs: Any) -> ScientificInputs:
        values = {
            "composition": base.composition_mol_percent,
            "temperature": base.temperature_k,
            "pressure": base.pressure_mpa,
            "kij": base.kij,
        } | kwargs
        return validate_scientific_inputs(
            values["composition"],
            values["temperature"],
            values["pressure"],
            kij=values["kij"],
        )

    return {
        "base": base,
        "composition": changed(composition=(40.0, 30.000001, 29.999999)),
        "temperature": changed(temperature=300.000001),
        "pressure": changed(pressure=5.000001),
        "kij C1-C2": changed(kij=(0.001, 0.0, 0.0)),
        "kij C1-C3": changed(kij=(0.0, 0.001, 0.0)),
        "kij C2-C3": changed(kij=(0.0, 0.0, 0.001)),
    }


@pytest.mark.parametrize("name", CACHED)
def test_changing_any_one_input_changes_the_cache_key(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    function, module, engine_name = CACHED[name]
    engine = _Engine()
    monkeypatch.setattr(module, engine_name, engine)
    variants = _variants()
    base = variants.pop("base")
    for label, changed in variants.items():
        function.clear()
        engine.calls = 0
        before = function(base)
        per_call = engine.calls
        after = function(changed)
        assert engine.calls == 2 * per_call, label  # a new key: the engine ran
        assert after != before, label
        assert function(base) == before  # the base is still cached
        assert function(changed) == after
        assert engine.calls == 2 * per_call, label


def test_each_shipped_example_has_its_own_cache_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _Engine()
    monkeypatch.setattr(views, "calculate_phase_envelope", engine)
    for example in INPUT_EXAMPLES:
        views._calculate_envelope(
            validate_scientific_inputs(
                (example.methane_pct, example.ethane_pct, example.propane_pct),
                example.temperature_k,
                example.pressure_pa,
                pressure_unit="Pa",
            )
        )
    assert engine.calls == len(INPUT_EXAMPLES)


def test_a_sweep_key_includes_every_request_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _Engine()
    monkeypatch.setattr(views, "run_sweep", engine)
    requests = (_sweep_request(), _sweep_request(start=2.0), _sweep_request(points=6))
    for request in requests:
        views._calculate_sweep(request)
    views._calculate_sweep(requests[0])
    assert engine.calls == len(requests)


def test_units_change_the_display_but_not_the_calculation() -> None:
    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=120).run()
    next(b for b in app.button if b.label == "RUN FLASH").click().run()
    result = app.session_state["results"]["flash"]
    kelvin = {metric.label: metric.value for metric in app.metric}["Temperature"]
    app.segmented_control(key="temperature_unit").set_value("°C").run()
    celsius = {metric.label: metric.value for metric in app.metric}["Temperature"]
    assert app.session_state["results"]["flash"] is result
    assert kelvin == "300 K"
    assert celsius == "26.85 °C"


# --- bounded size ------------------------------------------------------------------


def _cache_size(function: Any) -> int:
    cache_ = function._info.get_function_cache(function._function_key)
    return len(cache_._mem_cache)


@pytest.mark.parametrize("name", CACHED)
def test_every_engine_cache_is_bounded(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    function, module, engine_name = CACHED[name]
    bound = function._info.max_entries
    assert isinstance(bound, int) and 1 <= bound <= 16
    monkeypatch.setattr(module, engine_name, _Engine())
    for index in range(bound + 5):
        function(validate_scientific_inputs((50.0, 0.0, 50.0), 250.0 + index, 5.0))
    assert _cache_size(function) <= bound


def _live_bytes(value: Any) -> int:
    data = pickle.dumps(value)
    tracemalloc.start()
    copy = pickle.loads(data)
    size, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    del copy
    return size


def test_the_cache_bounds_keep_memory_inside_the_budget() -> None:
    """The largest results (envelope, saturation pair) bound the total.

    The measured sizes are for ``FAST``; a factor of 3 allows for longer traces
    at other states. The small results add well under a megabyte each.
    """

    envelope = _live_bytes(_direct("envelope"))
    saturation = _live_bytes(_direct("saturation"))
    small = max(
        _live_bytes(_direct(name)) for name in ("flash", "extended", "critical", "scan")
    )
    worst = 3 * (
        views._calculate_envelope._info.max_entries * envelope
        + views._calculate_operating_saturation._info.max_entries * saturation
        + (16 + 3 * 8 + views.SWEEP_CACHE_ENTRIES) * small
    )
    assert worst < CACHE_MEMORY_BUDGET_BYTES, worst


def test_every_cached_function_declares_a_bound() -> None:
    functions: list[Callable[..., Any]] = [entry[0] for entry in CACHED.values()]
    functions += [views._sweep_store, views._model_scope, views._records]
    for function in functions:
        assert function._info.max_entries is not None, function
