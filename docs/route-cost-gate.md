# The gate cost model

> Part of [pyFDS-Evac](../README.md). Reference for `routing.cost_model`.
> Provenance, review findings and the open questions live in
> [gate-model-review-notes.md](gate-model-review-notes.md); this page documents
> what the shipped code does.

Route choice runs under one of two cost models, selected per deck with
`routing.cost_model` in the scenario JSON:

| value | what decides the exit |
|---|---|
| `"gate"` (default) | Route optical depth decides which exits are *available* and orders the survivors; travel time breaks ties. |
| `"additive"` | Smoke is a toll per metre walked, folded into one composite cost. |

Under the gate one quantity does the whole of the smoke reasoning: the route's
optical depth `tau = K_ave * L`, the soot column the agent walks through. It
refuses a route, it orders the routes it does not refuse, and it weights every
Dijkstra edge — see [How the gate decides](#how-the-gate-decides).

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

To make the gate stricter or laxer, change `tau_max` — the optical depth a
route may carry before it is refused:

```json
{
  "routing": {
    "cost_model": "gate",
    "tau_max": 6.0,
    "tau_return_margin": 0.8,
    "current_exit_discount": 0.9
  }
}
```

**No vismap precondition.** The gate reads no visibility model. `b16e900`
unified the criterion on the route polyline and `89d13d4` removed the
`_gate_needs_sight` precompute that a gate deck used to trigger, so a
familiarity-1.0 gate deck now runs with no `--vis-cache` at all: `l_corridor`
takes 5 seconds and reproduces the cached run's 84/16. A visibility model is
still built for decks with discovery agents, which consult it to learn the
graph.

## How the gate decides

> **This page describes `9f55f6e`.**

Per agent, per reevaluation tick:

1. **Path per exit.** Dijkstra runs with each edge weighted by its own optical
   depth, `k_avg * length` (plus a `1e-6 * length` floor, below).
2. **Availability.** Each candidate route is tested twice. **Optical depth:**
   it is refused when `tau = K_ave * L_eff` exceeds `tau_max` (default 6), or
   `tau_max * tau_return_margin` if it is not the exit the agent already walks
   to. **Dose:** it is refused when its projected FED exceeds
   `fed_rejection_threshold`. Either refusal alone removes the route.
3. **Ordering among survivors.** Optical depth first, travel time second. The
   sort key is `(rejected, tier, tau, rank_cost, hops)` with
   `rank_cost = travel_time_s + w_queue * queue_time_s`. The `tau` in the key
   is scaled by `current_exit_discount` (0.9) for the exit the agent already
   heads for. `tier` is the clean-exit tier, off by default.

**One quantity refuses a route, orders it, and weights its edges.** That is the
change at `0d9bf79`. Before it, Dijkstra minimised the additive composite, the
survivors were ordered by travel time, and the gate judged them on optical
depth — three currencies, and a gate could refuse an exit on a smoky path while
a longer passable path to the same exit existed and was never offered.

**Optical depth can order routes where a visibility band could not**, because
`tau = K_ave * L` already contains the distance. Two routes through equally thin
haze order by length; in clear air every `tau` is zero and travel time decides
alone; a cleaner route wins only by carrying enough less smoke to pay for its
extra metres. A band compared cleanliness with no reference to how far the agent
had to carry it, which is why it had to be kept out of the main sort: on
`l_corridor` it put agents on the 58 m route while both routes read
`k_ave = 0.000`. `_visibility_band`, `_sighting_distance`, `band_width_m` and
the saturation constant are all gone at `0d9bf79`.

**The `1e-6 * length` floor on the edge weight is not a tuning constant.** In
clear air every `k_avg` is zero, so without it every path ties at weight zero
and Dijkstra returns an arbitrary one. The floor makes the tie break on length.
It is not configurable and has not been measured for its effect at small
nonzero `K`.

In clear air `K = 0`, every `tau` is zero, nothing is refused, and the gate
reduces to fastest-exit — which in clear air is nearest-exit. The two models
were measured identical on the `world_100` (7712 route-cost rows) and
`t_junction` (4030 rows) clear-air runs, and the `l_corridor` clear-air pair
evacuates 100/0 to the near exit under both with zero switches. **Those runs
predate `0d9bf79` entirely**, and the ordering has changed since. Equivalence
has not been re-measured under `tau` ordering, at `K = 0` or at `K = 1e-4`.

### Optical depth: what it measures, and what it does not

```
tau = K_ave * L_eff
```

`K_ave` is the length-weighted mean extinction over the route's own polyline;
`L_eff` is the distance still to walk. The product is the Beer-Lambert integral
of extinction along the walked path — the soot column the agent passes through.
It is an **exposure** statement.

**It is not a sighting distance.** The criterion grew out of one: `c / K_ave >=
0.5 * L` rearranges to `K_ave * L <= 2c`, and with Jin's `c = 3` that is
`tau <= 6`. But Jin's `S = c / K` is contrast along a straight, unobstructed
line to a sign. Integrating `K` around two corners measures how much smoke you
walk through, not how far you can see. The two coincide only on a straight
corridor. The names changed at `0d9bf79` to say what the quantity is.

**The estimator averages `K`; it does not take the route's worst point.** A
maximum over sampled cells is a step function of where the agent stands: one
dense cell entering the sample swings the estimate by an order of magnitude
between ticks, and measured on `world100` the same 28.9 m route reported 91 m of
sight, then 8 m, then 91 m again on consecutive seconds, with the ordering
flipping each time. `k_max_route` is still computed and reported, and still
decides the all-refused fallback's switch margin, where the question is which
walk is survivable rather than which is cleanest.

**The line of sight is a diagnostic, not a gate.** fdsvismap's obstruction-aware
sight line to an exit's own sign is the more faithful measurement of what an
occupant can see, but it is defined only where a sign resolves — so selecting
the criterion per exit let sign geometry decide *which exits were tested at
all*. Measured before `b16e900`: on `l_corridor` the far exit lies around two
corners, never resolved a sight line, was therefore never tested, and the
diversion the gate exists to produce vanished (84/16 became 100/0). On
`world100` one exit was tested by sight line 43 times and fell back 2095 times,
so moving a sign two metres would have changed which exits were gated. Mixing
the two was worse still: the same 22 m route read 9.9 m on one tick and 68.3 m
on the next as the sight line resolved. Not seeing a sign is a fact about
wayfinding, not about whether a route can be walked, so it belongs in the
cognitive map (`cognitive_map.expand_from_visibility`), not in this gate.

The rejection reason names the quantity and both factors of it:

```
tau 8.41 > 6.00 (K_ave 0.145 x 58.0 m)
tau 5.20 > 4.80 (K_ave 0.388 x 13.4 m)
```

The second is a rival exit, held to `tau_max * tau_return_margin` = 4.8.

**Where the 6 comes from.** FDS+Evac's tier-4 door test computes
`L2_tmp = d * 0.5 / (3.0 / K_ave_Door)` and strikes the door out when
`L2_tmp >= 1.0` (`evac.f90:16456-16462`). That expression is `K_ave * d / 6`, so
the test is exactly `tau > 6` with Jin's `c = 3`. The threshold is therefore
citable, but **the quantity it is applied to is not the same quantity**:
FDS+Evac's `K_ave_Door` is a mean along `See_door`'s straight sight line, and
for a door with no resolved sight line the distance is an L1 norm
(`evac.f90:16458-16459`); pyFDS-Evac averages `K` along the walked polyline.
Two further scope limits: the test lives in the tier-4 last-resort branch,
reached only once no smoke-free door is available and looping only over doors
that are already known or visible; and in FDS+Evac a struck-out door is struck
out *permanently* (`Is_Visible_Door(i) = .FALSE.`, `:16460-16461`), which
pyFDS-Evac deliberately does not do. So: the gate is *inspired by* FDS+Evac's
tier-4 visibility door rule and inherits its threshold with a citation; it does
not implement it. **`tau_max` has not been calibrated against a soot-dose or
FED-equivalent limit.** That is open work.

Under FDS+Evac's *primary* rule the criterion is different again — minimise time
among doors satisfying `K_ave_Door < ABS(FED_DOOR_CRIT)` = 0.03 /m
(`evac.f90:16265`, `:16272`; `FED_DOOR_CRIT = -100` becomes `3.0/100` at
`:5262`). pyFDS-Evac ships that absolute criterion as the opt-in clean-exit tier
below. See [model-comparison.md](model-comparison.md#the-smoke-criteria-on-a-door).

### Two asymmetries favour the exit the agent already walks to

`tau_return_margin` (default 0.8) is a deadband on **feasibility**. The current
route is judged against the bare `tau_max`; a rival must come in under
`tau_max * 0.8` before it is even a candidate:

```
budget = tau_max                        (current exit)
budget = tau_max * tau_return_margin    (any other exit)
```

Without it a route whose `tau` sits near the budget toggles in and out of the
feasible set every tick and the agent follows it. It replaces the old
`sight_return_margin`, which multiplied a sight requirement (1.25 *up*) where
this one scales a budget (0.8 *down*).

`current_exit_discount` (default 0.9) is a deadband on **ordering**. Only the
current exit's `tau` is discounted, and only in the sort key, so it holds its
place unless a rival is clearly cleaner rather than momentarily cleaner.

**Its provenance is FDS+Evac's `FAC_DOOR_OLD2 = 0.9`** (`evac.f90:1507`), which
is applied as `L2_tmp = FAC_DOOR_OLD2 * L2_tmp` to the current door at `:16290`
and `:16466` — and at `:16466` that `L2_tmp` is the `tau/6` of the tier-4 test,
i.e. the same quantity, discounted in the same place, inside the loop that
minimises it to pick a door. Note the shipped code comment in `route_graph.py`
instead cites `FAC_DOOR_WAIT` at `evac.f90:1503`; `FAC_DOOR_WAIT` is at `:1505`,
and it discounts the current door's *travel time* (`T_tmp`), not its smoke.

**A reviewer will ask why both.** They act on different stages — one on the
feasible set, one on the order within it — but they have not been measured
independently, and no run isolates the contribution of either.

### The clean-exit tier (off by default)

`clean_extinction_threshold` adds one rank above optical depth. A route whose
smokiest *leg* stays at or below the threshold is `clean`, and clean routes
outrank smoky ones outright however far they are; among routes of the same tier,
optical depth then time decides. The sort key is
`(rejected, tier, tau, rank_cost, hops)`.

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
current exit is not bypasses the anchor. It was added because the anchor's other
bypass, then keyed on the visibility band, could not fire between a clean route
and one 3.3x smokier — both saturated the band. That reasoning is now stale: the
bypass compares optical depth, which does discriminate there. The clause has not
been re-measured since, and the tier ships off anyway.

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
as optical depth: the current exit is held to the bare threshold so an agent
flees a lethal door at once, while a rival must come in under
`fed_rejection_threshold * fed_return_margin` (0.9). A dose refusal is a
"must flee" rejection, so it bypasses the exit-switch anchor — hysteresis
cannot pin an agent to a door that will kill it.

Surviving routes are then ordered by optical depth and time. Dose never makes
one exit outrank another; it only removes exits.
`tests/test_route_gate.py::TestDoseVetoesAnExit` covers all three parts in clear
air, so the smoke gate cannot be the cause.

**This is FDS+Evac's other branch, and we run both halves at once.** In
`evac.f90` (`Change_Target_Door`, :16439-:16467) the sign of `FED_DOOR_CRIT`
selects between a dose criterion and a smoke criterion — they are alternatives,
not layers — and the default of `-100.0` (:1459) selects the smoke branch that
this model implements. Which smoke criterion depends on the tier: absolute
`K_ave_Door` in tier 1, the `0.5 x d` sight ratio in tier 4. Two further
differences are worth knowing:

- FDS+Evac's chosen quantity both strikes a door out (`L2_tmp >= 1.0` marks it
  not visible) **and** ranks the survivors (`L2_tmp < L2_min` picks the door).
  Since `0d9bf79` pyFDS-Evac's optical depth does the same — it refuses and it
  ranks. Dose still only strikes out.
- pyFDS-Evac applies dose and optical depth together rather than choosing one.

**On the fires we have measured, the dose veto never fires.** On `l_corridor`'s
`fire_1MW_west` run the largest `fed_max_route` over 3498 route-cost rows is
0.0016, against a threshold of 1.0, and `world100` is reported the same way. On
these fires the model is **exposure-gated wayfinding, not hazard avoidance**:
every refusal that changes an exit comes from the optical-depth criterion, and
nothing in the run is near a tenability limit.

### Refusals are not remembered

The criterion is measured against the distance *still to walk*, so it relaxes
as the agent closes in: smoke that refuses a door at 40 m accepts it at 2 m.
Every tick re-decides from the current field; there is no permanent exit death.

### When every route is refused

The agent still has to move. `rank_routes` re-sorts the refused routes by
`(tau_route, rank_cost)` — least smoke to walk through, then quickest — and
un-rejects the head with a `fallback:` prefix on its reason. The agent keeps its
current target unless a rival's worst extinction is better by more than
`fallback_switch_margin` (default 0.2), i.e. unless

```
rival.k_max_route <= current.k_max_route * (1 - fallback_switch_margin)
```

The fallback sort uses the **undiscounted** `tau_route`;
`current_exit_discount` applies to the feasible ordering only, and the
`fallback_switch_margin` on `k_max_route` is the hysteresis here instead.
Ordering refused routes by `k_max` alone once put a 51 m route ahead of a 22 m
one on 2.0 m of sight against 1.8 m — two tenths of a metre of visibility,
neither usable, deciding a 29 m detour. `tau` carries the distance with it, so
the least-bad walk is the one with least smoke to walk through.

### Churn protection

Three mechanisms hold an agent on its exit.

**The exit-switch anchor.** A different exit is adopted only when its rank cost
beats `old_cost * exit_switch_anchor` (default 0.9). Note that `rank_cost` is a
**travel time**, so the anchor compares time while the ordering compares optical
depth — see [limitations](#known-limitations). One gate-specific bypass applies:
a rival is adopted outright when it is `feasible` **and** either clean while the
current exit is not, or cleaner in relative *and* absolute terms:

```
candidate.tau_route < current.tau_route * exit_switch_anchor
and current.tau_route - candidate.tau_route > tau_max * 0.1
```

The absolute term matters because the ratio alone fires on noise: `tau` 0.02
against 0.03 is a 33 % improvement and no difference at all to anyone walking
it. Measured on `l_corridor`, the ratio on its own produced 109 returns to
abandoned exits; adding the floor took that to 51. The `0.1` multiplier is
hard-coded, not configurable.

A route the ordering promotes but the anchor refuses no longer hides the rest of
the list: candidates are tried in rank order and the first the anchor would
admit wins, stopping at the agent's own exit.

**The deadbands.** `tau_return_margin` (0.8) and `fed_return_margin` (0.9) make
a rival exit harder to *qualify* than the current one;
`current_exit_discount` (0.9) makes it harder to *outrank* it.

**Monotonicity holds on `world100` and does not on `l_corridor`.** The
requirement is that an agent never returns to an exit it has abandoned. At
`0d9bf79` and `9f55f6e`:

| deck | before (`4ce4ac7`) | at `0d9bf79` | at `9f55f6e` |
|---|---|---|---|
| `world100`, far clean exit E3 | 12 agents | **39 agents**, 9 switches, **0 returns** | unchanged |
| `l_corridor`, returns to abandoned exits | **0** | 51 across 20 agents | 34 across 14 agents |
| `l_corridor`, switches | 4 | 74 | 55 |
| `l_corridor`, far-exit share | ~18 | ~18 | ~18 |

The `world100` result is what the model was asked for — prefer a clean exit even
when far — and no earlier version of the gate produced it. **`l_corridor`
regressed**, from no returns to 34, and the far-exit share did not move to pay
for it. Both figures come from the commit messages of `0d9bf79` and `9f55f6e`;
no CSV for them is in the results folder.

Enabling the clean-exit tier gives further violations back (34-38 agents per run
on `l_corridor`, measured before `0d9bf79`), which is why it is off.

**Two attempts that made it worse, recorded so they are not repeated.**

- *Making `tau` the anchor's currency* — replacing the `rank_cost` ratio test
  with a `tau` ratio test — took `l_corridor` from 51 returns to **90**. `tau`
  is zero in clear air, so every ratio test degenerates to `0 < 0` and the
  anchor stops discriminating. This is also why `rank_cost` stays a time: a
  `tau` anchor would let no agent switch in clear air, and a congestion weight
  would count for nothing exactly where decks calibrate one.
- *An absolute floor on the bypass* — the `tau_max * 0.1` term above — took 109
  returns to 51. It helped; it did not close the problem.

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
    "tau_max": 6.0
  }
}
```

| JSON key | Default | Effect | Under `"gate"` | Under `"additive"` |
|---|---|---|---|---|
| `cost_model` | `"gate"` | Selects the model. Unvalidated: any other string behaves as `"additive"`. | — | — |
| `tau_max` | `6.0` | Optical depth `K_ave * L` a route may carry before it is refused. Also orders the feasible routes. | active | inert |
| `tau_return_margin` | `0.8` | Factor a *rival* exit's budget is multiplied by, so switching needs a cleaner route than staying. | active | inert |
| `current_exit_discount` | `0.9` | Factor the current exit's `tau` is scaled by in the sort key. FDS+Evac's `FAC_DOOR_OLD2` is 0.9. | active | inert |
| `clean_extinction_threshold` | `0.0` (off) | Extinction at or below which a route's smokiest leg makes the exit `clean`; clean exits outrank smoky ones. FDS+Evac's value is `0.03`. | active | inert |
| `clean_exit_margin` | `0.1` | Divides the threshold for the exit the agent already heads for. FDS+Evac's `FAC_DOOR_OLD` is 0.1. | active | inert |
| `anticipate` | `true` | Price each segment at the agent's arrival time. | active | **active** |
| `foresight_horizon_s` | `inf` | Cap on how far ahead anticipation reaches, in seconds. | active | **active** |
| `fallback_switch_margin` | `0.2` | Hysteresis when every route is refused. | active | inert |
| `w_smoke` | `1.0` | Smoke weight in the additive composite and its Dijkstra edge weights. Since `0d9bf79` the gate weights edges by their own `tau`, so neither weight reaches route choice under the gate; the composite is still reported. | **inert** (reported only) | active |
| `w_fed` | `10.0` | FED weight. Same. | **inert** (reported only) | active |
| `w_queue` | `0.0` | Congestion weight, off by default. | active (as `w_queue * queue_time_s` on the rank cost) | active (as distance-equivalent in the composite) |
| `fed_rejection_threshold` | `1.0` | Projected FED above which a route is refused. Veto only: dose never ranks. | active | active |
| `visibility_extinction_threshold` | `0.5` | `K` above which a segment is flagged non-visible; a route whose segments are *all* non-visible is refused when some other route has a visible segment. | **inert** | active |
| `sampling_step_m` | `2.0` | Spacing of extinction samples along an edge polyline. | active | active |
| `base_speed_m_per_s` | `1.3` | Clear-air walking speed. Sets travel time, anticipation, and the queue conversion. It is not a speed floor; `min_speed_factor` is. | active | active |
| `alpha` | `0.706` | Lund speed-law coefficient. | active | active |
| `beta` | `-0.057` | Lund speed-law coefficient. | active | active |
| `min_speed_factor` | `0.1` | Floor on the smoke speed factor. | active | active |
| `default_exit_capacity` | `1.3` | Fallback exit capacity, agents/s, when the exit sets none. | active | active |

`clean_exit_margin` had two disagreeing defaults — 0.1 in the dataclass, 0.8
from `from_routing_params` — until `9508181` made both 0.1, the value
`FAC_DOOR_OLD` supplies. The clean-tier measurements below were made at 0.8 and
have not been repeated at 0.1.

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

- **The ordering is in optical depth and the anchor is in time.** This is the
  open defect. `rank_routes` orders by `tau`; `_anchor_allows` compares
  `rank_cost`, a travel time. The two can disagree, and an agent then oscillates
  between what each prefers. That is the mechanism behind `l_corridor`'s 34
  returns. The two constants damping it — `exit_switch_anchor` and
  `current_exit_discount` — are both 0.9, which in FDS+Evac is
  `FAC_DOOR_WAIT` on time and `FAC_DOOR_OLD2` on smoke; here they were arrived
  at separately. Closing this properly means the anchor and the ordering
  agreeing by construction, not by two constants that coincide.
- **The `1e-6 * length` edge-weight floor is a hard-coded tiebreaker.** It
  decides path choice in clear air, where every `k_avg * length` is zero. Its
  effect at small nonzero `K` has not been measured.
- **`tau_max = 6` is uncalibrated as an exposure budget.** The threshold is
  citable from FDS+Evac's tier-4 rule, but that rule applies it to a straight
  sight line, not to a walked route, and nothing here checks 6 against a
  soot-dose or FED-equivalent limit.
- **`impassable_extinction_threshold` is dead code under the default model.**
  `_must_flee_rejection` fires only on a rejection reason starting `FED` or
  containing `"visible"`; the gate's only reason string starts `tau`. So no
  smoke rejection bypasses the exit-switch anchor, at any density, and the key
  still takes a value and does nothing. `visibility_extinction_threshold`
  (0.5 /m, per segment) is likewise skipped under the gate. The FED bypass
  survives, and on the fires measured here FED never reaches its threshold, so
  in practice **nothing bypasses the anchor**.
- **Anticipation samples the field too early.** Segments are priced at
  `now + walked_so_far / base_speed_m_per_s`, the *unimpeded* speed, while an
  agent in smoke walks at as little as `min_speed_factor` = 0.1 of it. The
  clock therefore runs ahead of the agent systematically, and it runs furthest
  ahead exactly where the smoke is thickest. With `foresight_horizon_s = inf`
  the agent also has perfect foresight of the FDS solution.
- **Six hysteresis constants, none calibrated.** `exit_switch_anchor` (0.9),
  `fallback_switch_margin` (0.2), `fed_return_margin` (0.9),
  `tau_return_margin` (0.8), the hard-coded `tau_max * 0.1` bypass floor, and
  `_PATH_IMPROVEMENT_THRESHOLD` (10 %) are all chosen to stop measured churn,
  not fitted to observed behaviour. Two have FDS+Evac values behind them:
  `clean_exit_margin` = `FAC_DOOR_OLD`, and `current_exit_discount` =
  `FAC_DOOR_OLD2`. Neither was fitted here either.
- **Clear-air equivalence has not been re-measured since `0d9bf79`.** The gate
  now orders by `tau` and weights edges by `tau`; the last equivalence runs
  predate both. In clear air every `tau` is zero and the argument still holds by
  construction, but it is an argument, not a measurement.
- **`cost_model` is an unvalidated free string.** A typo silently yields the
  additive model.
- **FIC does not participate in routing under either model.** It drives the
  Purser slowdown and incapacitation only. FIC and the optical-depth gate are
  driven by the same smoke, so routing on both would double-count.

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
84/16 split was re-measured after `cea33ce` and reported unchanged; that re-run
is not in the folder above, so take the attribution from the commit message
rather than from a CSV.

At `45e146f` the reported state is `l_corridor` 84 near / 16 far with 2
switches and no returns to an abandoned exit, and `world100` E1 91 / E2 17 /
E3 12 with 5 switches and no returns. `a98f8bb` then moved the l_corridor spawn
and re-reported 84 / 16 with 4 switches, still no returns. The `world100` far
clean exit is used at all only since `b16e900`. These figures come from the
commit messages of `b16e900`, `45e146f` and `a98f8bb`; no CSV for them is in
the results folder.

**Since `0d9bf79` these are history.** Ranking on optical depth moved
`world100`'s far clean exit from 12 agents to 39, and moved `l_corridor` from no
returns to an abandoned exit to 51, then 34 at `9f55f6e`, with the far-exit
share unchanged at about 18. See
[Churn protection](#churn-protection) for the full table. No archived result set
exists for either; both come from the commit messages.

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
prefix, i.e. in ticks where every route was already refused. That matters before
anyone calibrates `tau_max`. The `los` criterion no longer gates at all
(`b16e900`), and the reason strings are `tau ...` since `0d9bf79`, so a current
CSV carries neither label.

**The route-cost CSV columns changed at `0d9bf79`.** `min_visibility_m` and
`band` are gone; `tau_route` replaces both. Any analysis script reading the old
columns needs updating.

`assets/t_junction` is **not** a route-choice benchmark. Its 2 MW PVC fire
drives route `K` to about 10.7 /m, so every route on it carries an optical depth
far above any plausible budget and all of them are refused. Keep it as a
lethality and speed-collapse case.

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
