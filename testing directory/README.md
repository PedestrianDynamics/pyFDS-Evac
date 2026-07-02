# Homogeneous CO FED Validation

## Purpose

This test case validates the FED (Fractional Effective Dose) accumulation and
probabilistic incapacitation logic in the pyFDS-Evac pipeline against
hand-calculated predictions, using a simplified scenario with a spatially
**homogeneous** (uniform) CO concentration field.

By removing spatial gradients as a variable, any deviation between simulated
and hand-calculated FED/incapacitation results can be attributed to the
model/pipeline logic itself, rather than to local concentration variation —
isolating the FED accumulation and incapacitation-probability code from the
gas-transport physics.

Three CO concentration levels are tested (2000, 4000, and 8000 ppm) to check
that the pipeline's FED/incapacitation results scale correctly with dose,
rather than validating against just a single data point.

## Test Setup

- **Geometry:** Sealed room (no vents/openings), so CO cannot escape and the
  concentration field stays spatially uniform once mixed.
- **Source:** Constant CO generation rate, homogeneous throughout the room.
  Three variants of this test are run, at 2000 ppm, 4000 ppm, and 8000 ppm
  CO, each producing a known, time-resolved CO concentration that can be
  predicted analytically.
- **Domain decomposition:** 4 MPI sub-meshes — confirms FED values are
  consistent across mesh boundaries (i.e. splitting the domain doesn't
  introduce discontinuities in the gas data JuPedSim consumes).
- **Agents:** 100 JuPedSim agents, stationary/non-evacuating, exposed
  uniformly to the CO field — isolates FED/incapacitation tracking from
  movement and exit-routing dynamics.

## What's Being Validated

1. **FED accumulation** — per-agent FED(t) computed from FDS CO output
   matches the hand-calculated FED curve for a known, constant CO
   concentration, across all three concentration levels.
2. **Probabilistic incapacitation** — agents are incapacitated according to
   the correct FED-derived probability model, not deterministically at a
   fixed FED threshold.
3. **Pipeline integration** — FDS gas slice output → fdsvismap → JuPedSim
   correctly carries FED data across the 4-mesh decomposition with no
   per-mesh discrepancies.

## Method

1. Hand-calculate the expected FED(t) curve for each of the three CO
   concentrations (2000, 4000, 8000 ppm) using the FDS-native Purser
   FED/CO incapacitation model (see `fed_hand_calc.py`).
2. Run the full FDS → fdsvismap → JuPedSim pipeline on each of the three
   scenarios.
3. Compare simulated per-agent FED accumulation curves and incapacitation
   timing/probability distribution against the hand-calculated reference,
   for each concentration.
4. Confirm agreement within tolerance across all 100 agents and all 4
   sub-meshes, at all three concentration levels.

## Hand-Calculated FED Reference

Computed with `fed_hand_calc.py`, using the exact FDS Purser equations
(NIST SP 1019, Section 22.10.18, eqs 22.42–22.49) — the same equations FDS
itself uses to produce its `FED` device output. Background CO2 = 500 ppm
(0.05%), O2 = 20.9% (ambient, no hypoxia contribution) held constant for
all three cases.

### Formulae used

**FED from CO** (eq. 22.43), C_CO in ppm, t in minutes:

```
FED_CO = 2.764e-5 x (C_CO)^1.036 x t
```

**FED from O2 hypoxia** (eq. 22.48), C_O2 in volume percent, t in minutes:

```
FED_O2 = t / exp[8.13 - 0.54 x (20.9 - C_O2)]
```

**Hyperventilation factor from CO2** (eq. 22.49), C_CO2 in percent:

```
HV_CO2 = exp(0.1903 x C_CO2 + 2.0004) / 7.1
```

**Total FED** (eq. 22.42) — FED_CN, FED_NOx, and FLD_irr are omitted here
since this scenario is CO-only:

```
FED_tot = FED_CO x HV_CO2 + FED_O2
```

`fed_hand_calc.py` accumulates this per-timestep (matching how FDS itself
does it internally) rather than as a single closed-form multiplication —
this matters because `HV_CO2` is not 1.0 even at 0% CO2 (it evaluates to
~1.04), so it can't be pulled out and applied once at the end.

| CO Concentration | FED = 0.3 (onset) | FED = 1.0 (incapacitation) |
|-------------------|-------------------|------------------------------|
| 2000 ppm          | 234.7 s           | 782.4 s                     |
| 4000 ppm          | 114.7 s           | 382.3 s                     |
| 8000 ppm          | 56.0 s            | 186.6 s                     |

These are the ground-truth values each `.fds` variant's simulated FED
output is compared against. Note: these do **not** match the shortcut
FED_CO = (C^1.036 × t_min) / 35000 approximation sometimes seen in `.fds`
comment blocks — that shortcut omits the HV_CO2 term and uses a slightly
different divisor, and is off by ~1.8% high vs. the values above. Treat
the table above, not any `.fds` file comment, as ground truth.

## Directory Contents

