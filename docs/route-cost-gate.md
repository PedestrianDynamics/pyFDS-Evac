# The gate cost model

> Part of [pyFDS-Evac](../README.md). Reference for `routing.cost_model`.
> Provenance, review findings and the open questions live in
> [gate-model-review-notes.md](gate-model-review-notes.md); this page documents
> what the shipped code does.

Route choice runs under one of two cost models, selected per deck with
`routing.cost_model` in the scenario JSON:

| value | what decides the exit |
|---|---|
| `"gate"` (default) | Distance is the objective; smoke decides which exits are *available*. |
| `"additive"` | Smoke is a toll per metre walked, folded into one composite cost. |

Both are implemented in `pyfds_evac/core/route_graph.py`
(`RouteCostConfig`, `evaluate_route`, `rank_routes`, `evaluate_and_reroute`).

## Quick start

Nothing to configure: the gate is the default. To pin the pre-gate behaviour
of an existing deck, set **both** keys — `anticipate` is independent of
`cost_model` and defaults to `true`:

```json
{
  "routing": {
    "cost_model": "additive",
    "anticipate": false
  }
}
```

To make the gate stricter or laxer, change `sight_distance_fraction` (a route
is refused when sighting distance falls below this fraction of the distance
still to walk):

```json
{
  "routing": {
    "cost_model": "gate",
    "sight_distance_fraction": 0.5,
    "sign_contrast_c": 3.0,
    "band_width_m": 10.0
  }
}
```

**Precondition.** The gate reads sighting distance from the visibility model.
`_gate_needs_sight` (`pyfds_evac/core/run_config.py`) therefore builds one for
*any* deck that runs with rerouting enabled and `cost_model` left at `"gate"` —
including decks whose agents are all `familiarity: 1.0`, which previously
skipped it. That costs a vismap precompute at startup. Pass `--vis-cache PATH`
to make it a one-off: the cache is written if missing and loaded if present.
Without a visibility model the gate still runs, but only on its coarser
fallback criterion (below).

## How the gate decides

Per agent, per reevaluation tick:

1. **Availability.** Each candidate route is tested. A route is refused when
   its sighting distance falls below `sight_distance_fraction` (default 0.5)
   times the distance still to walk, or when its projected FED exceeds the FED
   threshold.
2. **Ordering among survivors.** Visibility band first (`band_width_m`,
   default 10 m), then travel time. The rank cost under the gate is
   `travel_time_s + w_queue * queue_time_s`.
3. **Tie-break.** Fewer hops.

Ordering by band before time is what lets a genuinely clearer route win
outright while a few centimetres of visibility never sends anyone on a detour.
Band index is `int(sighting_distance // band_width_m)`.

In clear air `K = 0`, sighting distance is infinite, nothing is refused and
every route lands in the top band — so the gate reduces to nearest-exit. The
two models were measured identical on the `world_100` (7712 route-cost rows)
and `t_junction` (4030 rows) clear-air runs, and the `l_corridor` clear-air
pair evacuates 100/0 to the near exit under both with zero switches. Note the
scope of that check: it holds at `K = 0` exactly, not at small nonzero `K` —
see limitations.

### Sighting distance, and the two ways it is measured

Sighting distance is Jin's relation

```
S = c / K
```

with `c = sign_contrast_c` (default 3, light-reflecting signage; 8 is the value
for internally illuminated signs). It is deliberately uncapped, so `K = 0`
gives infinite sight.

What differs between the two criteria is *which* `K` and *which* distance:

| criterion | `K` | compared against | when it fires |
|---|---|---|---|
| `sight (los)` | `K_ave` along the real, obstruction-aware sight line to the exit's own sign, read from fdsvismap | `sight_distance_fraction` x straight-line distance to that sign | whenever a sight line resolves |
| `sight (path)` | worst `K` sampled over the route polyline | `sight_distance_fraction` x the whole remaining route length | fallback, when no sight line resolves |

`los` is FDS+Evac's `See_door` quantity, so the test reduces to a statement
about optical depth along one leg. `path` is the stricter reading: it demands
low `K` *everywhere* on the route and compares against the full remaining
length, so it penalises long routes. It is used only where there is no sight
line to read — an exit with no sign descriptor, a concealed one, one the agent
is standing behind, or a cache that holds no distances.

The rejection reason records which fired, for example:

```
sight (los) 8.8 m < 10.9 m (0.5 x 21.8 m)
sight (path) 2.1 m < 29.0 m (0.5 x 58.0 m)
```

so a route-cost CSV can be filtered on the criterion.

### Refusals are not remembered

The criterion is measured against the distance *still to walk*, so it relaxes
as the agent closes in: smoke that refuses a door at 40 m accepts it at 2 m.
Every tick re-decides from the current field; there is no permanent exit death.

