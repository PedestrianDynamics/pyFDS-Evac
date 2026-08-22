# Homogeneous Heat FED Validation

## Purpose

This test case validates the heat FED (Fractional Effective Dose from
convective heat, ISO TS 13571 eq. 5) accumulation logic in the pyFDS-Evac
pipeline against hand-calculated predictions, using a simplified scenario
with a spatially **homogeneous** (uniform) gas-phase temperature field. It
is the direct sibling of [`docs/testing-homogeneous.md`](testing-homogeneous.md)
(the toxic-CO validation), following the same method and the same directory
conventions.

By removing spatial gradients as a variable, any deviation between simulated
and hand-calculated heat FED results can be attributed to the model/pipeline
logic itself, rather than to local temperature variation — isolating the
heat FED accumulation code from the heat-transport physics.

Three temperature levels are tested (100, 150, 200 °C) to check that the
pipeline's heat FED results scale correctly with the T^3.4 power law, rather
than validating against just a single data point.

**Scope note:** this validates the heat FED *dose* track (incapacitation)
only. Heat does not currently factor into route cost or rejection — that
routing question is deliberately deferred pending further design discussion,
so there is nothing routing-related to validate here.

## Test Setup

- **Geometry:** Sealed room (no vents/openings), so temperature cannot
  redistribute, with **adiabatic boundaries on all six faces**. The boundary
  condition is the one place the CO ladder's layout cannot be copied: FDS's
  default is an `INERT` wall at `TMP_FRONT = TMPA`, which would hold ~2160 m²
  of enclosure surface at ambient against the prescribed gas and drain the
  room. Species do not diffuse into inert walls; temperature does.
- **Source:** No combustion at all — unlike the CO ladder, this deck tracks
  no species and needs no `&REAC`/yield setup. A single `&INIT` prescribes a
  constant initial temperature across the whole domain. With no source term,
  no decay and no heat flux through any surface, the field stays at that
  temperature for the whole run, which is what makes the closed-form rate the
  right reference to compare against.

  Verify this before trusting a result: the `TEMP_center*` and `TEMP_corner*`
  devices should all read the prescribed value at `T_END`, not merely at
  t = 0. A falling trace means the boundaries are not holding and the
  comparison below is measuring the deck rather than the model.
- **Domain decomposition:** 4 MPI sub-meshes — confirms heat FED values are
  consistent across mesh boundaries (i.e. splitting the domain doesn't
  introduce discontinuities in the gas data JuPedSim consumes), same as the
  CO ladder.
- **Agents:** 100 JuPedSim agents, non-evacuating travelling in a rectangular
  circuit, exposed uniformly to the temperature field — isolates heat FED
  tracking from movement and exit-routing dynamics. Reuses the CO ladder's
  `config.json`/`geometry.wkt` verbatim (the scenario config is physics-track
  agnostic).

## What's Being Validated

1. **Heat FED accumulation** — per-agent FED_HEAT(t) computed from the FDS
   TEMPERATURE slice output matches the hand-calculated closed form for a
   known, constant gas temperature, across all three levels.
2. **Pipeline integration** — FDS TEMPERATURE slice output → `fdsreader` →
   JuPedSim correctly carries heat FED data across the 4-mesh decomposition
   with no per-mesh discrepancies.
3. **Slice-height correctness** — `FdsHeatField.from_fds()` goes through
   `load_slice_sampler()` (unlike the gas `FdsFedField`, a known pre-existing
   blind spot — see `pyfds_evac/core/fed.py`), so this is also, incidentally,
   the first asset to exercise the height-mismatch warning path for a newly
   added slice type.

## Method

1. Hand-calculate the expected FED_HEAT(t) curve for each of the three
   temperatures (100, 150, 200 °C) using ISO TS 13571 eq. 5 (see
   `scripts/fed_heat_hand_calc.py`).
2. Run the full FDS → fdsreader → JuPedSim pipeline on each of the three
   scenarios.
3. Compare simulated per-agent heat FED accumulation curves against the
   hand-calculated reference, for each temperature.
4. Confirm agreement within tolerance across all 100 agents and all 4
   sub-meshes, at all three temperature levels.

## Hand-Calculated Heat FED Reference

Computed with `scripts/fed_heat_hand_calc.py`, using ISO TS 13571 eq. 5 directly —
quoted from the user-supplied source, not derived, and **not** in
`materials/FDS+EVAC_Guide.pdf` (that document has no heat term at all).

### Formula used

**FED from convective heat** (ISO TS 13571 eq. 5), T in °C, Δt in minutes:

