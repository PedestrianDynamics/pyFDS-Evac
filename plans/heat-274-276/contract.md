# Heat FED from FDS radiation: #276, #274, #275 — model contract

Status: contract for maintainer review. No code. Base: `origin/main`
a458415a. Author role: backend-model. Read with spec 016
(`specs/016-heat-fed/SPEC.md`), Models › Heat (`site/content/models/heat.md`),
Verification › Heat dose (`docs/testing-heat.md`) and Heat radiometer
(`docs/testing-heat-radiometer.md`).

Recommendation in brief:

- **#276 first.** Add FDS `RADIOMETER GAS` devices as a fourth radiant
  source of the opt-in total-flux method. One orientation per run. The
  convective term stays the slice term. The default path does not change.
- **#274 second, and only after the #276 evidence.** Read FDS layer devices
  and `ABSORPTION COEFFICIENT`. This needs a new short FDS run (go-ahead).
  It cannot fix the wall-facing #308 miss.
- **#275: no implementation.** Keep one regime per run and document it. No
  source gives a rule. With an FDS radiation source (U or radiometers) the
  regime has no effect on the radiant term.

---

## 1. Rino's methods note against the code

Note: `rino.txt` (a methods description of the current heat FED by a
collaborator; its equations were images and did not convert, so the
equation content below is inferred from the surrounding text). Verdicts:
**agree**, **disagree**, or **source** (a claim about ISO/SFPE that the
code cannot check; enrico checked it against the texts, §12, and the result
is given). Line numbers are on a458415a.

