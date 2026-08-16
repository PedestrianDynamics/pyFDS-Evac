# Model comparison: FDS+Evac vs pyFDS-Evac

> This document compares the evacuation models in FDS+Evac (v2.6.0,
> Korhonen 2021) and pyFDS-Evac as implemented in this repository.
> Claims are referenced to the FDS+Evac Technical Reference and User's
> Guide [1] and to the pyFDS-Evac source code.  Where the two systems
> differ, the differences are stated precisely; where they agree, that
> is noted too.

---

## 1. Movement model

| Aspect | FDS+Evac | pyFDS-Evac |
|--------|----------|------------|
| **Locomotion model** | Social Force Model (Helbing et al. [7], three-circle body shape [1] Table 1), continuous 2-D equation of motion solved with a modified velocity-Verlet integrator ([1] §3.1–3.2, §3.6) | JuPedSim collision-free speed model (operational model configured externally); no social forces |
| **Body shape** | Three overlapping circles (torso Rd, shoulder Rs, head Rt) with rotational degree of freedom ([1] Table 1, Fig. 1) | Point agent (circle of configurable radius in JuPedSim) |
| **Counterflow** | Dedicated counterflow collision-avoidance algorithm ([1] §3.3, evac.f90:8965–8979) | Handled by JuPedSim's operational model; no separate counterflow algorithm |
| **Spatial discretisation** | Rectilinear evacuation mesh (separate from the FDS fire mesh); geometry is fitted to the underlying grid; minimum ~0.25 m cell size recommended ([1] §1.2) | Continuous walkable polygon (Shapely geometry); no grid |

**References:** [1] §3.1–3.2 (agent model), §3.3 (counterflow), §3.6 (numerical method); evac.f90 lines 8965–8979 (counterflow code).

---

## 2. Exit / route selection

This is the area of largest conceptual difference.

### FDS+Evac

Exit selection is formulated as an **N-player game** where each agent
minimises its own **estimated evacuation time** by choosing among
available exits [9].  The model is based on the concept of
*best-response dynamics*: each agent periodically updates its exit
choice by selecting the exit that minimises its estimated evacuation
time, given the current choices of all other agents.

#### Cost function

The estimated evacuation time of agent *i* through exit *e_k* is
([9] Eq. 6):

```
T_i(e_k, s_{-i}; r) = beta_k * lambda_i(e_k, s_{-i}; r) + tau_i(e_k; r_i)
```

where:
- `beta_k` is a capacity parameter for exit *k* (seconds per agent)
- `lambda_i` is the number of other agents heading to exit *e_k*
  who are closer to it than agent *i* ([9] Eq. 7)
- `tau_i = d(e_k; r_i) / v_i^0` is the walking time ([9] Eq. 8)

The term `beta_k * lambda_i` estimates the queueing delay; `tau_i`
estimates the walking time.  Thus `T_i` = queueing time + walking
time.

In the FDS+Evac implementation ([1] §3.6 p35–36;
evac.f90:9011–9028), this is computed as:

```
T = alpha * t_walk + (1 - alpha) * t_queue
```

where `t_walk = distance / v0`, `t_queue = N_queue /
(FAC_DOOR_QUEUE * Width)`, and `alpha` is `FAC_DOOR_ALPHA`.
Distance is L2 (Euclidean) for visible exits and L1 (Manhattan) for
non-visible exits.  The currently chosen exit is favoured by 10%
(anchoring parameter) to prevent oscillation.

#### Nash equilibrium and convergence

Ehtamo et al. [9] prove that this game has a **Nash equilibrium in
pure strategies** (Theorem 3.1) when all agents have the same walking
speed.  The NE is a fixed point of the system of all agents'
best-response functions.  The existence proof is constructive: agents
can be fixed to their equilibrium strategies one by one, in
ascending order of their evacuation times.

Three decentralised algorithms are analysed for finding the NE:
1. **Parallel Update Algorithm (PUA)**: all agents update
   simultaneously; converges in at most N iterations ([9] Theorem 4.1)
2. **Round Robin Algorithm (RRA)**: agents update one at a time in
   sequence; converges in at most N² iterations ([9] Theorem 4.2).
   **FDS+Evac uses RRA** ([9] §6 p127).
3. **Random Polling Algorithm (RPA)**: agents update stochastically.

