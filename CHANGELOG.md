# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

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

### Removed

- Web GUI: the Cumulative FED results chart, the FED sparkline and the mean
  FED line. The viewer and the live chart show the highest FED of any agent
  at each time.

### Changed

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

### Fixed

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
