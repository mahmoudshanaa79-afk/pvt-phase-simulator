# Independent audit: v1_1_first_use_examples

This is a full audit of the work package described below.

## Your role and its limits

You are an INDEPENDENT ADVERSARIAL AUDITOR. You did not write this code and
you are not here to confirm it.

- Do NOT modify, stage, or commit anything. You are read-only.
- Do NOT regenerate any baseline or golden artifact.
- Do NOT start new features or fix what you find — report it.
- Re-derive equations independently where it matters; do not accept a
  formula because a comment or document agrees with the code.
- Do not trust a test merely because it passes. Ask what it would fail on.
- Prefer different numerical machinery from production when building a
  reference.
- Distinguish a genuine defect from a cosmetic preference. Do not inflate.

## Work package under audit
- Name: v1_1_first_use_examples
- Declared risk: LOW
- Objective: Polish first use without rebuilding the application. Add a compact native Streamlit example selector for a small set of truthful cases already within the verified methane/ethane/propane scope: the existing default two-phase-oriented case, the known valid 50/50 methane/propane 300 K and 20 MPa single-phase case, and the existing audited 50/50 methane/propane critical-solver seed near 321.5829183194 K and 8.53444323606381 MPa. Selecting an example may populate input widgets but must never submit the form or run a scientific calculation. Preserve exact user-editable values, explicit validation, stable widget keys, sidebar navigation, native layout, and sentence-case public copy. Add semantic tests proving selection only changes input state and does not populate results, and that custom edits still validate and submit normally. Do not add custom CSS, new components, new calculations, or claims beyond the documented verified scope.

## Scientific invariants claimed to hold
  - Every file under src/pvt_phase_simulator remains byte-unchanged.
  - Examples only assign input values; selection never invokes flash, stability, saturation, envelope, criticality, or critical-point APIs.
  - No scientific classification, equation, tolerance, convergence rule, or production result changes.
  - Example values and labels are truthful and remain within the verified methane/ethane/propane default-zero-kij scope.
  - User-entered values still pass through the existing explicit validation and exact unit-conversion boundary.
  - Protected data, validation artifacts, golden baselines, and pre-existing scientific tests remain byte-unchanged.

## Repository state
- Branch: `app-v1.1-autonomous`
- HEAD: `1f01975f30b3e9ea9197323fd2f00c8b7da411bc`
- Base for this change: `1f01975f30b3e9ea9197323fd2f00c8b7da411bc`

## Protected artifact hashes (recomputed locally)
  - `tests/golden_master/baseline.csv`: unchanged
  - `data/component_properties.csv`: unchanged
  - `docs/validation/module17_vle_validation.csv`: unchanged
  - `docs/validation/module17_vle_validation_summary.json`: unchanged

## Local verification the orchestrator already ran
Passed: **True**
```
        PASS  .venv/Scripts/python.exe -m pytest -q
        PASS  .venv/Scripts/python.exe -m ruff check .
        PASS  .venv/Scripts/python.exe -m ruff format --check .
        PASS  .venv/Scripts/python.exe -m mypy src app
        PASS  .venv/Scripts/python.exe -m compileall -q src app
        PASS  uv lock --check
        PASS  uv run python -c import pvt_phase_simulator_ui; import pvt_phase_simulator_ui.app; import pvt_phase_simulator_ui.views
        PASS  git diff --check
```
Changed files: ['docs/STREAMLIT_APPLICATION.md', 'src/pvt_phase_simulator_ui/app.py', 'src/pvt_phase_simulator_ui/state.py', 'tests/test_app_adapters.py', 'tests/test_app_streamlit.py']

## Builder's own report — treat as an unverified claim
```
Implemented and verified the native example selector, input-only state updates, editable precision, semantic tests, and documentation. Scientific sources and protected artifacts remain unchanged.

Full suite: 1,176 passed. All required quality gates passed; pytest used a writable temporary directory due sandbox permissions.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "pytest: 1176 passed; ruff check: passed; ruff format --check: 168 files formatted; mypy: passed; compileall: passed; uv lock --check: passed; uv import smoke test: passed; git diff --check: passed; protected artifact hashes: matched",
  "files_changed": ["src/pvt_phase_simulator_ui/app.py", "src/pvt_phase_simulator_ui/state.py", "tests/test_app_streamlit.py", "tests/test_app_adapters.py", "docs/STREAMLIT_APPLICATION.md"],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>
```

