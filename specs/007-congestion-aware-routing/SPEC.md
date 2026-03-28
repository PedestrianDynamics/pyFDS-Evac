# 007 — Congestion-aware routing

## Problem

pyFDS-Evac's route cost function considers path length, smoke
extinction, and FED but has **no congestion term**.  All agents
independently pick the cheapest Dijkstra path without considering
how many others target the same exit.  If one exit has slightly less
smoke than another, all agents may choose it, causing overcrowding
at the "best" exit while leaving other exits unused.

This is exactly the problem that Ehtamo et al. [1] solved for
FDS+Evac with a game-theoretic best-response model, where agents
minimise their *estimated evacuation time* — the sum of walking time
and queueing time — and self-organise to balance load across exits.
Their experiments show a ~29% reduction in total evacuation time
compared to nearest-exit selection ([1] Fig. 6).

## Goal

Add a queueing cost term to pyFDS-Evac's composite route cost so
agents avoid overcrowded exits.  The staggered per-agent
reevaluation already provides a natural Round Robin Algorithm (RRA,
[1] §4, Theorem 4.2), which Ehtamo et al. show converges to Nash
equilibrium in ~3–4 rounds.  No explicit equilibrium iteration is
needed.

## Relationship to Ehtamo et al. [1]

### What we adopt

The core insight: each agent's cost function should include a
**queueing delay** that depends on how many agents target the same
exit.  In Ehtamo et al., the cost is ([1] Eq. 6):

```
T_i(e_k) = beta_k * lambda_i(e_k) + tau_i(e_k)
```

where `beta_k` is seconds-per-agent (inverse of exit capacity),
`lambda_i` is the count of agents heading to exit `e_k` who are
closer to it than agent `i`, and `tau_i` is walking time.

We simplify `lambda_i` to `N_k` (total count of agents targeting
exit `e_k`), because in our stage-graph model all agents at a given
source node receive the same Dijkstra path — the "who is closer"
distinction is less meaningful than in FDS+Evac's direct
agent-to-exit model.

Our queueing time estimate:

```
t_queue(e_k) = N_k / capacity_k
```

where `capacity_k` is agents-per-second (inverse of `beta_k`).

### What we extend beyond [1]

Ehtamo et al.'s cost function is `queueing + walking`.  Ours
combines queueing with **continuous hazard terms**:

```
composite = path_length * (1 + w_smoke * K_ave)
          + w_fed * FED_max
          + w_queue * t_queue
```

This means agents balance three concerns simultaneously:
1. How long is the path and how much smoke is on it?
2. How much toxic gas will I accumulate?
3. How congested is the exit?

FDS+Evac's cost function does not include smoke or FED as
continuous terms — fire conditions enter only through the binary
preference-order filter.  Our model integrates both approaches.

### What we do not adopt

- **Distance-weighted agent count** (`lambda_i` vs `N_k`): we use
  total count for simplicity.
- **Preference ordering**: no familiarity/visibility group system.
- **Agent types**: no conservative/active/herding/follower
  distinction.
- **Hawk-dove game**: not relevant to the congestion problem.
- **Explicit NE iteration at init**: the staggered reevaluation
  provides RRA convergence naturally.

### Convergence argument

Ehtamo et al. prove that the RRA converges to NE in at most N²
iterations ([1] Theorem 4.2), and in practice ~3–4 rounds suffice
([1] §6).  pyFDS-Evac's staggered reevaluation (one agent per tick,
spread across the interval) is functionally equivalent to RRA: each
agent updates its best response given the current choices of all
others.  With typical reevaluation intervals of 10s and hundreds of
agents, multiple "rounds" complete within the first minute of
simulation.

## Design

### Cost function

Per-edge Dijkstra weight (Phase 1 of `rank_routes`):

```
edge_cost = length_m * (1 + w_smoke * k_avg) + w_fed * fed_growth
          + (w_queue * N_exit / capacity  if target is exit else 0)
```

The queueing term is added only on edges whose target is an exit
node, so it appears once per route (at the terminal edge).

Route-level composite cost (Phase 3):

```
composite = path_length * (1 + w_smoke * K_ave)
          + w_fed * FED_max
          + w_queue * N_exit / capacity
```

### Exit counts

A `dict[str, int]` mapping exit stage IDs to the number of agents
currently targeting each exit.  Maintained by the scenario loop:

- **Increment** when an agent is first assigned an exit (initial) or
  reroutes to a new exit.
- **Decrement** when an agent reroutes away from an exit or is
  removed (reaches exit / incapacitated).

Passed as an optional parameter to `rank_routes` and
`evaluate_and_reroute`.  When `None`, no queueing term is applied
(backward compatible).

### Exit capacity

A new optional field `capacity_agents_per_s: float` on exit stage
nodes in the scenario config:

```json
{
  "id": "exit_1",
  "stage_type": "exit",
  "capacity_agents_per_s": 1.3
}
```

Default: 1.3 agents/s (consistent with FDS+Evac's default specific
flow of 1.3 p/m/s for a 1 m wide door, [1] §6 p130).

Stored on `StageNode` as `Optional[float]`.  When `None`, falls
back to the default from config.

### Config additions

`RouteCostConfig` gains:

```python
w_queue: float = 1.0               # queueing cost weight (0 disables)
default_exit_capacity: float = 1.3  # fallback capacity (agents/s)
```

`w_queue = 0` disables congestion-aware routing entirely —
identical to current behaviour.

### Data structure additions

`RouteCost` gains:

```python
queue_time_s: float  # estimated queueing time at the exit
```

## Files to modify

| File | Changes |
|------|---------|
| `pyfds_evac/core/route_graph.py` | `RouteCostConfig` gains `w_queue`, `default_exit_capacity`; `StageNode` gains optional `capacity_agents_per_s`; `rank_routes` accepts optional `exit_counts` dict; edge cost adds queue term on exit edges; `evaluate_route` adds queue term to composite; `RouteCost` gains `queue_time_s` field; `evaluate_and_reroute` accepts and passes `exit_counts` |
| `pyfds_evac/core/scenario.py` | Maintain `exit_counts: dict[str, int]`; update on initial assignment, reroute, agent removal; read `capacity_agents_per_s` from stage config JSON; pass `exit_counts` to routing calls |
| `tests/test_route_graph.py` | Tests for queueing term effect, `w_queue=0` backward compat, capacity parameter, exit count updates |
| `docs/routing.md` | Document queueing cost, config parameters, congestion behaviour |

## What stays the same

- Graph topology (nodes, edges, polylines)
- Smoke/FED sampling along polylines
- Dynamic Dijkstra with smoke/FED weights
- Rejection logic (FED threshold, visibility filter)
- Staggered reevaluation scheduling
- `RouteSwitch` diagnostics and reasons

## Verification

1. **Unit tests**: Diamond graph with two exits — without queueing,
   all agents pick the same (closer) exit; with queueing, agents
   split across exits once one becomes congested.
2. **Backward compat**: `w_queue=0` produces identical results to
   current implementation.
3. **Capacity effect**: higher capacity → less queueing penalty →
   exit attracts more agents.
4. **Integration**: demo scenario with `w_queue > 0` — confirm
   agents distribute across exits in `route_cost_history.csv`.

## References

1. Ehtamo, H., Heliövaara, S., Korhonen, T. & Hostikka, S. (2010).
   Game theoretic best-response dynamics for evacuees' exit selection.
   *Advances in Complex Systems*, 13(1), 113–134.
   DOI: 10.1142/S021952591000244X.
