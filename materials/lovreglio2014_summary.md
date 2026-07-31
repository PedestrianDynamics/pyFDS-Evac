The paper "A discrete choice model based on random utilities for exit choice in emergency evacuations" by Lovreglio, Borri, dell'Olio & Ibeas (*Safety Science* 62, 2014) is the first in a series of studies that calibrate exit-choice models from stated-preference (SP) surveys built on FDS+Evac-generated videos, and it establishes the modelling framework (Random Utility Theory + Mixed Logit) that the later Lovreglio (2016) and Haghani/Sarvi papers all build on or contrast against.

### 1. Methodology: video-based stated preference survey
191 respondents watched 12 short **FDS+Evac** videos of a two-exit enclosed environment and, at the end of each, chose left or right exit under a 5-second countdown (to suppress over-deliberation). Each video varied three factors via an orthogonal fractional-factorial design: number of people at each exit (**NPE**), number of people near the decision-maker heading to an exit (**NPDM**), and the decision-maker's position relative to the two exits (**NEAREX**, left/center/right).

### 2. Model: Mixed Logit with random coefficients
Choices were fit with a **Mixed Logit Model (MLM)** rather than a plain Multinomial Logit, so that taste parameters (not just the random utility residual) are allowed to vary across the population — this is the paper's core methodological argument: heterogeneity in how people react to crowds is real and a fixed-coefficient model hides it. Key estimated effects:
*   **NPE** (crowd size at an exit): negative — more people already at an exit is a disamenity (congestion aversion).
*   **NPDM** (crowd near the decision-maker heading to one exit): positive on average — **herding behaviour**, but this reverses (`NPDM*GR` interaction) for decision-makers modelled as part of a graduate/higher-education subgroup, who show more independent, less herd-driven choice.
*   **NEAREX** (proximity): strongly positive — people prefer the nearer exit, and this preference **strengthens with age** (`NEAREX*AGE`), i.e. older decision-makers weight proximity more heavily than younger ones.

### 3. Principal findings
*   Exit choice is not just travel-time minimization; it is measurably shaped by **social influence** (herding) and **personal characteristics** (age, education), which a deterministic time-based router cannot represent.
*   The random-coefficient (MLM) formulation is necessary because different sub-populations respond to crowding in opposite directions — some are attracted to a crowd near them (informational social influence), others actively avoid it.
*   This paper explicitly frames itself as a first step; its case study is small (191 respondents, only 3 variables) and does not yet include environmental factors like smoke or lighting — that gap is what Lovreglio et al. (2016) (`lovreglio2016_summary.md`) address directly.

### 4. Relevance to this repository
This paper is the direct ancestor of the herding/crowd-avoidance social-influence mechanics one would want in [[pyfds_evac/core/route_graph.py]]-style rerouting logic: it's evidence that "avoid crowded exits" and "follow the crowd" are *both* real, population-heterogeneous behaviours, not a single universal rule — worth keeping in mind if familiarity/herding weighting is ever added to the agent routing model, alongside `[[lovreglio2016]]` and `[[haghani2017]]`.
