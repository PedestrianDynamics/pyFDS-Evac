---
title: "Model comparison: FDS+Evac vs pyFDS-Evac"
linkTitle: "FDS+Evac comparison"
weight: 13
aliases: [/docs/model-comparison/]
---

> This document compares the evacuation models in [FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source) (v2.6.0,
> Korhonen 2021) and pyFDS-Evac as implemented in this repository.
> Claims are referenced to the FDS+Evac Technical Reference and User's
> Guide [1] and to the pyFDS-Evac source code.  Where the two systems
> differ, the differences are stated precisely; where they agree, that
> is noted too.
>
> Line numbers of the form `evac.f90:NNNN` refer to the `evac.f90`
> source at FDS commit c9da70d7a (`FDS6.7.6-404-gc9da70d7a`), the copy
> in `materials/`, which is the FDS 6.7.6 / Evac 2.6.0 version that [1]
> documents.  The guide's title page shows `FDS6.7.6-404-gc9da70d7a`;
> its body text names `FDS6.7.6-336-gf2e836c15`, whose `evac.f90` equals
> the `FDS6.7.6` tag's.  This copy differs from the tag only by the
> `HR_SPEED`/`TPRE` initialisation (:11023–11024) and one `EVALUATE_RAMP`
> call (:13256), with no behaviour change.

---

## 1. Movement model

| Aspect | FDS+Evac | pyFDS-Evac |
|--------|----------|------------|
| **Locomotion model** | Social Force Model (Helbing et al. [6], three-circle body shape [1] Table 1), continuous 2-D equation of motion solved with a modified velocity-Verlet integrator ([1] §3.1–3.2, §3.6) | JuPedSim collision-free speed model (operational model configured externally); no social forces |
| **Body shape** | Three overlapping circles (torso Rd, shoulder Rs, head Rt) with rotational degree of freedom ([1] Table 1, Fig. 1) | Point agent (circle of configurable radius in JuPedSim) |
| **Counterflow** | Dedicated counterflow collision-avoidance algorithm ([1] §3.3) | Handled by JuPedSim's operational model; no separate counterflow algorithm |
| **Spatial discretisation** | Rectilinear evacuation mesh (separate from the FDS fire mesh); geometry is fitted to the underlying grid; minimum ~0.25 m cell size recommended ([1] §1.2) | Continuous walkable polygon (Shapely geometry); no grid |

**References:** [1] §3.1–3.2 (agent model), §3.3 (counterflow), §3.6 (numerical method).

---

## 2. Exit / route selection

This is the area of largest conceptual difference.

### FDS+Evac

Exit selection is formulated as an **N-player game** where each agent
minimises its own **estimated evacuation time** by choosing among
available exits [8].  The model is based on the concept of
*best-response dynamics*: each agent periodically updates its exit
choice by selecting the exit that minimises its estimated evacuation
time, given the current choices of all other agents.

#### Cost function

The estimated evacuation time of agent *i* through exit *e_k* is
([8] Eq. 6):

```
T_i(e_k, s_{-i}; r) = beta_k * lambda_i(e_k, s_{-i}; r) + tau_i(e_k; r_i)
```

where:
- `beta_k` is a capacity parameter for exit *k* (seconds per agent)
- `lambda_i` is the number of other agents heading to exit *e_k*
  who are closer to it than agent *i* ([8] Eq. 7)
- `tau_i = d(e_k; r_i) / v_i^0` is the walking time ([8] Eq. 8); in
  this section `tau` is Ehtamo's notation for a time, unrelated to the
  optical depth `tau` used for pyFDS-Evac below

The term `beta_k * lambda_i` estimates the queueing delay; `tau_i`
estimates the walking time.  Thus `T_i` = queueing time + walking
time.

In the FDS+Evac implementation ([1] §3.6 p35–36), this is computed
as:

```
T = alpha * t_walk + (1 - alpha) * t_queue
```

where `t_walk = distance / v0`, `t_queue = N_queue /
(FAC_DOOR_QUEUE * Width)`, and `alpha` is `FAC_DOOR_ALPHA`.
Distance is L2 (Euclidean) for visible exits and L1 (Manhattan) for
non-visible exits.  The currently chosen exit is favoured by 10%
(anchoring parameter) to prevent oscillation.

#### Nash equilibrium and convergence

Ehtamo et al. [8] prove that this game has a **Nash equilibrium in
pure strategies** (Theorem 3.1) when all agents have the same walking
speed.  The NE is a fixed point of the system of all agents'
best-response functions.  The existence proof is constructive: agents
can be fixed to their equilibrium strategies one by one, in
ascending order of their evacuation times.

Three decentralised algorithms are analysed for finding the NE:
1. **Parallel Update Algorithm (PUA)**: all agents update
   simultaneously; converges in at most N iterations ([8] Theorem 4.1)
2. **Round Robin Algorithm (RRA)**: agents update one at a time in
   sequence; converges in at most N² iterations ([8] Theorem 4.2).
   **FDS+Evac uses RRA** ([8] §6 p127).
3. **Random Polling Algorithm (RPA)**: agents update stochastically.

In practice, RRA converges in ~3–4 iteration rounds regardless of
parameter values, while PUA can oscillate and require 10–18 rounds
([8] §6, Figs. 1–4).  The initial assignment at simulation start
iterates until door-target counts stabilise (evac.f90:6995).

Numerical experiments in [8] show that using the exit selection
game (vs. nearest-exit) reduces total evacuation time by ~29%
(Fig. 6).

