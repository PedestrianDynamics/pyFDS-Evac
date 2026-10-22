---
title: "Status against NIST TN 1822"
linkTitle: "NIST TN 1822 status"
weight: 91
math: true
---

NIST Technical Note 1822 (Ronchi, Kuligowski, Reneke, Peacock and Nilsson,
2013, *The process of verification and validation of building fire evacuation
models*) suggests 17 verification tests (Verif.1.1 to Verif.5.2, Table 1 of
the report) and, separately, validation tests. The table below gives the
status of each verification test for pyFDS-Evac. The test list and the
descriptions are from the report itself. Everything on this page is
**verification**: it checks that the code reproduces the correlation or hand
calculation it implements. None of it is **validation** against observed
evacuations. The report's own prose numbers some tests differently from its
Table 1 (it calls the counter-flow test Verif.2.5 in one paragraph); this page
follows Table 1.

Six NIST tests overlap an [ISO 20414 test](/verification/iso-20414.md):
Verif.2.5 and ISO 18, Verif.2.6 and ISO 19, Verif.3.1 and ISO 8, Verif.3.3 and
ISO 16, Verif.4.1 and ISO 9, Verif.5.2 and ISO 11. Where the geometry and the
timing are the same, one test carries both markers. Where they differ, the
table says so, and for Verif.2.5 and Verif.4.1 a separate test runs NIST's own
setup.

To run the NIST TN 1822 cases on your machine (the rows marked run below), use
`uv run pytest -m "nist_tn1822 and not external_data"`; the same command runs
in the "NIST TN 1822" workflow on every push and pull request to `main`.

"Run" means that a maintained test reproduces the setup and checks the
expected result against a value computed by hand. "Inherited" means that the
component is JuPedSim's movement model, which pyFDS-Evac does not change and
has not rerun. "Out of scope" means that pyFDS-Evac does not model the
component. "Not yet run" means that the component belongs to pyFDS-Evac, or is
configured through it, but no test reproduces the NIST setup. Of the 17 tests,
6 are run, 4 are inherited, 5 are out of scope and 2 are not yet run.

## The three fire–people interaction tests

NIST suggests three tests of components that pyFDS-Evac adds to JuPedSim:
Verif.2.5, Verif.2.6 and Verif.4.1. JuPedSim alone cannot pass them: its own
suite runs Verif.2.5 and Verif.2.6 against adapters inside the test and cannot
run Verif.4.1, because it has no runtime exit closure.

**Verif.2.5** is NIST's corridor at K = 1.0 1/m and 1.25 m/s, which is the
ISO 18 corridor (`assets/ISO-table21`).
`test_nist_verif_2_5_reduced_visibility.py` walks it in clear air and under
both smoke-speed laws and compares the time over a 60 m stretch (x = −30 m to
+30 m, frame resolution 0.1 s) with the hand calculation. Clear air:
60 / 1.25 = 48.0 s. Frantzich–Nilsson: *f* = 1 − 0.057 / 0.706 = 0.919263,
*w* = 1.149079 m/s, 60 / *w* = 52.215 s. Fridolf with A = 2: visibility
2 / 1 = 2 m, *w* = 1.25 − 0.34 (3 − 2) = 0.91 m/s, 60 / *w* = 65.934 s.
Tolerance 0.15 s. The ISO 18 tests add the grid of speeds and extinction
coefficients that NIST suggests (the same values as ISO's), and
`test_iso_table21_coupled.py` reads K = 1.0 1/m from a committed FDS slice.
NIST does not say where the time is measured; the 60 m stretch is our choice.

**Verif.2.6** is NIST's room (10 m × 10 m × 3 m, no fire, one occupant at the
centre held by a pre-evacuation time above 10 000 000 s) and the ISO 19 setup
is the same, so the ISO 19 tests are the NIST tests; see
[ISO Test 19](/verification/iso-test-19.md).

**Verif.4.1** differs in layout. NIST's Figure 11 puts both 1 m exits on the
15 m walls near the far end and the occupant at the middle of the near 10 m
wall, about 14 m from either exit; the ISO test as run here puts the occupant
5 m from each door. `test_nist_verif_4_1_dynamic_exit.py` builds NIST's layout.
The report gives no dimension for the exit positions; the door centres at
y = 14 m and the occupant within 0.5 m of (5 m, 1 m) are our reading of the
figure. Each door centre is √(5² + 13²) = 13.93 m from (5, 1). At the closure
(1 s) the occupant has walked 1 m toward exit 1 and is 12.93 m from it and
13.2 m from exit 2. It leaves by exit 2 at about 1 + 1 + 13.2 = 15.2 s
(asserted between 12 s and 18 s) with one route change, exit 1 to exit 2, at
the first reroute check at or after the closure. Exit 1 usage is 0 of 1. The
control without the closure leaves by exit 1.

