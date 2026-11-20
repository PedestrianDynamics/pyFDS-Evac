---
title: "Movement models"
weight: 6
---

> [!NOTE]
> This page covers the JuPedSim operational model that moves the agents:
> which models a deck can select, the values pyFDS-Evac passes to each, and
> how each one behaves when agents meet in a door or head-on. The models
> themselves are described on
> [JuPedSim's model pages](https://www.jupedsim.org/stable/pedestrian_models/index.html).

A deck selects its movement model with `simulationParams.model_type`
([Scenario JSON › Simulation settings](/docs/scenario-json.md#simulation-settings)).
The default is `CollisionFreeSpeedModel`. Smoke, gas dose and routing act on
top of the movement model and are the same for every choice.

## Choosing a model

No supported model passes all three test cases below, so the default stays
`CollisionFreeSpeedModel`.

- **Unidirectional egress** (everyone heading out, doors and corridors):
  use `CollisionFreeSpeedModel`. Accept that a crowd can jam in a narrow
  opening, check that every run completes before you read an evacuation
  time, and run several seeds.
- **Dense head-on counterflow**: `SocialForceModel` clears the 50 % case
  below (Iso-06-counterflow-50, 3 seeds; pushing not validated against
  measured counterflow). Agents then reach about 2.2 times their desired
  speed, and the friction is 0
  ([#635](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/635)).
  Report both with any result. The 100 % case and `WarpDriverModel` are
  in [Counterflow with hard journeys](#counterflow-with-hard-journeys).
- **Not recommended**: `AnticipationVelocityModel`
  ([#758](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/758)),
  `GeneralizedCentrifugalForceModel`, and `WarpDriverModel`, which
  completes some runs only by letting agents overlap.

A run whose whole crowd stands still for 100 s stops with `end_reason`
`"deadlock"` and reports the stuck agents
([#760](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/760));
the jam itself is not cleared.

## Deadlock behaviour

### Test cases

> [!IMPORTANT]
> **Scope.** A study of three cases in clear air, at main `47cfeec5` with
> JuPedSim 1.4.2. Every model ran with pyFDS-Evac's mapping below, with only
> `model_type` changed, except `CollisionFreeSpeedModelV2`, which needed
> `strength_neighbor_repulsion` 2.6 and `range_neighbor_repulsion` 0.1 in
> the deck ([#757](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/757)).
> Values that pyFDS-Evac does not set keep JuPedSim's defaults. A run is a
> deadlock when it is incomplete and at least two of its agents moved less
> than 0.03 m over the last 100 s. A run overlaps when its closest pair of
> agents comes within 0.9 × 2r, centre to centre. These are
> implementation checks on three geometries. They do not validate any model
> against measured crowd movement, and the rates have not been shown to hold
> for other geometries, densities or seeds.

| Case | Deck | Agents | Radius | Seeds |
|---|---|---|---|---|
| HUT | `HUT_Library`, imported from FDS+Evac | 120 | 0.15 m | 1–13 |
| Counterflow 50 % | Iso-06-counterflow-50 of jupedsim-web-community (`82404ee`) | 150 | 0.15 m | 1–3 |
| Familiarity 5 | `familiarity_test_no_journey` | 5 | 0.2 m | 1–150 |
| Familiarity 20 | `familiarity_test_no_journey` | 20 | 0.2 m | 1–60 |

The counterflow deck is patched with `"journeys": []` and
`"transitions": []`, and keeps its `journeys_v2`. At the study's commits
that patch kept the counterflow. Since
[#504](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/504) each
group takes its nearest exit instead, so on current main the counterflow
column is reproduced as in
[Counterflow with hard journeys](#counterflow-with-hard-journeys), which
gives the same SFM mean of 86 s.
`SocialForceModel` ran at the radius of each deck. Its closer counterpart
of the FDS+Evac body is the enclosing circle R<sub>d</sub>, 0.255 m for an
adult ([Limitations › What is not modelled](/docs/limitations.md#what-is-not-modelled)).
The study is reported on
[#706](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/706#issuecomment-6110206792),
[#745](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/745#issuecomment-6110206980)
and
[#359](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/359#issuecomment-6110207162).

### Results

Runs completed per case, with what stopped the others, and the runs that
overlap. No CFSM, CSM V2, SFM or AVM run overlaps; the closest SFM pair on
the counterflow is 0.99 × 2r. CFSM is
`CollisionFreeSpeedModel`, CSM V2 `CollisionFreeSpeedModelV2`, SFM
`SocialForceModel`, AVM `AnticipationVelocityModel`, GCFM
`GeneralizedCentrifugalForceModel`.

| Model | HUT | Counterflow 50 % | Familiarity 5 | Familiarity 20 |
|---|---|---|---|---|
| CFSM | 6/13; 7 deadlock | 0/3; 0–1 of 150 out | 150/150 | 60/60 |
| CSM V2 | as CFSM | as CFSM | as CFSM | as CFSM |
| SFM | 4/13; 1 deadlock, 8 with 1 agent left | 3/3, mean 86 s | 147/150; 3 deadlock | 53/60; 7 deadlock |
| AVM | 0/13 | not re-measured | not re-measured | 8/60 |
| GCFM | error at spawn | error at spawn | 4/4, 3 overlap; 4 runs made | not run |
| WarpDriver | 13/13; 3 overlap | 3/3; 3 overlap | 150/150 | 60/60; 1 overlap |

The AVM and CFSM HUT and Familiarity 20 figures are from `1fc317db`
(seeds 1–13 and 1–60). The AVM counterflow and Familiarity 5 cells were
measured with the 0.1 m wall buffer (`47cfeec5`) and are not re-measured.

**`CollisionFreeSpeedModel`.** Agents stop at contact: the smallest
distance between two centres is 1.00 × 2r, and between a centre and a wall
about one radius. There is no side-step and no push, so a pair that meets
face to face waits for the rest of the run. On HUT at r = 0.15 m, 7 of 13
seeds jam (`1fc317db`); which seeds jam changes between commits
([#706](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/706#issuecomment-6110206792)).
On the 50 % counterflow the two streams lock, with one agent out in seed 1
and none in seeds 2 and 3
([#745](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/745#issuecomment-6110206980)).
The familiarity deck completes every run
([#359](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/359#issuecomment-6110207162)).

**`CollisionFreeSpeedModelV2`.** With the repulsion values of
`CollisionFreeSpeedModel` supplied in the deck, it gives the same numbers on
every case. A deck that omits `strength_neighbor_repulsion` or
`range_neighbor_repulsion`, which covers every deck imported with
`pyfds-evac init` and every jupedsim-web-community deck, gets the
`CollisionFreeSpeedModel` value 2.6 or 0.1 m for each missing key
([#757](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/757)).

**`SocialForceModel`.** It clears the 50 % counterflow in all 3 seeds
(mean 86 s) by pushing. With hard journeys it clears both counterflow
cases ([below](#counterflow-with-hard-journeys)). The peak speed is
2.65 m/s at a desired speed of 1.2 m/s, about 2.2 times the desired
speed, and 2.41 m/s on Familiarity 20.
The friction is 0 in every run
([#635](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/635)). On
HUT, 4 of 13 runs complete. One meets the deadlock criterion. In the other
8 a single agent is left, standing still just south of the 0.75 m gap at
the same spot in every seed; the cause is not established. The familiarity deck uses this model, and
its doorway deadlocks are those of
[#359](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/359#issuecomment-6110207162):
3 of 150 and 7 of 60 runs.

**`AnticipationVelocityModel`.** Not recommended.
The model is seeded from the run seed
([#758](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/758)).
pyFDS-Evac sets its `wall_buffer_distance` to 0.0 m; JuPedSim's default is
0.1 m. Neither value has a published source, and Xu, Chraibi and Seyfried
(2021, *Transp. Res. C* 133:103464) model no walls or doors. At 0.0 m an
agent stops about r from a wall, not r + 0.1 m. With 0.1 m, agents stopped
r + 0.1 m from a wall and could not reach an exit 0.2 m deep that sits flush
with it, because an exit counts as reached within 0.03 m of its polygon
([#975](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/975)). In a
10 × 6 m room with such an exit and r = 0.15 m, 0 of 6 agents left at 0.1 m
in each of seeds 3 and 5, and 6 of 6 at 0.0 m, the last at 6.69 s and 7.62 s.

The change does not make the model complete the decks. On `1fc317db`,
going from 0.1 m to 0.0 m changed the runs as follows:

| Deck | Complete at 0.1 m | Complete at 0.0 m | Agents out at 0.1 m → 0.0 m | CFSM completes |
|---|---|---|---|---|
| HUT, seeds 1–13 | 0/13 | 0/13 | 700 → 870 of 1560 | 6/13 |
| Familiarity 20, seeds 1–60 | 0/60 | 8/60 | 50 → 535 of 1200 | 60/60 |

On a plain 1.2 m door without pyFDS-Evac, JuPedSim's model completed 23 of
30 seeds at 0.1 m and 29 of 30 at 0.0 m; `CollisionFreeSpeedModel`
completed 30 of 30. The model still jams at that door in 6 to 7 of 30
seeds at 0.1 m (upstream issue pending). It also comes close to walls at
corners and door jambs: the closest sampled centre-to-wall distance falls
from 0.063 r to 0.041 r on HUT and from 0.105 r to 0.039 r on Familiarity
20, and in 67 of the 73 runs at 0.1 m the closest point lay within 1 r of a wall
vertex. Positions are sampled every 0.1 s, so the true minimum can be
smaller. The cause is not established.

All other values stay at JuPedSim 1.4.2's defaults. Xu et al.'s Table 3
parameters were run and not adopted: with a 0.0 m buffer they raised HUT
from 0 to 2 of 13, lowered Familiarity 20 from 8 to 6 of 60 and left the
door at 29 of 30; with 0.1 m they lowered the door from 23 to 17 of 30.

**`GeneralizedCentrifugalForceModel`.** Not recommended. It refuses most
spawns and overlaps when it runs. It fails at spawn on HUT and the
counterflow deck in every seed, with "too close to geometry boundaries" on
HUT and "outside of accessible area" on the counterflow. On Familiarity 5
the 4 runs made complete, and 3 of them overlap, with two centres as close
as 0.12 × 2r.

**`WarpDriverModel`.** It completes every run, some only by letting
agents overlap: 3 of 13 HUT runs (centres as close as 0.41 × 2r), all 3
counterflow runs (0.67 × 2r) and 1 of 60 Familiarity 20 runs
(0.35 × 2r); on every case agent centres come closer
than half a radius to a wall in some runs. `station_fahy` uses this
model; its choice is under review in
[#761](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/761).

`CollisionFreeSpeedModelV3` is in JuPedSim 1.4.2 and is not offered by
pyFDS-Evac
([#759](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/759)).
A deck that names it stops with a `ValueError`.

**At run time.** `pyfds_evac/core/deadlock.py` applies the study's
definition during a run: the thresholds are the same, 0.03 m of net
displacement over 100 s. The run-time rule is stricter: it needs *every*
counted agent to be still, not "at least two", so a working bottleneck with
a few agents creeping through never fires it. It also holds back while any
agent is held by design (pre-movement, a waiting stage, a desired speed of
0, a flow source that can still spawn, an exit yet to open), and it stops the
run while it is under way instead of judging the end state. The counts of
runs that end `deadlock` are therefore not comparable with the study's
counts. The run then stops with `end_reason` `"deadlock"`, unless a gas or heat
FED model is on and a stuck agent's dose is still rising: the run goes on and
integrates the dose ([#988](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/988)).
pyFDS-Evac reports the jam and does not clear it. See [Reading the results](/docs/outputs.md#reading-the-results).

### Counterflow with hard journeys

Since [#504](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/504)
the counterflow decks keep their counterflow only with their two
journeys, each given a transition
`{"from": <distribution>, "to": <exit>, "journey_id": <journey>}` and
`"allocation": "hard"`. The decks are Iso-06-counterflow-50 (150 agents)
and -100 (200 agents) of jupedsim-web-community (`82404ee`), clear air,
radius 0.15 m, desired speed 1.2 m/s, seeds 1–3, run at `7689907e`
([#745](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/745)). The
closest pair is the smallest centre distance over all frames, in units
of 2r; the peak speed is the largest frame-to-frame speed of any agent.

| Model | Case | Result (seeds 1 / 2 / 3) | Closest pair | Peak speed |
|---|---|---|---|---|
| CFSM | 50 % | `deadlock`, stopped at 189 / 197 / 250 s (stuck since 89 / 97 / 150 s); 1, 0, 0 of 150 out | 1.00 × 2r | 1.20 m/s |
| CFSM | 100 % | `deadlock`, stopped at 180 / 238 / 194 s (stuck since 80 / 138 / 94 s); 0 of 200 out | 1.00 × 2r | 1.20 m/s |
| SFM | 50 % | 150/150 in 82.4 / 92.5 / 82.8 s | 0.96–0.99 × 2r | 2.38–2.65 m/s |
| SFM | 100 % | 200/200 in 109.0 / 95.3 / 111.2 s | 0.93–0.96 × 2r | 2.25–2.65 m/s |
| WarpDriver | 50 % | 150/150 in 61.5 / 60.8 / 60.3 s | 0.63–0.70 × 2r | 1.20 m/s |
| WarpDriver | 100 % | 200/200 in 65.7 / 64.9 / 68.3 s | 0.20–0.60 × 2r | 1.20 m/s |

`SocialForceModel` clears both cases by pushing, at up to 2.2 times the
desired speed. `WarpDriverModel` keeps to the desired speed but clears
them by letting agents overlap, down to 0.20 × 2r on the 100 % case.
Neither result shows that a model handles counterflow; they are
implementation checks of what each model does on two decks.
`AnticipationVelocityModel` has no seeded run with hard journeys on this deck,
`GeneralizedCentrifugalForceModel` fails at spawn on this geometry, and
`CollisionFreeSpeedModelV2` gives the CFSM numbers, so they are not
listed.

**What a raw-CFSM prototype shows.** A raw JuPedSim 1.4.2
`CollisionFreeSpeedModel` prototype of Iso-06-counterflow-50 (no
pyFDS-Evac routing, exits as direct targets; 2026-11-15,
[#745](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/745#issuecomment-6894793321)) ended with no free lane: about 149 of 150 agents stood mixed
across the full width of the 2 m × 10 m corridor at about 7 agents/m².
A keep-right heading offset cleared 8, 2 and 0 of 150 agents in seeds 1–3
(trigger 1.0 m, offset 0.3 m) and 6 of 150 at 2.0 m / 0.6 m; at 3.0 m /
0.9 m it moved 75 of 150 (seed 1, unfinished at 200 s). A per-agent target
jitter of ±0.8 m cleared 0 of 150 (seeds 1–2). Neither reopened a lane at
a defensible size. This does not show that no other rule could, and the
100 % deck was not run. `SocialForceModel` finished the prototype in 69
and 79 s (seeds 1–2). In the pyFDS-Evac runs above it clears the corridor
by pushing (peak 2.25–2.65 m/s against v0 = 1.2 m/s) and `WarpDriverModel`
by overlap, so no supported model is shown to handle dense counterflow.

Two agents exactly head-on in a 12 m strip stop about 0.42 m apart, centre
to centre (1.4 × 2r, r = 0.15 m), because `CollisionFreeSpeedModel` stops
at its time-gap distance; this is not the 1.00 × 2r contact of the dense
case. A lateral offset of 0.02 m lets them pass in strips 0.7 m wide or
wider. The exact-symmetry lock showed up in the Haspel desk rows (0.58 m
gaps) and was removed there by closing each row at one end
(`assets/Haspel/README.md`,
[#959](https://github.com/PedestrianDynamics/pyFDS-Evac/pull/959)).

## Coded mapping

The model is built by `_MODEL_BUILDERS` (`scenario.py`), and each agent's
parameters by `create_agent_parameters` (`simulation_init.py`).
Every model receives the agent's `radius` and `v0` from its spawn area,
0.2 m and 1.25 m/s when the deck sets neither, except
`GeneralizedCentrifugalForceModel`, which receives no radius.

{{< details title="Values passed to each model" closed="true" >}}

Keys are those of `simulationParams` in `config.json`. "JuPedSim" marks a
value that pyFDS-Evac does not pass, so JuPedSim 1.4.2's default applies.

**`CollisionFreeSpeedModel`** (default)

| JuPedSim parameter (deck key) | Value |
|---|---|
| `strength_neighbor_repulsion` (same) | 2.6; JuPedSim's is 8.0 |
| `range_neighbor_repulsion` (same) | 0.1 m |
| `strength_geometry_repulsion` (none) | JuPedSim, 5.0 |
| `range_geometry_repulsion` (none) | JuPedSim, 0.02 m |
| `time_gap`, per agent (none) | JuPedSim, 1.0 s |

**`CollisionFreeSpeedModelV2`**: the repulsion values are per agent.
`strength_neighbor_repulsion` and `range_neighbor_repulsion` are read from
the deck. Each missing key takes the `CollisionFreeSpeedModel` value: 2.6
for the strength (JuPedSim's is 8.0) and 0.1 m for the range
([#757](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/757)).
`time_gap` is fixed at 1.0 s; the wall repulsion keeps JuPedSim's 5.0 and
0.02 m.

**`SocialForceModel`**

| JuPedSim parameter (deck key) | Value |
|---|---|
| `body_force` (`sfm_body_force`) | 120000 |
| `friction` (`sfm_friction`) | 0, whatever the deck says ([#635](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/635)) |
| `reaction_time`, per agent (`relaxation_time`) | 0.5 s |
| `agent_scale`, per agent (`agent_strength`) | 2000 |
| `force_distance`, per agent (`agent_range`) | 0.08 m |
| `obstacle_scale`, per agent (`sfm_obstacle_scale`) | 2000 |
| `mass`, per agent (none) | JuPedSim, 80 kg |

A deck that sets `sfm_friction` above 0 gets a warning, and the run
manifest records the requested and the applied friction.

**`AnticipationVelocityModel`**: `wall_buffer_distance` is 0.0 m, a
pyFDS-Evac choice (JuPedSim's is 0.1 m; see
[above](#deadlock-behaviour)), and `rng_seed` comes from the run seed
([#758](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/758)).
`pushout_strength` is JuPedSim's 0.3. No deck key sets the buffer.
Per agent, `anticipation_time` (1.0 s) and `reaction_time` (0.3 s) come
from the deck keys of the same name, defaulting to JuPedSim's values; the
CollisionFreeSpeedModel keys `T` and `s0` are not read
([#868](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/868)).
`time_gap` is fixed at 1.06 s, and the neighbour repulsion keeps JuPedSim's
8.0.

**`GeneralizedCentrifugalForceModel`**: the model takes
`gcfm_strength_neighbor_repulsion` (0.3),
`gcfm_strength_geometry_repulsion` (0.2),
`gcfm_max_neighbor_interaction_distance` and
`gcfm_max_geometry_interaction_distance` (2.0 m),
`gcfm_max_neighbor_repulsion_force` (9.0) and
`gcfm_max_geometry_repulsion_force` (3.0). Per agent it takes the deck keys `mass`
(1, JuPedSim's default), `tau` (0.5 s), `a_v` (1.0), `a_min` (0.2 m), `b_min` (0.2 m) and
`b_max` (0.4 m). The deck's `radius` is not passed; the body size comes
from `a_min`, `b_min` and `b_max`. JuPedSim 1.4.2 multiplies the driving
and neighbour forces by `mass` and divides their sum by it, but leaves the
wall force unscaled, so a `mass` above 1 weakens only the walls
([#868](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/868)).
Decks exported from the JuPedSim web app carry `"mass": 80`.

**`WarpDriverModel`**: `time_horizon` (2.0 s), `step_size` (0.5 s),
`sigma` (0.3), `time_uncertainty` (0.5), `velocity_uncertainty_x` and
`velocity_uncertainty_y` (0.2), each under the same deck key. All equal
JuPedSim's defaults.

{{< /details >}}

### Wall clearance and flush exits

A model that keeps an agent's centre at least r + c from a wall can leave
an exit that is flush with the wall out of reach. pyFDS-Evac checks this
per exit, with c = 0.0 m for `AnticipationVelocityModel`, 0.02 m for
`CollisionFreeSpeedModel` and `CollisionFreeSpeedModelV2` (JuPedSim's
`range_geometry_repulsion`) and 0 for the other models, whose clearance is
unmeasured. It warns when more than 0.03 m lies between the exit and the
region agent centres can occupy, the walkable area shrunk by the largest
agent radius plus c ([Troubleshooting](/docs/troubleshooting.md)).

## Limitations

- The deadlock rates above come from three geometries and a few seeds each.
  A smaller radius does not remove the `CollisionFreeSpeedModel` jam: HUT
  at 0.15 m still jams in 7 of 13 seeds (`1fc317db`).
- `SocialForceModel` pushing has not been validated against measured
  counterflow. On the counterflow case its peak speed exceeds the desired
  speed by a factor of about 2
  ([Counterflow with hard journeys](#counterflow-with-hard-journeys)).
- The dense lock of `CollisionFreeSpeedModel` is not cleared by the steering
  variants tried in a prototype
  ([Counterflow with hard journeys](#counterflow-with-hard-journeys)).
  pyFDS-Evac adds no counterflow algorithm of its own
  ([Model comparison › Movement model](/docs/model-comparison.md#1-movement-model)).
- The open defects are listed under
  [Limitations › Known defects](/docs/limitations.md#known-defects).
