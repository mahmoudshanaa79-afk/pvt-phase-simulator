# P10 survey: the app's envelope with and without the global fallback

**Investigation only (web session, 15 November 2026).** No engine or app
setting was changed. The owner asked for this wider survey of proposal P10,
option (b), before any decision (`docs/ENGINE_CHANGE_PROPOSALS.md`, P10).

## Question

Option (b) would set `allow_global_fallback=False` in the app's envelope
settings. On six states it gave identical envelope points and was about a
quarter faster. Does that hold on the 16 cases of
`tools/run_envelope_survey.py`, or does the fallback ever rescue a step?

## Method

`tools/run_p10_survey.py` runs the Phase Envelope page's own calculation (the
body of its cached function, with the app's settings) twice per case:

- **on:** the shipped settings, `allow_global_fallback=True`;
- **off:** the same settings with `allow_global_fallback=False`, set inside the
  survey process only.

It compares each branch's accepted points:
- the count;
- exact equality of their values (temperature, pressure, incipient
  composition, log K, separations);
- exact equality of their complete records, as `tools/engine_fingerprint.py`
  writes them.

It also records the termination reasons, how many accepted points came from
the global fallback, how often the fallback was tried, the rejected attempts
and the wall time.

The 16 cases are the three shipped examples and 13 more binaries and
ternaries. The first two shipped examples share composition and temperature,
and the app's envelope depends on nothing else, so their envelopes are the
same. The raw results are in `docs/investigations/p10_survey.csv`;
`tests/test_p10_survey.py` recomputes every number below from it.

## Result

All 16 cases ran; nothing was extrapolated.

- **Accepted points:** 365 accepted points with the fallback and
  365 without, on 32 branches. They are identical on
  32 of 32 branches, in their values and in
  their complete records. The largest temperature and pressure differences are
  exactly zero.
- **Termination:** the termination reasons agree on
  32 of 32 branches.
- **The fallback never rescued a step.** With the fallback on, the global
  fallback produced 0 accepted points. It was
  tried 56 times, and every try failed. Without it,
  those failed tries are simply not made, so the rejected attempts fall from
  428 to 372. That shorter list of rejected
  attempts is the only difference in the result objects.
- **Time:** 346.7 s with the fallback and 274.9 s
  without, in total over the 16 cases: 20.7 % less. The
  saving comes from the 10 cases where the fallback was tried: 315.2 s →
  239.6 s. In the 6 cases where it was never tried, both runs do exactly the
  same work. Their times (31.5 s → 35.3 s in total, up to 3.0 s apart in one
  case) show the run-to-run noise of this set-up. The survey ran as three
  processes in parallel on a four-core machine. Each case ran
  "on" and then "off" in the same process, so the two times of a case are
  comparable; the absolute times are not a benchmark.

| Case | Points on/off (bubble, dew) | Identical points | Reasons (bubble, dew) | Fallback points / tries (on) | Rejected on/off | Time on/off (s) |
|---|---|---|---|---|---|---:|
| shipped: Default two-phase-oriented case | 15/15, 11/11 | yes | maximum_points, near_critical | 0 / 0, 0 / 3 | 0/0, 23/20 | 26.6 / 19.9 |
| shipped: Known single-phase case at 300 K and 20 MPa | 15/15, 11/11 | yes | maximum_points, near_critical | 0 / 0, 0 / 3 | 0/0, 23/20 | 26.9 / 20.9 |
| shipped: Audited critical-solver seed | 15/15, 10/10 | yes | maximum_points, near_critical | 0 / 0, 0 / 5 | 0/0, 37/32 | 36.1 / 26.7 |
| C1/C3 50/50, warm start | 14/14, 9/9 | yes | near_critical, near_critical | 0 / 2, 0 / 5 | 14/12, 37/32 | 44.5 / 32.4 |
| C1/C3 10/90 | 9/9, 10/10 | yes | target_reached, target_reached | 0 / 0, 0 / 0 | 0/0, 1/1 | 4.2 / 4.4 |
| C1/C3 30/70 | 14/14, 10/10 | yes | target_reached, target_reached | 0 / 2, 0 / 0 | 14/12, 2/2 | 20.3 / 17.2 |
| C1/C3 70/30 | 15/15, 10/10 | yes | maximum_points, target_reached | 0 / 0, 0 / 0 | 0/0, 2/2 | 9.5 / 12.5 |
| C1/C3 90/10 | 12/12, 11/11 | yes | near_critical, near_critical | 0 / 2, 0 / 5 | 15/13, 40/35 | 29.3 / 22.1 |
| C2/C3 30/70 | 10/10, 10/10 | yes | target_reached, target_reached | 0 / 0, 0 / 0 | 1/1, 1/1 | 2.5 / 2.5 |
| C2/C3 70/30 | 13/13, 10/10 | yes | near_critical, target_reached | 0 / 4, 0 / 0 | 29/25, 2/2 | 6.6 / 6.6 |
| C1/C2 50/50 | 13/13, 9/9 | yes | near_critical, near_critical | 0 / 4, 0 / 5 | 29/25, 37/32 | 35.3 / 30.3 |
| C1/C2/C3 40/30/30 | 15/15, 11/11 | yes | maximum_points, near_critical | 0 / 3, 0 / 5 | 21/18, 37/32 | 52.5 / 38.9 |
| C1/C3 20/80 | 9/9, 10/10 | yes | target_reached, target_reached | 0 / 0, 0 / 0 | 0/0, 1/1 | 4.7 / 4.6 |
| C2/C3 50/50 | 10/10, 10/10 | yes | target_reached, target_reached | 0 / 0, 0 / 0 | 1/1, 1/1 | 3.3 / 3.4 |
| C1/C2/C3 30/40/30 | 10/10, 9/9 | yes | near_critical, near_critical | 0 / 3, 0 / 5 | 21/18, 37/32 | 37.1 / 24.6 |
| C1/C3 80/20 | 15/15, 10/10 | yes | maximum_points, target_reached | 0 / 0, 0 / 0 | 0/0, 2/2 | 7.3 / 7.9 |

## What this does not show

- Sixteen cases are not every case. A state where the fallback rescues a step
  may exist; this survey found none, and neither did the six states measured
  for P10. If (b) is adopted, an envelope that needed the fallback would stop
  early, with the engine's own termination reason, rather than give a wrong
  point.
- The exported envelope objects would change: the rejected-attempt records
  would be shorter. The plotted envelope and every accepted point would not.

## Recommendation

Option (b) is safe on every case tested so far, and it saves about a fifth of
the envelope time where the fallback is tried. The owner can approve it as a
one-line change to the app's envelope settings, with a test that pins this
survey's identity. Without that approval nothing changes, and the app keeps the
fallback. Option (a), skipping the boundary walk, is still not recommended.