## All verification tests

| Test | Title | Status | Reason |
|---|---|---|---|
| Verif.1.1 | Pre-evacuation time distributions | Not yet run | The four distributions are checked against closed-form moments (ISO 1 row, `test_premovement_verif.py`); NIST's room (8 m × 5 m, ten occupants, repeated runs) is not run. |
| Verif.2.1 | Speed in a corridor | Inherited | Movement is JuPedSim's. |
| Verif.2.2 | Speed on stairs | Out of scope | No stairs; the walkable area is one floor. |
| Verif.2.3 | Movement around a corner | Inherited | Movement is JuPedSim's. |
| Verif.2.4 | Assigned occupant demographics | Not yet run | Speed distributions (`v0_distribution`) are set in pyFDS-Evac; their assignment has not been tested in NIST's setup. |
| Verif.2.5 | Reduced visibility vs walking speed | Run, passes | Both smoke-speed laws at K = 1.0 1/m and 1.25 m/s in NIST's corridor (`test_nist_verif_2_5_reduced_visibility.py`), plus the ISO 18 grid and the FDS-sourced K (`test_iso_test_18_speed_laws.py`, `test_iso_table21_coupled.py`). Details above. |
| Verif.2.6 | Occupant incapacitation | Run for CO, CO2, O2 | Same room and method as ISO 19 (`test_iso_table22_coupled.py`, and the stubbed-field test in `test_fed.py`). NIST asks to repeat the test for each hazard in the sub-model; heat, HCN, irritants and the optional gases are not run ([#257](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/257)). |
| Verif.2.7 | Elevator usage | Out of scope | Elevators are not modelled. |
| Verif.2.8 | Horizontal counter-flows (rooms) | Inherited | Movement is JuPedSim's. |
| Verif.2.9 | Group behaviours | Out of scope | Groups are not modelled. |
| Verif.2.10 | People with movement disabilities | Inherited | Movement is JuPedSim's; slower and larger agents are set with `v0` and `radius`. |
| Verif.3.1 | Exit route allocation | Run, passes (user-defined allocation) | The ISO 8 test: 23 occupants in twelve rooms off a corridor, rooms 1–4 and 7–10 allocated to the main exit and the rest to the secondary one, as NIST states (`test_iso_test_8_route_allocation.py`). The layout follows JuPedSim's implementation, not NIST's Figure 8, which was not checked. The allocation is user-defined (each room's journey names its exit); with the exit left to the model (the predictive reading) 4 of the 23 leave by another exit, so that reading is not passed. |
| Verif.3.2 | Social influence | Out of scope | Herding is not modelled ([#78](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/78)). |
| Verif.3.3 | Affiliation | Run, passes (ISO layout) | The ISO 16 test: the cognitive-map model with the entrance exit known sends the occupant to exit 2 in 100 % of runs, against 49.2 % without it (`test_iso_test_16_familiar_exit.py`). **Differs from NIST:** the room is the ISO 9 room, with exits about 5 m away and the occupant in the middle, not NIST's Figure 10 layout (exits near the far end, occupant 1 m from the near wall), which was not run. The model has no graded preference between known exits, so this shows knowledge of an exit, not a probability weight. |
| Verif.4.1 | Dynamic availability of exits | Run, passes | NIST's layout, details above (`test_nist_verif_4_1_dynamic_exit.py`). A schedule acts only through rerouting and needs routed agents. The ISO 9 layout is run in `test_iso_test_9_dynamic_exit.py` (not tagged for NIST). Fire-driven closure is not run ([#850](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/850)). |
| Verif.5.1 | Congestion | Out of scope | NIST's geometry is a room, a corridor and a stair; there are no stairs. |
| Verif.5.2 | Maximum flow rates | Run, passes | The ISO 11 test: 100 occupants in an 8 m × 5 m room with a 1 m exit on the 5 m wall, as NIST states (`test_iso_test_11_max_flow.py`). NIST allows two readings. With exit throttling on at 1.33 p/m/s it is verification, and the measured flow stays at or below the limit. With throttling off (the default) the flow is emergent, a validation reading: JuPedSim's `CollisionFreeSpeedModel` gives 3.78 p/m/s on the tested seed, reported and not asserted against 1.33 p/m/s. One layout. |

## Where the list comes from

The test list, geometries, scenarios and expected results are from the report
([NIST TN 1822](https://nvlpubs.nist.gov/nistpubs/technicalnotes/NIST.TN.1822.pdf)),
Section 3.1. JuPedSim's V&V suite maps the same 17 tests; its status,
including its expected failures, is on the
[V&V standards coverage dashboard](https://pedestriandynamics.org/jupedsim-web-community/)
and applies to the models and versions it names, which may differ from the
model and version a pyFDS-Evac scenario uses. The movement tests are inherited
from JuPedSim and are not rerun here.
