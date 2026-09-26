# Independent audit: v2_01_d_validation_evidence_report (4th pass)

**Verdict: APPROVED.** I found nothing that blocks this package. Three minor (severity D) findings are listed at the end. None is a scientific error.

I made no changes. Every probe ran in memory, with bytecode writing turned off. The working tree is the same as the snapshot, and no frozen path differs from `a772dd6`.

## What I checked independently

**Frozen scope**
- `git diff a772dd6` over `src`, `tests`, `data`, `docs/validation`, `tools`, `app`, `pyproject.toml`, `uv.lock` and `.github` is empty.
- The only new files are `report/**` and `tests/test_validation_report.py`, plus the change to `docs/VALIDATION_FRAMEWORK.md`.
- `tests/test_validation_report.py`: 35 passed.

**Science comes from C**
- I read every COMPARED row of `comparisons.csv` (159 rows) and recomputed `signed_error = pred − ref` and, for pressure, `relative = error/ref` with plain arithmetic. There were 0 mismatches.
- I rebuilt the Worst Cases ranking myself from the CSV: pressure by |relative error|, composition by per-component |error|. It matches the rendered order exactly in all 8 groups.
  - An apparent tie-order anomaly (ch4_c3_009 lists propane before methane) is not a defect. The two values differ at about 1e-17, so the ordering follows the exact values.
- The AST scan test is meaningful. It bans `abs`, `sum`, `fsum`, `sqrt` and `mean`, and the `*`, `/`, `//` and `**` operators except on path joins. It only allows two set-difference expressions.
- Figures use Plotly axis tick formatting rather than multiplying by 100.

**Membership (S1/S2)**
- `membership.py` does three things:
  - It re-runs C's `aggregate_group` on the group and requires the result to equal C's aggregate exactly.
  - It derives contributors from C's comparison state. Metrics with unit `%` only count observations whose relative error is defined.
  - It proves each metric by re-running `aggregate_group` on the contributor cases and requiring the same value, sample count and state.
- The S2 test checks everything required:
  - MAE membership is [A, B, Z] and AARD membership is [A, B], with AARD = 2.0.
  - `ZERO_REFERENCE_DENOMINATOR` sits on case-Z's comparison and in its CSV state/reason columns, not on the AARD metric.
  - Adding case-Z to the AARD membership raises the error, and so does dropping a case from the group.

**Canonical JSON and determinism**
- I recomputed `content_sha256` myself: SHA-256 of the JSON without `volatile` and `content_sha256`, with sorted keys, compact separators, UTF-8 (`ensure_ascii=False`) and `allow_nan=False`. It matches.
- Two builds with different `run_id` and clock values give:
  - the same hash;
  - identical `comparisons.csv`;
  - identical HTML once the volatile block is masked.
- The JSON contains no NaN or Infinity.

**Pooled data (previous C-2)**
- `coverage.pooled_by_capability` now holds only the coverage block and the grouping key. There are no pooled metrics.
- The summary states "pooled accuracy is not displayed".

**Composition parity plot (previous C-1)**
- F5 now reads component order from `quantity.component_ids`, and a regression test covers it.

**Dataset roles (previous D-1)**
- `_FROZEN_ROLES` now enforces each (status, basis) pair.
- The JSON shows the frozen values, and `evaluation` is labelled DECLARED.

**Security and privacy**
- I put a hostile string (`</script><script>…`, quotes, an `<img onerror>` payload) into the case source references, failure reasons, the diagnostics interpretation and the run_id. None of it reached the HTML unescaped, and the `<script>` tag count stayed at 15.
- The only links outside the inlined plotly.js are two `https` links (doi.org and trc.nist.gov), both with `rel="noopener noreferrer"`.
- There is no `<script src>` and no CDN load. `unpkg`/`maki` strings appear only inside the inlined library.
- No absolute paths, username, hostname or institution name appear in any of the four outputs.
- The CSV formula-injection policy prefixes risky text fields with an apostrophe.

**Required wording**
- The S3 uncertainty sentence, the frozen NOT_FOUND sentence (with bold markup) and the dataset-role sentence all render verbatim.
- "95 % (as recorded)" and "not stated by the source" appear. `k=2`, "joint", "blind" and "held-out" do not.
- Historical 2U counts appear only inside the Legacy box.
- The DIRTY tree correctly shows "Not reproducible from a commit alone."
- The 283.38 K case:
  - it is kept in every primary result;
  - the callout appears in Scope and in Accuracy, with UNRESOLVED shown;
  - sensitivity shows primary and alternate values side by side with C's shifts;
  - the alternate subset excludes the case by identity.
- Model configuration separates (A) the stored artifact (80e8146, "Generating revision not embedded") from (B) the declared constants. I recomputed κ(ω) for methane (0.392217) and it matches.

## Findings

- **D-1 — One archive-verification item has no line of its own.** The design's archive-verification record includes "the ThermoML citation title states a range ending at 273 K". The declaration stores this as `citation_title_range_ends_k: 273.0`, but `html.py` never renders that field. The fact only reaches the reader through the manifest's anomaly prose ("article title and abstract state a 203 to 273 K range"), which is not the same claim.
- **D-2 — Section order contradiction (carried over, still not reported by a builder).** The HTML puts Model Configuration and Provenance after Limitations, which follows design §9. The objective lists them after Dataset Role. The code resolved this silently instead of reporting it.
- **D-3 — The frozen dataset-role sentence contains "held out".** The forbidden word is "held-out" (hyphenated), so the output literally complies. The frozen sentence and the ban are still in tension. This is informational only; the output is correct.

<ORCHESTRATOR_RESULT>
{
  "verdict": "APPROVED",
  "findings": [
    {"id": "D-1", "severity": "D", "blocks": false, "summary": "Declaration field citation_title_range_ends_k (ThermoML citation title range ending at 273 K) is never rendered as its own archive-verification item; html.py has no reference to it, and the fact is only indirectly conveyed via the manifest's anomaly prose."},
    {"id": "D-2", "severity": "D", "blocks": false, "summary": "HTML places Model Configuration/Provenance after Limitations (design section 9 order) rather than the objective's listed order; the contradiction was resolved silently rather than reported."},
    {"id": "D-3", "severity": "D", "blocks": false, "summary": "Frozen role sentence contains 'held out' while 'held-out' is forbidden; output complies literally (informational requirement tension)."}
  ],
  "safe_defer": ["D-1", "D-2", "D-3"]
}
</ORCHESTRATOR_RESULT>