#### Preference ordering

Exits are additionally filtered by a **preference order** (Table 3
in [1], Table 1 in [8]) determined by three Boolean criteria:
visibility (`vis`), familiarity (`fam`), and disturbing conditions
(`con`).  The best-response is constrained to the highest-priority
non-empty group ([8] Eq. 31):

```
s_i = BR_i(s_{-i}; r) = arg min T_i(s'_i, s_{-i}; r)
                          s.t. s'_i in E_i(z_bar)
```

where `E_i(z_bar)` is the set of exits in the best available
preference group for agent *i*.

Four agent types modulate which exits enter the feasible set:
conservative, active, herding, follower ([1] §3.5.1–3.5.4).
Herding and follower agents incorporate social information from
neighbours to expand their feasible exit set.

#### Hawk-dove game extension

A separate **hawk-dove game** (Heliövaara et al. [9]) is available
as an optional overlay (`C_HAWK >= 0`, default off: `C_HAWK = -2.0`,
evac.f90:1589).  When enabled, agents near an exit play a
hawk-dove game against nearby neighbours to decide whether to push
aggressively (hawk) or yield (dove).  This modulates *behaviour at
congestion points*, not the exit-selection cost function itself.

#### The smoke criteria on a door

FDS+Evac's *primary* smoke test on a door is **absolute**: a door
counts as smoke-free while `K_ave < ABS(FED_DOOR_CRIT)`.  The input is
a visibility in metres (`FED_DOOR_CRIT = -100.0`, evac.f90:1524) which
is converted to an extinction coefficient by Jin's relation,
`FED_DOOR_CRIT = 3.0 / FED_DOOR_CRIT` (evac.f90:5496) — so the default
is 0.03 /m.  `K_ave_Door` is assigned from `See_door` at evac.f90:16497,
and the tier-1 test that reads it is at evac.f90:16601 and :16608.  Among
the doors that pass, the agent minimises the time `T` above.

**That test is a hard filter.**  `IF (T_tmp < L2_min .AND. L2_tmp <
ABS(FED_DOOR_CRIT))` sets the chosen door `i_tmp` only for a door that
qualifies; when none qualifies the tier selects nothing and the search
moves to the next tier of doors, not to a time-only ranking.  pyFDS-Evac's
clean-exit tier falls through to the plain optical-depth ranking when it
is empty, which is our construction and not FDS+Evac's.  The
distance-relative rule — "check that visibility > 0.5 * distance to the
door" — is FDS+Evac's **tier-4 last resort** (evac.f90:16792-16799), reached
only when no smoke-free door exists.
That rule reads `K_ave` along the straight, occlusion-blocked bee line
(`See_door`, evac.f90:15682), so `S > 0.5 * d` is a statement about
optical depth along one real sight line.

Written out, the tier-4 test is
`L2_tmp = d * 0.5 / (3.0 / K_ave_Door)` struck out at `L2_tmp >= 1.0`
(evac.f90:16794, :16799) — that is `K_ave * d / 6 >= 1`, i.e. an optical
depth above 6, which is where pyFDS-Evac's `tau_max = 6` comes from.
Two scope limits on the citation: the loop runs only over doors already
known or visible, and the strike-out (`Is_Visible_Door(i) = .FALSE.`,
`Is_Known_Door(i) = .FALSE.`, :16800-16801) lasts for **one call** of
`Change_Target_Door` only: both arrays are reset at the start of every
call (:16170-16171).  What persists is a mark in the agent's
known-door list, `Human_Known_Doors%I_nodes`, and its effect is weak.
The mark is written in the tier-1 loop (:16613-16638) only for the
agent's previous target door, only while that door is still known and
visible at that call (:16559), only for a lone agent
(`HR%GROUP_ID < 0`), only if the door already has an entry in the
agent's known-door list filled at initialisation (:16230, :16279-16293;
the loop at :16632-16640 rewrites entries but never adds one), and only when `FAC_DOOR_OLD * K_ave >= 0.03 /m`
(:16628), i.e. `K_ave >= 0.3 /m` with `FAC_DOOR_OLD = 0.1` (:1571)
under the default negative `FED_DOOR_CRIT`.  The entry becomes negative
("some smoke") or 0 ("too much smoke", when `0.9 * K_ave * d / 6 >= 1`,
:16634-16637), and it is never set positive again.  What the mark does
depends on its value and on the call:

- *Negative entry.*  In the periodic re-evaluation (`imode = 1`) the
  door is forced unknown (:16533, :16542).  In the calls made on a floor
  or mesh change (`imode = 2`, from `CHECK_TARGET_NODE`, :12961) that
  override is skipped, and the `ABS` at :16188 and :16198 counts the
  door as known.
- *Zero entry.*  It matches no door, because `ABS(0)` never equals
  `n_egrids+N_ENTRYS+i` (:16540); so the override at :16541-16542 never
  fires for it, and the door is never made non-visible by memory.  It
  simply drops out of the list, so it is not known from memory on any
  later call, but it becomes known again if it is the current, visible
  target (:16535) or has `KNOWN_DOOR` = .TRUE. (:16185, :16195).

So in the periodic re-evaluation the "too much smoke" door is forgotten
less firmly than the "some smoke" one.  That the zero branch does not act as its comments intend
is our inference from the code, not a documented behaviour.
pyFDS-Evac inherits the threshold, applies it to the walked polyline
rather than the bee line, and remembers nothing.

