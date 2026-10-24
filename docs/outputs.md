---
title: "Outputs"
weight: 7
---

What a run writes, when each file is missing, and how to read the results
without being misled. Every file below is written by `run.py` only when you
ask for it with its flag. The web GUI and the terminal UI ask for all of them,
in the run's folder. From Python, the same data are
fields of the `ScenarioResult` that `run_scenario()` returns.

| File | Flag | Written when | Rows |
|---|---|---|---|
| Trajectory SQLite | `--output-sqlite PATH` | always | JuPedSim frames at 10 frames/s |
| Run manifest | with `--output-sqlite` | always | one JSON object, `<stem>.manifest.json` beside the SQLite |
| `agent_scalars` table | inside the SQLite | a FED track ran | one per agent per FED update |
| Smoke history | `--output-smoke-history CSV` | a smoke model ran (`--fds-dir` with an extinction slice, or `--constant-extinction`) | one per agent per `--smoke-update-interval` |
| FED history | `--output-fed-history CSV` | the gas FED or the heat FED ran | one per agent per `--smoke-update-interval` |
| Route history | `--output-route-history CSV` | rerouting is on (the default), or an exit has `open_from_s` or `closed_after_s`; without rerouting it then holds only the rows of agents whose exit is closed: `exit_closed`, `initial` (exit not open yet) or `default_route` ([#395](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/395)) | one per change of target: switch, fallback, better path, explore or wander; `initial` only when an agent without an exit is first given one, so a deck whose agents start with an exit can write a file with only its header |
| Route cost history | `--output-route-cost-history CSV` | rerouting is on | one per candidate route per agent per evaluation |
| Exit history | `--output-exit-history CSV` | always | one per agent that walks the stage graph |

A run of the terminal UI also leaves `child.log` (the run's own messages) in
its folder, and `command.sh` and `run.py` when you save them. They are not
model outputs; see [Terminal UI](terminal-ui.md#outputs-and-folders).

The run command, flags and defaults are on [Usage](usage.md). The example
columns below come from

```bash
uv run python run.py --scenario assets/iso_table22_coupled/config_a.json \
    --fds-dir assets/iso_table22_coupled/fds/a \
    --output-sqlite results/run.sqlite --output-smoke-history results/smoke.csv \
    --output-fed-history results/fed.csv --output-route-history results/routes.csv \
    --output-route-cost-history results/route_costs.csv
```

## Trajectory SQLite

The JuPedSim trajectory file, unchanged in schema: agent positions every 0.1 s
(simulation step 0.01 s, every tenth frame written). Load it with
[PedPy](https://pedpy.readthedocs.io), `scripts/plot_trajectories.py`,
`scripts/vis.py`, or [fds-viewer](https://github.com/PedestrianDynamics/fds-viewer).

When a FED track ran, the file also holds an extra table,
`agent_scalars(frame, id, fed, heat_fed, speed, in_fds_domain)`: gas FED,
heat FED and walking speed (`base_speed × speed_factor`, m/s) per agent per
frame of a FED update, and `in_fds_domain` (1 inside the FDS slices, 0 outside,
`NULL` without FDS output; see the FED history). The JuPedSim tables are
untouched, so JuPedSim tools still read the file. `heat_fed` sits before
`speed`: read the columns by name, not by position.

## Run manifest

The provenance record of the run. From Python it is `result.manifest_file`;
with `--output-sqlite` it is copied beside the trajectory as
`<stem>.manifest.json`.

| Key | Meaning |
|---|---|
| `versions` | installed versions of pyfds-evac, jupedsim, fdsreader, fdsvismap |
| `uv_lock_sha256` | hash of the `uv.lock` of the checkout, `null` for an installed wheel |
| `git_commit`, `git_dirty` | commit of the checkout, and whether tracked files had uncommitted changes; both `null` for an installed wheel |
| `seed` | the seed of the run |
| `agent_seeding` | how per-agent and per-distribution draws are derived from the seed, `spawn-key-blake2b-v2`; runs of another scheme, or without the key, draw differently under the same seed (`v1` runs place agents from `seed + index`, #360) |
| `scenario_path` | the scenario file that was loaded |
| `fds_dir`, `fds_version` | absolute FDS directory, and the FDS version read from its `.smv`; `null` without FDS output |
| `created_utc` | time the run finished, UTC |
| `outcome` | how the run ended: `status` (`completed` or `incomplete`), `end_reason` (`all_evacuated`, `time_limit`, `flows_closed`, `all_mobile_left` or `deadlock`), `agents_remaining` and `agents_not_spawned`, and `deadlock` (`agents`, `since_s`, `positions`) when the run stopped as a deadlock, as in [Reading the results](#reading-the-results) |
| `heat_clothing` | `clothed` or `unclothed`, when an ISO 13571 convective heat law ran |
| `heat_fed_threshold_override` | the `--heat-fed-threshold` value, only when it was set |
| `heat_endpoint`, `heat_validity` | the SFPE endpoint and its validity limits, only with `--heat-endpoint` |
| `smoke_blind` | `true`, only with `--smoke-blind` |
| `fds_coverage` | when FDS slices are sampled: the setup check of the scenario against the slice coverage, with `quantities`, `walkable_area_m2`, `walkable_outside_m2`, `areas_outside_m2` (exits, checkpoints, spawn areas), `signs_outside`, `signs_off_vismap_grid_m` and `edges_outside_m` (route edges) |
| `fds_outside` | with `fds_coverage`: the history rows sampled outside the FDS slices, as `rows`, `agents` and `agent_seconds`, the same as `metrics["fds_outside"]` |
| `replay_exits` | only with `--replay-exits`: `agents`, the number of replayed spawns, and `sha256`, of the sorted `origin<TAB>spawn_index<TAB>exit_id` lines, one per spawn and joined by newlines, to match the run whose exit history was replayed |
| `heat_fed_method`, `heat_flux_parameters` | only with `--heat-fed-method total-flux`: ε, h, skin temperature, dose *D*, radiant threshold, the list of assumed parameters, and, per option, the layer parameters or `radiant_source`, `u_factor` and `radiant_flux` |

The manifest does not yet record the slice height that was actually read
([#165](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/165)).

Example, from the command above:

```json
{
  "versions": {"pyfds-evac": "0.1.0", "jupedsim": "1.4.2",
               "fdsreader": "1.11.7", "fdsvismap": "0.2.1"},
  "uv_lock_sha256": "08fc497c…",
  "git_commit": "80a7608…",
  "git_dirty": false,
  "seed": 420,
  "agent_seeding": "spawn-key-blake2b-v2",
  "scenario_path": "/…/assets/iso_table22_coupled/config_a.json",
  "fds_dir": "/…/assets/iso_table22_coupled/fds/a",
  "fds_version": "FDS-6.10.1-0-g12efa16-release",
  "created_utc": "2026-09-29T12:53:08+00:00"
}
```

## Smoke history

| Column | Unit | Meaning |
|---|---|---|
| `time_s` | s | simulation time |
| `agent_id` | — | JuPedSim agent id |
| `x`, `y` | m | agent position |
| `base_speed` | m/s | the agent's speed before the smoke factor (its `v0` in open space) |
| `desired_speed` | m/s | speed after the smoke factor |
| `speed_factor` | — | `desired_speed / base_speed` from the speed law |
| `extinction_per_m` | 1/m | extinction coefficient *K* at the agent |
| `in_fds_domain` | — | with FDS output only: `True` where the extinction slice covers the agent, `False` where it reads *K* = 0 (clear air) outside it |

## FED history

One row per agent per update. The gas and heat columns are both present
whenever the file is written. A track that did not run shows clean air:
without the gas FED, the gases read 0 (O₂ 20.9 %) and every gas rate and
`fed_cumulative` read 0.0; without the heat FED, `temperature_celsius` reads
20.0 °C and `heat_fed_cumulative` 0.0.

| Column | Unit | Meaning |
|---|---|---|
| `time_s`, `agent_id`, `x`, `y` | s, —, m | as in the smoke history |
| `co_percent`, `co2_percent`, `o2_percent` | vol % | gas concentrations at the agent |
| `hcn_ppm`, `no_ppm`, `no2_ppm` | ppm | 0 when the case has no such slice |
| `co_rate_per_min`, `cn_rate_per_min`, `nox_rate_per_min`, `fld_rate_per_min` | 1/min | narcotic and irritant terms, before the CO₂ hyperventilation factor |
| `hv_co2` | — | CO₂ hyperventilation factor that multiplies the four terms above |
| `o2_rate_per_min` | 1/min | hypoxia term, added after the factor |
| `fed_rate_per_min` | 1/min | total gas FED rate |
| `fed_cumulative` | — | running gas FED |
| `temperature_celsius` | °C | gas temperature at the agent |
| `heat_fed_rate_per_min`, `heat_fed_cumulative` | 1/min, — | heat FED rate and running total, a separate track |
| `incapacitation_cause` | — | empty, `gas`, `heat` or `gas+heat` on the agent's last row, the update at which the threshold was crossed |
| `fic` | — | fractional irritant concentration |
| `fic_speed_factor` | — | irritant slowdown factor, 1 unless `--enable-fic-speed` |
| `incapacitated` | — | `True` on the agent's last row, the update at which a threshold is crossed; the record ends there |
| `base_speed`, `desired_speed`, `speed_factor` | m/s, m/s, — | speed as the agent is moving at this update, all slowdowns combined |

Extra columns appear with some heat options:

| Columns | Present with |
|---|---|
| `heat_endpoint`, `heat_outside_validity`, `heat_humidity` | `--heat-endpoint`; `heat_outside_validity` is `True` above 205 °C or for a non-finite sample, `heat_humidity` is `unknown` |
| `heat_flux_kw_m2` | `--heat-fed-method total-flux`: the heat flux to the skin [kW/m²] |
| `heat_integrated_intensity_kw_m2` | `--heat-radiant-source integrated-intensity`: *U* at the agent [kW/m²] |
| `heat_layer_temperature_c` | `--heat-regime layer`: layer temperature [°C] |
| `in_fds_domain` | FDS output: `True` where every sampled gas and heat slice covers the agent, `False` where it reads ambient air outside them |

The equations behind each rate are on [Models › FED](/models/fed.md) and
[Models › Heat](/models/heat.md).

## Route history

| Column | Meaning |
|---|---|
| `time_s`, `agent_id` | when, and who |
| `old_exit`, `new_exit` | exit before and after; `new_exit` is a node for `explore`, `wander`, `return` and `stay`. `old_exit` is empty for the first assignment, for `explore`, `wander`, `return` and `stay`, for an `initial` row, and for a `default_route` row at spawn. An agent that leaves its default route for another exit while the default exit is open has the default exit as `old_exit` |
| `old_cost`, `new_cost` | ranking cost of the two routes, rounded to 4 decimals; `old_cost` is empty when there was none |
| `reason` | `initial`, `default_route`, `allocation_preference`, `fed_reroute`, `smoke_reroute`, `exit_closed`, `exit_opened`, `learned_exit`, `congestion`, `shorter_path`, `exit_unreachable`, `resume`, `fallback`, `better_path`, `explore`, `wander`, `return` or `stay` |

The reasons are defined on
[Routing in practice](routing.md#route-switch-reasons). A change of exit is
labelled by its cause
([#92](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/92)):
`smoke_reroute` only when smoke made the switch, `fed_reroute` when the dose
did, `shorter_path` when time or length alone did.

An `initial` row is written only when an agent that has no exit at a
re-evaluation is given its first one: for an agent on its default route,
when that exit is its default exit or the default exit is not open. A
`default_route` row is written for
an agent that follows its default route, the journey or the nearest exit on
foot: at spawn when its map holds no exit, or when its known exits are all
closed or unreachable. For a default exit that has not opened yet, the
spawn row names the open exit the agent is sent to; with no exit open there
is none. Other agents that start with
a journey exit get no row until they change target, so a run without any switch (such as the
example above, `Route history rows: 0`) writes a file with only its header. This
does not mean rerouting was off.

## Route cost history

One row per candidate route at each evaluation of each agent. The columns are
the fields of `RouteCost`, defined on
[Routing in practice](routing.md#routecost), plus the context of the
evaluation:

| Column | Meaning |
|---|---|
| `time_s`, `agent_id`, `source` | when, who, and the graph node the route starts from |
| `current_exit`, `current_fed` | the agent's exit and gas FED at this evaluation |
| `route_rank`, `exit_id`, `path` | rank of this route (1 is best), its exit, and its node sequence |
| `path_length_m`, `k_ave_route`, `travel_time_s`, `fed_max_route` | route measures |
| `composite_cost`, `rank_cost`, `k_max_route`, `tau_route`, `k_leg_max`, `clean` | cost terms; which one orders the routes depends on the cost model |
| `feasible`, `rejected`, `rejection_reason` | whether the route was available, and why not. When every route is refused, the route the agent is sent along stays `rejected` and its reason starts with `fallback: `; read that prefix to tell it from a refusal that ended the tick |
| `queue_time_s`, `exit_count`, `exit_capacity` | queue estimate at the exit |

Under the default `"gate"` model, routes are ordered on `tau_route`, not on
`composite_cost`; see [Usage › Route cost curves](usage.md#route-cost-curves--plot_route_costspy).

## Exit history

One row per agent that walks the stage graph, in spawn order. From Python it
is `result.exit_history`. `--replay-exits` reads its `origin`,
`spawn_index` and `exit_id` columns.

| Column | Meaning |
|---|---|
| `agent_id` | JuPedSim agent id, as in the trajectory SQLite |
| `origin` | where the agent was spawned: `initial` for the agents placed at t = 0, `flow:<distribution>` for a flow source |
| `spawn_index` | order in which the agent was spawned from its origin in this run, from 0 |
| `exit_id` | the exit the agent left through; for an agent still inside at the end, the exit it was heading for |

## Reading the results

`ScenarioResult` (and the summary line of `run.py`) reports:

| Field | Meaning |
|---|---|
| `evacuation_time` | simulated time when the loop stopped: all agents left, only incapacitated agents left inside, the flows closed, a deadlock was detected, or the time limit |
| `metrics["last_exit_time"]` | simulated time the last agent left, by direct-steering removal or through a JuPedSim exit, rounded to 0.01 s; `None` when nobody left. Never later than `evacuation_time` |
| `total_agents`, `agents_evacuated`, `agents_remaining` | head counts at the end |
| `agents_not_spawned` | flow agents that had not entered when the run stopped: cut off by `max_simulation_time`, or still waiting for a free position when their flow window closed. A configuration error while building a flow agent stops the run instead of being counted here |
| `metrics["flow_spawns_deferred"]` | how often a flow found no free position in its spawn area and waited, counted per flow and time step: two flows waiting in one step count twice; the run then prints one line per such flow (#710) |
| `status` | `"completed"` when every agent entered and left; `"incomplete"` when the run reached `max_simulation_time` with agents inside or still to enter, when the building emptied after its flow windows closed with flow agents not spawned, when only incapacitated agents remain inside and no flow window is open, or when the whole crowd stood still and the run stopped as a deadlock |
| `end_reason` | why the run stopped: `"all_evacuated"` for a completed run; `"time_limit"` when `max_simulation_time` stopped it; `"flows_closed"` when the building emptied after the last flow window with agents still to enter had closed, before the time limit; `"all_mobile_left"` when every mobile agent has left, only incapacitated agents remain inside and no flow window is open; `"deadlock"` when every mobile agent inside stood still (net displacement below 0.03 m over the last 100 s) and no agent was in pre-movement, at a waiting stage or still to spawn. The run stops at once, before the time limit. Also in `metrics["end_reason"]` |
| `success` | `True` only for a completed run; `run.py` then exits with status 0, and with status 2 for an incomplete run |
| `metrics["route_switches"]` | per agent, each time step whose decision changes the agent's target (`new_exit`), or its path to an exit it holds (a row with an `old_exit`). A time step counts at most once, judged by its last row, the decision the agent acts on. The agent's first step counts only if its row names an old exit, the exit seeded at spawn. Reasons are not read (#733, #744). Each new `explore` or `wander` node counts, also moving on after reaching the previous one, so the count is not a number of reversals. Present when the route history has rows, so it can be 0 |
| `metrics["fed_enabled"]` | `True` when the gas FED ran, `False` otherwise (CO, CO2 or O2 missing, no `--fds-dir`, or FED switched off). With `False` there is no `fed_max`, and a heat-only run's `fed_cumulative` column is all zero |
| `metrics["fed_max"]` | highest gas FED of any agent; present only when the gas FED ran. It stops at the collapse row of an incapacitated agent |
| `metrics["heat_fed_max"]` | highest heat FED; present only when the heat FED ran. It stops at the collapse row of an incapacitated agent |

Four things to keep in mind:

- **An incapacitated agent stays in the simulation.** It stays where it
  collapsed until the run ends, is never counted in `agents_evacuated` and
  is not sampled after its collapse row. The run ends when every mobile
  agent has left and no flow window is open: `end_reason` is
  `"all_mobile_left"`, the run is `"incomplete"` and `success` is `False`.
  `evacuation_time` is then the end of the loop, not an exit time. Read
  `metrics["last_exit_time"]` or the trajectory for exit times, as the
  [RSET how-to](howto-rset-ensemble.md) does
  ([#141](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/141)).
- **A deadlocked run stops early.** When every mobile agent inside has
  moved less than 0.03 m, net, over the last 100 s, the run stops at once
  with `end_reason` `"deadlock"`, `"incomplete"` and `success` `False`,
  instead of running to `max_simulation_time`. The rule is fixed and has no
  option. Incapacitated agents are not counted. The rule waits while any
  other agent is in pre-movement, at a waiting stage, idle until a decision
  gives it somewhere to go, or has a desired speed of 0, and for 100 s after
  such an agent starts to move; it also waits while a flow source can still
  spawn agents or an exit has yet to open. A crowd that stands still with
  nothing left to wait for, such as one whose only reachable exit has
  closed or whose `max_throughput` lets an agent through less often than
  every 100 s, can be reported the same way.
  `evacuation_time` is the detection time, not an egress time, and
  `metrics["deadlock"]` and the manifest `outcome["deadlock"]` list the
  stuck agents' count, the start of the window (`since_s`) and their
  positions. A working bottleneck, with some agents still moving, never
  fires the rule. pyFDS-Evac only reports the jam; it does not clear it
  (see [Known defects](limitations.md#known-defects)).
- **No FED is not zero FED.** If neither FED track ran, `fed_history` is
  `None`, `metrics` has no `fed_max`, and `--output-fed-history` writes no
  file. If only the heat FED ran, the FED history exists and its
  `fed_cumulative` column is all zero. Check `metrics["fed_enabled"]`, or the
  `FED is disabled` warning
  ([#137](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/137)).
- **The progress line counts planned agents.** With flow spawning it can show
  more agents than the final summary, which counts those actually spawned
  ([#279](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/279)).
