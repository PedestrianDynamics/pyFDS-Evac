---
title: "Heat"
weight: 3
math: true
---

> [!NOTE]
> This page is the specification of the heat dose. For the verification case
> (a uniform hot room at 100, 150 and 200 °C), see
> [Heat dose](/verification/testing-heat.md).

Based on: [Heat](/fundamentals/heat.md) and [Incapacitation thresholds](/fundamentals/incapacitation-thresholds.md).

FDS+Evac has no heat dose. In pyFDS-Evac it is opt-in, and when it is off
nothing on this page affects a run.

## What is computed

With `--enable-heat-fed` (`opts.enable_heat_fed`) and a `TEMPERATURE` slice in
the case, each agent accumulates a convective heat dose at
`_heat_fed_rate_per_minute` (`pyfds_evac/core/fed.py:217`), SFPE Handbook 5th
ed. Eq. 63.44 (p. 2382), unless `--heat-endpoint` selects another law
([Endpoint](#endpoint)) or `--heat-fed-method total-flux` selects the flux
law ([Total flux](#total-flux)):

$$
\dot{\mathrm{FED}}_{\mathrm{heat}} = T^{3.4} / (5 \times 10^{7}) \quad [1/\mathrm{min}],
$$

with *T* the gas temperature in °C at the agent's position, read from the
`TEMPERATURE` slice at `--smoke-slice-height` (1.6 m by default, as
FDS+Evac's `HUMAN_SMOKE_HEIGHT`). The dose is updated on the same interval as
the gas FED (`--smoke-update-interval`) and is a running total of its own,
never added to the gas FED.

If the case has no `TEMPERATURE` slice, the run continues without a heat dose
and logs a warning; every heat column then reads zero.

## Endpoint

`--heat-endpoint {tolerance,injury,fatal}` (default: none) replaces Eq. 63.44
with the convective law of one endpoint of Ch. 63, so that heat FED = 1 means
that endpoint. Each endpoint is stored with its radiant dose *r* of Eq. 63.43
(`HEAT_ENDPOINTS` in `pyfds_evac/core/fed.py`), so a radiant constant from one
endpoint cannot be paired with the convective law of another:

| `--heat-endpoint` | Radiant *r* [(kW/m²)^4/3 min] | Convective law, *t* [min], *T* [°C] |
|---|---|---|
| `tolerance` | 1.33 | Eq. 63.45: \(2\times10^{31}\,T^{-16.963} + 4\times10^{8}\,T^{-3.7561}\) |
| `injury` | 10 | Eq. 63.46: \(5\times10^{22}\,T^{-11.783} + 3\times10^{7}\,T^{-2.9636}\) |
| `fatal` | 16.667 | Eq. 63.47: \(2\times10^{18}\,T^{-9.0403} + 10^{8}\,T^{-3.10898}\) |

*r* from pp. 2382 and 2384, the laws from pp. 2382–2383; the pairing is
explained in [Heat](/fundamentals/heat.md). The rate is \(1/t\)
(`endpoint_heat_fed_rate_per_minute`); a temperature at or below 0 °C, or
not finite, gives zero. `--heat-endpoint` without `--enable-heat-fed` logs a
warning and leaves the heat dose off. *r* enters the dose only
with `--heat-fed-method total-flux` ([Total flux](#total-flux)); with the
convective laws it is recorded only. The fatal *r* is
16.667 (spec 016); the Handbook prints it as 16.7. By maintainer decision,
heat FED = 1 is meant as the fatal endpoint; `--heat-endpoint fatal` gives
that meaning. Without the option the convective dose stays Eq. 63.44.

The caption of Table 63.21 (p. 2385) says Eq. 63.44, but its per-minute values
are those of Eq. 63.45; the tests use the table as the oracle for
`tolerance`.

The Handbook relates Eqs. 63.45–63.47 to heated air with less than 10 %
water vapour by volume (p. 2383) and gives no upper temperature. **Assumption:**
the upper limit is taken as 205 °C, the highest dry-air tolerance point of
Table 63.17 (Veghte, 4 min, p. 2375). With an endpoint, each FED history
sample whose temperature exceeds 205 °C (`HEAT_CONVECTIVE_VALIDITY_MAX_C`) or
is not a finite number is flagged. The flag does not clip the rate: Table
63.21 applies the law at 405 °C. A non-finite sample adds no dose. Humidity
is not sampled, so its status is reported as unknown rather than flagged.

## Total flux

`--heat-fed-method total-flux` (opt-in, with `--enable-heat-fed`; default
`convective`, the laws above) replaces the convective laws with the
total-flux form of spec 016 (`specs/016-heat-fed/SPEC.md`). The heat flux to
the skin is Eq. 63.49 (p. 2383, symbols on p. 2384), `total_heat_flux_kw_m2`:

$$
q = \frac{\varepsilon\,\sigma\,(T_g^4 - T_s^4) + h\,(T_g - T_s)}{1000}
\quad [\mathrm{kW/m^2}],
$$

with \(T_g\) the gas temperature at the agent's position (the same
`TEMPERATURE` slice), \(T_s\) the skin temperature, both in K, and
\(\sigma = 5.67\times10^{-8}\) W m⁻² K⁻⁴ (p. 2384). Both terms are in W/m²
and divided by 1000 together; this is a decision of spec 016, since the
Handbook prints the division on the convective term only. The rate is
Eq. 63.43 with the endpoint dose *D* in place of *r*
(`total_flux_heat_fed_rate_per_minute`):

$$
\dot{\mathrm{FED}}_{\mathrm{heat}} = q^{1.33} / D \quad [1/\mathrm{min}].
$$

- *D* is the radiant dose of `--heat-endpoint` (1.33, 10 or 16.667); without
  it, the fatal 16.667, as heat FED = 1 is meant as the fatal endpoint.
- **No 2.5 kW/m² threshold.** The Handbook applies Eq. 63.43 above
  2.5 kW/m² only (p. 2384); spec 016 drops the threshold, so the dose
  accumulates at every positive flux. With the threshold, clear air
  (ε = 0.05, h = 8) would give no dose below about 310 °C.
- **Not added to a convective law.** The rate is \(q^{1.33}/D\) alone.
- At or below skin temperature (\(q \le 0\)) or for a non-finite
  temperature the rate is zero: no dose, and no recovery.

Only the "head in smoke" regime of spec 016 is implemented: ε applies to the
gas at the head, and no external radiation is added. ε, h and \(T_s\) have
no sourced values; their defaults are assumptions
(`HEAT_FLUX_ASSUMED_PARAMETERS`):

| Parameter | Default | CLI flag | Source status |
|---|---|---|---|
| ε | `0.5` | `--heat-emissivity` | **Assumption.** p. 2384: 0.05 for a gas, "perhaps 0.5 for smoke" |
| h [W m⁻² K⁻¹] | `5.0` | `--heat-convective-coefficient` | **Assumption.** p. 2384: "approximately 5–8 for slow-moving air", no unit; 5 is the value of the spec 016 convection check |
| \(T_s\) [°C] | `35.0` | `--heat-skin-temperature` | **Assumption.** Not given for Eq. 63.49; 35 °C is the draft's value, held fixed |

Invalid values (ε outside [0, 1], h < 0, or non-finite) are rejected.
`--heat-fed-method` without `--enable-heat-fed` logs a warning and leaves
the heat dose off.

## Incapacitation

When the cumulative heat dose reaches the agent's heat threshold, the agent
stops and stays in place as an obstacle, as for the gas dose.

- **`deterministic` (default).** Every agent uses `heat_fed_threshold`
  (1.0). No published source gives a population spread for heat tolerance:
  SFPE Ch. 63 gives population figures for heat only for radiant lethality
  (p. 2382), which is not modelled here.
- **`probabilistic` (opt-in).** Each agent draws its own threshold once, from
  the run's seed, on a stream independent of the gas threshold:
  \(D_i = \texttt{heat\_fed\_threshold} \cdot \exp(\sigma Z)\),
  \(Z \sim N(0, 1)\). The default σ = 0.94 is borrowed from the gas dose, an
  assumption with no data basis for heat.

The gas dose is probabilistic by default; the two modes are set separately
(`--incapacitation-mode` and `--heat-incapacitation-mode`).

| Field | Default | CLI flag |
|---|---|---|
| `enable_heat_fed` | `False` | `--enable-heat-fed` |
| `heat_fed_threshold` | `1.0` | `--heat-fed-threshold` |
| `heat_incapacitation_mode` | `"deterministic"` | `--heat-incapacitation-mode` |
| `heat_susceptibility_sigma` | `0.94` | `--heat-susceptibility-sigma` |
| `heat_endpoint` | `None` (Eq. 63.44) | `--heat-endpoint` |
| `heat_fed_method` | `"convective"` | `--heat-fed-method` |

`--disable-tenability` turns off the stop; the dose is still computed.

## Output

The FED history CSV (`--output-fed-history`) carries `temperature_celsius`,
`heat_fed_rate_per_min` and `heat_fed_cumulative` per agent and update, and
`incapacitation_cause` (`gas`, `heat` or `gas+heat`) for agents that stopped.
With `--heat-endpoint` it also carries `heat_endpoint`,
`heat_outside_validity` (`True` above 205 °C or for a non-finite temperature)
and `heat_humidity` (always `unknown`). The run manifest then records
`heat_endpoint` and `heat_validity`: the 205 °C limit, marked as assumed, the
humidity status and the < 10 % water-vapour limit. `incapacitation_cause` still reads `heat` for every
endpoint; `heat_endpoint` says which one.

With `--heat-fed-method total-flux` the FED history also carries
`heat_flux_kw_m2` (*q*), and the manifest records `heat_fed_method` and
`heat_flux_parameters` (ε, h, \(T_s\), *D*, and the names of the assumed
parameters). With an endpoint, `heat_outside_validity` still flags samples
above 205 °C: that limit belongs to the convective data of Eqs.
63.45–63.47, not to the flux law.

## What is not modelled

- **Radiant heat from outside the gas at the head.** The convective laws
  count convective heat only. The total-flux method adds the radiation of the
  gas around the head, but no flux from a hot upper layer, from hot surfaces,
  or from a flame in view: the "below a hot layer" regime of spec 016 and the
  external flux term are not implemented
  ([#221](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/221),
  [#222](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/222)).
- **Regime selection.** The total-flux method uses one ε everywhere. The
  default 0.5 treats every head as in smoke, which overestimates the dose in
  clear hot air; set `--heat-emissivity 0.05` for clear air. How to decide
  the regime per agent is open (spec 016, open question 4).
- **Total-flux parameters.** h, \(T_s\) and ε are assumptions (see
  [Total flux](#total-flux)); \(T_s\) is fixed and does not rise with
  exposure (spec 016, open questions 1 and 2).
- **The default endpoint.** Without `--heat-endpoint`, heat FED = 1 is the
  Eq. 63.44 time. Eq. 63.44 is labelled a time to incapacitation, but its
  times lie near the Handbook's tolerance curve (Eq. 63.45) rather than its
  injury or fatal ones. Whether the default changes is open
  ([#218](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/218),
  [#220](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/220)).
- **Validity range.** Humidity is not sampled, so humid smoke is never
  flagged; `heat_humidity` reads `unknown`
  ([#272](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/272)). Without `--heat-endpoint`, temperatures above 205 °C are not
  flagged either, although Eq. 63.44 rests on the same data (p. 2382).
- **Web GUI.** The GUI does not offer `--heat-endpoint` or
  `--heat-fed-method`
  ([#270](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/270)).
- **Falling exposure and recovery.** The summed dose assumes exposure that is
  steady or rising (Eq. 63.48); a fleeing agent's exposure falls, and no
  recovery is modelled.
- **Clothing and face covering**, which protect against both convective and
  radiant heat.
- **Effects on walking speed or route choice.** The heat dose only
  incapacitates ([#81](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/81)).
- **Tests.** The endpoint laws are checked against the Handbook's tables
  (Tables 63.20 and 63.21) and hand formulas. The default Eq. 63.44 is still
  checked only against its own closed form
  ([#219](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/219)).
  The total-flux method is checked against hand formulas of Eqs. 63.49 and
  63.43, the radiant rows of Table 63.20 and the convection table of spec 016,
  in unit tests and coupled corridor runs; the layer regime is not tested.

## Sources

- Purser, D. A., & McAllister, J. L. (2016). Assessment of hazards to
  occupants from smoke, toxic gases, and heat. In *SFPE Handbook of Fire
  Protection Engineering* (5th ed., Ch. 63). Springer.
  doi:10.1007/978-1-4939-2565-0_63
