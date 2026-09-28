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
| Gas FED | [CO dose in a uniform room](/verification/testing-homogeneous.md) | FDS case | FED reaches 1 at the hand-calculated time; the fraction of agents incapacitated follows the log-normal threshold | passes |
| Gas FED | [FDS `FED_FIC` case](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_fed_fic_all_zones.py) | Equation | FED and FIC in the four zones of FDS's own verification case | passes |
| Gas FED | [S1 corridor](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_s1_corridor_fed.py) | Coupled | an agent in constant CO stops within one FED update of t\* | passes |
| Gas FED | [ISO 20414 Test 19](/verification/iso-20414.md#tests-18-and-19) | FDS case | CO, CO₂ and O₂ doses in the ISO room | passes |
| Heat FED | [Heat dose in a uniform room](/verification/testing-heat.md) | FDS case | heat FED at 100, 150 and 200 °C | passes; expected values come from the code's own formula ([#219](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/219)) |
| Heat FED | [S6 heat](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_s6_heat_fed.py) | Coupled | heat incapacitation at t\*, cause recorded as `heat` | passes; same caveat |
| Smoke speed | [S2 corridor](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_s2_corridor_speed.py) | Coupled | applied speed factor equals the Frantzich–Nilsson and Fridolf laws | passes |
| Smoke speed | [ISO 20414 Test 18](/verification/iso-20414.md#tests-18-and-19) | FDS case | egress-time ratio equals 1/*f*(*K*) | passes |
| Irritants | [FIC vs FED speed](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/test_fic_vs_fed_speed.py) | Equation | on a short egress FIC slows agents at once while FED stays far below 1 | passes |
| Pre-movement | [Distributions](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_premovement_verif.py) | Equation | sampled moments of the five presets | passes |
| Slice sampling | [Nearest FDS node](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/test_slice_node_index.py) | Equation | node- and cell-centred slices read at the right index | passes |
| Slice sampling | [Slice height](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_fed_slice_height.py) | FDS case | the gas FED reads the horizontal slice nearest 1.6 m in a room with CO in three layers | passes |
| Slice sampling | Gradient field | Coupled | the field is sampled at the agent's current position | missing ([#24](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/24)) |
| Sign legibility | [Unit tests](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/test_visibility.py) | Equation | reading distance, 30 m cap, viewing angle | passes |
| Sign legibility | S3 visibility gating | Coupled | a sign is acquired only when legible through smoke | missing ([#22](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/22)) |
| Cognitive map | [Familiarity routing](/verification/testing-familiarity.md) | FDS case | familiar agents against discovering agents on one plan | passes |
| Cognitive map | S5 staff vs visitor | Coupled | the cognitive map is used in the run loop | missing ([#23](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/23)) |
| Routing | [S4 T-junction](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/test_s4_tjunction_reroute.py) | Coupled | smoke on one branch makes every agent switch exit | passes |
| Routing | [Golden rerouting decisions](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/test_rerouting_golden.py) | Equation | route costs and decisions unchanged (regression, not verification) | passes |

Movement itself (walking, collision avoidance, flow through doors) is
JuPedSim's and is not retested here; see
[Status against ISO 20414](/verification/iso-20414.md).

## Running the tests

```bash
uv run pytest tests/verification -m "not slow"   # fast suite
uv run pytest tests/verification                  # incl. ensemble checks
```

The FDS cases need their FDS output, which is not in the repository; each
test page says where to get it or how to rerun FDS.
