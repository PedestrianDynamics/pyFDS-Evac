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
([Endpoint](#endpoint)):

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
| `fatal` | 16.7 | Eq. 63.47: \(2\times10^{18}\,T^{-9.0403} + 10^{8}\,T^{-3.10898}\) |

*r* from pp. 2382 and 2384, the laws from pp. 2382–2383; the pairing is
explained in [Heat](/fundamentals/heat.md). The rate is \(1/t\)
(`endpoint_heat_fed_rate_per_minute`); a temperature at or below 0 °C, or
not finite, gives zero. `--heat-endpoint` without `--enable-heat-fed` logs a
warning and leaves the heat dose off. Radiant heat is not an
input yet, so *r* is recorded but does not enter the dose. The Handbook prints
16.7 for the fatal dose; spec 016 writes 16.667. By maintainer decision,
heat FED = 1 is meant as the fatal endpoint; `--heat-endpoint fatal` gives
that meaning. Without the option the dose stays Eq. 63.44.

The caption of Table 63.21 (p. 2385) says Eq. 63.44, but its per-minute values
are those of Eq. 63.45; the tests use the table as the oracle for
`tolerance`.

The Handbook relates Eqs. 63.45–63.47 to heated air with less than 10 %
water vapour by volume (p. 2383) and gives no upper temperature. **Assumption:**
the upper limit is taken as 205 °C, the highest dry-air tolerance point of
Table 63.17 (Veghte, 4 min, p. 2375). With an endpoint, each FED history
sample whose temperature exceeds 205 °C (`HEAT_CONVECTIVE_VALIDITY_MAX_C`) is
flagged. The flag does not clip the rate: Table 63.21 applies the law at
405 °C.

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

`--disable-tenability` turns off the stop; the dose is still computed.

## Output

The FED history CSV (`--output-fed-history`) carries `temperature_celsius`,
`heat_fed_rate_per_min` and `heat_fed_cumulative` per agent and update, and
`incapacitation_cause` (`gas`, `heat` or `gas+heat`) for agents that stopped.
With `--heat-endpoint` it also carries `heat_endpoint` and
`heat_outside_validity` (`True` above 205 °C), and the run manifest records
`heat_endpoint`. `incapacitation_cause` still reads `heat` for every
endpoint; `heat_endpoint` says which one.

## What is not modelled

- **Radiant heat.** Only convective heat from the gas temperature is
  counted: no flux from a hot upper layer, from hot surfaces, or from a flame
  in view ([#221](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/221),
  [#222](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/222),
  [#223](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/223)).
- **The default endpoint.** Without `--heat-endpoint`, heat FED = 1 is the
  Eq. 63.44 time. Eq. 63.44 is labelled a time to incapacitation, but its
  times lie near the Handbook's tolerance curve (Eq. 63.45) rather than its
  injury or fatal ones. Whether the default changes is open
  ([#218](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/218),
  [#220](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/220)).
- **Validity range.** Humidity is not sampled, so humid smoke is never
  flagged. Without `--heat-endpoint`, temperatures above 205 °C are not
  flagged either, although Eq. 63.44 rests on the same data (p. 2382).
- **Web GUI.** The GUI does not offer `--heat-endpoint`
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

## Sources

- Purser, D. A., & McAllister, J. L. (2016). Assessment of hazards to
  occupants from smoke, toxic gases, and heat. In *SFPE Handbook of Fire
  Protection Engineering* (5th ed., Ch. 63). Springer.
  doi:10.1007/978-1-4939-2565-0_63
