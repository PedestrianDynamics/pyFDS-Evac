---
title: "Scenario assets"
weight: 17
---

Scenario definitions are stored in [`assets/`](../assets/).
[`assets/README.md`](../assets/README.md) indexes the folders and the file
conventions; what each one proves, and where that proof is checked, is below.

- **ISO-table21**: **ISO 20414:2020 Table 21** (Test 18, *reduced visibility vs
  walking speed*) — corridor 2 m x 100 m, one occupant at 1,25 m/s, constant
  extinction. See [the asset README](../assets/ISO-table21/README.md) for the
  clause-by-clause comparison, including the two places we deviate. Proves the smoke speed reduction law is applied correctly end to end:
  `test_iso_table21_constant_extinction_matches_expected_time_ratio` runs the
  scenario clear and then under a `ConstantExtinctionField` at five extinction
  coefficients (0.5, 1.0, 3.0, 7.5, 10.0 /m), asserting the ratio of evacuation
  times matches `1 / speed_factor_from_extinction(k)` within 8% and that every
  recorded `speed_factor` equals the expected one exactly. Doubles as the
  standard small fixture in `test_progress_callback.py`, `test_webapp.py` and
  `test_fed.py`, which use it for its size rather than its ISO provenance.
- **ISO-table22**: **ISO 20414:2020 Table 22** (Test 19, *occupant
  incapacitation by fire/smoke*) — room 10 m x 10 m x 3 m, one occupant held
  still by ISO's prescribed pre-evacuation time above 10 000 000 s. See
  [the asset README](../assets/ISO-table22/README.md). The gas field is stubbed, so
  it verifies the accumulator, not the FDS coupling; the coupled four-case
  version is [`iso_table22_coupled`](../assets/iso_table22_coupled/README.md). One
  agent with `v0` forced to 0 in a fixed gas concentration; config and geometry only, no deck. Proves the
  runtime FED accumulator agrees with the closed form:
  `test_iso_table22_stationary_runtime_matches_analytic_threshold_time` takes
  the analytic FED=1.0 time from `time_to_fed_threshold_s()` and asserts the
  observed crossing lands within one timestep of it, that `fed_max >= 1.0`, and
  that the agent does not evacuate. Holding the gas inputs constant is
  deliberate; this tests the accumulator, not the gas sampling. Also backs the
  FED history throttling test.
