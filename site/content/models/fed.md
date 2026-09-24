---
title: "Fractional effective dose"
weight: 2
math: true
---

The FED model implements the full ISO 13571 / Purser formulation as
described in Section 3.4 of the
[FDS+Evac Technical Reference and User's Guide](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/materials/FDS+EVAC_Guide.pdf)
(Korhonen, 2021).

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

## Recent additions

The FED model was extended in March 2026 to include all ISO 13571 terms:

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

All new terms are fully tested with constant-exposure unit tests in
`tests/test_fed.py`.

## Bug fixes (July 2026)

- **O2 hypoxia rate was 60x too slow.** `_o2_hypoxia_rate_per_minute` divided
  by an extra factor of 60, turning the per-minute rate from guide Eq. 18 into
  a per-hour rate before it was accumulated on a per-minute clock. Below the
  19.5 % suppression threshold (a real hypoxic atmosphere, e.g. 0 % O2), this
  understated incapacitation risk by 60x — 2.6 s of true incapacitation time
  was reported as ~155 s. Fixed in `pyfds_evac/core/fed.py`; the equation
  table above and the formula were both corrected to match. Caught while
  validating a deliberately oxygen-depleted homogeneous-gas test case.
- **Conflicting `&INIT` records silently zero out prescribed gas
  concentrations.** FDS resets the *entire* domain's species composition on
  each `&INIT` record that has no `XB` bounding box, so a second `&INIT`
  (e.g. one that only sets soot) overwrites an earlier one (e.g. one that
  sets CO/CO2/O2), leaving those species at 0 with no warning. All species
  prescribed via `&INIT` in a test deck must go in a single record. This is
  an FDS input-authoring pitfall, not a pyFDS-Evac bug, but it produced the
  same symptom as the rate bug above (near-zero toxic gas readings) and is
  easy to reintroduce, so it's called out here.
- **The smoke-speed model no longer falls back to FDS's `EXTINCTION`
  quantity.** `EXTINCTION` and `SOOT EXTINCTION COEFFICIENT` are two
  unrelated FDS slice quantities, not old/new spellings of the same field:
  `EXTINCTION` is a 0/1/-1 combustion-suppression flag (FDS User Guide
  Sec. 22.10.29), while the smoke extinction coefficient K [1/m] is
  `EXTINCTION COEFFICIENT` (Sec. 22.10.5), recorded by FDS as `SOOT
  EXTINCTION COEFFICIENT` for the default species. A case lacking the soot
  slice was silently sampling the combustion flag instead and feeding 0/1/-1
  into the smoke-speed model as if it were K. `load_slice_sampler` now
  requires `SOOT EXTINCTION COEFFICIENT` and raises `IndexError` when it's
  absent, instead of a quiet, meaningless fallback
  (`pyfds_evac/core/fds_sampling.py`).

## Verification

- Equation-level constant-exposure checks for all ISO 13571 terms are covered in
  [tests/test_fed.py](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/tests/test_fed.py)
- An ISO Table 22 style stationary benchmark is covered with `assets/ISO-table22`,
  comparing the runtime `FED=1` crossing time against the analytical reference

Generate the ISO Table 22 stationary FED verification figure:

```bash
uv run python scripts/generate_iso_table22_stationary_plot.py
```

Figure: ![ISO Table 22 stationary FED verification](/artifacts/iso-table22-stationary-fed.png)

## What is not implemented yet

- Thermal FED terms (radiant heat, convective heat)
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
