The paper "A mixed logit model for predicting exit choice during building evacuations" by Lovreglio, Fonzone & dell'Olio (*Transportation Research Part A* 92, 2016) substantially extends `[[lovreglio2014]]`: a much larger stated-preference survey (1503 respondents vs. 191), delivered via non-immersive Unity3D virtual-reality videos rather than FDS+Evac footage, and — critically for this project — it adds **fire-relevant environmental factors** (smoke, emergency lighting, exit flow rate) alongside the social factors studied before.

### 1. Survey design
Respondents watched Unity3D-rendered videos of a metro-station-like environment with two exits and, after each of 6 scenarios, chose left or right under a countdown timer. Scenarios were built with an **efficient design (D-error minimisation)** technique rather than a plain orthogonal design, letting the study cram more variables into fewer scenarios per respondent. Six variables were manipulated:
*   **NCE** — number of evacuees close to the exit itself (congestion at the exit)
*   **FL** — flow rate of evacuees through the exit (throughput/capacity signal)
*   **NCDM** — number of evacuees close to the decision-maker, heading toward one exit (a local-crowd/herding cue, distinct from NCE)
*   **SM** — presence of smoke near an exit (dummy variable)
*   **EL** — presence of emergency lighting above an exit
*   **DIST** — distance from the decision-maker to the exit

### 2. Model and key coefficient signs (Mixed Logit)
*   **NCE: negative.** Crowding *at* the exit is a disincentive — decision-makers show **crowd-avoidance**, not herding, when the crowd is already congesting their target exit.
*   **NCDM: on average negative but with very high dispersion** (large random-parameter standard deviation) — this is the paper's central behavioural finding: **herding and crowd-avoidance coexist in the population**, and which one dominates for a given individual differs. NCE and NCDM being oppositely-signed on average shows people react differently depending on *where* the crowd is (blocking the exit vs. moving toward it with you) — the proximity/Hall's "personal space" framing is offered as one explanation.
*   **FL: strongly positive.** A higher observed flow through an exit reads as "faster escape route," making it more attractive — this is a capacity/efficiency signal, separate from raw crowd count.
*   **SM: strongly negative.** Smoke near an exit is avoided, as expected.
*   **DIST: negative but with very large dispersion** — many respondents essentially ignored distance as a deciding factor in this study, a notably different (weaker) result than in `[[lovreglio2014]]`.
*   **EL: strongly positive.** Lit/marked exits are preferred — consistent with exit-sign/wayfinding-aid literature.

### 3. Comparison against prior models (their Table 5)
The paper directly benchmarks against Duives & Mahmassani (2012), `[[lovreglio2014]]`, and Haghani et al. (2014), showing its adjusted-R² fit is markedly better because it is the only model to include all six factors simultaneously — under-specified models (e.g. omitting smoke/lighting) risk **overestimating** the pull of other variables like flow rate.

### 4. Principal findings & caveats
*   Both "intrinsic behavioural uncertainty" (people are genuinely inconsistent) and "perception/preference behavioural uncertainty" (people weight the same factor differently) are present and are what the Mixed Logit's random coefficients are capturing.
*   Self-reported realism of the VR scenarios was only 3/5 on average — a stated limitation the authors flag explicitly, and one that motivates the stated-vs-revealed comparison later done by Haghani & Sarvi (`[[haghani2017]]`).
*   No significant gender effect was found on any environmental/social variable (differing from an earlier finding in `[[lovreglio2014]]`), attributed to this study's richer variable set absorbing what gender was previously proxying for.

### 5. Relevance to this repository
This is the most directly applicable paper for [[pyfds_evac/core/fed.py]]/[[pyfds_evac/core/route_graph.py]]-style rerouting: it gives concrete, signed, population-heterogeneous coefficients for exactly the kind of smoke/congestion/flow/lighting/distance tradeoff this codebase's dynamic rerouting is trying to approximate — in particular the finding that **crowding at the target exit repels but crowd movement toward an exit can still attract (with high variance)** is a nuance worth keeping distinct if crowd-based route cost terms are ever added here.
