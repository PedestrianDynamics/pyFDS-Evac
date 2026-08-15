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

**Precondition.** `_gate_needs_sight` (`pyfds_evac/core/run_config.py`) builds a
visibility model for *any* deck that runs with rerouting enabled and
`cost_model` left at `"gate"`, including decks whose agents are all
`familiarity: 1.0`. That costs a vismap precompute at startup. Pass
`--vis-cache PATH` to make it a one-off: the cache is written if missing and
loaded if present.

Since `b16e900` the model is no longer what the gate reads: the sight criterion
is computed from the route polyline and needs no vismap. What the model still
supplies is the line-of-sight diagnostic and the sign legibility the cognitive
map expands on. Its own docstring has not caught up with that, and neither has
the trigger — `_gate_needs_sight` keys on `cost_model == "gate"`, which no longer
implies a vismap is needed.

## How the gate decides

> **This page describes `45e146f`.**

Per agent, per reevaluation tick:

1. **Availability.** Each candidate route is tested twice. **Sight:** it is
   refused when its sighting distance falls below `sight_distance_fraction`
   (default 0.5) times the distance still to walk. **Dose:** it is refused when
   its projected FED exceeds `fed_rejection_threshold`. Either refusal alone
   removes the route. Every candidate faces the same sight test; none is
   exempt.
