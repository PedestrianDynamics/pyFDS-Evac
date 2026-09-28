# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

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
- `--heat-fed-method total-flux` (opt-in, with `--enable-heat-fed`; default
  `convective`): the heat dose is q^1.33/D (SFPE Handbook Ch. 63 Eq. 63.43)
  with q the heat flux to the skin of Eq. 63.49, both terms divided by 1000
  together, and no 2.5 kW/m² threshold (spec 016). D is the dose of
  `--heat-endpoint`, the fatal 16.667 without it. `--heat-emissivity` (0.5),
  `--heat-convective-coefficient` (5) and `--heat-skin-temperature` (35 °C)
  set the flux; their defaults are assumptions. The FED history gains
  `heat_flux_kw_m2` and the manifest `heat_fed_method` and
  `heat_flux_parameters`. This is the head-in-smoke regime
  ([#223](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/223)).
- `--heat-endpoint {tolerance,injury,fatal}` (opt-in, with
  `--enable-heat-fed`): the heat dose uses the convective law of that
  endpoint, SFPE Handbook Ch. 63 Eq. 63.45, 63.46 or 63.47, paired with its
  radiant dose (1.33, 10, 16.667; the Handbook prints 16.7, spec 016
  fixes 16.667). The FED history gains `heat_endpoint`,
  `heat_outside_validity` (above 205 °C, an assumed limit, or a non-finite
  temperature) and `heat_humidity` (`unknown`, as humidity is not sampled),
  and the run manifest records `heat_endpoint` and `heat_validity`. Without the option the dose stays
  Eq. 63.44
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

### Removed

- Web GUI: the Cumulative FED results chart, the FED sparkline and the mean
  FED line. The viewer and the live chart show the highest FED of any agent
  at each time.

### Changed

- Performance: the per-step speed update of direct-steering runs scans
  only the zones whose speed factor is not 1, precomputed once per run
  (`active_steering_zones`), and leaves an agent outside every such zone
  alone while its speed state (base speed, smoke, FIC, active zone) is
  unchanged. Trajectories are identical. Any code that writes an agent's
  `desired_speed` must also update its speed state (#240).
- Web GUI: the FED section is titled "Purser / FDS" instead of
  "ISO 13571"; the coded form is the Purser sum as in the FDS `FED` function.
- **Breaking.** `speed_law="fridolf"` now implements Eq. 7 (method 3) of
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
- Heat incapacitation is deterministic by default: every agent stops at
  `--heat-fed-threshold`. No population spread for heat is published; the
  log-normal draw with σ = 0.94, borrowed from the gas dose, is opt-in with
  `--heat-incapacitation-mode probabilistic`.

**Migration.** To reproduce results from earlier pyFDS-Evac versions, pass
`--smoke-slice-height 2.0 --enable-fic-speed --o2-threshold-percent 19.5
--enable-heat-fed --heat-incapacitation-mode probabilistic` to `run.py` (or set the matching `opts` attributes), and
give every spawn area `"use_premovement": false` and `"v0": 1.2` unless it
already sets them. Python callers that build the models themselves pass
`TenabilityConfig(enable_fic_speed=True, heat_incapacitation_mode="probabilistic")`,
`DefaultFedConfig(o2_threshold_percent=19.5, slice_height_m=2.0)`, and
`slice_height_m=2.0` to `SmokeSpeedConfig`, `ExtinctionField.from_fds`,
`FdsHeatField.from_fds` and `VisibilityModel`; a heat dose needs a
`DefaultHeatFedModel` passed to `run_scenario`, as before. The earlier HCN form is not available: it was a
documentation error in the FDS+Evac Guide, and it differs from the current
one only when NO is present or by the offset, 4.5 × 10⁻⁵ /min.

### Fixed

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
