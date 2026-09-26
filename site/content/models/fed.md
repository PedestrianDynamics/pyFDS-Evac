---
title: "Fractional effective dose"
weight: 2
math: true
---

Based on: [Asphyxiant fractional effective dose](/fundamentals/asphyxiant-fed.md), [Irritant gases](/fundamentals/irritants.md), [Heat](/fundamentals/heat.md) and [Incapacitation thresholds](/fundamentals/incapacitation-thresholds.md).

Symbols follow the [notation table](/docs/concepts.md#notation). The model
codes the Purser sum in the form of the FDS+Evac guide (Korhonen 2021, §3.4),
which adds irritants into the dose; ISO 13571 keeps them in a separate
concentration endpoint. The published equations are on the Fundamentals pages
linked above.

Background: the [Concepts](/docs/concepts.md) page
and the talk [*A Modular Workflow for Visibility-Aware Evacuation Modelling*](https://pedestriandynamics.org/pyFDS-Evac/talks/visibility-seminar-2026/)
([PDF](https://pedestriandynamics.org/pyFDS-Evac/talks/pyFDS-Evac_visibility_seminar_2026.pdf)).

## Coded form

`FedComponents.total_rate_per_min` (`pyfds_evac/core/fed.py:334`) returns the
gas FED rate [1/min]

$$
\dot{\mathrm{FED}} = \bigl(\dot{\mathrm{FED}}_{\mathrm{CO}} + \dot{\mathrm{FED}}_{\mathrm{CN}} + \dot{\mathrm{FED}}_{\mathrm{NO_x}} + \dot{\mathrm{FLD}}_{\mathrm{irr}}\bigr) \times \mathrm{HV}_{\mathrm{CO_2}} + \dot{\mathrm{FED}}_{\mathrm{O_2}},
$$

and `DefaultFedModel` integrates it over time, with *t* in minutes. Each term
is one function in `fed.py`:

| Term | Function | Coded rate [1/min] | Input |
|------|----------|--------------------|-------|
| CO | `_co_fed_rate_per_minute` | \(2.764 \times 10^{-5}\, C_{\mathrm{CO}}^{1.036}\) | CO (ppm) |
| CN | `_cn_fed_rate_per_minute` | \(\max\bigl(0,\ \exp(C_{\mathrm{CN}}/43)/220 - 0.0045\bigr)\), \(C_{\mathrm{CN}} = \max(0,\ C_{\mathrm{HCN}} - C_{\mathrm{NO_2}})\) | HCN, NO2 (ppm) |
| NOₓ | `_nox_fed_rate_per_minute` | \((C_{\mathrm{NO}} + C_{\mathrm{NO_2}})/1500\) | NO, NO2 (ppm) |
| Irritants | `_irritant_fld_rate_per_minute` | \(\sum_i C_i / F_{\mathrm{FLD},i}\) | seven irritants (ppm) |
| HV_CO2 | `_hyperventilation_factor` | \(\exp(0.1903\, C_{\mathrm{CO_2}} + 2.0004)/7.1\) (a factor, not a rate) | CO2 (vol %) |
| O2 | `_o2_hypoxia_rate_per_minute` | \(1/\exp\bigl(8.13 - 0.54\,(20.9 - C_{\mathrm{O_2}})\bigr)\); 0 at or above 19.5 % | O2 (vol %) |

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

When the case has a `TEMPERATURE` slice, a separate heat dose accumulates at
`_heat_fed_rate_per_minute` (`fed.py:207`),

$$
\dot{\mathrm{FED}}_{\mathrm{heat}} = T^{3.4} / (5 \times 10^{7}) \quad [1/\mathrm{min}],
$$

with *T* in °C. It is a running total of its own, never added to the gas FED.
The basis is on [Heat](/fundamentals/heat.md).

## Tenability: irritant slowdown and incapacitation

`TenabilityConfig` (`fed.py:216`) adds two rules. The slowdown and the gas
stop need the gas FED model; the heat stop needs only the heat FED model
(`run_config.py:246`–`256`).

- **Irritant slowdown.** `default_fic` sums \(C_i / F_{\mathrm{FIC},i}\) over the
  same seven irritants (constants in `_FIC_COEFFS_PPM`, not integrated over
  time). At each FED update where FIC > 0, the agent's irritant factor is set
  to \(g = \max(\texttt{fic\_min\_factor},\ 1 - \texttt{fic\_alpha}\cdot\mathrm{FIC})\)
  (`scenario.py:2076`–`2081`) and multiplies the smoke factor. When FIC is
  exactly 0 the last factor stays in force
  ([#142](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/142)).
- **Incapacitation.** Once the cumulative gas FED or heat FED reaches the
  agent's threshold for that dose, its desired speed is set to zero and it
  remains as a static obstacle. An agent incapacitated during pre-movement is
  released again when its pre-movement time ends
  ([#145](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/145)). In
  `probabilistic` mode each agent draws each threshold once, from the run's
  seed, as `_sample_threshold` does:
  \(D_i = \texttt{fed\_threshold} \cdot \exp(\sigma Z)\), \(Z \sim N(0, 1)\).
  In `deterministic` mode every agent uses the threshold itself.

| Field | Default | CLI flag |
|---|---|---|
| `fic_alpha` | `0.7` | `--fic-alpha` |
| `fic_min_factor` | `0.3` | `--fic-min-factor` |
| `fed_threshold` | `1.0` | `--fed-threshold` |
| `incapacitation_mode` | `"probabilistic"` | `--incapacitation-mode` |
| `susceptibility_sigma` | `0.94` | `--susceptibility-sigma` |
| `heat_fed_threshold` | `1.0` | `--heat-fed-threshold` |
| `heat_incapacitation_mode` | `"probabilistic"` | `--heat-incapacitation-mode` |
| `heat_susceptibility_sigma` | `0.94` | `--heat-susceptibility-sigma` |

The gas and heat FED are updated every `DefaultFedConfig.update_interval_s`,
which `run.py` sets from `--smoke-update-interval`. `--disable-tenability`
turns off the slowdown and both stops; the doses are still computed. The FED
history CSV (`--output-fed-history`) carries the columns `fic`,
`fic_speed_factor` and `incapacitated`.

![Three panels: f(K) against K, g(FIC) against FIC, and their product as a heat map over K and FIC](/images/concepts/tenability_speed_curves.png)

*Left: Frantzich–Nilsson factor f(K) [-] against K [1/m], floor 0.1. Middle:
irritant factor g(FIC) [-] against FIC [-], floor 0.3. Right: the product
f(K)·g(FIC) [-]. FED does not appear on these axes; it only sets the speed to
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

- Radiant heat. Only convective heat from the gas temperature is modelled.
- Effects of heat on route choice or walking speed: the heat FED only
  incapacitates.
- FED activity level: the CO term is fixed at light work; rest and heavy
  work are not supported
  ([#135](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/135)).
- **Height-relative FED and smoke sampling**: extinction and temperature are
  sampled from the horizontal FDS slice closest to `--smoke-slice-height`
  (default 2.0 m); each gas is read from the first slice of its quantity in the
  deck, whatever its height. All agents share these slices regardless of
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
FDS+Evac guide structure (`fed.py:334`), not the ISO 13571 one. Within it, the
code follows the guide, which cites the 3rd edition of the SFPE Handbook,
rather than the 5th edition
([#149](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/149)):

- **HCN.** The guide's exponential term (`fed.py:106`, `:109`), not the
  5th-edition power law (Eq. 63.24), and \(C_{\mathrm{CN}}\) ignores nitriles
  and NO (Eq. 63.26).
- **CO₂.** Eq. 63.34 (`fed.py:63`), not its simplification Eq. 63.35 used in
  Eq. 63.38. The 70 L/min limit on \(V_E\times VCO_2\) is not applied, and
  the CO₂ asphyxiant endpoint \(F_{I_{CO_2}}\) is not computed.
- **CO.** Fixed at light work (`fed.py:54`), Eq. 63.18 at its default
  \(V_E\) and *D*.
- **O₂.** The rate is zero at or above 19.5 % O₂ (`fed.py:66`, `:92`), a
  guard that neither Purser nor the guide has; it stops a tiny ambient rate
  from accumulating over long runs or outside the FDS domain, as Pathfinder
  does. The guide's Eq. 18 carries a factor 60 in the denominator while
  stating that *t* is in minutes; the code follows Handbook Eq. 63.50 without
  it.

The irritant slowdown \(g\) (`fed.py:241`–`242`) is multiplied with the smoke
factor (`direct_steering_runtime.py:186`–`190`). Its constants were not found
in the Handbook, the FDS+Evac guide or `evac.f90`
([#147](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/147)). The
Handbook uses a different curve and adds the smoke and irritant losses instead
of multiplying them (Eq. 63.14). Because the Frantzich–Nilsson smoke contained
acetic acid, \(f(K)\) already includes irritant slowing, so multiplying it by
\(g\) partly counts irritancy twice
([#153](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/153)).

Heat uses the convective Eq. 63.44 only (`fed.py:207`), not the mid-humidity
design form Eq. 63.45, and no radiant term. The log-normal σ of both
thresholds (`fed.py:252`, `:260`) is, for the gas dose, a compromise between
two bin edges of NIST TN 1797: it puts 10 % of agents below FED 0.3 and 88 %
below 3 (see [Incapacitation thresholds](/fundamentals/incapacitation-thresholds.md)
and [#148](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/148)). The
heat dose reuses the same σ without a data basis.