- **t_junction**: T-corridor FDS scenario with cable fire, two exits (A open, B smoke-accumulating),
  200 visitors spawning in the branch; used for visibility-aware routing and cognitive
  map verification. Includes `config_full.json` and `config_discovery.json`
  for familiarity-tier comparison. The rerouting mechanism itself is verified by
  scenario **S4** in
  [`tests/verification/test_s4_tjunction_reroute.py`](../tests/verification/test_s4_tjunction_reroute.py)
  (control arm and null-field control both record zero switches; smoke forces
  every agent B→A and never the reverse; reroute latency stays within the
  configured interval; switch count is reproducible under a fixed seed). Note
  that S4 builds its own T-corridor via `harness.t_junction_scenario()` with a
  synthetic smoke field rather than loading this asset, so the mechanism is
  covered but the deck and config here are not exercised by the suite. This
  config uses flow spawning deliberately: under by-number placement an agent's
  route-eval source node is its assigned exit, which makes rerouting degenerate
  ([issue #21](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/21)).
- **fed_incap_co_2000ppm** / **fed_incap_co_4000ppm** / **fed_incap_co_8000ppm**:
  FED accumulation and probabilistic-incapacitation verification against a
  hand-calculated reference (`fed_hand_calc.py`), at three constant CO
  concentrations (2000/4000/8000 ppm) in a sealed, spatially uniform room —
  removing gas-transport physics as a variable isolates the FED/incapacitation
  *pipeline* logic. 100 non-evacuating agents circling a rectangular path, FDS
  domain split across 4 MPI meshes to confirm gas data is consistent at mesh
  boundaries. All three concentrations currently match the hand-calc's FED=1.0
  crossing time to <0.5% (2000 ppm: 782.4 s hand-calc vs 786 s simulated;
  4000 ppm: 382.3 s vs 384 s; 8000 ppm: 186.6 s vs 187 s). Verified by running
  the cases and comparing, not by a test in `tests/`. (See the FDS input
  pitfalls on the
  [FED page](https://pedestriandynamics.org/pyFDS-Evac/models/fed/#fds-input-pitfalls)
  for the conflicting-`&INIT` pitfall this suite surfaced.) Full writeup:
  `docs/testing-homogeneous.md`.
- **Cognitive Map Memory**: 4x32 m corridor with a side alcove, 20 `discovery`
  agents. The side exit's sign faces west and is legible only from
  `y ∈ [12.5, 27.5]` on the centreline — a window that falls out of
  `view_angle * max_vis >= distance` rather than being tuned, and that
  `build_geometry.py` recomputes and asserts. Proves the cognitive map does the
  one thing a visibility query cannot: **remember**. The side exit is unknown at
  spawn, enters the map on crossing `y=12.5`, and is *still* there at `y=30`
  where the sign is long unreadable. Persistence is the load-bearing claim —
  delete the expansion rules and acquisition still appears to work for any agent
  starting inside the window. A third test closes the loop to routing: a
  remembered-but-illegible exit must still be routable. `scripts/generate_cognitive_map_states.py` renders the
  three states (unknown / legible now / remembered), and the amber band is the
  memory made visible. Checked by `tests/test_cognitive_map_memory.py`.
- **FIC vs FED Speed**: 4x50 m sealed corridor, 30 agents, one exit. The gas is
  *prescribed* by a single `&INIT` (CO at 2000 ppm, acrolein at 10 ppm) rather
  than burned, so concentration is constant in space and time and the only
  variable across runs is which tenability rules are enabled — set from the
  command line (`--disable-tenability`, `--fic-alpha 0`, or the default).
  Separates the two rules by timescale: **FED is a cumulative dose with a
  threshold and does nothing below it** (0.079 /min here, so 13 minutes to reach
  FED = 1, against a ~33 s egress), while **FIC responds instantaneously**
  (`FIC = 0.5`, speed factor 0.65, so ~51 s). The prediction is stated in the
  asset README before running and is falsifiable: if FED materially slows an
  agent over a minute of exposure, the model or the reasoning is wrong. A
  control test records that acrolein is *not* only an irritant — it also sits in
  FED's Fractional Lethal Dose sum, so removing it takes 100% of the speed
  penalty but only 3% of the dose rate, and that asymmetry is what makes the two
  rules separable. Also pins the O2 hypoxia term against the published closed
  form (Fire Safety Journal, surrogate-gases paper, Eq. 9) rather than against
  our own docs. Checked by `tests/test_fic_vs_fed_speed.py`.
- **Exit Visibility Alpha**: 4x30 m corridor, 40 `discovery` agents, two
  exits. The two configs differ in exactly one value — the viewing bearing
  (`alpha`) of the near exit's sign — so any difference in exit choice is
  attributable to sign orientation and nothing else. Proves that legibility
  decides cognitive-map membership, and membership decides the exit: at
  `alpha=0` both exits enter the map and agents take the nearer one; at
  `alpha=180` the near exit never enters the map and agents walk 10 m further
  to the only exit they know about, even though distance favours the near one
  by more than 2:1. The near exit is *absent*, not rejected — a stronger claim,
  since a rejected route still appears in the ranking and the all-rejected
  fallback can reinstate it. Checked by
  `tests/test_exit_visibility_alpha.py`, which needs no FDS output: it
  reimplements fdsvismap's clear-air rule (`view_angle * max_vis >= distance`)
  so the test exercises the routing decision rather than the third-party
  solver. A companion test pins that a `full`-familiarity agent ignores the
  bearing entirely — signs are wayfinding information and bind only where
  knowledge is incomplete. The folder README documents the **30 m visibility
  ceiling** that makes a sign illegible at any bearing, and how much tighter it
  becomes once smoke is present (`c / K̄`, so 6 m at `c=3`, `K̄=0.5`).
- **Familiarity Test Full** / **Familiarity Test Discovery**: `SocialForceModel`
  scenario on a hand-drawn maze-like floor plan (20x18 m, 0.1 m walls, 1.2 m
  doors throughout, generated parametrically by each folder's
  `build_geometry.py`), differing only in the spawn distribution's
  `familiarity` value. A matching fire deck lives at
  `assets/familiarity_test_full/familiarity_test.fds` (real
  combustion via `&REAC`, not a prescribed `&INIT`; walls mirror the
  walkable geometry exactly so smoke propagates through the same
  doorways agents use). These two configs use the legacy `journeys`/
  `transitions` shape directly (the web editor's `journeys_v2` format is
  auto-migrated to this shape by `load_scenario`, but was hand-converted
  here to add the extra edge below). The maze's start room is one open
  box that connects directly to the checkpoint outside the exit door
  (`jps-checkpoints_0 → jps-checkpoints_3`), completely bypassing the
  scripted checkpoint tour through the rest of the maze — a real ~39%
  shorter route (32 m vs 52 m) that's declared as an extra graph edge
  (tagged `journey_id: "shortcut"` in `transitions`, invisible to the
  static spawn-time journey) for the rerouting/cognitive-map system to
  find. Run with `--enable-rerouting` (no `--fds-dir`/vis-cache needed —
  divergence here is pure-distance, not smoke-driven) to see it: `full`
  agents know the whole graph immediately and reroute onto the shortcut
  within the first reevaluation tick; `discovery` agents start knowing
  only the spawn's declared neighbor and explore the nearest
  known-but-unvisited doorway at each step — which for this maze's
  geometry happens to coincide with the original scripted tour the whole
  way, so they end up taking the long route without ever finding the
  shortcut. Verified: `full` evacuates in 35.1 s vs `discovery`'s 75.1 s
  (both 20/20 evacuated; see the results table in
  [`docs/testing-familiarity.md`](testing-familiarity.md)).