In practice, RRA converges in ~3–4 iteration rounds regardless of
parameter values, while PUA can oscillate and require 10–18 rounds
([9] §6, Figs. 1–4).  The initial assignment at simulation start
iterates until door-target counts stabilise (evac.f90:6699).

Numerical experiments in [9] show that using the exit selection
game (vs. nearest-exit) reduces total evacuation time by ~29%
(Fig. 6).

#### Preference ordering

Exits are additionally filtered by a **preference order** (Table 3
in [1], Table 1 in [9]) determined by three Boolean criteria:
visibility (`vis`), familiarity (`fam`), and disturbing conditions
(`con`).  The best-response is constrained to the highest-priority
non-empty group ([9] Eq. 31):

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

A separate **hawk-dove game** (Heliövaara et al. [10]) is available
as an optional overlay (`C_HAWK >= 0`, default off: `C_HAWK = -2.0`,
evac.f90:1523).  When enabled, agents near an exit play a
hawk-dove game against nearby neighbours to decide whether to push
aggressively (hawk) or yield (dove).  This modulates *behaviour at
congestion points*, not the exit-selection cost function itself.

#### The smoke criteria on a door

FDS+Evac's *primary* smoke test on a door is **absolute**: a door
counts as smoke-free while `K_ave < ABS(FED_DOOR_CRIT)`.  The input is
a visibility in metres (`FED_DOOR_CRIT = -100.0`, evac.f90:1459) which
is converted to an extinction coefficient by Jin's relation,
`FED_DOOR_CRIT = 3.0 / FED_DOOR_CRIT` (evac.f90:5262) — so the default
is 0.03 /m.  `K_ave_Door` is assigned from `See_door` at evac.f90:16149,
and the tier-1 test that reads it is at evac.f90:16265 and :16272.  Among
the doors that pass, the agent minimises the time `T` above.

**That test is a hard filter.**  `IF (T_tmp < L2_min .AND. L2_tmp <
ABS(FED_DOOR_CRIT))` sets the chosen door `i_tmp` only for a door that
qualifies; when none qualifies the tier selects nothing and the search
moves to the next tier of doors, not to a time-only ranking.  pyFDS-Evac's
clean-exit tier falls through to the plain optical-depth ranking when it
is empty, which is our construction and not FDS+Evac's.  The

distance-relative rule — "check that visibility > 0.5 * distance to the
door" — is FDS+Evac's **tier-4 last resort** (evac.f90:16456-16463), reached
only when no smoke-free door exists.
That rule reads `K_ave` along the straight, occlusion-blocked bee line
(`See_door`, evac.f90:15343), so `S > 0.5 * d` is a statement about
optical depth along one real sight line.

Written out, the tier-4 test is
`L2_tmp = d * 0.5 / (3.0 / K_ave_Door)` struck out at `L2_tmp >= 1.0`
(evac.f90:16458, :16463) — that is `K_ave * d / 6 >= 1`, i.e. an optical
depth above 6, which is where pyFDS-Evac's `tau_max = 6` comes from.
Two scope limits on the citation: the loop runs only over doors already
known or visible, and a door struck out here is struck out
**permanently** (`Is_Visible_Door(i) = .FALSE.`, :16464-16465).
pyFDS-Evac inherits the threshold, applies it to the walked polyline
rather than the bee line, and remembers nothing.

Inside that tier, **dose and sight are alternatives, not layers**: the
sign of `FED_DOOR_CRIT` picks the branch (evac.f90:16439-16467).
Positive, and the door is scored by the dose the agent would arrive
with (`IntDose + FED_max_Door * distance / Speed`); negative — the
default `-100.0` — and it is scored by the visibility rule above.
Either way the resulting `L2_tmp` does **two** jobs: `L2_tmp >= 1.0`
strikes the door out ("too much smoke"), and `L2_tmp < L2_min` picks
the winner among those left.  The criterion vetoes *and* ranks, with
`FAC_DOOR_OLD2 = 0.9` favouring the door already targeted.

pyFDS-Evac splits those jobs.  Dose and sight both veto — dose when
`fed_max_route` exceeds `fed_rejection_threshold`, sight on the rule
above — and neither ranks; travel time ranks the survivors.  It also
applies both criteria at once rather than choosing one by a sign.

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

