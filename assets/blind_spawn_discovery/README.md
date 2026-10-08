# Blind spawn: discovery through occlusion

**What does an agent do when it knows no way out at all?**

Every other discovery asset here is one convex room whose builder *asserts* that
an exit is legible from the spawn area, so an agent always has a default target.
This one removes that guarantee. Both exits are behind walls, so a `discovery`
agent spawns with no exit in its cognitive map, `rank_routes` returns nothing,
and the agent has to explore.

That state had never occurred in a simulation before this asset. Finding out
what happens in it is the point — and what happened first was that nothing did.
See "What this asset found" below.

## Layout

```
 y=30  +---------------+---------------+
       |   west room   |   east room   |
       |   [E_west]    |   [E_east]    |
 y=22  +-----[C2]------+------[C3]-----+     doorways, 2 m wide
       |          corridor             |
 y=18  +------------[C1]---------------+     doorway, 2 m wide
       |                               |
       |     spawn hall, 30 agents     |
 y=0   +-------------------------------+
      x=0                            x=24
```

## Hidden by geometry, not by distance or bearing

Both exits sit **24.7 m** from the spawn centroid, inside the 30 m visibility
ceiling, and both signs are **omni-directional** (`alpha` omitted, which
fdsvismap reads as readable from any bearing). Distance and bearing are
therefore ruled out, and only one term of the legibility rule is left to hide
them:

```
view_angle · visibility · non_concealed  ≥  distance
```

| term | value here | why |
|---|---|---|
| `view_angle` | 1 | every sign is omni-directional |
| `visibility` | 30 m | clear air, so `min(c/K̄, max_vis) = max_vis` |
| `non_concealed` | **0** | the wall |
| `distance` | 24.7 m | inside the ceiling |

`non_concealed` is fdsvismap's line-of-sight mask, and until this asset it had
no test at any level. `build_geometry.py` refuses to write the asset unless the
exits are *both* inside the ceiling and occluded, because an asset that hid them
by distance instead would look identical from the outside and would test nothing
new. `test_removing_the_walls_would_make_the_exits_legible` closes the loop from
the other side.

## The expected sequence, and why it is three hops

| hop | map | routing | why |
|---|---|---|---|
| 0 | `{spawn, C1}` | ranking **empty** → explore to `C1` | exits occluded; `C1` visible |
| 1 | `+ C2, C3` | still empty → explore to the **nearer** doorway | `expand_on_arrival` reveals neighbours; exits are not neighbours of `C1` |
| 2 | `+ E_west` or `+ E_east` | commits to that exit | the exit behind the doorway it chose |

Hop 1 stays exit-free only because **betweenness pruning** keeps the exits
non-adjacent to `C1`:

```
jps-distributions_0 -> C1
C1                  -> C2, C3
C2                  -> E_west, C1, C3
C3                  -> E_east, C1, C2
```

`expand_on_arrival` ignores visibility entirely and reveals *every* neighbour,
so pruning is the only thing standing between this scenario and a single hop.
`test_but_still_no_exit` asserts it directly, rather than letting the scenario
silently collapse if pruning regresses.

## Configs

One geometry, four configs, each changing exactly one thing.

| config | familiarity | entrance | egress | what it isolates |
|---|---|---|---|---|
| `config_discovery.json` | `discovery` | — | 35.3 s | the sequence above |
| `config_full.json` | `full` | — | 43.6 s | straight out, 0 switches |
| `config_entrance.json` | `discovery` | `E_west` | 43.6 s | seeding: knows one door at t=0 |
| `config_mixed.json` | `0.5` | — | 38.2 s | scalar familiarity in a run |

At the deck's seed, 1301, all four evacuate 30/30. In the `full` and
`entrance` runs all 30 agents leave by `E_west`; the two exits are equally
far from the spawn centre, and the `discovery` and `mixed` crowds split
between them (west/east 14/16 and 11/19), so they are out sooner. The
`discovery` run makes 90 route changes, `mixed` 24, the others none.
Measured at commit `828ae8c3` (fdsvismap 0.3.2) with the `run.py` recipe
below, one `--vis-cache` per config, on the FDS 6.10.1 output of
`blind_spawn_discovery.fds`, with `--allow-fds-horizon-hold` because the
FDS run ends at 120 s. The exit is the side of the agent's last position
(x < 12 m: `E_west`).

