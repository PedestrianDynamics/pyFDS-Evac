---
title: "Verification suite"
weight: 5
math: true
---

Symbols follow the [notation table](/docs/concepts.md#notation).

A two-layer verification suite checks each sub-model against a hand-computable
reference:

- **Tier A** pins each model *function* (FED, smoke-speed, cognitive map,
  pre-movement) to a closed form, to machine precision.
- **Behavioural** scenarios drive the coupling inside `run_scenario` with
  injected synthetic fields (no FDS run): a corridor for FED lethality (S1) and
  smoke-speed slowdown (S2), and a T-junction for dynamic rerouting (S4). Each
  uses a control / treatment / null-field design and asserts both exact wiring
  (from the per-agent history logs) and aggregate behaviour.

```bash
uv run pytest tests/verification -m "not slow"   # fast suite
uv run pytest tests/verification                  # incl. ensemble checks
```

See [tests/verification/README.md](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/verification/README.md) for the full
catalogue and [specs/012-model-verification/SPEC.md](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/specs/012-model-verification/SPEC.md)
for the design. The suite already surfaced two engine findings: trajectory-level
nondeterminism (only aggregate outcomes reproduce under a fixed seed) and a
rerouting bug under by-number placement
([issue #21](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/21)).

## Status against ISO 20414

ISO 20414:2020 (*Fire safety engineering — Verification and validation
protocol for building fire evacuation models*) defines 21 verification tests
(Tests 1–21) and 9 validation tests (Tests 22–30). The table below gives the
status of each verification test for pyFDS-Evac. FED means fractional
effective dose, and *K* [1/m] is the extinction coefficient. Everything on this page is
**verification**: it checks that the code reproduces the correlation or hand
calculation it implements. None of it is **validation** against observed
evacuations, and none of ISO 20414's validation tests (22–30) has been run.

### Tests 18 and 19: the fire–people interaction tests

These two tests cover the part of the model that pyFDS-Evac adds to JuPedSim,
so they were run first. Each is implemented twice: once with the hazard
supplied directly, as the standard allows, and once with the hazard read from
committed FDS output, so that the path from slice file to agent is checked as
well. Each condition is one run with a single occupant, so no spread over
seeds is reported.

**Test 18, reduced visibility vs walking speed.** The occupant walks the ISO
corridor (2 m × 100 m, 1 m exit) once in clear air, which is the control, and
once under a constant extinction coefficient *K*. The reference is the model's
own correlation, as the standard requires: the ratio of the two egress times
must equal 1/*f*(*K*), where *f* is the speed factor of the Frantzich–Nilsson
law (the `lund` option; the linear FDS+Evac law). The ratio must agree within 8 %, which absorbs the finite spawn box, the
exit width and the 0.1 s update interval, and every recorded speed factor must
equal *f*(*K*) exactly. With *K* supplied as a constant field
(`assets/ISO-table21`, `tests/test_smoke_speed.py`), the test runs at
*K* = 0.5, 1.0, 3.0, 7.5 and 10 1/m, and at unimpeded speeds of 1.0, 0.75, 0.5
and 0.25 m/s at *K* = 1.0 1/m. With *K* read from FDS
(`assets/iso_table21_coupled`, `tests/test_iso_table21_coupled.py`), the deck
prescribes the soot density for *K* = 1.0 1/m. The test requires the slice to
return that value within 1 % and to be non-zero. The second check is a null
control, because a missing slice reads as clear air. Only the default
Frantzich–Nilsson law is run in the ISO layout. The `fridolf` option (`speed_law="fridolf"`), which
is reachable only from Python, is checked by the S2 corridor scenario of the
suite above, not by this test.

**Test 19, occupant incapacitation by fire or smoke.** The occupant stands at
the centre of a 10 m × 10 m room. The time at which the simulated dose reaches
FED = 1 is compared with a hand calculation of the same dose
(`time_to_fed_threshold_s()`). With the gas supplied directly
(`assets/ISO-table22`, `tests/test_fed.py`), the test holds the occupant by
setting its speed to zero, one mixture is run, and the crossing must fall
within one time step of the hand calculation. With the gas
read from FDS (`assets/iso_table22_coupled`,
`tests/test_iso_table22_coupled.py`), the occupant is held by a
pre-evacuation time above 10⁷ s, the method the standard prescribes, and four
cases are run. They take their
concentrations from Fig. 8 of the FDS+Evac guide (Korhonen 2021) and separate
the CO, CO2 and O2 terms. The crossing must fall within two intervals of the
FED history. The test also checks that each species arrives at its prescribed
concentration and that the occupant does not move. The standard asks for the
test to be repeated for each hazardous condition the sub-model has. That is
done for CO, CO2 and O2 only. The convective heat dose is verified against its
closed form by the S6 scenario and the Tier A tests, but not in the Test 19
layout. The optional gases (HCN, NOx and the irritants) are not run in this
layout.

### All verification tests

"Not yet run" means that the component belongs to pyFDS-Evac, or is
configured through it, but no test reproduces the ISO setup. "Inherited" means
that the component is JuPedSim's movement model, which pyFDS-Evac does not
change; pyFDS-Evac has not rerun it. "Out of scope" means that pyFDS-Evac does
not model the component.

| Test | Title | Status | Reason |
|---|---|---|---|
| 18 | Reduced visibility vs walking speed | Run, passes | See above. Frantzich–Nilsson law only. |
| 19 | Occupant incapacitation by fire/smoke | Run for CO, CO2, O2 | See above. Heat and optional gases not run in this layout. |
| 1 | Pre-evacuation time assignment | Partly covered | The four distributions are checked against closed-form moments (`test_premovement_verif.py`); the ISO room and per-agent start times are not run. |
| 2 | Walking speed in a corridor | Inherited | Movement is JuPedSim's. |
| 3 | Walking speed on stairs | Out of scope | No stairs; the walkable area is one floor. |
| 4 | Movement around a corner | Inherited | Movement is JuPedSim's. |
| 5 | Assigned demographics | Not yet run | Speed distributions (`v0_distribution`) are set in pyFDS-Evac; their assignment has not been tested in the ISO setup. |
| 6 | Horizontal counter-flows | Inherited | Movement is JuPedSim's. |
| 7 | Overtaking people with movement disabilities | Inherited | Movement is JuPedSim's; slower agents are set with `v0`. |
| 8 | Exit route allocation | Not yet run | Exits and journeys are set in the scenario JSON, but rerouting is on by default (`--enable-rerouting`), so an allocated route may not be kept; no test reproduces the ISO layout. |
| 9 | Dynamic availability of exit | Not supported | An exit cannot be closed at a set time. Availability changes only when routing refuses a route for its smoke or dose. |
| 10 | Congestion in front of a flight of stairs | Out of scope | No stairs. |
| 11 | Maximum flow rates at an opening/exit | Not yet run | Optional throughput throttling on exits exists (`enable_throughput_throttling`, `max_throughput`); it has not been tested in the ISO setup. |
| 12 | Stair flow rates | Out of scope | No stairs. |
| 13 | Flow rate, density and walking speed in a corridor | Inherited | Movement is JuPedSim's. |
| 14 | Group behaviour | Out of scope | Groups are not modelled. |
| 15 | Social influence on exit choice | Out of scope | Herding is not modelled ([issue #78](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/78)). |
| 16 | Affiliation to familiar exits | Not yet run | Familiarity and the `entrance` key exist; whether they meet the test's criterion has not been checked. |
| 17 | Route choice based on geometric layout | Out of scope | The ISO layout has two floors. |
| 20 | Lift usage | Out of scope | Lifts are not modelled. |
| 21 | Escalator usage | Out of scope | Escalators are not modelled. |

### Movement is inherited from JuPedSim

pyFDS-Evac does not implement locomotion. Walking, collision avoidance,
counter-flow and flow through openings are computed by the JuPedSim model
named in the scenario (`model_type`, default `CollisionFreeSpeedModel`).
pyFDS-Evac sets each agent's desired speed and target, and it can cap the
flow through an exit, but locomotion itself is JuPedSim's. The movement tests are
therefore inherited, and pyFDS-Evac has not rerun them. JuPedSim reports its
own status against ISO 20414, RiMEA, NIST TN 1822 and IMO MSC.1/Circ.1533 on
its [V&V standards coverage dashboard](https://pedestriandynamics.org/jupedsim-web-community/),
including the tests it marks as expected failures. That status applies to the
models and versions it names, which may differ from the model and version a
pyFDS-Evac scenario uses.
