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
favours `E_near` by more than 2:1 in both runs.

### Why the corridor is 30 m and not longer

fdsvismap decides legibility as `view_angle * visibility >= distance`, and in
clear air `visibility` saturates at its `max_vis` default of **30 m**. Because
`view_angle` is clipped to `[0, 1]`, a sign further than 30 m away can never be
legible **at any bearing**.

An earlier draft used a 44 m corridor, putting `E_far` 33 m from the spawn
area. In the hidden run *both* exits were then illegible, the fallback
reinstated the least-cost rejected route, and agents took `E_near` regardless —
an experiment that proves nothing while appearing to run correctly. The builder
now asserts both signs sit inside the cap, and a test checks the same thing.

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
