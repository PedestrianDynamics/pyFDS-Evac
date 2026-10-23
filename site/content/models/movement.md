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
  Report both with any result.
- **Not recommended**: `AnticipationVelocityModel`
  ([#758](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/758)),
  `GeneralizedCentrifugalForceModel`, and `WarpDriverModel`, which
  completes some runs only by letting agents overlap.

pyFDS-Evac does not yet detect or report agents that stand still for the
rest of a run
([#760](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/760)).
A stuck run shows as agents still inside at `max_simulation_time`.

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
`"transitions": []`, and keeps its `journeys_v2`.
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
| CFSM | 8/13; 5 deadlock | 0/3; 0–1 of 150 out | 150/150 | 60/60 |
| CSM V2 | as CFSM | as CFSM | as CFSM | as CFSM |
| SFM | 4/13; 1 deadlock, 8 with 1 agent left | 3/3, mean 86 s | 147/150; 3 deadlock | 53/60; 7 deadlock |
| AVM | 0/13 | 0/3 | 90/150 | 0/60 |
| GCFM | error at spawn | error at spawn | 4/4, 3 overlap; 4 runs made | not run |
| WarpDriver | 13/13; 3 overlap | 3/3; 3 overlap | 150/150 | 60/60; 1 overlap |

**`CollisionFreeSpeedModel`.** Agents stop at contact: the smallest
distance between two centres is 1.00 × 2r, and between a centre and a wall
about one radius. There is no side-step and no push, so a pair that meets
face to face waits for the rest of the run. On HUT at r = 0.15 m, 5 of 13
seeds jam; which seeds jam changes between commits
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
(mean 86 s) by pushing. The peak speed is 2.65 m/s at a desired speed of
1.2 m/s, about 2.2 times the desired speed, and 2.41 m/s on Familiarity 20.
The friction is 0 in every run
([#635](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/635)). On
HUT, 4 of 13 runs complete. One meets the deadlock criterion. In the other
8 a single agent is left, standing still just south of the 0.75 m gap at
the same spot in every seed; the cause is not established. The familiarity deck uses this model, and
its doorway deadlocks are those of
[#359](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/359#issuecomment-6110207162):
3 of 150 and 7 of 60 runs.

**`AnticipationVelocityModel`.** Not recommended
([#758](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/758)).
Its model-level parameters are commented out in the mapping, so the model
runs at JuPedSim's defaults. pyFDS-Evac never sets its `rng_seed`, and JuPedSim
draws a new one each time it is imported, so a run cannot be reproduced
from the run seed. Agent centres come within 0.03–0.18 r of walls.

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

**`AnticipationVelocityModel`**: no model-level value is passed, so
`pushout_strength` is JuPedSim's 0.3 and `rng_seed` is drawn at import
([#758](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/758)).
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

## Limitations

- The deadlock rates above come from three geometries and a few seeds each.
  A smaller radius does not remove the `CollisionFreeSpeedModel` jam: HUT
  at 0.15 m still jams in 5 of 13 seeds.
- `SocialForceModel` pushing has not been validated against measured
  counterflow. On the counterflow case its peak speed exceeds the desired
  speed by a factor of about 2.
- pyFDS-Evac has no counterflow algorithm of its own
  ([Model comparison › Movement model](/docs/model-comparison.md#1-movement-model)).
- The open defects are listed under
  [Limitations › Known defects](/docs/limitations.md#known-defects).
