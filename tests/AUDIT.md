# Test-quality audit

Findings from walking `tests/` against the smells in
[testing guidelines §4](../docs/TESTING_GUIDELINES.md#4-reviewing-a-pull-request),
with the results of targeted mutation checks (issue #816). Each area is
audited in its own pull request; a finding stays here until it is fixed.

Mutation checks are run by hand with `scripts/mutation_check.py <area>`.
They show which tests catch a representative defect, not that the code is
right.

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

## Property-based tests

Hypothesis is not a dependency; adding it needs the maintainer's yes.
Candidate relations, none implemented:

| Relation | Area | Cost note |
|---|---|---|
| FED rate is non-decreasing in each toxicant concentration and in CO2 | FED | Cheap; pure functions |
| Accumulated FED is linear in duration under constant exposure | FED | Cheap |
| Rate is zero for O2 at or above the threshold and clean air | FED | Cheap; one parametrised test covers it without Hypothesis |
| Agents are conserved (spawned = evacuated + remaining + incapacitated) | scenario | Each example is a simulation run; expensive |