- **`"gate"` (default).** Route optical depth `tau = K_ave * L` decides
  availability *and* the ordering.  A route is refused when `tau`
  exceeds `tau_max` (6), or `tau_max * tau_return_margin` (4.8) for an
  exit the agent is not already walking to; survivors are ordered by
  `tau`, with travel time (plus `w_queue` x queue time) breaking ties.
  `K_ave` is the length-weighted mean over the route's own polyline, so
  `tau` is the soot column the agent walks through — an exposure
  statement, not a sighting distance.  Dijkstra weights each edge by its
  own `tau`, so path choice and exit choice are one objective.  The
  obstruction-aware sight line is kept as a diagnostic: it is defined
  only where a sign resolves, so gating on it let sign geometry decide
  which exits were tested at all.  An opt-in tier above `tau`
  reproduces FDS+Evac's absolute criterion
  (`clean_extinction_threshold`, default 0, off).
- **`"additive"`.** The composite
  `path_length * (1 + w_smoke * K_ave) + w_fed * FED_max`.

Under both, routes are rejected if FED exceeds a threshold, and a
fallback un-rejection ensures agents always have a path.  The
all-segments-non-visible rejection runs under `"additive"` only.

**The borrowing is partial and should be read as such.** pyFDS-Evac
takes FDS+Evac's *last-resort* criterion as its *primary* gate.  The
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
group.

| Aspect | FDS+Evac | pyFDS-Evac |
|--------|----------|------------|
| **Algorithm** | N-player best-response game (NE in pure strategies) with preference-order filter [9] | Dijkstra shortest-path with dynamic edge weights, then a per-route gate |
| **Cost function** | `T_i = beta_k * lambda_i + tau_i` (queueing + walking time) [9] Eq. 6 | gate: route optical depth `K_ave * L`, with travel time (+ `w_queue` x queue time) as tie-break; additive: `length * (1 + w_smoke * K) + w_fed * FED` |
| **Smoke test on a door** | Absolute `K_ave < 0.03 /m` (`FED_DOOR_CRIT`, evac.f90:1459, :5262, :16149); the `0.5 x d` visibility rule is the tier-4 last resort (:16463), where `L2_tmp = d * 0.5 / (3/K_ave) >= 1` is exactly `K_ave * d > 6` | Optical depth `K_ave * L <= 6`, the same threshold, but applied to the walked polyline rather than a straight sight line; x 0.8 budget for a rival exit; no absolute `K` door criterion. It vetoes *and* ranks |
| **Congestion** | Modelled: queueing time depends on count of closer agents heading to same exit | Optional (`w_queue`), off by default; a global tally of agents targeting the exit |
| **Familiarity** | Per-agent per-exit familiarity (user-configurable, constrains feasible exit set) | Per-agent cognitive map: an agent can only route over stages it knows or has discovered |
| **Social behaviour** | Herding and follower agent types observe neighbours | Not modelled |
| **Smoke in cost** | Binary: disturbing conditions at exit affect preference group, but extinction is not a continuous term in the cost function | gate: availability *and* ordering, both on route optical depth; additive: continuous weighted term |
| **FED in cost** | Not in cost function; only used for incapacitation at FED >= 1.0 | Veto threshold under both models (never a ranking term); additionally a `w_fed * FED_max` term under additive |
| **Distance metric** | L2 for visible exits, L1 (Manhattan) for non-visible exits; direct agent-to-exit | Polyline arc length along corridor geometry (via JuPedSim RoutingEngine); routes through intermediate stages |
| **Anticipation** | `FED_max_Door * dist / Speed`: extrapolation from presently observable conditions | `anticipate` prices each segment at the agent's arrival time from the FDS solution itself — an upper bound on foresight, not FDS+Evac's model |
| **Equilibrium** | Proven NE existence; RRA converges in ~3–4 rounds [9] | No equilibrium concept; each agent independently picks the cheapest Dijkstra path |
| **Anchoring** | Current door favoured by 10 %: `FAC_DOOR_WAIT` = 0.9 on the time criterion (:1505, applied :16264), `FAC_DOOR_OLD2` = 0.9 on the smoke criterion (:1507, applied :16290, :16467) | `exit_switch_anchor` = 0.9 on travel time, mirroring `FAC_DOOR_WAIT`; `current_exit_discount` = 0.9 on the current exit's optical depth in the sort, mirroring `FAC_DOOR_OLD2`; bypasses for a lethal current exit and (gate) a feasible rival clearer by more than the symmetric deadband `tau_deadband * tau_max` (0.6), which also refuses a rival dirtier by that much; plus deadbands of 0.9 on dose and 0.8 on the optical-depth budget |
| **Rerouting frequency** | ~1 Hz (every second on average, `TAU_CHANGE_DOOR = 1.0`, evac.f90:1466) | Configurable interval, staggered per agent |

