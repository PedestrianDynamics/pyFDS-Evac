# 016 — Heat dose: total heat flux to the skin

Status: design, not implemented. The implemented heat dose is described on
Models › Heat (`site/content/models/heat.md`).

## Problem

The heat dose in use today is the convective law of SFPE Handbook 5th ed.
Eq. 63.44, \(\dot{\mathrm{FED}} = T^{3.4}/5\times10^{7}\) per minute, sampled
from one `TEMPERATURE` slice at head height. It has four gaps:

1. **No radiant heat.** Flux from a hot upper layer, hot surfaces or a flame
   in view is not counted.
2. **Unclear endpoint.** Eq. 63.44 is labelled a time to incapacitation, but
   its times lie near the tolerance curve (7.9 min at 100 °C, against
   12.3 min for Eq. 63.45, tolerance, and 35.6 min for Eq. 63.46, injury).
3. **Self-referential tests.** The heat tests compute their expected value
   with the same closed form as the code.
4. **No sourced population spread.** Heat is deterministic by default; the
   opt-in σ = 0.94 is borrowed from the gas dose.

## Decisions (maintainer)

- **Heat FED = 1 means the fatal endpoint.** In the dose form below this is
  D = 16.7 (third-degree burns), as printed in the SFPE Handbook 5th ed.,
  Ch. 63 (Purser & McAllister 2016), p. 2382 (range of r) and p. 2384
  (D values for Eq. 63.49). Purser's spreadsheet uses 16.667 (personal
  communication); the code follows the Handbook.
- **Heat incapacitation is deterministic by default**, σ opt-in (done; see
  Models › Heat).
- **The method is the total-flux form** (Eq. 63.49 with the Eq. 63.43 dose),
  as recommended by D. Purser (personal communication, 2026), not the
  two-dose draft method (see "Rejected alternatives").
