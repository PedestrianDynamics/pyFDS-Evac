---
title: "Scenario JSON"
weight: 8
---

A scenario is a `config.json` plus a `geometry.wkt` walkable area, in a
directory or a ZIP. This page lists the JSON keys that change a result, with
their defaults. The meaning of the model parameters is on the
[Models](/models/_index.md) pages; this page links there rather than repeating
the equations.

The keys are read by `load_scenario` and the JuPedSim set-up in
`simulation_init.py`. A key that is not listed here is either layout data for
[JuPedSim Web](https://app.jupedsim.org) (`config.ui_state`) or not read by
the run.

## Where scenario files come from

Scenario files are drawn in [JuPedSim Web](https://app.jupedsim.org) and
exported as a ZIP, or copied from an example and edited. The app does not
write the pyFDS-Evac keys (`routing`, exit schedules, `familiarity`, the
sign's `max_distance`); add them by hand after the last export.
[Create a scenario](howto-create-scenario.md) shows the three routes and how to
check the result.

## Top-level structure

```text
{
  "config": { "simulation_settings": { "simulationParams": {…}, "baseSeed": … } },
  "exits":         { "<id>": {…} },
  "distributions": { "<id>": { "coordinates": […], "parameters": {…} } },
  "checkpoints":   { "<id>": {…} },
  "waypoints":     { "<id>": {…} },
  "zones":         { "<id>": {…} },
  "journeys":      [ { "id": …, "stages": […] } ],
  "transitions":   [ { "from": …, "to": …, "journey_id": … } ],
  "journeys_v2":   [ { "id": …, "sequence": […] } ],
  "waypoint_routing": {…},
  "routing":       {…}
}
```

`journeys` and `transitions` are the stage graph that set-up builds on; a
journey needs its `transitions`
([#504](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/504)).
`journeys_v2`, as JuPedSim Web writes it, is converted into them only when
`journeys` is empty; see
[Create a scenario](howto-create-scenario.md#add-the-pyfds-evac-keys-last).
`waypoints` carry signs only.

## Simulation settings

Under `config.simulation_settings`.

| Key | Default | Effect |
|---|---|---|
| `simulationParams.max_simulation_time` | 300 s | The run stops here. An incapacitated agent keeps a run going until this time ([#141](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/141)). With `--fds-dir` it must not exceed the last FDS slice time by more than one output interval, unless `--allow-fds-horizon-hold` is given ([#340](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/340)). |
| `simulationParams.model_type` | `"CollisionFreeSpeedModel"` | The JuPedSim movement model. |
| `simulationParams.smoke_slice_height` | none (`--smoke-slice-height`, 1.6 m) | Absolute FDS slice height [m] for smoke, gases and sign legibility. `pyfds-evac --smoke-slice-height` overrides it; the run prints the value when it comes from here. `pyfds-evac init` writes the floor level plus `HUMAN_SMOKE_HEIGHT`. The GUI and TUI do not read it yet. |
| `baseSeed` | 42 | Random seed; `run.py --seed` overrides it. |

`simulationParams.dt` is not read: the JuPedSim step is 0.01 s, and the
trajectory is written every tenth step (10 frames/s).

### Social force model

Read when `model_type` is `"SocialForceModel"`. The symbols are those of
Helbing, Farkas & Vicsek (2000), Eqs. (1)–(3)
([doi:10.1038/35035023](https://doi.org/10.1038/35035023)); a missing key takes
JuPedSim 1.4.2's default.

| Key (`simulationParams.`) | JuPedSim parameter | Symbol | Unit | Default |
|---|---|---|---|---|
| `sfm_body_force` | `SocialForceModel(body_force=)` | *k* | kg s⁻² | 120000 |
| `sfm_friction` | `SocialForceModel(friction=)` | *κ* | kg m⁻¹ s⁻¹ | always 0, see below |
| `agent_strength` | `agent_scale`, per agent | *A*, agent term | N | 2000 |
| `sfm_obstacle_scale` | `obstacle_scale`, per agent | *A*, wall term | N | 2000 |
| `agent_range` | `force_distance`, per agent | *B* | m | 0.08 |
| `relaxation_time` | `reaction_time`, per agent | *τ* | s | 0.5 |

Negative, non-finite or non-numeric `sfm_body_force`, `sfm_friction` or
`sfm_obstacle_scale` stop the run with `ValueError`. JuPedSim 1.4.2 has
one friction for the agent and wall terms and applies the wall term with
the wrong sign
([jupedsim#1677](https://github.com/PedestrianDynamics/jupedsim/pull/1677)),
so friction is always passed as 0, also when `sfm_friction` is missing
([#635](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/635)).
A deck that declares `sfm_friction` above 0 gets a warning. The run
manifest records what JuPedSim received under `sfm`.

## Spawn areas: `distributions.<id>.parameters`

| Key | Default | Range | Effect |
|---|---|---|---|
| `number` | the first distribution's `number`, else 100 | ≥ 0 | Agents placed at the start. |
| `distribution_mode` | `"by_number"` | `by_number`, `by_percentage` | `by_percentage` fills the polygon to `percentage` (1–100, default 50). |
| `v0` | 1.25 m/s | — | Clear-air walking speed, for every movement model (FDS+Evac `VEL_MEAN`; 1.2 before). Every smoke, irritant and zone factor multiplies this value. |
| `v0_distribution` | `"constant"` | `constant`, `gaussian` | `gaussian` draws per agent with `v0_std`; draws are clipped to [0.1, 5.0] m/s. |
| `v0_std` | none | — | Spread of the Gaussian draw. |
| `radius` | 0.2 m | — | Body radius: packing, spawn spacing, and the `radius + 0.5` m arrival distance at a checkpoint. An agent leaves at an exit when its centre enters the exit polygon or comes within 0.03 m of it. |
| `radius_distribution` | `"constant"` | `constant`, `gaussian` | `gaussian` draws per agent with `radius_std`, clipped to [0.1, 1.0] m. |
| `radius_std` | none | — | Spread of the Gaussian draw. |
| `use_premovement` | constant 10 s when no pre-movement key is set, with a warning | `true`, `false` | Delay before the agent starts moving. Setting any pre-movement key, including `use_premovement: false`, turns the default off. |
| `premovement_distribution` | `"gamma"` | `gamma`, `lognormal`, `weibull`, `uniform`, `constant` | Distribution of the delay. |
| `premovement_param_a`, `premovement_param_b` | the preset of the distribution | — | Override the preset; the presets and their sources are in [Coming from FDS+Evac](coming-from-fds-evac.md#pre-movement-parameters). |
| `premovement_seed` | none | — | Separate seed for the pre-movement draw. When set, the pre-movement times are the same for every run seed. |
| `premovement_offset_s` | none | ≥ 0 s | A fixed delay added to every agent's drawn pre-movement time, so nobody starts earlier. It stands for FDS+Evac's detection time; `pyfds-evac init` writes it. It needs `use_premovement: true`, and without it the run stops with a `ValueError`. Applies with and without `journeys`; ignored with flow spawning. |
| `use_flow_spawning` | `false` | — | Add agents over time instead of at the start (no pre-movement then). |
| `flow_start_time`, `flow_end_time` | 0 s, 10 s | — | Window of flow spawning. |
| `familiarity` | `"full"` | `full`, `discovery`, or a probability in [0, 1] | What the agents know of the exits at the start; see [Models › Wayfinding](/models/wayfinding.md). |
| `entrance` | none | an exit id | One exit, reachable from the spawn area, that the agents know from the start. |

`desired_speed`, `desired_speed_distribution` and `desired_speed_std` are
aliases of `v0`, `v0_distribution` and `v0_std`. An alias set alone is used
as its `v0*` key. An alias and its `v0*` key with the same value are
accepted; with different values the run stops at the start with a
`ValueError` that names the distribution and both keys
([Troubleshooting](troubleshooting.md#errors)). This check applies to the
scenario JSON; `Scenario.set_agent_params()` in Python lets `desired_speed`
win instead
([#586](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/586)).

While an agent waits out its pre-movement time, the smoke update skips it, so
it starts at its full clear-air speed. An agent that reaches its FED threshold
while still waiting walks off when its pre-movement ends
([#145](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/145)).

## Exits: `exits.<id>`

| Key | Default | Effect |
|---|---|---|
| `coordinates` | required | Exit polygon. |
| `enable_throughput_throttling`, `max_throughput` | `false`, 0 | Cap the removal rate at the exit: an agent whose centre is inside the exit polygon, or within 0.03 m of it, is removed only if at least 1/`max_throughput` s have passed since the last removal there; otherwise it waits. A throttled exit is steered directly. This caps the rate; it does not model door flow. A `max_throughput` of 0 disables the cap. |
| `capacity_agents_per_s` | `routing.default_exit_capacity` (1.3 agents/s) | Exit capacity used to estimate queue time when routes are priced. |
| `open_from_s` | none (open from the start) | The exit opens at this time [s], a finite number ≥ 0. |
| `closed_after_s` | none (never closes) | The exit closes at this time [s], a finite number ≥ 0 and greater than `open_from_s`. |
| `sign` | an omni-directional sign at the exit's centre, `c` = 3 | The sign agents read; keys below. |

An exit with `open_from_s` or `closed_after_s` is open while
`open_from_s` ≤ *t* < `closed_after_s`
([#373](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/373)). While
it is closed:

- it removes nobody: an agent standing in it waits there;
- routes are ranked without it, both the opening choice and every
  re-evaluation, and it is no target for exploring or wandering. An exit is
  judged by whether it is open at the time of ranking, not at the time the
  agent would arrive;
- an agent whose route ends at it re-evaluates at the next reroute check
  (every second), whatever `--reroute-interval` says, and takes the best open
  exit it knows. The switch is logged with the reason `exit_closed`. An agent
  that knows no open exit is not told of another one. It heads for a known
  node it has not visited, or else wanders over the nodes it knows; an agent
  that knows only its spawn area and the closed exit has neither, so it keeps
  its route and waits at the closed exit.

When an exit opens, nobody is made to re-decide: an agent takes it at its next
regular re-evaluation, up to `--reroute-interval` later.

A schedule needs rerouting: a run with a scheduled exit and
`--no-enable-rerouting`, `--smoke-blind` or `--replay-exits` stops with an
error, as does an agent that walks a JuPedSim journey instead of a routed path
(a spawn area with no journey in a scenario that has journeys). Without a
schedule nothing changes.

### Signs: `sign`

Exits, checkpoints and waypoints can carry a `sign`. A node without one gets
an omni-directional sign at its position with `c` = 3, so every exit is
subject to smoke-dependent legibility.

| Key | Default | Effect |
|---|---|---|
| `x`, `y` | required in an authored `sign` | Sign position [m]. |
| `alpha` | none (omni-directional) | Bearing the sign faces [°], clockwise from north (+y); the sign is readable only from the side it faces. |
| `c` | 3 | The constant *C* of the legibility law *V* = *C*/*K*. |
| `max_distance` | `--max-sign-distance` (30 m) | Farthest reading distance for this sign, even in clear air. |

The legibility rule is on [Models › Wayfinding](/models/wayfinding.md).

## Checkpoints and zones

| Key | Object | Default | Effect |
|---|---|---|---|
| `coordinates` | both | required | Polygon. |
| `speed_factor` | both | 1.0 | Multiplies the speed of agents inside; clipped to [0, 3]. A negative or non-numeric value becomes 1.0. |
| `waiting_time` | checkpoint | 0 s | Time agents wait at the checkpoint. |
| `waiting_time_distribution`, `waiting_time_std` | checkpoint | constant, 1.0 s | `"gaussian"` draws the wait per agent. |
| `enable_throughput_throttling`, `max_throughput` | checkpoint | `false`, 1.0 | Cap the flow through the checkpoint. |

## Journey splits: `waypoint_routing`

A journey in which a checkpoint has more than one outgoing transition needs
the shares of agents that take each branch:

```text
"waypoint_routing": {
  "<checkpoint id>": {
    "<journey id>": {
      "destinations": [ { "target": "<stage id>", "percentage": 60 }, … ]
    }
  }
}
```

| Key | Default | Effect |
|---|---|---|
| `destinations[].target` | required | A stage the journey's transitions lead to from this checkpoint. Every such stage must be listed. |
| `destinations[].percentage` | 0 | Share of the agents sent to `target`. The sum must be greater than 0. |

Without it, or with a target missing, the set-up stops with `Explicit
routing required for <checkpoint> in <journey>` or `Explicit routing for
<checkpoint> in <journey> is incomplete` (`_create_journeys_with_percentages`
in `simulation_init.py`). The shares set the authored journey only. With
rerouting on, the default of `run.py`, the route-cost model picks each
agent's exit: in `assets/t_junction` with 40 agents, shares of 99/1 and 1/99
both sent all 40 to the nearer east exit, while with `--no-enable-rerouting`
99/1 sent all 40 west. JuPedSim Web does not write this key.

## Route choice: `routing`

The `routing` block sets the route-cost model. Its keys, defaults and the
constants that no key can set are listed in one place,
[Models › Routing › Parameters](/models/routing.md#parameters).
`cost_model` must be exactly `"gate"` or `"additive"` (lower case); without
the key it is `"gate"`. Any other value stops the run with a `ValueError`
that lists the two names, also with `--no-enable-rerouting`, since the first
exit choice uses the cost model too.

The `routing` keys `alpha`, `beta`, `min_speed_factor` and
`base_speed_m_per_s` only estimate travel time when a route is priced. They
do not change how fast agents walk.

## Not in the JSON

Some parameters exist only in Python, as fields of a config object:

- the smoke-speed law and its parameters (`SmokeSpeedConfig`: `speed_law`,
  `alpha`, `beta`, `min_speed_factor`, `visibility_factor_c`); a configured run
  always uses the Lund law with the defaults on
  [Models › Smoke speed](/models/smoke-speed.md#parameters);
- the routing constants `impassable_extinction_threshold` and
  `fed_return_margin` (`RouteCostConfig`), and `exit_switch_anchor`
  (`RerouteConfig`).

Tracking issue for this reference:
[#119](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/119).