## Diff stat
```
 .../streamlit_public_release_p1_fixes.json         |  65 ++++++++++--
 .ai/workflow_state.json                            | 117 +++++++++++++++++++--
 docs/STREAMLIT_APPLICATION.md                      |   8 ++
 src/pvt_phase_simulator_ui/app.py                  |  29 +++--
 src/pvt_phase_simulator_ui/state.py                |  63 +++++++++++
 tests/test_app_adapters.py                         |  21 ++++
 tests/test_app_streamlit.py                        |  39 +++++++
 7 files changed, 317 insertions(+), 25 deletions(-)

```

## Full diff
```diff
diff --git a/.ai/work_packages/streamlit_public_release_p1_fixes.json b/.ai/work_packages/streamlit_public_release_p1_fixes.json
index 8dfd732..fe0c549 100644
--- a/.ai/work_packages/streamlit_public_release_p1_fixes.json
+++ b/.ai/work_packages/streamlit_public_release_p1_fixes.json
@@ -65,14 +65,59 @@
     "All pre-existing scientific tests remain present and unchanged; new tests are application tests only."
   ],
   "required_tests": [
-    [".venv/Scripts/python.exe", "-m", "pytest", "-q"],
-    [".venv/Scripts/python.exe", "-m", "ruff", "check", "."],
-    [".venv/Scripts/python.exe", "-m", "ruff", "format", "--check", "."],
-    [".venv/Scripts/python.exe", "-m", "mypy", "src", "app"],
-    [".venv/Scripts/python.exe", "-m", "compileall", "-q", "src", "app"],
-    ["uv", "lock", "--check"],
-    ["uv", "run", "python", "-c", "import pvt_phase_simulator_ui; import pvt_phase_simulator_ui.app; import pvt_phase_simulator_ui.views"],
-    ["git", "diff", "--check"]
+    [
+      ".venv/Scripts/python.exe",
+      "-m",
+      "pytest",
+      "-q"
+    ],
+    [
+      ".venv/Scripts/python.exe",
+      "-m",
+      "ruff",
+      "check",
+      "."
+    ],
+    [
+      ".venv/Scripts/python.exe",
+      "-m",
+      "ruff",
+      "format",
+      "--check",
+      "."
+    ],
+    [
+      ".venv/Scripts/python.exe",
+      "-m",
+      "mypy",
+      "src",
+      "app"
+    ],
+    [
+      ".venv/Scripts/python.exe",
+      "-m",
+      "compileall",
+      "-q",
+      "src",
+      "app"
+    ],
+    [
+      "uv",
+      "lock",
+      "--check"
+    ],
+    [
+      "uv",
+      "run",
+      "python",
+      "-c",
+      "import pvt_phase_simulator_ui; import pvt_phase_simulator_ui.app; import pvt_phase_simulator_ui.views"
+    ],
+    [
+      "git",
+      "diff",
+      "--check"
+    ]
   ],
   "required_quality_gates": [],
   "audit_policy": "IMMEDIATE",
@@ -80,6 +125,6 @@
   "dependencies": [
     "streamlit_ui_stabilization"
   ],
-  "status": "PENDING",
-  "notes": "Narrow public-release P1 correction package. The immediate independent audit is targeted to the two stated findings. No documentation, theme, packaging, scientific, validation, or deployment work is permitted."
+  "status": "COMMITTED",
+  "notes": "Narrow public-release P1 correction package. The immediate independent audit is targeted to the two stated findings. No documentation, theme, packaging, scientific, validation, or deployment work is permitted.\nPENDING_INDEPENDENT_AUDIT at 1f01975f30b3e9ea9197323fd2f00c8b7da411bc."
 }
diff --git a/.ai/workflow_state.json b/.ai/workflow_state.json
index 2a5d24e..faa5be6 100644
--- a/.ai/workflow_state.json
+++ b/.ai/workflow_state.json
@@ -1,14 +1,14 @@
 {
   "project": "pvt-phase-simulator",
   "phase": "post-v1.0-extensions",
-  "workflow_status": "IDLE",
+  "workflow_status": "CLAUDE_RUNNING",
   "last_scientific_commit": "d2a0a74",
   "last_independent_audit_commit": "d2a0a74",
-  "work_packages_since_audit": 0,
-  "current_work_package": null,
-  "current_risk": "MEDIUM",
-  "audit_required": false,
-  "audit_reason": null,
+  "work_packages_since_audit": 1,
+  "current_work_package": "v1_1_first_use_examples",
+  "current_risk": "LOW",
+  "audit_required": true,
+  "audit_reason": "package audit_policy=IMMEDIATE",
   "blocking_findings": [],
   "safe_defer_findings": [
     {
@@ -45,10 +45,23 @@
       "blocks_release": false
     }
   ],
+  "deferred_independent_audits": [
+    {
+      "status": "PENDING_INDEPENDENT_AUDIT",
+      "package": "streamlit_public_release_p1_fixes",
+      "base_commit": "3a2dcb9e92f7b643c678322e9a0d6d73ded59db1",
+      "resulting_commit": "1f01975f30b3e9ea9197323fd2f00c8b7da411bc",
+      "effective_risk": "MEDIUM",
+      "verification_report": ".ai\\verification\\20260829-203045-streamlit_public_release_p1_fixes.json",
+      "provisional_review_report": ".ai\\provisional_reviews\\20260829-203046-streamlit_public_release_p1_fixes-provisional-review.md",
+      "reason": "Claude unavailable; approved only by fresh read-only Codex provisional review."
+    }
+  ],
   "planned_scope": "Original 21-module Hydrocarbon Phase-Behavior & PVT Simulator",
   "planned_scope_complete": true,
   "codex_correction_cycles": 0,
   "claude_reaudit_cycles": 0,
+  "provisional_review_cycles": 0,
   "claude_cost_usd_this_package": 0.0,
   "claude_cost_unknown_runs": 0,
   "last_error": null,
@@ -347,6 +360,96 @@
       "from": "APPROVED",
       "to": "IDLE",
       "reason": "manually stopped"
+    },
+    {
+      "from": "IDLE",
+      "to": "PLANNING",
+      "reason": "planning streamlit_public_release_p1_fixes"
+    },
+    {
+      "from": "PLANNING",
+      "to": "CODEX_RUNNING",
+      "reason": "invoking Codex builder"
+    },
+    {
+      "from": "CODEX_RUNNING",
+      "to": "HUMAN_ACTION_REQUIRED",
+      "reason": "Codex output contract unusable: no <ORCHESTRATOR_RESULT> block found in agent output. Raw report preserved at C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260826-153136-streamlit_public_release_p1_fixes-report.md."
+    },
+    {
+      "from": "HUMAN_ACTION_REQUIRED",
+      "to": "PLANNING",
+      "reason": "planning streamlit_public_release_p1_fixes"
+    },
+    {
+      "from": "PLANNING",
+      "to": "CODEX_RUNNING",
+      "reason": "invoking Codex builder"
+    },
+    {
+      "from": "CODEX_RUNNING",
+      "to": "CODEX_REVIEW",
+      "reason": "Codex returned COMPLETE"
+    },
+    {
+      "from": "CODEX_REVIEW",
+      "to": "LOCAL_VERIFY",
+      "reason": "running local gates"
+    },
+    {
+      "from": "LOCAL_VERIFY",
+      "to": "PROVISIONAL_CODEX_REVIEW",
+      "reason": "invoking fresh Codex provisional reviewer"
+    },
+    {
+      "from": "PROVISIONAL_CODEX_REVIEW",
+      "to": "IDLE",
+      "reason": "package committed with PENDING_INDEPENDENT_AUDIT"
+    },
+    {
+      "from": "IDLE",
+      "to": "PLANNING",
+      "reason": "planning v1_1_first_use_examples"
+    },
+    {
+      "from": "PLANNING",
+      "to": "CODEX_RUNNING",
+      "reason": "invoking Codex builder"
+    },
+    {
+      "from": "CODEX_RUNNING",
+      "to": "HUMAN_ACTION_REQUIRED",
+      "reason": "Codex output contract unusable: no <ORCHESTRATOR_RESULT> block found in agent output. Raw report preserved at C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260829-203854-v1_1_first_use_examples-report.md."
+    },
+    {
+      "from": "HUMAN_ACTION_REQUIRED",
+      "to": "IDLE",
+      "reason": "manually stopped"
+    },
+    {
+      "from": "IDLE",
+      "to": "PLANNING",
+      "reason": "planning v1_1_first_use_examples"
+    },
+    {
+      "from": "PLANNING",
+      "to": "CODEX_RUNNING",
+      "reason": "invoking Codex builder"
+    },
+    {
+      "from": "CODEX_RUNNING",
+      "to": "CODEX_REVIEW",
+      "reason": "Codex returned COMPLETE"
+    },
+    {
+      "from": "CODEX_REVIEW",
+      "to": "LOCAL_VERIFY",
+      "reason": "running local gates"
+    },
+    {
+      "from": "LOCAL_VERIFY",
+      "to": "CLAUDE_RUNNING",
+      "reason": "invoking Claude auditor"
     }
   ]
-}
\ No newline at end of file
+}
diff --git a/docs/STREAMLIT_APPLICATION.md b/docs/STREAMLIT_APPLICATION.md
index d59035f..befc8c8 100644
--- a/docs/STREAMLIT_APPLICATION.md
+++ b/docs/STREAMLIT_APPLICATION.md
@@ -46,6 +46,14 @@ pressure in MPa. On submission, the panel shows the composition total and reject
 nonfinite, negative, above-100, zero-total, and materially non-100% values. It
 does not silently normalize invalid composition.
 
+The native example selector can fill the form with the default
+two-phase-oriented case, the known 50/50 methane/propane single-phase case at
+300 K and 20 MPa, or the audited 50/50 methane/propane critical-solver seed near
+321.5829183194 K and 8.53444323606381 MPa. Selection changes input values only;
+it never submits the form or starts a scientific calculation. Every populated
+value remains editable and passes through the same validation and conversion
+boundary when the user explicitly submits it.
+
 Valid composition is divided by 100 exactly for mole fractions. Valid pressure
 is multiplied by `1e6` exactly before it reaches an SI-pressure API, and public
 Pa results are divided by `1e6` for MPa display.
diff --git a/src/pvt_phase_simulator_ui/app.py b/src/pvt_phase_simulator_ui/app.py
index 0e07fb8..51338bd 100644
--- a/src/pvt_phase_simulator_ui/app.py
+++ b/src/pvt_phase_simulator_ui/app.py
@@ -14,7 +14,12 @@ from pvt_phase_simulator_ui.adapters import (
     validate_scientific_inputs,
 )
 from pvt_phase_simulator_ui.context import session
-from pvt_phase_simulator_ui.state import initialize_session, store_result
+from pvt_phase_simulator_ui.state import (
+    INPUT_EXAMPLES,
+    apply_selected_input_example,
+    initialize_session,
+    store_result,
+)
 
 PAGES_DIRECTORY = Path(__file__).with_name("pages")
 
@@ -34,22 +39,30 @@ def _cached_flash(inputs: ScientificInputs) -> object:
 def _input_form() -> tuple[ScientificInputs | None, bool]:
     with st.sidebar:
         st.subheader("Fluid inputs")
+        st.selectbox(
+            "Example case",
+            options=[example.label for example in INPUT_EXAMPLES],
+            index=None,
+            placeholder="Choose an example",
+            key="input_example",
+            on_change=apply_selected_input_example,
+            args=(session(),),
+        )
+        st.caption("Examples fill the inputs only; they do not run a calculation.")
         st.caption("Verified components · precise mol %, K, and MPa entry")
         with st.form("scientific_inputs", border=True):
             methane = st.number_input(
-                "Methane (mol %)", value=50.0, format="%.10g", key="methane_pct"
-            )
-            ethane = st.number_input(
-                "Ethane (mol %)", value=0.0, format="%.10g", key="ethane_pct"
+                "Methane (mol %)", format="%.15g", key="methane_pct"
             )
+            ethane = st.number_input("Ethane (mol %)", format="%.15g", key="ethane_pct")
             propane = st.number_input(
-                "Propane (mol %)", value=50.0, format="%.10g", key="propane_pct"
+                "Propane (mol %)", format="%.15g", key="propane_pct"
             )
             temperature = st.number_input(
-                "Temperature (K)", value=300.0, format="%.10g", key="temperature_k"
+                "Temperature (K)", format="%.15g", key="temperature_k"
             )
             pressure = st.number_input(
-                "Pressure (MPa)", value=5.0, format="%.10g", key="pressure_mpa"
+                "Pressure (MPa)", format="%.15g", key="pressure_mpa"
             )
             values = (methane, ethane, propane)
             try:
diff --git a/src/pvt_phase_simulator_ui/state.py b/src/pvt_phase_simulator_ui/state.py
index 7957991..307a70c 100644
--- a/src/pvt_phase_simulator_ui/state.py
+++ b/src/pvt_phase_simulator_ui/state.py
@@ -3,6 +3,7 @@
 from __future__ import annotations
 
 from collections.abc import MutableMapping
+from dataclasses import dataclass
 from typing import Any, Final, cast
 
 from pvt_phase_simulator_ui.adapters import ScientificInputs
@@ -10,10 +11,72 @@ from pvt_phase_simulator_ui.adapters import ScientificInputs
 RESULT_KEYS: Final = ("flash", "envelope", "critical", "critical_scan")
 
 
+@dataclass(frozen=True)
+class InputExample:
+    """A documented input-only case for the verified component scope."""
+
+    label: str
+    methane_pct: float
+    ethane_pct: float
+    propane_pct: float
+    temperature_k: float
+    pressure_mpa: float
+
+
+INPUT_EXAMPLES: Final = (
+    InputExample(
+        label="Default two-phase-oriented case",
+        methane_pct=50.0,
+        ethane_pct=0.0,
+        propane_pct=50.0,
+        temperature_k=300.0,
+        pressure_mpa=5.0,
+    ),
+    InputExample(
+        label="Known single-phase case at 300 K and 20 MPa",
+        methane_pct=50.0,
+        ethane_pct=0.0,
+        propane_pct=50.0,
+        temperature_k=300.0,
+        pressure_mpa=20.0,
+    ),
+    InputExample(
+        label="Audited critical-solver seed",
+        methane_pct=50.0,
+        ethane_pct=0.0,
+        propane_pct=50.0,
+        temperature_k=321.5829183194,
+        pressure_mpa=8.53444323606381,
+    ),
+)
+
+_DEFAULT_INPUTS: Final = INPUT_EXAMPLES[0]
+
+
 def initialize_session(state: MutableMapping[str, Any]) -> None:
     state.setdefault("results", {})
     state.setdefault("result_signatures", {})
     state.setdefault("submitted_inputs", None)
+    state.setdefault("input_example", None)
+    state.setdefault("methane_pct", _DEFAULT_INPUTS.methane_pct)
+    state.setdefault("ethane_pct", _DEFAULT_INPUTS.ethane_pct)
+    state.setdefault("propane_pct", _DEFAULT_INPUTS.propane_pct)
+    state.setdefault("temperature_k", _DEFAULT_INPUTS.temperature_k)
+    state.setdefault("pressure_mpa", _DEFAULT_INPUTS.pressure_mpa)
+
+
+def apply_selected_input_example(state: MutableMapping[str, Any]) -> None:
+    """Copy a selected example into input state without submitting any work."""
+
+    selected = state.get("input_example")
+    example = next((item for item in INPUT_EXAMPLES if item.label == selected), None)
+    if example is None:
+        return
+    state["methane_pct"] = example.methane_pct
+    state["ethane_pct"] = example.ethane_pct
+    state["propane_pct"] = example.propane_pct
+    state["temperature_k"] = example.temperature_k
+    state["pressure_mpa"] = example.pressure_mpa
 
 
 def store_result(
diff --git a/tests/test_app_adapters.py b/tests/test_app_adapters.py
index 5af8389..881d57b 100644
--- a/tests/test_app_adapters.py
+++ b/tests/test_app_adapters.py
@@ -47,6 +47,8 @@ from pvt_phase_simulator_ui.exports import (
     export_json_bytes,
 )
 from pvt_phase_simulator_ui.state import (
+    INPUT_EXAMPLES,
+    apply_selected_input_example,
     get_result,
     initialize_session,
     result_is_stale,
@@ -325,6 +327,25 @@ def test_session_state_is_deterministic_and_marks_scientific_changes_stale() ->
     assert result_is_stale(state, "flash", None)
 
 
+def test_selecting_input_example_only_assigns_input_state() -> None:
+    prior_result = object()
+    state: dict[str, object] = {
+        "results": {"flash": prior_result},
+        "submitted_inputs": "prior submission",
+        "input_example": INPUT_EXAMPLES[2].label,
+    }
+
+    apply_selected_input_example(state)
+
+    assert state["results"] == {"flash": prior_result}
+    assert state["submitted_inputs"] == "prior submission"
+    assert state["methane_pct"] == 50.0
+    assert state["ethane_pct"] == 0.0
+    assert state["propane_pct"] == 50.0
+    assert state["temperature_k"] == 321.5829183194
+    assert state["pressure_mpa"] == 8.53444323606381
+
+
 def test_module21_validation_figures_keep_sign_and_retrospective_separation() -> None:
     records = load_module17_records(ROOT)
     parity = plot_validation_pressure_parity(
diff --git a/tests/test_app_streamlit.py b/tests/test_app_streamlit.py
index 5b9137a..8e2f35b 100644
--- a/tests/test_app_streamlit.py
+++ b/tests/test_app_streamlit.py
@@ -44,6 +44,12 @@ def test_clean_shell_compatibility_entrypoint_imports_without_pythonpath() -> No
 def test_streamlit_apptest_starts_and_exposes_explicit_form_boundary() -> None:
     app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
     assert not app.exception
+    assert [selector.label for selector in app.selectbox] == ["Example case"]
+    assert app.selectbox[0].options == [
+        "Default two-phase-oriented case",
+        "Known single-phase case at 300 K and 20 MPa",
+        "Audited critical-solver seed",
+    ]
     assert [field.label for field in app.number_input] == [
         "Methane (mol %)",
         "Ethane (mol %)",
@@ -54,6 +60,39 @@ def test_streamlit_apptest_starts_and_exposes_explicit_form_boundary() -> None:
     assert [button.label for button in app.button] == ["RUN FLASH"]
 
 
+def test_example_selection_populates_inputs_without_populating_results() -> None:
+    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
+
+    app.selectbox[0].select("Audited critical-solver seed").run()
+
+    assert not app.exception
+    assert [field.value for field in app.number_input] == [
+        50.0,
+        0.0,
+        50.0,
+        321.5829183194,
+        8.53444323606381,
+    ]
+    assert app.session_state["submitted_inputs"] is None
+    assert app.session_state["results"] == {}
+
+
+def test_custom_edits_after_example_selection_validate_and_submit_normally() -> None:
+    app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
+    app.selectbox[0].select("Known single-phase case at 300 K and 20 MPa").run()
+    app.number_input[0].set_value(49.0)
+    app.number_input[1].set_value(1.0)
+    app.number_input[3].set_value(301.25)
+    app.button[0].click().run()
+
+    assert not app.exception
+    submitted = app.session_state["submitted_inputs"]
+    assert submitted.composition_mol_percent == (49.0, 1.0, 50.0)
+    assert submitted.temperature_k == 301.25
+    assert submitted.pressure_mpa == 20.0
+    assert "flash" in app.session_state["results"]
+
+
 def test_every_navigation_page_renders_without_hidden_calculation() -> None:
     app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=30).run()
     expected = {

```

## Your task

Attempt to FALSIFY this implementation.

Investigate the repository directly with your read-only tools — do not rely on
the summaries above. Independently reproduce anything numerical that matters.
Look specifically for:

- scientific error: wrong equation, wrong units, wrong sign, wrong branch
- tests that cannot fail, or that were weakened to pass
- silent scope creep, or a protected artifact quietly changed
- failure paths that return a plausible answer instead of an error
- claims in documentation that the code does not support

## Required final output

Write the full human-readable audit first, then end with exactly one
machine-readable block:

<ORCHESTRATOR_RESULT>
{
  "verdict": "APPROVED",
  "findings": [
    {"id": "C-1", "severity": "C", "blocks": true, "summary": "..."}
  ],
  "safe_defer": []
}
</ORCHESTRATOR_RESULT>

`verdict` must be exactly one of APPROVED, CONDITIONAL, NOT_APPROVED.
`severity` must be A (critical), B (major), C (moderate) or D (minor).
`blocks` must be a boolean.

If you cannot complete the audit, return NOT_APPROVED with a finding that
explains why. A missing or malformed block is never read as approval.
