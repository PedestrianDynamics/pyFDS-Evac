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
