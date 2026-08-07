# What your FDS case must provide

Read this before pointing `--fds-dir` at a case for the first time.

**pyFDS-Evac never runs FDS.** It reads the output of a finished FDS run.
A deck written for some other purpose usually will not work as-is: it has to
be told to dump the specific slices this tool samples.

## The slices

```
&SLCF PBZ=2.0, QUANTITY='EXTINCTION COEFFICIENT' /
&SLCF PBZ=2.0, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON MONOXIDE' /
&SLCF PBZ=2.0, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON DIOXIDE' /
&SLCF PBZ=2.0, QUANTITY='VOLUME FRACTION', SPEC_ID='OXYGEN' /
&SLCF PBZ=2.0, QUANTITY='TEMPERATURE' /
&DUMP DT_SLCF=1.0 /
```

Nothing here is dumped by default. FDS writes only what the deck asks for.

For the default species (soot), FDS records the extinction-coefficient
slice internally as `SOOT EXTINCTION COEFFICIENT`, and that is the exact
quantity name `load_slice_sampler` looks up
([fds-sampling.md](fds-sampling.md)).

| Slice | Feeds | If absent |
|-------|-------|-----------|
| Extinction coefficient | smoke-speed, visibility gating, GUI smoke layer | `IndexError` when `--fds-dir` is given without `--constant-extinction` |
| CO **and** CO2 **and** O2 | FED toxic dose | **FED is switched off and the run continues** (see below) |
| TEMPERATURE | heat FED (ISO TS 13571 eq. 5) | **heat FED is switched off and the run continues** (see below) |

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

## Two silent failure modes

**FED disabled.** If CO, CO2 or O2 is missing, pyFDS-Evac carries on with
smoke-speed only and every FED column reads zero. A zero-dose result looks
exactly like a never-computed one. A warning is logged when this happens, and
it is the only signal you get:

```
FED is disabled for <dir>: it has no CO slice, and all three of CO, CO2 and
O2 are needed. ...
```

**Heat FED disabled.** The same applies to the independent heat FED track: if
there is no `TEMPERATURE` slice, heat FED is silently off, and every heat FED
column reads zero:

```
Heat FED is disabled for <dir>: it has no TEMPERATURE slice. ...
```

**Wrong slice height.** `--smoke-slice-height` (default 2.0 m) is a
preference, not a filter: a case with one slice of a quantity uses it whatever
its height, and a mismatch never fails the run. A case you inherit often
carries a single slice at whatever height its author chose, so you can end up
sampling floor-level CO for standing agents. A warning fires past 0.5 m:

```
Requested a 'SOOT EXTINCTION COEFFICIENT' slice at z=0.50 m but the nearest
available in <dir> is at z=2.00 m ...
```

Do not ignore either warning. Nothing else will tell you.

## Failure modes

| Symptom | Cause |
|---------|-------|
| `IndexError: No slice with quantity 'SOOT EXTINCTION COEFFICIENT' found in <dir>` | The deck never declared `&SLCF QUANTITY='EXTINCTION COEFFICIENT'`, or the species was never tracked. |
| `IndexError: No slice with quantity '...' found in <dir>` | The deck never declared that `&SLCF`, or the species was never tracked. |
| Warning: FED is disabled for `<dir>` | CO, CO2 or O2 is missing. Check `CO_YIELD` on `&REAC`. |
| Warning: Heat FED is disabled for `<dir>` | No `TEMPERATURE` slice. Add `&SLCF QUANTITY='TEMPERATURE'` — no `&REAC` change needed. |
| FED is zero everywhere and nobody is incapacitated | Either genuinely survivable, or FED never ran. Check for the warning above before concluding the former. |
| `ValueError: Point (x, y) is outside the sampled FDS slice domain` | Walkable area extends past the slice extent. |
| Warning: requested slice at z=A, nearest is z=B | Your case has no slice near the height you asked for. |
