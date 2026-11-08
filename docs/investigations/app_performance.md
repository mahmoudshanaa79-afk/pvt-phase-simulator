# App performance: measurements and the app-layer speed-up

Web session, 3 November 2026. Tool: `tools/profile_app.py`. Raw timings:
`app_performance_before.csv` and `app_performance_after.csv` in this folder,
compared with `uv run python tools/profile_app.py --compare BEFORE AFTER`.

**Machine:** Intel Xeon @ 2.80 GHz, 4 logical CPUs, Linux 6.18, Python 3.12.3
(the web session's container). Every figure is the **median of 3 runs**, with
Streamlit's caches cleared before each run unless the row says "warm".
"AppTest" rows are what a user waits for (the engine plus page rendering),
timed through Streamlit's AppTest. "Direct" rows are the same engine calls
without Streamlit. Streamlit Community Cloud machines are slower and shared,
so absolute times there will differ; the ratios hold.

## What the measurements show

1. **One action dominates: the phase envelope.** It takes about 2 to 3 minutes
   on the first run, and about 100–125 s of that is the engine's
   `calculate_phase_envelope`. Every other action takes under 5 s; page renders
   take under 0.1 s; exports and the HTML report take milliseconds.
2. **A cache hit was not free.** Running the same envelope again, with
   everything cached, still took 3.4 s. Almost all of it was
   `st.cache_data` unpickling a fresh copy of the results on every hit: about
   354,000 dataclass objects for one envelope and its saturation pair.
3. **Start-up is short.** Importing the app takes about 1.7 s and the first
   script run about 1.9 s.

## What changed (app layer only)

- **Engine results are cached with `st.cache_resource` instead of
  `st.cache_data`.** A hit now returns the stored object itself. This is safe
  because every cached result is deeply immutable (frozen dataclasses, tuples
  and frozen pydantic components), and a test walks every result to prove it.
  Keys are the complete submitted inputs (composition, temperature, pressure
  and the kij); units only change the display.
- **Bounded memory.** An envelope is about 16 MB in memory and a saturation
  pair about 7 MB, so those two caches hold 4 entries each. The flash, extended
  overlay, critical point and criticality map are each under 0.2 MB (8–16
  entries). With `st.cache_resource`, sessions computing the same case also
  share one object instead of holding a copy each.
- **The sweep is cached** (8 entries, in a small bounded store rather than
  `st.cache_resource`, because its progress bar cannot be replayed on a hit)
  with the same rules, so repeating a sweep
  is immediate. The progress callback is not part of the key.
- **The evidence-tab CSV reader cache is bounded** (8 entries).

Not changed, because the measurements do not justify it: lazy imports (start-up
is under 2 s), fragments and forms (a page rerun with results takes about
0.14 s), and the Validation figures (0.2 s).

## Before and after

| Action | Case | Before (s) | After (s) |
|---|---|---:|---:|
| RUN PHASE ENVELOPE, repeated (warm cache) | Default two-phase case | 3.40 | **0.13** |
| RUN PHASE ENVELOPE, repeated (warm cache) | Single-phase case, 20 MPa | 3.29 | **0.12** |
| RUN PHASE ENVELOPE, repeated (warm cache) | Critical-solver seed | 4.62 | **0.11** |
| RUN PHASE ENVELOPE, first run | Default two-phase case | 128.68 | 143.05 |
| RUN PHASE ENVELOPE, first run | Single-phase case, 20 MPa | 127.17 | 136.56 |
| RUN PHASE ENVELOPE, first run | Critical-solver seed | 179.11 | 170.22 |
| RUN FLASH | Default two-phase case | 0.28 | 0.26 |
| RUN CRITICAL SOLVER | Default two-phase case | 1.79 | 2.01 |
| RUN CRITICALITY MAP | Default two-phase case | 0.76 | 0.93 |
| RUN SWEEP (21 points) | Default two-phase case | 3.16 | 3.67 |
| GENERATE VALIDATION FIGURES | Default two-phase case | 0.15 | 0.16 |
| Overview with every result (exports, report) | Default two-phase case | 0.05 | 0.07 |
| First render of any page, no results | – | 0.02–0.08 | 0.02–0.07 |
| Import the app modules (fresh process) | – | 1.67 | 1.61 |
| First script run (fresh process) | – | 1.87 | 1.91 |

| Engine call (direct, no Streamlit) | Before (s) | After (s) |
|---|---:|---:|
| Phase envelope | 125.20 | 101.85 |
| Extended overlay | 9.90 | 8.58 |
| Bubble and dew at the operating temperature | 7.82 | 7.53 |
| Critical point | 1.89 | 1.50 |
| Criticality map | 0.83 | 0.64 |
| Sweep (21 points) | 3.62 | 2.77 |
| Flash | 0.17 | 0.13 |

First-run times are engine time, which this change does not touch. Their
before/after differences (up to about 10 %, both ways) are run-to-run noise on
a shared machine; the engine code is identical.

## Proof that no number changed

`tests/test_app_performance.py`:

- every cached result is deeply immutable;
- for every cached function, a cold call, a warm call and a direct uncached
  engine call give the same pickle bytes, and the warm call returns the same
  object;
- the app's stored results and its JSON and CSV exports are byte-identical
  with a cold and a warm cache, and equal to the direct engine results;
- changing any one input (composition, temperature, pressure or any kij pair)
  gives a new key and a new engine call; each shipped example has its own entry;
  a sweep key includes every request field; units change only the display;
- every cache is bounded, never holds more than its bound, and the bounds keep
  the worst case (with a factor of 3 for longer traces) under 300 MB, inside
  Streamlit Community Cloud's limit of about 1 GB.

## Where the remaining time goes (engine, proposal P9)

A cProfile of the app's `calculate_phase_envelope` call (300 K, default
mixture) shows that every corrector step runs a full saturation solve, and that
about half of the time is the engine re-validating the same three components'
parameters inside every pair calculation (4.6 million
`_validate_single_component_parameter` calls, 200 million `require_finite`
calls). The engine is frozen, so this is written up as **P9** in
`docs/ENGINE_CHANGE_PROPOSALS.md` for the owner to decide; nothing in the
engine was changed at the time. P9 was later approved and applied; see the
section below.

