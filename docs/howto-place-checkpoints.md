---
title: "How do I place checkpoints?"
linkTitle: "How-to: place checkpoints"
weight: 12
aliases: [/docs/howto-place-checkpoints/]
---

A checkpoint is a polygon you draw in `checkpoints.<id>.coordinates`. The
[routing pages](routing.md) call the same nodes *crossings*; this page calls
them checkpoints, after the JSON key.

Checkpoints are the nodes of the route graph between spawn areas and exits.
Agents who explore a building they do not know learn the building from them.
You do not need a checkpoint to get agents through a door: JuPedSim walks
agents along the navigation mesh.

This page shows where to draw checkpoints, how large, and how they join the
route graph. A badly placed checkpoint can change
route lengths, exit choice and the evacuation time. The page ends with a
check list.

## Draw a checkpoint at a door

1. Draw a box across the doorway that reaches into the rooms on both sides.
   Do not stop it at the wall faces.
2. Keep the whole box inside the walkable area.
3. Keep its centre (the *node point*, see [below](#reference-node-point-target-point-and-arrival))
   more than one agent radius from any wall, and more than one visibility
   cell from any wall face.
4. With a `sign`, keep the sign point at the same distance from walls.

The `blind_spawn_discovery` asset draws its door checkpoints this way:
2 m × 2 m boxes centred on 0.4 m thick doorways. Its geometry builder
(`assets/blind_spawn_discovery/build_geometry.py`, `_check_premises`) refuses
a checkpoint that is shallower than 1.5 m, because "agents jam aiming for the
same sliver", and one that is not wholly inside the walkable area, because
"direct steering could pick a target point inside a wall". The 1.5 m is that
builder's own check. pyFDS-Evac enforces no minimum checkpoint size.

{{< details title="Why a thin checkpoint jams" closed="true" >}}
Each agent steers to a random point inside the checkpoint, kept away from its
edge by a clearance of 0.8 times the agent radius. In a checkpoint as deep as
the wall, all these points lie on one thin strip, so the crowd aims at the
same line in the doorway. A box that spans both rooms spreads the targets.

Issue [#69](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/69)
reports the same failure for earlier Station checkpoints: "1.5 m -> 4.0 m
fixed 210 agents". That number is from the issue and was not re-run.
{{< /details >}}

{{< checkpoint title="The checkpoint is well placed" >}}
The run log has neither of these warnings for your checkpoint (the second
is logged only for scenarios with exploring agents):

```text
Routing <from> -> <to> failed (...); using a straight centroid ray
Node point (...) of stage <id> leaves no room for an agent of radius ... m: agents patrol from there without looking from it.
```

The first means the node point is off the navigation mesh: the route cost of
that edge is a straight line that ignores walls. The second means an
exploring agent cannot stand on the node point to look for signs. Move the
checkpoint away from the wall in both cases.
{{< /checkpoint >}}

## Wire checkpoints into the route graph

You choose between two ways.

**With `transitions`.** The graph has exactly the `from → to` pairs you list,
when both ends exist. Nothing else is added. A checkpoint with more than one
outgoing transition in a journey needs routing percentages; see
[Journey splits](scenario-json.md#journey-splits-waypoint_routing). A journey
whose stages appear in no transition is refused at load
(`simulation_init.py`, `check_journey_transitions`).

**Without `transitions`.** The graph wires itself: spawn areas and checkpoints
connect to checkpoints and exits, but not to a node when another checkpoint
lies on the way to it. The rule is on the routing page,
[Graph construction without a journey](routing.md#graph-construction-without-a-journey).
For placement it means:

- Each checkpoint you add on the walking line between two nodes removes their
  direct edge. Checkpoints therefore define which nodes are neighbours, and
  exploring agents learn the building neighbour by neighbour.
- A checkpoint that lies a little off the walking line, so that the detour
  through it is more than 5 % longer, does not remove the direct edge.
- In clear air, agents go to the nearest exit and do not visit checkpoints,
  unless smoke makes the route through them cheaper.

Shipped scenarios use both ways:

| Asset | Checkpoints | `transitions` |
|---|---|---|
| `blind_spawn_discovery` | 2 × 2 m boxes at the doors | none |
| `familiarity_test_{full,discovery,no_journey}` | boxes 0.55–1.22 m on a side | none |
| `station_fahy` | circles of radius 0.24–0.36 m | none |
| `t_junction` | one 3 × 3 m box | 3 |
| `schroeder2015_route` (`evac/config_*.json`) | 0.6 × 2 m boxes across the 0.2 m wall at doors A and B | 6 |

## Keep checkpoints and signs away from walls

Visibility is computed on a grid: the FDS mesh cells, or `cell_size_m`
(default 0.25 m) for the clear-air model (`visibility.py`,
`VisibilityModel.clear_air`). A sign or node point within about one cell of a
wall can fall onto the wall cell. Its sightlines then count as blocked at
every time, in clear air too, and exploring agents never see that checkpoint.

Issue [#100](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/100)
reports this for checkpoint 3 of `familiarity_test`, placed at y = 13.095 m
next to a partition at 13.0–13.1 m on a 0.25 m mesh. The shipped decks now
have its centre near y = 13.5 m. The rounding happens inside fdsvismap and
was not re-checked for this page.

Keep the node point and any authored sign more than one visibility cell from
any wall face. This margin is practice from #100. The software has no such
constant.

[Create a scenario](howto-create-scenario.md) asks that checkpoints lie
inside the walkable area. The two warnings in the check above are the signs that one
does not.

## How many checkpoints

No code rule or measured study gives a spacing. A spacing number would be
not established. What is known:

- An exploring agent learns a neighbour when it arrives at a node and when it
  sees the neighbour's sign from where it stands (`cognitive_map.py`,
  `expand_on_arrival`, `expand_from_visibility`). An edge between two distant
  checkpoints rests on one long sightline. Fewer checkpoints mean fewer, longer
  sightlines.
- Every shipped discovery scenario puts a checkpoint at each doorway or
  junction that a route must pass (the `familiarity_test` decks and
  `blind_spawn_discovery`).

## Crowds that stop at narrow doors

With the default `CollisionFreeSpeedModel`, a crowd can stop in an opening
several body widths wide
([#706](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/706)). Under
`no_known_exit: explore`, two agents can freeze head-on in a doorway
([#359](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/359)). The
rates are under [Known defects](limitations.md#known-defects).

Checkpoint size or placement does not remove these defects. In `station_fahy`
#706 occurs with or without the vestibule checkpoint and with a looser arrival
rule, which is why that scenario uses `WarpDriverModel`. What you can do:

- Draw door checkpoints that span both sides of the opening.
- Use smaller agent radii where the scenario allows; the effect is rarer but
  does not vanish.
- Before you read the evacuation time, check that every agent left before
  `max_simulation_time`. A deadlock shows as agents still inside at the end.

## Check list

- [ ] The node point lies inside the walkable area by more than the largest
      agent radius.
- [ ] The node point and every authored sign lie more than one visibility
      cell from any wall face.
- [ ] Door checkpoints span both sides of the opening.
- [ ] The log has no "Routing ... failed" warning and, with exploring
      agents, no "Node point ... leaves no room" warning.
- [ ] Every agent is out before `max_simulation_time`.

## Reference: node point, target point and arrival

{{< details title="Node point" closed="true" >}}
Every part of the software that needs one point for a checkpoint uses
`node_position` (`geometry.py`): the area centroid if it lies inside the
polygon, else the pole of inaccessibility (`polylabel`, tolerance 0.01 m),
else shapely's `representative_point()`. The node point is

- the end of each route-graph edge (`route_graph.py`,
  `StageGraph.from_scenario`, `_make_edge`). The edge follows the walkable
  path from JuPedSim's routing engine. If the node point is off the
  navigation mesh, the edge falls back to a straight ray and its cost ignores
  walls;
- the position of the default sign of a checkpoint without a `sign`: omni-directional, *c* = 3
  (`visibility.py`, `_default_sign`). An authored `sign` keeps its own `x, y`
  (`extract_sign_descriptors`), so visibility is then computed at the sign;
- the point an exploring agent walks to and looks from before it patrols on
  (`route_graph.py`, `_look_point`, `_node_point_fits`;
  [#250](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/250); see
  [Wayfinding](/models/wayfinding.md)). `_node_point_fits` requires an agent
  disc of radius *r* around the node point to fit in the walkable area.
{{< /details >}}

{{< details title="Target point" closed="true" >}}
Agents steer to a random target point inside the checkpoint, not to the node
point. The point is sampled inside the polygon shrunk by a clearance
(`simulation_init.py`, `_random_point_in_polygon`):

- max(0.05, 0.8 *r*) m for a stage after the first
  (`direct_steering_runtime.py`, `pick_stage_target`);
- max(0.05, 0.8 *r*, 0.25) m for the first stage
  (`simulation_init.py`, `_pick_initial_stage_target`).

*r* is the agent's own radius
([#732](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/732)). If the
shrunk polygon is empty or sampling fails, the point is drawn from the whole
polygon, and then `representative_point()` is used.
{{< /details >}}

{{< details title="Arrival" closed="true" >}}
`reached_stage` (`direct_steering_runtime.py`) decides when an agent has
reached a stage:

- **Checkpoint:** the agent's centre is within *r* + 0.5 m
  (`TARGET_REACH_MARGIN_M`) of its target point, or inside the checkpoint
  polygon.
- **Exit with a polygon:** the centre is inside the exit polygon or within
  0.03 m of it (`EXIT_REACH_TOLERANCE_M`).
- **Spawn area walked to on a patrol, zone, exit without a polygon:** the
  target-point test only.

A large checkpoint therefore does not delay arrival: agents arrive as they
enter it. A small checkpoint that fits inside the *r* + 0.5 m disc around the
target point, such as the `station_fahy` circles, is reached as before the
polygon test was added. The full steering loop is on
[Models › Routing](/models/routing.md#how-agents-are-steered).
{{< /details >}}

## Next step

Run the scenario and read the log for the two warnings above. Then follow
[Create a scenario](howto-create-scenario.md) to run it, or look up
every checkpoint key in [Checkpoints and zones](scenario-json.md#checkpoints-and-zones).