- **The `INTEGRATED INTENSITY` radiant term is the excess over an
  isotropic field at the skin temperature**, f (U − 4σT_s⁴), with the same
  T_s as the convective term (#221). A field at T_s gives zero for every f;
  a field at T gives 4fσ(T⁴ − T_s⁴), σ(T⁴ − T_s⁴) at f = 1/4. q ≤ 0 is net
  cooling and gives a zero dose rate.
- **`INTEGRATED INTENSITY` wins over the layer term** when both are set: U
  already contains the layer's emission and is the better-resolved input;
  the layer term is not added, and the run warns once (#221, #222).

## Sources

- Purser, D. A., & McAllister, J. L. (2016). SFPE Handbook 5th ed., Ch. 63,
  doi:10.1007/978-1-4939-2565-0_63. Eqs. 63.43–63.49, Tables 63.17–63.21,
  pp. 2375–2385.
- The draft `FED Heat v3.docx` (pyFDS-Evac-paper), which cites the 6th ed.,
  Ch. 70 (doi:10.1007/978-3-031-59212-6_70). The 6th ed. is not in the
  library. Its numbers appear to be the 5th ed.'s minus 2
  (70.41 ↔ 63.43, … 70.47 ↔ 63.49); unverified.
- D. Purser, personal communication (2026): review of the draft.
- FDS User's Guide 6.10.1: §§14.2, 15.4, 18.1, 22.10.12, 22.10.18, Table 22.4.

## Method

For each agent and update, the heat flux to the skin (kW/m²) is

$$
q_{\mathrm{tot}} = \frac{\varepsilon\,\sigma\,(T_g^4 - T_s^4) + h\,(T_g - T_s)}{1000} + q_{\mathrm{ext}},
$$

with temperatures in K, σ = 5.67 × 10⁻⁸ W m⁻² K⁻⁴, and \(q_{\mathrm{ext}}\) the
radiation from sources outside the gas around the head (hot layer above,
flames, hot surfaces). The time to the endpoint (min) and the dose are

$$
t = D / q_{\mathrm{tot}}^{1.33}, \qquad \mathrm{FED} = \sum \Delta t / t .
$$

D = 1.33 (pain), 10 (second-degree burns), 16.7
(third-degree burns, fatal), SFPE Ch. 63 pp. 2382 and 2384.

Differences from the draft:

| Item | Draft | This spec |
|---|---|---|
| Units | `/1000` on the convective term only (as printed in Eq. 63.49) | both terms in W/m², divided together |
| ε (gas at the head) | 0.5 smoke, 0.05 clear air | from the regime (below) |
| h | 5–8 | parameter, default open (5–8) |
| T_skin | 35 °C | parameter, default open (fixed or rising) |
| 2.5 kW/m² threshold | yes | **no** |
| D, second degree | 10 | open |

**No threshold.** With the 2.5 kW/m² threshold, the total-flux form gives no
dose in clear air below about 310 °C (h = 8, ε = 0.05), where the hot-air data
give minutes. Accumulating dose at all fluxes closes that gap.

**Convection check.** Converting hot-air temperatures to convective flux
should reproduce the hot-air tolerance data. Convection alone (h = 5,
T_s = 36 °C, D = 1.33), minutes to pain:

| T (°C) | h(T − T_s) only | Eq. 63.44 | Eq. 63.45 |
|---|---|---|---|
| 100 | 6.0 | 7.9 | 12.3 |
| 120 | 4.2 | 4.3 | 6.2 |
| 140 | 3.2 | 2.5 | 3.5 |
| 180 | 2.1 | 1.1 | 1.35 |

Agreement is close from 100 to 140 °C; the flux form is flatter above about
160 °C. Adding ε = 0.5–0.9 radiation to the same air temperature shortens the
times by a factor of 2–4, which suggests the hot-air exposures were mostly
convective. The ε term must therefore apply only where the head is in
radiating smoke.

### Regimes

- **Head in smoke.** \(T_g\) is the local temperature at head height, ε for
  sooty smoke; \(q_{\mathrm{ext}} = 0\) unless a flame is in view.
- **Head in clear air below a hot layer.** Convection from the local
  temperature; radiation from the layer: \(q_{\mathrm{ext}} = \varphi\,
  \varepsilon_L\,\sigma (T_L^4 - T_s^4)/1000\). φ ≈ 1 for the crown, ≈ 0.5 for
  the face (at 90° to the layer). ε_L high for a sooty layer.

Do not add both radiant terms at once. The draft's "extension" does, and with
T_i = T_L, ε_s = 0.5, φ = ε_L = 1 its radiant part is σΔT⁴, twice the
ε = 0.5 term; it does not reduce to Eq. 63.49 as claimed.

How to decide the regime (soot density, temperature, a layer-height
reduction) is open.

## Radiant flux from FDS

Why the flux to the skin is not simply U: `INTEGRATED
INTENSITY` U = ∫ I dΩ is the radiation arriving from all directions, not the
flux onto a surface. A surface sees one hemisphere, with rays weighted by
cos θ, so q ≤ U:

- q ≈ U for one small source seen face-on (a flame in view);
- q = U/2 under a uniformly glowing layer with nothing below (plate facing up);
- q = U/4 for a sphere, whatever the angular distribution; also a plate
  immersed in uniformly glowing smoke.

No single factor holds. Input options, in order of preference:

1. **Gauge devices on a head-height grid.** `GAUGE HEAT FLUX GAS` with
   `&PROP GAUGE_TEMPERATURE=35, HEAT_TRANSFER_COEFFICIENT=<h>` computes
   \(q_{\mathrm{tot}}\) with the full radiation solution (FDS UG Eq. 22.35). On
   a `POINTS` array at head height, facing up (crown) and sideways (face),
   it acts as a flux slice that can be sampled along paths. The face could
   use the agent's walking direction. `RADIATIVE HEAT FLUX GAS` is net flux,
   not a gauge.
2. **`INTEGRATED INTENSITY` slice** with a user-chosen factor in [0.25, 1],
   no default until the validation deck has run.
3. **Layer temperature** from a second `TEMPERATURE` slice near the ceiling,
   with φ and ε_L. Reads ceiling-jet temperatures; assumes one ceiling height.

Net vs incident flux: the radiant tolerance data are incident flux; σT⁴
differences and `RADIATIVE HEAT FLUX GAS` are net (≈ 20 % lower at the
200 °C anchor). Each input must say which it gives. The `INTEGRATED
INTENSITY` input is the excess over a skin-temperature field by decision
(see "Decisions").

## Validity and limits

- Summed doses (Eq. 63.48) hold only while exposure is steady or rising; a
  fleeing agent's exposure falls. No recovery.
- Convective data reach about 205 °C, below 10 % water vapour. Flag samples
  outside.
- Clothing and face covering protect against heat. Document; no parameter
  without data.
- The gas dose's FED = 1 is incapacitation; heat FED = 1 is fatal. Outputs
  and the `incapacitation_cause` column must not mix the two silently.

## Verification (spec 015 levels)

- **L1.** Table 63.21 as the oracle for Eq. 63.45 (its caption says
  Eq. 63.44; the numbers are Eq. 63.45). Table 63.20 convective and radiant
  rows, with stated bands. The 200 °C ≈ 2.5 kW/m² anchor. q = πI, U = 4πI for
  an isotropic field.
- **L2.** Walking past a flame: 1 m/s past a small flame at 1000 °C, closest
  approach 0.5 m, 1 s steps, flux from a view-factor calculation; expected
  values computed independently of the code. Constant T and q with a
  closed-form crossing time. A falling-exposure path.
- **L3.** An adiabatic room with a hot layer set by `&INIT`, radiometer and
  gauge devices at 1.6 and 1.8 m facing up and sideways, an `INTEGRATED
  INTENSITY` slice, and a burner case. Case files in sciebo
  `fds-evac-data/heat_radiometer/`.

## Open questions

1. h: 5 or 8?
2. T_skin: fixed 35 °C, or rising with exposure?
3. D for second-degree burns (only if that endpoint is offered)?
4. How to decide the regime (head in smoke vs below a layer)?
5. Do the 6th-ed. Ch. 70 equations match the 5th ed.? (Needs Ch. 70.)
6. ~~Does ISO 13571:2012 clause 8 give heat equations, and does FED 0.3
   apply to heat?~~ Answered from the full text. Clause 8 gives radiant
   Eqs. (7) (burns) and (8) (pain), a q^-b form from Wieczorek & Dembsey
   2001, applied to incident flux and zero below 2.5 kW/m²; convective
   Eqs. (9) (clothed, Crane 1978) and (10) (unclothed, = Eq. 63.44); and the
   summed FED of Eq. (11) (= Eq. 63.48). It has no total-flux method, so it
   supplies no h, T_skin, ε or D, and gives no support for dropping the
   2.5 kW/m² threshold. §8.5 applies the gas threshold logic to heat by
   reference, but the 0.3 / 11.4 % figures (A.5.2) rest on gas data, and
   ISO gives no heat spread. Details: `site/content/fundamentals/heat.md`
   and `incapacitation-thresholds.md`; clothed law #290; test band #289.
7. A sourced heat σ (Hockey & Rew 1996 probits; not in the library).
8. Should heat affect speed or route choice? The Handbook gives tolerance
   times, not performance loss.

## Rejected alternatives

- **The draft's two-dose method** (radiant r/q^1.33 above 2.5 kW/m² plus
  convective Eq. 63.45). Pairs the pain constant r = 1.33 with the tolerance
  law and calls FED = 1 incapacitation; mixes endpoints; kept only as
  background.
- **q = U/2 as a conservative bound.** Not an upper bound (see above).

## Issues

#218 endpoint and docs, #219 tests from SFPE tables, #220 endpoint-coherent
configuration, #221 radiant flux from `INTEGRATED INTENSITY`, #222 radiant
flux from the layer, #223 total-flux method (the core of this spec), #224 FDS
validation deck, #225 heat σ, #81 heat in route choice.
