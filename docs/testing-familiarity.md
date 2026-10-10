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
| **Status** | on the 0.05 m reference grid criteria 1–3 and 5 pass, and criterion 4 fails because 4 agents deadlock in CP1's door ([#359](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/359)); criteria 1–5 pass on the 0.1 and 0.025 m grids; the `run.py` default of 0.25 m does not resolve the walls; criterion 6 (30 seeds) fails on both halvings, 0.1 → 0.05 m and 0.05 → 0.025 m, because of #359 deadlocks, and passes on both when the deadlocked runs are left out ([#168](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/168)). The deadlocks became more frequent with [#726](https://github.com/PedestrianDynamics/pyFDS-Evac/pull/726) (0.5.0), which counts a checkpoint as reached once the agent is inside its box |

![Two copies of the same plan side by side. Left, 20 fully familiar agents walk straight to the one door in the partition and out. Right, 20 discovery agents first explore the dead-end rooms in the west; 16 then walk through the door and out, and 4 stop in CP1's door, deadlocked. Agents are coloured by the node they are heading for](/images/verification/familiarity.gif)

*Left: `full`. Right: `discovery`, 0.05 m sight grid. Colour: the node the
agent is heading for (full: CP3 until it passes the door, then the exit;
discovery: its current route target).*

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
  has not visited (walking distance). With none left, it looks from its
  current node's point and then, if that teaches it nothing, patrols the
  nodes it knows (`wander`;
  [Models › Wayfinding §2.4](/models/wayfinding.md#2-the-knowledge-contract)).

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

The last row matters. Arrival at a checkpoint registers when the agent's
centre is inside its box, or within r + 0.5 m (0.7 m here, r = 0.2 m) of a
random target point in the box
([#69](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/69)). The
target is drawn at least 0.8 r = 0.16 m inside the box, so arrival at CP3
can register from y = 12.68 m, still south of the door and of the sign line. There
the exit sign is behind the jamb, and arriving teaches nothing. If the agent
has stepped past the jamb by its next re-evaluation, it sees the exit and
leaves. If not, it has no frontier left. Before it patrols, it walks until
CP3's node point lies within its body radius, senses from there and decides
again
([Models › Wayfinding §2.4](/models/wayfinding.md#2-the-knowledge-contract)).
The criteria test that each decision matches what the agent could see.

![Zoom on CP3's door: the partition with its 1.2 m door, the CP3 box north of it, the dashed region where arrival can register, within 0.7 m of a target point drawn at least 0.16 m inside the box, reaching south of the door to y = 12.68 m, the green line above which the exit sign is legible, with its grid tolerance band, and the CP3 node point, marked with a cross inside the box](/images/verification/familiarity_door.png)

## Result

![Walked paths of the 20 agents on the two plans, coloured by the node each agent is heading for. Full agents go straight to CP3 and the exit. Discovery agents walk CP0, CP1, CP2, back through CP0 to CP3 and the exit; one goes from CP1 back to CP3 without CP2, and four stop in CP1's door, deadlocked](/images/verification/familiarity_paths.png)

Full agents never enter the west rooms. All 20 discovery agents explore them
first. 15 follow the predicted tour and leave. Agent 11 turns from CP1 to CP3
without visiting CP2: CP2's sign was not in sight where it stood at CP1, the
case criterion 4 allows. Agents 5, 6, 7 and 13 stop in CP1's door at about
40 s and stand there to the end of the run, the doorway deadlock of
[#359](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/359): the tours of three end there, and one had followed the predicted
tour so far. No agent turns back at CP3's door.

![Left: agents out over time for full and for discovery on four sight grids, with the reference times of 21 s and 40 s. Right: the route of each agent per run: full all direct; discovery at 0.25 m all on the tour; at 0.1 and 0.025 m 19 on the tour and one skipping CP2 because its sign was hidden at CP1. At 0.05 m the curve levels off at 16 of 20 out, because four agents are deadlocked in CP1's door: the bar shows 15 on the tour, one skipping CP2, and four deadlocked: one whose route so far follows the predicted tour and three that had not finished it](/images/verification/familiarity_egress.png)

| Check (0.05 m grid) | Expected | Simulated |
|---|---|---|
| full: map at t = 0; later changes | 6 nodes, 11 edges; 0 | 20 / 20; 0 |
| full: agents via CP3 only; route changes | 20 / 20; 0 | 20 / 20; 0 |
| full: walked / shortest path | ≥ 1 | 1.04–1.14 |
| full: first agent out (sanity check) | near \(t_{\text{ref}}\) = 21.1 s | 19.8 s |
| full: last agent out | no reference | 34.8 s; the door (y = 13.05 m) passes 20 agents in 7.7–22.1 s, 1.32 persons/s or 1.10 persons/(s·m) of door width |
| discovery: map at t = 0 | {S, CP0, CP3} | 20 / 20 |
| discovery: first target | CP0, 20 / 20 | 20 / 20 |
| discovery: nodes learnt later | each a neighbour of a known node, its sign in sight | 55 of 55 |
| discovery: tour up to CP3 | CP0 → CP1 → CP2 → CP3 where CP2's sign is legible at CP1 | **fails**: 16 / 20; agent 11 goes from CP1 to CP3, CP2's sign hidden there; 3 tours end in CP1's door, deadlocked ([#359](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/359)) |
| discovery: patrols started with the exit in sight | 0 | 0; no agent starts a patrol |
| discovery: first agent out (sanity check) | near \(t_{\text{ref}}\) = 40.0 s | 40.6 s |
| discovery: last agent out | no reference | 16 of 20 out; 4 deadlocked in CP1's door until the 300 s limit; no agent turned back at CP3 |

On other grids:

| Sight grid | Cells across a 0.1 m wall | Last out |
|---|---|---|
| 0.25 m | 0 | 76.3 s |
| 0.1 m | 1 | 82.4 s |
| 0.05 m | 2 | 16 of 20 out; 4 deadlocked in CP1's door ([#359](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/359)) |
| 0.025 m | 4 | 78.8 s |

At 0.05 m, agents 5, 6, 7 and 13 stop in CP1's door at 40–41 s, heading in
opposite directions, and stand there to the end of the run: the doorway
deadlock of [#359](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/359). Over seeds 1–30 (the runs of criterion 6), a doorway
deadlock ends 12 of 120 runs: 3 at 0.25 m (seeds 7, 29, 30), 2 at 0.1 m
(seeds 3, 12), 4 at 0.05 m (seeds 3, 12, 13, 14) and 3 at 0.025 m (seeds
12, 14, 27). Before [#726](https://github.com/PedestrianDynamics/pyFDS-Evac/pull/726) it ended 4 of 120 (0.25 m seeds 3 and 7, 0.1 m
seeds 20 and 28), and seed 420 deadlocked at 0.1 m instead of 0.05 m. A
bisection over the same runs ([#359](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/359#issuecomment-6100209538)) puts the change at #726, which counts
a checkpoint as reached once the agent is inside its box: its parent
`a9def615` reproduces the earlier numbers of this page exactly, and #726
itself gives those of `c619a046`. The deadlock moves between grids and
seeds; it does not follow the grid. On the other grids all agents are out by
76.3–82.4 s, and no agent turns back at CP3. At 0.25 m no cell centre falls
inside the walls, so the sight grid sees through them: agents learn CP2 from
the next room and the exit from south of the partition.

## Pass criteria

**Grid tolerance.** The sight grid moves the edge of the legible region. From
the code of `VisibilityModel.clear_air` and fdsvismap 0.3.2, each of four
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
evaluated; there, with no tolerance, 37 learnt nodes had their sign hidden in
exact geometry (12 of them CP2, learnt from the next room).

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
   what the agent could see. Here it holds trivially: no agent starts a
   patrol on any grid.
6. **Grid convergence of the discovery egress time.** Seeds 1–30, the
   last agent out of each run, a run that does not finish counted as 300 s.
   At each halving of the sight grid, 0.1 → 0.05 m and 0.05 → 0.025 m, the
   median and the 90th percentile (P90) over the 30 seeds change by less
   than 5 %. The rule was fixed before the runs
   ([#168](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/168)).
   Unlike the tables above, which read the last trajectory frame, it uses
   the simulation clock at the end of the run.
   - 0.1 → 0.05 m: median 74.6 → 74.7 s (+0.1 %), P90 85.4 → 300 s
     (+251 %): **fails**. Four runs at 0.05 m (seeds 3, 12, 13, 14) and two
     at 0.1 m (seeds 3, 12) do not finish; all are doorway deadlocks
     ([#359](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/359)) and count as 300 s.
   - 0.05 → 0.025 m: median 74.7 → 75.5 s (+1.1 %), P90 300 → 104.3 s
     (−65 %): **fails**, for the same reason; three runs at 0.025 m (seeds
     12, 14, 27) do not finish.
   - Without the runs that do not finish, both halvings pass: P90 −3.0 %
     (bootstrap 90 % interval −9.7 to +1.2 %) from 0.1 to 0.05 m, and
     +1.1 % (−1.8 to +4.2 %) from 0.05 to 0.025 m. The failure is the
     deadlock, not the grid.

| Grid | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| 0.1 m | pass | pass | pass | pass | pass | – |
| 0.05 m | pass | pass | pass | **fails**: 3 tours unexplained, agents deadlocked in CP1's door (#359) | pass | **fails** vs 0.1 m (P90 +251 %, #359) |
| 0.025 m | pass | pass | pass | pass | pass | **fails** vs 0.05 m (P90 −65 %, #359) |

On every fine grid one agent skips CP2 where its sign was not in sight, which
criterion 4 allows. At 0.05 m the tours of 3 of the 4 deadlocked agents end
in CP1's door, so they are not the predicted tour; the cause is the deadlock,
not the map. On the 0.025 m grid, the next finer one, criteria 1–5 all pass
for seed 420, which also points to the deadlock rather than the grid.

For seed 420, the run shown on this page, the clock gives 300 s at 0.05 m
(4 agents deadlocked) and 78.85 s at 0.025 m. #168 stays open: it is rerun
with the same rule once the #359 deadlock is fixed.

With no tolerance (*T* = 0), the results show how close to the edge some
decisions fall. Criterion 3 flags 7 learnt nodes at 0.1 m, 5 at 0.05 m and
none at 0.025 m. Criterion 5 flags no patrol. Criterion 4 is unchanged. Each
flag lies inside *T* of the edge of the legible region (CP1's and CP2's
signs near the west doors): there the grid decides, and exact geometry
cannot overrule it.

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

Each run takes seconds. The script prints every number on this page except
those of criterion 6. The numbers here come from these commands at commit
`c619a046` (Python 3.13.4, macOS arm64).

Criterion 6 runs the discovery deck for seeds 1–30 and 420 on each grid,
with the deck's `no_known_exit` and with `default_route`, one grid and mode
per process:

```bash
S=scripts/verification
for c in 0.25 0.1 0.05 0.025; do for m in explore default_route; do
  PYTHONHASHSEED=0 uv run python $S/familiarity_grid_study.py \
    --cell $c --mode $m --out <out>/results.jsonl $(seq 1 30) 420 &
done; done; wait
uv run python $S/familiarity_grid_analysis.py <out>/results.jsonl
```

Each of the 248 runs takes seconds. The analysis prints the medians, P90s,
changes, bootstrap intervals and verdicts quoted in criterion 6. The
numbers are from commit `c619a046`. Under `default_route` the agents learn
nothing after t = 0 on this deck, so the time (median 35.3 s, P90 36.2 s)
is the same on every grid; that arm is not a convergence test.

Reruns on the same machine reproduce these numbers to the last digit. Across
platforms they need not
([Limitations › Reproducibility](limitations.md#reproducibility)); the
tests on generated worlds (`tests/test_generated_worlds.py`) therefore
assert invariants, not trajectories.

`scripts/animate_cognitive_map.py` turns the map history of one agent into a
movie.

## Limits

- **The discovery egress time is not shown to converge in the grid**
  ([#168](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/168)).
  Criterion 6 fails on both halvings on this 30-seed sample, because of
  doorway deadlocks ([#359](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/359)) on every grid, and passes on both when the
  deadlocked runs are left out.
  #168 stays open, is blocked on the #359 fix and is then rerun with the
  same rule. Do not quote a discovery egress time without its grid, and on
  this deck use 0.05 m or finer.
- **The look is not logged.** The look from CP3's node point writes no
  route-history row, so the outputs this page checks cannot show where an
  agent looked. The page checks its effect (no patrol, no turn-back), not
  the look itself.
- **Grid.** `run.py` uses a 0.25 m sight grid by default. On this deck it
  sees through every wall, and the run logs a warning that the cell is not
  smaller than the thinnest wall
  ([#115](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/115)).
  Pass `--vis-cell-size 0.05` for the discovery deck.
- **No reference for the egress times.** The full run's last agent is out at
  34.8 s. Its door passes 1.32 persons/s (1.10 persons/(s·m) of the 1.2 m
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
- **Labels.** `routes.csv` records an agent's first exit as `initial`. A
  later change of exit is labelled by its cause; in clear air that is
  `learned_exit` or `shorter_path`, not `smoke_reroute`
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