---

## 3. Smoke–speed interaction

Both systems use the same underlying correlation from the Frantzich
& Nilsson experiments (Lund 2003, Report 3126 [4]).

### Speed reduction formula

```
speed_factor(K) = 1 + (beta / alpha) * K
```

with default coefficients `alpha = 0.706`, `beta = -0.057`.

| Aspect | FDS+Evac | pyFDS-Evac |
|--------|----------|------------|
| **Speed formula** | `c(Ks) = 1 + beta * Ks / alpha` ([1] §3.4 Eq. 11; evac.f90:8173–8175) | Same formula (`smoke_speed.py:225`) |
| **Default alpha/beta** | 0.706 / -0.057 (evac.f90:1479–1480) | 0.706 / -0.057 (`smoke_speed.py:91–92`) |
| **Minimum speed** | Configurable `SMOKE_MIN_SPEED_FACTOR`; additional visibility-based cutoff (evac.f90:8183–8189) | Configurable `min_speed_factor` (default 0.1) |
| **Smoke input** | Soot density from FDS mesh converted to extinction via `K = MASS_EXTINCTION_COEFF * SOOT_DENS * 1e-6` (evac.f90:8160–8161) | Extinction coefficient K read directly from FDS `SOOT EXTINCTION COEFFICIENT` slice via fdsreader |
| **Sampling geometry** | Local value at agent position on the evacuation mesh | Beer-Lambert path-integrated mean along edge polyline (Boerger et al. 2024 [3], Eq. 8–9) |

**Key difference:** FDS+Evac applies the speed reduction using the
*local* soot density at the agent's grid cell.  pyFDS-Evac samples the
extinction coefficient at uniform intervals along the corridor
polyline between two stages and uses the arithmetic mean.  This
polyline-integrated approach follows Boerger et al. (2024) and
considers smoke conditions along the entire path segment, not just
at the agent's current position.

---

## 4. Toxicity / FED model

### FDS+Evac

FED is computed using Purser's Fractional Effective Dose concept [5].
The default calculation uses **CO, CO2, and O2** gas phase
concentrations ([1] §1.2 p11, §2.7 p19).  The effects of additional
gases (NO, NO2, CN, HCl, HBr, HF, SO2, C3H4O, CH2O) are included
**only if the user provides the corresponding FDS species** ([1] §1.2
p11).  By default, HCN and HCl effects are **not** modelled; only the
CO2 hyperventilation factor is included ([1] §2.7 p19).

The FED function itself is in FDS's `PHYSICAL_FUNCTIONS` module (the
`FED` function imported at evac.f90:26), not in evac.f90 directly.

FED activity level is configurable: 1 (at rest), 2 (light work,
default), 3 (heavy work) (evac.f90:1465).

Incapacitation occurs at FED >= 1.0 ([1] §3.4 p31).

### pyFDS-Evac

FED is computed using the **ISO 13571** model (`fed.py`).  The full
model includes:

```
FED_tot = (FED_CO + FED_CN + FED_NOx + FLD_irr) * HV_CO2 + FED_O2
```

where:
- `FED_CO`: CO narcosis (Eq. 13 from guide)
- `FED_CN`: HCN + NO2 (protective effect of NO2 on HCN toxicity)
- `FED_NOx`: NO + NO2 (Ct product = 1500 ppm·min)
- `FLD_irr`: irritant gases (HCl, HBr, HF, SO2, acrolein, formaldehyde)
- `HV_CO2`: CO2 hyperventilation factor
- `FED_O2`: O2 vitiation

Required FDS slices: CO, CO2, O2.
Optional slices: HCN, NO, NO2, HCl, HBr, HF, SO2, acrolein,
formaldehyde.

When only CO/CO2/O2 are available, the model falls back to the
three-gas subset: every optional species defaults to zero concentration in
`DefaultFedInputs` (`fed.py:14–40`), so an absent slice contributes nothing.

