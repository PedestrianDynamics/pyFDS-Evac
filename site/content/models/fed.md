---
title: "Fractional effective dose"
weight: 2
math: true
---

The FED model implements the Purser formulation (as in the FDS+Evac guide; ISO 13571 keeps irritants in a separate FEC rather than in FED) as
described in Section 3.4 of the
FDS+Evac Technical Reference and User's Guide
(Korhonen, 2021).

Background: the ideas behind this model are explained on the [Concepts](/docs/concepts.md) page
and in the talk [*A Modular Workflow for Visibility-Aware Evacuation Modelling*](https://pedestriandynamics.org/pyFDS-Evac/talks/visibility-seminar-2026/)
([PDF](https://pedestriandynamics.org/pyFDS-Evac/talks/pyFDS-Evac_visibility_seminar_2026.pdf)).

## Implemented equation (guide Eq. 12)

$$
\mathrm{FED}_{\mathrm{tot}} = \bigl(\mathrm{FED}_{\mathrm{CO}} + \mathrm{FED}_{\mathrm{CN}} + \mathrm{FED}_{\mathrm{NO_x}} + \mathrm{FLD}_{\mathrm{irr}}\bigr) \times \mathrm{HV}_{\mathrm{CO_2}} + \mathrm{FED}_{\mathrm{O_2}}
$$

| Term | Guide Eq. | Formula | Input |
|------|-----------|---------|-------|
| FED_CO | (13) | $\int 2.764 \times 10^{-5}\, C_{\mathrm{CO}}^{1.036}\, dt$ | CO (ppm) |
| FED_CN | (14-15) | $\int \bigl(\exp(C_{\mathrm{CN}}/43)/220 - 0.0045\bigr)\, dt$, where $C_{\mathrm{CN}} = C_{\mathrm{HCN}} - C_{\mathrm{NO_2}}$ | HCN, NO2 (ppm) |
| FED_NOx | (16) | $\int C_{\mathrm{NO_x}}/1500\, dt$, where $C_{\mathrm{NO_x}} = C_{\mathrm{NO}} + C_{\mathrm{NO_2}}$ | NO, NO2 (ppm) |
| FLD_irr | (17) | $\int \sum_i C_i / F_{\mathrm{FLD},i}\, dt$ | HCl, HBr, HF, SO2, NO2, acrolein, formaldehyde (ppm) |
| HV_CO2 | (19) | $\exp(0.1903\, C_{\mathrm{CO_2}} + 2.0004)/7.1$ | CO2 (vol %) |
| FED_O2 | (18) | $\int 1/\exp\bigl(8.13 - 0.54\,(20.9 - C_{\mathrm{O_2}})\bigr)\, dt$ | O2 (vol %) |

Irritant Ct values (ppm·min) from guide Table 2:

| Species | HCl | HBr | HF | SO2 | NO2 | acrolein | formaldehyde |
|---------|------|------|------|------|------|----------|--------------|
| F_FLD | 114000 | 114000 | 87000 | 12000 | 1900 | 4500 | 22500 |

Gas species are read from FDS slice outputs via `fdsreader`. Required
species: CO, CO2, O2. Optional species (HCN, NO, NO2, HCl, HBr, HF,
SO2, acrolein, formaldehyde) are loaded when available; missing species
default to 0 and contribute nothing to the FED sum. With only the three
required species, the model reduces to the original FDS+Evac default
pathway: `FED_CO * HV_CO2 + FED_O2`.

## Additional terms

Beyond the three-gas FDS+Evac default, the model includes all Purser terms:

- **HCN (hydrogen cyanide) and NO2 (nitrogen dioxide)**: CN-term for narcosis,
  where NO2 has a protective effect (C_CN = C_HCN - C_NO2)
- **NO (nitric oxide)**: Added to NOx-term alongside NO2
- **Multiple irritant gases**: HCl, HBr, HF, SO2, NO2, acrolein, formaldehyde
  with species-specific Ct thresholds from guide Table 2
- **O2 hypoxia guard**: The O2 FED term (guide Eq. 18) is suppressed at or
  above 19.5 % O2 (OSHA safe-air threshold). At ambient conditions (20.9 %)
  the denominator of Eq. 18 is non-zero, producing a tiny but finite rate that
  accumulates spuriously over long simulations or when agents sample outside the
  FDS domain (where O2 defaults to 20.9 %). The guard sets the rate to zero
  when O2 ≥ 19.5 %, matching the default behaviour in Pathfinder (Thunderhead
  Engineering).

All terms are tested with constant-exposure unit tests in
`tests/test_fed.py`.

## Convective heat

A separate heat FED is accumulated from the FDS gas temperature when the case
has a `TEMPERATURE` slice (SFPE Handbook, 5th ed., Eq. 63.44):
$\mathrm{FED}_{\mathrm{heat}} = \int T^{3.4} / (5 \times 10^{7})\, dt$, with
$T$ in °C and $t$ in minutes. It is a running total of its own, not added to the
gas FED; an agent is incapacitated when either total crosses its threshold
(`--heat-fed-threshold`, median 1.0).

## FDS input pitfalls

- **Conflicting `&INIT` records silently zero out prescribed gas
  concentrations.** FDS resets the *entire* domain's species composition on
  each `&INIT` record that has no `XB` bounding box, so a second `&INIT`
  (e.g. one that only sets soot) overwrites an earlier one (e.g. one that
  sets CO/CO2/O2), leaving those species at 0 with no warning. All species
  prescribed via `&INIT` in a test deck must go in a single record. This is
  an FDS input-authoring pitfall, not a pyFDS-Evac bug; its symptom is
  near-zero toxic gas readings.
- **`EXTINCTION` is not the smoke extinction coefficient.**
  `EXTINCTION` and `SOOT EXTINCTION COEFFICIENT` are two
  unrelated FDS slice quantities, not old/new spellings of the same field:
  `EXTINCTION` is a 0/1/-1 combustion-suppression flag (FDS User Guide
  Sec. 22.10.29), while the smoke extinction coefficient K [1/m] is
  `EXTINCTION COEFFICIENT` (Sec. 22.10.5), recorded by FDS as `SOOT
  EXTINCTION COEFFICIENT` for the default species. `load_slice_sampler`
  requires `SOOT EXTINCTION COEFFICIENT` and raises `IndexError` when it is
  absent (`pyfds_evac/core/fds_sampling.py`).

## Verification

- Equation-level constant-exposure checks for all Purser terms are covered in
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
- FED activity level: the CO term uses the light-work coefficient
  2.764e-5; rest and heavy work are not supported
  ([#135](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/135)).
- **Height-relative FED and smoke sampling**: gas concentrations and extinction
  are sampled from a single horizontal FDS slice at a fixed height
  (`slice_height_m`, default 2.0 m), shared by all agents regardless of their
  individual heights.  Pathfinder samples at 90 % of each occupant's height,
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

## Tenability: irritant slowdown and incapacitation

On top of the Frantzich–Nilsson extinction–speed law, pyFDS-Evac
applies two Purser/FDS+Evac rules when a FED model is loaded:

- **FIC-driven slowdown.** Purser's Fractional Irritant
  Concentration (HCl, HBr, HF, SO2, NO2, acrolein, formaldehyde; see
  `pyfds_evac.core.fed.default_fic`) multiplies the Frantzich speed
  by `max(fic_min_factor, 1 − fic_alpha·FIC)`. Defaults:
  `fic_alpha = 0.7`, `fic_min_factor = 0.3`.
- **Incapacitation at the FED threshold.** Once cumulative FED crosses
  an agent's threshold, its target speed is driven to zero for the rest
  of the run and the agent remains as a static obstacle. Incapacitation
  is a *population* endpoint (NIST TN 1797 / Purser: ~11 % of occupants
  by FED 0.3, 50 % by 1, 89 % by 3), so by default each agent draws its
  own threshold from a log-normal `D_incap = D₅₀·exp(σ·Z)`, `Z ~ N(0,1)`
  (median `D₅₀ = --fed-threshold = 1`, `σ = --susceptibility-sigma =
  0.94`), sampled from the run's seed for reproducibility. Pass
  `--incapacitation-mode deterministic` to make every agent use the same
  threshold (the legacy uniform rule).

Both rules are enabled by default and can be tuned via CLI flags
`--fic-alpha`, `--fic-min-factor`, `--fed-threshold`,
`--incapacitation-mode`, `--susceptibility-sigma`, or turned off
entirely with `--disable-tenability`. The FED history CSV
(`--output-fed-history`) gains three extra columns `fic`,
`fic_speed_factor`, `incapacitated`.

![Three panels: f(K) against K, g(FIC) against FIC, and their product as a heat map over K and FIC](/images/concepts/tenability_speed_curves.png)

*Left: Frantzich–Nilsson factor f(K) [-] against K [1/m], floor 0.1. Middle:
irritant factor g(FIC) [-] against FIC [-], floor 0.3. Right: the product
f(K)·g(FIC) [-]. FED does not appear on these axes; it only sets the speed to
zero at the agent's threshold. Script: `scripts/generate_tenability_curves.py`.*
