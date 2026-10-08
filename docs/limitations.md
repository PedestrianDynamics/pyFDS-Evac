---
title: "Limitations"
weight: 8
aliases: [/docs/limitations/]
---

## Status

pyFDS-Evac is research software, provided without warranty. It is not intended
for regulatory or design use. It is developed at Forschungszentrum Jülich
(IAS-7); its maintainers are listed in
[CODEOWNERS](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/.github/CODEOWNERS).
Releases follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html): they are tagged
`vX.Y.Z` and published on
[GitHub](https://github.com/PedestrianDynamics/pyFDS-Evac/releases) and
[PyPI](https://pypi.org/project/pyfds-evac/). While the major version is 0, a
change to CLI flags, output columns, defaults, exit codes or the public API
bumps the minor version. The
[changelog](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/CHANGELOG.md)
lists every notable change. A result from pyFDS-Evac is a
research result. It is not an assessment of a building.

The evidence that exists is listed on the
[verification page](https://pedestriandynamics.org/pyFDS-Evac/verification/).
That evidence is verification (the code does what its equations say), not
validation (the equations describe how people behave).

## Some parameters are library-level

Not every model parameter is reachable from the command line or the scenario
JSON. The smoke-speed parameters (`speed_law`, `alpha`, `beta`,
`min_speed_factor` and `visibility_factor_c`) are fields of
`SmokeSpeedConfig`. `run.py`, the web GUI and the terminal UI build that object
with its defaults, so every run they start uses the Frantzich–Nilsson law (the `lund`
option; the linear [FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source) law) with the defaults listed on the
[smoke-speed model](/models/smoke-speed.md#parameters) page. Another law or
other coefficients require building the model in Python and passing it to
`run_scenario()`.

The JSON `routing` block has keys with the same names. They parameterise the
speed factor used to estimate travel time when a route is priced, not the
walking speed. Setting `routing.alpha` therefore changes which route an agent
prefers but leaves its speed in smoke unchanged. The same split applies to
speed itself: `routing.base_speed_m_per_s` (1.3 m/s) prices routes, while an
agent walks at its own `v0` (1.25 m/s by default).

## Outside the FDS domain the air is clear

Where no FDS slice covers an agent, it reads ambient air: *K* = 0, so full
walking speed, no gas dose, and 20 °C. FDS+Evac does the same for smoke,
gases and heat
([`evac.f90:7250–7272`](https://github.com/firemodels/fds/blob/c9da70d7a/Source/evac.f90#L7250-L7272)).
A route edge prices its part outside as clear air: an edge wholly outside
has optical depth τ = 0, and a partly covered edge has a diluted mean *K*.
A room left out of the FDS meshes therefore looks safe to walk through and
to route through. Values per quantity are on
[FDS slice sampling](fds-sampling.md#outside-the-fds-slices).

The run reports where this applies. At setup it logs the walkable area,
exits, checkpoints, spawn areas, signs and route edges outside the slices,
and stores them as `fds_coverage` in the run manifest. The smoke and FED
histories mark each row outside with `in_fds_domain = False`, and
`metrics["fds_outside"]` counts the agents, samples and agent-seconds
outside. Check these two; the single warning at the first extinction
sample outside says nothing about later agents. The route-cost history does
not record the length outside per row
([#431](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/431)).
`--require-fds-coverage` turns every case outside into an error.

**Signs seen from outside the FDS grid.** An agent beyond the grid of an
FDS visibility model sees every sign within its reading distance, measured
from its true position, without testing view angle, walls or smoke, also
when the sight line crosses smoke inside the domain
([#426](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/426)).
FDS+Evac's `See_door`
([`evac.f90:15682–15813`](https://github.com/firemodels/fds/blob/c9da70d7a/Source/evac.f90#L15682-L15813))
still walks that line across the evacuation grid: a wall stops it, and the
mean *K* that enters its door choice counts the soot of the cells inside
the fire meshes. Off the grid, pyFDS-Evac is therefore less conservative
than FDS+Evac, and a discovery agent outside can learn an exit from a sign
that the smoke between them would hide. See
[Wayfinding › Off the FDS grid](/models/wayfinding.md#off-the-fds-grid).

## Incapacitation is deterministic by default

FED below means fractional effective dose. By default
(`--incapacitation-mode deterministic`), every agent stops when its FED
reaches `--fed-threshold` (1.0), as in FDS+Evac. A real population does not
stop all at once. With `--incapacitation-mode probabilistic`, each agent
draws its own threshold from a log-normal distribution with median
`--fed-threshold` and log-scale spread `--susceptibility-sigma` (defaults on
the [FED model](/models/fed.md#tenability-irritant-slowdown-and-incapacitation) page).
About half of the agents then stop below FED = 1, and about 10 % stop
below FED = 0.3. The default spread is fitted to the incapacitation fractions
of NIST TN 1797
([#148](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/148)). The
heat dose, which FDS+Evac does not have, is also deterministic by default: no
population spread for heat is published. Its threshold is `--fed-threshold`
unless `--heat-fed-threshold` sets another, a departure from ISO 13571:2012
§5.4. Its `probabilistic` mode reuses the
gas spread without a data basis of its own.

The fractional irritant concentration (FIC) never incapacitates. The
published sources predict incapacitation at FIC = 1, but the opt-in irritant
slowdown, with its default floor `--fic-min-factor` 0.3, only lowers the
speed to 0.3 of its smoke-reduced value
([#398](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/398)).
Irritants reach incapacitation only through their lung dose
\(FLD_{irr}\), which is summed into the gas FED.

## Evacuation time when anyone is incapacitated

An incapacitated agent stays in the simulation as a stationary obstacle. The
run ends early only when no agent is left, so a run in which any agent is
incapacitated continues until `max_simulation_time` (300 s by default). Its
reported `evacuation_time` is then that time limit, not the time the last
mobile agent left. Such a run is incomplete: `success` is `False`,
`status` is `"incomplete"` and `run.py` exits with status 2
([issue #139](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/139)).
Read `agents_remaining`, and take the time each agent left from the
trajectory file, instead of relying on `evacuation_time`
([issue #141](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/141)).

## Incapacitation during pre-movement is undone

An agent that is incapacitated while it is still waiting out its
pre-movement time starts walking when that time ends
([issue #145](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/145)).
Scenarios that combine pre-movement with FED therefore under-report
incapacitations and over-report evacuees. A scenario that sets no pre-movement
gets the FDS+Evac default of 10 s, so this applies to it too, for its first
10 s. Until this is fixed, check the
per-agent FED history for agents that crossed their threshold and still
reached an exit.

## What is not modelled

**Radiant heat.** The heat dose is opt-in (`--enable-heat-fed`) and, by
default, convective only: ISO 13571:2012 Eq. (9) from the gas temperature of
an FDS `TEMPERATURE` slice. Radiation enters only through the opt-in
`--heat-fed-method total-flux`, from the gas at the head, a hot layer above
it (`--heat-regime layer`), or the FDS `INTEGRATED INTENSITY` slice with a
user factor; radiant flux from hot surfaces or a flame is otherwise missed
([#276](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/276)). In
every total-flux variant a radiant term below the ISO 2.5 kW/m² threshold
counts as zero, and the code applies that threshold to a net or excess flux
rather than an incident one; the consequences, with numbers, are on
[Models › Heat › Where the radiant threshold acts](/models/heat.md#where-the-radiant-threshold-acts),
and the unsourced values on
[Models › Heat › Assumptions](/models/heat.md#assumptions-unsourced-values).

**Heat does not affect route choice or walking speed.** The heat dose is
opt-in (`--enable-heat-fed`). When on, it is tracked per agent, separately from the toxic dose, and an agent is
incapacitated when either dose reaches its threshold, one value for both
by default, as ISO 13571:2012 asks (§5.4). The two doses have different
endpoints: gas FED = 1 is incapacitation, heat FED = 1 the time of ISO
Eq. (9), which ISO calls the time to prevention of escape or to
experiencing pain (see Fundamentals › Heat); the FED history's
`incapacitation_cause` column says which dose stopped the agent. Before that
point, heat has no effect. Route choice is given the toxic dose only, so an agent can
choose a route that will incapacitate it thermally. Walking speed is reduced
by extinction and, with `--enable-fic-speed`, by irritant gases, but not by temperature, so an agent walks
at full speed through a hot layer until the heat dose is reached.

**Multi-floor buildings and stairs.** The walkable area is a single 2-D
polygon, and hazards are sampled from slices at one height
(`--smoke-slice-height`). There is no stair model, no floor-to-floor
connection and no speed reduction on inclines. `pyfds-evac init` imports one
floor, and every `&OBST` in its walking band blocks, stair treads included; a
staircase drawn into the walkable area by hand is flat floor that agents cross
at full speed. A `&DOOR` to another floor becomes an exit, so "evacuated" on
an imported upper floor means "reached the stair door"
([Start from your own FDS case › Limits](start-from-fds-deck.md#limits)). A `zones` entry with a
`speed_factor` can slow agents inside a polygon, but it does not represent
direction of travel on a stair.

**FED activity level.** The CO term of the toxic dose uses one fixed
coefficient, the FDS+Evac default for light work (Korhonen 2021, Eq. 13; see
the [FED model](/models/fed.md#coded-form)). Rest and heavy work cannot be selected, although
breathing rate changes the CO dose. Not supported; see
[issue #135](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/135).

**Per-exit familiarity.** Familiarity is set per spawn distribution, as
`"full"`, `"discovery"`, or one probability applied to every exit. The
`entrance` key adds one exit that the whole group knows. A separate
probability for each exit, as FDS+Evac allows with `KNOWN_DOOR_PROBS`, is not
supported; see
[issue #136](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/136).

**Familiarity does not change how agents treat smoke.** Familiarity decides
which exits an agent knows, not how much smoke it accepts. The route-cost
settings, including every smoke setting of both cost models, are built once
per run from the scenario's `routing` block and fixed defaults
(`RouteCostConfig`), so every agent shares them. In Wood's UK
survey, people completely familiar with the building moved through smoke more
often than those less familiar (61 % against 51 %; Wood 1980, Table 6.4,
p. 87; Wood 1972, p. 80, reports the trend over four familiarity levels as
significant). Familiarity did not affect how far people moved through smoke
(Wood 1972, p. 83), 85 % of respondents were completely familiar with the
building (Wood 1972, Table 6, p. 40), and moving through smoke was not
associated with leaving the building (Wood 1980, p. 91). See
[issue #362](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/362).

**Herding and social influence.** Each agent chooses its route from its own
cognitive map and the hazard along each route. When `routing.w_queue` is
above zero (the default is 0.0), expected queueing at an exit also enters the
cost, so a crowded exit becomes less attractive. Agents do not follow others,
and an exit never becomes more attractive because others use it. See
[issue #78](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/78).

**Perception-limited route choice.** A discovery agent knows only the exits
its familiarity, `entrance` or a legible sign gave it, but it prices the routes to them with the smoke
sampled along the whole route, including stretches it has never seen
([issue #125](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/125)).
By default (`routing.anticipate` = true, `routing.foresight_horizon_s`
unbounded), the path to each exit is found from the agent's position on the
smoke at decision time,
and each point of that path is then priced with the smoke that the
finished FDS run holds for the time the agent would arrive there (#650). Knowledge limits which
routes an agent ranks, and only fully familiar agents know the whole graph;
it does not limit the smoke those routes are priced with. The route choice of
a discovery agent is therefore not limited by what it has perceived.

**Route choice.** Route choice has open limitations: switching can oscillate
where two routes cross in cost ([#124](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/124)), routes are priced with smoke the agent
cannot perceive ([#125](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/125)), one path is priced per exit ([#185](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/185)), the first-leg FED is taken pro rata from the first edge ([#171](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/171)), a real optical-depth
difference inside the anchor's deadband can keep the current exit ranked first, so the anchor is never asked ([#187](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/187); round-off is a tie since [#452](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/452)). The full list, with
one line per issue, is on
[Models › Routing › Limitations](/models/routing.md#limitations).

**Irritant slowdown.** The opt-in irritant slowdown
(`--enable-fic-speed`) uses a curve with no known source and is combined
with the smoke factor multiplicatively, not additively as published
([#147](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/147);
[Models › FED](/models/fed.md#irritant-slowdown-against-the-published-rule)).

**Recovery from irritants.** The irritant slowdown (opt-in with
`--enable-fic-speed`) is recomputed only while
the sampled fractional irritant concentration (FIC) is positive. When it
returns to exactly zero, the last slowdown stays in force, so an agent that
leaves an irritant plume into clean air does not return to full speed
([issue #142](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/142)).

**Pre-movement defaults are office data.** The gamma, log-normal and Weibull
presets are fitted to office evacuations, mostly drills (Lovreglio et al. 2019,
Business Cluster 1). The uniform 0–60 s preset is RiMEA's "speedy evacuation"
sensitivity scenario, not data. The 10 s used when a scenario sets no pre-movement is the FDS+Evac default, not
data. Set `premovement_param_a` and `premovement_param_b` for other occupancies.

**Smoke-triggered detection.** Pre-movement is one delay per agent, drawn
from a distribution. Smoke reaching the agent does not end the delay early,
and there is no separate detection phase.

**Feedback from occupants to the fire.** The coupling is one-way. The FDS run
is finished before the evacuation starts, so occupants cannot open doors or
otherwise change the fire. The time resolution of the hazard is that of the
slice output (`&DUMP DT_SLCF`).

**Social force friction.** With `model_type: "SocialForceModel"`, the
friction *κ* is 0 for agents and walls: JuPedSim 1.4.2 applies the wall
friction with the wrong sign
([jupedsim#1677](https://github.com/PedestrianDynamics/jupedsim/pull/1677)),
and its one friction parameter also drives the agent term. This holds
when `sfm_friction` is missing, without a warning; a deck that declares
it above 0 gets a warning
([#635](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/635)).
There is no sliding friction, so no clogging or faster-is-slower effect
from friction at a bottleneck. The body force *k* acts. *A* and *B* were
fitted to one bottleneck flow at a desired speed of about 0.8 m/s
(Helbing, Farkas & Vicsek 2000); the shipped SFM decks use 1.25–1.3 m/s
and a radius of 0.2 m.

**Re-entry.** An agent that reaches an exit is removed from the simulation
(`run_scenario` in `pyfds_evac/core/scenario.py`), so nobody goes back into
the building. In Wood's UK survey, 43 % of those who had left the building
re-entered it (Wood 1972, Fig. 5, p. 48; Wood 1980, Table 6.3, p. 87): 53 % of men and 34 % of women
(Table 6.3, p. 87).

## Reproducibility

A fixed seed does not give identical trajectories. The verification suite
found that individual trajectories differ between runs with the same seed,
while aggregate outcomes (counts and fractions, such as the number of agents
incapacitated or rerouted) reproduce. Report aggregate outcomes over several seeds, with their spread,
and do not compare single trajectories between runs. See the
[verification page](https://pedestriandynamics.org/pyFDS-Evac/verification/).

One known cause makes results depend on more than the seed:

- **Python's hash seed.** For discovery agents, the order of tied routes can
  depend on `PYTHONHASHSEED`
  ([#199](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/199)). Set
  it to a fixed value for bit-identical reruns.

Earlier runs in the same Python process do not change the results. Every
per-agent draw is seeded from the seed and the agent's spawn order, not from
its JuPedSim id. The outputs still label agents by JuPedSim id, which is
numbered per process, so a second run in the same process reports the same
agents under other ids.

## References

Helbing, D., Farkas, I., and Vicsek, T. (2000). Simulating dynamical
features of escape panic. *Nature*, 407, 487–490.
[doi:10.1038/35035023](https://doi.org/10.1038/35035023).

Korhonen, T. (2021). *Fire Dynamics Simulator with Evacuation: FDS+Evac.
Technical Reference and User's Guide*. VTT Technical Research Centre of
Finland.

Purser, D. A., and McAllister, J. L. (2016). Assessment of hazards to
occupants from smoke, toxic gases, and heat. In *SFPE Handbook of Fire
Protection Engineering*, 5th ed., Chapter 63. Springer.

Wood, P. G. (1972). *The Behaviour of People in Fires*. Fire Research Note
No. 953, Fire Research Station, Borehamwood. No DOI or public URL.

Wood, P. G. (1980). A survey of behaviour in fires. In D. Canter (Ed.),
*Fires and Human Behaviour*, pp. 83–95. John Wiley & Sons, Chichester.
ISBN 0-471-27709-6.
