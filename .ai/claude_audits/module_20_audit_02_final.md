# Module 20 — Second and Final Independent Audit (correction pass)

- **Auditor:** Claude (independent adversarial)
- **Audited tree:** HEAD `47da6f9` + corrected uncommitted Module 20
- **Committed as:** `b03050c` (Add mixture critical-point solver)
- **Report artifact:** https://claude.ai/code/artifact/91ba085c-9188-4655-a0a8-be87d59cbb44
- **Verdict:** `APPROVED — MAY COMMIT MODULE 20 AND PROCEED TO MODULE 21`

## Correction status

| ID | Status | Confirming mutation |
|---|---|---|
| C-1 | **CLOSED** | drop raw \|C\| gate -> KILLED (1 failed, 26 passed) |
| C-2 | **CLOSED** | disable convergence comparison -> KILLED; vacuous threshold -> KILLED |
| C-3 | **CLOSED** | disable cross-T/P root continuity -> KILLED (1 failed, 37 passed) |

## Independently recomputed evidence

- **Aliasing control** `sin(1000u)`: recomputed with own Richardson. Accepts at
  h=6.25e-5 after 4 reductions; derivative 999.999968215, error 0.162721,
  threshold 0.200001. Derivative improves monotonically as h shrinks.
- **Unresolved control:** 9 attempts, max error ratio 1991.55, no Jacobian accepted.
- **Gate does real work:** seed 300 K / 5 MPa previously ran at h=1e-3 with stored
  error 6.56; now steps through h in {1e-3, 5e-4, 2.5e-4}, max error 0.408.
- **Maxwell:** 200 K / 330900.046699 Pa, roots 0.0111654 / 0.0599429 / 0.9206251;
  all five Maxwell loci rejected as root-continuity failures.
- **Legitimate path unaffected:** all 24 stencil samples re-walked, single root, index 0.
- **No regression:** Tc/Pc/lambda/C/norm/history/conditions bit-identical. 140-seed
  sweep -> 22 converged, all 22 on the verified point, zero spurious.
- **Baselines:** golden `530C667A...`, property `C6F6BA9A...` (9 VERIFIED / 0 PROVISIONAL),
  Module 17 trio all unchanged. 1098 tests, ruff, format (81 files), mypy (21 files),
  compileall all pass.

## Findings

No Category A, B, or C. Two Category D recorded as safe-defer: **M20-D-1**
(root-continuity sub-checks mutually redundant, diagnostic-quality only) and
**M20-D-2** (pre-existing `phase_stability.py` near-critical band).
