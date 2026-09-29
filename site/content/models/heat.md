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
ed. Eq. 63.44:

$$
\dot{\mathrm{FED}}_{\mathrm{heat}} = T^{3.4} / (5 \times 10^{7}) \quad [1/\mathrm{min}],
$$

with *T* the gas temperature in °C at the agent's position, read from the
`TEMPERATURE` slice at `--smoke-slice-height` (1.6 m by default, as
FDS+Evac's `HUMAN_SMOKE_HEIGHT`). No heat flux enters the law, neither
incident nor net: it takes the gas temperature only. The dose is updated on the same interval as
the gas FED (`--smoke-update-interval`) and is a running total of its own,
never added to the gas FED.

If the case has no `TEMPERATURE` slice, the run continues without a heat dose
and logs a warning; every heat column then reads zero.

A heat-only case needs no soot. Without a `SOOT EXTINCTION COEFFICIENT`
slice the run logs two warnings and continues: there is no smoke-speed
model, so agents walk at clear-air speed and route costs see K = 0, and the
visibility model falls back to clear air
([#248](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/248)).
Neither enters the heat-dose rate; both can change where agents walk, and
so the temperature they are exposed to.

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
  assumption with no data basis for heat. The Handbook's radiant lethality
  figures point to a much narrower spread, for an endpoint not modelled here
  ([Incapacitation thresholds](/fundamentals/incapacitation-thresholds.md#heat),
  [#225](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/225)).

The gas dose is also deterministic by default; the two modes are set separately
(`--incapacitation-mode` and `--heat-incapacitation-mode`).

The two doses do not share an endpoint. Gas FED = 1 is Purser's
incapacitation endpoint. Heat FED = 1 is the Eq. 63.44 time, which the
Handbook labels time to incapacitation (p. 2382) but whose times lie near its tolerance curve
(see [What is not modelled](#what-is-not-modelled)). Both stop the agent in
the same way and set the same `incapacitated` flag; only
`incapacitation_cause` tells which endpoint was reached.

| Field | Default | CLI flag |
|---|---|---|
| `enable_heat_fed` | `False` | `--enable-heat-fed` |
| `heat_fed_threshold` | `1.0` | `--heat-fed-threshold` |
| `heat_incapacitation_mode` | `"deterministic"` | `--heat-incapacitation-mode` |
| `heat_susceptibility_sigma` | `0.94` | `--heat-susceptibility-sigma` |

`--disable-tenability` turns off the stop; the dose is still computed.

## Output

The FED history CSV (`--output-fed-history`) carries `temperature_celsius`,
`heat_fed_rate_per_min` and `heat_fed_cumulative` per agent and update, and
`incapacitation_cause` (`gas`, `heat` or `gas+heat`) for agents that stopped.
The `incapacitated` column is true whichever dose stopped the agent, so it
mixes the gas and heat endpoints; filter on `incapacitation_cause` to count
them apart. `gas+heat` means both doses crossed their thresholds on the same
update; a crossing by the other dose after the agent has stopped is not
recorded.

## What is not modelled

- **Radiant heat.** Only convective heat from the gas temperature is
  counted: no flux from a hot upper layer, from hot surfaces, or from a flame
  in view ([#221](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/221),
  [#222](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/222),
  [#223](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/223)).
  FDS reference data for that term exist but are not read by the model:
  [Heat radiometer reference decks](/verification/testing-heat-radiometer.md)
  ([#224](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/224)).
- **The endpoint.** Today heat FED = 1 is the Eq. 63.44 time. Eq. 63.44 is
  labelled a time to incapacitation, but its times lie near the Handbook's
  tolerance curve (Eq. 63.45) rather than its injury or fatal ones. The fatal
  endpoint (D = 16.667) chosen for the planned total-flux dose
  (`specs/016-heat-fed/SPEC.md`) is not implemented
  ([#220](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/220),
  [#223](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/223)).
- **Population spread.** No consulted source gives a spread of tolerance
  for the convective dose; the opt-in σ = 0.94 is borrowed from the gas dose
  ([#225](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/225)).
- **Validity range.** The convective data behind the law reach about 205 °C
  in air of low humidity (below 10 % water vapour). Higher temperatures and
  humid smoke are extrapolation, and neither is flagged.
- **Falling exposure and recovery.** The summed dose assumes exposure that is
  steady or rising (Eq. 63.48); a fleeing agent's exposure falls, and no
  recovery is modelled.
- **Clothing and face covering**, which protect against both convective and
  radiant heat.
- **Effects on walking speed or route choice.** The heat dose only
  incapacitates ([#81](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/81)).
- **Tests against the Handbook.** Eq. 63.44 is checked against the
  convective rows of Table 63.20 (p. 2383) and the dry-air rows of
  Table 63.17 (p. 2375). Against Table 63.20 it gives 0.61 to 1.07 times
  the tabulated times, never longer than the table's whole-minute rounding
  allows (read as ±0.5 min, an assumption); it never exceeds the times
  reported as tolerated in Table 63.17's dry-air rows. The factor-2 band
  the test allows is an assumption, not a sourced tolerance. Table 63.21 (p. 2385) and the radiant rows of
  Table 63.20 are kept as reference values that call no pyFDS-Evac code,
  because neither Eq. 63.45 nor a radiant term is implemented
  ([#219](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/219),
  [#223](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/223)).

## Sources

- Purser, D. A., & McAllister, J. L. (2016). Assessment of hazards to
  occupants from smoke, toxic gases, and heat. In *SFPE Handbook of Fire
  Protection Engineering* (5th ed., Ch. 63). Springer.
  doi:10.1007/978-1-4939-2565-0_63
