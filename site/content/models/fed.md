---
title: "Fractional effective dose"
weight: 2
math: true
---

Based on: [Asphyxiant fractional effective dose](/fundamentals/asphyxiant-fed.md), [Irritant gases](/fundamentals/irritants.md), [Heat](/fundamentals/heat.md) and [Incapacitation thresholds](/fundamentals/incapacitation-thresholds.md).

Symbols follow the [notation table](/docs/concepts.md#notation). The model
codes the Purser sum in the form of the [FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source) guide (Korhonen 2021, §3.4),
which adds irritants into the dose; ISO 13571 keeps them in a separate
concentration endpoint. The published equations are on the Fundamentals pages
linked above.

Background: the [Concepts](/docs/concepts.md) page
and the talk [*A Modular Workflow for Visibility-Aware Evacuation Modelling*](https://pedestriandynamics.org/pyFDS-Evac/talks/visibility-seminar-2026/).

## Coded form

`FedComponents.total_rate_per_min` (`pyfds_evac/core/fed.py`) returns the
gas FED rate [1/min]

$$
\dot{\mathrm{FED}} = \bigl(\dot{\mathrm{FED}}_{\mathrm{CO}} + \dot{\mathrm{FED}}_{\mathrm{CN}} + \dot{\mathrm{FED}}_{\mathrm{NO_x}} + \dot{\mathrm{FLD}}_{\mathrm{irr}}\bigr) \times \mathrm{HV}_{\mathrm{CO_2}} + \dot{\mathrm{FED}}_{\mathrm{O_2}},
$$

and `DefaultFedModel` integrates it over time, with *t* in minutes. Each term
is one function in `fed.py`:

| Term | Function | Coded rate [1/min] | Input |
|------|----------|--------------------|-------|
| CO | `_co_fed_rate_per_minute` | \(2.764 \times 10^{-5}\, C_{\mathrm{CO}}^{1.036}\) | CO (ppm) |
| CN | `_cn_fed_rate_per_minute` | \(\max\bigl(0,\ \exp(C_{\mathrm{CN}}/43)/220 - 1/220\bigr)\), \(C_{\mathrm{CN}} = \max\bigl(0,\ C_{\mathrm{HCN}} - (C_{\mathrm{NO}} + C_{\mathrm{NO_2}})\bigr)\) | HCN, NO, NO2 (ppm) |
| NOₓ | `_nox_fed_rate_per_minute` | \((C_{\mathrm{NO}} + C_{\mathrm{NO_2}})/1500\) | NO, NO2 (ppm) |
| Irritants | `_irritant_fld_rate_per_minute` | \(\sum_i C_i / F_{\mathrm{FLD},i}\) | seven irritants (ppm) |
| HV_CO2 | `_hyperventilation_factor` | \(\exp(0.1903\, C_{\mathrm{CO_2}} + 2.0004)/7.1\) for \(C_{\mathrm{CO_2}} > 0\) (at least 1.041), and 1 without CO2, as in FDS; a run warns once if CO is sampled with zero CO2, which points to a deck with no ambient CO2 (a factor, not a rate) | CO2 (vol %) |
| O2 | `_o2_hypoxia_rate_per_minute` | \(1/\exp\bigl(8.13 - 0.54\,(20.9 - C_{\mathrm{O_2}})\bigr)\); 0 at or above `o2_threshold_percent`, 20.0 % by default | O2 (vol %) |

The lethal Ct doses \(F_{\mathrm{FLD},i}\) [ppm·min] are constants in
`_irritant_fld_rate_per_minute`, taken from Table 2 of the FDS+Evac guide:

| Species | HCl | HBr | HF | SO2 | NO2 | acrolein | formaldehyde |
|---------|------|------|------|------|------|----------|--------------|
| F_FLD | 114000 | 114000 | 87000 | 12000 | 1900 | 4500 | 22500 |

Gas species are read from FDS slice outputs via `fdsreader`. CO, CO2 and O2
are required. The optional species (HCN, NO, NO2, HCl, HBr, HF, SO2, acrolein,
formaldehyde), the guide's optional terms, are loaded when available; a
missing species reads 0 and contributes nothing. With only the three required
species the sum reduces to the FDS+Evac default,
\(\dot{\mathrm{FED}}_{\mathrm{CO}}\,\mathrm{HV}_{\mathrm{CO_2}} + \dot{\mathrm{FED}}_{\mathrm{O_2}}\).

## Convective heat

FDS+Evac has no heat dose, so this one is opt-in: with `--enable-heat-fed`
(`opts.enable_heat_fed`) and a `TEMPERATURE` slice in the case, a separate
heat dose accumulates at
`_heat_fed_rate_per_minute` (`fed.py`),

$$
\dot{\mathrm{FED}}_{\mathrm{heat}} = T^{3.4} / (5 \times 10^{7}) \quad [1/\mathrm{min}],
$$

with *T* in °C. It is a running total of its own, never added to the gas FED.
The basis is on [Heat](/fundamentals/heat.md); the full specification,
including its limits, is on [Models › Heat](/models/heat.md).

## Tenability: irritant slowdown and incapacitation

`TenabilityConfig` (`fed.py`) adds two rules. The slowdown and the gas
stop need the gas FED model; the heat stop needs only the heat FED model
(`run_config.py`, `_build_tenability_config`).

- **Irritant slowdown, off by default.** FDS+Evac has no irritant slowdown, so
  `enable_fic_speed` defaults to false and `run.py` switches the rule on only
  with `--enable-fic-speed`. Before it became opt-in, it was on whenever a gas
  FED model was loaded. When on, `default_fic` sums \(C_i / F_{\mathrm{FIC},i}\) over the
  same seven irritants (constants in `_FIC_COEFFS_PPM`, not integrated over
  time). At each FED update where FIC > 0, the agent's irritant factor is set
  to \(g = \max(\texttt{fic\_min\_factor},\ 1 - \texttt{fic\_alpha}\cdot\mathrm{FIC})\)
  (`scenario.py`, `run_scenario`) and multiplies the smoke factor. The rule is a
  pyFDS-Evac assumption with no known source
  ([#147](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/147)).
  When FIC is exactly 0 the last factor stays in force
  ([#142](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/142)).
- **Incapacitation.** Once the cumulative gas FED or heat FED reaches the
  agent's threshold for that dose, its desired speed is set to zero and it
  remains as a static obstacle. An agent incapacitated during pre-movement is
  released again when its pre-movement time ends
  ([#145](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/145)). In
  `probabilistic` mode each agent draws each threshold once, from the run's
  seed, as `_sample_threshold` does:
  \(D_i = \texttt{fed\_threshold} \cdot \exp(\sigma Z)\), \(Z \sim N(0, 1)\).
  In `deterministic` mode every agent uses the threshold itself. Both doses
  are deterministic by default: the gas dose as in FDS+Evac, and the heat
  dose since no population spread for heat is published. The threshold at
  which an agent stops in the simulation is not, by itself, a design
  acceptance criterion; FED 1 describes the median occupant (see
  [Incapacitation thresholds](/fundamentals/incapacitation-thresholds.md)).

| Field | Default | CLI flag |
|---|---|---|
| `enable_fic_speed` | `False` | `--enable-fic-speed` |
| `fic_alpha` | `0.7` | `--fic-alpha` |
| `fic_min_factor` | `0.3` | `--fic-min-factor` |
| `fed_threshold` | `1.0` | `--fed-threshold` |
| `incapacitation_mode` | `"deterministic"` | `--incapacitation-mode` |
| `susceptibility_sigma` | `0.94` | `--susceptibility-sigma` |
| `heat_fed_threshold` | `1.0` | `--heat-fed-threshold` |
| `heat_incapacitation_mode` | `"deterministic"` | `--heat-incapacitation-mode` |
| `heat_susceptibility_sigma` | `0.94` | `--heat-susceptibility-sigma` |
| `o2_threshold_percent` (`DefaultFedConfig`) | `20.0` | `--o2-threshold-percent` |

The gas and heat FED are updated every `DefaultFedConfig.update_interval_s`,
which `run.py` sets from `--smoke-update-interval`. `--disable-tenability`
turns off the slowdown and both stops; the doses are still computed. The FED
history CSV (`--output-fed-history`) carries the columns `fic`,
`fic_speed_factor` and `incapacitated`.

![Three panels: f(K) against K, g(FIC) against FIC, and their product as a heat map over K and FIC](/images/concepts/tenability_speed_curves.png)

*(a) Frantzich–Nilsson factor f(K) [-] against K [1/m], floor 0.1.
(b) Irritant factor g(FIC) [-] against FIC [-], floor 0.3. (c) The product
f(K)·g(FIC) [-], with contours at 0.25, 0.5 and 0.75; where both floors apply
it is 0.1 × 0.3 = 0.03. FED does not appear on these axes; it only sets the speed to
zero at the agent's threshold. Script: `scripts/generate_tenability_curves.py`.*

## FDS input pitfalls

- **Conflicting `&INIT` records silently zero out prescribed gas
  concentrations.** FDS resets the *entire* domain's species composition on
  each `&INIT` record that has no `XB` bounding box, so a second `&INIT`
  (e.g. one that only sets soot) overwrites an earlier one (e.g. one that
  sets CO/CO2/O2), leaving those species at 0 with no warning. All species
  prescribed via `&INIT` in a test deck must go in a single record. This is
  an FDS input-authoring pitfall, not a pyFDS-Evac bug; its symptom is
  near-zero toxic gas readings.
- **`EXTINCTION` is not the smoke extinction coefficient.** It is an
  unrelated FDS quantity (see [Extinction coefficient](/fundamentals/extinction.md)).
  `load_slice_sampler` requires `SOOT EXTINCTION COEFFICIENT` and raises
  `IndexError` when it is absent (`pyfds_evac/core/fds_sampling.py`).

## Verification

- Equation-level constant-exposure checks for all coded terms are covered in
  [tests/test_fed.py](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/test_fed.py)
- An ISO 20414:2020 Test 19 (Table 22) stationary benchmark is covered with `assets/ISO-table22`,
  comparing the runtime `FED=1` crossing time against the analytical reference

Generate the ISO 20414 Test 19 (Table 22) stationary FED verification figure:

```bash
uv run python scripts/generate_iso_table22_stationary_plot.py
```

Figure: ![ISO 20414 Test 19 (Table 22) stationary FED verification](/artifacts/iso-table22-stationary-fed.png)

## What is not modelled

- Radiant heat from hot surfaces or a flame, except as the excess f·(U − 4σT_s⁴) from FDS
  `INTEGRATED INTENSITY` with `--heat-radiant-source integrated-intensity`
  and a user factor. Otherwise the heat dose is convective, or with
  `--heat-fed-method total-flux` adds the radiation of the gas at the head,
  or with `--heat-regime layer` that of a hot upper layer
  ([Heat](/models/heat.md)).
- Effects of heat on route choice or walking speed: the heat FED only
  incapacitates.
- FED activity level: the CO term is fixed at light work; rest and heavy
  work are not supported
  ([#135](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/135)).
- **Height-relative FED and smoke sampling**: extinction, temperature and
  each gas are sampled from the horizontal FDS slice closest to
  `--smoke-slice-height` (default 1.6 m, FDS+Evac `HUMAN_SMOKE_HEIGHT`). All agents share these slices regardless of
  their individual heights.  Pathfinder samples at 90 % of each occupant's height,
  which is more accurate for scenarios with mixed-height populations (children,
  wheelchair users).  A per-agent sampling height would require either multiple
  slice outputs at different elevations or 3-D slice data, and is a known
  approximation of the current model.

## Usage

See [docs/usage.md](/docs/usage.md) for the full catalogue of
`run.py` flags (scenario, FDS coupling, FED, rerouting, tenability)
and the post-processing scripts. Note: if an agent
sample lies outside the FDS domain the implementation falls back to
ambient conditions.

## Deviations from the literature

The published forms are on [Asphyxiant FED](/fundamentals/asphyxiant-fed.md)
and [Irritant gases](/fundamentals/irritants.md). The gas sum has the Purser /
FDS+Evac guide structure (`fed.py`, `FedComponents.total_rate_per_min`), not the ISO 13571 one. Within it, the
code follows the guide, which cites the 3rd edition of the SFPE Handbook,
rather than the 5th edition, except that the HCN term is computed as FDS
computes it
([#149](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/149)):

- **HCN.** The code computes the exponential term as FDS does,
  \(\exp(C_{\mathrm{CN}}/43)/220 - 1/220\) with
  \(C_{\mathrm{CN}} = C_{\mathrm{HCN}} - (C_{\mathrm{NO}} + C_{\mathrm{NO_2}})\)
  (`_cn_fed_rate_per_minute`), not the 5th-edition power law (Eq. 63.24;
  [#149](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/149)). The
  FDS code that FDS+Evac runs subtracts NO + NO2, with the offset 0.00454545,
  about 1/220 (FDS 6.7.6 `func.f90`, function `FED`), and has done so since
  firemodels/fds 694e033 (2011); earlier versions had no HCN term. The
  FDS+Evac guide instead writes the offset as 0.0045 (Eq. 14) and
  \(C_{\mathrm{CN}} = C_{\mathrm{HCN}} - C_{\mathrm{NO_2}}\) (Eq. 15), which
  FDS and FDS+Evac never computed; pyFDS-Evac followed that text before
  ([#159](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/159)). The
  FDS verification case `FED_FIC` separates the two forms and is reproduced in
  `tests/verification/test_fed_verif.py` (A2.8). The 5th edition also
  subtracts NO + NO2, because methaemoglobin formed by NO and NO2 binds
  cyanide (Ch. 63, p. 2370): with coefficient 1 in Eq. 63.26 (p. 2362) but
  0.67 in the note to the FED equation (p. 2372), so the chapter is
  inconsistent. No source we read supports NO2 alone, and the 3rd-edition
  wording the guide cites is not verified
  ([#152](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/152)).
  Organic nitriles are ignored. Ch. 63 gives the critical range of its
  5th-edition time-to-incapacitation relationship as about 80 to 180 ppm,
  from primate and human data (p. 2361). That range is not documented for the
  exponential term; that the term is an extrapolation below 80 ppm is our
  inference ([#159](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/159)).
- **CO₂.** Eq. 63.34 (`fed.py`, `_hyperventilation_factor`), not its simplification Eq. 63.35 used in
  Eq. 63.38. The 70 L/min limit on \(V_E\times VCO_2\) is not applied, and
  the CO₂ asphyxiant endpoint \(F_{I_{CO_2}}\) is not computed.
- **CO.** Fixed at light work (`fed.py`, `_co_fed_rate_per_minute`), Eq. 63.18 at its default
  \(V_E\) and *D*.
- **O₂.** The rate is zero at or above `o2_threshold_percent`, 20.0 % O₂
  by default, the guard of FDS+Evac's code (the `FED` function of FDS 6.7.6
  `func.f90` adds the term only when X_O2 < 0.20); neither Purser nor the
  guide has it. It stops a tiny ambient rate from accumulating over long runs
  or outside the FDS domain. `--o2-threshold-percent 19.5` restores the
  previous default, the OSHA limit that Pathfinder uses. The O₂ rate is Handbook Eq. 63.50
  per minute, with no factor 60; see the warning below on the FDS+Evac
  guide's Eq. 18.

![Low-oxygen time to incapacitation against O2 from 3.9 to 20.9 % on a log time axis: a straight line, solid over the decompression data from 3.9 to 9.6 % and dashed above, with vertical lines at 15 % (140 min) and 20 % (about 2090 min)](/images/fundamentals/fed_o2.png)

*Time to incapacitation by low oxygen, \(t_{IO}\) [min], Eq. 63.50: solid
over the decompression data (3.9–9.6 % O₂), dashed above. pyFDS-Evac
evaluates this law up to `o2_threshold_percent` (20 % by default, dash-dot
line, about 2090 min) and adds nothing at or above it; everything between
about 10 % and the gate is extrapolation. Dotted: 15 % O₂, down to which
there is little effect in humans (Purser & McAllister 2016, p. 2364). Figure
and sources: [Asphyxiant FED](/fundamentals/asphyxiant-fed.md). Script:
`scripts/figures/fundamentals_fed_o2.py`.*

> [!WARNING]
> **FDS+Evac guide, Eq. 18 (low O₂).** The guide (Korhonen 2021) divides the
> O₂ term by 60 while stating that *t* is in minutes. Taken literally, that
> gives an O₂ dose 60 times smaller than Purser's Eq. 63.50. The code
> FDS+Evac runs does not do this: FDS divides by 60 only because its time step
> is in seconds. pyFDS-Evac uses Eq. 63.50 per minute, as the code does. If
> you rebuild FDS+Evac's FED from the guide, leave the 60 out.
>
> Our reading is that the 60 survives from the 2009 guide, which gave the
> FED equations with *t* in seconds; the evidence is on
> [Asphyxiant FED](/fundamentals/asphyxiant-fed.md).

The irritant slowdown \(g\), when enabled (`fed.py`, `TenabilityConfig.fic_alpha`, `TenabilityConfig.fic_min_factor`), is multiplied with the smoke
factor (`direct_steering_runtime.py`, `set_agent_fic_factor`). Its constants were not found
in the Handbook, the FDS+Evac guide or `evac.f90`
([#147](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/147)). The
Handbook uses a different curve and adds the smoke and irritant losses instead
of multiplying them (Eq. 63.14). Because the Frantzich–Nilsson smoke contained
acetic acid, \(f(K)\) already includes irritant slowing, so multiplying it by
\(g\) partly counts irritancy twice
([#153](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/153)).

Heat uses the convective Eq. 63.44 (`fed.py`, `_heat_fed_rate_per_minute`) unless `--heat-endpoint`
selects Eq. 63.45, 63.46 or 63.47, or `--heat-fed-method total-flux` the
flux law of Eqs. 63.49 and 63.43 ([Heat](/models/heat.md)). The log-normal σ of both
thresholds (`fed.py`, `TenabilityConfig.susceptibility_sigma`, `TenabilityConfig.heat_susceptibility_sigma`) is, for the gas dose, a compromise between
two bin edges of NIST TN 1797: it puts 10 % of agents below FED 0.3 and 88 %
below 3 (see [Incapacitation thresholds](/fundamentals/incapacitation-thresholds.md)
and [#148](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/148)). The
heat dose is deterministic by default; in `probabilistic` mode it reuses the
same σ without a data basis.