| Aspect | FDS+Evac | pyFDS-Evac |
|--------|----------|------------|
| **FED standard** | Purser's FED concept [5] | ISO 13571 / Purser equations |
| **Default gases** | CO, CO2, O2 | CO, CO2, O2 (same three-gas minimum) |
| **Optional gases** | NO, NO2, CN, HCl, HBr, HF, SO2, C3H4O, CH2O (user must provide species) | HCN, NO, NO2, HCl, HBr, HF, SO2, acrolein, formaldehyde (auto-detected from FDS slices) |
| **HCN/HCl by default** | Not modelled unless user provides species ([1] §2.7 p19) | Not modelled unless FDS slices are present |
| **Incapacitation** | FED >= 1.0, agent stops (v0 = 0) ([1] §3.4 p31) | FED >= 1.0, route is rejected; agent incapacitation handled by simulation config |
| **Activity level** | Configurable (rest/light/heavy) | Not configurable (fixed light work equivalent) |
| **FED in routing** | Not used in exit selection cost; only used for incapacitation | A veto under both cost models; additionally a ranking term (`w_fed * FED_max`) under `"additive"` only, not under the default gate |
| **Temperature/radiation** | Not implemented for agent effects ([1] §1.2 p11) | Not implemented |

> **Note on the PDF claim [2]**: The PDF states FDS+Evac uses "Basic
> FED (CO, O2), flat speed penalty" while pyFDS-Evac uses "Full ISO
> 13571 / Purser equations (10+ irritant gases)."  This is **partially
> misleading**.  Both systems support the same extended gas list when
> the user provides the species.  The difference is that FDS+Evac
> defaults to CO/CO2/O2 and requires explicit user setup for
> additional species, while pyFDS-Evac auto-detects available FDS
> slices.  Neither system models all 10+ gases "by default" — both
> require the FDS simulation to produce those species.  The
> characterisation of FDS+Evac as "basic" understates its capability.

---

## 5. FDS data integration

| Aspect | FDS+Evac | pyFDS-Evac |
|--------|----------|------------|
| **Coupling** | Tightly coupled: evacuation module is compiled into FDS and runs as subroutines within the same executable ([1] §2.1) | Loosely coupled: reads pre-computed FDS output files via fdsreader; runs as a separate post-processing step |
| **Smoke data** | Direct access to soot density on the FDS computational grid at runtime | Reads FDS slice files (SOOT EXTINCTION COEFFICIENT, gas species volume fractions) |
| **Visibility check** | Bee-line visibility from agent to exit; checks if smoke along the line exceeds a user-defined threshold ([1] §3.5 p32, §3.6 p36) | Beer-Lambert integrated extinction along edge polylines (Boerger et al. 2024 [3]) |
| **Temporal resolution** | Same timestep as FDS fire simulation | Reads FDS output at whatever temporal resolution is available in the slice files |

> **Note on the PDF claim [2]**: The PDF characterises FDS+Evac data
> integration as "Categorical discrete tiers (Bee-line visibility)."
> This is **inaccurate**.  FDS+Evac uses continuous soot density values
> from the FDS grid, not categorical tiers.  The "bee-line" visibility
> check is a continuous comparison of smoke along the line of sight
> against a threshold, not a discrete categorisation.

---

## 6. Exit flow / throughput

| Aspect | FDS+Evac | pyFDS-Evac |
|--------|----------|------------|
| **Flow model** | Emergent from social-force dynamics; door width × specific flow (default 1.3 1/m/s) used for queueing time estimation ([1] §3.6 p36) | JuPedSim collision-free model produces emergent flow; optional per-checkpoint throughput throttling (`enable_throughput_throttling`, `max_throughput` in scenario config) |
| **Agent update order** | Agents are updated in sequence within each evacuation mesh; order can affect results ([1] §3.6) | JuPedSim handles agent updates internally |

> **Note on the PDF claim [2]**: The PDF describes FDS+Evac as
> "Round-Robin sequential updates" and pyFDS-Evac as "Algorithmic
> throughput throttling."  The "round-robin" characterisation is
> misleading — FDS+Evac uses a standard time-stepping loop for all
> agents, which is normal for agent-based simulations, not a special
> "round-robin" scheme.  The throughput throttling in pyFDS-Evac is an
> optional feature, not a core architectural difference.