Inside that tier, **dose and sight are alternatives, not layers**: the
sign of `FED_DOOR_CRIT` picks the branch (evac.f90:16775-16803).
Positive, and the door is scored by the dose the agent would arrive
with (`IntDose + FED_max_Door * distance / Speed`); negative — the
default `-100.0` — and it is scored by the visibility rule above.
Either way the resulting `L2_tmp` does **two** jobs: `L2_tmp >= 1.0`
strikes the door out ("too much smoke"), and `L2_tmp < L2_min` picks
the winner among those left.  The criterion vetoes *and* ranks, with
`FAC_DOOR_OLD2 = 0.9` favouring the door already targeted.

pyFDS-Evac splits those jobs differently.  Dose vetoes only: a route above
`fed_rejection_threshold` is removed and dose never makes one exit outrank
another.  Optical depth does both, as in tier 4 — it refuses a route above
`tau_max` *and* orders the survivors, with travel time breaking ties.  It also
applies dose and smoke at once rather than choosing one by a sign.

#### Where the quantity is used: the decisive difference

The threshold `tau > 6` is borrowed from tier 4 with a citation.  **The place
the quantity is used is not**, and that is what changes the behaviour.

In FDS+Evac's first three tiers the rank is `T_tmp` — a time in tier 1 when
`FAC_DOOR_QUEUE` is active, a plain L2 or L1 distance norm otherwise — while
`K_ave_Door` appears only as a boolean admission test:

```fortran
IF (T_tmp < L2_min .AND. L2_tmp < ABS(FED_DOOR_CRIT)) THEN   ! :16601, :16690, :16737
```

A change in the smoke field can move a door between tiers or out of the admitted
set, but it cannot reorder the doors inside a tier — and geometry does not
reorder itself.  Smoke enters the ordering only in the **tier-4 last resort**
(`IF (L2_tmp < L2_min)`, `:16803`), reached once no smoke-free door is available,
looping only over doors already known or visible, scoring a bee-line or L1
distance, and striking a refused door out for that call only (`:16799-16801`;
the arrays are reset at `:16170-16171`).