### When every route is refused

The agent still has to move. `rank_routes` re-sorts the refused routes by
`(-band, rank_cost)` — banded, then nearest — and un-rejects the head with a
`fallback:` prefix on its reason. The agent keeps its current target unless a
rival's worst extinction is better by more than `fallback_switch_margin`
(default 0.2), i.e. unless

```
rival.k_max_route <= current.k_max_route * (1 - fallback_switch_margin)
```

Nearest, not farthest, breaks the tie inside a band. Banding makes ties common
rather than measure-zero, and "farthest" systematically sent agents the long
way round — measured: a 51 m route chosen over a 22 m one on 2.0 m of sight
against 1.8 m.

### Churn protection

Under the gate the **exit-switch anchor** is the only other churn protection.
A different exit is adopted only when its rank cost beats
`old_cost * exit_switch_anchor` (default 0.9) — with one gate-specific bypass:
a rival that is both `feasible` and a whole band clearer is adopted outright,
because banding is the model's statement that the two routes are not comparable
on time. The bypass requires feasibility on purpose; letting refused routes
jump the anchor made agents ping-pong as bands healed and re-broke.

### Anticipation

With `anticipate` (default `true`), each segment is priced at the time the
agent would *arrive* there rather than the time it decides:

```
arrival_time = now + min(distance_walked_so_far / base_speed_m_per_s,
                         foresight_horizon_s)
```

The unimpeded `base_speed_m_per_s` is used, not the smoke-reduced speed: the
reduction depends on the smoke at the arrival time being computed, and one pass
settles what a second would only refine. `foresight_horizon_s` defaults to
infinity, which is perfect foresight of the FDS solution; a finite horizon
models an occupant who can only judge the near future.

**`anticipate` is independent of `cost_model`.** It applies under `"additive"`
too, which is why pinning pre-gate behaviour needs both keys.

## The additive model

```
composite = effective_length * (1 + w_smoke * K_ave)
          + w_fed * FED_max
          + w_queue * base_speed_m_per_s * queue_time      (when w_queue > 0)
```

and routes are ordered by `(rejected, composite, hops)`.

Both smoke and length terms scale with route length, so a long clean detour
pays for its own length and can never win however large `w_smoke` is — sweeping
it 1 → 20 on `assets/world_100` moved 12 of 120 agents. That is the reason the
gate exists.

`composite_cost` is still computed and reported under the gate; it simply does
not rank.

## Configuration

Every key below is read from the scenario's `routing` block by
`RouteCostConfig.from_routing_params`. Keys are flat, not nested:

```json
{
  "routing": {
    "cost_model": "gate",
    "sight_distance_fraction": 0.5,
    "band_width_m": 10.0
  }
}
```

| JSON key | Default | Effect | Under `"gate"` | Under `"additive"` |
|---|---|---|---|---|
| `cost_model` | `"gate"` | Selects the model. Unvalidated: any other string behaves as `"additive"`. | — | — |
| `sight_distance_fraction` | `0.5` | Fraction of remaining distance that must be visible for a route to stay available. | active | inert |
| `sign_contrast_c` | `3.0` | Jin's `c` in `S = c / K`. 3 reflective, 8 internally illuminated. | active | inert |
| `band_width_m` | `10.0` | Width of a visibility band, in metres of sighting distance. Ordering is by band before time. | active | inert |
| `anticipate` | `true` | Price each segment at the agent's arrival time. | active | **active** |
| `foresight_horizon_s` | `inf` | Cap on how far ahead anticipation reaches, in seconds. | active | **active** |
| `fallback_switch_margin` | `0.2` | Hysteresis when every route is refused. | active | inert |
| `w_smoke` | `1.0` | Smoke weight. Multiplies `K_ave` in the composite **and in the Dijkstra edge weights** — see limitations. | partly active | active |
| `w_fed` | `10.0` | FED weight. Same: composite **and** Dijkstra edge weights. | partly active | active |
| `w_queue` | `0.0` | Congestion weight, off by default. | active (as `w_queue * queue_time_s` on the rank cost) | active (as distance-equivalent in the composite) |
| `fed_rejection_threshold` | `1.0` | Projected FED above which a route is refused. | active | active |
| `visibility_extinction_threshold` | `0.5` | `K` above which a segment is flagged non-visible; a route whose segments are *all* non-visible is refused when some other route has a visible segment. | active | active |
| `sampling_step_m` | `2.0` | Spacing of extinction samples along an edge polyline. | active | active |
| `base_speed_m_per_s` | `1.3` | Clear-air walking speed. Sets travel time, anticipation, and the queue conversion. | active | active |
| `alpha` | `0.706` | Lund speed-law coefficient. | active | active |
| `beta` | `-0.057` | Lund speed-law coefficient. | active | active |
| `min_speed_factor` | `0.1` | Floor on the smoke speed factor. | active | active |
| `default_exit_capacity` | `1.3` | Fallback exit capacity, agents/s, when the exit sets none. | active | active |

