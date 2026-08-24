# Work order: final_release_doc_cleanup

## Repository state
- Branch: `master`
- HEAD: `ccd6af8bc5f4db452ba0f4d6ac2c40763f03139e`
- Working tree: DIRTY — .ai/workflow_state.json

## Objective
Close the two non-blocking documentation findings from the final whole-project audit. Documentation only: change no code, test, tolerance, baseline, or data.

FINAL-D-1 (README.md): the near-critical phase-stability weakness is currently disclosed only in general terms ('no exhaustive/global phase-stability certification'). Add one or two sentences naming the specific mechanism - trivial-solution collapse in the stability trials near a mixture critical point - so a reader knows the failure is localized and predictable rather than merely theoretical. Cite the independent final audit's OBSERVED example: an approximately 7.86 K false-stable band below the audited 50/50 methane/propane critical temperature at P = Pc. You MUST present this as an observed regression example for that one audited mixture, NOT as a universal width. Do not imply the band width generalizes to other fluids, compositions, or pressures. State that near-critical stability classifications require caution. Do NOT modify phase_stability.py or any other source file.

FINAL-D-2 (docs/PROJECT_JOURNAL.md): the Module 21 section still states the module 'remains unstaged and uncommitted pending independent scientific-visualization review'. APPEND a short closing entry recording that Module 21 was committed at 36d9584, was included in the final whole-repository independent audit, and is accepted as part of the completed original 21-module roadmap. Do NOT rewrite, delete, or edit the historical 'pending review' wording - the journal is chronological and its history must remain intact.

## Allowed files
  - `README.md`
  - `docs/PROJECT_JOURNAL.md`

## Files you must NOT modify
  - `src/pvt_phase_simulator`
  - `tests`
  - `data`
  - `tests/golden_master/baseline.csv`
  - `docs/validation`

## Protected artifacts — never regenerate
  - `tests/golden_master/baseline.csv` — SHA256 530C667AA70EF1EA182F4EDB98624A0A9B9908F149354276CDAC44A87EA7D2BE
  - `data/component_properties.csv` — SHA256 C6F6BA9AE9C2F4C7F257BBC09A75DF0D7065255868AA46BF3E8C81AC5A8B9B3A
  - `docs/validation/module17_vle_validation.csv` — SHA256 B14728D51AAC06AF38FC4F4E5F408942B253FEBE32D3E12EC26E9623CFA42482
  - `docs/validation/module17_vle_validation_summary.json` — SHA256 5B120B77BF05567FCC6A0EE0D0054C6D1DEBA35FE26A7C837352C92017D24870

## Scientific invariants that must continue to hold
  - No source file changes: src/ is untouched.
  - No test, tolerance, or baseline changes.
  - Golden master, property CSV, and Module 17 artifacts remain byte-identical.
  - Full scientific suite still reports 1137 passed.
  - FINAL-D-1 wording must not present the 7.86 K band as universal across fluids.
  - FINAL-D-2 must append to the journal without rewriting the historical entry.
  - No claim is added that the repository does not implement.

## Required tests
  - `.venv/Scripts/python.exe -m pytest -q`

## Required quality gates
  - `.venv/Scripts/python.exe -m ruff check .`
  - `.venv/Scripts/python.exe -m ruff format --check .`

## Rules
- Do NOT weaken a test to make it pass. Do not loosen a tolerance, edit an
  expected value to match output, delete a test, swallow an exception, or
  regenerate a baseline. Any of those is a blocking failure.
- Do NOT commit, stage, reset, or clean. The orchestrator owns git.
- Do NOT write your own audit — an independent auditor reviews your work.
- Keep the change within the objective; no unrelated cleanup.

## Required final output

End your reply with exactly one machine-readable block:

<ORCHESTRATOR_RESULT>
{
  "status": "COMPLETE",
  "tests_claimed": "<what you ran and what it reported>",
  "files_changed": ["<path>", "..."],
  "ready_for_local_verification": true
}
</ORCHESTRATOR_RESULT>

`status` must be COMPLETE, BLOCKED or FAILED. The orchestrator re-runs every
check locally, so an inaccurate claim here will simply be caught.
