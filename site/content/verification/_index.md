---
title: "Verification"
linkTitle: "Verification"
weight: 4
aliases: [/models/verification/]
cascade:
  type: docs
  math: true
---

Each test checks one part of pyFDS-Evac against a value computed without
the code under test: a hand calculation, a published table, or FDS's own
output. Everything here is **verification** (does the code solve its
equations correctly?), not **validation** against observed evacuations.

A test works at one of three levels:

| Level | What runs | What it catches |
|---|---|---|
| **Equation** | one model function, no simulation | a wrong formula or constant |
| **Coupled** | a full pyFDS-Evac run on a synthetic field, no FDS | wrong wiring: the field is not sampled at the agent, or the result does not reach the agent |
| **FDS case** | a full run on a small FDS case (`assets/`) | wrong reading of FDS output: slice height, units, species names |

## The tests

Click a test for its page: what it checks, the equation, the setup, the
expected value, and the simulated result. Tests without a page yet link to
their test file.

| Component | Test | Level | What it checks | Status |
|---|---|---|---|---|
| Gas FED | [CO dose in a uniform room](/verification/testing-homogeneous.md) | FDS case | FED reaches 1 at the hand-calculated time; the fraction of agents incapacitated follows the log-normal threshold (opt-in probabilistic mode) | passes: dose and deterministic stop; the probabilistic stop pooled over 10 seeds (1000 agents) stays in the 95 % band (D = 0.023 against 0.043) |
| Gas FED | [FDS `FED_FIC` case](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_fed_fic_all_zones.py) | Equation | FED and FIC in the four zones of FDS's own verification case | passes |
| Gas FED | [S1 corridor](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_s1_corridor_fed.py) | Coupled | an agent in constant CO stops within one FED update of t\* | passes |
| Gas FED | [ISO 20414 Test 19: incapacitation by toxic gases](/verification/iso-test-19.md) | FDS case | four gas mixtures separating the CO, CO₂ and O₂ terms: each occupant stops at the next update after the hand-calculated time, as FDS's own FED device does | passes for CO, CO₂, O₂; HCN, NOₓ, irritants not yet ([#257](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/257)) |
| Heat FED | [Heat dose in a uniform room](/verification/testing-heat.md) | FDS case | heat FED at 100, 150 and 200 °C: every agent stops at the update where the hand sum on the FDS temperature reaches 1 | passes with `--heat-clothing unclothed`; checks the pipeline, not Eq. 63.44 itself; the default ISO Eq. (9) is an expected row only ([#307](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/307)) |
| Heat FED | [S6 heat](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_s6_heat_fed.py) | Coupled | heat incapacitation at t\*, cause recorded as `heat` | passes; checks the wiring of the default ISO Eq. (9), not the law itself |
| Heat FED | [SFPE tables](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_heat_fed_verif.py) | Equation | Eq. 63.44 against Table 63.20 (convective rows): within the assumed ±0.5 min rounding of each whole-minute entry, shorter at 100–140 °C; never longer than Table 63.17's reported dry-air times; the default ISO Eq. (9) recorded at 1.8–3.0 times Table 63.20 | passes ([#219](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/219)) |
| Heat FED | [Heat endpoints](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_heat_endpoint_coupled.py) | Coupled | `--heat-endpoint`: on the temperature history of SFPE Table 63.21 the tolerance dose reaches 1 in the fourth minute; at 150 °C the fatal dose crosses at the Eq. 63.47 time; endpoint, 205 °C and non-finite flag and unknown humidity reach the outputs; with `--heat-clothing unclothed` the FED history and manifest match a baseline from main (apart from `heat_clothing`); without an endpoint the run crosses at ISO Eq. (9) | passes |
| Heat FED | [Total flux](/models/heat.md#total-flux) ([test](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_heat_total_flux_coupled.py)) | Coupled | `--heat-fed-method total-flux` against the hand formula of Eqs. 63.49 and 63.43: dense smoke at 300 °C (tolerance, ε 0.9, h 8) crosses at 5.8 s; clear air at 100 °C (tolerance, ε 0.05, h 8) at 190 s on convection alone; smoke at 200 °C (fatal, ε 0.5, h 8) has a radiant term of 1.17 kW/m², below the 2.5 kW/m² threshold; outputs carry `heat_flux_kw_m2` and the method | passes ([#223](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/223)) |
| Heat FED | [Hot layer](/models/heat.md#hot-layer) ([test](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_heat_layer_flux_coupled.py)) | Coupled | `--heat-regime layer`: head at 120 °C below a 300 °C layer (φ 0.5, ε_L 0.9; layer term 2.52 kW/m², just above the threshold) crosses at the hand time; distinct from the smoke regime and from double counting; layer column in the outputs | passes; synthetic fields only; no FDS case runs the layer regime yet ([#308](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/308)); the #224 radiometer decks are FDS-only reference data |
| Heat FED | [INTEGRATED INTENSITY](/models/heat.md#radiant-flux-from-integrated-intensity) ([test](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_heat_integrated_intensity_coupled.py)) | Coupled + FDS case | radiant-only crossing at the hand time (q = 3.98 kW/m², fatal after 159.7 s) and its scaling with *f*; a committed FDS 6.10.1 case read at the head height against FDS's own devices; *f* = 1/4 against the FDS skin gauge in the #224 uniform room | passes; radiometer part skipped without the sciebo data ([#221](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/221)) |
| Heat FED | [Radiant threshold](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/test_heat_radiant_threshold.py) | Equation | ISO 2.5 kW/m² on the radiant term of each source (gas, layer, *U*): 2.4 counts as zero, 2.5 counts, a negative term counts as zero, NaN still voids the dose; convection unchanged; `heat_flux_kw_m2` stays physical; manifest records the threshold | passes |
| Heat FED | [Radiant and flame-pass references](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_heat_flame_pass_reference.py) | Equation | Eq. 63.45 against Table 63.21; Eq. 63.43 against Table 63.20's radiant rows; dose of an agent walking past a flame | reference only; they call no pyFDS-Evac code ([#223](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/223)) |
| Heat FED | [Heat radiometer reference decks](/verification/testing-heat-radiometer.md) | FDS case | FDS only, no pyFDS-Evac run: where a skin gauge's incident flux q sits between U/4 and U under a hot layer, in a uniform room and beside a burner | reference data; no run reads it; the uniform room is the expected value of the *f* = 1/4 check above |
| Smoke speed | [S2 corridor](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_s2_corridor_speed.py) | Coupled | applied speed factor equals the Frantzich–Nilsson and Fridolf laws | passes |
| Smoke speed | [ISO 20414 Test 18: walking speed in smoke](/verification/iso-test-18.md) | FDS case | egress time in the ISO corridor at K = 0.5–10 1/m and from FDS: equals the clear-air time scaled by 1/*f*(*K*) | passes |
| Irritants | [FIC vs FED speed](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/test_fic_vs_fed_speed.py) | Equation | on a short egress FIC slows agents at once while FED stays far below 1 | passes |
| Pre-movement | [Distributions](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_premovement_verif.py) | Equation | sampled moments of the gamma, log-normal, Weibull and uniform presets; the constant 10 s default is not checked | passes ([#309](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/309)) |
| Slice sampling | [Nearest FDS node](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/test_slice_node_index.py) | Equation | node- and cell-centred slices read at the right index | passes |
| Slice sampling | [Slice height](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_fed_slice_height.py) | FDS case | the gas FED reads the horizontal slice nearest 1.6 m in a room with CO in three layers | passes |
| Slice sampling | [Sign legibility slice height](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_vis_slice_height.py) | FDS case | fdsvismap reads the horizontal extinction slice nearest 1.6 m, never a vertical slice listed first, and the same slice as the smoke sampler | passes |
| Slice sampling | Gradient field | Coupled | the field is sampled at the agent's current position | missing ([#24](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/24)) |
| Sign legibility | [Unit tests](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/test_visibility.py) | Equation | reading distance, 30 m cap, viewing angle | passes |
| Sign legibility | S3 visibility gating | Coupled | a sign is acquired only when legible through smoke | missing ([#22](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/22)) |
| Cognitive map | [Familiarity: full map vs discovered map](/verification/testing-familiarity.md) | Coupled | what each agent knows, learns and walks, against sight lines computed from the plan | **fails (0.1 m)**: criteria 1–5 pass on 0.05 and 0.025 m; at 0.1 m 4 agents deadlock in a doorway and criterion 4 fails ([#359](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/359)); grid convergence over 30 seeds passes from 0.05 to 0.025 m on this sample (the 90 % interval of the P90 change reaches +10 %) and fails from 0.1 to 0.05 m because of #359 ([#168](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/168)) |
| Cognitive map | S5 staff vs visitor | Coupled | the cognitive map is used in the run loop | missing ([#23](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/23)) |
| Routing | [S4 T-junction](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_s4_tjunction_reroute.py) | Coupled | without anticipation, smoke on one branch moves at least 12 of 20 agents to the clear exit, none the other way; the four just inside the smoky arm turn back ([#458](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/458)). With anticipation, at least 17 of 20 take the clear exit at spawn and nobody reroutes ([#650](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/650)) | passes |
| Routing | [Golden rerouting decisions](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/test_rerouting_golden.py) | Equation | route costs and decisions unchanged (regression, not verification) | passes |

Every field is read from the horizontal slice nearest `--smoke-slice-height`
(1.6 m). The FDS-case checks of that rule, per quantity: gas, the slice-height
test above; sign legibility, the sign-legibility slice-height test;
temperature and *U*, the committed case of the INTEGRATED INTENSITY test;
extinction for walking speed, only the weak check of ISO Test 18, whose
slices differ by very little
([#259](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/259)).

Movement itself (walking, collision avoidance, flow through doors) is
JuPedSim's and is not retested here; see
[Status against ISO 20414](/verification/iso-20414.md).

## Running the tests

```bash
uv run pytest tests/verification -m "not slow"   # fast suite
uv run pytest tests/verification                  # incl. ensemble checks
```

Seven rows of the table link tests outside `tests/verification`, including
the CI tests behind ISO Tests 18 and 19. Run them with:

```bash
uv run pytest tests/test_heat_radiant_threshold.py tests/test_fic_vs_fed_speed.py \
    tests/test_slice_node_index.py tests/test_visibility.py \
    tests/test_rerouting_golden.py tests/test_smoke_speed.py \
    tests/test_iso_table21_coupled.py tests/test_iso_table22_coupled.py
```

`uv run pytest` runs everything. Tests that need the external data store
(for example the radiometer decks, `$HEAT_RADIOMETER_DATA`) carry the
`external_data` marker and are skipped when it is absent; CI deselects them
with `-m "not external_data"`.

The FDS cases need their FDS output, which is not in the repository; each
test page says where to get it or how to rerun FDS.
