---
title: "Familiarity: known exits vs discovered exits"
linkTitle: "Familiarity"
weight: 16
math: true
aliases: [/docs/testing-familiarity/]
---

| | |
|---|---|
| **Component** | Cognitive map and exploration ([Models › Wayfinding](/models/wayfinding.md#2-the-knowledge-contract)) |
| **Level** | Coupled: two full runs in clear air, no FDS |
| **Asset** | `assets/familiarity_test_full`, `assets/familiarity_test_discovery` |
| **Expected value from** | the plan alone: shortest paths, sight lines to the signs and the wiring rule, computed without pyFDS-Evac |
| **Status** | passes on the 0.05 m sight grid; the discovery egress time depends on the grid ([#168](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/168), [#250](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/250)) |

![Two copies of the same plan side by side. Left, 20 fully familiar agents walk straight to the one door in the partition and out. Right, 20 discovery agents first explore the dead-end rooms in the west, then walk to the door; some turn back at it. Agents are coloured by the node they are heading for](/images/verification/familiarity.gif)

*Left: `full`. Right: `discovery`, 0.05 m sight grid. Colour: the node the
agent is heading for (full: CP3 until it passes the door, then the exit;
discovery: its current route target).*

## What is tested

Whether `familiarity` changes what an agent knows, and only that. The two
decks share plan, signs, agents and seed; only the spawn group's
`familiarity` differs. A `full` agent must take the shortest route to the
exit. A `discovery` agent may only head for nodes whose sign it has seen, so
it must explore, in an order that follows from the plan. This catches a
familiarity flag that is ignored, a map seeded with nodes the agent cannot
see, and an exploration that does not follow the frontier rule.

## Equation

Familiarity is \(p = 1\) (`full`) or \(p = 0\) (`discovery`)
([Models › Wayfinding §2](/models/wayfinding.md#2-the-knowledge-contract)).

- **Full.** The agent knows the whole stage graph from t = 0 and takes the
  shortest path to the exit.
- **Discovery.** At t = 0 the agent knows its spawn node and each neighbour
  whose sign is legible from the spawn's centre. It learns a neighbour of its
  current node when that sign becomes legible: on arrival at a node, and at
  each re-evaluation (every 1 s).
- **Exploration.** With no exit known, it heads for the nearest known node it
  has not visited (walking distance). With none left, it patrols the nodes it
  knows (`wander`).

A sign at \(s\) facing the compass bearing \(\alpha\), with
\(\hat n = (\sin\alpha, \cos\alpha)\), is legible in clear air from \(p\) when
the sight line \(p\)–\(s\) stays in the walkable area and

$$
\hat n\cdot(p - s) \;\ge\; \frac{|p - s|^2}{V_{\max}}, \qquad V_{\max} = 30\ \text{m},
$$

that is, \(p\) lies in a disc of diameter 30 m in front of the sign. A sign
without a bearing needs only \(|p - s| \le V_{\max}\).

The stage graph is wired automatically: each spawn area and checkpoint links
to every checkpoint and exit it reaches without passing another checkpoint
(a detour of at most 5 %).

A path of length *L* takes at least

$$
t \ge L / v_0, \qquad v_0 = 1.3\ \text{m/s}.
$$

## Setup

![Plan of the 20 by 18 m floor: spawn room in the south-east, a partition with one door (CP3) below the exit alcove, dead-end rooms in the west with CP1 and CP2, the stage-graph edges, the full agents' shortest path and the discovery agents' predicted tour](/images/verification/familiarity_setup.png)

- **Plan:** 20 × 18 m, 0.1 m walls, 1.2 m doors. A partition at y = 13 m has
  one door, CP3; the exit is behind it. The west rooms (CP1, CP2) hold no
  exit. Signs: CP0 and CP1 face east, CP2 north, CP3 south; the exit's sign
  is synthesised at its centre, without a bearing.
- **Agents:** 20, all at t = 0 in the spawn room; Social Force model,
  \(v_0\) = 1.3 m/s, radius 0.2 m, seed 420; rerouting on, re-evaluation
  every 1 s.
- **Runs:** clear air (no `--fds-dir`). `full` once. `discovery` on sight
  grids of 0.25, 0.1, 0.05 and 0.025 m; 0.05 m, two cells across a wall, is
  the reference.
- **Not used:** the paired FDS deck `familiarity_test.fds` (a fire in the
  spawn room). Smoke would change speed and route cost as well, and this test
  is about knowledge only.

## Expected

All from the plan, computed by the figure script with its own
visibility-graph shortest paths and the legibility rule above.

| Quantity | Value | From |
|---|---|---|
| stage graph | 6 nodes, 11 edges (the run log prints `nodes=6 edges=11`) | wiring rule |
| neighbours of the spawn | CP0, CP3 | wiring rule; the exit is pruned because CP3 lies on the way |
| full: route | S → CP3 → exit for all 20; nobody in CP0–CP2 | the partition has one door |
| full: shortest path, spawn centre to exit | 27.4 m, 21.1 s at \(v_0\) | shortest path |
| discovery: known at t = 0 | spawn, CP0, CP3 (3 of 6 nodes) | CP0's and CP3's signs are legible from the spawn centre; the exit's is behind the partition |
| discovery: first target | CP0, for all 20 | nearest frontier: CP0 3.2 m, CP3 11.8 m |
| discovery: tour | CP0 → CP1 → CP2 → CP3 → exit | from CP0: CP1 6.5 m vs CP3 12.7 m; from CP1: CP2 4.0 m vs CP3 18.5 m; from CP2: CP3 only |
| discovery: tour length | 52.0 m (1.9 × full), 40.0 s at \(v_0\) | shortest path along the tour |
| exit sign seen from CP3's door | first legible at y = 12.96–13.08 m, depending on x in the door | the west jamb of the door blocks the sight line |

The last row matters. Arrival at a stage registers within 0.7 m of a random
point in its box
([#69](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/69)). CP3's
box starts at y = 13.22 m, so arrival can register while the agent is still
in the door, behind the jamb; then it learns nothing on arriving at CP3. If
it has stepped past the jamb by its next re-evaluation, it sees the exit and
leaves. If not, it has no
frontier left and starts a patrol. The plan cannot say which agents do what;
the checks below test that each decision matches what the agent could see.

## Result

![Walked paths of the 20 agents on the two plans, coloured by the node each agent is heading for. Full agents go straight to CP3 and the exit; discovery agents walk CP0, CP1, CP2, back through CP0 to CP3 and the exit](/images/verification/familiarity_paths.png)

Full agents never enter the west rooms. Discovery agents all explore them
first, as predicted.

![Left: agents out over time for full and for discovery on four sight grids, with the lower bounds of 21 s and 40 s. Right: the route of each agent per run: full all direct; discovery mostly the predicted tour, some in another order, some turned back at CP3](/images/verification/familiarity_egress.png)

| Check (0.05 m grid) | Expected | Simulated |
|---|---|---|
| full: agents via CP3 only, route changes | 20 / 20, 0 | 20 / 20, 0 |
| full: walked / shortest path | ≥ 1 | 1.03–1.14 |
| full: egress time minus own shortest path / \(v_0\) (sanity check) | ≥ 0 | ≥ +0.48 s |
| full: last agent out | – | 33.9 s |
| discovery: first target CP0 | 20 / 20 | 20 / 20 |
| discovery: targets chosen before their sign was in sight | 0 | 0 |
| discovery: tour CP0 → CP1 → CP2 → CP3 | where CP2's sign is legible at CP1 | 18 / 20; agents 9 and 12 reach CP1 behind the riser, where CP2's sign is hidden, and go to CP3 first |
| discovery: patrol started with the exit in sight | 0 | 0 of 20 patrol decisions; those at CP3 at y = 12.68–13.01 m |
| discovery: first agent out (sanity check) | ≥ 40.0 s (tour from the spawn centre) | 46.7 s |
| discovery: last agent out | – | 158.5 s; 7 agents turned back at CP3 |

On other grids:

| Sight grid | Cells across a 0.1 m wall | Last out | Turned back at CP3 | Last out, never turned back | Targets chosen before in sight |
|---|---|---|---|---|---|
| 0.25 m | 0 | 88.5 s | 0 | 88.5 s | 1 |
| 0.1 m | 1 | 138.2 s | 3 | 83.6 s | 0 |
| 0.05 m | 2 | 158.5 s | 7 | 95.7 s | 0 |
| 0.025 m | 4 | 200.7 s | 4 | 84.5 s | 0 |

The agents that never turn back are out by 84–96 s on every grid. The grid
dependence is the turn-back at CP3
([#250](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/250)). At
0.25 m no cell centre falls inside the walls, so the vismap sees through
them. That removes the turn-back, and criterion 3 catches it: agent 9 targets CP2
without ever having had a sight line to its sign.

## Pass criteria

1. **Full route.** Every full agent's trajectory enters CP3's box and none of
   CP0–CP2's, and no route changes. Counts, no tolerance.
2. **Discovery start.** All 20 first targets are CP0. Counts.
3. **Evidence.** Every node a discovery agent targets was, at some point of
   its trajectory before that decision, in sight of the node's sign, or known
   at t = 0. The vismap tests sight at cell centres, so a wall face or a
   position is uncertain by half a cell diagonal, \(c\sqrt2/2\) = 0.035 m at
   *c* = 0.05 m; sight from any point within that distance counts.
4. **Tour.** Each agent follows the predicted tour, except where the next
   node's sign was hidden from where the agent chose (same rule and
   tolerance as criterion 3).
5. **No patrol in sight of the exit.** No `wander` decision is taken where the
   exit sign is legible from every point within the tolerance of criterion 3.

All five pass on the 0.05 m grid, and on 0.1 and 0.025 m. On 0.25 m criterion
3 fails once.

The speed bounds in the table are sanity checks, not criteria: pushed by
neighbours, agents reach 2.0 m/s, so \(L/v_0\) is not a strict bound.

## Run it yourself

No FDS is needed. Run the two decks, the discovery deck on each grid:

```bash
uv run python run.py --scenario assets/familiarity_test_full --seed 420 \
  --output-route-history <out>/full/routes.csv \
  --output-sqlite <out>/full/run.sqlite --cleanup
for c in 0.25 0.1 0.05 0.025; do
  uv run python run.py --scenario assets/familiarity_test_discovery --seed 420 \
    --vis-cell-size $c \
    --output-route-history <out>/discovery_cell$c/routes.csv \
    --output-sqlite <out>/discovery_cell$c/run.sqlite --cleanup
done
uv run python scripts/verification/familiarity_figures.py --data <out>
```

Each run takes seconds. The script prints every number on this page. The
runs used here (main at `9bd5c28`, macOS arm64) are in the project's data
folder, `fds-evac-data/familiarity_test_discovery/evac/`.

Reruns on the same machine reproduce these numbers to the last digit. Across
platforms, or with other runs in the same process, they need not
([#198](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/198),
[#199](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/199)); the
tests on generated worlds (`tests/test_generated_worlds.py`) therefore
assert invariants, not trajectories.

To see what each agent knows over time, call
`run_scenario(..., collect_cognitive_map_history=True)`: it returns one row
each time an agent's map changes (`time_s`, `agent_id`, `known_nodes`,
`known_edges`). `scripts/animate_cognitive_map.py` turns it into a movie of
one agent.

## Limits

- **The discovery egress time is not converged in the grid**
  ([#168](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/168)).
  It comes from agents turning back at the door of the only exit
  ([#250](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/250)),
  because arrival registers before the door
  ([#69](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/69)). Do not
  quote a discovery egress time without its grid.
- **Grid.** `run.py` uses a 0.25 m sight grid by default. On this deck it
  sees through every wall, and criterion 3 fails. Pass
  `--vis-cell-size 0.05` for the discovery deck; a warning for grids coarser
  than the walls is proposed in
  [#168](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/168).
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
  `smoke_reroute`, also in clear air: every change of exit gets that label.
- **Not yet an automated test.** The checks run in the figure script on the
  stored output. `scripts/golden_rerouting.py` records these runs, the grid
  sweep included, as golden output, and `tests/test_rerouting_golden.py`
  pins route decisions on these decks under synthetic smoke; both are
  regression checks, not verification.
- **History.** Before
  [#99](https://github.com/PedestrianDynamics/pyFDS-Evac/pull/99) the deck
  had a scripted tour and hand-added shortcut edges, and a second exit; the
  talk's 35.1 s and 75.1 s come from that version and are not comparable.
