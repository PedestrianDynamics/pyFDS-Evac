_Source PDF is not tracked in this repository._

The paper "Simulating Indoor Evacuation of Pedestrians: The Sensitivity of Predictions to Directional-Choice Calibration Parameters" by Haghani, Sarvi & Rajabifard (*Transportation Research Record* 2672(1), 2018) takes the disaggregate directional-choice dataset from the same experimental program as `[[haghani2017]]` (real physical evacuation-drill trials, ~150 participants, PeTrack-tracked, 3338 observations here) and plugs the calibrated exit-choice model into a full **bi-layer microscopic simulation** â€” social-force operational layer + discrete-choice tactical layer â€” to ask a different question: *how much does the accuracy of these calibration parameters actually matter for simulated evacuation time?*

### 1. Model architecture: two coupled layers
*   **Operational layer** â€” a standard **social force model** (Helbing, Farkas & Vicsek formulation): each pedestrian's motion is the net of a desired-direction force, inter-pedestrian repulsion forces, and wall-avoidance forces.
*   **Tactical layer** â€” a **multinomial-logit directional-choice model** feeding the desired direction into the operational layer. Utility for each candidate exit direction `n`:
    `V = Î²1Â·DIST + Î²2Â·CONG + Î²3Â·FLTOVIS + Î²4Â·FLTOINVIS + Î²5Â·VIS`
    (same variable definitions as `[[haghani2017]]`: distance, congestion at the exit, flow toward visible/invisible exits split out separately, and exit visibility). Calibrated coefficients: DIST âˆ’0.256, CONG âˆ’0.138, FLTOVIS âˆ’0.024, FLTOINVIS +0.093, VIS +0.710 â€” all statistically significant, matching the sign pattern found in `[[haghani2017]]`.

### 2. The sensitivity analysis
Holding all other parameters at their calibrated value, each of the five Î² coefficients was independently swept across a wide range (increasing/decreasing until no further change in outcome), with 50 simulation repetitions per parameter value, recording **total evacuation time** and **average individual evacuation time**.

### 3. Principal findings
*   Simulated evacuation time is **highly sensitive to these parameters** â€” total evacuation time varied by up to **~30%** depending on the parameter value chosen, which the authors frame as a strong argument for careful, data-driven calibration over hand-picked/intuitive parameter values.
*   **Total evacuation time and average individual evacuation time move together** almost identically across all sensitivity sweeps â€” meaning either metric can be used interchangeably as an optimization objective; you don't need to track both.
*   **Multi-attribute tradeoff behaviour outperforms single-attribute rules at the system level.** Two common simplified heuristics were effectively tested as limiting cases: pure shortest-distance routing and pure follow-the-crowd routing. Both perform **worse** (longer evacuation time) than the real, multi-attribute behaviour people actually exhibited â€” extreme/simplified parameter settings were consistently sub-optimal, and the best system-level performance for each parameter occurred at an **intermediate value**, not at either extreme.
*   Practical implication: a router that always takes the shortest path, or one that always follows the crowd, is a worse model of real evacuation dynamics (and produces worse throughput predictions) than a weighted tradeoff model â€” even though shortest-path and crowd-following are the two most common simplifying assumptions in evacuation modelling.

### 4. Relevance to this repository
This paper is direct evidence for why this repo's dynamic rerouting (in `[[pyfds_evac/core/route_graph.py]]`, driven by smoke/congestion cost terms rather than pure shortest-path) is the right modelling choice â€” the authors explicitly show pure-shortest-path and pure-follow-the-crowd routing both *overestimate* evacuation time relative to calibrated multi-attribute choice. It's also a caution about **calibration sensitivity**: if this project's route-cost weighting (smoke penalty, congestion penalty, distance) is ever tuned, expect evacuation-time outcomes to be quite sensitive to those relative weights (Â±30% swings are plausible from parameter choice alone), so weight values should be justified from data rather than picked intuitively, and total vs. average evacuation time can be treated as interchangeable metrics when tuning/validating.

