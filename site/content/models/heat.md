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
`_heat_fed_rate_per_minute` (`pyfds_evac/core/fed.py`), ISO 13571:2012
Eq. (9) for fully clothed subjects (§8.3.1), unless `--heat-clothing
unclothed` selects ISO Eq. (10), `--heat-endpoint` selects another law
([Endpoint](#endpoint)) or `--heat-fed-method total-flux` selects the flux
law ([Total flux](#total-flux)):

$$
\dot{\mathrm{FED}}_{\mathrm{heat}} = T^{3.61} / (4.1 \times 10^{8}) \quad [1/\mathrm{min}],
$$

with *T* the gas temperature in °C at the agent's position, read from the
`TEMPERATURE` slice at `--smoke-slice-height` (1.6 m by default, as
FDS+Evac's `HUMAN_SMOKE_HEIGHT`). No heat flux enters the law, neither
incident nor net: it takes the gas temperature only. The dose is updated on the same interval as
the gas FED (`--smoke-update-interval`) and is a running total of its own,
never added to the gas FED.

If the case has no `TEMPERATURE` slice, the run continues without a heat dose
and logs a warning. In the FED history `heat_fed_cumulative` then reads 0 and
`temperature_celsius` 20.0 °C, and `metrics` has no `heat_fed_max` (see
[Outputs › FED history](/docs/outputs.md#fed-history)).

Outside the `TEMPERATURE` slice (outside the FDS domain) *T* reads 20 °C,
with no warning. FDS+Evac uses its ambient temperature `TMPA` there. The
default clothed law gives a small dose rate at 20 °C,
1.2 × 10⁻⁴ /min, so FED 1 would take about 137 h. The FED history marks
these rows with `in_fds_domain = False`; with `--require-fds-coverage` a
sample outside stops the run. Details on
[FDS slice sampling](/docs/fds-sampling.md#outside-the-fds-slices).

A heat-only case needs no soot. Without a `SOOT EXTINCTION COEFFICIENT`
slice the run logs two warnings and continues: there is no smoke-speed
model, so agents walk at clear-air speed and route costs see K = 0, and the
visibility model falls back to clear air
([#248](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/248)).
Neither enters the heat-dose rate; both can change where agents walk, and
so the temperature they are exposed to.

### Clothing

`--heat-clothing {clothed,unclothed}` (`opts.heat_clothing`, the
`clothing` argument of `DefaultHeatFedModel`) selects one of the two
convective laws of ISO 13571:2012 §8.3 (§8.3.1, §8.3.2), both for air with less than 10 %
water vapour by volume, with *t* in min and *T* in °C
(`HEAT_CLOTHING_LAWS`):

| `--heat-clothing` | ISO 13571:2012 | \(t_{I\,\mathrm{conv}}\) [min] | Source cited by ISO |
|---|---|---|---|
| `clothed` (default) | Eq. (9), fully clothed | \(4.1\times10^{8}\,T^{-3.61}\) | Crane (1978) |
| `unclothed` | Eq. (10), unclothed or lightly clothed | \(5\times10^{7}\,T^{-3.4}\) | Purser, SFPE Handbook; the constants of Eq. 63.44 |

The rate is \(1/t_{I\,\mathrm{conv}}\); a temperature at or below 0 °C,
or not finite, gives zero. ISO recommends Eq. (9) for fully clothed
subjects and states an uncertainty of ±25 % for both. Eq. (9) gives about
three times the time of Eq. (10): 24.7 against 7.9 min at 100 °C, 5.7
against 2.0 min at 150 °C, 2.0 against 0.75 min at 200 °C. Before
[#290](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/290) the
default was Eq. 63.44; `--heat-clothing unclothed` reproduces it exactly.
SFPE Ch. 63 treats the unclothed expressions as the relevant ones unless
protective clothing is worn (p. 2336); the default follows ISO instead
([Fundamentals › Heat](/fundamentals/heat.md#iso-135712012-clause-8)).
`--heat-clothing` has no effect with `--heat-endpoint` or
`--heat-fed-method total-flux`, and logs a warning there and without
`--enable-heat-fed`. The run manifest records `heat_clothing` whenever one
of the two laws is in use.

## Endpoint

`--heat-endpoint {tolerance,injury,fatal}` (default: none) replaces the ISO
law with the convective law of one endpoint of Ch. 63, so that heat FED = 1 means
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
warning and leaves the heat dose off. *r* enters the dose only
with `--heat-fed-method total-flux` ([Total flux](#total-flux)); with the
convective laws it is recorded only. The fatal *r* is
16.7 as printed on pp. 2382 and 2384; Purser's spreadsheet uses 16.667
(personal communication), and the code follows the Handbook. By maintainer decision,
heat FED = 1 is meant as the fatal endpoint; `--heat-endpoint fatal` gives
that meaning. Without the option the convective dose is the ISO law of
`--heat-clothing`.

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
total-flux form of [spec 016](https://github.com/PedestrianDynamics/pyFDS-Evac/blob/main/specs/016-heat-fed/SPEC.md). The heat flux to
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

- *D* is the radiant dose of `--heat-endpoint` (1.33, 10 or 16.7); without
  it, the fatal 16.7, as heat FED = 1 is meant as the fatal endpoint.
- **2.5 kW/m² threshold on the radiant term only.** The radiant term of
  *q* counts as zero in the dose where it is below 2.5 kW/m²
  (ISO 13571:2012 §8.2, §8.4; 2.5 itself counts), for every regime and
  source. The convective term \(h\,(T_g - T_s)\) counts at every level: with
  the threshold on the total *q*, clear air (ε = 0.05, h = 8) would give no
  dose below about 310 °C. ISO's 2.5 kW/m² is an incident flux; the code
  applies it to the net or excess radiant term (spec 016). `heat_flux_kw_m2`
  stays the physical *q*; the constant is `ISO_RADIANT_THRESHOLD_KW_M2`.
- **Not added to a convective law.** The rate is \(q^{1.33}/D\) alone.
- Where the *q* that enters the dose (convection plus the counted radiant
  term) is at or below zero, or the temperature is not finite, the rate is
  zero: no dose, and no recovery. The physical *q* can be negative while
  this *q* is positive: a layer cooler than the skin still leaves the
  convective dose of hot air at the head
  (`test_layer_regime_cool_layer_still_gives_convection` in
  `tests/test_heat_layer_flux.py`).

This is the "head in smoke" regime of spec 016 (`--heat-regime smoke`, the
default): ε applies to the gas at the head, and no external radiation is
added unless the radiant term comes from `INTEGRATED INTENSITY`
([Radiant flux from INTEGRATED INTENSITY](#radiant-flux-from-integrated-intensity)).
The "below a hot layer" regime is described in
[Hot layer](#hot-layer). ε, h and \(T_s\) have no sourced values; their
defaults are assumptions (`HEAT_FLUX_ASSUMED_PARAMETERS`):

| Parameter | Default | CLI flag | Source status |
|---|---|---|---|
| ε | `0.5` | `--heat-emissivity` | **Assumption.** p. 2384: 0.05 for a gas, "perhaps 0.5 for smoke" |
| h [W m⁻² K⁻¹] | `5.0` | `--heat-convective-coefficient` | **Assumption.** p. 2384: "approximately 5–8 for slow-moving air", no unit; 5 is the value of the spec 016 convection check |
| \(T_s\) [°C] | `35.0` | `--heat-skin-temperature` | **Assumption.** Not given for Eq. 63.49; 35 °C is the draft's value, held fixed |

Invalid values (ε outside [0, 1], h < 0, or non-finite) are rejected.
`--heat-fed-method` without `--enable-heat-fed` logs a warning and leaves
the heat dose off.

### Where the radiant threshold acts

With the defaults above, smoke at the head below about 285 °C gives no
radiant dose: its radiant term stays under 2.5 kW/m², and the dose is
convection alone. What follows from that:

- **Longer times than the convective default.** At 200 °C the time to
  heat FED = 1 is 21.6 min, against 6.7 min with the radiant term always
  counted and 2.0 min for ISO Eq. (9), the convective default. The
  endpoints differ (fatal *D* = 16.7 here, prevention of escape for
  Eq. (9)), but total flux at its defaults is not the more conservative
  choice: from 100 to 400 °C it gives the longer time throughout.
- **A step in the rate.** Where the radiant term reaches 2.5 kW/m² it
  enters the dose at once: near 285 °C the time to FED = 1 falls from
  12.4 to 2.9 min.
- **ε matters only above the threshold.** At \(T_s\) = 35 °C the radiant
  term reaches 2.5 kW/m² at about 207 °C for ε = 1 (or a black layer,
  \(\varphi\,\varepsilon_L\) = 1), 285 °C for ε = 0.5 (or \(\varphi\,\varepsilon_L\) = 0.5) and 698 °C for
  ε = 0.05. Below that temperature ε does not change the dose.

![Two panels. Left: the radiant term of the heat flux against source temperature for emissivity 1, 0.5 and 0.05, with the band below 2.5 kW/m² shaded as counted as zero; the curves reach 2.5 kW/m² at 207, 285 and 698 °C. Right, log scale: time to heat FED = 1 against gas temperature from 100 to 400 °C at the total-flux defaults. The solid curve with the threshold lies above the dashed curve without it until 285 °C, where it drops from 12.4 to 2.9 min onto the dashed curve; at 200 °C it gives 21.6 min against 6.7 min. A dotted grey curve, ISO Eq. (9), lies below both](/images/concepts/heat_radiant_threshold.png)

*(a) The radiant term of Eq. 63.49 at \(T_s\) = 35 °C; below 2.5 kW/m²
(shaded) it counts as zero. (b) Time to heat FED = 1 in a uniform room at
the total-flux defaults (ε 0.5, h 5, fatal D 16.7): solid with the
threshold, as the code runs; dashed with the radiant term always counted;
dotted, ISO Eq. (9), a different endpoint. Computed through
`DefaultHeatFedModel`. Script: `scripts/figures/heat_radiant_threshold.py`.*

{{< details title="Why the threshold sits on the radiant term, and on net flux" closed="true" >}}

- **Follow ISO.** ISO 13571:2012 sets the radiant contribution to zero
  where the radiant flux to the skin is below 2.5 kW/m² (§8.2, §8.4). The
  code follows it by maintainer decision. Before, total flux had no
  threshold; that followed Purser's spreadsheet and had no published source.
- **Radiant term only.** ISO applies the limit to the radiant term, not to
  convection. With the threshold on the total *q*, clear air (ε = 0.05,
  h = 8) would give no dose below about 310 °C, where the hot-air data give
  minutes. Convection therefore counts at every level.
- **Net or excess flux, not incident.** ISO calls 2.5 kW/m² an incident
  flux level. The code compares it with the radiant term as it has it: a
  net σT⁴ difference for the gas and layer terms, the excess
  *f* (*U* − 4σ\(T_s^4\)) for `INTEGRATED INTENSITY`. At the Handbook's
  200 °C / 2.5 kW/m² anchor (black layer, φ = 1) the net term is
  2.33 kW/m², about 18 % below the incident 2.84 kW/m², so that anchor
  adds no radiant dose. The threshold is therefore reached at a hotter
  source than on incident flux. This is recorded in spec 016, not
  corrected, and listed in [Assumptions](#assumptions-unsourced-values).
- **A fixed constant.** 2.5 kW/m² is `ISO_RADIANT_THRESHOLD_KW_M2`
  (`fed.py`), applied by `counted_radiant_flux_kw_m2`, with no flag.

{{< /details >}}

### Hot layer

`--heat-regime layer` (opt-in, with `--heat-fed-method total-flux`) takes
the head to be in clear air below a hot upper layer (spec 016, "Regimes";
[#222](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/222)).
The Handbook says only that a subject "in air (with a low emissivity), below
a hot smoke layer" receives radiation from the layer (p. 2384), and that
2.5 kW/m² corresponds approximately to a hot layer at 200 °C (p. 2382). The
flux to the skin is convection from the gas at the head plus the radiant
term of Eq. 63.49 with the layer as source and a view factor,
`layer_radiant_flux_kw_m2`:

$$
q = \frac{h\,(T_g - T_s)}{1000} + q_{\mathrm{ext}}, \qquad
q_{\mathrm{ext}} = \frac{\varphi\,\varepsilon_L\,\sigma\,(T_L^4 - T_s^4)}{1000}
\quad [\mathrm{kW/m^2}],
$$

with \(T_L\) the temperature of a second `TEMPERATURE` slice at
`--heat-layer-height`, sampled at the agent's x, y. The rate is
\(q^{1.33}/D\) as above.

- **No radiant term of the gas at the head.** In this regime the εσ term of
  the gas at the head is dropped, so `--heat-emissivity` has no effect. The
  layer term is never added on top of the in-smoke radiant term: with
  \(T_g = T_L\), ε = 0.5 and φ = ε_L = 1 that sum would be
  1.5 σΔT⁴, against σΔT⁴ here.
- **Net flux.** \(q_{\mathrm{ext}}\) is a net flux (a σT⁴ difference),
  not the incident flux of the radiant tolerance data. At the 200 °C anchor
  (black layer, φ = 1, \(T_s\) = 35 °C) it is 2.33 kW/m² net against
  2.84 kW/m² incident, both within 15 % of the Handbook's 2.5 kW/m².
  2.33 is below the 2.5 kW/m² radiant threshold, so a layer at the anchor
  adds no radiant dose; a black layer with φ = 1 counts from about
  207 °C ([Where the radiant threshold acts](#where-the-radiant-threshold-acts)).
- **The regime is a user choice** for the whole run. No source gives a rule
  to decide it per agent
  ([#275](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/275)).
- A layer cooler than the skin gives a negative \(q_{\mathrm{ext}}\),
  which is below 2.5 kW/m² and counts as zero in the dose; it appears only
  in `heat_flux_kw_m2`. A non-finite layer
  temperature gives no dose. Where the layer slice has no value, the layer
  temperature falls back to 20 °C, as the temperature at the head does.
  This fallback is an unsourced assumption. Below the skin temperature it
  makes \(q_{\mathrm{ext}}\) slightly negative (cooling), about
  −0.09 φ ε_L kW/m² at \(T_s\) = 35 °C; that counts as zero in the dose,
  so the fallback changes only `heat_flux_kw_m2`, not the dose.

φ, \(\varepsilon_L\) and the layer height have no sourced values and no
defaults; the layer regime without any of them is rejected, as are a
non-finite layer height and `--heat-regime layer` with
`--heat-fed-method convective`:

| Parameter | Default | CLI flag | Source status |
|---|---|---|---|
| regime | `smoke` | `--heat-regime` | User choice; no sourced rule |
| layer height [m] | none (required) | `--heat-layer-height` | Depends on the ceiling height |
| φ | none (required) | `--heat-view-factor` | Unsourced; spec 016 gives about 1 for the crown, about 0.5 for the face |
| \(\varepsilon_L\) | none (required) | `--heat-layer-emissivity` | Unsourced; p. 2384 gives 1 for a black body, "perhaps 0.5" for smoke |

φ and \(\varepsilon_L\) outside [0, 1] or non-finite are rejected.
`--heat-regime` without `--enable-heat-fed` logs a warning and leaves the
heat dose off.

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
q = f\,\Bigl(U - \frac{4\,\sigma\,T_s^4}{1000}\Bigr) + \frac{h\,(T_g - T_s)}{1000}
\quad [\mathrm{kW/m^2}],
$$

with \(T_s\) in K (`radiant_flux_from_integrated_intensity_kw_m2` for the
incident *f U*), and the rate is \(q^{1.33}/D\) as above.

- **The radiant term is the excess over a skin-temperature field**,
  *f* (*U* − 4σ\(T_s^4\)), by maintainer decision
  ([#221](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/221)),
  with the same \(T_s\) as the convective term. 4σ\(T_s^4\) is the *U* of an
  isotropic black field at the skin temperature, so that field gives
  *q* = 0 for every *f* in [0.25, 1]: surroundings at skin temperature
  exchange no net heat with the skin, whatever the orientation factor. An
  isotropic field at *T* gives 4*f*σ(*T*⁴ − \(T_s^4\)); at *f* = 1/4 that is
  σ(*T*⁴ − \(T_s^4\)), the radiant term of Eq. 63.49 with ε = 1, and what an
  FDS skin gauge reports in that field (FDS User's Guide 6.10.1, Eq. 22.35,
  p. 381). A source seen face-on in surroundings at skin temperature
  (*f* = 1, *U* = *q*\(_{\mathrm{src}}\) + 4σ\(T_s^4\)) gives its own flux
  *q*\(_{\mathrm{src}}\). The Handbook calls Eq. 63.49 "the total incident
  flux to the skin" (p. 2383), and spec 016 takes the radiant tolerance data
  as incident, so this basis is a choice, not a reading of the sources.
- **No negative dose.** Where the *q* that enters the dose (convection plus
  the counted radiant term) is at or below zero, the rate is 0; there is no
  recovery. An excess below zero (*U* < 4σ\(T_s^4\)) counts as zero, so hot
  air at the head still gives its convective dose while `heat_flux_kw_m2`
  is negative. A 20 °C room with no fire (*U* = 1.68 kW/m² <
  4σ\(T_s^4\) = 2.04 kW/m², air below \(T_s\)) gives no dose for any *f*.
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
- Both slices are read at one height. The `INTEGRATED INTENSITY` slice
  nearest the slice height must lie at the z of the `TEMPERATURE` slice;
  otherwise the run stops with an error, even when both lie within the
  0.5 m that only warns for other slices.
- Both slices must cover every agent. A point inside one slice and outside
  the other stops the run with an error; a missing *U* is not read as zero.
  Outside both (outside the FDS domain) *U* and *q* are NaN in the FED
  history and the rate is zero; the run logs one warning the first time
  this happens, not one per agent or update, and marks each such row with
  `in_fds_domain = False`.
- A non-finite *U* gives a zero rate, as for the gas term.
- **With `--heat-regime layer` as well, *U* supplies the radiant term** and
  the layer term is not added; the run logs one warning and the manifest
  records `layer_term: false`. Reasoning: FDS's radiation solution already
  contains the layer's emission, so the sum would count it twice; of the
  two, *U* is the better-resolved input, since it integrates the whole
  radiation field at the head (layer, flame, walls, the gas around the
  head), while the layer term takes one slice temperature, a user view
  factor and a user emissivity. The layer term is used only when *U* is not
  the radiant source. There is no per-sample fallback from *U* to the layer
  term: inside the domain both slices must cover every agent, so *U* is
  always there, and outside it (the only place *U* is missing) the layer
  slice has no value either.

### Limits of the INTEGRATED INTENSITY source

- **Ambient background.** *U* is not zero in a cold room (1.68 kW/m² at
  20 °C), but the excess basis subtracts the field at skin temperature, so
  surroundings at or below \(T_s\) give no dose for any *f*. Surroundings
  warmer than the skin but with no fire (a warm day, a heated room) give a
  radiant dose only where \(f\,(U - 4\sigma T_s^4)\) reaches 2.5 kW/m²;
  below that only convection counts.
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

- **One threshold for gas and heat.** The heat threshold is `fed_threshold`
  (`--fed-threshold`, 1.0 by default), as ISO 13571:2012 asks for one
  threshold for both FED and FEC in an estimation (§5.4) and finds the time
  for heat in the same manner (§8.5). `--heat-fed-threshold`
  (`TenabilityConfig.heat_fed_threshold`, default none) sets a separate
  heat threshold; that departs from ISO, so the run logs a warning and the
  manifest records `heat_fed_threshold_override`.
- **`deterministic` (default).** Every agent uses the heat threshold. No
  published source gives a population spread for heat tolerance:
  SFPE Ch. 63 gives population figures for heat only for radiant lethality
  (p. 2382). Read as a log-normal, those figures give σ ≈ 0.22; the gas
  value σ = 0.94 would put 29 % of agents below FED 0.60, where they imply
  1 % ([Incapacitation thresholds](/fundamentals/incapacitation-thresholds.md#heat)).
  That is why heat stays deterministic by default
  ([#225](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/225)).
- **`probabilistic` (opt-in).** Each agent draws its own threshold once, from
  a stream seeded by the run's seed and its spawn order, independent of the
  gas threshold:
  \(D_i = D \cdot \exp(\sigma Z)\), with *D* the heat threshold,
  \(Z \sim N(0, 1)\). The default σ = 0.94 is borrowed from the gas dose, an
  assumption with no data basis for heat. The Handbook's radiant lethality
  figures point to a much narrower spread, for an endpoint not modelled here
  ([Incapacitation thresholds](/fundamentals/incapacitation-thresholds.md#heat),
  [#225](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/225)).

The gas dose is also deterministic by default; the two modes are set separately
(`--incapacitation-mode` and `--heat-incapacitation-mode`).

The two doses use one threshold but do not share an endpoint. Gas FED = 1 is
Purser's incapacitation endpoint. Without `--heat-endpoint`, heat FED = 1
is the time of ISO Eq. (9) or (10), which ISO introduces as the time to
prevention of escape and also calls the time to experiencing pain (§8.3,
§8.3.1; see [What is not modelled](#what-is-not-modelled)). Both stop the agent in
the same way and set the same `incapacitated` flag; only
`incapacitation_cause` tells which endpoint was reached.

| Field | Default | CLI flag |
|---|---|---|
| `enable_heat_fed` | `False` | `--enable-heat-fed` |
| `heat_fed_threshold` | none, `fed_threshold` | `--heat-fed-threshold` |
| `heat_incapacitation_mode` | `"deterministic"` | `--heat-incapacitation-mode` |
| `heat_susceptibility_sigma` | `0.94` | `--heat-susceptibility-sigma` |
| `heat_clothing` | `"clothed"` | `--heat-clothing` |
| `heat_endpoint` | `None` (ISO law of `heat_clothing`) | `--heat-endpoint` |
| `heat_fed_method` | `"convective"` | `--heat-fed-method` |
| `heat_radiant_source` | `"gas"` | `--heat-radiant-source` |
| `heat_u_factor` | none, required with `integrated-intensity` | `--heat-u-factor` |
| `heat_regime` | `"smoke"` | `--heat-regime` |

The 2.5 kW/m² radiant threshold of [Total flux](#total-flux) is not a heat
threshold in this sense: it decides which radiant flux enters the dose, is
a fixed constant and has no flag.

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
`heat_flux_parameters` (ε, h, \(T_s\), *D*, `radiant_threshold_kw_m2`,
and the names of the assumed parameters). With `--heat-regime layer`, `heat_flux_kw_m2` includes
\(q_{\mathrm{ext}}\), the FED history also carries
`heat_layer_temperature_c` (\(T_L\)), and `heat_flux_parameters` also
records `regime`, `view_factor`, `layer_emissivity` and `layer_height_m`;
it still records ε, which has no effect in that regime. With
`--heat-radiant-source integrated-intensity` the FED history also carries
`heat_integrated_intensity_kw_m2` (*U*), and `heat_flux_parameters` adds
`radiant_source`, `u_factor` and `radiant_flux` (`excess`); ε is then not
listed as assumed, as it is not used.
`heat_flux_kw_m2` is the physical *q*, before the radiant threshold. Where
the radiant term is below 2.5 kW/m², `heat_fed_rate_per_min` is therefore
not `heat_flux_kw_m2`^1.33/*D*: it is the convective part alone raised to
1.33, divided by *D* (zero where the head is at or below the skin
temperature).
With an endpoint, `heat_outside_validity` still flags samples
above 205 °C: that limit belongs to the convective data of Eqs.
63.45–63.47, not to the flux law.

The manifest records `heat_clothing` (`clothed` or `unclothed`) when the
ISO law is in use, that is without `--heat-endpoint` and with
`--heat-fed-method convective`, and `heat_fed_threshold_override` when
`--heat-fed-threshold` was set.

The `incapacitated` column is true whichever dose stopped the agent, so it
mixes the gas and heat endpoints; filter on `incapacitation_cause` to count
them apart. `gas+heat` means both doses crossed their thresholds on the same
update; a crossing by the other dose after the agent has stopped is not
recorded.

## What is not modelled

The values the heat dose and its tests rest on without a source are listed
in [Assumptions (unsourced values)](#assumptions-unsourced-values).

- **Radiant heat from hot surfaces or a flame in view.** The convective laws
  count convective heat only. The total-flux method adds the radiation of the
  gas around the head, or with `--heat-regime layer` that of a hot upper
  layer. Flux from hot surfaces or a flame in view enters only through
  `--heat-radiant-source integrated-intensity`, with a user factor (see
  [Limits of the INTEGRATED INTENSITY source](#limits-of-the-integrated-intensity-source)).
  Gauge devices are not read
  ([#221](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/221),
  [#276](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/276)).
  FDS reference data for that term exist but are not read by the model:
  [Heat radiometer reference decks](/verification/testing-heat-radiometer.md)
  ([#224](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/224)).
- **Layer temperature and emissivity.** The layer temperature is read from
  one slice at one height: it reads ceiling-jet temperatures near the
  ceiling and assumes one ceiling height for the whole domain. There is no
  layer reduction from several heights, and \(\varepsilon_L\) is a constant,
  not taken from FDS's `ABSORPTION COEFFICIENT`
  ([#274](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/274)).
- **Regime selection.** The regime is one user choice for the whole run.
  In the smoke regime the default ε = 0.5 treats every head as in smoke.
  Above about 285 °C that overestimates the dose in clear hot air; set
  `--heat-emissivity 0.05` for clear air. Below about 285 °C the radiant
  term is under the 2.5 kW/m² threshold for either value, and ε does not
  change the dose. In the layer regime an agent that walks into the smoke
  still gets the layer formula. How to decide the regime per agent is open
  (spec 016, open question 4;
  [#275](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/275)).
- **Total-flux parameters.** h, \(T_s\) and ε are assumptions (see
  [Total flux](#total-flux)); \(T_s\) is fixed and does not rise with
  exposure (spec 016, open questions 1 and 2).
- **The default endpoint.** Without `--heat-endpoint`, heat FED = 1 is the
  time of ISO Eq. (9), or of Eq. (10) with `--heat-clothing unclothed`. ISO
  introduces both as the time to prevention of escape and also calls it the
  time to experiencing pain (§8.3, §8.3.1). Ch. 63 labels Eq. 63.44
  (= Eq. (10)) a time to incapacitation, but its times lie near the
  Handbook's tolerance curve (Eq. 63.45) rather than its injury or fatal
  ones ([#220](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/220)).
- **Population spread.** No consulted source gives a spread of tolerance
  for the convective dose; the opt-in σ = 0.94 is borrowed from the gas dose
  ([#225](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/225)).
- **Validity range.** Humidity is not sampled, so humid smoke is never
  flagged; `heat_humidity` reads `unknown`
  ([#272](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/272)). Without `--heat-endpoint`, temperatures above 205 °C are not
  flagged either, although Eq. 63.44 rests on the same data (p. 2382); ISO
  states no temperature range for Eqs. (9) and (10).
- **Web GUI.** The GUI offers `--heat-clothing` (a dropdown) and
  `--heat-fed-threshold` in its FED group. The other heat options are fields
  of its collapsed "Other" section, not next to them
  ([Web GUI](/docs/web-gui.md);
  [#270](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/270),
  [#311](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/311)).
- **Falling exposure and recovery.** The summed dose assumes exposure that is
  steady or rising (Eq. 63.48; ISO 13571:2012 §8.4 states it for the
  temperature experienced by the occupant); a fleeing agent's exposure falls, and no
  recovery is modelled.
- **Clothing beyond the two ISO laws.** `--heat-clothing` switches between
  fully clothed and unclothed for the whole run; there is no per-agent
  clothing, no face covering, and no clothing term in the endpoint laws, the
  total-flux method or the radiant terms.
- **Effects on walking speed or route choice.** The heat dose only
  incapacitates ([#81](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/81)).

## Verification

The heat laws are checked against hand formulas and the tables of SFPE
Handbook Ch. 63 (equation level), in coupled corridor runs on synthetic
fields, and on FDS cases at 100, 150 and 200 °C. The default ISO Eq. (9) has
expected times only on the FDS cases
([#307](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/307)), and the
layer regime has no FDS case yet
([#308](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/308)). The
checks, their numbers and the test assumptions are on
[Verification › Heat dose](/verification/testing-heat.md#checks-against-the-handbook)
and [Heat radiometer](/verification/testing-heat-radiometer.md).

## Relation to ISO 13571:2012

ISO 13571:2012 clause 8 ([Fundamentals](/fundamentals/heat.md#iso-135712012-clause-8))
has both convective laws and the 2.5 kW/m² radiant threshold in common with
the code, and none of its other options:

| Option | ISO 13571:2012 counterpart |
|---|---|
| Default, `--heat-clothing clothed` | Eq. (9), §8.3.1: fully clothed, uncertainty ±25 % (§8.3.2) |
| `--heat-clothing unclothed` (Eq. 63.44) | Eq. (10), §8.3.2: same constants, for unclothed or lightly clothed subjects, uncertainty ±25 % |
| `--heat-endpoint tolerance`, `injury`, `fatal` (Eqs. 63.45–63.47) | None |
| `--heat-fed-method total-flux` (Eqs. 63.49 and 63.43, dose *D*) | None: ISO has no total-flux form, no ε, h or \(T_s\), and no radiant dose |
| Radiant law, any regime or source | None: ISO's radiant laws are Eqs. (7) (burns) and (8) (pain), \(a\,q^{-b}\) with other exponents and *q* defined only as the radiant heat flux; the code does not use them |
| Radiant term counted as zero below 2.5 kW/m² | Adopted from §8.2, §8.4, where 2.5 kW/m² is an incident flux level; the code compares it with the net or excess radiant term, not the incident flux (spec 016) |
| Heat FED kept apart from the gas FED | Consistent: ISO treats heat as a component of its own (§4.1, §4.6 a) |
| Heat threshold = `fed_threshold` (default) | Our reading of §5.4 (one threshold for FED and FEC in an estimation) with §8.5 (heat time found in the same manner); ISO does not name the heat FED in §5.4 |
| `--heat-fed-threshold`, separate from the gas threshold | A departure from §5.4; logged and recorded in the manifest |
| Heat σ | None: ISO gives no population spread for heat |

ISO gives no upper temperature for Eqs. (9) and (10), so the 205 °C limit
of the endpoint laws stays an assumption; its humidity condition, less than
10 % water vapour by volume (§8.3), is the one the code already records.

## Assumptions (unsourced values)

Values in the heat code that no consulted source fixes. Each can change a
result; none is a Handbook tolerance.

| Parameter | Value | CLI flag / config key | Where used | Why this value | What would source it |
|---|---|---|---|---|---|
| Convective coefficient h | 5 W/(m²·K) | `--heat-convective-coefficient` / `convective_coefficient` (`DEFAULT_HEAT_CONVECTIVE_COEFFICIENT`) | Total-flux *q*, every regime and radiant source | Low end of "approximately 5–8 for slow-moving air" (p. 2384, printed without a unit); the value of the spec 016 convection check | h measured for a walking, clothed person in hot air or smoke |
| Skin temperature \(T_s\) | 35 °C, fixed | `--heat-skin-temperature` / `skin_temperature_celsius` (`DEFAULT_HEAT_SKIN_TEMPERATURE_C`) | Total-flux convective and radiant terms, and 4σ\(T_s^4\) of the excess `INTEGRATED INTENSITY` term | The draft's value; the Handbook gives none for Eq. 63.49 | Skin temperature data under heat exposure, including its rise (spec 016, open question 2) |
| Gas emissivity ε | 0.5 | `--heat-emissivity` / `emissivity` (`DEFAULT_HEAT_EMISSIVITY`) | Total-flux gas term at the head (`--heat-regime smoke`, `--heat-radiant-source gas`) | "perhaps 0.5 for smoke" (p. 2384); treats every head as in smoke. Below about 285 °C it does not change the dose (radiant threshold) | ε per agent from FDS absorption and path length ([#274](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/274), [#275](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/275)) |
| Temperature fallback | 20 °C | none (`HeatFedInputs.temperature_celsius`) | Temperature at the head outside the `TEMPERATURE` slice; layer temperature where the layer slice has no value ([#222](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/222)) | A room ambient; below \(T_s\) it gives a small negative layer flux, which counts as zero in the dose and shows only in `heat_flux_kw_m2` | The case's ambient `TMPA` |
| Convective validity limit | 205 °C | none (`HEAT_CONVECTIVE_VALIDITY_MAX_C`) | `heat_outside_validity` flag with `--heat-endpoint` (Eqs. 63.45–63.47, [#220](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/220)); does not clip the rate | Highest dry-air tolerance point of Table 63.17 (Veghte, 4 min, p. 2375); the Handbook gives no upper temperature | The temperature range of the data Purser fitted Eqs. 63.45–63.47 to |
| Radiant threshold basis | 2.5 kW/m² on the net or excess radiant term | none (`ISO_RADIANT_THRESHOLD_KW_M2`, fixed) | Total-flux radiant term, every regime and source | ISO 13571:2012 §8.2, §8.4 give 2.5 kW/m² as an incident flux level; the code compares it with the radiant term it computes, about 18 % below incident at the 200 °C anchor (2.33 against 2.84 kW/m², spec 016) | Whether the threshold, and the radiant tolerance data, hold for incident flux or for net flux at the skin |
| U factor *f* | in [0.25, 1], no default | `--heat-u-factor` / `u_factor` (`HEAT_U_FACTOR_RANGE`) | `--heat-radiant-source integrated-intensity` ([#221](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/221)) | Geometric bounds: *U*/4 for a sphere or an isotropic field, *U* for one small source face-on; the #224 data put some orientations below 0.25 | Gauge devices per orientation ([#276](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/276)) |
| Flux basis of *f U* | excess over a skin-temperature isotropic field, *f* (*U* − 4σ\(T_s^4\)) | none (fixed) | `--heat-radiant-source integrated-intensity` | Maintainer decision: surroundings at skin temperature give no flux for any *f*; at *f* = 1/4 equals Eq. 63.49 with ε = 1 and the FDS skin gauge (FDS User's Guide 6.10.1, Eq. 22.35). The Handbook calls Eq. 63.49 incident (p. 2383) | Whether the radiant tolerance data (Table 63.19) hold for incident flux or for flux above the skin's own exchange |
| *U* with the layer regime | *U* supplies the radiant term; layer term not added | `--heat-regime layer` with `--heat-radiant-source integrated-intensity` | Total-flux *q* when both are set | *U* already contains the layer's emission and is the better-resolved input | Gauge devices, which replace both ([#276](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/276)) |
| Heat σ | 0.94 | `--heat-susceptibility-sigma` / `heat_susceptibility_sigma` | Probabilistic heat mode only (`--heat-incapacitation-mode probabilistic`) | Borrowed from the gas dose ([#225](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/225)); the radiant lethality figures imply about 0.22 | A population spread for the convective dose, e.g. the probits of Hockey & Rew (1996), not read |
| Clothing | fully clothed, every agent | `--heat-clothing` / `heat_clothing` (`DEFAULT_HEAT_CLOTHING`) | Convective law without `--heat-endpoint` or total flux ([#290](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/290)) | Maintainer decision following ISO 13571:2012, which recommends Eq. (9) for fully clothed subjects (§8.3.1); SFPE Ch. 63 treats the unclothed law as the relevant one unless protective clothing is worn (p. 2336) | Clothing data per occupancy or per agent |
| One threshold for gas and heat | heat threshold = `fed_threshold` | `--heat-fed-threshold` / `heat_fed_threshold` overrides it | Heat incapacitation | Maintainer reading of ISO 13571:2012 §5.4 with §8.5; the standard does not say whether the heat FED shares the gas threshold ([Incapacitation thresholds](/fundamentals/incapacitation-thresholds.md#heat)) | A statement of the standard, or data on heat and gas thresholds in the same people |

The assumptions of the test decks and test bands (the #224 and #221 decks,
the skin gauge, the table reading, the test bands and the flame pass) are on
[Verification › Heat dose](/verification/testing-heat.md#test-and-reference-deck-assumptions);
they do not affect a run.

## Sources

- Purser, D. A., & McAllister, J. L. (2016). Assessment of hazards to
  occupants from smoke, toxic gases, and heat. In *SFPE Handbook of Fire
  Protection Engineering* (5th ed., Ch. 63). Springer.
  doi:10.1007/978-1-4939-2565-0_63
- McGrattan, K., et al. (2025). *Fire Dynamics Simulator User's Guide*,
  FDS 6.10.1. NIST Special Publication 1019. Table 22.4 (p. 403) and
  Eq. 22.35 (p. 381).