Not every seed finishes. In clear air (no `--fds-dir`, 0.25 m grid) at
`828ae8c3`, `config_discovery` completes 41 of 41 runs (seeds 1–40 and
1301), `config_mixed` 19 of 20 (seeds 1–20; seed 15 does not) and
`config_entrance` 19 of 20 (seed 10 does not); in both, two agents block
each other in a doorway
([#359](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/359)).

`config_entrance.json` is the Station crush mechanism in miniature — everyone
entered by one door, so everyone knows that door. It was wired through the code
with no behavioural test anywhere until this asset.

## Running it

```bash
mkdir -p /tmp/bsd && cd /tmp/bsd \
  && fds /path/to/assets/blind_spawn_discovery/blind_spawn_discovery.fds && cd -

.venv/bin/python run.py \
    --scenario assets/blind_spawn_discovery/config_discovery.json \
    --fds-dir /tmp/bsd --allow-fds-horizon-hold \
    --vis-cache /tmp/vis_bsd.npz \
    --output-sqlite /tmp/bsd.sqlite \
    --output-route-history /tmp/bsd_routes.csv

.venv/bin/python scripts/plot_trajectories.py /tmp/bsd.sqlite \
    --config assets/blind_spawn_discovery/config_discovery.json \
    --route-history /tmp/bsd_routes.csv \
    -o assets/blind_spawn_discovery/trajectories_discovery.png \
    --title "blind_spawn_discovery -- config_discovery.json"
```

`--vis-cache` is what constructs the visibility model; without it every
neighbour enters the map unconditionally and a `discovery` agent behaves like a
`full` one. Each config needs its own cache file — the sign descriptors are part
of the cache metadata.

![trajectories](trajectories_discovery.png)

**Grey means exploring.** The plotter colours a path by the exit targeted at
that moment, and while an agent is heading for a doorway it has no exit target
at all. So grey is the state this asset exists to produce, and the two dots on
each path are the two frontier hops.

## What this asset found

Three engine defects. This section records what the runs showed when the
asset was built (#66, `42fcbac2`, August 2026) and when the third defect was
fixed (#70, `bec65fa9`); its counts, times and sequences are from those
commits, not from current runs. The first two made frontier exploration impossible in any
simulation while every unit test passed. The unit tests call
`evaluate_and_reroute` directly; only a simulation runs the direct-steering loop
that produces the state.

**1. A frontier hop retired the agent.** `advance_path_target` set
`state="done"` whenever a stage had nothing scripted after it. `done` means
"finished" — the reroute pass skips those agents — but for an explorer it meant
"arrived at the frontier", which is precisely when it must re-plan. First run:
**0 of 30 evacuated.** Arrival now records the stage as the routing origin and
leaves the agent `idle`, which is re-evaluated.

**2. The same-exit branch froze half the crowd.** Agents are assigned a nearest
exit by straight-line distance before routing runs, and that seeds
`route_state.current_exit`. When an explorer discovered exactly that exit,
`old_exit == best.exit_id` sent it down the same-exit branch, which compares
against a committed path an idle agent does not have — so it was never routed
anywhere. Second run: **10 of 30**, and every one of those ten had been assigned
`E_east` and discovered `E_west`. The other twenty were assigned `E_west`,
discovered `E_west`, and stood at the doorway for 300 s.

Both are pinned by `TestAnIdleAgentIsNotRetired` in `tests/test_route_graph.py`,
verified to fail without the fixes.

**3. The crowd could not fan out** (issue #68, fixed separately).
`nearest_frontier_target` measured with `shortest_path_to(source, node)` — from
the graph *node*, never from the agent. `C2` and `C3` are equidistant from `C1`
by construction, so `sorted(frontier)` broke the tie identically for everyone
and **all 30 agents used the west door**; the east room was never entered,
however the crowd was spread across the hall.

The exit ranking had been position-aware since `_position_aware_length`;
exploration was simply never given the same treatment. It now substitutes the
walk from the agent's position for the first leg, exactly as exit ranking does.
Agents to the west of `C1` take `C2`, agents to the east take `C3`, and the
split falls out of geometry rather than out of `sorted()`:

```
sequences: {('C1','C3','E_east'): 18, ('C1','C2','E_west'): 11,
            ('C1','C3','C2','E_west'): 1}
```

Egress drops from 43.3 s to 38.0 s, because both doors are now used.

That one four-hop agent is worth noting: it explored to `C3`, never registered
arrival there, and re-explored to `C2` as it drifted west. That is issue #69 —
arrival is proximity to a random point inside the stage box, not containment in
it — showing up in the wild. It still evacuated.

## Deliberate choices

**Clear air.** The extinction field is zero, so `visibility = max_vis`
everywhere and legibility depends on geometry alone.

**Symmetric exits.** `C2` and `C3` are equidistant from `C1`, so the node
distance cannot separate them and only the agent's own position can. That is
what makes the asset a test of issue #68 rather than of arithmetic.

**Checkpoint boxes 2 m deep, not 0.4 m.** Direct steering walks each agent to a
random point inside the stage polygon and counts arrival within 0.7 m of *that
point*. A box only as deep as the wall gives thirty agents the same sliver to
aim at. The builder asserts a minimum depth. (Related: `inside_since` and
`reach_penetration` are written into `wait_info` and never read — arrival is
proximity to a point, not containment in the polygon.) An explorer with
nothing left to explore first walks to the node's routing point and looks
from there before it patrols
([Models › Wayfinding §2.4](https://pedestriandynamics.org/pyFDS-Evac/models/wayfinding/#2-the-knowledge-contract)).

**No journeys or transitions.** The graph auto-wires and cost decides, which is
what puts betweenness pruning on the critical path.

## Regenerating

```bash
.venv/bin/python assets/blind_spawn_discovery/build_geometry.py
```

Writes `geometry.wkt`, `blind_spawn_discovery.fds` and all four configs, and
refuses if any premise has broken — exits outside the ceiling, exits visible,
`C1` invisible, asymmetric exits, or checkpoint boxes too shallow.

## Tests

`tests/test_blind_spawn_discovery.py`, 26 tests, no FDS output needed:
`OccludingVisMap` reimplements the line-of-sight term on the walkable polygon,
the same way `test_cognitive_map_memory.py` reimplements the view-angle term.