## After the engine speed-up (P9, 8 November 2026)

P9 (owner-approved on 8 November 2026, on the condition that every result
stays byte-identical) stops the engine from repeating validations that already
succeeded for the very same immutable inputs. `tools/engine_fingerprint.py`
hashes the complete canonical form of 801 results; all 801 are identical to
master, and the full test suite passes with no test edited.

**Machine:** Intel Xeon @ 2.10 GHz, 4 logical CPUs, Linux 6.18, Python 3.12.3.
This is a different container from the tables above, so master was measured
again on this machine before the change (`app_performance_before_p9.csv`) and
the result after it (`app_performance_after_p9.csv`). Median of 3 runs, caches
cleared before each run.

| Action | Case | Master (s) | After P9 (s) |
|---|---|---:|---:|
| RUN PHASE ENVELOPE, first run | Default two-phase case | 82.13 | **34.64** |
| RUN PHASE ENVELOPE, first run | Single-phase case, 20 MPa | 77.70 | **37.84** |
| RUN PHASE ENVELOPE, first run | Critical-solver seed | 106.94 | **48.43** |
| RUN PHASE ENVELOPE, repeated (warm cache) | Default two-phase case | 0.10 | 0.10 |
| RUN FLASH | Default two-phase case | 0.24 | 0.14 |
| RUN CRITICAL SOLVER | Default two-phase case | 1.36 | 0.49 |
| RUN CRITICALITY MAP | Default two-phase case | 0.51 | 0.22 |
| RUN SWEEP (21 points) | Default two-phase case | 2.10 | 0.86 |
| Import the app modules (fresh process) | – | 1.17 | 1.07 |

| Engine call (direct, no Streamlit) | Master (s) | After P9 (s) |
|---|---:|---:|
| Phase envelope | 68.86 | 30.53 |
| Extended overlay | 4.87 | 1.80 |
| Bubble and dew at the operating temperature | 4.71 | 2.09 |
| Critical point | 1.13 | 0.35 |
| Criticality map | 0.45 | 0.13 |
| Sweep (21 points) | 1.94 | 0.73 |

The first envelope of a case is now about **2.1 to 2.4 times faster**: about
half a minute to a minute here instead of 1.3 to 1.8 minutes. The public server
is shared and slower, so it will take longer there. The remaining time is the
cubic-root arithmetic itself, which P9 does not change. Two further speed-ups
that would change recorded results were measured on a scratch copy and are
written up as **P10** in `docs/ENGINE_CHANGE_PROPOSALS.md` for the owner.
