---
title: "Limitations"
weight: 8
---

## Status

pyFDS-Evac is research software, provided without warranty. It is not intended
for regulatory or design use. It is maintained by one researcher at
Forschungszentrum Jülich (IAS-7) and has no release policy yet, so behaviour
and defaults can change between commits. A result from pyFDS-Evac is a
research result. It is not an assessment of a building.

The evidence that exists is listed on the
[verification page](https://pedestriandynamics.org/pyFDS-Evac/models/verification/).
That evidence is verification (the code does what its equations say), not
validation (the equations describe how people behave).

## Some parameters are library-level

Not every model parameter is reachable from the command line or the scenario
JSON. The smoke-speed parameters (`speed_law`, `alpha`, `beta`,
`min_speed_factor` and `visibility_factor_c`) are fields of
`SmokeSpeedConfig`. `run.py` and the web GUI build that object with its
defaults, so every run they start uses the Frantzich–Nilsson law (the `lund`
option; the linear FDS+Evac law) with the defaults listed on the
[smoke-speed model](/models/smoke-speed.md#parameters) page. Another law or
other coefficients require building the model in Python and passing it to
`run_scenario()`.

The JSON `routing` block has keys with the same names. They parameterise the
speed factor used to estimate travel time when a route is priced, not the
walking speed. Setting `routing.alpha` therefore changes which route an agent
prefers but leaves its speed in smoke unchanged. The same split applies to
speed itself: `routing.base_speed_m_per_s` (1.3 m/s) prices routes, while an
agent walks at its own `v0` (1.2 m/s by default).

## Incapacitation is probabilistic by default

FED below means fractional effective dose. By default
(`--incapacitation-mode probabilistic`), each agent draws its own
incapacitation threshold from a log-normal distribution with median
`--fed-threshold` and log-scale spread `--susceptibility-sigma` (defaults on
the [FED model](/models/fed.md#tenability-irritant-slowdown-and-incapacitation) page).
About half of the agents therefore stop below FED = 1, and about 10 % stop
below FED = 0.3. The default spread is fitted to the incapacitation fractions
of NIST TN 1797
([#148](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/148)). The
heat dose uses the same mechanism, and its spread is reused from the gas value
without a data basis of its own. FDS+Evac stops
every agent at FED = 1. For results comparable with FDS+Evac, run with
`--incapacitation-mode deterministic` (and `--heat-incapacitation-mode
deterministic` for the heat dose).

## Evacuation time when anyone is incapacitated

An incapacitated agent stays in the simulation as a stationary obstacle. The
run ends early only when no agent is left, so a run in which any agent is
incapacitated continues until `max_simulation_time` (300 s by default). Its
reported `evacuation_time` is then that time limit, not the time the last
mobile agent left. `success` is also true at the time limit even when agents
remain ([issue #139](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/139)).
Read `agents_remaining`, and take the time each agent left from the
trajectory file, instead of relying on these two values
([issue #141](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/141)).

## Incapacitation during pre-movement is undone

An agent that is incapacitated while it is still waiting out its
pre-movement time starts walking when that time ends
([issue #145](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/145)).
Scenarios that combine pre-movement with FED therefore under-report
incapacitations and over-report evacuees. Until this is fixed, check the
per-agent FED history for agents that crossed their threshold and still
reached an exit.

## What is not modelled

**Radiant heat.** The heat dose is the convective term of Purser and
McAllister (SFPE Handbook, 5th ed., Eq. 63.44), computed from the gas
temperature of an FDS `TEMPERATURE` slice. Radiant heat flux is not read and
does not contribute to any dose. An agent near a flame or under a hot layer
that radiates strongly is therefore treated as less exposed than it is.

**Heat does not affect route choice or walking speed.** The heat dose is
tracked per agent, separately from the toxic dose, and an agent is
incapacitated when either dose reaches its threshold. Before that point, heat
has no effect. Route choice is given the toxic dose only, so an agent can
choose a route that will incapacitate it thermally. Walking speed is reduced
by extinction and by irritant gases, but not by temperature, so an agent walks
at full speed through a hot layer until the heat dose is reached.

**Multi-floor buildings and stairs.** The walkable area is a single 2-D
polygon, and hazards are sampled from slices at one height
(`--smoke-slice-height`). There is no stair model, no floor-to-floor
connection and no speed reduction on inclines. `generate_walkable_from_fds.py`
treats stair treads and risers as floor, so a staircase in an FDS deck becomes
flat floor that agents cross at full speed. A `zones` entry with a
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

**Herding and social influence.** Each agent chooses its route from its own
cognitive map and the hazard along each route. When `routing.w_queue` is
above zero (the default is 0.0), expected queueing at an exit also enters the
cost, so a crowded exit becomes less attractive. Agents do not follow others,
and an exit never becomes more attractive because others use it. See
[issue #78](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/78).

**Perception-limited route choice.** A discovery agent knows only the exits
whose signs it has read, but it prices the routes to them with the smoke
sampled along the whole route, including stretches it has never seen
([issue #125](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/125)).
By default (`routing.anticipate` = true, `routing.foresight_horizon_s`
unbounded), each stretch is also priced with the smoke that the finished FDS
run holds for the time the agent would arrive there. Route choice is therefore
a best case with perfect foresight, not a model of what an occupant can see or
predict.

**Recovery from irritants.** The irritant slowdown is recomputed only while
the sampled fractional irritant concentration (FIC) is positive. When it
returns to exactly zero, the last slowdown stays in force, so an agent that
leaves an irritant plume into clean air does not return to full speed
([issue #142](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/142)).

**Sourced pre-movement defaults.** The preset parameters of the four
pre-movement distributions are illustrative, not from a cited dataset. Set
`premovement_param_a` and `premovement_param_b` from data for your occupancy
([issue #144](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/144)).

**Smoke-triggered detection.** Pre-movement is one delay per agent, drawn
from a distribution. Smoke reaching the agent does not end the delay early,
and there is no separate detection phase.

**Feedback from occupants to the fire.** The coupling is one-way. The FDS run
is finished before the evacuation starts, so occupants cannot open doors or
otherwise change the fire. The time resolution of the hazard is that of the
slice output (`&DUMP DT_SLCF`).

## Reproducibility

A fixed seed does not give identical trajectories. The verification suite
found that individual trajectories differ between runs with the same seed,
while aggregate outcomes (counts and fractions, such as the number of agents
incapacitated or rerouted) reproduce. Report aggregate outcomes over several seeds, with their spread,
and do not compare single trajectories between runs. See the
[verification page](https://pedestriandynamics.org/pyFDS-Evac/models/verification/).

## References

Korhonen, T. (2021). *Fire Dynamics Simulator with Evacuation: FDS+Evac.
Technical Reference and User's Guide*. VTT Technical Research Centre of
Finland.

Purser, D. A., and McAllister, J. L. (2016). Assessment of hazards to
occupants from smoke, toxic gases, and heat. In *SFPE Handbook of Fire
Protection Engineering*, 5th ed., Chapter 63. Springer.