```
homogeneous_co_fed_validation/
├── FDS_results/
│   ├── demo_homogeneous_CO_2000ppm.fds       — FDS input, 2000 ppm variant
│   ├── demo_homogeneous_CO_4000ppm.fds       — FDS input, 4000 ppm variant
│   ├── demo_homogeneous_CO_v2_8000ppm.fds    — FDS input, 8000 ppm variant
│   ├── demo_homogeneous_CO.smv        — Smokeview scene file
│   ├── demo_homogeneous_CO.out        — FDS console output / run log
│   ├── demo_homogeneous_CO_devc.csv   — Device output (time-series measurements)
│   ├── demo_homogeneous_CO_hrr.csv    — Heat release rate over time
│   ├── demo_homogeneous_CO_cpu.csv    — MPI CPU timing info
│   ├── demo_homogeneous_CO_steps.csv  — Solver timestep log
│   ├── demo_homogeneous_CO_git.txt    — FDS version / git hash at time of run
│   ├── demo_homogeneous_CO.pickle     — Cached fdsreader data
│   ├── demo_homogeneous_CO.sf.gbnd    — Global slice boundary file
│   └── demo_homogeneous_CO_{1-4}_{1-17}.sf/.sf.bnd — Slice field data (4 meshes × 17 quantities)
│
├── geometry&pedestrians/
│   ├── geometry.wkt                   — Walkable area definition (Shapely WKT)
│   └── config.json                    — JuPedSim scenario (agents, journey, routing)
│
├── graphs/
│   ├── homogenous_co_incapacitation_onset_2000ppm.png   — Histogram of incapacitation onset times, 2000ppm
│   ├── homogenous_onset_cumulative_2000ppm.png          — Cumulative incapacitation curve over time, 2000ppm
│   ├── homogenous_co_incapacitation_onset_4000ppm.png   — Histogram of incapacitation onset times, 4000ppm
│   ├── homogenous_onset_cumulative_4000ppm.png          — Cumulative incapacitation curve over time, 4000ppm
│   ├── homogenous_co_incapacitation_onset_8000ppm.png   — Histogram of incapacitation onset times, 8000ppm
│   └── homogenous_onset_cumulative_8000ppm.png          — Cumulative incapacitation curve over time, 8000ppm
│
└── pyFDS-Evac_results/
    ├── Homogenous_Test_smol.sqlite                  — Agent trajectory database
    ├── Homogenous_Test_smol_fed_history.csv         — Per-agent FED accumulation over time
    ├── Homogenous_Test_smol_smoke_history.csv       — Per-agent smoke exposure over time
    ├── Homogenous_Test_smol_route_history.csv       — Agent route decisions over time
    └── Homogenous_Test_smol_route_cost_history.csv  — Route cost values over time
```

## How to Run

> TODO — fill in exact commands once finalized.

## Results / Pass Criteria

**Status: 8000 ppm case passing; 2000/4000 ppm pending.**

For the 8000 ppm case, all 100 agents now show `incapacitated = True` at
~186–187 s, matching the hand-calculated FED = 1.0 time of **186.6 s**
within about 1 s. This is the first run where the sampler bug (CO/CO2/O2
all reading 0, per earlier debugging) is no longer visibly affecting the
result.

![Incapacitation onset time distribution, 8000ppm](graphs/homogenous_co_incapacitation_onset_8000ppm.png)

![Cumulative incapacitation over time, 8000ppm](graphs/homogenous_onset_cumulative_8000ppm.png)

Note on terminology: the pipeline's "onset time" (plotted above) is the
timestamp at which `incapacitated` first flips `True` — this corresponds
to the hand-calc's **FED = 1.0** threshold (186.6 s), not the FED = 0.3
"onset" threshold used elsewhere in this doc's reference table (56.0 s for
8000 ppm). Same word, two different thresholds — worth not conflating the
two when comparing numbers.

Also worth a second look: both plots show all 100 agents incapacitating
in a single instant, with no spread. Given "What's Being Validated" above
calls for *probabilistic* incapacitation rather than a fixed deterministic
threshold, a single-bin spike is either expected here (e.g. if the
probability model's expected value collapses to one point for identical,
constant exposure across all agents) or a sign the probabilistic model
isn't actually introducing variance yet — worth confirming which before
calling this fully validated.

Remaining before this test case is complete:
- Re-run and confirm the 2000 ppm and 4000 ppm cases show the same
  agreement with their hand-calc references (782.4 s and 382.3 s FED=1.0
  respectively).
- Confirm per-mesh agreement across all 4 MPI sub-meshes (not just
  agent-level agreement).
- Decide and document a formal tolerance (±5%, absolute FED difference,
  etc.) rather than eyeballing agreement from the plots.
- Confirm whether the single-instant incapacitation spike is expected
  behavior for the probabilistic model in a homogeneous scenario.

## Notes

- Confirms the FED/CO gas slice requirements identified during earlier
  pipeline debugging are correctly satisfied by this scenario.
- Confirms agents are tracked for the full exposure duration rather than
  exiting prematurely (related to the earlier JuPedSim "everyone exits
  immediately" scenario JSON bug).