---

## 7. Geometry representation

| Aspect | FDS+Evac | pyFDS-Evac |
|--------|----------|------------|
| **Domain** | 2-D rectilinear evacuation meshes; obstacles conform to grid ([1] §1.2) | Continuous walkable polygon (Shapely); arbitrary geometry |
| **Multi-floor** | Separate evacuation meshes per floor connected by DOOR/ENTR/CORR/STRS namelists ([1] §1.2, §8.11–8.15) | Currently single-floor; multi-floor not yet implemented |
| **Stairs** | Dedicated staircase models (CORR, EVSS, STRS) with speed reduction factors ([1] §1.2 p13) | Not implemented |
| **Doors** | Explicit DOOR and EXIT namelists with width, flow fields, opening/closing times ([1] §8.10–8.12) | Stages (distributions, checkpoints, exits) in the stage graph |

---

## 8. Summary of PDF claims [2] vs reality

The NotebookLM-generated PDF [2] contains several claims that
require correction:

| PDF claim | Assessment |
|-----------|------------|
| FDS+Evac uses "Game-Theoretic Best-Response (Nash Equilibrium)" | **Partially correct** but context is missing. The core exit selection *is* formulated as an N-player game with best-response dynamics and provable NE existence [9]. However, the PDF conflates this with the separate hawk-dove game (which is optional, off by default). The game-theoretic aspect is the exit-selection cost function itself, not a separate "game theory module." |
| FDS+Evac cost function is `T_i = beta_k * lambda_i + tau_i(e_k)` | **Correct notation** from Ehtamo et al. [9] Eq. 6. The implementation in evac.f90 uses `alpha * t_walk + (1 - alpha) * t_queue` which is an equivalent weighted form. |
| FDS+Evac uses "Categorical discrete tiers (Bee-line visibility)" | **Incorrect.** FDS+Evac uses continuous soot density from FDS; visibility is a continuous threshold comparison, not discrete tiers. |
| FDS+Evac uses "Basic FED (CO, O2), flat speed penalty" | **Understated.** FDS+Evac supports CO, CO2, O2 by default and optionally 9+ additional gases. Speed reduction is a continuous function of extinction, not a "flat penalty." |
| pyFDS-Evac uses "Full ISO 13571 / Purser equations (10+ irritant gases)" | **Overstated.** pyFDS-Evac *supports* 12 gas species but only uses those available in the FDS output. The default minimum is CO/CO2/O2, same as FDS+Evac. |
| FDS+Evac uses "Round-Robin sequential updates" | **Misleading.** Standard time-stepping loop, not a special scheme. |
| pyFDS-Evac uses "Algorithmic throughput throttling" | **Overstated.** This is an optional per-checkpoint feature, not a core model difference. |

---

## 9. Advantages and disadvantages

### FDS+Evac

**Advantages:**

- **Congestion-aware routing with theoretical guarantees.**  The
  game-theoretic exit-selection model accounts for queueing at exits.
  The NE existence proof [9] guarantees a consistent solution, and
  the RRA converges in a few rounds.  This means agents
  self-organise to balance load across exits — shown to reduce total
  evacuation time by ~29% versus nearest-exit [9] Fig. 6.

- **Rich behavioural model.**  Four agent types
  (conservative/active/herding/follower) with per-agent exit
  familiarity and visibility model a heterogeneous population.  The
  preference-order system captures the well-documented tendency to
  prefer familiar exits over unfamiliar ones, even when the familiar
  route is longer [9] §5.2, [1] §3.5.

- **Tight FDS coupling.**  Running inside the FDS executable gives
  access to all fire-simulation fields at native resolution and
  timestep.  No I/O overhead or temporal interpolation.

- **Social Force Model with counterflow.**  The three-circle body
  shape and social-force locomotion produce realistic crowd dynamics
  including pushing, lane formation, and counterflow effects ([1]
  §3.2–3.3).

- **Mature and validated.**  Extensive IMO test cases, sensitivity
  analyses, and comparisons with other models ([1] Ch. 4–6).

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

