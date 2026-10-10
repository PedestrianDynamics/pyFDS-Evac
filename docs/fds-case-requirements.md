---
title: "What your FDS case must provide"
linkTitle: "Your FDS case"
weight: 4
aliases: [/docs/fds-case-requirements/]
---

Read this before pointing `--fds-dir` at a case for the first time. To
check a deck for these slices before FDS runs, and to build the scenario
from it, see [Start from your own FDS case](start-from-fds-deck.md).

**pyFDS-Evac never runs FDS.** It reads the output of a finished FDS run.
A deck written for some other purpose usually will not work as-is: it has to
be told to dump the specific slices this tool samples.

## The slices

```
&SLCF PBZ=1.6, QUANTITY='EXTINCTION COEFFICIENT' /
&SLCF PBZ=1.6, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON MONOXIDE' /
&SLCF PBZ=1.6, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON DIOXIDE' /
&SLCF PBZ=1.6, QUANTITY='VOLUME FRACTION', SPEC_ID='OXYGEN' /
&SLCF PBZ=1.6, QUANTITY='TEMPERATURE' /
&DUMP DT_SLCF=1.0 /
```

Nothing here is dumped by default. FDS writes only what the deck asks for.

For the default species (soot), FDS records the extinction-coefficient
slice internally as `SOOT EXTINCTION COEFFICIENT`, and that is the exact
quantity name `load_slice_sampler` looks up
([fds-sampling.md](fds-sampling.md)).

| Slice | Feeds | If absent |
|-------|-------|-----------|
| Extinction coefficient | smoke-speed, visibility gating, GUI smoke layer | **smoke speed reduction is switched off and visibility falls back to clear air; the run continues** (see below). `--constant-extinction` restores smoke speed with a uniform K; visibility stays clear air |
| CO **and** CO2 **and** O2 | FED toxic dose | **FED is switched off and the run continues** (see below) |
| TEMPERATURE | heat FED (ISO 13571:2012 Eq. (9) or (10)), only with `--enable-heat-fed` | **heat FED is switched off and the run continues** (see below) |
| TEMPERATURE at `--heat-layer-height` | the hot-layer temperature, only with `--heat-regime layer` | the run stops |
| INTEGRATED INTENSITY | radiant flux f·(U − 4σT_s⁴), only with `--heat-radiant-source integrated-intensity`; at the TEMPERATURE slice z, covering the same area | `ValueError`: the run stops (also for another z, or an agent inside only one of the two slices) |

It is all three gases or none of them; there is no partial FED. TEMPERATURE
is independent of that gate — it needs neither CO/CO2/O2 nor any `&REAC`
yield to work (see below), so a case can have heat FED without toxic FED
or vice versa.

`EXTINCTION` and `EXTINCTION COEFFICIENT` are two unrelated gas-phase output
quantities (FDS User Guide Table 22.4) — don't confuse them. `EXTINCTION`
(Sec. 22.10.29) is a combustion-suppression flag with no units: 0 if the
extinction routine did not prevent combustion, 1 if it did, -1 if there was
no fuel or oxidizer. `EXTINCTION COEFFICIENT` (Sec. 22.10.5) is the light
extinction coefficient K [1/m] that the smoke-speed model actually needs.
If your deck has `QUANTITY='EXTINCTION'` where you meant the extinction
coefficient, fix it to `QUANTITY='EXTINCTION COEFFICIENT'` and rerun FDS.

pyFDS-Evac reads `&SLCF` output only. `&DEVC` device output is listed by
`--inspect-fds` but not read by the run.

## Check the deck before you run FDS

