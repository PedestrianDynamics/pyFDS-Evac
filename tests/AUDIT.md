# Test-quality audit

Findings from walking `tests/` against the smells in
[testing guidelines §4](../docs/TESTING_GUIDELINES.md#4-reviewing-a-pull-request),
with the results of targeted mutation checks (issue #816). Each area is
audited in its own pull request; a finding stays here until it is fixed.

Mutation checks are run by hand with `scripts/mutation_check.py <area>`.
They run the area's tests as CI does, without `external_data`, and show
which tests catch a representative defect, not that the code is right.

## FED (gas)

Module `pyfds_evac/core/fed.py`, gas terms only; the heat terms are a
separate area.

Audited files: `test_fed.py`, `test_fed_rate_memo.py`,
`test_fic_vs_fed_speed.py`, `test_fed_margin_deck.py`, and in
`verification/`: `test_fed_verif.py`, `test_fed_fic_all_zones.py`,
`test_fed_slice_height.py`, `test_s1_corridor_fed.py`. These are also the
tests the mutation check runs, so its results are relative to this list.

Not yet audited, though they exercise gas FED: `test_iso_table22_coupled.py`,
`test_incapacitation.py`, `test_incapacitation_absorbing.py`,
`test_scheduled_exits.py` (additive FED), `test_smoke_blind.py`,
`verification/test_fds_evac_guide_cases.py`.

### Mutation checks

`python scripts/mutation_check.py fed`: 12 of 12 mutants killed.

| Mutant | Kind | Killed before the audit |
|---|---|---|
| CO % to ppm × 1000 instead of × 10000 | unit conversion | yes |
| `accumulate_default_fed` duration not divided by 60 | unit conversion | yes |
| `DefaultFedModel.advance` dt not divided by 60 | unit conversion | no: added `TestModelStepUnits` |
| `DefaultFedModel.advance_with_components` dt not divided by 60 | unit conversion | only by the S1 corridor runs: added `TestModelStepUnits` |
| O2 threshold `>=` to `>` | reversed comparison | yes |
| HV_CO2 zero-CO2 guard `<=` to `<` | reversed comparison | yes |
| `time_to_fed_threshold_s` remaining `<=` to `<` | reversed comparison | no: added the already-reached boundary test |
| NOx term dropped from the sum | removed term | yes |
| HV_CO2 multiplier dropped | removed term | yes |
| NOx protection dropped from the CN term | removed term | yes |
| Offset 2.0004 dropped from HV_CO2 | removed term | yes |
| `- 1` dropped from the CN term | removed term | yes |

### Fixed

| Test | Smell | Change |
|---|---|---|
| `test_fed.py::test_run_scenario_throttles_fed_history_to_update_interval` | missing boundary | `len <= 6` let a single row pass; now the exact times 0, 0.5, 1.0, 1.5, 2.0 s |
| `test_fed.py::test_no2_ppm_contributes_to_fed_rate` | weak oracle, unsound claim | docstring said NO2 enters the CN term; now pins `20/1500 + 20/1900` |
| `verification/test_fed_verif.py::test_a2_7_threshold_draws_are_seed_reproducible` | weak oracle | a fresh `Random(99)` per draw made all 50 draws equal; one generator per list now |
| `verification/test_s1_corridor_fed.py::test_probabilistic_run_is_reproducible_under_fixed_seed` | rotten green | `[] == []` passed if nobody collapsed; now asserts a non-empty list. Comment t* corrected to 24.3 s |
| `test_fed_margin_deck.py::test_rival_in_the_band_is_admitted` | rotten green | "no refusal in the band" passed if no rival row was in the band; now asserts such rows exist |

### Open

The rows below come from a review pass; the hand-calculated values were
rechecked, but each smell is confirmed only when its row is fixed.

| Test | Smell | Proposed contract |
|---|---|---|
| `test_fed.py::test_constant_exposure_step_integration_matches_threshold_time`, `test_new_term_threshold_time_matches_step_integration`, `test_iso_table22_stationary_runtime_matches_analytic_threshold_time` | circular, unlabelled | Both sides call `default_fed_rate_per_minute`. Label as consistency checks; add an independent anchor, e.g. CO 1000 ppm only: `t = 60 / (2.764e-5 * 1000**1.036) = 1692.8 s`; Table 22 combined (CO 1000 ppm, CO2 5 %, O2 12 %): 456.0 s |
| `test_fed.py::test_constant_exposure_accumulation_matches_closed_form` | circular | `expected` uses the production rate; label as a linearity check |
| `test_fed.py` ambient case (`time > 1e7`) | weak oracle | `time_to_fed_threshold_s(DefaultFedInputs()) == math.inf` |
| `test_fed.py` irritant and NO tests (`rate_x > rate_base > 0`) | weak oracle | Pin `C / Ct` per species from guide Table 2, e.g. HCl 100 ppm: `100 / 114000` |
| `test_fed.py::test_fds_evac_guide_stationary_fed_cases_reach_fed_one_consistently` | weak oracle | Replace the dominant-term branches with hand-calculated times per case |
| `test_fed.py` runtime-plot tests | weak oracle | Only file existence is checked; compare runtime and analytic curves within `rate * dt / 60`, or label as plotting smoke tests |
| `test_fic_vs_fed_speed.py` | self-fulfilling | The speed factor is test-local; assert `TenabilityConfig` defaults equal the builder constants or drive the runtime speed path. Pin the FED rate `0.0787` 1/min instead of `dose < 0.1` |
| `verification/test_fed_verif.py::test_a2_4_*` | circular | FIC coefficients imported from production; hard-code `90/900 + 24/120 = 0.3` with the Table 2 source |
| `verification/test_fed_verif.py` speed-factor test | self-fulfilling | Formula defined in the test; exercise it through `run_scenario` or label it as documenting the contract |
| `verification/test_fed_verif.py` lognormal CDF and median | tolerance camouflage | `abs=0.03` at n = 20000 is about 8 sampling σ; justify or tighten to about 4 σ |
| `verification/test_fed_verif.py::test_a2_7_rate_is_pure_function` | weak oracle | `f(x) == f(x)`; replace with a hand-calculated value |
| `verification/test_fed_fic_all_zones.py` | tolerance, missing boundary | `rel=1e-3` against 4–5 significant FDS digits is not justified; no just-above-zero CO2 case for the documented 1 → 1.041 step of HV_CO2 |
| `verification/test_s1_corridor_fed.py` threshold-time test | tolerance | 0.5 s of early slack, though the crossing cannot precede t*; use `t* <= observed <= t* + update interval` |
| `verification/test_s1_corridor_fed.py` population test | tolerance, single seed | `0.35..0.65` on one seed with n = 120 (binomial σ 0.046); add the derivation or several seeds (guidelines §3.8) |
| `verification/test_s1_corridor_fed.py` | unsound physics claim (check) | 60,000 ppm CO through Eq. 13 without a stated validity range; state the range or mark it as a wiring test |

## Heat

Module `pyfds_evac/core/fed.py`, heat terms: the ISO 13571 convective law,
the SFPE Ch. 63 endpoint laws, the total-flux method (Eq. 63.43, 63.49),
the layer and INTEGRATED INTENSITY radiant terms and the ISO 2.5 kW/m2 cut.

Audited files: every `test_heat_*.py`, `verification/test_heat_*.py` and
`verification/test_s6_heat_fed.py`. These are also the tests the mutation
check runs.

### Mutation checks

`python scripts/mutation_check.py heat`: 15 of 15 mutants killed.

| Mutant | Kind | Killed before the audit |
|---|---|---|
| Convective law with T in K instead of deg C | unit conversion | yes |
| `accumulate_default_heat_fed` duration not divided by 60 | unit conversion | yes |
| `DefaultHeatFedModel.advance` dt not divided by 60 | unit conversion | yes |
| Gas temperature not converted to K in Eq. 63.49 | unit conversion | yes |
| Radiant term of Eq. 63.49 left in W/m2 | unit conversion | yes |
| Layer flux left in W/m2 | unit conversion | yes |
| ISO radiant cut `<` to `<=` (2.5 kW/m2 counts) | reversed comparison | yes, by one test |
| Validity flag `>` to `>=` at 205 deg C | reversed comparison | no: 205 and 205.5 deg C cases added |
| U factor range `<=` to `<` | reversed comparison | yes |
| Second term of the endpoint law dropped | removed term | yes |
| Exponent 1.33 of Eq. 63.43 dropped | removed term | yes |
| ISO radiant cut not applied to the dose | removed term | yes |
| Skin emission not subtracted from U | removed term | yes |
| View factor dropped from the layer flux | removed term | yes |
| Convection dropped from the model flux | removed term | yes |

### Fixed

| Test | Smell | Change |
|---|---|---|
| `test_heat_endpoint.py::test_validity_limit_is_the_highest_convective_data_point` | weak oracle | `200 <= limit <= 210`; now `== 205.0` |
| `test_heat_endpoint.py::test_samples_above_the_data_are_flagged` | missing boundary | adds 205 deg C (not flagged) and 205.5 deg C (flagged) |
| `verification/test_heat_endpoint_coupled.py::_check_row_flags` | weak oracle | checked only rows below 180 or above 250 deg C; now every row against `T > 205` |
| `verification/test_heat_fed_verif.py::test_a3_6_threshold_draws_are_seed_reproducible` | weak oracle | a fresh `Random(99)` per draw; one generator per list now |
| `verification/test_heat_fed_verif.py::test_a3_6_rate_is_pure_function` | weak oracle | `f(x) == f(x)`; now `test_a3_6_rate_at_130_c_matches_iso_eq_9` pins `1 / (4.1e8 * 130**-3.61)` |
| `verification/test_heat_fed_verif.py::test_a3_2_rate_is_zero_only_at_or_below_zero_degrees` | missing boundary | dropped a line that tested the standard library; adds the rate at 1e-3 deg C |
| `verification/test_heat_room_decks.py::test_deck_init_matches_its_name` | rotten green | passed for a deck with no `&INIT TEMPERATURE`; now asserts one exists |
| `verification/test_heat_radiometer.py::test_uniform_room_gives_a_quarter_of_u` | rotten green | loop over plates had no emptiness guard (`external_data`) |
| `test_heat_total_flux.py::test_model_rejects_unknown_method` | weak oracle | accepted `TypeError`; now `ValueError` with its message |
| `test_heat_total_flux.py::test_cli_default_method_is_not_total_flux`, `test_heat_layer_flux.py::test_cli_default_is_not_the_layer_regime` | weak oracle | accepted `None`; now the exact defaults |
| `test_heat_layer_flux.py::test_layer_flux_sign` | weak oracle | `< 0`; now `sigma (293.15**4 - 308.15**4) / 1000` |
| `test_heat_integrated_intensity.py::test_cli_help_states_range_no_default_and_excess` | weak oracle | `"1" in text`; now `"[0.25, 1]"` |
| `verification/test_heat_layer_flux_coupled.py::test_layer_case_is_distinguishable_from_smoke_and_double_counting` | missing boundary | the hand `q_layer` omits the ISO cut; now asserts the layer term is at or above 2.5 kW/m2 |

### Open

The rows below come from a review pass; each smell is confirmed only when
its row is fixed.

| Test | Smell | Proposed contract |
|---|---|---|
| `verification/test_heat_fed_verif.py::test_a3_7_heat_fed_has_no_effect_on_gas_fed_total` | rotten green | Re-calls a pure gas function that takes no heat input, so it cannot fail; check separate `fed_cumulative` and `heat_fed_cumulative` in a coupled run |
| `verification/test_s6_heat_fed.py` threshold-time tests | tolerance | `t* - 0.5 <= observed <= t* + 1.5`, though the crossing lands on the first update at or after t*; use `t* <= observed <= t* + update interval` |
| `verification/test_heat_*_coupled.py` (`TIMING_TOL_S = 1.5`) | tolerance | Symmetric band around a one-sided crossing; verify per test and make it one-sided |
| `verification/test_s6_heat_fed.py::test_null_field_control_no_meaningful_accumulation` | tolerance camouflage | `< 0.01`; the 20 deg C clothed rate gives at most `rate(20) * 60 / 60 = 1.2e-4` |
| `verification/test_heat_fed_verif.py::test_a3_5_*` lognormal bands | tolerance camouflage | `abs=0.03` and `abs=0.05` at n = 20000 are 6 to 14 sampling σ; justify or tighten to about 4 σ |
| `test_heat_layer_flux.py::test_layer_flux_reproduces_the_200_c_anchor` | tolerance | `rel=0.15` also admits the incident flux (+13.7 %), so it cannot tell net from incident; label it a Handbook-anchor check (the formula is pinned at `rel=1e-9` elsewhere) |
| `test_heat_integrated_intensity.py::test_integrated_intensity_wins_over_the_layer_term` | circular, unlabelled | Both sides from production; label as consistency checks and anchor the rate with `q**1.33 / 16.7` |
| `test_heat_integrated_intensity.py::test_field_accepts_intensity_slice_at_the_temperature_height` | weak oracle | Only "no error"; assert both samplers are kept |
| `run_config` tests in `test_heat_layer_flux.py`, `test_heat_integrated_intensity.py` | weak oracle | `raises((ValueError, SystemExit))` without `match=` |
| `HEAT_SLICE_Z_TOLERANCE_M`, non-finite skin temperature, negative duration | missing boundary | No test at 1e-6 m, for NaN skin temperature or for `duration_s < 0` |
| `test_heat_endpoint_docs.py::test_models_heat_does_not_call_the_implemented_law_fatal` | stale claim | Docstring says Eq. 63.44 is the implemented law and total-flux is missing; both are no longer true |
| `verification/test_heat_endpoint_outputs.py` (`TEMPERATURE_C = 230`) | unsound physics claim | Above the 205 deg C limit without a wiring-only note |

## Smoke speed

Module `pyfds_evac/core/smoke_speed.py`: the Lund linear law with its 0.1
clamp, the Fridolf et al. (2019) law with V = C / K, the soot to K
conversion and `SmokeSpeedModel`. Where `scenario.py` applies the factor
is reached only through the coupled tests.

Audited files: `test_smoke_speed.py`, `test_smoke_speed_widget.py`,
`test_speed_update_pin.py`, `test_speed_update_skip.py`,
`test_iso_table21_coupled.py`, `test_model_speed_attrs.py`, and in
`verification/`: `test_smoke_speed_verif.py`, `test_s2_corridor_speed.py`,
`test_speed_update_coupling.py`, `test_fds_evac_guide_cases.py`. These are
also the tests the mutation check runs.

### Mutation checks

`python scripts/mutation_check.py smoke_speed`: 10 of 10 mutants killed,
all before the audit.

| Mutant | Kind |
|---|---|
| Soot density read as g/m3 instead of mg/m3 | unit conversion |
| Visibility K / C instead of C / K | unit conversion |
| Fridolf returns the speed instead of the factor | unit conversion |
| Fridolf reduction sign reversed | reversed comparison |
| Fridolf `w_free <= 0` guard to `< 0` | reversed comparison (killed by one test) |
| Lund `/ alpha` dropped | removed term |
| Lund lower clamp dropped | removed term |
| Fridolf 0.2 m/s floor dropped | removed term |
| Fridolf cap at `w_free` dropped | removed term |
| Model ignores the agent's free speed | removed term |

### Fixed

| Test | Smell | Change |
|---|---|---|
| `test_model_speed_attrs.py::test_the_model_obeys_the_write` | tolerance camouflage | `rel=0.15` passed a write honoured at 57 %; measured ratio is 0.5 to 2.4e-5, now `rel=1e-3` |
| `test_smoke_speed.py::test_lund_law_used_by_default` | weak oracle | K = 0 gives 1 under both laws; now K = 2, `1 - 0.057 * 2 / 0.706` |
| `test_smoke_speed.py::test_speed_factor_reduces_with_extinction` | weak oracle | ordering only; now the Lund values at K = 1 and 3 |
| `test_smoke_speed.py::test_larger_c_gives_higher_factor` | weak oracle | ordering only; now Eq. 7 values for C = 3 and C = 8 |
| `test_smoke_speed.py::test_smoke_updates_record_base_speed_during_premovement` | weak oracle | `desired < base`; now `desired = base * (1 - 0.057 / 0.706)` |
| `test_smoke_speed.py::test_run_scenario_accepts_three_argument_sample` | self-fulfilling mock | asserted only the factor the stub returns; now also that the agent's desired speed is halved |
| `test_speed_update_skip.py::test_precomputed_zones_match_the_scan` | circular | two paths of one function compared; now both against the expected zones |
| `test_iso_table21_coupled.py::test_it_is_constant_in_space_and_time` | false comment | "two decades above" the spread; it is about nine times |

### Open

The rows below come from a review pass; each smell is confirmed only when
its row is fixed.

| Test | Smell | Proposed contract |
|---|---|---|
| `test_iso_table21_coupled.py::test_the_time_ratio_matches`, `test_smoke_speed.py::test_iso_table21_constant_extinction_matches_expected_time_ratio` | tolerance camouflage | `rel=0.08` against effects of 4 to 9 %, so a half-strength coupling passes; derive the tolerance from the measured discretisation |
| `test_smoke_speed.py::test_iso_table21_holds_across_unimpeded_walking_speeds` | unsound claim | Says it catches a clamp on absolute speed, but at K = 1 no clamp binds; use K = 10 or drop the claim |
| `test_iso_table21_coupled.py::test_the_recorded_factor_matches_the_observed_coefficient`, the factor check in the ISO Table 21 sweep | circular, unlabelled | Production function on both sides; label as consistency checks and add the hand value at the observed K |
| `verification/test_speed_update_coupling.py` closed-form tests | circular | Expected speed uses the factor read from `smoke_history`, so a factor of 1 everywhere passes; pin the logged factors to the Lund values and assert one is below 1 |
| `verification/test_s2_corridor_speed.py::test_laws_diverge_at_same_extinction` | self-fulfilling | Compares two test-local helpers; compare `SmokeSpeedModel` under both laws |
| `test_smoke_speed.py` plot tests (sweep, guide plot) | weak oracle | Only file existence; label as plotting smoke tests |
| `test_smoke_speed.py` `TestFridolf` | missing boundary | No `w_free < 0` case and no test at the floor knee (K = 4.636 for `w_free` = 1) |
| `test_smoke_speed_widget.py::test_javascript_matches_python` | silent skip | Skips without node; CI has no `setup-node`, so it relies on the runner image |
| `test_smoke_speed.py` `FRIDOLF_TABLE`, `verification/test_fds_evac_guide_cases.py::test_guide_smoke_speed_table_values` | oracle source | Values come from Eq. 7 and the closed form, not from a cited table; say so |

## Routing: cost

Module `pyfds_evac/core/route_graph.py`, the measurement half of route
cost: the extinction mean along a line of sight or polyline
(`integrated_extinction_along_los`, `integrated_extinction_along_polyline`,
`_polyline_stats`, `_length_weighted_mean`), `_sample_segment_extinction`,
the foresight clock (`_arrival_time`, `_fds_end`, `_cap_at_fds_end`,
`_ForesightClock`), `evaluate_segment`, the first leg (`_first_leg*`,
`_leg_travel_time`, `_dose`, `_position_aware_length`), `_measure_route`,
the measuring side of `_fed_violations` and `RouteCostConfig` validation.
Policies, ranking and rerouting are other slices. Routing does not compute
Jin visibility: tau is the integral of K along the walked route.

Audited files: `test_route_smoke_integral.py`, `test_route_grid_sampling.py`,
`test_foresight_arrival_time.py`, `test_route_assessment.py`,
`test_walk_dose.py`, `test_fds_horizon.py`, `test_rerouting_hand_checks.py`,
and by node ID in `test_route_graph.py`: `TestSegmentCost`, `TestRouteCost`,
`TestPositionAwareRouting`, `TestIntegratedExtinctionAlongLos`,
`TestPolylineSampling`, `TestFedRateAdapter`, `TestWalkableRemainingDistance`;
in `test_routing_decisions.py`: `test_ramp_tau_matches_hand_value`. Added:
`test_route_cost_hand_values.py`. These are also the tests the mutation
check runs. The deck goldens of `test_rerouting_golden.py` are not in the
list (15 subprocesses per mutant); no mutant survived, so none needed a
separate run against it.

### Mutation checks

`python scripts/mutation_check.py routing_cost`: 23 of 23 mutants killed,
18 before the audit. None is killed by golden comparisons alone.

| Mutant | Kind | Killed before the audit |
|---|---|---|
| tau from `k_max` instead of `k_ave` | removed term | yes |
| tau from `k_leg_max` instead of `k_ave` | removed term | yes |
| tau without the effective length | removed term | yes |
| tau from `path_length` instead of the position-aware length | removed term | yes |
| Segment travel time ignores the smoke speed factor | removed term | yes, by two tests |
| First-leg travel time ignores the smoke speed factor | removed term | yes, by two tests |
| FED rate sampled at the decision time, not the arrival time | removed term | no: added `test_segment_dose_is_the_rate_at_the_arrival_time_over_the_walk` |
| Segment dose not divided by 60 | unit conversion | yes |
| `_dose` not divided by 60 | unit conversion | yes |
| Cap at the last FDS frame removed | removed term | yes, by two tests |
| Cap at the last FDS frame ignores the decision time (`max` to `min`) | reversed comparison | yes |
| `at_many` not capped at the last FDS frame | removed term | yes, by two tests |
| Length weighting dropped from the extinction mean | removed term | yes |
| Foresight horizon dropped from `_arrival_time` | removed term | no: added `test_arrival_time_is_walk_over_speed_capped_by_the_horizon` |
| `_arrival_time` ignores `anticipate` | reversed comparison | yes |
| `_arrival_time` adds metres as seconds | unit conversion | no: same test |
| Visible `<` to `<=` at the threshold | reversed comparison | no: added `test_a_segment_at_the_visibility_threshold_is_not_visible` |
| FED violation `>` to `>=` at the limit | reversed comparison | no: added `test_a_route_at_the_fed_threshold_is_not_in_violation` |
| Step sampling drops the far end | removed term | yes |
| Position-aware length ignores the agent's walk | removed term | yes |
| Excess walk time not pro rata | removed term | yes |
| Clock ignores the walked offset of a piece | removed term | yes, by one test |
| Horizon measured from zero, not the decision time | unit conversion | yes, by two tests |

### Fixed

| Test | Smell | Change |
|---|---|---|
| `test_route_graph.py::TestSegmentCost::test_heavy_smoke_segment` | weak oracle | `factor < 1`, `time > 10`; now the Lund factor at K = 5 and `10 / factor` |
| `test_route_graph.py::TestSegmentCost::test_fed_growth_computed` | tolerance camouflage | `abs < 0.01` against 0.0167; now `0.1 x 10 / 60` at `rel=1e-12` |
| `test_route_graph.py::TestSegmentCost::test_clear_air_segment` | tolerance camouflage | `abs < 0.1` on a length and time that are exact; now `rel=1e-12` |
| `test_route_graph.py::TestFedRateAdapter::test_evaluate_segment_with_fed_sampler` | circular | expected dose from the segment's own `travel_time_s` at `rel=0.01`; now `0.1 x (10 / 1.3) / 60` |
| `test_foresight_arrival_time.py::test_cache_is_not_shared_across_decision_times_under_a_horizon` | weak oracle | `shared == fresh > 0`; now tau = `0.8 x 5/6 x 10` |
| `test_foresight_arrival_time.py::test_cache_keys_on_the_foresight_limit_for_one_start_time` | weak oracle | `tau > 0`; now `0.8 x 4/6 x 10` |
| `test_route_grid_sampling.py::test_band_along_y_is_marched_by_rows` | tolerance camouflage | `abs=2.5` on 10.14 (measured 9.93); now `abs=0.25` |

New hand-value tests (`test_route_cost_hand_values.py`): K = 0.5 over 12 m
gives tau = 6.0 exactly; 10 m at K = 1 and 30 m at K = 0 weight to 0.25
(0.5 unweighted); 13 m at 1.3 m/s arrives at t + 10 s, capped by a
horizon; 0.6 /min for 100 s adds 1.0; the router speed at K = 2 equals
the `SmokeSpeedModel` factor `1 - 0.057 x 2 / 0.706`; the foresight clock
offsets and its cap at the last FDS frame; `_fds_end` takes the earliest.

### Model limits (not test gaps)

- Heat dose does not enter route choice: route FED is the gas rate.
- The gate has no smoke must-flee (#696, #751); a FED violation is the only
  must-flee kind under both models.
- Travel time uses the speed factor of the mean K of a leg, not the mean
  of the speed factors along it: a modelling choice, pinned by the hand
  value above.

### Open

The rows below come from a review pass; each smell is confirmed only when
its row is fixed.

| Test | Smell | Proposed contract |
|---|---|---|
| `test_route_grid_sampling.py::test_band_diagonal_leg_does_not_skip_the_plume` | tolerance camouflage | `abs <= 2.9` (25 %) around 11.55, the crossing length of the core; derive the cell count for the 30 degree leg and pin it |
| `test_route_grid_sampling.py::test_band_fixed_position_counts_the_cells` | tolerance | `abs(tau - 10) <= 0.25` documents the discretisation, but the 18 x 40 / 73 value above it already fixes the result |
| `test_route_smoke_integral.py` convergence tests (`rel=0.02`) | tolerance | Ordered errors are asserted; derive 0.02 from the step sizes |

## Routing: graph

Module `pyfds_evac/core/route_graph.py`, the search half of routing:
`StageNode.is_open`, `StageGraph.shortest_paths_to_exits`,
`shortest_path_to`, `_dijkstra`, `_reconstruct`, `without_closed_stages`,
`stage_closed` and `stage_closed_down`. Costs come from the cost slice;
ranking ties (`taus_tie`) belong to the ranking slice. Routing does not
compute Jin visibility.

Audited files, by node ID in `test_route_graph.py`: `TestGraphConstruction`,
`TestDijkstra`, `TestEdgeCases`, `TestDynamicDijkstra`,
`TestStaggeredScheduling` (it tests re-evaluation timing and kills no graph
mutant); in `test_scheduled_exits.py`:
`test_unscheduled_exits_are_always_open` and
`test_schedule_window_is_half_open`, the two tests there that use the graph
without running a scenario. Added: `test_route_graph_hand_values.py`. The
remaining tests of `test_scheduled_exits.py` and `test_flow_schedule_run.py`
run scenarios and are not in the list.

### Mutation checks

`python scripts/mutation_check.py routing_graph`: 12 of 12 mutants killed,
5 before the audit. None is killed by golden comparisons alone.

| Mutant | Kind | Killed before the audit |
|---|---|---|
| `is_open`: `time_s < open_from_s` to `<=` | reversed comparison | yes |
| `is_open`: `time_s < closed_after_s` to `<=` | reversed comparison | yes |
| `stage_closed_down`: `>=` to `>` | reversed comparison | no: added `test_closed_down_starts_at_closed_after` |
| `without_closed_stages` keeps edges into a closed stage | removed term | no: added `TestWithoutClosedStages` |
| `without_closed_stages` keeps the edges out of a closed stage | removed term | no: same class |
| `_dijkstra` relaxes edges into the source under `first_hops` | removed term | yes |
| `_dijkstra` seeds the source itself under `first_hops` | removed term | no: added `test_source_is_not_seeded_and_its_own_edges_are_replaced` |
| `_dijkstra` ignores `dynamic_weights` | removed term | yes, by a path-only test; exact costs added |
| `_dijkstra` relaxes on `alt <=` (tie moves the predecessor) | reversed comparison | no: added `test_tie_keeps_the_first_path_found` |
| `shortest_paths_to_exits` keeps exits at infinite cost | removed term | yes |
| `shortest_path_to` keeps a target at infinite cost | removed term | no: added `test_unreachable_target_gives_none` |
| `_reconstruct` does not stop at the source | removed term | no: added `TestReconstruct` |

Not mutated: the `if d > dist[u]: continue` skip of stale heap entries.
It is equivalent: a stale entry relaxes with a cost no lower than the
fresh one, so no distance or predecessor changes.

The `<=` mutant is written `alt <= dist[...] and edge.target != u`. Plain
`<=` never terminates: the zero-weight self-loop of
`TestEdgeCases::test_self_loop_ignored_in_shortest_path` relaxes forever.
The suite catches it as a hang, but a hang cannot be reported as a kill by
`mutation_check.py`, which has no timeout.

The stop at the source in `_reconstruct` only matters if the source has a
predecessor, which `_dijkstra` never produces for non-negative weights; the
test feeds `_reconstruct` a `prev` map directly and pins that contract.

### Fixed

| Test | Smell | Change |
|---|---|---|
| `test_route_graph.py::TestGraphConstruction::test_edge_weight_is_euclidean` | tolerance camouflage | `abs < 0.01` on 10.0; now `rel=1e-12` |
| `test_route_graph.py::TestDijkstra::test_linear_path` | tolerance camouflage | `abs < 0.01` on 20.0; now `rel=1e-12` |
| `test_route_graph.py::TestDijkstra::test_diamond_picks_shorter_path` | weak oracle | `cost < 31.0`; now 10 + 20 = 30 at `rel=1e-12` |
| `test_route_graph.py::TestDijkstra::test_multi_exit_picks_nearest` | tolerance camouflage | `abs < 0.01` on 10.0; now `rel=1e-12` |
| `test_route_graph.py::TestEdgeCases::test_duplicate_transitions` | tolerance camouflage | `abs < 0.01` on 10.0; now `rel=1e-12` |

New hand-value tests (`test_route_graph_hand_values.py`): the window
`open_from = 10`, `closed_after = 20` is closed at 9.999, open at 10 and
19.999, closed at 20; an exit that has not opened is `stage_closed` but not
`stage_closed_down`; a closure removes the stage, its out-edges and the
edges into it, and the search on what remains costs 5.0, not 2.0; a seeded
search from a point off the graph costs `first_hop + edge weights` and
ignores the source's own out-edges; an unreachable exit or target is
absent or `None`.

### Open

- `taus_tie` and the ranking of equal routes are not tested here (ranking
  slice).
- Between equal-cost paths the search keeps the one expanded first (node-id
  order in the heap). The tie test pins this; no documented contract
  promises it.

## Routing: policy

Module `pyfds_evac/core/route_graph.py`, the half of routing that decides
what a measured route means: `GatePolicy.feasibility` (the tau refusal),
`_fed_violations` (the FED refusal), `GatePolicy._tau_band` (the tau
deadband), `AdditivePolicy.edge_weight`, `_fallback_rival_wins` (the
all-refused fallback and its `hold` rule) and `taus_tie`. Optical depth is
the integral of the extinction along the route; routing does not compute a
Jin visibility distance, so these tests do not test Jin.

Audited files, by node ID: `test_fallback_hold.py`,
`test_fallback_tau_hold.py` and `test_gate_exit_pricing.py` (each kills
mutants, see below); `test_route_gate.py` (end-to-end gate refusal through
`rank_routes`; no mutant of this area depends on it). Added:
`test_route_policy_hand_values.py`, with binary-exact boundary values:
`tau_max = 2.0` with tau 2.0 feasible and one ulp above refused; FED
threshold 0.75 reached by `current_fed = 0.25` plus a growth of 0.5
(3.0 /min over a 10 s walk), and crossed with `current_fed = 0.3125`;
deadband margin 2.0 x 0.25 = 0.5 with a tau difference of exactly 0.5 (band
0 either way) and of 0.5625 (+1 for a cleaner candidate, -1 for a dirtier
one); fallback margin 0.25 with a rival at exactly 3.0 against 4.0 (holds)
and at 2.9375 (wins). No deck goldens are in the area.

### Mutation checks

`python scripts/mutation_check.py routing_policy`: 11 of 11 mutants killed,
4 before the audit. None is killed by golden comparisons alone.

| Mutant | Kind | Killed before the audit |
|---|---|---|
| `feasibility`: `tau_route > budget` to `>=` | reversed comparison | no: added `test_route_at_tau_max_is_feasible` |
| `_tau_band`: `delta > margin` to `>=` | reversed comparison | no: added `test_candidate_cleaner_by_exactly_the_margin_is_not_clearly_cleaner` |
| `_tau_band`: `delta < -margin` to `<=` | reversed comparison | no: added `test_candidate_dirtier_by_exactly_the_margin_is_not_clearly_dirtier` |
| `_tau_band`: margin 0 instead of `tau_max * tau_deadband` | removed term | yes, by `test_gate_exit_pricing.py` |
| `_tau_band`: the refusal `return -1` becomes `return 0` | changed constant | no: added `test_candidate_dirtier_by_more_than_the_margin_is_clearly_dirtier` (the missing refusal half was the oscillation bug) |
| `AdditivePolicy.edge_weight` drops the `w_fed * fed_growth` term | removed term | no: added `test_additive_edge_weight_is_length_times_smoke_plus_the_fed_toll` |
| `_fed_violations`: `fed_max > threshold` to `>=` | reversed comparison | no: added `test_fed_at_the_threshold_is_feasible_and_above_it_is_not` |
| `_measure_route`: `fed_max = current_fed + growth` to `growth` | removed term | no: added `test_fed_max_is_the_dose_already_taken_plus_the_growth` |
| `_fallback_rival_wins` ignores `fallback_rule == "hold"` | removed term | yes, by `test_fallback_hold.py` |
| `_fallback_rival_wins`: `<` to `<=` at the margin | reversed comparison | yes, by `test_fallback_tau_hold.py` |
| `taus_tie`: `<= EPS_TAU` to `<` | reversed comparison | yes, by `test_fallback_tau_hold.py` |

`edge_weight` omits `current_fed` on purpose (it is constant across one
agent's routes), so only a measured route with a non-zero `current_fed`
that pushes it over the threshold can kill the `fed_max` mutant; the
`evaluate_route` test does that. The gate's `edge_weight` has no FED term
(dose is a refusal there, not a cost); `test_gate_edge_weight_has_no_fed_term`
pins it, but no mutant targets it.

### Model limits, recorded and not tested as behaviour

- Heat dose takes no part in route choice: the router is given the gas
  dose and a gas-only rate sampler.
- The gate has no smoke must-flee: only a FED violation bypasses the exit
  anchor (#696, #751). `test_must_flee_*` in the hand-value file pin the FED
  case only.
- Travel time uses the speed factor of the mean extinction, f(mean K), not
  the mean of f(K). That is the model's choice; nothing here validates it.

### Open

- None of the mutants survives or is equivalent. The tie test for
  `taus_tie` pins `EPS_TAU = 1e-9` as the tolerance.
- `test_route_gate.py` kills none of the eleven; it stays as the
  end-to-end check of the refusal and is not tightened here.

## Property-based tests

Hypothesis is a dev dependency (maintainer's yes, #816). Tests use fixed
examples (`derandomize=True`), so CI runs are reproducible.

| Relation | Area | Status |
|---|---|---|
| FED rate is non-negative | FED | `test_fed_properties.py` |
| FED rate is non-decreasing in CO, CO2, HCN and each irritant | FED | `test_fed_properties.py`; NO and NO2 excluded, they lower the CN term |
| FED rate is non-increasing in O2 | FED | `test_fed_properties.py` |
| Rate is zero for clean air at or above the O2 threshold | FED | `test_fed_properties.py` |
| Accumulated FED is additive in duration under constant exposure | FED | `test_fed_properties.py` |
| Accumulating for `time_to_fed_threshold_s` gives FED 1 | FED | `test_fed_properties.py` (consistency check) |
| Agents are conserved (spawned = evacuated + remaining + incapacitated) | scenario | Open; each example is a simulation run, expensive |