- **FED does not influence routing.**  FED is accumulated per agent
  and triggers incapacitation at FED >= 1.0, but projected FED along
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
  Extinction K and projected FED are continuous, weighted terms in
  the per-edge cost Dijkstra minimises, under both models.  What
  differs is how the resulting routes are judged: `"additive"`
  (historical) keeps smoke as a continuous toll per metre, while
  `"gate"` (default) makes distance the objective and lets smoke
  decide which exits remain available, ordering the survivors by
  travel time.  The gate exists because in the additive form both terms
  scale with route length, so a long clean detour can never win.
  Being able to run the same deck under both is itself the
  comparison instrument — see
  [docs/route-cost-gate.md](route-cost-gate.md).

- **Path-integrated extinction sampling.**  Smoke is sampled along
  corridor-following polylines (JuPedSim RoutingEngine waypoints)
  using the Beer-Lambert path-integrated mean [3].  This captures
  spatially varying smoke along the actual walking path, not just at
  the agent's position or along a straight line.

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

- **The gate's sight test is only as good as its sight line.**  Where
  an exit's sign resolves no line of sight — around a corner,
  concealed, or without a sign descriptor — the criterion falls back
  to mean K over the whole route polyline, compared against the whole
  remaining length, which holds long routes to a stricter standard than
  short ones.  On the deck the model is judged on, every refusal that
  changed an exit came from that fallback.

- **Loose FDS coupling.**  Reading pre-computed FDS output means the
  evacuation cannot influence the fire (e.g., agents opening doors),
  and temporal resolution depends on slice file output frequency.
  There is no real-time feedback loop.

- **Single-floor only.**  Multi-floor buildings with stairs are not
  yet supported.

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
| **Maturity** | Validated, published, widely used | New, not yet validated |

Neither model is strictly superior.  An ideal system would combine
FDS+Evac's congestion-aware game-theoretic routing and behavioural
agent types with pyFDS-Evac's continuous smoke/FED-weighted cost
function and path-integrated hazard sampling.

---

## References

1. Korhonen, T. (2021). *Fire Dynamics Simulator with Evacuation:
   FDS+Evac. Technical Reference and User's Guide.* FDS 6.7.6, Evac
   2.6.0-draft. VTT Technical Research Centre of Finland.

2. NotebookLM-generated PDF: "From Rigid Grids to Fluid Dynamics:
   The Mathematical and Architectural Evolution of pyFDS-Evac."
   (Unreviewed AI-generated document.)

3. Boerger, M., Mayer, L., Mühlberger, A. & Pauli, P. (2024).
   Waypoint-based visibility and evacuation modeling. *Fire Safety
   Journal*, 150, 104269.

4. Frantzich, H. & Nilsson, D. (2003). *Utrymning genom tät rök:
   beteende och förflyttning.* Department of Fire Safety Engineering,
   Lund University, Report 3126.

5. Purser, D. A. (2008). Assessment of hazards to occupants from
   smoke, toxic gases, and heat. In *SFPE Handbook of Fire Protection
   Engineering* (4th ed.), Chapter 2-6.

6. ISO 13571:2012. *Life-threatening components of fire — Guidelines
   for the estimation of time to compromised tenability in fires.*

7. Helbing, D. & Molnár, P. (1995). Social force model for
   pedestrian dynamics. *Physical Review E*, 51(5), 4282.

8. Korhonen, T. & Hostikka, S. (2009). Fire Dynamics Simulator with
   Evacuation: FDS+Evac. Technical Reference and User's Guide.
   VTT Working Papers 119.

9. Ehtamo, H., Heliövaara, S., Korhonen, T. & Hostikka, S. (2010).
   Game theoretic best-response dynamics for evacuees' exit selection.
   *Advances in Complex Systems*, 13(1), 113–134.
   DOI: 10.1142/S021952591000244X.

10. Heliövaara, S., Ehtamo, H., Helbing, D. & Korhonen, T. (2013).
    Patient and impatient pedestrians in a spatial game for egress
    congestion. *Physical Review E*, 87(1), 012802.

11. Ronchi, E., Fridolf, K., Frantzich, H., Nilsson, D., Walter, A.
    L. & Modig, H. (2013). A tunnel evacuation experiment on movement
    speed and exit choice in smoke. *Fire Safety Journal*, 97, 126–136.

12. Schroder, B., Arnold, L., Seyfried, A. (2020). A map
    representation of the ASET-RSET concept. *Fire Safety Journal*,
    115, 103154.
