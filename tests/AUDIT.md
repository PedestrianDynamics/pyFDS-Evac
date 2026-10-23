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
- Neither model has a smoke must-flee (#696, #751, #835); a FED violation is
  the only must-flee kind.
- Travel time uses the speed factor of the mean K of a leg, not the mean
  of the speed factors along it: a modelling choice, pinned by the hand
  value above.

### Tolerance rows closed (#836)

Each tolerance is replaced by the hand count and `rel=1e-12` (`1e-9` for
the convergence values). The mutants below are ones the old tolerance
admitted: the old test passes them, the new one fails them.

| Test | Change | Mutant killed |
|---|---|---|
| `test_route_grid_sampling.py::test_band_diagonal_leg_does_not_skip_the_plume` | `abs <= 2.9` around 11.55; now 49 nodes x = 4.00..16.00, four in the core: `40 / 49 x 12 / cos 30 = 11.311` | `_cell_fractions` drops the start sample (48 samples, tau 12.0); the old test passes it |
| `test_route_grid_sampling.py::test_band_fixed_position_counts_the_cells` | the extra `abs(tau - 10) <= 0.25` removed: the `18 x 40 / 73` line above it, now `rel=1e-12`, fixes the value (10.0 is the continuous integral, 9.863 the cell count) | `_cell_fractions` drops the end sample; the retained line kills it, and the old tolerance on it was `abs=1e-6` |
| `test_route_grid_sampling.py::test_band_along_y_is_marched_by_rows` (second leg) | `abs=0.25`; now `40 / 49 x hypot(2, 12)` | none needed: the first leg of the same test already kills a dropped sample; this assertion was tightened for consistency |
| `test_route_smoke_integral.py::test_step_field_converges_to_the_line_integral` | `rel=0.02` around 1 / 2.1; now the sample count: one segment `10 x 101 / 2101`, two segments `(10 x 0.1 + 10 / 2001 x 2.0) / 2.1` | `_step_los_stats` takes one extra sample (`+ 1` to `+ 2`, relative change 5e-4); the old test passes it |

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
`TestEdgeCases::test_self_loop_ignored_in_shortest_path` relaxes forever,
and `mutation_check.py` has no timeout to report that as a kill. Closed
(#836): the `bounded_search` fixture (`tests/conftest.py`) counts the heap
pops of the search and fails the test past 10 000, and the area's search
tests use it (`test_route_graph_hand_values.py` as a module,
`TestDijkstra`, `TestEdgeCases` and `TestDynamicDijkstra`). Plain
`alt <=` (`if alt < dist[edge.target]` to `<=`) now fails in 0.2 s: the
old self-loop test hangs under it (killed by a 40 s timeout in the check),
the new `test_a_zero_weight_self_loop_is_never_relaxed` (hand value: two
pops, cost 2.0), `TestEdgeCases::test_self_loop_ignored_in_shortest_path`
and `TestEqualCostPaths::test_tie_keeps_the_first_path_found` fail. The
fixture needs no new dependency (`pytest-timeout` is not one).

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
  order in the heap). Closed (#836): the `_dijkstra` docstring states the
  rule and names the test that pins it; it is an implementation order, and
  no user-facing contract promises it.

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
- Neither model has a smoke must-flee: only a FED violation bypasses the exit
  anchor (#696, #751, #835). `test_must_flee_*` in the hand-value file pin the FED
  case only.
- Travel time uses the speed factor of the mean extinction, f(mean K), not
  the mean of f(K). That is the model's choice; nothing here validates it.

### Open

- None of the mutants survives or is equivalent. The tie test for
  `taus_tie` pins `EPS_TAU = 1e-9` as the tolerance.
- `test_route_gate.py` kills none of the eleven; it stays as the
  end-to-end check of the refusal and is not tightened here.

## Routing: reroute

Modules `pyfds_evac/core/route_graph.py` (`should_reevaluate`, the guards
of `evaluate_and_reroute`) and `pyfds_evac/core/scenario.py` (the
`_reevaluate`, `_arrive` and `_decide_at_flow_spawn` closures). This is the
half of routing that decides when an agent re-decides and what it is given
to decide with; the cost terms and the policy are audited in "Routing:
cost" and "Routing: policy".

Audited files, by node ID (each kills mutants, see below):
`test_routing_decisions.py::test_agent_path_snapshot`,
`::test_scan_takes_a_rejected_route_and_returns_unstamped`,
`::test_evaluate_and_reroute_snapshot`, `::test_reference_exit_reroute_snapshot`,
`::test_empty_ranking_stamps_before_exploring`;
`test_switch_reasons.py::test_idle_agent_routed_to_its_own_exit_is_resume`,
`::test_leaving_a_closed_exit_is_exit_closed`,
`::test_station_switches_to_exits_seen_at_spawn_are_learned_exit`;
`test_scheduled_exits.py::test_sequential_closures_leave_from_the_exit_walked_to`;
`test_look_before_wander.py::test_a_new_visit_to_a_node_allows_a_new_look`;
`test_no_known_exit.py::test_a_flow_agent_decides_as_it_spawns`. The
`test_routing_decisions.py` snapshots are regression-only
(`tests/golden/README.md`); the named behaviour tests above kill the same
mutants where a row says so.

Added: `test_route_reroute_hand_values.py` (the schedule, with binary-exact
times: interval 0.5 from a last evaluation at 1.0 re-evaluates at exactly
1.5 and not at 1.4375; an offset of 0.75 evaluates at exactly 0.75 and not
at 0.5; the first evaluation ignores the interval; an interval of 0 or
less never re-evaluates), `test_scheduled_exits.py::test_reroute_pass_evaluates_with_the_dose_taken`
(the pass is given the cumulative FED, a constant 3.0 /min dose) and
`test_no_known_exit.py::test_a_flow_agent_is_evaluated_from_where_it_spawned`
(the flow-spawn decision gets the spawned position). Both scenario tests
use the synthetic rooms already in those files; no FDS deck, no goldens.

### Mutation checks

`python scripts/mutation_check.py routing_reroute`: 14 of 14 mutants killed,
10 before the audit. `test_no_known_exit.py::TestRunModes::test_the_gui_refuses_the_form`
is deselected in the area (it needs the webapp extra, which the checking
environment lacks, and would otherwise fail, hence "kill", every mutant).

| Mutant | Kind | Killed before the audit |
|---|---|---|
| `should_reevaluate`: elapsed `>= interval` to `>` | reversed comparison | yes, but by one test only (`test_station_switches_to_exits_seen_at_spawn_are_learned_exit`); the hand values pin the boundary (now two) |
| `should_reevaluate`: `current_time >= eval_offset` to `>` | reversed comparison | no: added `test_offset_exactly_reached_evaluates_the_first_time` |
| `should_reevaluate`: `interval <= 0` to `< 0` | reversed comparison | no: added `test_zero_interval_never_reevaluates` (it terminates: interval 0 then re-evaluates every call) |
| `evaluate_and_reroute`: a refused best route no longer returns | removed term | yes, by `test_routing_decisions.py` (one snapshot, one golden-case test); #836 added `TestEvaluateAndReroute::test_a_refused_route_the_scan_lands_on_is_not_taken_or_stamped` |
| `evaluate_and_reroute`: the idle check of the same-exit branch dropped | removed term | yes, by `test_idle_agent_routed_to_its_own_exit_is_resume` |
| empty ranking no longer stamps `last_eval_time_s` | removed term | yes, by `test_empty_ranking_stamps_before_exploring` and 10 more, 3 of them snapshots; #836 added `TestEvaluateAndReroute::test_no_reachable_exit_stamps_and_decides_nothing` |
| chosen route no longer stamps `last_eval_time_s` | removed term | yes, by 12 tests (5 snapshots); #836 added `TestEvaluateAndReroute::test_a_chosen_exit_stamps_the_evaluation` |
| closed default route: `old_exit` not set to the exit walked to | removed term | yes, by `test_sequential_closures_leave_from_the_exit_walked_to` |
| closure switch not labelled `exit_closed` | removed term | yes, by `test_switch_reasons.py` and `test_scheduled_exits.py` |
| `_reevaluate`: `current_fed` 0 instead of the cumulative FED | removed term | no: added `test_reroute_pass_evaluates_with_the_dose_taken` |
| `_reevaluate`: exit count not moved | removed term | yes, by `test_station_switches_to_exits_seen_at_spawn_are_learned_exit` only (a Station run); #836 added `test_scheduled_exits.py::test_a_switch_moves_the_agents_count_between_the_exits` (synthetic room) |
| `_arrive`: `looked_node` of another node kept | removed term | yes, by `test_a_new_visit_to_a_node_allows_a_new_look` only |
| `_decide_at_flow_spawn`: decision skipped | removed term | yes, by `test_a_flow_agent_decides_as_it_spawns` |
| `_decide_at_flow_spawn`: position not refreshed | removed term | no: added `test_a_flow_agent_is_evaluated_from_where_it_spawned` |

### Open

- No mutant survives, hangs or is equivalent after the audit.
- Closed (#836): the exit-count mutant now has a second killer in a
  synthetic room, and `evaluate_and_reroute` has direct hand-valued tests
  (`TestEvaluateAndReroute`, `test_route_reroute_hand_values.py`) for the
  refused-best return and the two stamps, so those kills no longer come
  from snapshots alone. Each was checked with `mutation_check.py`'s
  mutants applied to the full area (`refused_best_not_returned`,
  `no_exit_last_eval_unset`, `last_eval_unset_after_choice`,
  `reevaluate_counts_not_moved`): the new tests fail under each.
- The `looked_node` mutant still rests on one test. The map entry only
  matters on a revisit after a visit that completed without a look, and
  `test_a_new_visit_to_a_node_allows_a_new_look` is the one scenario that
  builds it; a second test would repeat that scenario, so it is left as it is.
- `test_the_gui_refuses_the_form` fails in an environment without the
  webapp extra (`ModuleNotFoundError: pyfds_evac.webapp.app`); the full
  suite there is not clean for that reason alone.

## Routing: cognitive map

Modules `pyfds_evac/core/cognitive_map.py` (`familiarity_probability`,
`init_cognitive_map`, `expand_on_arrival`, `expand_from_visibility`,
`cognitive_subgraph`) and `pyfds_evac/core/scenario.py`
(`_assign_initial_exit`). The map decides which exits an agent may rank at
all; the cost terms, the policy and the schedule are audited in "Routing:
cost", "Routing: policy" and "Routing: reroute".

Audited files, by node ID (each kills mutants, see below):
`test_cognitive_map_memory.py::TestAcquisitionAndPersistence::test_side_exit_is_acquired_on_entering_the_window`,
`::test_an_agent_that_never_enters_the_window_never_learns_it`;
`test_scalar_familiarity.py::TestFamiliarityAsAProbability::test_one_point_zero_is_the_old_full_tier`,
`::test_a_population_lands_near_the_requested_share`,
`::TestEntranceSeeding::test_the_entrance_is_reachable_not_merely_listed`;
`test_blind_spawn_discovery.py::TestArrivalRespectsVisibility::test_a_neighbour_behind_a_wall_stays_unknown`,
`::TestTraversalTeachesTheWayBack::test_the_reverse_leg_is_learned_with_the_leg`;
`test_no_known_exit.py::test_arrival_teaches_the_leg_walked`;
`test_initial_exit_from_cognitive_map.py::test_knowledge_changes_the_opening_choice`;
`test_initial_exit_per_agent.py::test_agent_beside_a_door_takes_it`;
`verification/test_cognitive_map_verif.py::test_full_knows_all_nodes_and_edges`.
No deck golden is in the area.

Added: `test_cognitive_map_hand_values.py`, five nodes and six edges
(`S`, `A`, `B`, two exits; `A` and `B` joined both ways), a stub visibility
model with a fixed visible set that records every query, and exact
assertions on `known_nodes`, `known_edges` and `visited_nodes`: what a
visible, an invisible and a two-way neighbour teach; the walked leg in and
against the graph's direction; a full map is not even asked; familiarity
exactly 1.0 against `1 - 1e-12`, and the inclusive bounds of the accepted
range; the initial draw with a stub rng (strict `<`, one draw per exit in
`exit_nodes()` order, none at 0.0 or without an rng) and a seeded
`random.Random` for reproducibility; the entrance learned at familiarity
0; `_assign_initial_exit` called directly (with `_apply_initial_path`
recorded): a full map takes the near exit, a stranger takes the farther
entrance, the map is stored and an existing one is reused.

### Mutation checks

`python scripts/mutation_check.py routing_cognitive_map`: 18 of 18 mutants
killed, 15 before the audit (the area was first run with 19 mutants, one of
them equivalent, see below). `test_the_gui_refuses_the_form` is deselected
in the area (it needs the webapp extra).

| Mutant | Kind | Killed before the audit |
|---|---|---|
| `expand_on_arrival`: visibility check dropped (every neighbour learned) | removed term | yes, by 3 tests |
| `_expand_visible`: `if visible` to `if True` | removed term | yes, by 8 tests |
| `init_cognitive_map`: probability fixed at 1.0 | removed term | yes, by 44 tests |
| `init_cognitive_map`: `>= 1.0` to `> 1.0` | reversed comparison | yes, by 7 tests |
| `expand_on_arrival`: no early return for a full map | removed term | no: added the full-map tests (two independent: sets and `visited_nodes`; vis queries) |
| `expand_from_visibility`: no early return for a full map | removed term | no: added `test_a_full_map_does_not_even_ask` (the only observable is whether the model is queried) |
| `cognitive_subgraph`: no early return for a full map | removed term | yes, by 2 tests |
| range check `0.0 <=` to `0.0 <` | reversed comparison | yes, by 5 tests |
| range check `<= 1.0` to `< 1.0` | reversed comparison | yes, but by one test only; the bounds tests add more |
| draw only above `probability > 0.5` | reversed comparison | yes, by 2 tests |
| draw `rng.random() <` reversed | reversed comparison | yes, but by one test only; the stub-rng tests add more |
| entrance not learned | removed term | yes, by 5 tests |
| walked leg never learned in the graph's direction | removed term | yes, by 4 tests |
| reverse edge not learned | removed term | yes, by 4 tests |
| `_assign_initial_exit`: ranking ignores the map | removed term | yes, by 14 tests |
| `_assign_initial_exit`: familiarity forced to full | removed term | yes, by 16 tests |
| `_assign_initial_exit`: agent position dropped | removed term | yes, by 2 tests |
| `_assign_initial_exit`: map not stored for the reroute pass | removed term | no: added `test_the_map_is_kept_for_the_reroute_pass` |

Equivalent, dropped from the area: in `_assign_initial_exit`,
`ranked = [rc for rc in ranked if not rc.rejected] or ranked` to nothing.
Every ranking policy puts `rejected` first in `order_key`, so
`ranked[0]` is already a non-rejected route whenever one exists, and when
all are rejected the `or ranked` branch gives the same list. The filter is
a guard against a future ordering, not behaviour today.

### Open

- No mutant survives or hangs; one is equivalent (above).
- Closed (#836): `visibility_full_return_dropped` and
  `initial_exit_map_not_stored` each have a second killer.
  `test_a_full_map_does_not_even_ask` runs for `1.0` and `"full"` (two
  construction paths to a full map; the observable is still only whether the
  model is queried). `test_a_second_decision_reuses_the_map_the_first_stored`
  stores a map of S, B and X2 for a stranger told the entrance X2, then
  decides again at familiarity 1.0: the stored map gives X2, a rebuilt full
  map would give the nearest exit X1. Both mutants fail the new tests
  (`mutation_check.py routing_cognitive_map`, each applied to the full area).
- `visibility_always_true` and `expand_skips_visibility` are killed by
  stub and by clear-air visibility; no FDS-smoke visibility is in the area.

### Closing the routing audit (PR 2 to 5)

The model limits recorded as limits, not test gaps, are listed under
"Routing: cost" (heat dose not in route choice; neither model has a smoke
must-flee, #696, #751, #835; travel time uses f(mean K)) and repeated under
"Routing: policy". Nothing in this section adds to that list; the tests of this area pin the code's
behaviour, not the model's validity.

## Item 1: spawning and flows

Modules `pyfds_evac/core/scenario.py` (flow loop, outcome counts) and
`pyfds_evac/core/simulation_init.py` (flow spacing, both set-up paths).
Weak-test survey of issue #836; this part closes the flow cadence and the
run-outcome bookkeeping. The mutants were applied by hand to the file and
line named, run against the three files below, and reverted.

Files: `test_flow_schedule_run.py`, `test_run_outcome.py` and the new
`test_agent_conservation.py`. The rows closed for #876 were mutated the
same way (hand-applied, run against `test_flow_spawn_spacing.py`,
`test_flow_spawn_checks.py` and `test_agent_conservation.py`, reverted);
`test_flow_spawn_checks.py` is new.

### Fixed

| Finding | Test | Mutant killed by it |
|---|---|---|
| No run asserted when a flow agent enters; the spacing `duration / n` was pinned only by a unit test that is given the frequency | `test_flow_spawning_enters_one_agent_every_window_over_count[journeys, no-journeys]`: 6 agents over [0, 6] s enter at 0, 1, ... 5 s, each within one 0.1 s frame | `duration / (n + 1)` at `simulation_init.py:2056` (no journeys) and `:3288` (journeys), each killed by its own parameter |
| The same for a `flow_schedule` window | `test_a_flow_schedule_window_enters_one_agent_every_window_over_count[journeys, no-journeys]`: 6 agents in [2, 8] s enter at 2, 3, ... 7 s | `duration / (n + 1)` at `:1980` (no journeys) and `:3228` (journeys), each killed by its own parameter |
| `0 < agents_not_spawned < 10` | `test_a_window_past_the_time_limit_leaves_agents_unspawned` now asserts `(total, not_spawned) == (2, 8)` and `(evacuated, remaining) == (0, 2)`, derived in the docstring (entries at 2 s and 3 s, the 4 s limit ends the run first) | `not_spawned` off by one (`scenario.py:3849`) |
| `test_run_outcome.py` never asserted the identity or `agents_evacuated` | the completed, time-limit and flow-cut cases assert `total == evacuated + remaining` and `total + not_spawned == configured`, with the exact counts (6/0/0, 0/6/0, 0/1/5) | `agents_evacuated = total_agents` (`scenario.py:3881`, was killed only by an incapacitation test); `not_spawned` off by one |
| No conservation table | `test_agent_conservation.py`: seven fixed-seed runs (by number, flow with and without journeys, initial plus scheduled, time limit on each) with hand-derived counts | `total_agents` ignoring flow agents (`scenario.py:3844`); the two above |
| The cadence mutant "spawn all agents at window open" was killed only by the band | now also killed by the six cadence tests and the exact-count tests | `start = flow["start_time"]` (`scenario.py:983`) |
| `_defer_flow_spawn` count was asserted against the metric, which is the same count | `test_a_full_area_defers_the_flow_and_reports_it` asserts 101 deferrals and "101 steps" (t = 0.00 ... 1.00 s at 0.01 s); `test_deferrals_of_a_source_are_counted_with_their_first_and_last_time` | `count + 2` and `count` at `scenario.py:1017` |
| The "did not enter" figure was only seen as 5 of 5, where `numbers - counters` equals `numbers` | `test_the_report_counts_the_agents_that_did_not_enter`: 2 of 5 entered gives "3 of its 5", 0 of 4 gives "4 of its 4", source named by index without a `dist_key` | `numbers[source_id]` alone (survived the run tests) and `counters[source_id]` alone at `scenario.py:1040` |
| `_percentage_count` floor: only 10, 50 and 90 % of one area, through whole runs | `test_percentage_count_floors_the_share_of_the_capacity[10, 50, 90, 1]` and `test_percentage_count_places_at_least_one_agent` (100 m2 at 0.5 m: capacity 63; 6, 31, 56, 1; 1 m2: 0.5 raised to 1) | `round(...)` for `int(...)` and `max(0, ...)` for `max(1, ...)` at `simulation_init.py:1044` |
| `_check_flow_rate` equality had no test at the boundary | `test_a_flow_rate_equal_to_the_capacity_is_accepted` (4 agents over 2 s, capacity 2) and `test_a_flow_rate_above_the_capacity_is_refused` (2.5 agents/s) | `rate >= capacity` at `simulation_init.py:1103` |
| `_schedule_window` tolerance was never at the edge | `test_a_window_short_by_rounding_is_accepted` (3 agents at 0.1 s in [0, 0.3]: 3 * 0.1 = 0.30000000000000004), `test_a_window_short_by_more_than_the_tolerance_is_refused` (1e-7 s short), `test_a_window_of_exactly_one_step_per_agent_is_accepted` | dropping `+ 1e-9` and widening it to `1e-6` at `simulation_init.py:1090` |
| `test_positions_are_kept_only_before_a_due_spawn` allowed 5 to 11 snapshots | the band is now 5 to 6, derived in the docstring (one before the run, one per later spawn, one more for the float rounding of 3 * 0.4) | the half-step margin `dt / 2` widened to `dt` at `scenario.py:1007`, which takes 9 snapshots and passed the old band |
| The conservation table had no run with incapacitated agents | `test_incapacitated_agents_stay_in_agents_remaining[by-number, flow]` in `test_agent_conservation.py`: five agents collapse within a second under uniform lethal CO, 35 m or more from the exit; (evacuated, remaining, not_spawned, incapacitated) = (0, 5, 0, 5) | `remaining = simulation.agent_count() - len(incapacitated_agents)` at `scenario.py:3841` |

### Open

- `_schedule_window` with `>=` for `>` is an equivalent mutant: the
  `1e-9` tolerance already accepts a window of exactly `number * dt`, so
  no input separates the two.
- The first agent of a `flow_schedule` window is first seen in the frame
  after its start (2.1 s for a window opening at 2 s); the cadence tests
  allow one frame and do not pin which.

## Item 1: GUI/TUI (#836)

Survey of `webapp/`, `tui/` and `config/frontend.py` against hand-applied
mutants (survey ids F and T). The rows below are the run lifecycle of the
GUI (`webapp/runner.py`, the `/run` and `/clear` routes), then the parameter
mapping, export and wording rows below. Rows still open are listed at the end
of the section.

### Run lifecycle rows closed

All tests are in `test_webapp.py`; the stubbed `run_scenario` decides what the
worker logs and prints, so each expectation is a hand count.

| Finding | Smell | Test | Mutant killed |
|---|---|---|---|
| F14 `RunManager.start` does not clear the cancel flag | self-fulfilling mock (the stub never called `progress_callback`), missing case | `TestCancelLifecycle::test_a_run_after_a_cancel_ends_done`: cancel one run, start a second on the same manager with a stub that ticks once; it ends `done`, run id 2, last event 7.0 | `self._cancel.clear()` replaced by `pass`: the second run ends `cancelled` |
| F36 warning handler records nothing | untested behaviour | `TestRunCapture::test_model_warnings_reach_the_run_once_each_in_order` | `self._sink.append(message)` replaced by `pass` |
| F37 handler not installed on the logger | untested behaviour | same test, warnings logged on the child `pyfds_evac.core.stub` | `addHandler` replaced by `pass` |
| F38 logger level not lowered | untested behaviour | `test_warnings_survive_a_logger_configured_above_warning`; also pins that level and handlers are restored | `setLevel(logging.WARNING)` replaced by `pass` |
| F10 warnings not de-duplicated | missing case | first test: "slice height" logged twice appears once, order kept, an INFO record absent | dedupe test replaced by `True` |
| F11 warning cap off by one | missing boundary | `test_warnings_keep_the_newest_four`: seven warnings with the cap at 4 leave w3 to w6 | `[:-(cap + 1)]` |
| F12 console cap off by one | missing boundary | `test_console_keeps_the_newest_five_lines`: eight lines with the cap at 5 leave line3 to line7 | `[:-(cap - 1)]` |
| F13 console keeps CR progress chunks | missing case | `test_console_drops_carriage_return_chunks_and_unfinished_lines`: two `\r` chunks, one line, one unterminated write; only `done` is kept | the `\r` branch replaced by `False` |
| F1 `/run` reconnect to the active run dropped | name overstates coverage | `test_run_route_reconnects_to_the_active_run` (live panel pinned to the first run id, no error, no second run) and `test_run_route_reconnects_to_a_cancelling_run` ("Cancelling…") | guard replaced by `False` |
| F42 `/clear` guard | already covered | `test_clear_keeps_the_run_panel_while_a_worker_is_active` (existing; the survey did not run this mutant) | guard replaced by `False` |

The caps are lowered by `monkeypatch` (4 warnings, 5 console lines) to keep
the counts small; the values of `_MAX_WARNINGS` and `_MAX_LOG_LINES` are
configuration and not pinned here. A new run starting with empty warning and
console lists is also pinned (`test_a_new_run_starts_with_no_warnings`).

### Mapping, export and wording rows closed

Tests are in `test_progress_callback.py`, `test_webapp_launch.py`,
`test_webapp_remainder.py` and `test_tui_remainder.py`. Expected values are
hand derived (four agents give 0, 25, 50, 75 %; the Model tab sigma and the
port default come from `docs/usage.md`; smoke bins from the fixed edges).

| Finding | Smell | Test | Mutant killed |
|---|---|---|---|
| F33 `ProgressEvent.pct` always 0 | weak oracle (`0 <= pct <= 100`; the one-agent deck never shows a non-zero pct) | `test_progress_percentage_and_clocks_follow_the_documented_fields` on `single_exit_clear_air` (4 agents): `pct == int(100 * evacuated / 4)` for every event, at least 25 % reached | `pct=0` |
| F34 `wall_time` always 0 | weak oracle | same test: `wall_time` non-decreasing and positive at the end; `sim_time` starts at 0 and does not decrease | `wall_time=0.0` |
| `test_run_scenario_without_callback_is_unchanged` | rotten green by name | now compares evacuation time and agent counts with a run that has a callback | (no mutant; the old test asserted only a truthy `metrics`) |
| F30, F31 `--port` and `$PORT` | missing case | `test_gui_command_takes_the_port_from_the_option`, `test_gui_command_defaults_the_port_to_the_environment` | `type=int` removed; `$PORT` ignored |
| F41 `RunSpec.time_limit` | missing case | `test_run_snapshot_keeps_the_scenario_time_limit` | `time_limit=None` |
| F45 failed run wording | missing case | `test_failed_run_is_worded_failed` | `"failed"` worded `"error"` |
| F47 unknown incapacitated figure | missing case | `test_incapacitated_figure_is_not_shown_when_it_is_unknown` | `or count is None` dropped |
| F22 dirty checkout in the export header | missing case | `test_export_header_names_a_dirty_checkout` (and a clean header without it) | `if dirty:` replaced by `if False:` |
| F20 non-literal export value | missing case | `test_export_refuses_values_that_are_not_plain_literals` (list, tuple, dict) | type check replaced by `False` |
| F50 Model tab sigma | weak oracle (`test_defaults_match_the_cli` never reads the tab) | `test_model_tab_states_the_documented_default_sigma` | `0.94` changed to `0.95` |
| T1 TUI choice check | missing case | `test_value_outside_the_choices_is_rejected` over all seven options with choices | `_check_value` call removed |
| T5 unparsable TUI field | missing case | `test_unparsable_field_keeps_its_default_and_reports_the_error` | default replaced by `None` |
| T10 `status_word` | untested behaviour | `test_status_word_names_each_outcome` (four statuses) | incomplete worded `complete` |
| T11, T12 plan-view smoke bins | snapshot-only coverage | `test_smoke_bin_counts_the_edges_at_or_below_k` (K on the edges 0.5, 1, 3, 10 and between), `test_smoke_bins_are_clear_outside_the_walkable_area` on a 10 m room | `side="left"`; the clearing of outside cells removed |

### Open (GUI/TUI)

- The 0.1 edge of the smoke bins is not pinned on the edge itself: K is
  carried as float16, where 0.1 is 0.09998 and falls below the edge.
- F17 to F19, F46, T7, T13: equivalent, cosmetic or killed elsewhere.
- F29, F35 are killed by `test_run_events` and `test_config_model`.
- JS and CSS source-substring tests in `test_webapp.py` (no executed
  browser or Node test), the wall-clock bound in
  `test_a1_help_is_fast_and_imports_no_stack`, `test_a9_no_range_rejection`
  lock-in, and the GUI-versus-API run equivalence beyond one clear-air deck:
  not changed here.
- The one-agent deck `ISO-table21` emits no progress event with a non-zero
  `pct` (the last event precedes the final exit); a source question, not
  changed here.

## Item 1: movement and steering

Weak-test survey of movement and steering (#836, item 1). Each part is
fixed in its own pull request; the rows below are the per-model defaults.

### Per-model agent defaults

| Mutant | Source | Killed by |
|---|---|---|
| default `v0` 1.25 to 1.0, in each of six model branches | `simulation_init.create_agent_parameters` | `test_model_agent_defaults.py::test_v0_default[<model>]` |
| default `radius` 0.2 to 0.25 | same | `test_radius_default[<model>]` |
| GCFM `tau`, `a_v`, `a_min`, `b_min`, `b_max` default changed, with and without global parameters | same | `test_gcfm_defaults_without_global_parameters[None]`, `[global_params1]` |
| AVM `time_gap` 1.06 to 1.5; `anticipation_time` 1.0 to 2.0; `reaction_time` 0.3 to 0.4, both default branches | same | `test_avm_defaults_without_global_parameters` |
| Gaussian `v0` clip low 0.1 to 0.0, high 5.0 to 6.0 | `_sample_agent_values` | `test_gaussian_v0_is_clipped_to_the_documented_range` |

Sources of the expected values are stated in the test module: `v0` and
`radius` from `docs/scenario-json.md`, the clip from
`docs/coming-from-fds-evac.md`, the GCFM and AVM numbers from JuPedSim
1.4.2's defaults (not documented in the pyFDS-Evac pages).

`test_sfm_params.py` and `test_csm_v2_params.py` run-level tests now compare
the run without the keys with the run that sets the defaults, and pin the
agent count. This catches a missing key that stops spawning; it does not
catch a changed default value, which the unit tests above and in those files
pin.

### Fixed

The rows closed for #876 were mutated by hand (applied to the file named,
run against `test_movement_targets.py` and
`test_checkpoint_speed_factor_run.py`, reverted).

| Finding | Test | Mutant killed by it |
|---|---|---|
| The set-up copy `_normalize_speed_factor` had no test (the runtime copy is pinned in `test_speed_update_pin.py`) | `test_simulation_init_clips_the_speed_factor_to_zero_to_three`: the same 13-value table as the runtime copy, from `docs/scenario-json.md` ([0, 3]; negative or non-numeric gives 1.0) | `3.0` to `4.0`; `< 0.0` to `<= 0.0` and to `< -1.0`; `np.isfinite` dropped; `return 1.0` to `0.0` on a non-numeric value (`simulation_init.py:1296`) |
| The first-stage target clearance `max(0.05, 0.8 r, 0.25)` was not tested | `test_the_first_stage_target_keeps_the_documented_clearance[0.2, 0.5]`: 3000 draws in a 2 x 2 m stage keep 0.25 m (radius 0.2) and 0.4 m (radius 0.5) from the edge, and the closest draw is within 0.01 m of it (a clearance that is too deep fails) | `0.25` to `0.2`, to `0.3` and dropped; `0.8` to `0.5`; floor `0.05` to `0.3` (`simulation_init.py:1437`) |
| The later-stage clearance `max(0.05, 0.8 r)` and its default radius 0.2 were not tested | `test_a_later_stage_target_keeps_the_documented_clearance[0.2, 0.5, none, 0.01]`: 0.16 m, 0.4 m, 0.16 m (missing radius), 0.05 m (floor) | `0.8` to `0.5` and to `1.0`; default radius 0.2 to 0.3; floor `0.05` to `0.2`; a `0.25` floor added (`direct_steering_runtime.py:52`) |
| `test_next_stage_choice_has_its_own_stream` only checked independence of `base_seed`; the stream formula survived any constant | `test_the_next_stage_is_drawn_from_choice_seed_plus_step_stream`: five (seed, step) pairs over 20 equal-weight stages, picks pinned (recorded from the shipped stream, `random.random()` is stable) | `131` to `132`; `53` to `54`; `step_index` term dropped; `choice_seed` replaced by `base_seed` (`direct_steering_runtime.py:538`) |
| No run showed a checkpoint's `speed_factor` acting on the agent | `test_checkpoint_speed_factor_scales_the_speed_inside_only[0.5, 2.0, 5.0, -1.0]`: one agent, v0 1.0 m/s, checkpoint [15, 25] m; desired speed read after each step is 1.0 before and after and 0.5, 2.0, 3.0 (clipped), 1.0 (negative) inside | the checkpoint's `speed_factor` set to 1.0 in each of the two `direct_steering_info` entries (`simulation_init.py:1874` and `:2467`), each alone; `active_speed_factor` ignored in `update_checkpoint_speed`; the zone applied outside its polygon (`_find_checkpoint_zone`) |

The run case does not kill the runtime clip mutants (`3.0` to `9.0`,
`< 0.0` to `<= 0.0`, `normalize_speed_factor` dropped in
`_find_checkpoint_zone`): the set-up already clips the factor, and
`test_speed_update_pin.py` kills them.

### Open

- Closed by #868: GCFM `mass` defaults to JuPedSim's 1, and AVM reads the
  deck keys `anticipation_time` and `reaction_time` instead of `T` and
  `s0`; `test_model_agent_defaults.py` pins both.
- "The other survey rows of area A": the survey rows were not kept in the
  #836 issue or in PR #867 (the issue has no comments; #867 lists only the
  per-model defaults), so they cannot be listed here. Rebuild the survey
  of movement and steering before closing #876's movement item.

## Item 1: FDS sampling and visibility cache

Weak-test survey of the visibility cache (issue #836, item 1). Only the
cache keys and the cached sighting distance are closed here; the sampling
geometry and horizon findings of the same survey stay open.

### Mutation checks

Each defect was applied to `pyfds_evac/core/visibility.py`, the two files
below were run, and the source was restored. Before the new tests all eight
survived.

| Defect | Killed by |
|---|---|
| `_make_meta` drops `time_step_s` | `test_visibility.py::TestVismapCacheKey::test_changing_one_field_rebuilds[time_step_s]` |
| `_make_meta` drops `slice_height_m` | `...[slice_height_m]` |
| sign `alpha` in the key replaced by `None` | `...[alpha]` |
| sign `c` in the key replaced by 3 | `...[c]` |
| clear-air key drops the walkable hash | `TestClearAirCacheKey::test_changing_one_field_rebuilds[walkable]` |
| clear-air key drops `cell_size_m` | `...[cell_size_m]` |
| clear-air key drops `extinction_per_m` | `...[extinction_per_m]` |
| `_vis_metre_array` drops the obstruction mask | `test_fdsvismap_adapter.py::test_cached_sighting_distance_respects_an_obstruction` |

### Fixed

- The key tests write a cache with one config and build a model with a
  second config that differs in one field (time step, slice height, global
  cap, sign x, y, alpha, alpha to omni-directional, c, per-sign cap; for
  clear air the walkable shape, cell size, extinction). The cache must not
  answer. An identical second config must reuse it. Neither side reads
  `_make_meta`.
- The cached sighting distance is checked in a room with a wall. The
  expectation is by hand: c / K = 3 / 0.5 = 6 m in front of the wall, no
  sighting behind it although 4 m is inside 6 m.

### Open

- Sampling geometry and horizon findings (`line_parts` edge cases, line cache
  key, horizon equality): closed in "FDS sampling geometry and horizon"
  below.

## Item 1: FDS sampling geometry and horizon (#836)

Module `pyfds_evac/core/fds_sampling.py`; the survey's area C, the part
that is not the vismap and clear-air cache keys. The mutants were applied
by hand to the line named, run against the new file, and reverted
(bytecode disabled, so a same-size mutant cannot reuse a stale `.pyc`).

File: `test_fds_sampling_geometry.py`. Its slices are synthetic node grids
(x = 0..10, y = 0..4, 1 m apart) whose frame value is the frame index, so
every expectation is a count of nodes or frames.

### Fixed

| Finding | Smell | Test | Mutant killed |
|---|---|---|---|
| Every line in the old tests is horizontal or the diagonal | missing boundary | `test_a_segment_parallel_to_and_outside_an_edge_reads_nothing`: four segments one metre beyond an edge, parallel to it, each one outside part | `if q < 0.0: return None` removed (`_clip_to_extent`) |
| No segment touches a corner | missing boundary | `test_a_segment_touching_a_corner_counts_as_outside` (corner at t = 0 and t = 1) | `ta < tb` to `ta <= tb` |
| `_subtract` keeps empty pieces; only a zero-length part shows it | missing case | `test_a_subslice_inside_an_earlier_one_adds_no_part`: B inside A and ending with the line gives one part | `piece[0] < piece[1]` to `<=` |
| Overlap rule (#653) pinned by cells, not by the part bounds | missing case | `test_the_first_subslice_takes_the_overlap_band`: A x = 0..6, B x = 5..10 give parts 0..0.6 and 0.6..1 | none in the survey; pins the rule |
| `_same_cell` never decides a result | missing case | `test_ends_in_one_column_but_two_rows_give_two_samples` (two samples) and `test_ends_in_one_cell_give_one_sample` | `_cell_fractions` skips `_same_cell` |
| Line cache keyed on the start and `x1` only | missing case | `test_lines_sharing_start_and_x_end_are_kept_apart`: (2, 0)-(8, 0) then (2, 0)-(8, 2); rows 0 x 7 and 0, 0, 1, 1, 1, 2, 2 | key without `y1` |
| Vector nearest index: ties and a one-position axis unpinned | missing boundary | `test_a_start_between_two_nodes_reads_the_lower_one`, `test_nearest_indices_ties_go_to_the_lower_value_position`, `test_nearest_indices_of_a_single_position_axis_is_zero` | tie to the upper; single-position branch removed (the wrap-around -1 reads the same cell, so only the index shows it) |
| Sampler horizon `<=` was killed by an unrelated single-frame test | missing boundary | `test_the_horizon_itself_passes_and_the_next_float_raises`: 10 s frames (11 s) and the clipped final frame (10 + 1.5 = 11.5 s), `nextafter` raises | `time_s <= last + interval` to `<` |
| `read_cells` horizon unpinned (the upstream cap hides it) | missing case | `test_read_cells_checks_the_horizon_of_a_time_vector` (frames 0, 2, 4, 6, 10 at the horizon; one float later raises) and `test_read_cells_holds_the_last_frame_with_the_flag` (one warning) | `_frames` without the horizon check |
| Case horizon: one case, one slice | missing case | `test_the_slice_that_ends_first_sets_the_case_horizon` (either order) and `test_a_single_frame_slice_does_not_set_the_case_horizon` | `min` to `max` in `fds_output_horizon` |
| Height tolerance equality and tie order | missing boundary | `test_the_height_warning_stops_at_the_tolerance` (0.5 m silent, 0.51 m reported), `test_the_first_of_two_equally_near_slices_is_chosen` | `<=` to `<` at the tolerance; last equal slice wins |

### Open

- `_nearest_frames` without the `times > 0` rule: equivalent for frame
  times that are not negative. For a time at or before the first frame the
  wrapped "before" frame is the last one, never nearer; `idx == count`
  already takes the earlier frame. Not pinned.
- Survey rows outside this part: `SliceGrid.values` outside cells (killed
  in the wide set); the other four rows are closed in "Visibility cache
  edges (#876)" below.
- The sciebo-dependent tests (`test_t_junction_*`) skip without the data;
  the skip reason and the end-of-run list now name them (see "I/O and
  manifests").

## Item 1: Visibility cache edges (#876)

Module `pyfds_evac/core/visibility.py`. The mutants were applied by hand
to the line named, run against `test_visibility_cache_edges.py` and
`test_fdsvismap_adapter.py`, and reverted (bytecode disabled). The cache
arrays of the new file are built by hand: metres = 100 t + 10 w + x + 1.

### Fixed

| Finding | Test | Mutant killed by it |
|---|---|---|
| `_VisMapCache._nearest` tie unpinned (time, x and a one-position axis) | `test_nearest_coordinate_ties_go_to_the_lower_one[0.5, 1.5, hair above and below, on a node, below, above]`, `test_a_one_position_axis_is_always_index_zero`, `test_a_query_time_halfway_between_frames_reads_the_earlier_frame`, `test_an_x_halfway_between_cells_reads_the_lower_cell`. The tie rule is not documented; the literals follow the sampler's "ties to the lower" | `<` to `<=` in the comparison; `idx >= len` to `>`; `idx <= 0` to `< 0` (`visibility.py:483`) |
| `visibility_to_node` exception set: no test raised any of the three, none checked that others pass | `test_a_backend_without_an_answer_gives_none[RuntimeError, IndexError, KeyError]` (stub backend), `test_any_other_backend_error_is_raised`, `test_a_cache_without_distances_gives_none`, `test_a_sign_beyond_the_cache_waypoints_gives_none` (real `_VisMapCache`, index out of range) | each of the three dropped alone; `except Exception` (`visibility.py:1113`) |
| Masked zero | `test_a_masked_zero_distance_gives_none_and_a_positive_one_is_returned` | `metres > 0.0` to `>= 0.0` (`:1115`) |
| Observer off the grid: reading distance equality and the cell edge | `test_an_observer_exactly_at_the_reading_distance_sees_the_sign` (5 m, cap 5 m seen; one 1e-7 m further not), `test_an_observer_on_the_cell_edge_is_on_the_grid[-0.5, 2.5]`, `test_an_observer_a_hair_beyond_the_cell_edge_is_off_the_grid[-0.5000001, 2.5000001]` | `distance <= cap` to `<` (`:925`); `== 0.0` widened to `< 1e-3` and `< 1e-6` (`:906`); the x-bounds terms of `_distance_outside` shifted by 1e-3 (`:748`) |
| `_vis_metre_array` mask: each of the three factors | already pinned by `test_fdsvismap_adapter.py`; mutated per factor here | angle array replaced by 1 and visibility array replaced by 1 (`test_cached_metres_mirror_fdsvismaps_masked_product`); non-concealed array replaced by 1 (`test_cached_sighting_distance_respects_an_obstruction`) |

### Open

- The y bounds of `_distance_outside` are not mutated: the new grids have a
  single y row (zero extent), so only the x terms are pinned at the edge.

## Item 1: I/O and manifests (#836)

Survey of `manifest.py`, `run_outputs.py`, `wkt_to_fds.py`, the progress
events of `scenario.py` and the deck sweep against hand-applied mutants
(survey area D). The rows below are the ones closed with the manifest, the
generated deck and the writers. The rows closed for #876 are at the end of
the table; each mutant was applied by hand, run against the touched test
files and reverted. Still open: nothing from the survey list; the notes
under the table record what the new tests do not pin.

### Rows closed

| Finding | Smell | Test | Mutant killed |
|---|---|---|---|
| `sha256_of` and the manifest lock hash | circular (`== sha256_of(lock)`), weak oracle (`len == 64`) | `test_manifest.py::test_sha256_of_is_the_digest_of_the_content_not_of_the_path` and `test_build_manifest_fields` compare with the digest of `b"lock"` written out; two files of equal content, different names | hash of the path string instead of the content |
| `git_state` dirty flag | missing case (only outside a repository) | `test_git_state_dirty_counts_tracked_changes_only`: a repository made in `tmp_path`; clean, untracked file (clean), tracked edit (dirty) | `bool(status)` replaced by `not status` |
| Progress events | weak oracle (`0 <= pct <= 100`), single agent so `pct` is always 0 | `test_progress_callback.py::test_progress_events_report_the_evacuated_share_rounded_down`: three agents, `pct` 0, 33, 66 by hand; `sim_time` strictly increasing, `evacuated` non-decreasing | `pct` always 0; `pct` rounded up (34, 67) |
| Walls of the generated deck | one-sided oracle (a deck without walls passes) | `test_wkt_to_fds.py::test_walls_cover_every_cell_without_walkable_overlap` for three rooms, and `test_room_with_a_hole_gets_exactly_these_wall_boxes` with the five boxes derived by hand | greedy rectangle loses its top row |
| FED, exit and route-cost CSV columns | untested writers; `extrasaction="ignore"` hides a missing column | `test_run_outputs.py`: literal header and cell values per writer, with and without the heat group | `heat_endpoint` group dropped; `exit_in_map` dropped; `queue_time_s` dropped |
| Fill note | circular (placed equal to the bound in the only test) | `test_summary_line_names_the_placed_count_and_the_upper_bound`: placed 5 of at most 8 | upper bound printed as `placed` |
| `test_init_deck_sweep.py` | snapshot-only coverage, regenerated from the code under test | The module says it is a characterisation. `test_hand_derived_room_anchors_the_import`: a 10 x 10 m room, a 1.2 m door, 25 agents, area 100 m2 and exit strip 0.5 x 1.2 m from the coordinates. The area check no longer skips a row that has none | `EXIT_DEPTH_M` 0.5 changed to 0.4: the anchor fails even if the table is regenerated |
| Silent `external_data` omission | the three `t_junction` tests (`test_fds_horizon.py`, `test_fds_sampling_grid_index.py`, `test_example_downloads.py`) are deselected in CI and skip without the data | The skip reasons name the path and `T_JUNCTION_FDS`. `conftest.py` prints the deselected `external_data` ids at the end of every run, under xdist too. CI still does not need sciebo | not a mutant; the three tests passed locally with the data |
| Optional manifest fields | one-sided oracle (the fields were never absent and never present in a test) | `test_manifest.py::test_fds_coverage_is_recorded_as_given_and_only_when_given` (given, empty dict kept, absent when `None`); `test_run_settings_records_require_fds_coverage[False, True]` and `..._defaults_to_off`; `test_run_settings_visibility_kind_follows_the_model` (no parameters: smoky for an FDS field, clear-air otherwise; parameters recorded as a copy; no model gives `None`) | `if fds_coverage:` and `if False:`; `require_fds_coverage` fixed `False` and negated; smoky and clear-air swapped; `dict(parameters)` for `parameters` |
| `&MULT` forms | only I/J and N with `DXB` on z were tested | `test_fds_deck.py::test_mult_k_and_j_offsets_and_negative_lower_indices`, `..._i_lower_shifts_x_to_the_left`, `..._without_indices_is_one_copy_...`, `..._n_form_with_a_lower_bound_and_all_axes`, `..._n_form_needs_six_dxb_numbers[3, 7 numbers]`, `..._mixing_the_n_form_...`, `..._expands_the_documented_groups[HOLE, VENT, OBST]`, `..._expands_a_mesh_and_leaves_other_groups_alone`, `..._needs_xb_on_the_record`; defaults and index ranges from the FDS User Guide | `K` or `J` or `I` axis order changed; `dz` or `dy` dropped; `DY0` and `DZ0` swapped; `*_LOWER` ignored; `N_LOWER` ignored; `len(dxb) != 6` to `< 6`; each of the two refusals dropped; `HOLE`, `VENT` or `MESH` removed from `MULT_GROUPS` |
| `D` exponent | no test of `1.5D+2` | `test_exponent_numbers_read_as_fortran_reals[...]` (`1.5D+2`, `1.5d2`, `2D-1`, `-2.5d-1`, `.5D1`, `E` forms), `test_d_exponent_in_xb_and_mult_spacing`, `test_a_malformed_exponent_stays_text[1D, D2, 1.5D+, 1DD2, 1D2.5]` | `D` dropped from the number pattern; the `D` to `E` replacement broken |
| Walkable-area minimum part | the 0.25 m2 limit was never at the edge | `test_walkable_provider.py::test_a_free_part_of_exactly_the_limit_is_dropped` (0.25 dropped, 0.2501 and 0.3 kept) and `test_a_ring_of_exactly_the_limit_is_kept_and_a_smaller_one_filled` (0.25 kept, 0.2499 filled) | `MIN_PART_M2` 0.25 to 0.2 and to 0.3; `>` to `>=` (`walkable_provider.py:98`); `>=` to `>` and `+ 0.0003` in `fill_small_rings` (`fds_import_geometry.py:127`) |
| `resolve_dx` floor | the floor 0.1 m and its tolerance were never reached | `test_wkt_to_fds.py::test_auto_dx_is_the_thinnest_wall_between_the_default_and_the_floor[0.3, 0.25, 0.2, 0.1, 0.05]`, `test_a_wall_at_the_floor_does_not_warn` (5.1 - 5.0 is 0.0999999999999996), `test_a_wall_below_the_floor_warns_and_keeps_the_floor` (0.09 m, message text) | `_MIN_DX` 0.1 to 0.05 and to 0.15; `- 1e-9` dropped (spurious warning at 0.1) and widened to `- 0.02`; `max` to `min`; floor dropped |
| Vacuous `test_run_config` checks | no assertion (`vis_cache_without_fds_dir`), `is not None`, `any("smoke" in m)`, `isinstance` only | `test_constant_extinction_builds_smoke_model` pins the field, extinction 0.5, interval 2.5 and height 1.8; `test_rerouting_builds_reroute_config` uses interval 2.5; `test_vis_cache_without_fds_dir_is_allowed` pins `vis_model is None` and the two log lines; new `test_a_plain_deck_without_cache_or_flags_asks_for_no_visibility_model`; the log test compares the full message list | `or opts.vis_cache` condition dropped and forced `True`; `ConstantExtinctionField(1.0)`; interval and slice height replaced by constants; `reevaluation_interval_s=1.0` |

Notes on the rows above:

- The floor `_MIN_DX = 0.1` is recorded from the code; no page states it.
- The module docstring of `walkable_provider.py` says rings "smaller than
  that" are filled, the comment on `MIN_PART_M2` says "or less". The code
  keeps a ring of exactly 0.25 m2; the test pins the code and the
  docstring. The comment disagrees (source wording, not changed here).
- `1D2` reads as the integer 100 and `1E2` as the float 100.0 (`_atom`
  tests `"E" not in upper` after upper-casing, so a `D` exponent counts as
  no exponent). The values are equal; the type differs and is not pinned.
- The order in which `&MULT` copies are emitted (`K` outermost, `I`
  innermost) is not documented and is not pinned; the tests sort.

## Item 1: CLI

Weak-test survey of the CLI constants and flags (#836, item 1, area E).
Expected values come from `docs/usage.md`, the `init --help` text and the
`scripts/margin_audit.py` docstring, or from a hand count (stated in the
test).

| Mutant | Source | Killed by |
|---|---|---|
| `EXIT_NOT_RUNNABLE` 3 to 2 | `cli_init.py` | `test_init_flags.py::test_exit_status_numbers_of_a_plain_init` (subprocess, literals 0, 3, 1) |
| `_exit_spec` accepts six values | `cli_init.py` | `test_a_malformed_exit_is_an_argument_error` |
| `--no-fds` ignored | `cli_init.py` | `test_no_fds_leaves_the_fds_dir_out_of_the_run_command` |
| `--z-band` not passed to the importer (plain `init`) | `cli_init.py` | `test_z_band_makes_the_beam_block_walking` (walkable area 200 m2 instead of 20 m2) |
| `enable_rerouting`, `no_visibility`, `disable_tenability` `python_default` flipped | `config/parameters.py` | `test_config_model.py::test_python_defaults_of_the_switches_are_the_omitted_arguments` |
| `horizon_overrun` `<=` to `<` | `config/rules.py` | `test_max_time_may_reach_the_last_frame_plus_one_interval` |
| `ALPHA` 0.05 to 0.1 | `margin_audit.py` | `test_judge_p_between_five_and_ten_percent_is_not_distinct` (p = 4/64) |
| `EXACT_MAX_N` 20 to 19 | same | `test_exact_enumeration_holds_up_to_twenty_seeds` |
| `size >= floor` to `>` | same | `test_judge_effect_equal_to_the_floor_is_distinct` |
| `walk_mean` floor 1.0 to 0.5 | same | `test_floor_follows_the_plan_table[walk_mean-...]`, `test_judge_walk_mean_is_judged_against_its_floor` |
| `RETURN_WINDOW_S` 10 to 5 | same | `test_a_return_counts_in_the_window_up_to_ten_seconds` (9.9 s in, 10.1 s out) |
| permutation tolerance removed | same | `test_a_tie_in_floating_point_counts_as_a_tie` (p = 2/64 by hand; 0 without the tolerance) |
| `if args.print_summary` always false | `cli.py` | `test_cli_main_output.py::test_print_summary_prints_the_scenario_summary` (lines by hand count: 1 exit, 1 distribution, ~6 agents) |
| outside line printed for `rows == 0` (`if outside`) | `cli.py` | `test_no_samples_outside_the_domain_print_no_line[zero-rows]` |
| outside line `.1f` to `.2f`; wording changed | `cli.py` | `test_outside_the_fds_domain_line_follows_the_summary_line` (wording of `docs/fds-sampling.md`, 56.04 prints 56.0) |
| `base...head` to `base..head` | `check_golden_rerecord.py` | `test_check_golden_rerecord.py::test_the_diff_is_taken_from_the_merge_base` (base moves on, branch changes a README only) |
| diagnostic lines of `golden_rerouting.py` reworded or dropped (refusal to write, refusal on dirty paths, provenance change, `run`, `INCOMPLETE`, `MISSING`, `n of m runs`, `same`/`DIFF`, `identical`/`differences found`, `base`/`head` provenance line, refusal to compare with itself) | `golden_rerouting.py` | `test_golden_rerouting_script.py::test_run_names_*`, `test_run_lists_*`, `test_identical_runs_are_listed_file_by_file`, `test_a_differing_file_is_marked_*`, `test_comparing_a_run_with_itself_says_so` (script wording as literals) |

`test_init_flags.py` runs the command in a fresh process only for the exit
status numbers; the flag tests call `cli_init.main`.

### Open

- The `walk_mean` floor (the larger of 2 % of the base mean and 1 s) is
  pinned from the code: no page or docstring states it. It needs a
  documented source.
- The 10 s return window is documented as a number; whether a return at
  exactly 10.0 s counts is not, so it is not pinned.
- Closed: `--inspect-fds` without `--fds-dir` ended in a raw `ValueError`
  traceback; it now exits with the one-line `pyfds-evac: error:` message,
  pinned by `test_cli_main_output.py::test_inspect_fds_without_fds_dir_is_a_one_line_error`.

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
| Agents are conserved (spawned = evacuated + remaining + incapacitated) | scenario | Seven fixed runs in `test_agent_conservation.py`; no generated cases, each is a simulation run |
| Leg travel time is non-decreasing in extinction and in length; speed factor non-increasing in K | routing | `test_route_leg_properties.py`; precondition alpha > 0, beta <= 0, base speed > 0, 0 <= min factor <= 1; `inf` time allowed. A strict case guards the non-strict orderings |
| Exported `OPTIONS` read back equal the options written (keys, order, values, types, `-0.0`, hostile text) | export | `test_script_export_properties.py` (the comparison is to `export_options`, so only the rendering is under test) |

Open (PR 9 of the survey):

- Agent conservation as a generated property: the outcome counts are assembled
  inline in `run_scenario` (`scenario.py`, from `initial_agent_count` and the
  flow counters), not in a function that can be called alone. A Hypothesis
  test needs that extraction (a source change) or a run per example; the fixed
  table in `test_agent_conservation.py` stays the check.
- Full route composite non-decreasing in K and length: needs a graph fixture
  with the additive model, one edge per route and no rival; the default
  `gate` model ranks by time and the queue and FED terms are not monotone in
  K alone. Not cheap enough for this pull request.
- Threshold boundaries: the survey assigns no rows to this pull request and
  asks for parametrised tests, not Hypothesis; none added.
