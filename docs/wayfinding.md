---
title: "Wayfinding implementation notes"
linkTitle: "Wayfinding"
weight: 11
math: true
aliases: [/docs/wayfinding/]
---

> Part of [pyFDS-Evac](../README.md). The coded form, parameters and
> limitations are on [Models › Wayfinding](/models/wayfinding.md), which also
> defines the terms used here: *legible*, *known*, *learn*, *visited*,
> *frontier*. The intuition is on [Concepts › Wayfinding](/docs/concepts.md#wayfinding).

This page follows §3 of the talk
[*A Modular Workflow for Visibility-Aware Evacuation Modelling*](https://pedestriandynamics.org/pyFDS-Evac/talks/visibility-seminar-2026/),
one slide per section. Each section says what the code does, where, and which
figure belongs there. Where the talk and the code disagree, a **Talk vs code**
note says so, and the code is the reference.

Mechanisms were checked against main at `df0ccb0`. Each reported run outcome
names its source: a repository test, an asset README, a figure script, or a
run on main by one of the investigations of #160 and #168. None of the examples validates human
wayfinding. They verify that the implementation does what this page says.

The argument of the section is that **route choice can only choose among
routes the agent knows, so what the agent knows is as much part of the model
as how it prices smoke**. An agent starts with what its familiarity gives it.
After that, its map grows only through legible signs, or, with
`--no-visibility`, through every neighbour of the nodes it advances from.

## 1. A sign is more than a position

A node is a place. A sign tells someone standing elsewhere that the place
exists. Every exit, checkpoint and waypoint therefore carries a sign
descriptor \(\{x, y, \alpha, C\}\), authored or synthesised
(`visibility.py:34–73`).

pyFDS-Evac does not compute legibility itself. It hands the descriptors to
[fdsvismap](https://github.com/FireDynamics/fdsvismap), the implementation of
the waypoint method of Börger, Belt and Arnold (2024). fdsvismap precomputes,
for every sign, grid cell and stored time, whether the sign is legible there.
The rule, with its view-angle, obstruction and extinction factors, is on
[Models › Wayfinding §1](/models/wayfinding.md#1-the-sign-legibility-test).
During the run the model only looks the answer up (`visibility.py:531–543`).
A better visibility model in fdsvismap, or a *C* measured for a real sign,
therefore reaches the evacuation model without a change to the routing code.

*C* is set per sign. The code has one default, *C* = 3, for authored and
synthesised signs alike (`visibility.py:58`, `:94`).

> **Talk vs code.** The speaker notes say *C* defaults "to Jin's 3 for
> reflective and 8 for lit signs". The code has no default for lit signs; a
> sign gets 8 only if its author writes it. 3 and 8 are the FDS User Guide
> values. The [Fundamentals page](/fundamentals/visibility.md) gives Jin's
> ranges as 2–4 for reflecting and 5–10 for light-emitting signs.
>
> **Talk vs code.** The slide says legibility is "evaluated from the agent's
> actual position, not the source node centroid". Periodic learning uses the
> agent's stored position, which is the previous step's
> (`scenario.py:2240–2253`, `:2423`). Perception at spawn uses the spawn
> node's routing point for all agents of that spawn area
> (`cognitive_map.py:131–135`).
>
> **Code changed since the talk.** pyFDS-Evac replaces fdsvismap's 30 m
> visibility cap with the diagonal of the grid (`visibility.py:103`, `:512`).

<!-- FIGURE: none. The talk shows Börger, Belt and Arnold (2024), Fig. 11,
a third-party figure; link to the paper instead of reproducing it.
Proposed new figure: plan view of one sign's legible region at mean K = 0,
0.2 and 0.5 1/m, C = 3, drawn once with the 30 m cap and once with the grid
diagonal, computed by fdsvismap on a small deck with one wall. -->

## 2. One number flips the exit

The asset `assets/exit_visibility_alpha` isolates the bearing. It is a
corridor 4 m wide and 30 m long, with an exit at each end, and 40 agents at
familiarity 0 about 9 m from the near exit and 19 m from the far one. The two
configs differ only in the bearing of the near exit's sign; the far sign faces
the agents in both (`assets/exit_visibility_alpha/README.md`).

With the near sign facing the agents (\(\alpha = 0\)), both exits are learned
at spawn and the near one ranks first. With it facing away (\(\alpha = 180\)),
\(A = 0\) at every agent cell, so the near exit is never learned. Ranking runs
on the known subgraph only (`route_graph.py:1265–1269`), so the near exit is
absent, not refused.

This distinction matters because of the all-refused fallback. When every known
route fails the exposure gate, one refused route is re-admitted
(`route_graph.py:1427–1438`). A refused route can come back that way. An
unknown route cannot, because the fallback never sees it.

The tests pin the mechanism at router level
(`tests/test_exit_visibility_alpha.py::TestExitChoiceFollowsLegibility::test_illegible_near_exit_never_enters_the_map`,
`::TestExitChoiceFollowsLegibility::test_the_near_exit_is_absent_not_rejected`,
`::TestExitChoiceFollowsLegibility::test_a_fully_familiar_agent_ignores_the_bearing`).
Full runs of the asset follow the README's recipe, which uses `--fds-dir`, so
legibility comes from the FDS vismap, not from clear air. In those runs all 40
agents take the near exit when the sign faces them, and all 40 take the far
exit when it faces away. With FDS 6.10.1 output of the smoke-free deck and
seed 1904, on main after #170:

| Near sign | Exit taken | Egress | Route switches |
|---|---|---|---|
| \(\alpha = 0\) | 40 to `E_near` | 17.07 s | 0 |
| \(\alpha = 180\) | 40 to `E_far` | 25.89 s | 0 |

The visibility cap is the grid diagonal: 30.83 m on the FDS grid, 29.99 m on
the 0.25 m clear-air grid of Figure 1.

The asset's probe map of the ranked exit along the corridor
(`exit_choice_map.png`) was shifted by
[#167](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/167): before
#170 the switch from near to far fell at y ≈ 20.25. With the fix, clear-air
ranking uses travel time measured from the agent's position, and the switch is
at y ≈ 15.0, midway between the two exits.

![Two 30 m corridors side by side, each with an exit at both ends and the cells from which the near sign is legible shaded yellow; in the left corridor the near sign faces the agents and all 40 take the near exit, in the right the near sign faces away and all 40 walk to the far exit](/images/wayfinding/sign_bearing.png)

*Figure 1. One number flips the exit. `assets/exit_visibility_alpha`: a
4 m × 30 m corridor, 40 agents at familiarity 0, run in clear air on the
0.25 m grid, seed 1904. The two configurations differ only in the bearing of
the near exit's sign. Yellow: cells from which the near sign is legible. The
far sign is legible for y = 0–29.2 m in both panels. (a) \(\alpha = 0\): the
near sign is legible for y = 0.8–30.0 m; 40 of 40 agents take the near exit,
median walk 9.2 m, out at 17.1 s. (b) \(\alpha = 180\): the near sign is
legible only for y = 0–0.8 m; the near exit is never learned, and 40 of 40
agents walk to the far exit, median walk 19.0 m, out at 25.9 s. Counts, walks
and times are computed from the runs. Script:
`scripts/figures/sign_bearing.py`.*

## 3. What the agent knows

The talk draws wayfinding as a loop of three stages. The code has the same
structure.

- **Perception.** `node_is_visible`, called by `expand_from_visibility` and
  `expand_on_arrival`. It is asked only about neighbours of one node
  (`cognitive_map.py:177–186`, `:228–234`).
- **Knowledge.** `AgentCognitiveMap`: known nodes, known edges, visited nodes
  (`cognitive_map.py:10–25`).
- **Decision.** `rank_routes` on `cognitive_subgraph(map, graph)`
  (`route_graph.py:1265–1269`), then the switching rules of
  `evaluate_and_reroute`. With no reachable known exit, exploration or the
  patrol (`route_graph.py:1782–1844`).
- **The loop.** Moving changes the stored position that the next periodic
  learning uses (`scenario.py:2238–2254`), and advancing along the path
  triggers learning at the node left behind (`scenario.py:2508–2551`).

The full contract, including the #91 exception, the difference between
ranking and adoption, and the learning schedule, is on
[Models › Wayfinding §2](/models/wayfinding.md#2-the-knowledge-contract).

<!-- FIGURE: loop (proposed). A static redraw of the talk's HTML diagram:
three boxes (perception, knowledge, decision) and a loop back, with the
function name under each box. The talk slide has no image file. -->

## 4. An empty map

The talk asks where an agent goes when it knows nothing and no sign is legible
anywhere. Its intended answer: the agent has nothing to route to, explores,
learns nothing new, and circles. That is why the map has to be filled by
something, and the following slides show signs filling it.

**The code does not do this for a map that holds only the spawn node. This is
a known defect, not intended behaviour**
([#91](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/91); see also
defect 2 in `assets/blind_spawn_discovery/README.md`). The chain is:

- the agent is given the geometrically nearest exit as its steering target
  before its map exists (`simulation_init.py:1430–1449`);
- the opening choice finds no reachable known exit and leaves that target in
  place (`scenario.py:1006–1008`);
- the spawn node is visited from the start (`cognitive_map.py:117–121`), so
  there is no frontier;
- the patrol excludes the current node, so a one-node map has no stop
  (`cognitive_map.py:341–347`);
- `evaluate_and_reroute` returns without a switch (`route_graph.py:1809–1810`).

The agent keeps steering towards an exit it does not know. Periodic learning
can still add that exit on the way, once its sign becomes legible. The target,
however, was never chosen from the map.

Two probes support this. In ours, we ran the three-exit corridor of
`tests/test_initial_exit_from_cognitive_map.py` with 40 agents at familiarity
0, no `entrance`, rerouting every 1 s and seed 7. We ran it first with no
visibility model, and then with a clear-air model at 0.5 m in which every sign
faced away from the crowd. In both runs every agent left by the geometrically
nearest exit, and the route history recorded no switch. In the clear-air run,
3 of the 40 agents learned that exit on the way. Our probe scripts are
not in the repository. Figure 2 shows the same behaviour for one agent.

Circling needs a patrol target: at least one other known node reachable over
known edges. Whether the agent then circles also depends on connectivity and
steering. That is the smoke case of `assets/world_100` in #122.

> **Talk vs code.** The slide says the map "holds a single node" and "the agent
> circles". For a single node the code keeps the geometric target. No
> repository test pins either behaviour.

![Plan of a floor with two exits and one agent whose map holds only its spawn node; yellow cells mark where a sign is legible, none of them on the agent's path, and the agent walks straight to the south exit, which is not in its map](/images/wayfinding/empty_map_routes.png)

*Figure 2. An empty map, as the code behaves on main. One agent at
familiarity 0 with a clear-air visibility model. Yellow: cells from which a
sign is legible. The south exit, 22.4 m from the start, has a sign facing out
of the building; the west exit, 30.1 m away, has a sign facing along the
corridor behind walls. The map holds only the spawn for the whole run, and the
agent makes 0 route switches. After the default 10 s pre-movement it walks
23.4 m to the geometrically nearest exit, the south one, which it does not
know, and is out at 28.8 s. Nothing replaces the target it received at spawn
([#91](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/91)). The
intended behaviour is exploration. Script: `scripts/figures/empty_map_routes.py`.*

## 5. Per-agent cognitive maps

The talk calls this slide "staff know the building, visitors discover it".
In the code there are no staff and no visitors. There is a familiarity value
per group. At \(p = 1\) the agent is given the whole graph; that is an
assumption about the agent, not a model of training. At \(p < 1\) the map
starts from the spawn node, an optional reachable `entrance`, a draw per exit
with probability \(p\), and the neighbours legible from the spawn area's
routing point (`init_cognitive_map`, `cognitive_map.py:78–136`).

After spawn, the map grows at each due re-evaluation and each time the agent
advances along its path, by the neighbours whose signs are legible
(`cognitive_map.py:155–234`). Edges learned this way also teach their
reverse, when the graph has one. Routing then works on the known subgraph.

The talk illustrates this on a T-corridor with a junction and two exits. In
that schematic the discovery agent learns the junction at spawn and both exits
at the junction. Smoke then fills the right arm, and the agent heads for exit A.
In the code, whether exit B is refused depends on its route's optical depth
exceeding the gate budget. Legibility of B's sign plays no part in that
(`route_graph.py:1338–1344`).

<!-- FIGURE: cognitive_map (four panels + legend)
Source: scripts/figures/cognitive_map.py. Schematic: the known sets, the
smoke and the chosen exit are hard-coded (cognitive_map.py:64–95); nothing is
computed. -->

![Four panels of a T-shaped corridor showing which nodes and edges one agent knows: at spawn, at the junction, with smoke in the right arm, and for a fully familiar agent](/images/wayfinding/cognitive_map.png)

*Figure 3. Schematic, not a simulation: known sets and choices are drawn by
hand. A T-shaped corridor; filled nodes and solid edges are known. (1) A
discovery agent at spawn knows its spawn node and the junction, whose sign is
legible from there. (2) At the junction both exit signs are legible, and both
exits are learned. (3) Smoke fills the right arm. Exit B stays known; if its
route exceeds the exposure budget, the gate refuses it and the agent heads for
A. (4) A fully familiar agent knows the whole graph at t = 0. Script:
`scripts/figures/cognitive_map.py`.*

> **Talk vs code.** Panel 2 says "every neighbour whose sign is legible from the
> new node". The code tests legibility from the agent's position when the
> path advances (`scenario.py:2519–2520`).
>
> **Talk vs code.** The slide says "Learned edges are bidirectional". That holds
> only for edges learned by perception and arrival, and only where the graph
> has the reverse edge. With automatic wiring, exits have no outgoing edges.
> Paths learned from familiarity or `entrance` are forward only
> (`cognitive_map.py:71–74`, `:139–152`).
>
> **Talk vs code.** The slide calls `full` "the FDS+Evac default". It is
> pyFDS-Evac's default. FDS+Evac's `KNOWN_DOOR` defaults to `.FALSE.`
> (`evac.f90:2223`, `:2666`).

## 6. The map remembers

A known node stays known after its sign stops being legible. A visibility
query cannot do that on its own, because it answers only for the present
position and time.

The asset `assets/cognitive_map_memory` separates the two. A corridor has an
end exit, legible from spawn, and a side exit whose sign, at \((4, 20)\)
facing west, is legible from the centreline only inside a region. The asset
builder's estimate, y ≈ 12.5–27.5 m, assumes the 30 m cap
(`build_geometry.py:61`, `:78–95`), which the code no longer uses
(`visibility.py:512`). With the grid diagonal as the cap, on the 0.25 m
clear-air grid, the model reads the sign from y = 12.0 to 28.0 m on the
centreline (Figure 4).

The probes place one discovery agent at fixed positions on the centreline, in
sequence, and ask the router which exit ranks first there. They are sequential
state probes, not a walked trajectory. The tests assert four things
(`tests/test_cognitive_map_memory.py`):

- **Learning.** The side exit is unknown at y = 8 and known at y = 14
  (`::TestAcquisitionAndPersistence::test_side_exit_is_acquired_on_entering_the_window`).
- **Memory.** At y = 30 the sign is not legible, and the side exit is still
  known and routable (`::TestAcquisitionAndPersistence::test_side_exit_persists_after_its_sign_goes_illegible`,
  `::TestAcquisitionAndPersistence::test_a_remembered_exit_is_routable_though_illegible`).
- **Control.** A probe that never enters the region never learns it
  (`::TestAcquisitionAndPersistence::test_an_agent_that_never_enters_the_window_never_learns_it`).
- **Ranking.** The side exit ranks first at y = 14, the end exit at y = 30
  (`::TestAcquisitionAndPersistence::test_acquiring_the_side_exit_changes_where_the_agent_would_go`).

`::test_map_memory_probes_match_engine` pins the whole northbound sequence.
The probes use the test's clear-air setup, which has no routing engine, so the
distances are straight lines.

| y [m] | side exit | first-ranked exit |
|---|---|---|
| 4 | unknown | end |
| 10 | unknown | end |
| 14 | known, legible | side |
| 20 | known, legible | side |
| 26 | known, legible | end (5.30 m against 6.50 m) |
| 30 | known, not legible | end |

The two distances are equal at y ≈ 25.4. At every probe where both exits are
known, the distance from the agent to each exit is shorter than that route's
first leg from the spawn node (16.3 m to the side exit, 27.3 m to the end
exit, from the test's comment). The #167 cap is therefore inactive here. We
checked this by hand.

Memory therefore shows on the way north as *known and routable*, not as
*first-ranked*. It changes the ranking on the way back. Probed again at
y = 10 after the northbound sequence, the side sign is still not legible
there, but the side exit is known and nearer (10.31 m against 21.30 m), and it
ranks first. At the same place before learning, the end exit ranked first.
`::test_map_memory_probes_match_engine` pins this return probe too.

In a moving agent, ranking is not adoption: the switching rules can keep a
current exit that no longer ranks first
([Models › Wayfinding §2.4](/models/wayfinding.md#2-the-knowledge-contract)).
In the full run of the asset README, with the FDS vismap, all 20 agents
left by the side exit, egress 21.2 s, each after one switch from the end exit
to the side exit (`assets/cognitive_map_memory/README.md`).

> **Talk vs code.** The slide says the side exit is learned "at y = 12.5" and
> "at y = 30 … the agent still routes to it". 12.5 m is the builder's 30 m
> estimate. The first test probe inside the region is at y = 14. At y = 26 and
> 30 the end exit ranks first. This follows from
> [#65](https://github.com/PedestrianDynamics/pyFDS-Evac/pull/65), which prices
> routes from the agent's position (see
> [#160](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/160)).

![Five probes of one corridor: side exit unknown at y = 4, learned at y = 14, legible at y = 20, known but not legible at y = 30, and first-ranked at a return probe at y = 10](/images/wayfinding/map_memory.png)

*Figure 4. The map remembers. `assets/cognitive_map_memory`, clear air, one
discovery agent probed in sequence at y = 4, 14, 20 and 30 m, then at y = 10 m
again. These are state probes, not a walk. The shaded, lens-shaped region is
where the side sign is legible; on the centreline it spans y = 12.0–28.0 m
(gold ticks). Northbound, the side exit is learned inside the region and
stays known beyond it. At y = 30 the nearer end exit ranks first. At the return
probe, where the side sign is not legible, the known side exit is nearer and
ranks first. At that place before learning, the end exit ranked first. Each
ranking is computed by `rank_routes`. Script: `scripts/figures/map_memory.py`.*

## 7. Full versus discovery

The talk compares the two tiers on the same geometry, seed and signs. One
thing differs in the code, and until #174 a second one did:

1. **The initial map.** A fully familiar agent knows the whole graph. A
   discovery agent explores: it takes the frontier with the lowest path cost
   from its position, learns as the path advances, and, with no frontier left,
   patrols its known nodes (`cognitive_map.py:260–397`). Route history logs
   `reason="explore"` and `reason="wander"` (`route_graph.py:1793`, `:1808`).
2. **The ranked length of the first leg**
   ([#172](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/172), fixed
   by #174, now merged). The discovery agent's subgraph lacked the routing
   engine, so `rank_routes` measured the walk from the agent to its next node as a
   straight line, even through walls. Exploration was not affected, because
   frontier selection measures that leg on the full graph.

Before #174, a comparison around obstacles mixed the effect of knowledge with
the effect of #172. The run of Figure 5 gives the same numbers before and
after #174. For both tiers, the first leg's smoke is sampled on a straight
line from the agent to its next node
([#171](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/171)).

The patrol can stall: when smoke limits legibility to a few metres, a patrol
over a few known nodes may never pass a legible new sign
([#122](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/122)).

**Discovery times depend on the grid.** On
`assets/familiarity_test_discovery`, seed 420, the #168 investigation measured
the following discovery egress times on main:

| Clear-air cell | Discovery egress |
|---|---|
| 0.25 m | 88.6 s |
| 0.1 m | 138.2 s |
| 0.05 m | 158.5 s |
| 0.025 m | 200.8 s |

The fully familiar tier took 33.9 s. The code advises a cell smaller than the
thinnest wall (`visibility.py:455–465`). The #168 investigation recommends at
most half of it, as guidance: 0.05 m for the 0.1 m walls of this deck. The
continued change below that is not explained
([#168](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/168)). Do not
quote a discovery egress time without its grid.

The talk also shows discovery with and without sign gating on the NIST floor
plan of The Station (`assets/station_fahy`). With `--no-visibility`, advancing
from a node teaches every neighbour. With a visibility model, only neighbours
with legible signs are learned, so walls and bearings cut the known set even
in clear air. The talk's counts (8 of 11 and 3 of 11 nodes) were not
reproduced for this page.

![Two copies of a three-room floor plan side by side with the walked paths of 20 agents; left, fully familiar agents walk to the exit; right, discovery agents detour through a dead-end room first](/images/wayfinding/full_vs_discovery_paths.png)

*Figure 5. Full versus discovery. `assets/familiarity_test_full` and
`assets/familiarity_test_discovery`: 20 agents, seed 420, same geometry and
signs; `familiarity` differs. Clear-air grid 0.05 m. (a) Full: 6 of 6 stages
known from t = 0, no route changes; the last agent leaves at 33.9 s, median
path 29 m. (b) Discovery: 3 of 6 stages known at t = 0, a median of 6 at the
end; the exit enters the maps at t = 34–145 s (median 60 s). After t = 0 the
agents make 101 route changes (60 explore, 21 wander, 20 onto the exit), with a
detour into a dead-end room; the last leaves at 158.5 s, median path 61 m. The
discovery time has not converged with the grid (88.6 s at 0.25 m, 200.8 s at
0.025 m; #168). This illustrates the mechanism; it is not a result. Script: `scripts/figures/full_vs_discovery_paths.py`.*

> **Talk vs code.** The talk caption gives 35.1 s and 75.1 s. Those are results
> from the deck before its rework in #99 (`docs/testing-familiarity.md`). The
> world_100 clip ("42 signs") and the Station clips were not reproduced for this
> page, and their decks and commits are not recorded.

## References

- Börger, K., Belt, A., & Arnold, L. (2024). *A waypoint based approach to
  visibility in performance based fire safety design*. Fire Safety Journal,
  150, 104269.
  [doi:10.1016/j.firesaf.2024.104269](https://doi.org/10.1016/j.firesaf.2024.104269)
- Haensel, D. (2014). *A knowledge-based routing framework for pedestrian
  dynamics simulation*. Diploma thesis, TU Dresden.
