---
title: "Familiarity: full map vs discovered map"
linkTitle: "Familiarity"
weight: 17
math: true
aliases: [/docs/testing-familiarity/, /models/verification/testing-familiarity/]
---

| | |
|---|---|
| **Component** | Cognitive map and exploration ([Models › Wayfinding](/models/wayfinding.md#2-the-knowledge-contract)) |
| **Level** | Coupled: two full runs in clear air (a uniform zero-extinction field), no FDS |
| **Asset** | `assets/familiarity_test_full`, `assets/familiarity_test_discovery` |
| **Expected value from** | the plan alone: shortest paths, sight lines to the signs and the wiring rule, computed without pyFDS-Evac |
| **Status** | criteria 1–5 pass on the 0.1, 0.05 and 0.025 m sight grids; the `run.py` default of 0.25 m does not resolve the walls; criterion 6 fails: the discovery egress time is not grid-converged ([#168](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/168), [#250](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/250)) |

![Two copies of the same plan side by side. Left, 20 fully familiar agents walk straight to the one door in the partition and out. Right, 20 discovery agents first explore the dead-end rooms in the west, then walk to the door; some turn back at it and patrol. Agents are coloured by the node they are heading for; patrolling agents have a thick ring](/images/verification/familiarity.gif)

*Left: `full`. Right: `discovery`, 0.05 m sight grid. Colour: the node the
agent is heading for (full: CP3 until it passes the door, then the exit;
discovery: its current route target). Thick ring: a patrol (`wander`).*

## What is tested

Whether `familiarity` changes what an agent knows, and only that. The two
decks share plan, signs, agents and seed; only the spawn group's
`familiarity` differs. A `full` agent must know the whole map and take the
shortest route. A `discovery` agent must start with only what it can see and
learn a node only when its sign comes into sight. This catches a familiarity
flag that is ignored, a map seeded with nodes the agent cannot see, a node
learnt through a wall, and an exploration that does not follow the frontier
rule.

## Equation

Familiarity is \(p = 1\) (`full`) or \(p = 0\) (`discovery`)
([Models › Wayfinding §2](/models/wayfinding.md#2-the-knowledge-contract)).

- **Full.** The agent knows the whole stage graph from t = 0 and takes the
  shortest path to the exit.
- **Discovery.** At t = 0 the agent knows its spawn node and each neighbour
  whose sign is legible from where it stands. Later it learns a neighbour of
  its current node when that node's sign becomes legible: on arrival at a
  node, and at each re-evaluation (every 1 s).
- **Exploration.** With no exit known, it heads for the nearest known node it
  has not visited (walking distance). With none left, it patrols the nodes it
  knows (`wander`).

**Legibility.** pyFDS-Evac hands the signs to
[fdsvismap](https://github.com/FireDynamics/fdsvismap), the implementation of
the waypoint method of Börger, Belt and Arnold (2024,
[doi:10.1016/j.firesaf.2024.104269](https://doi.org/10.1016/j.firesaf.2024.104269)).
In clear air its rule reads: a sign at \(s\) facing the compass bearing
\(\alpha\), with \(\hat n = (\sin\alpha, \cos\alpha)\), is legible from \(p\)
when the sight line \(p\)–\(s\) stays in the walkable area and

$$
\hat n\cdot(p - s) \;\ge\; \frac{|p - s|^2}{V_{\max}}, \qquad V_{\max} = 30\ \text{m}.
$$

The view-angle factor is \(\hat n\cdot(p-s)/|p-s|\). fdsvismap caps the
reading distance at \(V_{\max}\) before it multiplies by that factor, so the
legible region is a disc of diameter 30 m in front of the sign. Capping after
the factor would give a half-disc of radius 30 m; on this plan both orders give
the same predictions (the script checks both). \(V_{\max}\) is the default of
`--max-sign-distance`, a reading limit, not a measured distance. A sign
without a bearing (here the exit's) needs only \(|p - s| \le V_{\max}\).

**Stage graph.** With no transitions in the deck, the graph is wired
automatically. With \(d\) the shortest walkable path between node centres, the
edge \(u \to v\) from a spawn area or checkpoint to a checkpoint or exit is
dropped when some other checkpoint \(m\) lies on the way:

$$
d(u,m) + d(m,v) \;\le\; 1.05\, d(u,v).
$$

If every edge of \(u\) is dropped, the nearest target is kept.

**Reference time.** A path of length *L* walked at the desired speed takes
\(t_{\text{ref}} = L / v_0\), with \(v_0\) = 1.3 m/s. It is not a bound:
agents pushed by neighbours walk faster than \(v_0\).

## Setup

![Plan of the 20 by 18 m floor: spawn room in the south-east, a partition with one door below the exit area, CP3 just behind the door, dead-end rooms in the west with CP1 and CP2, the stage-graph edges, the signs as arrows, the full agents' shortest path and the discovery agents' predicted tour](/images/verification/familiarity_setup.png)

- **Plan:** 20 × 18 m, 0.1 m walls, 1.2 m doors. The partition
  (y = 13.0–13.1 m) has one door (x = 17.0–18.2 m); CP3 is the box just north
  of it (y = 13.22–13.77 m). The exit is in the north-west corner. The west
  rooms (CP1, CP2) hold no exit.
- **Signs:** CP0 and CP1 face east, CP2 north, CP3 south; the exit's sign is
  synthesised at its centre, without a bearing.
- **Agents:** 20, all at t = 0 in the spawn room; Social Force model,
  \(v_0\) = 1.3 m/s, radius 0.2 m, seed 420; rerouting on, re-evaluation
  every 1 s.
- **Runs:** clear air (no `--fds-dir`). `full` once. `discovery` on sight
  grids of 0.25, 0.1, 0.05 and 0.025 m; 0.05 m, two cells across a wall, is
  the reference. Each run records every change of every agent's map.

## Expected

All from the plan, computed by the figure script with its own
visibility-graph shortest paths, the legibility rule and the wiring rule.

| Quantity | Value | From |
|---|---|---|
| stage graph | 6 nodes, 11 edges (the run log prints `nodes=6 edges=11`) | wiring rule |
| neighbours of the spawn | CP0, CP3 | wiring rule; the exit is dropped because CP3 lies on the way |
| full: map at t = 0 | all 6 nodes and 11 edges | \(p = 1\) |
| full: route | S → CP3 → exit for all 20; nobody in CP0–CP2 | the partition has one door |
| full: shortest path, spawn centre to exit | 27.4 m; \(t_{\text{ref}}\) = 21.1 s | shortest path |
| discovery: map at t = 0 | spawn, CP0, CP3 (3 of 6 nodes) | CP0's and CP3's signs are legible from the spawn centre; the exit is not a neighbour |
| discovery: first target | CP0, for all 20 | nearest frontier: CP0 3.2 m, CP3 11.8 m |
| discovery: tour | CP0 → CP1 → CP2 → CP3 → exit | from CP0: CP1 6.5 m vs CP3 12.7 m; from CP1: CP2 4.0 m vs CP3 18.5 m; from CP2: CP3 only |
| discovery: tour length | 52.0 m (1.9 × full); \(t_{\text{ref}}\) = 40.0 s | shortest path along the tour |
| exit sign seen from CP3's door | first legible at y = 12.96–13.08 m, for agent centres 0.2 m clear of the jambs (x = 17.2–18.0 m) | the west jamb blocks the sight line |

The last row matters. Arrival at a stage registers within 0.7 m of a random
point in its box
([#69](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/69)), so
arrival at CP3 can register from y = 12.52 m, still south of the door. There
the exit sign is behind the jamb, and arriving teaches nothing. If the agent
has stepped past the jamb by its next re-evaluation, it sees the exit and
leaves. If not, it has no frontier left and starts a patrol. The plan cannot
say which agents do what; the criteria test that each decision matches what
the agent could see.

![Zoom on CP3's door: the partition with its 1.2 m door, the CP3 box north of it, the dashed region within 0.7 m of the box where arrival can register, reaching south of the door, the green line above which the exit sign is legible, with its grid tolerance band, and the positions of the patrol decisions, all at or below that line](/images/verification/familiarity_door.png)

## Result

![Walked paths of the 20 agents on the two plans, coloured by the node each agent is heading for, patrols dashed. Full agents go straight to CP3 and the exit; discovery agents walk CP0, CP1, CP2, back through CP0 to CP3 and the exit; seven turn back at CP3's door and patrol](/images/verification/familiarity_paths.png)

Full agents never enter the west rooms. Discovery agents all explore them
first, as predicted. The dashed legs are patrols: agents that turned back at
CP3's door.

![Left: agents out over time for full and for discovery on four sight grids, with the reference times of 21 s and 40 s. Right: the route of each agent per run: full all direct; discovery mostly the predicted tour, two skipping CP2 because its sign was hidden, and three to seven turning back at CP3](/images/verification/familiarity_egress.png)

| Check (0.05 m grid) | Expected | Simulated |
|---|---|---|
| full: map at t = 0; later changes | 6 nodes, 11 edges; 0 | 20 / 20; 0 |
| full: agents via CP3 only; route changes | 20 / 20; 0 | 20 / 20; 0 |
| full: walked / shortest path | ≥ 1 | 1.03–1.14 |
| full: first agent out (sanity check) | near \(t_{\text{ref}}\) = 21.1 s | 20.3 s |
| full: last agent out | no reference | 33.9 s; the door (y = 13.05 m) passes 20 agents in 7.7–21.3 s, 1.40 persons/s or 1.17 persons/(s·m) of door width |
| discovery: map at t = 0 | {S, CP0, CP3} | 20 / 20 |
| discovery: first target | CP0, 20 / 20 | 20 / 20 |
| discovery: nodes learnt later | each a neighbour of a known node, its sign in sight | 59 of 59 |
| discovery: tour up to CP3 | CP0 → CP1 → CP2 → CP3 where CP2's sign is legible at CP1 | 18 / 20; agents 9 and 12 reach CP1 behind the wall stub, where CP2's sign is hidden, and go to CP3 first |
| discovery: patrols started with the exit in sight | 0 | 0 of 21; those at CP3 at y = 12.68–13.01 m |
| discovery: first agent out (sanity check) | near \(t_{\text{ref}}\) = 40.0 s | 46.7 s |
| discovery: last agent out | no reference | 158.5 s; 7 agents turned back at CP3 |

On other grids:

| Sight grid | Cells across a 0.1 m wall | Last out | Turned back at CP3 | Last out, never turned back |
|---|---|---|---|---|
| 0.25 m | 0 | 88.5 s | 0 | 88.5 s |
| 0.1 m | 1 | 138.2 s | 3 | 83.6 s |
| 0.05 m | 2 | 158.5 s | 7 | 95.7 s |
| 0.025 m | 4 | 200.7 s | 4 | 84.5 s |

The agents that never turn back are out by 84–96 s on every grid. The grid
dependence is the turn-back at CP3
([#250](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/250)). At
0.25 m no cell centre falls inside the walls, so the sight grid sees through
them: agents learn CP2 from the next room and the exit from south of the
partition, and nobody turns back.

## Pass criteria

**Grid tolerance.** The sight grid moves the edge of the legible region. From
the code of `VisibilityModel.clear_air` and fdsvismap 0.2.1, each of four
errors shifts a sight line sideways by at most:

| Source | Shift, at most |
|---|---|
| the agent's position snaps to the nearest cell centre | \(c\sqrt2/2\) |
| the sign snaps to the nearest cell centre | \(c\sqrt2/2\) |
| a wall cell blocks when its centre is outside the walkable area | \(c/2\) |
| rays are anti-aliased, which marks cells up to one cell beside the line | \(c\) |

Their sum is \(T = c(\sqrt2 + 3/2) \approx 2.9\,c\): 0.15 m at
*c* = 0.05 m. This is a first-order estimate for this plan, not a general
bound: a shift at the sign reaches the agent scaled by (agent to wall) /
(sign to wall), which is small here (the jamb of CP3's door is within 1 m
of the agents, the exit sign 16.5 m away). At 0.1 m, *T* = 0.29 m, about
three wall thicknesses, so a pass there is weaker evidence than at 0.05 m. A decision within *T* of the edge cannot be judged on this grid.
So a node counts as *hidden* only if its sign is illegible from every point
within *T* of the agent, and as *in sight* only if it is legible from every
such point. The script samples that disc at its centre and at 48 points on
three rings.

**Precondition.** The grid resolves the walls: at least one cell centre lies
inside each 0.1 m wall. At 0.25 m it does not, and the criteria below are not
evaluated; there, with no tolerance, 33 learnt nodes had their sign hidden in
exact geometry (13 of them CP2, learnt from the next room).

1. **Full.** Every full agent knows all 6 nodes and the 11 wired edges at
   t = 0 and learns nothing later; every trajectory enters CP3's box and none
   of CP0–CP2's; no route changes. Counts, no tolerance.
2. **Discovery start.** Every discovery agent's map at t = 0 is exactly
   {S, CP0, CP3}, and its first target is CP0. Counts.
3. **Learning.** Every node added to a map after t = 0 is the head of a wired
   edge from a node already known, and its sign is not hidden from the
   agent's position at that time. The rule asks for a neighbour of the
   agent's current node; the check accepts any known node, so it is a
   necessary condition only.
4. **Tour.** Each agent explores CP0 → CP1 → CP2 → CP3, or skips CP2 only
   where CP2's sign was not in sight when it chose CP3.
5. **No patrol in sight of the exit.** No `wander` decision is taken where
   the exit sign is in sight. This checks that a patrol is consistent with
   what the agent could see. It does not say that turning back at the only
   door is right; that is #250.
6. **Grid convergence of the discovery egress time.** The last agent out on
   the 0.05 and 0.025 m grids differs by at most 5 s. Halving the cell moves
   each sight edge by at most *T* = 0.15 m, which an agent at 1.3 m/s walks
   in about 0.1 s. So each of the 5 decisions of the tour may move by at most
   one re-evaluation (1 s).

| Grid | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| 0.1 m | pass | pass | pass | pass (2 skips explained) | pass | – |
| 0.05 m | pass | pass | pass | pass (2 skips explained) | pass | **fails**: 158.5 vs 200.7 s |
| 0.025 m | pass | pass | pass | pass (2 skips explained) | pass | – |

With no tolerance (*T* = 0), the results show how close to the edge some
decisions fall. Criterion 3 flags 2 learnt nodes at 0.1 m and 1 at 0.05 m.
Criterion 5 flags 1 patrol at 0.1 m and 1 at 0.05 m. Criterion 4 is
unchanged. Each flag lies within 0.04 m of the edge of the legible region
(the exit sign at y ≈ 13.01 m in CP3's door, CP2's sign near CP1), well
inside *T*: there the grid decides, and exact geometry cannot overrule it.

## Run it yourself

No FDS is needed. `scripts/verification/familiarity_run.py` takes the same
arguments as `run.py` and also writes each agent's map history. Run each deck
in its own process:

```bash
R=scripts/verification/familiarity_run.py
uv run python $R --scenario assets/familiarity_test_full --seed 420 \
  --output-route-history <out>/full/routes.csv \
  --output-sqlite <out>/full/run.sqlite \
  --output-cognitive-map <out>/full/cognitive_map.csv --cleanup
for c in 0.25 0.1 0.05 0.025; do
  d=<out>/discovery_cell$c
  uv run python $R --scenario assets/familiarity_test_discovery --seed 420 \
    --vis-cell-size $c --output-route-history $d/routes.csv \
    --output-sqlite $d/run.sqlite --output-cognitive-map $d/cognitive_map.csv \
    --cleanup
done
uv run python scripts/verification/familiarity_figures.py --data <out>
```

Each run takes seconds. The script prints every number on this page. The
runs used here (main at `9bd5c28`, macOS arm64) are in the project's data
folder, `fds-evac-data/familiarity_test_discovery/evac/`. The map histories
come from reruns whose trajectories and route decisions are identical to the
stored runs.

Reruns on the same machine reproduce these numbers to the last digit. Across
platforms they need not
([#199](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/199)); the
tests on generated worlds (`tests/test_generated_worlds.py`) therefore
assert invariants, not trajectories.

`scripts/animate_cognitive_map.py` turns the map history of one agent into a
movie.

## Limits

- **The discovery egress time is not converged in the grid**
  ([#168](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/168)), and
  criterion 6 fails. The cause is agents turning back at the door of the
  only exit
  ([#250](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/250)),
  because arrival registers before the door
  ([#69](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/69)). Do not
  quote a discovery egress time without its grid.
- **Grid.** `run.py` uses a 0.25 m sight grid by default. On this deck it
  sees through every wall. Pass `--vis-cell-size 0.05` for the discovery
  deck; a warning for grids coarser than the walls is proposed in
  [#168](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/168).
- **No reference for the egress times.** The full run's last agent is out at
  33.9 s. Its door passes 1.40 persons/s (1.17 persons/(s·m) of the 1.2 m
  door), measured where the agents cross the door's mid-line. No
  hand-calculated door flow is compared here.
- **One exit, clear air.** Choosing between several known exits, and learning
  through smoke, are not tested here. For the bearing of a sign see
  `tests/test_exit_visibility_alpha.py`; smoke-limited learning has no test
  yet ([#22](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/22)).
  The paired FDS deck has slices at 2.0 and 1.0 m only, not at the 1.6 m
  sampling height; it would need them before a smoke variant is run.
- **Route choice is not perception-limited.** Among the exits it knows, a
  discovery agent prices smoke over legs it has never seen
  ([#125](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/125)).
  In clear air this changes nothing here.
- **Labels.** `routes.csv` records the step onto the exit with reason
  `smoke_reroute`, also in clear air: every change of exit gets that label
  ([#92](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/92)).
- **Not yet an automated test.** The checks run in the figure script on the
  stored output. `scripts/golden_rerouting.py` records these runs, the grid
  sweep included, as golden output, and `tests/test_rerouting_golden.py`
  pins route decisions on these decks under synthetic smoke; both are
  regression checks, not verification.
- **History.** Before
  [#99](https://github.com/PedestrianDynamics/pyFDS-Evac/pull/99) the deck
  had a scripted tour, hand-added shortcut edges and a second exit. The
  talk's 35.1 s and 75.1 s, quoted on
  [Models › Wayfinding](/models/wayfinding.md), come from that version and
  are not comparable.
