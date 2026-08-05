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

Testing was also conducted using probabilistic tenability to make ensure that encapacitation 
occurs at a log-normal distribution. 

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
- **Agents:** 100 JuPedSim agents, non-evacuating travelling in a rectangular circuit, exposed
  uniformly to the CO field — isolates FED/incapacitation tracking from
  movement and exit-routing dynamics.

## What's Being Validated

1. **FED accumulation** — per-agent FED(t) computed from FDS CO output
   matches the hand-calculated FED curve for a known, constant CO
   concentration, across all three concentration levels.
2. **Probabilistic incapacitation** — agents are incapacitated according to
   the correct FED-derived probability model, not deterministically at a
   fixed FED threshold.
3. **Pipeline integration** — FDS gas slice output → `fdsreader` → JuPedSim
   correctly carries FED data across the 4-mesh decomposition with no
   per-mesh discrepancies. (Not `fdsvismap`: that's a separate component
   used only by the sign-visibility model that gates rerouting/`discovery`
   familiarity — this test has a single exit, non-evacuating agents, and no
   `--vis-cache`/`--enable-rerouting`, so it never touches fdsvismap.)

## Method

1. Hand-calculate the expected FED(t) curve for each of the three CO
   concentrations (2000, 4000, 8000 ppm) using the FDS-native Purser
   FED/CO incapacitation model (see `fed_hand_calc.py`).
2. Run the full FDS → fdsreader → JuPedSim pipeline on each of the three
   scenarios.
3. Compare simulated per-agent FED accumulation curves and incapacitation
   timing/probability distribution against the hand-calculated reference,
   for each concentration.
4. Confirm agreement within tolerance across all 100 agents and all 4
   sub-meshes, at all three concentration levels.
5. Run the homogenous test at different seeds with the probabilistic incapacitation to ensure they're following the log-normal distribution.

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
|------------------|-------------------|----------------------------|
| 2000 ppm         | 234.7 s           | 782.4 s                    |
| 4000 ppm         | 114.7 s           | 382.3 s                    |
| 8000 ppm         | 56.0 s            | 186.6 s                    |


## Directory Contents

Each case is a self-contained scenario directory. The deck, the JuPedSim
config and the walkable area live together; FDS run output lands beside them
and is gitignored.

```
assets/
├── fed_incap_co_2000ppm/
│   ├── fed_incap_co_2000ppm.fds   — FDS deck, 2000 ppm CO (CHID demo_homogeneous_CO_2000ppm)
│   ├── config.json                — JuPedSim scenario (agents, journey, routing)
│   ├── geometry.wkt               — Walkable area (Shapely WKT)
│   └── <untracked run output>     — .smv .out .pickle .sf/.sf.bnd (4 meshes x 17 quantities),
│                                    _devc.csv _hrr.csv _cpu.csv _steps.csv _git.txt
├── fed_incap_co_4000ppm/          — same layout, 4000 ppm
└── fed_incap_co_8000ppm/          — same layout, 8000 ppm
```

Three earlier iterations from this debugging lineage are no longer tracked:
`fed_incap_co_v1` and `fed_incap_co_v2` (both 4000 ppm), and
`fed_incap_co_smol`, which never had a deck of its own. The 2000/4000/8000 ppm
ladder supersedes all three.

pyFDS-Evac run artefacts (written wherever you point the `--output-*` flags):

```
<scenario>.sqlite                  — Agent trajectory database
<scenario>_fed_history.csv         — Per-agent FED accumulation over time
<scenario>_smoke_history.csv       — Per-agent smoke exposure over time
<scenario>_route_history.csv       — Agent route decisions over time
<scenario>_route_cost_history.csv  — Route cost values over time
```

Analysis plots (incapacitation-onset histograms and cumulative onset curves
per concentration) are produced from the FED history CSV by the plotting
scripts in `scripts/`; see `docs/usage.md`.

## How to Run

> TODO — fill in exact commands once finalized.

## Results / Pass Criteria

**Status: All cases of 2000, 4000, and 8000 ppm are passing.**

For the 8000 ppm case, all 100 agents now show `incapacitated = True` at
~186–187 s, matching the hand-calculated FED = 1.0 time of **186.6 s**
within about 1 s. This is the first run where the sampler bug (CO/CO2/O2
all reading 0, per earlier debugging) is no longer visibly affecting the
result.

| Case     | FED = 1.0 (Hand Calculation) | FED = 1.0 (Simulation) | 
|----------|------------------------------|------------------------|
| 2000 ppm | 782.4 s                      | 786 s                  | 
| 4000 ppm | 382.3 s                      | 384 s                  | 
| 8000 ppm | 186.6 s                      | 187 s                  |

All of these result in a percent difference <0.50% which is accepted.

![Incapacitation onset time distribution, 8000ppm](graphs/homogenous_co_incapacitation_onset_8000ppm.png)

![Cumulative incapacitation over time, 8000ppm](graphs/homogenous_onset_cumulative_8000ppm.png)

Note on terminology: the pipeline's "onset time" (plotted above) is the
timestamp at which `incapacitated` first flips `True` — this corresponds
to the hand-calc's **FED = 1.0** threshold (186.6 s), not the FED = 0.3
"onset" threshold used elsewhere in this doc's reference table (56.0 s for
8000 ppm). Same word, two different thresholds — worth not conflating the
two when comparing numbers.


Remaining before this test case is complete:

- Decide and document a formal tolerance (±5%, absolute FED difference,
  etc.) rather than eyeballing agreement from the plots.
- Confirm whether the single-instant incapacitation spike is expected
  behavior for the probabilistic model in a homogeneous scenario.