Two `RouteCostConfig` fields are **not** readable from the `routing` block and
keep their dataclass defaults in any scenario run: `fed_return_margin` (0.9,
the asymmetric FED hysteresis) and `impassable_extinction_threshold` (3.0, the
route-average extinction above which a smoke rejection bypasses the anchor).
Setting them requires constructing `RouteCostConfig` in Python.

`exit_switch_anchor` (default 0.9) belongs to `RerouteConfig`, not to
`RouteCostConfig`.

## Known limitations

These are real and documented, not hypothetical. Details and measurements are
in [gate-model-review-notes.md](gate-model-review-notes.md).

- **`w_smoke` and `w_fed` still choose the path.** Dijkstra's edge weights are
  `length * (1 + w_smoke * k_avg) + w_fed * fed_growth` under both models, at
  the decision time and without anticipation. The gate then judges the single
  path Dijkstra returned per exit. If an exit has a short smoky path and a
  longer clean one, Dijkstra returns the smoky one and the gate refuses the
  exit. (Measured neutral on `t_junction`: gate with `w_smoke = 0` reproduced
  gate with `w_smoke = 5` exactly.)
- **The extinction thresholds still apply under the gate.**
  `visibility_extinction_threshold` and `impassable_extinction_threshold` were
  meant to be additive-model machinery; both still run.
- **Bands are unbounded above** (`_MAX_BAND` is 10^6). At small but nonzero
  `K` — which real FDS fields have almost everywhere — two physically clear
  routes can land in different bands and band ordering outranks travel time.
  Clear-air equivalence is verified exactly at `K = 0`, not at `K = 1e-4`.
- **`cost_model` is an unvalidated free string.** A typo silently yields the
  additive model.
- **Gate diagnostics are missing from the route-cost CSV.** `k_max_route`,
  `min_visibility_m`, `band` and `feasible` are computed but not written; only
  the numbers embedded in the rejection string are recoverable.
- **FIC does not participate in routing under either model.** It drives the
  Purser slowdown and incapacitation only. FIC and the sight gate are driven by
  the same smoke, so routing on both would double-count.

## Evidence

`assets/l_corridor` is the deck the model is judged on: an 11 m exit behind the
fire and a clean 58 m way round, so distance alone prefers the near exit by more
than 5x and any diversion is unambiguously smoke-driven. Results are in
`<sciebo>/fds-evac-data/l_corridor/evac/RESULTS.md` (100 agents, seed 1,
familiarity 1.0):

| run | fire | near / far | switches |
|---|---|---|---|
| gate | `fire_1MW_west` | **84 / 16** | 14 `smoke_reroute` |
| additive | `fire_1MW_west` | 100 / 0 | 23 `smoke_reroute` |
| gate, control | `fire_1MW` | 99 / 1 | — |
| gate, clear air | none | 100 / 0 | 0 |
| additive, clear air | none | 100 / 0 | 0 |

The control run puts the fire east of the junction, where the far route smokes
first; the gate then diverts 1 agent instead of 16, so it is not simply
preferring long routes.

**Read the headline with its caveat.** On that deck there were **zero `los`
rejections**: the near exit lies straight down the bottom corridor, its sight
line resolved on 2926 queries, and `3/K` along it stayed above half the
remaining distance throughout. All 1220 refusals were `sight (path)` on the far
exit, which lies around two corners and has no sight line. The 84/16 split is
therefore produced by the *fallback* criterion and by band ordering, not by the
LOS test. That matters before anyone calibrates `sight_distance_fraction`.

`assets/t_junction` is **not** a route-choice benchmark. Its 2 MW PVC fire
drives route `K` to about 10.7 /m — a Jin sighting distance of 0.28 m — so every
route is refused under any Jin-based criterion. Keep it as a lethality and
speed-collapse case.

## References

- [FDS+Evac Technical Reference and User's Guide](../materials/FDS+EVAC_Guide.pdf)
  — Korhonen (2021).
- `materials/evac.f90` — the reference implementation; line-level citations for
  the door criteria are in [gate-model-review-notes.md](gate-model-review-notes.md).
- [Boerger et al. (2024)](../materials/waypoint_based_visibility.pdf) —
  waypoint-based visibility, Beer-Lambert integrated extinction (Eq. 8-9).
- Jin, T. (1978). Visibility through fire smoke. *Journal of Fire and
  Flammability*, 9, 135-155. — `S = c / K`, `c = 3` for reflecting signs.
- [assets/l_corridor/README.md](../assets/l_corridor/README.md) — the deck, its
  fire, and the measured smoke contrast.
