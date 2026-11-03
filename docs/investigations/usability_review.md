# Usability review of the OpenPhase app

Web session, 3 November 2026. I reviewed every page twice: as a first-time
student following the app with no instructions, and as an engineer running a
case and reading its results.

**Method**
- The app ran locally at 1280 × 900 (desktop) and 390 × 844 (phone).
- Each page was captured with Playwright before and after a calculation, with
  the system colour scheme set to light and to dark.
- The page code was read for wording, empty states, progress feedback and
  units.
- Timings come from `docs/investigations/app_performance.md`.

**Severity**
- **High:** a user is likely to be misled or to think the app is broken.
- **Medium:** a user has to guess or search.
- **Low:** polish.

High and medium findings are fixed in the same pull request as this review.
Each fix has an AppTest assertion in `tests/test_app_usability.py`.

## What already works

- No page scrolls horizontally at 390 px.
- Plots keep their legends below the axes on narrow screens.
- Every plot axis states its unit.
- Every action over about 1 s shows progress (`st.status`, `st.spinner` or the
  sweep progress bar).
- Errors say what is wrong and keep the engine's own status and reason.
- Every input has a label.
- Learn mode and the kij fields have help text.
- The theme is fixed to the light palette, so a dark operating-system setting
  does not reduce contrast.

## Findings

| # | Severity | Page | What happens | Fix |
|---|---|---|---|---|
| 1 | High | Phase Envelope | The running status says "Typical first run: about 20–30 seconds". Measured: about 2–3 minutes here, and longer on the shared Cloud server. A user is likely to think the app has hung. | The status now says the first run of a case can take a few minutes, and that the same case afterwards is answered from the cache at once. |
| 2 | High | Overview | After RUN FLASH, the result appears below the long "Model and limitations" panel, so nothing visible changes at the top of the page. Before any run, a first-time user sees that panel and no hint of what to do. | Before a result, a short "Start here" box comes first: pick an example or enter a case, press RUN FLASH, then use the other pages. After a result, the result comes first and the model panel follows it. |
| 3 | Medium | All (phone) | The sidebar opens expanded on a phone and covers the whole page. | `initial_sidebar_state="auto"`: expanded on a desktop, collapsed on a phone. |
| 4 | Medium | Phase Envelope, Critical Point, Sweeps | The empty states say only what is missing ("No calculated envelope is available."). The lock caption says "Submit RUN FLASH" without saying where RUN FLASH is, and on a phone the sidebar is hidden. | Each empty state now names the button to press, and the lock caption says that RUN FLASH is in the sidebar. |
| 5 | Medium | Overview | The phase-composition table shows unrounded values (41.08891351876942) with no unit. Its intended format, `%.6g mol %`, has an unescaped `%`, so Streamlit ignores it. | The format is now `%.6g mol %%`, so values show 6 significant figures with "mol %", like the metrics. Exports keep full precision. |
| 6 | Medium | Overview | The phase-split bar distinguishes liquid from vapour by colour only. | A caption under the bar states both fractions in words ("Liquid 0.822955 · Vapor 0.177045"), using the same values as the metrics. |
| 7 | Medium | Learn mode | The four teaching labs are not linked anywhere in the app. | Learn mode lists the labs with links to the repository. |
| 8 | Low | Downloads | File names mix `pvt-current-case.*`, `pvt-engineering-sweep.csv` and `openphase-*`. | Not changed. Existing tests and users' scripts may rely on the names. Recorded for the owner. |
| 9 | Low | Status tables (phone) | In the three-column tables, the third column ("Units / meaning", which holds the status, reason and codes) is off-screen until you scroll inside the table. | Not changed. The table scrolls, and the same information appears in the plain-language lines below each table. |
| 10 | Low | Validation | The direction control reads "bubble" / "dew" in lower case, while other pages capitalise. | Not changed. Its value is part of the page state, so cosmetic only. |
| 11 | Low | Phase Envelope | The operating point is described in words but not marked on the plot. | Not changed. A candidate for a later presentation change. |
| 12 | Low | All | A browser reload starts a new session and clears every result (standard Streamlit behaviour). | Not changed. "Save or load case" keeps the inputs. |
