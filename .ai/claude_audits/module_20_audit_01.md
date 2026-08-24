# Module 20 — First Independent Audit

- **Auditor:** Claude (independent adversarial)
- **Audited tree:** HEAD `47da6f9da8361f2efecd6d0d71aeaac38c3f4359` + uncommitted Module 20
- **Committed as:** `b03050c` (Add mixture critical-point solver)
- **Report artifact:** https://claude.ai/code/artifact/d566199c-b9fe-4e7c-8935-002960c7d1b9
- **Verdict:** `CONDITIONALLY APPROVED — CORRECTIONS REQUIRED BEFORE COMMIT`

## Independent scientific confirmation

An 80-digit `Decimal` Peng-Robinson reference sharing no code with the repository
(own transcendentals, own trigonometric/Cardano cubic solver, own Gibbs-lowest root
selection) was solved from a deliberately different seed (300 K / 6 MPa) using the
**classical binary criticality conditions** `g''(x)=0 AND g'''(x)=0`, bypassing the
projected-Hessian / tangent-basis / eigenmode machinery entirely.

| Quantity | Independent | Production | Relative |
|---|---|---|---|
| Tc | 321.58291831086 K | 321.5829183194 K | 2.7e-11 |
| Pc | 8534443.23488 Pa | 8534443.23606 Pa | 1.4e-10 |

Corroborated by three structural signatures: g'' sign inversion exactly at Tc;
continuous closure of the two-phase region onto the feed (min TPD -5.42e-04 ->
-1.03e-05 -> -7.00e-08 -> 0, argmin w1 0.595 -> 0.531 -> 0.508 -> 0.500);
transversal sign crossing of both residuals.

## Findings

| ID | Cat | Summary | Blocks |
|---|---|---|---|
| C-1 | C | Raw cubic tolerance load-bearing (cubic_scale up to 60.1 => scaled-norm gate alone admits \|C\| <= 6.0e-05) but not pinned by any test; mutation SURVIVED. | YES |
| C-2 | C | Richardson error estimate computed, stored, never thresholded; base_step never reduced across 61 iterations; a Jacobian with error 6.56 was accepted. | YES |
| C-3 | C | Root-branch continuity not asserted across the T/P stencil; reachable at the Maxwell locus (Z(+h)=0.0112 vs Z(-h)=0.9207). | YES |
| D-1 | D | Pre-existing 7.86 K near-critical false-stable band in `phase_stability.py`. | NO |
