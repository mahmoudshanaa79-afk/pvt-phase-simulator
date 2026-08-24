# Independent audit: final_release_doc_cleanup

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
- Name: final_release_doc_cleanup
- Declared risk: LOW
- Objective: Close the two non-blocking documentation findings from the final whole-project audit. Documentation only: change no code, test, tolerance, baseline, or data.

FINAL-D-1 (README.md): the near-critical phase-stability weakness is currently disclosed only in general terms ('no exhaustive/global phase-stability certification'). Add one or two sentences naming the specific mechanism - trivial-solution collapse in the stability trials near a mixture critical point - so a reader knows the failure is localized and predictable rather than merely theoretical. Cite the independent final audit's OBSERVED example: an approximately 7.86 K false-stable band below the audited 50/50 methane/propane critical temperature at P = Pc. You MUST present this as an observed regression example for that one audited mixture, NOT as a universal width. Do not imply the band width generalizes to other fluids, compositions, or pressures. State that near-critical stability classifications require caution. Do NOT modify phase_stability.py or any other source file.

FINAL-D-2 (docs/PROJECT_JOURNAL.md): the Module 21 section still states the module 'remains unstaged and uncommitted pending independent scientific-visualization review'. APPEND a short closing entry recording that Module 21 was committed at 36d9584, was included in the final whole-repository independent audit, and is accepted as part of the completed original 21-module roadmap. Do NOT rewrite, delete, or edit the historical 'pending review' wording - the journal is chronological and its history must remain intact.

## Scientific invariants claimed to hold
  - No source file changes: src/ is untouched.
  - No test, tolerance, or baseline changes.
  - Golden master, property CSV, and Module 17 artifacts remain byte-identical.
  - Full scientific suite still reports 1137 passed.
  - FINAL-D-1 wording must not present the 7.86 K band as universal across fluids.
  - FINAL-D-2 must append to the journal without rewriting the historical entry.
  - No claim is added that the repository does not implement.

## Repository state
- Branch: `master`
- HEAD: `89fdcbe464b6dec814a1f315959cb9160ecfc57d`
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
```
Changed files: ['README.md', 'docs/PROJECT_JOURNAL.md']

## Builder's own report — treat as an unverified claim
```
Updated only the requested documentation:

- README documents the localized near-critical trivial-solution collapse and mixture-specific observed 7.86 K example.
- Project journal records Module 21’s commit, final audit inclusion, and acceptance.
- Protected artifact hashes remain byte-identical.
- Existing `.ai` changes were untouched.

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "pytest -q: 1137 passed in 436.44s; ruff check .: All checks passed; ruff format --check .: 109 files already formatted",
  "files_changed": ["README.md", "docs/PROJECT_JOURNAL.md"],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>
```

## Diff stat
```
 .ai/workflow_state.json | 31 ++++++++++++++++++++++++++++---
 README.md               |  8 ++++++++
 docs/PROJECT_JOURNAL.md |  6 ++++++
 3 files changed, 42 insertions(+), 3 deletions(-)

```

## Full diff
```diff
diff --git a/.ai/workflow_state.json b/.ai/workflow_state.json
index dd2510a..fdff109 100644
--- a/.ai/workflow_state.json
+++ b/.ai/workflow_state.json
@@ -1,14 +1,14 @@
 {
   "project": "pvt-phase-simulator",
   "phase": "post-roadmap",
-  "workflow_status": "IDLE",
+  "workflow_status": "CLAUDE_RUNNING",
   "last_scientific_commit": "36d9584baf8ff77e1e79ad5f9ad91d0eb9fd4439",
   "last_independent_audit_commit": "f71ef10",
   "work_packages_since_audit": 0,
   "current_work_package": "final_release_doc_cleanup",
   "current_risk": "LOW",
-  "audit_required": false,
-  "audit_reason": null,
+  "audit_required": true,
+  "audit_reason": "package audit_policy=IMMEDIATE",
   "blocking_findings": [],
   "safe_defer_findings": [
     {
@@ -90,6 +90,31 @@
       "from": "LOCAL_VERIFY",
       "to": "IDLE",
       "reason": "manually stopped"
+    },
+    {
+      "from": "IDLE",
+      "to": "PLANNING",
+      "reason": "planning final_release_doc_cleanup"
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
 }
diff --git a/README.md b/README.md
index 818f1bf..662b549 100644
--- a/README.md
+++ b/README.md
@@ -234,6 +234,14 @@ The project does **not** yet implement:
 - engineering unit conversion functions
 - a Streamlit user interface
 
+Near a mixture critical point, the bounded stability trials can collapse to the
+trivial solution and falsely classify a state as stable. In the independently
+audited 50/50 methane/propane regression at `P = Pc`, this produced an observed
+false-stable band of approximately 7.86 K below that mixture's audited critical
+temperature; this width is specific to that audited example and must not be
+generalized to other fluids, compositions, or pressures, so near-critical
+stability classifications require caution.
+
 The current flash and saturation inner solves use undamped successive
 substitution. Saturation calculations search only the requested finite pressure
 interval and can return `NOT_FOUND` or `INCONCLUSIVE`; they do not establish a
diff --git a/docs/PROJECT_JOURNAL.md b/docs/PROJECT_JOURNAL.md
index cc52d09..a84b616 100644
--- a/docs/PROJECT_JOURNAL.md
+++ b/docs/PROJECT_JOURNAL.md
@@ -2250,6 +2250,12 @@ The two safe-defer items remain untouched: individual redundant Module 20 root-
 continuity sub-checks are not each mutation-pinned, and the pre-existing
 near-critical phase-stability false-stability band remains separate work.
 
+### Module 21 closing status
+
+Module 21 was committed at `36d9584`, was included in the final whole-repository
+independent audit, and is accepted as part of the completed original 21-module
+roadmap.
+
 ## Module/Stage X â€” Name
 
 ### Purpose

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
