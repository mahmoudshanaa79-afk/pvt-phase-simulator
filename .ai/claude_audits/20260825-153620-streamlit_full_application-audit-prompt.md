# Independent audit: streamlit_full_application

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
- Name: streamlit_full_application
- Declared risk: MEDIUM
- Objective: Build the first optional post-v1.0 application extension: a polished, testable Streamlit frontend for the completed Hydrocarbon Phase-Behavior & PVT Simulator. Create app/streamlit_app.py as the entrypoint and keep supporting modules under app/ only when they improve maintainability (prefer a compact adapters/state/UI structure over a large page framework). Use a light, responsive scientific-engineering design with white/off-white surfaces, dark navy text, restrained teal/blue accents, thin borders, modest rounding, generous spacing, and no flashy gradients, neon, decorative gauges, or unnecessary animation. The header must identify PVT PHASE SIMULATOR and Peng-Robinson EOS - Hydrocarbon Phase Behavior. Provide Overview, Phase Envelope, Critical Point, Validation, and Diagnostics navigation using standard Streamlit constructs.

Provide a persistent Fluid Input panel for the verified v1 components Methane, Ethane, and Propane. Accept composition in mol %, show an exact live total with valid/invalid semantics, reject negative, above-100, zero-total, nonfinite, and materially non-100% input, and do not silently renormalize clearly invalid input. Accept positive finite temperature in K and pressure in MPa, convert mol % to fractions and MPa to internal Pa exactly, and call scientific APIs only after validation and an explicit RUN FLASH action. Preserve results across cosmetic reruns while clearly invalidating or marking results stale after scientific inputs change.

The Overview must answer the entered fluid/conditions, phase, vapor and liquid fractions, pressure, vapor and liquid compressibility factors, and location relative to the phase envelope. Never fabricate unavailable single-phase quantities. Use the existing public flash/result APIs unchanged, show source-provided liquid/vapor compositions only when available, and place advanced statuses, iterations, residuals, K values, phase compositions, and fugacity details in a technical-details expander only when public result fields provide them.

Use src/pvt_phase_simulator/plotting.py Figure-returning APIs rather than rebuilding plotting logic. The Phase Envelope view must retain bubble/dew identity, status-aware unavailable points, certified converged critical overlays, and the distinction between turning points and critical points. The Critical Point view must use existing Module 19/20 results and show Tc, Pc, lambda_min, C, critical direction, convergence, conditioning, and criticality maps only when available; lambda_min=0 alone must never be certified as a critical point. The Validation view must consume existing Module 17 artifacts/adapters and Module 21 parity, error, composition, status, and retrospective figures; retrospective nearest-root diagnostics must remain separately labelled 'not production prediction', and relative error remains 100*(P_pred-P_exp)/P_exp. The Diagnostics view must expose stable public status, termination, iteration, residual, Jacobian, continuation, and root information with explanatory labels, without reaching into private implementation objects.

