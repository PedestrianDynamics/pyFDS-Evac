# The gate cost model

> Part of [pyFDS-Evac](../README.md). Reference for `routing.cost_model`.
> Provenance, review findings and the open questions live in
> [gate-model-review-notes.md](gate-model-review-notes.md); this page documents
> what the shipped code does.

Route choice runs under one of two cost models, selected per deck with
`routing.cost_model` in the scenario JSON:

| value | what decides the exit |
|---|---|
| `"gate"` (default) | Travel time is the objective; smoke decides which exits are *available*. |
| `"additive"` | Smoke is a toll per metre walked, folded into one composite cost. |

Under the gate, smoke reaches the ordering only through the speed law inside
`travel_time_s`. No visibility term ranks the survivors — see
[How the gate decides](#how-the-gate-decides).

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

> **This page describes `8502e66`.** Two changes are in flight in the working
> tree and are *not* documented here, because they are uncommitted and carry no
> tests yet: (a) the `sight (path)` criterion becoming a substitute for a
> missing visibility model rather than for an unresolved sight line, so that an
> exit whose sign cannot be seen would face no sight test at all; and (b) the
> `visibility_extinction_threshold` rejection becoming additive-only. When they
> land, the sight table and the first two limitations below need rewriting.

Per agent, per reevaluation tick:

1. **Availability.** Each candidate route is tested twice. **Sight:** it is
   refused when its sighting distance falls below `sight_distance_fraction`
   (default 0.5) times the distance still to walk. **Dose:** it is refused when
   its projected FED exceeds `fed_rejection_threshold`. Either refusal alone
   removes the route.
2. **Ordering among survivors.** Travel time alone:
   `rank_cost = travel_time_s + w_queue * queue_time_s`.
3. **Tie-break.** Fewer hops.

**The visibility band does not order feasible routes.** It is computed and
reported as a diagnostic, and it still has two jobs — ordering the all-refused
fallback, and the anchor bypass — but it no longer sits ahead of time in the
main sort. It used to, and measurement showed it was not breaking ties but
deciding: on `l_corridor` it put agents on the 58 m route while both routes
read `k_ave = 0.000`, because a route carrying any trace of smoke gets a finite
`S = c / K` while a route with none got the unbounded band. A 5x distance
penalty never entered the comparison. Smoke now says which exits exist; it does
not also say which of the survivors is nearer.

Band index is `int(sighting_distance // band_width_m)`, **saturating at three
classes** (`_BAND_SATURATION_CLASSES`, 30 m at the default width). Anything
past the ceiling — including infinite sight in clear air — ties at band 3.
Sight is a discriminator while it is scarce; past a few tens of metres one
route seeing 91 m where another sees "unbounded" is not a difference anyone
acts on, and before the ceiling that difference was five orders of magnitude.
The unbounded `_MAX_BAND` survives only for the degenerate `band_width_m <= 0`.

In clear air `K = 0`, sighting distance is infinite, nothing is refused, and
the gate reduces to fastest-exit — which in clear air is nearest-exit. The two
models were measured identical on the `world_100` (7712 route-cost rows) and
`t_junction` (4030 rows) clear-air runs, and the `l_corridor` clear-air pair
evacuates 100/0 to the near exit under both with zero switches. Those runs
predate the band's removal from the ordering, and they were the check that
held only at `K = 0` exactly. The term that broke it at small nonzero `K` was
the band, which no longer orders feasible routes; equivalence at `K = 1e-4` has
not been re-measured since.

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
| `sight (path)` | `K_ave` over the route polyline, length-weighted across segments | `sight_distance_fraction` x the whole remaining route length | fallback, when no sight line resolves |

**Both criteria now average `K`; neither takes its worst point.** The `path`
criterion used the route's worst sample until `cea33ce`. A maximum over sampled
cells is a step function of where the agent stands: one dense cell entering the
sample swings the estimate by an order of magnitude between ticks, and measured
on `world100` the same 28.9 m route reported 91 m of sight, then 8 m, then 91 m
again on consecutive seconds, with the ordering flipping each time. Averaging
is also what FDS+Evac's `See_door` does. `k_max_route` is still computed and
reported, and still decides the all-refused fallback's switch margin, where the
question is which walk is survivable rather than which is legible.

`los` is FDS+Evac's `See_door` quantity (evac.f90:15343), so the test reduces to
a statement about optical depth along one leg. Note the borrowing is partial:
`S > 0.5 x d` is FDS+Evac's *last-resort* door criterion (evac.f90:16456), not
its primary one, which is the absolute `K_ave < ABS(FED_DOOR_CRIT)` = 0.03 /m
(evac.f90:1459, :5262). pyFDS-Evac has no absolute door criterion. See
[model-comparison.md](model-comparison.md#the-smoke-criteria-on-a-door). `path`
remains the harsher test, but now only through its *distance*: it compares
against the full remaining route length, however far the route bends, so it
penalises long routes. It is used only where there is no sight line to read —
an exit with no sign descriptor, a concealed one, one the agent is standing
behind, or a cache that holds no distances.

The rejection reason records which fired, for example:

```
sight (los) 8.8 m < 10.9 m (0.5 x 21.8 m)
sight (path) 2.1 m < 29.0 m (0.5 x 58.0 m)
```

so a route-cost CSV can be filtered on the criterion. **The parenthetical is
not the whole threshold on a rival exit.** For any exit other than the one the
agent is walking to, the requirement carries an extra `sight_return_margin`
factor (below) that the printed `fraction x distance` does not show, so the
quoted product falls short of the number to its left.

### Switching onto a rival needs more sight than staying

`sight_return_margin` (default 1.25) is an asymmetric deadband on the sight
gate, mirroring `fed_return_margin` on dose. The route the agent is already
walking is judged against the bare criterion; a rival exit must clear it by
that factor before the agent will switch onto it:

```
needed = sight_distance_fraction * distance          (current exit)
needed = sight_distance_fraction * distance * 1.25   (any other exit)
```

Without the deadband a route whose sight sits near the threshold toggles in and
out of feasibility every tick and the agent follows it. Measured on `world100`
before the fix, one exit swung between 2.9 m and 24.2 m of sight on consecutive
seconds, producing 169 returns to abandoned exits across 23 agents. The margin
is uncalibrated — see [limitations](#known-limitations).

### Dose vetoes an exit; it does not rank

FED enters route choice as a veto only. Each route's `fed_max_route` is the
dose already taken plus the dose predicted over the walk
(`current_fed + sum(fed_growth)`), and a route above `fed_rejection_threshold`
(default 1.0, incapacitation) is refused. Refusal is asymmetric in the same way
as sight: the current exit is held to the bare threshold so an agent flees a
lethal door at once, while a rival must come in under
`fed_rejection_threshold * fed_return_margin` (0.9). A dose refusal is a
"must flee" rejection, so it bypasses the exit-switch anchor — hysteresis
cannot pin an agent to a door that will kill it.

Surviving routes are then ordered by time. Dose never makes one exit outrank
another; it only removes exits. `tests/test_route_gate.py::TestDoseVetoesAnExit`
covers all three parts in clear air, so the sight gate cannot be the cause.

**This is FDS+Evac's other branch, and we run both halves at once.** In
`evac.f90` (`Change_Target_Door`, :16439-:16467) the sign of `FED_DOOR_CRIT`
selects between a dose criterion and the sight criterion — they are
alternatives, not layers — and the default of `-100.0` (:1459) selects the
sight branch that this model implements. Two differences are worth knowing:

- FDS+Evac's chosen quantity both strikes a door out (`L2_tmp >= 1.0` marks it
  not visible) **and** ranks the survivors (`L2_tmp < L2_min` picks the door).
  Here both dose and sight only strike out, and travel time ranks.
- pyFDS-Evac applies dose and sight together rather than choosing one.

**On the fires we have measured, the dose veto never fires.** On `l_corridor`'s
`fire_1MW_west` run the largest `fed_max_route` over 3498 route-cost rows is
0.0016, against a threshold of 1.0, and `world100` is reported the same way. On
these fires the gate is wayfinding, not hazard avoidance, and every refusal
that changes an exit comes from the sight criterion.

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
against 1.8 m. This is the one place the band still orders routes, and with the
band now saturating at three classes it orders them more coarsely than before:
every refused route with 30 m or more of sight ties, and distance decides.

### Churn protection

Three mechanisms hold an agent on its exit, and they are not enough.

**The exit-switch anchor.** A different exit is adopted only when its rank cost
beats `old_cost * exit_switch_anchor` (default 0.9). One gate-specific bypass
applies: a rival is adopted outright when it is `feasible`, a whole band
clearer, **and** clearer by a real margin in metres —
`rival.min_visibility_m * exit_switch_anchor > current.min_visibility_m`. The
feasibility requirement stops refused routes jumping the anchor, which made
agents ping-pong as bands healed and re-broke. The metres requirement was added
in `cea33ce`: a band is a quantised sighting distance, and a quantiser with no
hysteresis oscillates, so sight jittering either side of a band edge flipped
the order every tick — and because the bypass skips the anchor, every flip was
an actual switch.

**The two deadbands.** `sight_return_margin` (1.25) and `fed_return_margin`
(0.9) make a rival exit harder to qualify than the current one, so a route
sitting on either threshold cannot toggle the agent back and forth.

**Monotonicity is still violated.** The requirement is that an agent never
returns to an exit it has abandoned. Measured on `world100`, `cea33ce` took
223 switches and 182 returns across 26 agents down to 59 switches and **38
returns across 12 agents**. Better, not solved. Anyone reading a `world100`
route history should expect returns in it.

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
| `sight_return_margin` | `1.25` | Factor a *rival* exit's sight requirement is multiplied by, so switching needs more sight than staying. | active | inert |
| `sign_contrast_c` | `3.0` | Jin's `c` in `S = c / K`. 3 reflective, 8 internally illuminated. | active | inert |
| `band_width_m` | `10.0` | Width of a visibility band, in metres of sighting distance; bands saturate at 3 classes. Bands order the all-refused fallback and gate the anchor bypass — they do **not** order feasible routes. | active | inert |
| `anticipate` | `true` | Price each segment at the agent's arrival time. | active | **active** |
| `foresight_horizon_s` | `inf` | Cap on how far ahead anticipation reaches, in seconds. | active | **active** |
| `fallback_switch_margin` | `0.2` | Hysteresis when every route is refused. | active | inert |
| `w_smoke` | `1.0` | Smoke weight. Multiplies `K_ave` in the composite **and in the Dijkstra edge weights** — see limitations. | partly active | active |
| `w_fed` | `10.0` | FED weight. Same: composite **and** Dijkstra edge weights. | partly active | active |
| `w_queue` | `0.0` | Congestion weight, off by default. | active (as `w_queue * queue_time_s` on the rank cost) | active (as distance-equivalent in the composite) |
| `fed_rejection_threshold` | `1.0` | Projected FED above which a route is refused. Veto only: dose never ranks. | active | active |
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
- **There are three smoke gates, not one.** Besides the sight criterion,
  `visibility_extinction_threshold` (0.5 /m, per segment) and
  `impassable_extinction_threshold` (3.0 /m, route average, bypasses the
  anchor) both still run under the gate. They were meant to be additive-model
  machinery.
- **Anticipation samples the field too early.** Segments are priced at
  `now + walked_so_far / base_speed_m_per_s`, the *unimpeded* speed, while an
  agent in smoke walks at as little as `min_speed_factor` = 0.1 of it. The
  clock therefore runs ahead of the agent systematically, and it runs furthest
  ahead exactly where the smoke is thickest. With `foresight_horizon_s = inf`
  the agent also has perfect foresight of the FDS solution.
- **Five hysteresis constants, none calibrated.** `exit_switch_anchor` (0.9),
  `fallback_switch_margin` (0.2), `fed_return_margin` (0.9),
  `sight_return_margin` (1.25) and `_PATH_IMPROVEMENT_THRESHOLD` (10 %) are all
  chosen to stop measured churn, not fitted to observed behaviour. They do not
  yet stop it: 38 returns to abandoned exits across 12 agents remain on
  `world100`.
- **Clear-air equivalence is verified at `K = 0`, not at `K = 1e-4`.** The band
  that caused the divergence no longer orders feasible routes, but the check
  has not been re-run at small nonzero `K`.
- **`cost_model` is an unvalidated free string.** A typo silently yields the
  additive model.
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

The table is the run made at `b3babc0`, before the band left the ordering. The
84/16 split was re-measured after `cea33ce` and reported unchanged, now
produced by the sight gate alone; that re-run is not in the folder above, so
take the attribution from the commit message rather than from a CSV.

**Read the headline with its caveat.** Counted directly from `f_gate_costs.csv`
(3498 rows, the `b3babc0` run), the refusals break down as:

| refusal | near exit | far exit |
|---|---|---|
| `sight (path)` | 200 | 1020 |
| `fallback: sight (path)` | 12 | 25 |
| `fallback: sight (los)` | 130 | 0 |

So in that run the `path` criterion did the work, and it refused the *near* exit
200 times as well as the far one — the split is not a one-sided refusal of the
long way round. The `los` criterion appears there only under a `fallback:`
prefix, i.e. in ticks where every route was already refused. That matters
before anyone calibrates `sight_distance_fraction`.
`RESULTS.md` in the folder above states that all 1220 `path` refusals were on
the far exit; the CSV says 1020, and this table supersedes it.

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