| # | Claim in the note | Code (file:line) | Verdict |
|---|---|---|---|
| R1 | Heat FED is the fraction of the dose for pain, injury or fatal exposure | `fed.py:356-360` (`HEAT_ENDPOINTS` tolerance, injury, fatal) | agree |
| R2 | ISO Eq. (11) / SFPE Eq. 70.46 sums Δt/t_conv + Δt/t_rad (note Eq. 1) | not implemented: the convective method has no radiant dose; total flux replaces the sum (`fed.py:1753-1762`); spec 016 rejects the two-dose method (`SPEC.md:227-230`) | agree as a source description; the note itself says Eq. 7 replaces Eq. 1. Readers may still take Eq. 1 for code |
| R3 | Default convective law is ISO Eq. (9), fully clothed | `fed.py:285`, `fed.py:289` (`4.1e8, 3.61`, `DEFAULT_HEAT_CLOTHING = "clothed"`) | agree |
| R4 | Unclothed: ISO Eq. (10), the coefficients of SFPE Eq. 70.42 | `fed.py:286` (`5e7, 3.4`; code cites 5th ed. Eq. 63.44) | agree |
| R5 | Tolerance, injury, fatal use SFPE Eqs. 70.43-70.45 | `fed.py:356-360` (Eqs. 63.45-63.47 = 70.43-70.45 by `fed.py:355`) | agree |
| R6 | Gas temperature from the `TEMPERATURE` slice, "normally at 1.6 m" | `parameters.py:196` (`SMOKE_SLICE_HEIGHT_M = 1.6`), `run_config.py:255-261` (slice nearest `--smoke-slice-height`, warns beyond 0.2 m, `fds_sampling.py:36`) | agree |
| R7 | D = 1.33, 10, 16.7; 16.7 by default | `fed.py:357-359`, `fed.py:1755` (fatal D when no `--heat-endpoint`) | agree on values. Default holds only within `--heat-fed-method total-flux`; the default method is `convective` (`parameters.py:205`). Labels: **source, partly disagree** (Q9). SFPE 6th pp. 2318-2319 labels 1.33 "tolerance threshold" / "tolerance limit/pain/first-degree burns", 10 "incapacitation and serious injury" / "severe incapacitation and second-degree burns", 16.7 "50% lethal level for the average population" / "fatal exposure with third-degree burns". "Potentially fatal" is not a Handbook label of 16.7 (it appears only for the convective endpoint, p. 2318) |
| R8 | Eq. 8 applies for q > 0; no dose at zero | `fed.py:612-613` (q ≤ 0 or non-finite → 0) | agree |
| R9 | The reciprocal of Eq. 8 times Δt is accumulated | `fed.py:614` (q^1.33/D per min), `fed.py:1820-1824` (× dt/60) | agree |
| R10 | Eq. 9: q = max(0, q_conv + q_rad*) | `fed.py:1700-1709` then `fed.py:612` | agree |
| R11 | q_rad* = 0 below 2.5 kW/m², q_rad at or above | `fed.py:517`, `fed.py:520-528` (`<` 2.5 → 0; 2.5 counts) | agree |
| R12 | The threshold acts on the radiant part only | `fed.py:1700-1702` (threshold on `radiant`; convection added after, `fed.py:1703-1709`) | agree |
| R13 | ISO's threshold is incident; the code applies it to net or excess flux | net: `fed.py:574-577`, `fed.py:600`; excess: `fed.py:1732-1738` | agree |
| R14 | "SFPE describes the total-flux method for total fluxes above 2.5 kW/m²" | spec 016 attributes the threshold on total q to the draft (`SPEC.md:96`, `SPEC.md:99-104`); the code gates the radiant term only (`fed.py:1700-1702`) | **source, agree** (Q7): SFPE 6th p. 2319 (5th p. 2384) gives the endpoint times "for total heat fluxes more than 2.5 kW/m²". The code's gate therefore matches neither source literally: SFPE gates total q, ISO §8.2 the incident radiant flux, the code the net radiant term (spec 016 decision to follow ISO's radiant-only gate) |
| R15 | Eq. 10: q_conv = h (T_g − T_s)/1000, T in K | `fed.py:576-577` | agree |
| R16 | h = 5 W m⁻² K⁻¹, T_s = 35 °C fixed | `fed.py:491`, `fed.py:494` | agree. Conflict: the spec 016 convection check uses T_s = 36 °C (`SPEC.md:111-112`), not the default 35 °C |
| R17 | SFPE gives an approximate range for h | comment `fed.py:489-490` ("approximately 5-8 for slow-moving air", p. 2384) | agree; **source** checked (Q11): the 6th ed. p. 2319 has the 5th ed.'s wording (p. 2384), "approximately 5–8 for slow-moving air", with no unit |
| R18 | Eq. 11: εσ(T_g⁴ − T_s⁴), same slice as Eq. 10, ε = 0.5 assumed for smoke | `fed.py:488`, `fed.py:1720-1726` | agree |
| R19 | Both terms divided by 1000; SFPE prints it on the convective term only | `fed.py:572-577` (docstring and code) | agree; both editions print `/1000` on the convective term only, with no outer bracket (6th p. 2319, 5th p. 2383; Q11) |
| R20 | "When the occupant is immersed in smoke ..." / "If the occupant is below a hot smoke layer ..." | the regime is one user choice for the whole run (`parameters.py:860-873`, `fed.py:1628-1633`); no per-occupant test exists | **disagree** in wording: reads as a per-occupant decision. It is a run setting (#275) |
| R21 | Eq. 12: T_L from a second `TEMPERATURE` slice at the agent's x, y; user gives height, φ, ε_L; replaces Eq. 11; convection still from the head slice | `run_config.py:323-344`, `fed.py:1717-1719`, `fed.py:1767-1778`, `fed.py:1697-1709` | agree. Not said: none of the three has a default; a missing layer sample falls back to 20 °C (`fed.py:1773-1777`); q_ext is a net flux (`fed.py:589-592`) |
| R22 | Eq. 13: f (U − reference) with U in kW/m² | `fed.py:1727-1738`; the `/1000` is on 4σT_s⁴ only, U is already kW/m² | agree |
| R23 | The reference subtraction is an implementation assumption, not ISO or SFPE | maintainer decision #221 (`SPEC.md:34-39`; `heat.md:357-359`, "a choice, not a reading of the sources") | agree. Add: FDS's radiometer (UG Eq. 22.36) subtracts σT_gauge⁴ of the plate, the same basis; in the #224 uniform room R/(U − 4σT_s⁴) is 0.250 for every facing (scratch, §4.6), and f = 0.25 with convection matches the FDS gauge within 3 % (`testing-heat.md`, #221 check). That is an FDS counterpart, not an ISO/SFPE source |
| R24 | f in [0.25, 1] converts all-direction radiation to surface exposure | `fed.py:505`, `fed.py:531-553` (enforced; no default) | agree on the code. The bounds are geometric bounds on the incident f·U. The #224 radiometers on the excess basis give 0.113 facing down and 0.21-0.26 sideways under the layer (§4.6), below 0.25 |
| R25 | Eq. 13 replaces Eqs. 11 and 12; the local gas or layer is not added again | `fed.py:1628-1640` (`uses_layer_term` false with U; one warning) | agree |
| R26 | The selected radiant flux passes the threshold before Eq. 9 | `fed.py:1700-1702` | agree |
| R27 | Dose along each trajectory, separate from the toxic FED | `fed.py:1810-1825`; `TenabilityConfig` docstring `fed.py:747` ff. | agree |
| R28 | Ref. [2]: Purser & McAllister (2026), 6th ed. Ch. 70, pp. 2318-2319 | code and pages cite the 5th ed. Ch. 63 pp. 2382-2384 as primary, the 6th ed. only as a mapping (`fed.py:350-355`) | **source, agree** (Q9): 2026, Ch. 70 "Assessment of Hazards to Occupants from Smoke, Toxic Gases, and Heat", pp. 2271-2352; Eqs. 70.41-70.46 on p. 2318, 70.47 on p. 2319, one-to-one with 63.43-63.49. Conflict with the project convention (cite the 6th ed.); docs item, not a model defect |
| R29 | ISO 13571:2012 §§8.2-8.5, pp. 9-10 | — | **source, agree** (Q8): §8.1-8.2 on p. 9, §8.3-8.5 on p. 10. §8.2 calls 2.5 kW·m⁻² an "incident heat flux level"; §8.4 zeroes 1/t_Irad "where the radiant flux to the skin is under 2,5 kW·m⁻²" |
| R30 | Layer slice height user-given; head slice at the slice height | `parameters.py:877-886` (no default) | agree |
| R31 | ISO/TR 13571-2:2016 §6.3 supports applying the ISO thermal models | not cited in the code or docs | not checked: not sent to enrico. (Enrico cited its Annex A, p. 13, for head-height temperatures at 1.4 m, a different point) |

Two further conflicts found while checking:

- `specs/016-heat-fed/SPEC.md:3` still says "design, not implemented";
  the total-flux method, the layer regime and the U source are implemented
  (#221-#223).
- R20: the per-occupant wording also appears nowhere in the code docs;
  Models › Heat says the regime is a user choice for the whole run
  (`heat.md:294-296`). The note should say so.

**How the note's flagged assumptions interact with #276.**

1. *Net vs incident threshold (R13).* A radiometer gives both: with
   emissivity 1, incident = reading + σT_s⁴, a fixed offset of 0.511 kW/m² at
   T_s = 35 °C. So "net ≥ 2.5" is "incident ≥ 3.01". The choice matters on the
   #224 data: under the layer at 1.6 m the sideways plates (`px`, `mx`) never
   reach 2.5 net (0 of 763 samples each, t ≥ 1 s) but reach 2.5 incident in
   300 and 252 of 763; in the #308 deck at t = 3 s five of seven `px` points
   lie between 2.01 and 2.30 kW/m² net. The facing-up plates exceed 2.5 on
   both bases. Decision D3.
2. *Reference subtraction in Eq. 13 (R23, R24).* The radiometer is the
   physical version of the same subtraction (the plate's own emission at
   T_gauge), with the orientation solved by FDS. A radiometer source needs no
   f. Where both exist, the radiometer measures the f that U would need:
   f_eff = R/(U − 4σT_s⁴) (§4.6).

---

## 2. Classification, defaults, outputs

- **Class:** intentional model change, all three issues. Each adds an
  opt-in input to the opt-in total-flux method.
- **Default path unchanged.** `--enable-heat-fed` stays off by default; with
  it, `--heat-fed-method convective` (ISO Eq. (9)) stays the default, and in
  total flux `--heat-radiant-source gas`, `--heat-regime smoke`, ε 0.5, h 5,
  T_s 35 °C stay. No golden, snapshot or documented number of the default
  path moves. FDS+Evac has no radiant heat dose, so there is no FDS+Evac
  counterpart to keep; all new behaviour is opt-in.
- **Outputs that change only when the new options are set:** FED history
  gains `heat_radiometer_kw_m2` (net reading) and
  `heat_radiometer_incident_kw_m2` (diagnostic) (#276),
  `heat_layer_interface_m` and `heat_layer_emissivity` (#274); manifest
  `heat_flux_parameters` gains the source, orientation, gauge temperature
  and emissivity, device count and grid spacing.
- **Exception to "unchanged":** decision D3, if the maintainer moves the
  threshold to an incident basis. That changes opt-in documented numbers
  (§10).

## 3. Current behaviour (what the contract builds on)

- Total flux: q = radiant + h (T_g − T_s)/1000, the radiant term counted as 0
  below 2.5 kW/m² (`fed.py:1683-1709`); rate q^1.33/D (`fed.py:603-614`).
- Radiant sources: `gas` εσ(T_g⁴ − T_s⁴) (`fed.py:1720-1726`); `integrated-
  intensity` f (U − 4σT_s⁴) (`fed.py:1727-1738`); layer term
  φ ε_L σ(T_L⁴ − T_s⁴) in `--heat-regime layer` (`fed.py:1717-1719`).
- U wins over the layer term (`fed.py:1628-1640`). U must cover every agent
  that the `TEMPERATURE` slice covers (`fed.py:1517-1531`). Outside the FDS
  domain U is NaN, the rate 0, with one warning (`fed.py:1794-1808`).
- The FED history keeps the physical q, before the threshold
  (`fed.py:687-718` calls `heat_flux_kw_m2` without `radiant_threshold`).
- fdsreader 1.14.0 (installed) exposes, per device point: `id`
  (`<ID>-<k>` for `POINTS`), `quantity_name` (`RADIOMETER`, `GAUGE HEAT
  FLUX`: FDS drops the `GAS` suffix), `xyz`, `orientation`, `unit` and
  `data`. It does not expose `&PROP` values (`GAUGE_TEMPERATURE`,
  `HEAT_TRANSFER_COEFFICIENT`, `GAUGE_EMISSIVITY`). Probed on a scratch copy of
  `fds-evac-data/heat_radiometer/layer_308`. The deck parser
  `pyfds_evac/core/fds_deck.py:184` (`parse_fds_deck`) can read `&PROP`.

---

## 4. #276 — radiant flux from FDS radiometers

### 4.1 Which device

FDS UG 6.10.1 Sec. 22.10.12, p. 381 (already quoted in
`testing-heat-radiometer.md`; enrico checked the rendered page):

- gauge: q_gauge = ε (q_inc − σT_gauge⁴) + h (T_g − T_gauge)   (22.35)
- radiometer: q_rad = ε (q_inc − σT_gauge⁴)   (22.36)

`&PROP` defaults (UG p. 381): `GAUGE_TEMPERATURE` = `TMPA`,
`GAUGE_EMISSIVITY` = 1, `HEAT_TRANSFER_COEFFICIENT` = 10 W/(m² K). So a
deck that leaves out `GAUGE_TEMPERATURE` measures against a plate at
ambient (20 °C), not the skin: the check below must catch that. The UG
defines T_g only as "the gas temperature in the vicinity of the surface"
(p. 380); the FDS source suggests the temperature of the device's gas cell
(enrico's inference from a development checkout, not the 6.10.1 release).
In that development source `GAUGE HEAT FLUX GAS` and `RADIOMETER GAS`
survive only as old-name aliases of `GAUGE HEAT FLUX` and `RADIOMETER`; the
6.10.1 output already reports `RADIOMETER` (fdsreader probe). The reader
accepts both spellings.

Options (decision D1):

| Option | Radiant term | Convective term | Consistency rule | Double-count risk |
|---|---|---|---|---|
| **R (recommended)** `RADIOMETER GAS` | the device reading | pyFDS-Evac's h (T_g − T_s)/1000 from the slice, as today | `GAUGE_TEMPERATURE` = `--heat-skin-temperature` (to 1e-6 °C); `HEAT_TRANSFER_COEFFICIENT` irrelevant | none: the device has no convective part |
| G `GAUGE HEAT FLUX GAS` | gauge − h_PROP (T_dev − T_s)/1000, needs a co-located `TEMPERATURE` device | inside the gauge | T_gauge = T_s and h_PROP = `--heat-convective-coefficient`, else the user's h is silently replaced | high: adding the slice convection on top counts it twice |
| RG both | radiometer | gauge − radiometer (FDS's own h) | T_gauge = T_s; CLI h ignored or must equal h_PROP | low, but two device sets |

Why R: it fits the existing design (the source replaces only the radiant
term; convection always comes from the slice with the user's h), the
threshold applies to the radiant term without a split, and only one `&PROP`
value must match. The gauges stay useful as the validation reference
(gauge − radiometer = h (T_g − T_s) holds to 3.8·10⁻⁷ kW/m² in #224). The
issue text names `GAUGE HEAT FLUX GAS`; choosing R departs from its wording,
not its intent.

`&PROP` check: the reader parses the case's `.fds` with `parse_fds_deck`
(`fds_deck.py:184`). Checked on `heat_radiometer_layer_308.fds`: it returns
`&PROP` `{'ID': ['skin'], 'GAUGE_TEMPERATURE': [35.0],
'HEAT_TRANSFER_COEFFICIENT': [8.0]}` and the multi-line `&DEVC RAD_z16_up`
with `PROP_ID`, `ORIENTATION`, `XBP` and `POINTS`, no issues. A device
point maps to its `&DEVC` by its fdsreader ID with the trailing `-<digits>`
stripped (`RAD_z16_up-3` → `RAD_z16_up`); that works for `-3` and `-03`
alike, so the padding question (O4) does not block. The reader then takes
the `&PROP` of each selected device, and stops with an error when
`GAUGE_TEMPERATURE` differs from `--heat-skin-temperature` or when the deck
is absent (decision D5). A `&PROP` without `GAUGE_TEMPERATURE` reads as
`TMPA` and fails the check unless T_s equals it. `GAUGE_EMISSIVITY` (default
1) is recorded in the manifest, not checked.

### 4.2 FDS input the user adds

At the height of the `TEMPERATURE` slice (default 1.6 m), one orientation per
`&DEVC` family, on a regular rectangular grid of points:

```fortran
&PROP ID='skin', GAUGE_TEMPERATURE=35. /   ! = --heat-skin-temperature
! one line per grid row y_j; POINTS along x. Repeat for each row.
&DEVC ID='RAD_up_r01', QUANTITY='RADIOMETER GAS', ORIENTATION=0,0,1,
      PROP_ID='skin', XBP=x0,x1, y1,y1, 1.6,1.6, POINTS=nx, TIME_HISTORY=T /
&SLCF PBZ=1.6, QUANTITY='TEMPERATURE' /
```

- Keywords used above all occur in the tracked deck
  `assets/heat_radiometer/heat_radiometer_layer_308.fds:46-69`. One `&DEVC`
  cannot write a 2-D array: `POINTS` gives a 1-D line (straight between the
  `XBP` ends, or along `POINTS_ARRAY_X/Y/Z`, at most 100 values each); for
  the gas gauges the UG says "one-dimensional array" (UG §22.2.5,
  pp. 359-361; pp. 381-382). A grid therefore needs one `&DEVC` per row.
  pyFDS-Evac can print these lines for a given rectangle and spacing (a
  convenience, PR 2 or later).
- Column names: the UG shows `ID-01`, `ID-02`; the 6.10.1 output read here
  has `T_z16-1`. Whether IDs pad beyond 99 points is not documented. The
  reader selects by quantity, orientation and z, and strips `-<digits>` only
  to find the `&DEVC` (§4.1), so the padding does not matter.
- Orientations: `0,0,1` (crown) or a horizontal unit vector (face). The user
  picks one per run with a required flag, for example
  `--heat-radiometer-orientation 0,0,1` (decision D2). Devices are selected by
  `quantity_name` in {`RADIOMETER`, `RADIOMETER GAS`}, orientation (to
  1e-6) and z; the ID is used only to find the `&DEVC` and its `&PROP`
  (§4.1), so the user needs no naming convention.
- Spacing: an engineering choice of the user. The #224 lines use 0.5 m. The
  docs recommend ≤ 0.5 m and one cell or more from walls; no source.

### 4.3 Sampling along paths

- **Space.** The selected points must form a regular rectilinear grid
  (sorted unique x × unique y, every node present, spacing uniform to 1e-6 m);
  otherwise an error that lists the missing nodes. Bilinear interpolation
  inside the grid; exact at nodes. A grid one row wide is accepted, and then
  only agents on that row (to 1e-6 m) are inside it: this is the form the
  #224 data have, and it serves the validation.
- **Height.** All selected devices at one z (to 1e-6 m). That z must lie
  within half a cell of the `TEMPERATURE` slice z, so convection and
  radiation come from one height (as `_check_same_slice_height` does for U);
  otherwise an error naming both heights.
- **Time.** Linear interpolation between device output times; the horizon
  rules of the slices apply (`FdsHorizonError`, `--allow-fds-horizon-hold`).
- **Coverage.** Inside the `TEMPERATURE` slice but outside the grid: an
  error, as for a point inside only one of the `TEMPERATURE` and U slices
  (`fed.py:1517-1531`). A missing radiometer is never read as zero (decision
  D4). Outside the FDS domain: radiant NaN, rate 0, one warning, or
  `FdsDomainError` with `--require-fds-coverage`, as for U.
- **Known limit.** Bilinear interpolation does not know walls or
  obstructions: across a wall it mixes rooms, and devices inside an
  obstruction read meaningless values. Documented, not checked.

### 4.4 Net vs incident, threshold, convection

- The radiometer reading is the **net** radiant flux to a plate at T_gauge =
  T_s with the device emissivity (Eq. 22.36). It enters as the radiant term
  as read: no conversion, no factor.
- **Threshold:** applied to that net reading, as for every other source
  (spec 016 decision; R13). The incident value (reading/ε + σT_s⁴) is
  written to the history as a diagnostic but does not enter the dose, unless
  the maintainer chooses D3 = incident.
- The sources gate three different quantities: ISO §8.2 the incident radiant
  flux, SFPE p. 2319 the total q, the code the net radiant term (R14). The
  radiometer (reading/ε + σT_s⁴) and the U source (f·U) can supply an
  incident value. For the `gas` and layer sources no incident flux is
  defined without the background radiation, so an incident gate cannot be
  applied to every source.
- **Convection:** h (T_g − T_s)/1000 from the slice, added once, after the
  threshold, as now. Not taken from the device.
- **With other options:** the radiometer source replaces the gas term and
  the layer term (FDS's radiation already contains the layer, as for U);
  `--heat-regime layer` with it logs one warning, `layer_term: false`.
  `--heat-emissivity` and `--heat-u-factor` are ignored (warn if given).

### 4.5 Validation, predeclared

All comparisons use the physical q (`heat_flux_kw_m2`, before the
threshold), as #308 did; the threshold and dose are tested separately.
Comparing radiometer-fed q with the FDS gauge at the same point **checks the
reader and the assembly of q, not the model**: the reference contains the
same radiation solution. It says nothing about whether a plate is a person.

| ID | Data | Check | Tolerance and why |
|---|---|---|---|
| V1 | synthetic device collection (unit) | bilinear values on a 2 × 3 grid, hand-computed; node identity; irregular grid, missing node, wrong z, wrong orientation, T_gauge ≠ T_s, agent outside grid → errors | 1e-12 (exact arithmetic) |
| V2 | synthetic (unit) | q = R + h (T_g − T_s)/1000 with R = 3.0, h = 8, T_g = 60 °C, T_s = 35 °C: 3.200 kW/m²; fails if h ΔT is added twice (3.400) or the threshold acts on q (R = 2.4: q = 0.200, not 2.600) | 1e-12 |
| V3 | `fds-evac-data/heat_radiometer/{layer,uniform}` (external_data), agents at the 7 device x on y = 2.05 m, z 1.6 m, h 8, T_s 35 °C, each orientation `up`, `px`, `mx`, `dn` | radiant term in the history = an independent linear interpolation in time of `RAD_z16_<o>-k` at the history's update times | 1e-6 kW/m²: the same number through interpolation at nodes |
| V4 (gate) | as V3 | q − `GAUGE_z16_<o>-k` (both interpolated to the update time) = h (T_slice − T_dev)/1000, with T_dev = `T_z16-k` | 1e-6 kW/m²: an identity of Eq. 22.35 given V3. This is the gate for the gauge comparison |
| V5 (report) | as V3 | \|q / q_gauge − 1\| at t = 3, 6, 9 s, per orientation | not gated. The only difference is the slice vs device head temperature (#308: up to 12 %, about 7 K at 9 s; h = 8 gives about 0.06 kW/m²). Relative to q that is about 4 % sideways (q ≈ 1.4 kW/m²) and about 7 % facing down (gauge ≈ 0.86 kW/m²), so one band would be set by the weakest plate. Reported with the expected h·ΔT/q per orientation |
| V6 (report) | `fds-evac-data/heat_radiometer/layer_308`, the 21 #308 runs (up, px, mx × 7) with the radiometer source | V4 identity as the gate; \|q/q_gauge − 1\| reported beside the layer term's 54 of 63 within ±30 % | V4 tolerance. Reader check, as above; #308's recorded miss stays |
| V7 | `fds-evac-data/heat_radiometer/burner` | where `RAD` ≥ 2.5 kW/m² the dose rate > 0 from radiation; below, rate = convection only | exact (threshold logic on real data) |
| V8 | layer data, 1-D leave-one-out at interior points k = 2-6 | interpolation error from k−1, k+1 | reported, not gated: the band would be set after seeing the data |

2-D interpolation along a path is tested only on synthetic data (V1). A real
2-D check needs a new FDS deck with a radiometer grid (the #308 deck plus a
grid; seconds on 4 ranks). That run needs the maintainer's go-ahead
(decision D6).

### 4.6 Scratch evidence on f (not a test)

From the last output step of the #224 device files, 1.6 m, T_s = 35 °C,
f_eff = R/(U − 4σT_s⁴) (scratch script, not committed; the docs' figures use
time means and a 20 °C basis, so the numbers differ from those tables):

| Deck | up | px | mx | dn |
|---|---|---|---|---|
| uniform | 0.250 | 0.250 | 0.250 | 0.250 |
| layer (min-max over 7 points) | 0.445-0.456 | 0.209-0.264 | 0.206-0.261 | 0.112-0.120 |

The burner deck is left out: its denominator U − 4σT_s⁴ is 0.19-6.2 kW/m²
over the five points (surroundings at 20 °C, below T_s), so the ratio is not
meaningful at the far points. With radiometers no f is needed.

### 4.7 Fallback without radiometers

None. `--heat-radiant-source radiometer` on a case without matching devices
stops with an error that names the quantity, orientation and height and
shows the `&DEVC` line of §4.2 (like the D17 message for U,
`config/messages.py:166-171`). No silent fall back to `gas`, U or the layer
term. Cases without the option run as today.

---

## 5. #274 — layer temperature, interface height and ε_L from FDS

### 5.1 What #308 says #274 can and cannot fix

- Facing up, the layer term was 15-37 % high with ε_L = 1 and geometric φ;
  the implied φ_eff was 0.67-0.84 against φ 0.86-0.97 (`testing-heat.md`,
  #308). A layer emissivity below 1 from FDS's absorption could explain part
  of that. Untested.
- The wall-facing misses (`px` at x = 3.45 m, `mx` at x = 0.45 m, 33-54 %
  low) are a φ and wall-emission problem: the layer term counts only the
  layer base. Better T_L or ε_L does not fix them. #276 does.
- So #274 improves the layer term only where the layer dominates the view.
  After #276, the layer term is the fallback for cases without radiometers.

### 5.2 Options for T_L and the interface height

| Option | Input | T_L, interface | Pros | Cons |
|---|---|---|---|---|
| L0 (today) | one `TEMPERATURE` slice at `--heat-layer-height` | point T at a fixed height; no interface | simple | reads the ceiling jet near the ceiling; one ceiling height |
| L1 | several horizontal `TEMPERATURE` slices | layer reduction computed by pyFDS-Evac per (x, y) | full-plane coverage, existing slice reader | reimplements FDS's reduction on a coarse discrete profile; needs the ceiling height per column (geometry) |
| **L2 (recommended)** | FDS `LAYER HEIGHT` and `UPPER TEMPERATURE` devices on vertical lines, columns on a regular x-y grid | FDS's own reduction, interpolated with the #276 grid reader | FDS-defined quantity, verifiable to the device, no reimplementation, reuses PR 1 | one `&DEVC` per column; across walls the same limit as §4.3 |

What FDS documents (UG §22.10.7, pp. 375-376; Table 22.6, p. 408):
`LAYER HEIGHT`, `UPPER TEMPERATURE`, `LOWER TEMPERATURE` are device-only
quantities (no slice) on a vertical line `XB` (the example runs z = 0 to
3 m). The reduction follows Janssens & Tran, J. Fire Sci. 10:528-555
(1992): with I₁ = ∫₀ᴴ T dz and I₂ = ∫₀ᴴ 1/T dz,
z_int = T_l (I₁ I₂ − H²)/(I₁ + I₂ T_l² − 2 T_l H) (Eq. 22.25) and
(H − z_int) T_u = ∫ from z_int to H of T dz (Eq. 22.26), with T_l "the
temperature in the lowest mesh cell". The only caveat stated is that "there
are not two distinct zones, but rather a continuous profile"; no limit for
ceiling jets or the near field. Not documented: whether the line must run
floor to ceiling (inferred from the example), and whether z_int is absolute
or relative to the bottom of `XB` when that is not 0. PR 3 settles the
second with a one-column test deck with a raised `XB` before relying on it.
Open modelling point: `UPPER TEMPERATURE` is a
mean of T, while emission goes with T⁴; for a stratified layer
σ(mean T)⁴ < mean(σT⁴). Whether to use T_u as is or a T⁴ mean from a
temperature line is a decision (D7), not a source.

### 5.3 Options for ε_L

| Option | ε_L | Needs |
|---|---|---|
| E0 (today) | user constant | nothing |
| **E1 (recommended)** | 1 − exp(−κ̄ L), κ̄ the mean `ABSORPTION COEFFICIENT` in the layer, L = 1.8 (H − z_int) | a κ line per column, z_int from L2 |
| E2 (rejected) | 1 − exp(−∫ κ dz) from z_int to the ceiling, the vertical optical depth | κ line per column, z_int from L2 |

E1 uses the sourced mean beam length for a slab. E2 is rejected: it takes
the vertical path only, while a face sees the layer along longer, slanted
paths, and it has no sourced path length. Both depend on FDS's
`PATH_LENGTH` (below). With either, a face also needs φ.

Sources and caveats:

- **Path length.** SFPE 6th Ch. 23 (Lautenberger): ε = 1 − exp(−κS)
  (Eq. 23.48, p. 656); mean beam length L ≈ 0.9 · 4V/A (Eqs. 23.57-23.59,
  p. 658); for an infinite slab of thickness D radiating to an element on
  its face, L₀ = 2D, C = 0.9, so L ≈ 1.8D (Table 23.10, p. 659). Ch. 60
  (Wickström) states L_e = 1.8 L between two planes (Eqs. 60.23-60.24,
  p. 1964). These hold for a uniform, isothermal gas seen from its own
  boundary. A head below the interface of a finite layer also needs the
  view factor φ; 1.8D is not φ. So E1 with L = 1.8 (H − z_int) is the
  sourced form for the crown under a wide layer.
- **What FDS's κ is.** `ABSORPTION COEFFICIENT` is the gray absorption
  coefficient [1/m] of the gases and soot, from RadCal tables, available
  as slice and device (UG §14.3, p. 206; Table 22.4, p. 403). With one
  band it is κ = min(Planck mean, path mean at L = `PATH_LENGTH`), default
  0.1 m (UG §14.3.1, p. 207; TRG App. C, Eqs. C.4-C.6, p. 156). It is not
  usable with the wide-band or WSGG models. So a κ computed at 0.1 m does
  not apply to a 1 m path: the user must set `PATH_LENGTH` near the layer
  path, or the run must show the result does not depend on it. FDS gives no
  guidance on layer emissivity (UG, TRG: not found).
- **Consequence for E1.** The deck's `PATH_LENGTH` is recorded in the
  manifest, and PR 3 includes a sensitivity run with `PATH_LENGTH` = 0.1 m
  and = 1.8 × layer depth (D6, D7).

### 5.4 Validation, predeclared

No tracked deck writes `LAYER HEIGHT`, `UPPER TEMPERATURE` or `ABSORPTION
COEFFICIENT`. Validation needs a new run of the #308 deck with these devices
at the 7 columns (6 s on 4 ranks for #308; go-ahead D6). Then:

| ID | Check | Tolerance and why |
|---|---|---|
| V9 | reader: interface and T_u at the columns = the FDS devices | 1e-6 |
| V10 | interface at t = 1 s: the `&INIT` layer base 2.0 m | ± one cell (0.1 m): the step is sharp at the start |
| V11 | T_u against the `T_z25` device | reported; the layer is uniform in z at t = 0 and stratifies later |
| V12 | rerun the 21 #308 cases with L2 + E1, at both `PATH_LENGTH` values | facing up: 21 of 21 within ±30 % (the #308 band). Sideways at the walls: expected to stay outside; recorded, not a gate |

V12 is predeclared now, before the run. A miss is a result.

## 6. #275 — regime per agent

No source gives a rule for deciding, per agent, whether the head is in smoke
or in clear air below a layer (spec 016 open question 4, `SPEC.md:206`;
`heat.md:294-296`). Enrico checked (Q10): no source gives a per-occupant
rule, by extinction, interface or temperature. What the sources say:

- ISO 13571:2012, Introduction (p. v): exposure is "determined, in part, by
  assumptions regarding the position of the occupants' heads relative to the
  hot smoke layer".
- SFPE 6th p. 2319 (5th p. 2384): below a hot layer "the only significant
  radiative heat flux sources are likely to be the upper layer, the fire, or
  hot surfaces". Its worked example (p. 2323) "assumed that the head … would
  always be in the smoke"; "if the height of the smoke layer with time is
  measured, then it is possible to allow for this factor". This points at
  rule B below but gives no margin or threshold.

Candidates, each with its threshold as an explicit parameter and no default:

| Rule | Input | Parameter | Notes |
|---|---|---|---|
| A: extinction at the head | the `SOOT EXTINCTION COEFFICIENT` slice already read for smoke speed | K_crit [1/m] | cheap; no source for K_crit |
| B: head below the interface | z_int from #274 L2 | margin Δz [m] (head height = slice height) | the most physical; needs #274 |
| C: temperature at the head | the `TEMPERATURE` slice | T_crit [°C] | conflates hot air and smoke |

What any rule would change: switching an agent between regimes switches the
ε term on and the layer term off, a step in q and in the rate. Without a
source there is no basis for a hysteresis or blending either.

With an FDS radiation source (U or radiometers) the regime does not touch
the radiant term (`fed.py:1628-1640`; §4.4). The question is only open for
the `gas` source and the layer term.

**Recommendation:** no code. Keep one regime per run, document the limit as
it is now (`heat.md:565-573`), and point users who need both regimes to the
radiometer source. Leave #275 open, labelled as needing a source (D8).

---

## 7. Design review (DESIGN_PRINCIPLES.md §9)

1. **Configurable:** radiant source (`radiometer`), orientation (required),
   layer source (`slice` | `devices`), ε_L source (`constant` |
   `absorption`). h, T_s, D unchanged.
2. **Derived:** incident = reading/ε + σT_s⁴ (diagnostic);
   ε_L = 1 − exp(−κ̄ · 1.8 (H − z_int)); T_gauge must equal T_s (checked,
   not set twice).
3. **Fixed:** σ = 5.67e-8, 2.5 kW/m² threshold constant, the exponent 1.33,
   the /1000 of both terms, Eqs. 22.35-22.36 as FDS defines them.
4. **Validity domain:** plate, not body; one orientation; the grid spacing
   the user chose; bilinear interpolation unaware of walls; device output
   interval; the slice height = device height.
5. **Sources:** FDS UG 6.10.1 §22.10.12 (gauges), §22.2.5 (`POINTS`),
   §22.10.7 (layer devices, Janssens & Tran 1992), §14.3 and TRG App. C
   (absorption coefficient); SFPE 6th Ch. 23 Table 23.10 (mean beam length);
   ISO 13571 §8.2/8.4 (threshold); SFPE 6th Ch. 70 Eqs. 70.41, 70.47
   (= 5th Ch. 63 Eqs. 63.43, 63.49). Engineering choices without source:
   device type R, one orientation, bilinear interpolation, coverage error,
   the net-basis gate, κ̄ as a line mean.
6. **Verification:** V1-V12 above; reader identities at nodes; #308
   rerun.
7. **Extension:** walking-direction face (several horizontal orientations,
   chosen per agent from its velocity) is the realistic next step; the grid
   reader takes an orientation, so it needs no redesign. Not in scope.
8. **Reproducibility:** the manifest records source, orientation,
   T_gauge, device emissivity, device count, grid origin and spacing. The
   manifest does not record the FDS deck's sha256 today (only `uv.lock`,
   `manifest.py:368`); PR 2 adds it, since the `&PROP` values come from
   the deck.
9. **Architecture:** one pure regular-grid interpolator and one device
   adapter behind fdsreader (dependency boundary); the heat model keeps one
   new branch in `_radiant_flux_kw_m2`. No class hierarchy.
10. **What could go wrong:** wrong orientation sign (the face looks away from
    the fire; V3 per orientation catches swaps); T_gauge ≠ T_s (checked);
    convection counted twice (V2); devices on cell faces vs centres (record
    positions as FDS writes them); a sparse grid smoothing a flame peak
    (documented; V8 reports it); interpolation across walls (documented).

## 8. PR split and order

| PR | Issue | Content | Tests: fail before / pass after |
|---|---|---|---|
| 1 | #276 | device adapter (`fdsreader` devices → points, orientation, z, series) and a regular-grid bilinear interpolator; no model change | new unit tests V1 (grid, errors). Before: module absent. QA checks sensitivity by perturbing one node value and by swapping x/y |
| 2 | #276 | `--heat-radiant-source radiometer`, `--heat-radiometer-orientation`, `&PROP` check, coverage rules, history/manifest fields, CLI/config rules, docs handoff | V2-V7 (V3-V7 `external_data`). Before: the CLI rejects `radiometer`; V2 fails on main. Default-path regression: existing heat tests and goldens unchanged, no re-record |
| 2b (only if D3 = incident) | #276 | threshold on incident for the radiometer (and U) source | unit test at reading 2.2 kW/m², T_s 35 °C: counted (incident 2.71) vs not (net). Documented numbers move (§10) |
| 3 (after D6, D7) | #274 | layer source `devices` (L2) and ε_L source `absorption` (E1), new FDS runs in `fds-evac-data/heat_radiometer/layer_274/` (with `PATH_LENGTH` 0.1 m and 1.8 × layer depth, plus a one-column deck with a raised `XB`) | V9-V12. Before: options absent |
| — | #275 | none (D8) | — |

Order: 1 → 2 → (2b) → decision on 3 from the V6 result. Each PR keeps the
default path bit-identical.

## 9. Decisions for the maintainer

1. **D1 Device type for #276:** `RADIOMETER GAS` with slice convection
   (recommended), `GAUGE HEAT FLUX GAS`, or both.
2. **D2 Orientation:** one fixed orientation per run, required flag, no
   default (recommended); walking-direction face later.
3. **D3 Threshold basis:** keep net for every source (recommended, consistent
   with spec 016) or incident for the radiometer and U sources. Neither
   matches the sources literally: ISO gates incident radiant flux, SFPE
   total q. Evidence: on the incident basis the sideways plates under the
   #224 layer count in 300 and 252 of 763 samples, against 0 on the net
   basis.
4. **D4 Coverage:** agent inside the slice but outside the radiometer grid →
   error (recommended), not zero.
5. **D5 `&PROP` check:** parse the deck, error if `GAUGE_TEMPERATURE` ≠
   `--heat-skin-temperature` or the deck is missing (recommended).
6. **D6 FDS runs:** go-ahead for two short local runs (seconds on 4 ranks): a
   2-D radiometer grid deck (V1 on real data) and the #308 deck with layer
   and absorption devices (#274). Recommended: yes, local, no JURECA.
7. **D7 #274 scope:** L2 (FDS layer devices) + E1 (κ̄ from an
   `ABSORPTION COEFFICIENT` line, L = 1.8 × layer depth, `PATH_LENGTH`
   recorded and tested at two values), T_u as FDS gives it; only after
   PR 2's V6 result (recommended). Or defer #274: after #276 the layer term
   only serves cases without radiometers.
8. **D8 #275:** no implementation; keep one regime per run, document, leave
   the issue open as needing a source (recommended).
9. **D9 Citations:** move the primary heat citation from SFPE 5th ed. Ch. 63
   to the 6th ed. Ch. 70 (project convention; Q9 confirms the one-to-one
   mapping), as a docs PR (recommended). Cite equations by content: both
   editions carry wrong internal cross-references (6th: "70.38", "70.30",
   "70.35"; 5th: "63.41", "63.46").
10. **D10 Spec 016:** update its status line and the T_s = 36 °C of the
    convection check to the implemented state (recommended, docs PR).

## 10. Docs handoff (docs-architect)

Pages that move with PR 2 (no default-path number moves):

- `site/content/models/heat.md:323-421` (new subsection "Radiant flux from
  FDS radiometers"), `:414-418` ("They are not read yet (#276)"), `:547-558`
  ("Gauge devices are not read"), `:565-573` (regime bullet: point to the
  radiometer source), `:653-672` (Assumptions: orientation, coverage rule,
  bilinear grid, T_gauge check), Output section (new history columns),
  Sources (FDS UG Sec. 22.10.12).
- `docs/testing-heat-radiometer.md:7-12` (Status row: decks now read),
  `:229-234` (Limits).
- `docs/testing-heat.md:357-449` (radiometer-source result beside #308),
  `:463` (assumption row "(#274, #275)"), Limits.
- `docs/limitations.md:140-155`; `docs/troubleshooting.md` (new errors);
  `docs/fds-sampling.md:~327` (height rule for devices).
- `specs/016-heat-fed/SPEC.md:3`, `:155-167`, `:201-207`.
- CHANGELOG Unreleased. GUI parameter mapping (webapp-integration): the new
  `--heat-radiant-source` choice and the orientation field.
- If D3 = incident: `heat.md:207-258` numbers (207, 285, 698 °C; 21.6, 6.7,
  2.0 min; 12.4 → 2.9 min; 2.33 vs 2.84 kW/m²), the figure
  `heat_radiant_threshold.png` and its script, and the Assumptions row
  "Radiant threshold basis".
- PR 3: `heat.md:260-321` (Hot layer), `:559-564`.

## 11. Task record (backend_team.md §6)

```text
Task / change class: #276, #274, #275 heat FED from FDS radiation; intentional
  model change, opt-in only; default path unchanged.
Model contract / documentation links: plans/heat-274-276/contract.md;
  specs/016-heat-fed/SPEC.md; site/content/models/heat.md;
  docs/testing-heat.md (#308); docs/testing-heat-radiometer.md (#224).
Affected outputs / invariants / tolerances: new opt-in history and manifest
  fields; default and existing opt-in outputs bit-identical (unless D3);
  V1-V12 tolerances in §4.5, §5.4.
Implementation / dependency impact: fdsreader 1.14.0 devices (id, xyz,
  orientation, quantity_name without GAS); &PROP via fds_deck.py; no new
  dependency; webapp mapping for one new choice.
Evidence: revisions a458415a; scratch device probe and counts on copies of
  fds-evac-data/heat_radiometer (no writes there); no FDS run.
Findings / outstanding checks / docs handoff: Rino table §1; source
  answers Q1-Q11 and open items O1-O5 §12; docs list §10; decisions
  D1-D10 §9.
QA gate: not started (contract phase).
```

## 12. Source checks (enrico)

Enrico read each passage in the FDS 6.10.1 UG and TRG, SFPE 6th (full
book) and 5th Ch. 63, ISO 13571:2012 and ISO/TR 13571-2:2016. Points marked
"inference" are his, not text.

| Q | Question | Answer | Status |
|---|---|---|---|
| Q1 | gauge equations, `&PROP` defaults, T_g | Eqs. 22.35/22.36, UG p. 381; `GAUGE_TEMPERATURE` = TMPA, `GAUGE_EMISSIVITY` = 1, `HEAT_TRANSFER_COEFFICIENT` = 10; T_g "gas temperature in the vicinity" (p. 380), the cell temperature by inference from dev source; GAS names are aliases in dev source | verified; T_g cell and release behaviour open (O1) |
| Q2 | 2-D point array, naming | no: `POINTS` is 1-D (UG §22.2.5, pp. 359-361); one `&DEVC` per row; UG shows `ID-01` | verified; padding past 99 open (O4) |
| Q3 | layer devices | UG §22.10.7, pp. 375-376, Eqs. 22.25-22.26, Janssens & Tran 1992; device only; T_l lowest cell | verified; absolute vs relative z_int open (O2) |
| Q4 | `ABSORPTION COEFFICIENT` | gray κ [1/m], gas + soot, RadCal; D/I/P/S; depends on `PATH_LENGTH` (0.1 m default); not for wide-band/WSGG (UG §14.3-14.3.1, pp. 206-207; TRG Eqs. C.4-C.6, p. 156) | verified (TRG from text extraction) |
| Q5 | FDS layer-emissivity guidance | none found; `PATH_LENGTH` rule of thumb 4V/A (UG p. 207) | not found |
| Q6 | path length for ε_L | 1.8 D for a slab seen from its face (SFPE 6th Ch. 23 Table 23.10, p. 659; Ch. 60 Eqs. 60.23-60.24, p. 1964); a finite layer also needs φ | verified |
| Q7 | SFPE total q > 2.5 | yes, "for total heat fluxes more than 2.5 kW/m²", 6th p. 2319, 5th p. 2384 | verified |
| Q8 | ISO incident | §8.2 "incident heat flux level"; §8.4 "radiant flux to the skin"; pp. 9-10 | verified |
| Q9 | 6th ed. citation and labels | 2026, pp. 2271-2352, Eqs. on pp. 2318-2319, 1:1 with 63.43-63.49; labels as in R7 | verified |
| Q10 | per-occupant regime rule | none; ISO Introduction p. v; SFPE 6th pp. 2319, 2323 | verified (not found) |
| Q11 | h and ε wording | identical in both editions; no unit for h | verified |

Open items, each blocking only its PR:

- **O1 (PR 2):** the 6.10.1 release, not dev, behaviour of
  `RADIOMETER GAS` (name in the output, cell temperature). The #224 output
  already shows quantity `RADIOMETER`; PR 2 adds a fixture from it.
- **O2 (PR 3):** whether `LAYER HEIGHT` is absolute z with a raised `XB`;
  a one-column test deck.
- **O3 (PR 3):** κ dependence on `PATH_LENGTH`; the sensitivity run.
- **O4 (docs):** `ID-` padding past 99 points; not needed by the reader.
- **O5 (docs):** the evidence base of r/q^1.33 (SFPE 6th refs [125, 126]),
  before any figure plots it beyond the measured range.

## 13. Maintainer decisions (2026-11-20)

- D1: `RADIOMETER GAS`, convection from the slice with the user's h.
- D2: one orientation per run, required flag, no default.
- D3: threshold on the net radiant flux for every source (as spec 016).
- D4: agent inside the slice but outside the radiometer grid is an error.
- D5: parse the deck; error if `GAUGE_TEMPERATURE` differs from
  `--heat-skin-temperature` or the deck is missing.
- D6: yes to the two short local FDS runs (no JURECA).
- D7: #274 after #276 (PR 2's V6 result), L2 + E1, `PATH_LENGTH` tested
  at 0.1 m and 1.8 x layer depth.
- D8: #275 no code; one regime per run, documented; issue stays open as
  needing a source.
- D9, D10: docs PRs (6th-edition citations; spec 016 status and T_s).

## 14. D6 results and E1 dropped (2026-11-20)

Runs in `fds-evac-data/heat_radiometer/{grid2d,layer_274,layer_274_pl,layer_height_xb}`
(FDS 6.10.1, decks from 9f11ee54).

- O2: `LAYER HEIGHT` is measured from the bottom of the device line's
  `XB`, and FDS takes T_l from the line's lowest cell. Layer lines must
  start at the floor.
- V10 missed: the interface at t = 1 s is 2.13-2.18 m, not 2.0 +- 0.1 m.
  FDS UG Eq. 22.25 on the cell temperatures reproduces it; with T_l fixed
  at 20 C it gives 1.96 m. The warming floor cell lifts it.
- O3: `PATH_LENGTH` changes the layer kappa by 3.7 % and also the clear-air
  kappa, so each variant has its own gauges.
- V12 preview (facing up, 21 cases, +-30 %): E1 gives 20/21 and 17/21 and
  pulls the ratios below 1; eps_L = 1 at the FDS interface gives 21/21
  for both `PATH_LENGTH` values.
- Deck A: the first full CLI run with `--heat-radiant-source radiometer`
  on real FDS output passes V4 (2.8e-7 kW/m2, 11 nodes x 8 times),
  |q/q_gauge - 1| <= 2.94 %.

**Maintainer decision: E1 is dropped.** 1.8 D is Hottel's mean beam
length for a slab radiating to its own boundary, not to a head below it
seen through phi, and it made agreement worse. #274 keeps L2 (layer
temperature from FDS devices) with eps_L a user input; layered cases are
pointed to the radiometer source. The base of phi (FDS interface or a
fixed height) is still open.

## 15. Base of phi: FDS interface (I) or fixed height (F), predeclared (2026-11-20)

Question: in the layer term q = h (T_g - T_s) + phi eps_L sigma
(T_u^4 - T_s^4), where is the base of the layer that phi sees?

- (I): the FDS interface, `LAYER HEIGHT` of the column, read at every
  output time.
- (F): a fixed height set by the user, as `--heat-layer-height` today.
  Scored at 1.8, 2.0 and 2.5 m.

Written before the descending run (step 2). The step-1 numbers below were
known when this section was written; the descending run was not.

### 15.1 Criterion

- Facing up only. T_u = `UPPER TEMPERATURE` of the column, T_g =
  `TEMPERATURE` at 1.6 m (device), eps_L = 1, h = 8 W/(m2 K), T_s = 35 C.
  phi = Howell C-11 from the gauge (1.6 m, the 4 x 4 m footprint) to the
  base, `phi_up` with `scripts/verification/heat_layer_view_factor.py`.
- Reference: `GAUGE HEAT FLUX GAS` facing up at 1.6 m, same column, same
  run. Check first that gauge - radiometer = h (T_g - 35 C) / 1000.
- Score: model / gauge within +-30 % (the #308 band).
- Pairwise: (I) against each of F1.8, F2.0, F2.5; three verdicts. The
  option with more scored rows within +-30 % wins the pair; a tie goes to
  (F) (simpler, implemented). Overall, (I) is adopted only if it wins all
  three pairs, since the user may set any fixed height.
- Deciding data: the descending run alone. Step 1 (`layer_274`,
  `layer_274_pl`) is reported beside it, not pooled.
- Sample times, set from `LAYER HEIGHT` only: t_a = first output time with
  the median interface over the 7 columns below 2.6 m, t_b = first time it
  is at or below 1.3 m (T_END if never). 8 times equally spaced over
  [t_a, t_b], both ends included.
- Values: model flux and gauge are each averaged over a centred 2 s window
  (output rows in [t - 1, t + 1]); the ratio is the ratio of those means.
  Point values are reported as a sensitivity.
- Floor: rows with mean gauge below 0.5 kW/m2 are listed, not scored.
- Head in the layer (interface at or below 1.6 m): outside the layer
  regime, which assumes clear air at the head. Not scored. Listed with
  phi = 1 for (I) (the limit of C-11 as the base reaches the gauge).
- Report per option: count within +-30 %, median ratio, worst miss.
- Sensitivity only, not gates: bands +-20 % and +-40 %, per-time counts,
  point values, and dropping the column nearest the fire.

### 15.2 Step 1 (no new runs; t = 3, 6, 9 s, 7 columns, point values)

| run | option | within +-30 % | median | worst |
|---|---|---|---|---|
| layer_274 | I | 21/21 | 1.096 | 1.257 |
| layer_274 | F1.8 | 18/21 | 1.228 | 1.380 |
| layer_274 | F2.0 | 20/21 | 1.184 | 1.310 |
| layer_274 | F2.5 | 21/21 | 1.031 | 0.788 |
| layer_274_pl | I | 21/21 | 1.031 | 1.150 |
| layer_274_pl | F1.8 | 21/21 | 1.160 | 1.287 |
| layer_274_pl | F2.0 | 21/21 | 1.123 | 1.236 |
| layer_274_pl | F2.5 | 20/21 | 0.952 | 0.663 |

The interface stays at 1.85-2.59 m, so the head is never in the layer.
(I) has the smallest spread; F2.0 is 20/21 and 21/21.
