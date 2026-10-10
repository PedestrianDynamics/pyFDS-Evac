# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Upgrading

- A deck with a journey from a distribution to a stage that no entry in
  `transitions` names now fails to load (#504): `Journey(s) 'J' list
  stages but no entry in 'transitions' names them, so their agents
  would never move: ...`. Such a deck used to run to
  `max_simulation_time` with every agent on that journey standing
  still. Add the transitions between the
  journey's stages, or, for an editor export that also carries
  `journeys_v2`, set `"journeys": []` so the editor's journeys are used.
  No shipped deck has this shape.

- Results change for agents whose radius is not 0.2 m (#408): the
  runtime now reaches a stage target within the agent's own radius plus
  0.5 m, and keeps next-stage and reroute target points 0.8 times the
  agent's own radius from a stage's edge; both used 0.2 m for every
  agent. This includes decks imported by `pyfds-evac init` since #699
  (0.12–0.16 m) and decks with a sampled `radius_distribution`. Of the
  rerouting goldens (darwin-arm64) only the six `tj_*` decks
  (`t_junction`, 0.15 m, one checkpoint) move: evacuation times change
  by -0.36 to +1.11 s, all 30 agents still get out. The
  `heat_default` verification baseline (0.15 m) moves by up to 12 mm in
  `x`/`y`, its FED values do not. Clear-air runs of the shipped decks:
  `station_fahy` (Gaussian radius, seed 420) still gets 331 of 333 out
  at 600 s together with #709 below, on other trajectories (330 with
  this change alone); `l_corridor` and `schroeder2015_route` end
  0.03 s later;
  `t_junction` and `schroeder2020_room` end with the same counts and
  times; decks with 0.2 m are unchanged. In the first FDS case
  (`t_junction`, 2 MW PVC fire, seed 42) 99 of 150 agents get out
  instead of 100, FED max 0.23 instead of 0.24.

- Decks with journeys and an exit `capacity_agents_per_s` now price
  that exit's queue with it (#394), as decks without journeys did;
  it was priced at `routing.default_exit_capacity` (1.3 agents/s).
  Only runs with `routing.w_queue` > 0 change. No shipped deck sets
  `capacity_agents_per_s`, so no golden or asset result moves.

- Gaussian radii (`radius_distribution: gaussian`) are clipped to the
  radius placement spaces agents for, b = min(max(`radius` + 3 ×
  `radius_std`, 0.1), 1.0) m, instead of [0.1, 1.0] m (#709). A draw
  beyond mean + 3σ (0.135 % of agents) becomes b; the draws, the other
  radii, every v0 and every position stay the same for a seed. Of the
  shipped decks only `station_fahy` uses a Gaussian radius: at its
  default seed 420 one radius goes from 0.2656 to 0.26 m, and the run
  can diverge from that agent's first contact on. A deck with
  `radius` + 3 × `radius_std` below 0.1 m is now spaced for 0.1 m.

- `fed_max_route` in the route-cost history rises for an agent behind
  its route's origin node in runs with a FED field (#171). Under
  `additive` the route cost rises by `w_fed` times that change, so
  near-tied choices can change. Agents on or ahead of the origin, and
  runs without a FED field, are unchanged.

- Route history (`--output-route-history`, `result.route_history`):
  `smoke_reroute` now counts only the exit changes smoke caused (#92).
  Other changes of exit, labelled `smoke_reroute` before, are
  `fed_reroute`, `exit_opened`, `learned_exit`, `congestion`,
  `shorter_path`, `exit_unreachable` or `resume`. Scripts that count
  `smoke_reroute` as "any change of exit" must count these too.
  Trajectories, exit choices and times are unchanged.

- Results of decks with checkpoints change (#69): checkpoint arrivals
  come earlier, and crowd interaction then moves individual agents
  either way. In the first FDS case (`t_junction`, 2 MW PVC fire,
  seed 42) 100 of 150 agents get out instead of 93; its clear-air run
  stays at 144/150. Decks without checkpoints (all `init` imports, the
  ISO decks, exit-only decks) and `station_fahy`, whose checkpoint
  circles lie inside the 0.7 m reach disc, are unchanged.

- `pyfds-evac init --check` can now fail (✗, exit 3) on a deck it
  passed: a slice that FDS culls no longer counts, and a `PBZ` slice
  that also sets `PBX` or `PBY` is a line the run does not read (#705).
  No tracked deck changes. `import_report.json` gains
  `recommendations.slices_dropped`.

- Scripts that parse `import_report.json`: `nearest_pbz` under
  `recommendations.slices` is the z the run ranks the slice on, the grid
  node FDS writes it at, no longer the deck's z (#687). On a 0.5 m grid
  a deck `PBZ=1.6` now reads 1.5.

- `pyfds-evac init` now writes a `radius` for FDS+Evac decks: the mean
  torso radius of each `&PERS` type, 0.12–0.16 m (Adult 0.15, Male
  0.16, Female 0.14, Child 0.12, Elderly 0.15), instead of leaving the
  0.2 m default (#699). Results of re-imported decks change; scenarios
  imported before keep 0.2 m until they are imported again. Some
  imported decks, such as `HUT_Library` and `imo/CompTest9a`, can still
  deadlock at doors and narrow gaps in some seeds (#706).

- Results change for runs with same-exit `better_path` switches, and
  for any rerouting run in which an agent switches to a route that
  reaches its current target by a detour (#445): the agent now walks the
  detour. On the golden decks only `better_path` switches are affected.
  On the golden deck `ft_full_gate_detour` (darwin-arm64) the
  evacuation time goes from 49.43 s to 54.92 s and the `better_path`
  rows of `route_history.csv` from 24 to 17.

- A scenario with an exit that opens or closes on a schedule
  (`open_from_s`, `closed_after_s`) now runs with `--smoke-blind` and
  with `--no-enable-rerouting` (and `run_scenario` without a
  `RerouteConfig`) instead of stopping with "need rerouting" (#395).
  Imported FDS+Evac decks with `TIME_OPEN` or `TIME_CLOSE`, such as the
  `HUT_Library` decks, the `OpenFloorOffice` decks and `DoorAlgo2_A`,
  run without rerouting. Such runs now return and write a route history
  (`--output-route-history`) holding the rows of these re-choices:
  `exit_closed`, `initial` (exit not open yet) and `default_route`.
  Runs without a schedule are unchanged. Runs with rerouting and a
  schedule move the same, and an exit that has not opened yet gives the
  same rows as before, but rows for an exit that has closed
  (`closed_after_s`) change in two ways: a closure row of an agent that
  followed its default route has `old_exit` = the closed exit instead
  of empty, and a closure onto a gate fallback route is labelled
  `exit_closed` instead of `fallback`.

### Added

- The FDS coverage warning names the frame (#26): when part of the
  walkable area lies outside the FDS slices, it ends with the bounds of
  the walkable area and of the FDS domain. When more than half of it
  lies outside and swapping x and y, shifting the walkable area onto the
  domain, or both would leave at most 1 % of it outside, it names that
  as a possible explanation
  (`With x and y swapped, ...`, `Shifted by (dx, dy) m, ...`). The run
  manifest records the end-of-run count of samples outside as
  `fds_outside`. Results are unchanged; outside the slices agents still
  read ambient air and clear sight.
- `pyfds-evac --scenario DIR` prints one warning before the run when
  `DIR/import_report.json` says `runnable: false`, with the report's
  `not_runnable_reasons` (#701): `pyfds-evac: warning:
  import_report.json marks this scenario not runnable: ...`. The run
  continues, since the folder may have been fixed by hand after `init`.
  A missing or unreadable report prints nothing.
- `RouteCostConfig.fallback_rule` (#696), an experimental code-level
  option with no scenario key, CLI flag or GUI control. `"tau"` (the
  default) keeps the lowest-tau rule when every route is refused.
  `"hold"` keeps the agent's exit between refused routes, unless the
  current route must be fled (#128). Default results are unchanged.
  The run manifest's `cost_config` gains `"fallback_rule": "tau"`.
  #696 stays open as a documented finding: on `t_junction` the default
  still sends agents past the burner.

### Changed

- In a scenario with neither journeys nor transitions, a spawn area
  whose agents JuPedSim cannot all place raises `SpawnCapacityError`, a
  `ValueError`, with JuPedSim's error as `__cause__`, instead of
  `jupedsim.distributions.AgentNumberError` (#702). Code that caught
  `AgentNumberError` must catch `SpawnCapacityError` or `ValueError`.

- `import_report.json` gives, per `&PERS`, the FDS+Evac three-circle body
  (R_d, R_t, R_s) and the radius taken from it, instead of "body size not
  mapped". A `&PERS` that sets `DIAMETER_DIST` gets 0.5 · `D_TORSO_MEAN`
  · mean diameter / `DIA_MEAN`; one with only a positive `DIA_MEAN`, a
  constant body in FDS+Evac, gets max(`DIA_MEAN`/2, 0.05) ·
  `D_TORSO_MEAN` / `DIA_MEAN`; any other gets no radius and a warning
  (#699). `DoorFlowExample.fds` now imports as runnable: its 100 agents
  fit the spawn area at 0.15 m, not at 0.2 m.

### Fixed

- `load_scenario` and the run refuse a journey that no entry in
  `transitions` names, with an error naming the journey (#504). Agents
  on it had no route and stood still, without a warning; the
  `--print-summary`, `--export-only` and GUI upload paths now stop on it
  too. Only journeys that place agents are checked: one that lists a
  distribution of the deck and a stage to walk to. A journey of exits
  only, or of a distribution only, places nobody and needs no
  transitions; decks without distributions use no journeys.

- The per-agent steering state stores the agent's radius (#408). It was
  read with a 0.2 m default but never written, so stage reach
  (radius + 0.5 m of the target point) and target clearance used 0.2 m
  whatever the agent's radius.

- The set-up with journeys passes each exit's `capacity_agents_per_s`
  to route pricing (#394). It was dropped, so the queue term priced
  every exit of a journey deck at the 1.3 agents/s default.

- A Gaussian radius draw no longer exceeds the radius placement spaced
  for (#709): agents could start overlapping. The spacing bound now has
  one definition, `agent_params.max_agent_radius`, read by the run and
  by `pyfds-evac init`'s capacity check.

- Scheduled exits work in runs without rerouting (#395). At each
  one-second check, only an agent whose route ends at a closed exit, or
  at one not open yet, chooses again, once for each closure, scored as
  its opening choice: on the map it
  holds, without the queue term, with the smoke at that time, or in
  clear air when smoke-blind. An agent that knows no open exit takes
  the default route to the nearest open exit on foot; with every exit
  closed it waits. Nobody re-decides when an exit opens, which differs
  from FDS+Evac, whose door choice keeps running. A flow-spawned agent
  on a JuPedSim journey is refused in these runs too.

- A checkpoint now counts as reached when the agent's centre is inside
  its polygon, as well as within the agent radius plus 0.5 m of its
  random target point (#69). An agent deep inside a large checkpoint,
  such as the 3x3 m boxes of `t_junction` and `l_corridor`, used to
  walk on to the target point first. Arrival is never later than
  before on the same trajectory. Exits keep their polygon rule; spawn
  areas walked to on patrol and speed zones keep the point rule. An
  agent that spawns inside a checkpoint on its route reaches it on its
  first step: in the `fed_incap_*` decks 4 m² of each of the four
  first 4x4 m checkpoints lies in the spawn area. The unused
  `inside_since`, `reach_penetration` and `reach_dwell_seconds`
  entries of the per-agent steering state are removed.

- Reading FDS output no longer writes to or deletes from the FDS
  directory (#716). fdsreader 1.11.7 writes `<CHID>.pickle` next to the
  `.smv`, deletes a pickle it cannot read, and deletes it when caching is
  off, so runs, the GUI smoke view, `--inspect-fds` and the scripts
  changed the user's case folder. pyFDS-Evac now opens every case, also
  through fdsvismap, with fdsreader's cache off and its pickle path
  redirected, and restores both settings afterwards. An existing pickle
  is left as it is and no longer read; each open parses the `.smv` and
  slice headers again, 0.1–0.4 s on a 64-mesh case with 768 slice
  files (0.01 s from the pickle). Results are unchanged. fdsreader is
  now pinned to `>=1.11.7,<1.12`, the versions this was checked on.

- A route switch is labelled by what caused it, not `smoke_reroute` for
  every change of exit (#92). An agent that switches in clear air to a
  nearer exit, or to one it has just learned, logged a smoke reroute.
  Outputs lists the values; Routing in practice lists them with their
  order of precedence and how a cause is credited.

- An agent now leaves a route whose predicted dose is lethal, as the
  routing docs promise (#128). Under the gate, a route over both the FED
  and the `tau` limit reports `tau ...` and lost the must-flee bypass;
  when every route was refused, a lethal current exit with the lowest
  `tau` was held. Must-flee now reads the limits a route breaks, the new
  `RouteCost.violation_kinds` (default `()`), instead of the rejection
  reason, and the all-refused fallback orders a route the agent must
  flee behind every route it need not flee. The `rejection_reason` text
  and the CSV outputs are unchanged. No shipped deck changes: the
  largest route FED in their outputs is 0.565, below the limit.
- An agent behind its route's origin node is charged the dose of its
  walk back to the origin (#171). The first segment's dose is charged
  pro rata to what is left of it, a share capped at 1, so that stretch
  carried no dose although its smoke and time were counted. It is now
  charged at the mean FED rate sampled along it at the decision time,
  over the walk's pace; the candidate search weighs the walk to each
  first node the same way.
- `pyfds-evac init --check` drops a slice that FDS culls, with the exact
  bounds of FDS `READ_SLCF`: outside every fire `&MESH` (all of `PBX`,
  `PBY` and `PBZ` count), or a `MESH_NUMBER` naming a mesh that does not
  hold it or no fire mesh. The check gives the status it gives without
  that slice and prints `dropped &SLCF line N (…): REASON, so FDS writes
  no such slice`; before, it ranked the slice at the deck's z and could
  pass (#705). The cull applies to `&TRNZ` decks too. `MESH_NUMBER`
  counts the fire meshes only, as the FDS 6.7.6 fire run does, and
  `PBX` or `PBY` with `PBZ` is a vertical line, as fdsreader reads it.
  On a deck with evacuation meshes (FDS 6.7.6), a horizontal slice that
  only touches a mesh in x or y is reported as unreadable: FDS keeps it
  there at zero width, and fdsreader then reads no horizontal slice.
- The deck parser computes `MULT` copies as FDS does, `(XB + DX0) +
  I*DX`, so the check compares the doubles FDS uses (#705). The
  walkable area, exits and obstructions use these coordinates rounded to
  1e-9 m, so faces that `MULT` copies leave a few ulp apart coincide:
  such a seam between mesh rows could split the walkable area in two and
  leave no agents placed. No tracked deck's `init` output changes. The
  rounding closes such seams up to coordinates of about 2e6 m; at
  larger ones, such as UTM northings (~5e6 m), one ulp exceeds 0.5e-9 m
  and a seam can remain.
- `pyfds-evac init` reads a deck as an FDS+Evac deck only when it has a
  `&MESH` with `EVACUATION=.TRUE.`. An `&EVHO` in a plain deck is cut out
  of the derived walkable area and keeps the `SURF_ID='OPEN'` exits;
  t_junction with an `&EVHO` lost both exits before (#688). Other
  FDS+Evac namelists in a plain deck are reported as ignored.
- `pyfds-evac init --check` ranks slices at the z the run ranks them on:
  the grid node FDS writes each at (the nearest cell face, the top of
  the cell for `CELL_CENTERED`, only in `MESH_NUMBER` if given), the
  lowest across meshes, as fdsreader reads it. On tracked output at
  z = 2.0 m it named PBZ 1.6 where the run reads PBZ 2.5 (#687). Lines
  print that z, with the deck's z when it differs.
- On a plain deck, `pyfds-evac init` reports an `&EVHO` without `XB` as
  invalid, not as off the floor, and names the `&EVHO` records when they
  cover the whole walkable area, which ended in exit 1 with only
  "walkable area (derived:deck) is empty". The fire-surface advice also
  offers an `&EVHO` over the surface, in a copy of the deck (#688).

- In a scenario with neither journeys nor transitions, a spawn area
  whose count is within the capacity estimate but where JuPedSim cannot
  place every agent, for example a narrow area, stops `pyfds-evac
  --scenario` with one line, exit 1, instead of an `AgentNumberError`
  traceback (#702): `pyfds-evac: error: Distribution '<id>': could not
  place the N requested agents (...). The capacity estimate ~C is an
  upper bound. ...`. Results do not change.

- In a scenario with journeys, a spawn area whose agents JuPedSim
  cannot all place stops `pyfds-evac --scenario` with the same line and
  exit 1, instead of a traceback ending in `Exception: CRITICAL: Failed
  to place agents ...` (#508). `run_scenario` raises
  `SpawnCapacityError` with JuPedSim's error as `__cause__`. An agent
  that JuPedSim refuses to add at set-up, with or without journeys,
  stops the run with `pyfds-evac: error: Distribution '<id>': JuPedSim
  could not add an agent to the simulation (...).` and exit 1;
  `run_scenario` raises `AgentInsertionError`, a `RuntimeError`.
  Results do not change.

- `pyfds-evac --scenario DIR --export-only`, with or without
  `--print-summary`, reported a spawn area that asks for more agents
  than its capacity estimate as `Agents: ~N` and exited 0. It now prints
  the run's line, `pyfds-evac: error: Distribution '<id>': requested N
  agents but area can hold at most ~C. ...`, and exits 1 (#508). It
  counts as the run does: the stored `number` in every
  `distribution_mode`, and the whole walkable area for a deck without
  spawn areas. A count within the estimate that JuPedSim cannot place is
  still found by the run only.

- Two spawn areas that overlap but are not the same polygon, with or
  without journeys, could place agents of one within a body width of
  the other's, and the run stopped with `AgentInsertionError` (#402).
  An area that overlaps one placed before it, in deck order, is now
  seeded around the agents already there, so agents of the two keep
  `distance_to_agents` (twice the larger radius) apart. The area placed
  first and every area that overlaps none keep their positions; the
  counts and capacity estimates do not change. When the agents already
  placed cut the free part of an area into pieces, the agents are shared
  among the pieces by their capacity; when the pieces cannot seat them
  all, or nothing is left free, the run stops with `SpawnCapacityError`.
  Flow-spawned agents keep the same spacing, see #710 below.

- A flow-spawned agent (`use_flow_spawning`, `flow_schedule`) now keeps
  twice the larger radius from every agent already in the run, as the
  agents of overlapping spawn areas do (#710). It used to be checked
  only by JuPedSim's `add_agent`, which refuses closer than the model's
  own limit, and measures to where the others stood at the start of the
  last time step: the sum of the two radii for the collision-free speed
  and anticipation velocity models, the radius of the agent added for
  `SocialForceModel`, an ellipse spacing for
  `GeneralizedCentrifugalForceModel`, nothing for `WarpDriverModel`. A
  flow of 0.15 m agents into an area where 0.3 m agents wait could
  enter 0.48 m from one of them instead of 0.6 m, and under
  `WarpDriverModel` on top of one. A flow that finds no free position
  waits as before; instead of a `Flow spawn attempt failed` line at
  every step it is counted in
  `metrics["flow_spawns_deferred"]`, and the run ends with one line per
  such flow: `Flow spawning: '<id>' found no free position at N steps
  between t=A s and t=B s; K of its M agents did not enter`. A
  candidate that JuPedSim refuses anyway is still handed to it, since a
  refusal uses up an agent id; so runs where no agent entered too close
  are placed as before, ids included, except under
  `GeneralizedCentrifugalForceModel`, whose refusal is not mirrored and
  whose agents can be numbered differently. `l_corridor` and the three
  flow configs of `t_junction` (seeds 1 and 42) add the same agents at
  the same times and positions, with the same ids and metrics, but for
  one agent of `t_junction/config_full.json` under seed 42, run in clear
  air (without its fire): at t = 222 s it entered 0.296 m from another agent, where 0.3 m is kept now, and
  enters at the next free position. Of the rerouting goldens only
  `ft_full_gate_detour` and `ft_full_additive_detour`
  (`SocialForceModel`, a 0.2 m flow) move: 5 of their 30 agents entered
  0.19 to 0.37 m from another, now none closer than 0.4 m; all 30 still get
  out, at 58.18 s instead of 54.39 s and at 48.33 s instead of 48.35 s.
- An applied route is walked as it was priced (#445). A route is priced
  from the node the agent last left, through the node after it. When
  the agent's current target was further along the new route, the agent
  kept walking to it: it stayed on a leg the gate had refused
  (τ > `tau_max`), and the same `better_path` switch was logged again at
  every re-evaluation. The agent now heads for the node after the one it
  last left. This holds for every kind of switch, exit changes included.

### Documentation

- Model comparison: the FDS+Evac body is a torso circle R_t and two
  shoulder circles R_s inside an enclosing circle R_d; there is no head
  circle (#699).

## [0.4.0] - 2026-10-09

### Upgrading

- Agents that know no exit follow the default route instead of
  exploring. Set `"no_known_exit": "explore"` to keep the 0.3.1
  behaviour; it needs rerouting on (#610).
- Runs with route foresight (`anticipate`, on by default) in a smoke
  field that changes in time give different results (#650). Between
  two refused routes `fallback_switch_margin` compares `tau`, and a
  switch straight back waits `fallback_return_lockout_s` (10 s) (#458).
- A spawn area without `number` places `simulationParams.number`, else
  10 agents, not 100 (#567). SocialForceModel runs read
  `sfm_body_force` as the body force and pass friction as 0 (#611,
  #635). `VisibilityModel.clear_air()` uses a 0.25 m grid; pass
  `cell_size_m=0.5` for the old one (#115).
- Spawn values out of range, booleans and conflicting `v0` aliases stop
  the run with a `ValueError` that names the key (#612, #649).
- `pyfds-evac --scenario` reads `simulationParams.smoke_slice_height`;
  GUI, TUI and Python runs do not apply it (#632).
- Scripts that parse the output: `Route switches: N` is now
  `Route history rows: N`; the exit history has a column `exit_in_map`;
  the route history has rows with reason `default_route`, and a first
  choice is `initial`, not `smoke_reroute` (#610).
- `scripts/generate_walkable_from_fds.py` takes only `-o` and
  `--z-band`, whose default is now the evacuation-mesh slab; its other
  options are removed (#505).
- Vismap caches are rebuilt once (format 6, #510).

### Added

- `pyfds-evac init DECK.fds` starts a scenario from an FDS deck. It writes
  `config.json`, `geometry.wkt` and `import_report.json` to
  `<deck stem>_scenario/` next to the deck (`-o DIR` picks another folder),
  prints a short summary and the next steps, and exits 0 when runnable, 3
  when written but not runnable or an input was dropped at error level, and
  1 on an error, with nothing written (#605, part of #606, #632).
  - An FDS+Evac deck keeps its `&EXIT`, `&DOOR`, `&EVAC`, `&EVHO`, `&ENTR`
    and `&PERS` records for one floor. Detection plus reaction becomes one
    pre-movement delay with the same mean and variance, and no agent
    starts before the earliest FDS+Evac start.
  - A plain FDS deck gets exits from `SURF_ID='OPEN'` vents on the outside
    of its meshes, or from `--exit`, and a flagged placeholder of 100
    agents unless `--agents` is given.
  - `import_report.json` lists every input that was imported, inferred,
    approximated or dropped, with its deck line; `-v` prints all of it.
  - The walkable area is derived inside the package, so `init` works from
    an installed wheel: the union of the floor's mesh footprints, whose
    edge is a wall, minus the `&OBST` records in the walking band less
    their `&HOLE` cuts. Only the parts that hold a spawn area, or without
    one an exit, are kept, and `import_report.json` lists the others.
    `--walkable FILE.wkt` replaces the derived polygon.
    `scripts/generate_walkable_from_fds.py` is a thin wrapper that writes
    the same polygon. The script now takes only `-o` and `--z-band`, an
    absolute band whose default is the evacuation-mesh slab or 0.1 to
    1.8 m above the lowest mesh; `--half-cell`, `--min-hole`, `--plot`
    and `--report` are removed, and the polygon follows the importer's
    rule (#505).
  - A plain deck's floor is made of the meshes that reach the walking band;
    a mesh of another storey is reported, not joined. An `&EVAC` area is
    clipped to the walkable area before its agents are shared out.
  - A spawn area that asks for more agents than the run admits (the
    runtime's packing estimate) makes the scenario not runnable, with the
    area, the capacity, the requested number and what to change.
  - An FDS+Evac deck's walkable area is the union of its floor's main
    evacuation meshes, whose boundary is a wall; only `&EXIT` and `&DOOR`
    records leave it (`walkable.source` is `derived:evac-mesh`). Touching
    evacuation meshes of one floor are reported, a `COUNT_ONLY` exit is
    listed as a counter, and a point or line `&EVAC` is named as the reason
    when no agents can be placed (#672).
  - A point or line `&EVAC` becomes a 0.6 m band across its zero-width
    axis (a 0.6 m square for a point), clipped to the walkable area; its
    agents are placed at random in it, and `import_report.json` records the
    expansion per group as `zero_width_expansion` (#675).
  - An `&EXIT` or `&DOOR` keeps the deck's position; where FDS+Evac would
    move it to its evacuation grid, `import_report.json` gives that
    position as `fds_evac_segment`. A dropped exit's message says whether
    its strip is empty (with the distance) or below the 0.1 m minimum width,
    and a deck whose every exit is below it is named as using exits only
    as flow-field targets (#673).
  - `--floor MESH_ID` imports another floor of an FDS+Evac deck,
    `--floor-z Z` sets a plain deck's floor level (default: the lowest
    mesh z), `--z-band LO HI` the height band whose obstructions block
    walking, `--exit-depth D` the depth of an exit strip on the room side
    (default 0.5 m), and `--no-fds` leaves `--fds-dir` out of the printed
    run command.
- `pyfds-evac init DECK.fds --check` checks a deck before FDS runs and
  writes nothing (#604). At the smoke slice height `init` writes, with the
  run's selection rule (horizontal slice, nearest z, first declared on a
  tie), it fails (exit 3) when the extinction-coefficient slice (no
  `SPEC_ID` or `SPEC_ID='SOOT'`), a CO, CO2 or O2 volume-fraction slice, or
  `&TIME T_END` is missing; vertical slices do not count. It reports the
  optional FED gases, `TEMPERATURE` and `INTEGRATED INTENSITY` slices, the
  effective `DT_SLCF` and absent simple-chemistry yields. Exit 1 when the
  deck cannot be read. `--smoke-slice-height Z` checks another height.
  - A plain `init` runs the same check after choosing the floor, prints
    it (also when the walkable step then fails) and records it in
    `import_report.json` (`recommendations.slices`, additive keys, and
    `recommendations.slice_check_ok`). It never changes `config.json` or
    the exit status. The check replaces the old slice listing, which read
    `PBZ` only and counted `TEMPERATURE` as needed.
- Scenario key `distributions.<id>.parameters.no_known_exit`: what an agent
  does while no exit is reachable in its map. `default_route` (default, the
  FDS+Evac counterpart) follows the journey, or without one the exit nearest
  on foot; `explore` (frontier, patrol), `return` and `stay` are opt-in and
  never walk to a stage absent from the map. The opt-in modes need rerouting
  and are refused with `--smoke-blind`, before a CLI, GUI or TUI run (D33,
  #610, #91).
- Exit history rows carry `exit_in_map`, and the run metrics count
  `agents_left_by_unknown_exit`, the agents that left by an exit absent from
  their map. `pyfds-evac`, `run.py` and the GUI log print `Agents that
  left by an exit not in their map: N` when N is above 0 (#610).
- The route history gains the reason `default_route`: an agent with no
  known exit gets one row at spawn with the exit it is sent to. Outputs
  and Routing in practice list the reason (#610).
- `tests/test_init_deck_sweep.py` runs the deck importer of
  `pyfds-evac init` on the 227 tracked decks (the FDS+Evac guide decks,
  the `assets/` and `artifacts/` decks) and pins each deck's exit status,
  walkable area, exit and agent counts, reason and `config.json` hash in
  `tests/init_decks.tsv`, and its exit polygons in
  `tests/init_deck_exits.json` (#606).
- `--force` lets `pyfds-evac init` overwrite an output folder that holds a
  `config.json` it did not write; without it, such a folder is refused
  (#632).
- Scenario key `simulationParams.smoke_slice_height` [m]: the absolute FDS
  slice height of a run. `pyfds-evac init` writes the floor level plus
  `HUMAN_SMOKE_HEIGHT`. `--smoke-slice-height` overrides it; a run that
  samples elsewhere logs a warning. A bad value stops the run with a
  one-line error (#632).
- Scenario key `distributions.<id>.parameters.premovement_offset_s` [s]:
  a fixed delay added to every drawn pre-movement time, with and without
  journeys. It needs `use_premovement: true` (#632).
- The 182 input decks of the FDS+Evac guide in `assets/fds_evac_guide/`,
  copied unmodified from tkorhon1/FDS-Evac-Guide at a pinned commit, as
  reference input for the deck importer. They are GPL-3.0-only and are
  excluded from the wheel and the sdist. A test fails when a deck is
  changed, added or removed (#633).
- `REUSE.toml`, `LICENSES/` and `NOTICE` declare the license of every
  file: MIT by default, GPL-3.0-only for the guide decks and the NIST
  software notice for `materials/evac.f90`. CI checks this with
  `reuse lint` (#633).
- A clear-air visibility build logs a warning when its cell size is not
  smaller than the thinnest wall of the walkable area, with the wall's
  estimated width and location: such a wall may hold no cell centre and
  let sight through. The check is a heuristic: it is meant to find walls
  attached to the outer boundary and thin parts of larger obstructions,
  and to pass over rounded corners, bevels and wedge tips. The run's
  visibility settings record the width and the verdict as `thin_wall_m`
  and `thin_wall_warning`; `--show-config` predicts both from the
  scenario's geometry with the same function, prints them as resolved
  values and lists the warning under "Setup warnings". No warning does
  not prove that every wall blocks sight: parts shorter than one cell are
  not reported. A junction of walls of different widths is measured per
  wall, and the width reported is that of the thinnest wall (#115).
- `scripts/release_check.sh --keep` keeps each page's run outputs in
  `<report>.work/` and the files the documented commands regenerate in
  `<report>.changed/`, instead of removing them on exit (#697).

### Changed

- `pyfds-evac`, `run.py` and the GUI log print `Route history rows: N`
  with `--output-route-history`, instead of `Route switches: N`. N is the
  number of rows of the file, `initial` and `default_route` rows
  included, not the number of route switches: the first FDS case prints
  161, of which 150 are `default_route` rows written at spawn.
  `examples/first_fds_case.py` prints "route history rows by reason"
  instead of "route changes" for the same count (#697).
- Route foresight (`anticipate`, on by default) reads every smoke sample
  at the time the agent would reach it, counted from the agent's position,
  instead of each leg at the time the agent reaches its start, counted from
  the route's origin node (#650; refs #171). The first leg starts where the
  agent stands and was read at the decision time, so a route's optical
  depth jumped when the agent passed a node: on `tj_full_gate_fallback`
  route A fell from tau 72 to 0 as agents passed the checkpoint, and they
  switched onto it and back. Every run with anticipation in a field that
  changes in time moves; runs with `anticipate = false` and runs in a
  field constant in time are bit-identical. The FED rate is still one
  sample per leg, read at the leg's midpoint at the time the agent reaches
  the leg's start. Ten of the fifteen CI scenario snapshots
  move; `tj_full_gate_fallback` and the S4 rerouting arms now run with
  `anticipate = false`, and S4 gains an arm on the spawn-time choice under
  foresight. FDS decks: `l_corridor_gate` goes from 58 to 17 switches
  and from 40 to 8 exit reversals, 5 of them within 2 s (28 before); the
  oscillation near a smoky door (#124) is reduced, not removed.
  `t_junction` goes from 3 to 5 switches, all fallback, and still
  evacuates 93 of 150; `world77` from 0 to 1. Anticipation has no
  FDS+Evac counterpart.
- `tests/test_familiarity_no_journey.py` bounds the rate of doorway
  deadlocks (#359) instead of requiring every agent out: at most 4 of 30
  runs of 5 agents and 5 of 20 runs of 20 agents may end with up to 4
  agents left, and any other incomplete run fails. Since #250, nothing
  breaks such a stand up under `explore`; the measured rate is 5/150 and
  5/60, and the Wayfinding page lists it as a limitation. The test is
  marked `slow`.
- An agent that knows no exit no longer explores by default; it follows the
  default route (see `no_known_exit`). `familiarity_test_discovery`,
  `familiarity_test_no_journey`, `blind_spawn_discovery` and `world_100` set
  `explore`. In the first FDS case 93/150 agents get out instead of 70/150,
  82 of them by an exit not in their map (#610).
- **API change:** `run_scenario` on a deck whose distribution sets a
  non-default `no_known_exit` and without `reroute_config` (rerouting off or
  `smoke_blind`) now raises `ValueError` naming the distribution; so do
  `--no-enable-rerouting` and `--smoke-blind` with such a deck (D33, #610).
  Pass a `RerouteConfig`, or drop the key to run on the default.
- The nearest exit of a spawn area without a journey is measured on foot
  through the walkable area, not in a straight line (#610).
- An agent's first choice of a known exit is logged as `initial`, not as a
  `smoke_reroute` away from an exit it never knew, and is adopted at once
  (#610).
- `pyfds-evac --scenario` takes the slice height from the scenario's
  `smoke_slice_height` when `--smoke-slice-height` is not given, and says
  so. A scenario without the key runs as before (#632).
- `pyfds-evac --help` lists `pyfds-evac init` among its examples (#606).
- SocialForceModel friction is passed to JuPedSim as 0, with a warning
  when a deck declares `sfm_friction` above 0. JuPedSim 1.4.2 applies
  the wall friction with the wrong sign (jupedsim#1677). The clamp goes
  once a JuPedSim release with that fix is pinned (#635).
- A spawn area that leaves out `number`, `radius` or `v0` takes
  `simulationParams.number`, `.radius` or `.v0`, else 10 agents, 0.2 m
  and 1.25 m/s, with and without journeys. Without journeys it took the
  `simulationParams` value, else the first spawn area's value, else a
  built-in count of 100; with journeys it ignored `simulationParams`.
  The built-in count for a deck without spawn areas drops from 100 to
  10; `simulationParams.number` still sets it. No shipped deck changes
  (#567).
- `VisibilityModel.clear_air()` and `scripts/animate_cognitive_map.py
  --cell-size` default to a 0.25 m grid, as `--vis-cell-size` does,
  instead of 0.5 m. A Python caller that relied on the 0.5 m default
  gets a finer grid, a build about four times slower, and walls 0.25 to
  0.5 m wide that may now block sight; pass `cell_size_m=0.5` to
  keep the old grid (#115).
- Scenario key `routing.fallback_switch_margin` (default 0.2) now
  compares optical depth `tau` instead of the worst extinction
  `k_max_route`. Between two refused routes, under both cost models, an
  agent leaves its exit, except for the existing must-flee override,
  only for a rival whose `tau` is strictly more than the margin lower
  (`tau < current × 0.8` by default) and differs from it by more than
  1e-9; equality keeps the exit, also when both `tau` are 0. The same
  rule replaces the travel-time anchor and the clean-route bypass
  between two refused routes, which kept agents on a route with three
  times the smoke. Configs that set the key still load; its effect
  changes. In the S4 T-junction the four agents just inside the smoky
  arm now turn back (8 → 12 switches). CI references move: four
  fallback cases and the `tj_full_gate_fallback` and
  `tj_discovery_gate_ramp` snapshots on both platforms. In the latter
  agent 29 turns back late and is still in the building at the 60 s
  horizon. Some returns to an abandoned exit remain; part of them come
  from foresight that samples each leg at one instant (#650). The
  `t_junction` FDS deck moves too: 1 → 3 switches; agent 21 now leaves
  by exit B instead of A, and agent 22 by A instead of B (#458).
- New scenario key `routing.fallback_return_lockout_s` (default 10 s;
  0 turns it off). After an exit switch between two refused routes, a
  switch straight back to the exit just left, again between two refused
  routes, waits this long. A feasible route on either side, a must-flee
  hazard and a third exit are never blocked. Before #650, on the
  `t_junction` FDS deck the 2 m route smoke sampling stepped over a
  narrow plume core and swung agent 22's tau past the margin and back:
  B → A at 48 s, A → B at 50 s. The lockout keeps the agent on A; the
  sampling resolution is tracked in #653. No CI reference, S4 count or
  other FDS deck checked (`l_corridor_gate`, `world100_stream_east`,
  `world100_stream_oval`) moves. A negative or non-numeric value stops
  the run (#458).

### Fixed

- A spawn area asked for more agents than it can hold stops
  `pyfds-evac --scenario` with one line, exit 1, instead of a traceback
  (#692): `pyfds-evac: error: Distribution '<id>': requested N agents but
  area can hold at most ~C. ...`. The message names the distribution key
  (before: its index) and, when several distributions share one polygon,
  all of them. The error is `SpawnCapacityError`, a `ValueError`, on both
  placement paths (with and without journeys). Results do not change.
- `pyfds-evac init` no longer says an exit "0.100 m wide" is below the
  0.1 m minimum exit width. A dropped exit's width gets the decimals it
  needs to read as below the minimum (0.0999 m), up to the full float for
  a width short of it only by floating-point noise, as in
  CorridorFlowExample (0.09999999999999964 m) (#682). Which exits are
  dropped does not change.
- On a plain FDS deck, `pyfds-evac init` no longer advises excluding a
  fire surface from the walkable area "with &EVHO": an `&EVHO` turns the
  deck into an FDS+Evac deck, and t_junction then lost both exits. It now
  advises rerunning `init` with `--walkable FILE.wkt`, a walkable area
  without the surface (agents then neither spawn nor walk on it), or, to
  keep it walkable, cutting a notch around it from the edge of the spawn
  polygon in `config.json`. FDS+Evac decks keep the `&EVHO` advice (#683).
- Route foresight no longer stops a run that passes the FDS horizon
  check (#666). With `anticipate` on (the default) and without
  `--allow-fds-horizon-hold`, a leg foreseen past the last FDS frame
  raised `FdsHorizonError` mid-run: t_junction with `fire_2MW_PVC`
  (300 s of output, a 300 s run) stopped at 295.6 s. A foreseen time is
  now held at the last frame, and the run logs it once. Samples at the
  agent's own time keep the horizon check. Runs with the hold flag are
  bit-identical when the slices routing reads share their last frame, as
  in every reference deck: foresight is held at the earliest last frame of
  those slices, where the flag holds each slice at its own.
- An exploring agent no longer turns back at the door of the only exit
  (#250, #387 a duplicate). A stage completes within 0.7 m of a random
  point in it, which can be short of where the next sign is legible.
  Before a patrol leg, the agent now walks until the node's routing point
  lies within its radius and looks from there; an exit or frontier it
  learns there is taken. The look writes no route-history row and leaves
  the patrol rotation unchanged. Only runs that patrol change: the
  `bs_discovery_gate_west` golden snapshot evacuates 10/10 by 29.0 s
  instead of 9/10 at 60 s, with no `wander` row. `default_route` and full
  familiarity runs are bit-identical.
- Arriving at a node teaches the leg just walked, and its reverse where the
  graph has one (#468).
- The SocialForceModel builder reads `sfm_body_force` (default 120000,
  JuPedSim's) as the body force *k* and passes it as `body_force=`. It
  used to pass `agent_strength` (2000) as *k* and `agent_range` (0.08)
  as the friction, through the deprecated `bodyForce=`.
  `sfm_obstacle_scale` reaches the per-agent `obstacle_scale` (default
  2000). Negative, non-finite or non-numeric `sfm_body_force`,
  `sfm_friction` and `sfm_obstacle_scale` raise `ValueError`. The run
  manifest records the effective values under `sfm`. Shipped decks in
  clear air and every documented number are unchanged; the
  `ft_full_gate_detour` and `ft_full_additive_detour` golden snapshots,
  with contact under synthetic smoke, are regenerated (#611).
- `--show-config`, the TUI and the GUI report a distribution whose
  `desired_speed`, `desired_speed_distribution` or `desired_speed_std`
  differs from its `v0*` key, with the error the run stops on. They used
  to accept the deck. The check,
  `pyfds_evac.core.agent_params.check_speed_aliases`, does not import
  JuPedSim; runs are unchanged (#612).
- A spawn area's own `number`, `radius` and `v0` are read as the
  `simulationParams` values are: numeric strings are converted, a
  boolean is not a number, `number` must be 0 or more and `radius` finite
  and greater than 0. A spawn area's `v0` must be finite and 0 or more
  (0 for agents that stand still); `simulationParams.v0` stays above 0.
  `simulationParams.number` below 0 and a boolean `simulationParams`
  value are rejected too. A value out of range stops the run with a
  `ValueError` that names the key, and the distribution for a spawn
  area's own value (`desired_speed` when the deck set that alias). A
  spawn area's own `null` is unset and takes the deck-wide default, as a
  deck-wide `null` does; it used to stop the run with a `TypeError`. A
  boolean used to be read as 1 or 0, a numeric string `v0` or `radius`
  failed inside pyFDS-Evac with a `TypeError`, and NaN or negative
  values were accepted or failed later without naming the key. No
  shipped deck changes (#649).
- `Scenario.summary()`, `Scenario.plot()`, `Scenario.list_distributions()`
  and the TUI's agent count show the count the run places for a spawn
  area without `number`, `simulationParams.number` else 10, instead of 0
  or `?`. An invalid `simulationParams.number` raises the run's
  `ValueError` in the `Scenario` views; the TUI shows `?`. The defaults
  move to `pyfds_evac.core.agent_params`, which does not import JuPedSim;
  runs are unchanged (#647).
- A distribution whose `parameters` is a JSON-encoded string, which the
  initialisers read, now works as the object form. The discovery check
  behind `--show-config`, the TUI and every CLI or GUI run, the
  familiarity and `entrance` lookup of `run_scenario`,
  `Scenario.summary()`, `plot()` and `list_distributions()`, and the
  TUI's agent count stopped with an `AttributeError`, and the string's
  `no_known_exit` was ignored. `Scenario.set_agent_params()`,
  `set_agent_count()` and `set_flow_schedule()` store the parsed object.
  An unparseable string, `null`, or a value that is not an object
  (`"[]"`, `"42"`) reads as no parameters everywhere, the initialisers
  included; the fallback initialiser stopped on `null`, and both on an
  encoded non-object, with an `AttributeError` (#644).
- Sign visibility from an FDS run no longer stores a time point past the
  end of the FDS output when `--reroute-interval` does not divide `T_END`;
  the last stored point is `T_END`. It now raises `FdsHorizonError` only
  more than one FDS output interval past the end, the window the setup
  check and the smoke and FED samplers use, so a run the setup check
  accepts no longer fails mid-run in sign visibility. The vismap cache
  format goes from 5 to 6, so existing caches are rebuilt once (#510).
- Routes that tie exactly for a discovery agent no longer rank in an
  order that depends on `PYTHONHASHSEED`: the agent's known subgraph is
  built in sorted order, so an exact tie goes to the alphabetically
  first exit. Full-familiarity agents keep the scenario's order (#199).
- Under the gate, route optical depths `tau` at most 1e-9 apart rank as
  equal, so travel time decides. Round-off such as 1e-19 against 4e-15
  used to decide the order, and with it whether the exit-switch anchor
  was asked at all. Neighbouring ties form one group; within it, travel
  time, path length and then the candidate order decide, never the raw
  `tau`. Three FDS decks move, each from a tie with |Δtau| ≤ 1.6e-12:
  `t_junction` goes from 0 to 1 switch, one agent of `l_corridor_gate`
  first picks the near exit (far exit 28 → 27 agents), and agents 5 and
  6 of `world100_stream_east` take another exit. CI goldens and snapshots
  are unchanged (#452).

### Documentation

- The page "Start from your own FDS case" (Getting started) checks
  and imports two plain FDS decks and an FDS+Evac guide deck with
  `pyfds-evac init`, and Usage lists what the importer derives, its
  constants, its messages and the fields of `import_report.json` (#606).
- Verification › Familiarity and Wayfinding in practice restated at
  `828ae8c3`: no patrols or turn-backs since #250, and criterion 6 is the
  30-seed grid study of #168 (passes from 0.05 to 0.025 m on this sample,
  where the 90 % interval of the P90 change reaches +10 %; fails from 0.1
  to 0.05 m because of #359 deadlocks); figure captions match the
  regenerated figures (#463, #637).
- Verification scripts `scripts/verification/familiarity_grid_study.py`
  and `familiarity_grid_analysis.py` rerun and judge the #168 grid study
  (#168, #637).
- `site/data/examples.toml` takes an optional `results_note`, shown under
  the commit on the example's page (#463).
- Limitations lists the open defects 0.4.0 ships with: sight lines through
  cells outside the FDS meshes hide signs (#454), doorway deadlocks under
  `explore` (#359), reevaluation intervals below 1 s act as 1 s (#660),
  stage reach uses a 0.2 m radius (#661), `init --check` ranks slices on
  the deck's z (#687), and `&EVHO` turns a plain deck into an FDS+Evac
  deck (#688). Usage and Models › Routing state the 1 s floor of
  `--reroute-interval`.
- The tie order of discovery agents is no longer listed as depending on
  `PYTHONHASHSEED` (#199, fixed by #643).
- The assets page states what S4 asserts: at least 12 of 20 agents switch
  without anticipation, and at least 17 of 20 take the clear exit at spawn
  with it (#458, #650).
- The steering-pass profiling on Models › Routing is dated to `4f859bf5`
  (#665), and the FDS+Evac guide is cited as "Evac 2.6.0-draft"
  throughout.
- Fundamentals › Seeing and using exit signs states the waypoint method
  of Börger, Belt and Arnold (2024, Eqs. 2-10), the steps from seeing a
  sign to following it (SFPE Handbook, 6th ed., Ch. 65), and the
  detection, reading and following studies with their settings and
  values. "Seen" is Jin's obscuration threshold (#315).
- Models › Wayfinding defines a legible sign as one barely seen at the
  visibility distance (Jin's seeing threshold, C = 3); its words or arrow
  need not be readable. A Deviations bullet states that the model treats
  a seen sign as understood, and the #173 limitation states that the
  30 m default lies outside Jin's data. The FED_DOOR_CRIT notes say that
  only the form of Jin's law is borrowed; dated review notes carry
  errata instead of rewrites (#287).
- Fundamentals › Visibility cites McGrattan and Merci (SFPE Handbook,
  6th ed., Ch. 40, Eq. 40.22, p. 1206) for C = 3 and C = 8, next to the
  FDS User's Guide and Mulholland (2002) (#640).
- Models › Wayfinding lists sign photometry as a limit: the luminance,
  size and contrast of a sign, the ambient light and light scattered into
  the line of sight enter only through C. A figure shows the
  sign-legibility test step by step for sign B of `t_junction`
  (`fire_2MW_PVC`, t = 20 s) from the run's VisMap, with the equation
  numbers of Börger et al.; the extinction slices it reads are tracked in
  `scripts/figures/data/` so the docs workflow regenerates it (#652,
  #654, #655).
- Studies › Schröder 2015 is rerun at `9c820e0f` (100 runs, seeds 1-10).
  On the main fire the exit-E share is 0.642 under the gate (was 0.614)
  and 0.452 under the additive model (was 0.457), with Δy = −1.08 m
  (−1.53, −0.62) (was −0.85 m). The gate mechanism is rewritten: since
  #650 every route is refused for the first hall agents at 130-134 s, the
  fallback wave follows at 151-155 s, and exit E re-paths via door B at
  152-156 s. The no-fire and smoke-blind arms are unchanged. The
  figures, the GIF (median seed now 5) and the alt texts are regenerated
  (#650, #697).
- How-to › With and without the fire is rerun at `9c820e0f` with 320
  runs (#697). C, U and S are unchanged. With smoke-aware routing
  (arm R), 80 % of the agents take the far exit A with no pre-movement,
  19 % with 30 s and none with 60 s, against 100 %, 88 % and 86 % in the
  earlier runs. The page reports the cause as a finding: with
  pre-movement both routes are refused before anyone walks, and since
  #458 the lower optical depth decides, which picks the shorter route to
  exit B past the burner. R's largest max FED rises from 0.17 to 0.24.
  Whether this rule is right is open (#696).
- Every example result is re-run or re-checked at `9c820e0f`, and no
  page carries "Not re-checked for 0.4.0." any more: the walkthrough,
  RSET ensemble, ISO Tests 18 and 19, heat radiometer, Schröder 2020
  (160 runs), `cognitive_map_memory` and the first FDS case. ISO Test 19
  now gives the occupant's spawn as (4.92, 4.68) m, the position since
  #385; FED values and stop times are unchanged. The first FDS case
  names fdsvismap 0.3.2 and explains its 161 route-history rows (#697).
- The Terminal UI page's screenshots are recaptured on the `t_junction`
  `fire_2MW_PVC` output (93 of 150 out), and the Review screen now lists
  the O2 threshold, FIC off and the visibility time step (#697).
- The landing page badge shows the released version, read from
  `pyproject.toml`, instead of "Alpha" (#641).

## [0.3.1] - 2026-10-06

### Removed

- The unused agent-parameter builders and second speed sampler in
  `core.scenario`. Runs never called them; spawning uses
  `core.simulation_init`. Results are unchanged (#569).

### Fixed

- `create_agent_parameters` raises `ValueError` naming an unknown
  `model_type` and the accepted ones. It used to return collision-free
  speed model parameters, so a misspelled model type silently ran a
  different model (#570).
- The plan-view frame recorder of the terminal UI gets a frozen copy of
  the run's incapacitated agents, not the run's own set, so it cannot
  change who is incapacitated. Frames and results are unchanged (#561).
- A SocialForceModel deck whose `simulationParams` omits
  `relaxation_time`, `agent_strength` or `agent_range` runs with 0.5,
  2000 and 0.08 for the missing keys, the values already used without
  simulation parameters. It used to crash, report a spawn area that is
  too small, or spawn no flow agents. An error other than a failed
  placement while spawning agents on a journey keeps its own type
  instead of being reported as a placement failure (#568).
- `--show-config` exits 1 on a scenario whose `routing.cost_model` names no
  route cost model, which every run rejects; the GUI rejects such a
  scenario at upload and submit, and the terminal UI lists it in Review
  (#571).
- The exported `run.py` gives `replay_exits` as an absolute path, so a
  script run from another folder still replays the exits, and a script
  written by the terminal UI no longer says it came from the GUI (#558,
  #576).
- A blank FDS folder is left out of the equivalent CLI command instead of
  becoming the current folder (#557).
- Terminal UI:
  - Save and Copy command right after an edit include that edit (#559).
  - Save, Copy command and Show Python refuse while a field does not
    parse, and name the field; they used to write the default value
    (#619).
  - The Recent tab keeps entries whose scenario or FDS folder is gone,
    dimmed and labelled with what is missing; `Delete` removes the
    highlighted entry, and two long paths no longer look the same
    (#600).
  - Checks are described in words instead of rule IDs (D3, D17, ...);
    the JSON output keeps the IDs (#573).
  - "Open docs page" opens the Terminal UI page (#575), and no redraw
    runs after the app closes (#602).
- Web GUI: decimal fields no longer ask for a keypad without a decimal
  point (#552), and units keep their case in the uppercase form labels,
  e.g. "(m)" instead of "(M)" (#348).
- The FDS case warnings link the published FDS case page instead of a
  path in the repository (#323).
- The analysis scripts that call `run.py` report a run that ends with
  exit status 2 as incomplete instead of using it silently (#449).

### Documentation

- Smoke speed model: FDS+Evac reference speeds from the guide's component
  test; the plot is no longer called a verification, and new
  verification tests check the speed and FED cases of the FDS+Evac guide
  against formulas rebuilt from `evac.f90` and `func.f90` (#631).
- Web GUI: the `run.py` listing matches the exported script (#558, #576).
- Terminal UI: the Recent tab (#600).

## [0.3.0] - 2026-10-05

### Added

- `pyfds-evac-tui`, a terminal UI (`pip install 'pyfds-evac[tui]'`, built
  on Textual): pick a scenario and FDS folder, configure with the options
  of `pyfds-evac` (inactive options greyed out with the reason), review
  the effective configuration and the equivalent command, run in a
  separate process with a live plan view of walls, exits, agents and
  smoke, and inspect the outcome and output files. Runs write to the GUI's
  folder layout under `./results`; the same options give the same files as
  `pyfds-evac` (#485). Keys and navigation:
  - every footer shows `^q quit  ? keys  ^k palette`; `?` and `F1` open the
    key list on every step (#598, #583);
  - `ctrl+n` / `ctrl+p` go to the next / previous step, and the footer names
    the target; `Esc` also goes back; the command palette is on `ctrl+k`;
  - on Configure, `↑`/`↓` move between options and the focused option's row
    is highlighted as in the palette; a click on an inactive option shows
    why it is inactive;
  - the FDS folder box and the Open file tab browse folders as Emacs `dired`
    does, with fzf-like filtering, `Tab` completion and `..`; FDS output
    folders and scenarios are marked;
  - on Results, `←`/`→` replay the plan frames, `v` opens it full screen, and
    `Enter` on an output file previews it (text lines, SQLite tables, folder
    contents) with `y` copy path and `o` open (not over SSH);
  - in a terminal with 256 or 16 colours, a notice says the theme colours
    are approximate and how to get truecolor (#599).
- `pyfds_evac.config.frontend`: the run folders and outcome wording the GUI
  and the TUI share (provisional) (#485).
- `pyfds_evac.config`: one model of the run options (name, type, unit,
  default, choices, help, the Python field each sets) from which the
  `pyfds-evac` parser and the GUI form are built, the effective
  configuration of a run (models on or off and why, options with their
  origin, options that have no effect, setup warnings and errors) and the
  equivalent command and Python script. Provisional public API: it can
  change in 0.3.x. Flags, defaults, help and results are unchanged (#484).
- `--show-config` prints the effective configuration and exits without
  running; exit status 1 when the configuration has an error (#484).
- The run manifest written with `--output-sqlite` records the effective
  configuration under `configuration`, checked against the seed, models and
  model parameters the run used (`ScenarioResult.run_settings`,
  provisional) (#484).
- `ProgressEvent` counts incapacitated agents and flow agents not yet
  spawned (`incapacitated`, `not_spawned`; provisional) (#484).
- For the terminal UI (#485), provisional:
  - `pyfds_evac.config.rules.applies` / `applicability`: whether each
    option changes the run, also at its default, with the rule and reason
    of the "has no effect" warnings; `Parameter.tier` (`common` for the
    GUI's sections, else `advanced`).
  - `pyfds_evac.core.run_stream.stream_run`: runs the options as
    `pyfds-evac` does and sends status events instead of printing:
    phases, log lines, warnings (with the simulated time), progress, a
    `PlanEvent` (walkable outline, exits and their openings, signs, spawn
    areas, smoke mode, the FDS slice height read), throttled `FrameEvent`s
    (agent positions and states, agents per exit, a coarse float16
    extinction grid) and a `ResultEvent` with the outcome (evacuated,
    total, remaining, incapacitated, not spawned, end time, seed, files).
    Frames are off unless asked for; results are the same with them.
  - `ScenarioResult.agents_incapacitated`.

### Changed

- An option set away from its default that changes nothing in the run now
  logs a warning at setup, e.g. `--enable-fic-speed has no effect without
  --fds-dir.` Runs with default options log nothing new (#484).
- `uv.lock` takes the security fixes of pillow, starlette, anyio, idna,
  soupsieve and oauthlib (#525).
- `uv run app.py` and `python -m pyfds_evac.webapp.app` listen on
  127.0.0.1 instead of all interfaces, as `pyfds-evac-gui` does; `--host`
  and `--port` work as for `pyfds-evac-gui`. All three print a warning
  when `--host` makes the GUI reachable from other computers. `app.py` and
  `python -m pyfds_evac.webapp.app` now stop with a usage error on
  arguments other than `--host` and `--port` (#477).
- GUI and TUI results show an Incapacitated count after Remaining, or
  "not modelled in this run" when no dose model applies. Counts read
  "e of n agents", or "e of n that entered" when flow agents were cut
  off. The smoke overlay draws the horizontal FDS slice at the run's
  smoke slice height on fixed K bins, with a caption naming the slice
  and the frame time. The smoke chart has fixed axes, a dashed mean K
  and a numeric summary. `ResultEvent` and `PlanEvent` gain
  `incapacitation_modelled` (#321).

### Fixed

- The GUI no longer prints a `SyntaxWarning: invalid escape sequence`
  on its first import: a regular expression in its inline JavaScript was
  not escaped for Python. The page sends the same JavaScript (#476).
- The custom replay speed of the GUI's trajectory viewer shows a decimal
  point on a host with a comma region (`1.5`, not `1,5`). It takes digits
  with a point, at least 0.05; any other value (`1,5`, `2x`, `-1`) is not
  applied, and a message under the controls says so and names the speed
  that is kept. Before, `1,5` applied as 1 (#493).
- The GUI's results-only view lists the run manifest under "Output
  files", as the finished view does (#494).
- GUI and TUI runs write the exit history CSV
  (`<run>_exit_history.csv`, as `--output-exit-history`) to the run's
  folder, and the GUI lists it with the other output files. Before, no
  front end set the option, so the file was never written (#547).
- An unknown routing `cost_model` or smoke `speed_law` raises
  `ValueError` and names the allowed values. Before, any `cost_model`
  other than `"gate"` ran the additive model and any `speed_law` other
  than `"fridolf"` ran lund, so `"Gate"` or `"Fridolf"` silently gave the
  other model. Names are matched exactly (`"gate"`, `"additive"`,
  `"lund"`, `"fridolf"`); an absent key still means `"gate"` and
  `"lund"`. Valid inputs give the same results (#305).
- A scenario JSON accepts `desired_speed`, `desired_speed_distribution`
  and `desired_speed_std` as aliases of `v0`, `v0_distribution` and
  `v0_std`, as `Scenario.set_agent_params()` does. Before, the run
  ignored them without a warning and used 1.25 m/s. A distribution that
  sets an alias and its `v0*` key to different values is an error; equal
  values are accepted. Scenarios without these keys run unchanged. The
  SocialForceModel agent parameters fall back to 1.25 m/s, not 0.8, when
  no `v0` is given; no run reached that fallback (#143).
- In the layer heat regime, the effective configuration reports a
  missing layer input once, not twice, and attributes layer errors to
  the layer emissivity option, not to `heat_emissivity` (#522).
- A `run_scenario` that fails removes its temporary trajectory SQLite
  and its manifest. Before, they were left behind (#331).
- Stale user-facing text: the usage of `scripts/run_and_plot.sh` names a
  finished FDS run as `<fds-dir>`; the `--smoke-slice-height` help names
  walking speed, FED and sign legibility; `examples/walkthrough.py` uses
  the 1.6 m slice height; `examples/rset_ensemble.py` writes its figure
  to a temporary folder or to its first argument, not over the tracked
  site figure (#312).

### Documentation

- New Terminal UI page (#537).
- Scenario JSON and Troubleshooting document the exact names of
  `cost_model` and `speed_law` and the `desired_speed*` aliases; Usage
  tables the defaults of `pyfds-evac` and `run_scenario()` (#584, #585).
- Visibility (Fundamentals): Jin's limits of 0.15 1/m for occupants
  unfamiliar with a building and 0.5 1/m for familiar ones, checked
  against Jin (1981); the routing threshold of 0.5 1/m applies to all
  agents (#515, #608).
- Coming from FDS+Evac names FDS 6.7.7 as the last FDS+Evac release, and
  the Wayfinding, Route-cost gate and model comparison pages mark
  0.03 1/m as the Evac 2.6.0 door threshold (#542, #543).
- Fundamentals pages state published laws only; the slice-height default
  moved from ASET/RSET to the docs (#588).

## [0.2.4] - 2026-10-03

### Added

- `scripts/release_check.sh` has an install gate, in `--quick` and
  `--full`: it builds the wheel of the commit and, per supported Python
  version, installs `<wheel>[gui]` with plain pip into a fresh venv. It
  checks `pip check`, `pyfds-evac --help`, an argument error,
  `python -m pyfds_evac --help`, the GUI page and the `ISO-table21`
  scenario from a folder outside the repository, and the install hint
  of `pyfds-evac-gui` without the extra. The first `pyfds-evac --help`
  and `pyfds-evac-gui --help` after the install are timed with an empty
  matplotlib cache and fail above 1 s. CI runs the same check on Python
  3.12 with a 3 s limit (#478).

### Fixed

- `pyfds-evac --help` and argument errors no longer load numpy. The
  heat options of the parser read their constants from `core.fed`,
  which loaded the FDS slice sampler and numpy with it; the sampler now
  loads when FDS data is read. On macOS the first numpy import after an
  install took up to 1.2 s and made the 1 s limit of the install gate
  fail now and then (#503).

### Documentation

- New how-to "Create a scenario": the three ways to get `config.json` and
  `geometry.wkt` (JuPedSim Web, an example download, matching the FDS
  deck), the keys to add by hand after an export from the app, and how to
  check a scenario before a run (#506, #512). Scenario JSON documents
  `waypoint_routing`, `transitions` and `journeys_v2`.
- `CONTRIBUTING.md` is one screen: issue, fork, pull request. Setup, CI,
  docs build, commit style and versioning moved to a new Development
  page. The Limitations page states the release policy (SemVer) (#511,
  closes #502).

## [0.2.3] - 2026-10-03

### Fixed

- `pyfds-evac --help` and argument errors return at once, also on the
  first call after an install: JuPedSim, fdsreader, fdsvismap and
  matplotlib now load when a run starts, not when the command starts.
  The first run after an install still builds matplotlib's font cache.
  Flags, defaults and outputs are unchanged (#496).

## [0.2.2] - 2026-10-02

### Changed

- `pyfds-evac --help` is shorter to read: a one-line usage
  (`pyfds-evac --scenario PATH [--fds-dir DIR] [options]`), a description
  of what the tool does, the flags in eight groups (scenario and run,
  outputs, FDS input and smoke, toxic gas, heat, routing, visibility and
  signs, ASET/RSET tools) and copy-paste examples. It is rendered by
  rich-argparse, a new runtime dependency (`>=1.8`), in colour on a
  terminal and as plain text when piped or with `NO_COLOR`. Flag names,
  defaults, choices and behaviour are unchanged.

### Fixed

- GUI: decimal fields show "1.6", not "1,6", when the operating system's
  region uses a decimal comma (Chromium on macOS formats number inputs
  by the OS region). They are text fields now; a typed comma is flagged
  before the run starts. Submitted values are unchanged (#487).
- GUI: "Artifacts written" and the results-only file list show the
  results folder once, with a Copy path button, and each file relative
  to it; the full path is in the tooltip (#488).
- GUI: the Smoke and Cognitive map growth plots are left out when the
  run has no data for them (no smoke source, no agent's cognitive map
  grew); one "Not shown" note says why (#489).
- A default run no longer prints the `Reroute debug` trace of the
  rerouting pass; it is a debug log, printed with the `--debug` flag. The
  command line prints fdsreader's repeated module-parse warning (such as
  `Module vents`) once instead of once per opened case. Results and
  written outputs are unchanged (#486).

## [0.2.1] - 2026-10-02

First release on PyPI: `pip install pyfds-evac`.

### Added

- Releases are published to PyPI as `pyfds-evac` by a GitHub workflow
  with Trusted Publishing, when a GitHub release is published (#472).
  The sdist leaves out the site, specs and working material.

### Changed

- fdsvismap 0.3.2 replaces 0.3.1, still pinned exactly. Its code is the
  same; it allows scikit-image `>=0.23.2,<1.0` instead of `~=0.23.2`.
  The uv override of scikit-image is removed, and `pip install` now
  works on Python 3.12, 3.13 and 3.14. The lock moves scikit-image from
  0.23.2 to 0.26.0 on Python 3.12, as on 3.13 and 3.14 already; a seeded
  reference run gives identical trajectories and visibility maps (#479).

### Fixed

- The CLI and the GUI work from an installed wheel (#471). The CLI moved
  from `run.py` into `pyfds_evac.cli` and installs as the `pyfds-evac`
  command and as `python -m pyfds_evac`; `run.py` still runs it, with the
  same flags, defaults and outputs. The GUI starts with the
  `pyfds-evac-gui` command (gui extra; without it the command says how to
  install it), listening on 127.0.0.1:5001; `uv run app.py` still works.
  Installed outside a source checkout, the GUI reads scenarios from
  `./assets` and writes `uploads/` and `results/` under the directory it
  starts in, not under site-packages.

### Documentation

- Install, Web GUI, Usage, Quickstart, Troubleshooting and the README
  describe `pip install pyfds-evac` and the installed commands
  `pyfds-evac`, `python -m pyfds_evac` and `pyfds-evac-gui`: where the
  GUI reads and writes, its 127.0.0.1 default, the message without the
  gui extra, and that an example zip unpacks into a folder of its own
  (#475). The README links are absolute, so they work on PyPI.
- The page "A crowd in a real fire" is renamed "A crowd in a fire". Its
  address (`first-fds-case`) and anchors stay, so links keep working.
  The Fundamentals and the figure of the design-fire page say "fire"
  where they said "real fire".

## [0.2.0] - 2026-10-02

Highlights. Smoke along a route now changes an agent's exit: route costs
add smoke and dose, and a gate on the route's optical depth rejects a
smoky path. Agents choose exits from a cognitive map that grows with
familiarity, signs they can read and exits they discover. The heat dose
follows ISO 13571 and the SFPE Handbook, with opt-in total-flux,
hot-layer and `INTEGRATED INTENSITY` methods. Defaults follow FDS+Evac
where a mechanism has a direct counterpart. Exits can open and close on
a schedule. A run checks its scenario against the FDS domain and stops at
the end of the FDS output. A run that reaches its time limit with agents
inside is reported as incomplete, and `run.py` then exits with status 2.
Seeded results differ from v0.1; see Changed. pyFDS-Evac runs on Python
3.12, 3.13 and 3.14. Release 0.2.0 is installed from the source tree
with uv; it is not published on PyPI.

Breaking changes, which make this a MINOR release while MAJOR is 0:

- Python 3.12, 3.13 or 3.14 is required; Python 3.11 and earlier are no
  longer supported (Removed).
- Exit status and run outcome: `run.py` exits with status 2 for an
  incomplete run, and `success` is then `False` (Changed).
- A run that outlasts the FDS output stops with `FdsHorizonError` (Changed).
- Defaults follow FDS+Evac: sampling height, FIC slowdown, heat dose,
  incapacitation, O2 threshold, pre-movement and `v0` (Changed, Migration).
- Heat: the ISO 13571 clothed law by default, and one threshold for gas and
  heat (Changed).
- Seeded placements and outcomes differ from earlier versions (Changed).
- Agents leave at an exit when their centre enters the exit polygon, and the
  opening exit is ranked from each agent's position (Changed).
- Exits are priced from where the agent stands, which changes route
  switches and exit choice in smoke (Fixed, #451).
- Rerouting is on by default, `w_queue` defaults to 0, `EXTINCTION` is no
  longer read as smoke, and the FDS decks and demo assets moved to
  `fds_directory/` and `assets/t_junction/` (Changed).
- `speed_law="fridolf"` is Eq. 7 of Fridolf et al.; the V/(V+2) law is
  removed (Changed).
- New output columns and manifest keys: `in_fds_domain`, `fds_coverage`,
  `outcome`, `agent_seeding` and the heat columns (Added, Changed).
- Web GUI: the cumulative FED chart, sparkline and mean line (Removed).
- The unused modules `pyfds_evac.config` and `pyfds_evac.utilities`
  (Removed).

### Added

- `scripts/release_check.sh`, the release gate. In a detached worktree of
  the current commit it runs the tests per supported Python, builds and
  follows the download bundles, runs the documented commands listed in
  `scripts/release_check.toml` and builds the site, then writes
  `release-check-<commit>.md`. Checks of pages an open issue already
  lists are reported as STALE and do not fail the gate (#462).
- Python 3.13 and 3.14 support; CI tests 3.12, 3.13 and 3.14.
  On 3.13 and 3.14, `uv sync` installs scikit-image 0.26 instead of the
  0.23 that fdsvismap requires, which does not build there; fdsvismap's
  sight lines are unchanged. A pip install needs Python 3.12.
- A setup check of the scenario against the FDS slice coverage: the
  walkable area, exits, checkpoints, spawn areas and route edges outside
  the slices of every sampled quantity (m² and m), and signs outside them
  or off the vismap grid, are logged once and recorded as `fds_coverage` in
  the run manifest and in `metrics`. The smoke and FED histories gain an
  `in_fds_domain` column, `agent_scalars` the same column, and the run ends
  with a count of agents and samples outside (`metrics["fds_outside"]`).
  Outside the slices the values are unchanged: ambient air and clear sight,
  as in FDS+Evac.
- `--require-fds-coverage` (`require_fds_coverage=True` on
  `run_scenario`, `ExtinctionField`, `FdsFedField`, `FdsHeatField` and
  `VisibilityModel`): anything the setup check finds outside is an error,
  and so is any smoke, FED, heat or sign-visibility sample outside the
  slices (`FdsDomainError`, naming the quantity, position and time).
- Exits that open and close on a schedule: the optional exit keys
  `open_from_s` and `closed_after_s` keep an exit open while
  `open_from_s` ≤ t < `closed_after_s`. A closed exit removes nobody, is left
  out of route ranking and of explore and wander targets, and an agent
  heading for it re-evaluates at the next reroute check, on the exits it
  knows; the switch is logged as `exit_closed`. An agent that knows no other
  node waits at the closed exit. An opened exit is taken at the next regular
  re-evaluation. A schedule needs rerouting and routed agents:
  `--no-enable-rerouting`, `--smoke-blind`, `--replay-exits` and agents on
  JuPedSim journeys are rejected. `StageNode` gains `open_from_s`,
  `closed_after_s` and `is_open()`; `route_graph` gains
  `without_closed_stages` and `stage_closed`. Without a schedule results are
  unchanged ([#373](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/373)).
- `assets/station_fahy/validate.py` prints the agreement statistics of the
  Station validation study: T1 over the placed rows (Fahy 117/229 =
  51.1 %) with its signed bias; W, the door-user-weighted total variation
  distance, with the rows under 10 door users pooled; W's noise floor from
  20,000 multinomial resamples of Fahy; the per-run spread over several
  runs; the split at `--t-jam`, descriptive only; and, with `--against`,
  the paired W difference per seed on the agents that exited in both arms.
  A scored row without a model door user counts as distance 1. Agents still
  on the grid at the horizon (`max_simulation_time` of `--config`, or
  `--horizon`) are censored: counted, and left out of T1, W and the
  same-agent set; `observed_matrix` is unchanged
  ([#374](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/374),
  [#382](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/382)).
- `--smoke-blind`, `--replay-exits CSV` and `--output-exit-history CSV`
  for ASET/RSET arms on the same FDS output. `--smoke-blind` samples the fire
  for the smoke and FED histories only: agents walk at free speed, choose
  their first exit with K = 0 and no FED, see signs as without the fire, and
  rerouting and tenability are off; FED, heat FED and FIC still accumulate.
  `--output-exit-history` writes each agent's exit
  (`agent_id,origin,spawn_index,exit_id`), and `--replay-exits` sends the
  n-th agent spawned from an origin in a later run to the exit of the n-th
  agent from that origin there, by clear-air costs on the agent's map,
  failing on a missing spawn, an unknown exit or an exit it cannot apply.
  `run_scenario` takes `smoke_blind` and `replay_exits`, `ScenarioResult`
  gains `exit_history`, and the manifest records both options when on,
  the replay as its agent count and sha256
  ([#341](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/341)).
- `--heat-regime {smoke,layer}` (opt-in, with `--heat-fed-method
  total-flux`; default `smoke`, the behaviour below): `layer` takes the head
  to be in clear air below a hot layer, with q = h(T_g − T_s)/1000 plus the
  net layer flux φ ε_L σ(T_L⁴ − T_s⁴)/1000 and no radiant term of the gas at
  the head, so the two radiant terms are never summed (spec 016). T_L is read
  from a second `TEMPERATURE` slice at `--heat-layer-height`;
  `--heat-view-factor` and `--heat-layer-emissivity` set φ and ε_L. None of
  the three has a default. The FED history gains `heat_layer_temperature_c`
  and the manifest's `heat_flux_parameters` the regime and layer parameters
  ([#222](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/222)).
- `--heat-radiant-source integrated-intensity` with `--heat-u-factor f`
  (opt-in, with `--heat-fed-method total-flux`; default source `gas`): the
  radiant term is the excess f·(U − 4σT_s⁴) over an isotropic field at the
  skin temperature (maintainer decision) from the FDS `INTEGRATED
  INTENSITY` slice at the slice height, in place of the gas term
  ε σ (T_g⁴ − T_s⁴), so q = f·(U − 4σT_s⁴/1000) + h (T_g − T_s)/1000.
  f in [0.25, 1] has no default and is
  required; a case without the slice, a U slice at another height than the
  TEMPERATURE slice, or an agent inside only one of the two slices is an
  error. With `--heat-regime layer` as well, U supplies the radiant term
  and the layer term is not added (U already holds the layer's emission),
  with one warning and `layer_term: false` in the manifest. The FED
  history gains
  `heat_integrated_intensity_kw_m2` and the manifest `radiant_source`,
  `u_factor` and `radiant_flux` (`excess`). Agents outside the FDS domain
  get a zero rate, with U and q NaN in the FED history, and one warning
  per run. Surroundings at or below the skin temperature give no dose for
  any f; a negative excess counts as zero and the rate is never negative
  ([#221](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/221)).
- `--heat-fed-method total-flux` (opt-in, with `--enable-heat-fed`; default
  `convective`): the heat dose is q^1.33/D (SFPE Handbook Ch. 63 Eq. 63.43)
  with q the heat flux to the skin of Eq. 63.49, both terms divided by 1000
  together. The radiant term of q (the gas term, the `INTEGRATED
  INTENSITY` excess or the layer term) counts as zero in the dose below
  2.5 kW/m² (ISO 13571:2012 §8.2, §8.4, spec 016; 2.5 itself counts); the
  convective term counts at every level, so hot air still gives a dose.
  D is the dose of `--heat-endpoint`, the fatal 16.7 without it (SFPE Ch. 63 p. 2384). `--heat-emissivity` (0.5),
  `--heat-convective-coefficient` (5) and `--heat-skin-temperature` (35 °C)
  set the flux; their defaults are assumptions. The FED history gains
  `heat_flux_kw_m2` (the physical q) and the manifest `heat_fed_method`
  and `heat_flux_parameters`, with `radiant_threshold_kw_m2`. This is the
  head-in-smoke regime
  ([#223](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/223)).
- `--heat-endpoint {tolerance,injury,fatal}` (opt-in, with
  `--enable-heat-fed`): the heat dose uses the convective law of that
  endpoint, SFPE Handbook Ch. 63 Eq. 63.45, 63.46 or 63.47, paired with its
  radiant dose (1.33, 10, 16.7; SFPE Ch. 63 pp. 2382 and 2384). The FED history gains `heat_endpoint`,
  `heat_outside_validity` (above 205 °C, an assumed limit, or a non-finite
  temperature) and `heat_humidity` (`unknown`, as humidity is not sampled),
  and the run manifest records `heat_endpoint` and `heat_validity`. Without the option the dose is
  the ISO 13571:2012 law of `--heat-clothing`
  ([#220](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/220)).
- A run warns once when CO is sampled with zero CO2: the hyperventilation
  factor is then 1, and the FDS deck probably has no ambient CO2.
- Web GUI: a light/dark theme switch, a Cancel control for a running scenario,
  a Clear control for finished results, and a trajectory viewer that fills
  the screen in fullscreen. A cancel stops the run at its next progress tick
  or between phases; output files written before the cancel stay on disk.
- `assets/Haspel`: the BUW Campus Haspel ground floor with an FDS deck, for
  a model-to-model comparison with a PathFinder student study. Not yet a
  valid comparison; see `assets/Haspel/README.md`
  ([#134](https://github.com/PedestrianDynamics/pyFDS-Evac/pull/134)).
- `assets/heat_radiometer`: three FDS decks for the heat dose (spec 016,
  L3): a sealed adiabatic room with a hot sooty layer above 2 m, the same
  room uniformly hot (the isotropic control), and a propane burner in the
  open. Skin radiometers and gauges (35 C, h = 8 W/(m2 K)) at 1.6 and
  1.8 m face up, sideways and down next to `INTEGRATED INTENSITY`
  devices and slices. `scripts/verification/heat_radiometer.py` tabulates
  q/U and `heat_radiometer_figures.py` draws it; page
  `docs/testing-heat-radiometer.md`. Reference data for #221-#223; the
  heat model is unchanged ([#224](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/224)).

- Routing and wayfinding since v0.1: congestion-aware routing (#16);
  visibility-aware routing with cognitive maps (#17); auto-routing for
  minimal configs with distributions and exits only (#18), whose
  auto-wired adjacency has physical lengths (#58); familiarity-aware
  frontier exploration for discovery agents (#39); familiarity as a
  probability, with entrance seeding (#59); smoke as a gate on route
  optical depth (#123); cognitive-map growth recorded by `run_scenario`
  (#93).
- An FDS deck generated from a JuPedSim walkable WKT (#28), and placeable
  fires for discovery decks (#117).
- Warnings on silent slice-height and FED mismatches (#67).
- jupedsim 1.4.2 with `WarpDriverModel` (#85).
- Web GUI: FDS smoke overlay in the trajectory viewer (#36), playback
  speed and a live FED panel (#37), a dark theme (#38), results-only runs
  and scenario upload (#109), a theme switch, run controls and a working
  fullscreen viewer (#130), and a "Show equivalent Python" export (#329).
- Verification and test scenarios: ISO 20414 Tables 21 and 22 (#82, #83),
  stationary FED against FDS output (#74), blind-spawn discovery (#66),
  cognitive-map acquisition and exit visibility scenarios (#50, #54), and
  an in-repo world generator with invariant tests on generated decks
  (#97).
- CI runs the whole test suite (#381) and reports coverage on Codecov
  (#435). Golden snapshots pin rerouting decisions (#201), and tests pin
  route smoke sampling, scenario loading, spawn placement and direct
  steering (#438-#441).
- The FDS+Evac source of FDS 6.7.6 is bundled with an `evac.f90` notice
  as the reference for the ported equations (#205, #206), and the
  repository has community health files (#203).

### Changed

- fdsvismap 0.3.1 from PyPI replaces the git pin, pinned exactly because
  `visibility.py` patches its private `_get_visibility_array`. numpy is now
  at least 2.1. fdsvismap 0.3.1 also picks the horizontal slice nearest the
  height (fdsvismap#55), so the patch of fdsreader's slice lookup is
  removed; the extinction slice is still chosen by
  `fds_sampling.select_horizontal_slice` and passed by index. Vismap caches
  written before are rebuilt (cache format 5). `pyfds_evac/jpstooling.py`,
  `scripts/demo_vismap_phase0.py` and `scripts/demo_cognitive_map_vis.py`,
  which used the removed waypoint API and had no caller, are deleted.
- A run that reaches `max_simulation_time` with agents inside, or with flow
  agents still to enter, is incomplete: `success` is `False` (it was
  `True`, #139), the new `metrics["status"]` is `"incomplete"` (else
  `"completed"`), and `metrics["agents_not_spawned"]` counts the flow agents
  that never entered. The run manifest records the same under `outcome`,
  and the `run.py` summary line reads `Simulation incomplete: time limit
  reached after …`. `run.py` exits with status 2 for an incomplete run
  (outputs are still written); `scripts/run_and_plot.sh`,
  `scripts/sweep_queue_weight.py` and `assets/schroeder2015_route/run_p1.sh`
  accept it.

- **Seeded placements differ from earlier versions.** The start positions,
  their shuffle, the radius and v0 samples and the default pre-movement
  stream of each distribution are seeded from a blake2b hash of the run
  seed, the purpose and the distribution key, not from `seed + index`,
  `seed + 1000` or the bare seed. Distribution 1 under seed s used to draw
  what distribution 0 draws under seed s + 1, so ensembles over
  consecutive seeds reused streams; in the full-config initialiser all
  t=0 distributions shared one position stream and one pre-movement
  stream. An explicit `premovement_seed` still wins. The manifest's
  `agent_seeding` is now `spawn-key-blake2b-v2`; per-agent seeds are
  unchanged. Goldens and the cheap documented numbers were regenerated
  ([#360](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/360)).
- **An agent leaves at an exit when its centre enters the exit polygon**,
  not within its radius + 0.5 m of a target point inside it, so the door
  width sets the door flow. Before, a door drawn flush with a wall acted
  up to about 1.3 m wider and agents left from the room beside it.
  Checkpoints keep the distance rule. A single agent now leaves about
  0.3 s later; crowd results move by more, since the door now bounds the
  flow (the golden decks end up to 0.8 s later). The golden snapshots,
  the single-run pages, the RSET how-to and ISO Test 18 are regenerated;
  the with/without-fire how-to
  ([#391](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/391)),
  the Schröder study
  ([#388](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/388)),
  the web GUI screenshots
  ([#389](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/389))
  and the pages still on runs before #360 (A crowd in a real fire,
  familiarity, wayfinding;
  [#384](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/384))
  still show the earlier runs
  ([#349](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/349)).
- **The opening exit is ranked from each agent's position**, as
  re-evaluation ranks it, not from its spawn area's node. Before, every
  agent of one spawn area started towards the same exit, including agents
  beside another door; a shortest-path crowd in a room with two doors now
  splits between them. The golden snapshots and the example outputs are
  unchanged
  ([#350](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/350)).
- **Seeded outcomes differ from earlier versions.** Every per-agent random
  draw is seeded from the run seed and the agent's spawn key
  `(origin, spawn_index)`, through a blake2b hash that does not depend on
  the process, the platform or `PYTHONHASHSEED`, not from the JuPedSim id,
  a per-distribution index or a stream shared by all agents: the
  familiarity map, the start stage and target points, the journey variant
  of a flow spawn (now one draw per spawn, not per candidate position),
  the later direct-steering target, wait and next-stage draws (each on its
  own stream), the probabilistic gas and heat incapacitation thresholds
  and the reevaluation offset, `((spawn_index + 1) % steps) * dt`. The
  same scenario and seed therefore give other trajectories and counts than
  before; goldens and documented numbers were regenerated. A second run in
  the same process now gives the same results as a fresh one, under other
  JuPedSim ids, and a refused spawn no longer shifts the draws of later
  agents. The JuPedSim id stays the key of all per-agent state and output.
  Exit histories written before this change replay without error but pair
  agents whose draws differ; the manifest gains `agent_seeding`
  (`spawn-key-blake2b-v1`) to tell the two apart. A flow journey variant
  with a positive weight and no valid entry stage now fails at setup
  ([#353](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/353),
  [#198](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/198)).

- **Breaking:** a run that outlasts the FDS output stops instead of
  holding the last slice frame. `build_run_kwargs` (so `run.py` and the
  web GUI) rejects a `max_simulation_time` more than one slice output
  interval past the last frame of any FDS slice at setup, even when all
  agents would leave before `T_END` (the default of 300 s now fails on a
  shorter FDS run), and smoke, gas FED, heat FED and sign-visibility
  samples past that point raise `FdsHorizonError`, a `ValueError`, naming
  the quantity, the requested time and the last FDS time. Previously every
  such sample silently returned the last frame, so agents walked through
  frozen smoke and kept accumulating dose at the final concentrations.
  `--allow-fds-horizon-hold` (and `allow_horizon_hold=True` on
  `SliceFieldSampler`, `load_slice_sampler`, the `from_fds` constructors
  and `VisibilityModel`) restores the hold with one warning per quantity
  and a setup warning ([#340](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/340)).
- With `--enable-heat-fed` the default convective law is ISO 13571:2012
  Eq. (9), fully clothed,
  t = 4.1e8 · T^-3.61 min (T in °C, air with less than 10 % water vapour),
  in place of SFPE Handbook Eq. 63.44, t = 5e7 · T^-3.4 min. At 100, 150
  and 200 °C the time to heat FED = 1 grows from 7.9, 2.0 and 0.75 min to
  24.7, 5.7 and 2.0 min. `--heat-clothing unclothed`
  (`opts.heat_clothing`, `DefaultHeatFedModel(..., clothing="unclothed")`)
  selects ISO Eq. (10), which has the constants of Eq. 63.44, and gives the
  previous behaviour. The manifest records `heat_clothing`.
  `--heat-endpoint` and `--heat-fed-method total-flux` are unchanged
  ([#290](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/290)).
- The heat threshold is now the gas threshold `--fed-threshold`, as ISO
  13571:2012 asks for one threshold for FED and FEC (§5.4, §8.5). `--heat-fed-threshold` and
  `TenabilityConfig.heat_fed_threshold` default to none; a value sets a
  separate heat threshold, logs a warning that it departs from ISO, and is
  recorded in the manifest as `heat_fed_threshold_override`. Runs with the
  default `--fed-threshold 1.0` are unaffected; a run that changed
  `--fed-threshold` and wants the previous heat threshold passes
  `--heat-fed-threshold 1.0`. Both doses stay deterministic by default.
- Docs: Models › Heat explains where the 2.5 kW/m² radiant threshold of
  total flux acts: from about 285 °C at the default ε, with a step in the
  rate there and no radiant dose at the 200 °C anchor. A figure
  (`scripts/figures/heat_radiant_threshold.py`) shows it, and the
  verification table lists the total-flux, layer, `INTEGRATED INTENSITY`
  and threshold tests.
- Docs: Fundamentals › Incapacitation thresholds states what is known
  about the population spread of heat tolerance: SFPE Ch. 63 gives figures
  only for radiant lethality, which imply σ ≈ 0.22 if log-normal, not the
  borrowed 0.94. No code change; the heat threshold stays deterministic by
  default ([#225](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/225)).
- Heat FED tests take their expected values from the SFPE Handbook
  (5th ed., Ch. 63) instead of the code's own formula: Eq. 63.44 as printed
  (p. 2382), Table 63.20's convective rows (p. 2383) and Table 63.17's
  dry-air rows (p. 2375). Table 63.21 (p. 2385, whose values follow
  Eq. 63.45 despite its caption), Table 63.20's radiant rows and a
  walking-past-a-flame case are added as reference values for a future
  Eq. 63.45 option and the planned radiant term; they call no pyFDS-Evac
  code. The heat dose
  itself is unchanged
  ([#219](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/219)).
- Docs, heat dose: each formula states whether it takes incident flux, net
  flux or air temperature; Models › Heat and Limitations say that heat
  FED = 1 and gas FED = 1 are different endpoints that set the same
  `incapacitated` flag, told apart only by `incapacitation_cause`; the
  stale line references on Models › FED are corrected, the `fed.py` ones
  checked by a test
  ([#218](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/218)).
- Performance: the per-step speed update of direct-steering runs scans
  only the zones whose speed factor is not 1, precomputed once per run
  (`active_steering_zones`), and leaves an agent outside every such zone
  alone while its speed state (base speed, smoke, FIC, active zone) is
  unchanged. Trajectories are identical. Any code that writes an agent's
  `desired_speed` must also update its speed state (#240).
- Web GUI: a flag with a fixed set of choices (the heat clothing, endpoint,
  dose method, radiant source, regime and heat incapacitation mode) is a
  dropdown of its argparse choices with the CLI default preselected, in
  place of a free text field. A flag without a default offers a blank
  "default" entry.
- Web GUI: the FED section is titled "Purser / FDS" instead of
  "ISO 13571"; the coded form is the Purser sum as in the FDS `FED` function.
- `speed_law="fridolf"` now implements Eq. 7 (method 3) of
  Fridolf, Ronchi, Nilsson & Frantzich (2019),
  [doi:10.1016/j.tust.2019.04.016](https://doi.org/10.1016/j.tust.2019.04.016),
  also in Fridolf et al. (2018, SFPE extended abstract), a summary of their
  2016 SP report:
  w = min(v₀, max(0.2, v₀ − 0.34 (3 − V))) with V = C/K. C = 3 is the
  coded FDS default; the 2019 paper used A = 2 for reflecting targets. The
  reduction is additive with an absolute 0.2 m/s floor, and speed is
  unchanged above 3 m. The option used to compute V/(V+2), which has no
  known source; that law is removed and cannot be selected. New
  `SmokeSpeedConfig` fields: `fridolf_slope`, `fridolf_visibility_threshold_m`,
  `fridolf_min_speed_m_per_s`. `SmokeSpeedModel.sample` and `speed_factor`
  take an optional `free_speed_m_per_s` (1 m/s, method 1, if omitted)
  ([#146](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/146)).

Defaults now follow FDS+Evac where a mechanism has a direct FDS+Evac
counterpart ([#157](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/157)).
See [Defaults follow FDS+Evac](https://pedestriandynamics.org/pyFDS-Evac/docs/getting-started/coming-from-fds-evac/#defaults-follow-fdsevac).

- Smoke, heat and visibility are sampled at 1.6 m (`HUMAN_SMOKE_HEIGHT`)
  instead of 2.0 m.
- The irritant (FIC) slowdown is off by default. `--enable-fic-speed` turns it
  on.
- The HCN term of the FED subtracts NO + NO2 and uses the offset 1/220, as the
  FDS `FED` function that FDS+Evac calls, instead of NO2 alone with 0.0045
  (FDS+Evac Guide Eq. 15)
  ([#159](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/159)).
- The CO2 hyperventilation factor is 1 when there is no CO2 (or no CO2
  reading), as in the FDS `FED` function, instead of exp(2.0004)/7.1 = 1.0411.
  FED from CO, HCN, NOx and irritants in CO2-free air is therefore about 4 %
  lower; this matches FDS's `FED_FIC` verification case. Runs with FDS's
  default ambient CO2 (about 0.04 vol %) are unaffected; only cells with
  exactly zero CO2 change
  ([#194](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/194)).
- The O2 term of the FED applies below 20 % O2 instead of 19.5 %.
  `--o2-threshold-percent` sets the threshold.
- A spawn area that sets no pre-movement gets a constant 10 s (`PRE_MEAN`),
  with a warning, instead of 0 s. A `constant` pre-movement distribution is
  added.
- A spawn area that sets no `v0` walks at 1.25 m/s (`VEL_MEAN`) instead of
  1.2 m/s.
- The convective heat dose is off by default. `--enable-heat-fed` turns it on;
  before, it was on whenever the FDS output had a `TEMPERATURE` slice.
- Heat incapacitation is deterministic by default: every agent stops at the
  heat threshold, which is `--fed-threshold` unless `--heat-fed-threshold`
  overrides it. No population spread for heat is published; the
  log-normal draw with σ = 0.94, borrowed from the gas dose, is opt-in with
  `--heat-incapacitation-mode probabilistic`.
- Gas incapacitation is deterministic by default: every agent stops at
  `--fed-threshold` (1.0), as in FDS+Evac. The per-agent log-normal draw
  (σ = 0.94, fitted to NIST TN 1797) is opt-in with
  `--incapacitation-mode probabilistic`. The web GUI's default output folder
  is `results/<scenario>/deterministic/…` accordingly
  ([#235](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/235)).

- Rerouting is on by default and re-evaluates every 1 s (#41).
- `w_queue` defaults to 0; the Station case sets its calibration against
  Fahy Table 2 (0.03) in its deck (#90, #94).
- Clear-air visibility comes from fdsvismap (#95), and the cognitive map
  is the only visibility gate (#53). Discovery decks without FDS data use
  clear-air sight instead of unlimited sight (#117).
- `EXTINCTION` is no longer read as the smoke extinction coefficient; a
  deck needs a `SOOT EXTINCTION COEFFICIENT` slice (#71).
- Repository layout: `fds_data/` and `testing directory/` are merged into
  `fds_directory/` (#47), and `assets/demo` is `assets/t_junction`; unused
  scenarios are retired (#51).

**Migration.** To reproduce results from earlier pyFDS-Evac versions, pass
`--smoke-slice-height 2.0 --enable-fic-speed --o2-threshold-percent 19.5
--enable-heat-fed --heat-incapacitation-mode probabilistic
--incapacitation-mode probabilistic` to `run.py` (or set the matching `opts` attributes), and
give every spawn area `"use_premovement": false` and `"v0": 1.2` unless it
already sets them. Python callers that build the models themselves pass
`TenabilityConfig(enable_fic_speed=True, heat_incapacitation_mode="probabilistic",
incapacitation_mode="probabilistic")`,
`DefaultFedConfig(o2_threshold_percent=19.5, slice_height_m=2.0)`, and
`slice_height_m=2.0` to `SmokeSpeedConfig`, `ExtinctionField.from_fds`,
`FdsHeatField.from_fds` and `VisibilityModel`; a heat dose needs a
`DefaultHeatFedModel` passed to `run_scenario`, as before. The earlier HCN form is not available: it was a
documentation error in the FDS+Evac Guide, and it differs from the current
one only when NO is present or by the offset, 4.5 × 10⁻⁵ /min.

### Removed

- Python 3.11 support. pyFDS-Evac requires Python 3.12, 3.13 or 3.14
  (`requires-python = ">=3.12,<3.15"`). Python 3.15 waits on jupedsim
  wheels for it.
- The unused modules `pyfds_evac.config` (`SimulationConfig`) and
  `pyfds_evac.utilities` (`distance`); nothing in the package has
  imported them since `jpstooling.py` was removed. Code that imports
  them breaks; this is acceptable for 0.2.0 under SemVer 0.x. Also the
  three images in `assets/t_junction/` written by the removed demo
  scripts (`cognitive_map_evolution.png`, `vismap_aset.png`,
  `vismap_coverage.png`).
- Web GUI: the Cumulative FED results chart, the FED sparkline and the mean
  FED line. The viewer and the live chart show the highest FED of any agent
  at each time.

- The notebooks and `Gregory.md` (#205).

### Fixed

- A directional sign is legible from its own grid cell. fdsvismap before
  0.3.0 divided 0 by 0 there, so the sign was hidden and
  `visibility_to_node` returned `None`. Only FDS-backed discovery runs whose
  agents pass a sign's cell change; on the first FDS case 70 of 150 agents
  leave instead of 72.
- Exits are priced from where the agent stands (#451). The path search
  starts at the agent's position and never routes back through the node the
  agent last left, the first leg is charged the smoke on the
  walk ahead of the agent rather than a share of its edge's mean, and the
  current exit is never priced above the path the agent walks
  (`rank_routes(current_path=...)`, #186). An agent past smoke near its
  origin no longer leaves an exit a few seconds ahead for a detour, and a
  walk back through smoke is charged. Without `agent_position` nothing
  changes; FED keeps the share of the first segment (#171).
- The mean extinction of a route edge (`k_avg`) averaged over all samples
  of its polyline, so short segments and interior vertices weighed too much
  and the mean depended on where the routing engine put its vertices. It is
  now the length-weighted mean of the per-segment means; the sample points
  and the worst sample `k_max` are unchanged, and so are two-point edges
  and clear-air runs. Route costs and choices in smoke change (#437).
- In a deck with journeys, agents of a distribution without a journey whose
  nearest exit is throttled stood at their spawn points until the time
  limit. They are now steered to that exit and leave through it under its
  cap (#434).

- A point that some loaded gas slices cover and others do not raises
  `ValueError`, as heat already did, instead of reading ambient air for
  every gas ([#427](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/427)).
- An agent off the vismap grid no longer reads the sign visibility of the
  nearest edge cell. It sees a sign in clear air when the sign is within its
  reading distance, measured from the agent, and `visibility_to_node`
  returns `None` there. A sign off the grid logs a warning, as fdsvismap
  casts its sight lines from the grid edge
  ([#426](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/426)).
- An agent could stop 0.01-0.02 m short of an exit polygon drawn thinner
  than about 0.25 m against a wall, held there by the wall or a door jamb,
  and was never removed; about one run in ten of the Schröder room configs
  ran to `max_simulation_time` with one or two agents left. An exit now
  also counts as reached when the agent's centre is within 0.03 m of its
  polygon. A single agent leaves about 0.02 s earlier (clear ISO corridor
  79.26 -> 79.24 s); the golden decks end 0.02-0.10 s earlier. The golden
  snapshots, the single-run pages, the RSET how-to and ISO Test 18 are
  regenerated; pages already on earlier runs keep their notes
  ([#401](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/401)).
- A flow spawn whose setup failed after `add_agent` had succeeded was
  retried at the next candidate position, which left a half-initialised
  agent in the simulation and added a second one. The error is now raised
  ([#353](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/353)).

- Sign legibility and the route `next_node_not_visible` gate read the
  horizontal extinction slice nearest `--smoke-slice-height`, the slice
  walking speed and FED read, with the same warning when it is more than
  0.5 m away. fdsvismap used fdsreader's `get_nearest`, which returns the
  first horizontal slice declared, or a vertical one through the plan
  origin. Visibility caches are rebuilt (format 4)
  ([#296](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/296)).

- `scripts/fed_heat_hand_calc.py` cited "ISO TS 13571 eq. 5" for
  t = 5e7 · T^-3.4; it is ISO 13571:2012 Eq. (10) (§8.3.2), equal to SFPE
  Eq. 63.44
  ([#291](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/291)).

- A heat-only FDS case (TEMPERATURE slice, no SOOT EXTINCTION COEFFICIENT
  slice) no longer crashes `run.py`. Smoke speed reduction is then off and
  the visibility model falls back to clear air, each with a warning, so
  `--constant-extinction 0 --no-visibility` is no longer needed
  ([#248](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/248)).

- The uniform heat rooms `assets/fed_incap_heat_{100,150,200}c` set `TMPA`
  to the deck temperature instead of 20 °C. FDS started the walls and the
  radiation field at `TMPA`, so the room lost heat at t = 0 and settled
  0.7–1.8 % below its `&INIT` value. It now holds the deck value to within
  1 mK, and the deterministic heat stops of the verification page are the
  closed form at the deck temperature (476 / 120 / 46 s, were 487 / 125 /
  48 s). FDS's device output is committed so CI checks the hold
  ([#253](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/253)).
- With direct steering, an agent slowed by smoke outside every speed zone
  kept its reduced speed once the smoke factor returned to exactly 1 (for
  example on walking into air with K = 0). The restore now also writes when
  the factors last applied were below 1, so the agent walks at its free speed
  again. Runs where agents leave smoke for clear air change; the rerouting
  golden snapshots are regenerated
  ([#246](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/246)).
- The gas FED read the first CO, CO2 and O2 slice listed in the FDS deck,
  whatever its height, instead of the slice nearest `--smoke-slice-height`
  (1.6 m). It now selects each species like smoke speed and heat do. Slice
  selection also skips vertical (PBX/PBY) slices, whose mid-height could
  look closest to the requested height; a quantity with only vertical slices
  now raises an error
  ([#238](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/238)).
- The FDS slice sampler reads the value nearest to the query point: the
  nearest node of a node-centred slice (the FDS default) and the nearest
  cell centre of a `CELL_CENTERED=T` slice, including on stretched grids.
  It used to space the values evenly with half-cell offsets, which on
  node-centred slices read the wrong node for about a quarter of positions
  ([#212](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/212)).
- The O2 hypoxia rate was 60 times too slow (#35, #52), and the FIC speed
  factor compounded every step (#73).
- Routing: first-segment FED and smoke were charged twice mid-leg (#44);
  each agent is routed from its own spawn area (#46) and no-journey agents
  are rooted at their spawn area (#64); distances are measured along the
  walkable area (#48); every route is priced from the agent's position
  (#65) and the frontier is chosen from where the agent stands (#70); the
  first exit comes from the agent's cognitive map, not geometry (#87);
  arrival learning is gated by visibility and learns reverse edges (#96);
  stale `path_choices` no longer trap discovery agents (#107); a stage's
  node lies inside its polygon, at its most open interior point for a
  concave stage (#105, #108).
- Web GUI: trajectories play at the recorded rate (#106), and agents are
  drawn at map scale (#111).
- Assets: the ISO-table21 deck runs (#79), and the Station doorways open
  to their clear width (#110, #112).
- Docs for the release (#470): the ISO Test 19 page runs
  `build_geometry.py` with `uv run python` (#464); bundle READMEs quote
  the printed rows verbatim (#465); the how-tos, limitations,
  first-fds-case and routing pages describe incomplete runs and exit
  status 2 (#442); the with/without-fire study and the cognitive-map
  memory example are re-run on the current code (#391).
