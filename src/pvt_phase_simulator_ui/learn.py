"""Optional Learn mode: short explanations and checked exercises for each page.

Learn mode adds teaching text only. It never runs a calculation, changes an
input, or alters a result. Every number quoted in an exercise was produced with
this application's unchanged engine for the stated case (Peng-Robinson, kij = 0)
and is pinned by ``tests/test_app_learn.py`` so the text cannot drift from the
model silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

import streamlit as st

PageName = Literal[
    "overview",
    "phase_envelope",
    "critical_point",
    "engineering_sweeps",
    "validation",
    "diagnostics",
]

LEARN_MODE_KEY: Final = "learn_mode"
LEARN_MODE_LABEL: Final = "Learn mode"
LEARN_MODE_HELP: Final = (
    "Show short explanations and exercises on each page. Learn mode never runs a "
    "calculation or changes a result."
)


@dataclass(frozen=True, slots=True)
class LearnTopic:
    title: str
    explanation: str
    exercises: tuple[str, ...]


TOPICS: Final[dict[PageName, LearnTopic]] = {
    "overview": LearnTopic(
        title="What a flash calculation answers",
        explanation=(
            "A **flash** takes a fixed overall composition *z*, temperature *T* and "
            "pressure *P* and asks: is this fluid one phase or two, and if two, "
            "how much of each and of what composition?\n\n"
            "1. **Stability first.** A tangent-plane-distance test checks whether "
            "splitting the feed into two phases would lower the Gibbs energy. If "
            "not, the fluid is reported as a single phase and no split is "
            "invented.\n"
            "2. **Equilibrium ratios.** For each component, *K* = *y*/*x*, the ratio "
            "of its vapour and liquid mole fractions. At equilibrium each "
            "component's fugacity is equal in both phases, so *K* = φᴸ/φⱽ, a ratio "
            "of fugacity coefficients from the Peng-Robinson equation of state.\n"
            "3. **Material balance.** The Rachford-Rice equation finds the vapour "
            "fraction β that conserves every component for the current *K* values; "
            "*K* is then updated until the fugacities match.\n\n"
            "**Z** is the compressibility factor *PV/(nRT)*. A liquid-like phase has "
            "a small Z; a vapour-like phase has Z closer to 1."
        ),
        exercises=(
            "Run the default case (50 % methane, 50 % propane, 300 K, 5 MPa). "
            "The fluid splits into two phases with a vapour fraction of about "
            "0.57. Which phase is richer in methane, and why?",
            "Keep 300 K and lower the pressure to 2 MPa. The flash now reports a "
            "single phase: you are below the dew point (about 2.35 MPa at 300 K "
            "for this mixture).",
        ),
    ),
    "phase_envelope": LearnTopic(
        title="Reading a pressure-temperature phase envelope",
        explanation=(
            "For one fixed composition, the envelope separates single-phase "
            "states (outside) from two-phase states (inside).\n\n"
            "- The **bubble curve** is where a liquid first forms a bubble of "
            "vapour; the **dew curve** is where a vapour first forms a drop of "
            "liquid.\n"
            "- They meet at the **mixture critical point**, where the two "
            "phases become identical. For a mixture this is generally *not* the "
            "highest pressure or highest temperature on the envelope.\n"
            "- The **cricondenbar** is the highest pressure and the "
            "**cricondentherm** the highest temperature at which two phases can "
            "coexist.\n"
            "- Between the critical temperature and the cricondentherm, raising "
            "the pressure can *create* liquid. This is **retrograde "
            "condensation**, important in gas-condensate reservoirs.\n\n"
            "The standard trace steps in temperature, so it cannot follow a "
            "curve back once it turns. The dotted *extended* branches use "
            "pseudo-arclength continuation, which can. A turning point marker is "
            "geometry, not a critical point."
        ),
        exercises=(
            "Run the envelope for the default case. The certified critical "
            "point is about 321.6 K and 8.53 MPa; the extended curves reach about "
            "8.8 MPa (cricondenbar) and about 329 K (cricondentherm). Check that "
            "the critical point is neither of these.",
            "Find 300 K on the envelope. The dew curve there is near 2.35 MPa and "
            "the bubble curve between 8.5 and 8.8 MPa. Compare with an Engineering "
            "Sweeps run at 300 K.",
        ),
    ),
    "critical_point": LearnTopic(
        title="What makes a point critical",
        explanation=(
            "At a mixture critical point the two coexisting phases become "
            "identical. Mathematically, the Gibbs energy loses its curvature in "
            "one composition direction (the smallest eigenvalue of the "
            "composition Hessian is zero) *and* the cubic term along that "
            "direction also vanishes.\n\n"
            "The first condition alone describes a spinodal, the limit of "
            "local stability, which is why this solver requires both. It also "
            "needs a starting guess (a seed) and reports failure rather than "
            "returning an uncertified point."
        ),
        exercises=(
            "Choose the example *Audited critical-solver seed*, press RUN FLASH, "
            "then RUN CRITICAL SOLVER. For the 50/50 methane/propane mixture it "
            "converges to about 321.58 K and 8.534 MPa. The flash at that state "
            "reports a single phase: at the critical point the two phases are "
            "identical.",
            "Compare that with the pure-component critical temperatures of "
            "methane (about 190.6 K) and propane (about 369.9 K). Is the mixture "
            "value a simple mole-fraction average?",
        ),
    ),
    "engineering_sweeps": LearnTopic(
        title="Following a fluid through a pressure or temperature change",
        explanation=(
            "A sweep runs an independent flash at each point along a line of "
            "constant temperature (or pressure). It shows where the fluid "
            "crosses the dew and bubble curves and how the phase amounts change "
            "in between.\n\n"
            "Each point is solved separately. A point that fails is reported as "
            "failed and is never smoothed over, so gaps in a curve are real "
            "information."
        ),
        exercises=(
            "Default case at 300 K, pressure from 1 to 10 MPa: the fluid is a "
            "single vapour phase below about 2.35 MPa. The vapour fraction falls "
            "to about 0.57 at 5 MPa and about 0.20 at 8 MPa, and the fluid is a "
            "single phase again by 8.8 MPa.",
            "Retrograde condensation: change the temperature to 325 K (between "
            "the critical temperature and the cricondentherm), press RUN FLASH, "
            "and sweep pressure from 5 to 8 MPa. Liquid appears above "
            "about 5.24 MPa *as pressure rises*, the vapour fraction falls to "
            "about 0.80 near 7.7 MPa, then starts to rise. Near 7.9 MPa the flash "
            "becomes inconclusive, because states this close to critical are "
            "numerically hard. The app reports that instead of guessing.",
        ),
    ),
    "validation": LearnTopic(
        title="Model accuracy versus software correctness",
        explanation=(
            "Two different questions are kept apart here:\n\n"
            "- **Is the code right?** Verification: the equations are solved "
            "correctly, checked by tests and independent recomputation.\n"
            "- **Is the model right?** Validation: Peng-Robinson with kij = 0 is "
            "compared against measured data (May et al., 2015).\n\n"
            "**AARD** is the average absolute relative deviation. A large error "
            "is not automatically model error. Near the maximum vapour "
            "composition of an isotherm, the dew pressure for a given vapour "
            "composition is extremely sensitive, so a tiny composition "
            "uncertainty can mean megapascals of pressure. See "
            "docs/DEW_INVESTIGATION.md."
        ),
        exercises=(
            "Compare the CH4+C3 bubble and dew results. The bubble direction "
            "(measured liquid composition → pressure) has about 1 % AARD. Why "
            "might the dew direction (measured vapour composition → pressure) "
            "look far worse for the same model and data?",
        ),
    ),
    "diagnostics": LearnTopic(
        title="Why a scientific tool shows its working",
        explanation=(
            "Iterative solvers can converge, stop early, or fail. Diagnostics "
            "show the residuals (how far the equations are from being "
            "satisfied), the number of iterations and the reason a calculation "
            "stopped.\n\n"
            "A trustworthy result is one whose residuals are small *and* whose "
            "stopping reason is understood. A plausible-looking number with an "
            "unexplained stop is not a result."
        ),
        exercises=(
            "Run the default flash and open this page. The flash converges in "
            "15 iterations, and the maximum equilibrium residual of the latest "
            "iteration is below 1e-8. Equal fugacities in both phases are "
            "satisfied to that level.",
        ),
    ),
}


def learn_mode_enabled() -> bool:
    return bool(st.session_state.get(LEARN_MODE_KEY, False))


def render_learn_toggle() -> None:
    st.toggle(LEARN_MODE_LABEL, key=LEARN_MODE_KEY, help=LEARN_MODE_HELP)


def render_learn_panel(page: PageName) -> None:
    """Show the page's teaching panel when Learn mode is on; otherwise nothing."""

    if not learn_mode_enabled():
        return
    topic = TOPICS[page]
    with st.expander(f"Learn: {topic.title}", expanded=True, icon=":material/school:"):
        st.markdown(topic.explanation)
        st.markdown("**Try this**")
        for exercise in topic.exercises:
            st.markdown(f"- {exercise}")
