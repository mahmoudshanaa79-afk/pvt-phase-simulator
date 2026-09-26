# Independent audit: V2-01-D validation evidence report

**Verdict: CONDITIONAL.** I found no blocking defect. The core guarantees of the package hold when checked directly against the code and a real generation run: C owns the science, membership is proven per metric, diagnostics are isolated, output is deterministic, and the frozen paths are unchanged. I found one latent correctness defect in a production figure and four minor issues.

I did not modify, stage or commit anything. The plan-file write was refused because Write is disabled in this session, so this audit exists only in this message. My probes were throwaway scripts in `/tmp`. Everything else ran in memory, with no artifacts written.

## What I checked and confirmed

- **Frozen paths.** `git status` shows no change under the engine, data, `docs/validation`, `tests/golden_master`, the A/B/C modules, the app, tools, `pyproject.toml`, `uv.lock` or `.github`. `tests/test_validation_report.py` ran: 32 passed.
- **Real Module 17 generation** (in memory):
  - 8 per-system aggregates, 4 PER_CASE_VECTOR / MEAN_ABS_COMPONENT aggregates and 4 pooled coverage blocks.
  - 80 ledger rows. 240 comparison rows, which is 80 × (1 pressure + 2 components).
  - The JSON has exactly the 18 top-level keys that design §9 lists.
- **Numbers match the protected legacy summary.** CH4+C3H8 dew AARD is 36.668237970426496 with n = 7. Coverage is 23 total = 7 converged + 2 not found + 14 inconclusive. CH4+C2H6 bubble AARD is 0.45469 and composition MAE is 0.00370912 over 22 observations. Pressure within 1U is 10 of 11 and 1 of 7.
- **Membership (S1).** `membership.py` re-runs C's `aggregate_group` on each group and requires frozen-dataclass equality. It also re-runs on each metric's contributor subset and requires that metric's value, state and sample_count to be reproduced.
  - Contributors come from C's COMPARED state. Percent metrics use only a defined C `relative_error`.
  - Tamper tests exist at group level (`comparisons[:-1]`) and metric level (case-Z added to AARD). Both raise.
  - I also probed a group in which every case failed: all metrics are UNDEFINED / NO_USABLE_OBSERVATIONS with 0 contributors, and the proof still succeeds rather than crashing.
- **S2 synthetic test.**
  - MAE contributors are [A, B, Z] and AARD contributors are [A, B], giving AARD 2.0 over 2.
  - ZERO_REFERENCE_DENOMINATOR is kept on case-Z's comparison and in its CSV state/reason columns.
- **No independent science in D.** The AST test is stricter than required: it bans `*`, `/`, `**`, `//`, and `-` apart from two set differences, plus `abs`/`sum`/`fsum`/`sqrt`/`mean`. Figure errors come from C's `errors`. Percentages are produced by format specifiers only.
- **Determinism.** I ran two generations with different run_id and clock values:
  - `content_sha256` is identical in both, and I recomputed it independently from the canonical bytes.
  - Both CSVs are byte-identical.
  - The HTML differs only in the run/timestamp line.
- **Wording.** Every frozen sentence is present:
  - the reference-only uncertainty statement;
  - "not stated by the source";
  - "95 % (as recorded)";
  - the NOT_FOUND disclaimer;
  - the dataset-role sentence;
  - the RETROSPECTIVE DIAGNOSTICS heading;
  - the 283.38 K callout with UNRESOLVED.
- **Forbidden content.**
  - "blind" and "held-out" never appear.
  - "PASS", "FAIL", "joint", "NaN" and "http://" appear only inside the inlined plotly.js runtime.
  - "2U" appears only in the legacy section.
  - Pooled accuracy is not shown; pooled data is used only for coverage and captions.
