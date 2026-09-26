# Independent audit: V2-01-D validation evidence report

**Verdict: NOT_APPROVED.** The core science is sound: membership proofs, keeping diagnostics separate from production output, and leaving all formulas to C all held under my own probes. But two gates will fail on CI or after commit, the test suite is missing a large part of the required list, and one S3 rule is broken in the CSV export.

## How I checked
- I ran mypy, the report tests (13 passed) and the CLI, writing to `%TEMP%\d_audit_out`, outside the repo.
- I parsed the generated HTML (with the plotly bundle removed), the JSON and both CSVs.
- I wrote my own probes:
  - planted a sentinel in the adapter's real `prediction.diagnostics`;
  - forced git to be unavailable;
  - ran an all-zero-reference group through the membership proof.
- Protected artifacts are unchanged. The only tracked change outside `.ai/` is `docs/VALIDATION_FRAMEWORK.md`, which is allowed.

## What held up (with evidence)
- **S1/S2 membership:**
  - `membership.py` re-runs C's `aggregate_group` on each group and requires the result to equal C's aggregate exactly.
  - For each metric it re-runs on the contributing cases and requires the same value, sample count and state.
  - The S2 test reproduces MAE = {A, B, Z} and AARD = {A, B} (value 2.0).
  - A tampered AARD list that includes case-Z raises `EvidenceInconsistencyError`, and so does a group with a case removed.
  - My extra probe: with only case-Z, the relative metrics are UNDEFINED with sample count 0 and no contributors, and the proof passes. It does not crash.
- **Diagnostics stay separate:** my sentinel, planted in the real `prediction.diagnostics`, appeared only in the HTML `diagnostics` section and the JSON `diagnostics` key. It was absent from both CSVs and every production section.
- **No D-side formulas:** grep finds no arithmetic on errors or metrics. The worst-case ranking uses C's `absolute_relative_error` and per-component `absolute_error`. F2–F4 plot C's `relative_error`, and Plotly's `%` tick format only changes the display.
- **Numbers agree with the legacy results:**
  - Solver coverage: bubble 31 converged of 40 (9 not found); dew 22 of 40 (4 not found, 14 inconclusive).
  - Accuracy: CH4+C2H6 bubble AARD 0.45469 % over 11 compared of 17; CH4+C3H8 dew AARD 36.6682 % over 7 compared of 23.
  - Sensitivity: bubble goes from 20 to 19 cases and dew from 7 to 6, with the primary values shown unchanged.
- **Required wording and forbidden content:**
  - The frozen wording (NOT_FOUND, dataset role, reference-only uncertainty, "95 % (as recorded)", "not stated by the source") is all present.
  - The article-level check is shown as UNRESOLVED.
  - The HTML body contains none of: "blind", "held-out", NaN, Infinity, "k=2", "joint", PASS/FAIL badges.
  - There are no absolute paths or usernames, and no external `src`, `link` or `img`.
  - The ledger has 80 rows (53 converged, 13 not found, 14 inconclusive).

## Findings

**F-1 (C, blocks): the mypy gate fails.**
- `report/figures.py:483`: `pio.to_html` returns `Any`, which mypy rejects as `no-any-return`.
- `.github/workflows/quality.yml` runs `mypy src app`, so CI will be red. This is the orchestrator's FAIL(1).

**F-2 (C, blocks): one HTML test only passes because the working tree is dirty.**
- `test_html_is_self_contained_scoped_and_responsive` always expects the banner "Not reproducible from a commit alone."
- `html.py:969` only prints that banner when the tree state is DIRTY.
- On a clean CI checkout, or when the report is regenerated from the committed revision (S4), the test will fail.
- The CLEAN, DIRTY and UNKNOWN branches have no tests of their own.

**F-3 (C, blocks): required tests are missing or too weak.** The objective and design §13 require these, and none exist:
- OTHER_FAILURE;
- reference-unavailable versus uncertainty-unavailable;
- undefined or empty metrics never shown as 0;
- sensitivity keeping the primary values;
- dirty and unknown tree states;
- protected files unchanged;
- very long citations and malformed URLs;
- a declared model configuration that disagrees with the engine.