The scientific engine and its evidence are protected: do not modify src/pvt_phase_simulator/** (including plotting.py), data/**, docs/validation/**, tests/golden_master/**, or any pre-existing scientific test enumerated in protected_files. Only the application surface enumerated in allowed_files may change. Any actual change to a configured high-risk scientific path automatically escalates effective risk to HIGH and requires an immediate independent audit; a protected-path change also fails local scope verification.

Do not implement Peng-Robinson, fugacity, Rachford-Rice, TPD, saturation, envelope, criticality, or continuation equations in app code. Do not change scientific APIs or tune calculations to reference values. Structured failures such as LINE_SEARCH_FAILED, JACOBIAN_FAILED, NOT_FOUND, BRANCH_LOST, and non-applicable results must remain failures/information rather than plausible success. Preserve the approved 50/50 methane/propane zero-kij critical regression exactly through production result objects: 321.5829183194 K and 8,534,443.23606381 Pa, displayed as 8.53444323606381 MPa.

Add semantic application tests in new tests/test_app*.py files without browser or screenshot dependence. Cover imports, input validation, unit conversion, prevention of invalid scientific calls, correct valid flash invocation, scientifically unchanged result adaptation, phase/fraction/composition/Z identity, structured failures, critical certification, Module 21 figure use, retrospective separation, pressure-error sign, turning-point labelling, absence of thermodynamic equations in app code, protected-file integrity, and deterministic adapter/session behavior. Create docs/STREAMLIT_APPLICATION.md with purpose, architecture, launch command, supported inputs/pages, API separation, state and failure handling, limitations, and relationship to the v1.0 scientific engine; add only a truthful README launch/capability update. Do not claim or implement reservoir depletion, CCE/CVD, separator trains, pseudocomponents/C7+, EOS tuning, kij fitting, new components, new experimental datasets, arbitrary reservoir-fluid validation, or commercial-PVT readiness.

## Scientific invariants claimed to hold
  - Modules 1-21 and every file under src/pvt_phase_simulator remain unchanged; the application calls existing public scientific APIs and Module 21 Plotly APIs.
  - No Peng-Robinson, fugacity, Rachford-Rice, TPD, saturation, phase-envelope, pseudo-arclength, Gibbs-curvature, or critical-point equations are duplicated in app code.
  - Internal pressure remains SI Pa; UI conversion is exactly MPa * 1e6 on input and Pa / 1e6 on display.
  - Composition input is mol %, converted exactly to mole fractions only after finite, nonnegative, positive-total, production-compatible 100% validation; clearly invalid input is not silently normalized.
  - Invalid UI input cannot invoke a production scientific API, and expensive calculations occur only on explicit user action.
  - Production result objects remain the scientific source of truth; adapters do not alter phase, vapor/liquid fractions, x/y compositions, Z factors, statuses, residuals, or iteration data.
  - Unavailable phase quantities are displayed as unavailable and are never fabricated for single-phase or failed states.
  - Bubble and dew identities are preserved; failed/unavailable envelope points are not rendered as converged states; pressure or temperature turning points are never labelled critical points.
  - Only CriticalPointStatus.CONVERGED results may be presented as certified critical points; lambda_min=0 alone and spinodal states are not critical certification.
  - The approved zero-kij 50/50 methane/propane result remains 321.5829183194 K and 8,534,443.23606381 Pa, displayed as 8.53444323606381 MPa, when supplied by the production result.
  - Module 17 production predictions remain separate from retrospective nearest-root diagnostics, which retain explicit 'not production prediction' semantics.
  - Module 17 relative pressure error remains 100*(P_pred-P_exp)/P_exp and reported validation remains kij=0 with no fitted binary interaction parameters.
  - Expected scientific failures remain structured failures/information and are never converted into plausible success or valid-looking critical metrics.
  - Session state preserves deliberate calculation results across cosmetic reruns while stale results are invalidated or clearly identified after scientific inputs change.
  - The existing 1137 scientific tests are retained and continue to pass; no historical test, tolerance, baseline, or expected scientific value is deleted or weakened.
  - Golden, property, and Module 17 protected artifacts remain byte-identical and are never regenerated.
  - Supported verified frontend property scope remains methane, ethane, and propane; no arbitrary reservoir-fluid or commercial-PVT claim is introduced.
  - No reservoir depletion, CCE/CVD, separator, pseudocomponent/C7+, EOS tuning, kij fitting, component expansion, or experimental-data extension is implemented.

## Repository state
- Branch: `master`
- HEAD: `673244e96d7bf53aee8e692bfcc4cd027db6f237`
- Base for this change: `89fdcbe464b6dec814a1f315959cb9160ecfc57d`

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
        PASS  .venv/Scripts/python.exe -m mypy src
        PASS  .venv/Scripts/python.exe -m compileall -q src
```
Changed files: ['README.md', 'app/__init__.py', 'app/adapters.py', 'app/state.py', 'app/streamlit_app.py', 'app/styles.py', 'docs/STREAMLIT_APPLICATION.md', 'tests/test_app_adapters.py']

## Builder's own report — treat as an unverified claim
```
(audit invoked directly; no builder report)
```

## Diff stat
```
 ...33237-final_release_doc_cleanup-audit-prompt.md | 215 ++++++++
 ...60824-233237-final_release_doc_cleanup-audit.md |  30 ++
 ...final_release_doc_cleanup-audit.transcript.json |  30 ++
 ...nal_release_doc_cleanup-report.last-message.txt |  15 +
 ...0824-230618-final_release_doc_cleanup-report.md |  15 +
 ...inal_release_doc_cleanup-report.transcript.json |  28 +
 .../20260824-233236-final_release_doc_cleanup.json |  62 +++
 ...60824-230618-final_release_doc_cleanup-order.md |  70 +++
 .ai/work_packages/final_release_doc_cleanup.json   |   4 +-
 .ai/workflow_state.json                            | 142 +++++-
 README.md                                          |  26 +-
 app/streamlit_app.py                               | 566 ++++++++++++++++++++-
 docs/PROJECT_JOURNAL.md                            |   6 +
 tools/orchestration/agents.py                      |  28 +-
 tools/orchestration/gitops.py                      |   9 +
 tools/orchestration/prompts.py                     |   6 +-
 tools/orchestration/verify.py                      |   2 +
 tools/tests/test_orchestrator.py                   |  76 +++
 18 files changed, 1293 insertions(+), 37 deletions(-)

```

## Full diff
```diff
diff --git a/.ai/claude_audits/20260824-233237-final_release_doc_cleanup-audit-prompt.md b/.ai/claude_audits/20260824-233237-final_release_doc_cleanup-audit-prompt.md
new file mode 100644
index 0000000..19727ba
--- /dev/null
+++ b/.ai/claude_audits/20260824-233237-final_release_doc_cleanup-audit-prompt.md
@@ -0,0 +1,215 @@
+# Independent audit: final_release_doc_cleanup
+
+This is a full audit of the work package described below.
+
+## Your role and its limits
+
+You are an INDEPENDENT ADVERSARIAL AUDITOR. You did not write this code and
+you are not here to confirm it.
+
+- Do NOT modify, stage, or commit anything. You are read-only.
+- Do NOT regenerate any baseline or golden artifact.
+- Do NOT start new features or fix what you find — report it.
+- Re-derive equations independently where it matters; do not accept a
+  formula because a comment or document agrees with the code.
+- Do not trust a test merely because it passes. Ask what it would fail on.
+- Prefer different numerical machinery from production when building a
+  reference.
+- Distinguish a genuine defect from a cosmetic preference. Do not inflate.
+
+## Work package under audit
+- Name: final_release_doc_cleanup
+- Declared risk: LOW
+- Objective: Close the two non-blocking documentation findings from the final whole-project audit. Documentation only: change no code, test, tolerance, baseline, or data.
+
+FINAL-D-1 (README.md): the near-critical phase-stability weakness is currently disclosed only in general terms ('no exhaustive/global phase-stability certification'). Add one or two sentences naming the specific mechanism - trivial-solution collapse in the stability trials near a mixture critical point - so a reader knows the failure is localized and predictable rather than merely theoretical. Cite the independent final audit's OBSERVED example: an approximately 7.86 K false-stable band below the audited 50/50 methane/propane critical temperature at P = Pc. You MUST present this as an observed regression example for that one audited mixture, NOT as a universal width. Do not imply the band width generalizes to other fluids, compositions, or pressures. State that near-critical stability classifications require caution. Do NOT modify phase_stability.py or any other source file.
+
+FINAL-D-2 (docs/PROJECT_JOURNAL.md): the Module 21 section still states the module 'remains unstaged and uncommitted pending independent scientific-visualization review'. APPEND a short closing entry recording that Module 21 was committed at 36d9584, was included in the final whole-repository independent audit, and is accepted as part of the completed original 21-module roadmap. Do NOT rewrite, delete, or edit the historical 'pending review' wording - the journal is chronological and its history must remain intact.
+
+## Scientific invariants claimed to hold
+  - No source file changes: src/ is untouched.
+  - No test, tolerance, or baseline changes.
+  - Golden master, property CSV, and Module 17 artifacts remain byte-identical.
+  - Full scientific suite still reports 1137 passed.
+  - FINAL-D-1 wording must not present the 7.86 K band as universal across fluids.
+  - FINAL-D-2 must append to the journal without rewriting the historical entry.
+  - No claim is added that the repository does not implement.
+
+## Repository state
+- Branch: `master`
+- HEAD: `89fdcbe464b6dec814a1f315959cb9160ecfc57d`
+- Base for this change: `89fdcbe464b6dec814a1f315959cb9160ecfc57d`
+
+## Protected artifact hashes (recomputed locally)
+  - `tests/golden_master/baseline.csv`: unchanged
+  - `data/component_properties.csv`: unchanged
+  - `docs/validation/module17_vle_validation.csv`: unchanged
+  - `docs/validation/module17_vle_validation_summary.json`: unchanged
+
+## Local verification the orchestrator already ran
+Passed: **True**
+```
+        PASS  .venv/Scripts/python.exe -m pytest -q
+        PASS  .venv/Scripts/python.exe -m ruff check .
+        PASS  .venv/Scripts/python.exe -m ruff format --check .
+```
+Changed files: ['README.md', 'docs/PROJECT_JOURNAL.md']
+
+## Builder's own report — treat as an unverified claim
+```
+Updated only the requested documentation:
+
+- README documents the localized near-critical trivial-solution collapse and mixture-specific observed 7.86 K example.
+- Project journal records Module 21’s commit, final audit inclusion, and acceptance.
+- Protected artifact hashes remain byte-identical.
+- Existing `.ai` changes were untouched.
+
+<ORCHESTRATOR_RESULT>
+{
+  "status": "COMPLETE",
+  "tests_claimed": "pytest -q: 1137 passed in 436.44s; ruff check .: All checks passed; ruff format --check .: 109 files already formatted",
+  "files_changed": ["README.md", "docs/PROJECT_JOURNAL.md"],
+  "ready_for_local_verification": true
+}
+</ORCHESTRATOR_RESULT>
+```
+
+## Diff stat
+```
+ .ai/workflow_state.json | 31 ++++++++++++++++++++++++++++---
+ README.md               |  8 ++++++++
+ docs/PROJECT_JOURNAL.md |  6 ++++++
+ 3 files changed, 42 insertions(+), 3 deletions(-)
+
+```
+
+## Full diff
+```diff
+diff --git a/.ai/workflow_state.json b/.ai/workflow_state.json
+index dd2510a..fdff109 100644
+--- a/.ai/workflow_state.json
++++ b/.ai/workflow_state.json
+@@ -1,14 +1,14 @@
+ {
+   "project": "pvt-phase-simulator",
+   "phase": "post-roadmap",
+-  "workflow_status": "IDLE",
++  "workflow_status": "CLAUDE_RUNNING",
+   "last_scientific_commit": "36d9584baf8ff77e1e79ad5f9ad91d0eb9fd4439",
+   "last_independent_audit_commit": "f71ef10",
+   "work_packages_since_audit": 0,
+   "current_work_package": "final_release_doc_cleanup",
+   "current_risk": "LOW",
+-  "audit_required": false,
+-  "audit_reason": null,
++  "audit_required": true,
++  "audit_reason": "package audit_policy=IMMEDIATE",
+   "blocking_findings": [],
+   "safe_defer_findings": [
+     {
+@@ -90,6 +90,31 @@
+       "from": "LOCAL_VERIFY",
+       "to": "IDLE",
+       "reason": "manually stopped"
++    },
++    {
++      "from": "IDLE",
++      "to": "PLANNING",
++      "reason": "planning final_release_doc_cleanup"
++    },
++    {
++      "from": "PLANNING",
++      "to": "CODEX_RUNNING",
++      "reason": "invoking Codex builder"
++    },
++    {
++      "from": "CODEX_RUNNING",
++      "to": "CODEX_REVIEW",
++      "reason": "Codex returned COMPLETE"
++    },
++    {
++      "from": "CODEX_REVIEW",
++      "to": "LOCAL_VERIFY",
++      "reason": "running local gates"
++    },
++    {
++      "from": "LOCAL_VERIFY",
++      "to": "CLAUDE_RUNNING",
++      "reason": "invoking Claude auditor"
+     }
+   ]
+ }
+diff --git a/README.md b/README.md
+index 818f1bf..662b549 100644
+--- a/README.md
++++ b/README.md
+@@ -234,6 +234,14 @@ The project does **not** yet implement:
+ - engineering unit conversion functions
+ - a Streamlit user interface
+ 
++Near a mixture critical point, the bounded stability trials can collapse to the
++trivial solution and falsely classify a state as stable. In the independently
++audited 50/50 methane/propane regression at `P = Pc`, this produced an observed
++false-stable band of approximately 7.86 K below that mixture's audited critical
++temperature; this width is specific to that audited example and must not be
++generalized to other fluids, compositions, or pressures, so near-critical
++stability classifications require caution.
++
+ The current flash and saturation inner solves use undamped successive
+ substitution. Saturation calculations search only the requested finite pressure
+ interval and can return `NOT_FOUND` or `INCONCLUSIVE`; they do not establish a
+diff --git a/docs/PROJECT_JOURNAL.md b/docs/PROJECT_JOURNAL.md
+index cc52d09..a84b616 100644
+--- a/docs/PROJECT_JOURNAL.md
++++ b/docs/PROJECT_JOURNAL.md
+@@ -2250,6 +2250,12 @@ The two safe-defer items remain untouched: individual redundant Module 20 root-
+ continuity sub-checks are not each mutation-pinned, and the pre-existing
+ near-critical phase-stability false-stability band remains separate work.
+ 
++### Module 21 closing status
++
++Module 21 was committed at `36d9584`, was included in the final whole-repository
++independent audit, and is accepted as part of the completed original 21-module
++roadmap.
++
+ ## Module/Stage X â€” Name
+ 
+ ### Purpose
+
+```
+
+## Your task
+
+Attempt to FALSIFY this implementation.
+
+Investigate the repository directly with your read-only tools — do not rely on
+the summaries above. Independently reproduce anything numerical that matters.
+Look specifically for:
+
+- scientific error: wrong equation, wrong units, wrong sign, wrong branch
+- tests that cannot fail, or that were weakened to pass
+- silent scope creep, or a protected artifact quietly changed
+- failure paths that return a plausible answer instead of an error
+- claims in documentation that the code does not support
+
+## Required final output
+
+Write the full human-readable audit first, then end with exactly one
+machine-readable block:
+
+<ORCHESTRATOR_RESULT>
+{
+  "verdict": "APPROVED",
+  "findings": [
+    {"id": "C-1", "severity": "C", "blocks": true, "summary": "..."}
+  ],
+  "safe_defer": []
+}
+</ORCHESTRATOR_RESULT>
+
+`verdict` must be exactly one of APPROVED, CONDITIONAL, NOT_APPROVED.
+`severity` must be A (critical), B (major), C (moderate) or D (minor).
+`blocks` must be a boolean.
+
+If you cannot complete the audit, return NOT_APPROVED with a finding that
+explains why. A missing or malformed block is never read as approval.
diff --git a/.ai/claude_audits/20260824-233237-final_release_doc_cleanup-audit.md b/.ai/claude_audits/20260824-233237-final_release_doc_cleanup-audit.md
new file mode 100644
index 0000000..93ea04c
--- /dev/null
+++ b/.ai/claude_audits/20260824-233237-final_release_doc_cleanup-audit.md
@@ -0,0 +1,30 @@
+## Independent Audit — `final_release_doc_cleanup`
+
+### Scope verification
+`git diff --stat HEAD` shows exactly three changed files: `README.md` (+8/−0), `docs/PROJECT_JOURNAL.md` (+6/−0), `.ai/workflow_state.json` (orchestrator bookkeeping only). `git diff --stat HEAD -- src/`, `-- tests/`, and the four protected artifacts (`tests/golden_master/baseline.csv`, `data/component_properties.csv`, `docs/validation/module17_vle_validation.csv`, `docs/validation/module17_vle_validation_summary.json`) are all empty. No code, test, tolerance, baseline, or data changed. `phase_stability.py` is untouched. This matches the declared scope exactly.
+
+### FINAL-D-2 (journal) — verified correct
+The pre-existing "Module 21 remains unstaged and uncommitted pending independent scientific-visualization review" sentence is byte-for-byte untouched (line 2246). The new "### Module 21 closing status" section is appended after it and before the next chronological entry — pure append, no rewrite. I confirmed independently: `git merge-base --is-ancestor 36d9584 b6c010b` returns true, i.e. the Module 21 commit (`36d9584`, "Add scientific plotting layer") is genuinely an ancestor of the final-audit commit (`b6c010b`, "Record final whole-project audit: approved for release"), with an intermediate commit `f1b961b` "Record Module 21 verification and builder availability" corroborating it was reviewed. The claim is factually accurate.
+
+### FINAL-D-1 (README) — verified correct, including the number
+This is the part worth real scrutiny, since a fabricated-but-plausible number is exactly the kind of defect an LLM auditor should catch. I did not trust the cited 7.86 K figure — I reproduced it independently using the actual production code:
+
+- Solved the 50/50 methane/propane critical point with `solve_mixture_critical_point`: **Tc = 321.5829 K, Pc = 8,534,443 Pa** (this is a real, pre-existing test mixture — `test_critical_point.py:615`, `test_criticality.py:337` — distinct from the unrelated 60/40 CH4/C3 fixture used in the phase-envelope/saturation tests).
+- Scanned `analyze_mixture_phase_stability` at `P = Pc` for temperatures below Tc and found a genuine "stable" misclassification band.
+- Bisected the exact crossover: **ΔT = 7.856089 K**, which rounds to 7.86 K — matching the documented figure to three significant figures.
+
+The README wording itself was checked against every constraint in the work order: it names the mechanism (trivial-solution collapse in the bounded stability trials), attributes the 7.86 K figure specifically to "the independently audited 50/50 methane/propane regression at `P = Pc`," and explicitly states "this width is specific to that audited example and must not be generalized to other fluids, compositions, or pressures." No universalizing language is present, and no capability is claimed that the code doesn't have.
+
+### Test/lint evidence
+`.ai/verification/20260824-233236-final_release_doc_cleanup.json` is a machine-recorded log (not merely an LLM claim) showing `pytest -q` → 1137 passed, `ruff check` → clean, `ruff format --check` → clean, all timestamped. Since `src/` and `tests/` are provably unchanged from the last known-good state, re-running the 7-minute suite would not add information beyond what the diff already guarantees, so I did not re-run it.
+
+### Nothing else found
+No silent scope creep, no weakened tests (none touched), no protected-artifact drift, no unsupported claims. `.ai/workflow_state.json`'s changes are ordinary orchestration-loop bookkeeping (state transitions, audit-required flag), not a scientific or documentation change.
+
+<ORCHESTRATOR_RESULT>
+{
+  "verdict": "APPROVED",
+  "findings": [],
+  "safe_defer": []
+}
+</ORCHESTRATOR_RESULT>
\ No newline at end of file
diff --git a/.ai/claude_audits/20260824-233237-final_release_doc_cleanup-audit.transcript.json b/.ai/claude_audits/20260824-233237-final_release_doc_cleanup-audit.transcript.json
new file mode 100644
index 0000000..af9db82
--- /dev/null
+++ b/.ai/claude_audits/20260824-233237-final_release_doc_cleanup-audit.transcript.json
@@ -0,0 +1,30 @@
+{
+  "name": "claude",
+  "command": [
+    "C:\\Users\\user\\AppData\\Roaming\\Claude\\claude-code\\2.1.237\\claude.exe",
+    "--print",
+    "--output-format",
+    "json",
+    "--permission-mode",
+    "plan",
+    "--allowed-tools",
+    "Read,Glob,Grep,Bash,TodoWrite",
+    "--disallowed-tools",
+    "Edit,Write,NotebookEdit,MultiEdit",
+    "--add-dir",
+    "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator",
+    "--max-budget-usd",
+    "5.0"
+  ],
+  "exit_code": 0,
+  "duration_seconds": 332.93769574165344,
+  "cost_usd": 1.6533728,
+  "contract": {
+    "verdict": "APPROVED",
+    "findings": [],
+    "safe_defer": []
+  },
+  "contract_error": null,
+  "stdout": "{\"is_error\":false,\"duration_api_ms\":286240,\"num_turns\":46,\"stop_reason\":\"end_turn\",\"session_id\":\"c486f907-7ccc-449d-bef0-20354c4b3745\",\"total_cost_usd\":1.6533728,\"usage\":{\"input_tokens\":64,\"cache_creation_input_tokens\":99758,\"cache_read_input_tokens\":2366046,\"output_tokens\":22750,\"output_tokens_details\":{\"thinking_tokens\":11218},\"server_tool_use\":{\"web_search_requests\":0,\"web_fetch_requests\":0},\"service_tier\":\"standard\",\"cache_creation\":{\"ephemeral_1h_input_tokens\":99758,\"ephemeral_5m_input_tokens\":0},\"inference_geo\":\"not_available\",\"iterations\":[{\"input_tokens\":2,\"output_tokens\":1893,\"cache_read_input_tokens\":97927,\"cache_creation_input_tokens\":1831,\"cache_creation\":{\"ephemeral_5m_input_tokens\":0,\"ephemeral_1h_input_tokens\":1831},\"type\":\"message\"}],\"speed\":\"standard\"},\"modelUsage\":{\"claude-haiku-4-5-20251001\":{\"inputTokens\":3504,\"outputTokens\":13,\"cacheReadInputTokens\":0,\"cacheCreationInputTokens\":0,\"webSearchRequests\":0,\"costUSD\":0.003569,\"contextWindow\":200000,\"maxOutputTokens\":32000,\"canonicalModel\":\"claude-haiku-4-5\",\"provider\":\"firstParty\"},\"claude-sonnet-5\":{\"inputTokens\":64,\"outputTokens\":22750,\"cacheReadInputTokens\":2366046,\"cacheCreationInputTokens\":99758,\"webSearchRequests\":0,\"costUSD\":1.6498038,\"contextWindow\":1000000,\"maxOutputTokens\":64000,\"canonicalModel\":\"claude-sonnet-5\",\"provider\":\"firstParty\"}},\"permission_denials\":[],\"terminal_reason\":\"completed\",\"fast_mode_state\":\"off\",\"fast_mode_disabled_reason\":\"sdk_opt_in_required\",\"subtype\":\"success\",\"api_error_status\":null,\"result\":\"## Independent Audit \u2014 `final_release_doc_cleanup`\\n\\n### Scope verification\\n`git diff --stat HEAD` shows exactly three changed files: `README.md` (+8/\u22120), `docs/PROJECT_JOURNAL.md` (+6/\u22120), `.ai/workflow_state.json` (orchestrator bookkeeping only). `git diff --stat HEAD -- src/`, `-- tests/`, and the four protected artifacts (`tests/golden_master/baseline.csv`, `data/component_properties.csv`, `docs/validation/module17_vle_validation.csv`, `docs/validation/module17_vle_validation_summary.json`) are all empty. No code, test, tolerance, baseline, or data changed. `phase_stability.py` is untouched. This matches the declared scope exactly.\\n\\n### FINAL-D-2 (journal) \u2014 verified correct\\nThe pre-existing \\\"Module 21 remains unstaged and uncommitted pending independent scientific-visualization review\\\" sentence is byte-for-byte untouched (line 2246). The new \\\"### Module 21 closing status\\\" section is appended after it and before the next chronological entry \u2014 pure append, no rewrite. I confirmed independently: `git merge-base --is-ancestor 36d9584 b6c010b` returns true, i.e. the Module 21 commit (`36d9584`, \\\"Add scientific plotting layer\\\") is genuinely an ancestor of the final-audit commit (`b6c010b`, \\\"Record final whole-project audit: approved for release\\\"), with an intermediate commit `f1b961b` \\\"Record Module 21 verification and builder availability\\\" corroborating it was reviewed. The claim is factually accurate.\\n\\n### FINAL-D-1 (README) \u2014 verified correct, including the number\\nThis is the part worth real scrutiny, since a fabricated-but-plausible number is exactly the kind of defect an LLM auditor should catch. I did not trust the cited 7.86 K figure \u2014 I reproduced it independently using the actual production code:\\n\\n- Solved the 50/50 methane/propane critical point with `solve_mixture_critical_point`: **Tc = 321.5829 K, Pc = 8,534,443 Pa** (this is a real, pre-existing test mixture \u2014 `test_critical_point.py:615`, `test_criticality.py:337` \u2014 distinct from the unrelated 60/40 CH4/C3 fixture used in the phase-envelope/saturation tests).\\n- Scanned `analyze_mixture_phase_stability` at `P = Pc` for temperatures below Tc and found a genuine \\\"stable\\\" misclassification band.\\n- Bisected the exact crossover: **\u0394T = 7.856089 K**, which rounds to 7.86 K \u2014 matching the documented figure to three significant figures.\\n\\nThe README wording itself was checked against every constraint in the work order: it names the mechanism (trivial-solution collapse in the bounded stability trials), attributes the 7.86 K figure specifically to \\\"the independently audited 50/50 methane/propane regression at `P = Pc`,\\\" and explicitly states \\\"this width is specific to that audited example and must not be generalized to other fluids, compositions, or pressures.\\\" No universalizing language is present, and no capability is claimed that the code doesn't have.\\n\\n### Test/lint evidence\\n`.ai/verification/20260824-233236-final_release_doc_cleanup.json` is a machine-recorded log (not merely an LLM claim) showing `pytest -q` \u2192 1137 passed, `ruff check` \u2192 clean, `ruff format --check` \u2192 clean, all timestamped. Since `src/` and `tests/` are provably unchanged from the last known-good state, re-running the 7-minute suite would not add information beyond what the diff already guarantees, so I did not re-run it.\\n\\n### Nothing else found\\nNo silent scope creep, no weakened tests (none touched), no protected-artifact drift, no unsupported claims. `.ai/workflow_state.json`'s changes are ordinary orchestration-loop bookkeeping (state transitions, audit-required flag), not a scientific or documentation change.\\n\\n<ORCHESTRATOR_RESULT>\\n{\\n  \\\"verdict\\\": \\\"APPROVED\\\",\\n  \\\"findings\\\": [],\\n  \\\"safe_defer\\\": []\\n}\\n</ORCHESTRATOR_RESULT>\",\"ttft_ms\":35486,\"ttft_stream_ms\":1717,\"time_to_request_ms\":176,\"type\":\"result\",\"duration_ms\":327725,\"uuid\":\"b5b019a8-6f75-40f9-a78d-ccbacef7bf27\"}\n",
+  "stderr": ""
+}
\ No newline at end of file
diff --git a/.ai/codex_reports/20260824-230618-final_release_doc_cleanup-report.last-message.txt b/.ai/codex_reports/20260824-230618-final_release_doc_cleanup-report.last-message.txt
new file mode 100644
index 0000000..feb0099
--- /dev/null
+++ b/.ai/codex_reports/20260824-230618-final_release_doc_cleanup-report.last-message.txt
@@ -0,0 +1,15 @@
+Updated only the requested documentation:
+
+- README documents the localized near-critical trivial-solution collapse and mixture-specific observed 7.86 K example.
+- Project journal records Module 21’s commit, final audit inclusion, and acceptance.
+- Protected artifact hashes remain byte-identical.
+- Existing `.ai` changes were untouched.
+
+<ORCHESTRATOR_RESULT>
+{
+  "status": "COMPLETE",
+  "tests_claimed": "pytest -q: 1137 passed in 436.44s; ruff check .: All checks passed; ruff format --check .: 109 files already formatted",
+  "files_changed": ["README.md", "docs/PROJECT_JOURNAL.md"],
+  "ready_for_local_verification": true
+}
+</ORCHESTRATOR_RESULT>
\ No newline at end of file
diff --git a/.ai/codex_reports/20260824-230618-final_release_doc_cleanup-report.md b/.ai/codex_reports/20260824-230618-final_release_doc_cleanup-report.md
new file mode 100644
index 0000000..feb0099
--- /dev/null
+++ b/.ai/codex_reports/20260824-230618-final_release_doc_cleanup-report.md
@@ -0,0 +1,15 @@
+Updated only the requested documentation:
+
+- README documents the localized near-critical trivial-solution collapse and mixture-specific observed 7.86 K example.
+- Project journal records Module 21’s commit, final audit inclusion, and acceptance.
+- Protected artifact hashes remain byte-identical.
+- Existing `.ai` changes were untouched.
+
+<ORCHESTRATOR_RESULT>
+{
+  "status": "COMPLETE",
+  "tests_claimed": "pytest -q: 1137 passed in 436.44s; ruff check .: All checks passed; ruff format --check .: 109 files already formatted",
+  "files_changed": ["README.md", "docs/PROJECT_JOURNAL.md"],
+  "ready_for_local_verification": true
+}
+</ORCHESTRATOR_RESULT>
\ No newline at end of file
diff --git a/.ai/codex_reports/20260824-230618-final_release_doc_cleanup-report.transcript.json b/.ai/codex_reports/20260824-230618-final_release_doc_cleanup-report.transcript.json
new file mode 100644
index 0000000..43d9ac5
--- /dev/null
+++ b/.ai/codex_reports/20260824-230618-final_release_doc_cleanup-report.transcript.json
@@ -0,0 +1,28 @@
+{
+  "name": "codex",
+  "command": [
+    "C:\\Users\\user\\AppData\\Roaming\\npm\\codex.CMD",
+    "exec",
+    "-s",
+    "workspace-write",
+    "-C",
+    "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator",
+    "--output-last-message",
+    "C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.ai\\codex_reports\\20260824-230618-final_release_doc_cleanup-report.last-message.txt"
+  ],
+  "exit_code": 0,
+  "duration_seconds": 1138.1285412311554,
+  "cost_usd": null,
+  "contract": {
+    "status": "COMPLETE",
+    "tests_claimed": "pytest -q: 1137 passed in 436.44s; ruff check .: All checks passed; ruff format --check .: 109 files already formatted",
+    "files_changed": [
+      "README.md",
+      "docs/PROJECT_JOURNAL.md"
+    ],
+    "ready_for_local_verification": true
+  },
+  "contract_error": null,
+  "stdout": "Updated only the requested documentation:\n\n- README documents the localized near-critical trivial-solution collapse and mixture-specific observed 7.86 K example.\n- Project journal records Module 21\u2019s commit, final audit inclusion, and acceptance.\n- Protected artifact hashes remain byte-identical.\n- Existing `.ai` changes were untouched.\n\n<ORCHESTRATOR_RESULT>\n{\n  \"status\": \"COMPLETE\",\n  \"tests_claimed\": \"pytest -q: 1137 passed in 436.44s; ruff check .: All checks passed; ruff format --check .: 109 files already formatted\",\n  \"files_changed\": [\"README.md\", \"docs/PROJECT_JOURNAL.md\"],\n  \"ready_for_local_verification\": true\n}\n</ORCHESTRATOR_RESULT>\n",
+  "stderr": "tly\n+audited 50/50 methane/propane regression at `P = Pc`, this produced an observed\n+false-stable band of approximately 7.86 K below that mixture's audited critical\n+temperature; this width is specific to that audited example and must not be\n+generalized to other fluids, compositions, or pressures, so near-critical\n+stability classifications require caution.\n+\n+The current flash and saturation inner solves use undamped successive\n+substitution. Saturation calculations search only the requested finite pressure\n+interval and can return `NOT_FOUND` or `INCONCLUSIVE`; they do not establish a\n globally complete phase diagram. Envelope tracing defaults to natural\n temperature continuation. The opt-in pseudo-arclength mode can cross regular\n geometric turns but still terminates at root-role loss or indistinguishable\ndiff --git a/docs/PROJECT_JOURNAL.md b/docs/PROJECT_JOURNAL.md\nindex 2a092b40a22df4550788454eab60a754f185a81b..f649151a93391feb2b441e556df43081248a9061\n--- a/docs/PROJECT_JOURNAL.md\n+++ b/docs/PROJECT_JOURNAL.md\n@@ -2246,11 +2246,17 @@\n or pseudocomponent implementation is included. Module 21 remains unstaged and\n uncommitted pending independent scientific-visualization review.\n \n-The two safe-defer items remain untouched: individual redundant Module 20 root-\n-continuity sub-checks are not each mutation-pinned, and the pre-existing\n-near-critical phase-stability false-stability band remains separate work.\n-\n-## Module/Stage X \u2014 Name\n+The two safe-defer items remain untouched: individual redundant Module 20 root-\n+continuity sub-checks are not each mutation-pinned, and the pre-existing\n+near-critical phase-stability false-stability band remains separate work.\n+\n+### Module 21 closing status\n+\n+Module 21 was committed at `36d9584`, was included in the final whole-repository\n+independent audit, and is accepted as part of the completed original 21-module\n+roadmap.\n+\n+## Module/Stage X \u2014 Name\n \n ### Purpose\n \n\ndiff --git a/README.md b/README.md\nindex 3dac99de2b04c84f553330e162d4b62b19fba1ea..c811ec37e5e65f1f2a10a4daa9c1b24dacbc6e2e\n--- a/README.md\n+++ b/README.md\n@@ -222,8 +222,8 @@\n \n - three-phase or multiphase flash calculations\n - accelerated, damped, or globally convergent flash algorithms\n-- exhaustive/global phase-stability certification beyond the bounded\n-  Wilson-plus-fallback Michelsen-style trials\n+- exhaustive/global phase-stability certification beyond the bounded\n+  Wilson-plus-fallback Michelsen-style trials\n - critical-locus continuation or a supported-fluid temperature-fold\n   regression (the pseudo-arclength core has generic-fold and CH4/C3\n   pressure-turning evidence)\n@@ -232,11 +232,19 @@\n - experimental authentication and uncertainty quantification beyond the\n   verified bibliographic traceability of component-property values\n - engineering unit conversion functions\n-- a Streamlit user interface\n-\n-The current flash and saturation inner solves use undamped successive\n-substitution. Saturation calculations search only the requested finite pressure\n-interval and can return `NOT_FOUND` or `INCONCLUSIVE`; they do not establish a\n+- a Streamlit user interface\n+\n+Near a mixture critical point, the bounded stability trials can collapse to the\n+trivial solution and falsely classify a state as stable. In the independently\n+audited 50/50 methane/propane regression at `P = Pc`, this produced an observed\n+false-stable band of approximately 7.86 K below that mixture's audited critical\n+temperature; this width is specific to that audited example and must not be\n+generalized to other fluids, compositions, or pressures, so near-critical\n+stability classifications require caution.\n+\n+The current flash and saturation inner solves use undamped successive\n+substitution. Saturation calculations search only the requested finite pressure\n+interval and can return `NOT_FOUND` or `INCONCLUSIVE`; they do not establish a\n globally complete phase diagram. Envelope tracing defaults to natural\n temperature continuation. The opt-in pseudo-arclength mode can cross regular\n geometric turns but still terminates at root-role loss or indistinguishable\ndiff --git a/docs/PROJECT_JOURNAL.md b/docs/PROJECT_JOURNAL.md\nindex 2a092b40a22df4550788454eab60a754f185a81b..f649151a93391feb2b441e556df43081248a9061\n--- a/docs/PROJECT_JOURNAL.md\n+++ b/docs/PROJECT_JOURNAL.md\n@@ -2246,11 +2246,17 @@\n or pseudocomponent implementation is included. Module 21 remains unstaged and\n uncommitted pending independent scientific-visualization review.\n \n-The two safe-defer items remain untouched: individual redundant Module 20 root-\n-continuity sub-checks are not each mutation-pinned, and the pre-existing\n-near-critical phase-stability false-stability band remains separate work.\n-\n-## Module/Stage X \u2014 Name\n+The two safe-defer items remain untouched: individual redundant Module 20 root-\n+continuity sub-checks are not each mutation-pinned, and the pre-existing\n+near-critical phase-stability false-stability band remains separate work.\n+\n+### Module 21 closing status\n+\n+Module 21 was committed at `36d9584`, was included in the final whole-repository\n+independent audit, and is accepted as part of the completed original 21-module\n+roadmap.\n+\n+## Module/Stage X \u2014 Name\n \n ### Purpose\n \n\ndiff --git a/README.md b/README.md\nindex 3dac99de2b04c84f553330e162d4b62b19fba1ea..c811ec37e5e65f1f2a10a4daa9c1b24dacbc6e2e\n--- a/README.md\n+++ b/README.md\n@@ -222,8 +222,8 @@\n \n - three-phase or multiphase flash calculations\n - accelerated, damped, or globally convergent flash algorithms\n-- exhaustive/global phase-stability certification beyond the bounded\n-  Wilson-plus-fallback Michelsen-style trials\n+- exhaustive/global phase-stability certification beyond the bounded\n+  Wilson-plus-fallback Michelsen-style trials\n - critical-locus continuation or a supported-fluid temperature-fold\n   regression (the pseudo-arclength core has generic-fold and CH4/C3\n   pressure-turning evidence)\n@@ -232,11 +232,19 @@\n - experimental authentication and uncertainty quantification beyond the\n   verified bibliographic traceability of component-property values\n - engineering unit conversion functions\n-- a Streamlit user interface\n-\n-The current flash and saturation inner solves use undamped successive\n-substitution. Saturation calculations search only the requested finite pressure\n-interval and can return `NOT_FOUND` or `INCONCLUSIVE`; they do not establish a\n+- a Streamlit user interface\n+\n+Near a mixture critical point, the bounded stability trials can collapse to the\n+trivial solution and falsely classify a state as stable. In the independently\n+audited 50/50 methane/propane regression at `P = Pc`, this produced an observed\n+false-stable band of approximately 7.86 K below that mixture's audited critical\n+temperature; this width is specific to that audited example and must not be\n+generalized to other fluids, compositions, or pressures, so near-critical\n+stability classifications require caution.\n+\n+The current flash and saturation inner solves use undamped successive\n+substitution. Saturation calculations search only the requested finite pressure\n+interval and can return `NOT_FOUND` or `INCONCLUSIVE`; they do not establish a\n globally complete phase diagram. Envelope tracing defaults to natural\n temperature continuation. The opt-in pseudo-arclength mode can cross regular\n geometric turns but still terminates at root-role loss or indistinguishable\ndiff --git a/docs/PROJECT_JOURNAL.md b/docs/PROJECT_JOURNAL.md\nindex 2a092b40a22df4550788454eab60a754f185a81b..f649151a93391feb2b441e556df43081248a9061\n--- a/docs/PROJECT_JOURNAL.md\n+++ b/docs/PROJECT_JOURNAL.md\n@@ -2246,11 +2246,17 @@\n or pseudocomponent implementation is included. Module 21 remains unstaged and\n uncommitted pending independent scientific-visualization review.\n \n-The two safe-defer items remain untouched: individual redundant Module 20 root-\n-continuity sub-checks are not each mutation-pinned, and the pre-existing\n-near-critical phase-stability false-stability band remains separate work.\n-\n-## Module/Stage X \u2014 Name\n+The two safe-defer items remain untouched: individual redundant Module 20 root-\n+continuity sub-checks are not each mutation-pinned, and the pre-existing\n+near-critical phase-stability false-stability band remains separate work.\n+\n+### Module 21 closing status\n+\n+Module 21 was committed at `36d9584`, was included in the final whole-repository\n+independent audit, and is accepted as part of the completed original 21-module\n+roadmap.\n+\n+## Module/Stage X \u2014 Name\n \n ### Purpose\n \n\ndiff --git a/README.md b/README.md\nindex 3dac99de2b04c84f553330e162d4b62b19fba1ea..c811ec37e5e65f1f2a10a4daa9c1b24dacbc6e2e\n--- a/README.md\n+++ b/README.md\n@@ -222,8 +222,8 @@\n \n - three-phase or multiphase flash calculations\n - accelerated, damped, or globally convergent flash algorithms\n-- exhaustive/global phase-stability certification beyond the bounded\n-  Wilson-plus-fallback Michelsen-style trials\n+- exhaustive/global phase-stability certification beyond the bounded\n+  Wilson-plus-fallback Michelsen-style trials\n - critical-locus continuation or a supported-fluid temperature-fold\n   regression (the pseudo-arclength core has generic-fold and CH4/C3\n   pressure-turning evidence)\n@@ -232,11 +232,19 @@\n - experimental authentication and uncertainty quantification beyond the\n   verified bibliographic traceability of component-property values\n - engineering unit conversion functions\n-- a Streamlit user interface\n-\n-The current flash and saturation inner solves use undamped successive\n-substitution. Saturation calculations search only the requested finite pressure\n-interval and can return `NOT_FOUND` or `INCONCLUSIVE`; they do not establish a\n+- a Streamlit user interface\n+\n+Near a mixture critical point, the bounded stability trials can collapse to the\n+trivial solution and falsely classify a state as stable. In the independently\n+audited 50/50 methane/propane regression at `P = Pc`, this produced an observed\n+false-stable band of approximately 7.86 K below that mixture's audited critical\n+temperature; this width is specific to that audited example and must not be\n+generalized to other fluids, compositions, or pressures, so near-critical\n+stability classifications require caution.\n+\n+The current flash and saturation inner solves use undamped successive\n+substitution. Saturation calculations search only the requested finite pressure\n+interval and can return `NOT_FOUND` or `INCONCLUSIVE`; they do not establish a\n globally complete phase diagram. Envelope tracing defaults to natural\n temperature continuation. The opt-in pseudo-arclength mode can cross regular\n geometric turns but still terminates at root-role loss or indistinguishable\ndiff --git a/docs/PROJECT_JOURNAL.md b/docs/PROJECT_JOURNAL.md\nindex 2a092b40a22df4550788454eab60a754f185a81b..f649151a93391feb2b441e556df43081248a9061\n--- a/docs/PROJECT_JOURNAL.md\n+++ b/docs/PROJECT_JOURNAL.md\n@@ -2246,11 +2246,17 @@\n or pseudocomponent implementation is included. Module 21 remains unstaged and\n uncommitted pending independent scientific-visualization review.\n \n-The two safe-defer items remain untouched: individual redundant Module 20 root-\n-continuity sub-checks are not each mutation-pinned, and the pre-existing\n-near-critical phase-stability false-stability band remains separate work.\n-\n-## Module/Stage X \u2014 Name\n+The two safe-defer items remain untouched: individual redundant Module 20 root-\n+continuity sub-checks are not each mutation-pinned, and the pre-existing\n+near-critical phase-stability false-stability band remains separate work.\n+\n+### Module 21 closing status\n+\n+Module 21 was committed at `36d9584`, was included in the final whole-repository\n+independent audit, and is accepted as part of the completed original 21-module\n+roadmap.\n+\n+## Module/Stage X \u2014 Name\n \n ### Purpose\n \n\ncodex\nThe clean pytest rerun has reached 75% with no failures or errors.\ndiff --git a/README.md b/README.md\nindex 3dac99de2b04c84f553330e162d4b62b19fba1ea..c811ec37e5e65f1f2a10a4daa9c1b24dacbc6e2e\n--- a/README.md\n+++ b/README.md\n@@ -222,8 +222,8 @@\n \n - three-phase or multiphase flash calculations\n - accelerated, damped, or globally convergent flash algorithms\n-- exhaustive/global phase-stability certification beyond the bounded\n-  Wilson-plus-fallback Michelsen-style trials\n+- exhaustive/global phase-stability certification beyond the bounded\n+  Wilson-plus-fallback Michelsen-style trials\n - critical-locus continuation or a supported-fluid temperature-fold\n   regression (the pseudo-arclength core has generic-fold and CH4/C3\n   pressure-turning evidence)\n@@ -232,11 +232,19 @@\n - experimental authentication and uncertainty quantification beyond the\n   verified bibliographic traceability of component-property values\n - engineering unit conversion functions\n-- a Streamlit user interface\n-\n-The current flash and saturation inner solves use undamped successive\n-substitution. Saturation calculations search only the requested finite pressure\n-interval and can return `NOT_FOUND` or `INCONCLUSIVE`; they do not establish a\n+- a Streamlit user interface\n+\n+Near a mixture critical point, the bounded stability trials can collapse to the\n+trivial solution and falsely classify a state as stable. In the independently\n+audited 50/50 methane/propane regression at `P = Pc`, this produced an observed\n+false-stable band of approximately 7.86 K below that mixture's audited critical\n+temperature; this width is specific to that audited example and must not be\n+generalized to other fluids, compositions, or pressures, so near-critical\n+stability classifications require caution.\n+\n+The current flash and saturation inner solves use undamped successive\n+substitution. Saturation calculations search only the requested finite pressure\n+interval and can return `NOT_FOUND` or `INCONCLUSIVE`; they do not establish a\n globally complete phase diagram. Envelope tracing defaults to natural\n temperature continuation. The opt-in pseudo-arclength mode can cross regular\n geometric turns but still terminates at root-role loss or indistinguishable\ndiff --git a/docs/PROJECT_JOURNAL.md b/docs/PROJECT_JOURNAL.md\nindex 2a092b40a22df4550788454eab60a754f185a81b..f649151a93391feb2b441e556df43081248a9061\n--- a/docs/PROJECT_JOURNAL.md\n+++ b/docs/PROJECT_JOURNAL.md\n@@ -2246,11 +2246,17 @@\n or pseudocomponent implementation is included. Module 21 remains unstaged and\n uncommitted pending independent scientific-visualization review.\n \n-The two safe-defer items remain untouched: individual redundant Module 20 root-\n-continuity sub-checks are not each mutation-pinned, and the pre-existing\n-near-critical phase-stability false-stability band remains separate work.\n-\n-## Module/Stage X \u2014 Name\n+The two safe-defer items remain untouched: individual redundant Module 20 root-\n+continuity sub-checks are not each mutation-pinned, and the pre-existing\n+near-critical phase-stability false-stability band remains separate work.\n+\n+### Module 21 closing status\n+\n+Module 21 was committed at `36d9584`, was included in the final whole-repository\n+independent audit, and is accepted as part of the completed original 21-module\n+roadmap.\n+\n+## Module/Stage X \u2014 Name\n \n ### Purpose\n \n\ndiff --git a/README.md b/README.md\nindex 3dac99de2b04c84f553330e162d4b62b19fba1ea..c811ec37e5e65f1f2a10a4daa9c1b24dacbc6e2e\n--- a/README.md\n+++ b/README.md\n@@ -222,8 +222,8 @@\n \n - three-phase or multiphase flash calculations\n - accelerated, damped, or globally convergent flash algorithms\n-- exhaustive/global phase-stability certification beyond the bounded\n-  Wilson-plus-fallback Michelsen-style trials\n+- exhaustive/global phase-stability certification beyond the bounded\n+  Wilson-plus-fallback Michelsen-style trials\n - critical-locus continuation or a supported-fluid temperature-fold\n   regression (the pseudo-arclength core has generic-fold and CH4/C3\n   pressure-turning evidence)\n@@ -232,11 +232,19 @@\n - experimental authentication and uncertainty quantification beyond the\n   verified bibliographic traceability of component-property values\n - engineering unit conversion functions\n-- a Streamlit user interface\n-\n-The current flash and saturation inner solves use undamped successive\n-substitution. Saturation calculations search only the requested finite pressure\n-interval and can return `NOT_FOUND` or `INCONCLUSIVE`; they do not establish a\n+- a Streamlit user interface\n+\n+Near a mixture critical point, the bounded stability trials can collapse to the\n+trivial solution and falsely classify a state as stable. In the independently\n+audited 50/50 methane/propane regression at `P = Pc`, this produced an observed\n+false-stable band of approximately 7.86 K below that mixture's audited critical\n+temperature; this width is specific to that audited example and must not be\n+generalized to other fluids, compositions, or pressures, so near-critical\n+stability classifications require caution.\n+\n+The current flash and saturation inner solves use undamped successive\n+substitution. Saturation calculations search only the requested finite pressure\n+interval and can return `NOT_FOUND` or `INCONCLUSIVE`; they do not establish a\n globally complete phase diagram. Envelope tracing defaults to natural\n temperature continuation. The opt-in pseudo-arclength mode can cross regular\n geometric turns but still terminates at root-role loss or indistinguishable\ndiff --git a/docs/PROJECT_JOURNAL.md b/docs/PROJECT_JOURNAL.md\nindex 2a092b40a22df4550788454eab60a754f185a81b..f649151a93391feb2b441e556df43081248a9061\n--- a/docs/PROJECT_JOURNAL.md\n+++ b/docs/PROJECT_JOURNAL.md\n@@ -2246,11 +2246,17 @@\n or pseudocomponent implementation is included. Module 21 remains unstaged and\n uncommitted pending independent scientific-visualization review.\n \n-The two safe-defer items remain untouched: individual redundant Module 20 root-\n-continuity sub-checks are not each mutation-pinned, and the pre-existing\n-near-critical phase-stability false-stability band remains separate work.\n-\n-## Module/Stage X \u2014 Name\n+The two safe-defer items remain untouched: individual redundant Module 20 root-\n+continuity sub-checks are not each mutation-pinned, and the pre-existing\n+near-critical phase-stability false-stability band remains separate work.\n+\n+### Module 21 closing status\n+\n+Module 21 was committed at `36d9584`, was included in the final whole-repository\n+independent audit, and is accepted as part of the completed original 21-module\n+roadmap.\n+\n+## Module/Stage X \u2014 Name\n \n ### Purpose\n \n\n succeeded in 439011ms:\n........................................................................ [  6%]\n........................................................................ [ 12%]\n........................................................................ [ 18%]\n........................................................................ [ 25%]\n........................................................................ [ 31%]\n........................................................................ [ 37%]\n........................................................................ [ 44%]\n........................................................................ [ 50%]\n........................................................................ [ 56%]\n........................................................................ [ 63%]\n........................................................................ [ 69%]\n........................................................................ [ 75%]\n........................................................................ [ 82%]\n........................................................................ [ 88%]\n........................................................................ [ 94%]\n.........................................................                [100%]\n1137 passed in 436.44s (0:07:16)\n\ndiff --git a/README.md b/README.md\nindex 3dac99de2b04c84f553330e162d4b62b19fba1ea..c811ec37e5e65f1f2a10a4daa9c1b24dacbc6e2e\n--- a/README.md\n+++ b/README.md\n@@ -222,8 +222,8 @@\n \n - three-phase or multiphase flash calculations\n - accelerated, damped, or globally convergent flash algorithms\n-- exhaustive/global phase-stability certification beyond the bounded\n-  Wilson-plus-fallback Michelsen-style trials\n+- exhaustive/global phase-stability certification beyond the bounded\n+  Wilson-plus-fallback Michelsen-style trials\n - critical-locus continuation or a supported-fluid temperature-fold\n   regression (the pseudo-arclength core has generic-fold and CH4/C3\n   pressure-turning evidence)\n@@ -232,11 +232,19 @@\n - experimental authentication and uncertainty quantification beyond the\n   verified bibliographic traceability of component-property values\n - engineering unit conversion functions\n-- a Streamlit user interface\n-\n-The current flash and saturation inner solves use undamped successive\n-substitution. Saturation calculations search only the requested finite pressure\n-interval and can return `NOT_FOUND` or `INCONCLUSIVE`; they do not establish a\n+- a Streamlit user interface\n+\n+Near a mixture critical point, the bounded stability trials can collapse to the\n+trivial solution and falsely classify a state as stable. In the independently\n+audited 50/50 methane/propane regression at `P = Pc`, this produced an observed\n+false-stable band of approximately 7.86 K below that mixture's audited critical\n+temperature; this width is specific to that audited example and must not be\n+generalized to other fluids, compositions, or pressures, so near-critical\n+stability classifications require caution.\n+\n+The current flash and saturation inner solves use undamped successive\n+substitution. Saturation calculations search only the requested finite pressure\n+interval and can return `NOT_FOUND` or `INCONCLUSIVE`; they do not establish a\n globally complete phase diagram. Envelope tracing defaults to natural\n temperature continuation. The opt-in pseudo-arclength mode can cross regular\n geometric turns but still terminates at root-role loss or indistinguishable\ndiff --git a/docs/PROJECT_JOURNAL.md b/docs/PROJECT_JOURNAL.md\nindex 2a092b40a22df4550788454eab60a754f185a81b..f649151a93391feb2b441e556df43081248a9061\n--- a/docs/PROJECT_JOURNAL.md\n+++ b/docs/PROJECT_JOURNAL.md\n@@ -2246,11 +2246,17 @@\n or pseudocomponent implementation is included. Module 21 remains unstaged and\n uncommitted pending independent scientific-visualization review.\n \n-The two safe-defer items remain untouched: individual redundant Module 20 root-\n-continuity sub-checks are not each mutation-pinned, and the pre-existing\n-near-critical phase-stability false-stability band remains separate work.\n-\n-## Module/Stage X \u2014 Name\n+The two safe-defer items remain untouched: individual redundant Module 20 root-\n+continuity sub-checks are not each mutation-pinned, and the pre-existing\n+near-critical phase-stability false-stability band remains separate work.\n+\n+### Module 21 closing status\n+\n+Module 21 was committed at `36d9584`, was included in the final whole-repository\n+independent audit, and is accepted as part of the completed original 21-module\n+roadmap.\n+\n+## Module/Stage X \u2014 Name\n \n ### Purpose\n \n\ncodex\nThe full suite now passes: `1137 passed in 436.44s`. I\u2019m removing only the verified workspace-local pytest temp directory, then performing the final scope, whitespace, and protected-hash checks.\n2026-08-24T20:24:41.367486Z ERROR codex_core::tools::router: error=exec_command failed for `\"C:\\\\windows\\\\System32\\\\WindowsPowerShell\\\\v1.0\\\\powershell.exe\" -Command '$workspacePath = (Resolve-Path -LiteralPath '\"'.').Path; \"'$testTempPath = (Resolve-Path -LiteralPath '\"'.pytest-tmp-final-release').Path; if (-not \"'$testTempPath.StartsWith($workspacePath + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw \"Refusing removal outside workspace: $testTempPath\" }; Remove-Item -LiteralPath $testTempPath -Recurse -Force; git diff --check; git diff --name-only; git status --short; Get-FileHash tests/golden_master/baseline.csv -Algorithm SHA256; Get-FileHash data/component_properties.csv -Algorithm SHA256; Get-FileHash docs/validation/module17_vle_validation.csv -Algorithm SHA256; Get-FileHash docs/validation/module17_vle_validation_summary.json -Algorithm SHA256'`: CreateProcess { message: \"Rejected(\\\"`\\\\\\\"C:\\\\\\\\\\\\\\\\windows\\\\\\\\\\\\\\\\System32\\\\\\\\\\\\\\\\WindowsPowerShell\\\\\\\\\\\\\\\\v1.0\\\\\\\\\\\\\\\\powershell.exe\\\\\\\" -Command '$workspacePath = (Resolve-Path -LiteralPath '\\\\\\\"'.').Path; \\\\\\\"'$testTempPath = (Resolve-Path -LiteralPath '\\\\\\\"'.pytest-tmp-final-release').Path; if (-not \\\\\\\"'$testTempPath.StartsWith($workspacePath + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw \\\\\\\"Refusing removal outside workspace: $testTempPath\\\\\\\" }; Remove-Item -LiteralPath $testTempPath -Recurse -Force; git diff --check; git diff --name-only; git status --short; Get-FileHash tests/golden_master/baseline.csv -Algorithm SHA256; Get-FileHash data/component_properties.csv -Algorithm SHA256; Get-FileHash docs/validation/module17_vle_validation.csv -Algorithm SHA256; Get-FileHash docs/validation/module17_vle_validation_summary.json -Algorithm SHA256'` rejected: blocked by policy\\\")\" }\ndiff --git a/README.md b/README.md\nindex 3dac99de2b04c84f553330e162d4b62b19fba1ea..c811ec37e5e65f1f2a10a4daa9c1b24dacbc6e2e\n--- a/README.md\n+++ b/README.md\n@@ -222,8 +222,8 @@\n \n - three-phase or multiphase flash calculations\n - accelerated, damped, or globally convergent flash algorithms\n-- exhaustive/global phase-stability certification beyond the bounded\n-  Wilson-plus-fallback Michelsen-style trials\n+- exhaustive/global phase-stability certification beyond the bounded\n+  Wilson-plus-fallback Michelsen-style trials\n - critical-locus continuation or a supported-fluid temperature-fold\n   regression (the pseudo-arclength core has generic-fold and CH4/C3\n   pressure-turning evidence)\n@@ -232,11 +232,19 @@\n - experimental authentication and uncertainty quantification beyond the\n   verified bibliographic traceability of component-property values\n - engineering unit conversion functions\n-- a Streamlit user interface\n-\n-The current flash and saturation inner solves use undamped successive\n-substitution. Saturation calculations search only the requested finite pressure\n-interval and can return `NOT_FOUND` or `INCONCLUSIVE`; they do not establish a\n+- a Streamlit user interface\n+\n+Near a mixture critical point, the bounded stability trials can collapse to the\n+trivial solution and falsely classify a state as stable. In the independently\n+audited 50/50 methane/propane regression at `P = Pc`, this produced an observed\n+false-stable band of approximately 7.86 K below that mixture's audited critical\n+temperature; this width is specific to that audited example and must not be\n+generalized to other fluids, compositions, or pressures, so near-critical\n+stability classifications require caution.\n+\n+The current flash and saturation inner solves use undamped successive\n+substitution. Saturation calculations search only the requested finite pressure\n+interval and can return `NOT_FOUND` or `INCONCLUSIVE`; they do not establish a\n globally complete phase diagram. Envelope tracing defaults to natural\n temperature continuation. The opt-in pseudo-arclength mode can cross regular\n geometric turns but still terminates at root-role loss or indistinguishable\ndiff --git a/docs/PROJECT_JOURNAL.md b/docs/PROJECT_JOURNAL.md\nindex 2a092b40a22df4550788454eab60a754f185a81b..f649151a93391feb2b441e556df43081248a9061\n--- a/docs/PROJECT_JOURNAL.md\n+++ b/docs/PROJECT_JOURNAL.md\n@@ -2246,11 +2246,17 @@\n or pseudocomponent implementation is included. Module 21 remains unstaged and\n uncommitted pending independent scientific-visualization review.\n \n-The two safe-defer items remain untouched: individual redundant Module 20 root-\n-continuity sub-checks are not each mutation-pinned, and the pre-existing\n-near-critical phase-stability false-stability band remains separate work.\n-\n-## Module/Stage X \u2014 Name\n+The two safe-defer items remain untouched: individual redundant Module 20 root-\n+continuity sub-checks are not each mutation-pinned, and the pre-existing\n+near-critical phase-stability false-stability band remains separate work.\n+\n+### Module 21 closing status\n+\n+Module 21 was committed at `36d9584`, was included in the final whole-repository\n+independent audit, and is accepted as part of the completed original 21-module\n+roadmap.\n+\n+## Module/Stage X \u2014 Name\n \n ### Purpose\n \n\ncodex\nThe combined cleanup command was blocked before execution by the filesystem safety policy. I\u2019ll split it into an explicit read-only path verification, a narrowly targeted removal, and separate final checks.\nexec\n\"C:\\\\windows\\\\System32\\\\WindowsPowerShell\\\\v1.0\\\\powershell.exe\" -Command '$workspacePath = (Resolve-Path -LiteralPath '\"'.').Path; \"'$testTempPath = (Resolve-Path -LiteralPath '\"'.pytest-tmp-final-release').Path; Write-Output \\\"WORKSPACE=\"'$workspacePath\"; Write-Output \"TEMP_TARGET=$testTempPath\"; Write-Output \"WITHIN_WORKSPACE=$($testTempPath.StartsWith($workspacePath + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase))\"; Get-ChildItem -LiteralPath $testTempPath -Force | Select-Object -First 10 FullName' in C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\n succeeded in 541ms:\nWORKSPACE=C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\nTEMP_TARGET=C:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.pytest-tmp-final-release\nWITHIN_WORKSPACE=True\n\nFullName                                                                                                               \n--------                                                                                                               \nC:\\Users\\user\\OneDrive - American University of Beirut\\Desktop\\pvt-phase-simulator\\.pytest-tmp-final-release\\pytest-...\n\n\n\ndiff --git a/README.md b/README.md\nindex 3dac99de2b04c84f553330e162d4b62b19fba1ea..c811ec37e5e65f1f2a10a4daa9c1b24dacbc6e2e\n--- a/README.md\n+++ b/README.md\n@@ -222,8 +222,8 @@\n \n - three-phase or multiphase flash calculations\n - accelerated, damped, or globally convergent flash algorithms\n-- exhaustive/global phase-stability certification beyond the bounded\n-  Wilson-plus-fallback Michelsen-style trials\n+- exhaustive/global phase-stability certification beyond the bounded\n+  Wilson-plus-fallback Michelsen-style trials\n - critical-locus continuation or a supported-fluid temperature-fold\n   regression (the pseudo-arclength core has generic-fold and CH4/C3\n   pressure-turning evidence)\n@@ -232,11 +232,19 @@\n - experimental authentication and uncertainty quantification beyond the\n   verified bibliographic traceability of component-property values\n - engineering unit conversion functions\n-- a Streamlit user interface\n-\n-The current flash and saturation inner solves use undamped successive\n-substitution. Saturation calculations search only the requested finite pressure\n-interval and can return `NOT_FOUND` or `INCONCLUSIVE`; they do not establish a\n+- a Streamlit user interface\n+\n+Near a mixture critical point, the bounded stability trials can collapse to the\n+trivial solution and falsely classify a state as stable. In the independently\n+audited 50/50 methane/propane regression at `P = Pc`, this produced an observed\n+false-stable band of approximately 7.86 K below that mixture's audited critical\n+temperature; this width is specific to that audited example and must not be\n+generalized to other fluids, compositions, or pressures, so near-critical\n+stability classifications require caution.\n+\n+The current flash and saturation inner solves use undamped successive\n+substitution. Saturation calculations search only the requested finite pressure\n+interval and can return `NOT_FOUND` or `INCONCLUSIVE`; they do not establish a\n globally complete phase diagram. Envelope tracing defaults to natural\n temperature continuation. The opt-in pseudo-arclength mode can cross regular\n geometric turns but still terminates at root-role loss or indistinguishable\ndiff --git a/docs/PROJECT_JOURNAL.md b/docs/PROJECT_JOURNAL.md\nindex 2a092b40a22df4550788454eab60a754f185a81b..f649151a93391feb2b441e556df43081248a9061\n--- a/docs/PROJECT_JOURNAL.md\n+++ b/docs/PROJECT_JOURNAL.md\n@@ -2246,11 +2246,17 @@\n or pseudocomponent implementation is included. Module 21 remains unstaged and\n uncommitted pending independent scientific-visualization review.\n \n-The two safe-defer items remain untouched: individual redundant Module 20 root-\n-continuity sub-checks are not each mutation-pinned, and the pre-existing\n-near-critical phase-stability false-stability band remains separate work.\n-\n-## Module/Stage X \u2014 Name\n+The two safe-defer items remain untouched: individual redundant Module 20 root-\n+continuity sub-checks are not each mutation-pinned, and the pre-existing\n+near-critical phase-stability false-stability band remains separate work.\n+\n+### Module 21 closing status\n+\n+Module 21 was committed at `36d9584`, was included in the final whole-repository\n+independent audit, and is accepted as part of the completed original 21-module\n+roadmap.\n+\n+## Module/Stage X \u2014 Name\n \n ### Purpose\n \n\n2026-08-24T20:24:54.707081Z ERROR codex_core::tools::router: error=exec_command failed for `\"C:\\\\windows\\\\System32\\\\WindowsPowerShell\\\\v1.0\\\\powershell.exe\" -Command \"Remove-Item -LiteralPath 'C:\\\\Users\\\\user\\\\OneDrive - American University of Beirut\\\\Desktop\\\\pvt-phase-simulator\\\\.pytest-tmp-final-release' -Recurse -Force\"`: CreateProcess { message: \"Rejected(\\\"`\\\\\\\"C:\\\\\\\\\\\\\\\\windows\\\\\\\\\\\\\\\\System32\\\\\\\\\\\\\\\\WindowsPowerShell\\\\\\\\\\\\\\\\v1.0\\\\\\\\\\\\\\\\powershell.exe\\\\\\\" -Command \\\\\\\"Remove-Item -LiteralPath 'C:\\\\\\\\\\\\\\\\Users\\\\\\\\\\\\\\\\user\\\\\\\\\\\\\\\\OneDrive - American University of Beirut\\\\\\\\\\\\\\\\Desktop\\\\\\\\\\\\\\\\pvt-phase-simulator\\\\\\\\\\\\\\\\.pytest-tmp-final-release' -Recurse -Force\\\\\\\"` rejected: blocked by policy\\\")\" }\ndiff --git a/README.md b/README.md\nindex 3dac99de2b04c84f553330e162d4b62b19fba1ea..c811ec37e5e65f1f2a10a4daa9c1b24dacbc6e2e\n--- a/README.md\n+++ b/README.md\n@@ -222,8 +222,8 @@\n \n - three-phase or multiphase flash calculations\n - accelerated, damped, or globally convergent flash algorithms\n-- exhaustive/global phase-stability certification beyond the bounded\n-  Wilson-plus-fallback Michelsen-style trials\n+- exhaustive/global phase-stability certification beyond the bounded\n+  Wilson-plus-fallback Michelsen-style trials\n - critical-locus continuation or a supported-fluid temperature-fold\n   regression (the pseudo-arclength core has generic-fold and CH4/C3\n  
… [truncated, 63362 more characters]
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