2. **Ordering among survivors.** Travel time alone:
   `rank_cost = travel_time_s + w_queue * queue_time_s`. With
   `clean_extinction_threshold > 0` a clean-exit tier sits ahead of time — see
   [The clean-exit tier](#the-clean-exit-tier-off-by-default), which is off by
   default.
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

### Sighting distance, and the one estimator that measures it

Sighting distance is Jin's relation

```
S = c / K
```

with `c = sign_contrast_c` (default 3, light-reflecting signage; 8 is the value
for internally illuminated signs). It is deliberately uncapped, so `K = 0`
gives infinite sight.

Every candidate is judged on the same quantity: `K` is `K_ave` over that
route's own polyline, length-weighted across its segments, and the distance it
is compared against is the whole remaining route length. Because the estimator
uses the mean, the criterion `c / K_ave >= f * L` rearranges to a statement
about optical depth,

```
K_ave * L <= c / f          (= 2c at the default f = 0.5)
```

which is the same statement fdsvismap's line of sight makes along its own path.
The polyline is the estimator available for *every* exit, which is why it is
the one that gates.

**The estimator averages `K`; it does not take the route's worst point.** The
criterion used the worst sample until `cea33ce`. A maximum over sampled cells
is a step function of where the agent stands: one dense cell entering the
sample swings the estimate by an order of magnitude between ticks, and measured
on `world100` the same 28.9 m route reported 91 m of sight, then 8 m, then 91 m
again on consecutive seconds, with the ordering flipping each time. Averaging
is what FDS+Evac's `See_door` does too. `k_max_route` is still computed and
reported, and still decides the all-refused fallback's switch margin, where the
question is which walk is survivable rather than which is legible.

**The line of sight is a diagnostic, not a gate.** fdsvismap's obstruction-aware
sight line to an exit's own sign is the more faithful measurement, and it is
still read and reported, but it is defined only where a sign resolves — so
selecting the criterion per exit let sign geometry decide *which exits were
tested at all*. Measured before `b16e900`: on `l_corridor` the far exit lies
around two corners, never resolved a sight line, was therefore never sight-
tested, and the diversion the gate exists to produce vanished (84/16 became
100/0). On `world100` one exit was sight-tested 43 times and fell back 2095
times, so moving a sign two metres would have changed which exits were gated.
Mixing the two was worse still: the same 22 m route read 9.9 m on one tick and
68.3 m on the next as the sight line resolved. Not seeing a sign is a fact
about wayfinding, not about whether a route can be walked, so it belongs in the
cognitive map (`cognitive_map.expand_from_visibility`), not in this gate.

The rejection reason therefore always names the `path` criterion, for example:

```
sight (path) 2.1 m < 29.0 m (0.5 x 58.0 m)
sight (path) 6.8 m < 8.4 m (0.5 x 13.4 m x 1.25)
```

**The parenthetical shows the whole threshold.** For any exit other than the one
the agent is walking to, the requirement carries an extra `sight_return_margin`
factor (below), and the string names it — reading `(0.5 x 13.4 m)` on a rival
and finding `0.5 x 13.4 = 6.7` had led a reviewer to conclude the deadband had
produced a result it had not.

**The borrowing from FDS+Evac is partial, and it is from the last resort.**
`S > 0.5 x d` is FDS+Evac's tier-4 door criterion (`evac.f90:16456`), reached
only once no smoke-free door is available. Its *primary* rule is an absolute
one: minimise time among doors satisfying `K_ave_Door < ABS(FED_DOOR_CRIT)`
= 0.03 /m (`evac.f90:16265`, `:16272`; `FED_DOOR_CRIT = -100` becomes `3.0/100`
at `:5262`, Jin's `S = 3/K` at 100 m). pyFDS-Evac ships that absolute criterion
as the opt-in clean-exit tier below. See
[model-comparison.md](model-comparison.md#the-smoke-criteria-on-a-door).

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

### The clean-exit tier (off by default)

`clean_extinction_threshold` adds one rank above time. A route whose smokiest
*leg* stays at or below the threshold is `clean`, and clean routes outrank smoky
ones outright however far they are; among routes of the same tier, time decides.
The sort key is `(rejected, tier, rank_cost, hops)`.

This is FDS+Evac's primary door rule (`evac.f90:16265`, `:16272`), and its
threshold is not a new constant: `FED_DOOR_CRIT = -100` becomes `3.0/100` =
0.03 /m at `:5262`, which is Jin's `S = 3/K` at a 100 m sighting distance. Two
differences from the reference implementation are worth stating:

- **FDS+Evac's tier 1 is a hard filter.** `IF (T_tmp < L2_min .AND. L2_tmp <
  ABS(FED_DOOR_CRIT))` only ever selects a *qualifying* door; when no door
  qualifies the tier picks nothing and the search falls to the next tier of
  doors. Falling through to plain time ranking when our tier is empty is
  pyFDS-Evac's choice, not FDS+Evac's.
- **Membership is measured on the smokiest leg, each leg its own mean.** The
  route mean would dilute a smoky stretch with whatever clear corridor follows,
  so a long route could qualify by being long — the mirror of the length
  penalty the gate exists to remove. The worst *sample* is the step function
  that made sighting distances jump between ticks. FDS+Evac applies its 0.03 to
  `K_ave_Door`, a per-door average, for the same reason — though note that
  `K_ave_Door` is a mean along a bee-line sight line (`See_door`,
  `evac.f90:16149`), not a maximum over legs.

`clean_exit_margin` is hysteresis on membership for the exit the agent already
heads for: its limit is `clean_extinction_threshold / clean_exit_margin`.
FDS+Evac supplies the value — `FAC_DOOR_OLD = 0.1` (`evac.f90:1506`), applied as
`L2_tmp = FAC_DOOR_OLD * L2_tmp` for the current door (`:16255`), so the door an
agent already walks to stays smoke-free up to ten times the criterion.

The exit-switch anchor has a matching clause: a rival that is clean while the
current exit is not bypasses the anchor. Without it the tier could never change
an outcome, because clean implies about 100 m of sight while the visibility band
saturates at 30 m, so a clean route and one 3.3x smokier always share a band and
the band bypass never fires.

**It ships off (`clean_extinction_threshold = 0.0`, which means no route is ever
clean) because measurement refuted it.** On `l_corridor` over five seeds the
far-exit share was 15-22 with the tier against 15-17 without, identical on four
of the five; the prediction that motivated the tier was 25-40. The tier is not
inert — it is non-empty on 52 % of decision ticks and changes the ordering on
41 % — but the effect is churn rather than redirection: agents flip toward the
clean exit and back before reaching the junction. Median RSET rises 17 %
(71.2 s to 83.7 s) and monotonicity goes from 0 returns to an abandoned exit to
34-38 agents per run.

The proposed mechanism is a threshold too sharp for the signal. Tick-to-tick
movement in a leg mean has median 0.0072 /m and p90 0.134 /m, against a
hysteresis band of 0.0075 /m — narrower than the median jump, 116 crossings per
run. The band is also one-sided: the incumbent is relaxed to 0.0375 /m while a
rival is admitted at the bare 0.03 /m. And because tier membership is binary, a
crossing does not reorder the list, it swaps which objective is in force, so the
target jumps. FDS+Evac can afford that because a door leaves an agent's known
set permanently; here nothing is remembered, by design.

**Read the refutation as provisional.** A band of 0.0075 /m is
`0.03 / 0.8 - 0.03`, so those runs were made at `clean_exit_margin = 0.8` — the
value `from_routing_params` still hands out, and the value the same commit
records as invented. At the 0.1 that `FAC_DOOR_OLD` supplies, the incumbent's
limit is 0.3 /m and the band is 0.27 /m: twice the p90 of the drift instead of
a third of the median, which is a different regime for exactly the quantity the
mechanism blames. The tier has not been measured at 0.1. Anyone re-opening this
should set the key explicitly and re-run before trusting either the numbers or
the explanation.

Turn it on for a deck that has a genuinely clean alternative to reach for, and
read the `clean` and `k_leg_max` columns of the route-cost CSV when you do.

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
selects between a dose criterion and a smoke criterion — they are alternatives,
not layers — and the default of `-100.0` (:1459) selects the smoke branch that
this model implements. Which smoke criterion depends on the tier: absolute
`K_ave_Door` in tier 1, the `0.5 x d` sight ratio in tier 4. Two further
differences are worth knowing:

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

Three mechanisms hold an agent on its exit.

**The exit-switch anchor.** A different exit is adopted only when its rank cost
beats `old_cost * exit_switch_anchor` (default 0.9). One gate-specific bypass
applies: a rival is adopted outright when it is `feasible`, clearer by a real
margin in metres — `rival.min_visibility_m * exit_switch_anchor >
current.min_visibility_m` — **and** either a whole band clearer or clean while
the current exit is not. The
feasibility requirement stops refused routes jumping the anchor, which made
agents ping-pong as bands healed and re-broke. The metres requirement was added
in `cea33ce`: a band is a quantised sighting distance, and a quantiser with no
hysteresis oscillates, so sight jittering either side of a band edge flipped
the order every tick — and because the bypass skips the anchor, every flip was
an actual switch.

A route the ordering promotes but the anchor refuses no longer hides the rest of
the list: candidates are tried in rank order and the first the anchor would
admit wins, stopping at the agent's own exit. Before `45e146f`, a promoted route
the anchor vetoed made the agent see nothing below it, so enabling the
clean-exit tier could *suppress* a switch the model made without it.

**The two deadbands.** `sight_return_margin` (1.25) and `fed_return_margin`
(0.9) make a rival exit harder to qualify than the current one, so a route
sitting on either threshold cannot toggle the agent back and forth.

**Monotonicity holds at `45e146f`.** The requirement is that an agent never
returns to an exit it has abandoned. `cea33ce` took `world100` from 223
switches and 182 returns across 26 agents down to 59 switches and 38 returns
across 12 agents; at `45e146f` both decks report **zero** returns —
`l_corridor` with 2 switches, `world100` with 5. Enabling the clean-exit tier
gives the violations back (34-38 agents per run on `l_corridor`), which is why
it is off.

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
| `clean_extinction_threshold` | `0.0` (off) | Extinction at or below which a route's smokiest leg makes the exit `clean`; clean exits outrank smoky ones. FDS+Evac's value is `0.03`. | active | inert |
| `clean_exit_margin` | `0.8` from JSON, `0.1` in the dataclass | Divides the threshold for the exit the agent already heads for. FDS+Evac's `FAC_DOOR_OLD` is 0.1. The two defaults disagree — see the note below the table. | active | inert |
| `sign_contrast_c` | `3.0` | Jin's `c` in `S = c / K`. 3 reflective, 8 internally illuminated. | active | inert |
| `band_width_m` | `10.0` | Width of a visibility band, in metres of sighting distance; bands saturate at 3 classes. Bands order the all-refused fallback and gate the anchor bypass — they do **not** order feasible routes. | active | inert |
| `anticipate` | `true` | Price each segment at the agent's arrival time. | active | **active** |
| `foresight_horizon_s` | `inf` | Cap on how far ahead anticipation reaches, in seconds. | active | **active** |
| `fallback_switch_margin` | `0.2` | Hysteresis when every route is refused. | active | inert |
| `w_smoke` | `1.0` | Smoke weight. Multiplies `K_ave` in the composite **and in the Dijkstra edge weights** — see limitations. | partly active | active |
| `w_fed` | `10.0` | FED weight. Same: composite **and** Dijkstra edge weights. | partly active | active |
| `w_queue` | `0.0` | Congestion weight, off by default. | active (as `w_queue * queue_time_s` on the rank cost) | active (as distance-equivalent in the composite) |
| `fed_rejection_threshold` | `1.0` | Projected FED above which a route is refused. Veto only: dose never ranks. | active | active |
| `visibility_extinction_threshold` | `0.5` | `K` above which a segment is flagged non-visible; a route whose segments are *all* non-visible is refused when some other route has a visible segment. | **inert** | active |
| `sampling_step_m` | `2.0` | Spacing of extinction samples along an edge polyline. | active | active |
| `base_speed_m_per_s` | `1.3` | Clear-air walking speed. Sets travel time, anticipation, and the queue conversion. It is not a speed floor; `min_speed_factor` is. | active | active |
| `alpha` | `0.706` | Lund speed-law coefficient. | active | active |
| `beta` | `-0.057` | Lund speed-law coefficient. | active | active |
| `min_speed_factor` | `0.1` | Floor on the smoke speed factor. | active | active |
| `default_exit_capacity` | `1.3` | Fallback exit capacity, agents/s, when the exit sets none. | active | active |

**`clean_exit_margin` has two different defaults.** `RouteCostConfig` declares
0.1, but `from_routing_params` — the path every scenario JSON takes — supplies
0.8 when the key is absent. A deck that enables the tier without naming the
margin therefore gets 0.8, i.e. a current-exit limit of `threshold / 0.8`,
1.25x, not the 10x that `FAC_DOOR_OLD` intends. The commit that set the
dataclass to 0.1 (`45e146f`) records 1.25x as measured far too narrow. Set the
key explicitly until the two agree.

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
- **The other two smoke thresholds are now additive-only machinery.**
  `visibility_extinction_threshold` (0.5 /m, per segment) is skipped under the
  gate, and `impassable_extinction_threshold` (3.0 /m) can no longer fire there
  either: it is reached only from a rejection reason containing "visible", and
  the gate emits no such reason. Both keys still take values under `"gate"` and
  do nothing.
- **Anticipation samples the field too early.** Segments are priced at
  `now + walked_so_far / base_speed_m_per_s`, the *unimpeded* speed, while an
  agent in smoke walks at as little as `min_speed_factor` = 0.1 of it. The
  clock therefore runs ahead of the agent systematically, and it runs furthest
  ahead exactly where the smoke is thickest. With `foresight_horizon_s = inf`
  the agent also has perfect foresight of the FDS solution.
- **Five hysteresis constants, none calibrated.** `exit_switch_anchor` (0.9),
  `fallback_switch_margin` (0.2), `fed_return_margin` (0.9),
  `sight_return_margin` (1.25) and `_PATH_IMPROVEMENT_THRESHOLD` (10 %) are all
  chosen to stop measured churn, not fitted to observed behaviour.
  `clean_exit_margin` is the one that is not invented: it is FDS+Evac's
  `FAC_DOOR_OLD`.
- **`_adoptable` is a laxer test than the anchor it stands in for.** The
  skip-past-a-refused-promotion loop tests only band, cleanliness and rank cost;
  the anchor itself also requires `feasible` and a margin in metres. Its
  docstring says to keep the two in step, and they are not.
- **Clear-air equivalence is verified at `K = 0`, not at `K = 1e-4`.** The band
  that caused the divergence no longer orders feasible routes, but the check
  has not been re-run at small nonzero `K`.
- **`cost_model` is an unvalidated free string.** A typo silently yields the
  additive model.
- **FIC does not participate in routing under either model.** It drives the
  Purser slowdown and incapacitation only. FIC and the sight gate are driven by
  the same smoke, so routing on both would double-count.

## Evidence

`assets/l_corridor` is the deck the model is judged on: a near exit reached by
passing the fire, and a clean way round. Since `a98f8bb` the spawn sits in the
middle of the vertical leg and the two routes are 26 m and 46 m, a 1.8x ratio;
before that it sat 3 m from the junction and they were 11 m and 58 m, 5.3x —
a spread wide enough that no smoke could justify the detour. Exit shares are
unchanged across the move at 84 / 16, with 4 switches and no agent returning to
an abandoned exit. **The numbers below predate the move**, so read their route
lengths against the old geometry. Results are in
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

At `45e146f` the reported state is `l_corridor` 84 near / 16 far with 2
switches and no returns to an abandoned exit, and `world100` E1 91 / E2 17 /
E3 12 with 5 switches and no returns. `a98f8bb` then moved the l_corridor spawn
and re-reported 84 / 16 with 4 switches, still no returns. The `world100` far
clean exit is used at all only since `b16e900`. These figures come from the
commit messages of `b16e900`, `45e146f` and `a98f8bb`; no CSV for them is in
the results folder.

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
before anyone calibrates `sight_distance_fraction`. The `los` criterion no
longer gates at all (`b16e900`), so a CSV taken at `45e146f` carries only
`sight (path)` rows.
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