pyFDS-Evac promotes that last-resort ranking criterion to its primary one, over
all candidates, at every tick, on the walked polyline, and drops the reference's
one lasting smoke memory, a weak mark on a lone agent's previous target once its
`K_ave` reaches 0.3 /m (`:16628-16637`; see [The smoke criteria on a door](#the-smoke-criteria-on-a-door)).  Measured consequence on
`assets/l_corridor`: this model diverts **18 of 100** agents to the longer,
cleaner route, where the reference criterion — distance ranking, both doors
clearing the 0.03 /m admission test until the smoke is well developed — would
send essentially everyone to the near exit, roughly 100/0.  **That 100/0 is a
prediction reasoned from `evac.f90`, not a measured run of FDS+Evac**; the
deck's own additive model is the nearest empirical proxy and does evacuate
100/0.  The diversion is a deliberate departure, and stands or falls on its own
merits.  See
[route-cost-gate.md](route-cost-gate.md#the-diversion-is-a-departure-from-fdsevac-not-a-reproduction-of-it)
for the accompanying `L/d` geometric bias (1.41 near against 1.27 far on that
deck).

### pyFDS-Evac

Route selection uses a **stage graph** (directed weighted graph of
distributions, checkpoints, and exits) with **Dijkstra shortest-path**
queries ([docs/routing.md](routing.md), `route_graph.py`).

At each reevaluation tick, per-edge costs are computed from current
smoke and FED fields.  The weight depends on the cost model
(`route_graph.py:1299-1310`):

```
gate      edge_cost = k_avg * length_m + 1e-6 * length_m
additive  edge_cost = length_m * (1 + w_smoke * k_avg) + w_fed * fed_growth
```

Under the gate the edge weight is the segment's optical depth, with a
length floor that keeps a clear-air graph from collapsing to all-zero
weights; under `"additive"` it is the composite decomposed per segment.
Dijkstra then finds one cheapest path per reachable exit using these
dynamic weights.

The routes it returns are then judged by one of two models
([docs/route-cost-gate.md](route-cost-gate.md)):

- **`"gate"` (default).** Route optical depth `tau = K_ave * L`
  (dimensionless; `L` is the distance still to walk) decides
  availability *and* the ordering.  Here `tau` is always optical
  depth, not the relaxation time τ of FDS+Evac's movement model.  A route is refused when `tau`
  exceeds `tau_max` (6), or `tau_max * tau_return_margin` (4.8) for an
  exit the agent is not already walking to; survivors are ordered by
  `tau`, with travel time (plus `w_queue` x queue time) breaking ties.
  `K_ave` is the length-weighted mean over the route's own polyline, so
  `tau` is the soot column the agent walks through — an exposure
  statement, not a sighting distance.  Dijkstra weights each edge by its
  own `tau`, so path choice and exit choice are one objective.  Sign
  legibility is not consulted in route choice; it decides only which
  exits enter the agent's cognitive map.  An opt-in tier above `tau`
  reproduces FDS+Evac's absolute criterion
  (`clean_extinction_threshold`, default 0, off).
- **`"additive"`.** The composite
  `path_length * (1 + w_smoke * K_ave) + w_fed * FED_max`.

Under both, routes are rejected if FED exceeds a threshold, and a
fallback un-rejection ensures agents always have a path.  The
all-segments-non-visible rejection runs under `"additive"` only.

**The borrowing is partial and should be read as such.** pyFDS-Evac
takes FDS+Evac's *last-resort* criterion as the primary criterion of
its `"gate"` cost model.  The
absolute `K_ave < 0.03 /m` test exists as an opt-in tier that ships
off, because measured on two decks it produced churn rather than
redirection — see
[route-cost-gate.md](route-cost-gate.md#the-clean-exit-tier-off-by-default).
The distance-relative
form is the point of the choice — the same haze is usable 5 m from an
exit and not at 40 m — but it is not what FDS+Evac reaches for first.

There is **no** preference ordering, no agent types
(conservative/active/herding/follower), and no game-theoretic
component.  Familiarity is modelled, but as a per-agent cognitive map
that restricts the graph before routing, not as a per-exit preference
group.  Per-exit familiarity is not supported
([#136](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/136)).

| Aspect | FDS+Evac | pyFDS-Evac |
|--------|----------|------------|
| **Algorithm** | N-player best-response game (NE in pure strategies) with preference-order filter [8] | Dijkstra shortest-path with dynamic edge weights, then a per-route check under the selected cost model |
| **Cost function** | `T_i = beta_k * lambda_i + tau_i` (queueing + walking time) [8] Eq. 6 | gate: route optical depth `K_ave * L`, with travel time (+ `w_queue` x queue time) as tie-break; additive: `length * (1 + w_smoke * K) + w_fed * FED` |
| **Smoke test on a door** | Absolute `K_ave < 0.03 /m` (`FED_DOOR_CRIT`, evac.f90:1524, :5496, :16497); the `0.5 x d` visibility rule is the tier-4 last resort (:16799), where `L2_tmp = d * 0.5 / (3/K_ave) >= 1` is exactly `K_ave * d > 6` | Optical depth `K_ave * L <= 6`, the same threshold, but applied to the walked polyline rather than a straight sight line; x 0.8 budget for a rival exit; no absolute `K` door criterion. It vetoes *and* ranks |
| **Congestion** | Modelled: queueing time depends on count of closer agents heading to same exit | Optional (`w_queue`), off by default; a global tally of agents targeting the exit |
| **Familiarity** | Per-agent per-exit familiarity (user-configurable, constrains feasible exit set) | Per-agent cognitive map: an agent can only route over stages it knows or has discovered. The restriction is on *topology* only — smoke is sampled globally, so a discovery agent's route choice is not perception-limited ([#125](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/125)). Per-exit familiarity is not supported ([#136](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/136)) |
| **Social behaviour** | Herding and follower agent types observe neighbours | Not modelled |
| **Smoke in cost** | Admission only in tiers 1–3 (`K_ave_Door < 0.03 /m`, the rank stays `T_tmp`); smoke ranks doors only in the tier-4 last resort (`:16803`), over known-or-visible doors, with a strike-out that lasts one call; the only lasting memory is a weak mark on a lone agent's previous target once `K_ave >= 0.3 /m` (:16628-16637), which acts weakly: a "some smoke" mark forces the door unknown only in the periodic re-evaluation, and a "too much smoke" mark only drops it from the list | gate: availability *and* ordering, both on route optical depth, for every candidate at every tick and with no memory; additive: continuous weighted term |
| **FED in cost** | Not in cost function by default (`FED_DOOR_CRIT < 0`); only used for incapacitation at FED >= 1.0 | Veto threshold under both models; a ranking term (`w_fed * FED_max`) under additive only |
| **Distance metric** | L2 for visible exits, L1 (Manhattan) for non-visible exits; direct agent-to-exit | Polyline arc length along corridor geometry (via JuPedSim RoutingEngine); routes through intermediate stages |
| **Anticipation** | `FED_max_Door * dist / Speed`: extrapolation from presently observable conditions | `anticipate` prices each segment at the agent's arrival time from the FDS solution itself — an upper bound on foresight, not FDS+Evac's model |
| **Equilibrium** | Proven NE existence; RRA converges in ~3–4 rounds [8] | No equilibrium concept; each agent independently picks the cheapest Dijkstra path |
| **Anchoring** | Current door favoured by 10 %: `FAC_DOOR_WAIT` = 0.9 on the time criterion (:1570, applied :16600), `FAC_DOOR_OLD2` = 0.9 on the smoke criterion (:1572, applied :16626, :16803) | `exit_switch_anchor` = 0.9 on travel time, mirroring `FAC_DOOR_WAIT`; `current_exit_discount` = 0.9 on the current exit's optical depth in the sort, mirroring `FAC_DOOR_OLD2`; bypasses for a lethal current exit and (gate) a feasible rival clearer by more than the symmetric deadband `tau_deadband * tau_max` (0.6), which also refuses a rival dirtier by that much; plus deadbands of 0.9 on dose and 0.8 on the optical-depth budget |
| **Rerouting frequency** | ~1 Hz (every second on average, `TAU_CHANGE_DOOR = 1.0`, evac.f90:1531) | Configurable interval, staggered per agent |

---

## 3. Smoke–speed interaction

Both systems use the same underlying correlation from the Frantzich
& Nilsson experiments (Lund 2003, Report 3126 [3]).

### Speed reduction formula

```
speed_factor(K) = 1 + (beta / alpha) * K
```

with the Frantzich–Nilsson coefficients; the published values are on
[Walking speed in smoke](/fundamentals/walking-speed.md) and the code defaults
on the [smoke-speed model](/models/smoke-speed.md#parameters) page.

| Aspect | FDS+Evac | pyFDS-Evac |
|--------|----------|------------|
| **Speed formula** | `c(Ks) = 1 + beta * Ks / alpha` ([1] §3.4 Eq. 11) | Same formula (`smoke_speed.py:234`) |
| **Default alpha/beta** | Frantzich–Nilsson values (evac.f90:1544–1545) | Same values (`smoke_speed.py:95–96`); see the [smoke-speed model](/models/smoke-speed.md#parameters) |
| **Minimum speed** | `SMOKE_MIN_SPEED_FACTOR` (default 0.1, evac.f90:2154) as a factor of *v*0, or `SMOKE_MIN_SPEED`, which the code treats as a speed in m/s (`SMOKE_MIN_SPEED/HR%SPEED`, :8516) although the guide calls it a factor ([1] §8.7 p. 81). The visibility-based cutoff (`SMOKE_MIN_SPEED_VISIBILITY`, :8529–8536) is marked obsolete in the source ("obsolote feature ... it is not used if default SMOKE_MIN_SPEED_VISIBILITY is given", :8529-8530) and is inactive by default: the default 0.0 is clamped to 0.01 m, so it would act only above K = 300 /m (:1528, :2160-2161) | Configurable `min_speed_factor` (default 0.1) |
| **Smoke input** | Soot density from FDS mesh converted to extinction via `K = MASS_EXTINCTION_COEFF * SOOT_DENS * 1e-6` (evac.f90:8522–8523) | Extinction coefficient K read directly from FDS `SOOT EXTINCTION COEFFICIENT` slice via fdsreader |
| **Sampling geometry** | Local value at agent position on the evacuation mesh, at `HUMAN_SMOKE_HEIGHT` above the floor (default 1.6 m, evac.f90:1138; [1] §8.7 p. 81; [7] p. 61) | Local value at agent position: nearest value position of the extinction slice closest to `--smoke-slice-height` (default 1.6 m as in FDS+Evac, 2.0 m before; an absolute z in the FDS domain, not a height above the floor). For FDS's default node-centred slices this is the nearest node, a value FDS averages from the surrounding cells; for `CELL_CENTERED=T` slices it is the nearest cell centre (see [FDS slice sampling](fds-sampling.md)). Gas FED is read from the first slice of each species, whatever its height ([#150](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/150)) |

**Key difference:** Both systems apply the speed reduction using the
*local* smoke at the agent's position.  FDS+Evac converts the soot
density at runtime from the cell-centred value of the fire cell that
contains the centre of the agent's evacuation-grid cell (evac.f90:6337,
:16078); pyFDS-Evac reads the extinction coefficient from the nearest
value position of an FDS slice at a fixed height, which for FDS's
default node-centred slices is a node value averaged over the
surrounding cells.  The path-averaged extinction coefficient, which Börger et al.
(2024) [2] take along the line of sight to a sign and pyFDS-Evac takes
along the walked polyline, is used in pyFDS-Evac for route cost only,
not for walking speed.

---

## 4. Toxicity / FED model

### FDS+Evac

FED is computed using Purser's Fractional Effective Dose concept [4].
The default calculation uses **CO, CO2, and O2** gas phase
concentrations ([1] §1.2 p11, §2.7 p19).  The effects of additional
gases (NO, NO2, CN, HCl, HBr, HF, SO2, C3H4O, CH2O) are included
**only if the user provides the corresponding FDS species** ([1] §1.2
p11).  By default, HCN and HCl effects are **not** modelled; only the
CO2 hyperventilation factor is included ([1] §2.7 p19).

The FED function itself is in FDS's `PHYSICAL_FUNCTIONS` module (the
`FED` function imported at evac.f90:65), not in evac.f90 directly.  Its
HCN term subtracts NO + NO2 with the offset 0.00454545, about 1/220 (FDS 6.7.6
`func.f90`), not the NO2 alone of [1] Eq. 15; it has done so since
firemodels/fds 694e033 (2011), and earlier versions had no HCN term
([#159](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/159)).

FED activity level is an input: 1 (at rest), 2 (light work,
default), 3 (heavy work) (evac.f90:1530).  In this version it has no
effect on the dose: `GET_FIRE_CONDITIONS` evaluates `FED` at all three
levels and only the light-work value is kept (evac.f90:16086-16088).

Incapacitation occurs at FED >= 1.0 ([1] §3.4 p31).

### pyFDS-Evac

FED is computed with the Purser equations as written out in the
FDS+Evac guide [1] (`fed.py`), except the HCN term, which is computed as
the FDS code computes it (#159), from up to 12 gas species: CO, CO2,
O2, HCN, NO, NO2, HCl, HBr, HF, SO2, acrolein and formaldehyde.
This is not the ISO 13571 [5] form: ISO 13571 keeps irritants in a
separate fractional effective concentration (FEC) and does not add
them into the FED, whereas here an irritant lethal-dose term is summed
into the FED total.  With `--enable-fic-speed` (off by default, as
FDS+Evac has no such rule), irritants also slow agents through Purser's
fractional irritant concentration (FIC). ISO 13571's FEC is a related
but different quantity, with its own denominators.  The full model is:

```
FED_tot = (FED_CO + FED_CN + FED_NOx + FLD_irr) * HV_CO2 + FED_O2
```

where:
- `FED_CO`: CO narcosis (Eq. 13 from guide)
- `FED_CN`: HCN − (NO + NO2) (protective effect of NOx on HCN toxicity), as FDS computes it (#159)
- `FED_NOx`: NO + NO2 (Ct product = 1500 ppm·min)
- `FLD_irr`: irritant gases (HCl, HBr, HF, SO2, NO2, acrolein, formaldehyde)
- `HV_CO2`: CO2 hyperventilation factor
- `FED_O2`: O2 vitiation

Required FDS slices: CO, CO2, O2.
Optional slices: HCN, NO, NO2, HCl, HBr, HF, SO2, acrolein,
formaldehyde.

When only CO/CO2/O2 are available, the model falls back to the
three-gas subset: every optional species defaults to zero concentration in
`DefaultFedInputs` (`fed.py`), so an absent slice contributes nothing.

| Aspect | FDS+Evac | pyFDS-Evac |
|--------|----------|------------|
| **FED standard** | Purser's FED concept [4] | Purser equations as in the FDS+Evac guide, with irritants summed into FED (not the ISO 13571 split into FED and FEC) |
| **Default gases** | CO, CO2, O2 | CO, CO2, O2 (same three-gas minimum) |
| **Optional gases** | NO, NO2, CN, HCl, HBr, HF, SO2, C3H4O, CH2O (user must provide species) | HCN, NO, NO2, HCl, HBr, HF, SO2, acrolein, formaldehyde (auto-detected from FDS slices) |
| **HCN/HCl by default** | Not modelled unless user provides species ([1] §2.7 p19) | Not modelled unless FDS slices are present |
| **Incapacitation** | FED >= 1.0, agent stops (v0 = 0) ([1] §3.4 p31) | Agent stops (desired speed 0) and remains as a static obstacle. Per-agent threshold, log-normal with median 1.0 by default, or 1.0 for every agent in deterministic mode. The convective heat FED is a separate running total; crossing either threshold incapacitates |
| **Activity level** | Input accepted; no effect in 6.7.6, the dose is always light work (`evac.f90:16086–16088`) | Not supported ([#135](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/135)); the CO term uses the light-work coefficient ([FED model](/models/fed.md#coded-form)) |
| **FED in routing** | Not used in exit selection cost by default (`FED_DOOR_CRIT < 0`); only used for incapacitation | A veto under both cost models; additionally a ranking term (`w_fed * FED_max`) under `"additive"` only, not under the default gate |
| **Temperature/radiation** | Not implemented for agent effects ([1] §1.2 p11) | Convective heat FED (SFPE Handbook Eq. 63.44) from an FDS `TEMPERATURE` slice, tracked separately from the gas FED; it does not affect route choice or speed. Radiant heat is not modelled |

---

## 5. FDS data integration

| Aspect | FDS+Evac | pyFDS-Evac |
|--------|----------|------------|
| **Coupling** | Tightly coupled: evacuation module is compiled into FDS and runs as subroutines within the same executable ([1] §2.1) | Loosely coupled: reads pre-computed FDS output files via fdsreader; runs as a separate post-processing step |
| **Smoke data** | Direct access to soot density on the FDS computational grid at runtime | Reads FDS slice files (SOOT EXTINCTION COEFFICIENT, gas species volume fractions) |
| **Visibility check** | Bee-line visibility from agent to exit; checks if smoke along the line exceeds a user-defined threshold ([1] §3.5 p32, §3.6 p36) | Sign legibility on a precomputed visibility grid (smoke-aware fdsvismap with `--fds-dir` and `--vis-cache`, clear air otherwise); it decides which exits enter the agent's cognitive map, not whether a route is admitted. Route cost separately uses the mean of K along the walked edge polylines; Börger et al. (2024) [2] average K along the line of sight to a sign, and applying the average to a walked path is a pyFDS-Evac extension |
| **Temporal resolution** | Smoke, gas and FED fields are copied from the fire meshes to the evacuation meshes every `DT_SAVE` = 2 s (evac.f90:7187), not every FDS time step; the agents move on their own time step in between | Reads FDS output at whatever temporal resolution is available in the slice files |

---

## 6. Exit flow / throughput

| Aspect | FDS+Evac | pyFDS-Evac |
|--------|----------|------------|
| **Flow model** | Emergent from social-force dynamics; door width × specific flow (default 1.3 1/m/s) used for queueing time estimation ([1] §3.6 p36) | JuPedSim collision-free model produces emergent flow; optional per-checkpoint throughput throttling (`enable_throughput_throttling`, `max_throughput` in scenario config) |
| **Agent update order** | Agents are updated in sequence within each evacuation mesh; order can affect results ([1] §3.6) | JuPedSim handles agent updates internally |

---

## 7. Geometry representation

| Aspect | FDS+Evac | pyFDS-Evac |
|--------|----------|------------|
| **Domain** | 2-D rectilinear evacuation meshes; obstacles conform to grid ([1] §1.2) | Continuous walkable polygon (Shapely); arbitrary geometry |
| **Multi-floor** | Separate evacuation meshes per floor connected by DOOR/ENTR/CORR/STRS namelists ([1] §1.2, §8.11–8.15) | Single floor only; multi-floor buildings are not supported |
| **Stairs** | Dedicated staircase models (CORR, EVSS, STRS) with speed reduction factors ([1] §1.2 p13) | Not implemented |
| **Doors** | Explicit DOOR and EXIT namelists with width, flow fields, opening/closing times ([1] §8.10–8.12) | Stages (distributions, checkpoints, exits) in the stage graph |

---

## 8. Advantages and disadvantages

### FDS+Evac

**Advantages:**

- **Congestion-aware routing with theoretical guarantees.**  The
  game-theoretic exit-selection model accounts for queueing at exits.
  The NE existence proof [8] guarantees a consistent solution, and
  the RRA converges in a few rounds.  This means agents
  self-organise to balance load across exits — shown to reduce total
  evacuation time by ~29% versus nearest-exit [8] Fig. 6.

- **Rich behavioural model.**  Four agent types
  (conservative/active/herding/follower) with per-agent exit
  familiarity and visibility model a heterogeneous population.  The
  preference-order system captures the well-documented tendency to
  prefer familiar exits over unfamiliar ones, even when the familiar
  route is longer [8] §5.2, [1] §3.5.

- **Tight FDS coupling.**  Running inside the FDS executable gives
  access to the fire-simulation fields without slice-file I/O.  The
  fields are copied to the evacuation meshes every `DT_SAVE` = 2 s
  (evac.f90:7187), not every FDS time step.

- **Social Force Model with counterflow.**  The three-circle body
  shape and social-force locomotion produce realistic crowd dynamics
  including pushing, lane formation, and counterflow effects ([1]
  §3.2–3.3).

- **Documented testing.**  The guide reports component tests based on
  the IMO test cases ([1] §4.2), sensitivity analyses ([1] Ch. 5), and
  comparisons with test data and with other evacuation models ([1]
  Ch. 6).

**Disadvantages:**

- **Smoke does not enter the cost function continuously.**  Fire
  conditions affect exit selection only through the binary
  preference-order filter (disturbing conditions yes/no) and
  visibility checks.  A heavily smoke-filled route and a lightly
  smoke-filled route receive the same cost if both are in the same
  preference group.  The cost function T_i has no continuous
  extinction or FED term.

- **No path-integrated smoke assessment.**  Visibility is checked
  along a bee line from agent to exit ([1] §3.6 p36).  Smoke
  conditions along the actual walking path (which may follow
  corridors around obstacles) are not sampled.

- **FED does not influence routing by default.**  FED is accumulated
  per agent and triggers incapacitation at FED >= 1.0, but with the
  default `FED_DOOR_CRIT < 0` projected FED along
  candidate routes is not used to steer agents away from toxic paths
  before incapacitation occurs.

- **Rectilinear mesh constraint.**  Geometry is fitted to a
  rectangular grid; obstacles snap to cell boundaries.  Minimum
  corridor width ~0.7 m.  Fine geometric details (angled walls,
  curved corridors) require very fine meshes ([1] §1.2, §2.7).

- **Distance metric approximation.**  L1 (Manhattan) distance is
  used for non-visible exits as an approximation of walking distance
  ([1] §3.5.1 p33).  This can over- or under-estimate actual
  corridor-following paths.

- **Single-threaded evacuation.**  The evacuation calculation runs
  as a single thread even when FDS uses MPI parallelism ([1] §1.2
  p12).  This limits scalability for large agent populations.

- **FDS version lock-in.**  The evacuation module is compiled into
  FDS.  Updating the movement model or routing algorithm requires
  modifying and recompiling the FDS Fortran source.

### pyFDS-Evac

**Advantages:**

- **Two explicit route-choice models, switchable per deck.**
  `"additive"` keeps smoke and projected FED as continuous, weighted
  terms in the per-edge cost Dijkstra minimises: a toll per metre plus
  `w_fed * FED`.  `"gate"` (default) weights each edge by its own
  optical depth, refuses a route whose optical depth exceeds `tau_max`
  or whose projected FED exceeds the veto threshold, and orders the
  survivors by optical depth, with travel time breaking ties.  The gate
  exists because in the additive form both terms scale with route
  length, so a long clean detour can never win.
  Being able to run the same deck under both is itself the
  comparison instrument — see
  [docs/route-cost-gate.md](route-cost-gate.md).

- **Path-integrated extinction sampling for route cost.**  For route
  cost, smoke is sampled along corridor-following polylines (JuPedSim
  RoutingEngine waypoints) and averaged along the path.  Börger et al. [2]
  average K along the line of sight to a sign; averaging it along a walked
  path is a pyFDS-Evac extension.  This captures spatially varying smoke
  along the actual walking path, not just along a straight line.

- **Continuous geometry.**  Walkable areas are arbitrary polygons
  (Shapely).  No grid snapping, no minimum corridor width imposed by
  cell size.

- **Decoupled from FDS.**  Reads FDS output via fdsreader.  Can be
  used with any FDS version, any fire simulator that produces
  compatible output, or even with synthetic hazard fields.  The
  movement model (JuPedSim) and routing logic (Python) can be
  updated independently.

- **FED-aware route rejection.**  Routes with projected FED above a
  threshold are rejected before the agent commits to them.  This is
  proactive (avoid lethal routes) rather than reactive (incapacitate
  after exposure).

- **Modular and extensible.**  Python codebase with clear separation
  between routing (`route_graph.py`), FED (`fed.py`), smoke-speed
  (`smoke_speed.py`), and scenario orchestration (`scenario.py`).

**Disadvantages:**

- **Congestion modelling is opt-in and scale-dependent.**  A queueing
  term exists (`w_queue`) but is **off by default**: it is driven by a
  global tally of every agent targeting an exit, so no constant is
  right at more than one crowd size.  With it off, agents
  independently pick the cheapest path without considering how many
  others are heading to the same exit — exactly the overcrowding the
  game-theoretic model in FDS+Evac was designed to solve.  See
  [docs/routing.md](routing.md#why-it-is-opt-in-and-what-0024-means).

- **No equilibrium concept.**  Without agent interaction in the cost
  function, there is no mechanism for agents to self-organise across
  exits.  If 100 agents face two exits and one has slightly less
  smoke, all 100 may choose the same exit.

- **Familiarity but no social behaviour.**  Agents can be given a
  per-agent cognitive map, so an unfamiliar agent routes only over
  stages it has discovered.  There is still no model for herding,
  following, or a preference for the familiar route among known ones.

- **The `"gate"` cost model measures exposure, not sight.**  Its
  criterion is always the mean K over the route polyline times the
  distance still to walk; no line of sight to the exit is tested.
  Integrated around corners this is the soot column the agent walks
  through, not how far it can see, and `tau_max` is not calibrated
  against a soot-dose or FED-equivalent limit.

- **Loose FDS coupling.**  Reading pre-computed FDS output means the
  evacuation cannot influence the fire (e.g., agents opening doors),
  and temporal resolution depends on slice file output frequency.
  There is no real-time feedback loop.

- **Single-floor only.**  Multi-floor buildings and stairs are not
  supported.

- **No collision-based locomotion model.**  JuPedSim's collision-free
  speed model does not produce social forces, body compression, or
  pushing.  Counterflow effects depend on the operational model's
  collision avoidance rather than explicit force-based interactions.

- **Limited validation.**  The routing model is new and has not yet
  been validated against experimental evacuation data or benchmarked
  against other evacuation models.

### Summary

The two systems make fundamentally different trade-offs:

| Trade-off | FDS+Evac | pyFDS-Evac |
|-----------|----------|------------|
| **Congestion vs. hazard awareness** | Strong congestion model (game-theoretic queueing); weak continuous hazard influence on routing | Congestion opt-in and uncalibrated across crowd sizes; strong hazard influence on routing |
| **Behavioural realism** | Rich (familiarity, herding, hawk-dove) | Familiarity via cognitive maps; no herding or social types |
| **Geometric fidelity** | Grid-constrained; L1/L2 distance approximations | Continuous geometry; polyline corridor paths |
| **Coupling** | Tight (inside FDS) | Loose (post-processing) |
| **Extensibility** | Fortran, tightly integrated | Python, modular |
| **Maturity** | Published; its own guide states it "is not yet fully validated" ([1] §1.4) | New, not yet validated |

Neither model is strictly superior.  An ideal system would combine
FDS+Evac's congestion-aware game-theoretic routing and behavioural
agent types with pyFDS-Evac's smoke-aware route cost (optical depth
under `"gate"`, a smoke/FED-weighted toll under `"additive"`) and
path-integrated hazard sampling.

---

## References

1. Korhonen, T. (2021). *Fire Dynamics Simulator with Evacuation:
   FDS+Evac. Technical Reference and User's Guide.* FDS 6.7.6, Evac
   2.6.0-draft. VTT Technical Research Centre of Finland.


2. Börger, K., Belt, A. & Arnold, L. (2024). A waypoint based
   approach to visibility in performance based fire safety design.
   *Fire Safety Journal*, 150, 104269.
   DOI: [10.1016/j.firesaf.2024.104269](https://doi.org/10.1016/j.firesaf.2024.104269).

3. Frantzich, H. & Nilsson, D. (2003). *Utrymning genom tät rök:
   beteende och förflyttning.* Department of Fire Safety Engineering,
   Lund University, Report 3126.

4. Purser, D. A. (2008). Assessment of hazards to occupants from
   smoke, toxic gases, and heat. In *SFPE Handbook of Fire Protection
   Engineering* (4th ed.), Chapter 2-6.

5. ISO 13571:2012. *Life-threatening components of fire — Guidelines
   for the estimation of time to compromised tenability in fires.*

6. Helbing, D. & Molnár, P. (1995). Social force model for
   pedestrian dynamics. *Physical Review E*, 51(5), 4282.

7. Korhonen, T. & Hostikka, S. (2009). Fire Dynamics Simulator with
   Evacuation: FDS+Evac. Technical Reference and User's Guide.
   VTT Working Papers 119.

8. Ehtamo, H., Heliövaara, S., Korhonen, T. & Hostikka, S. (2010).
   Game theoretic best-response dynamics for evacuees' exit selection.
   *Advances in Complex Systems*, 13(1), 113–134.
   DOI: 10.1142/S021952591000244X.

9. Heliövaara, S., Ehtamo, H., Helbing, D. & Korhonen, T. (2013).
    Patient and impatient pedestrians in a spatial game for egress
    congestion. *Physical Review E*, 87(1), 012802.

10. Ronchi, E., Fridolf, K., Frantzich, H., Nilsson, D., Walter, A.
    L. & Modig, H. (2018). A tunnel evacuation experiment on movement
    speed and exit choice in smoke. *Fire Safety Journal*, 97, 126–136.
    DOI: [10.1016/j.firesaf.2017.06.002](https://doi.org/10.1016/j.firesaf.2017.06.002).

11. Schroder, B., Arnold, L., Seyfried, A. (2020). A map
    representation of the ASET-RSET concept. *Fire Safety Journal*,
    115, 103154.
