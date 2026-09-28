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
gas at the head, and no external radiation is added unless the radiant term
comes from `INTEGRATED INTENSITY`
([Radiant flux from INTEGRATED INTENSITY](#radiant-flux-from-integrated-intensity)).
ε, h and \(T_s\) have no sourced values; their defaults are assumptions
(`HEAT_FLUX_ASSUMED_PARAMETERS`):

| Parameter | Default | CLI flag | Source status |
|---|---|---|---|
| ε | `0.5` | `--heat-emissivity` | **Assumption.** p. 2384: 0.05 for a gas, "perhaps 0.5 for smoke" |
| h [W m⁻² K⁻¹] | `5.0` | `--heat-convective-coefficient` | **Assumption.** p. 2384: "approximately 5–8 for slow-moving air", no unit; 5 is the value of the spec 016 convection check |
| \(T_s\) [°C] | `35.0` | `--heat-skin-temperature` | **Assumption.** Not given for Eq. 63.49; 35 °C is the draft's value, held fixed |

Invalid values (ε outside [0, 1], h < 0, or non-finite) are rejected.
`--heat-fed-method` without `--enable-heat-fed` logs a warning and leaves
the heat dose off.

### Radiant flux from INTEGRATED INTENSITY

`--heat-radiant-source integrated-intensity` (opt-in, total-flux only;
default `gas`, the ε term above) takes the radiant term from the FDS
`INTEGRATED INTENSITY` slice at the slice height, the same height as the
`TEMPERATURE` slice
([#221](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/221)).
FDS's *U* = ∫ *I* dΩ [kW/m²] (FDS User's Guide 6.10.1, Table 22.4, p. 403) is the
radiation arriving from all directions, not the flux onto a surface. A
surface sees one hemisphere, with rays weighted by cos θ, so its incident
flux lies between *U*/4 (a sphere, or a plate in an isotropic field) and *U*
(one small source seen face-on); *U*/2 holds for a plate facing a uniform
layer (spec 016). The flux to the skin is

$$
q = f\,U + \frac{h\,(T_g - T_s)}{1000} \quad [\mathrm{kW/m^2}],
$$

(`radiant_flux_from_integrated_intensity_kw_m2` for *f U*), and the rate is
\(q^{1.33}/D\) as above.

- **f U is incident flux.** Spec 016 takes the radiant tolerance data as
  incident flux, and the Handbook calls Eq. 63.49 "the total incident flux
  to the skin" (p. 2383); the skin's own emission σ\(T_s^4\) is not
  subtracted.
- **The ε term is not added.** *U* already contains the emission of the gas
  at the head, so ε σ (\(T_g^4 - T_s^4\)) would count it twice;
  `--heat-emissivity` is ignored with this source.
- **`--heat-u-factor` *f* in [0.25, 1] has no default.** No single factor
  holds (see Limits below), so *f* must be given with this source; without
  it, or outside [0.25, 1], the run stops with an error. *f* is the user's
  choice, not an assumption of the code.
- A case with no `INTEGRATED INTENSITY` slice is an error, not a zero: the
  run would otherwise read as a case without radiation. The source with the
  convective method is an error too.
- A non-finite *U* gives a zero rate, as for the gas term.

### Limits of the INTEGRATED INTENSITY source

- **Ambient background.** *U* is not zero in a cold room: at 20 °C,
  *U* = 4σ*T*⁴ = 1.68 kW/m². With no 2.5 kW/m² threshold, the incident
  *f U* gives a dose with no fire at all. With h = 5, \(T_s\) = 35 °C and
  *D* = 16.667 the fatal heat FED = 1 is reached after about 8.9 min
  (*f* = 1) or 69 min (*f* = 0.25). Whether to use incident *f U*, net *f U* − σ\(T_s^4\), or
  the excess above ambient *f* (*U* − 4σ\(T_a^4\)) is open
  ([#221](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/221)).
- **[0.25, 1] is not a bound for every orientation.** In the FDS radiometer
  data of [#224](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/224),
  below a hot layer the plate facing up gets about 0.41 *U*, but a plate
  facing down gets about 0.13 *U* and some facing sideways about 0.22 *U*,
  less than *f* = 0.25 gives. Beside a burner, plates facing up or away
  from the flame get about 0.12–0.14 *U*. One *f* serves one orientation.
- **Gauge devices are the preferred input** (spec 016): FDS
  `GAUGE HEAT FLUX GAS` devices give the flux to a skin-like plate from the
  full radiation solution, with no factor (FDS User's Guide 6.10.1,
  Eq. 22.35, p. 381). They are not read yet
  ([#276](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/276)).
- **Possible double count with convection.** The hot-air data behind
  Eqs. 63.45–63.47 may already include radiation from the walls of the test
  chambers. If so, adding *f U* to the convective term partly counts that
  radiation twice. This is an open question
  ([#221](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/221)).
- **Falling exposure.** As for every summed dose, Eq. 63.48 holds only
  while exposure is steady or rising.

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
| `heat_radiant_source` | `"gas"` | `--heat-radiant-source` |
| `heat_u_factor` | none, required with `integrated-intensity` | `--heat-u-factor` |

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
parameters). With `--heat-radiant-source integrated-intensity` the FED
history also carries `heat_integrated_intensity_kw_m2` (*U*), and
`heat_flux_parameters` adds `radiant_source`, `u_factor` and
`radiant_flux` (`incident`); ε is then not listed as assumed, as it is not
used. With an endpoint, `heat_outside_validity` still flags samples
above 205 °C: that limit belongs to the convective data of Eqs.
63.45–63.47, not to the flux law.

## What is not modelled

- **Radiant heat from outside the gas at the head.** The convective laws
  count convective heat only. The total-flux method adds the radiation of the
  gas around the head; flux from a hot upper layer, hot surfaces or a flame
  in view enters only through `--heat-radiant-source integrated-intensity`,
  with a user factor (see
  [Limits of the INTEGRATED INTENSITY source](#limits-of-the-integrated-intensity-source)).
  The layer-temperature input of spec 016 and gauge devices are not
  implemented
  ([#222](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/222),
  [#276](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/276)).
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
- **Web GUI.** The GUI does not offer `--heat-endpoint`,
  `--heat-fed-method`, `--heat-radiant-source` or `--heat-u-factor`
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
  The `INTEGRATED INTENSITY` source is checked against hand formulas, a
  committed FDS 6.10.1 case (`assets/heat_integrated_intensity`, slice *U*
  and *T* against FDS's own devices), and the #224 radiometer data, where
  *f* = 0.25 with convection matches the FDS skin gauge in an isotropic room
  in all four orientations within 3 %. The 300 °C layer, soot fraction and
  geometry of the committed case, and the gauge's h = 8 and \(T_s\) = 35 °C
  in the #224 decks, are assumptions of those test decks, not sourced values.

## Sources

- Purser, D. A., & McAllister, J. L. (2016). Assessment of hazards to
  occupants from smoke, toxic gases, and heat. In *SFPE Handbook of Fire
  Protection Engineering* (5th ed., Ch. 63). Springer.
  doi:10.1007/978-1-4939-2565-0_63
- McGrattan, K., et al. (2025). *Fire Dynamics Simulator User's Guide*,
  FDS 6.10.1. NIST Special Publication 1019. Table 22.4 (p. 403) and
  Eq. 22.35 (p. 381).