- **Privacy and security.**
  - No absolute paths or usernames appear in any output.
  - Links are https-only, validated, and carry `rel="noopener noreferrer"`.
  - `</script` is neutralized in the Plotly runtime, and Plotly's JSON encoder escapes `<`, `>` and `/`.
  - The diagnostic sentinel appears only in the diagnostics section.
- **Tree state.** It is DIRTY in the current worktree, and the "Not reproducible from a commit alone." banner renders. UNKNOWN is returned when git fails.

## Findings

**C-1 (C, not blocking) — F5 mislabels components when the reference order differs from the case order.**
- In `figures.py` `_composition_parity`, the output of `align_values` is in the reference value's component order. The code pairs it with `case.component_ids` using `dict(zip(case.component_ids, reference))`.
- C only requires the reference to have the same *set* of components as the case, not the same order. So this trusts array position, which V2-01-C forbids.
- I confirmed it with a probe that reversed one bubble case's reference composition. The ethane subplot then plotted 0.8667, which is methane's value.
- Module 17 is not affected today: 0 of 80 cases have a different order. The comparisons CSV and F6 both correctly use `comparison.component_ids`.

**D-1 (D) — Frozen dataset-role statuses are not enforced.**
- `declarations.py` only checks that each status and basis is in its allowed set. A declaration that set `held_out_from_development` to USED would load, and would contradict the hard-coded rendered sentence.
- Only `parameter_fitting` is tested.
- `evaluation` is labelled DERIVED, but it is a static declaration and nothing derives it at generation time. Design §7's table says "declared".

**D-2 (D) — Unreported contradiction in HTML section order.**
- The objective lists Provenance and Model Configuration before Dataset Conditions.
- Design §9 (line 306) puts them after the diagnostics box.
- The build follows the design. There was no builder report to flag the contradiction.

**D-3 (D) — Uncertainty table rows lack C's reason.** The dew MOLE_FRACTION rows show "NOT ASSESSABLE" with em-dashes but not C's reason, NO_REFERENCE_UNCERTAINTY. The reason does appear in the Unavailable section and in the CSV.

**D-4 (D) — F2–F4 captions can overstate the plotted count.** The captions report C's compared count, but points whose relative error is undefined are skipped. The caption would then overstate how many points are plotted. This is latent: Module 17 has no zero-pressure references.

<ORCHESTRATOR_RESULT>
{
  "verdict": "CONDITIONAL",
  "findings": [
    {"id": "C-1", "severity": "C", "blocks": false, "summary": "figures.py F5 _composition_parity zips align_values output (reference component order) with case.component_ids, trusting array position; a reference vector legally permuted relative to the case mislabels components in the production parity figure (confirmed by probe; Module 17 currently unaffected, 0/80 mismatches). Use comparison.component_ids / reference.component_ids as the CSV and F6 do."},
    {"id": "D-1", "severity": "D", "blocks": false, "summary": "Frozen dataset-role statuses are not enforced in declarations.py (only membership in the allowed sets is checked; only parameter_fitting is tested). A declaration with held_out_from_development=USED would load and contradict the rendered sentence. evaluation basis is labelled DERIVED although it is a static declaration and design section 7 says declared."},
    {"id": "D-2", "severity": "D", "blocks": false, "summary": "HTML section order follows design section 9 (Model Configuration/Provenance after diagnostics), contradicting the objective's listed order; the contradiction was not reported."},
    {"id": "D-3", "severity": "D", "blocks": false, "summary": "Uncertainty table shows dew MOLE_FRACTION as NOT ASSESSABLE without C's reason (NO_REFERENCE_UNCERTAINTY) in that row; the reason appears elsewhere (Unavailable section, CSV)."},
    {"id": "D-4", "severity": "D", "blocks": false, "summary": "F2-F4 captions report C's compared count while points with undefined relative error are omitted, so the caption could overstate plotted points (latent; no zero-reference pressures in Module 17)."}
  ],
  "safe_defer": ["C-1", "D-1", "D-2", "D-3", "D-4"]
}
</ORCHESTRATOR_RESULT>