`pyfds-evac init DECK.fds --check` reads the deck, before FDS runs, and
writes nothing. It applies the run's rule for choosing a slice and reports
each slice of the table above, `&TIME T_END`, `DT_SLCF` and the `&REAC`
yields, with the `&SLCF` line to add for each missing one. It exits with 0
when the deck has the extinction coefficient, CO, CO2, O2 and `T_END`, with
3 when one is missing, and with 1 when the deck cannot be read, the floor
cannot be chosen or an argument is wrong. The full
list is in
[Usage › init --check](usage.md#check-a-deck-before-running-fds--pyfds-evac-init---check),
and [Start from your own FDS case](start-from-fds-deck.md) shows it on a
ready deck and on one that fails.

## Declaring a slice is not enough

The species also has to exist in the run. Under simple chemistry, `OXYGEN`,
`NITROGEN`, `WATER VAPOR` and `CARBON DIOXIDE` are always present, but
`CARBON MONOXIDE` only exists if `CO_YIELD` is set on `&REAC`, and `SOOT` only
if `SOOT_YIELD` is set. A plain `&REAC FUEL='PROPANE' /` cannot produce FED no
matter what `&SLCF` lines you add. Fix it at the source:

```
&REAC FUEL='CABLE_FUEL', C=3, H=5, O=0, N=1,
      SOOT_YIELD=0.172, CO_YIELD=0.063, HCN_YIELD=0.006,
      HEAT_OF_COMBUSTION=16400 /
```

That is the `t_junction` reaction. Yields are fuel properties: take them from
your material's data rather than copying these.

`TEMPERATURE` is the one exception: it is a core solved gas-phase variable in
every FDS run, not a species yield, so it needs no `&REAC` setup at all — the
`&SLCF` line above is sufficient on its own.

## Silent failure modes

**FED disabled.** If CO, CO2 or O2 is missing, pyFDS-Evac carries on with
smoke speed only. If the heat FED is off too, the result has no FED at all:
`fed_history` is `None`, `metrics` has no `fed_max`, and
`--output-fed-history` writes no file. If the heat FED runs but the gas FED
does not, the FED history exists and its `fed_cumulative` column is all
zero, which looks exactly like a survivable fire. Check `metrics["fed_max"]`,
or the warning, which is logged every time
([#137](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/137)):

```
FED is disabled for <dir>: it has no CO slice, and all three of CO, CO2 and
O2 are needed. ...
```

**Heat FED disabled.** The heat FED track is off unless `--enable-heat-fed`
is given. With it, the same applies as for the gases: if there is no
`TEMPERATURE` slice, heat FED is off, `metrics` has no `heat_fed_max`, and
any heat FED column in the history reads zero:

```
Heat FED is disabled for <dir>: it has no TEMPERATURE slice. ...
```

**Wrong slice height.** `--smoke-slice-height` (default 1.6 m, [FDS+Evac](https://github.com/firemodels/fds/tree/c9da70d7a/Source)'s `HUMAN_SMOKE_HEIGHT`) is a
preference, not a filter: a case with one slice of a quantity uses it whatever
its height, and a mismatch never fails the run. A case you inherit often
carries a single slice at whatever height its author chose, so you can end up
sampling floor-level CO for standing agents. A warning fires only past 0.5 m.
The common case, a request of 1.6 m on a deck with a single slice at 2.0 m, is
0.4 m away and gives no warning
([#165](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/165)). Beyond
0.5 m you see:

```
Requested a 'SOOT EXTINCTION COEFFICIENT' slice at z=0.50 m but the nearest
available in <dir> is at z=2.00 m ...
```

Do not ignore these warnings. Nothing else will tell you.

## Failure modes

| Symptom | Cause |
|---------|-------|
| Warning: Smoke speed reduction is disabled for `<dir>`, and Visibility falls back to clear air for `<dir>` | No `SOOT EXTINCTION COEFFICIENT` slice: the deck never declared `&SLCF QUANTITY='EXTINCTION COEFFICIENT'`, or the species was never tracked. Agents walk and see as in clear air. |
| `IndexError: No slice with quantity '...' found in <dir>` | A direct library call on a case without that slice: the deck never declared that `&SLCF`, or the species was never tracked. |
| Warning: FED is disabled for `<dir>` | CO, CO2 or O2 is missing. Check `CO_YIELD` on `&REAC`. |
| Warning: Heat FED is disabled for `<dir>` | No `TEMPERATURE` slice. Add `&SLCF QUANTITY='TEMPERATURE'` — no `&REAC` change needed. |
| FED is zero everywhere and nobody is incapacitated | Either genuinely survivable, or FED never ran. Check for the warning above before concluding the former. |
| Warning: `FDS coverage: outside the FDS slices (...), agents read ambient air and clear sight: walkable area ... m² ... Walkable area x ..., FDS domain x ...` | Part of the scenario lies outside the slices of a sampled quantity. Agents there read *K* = 0, ambient gases and 20 °C, as in FDS+Evac, and read signs in clear air within their reading distance. The smoke and FED histories mark those rows with `in_fds_domain = False`, and the run ends with a count of the samples outside. Compare the two bounds: if the walkable area is meant to lie inside, its origin or axis order differs from the deck's. See [FDS slice sampling](fds-sampling.md#outside-the-fds-slices). |
| The same warning ending `With x and y swapped the walkable area would lie inside the FDS domain`, `Shifted by (dx, dy) m the walkable area would lie inside the FDS domain`, or `With x and y swapped and shifted by (dx, dy) m ...` | The geometry and the FDS deck use different frames: x and y swapped, or a different origin. Draw the walkable area in the deck's frame, or derive it from the deck with `pyfds-evac init`. |
| `FdsDomainError: ... outside the FDS slice domain (--require-fds-coverage)`, or `FdsDomainError: FDS coverage: ...` at setup | `--require-fds-coverage` is set and part of the scenario, or a sample, lies outside the slices. Extend the FDS meshes or slices, or run without the option. |
| Warning: `N sign(s) lie outside the FDS extinction slice that sign visibility is computed on, ...`; with `--require-fds-coverage` the same text as `FdsDomainError`, ending `Extend the FDS meshes over the signs, or run without --require-fds-coverage.` | A sign lies off the vismap grid. fdsvismap casts its sight lines from the nearest grid edge. See [Wayfinding](/models/wayfinding.md#off-the-fds-grid). |
| `ValueError: Point (x, y) at t=... lies outside the <quantity> slice but inside another FED gas slice` | The gas slices cover different areas ([#427](https://github.com/PedestrianDynamics/pyFDS-Evac/issues/427)). Give all gas slices the same meshes. |
| Warning: requested slice at z=A, nearest is z=B | Your case has no slice near the height you asked for. |

Errors from the command line itself (wrong `--fds-dir`, conflicting flags)
are listed on [Troubleshooting](troubleshooting.md).
