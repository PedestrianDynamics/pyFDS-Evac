# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

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