Two of the existing tests are too weak:
- The diagnostics-leak test plants its sentinel in `DiagnosticEvidence`, not in `prediction.diagnostics`. It only checks that the sentinel appears somewhere in the HTML, so it would still pass if the sentinel leaked into a production table.
- The formula scan only bans `fsum` and `sqrt`, so it would not catch `(p - r) / r`.

My probes show the current behaviour is correct; the gap is that nothing would catch a regression.

**F-4 (C, blocks): `comparisons.csv` leaves `coverage_factor` blank on all 240 rows.**
- This includes the 115 rows where uncertainty was ASSESSED.
- No state or reason column sits beside it.
- This breaks S3 ("never blank") and design §9 ("An empty cell always has a state/reason column beside it").
- `standard_normalized_residual` and the tolerance kind, value and citation columns are also blank on every row. Their emptiness is only explained indirectly by other columns.

**F-5 (D): an unknown git state produces a fake commit SHA.**
- When git is unavailable, `_revision` returns `"0"*40`, which is then rendered and exported as `git_commit_sha`.
- The tree state is correctly shown as UNKNOWN, but the SHA should also say UNKNOWN.
- Similarly, `_package_version` quietly falls back to `"0.1.0"`.

**F-6 (D): the F7 caption says "N compared" but counts converged cases.** Converged and compared are not the same count in general. They happen to be equal for Module 17.

**F-7 (D): the sensitivity table shows pressure MAE, bias and RMSE in raw Pa with no unit.** The rest of the HTML shows pressure in MPa.

**F-8 (D): the CSV formula-injection guard only covers `= + - @`.** Leading tab or carriage-return characters are not neutralised.

**Conflict between the objective and the design (reported, not a defect).** The objective's section list puts Provenance and Model Configuration right after Dataset Role. Design §9 puts them after the diagnostics box. The build follows the design order.

<ORCHESTRATOR_RESULT>
{
  "verdict": "NOT_APPROVED",
  "findings": [
    {"id": "F-1", "severity": "C", "blocks": true, "summary": "mypy fails at report/figures.py:483 (no-any-return from pio.to_html); CI quality.yml runs mypy src app, so the gate is red."},
    {"id": "F-2", "severity": "C", "blocks": true, "summary": "test_html_is_self_contained_scoped_and_responsive always expects the DIRTY-only banner 'Not reproducible from a commit alone.'; it fails on a clean checkout (CI, and S4 regeneration from the committed revision). CLEAN/DIRTY/UNKNOWN are not tested separately."},
    {"id": "F-3", "severity": "C", "blocks": true, "summary": "Required tests are missing: OTHER_FAILURE, reference- vs uncertainty-unavailable, undefined never 0, sensitivity keeps primary values, dirty/unknown tree, protected files unchanged, long/malformed citations, declaration-vs-engine mismatch. The diagnostics sentinel is not planted in prediction.diagnostics and is not checked absent from production sections; the formula scan only bans fsum/sqrt."},
    {"id": "F-4", "severity": "C", "blocks": true, "summary": "comparisons.csv leaves coverage_factor blank on all 240 rows (including 115 ASSESSED rows) with no state/reason column beside it, breaking S3 'never blank' and design section 9."},
    {"id": "F-5", "severity": "D", "blocks": false, "summary": "When git is unavailable, git_commit_sha is rendered and exported as forty zeros (a fake SHA); package version silently falls back to '0.1.0'."},
    {"id": "F-6", "severity": "D", "blocks": false, "summary": "F7 caption labels the converged count as 'compared'."},
    {"id": "F-7", "severity": "D", "blocks": false, "summary": "Sensitivity table shows pressure MAE/bias/RMSE in raw Pa with no unit, unlike the MPa display elsewhere."},
    {"id": "F-8", "severity": "D", "blocks": false, "summary": "CSV formula-injection guard does not cover leading tab or carriage-return characters."}
  ],
  "safe_defer": ["F-5", "F-6", "F-7", "F-8"]
}
</ORCHESTRATOR_RESULT>