```
FED_HEAT = sum_{t1}^{t2} [ T^3.4 / 5e7 ] * dt
```

Under this test's constant-T exposure, the accumulator reduces to an exact
closed form, `FED_HEAT(t) = (T^3.4 / 5e7) * t_min` — `scripts/fed_heat_hand_calc.py`
still accumulates it per-timestep (rather than as a single multiplication) so
it can be driven directly off a real FDS dump's timestamps, structurally
matching the CO hand-calc script (`fed_hand_calc.py`).

| Temperature | FED = 0.3 (onset) | FED = 1.0 (incapacitation) |
|-------------|-------------------|-----------------------------|
| 100 °C      | 142.6 s           | 475.5 s                     |
| 150 °C      | 35.9 s            | 119.8 s                     |
| 200 °C      | 13.5 s            | 45.0 s                      |

(Accumulator and closed-form agree to all printed digits — expected, since
there is no HV-style multiplier or ramp to introduce discretisation error
the way the CO ladder's CO2 hyperventilation term does.)

## Directory Contents

Each case is a self-contained scenario directory, following the CO ladder's
layout exactly:

```
assets/
├── fed_incap_heat_100c/
│   ├── fed_incap_heat_100c.fds    — FDS deck, 100 C (CHID demo_homogeneous_heat_100C)
│   ├── config.json                — JuPedSim scenario (reused from fed_incap_co_2000ppm)
│   ├── geometry.wkt                — Walkable area (reused from fed_incap_co_2000ppm)
│   └── <untracked run output>     — .smv .out .sf/.sf.bnd (4 meshes), _devc.csv _cpu.csv _steps.csv
├── fed_incap_heat_150c/           — same layout, 150 C
└── fed_incap_heat_200c/           — same layout, 200 C
```

`config.json`/`geometry.wkt` are byte-identical copies of
`fed_incap_co_2000ppm`'s — the scenario config (agents, journey, routing
weights) has no dependency on which hazard track is under test.

pyFDS-Evac run artefacts (written wherever you point the `--output-*` flags):

```
<scenario>.sqlite                  — Agent trajectory database
<scenario>_fed_history.csv         — Per-agent FED + heat FED accumulation over time
```

## How to Run

```bash
# Requires an FDS install with a working MPI runtime (e.g. Intel MPI) on PATH.
mpiexec -n 4 fds assets/fed_incap_heat_100c/fed_incap_heat_100c.fds
mpiexec -n 4 fds assets/fed_incap_heat_150c/fed_incap_heat_150c.fds
mpiexec -n 4 fds assets/fed_incap_heat_200c/fed_incap_heat_200c.fds

.venv/bin/python run.py \
    --scenario assets/fed_incap_heat_100c \
    --fds-dir assets/fed_incap_heat_100c \
    --heat-fed-threshold 1.0 \
    --output-fed-history /tmp/heat_100c_fed_history.csv \
    --output-sqlite /tmp/heat_100c.sqlite
# repeat --fds-dir/--scenario for the 150c and 200c decks
```

No `--fed-threshold`/CO-related flags are needed — these decks track no gas
species, so the toxic FED path stays inactive (`fed_model=None`) and only
`heat_fed_model` is built.

## Results / Pass Criteria

**Status: not yet run.** FDS could not be executed to produce real output in
the environment this test case was built in — the installed FDS binary
requires the Intel MPI runtime (`impi.dll`), which is not present, and
installing it is a system-level change outside the scope of adding this
verification asset. The decks, hand-calc reference, and pipeline wiring are
all in place and unit/behavioural-tested (see `tests/verification/test_s6_heat_fed.py`
and `test_heat_fed_verif.py`, which validate the same formula and OR-incapacitation
logic against synthetic fields, no FDS required) — what remains is running
the three decks above in an environment with FDS+MPI available and filling
in this table:

| Case   | FED = 1.0 (Hand Calculation) | FED = 1.0 (Simulation) | % difference |
|--------|-------------------------------|-------------------------|--------------|
| 100 °C | 475.5 s                       | —                        | —            |
| 150 °C | 119.8 s                       | —                        | —            |
| 200 °C | 45.0 s                        | —                        | —            |

Target tolerance: <0.5%, matching the CO ladder's precedent in
[`docs/testing-homogeneous.md`](testing-homogeneous.md).

Remaining before this test case is complete:

- Run all three decks through FDS and fill in the table above.
- Confirm the `FdsHeatField.from_fds()` height-matching warning path fires
  correctly if a mismatched `--smoke-slice-height` is passed (it reuses the
  same flag as smoke/gas FED).
