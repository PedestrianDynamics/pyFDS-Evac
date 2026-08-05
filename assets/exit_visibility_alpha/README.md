# Exit visibility vs. sign bearing

A single-variable experiment: **does an agent abandon its nearest exit when
that exit's sign faces away from it?**

The two configs in this directory are byte-identical apart from one number —
the viewing bearing (`alpha`) of the near exit's sign. Any difference in exit
choice is therefore attributable to sign orientation and nothing else.

## Layout

A straight north–south corridor, 4 m wide and 30 m long.

```
 y = 30  +--------+   E_far    alpha = 180, always legible
         |        |
 y = 12  |  spawn |   200 agents
 y =  8  |        |
 y =  0  +--------+   E_near   alpha is the experiment's variable
```

Agents stand roughly 9 m from `E_near` and 19 m from `E_far`, so distance
favours `E_near` by more than 2:1 in both runs. The corridor is 30 m rather
than longer for a reason — see the pitfall below.

## Pitfall: the visibility ceiling

**Read this before building any scenario that depends on sign legibility.**

fdsvismap decides that a sign is legible from a cell when

```
view_angle x visibility >= distance
```

with `view_angle` clipped to `[0, 1]` (`FDSVisMap._get_view_angle_array`) and

```
visibility = c / mean_extinction     capped at max_vis, default 30 m
                                     equal to max_vis when extinction is 0
```

(`FDSVisMap._get_visibility_array`, `FDSVisMap.get_vismap`).

Two consequences that are easy to miss:

**In clear air the reach is 30 m, full stop.** Extinction is zero, so
`visibility` is `max_vis`. Because `view_angle` cannot exceed 1, a sign more
than 30 m away is illegible **at every bearing**. No choice of `alpha` rescues
it.

**With smoke the reach is `c / K̄`, which is usually far shorter.** The cap
stops mattering almost immediately:

| `c` | mean extinction `K̄` | usable radius |
|---|---|---|
| 3 (reflective) | 0.0 (clear) | 30 m — the cap |
| 3 | 0.1 | 30 m — still capped |
| 3 | 0.2 | 15 m |
| 3 | 0.5 | 6 m |
| 8 (illuminated) | 0.5 | 16 m |

So a smoke scenario needs its exits inside the *smoke-reduced* radius, not
inside 30 m. Sizing a corridor against the clear-air ceiling and then adding
smoke will silently push every sign out of range.

### Why this bites quietly

An out-of-range sign does not raise. Its route is rejected as
`next_node_not_visible`, and if *every* route is rejected the fallback
reinstates the least-cost rejected one — so agents proceed to the nearest exit
exactly as if visibility were never modelled. The simulation runs, the numbers
look plausible, and the experiment measures nothing.

This scenario hit precisely that. An earlier draft used a 44 m corridor with
`E_far` 33 m from the spawn area:

```
OLD corridor (44 m), hidden config
  E_near  d= 9.3  view_angle=0.00    0.0 >=  9.3 ? False
  E_far   d=33.3  view_angle=1.00   30.0 >= 33.3 ? False   <- never legible
```

Both exits illegible, fallback to `E_near`, and the assertion "agents take the
near exit when its sign is visible" passed for the wrong reason. The corridor is
30 m so that `E_far` sits at 19.3 m, comfortably legible head-on, while distance
still favours `E_near` by more than 2:1.

### Guards

Two, because a silent failure needs catching from both ends:

- `build_geometry.py` refuses to write the asset if either sign is at or beyond
  `MAX_VIS_M` from the spawn centroid.
- `test_both_exits_are_inside_the_visibility_cap` asserts the same, and further
  asserts `view_angle * max_vis >= distance` for both — so a bearing that is
  merely *poor* rather than reversed is caught too.

The test double models the full rule rather than the half-plane alone. That
distinction is what makes the guard possible: a half-plane-only double reports
a 33 m sign as perfectly legible.

## The two runs

| config | `E_near` alpha | sign faces | expected outcome |
|---|---|---|---|
| `config_visible.json` | 0 | north, toward the agents | all agents take `E_near` |
| `config_hidden.json` | 180 | south, away from them | `E_near` rejected as `next_node_not_visible`; all agents walk the extra 10 m to `E_far` |

`alpha` is a compass bearing in degrees clockwise from north. fdsvismap makes a
sign legible only within the half-plane it faces, with cosine falloff — head-on
gives a factor of 1, 90° to the side gives 0, and behind is clipped to 0.

The flip is the point. Distance still favours `E_near` in both runs, so a model
that ignored sign orientation would send agents there either way.

## Deliberate choices

**Familiarity stays `full`.** Sign-visibility rejection lives in `rank_routes`
and does not consult the cognitive map, so this scenario isolates the
visibility channel without involving discovery.

**The air is clear.** `exit_visibility_alpha.fds` carries no fire, so the
extinction field is zero everywhere and legibility is decided by viewing angle
and distance alone. That is what keeps `alpha` the single independent variable —
with smoke present, an outcome could always be attributed to extinction
instead.

**No journeys or transitions.** The stage graph auto-wires every spawn area to
every exit and the composite cost decides, which is the routing mode this
experiment is about.

## Regenerating

```bash
.venv/bin/python assets/exit_visibility_alpha/build_geometry.py
```

This writes `geometry.wkt`, both configs, and `exit_visibility_alpha.fds`. The
FDS deck is generated from the WKT via `pyfds_evac.core.wkt_to_fds`, with the
generator's burner stripped and its analysis slices kept — fdsvismap needs a
`SOOT EXTINCTION COEFFICIENT` slice to answer any legibility query at all, so
`--geometry-only` would not do, since it drops the slices along with the fire.
The builder asserts both conditions and fails loudly if either is violated.

## Tests

`tests/test_exit_visibility_alpha.py` drives this asset through the real
routing code. It needs no FDS output: it reimplements fdsvismap's clear-air
rule — `view_angle * max_vis >= distance` — so the test exercises our routing
decision rather than the third-party visibility solver. Modelling the distance
comparison and not merely the half-plane is what makes the cap guard possible.

Alongside the two headline assertions it carries four guards, because the
experiment is worthless if its premises silently drift:

- the configs differ in nothing but the bearing;
- `E_near` really is the closer exit;
- both signs sit inside the 30 m visibility cap, so neither is illegible for
  the trivial reason of being too far away;
- with no visibility model, **both** configs choose `E_near` — so the flip is
  caused by legibility, not by some accident of the geometry.

Running the scenario as a full simulation additionally requires FDS output for
the deck; the tests do not.
