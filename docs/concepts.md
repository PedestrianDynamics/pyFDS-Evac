---
title: "Concepts"
weight: 2
math: true
---

ISO 13943:2023 defines human behaviour in fire as "actions performed in the
event of a fire as a result of a behavioural or decision-making process". The
talk
[*A Modular Workflow for Visibility-Aware Evacuation Modelling*](https://pedestriandynamics.org/pyFDS-Evac/talks/visibility-seminar-2026/)
(Visibility Seminar 2026, [PDF](https://pedestriandynamics.org/pyFDS-Evac/talks/pyFDS-Evac_visibility_seminar_2026.pdf))
splits the behaviour that smoke disturbs into three questions. **Speed** asks
how fast an occupant can walk. **Route choice** asks which exit the occupant
heads for. **Wayfinding** asks which exits the occupant knows about at all.
pyFDS-Evac answers each question from the output of a finished Fire Dynamics
Simulator (FDS) run and hands the answers to JuPedSim, which moves the agents.
This page explains the ideas behind each answer and the rules you need to read
a result. The equations, parameters and evidence are on the
[model pages](/models/_index.md). The published laws these models rest on, independent
of this code, are on the [Fundamentals](/fundamentals/_index.md) pages.

pyFDS-Evac is research software, provided without warranty. It is not intended
for regulatory or design use. See [Limitations](/docs/limitations.md).

## One-way coupling and the data flow

FDS runs once, before any agent moves. pyFDS-Evac never starts FDS and never
writes back to it: the egress simulation only reads the slice files that FDS
stored. This is one-way coupling. Agents cannot change the fire, so a crowd
that blocks a door does not change the smoke that reaches it. In return, the
same fire can be reused for any number of egress runs, and a prescribed field
can replace FDS entirely. The [Quickstart](/docs/quickstart.md) uses a uniform
extinction field and needs no FDS output at all.

```text
FDS output (.smv + slice files)
  │
  ├─ fdsreader ─ SliceFieldSampler ─┬─ ExtinctionField   K [1/m]
  │   nearest-neighbour lookup      ├─ FdsFedField       CO, CO₂, O₂, irritants
  │   of (t, x, y) at one height    └─ FdsHeatField      gas temperature [°C]
  │
  └─ fdsvismap ─ VisibilityModel     which cells can read which sign, per time
                                   │
Scenario (load_scenario) ──────────┤
                                   ▼
                             run_scenario()  ── JuPedSim moves the agents
                                   │
                                   ▼
  trajectory (SQLite) + optional per-agent histories (smoke, FED, route,
  route cost, cognitive map) + <trajectory>.manifest.json
```

The FED fields feed the fractional effective dose (FED) described below. The
sampler looks up the nearest stored value in time and space on a single
horizontal slice, 2 m above the floor by default. Every agent reads the same
height. The manifest records the package versions, the seed, the scenario path
and the FDS version, so a result can be traced to the code and the fire that
produced it. The [walkthrough](/docs/walkthrough.md) runs this chain on a
tracked FDS case, and [Your FDS case](/docs/fds-case-requirements.md) lists the
slices the deck must write.

## Speed

### From extinction to walking speed

Smoke enters the speed model through the extinction coefficient *K* [1/m],
read from the FDS `SOOT EXTINCTION COEFFICIENT` slice at the agent's position.
An agent walks at

$$
v = v_0 \, f(K),
$$

where \(v_0\) [m/s] is its unimpeded desired speed and \(f\) [-] is a speed
factor between 0 and 1. The default law is Frantzich–Nilsson (the `lund`
option; the linear FDS+Evac law), used with the same constants as FDS+Evac (Korhonen 2021, §3.4;
compared across tools by [Ronchi et al. 2013](https://doi.org/10.1007/s10694-012-0280-y)):

$$
f(K) = \max\!\left(f_{\min},\; 1 + \frac{\beta}{\alpha}\,K\right),
\qquad \alpha = 0.706~\mathrm{m/s},\quad \beta = -0.057~\mathrm{m^2/s},\quad f_{\min} = 0.1 .
$$

Speed falls linearly until the floor \(f_{\min}\) is reached at
\(K \approx 11.1\) 1/m. Beyond that point, denser smoke does not slow the
agent further. Because the law and constants match FDS+Evac, a difference
between the two tools downstream of speed cannot come from the speed law.

The alternative is the law of
[Fridolf et al. (2019)](https://doi.org/10.1016/j.tust.2019.04.016), fitted to
individual walking speeds measured in smoke-filled tunnels. It
works through the sighting distance of Jin, \(S = C/K\) [m], where \(C\) [-] is
3 for a reflective sign and 8 for a light-emitting one:

$$
f(S) = \frac{S}{S + 2~\mathrm{m}} .
$$

This law is steeper in light smoke and has no floor. It is available from
Python only, as `SmokeSpeedConfig(speed_law="fridolf")`; `run.py`, the scenario
JSON and the web GUI always use the Frantzich–Nilsson law (see
[the parameter split](#the-parameter-split) below).

![Speed factor v/v0 against extinction coefficient K for the Frantzich–Nilsson law and for Fridolf's law with C = 3 and C = 8](/images/concepts/speed_laws.png)

*Figure 1. Speed factor \(v/v_0\) [-] against extinction coefficient K [1/m].
Solid blue: Frantzich–Nilsson with the default constants, floor 0.1 reached at
K = 11.1 1/m. Orange: Fridolf et al. (2019) with C = 3 (solid) and C = 8
(dashed). The curves are evaluated through `SmokeSpeedModel`.
Script: `scripts/figures/speed_laws.py`.*

### Tenability: a brake and a stop

Smoke affects an occupant in two ways. Some effects depend only on what the
agent meets now. Others accumulate into a dose. pyFDS-Evac keeps the two apart.
Speed varies smoothly with what the agent meets at the current moment, and dose
acts only as a switch:

$$
v_i = v_{0,i}\; f(K)\; g(\mathrm{FIC})\;
\mathbb{1}\!\left[\mathrm{FED}_i < D_i\right]\;
\mathbb{1}\!\left[\mathrm{FED}_{\mathrm{heat},i} < D_{\mathrm{heat},i}\right].
$$

The brake is the product \(f(K)\,g(\mathrm{FIC})\). The fractional irritant
concentration (FIC) [-] of Purser sums seven irritant gases, each divided by
its own reference concentration. It slows the agent through
\(g = \max(0.3,\; 1 - 0.7\,\mathrm{FIC})\). FIC is a concentration, not a dose:
the factor is recomputed from the FIC at the agent's current position at every
update while FIC is positive. When the sampled FIC drops to exactly zero, the
factor is not recomputed and the last value stays in force, so an agent that
leaves an irritant plume into clean air keeps its last irritant slowdown. ISO
13571 calls this quantity the fractional effective concentration (FEC).

The stop is the fractional effective dose (FED) [-]. The toxic-gas FED uses
the Purser equations as written out in the FDS+Evac guide: CO, HCN and NOₓ
narcosis and an irritant term, scaled by CO₂ hyperventilation, plus hypoxia.
Up to 12 gas species enter it (CO, CO₂, O₂, HCN, NO, NO₂, HCl, HBr, HF,
SO₂, acrolein and formaldehyde). This is not the ISO 13571 form, which keeps
irritants in the separate FEC and does not add them into the FED.
Convective heat accumulates in a second, separate dose, \(T^{3.4}/(5\times10^{7})\)
per minute with *T* in °C (Society of Fire Protection Engineers (SFPE)
Handbook, 5th ed., Eq. 63.44). It is read from
an FDS `TEMPERATURE` slice. A deck without that slice runs without a heat
dose, and the run log says so. The two doses are never added. Each agent draws its own threshold for each track, \(D_i\) and
\(D_{\mathrm{heat},i}\), from a log-normal distribution with median 1 and
log-scale spread 0.94. For the gas dose this spread is fitted to the
incapacitation fractions of NIST TN 1797; the heat dose reuses it without a
data basis of its own. When either dose crosses its threshold, the agent's
speed is set to zero for the rest of the run, and it stays in place as an
obstacle. FED never enters \(v\) before that moment. Both rules are active by
default when a gas FED model is loaded. `--disable-tenability` turns off the
FIC slowdown and both stops, the gas dose and the heat dose; the doses are
still computed and logged. For results comparable with FDS+Evac, where every
agent stops at FED = 1, use `--incapacitation-mode deterministic`.

Two consequences matter when you read a result. First, an FED that stays below
the threshold leaves the agent's walking speed unchanged, however close it
comes.
Second, the heat dose only incapacitates. It does not slow agents and it does
not affect route choice, and radiant heat is not modelled at all. See the
[smoke-speed model](/models/smoke-speed.md) and the
[FED model](/models/fed.md) for the equations and defaults.

![Three panels: f(K) against K, g(FIC) against FIC, and their product as a heat map over K and FIC](/images/concepts/tenability_speed_curves.png)

*Figure 2. The brake. Left: Frantzich–Nilsson factor f(K) [-] against K [1/m],
floor 0.1. Middle: irritant factor g(FIC) [-] against FIC [-], floor 0.3.
Right: the product f(K)·g(FIC) [-] over K and FIC, with contours at 0.03
(both floors), 0.25, 0.5 and 0.75. FED does not appear on these axes; it only
sets the speed to zero at the agent's threshold.
Script: `scripts/generate_tenability_curves.py`.*

## Route choice

### Routes live on a stage graph

Routes are paths on a directed graph of stages. Its nodes are the spawn areas,
checkpoints and exits of the scenario. Each edge carries a polyline that
JuPedSim's routing engine computes along the walkable area, so it follows the
corridors the agent would walk and not a straight line through walls. Smoke is
sampled along this polyline, with samples at most \(\Delta s = 2\) m apart. The
mean extinction of an edge, \(\bar K_{uv}\) [1/m], is the arithmetic mean of
its samples. This is the discrete Beer–Lambert mean of
[Börger et al. (2024)](https://doi.org/10.1016/j.firesaf.2024.104269),
Eqs. 8–9, applied to a walked path instead of a line of sight.

A route is measured from where the agent stands: the walkable distance to the
next node plus the rest of the path. Its mean extinction \(\bar K_k\) is the
length-weighted mean over its edges, and \(L_k\) [m] is the distance still to
walk. Each agent re-decides its route at a fixed interval: 1 s when started
from `run.py`, 10 s for a `RerouteConfig` built in Python without arguments. The staggered start times spread the decisions over the
interval. A decision is not remembered: every re-decision starts again from
the current field.

![Plan view of a room with an internal wall; a dashed straight line from agent to exit crosses the wall, a solid walked polyline goes around it with sample points coloured by extinction](/images/concepts/stage_graph.png)

*Figure 3. Schematic with a prescribed toy extinction field, not a simulation.
The dashed straight line from agent to exit passes through a wall. The solid
polyline is the walked route. Its dots are the samples, spaced at most 2 m
apart and coloured by the extinction K [1/m] at the time the agent would reach
them at 1.3 m/s. \(d_W\) is the walkable distance from the agent to the first
node. Script: `scripts/figures/stage_graph.py`.*

### The exposure gate

Under the default `"gate"` cost model, one quantity carries all of the smoke
reasoning: the optical depth along the walk,

$$
\tau_k = \bar K_k \, L_k \quad [-].
$$

The pipeline has three steps. First, a shortest-path search finds one path to
each exit, with every edge weighted by its own optical depth
\(\bar K_{uv} L_{uv}\). The path to each exit is therefore the least-smoky path,
and in clear air it is the shortest path. This search uses the field at the
decision time. Second, each candidate route is re-evaluated with anticipation:
each edge is sampled at the time the agent would reach it, estimated at the
router's unimpeded speed. By default the router sees the whole future of the
FDS solution, so the result is an upper bound on how well an occupant could
route. Third, the gate refuses a route when \(\tau_k\) exceeds
\(\tau_{\max} = 6\). A projected FED above 1 at arrival is a separate veto. The
surviving routes are ranked by \(\tau_k\), cleanest first. Travel time breaks
ties, so in clear air, where every \(\tau_k\) is zero, the model reduces to the
nearest exit.

Because \(\tau\) already contains the distance, a long clean route can beat a
short smoky one, but a slightly cleaner route cannot divert an agent for
free. Hysteresis keeps agents from switching on marginal differences. A rival
exit must come in under \(0.8\,\tau_{\max}\). The current exit's \(\tau\) is
discounted by 0.9 when ranking. A switch needs a clear margin in \(\tau\). If
every route is refused, the agent still moves and takes the route with the
least optical depth, keeping its current route unless a rival's smokiest
stretch is clearly milder. Irritants and heat do not enter route choice.
FIC and the gate respond to the same smoke, so routing on both would count it
twice.

The threshold 6 comes from the door test of FDS+Evac, in which a door is
dropped when \(\bar K d / 6 \ge 1\), with Jin's constant 3. Here it is applied to a
Beer–Lambert integral along a walked path. That measures how much smoke the
agent walks through, not how far it can see, and the two agree only on a
straight corridor. The value 6 is inherited and cited. It has not been
calibrated as an exposure budget. pyFDS-Evac also uses \(\tau\) to order all
routes, where FDS+Evac ranks on smoke only in its last-resort branch, so the
gate is a departure from FDS+Evac and not a reproduction of it. The
[routing page](/models/routing.md) gives the full pipeline, the alternative
`"additive"` cost model and a measured case where agents oscillate between
exits.

![Top: plan view with three routes from one agent to exits A, B and C around a smoke plume. Bottom: bar chart of optical depth per route against the budgets 4.8 and 6](/images/concepts/exposure_gate.png)

*Figure 4. Schematic with a prescribed toy plume, not a simulation. Top: three
candidate routes from one agent, sampled along each walk and coloured by
extinction K [1/m]. Bottom: optical depth \(\tau\) [-] of each route against the
budget \(\tau_{\max} = 6\) (solid, the current exit and the initial choice) and
\(0.8\,\tau_{\max} = 4.8\) (dashed, any other exit). Route C (\(\tau \approx 6.2\))
is refused. Route B (\(\tau \approx 1.3\)) ranks first although it is the longest
walk. Walk times use the router's speed, 1.3 m/s times the Frantzich–Nilsson
factor at the route mean K. Script: `scripts/figures/exposure_gate.py`.*

## Wayfinding

### A sign is more than a position

In pyFDS-Evac, what an agent knows about the building depends on the signs it
can read. Each exit, checkpoint and waypoint carries a sign
descriptor \(\{x, y, \alpha_s, C\}\). Here \((x, y)\) [m] is the position of the sign,
\(\alpha_s\) [°] is a compass bearing that gives the side from which the sign
can be read, and \(C\) [-] is Jin's constant (sign key `c`), 3 by default. A node
without an authored sign receives a reflective sign at its centroid that can be
read from every direction.

Legibility is computed by [fdsvismap](https://github.com/FireDynamics/fdsvismap)
from the FDS extinction field when `run.py` is given `--fds-dir`, and from clear
air otherwise. The model is built when the deck has discovery agents, and
`--no-visibility` turns sight gating off. A sign
is legible from a floor cell when its visibility \(C/\bar K\) along the line of
sight, capped at the domain diagonal and scaled by the viewing angle, reaches the distance to
the sign. Walls block the line of sight. pyFDS-Evac builds this map once per
run, and `--vis-cache` stores it for reuse between runs. During the run, it asks only whether the sign of a node is legible
from the agent's cell at the current time.

Legibility decides what an agent **knows**, not whether a route is allowed. An
exit whose sign the agent has never read is absent from its graph. It is not
present and refused.

![Two 30 m corridors, each with an exit at both ends; left, the near sign faces the agents and all 40 go to the near exit; right, the near sign faces away and all 40 walk to the far exit](/images/concepts/sign_bearing.png)

*Figure 5. Asset `assets/exit_visibility_alpha`: a 4 m × 30 m corridor in clear
air, 40 agents with familiarity 0 spawned between y = 8 m and 12 m, an exit at
each end. The two configurations differ only in the bearing of the near exit's
sign. Facing the agents (0°), all 40 agents took the near exit. Facing away
(180°), all 40 walked to the far exit, and egress took 26.0 s instead of
18.2 s. Both configurations use base seed 1904; the outcomes are as recorded
in the asset README, and the script draws them without rerunning the asset.
Script: `scripts/figures/sign_bearing.py`.*

### Per-agent cognitive maps

Each agent carries a cognitive map, defined here as the graph of stages it
knows, not in the psychological sense. Routing runs only on this subgraph. The
`familiarity` key of a distribution group sets how the map starts. With
`"full"`, the default, the agent knows the whole stage graph from the start, as
trained staff would. With `"discovery"`, it knows only its spawn node and the
neighbours whose signs are legible from the centroid of the spawn area. A
number *p* between 0 and 1 sits between the two tiers: each exit enters the map
at spawn with probability *p*, drawn from the run's seed, so a population can
be a gradient rather than two groups. An `entrance` key names an exit that the agent always knows, such as the door
it came in by. Setting familiarity separately for each exit is not supported
([#136](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/136)).

A map grows in three ways. At spawn, neighbours whose signs are legible from
the centroid of the spawn area are added. On arrival at a node, neighbours
legible from the agent's position are added. At each re-decision, neighbours legible from where
the agent stands are added. A learned corridor is known in both directions, so
an agent can always retrace its steps out of a dead end. If no exit is known,
the agent heads for the nearest known node it has not yet visited. When every
known node has been visited, it patrols the nodes it knows, because a new
position can bring a new sign into view.

![Four panels of a T-shaped corridor showing which nodes and edges an agent knows: at spawn, at the junction, with smoke hiding exit B, and for a fully familiar agent](/images/concepts/cognitive_map.png)

*Figure 6. Schematic of the rules on a T-shaped corridor; the geometry is
illustrative, not an asset. Filled nodes and solid edges are in the agent's
map, and hollow nodes and dashed edges are not. (1) A discovery agent at spawn
knows the spawn node and the junction, whose sign is legible. (2) At the
junction both exit signs become legible, and both exits enter the map.
(3) Smoke fills the right arm; exit B stays in the map, and the router picks
exit A. (4) A fully familiar agent knows the whole graph at t = 0.
Script: `scripts/figures/cognitive_map.py`.*

### The map remembers

Nothing leaves a cognitive map. An exit learned while its sign was legible
stays known and routable after smoke or distance makes the sign illegible.
This separates a map from a visibility query: with a query alone, the agent
would forget the exit as soon as it lost sight of it.

The cognitive map limits topology, not knowledge of the smoke. To choose among
the exits it knows, a discovery agent integrates \(\tau\) over the whole
remaining route, including legs it has never walked and, with anticipation,
times that have not yet happened. Its route choice is therefore a best case
over its known subgraph, not a model of what it can perceive
([#125](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/125)). The
[visibility page](/models/visibility.md) lists the command-line settings for
sight gating and what each one means.

![Six copies of a corridor with an agent probe at y = 4, 10, 14, 20, 26 and 30 m; the side exit is unknown below the legibility band, known inside it, and still known above it](/images/concepts/map_memory.png)

*Figure 7. Asset `assets/cognitive_map_memory`: a 4 m × 32 m corridor with an
exit at the end and a side exit at y = 20 m whose sign is legible only between
y = 12.5 m and 27.5 m (green band). A discovery agent was placed at six probe
positions (a probe, not a walk), and the panels show what its map held and
which exit it would take there. At y = 30 m the side sign was no longer
legible, but the exit was still in the map and still chosen. Outcomes as
recorded in the asset README and pinned by tests; the script draws them.
Script: `scripts/figures/map_memory.py`.*

## The parameter split

Some parameters with the same name live in two places, and they do different
things. The walking-speed parameters (`speed_law`, `alpha`, `beta`,
`min_speed_factor` and `visibility_factor_c`) are fields of `SmokeSpeedConfig`.
`run.py` and the web GUI build that object with its defaults, so every run they
start uses the Frantzich–Nilsson law with \(\alpha = 0.706\) m/s,
\(\beta = -0.057\) m²/s and \(f_{\min} = 0.1\). Another law or other coefficients require building the
model in Python and passing it to `run_scenario()`.

The `routing` block of the scenario JSON accepts `alpha`, `beta` and
`min_speed_factor` with the same defaults. They only set the speed factor the
router uses to estimate travel time when it prices a route. Setting
`routing.alpha` changes which route an agent prefers, but not how fast it walks
in smoke. The same holds for speed itself. The router prices routes at
`routing.base_speed_m_per_s` (1.3 m/s), while an agent walks at its own
\(v_0\) (1.2 m/s by default, for every operational model). The router always uses the linear law, even when
agents walk with Fridolf's law. See [Limitations](/docs/limitations.md).

## Notation

| Symbol | Meaning | Unit | Code name |
|---|---|---|---|
| *K* | Extinction coefficient at a point (FDS `SOOT EXTINCTION COEFFICIENT`) | 1/m | `extinction_per_m` |
| \(\bar K\) | Mean extinction along an edge or a route | 1/m | `k_avg`, `k_ave_route` |
| *S* = *C*/*K* | Sighting distance (Jin); *V* in Fridolf's notation | m | — |
| *C* | Jin's constant: 3 reflective, 8 light-emitting | - | `visibility_factor_c`, sign `c` |
| \(v_0\) | Unimpeded desired speed of an agent | m/s | `v0` (distribution group) |
| *f*(*K*) | Smoke speed factor | - | `speed_factor` |
| \(\alpha\), \(\beta\) | Frantzich–Nilsson coefficients | m/s, m²/s | `alpha`, `beta` |
| \(f_{\min}\) | Floor of the smoke speed factor | - | `min_speed_factor` |
| FIC | Fractional irritant concentration (Purser; related to, but not the same as, ISO 13571 FEC) | - | `fic` |
| *g*(FIC) | Irritant speed factor, \(\max(0.3, 1 - 0.7\,\mathrm{FIC})\) | - | `fic_min_factor`, `fic_alpha` |
| FED | Fractional effective dose, toxic gases | - | `fed` |
| \(\mathrm{FED}_{\mathrm{heat}}\) | Fractional effective dose, convective heat | - | heat FED |
| \(D_i\), \(D_{\mathrm{heat},i}\) | Incapacitation threshold of agent *i*, log-normal, median 1 | - | `fed_threshold`, `heat_fed_threshold` |
| *T* | Gas temperature | °C | `TEMPERATURE` slice |
| \(L_k\) | Walkable distance still to go on route *k* | m | `effective_length` |
| \(\tau_k = \bar K_k L_k\) | Optical depth along route *k* | - | `tau_route` |
| \(\tau_{\max}\) | Refusal budget for \(\tau\), default 6 | - | `tau_max` |
| \(\Delta s\) | Maximum spacing of smoke samples along a polyline | m | `sampling_step_m` |
| \(\alpha_s\) | Bearing of a sign, degrees clockwise from north | ° | sign `alpha` |

The same code name `alpha` is used for the Frantzich–Nilsson coefficient, for
the irritant slope `fic_alpha` and for the sign bearing; the table keeps them
apart. In FDS+Evac, \(\tau\) is the relaxation time of the movement model. On
these pages \(\tau\) is always the dimensionless optical depth. "Gate" is used
in two senses only: the exposure gate (the route-cost gate) that refuses a
route, and sight gating, which decides whether a sign is legible and so what
enters the cognitive map. The dose does not gate anything; it stops the agent.

## Further reading

- The talk: [slides](https://pedestriandynamics.org/pyFDS-Evac/talks/visibility-seminar-2026/)
  and [PDF](https://pedestriandynamics.org/pyFDS-Evac/talks/pyFDS-Evac_visibility_seminar_2026.pdf), Visibility
  Seminar 2026, University of Wuppertal, 25 September 2026.
- Model pages: [smoke speed](/models/smoke-speed.md), [FED](/models/fed.md),
  [routing](/models/routing.md), [visibility and cognitive maps](/models/visibility.md),
  and [verification](/models/verification.md).
- [Limitations](/docs/limitations.md): what is not modelled, and which
  parameters are library-level.
